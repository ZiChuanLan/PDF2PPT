"""SAM (Segment Anything Model) polygon refinement provider.

Uses MobileSAM ViT-T to refine rectangular bboxes into precise polygon masks.
"""

import logging
from pathlib import Path
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)

_SAM_CHECKPOINT_URL = (
    "https://github.com/ChaoningZhang/MobileSAM/raw/master/weights/mobile_sam.pt"
)

_predictor: Any = None
_model_loaded = False


def _get_checkpoint_path() -> Path:
    import os

    data_dir = Path(os.environ.get("APP_DATA_DIR", "/app/data"))
    return data_dir / "models" / "sam" / "mobile_sam.pt"


def _download_checkpoint(path: Path) -> None:
    import urllib.request

    path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Downloading MobileSAM checkpoint from %s ...", _SAM_CHECKPOINT_URL)
    urllib.request.urlretrieve(_SAM_CHECKPOINT_URL, str(path))
    logger.info("Downloaded to %s", path)


def _ensure_model() -> Any:
    global _predictor, _model_loaded

    if _model_loaded:
        return _predictor

    try:
        from mobile_sam import sam_model_registry, SamPredictor
    except ImportError:
        raise RuntimeError(
            "mobile_sam package not installed. "
            "Install with: pip install git+https://github.com/ChaoningZhang/MobileSAM.git"
        )

    ckpt_path = _get_checkpoint_path()
    if not ckpt_path.exists():
        _download_checkpoint(ckpt_path)

    logger.info("Loading MobileSAM model...")
    sam = sam_model_registry["vit_t"](checkpoint=str(ckpt_path))
    sam.to(device="cpu")
    sam.eval()
    _predictor = SamPredictor(sam)
    _model_loaded = True
    logger.info("MobileSAM model loaded")
    return _predictor


def refine_bbox_to_polygon(
    image_rgb: np.ndarray,
    bbox: list[float],
    *,
    epsilon_ratio: float = 0.005,
) -> list[list[int]] | None:
    """Refine a rectangular bbox into a polygon using SAM.

    Args:
        image_rgb: RGB image as numpy array (H, W, 3)
        bbox: [x1, y1, x2, y2] bounding box
        epsilon_ratio: Douglas-Peucker epsilon as ratio of perimeter

    Returns:
        List of [x, y] polygon vertices, or None if refinement fails.
    """
    try:
        predictor = _ensure_model()
    except Exception as e:
        logger.warning("SAM model unavailable: %s", e)
        return None

    try:
        predictor.set_image(image_rgb)
        box_np = np.array(bbox)
        masks, scores, _ = predictor.predict(box=box_np, multimask_output=True)

        best_idx = np.argmax(scores)
        mask = masks[best_idx]

        mask_uint8 = (mask.astype(np.uint8) * 255)
        contours, _ = cv2.findContours(
            mask_uint8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        if not contours:
            return None

        largest = max(contours, key=cv2.contourArea)
        if cv2.contourArea(largest) < 100:
            return None

        perimeter = cv2.arcLength(largest, True)
        epsilon = epsilon_ratio * perimeter
        approx = cv2.approxPolyDP(largest, epsilon, True)

        points = approx.squeeze().tolist()
        if isinstance(points[0], (int, float)):
            points = [points]
        if len(points) < 3:
            return None

        return [[int(p[0]), int(p[1])] for p in points]

    except Exception as e:
        logger.warning("SAM refinement failed: %s", e)
        return None


def refine_image_regions(
    image_path: str,
    image_regions: list[Any],
    *,
    epsilon_ratio: float = 0.005,
) -> list[Any]:
    """Refine image region bboxes into polygon payloads.

    Args:
        image_path: Path to the source image
        image_regions: List of bbox arrays [x1, y1, x2, y2]
        epsilon_ratio: Douglas-Peucker epsilon ratio

    Returns:
        List of refined image region payloads (dict with polygon or bbox fallback).
    """
    try:
        from PIL import Image

        img = Image.open(image_path).convert("RGB")
        img_rgb = np.array(img)
    except Exception as e:
        logger.warning("Failed to load image for SAM: %s", e)
        return image_regions

    refined: list[Any] = []
    for region in image_regions:
        if isinstance(region, dict):
            bbox = region.get("bbox", [])
        elif isinstance(region, (list, tuple)) and len(region) >= 4:
            bbox = list(region[:4])
        else:
            refined.append(region)
            continue

        if len(bbox) < 4:
            refined.append(region)
            continue

        polygon = refine_bbox_to_polygon(img_rgb, bbox, epsilon_ratio=epsilon_ratio)

        if polygon is not None and len(polygon) >= 3:
            # Check if polygon is meaningfully non-rectangular
            xs = [p[0] for p in polygon]
            ys = [p[1] for p in polygon]
            is_rect = (
                len(polygon) == 4
                and len(set(xs)) <= 2
                and len(set(ys)) <= 2
            )

            if not is_rect:
                refined.append({
                    "bbox": [float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])],
                    "geometry_kind": "polygon",
                    "geometry_points": polygon,
                    "geometry_source": "sam",
                })
                logger.info(
                    "SAM refined bbox %s -> %d-point polygon",
                    [int(b) for b in bbox],
                    len(polygon),
                )
                continue

        # Fallback: keep original bbox
        refined.append(region)

    return refined


def is_sam_available() -> bool:
    """Check if SAM can be loaded (package installed + checkpoint accessible)."""
    try:
        import mobile_sam  # noqa: F401 - needed to check availability
        return True
    except ImportError:
        return False
