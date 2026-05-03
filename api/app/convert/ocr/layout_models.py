"""Unified layout model registry and provider abstraction.

Supports PP-DocLayout (PaddleX) and DocLayout-YOLO models with a common
``LayoutModelProvider`` protocol so callers don't need to know about the
underlying implementation.
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.convert.ocr.base import _clean_str

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Model metadata
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LayoutModelInfo:
    """Metadata for a single layout model variant."""

    model_id: str  # e.g. "pp_doclayout_v3"
    display_name: str  # e.g. "PP-DocLayoutV3"
    provider: str  # "paddlex" or "doclayout_yolo"
    size_mb: float  # Approximate download size
    speed_label: str  # e.g. "8ms GPU / 14ms CPU"
    accuracy: str  # e.g. "70.9% mAP"
    description: str  # Short description (Chinese)
    paddlex_model_name: str | None  # For paddlex: "PP-DocLayoutV3", etc.
    recommended: bool  # Whether to recommend in setup wizard


LAYOUT_MODELS: dict[str, LayoutModelInfo] = {
    "pp_doclayout_s": LayoutModelInfo(
        model_id="pp_doclayout_s",
        display_name="PP-DocLayout-S",
        provider="paddlex",
        size_mb=1.2,
        speed_label="8ms GPU / 14ms CPU",
        accuracy="70.9% mAP",
        description="超轻量，适合 CPU 和边缘设备",
        paddlex_model_name="PP-DocLayout-S",
        recommended=False,
    ),
    "pp_doclayout_m": LayoutModelInfo(
        model_id="pp_doclayout_m",
        display_name="PP-DocLayout-M",
        provider="paddlex",
        size_mb=23.0,
        speed_label="13ms GPU / 43ms CPU",
        accuracy="75.2% mAP",
        description="均衡型，速度与精度兼顾",
        paddlex_model_name="PP-DocLayout-M",
        recommended=False,
    ),
    "pp_doclayout_l": LayoutModelInfo(
        model_id="pp_doclayout_l",
        display_name="PP-DocLayout-L",
        provider="paddlex",
        size_mb=124.0,
        speed_label="34ms GPU / 503ms CPU",
        accuracy="90.4% mAP",
        description="高精度，适合复杂版式文档",
        paddlex_model_name="PP-DocLayout-L",
        recommended=False,
    ),
    "pp_doclayout_v3": LayoutModelInfo(
        model_id="pp_doclayout_v3",
        display_name="PP-DocLayoutV3",
        provider="paddlex",
        size_mb=126.0,
        speed_label="24ms GPU",
        accuracy="25 类 + 阅读序",
        description="默认推荐，支持 25 类版面元素与阅读序",
        paddlex_model_name="PP-DocLayoutV3",
        recommended=True,
    ),
    "doclayout_yolo": LayoutModelInfo(
        model_id="doclayout_yolo",
        display_name="DocLayout-YOLO",
        provider="doclayout_yolo",
        size_mb=10.0,
        speed_label="极快 (YOLO)",
        accuracy="93.4% AP50 (DocLayNet)",
        description="YOLO 架构，速度极快，通用文档适用",
        paddlex_model_name=None,
        recommended=False,
    ),
}

DEFAULT_LAYOUT_MODEL_ID = "pp_doclayout_v3"


# ---------------------------------------------------------------------------
# Provider protocol
# ---------------------------------------------------------------------------


class LayoutModelProvider(Protocol):
    """Protocol for layout model inference."""

    def predict(self, image_path: str) -> list[dict[str, Any]]:
        """Run layout analysis on an image.

        Returns list of dicts with keys:
        - label: str — element label (e.g. "text", "figure")
        - score: float — confidence score
        - bbox: list[float] — [x0, y0, x1, y1]
        - order: int | None — reading order (optional)
        """
        ...


# ---------------------------------------------------------------------------
# Concrete providers
# ---------------------------------------------------------------------------


class PaddleXLayoutProvider:
    """PP-DocLayout provider using PaddleX."""

    def __init__(self, model_name: str) -> None:
        try:
            import paddlex
        except ImportError as e:
            raise RuntimeError(
                "paddlex package is required for PP-DocLayout models. "
                "Install with: pip install paddlex"
            ) from e

        self._model = paddlex.create_model(model_name)

    def predict(self, image_path: str) -> list[dict[str, Any]]:
        results = self._model.predict(image_path)
        items: list[dict[str, Any]] = []
        for result in results:
            if hasattr(result, "json"):
                data = result.json()
            elif isinstance(result, dict):
                data = result
            else:
                continue

            # PaddleX returns {"res": {"boxes": [...]}} or similar
            boxes = data.get("res", {}).get("boxes", []) if isinstance(data, dict) else []
            for box in boxes:
                items.append({
                    "label": box.get("label", ""),
                    "score": box.get("score", 0.0),
                    "bbox": box.get("coordinate", [0, 0, 0, 0]),
                    "order": box.get("reading_order"),
                })
        return items


class DocLayoutYoloProvider:
    """DocLayout-YOLO provider."""

    def __init__(self) -> None:
        try:
            from doclayout_yolo import DocLayoutYOLO
        except ImportError as e:
            raise RuntimeError(
                "doclayout-yolo package is required. "
                "Install with: pip install doclayout-yolo"
            ) from e

        # Download model from HuggingFace if not cached
        model_path = self._ensure_model_weights()
        self._model = DocLayoutYOLO(model_path)

    @staticmethod
    def _ensure_model_weights() -> str:
        """Ensure DocLayout-YOLO model weights are downloaded."""
        cache_dir = Path(os.getenv("MODEL_CACHE_DIR", "/app/data/models"))
        model_path = cache_dir / "doclayout_yolo" / "docstructbench_imgsz1024.onnx"
        if model_path.exists():
            return str(model_path)

        try:
            from huggingface_hub import hf_hub_download

            downloaded = hf_hub_download(
                repo_id="juliozhao/DocLayout-YOLO-DocStructBench",
                filename="docstructbench_imgsz1024.onnx",
                local_dir=str(model_path.parent),
            )
            return downloaded
        except Exception as e:
            raise RuntimeError(
                f"Failed to download DocLayout-YOLO weights: {e}"
            ) from e

    def predict(self, image_path: str) -> list[dict[str, Any]]:
        results = self._model.predict(image_path, imgsz=1024, conf=0.2)
        items: list[dict[str, Any]] = []
        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue
            for i in range(len(boxes)):
                xyxy = boxes.xyxy[i].tolist()
                items.append({
                    "label": result.names[int(boxes.cls[i])] if result.names else str(int(boxes.cls[i])),
                    "score": float(boxes.conf[i]),
                    "bbox": xyxy,
                    "order": None,
                })
        return items


# ---------------------------------------------------------------------------
# Provider cache (thread-safe singleton per model_id)
# ---------------------------------------------------------------------------

_provider_cache: dict[str, LayoutModelProvider] = {}
_provider_lock = threading.Lock()


def get_layout_model(model_id: str) -> LayoutModelProvider:
    """Get a layout model provider by ID. Raises if not available."""
    info = LAYOUT_MODELS.get(model_id)
    if info is None:
        raise ValueError(f"Unknown layout model: {model_id}")

    with _provider_lock:
        if model_id in _provider_cache:
            return _provider_cache[model_id]

        if info.provider == "paddlex":
            assert info.paddlex_model_name is not None
            provider = PaddleXLayoutProvider(info.paddlex_model_name)
        elif info.provider == "doclayout_yolo":
            provider = DocLayoutYoloProvider()
        else:
            raise ValueError(f"Unknown provider: {info.provider}")

        _provider_cache[model_id] = provider
        return provider


def is_model_downloaded(model_id: str) -> bool:
    """Check if a model's weights are locally available.

    For PaddleX models: checks if paddlex can resolve the model cache.
    For DocLayout-YOLO: checks if the ONNX weights file exists.
    """
    info = LAYOUT_MODELS.get(model_id)
    if info is None:
        return False

    if info.provider == "paddlex":
        return _is_paddlex_model_cached(info)
    elif info.provider == "doclayout_yolo":
        return _is_doclayout_yolo_cached()
    return False


def _is_paddlex_model_cached(info: LayoutModelInfo) -> bool:
    """Check if a PaddleX model is cached locally."""
    try:
        import paddlex
    except ImportError:
        return False

    # PaddleX caches models in ~/.paddlex/official_models or similar
    # The most reliable check is to see if the model directory exists
    try:
        home = Path.home()
        paddlex_cache = home / ".paddlex" / "official_models"
        if not paddlex_cache.exists():
            # Try the PaddleX default cache location
            from paddlex.utils.cache import CACHE_DIR  # type: ignore[import-untyped]

            paddlex_cache = Path(CACHE_DIR) / "official_models"
    except Exception:
        paddlex_cache = Path.home() / ".paddlex" / "official_models"

    if not paddlex_cache.exists():
        return False

    # Model directory name pattern: lowercase with hyphens
    model_dir_name = (info.paddlex_model_name or "").lower().replace("-", "_")
    model_dir = paddlex_cache / model_dir_name
    if model_dir.exists() and any(model_dir.iterdir()):
        return True

    # Fallback: check for any directory matching the model name pattern
    for d in paddlex_cache.iterdir():
        if d.is_dir() and model_dir_name in d.name.lower():
            if any(d.iterdir()):
                return True

    return False


def _is_doclayout_yolo_cached() -> bool:
    """Check if DocLayout-YOLO weights are cached."""
    cache_dir = Path(os.getenv("MODEL_CACHE_DIR", "/app/data/models"))
    model_path = cache_dir / "doclayout_yolo" / "docstructbench_imgsz1024.onnx"
    return model_path.exists()


def download_model(model_id: str) -> bool:
    """Download a model. Returns True on success.

    For PaddleX: triggers paddlex.create_model() which auto-downloads.
    For DocLayout-YOLO: downloads from HuggingFace.
    """
    info = LAYOUT_MODELS.get(model_id)
    if info is None:
        raise ValueError(f"Unknown layout model: {model_id}")

    if info.provider == "paddlex":
        return _download_paddlex_model(info)
    elif info.provider == "doclayout_yolo":
        return _download_doclayout_yolo()
    return False


def _download_paddlex_model(info: LayoutModelInfo) -> bool:
    """Download a PaddleX model by creating it (triggers auto-download)."""
    try:
        import paddlex

        assert info.paddlex_model_name is not None
        logger.info("Starting PaddleX model download: %s", info.paddlex_model_name)
        paddlex.create_model(info.paddlex_model_name)
        logger.info("PaddleX model download complete: %s", info.paddlex_model_name)
        return True
    except ImportError:
        raise RuntimeError(
            "paddlex package is not installed. Install with: pip install paddlex"
        )
    except Exception as e:
        logger.exception("PaddleX model download failed: %s", e)
        raise RuntimeError(f"PaddleX model download failed: {e}") from e


def _download_doclayout_yolo() -> bool:
    """Download DocLayout-YOLO model weights."""
    try:
        from huggingface_hub import hf_hub_download

        cache_dir = Path(os.getenv("MODEL_CACHE_DIR", "/app/data/models"))
        target_dir = cache_dir / "doclayout_yolo"
        target_dir.mkdir(parents=True, exist_ok=True)

        logger.info("Starting DocLayout-YOLO download")
        hf_hub_download(
            repo_id="juliozhao/DocLayout-YOLO-DocStructBench",
            filename="docstructbench_imgsz1024.onnx",
            local_dir=str(target_dir),
        )
        logger.info("DocLayout-YOLO download complete")
        return True
    except Exception as e:
        logger.exception("DocLayout-YOLO download failed: %s", e)
        raise RuntimeError(f"DocLayout-YOLO download failed: {e}") from e


def normalize_layout_model_id(raw: str | None) -> str:
    """Normalize a layout model ID to a canonical form.

    Handles common aliases and falls back to the default.
    """
    normalized = (_clean_str(raw) or DEFAULT_LAYOUT_MODEL_ID).lower()

    # Aliases for backward compatibility
    aliases: dict[str, str] = {
        "pp-doclayoutv3": "pp_doclayout_v3",
        "pp_doclayoutv3": "pp_doclayout_v3",
        "pp_doclayout": "pp_doclayout_v3",
        "pp-doclayout-v3": "pp_doclayout_v3",
        "pp-doclayout-s": "pp_doclayout_s",
        "pp_doclayouts": "pp_doclayout_s",
        "pp-doclayout-m": "pp_doclayout_m",
        "pp_doclayoutm": "pp_doclayout_m",
        "pp-doclayout-l": "pp_doclayout_l",
        "pp_doclayoutl": "pp_doclayout_l",
        "doclayout-yolo": "doclayout_yolo",
        "doclayoutyolo": "doclayout_yolo",
    }

    if normalized in aliases:
        return aliases[normalized]
    if normalized in LAYOUT_MODELS:
        return normalized
    return DEFAULT_LAYOUT_MODEL_ID
