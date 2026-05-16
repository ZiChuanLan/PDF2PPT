"""AI chat completion OCR methods for AiOcrClient (mixin)."""

import base64
import io
import json
import logging
import math
import os
from pathlib import Path
from typing import Any, Dict, List

from PIL import Image

from .base import _clean_str, _env_flag, _env_float
from .deepseek_parser import _extract_deepseek_tagged_items, _is_deepseek_ocr_model, _looks_like_ocr_prompt_echo_text
from .json_extraction import _extract_json_list, _extract_message_text, _extract_partial_json_object_list
from .prompts import build_ai_ocr_direct_prompt, build_ai_ocr_image_region_prompt, normalize_ai_ocr_prompt_override, normalize_ai_ocr_prompt_preset, resolve_ai_ocr_prompt_preset
from .result_parsing import _extract_deepseek_image_regions, _extract_image_regions_json, _normalize_bbox_px
from .routing import ROUTE_KIND_LOCAL_LAYOUT_BLOCK_OCR, ROUTE_KIND_REMOTE_DOC_PARSER, ROUTE_KIND_REMOTE_PROMPT_OCR
from .utils import _coerce_bbox_xyxy, _is_paddleocr_vl_model, _looks_like_structural_gibberish
from .vendors import _should_send_image_first_for_ai_ocr, get_vendor_tuning
from ._ai_helpers import (
    _clone_image_region_payload,
    _compact_debug_text,
    _env_int,
    _run_chat_completion_request,
    _sanitize_debug_value,
)
from ..llm_adapter import _validate_image_regions_px

logger = logging.getLogger(__name__)


class _AiChatMixin:
    """Mixin providing AI chat completion OCR methods for AiOcrClient."""

    def _detect_image_regions_with_prompt(self, image_path: str) -> list[list[float]]:
        from ..llm_adapter import _validate_image_regions_px

        image = Image.open(image_path).convert("RGB")
        width, height = image.size
        if width <= 0 or height <= 0:
            return []

        import base64
        import io

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        data_uri = f"data:image/png;base64,{b64}"

        effective_model = str(self.model)
        is_deepseek_model = _is_deepseek_ocr_model(effective_model)
        request_timeout_s = max(
            8.0,
            _env_float("OCR_AI_IMAGE_REGION_TIMEOUT_S", 30.0),
        )
        max_tokens_image_regions = self.vendor_adapter.clamp_max_tokens(
            1024, kind="ocr"
        )
        resolved_prompt_preset = resolve_ai_ocr_prompt_preset(
            preset=self.prompt_preset,
            model_name=effective_model,
            provider_id=self.provider_id,
        )
        prompt = build_ai_ocr_image_region_prompt(
            preset=resolved_prompt_preset,
            image_width=int(width),
            image_height=int(height),
            override=self.image_region_prompt_override,
        )

        user_content = self.vendor_adapter.build_user_content(
            prompt=prompt,
            image_data_uri=data_uri,
            image_first=_should_send_image_first_for_ai_ocr(
                provider_id=self.provider_id,
                model_name=effective_model,
            ),
        )
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": "Return JSON array only, no markdown.",
            },
            {
                "role": "user",
                "content": user_content,
            },
        ]
        if is_deepseek_model:
            messages = [
                {
                    "role": "user",
                    "content": user_content,
                }
            ]

        completion = self._chat_completion(
            model=effective_model,
            timeout_s=request_timeout_s,
            request_label="image_region_detection",
            temperature=0,
            max_tokens=max_tokens_image_regions,
            messages=messages,
        )
        content_obj = (
            completion.choices[0].message.content
            if getattr(completion, "choices", None)
            else ""
        )
        content = _extract_message_text(content_obj)
        region_items = _extract_image_regions_json(content)
        if not region_items and (is_deepseek_model or "<|det|>" in (content or "")):
            region_items = _extract_deepseek_image_regions(content)
        if not region_items and (is_deepseek_model or "<|det|>" in (content or "")):
            tagged_items = _extract_deepseek_tagged_items(content)
            if tagged_items:
                region_items = []
                for item in tagged_items:
                    bbox = _coerce_bbox_xyxy(item.get("bbox"))
                    if bbox is None:
                        continue
                    region_items.append(
                        [float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])]
                    )

        if region_items:
            normalized_candidates = [
                {
                    "text": "image_region",
                    "bbox": list(region),
                    "confidence": 1.0,
                }
                for region in region_items
                if isinstance(region, list) and len(region) == 4
            ]
            normalized_items, _ = self._normalize_items_to_pixels(
                normalized_candidates,
                image=image,
            )
            normalized_regions = [
                list(bbox)
                for bbox in (
                    item.get("bbox") if isinstance(item, dict) else None
                    for item in normalized_items
                )
                if isinstance(bbox, list) and len(bbox) == 4
            ]
            if normalized_regions:
                region_items = normalized_regions

        validated = _validate_image_regions_px(
            region_items or [],
            width_px=int(width),
            height_px=int(height),
            max_regions=12,
        )
        return validated or []

    def detect_image_regions(self, image_path: str) -> list[Any]:
        requested_path = str(image_path)
        if (
            self._image_region_cache_ready
            and str(self._image_region_cache_path or "") == requested_path
        ):
            return [
                _clone_image_region_payload(region)
                for region in self.last_image_regions_px
            ]

        self.last_image_regions_px = []
        self.last_layout_blocks = []
        self._last_layout_image_path = requested_path
        self._image_region_cache_path = requested_path
        self._image_region_cache_ready = False

        if self._uses_local_layout_block_ocr():
            try:
                _, image_regions = self._run_local_layout_analysis(image_path)
                self._refresh_route_kind()
                return [_clone_image_region_payload(region) for region in image_regions]
            except Exception as e:
                logger.warning(
                    "Local layout_block image-region extraction failed; falling back to prompt detection: %s",
                    e,
                )

        if self._uses_remote_doc_parser():
            try:
                self._ocr_image_with_paddle_doc_parser(image_path)
                self._refresh_route_kind()
                return [
                    _clone_image_region_payload(region)
                    for region in self.last_image_regions_px
                ]
            except Exception as e:
                logger.warning(
                    "PaddleOCR-VL image-region extraction failed; falling back to prompt detection: %s",
                    e,
                )

        try:
            self.last_image_regions_px = [
                _clone_image_region_payload(region)
                for region in self._detect_image_regions_with_prompt(image_path)
            ]
            self._refresh_route_kind()
        except Exception as e:
            logger.warning("AI OCR image-region detection failed: %s", e)
            self.last_image_regions_px = []

        self._image_region_cache_ready = True
        return [
            _clone_image_region_payload(region) for region in self.last_image_regions_px
        ]

    def _score_bbox_transform(
        self,
        *,
        image: Image.Image,
        gray: Image.Image,
        items: list[dict],
        base: float | tuple[float, float] | None,
        max_items: int = 60,
    ) -> tuple[float, dict]:
        """Score candidate bbox coordinate systems.

        Some vision models return bounding boxes in a *normalized* coordinate
        grid (often around 0..1000/1024) regardless of the actual image size.
        We evaluate a few plausible transforms and pick the best one.
        """

        width, height = image.size
        if width <= 0 or height <= 0 or not items:
            return (float("-inf"), {"reason": "empty"})

        if base is None:
            sx = 1.0
            sy = 1.0
            base_name = "identity"
        elif isinstance(base, tuple):
            try:
                base_x = float(base[0])
                base_y = float(base[1])
            except Exception:
                return (float("-inf"), {"reason": "invalid_base_xy"})
            if base_x <= 0 or base_y <= 0:
                return (float("-inf"), {"reason": "invalid_base_xy"})
            sx = float(width) / float(base_x)
            sy = float(height) / float(base_y)
            base_name = f"{int(round(base_x))}x{int(round(base_y))}"
        else:
            b = float(base)
            if b <= 0:
                return (float("-inf"), {"reason": "invalid_base"})
            sx = float(width) / b
            sy = float(height) / b
            base_name = str(int(b)) if b.is_integer() else str(b)

        # Take a stable subset (first N) to keep scoring fast on dense pages.
        subset = items[: max(1, min(len(items), int(max_items)))]

        x0s: list[float] = []
        x1s: list[float] = []
        y0s: list[float] = []
        y1s: list[float] = []
        stds: list[float] = []
        out_of_bounds = 0
        valid = 0

        for it in subset:
            bbox = it.get("bbox")
            if not isinstance(bbox, list) or len(bbox) != 4:
                continue
            try:
                x0, y0, x1, y1 = (
                    float(bbox[0]) * sx,
                    float(bbox[1]) * sy,
                    float(bbox[2]) * sx,
                    float(bbox[3]) * sy,
                )
            except Exception:
                continue
            if math.isnan(x0) or math.isnan(y0) or math.isnan(x1) or math.isnan(y1):
                continue
            x0, x1 = (min(x0, x1), max(x0, x1))
            y0, y1 = (min(y0, y1), max(y0, y1))
            if x1 <= x0 or y1 <= y0:
                continue

            # Count OOB based on unclamped coords.
            if x0 < 0 or y0 < 0 or x1 > width or y1 > height:
                out_of_bounds += 1

            # Clamp for sampling.
            x0c = max(0, min(width - 1, int(round(x0))))
            y0c = max(0, min(height - 1, int(round(y0))))
            x1c = max(0, min(width, int(round(x1))))
            y1c = max(0, min(height, int(round(y1))))
            if x1c <= x0c or y1c <= y0c:
                continue

            x0s.append(float(x0c))
            x1s.append(float(x1c))
            y0s.append(float(y0c))
            y1s.append(float(y1c))
            valid += 1

            # Pixel-variance proxy: real text regions tend to have higher
            # local variance than blank/background regions.
            crop = gray.crop((x0c, y0c, x1c, y1c))
            if crop.width <= 0 or crop.height <= 0:
                continue
            target_w = max(8, min(64, crop.width // 8))
            target_h = max(8, min(64, crop.height // 8))
            small = crop.resize((target_w, target_h))
            pixels = list(small.getdata())  # type: ignore[arg-type]
            if not pixels:
                continue
            mean = sum(pixels) / len(pixels)
            var = sum((p - mean) ** 2 for p in pixels) / len(pixels)
            stds.append(float(var**0.5))

        if valid <= 0:
            return (float("-inf"), {"base": base_name, "reason": "no_valid_boxes"})

        def _percentile(sorted_vals: list[float], p: float) -> float:
            if not sorted_vals:
                return 0.0
            p = max(0.0, min(1.0, float(p)))
            idx = int(round((len(sorted_vals) - 1) * p))
            return sorted_vals[idx]

        x0s_s = sorted(x0s)
        x1s_s = sorted(x1s)
        y0s_s = sorted(y0s)
        y1s_s = sorted(y1s)

        x_span = (_percentile(x1s_s, 0.95) - _percentile(x0s_s, 0.05)) / float(width)
        y_span = (_percentile(y1s_s, 0.95) - _percentile(y0s_s, 0.05)) / float(height)
        coverage_score = max(0.0, min(1.0, x_span)) + max(0.0, min(1.0, y_span))  # 0..2

        median_std = sorted(stds)[len(stds) // 2] if stds else 0.0
        out_rate = float(out_of_bounds) / float(valid)

        # Weighted score: prioritize good coverage (boxes span the page) then
        # variance, penalize out-of-bounds.
        score = (1.6 * coverage_score) + (median_std / 32.0) - (2.0 * out_rate)
        details = {
            "base": base_name,
            "sx": sx,
            "sy": sy,
            "valid": valid,
            "median_std": median_std,
            "coverage_x": x_span,
            "coverage_y": y_span,
            "out_rate": out_rate,
        }
        return (float(score), details)

    def _normalize_items_to_pixels(
        self,
        items: list[dict],
        *,
        image: Image.Image,
    ) -> tuple[list[dict], dict]:
        """Return (items_px, debug) after auto-normalizing bbox coords to pixels."""

        width, height = image.size
        if width <= 0 or height <= 0 or not items:
            return (items, {"chosen": "none", "reason": "empty"})

        gray = image.convert("L")

        # Evaluate common coordinate grids + identity. Some gateways also return
        # bbox coordinates in the *resized* model-input pixel space (e.g. long
        # side normalized to 1024 while keeping aspect ratio). In that case the
        # X/Y bases differ; we add a few aspect-preserving candidates.
        uniform_candidates: list[float | None] = [
            None,
            1.0,
            100.0,
            1000.0,
            1024.0,
            2048.0,
            4096.0,
        ]

        def _resize_dims_for_target_side(
            target_side: float, *, mode: str
        ) -> tuple[float, float] | None:
            try:
                target = float(target_side)
            except Exception:
                return None
            if target <= 0:
                return None
            if mode == "short":
                denom = float(min(width, height))
            else:
                denom = float(max(width, height))
            if denom <= 0:
                return None
            scale = float(target) / denom
            if scale <= 0:
                return None
            bw = max(1.0, float(round(float(width) * scale)))
            bh = max(1.0, float(round(float(height) * scale)))
            if bw <= 0 or bh <= 0:
                return None
            return (bw, bh)

        seen: set[str] = set()
        candidates: list[float | tuple[float, float] | None] = []

        def _add_candidate(value: float | tuple[float, float] | None) -> None:
            if value is None:
                key = "identity"
            elif isinstance(value, tuple):
                key = f"xy:{int(round(float(value[0])))}x{int(round(float(value[1])))}"
            else:
                key = f"u:{float(value):.3f}"
            if key in seen:
                return
            seen.add(key)
            candidates.append(value)

        for base in uniform_candidates:
            _add_candidate(base)

        for side in (1000.0, 1024.0, 1536.0, 2048.0):
            cand = _resize_dims_for_target_side(side, mode="long")
            if cand is not None:
                _add_candidate(cand)

        for side in (1000.0, 1024.0):
            cand = _resize_dims_for_target_side(side, mode="short")
            if cand is not None:
                _add_candidate(cand)

        scored: list[tuple[float, float | tuple[float, float] | None, dict]] = []
        for base in candidates:
            score, details = self._score_bbox_transform(
                image=image, gray=gray, items=items, base=base
            )
            scored.append((score, base, details))

        scored.sort(key=lambda t: t[0], reverse=True)
        best_score, best_base, best_details = scored[0]

        # Apply best transform.
        if best_base is None:
            sx = 1.0
            sy = 1.0
        elif isinstance(best_base, tuple):
            bx, by = best_base
            bx = float(bx)
            by = float(by)
            sx = float(width) / float(max(1.0, bx))
            sy = float(height) / float(max(1.0, by))
        else:
            sx = float(width) / float(best_base)
            sy = float(height) / float(best_base)

        out: list[dict] = []
        for it in items:
            bbox = it.get("bbox")
            if not isinstance(bbox, list) or len(bbox) != 4:
                continue
            try:
                x0, y0, x1, y1 = (
                    float(bbox[0]) * sx,
                    float(bbox[1]) * sy,
                    float(bbox[2]) * sx,
                    float(bbox[3]) * sy,
                )
            except Exception:
                continue
            if math.isnan(x0) or math.isnan(y0) or math.isnan(x1) or math.isnan(y1):
                continue
            x0, x1 = (min(x0, x1), max(x0, x1))
            y0, y1 = (min(y0, y1), max(y0, y1))
            if x1 <= x0 or y1 <= y0:
                continue
            # Clamp to image bounds.
            x0 = max(0.0, min(x0, float(width - 1)))
            y0 = max(0.0, min(y0, float(height - 1)))
            x1 = max(0.0, min(x1, float(width)))
            y1 = max(0.0, min(y1, float(height)))
            if x1 <= x0 or y1 <= y0:
                continue
            new_it = dict(it)
            new_it["bbox"] = [x0, y0, x1, y1]
            out.append(new_it)

        debug = {
            "chosen_base": best_details.get("base"),
            "chosen_score": best_score,
            "chosen_details": best_details,
            "candidates": [d for _, _, d in scored[:3]],
        }
        return (out, debug)

    def _resolve_model_request_timeout_s(self, *, model_name: str | None) -> float:
        default_timeout = max(8.0, _env_float("OCR_AI_REQUEST_TIMEOUT_S", 25.0))
        lowered = str(model_name or "").strip().lower()
        provider_id = str(self.provider_id or "").strip().lower()
        if not lowered:
            return default_timeout

        if "qwen" in lowered and ("vl" in lowered or "omni" in lowered):
            return max(
                8.0,
                _env_float("OCR_AI_REQUEST_TIMEOUT_S_QWEN", default_timeout),
            )

        if "deepseek-ocr" in lowered or "deepseekocr" in lowered:
            tuning = get_vendor_tuning(self.provider_id)
            if tuning.predict_timeout_override is not None:
                vendor_default = max(default_timeout, tuning.predict_timeout_override)
                return max(
                    8.0,
                    _env_float("OCR_AI_REQUEST_TIMEOUT_S_DEEPSEEK_OCR", vendor_default),
                )
            return max(
                8.0,
                _env_float("OCR_AI_REQUEST_TIMEOUT_S_DEEPSEEK_OCR", default_timeout),
            )

        if "paddleocr-vl" in lowered:
            return max(
                8.0,
                _env_float("OCR_AI_REQUEST_TIMEOUT_S_PADDLE_VL", default_timeout),
            )

        return default_timeout

    def _chat_completion(
        self,
        *,
        model: str,
        timeout_s: float,
        messages: Any,
        max_tokens: int,
        request_label: str,
        **kwargs: Any,
    ) -> Any:
        return _run_chat_completion_request(
            client=self.client,
            provider_id=self.provider_id,
            model=model,
            timeout_s=timeout_s,
            max_retries=self.request_max_retries,
            request_limiter=self._request_limiter,
            request_label=request_label,
            logger_obj=logger,
            messages=messages,
            max_tokens=max_tokens,
            **kwargs,
        )

    def ocr_image(self, image_path: str) -> List[Dict]:
        self.last_image_regions_px = []
        self.last_layout_blocks = []
        self._last_layout_image_path = str(image_path)
        self._image_region_cache_path = None
        self._image_region_cache_ready = False
        image = Image.open(image_path).convert("RGB")
        width, height = image.size
        if width <= 0 or height <= 0:
            return []

        if self._uses_local_layout_block_ocr():
            bypass_reason = None
            is_deepseek_layout_block = _is_deepseek_ocr_model(self.model)
            # Check bypass for ALL models: low coverage (screenshots),
            # wide_flat layout, etc.
            bypass_reason = self._should_bypass_local_layout_block_ocr(
                image_path=image_path,
                image=image,
            )
            if is_deepseek_layout_block and not bypass_reason:
                # DeepSeek-OCR performs reliably on the full page in our
                # real pipeline tests, while local block crops frequently
                # return empty text and then time out on the fallback pass.
                bypass_reason = "deepseek_model_prefers_direct_page_ocr"
            if bypass_reason:
                layout_debug = (
                    dict(self.last_layout_analysis_debug)
                    if isinstance(self.last_layout_analysis_debug, dict)
                    else {}
                )
                self.last_layout_analysis_debug = {
                    **layout_debug,
                    "layout_block_bypass_reason": bypass_reason,
                }
                logger.info(
                    "Bypassing local layout_block crop OCR and using direct page OCR"
                    " (provider=%s, model=%s, image=%s, reason=%s)",
                    self.provider_id,
                    self.model,
                    Path(image_path).name,
                    bypass_reason,
                )
            else:
                try:
                    result = self._ocr_image_with_local_layout_blocks(
                        image_path,
                        image=image,
                    )
                except Exception as exc:
                    if not is_deepseek_layout_block:
                        raise
                    logger.warning(
                        "Local layout_block OCR failed; falling back to direct page OCR"
                        " (provider=%s, model=%s, image=%s, error=%s)",
                        self.provider_id,
                        self.model,
                        Path(image_path).name,
                        exc,
                    )
                else:
                    if result:
                        # Post-OCR quality validation: check if results are
                        # suspiciously sparse (layout model missed most content).
                        validation_reason = self._validate_layout_block_ocr_results(
                            result, image
                        )
                        if validation_reason:
                            logger.warning(
                                "Layout-block OCR results suspicious (%s); "
                                "falling back to direct page OCR"
                                " (provider=%s, model=%s, image=%s, blocks=%d, chars=%d)",
                                validation_reason,
                                self.provider_id,
                                self.model,
                                Path(image_path).name,
                                len(result),
                                sum(len(r.get("text", "")) for r in result),
                            )
                            # Store the suspicious result for debugging
                            layout_debug = (
                                dict(self.last_layout_analysis_debug)
                                if isinstance(self.last_layout_analysis_debug, dict)
                                else {}
                            )
                            self.last_layout_analysis_debug = {
                                **layout_debug,
                                "post_ocr_validation": validation_reason,
                                "post_ocr_chars": sum(
                                    len(r.get("text", "")) for r in result
                                ),
                            }
                            # Fall through to direct page OCR
                        else:
                            self._refresh_route_kind()
                            return result
                    if not is_deepseek_layout_block:
                        self._refresh_route_kind()
                        return result
                    logger.warning(
                        "Local layout_block OCR returned no usable text; falling back to direct page OCR"
                        " (provider=%s, model=%s, image=%s)",
                        self.provider_id,
                        self.model,
                        Path(image_path).name,
                    )

        is_paddle_model = _is_paddleocr_vl_model(self.model)
        should_use_doc_parser = self._uses_remote_doc_parser()
        if should_use_doc_parser:
            try:
                result = self._ocr_image_with_paddle_doc_parser(image_path)
                self._refresh_route_kind()
                return result
            except Exception as e:
                if not self.allow_paddle_prompt_fallback:
                    logger.error(
                        "PaddleOCR-VL doc_parser failed with strict routing enabled (provider=%s, model=%s): %s",
                        self.provider_id,
                        self.model,
                        e,
                    )
                    raise RuntimeError(
                        f"PaddleOCR-VL dedicated channel failed: {e}"
                    ) from e
                logger.warning(
                    "PaddleOCR-VL doc_parser failed; prompt fallback is explicitly enabled: %s",
                    e,
                )
                self._paddle_doc_parser_disabled = True
                self._paddle_doc_parser = None
                should_use_doc_parser = self._uses_remote_doc_parser()

        model_candidates: list[str] = [str(self.model)]
        if is_paddle_model and not should_use_doc_parser:
            if not self.allow_paddle_prompt_fallback:
                raise RuntimeError(
                    "PaddleOCR-VL dedicated channel is unavailable for current provider/base_url; "
                    "prompt fallback is disabled."
                )
            # Prompt path is opt-in for advanced users who know their gateway can
            # emit bbox JSON without Paddle doc_parser protocol.
            fallback_model = _clean_str(os.getenv("OCR_PADDLE_PROMPT_FALLBACK_MODEL"))
            if fallback_model and fallback_model.lower() != str(self.model).lower():
                model_candidates.append(fallback_model)
                logger.info(
                    "PaddleOCR-VL prompt fallback enabled; trying requested model first, then fallback model=%s",
                    fallback_model,
                )
            else:
                logger.info(
                    "PaddleOCR-VL prompt fallback enabled; trying requested model=%s",
                    self.model,
                )

        import base64
        import io

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        data_uri = f"data:image/png;base64,{b64}"

        last_error: Exception | None = None
        items: list[dict] | None = None
        max_attempts = max(1, min(5, _env_int("OCR_AI_MAX_ATTEMPTS", 3)))
        empty_response_break_after = max(
            1,
            min(3, _env_int("OCR_AI_EMPTY_RESPONSE_BREAK_AFTER", 2)),
        )
        for model_index, effective_model in enumerate(model_candidates, start=1):
            is_deepseek_model = _is_deepseek_ocr_model(effective_model)
            request_timeout_s = self._resolve_model_request_timeout_s(
                model_name=effective_model
            )

            def _make_prompt(*, item_limit: int) -> str:
                resolved_prompt_preset = resolve_ai_ocr_prompt_preset(
                    preset=self.prompt_preset,
                    model_name=effective_model,
                    provider_id=self.provider_id,
                )
                return build_ai_ocr_direct_prompt(
                    preset=resolved_prompt_preset,
                    image_width=int(width),
                    image_height=int(height),
                    item_limit=int(item_limit),
                    override=self.direct_prompt_override,
                )

            attempt_limits = [60, 40, 24, 16, 10]
            if is_deepseek_model:
                # DeepSeek grounding tags are fairly compact; allow more lines on
                # dense scanned pages while still retrying with smaller limits when
                # output truncates.
                attempt_limits = [180, 120, 90, 60, 40]
            attempt_limits = attempt_limits[:max_attempts]
            empty_response_streak = 0

            for attempt, item_limit in enumerate(attempt_limits, start=1):
                try:
                    prompt = _make_prompt(item_limit=item_limit)
                    requested_tokens = 8192
                    if is_deepseek_model:
                        # Each grounding item is short, but dense pages can easily
                        # exceed 60 lines. Allow enough output budget to avoid
                        # truncation while staying below common gateway limits.
                        requested_tokens = int(320 + int(item_limit) * 22)
                        requested_tokens = max(900, requested_tokens)
                        requested_tokens = min(3500, requested_tokens)
                    max_tokens_ocr = self.vendor_adapter.clamp_max_tokens(
                        requested_tokens, kind="ocr"
                    )
                    system_content = "Return JSON array only, no markdown."
                    if is_deepseek_model:
                        system_content = (
                            "You are an OCR engine. Output only DeepSeek grounding tags "
                            "(<|ref|>...<|/ref|><|det|>[[x0,y0,x1,y1]]<|/det|>) or JSON array with bbox."
                        )

                    user_content = self.vendor_adapter.build_user_content(
                        prompt=prompt,
                        image_data_uri=data_uri,
                        image_first=_should_send_image_first_for_ai_ocr(
                            provider_id=self.provider_id,
                            model_name=effective_model,
                        ),
                    )
                    messages: list[dict[str, Any]] = [
                        {
                            "role": "system",
                            "content": system_content,
                        },
                        {
                            "role": "user",
                            "content": user_content,
                        },
                    ]
                    if is_deepseek_model:
                        messages = [
                            {
                                "role": "user",
                                "content": user_content,
                            }
                        ]

                    completion = self._chat_completion(
                        model=effective_model,
                        timeout_s=request_timeout_s,
                        request_label="page_ocr",
                        temperature=0,
                        max_tokens=max_tokens_ocr,
                        messages=messages,
                    )

                    content_obj = (
                        completion.choices[0].message.content
                        if getattr(completion, "choices", None)
                        else ""
                    )
                    content = _extract_message_text(content_obj)
                    finish_reason = None
                    try:
                        finish_reason = completion.choices[0].finish_reason
                    except Exception:
                        finish_reason = None

                    if not (content or "").strip():
                        empty_response_streak += 1
                        logger.warning(
                            "AI OCR returned empty content (model=%s, attempt=%s/%s, finish_reason=%s)",
                            effective_model,
                            attempt,
                            len(attempt_limits),
                            finish_reason,
                        )
                        if empty_response_streak >= empty_response_break_after:
                            last_error = RuntimeError(
                                "AI OCR returned empty content repeatedly"
                            )
                            # For some gateways/models this pattern is stable;
                            # stop early so OcrManager can move to fallback
                            # providers instead of burning the whole page timeout.
                            break
                    else:
                        empty_response_streak = 0

                    if is_deepseek_model and _looks_like_structural_gibberish(content):
                        preview = (content or "")[:220].replace("\n", " ").strip()
                        logger.warning(
                            "AI OCR returned structural gibberish (model=%s, attempt=%s, chars=%s, preview=%r)",
                            effective_model,
                            attempt,
                            len(content or ""),
                            preview,
                        )
                        raise RuntimeError("AI OCR returned structural gibberish")

                    items = _extract_json_list(content)
                    if not items and (
                        is_deepseek_model or "<|det|>" in (content or "")
                    ):
                        items = _extract_deepseek_tagged_items(content)
                    if items:
                        logger.info(
                            "AI OCR parsed %s items (model=%s, attempt=%s, limit=%s, finish_reason=%s)",
                            len(items),
                            effective_model,
                            attempt,
                            item_limit,
                            finish_reason,
                        )
                        break

                    if finish_reason == "length":
                        partial_items = _extract_partial_json_object_list(content)
                        if not partial_items and (
                            is_deepseek_model or "<|det|>" in (content or "")
                        ):
                            tagged_partial = _extract_deepseek_tagged_items(content)
                            partial_items = tagged_partial or []
                        if partial_items:
                            logger.warning(
                                "AI OCR output truncated (model=%s, attempt=%s, limit=%s); recovered %s partial items.",
                                effective_model,
                                attempt,
                                item_limit,
                                len(partial_items),
                            )
                            items = partial_items
                            break
                        preview = (content or "")[:360].replace("\n", " ").strip()
                        logger.warning(
                            "AI OCR truncated with no recoverable JSON (model=%s, attempt=%s, limit=%s, chars=%s, preview=%r)",
                            effective_model,
                            attempt,
                            item_limit,
                            len(content or ""),
                            preview,
                        )
                        raise RuntimeError(
                            f"AI OCR output truncated (finish_reason=length, chars={len(content)})"
                        )

                    preview = (content or "")[:360].replace("\n", " ").strip()
                    logger.warning(
                        "AI OCR returned no parseable items (model=%s, attempt=%s, finish_reason=%s, chars=%s, preview=%r)",
                        effective_model,
                        attempt,
                        finish_reason,
                        len(content or ""),
                        preview,
                    )
                    plain_text_without_boxes = (
                        (not is_deepseek_model)
                        and bool(content and content.strip())
                        and ("{" not in (content or ""))
                        and ("[" not in (content or ""))
                        and ("<|det|>" not in (content or ""))
                    )
                    if plain_text_without_boxes:
                        # Some OCR-capable VLM endpoints return plain transcript
                        # text (without geometry) for prompt-based calls. Retries
                        # are typically useless and only consume page timeout.
                        # Fail this model fast so OcrManager can move to fallback
                        # providers (for example local PaddleOCR).
                        last_error = RuntimeError(
                            "AI OCR returned plain text without bbox/json"
                        )
                        logger.warning(
                            "AI OCR model produced plain text without geometry; skipping remaining attempts for model=%s",
                            effective_model,
                        )
                        break
                    raise RuntimeError("AI OCR returned no items")
                except Exception as e:
                    last_error = e
                    logger.warning(
                        "AI OCR attempt failed (model=%s, attempt=%s): %s",
                        effective_model,
                        attempt,
                        e,
                    )
                    continue

            if items:
                break
            if model_index < len(model_candidates):
                logger.warning(
                    "AI OCR model candidate produced no usable items: %s. Trying next model candidate.",
                    effective_model,
                )

        if not items:
            raise RuntimeError("AI OCR returned no items") from last_error

        raw_elements: List[Dict] = []
        for item in items:
            if not isinstance(item, dict):
                continue

            text = str(
                item.get("text")
                or item.get("t")
                or item.get("words")
                or item.get("content")
                or item.get("transcription")
                or item.get("value")
                or item.get("label")
                or ""
            ).strip()

            if _looks_like_ocr_prompt_echo_text(text):
                continue

            bbox_raw = item.get("bbox")
            if bbox_raw is None:
                for bbox_key in (
                    "b",
                    "box",
                    "bounding_box",
                    "location",
                    "rect",
                    "points",
                    "polygon",
                    "position",
                    "coordinates",
                    "quad",
                    "bbox_2d",
                ):
                    if bbox_key in item:
                        bbox_raw = item.get(bbox_key)
                        break
            bbox = _coerce_bbox_xyxy(bbox_raw)
            if not text or not bbox:
                continue

            try:
                x0, y0, x1, y1 = (
                    float(bbox[0]),
                    float(bbox[1]),
                    float(bbox[2]),
                    float(bbox[3]),
                )
            except Exception:
                continue
            if not all(math.isfinite(v) for v in (x0, y0, x1, y1)):
                continue

            confidence_raw = item.get("confidence")
            if confidence_raw is None:
                confidence_raw = item.get("c")
            if confidence_raw is None:
                confidence_raw = item.get("score")
            if confidence_raw is None:
                confidence_raw = item.get("prob")

            try:
                confidence = (
                    float(confidence_raw) if confidence_raw is not None else 0.7
                )
            except Exception:
                confidence = 0.7
            if confidence > 1.0:
                confidence = confidence / 100.0 if confidence <= 100.0 else 1.0
            confidence = max(0.0, min(confidence, 1.0))

            raw_elements.append(
                {
                    "text": text,
                    "bbox": [x0, y0, x1, y1],
                    "confidence": confidence,
                }
            )

        if not raw_elements:
            raise RuntimeError("AI OCR returned empty elements")

        # Normalize bbox coordinates into the real image pixel space.
        elements, debug = self._normalize_items_to_pixels(raw_elements, image=image)
        if not elements:
            raise RuntimeError("AI OCR bbox normalization produced no valid elements")

        # Lightweight sanity check: if bboxes cover only a tiny fraction of the
        # page and we have many items, treat it as a coordinate mismatch so
        # OcrManager can fall back to a bbox-accurate engine.
        try:
            if len(elements) >= 12:
                xs0 = sorted(float(it["bbox"][0]) for it in elements)
                xs1 = sorted(float(it["bbox"][2]) for it in elements)
                ys0 = sorted(float(it["bbox"][1]) for it in elements)
                ys1 = sorted(float(it["bbox"][3]) for it in elements)
                p05 = max(0, int(round((len(xs0) - 1) * 0.05)))
                p95 = max(0, int(round((len(xs1) - 1) * 0.95)))
                span_x = (xs1[p95] - xs0[p05]) / float(width)
                span_y = (ys1[p95] - ys0[p05]) / float(height)
                coverage_threshold = 0.24 if is_deepseek_model else 0.35
                if span_x < coverage_threshold or span_y < coverage_threshold:
                    raise RuntimeError(
                        f"AI OCR bbox coverage too small after normalization: span_x={span_x:.3f}, span_y={span_y:.3f}"
                    )
        except Exception as e:
            logger.warning("AI OCR bbox sanity check failed: %s debug=%s", e, debug)
            raise

        logger.info("AI OCR bbox normalization: %s", debug.get("chosen_details"))
        # Attach lightweight provenance for downstream dedupe/QA. Do NOT include
        # API keys or full URLs.
        try:
            for el in elements:
                if not isinstance(el, dict):
                    continue
                el.setdefault("provider", self.provider_id)
                el.setdefault("model", self.model)
        except Exception:
            pass
        return elements


