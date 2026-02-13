from __future__ import annotations


def clamp_bbox_px(bbox: list[float], width: int, height: int) -> list[float] | None:
    if len(bbox) != 4:
        return None
    x0, y0, x1, y1 = [float(v) for v in bbox]
    x0 = max(0.0, min(x0, float(width - 1)))
    y0 = max(0.0, min(y0, float(height - 1)))
    x1 = max(0.0, min(x1, float(width)))
    y1 = max(0.0, min(y1, float(height)))
    if x1 <= x0 or y1 <= y0:
        return None
    return [x0, y0, x1, y1]


def px_bbox_to_pt_bbox(
    bbox: list[float],
    image_width_px: int,
    image_height_px: int,
    page_width_pt: float,
    page_height_pt: float,
) -> list[float]:
    x0, y0, x1, y1 = bbox
    sx = float(page_width_pt) / float(image_width_px)
    sy = float(page_height_pt) / float(image_height_px)
    return [x0 * sx, y0 * sy, x1 * sx, y1 * sy]
