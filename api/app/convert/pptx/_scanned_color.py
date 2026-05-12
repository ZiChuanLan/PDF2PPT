"""Scanned-page color sampling functions."""

from __future__ import annotations

from typing import Any

import numpy as np

from ._scanned_render import _pixel_to_rgb_triplet
from ._scanned_region_detect import _pdf_pt_to_pix_px
from .bbox_utils import _coerce_bbox_pt
from .color_utils import _rgb_luma, _rgb_sq_distance


def _sample_pixmap_rgb(
    pix: Any,
    *,
    x_px: int,
    y_px: int,
) -> tuple[int, int, int]:
    x = max(0, min(int(x_px), int(pix.width) - 1))
    y = max(0, min(int(y_px), int(pix.height) - 1))

    n = int(getattr(pix, "n", 0) or 0)
    if n <= 0:
        return (255, 255, 255)
    samples = pix.samples
    idx = (y * int(pix.width) + x) * n
    if idx + 1 >= len(samples):
        return (255, 255, 255)

    if n == 1:
        v = samples[idx]
        return (v, v, v)
    if n >= 3 and idx + 2 < len(samples):
        return (samples[idx], samples[idx + 1], samples[idx + 2])
    v = samples[idx]
    return (v, v, v)


_PIX_RGB_ARRAY_CACHE: dict[int, tuple[int, int, int, Any]] = {}


def _pix_to_rgb_array(pix: Any) -> Any | None:
    """Return cached HxWx3 uint8 array for a PyMuPDF pixmap."""

    try:
        w = int(getattr(pix, "width", 0) or 0)
        h = int(getattr(pix, "height", 0) or 0)
        n = int(getattr(pix, "n", 0) or 0)
    except Exception:
        return None

    if w <= 0 or h <= 0 or n <= 0:
        return None

    cache_key = id(pix)
    cached = _PIX_RGB_ARRAY_CACHE.get(cache_key)
    if cached is not None:
        cw, ch, cn, carr = cached
        if cw == w and ch == h and cn == n:
            return carr

    try:
        raw = np.frombuffer(pix.samples, dtype=np.uint8)
        expected = int(w) * int(h) * int(n)
        if raw.size < expected:
            return None
        arr = raw[:expected].reshape((h, w, n))
        if n == 1:
            rgb = np.repeat(arr[:, :, :1], 3, axis=2)
        else:
            rgb = arr[:, :, :3]
        _PIX_RGB_ARRAY_CACHE[cache_key] = (w, h, n, rgb)
        if len(_PIX_RGB_ARRAY_CACHE) > 24:
            _PIX_RGB_ARRAY_CACHE.clear()
        return rgb
    except Exception:
        return None


def _sample_bbox_background_rgb(
    pix: Any,
    *,
    bbox_pt: Any,
    page_height_pt: float,
    dpi: int,
) -> tuple[int, int, int]:
    """Best-effort background color sampling for a text bbox.

    Sampling the bbox center can hit foreground glyph pixels (dark text / white
    text), producing obvious masking artifacts. Instead sample just outside the
    bbox and average.
    """

    try:
        x0, y0, x1, y1 = _coerce_bbox_pt(bbox_pt)
    except Exception:
        return (255, 255, 255)

    h = max(1.0, y1 - y0)
    pad_pt = max(1.0, min(3.0, 0.1 * h))

    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0
    sample_pts = [
        (x0 - pad_pt, y0 - pad_pt),
        (x1 + pad_pt, y0 - pad_pt),
        (x0 - pad_pt, y1 + pad_pt),
        (x1 + pad_pt, y1 + pad_pt),
        (x0 - pad_pt, cy),
        (x1 + pad_pt, cy),
        (cx, y0 - pad_pt),
        (cx, y1 + pad_pt),
    ]

    colors: list[tuple[int, int, int]] = []
    for px_pt, py_pt in sample_pts:
        px, py = _pdf_pt_to_pix_px(
            float(px_pt),
            float(py_pt),
            page_height_pt=page_height_pt,
            dpi=int(dpi),
        )
        colors.append(_sample_pixmap_rgb(pix, x_px=px, y_px=py))

    if not colors:
        return (255, 255, 255)
    rs = sorted(c[0] for c in colors)
    gs = sorted(c[1] for c in colors)
    bs = sorted(c[2] for c in colors)
    mid = len(rs) // 2
    r = int(rs[mid])
    g = int(gs[mid])
    b = int(bs[mid])
    return (max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)))


def _sample_bbox_text_rgb(
    pix: Any,
    *,
    bbox_pt: Any,
    page_height_pt: float,
    dpi: int,
    bg_rgb: tuple[int, int, int],
) -> tuple[int, int, int] | None:
    """Estimate text color inside a bbox by selecting high-contrast pixels."""

    try:
        x0, y0, x1, y1 = _coerce_bbox_pt(bbox_pt)
    except Exception:
        return None

    x0p, y0p = _pdf_pt_to_pix_px(
        float(x0), float(y0), page_height_pt=page_height_pt, dpi=int(dpi)
    )
    x1p, y1p = _pdf_pt_to_pix_px(
        float(x1), float(y1), page_height_pt=page_height_pt, dpi=int(dpi)
    )
    left = max(0, min(int(x0p), int(x1p)))
    right = max(0, max(int(x0p), int(x1p)))
    top = max(0, min(int(y0p), int(y1p)))
    bottom = max(0, max(int(y0p), int(y1p)))

    width = max(0, right - left)
    height = max(0, bottom - top)
    if width < 2 or height < 2:
        return None

    max_samples = 1600
    area = max(1, width * height)
    step = max(1, int(round((float(area) / float(max_samples)) ** 0.5)))

    rgb_arr = _pix_to_rgb_array(pix)
    if rgb_arr is not None:
        try:

            ys = np.arange(top, bottom, step, dtype=np.int32)
            xs = np.arange(left, right, step, dtype=np.int32)
            if ys.size >= 1 and xs.size >= 1:
                yy, xx = np.meshgrid(ys, xs, indexing="ij")
                sampled = rgb_arr[yy, xx]
                sampled_flat = sampled.reshape(-1, 3).astype(np.float32, copy=False)

                bg_luma = float(_rgb_luma(bg_rgb))
                luma = (
                    0.299 * sampled_flat[:, 0]
                    + 0.587 * sampled_flat[:, 1]
                    + 0.114 * sampled_flat[:, 2]
                )
                contrast = np.abs(luma - float(bg_luma))
                keep = contrast >= 14.0
                if int(np.count_nonzero(keep)) >= 6:
                    kept_rgb = sampled_flat[keep]
                    kept_contrast = contrast[keep]
                    top_k = max(6, int(round(0.25 * kept_rgb.shape[0])))
                    if kept_rgb.shape[0] > top_k:
                        idx = np.argpartition(kept_contrast, -top_k)[-top_k:]
                        selected = kept_rgb[idx]
                    else:
                        selected = kept_rgb

                    med = np.median(selected, axis=0)
                    estimated = (
                        int(max(0, min(255, round(float(med[0]))))),
                        int(max(0, min(255, round(float(med[1]))))),
                        int(max(0, min(255, round(float(med[2]))))),
                    )
                    if _rgb_sq_distance(estimated, bg_rgb) < (24 * 24):
                        return None
                    return estimated
        except Exception:
            pass

    bg_luma = _rgb_luma(bg_rgb)
    candidates: list[tuple[float, tuple[int, int, int]]] = []
    for yp in range(top, bottom, step):
        for xp in range(left, right, step):
            rgb = _sample_pixmap_rgb(pix, x_px=int(xp), y_px=int(yp))
            luma = _rgb_luma(rgb)
            contrast = abs(float(luma) - float(bg_luma))
            if contrast >= 14.0:
                candidates.append((contrast, rgb))

    if len(candidates) < 6:
        return None

    candidates.sort(key=lambda row: row[0], reverse=True)
    top_k = max(6, int(round(0.25 * len(candidates))))
    selected = [rgb for _, rgb in candidates[:top_k]]
    rs = sorted(int(c[0]) for c in selected)
    gs = sorted(int(c[1]) for c in selected)
    bs = sorted(int(c[2]) for c in selected)
    mid = len(rs) // 2
    estimated = (int(rs[mid]), int(gs[mid]), int(bs[mid]))
    if _rgb_sq_distance(estimated, bg_rgb) < (24 * 24):
        return None
    return estimated
