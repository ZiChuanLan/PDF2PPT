"""AI OCR text refinement and line-break assist."""

import base64
import io
import json
import logging
import math
import re
from typing import Any, Dict, List

import numpy as np
from PIL import Image

from .base import _env_float, _env_int
from .vendors import (
    _create_ai_ocr_vendor_adapter,
    _normalize_ai_ocr_model_name,
    _should_send_image_first_for_ai_ocr,
)
from .result_parsing import _normalize_bbox_px
from ._ai_helpers import (
    _coerce_int_in_range,
    _compact_debug_text,
    _run_chat_completion_request,
)
from ._ai_rate_limiter import _get_shared_ai_request_limiter

logger = logging.getLogger(__name__)


def _is_multiline_candidate_for_linebreak_assist(
    *,
    text: str,
    bbox: tuple[float, float, float, float] | Any,
    image_width: int,
    image_height: int,
    median_line_height: float,
) -> bool:
    """Decide whether an OCR bbox likely contains multiple visual lines.

    This is a pre-filter before calling a vision model to split lines. Keeping
    it as a standalone helper makes behavior testable and easier to tune.
    """

    bbox_n = _normalize_bbox_px(bbox) if not isinstance(bbox, tuple) else bbox
    if bbox_n is None:
        return False

    x0, y0, x1, y1 = bbox_n
    w = max(1.0, float(x1 - x0))
    h = max(1.0, float(y1 - y0))
    width = max(1, int(image_width))
    height = max(1, int(image_height))
    median_h = max(0.0, float(median_line_height))
    if median_h <= 0.0:
        median_h = max(10.0, 0.02 * float(height))

    raw_text = str(text or "")
    compact = re.sub(r"\s+", "", raw_text)
    if "\n" in raw_text and len(compact) >= 3:
        return True
    if len(compact) < 8:
        return False

    # Wide banner-like titles are often single-line even with larger bboxes;
    # avoid over-splitting these into pseudo-lines.
    wide_banner_like = (
        w >= 0.28 * float(width)
        and (h / max(1.0, w)) <= 0.11
        and len(compact) <= 42
        and h <= max(3.6 * median_h, 0.16 * float(height))
    )
    if wide_banner_like:
        return False

    # PaddleOCR-VL doc parser (and some AI OCR providers) frequently returns
    # paragraph-like bboxes that are only ~1.5x the median line height. A
    # stricter 1.8x gate misses these, leaving the renderer to guess line
    # breaks and causing visible wrap drift in PPT.
    if h >= max(1.80 * median_h, 0.055 * float(height)):
        return True
    if h >= max(1.45 * median_h, 0.045 * float(height)) and (
        len(compact) >= 16 or w >= 0.30 * float(width)
    ):
        return True
    return False



class AiOcrTextRefiner:
    """Refine OCR line texts using an OpenAI-compatible vision model.

    This does NOT change bounding boxes. It is designed to run after a bbox-
    accurate OCR engine (e.g. Tesseract) and improve transcription quality.
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None = None,
        model: str | None = None,
        provider: str | None = None,
        request_rpm_limit: int | None = None,
        request_tpm_limit: int | None = None,
        request_max_retries: int | None = None,
    ):
        import openai

        if not api_key:
            raise ValueError("AI refiner api_key is required")

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
            api_key=api_key,
            provider_id=self.provider_id,
            base_url=self.base_url,
            model=self.model,
            requests_per_minute=self.request_rpm_limit,
            tokens_per_minute=self.request_tpm_limit,
        )

    def _chat_completion(
        self,
        *,
        messages: Any,
        max_tokens: int,
        request_label: str,
    ) -> Any:
        from ...config import get_settings
        return _run_chat_completion_request(
            client=self.client,
            provider_id=self.provider_id,
            model=str(self.model or ""),
            timeout_s=get_settings().ocr_ai_text_refiner_timeout_s,
            max_retries=self.request_max_retries,
            request_limiter=self._request_limiter,
            request_label=request_label,
            logger_obj=logger,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0,
        )

    def refine_items(
        self,
        image_path: str,
        *,
        items: list[dict],
        max_items_per_call: int = 80,
    ) -> list[dict]:
        """Return a new items list with refined `text` fields.

        Args:
            image_path: Path to the page image.
            items: List of dicts with keys: text (str) and bbox ([x0,y0,x1,y1] in px).
            max_items_per_call: Chunk size to reduce truncation risk.
        """

        image = Image.open(image_path).convert("RGB")
        width, height = image.size
        if width <= 0 or height <= 0 or not items:
            return items

        import base64
        import io

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        data_uri = f"data:image/png;base64,{b64}"

        def _chunks(seq: list[dict], n: int) -> list[list[dict]]:
            n = max(1, int(n))
            return [seq[i : i + n] for i in range(0, len(seq), n)]

        refined: list[dict] = [dict(it) for it in items]

        # Build a stable indexing so the model can return corrections by id.
        indexed: list[dict] = []
        for i, it in enumerate(items):
            text = str(it.get("text") or "")
            bbox = it.get("bbox")
            if not isinstance(bbox, list) or len(bbox) != 4:
                continue
            indexed.append({"i": i, "bbox": bbox, "text": text})

        if not indexed:
            return refined

        for part in _chunks(indexed, max_items_per_call):
            prompt = (
                "You are an OCR post-processor. You will be given a page image and a JSON array of OCR line boxes. "
                "Each item has {i, bbox:[x0,y0,x1,y1], text}. The bbox is in PIXELS in the page image "
                f"(origin top-left, width={width}, height={height}).\n\n"
                "Task: For each item, READ the text inside its bbox on the image and output ONLY a JSON array of "
                "objects {i:int, text:string}. Keep the same i values. Do NOT include bbox in the output. "
                "Do NOT add new items.\n\n"
                "Rules:\n"
                "- The provided `text` is noisy; treat it as a hint only.\n"
                "- Preserve the original language(s) and punctuation (Chinese/English/numbers/parentheses).\n"
                "- Do NOT hallucinate words that are not visible in the bbox.\n"
                "- If the bbox is unreadable or blank, return the original text for that i.\n\n"
                "Input items:\n"
                + json.dumps(part, ensure_ascii=True)
                + "\n\nOutput ONLY the JSON array."
            )

            messages_payload: Any = [
                {
                    "role": "system",
                    "content": "Return JSON array only, no markdown.",
                },
                {
                    "role": "user",
                    "content": self.vendor_adapter.build_user_content(
                        prompt=prompt,
                        image_data_uri=data_uri,
                        image_first=_should_send_image_first_for_ai_ocr(
                            provider_id=self.provider_id,
                            model_name=self.model,
                        ),
                    ),
                },
            ]
            completion = self._chat_completion(
                messages=messages_payload,
                max_tokens=self.vendor_adapter.clamp_max_tokens(4096, kind="refiner"),
                request_label="text_refine",
            )

            content = (
                completion.choices[0].message.content
                if getattr(completion, "choices", None)
                else ""
            )
            out = _extract_json_list(content or "")
            if not out:
                continue

            for item in out:
                if not isinstance(item, dict):
                    continue
                idx = item.get("i")
                if not isinstance(idx, int) or idx < 0 or idx >= len(refined):
                    continue
                text = item.get("text")
                if isinstance(text, str):
                    # Never overwrite a bbox's OCR text with empty output from the
                    # refiner. Some vision models return "" when they can't read
                    # a region; keeping the original Tesseract/Baidu text preserves
                    # coverage (the user can later fix/delete a few bad boxes).
                    new_text = text.strip()
                    if new_text:
                        refined[idx]["text"] = new_text

        return refined

    def assist_line_breaks(
        self,
        image_path: str,
        *,
        items: list[dict],
        max_items_per_call: int = 36,
        max_lines_per_item: int = 8,
        allow_heuristic_fallback: bool = False,
    ) -> list[dict]:
        """Split coarse OCR boxes into line-level boxes with visual guidance.

        Primarily split vertically, and then opportunistically tighten each
        line's horizontal bounds by local ink projection. This improves layout
        fidelity for downstream PPT text placement/color sampling.
        """

        image = Image.open(image_path).convert("RGB")
        width, height = image.size
        if width <= 0 or height <= 0 or not items:
            return items

        import base64
        import io

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        data_uri = f"data:image/png;base64,{b64}"

        normalized_rows: list[dict[str, Any]] = []
        line_heights: list[float] = []
        for i, it in enumerate(items):
            if not isinstance(it, dict):
                continue
            text = str(it.get("text") or "").strip()
            bbox_n = _normalize_bbox_px(it.get("bbox"))
            if not text or bbox_n is None:
                continue
            x0, y0, x1, y1 = bbox_n
            h = max(1.0, float(y1 - y0))
            line_heights.append(h)
            normalized_rows.append(
                {
                    "i": i,
                    "text": text,
                    "bbox": [float(x0), float(y0), float(x1), float(y1)],
                    "bbox_n": bbox_n,
                    "original": it,
                }
            )

        if not normalized_rows:
            return items

        def _median(values: list[float]) -> float:
            if not values:
                return 0.0
            ordered = sorted(float(v) for v in values)
            n = len(ordered)
            m = n // 2
            if n % 2 == 1:
                return ordered[m]
            return (ordered[m - 1] + ordered[m]) / 2.0

        median_h = _median(line_heights)
        if median_h <= 0:
            median_h = max(10.0, 0.02 * float(height))

        candidates: list[dict[str, Any]] = []
        for row in normalized_rows:
            if _is_multiline_candidate_for_linebreak_assist(
                text=str(row.get("text") or ""),
                bbox=row.get("bbox_n"),
                image_width=width,
                image_height=height,
                median_line_height=median_h,
            ):
                candidates.append(
                    {
                        "i": row["i"],
                        "bbox": row["bbox"],
                        "text": row["text"],
                    }
                )

        if not candidates:
            return items

        def _chunks(seq: list[dict], n: int) -> list[list[dict]]:
            n = max(1, int(n))
            return [seq[i : i + n] for i in range(0, len(seq), n)]

        split_map: dict[int, list[str]] = {}
        for part in _chunks(candidates, max_items_per_call):
            prompt = (
                "You are an OCR layout post-processor. You will get a page image and a JSON array "
                "of OCR text boxes that may contain multiple visual lines. Each item has {i, bbox, text}. "
                "bbox is in PIXELS in the image "
                f"(origin top-left, width={width}, height={height}).\n\n"
                "Task: For each item, read only the text inside its bbox and split it into visual lines "
                "(top to bottom). Return ONLY a JSON array of objects {i:int, lines:string[]}.\n\n"
                "Rules:\n"
                "- Keep original i values; do NOT add new items.\n"
                "- Keep language and punctuation as seen in the image.\n"
                "- If a box is single-line or uncertain, return lines with exactly one entry.\n"
                "- Do NOT include markdown or explanations.\n\n"
                "Input items:\n"
                + json.dumps(part, ensure_ascii=True)
                + "\n\nOutput ONLY the JSON array."
            )

            messages_payload: Any = [
                {
                    "role": "system",
                    "content": "Return JSON array only, no markdown.",
                },
                {
                    "role": "user",
                    "content": self.vendor_adapter.build_user_content(
                        prompt=prompt,
                        image_data_uri=data_uri,
                        image_first=_should_send_image_first_for_ai_ocr(
                            provider_id=self.provider_id,
                            model_name=self.model,
                        ),
                    ),
                },
            ]
            completion = self._chat_completion(
                messages=messages_payload,
                max_tokens=self.vendor_adapter.clamp_max_tokens(3072, kind="refiner"),
                request_label="linebreak_refine",
            )

            content = (
                completion.choices[0].message.content
                if getattr(completion, "choices", None)
                else ""
            )
            out = _extract_json_list(content or "")
            if not out:
                continue

            for item in out:
                if not isinstance(item, dict):
                    continue
                idx = item.get("i")
                if not isinstance(idx, int):
                    continue
                raw_lines = item.get("lines")
                lines: list[str] = []
                if isinstance(raw_lines, str):
                    lines = [
                        seg.strip() for seg in raw_lines.splitlines() if seg.strip()
                    ]
                elif isinstance(raw_lines, list):
                    for seg in raw_lines:
                        if isinstance(seg, str):
                            cleaned = seg.strip()
                            if cleaned:
                                lines.append(cleaned)
                if lines:
                    split_map[idx] = lines[: max(1, int(max_lines_per_item))]

        row_map: dict[int, dict[str, Any]] = {
            int(row["i"]): row
            for row in normalized_rows
            if isinstance(row.get("i"), int)
        }
        candidate_idx_set: set[int] = {
            int(row["i"]) for row in candidates if isinstance(row.get("i"), int)
        }

        def _compact_text(text: str) -> str:
            return re.sub(r"\s+", "", text or "")

        def _split_is_plausible(
            original_text: str,
            lines: list[str],
            *,
            row: dict[str, Any] | None,
        ) -> bool:
            if len(lines) <= 1:
                return False
            compact_orig = _compact_text(original_text)
            compact_joined = _compact_text("".join(lines))
            if not compact_joined:
                return False
            if not compact_orig:
                return True

            contains_relation = (
                compact_orig in compact_joined or compact_joined in compact_orig
            )

            if contains_relation:
                diff = abs(len(compact_orig) - len(compact_joined))
                # For short/medium lines, don't accept splits that drop a visible
                # prefix/suffix chunk. This prevents title-like lines from losing
                # the first few glyphs after model line-splitting.
                if len(compact_orig) <= 44 and diff >= 3:
                    return False

            ratio = min(len(compact_orig), len(compact_joined)) / max(
                1, len(compact_orig), len(compact_joined)
            )
            min_ratio = 0.45
            # Moderate guard for short/medium boxes: strict enough to prevent
            # obvious truncation, but not so strict that valid line splits fail.
            if len(compact_orig) <= 64:
                min_ratio = 0.56
            if len(compact_orig) <= 36:
                min_ratio = 0.62
            if ratio < min_ratio:
                return False

            # Guard against unstable split outputs: for wide single-line titles,
            # splitting into a very short first segment + long remainder usually
            # hurts alignment and may later trigger noise filtering.
            if len(lines) == 2:
                lens = [len(_compact_text(seg)) for seg in lines]
                short_len = min(lens) if lens else 0
                long_len = max(lens) if lens else 0
                if short_len > 0 and long_len > 0:
                    imbalance = float(short_len) / float(long_len)
                    bbox_n = row.get("bbox_n") if isinstance(row, dict) else None
                    if isinstance(bbox_n, tuple) and len(bbox_n) == 4:
                        x0, y0, x1, y1 = bbox_n
                        w = max(1.0, float(x1 - x0))
                        h = max(1.0, float(y1 - y0))
                        wide_banner_like = (
                            w >= 0.25 * float(width) and (h / max(1.0, w)) <= 0.12
                        )
                        if wide_banner_like and short_len <= 5 and imbalance < 0.30:
                            return False

            return True

        def _split_bbox_by_ink_projection(
            row: dict[str, Any],
            *,
            n_lines: int,
        ) -> list[tuple[float, float]] | None:
            """Estimate vertical line ranges from image pixels inside a bbox.

            Returns a list of (y0, y1) in absolute image pixels for each line.
            """

            bbox_n = row.get("bbox_n")
            if not isinstance(bbox_n, tuple) or len(bbox_n) != 4:
                return None
            if n_lines <= 1:
                return None

            x0, y0, x1, y1 = bbox_n
            xi0 = max(0, min(width - 1, int(math.floor(float(x0)))))
            yi0 = max(0, min(height - 1, int(math.floor(float(y0)))))
            xi1 = max(0, min(width, int(math.ceil(float(x1)))))
            yi1 = max(0, min(height, int(math.ceil(float(y1)))))
            if xi1 - xi0 < 4 or yi1 - yi0 < max(6, n_lines * 3):
                return None

            try:
                gray = image.crop((xi0, yi0, xi1, yi1)).convert("L")
                arr = np.asarray(gray, dtype=np.float32)
            except Exception:
                return None

            if arr.ndim != 2 or arr.size <= 0:
                return None

            h_px, w_px = arr.shape
            if h_px < max(6, n_lines * 3):
                return None

            p95 = float(np.percentile(arr, 95.0))
            p10 = float(np.percentile(arr, 10.0))
            contrast = max(1.0, p95 - p10)
            if contrast < 8.0:
                return None

            # Convert to rough "ink" intensity (0..1), then row profile.
            ink = np.clip((p95 - arr) / contrast, 0.0, 1.0)
            ink_mask = (ink >= 0.16).astype(np.float32)
            row_profile = ink_mask.mean(axis=1)
            if float(np.sum(row_profile)) <= max(0.02 * h_px, 1.0):
                return None

            k = max(1, int(round(h_px / 54.0)))
            if k > 1:
                kernel = np.ones((k,), dtype=np.float32) / float(k)
                smooth = np.convolve(row_profile, kernel, mode="same")
            else:
                smooth = row_profile

            minima: list[int] = []
            low_th = float(np.percentile(smooth, 45.0))
            for pos in range(1, h_px - 1):
                v = float(smooth[pos])
                if v > low_th:
                    continue
                if v <= float(smooth[pos - 1]) and v <= float(smooth[pos + 1]):
                    minima.append(pos)

            target_cuts = max(1, int(n_lines) - 1)
            cuts: list[int] = []
            used: set[int] = set()
            max_dist = max(3, int(round(0.22 * h_px)))
            for k_idx in range(1, target_cuts + 1):
                target = int(round(float(k_idx) * float(h_px) / float(n_lines)))
                cands = [
                    m for m in minima if m not in used and abs(m - target) <= max_dist
                ]
                if not cands:
                    continue
                chosen = min(cands, key=lambda m: abs(m - target))
                cuts.append(chosen)
                used.add(chosen)

            # Fallback: quantiles by cumulative row ink.
            if len(cuts) < target_cuts:
                prof = smooth + 1e-6
                cum = np.cumsum(prof)
                total = float(cum[-1])
                if total > 0:
                    for k_idx in range(1, target_cuts + 1):
                        target_mass = total * (float(k_idx) / float(n_lines))
                        pos = int(np.searchsorted(cum, target_mass))
                        pos = max(1, min(h_px - 2, pos))
                        cuts.append(pos)

            if len(cuts) < target_cuts:
                return None

            cuts = sorted(set(cuts))
            if len(cuts) > target_cuts:
                # Keep cuts nearest to uniform targets for stability.
                targets = [
                    int(round(float(k_idx) * float(h_px) / float(n_lines)))
                    for k_idx in range(1, target_cuts + 1)
                ]
                selected: list[int] = []
                remaining = list(cuts)
                for t in targets:
                    if not remaining:
                        break
                    best = min(remaining, key=lambda c: abs(c - t))
                    selected.append(best)
                    remaining.remove(best)
                cuts = sorted(selected)

            bounds = [0] + cuts + [h_px]
            if len(bounds) != n_lines + 1:
                return None

            ranges: list[tuple[float, float]] = []
            prev_y = float(y0)
            for idx in range(n_lines):
                by0 = int(bounds[idx])
                by1 = int(bounds[idx + 1])
                if by1 - by0 < 1:
                    continue
                ly0 = float(y0) + float(by0)
                ly1 = float(y0) + float(by1)
                ly0 = max(float(y0), min(float(y1) - 1.0, ly0))
                ly1 = max(ly0 + 1.0, min(float(y1), ly1))
                if ly0 < prev_y:
                    ly0 = prev_y
                if ly1 <= ly0:
                    continue
                ranges.append((ly0, ly1))
                prev_y = ly1

            if len(ranges) != n_lines:
                return None

            heights = [max(0.0, ly1 - ly0) for (ly0, ly1) in ranges]
            if not heights:
                return None
            avg_h = float(sum(heights)) / float(max(1, len(heights)))
            min_h = min(heights)
            max_h = max(heights)
            # Guard against unstable projection cuts (over-compressed lines).
            # If line heights are too imbalanced, fallback to equal split.
            if avg_h > 0:
                if min_h < max(1.0, 0.55 * avg_h):
                    return None
                if max_h > (1.80 * avg_h):
                    return None

            return ranges

        def _tighten_line_bbox_x_by_ink(
            row: dict[str, Any],
            *,
            ly0: float,
            ly1: float,
            fallback_x0: float,
            fallback_x1: float,
        ) -> tuple[float, float]:
            """Best-effort horizontal tightening for a single split line bbox."""

            bbox_n = row.get("bbox_n")
            if not isinstance(bbox_n, tuple) or len(bbox_n) != 4:
                return (float(fallback_x0), float(fallback_x1))
            x0, y0, x1, y1 = bbox_n
            base_x0 = float(min(x0, x1))
            base_x1 = float(max(x0, x1))
            if base_x1 - base_x0 < 6.0:
                return (float(fallback_x0), float(fallback_x1))

            seg_y0 = max(float(y0), min(float(y1) - 1.0, float(ly0)))
            seg_y1 = max(seg_y0 + 1.0, min(float(y1), float(ly1)))
            if seg_y1 - seg_y0 < 2.0:
                return (float(fallback_x0), float(fallback_x1))

            xi0 = max(0, min(width - 1, int(math.floor(base_x0))))
            xi1 = max(0, min(width, int(math.ceil(base_x1))))
            yi0 = max(0, min(height - 1, int(math.floor(seg_y0))))
            yi1 = max(0, min(height, int(math.ceil(seg_y1))))
            if (xi1 - xi0) < 6 or (yi1 - yi0) < 2:
                return (float(fallback_x0), float(fallback_x1))

            try:
                gray = image.crop((xi0, yi0, xi1, yi1)).convert("L")
                arr = np.asarray(gray, dtype=np.float32)
            except Exception:
                return (float(fallback_x0), float(fallback_x1))

            if arr.ndim != 2 or arr.size <= 0:
                return (float(fallback_x0), float(fallback_x1))
            h_px, w_px = arr.shape
            if w_px < 6 or h_px < 2:
                return (float(fallback_x0), float(fallback_x1))

            p95 = float(np.percentile(arr, 95.0))
            p10 = float(np.percentile(arr, 10.0))
            contrast = max(1.0, p95 - p10)
            if contrast < 8.0:
                return (float(fallback_x0), float(fallback_x1))

            ink = np.clip((p95 - arr) / contrast, 0.0, 1.0)
            ink_mask = (ink >= 0.16).astype(np.float32)
            col_profile = ink_mask.mean(axis=0)
            if float(np.sum(col_profile)) <= max(0.015 * w_px, 1.0):
                return (float(fallback_x0), float(fallback_x1))

            # Prefer robust, not over-tight, trimming.
            th = float(np.percentile(col_profile, 65.0))
            th = max(0.04, min(0.22, th))
            active = np.where(col_profile >= th)[0]
            if active.size == 0:
                return (float(fallback_x0), float(fallback_x1))

            left_idx = int(active[0])
            right_idx = int(active[-1]) + 1
            if right_idx - left_idx < 3:
                return (float(fallback_x0), float(fallback_x1))

            base_w = max(1.0, base_x1 - base_x0)
            margin_px = max(1, int(round(0.025 * float(base_w))))
            left_idx = max(0, left_idx - margin_px)
            right_idx = min(w_px, right_idx + margin_px)
            if right_idx - left_idx < 3:
                return (float(fallback_x0), float(fallback_x1))

            tx0 = float(xi0 + left_idx)
            tx1 = float(xi0 + right_idx)
            tightened_w = max(1.0, tx1 - tx0)

            # Guard against unstable over-shrink, especially for short lines.
            line_text = str(row.get("text") or "")
            compact_len = len(_compact_text(line_text))
            min_ratio = 0.28 if compact_len <= 8 else 0.22
            if tightened_w < (min_ratio * base_w):
                return (float(fallback_x0), float(fallback_x1))

            # Never expand beyond original fallback bounds.
            tx0 = max(float(fallback_x0), min(float(fallback_x1) - 1.0, tx0))
            tx1 = min(float(fallback_x1), max(float(fallback_x0) + 1.0, tx1))
            if tx1 <= tx0:
                return (float(fallback_x0), float(fallback_x1))
            return (float(tx0), float(tx1))

        def _estimate_target_lines(row: dict[str, Any]) -> int:
            bbox_n = row.get("bbox_n")
            if not isinstance(bbox_n, tuple) or len(bbox_n) != 4:
                return 1
            _, y0, _, y1 = bbox_n
            h = max(1.0, float(y1 - y0))
            baseline = max(8.0, float(median_h))
            est = int(round(h / baseline))
            if _is_multiline_candidate_for_linebreak_assist(
                text=str(row.get("text") or ""),
                bbox=row.get("bbox_n"),
                image_width=width,
                image_height=height,
                median_line_height=median_h,
            ):
                est = max(est, 2)
            est = max(1, min(est, max(2, int(max_lines_per_item))))
            return est

        def _split_into_sentences(text: str) -> list[str]:
            cleaned = " ".join(str(text or "").split()).strip()
            if not cleaned:
                return []
            out: list[str] = []
            buf = ""
            for ch in cleaned:
                buf += ch
                if ch in "。！？!?；;":
                    seg = buf.strip()
                    if seg:
                        out.append(seg)
                    buf = ""
            if buf.strip():
                out.append(buf.strip())
            return out

        def _fallback_split_lines(original_text: str, target_lines: int) -> list[str]:
            target_lines = max(1, int(target_lines))
            normalized = " ".join(str(original_text or "").split()).strip()
            if not normalized:
                return []
            if target_lines <= 1:
                return [normalized]

            sentences = _split_into_sentences(normalized)
            if not sentences:
                sentences = [normalized]

            if len(sentences) < target_lines:
                finer: list[str] = []
                for seg in sentences:
                    parts = [
                        p.strip() for p in re.split(r"(?<=[，,：:])", seg) if p.strip()
                    ]
                    if len(parts) > 1:
                        finer.extend(parts)
                    else:
                        finer.append(seg)
                if finer:
                    sentences = finer

            if len(sentences) <= 1:
                compact_len = len(_compact_text(normalized))
                if compact_len < target_lines * 4:
                    return [normalized]
                per_line = max(4, int(round(compact_len / float(target_lines))))
                out: list[str] = []
                buf = ""
                buf_len = 0
                for ch in normalized:
                    buf += ch
                    if ch.isspace():
                        continue
                    buf_len += 1
                    if buf_len >= per_line and len(out) < (target_lines - 1):
                        seg = buf.strip()
                        if seg:
                            out.append(seg)
                        buf = ""
                        buf_len = 0
                if buf.strip():
                    out.append(buf.strip())
                return [seg for seg in out if seg]

            desired = max(2, min(target_lines, max(2, int(max_lines_per_item))))
            total = sum(max(1, len(_compact_text(seg))) for seg in sentences)
            target_chars = max(6.0, float(total) / float(desired))

            out: list[str] = []
            cur_parts: list[str] = []
            cur_chars = 0.0
            for idx, seg in enumerate(sentences):
                seg_chars = float(max(1, len(_compact_text(seg))))
                cur_parts.append(seg)
                cur_chars += seg_chars

                slots_left = max(1, desired - len(out))
                segments_left = len(sentences) - idx - 1
                should_cut = len(out) < (desired - 1) and (
                    cur_chars >= target_chars or segments_left <= (slots_left - 1)
                )
                if should_cut:
                    merged = "".join(cur_parts).strip()
                    if merged:
                        out.append(merged)
                    cur_parts = []
                    cur_chars = 0.0

            if cur_parts:
                merged = "".join(cur_parts).strip()
                if merged:
                    out.append(merged)

            return [seg for seg in out if seg]

        def _has_strong_two_line_split_cue(text: str) -> bool:
            normalized = " ".join(str(text or "").split()).strip()
            if not normalized:
                return False

            stripped = normalized.lstrip()
            if stripped.startswith(("-", "•", "·", "●", "▪", "▶", "◆", "■", "*")):
                return True

            parts = re.split(r"[：:]", normalized, maxsplit=1)
            if len(parts) == 2:
                head = _compact_text(parts[0])
                tail = _compact_text(parts[1])
                if 2 <= len(head) <= 26 and len(tail) >= 2:
                    return True

            if re.match(r"^\s*[（(]?[0-9一二三四五六七八九十]+[）).、]", normalized):
                return True

            return False

        def _is_structured_multiline_text(text: str) -> bool:
            raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
            if "\n" not in raw:
                return False

            lines = [ln.strip() for ln in raw.split("\n") if ln.strip()]
            if len(lines) < 3:
                return False

            compact_lens = [len(_compact_text(ln)) for ln in lines]
            if not compact_lens:
                return False

            marker_lines = 0
            for ln in lines:
                if any(tok in ln for tok in ("【", "】", "[", "]", "#", "##")):
                    marker_lines += 1

            avg_len = float(sum(compact_lens)) / float(max(1, len(compact_lens)))
            max_len = max(compact_lens)

            # Template/spec-like multiline blocks are often already close to
            # intended line structure; avoid AI split from over-fragmenting.
            if (
                marker_lines >= max(2, int(round(0.35 * len(lines))))
                and avg_len <= 34.0
            ):
                return True
            if marker_lines >= 2 and len(lines) >= 5 and max_len <= 48:
                return True

            return False

        def _allow_split_for_row(
            *,
            original_text: str,
            lines: list[str],
            row: dict[str, Any],
        ) -> bool:
            if len(lines) <= 1:
                return False
            if "\n" in str(original_text or ""):
                return True
            if len(lines) != 2:
                return True

            estimated = _estimate_target_lines(row)
            if estimated >= 3:
                return True

            compact_len = len(_compact_text(original_text))
            if compact_len <= 34:
                return True

            # Paragraph-like long text with only two inferred lines is usually
            # more stable when kept in one bbox and rendered with adaptive wrap.
            return _has_strong_two_line_split_cue(original_text)

        split_count = 0
        fallback_split_count = 0
        x_tighten_count = 0
        out_items: list[dict] = []
        for idx, original in enumerate(items):
            if not isinstance(original, dict):
                continue
            lines = split_map.get(idx) or []
            row = row_map.get(idx)
            if row is None:
                out_items.append(dict(original))
                continue

            original_text = str(row.get("text") or "")

            if idx in candidate_idx_set and _is_structured_multiline_text(
                original_text
            ):
                out_items.append(dict(original))
                continue

            clean_lines = [
                str(seg).strip() for seg in (lines or []) if str(seg).strip()
            ]

            if (
                allow_heuristic_fallback
                and (not clean_lines or len(clean_lines) <= 1)
                and idx in candidate_idx_set
            ):
                estimated = _estimate_target_lines(row)
                if estimated >= 2:
                    fallback_lines = _fallback_split_lines(original_text, estimated)
                    if len(fallback_lines) >= 2:
                        clean_lines = fallback_lines
                        fallback_split_count += 1

            if not _allow_split_for_row(
                original_text=original_text,
                lines=clean_lines,
                row=row,
            ):
                out_items.append(dict(original))
                continue

            if not _split_is_plausible(original_text, clean_lines, row=row):
                out_items.append(dict(original))
                continue

            bbox_n = row.get("bbox_n")
            if not isinstance(bbox_n, tuple) or len(bbox_n) != 4:
                out_items.append(dict(original))
                continue

            x0, y0, x1, y1 = bbox_n
            n = max(1, len(clean_lines))
            total_h = max(1.0, float(y1 - y0))

            ranges = _split_bbox_by_ink_projection(row, n_lines=n)

            for line_idx, text_line in enumerate(clean_lines):
                if ranges is not None and line_idx < len(ranges):
                    ly0, ly1 = ranges[line_idx]
                else:
                    ly0 = y0 + total_h * float(line_idx) / float(n)
                    ly1 = y0 + total_h * float(line_idx + 1) / float(n)
                if ly1 - ly0 < 1.0:
                    continue

                tx0, tx1 = _tighten_line_bbox_x_by_ink(
                    row,
                    ly0=float(ly0),
                    ly1=float(ly1),
                    fallback_x0=float(x0),
                    fallback_x1=float(x1),
                )
                if (tx1 - tx0) < (x1 - x0):
                    x_tighten_count += 1

                new_item = dict(original)
                new_item["text"] = text_line
                new_item["bbox"] = [float(tx0), float(ly0), float(tx1), float(ly1)]
                new_item["linebreak_assisted"] = True
                new_item["linebreak_assist_source"] = (
                    "ai" if idx in split_map else "heuristic_fallback"
                )
                out_items.append(new_item)

            split_count += 1

        if split_count > 0:
            logger.info(
                "AI OCR line-break assist applied: split_boxes=%s/%s (fallback=%s, x_tightened=%s)",
                split_count,
                len(items),
                fallback_split_count,
                x_tighten_count,
            )

        return out_items
