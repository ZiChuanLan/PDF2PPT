"""OCR Manager: orchestrates multiple OCR providers with fallback logic."""

import logging
from typing import Any, Dict, List, Optional

from .ai_client import AiOcrClient, AiOcrTextRefiner, _clone_image_region_payload, _is_multiline_candidate_for_linebreak_assist
from .base import _ACRONYM_ALLOWLIST, _DEFAULT_PADDLE_OCR_VL_MODEL, _clean_str, _normalize_paddle_language, _normalize_tesseract_language, _split_tesseract_languages, OcrProvider
from .deepseek_parser import _looks_like_ocr_prompt_echo_text
from .routing import ROUTE_KIND_HYBRID_AUTO, ROUTE_KIND_LOCAL_LAYOUT_BLOCK_OCR, ROUTE_KIND_REMOTE_DOC_PARSER, ROUTE_KIND_REMOTE_PROMPT_OCR, normalize_ocr_route_kind
from .runtime_probe import probe_local_paddle_models, probe_local_paddleocr, probe_local_tesseract, probe_local_tesseract_models
from .utils import _coerce_bbox_xyxy, _is_paddleocr_vl_model
from .vendors import _normalize_ai_ocr_provider

from ._ocr_remote import (
    RemoteOcrClientSpec,
    _build_remote_ocr_client_from_spec,
    create_remote_ocr_client,
    resolve_remote_ocr_client_spec,
)
from ._baidu_ocr import BaiduOcrClient
from ._tesseract_ocr import TesseractOcrClient, _TESSERACT_DEFAULT_MIN_CONFIDENCE
from ._paddle_ocr import LazyPaddleOcrClient, PaddleOcrClient
from ._ocr_constants import (
    _BAND_CLOSE_Y_THRESHOLD_MULTIPLIER,
    _BAND_OVERLAP_THRESHOLD_MULTIPLIER,
    _BAND_X_GAP_THRESHOLD_HEIGHT_MULTIPLIER,
    _BAND_X_GAP_THRESHOLD_RATIO,
    _MERGE_GAP_THRESHOLD_MULTIPLIER,
    _MERGE_GAP_THRESHOLD_RATIO,
    _MERGE_Y_THRESHOLD_MULTIPLIER,
    _MERGE_Y_THRESHOLD_RATIO,
)
from ._ocr_postprocess import (
    _build_primary_ocr_quality_notes,
    _dedupe_overlapping_ocr_items,
    _filter_contextual_noise_items,
    _is_probably_noise_line,
    _merge_line_items_prefer_primary,
    _merge_ocr_items_to_lines,
    _normalize_bbox_px,
    _normalize_ocr_items_as_lines,
)

# ---------------------------------------------------------------------------
# Constants: Overlap merge threshold
# ---------------------------------------------------------------------------
_OVERLAP_MERGE_THRESHOLD = 0.90
"""Overlap ratio threshold for merging overlapping boxes."""


# ---------------------------------------------------------------------------
# Constants: Word-level merge detection
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
_WORD_MERGE_AI_OCR_MIN_ITEMS = 140
"""Minimum item count for AI OCR word-level merge detection."""

_WORD_MERGE_AI_OCR_WIDTH_RATIO = 0.18
"""Width ratio threshold for AI OCR word-level detection."""

_WORD_MERGE_AI_OCR_HEIGHT_MULTIPLIER = 2.9
"""Height multiplier for AI OCR word-level detection."""

_WORD_MERGE_PADDLE_MIN_ITEMS = 80
"""Minimum item count for PaddleOCR word-level merge detection."""

_WORD_MERGE_PADDLE_WIDTH_RATIO = 0.22
"""Width ratio threshold for PaddleOCR word-level detection."""

_WORD_MERGE_PADDLE_HEIGHT_MULTIPLIER = 3.2
"""Height multiplier for PaddleOCR word-level detection."""

# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Constants: AI supplement pruning (hybrid mode)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
_AI_SUPPLEMENT_HEIGHT_MULTIPLIER = 3.0
"""Multiplier for baseline height in coarse paragraph detection."""

_AI_SUPPLEMENT_HEIGHT_RATIO = 0.14
"""Height ratio of image for coarse paragraph detection."""

_AI_SUPPLEMENT_WIDTH_RATIO = 0.20
"""Width ratio of image for coarse paragraph detection."""

_AI_SUPPLEMENT_TEXT_LENGTH = 8
"""Text length threshold for coarse paragraph detection."""

_AI_SUPPLEMENT_WIDE_WIDTH_RATIO = 0.90
"""Width ratio for wide paragraph detection."""

_AI_SUPPLEMENT_WIDE_HEIGHT_MULTIPLIER = 1.8
"""Multiplier for baseline height in wide paragraph detection."""

_AI_SUPPLEMENT_WIDE_HEIGHT_RATIO = 0.08
"""Height ratio of image for wide paragraph detection."""

_AI_SUPPLEMENT_FALLBACK_HEIGHT_RATIO = 0.16
"""Height ratio for fallback paragraph detection."""

_AI_SUPPLEMENT_FALLBACK_WIDTH_RATIO = 0.20

# Tesseract defaults (shared with _tesseract_ocr)
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

class OcrManager:
    """
    OCR manager with strict provider behavior.

    Policy:
    - If provider is explicitly `tesseract`/`local`, use Tesseract only.
    - For explicit providers (`aiocr`, `paddle`, `paddle_local`, `baidu`), strict
      mode keeps the provider pure. Non-strict mode may add local OCR fallbacks.
    - With `strict_no_fallback=True`, `auto` mode does not use local fallback
      providers; it requires AI OCR and fails fast on setup/runtime failures.
    - With `strict_no_fallback=False`, `auto` mode keeps hybrid fallback behavior.
    """

    def __init__(
        self,
        provider: str | None = None,
        *,
        route_kind: str | None = None,
        ai_provider: str | None = None,
        ai_api_key: str | None = None,
        ai_base_url: str | None = None,
        ai_model: str | None = None,
        ai_layout_model: str | None = None,
        paddle_doc_max_side_px: int | None = None,
        layout_block_max_concurrency: int | None = None,
        request_rpm_limit: int | None = None,
        request_tpm_limit: int | None = None,
        request_max_retries: int | None = None,
        prompt_preset: str | None = None,
        direct_prompt_override: str | None = None,
        layout_block_prompt_override: str | None = None,
        image_region_prompt_override: str | None = None,
        baidu_app_id: str | None = None,
        baidu_api_key: str | None = None,
        baidu_secret_key: str | None = None,
        tesseract_min_confidence: float | None = None,
        tesseract_language: str | None = None,
        strict_no_fallback: bool = False,
        allow_paddle_model_downgrade: bool = False,
        enable_layout: bool = True,
        enable_sam: bool | None = None,
    ):
        """Initialize OCR manager with primary and fallback providers."""
        self.providers: list[OcrProvider] = []
        self.primary_provider: Optional[OcrProvider] = None
        self.fallback_provider: Optional[OcrProvider] = None
        self.last_provider_name: str | None = None
        self.last_provider_error: str | None = None
        self.last_fallback_reason: str | None = None
        self.last_quality_notes: list[str] = []
        self.last_image_regions: list[Any] = []
        self.last_layout_blocks: list[dict[str, Any]] = []
        self.last_layout_analysis_debug: dict[str, Any] | None = None
        self.provider_id: str = "auto"
        self.route_kind: str = ROUTE_KIND_HYBRID_AUTO
        self.strict_no_fallback: bool = bool(strict_no_fallback)
        self.allow_paddle_model_downgrade: bool = bool(allow_paddle_model_downgrade)
        self.enable_layout: bool = bool(enable_layout)
        self.ai_provider_disabled: bool = False
        self.ai_provider_disabled_reason: str | None = None
        # Keep typed references so `auto` mode can combine results.
        self.baidu_provider: BaiduOcrClient | None = None
        self.tesseract_provider: TesseractOcrClient | None = None
        self.paddle_provider: AiOcrClient | PaddleOcrClient | None = None
        self.paddle_local_fallback_provider: OcrProvider | None = None
        self.ai_provider: AiOcrClient | None = None

        provider_id = (provider or "auto").strip().lower()
        # Backward compatibility: legacy ids map to canonical provider names.
        if provider_id in {"remote", "ai"}:
            provider_id = "aiocr"
        if provider_id in {"paddle-local", "local_paddle"}:
            provider_id = "machine"
        # paddle_local → paddleocr (new canonical name)
        if provider_id == "paddle_local":
            provider_id = "paddleocr"
        if provider_id not in {
            "auto",
            "aiocr",
            "baidu",
            "machine",
            "tesseract",
            "local",
            "paddle",
            "paddleocr",
        }:
            raise ValueError(f"Unsupported OCR provider: {provider_id}")
        self.provider_id = provider_id
        self.route_kind = normalize_ocr_route_kind(
            route_kind,
            default=(ROUTE_KIND_HYBRID_AUTO if provider_id == "auto" else "unknown"),
        )

        tesseract_min_conf = (
            float(tesseract_min_confidence)
            if tesseract_min_confidence is not None
            else None
        )
        # Prefer a bilingual default for scanned PDFs. Both language packs are
        # installed in the Docker image.
        tesseract_lang = (tesseract_language or "chi_sim+eng").strip() or "chi_sim+eng"

        def _maybe_add_tesseract_fallback(*, reason: str) -> None:
            """Add local Tesseract as a best-effort fallback provider.

            In strict mode we keep explicit providers "pure" (no implicit
            fallback). In non-strict mode, a Tesseract fallback makes explicit
            AI/cloud OCR options more reliable in open-source deployments.
            """

            if self.strict_no_fallback:
                return
            if self.tesseract_provider is not None:
                return
            try:
                self.tesseract_provider = TesseractOcrClient(
                    min_confidence=tesseract_min_conf or _TESSERACT_DEFAULT_MIN_CONFIDENCE,
                    language=tesseract_lang,
                )
                self.providers.append(self.tesseract_provider)
                logger.info(
                    "Added Tesseract OCR as fallback provider (reason=%s)",
                    reason,
                )
            except Exception as e:
                logger.warning(
                    "Tesseract OCR fallback unavailable (reason=%s): %s",
                    reason,
                    e,
                )

        def _maybe_add_paddle_local_fallback(*, reason: str) -> None:
            """Add local PaddleOCR as a lazy fallback provider in non-strict mode."""

            if self.strict_no_fallback:
                return
            if any(
                isinstance(provider_obj, (PaddleOcrClient, LazyPaddleOcrClient))
                for provider_obj in self.providers
            ):
                return

            paddle_lang = "en" if tesseract_lang.strip().lower() == "eng" else "ch"
            try:
                self.paddle_local_fallback_provider = LazyPaddleOcrClient(
                    language=paddle_lang,
                    layout_model=ai_layout_model,
                    enable_layout=self.enable_layout,
                    enable_sam=enable_sam,
                )
                self.providers.append(self.paddle_local_fallback_provider)
                logger.info(
                    "Added local PaddleOCR as lazy fallback provider (reason=%s, lang=%s)",
                    reason,
                    paddle_lang,
                )
            except Exception as e:
                logger.warning(
                    "Local PaddleOCR fallback unavailable (reason=%s): %s",
                    reason,
                    e,
                )

        if provider_id == "aiocr":
            if not ai_api_key:
                raise ValueError("AI OCR requires api_key")
            remote_spec = resolve_remote_ocr_client_spec(
                provider_id=provider_id,
                ai_provider=ai_provider,
                ai_base_url=ai_base_url,
                ai_model=ai_model,
                route_kind=route_kind,
            )
            self.route_kind = remote_spec.route_kind
            self.ai_provider = create_remote_ocr_client(
                requested_provider=provider_id,
                route_kind=route_kind,
                ai_provider=ai_provider,
                ai_api_key=ai_api_key,
                ai_base_url=ai_base_url,
                ai_model=ai_model,
                ai_layout_model=ai_layout_model,
                paddle_doc_max_side_px=paddle_doc_max_side_px,
                layout_block_max_concurrency=layout_block_max_concurrency,
                request_rpm_limit=request_rpm_limit,
                request_tpm_limit=request_tpm_limit,
                request_max_retries=request_max_retries,
                prompt_preset=prompt_preset,
                direct_prompt_override=direct_prompt_override,
                layout_block_prompt_override=layout_block_prompt_override,
                image_region_prompt_override=image_region_prompt_override,
                allow_paddle_model_downgrade=self.allow_paddle_model_downgrade,
            )
            self.providers.append(self.ai_provider)
            logger.info(
                "Using AI OCR as primary provider (route=%s, vendor=%s, model=%s, base_url=%s)",
                self.ai_provider.route_kind,
                self.ai_provider.provider_id,
                self.ai_provider.model,
                self.ai_provider.base_url or "<default>",
            )
            _maybe_add_tesseract_fallback(reason=remote_spec.route_kind)
            _maybe_add_paddle_local_fallback(reason=remote_spec.route_kind)
        if provider_id in {"baidu"}:
            self.baidu_provider = BaiduOcrClient(
                app_id=baidu_app_id,
                api_key=baidu_api_key,
                secret_key=baidu_secret_key,
            )
            self.providers.append(self.baidu_provider)
            logger.info("Using Baidu OCR (explicit)")
            _maybe_add_tesseract_fallback(reason="baidu")
            _maybe_add_paddle_local_fallback(reason="baidu")
        if provider_id in {"tesseract", "local", "machine"}:
            # machine provider: try PaddleOCR local first (better quality),
            # fall back to Tesseract.  tesseract/local: Tesseract only.
            if provider_id == "machine":
                paddle_lang = "en" if tesseract_lang.strip().lower() == "eng" else "ch"
                try:
                    self.paddle_provider = PaddleOcrClient(
                        language=paddle_lang,
                        layout_model=ai_layout_model,
                        enable_layout=self.enable_layout,
                        enable_sam=enable_sam,
                    )
                    self.providers.append(self.paddle_provider)
                    logger.info("Using local PaddleOCR as primary in machine mode (lang=%s)", paddle_lang)
                except (ImportError, RuntimeError) as e:
                    logger.warning("Local PaddleOCR not available in machine mode: %s", e)
            try:
                self.tesseract_provider = TesseractOcrClient(
                    min_confidence=tesseract_min_conf or _TESSERACT_DEFAULT_MIN_CONFIDENCE,
                    language=tesseract_lang,
                )
                if provider_id != "machine" or not self.providers:
                    # For explicit tesseract/local, always add. For machine,
                    # only add as fallback if PaddleOCR is not available.
                    self.providers.append(self.tesseract_provider)
                    logger.info("Using Tesseract OCR (explicit)")
                else:
                    logger.info("Tesseract OCR available as fallback in machine mode")
            except (ImportError, RuntimeError) as e:
                if provider_id != "machine":
                    raise
                logger.warning("Tesseract not available in machine mode: %s", e)
        if provider_id == "paddle_local":
            paddle_lang = "en" if tesseract_lang.strip().lower() == "eng" else "ch"
            self.paddle_provider = PaddleOcrClient(
                language=paddle_lang,
                layout_model=ai_layout_model,
                enable_layout=self.enable_layout,
                enable_sam=enable_sam,
            )
            self.providers.append(self.paddle_provider)
            logger.info("Using local PaddleOCR (explicit, lang=%s)", paddle_lang)
            _maybe_add_tesseract_fallback(reason="paddle_local")
        if provider_id == "paddleocr":
            paddle_lang = "en" if tesseract_lang.strip().lower() == "eng" else "ch"
            self.paddle_provider = PaddleOcrClient(
                language=paddle_lang,
                layout_model=ai_layout_model,
                enable_layout=self.enable_layout,
                enable_sam=enable_sam,
            )
            self.providers.append(self.paddle_provider)
            logger.info("Using local PaddleOCR (explicit, lang=%s)", paddle_lang)
            _maybe_add_tesseract_fallback(reason="paddleocr")
        if provider_id == "paddle":
            if not ai_api_key:
                raise ValueError("Paddle OCR requires api_key")
            remote_spec = resolve_remote_ocr_client_spec(
                provider_id=provider_id,
                ai_provider=ai_provider,
                ai_base_url=ai_base_url,
                ai_model=ai_model,
                route_kind=route_kind,
            )
            self.route_kind = remote_spec.route_kind
            self.paddle_provider = create_remote_ocr_client(
                requested_provider=provider_id,
                route_kind=route_kind,
                ai_provider=ai_provider,
                ai_api_key=ai_api_key,
                ai_base_url=ai_base_url,
                ai_model=ai_model,
                ai_layout_model=ai_layout_model,
                paddle_doc_max_side_px=paddle_doc_max_side_px,
                layout_block_max_concurrency=layout_block_max_concurrency,
                request_rpm_limit=request_rpm_limit,
                request_tpm_limit=request_tpm_limit,
                request_max_retries=request_max_retries,
                prompt_preset=prompt_preset,
                direct_prompt_override=direct_prompt_override,
                layout_block_prompt_override=layout_block_prompt_override,
                image_region_prompt_override=image_region_prompt_override,
                allow_paddle_model_downgrade=self.allow_paddle_model_downgrade,
            )
            self.providers.append(self.paddle_provider)
            logger.info(
                "Using PaddleOCR-VL as primary provider (route=%s, vendor=%s, model=%s, base_url=%s)",
                self.paddle_provider.route_kind,
                self.paddle_provider.provider_id,
                self.paddle_provider.model,
                self.paddle_provider.base_url or "<default>",
            )
            _maybe_add_tesseract_fallback(reason=remote_spec.route_kind)
            _maybe_add_paddle_local_fallback(reason=remote_spec.route_kind)

        if provider_id == "auto":
            if self.strict_no_fallback:
                if not ai_api_key:
                    raise RuntimeError(
                        "Strict OCR mode with provider=auto requires AI OCR credentials; "
                        "set ocr_provider=paddle/aiocr (recommended) or disable strict mode explicitly."
                    )

                remote_spec = resolve_remote_ocr_client_spec(
                    provider_id="aiocr",
                    ai_provider=ai_provider,
                    ai_base_url=ai_base_url,
                    ai_model=ai_model,
                    route_kind=route_kind,
                )
                self.route_kind = remote_spec.route_kind
                self.ai_provider = create_remote_ocr_client(
                    requested_provider="aiocr",
                    route_kind=route_kind,
                    ai_provider=ai_provider,
                    ai_api_key=ai_api_key,
                    ai_base_url=ai_base_url,
                    ai_model=ai_model,
                    ai_layout_model=ai_layout_model,
                    paddle_doc_max_side_px=paddle_doc_max_side_px,
                    layout_block_max_concurrency=layout_block_max_concurrency,
                    request_rpm_limit=request_rpm_limit,
                    request_tpm_limit=request_tpm_limit,
                    request_max_retries=request_max_retries,
                    prompt_preset=prompt_preset,
                    direct_prompt_override=direct_prompt_override,
                    layout_block_prompt_override=layout_block_prompt_override,
                    image_region_prompt_override=image_region_prompt_override,
                    allow_paddle_model_downgrade=self.allow_paddle_model_downgrade,
                )
                self.providers.append(self.ai_provider)
                logger.info(
                    "Using AI OCR as primary provider in strict auto mode (route=%s, vendor=%s, model=%s)",
                    self.ai_provider.route_kind,
                    self.ai_provider.provider_id,
                    self.ai_provider.model,
                )
            else:
                # Default behavior for scanned PDFs: prefer bbox-accurate machine OCR
                # for *geometry* (line bboxes), then optionally merge/refine with AI.
                try:
                    self.baidu_provider = BaiduOcrClient(
                        app_id=baidu_app_id,
                        api_key=baidu_api_key,
                        secret_key=baidu_secret_key,
                    )
                    self.providers.append(self.baidu_provider)
                    logger.info("Using Baidu OCR as primary provider")
                except (ValueError, ImportError) as e:
                    logger.warning("Baidu OCR not available: %s", e)

                # In auto mode, allow local Tesseract as fallback.
                try:
                    self.tesseract_provider = TesseractOcrClient(
                        min_confidence=tesseract_min_conf or _TESSERACT_DEFAULT_MIN_CONFIDENCE,
                        language=tesseract_lang,
                    )
                    self.providers.append(self.tesseract_provider)
                    logger.info("Using Tesseract OCR as fallback provider in auto mode")
                except (ImportError, RuntimeError) as e:
                    logger.warning("Tesseract OCR not available in auto mode: %s", e)

                # In auto mode, allow local PaddleOCR as fallback.
                if not self.providers:
                    try:
                        self.paddle_provider = PaddleOcrClient(enable_layout=self.enable_layout, enable_sam=enable_sam)
                        self.providers.append(self.paddle_provider)
                        logger.info("Using PaddleOCR as fallback provider in auto mode")
                    except (ImportError, RuntimeError) as e:
                        logger.warning("PaddleOCR not available in auto mode: %s", e)

                try:
                    if ai_api_key:
                        remote_spec = resolve_remote_ocr_client_spec(
                            provider_id="aiocr",
                            ai_provider=ai_provider,
                            ai_base_url=ai_base_url,
                            ai_model=ai_model,
                            route_kind=route_kind,
                        )
                        self.ai_provider = create_remote_ocr_client(
                            requested_provider="aiocr",
                            route_kind=route_kind,
                            ai_provider=ai_provider,
                            ai_api_key=ai_api_key,
                            ai_base_url=ai_base_url,
                            ai_model=ai_model,
                            ai_layout_model=ai_layout_model,
                            paddle_doc_max_side_px=paddle_doc_max_side_px,
                            prompt_preset=prompt_preset,
                            direct_prompt_override=direct_prompt_override,
                            layout_block_prompt_override=layout_block_prompt_override,
                            image_region_prompt_override=image_region_prompt_override,
                            allow_paddle_model_downgrade=self.allow_paddle_model_downgrade,
                        )
                        self.providers.append(self.ai_provider)
                        logger.info(
                            "Using AI OCR as supplementary provider in auto mode (route=%s)",
                            self.ai_provider.route_kind,
                        )
                except Exception as e:
                    logger.warning("AI OCR not available: %s", e)

        if not self.providers:
            raise RuntimeError(
                "No OCR provider available. Install baidu-aip, pytesseract, or paddleocr."
            )

        self.primary_provider = self.providers[0]
        self.fallback_provider = self.providers[1] if len(self.providers) > 1 else None

    def ocr_image_lines(
        self, image_path: str, *, image_width: int, image_height: int
    ) -> list[dict]:
        """Return *line-level* OCR items (best-effort).

        In `auto` mode we combine available sources (for example
        Baidu / Tesseract / AI OCR) to reduce missed lines on scan-heavy PDFs.
        """

        W = int(image_width)
        H = int(image_height)
        self.last_quality_notes = []
        self.last_image_regions = []
        self.last_layout_blocks = []
        self.last_layout_analysis_debug = None
        if W <= 0 or H <= 0:
            return []

        if self.provider_id != "auto":
            raw = self.ocr_image(image_path)
            # Providers like Baidu and AI OCR typically return line-level items
            # already. Re-merging can create huge paragraph-like boxes.
            if self.provider_id == "baidu":
                return _normalize_ocr_items_as_lines(raw, image_width=W, image_height=H)
            if self.provider_id in {"aiocr", "paddle"}:
                normalized = _normalize_ocr_items_as_lines(
                    raw, image_width=W, image_height=H
                )
                primary_model = None
                if self.ai_provider is not None:
                    primary_model = getattr(self.ai_provider, "model", None)
                elif self.paddle_provider is not None:
                    primary_model = getattr(self.paddle_provider, "model", None)
                self.last_quality_notes = _build_primary_ocr_quality_notes(
                    normalized,
                    image_width=W,
                    image_height=H,
                    provider_name=self.last_provider_name,
                    model_name=primary_model,
                )

                # Defensive: some remote OCR models still return word-level
                # boxes even when prompted for line-level output. If we see a
                # very fragmented result, merge into line-level to keep PPT
                # shape count reasonable and improve wrap/size fitting.
                widths: list[float] = []
                heights: list[float] = []
                for it in normalized:
                    if not isinstance(it, dict):
                        continue
                    bbox_n = _normalize_bbox_px(it.get("bbox"))
                    if bbox_n is None:
                        continue
                    x0, y0, x1, y1 = bbox_n
                    w = float(x1 - x0)
                    h = float(y1 - y0)
                    if w > 0 and h > 0:
                        widths.append(w)
                        heights.append(h)

                allow_merge = False
                if widths and heights and len(widths) >= _WORD_MERGE_AI_OCR_MIN_ITEMS:
                    widths.sort()
                    heights.sort()
                    median_w = float(widths[len(widths) // 2])
                    median_h = float(heights[len(heights) // 2])
                    # Word-level output tends to have narrow boxes compared to
                    # page width and relative to glyph height.
                    if median_w <= max(_WORD_MERGE_AI_OCR_WIDTH_RATIO * float(W), _WORD_MERGE_AI_OCR_HEIGHT_MULTIPLIER * float(median_h)):
                        allow_merge = True

                if allow_merge:
                    return _merge_ocr_items_to_lines(
                        normalized,
                        image_width=W,
                        image_height=H,
                        allow_merge=True,
                    )
                return normalized
            if self.provider_id in {"paddle_local", "machine", "paddleocr"}:
                # PaddleOCR local output format varies across versions/models.
                # Some pipelines emit per-word boxes (very fragmented), which
                # leads to thousands of PPT shapes and poor line wrapping/font
                # fitting downstream. Detect this case and merge into
                # line-level boxes.
                widths: list[float] = []
                heights: list[float] = []
                for it in raw:
                    if not isinstance(it, dict):
                        continue
                    bbox_n = _normalize_bbox_px(it.get("bbox"))
                    if bbox_n is None:
                        continue
                    x0, y0, x1, y1 = bbox_n
                    w = float(x1 - x0)
                    h = float(y1 - y0)
                    if w > 0 and h > 0:
                        widths.append(w)
                        heights.append(h)

                allow_merge = False
                if widths and heights and len(widths) >= _WORD_MERGE_PADDLE_MIN_ITEMS:
                    widths.sort()
                    heights.sort()
                    median_w = float(widths[len(widths) // 2])
                    median_h = float(heights[len(heights) // 2])
                    # Word-level output tends to have narrow boxes compared to
                    # the page width and relative to glyph height.
                    if median_w <= max(_WORD_MERGE_PADDLE_WIDTH_RATIO * float(W), _WORD_MERGE_PADDLE_HEIGHT_MULTIPLIER * float(median_h)):
                        allow_merge = True

                return _merge_ocr_items_to_lines(
                    raw,
                    image_width=W,
                    image_height=H,
                    allow_merge=allow_merge,
                )
            return _merge_ocr_items_to_lines(
                raw,
                image_width=W,
                image_height=H,
                allow_merge=False,
            )

        last_error: Exception | None = None
        baidu_lines: list[dict] = []
        tesseract_lines: list[dict] = []
        paddle_lines: list[dict] = []
        ai_lines: list[dict] = []
        ai_image_regions: list[Any] = []

        if self.baidu_provider is not None:
            try:
                raw_baidu = self.baidu_provider.ocr_image(image_path)
                baidu_lines = _normalize_ocr_items_as_lines(
                    raw_baidu, image_width=W, image_height=H
                )
            except Exception as e:
                last_error = e
                logger.warning("Baidu OCR failed (auto mode): %s", e)

        if self.tesseract_provider is not None:
            try:
                raw_tess = self.tesseract_provider.ocr_image(image_path)
                tesseract_lines = _merge_ocr_items_to_lines(
                    raw_tess,
                    image_width=W,
                    image_height=H,
                    allow_merge=False,
                )
            except Exception as e:
                last_error = e
                logger.warning("Tesseract OCR failed (auto mode): %s", e)

        if self.paddle_provider is not None:
            try:
                raw_paddle = self.paddle_provider.ocr_image(image_path)
                paddle_lines = _merge_ocr_items_to_lines(
                    raw_paddle,
                    image_width=W,
                    image_height=H,
                    allow_merge=True,
                )
            except Exception as e:
                last_error = e
                logger.warning("Paddle OCR failed (auto mode): %s", e)

        if self.ai_provider is not None:
            try:
                raw_ai = self.ai_provider.ocr_image(image_path)
                ai_image_regions = [
                    _clone_image_region_payload(region)
                    for region in getattr(self.ai_provider, "last_image_regions_px", [])
                ]
                self.last_layout_blocks = [
                    dict(block)
                    for block in getattr(self.ai_provider, "last_layout_blocks", [])
                    if isinstance(block, dict)
                ]
                layout_debug = getattr(
                    self.ai_provider, "last_layout_analysis_debug", None
                )
                self.last_layout_analysis_debug = (
                    dict(layout_debug) if isinstance(layout_debug, dict) else None
                )
                ai_lines = _normalize_ocr_items_as_lines(
                    raw_ai, image_width=W, image_height=H
                )
            except Exception as e:
                last_error = e
                logger.warning("AI OCR failed (auto mode): %s", e)

        def _median_line_height(items: list[dict]) -> float:
            hs: list[float] = []
            for it in items:
                if not isinstance(it, dict):
                    continue
                bbox_n = _normalize_bbox_px(it.get("bbox"))
                if bbox_n is None:
                    continue
                _, y0, _, y1 = bbox_n
                h = float(y1 - y0)
                if h > 0:
                    hs.append(h)
            if not hs:
                return 0.0
            hs.sort()
            return max(1.0, float(hs[len(hs) // 2]))

        def _prune_ai_supplement(items: list[dict], *, baseline_h: float) -> list[dict]:
            """Drop likely coarse AI paragraph boxes when machine OCR exists."""

            out: list[dict] = []
            baseline_h = max(0.0, float(baseline_h))
            for it in items:
                if not isinstance(it, dict):
                    continue
                text = str(it.get("text") or "").strip()
                bbox_n = _normalize_bbox_px(it.get("bbox"))
                if not text or bbox_n is None:
                    continue
                if _is_probably_noise_line(text, bbox_n, image_width=W, image_height=H):
                    continue
                x0, y0, x1, y1 = bbox_n
                w = max(1.0, float(x1 - x0))
                h = max(1.0, float(y1 - y0))

                # Coarse paragraph-like boxes are harmful in hybrid mode:
                # they over-erase backgrounds and break text/image separation.
                if baseline_h > 0.0:
                    if h >= max(_AI_SUPPLEMENT_HEIGHT_MULTIPLIER * baseline_h, _AI_SUPPLEMENT_HEIGHT_RATIO * float(H)) and (
                        w >= _AI_SUPPLEMENT_WIDTH_RATIO * float(W) or len(text) >= _AI_SUPPLEMENT_TEXT_LENGTH
                    ):
                        continue
                    if w >= _AI_SUPPLEMENT_WIDE_WIDTH_RATIO * float(W) and h >= max(
                        _AI_SUPPLEMENT_WIDE_HEIGHT_MULTIPLIER * baseline_h, _AI_SUPPLEMENT_WIDE_HEIGHT_RATIO * float(H)
                    ):
                        continue
                else:
                    if h >= _AI_SUPPLEMENT_FALLBACK_HEIGHT_RATIO * float(H) and w >= _AI_SUPPLEMENT_FALLBACK_WIDTH_RATIO * float(W):
                        continue

                out.append({**it, "text": text, "bbox": [x0, y0, x1, y1]})

            out.sort(
                key=lambda it: ((it["bbox"][1] + it["bbox"][3]) / 2.0, it["bbox"][0])
            )
            return out

        machine_lines: list[dict] = []
        if baidu_lines:
            machine_lines.extend(baidu_lines)
        if tesseract_lines:
            machine_lines.extend(tesseract_lines)
        if paddle_lines:
            machine_lines.extend(paddle_lines)
        if ai_lines and machine_lines:
            machine_h = _median_line_height(machine_lines)
            ai_lines = _prune_ai_supplement(ai_lines, baseline_h=machine_h)

        # Merge available line lists in a preferred order.
        merged: list[dict] = []
        providers_used: list[str] = []

        def _merge_in(items: list[dict], label: str) -> None:
            nonlocal merged, providers_used
            if not items:
                return
            if not merged:
                merged = list(items)
                providers_used = [label]
                return
            merged = _merge_line_items_prefer_primary(
                merged, items, image_width=W, image_height=H
            )
            if label not in providers_used:
                providers_used.append(label)

        # Choose base ordering (machine OCR first for geometry, AI as supplement).
        if baidu_lines:
            _merge_in(baidu_lines, "Baidu")
        if tesseract_lines:
            _merge_in(tesseract_lines, "Tesseract")
        if paddle_lines:
            _merge_in(paddle_lines, "Paddle")
        if ai_lines:
            _merge_in(ai_lines, "AI")

        if merged:
            self.last_image_regions = [
                _clone_image_region_payload(region) for region in ai_image_regions
            ]
            self.last_provider_name = (
                f"HybridOcr({'+'.join(providers_used)})"
                if len(providers_used) > 1
                else (
                    "BaiduOcrClient"
                    if providers_used[0] == "Baidu"
                    else (
                        "TesseractOcrClient"
                        if providers_used[0] == "Tesseract"
                        else (
                            "PaddleOcrClient"
                            if providers_used[0] == "Paddle"
                            else "AiOcrClient"
                        )
                    )
                )
            )
            return merged

        # Defensive fallback: re-run AI OCR directly if all merged lists are empty.
        if self.ai_provider is not None:
            try:
                raw_ai = self.ai_provider.ocr_image(image_path)
                self.last_image_regions = [
                    _clone_image_region_payload(region)
                    for region in getattr(self.ai_provider, "last_image_regions_px", [])
                ]
                self.last_layout_blocks = [
                    dict(block)
                    for block in getattr(self.ai_provider, "last_layout_blocks", [])
                    if isinstance(block, dict)
                ]
                layout_debug = getattr(
                    self.ai_provider, "last_layout_analysis_debug", None
                )
                self.last_layout_analysis_debug = (
                    dict(layout_debug) if isinstance(layout_debug, dict) else None
                )
                self.last_provider_name = "AiOcrClient"
                return _normalize_ocr_items_as_lines(
                    raw_ai, image_width=W, image_height=H
                )
            except Exception as e:
                last_error = e
                logger.warning("AI OCR failed (auto mode): %s", e)

        if self.paddle_provider is not None:
            try:
                raw_paddle = self.paddle_provider.ocr_image(image_path)
                self.last_provider_name = "PaddleOcrClient"
                return _merge_ocr_items_to_lines(
                    raw_paddle,
                    image_width=W,
                    image_height=H,
                    allow_merge=True,
                )
            except Exception as e:
                last_error = e
                logger.warning("Paddle OCR failed (auto mode): %s", e)

        raise RuntimeError("All OCR providers failed") from last_error

    def ocr_image(self, image_path: str) -> List[Dict]:
        """
        Perform OCR with automatic fallback.

        Args:
            image_path: Path to the image file

        Returns:
            List of text elements with bbox and confidence
        """
        last_error: Exception | None = None
        self.last_provider_error = None
        self.last_fallback_reason = None
        self.last_quality_notes = []
        self.last_image_regions = []
        self.last_layout_blocks = []
        self.last_layout_analysis_debug = None
        for provider in self.providers:
            if self.ai_provider_disabled and isinstance(provider, AiOcrClient):
                continue
            try:
                out = provider.ocr_image(image_path)
                self.last_provider_name = provider.__class__.__name__
                self.last_image_regions = [
                    _clone_image_region_payload(region)
                    for region in getattr(provider, "last_image_regions_px", [])
                ]
                self.last_layout_blocks = [
                    dict(block)
                    for block in getattr(provider, "last_layout_blocks", [])
                    if isinstance(block, dict)
                ]
                layout_debug = getattr(provider, "last_layout_analysis_debug", None)
                self.last_layout_analysis_debug = (
                    dict(layout_debug) if isinstance(layout_debug, dict) else None
                )
                if isinstance(provider, AiOcrClient):
                    self.last_fallback_reason = None
                elif self.ai_provider_disabled:
                    self.last_fallback_reason = (
                        self.ai_provider_disabled_reason
                        or "aiocr_disabled_after_runtime_failure"
                    )
                return out
            except Exception as e:
                last_error = e
                self.last_provider_error = str(e)
                logger.warning(f"OCR provider failed: {str(e)}")
                if isinstance(provider, AiOcrClient) and not self.strict_no_fallback:
                    err = str(e).strip()
                    err_l = err.lower()
                    disable_markers = (
                        "ai ocr returned no items",
                        "ai ocr returned no parseable items",
                        "ai ocr returned empty",
                        "plain text without bbox",
                        "structural gibberish",
                        "timed out",
                        "timeout",
                    )
                    if any(marker in err_l for marker in disable_markers):
                        self.ai_provider_disabled = True
                        self.ai_provider_disabled_reason = (
                            f"aiocr_runtime_failure:{err or 'unknown'}"
                        )
                        logger.warning(
                            "Disabling AI OCR provider for remaining pages: %s",
                            err or "unknown",
                        )
                continue

        raise RuntimeError("All OCR providers failed") from last_error

    def detect_image_regions(self, image_path: str) -> list[Any]:
        if self.last_image_regions:
            return [
                _clone_image_region_payload(region)
                for region in self.last_image_regions
            ]

        if self.ai_provider_disabled:
            return []

        candidate_provider: OcrProvider | None = None
        if self.provider_id == "aiocr" and self.ai_provider is not None:
            candidate_provider = self.ai_provider
        elif self.provider_id == "paddle" and isinstance(
            self.paddle_provider, AiOcrClient
        ):
            candidate_provider = self.paddle_provider
        elif self.ai_provider is not None:
            candidate_provider = self.ai_provider
        elif isinstance(self.paddle_provider, AiOcrClient):
            candidate_provider = self.paddle_provider

        if candidate_provider is None:
            return []

        detect = getattr(candidate_provider, "detect_image_regions", None)
        if not callable(detect):
            return []

        try:
            regions = detect(image_path)
        except Exception as e:
            logger.warning("OCR image-region detection failed: %s", e)
            self.last_image_regions = []
            return []

        self.last_image_regions = [
            _clone_image_region_payload(region) for region in regions
        ]
        return [
            _clone_image_region_payload(region) for region in self.last_image_regions
        ]

    def convert_bbox_to_pdf_coords(
        self,
        bbox: List[float],
        image_width: int,
        image_height: int,
        page_width_pt: float,
        page_height_pt: float,
    ) -> List[float]:
        """
        Convert OCR bounding box from image coordinates to PDF points.

        Args:
            bbox: [x0, y0, x1, y1] in image coordinates
            image_width: Image width in pixels
            image_height: Image height in pixels
            page_width_pt: PDF page width in points
            page_height_pt: PDF page height in points

        Returns:
            [x0, y0, x1, y1] in PDF points
        """
        x0, y0, x1, y1 = bbox

        # Scale factors
        scale_x = page_width_pt / image_width
        scale_y = page_height_pt / image_height

        # Convert coordinates
        pdf_x0 = x0 * scale_x
        pdf_y0 = y0 * scale_y
        pdf_x1 = x1 * scale_x
        pdf_y1 = y1 * scale_y

        return [pdf_x0, pdf_y0, pdf_x1, pdf_y1]


def create_ocr_manager(
    provider: str | None = None,
    *,
    route_kind: str | None = None,
    ai_provider: str | None = None,
    ai_api_key: str | None = None,
    ai_base_url: str | None = None,
    ai_model: str | None = None,
    ai_layout_model: str | None = None,
    paddle_doc_max_side_px: int | None = None,
    layout_block_max_concurrency: int | None = None,
    request_rpm_limit: int | None = None,
    request_tpm_limit: int | None = None,
    request_max_retries: int | None = None,
    prompt_preset: str | None = None,
    direct_prompt_override: str | None = None,
    layout_block_prompt_override: str | None = None,
    image_region_prompt_override: str | None = None,
    baidu_app_id: str | None = None,
    baidu_api_key: str | None = None,
    baidu_secret_key: str | None = None,
    tesseract_min_confidence: float | None = None,
    tesseract_language: str | None = None,
    strict_no_fallback: bool = False,
    allow_paddle_model_downgrade: bool = False,
    enable_layout: bool = True,
    enable_sam: bool | None = None,
) -> OcrManager:
    """
    Factory function to create OCR manager.

    Returns:
        Configured OcrManager instance
    """
    return OcrManager(
        provider=provider,
        route_kind=route_kind,
        ai_provider=ai_provider,
        ai_api_key=ai_api_key,
        ai_base_url=ai_base_url,
        ai_model=ai_model,
        ai_layout_model=ai_layout_model,
        paddle_doc_max_side_px=paddle_doc_max_side_px,
        layout_block_max_concurrency=layout_block_max_concurrency,
        request_rpm_limit=request_rpm_limit,
        request_tpm_limit=request_tpm_limit,
        request_max_retries=request_max_retries,
        prompt_preset=prompt_preset,
        direct_prompt_override=direct_prompt_override,
        layout_block_prompt_override=layout_block_prompt_override,
        image_region_prompt_override=image_region_prompt_override,
        baidu_app_id=baidu_app_id,
        baidu_api_key=baidu_api_key,
        baidu_secret_key=baidu_secret_key,
        tesseract_min_confidence=tesseract_min_confidence,
        tesseract_language=tesseract_language,
        strict_no_fallback=strict_no_fallback,
        allow_paddle_model_downgrade=allow_paddle_model_downgrade,
        enable_layout=enable_layout,
        enable_sam=enable_sam,
    )
