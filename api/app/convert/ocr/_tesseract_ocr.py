"""Tesseract OCR client provider."""

import logging
from typing import Any, Dict, List

from PIL import Image

from .base import _normalize_tesseract_language, _split_tesseract_languages, OcrProvider
from .runtime_probe import probe_local_tesseract, probe_local_tesseract_models

# ---------------------------------------------------------------------------
# Constants: Tesseract OCR thresholds
# ---------------------------------------------------------------------------
# Constants: Tesseract OCR thresholds
# ---------------------------------------------------------------------------
_TESSERACT_DEFAULT_MIN_CONFIDENCE = 50.0
"""Default minimum confidence threshold for Tesseract OCR (0-100 scale)."""

_TESSERACT_PSM_SPARSE_TEXT = 11
"""Tesseract PSM mode for sparse text (best for slides/scanned pages)."""

_TESSERACT_LOW_RECALL_LINE_THRESHOLD = 12
"""Line count below which we consider the result low recall."""

_TESSERACT_LOW_RECALL_WORD_THRESHOLD = 80
"""Word count below which we consider the result low recall."""

_TESSERACT_LOW_CONFIDENCE_RETRY_THRESHOLD = 25.0
"""Confidence threshold below which we retry with lower confidence."""

_TESSERACT_LOOKS_EMPTY_LINE_THRESHOLD = 8
"""Line count below which the result looks empty."""

_TESSERACT_LOOKS_EMPTY_WORD_THRESHOLD = 40
"""Word count below which the result looks empty."""


logger = logging.getLogger(__name__)

class TesseractOcrClient(OcrProvider):
    """Tesseract OCR client implementation."""

    def __init__(self, min_confidence: float = _TESSERACT_DEFAULT_MIN_CONFIDENCE, language: str = "chi_sim+eng"):
        """
        Initialize Tesseract OCR client.

        Args:
            min_confidence: Minimum confidence threshold (0-100)
        """
        self.min_confidence = min_confidence
        # Prefer a bilingual default for typical scanned PDFs. This project is
        # mostly used on Chinese+English slide decks.
        self.language = _normalize_tesseract_language(language)

        try:
            import pytesseract
            from pytesseract import Output

            self.pytesseract = pytesseract
            self.Output = Output
            probe = probe_local_tesseract(language=self.language)
            if not bool(probe.get("binary_available")):
                raise RuntimeError(
                    "Tesseract executable is not available. "
                    "Install system package: tesseract-ocr"
                )

            missing_languages = [
                str(item).strip()
                for item in (probe.get("missing_languages") or [])
                if str(item).strip()
            ]
            if missing_languages:
                requested_languages = _split_tesseract_languages(self.language)
                available_languages = [
                    str(item).strip()
                    for item in (probe.get("available_languages") or [])
                    if str(item).strip()
                ]
                available_set = {lang.lower() for lang in available_languages}
                fallback_languages = [
                    lang
                    for lang in requested_languages
                    if lang.lower() in available_set
                ]

                if fallback_languages:
                    fallback = "+".join(fallback_languages)
                    logger.warning(
                        "Tesseract requested lang '%s' is partially missing. "
                        "Fallback to '%s'. Missing=%s",
                        self.language,
                        fallback,
                        ",".join(missing_languages),
                    )
                    self.language = fallback
                else:
                    raise RuntimeError(
                        "Tesseract language pack(s) not available: "
                        f"{', '.join(missing_languages)}"
                    )

            logger.info(
                "Tesseract OCR client initialized successfully (lang=%s, version=%s)",
                self.language,
                str(probe.get("version") or "unknown"),
            )
        except ImportError:
            raise ImportError(
                "pytesseract package not installed. "
                "Install with: pip install pytesseract"
            )

    def _extract_elements_from_data(
        self, data: dict, *, min_conf: float
    ) -> tuple[list[dict], dict]:
        elements: list[dict] = []
        n_boxes = len(data.get("text") or [])
        line_keys: set[tuple[int, int, int]] = set()
        conf_sum = 0.0
        conf_n = 0

        for i in range(n_boxes):
            # Tesseract returns conf as string numbers; it can also be "-1".
            try:
                conf = float((data.get("conf") or ["-1"] * n_boxes)[i])
            except Exception:
                conf = -1.0
            text = str((data.get("text") or [""] * n_boxes)[i] or "").strip()

            if conf < float(min_conf) or not text:
                continue

            try:
                x = int((data.get("left") or [0] * n_boxes)[i])
                y = int((data.get("top") or [0] * n_boxes)[i])
                w = int((data.get("width") or [0] * n_boxes)[i])
                h = int((data.get("height") or [0] * n_boxes)[i])
            except Exception:
                continue

            block_num = (data.get("block_num") or [None] * n_boxes)[i]
            par_num = (data.get("par_num") or [None] * n_boxes)[i]
            line_num = (data.get("line_num") or [None] * n_boxes)[i]
            word_num = (data.get("word_num") or [None] * n_boxes)[i]

            try:
                lk = (int(block_num or 0), int(par_num or 0), int(line_num or 0))
                line_keys.add(lk)
            except Exception:
                pass

            elements.append(
                {
                    "text": text,
                    "bbox": [x, y, x + w, y + h],
                    "confidence": conf / 100.0,  # Normalize to 0-1
                    # Preserve Tesseract's structural hints so we can merge
                    # words into line-level boxes more accurately.
                    "block_num": block_num,
                    "par_num": par_num,
                    "line_num": line_num,
                    "word_num": word_num,
                }
            )
            conf_sum += conf
            conf_n += 1

        avg_conf = (conf_sum / conf_n) if conf_n else 0.0
        stats = {
            "words": len(elements),
            "lines": len(line_keys),
            "avg_conf": avg_conf,
        }
        return elements, stats

    def ocr_image(self, image_path: str) -> List[Dict]:
        """
        Perform OCR using Tesseract.

        Args:
            image_path: Path to the image file

        Returns:
            List of text elements with bbox and confidence
        """
        try:
            # Open image
            image = Image.open(image_path).convert("RGB")

            # Slides / scanned pages often have multiple isolated text boxes.
            # Sparse-text mode (PSM 11) typically yields higher recall, but some
            # documents behave better with other modes. We start with PSM 11 and
            # only try extra modes when the first pass looks suspiciously low.
            psm_candidates: list[int] = [_TESSERACT_PSM_SPARSE_TEXT]

            # Try the configured language first, but in real-world usage users
            # sometimes set lang=eng while the PDF contains Chinese. In that case
            # we automatically try a bilingual fallback and pick the better run.
            lang_candidates: list[str] = []
            primary_lang = (self.language or "").strip()
            if primary_lang:
                lang_candidates.append(primary_lang)
            fallback_lang = "chi_sim+eng"
            if fallback_lang not in lang_candidates:
                lang_candidates.append(fallback_lang)

            best_elements: list[dict] = []
            best_stats: dict = {"words": 0, "lines": 0, "avg_conf": 0.0}
            best_lang: str | None = None
            best_psm: int | None = None
            last_error: Exception | None = None

            def _score(stats: dict) -> int:
                return (int(stats.get("lines") or 0) * 10) + int(
                    stats.get("words") or 0
                )

            def _run(
                lang: str, psm: int, *, min_conf: float
            ) -> tuple[list[dict] | None, dict | None]:
                nonlocal last_error
                try:
                    data = self.pytesseract.image_to_data(
                        image,
                        output_type=self.Output.DICT,
                        lang=lang,
                        config=f"--psm {int(psm)}",
                    )
                except Exception as e:
                    last_error = e
                    logger.warning(
                        "Tesseract OCR run failed (lang=%s, psm=%s): %s", lang, psm, e
                    )
                    return (None, None)

                elems, stats = self._extract_elements_from_data(
                    data, min_conf=float(min_conf)
                )
                return (elems, stats)

            min_conf_primary = float(self.min_confidence)
            used_min_conf = float(min_conf_primary)

            # First pass: PSM 11.
            for lang in lang_candidates:
                elems, stats = _run(lang, _TESSERACT_PSM_SPARSE_TEXT, min_conf=min_conf_primary)
                if elems is None or stats is None:
                    continue
                if best_lang is None or _score(stats) > _score(best_stats):
                    best_elements = elems
                    best_stats = stats
                    best_lang = lang
                    best_psm = _TESSERACT_PSM_SPARSE_TEXT

            # If the first pass looks low recall, try a couple more modes.
            if best_lang is not None:
                if (
                    int(best_stats.get("lines") or 0) < _TESSERACT_LOW_RECALL_LINE_THRESHOLD
                    and int(best_stats.get("words") or 0) < _TESSERACT_LOW_RECALL_WORD_THRESHOLD
                ):
                    psm_candidates = [_TESSERACT_PSM_SPARSE_TEXT, 6, 3]

            for psm in psm_candidates:
                if psm == _TESSERACT_PSM_SPARSE_TEXT:
                    continue
                for lang in lang_candidates:
                    elems, stats = _run(lang, psm, min_conf=min_conf_primary)
                    if elems is None or stats is None:
                        continue
                    if best_lang is None or _score(stats) > _score(best_stats):
                        best_elements = elems
                        best_stats = stats
                        best_lang = lang
                        best_psm = int(psm)

            if best_lang is None:
                # All tesseract runs failed (e.g. binary not installed).
                raise RuntimeError(
                    "Tesseract OCR failed for all languages"
                ) from last_error

            # If the configured min_conf is too strict, Tesseract can return an
            # empty/near-empty result on scan-heavy slides. In that case we
            # retry with a lower confidence threshold so we at least get line
            # geometry; downstream can filter obvious noise and (optionally)
            # refine text with an AI vision model.
            if min_conf_primary > _TESSERACT_LOW_CONFIDENCE_RETRY_THRESHOLD:
                lines_n = int(best_stats.get("lines") or 0)
                words_n = int(best_stats.get("words") or 0)
                looks_empty = (not best_elements) or (lines_n < _TESSERACT_LOOKS_EMPTY_LINE_THRESHOLD and words_n < _TESSERACT_LOOKS_EMPTY_WORD_THRESHOLD)
                if looks_empty:
                    low_min_conf = _TESSERACT_LOW_CONFIDENCE_RETRY_THRESHOLD
                    low_best_elems: list[dict] = []
                    low_best_stats: dict = {"words": 0, "lines": 0, "avg_conf": 0.0}
                    low_best_lang: str | None = None
                    low_best_psm: int | None = None

                    # Start from the best (lang, psm) choice, but also probe a
                    # couple other modes to avoid pathological edge cases.
                    psm_probe: list[int] = []
                    if best_psm is not None:
                        psm_probe.append(int(best_psm))
                    for p in (_TESSERACT_PSM_SPARSE_TEXT, 6, 3):
                        if p not in psm_probe:
                            psm_probe.append(p)

                    for psm in psm_probe:
                        for lang in lang_candidates:
                            elems, stats = _run(lang, int(psm), min_conf=low_min_conf)
                            if elems is None or stats is None:
                                continue
                            if low_best_lang is None or _score(stats) > _score(
                                low_best_stats
                            ):
                                low_best_elems = elems
                                low_best_stats = stats
                                low_best_lang = lang
                                low_best_psm = int(psm)

                    if (
                        low_best_lang is not None
                        and low_best_elems
                        and _score(low_best_stats) > _score(best_stats)
                    ):
                        logger.info(
                            "Tesseract OCR lowered min_conf from %s to %s (lines=%s words=%s).",
                            min_conf_primary,
                            low_min_conf,
                            low_best_stats.get("lines"),
                            low_best_stats.get("words"),
                        )
                        best_elements = low_best_elems
                        best_stats = low_best_stats
                        best_lang = low_best_lang
                        best_psm = (
                            low_best_psm if low_best_psm is not None else best_psm
                        )
                        used_min_conf = float(low_min_conf)

            if best_lang and best_lang != primary_lang:
                logger.info(
                    "Tesseract OCR auto-switched lang from %s to %s (lines=%s words=%s).",
                    primary_lang or "<empty>",
                    best_lang,
                    best_stats.get("lines"),
                    best_stats.get("words"),
                )

            logger.info(
                "Tesseract OCR extracted %s text elements from %s (lang=%s, psm=%s, min_conf=%s)",
                len(best_elements),
                image_path,
                best_lang or primary_lang or "<unknown>",
                best_psm if best_psm is not None else _TESSERACT_PSM_SPARSE_TEXT,
                used_min_conf,
            )
            return best_elements

        except Exception as e:
            logger.error(f"Tesseract OCR failed on {image_path}: {str(e)}")
            raise


