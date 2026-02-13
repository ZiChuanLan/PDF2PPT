from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Literal
import re

from .geometry import normalize_bbox_to_px, parse_bbox_candidate
from .models import OcrLine, PageRender, VisualRegion

_IMAGE_LABEL_KEYWORDS = {
    "image",
    "picture",
    "figure",
    "chart",
    "table",
    "diagram",
    "screenshot",
    "photo",
    "logo",
}

_IGNORED_TEXT_LABELS = {
    "footer",
    "footer_image",
    "header",
    "header_image",
    "footnote",
    "number",
}

_TITLE_LABEL_KEYWORDS = {
    "title",
    "paragraph_title",
    "doc_title",
    "section_title",
    "heading",
}


def _contains_keyword(text: str | None, keywords: set[str]) -> bool:
    label = str(text or "").strip().lower()
    if not label:
        return False
    return any(keyword in label for keyword in keywords)


def _extract_confidence(payload: dict[str, Any], *, default: float = 0.99) -> float:
    for key in ("score", "confidence", "prob", "probability", "conf"):
        value = payload.get(key)
        if value is None:
            continue
        try:
            conf = float(value)
            if conf > 1.0 and conf <= 100.0:
                conf = conf / 100.0
            return max(0.0, min(1.0, conf))
        except Exception:
            continue
    return max(0.0, min(1.0, float(default)))


def _visual_length(text: str) -> float:
    score = 0.0
    for ch in str(text or ""):
        if ch.isspace():
            continue
        if "\u4e00" <= ch <= "\u9fff":
            score += 1.0
        elif ord(ch) < 128:
            score += 0.62
        else:
            score += 0.9
    return score


def _split_sentence_chunks(text: str) -> list[str]:
    base = str(text or "").strip()
    if not base:
        return []
    chunks = [chunk.strip() for chunk in re.split(r"(?<=[。！？；.!?])", base) if chunk and chunk.strip()]
    if len(chunks) > 1:
        return chunks
    chunks = [chunk.strip() for chunk in re.split(r"(?<=[，,：:])", base) if chunk and chunk.strip()]
    if chunks:
        return chunks
    return [base]


def _split_by_minor_punctuation(text: str) -> list[str]:
    base = str(text or "").strip()
    if not base:
        return []
    parts = [part.strip() for part in re.split(r"(?<=[，,：:、])", base) if part and part.strip()]
    return parts if parts else [base]


def _hard_wrap_text(text: str, *, max_chars: float) -> list[str]:
    text = str(text or "").strip()
    if not text:
        return []
    out: list[str] = []
    remaining = text

    while remaining:
        if _visual_length(remaining) <= max_chars:
            out.append(remaining.strip())
            break

        lengths: list[float] = []
        acc = ""
        for ch in remaining:
            acc += ch
            lengths.append(_visual_length(acc))

        cut = 0
        for idx, value in enumerate(lengths):
            if value <= max_chars:
                cut = idx + 1
            else:
                break

        hard_max = max_chars * 1.35
        lookahead_cut = cut
        for idx, value in enumerate(lengths):
            if value <= hard_max:
                lookahead_cut = idx + 1
            else:
                break

        punct_set = {"，", ",", "。", "；", ";", "：", ":", "、", ")", "）", "]", "】"}
        best_cut = 0
        best_gap = float("inf")
        for idx in range(max(0, cut - 1), lookahead_cut):
            ch = remaining[idx]
            if ch not in punct_set:
                continue
            value = lengths[idx]
            gap = abs(value - max_chars)
            if value >= max_chars:
                gap *= 0.6
            if gap < best_gap:
                best_gap = gap
                best_cut = idx + 1

        use_cut = best_cut or cut

        if use_cut > 1 and use_cut < len(remaining):
            left = remaining[use_cut - 1]
            right = remaining[use_cut]
            if left.isascii() and right.isascii() and (left.isalnum() and right.isalnum()):
                back = use_cut - 1
                while back > 0 and remaining[back - 1].isascii() and remaining[back - 1].isalnum():
                    back -= 1
                if back > 0:
                    use_cut = back

        if use_cut <= 0:
            use_cut = 1

        head = remaining[:use_cut].strip()
        tail = remaining[use_cut:].strip()
        if head:
            out.append(head)
        remaining = tail

    return [item for item in out if item]


def _split_midpoint(line: str) -> tuple[str, str]:
    text = str(line or "").strip()
    if len(text) <= 1:
        return text, ""

    punct_positions = [
        idx for idx, ch in enumerate(text)
        if ch in {"，", ",", "。", "；", ";", "：", ":", "、"}
    ]
    if punct_positions:
        mid = len(text) // 2
        pos = min(punct_positions, key=lambda item: abs(item - mid))
        left = text[: pos + 1].strip()
        right = text[pos + 1 :].strip()
        if left and right:
            return left, right

    mid = len(text) // 2
    left = text[:mid].strip()
    right = text[mid:].strip()
    return left, right


def _estimate_target_lines(*, text: str, bbox: list[float], label: str) -> int:
    clean = "".join(ch for ch in str(text or "") if not ch.isspace())
    if not clean:
        return 0

    if _contains_keyword(label, _TITLE_LABEL_KEYWORDS):
        if len(clean) <= 28:
            return 1

    x0, y0, x1, y1 = [float(v) for v in bbox]
    box_w = max(1.0, x1 - x0)
    box_h = max(1.0, y1 - y0)

    cjk_count = sum(1 for ch in clean if "\u4e00" <= ch <= "\u9fff")
    cjk_ratio = float(cjk_count) / float(max(1, len(clean)))
    width_factor = 0.95 if cjk_ratio >= 0.5 else 0.62

    est = math.sqrt((float(len(clean)) * box_h * width_factor) / (1.35 * box_w))
    lines = int(round(est))

    visual_len = _visual_length(clean)

    if _contains_keyword(label, _TITLE_LABEL_KEYWORDS):
        lines = min(2, max(1, lines))
    else:
        lines = max(1, lines)
        if len(clean) >= 36:
            lines = max(lines, 2)
        cap = max(1, min(5, int(math.ceil(visual_len / 22.0))))
        lines = min(lines, cap)
        if visual_len >= 52:
            lines = max(lines, 3)

    return max(1, min(8, lines))


def _wrap_text_to_lines(*, text: str, target_lines: int) -> list[str]:
    source = str(text or "").strip()
    if not source:
        return []
    if target_lines <= 1:
        return [source]

    total_len = _visual_length(source)
    max_chars = max(8.0, total_len / float(max(1, target_lines)))
    line_limit = max_chars * 1.25

    chunks = _split_sentence_chunks(source)
    lines: list[str] = []
    buffer = ""

    def flush_buffer() -> None:
        nonlocal buffer
        text_value = buffer.strip()
        if text_value:
            lines.append(text_value)
        buffer = ""

    for chunk in chunks:
        piece = str(chunk or "").strip()
        if not piece:
            continue

        wrapped_pieces = [piece]
        if _visual_length(piece) > line_limit * 1.15:
            minor_parts = _split_by_minor_punctuation(piece)
            if len(minor_parts) > 1:
                wrapped_pieces = []
                for part in minor_parts:
                    if _visual_length(part) > line_limit * 1.15:
                        wrapped_pieces.extend(_hard_wrap_text(part, max_chars=max_chars))
                    else:
                        wrapped_pieces.append(part)
            else:
                wrapped_pieces = _hard_wrap_text(piece, max_chars=max_chars)

        for wrapped in wrapped_pieces:
            if not buffer:
                buffer = wrapped
                continue

            merged = f"{buffer}{wrapped}"
            if _visual_length(merged) <= line_limit:
                buffer = merged
            else:
                flush_buffer()
                buffer = wrapped

    flush_buffer()
    if not lines:
        lines = [source]

    # Rebalance to approach target line count.
    while len(lines) < target_lines:
        longest_idx = max(range(len(lines)), key=lambda idx: _visual_length(lines[idx]))
        if _visual_length(lines[longest_idx]) <= max_chars * 1.15:
            break
        left, right = _split_midpoint(lines[longest_idx])
        if not left or not right:
            break
        lines = lines[:longest_idx] + [left, right] + lines[longest_idx + 1 :]

    while len(lines) > target_lines and len(lines) >= 2:
        shortest_idx = min(range(len(lines)), key=lambda idx: _visual_length(lines[idx]))
        if shortest_idx <= 0:
            pair_idx = 0
        elif shortest_idx >= len(lines) - 1:
            pair_idx = len(lines) - 2
        else:
            left_len = _visual_length(lines[shortest_idx - 1])
            right_len = _visual_length(lines[shortest_idx + 1])
            pair_idx = shortest_idx - 1 if left_len <= right_len else shortest_idx
        merged = f"{lines[pair_idx]}{lines[pair_idx + 1]}"
        lines = lines[:pair_idx] + [merged] + lines[pair_idx + 2 :]

    return [line.strip() for line in lines if line and line.strip()]


def _split_block_text(text: str, *, bbox: list[float], label: str) -> list[str]:
    raw = str(text or "")
    lines = [line.strip() for line in raw.splitlines() if line and line.strip()]
    merged = "".join(lines).strip() if lines else raw.strip()
    if not merged:
        return []

    target_lines = _estimate_target_lines(text=merged, bbox=bbox, label=label)
    return _wrap_text_to_lines(text=merged, target_lines=target_lines)


class PaddleDocParserOcrClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        max_image_side_px: int = 2200,
    ):
        try:
            from paddleocr import PaddleOCRVL
        except Exception as exc:
            raise RuntimeError(
                "Paddle doc_parser backend requires 'paddleocr[doc-parser]' and 'paddlepaddle'."
            ) from exc

        model_lower = model.lower()
        if "1.5" in model_lower:
            pipeline_version = "v1.5"
        else:
            pipeline_version = "v1"

        self._pipeline = PaddleOCRVL(
            pipeline_version=pipeline_version,
            vl_rec_backend="vllm-server",
            vl_rec_server_url=base_url,
            vl_rec_api_model_name=model,
            vl_rec_api_key=api_key,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_chart_recognition=False,
            use_seal_recognition=False,
        )
        self._cache: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _normalize_bbox(raw_bbox: Any, page: PageRender) -> list[float] | None:
        parsed = parse_bbox_candidate(raw_bbox)
        if parsed is None:
            return None
        x0, y0, x1, y1 = parsed
        return normalize_bbox_to_px(
            x0=x0,
            y0=y0,
            x1=x1,
            y1=y1,
            width=page.width_px,
            height=page.height_px,
        )

    def _predict_payload(self, page: PageRender) -> dict[str, Any]:
        key = str(Path(page.image_path).resolve())
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        result_iter = self._pipeline.predict(key)
        result_obj = next(iter(result_iter), None)
        if result_obj is None:
            payload: dict[str, Any] = {}
            self._cache[key] = payload
            return payload

        raw_json = getattr(result_obj, "json", None)
        if callable(raw_json):
            try:
                raw_json = raw_json()
            except Exception:
                raw_json = None

        payload: dict[str, Any]
        if isinstance(raw_json, dict):
            if isinstance(raw_json.get("res"), dict):
                payload = raw_json["res"]
            else:
                payload = raw_json
        else:
            payload = {}

        self._cache[key] = payload
        return payload

    def ocr_page(
        self,
        page: PageRender,
        *,
        pass_mode: Literal["primary", "retry"] = "primary",
    ) -> list[OcrLine]:
        payload = self._predict_payload(page)
        blocks = payload.get("parsing_res_list")
        if not isinstance(blocks, list):
            return []

        source: Literal["ai_primary", "ai_retry"] = "ai_retry" if pass_mode == "retry" else "ai_primary"

        lines: list[OcrLine] = []
        for block in blocks:
            if not isinstance(block, dict):
                continue

            label = str(block.get("block_label") or "").strip().lower()
            if _contains_keyword(label, _IMAGE_LABEL_KEYWORDS):
                continue

            bbox = self._normalize_bbox(block.get("block_bbox"), page)
            if bbox is None:
                continue

            text_raw = block.get("block_content")
            if text_raw is None:
                continue
            text_items = _split_block_text(str(text_raw), bbox=bbox, label=label)
            if not text_items:
                continue

            if label in _IGNORED_TEXT_LABELS and len("".join(text_items)) <= 24:
                continue

            confidence = _extract_confidence(block)
            x0, y0, x1, y1 = bbox
            total_h = max(1.0, y1 - y0)
            slice_h = total_h / float(max(1, len(text_items)))
            block_id = block.get("block_id")
            if block_id is None:
                block_id = block.get("group_id")
            group_id = f"block:{block_id}" if block_id is not None else f"bbox:{int(round(x0))}:{int(round(y0))}:{int(round(x1))}:{int(round(y1))}"
            for idx, text in enumerate(text_items):
                ly0 = y0 + slice_h * float(idx)
                ly1 = y0 + slice_h * float(idx + 1)
                lines.append(
                    OcrLine(
                        text=text,
                        bbox=[x0, ly0, x1, ly1],
                        confidence=confidence,
                        source=source,
                        group_id=group_id,
                        group_bbox=[x0, y0, x1, y1],
                    )
                )

        lines.sort(key=lambda item: (float(item.bbox[1]), float(item.bbox[0])))
        return lines

    def detect_layout_regions(self, page: PageRender) -> list[VisualRegion]:
        payload = self._predict_payload(page)
        regions: list[VisualRegion] = []
        dedup: set[tuple[int, int, int, int]] = set()

        blocks = payload.get("parsing_res_list")
        if isinstance(blocks, list):
            for block in blocks:
                if not isinstance(block, dict):
                    continue
                label = str(block.get("block_label") or "").strip().lower()
                if not _contains_keyword(label, _IMAGE_LABEL_KEYWORDS):
                    continue
                bbox = self._normalize_bbox(block.get("block_bbox"), page)
                if bbox is None:
                    continue
                key = tuple(int(round(v)) for v in bbox)
                if key in dedup:
                    continue
                dedup.add(key)
                regions.append(
                    VisualRegion(
                        bbox=bbox,
                        label=label or None,
                        confidence=_extract_confidence(block),
                        source="ai_layout",
                    )
                )

        layout = payload.get("layout_det_res")
        if isinstance(layout, dict):
            boxes = layout.get("boxes")
            if isinstance(boxes, list):
                for block in boxes:
                    if not isinstance(block, dict):
                        continue
                    label = str(block.get("label") or "").strip().lower()
                    if not _contains_keyword(label, _IMAGE_LABEL_KEYWORDS):
                        continue
                    bbox = self._normalize_bbox(block.get("coordinate"), page)
                    if bbox is None:
                        continue
                    key = tuple(int(round(v)) for v in bbox)
                    if key in dedup:
                        continue
                    dedup.add(key)
                    regions.append(
                        VisualRegion(
                            bbox=bbox,
                            label=label or None,
                            confidence=_extract_confidence(block),
                            source="ai_layout",
                        )
                    )

        regions.sort(key=lambda item: (float(item.bbox[1]), float(item.bbox[0])))
        return regions
