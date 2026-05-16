"""Local layout-block OCR methods for AiOcrClient (mixin)."""

import copy
import html
import json
import logging
import math
import os
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
from PIL import Image

from .base import _env_float, _run_in_daemon_thread_with_timeout
from .deepseek_parser import _extract_deepseek_tagged_items, _looks_like_ocr_prompt_echo_text
from .json_extraction import _extract_json_list, _extract_message_text, _extract_partial_json_object_list
from .prompts import build_ai_ocr_layout_block_prompt, normalize_ai_ocr_prompt_override, resolve_ai_ocr_prompt_preset
from .result_parsing import _is_image_like_layout_label, _normalize_layout_label, _normalize_bbox_px
from .routing import ROUTE_KIND_REMOTE_PROMPT_OCR
from .utils import _coerce_bbox_xyxy
from .vendors import get_vendor_tuning, _should_send_image_first_for_ai_ocr
from ._ai_helpers import (
    _BG_DIFF_DARK_THRESHOLD,
    _BG_DIFF_LIGHT_BG_LUMA,
    _BG_DIFF_LIGHT_THRESHOLD,
    _BLOCK_CROP_PAD_MAX_PX,
    _BLOCK_CROP_PAD_MIN_PX,
    _BLOCK_CROP_PAD_RATIO,
    _BLOCK_CROP_YPAD_MAX_PX,
    _BLOCK_CROP_YPAD_MIN_PX,
    _BLOCK_CROP_YPAD_RATIO,
    _COL_THRESHOLD_MIN_PX,
    _COL_THRESHOLD_RATIO,
    _DEFAULT_TOLERANCE_PX,
    _EDGE_HEIGHT_CUTOFF,
    _EDGE_THRESH_HIGH,
    _EDGE_THRESH_LOW,
    _KEEP_AREA_RATIO,
    _KEEP_HEIGHT_RATIO,
    _KEEP_WIDTH_RATIO,
    _LAYOUT_BLOCK_DIMENSION_MIN_PX,
    _LAYOUT_BLOCK_PREDICT_TIMEOUT_MIN_S,
    _LAYOUT_MODEL_INIT_TIMEOUT_MIN_S,
    _OUTER_MARGIN_MAX_PX,
    _OUTER_MARGIN_MIN_PX,
    _OUTER_MARGIN_RATIO,
    _PAD_X_MAX_PX,
    _PAD_X_MIN_PX,
    _PAD_X_RATIO,
    _PAD_Y_MAX_PX,
    _PAD_Y_MIN_PX,
    _PAD_Y_RATIO,
    _RING_XMARGIN_MAX_PX,
    _RING_XMARGIN_MIN_PX,
    _RING_XMARGIN_RATIO,
    _RING_YMARGIN_MAX_PX,
    _RING_YMARGIN_MIN_PX,
    _RING_YMARGIN_RATIO,
    _ROW_THRESHOLD_MIN_PX,
    _ROW_THRESHOLD_RATIO,
    _SPECIAL_OCR_TOKEN_PATTERN,
    _STANDALONE_BOX_COORDS_PATTERN,
    _TIGHTENED_HEIGHT_RATIO,
    _TIGHTENED_WIDTH_RATIO,
    _build_layout_image_region_payload,
    _clone_image_region_payload,
    _coerce_int_in_range,
    _coerce_layout_geometry_points,
    _compact_debug_text,
    _env_int,
    _layout_geometry_kind,
    _normalize_ai_layout_model_name,
    _resolve_paddlex_layout_model_name,
    _run_chat_completion_request,
    _sanitize_debug_value,
    _utc_now_iso,
)
from ._ai_rate_limiter import _get_shared_ai_request_limiter, _estimate_chat_completion_tokens

logger = logging.getLogger(__name__)

# Confidence-based bypass thresholds for layout model reliability detection.
# When a layout model encounters unfamiliar image types (e.g. screenshots vs docs),
# it produces low-confidence detections. These constants control when to bypass
# block-level OCR and fall back to full-page OCR.
_CONFIDENCE_BYPASS_LOW_THRESHOLD = 0.5    # Score below this = "low confidence"
_CONFIDENCE_BYPASS_AVG_THRESHOLD = 0.3    # Average below this → bypass
_CONFIDENCE_BYPASS_RATIO_THRESHOLD = 0.8  # >80% low-confidence detections → bypass

# Adaptive coverage threshold: when layout model confidence is low/high,
# adjust the text-coverage bypass threshold to be more/less aggressive.
_LOW_CONFIDENCE_THRESHOLD = 0.6             # avg confidence below this → low
_HIGH_CONFIDENCE_THRESHOLD = 0.85           # avg confidence above this → high
_LOW_CONFIDENCE_COVERAGE_MULTIPLIER = 0.6   # reduce threshold when uncertain
_HIGH_CONFIDENCE_COVERAGE_MULTIPLIER = 1.3  # raise threshold when confident


class _LayoutBlockMixin:
    """Mixin providing local layout-block OCR methods for AiOcrClient."""

    def _get_local_layout_model(self) -> Any:
        normalized_layout_model = _normalize_ai_layout_model_name(self.layout_model)
        paddlex_model_name = _resolve_paddlex_layout_model_name(normalized_layout_model)
        with self.__class__._local_layout_model_lock:
            cached_model = self.__class__._local_layout_model
            cached_name = self.__class__._local_layout_model_name
            if cached_model is not None and cached_name == normalized_layout_model:
                return cached_model

            try:
                import paddlex
            except Exception as e:
                raise RuntimeError(
                    "Local layout_block OCR requires `paddlex` package"
                ) from e

            init_timeout_s = max(
                _LAYOUT_MODEL_INIT_TIMEOUT_MIN_S,
                _env_float("OCR_AI_LAYOUT_MODEL_INIT_TIMEOUT_S", 30.0),
            )
            model = _run_in_daemon_thread_with_timeout(
                lambda: paddlex.create_model(paddlex_model_name),
                timeout_s=init_timeout_s,
                label=f"{normalized_layout_model}:init",
            )
            self.__class__._local_layout_model = model
            self.__class__._local_layout_model_name = normalized_layout_model
            logger.info(
                "Initialized local layout model for AI OCR (layout_model=%s, paddlex_model=%s)",
                normalized_layout_model,
                paddlex_model_name,
            )
            return model

    def _extract_local_layout_blocks(
        self,
        output: Any,
    ) -> tuple[list[dict[str, Any]], list[Any]]:
        layout_blocks: list[dict[str, Any]] = []
        image_regions: list[Any] = []
        raw_boxes_debug: list[dict[str, Any]] = []

        def _result_payloads(result_obj: Any) -> list[Any]:
            payloads: list[Any] = []

            json_payload = getattr(result_obj, "json", None)
            if callable(json_payload):
                try:
                    payloads.append(json_payload())
                except Exception:
                    pass
            elif json_payload is not None:
                payloads.append(json_payload)

            to_dict_payload = getattr(result_obj, "to_dict", None)
            if callable(to_dict_payload):
                try:
                    payloads.append(to_dict_payload())
                except Exception:
                    pass

            payloads.append(result_obj)
            return payloads

        if isinstance(output, dict):
            results_iter = [output]
        elif isinstance(output, list):
            results_iter = output
        elif isinstance(output, tuple):
            results_iter = list(output)
        else:
            try:
                results_iter = list(output)
            except Exception:
                results_iter = [output]

        for result in results_iter:
            for payload in _result_payloads(result):
                if not isinstance(payload, dict):
                    continue
                root = (
                    payload.get("res")
                    if isinstance(payload.get("res"), dict)
                    else payload
                )
                if not isinstance(root, dict):
                    continue
                boxes = root.get("boxes")
                if not isinstance(boxes, list):
                    continue
                for raw_box in boxes:
                    if not isinstance(raw_box, dict):
                        continue
                    geometry_source: str | None = None
                    raw_geometry: Any = None
                    for candidate_source in (
                        "polygon_points",
                        "coordinate",
                        "bbox",
                        "box",
                    ):
                        candidate_value = raw_box.get(candidate_source)
                        if candidate_value is None:
                            continue
                        geometry_source = candidate_source
                        raw_geometry = candidate_value
                        break

                    bbox = _coerce_bbox_xyxy(raw_geometry)
                    if bbox is None:
                        continue
                    geometry_points = _coerce_layout_geometry_points(raw_geometry)
                    geometry_kind = _layout_geometry_kind(raw_geometry, geometry_source)
                    x0, y0, x1, y1 = (
                        float(bbox[0]),
                        float(bbox[1]),
                        float(bbox[2]),
                        float(bbox[3]),
                    )
                    if x1 - x0 < _LAYOUT_BLOCK_DIMENSION_MIN_PX or y1 - y0 < _LAYOUT_BLOCK_DIMENSION_MIN_PX:
                        continue

                    label = _normalize_layout_label(
                        raw_box.get("label") or raw_box.get("type")
                    )
                    try:
                        score = (
                            float(raw_box.get("score"))
                            if raw_box.get("score") is not None
                            else None
                        )
                    except Exception:
                        score = None
                    try:
                        order = (
                            int(raw_box.get("order"))
                            if raw_box.get("order") is not None
                            else None
                        )
                    except Exception:
                        order = None

                    block = {
                        "label": label,
                        "bbox": [x0, y0, x1, y1],
                        "score": score,
                        "order": order,
                        "geometry_source": geometry_source,
                        "geometry_kind": geometry_kind,
                        "geometry_points": geometry_points,
                        "text": "",
                    }
                    layout_blocks.append(block)
                    raw_boxes_debug.append(
                        {
                            "label": label,
                            "bbox": [x0, y0, x1, y1],
                            "score": score,
                            "order": order,
                            "geometry_source": geometry_source,
                            "geometry_kind": geometry_kind,
                            "geometry_points": geometry_points,
                        }
                    )
                    if _is_image_like_layout_label(label):
                        image_regions.append(
                            _build_layout_image_region_payload(
                                bbox=[x0, y0, x1, y1],
                                label=label,
                                score=score,
                                order=order,
                                geometry_source=geometry_source,
                                geometry_kind=geometry_kind,
                                geometry_points=geometry_points,
                            )
                        )
                break

        layout_blocks.sort(
            key=lambda block: (
                block.get("order") is None,
                int(block.get("order") or 0),
                float(((block.get("bbox") or [0, 0, 0, 0])[1])),
                float(((block.get("bbox") or [0, 0, 0, 0])[0])),
            )
        )
        self.last_layout_analysis_debug = {
            "layout_model": self.layout_model,
            "raw_boxes": _sanitize_debug_value(raw_boxes_debug),
            "extracted_blocks": _sanitize_debug_value(layout_blocks),
            "image_regions": _sanitize_debug_value(image_regions),
        }
        return layout_blocks, image_regions

    def _run_local_layout_analysis(
        self,
        image_path: str,
    ) -> tuple[list[dict[str, Any]], list[Any]]:
        requested_path = str(image_path)
        if (
            self._image_region_cache_ready
            and str(self._image_region_cache_path or "") == requested_path
            and str(self._last_layout_image_path or "") == requested_path
        ):
            return (
                [dict(block) for block in self.last_layout_blocks],
                [
                    _clone_image_region_payload(region)
                    for region in self.last_image_regions_px
                ],
            )

        layout_model = self._get_local_layout_model()
        predict_timeout_s = max(
            _LAYOUT_BLOCK_PREDICT_TIMEOUT_MIN_S,
            _env_float("OCR_AI_LAYOUT_MODEL_PREDICT_TIMEOUT_S", 45.0),
        )

        def _predict_and_extract_once() -> tuple[list[dict[str, Any]], list[Any]]:
            # PaddleX layout model instances are cached process-wide. Keep both
            # predict() and the immediate payload extraction serialized so a
            # later predict() cannot mutate or recycle the previous result
            # object before we finish parsing layout blocks for the current
            # page.
            with self.__class__._local_layout_predict_lock:
                try:
                    output = layout_model.predict(input=image_path)
                except TypeError:
                    output = layout_model.predict(image_path)
                try:
                    output = copy.deepcopy(output)
                except Exception:
                    pass
                return self._extract_local_layout_blocks(output)

        layout_blocks, image_regions = _run_in_daemon_thread_with_timeout(
            _predict_and_extract_once,
            timeout_s=predict_timeout_s,
            label=f"{self.layout_model}:predict",
        )
        self.last_layout_blocks = [dict(block) for block in layout_blocks]
        self.last_image_regions_px = [
            _clone_image_region_payload(region) for region in image_regions
        ]
        self._last_layout_image_path = requested_path
        self._image_region_cache_path = requested_path
        self._image_region_cache_ready = True
        if isinstance(self.last_layout_analysis_debug, dict):
            self.last_layout_analysis_debug = {
                **self.last_layout_analysis_debug,
                "image_path": requested_path,
                "layout_model": self.layout_model,
            }
        logger.info(
            "Local layout analysis produced %s blocks and %s image-like regions (layout_model=%s)",
            len(layout_blocks),
            len(image_regions),
            self.layout_model,
        )
        return (
            [dict(block) for block in layout_blocks],
            [_clone_image_region_payload(region) for region in image_regions],
        )

    def _image_to_data_uri(self, image: Image.Image) -> str:
        import base64
        import io

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{b64}"

    def _clean_plain_text_ocr_output(self, content: Any) -> str:
        text = _extract_message_text(content or "")
        stripped = str(text or "").strip()
        if not stripped:
            return ""

        try:
            parsed = json.loads(stripped)
        except Exception:
            parsed = None
        if isinstance(parsed, dict):
            candidate = (
                parsed.get("text") or parsed.get("content") or parsed.get("value")
            )
            if isinstance(candidate, str):
                stripped = candidate.strip()
        elif isinstance(parsed, list):
            lines: list[str] = []
            for item in parsed:
                if isinstance(item, str) and item.strip():
                    lines.append(item.strip())
                elif isinstance(item, dict):
                    candidate = (
                        item.get("text") or item.get("content") or item.get("value")
                    )
                    if isinstance(candidate, str) and candidate.strip():
                        lines.append(candidate.strip())
            if lines:
                stripped = "\n".join(lines)

        if stripped.startswith("```"):
            lines = stripped.splitlines()
            if lines:
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            stripped = "\n".join(lines).strip()

        for _ in range(2):
            decoded = html.unescape(stripped)
            if decoded == stripped:
                break
            stripped = decoded
        stripped = _SPECIAL_OCR_TOKEN_PATTERN.sub(" ", stripped)

        lowered = stripped.lower()
        if lowered in {
            "",
            "none",
            "null",
            "n/a",
            "no text",
            "no readable text",
            "empty",
        }:
            return ""

        cleaned_lines: list[str] = []
        for line in stripped.replace("\r\n", "\n").split("\n"):
            compact = re.sub(r"\s+", " ", str(line or "")).strip()
            if not compact:
                continue
            if _STANDALONE_BOX_COORDS_PATTERN.fullmatch(compact):
                continue
            cleaned_lines.append(compact)
        return "\n".join(line for line in cleaned_lines if line.strip()).strip()

    def _extract_deepseek_layout_block_text(self, content: Any) -> str:
        raw = _extract_message_text(content or "")
        tagged_items = _extract_deepseek_tagged_items(raw, max_items=48)
        if tagged_items:
            lines: list[str] = []
            for item in tagged_items:
                text = str(item.get("text") or "").strip()
                if not text or _looks_like_ocr_prompt_echo_text(text):
                    continue
                lines.append(text)
            if lines:
                return "\n".join(lines).strip()

        cleaned = self._clean_plain_text_ocr_output(content)
        if "<|ref|>" in raw or "<|det|>" in raw:
            return ""
        return cleaned

    def _crop_layout_block(
        self,
        *,
        image: Image.Image,
        bbox: list[float],
        geometry_points: list[list[float]] | None = None,
    ) -> Image.Image | None:
        width, height = image.size
        if width <= 0 or height <= 0:
            return None
        bbox_n = _normalize_bbox_px(bbox)
        if bbox_n is None:
            return None
        x0, y0, x1, y1 = bbox_n
        block_w = max(1.0, float(x1 - x0))
        block_h = max(1.0, float(y1 - y0))
        pad_x = min(_BLOCK_CROP_PAD_MAX_PX, max(_BLOCK_CROP_PAD_MIN_PX, int(round(block_w * _BLOCK_CROP_PAD_RATIO))))
        pad_y = min(_BLOCK_CROP_YPAD_MAX_PX, max(_BLOCK_CROP_YPAD_MIN_PX, int(round(block_h * _BLOCK_CROP_YPAD_RATIO))))
        xi0 = max(0, min(width - 1, int(math.floor(x0)) - pad_x))
        yi0 = max(0, min(height - 1, int(math.floor(y0)) - pad_y))
        xi1 = max(0, min(width, int(math.ceil(x1)) + pad_x))
        yi1 = max(0, min(height, int(math.ceil(y1)) + pad_y))
        if xi1 - xi0 < 6 or yi1 - yi0 < 6:
            return None
        cropped = image.crop((xi0, yi0, xi1, yi1)).convert("RGB")

        polygon_points: list[tuple[float, float]] = []
        for point in geometry_points or []:
            if not isinstance(point, list) or len(point) < 2:
                continue
            try:
                px = float(point[0]) - float(xi0)
                py = float(point[1]) - float(yi0)
            except Exception:
                continue
            if math.isfinite(px) and math.isfinite(py):
                polygon_points.append((px, py))

        ordered_points: list[tuple[float, float]] = []
        seen_points: set[tuple[float, float]] = set()
        for px, py in polygon_points:
            key = (round(px, 3), round(py, 3))
            if key in seen_points:
                continue
            seen_points.add(key)
            ordered_points.append((px, py))
        if len(ordered_points) < 3:
            return cropped

        try:
            from PIL import ImageDraw

            mask = Image.new("L", cropped.size, 0)
            draw = ImageDraw.Draw(mask)
            draw.polygon(ordered_points, fill=255)
            composited = Image.new("RGB", cropped.size, "white")
            composited.paste(cropped, mask=mask)
            return composited
        except Exception:
            return cropped

    def _tighten_layout_block_bbox_by_visual_bounds(
        self,
        *,
        image: Image.Image,
        bbox: list[float],
        geometry_points: list[list[float]] | None = None,
    ) -> list[float] | None:
        """Best-effort tighten of loose layout text boxes using visual content."""

        try:
            from PIL import ImageFilter
        except Exception:
            return None

        try:
            x0, y0, x1, y1 = [float(v) for v in bbox[:4]]
        except Exception:
            return None
        if (x1 - x0) <= 0.0 or (y1 - y0) <= 0.0:
            return None

        crop = self._crop_layout_block(
            image=image,
            bbox=bbox,
            geometry_points=geometry_points,
        )
        if crop is None:
            return None

        crop_w, crop_h = crop.size
        if crop_w < 48 or crop_h < 16:
            return None

        width, height = image.size
        bbox_n = _normalize_bbox_px(bbox)
        if bbox_n is None or width <= 0 or height <= 0:
            return None
        ox0, oy0, ox1, oy1 = bbox_n
        block_w = max(1.0, float(ox1 - ox0))
        block_h = max(1.0, float(oy1 - oy0))
        pad_x = min(_BLOCK_CROP_PAD_MAX_PX, max(_BLOCK_CROP_PAD_MIN_PX, int(round(block_w * _BLOCK_CROP_PAD_RATIO))))
        pad_y = min(_BLOCK_CROP_YPAD_MAX_PX, max(_BLOCK_CROP_YPAD_MIN_PX, int(round(block_h * _BLOCK_CROP_YPAD_RATIO))))
        crop_left = max(0, min(width - 1, int(math.floor(ox0)) - pad_x))
        crop_top = max(0, min(height - 1, int(math.floor(oy0)) - pad_y))

        try:
            gray = crop.convert("L")
            arr = np.asarray(gray, dtype=np.uint8)
        except Exception:
            return None
        if arr.ndim != 2 or arr.size <= 0:
            return None

        ring_y = max(_RING_YMARGIN_MIN_PX, min(_RING_YMARGIN_MAX_PX, int(round(_RING_YMARGIN_RATIO * float(crop_h)))))
        ring_x = max(_RING_XMARGIN_MIN_PX, min(_RING_XMARGIN_MAX_PX, int(round(_RING_XMARGIN_RATIO * float(crop_w)))))
        try:
            border_vals = np.concatenate(
                [
                    arr[:ring_y, :].reshape(-1),
                    arr[max(0, crop_h - ring_y) :, :].reshape(-1),
                    arr[:, :ring_x].reshape(-1),
                    arr[:, max(0, crop_w - ring_x) :].reshape(-1),
                ]
            )
        except Exception:
            return None
        if border_vals.size <= 0:
            return None

        bg = float(np.median(border_vals))
        diff = np.abs(arr.astype(np.int16) - int(round(bg)))

        try:
            edges = np.asarray(gray.filter(ImageFilter.FIND_EDGES), dtype=np.uint8)
        except Exception:
            return None
        if edges.shape != arr.shape:
            return None

        diff_thresh = _BG_DIFF_LIGHT_THRESHOLD if bg >= _BG_DIFF_LIGHT_BG_LUMA else _BG_DIFF_DARK_THRESHOLD
        edge_thresh = _EDGE_THRESH_LOW if crop_h <= _EDGE_HEIGHT_CUTOFF else _EDGE_THRESH_HIGH
        mask = (diff >= diff_thresh) | (edges >= edge_thresh)
        outer_margin = max(_OUTER_MARGIN_MIN_PX, min(_OUTER_MARGIN_MAX_PX, int(round(_OUTER_MARGIN_RATIO * float(min(crop_w, crop_h))))))
        if outer_margin > 0:
            mask[:outer_margin, :] = False
            mask[max(0, crop_h - outer_margin) :, :] = False
            mask[:, :outer_margin] = False
            mask[:, max(0, crop_w - outer_margin) :] = False
        if not bool(mask.any()):
            return None

        row_threshold = max(_ROW_THRESHOLD_MIN_PX, int(round(_ROW_THRESHOLD_RATIO * float(crop_w))))
        col_threshold = max(_COL_THRESHOLD_MIN_PX, int(round(_COL_THRESHOLD_RATIO * float(crop_h))))
        row_counts = mask.sum(axis=1)
        col_counts = mask.sum(axis=0)
        ys = np.flatnonzero(row_counts >= row_threshold)
        xs = np.flatnonzero(col_counts >= col_threshold)
        if ys.size <= 0 or xs.size <= 0:
            return None

        local_x0 = int(xs[0])
        local_y0 = int(ys[0])
        local_x1 = int(xs[-1]) + 1
        local_y1 = int(ys[-1]) + 1

        content_w = max(1, local_x1 - local_x0)
        content_h = max(1, local_y1 - local_y0)
        if content_w < 8 or content_h < 6:
            return None

        keep_area_ratio = (float(content_w) * float(content_h)) / max(
            1.0,
            float(crop_w) * float(crop_h),
        )
        width_keep_ratio = float(content_w) / max(1.0, float(crop_w))
        height_keep_ratio = float(content_h) / max(1.0, float(crop_h))
        if (
            keep_area_ratio >= _KEEP_AREA_RATIO
            and width_keep_ratio >= _KEEP_WIDTH_RATIO
            and height_keep_ratio >= _KEEP_HEIGHT_RATIO
        ):
            return None

        pad_x_local = max(_PAD_X_MIN_PX, min(_PAD_X_MAX_PX, int(round(_PAD_X_RATIO * float(content_h)))))
        pad_y_local = max(_PAD_Y_MIN_PX, min(_PAD_Y_MAX_PX, int(round(_PAD_Y_RATIO * float(content_h)))))
        local_x0 = max(0, local_x0 - pad_x_local)
        local_y0 = max(0, local_y0 - pad_y_local)
        local_x1 = min(crop_w, local_x1 + pad_x_local)
        local_y1 = min(crop_h, local_y1 + pad_y_local)
        if local_x1 - local_x0 < 6 or local_y1 - local_y0 < 6:
            return None

        tightened = [
            max(float(ox0), float(crop_left + local_x0)),
            max(float(oy0), float(crop_top + local_y0)),
            min(float(ox1), float(crop_left + local_x1)),
            min(float(oy1), float(crop_top + local_y1)),
        ]
        tightened_n = _normalize_bbox_px(tightened)
        if tightened_n is None:
            return None
        tx0, ty0, tx1, ty1 = tightened_n
        tightened_w = max(1.0, float(tx1 - tx0))
        tightened_h = max(1.0, float(ty1 - ty0))
        if tightened_w >= (_TIGHTENED_WIDTH_RATIO * block_w) and tightened_h >= (_TIGHTENED_HEIGHT_RATIO * block_h):
            return None
        return [float(tx0), float(ty0), float(tx1), float(ty1)]

    def _layout_geometry_fits_bbox(
        self,
        *,
        geometry_points: list[list[float]] | None,
        bbox: list[float],
        tolerance_px: float = _DEFAULT_TOLERANCE_PX,
    ) -> bool:
        if not geometry_points:
            return False
        bbox_n = _normalize_bbox_px(bbox)
        if bbox_n is None:
            return False
        x0, y0, x1, y1 = bbox_n
        tol = max(0.0, float(tolerance_px))
        for point in geometry_points:
            if not isinstance(point, list) or len(point) < 2:
                return False
            try:
                px = float(point[0])
                py = float(point[1])
            except Exception:
                return False
            if (
                px < (float(x0) - tol)
                or px > (float(x1) + tol)
                or py < (float(y0) - tol)
                or py > (float(y1) + tol)
            ):
                return False
        return True

    def _min_side_px_for_layout_block_model(self, effective_model: str) -> int:
        min_side_px = max(0, _env_int("OCR_AI_LAYOUT_BLOCK_MIN_SIDE_PX", 0))
        normalized_model = (
            _normalize_ai_ocr_model_name(
                effective_model,
                provider_id=self.provider_id,
            )
            or effective_model
            or ""
        )
        normalized_key = re.sub(r"[\s_]+", "-", str(normalized_model).strip().lower())
        if _is_deepseek_ocr_model(normalized_key):
            return max(min_side_px, 32)
        if "qwen3-vl" in normalized_key:
            return max(min_side_px, 32)
        return min_side_px

    def _resolve_local_layout_block_max_workers(self, *, effective_model: str) -> int:
        if self._layout_block_max_concurrency_override is not None:
            return int(self._layout_block_max_concurrency_override)
        raw_override = _clean_str(os.getenv("OCR_AI_LAYOUT_BLOCK_MAX_CONCURRENCY"))
        if raw_override is not None:
            try:
                parsed = int(raw_override)
            except Exception:
                parsed = 0
            return max(1, min(8, parsed or 4))

        provider_id = str(self.provider_id or "").strip().lower()
        lowered_model = str(effective_model or "").strip().lower()
        if "qwen3-vl" in lowered_model:
            tuning = get_vendor_tuning(self.provider_id)
            if tuning.layout_block_max_concurrency is not None:
                return tuning.layout_block_max_concurrency
        return 4

    def _resolve_local_layout_block_progress_log_interval_s(self) -> float:
        return max(
            0.0,
            _env_float("OCR_AI_LAYOUT_BLOCK_PROGRESS_LOG_INTERVAL_S", 10.0),
        )

    def _resolve_layout_block_request_timeout_s(self, *, effective_model: str) -> float:
        base_timeout = self._resolve_model_request_timeout_s(model_name=effective_model)
        default_timeout = max(
            float(base_timeout),
            _env_float("OCR_AI_LAYOUT_BLOCK_REQUEST_TIMEOUT_S", 40.0),
        )
        lowered = str(effective_model or "").strip().lower()
        if "qwen" in lowered and ("vl" in lowered or "omni" in lowered):
            return max(
                float(base_timeout),
                _env_float(
                    "OCR_AI_LAYOUT_BLOCK_REQUEST_TIMEOUT_S_QWEN",
                    default_timeout,
                ),
            )
        if "deepseek-ocr" in lowered or "deepseekocr" in lowered:
            return max(
                float(base_timeout),
                _env_float(
                    "OCR_AI_LAYOUT_BLOCK_REQUEST_TIMEOUT_S_DEEPSEEK_OCR",
                    default_timeout,
                ),
            )
        return default_timeout

    def _resolve_layout_block_retry_timeout_s(
        self,
        *,
        effective_model: str,
        request_timeout_s: float,
    ) -> float:
        default_retry_timeout = max(
            float(request_timeout_s) + _REQUEST_TIMEOUT_BUFFER_S,
            float(request_timeout_s) * _REQUEST_TIMEOUT_MULTIPLIER,
            _REQUEST_TIMEOUT_CAP_S,
        )
        lowered = str(effective_model or "").strip().lower()
        if "qwen" in lowered and ("vl" in lowered or "omni" in lowered):
            return max(
                float(request_timeout_s) + _RETRY_TIMEOUT_BUFFER_S,
                _env_float(
                    "OCR_AI_LAYOUT_BLOCK_RETRY_TIMEOUT_S_QWEN",
                    default_retry_timeout,
                ),
            )
        return max(
            float(request_timeout_s) + _RETRY_TIMEOUT_BUFFER_S,
            _env_float(
                "OCR_AI_LAYOUT_BLOCK_RETRY_TIMEOUT_S",
                default_retry_timeout,
            ),
        )

    def _should_retry_layout_block_timeout(self, *, effective_model: str) -> bool:
        lowered = str(effective_model or "").strip().lower()
        if "qwen" in lowered and ("vl" in lowered or "omni" in lowered):
            raw_specific = os.getenv("OCR_AI_LAYOUT_BLOCK_RETRY_ON_TIMEOUT_QWEN")
            if raw_specific is not None:
                return _env_flag(
                    "OCR_AI_LAYOUT_BLOCK_RETRY_ON_TIMEOUT_QWEN",
                    default=True,
                )
        return _env_flag("OCR_AI_LAYOUT_BLOCK_RETRY_ON_TIMEOUT", default=True)

    def _is_timeout_like_error(self, exc: Exception) -> bool:
        if isinstance(exc, TimeoutError):
            return True
        lowered = str(exc or "").strip().lower()
        return ("timed out" in lowered) or ("timeout" in lowered)

    def _prepare_layout_block_crop_for_model(
        self,
        *,
        crop: Image.Image,
        effective_model: str,
    ) -> Image.Image:
        min_side_px = self._min_side_px_for_layout_block_model(effective_model)
        if min_side_px <= 0:
            return crop
        crop_width, crop_height = crop.size
        if crop_width >= min_side_px and crop_height >= min_side_px:
            return crop
        scale = max(
            float(min_side_px) / max(1.0, float(crop_width)),
            float(min_side_px) / max(1.0, float(crop_height)),
        )
        target_width = max(min_side_px, int(math.ceil(float(crop_width) * scale)))
        target_height = max(min_side_px, int(math.ceil(float(crop_height) * scale)))
        if target_width == crop_width and target_height == crop_height:
            return crop
        return crop.resize((target_width, target_height), Image.Resampling.LANCZOS)

    def _should_skip_layout_block_for_ocr(self, *, label: str) -> bool:
        normalized = _normalize_layout_label(label)
        if not normalized:
            return False
        if normalized in {"footer", "page_number"}:
            return True
        if normalized.endswith("_footer") or normalized.startswith("page_number"):
            return True
        return False

    def _should_bypass_local_layout_block_ocr(
        self,
        *,
        image_path: str,
        image: Image.Image,
    ) -> str | None:
        """Return a bypass reason when direct page OCR is safer/faster.

        Uses multi-signal fusion instead of a single fixed threshold:
        1. Layout model confidence scores (model-native signal)
        2. Coverage area (secondary signal, adaptive based on confidence)
        3. Block count sanity check
        """

        try:
            layout_blocks, image_regions = self._run_local_layout_analysis(image_path)
        except Exception:
            return None

        self.last_layout_blocks = [dict(block) for block in layout_blocks]
        self.last_image_regions_px = [
            _clone_image_region_payload(region) for region in image_regions
        ]
        self._last_layout_image_path = str(image_path)
        self._image_region_cache_path = str(image_path)
        self._image_region_cache_ready = True

        page_w, page_h = image.size
        if page_w <= 0 or page_h <= 0:
            return None

        page_area = max(1.0, float(page_w * page_h))
        text_blocks: list[list[float]] = []
        text_area = 0.0
        confidence_scores: list[float] = []

        for block in layout_blocks:
            label = str(block.get("label") or "")
            if _is_image_like_layout_label(label):
                continue
            if self._should_skip_layout_block_for_ocr(label=label):
                continue
            bbox = block.get("bbox")
            if not isinstance(bbox, list) or len(bbox) != 4:
                continue
            bbox_n = _normalize_bbox_px(bbox)
            if bbox_n is None:
                continue
            x0, y0, x1, y1 = [float(v) for v in bbox_n]
            text_blocks.append([x0, y0, x1, y1])
            text_area += max(0.0, x1 - x0) * max(0.0, y1 - y0)
            score = block.get("score")
            if isinstance(score, (int, float)):
                confidence_scores.append(float(score))

        # Signal 1: Confidence scores (model-native, zero-cost)
        # When a layout model encounters image types it wasn't trained on
        # (e.g. screenshots for PP-DocLayout-V3 trained on papers/docs),
        # it produces low-confidence detections. This is the most reliable
        # signal — it's the model telling us "I'm not sure."
        if confidence_scores:
            avg_confidence = sum(confidence_scores) / len(confidence_scores)
            low_conf_count = sum(1 for s in confidence_scores if s < _CONFIDENCE_BYPASS_LOW_THRESHOLD)
            low_conf_ratio = low_conf_count / len(confidence_scores)

            if avg_confidence < _CONFIDENCE_BYPASS_AVG_THRESHOLD:
                logger.info(
                    "Layout model avg confidence %.2f < %.1f — bypassing block OCR"
                    " (text_blocks=%s, scores=%s, layout_model=%s, image=%s)",
                    avg_confidence,
                    _CONFIDENCE_BYPASS_AVG_THRESHOLD,
                    len(text_blocks),
                    [round(s, 2) for s in confidence_scores[:10]],
                    self.layout_model,
                    Path(image_path).name,
                )
                return "low_layout_confidence"

            if low_conf_ratio > _CONFIDENCE_BYPASS_RATIO_THRESHOLD:
                logger.info(
                    "Layout model %.0f%% detections below %.1f confidence — bypassing block OCR"
                    " (text_blocks=%s, layout_model=%s, image=%s)",
                    low_conf_ratio * 100,
                    _CONFIDENCE_BYPASS_LOW_THRESHOLD,
                    len(text_blocks),
                    self.layout_model,
                    Path(image_path).name,
                )
                return "high_low_confidence_ratio"

        # Signal 2: Coverage with adaptive threshold
        # When confidence is high but coverage is very low, the layout model
        # is "confident" about a small area — likely a real document with little
        # text, OR the model is confidently wrong about a non-document image.
        # Use a more conservative threshold when confidence is mediocre.
        coverage = text_area / page_area
        base_threshold = float(self._LOW_COVERAGE_THRESHOLD)

        if confidence_scores:
            avg_conf = sum(confidence_scores) / len(confidence_scores)
            if avg_conf < _LOW_CONFIDENCE_THRESHOLD:
                # Mediocre confidence → lower coverage threshold (more aggressive bypass)
                base_threshold *= _LOW_CONFIDENCE_COVERAGE_MULTIPLIER
            elif avg_conf > _HIGH_CONFIDENCE_THRESHOLD:
                # High confidence → trust the model more, raise threshold
                base_threshold *= _HIGH_CONFIDENCE_COVERAGE_MULTIPLIER

        if text_blocks and coverage < base_threshold:
            logger.info(
                "Layout text coverage %.1f%% below adaptive threshold %.0f%% — bypassing block OCR"
                " (text_blocks=%s, avg_conf=%.2f, layout_model=%s, image=%s)",
                coverage * 100,
                base_threshold * 100,
                len(text_blocks),
                sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.0,
                self.layout_model,
                Path(image_path).name,
            )
            return "low_text_coverage"

        if not text_blocks or len(text_blocks) > 3:
            return None

        min_y = float(page_h)
        max_y = 0.0
        max_width_ratio = 0.0
        for bbox in text_blocks:
            x0, y0, x1, y1 = bbox
            block_w = max(1.0, float(x1 - x0))
            block_h = max(1.0, float(y1 - y0))
            width_ratio = block_w / max(1.0, float(page_w))
            height_ratio = block_h / max(1.0, float(page_h))
            aspect_ratio = block_w / max(1.0, block_h)
            if (
                aspect_ratio < _WIDE_FLAT_MIN_ASPECT_RATIO
                or width_ratio < _WIDE_FLAT_MIN_WIDTH_RATIO
                or height_ratio > _WIDE_FLAT_MAX_HEIGHT_RATIO
            ):
                return None
            min_y = min(min_y, float(y0))
            max_y = max(max_y, float(y1))
            max_width_ratio = max(max_width_ratio, width_ratio)

        vertical_span_ratio = max(0.0, max_y - min_y) / max(1.0, float(page_h))
        if vertical_span_ratio > _WIDE_FLAT_MAX_VERTICAL_SPAN or max_width_ratio < _WIDE_FLAT_MIN_COVERAGE_RATIO:
            return None
        return "wide_flat_layout_blocks"

    _LOW_COVERAGE_THRESHOLD = _env_float(
        "OCR_AI_LAYOUT_COVERAGE_BYPASS_THRESHOLD", 0.30
    )

    # ------------------------------------------------------------------
    # Post-OCR quality validation
    # ------------------------------------------------------------------

    def _validate_layout_block_ocr_results(
        self,
        ocr_results: list[dict[str, Any]],
        image: Image.Image,
    ) -> str | None:
        """Check if layout-block OCR results are suspiciously sparse.

        Returns a reason string if results look bad, None if OK.
        This is a post-hoc signal — runs AFTER OCR, zero extra API cost.
        """
        if not ocr_results:
            return "no_ocr_results"

        page_w, page_h = image.size
        page_area = max(1.0, float(page_w * page_h))
        total_chars = sum(len(r.get("text", "")) for r in ocr_results)

        # Text density: chars per 10K pixels
        # A typical document page (A4, 300dpi, ~2500x3500) with 2000 chars
        # → density ≈ 2000 / (8750000/10000) ≈ 2.3 chars/10Kpx
        # A screenshot with sparse text might have density < 0.5
        text_density = total_chars / (page_area / _PIXELS_PER_10K)

        # Coherence: ratio of alphanumeric chars (real text vs garbage)
        alphanumeric = sum(
            c.isalnum() or c.isspace()
            for r in ocr_results
            for c in r.get("text", "")
        )
        coherence = alphanumeric / max(1, total_chars)

        # Suspicious conditions:
        # - Very little text from many blocks (layout model missed most content)
        # - Text is mostly garbage characters
        suspicious = False
        reason = None

        if text_density < _VALIDATION_DENSITY_THRESHOLD and len(ocr_results) >= 3:
            suspicious = True
            reason = f"very_low_density_{text_density:.2f}_chars_per_10Kpx"
        elif coherence < _VALIDATION_COHERENCE_THRESHOLD and total_chars > _VALIDATION_MIN_CHARS_FOR_COHERENCE:
            suspicious = True
            reason = f"low_coherence_{coherence:.2f}"
        elif len(ocr_results) <= _VALIDATION_TOO_FEW_BLOCKS and page_area > _VALIDATION_LARGE_IMAGE_AREA:
            # Large image but only 1-2 text blocks → layout model probably failed
            suspicious = True
            reason = f"too_few_blocks_{len(ocr_results)}_for_large_image"

        if suspicious:
            logger.warning(
                "Layout-block OCR results suspicious: %s"
                " (density=%.2f, coherence=%.2f, blocks=%d, chars=%d, image_size=%dx%d)",
                reason,
                text_density,
                coherence,
                len(ocr_results),
                total_chars,
                page_w,
                page_h,
            )

        return reason

    def _ocr_local_layout_block_crop(
        self,
        *,
        data_uri: str,
        label: str,
        crop_width: int,
        crop_height: int,
        effective_model: str,
    ) -> str:
        is_deepseek_model = _is_deepseek_ocr_model(effective_model)
        request_timeout_s = self._resolve_layout_block_request_timeout_s(
            effective_model=effective_model
        )
        retry_timeout_s = self._resolve_layout_block_retry_timeout_s(
            effective_model=effective_model,
            request_timeout_s=request_timeout_s,
        )
        resolved_prompt_preset = resolve_ai_ocr_prompt_preset(
            preset=self.prompt_preset,
            model_name=effective_model,
            provider_id=self.provider_id,
        )
        prompt = build_ai_ocr_layout_block_prompt(
            preset=resolved_prompt_preset,
            label=label,
            crop_width=int(crop_width),
            crop_height=int(crop_height),
            override=self.layout_block_prompt_override,
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
                "content": "You are an OCR engine. Return plain text only.",
            },
            {
                "role": "user",
                "content": user_content,
            },
        ]
        if is_deepseek_model:
            messages = [{"role": "user", "content": user_content}]

        request_kwargs = {
            "model": effective_model,
            "temperature": 0,
            "max_tokens": self.vendor_adapter.clamp_max_tokens(768, kind="ocr"),
            "messages": messages,
        }
        try:
            completion = self._chat_completion(
                **request_kwargs,
                timeout_s=request_timeout_s,
                request_label="layout_block_crop",
            )
        except Exception as exc:
            if not (
                self._should_retry_layout_block_timeout(effective_model=effective_model)
                and self._is_timeout_like_error(exc)
            ):
                raise
            logger.warning(
                "Retrying local layout_block OCR after timeout (label=%s, model=%s, timeout_s=%.1f, retry_timeout_s=%.1f)",
                label,
                effective_model,
                float(request_timeout_s),
                float(retry_timeout_s),
            )
            completion = self._chat_completion(
                **request_kwargs,
                timeout_s=retry_timeout_s,
                request_label="layout_block_crop_retry",
            )
        content_obj = (
            completion.choices[0].message.content
            if getattr(completion, "choices", None)
            else ""
        )
        if is_deepseek_model:
            return self._extract_deepseek_layout_block_text(content_obj)
        return self._clean_plain_text_ocr_output(content_obj)

    def _ocr_image_with_local_layout_blocks(
        self,
        image_path: str,
        *,
        image: Image.Image,
    ) -> List[Dict]:
        layout_blocks, image_regions = self._run_local_layout_analysis(image_path)
        self.last_layout_blocks = [dict(block) for block in layout_blocks]
        self.last_image_regions_px = [
            _clone_image_region_payload(region) for region in image_regions
        ]
        self._last_layout_image_path = str(image_path)
        self._image_region_cache_path = str(image_path)
        self._image_region_cache_ready = True

        effective_model = str(self.model)
        text_tasks: list[dict[str, Any]] = []
        for index, block in enumerate(layout_blocks):
            label = str(block.get("label") or "")
            if _is_image_like_layout_label(label):
                continue
            if self._should_skip_layout_block_for_ocr(label=label):
                if index < len(self.last_layout_blocks):
                    self.last_layout_blocks[index]["ocr_skipped"] = True
                    self.last_layout_blocks[index]["ocr_skip_reason"] = (
                        "low_value_layout_label"
                    )
                continue
            bbox = block.get("bbox")
            if not isinstance(bbox, list) or len(bbox) != 4:
                continue
            original_bbox = [float(v) for v in bbox]
            adjusted_bbox = self._tighten_layout_block_bbox_by_visual_bounds(
                image=image,
                bbox=original_bbox,
                geometry_points=block.get("geometry_points"),
            )
            effective_bbox = list(adjusted_bbox or original_bbox)
            geometry_points = block.get("geometry_points")
            geometry_source = block.get("geometry_source")
            geometry_kind = block.get("geometry_kind")
            if adjusted_bbox is not None and not self._layout_geometry_fits_bbox(
                geometry_points=geometry_points,
                bbox=effective_bbox,
            ):
                geometry_points = None
                geometry_source = None
                geometry_kind = None
            crop = self._crop_layout_block(
                image=image,
                bbox=effective_bbox,
                geometry_points=geometry_points,
            )
            if crop is None:
                continue
            crop = self._prepare_layout_block_crop_for_model(
                crop=crop,
                effective_model=effective_model,
            )
            if index < len(self.last_layout_blocks):
                self.last_layout_blocks[index]["ocr_input_bbox"] = list(effective_bbox)
                self.last_layout_blocks[index]["ocr_bbox_tightened"] = bool(
                    adjusted_bbox is not None
                )
                if adjusted_bbox is not None:
                    self.last_layout_blocks[index]["bbox_original"] = list(
                        original_bbox
                    )
                    self.last_layout_blocks[index]["bbox"] = list(effective_bbox)
            text_tasks.append(
                {
                    "index": index,
                    "bbox": list(effective_bbox),
                    "label": label,
                    "score": block.get("score"),
                    "order": block.get("order"),
                    "geometry_source": geometry_source,
                    "geometry_kind": geometry_kind,
                    "geometry_points": [
                        [float(point[0]), float(point[1])]
                        for point in (geometry_points or [])
                        if isinstance(point, list) and len(point) >= 2
                    ],
                    "crop_width": int(crop.size[0]),
                    "crop_height": int(crop.size[1]),
                    "data_uri": self._image_to_data_uri(crop),
                }
            )

        if not text_tasks:
            logger.info(
                "Local layout_block OCR found no text-like blocks (layout_model=%s, image_regions=%s)",
                self.layout_model,
                len(self.last_image_regions_px),
            )
            return []

        if isinstance(self.last_layout_analysis_debug, dict):
            self.last_layout_analysis_debug = {
                **self.last_layout_analysis_debug,
                "ocr_input_blocks": _sanitize_debug_value(self.last_layout_blocks),
            }

        image_name = Path(image_path).name
        max_workers = self._resolve_local_layout_block_max_workers(
            effective_model=effective_model
        )
        progress_interval_s = self._resolve_local_layout_block_progress_log_interval_s()
        raw_elements: list[dict[str, Any]] = []
        failures: list[str] = []
        task_lock = threading.Lock()
        last_progress_log_monotonic = 0.0

        for seq, task in enumerate(text_tasks, start=1):
            task["seq"] = seq
            task["status"] = "pending"
            task["submitted_at"] = _utc_now_iso()
            task["_submitted_monotonic"] = time.monotonic()

        logger.info(
            "Submitting local layout_block OCR page (image=%s, text_blocks=%s, image_like_regions=%s, layout_model=%s, provider=%s, model=%s, max_workers=%s)",
            image_name,
            len(text_tasks),
            len(self.last_image_regions_px),
            self.layout_model,
            self.provider_id,
            effective_model,
            max_workers,
        )

        def _summarize_task(
            task: dict[str, Any], *, now_monotonic: float
        ) -> dict[str, Any]:
            started_monotonic = float(
                task.get("_started_monotonic")
                or task.get("_submitted_monotonic")
                or 0.0
            )
            age_ms = int(round(max(0.0, now_monotonic - started_monotonic) * 1000.0))
            return {
                "seq": int(task.get("seq") or 0),
                "index": int(task.get("index") or 0),
                "label": task.get("label") or None,
                "status": str(task.get("status") or "pending"),
                "crop": [
                    int(task.get("crop_width") or 0),
                    int(task.get("crop_height") or 0),
                ],
                "age_ms": age_ms,
            }

        def _maybe_log_local_layout_progress(*, force: bool = False) -> None:
            nonlocal last_progress_log_monotonic
            now_monotonic = time.monotonic()
            if (
                not force
                and progress_interval_s > 0.0
                and (now_monotonic - last_progress_log_monotonic) < progress_interval_s
            ):
                return
            with task_lock:
                snapshots = [
                    _summarize_task(task, now_monotonic=now_monotonic)
                    for task in text_tasks
                ]
            payload = {
                "image": image_name,
                "provider": self.provider_id,
                "model": effective_model,
                "max_workers": max_workers,
                "block_counts": {
                    "total": len(snapshots),
                    "success": sum(
                        1 for item in snapshots if item["status"] == "success"
                    ),
                    "error": sum(1 for item in snapshots if item["status"] == "error"),
                    "pending": sum(
                        1
                        for item in snapshots
                        if item["status"] in {"pending", "running"}
                    ),
                },
                "unfinished_blocks": [
                    item
                    for item in snapshots
                    if item["status"] in {"pending", "running"}
                ][:12],
            }
            last_progress_log_monotonic = now_monotonic
            logger.info(
                "Local layout_block OCR progress: %s",
                json.dumps(payload, ensure_ascii=True, sort_keys=True),
            )

        def _mark_task_started(task: dict[str, Any]) -> None:
            with task_lock:
                task["status"] = "running"
                task["started_at"] = _utc_now_iso()
                task["_started_monotonic"] = time.monotonic()
            logger.info(
                "Local layout_block OCR started block (image=%s, block=%s/%s, index=%s, label=%s, crop=%sx%s)",
                image_name,
                int(task.get("seq") or 0),
                len(text_tasks),
                int(task.get("index") or 0),
                task.get("label") or "",
                int(task.get("crop_width") or 0),
                int(task.get("crop_height") or 0),
            )

        def _mark_task_finished(
            task: dict[str, Any],
            *,
            error: BaseException | None = None,
            text: str | None = None,
        ) -> None:
            now_monotonic = time.monotonic()
            with task_lock:
                started_monotonic = float(
                    task.get("_started_monotonic")
                    or task.get("_submitted_monotonic")
                    or 0.0
                )
                elapsed_ms = int(
                    round(max(0.0, now_monotonic - started_monotonic) * 1000.0)
                )
                task["finished_at"] = _utc_now_iso()
                task["elapsed_ms"] = elapsed_ms
                if error is None:
                    task["status"] = "success"
                    task["text_len"] = len(str(text or ""))
                else:
                    task["status"] = "error"
                    task["error"] = _compact_debug_text(error, limit=240)
            if error is None:
                logger.info(
                    "Local layout_block OCR finished block (image=%s, block=%s/%s, index=%s, label=%s, elapsed_ms=%s, text_len=%s)",
                    image_name,
                    int(task.get("seq") or 0),
                    len(text_tasks),
                    int(task.get("index") or 0),
                    task.get("label") or "",
                    int(task.get("elapsed_ms") or 0),
                    int(task.get("text_len") or 0),
                )
            else:
                logger.warning(
                    "Local layout_block OCR failed block (image=%s, block=%s/%s, index=%s, label=%s, elapsed_ms=%s): %s",
                    image_name,
                    int(task.get("seq") or 0),
                    len(text_tasks),
                    int(task.get("index") or 0),
                    task.get("label") or "",
                    int(task.get("elapsed_ms") or 0),
                    error,
                )

        def _run_task(task: dict[str, Any]) -> dict[str, Any]:
            _mark_task_started(task)
            try:
                text = self._ocr_local_layout_block_crop(
                    data_uri=str(task["data_uri"]),
                    label=str(task.get("label") or ""),
                    crop_width=int(task.get("crop_width") or 0),
                    crop_height=int(task.get("crop_height") or 0),
                    effective_model=effective_model,
                )
            except Exception as exc:
                _mark_task_finished(task, error=exc)
                raise
            _mark_task_finished(task, text=text)
            result = dict(task)
            result["text"] = text
            return result

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(_run_task, task): task for task in text_tasks}
            pending_futures = set(future_map)
            while pending_futures:
                done_futures, pending_futures = wait(
                    pending_futures,
                    timeout=1.0,
                    return_when=FIRST_COMPLETED,
                )
                for future in done_futures:
                    task = future_map[future]
                    try:
                        result = future.result()
                    except Exception as e:
                        failures.append(f"block={task.get('index')} error={e}")
                        continue
                    text = str(result.get("text") or "").strip()
                    if not text or _looks_like_ocr_prompt_echo_text(text):
                        continue
                    raw_elements.append(
                        {
                            "text": text,
                            "bbox": list(result["bbox"]),
                            "confidence": max(
                                0.55,
                                min(
                                    0.98,
                                    float(result.get("score"))
                                    if result.get("score") is not None
                                    else 0.82,
                                ),
                            ),
                            "provider": self.provider_id,
                            "model": effective_model,
                            "ocr_layout_label": result.get("label") or None,
                            "ocr_layout_geometry_source": result.get("geometry_source")
                            or None,
                            "ocr_layout_geometry_kind": result.get("geometry_kind")
                            or None,
                            "ocr_layout_geometry_points": result.get("geometry_points")
                            or None,
                        }
                    )
                    self.last_layout_blocks[int(result["index"])]["text"] = text
                if pending_futures:
                    _maybe_log_local_layout_progress()

        _maybe_log_local_layout_progress(force=True)

        raw_elements.sort(
            key=lambda item: (
                float(((item.get("bbox") or [0, 0, 0, 0])[1])),
                float(((item.get("bbox") or [0, 0, 0, 0])[0])),
            )
        )
        if raw_elements:
            logger.info(
                "Local layout_block OCR parsed %s text blocks and %s image-like regions (layout_model=%s, model=%s, failures=%s)",
                len(raw_elements),
                len(self.last_image_regions_px),
                self.layout_model,
                effective_model,
                len(failures),
            )
            return raw_elements

        failure_preview = "; ".join(failures[:3]).strip()
        raise RuntimeError(
            "Local layout block OCR returned no usable text blocks"
            + (f" ({failure_preview})" if failure_preview else "")
        )
