"""Scanned-page image erase / background cleanup functions."""

from __future__ import annotations

import math
from collections import deque
from pathlib import Path
from typing import Any

import numpy as np

from ._scanned_color import _sample_bbox_background_rgb
from ._scanned_render import _apply_max_filter_l, _pixel_to_rgb_triplet
from ._scanned_region_detect import _pdf_pt_to_pix_px, _polygon_points_pt_to_px
from .bbox_utils import _coerce_bbox_pt, _ensure_parent_dir
from .constants import _PTS_PER_INCH


def _erase_regions_in_render_image(
    render_path: Path,
    *,
    out_path: Path,
    erase_bboxes_pt: list[list[float]],
    erase_polygons_pt: list[list[list[float]] | None] | None = None,
    protect_bboxes_pt: list[list[float]] | None = None,
    page_height_pt: float,
    dpi: int,
    text_erase_mode: str = "fill",
) -> Path:
    """Erase bboxes directly in the rendered background image.

    This avoids PPT rectangle masks (which can look like color blocks) and
    produces a cleaner editable overlay: erase first, then place text boxes.
    """

    if not erase_bboxes_pt:
        return render_path

    try:
        from PIL import Image, ImageChops, ImageDraw, ImageFilter
    except Exception:
        return render_path

    try:
        img = Image.open(render_path).convert("RGB")
    except Exception:
        return render_path

    W, H = img.size
    if W <= 0 or H <= 0:
        return render_path

    def _bbox_pt_to_rect_px(
        bb: list[float], *, pad: int = 0
    ) -> tuple[int, int, int, int] | None:
        try:
            x0, y0, x1, y1 = _coerce_bbox_pt(bb)
        except Exception:
            return None
        x0p, y0p = _pdf_pt_to_pix_px(
            x0, y0, page_height_pt=page_height_pt, dpi=int(dpi)
        )
        x1p, y1p = _pdf_pt_to_pix_px(
            x1, y1, page_height_pt=page_height_pt, dpi=int(dpi)
        )
        x0p = max(0, min(int(W - 1), int(x0p) - int(pad)))
        y0p = max(0, min(int(H - 1), int(y0p) - int(pad)))
        x1p = max(0, min(int(W), int(x1p) + int(pad)))
        y1p = max(0, min(int(H), int(y1p) + int(pad)))
        if x1p <= x0p or y1p <= y0p:
            return None
        return (x0p, y0p, x1p, y1p)

    rects: list[tuple[int, int, int, int]] = []
    core_rects: list[tuple[int, int, int, int]] = []
    polygon_masks_px: list[list[tuple[int, int]] | None] = []
    raw_polygons = erase_polygons_pt or []
    for index, bb in enumerate(erase_bboxes_pt):
        core = _bbox_pt_to_rect_px(bb, pad=0)
        if core is None:
            continue
        expanded = _bbox_pt_to_rect_px(bb, pad=1)
        if expanded is None:
            expanded = core
        rects.append(expanded)
        core_rects.append(core)
        polygon_masks_px.append(
            _polygon_points_pt_to_px(
                raw_polygons[index] if index < len(raw_polygons) else None,
                page_height_pt=page_height_pt,
                dpi=int(dpi),
                width_px=W,
                height_px=H,
            )
        )

    if not rects:
        return render_path

    protect_rects: list[tuple[int, int, int, int]] = []
    for bb in protect_bboxes_pt or []:
        rect = _bbox_pt_to_rect_px(bb, pad=2)
        if rect is not None:
            protect_rects.append(rect)

    erase_mode = str(text_erase_mode or "smart").strip().lower()
    if erase_mode not in {"smart", "fill"}:
        erase_mode = "smart"

    if erase_mode == "fill":
        dilate_size = 5 if max(W, H) >= 1600 else 3
        dilate_pad = max(1, int(dilate_size // 2) + 1)

        def _point_in_protect(x: int, y: int) -> bool:
            for px0, py0, px1, py1 in protect_rects:
                if px0 <= x < px1 and py0 <= y < py1:
                    return True
            return False

        def _median_color(values: list[tuple[int, int, int]]) -> tuple[int, int, int]:
            if not values:
                return (255, 255, 255)
            rs = sorted(v[0] for v in values)
            gs = sorted(v[1] for v in values)
            bs = sorted(v[2] for v in values)
            mid = len(values) // 2
            return (int(rs[mid]), int(gs[mid]), int(bs[mid]))

        def _estimate_fill_color(
            x0: int, y0: int, x1: int, y1: int
        ) -> tuple[int, int, int]:
            h = max(1, int(y1 - y0))
            w = max(1, int(x1 - x0))
            pad = max(1, min(8, int(round(0.28 * float(h)))))

            sample_points: list[tuple[int, int]] = []
            x_fracs = [0.15, 0.35, 0.50, 0.65, 0.85]
            y_fracs = [0.15, 0.35, 0.50, 0.65, 0.85]
            for frac in x_fracs:
                px = int(round(x0 + frac * float(w)))
                sample_points.append((px, y0 - pad))
                sample_points.append((px, y1 + pad))
            for frac in y_fracs:
                py = int(round(y0 + frac * float(h)))
                sample_points.append((x0 - pad, py))
                sample_points.append((x1 + pad, py))

            sample_points.extend(
                [
                    (x0 - pad, y0 - pad),
                    (x1 + pad, y0 - pad),
                    (x0 - pad, y1 + pad),
                    (x1 + pad, y1 + pad),
                ]
            )

            values: list[tuple[int, int, int]] = []
            for sx, sy in sample_points:
                cx = max(0, min(W - 1, int(sx)))
                cy = max(0, min(H - 1, int(sy)))
                if _point_in_protect(cx, cy):
                    continue
                rgb = _pixel_to_rgb_triplet(img.getpixel((cx, cy)))
                if rgb is not None:
                    values.append(rgb)

            if not values:
                rgb = _pixel_to_rgb_triplet(
                    img.getpixel((max(0, min(W - 1, x0)), max(0, min(H - 1, y0))))
                )
                if rgb is not None:
                    values.append(rgb)
            return _median_color(values)

        try:
            fill_img = img.copy()
            protect_mask_img = Image.new("L", (W, H), 0)
            if protect_rects:
                protect_draw = ImageDraw.Draw(protect_mask_img)
                for x0, y0, x1, y1 in protect_rects:
                    protect_draw.rectangle(
                        [x0, y0, max(x0, x1 - 1), max(y0, y1 - 1)], fill=255
                    )

            for (x0, y0, x1, y1), polygon_px in zip(rects, polygon_masks_px):
                color = _estimate_fill_color(x0, y0, x1, y1)

                patch_x0 = int(x0)
                patch_y0 = int(y0)
                patch_x1 = int(x1)
                patch_y1 = int(y1)
                if polygon_px is not None:
                    xs = [int(pt[0]) for pt in polygon_px]
                    ys = [int(pt[1]) for pt in polygon_px]
                    if xs and ys:
                        patch_x0 = min(patch_x0, min(xs))
                        patch_y0 = min(patch_y0, min(ys))
                        patch_x1 = max(patch_x1, max(xs) + 1)
                        patch_y1 = max(patch_y1, max(ys) + 1)

                patch_x0 = max(0, patch_x0 - dilate_pad)
                patch_y0 = max(0, patch_y0 - dilate_pad)
                patch_x1 = min(W, patch_x1 + dilate_pad)
                patch_y1 = min(H, patch_y1 + dilate_pad)
                if patch_x1 <= patch_x0 or patch_y1 <= patch_y0:
                    continue

                rect_mask = Image.new(
                    "L",
                    (int(patch_x1 - patch_x0), int(patch_y1 - patch_y0)),
                    0,
                )
                rect_draw = ImageDraw.Draw(rect_mask)
                if polygon_px is not None:
                    local_polygon_px = [
                        (int(px - patch_x0), int(py - patch_y0))
                        for px, py in polygon_px
                    ]
                    if len({pt for pt in local_polygon_px}) >= 3:
                        rect_draw.polygon(local_polygon_px, fill=255)
                    else:
                        rect_draw.rectangle(
                            [
                                int(x0 - patch_x0),
                                int(y0 - patch_y0),
                                max(int(x0 - patch_x0), int(x1 - patch_x0 - 1)),
                                max(int(y0 - patch_y0), int(y1 - patch_y0 - 1)),
                            ],
                            fill=255,
                        )
                else:
                    rect_draw.rectangle(
                        [
                            int(x0 - patch_x0),
                            int(y0 - patch_y0),
                            max(int(x0 - patch_x0), int(x1 - patch_x0 - 1)),
                            max(int(y0 - patch_y0), int(y1 - patch_y0 - 1)),
                        ],
                        fill=255,
                    )
                try:
                    rect_mask = rect_mask.filter(ImageFilter.MaxFilter(dilate_size))
                except Exception:
                    pass
                if protect_rects:
                    rect_mask = ImageChops.subtract(
                        rect_mask,
                        protect_mask_img.crop(
                            (patch_x0, patch_y0, patch_x1, patch_y1)
                        ),
                    )
                    if rect_mask.getbbox() is None:
                        continue
                fill_patch = Image.new(
                    "RGB",
                    (int(patch_x1 - patch_x0), int(patch_y1 - patch_y0)),
                    color,
                )
                fill_img.paste(fill_patch, (patch_x0, patch_y0), rect_mask)

            _ensure_parent_dir(out_path)
            fill_img.save(out_path)
            return out_path
        except Exception:
            return render_path

    arr = np.array(img, dtype=np.uint8)
    if arr.ndim != 3 or arr.shape[2] < 3:
        return render_path

    try:
        blur_radius = 2.2 if max(W, H) >= 1600 else 1.6
        bg_arr = np.array(
            img.filter(ImageFilter.GaussianBlur(radius=blur_radius)), dtype=np.uint8
        )
        strong_blur_radius = min(34.0, max(18.0, 7.5 * float(blur_radius)))
        bg_strong_arr = np.array(
            img.filter(ImageFilter.GaussianBlur(radius=strong_blur_radius)),
            dtype=np.uint8,
        )
    except Exception:
        bg_arr = arr.copy()
        bg_strong_arr = arr.copy()

    gray = (
        0.299 * arr[:, :, 0].astype(np.float32)
        + 0.587 * arr[:, :, 1].astype(np.float32)
        + 0.114 * arr[:, :, 2].astype(np.float32)
    )

    protect_mask = np.zeros((H, W), dtype=bool)
    for x0p, y0p, x1p, y1p in protect_rects:
        protect_mask[y0p:y1p, x0p:x1p] = True

    out = arr.copy()
    rects.sort(key=lambda r: (r[2] - r[0]) * (r[3] - r[1]))
    remove_mask = np.zeros((H, W), dtype=bool)
    fallback_mask = np.zeros((H, W), dtype=bool)
    remove_color_mask = np.zeros((H, W), dtype=bool)
    remove_color_map = np.zeros((H, W, 3), dtype=np.uint8)

    def _dilate_mask(mask: Any, radius: int = 1) -> Any:
        if radius <= 0:
            return mask
        hh, ww = mask.shape
        pad = int(radius)
        src = np.pad(
            mask, ((pad, pad), (pad, pad)), mode="constant", constant_values=False
        )
        dil = np.zeros_like(mask, dtype=bool)
        for dy in range(0, 2 * pad + 1):
            y_slice = slice(dy, dy + hh)
            for dx in range(0, 2 * pad + 1):
                dil |= src[y_slice, dx : dx + ww]
        return dil

    def _median_ring_rgb(
        x0: int,
        y0: int,
        x1: int,
        y1: int,
    ) -> tuple[int, int, int]:
        if x1 <= x0 or y1 <= y0:
            return (255, 255, 255)

        h = max(1, int(y1 - y0))
        pad = max(2, min(12, int(round(0.45 * float(h)))))
        rx0 = max(0, x0 - pad)
        ry0 = max(0, y0 - pad)
        rx1 = min(W, x1 + pad)
        ry1 = min(H, y1 + pad)
        if rx1 <= rx0 or ry1 <= ry0:
            return (255, 255, 255)

        ring = np.ones((ry1 - ry0, rx1 - rx0), dtype=bool)
        ix0 = max(0, x0 - rx0)
        iy0 = max(0, y0 - ry0)
        ix1 = min(ring.shape[1], x1 - rx0)
        iy1 = min(ring.shape[0], y1 - ry0)
        ring[iy0:iy1, ix0:ix1] = False

        sub_protect = protect_mask[ry0:ry1, rx0:rx1]
        if sub_protect.any():
            ring &= ~sub_protect

        ring_pixels = arr[ry0:ry1, rx0:rx1][ring]
        if ring_pixels.size <= 0:
            sub_blur = bg_strong_arr[y0:y1, x0:x1]
            if sub_blur.size <= 0:
                return (255, 255, 255)
            med = np.median(sub_blur.reshape(-1, 3), axis=0)
        else:
            med = np.median(ring_pixels.reshape(-1, 3), axis=0)

        return (
            int(max(0, min(255, round(float(med[0]))))),
            int(max(0, min(255, round(float(med[1]))))),
            int(max(0, min(255, round(float(med[2]))))),
        )

    for x0, y0, x1, y1 in rects:
        w = max(1, int(x1 - x0))
        h = max(1, int(y1 - y0))

        grow_x = max(2, min(18, int(round(0.55 * float(h)))))
        grow_y = max(1, min(4, int(round(0.18 * float(h)))))
        ex0 = max(0, x0 - grow_x)
        ey0 = max(0, y0 - grow_y)
        ex1 = min(W, x1 + grow_x)
        ey1 = min(H, y1 + grow_y)
        if ex1 <= ex0 or ey1 <= ey0:
            continue

        sub_gray = gray[ey0:ey1, ex0:ex1]
        sub_protect = protect_mask[ey0:ey1, ex0:ex1]

        ix0 = max(0, x0 - ex0)
        iy0 = max(0, y0 - ey0)
        ix1 = min(sub_gray.shape[1], x1 - ex0)
        iy1 = min(sub_gray.shape[0], y1 - ey0)
        if ix1 <= ix0 or iy1 <= iy0:
            continue

        ring_mask = np.ones_like(sub_gray, dtype=bool)
        ring_mask[iy0:iy1, ix0:ix1] = False
        if sub_protect.any():
            ring_mask &= ~sub_protect
        ring_vals = sub_gray[ring_mask]
        local_bg = (
            float(np.median(ring_vals))
            if ring_vals.size > 0
            else float(np.median(sub_gray))
        )

        delta_dark = max(8.0, min(26.0, 0.14 * local_bg + 4.0))
        delta_bright = max(9.0, min(30.0, 0.13 * (255.0 - local_bg) + 6.0))
        dark_mask = sub_gray <= (local_bg - delta_dark)
        if local_bg < 125.0:
            bright_mask = sub_gray >= (local_bg + delta_bright)
            text_like = dark_mask | bright_mask
        else:
            text_like = dark_mask

        band_pad = max(0, min(2, int(round(0.10 * float(h)))))
        by0 = max(0, iy0 - band_pad)
        by1 = min(sub_gray.shape[0], iy1 + band_pad)
        band_mask = np.zeros_like(sub_gray, dtype=bool)
        band_mask[by0:by1, :] = True

        m = text_like & band_mask & (~sub_protect)

        band_area = max(1, int(np.count_nonzero(band_mask & (~sub_protect))))
        if (int(np.count_nonzero(m)) / float(band_area)) > 0.42:
            stricter = max(10.0, delta_dark + 5.0)
            m = (sub_gray <= (local_bg - stricter)) & band_mask & (~sub_protect)

        near_delta = max(4.0, min(14.0, 0.55 * delta_dark))
        near_mask = (np.abs(sub_gray - local_bg) >= near_delta) & band_mask
        m = (m | (_dilate_mask(m, radius=1) & near_mask)) & (~sub_protect)

        core = np.zeros_like(sub_gray, dtype=bool)
        core[iy0:iy1, ix0:ix1] = True
        core &= ~sub_protect
        core_pixels = int(np.count_nonzero(core))
        masked_pixels = int(np.count_nonzero(m))

        need_fallback = False
        if masked_pixels <= 0:
            need_fallback = True
        elif core_pixels > 0 and (masked_pixels / float(core_pixels)) < 0.08:
            need_fallback = True

        if masked_pixels > 0:
            remove_mask[ey0:ey1, ex0:ex1] |= m
            fr, fg, fb = _median_ring_rgb(x0, y0, x1, y1)
            sub_color_map = remove_color_map[ey0:ey1, ex0:ex1]
            sub_color_map[m] = (fr, fg, fb)
            remove_color_map[ey0:ey1, ex0:ex1] = sub_color_map
            remove_color_mask[ey0:ey1, ex0:ex1] |= m
        if need_fallback and core_pixels > 0:
            fallback_mask[ey0:ey1, ex0:ex1] |= core

    if np.any(remove_mask) or np.any(fallback_mask):
        remove_mask = _dilate_mask(remove_mask, radius=1)
        fallback_mask = _dilate_mask(fallback_mask, radius=1)
        remove_mask &= ~protect_mask
        fallback_mask &= ~protect_mask
        fallback_only = fallback_mask & (~remove_mask)

        fill_remove_mask = remove_mask & remove_color_mask
        if np.any(fill_remove_mask):
            out[fill_remove_mask] = remove_color_map[fill_remove_mask]

        residual_remove_mask = remove_mask & (~remove_color_mask)
        if np.any(residual_remove_mask):
            out[residual_remove_mask] = bg_arr[residual_remove_mask]

        if np.any(fallback_only):
            out[fallback_only] = bg_arr[fallback_only]

    unresolved_mask = np.zeros((H, W), dtype=bool)
    try:
        diff_changed = (
            np.abs(out.astype(np.int16) - arr.astype(np.int16)).sum(axis=2) >= 8
        )
        for x0, y0, x1, y1 in core_rects:
            sub_protect = protect_mask[y0:y1, x0:x1]
            eligible = ~sub_protect
            eligible_px = int(np.count_nonzero(eligible))
            if eligible_px <= 0:
                continue
            changed_px = int(np.count_nonzero(diff_changed[y0:y1, x0:x1] & eligible))
            if (changed_px / float(eligible_px)) < 0.72:
                unresolved_mask[y0:y1, x0:x1] |= eligible
    except Exception:
        unresolved_mask = np.zeros((H, W), dtype=bool)

    if np.any(unresolved_mask):
        unresolved_mask = _dilate_mask(unresolved_mask, radius=1)
        unresolved_mask &= ~protect_mask
        out[unresolved_mask] = bg_arr[unresolved_mask]

    if core_rects:
        final_force_mask = np.zeros((H, W), dtype=bool)
        for x0, y0, x1, y1 in core_rects:
            if x1 <= x0 or y1 <= y0:
                continue
            sub_protect = protect_mask[y0:y1, x0:x1]
            if sub_protect.shape[0] <= 0 or sub_protect.shape[1] <= 0:
                continue

            sub_gray = gray[y0:y1, x0:x1]
            sub_out = out[y0:y1, x0:x1]
            out_luma = (
                0.299 * sub_out[:, :, 0].astype(np.float32)
                + 0.587 * sub_out[:, :, 1].astype(np.float32)
                + 0.114 * sub_out[:, :, 2].astype(np.float32)
            )
            residual = np.abs(sub_gray - out_luma)
            local_mask = (residual >= 10.0) & (~sub_protect)
            if not np.any(local_mask):
                continue
            sub_force = final_force_mask[y0:y1, x0:x1]
            sub_force |= local_mask
            final_force_mask[y0:y1, x0:x1] = sub_force

        if np.any(final_force_mask):
            final_force_mask = _dilate_mask(final_force_mask, radius=1)
            final_force_mask &= ~protect_mask
            out[final_force_mask] = bg_arr[final_force_mask]

    try:
        out_img = Image.fromarray(out.astype(np.uint8), mode="RGB")
        _ensure_parent_dir(out_path)
        out_img.save(out_path)
        return out_path
    except Exception:
        return render_path


def _try_make_crop_background_transparent(crop_path: Path) -> bool:
    """Best-effort background removal for icon-like crops.

    We estimate the dominant border color, then flood-fill similar colors from
    image edges as background and convert them to transparent alpha.
    """

    try:
        from PIL import Image, ImageFilter
    except Exception:
        return False

    try:
        img = Image.open(crop_path).convert("RGBA")
    except Exception:
        return False

    w, h = img.size
    if w < 18 or h < 18:
        return False

    band = max(1, min(6, int(round(0.045 * float(min(w, h))))))
    pix = img.load()
    if pix is None:
        return False

    border_rgb: list[tuple[int, int, int]] = []
    for y in range(h):
        for x in range(w):
            if x < band or x >= (w - band) or y < band or y >= (h - band):
                rgb = _pixel_to_rgb_triplet(pix[x, y])
                if rgb is None:
                    continue
                border_rgb.append(rgb)
    if len(border_rgb) < 12:
        return False

    def _median(vals: list[int]) -> int:
        if not vals:
            return 0
        s = sorted(vals)
        return int(s[len(s) // 2])

    med_r = _median([c[0] for c in border_rgb])
    med_g = _median([c[1] for c in border_rgb])
    med_b = _median([c[2] for c in border_rgb])

    def _dist_l1(rgb: tuple[int, int, int]) -> int:
        return (
            abs(int(rgb[0]) - med_r)
            + abs(int(rgb[1]) - med_g)
            + abs(int(rgb[2]) - med_b)
        )

    border_d = sorted(_dist_l1(c) for c in border_rgb)
    p90_idx = max(0, min(len(border_d) - 1, int(round(0.90 * (len(border_d) - 1)))))
    p90 = int(border_d[p90_idx])
    dist_thresh = max(14, min(72, int(round(1.35 * float(p90) + 8.0))))

    bg_candidate = [[False] * w for _ in range(h)]
    for y in range(h):
        row = bg_candidate[y]
        for x in range(w):
            rgb = _pixel_to_rgb_triplet(pix[x, y])
            if rgb is None:
                continue
            r, g, b = rgb
            row[x] = _dist_l1((int(r), int(g), int(b))) <= dist_thresh

    bg_mask = [[False] * w for _ in range(h)]
    q: deque[tuple[int, int]] = deque()

    def _enqueue_if_bg(x: int, y: int) -> None:
        if x < 0 or y < 0 or x >= w or y >= h:
            return
        if bg_mask[y][x] or (not bg_candidate[y][x]):
            return
        bg_mask[y][x] = True
        q.append((x, y))

    for x in range(w):
        _enqueue_if_bg(x, 0)
        _enqueue_if_bg(x, h - 1)
    for y in range(h):
        _enqueue_if_bg(0, y)
        _enqueue_if_bg(w - 1, y)

    while q:
        x, y = q.popleft()
        _enqueue_if_bg(x - 1, y)
        _enqueue_if_bg(x + 1, y)
        _enqueue_if_bg(x, y - 1)
        _enqueue_if_bg(x, y + 1)

    total = max(1, w * h)
    bg_pixels = sum(1 for y in range(h) for x in range(w) if bg_mask[y][x])
    bg_ratio = float(bg_pixels) / float(total)
    if bg_ratio < 0.15 or bg_ratio > 0.93:
        return False

    alpha_bytes = bytearray(total)
    idx = 0
    for y in range(h):
        for x in range(w):
            alpha_bytes[idx] = 0 if bg_mask[y][x] else 255
            idx += 1

    alpha = Image.frombytes("L", (w, h), bytes(alpha_bytes)).filter(
        ImageFilter.GaussianBlur(radius=0.7)
    )
    img.putalpha(alpha)

    try:
        img.save(crop_path)
    except Exception:
        return False
    return True


def _clear_regions_for_transparent_crops(
    *,
    cleaned_render_path: Path,
    out_path: Path,
    regions_pt: list[list[float]],
    regions_polygons_pt: list[list[list[float]] | None] | None = None,
    pix: Any,
    page_height_pt: float,
    dpi: int,
    clear_expand_min_pt: float = 0.35,
    clear_expand_max_pt: float = 1.5,
    clear_expand_ratio: float = 0.012,
) -> Path:
    if not regions_pt:
        return cleaned_render_path

    try:
        min_expand_pt = float(clear_expand_min_pt)
    except Exception:
        min_expand_pt = 0.35
    try:
        max_expand_pt = float(clear_expand_max_pt)
    except Exception:
        max_expand_pt = 1.5
    try:
        expand_ratio = float(clear_expand_ratio)
    except Exception:
        expand_ratio = 0.012

    min_expand_pt = max(0.0, min(6.0, min_expand_pt))
    max_expand_pt = max(0.0, min(8.0, max_expand_pt))
    if max_expand_pt < min_expand_pt:
        max_expand_pt = min_expand_pt
    expand_ratio = max(0.0, min(0.12, expand_ratio))

    try:
        from PIL import Image, ImageDraw, ImageFilter
    except Exception:
        return cleaned_render_path

    try:
        img = Image.open(cleaned_render_path).convert("RGB")
    except Exception:
        return cleaned_render_path

    fill_img = img.copy()
    raw_polygons = regions_polygons_pt or []
    dilate_size = 5 if max(img.width, img.height) >= 1600 else 3
    for index, bb in enumerate(regions_pt):
        try:
            x0, y0, x1, y1 = _coerce_bbox_pt(bb)
        except Exception:
            continue
        if x1 <= x0 or y1 <= y0:
            continue

        fill_rgb = _sample_bbox_background_rgb(
            pix,
            bbox_pt=[x0, y0, x1, y1],
            page_height_pt=page_height_pt,
            dpi=int(dpi),
        )
        w_pt = max(1.0, float(x1 - x0))
        h_pt = max(1.0, float(y1 - y0))
        expand_pt = max(
            float(min_expand_pt),
            min(float(max_expand_pt), float(expand_ratio) * min(w_pt, h_pt)),
        )
        x0e = float(x0) - float(expand_pt)
        y0e = float(y0) - float(expand_pt)
        x1e = float(x1) + float(expand_pt)
        y1e = float(y1) + float(expand_pt)

        scale = float(dpi) / float(_PTS_PER_INCH)
        x0p = int(math.floor(x0e * scale))
        y0p = int(math.floor(y0e * scale))
        x1p = int(math.ceil(x1e * scale))
        y1p = int(math.ceil(y1e * scale))
        x0p = max(0, min(int(img.width - 1), int(x0p)))
        y0p = max(0, min(int(img.height - 1), int(y0p)))
        x1p = max(0, min(int(img.width), int(x1p)))
        y1p = max(0, min(int(img.height), int(y1p)))
        if x1p <= x0p or y1p <= y0p:
            continue

        region_mask = Image.new("L", (img.width, img.height), 0)
        region_draw = ImageDraw.Draw(region_mask)
        polygon_px = _polygon_points_pt_to_px(
            raw_polygons[index] if index < len(raw_polygons) else None,
            page_height_pt=page_height_pt,
            dpi=int(dpi),
            width_px=int(img.width),
            height_px=int(img.height),
        )
        if polygon_px is not None:
            region_draw.polygon(polygon_px, fill=255)
        else:
            region_draw.rectangle(
                [x0p, y0p, max(x0p, x1p - 1), max(y0p, y1p - 1)],
                fill=255,
            )
        try:
            region_mask = region_mask.filter(ImageFilter.MaxFilter(dilate_size))
        except Exception:
            pass
        fill_img.paste(fill_rgb, (0, 0, img.width, img.height), region_mask)

    try:
        _ensure_parent_dir(out_path)
        fill_img.save(out_path)
        return out_path
    except Exception:
        return cleaned_render_path
