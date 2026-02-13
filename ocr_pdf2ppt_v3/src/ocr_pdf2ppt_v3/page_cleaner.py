from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageFilter

from .geometry import clamp_bbox_px
from .models import OcrLine, VisualRegion

try:
    import cv2  # type: ignore
    import numpy as np

    _HAS_CV2 = True
except Exception:
    _HAS_CV2 = False


def erase_regions(
    image_path: Path,
    bboxes: list[list[float]],
    out_path: Path,
    *,
    padding_px: int = 2,
    inpaint_radius: float = 2.0,
    inpaint_method: str = "ns",
) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.open(image_path).convert("RGB")
    width, height = image.size

    regions: list[tuple[int, int, int, int]] = []
    for bbox_raw in bboxes:
        bbox = clamp_bbox_px([float(v) for v in bbox_raw], width, height)
        if bbox is None:
            continue
        x0, y0, x1, y1 = bbox
        xi0 = max(0, int(round(x0)) - padding_px)
        yi0 = max(0, int(round(y0)) - padding_px)
        xi1 = min(width, int(round(x1)) + padding_px)
        yi1 = min(height, int(round(y1)) + padding_px)
        if xi1 <= xi0 or yi1 <= yi0:
            continue
        regions.append((xi0, yi0, xi1, yi1))

    if not regions:
        image.save(out_path)
        return out_path

    if _HAS_CV2:
        arr = np.array(image)
        mask = np.zeros((height, width), dtype=np.uint8)
        for x0, y0, x1, y1 in regions:
            mask[y0:y1, x0:x1] = 255
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        mask = cv2.dilate(mask, kernel, iterations=1)
        method_flag = cv2.INPAINT_NS if str(inpaint_method or "").lower() == "ns" else cv2.INPAINT_TELEA
        inpainted = cv2.inpaint(arr, mask, float(inpaint_radius), method_flag)
        Image.fromarray(inpainted).save(out_path)
        return out_path

    blurred = image.filter(ImageFilter.GaussianBlur(radius=1.2))
    src = image.load()
    rep = blurred.load()
    for x0, y0, x1, y1 in regions:
        for y in range(y0, y1):
            for x in range(x0, x1):
                src[x, y] = rep[x, y]
    image.save(out_path)
    return out_path


def erase_text_regions(
    image_path: Path,
    ocr_lines: list[OcrLine],
    out_path: Path,
    *,
    padding_px: int = 2,
    inpaint_radius: float = 2.0,
    inpaint_method: str = "ns",
) -> Path:
    return erase_regions(
        image_path=image_path,
        bboxes=[line.bbox for line in ocr_lines],
        out_path=out_path,
        padding_px=padding_px,
        inpaint_radius=inpaint_radius,
        inpaint_method=inpaint_method,
    )


def erase_text_and_image_regions(
    image_path: Path,
    ocr_lines: list[OcrLine],
    image_regions: list[VisualRegion],
    out_path: Path,
    *,
    padding_px: int = 2,
    inpaint_radius: float = 2.0,
    inpaint_method: str = "ns",
    erase_image_regions: bool = False,
) -> Path:
    bboxes = [line.bbox for line in ocr_lines]
    if erase_image_regions:
        bboxes.extend(region.bbox for region in image_regions)
    return erase_regions(
        image_path=image_path,
        bboxes=bboxes,
        out_path=out_path,
        padding_px=padding_px,
        inpaint_radius=inpaint_radius,
        inpaint_method=inpaint_method,
    )
