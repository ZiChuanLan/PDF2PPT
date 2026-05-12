"""Private extraction helpers for MinerU adapter (split from mineru_adapter.py).

Contains text extraction, bbox extraction, kind detection, page indexing,
style parsing, and content-list parsing logic.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pymupdf

from app.models.error import AppException, ErrorCode
from app.utils.text import clean_str as _clean_str
from ._adapter_utils import _IMAGE_KIND_TOKENS, _is_image_like_kind


_DEFAULT_PAGE_WIDTH_PT = 1000.0
_DEFAULT_PAGE_HEIGHT_PT = 1000.0

# ------------------------------------------------------------------ public api


# flake8: noqa: E302 (blank-line-before-function – we group by topic)

# ---- color / style helpers ----

def _normalize_hex_color(value: Any) -> str | None:
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        try:
            r = max(0, min(255, int(value[0])))
            g = max(0, min(255, int(value[1])))
            b = max(0, min(255, int(value[2])))
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception:
            return None

    cleaned = _clean_str(value if isinstance(value, str) else None)
    if not cleaned:
        return None
    normalized = cleaned.strip()
    if normalized.startswith("#"):
        normalized = normalized[1:]
    elif normalized.lower().startswith("0x"):
        normalized = normalized[2:]

    if len(normalized) == 8:
        normalized = normalized[-6:]
    if len(normalized) == 3:
        normalized = "".join(ch * 2 for ch in normalized)
    if len(normalized) != 6:
        return None
    try:
        int(normalized, 16)
    except Exception:
        return None
    return f"#{normalized.lower()}"


def _extract_style_value(item: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in item:
            return item.get(key)
    style = item.get("style")
    if isinstance(style, dict):
        for key in keys:
            if key in style:
                return style.get(key)
    return None


def _extract_positive_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            num = float(value)
        except Exception:
            return None
        return num if num > 0 else None
    if isinstance(value, str):
        cleaned = value.strip().lower().replace("pt", "").strip()
        if not cleaned:
            return None
        try:
            num = float(cleaned)
        except Exception:
            return None
        return num if num > 0 else None
    return None


def _coerce_optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if float(value) == 1.0:
            return True
        if float(value) == 0.0:
            return False
        return None
    if not isinstance(value, str):
        return None
    lowered = value.strip().lower()
    if lowered in {"true", "1", "yes", "y", "on"}:
        return True
    if lowered in {"false", "0", "no", "n", "off"}:
        return False
    if lowered in {"bold", "semibold"}:
        return True
    if lowered in {"normal", "regular"}:
        return False
    if lowered.isdigit():
        try:
            return int(lowered) >= 600
        except Exception:
            return None
    return None


def _extract_text_style(item: dict[str, Any]) -> dict[str, Any]:
    style: dict[str, Any] = {}

    color = _normalize_hex_color(
        _extract_style_value(item, "color", "text_color", "font_color", "fg_color")
    )
    if color:
        style["color"] = color

    font_size = _extract_positive_float(
        _extract_style_value(item, "font_size_pt", "font_size", "size", "text_size")
    )
    if font_size is not None and 1.0 <= font_size <= 240.0:
        style["font_size_pt"] = float(font_size)

    font_name = _clean_str(
        _extract_style_value(item, "font_name", "font", "font_family", "family")
    )
    if font_name:
        style["font_name"] = font_name

    bold = _coerce_optional_bool(
        _extract_style_value(item, "bold", "is_bold", "font_bold", "font_weight", "weight")
    )
    if bold is not None:
        style["bold"] = bool(bold)

    italic = _coerce_optional_bool(
        _extract_style_value(item, "italic", "is_italic", "font_italic", "slant")
    )
    if italic is not None:
        style["italic"] = bool(italic)

    return style


def _normalize_mineru_token(value: str | None) -> str | None:
    cleaned = _clean_str(value)
    if not cleaned:
        return None
    lowered = cleaned.lower()
    if lowered.startswith("bearer "):
        token = cleaned[7:].strip()
        return token if token else None
    return cleaned


def _parse_page_ranges(page_start: int | None, page_end: int | None) -> str | None:
    if page_start is None and page_end is None:
        return None
    if page_start is None or page_end is None:
        return None
    start = int(page_start)
    end = int(page_end)
    if start <= 0 or end <= 0 or start > end:
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            message="Invalid page range",
            details={"page_start": page_start, "page_end": page_end},
        )
    return f"{start}-{end}"


# ---- JSON / file helpers ----

def _find_json_file(
    root: Path,
    *,
    exact_name: str,
    suffix_name: str,
    contain_name: str | None = None,
) -> Path | None:
    exact_name_lower = exact_name.lower()
    suffix_name_lower = suffix_name.lower()
    contain_name_lower = contain_name.lower() if contain_name else None

    candidates: list[Path] = []
    for path in root.rglob("*.json"):
        name_lower = path.name.lower()
        if name_lower == exact_name_lower or name_lower.endswith(suffix_name_lower):
            candidates.append(path)
            continue
        if contain_name_lower and contain_name_lower in name_lower:
            candidates.append(path)
    if not candidates:
        return None

    def _candidate_sort_key(path: Path) -> tuple[int, int, str]:
        name_lower = path.name.lower()
        if name_lower == exact_name_lower:
            rank = 0
        elif name_lower.endswith(suffix_name_lower):
            rank = 1
        elif contain_name_lower and contain_name_lower in name_lower:
            rank = 2
        else:
            rank = 3
        return (rank, len(str(path)), str(path))

    candidates.sort(key=_candidate_sort_key)
    return candidates[0]


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise AppException(
            code=ErrorCode.CONVERSION_FAILED,
            message="Failed to parse MinerU output JSON",
            details={"path": str(path), "error": str(e)},
            status_code=500,
        )


# ---- page-size helpers ----

def _extract_page_sizes(middle_payload: Any) -> dict[int, tuple[float, float]]:
    page_sizes: dict[int, tuple[float, float]] = {}
    pdf_info: Any = None

    if isinstance(middle_payload, dict):
        pdf_info = middle_payload.get("pdf_info")
        if pdf_info is None and isinstance(middle_payload.get("data"), dict):
            pdf_info = middle_payload["data"].get("pdf_info")

    if not isinstance(pdf_info, list):
        return page_sizes

    for fallback_idx, page in enumerate(pdf_info):
        if not isinstance(page, dict):
            continue
        idx_raw = page.get("page_idx")
        try:
            page_idx = int(idx_raw) if idx_raw is not None else int(fallback_idx)
        except Exception:
            page_idx = int(fallback_idx)

        size = page.get("page_size")
        if not isinstance(size, list) or len(size) != 2:
            continue
        try:
            page_w = float(size[0])
            page_h = float(size[1])
        except Exception:
            continue
        if page_w <= 0 or page_h <= 0:
            continue
        page_sizes[page_idx] = (page_w, page_h)

    return page_sizes


def _extract_pdf_page_sizes(pdf_path: Path) -> dict[int, tuple[float, float]]:
    page_sizes: dict[int, tuple[float, float]] = {}
    try:
        doc = pymupdf.open(str(pdf_path))
    except Exception:
        return page_sizes
    try:
        for idx in range(int(doc.page_count or 0)):
            page = doc.load_page(idx)
            page_sizes[idx] = (float(page.rect.width), float(page.rect.height))
    except Exception:
        return {}
    finally:
        doc.close()
    return page_sizes


# ---- content-list extraction helpers ----

def _with_inferred_page_idx(item: dict[str, Any], *, page_idx: int) -> dict[str, Any]:
    for key in ("page_idx", "page_index", "page"):
        if key in item:
            return item
    copied = dict(item)
    copied["page_idx"] = int(page_idx)
    return copied


def _extract_items_from_sequence(sequence: list[Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for idx, entry in enumerate(sequence):
        if isinstance(entry, dict):
            items.append(entry)
            continue
        if isinstance(entry, list):
            for nested in entry:
                if isinstance(nested, dict):
                    items.append(_with_inferred_page_idx(nested, page_idx=idx))
    return items


def _extract_content_items(content_payload: Any) -> list[dict[str, Any]]:
    if isinstance(content_payload, list):
        direct = _extract_items_from_sequence(content_payload)
        if direct:
            return direct

    if not isinstance(content_payload, dict):
        return []

    direct = content_payload.get("content_list")
    if isinstance(direct, list):
        direct_items = _extract_items_from_sequence(direct)
        if direct_items:
            return direct_items

    nested_data = content_payload.get("data")
    if isinstance(nested_data, dict):
        nested = nested_data.get("content_list")
        if isinstance(nested, list):
            nested_items = _extract_items_from_sequence(nested)
            if nested_items:
                return nested_items

    fallback_items: list[dict[str, Any]] = []
    for value in content_payload.values():
        if isinstance(value, list):
            fallback_items.extend(_extract_items_from_sequence(value))
    return fallback_items


# ---- layout extraction helpers ----

def _is_layout_formula_span(span_type: str) -> bool:
    lowered = str(span_type or "").strip().lower()
    if not lowered:
        return False
    return any(token in lowered for token in ("equation", "formula", "latex", "math"))


def _is_layout_image_span(span_type: str) -> bool:
    lowered = str(span_type or "").strip().lower()
    if not lowered:
        return False
    return lowered in {"image", "img", "figure", "picture", "photo"}


def _normalize_layout_image_path(path_value: Any) -> str | None:
    cleaned = _clean_str(path_value if isinstance(path_value, str) else None)
    if not cleaned:
        return None
    if "/" not in cleaned and "\\" not in cleaned:
        return f"images/{cleaned}"
    return cleaned


def _extract_layout_line_items(
    *,
    lines: Any,
    block_type: str,
    block_bbox: Any,
    page_idx: int,
) -> list[dict[str, Any]]:
    out_items: list[dict[str, Any]] = []
    if not isinstance(lines, list):
        return out_items

    fallback_bbox = (
        list(block_bbox)
        if isinstance(block_bbox, list) and len(block_bbox) == 4
        else None
    )

    for line in lines:
        if not isinstance(line, dict):
            continue
        spans = line.get("spans")
        if not isinstance(spans, list) or not spans:
            continue

        line_bbox_raw = line.get("bbox")
        line_bbox = (
            list(line_bbox_raw)
            if isinstance(line_bbox_raw, list) and len(line_bbox_raw) == 4
            else fallback_bbox
        )

        text_parts: list[str] = []
        has_formula_span = False
        line_style = _extract_text_style(line)

        for span in spans:
            if not isinstance(span, dict):
                continue
            span_type = str(span.get("type") or "").strip().lower()
            span_bbox_raw = span.get("bbox")
            span_bbox = (
                list(span_bbox_raw)
                if isinstance(span_bbox_raw, list) and len(span_bbox_raw) == 4
                else line_bbox
            )

            if _is_layout_image_span(span_type):
                normalized_path = _normalize_layout_image_path(
                    span.get("image_path") or span.get("path")
                )
                if normalized_path and span_bbox is not None:
                    out_items.append(
                        {
                            "type": "image",
                            "bbox": list(span_bbox),
                            "page_idx": int(page_idx),
                            "img_path": normalized_path,
                            "bbox_mode": "absolute",
                        }
                    )
                continue

            if span_type == "text" or _is_layout_formula_span(span_type):
                content = span.get("content")
                if isinstance(content, str) and content.strip():
                    text_parts.append(content.strip())
                    if _is_layout_formula_span(span_type):
                        has_formula_span = True
                    span_style = _extract_text_style(span)
                    for key, value in span_style.items():
                        line_style.setdefault(key, value)

        if text_parts and line_bbox is not None:
            line_kind = block_type or "text"
            if has_formula_span and line_kind in {"text", "paragraph", "list"}:
                line_kind = "equation"
            line_item: dict[str, Any] = {
                "type": line_kind,
                "bbox": list(line_bbox),
                "page_idx": int(page_idx),
                "text": "".join(text_parts),
                "bbox_mode": "absolute",
            }
            if line_style:
                line_item.update(line_style)
            out_items.append(line_item)

    return out_items


def _collect_layout_block_items(
    block: Any,
    *,
    page_idx: int,
    out_items: list[dict[str, Any]],
) -> None:
    if not isinstance(block, dict):
        return

    block_type = str(block.get("type") or "").strip().lower()
    bbox = block.get("bbox")
    nested_blocks = block.get("blocks")

    if block_type == "list" and isinstance(nested_blocks, list) and nested_blocks:
        for nested in nested_blocks:
            _collect_layout_block_items(nested, page_idx=page_idx, out_items=out_items)
        return

    line_items = _extract_layout_line_items(
        lines=block.get("lines"),
        block_type=block_type,
        block_bbox=bbox,
        page_idx=page_idx,
    )
    if line_items:
        out_items.extend(line_items)
        return

    direct_image_path = _normalize_layout_image_path(
        block.get("image_path") or block.get("img_path") or block.get("path")
    )
    if direct_image_path and isinstance(bbox, list) and len(bbox) == 4:
        out_items.append(
            {
                "type": "image",
                "bbox": list(bbox),
                "page_idx": int(page_idx),
                "img_path": direct_image_path,
                "bbox_mode": "absolute",
            }
        )
        return

    if isinstance(bbox, list) and len(bbox) == 4:
        direct_text = _extract_text(block)
        if direct_text:
            direct_item: dict[str, Any] = {
                "type": block_type or "text",
                "bbox": list(bbox),
                "page_idx": int(page_idx),
                "text": direct_text,
                "bbox_mode": "absolute",
            }
            block_style = _extract_text_style(block)
            if block_style:
                direct_item.update(block_style)
            out_items.append(direct_item)
            return

    if isinstance(nested_blocks, list):
        for nested in nested_blocks:
            _collect_layout_block_items(nested, page_idx=page_idx, out_items=out_items)


def _extract_content_items_from_layout(layout_payload: Any) -> list[dict[str, Any]]:
    if not isinstance(layout_payload, dict):
        return []

    pdf_info = layout_payload.get("pdf_info")
    if pdf_info is None and isinstance(layout_payload.get("data"), dict):
        pdf_info = layout_payload["data"].get("pdf_info")
    if not isinstance(pdf_info, list):
        return []

    items: list[dict[str, Any]] = []
    for fallback_page_idx, page in enumerate(pdf_info):
        if not isinstance(page, dict):
            continue
        raw_page_idx = page.get("page_idx")
        try:
            page_idx = (
                int(raw_page_idx)
                if raw_page_idx is not None
                else int(fallback_page_idx)
            )
        except Exception:
            page_idx = int(fallback_page_idx)
        para_blocks = page.get("para_blocks")
        if not isinstance(para_blocks, list):
            continue
        for block in para_blocks:
            _collect_layout_block_items(block, page_idx=page_idx, out_items=items)

    return items


# ---- item extraction helpers ----

def _extract_page_idx(item: dict[str, Any], *, fallback: int = 0) -> int:
    for key in ("page_idx", "page_index", "page"):
        if key in item:
            try:
                return int(item[key])
            except Exception:
                continue
    return int(fallback)


def _collect_text_fragments(value: Any, fragments: list[str]) -> None:
    if isinstance(value, str):
        text = value.strip()
        if text:
            fragments.append(text)
        return

    if isinstance(value, list):
        for row in value:
            _collect_text_fragments(row, fragments)
        return

    if not isinstance(value, dict):
        return

    for key, nested in value.items():
        key_lower = str(key).strip().lower()
        if key_lower in {
            "bbox", "poly", "page_idx", "page_index", "page",
            "id", "index", "level", "text_level",
            "type", "sub_type", "list_type", "item_type",
            "img_path", "image_path", "image_source",
        }:
            continue
        _collect_text_fragments(nested, fragments)


def _join_text_fragments(fragments: list[str]) -> str:
    seen: set[str] = set()
    deduped: list[str] = []
    for part in fragments:
        normalized = part.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return "\n".join(deduped)


def _extract_text(item: dict[str, Any]) -> str:
    for key in ("text", "content", "latex"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    content = item.get("content")
    if isinstance(content, (list, dict)):
        parts: list[str] = []
        _collect_text_fragments(content, parts)
        merged = _join_text_fragments(parts)
        if merged:
            return merged

    list_items = item.get("list_items")
    if isinstance(list_items, list):
        parts: list[str] = []
        _collect_text_fragments(list_items, parts)
        merged = _join_text_fragments(parts)
        if merged:
            return merged

    list_items = item.get("list_item_infos")
    if isinstance(list_items, list):
        parts: list[str] = []
        for row in list_items:
            if not isinstance(row, dict):
                continue
            text = row.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
        if parts:
            return _join_text_fragments(parts)

    table_body = item.get("table_body")
    if isinstance(table_body, str) and table_body.strip():
        return table_body.strip()

    return ""


def _extract_bbox(item: dict[str, Any]) -> tuple[float, float, float, float] | None:
    bbox = item.get("bbox")
    if isinstance(bbox, list) and len(bbox) == 4:
        try:
            x0 = float(bbox[0])
            y0 = float(bbox[1])
            x1 = float(bbox[2])
            y1 = float(bbox[3])
            return (x0, y0, x1, y1)
        except Exception:
            return None

    poly = item.get("poly")
    if isinstance(poly, list) and len(poly) >= 8:
        coords: list[float] = []
        for value in poly:
            try:
                coords.append(float(value))
            except Exception:
                return None
        xs = coords[0::2]
        ys = coords[1::2]
        if not xs or not ys:
            return None
        return (min(xs), min(ys), max(xs), max(ys))

    return None


def _extract_item_kind(item: dict[str, Any]) -> str:
    for key in (
        "type", "category_type", "block_type", "kind", "tag", "content_type",
    ):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    return ""


def _extract_image_rel_path(item: dict[str, Any]) -> str | None:
    for key in ("img_path", "image_path", "path"):
        value = item.get(key)
        cleaned = _clean_str(value if isinstance(value, str) else None)
        if cleaned:
            return cleaned

    content = item.get("content")
    if isinstance(content, dict):
        image_source = content.get("image_source")
        if isinstance(image_source, dict):
            for key in ("path", "img_path", "image_path", "url"):
                value = image_source.get(key)
                cleaned = _clean_str(value if isinstance(value, str) else None)
                if cleaned:
                    return cleaned
        if isinstance(image_source, str):
            cleaned = _clean_str(image_source)
            if cleaned:
                return cleaned

    return None


# ---- geometry / image helpers ----

def _crop_pdf_region_png(
    *,
    doc: pymupdf.Document,
    page_index: int,
    bbox_pt: list[float],
    out_path: Path,
    zoom: float = 2.0,
) -> bool:
    if page_index < 0 or page_index >= int(doc.page_count or 0):
        return False

    try:
        x0, y0, x1, y1 = (
            float(bbox_pt[0]), float(bbox_pt[1]),
            float(bbox_pt[2]), float(bbox_pt[3]),
        )
    except Exception:
        return False
    if x1 <= x0 or y1 <= y0:
        return False

    page = doc.load_page(page_index)
    clip = pymupdf.Rect(x0, y0, x1, y1) & page.rect
    if clip.is_empty or clip.width <= 1.0 or clip.height <= 1.0:
        return False

    out_path.parent.mkdir(parents=True, exist_ok=True)
    pix = page.get_pixmap(  # type: ignore[attr-defined]
        matrix=pymupdf.Matrix(float(zoom), float(zoom)),
        clip=clip,
        alpha=False,
    )
    pix.save(str(out_path))
    return True


def _bbox_to_page_pt(
    bbox: tuple[float, float, float, float],
    *,
    page_width_pt: float,
    page_height_pt: float,
    assume_normalized: bool | None = None,
) -> list[float] | None:
    x0, y0, x1, y1 = bbox

    should_normalize = False
    if assume_normalized is True:
        should_normalize = True
    elif assume_normalized is None:
        should_normalize = max(abs(x0), abs(y0), abs(x1), abs(y1)) <= 1100.0

    if should_normalize:
        x0 = (x0 / 1000.0) * page_width_pt
        x1 = (x1 / 1000.0) * page_width_pt
        y0 = (y0 / 1000.0) * page_height_pt
        y1 = (y1 / 1000.0) * page_height_pt

    left = max(0.0, min(float(x0), float(x1)))
    right = min(float(page_width_pt), max(float(x0), float(x1)))
    top = max(0.0, min(float(y0), float(y1)))
    bottom = min(float(page_height_pt), max(float(y0), float(y1)))

    if right <= left or bottom <= top:
        return None
    return [left, top, right, bottom]


# ---- quality estimation ----

def _estimate_content_items_quality(items: list[dict[str, Any]]) -> tuple[int, int]:
    usable_count = 0
    score = 0
    for item in items:
        bbox = _extract_bbox(item)
        if bbox is None:
            continue
        usable_count += 1
        kind = _extract_item_kind(item)
        text = _extract_text(item)
        if text and not _is_image_like_kind(kind):
            score += 4
            text_len = len(text.replace("\n", "").strip())
            bbox_h = abs(float(bbox[3]) - float(bbox[1]))
            if text_len <= 100:
                score += 1
            elif text_len >= 500:
                score -= 2
            elif text_len >= 240:
                score -= 1
            if bbox_h <= 30.0:
                score += 2
            elif bbox_h <= 55.0:
                score += 1
            elif bbox_h >= 110.0:
                score -= 2
            elif bbox_h >= 75.0:
                score -= 1
            continue
        if _is_image_like_kind(kind):
            if _extract_image_rel_path(item):
                score += 3
            else:
                score += 2
            continue
        score += 1
    return (usable_count, score)


def _estimate_text_bbox_stats(items: list[dict[str, Any]]) -> dict[str, float] | None:
    heights: list[float] = []
    for item in items:
        kind = _extract_item_kind(item)
        if _is_image_like_kind(kind):
            continue
        text = _extract_text(item)
        if not text:
            continue
        bbox = _extract_bbox(item)
        if bbox is None:
            continue
        h = abs(float(bbox[3]) - float(bbox[1]))
        if h > 0:
            heights.append(h)

    if not heights:
        return None

    heights.sort()
    mid = len(heights) // 2
    p90_idx = int(round((len(heights) - 1) * 0.9))
    p90_idx = max(0, min(p90_idx, len(heights) - 1))
    return {
        "count": float(len(heights)),
        "median_h": float(heights[mid]),
        "p90_h": float(heights[p90_idx]),
    }


def _should_prefer_layout_candidate(
    *,
    content_items: list[dict[str, Any]],
    content_score: tuple[int, int],
    layout_items: list[dict[str, Any]],
    layout_score: tuple[int, int],
) -> bool:
    if layout_score > content_score:
        return True

    score_gap = int(content_score[1]) - int(layout_score[1])
    usable_gap = int(content_score[0]) - int(layout_score[0])
    if score_gap > 8 or usable_gap > 2:
        return False

    content_stats = _estimate_text_bbox_stats(content_items)
    layout_stats = _estimate_text_bbox_stats(layout_items)
    if content_stats is None or layout_stats is None:
        return False

    content_median = max(1.0, float(content_stats["median_h"]))
    layout_median = max(1.0, float(layout_stats["median_h"]))
    content_p90 = max(1.0, float(content_stats["p90_h"]))
    layout_p90 = max(1.0, float(layout_stats["p90_h"]))

    return layout_median <= (0.82 * content_median) and layout_p90 <= (
        0.88 * content_p90
    )


# ---- footer helpers ----

def _normalize_footer_brand_text(text: str) -> str:
    return "".join(ch.lower() for ch in str(text or "") if ch.isalnum())


def _is_notebooklm_footer_brand_text(text: str) -> bool:
    normalized = _normalize_footer_brand_text(text)
    if not normalized or "notebooklm" not in normalized:
        return False
    extra = normalized.replace("notebooklm", "")
    return len(extra) <= 24



