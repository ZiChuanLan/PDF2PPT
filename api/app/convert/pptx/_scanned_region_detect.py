"""Scanned-page image region detection (heuristic + shape analysis)."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from ._scanned_render import (
    _apply_max_filter_l,
    _estimate_baseline_ocr_line_height_pt,
    _pixel_to_int,
    _pixel_to_rgb_triplet,
)
from .bbox_utils import _coerce_bbox_pt
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


def _detect_image_regions_from_render(
    render_path: Path,
    *,
    page_width_pt: float,
    page_height_pt: float,
    dpi: int,
    ocr_text_elements: list[dict[str, Any]] | None = None,
    max_regions: int = 12,
    merge_gap_scale: float = 0.06,
) -> list[list[float]]:
    """Heuristically detect non-text image regions on a scanned page.

    This is a best-effort fallback when AI layout assist is disabled/unavailable.
    It tries to find "busy" visual regions (diagrams, screenshots, photos) by:
    - masking out OCR text boxes on the rendered page image
    - edge-detecting the remaining content
    - connected-component grouping of edge pixels

    Returns bboxes in *PDF point* coordinates using the IR convention (top-left
    origin, y increasing downward).
    """

    try:
        from PIL import Image, ImageDraw, ImageFilter
    except Exception:
        return []

    try:
        img = Image.open(render_path).convert("RGB")
    except Exception:
        return []

    W, H = img.size
    if W <= 0 or H <= 0:
        return []

    scale = float(dpi) / _PTS_PER_INCH  # px per pt

    # 1) Build a text mask to reduce edges caused by glyph strokes.
    mask = Image.new("L", (W, H), 0)
    masked_regions_px: list[
        tuple[tuple[int, int, int, int], list[tuple[int, int]] | None]
    ] = []
    if ocr_text_elements:
        baseline_h_pt = _estimate_baseline_ocr_line_height_pt(
            ocr_text_elements=ocr_text_elements,
            page_w_pt=float(page_width_pt),
        )

        draw = ImageDraw.Draw(mask)
        for el in ocr_text_elements:
            bbox_pt = el.get("bbox_pt")
            try:
                x0, y0, x1, y1 = _coerce_bbox_pt(bbox_pt)
            except Exception:
                continue

            w_pt = max(1.0, float(x1 - x0))
            h_pt = max(1.0, float(y1 - y0))
            if h_pt < (0.35 * baseline_h_pt):
                continue
            width_ratio = w_pt / max(1.0, float(page_width_pt))
            if width_ratio < 0.18 and h_pt < (0.78 * baseline_h_pt):
                continue
            if h_pt > (2.8 * baseline_h_pt):
                if w_pt < (3.2 * h_pt):
                    continue
            # Expand a bit to cover anti-aliased edges around characters.
            pad_pt = max(1.0, min(5.0, 0.14 * h_pt))
            x0p = int(round((x0 - pad_pt) * scale))
            y0p = int(round((y0 - pad_pt) * scale))
            x1p = int(round((x1 + pad_pt) * scale))
            y1p = int(round((y1 + pad_pt) * scale))

            x0p = max(0, min(W - 1, x0p))
            y0p = max(0, min(H - 1, y0p))
            x1p = max(0, min(W, x1p))
            y1p = max(0, min(H, y1p))
            if x1p <= x0p or y1p <= y0p:
                continue

            polygon_px = _element_polygon_points_px(
                el,
                page_height_pt=page_height_pt,
                dpi=int(dpi),
                width_px=W,
                height_px=H,
            )
            if polygon_px is not None:
                draw.polygon(polygon_px, fill=255)
            else:
                draw.rectangle([x0p, y0p, x1p, y1p], fill=255)
            masked_regions_px.append(((x0p, y0p, x1p, y1p), polygon_px))

        # Dilate the mask a bit to cover edge halos.
        mask = _apply_max_filter_l(mask, size=5)

    def _median_rgb(samples: list[tuple[int, int, int]]) -> tuple[int, int, int]:
        if not samples:
            return (255, 255, 255)
        rs = sorted(int(s[0]) for s in samples)
        gs = sorted(int(s[1]) for s in samples)
        bs = sorted(int(s[2]) for s in samples)
        mid = len(rs) // 2
        return (rs[mid], gs[mid], bs[mid])

    def _sample_local_bg_rgb(
        source: Image.Image, *, x0: int, y0: int, x1: int, y1: int
    ) -> tuple[int, int, int]:
        # Sample just outside the bbox so we don't hit glyph pixels.
        pad = 4
        cx = (x0 + x1) // 2
        cy = (y0 + y1) // 2
        pts = [
            (x0 - pad, y0 - pad),
            (x1 + pad, y0 - pad),
            (x0 - pad, y1 + pad),
            (x1 + pad, y1 + pad),
            (x0 - pad, cy),
            (x1 + pad, cy),
            (cx, y0 - pad),
            (cx, y1 + pad),
        ]
        cols: list[tuple[int, int, int]] = []
        for px, py in pts:
            px = max(0, min(int(px), int(W - 1)))
            py = max(0, min(int(py), int(H - 1)))
            try:
                rgb = _pixel_to_rgb_triplet(source.getpixel((px, py)))
                if rgb is None:
                    continue
                cols.append(rgb)
            except Exception:
                continue
        return _median_rgb(cols)

    if masked_regions_px and mask.getbbox():
        try:
            masked_img = img.copy()
            draw_masked = ImageDraw.Draw(masked_img)
            for (x0p, y0p, x1p, y1p), polygon_px in masked_regions_px:
                bg = _sample_local_bg_rgb(img, x0=x0p, y0=y0p, x1=x1p, y1=y1p)
                if polygon_px is not None:
                    draw_masked.polygon(polygon_px, fill=bg)
                else:
                    draw_masked.rectangle([x0p, y0p, x1p, y1p], fill=bg)
            # A tiny blur helps hide hard boundaries of painted regions.
            try:
                masked_img = masked_img.filter(ImageFilter.BoxBlur(0.6))
            except Exception:
                pass
            img = masked_img
        except Exception:
            pass

    # 2) Edge-detect + threshold.
    edges = img.convert("L").filter(ImageFilter.FIND_EDGES)
    threshold = 32
    bw = edges.point(lambda p: 255 if p > threshold else 0, "L")  # type: ignore[reportOperatorIssue]
    # Thicken edges to connect disjoint strokes belonging to the same image.
    bw = _apply_max_filter_l(bw, size=5)

    # 3) Connected components on a downsampled binary image.
    factor = 8 if max(W, H) >= 3000 else (6 if max(W, H) >= 1600 else 4)
    SW = max(1, W // factor)
    SH = max(1, H // factor)
    small = bw.resize((SW, SH), Image.Resampling.NEAREST)  # type: ignore[reportAttributeAccessIssue]
    px = small.load()
    if px is None:
        return []

    visited: list[bytearray] = [bytearray(SW) for _ in range(SH)]
    comps: list[
        tuple[int, float, tuple[int, int, int, int]]
    ] = []  # (area, density, bbox)
    page_area = float(SW * SH)

    for y in range(SH):
        row = visited[y]
        for x in range(SW):
            if row[x]:
                continue
            pxy_v = _pixel_to_int(px[x, y])
            if pxy_v == 0:
                continue
            # BFS over 4-neighborhood.
            q: list[tuple[int, int]] = [(x, y)]
            row[x] = 1
            minx = maxx = x
            miny = maxy = y
            count = 0
            while q:
                cx, cy = q.pop()
                count += 1
                if cx < minx:
                    minx = cx
                if cx > maxx:
                    maxx = cx
                if cy < miny:
                    miny = cy
                if cy > maxy:
                    maxy = cy
                nx = cx - 1
                if nx >= 0 and not visited[cy][nx]:
                    pn_v = _pixel_to_int(px[nx, cy])
                    if pn_v != 0:
                        visited[cy][nx] = 1
                        q.append((nx, cy))
                nx = cx + 1
                if nx < SW and not visited[cy][nx]:
                    pn_v = _pixel_to_int(px[nx, cy])
                    if pn_v != 0:
                        visited[cy][nx] = 1
                        q.append((nx, cy))
                ny = cy - 1
                if ny >= 0 and not visited[ny][cx]:
                    pn_v = _pixel_to_int(px[cx, ny])
                    if pn_v != 0:
                        visited[ny][cx] = 1
                        q.append((cx, ny))
                ny = cy + 1
                if ny < SH and not visited[ny][cx]:
                    pn_v = _pixel_to_int(px[cx, ny])
                    if pn_v != 0:
                        visited[ny][cx] = 1
                        q.append((cx, ny))

            w = maxx - minx + 1
            h = maxy - miny + 1
            area = int(w * h)
            if area <= 0:
                continue
            density = float(count) / float(area)
            comps.append((area, density, (minx, miny, maxx + 1, maxy + 1)))

    # Filter candidates.
    min_area = max(80, int(0.0012 * page_area))
    candidates: list[tuple[int, float, tuple[int, int, int, int]]] = []
    for area, density, (x0, y0, x1, y1) in comps:
        if area < min_area:
            continue
        if page_area > 0 and (float(area) / page_area) > 0.60:
            continue
        w = x1 - x0
        h = y1 - y0
        if w <= 0 or h <= 0:
            continue
        if (w >= 12 and h <= 2) or (h >= 12 and w <= 2):
            continue
        if w > 16 * h or h > 16 * w:
            continue
        if density < 0.04:
            continue
        candidates.append((area, density, (x0, y0, x1, y1)))

    # Prefer larger regions.
    candidates.sort(key=lambda t: t[0], reverse=True)

    def _merge_boxes(
        boxes: list[tuple[int, int, int, int]],
        *,
        iou_thresh: float = 0.18,
        gap: int = 6,
    ) -> list[tuple[int, int, int, int]]:
        merged: list[tuple[int, int, int, int]] = []
        for b in boxes:
            bx0, by0, bx1, by1 = b
            did_merge = False
            for i, a in enumerate(merged):
                ax0, ay0, ax1, ay1 = a
                ax0g, ay0g, ax1g, ay1g = ax0 - gap, ay0 - gap, ax1 + gap, ay1 + gap
                inter_x0 = max(ax0g, bx0)
                inter_y0 = max(ay0g, by0)
                inter_x1 = min(ax1g, bx1)
                inter_y1 = min(ay1g, by1)
                if inter_x1 <= inter_x0 or inter_y1 <= inter_y0:
                    continue
                inter = (inter_x1 - inter_x0) * (inter_y1 - inter_y0)
                area_a = max(1, (ax1 - ax0) * (ay1 - ay0))
                area_b = max(1, (bx1 - bx0) * (by1 - by0))
                union = area_a + area_b - inter
                iou = float(inter) / float(max(1, union))
                if iou >= iou_thresh or inter >= 0.45 * float(min(area_a, area_b)):
                    merged[i] = (
                        min(ax0, bx0),
                        min(ay0, by0),
                        max(ax1, bx1),
                        max(ay1, by1),
                    )
                    did_merge = True
                    break
            if not did_merge:
                merged.append((bx0, by0, bx1, by1))
        return merged

    # Convert candidate boxes from small coords to pt coords.
    boxes_small = [bbox for _, _, bbox in candidates[: max_regions * 3]]
    merge_gap_scale = float(merge_gap_scale)
    merge_gap_scale = max(0.02, min(0.25, merge_gap_scale))
    merge_gap = max(6, int(round(merge_gap_scale * float(min(SW, SH)))))
    boxes_small = _merge_boxes(boxes_small, gap=merge_gap)

    regions_pt: list[list[float]] = []
    for x0, y0, x1, y1 in boxes_small[:max_regions]:
        px0 = int(x0 * factor)
        py0 = int(y0 * factor)
        px1 = int(min(W, x1 * factor))
        py1 = int(min(H, y1 * factor))
        if px1 <= px0 or py1 <= py0:
            continue

        pad = int(round(0.03 * float(min(px1 - px0, py1 - py0))))
        pad = max(3, min(24, pad))
        px0 = max(0, px0 - pad)
        py0 = max(0, py0 - pad)
        px1 = min(W, px1 + pad)
        py1 = min(H, py1 + pad)

        x0_pt = float(px0) / scale
        y0_pt = float(py0) / scale
        x1_pt = float(px1) / scale
        y1_pt = float(py1) / scale

        x0_pt = max(0.0, min(float(page_width_pt), x0_pt))
        y0_pt = max(0.0, min(float(page_height_pt), y0_pt))
        x1_pt = max(0.0, min(float(page_width_pt), x1_pt))
        y1_pt = max(0.0, min(float(page_height_pt), y1_pt))
        if x1_pt <= x0_pt or y1_pt <= y0_pt:
            continue

        area_pt = (x1_pt - x0_pt) * (y1_pt - y0_pt)
        if area_pt / max(1.0, float(page_width_pt) * float(page_height_pt)) > 0.80:
            continue

        regions_pt.append([x0_pt, y0_pt, x1_pt, y1_pt])

    # De-duplicate nearly identical bboxes.
    uniq: list[list[float]] = []
    for bb in regions_pt:
        x0, y0, x1, y1 = bb
        keep = True
        for ub in uniq:
            ux0, uy0, ux1, uy1 = ub
            if (
                abs(x0 - ux0) <= 2.0
                and abs(y0 - uy0) <= 2.0
                and abs(x1 - ux1) <= 2.0
                and abs(y1 - uy1) <= 2.0
            ):
                keep = False
                break
        if keep:
            uniq.append(bb)
    return uniq[:max_regions]


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
