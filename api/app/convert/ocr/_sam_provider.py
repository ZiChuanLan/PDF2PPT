"""SAM (Segment Anything Model) polygon refinement provider.

Uses MobileSAM ViT-T to refine rectangular bboxes into precise polygon masks.
"""

import importlib.util
import logging
import shutil
import site
import subprocess
import sys
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
_SAM_RUNTIME_MODULES = ("mobile_sam", "torch", "torchvision", "timm")
_SAM_RUNTIME_TARGET_ENV_VARS = ("MOBILE_SAM_RUNTIME_TARGET", "SAM_RUNTIME_TARGET")
_SAM_PACKAGE_URL_ENV_VARS = ("MOBILE_SAM_PACKAGE_URL", "SAM_PACKAGE_URL")
_SAM_PYTORCH_INDEX_ENV_VARS = ("MOBILE_SAM_PYTORCH_INDEX_URL", "PYTORCH_CPU_INDEX_URL")
_DEFAULT_SAM_PACKAGE_URL = (
    "https://github.com/ChaoningZhang/MobileSAM/archive/"
    "f706ad9c4eb7f219c00d9050e46328518ffb65d2.zip"
)
_DEFAULT_PYTORCH_CPU_INDEX_URL = "https://download.pytorch.org/whl/cpu"
_SAM_RUNTIME_PIP_SPECS = (
    "torch==2.12.0+cpu",
    "torchvision==0.27.0+cpu",
    "timm==1.0.27",
)

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


def get_sam_package_url() -> str:
    """Return the configured MobileSAM Python package URL."""
    return _first_non_empty_env(_SAM_PACKAGE_URL_ENV_VARS) or _DEFAULT_SAM_PACKAGE_URL


def get_sam_pytorch_index_url() -> str:
    """Return the configured PyTorch CPU wheel index URL."""
    return _first_non_empty_env(_SAM_PYTORCH_INDEX_ENV_VARS) or _DEFAULT_PYTORCH_CPU_INDEX_URL


def get_sam_runtime_target_path() -> Path:
    """Return the persistent target path for downloaded SAM runtime packages."""
    import os

    configured = _first_non_empty_env(_SAM_RUNTIME_TARGET_ENV_VARS)
    if configured:
        return Path(configured).expanduser()
    data_dir = Path(os.environ.get("APP_DATA_DIR", "/app/data"))
    return data_dir / "python-packages" / "sam-runtime"


def _add_sam_runtime_target_to_path() -> None:
    runtime_path = get_sam_runtime_target_path()
    if not runtime_path.exists():
        return
    runtime_path_str = str(runtime_path)
    if runtime_path_str not in sys.path:
        site.addsitedir(runtime_path_str)


_add_sam_runtime_target_to_path()


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


def install_sam_runtime_dependencies(progress_callback: Any | None = None) -> bool:
    """Install MobileSAM runtime packages into persistent app data if missing.

    Returns True when an install command ran, False when the runtime was already
    available from the image or the persistent target.
    """
    _add_sam_runtime_target_to_path()
    if not get_sam_runtime_issues():
        return False

    runtime_path = get_sam_runtime_target_path()
    runtime_path.mkdir(parents=True, exist_ok=True)
    package_url = get_sam_package_url()
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-cache-dir",
        "--target",
        str(runtime_path),
        "--upgrade",
        "--extra-index-url",
        get_sam_pytorch_index_url(),
        *_SAM_RUNTIME_PIP_SPECS,
        package_url,
    ]

    if progress_callback is not None:
        progress_callback(0.0, "正在下载 SAM 运行依赖…")
    logger.info("Installing SAM runtime packages into %s", runtime_path)
    try:
        subprocess.run(cmd, check=True, text=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        output = "\n".join(
            part for part in ((e.stdout or "").strip(), (e.stderr or "").strip()) if part
        )
        raise RuntimeError(f"SAM runtime dependency installation failed: {output or e}") from e

    importlib.invalidate_caches()
    _add_sam_runtime_target_to_path()
    issues = get_sam_runtime_issues()
    if issues:
        raise RuntimeError(format_sam_runtime_error(issues))
    if progress_callback is not None:
        progress_callback(0.2, "SAM 运行依赖安装完成")
    logger.info("SAM runtime packages installed")
    return True


def _ensure_model() -> Any:
    global _predictor, _model_loaded

    if _model_loaded:
        return _predictor

    runtime_issues = get_sam_runtime_issues()
    if runtime_issues:
        raise RuntimeError(format_sam_runtime_error(runtime_issues))

    try:
        from mobile_sam import sam_model_registry, SamPredictor
    except ImportError as e:
        raise RuntimeError(
            "SAM runtime import failed after dependency probe. "
            f"Rebuild the API/worker image or install MobileSAM runtime dependencies. Original error: {e}"
        ) from e

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
    _add_sam_runtime_target_to_path()
    return importlib.util.find_spec("mobile_sam") is not None


def get_sam_runtime_issues() -> list[str]:
    """Return missing runtime dependency issue codes for MobileSAM."""
    _add_sam_runtime_target_to_path()
    issues: list[str] = []
    for module_name in _SAM_RUNTIME_MODULES:
        if importlib.util.find_spec(module_name) is None:
            issues.append(f"{module_name}_not_installed")
    return issues


def is_sam_runtime_available() -> bool:
    """Check whether all Python runtime dependencies for MobileSAM are installed."""
    return not get_sam_runtime_issues()


def format_sam_runtime_error(issues: list[str]) -> str:
    missing = ", ".join(issue.removesuffix("_not_installed") for issue in issues)
    return (
        "SAM runtime dependencies are missing: "
        f"{missing}. Use the SAM download action to install MobileSAM runtime "
        "packages into persistent app data, or configure the Docker image with "
        "MobileSAM, torch, torchvision, and timm."
    )


def is_sam_available() -> bool:
    """Check if SAM can be loaded (package installed AND checkpoint downloaded)."""
    return is_sam_runtime_available() and is_sam_checkpoint_downloaded()
