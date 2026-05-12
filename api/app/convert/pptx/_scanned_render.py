"""Scanned-page rendering and pixel utility functions."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import numpy as np

from ....models.error import AppException, ErrorCode

from .bbox_utils import _coerce_bbox_pt, _ensure_parent_dir


def _pixel_to_int(pixel: Any) -> int:
    if isinstance(pixel, tuple):
        if not pixel:
            return 0
        pixel = pixel[0]
    if pixel is None:
        return 0
    try:
        return int(pixel)
    except Exception:
        return 0


def _pixel_to_rgb_triplet(pixel: Any) -> tuple[int, int, int] | None:
    if isinstance(pixel, tuple):
        if len(pixel) >= 3:
            c0, c1, c2 = pixel[0], pixel[1], pixel[2]
        elif len(pixel) == 1:
            c0 = c1 = c2 = pixel[0]
        else:
            return None
    else:
        c0 = c1 = c2 = pixel

    if c0 is None or c1 is None or c2 is None:
        return None

    try:
        return (int(c0), int(c1), int(c2))
    except Exception:
        return None


def _apply_max_filter_l(image: Any, *, size: int) -> Any:
    """Apply an L-mode max filter, preferring a faster NumPy implementation."""

    try:
        size_id = int(size)
    except Exception:
        return image

    if size_id <= 1:
        return image
    if size_id % 2 == 0:
        size_id += 1

    try:
        from PIL import Image

        if getattr(image, "mode", None) == "L":
            arr = np.asarray(image, dtype=np.uint8)
            if arr.ndim == 2 and arr.size > 0:
                radius = size_id // 2
                pad = np.pad(arr, radius, mode="edge")
                out = pad[: arr.shape[0], : arr.shape[1]].copy()
                for dy in range(size_id):
                    row_start = dy
                    row_end = dy + arr.shape[0]
                    for dx in range(size_id):
                        if dy == 0 and dx == 0:
                            continue
                        col_start = dx
                        col_end = dx + arr.shape[1]
                        np.maximum(
                            out,
                            pad[row_start:row_end, col_start:col_end],
                            out=out,
                        )
                return Image.fromarray(out, mode="L")
    except Exception:
        pass

    try:
        from PIL import ImageFilter

        return image.filter(ImageFilter.MaxFilter(size_id))
    except Exception:
        return image


def _render_pdf_page_png(
    pdf_path: Path,
    *,
    page_index: int,
    dpi: int,
    out_path: Path,
) -> Any:
    try:
        pymupdf = importlib.import_module("pymupdf")
    except Exception as e:
        raise AppException(
            code=ErrorCode.CONVERSION_FAILED,
            message="PyMuPDF (pymupdf) is required for scanned-page rendering",
            details={"error": str(e)},
        )
    try:
        doc = pymupdf.open(str(pdf_path))
    except Exception as e:
        raise AppException(
            code=ErrorCode.CONVERSION_FAILED,
            message="Unable to open source PDF for scanned-page rendering",
            details={"path": str(pdf_path), "error": str(e)},
        )

    try:
        page = doc.load_page(int(page_index))
        _ensure_parent_dir(out_path)
        cs_rgb = getattr(pymupdf, "csRGB", None)
        try:
            if cs_rgb is not None:
                pix = page.get_pixmap(dpi=int(dpi), colorspace=cs_rgb, alpha=False)
            else:
                pix = page.get_pixmap(dpi=int(dpi), alpha=False)
        except TypeError:
            # Older/newer PyMuPDF versions may not accept colorspace/alpha arguments.
            pix = page.get_pixmap(dpi=int(dpi))
        pix.save(str(out_path))
        return pix
    except AppException:
        raise
    except Exception as e:
        raise AppException(
            code=ErrorCode.CONVERSION_FAILED,
            message="Failed to render scanned PDF page to image",
            details={"path": str(pdf_path), "page_index": page_index, "error": str(e)},
        )
    finally:
        doc.close()


def _estimate_baseline_ocr_line_height_pt(
    *,
    ocr_text_elements: list[dict[str, Any]],
    page_w_pt: float,
) -> float:
    """Estimate a "typical" OCR line height (pt) on scanned pages.

    Many scanned-slide OCR engines also detect lots of tiny UI text inside
    screenshots/diagrams. Using a raw median/low-quantile can be skewed toward
    those tiny boxes, which then breaks downstream heuristics (wrap decision,
    image-region detection, dedupe thresholds).

    We therefore:
    - filter invalid/extreme boxes
    - focus on the *widest* OCR lines (more likely slide body text)
    - compute a width-weighted upper-median (slightly biased toward larger text)
    """

    samples: list[tuple[float, float]] = []  # (height_pt, width_ratio)
    width_pt = max(1.0, float(page_w_pt))

    for el in ocr_text_elements:
        if not isinstance(el, dict):
            continue
        bbox_pt = el.get("bbox_pt")
        if not isinstance(bbox_pt, list) or len(bbox_pt) != 4:
            continue
        try:
            x0, y0, x1, y1 = _coerce_bbox_pt(bbox_pt)
        except Exception:
            continue
        w = max(0.0, float(x1 - x0))
        h = max(0.0, float(y1 - y0))
        if w <= 0.0 or h <= 0.0:
            continue
        # Filter extreme outliers.
        if h < 4.5 or h > 96.0:
            continue
        width_ratio = w / width_pt
        samples.append((float(h), float(width_ratio)))

    if not samples:
        return 12.0

    # Use only the widest OCR lines to avoid being skewed by many tiny UI
    # elements inside screenshots. For small sample sizes keep all.
    samples.sort(key=lambda t: float(t[1]), reverse=True)
    if len(samples) > 24:
        k = max(12, int(round(0.25 * float(len(samples)))))
        k = max(12, min(int(k), len(samples)))
        samples = samples[:k]

    # Compute a width-weighted quantile on heights. Squaring width_ratio makes
    # narrow UI lines contribute much less even when they are numerous.
    weighted: list[tuple[float, float]] = []
    for h, width_ratio in samples:
        wr = max(0.0, min(1.0, float(width_ratio)))
        weight = max(1e-4, float(wr) * float(wr))
        weighted.append((float(h), float(weight)))

    weighted.sort(key=lambda t: float(t[0]))
    total_w = sum(float(w) for _, w in weighted) or 1.0
    target = 0.60 * total_w
    acc = 0.0
    baseline = float(weighted[len(weighted) // 2][0])
    for h, w in weighted:
        acc += float(w)
        if acc >= target:
            baseline = float(h)
            break

    return max(6.0, min(48.0, float(baseline)))
