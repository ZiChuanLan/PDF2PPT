"""SAM (Segment Anything Model) polygon refinement provider.

Uses MobileSAM ViT-T to refine rectangular bboxes into precise polygon masks.
"""

import importlib.util
import logging
import shutil
from pathlib import Path
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)

_SAM_CHECKPOINT_URL = (
    "https://github.com/ChaoningZhang/MobileSAM/raw/master/weights/mobile_sam.pt"
)
_SAM_CHECKPOINT_URL_ENV_VARS = ("MOBILE_SAM_CHECKPOINT_URL", "SAM_CHECKPOINT_URL")
_SAM_CHECKPOINT_PATH_ENV_VARS = ("MOBILE_SAM_CHECKPOINT_PATH", "SAM_CHECKPOINT_PATH")

_predictor: Any = None
_model_loaded = False


def _first_non_empty_env(names: tuple[str, ...]) -> str | None:
    import os

    for name in names:
        value = os.environ.get(name)
        if value and value.strip():
            return value.strip()
    return None


def get_sam_checkpoint_url() -> str:
    """Return the configured MobileSAM checkpoint URL."""
    return _first_non_empty_env(_SAM_CHECKPOINT_URL_ENV_VARS) or _SAM_CHECKPOINT_URL


def get_sam_checkpoint_source_path() -> Path | None:
    """Return a configured local MobileSAM checkpoint source path, if any."""
    configured = _first_non_empty_env(_SAM_CHECKPOINT_PATH_ENV_VARS)
    if not configured:
        return None
    return Path(configured).expanduser()


def _get_checkpoint_path() -> Path:
    import os

    data_dir = Path(os.environ.get("APP_DATA_DIR", "/app/data"))
    return data_dir / "models" / "sam" / "mobile_sam.pt"


def _download_checkpoint(path: Path, reporthook: Any | None = None) -> None:
    import urllib.request

    path.parent.mkdir(parents=True, exist_ok=True)

    source_path = get_sam_checkpoint_source_path()
    if source_path is not None:
        if not source_path.exists() or not source_path.is_file():
            raise RuntimeError(
                "Configured MobileSAM checkpoint file does not exist: "
                f"{source_path}. Set MOBILE_SAM_CHECKPOINT_PATH or "
                "SAM_CHECKPOINT_PATH to an existing mobile_sam.pt file."
            )

        try:
            if source_path.resolve() == path.resolve():
                logger.info("MobileSAM checkpoint already installed at %s", path)
                if reporthook is not None:
                    reporthook(1, 1, 1)
                return
        except OSError:
            pass

        logger.info("Installing MobileSAM checkpoint from local file %s", source_path)
        shutil.copy2(source_path, path)
        if reporthook is not None:
            reporthook(1, 1, 1)
        logger.info("Installed MobileSAM checkpoint to %s", path)
        return

    checkpoint_url = get_sam_checkpoint_url()
    logger.info("Downloading MobileSAM checkpoint from %s ...", checkpoint_url)
    urllib.request.urlretrieve(checkpoint_url, str(path), reporthook)
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
        raise RuntimeError(
            "SAM checkpoint not found. Please download it from the Settings page first."
        )

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


def is_sam_checkpoint_downloaded() -> bool:
    """Check if the SAM checkpoint file exists on disk."""
    return _get_checkpoint_path().exists()


def is_sam_package_available() -> bool:
    """Check if the MobileSAM Python package is importable."""
    return importlib.util.find_spec("mobile_sam") is not None


def is_sam_available() -> bool:
    """Check if SAM can be loaded (package installed AND checkpoint downloaded)."""
    return is_sam_package_available() and is_sam_checkpoint_downloaded()
