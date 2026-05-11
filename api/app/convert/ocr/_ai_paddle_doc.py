"""PaddleOCR-VL doc_parser methods for AiOcrClient (mixin)."""

import copy
import contextvars
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import re
import tempfile
import threading
import time
from typing import Any, Dict, List

try:
    import fcntl
except Exception:
    fcntl = None

from PIL import Image

from .base import (
    _PADDLE_OCR_VL_MODEL_V1,
    _PADDLE_OCR_VL_MODEL_V15,
    _clean_str,
    _env_flag,
    _env_float,
    _is_probably_model_unsupported_error,
    _normalize_paddle_doc_backend,
    _normalize_paddle_doc_server_url,
    _resolve_paddle_doc_model_and_pipeline,
    _run_in_daemon_thread_with_timeout,
)
from .result_parsing import (
    _derive_paddle_doc_predict_max_pixels,
    _extract_paddle_doc_parser_output,
    _scale_paddle_doc_parser_output,
)
from .vendors import get_vendor_tuning
from .utils import _coerce_bbox_xyxy
from ._ai_helpers import (
    _compact_debug_text,
    _clone_image_region_payload,
    _coerce_layout_geometry_points,
    _get_paddle_predict_timeout,
    _layout_geometry_kind,
    _normalize_ai_layout_model_name,
    _resolve_paddlex_layout_model_name,
    _sanitize_debug_value,
    _utc_now_iso,
)

logger = logging.getLogger(__name__)


class _PaddleDocMixin:
    """Mixin providing PaddleOCR-VL doc_parser methods for AiOcrClient."""

    def _should_use_paddle_doc_parser(self) -> bool:
        if self._paddle_doc_parser_disabled:
            return False
        if self.requested_route_kind == ROUTE_KIND_REMOTE_PROMPT_OCR:
            return False
        if self.requested_route_kind == ROUTE_KIND_REMOTE_DOC_PARSER:
            return True
        # Explicit env switch takes highest priority for debugging/rollout.
        explicit_env = os.getenv("OCR_PADDLE_VL_USE_DOCPARSER")
        if explicit_env is not None:
            return _env_flag("OCR_PADDLE_VL_USE_DOCPARSER", default=True)
        return self.vendor_adapter.should_use_paddle_doc_parser(
            base_url=self.base_url,
            model_name=self.model,
        )

    def _describe_paddle_doc_parser_unavailable_reason(self) -> str:
        if self._paddle_doc_parser_disabled:
            return "doc_parser was disabled after a previous dedicated-channel failure"
        if self.requested_route_kind == ROUTE_KIND_REMOTE_PROMPT_OCR:
            return "current chain mode is direct/prompt, not doc_parser"
        explicit_env = os.getenv("OCR_PADDLE_VL_USE_DOCPARSER")
        if explicit_env is not None and not _env_flag(
            "OCR_PADDLE_VL_USE_DOCPARSER",
            default=True,
        ):
            return "OCR_PADDLE_VL_USE_DOCPARSER=0 disables doc_parser routing"
        return (
            "current provider/base_url does not advertise PaddleOCR-VL doc_parser support "
            f"(provider={self.provider_id}, base_url={self.base_url or 'unset'})"
        )

    def _uses_remote_doc_parser(self) -> bool:
        return (
            _is_paddleocr_vl_model(self.model) and self._should_use_paddle_doc_parser()
        )

    def _uses_local_layout_block_ocr(self) -> bool:
        return self.requested_route_kind == ROUTE_KIND_LOCAL_LAYOUT_BLOCK_OCR

    def _refresh_route_kind(self) -> str:
        if self._uses_local_layout_block_ocr():
            self.route_kind = ROUTE_KIND_LOCAL_LAYOUT_BLOCK_OCR
            return self.route_kind
        self.route_kind = (
            ROUTE_KIND_REMOTE_DOC_PARSER
            if self._uses_remote_doc_parser()
            else ROUTE_KIND_REMOTE_PROMPT_OCR
        )
        return self.route_kind

    def _extract_paddle_doc_block_query_text(self, messages: Any) -> str:
        texts: list[str] = []

        def _collect(content: Any) -> None:
            if isinstance(content, str):
                compact = _compact_debug_text(content, limit=_DEBUG_TEXT_CONTENT_LIMIT)
                if compact:
                    texts.append(compact)
                return
            if isinstance(content, list):
                for item in content:
                    _collect(item)
                return
            if not isinstance(content, dict):
                return
            item_type = str(content.get("type") or "").strip().lower()
            if item_type == "text":
                _collect(content.get("text"))
                return
            if item_type == "image_url":
                return
            if "text" in content:
                _collect(content.get("text"))
                return
            if "content" in content:
                _collect(content.get("content"))

        if isinstance(messages, list):
            for message in messages:
                if isinstance(message, dict):
                    _collect(message.get("content"))
        else:
            _collect(messages)

        return _compact_debug_text(" ".join(texts), limit=_DEBUG_TEXTS_LIMIT)

    def _extract_paddle_doc_block_label(self, query_text: str) -> str | None:
        if not query_text:
            return None
        prompt_match = re.match(
            r"^\s*([A-Za-z][A-Za-z ]{0,64}?)(?:\s+Recognition)?\s*:\s*$",
            query_text,
            flags=re.IGNORECASE,
        )
        if prompt_match:
            label = _compact_debug_text(prompt_match.group(1), limit=_DEBUG_LABEL_LIMIT).strip()
            if label:
                return label
        patterns = (
            r"<label>\s*([^<]{1,64})\s*</label>",
            r"(?:label|type|category)\s*(?:is|:)\s*['\"]?([a-zA-Z0-9_./-]{1,64})",
            r"text block\s+(?:is|labelled|labeled)\s+['\"]?([a-zA-Z0-9_./-]{1,64})",
            r"block\s+(?:type|label)\s*(?:is|:)\s*['\"]?([a-zA-Z0-9_./-]{1,64})",
        )
        for pattern in patterns:
            match = re.search(pattern, query_text, flags=re.IGNORECASE)
            if match:
                label = _compact_debug_text(match.group(1), limit=_DEBUG_LABEL_LIMIT).strip(" .,:;")
                if label:
                    return label
        return None

    def _extract_paddle_doc_pixel_bucket(
        self, kwargs: dict[str, Any]
    ) -> dict[str, Any]:
        mm_processor_kwargs: dict[str, Any] = {}
        extra_body = kwargs.get("extra_body")
        if isinstance(extra_body, dict):
            raw_mm_processor_kwargs = extra_body.get("mm_processor_kwargs")
            if isinstance(raw_mm_processor_kwargs, dict):
                mm_processor_kwargs = raw_mm_processor_kwargs

        def _coerce_int(value: Any) -> int | None:
            try:
                if value is None:
                    return None
                parsed = int(value)
            except Exception:
                return None
            return parsed if parsed > 0 else None

        min_pixels = _coerce_int(mm_processor_kwargs.get("min_pixels"))
        max_pixels = _coerce_int(mm_processor_kwargs.get("max_pixels"))
        bucket_parts: list[str] = []
        if min_pixels is not None:
            bucket_parts.append(f"min={min_pixels}")
        if max_pixels is not None:
            bucket_parts.append(f"max={max_pixels}")
        return {
            "min_pixels": min_pixels,
            "max_pixels": max_pixels,
            "bucket": ",".join(bucket_parts) if bucket_parts else None,
        }

    def _begin_paddle_doc_predict_trace(
        self,
        *,
        image_path: str,
        predict_image_path: str,
        predict_kwargs: dict[str, Any],
        timeout_s: float,
        label: str,
        max_side_px: int,
        scale_x: float,
        scale_y: float,
    ) -> dict[str, Any]:
        with self._paddle_doc_trace_lock:
            trace = {
                "attempt_label": str(label),
                "status": "running",
                "provider": str(self.provider_id or ""),
                "requested_model": str(self.model or ""),
                "effective_model": str(
                    self._paddle_doc_effective_model or self.model or ""
                ),
                "pipeline_version": self._paddle_doc_pipeline_version,
                "image_path": str(image_path),
                "predict_image_path": str(predict_image_path),
                "predict_kwargs": _sanitize_debug_value(dict(predict_kwargs)),
                "timeout_s": float(timeout_s),
                "max_side_px": int(max_side_px),
                "scale_x": float(scale_x),
                "scale_y": float(scale_y),
                "started_at": _utc_now_iso(),
                "blocks": [],
                "_started_monotonic": time.monotonic(),
                "_last_progress_log_monotonic": 0.0,
            }
            self._paddle_doc_active_predict_trace = trace
            return trace

    def _register_paddle_doc_block_request(
        self,
        *,
        messages: Any,
        kwargs: dict[str, Any],
    ) -> dict[str, Any] | None:
        query_text = self._extract_paddle_doc_block_query_text(messages)
        pixel_bucket = self._extract_paddle_doc_pixel_bucket(kwargs)
        with self._paddle_doc_trace_lock:
            trace = self._paddle_doc_active_predict_trace
            if not isinstance(trace, dict):
                return None
            self._paddle_doc_trace_serial += 1
            entry = {
                "seq": int(self._paddle_doc_trace_serial),
                "status": "pending",
                "label": self._extract_paddle_doc_block_label(query_text),
                "query_preview": query_text or None,
                "pixel_bucket": pixel_bucket.get("bucket"),
                "min_pixels": pixel_bucket.get("min_pixels"),
                "max_pixels": pixel_bucket.get("max_pixels"),
                "started_at": _utc_now_iso(),
                "_started_monotonic": time.monotonic(),
            }
            trace.setdefault("blocks", []).append(entry)
            return entry

    def _complete_paddle_doc_block_request(
        self,
        entry: dict[str, Any] | None,
        *,
        error: BaseException | None = None,
    ) -> None:
        if not isinstance(entry, dict):
            return
        with self._paddle_doc_trace_lock:
            if str(entry.get("status") or "") != "pending":
                return
            elapsed_ms = int(
                round(
                    max(
                        0.0,
                        time.monotonic()
                        - float(entry.get("_started_monotonic") or 0.0),
                    )
                    * 1000.0
                )
            )
            entry["finished_at"] = _utc_now_iso()
            entry["elapsed_ms"] = elapsed_ms
            if error is None:
                entry["status"] = "success"
                return
            entry["status"] = "error"
            entry["error"] = _compact_debug_text(error, limit=240)

    def _summarize_paddle_doc_unfinished_blocks(
        self, blocks: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        now_monotonic = time.monotonic()
        summaries: list[dict[str, Any]] = []
        for block in blocks:
            if not isinstance(block, dict):
                continue
            if str(block.get("status") or "") != "pending":
                continue
            age_ms = int(
                round(
                    max(
                        0.0,
                        now_monotonic - float(block.get("_started_monotonic") or 0.0),
                    )
                    * 1000.0
                )
            )
            summaries.append(
                {
                    "seq": block.get("seq"),
                    "label": block.get("label"),
                    "pixel_bucket": block.get("pixel_bucket"),
                    "started_at": block.get("started_at"),
                    "age_ms": age_ms,
                    "query_preview": block.get("query_preview"),
                }
            )
        return summaries

    def _finalize_paddle_doc_predict_trace(
        self,
        trace: dict[str, Any] | None,
        *,
        status: str,
        error: BaseException | str | None = None,
        raw_element_count: int | None = None,
        image_region_count: int | None = None,
        layout_block_count: int | None = None,
    ) -> dict[str, Any] | None:
        if not isinstance(trace, dict):
            return None
        with self._paddle_doc_trace_lock:
            elapsed_ms = int(
                round(
                    max(
                        0.0,
                        time.monotonic()
                        - float(trace.get("_started_monotonic") or 0.0),
                    )
                    * 1000.0
                )
            )
            trace["status"] = str(status or "unknown")
            trace["finished_at"] = _utc_now_iso()
            trace["elapsed_ms"] = elapsed_ms
            if error is not None:
                trace["error"] = _compact_debug_text(error, limit=320)

            blocks = [
                block
                for block in (trace.get("blocks") or [])
                if isinstance(block, dict)
            ]
            success_count = sum(
                1 for block in blocks if str(block.get("status") or "") == "success"
            )
            error_count = sum(
                1 for block in blocks if str(block.get("status") or "") == "error"
            )
            pending_count = sum(
                1 for block in blocks if str(block.get("status") or "") == "pending"
            )
            trace["block_counts"] = {
                "total": len(blocks),
                "success": success_count,
                "error": error_count,
                "pending": pending_count,
            }
            trace["unfinished_blocks"] = self._summarize_paddle_doc_unfinished_blocks(
                blocks
            )
            if raw_element_count is not None:
                trace["raw_element_count"] = int(raw_element_count)
            if image_region_count is not None:
                trace["image_region_count"] = int(image_region_count)
            if layout_block_count is not None:
                trace["layout_block_count"] = int(layout_block_count)

            sanitized = _sanitize_debug_value(copy.deepcopy(trace))
            self._paddle_doc_last_predict_debug = sanitized
            history = list(self._paddle_doc_recent_predict_debug)
            history.append(sanitized)
            self._paddle_doc_recent_predict_debug = history[-3:]
            if self._paddle_doc_active_predict_trace is trace:
                self._paddle_doc_active_predict_trace = None
            return copy.deepcopy(sanitized)

    def _log_paddle_doc_timeout_trace(
        self,
        trace_debug: dict[str, Any] | None,
        *,
        timeout_s: float,
    ) -> None:
        if not isinstance(trace_debug, dict):
            return
        blocks = trace_debug.get("unfinished_blocks")
        if not isinstance(blocks, list):
            blocks = []
        payload = {
            "attempt_label": trace_debug.get("attempt_label"),
            "timeout_s": float(timeout_s),
            "requested_model": trace_debug.get("requested_model"),
            "effective_model": trace_debug.get("effective_model"),
            "predict_image_path": trace_debug.get("predict_image_path"),
            "predict_image_name": Path(
                str(trace_debug.get("predict_image_path") or "")
            ).name
            or None,
            "block_counts": trace_debug.get("block_counts"),
            "unfinished_blocks": blocks[:12],
        }
        logger.warning(
            "PaddleOCR-VL doc_parser timeout diagnostics: %s",
            json.dumps(payload, ensure_ascii=True, sort_keys=True),
        )

    def _resolve_paddle_doc_progress_log_interval_s(self) -> float:
        return max(
            0.0,
            _env_float("OCR_PADDLE_VL_DOCPARSER_PROGRESS_LOG_INTERVAL_S", 10.0),
        )

    def _maybe_log_paddle_doc_progress_trace(self, *, force: bool = False) -> None:
        interval_s = self._resolve_paddle_doc_progress_log_interval_s()
        if interval_s <= 0.0 and not force:
            return
        with self._paddle_doc_trace_lock:
            trace = self._paddle_doc_active_predict_trace
            if not isinstance(trace, dict):
                return
            now_monotonic = time.monotonic()
            last_logged = float(
                trace.get("_last_progress_log_monotonic")
                or trace.get("_started_monotonic")
                or 0.0
            )
            if not force and (now_monotonic - last_logged) < interval_s:
                return
            blocks = [
                block
                for block in (trace.get("blocks") or [])
                if isinstance(block, dict)
            ]
            payload = {
                "attempt_label": trace.get("attempt_label"),
                "elapsed_ms": int(
                    round(
                        max(
                            0.0,
                            now_monotonic
                            - float(trace.get("_started_monotonic") or now_monotonic),
                        )
                        * 1000.0
                    )
                ),
                "requested_model": trace.get("requested_model"),
                "effective_model": trace.get("effective_model"),
                "predict_image_name": Path(
                    str(trace.get("predict_image_path") or "")
                ).name
                or None,
                "block_counts": {
                    "total": len(blocks),
                    "success": sum(
                        1
                        for block in blocks
                        if str(block.get("status") or "") == "success"
                    ),
                    "error": sum(
                        1
                        for block in blocks
                        if str(block.get("status") or "") == "error"
                    ),
                    "pending": sum(
                        1
                        for block in blocks
                        if str(block.get("status") or "") == "pending"
                    ),
                },
                "unfinished_blocks": self._summarize_paddle_doc_unfinished_blocks(
                    blocks
                )[:12],
            }
            trace["_last_progress_log_monotonic"] = now_monotonic
        logger.info(
            "PaddleOCR-VL doc_parser progress: %s",
            json.dumps(payload, ensure_ascii=True, sort_keys=True),
        )

    def _ensure_paddle_doc_block_instrumentation(self, parser_local: Any) -> None:
        paddlex_pipeline = getattr(parser_local, "paddlex_pipeline", None)
        vl_rec_model = getattr(paddlex_pipeline, "vl_rec_model", None)
        genai_client = getattr(vl_rec_model, "_genai_client", None)
        if genai_client is None:
            return
        if bool(getattr(genai_client, "_ppt_block_trace_installed", False)):
            return

        original_create = getattr(genai_client, "create_chat_completion", None)
        if not callable(original_create):
            return

        def _wrapped_create_chat_completion(
            messages: Any, *, return_future: bool = False, **kwargs: Any
        ) -> Any:
            entry = self._register_paddle_doc_block_request(
                messages=messages,
                kwargs=kwargs,
            )
            try:
                result = original_create(
                    messages,
                    return_future=return_future,
                    **kwargs,
                )
            except Exception as exc:  # noqa: BLE001
                self._complete_paddle_doc_block_request(entry, error=exc)
                raise
            if entry is None:
                return result
            if return_future and hasattr(result, "add_done_callback"):

                def _on_done(future: Any, block_entry: dict[str, Any] = entry) -> None:
                    try:
                        future.result()
                    except BaseException as exc:  # noqa: BLE001
                        self._complete_paddle_doc_block_request(
                            block_entry,
                            error=exc,
                        )
                    else:
                        self._complete_paddle_doc_block_request(block_entry)

                result.add_done_callback(_on_done)
                return result
            self._complete_paddle_doc_block_request(entry)
            return result

        setattr(genai_client, "create_chat_completion", _wrapped_create_chat_completion)
        setattr(genai_client, "_ppt_block_trace_installed", True)
        logger.info(
            "Enabled PaddleOCR-VL doc_parser block tracing (provider=%s, model=%s)",
            self.provider_id,
            self._paddle_doc_effective_model or self.model,
        )

    def _get_paddle_doc_parser(self) -> Any:
        if self._paddle_doc_parser is not None:
            self._ensure_paddle_doc_block_instrumentation(self._paddle_doc_parser)
            return self._paddle_doc_parser

        try:
            from paddleocr import PaddleOCRVL
        except Exception as e:
            raise RuntimeError(
                "PaddleOCR-VL dedicated adapter requires `paddleocr` package"
            ) from e

        raw_server_url = (
            _clean_str(os.getenv("OCR_PADDLE_VL_REC_SERVER_URL"))
            or self.base_url
            or self.vendor_adapter.resolve_base_url(None)
        )
        server_url = _normalize_paddle_doc_server_url(
            raw_server_url,
            provider_id=self.provider_id,
        )
        if not server_url:
            raise RuntimeError("PaddleOCR-VL dedicated adapter requires base_url")

        backend = _normalize_paddle_doc_backend(os.getenv("OCR_PADDLE_VL_REC_BACKEND"))
        effective_model, pipeline_version = _resolve_paddle_doc_model_and_pipeline(
            model=self.model,
            provider_id=self.provider_id,
            allow_model_downgrade=self.allow_model_downgrade,
        )

        kwargs: dict[str, Any] = {
            "vl_rec_backend": backend,
            "vl_rec_server_url": server_url,
            "vl_rec_api_key": self.api_key,
            "vl_rec_api_model_name": effective_model,
        }
        kwargs.update(
            self._resolve_paddle_doc_parser_tuning_kwargs(
                effective_model=effective_model,
            )
        )
        if pipeline_version:
            kwargs["pipeline_version"] = pipeline_version

        init_timeout_s = _env_float("OCR_PADDLE_VL_DOCPARSER_INIT_TIMEOUT_S", 30.0)
        try:
            self._paddle_doc_parser = _run_in_daemon_thread_with_timeout(
                lambda: PaddleOCRVL(**kwargs),
                timeout_s=init_timeout_s,
                label="paddleocr-vl:init",
            )
        except TimeoutError as e:
            # Disable doc_parser for this client. Callers may optionally enable
            # prompt fallback via OCR_PADDLE_VL_ALLOW_PROMPT_FALLBACK.
            self._paddle_doc_parser_disabled = True
            raise RuntimeError(str(e)) from e
        except Exception:
            # Disable doc_parser for this client.
            self._paddle_doc_parser_disabled = True
            raise
        self._paddle_doc_effective_model = effective_model
        self._paddle_doc_pipeline_version = pipeline_version
        self._paddle_doc_server_url = server_url
        self._paddle_doc_backend = backend
        logger.info(
            "Initialized PaddleOCR-VL doc_parser adapter (provider=%s, requested_model=%s, effective_model=%s, pipeline_version=%s, base_url=%s, backend=%s, max_concurrency=%s, use_queues=%s)",
            self.provider_id,
            self.model,
            effective_model,
            pipeline_version or "<default>",
            server_url,
            backend,
            kwargs.get("vl_rec_max_concurrency"),
            kwargs.get("use_queues"),
        )
        self._ensure_paddle_doc_block_instrumentation(self._paddle_doc_parser)
        return self._paddle_doc_parser

    def _resolve_paddle_doc_parser_tuning_kwargs(
        self, *, effective_model: str
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        lowered_model = str(effective_model or "").strip().lower()

        raw_max_concurrency = _clean_str(
            os.getenv("OCR_PADDLE_VL_DOCPARSER_MAX_CONCURRENCY")
        )
        if raw_max_concurrency is not None:
            try:
                parsed_max_concurrency = int(raw_max_concurrency)
            except Exception:
                parsed_max_concurrency = 0
            if parsed_max_concurrency > 0:
                kwargs["vl_rec_max_concurrency"] = parsed_max_concurrency
        elif "paddleocr-vl-1.5" in lowered_model:
            tuning = get_vendor_tuning(self.provider_id)
            kwargs["vl_rec_max_concurrency"] = tuning.vl_rec_max_concurrency

        raw_use_queues = _clean_str(os.getenv("OCR_PADDLE_VL_DOCPARSER_USE_QUEUES"))
        if raw_use_queues is not None:
            kwargs["use_queues"] = _env_flag(
                "OCR_PADDLE_VL_DOCPARSER_USE_QUEUES",
                default=True,
            )
        elif "paddleocr-vl-1.5" in lowered_model:
            tuning = get_vendor_tuning(self.provider_id)
            kwargs["use_queues"] = tuning.use_queues
        return kwargs

    def _resolve_paddle_doc_predict_timeout_s(self) -> float:
        default_timeout = max(
            _PADDLE_MIN_PREDICT_TIMEOUT_S,
            _env_float("OCR_PADDLE_VL_DOCPARSER_PREDICT_TIMEOUT_S", 120.0),
        )
        lowered_model = str(self.model or "").strip().lower()
        if "paddleocr-vl-1.5" in lowered_model:
            tuning = get_vendor_tuning(self.provider_id)
            v15_default = max(default_timeout, tuning.predict_timeout_override or _get_paddle_predict_timeout())
            return max(
                _PADDLE_MIN_PREDICT_TIMEOUT_S,
                _env_float(
                    "OCR_PADDLE_VL_DOCPARSER_PREDICT_TIMEOUT_S_V15",
                    v15_default,
                ),
            )
        return default_timeout

    def _resolve_paddle_doc_retry_timeout_s(self, *, predict_timeout_s: float) -> float:
        default_retry_timeout_s = min(_PADDLE_RETRY_TIMEOUT_CAP_S, predict_timeout_s)
        lowered_model = str(self.model or "").strip().lower()
        if "paddleocr-vl-1.5" in lowered_model:
            tuning = get_vendor_tuning(self.provider_id)
            retry_default = tuning.retry_timeout_override
            if retry_default is not None:
                return max(
                    _PADDLE_MIN_PREDICT_TIMEOUT_S,
                    _env_float(
                        "OCR_PADDLE_VL_DOCPARSER_RETRY_TIMEOUT_S",
                        min(retry_default, predict_timeout_s),
                    ),
                )
        return max(
            _PADDLE_MIN_PREDICT_TIMEOUT_S,
            _env_float(
                "OCR_PADDLE_VL_DOCPARSER_RETRY_TIMEOUT_S",
                default_retry_timeout_s,
            ),
        )

    def _is_vendor_paddle_doc_v15(self) -> bool:
        """Check if current model is PaddleOCR-VL-1.5 (vendor-agnostic)."""
        lowered_model = str(self.model or "").strip().lower()
        return "paddleocr-vl-1.5" in lowered_model

    def _should_retry_paddle_doc_timeout(self) -> bool:
        raw_generic = os.getenv("OCR_PADDLE_VL_DOCPARSER_RETRY_ON_TIMEOUT")
        if self._is_vendor_paddle_doc_v15():
            if raw_generic is not None:
                return _env_flag(
                    "OCR_PADDLE_VL_DOCPARSER_RETRY_ON_TIMEOUT",
                    default=False,
                )
            tuning = get_vendor_tuning(self.provider_id)
            return tuning.retry_on_timeout
        return _env_flag("OCR_PADDLE_VL_DOCPARSER_RETRY_ON_TIMEOUT", default=True)

    def _should_use_paddle_doc_singleflight(self) -> bool:
        raw_generic = os.getenv("OCR_PADDLE_VL_DOCPARSER_SINGLEFLIGHT")
        if self._is_vendor_paddle_doc_v15():
            if raw_generic is not None:
                return _env_flag(
                    "OCR_PADDLE_VL_DOCPARSER_SINGLEFLIGHT",
                    default=True,
                )
            tuning = get_vendor_tuning(self.provider_id)
            return tuning.singleflight
        return _env_flag("OCR_PADDLE_VL_DOCPARSER_SINGLEFLIGHT", default=False)

    def _resolve_paddle_doc_singleflight_wait_s(self) -> float:
        # Vendor-specific wait time: some providers need longer singleflight
        # locks due to sequential page processing characteristics.
        tuning = get_vendor_tuning(self.provider_id)
        default_wait_s = (
            tuning.singleflight_wait_s
            if self._is_vendor_paddle_doc_v15()
            else _SINGLEFLIGHT_WAIT_S
        )
        return max(
            0.0,
            _env_float("OCR_PADDLE_VL_DOCPARSER_SINGLEFLIGHT_WAIT_S", default_wait_s),
        )

    def _resolve_paddle_doc_singleflight_lock_path(self) -> Path:
        raw_lock_dir = _clean_str(
            os.getenv("OCR_PADDLE_VL_DOCPARSER_SINGLEFLIGHT_LOCK_DIR")
        )
        lock_dir = Path(raw_lock_dir) if raw_lock_dir else Path("/tmp")
        lock_key = "|".join(
            [
                str(self.provider_id or "").strip().lower(),
                str(self.base_url or "").strip().lower(),
                str(self.model or "").strip().lower(),
                str(self._paddle_doc_pipeline_version or "").strip().lower(),
            ]
        )
        digest = hashlib.sha1(lock_key.encode("utf-8")).hexdigest()[:24]
        return lock_dir / f"paddleocr-vl-docparser-{digest}.lock"

    def _describe_paddle_doc_predict_target(self) -> str:
        with self._paddle_doc_trace_lock:
            trace = self._paddle_doc_active_predict_trace
            if not isinstance(trace, dict):
                return "<unknown>"
            raw_path = (
                trace.get("predict_image_path")
                or trace.get("image_path")
                or trace.get("attempt_label")
            )
        raw_text = str(raw_path or "").strip()
        if not raw_text:
            return "<unknown>"
        try:
            return Path(raw_text).name or raw_text
        except Exception:
            return raw_text

    def _release_paddle_doc_singleflight_lock(self, lock_file: Any | None) -> None:
        if lock_file is None or fcntl is None:
            return
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        try:
            lock_file.close()
        except Exception:
            pass

    def _resolve_paddle_doc_max_side_px(self) -> int:
        if self._paddle_doc_max_side_px_override is not None:
            return int(self._paddle_doc_max_side_px_override)
        from ...config import get_settings
        return max(0, int(get_settings().ocr_paddle_vl_docparser_max_side_px))

    def _prepare_paddle_doc_predict_image(
        self, image_path: str
    ) -> tuple[str, float, float, Path | None]:
        max_side_px = self._resolve_paddle_doc_max_side_px()
        if max_side_px <= 0:
            return image_path, 1.0, 1.0, None

        try:
            with Image.open(image_path).convert("RGB") as image:
                width, height = image.size
                largest = max(int(width), int(height))
                if largest <= int(max_side_px):
                    return image_path, 1.0, 1.0, None

                ratio = float(max_side_px) / float(largest)
                new_width = max(32, int(round(float(width) * ratio)))
                new_height = max(32, int(round(float(height) * ratio)))
                resized = image.resize(
                    (new_width, new_height), Image.Resampling.LANCZOS
                )

                source_stat = Path(image_path).stat()
                digest = hashlib.sha1(
                    f"{image_path}|{source_stat.st_mtime_ns}|{source_stat.st_size}|{max_side_px}".encode(
                        "utf-8"
                    )
                ).hexdigest()[:16]
                temp_path = Path(tempfile.gettempdir()) / (
                    f"paddleocr-vl-{digest}-{new_width}x{new_height}.png"
                )
                resized.save(temp_path)
                logger.info(
                    "Downscaled PaddleOCR-VL doc_parser image from %sx%s to %sx%s (max_side=%s)",
                    width,
                    height,
                    new_width,
                    new_height,
                    max_side_px,
                )
                return (
                    str(temp_path),
                    float(width) / float(new_width),
                    float(height) / float(new_height),
                    temp_path,
                )
        except Exception as e:
            logger.warning(
                "Failed to prepare downscaled PaddleOCR-VL image for %s: %s",
                image_path,
                e,
            )
        return image_path, 1.0, 1.0, None

    def _run_paddle_doc_predict_with_timeout(
        self,
        func: Any,
        *,
        timeout_s: float,
        label: str,
    ) -> Any:
        effective_timeout = max(1.0, float(timeout_s))
        if not self._should_use_paddle_doc_singleflight() or fcntl is None:
            return _run_in_daemon_thread_with_timeout(
                func,
                timeout_s=effective_timeout,
                label=label,
            )

        lock_path = self._resolve_paddle_doc_singleflight_lock_path()
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        wait_timeout_s = self._resolve_paddle_doc_singleflight_wait_s()
        wait_deadline = time.monotonic() + float(wait_timeout_s)
        lock_file = None
        wait_logged = False

        while True:
            candidate = lock_path.open("a+b")
            try:
                fcntl.flock(candidate.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                lock_file = candidate
                break
            except BlockingIOError:
                candidate.close()
                if not wait_logged:
                    logger.warning(
                        "PaddleOCR-VL doc_parser waiting for singleflight lock (label=%s, wait_timeout_s=%.1f, lock=%s, target=%s)",
                        label,
                        wait_timeout_s,
                        lock_path,
                        self._describe_paddle_doc_predict_target(),
                    )
                    wait_logged = True
                if time.monotonic() >= wait_deadline:
                    self._maybe_log_paddle_doc_progress_trace(force=True)
                    raise TimeoutError(
                        f"{label} blocked by another in-flight PaddleOCR-VL doc_parser request "
                        f"after {wait_timeout_s:.1f}s"
                    )
                time.sleep(min(_CONCURRENCY_WAIT_MAX_S, max(_CONCURRENCY_WAIT_MIN_S, wait_deadline - time.monotonic())))

        done = threading.Event()
        result: dict[str, Any] = {}
        error: dict[str, BaseException] = {}
        ctx = contextvars.copy_context()

        def _runner() -> None:
            def _run_with_context() -> None:
                try:
                    result["value"] = func()
                except BaseException as exc:  # noqa: BLE001
                    error["error"] = exc
                finally:
                    self._release_paddle_doc_singleflight_lock(lock_file)
                    done.set()

            ctx.run(_run_with_context)

        thread = threading.Thread(target=_runner, name=f"timeout:{label}", daemon=True)
        thread.start()

        deadline = time.monotonic() + effective_timeout
        while True:
            remaining_s = max(0.0, deadline - time.monotonic())
            if remaining_s <= 0.0:
                self._maybe_log_paddle_doc_progress_trace(force=True)
                logger.warning(
                    "PaddleOCR-VL doc_parser timed out; releasing singleflight lock for follow-up requests (label=%s, timeout_s=%.0f, target=%s)",
                    label,
                    effective_timeout,
                    self._describe_paddle_doc_predict_target(),
                )
                self._release_paddle_doc_singleflight_lock(lock_file)
                lock_file = None
                raise TimeoutError(f"{label} timed out after {effective_timeout:.0f}s")
            if done.wait(timeout=min(_DONE_WAIT_TIMEOUT_S, remaining_s)):
                break
            self._maybe_log_paddle_doc_progress_trace()
        if "error" in error:
            raise error["error"]
        return result.get("value")

    def _ocr_image_with_paddle_doc_parser(self, image_path: str) -> List[Dict]:
        max_side_px = self._resolve_paddle_doc_max_side_px()
        predict_image_path, scale_x, scale_y, temp_image_path = (
            self._prepare_paddle_doc_predict_image(image_path)
        )
        predict_kwargs: dict[str, Any] = {}
        predict_trace: dict[str, Any] | None = None
        predict_max_pixels = _derive_paddle_doc_predict_max_pixels(
            max_side_px=max_side_px,
            did_downscale=temp_image_path is not None,
        )
        if predict_max_pixels is not None:
            predict_kwargs["max_pixels"] = int(predict_max_pixels)
            logger.info(
                "Constraining PaddleOCR-VL doc_parser predict max_pixels=%s (max_side=%s, downscaled=%s)",
                predict_max_pixels,
                max_side_px,
                temp_image_path is not None,
            )

        def _predict_once() -> Any:
            parser_local = self._get_paddle_doc_parser()
            try:
                return parser_local.predict(input=predict_image_path, **predict_kwargs)
            except TypeError:
                try:
                    return parser_local.predict(predict_image_path, **predict_kwargs)
                except TypeError:
                    try:
                        return parser_local.predict(input=predict_image_path)
                    except TypeError:
                        return parser_local.predict(predict_image_path)

        try:
            try:
                predict_timeout_s = self._resolve_paddle_doc_predict_timeout_s()
                predict_trace = self._begin_paddle_doc_predict_trace(
                    image_path=str(image_path),
                    predict_image_path=str(predict_image_path),
                    predict_kwargs=predict_kwargs,
                    timeout_s=predict_timeout_s,
                    label="paddleocr-vl:predict",
                    max_side_px=max_side_px,
                    scale_x=scale_x,
                    scale_y=scale_y,
                )
                output = self._run_paddle_doc_predict_with_timeout(
                    _predict_once,
                    timeout_s=predict_timeout_s,
                    label="paddleocr-vl:predict",
                )
            except Exception as first_error:
                wants_v15 = (
                    str(self.model or "").strip().lower()
                    == _PADDLE_OCR_VL_MODEL_V15.lower()
                )
                can_downgrade = bool(self.allow_model_downgrade)
                error_to_raise: Exception | None = first_error
                first_trace_debug = self._finalize_paddle_doc_predict_trace(
                    predict_trace,
                    status="timeout"
                    if isinstance(first_error, TimeoutError)
                    else "error",
                    error=first_error,
                )
                if isinstance(first_error, TimeoutError):
                    self._log_paddle_doc_timeout_trace(
                        first_trace_debug,
                        timeout_s=predict_timeout_s,
                    )
                if (
                    isinstance(first_error, TimeoutError)
                    and wants_v15
                    and self._should_retry_paddle_doc_timeout()
                ):
                    retry_timeout_s = self._resolve_paddle_doc_retry_timeout_s(
                        predict_timeout_s=predict_timeout_s
                    )
                    logger.warning(
                        "PaddleOCR-VL-1.5 predict timed out after %.0fs; retrying once with a fresh parser (retry_timeout=%.0fs)",
                        predict_timeout_s,
                        retry_timeout_s,
                    )
                    self._paddle_doc_parser = None
                    self._paddle_doc_parser_disabled = False
                    retry_trace = self._begin_paddle_doc_predict_trace(
                        image_path=str(image_path),
                        predict_image_path=str(predict_image_path),
                        predict_kwargs=predict_kwargs,
                        timeout_s=retry_timeout_s,
                        label="paddleocr-vl:predict:retry",
                        max_side_px=max_side_px,
                        scale_x=scale_x,
                        scale_y=scale_y,
                    )
                    try:
                        output = self._run_paddle_doc_predict_with_timeout(
                            _predict_once,
                            timeout_s=retry_timeout_s,
                            label="paddleocr-vl:predict:retry",
                        )
                        predict_trace = retry_trace
                        error_to_raise = None
                    except Exception as retry_error:
                        retry_trace_debug = self._finalize_paddle_doc_predict_trace(
                            retry_trace,
                            status="timeout"
                            if isinstance(retry_error, TimeoutError)
                            else "error",
                            error=retry_error,
                        )
                        if isinstance(retry_error, TimeoutError):
                            self._log_paddle_doc_timeout_trace(
                                retry_trace_debug,
                                timeout_s=retry_timeout_s,
                            )
                        error_to_raise = retry_error
                if error_to_raise is not None and isinstance(
                    error_to_raise, TimeoutError
                ):
                    self._paddle_doc_parser_disabled = True
                if (
                    wants_v15
                    and can_downgrade
                    and error_to_raise is not None
                    and _is_probably_model_unsupported_error(error_to_raise)
                ):
                    logger.warning(
                        "PaddleOCR-VL-1.5 request failed and downgrade is allowed; retrying with %s",
                        _PADDLE_OCR_VL_MODEL_V1,
                    )
                    self._paddle_doc_parser = None
                    self._paddle_doc_effective_model = _PADDLE_OCR_VL_MODEL_V1
                    self._paddle_doc_pipeline_version = "v1"
                    self._paddle_doc_server_url = None
                    self._paddle_doc_backend = None
                    original_model = self.model
                    try:
                        self.model = _PADDLE_OCR_VL_MODEL_V1
                        output = _run_in_daemon_thread_with_timeout(
                            _predict_once,
                            timeout_s=predict_timeout_s,
                            label="paddleocr-vl:predict",
                        )
                    except Exception:
                        self.model = original_model
                        raise error_to_raise
                else:
                    if (
                        wants_v15
                        and (not can_downgrade)
                        and error_to_raise is not None
                        and _is_probably_model_unsupported_error(error_to_raise)
                    ):
                        raise RuntimeError(
                            "PaddleOCR-VL-1.5 is not available on current endpoint and strict mode forbids downgrade; "
                            "switch to PaddlePaddle/PaddleOCR-VL or disable strict mode explicitly."
                        ) from error_to_raise
                    if error_to_raise is not None:
                        raise error_to_raise

            try:
                raw_elements, image_regions, layout_blocks = (
                    _extract_paddle_doc_parser_output(output)
                )
                raw_elements, image_regions, layout_blocks = (
                    _scale_paddle_doc_parser_output(
                        raw_elements,
                        image_regions,
                        layout_blocks,
                        scale_x=scale_x,
                        scale_y=scale_y,
                    )
                )
                self.last_layout_blocks = list(layout_blocks)
                self.last_image_regions_px = [
                    _clone_image_region_payload(region) for region in image_regions
                ]
                self._last_layout_image_path = str(image_path)
                self._image_region_cache_path = str(image_path)
                self._image_region_cache_ready = True

                if not raw_elements:
                    logger.warning(
                        "PaddleOCR-VL doc_parser produced no usable text blocks "
                        "(provider=%s, requested_model=%s, effective_model=%s, pipeline_version=%s)",
                        self.provider_id,
                        self.model,
                        self._paddle_doc_effective_model or self.model,
                        self._paddle_doc_pipeline_version or "<default>",
                    )
                    raise RuntimeError(
                        "PaddleOCR-VL doc_parser returned no valid text blocks in parsing_res_list"
                    )
            except Exception as parse_error:
                self._finalize_paddle_doc_predict_trace(
                    predict_trace,
                    status="error",
                    error=parse_error,
                )
                raise

            self._finalize_paddle_doc_predict_trace(
                predict_trace,
                status="success",
                raw_element_count=len(raw_elements),
                image_region_count=len(self.last_image_regions_px),
                layout_block_count=len(self.last_layout_blocks),
            )
            logger.info(
                "PaddleOCR-VL doc_parser parsed %s text blocks and %s image-like regions",
                len(raw_elements),
                len(self.last_image_regions_px),
            )
            return raw_elements
        finally:
            if temp_image_path is not None:
                try:
                    temp_image_path.unlink(missing_ok=True)
                except Exception:
                    pass

