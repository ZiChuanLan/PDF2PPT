"""NotebookLM footer detection and cleanup utilities."""

from pathlib import Path
from typing import Any

from ..bbox_utils import _coerce_bbox_pt, _compute_text_erase_padding_pt
from ..scanned_page import _sample_bbox_background_rgb
from .markdown_utils import _normalize_footer_brand_text


def _is_notebooklm_footer_brand_normalized(normalized: str) -> bool:
    value = str(normalized or "").strip().lower()
    if not value:
        return False
    if "notebooklm" not in value:
        return False
    extra = value.replace("notebooklm", "")
    return len(extra) <= 24


def _is_notebooklm_footer_text_element(
    el: dict[str, Any],
    *,
    page_w_pt: float,
    page_h_pt: float,
) -> bool:
    raw_text = str(el.get("text") or "").strip()
    if not raw_text:
        return False

    normalized = _normalize_footer_brand_text(raw_text)
    if not _is_notebooklm_footer_brand_normalized(normalized):
        return False

    try:
        x0, y0, x1, y1 = _coerce_bbox_pt(el.get("bbox_pt"))
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


def _detect_notebooklm_footer_bbox_from_render(
    *,
    render_path: Path,
    page_w_pt: float,
    page_h_pt: float,
) -> list[float] | None:
    """OCR the bottom-right footer area to recover small NotebookLM branding."""

    try:
        from PIL import Image, ImageOps
        import pytesseract
        from pytesseract import Output
    except Exception:
        return None

    try:
        img = Image.open(render_path).convert("RGB")
    except Exception:
        return None

    width_px, height_px = img.size
    if width_px <= 0 or height_px <= 0 or page_w_pt <= 0.0 or page_h_pt <= 0.0:
        return None

    crop_x0_px = max(0, min(width_px - 1, int(round(0.72 * float(width_px)))))
    crop_y0_px = max(0, min(height_px - 1, int(round(0.84 * float(height_px)))))
    if crop_x0_px >= width_px or crop_y0_px >= height_px:
        return None

    crop = img.crop((crop_x0_px, crop_y0_px, width_px, height_px))
    if crop.width <= 2 or crop.height <= 2:
        return None

    scale = 2 if max(crop.size) < 700 else 1
    ocr_img = ImageOps.autocontrast(crop.convert("L"))
    if scale > 1:
        ocr_img = ocr_img.resize(
            (int(ocr_img.width * scale), int(ocr_img.height * scale)),
            Image.Resampling.LANCZOS,
        )

    scale_x = float(crop.width) / float(ocr_img.width)
    scale_y = float(crop.height) / float(ocr_img.height)

    def _iter_line_candidates(data: dict[str, Any]) -> list[tuple[int, int, int, int]]:
        texts = data.get("text") or []
        lefts = data.get("left") or []
        tops = data.get("top") or []
        widths = data.get("width") or []
        heights = data.get("height") or []
        block_nums = data.get("block_num") or []
        par_nums = data.get("par_num") or []
        line_nums = data.get("line_num") or []
        confs = data.get("conf") or []

        words_by_line: dict[tuple[int, int, int], list[dict[str, Any]]] = {}
        count = min(
            len(texts),
            len(lefts),
            len(tops),
            len(widths),
            len(heights),
            len(block_nums),
            len(par_nums),
            len(line_nums),
            len(confs),
        )
        for idx in range(count):
            text = str(texts[idx] or "").strip()
            if not text:
                continue
            try:
                conf = float(confs[idx])
            except Exception:
                conf = -1.0
            if conf < -0.5:
                continue
            try:
                key = (
                    int(block_nums[idx] or 0),
                    int(par_nums[idx] or 0),
                    int(line_nums[idx] or 0),
                )
                word = {
                    "text": text,
                    "left": int(lefts[idx] or 0),
                    "top": int(tops[idx] or 0),
                    "right": int(lefts[idx] or 0) + int(widths[idx] or 0),
                    "bottom": int(tops[idx] or 0) + int(heights[idx] or 0),
                }
            except Exception:
                continue
            words_by_line.setdefault(key, []).append(word)

        candidates: list[tuple[int, int, int, int]] = []
        for words in words_by_line.values():
            words.sort(key=lambda item: (int(item["left"]), int(item["top"])))
            for start in range(len(words)):
                for end in range(start, min(len(words), start + 3)):
                    segment = words[start : end + 1]
                    normalized = _normalize_footer_brand_text(
                        "".join(str(item["text"]) for item in segment)
                    )
                    if not _is_notebooklm_footer_brand_normalized(normalized):
                        continue
                    x0 = min(int(item["left"]) for item in segment)
                    y0 = min(int(item["top"]) for item in segment)
                    x1 = max(int(item["right"]) for item in segment)
                    y1 = max(int(item["bottom"]) for item in segment)
                    candidates.append((x0, y0, x1, y1))
        return candidates

    best_bbox_px: tuple[int, int, int, int] | None = None
    for psm in (6, 11):
        try:
            data = pytesseract.image_to_data(
                ocr_img,
                output_type=Output.DICT,
                lang="eng",
                config=f"--psm {int(psm)}",
            )
        except Exception:
            continue
        line_candidates = _iter_line_candidates(data)
        if not line_candidates:
            continue
        best_bbox_px = max(
            line_candidates,
            key=lambda bb: ((bb[3] - bb[1]), (bb[1] + bb[3]), (bb[2] - bb[0])),
        )
        break

    if best_bbox_px is None:
        return None

    bx0, by0, bx1, by1 = best_bbox_px
    px0 = crop_x0_px + (float(bx0) * scale_x)
    py0 = crop_y0_px + (float(by0) * scale_y)
    px1 = crop_x0_px + (float(bx1) * scale_x)
    py1 = crop_y0_px + (float(by1) * scale_y)
    if px1 <= px0 or py1 <= py0:
        return None

    x0_pt = (px0 / float(width_px)) * float(page_w_pt)
    y0_pt = (py0 / float(height_px)) * float(page_h_pt)
    x1_pt = (px1 / float(width_px)) * float(page_w_pt)
    y1_pt = (py1 / float(height_px)) * float(page_h_pt)
    return [x0_pt, y0_pt, x1_pt, y1_pt]


def _build_notebooklm_footer_fill_overlays(
    *,
    footer_elements: list[dict[str, Any]],
    render_pix: Any | None,
    page_h_pt: float,
    scanned_render_dpi: int,
    text_erase_mode: str,
) -> list[tuple[list[float], tuple[int, int, int]]]:
    """Return local fill overlays for NotebookLM footer cleanup on text pages."""

    if render_pix is None or not footer_elements:
        return []

    overlays: list[tuple[list[float], tuple[int, int, int]]] = []
    for el in footer_elements:
        try:
            x0, y0, x1, y1 = _coerce_bbox_pt(el.get("bbox_pt"))
        except Exception:
            continue
        if x1 <= x0 or y1 <= y0:
            continue
        bbox_h_pt = max(1.0, y1 - y0)
        pad_x_pt, pad_y_pt = _compute_text_erase_padding_pt(
            bbox_h_pt=bbox_h_pt,
            text_erase_mode=text_erase_mode,
        )
        fill_rgb = _sample_bbox_background_rgb(
            render_pix,
            bbox_pt=[x0, y0, x1, y1],
            page_height_pt=float(page_h_pt),
            dpi=int(scanned_render_dpi),
        )
        overlays.append(
            (
                [x0 - pad_x_pt, y0 - pad_y_pt, x1 + pad_x_pt, y1 + pad_y_pt],
                fill_rgb,
            )
        )
    return overlays
