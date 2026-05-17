"""Scanned-page image region building, merging, and assembly."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from ._scanned_erase import _try_make_crop_background_transparent
from ._scanned_region_detect import (
    _analyze_shape_crop,
    _coerce_polygon_points_pt,
    _is_shape_confirmed_crop,
    _pdf_pt_to_pix_px,
    _polygon_points_pt_to_px,
)
from ._scanned_render import _apply_max_filter_l
from .bbox_utils import (
    _bbox_intersection_area_pt,
    _bbox_iou_pt,
    _coerce_bbox_pt,
    _compute_text_erase_padding_pt,
    _ensure_parent_dir,
    _texts_similar_for_bbox_dedupe,
)
from .constants import _PTS_PER_INCH
from .font_utils import (
    _compact_text_length,
    _contains_cjk,
    _is_inline_short_token,
)
from .slide_builder import _iter_page_elements


def _coerce_image_region_entry_pt(value: Any) -> dict[str, Any] | None:
    raw_bbox = value.get("bbox_pt") if isinstance(value, dict) else value
    if raw_bbox is None and isinstance(value, dict):
        raw_bbox = value.get("bbox")
    try:
        bbox_pt = [float(v) for v in _coerce_bbox_pt(raw_bbox)]
    except Exception:
        return None

    out: dict[str, Any] = {"bbox_pt": bbox_pt}
    if not isinstance(value, dict):
        return out

    for key in ("label", "score", "order", "geometry_source"):
        if value.get(key) is not None:
            out[key] = value.get(key)

    geometry_kind = str(value.get("geometry_kind") or "").strip().lower()
    raw_points = value.get("geometry_points_pt")
    if raw_points is None:
        raw_points = value.get("geometry_points")
    points = _coerce_polygon_points_pt(raw_points)
    if points is not None:
        out["geometry_kind"] = "polygon"
        out["geometry_points_pt"] = [[float(x), float(y)] for x, y in points]
    elif geometry_kind:
        out["geometry_kind"] = geometry_kind

    return out


@dataclass
class _ScannedImageRegionInfo:
    bbox_pt: list[float]
    suppress_bbox_pt: list[float]
    crop_path: Path
    shape_confirmed: bool
    ai_hint: bool = False
    background_removed: bool = False
    geometry_kind: str | None = None
    geometry_points_pt: list[list[float]] | None = None


def _geometry_points_signature(
    points: list[list[float]] | None,
) -> tuple[tuple[int, int], ...]:
    if not isinstance(points, list):
        return ()
    signature: list[tuple[int, int]] = []
    for point in points:
        if not isinstance(point, list) or len(point) < 2:
            return ()
        try:
            signature.append(
                (
                    int(round(float(point[0]) * 10.0)),
                    int(round(float(point[1]) * 10.0)),
                )
            )
        except Exception:
            return ()
    return tuple(signature)


def _project_polygon_points_pt_to_local_crop(
    points_pt: list[list[float]] | None,
    *,
    crop_x0_px: int,
    crop_y0_px: int,
    crop_width_px: int,
    crop_height_px: int,
    page_h_pt: float,
    scanned_render_dpi: int,
    image_width_px: int,
    image_height_px: int,
) -> list[tuple[int, int]] | None:
    if not points_pt or crop_width_px <= 0 or crop_height_px <= 0:
        return None

    polygon_px = _polygon_points_pt_to_px(
        points_pt,
        page_height_pt=page_h_pt,
        dpi=int(scanned_render_dpi),
        width_px=int(image_width_px),
        height_px=int(image_height_px),
    )
    if polygon_px is None:
        return None

    local_points: list[tuple[int, int]] = []
    for px, py in polygon_px:
        coord = (
            max(0, min(int(crop_width_px - 1), int(px - crop_x0_px))),
            max(0, min(int(crop_height_px - 1), int(py - crop_y0_px))),
        )
        if local_points and coord == local_points[-1]:
            continue
        local_points.append(coord)

    if len({point for point in local_points}) < 3:
        return None
    return local_points


def _project_bbox_pt_to_local_crop_rect(
    bbox_pt: list[float],
    *,
    crop_x0_px: int,
    crop_y0_px: int,
    crop_width_px: int,
    crop_height_px: int,
    page_h_pt: float,
    scanned_render_dpi: int,
    pad_x_pt: float = 0.0,
    pad_y_pt: float = 0.0,
) -> tuple[int, int, int, int] | None:
    try:
        x0, y0, x1, y1 = _coerce_bbox_pt(bbox_pt)
    except Exception:
        return None

    x0p, y0p = _pdf_pt_to_pix_px(
        x0 - float(pad_x_pt),
        y0 - float(pad_y_pt),
        page_height_pt=page_h_pt,
        dpi=int(scanned_render_dpi),
    )
    x1p, y1p = _pdf_pt_to_pix_px(
        x1 + float(pad_x_pt),
        y1 + float(pad_y_pt),
        page_height_pt=page_h_pt,
        dpi=int(scanned_render_dpi),
    )

    lx0 = max(0, min(int(crop_width_px - 1), int(math.floor(x0p - crop_x0_px))))
    ly0 = max(0, min(int(crop_height_px - 1), int(math.floor(y0p - crop_y0_px))))
    lx1 = max(0, min(int(crop_width_px), int(math.ceil(x1p - crop_x0_px))))
    ly1 = max(0, min(int(crop_height_px), int(math.ceil(y1p - crop_y0_px))))
    if lx1 <= lx0 or ly1 <= ly0:
        return None
    return (lx0, ly0, lx1, ly1)


def _save_scanned_image_region_crop(
    *,
    img: Any,
    bbox_pt: list[float],
    crop_out_path: Path,
    page_h_pt: float,
    scanned_render_dpi: int,
    geometry_points_pt: list[list[float]] | None = None,
    exclude_bboxes_pt: list[list[float]] | None = None,
    exclude_polygons_pt: list[list[list[float]]] | None = None,
    expand_pt: float = 0.0,
) -> bool:
    try:
        from PIL import Image, ImageChops, ImageDraw
    except Exception:
        return False

    try:
        x0, y0, x1, y1 = _coerce_bbox_pt(bbox_pt)
    except Exception:
        return False

    # Expand crop bbox by a small margin (used for polygon-backed regions
    # where the mask makes extra pixels transparent anyway).
    if expand_pt > 0.0:
        x0 -= expand_pt
        y0 -= expand_pt
        x1 += expand_pt
        y1 += expand_pt

    x0p, y0p = _pdf_pt_to_pix_px(
        x0,
        y0,
        page_height_pt=page_h_pt,
        dpi=int(scanned_render_dpi),
    )
    x1p, y1p = _pdf_pt_to_pix_px(
        x1,
        y1,
        page_height_pt=page_h_pt,
        dpi=int(scanned_render_dpi),
    )
    x0p = max(0, min(int(img.width - 1), int(x0p)))
    y0p = max(0, min(int(img.height - 1), int(y0p)))
    x1p = max(0, min(int(img.width), int(x1p)))
    y1p = max(0, min(int(img.height), int(y1p)))
    if x1p <= x0p or y1p <= y0p:
        return False

    crop = img.crop((x0p, y0p, x1p, y1p))
    local_polygon_points = _project_polygon_points_pt_to_local_crop(
        geometry_points_pt,
        crop_x0_px=x0p,
        crop_y0_px=y0p,
        crop_width_px=int(crop.width),
        crop_height_px=int(crop.height),
        page_h_pt=page_h_pt,
        scanned_render_dpi=int(scanned_render_dpi),
        image_width_px=int(img.width),
        image_height_px=int(img.height),
    )
    has_text_cutouts = bool(exclude_bboxes_pt) or bool(exclude_polygons_pt)
    if local_polygon_points is not None or has_text_cutouts:
        crop = crop.convert("RGBA")
        mask = crop.getchannel("A")
        if local_polygon_points is not None:
            mask.paste(0, (0, 0, crop.width, crop.height))
            ImageDraw.Draw(mask).polygon(local_polygon_points, fill=255)
            mask = _apply_max_filter_l(mask, size=3)
        else:
            mask.paste(255, (0, 0, crop.width, crop.height))

        if has_text_cutouts:
            cutout_mask = Image.new("L", (crop.width, crop.height), 0)
            draw_cutout = ImageDraw.Draw(cutout_mask)

            for points_pt in exclude_polygons_pt or []:
                local_points = _project_polygon_points_pt_to_local_crop(
                    points_pt,
                    crop_x0_px=x0p,
                    crop_y0_px=y0p,
                    crop_width_px=int(crop.width),
                    crop_height_px=int(crop.height),
                    page_h_pt=page_h_pt,
                    scanned_render_dpi=int(scanned_render_dpi),
                    image_width_px=int(img.width),
                    image_height_px=int(img.height),
                )
                if local_points is None:
                    continue
                draw_cutout.polygon(local_points, fill=255)

            for text_bbox_pt in exclude_bboxes_pt or []:
                try:
                    tx0, ty0, tx1, ty1 = _coerce_bbox_pt(text_bbox_pt)
                except Exception:
                    continue
                bbox_h_pt = max(1.0, float(ty1 - ty0))
                pad_x_pt, pad_y_pt = _compute_text_erase_padding_pt(
                    bbox_h_pt=bbox_h_pt,
                    text_erase_mode="fill",
                )
                local_rect = _project_bbox_pt_to_local_crop_rect(
                    [tx0, ty0, tx1, ty1],
                    crop_x0_px=x0p,
                    crop_y0_px=y0p,
                    crop_width_px=int(crop.width),
                    crop_height_px=int(crop.height),
                    page_h_pt=page_h_pt,
                    scanned_render_dpi=int(scanned_render_dpi),
                    pad_x_pt=pad_x_pt,
                    pad_y_pt=pad_y_pt,
                )
                if local_rect is None:
                    continue
                lx0, ly0, lx1, ly1 = local_rect
                draw_cutout.rectangle(
                    [lx0, ly0, max(lx0, lx1 - 1), max(ly0, ly1 - 1)],
                    fill=255,
                )

            cutout_mask = _apply_max_filter_l(cutout_mask, size=3)
            mask = ImageChops.subtract(mask, cutout_mask)

        crop.putalpha(mask)

    try:
        _ensure_parent_dir(crop_out_path)
        crop.save(crop_out_path)
        return True
    except Exception:
        return False


def _build_scanned_image_region_suppress_bbox(
    bbox_pt: list[float],
    *,
    page_w_pt: float,
    page_h_pt: float,
    shape_confirmed: bool,
) -> list[float]:
    x0, y0, x1, y1 = _coerce_bbox_pt(bbox_pt)
    w_pt = float(x1 - x0)
    h_pt = float(y1 - y0)
    if shape_confirmed:
        pad_x = max(1.5, min(8.0, 0.05 * w_pt))
        pad_y = max(1.0, min(6.0, 0.07 * h_pt))
    else:
        pad_x = max(0.8, min(3.5, 0.02 * w_pt))
        pad_y = max(0.8, min(3.0, 0.03 * h_pt))
    return [
        max(0.0, float(x0) - pad_x),
        max(0.0, float(y0) - pad_y),
        min(float(page_w_pt), float(x1) + pad_x),
        min(float(page_h_pt), float(y1) + pad_y),
    ]


def _tighten_scanned_image_region_bbox_by_visual_bounds(
    *,
    img: Any,
    bbox_pt: list[float],
    page_w_pt: float,
    page_h_pt: float,
    scanned_render_dpi: int,
    shape_confirmed: bool,
    ocr_text_elements: list[dict[str, Any]] | None = None,
) -> list[float] | None:
    """Best-effort tighten for image crops with excessive blank margins."""

    try:
        from PIL import ImageFilter
    except Exception:
        return None

    try:
        x0, y0, x1, y1 = _coerce_bbox_pt(bbox_pt)
    except Exception:
        return None

    if float(x1 - x0) <= 0.0 or float(y1 - y0) <= 0.0:
        return None

    x0p, y0p = _pdf_pt_to_pix_px(
        x0,
        y0,
        page_height_pt=page_h_pt,
        dpi=int(scanned_render_dpi),
    )
    x1p, y1p = _pdf_pt_to_pix_px(
        x1,
        y1,
        page_height_pt=page_h_pt,
        dpi=int(scanned_render_dpi),
    )
    x0p = max(0, min(int(img.width - 1), int(x0p)))
    y0p = max(0, min(int(img.height - 1), int(y0p)))
    x1p = max(0, min(int(img.width), int(x1p)))
    y1p = max(0, min(int(img.height), int(y1p)))
    if x1p <= x0p or y1p <= y0p:
        return None

    try:
        crop = img.crop((x0p, y0p, x1p, y1p)).convert("L")
    except Exception:
        return None

    w = int(crop.width)
    h = int(crop.height)
    if w < 40 or h < 40:
        return None

    arr = np.asarray(crop, dtype=np.uint8)
    if arr.ndim != 2 or arr.size <= 0:
        return None

    ring = max(3, min(14, int(round(0.05 * float(min(w, h))))))
    border_vals = np.concatenate(
        [
            arr[:ring, :].reshape(-1),
            arr[max(0, h - ring) :, :].reshape(-1),
            arr[:, :ring].reshape(-1),
            arr[:, max(0, w - ring) :].reshape(-1),
        ]
    )
    if border_vals.size <= 0:
        return None

    bg = float(np.median(border_vals))
    diff = np.abs(arr.astype(np.int16) - int(round(bg)))

    edges_img = crop.filter(ImageFilter.FIND_EDGES)
    edges = np.asarray(edges_img, dtype=np.uint8)
    if edges.shape != arr.shape:
        return None

    diff_thresh = 18.0 if bg >= 150.0 else 22.0
    edge_thresh = 24 if shape_confirmed else 28
    mask = (edges >= edge_thresh) | (diff >= diff_thresh)

    if ocr_text_elements:
        overlap_boxes: list[tuple[int, int, int, int]] = []
        overlap_cov = 0.0
        crop_area = max(1.0, float(x1 - x0) * float(y1 - y0))
        for el in ocr_text_elements:
            bbox_el = el.get("bbox_pt") if isinstance(el, dict) else None
            if not isinstance(bbox_el, list) or len(bbox_el) != 4:
                continue
            try:
                tx0, ty0, tx1, ty1 = _coerce_bbox_pt(bbox_el)
            except Exception:
                continue
            ix0 = max(float(x0), float(tx0))
            iy0 = max(float(y0), float(ty0))
            ix1 = min(float(x1), float(tx1))
            iy1 = min(float(y1), float(ty1))
            if ix1 <= ix0 or iy1 <= iy0:
                continue
            overlap_cov += float((ix1 - ix0) * (iy1 - iy0)) / crop_area
            ex0 = max(
                0,
                int(
                    round(
                        (float(tx0) * float(scanned_render_dpi) / _PTS_PER_INCH)
                        - x0p
                    )
                ),
            )
            ey0 = max(
                0,
                int(
                    round(
                        (float(ty0) * float(scanned_render_dpi) / _PTS_PER_INCH)
                        - y0p
                    )
                ),
            )
            ex1 = min(
                w,
                int(
                    round(
                        (float(tx1) * float(scanned_render_dpi) / _PTS_PER_INCH)
                        - x0p
                    )
                ),
            )
            ey1 = min(
                h,
                int(
                    round(
                        (float(ty1) * float(scanned_render_dpi) / _PTS_PER_INCH)
                        - y0p
                    )
                ),
            )
            if ex1 <= ex0 or ey1 <= ey0:
                continue
            overlap_boxes.append((ex0, ey0, ex1, ey1))

        if overlap_boxes and len(overlap_boxes) <= 2 and overlap_cov >= 0.10:
            text_x0 = min(box[0] for box in overlap_boxes)
            text_y0 = min(box[1] for box in overlap_boxes)
            text_x1 = max(box[2] for box in overlap_boxes)
            text_y1 = max(box[3] for box in overlap_boxes)
            text_w = max(1, text_x1 - text_x0)
            text_h = max(1, text_y1 - text_y0)

            if (
                text_y0 >= int(round(0.48 * float(h)))
                and text_w >= int(round(0.28 * float(w)))
                and text_h <= int(round(0.42 * float(h)))
                and text_y0 >= max(18, int(round(0.22 * float(h))))
            ):
                clip_pad = max(4, min(14, int(round(0.06 * float(h)))))
                ny1p = max(y0p + 8, y0p + text_y0 - clip_pad)
                if ny1p > y0p + int(round(0.22 * float(h))):
                    scale = float(_PTS_PER_INCH) / float(max(1, int(scanned_render_dpi)))
                    clipped = [
                        float(x0p) * scale,
                        float(y0p) * scale,
                        float(x1p) * scale,
                        float(ny1p) * scale,
                    ]
                    clipped = [float(v) for v in _coerce_bbox_pt(clipped)]
                    if clipped[2] > clipped[0] and clipped[3] > clipped[1]:
                        return clipped

            for ex0, ey0, ex1, ey1 in overlap_boxes:
                pad_x = max(4, min(18, int(round(0.12 * float(ex1 - ex0)))))
                pad_y = max(4, min(20, int(round(0.28 * float(ey1 - ey0)))))
                ex0 = max(0, ex0 - pad_x)
                ey0 = max(0, ey0 - pad_y)
                ex1 = min(w, ex1 + pad_x)
                ey1 = min(h, ey1 + pad_y)
                mask[ey0:ey1, ex0:ex1] = False

    row_counts = mask.sum(axis=1)
    col_counts = mask.sum(axis=0)
    if row_counts.size > 0 and col_counts.size > 0:
        row_peak = int(row_counts.max()) if row_counts.size else 0
        col_peak = int(col_counts.max()) if col_counts.size else 0
        row_thresh = max(2, int(round(0.10 * float(row_peak)))) if row_peak > 0 else 2
        col_thresh = max(2, int(round(0.10 * float(col_peak)))) if col_peak > 0 else 2
        ys = np.where(row_counts >= row_thresh)[0]
        xs = np.where(col_counts >= col_thresh)[0]
    else:
        ys = np.empty((0,), dtype=np.int32)
        xs = np.empty((0,), dtype=np.int32)

    if xs.size < 24 or ys.size < 24:
        ys, xs = np.where(mask)
    if xs.size < 24 or ys.size < 24:
        return None

    cx0 = int(xs.min())
    cy0 = int(ys.min())
    cx1 = int(xs.max()) + 1
    cy1 = int(ys.max()) + 1

    left_margin = cx0
    top_margin = cy0
    right_margin = max(0, w - cx1)
    bottom_margin = max(0, h - cy1)
    trim_x = float(left_margin + right_margin) / max(1.0, float(w))
    trim_y = float(top_margin + bottom_margin) / max(1.0, float(h))
    side_trim_px = max(left_margin, top_margin, right_margin, bottom_margin)
    if side_trim_px < max(10, int(round(0.06 * float(min(w, h))))) and (
        trim_x < 0.10 and trim_y < 0.10
    ):
        return None

    pad = max(4, min(18, int(round(0.03 * float(min(w, h))))))
    nx0p = max(x0p, x0p + cx0 - pad)
    ny0p = max(y0p, y0p + cy0 - pad)
    nx1p = min(x1p, x0p + cx1 + pad)
    ny1p = min(y1p, y0p + cy1 + pad)
    if nx1p <= nx0p or ny1p <= ny0p:
        return None

    orig_area = max(1.0, float(x1p - x0p) * float(y1p - y0p))
    new_area = max(1.0, float(nx1p - nx0p) * float(ny1p - ny0p))
    shrink_ratio = float(new_area) / float(orig_area)
    if shrink_ratio <= 0.18:
        return None

    scale = float(_PTS_PER_INCH) / float(max(1, int(scanned_render_dpi)))
    tightened = [
        float(nx0p) * scale,
        float(ny0p) * scale,
        float(nx1p) * scale,
        float(ny1p) * scale,
    ]
    tightened = [float(v) for v in _coerce_bbox_pt(tightened)]
    if tightened[2] <= tightened[0] or tightened[3] <= tightened[1]:
        return None
    return tightened


def _tighten_scanned_image_region_infos(
    *,
    infos: list[_ScannedImageRegionInfo],
    img: Any,
    page_w_pt: float,
    page_h_pt: float,
    scanned_render_dpi: int,
    ocr_text_elements: list[dict[str, Any]] | None = None,
) -> list[_ScannedImageRegionInfo]:
    if not infos:
        return infos

    out: list[_ScannedImageRegionInfo] = []
    for info in infos:
        if info.geometry_points_pt:
            out.append(info)
            continue
        tightened_bbox = _tighten_scanned_image_region_bbox_by_visual_bounds(
            img=img,
            bbox_pt=info.bbox_pt,
            page_w_pt=page_w_pt,
            page_h_pt=page_h_pt,
            scanned_render_dpi=scanned_render_dpi,
            shape_confirmed=bool(info.shape_confirmed),
            ocr_text_elements=ocr_text_elements,
        )
        if tightened_bbox is None:
            out.append(info)
            continue

        try:
            x0, y0, x1, y1 = _coerce_bbox_pt(tightened_bbox)
            x0p, y0p = _pdf_pt_to_pix_px(
                x0,
                y0,
                page_height_pt=page_h_pt,
                dpi=int(scanned_render_dpi),
            )
            x1p, y1p = _pdf_pt_to_pix_px(
                x1,
                y1,
                page_height_pt=page_h_pt,
                dpi=int(scanned_render_dpi),
            )
            x0p = max(0, min(int(img.width - 1), int(x0p)))
            y0p = max(0, min(int(img.height - 1), int(y0p)))
            x1p = max(0, min(int(img.width), int(x1p)))
            y1p = max(0, min(int(img.height), int(y1p)))
            if x1p <= x0p or y1p <= y0p:
                out.append(info)
                continue

            crop = img.crop((x0p, y0p, x1p, y1p))
            _ensure_parent_dir(info.crop_path)
            crop.save(info.crop_path)
        except Exception:
            out.append(info)
            continue

        suppress_bbox = _build_scanned_image_region_suppress_bbox(
            tightened_bbox,
            page_w_pt=page_w_pt,
            page_h_pt=page_h_pt,
            shape_confirmed=bool(info.shape_confirmed),
        )
        out.append(
            _ScannedImageRegionInfo(
                bbox_pt=[float(v) for v in _coerce_bbox_pt(tightened_bbox)],
                suppress_bbox_pt=[float(v) for v in _coerce_bbox_pt(suppress_bbox)],
                crop_path=info.crop_path,
                shape_confirmed=bool(info.shape_confirmed),
                ai_hint=bool(info.ai_hint),
                background_removed=bool(info.background_removed),
                geometry_kind=info.geometry_kind,
                geometry_points_pt=info.geometry_points_pt,
            )
        )
    return out


def _dedupe_scanned_ocr_text_elements(
    *,
    ocr_text_elements: list[dict[str, Any]],
    baseline_ocr_h_pt: float,
) -> list[dict[str, Any]]:
    """Drop near-duplicate OCR text bboxes on scanned pages."""

    if len(ocr_text_elements) <= 1:
        return list(ocr_text_elements)

    candidates: list[dict[str, Any]] = []
    for el in ocr_text_elements:
        if not isinstance(el, dict):
            continue
        bbox_pt = el.get("bbox_pt")
        if not isinstance(bbox_pt, list) or len(bbox_pt) != 4:
            continue
        text = str(el.get("text") or "").strip()
        if not text:
            continue
        try:
            x0, y0, x1, y1 = _coerce_bbox_pt(bbox_pt)
        except Exception:
            continue
        if x1 <= x0 or y1 <= y0:
            continue
        area = float((x1 - x0) * (y1 - y0))
        conf = float(el.get("confidence") or 0.0)
        candidates.append(
            {
                **el,
                "bbox_pt": [float(x0), float(y0), float(x1), float(y1)],
                "_bbox": [float(x0), float(y0), float(x1), float(y1)],
                "_area": float(area),
                "_conf": float(conf),
                "_text": text,
            }
        )

    if len(candidates) <= 1:
        return [dict(el) for el in ocr_text_elements if isinstance(el, dict)]

    candidates.sort(
        key=lambda it: (-float(it.get("_conf") or 0.0), float(it.get("_area") or 0.0))
    )

    baseline = max(4.0, float(baseline_ocr_h_pt))
    kept: list[dict[str, Any]] = []
    for cur in candidates:
        cur_bbox = cur.get("_bbox")
        if not isinstance(cur_bbox, list) or len(cur_bbox) != 4:
            continue
        cur_area = float(cur.get("_area") or 1.0)
        cur_text = str(cur.get("_text") or "")
        cur_cy = float(cur_bbox[1] + cur_bbox[3]) / 2.0

        duplicate = False
        for prev in kept:
            prev_bbox = prev.get("_bbox")
            if not isinstance(prev_bbox, list) or len(prev_bbox) != 4:
                continue
            prev_area = float(prev.get("_area") or 1.0)
            prev_cy = float(prev_bbox[1] + prev_bbox[3]) / 2.0
            inter = _bbox_intersection_area_pt(cur_bbox, prev_bbox)
            if inter <= 0.0:
                continue

            overlap_small = float(inter) / max(1.0, float(min(cur_area, prev_area)))
            iou = _bbox_iou_pt(cur_bbox, prev_bbox)
            dy = abs(float(cur_cy) - float(prev_cy))

            if overlap_small >= 0.965 and iou >= 0.85:
                duplicate = True
                break

            if overlap_small >= 0.86 and _texts_similar_for_bbox_dedupe(
                cur_text, str(prev.get("_text") or "")
            ):
                duplicate = True
                break

            if dy <= (0.55 * baseline) and _texts_similar_for_bbox_dedupe(
                cur_text, str(prev.get("_text") or "")
            ):
                if overlap_small >= 0.70 or iou >= 0.55:
                    duplicate = True
                    break

            if dy <= (0.35 * baseline) and (overlap_small >= 0.80 or iou >= 0.60):
                duplicate = True
                break

            try:
                _, y0, _, y1 = _coerce_bbox_pt(cur_bbox)
                cur_h = float(y1 - y0)
            except Exception:
                cur_h = baseline
            if (
                cur_h <= (1.35 * baseline)
                and overlap_small >= 0.78
                and _texts_similar_for_bbox_dedupe(
                    cur_text, str(prev.get("_text") or "")
                )
            ):
                duplicate = True
                break

        if duplicate:
            continue
        kept.append(cur)

    def _reading_key(it: dict[str, Any]) -> tuple[float, float]:
        bb = it.get("_bbox")
        if not isinstance(bb, list) or len(bb) != 4:
            return (0.0, 0.0)
        x0, y0, x1, y1 = bb
        return ((float(y0) + float(y1)) / 2.0, float(x0))

    kept.sort(key=_reading_key)
    out: list[dict[str, Any]] = []
    for it in kept:
        cp = dict(it)
        cp.pop("_bbox", None)
        cp.pop("_area", None)
        cp.pop("_conf", None)
        cp.pop("_text", None)
        out.append(cp)
    return out


def _merge_neighbor_boxes_pt(
    boxes: list[list[float]],
    *,
    page_w_pt: float,
    page_h_pt: float,
    text_coverage_ratio_fn: Callable[[list[float]], tuple[float, int]],
) -> list[list[float]]:
    if len(boxes) <= 1:
        return [list(_coerce_bbox_pt(bb)) for bb in boxes if isinstance(bb, list)]

    merged = [list(_coerce_bbox_pt(bb)) for bb in boxes if isinstance(bb, list)]
    if len(merged) <= 1:
        return merged

    gap_x_pt = max(16.0, 0.04 * float(page_w_pt))
    gap_y_pt = max(12.0, 0.03 * float(page_h_pt))
    for _ in range(2):
        out: list[list[float]] = []
        for bb in merged:
            x0, y0, x1, y1 = _coerce_bbox_pt(bb)
            did_merge = False
            for i, ub in enumerate(out):
                ux0, uy0, ux1, uy1 = _coerce_bbox_pt(ub)
                y_overlap = float(min(y1, uy1) - max(y0, uy0))
                x_overlap = float(min(x1, ux1) - max(x0, ux0))
                min_h = max(1.0, float(min(y1 - y0, uy1 - uy0)))
                min_w = max(1.0, float(min(x1 - x0, ux1 - ux0)))

                horizontal_ok = False
                if y_overlap > 0.0 and y_overlap >= (0.62 * min_h):
                    if x0 > ux1:
                        x_gap = float(x0 - ux1)
                    elif ux0 > x1:
                        x_gap = float(ux0 - x1)
                    else:
                        x_gap = 0.0
                    horizontal_ok = x_gap <= gap_x_pt

                vertical_ok = False
                if x_overlap > 0.0 and x_overlap >= (0.62 * min_w):
                    if y0 > uy1:
                        y_gap = float(y0 - uy1)
                    elif uy0 > y1:
                        y_gap = float(uy0 - y1)
                    else:
                        y_gap = 0.0
                    vertical_ok = y_gap <= gap_y_pt

                if not (horizontal_ok or vertical_ok):
                    continue

                candidate = [
                    min(x0, ux0),
                    min(y0, uy0),
                    max(x1, ux1),
                    max(y1, uy1),
                ]
                cw = float(candidate[2] - candidate[0])
                ch = float(candidate[3] - candidate[1])
                page_area = max(1.0, float(page_w_pt) * float(page_h_pt))
                area_ratio = max(0.0, cw * ch) / page_area
                width_ratio = cw / max(1.0, float(page_w_pt))
                cov, n = text_coverage_ratio_fn(candidate)

                if (
                    (width_ratio >= 0.56 and (n >= 2 or cov >= 0.08))
                    or (area_ratio >= 0.16 and (n >= 3 or cov >= 0.12))
                    or (width_ratio >= 0.34 and n >= 2 and cov >= 0.05)
                    or (width_ratio >= 0.26 and n >= 3 and cov >= 0.04)
                    or (area_ratio >= 0.08 and n >= 2 and cov >= 0.07)
                ):
                    continue

                out[i] = candidate
                did_merge = True
                break

            if not did_merge:
                out.append([x0, y0, x1, y1])
        merged = out

    return merged


def _collect_scanned_image_region_candidates(
    *,
    page: dict[str, Any],
) -> list[list[float]]:
    """Return only explicit image-region hints from OCR/layout analysis."""

    regions_pt_from_ai: list[list[float]] = []
    regions = page.get("image_regions")
    if isinstance(regions, list) and regions:
        for raw_region in regions:
            region_info = _coerce_image_region_entry_pt(raw_region)
            if region_info is None:
                continue
            try:
                x0, y0, x1, y1 = _coerce_bbox_pt(region_info.get("bbox_pt"))
            except Exception:
                continue
            if x1 <= x0 or y1 <= y0:
                continue
            regions_pt_from_ai.append([float(x0), float(y0), float(x1), float(y1)])
    return regions_pt_from_ai


def _is_card_like_region(
    bbox: list[float],
    *,
    page_w_pt: float,
    page_h_pt: float,
    baseline_ocr_h_pt: float,
    ocr_text_elements: list[dict[str, Any]],
) -> bool:
    """Detect card-like mixed content region on scanned slides."""

    try:
        x0, y0, x1, y1 = _coerce_bbox_pt(bbox)
    except Exception:
        return False
    w = float(x1 - x0)
    h = float(y1 - y0)
    if w <= 0.0 or h <= 0.0:
        return False

    page_area = max(1.0, float(page_w_pt) * float(page_h_pt))
    area_ratio = (w * h) / page_area
    width_ratio = w / max(1.0, float(page_w_pt))
    height_ratio = h / max(1.0, float(page_h_pt))

    if area_ratio < 0.10:
        return False
    if width_ratio < 0.22 or height_ratio < 0.18:
        return False
    if width_ratio > 0.78 or height_ratio > 0.78:
        return False

    line_h_threshold = max(4.0, 0.60 * float(baseline_ocr_h_pt))
    text_lines = 0
    cjk_lines = 0
    area_overlap = 0.0

    for tel in ocr_text_elements:
        bbox_pt = tel.get("bbox_pt")
        if not isinstance(bbox_pt, list) or len(bbox_pt) != 4:
            continue
        try:
            tx0, ty0, tx1, ty1 = _coerce_bbox_pt(bbox_pt)
        except Exception:
            continue

        cx = (tx0 + tx1) / 2.0
        cy = (ty0 + ty1) / 2.0
        if cx < x0 or cx > x1 or cy < y0 or cy > y1:
            continue

        text_value = str(tel.get("text") or "")
        if _is_inline_short_token(text_value):
            continue

        tw = max(1.0, float(tx1 - tx0))
        th = max(1.0, float(ty1 - ty0))
        if th < line_h_threshold:
            continue

        text_lines += 1
        if _contains_cjk(text_value):
            cjk_lines += 1
        area_overlap += _bbox_intersection_area_pt(
            [x0, y0, x1, y1], [tx0, ty0, tx1, ty1]
        )

    cov = min(1.0, area_overlap / max(1.0, w * h))
    if text_lines >= 4:
        return True
    if cjk_lines >= 2 and text_lines >= 3:
        return True
    if text_lines >= 2 and cov >= 0.05 and area_ratio >= 0.14:
        return True
    return False


def _is_small_text_fragment_region(
    bbox: list[float],
    *,
    page_w_pt: float,
    page_h_pt: float,
    baseline_ocr_h_pt: float,
    ocr_text_elements: list[dict[str, Any]],
) -> bool:
    """Return whether a small candidate region is likely a text fragment."""

    if not ocr_text_elements:
        return False

    try:
        x0, y0, x1, y1 = _coerce_bbox_pt(bbox)
    except Exception:
        return False

    w = max(1.0, float(x1 - x0))
    h = max(1.0, float(y1 - y0))
    area = max(1.0, float(w * h))
    page_area = max(1.0, float(page_w_pt) * float(page_h_pt))
    area_ratio = float(area) / float(page_area)
    if area_ratio > 0.015:
        return False

    line_h_threshold = max(4.0, 0.55 * float(baseline_ocr_h_pt))
    for tel in ocr_text_elements:
        bbox_pt = tel.get("bbox_pt")
        if not isinstance(bbox_pt, list) or len(bbox_pt) != 4:
            continue

        text_value = str(tel.get("text") or "")
        compact_len = _compact_text_length(text_value)
        if compact_len < 4:
            continue

        try:
            tx0, ty0, tx1, ty1 = _coerce_bbox_pt(bbox_pt)
        except Exception:
            continue

        tw = max(1.0, float(tx1 - tx0))
        th = max(1.0, float(ty1 - ty0))
        if th < line_h_threshold:
            continue

        inter = _bbox_intersection_area_pt(
            [x0, y0, x1, y1],
            [tx0, ty0, tx1, ty1],
        )
        if inter > 0.0 and (float(inter) / float(area)) >= 0.72:
            return True

        y_overlap = float(min(y1, ty1) - max(y0, ty0))
        if y_overlap <= 0.0:
            continue
        min_h = max(1.0, float(min(h, th)))
        y_overlap_ratio = float(y_overlap) / float(min_h)
        if y_overlap_ratio < 0.68:
            continue

        x_overlap = max(0.0, float(min(x1, tx1) - max(x0, tx0)))
        min_w = max(1.0, float(min(w, tw)))
        x_overlap_ratio = float(x_overlap) / float(min_w)

        if x_overlap_ratio < 0.10:
            continue

        if tw >= (1.10 * float(w)) or (float(inter) / float(area)) >= 0.55:
            return True

    return False


def _save_scanned_regions_debug_overlay(
    *,
    render_path: Path,
    regions_pt: list[list[float]],
    artifacts_dir: Path,
    page_index: int,
    page_h_pt: float,
    scanned_render_dpi: int,
) -> None:
    if not regions_pt:
        return
    try:
        import json

        dbg_dir = artifacts_dir / "image_regions"
        dbg_dir.mkdir(parents=True, exist_ok=True)
        try:
            json_path = dbg_dir / f"page-{page_index:04d}.regions.json"
            payload = {
                "page_index": int(page_index),
                "regions_pt": [list(_coerce_bbox_pt(bb)) for bb in regions_pt],
            }
            json_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass
    except Exception:
        pass


def _try_merge_fragmented_scanned_image_regions(
    *,
    infos: list[_ScannedImageRegionInfo],
    img: Any,
    crops_dir: Path,
    page_index: int,
    page_w_pt: float,
    page_h_pt: float,
    scanned_render_dpi: int,
    baseline_ocr_h_pt: float,
    ocr_text_elements: list[dict[str, Any]],
    text_coverage_ratio_fn: Callable[[list[float]], tuple[float, int]],
) -> list[_ScannedImageRegionInfo]:
    """Try to merge split screenshot/diagram regions on scanned pages."""

    if len(infos) <= 1:
        return infos
    if page_w_pt <= 0 or page_h_pt <= 0:
        return infos

    page_area = max(1.0, float(page_w_pt) * float(page_h_pt))
    merge_counter = 0

    def _bbox_area(bb: list[float]) -> float:
        try:
            x0, y0, x1, y1 = _coerce_bbox_pt(bb)
        except Exception:
            return 0.0
        return max(0.0, float(x1 - x0) * float(y1 - y0))

    def _bbox_union(a: list[float], b: list[float]) -> list[float]:
        ax0, ay0, ax1, ay1 = _coerce_bbox_pt(a)
        bx0, by0, bx1, by1 = _coerce_bbox_pt(b)
        return [
            float(min(ax0, bx0)),
            float(min(ay0, by0)),
            float(max(ax1, bx1)),
            float(max(ay1, by1)),
        ]

    def _gap_and_overlap_ratios(
        a: list[float], b: list[float]
    ) -> tuple[float, float, float, float]:
        ax0, ay0, ax1, ay1 = _coerce_bbox_pt(a)
        bx0, by0, bx1, by1 = _coerce_bbox_pt(b)

        x_overlap = float(min(ax1, bx1) - max(ax0, bx0))
        y_overlap = float(min(ay1, by1) - max(ay0, by0))
        min_w = max(1.0, float(min(ax1 - ax0, bx1 - bx0)))
        min_h = max(1.0, float(min(ay1 - ay0, by1 - by0)))
        x_overlap_ratio = (x_overlap / min_w) if x_overlap > 0.0 else 0.0
        y_overlap_ratio = (y_overlap / min_h) if y_overlap > 0.0 else 0.0

        x_gap = 0.0
        if ax0 > bx1:
            x_gap = float(ax0 - bx1)
        elif bx0 > ax1:
            x_gap = float(bx0 - ax1)

        y_gap = 0.0
        if ay0 > by1:
            y_gap = float(ay0 - by1)
        elif by0 > ay1:
            y_gap = float(by0 - ay1)

        return (x_gap, y_gap, x_overlap_ratio, y_overlap_ratio)

    def _crop_bbox_to_path(bbox_pt: list[float], out_path: Path) -> bool:
        try:
            from PIL import Image
        except Exception:
            return False

        try:
            x0, y0, x1, y1 = _coerce_bbox_pt(bbox_pt)
        except Exception:
            return False

        x0p, y0p = _pdf_pt_to_pix_px(
            x0,
            y0,
            page_height_pt=page_h_pt,
            dpi=int(scanned_render_dpi),
        )
        x1p, y1p = _pdf_pt_to_pix_px(
            x1,
            y1,
            page_height_pt=page_h_pt,
            dpi=int(scanned_render_dpi),
        )
        x0p = max(0, min(int(img.width - 1), int(x0p)))
        y0p = max(0, min(int(img.height - 1), int(y0p)))
        x1p = max(0, min(int(img.width), int(x1p)))
        y1p = max(0, min(int(img.height), int(y1p)))
        if x1p <= x0p or y1p <= y0p:
            return False

        try:
            crop = img.crop((x0p, y0p, x1p, y1p))
            _ensure_parent_dir(out_path)
            crop.save(out_path)
            return True
        except Exception:
            return False

    def _build_union_info(
        bbox_pt: list[float],
        *,
        crop_path: Path,
        shape_confirmed: bool,
        ai_hint: bool,
    ) -> _ScannedImageRegionInfo:
        x0, y0, x1, y1 = _coerce_bbox_pt(bbox_pt)
        suppress_bbox = _build_scanned_image_region_suppress_bbox(
            [float(x0), float(y0), float(x1), float(y1)],
            page_w_pt=page_w_pt,
            page_h_pt=page_h_pt,
            shape_confirmed=bool(shape_confirmed),
        )
        return _ScannedImageRegionInfo(
            bbox_pt=[float(x0), float(y0), float(x1), float(y1)],
            suppress_bbox_pt=[float(v) for v in _coerce_bbox_pt(suppress_bbox)],
            crop_path=crop_path,
            shape_confirmed=bool(shape_confirmed),
            ai_hint=bool(ai_hint),
            background_removed=False,
            geometry_kind=None,
            geometry_points_pt=None,
        )

    merged = list(infos)
    for _ in range(3):
        changed = False
        merged.sort(key=lambda info: _bbox_area(info.bbox_pt), reverse=True)

        for i in range(len(merged)):
            a = merged[i]
            a_area = _bbox_area(a.bbox_pt)
            if a_area <= 0.0:
                continue
            for j in range(i + 1, len(merged)):
                b = merged[j]
                b_area = _bbox_area(b.bbox_pt)
                if b_area <= 0.0:
                    continue
                same_ai_hint_polygon = False
                if (
                    bool(getattr(a, "ai_hint", False))
                    and bool(getattr(b, "ai_hint", False))
                    and str(getattr(a, "geometry_kind", "") or "").strip().lower()
                    == "polygon"
                    and str(getattr(b, "geometry_kind", "") or "").strip().lower()
                    == "polygon"
                ):
                    same_ai_hint_polygon = _geometry_points_signature(
                        getattr(a, "geometry_points_pt", None)
                    ) == _geometry_points_signature(
                        getattr(b, "geometry_points_pt", None)
                    ) and bool(getattr(a, "geometry_points_pt", None))
                if (
                    a.background_removed
                    or b.background_removed
                ):
                    continue
                if (a.geometry_points_pt or b.geometry_points_pt) and (
                    not same_ai_hint_polygon
                ):
                    continue

                ax0, ay0, ax1, ay1 = _coerce_bbox_pt(a.bbox_pt)
                bx0, by0, bx1, by1 = _coerce_bbox_pt(b.bbox_pt)
                aw = max(1.0, float(ax1 - ax0))
                ah = max(1.0, float(ay1 - ay0))
                bw = max(1.0, float(bx1 - bx0))
                bh = max(1.0, float(by1 - by0))

                x_gap, y_gap, x_ov, y_ov = _gap_and_overlap_ratios(a.bbox_pt, b.bbox_pt)
                gap_x_limit = max(6.0, min(0.04 * float(page_w_pt), 40.0))
                gap_y_limit = max(6.0, min(0.03 * float(page_h_pt), 32.0))

                horizontal_adjacent = y_ov >= 0.70 and x_gap <= gap_x_limit
                vertical_adjacent = x_ov >= 0.70 and y_gap <= gap_y_limit
                if not (horizontal_adjacent or vertical_adjacent):
                    continue

                tol_x = max(8.0, min(0.05 * float(page_w_pt), 48.0))
                tol_y = max(8.0, min(0.05 * float(page_h_pt), 48.0))
                width_sim = abs(aw - bw) <= (0.25 * max(aw, bw))
                height_sim = abs(ah - bh) <= (0.25 * max(ah, bh))

                aligned = False
                if same_ai_hint_polygon:
                    aligned = bool(horizontal_adjacent or vertical_adjacent)
                elif vertical_adjacent:
                    aligned = (abs(ax0 - bx0) <= tol_x and abs(ax1 - bx1) <= tol_x) or (
                        width_sim and x_ov >= 0.85
                    )
                elif horizontal_adjacent:
                    aligned = (abs(ay0 - by0) <= tol_y and abs(ay1 - by1) <= tol_y) or (
                        height_sim and y_ov >= 0.85
                    )
                if not aligned:
                    continue

                union_bbox = _bbox_union(a.bbox_pt, b.bbox_pt)
                union_area = _bbox_area(union_bbox)
                if union_area <= 0.0:
                    continue

                if union_area > (1.45 * float(a_area + b_area)):
                    continue

                union_area_ratio = float(union_area) / float(page_area)
                if union_area_ratio < 0.020:
                    continue
                if union_area_ratio > 0.72:
                    continue

                cov, n = text_coverage_ratio_fn(union_bbox)
                if cov >= 0.18 or n >= 16:
                    continue

                if _is_card_like_region(
                    union_bbox,
                    page_w_pt=page_w_pt,
                    page_h_pt=page_h_pt,
                    baseline_ocr_h_pt=float(baseline_ocr_h_pt),
                    ocr_text_elements=ocr_text_elements,
                ):
                    continue

                merge_counter += 1
                union_crop_path = (
                    crops_dir
                    / f"page-{page_index:04d}-crop-merge-{merge_counter:02d}.png"
                )
                if not _crop_bbox_to_path(union_bbox, union_crop_path):
                    continue

                union_stats = _analyze_shape_crop(union_crop_path)
                if not union_stats.get("confirmed"):
                    continue

                union_info = _build_union_info(
                    union_bbox,
                    crop_path=union_crop_path,
                    shape_confirmed=bool(union_stats.get("confirmed")),
                    ai_hint=bool(
                        getattr(a, "ai_hint", False) or getattr(b, "ai_hint", False)
                    ),
                )

                keep: list[_ScannedImageRegionInfo] = []
                for k, info in enumerate(merged):
                    if k in (i, j):
                        continue
                    keep.append(info)
                keep.append(union_info)
                merged = keep
                changed = True
                break

            if changed:
                break

        if not changed:
            break

    return merged


def _build_scanned_image_region_infos(
    *,
    page: dict[str, Any],
    render_path: Path,
    artifacts_dir: Path,
    page_index: int,
    page_w_pt: float,
    page_h_pt: float,
    scanned_render_dpi: int,
    baseline_ocr_h_pt: float,
    ocr_text_elements: list[dict[str, Any]],
    has_full_page_bg_image: bool,
    text_coverage_ratio_fn: Callable[[list[float]], tuple[float, int]],
    text_inside_counts_fn: Callable[[list[float]], tuple[int, int]],
    min_area_ratio: float = 0.0025,
    max_area_ratio: float = 0.72,
    max_aspect_ratio: float = 4.8,
) -> list[_ScannedImageRegionInfo]:
    try:
        min_area_ratio_id = float(min_area_ratio)
    except Exception:
        min_area_ratio_id = 0.0025
    try:
        max_area_ratio_id = float(max_area_ratio)
    except Exception:
        max_area_ratio_id = 0.72
    try:
        max_aspect_ratio_id = float(max_aspect_ratio)
    except Exception:
        max_aspect_ratio_id = 4.8

    min_area_ratio_id = max(0.0, min(0.35, min_area_ratio_id))
    max_area_ratio_id = max(0.05, min(1.0, max_area_ratio_id))
    if max_area_ratio_id <= min_area_ratio_id:
        max_area_ratio_id = min(1.0, min_area_ratio_id + 0.05)
    max_aspect_ratio_id = max(1.2, min(30.0, max_aspect_ratio_id))

    regions_pt = _collect_scanned_image_region_candidates(
        page=page,
    )
    _save_scanned_regions_debug_overlay(
        render_path=render_path,
        regions_pt=regions_pt,
        artifacts_dir=artifacts_dir,
        page_index=page_index,
        page_h_pt=page_h_pt,
        scanned_render_dpi=scanned_render_dpi,
    )
    if not regions_pt:
        return []

    try:
        from PIL import Image
    except Exception:
        return []

    try:
        img = Image.open(render_path).convert("RGB")
    except Exception:
        return []

    crops_dir = artifacts_dir / "image_crops"
    crops_dir.mkdir(parents=True, exist_ok=True)
    page_area = max(1.0, float(page_w_pt) * float(page_h_pt))
    ai_hint_regions_pt: list[dict[str, Any]] = []
    raw_ai_regions = page.get("image_regions")
    if isinstance(raw_ai_regions, list):
        for raw_region in raw_ai_regions:
            region_info = _coerce_image_region_entry_pt(raw_region)
            if region_info is None:
                continue
            try:
                hx0, hy0, hx1, hy1 = _coerce_bbox_pt(region_info.get("bbox_pt"))
            except Exception:
                continue
            if hx1 <= hx0 or hy1 <= hy0:
                continue
            ai_hint_regions_pt.append(
                {
                    **region_info,
                    "bbox_pt": [float(hx0), float(hy0), float(hx1), float(hy1)],
                }
            )

    def _match_ai_hint_candidate(cand_bbox: list[float]) -> dict[str, Any] | None:
        c_area = max(
            1.0,
            float(
                max(
                    0.0,
                    float(cand_bbox[2] - cand_bbox[0])
                    * float(cand_bbox[3] - cand_bbox[1]),
                )
            ),
        )
        best_hint: dict[str, Any] | None = None
        best_score = 0.0
        for hint in ai_hint_regions_pt:
            hint_bbox = hint.get("bbox_pt")
            if not isinstance(hint_bbox, list) or len(hint_bbox) != 4:
                continue
            h_area = max(
                1.0,
                float(
                    max(
                        0.0,
                        float(hint_bbox[2] - hint_bbox[0])
                        * float(hint_bbox[3] - hint_bbox[1]),
                    )
                ),
            )
            inter = _bbox_intersection_area_pt(cand_bbox, hint_bbox)
            if inter <= 0.0:
                continue
            iou = _bbox_iou_pt(cand_bbox, hint_bbox)
            cover_c = inter / c_area
            cover_h = inter / h_area
            if iou < 0.52 and cover_c < 0.72 and cover_h < 0.72:
                continue
            score = max(float(iou), float(cover_c), float(cover_h))
            if best_hint is None or score > best_score:
                best_hint = hint
                best_score = score
        return best_hint

    infos: list[_ScannedImageRegionInfo] = []

    for ri, bbox in enumerate(regions_pt):
        if len(infos) >= 12:
            break

        try:
            x0, y0, x1, y1 = _coerce_bbox_pt(bbox)
        except Exception:
            continue
        w_pt = float(x1 - x0)
        h_pt = float(y1 - y0)
        if w_pt <= 0.0 or h_pt <= 0.0:
            continue

        cand_bbox = [float(x0), float(y0), float(x1), float(y1)]
        matched_ai_hint = _match_ai_hint_candidate(cand_bbox)
        is_ai_hint = matched_ai_hint is not None
        area_pt = max(0.0, w_pt * h_pt)
        area_ratio = area_pt / page_area
        if not is_ai_hint:
            if area_ratio < min_area_ratio_id or area_ratio > max_area_ratio_id:
                continue
        min_dim_threshold_pt = 1.0 if is_ai_hint else 12.0
        if min(w_pt, h_pt) < min_dim_threshold_pt:
            continue

        aspect = max(w_pt / max(1.0, h_pt), h_pt / max(1.0, w_pt))
        if (not is_ai_hint) and aspect >= max_aspect_ratio_id and area_ratio < 0.08:
            continue

        min_dim_pt = max(18.0, 1.8 * float(baseline_ocr_h_pt))
        min_dim_pt = min(72.0, float(min_dim_pt))
        min_area_pt = 0.65 * float(min_dim_pt) * float(min_dim_pt)
        if (not is_ai_hint) and area_pt < min_area_pt:
            continue

        cov, n = text_coverage_ratio_fn([x0, y0, x1, y1])
        n_inside, n_cjk_inside = text_inside_counts_fn([x0, y0, x1, y1])

        if (not is_ai_hint) and _is_card_like_region(
            [x0, y0, x1, y1],
            page_w_pt=page_w_pt,
            page_h_pt=page_h_pt,
            baseline_ocr_h_pt=float(baseline_ocr_h_pt),
            ocr_text_elements=ocr_text_elements,
        ):
            continue

        if (not is_ai_hint) and _is_small_text_fragment_region(
            [x0, y0, x1, y1],
            page_w_pt=page_w_pt,
            page_h_pt=page_h_pt,
            baseline_ocr_h_pt=float(baseline_ocr_h_pt),
            ocr_text_elements=ocr_text_elements,
        ):
            continue

        large_line_inside = 0
        wide_large_line_inside = 0
        large_line_overlap = 0.0
        large_line_h_threshold = max(4.0, 0.72 * float(baseline_ocr_h_pt))
        for tel in ocr_text_elements:
            bbox_pt = tel.get("bbox_pt")
            if not isinstance(bbox_pt, list) or len(bbox_pt) != 4:
                continue
            try:
                tx0, ty0, tx1, ty1 = _coerce_bbox_pt(bbox_pt)
            except Exception:
                continue
            tcx = (tx0 + tx1) / 2.0
            tcy = (ty0 + ty1) / 2.0
            if tcx < x0 or tcx > x1 or tcy < y0 or tcy > y1:
                continue

            tw = max(1.0, float(tx1 - tx0))
            th = max(1.0, float(ty1 - ty0))
            text_value = str(tel.get("text") or "")
            compact_len = _compact_text_length(text_value)
            if compact_len < 4:
                continue
            if th < large_line_h_threshold:
                continue
            if _is_inline_short_token(text_value):
                continue

            large_line_inside += 1
            if tw >= 0.22 * w_pt:
                wide_large_line_inside += 1
            large_line_overlap += _bbox_intersection_area_pt(
                [tx0, ty0, tx1, ty1], [x0, y0, x1, y1]
            )

        large_line_cov = min(1.0, large_line_overlap / max(1.0, area_pt))

        if not is_ai_hint:
            if (
                (n >= 4 and cov >= 0.10)
                or (n >= 3 and cov >= 0.16)
                or (n >= 2 and cov >= 0.24)
            ):
                continue
            if n_inside >= 1 and cov >= 0.42 and area_ratio >= 0.012:
                continue
            if n_cjk_inside >= 1 and cov >= 0.30 and area_ratio >= 0.020:
                continue
            if (
                area_ratio >= 0.020
                and large_line_inside >= 2
                and large_line_cov >= 0.10
            ):
                continue
            if large_line_inside >= 4 and (cov >= 0.08 or large_line_cov >= 0.10):
                continue
            if (
                wide_large_line_inside >= 2
                and large_line_cov >= 0.08
                and area_ratio >= 0.030
            ):
                continue

        geometry_kind = None
        geometry_points_pt = None
        if matched_ai_hint is not None:
            raw_geometry_kind = str(
                matched_ai_hint.get("geometry_kind") or ""
            ).strip().lower()
            raw_geometry_points = matched_ai_hint.get("geometry_points_pt")
            if raw_geometry_kind == "polygon" and isinstance(
                raw_geometry_points, list
            ):
                geometry_kind = "polygon"
                geometry_points_pt = [
                    [float(point[0]), float(point[1])]
                    for point in raw_geometry_points
                    if isinstance(point, list) and len(point) >= 2
                ] or None

        crop_out_path = crops_dir / f"page-{page_index:04d}-crop-{ri:02d}.png"
        # For AI-hint polygon regions, add a small crop expansion margin.
        # The polygon mask makes extra pixels transparent, so this safely
        # prevents clipping at polygon edges without visual artifacts.
        _polygon_expand_pt = 0.0
        if is_ai_hint and geometry_points_pt is not None:
            min_dim = min(w_pt, h_pt)
            _polygon_expand_pt = max(2.0, min(8.0, 0.02 * min_dim))
        if not _save_scanned_image_region_crop(
            img=img,
            bbox_pt=cand_bbox,
            crop_out_path=crop_out_path,
            page_h_pt=page_h_pt,
            scanned_render_dpi=int(scanned_render_dpi),
            geometry_points_pt=geometry_points_pt,
            expand_pt=_polygon_expand_pt,
        ):
            continue
        shape_confirmed = _is_shape_confirmed_crop(crop_out_path)
        background_removed = False

        if shape_confirmed and geometry_points_pt is None:
            try:
                if (
                    area_ratio <= 0.020
                    and aspect <= 2.4
                    and cov <= 0.06
                    and n_inside <= 1
                    and max(w_pt, h_pt) <= (7.0 * float(baseline_ocr_h_pt))
                ):
                    background_removed = _try_make_crop_background_transparent(
                        crop_out_path
                    )
            except Exception:
                background_removed = False

        cjk_text_heavy = (
            n_cjk_inside >= 2 and n_inside >= 3 and cov >= 0.08 and area_ratio >= 0.03
        )
        if shape_confirmed:
            if (not is_ai_hint) and area_ratio >= 0.40 and (
                cov >= 0.20 or n_inside >= 10
            ):
                continue
            if (not is_ai_hint) and cjk_text_heavy and area_ratio >= 0.07:
                continue
            if (not is_ai_hint) and (
                area_ratio >= 0.030
                and large_line_inside >= 3
                and large_line_cov >= 0.10
            ):
                continue
            if (not is_ai_hint) and large_line_inside >= 5 and (
                cov >= 0.08 or large_line_cov >= 0.10
            ):
                continue
            if (not is_ai_hint) and (
                wide_large_line_inside >= 2
                and large_line_cov >= 0.08
                and area_ratio >= 0.030
            ):
                continue
        else:
            if not is_ai_hint:
                if cov >= 0.16 or n_inside >= 5 or large_line_inside >= 3:
                    continue
                if area_ratio >= 0.24:
                    continue
                if cjk_text_heavy and area_ratio >= 0.06:
                    continue

        cand_area = max(1.0, area_pt)
        duplicated = False
        for info in infos:
            inter = _bbox_intersection_area_pt(cand_bbox, info.bbox_pt)
            if inter <= 0.0:
                continue
            if _bbox_iou_pt(cand_bbox, info.bbox_pt) >= 0.66:
                duplicated = True
                break
            ex0, ey0, ex1, ey1 = _coerce_bbox_pt(info.bbox_pt)
            ex_area = max(1.0, float((ex1 - ex0) * (ey1 - ey0)))
            if (inter / cand_area) >= 0.88:
                duplicated = True
                break
            if (
                (inter / ex_area) >= 0.88
                and (cand_area / ex_area) >= 1.6
                and cov >= 0.08
            ):
                duplicated = True
                break
        if duplicated:
            continue

        suppress_bbox = _build_scanned_image_region_suppress_bbox(
            cand_bbox,
            page_w_pt=page_w_pt,
            page_h_pt=page_h_pt,
            shape_confirmed=bool(shape_confirmed),
        )
        infos.append(
            _ScannedImageRegionInfo(
                bbox_pt=cand_bbox,
                suppress_bbox_pt=[float(v) for v in _coerce_bbox_pt(suppress_bbox)],
                crop_path=crop_out_path,
                shape_confirmed=bool(shape_confirmed),
                ai_hint=bool(is_ai_hint),
                background_removed=bool(background_removed),
                geometry_kind=geometry_kind,
                geometry_points_pt=geometry_points_pt,
            )
        )

    infos = _try_merge_fragmented_scanned_image_regions(
        infos=infos,
        img=img,
        crops_dir=crops_dir,
        page_index=page_index,
        page_w_pt=page_w_pt,
        page_h_pt=page_h_pt,
        scanned_render_dpi=scanned_render_dpi,
        baseline_ocr_h_pt=baseline_ocr_h_pt,
        ocr_text_elements=ocr_text_elements,
        text_coverage_ratio_fn=text_coverage_ratio_fn,
    )
    infos = _tighten_scanned_image_region_infos(
        infos=infos,
        img=img,
        page_w_pt=page_w_pt,
        page_h_pt=page_h_pt,
        scanned_render_dpi=scanned_render_dpi,
        ocr_text_elements=ocr_text_elements,
    )

    try:
        import json

        dbg_dir = artifacts_dir / "image_regions"
        dbg_dir.mkdir(parents=True, exist_ok=True)
        json_path = dbg_dir / f"page-{page_index:04d}.crops.json"
        payload = {
            "page_index": int(page_index),
            "crops": [
                {
                    "bbox_pt": list(_coerce_bbox_pt(info.bbox_pt)),
                    "suppress_bbox_pt": list(_coerce_bbox_pt(info.suppress_bbox_pt)),
                    "crop_path": str(info.crop_path),
                    "shape_confirmed": bool(info.shape_confirmed),
                    "ai_hint": bool(info.ai_hint),
                    "background_removed": bool(info.background_removed),
                    "geometry_kind": info.geometry_kind,
                    "geometry_points_pt": info.geometry_points_pt,
                }
                for info in infos
            ],
        }
        json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass
    return infos


def _filter_scanned_ocr_text_elements(
    *,
    ocr_text_elements: list[dict[str, Any]],
    image_region_infos: list[_ScannedImageRegionInfo],
    baseline_ocr_h_pt: float,
) -> list[dict[str, Any]]:
    if not ocr_text_elements or not image_region_infos:
        return list(ocr_text_elements)

    filtered: list[dict[str, Any]] = []
    for el in ocr_text_elements:
        bb = el.get("bbox_pt") if isinstance(el, dict) else None
        if not isinstance(bb, list) or len(bb) != 4:
            continue
        try:
            tx0, ty0, tx1, ty1 = _coerce_bbox_pt(bb)
        except Exception:
            continue
        tw = float(tx1 - tx0)
        th = float(ty1 - ty0)
        if tw <= 0.0 or th <= 0.0:
            continue

        # OCR text from eligible image-like blocks (e.g. charts) must be
        # preserved even when it overlaps its paired image region, because
        # the block is intentionally dual-path: image overlay + OCR text.
        if bool(el.get("ocr_image_like")):
            filtered.append(el)
            continue

        text_value = str(el.get("text") or "").strip()
        compact_len = _compact_text_length(text_value)
        is_cjk_line = _contains_cjk(text_value)
        keep_as_text_preferred = (
            is_cjk_line and compact_len >= 4 and th >= (0.65 * float(baseline_ocr_h_pt))
        )

        t_area = max(1.0, tw * th)
        tcx = (tx0 + tx1) / 2.0
        tcy = (ty0 + ty1) / 2.0
        inside_image = False
        for info in image_region_infos:
            ai_hint = bool(getattr(info, "ai_hint", False))
            region_bbox = info.bbox_pt if ai_hint else info.suppress_bbox_pt
            try:
                ix0, iy0, ix1, iy1 = _coerce_bbox_pt(region_bbox)
            except Exception:
                continue

            inter = _bbox_intersection_area_pt(
                [tx0, ty0, tx1, ty1], [ix0, iy0, ix1, iy1]
            )
            if inter <= 0.0:
                continue
            overlap_ratio = float(inter) / t_area
            center_inside = tcx >= ix0 and tcx <= ix1 and tcy >= iy0 and tcy <= iy1

            if ai_hint:
                if overlap_ratio >= 0.86:
                    inside_image = True
                    break
                continue

            if keep_as_text_preferred and not info.shape_confirmed:
                if center_inside and compact_len <= 3 and overlap_ratio >= 0.97:
                    inside_image = True
                    break
                continue

            if overlap_ratio >= 0.72:
                inside_image = True
                break
            if info.shape_confirmed and center_inside and overlap_ratio >= 0.25:
                inside_image = True
                break
            if (not info.shape_confirmed) and center_inside and overlap_ratio >= 0.82:
                inside_image = True
                break
            if center_inside and compact_len <= 3 and overlap_ratio >= 0.22:
                inside_image = True
                break

        if not inside_image:
            filtered.append(el)

    return filtered


def _apply_text_cutouts_to_scanned_image_region_crops(
    *,
    infos: list[_ScannedImageRegionInfo],
    render_path: Path,
    page_h_pt: float,
    scanned_render_dpi: int,
    ocr_text_elements: list[dict[str, Any]],
) -> list[_ScannedImageRegionInfo]:
    if not infos or not ocr_text_elements:
        return infos

    try:
        from PIL import Image
    except Exception:
        return infos

    try:
        img = Image.open(render_path).convert("RGB")
    except Exception:
        return infos

    for info in infos:
        if not (bool(info.ai_hint) or bool(info.geometry_points_pt)):
            continue

        cutout_bboxes_pt: list[list[float]] = []
        cutout_polygons_pt: list[list[list[float]]] = []
        for el in ocr_text_elements:
            bbox_pt = el.get("bbox_pt") if isinstance(el, dict) else None
            if not isinstance(bbox_pt, list) or len(bbox_pt) != 4:
                continue
            try:
                tx0, ty0, tx1, ty1 = _coerce_bbox_pt(bbox_pt)
            except Exception:
                continue
            if _bbox_intersection_area_pt([tx0, ty0, tx1, ty1], info.bbox_pt) <= 0.0:
                continue

            text_polygon = (
                el.get("ocr_layout_geometry_points_pt")
                if str(el.get("ocr_layout_geometry_kind") or "").strip().lower()
                == "polygon"
                else None
            )
            if isinstance(text_polygon, list) and text_polygon:
                normalized_polygon = [
                    [float(point[0]), float(point[1])]
                    for point in text_polygon
                    if isinstance(point, list) and len(point) >= 2
                ]
                if len(normalized_polygon) >= 3:
                    cutout_polygons_pt.append(normalized_polygon)
                    continue
            cutout_bboxes_pt.append([float(tx0), float(ty0), float(tx1), float(ty1)])

        if not cutout_bboxes_pt and not cutout_polygons_pt:
            continue

        try:
            _save_scanned_image_region_crop(
                img=img,
                bbox_pt=info.bbox_pt,
                crop_out_path=info.crop_path,
                page_h_pt=page_h_pt,
                scanned_render_dpi=int(scanned_render_dpi),
                geometry_points_pt=info.geometry_points_pt,
                exclude_bboxes_pt=cutout_bboxes_pt,
                exclude_polygons_pt=cutout_polygons_pt,
            )
        except Exception:
            continue

    return infos
