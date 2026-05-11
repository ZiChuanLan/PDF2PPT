"""Baidu OCR client provider."""

import logging
import os
from typing import Any, Dict, List

from PIL import Image

from .base import OcrProvider

# ---------------------------------------------------------------------------
# Constants: Baidu OCR thresholds
# ---------------------------------------------------------------------------
_BAIDU_AREA_RATIO_PRUNE_THRESHOLD = 0.16
"""Area ratio above which a Baidu OCR box is considered a coarse paragraph."""

_BAIDU_WIDTH_RATIO_PRUNE_THRESHOLD = 0.85
"""Width ratio threshold for wide+short paragraph detection."""

_BAIDU_HEIGHT_RATIO_PRUNE_THRESHOLD = 0.08
"""Height ratio threshold for wide+short paragraph detection."""

_BAIDU_COMPACT_TEXT_LENGTH_LIMIT = 24
"""Max compact text length for wide+short paragraph pruning."""

_BAIDU_AREA_RATIO_THRESHOLD_ALT = 0.06
"""Alternative area ratio threshold for short-text pruning."""

_BAIDU_COMPACT_TEXT_LENGTH_LIMIT_ALT = 6
"""Alternative compact text length limit for short-text pruning."""

_BAIDU_HEIGHT_RATIO_THRESHOLD_ALT = 0.06
"""Alternative height ratio threshold for short-text pruning."""

_BAIDU_DEFAULT_CONFIDENCE = 0.95
"""Default confidence for Baidu OCR results (Baidu doesn't reliably return confidences)."""


logger = logging.getLogger(__name__)

class BaiduOcrClient(OcrProvider):
    """Baidu OCR client implementation."""

    def __init__(
        self,
        app_id: str | None = None,
        api_key: str | None = None,
        secret_key: str | None = None,
    ):
        """Initialize Baidu OCR client with credentials from parameters or env."""
        self.app_id = (app_id or os.getenv("BAIDU_OCR_APP_ID") or "").strip()
        self.api_key = (api_key or os.getenv("BAIDU_OCR_API_KEY") or "").strip()
        self.secret_key = (
            secret_key or os.getenv("BAIDU_OCR_SECRET_KEY") or ""
        ).strip()

        if not all([self.api_key, self.secret_key]):
            raise ValueError(
                "Baidu OCR credentials not found. "
                "Set BAIDU_OCR_API_KEY and BAIDU_OCR_SECRET_KEY"
            )

        try:
            from aip import AipOcr

            # The legacy `baidu-aip` SDK constructor still accepts appId, but its
            # token flow authenticates with apiKey/secretKey only. Keep App ID as
            # an optional compatibility field instead of a hard requirement.
            self.client = AipOcr(self.app_id, self.api_key, self.secret_key)
            logger.info("Baidu OCR client initialized successfully")
        except ImportError:
            raise ImportError(
                "baidu-aip package not installed. Install with: pip install baidu-aip"
            )

    def ocr_image(self, image_path: str) -> List[Dict]:
        """
        Perform OCR using Baidu API.

        Args:
            image_path: Path to the image file

        Returns:
            List of text elements with bbox and confidence
        """
        try:
            # Read image as binary
            with open(image_path, "rb") as f:
                image_data = f.read()

            # Request direction + probability when supported. These options
            # improve robustness on scan-heavy slide decks and keep the output
            # stable across Baidu OCR endpoints/SDK versions.
            options = {
                "detect_direction": "true",
                "probability": "true",
                # Prefer bilingual recognition for typical CN/EN decks.
                "language_type": "CHN_ENG",
            }

            # Prefer high-accuracy endpoint *with location* so we can place
            # editable text boxes precisely. SDK method names vary slightly
            # across versions, so we probe a few.
            call_candidates: list[tuple[str, Any]] = []
            if hasattr(self.client, "accurate"):
                call_candidates.append(("accurate", getattr(self.client, "accurate")))
            if hasattr(self.client, "general"):
                call_candidates.append(("general", getattr(self.client, "general")))
            if hasattr(self.client, "basicAccurate"):
                # Some SDKs expose this name; it typically maps to accurate_basic.
                call_candidates.append(
                    ("basicAccurate", getattr(self.client, "basicAccurate"))
                )
            if hasattr(self.client, "basicGeneral"):
                call_candidates.append(
                    ("basicGeneral", getattr(self.client, "basicGeneral"))
                )

            if not call_candidates:
                raise RuntimeError("Baidu OCR SDK has no callable OCR methods")

            last_error: Exception | None = None
            result: dict | None = None
            used_method = None
            for name, fn in call_candidates:
                try:
                    used_method = name
                    # Keep options minimal; callers may still get direction info
                    # by enabling detect_direction via Baidu console if needed.
                    try:
                        result = fn(image_data, options)
                    except TypeError:
                        # Some SDK versions/endpoints may not accept an options
                        # arg (or may have a different signature).
                        result = fn(image_data)
                    if isinstance(result, dict) and "error_code" not in result:
                        break
                except Exception as e:
                    last_error = e
                    result = None
                    continue

            if not isinstance(result, dict):
                raise RuntimeError("Baidu OCR returned no result") from last_error

            # Check for errors
            if "error_code" in result:
                error_msg = result.get("error_msg", "Unknown error")
                logger.error("Baidu OCR API error (%s): %s", used_method, error_msg)
                raise RuntimeError(f"Baidu OCR failed: {error_msg}")

            # Parse results
            img_w = 0.0
            img_h = 0.0
            try:
                with Image.open(image_path) as _im:
                    img_w = float(_im.width)
                    img_h = float(_im.height)
            except Exception:
                img_w = 0.0
                img_h = 0.0

            elements: list[dict] = []
            words_result = result.get("words_result", [])
            if not isinstance(words_result, list):
                words_result = []

            for item in words_result:
                if not isinstance(item, dict):
                    continue
                text = str(item.get("words") or "").strip()
                location = item.get("location") or {}
                if not text or not isinstance(location, dict):
                    continue

                # Baidu returns: {left, top, width, height} in pixels
                try:
                    x0 = float(location.get("left", 0) or 0)
                    y0 = float(location.get("top", 0) or 0)
                    w = float(location.get("width", 0) or 0)
                    h = float(location.get("height", 0) or 0)
                except Exception:
                    continue
                if w <= 0 or h <= 0:
                    continue

                # Defensive pruning for occasional coarse/paragraph-level boxes.
                # Such boxes are harmful in slide conversion because they can wipe
                # image regions and create duplicate/stacked text overlays.
                compact = "".join(ch for ch in text if not ch.isspace())
                if img_w > 0 and img_h > 0:
                    area_ratio = float(w * h) / float(max(1.0, img_w * img_h))
                    width_ratio = float(w) / float(max(1.0, img_w))
                    height_ratio = float(h) / float(max(1.0, img_h))
                    if area_ratio >= _BAIDU_AREA_RATIO_PRUNE_THRESHOLD:
                        continue
                    if (
                        width_ratio >= _BAIDU_WIDTH_RATIO_PRUNE_THRESHOLD
                        and height_ratio >= _BAIDU_HEIGHT_RATIO_PRUNE_THRESHOLD
                        and len(compact) <= _BAIDU_COMPACT_TEXT_LENGTH_LIMIT
                    ):
                        continue
                    if (
                        area_ratio >= _BAIDU_AREA_RATIO_THRESHOLD_ALT
                        and len(compact) <= _BAIDU_COMPACT_TEXT_LENGTH_LIMIT_ALT
                        and height_ratio >= _BAIDU_HEIGHT_RATIO_THRESHOLD_ALT
                    ):
                        continue

                elements.append(
                    {
                        "text": text,
                        "bbox": [x0, y0, x0 + w, y0 + h],
                        # Baidu does not reliably return confidences across
                        # endpoints; keep a high default so downstream can treat
                        # it as a strong signal.
                        "confidence": _BAIDU_DEFAULT_CONFIDENCE,
                    }
                )

            logger.info(
                "Baidu OCR extracted %s text elements from %s (method=%s)",
                len(elements),
                image_path,
                used_method,
            )
            return elements

        except Exception as e:
            logger.error("Baidu OCR failed on %s: %s", image_path, e)
            raise


