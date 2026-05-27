"""Scanned-page image region detection (heuristic + shape analysis)."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from ._scanned_render import _pixel_to_int
from .constants import _PTS_PER_INCH


def _pdf_pt_to_pix_px(
    x_pt: float,
    y_pt: float,
    *,
    page_height_pt: float,
    dpi: int,
) -> tuple[int, int]:
    # IR coordinates and rendered pixmaps both use a top-left origin.
    x_px = x_pt * dpi / _PTS_PER_INCH
    y_px = y_pt * dpi / _PTS_PER_INCH
    return (int(round(x_px)), int(round(y_px)))


def _coerce_polygon_points_pt(value: Any) -> list[tuple[float, float]] | None:
    if not isinstance(value, (list, tuple)):
        return None
    points: list[tuple[float, float]] = []
    for raw_point in value:
        if not isinstance(raw_point, (list, tuple)) or len(raw_point) < 2:
            return None
        try:
            x = float(raw_point[0])
            y = float(raw_point[1])
        except Exception:
            return None
        if not math.isfinite(x) or not math.isfinite(y):
            return None
        points.append((x, y))
    if len(points) < 3:
        return None
    return points


def _polygon_points_pt_to_px(
    value: Any,
    *,
    page_height_pt: float,
    dpi: int,
    width_px: int,
    height_px: int,
) -> list[tuple[int, int]] | None:
    points_pt = _coerce_polygon_points_pt(value)
    if points_pt is None or width_px <= 0 or height_px <= 0:
        return None

    converted: list[tuple[int, int]] = []
    for x_pt, y_pt in points_pt:
        x_px, y_px = _pdf_pt_to_pix_px(
            x_pt,
            y_pt,
            page_height_pt=page_height_pt,
            dpi=int(dpi),
        )
        coord = (
            max(0, min(int(width_px - 1), int(x_px))),
            max(0, min(int(height_px - 1), int(y_px))),
        )
        if converted and coord == converted[-1]:
            continue
        converted.append(coord)
    if len({point for point in converted}) < 3:
        return None
    return converted


def _element_polygon_points_px(
    element: dict[str, Any],
    *,
    page_height_pt: float,
    dpi: int,
    width_px: int,
    height_px: int,
) -> list[tuple[int, int]] | None:
    if bool(element.get("ocr_linebreak_assisted")):
        return None
    if str(element.get("ocr_layout_geometry_kind") or "").strip().lower() != "polygon":
        return None
    return _polygon_points_pt_to_px(
        element.get("ocr_layout_geometry_points_pt"),
        page_height_pt=page_height_pt,
        dpi=int(dpi),
        width_px=width_px,
        height_px=height_px,
    )


def _analyze_shape_crop(crop_path: Path) -> dict[str, Any]:
    """Return best-effort "image-likeness" stats for a rendered crop.

    This is a lightweight *visual* heuristic that helps answer:
    - does this crop look like a real screenshot/diagram/icon?
    - is it likely a text-only panel/strip?

    It intentionally avoids any extra model calls (VLM/LLM) so it stays cheap
    and works offline. The output is used as an internal quality signal for
    merging fragmented image regions.
    """

    try:
        from PIL import Image, ImageFilter
    except Exception:
        return {"confirmed": False, "score": 0.0}

    try:
        img = Image.open(crop_path).convert("L")
    except Exception:
        return {"confirmed": False, "score": 0.0}

    w, h = img.size
    if w < 18 or h < 18:
        return {"confirmed": False, "score": 0.0, "w": int(w), "h": int(h)}

    # Normalize size for stable thresholds.
    max_side = max(w, h)
    if max_side > 320:
        scale = 320.0 / float(max_side)
        w2 = max(16, int(round(float(w) * scale)))
        h2 = max(16, int(round(float(h) * scale)))
        img = img.resize((w2, h2))
        w, h = img.size

    edges = img.filter(ImageFilter.FIND_EDGES)
    bw = edges.point(lambda p: 255 if p > 34 else 0, "L")  # type: ignore[reportOperatorIssue]
    pix = bw.load()

    if pix is None or w <= 0 or h <= 0:
        return {"confirmed": False, "score": 0.0, "w": int(w), "h": int(h)}

    band = max(2, min(7, int(round(0.03 * float(min(w, h))))))

    def _edge_ratio_rect(x0: int, y0: int, x1: int, y1: int) -> float:
        x0 = max(0, min(x0, w))
        x1 = max(0, min(x1, w))
        y0 = max(0, min(y0, h))
        y1 = max(0, min(y1, h))
        if x1 <= x0 or y1 <= y0:
            return 0.0
        total = max(1, (x1 - x0) * (y1 - y0))
        on = 0
        for yy in range(y0, y1):
            for xx in range(x0, x1):
                pxy_v = _pixel_to_int(pix[xx, yy])
                if pxy_v > 0:
                    on += 1
        return float(on) / float(total)

    top_r = _edge_ratio_rect(0, 0, w, band)
    bottom_r = _edge_ratio_rect(0, h - band, w, h)
    left_r = _edge_ratio_rect(0, 0, band, h)
    right_r = _edge_ratio_rect(w - band, 0, w, h)

    border_side_hits = sum(1 for r in (top_r, bottom_r, left_r, right_r) if r >= 0.06)

    inset = max(2 * band, int(round(0.10 * float(min(w, h)))))
    interior_r = _edge_ratio_rect(inset, inset, w - inset, h - inset)

    has_h_pair = top_r >= 0.07 and bottom_r >= 0.07
    has_v_pair = left_r >= 0.07 and right_r >= 0.07
    has_frame = has_h_pair or has_v_pair

    aspect = max(float(w) / max(1.0, float(h)), float(h) / max(1.0, float(w)))
    icon_like = aspect <= 1.8 and interior_r >= 0.075 and (w * h) >= 1200
    screenshot_like = (
        (w * h) >= 8500
        and aspect <= 3.8
        and interior_r >= 0.032
        and border_side_hits >= 1
    )

    confirmed = False
    if has_frame and border_side_hits >= 2 and interior_r >= 0.010:
        confirmed = True
    elif screenshot_like:
        confirmed = True
    elif icon_like and border_side_hits >= 1:
        confirmed = True

    border_avg = (top_r + bottom_r + left_r + right_r) / 4.0
    border_strength = min(1.0, float(border_avg) / 0.10)
    interior_strength = min(1.0, float(interior_r) / 0.06)
    score = 0.55 * interior_strength + 0.35 * border_strength
    if has_frame:
        score += 0.08
    if screenshot_like:
        score += 0.08
    if icon_like:
        score += 0.05
    score = max(0.0, min(1.0, float(score)))

    return {
        "confirmed": bool(confirmed),
        "score": float(score),
        "w": int(w),
        "h": int(h),
        "aspect": float(aspect),
        "border_side_hits": int(border_side_hits),
        "top_r": float(top_r),
        "bottom_r": float(bottom_r),
        "left_r": float(left_r),
        "right_r": float(right_r),
        "interior_r": float(interior_r),
        "has_frame": bool(has_frame),
        "icon_like": bool(icon_like),
        "screenshot_like": bool(screenshot_like),
    }


def _is_shape_confirmed_crop(crop_path: Path) -> bool:
    """Best-effort check whether a crop looks like a real image/diagram region.

    We treat regions with clear rectangular edges and non-trivial interior
    structure as "confirmed image". This helps suppress OCR edits *inside*
    screenshots/diagrams while avoiding false positives on plain text blocks.
    """

    try:
        return bool(_analyze_shape_crop(crop_path).get("confirmed"))
    except Exception:
        return False
