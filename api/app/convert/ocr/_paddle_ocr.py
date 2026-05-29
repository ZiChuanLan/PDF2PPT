"""Local PaddleOCR client providers."""

import logging
from typing import Any, Dict, List

import numpy as np
from PIL import Image

from app.config import get_settings

from .base import _normalize_paddle_language, OcrProvider
from .result_parsing import _is_image_like_layout_label, _normalize_layout_label
from .utils import _coerce_bbox_xyxy

# ---------------------------------------------------------------------------
# Constants: PaddleOCR thresholds
# ---------------------------------------------------------------------------
# Constants: PaddleOCR thresholds
# ---------------------------------------------------------------------------
_PADDLE_OCR_DEFAULT_CONFIDENCE = 0.85
"""Default confidence for PaddleOCR results when not provided."""

_PADDLE_OCR_MAX_NODES_FOR_TRAVERSAL = 20000
"""Maximum nodes to visit when traversing PaddleOCR result tree."""


logger = logging.getLogger(__name__)

class PaddleOcrClient(OcrProvider):
    """PaddleOCR local client implementation."""

    def __init__(self, language: str = "ch"):
        self.language = _normalize_paddle_language(language)
        self._engine: Any | None = None
        # PaddleOCR 3.x (PaddleX pipeline) can be memory-hungry on large page
        # renders. Downscale long-edge to keep CPU inference stable.
        self._max_side_px: int = int(get_settings().ocr_paddle_vl_docparser_max_side_px)
        # Layout detection state (populated after ocr_image())
        self.last_image_regions_px: list[Any] = []
        self.last_layout_blocks: list[dict[str, Any]] = []

        try:
            from paddleocr import PaddleOCR
        except ImportError:
            raise ImportError(
                "paddleocr package not installed. Install with: pip install paddleocr"
            )

        self._PaddleOCR = PaddleOCR
        logger.info("PaddleOCR client initialized (lang=%s)", self.language)

    def _ensure_engine(self) -> Any:
        if self._engine is not None:
            return self._engine

        last_error: Exception | None = None
        constructors: list[dict[str, Any]] = [
            # PaddleOCR 3.x uses a PaddleX pipeline wrapper internally. On some
            # CPU builds, enabling MKL-DNN / oneDNN can trigger runtime errors in
            # the new executor. Keep it off by default for stability.
            {
                "lang": self.language,
                "use_textline_orientation": True,
                "use_doc_orientation_classify": False,
                "use_doc_unwarping": False,
                "enable_mkldnn": False,
                "enable_cinn": False,
                "device": "cpu",
            },
            {
                "lang": self.language,
                "use_doc_orientation_classify": False,
                "use_doc_unwarping": False,
                "enable_mkldnn": False,
                "enable_cinn": False,
                "device": "cpu",
            },
        ]

        for kwargs in constructors:
            try:
                self._engine = self._PaddleOCR(**kwargs)
                return self._engine
            except Exception as e:
                last_error = e
                continue

        raise RuntimeError("Failed to initialize PaddleOCR runtime") from last_error

    def _run_layout_detection(
        self, image_path: str
    ) -> tuple[list[dict[str, Any]], list[Any]]:
        """Run PP-DocLayoutV3 layout detection and return (layout_blocks, image_regions).

        Layout blocks: list of {label, score, bbox, order, polygon_points}
        Image regions: list of image region payloads for non-text blocks
        """
        from .layout_models import get_layout_model, DEFAULT_LAYOUT_MODEL_ID

        try:
            layout_model = get_layout_model(DEFAULT_LAYOUT_MODEL_ID)
            raw_blocks = layout_model.predict(image_path)
        except Exception as e:
            logger.warning("Layout detection failed, skipping: %s", e)
            return [], []

        layout_blocks: list[dict[str, Any]] = []
        image_regions: list[Any] = []

        for block in raw_blocks:
            label = _normalize_layout_label(block.get("label", ""))
            score = float(block.get("score", 0.0))
            bbox = block.get("bbox", [0, 0, 0, 0])
            order = block.get("order")

            if not label or len(bbox) < 4:
                continue

            bbox_xyxy = [float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])]
            layout_block: dict[str, Any] = {
                "label": label,
                "score": score,
                "bbox": bbox_xyxy,
                "order": order,
            }

            # Preserve polygon_points from layout model
            poly_pts = block.get("polygon_points")
            if isinstance(poly_pts, list) and len(poly_pts) >= 3:
                layout_block["polygon_points"] = poly_pts

            layout_blocks.append(layout_block)

            if _is_image_like_layout_label(label):
                image_regions.append(list(bbox_xyxy))

        logger.info(
            "Layout detection found %d blocks (%d image regions) from %s",
            len(layout_blocks),
            len(image_regions),
            image_path,
        )
        return layout_blocks, image_regions

    def ocr_image(self, image_path: str) -> List[Dict]:
        # Run layout detection first to identify text vs image regions
        self.last_layout_blocks = []
        self.last_image_regions_px = []
        try:
            layout_blocks, image_regions = self._run_layout_detection(image_path)
            self.last_layout_blocks = layout_blocks
            self.last_image_regions_px = image_regions
        except Exception as e:
            logger.debug("Layout detection skipped: %s", e)

        engine = self._ensure_engine()

        # PaddleOCR can run on file paths or numpy arrays. We downscale huge
        # images before inference and scale bboxes back to the original size.
        image_for_ocr: Any = image_path
        scale_x = 1.0
        scale_y = 1.0
        try:
            image = Image.open(image_path).convert("RGB")
            w, h = image.size
            largest = max(w, h)
            if largest > int(self._max_side_px):
                ratio = float(self._max_side_px) / float(largest)
                new_w = max(32, int(round(float(w) * ratio)))
                new_h = max(32, int(round(float(h) * ratio)))
                image_small = image.resize((new_w, new_h), Image.Resampling.LANCZOS)
                try:

                    image_for_ocr = np.array(image_small)
                    scale_x = float(w) / float(new_w)
                    scale_y = float(h) / float(new_h)
                except Exception:
                    image_for_ocr = image_path
        except Exception:
            pass

        raw_result: Any = None
        last_error: Exception | None = None

        ocr_calls = [
            # PaddleOCR 3.x deprecates `.ocr()` in favor of `.predict()` and no
            # longer accepts the legacy `cls=` kwarg.
            lambda: engine.predict(image_for_ocr),
            lambda: engine.predict(input=image_for_ocr),
            lambda: engine.ocr(image_for_ocr),
        ]
        for fn in ocr_calls:
            try:
                raw_result = fn()
                last_error = None
                break
            except Exception as e:
                last_error = e
                continue

        if raw_result is None and hasattr(engine, "predict"):
            predict_calls = [
                lambda: engine.predict(input=image_for_ocr),
                lambda: engine.predict(image_for_ocr),
            ]
            for fn in predict_calls:
                try:
                    raw_result = fn()
                    last_error = None
                    break
                except Exception as e:
                    last_error = e
                    continue

        if raw_result is None:
            if last_error is not None:
                logger.warning("PaddleOCR failed to produce output: %s", last_error)
            raise RuntimeError("PaddleOCR failed to produce output") from last_error

        elements: list[dict] = []

        def _append_from_paddlex_ocr_payload(payload: dict[str, Any]) -> bool:
            """Parse PaddleOCR 3.x / PaddleX pipeline output dict."""

            texts = payload.get("rec_texts")
            polys = payload.get("rec_polys")
            scores = payload.get("rec_scores")
            if texts is None or polys is None:
                # Some variants expose detection polys; use them only if they line
                # up with recognized texts.
                texts = payload.get("texts") or payload.get("text") or texts
                polys = payload.get("polys") or payload.get("dt_polys") or polys
                scores = payload.get("scores") or payload.get("rec_scores") or scores

            if texts is not None and hasattr(texts, "tolist"):
                try:
                    texts = texts.tolist()
                except Exception:
                    pass
            if polys is not None and hasattr(polys, "tolist"):
                try:
                    polys = polys.tolist()
                except Exception:
                    pass
            if scores is not None and hasattr(scores, "tolist"):
                try:
                    scores = scores.tolist()
                except Exception:
                    pass

            if not isinstance(texts, list) or not isinstance(polys, list) or not texts:
                return False
            if len(polys) != len(texts):
                return False

            used = False
            for i, (text_raw, poly) in enumerate(zip(texts, polys)):
                text = str(text_raw or "").strip()
                bbox = _coerce_bbox_xyxy(poly)
                if not text or not bbox:
                    continue

                # Preserve polygon points from rec_polys (4-point quadrilateral)
                geometry_points: list[list[float]] | None = None
                if isinstance(poly, (list, tuple)) and len(poly) >= 3:
                    pts: list[list[float]] = []
                    for pt in poly:
                        if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                            pts.append([float(pt[0]), float(pt[1])])
                    if len(pts) >= 3:
                        geometry_points = pts

                confidence_raw: Any = None
                if isinstance(scores, list) and i < len(scores):
                    confidence_raw = scores[i]
                try:
                    confidence = (
                        float(confidence_raw) if confidence_raw is not None else _PADDLE_OCR_DEFAULT_CONFIDENCE
                    )
                except Exception:
                    confidence = _PADDLE_OCR_DEFAULT_CONFIDENCE
                if confidence > 1.0:
                    confidence = confidence / 100.0 if confidence <= 100.0 else 1.0
                confidence = max(0.0, min(confidence, 1.0))

                element: dict[str, Any] = {
                    "text": text,
                    "bbox": [
                        float(bbox[0]),
                        float(bbox[1]),
                        float(bbox[2]),
                        float(bbox[3]),
                    ],
                    "confidence": confidence,
                }
                if geometry_points is not None:
                    element["ocr_layout_geometry_kind"] = "polygon"
                    element["ocr_layout_geometry_points"] = geometry_points

                elements.append(element)
                used = True

            return used

        def _append_from_dict(candidate: dict[str, Any]) -> bool:
            text = str(
                candidate.get("text")
                or candidate.get("transcription")
                or candidate.get("content")
                or candidate.get("label")
                or ""
            ).strip()
            bbox = _coerce_bbox_xyxy(
                candidate.get("bbox")
                or candidate.get("box")
                or candidate.get("points")
                or candidate.get("polygon")
                or candidate.get("position")
                or candidate.get("coordinates")
                or candidate.get("block_bbox")
            )
            if not text or not bbox:
                return False

            confidence_raw = (
                candidate.get("confidence")
                or candidate.get("score")
                or candidate.get("prob")
            )
            try:
                confidence = (
                    float(confidence_raw) if confidence_raw is not None else _PADDLE_OCR_DEFAULT_CONFIDENCE
                )
            except Exception:
                confidence = _PADDLE_OCR_DEFAULT_CONFIDENCE
            if confidence > 1.0:
                confidence = confidence / 100.0 if confidence <= 100.0 else 1.0
            confidence = max(0.0, min(confidence, 1.0))

            elements.append(
                {
                    "text": text,
                    "bbox": [
                        float(bbox[0]),
                        float(bbox[1]),
                        float(bbox[2]),
                        float(bbox[3]),
                    ],
                    "confidence": confidence,
                }
            )
            return True

        # Fast-path: PaddleOCR 3.x (PaddleX pipeline) returns a list of dicts
        # containing rec_texts/rec_polys arrays instead of the legacy
        # `[[quad], (text, score)]` layout.
        if (
            isinstance(raw_result, list)
            and raw_result
            and all(isinstance(v, dict) for v in raw_result)
        ):
            used_any = False
            for payload in raw_result:
                used_any = _append_from_paddlex_ocr_payload(payload) or used_any
            if used_any:
                if scale_x != 1.0 or scale_y != 1.0:
                    for el in elements:
                        bbox = el.get("bbox")
                        if not isinstance(bbox, list) or len(bbox) != 4:
                            continue
                        x0, y0, x1, y1 = [float(v) for v in bbox]
                        el["bbox"] = [
                            x0 * scale_x,
                            y0 * scale_y,
                            x1 * scale_x,
                            y1 * scale_y,
                        ]
                        # Scale polygon points too
                        pts = el.get("ocr_layout_geometry_points")
                        if isinstance(pts, list):
                            el["ocr_layout_geometry_points"] = [
                                [float(p[0]) * scale_x, float(p[1]) * scale_y]
                                for p in pts
                                if isinstance(p, (list, tuple)) and len(p) >= 2
                            ]
                logger.info(
                    "PaddleOCR extracted %s text elements from %s (paddlex pipeline)",
                    len(elements),
                    image_path,
                )
                return elements

        stack: list[Any] = [raw_result]
        max_nodes = _PADDLE_OCR_MAX_NODES_FOR_TRAVERSAL
        visited = 0

        while stack and visited < max_nodes:
            visited += 1
            node = stack.pop()

            if isinstance(node, dict):
                used = _append_from_dict(node)
                if not used:
                    for value in node.values():
                        stack.append(value)
                continue

            if isinstance(node, (list, tuple)):
                if len(node) >= 2:
                    bbox = _coerce_bbox_xyxy(node[0])
                    text = ""
                    confidence_raw: Any = None

                    second = node[1]
                    if isinstance(second, (list, tuple)):
                        if second:
                            text = str(second[0] or "").strip()
                        if len(second) > 1:
                            confidence_raw = second[1]
                    elif isinstance(second, str):
                        text = second.strip()
                        if len(node) > 2:
                            confidence_raw = node[2]

                    if text and bbox:
                        try:
                            confidence = (
                                float(confidence_raw)
                                if confidence_raw is not None
                                else _PADDLE_OCR_DEFAULT_CONFIDENCE
                            )
                        except Exception:
                            confidence = _PADDLE_OCR_DEFAULT_CONFIDENCE
                        if confidence > 1.0:
                            confidence = (
                                confidence / 100.0 if confidence <= 100.0 else 1.0
                            )
                        confidence = max(0.0, min(confidence, 1.0))

                        elements.append(
                            {
                                "text": text,
                                "bbox": [
                                    float(bbox[0]),
                                    float(bbox[1]),
                                    float(bbox[2]),
                                    float(bbox[3]),
                                ],
                                "confidence": confidence,
                            }
                        )
                        continue

                for item in node:
                    stack.append(item)

        if not elements:
            raise RuntimeError("PaddleOCR returned no valid text elements")

        if scale_x != 1.0 or scale_y != 1.0:
            for el in elements:
                bbox = el.get("bbox")
                if not isinstance(bbox, list) or len(bbox) != 4:
                    continue
                x0, y0, x1, y1 = [float(v) for v in bbox]
                el["bbox"] = [x0 * scale_x, y0 * scale_y, x1 * scale_x, y1 * scale_y]
                pts = el.get("ocr_layout_geometry_points")
                if isinstance(pts, list):
                    el["ocr_layout_geometry_points"] = [
                        [float(p[0]) * scale_x, float(p[1]) * scale_y]
                        for p in pts
                        if isinstance(p, (list, tuple)) and len(p) >= 2
                    ]

        logger.info(
            "PaddleOCR extracted %s text elements from %s", len(elements), image_path
        )
        return elements


class LazyPaddleOcrClient(OcrProvider):
    """Lazy wrapper for local PaddleOCR fallback.

    Loading PaddleOCR can be expensive; explicit cloud OCR providers should not
    pay that startup cost unless fallback is actually needed.
    """

    def __init__(self, *, language: str = "ch"):
        self.language = _normalize_paddle_language(language)
        self._provider: PaddleOcrClient | None = None

    def _ensure_provider(self) -> PaddleOcrClient:
        if self._provider is None:
            self._provider = PaddleOcrClient(language=self.language)
        return self._provider

    def ocr_image(self, image_path: str) -> List[Dict]:
        return self._ensure_provider().ocr_image(image_path)


