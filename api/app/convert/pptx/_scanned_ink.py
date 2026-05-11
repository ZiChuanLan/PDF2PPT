"""Scanned-page ink/line detection functions."""

from __future__ import annotations

from typing import Any

from ._scanned_color import _pix_to_rgb_array
from ._scanned_region_detect import _pdf_pt_to_pix_px
from .bbox_utils import _coerce_bbox_pt


def _estimate_bbox_ink_line_count(
    pix: Any,
    *,
    bbox_pt: Any,
    page_height_pt: float,
    dpi: int,
    max_lines: int = 3,
) -> int | None:
    """Estimate visible text line count in a bbox from source-page pixels.

    This is a lightweight visual signal used by OCR text rendering to choose
    single-line vs wrapped layout when AI/heuristic split metadata is absent.
    """

    try:
        import numpy as np  # type: ignore
    except Exception:
        return None

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
    if width < 8 or height < 8:
        return 1

    rgb_arr = _pix_to_rgb_array(pix)
    if rgb_arr is None:
        return None

    try:
        patch = rgb_arr[top:bottom, left:right]
        if patch.size <= 0:
            return 1

        gray = (
            0.299 * patch[:, :, 0].astype(np.float32)
            + 0.587 * patch[:, :, 1].astype(np.float32)
            + 0.114 * patch[:, :, 2].astype(np.float32)
        )

        bg = float(np.percentile(gray, 92.0))
        threshold = max(0.0, bg - 18.0)
        ink = gray < threshold
        if float(np.mean(ink)) < 0.004:
            return 1

        row_density = np.mean(ink, axis=1)
        if row_density.size < 3:
            return 1

        kernel = np.array([0.2, 0.6, 0.2], dtype=np.float32)
        row_density = np.convolve(row_density, kernel, mode="same")

        active_th = float(np.percentile(row_density, 72.0)) * 0.58
        active_th = max(0.018, min(0.22, active_th))
        active = row_density >= active_th

        runs = 0
        run_len = 0
        min_run = max(2, int(round(0.015 * float(height))))
        for flag in active.tolist():
            if flag:
                run_len += 1
            else:
                if run_len >= min_run:
                    runs += 1
                run_len = 0
        if run_len >= min_run:
            runs += 1

        if runs <= 0:
            return 1
        return max(1, min(int(max_lines), int(runs)))
    except Exception:
        return None
