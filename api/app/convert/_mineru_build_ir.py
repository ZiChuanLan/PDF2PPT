# pyright: reportMissingImports=false

"""MinerU IR builder — builds the intermediate representation from extracted items."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pymupdf

from app.utils.text import clean_str as _clean_str

from ._adapter_utils import _IMAGE_KIND_TOKENS, _is_image_like_kind
from ._mineru_extract import (
    _DEFAULT_PAGE_HEIGHT_PT,
    _DEFAULT_PAGE_WIDTH_PT,
    _bbox_to_page_pt,
    _crop_pdf_region_png,
    _extract_bbox,
    _extract_image_rel_path,
    _extract_item_kind,
    _extract_page_idx,
    _extract_text,
    _extract_text_style,
    _is_notebooklm_footer_brand_text,
    _normalize_footer_brand_text,
)


# ── primary IR builder ───────────────────────────────────────────────────────


def _build_ir_from_mineru_outputs(
    *,
    source_pdf: Path,
    content_items: list[dict[str, Any]],
    page_sizes: dict[int, tuple[float, float]],
    page_start: int | None = None,
    page_end: int | None = None,
    image_output_dir: Path | None = None,
    image_path_prefix: str | None = None,
    mineru_result_dir: Path | None = None,
    mineru_result_path_prefix: str | None = None,
    layout_source: str = "mineru",
    warning_prefix: str = "mineru",
) -> dict[str, Any]:
    item_page_pairs: list[tuple[dict[str, Any], int]] = [
        (item, _extract_page_idx(item, fallback=idx))
        for idx, item in enumerate(content_items)
    ]
    raw_indices = [page_idx for _, page_idx in item_page_pairs]

    page_index_shift = 0
    if raw_indices:
        target_start: int | None = None
        target_end: int | None = None
        if page_start is not None and page_end is not None:
            target_start = int(page_start) - 1
            target_end = int(page_end) - 1
        page_size_keys = set(page_sizes.keys())

        candidate_shifts: set[int] = {0, -1, 1}
        if target_start is not None:
            # MinerU may re-index selected page ranges to start from 0 (or 1).
            candidate_shifts.add(int(target_start))
            candidate_shifts.add(int(target_start - 1))

        best_key: tuple[int, int, int, int, int] | None = None
        best_shift = 0
        for shift in sorted(candidate_shifts):
            adjusted = [int(idx + shift) for idx in raw_indices]
            in_range_hits = (
                sum(
                    1
                    for idx in adjusted
                    if target_start is not None
                    and target_end is not None
                    and target_start <= idx <= target_end
                )
                if target_start is not None and target_end is not None
                else 0
            )
            page_size_hits = (
                sum(1 for idx in adjusted if idx in page_size_keys)
                if page_size_keys
                else 0
            )
            non_negative_hits = sum(1 for idx in adjusted if idx >= 0)
            prefer_zero = 1 if shift == 0 else 0
            key = (
                int(in_range_hits),
                int(page_size_hits),
                int(non_negative_hits),
                int(prefer_zero),
                int(-abs(int(shift))),
            )
            if best_key is None or key > best_key:
                best_key = key
                best_shift = int(shift)

        page_index_shift = int(best_shift)

    items_by_page: dict[int, list[dict[str, Any]]] = {}
    for item, raw_page_idx in item_page_pairs:
        page_idx = int(raw_page_idx + page_index_shift)
        if page_idx < 0:
            continue
        items_by_page.setdefault(page_idx, []).append(item)

    ordered_indices = sorted(items_by_page.keys())
    if not ordered_indices:
        if page_start is not None and page_end is not None:
            start_idx = int(page_start) - 1
            end_idx = int(page_end) - 1
            ordered_indices = [idx for idx in range(start_idx, end_idx + 1) if idx >= 0]
        elif page_sizes:
            ordered_indices = sorted(page_sizes.keys())
        else:
            ordered_indices = [0]

    if page_start is not None and page_end is not None:
        start_idx = int(page_start) - 1
        end_idx = int(page_end) - 1
        ordered_indices = [
            idx for idx in ordered_indices if start_idx <= idx <= end_idx
        ]
        if not ordered_indices:
            ordered_indices = [idx for idx in range(start_idx, end_idx + 1) if idx >= 0]

    if not ordered_indices:
        if page_sizes:
            ordered_indices = sorted(page_sizes.keys())
        else:
            ordered_indices = [0]

    pages: list[dict[str, Any]] = []
    ir_warnings: list[str] = []
    image_prefix = _clean_str(image_path_prefix) or "images"
    result_prefix = _clean_str(mineru_result_path_prefix) or ""

    pdf_doc: pymupdf.Document | None = None
    if image_output_dir is not None and source_pdf.exists():
        try:
            pdf_doc = pymupdf.open(str(source_pdf))
        except Exception:
            pdf_doc = None

    image_counter = 0

    try:
        for page_idx in ordered_indices:
            page_w, page_h = page_sizes.get(
                page_idx, (_DEFAULT_PAGE_WIDTH_PT, _DEFAULT_PAGE_HEIGHT_PT)
            )
            page_items = items_by_page.get(page_idx, [])

            elements: list[dict[str, Any]] = []
            dropped_items = 0
            for item in page_items:
                kind = _extract_item_kind(item)
                bbox = _extract_bbox(item)
                if bbox is None:
                    dropped_items += 1
                    continue
                bbox_mode = str(item.get("bbox_mode") or "").strip().lower()
                assume_normalized: bool | None = None
                if bbox_mode == "absolute":
                    assume_normalized = False
                elif bbox_mode == "normalized":
                    assume_normalized = True
                bbox_pt = _bbox_to_page_pt(
                    bbox,
                    page_width_pt=float(page_w),
                    page_height_pt=float(page_h),
                    assume_normalized=assume_normalized,
                )
                if bbox_pt is None:
                    dropped_items += 1
                    continue

                text = _extract_text(item)
                if text and not _is_image_like_kind(kind):
                    text_element: dict[str, Any] = {
                        "type": "text",
                        "bbox_pt": bbox_pt,
                        "text": text,
                        "source": layout_source,
                        "mineru_block_type": kind,
                    }
                    text_style = _extract_text_style(item)
                    if text_style:
                        text_element.update(text_style)
                    text_level_raw = item.get("text_level")
                    if text_level_raw is not None:
                        try:
                            text_level = int(text_level_raw)
                            if text_level > 0:
                                text_element["mineru_text_level"] = text_level
                        except Exception:
                            pass
                    elements.append(text_element)
                    continue

                if _is_image_like_kind(kind):
                    rel_image_path = _extract_image_rel_path(item)
                    if (
                        rel_image_path
                        and mineru_result_dir is not None
                        and result_prefix
                    ):
                        image_added = False
                        candidate_paths: list[Path] = []
                        rel_path_obj = Path(rel_image_path)
                        if (
                            not rel_path_obj.is_absolute()
                            and ".." not in rel_path_obj.parts
                        ):
                            candidate_paths.append(rel_path_obj)
                            if len(rel_path_obj.parts) <= 1:
                                candidate_paths.append(
                                    Path("images") / rel_path_obj.name
                                )

                        if rel_image_path.startswith(("http://", "https://")):
                            file_name = rel_image_path.rsplit("/", 1)[-1].strip()
                            if file_name:
                                candidate_paths.append(Path("images") / file_name)

                        seen_candidate: set[str] = set()
                        for candidate_rel in candidate_paths:
                            key = candidate_rel.as_posix()
                            if key in seen_candidate:
                                continue
                            seen_candidate.add(key)
                            resolved = (mineru_result_dir / candidate_rel).resolve()
                            try:
                                resolved.relative_to(mineru_result_dir.resolve())
                                within_root = True
                            except Exception:
                                within_root = False
                            if not within_root:
                                continue
                            if not (resolved.exists() and resolved.is_file()):
                                continue
                            normalized_rel = candidate_rel.as_posix().lstrip("./")
                            elements.append(
                                {
                                    "type": "image",
                                    "bbox_pt": bbox_pt,
                                    "image_path": f"{result_prefix}/{normalized_rel}",
                                    "source": layout_source,
                                }
                            )
                            image_added = True
                            break
                        if image_added:
                            continue

                if (
                    _is_image_like_kind(kind)
                    and image_output_dir is not None
                    and pdf_doc is not None
                ):
                    image_counter += 1
                    image_name = (
                        f"page-{int(page_idx):04d}-img-{int(image_counter):04d}.png"
                    )
                    image_abs_path = image_output_dir / image_name
                    try:
                        saved = _crop_pdf_region_png(
                            doc=pdf_doc,
                            page_index=int(page_idx),
                            bbox_pt=bbox_pt,
                            out_path=image_abs_path,
                            zoom=2.0,
                        )
                    except Exception:
                        saved = False
                    if saved:
                        elements.append(
                            {
                                "type": "image",
                                "bbox_pt": bbox_pt,
                                "image_path": f"{image_prefix}/{image_name}",
                                "mime": "image/png",
                                "source": layout_source,
                            }
                        )

            elements.sort(key=lambda item: (item["bbox_pt"][1], item["bbox_pt"][0]))
            page_warnings: list[str] = []
            if dropped_items:
                page_warnings.append(f"{warning_prefix}_items_dropped={dropped_items}")
            if not elements:
                page_warnings.append(f"{warning_prefix}_no_elements")
            has_text_like_elements = any(
                str(el.get("type") or "").strip().lower() in {"text", "table"}
                for el in elements
            )

            pages.append(
                {
                    "page_index": int(page_idx),
                    "page_width_pt": float(page_w),
                    "page_height_pt": float(page_h),
                    "rotation": 0,
                    "elements": elements,
                    "warnings": page_warnings,
                    # Use direct placement path when MinerU blocks are available.
                    # If a page has no elements, fallback to scanned-page render path
                    # so the slide is never blank.
                    "has_text_layer": bool(has_text_like_elements),
                    "ocr_used": any(el.get("type") == "text" for el in elements),
                }
            )
    finally:
        if pdf_doc is not None:
            pdf_doc.close()

    pages.sort(key=lambda page: int(page.get("page_index") or 0))
    if not pages:
        ir_warnings.append(f"{warning_prefix}_no_pages")
    if page_index_shift:
        ir_warnings.append(f"{warning_prefix}_page_index_shift={page_index_shift}")

    source_page_count = len(page_sizes) if page_sizes else len(pages)
    selected_start = (
        int(page_start)
        if page_start is not None
        else (pages[0]["page_index"] + 1 if pages else 1)
    )
    selected_end = (
        int(page_end)
        if page_end is not None
        else (pages[-1]["page_index"] + 1 if pages else selected_start)
    )

    return {
        "source_pdf": str(source_pdf),
        "page_count": len(pages),
        "source_page_count": max(0, int(source_page_count)),
        "page_start": selected_start,
        "page_end": selected_end,
        "pages": pages,
        "warnings": ir_warnings,
    }


# ── NotebookLM footer recovery (re-used by baidu_doc_adapter) ────────────────


def _is_notebooklm_footer_ir_element(
    el: dict[str, Any],
    *,
    page_w_pt: float,
    page_h_pt: float,
) -> bool:
    text = _extract_text(el).strip()
    if not _is_notebooklm_footer_brand_text(text):
        return False

    bbox = el.get("bbox_pt")
    if not isinstance(bbox, list) or len(bbox) != 4:
        return False

    try:
        x0 = float(bbox[0])
        y0 = float(bbox[1])
        x1 = float(bbox[2])
        y1 = float(bbox[3])
    except Exception:
        return False

    if x1 <= x0 or y1 <= y0 or page_w_pt <= 0.0 or page_h_pt <= 0.0:
        return False

    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0
    width_ratio = float(x1 - x0) / float(page_w_pt)
    height_ratio = float(y1 - y0) / float(page_h_pt)
    return (
        cy >= (0.84 * float(page_h_pt))
        and cx >= (0.72 * float(page_w_pt))
        and width_ratio <= 0.22
        and height_ratio <= 0.08
    )


def _footer_elements_match(
    existing: dict[str, Any],
    candidate: dict[str, Any],
) -> bool:
    existing_bbox = existing.get("bbox_pt")
    candidate_bbox = candidate.get("bbox_pt")
    if (
        not isinstance(existing_bbox, list)
        or len(existing_bbox) != 4
        or not isinstance(candidate_bbox, list)
        or len(candidate_bbox) != 4
    ):
        return False

    existing_text = _normalize_footer_brand_text(_extract_text(existing))
    candidate_text = _normalize_footer_brand_text(_extract_text(candidate))
    if existing_text and candidate_text and existing_text != candidate_text:
        return False

    try:
        ex0, ey0, ex1, ey1 = [float(v) for v in existing_bbox]
        cx0, cy0, cx1, cy1 = [float(v) for v in candidate_bbox]
    except Exception:
        return False

    inter_left = max(ex0, cx0)
    inter_top = max(ey0, cy0)
    inter_right = min(ex1, cx1)
    inter_bottom = min(ey1, cy1)
    inter_w = max(0.0, inter_right - inter_left)
    inter_h = max(0.0, inter_bottom - inter_top)
    inter_area = inter_w * inter_h
    if inter_area <= 0.0:
        return False

    existing_area = max(1.0, (ex1 - ex0) * (ey1 - ey0))
    candidate_area = max(1.0, (cx1 - cx0) * (cy1 - cy0))
    overlap_existing = inter_area / existing_area
    overlap_candidate = inter_area / candidate_area
    return overlap_existing >= 0.55 or overlap_candidate >= 0.55


def _recover_missing_notebooklm_footer_elements(
    *,
    ir: dict[str, Any],
    content_items: list[dict[str, Any]],
    source_pdf: Path,
    page_sizes: dict[int, tuple[float, float]],
    page_start: int | None = None,
    page_end: int | None = None,
) -> int:
    footer_candidates = [
        item
        for item in content_items
        if _is_notebooklm_footer_brand_text(_extract_text(item))
        and _extract_bbox(item) is not None
    ]
    if not footer_candidates:
        return 0

    footer_ir = _build_ir_from_mineru_outputs(
        source_pdf=source_pdf,
        content_items=footer_candidates,
        page_sizes=page_sizes,
        page_start=page_start,
        page_end=page_end,
        image_output_dir=None,
        image_path_prefix=None,
        mineru_result_dir=None,
        mineru_result_path_prefix=None,
    )

    pages = [page for page in (ir.get("pages") or []) if isinstance(page, dict)]
    pages_by_index = {int(page.get("page_index") or 0): page for page in pages}
    recovered = 0

    for footer_page in footer_ir.get("pages") or []:
        if not isinstance(footer_page, dict):
            continue
        page_index = int(footer_page.get("page_index") or 0)
        target_page = pages_by_index.get(page_index)
        if target_page is None:
            continue
        page_w_pt = float(target_page.get("page_width_pt") or 0.0)
        page_h_pt = float(target_page.get("page_height_pt") or 0.0)
        target_elements = [
            el for el in (target_page.get("elements") or []) if isinstance(el, dict)
        ]

        for candidate in footer_page.get("elements") or []:
            if not isinstance(candidate, dict):
                continue
            if str(candidate.get("type") or "").strip().lower() != "text":
                continue
            if not _is_notebooklm_footer_ir_element(
                candidate,
                page_w_pt=page_w_pt,
                page_h_pt=page_h_pt,
            ):
                continue
            if any(
                _is_notebooklm_footer_ir_element(
                    existing,
                    page_w_pt=page_w_pt,
                    page_h_pt=page_h_pt,
                )
                and _footer_elements_match(existing, candidate)
                for existing in target_elements
            ):
                continue
            target_elements.append(dict(candidate))
            recovered += 1

        target_elements.sort(
            key=lambda item: (
                float(((item.get("bbox_pt") or [0.0, 0.0, 0.0, 0.0])[1])),
                float(((item.get("bbox_pt") or [0.0, 0.0, 0.0, 0.0])[0])),
            )
        )
        target_page["elements"] = target_elements
        target_page["has_text_layer"] = any(
            str(el.get("type") or "").strip().lower() in {"text", "table"}
            for el in target_elements
        )
        target_page["ocr_used"] = any(el.get("type") == "text" for el in target_elements)

    return recovered
