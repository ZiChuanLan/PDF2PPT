from __future__ import annotations

from typing import Any


def clamp_bbox_px(bbox: list[float], width: int, height: int) -> list[float] | None:
    if len(bbox) != 4:
        return None
    x0, y0, x1, y1 = [float(v) for v in bbox]
    x0 = max(0.0, min(x0, float(max(0, width - 1))))
    y0 = max(0.0, min(y0, float(max(0, height - 1))))
    x1 = max(0.0, min(x1, float(max(0, width))))
    y1 = max(0.0, min(y1, float(max(0, height))))
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
    sx = float(page_width_pt) / max(1.0, float(image_width_px))
    sy = float(page_height_pt) / max(1.0, float(image_height_px))
    return [x0 * sx, y0 * sy, x1 * sx, y1 * sy]


def normalize_bbox_to_px(
    *,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    width: int,
    height: int,
) -> list[float] | None:
    max_abs = max(abs(x0), abs(y0), abs(x1), abs(y1))
    candidates: list[list[float]] = [[x0, y0, x1, y1]]

    if max_abs <= 1.5:
        candidates.append([x0 * width, y0 * height, x1 * width, y1 * height])

    if max_abs <= 1200.0 and (width >= 1400 or height >= 1400):
        candidates.append(
            [
                (x0 / 1000.0) * width,
                (y0 / 1000.0) * height,
                (x1 / 1000.0) * width,
                (y1 / 1000.0) * height,
            ]
        )

    for candidate in candidates:
        clamped = clamp_bbox_px(candidate, width, height)
        if clamped is not None:
            return clamped
    return None


def parse_bbox_candidate(raw_bbox: Any) -> tuple[float, float, float, float] | None:
    def _to_float(value: Any) -> float | None:
        try:
            return float(value)
        except Exception:
            return None

    if isinstance(raw_bbox, dict):
        x0 = _to_float(raw_bbox.get("x0"))
        y0 = _to_float(raw_bbox.get("y0"))
        x1 = _to_float(raw_bbox.get("x1"))
        y1 = _to_float(raw_bbox.get("y1"))
        if None not in (x0, y0, x1, y1):
            return float(x0), float(y0), float(x1), float(y1)

        left = _to_float(raw_bbox.get("left"))
        top = _to_float(raw_bbox.get("top"))
        right = _to_float(raw_bbox.get("right"))
        bottom = _to_float(raw_bbox.get("bottom"))
        if None not in (left, top, right, bottom):
            return float(left), float(top), float(right), float(bottom)

        width = _to_float(raw_bbox.get("width"))
        height = _to_float(raw_bbox.get("height"))
        if None not in (left, top, width, height):
            return float(left), float(top), float(left) + float(width), float(top) + float(height)

    if isinstance(raw_bbox, (list, tuple)):
        seq = list(raw_bbox)
        if len(seq) == 4:
            vals = [_to_float(v) for v in seq]
            if all(v is not None for v in vals):
                x0, y0, x1, y1 = [float(v) for v in vals if v is not None]
                return x0, y0, x1, y1

        if len(seq) == 8:
            vals = [_to_float(v) for v in seq]
            if all(v is not None for v in vals):
                nums = [float(v) for v in vals if v is not None]
                xs = nums[0::2]
                ys = nums[1::2]
                return min(xs), min(ys), max(xs), max(ys)

        if len(seq) >= 4 and all(isinstance(p, (list, tuple)) and len(p) >= 2 for p in seq):
            xs: list[float] = []
            ys: list[float] = []
            for point in seq:
                px = _to_float(point[0])
                py = _to_float(point[1])
                if px is None or py is None:
                    continue
                xs.append(float(px))
                ys.append(float(py))
            if xs and ys:
                return min(xs), min(ys), max(xs), max(ys)

    return None
