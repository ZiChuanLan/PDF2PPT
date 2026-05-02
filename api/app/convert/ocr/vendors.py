"""AI OCR vendor profiles and adapters.

Vendor-specific behaviour is driven by ``VendorConfig`` dataclass entries in
``VENDOR_DEFAULTS``.  The adapter classes have been reduced to a single
``OpenAiAiOcrAdapter`` (the only subclass with real custom logic — local/private
URL detection for PaddleOCR-VL doc_parser support).  Empty vendor-specific
subclasses (SiliconFlow, PPIO, Novita, DeepSeek) were removed because they
added zero behaviour.
"""

from abc import ABC
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from .base import _AI_OCR_PROVIDER_ALIASES, _VALID_AI_OCR_PROVIDERS, _clean_str
from .deepseek_parser import _is_deepseek_ocr_model


# ---------------------------------------------------------------------------
# Vendor tuning config (embedded in VendorConfig.tuning)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VendorTuningConfig:
    """Vendor-specific tuning parameters for PaddleOCR-VL doc parser.

    Defaults are sensible for most providers. Override per-vendor in
    ``VENDOR_DEFAULTS`` when a provider needs different behaviour.
    """

    # PaddleOCR-VL-1.5: bounded fan-out for doc parser recognition.
    vl_rec_max_concurrency: int = 4
    # Whether PaddleX internal queues are enabled (False = off).
    use_queues: bool = True
    # Per-predict timeout override (seconds). ``None`` = use generic default.
    predict_timeout_override: float | None = None
    # Per-retry timeout override (seconds). ``None`` = use generic default.
    retry_timeout_override: float | None = None
    # Whether to retry on timeout for PaddleOCR-VL-1.5.
    retry_on_timeout: bool = False
    # Whether to enable singleflight dedup for PaddleOCR-VL-1.5.
    singleflight: bool = False
    # How long to wait for the singleflight lock (seconds).
    singleflight_wait_s: float = 3.0
    # Layout-block max concurrency override (for Qwen3-VL etc.). ``None`` = default.
    layout_block_max_concurrency: int | None = None


# ---------------------------------------------------------------------------
# VendorConfig — single source of truth for vendor-specific behaviour
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VendorConfig:
    """Config-driven vendor profile replacing per-vendor adapter subclasses.

    All vendor-specific behaviour is expressed as flags/data on this object
    instead of subclass method overrides.
    """

    # Default base URL (None = user must provide, e.g. generic OpenAI).
    base_url: str | None = None
    # Default model name for this vendor.
    default_model: str = "gpt-4o-mini"
    # Max tokens for OCR output.
    max_tokens_ocr: int = 8192
    # Max tokens for text refiner output.
    max_tokens_refiner: int = 4096
    # URL path to force for PaddleOCR-VL doc parser ("", "/v1", "/openai").
    paddle_doc_path: str | None = None
    # Model name casing: "lowercase" (novita, ppio) or "mixed" (default).
    model_casing: str = "mixed"
    # Whether this vendor supports remote PaddleOCR-VL doc_parser protocol.
    supports_remote_paddle_doc: bool = False
    # DeepSeek grounding tags (<|ref|>, <|det|>).
    use_grounding: bool = False
    # DeepSeek image-first content ordering.
    send_image_first: bool = False
    # DeepSeek single-message format (no system message).
    single_message_format: bool = False
    # Vendor-specific tuning for PaddleOCR-VL.
    tuning: VendorTuningConfig = field(default_factory=VendorTuningConfig)


VENDOR_DEFAULTS: dict[str, VendorConfig] = {
    "openai": VendorConfig(),
    "siliconflow": VendorConfig(
        base_url="https://api.siliconflow.cn/v1",
        default_model="Qwen/Qwen2.5-VL-72B-Instruct",
        max_tokens_ocr=4096,
        max_tokens_refiner=2048,
        paddle_doc_path="/v1",
        model_casing="mixed",
        supports_remote_paddle_doc=True,
        tuning=VendorTuningConfig(
            vl_rec_max_concurrency=4,
            use_queues=False,
            predict_timeout_override=180.0,
            retry_timeout_override=20.0,
            retry_on_timeout=False,
            singleflight=True,
            singleflight_wait_s=10.0,
            layout_block_max_concurrency=2,  # Qwen3-VL on SiliconFlow
        ),
    ),
    "ppio": VendorConfig(
        base_url="https://api.ppio.com/openai",
        default_model="qwen/qwen2.5-vl-72b-instruct",
        max_tokens_ocr=4096,
        max_tokens_refiner=3072,
        paddle_doc_path="/openai",
        model_casing="lowercase",
    ),
    "novita": VendorConfig(
        base_url="https://api.novita.ai/openai",
        default_model="qwen/qwen2.5-vl-72b-instruct",
        max_tokens_ocr=4096,
        max_tokens_refiner=3072,
        paddle_doc_path="/openai",
        model_casing="lowercase",
        supports_remote_paddle_doc=True,
    ),
    "deepseek": VendorConfig(
        base_url="https://api.deepseek.com/v1",
        default_model="deepseek-ai/DeepSeek-OCR",
        max_tokens_ocr=4096,
        max_tokens_refiner=2048,
        paddle_doc_path="/v1",
        use_grounding=True,
        send_image_first=True,
        single_message_format=True,
    ),
}


def get_vendor_config(provider_id: str | None) -> VendorConfig:
    """Look up vendor config, falling back to generic OpenAI defaults."""
    normalized = (_clean_str(provider_id) or "").lower()
    return VENDOR_DEFAULTS.get(normalized, VENDOR_DEFAULTS["openai"])


def get_vendor_tuning(provider_id: str | None) -> VendorTuningConfig:
    """Look up vendor-specific tuning config, falling back to defaults."""
    return get_vendor_config(provider_id).tuning


# ---------------------------------------------------------------------------
# Legacy profile (thin wrapper for backward compat with adapter pattern)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AiOcrVendorProfile:
    """Legacy profile kept for adapter compatibility. Derived from VendorConfig."""

    provider_id: str
    default_base_url: str | None
    default_model: str
    max_tokens_ocr: int
    max_tokens_refiner: int
    supports_remote_paddle_doc_parser: bool = False


def _profile_from_config(provider_id: str, cfg: VendorConfig) -> AiOcrVendorProfile:
    return AiOcrVendorProfile(
        provider_id=provider_id,
        default_base_url=cfg.base_url,
        default_model=cfg.default_model,
        max_tokens_ocr=cfg.max_tokens_ocr,
        max_tokens_refiner=cfg.max_tokens_refiner,
        supports_remote_paddle_doc_parser=cfg.supports_remote_paddle_doc,
    )


# Build legacy profiles dict from VENDOR_DEFAULTS for backward compat.
_AI_OCR_VENDOR_PROFILES: dict[str, AiOcrVendorProfile] = {
    vid: _profile_from_config(vid, cfg) for vid, cfg in VENDOR_DEFAULTS.items()
}


# ---------------------------------------------------------------------------
# Model name normalization
# ---------------------------------------------------------------------------


def _normalize_ai_ocr_model_name(
    model_name: str | None,
    *,
    provider_id: str | None,
) -> str | None:
    cleaned = _clean_str(model_name)
    if not cleaned:
        return cleaned

    lowered = cleaned.lower()

    normalized_provider = (_clean_str(provider_id) or "").lower()
    vendor_cfg = get_vendor_config(normalized_provider)

    # OCR gateways often alias model ids with a Pro/ prefix.
    if lowered.startswith("pro/deepseek-ai/deepseek-ocr"):
        return "deepseek-ai/DeepSeek-OCR"

    if lowered == "deepseek-ai/deepseek-ocr":
        return "deepseek-ai/DeepSeek-OCR"

    if "paddleocr-vl-1.5" in lowered:
        if vendor_cfg.model_casing == "lowercase":
            return "paddlepaddle/paddleocr-vl-1.5"
        return "PaddlePaddle/PaddleOCR-VL-1.5"

    if "paddleocr-vl" in lowered:
        if vendor_cfg.model_casing == "lowercase":
            return "paddlepaddle/paddleocr-vl"
        return "PaddlePaddle/PaddleOCR-VL"

    return cleaned


# ---------------------------------------------------------------------------
# Image-first / DeepSeek helpers (config-driven)
# ---------------------------------------------------------------------------


def _should_send_image_first_for_ai_ocr(
    *,
    provider_id: str | None,
    model_name: str | None,
) -> bool:
    """Check if image should be sent before text in user content.

    Uses VendorConfig.send_image_first flag, with model-name fallback for
    DeepSeek models on unknown vendors.
    """
    normalized = (_clean_str(provider_id) or "").lower()
    if normalized and normalized != "auto":
        cfg = get_vendor_config(normalized)
        if cfg.send_image_first:
            return True
    # Fallback: model-name check for DeepSeek on unknown/generic vendors.
    return _is_deepseek_ocr_model(model_name)


# ---------------------------------------------------------------------------
# Provider normalization and inference
# ---------------------------------------------------------------------------


def _normalize_ai_ocr_provider(value: str | None) -> str:
    cleaned = (_clean_str(value) or "").lower()
    provider_id = _AI_OCR_PROVIDER_ALIASES.get(cleaned, cleaned)
    if provider_id not in _VALID_AI_OCR_PROVIDERS:
        return "auto"
    return provider_id


def _infer_ai_ocr_provider_from_base_url(base_url: str | None) -> str:
    cleaned = _clean_str(base_url)
    if not cleaned:
        return "openai"
    try:
        host = (urlparse(cleaned).netloc or "").lower()
    except Exception:
        host = ""
    if not host:
        return "openai"
    if "siliconflow" in host:
        return "siliconflow"
    if "ppio.com" in host or "ppinfra.com" in host:
        return "ppio"
    if "novita.ai" in host:
        return "novita"
    if "deepseek.com" in host:
        return "deepseek"
    if "openai.com" in host:
        return "openai"
    return "openai"


def _is_paddleocr_vl_model_name(model_name: str | None) -> bool:
    cleaned = _clean_str(model_name)
    if not cleaned:
        return False
    return "paddleocr-vl" in cleaned.lower()


def _is_local_or_private_base_url(base_url: str | None) -> bool:
    cleaned = _clean_str(base_url)
    if not cleaned:
        return False
    try:
        host = (urlparse(cleaned).hostname or "").strip().lower()
    except Exception:
        host = ""
    if not host:
        return False
    if host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
        return True
    if host.endswith(".local"):
        return True
    if host.startswith("10.") or host.startswith("192.168."):
        return True
    if host.startswith("172."):
        parts = host.split(".")
        if len(parts) >= 2:
            try:
                second = int(parts[1])
            except Exception:
                second = -1
            if 16 <= second <= 31:
                return True
    return False


def _resolve_ai_ocr_profile(
    *, provider: str | None, base_url: str | None
) -> tuple[str, AiOcrVendorProfile]:
    provider_id = _normalize_ai_ocr_provider(provider)
    if provider_id == "auto":
        provider_id = _infer_ai_ocr_provider_from_base_url(base_url)
    profile = _AI_OCR_VENDOR_PROFILES.get(
        provider_id,
        _AI_OCR_VENDOR_PROFILES["openai"],
    )
    return provider_id, profile


# ---------------------------------------------------------------------------
# Adapter classes — single concrete class with config-driven behaviour
# ---------------------------------------------------------------------------


class AiOcrVendorAdapter(ABC):
    """Vendor adapter for OpenAI-compatible OCR gateways."""

    def __init__(self, *, profile: AiOcrVendorProfile):
        self.profile = profile
        self.config = get_vendor_config(profile.provider_id)

    @property
    def provider_id(self) -> str:
        return self.profile.provider_id

    def resolve_base_url(self, base_url: str | None) -> str | None:
        return _clean_str(base_url) or self.profile.default_base_url

    def resolve_model(self, model: str | None) -> str:
        return _clean_str(model) or self.profile.default_model

    def clamp_max_tokens(self, requested: int, *, kind: str) -> int:
        if kind == "refiner":
            limit = int(self.profile.max_tokens_refiner)
        else:
            limit = int(self.profile.max_tokens_ocr)
        req = max(256, int(requested))
        return max(256, min(req, max(256, limit)))

    def build_user_content(
        self,
        *,
        prompt: str,
        image_data_uri: str,
        image_first: bool = False,
    ) -> list[dict[str, Any]]:
        text_part = {"type": "text", "text": prompt}
        image_part = {"type": "image_url", "image_url": {"url": image_data_uri}}
        if image_first:
            return [image_part, text_part]
        return [text_part, image_part]

    def supports_remote_paddle_doc_parser(self, *, base_url: str | None) -> bool:
        _ = base_url
        return bool(self.profile.supports_remote_paddle_doc_parser)

    def should_use_paddle_doc_parser(
        self,
        *,
        base_url: str | None,
        model_name: str | None,
    ) -> bool:
        if not _is_paddleocr_vl_model_name(model_name):
            return False
        if not _clean_str(base_url):
            return True
        return self.supports_remote_paddle_doc_parser(base_url=base_url)


class OpenAiAiOcrAdapter(AiOcrVendorAdapter):
    """Adapter for generic OpenAI-compatible endpoints.

    Supports local/private URLs that may host PaddleOCR-VL doc_parser protocol.
    """

    def supports_remote_paddle_doc_parser(self, *, base_url: str | None) -> bool:
        # Generic OpenAI-compatible provider can still be a self-hosted vLLM/
        # sglang endpoint that supports PaddleOCRVL doc_parser protocol.
        if _is_local_or_private_base_url(base_url):
            return True
        # Also check VendorConfig flag (for known vendors).
        return bool(self.config.supports_remote_paddle_doc)


def _create_ai_ocr_vendor_adapter(
    *, provider: str | None, base_url: str | None
) -> AiOcrVendorAdapter:
    _, profile = _resolve_ai_ocr_profile(provider=provider, base_url=base_url)
    # Always use OpenAiAiOcrAdapter — it's the only subclass with real logic.
    return OpenAiAiOcrAdapter(profile=profile)
