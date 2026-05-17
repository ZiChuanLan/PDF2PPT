"""AI OCR client and text refinement utilities.

This module is now a thin orchestrator.  Implementation methods have
been moved to mixin classes in sub-modules prefixed with ``_``.
"""

import os
import threading
import time
from typing import Any, Dict, List

from .base import (
    _DEFAULT_PADDLE_OCR_VL_MODEL,
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
    OcrProvider,
)
from .deepseek_parser import (
    _extract_deepseek_tagged_items,
    _is_deepseek_ocr_model,
    _looks_like_ocr_prompt_echo_text,
)
from .prompts import (
    build_ai_ocr_direct_prompt,
    build_ai_ocr_image_region_prompt,
    build_ai_ocr_layout_block_prompt,
    normalize_ai_ocr_prompt_override,
    normalize_ai_ocr_prompt_preset,
    resolve_ai_ocr_prompt_preset,
)
from .json_extraction import (
    _extract_json_list,
    _extract_message_text,
    _extract_partial_json_object_list,
)
from .result_parsing import (
    _derive_paddle_doc_predict_max_pixels,
    _extract_deepseek_image_regions,
    _extract_image_regions_json,
    _is_image_like_layout_label,
    _is_ocr_eligible_image_like_label,
    _normalize_layout_label,
    _extract_paddle_doc_parser_output,
    _normalize_bbox_px,
    _scale_paddle_doc_parser_output,
)
from .routing import (
    ROUTE_KIND_LOCAL_LAYOUT_BLOCK_OCR,
    ROUTE_KIND_REMOTE_DOC_PARSER,
    ROUTE_KIND_REMOTE_PROMPT_OCR,
    normalize_ocr_route_kind,
)
from .utils import (
    _coerce_bbox_xyxy,
    _is_paddleocr_vl_model,
    _looks_like_structural_gibberish,
)
from .vendors import (
    VendorTuningConfig,
    _create_ai_ocr_vendor_adapter,
    _normalize_ai_ocr_model_name,
    _should_send_image_first_for_ai_ocr,
    get_vendor_tuning,
)

# --- Sub-module imports ---
from ._ai_helpers import (
    _PADDLE_DOC_MAX_SIDE_PX,
    _clone_image_region_payload,
    _coerce_int_in_range,
    _compact_debug_text,
    _env_int,
    _normalize_ai_layout_model_name,
    _resolve_paddlex_layout_model_name,
)
from ._ai_rate_limiter import _get_shared_ai_request_limiter
from ._ai_paddle_doc import _PaddleDocMixin
from ._ai_layout_block import _LayoutBlockMixin
from ._ai_chat import _AiChatMixin
from ._ai_text_refiner import AiOcrTextRefiner, _is_multiline_candidate_for_linebreak_assist


class AiOcrClient(_PaddleDocMixin, _LayoutBlockMixin, _AiChatMixin, OcrProvider):
    """AI OCR using OpenAI-compatible vision models.

    Implementation methods are split across mixin classes:
    - _PaddleDocMixin: PaddleOCR-VL doc_parser pipeline
    - _LayoutBlockMixin: Local layout-block crop OCR
    - _AiChatMixin: Direct AI chat completion OCR
    """

    _local_layout_model_lock = threading.Lock()
    _local_layout_predict_lock = threading.Lock()
    _local_layout_model: Any | None = None
    _local_layout_model_name: str | None = None

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None = None,
        model: str | None = None,
        provider: str | None = None,
        layout_model: str | None = None,
        paddle_doc_max_side_px: int | None = None,
        layout_block_max_concurrency: int | None = None,
        request_rpm_limit: int | None = None,
        request_tpm_limit: int | None = None,
        request_max_retries: int | None = None,
        route_kind: str | None = None,
        prompt_preset: str | None = None,
        direct_prompt_override: str | None = None,
        layout_block_prompt_override: str | None = None,
        image_region_prompt_override: str | None = None,
    ):
        import openai

        if not api_key:
            raise ValueError("AI OCR api_key is required")

        self.api_key = str(api_key).strip()
        self._paddle_doc_parser: Any | None = None
        self._paddle_doc_parser_disabled: bool = False
        self._paddle_doc_effective_model: str | None = None
        self._paddle_doc_pipeline_version: str | None = None
        self._paddle_doc_server_url: str | None = None
        self._paddle_doc_backend: str | None = None
        self.last_image_regions_px: list[Any] = []
        self.last_layout_blocks: list[dict[str, Any]] = []
        self._last_layout_image_path: str | None = None
        self._image_region_cache_path: str | None = None
        self._image_region_cache_ready: bool = False
        self._paddle_doc_trace_lock = threading.Lock()
        self._paddle_doc_trace_serial: int = 0
        self._paddle_doc_active_predict_trace: dict[str, Any] | None = None
        self._paddle_doc_last_predict_debug: dict[str, Any] | None = None
        self._paddle_doc_recent_predict_debug: list[dict[str, Any]] = []
        self.last_layout_analysis_debug: dict[str, Any] | None = None

        self.vendor_adapter = _create_ai_ocr_vendor_adapter(
            provider=provider,
            base_url=base_url,
        )
        resolved_base_url = self.vendor_adapter.resolve_base_url(base_url)
        client_kwargs: dict[str, Any] = {"api_key": api_key}
        if resolved_base_url:
            client_kwargs["base_url"] = resolved_base_url
        self.client = openai.OpenAI(**client_kwargs)
        resolved_model = self.vendor_adapter.resolve_model(model)
        self.model = (
            _normalize_ai_ocr_model_name(
                resolved_model,
                provider_id=self.vendor_adapter.provider_id,
            )
            or resolved_model
        )
        self.provider_id = self.vendor_adapter.provider_id
        self.base_url = resolved_base_url
        self.layout_model = _normalize_ai_layout_model_name(layout_model)
        self.requested_route_kind = normalize_ocr_route_kind(
            route_kind,
            default="auto",
        )
        self.prompt_preset = normalize_ai_ocr_prompt_preset(prompt_preset)
        self.direct_prompt_override = normalize_ai_ocr_prompt_override(
            direct_prompt_override
        )
        self.layout_block_prompt_override = normalize_ai_ocr_prompt_override(
            layout_block_prompt_override
        )
        self.image_region_prompt_override = normalize_ai_ocr_prompt_override(
            image_region_prompt_override
        )
        self.route_kind = ROUTE_KIND_REMOTE_PROMPT_OCR
        self.allow_model_downgrade: bool = _env_flag(
            "OCR_PADDLE_ALLOW_MODEL_DOWNGRADE",
            default=False,
        )
        self.allow_paddle_prompt_fallback: bool = _env_flag(
            "OCR_PADDLE_VL_ALLOW_PROMPT_FALLBACK",
            default=False,
        )
        self._paddle_doc_max_side_px_override: int | None = None
        if paddle_doc_max_side_px is not None:
            try:
                normalized_max_side = int(paddle_doc_max_side_px)
            except Exception:
                normalized_max_side = None
            if normalized_max_side is not None:
                self._paddle_doc_max_side_px_override = max(
                    0, min(_PADDLE_DOC_MAX_SIDE_PX, int(normalized_max_side))
                )
        self._layout_block_max_concurrency_override = _coerce_int_in_range(
            layout_block_max_concurrency,
            low=1,
            high=8,
            default=None,
        )
        self.request_rpm_limit = _coerce_int_in_range(
            request_rpm_limit,
            low=1,
            high=2000,
            default=None,
        )
        self.request_tpm_limit = _coerce_int_in_range(
            request_tpm_limit,
            low=1,
            high=2_000_000,
            default=None,
        )
        self.request_max_retries = int(
            _coerce_int_in_range(
                request_max_retries,
                low=0,
                high=8,
                default=0,
            )
            or 0
        )
        self._request_limiter = _get_shared_ai_request_limiter(
            api_key=self.api_key,
            provider_id=self.provider_id,
            base_url=self.base_url,
            model=self.model,
            requests_per_minute=self.request_rpm_limit,
            tokens_per_minute=self.request_tpm_limit,
        )

        if (
            self.requested_route_kind == ROUTE_KIND_REMOTE_DOC_PARSER
            and not _is_paddleocr_vl_model(self.model)
        ):
            raise ValueError("remote_doc_parser route requires a PaddleOCR-VL model")

        if (
            _is_paddleocr_vl_model(self.model)
            and self.requested_route_kind == ROUTE_KIND_REMOTE_PROMPT_OCR
        ):
            raise ValueError(
                "PaddleOCR-VL does not support the direct OCR chain. "
                "Choose `内置文档解析（PaddleOCR-VL）` / `doc_parser` instead."
            )

        if (
            _is_paddleocr_vl_model(self.model)
            and self.requested_route_kind != ROUTE_KIND_LOCAL_LAYOUT_BLOCK_OCR
        ):
            should_use_doc_parser = self._should_use_paddle_doc_parser()
            if not should_use_doc_parser and not self.allow_paddle_prompt_fallback:
                reason = self._describe_paddle_doc_parser_unavailable_reason()
                raise ValueError(
                    "Selected PaddleOCR-VL model cannot use the current OCR chain. "
                    f"Reason: {reason}. "
                    "Choose `内置文档解析（PaddleOCR-VL）` / `doc_parser`, "
                    "or set OCR_PADDLE_VL_ALLOW_PROMPT_FALLBACK=1 to force prompt mode explicitly."
                )
            if should_use_doc_parser:
                if not _clean_str(self.base_url):
                    raise ValueError(
                        "PaddleOCR-VL requires base_url (for example https://api.siliconflow.cn/v1)"
                    )
                try:
                    import paddleocr as _  # noqa: F401
                except Exception as e:
                    raise ValueError(
                        "PaddleOCR-VL requires `paddleocr` package. Install with: pip install paddleocr"
                    ) from e
        self._refresh_route_kind()


__all__ = [
    "AiOcrClient",
    "AiOcrTextRefiner",
    "_is_multiline_candidate_for_linebreak_assist",
]
