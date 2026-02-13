"""OCR integration module.

Supports multiple OCR providers:
- AI OCR (OpenAI-compatible vision models)
- Baidu OCR (cloud)
- Tesseract (local)

For scanned PDFs we primarily care about *bbox-accurate* line boxes so we can
overlay editable text on top of a full-page background render.
"""

import os
import logging
import json
import math
import ast
import re
import html
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, List, Dict, Optional, Tuple
from urllib.parse import urlparse, urlunparse
from PIL import Image

logger = logging.getLogger(__name__)

# PaddleX (used by PaddleOCR 3.x / PaddleOCR-VL pipelines) performs a network
# connectivity check to model hosters on import. In some environments this can
# take a *very* long time or even hang, which in turn makes OCR jobs appear
# "stuck" during initialization. Prefer skipping this check by default.
#
# Users can override by explicitly setting this env var before launching.
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

_ACRONYM_ALLOWLIST = {
    "AI",
    "API",
    "LLM",
    "RAG",
    "NLP",
    "OCR",
    "PDF",
    "PPT",
    "PPTX",
    "GPT",
    "CPU",
    "GPU",
    "HTTP",
    "HTTPS",
    "JSON",
    "SQL",
    "UI",
    "UX",
    "SDK",
    "IDE",
    "ETL",
}


_VALID_AI_OCR_PROVIDERS = {
    "auto",
    "openai",
    "siliconflow",
    "ppio",
    "novita",
    "deepseek",
}

_AI_OCR_PROVIDER_ALIASES = {
    "": "auto",
    "auto": "auto",
    "openai": "openai",
    "openai_compatible": "openai",
    "openai-compatible": "openai",
    "siliconflow": "siliconflow",
    "silicon_flow": "siliconflow",
    "sf": "siliconflow",
    "ppio": "ppio",
    "ppinfra": "ppio",
    "novita": "novita",
    "deepseek": "deepseek",
    "deep_seek": "deepseek",
}

_PADDLE_OCR_VL_MODEL_V1 = "PaddlePaddle/PaddleOCR-VL"
_PADDLE_OCR_VL_MODEL_V15 = "PaddlePaddle/PaddleOCR-VL-1.5"
_DEFAULT_PADDLE_OCR_VL_MODEL = _PADDLE_OCR_VL_MODEL_V1
_DEFAULT_PADDLE_DOC_BACKEND = "vllm-server"
_VALID_PADDLE_DOC_BACKENDS = {"vllm-server", "sglang-server"}


@dataclass(frozen=True)
class AiOcrVendorProfile:
    provider_id: str
    default_base_url: str | None
    default_model: str
    max_tokens_ocr: int
    max_tokens_refiner: int


_AI_OCR_VENDOR_PROFILES: dict[str, AiOcrVendorProfile] = {
    "openai": AiOcrVendorProfile(
        provider_id="openai",
        default_base_url=None,
        default_model="gpt-4o-mini",
        max_tokens_ocr=8192,
        max_tokens_refiner=4096,
    ),
    "siliconflow": AiOcrVendorProfile(
        provider_id="siliconflow",
        default_base_url="https://api.siliconflow.cn/v1",
        default_model="Qwen/Qwen2.5-VL-72B-Instruct",
        max_tokens_ocr=4096,
        max_tokens_refiner=2048,
    ),
    "ppio": AiOcrVendorProfile(
        provider_id="ppio",
        default_base_url="https://api.ppio.com/openai",
        default_model="qwen/qwen2.5-vl-72b-instruct",
        max_tokens_ocr=4096,
        max_tokens_refiner=3072,
    ),
    "novita": AiOcrVendorProfile(
        provider_id="novita",
        default_base_url="https://api.novita.ai/openai",
        default_model="qwen/qwen2.5-vl-72b-instruct",
        max_tokens_ocr=4096,
        max_tokens_refiner=3072,
    ),
    "deepseek": AiOcrVendorProfile(
        provider_id="deepseek",
        default_base_url="https://api.deepseek.com/v1",
        default_model="deepseek-ai/DeepSeek-OCR",
        max_tokens_ocr=4096,
        max_tokens_refiner=2048,
    ),
}


def _clean_str(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned if cleaned else None


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    normalized = str(raw).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return bool(default)


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return float(default)
    try:
        value = float(str(raw).strip())
    except Exception:
        return float(default)
    if not math.isfinite(value):
        return float(default)
    return float(value)


def _run_in_daemon_thread_with_timeout(
    func: Any,
    *,
    timeout_s: float,
    label: str,
) -> Any:
    """Run `func()` in a daemon thread with a soft timeout.

    This is used to prevent rare third-party OCR adapters from blocking the
    conversion pipeline indefinitely (for example, network checks inside
    PaddleX/PaddleOCR wrappers). On timeout we raise TimeoutError and keep the
    background thread as daemon so it cannot block process exit.

    Note: this cannot forcibly kill C extensions; it is a best-effort escape
    hatch to keep jobs from staying "processing" forever.
    """

    import threading

    done = threading.Event()
    result: dict[str, Any] = {}
    error: dict[str, BaseException] = {}

    def _runner() -> None:
        try:
            result["value"] = func()
        except BaseException as e:  # noqa: BLE001 - want to propagate keyboard interrupts too
            error["error"] = e
        finally:
            done.set()

    thread = threading.Thread(
        target=_runner,
        name=f"ocr-timeout:{label}",
        daemon=True,
    )
    thread.start()
    timeout_s = max(1.0, float(timeout_s))
    if not done.wait(timeout_s):
        raise TimeoutError(f"{label} timed out after {timeout_s:.0f}s")
    err = error.get("error")
    if err is not None:
        raise err
    return result.get("value")


def _normalize_ai_ocr_model_name(
    model_name: str | None,
    *,
    provider_id: str | None,
) -> str | None:
    cleaned = _clean_str(model_name)
    if not cleaned:
        return cleaned

    lowered = cleaned.lower()

    # SiliconFlow currently exposes OCR models without a Pro/ prefix.
    if lowered.startswith("pro/deepseek-ai/deepseek-ocr"):
        return "deepseek-ai/DeepSeek-OCR"
    if lowered.startswith("pro/paddlepaddle/paddleocr-vl-1.5"):
        return "PaddlePaddle/PaddleOCR-VL-1.5"
    if lowered.startswith("pro/paddlepaddle/paddleocr-vl"):
        return "PaddlePaddle/PaddleOCR-VL"

    if lowered == "deepseek-ai/deepseek-ocr":
        return "deepseek-ai/DeepSeek-OCR"

    return cleaned


def _should_send_image_first_for_ai_ocr(
    *,
    provider_id: str | None,
    model_name: str | None,
) -> bool:
    # DeepSeek-OCR on OpenAI-compatible gateways (including SiliconFlow)
    # is much more stable when image appears before text in user content.
    return _is_deepseek_ocr_model(model_name)


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


class AiOcrVendorAdapter(ABC):
    """Vendor adapter for OpenAI-compatible OCR gateways."""

    def __init__(self, *, profile: AiOcrVendorProfile):
        self.profile = profile

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


class OpenAiAiOcrAdapter(AiOcrVendorAdapter):
    pass


class SiliconFlowAiOcrAdapter(AiOcrVendorAdapter):
    pass


class PpioAiOcrAdapter(AiOcrVendorAdapter):
    pass


class NovitaAiOcrAdapter(AiOcrVendorAdapter):
    pass


class DeepSeekAiOcrAdapter(AiOcrVendorAdapter):
    pass


_AI_OCR_VENDOR_ADAPTERS: dict[str, type[AiOcrVendorAdapter]] = {
    "openai": OpenAiAiOcrAdapter,
    "siliconflow": SiliconFlowAiOcrAdapter,
    "ppio": PpioAiOcrAdapter,
    "novita": NovitaAiOcrAdapter,
    "deepseek": DeepSeekAiOcrAdapter,
}


def _create_ai_ocr_vendor_adapter(
    *, provider: str | None, base_url: str | None
) -> AiOcrVendorAdapter:
    _, profile = _resolve_ai_ocr_profile(provider=provider, base_url=base_url)
    adapter_cls = _AI_OCR_VENDOR_ADAPTERS.get(profile.provider_id, OpenAiAiOcrAdapter)
    return adapter_cls(profile=profile)


def _normalize_tesseract_language(language: str | None) -> str:
    cleaned = _clean_str(language)
    return cleaned or "chi_sim+eng"


def _split_tesseract_languages(language: str | None) -> list[str]:
    normalized = _normalize_tesseract_language(language)
    out: list[str] = []
    for token in normalized.split("+"):
        cleaned = token.strip()
        if cleaned and cleaned not in out:
            out.append(cleaned)
    return out


def probe_local_tesseract(*, language: str | None = None) -> dict[str, Any]:
    """Probe local Tesseract runtime and language-pack availability."""

    requested_language = _normalize_tesseract_language(language)
    requested_languages = _split_tesseract_languages(requested_language)

    python_package_available = False
    binary_available = False
    languages_probe_ok = False
    version: str | None = None
    available_languages: list[str] = []
    missing_languages: list[str] = []
    issues: list[str] = []

    try:
        import pytesseract

        python_package_available = True
    except ImportError:
        issues.append("pytesseract_not_installed")
        return {
            "provider": "tesseract",
            "requested_language": requested_language,
            "requested_languages": requested_languages,
            "python_package_available": False,
            "binary_available": False,
            "version": None,
            "available_languages": [],
            "missing_languages": requested_languages,
            "issues": issues,
            "ready": False,
            "message": "pytesseract package is not installed",
        }

    try:
        version_raw = pytesseract.get_tesseract_version()
        version = str(version_raw).replace("\n", " ").strip() or None
        binary_available = True
    except Exception as e:
        issues.append(f"tesseract_binary_unavailable:{e!s}")

    if binary_available:
        try:
            raw_languages = pytesseract.get_languages(config="") or []
            unique_languages = {
                str(item).strip()
                for item in raw_languages
                if str(item).strip()
            }
            available_languages = sorted(unique_languages)
            languages_probe_ok = True
        except Exception as e:
            issues.append(f"tesseract_languages_probe_failed:{e!s}")

    if languages_probe_ok and requested_languages:
        available_set = {lang.lower() for lang in available_languages}
        missing_languages = [
            lang for lang in requested_languages if lang.lower() not in available_set
        ]
        if missing_languages:
            issues.append("tesseract_missing_languages")

    ready = (
        python_package_available
        and binary_available
        and (not languages_probe_ok or not missing_languages)
    )

    if not python_package_available:
        message = "pytesseract package is not installed"
    elif not binary_available:
        message = "tesseract executable is not available"
    elif missing_languages:
        message = f"Missing tesseract language packs: {', '.join(missing_languages)}"
    elif issues:
        message = "Local Tesseract OCR is available with warnings"
    else:
        message = "Local Tesseract OCR is ready"

    return {
        "provider": "tesseract",
        "requested_language": requested_language,
        "requested_languages": requested_languages,
        "python_package_available": python_package_available,
        "binary_available": binary_available,
        "version": version,
        "available_languages": available_languages,
        "missing_languages": missing_languages,
        "issues": issues,
        "ready": ready,
        "message": message,
    }


def _normalize_paddle_language(language: str | None) -> str:
    cleaned = _clean_str(language)
    if not cleaned:
        return "ch"
    lowered = cleaned.lower()
    alias_map = {
        "zh": "ch",
        "zh-cn": "ch",
        "cn": "ch",
        "chinese": "ch",
        "en-us": "en",
        "english": "en",
    }
    return alias_map.get(lowered, lowered)


def probe_local_paddleocr(*, language: str | None = None) -> dict[str, Any]:
    """Probe local PaddleOCR runtime availability."""

    requested_language = _normalize_paddle_language(language)
    python_package_available = False
    runtime_available = False
    version: str | None = None
    available_languages: list[str] = [
        "ch",
        "en",
        "latin",
        "arabic",
        "cyrillic",
        "devanagari",
    ]
    missing_languages: list[str] = []
    issues: list[str] = []

    try:
        import paddleocr as paddleocr_module

        python_package_available = True
        version = str(getattr(paddleocr_module, "__version__", "") or "").strip() or None
    except ImportError:
        issues.append("paddleocr_not_installed")
        return {
            "provider": "paddle",
            "requested_language": requested_language,
            "requested_languages": [requested_language],
            "python_package_available": False,
            "binary_available": False,
            "version": None,
            "available_languages": available_languages,
            "missing_languages": [requested_language],
            "issues": issues,
            "ready": False,
            "message": "paddleocr package is not installed",
        }

    # For local packaging (e.g. exe), we keep probe lightweight and offline:
    # validate imports only, avoid constructing OCR engine (may trigger model downloads).
    try:
        import paddle
        from paddleocr import PaddleOCR

        _ = paddle.__version__
        _ = PaddleOCR
        runtime_available = True
    except Exception as e:
        issues.append(f"paddleocr_runtime_unavailable:{e!s}")

    if requested_language not in available_languages:
        missing_languages.append(requested_language)
        issues.append("paddleocr_language_maybe_unsupported")

    ready = bool(python_package_available and runtime_available)
    if not python_package_available:
        message = "paddleocr package is not installed"
    elif not runtime_available:
        message = "PaddleOCR runtime is not ready"
    elif missing_languages:
        message = (
            "PaddleOCR runtime is ready, but requested language may be unsupported"
        )
    elif issues:
        message = "PaddleOCR is available with warnings"
    else:
        message = "Local PaddleOCR is ready"

    return {
        "provider": "paddle",
        "requested_language": requested_language,
        "requested_languages": [requested_language],
        "python_package_available": python_package_available,
        "binary_available": runtime_available,
        "version": version,
        "available_languages": available_languages,
        "missing_languages": missing_languages,
        "issues": issues,
        "ready": ready,
        "message": message,
    }


class OcrProvider(ABC):
    """Abstract base class for OCR providers."""

    @abstractmethod
    def ocr_image(self, image_path: str) -> List[Dict]:
        """
        Perform OCR on an image.

        Args:
            image_path: Path to the image file

        Returns:
            List of text elements with format:
            [
              {
                "text": "string",
                "bbox": [x0, y0, x1, y1],  # in image coordinates
                "confidence": 0.95
              }
            ]
        """
        pass


def _extract_items_from_json_payload(value: Any, *, _depth: int = 0) -> list[dict] | None:
    if _depth > 4:
        return None

    if isinstance(value, list):
        rows = [item for item in value if isinstance(item, dict)]
        return rows or None

    if not isinstance(value, dict):
        return None

    if (
        any(
            key in value
            for key in (
                "bbox",
                "box",
                "bounding_box",
                "location",
                "rect",
                "points",
                "polygon",
                "position",
                "coordinates",
                "quad",
                "b",
                "bbox_2d",
            )
        )
        and any(
            key in value
            for key in (
                "text",
                "words",
                "content",
                "transcription",
                "value",
                "label",
                "t",
            )
        )
    ):
        return [value]

    preferred_keys = (
        "items",
        "result",
        "results",
        "data",
        "lines",
        "blocks",
        "text_blocks",
        "ocr",
        "output",
    )
    for key in preferred_keys:
        if key not in value:
            continue
        extracted = _extract_items_from_json_payload(value.get(key), _depth=_depth + 1)
        if extracted:
            return extracted

    for candidate in value.values():
        extracted = _extract_items_from_json_payload(candidate, _depth=_depth + 1)
        if extracted:
            return extracted
    return None


def _extract_partial_json_array_items(text: str, *, max_items: int = 1000) -> list[dict]:
    """Best-effort parse of a possibly truncated JSON array payload."""

    if not text:
        return []

    decoder = json.JSONDecoder()
    n = len(text)
    bracket_positions: list[int] = []
    pos = -1
    while len(bracket_positions) < 16:
        pos = text.find("[", pos + 1)
        if pos < 0:
            break
        bracket_positions.append(pos)

    best: list[dict] = []

    for start in bracket_positions:
        i = start + 1
        out: list[dict] = []

        while i < n and len(out) < max_items:
            while i < n and text[i] in " \t\r\n,":
                i += 1
            if i >= n or text[i] == "]":
                break

            try:
                value, next_i = decoder.raw_decode(text, i)
            except Exception:
                # Most likely truncated tail; keep successfully decoded prefix.
                break

            extracted = _extract_items_from_json_payload(value)
            if extracted:
                for row in extracted:
                    out.append(row)
                    if len(out) >= max_items:
                        break
            elif isinstance(value, dict):
                out.append(value)

            if next_i <= i:
                i += 1
            else:
                i = next_i

        if len(out) > len(best):
            best = out
            if len(best) >= max_items:
                break

    return best


def _parse_relaxed_json(candidate: str) -> Any | None:
    try:
        return json.loads(candidate)
    except Exception:
        pass

    try:
        return ast.literal_eval(candidate)
    except Exception:
        return None


def _extract_balanced_object_snippets(text: str, *, max_items: int = 1000) -> list[dict]:
    if not text:
        return []

    n = len(text)
    i = 0
    depth = 0
    start_idx = -1
    in_string = False
    escaped = False
    out: list[dict] = []

    while i < n and len(out) < max_items:
        ch = text[i]

        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue

        if ch == '"':
            in_string = True
            i += 1
            continue

        if ch == "{":
            if depth == 0:
                start_idx = i
            depth += 1
            i += 1
            continue

        if ch == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start_idx >= 0:
                snippet = text[start_idx : i + 1]
                parsed = _parse_relaxed_json(snippet)
                extracted = _extract_items_from_json_payload(parsed)
                if extracted:
                    for row in extracted:
                        out.append(row)
                        if len(out) >= max_items:
                            break
                elif isinstance(parsed, dict):
                    out.append(parsed)
                start_idx = -1
            i += 1
            continue

        i += 1

    return out[:max_items]


def _extract_partial_json_object_list(text: str, *, max_items: int = 1000) -> list[dict]:
    if not text:
        return []

    items = _extract_partial_json_array_items(text, max_items=max_items)
    if items:
        return items[:max_items]

    decoder = json.JSONDecoder()
    n = len(text)
    i = 0
    out: list[dict] = []

    while i < n and len(out) < max_items:
        start = text.find("{", i)
        if start < 0:
            break

        try:
            parsed_obj, next_i = decoder.raw_decode(text, start)
        except Exception:
            i = start + 1
            continue

        extracted = _extract_items_from_json_payload(parsed_obj)
        if extracted:
            for row in extracted:
                out.append(row)
                if len(out) >= max_items:
                    break
        elif isinstance(parsed_obj, dict):
            out.append(parsed_obj)

        if next_i <= start:
            i = start + 1
        else:
            i = next_i

    if out:
        return out[:max_items]

    relaxed = _extract_balanced_object_snippets(text, max_items=max_items)
    if relaxed:
        return relaxed[:max_items]

    return []


def _extract_message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: list[str] = []
        for part in content:
            if isinstance(part, str):
                cleaned = part.strip()
                if cleaned:
                    chunks.append(cleaned)
                continue
            if not isinstance(part, dict):
                continue
            text_value = part.get("text")
            if not isinstance(text_value, str):
                text_value = part.get("content")
            if isinstance(text_value, str):
                cleaned = text_value.strip()
                if cleaned:
                    chunks.append(cleaned)
        return "\n".join(chunks).strip()
    if content is None:
        return ""
    return str(content)


def _extract_json_list(text: Any) -> list[dict] | None:
    content = _extract_message_text(text)
    if not content:
        return None

    candidates: list[str] = [content]
    stripped = content.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        fenced = "\n".join(lines).strip()
        if fenced:
            candidates.append(fenced)

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            extracted = _extract_items_from_json_payload(parsed)
            if extracted:
                return extracted
        except Exception:
            pass

        start_idx = candidate.find("[")
        end_idx = candidate.rfind("]")
        if start_idx >= 0 and end_idx > start_idx:
            clipped = candidate[start_idx : end_idx + 1]
            try:
                parsed = json.loads(clipped)
                extracted = _extract_items_from_json_payload(parsed)
                if extracted:
                    return extracted
            except Exception:
                pass

        partial = _extract_partial_json_object_list(candidate)
        if partial:
            return partial

    return None


_DEEPSEEK_DET_BOX_PATTERN = re.compile(
    r"<\|det\|>\s*\[\[\s*"
    r"(?P<x0>-?\d+(?:\.\d+)?)\s*,\s*"
    r"(?P<y0>-?\d+(?:\.\d+)?)\s*,\s*"
    r"(?P<x1>-?\d+(?:\.\d+)?)\s*,\s*"
    r"(?P<y1>-?\d+(?:\.\d+)?)\s*"
    r"\]\]\s*<\|/det\|>",
    re.IGNORECASE,
)

_DEEPSEEK_REF_THEN_DET_PATTERN = re.compile(
    r"<\|ref\|>(?P<text>.*?)<\|/ref\|>\s*"
    r"<\|det\|>\s*\[\[\s*"
    r"(?P<x0>-?\d+(?:\.\d+)?)\s*,\s*"
    r"(?P<y0>-?\d+(?:\.\d+)?)\s*,\s*"
    r"(?P<x1>-?\d+(?:\.\d+)?)\s*,\s*"
    r"(?P<y1>-?\d+(?:\.\d+)?)\s*"
    r"\]\]\s*<\|/det\|>",
    re.IGNORECASE | re.DOTALL,
)

_DEEPSEEK_DET_THEN_REF_PATTERN = re.compile(
    r"<\|det\|>\s*\[\[\s*"
    r"(?P<x0>-?\d+(?:\.\d+)?)\s*,\s*"
    r"(?P<y0>-?\d+(?:\.\d+)?)\s*,\s*"
    r"(?P<x1>-?\d+(?:\.\d+)?)\s*,\s*"
    r"(?P<y1>-?\d+(?:\.\d+)?)\s*"
    r"\]\]\s*<\|/det\|>\s*"
    r"<\|ref\|>(?P<text>.*?)<\|/ref\|>",
    re.IGNORECASE | re.DOTALL,
)

_DEEPSEEK_REF_DET_INLINE_TEXT_PATTERN = re.compile(
    r"<\|ref\|>(?P<label>.*?)<\|/ref\|>\s*"
    r"<\|det\|>\s*\[\[\s*"
    r"(?P<x0>-?\d+(?:\.\d+)?)\s*,\s*"
    r"(?P<y0>-?\d+(?:\.\d+)?)\s*,\s*"
    r"(?P<x1>-?\d+(?:\.\d+)?)\s*,\s*"
    r"(?P<y1>-?\d+(?:\.\d+)?)\s*"
    r"\]\]\s*<\|/det\|>\s*"
    r"(?P<text>.*?)(?=(?:<\|ref\|>|$))",
    re.IGNORECASE | re.DOTALL,
)

_DEEPSEEK_TAG_TOKEN_PATTERN = re.compile(
    r"(?P<ref><\|ref\|>(?P<ref_text>.*?)<\|/ref\|>)"
    r"|(?P<det><\|det\|>\s*\[\[\s*"
    r"(?P<x0>-?\d+(?:\.\d+)?)\s*,\s*"
    r"(?P<y0>-?\d+(?:\.\d+)?)\s*,\s*"
    r"(?P<x1>-?\d+(?:\.\d+)?)\s*,\s*"
    r"(?P<y1>-?\d+(?:\.\d+)?)\s*"
    r"\]\]\s*<\|/det\|>)",
    re.IGNORECASE | re.DOTALL,
)

_DEEPSEEK_DET_INLINE_TEXT_PATTERN = re.compile(
    r"<\|det\|>\s*\[\[\s*"
    r"(?P<x0>-?\d+(?:\.\d+)?)\s*,\s*"
    r"(?P<y0>-?\d+(?:\.\d+)?)\s*,\s*"
    r"(?P<x1>-?\d+(?:\.\d+)?)\s*,\s*"
    r"(?P<y1>-?\d+(?:\.\d+)?)\s*"
    r"\]\]\s*<\|/det\|>\s*"
    r"(?P<text>.*?)(?=(?:<\|det\|>|$))",
    re.IGNORECASE | re.DOTALL,
)

_DEEPSEEK_PLAIN_BOX_INLINE_PATTERN = re.compile(
    r"\[\[?\s*"
    r"(?P<x0>-?\d+(?:\.\d+)?)\s*,\s*"
    r"(?P<y0>-?\d+(?:\.\d+)?)\s*,\s*"
    r"(?P<x1>-?\d+(?:\.\d+)?)\s*,\s*"
    r"(?P<y1>-?\d+(?:\.\d+)?)\s*"
    r"\]\]?\s*"
    r"(?P<text>[^\n\r]+)",
    re.IGNORECASE,
)

_DEEPSEEK_GENERIC_REF_LABELS = {
    "text",
    "image",
    "figure",
    "icon",
    "diagram",
    "chart",
    "logo",
    "subtitle",
    "sub_title",
    "equation",
    "formula",
    "table",
    "title",
    "caption",
    "footnote",
    "header",
    "footer",
}

_OCR_PROMPT_ECHO_PREFIXES = (
    "ocr task",
    "image size",
    "return line-level ocr",
    "return line level ocr",
    "preferred format",
    "json array is also accepted",
    "each item must be one visual text line",
    "coordinates are pixel values",
    "stop immediately after json closes",
)


def _is_deepseek_ocr_model(model_name: str | None) -> bool:
    cleaned = (_clean_str(model_name) or "").lower()
    if not cleaned:
        return False
    return "deepseek-ocr" in cleaned or "deepseekocr" in cleaned


def _looks_like_ocr_prompt_echo_text(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(text or "")).strip().lower()
    if not normalized:
        return False

    if normalized in _DEEPSEEK_GENERIC_REF_LABELS:
        return True

    if re.fullmatch(r"region[_\s-]?\d{1,4}", normalized):
        return True

    if normalized.startswith("image size:") and "px" in normalized:
        return True

    if any(normalized.startswith(prefix) for prefix in _OCR_PROMPT_ECHO_PREFIXES):
        return True

    if "return line-level ocr" in normalized and "bbox" in normalized:
        return True

    return False


def _clean_deepseek_ref_text(raw_text: str) -> str:
    text = str(raw_text or "")
    if not text:
        return ""
    # Decode HTML-escaped tags (e.g. &lt;|ref|&gt;).
    for _ in range(2):
        decoded = html.unescape(text)
        if decoded == text:
            break
        text = decoded
    text = re.sub(r"<\|/?[a-zA-Z0-9_]+\|>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_deepseek_tagged_items(text: Any, *, max_items: int = 1500) -> list[dict] | None:
    content = _extract_message_text(text)
    if not content:
        return None

    normalized = content
    for _ in range(2):
        decoded = html.unescape(normalized)
        if decoded == normalized:
            break
        normalized = decoded

    out: list[dict] = []
    seen: set[tuple[str, float, float, float, float]] = set()

    def _append_item(raw_text: str, x0: str, y0: str, x1: str, y1: str) -> None:
        if len(out) >= max_items:
            return
        text_cleaned = _clean_deepseek_ref_text(raw_text)
        if not text_cleaned:
            return
        if _looks_like_ocr_prompt_echo_text(text_cleaned):
            return
        try:
            fx0 = float(x0)
            fy0 = float(y0)
            fx1 = float(x1)
            fy1 = float(y1)
        except Exception:
            return
        key = (text_cleaned, fx0, fy0, fx1, fy1)
        if key in seen:
            return
        seen.add(key)
        out.append(
            {
                "text": text_cleaned,
                "bbox": [fx0, fy0, fx1, fy1],
                "confidence": 0.72,
            }
        )

    has_ref_tags = "<|ref|>" in normalized.lower()
    has_det_tags = "<|det|>" in normalized.lower()

    def _clean_inline_text(chunk: str) -> str:
        # Inline text after a det tag can contain newlines or extra whitespace.
        cleaned = _clean_deepseek_ref_text(chunk)
        if not cleaned:
            return ""
        # Avoid swallowing the next tag if the gateway concatenated outputs.
        cleaned = cleaned.split("<|ref|>", 1)[0].split("<|det|>", 1)[0].strip()
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    # Parse DeepSeek grounding tags via a non-overlapping token stream. Regex
    # patterns like det-then-ref can accidentally pair a <|det|> from one item
    # with the <|ref|> of the *next* item (because tags are adjacent), creating
    # a shifted "two texts per bbox" ladder. Tokenize and pair sequentially
    # instead.
    if has_det_tags and has_ref_tags:
        tokens: list[dict[str, Any]] = []
        for match in _DEEPSEEK_TAG_TOKEN_PATTERN.finditer(normalized):
            if match.group("ref") is not None:
                tokens.append(
                    {
                        "type": "ref",
                        "text": str(match.group("ref_text") or ""),
                        "start": int(match.start()),
                        "end": int(match.end()),
                    }
                )
                continue
            if match.group("det") is not None:
                tokens.append(
                    {
                        "type": "det",
                        "bbox": (
                            str(match.group("x0") or ""),
                            str(match.group("y0") or ""),
                            str(match.group("x1") or ""),
                            str(match.group("y1") or ""),
                        ),
                        "start": int(match.start()),
                        "end": int(match.end()),
                    }
                )

        i = 0
        while (i + 1) < len(tokens) and len(out) < max_items:
            a = tokens[i]
            b = tokens[i + 1]
            a_type = str(a.get("type") or "")
            b_type = str(b.get("type") or "")

            if a_type == "ref" and b_type == "det":
                ref_text_raw = str(a.get("text") or "")
                x0, y0, x1, y1 = a.get("bbox") or ("", "", "", "")
                if isinstance(b.get("bbox"), tuple) and len(b["bbox"]) == 4:
                    x0, y0, x1, y1 = b["bbox"]

                next_start = (
                    int(tokens[i + 2]["start"])
                    if (i + 2) < len(tokens)
                    else len(normalized)
                )
                inline_raw = normalized[int(b.get("end") or 0) : next_start]
                inline_clean = _clean_inline_text(inline_raw)
                ref_clean = _clean_deepseek_ref_text(ref_text_raw)

                chosen_text = ref_text_raw
                if inline_clean and (
                    (not ref_clean)
                    or (ref_clean.lower() in _DEEPSEEK_GENERIC_REF_LABELS)
                    or _looks_like_ocr_prompt_echo_text(ref_clean)
                ):
                    chosen_text = inline_clean

                _append_item(chosen_text, x0, y0, x1, y1)
                i += 2
                continue

            if a_type == "det" and b_type == "ref":
                ref_text_raw = str(b.get("text") or "")
                x0, y0, x1, y1 = a.get("bbox") or ("", "", "", "")
                if isinstance(a.get("bbox"), tuple) and len(a["bbox"]) == 4:
                    x0, y0, x1, y1 = a["bbox"]

                next_start = (
                    int(tokens[i + 2]["start"])
                    if (i + 2) < len(tokens)
                    else len(normalized)
                )
                inline_raw = normalized[int(b.get("end") or 0) : next_start]
                inline_clean = _clean_inline_text(inline_raw)
                ref_clean = _clean_deepseek_ref_text(ref_text_raw)

                chosen_text = ref_text_raw
                if inline_clean and (
                    (not ref_clean)
                    or (ref_clean.lower() in _DEEPSEEK_GENERIC_REF_LABELS)
                    or _looks_like_ocr_prompt_echo_text(ref_clean)
                ):
                    chosen_text = inline_clean

                _append_item(chosen_text, x0, y0, x1, y1)
                i += 2
                continue

            i += 1

    # Backward compatibility: some gateways return tagged grounding but without
    # both ref+det tokens being parsable by the tokenizer above. Fall back to
    # simple ref-then-det pairing only (avoid det-then-ref which can cross-pair).
    #
    # IMPORTANT: only run this when token pairing produced no items; otherwise
    # we risk adding a second text candidate for the same bbox (e.g. generic
    # ref labels vs inline text), which reintroduces duplicated/shifted lines.
    if not out and has_ref_tags:
        for match in _DEEPSEEK_REF_THEN_DET_PATTERN.finditer(normalized):
            _append_item(
                str(match.group("text") or ""),
                str(match.group("x0") or ""),
                str(match.group("y0") or ""),
                str(match.group("x1") or ""),
                str(match.group("y1") or ""),
            )
            if len(out) >= max_items:
                break

    # Det-only inline text formats are used as fallback only when ref tags are
    # absent. This prevents shifted duplicate lines in DeepSeek grounding output.
    if len(out) < max_items and not has_ref_tags:
        for match in _DEEPSEEK_DET_INLINE_TEXT_PATTERN.finditer(normalized):
            _append_item(
                str(match.group("text") or ""),
                str(match.group("x0") or ""),
                str(match.group("y0") or ""),
                str(match.group("x1") or ""),
                str(match.group("y1") or ""),
            )
            if len(out) >= max_items:
                break

    if len(out) < max_items and not has_ref_tags:
        for match in _DEEPSEEK_PLAIN_BOX_INLINE_PATTERN.finditer(normalized):
            _append_item(
                str(match.group("text") or ""),
                str(match.group("x0") or ""),
                str(match.group("y0") or ""),
                str(match.group("x1") or ""),
                str(match.group("y1") or ""),
            )
            if len(out) >= max_items:
                break

    if out:
        return out

    # Fallback: when only <|det|> boxes are present (no usable text), still return
    # coarse placeholders so caller can decide whether to keep/fallback.
    det_only: list[dict] = []
    for idx, match in enumerate(_DEEPSEEK_DET_BOX_PATTERN.finditer(normalized), start=1):
        if len(det_only) >= max_items:
            break
        try:
            fx0 = float(match.group("x0"))
            fy0 = float(match.group("y0"))
            fx1 = float(match.group("x1"))
            fy1 = float(match.group("y1"))
        except Exception:
            continue
        det_only.append(
            {
                "text": f"region_{idx}",
                "bbox": [fx0, fy0, fx1, fy1],
                "confidence": 0.45,
            }
        )

    return det_only or None


def _looks_like_structural_gibberish(text: str) -> bool:
    """Detect malformed gateway outputs made mostly of JSON delimiters.

    Some OpenAI-compatible OCR gateways occasionally return long streams like
    `}}]}]}...` with almost no textual content. These payloads are not valid
    OCR results and retrying with smaller limits rarely helps.
    """

    content = str(text or "").strip()
    if len(content) < 64:
        return False

    compact = "".join(ch for ch in content if not ch.isspace())
    if len(compact) < 64:
        return False

    structural = sum(1 for ch in compact if ch in "{}[],:")
    alnum = sum(1 for ch in compact if ch.isalnum())
    structural_ratio = float(structural) / float(max(1, len(compact)))
    alnum_ratio = float(alnum) / float(max(1, len(compact)))

    if structural_ratio >= 0.88 and alnum_ratio <= 0.06:
        return True

    if "}}]}" in compact or "}]}]" in compact:
        repeat_hits = compact.count("}}]}") + compact.count("}]}]")
        if repeat_hits >= max(6, len(compact) // 80):
            return True

    return False

def _coerce_bbox_xyxy(raw_bbox: Any) -> list[float] | None:
    if raw_bbox is None:
        return None

    # Numpy arrays (and some other tensor-like objects) show up in OCR SDK
    # outputs (e.g. PaddleX / PaddleOCR 3.x). Convert them to Python lists so
    # downstream logic can treat them uniformly.
    if hasattr(raw_bbox, "tolist"):
        try:
            raw_bbox = raw_bbox.tolist()
        except Exception:
            pass

    if isinstance(raw_bbox, dict):
        if all(k in raw_bbox for k in ("left", "top", "width", "height")):
            try:
                x0 = float(raw_bbox.get("left") or 0)
                y0 = float(raw_bbox.get("top") or 0)
                width = float(raw_bbox.get("width") or 0)
                height = float(raw_bbox.get("height") or 0)
                return [x0, y0, x0 + width, y0 + height]
            except Exception:
                return None
        for keys in (("x0", "y0", "x1", "y1"), ("xmin", "ymin", "xmax", "ymax")):
            if not all(k in raw_bbox for k in keys):
                continue
            try:
                x0 = float(raw_bbox.get(keys[0]))
                y0 = float(raw_bbox.get(keys[1]))
                x1 = float(raw_bbox.get(keys[2]))
                y1 = float(raw_bbox.get(keys[3]))
                return [x0, y0, x1, y1]
            except Exception:
                return None
        return None

    if isinstance(raw_bbox, tuple):
        raw_bbox = list(raw_bbox)
    if not isinstance(raw_bbox, list):
        return None

    if len(raw_bbox) == 4 and all(isinstance(v, (int, float)) for v in raw_bbox):
        return [
            float(raw_bbox[0]),
            float(raw_bbox[1]),
            float(raw_bbox[2]),
            float(raw_bbox[3]),
        ]

    if raw_bbox and all(isinstance(v, dict) for v in raw_bbox):
        xs: list[float] = []
        ys: list[float] = []
        for point in raw_bbox:
            try:
                x = point.get("x")
                y = point.get("y")
                if x is None:
                    x = point.get("left")
                if y is None:
                    y = point.get("top")
                xs.append(float(x))
                ys.append(float(y))
            except Exception:
                return None
        if xs and ys:
            return [min(xs), min(ys), max(xs), max(ys)]

    if raw_bbox and all(isinstance(v, list) and len(v) >= 2 for v in raw_bbox):
        xs: list[float] = []
        ys: list[float] = []
        for point in raw_bbox:
            try:
                xs.append(float(point[0]))
                ys.append(float(point[1]))
            except Exception:
                return None
        if xs and ys:
            return [min(xs), min(ys), max(xs), max(ys)]

    if len(raw_bbox) >= 8 and len(raw_bbox) % 2 == 0 and all(
        isinstance(v, (int, float)) for v in raw_bbox
    ):
        xs = [float(raw_bbox[i]) for i in range(0, len(raw_bbox), 2)]
        ys = [float(raw_bbox[i]) for i in range(1, len(raw_bbox), 2)]
        if xs and ys:
            return [min(xs), min(ys), max(xs), max(ys)]

    return None


def _is_paddleocr_vl_model(model_name: str | None) -> bool:
    cleaned = _clean_str(model_name)
    if not cleaned:
        return False
    return "paddleocr-vl" in cleaned.lower()


def _normalize_paddle_doc_backend(value: str | None) -> str:
    cleaned = (_clean_str(value) or "").lower()
    if cleaned in _VALID_PADDLE_DOC_BACKENDS:
        return cleaned
    return _DEFAULT_PADDLE_DOC_BACKEND


def _normalize_paddle_doc_server_url(
    value: str | None,
    *,
    provider_id: str | None,
) -> str | None:
    cleaned = _clean_str(value)
    if not cleaned:
        return None

    trimmed = cleaned.rstrip("/")
    try:
        parsed = urlparse(trimmed)
    except Exception:
        return trimmed

    if not parsed.scheme or not parsed.netloc:
        return trimmed

    host = (parsed.netloc or "").lower()
    normalized_provider = (_clean_str(provider_id) or "").lower()
    should_force_v1_path = normalized_provider == "siliconflow" or "siliconflow" in host

    normalized_path = (parsed.path or "").rstrip("/")
    if should_force_v1_path and not normalized_path:
        normalized_path = "/v1"

    normalized = urlunparse(parsed._replace(path=normalized_path or parsed.path)).rstrip("/")
    return normalized


def _resolve_paddle_doc_model_and_pipeline(
    *,
    model: str | None,
    provider_id: str | None,
    allow_model_downgrade: bool | None = None,
) -> tuple[str, str | None]:
    effective_model = _clean_str(model) or _DEFAULT_PADDLE_OCR_VL_MODEL
    pipeline_version = _clean_str(os.getenv("OCR_PADDLE_VL_PIPELINE_VERSION"))

    _ = allow_model_downgrade
    _ = provider_id
    model_lower = effective_model.lower()

    if model_lower == _PADDLE_OCR_VL_MODEL_V1.lower() and not pipeline_version:
        pipeline_version = "v1"

    return effective_model, pipeline_version


def _is_probably_model_unsupported_error(error: Exception) -> bool:
    text = str(error or "").lower()
    signals = (
        "invalid model",
        "model not found",
        "unsupported model",
        "does not support",
        "not support",
        "unknown model",
        "model not exist",
        "404",
    )
    return any(sig in text for sig in signals)


_LOC_TOKEN_PATTERN = re.compile(r"<\|LOC_\d+\|>")


def _strip_loc_tokens(text: str) -> str:
    """Remove PaddleOCR-VL location markers from plain text fields."""

    cleaned = _LOC_TOKEN_PATTERN.sub("", str(text or ""))
    return cleaned.strip()


class AiOcrClient(OcrProvider):
    """AI OCR using OpenAI-compatible vision models."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None = None,
        model: str | None = None,
        provider: str | None = None,
    ):
        import openai

        if not api_key:
            raise ValueError("AI OCR api_key is required")

        self.api_key = str(api_key).strip()
        self._paddle_doc_parser: Any | None = None
        self._paddle_doc_parser_disabled: bool = False
        self._paddle_doc_effective_model: str | None = None
        self._paddle_doc_pipeline_version: str | None = None
        self._paddle_doc_server_url: str | None = None
        self._paddle_doc_backend: str | None = None

        self.vendor_adapter = _create_ai_ocr_vendor_adapter(
            provider=provider,
            base_url=base_url,
        )
        resolved_base_url = self.vendor_adapter.resolve_base_url(base_url)
        client_kwargs: dict[str, str] = {"api_key": api_key}
        if resolved_base_url:
            client_kwargs["base_url"] = resolved_base_url
        self.client = openai.OpenAI(**client_kwargs)
        resolved_model = self.vendor_adapter.resolve_model(model)
        self.model = _normalize_ai_ocr_model_name(
            resolved_model,
            provider_id=self.vendor_adapter.provider_id,
        ) or resolved_model
        self.provider_id = self.vendor_adapter.provider_id
        self.base_url = resolved_base_url
        self.allow_model_downgrade: bool = _env_flag(
            "OCR_PADDLE_ALLOW_MODEL_DOWNGRADE",
            default=False,
        )

        if self._should_use_paddle_doc_parser():
            if not _clean_str(self.base_url):
                raise ValueError(
                    "PaddleOCR-VL requires base_url (for example https://api.siliconflow.cn/v1)"
                )
            try:
                import paddleocr as _  # noqa: F401
            except Exception as e:
                raise ValueError(
                    "PaddleOCR-VL requires `paddleocr` package. Install with: pip install paddleocr"
                ) from e

    def _should_use_paddle_doc_parser(self) -> bool:
        if self._paddle_doc_parser_disabled:
            return False
        if not _is_paddleocr_vl_model(self.model):
            return False
        # Allow deployments to disable the doc_parser adapter when it causes
        # timeouts or resource issues. When disabled, we fall back to the normal
        # prompt-based AI OCR path (still using the same model).
        if not _env_flag("OCR_PADDLE_VL_USE_DOCPARSER", default=True):
            return False
        return True

    def _get_paddle_doc_parser(self) -> Any:
        if self._paddle_doc_parser is not None:
            return self._paddle_doc_parser

        try:
            from paddleocr import PaddleOCRVL
        except Exception as e:
            raise RuntimeError(
                "PaddleOCR-VL dedicated adapter requires `paddleocr` package"
            ) from e

        raw_server_url = (
            _clean_str(os.getenv("OCR_PADDLE_VL_REC_SERVER_URL"))
            or self.base_url
            or self.vendor_adapter.resolve_base_url(None)
        )
        server_url = _normalize_paddle_doc_server_url(
            raw_server_url,
            provider_id=self.provider_id,
        )
        if not server_url:
            raise RuntimeError("PaddleOCR-VL dedicated adapter requires base_url")

        backend = _normalize_paddle_doc_backend(os.getenv("OCR_PADDLE_VL_REC_BACKEND"))
        effective_model, pipeline_version = _resolve_paddle_doc_model_and_pipeline(
            model=self.model,
            provider_id=self.provider_id,
            allow_model_downgrade=self.allow_model_downgrade,
        )

        kwargs: dict[str, Any] = {
            "vl_rec_backend": backend,
            "vl_rec_server_url": server_url,
            "vl_rec_api_key": self.api_key,
            "vl_rec_api_model_name": effective_model,
        }
        if pipeline_version:
            kwargs["pipeline_version"] = pipeline_version

        init_timeout_s = _env_float("OCR_PADDLE_VL_DOCPARSER_INIT_TIMEOUT_S", 90.0)
        try:
            self._paddle_doc_parser = _run_in_daemon_thread_with_timeout(
                lambda: PaddleOCRVL(**kwargs),
                timeout_s=init_timeout_s,
                label="paddleocr-vl:init",
            )
        except TimeoutError as e:
            # Disable doc_parser for this client so callers can fall back to the
            # prompt-based OCR path instead of hanging forever.
            self._paddle_doc_parser_disabled = True
            raise RuntimeError(str(e)) from e
        except Exception:
            # Disable doc_parser for this client; prompt-based OCR may still work.
            self._paddle_doc_parser_disabled = True
            raise
        self._paddle_doc_effective_model = effective_model
        self._paddle_doc_pipeline_version = pipeline_version
        self._paddle_doc_server_url = server_url
        self._paddle_doc_backend = backend
        logger.info(
            "Initialized PaddleOCR-VL doc_parser adapter (provider=%s, requested_model=%s, effective_model=%s, pipeline_version=%s, base_url=%s, backend=%s)",
            self.provider_id,
            self.model,
            effective_model,
            pipeline_version or "<default>",
            server_url,
            backend,
        )
        return self._paddle_doc_parser

    def _ocr_image_with_paddle_doc_parser(self, image_path: str) -> List[Dict]:
        def _predict_once() -> Any:
            parser_local = self._get_paddle_doc_parser()
            try:
                return parser_local.predict(input=image_path)
            except TypeError:
                return parser_local.predict(image_path)

        try:
            predict_timeout_s = _env_float(
                "OCR_PADDLE_VL_DOCPARSER_PREDICT_TIMEOUT_S", 180.0
            )
            output = _run_in_daemon_thread_with_timeout(
                _predict_once,
                timeout_s=predict_timeout_s,
                label="paddleocr-vl:predict",
            )
        except Exception as first_error:
            wants_v15 = (
                str(self.model or "").strip().lower()
                == _PADDLE_OCR_VL_MODEL_V15.lower()
            )
            can_downgrade = bool(self.allow_model_downgrade)
            if isinstance(first_error, TimeoutError):
                self._paddle_doc_parser_disabled = True
            if (
                wants_v15
                and can_downgrade
                and _is_probably_model_unsupported_error(first_error)
            ):
                logger.warning(
                    "PaddleOCR-VL-1.5 request failed and downgrade is allowed; retrying with %s",
                    _PADDLE_OCR_VL_MODEL_V1,
                )
                self._paddle_doc_parser = None
                self._paddle_doc_effective_model = _PADDLE_OCR_VL_MODEL_V1
                self._paddle_doc_pipeline_version = "v1"
                self._paddle_doc_server_url = None
                self._paddle_doc_backend = None
                original_model = self.model
                try:
                    self.model = _PADDLE_OCR_VL_MODEL_V1
                    output = _run_in_daemon_thread_with_timeout(
                        _predict_once,
                        timeout_s=predict_timeout_s,
                        label="paddleocr-vl:predict",
                    )
                except Exception:
                    self.model = original_model
                    raise first_error
            else:
                if wants_v15 and (not can_downgrade) and _is_probably_model_unsupported_error(first_error):
                    raise RuntimeError(
                        "PaddleOCR-VL-1.5 is not available on current endpoint and strict mode forbids downgrade; "
                        "switch to PaddlePaddle/PaddleOCR-VL or disable strict mode explicitly."
                    ) from first_error
                raise

        if isinstance(output, list):
            results_iter = output
        elif isinstance(output, tuple):
            results_iter = list(output)
        else:
            try:
                results_iter = list(output)
            except Exception:
                results_iter = [output]

        raw_elements: list[dict] = []

        def _extract_parsing_blocks(result_obj: Any) -> list[Any]:
            payload_candidates: list[Any] = []

            json_payload = getattr(result_obj, "json", None)
            if callable(json_payload):
                try:
                    json_payload = json_payload()
                except Exception:
                    json_payload = None
            if json_payload is not None:
                payload_candidates.append(json_payload)

            to_dict_payload = getattr(result_obj, "to_dict", None)
            if callable(to_dict_payload):
                try:
                    payload_candidates.append(to_dict_payload())
                except Exception:
                    pass

            payload_candidates.append(result_obj)

            for payload in payload_candidates:
                if not isinstance(payload, dict):
                    continue
                root = payload.get("res") if isinstance(payload.get("res"), dict) else payload
                blocks = root.get("parsing_res_list")
                if isinstance(blocks, list):
                    return blocks
            return []

        def _extract_block_fields(block: Any) -> tuple[str, Any, Any]:
            if isinstance(block, dict):
                text = _strip_loc_tokens(
                    block.get("block_content")
                    or block.get("content")
                    or block.get("text")
                    or ""
                )
                bbox_raw: Any = None
                for key in ("block_bbox", "bbox", "box", "b"):
                    if key in block and block[key] is not None:
                        bbox_raw = block[key]
                        break

                confidence_raw: Any = None
                for key in ("confidence", "score", "prob"):
                    if key in block and block[key] is not None:
                        confidence_raw = block[key]
                        break
                return text, bbox_raw, confidence_raw

            text = _strip_loc_tokens(
                getattr(block, "block_content", None)
                or getattr(block, "content", None)
                or getattr(block, "text", None)
                or ""
            )
            bbox_raw: Any = None
            for attr in ("block_bbox", "bbox", "box", "b"):
                value = getattr(block, attr, None)
                if value is not None:
                    bbox_raw = value
                    break

            confidence_raw: Any = None
            for attr in ("confidence", "score", "prob"):
                value = getattr(block, attr, None)
                if value is not None:
                    confidence_raw = value
                    break
            return text, bbox_raw, confidence_raw

        first_result_type: str | None = None
        first_block_type: str | None = None

        for result in results_iter:
            if first_result_type is None:
                first_result_type = type(result).__name__

            blocks = _extract_parsing_blocks(result)
            for block in blocks:
                if first_block_type is None:
                    first_block_type = type(block).__name__

                text, bbox_raw, confidence_raw = _extract_block_fields(block)
                bbox = _coerce_bbox_xyxy(bbox_raw)
                if not text or not bbox:
                    continue

                try:
                    confidence = (
                        float(confidence_raw)
                        if confidence_raw is not None
                        else 0.9
                    )
                except Exception:
                    confidence = 0.9
                if confidence > 1.0:
                    confidence = confidence / 100.0 if confidence <= 100.0 else 1.0
                confidence = max(0.0, min(confidence, 1.0))

                raw_elements.append(
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

        if not raw_elements:
            logger.warning(
                "PaddleOCR-VL doc_parser produced no usable text blocks "
                "(provider=%s, requested_model=%s, effective_model=%s, pipeline_version=%s, result_type=%s, block_type=%s)",
                self.provider_id,
                self.model,
                self._paddle_doc_effective_model or self.model,
                self._paddle_doc_pipeline_version or "<default>",
                first_result_type,
                first_block_type,
            )
            raise RuntimeError(
                "PaddleOCR-VL doc_parser returned no valid text blocks in parsing_res_list"
            )

        logger.info(
            "PaddleOCR-VL doc_parser parsed %s blocks",
            len(raw_elements),
        )
        return raw_elements

    def _score_bbox_transform(
        self,
        *,
        image: Image.Image,
        gray: Image.Image,
        items: list[dict],
        base: float | tuple[float, float] | None,
        max_items: int = 60,
    ) -> tuple[float, dict]:
        """Score candidate bbox coordinate systems.

        Some vision models return bounding boxes in a *normalized* coordinate
        grid (often around 0..1000/1024) regardless of the actual image size.
        We evaluate a few plausible transforms and pick the best one.
        """

        width, height = image.size
        if width <= 0 or height <= 0 or not items:
            return (float("-inf"), {"reason": "empty"})

        if base is None:
            sx = 1.0
            sy = 1.0
            base_name = "identity"
        elif isinstance(base, tuple):
            try:
                base_x = float(base[0])
                base_y = float(base[1])
            except Exception:
                return (float("-inf"), {"reason": "invalid_base_xy"})
            if base_x <= 0 or base_y <= 0:
                return (float("-inf"), {"reason": "invalid_base_xy"})
            sx = float(width) / float(base_x)
            sy = float(height) / float(base_y)
            base_name = f"{int(round(base_x))}x{int(round(base_y))}"
        else:
            b = float(base)
            if b <= 0:
                return (float("-inf"), {"reason": "invalid_base"})
            sx = float(width) / b
            sy = float(height) / b
            base_name = str(int(b)) if b.is_integer() else str(b)

        # Take a stable subset (first N) to keep scoring fast on dense pages.
        subset = items[: max(1, min(len(items), int(max_items)))]

        x0s: list[float] = []
        x1s: list[float] = []
        y0s: list[float] = []
        y1s: list[float] = []
        stds: list[float] = []
        out_of_bounds = 0
        valid = 0

        for it in subset:
            bbox = it.get("bbox")
            if not isinstance(bbox, list) or len(bbox) != 4:
                continue
            try:
                x0, y0, x1, y1 = (
                    float(bbox[0]) * sx,
                    float(bbox[1]) * sy,
                    float(bbox[2]) * sx,
                    float(bbox[3]) * sy,
                )
            except Exception:
                continue
            if math.isnan(x0) or math.isnan(y0) or math.isnan(x1) or math.isnan(y1):
                continue
            x0, x1 = (min(x0, x1), max(x0, x1))
            y0, y1 = (min(y0, y1), max(y0, y1))
            if x1 <= x0 or y1 <= y0:
                continue

            # Count OOB based on unclamped coords.
            if x0 < 0 or y0 < 0 or x1 > width or y1 > height:
                out_of_bounds += 1

            # Clamp for sampling.
            x0c = max(0, min(width - 1, int(round(x0))))
            y0c = max(0, min(height - 1, int(round(y0))))
            x1c = max(0, min(width, int(round(x1))))
            y1c = max(0, min(height, int(round(y1))))
            if x1c <= x0c or y1c <= y0c:
                continue

            x0s.append(float(x0c))
            x1s.append(float(x1c))
            y0s.append(float(y0c))
            y1s.append(float(y1c))
            valid += 1

            # Pixel-variance proxy: real text regions tend to have higher
            # local variance than blank/background regions.
            crop = gray.crop((x0c, y0c, x1c, y1c))
            if crop.width <= 0 or crop.height <= 0:
                continue
            target_w = max(8, min(64, crop.width // 8))
            target_h = max(8, min(64, crop.height // 8))
            small = crop.resize((target_w, target_h))
            pixels = list(small.getdata())
            if not pixels:
                continue
            mean = sum(pixels) / len(pixels)
            var = sum((p - mean) ** 2 for p in pixels) / len(pixels)
            stds.append(float(var**0.5))

        if valid <= 0:
            return (float("-inf"), {"base": base_name, "reason": "no_valid_boxes"})

        def _percentile(sorted_vals: list[float], p: float) -> float:
            if not sorted_vals:
                return 0.0
            p = max(0.0, min(1.0, float(p)))
            idx = int(round((len(sorted_vals) - 1) * p))
            return sorted_vals[idx]

        x0s_s = sorted(x0s)
        x1s_s = sorted(x1s)
        y0s_s = sorted(y0s)
        y1s_s = sorted(y1s)

        x_span = (_percentile(x1s_s, 0.95) - _percentile(x0s_s, 0.05)) / float(width)
        y_span = (_percentile(y1s_s, 0.95) - _percentile(y0s_s, 0.05)) / float(height)
        coverage_score = max(0.0, min(1.0, x_span)) + max(0.0, min(1.0, y_span))  # 0..2

        median_std = sorted(stds)[len(stds) // 2] if stds else 0.0
        out_rate = float(out_of_bounds) / float(valid)

        # Weighted score: prioritize good coverage (boxes span the page) then
        # variance, penalize out-of-bounds.
        score = (1.6 * coverage_score) + (median_std / 32.0) - (2.0 * out_rate)
        details = {
            "base": base_name,
            "sx": sx,
            "sy": sy,
            "valid": valid,
            "median_std": median_std,
            "coverage_x": x_span,
            "coverage_y": y_span,
            "out_rate": out_rate,
        }
        return (float(score), details)

    def _normalize_items_to_pixels(
        self,
        items: list[dict],
        *,
        image: Image.Image,
    ) -> tuple[list[dict], dict]:
        """Return (items_px, debug) after auto-normalizing bbox coords to pixels."""

        width, height = image.size
        if width <= 0 or height <= 0 or not items:
            return (items, {"chosen": "none", "reason": "empty"})

        gray = image.convert("L")

        # Evaluate common coordinate grids + identity. Some gateways also return
        # bbox coordinates in the *resized* model-input pixel space (e.g. long
        # side normalized to 1024 while keeping aspect ratio). In that case the
        # X/Y bases differ; we add a few aspect-preserving candidates.
        uniform_candidates: list[float | None] = [
            None,
            1.0,
            100.0,
            1000.0,
            1024.0,
            2048.0,
            4096.0,
        ]

        def _resize_dims_for_target_side(
            target_side: float, *, mode: str
        ) -> tuple[float, float] | None:
            try:
                target = float(target_side)
            except Exception:
                return None
            if target <= 0:
                return None
            if mode == "short":
                denom = float(min(width, height))
            else:
                denom = float(max(width, height))
            if denom <= 0:
                return None
            scale = float(target) / denom
            if scale <= 0:
                return None
            bw = max(1.0, float(round(float(width) * scale)))
            bh = max(1.0, float(round(float(height) * scale)))
            if bw <= 0 or bh <= 0:
                return None
            return (bw, bh)

        seen: set[str] = set()
        candidates: list[float | tuple[float, float] | None] = []

        def _add_candidate(value: float | tuple[float, float] | None) -> None:
            if value is None:
                key = "identity"
            elif isinstance(value, tuple):
                key = f"xy:{int(round(float(value[0])))}x{int(round(float(value[1])))}"
            else:
                key = f"u:{float(value):.3f}"
            if key in seen:
                return
            seen.add(key)
            candidates.append(value)

        for base in uniform_candidates:
            _add_candidate(base)

        for side in (1000.0, 1024.0, 1536.0, 2048.0):
            cand = _resize_dims_for_target_side(side, mode="long")
            if cand is not None:
                _add_candidate(cand)

        for side in (1000.0, 1024.0):
            cand = _resize_dims_for_target_side(side, mode="short")
            if cand is not None:
                _add_candidate(cand)

        scored: list[tuple[float, float | tuple[float, float] | None, dict]] = []
        for base in candidates:
            score, details = self._score_bbox_transform(
                image=image, gray=gray, items=items, base=base
            )
            scored.append((score, base, details))

        scored.sort(key=lambda t: t[0], reverse=True)
        best_score, best_base, best_details = scored[0]

        # Apply best transform.
        if best_base is None:
            sx = 1.0
            sy = 1.0
        elif isinstance(best_base, tuple):
            bx, by = best_base
            bx = float(bx)
            by = float(by)
            sx = float(width) / float(max(1.0, bx))
            sy = float(height) / float(max(1.0, by))
        else:
            sx = float(width) / float(best_base)
            sy = float(height) / float(best_base)

        out: list[dict] = []
        for it in items:
            bbox = it.get("bbox")
            if not isinstance(bbox, list) or len(bbox) != 4:
                continue
            try:
                x0, y0, x1, y1 = (
                    float(bbox[0]) * sx,
                    float(bbox[1]) * sy,
                    float(bbox[2]) * sx,
                    float(bbox[3]) * sy,
                )
            except Exception:
                continue
            if math.isnan(x0) or math.isnan(y0) or math.isnan(x1) or math.isnan(y1):
                continue
            x0, x1 = (min(x0, x1), max(x0, x1))
            y0, y1 = (min(y0, y1), max(y0, y1))
            if x1 <= x0 or y1 <= y0:
                continue
            # Clamp to image bounds.
            x0 = max(0.0, min(x0, float(width - 1)))
            y0 = max(0.0, min(y0, float(height - 1)))
            x1 = max(0.0, min(x1, float(width)))
            y1 = max(0.0, min(y1, float(height)))
            if x1 <= x0 or y1 <= y0:
                continue
            new_it = dict(it)
            new_it["bbox"] = [x0, y0, x1, y1]
            out.append(new_it)

        debug = {
            "chosen_base": best_details.get("base"),
            "chosen_score": best_score,
            "chosen_details": best_details,
            "candidates": [d for _, _, d in scored[:3]],
        }
        return (out, debug)

    def ocr_image(self, image_path: str) -> List[Dict]:
        image = Image.open(image_path).convert("RGB")
        width, height = image.size
        if width <= 0 or height <= 0:
            return []

        if self._should_use_paddle_doc_parser():
            try:
                return self._ocr_image_with_paddle_doc_parser(image_path)
            except Exception as e:
                # The dedicated PaddleOCR-VL doc_parser adapter is helpful when
                # available, but it can hang or timeout in some deployments
                # (network checks, gateway instability, etc.). Fall back to the
                # normal prompt-based OCR path instead of failing the whole job.
                logger.warning(
                    "PaddleOCR-VL doc_parser failed; falling back to prompt-based OCR: %s",
                    e,
                )
                self._paddle_doc_parser_disabled = True
                self._paddle_doc_parser = None

        import base64
        import io

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        data_uri = f"data:image/png;base64,{b64}"

        is_deepseek_model = _is_deepseek_ocr_model(self.model)

        def _make_prompt(*, item_limit: int) -> str:
            # Keep prompt compact to reduce instruction tokens and steer models
            # (especially OpenAI-compatible gateways) toward short structured output.
            if is_deepseek_model:
                # DeepSeek OCR grounding tends to behave best with the special
                # <|grounding|> prefix, but we still provide strict formatting
                # and item-limit guidance so dense slides do not get truncated
                # or duplicated.
                item_limit = max(20, int(item_limit))
                return (
                    "<|grounding|> Extract all visible text lines.\n"
                    f"Image size: {width}x{height} px.\n"
                    "Output ONLY grounding tags, one line per text line:\n"
                    "<|ref|>TEXT<|/ref|><|det|>[[x0,y0,x1,y1]]<|/det|>\n"
                    "bbox must be pixel coords in THIS image (origin top-left).\n"
                    f"Return at most {item_limit} lines. Keep reading order. "
                    "Do not repeat the same line/bbox."
                )
            return (
                f"OCR task. Return ONLY minified JSON array, no markdown. "
                f"Image size: {width}x{height} px. "
                "Each item must be one visual text line with tight bbox. "
                "Do not output duplicate lines/boxes; skip pure punctuation/noise. "
                "Preferred item schema: {\"t\":\"text\",\"b\":[x0,y0,x1,y1],\"c\":0.0-1.0}. "
                "Also accepted: {\"text\":...,\"bbox\":...}. "
                "Coordinates are pixel values, origin top-left. "
                f"Keep output <= {int(item_limit)} items. "
                "If dense page, merge words into line-level entries. "
                "Stop immediately after JSON closes."
            )

        last_error: Exception | None = None
        items: list[dict] | None = None
        attempt_limits = [60, 40, 24, 16, 10]
        if is_deepseek_model:
            # DeepSeek grounding tags are fairly compact; allow more lines on
            # dense scanned pages while still retrying with smaller limits when
            # output truncates.
            attempt_limits = [180, 120, 90, 60, 40]

        for attempt, item_limit in enumerate(attempt_limits, start=1):
            try:
                prompt = _make_prompt(item_limit=item_limit)
                requested_tokens = 8192
                if is_deepseek_model:
                    # Each grounding item is short, but dense pages can easily
                    # exceed 60 lines. Allow enough output budget to avoid
                    # truncation while staying below common gateway limits.
                    requested_tokens = int(320 + int(item_limit) * 22)
                    requested_tokens = max(900, requested_tokens)
                    requested_tokens = min(3500, requested_tokens)
                max_tokens_ocr = self.vendor_adapter.clamp_max_tokens(requested_tokens, kind="ocr")
                system_content = "Return JSON array only, no markdown."
                if is_deepseek_model:
                    system_content = (
                        "You are an OCR engine. Output only DeepSeek grounding tags "
                        "(<|ref|>...<|/ref|><|det|>[[x0,y0,x1,y1]]<|/det|>) or JSON array with bbox."
                    )

                user_content = self.vendor_adapter.build_user_content(
                    prompt=prompt,
                    image_data_uri=data_uri,
                    image_first=_should_send_image_first_for_ai_ocr(
                        provider_id=self.provider_id,
                        model_name=self.model,
                    ),
                )
                messages: list[dict[str, Any]] = [
                    {
                        "role": "system",
                        "content": system_content,
                    },
                    {
                        "role": "user",
                        "content": user_content,
                    },
                ]
                if is_deepseek_model:
                    messages = [
                        {
                            "role": "user",
                            "content": user_content,
                        }
                    ]

                completion = self.client.with_options(timeout=90).chat.completions.create(
                    model=self.model,
                    temperature=0,
                    max_tokens=max_tokens_ocr,
                    messages=messages,
                )

                content_obj = (
                    completion.choices[0].message.content
                    if getattr(completion, "choices", None)
                    else ""
                )
                content = _extract_message_text(content_obj)
                finish_reason = None
                try:
                    finish_reason = completion.choices[0].finish_reason
                except Exception:
                    finish_reason = None

                if is_deepseek_model and _looks_like_structural_gibberish(content):
                    preview = (content or "")[:220].replace("\n", " ").strip()
                    logger.warning(
                        "AI OCR returned structural gibberish (attempt=%s, chars=%s, preview=%r)",
                        attempt,
                        len(content or ""),
                        preview,
                    )
                    raise RuntimeError("AI OCR returned structural gibberish")

                items = _extract_json_list(content)
                if not items and (is_deepseek_model or "<|det|>" in (content or "")):
                    items = _extract_deepseek_tagged_items(content)
                if items:
                    logger.info(
                        "AI OCR parsed %s items on attempt %s (limit=%s, finish_reason=%s)",
                        len(items),
                        attempt,
                        item_limit,
                        finish_reason,
                    )
                    break

                if finish_reason == "length":
                    partial_items = _extract_partial_json_object_list(content)
                    if not partial_items and (is_deepseek_model or "<|det|>" in (content or "")):
                        tagged_partial = _extract_deepseek_tagged_items(content)
                        partial_items = tagged_partial or []
                    if partial_items:
                        logger.warning(
                            "AI OCR output truncated (attempt=%s, limit=%s); recovered %s partial items.",
                            attempt,
                            item_limit,
                            len(partial_items),
                        )
                        items = partial_items
                        break
                    preview = (content or "")[:360].replace("\n", " ").strip()
                    logger.warning(
                        "AI OCR truncated with no recoverable JSON (attempt=%s, limit=%s, chars=%s, preview=%r)",
                        attempt,
                        item_limit,
                        len(content or ""),
                        preview,
                    )
                    raise RuntimeError(
                        f"AI OCR output truncated (finish_reason=length, chars={len(content)})"
                    )

                preview = (content or "")[:360].replace("\n", " ").strip()
                logger.warning(
                    "AI OCR returned no parseable items (attempt=%s, finish_reason=%s, chars=%s, preview=%r)",
                    attempt,
                    finish_reason,
                    len(content or ""),
                    preview,
                )
                raise RuntimeError("AI OCR returned no items")
            except Exception as e:
                last_error = e
                logger.warning("AI OCR attempt %s failed: %s", attempt, e)
                continue

        if not items:
            raise RuntimeError("AI OCR returned no items") from last_error

        raw_elements: List[Dict] = []
        for item in items:
            if not isinstance(item, dict):
                continue

            text = str(
                item.get("text")
                or item.get("t")
                or item.get("words")
                or item.get("content")
                or item.get("transcription")
                or item.get("value")
                or item.get("label")
                or ""
            ).strip()

            if _looks_like_ocr_prompt_echo_text(text):
                continue

            bbox_raw = item.get("bbox")
            if bbox_raw is None:
                for bbox_key in (
                    "b",
                    "box",
                    "bounding_box",
                    "location",
                    "rect",
                    "points",
                    "polygon",
                    "position",
                    "coordinates",
                    "quad",
                    "bbox_2d",
                ):
                    if bbox_key in item:
                        bbox_raw = item.get(bbox_key)
                        break
            bbox = _coerce_bbox_xyxy(bbox_raw)
            if not text or not bbox:
                continue

            try:
                x0, y0, x1, y1 = (
                    float(bbox[0]),
                    float(bbox[1]),
                    float(bbox[2]),
                    float(bbox[3]),
                )
            except Exception:
                continue
            if not all(math.isfinite(v) for v in (x0, y0, x1, y1)):
                continue

            confidence_raw = item.get("confidence")
            if confidence_raw is None:
                confidence_raw = item.get("c")
            if confidence_raw is None:
                confidence_raw = item.get("score")
            if confidence_raw is None:
                confidence_raw = item.get("prob")

            try:
                confidence = float(confidence_raw) if confidence_raw is not None else 0.7
            except Exception:
                confidence = 0.7
            if confidence > 1.0:
                confidence = confidence / 100.0 if confidence <= 100.0 else 1.0
            confidence = max(0.0, min(confidence, 1.0))

            raw_elements.append(
                {
                    "text": text,
                    "bbox": [x0, y0, x1, y1],
                    "confidence": confidence,
                }
            )

        if not raw_elements:
            raise RuntimeError("AI OCR returned empty elements")

        # Normalize bbox coordinates into the real image pixel space.
        elements, debug = self._normalize_items_to_pixels(raw_elements, image=image)
        if not elements:
            raise RuntimeError("AI OCR bbox normalization produced no valid elements")

        # Lightweight sanity check: if bboxes cover only a tiny fraction of the
        # page and we have many items, treat it as a coordinate mismatch so
        # OcrManager can fall back to a bbox-accurate engine.
        try:
            if len(elements) >= 12:
                xs0 = sorted(float(it["bbox"][0]) for it in elements)
                xs1 = sorted(float(it["bbox"][2]) for it in elements)
                ys0 = sorted(float(it["bbox"][1]) for it in elements)
                ys1 = sorted(float(it["bbox"][3]) for it in elements)
                p05 = max(0, int(round((len(xs0) - 1) * 0.05)))
                p95 = max(0, int(round((len(xs1) - 1) * 0.95)))
                span_x = (xs1[p95] - xs0[p05]) / float(width)
                span_y = (ys1[p95] - ys0[p05]) / float(height)
                coverage_threshold = 0.24 if is_deepseek_model else 0.35
                if span_x < coverage_threshold or span_y < coverage_threshold:
                    raise RuntimeError(
                        f"AI OCR bbox coverage too small after normalization: span_x={span_x:.3f}, span_y={span_y:.3f}"
                    )
        except Exception as e:
            logger.warning("AI OCR bbox sanity check failed: %s debug=%s", e, debug)
            raise

        logger.info("AI OCR bbox normalization: %s", debug.get("chosen_details"))
        # Attach lightweight provenance for downstream dedupe/QA. Do NOT include
        # API keys or full URLs.
        try:
            for el in elements:
                if not isinstance(el, dict):
                    continue
                el.setdefault("provider", self.provider_id)
                el.setdefault("model", self.model)
        except Exception:
            pass
        return elements


def _is_multiline_candidate_for_linebreak_assist(
    *,
    text: str,
    bbox: tuple[float, float, float, float] | Any,
    image_width: int,
    image_height: int,
    median_line_height: float,
) -> bool:
    """Decide whether an OCR bbox likely contains multiple visual lines.

    This is a pre-filter before calling a vision model to split lines. Keeping
    it as a standalone helper makes behavior testable and easier to tune.
    """

    bbox_n = _normalize_bbox_px(bbox) if not isinstance(bbox, tuple) else bbox
    if bbox_n is None:
        return False

    x0, y0, x1, y1 = bbox_n
    w = max(1.0, float(x1 - x0))
    h = max(1.0, float(y1 - y0))
    width = max(1, int(image_width))
    height = max(1, int(image_height))
    median_h = max(0.0, float(median_line_height))
    if median_h <= 0.0:
        median_h = max(10.0, 0.02 * float(height))

    raw_text = str(text or "")
    compact = re.sub(r"\s+", "", raw_text)
    if "\n" in raw_text and len(compact) >= 3:
        return True
    if len(compact) < 8:
        return False

    # Wide banner-like titles are often single-line even with larger bboxes;
    # avoid over-splitting these into pseudo-lines.
    wide_banner_like = (
        w >= 0.28 * float(width)
        and (h / max(1.0, w)) <= 0.11
        and len(compact) <= 42
        and h <= max(3.6 * median_h, 0.16 * float(height))
    )
    if wide_banner_like:
        return False

    # PaddleOCR-VL doc parser (and some AI OCR providers) frequently returns
    # paragraph-like bboxes that are only ~1.5x the median line height. A
    # stricter 1.8x gate misses these, leaving the renderer to guess line
    # breaks and causing visible wrap drift in PPT.
    if h >= max(1.80 * median_h, 0.055 * float(height)):
        return True
    if h >= max(1.45 * median_h, 0.045 * float(height)) and (
        len(compact) >= 16 or w >= 0.30 * float(width)
    ):
        return True
    return False


class AiOcrTextRefiner:
    """Refine OCR line texts using an OpenAI-compatible vision model.

    This does NOT change bounding boxes. It is designed to run after a bbox-
    accurate OCR engine (e.g. Tesseract) and improve transcription quality.
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None = None,
        model: str | None = None,
        provider: str | None = None,
    ):
        import openai

        if not api_key:
            raise ValueError("AI refiner api_key is required")

        self.vendor_adapter = _create_ai_ocr_vendor_adapter(
            provider=provider,
            base_url=base_url,
        )
        resolved_base_url = self.vendor_adapter.resolve_base_url(base_url)
        client_kwargs: dict[str, str] = {"api_key": api_key}
        if resolved_base_url:
            client_kwargs["base_url"] = resolved_base_url
        self.client = openai.OpenAI(**client_kwargs)
        resolved_model = self.vendor_adapter.resolve_model(model)
        self.model = _normalize_ai_ocr_model_name(
            resolved_model,
            provider_id=self.vendor_adapter.provider_id,
        ) or resolved_model
        self.provider_id = self.vendor_adapter.provider_id
        self.base_url = resolved_base_url

    def refine_items(
        self,
        image_path: str,
        *,
        items: list[dict],
        max_items_per_call: int = 80,
    ) -> list[dict]:
        """Return a new items list with refined `text` fields.

        Args:
            image_path: Path to the page image.
            items: List of dicts with keys: text (str) and bbox ([x0,y0,x1,y1] in px).
            max_items_per_call: Chunk size to reduce truncation risk.
        """

        image = Image.open(image_path).convert("RGB")
        width, height = image.size
        if width <= 0 or height <= 0 or not items:
            return items

        import base64
        import io

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        data_uri = f"data:image/png;base64,{b64}"

        def _chunks(seq: list[dict], n: int) -> list[list[dict]]:
            n = max(1, int(n))
            return [seq[i : i + n] for i in range(0, len(seq), n)]

        refined: list[dict] = [dict(it) for it in items]

        # Build a stable indexing so the model can return corrections by id.
        indexed: list[dict] = []
        for i, it in enumerate(items):
            text = str(it.get("text") or "")
            bbox = it.get("bbox")
            if not isinstance(bbox, list) or len(bbox) != 4:
                continue
            indexed.append({"i": i, "bbox": bbox, "text": text})

        if not indexed:
            return refined

        for part in _chunks(indexed, max_items_per_call):
            prompt = (
                "You are an OCR post-processor. You will be given a page image and a JSON array of OCR line boxes. "
                "Each item has {i, bbox:[x0,y0,x1,y1], text}. The bbox is in PIXELS in the page image "
                f"(origin top-left, width={width}, height={height}).\n\n"
                "Task: For each item, READ the text inside its bbox on the image and output ONLY a JSON array of "
                "objects {i:int, text:string}. Keep the same i values. Do NOT include bbox in the output. "
                "Do NOT add new items.\n\n"
                "Rules:\n"
                "- The provided `text` is noisy; treat it as a hint only.\n"
                "- Preserve the original language(s) and punctuation (Chinese/English/numbers/parentheses).\n"
                "- Do NOT hallucinate words that are not visible in the bbox.\n"
                "- If the bbox is unreadable or blank, return the original text for that i.\n\n"
                "Input items:\n"
                + json.dumps(part, ensure_ascii=True)
                + "\n\nOutput ONLY the JSON array."
            )

            completion = self.client.with_options(timeout=60).chat.completions.create(
                model=self.model,
                temperature=0,
                max_tokens=self.vendor_adapter.clamp_max_tokens(4096, kind="refiner"),
                messages=[
                    {
                        "role": "system",
                        "content": "Return JSON array only, no markdown.",
                    },
                    {
                        "role": "user",
                        "content": self.vendor_adapter.build_user_content(
                            prompt=prompt,
                            image_data_uri=data_uri,
                            image_first=_should_send_image_first_for_ai_ocr(
                                provider_id=self.provider_id,
                                model_name=self.model,
                            ),
                        ),
                    },
                ],
            )

            content = (
                completion.choices[0].message.content
                if getattr(completion, "choices", None)
                else ""
            )
            out = _extract_json_list(content or "")
            if not out:
                continue

            for item in out:
                if not isinstance(item, dict):
                    continue
                idx = item.get("i")
                if not isinstance(idx, int) or idx < 0 or idx >= len(refined):
                    continue
                text = item.get("text")
                if isinstance(text, str):
                    # Never overwrite a bbox's OCR text with empty output from the
                    # refiner. Some vision models return "" when they can't read
                    # a region; keeping the original Tesseract/Baidu text preserves
                    # coverage (the user can later fix/delete a few bad boxes).
                    new_text = text.strip()
                    if new_text:
                        refined[idx]["text"] = new_text

        return refined

    def assist_line_breaks(
        self,
        image_path: str,
        *,
        items: list[dict],
        max_items_per_call: int = 36,
        max_lines_per_item: int = 8,
        allow_heuristic_fallback: bool = False,
    ) -> list[dict]:
        """Split coarse OCR boxes into line-level boxes with visual guidance.

        The method keeps horizontal geometry and only splits bbox vertically.
        It is designed for cases where OCR returns paragraph/block boxes and
        downstream PPT rendering needs line-level text boxes.
        """

        image = Image.open(image_path).convert("RGB")
        width, height = image.size
        if width <= 0 or height <= 0 or not items:
            return items

        import base64
        import io

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        data_uri = f"data:image/png;base64,{b64}"

        normalized_rows: list[dict[str, Any]] = []
        line_heights: list[float] = []
        for i, it in enumerate(items):
            if not isinstance(it, dict):
                continue
            text = str(it.get("text") or "").strip()
            bbox_n = _normalize_bbox_px(it.get("bbox"))
            if not text or bbox_n is None:
                continue
            x0, y0, x1, y1 = bbox_n
            h = max(1.0, float(y1 - y0))
            line_heights.append(h)
            normalized_rows.append(
                {
                    "i": i,
                    "text": text,
                    "bbox": [float(x0), float(y0), float(x1), float(y1)],
                    "bbox_n": bbox_n,
                    "original": it,
                }
            )

        if not normalized_rows:
            return items

        def _median(values: list[float]) -> float:
            if not values:
                return 0.0
            ordered = sorted(float(v) for v in values)
            n = len(ordered)
            m = n // 2
            if n % 2 == 1:
                return ordered[m]
            return (ordered[m - 1] + ordered[m]) / 2.0

        median_h = _median(line_heights)
        if median_h <= 0:
            median_h = max(10.0, 0.02 * float(height))

        candidates: list[dict[str, Any]] = []
        for row in normalized_rows:
            if _is_multiline_candidate_for_linebreak_assist(
                text=str(row.get("text") or ""),
                bbox=row.get("bbox_n"),
                image_width=width,
                image_height=height,
                median_line_height=median_h,
            ):
                candidates.append(
                    {
                        "i": row["i"],
                        "bbox": row["bbox"],
                        "text": row["text"],
                    }
                )

        if not candidates:
            return items

        def _chunks(seq: list[dict], n: int) -> list[list[dict]]:
            n = max(1, int(n))
            return [seq[i : i + n] for i in range(0, len(seq), n)]

        split_map: dict[int, list[str]] = {}
        for part in _chunks(candidates, max_items_per_call):
            prompt = (
                "You are an OCR layout post-processor. You will get a page image and a JSON array "
                "of OCR text boxes that may contain multiple visual lines. Each item has {i, bbox, text}. "
                "bbox is in PIXELS in the image "
                f"(origin top-left, width={width}, height={height}).\n\n"
                "Task: For each item, read only the text inside its bbox and split it into visual lines "
                "(top to bottom). Return ONLY a JSON array of objects {i:int, lines:string[]}.\n\n"
                "Rules:\n"
                "- Keep original i values; do NOT add new items.\n"
                "- Keep language and punctuation as seen in the image.\n"
                "- If a box is single-line or uncertain, return lines with exactly one entry.\n"
                "- Do NOT include markdown or explanations.\n\n"
                "Input items:\n"
                + json.dumps(part, ensure_ascii=True)
                + "\n\nOutput ONLY the JSON array."
            )

            completion = self.client.with_options(timeout=60).chat.completions.create(
                model=self.model,
                temperature=0,
                max_tokens=self.vendor_adapter.clamp_max_tokens(3072, kind="refiner"),
                messages=[
                    {
                        "role": "system",
                        "content": "Return JSON array only, no markdown.",
                    },
                    {
                        "role": "user",
                        "content": self.vendor_adapter.build_user_content(
                            prompt=prompt,
                            image_data_uri=data_uri,
                            image_first=_should_send_image_first_for_ai_ocr(
                                provider_id=self.provider_id,
                                model_name=self.model,
                            ),
                        ),
                    },
                ],
            )

            content = (
                completion.choices[0].message.content
                if getattr(completion, "choices", None)
                else ""
            )
            out = _extract_json_list(content or "")
            if not out:
                continue

            for item in out:
                if not isinstance(item, dict):
                    continue
                idx = item.get("i")
                if not isinstance(idx, int):
                    continue
                raw_lines = item.get("lines")
                lines: list[str] = []
                if isinstance(raw_lines, str):
                    lines = [seg.strip() for seg in raw_lines.splitlines() if seg.strip()]
                elif isinstance(raw_lines, list):
                    for seg in raw_lines:
                        if isinstance(seg, str):
                            cleaned = seg.strip()
                            if cleaned:
                                lines.append(cleaned)
                if lines:
                    split_map[idx] = lines[: max(1, int(max_lines_per_item))]

        row_map: dict[int, dict[str, Any]] = {
            int(row["i"]): row for row in normalized_rows if isinstance(row.get("i"), int)
        }
        candidate_idx_set: set[int] = {
            int(row["i"]) for row in candidates if isinstance(row.get("i"), int)
        }

        def _compact_text(text: str) -> str:
            return re.sub(r"\s+", "", text or "")

        def _split_is_plausible(
            original_text: str,
            lines: list[str],
            *,
            row: dict[str, Any] | None,
        ) -> bool:
            if len(lines) <= 1:
                return False
            compact_orig = _compact_text(original_text)
            compact_joined = _compact_text("".join(lines))
            if not compact_joined:
                return False
            if not compact_orig:
                return True

            contains_relation = (
                compact_orig in compact_joined or compact_joined in compact_orig
            )

            if contains_relation:
                diff = abs(len(compact_orig) - len(compact_joined))
                # For short/medium lines, don't accept splits that drop a visible
                # prefix/suffix chunk. This prevents title-like lines from losing
                # the first few glyphs after model line-splitting.
                if len(compact_orig) <= 44 and diff >= 3:
                    return False

            ratio = min(len(compact_orig), len(compact_joined)) / max(
                1, len(compact_orig), len(compact_joined)
            )
            min_ratio = 0.45
            # Moderate guard for short/medium boxes: strict enough to prevent
            # obvious truncation, but not so strict that valid line splits fail.
            if len(compact_orig) <= 64:
                min_ratio = 0.56
            if len(compact_orig) <= 36:
                min_ratio = 0.62
            if ratio < min_ratio:
                return False

            # Guard against unstable split outputs: for wide single-line titles,
            # splitting into a very short first segment + long remainder usually
            # hurts alignment and may later trigger noise filtering.
            if len(lines) == 2:
                lens = [len(_compact_text(seg)) for seg in lines]
                short_len = min(lens) if lens else 0
                long_len = max(lens) if lens else 0
                if short_len > 0 and long_len > 0:
                    imbalance = float(short_len) / float(long_len)
                    bbox_n = row.get("bbox_n") if isinstance(row, dict) else None
                    if isinstance(bbox_n, tuple) and len(bbox_n) == 4:
                        x0, y0, x1, y1 = bbox_n
                        w = max(1.0, float(x1 - x0))
                        h = max(1.0, float(y1 - y0))
                        wide_banner_like = (
                            w >= 0.25 * float(width)
                            and (h / max(1.0, w)) <= 0.12
                        )
                        if wide_banner_like and short_len <= 5 and imbalance < 0.30:
                            return False

            return True

        def _split_bbox_by_ink_projection(
            row: dict[str, Any],
            *,
            n_lines: int,
        ) -> list[tuple[float, float]] | None:
            """Estimate vertical line ranges from image pixels inside a bbox.

            Returns a list of (y0, y1) in absolute image pixels for each line.
            """

            try:
                import numpy as np
            except Exception:
                return None

            bbox_n = row.get("bbox_n")
            if not isinstance(bbox_n, tuple) or len(bbox_n) != 4:
                return None
            if n_lines <= 1:
                return None

            x0, y0, x1, y1 = bbox_n
            xi0 = max(0, min(width - 1, int(math.floor(float(x0)))))
            yi0 = max(0, min(height - 1, int(math.floor(float(y0)))))
            xi1 = max(0, min(width, int(math.ceil(float(x1)))))
            yi1 = max(0, min(height, int(math.ceil(float(y1)))))
            if xi1 - xi0 < 4 or yi1 - yi0 < max(6, n_lines * 3):
                return None

            try:
                gray = image.crop((xi0, yi0, xi1, yi1)).convert("L")
                arr = np.asarray(gray, dtype=np.float32)
            except Exception:
                return None

            if arr.ndim != 2 or arr.size <= 0:
                return None

            h_px, w_px = arr.shape
            if h_px < max(6, n_lines * 3):
                return None

            p95 = float(np.percentile(arr, 95.0))
            p10 = float(np.percentile(arr, 10.0))
            contrast = max(1.0, p95 - p10)
            if contrast < 8.0:
                return None

            # Convert to rough "ink" intensity (0..1), then row profile.
            ink = np.clip((p95 - arr) / contrast, 0.0, 1.0)
            ink_mask = (ink >= 0.16).astype(np.float32)
            row_profile = ink_mask.mean(axis=1)
            if float(np.sum(row_profile)) <= max(0.02 * h_px, 1.0):
                return None

            k = max(1, int(round(h_px / 54.0)))
            if k > 1:
                kernel = np.ones((k,), dtype=np.float32) / float(k)
                smooth = np.convolve(row_profile, kernel, mode="same")
            else:
                smooth = row_profile

            minima: list[int] = []
            low_th = float(np.percentile(smooth, 45.0))
            for pos in range(1, h_px - 1):
                v = float(smooth[pos])
                if v > low_th:
                    continue
                if v <= float(smooth[pos - 1]) and v <= float(smooth[pos + 1]):
                    minima.append(pos)

            target_cuts = max(1, int(n_lines) - 1)
            cuts: list[int] = []
            used: set[int] = set()
            max_dist = max(3, int(round(0.22 * h_px)))
            for k_idx in range(1, target_cuts + 1):
                target = int(round(float(k_idx) * float(h_px) / float(n_lines)))
                cands = [m for m in minima if m not in used and abs(m - target) <= max_dist]
                if not cands:
                    continue
                chosen = min(cands, key=lambda m: abs(m - target))
                cuts.append(chosen)
                used.add(chosen)

            # Fallback: quantiles by cumulative row ink.
            if len(cuts) < target_cuts:
                prof = smooth + 1e-6
                cum = np.cumsum(prof)
                total = float(cum[-1])
                if total > 0:
                    for k_idx in range(1, target_cuts + 1):
                        target_mass = total * (float(k_idx) / float(n_lines))
                        pos = int(np.searchsorted(cum, target_mass))
                        pos = max(1, min(h_px - 2, pos))
                        cuts.append(pos)

            if len(cuts) < target_cuts:
                return None

            cuts = sorted(set(cuts))
            if len(cuts) > target_cuts:
                # Keep cuts nearest to uniform targets for stability.
                targets = [
                    int(round(float(k_idx) * float(h_px) / float(n_lines)))
                    for k_idx in range(1, target_cuts + 1)
                ]
                selected: list[int] = []
                remaining = list(cuts)
                for t in targets:
                    if not remaining:
                        break
                    best = min(remaining, key=lambda c: abs(c - t))
                    selected.append(best)
                    remaining.remove(best)
                cuts = sorted(selected)

            bounds = [0] + cuts + [h_px]
            if len(bounds) != n_lines + 1:
                return None

            ranges: list[tuple[float, float]] = []
            prev_y = float(y0)
            for idx in range(n_lines):
                by0 = int(bounds[idx])
                by1 = int(bounds[idx + 1])
                if by1 - by0 < 1:
                    continue
                ly0 = float(y0) + float(by0)
                ly1 = float(y0) + float(by1)
                ly0 = max(float(y0), min(float(y1) - 1.0, ly0))
                ly1 = max(ly0 + 1.0, min(float(y1), ly1))
                if ly0 < prev_y:
                    ly0 = prev_y
                if ly1 <= ly0:
                    continue
                ranges.append((ly0, ly1))
                prev_y = ly1

            if len(ranges) != n_lines:
                return None

            heights = [max(0.0, ly1 - ly0) for (ly0, ly1) in ranges]
            if not heights:
                return None
            avg_h = float(sum(heights)) / float(max(1, len(heights)))
            min_h = min(heights)
            max_h = max(heights)
            # Guard against unstable projection cuts (over-compressed lines).
            # If line heights are too imbalanced, fallback to equal split.
            if avg_h > 0:
                if min_h < max(1.0, 0.55 * avg_h):
                    return None
                if max_h > (1.80 * avg_h):
                    return None

            return ranges

        def _estimate_target_lines(row: dict[str, Any]) -> int:
            bbox_n = row.get("bbox_n")
            if not isinstance(bbox_n, tuple) or len(bbox_n) != 4:
                return 1
            _, y0, _, y1 = bbox_n
            h = max(1.0, float(y1 - y0))
            baseline = max(8.0, float(median_h))
            est = int(round(h / baseline))
            if _is_multiline_candidate(row):
                est = max(est, 2)
            est = max(1, min(est, max(2, int(max_lines_per_item))))
            return est

        def _split_into_sentences(text: str) -> list[str]:
            cleaned = " ".join(str(text or "").split()).strip()
            if not cleaned:
                return []
            out: list[str] = []
            buf = ""
            for ch in cleaned:
                buf += ch
                if ch in "。！？!?；;":
                    seg = buf.strip()
                    if seg:
                        out.append(seg)
                    buf = ""
            if buf.strip():
                out.append(buf.strip())
            return out

        def _fallback_split_lines(original_text: str, target_lines: int) -> list[str]:
            target_lines = max(1, int(target_lines))
            normalized = " ".join(str(original_text or "").split()).strip()
            if not normalized:
                return []
            if target_lines <= 1:
                return [normalized]

            sentences = _split_into_sentences(normalized)
            if not sentences:
                sentences = [normalized]

            if len(sentences) < target_lines:
                finer: list[str] = []
                for seg in sentences:
                    parts = [p.strip() for p in re.split(r"(?<=[，,：:])", seg) if p.strip()]
                    if len(parts) > 1:
                        finer.extend(parts)
                    else:
                        finer.append(seg)
                if finer:
                    sentences = finer

            if len(sentences) <= 1:
                compact_len = len(_compact_text(normalized))
                if compact_len < target_lines * 4:
                    return [normalized]
                per_line = max(4, int(round(compact_len / float(target_lines))))
                out: list[str] = []
                buf = ""
                buf_len = 0
                for ch in normalized:
                    buf += ch
                    if ch.isspace():
                        continue
                    buf_len += 1
                    if buf_len >= per_line and len(out) < (target_lines - 1):
                        seg = buf.strip()
                        if seg:
                            out.append(seg)
                        buf = ""
                        buf_len = 0
                if buf.strip():
                    out.append(buf.strip())
                return [seg for seg in out if seg]

            desired = max(2, min(target_lines, max(2, int(max_lines_per_item))))
            total = sum(max(1, len(_compact_text(seg))) for seg in sentences)
            target_chars = max(6.0, float(total) / float(desired))

            out: list[str] = []
            cur_parts: list[str] = []
            cur_chars = 0.0
            for idx, seg in enumerate(sentences):
                seg_chars = float(max(1, len(_compact_text(seg))))
                cur_parts.append(seg)
                cur_chars += seg_chars

                slots_left = max(1, desired - len(out))
                segments_left = len(sentences) - idx - 1
                should_cut = len(out) < (desired - 1) and (
                    cur_chars >= target_chars or segments_left <= (slots_left - 1)
                )
                if should_cut:
                    merged = "".join(cur_parts).strip()
                    if merged:
                        out.append(merged)
                    cur_parts = []
                    cur_chars = 0.0

            if cur_parts:
                merged = "".join(cur_parts).strip()
                if merged:
                    out.append(merged)

            return [seg for seg in out if seg]

        def _has_strong_two_line_split_cue(text: str) -> bool:
            normalized = " ".join(str(text or "").split()).strip()
            if not normalized:
                return False

            stripped = normalized.lstrip()
            if stripped.startswith(("-", "•", "·", "●", "▪", "▶", "◆", "■", "*")):
                return True

            parts = re.split(r"[：:]", normalized, maxsplit=1)
            if len(parts) == 2:
                head = _compact_text(parts[0])
                tail = _compact_text(parts[1])
                if 2 <= len(head) <= 26 and len(tail) >= 2:
                    return True

            if re.match(r"^\s*[（(]?[0-9一二三四五六七八九十]+[）).、]", normalized):
                return True

            return False

        def _is_structured_multiline_text(text: str) -> bool:
            raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
            if "\n" not in raw:
                return False

            lines = [ln.strip() for ln in raw.split("\n") if ln.strip()]
            if len(lines) < 3:
                return False

            compact_lens = [len(_compact_text(ln)) for ln in lines]
            if not compact_lens:
                return False

            marker_lines = 0
            for ln in lines:
                if any(tok in ln for tok in ("【", "】", "[", "]", "#", "##")):
                    marker_lines += 1

            avg_len = float(sum(compact_lens)) / float(max(1, len(compact_lens)))
            max_len = max(compact_lens)

            # Template/spec-like multiline blocks are often already close to
            # intended line structure; avoid AI split from over-fragmenting.
            if marker_lines >= max(2, int(round(0.35 * len(lines)))) and avg_len <= 34.0:
                return True
            if marker_lines >= 2 and len(lines) >= 5 and max_len <= 48:
                return True

            return False

        def _allow_split_for_row(
            *,
            original_text: str,
            lines: list[str],
            row: dict[str, Any],
        ) -> bool:
            if len(lines) <= 1:
                return False
            if "\n" in str(original_text or ""):
                return True
            if len(lines) != 2:
                return True

            estimated = _estimate_target_lines(row)
            if estimated >= 3:
                return True

            compact_len = len(_compact_text(original_text))
            if compact_len <= 34:
                return True

            # Paragraph-like long text with only two inferred lines is usually
            # more stable when kept in one bbox and rendered with adaptive wrap.
            return _has_strong_two_line_split_cue(original_text)

        split_count = 0
        fallback_split_count = 0
        out_items: list[dict] = []
        for idx, original in enumerate(items):
            if not isinstance(original, dict):
                continue
            lines = split_map.get(idx)
            row = row_map.get(idx)
            if row is None:
                out_items.append(dict(original))
                continue

            original_text = str(row.get("text") or "")

            if idx in candidate_idx_set and _is_structured_multiline_text(original_text):
                out_items.append(dict(original))
                continue

            clean_lines = [str(seg).strip() for seg in (lines or []) if str(seg).strip()]

            if (
                allow_heuristic_fallback
                and (not clean_lines or len(clean_lines) <= 1)
                and idx in candidate_idx_set
            ):
                estimated = _estimate_target_lines(row)
                if estimated >= 2:
                    fallback_lines = _fallback_split_lines(original_text, estimated)
                    if len(fallback_lines) >= 2:
                        clean_lines = fallback_lines
                        fallback_split_count += 1

            if not _allow_split_for_row(
                original_text=original_text,
                lines=clean_lines,
                row=row,
            ):
                out_items.append(dict(original))
                continue

            if not _split_is_plausible(original_text, clean_lines, row=row):
                out_items.append(dict(original))
                continue

            bbox_n = row.get("bbox_n")
            if not isinstance(bbox_n, tuple) or len(bbox_n) != 4:
                out_items.append(dict(original))
                continue

            x0, y0, x1, y1 = bbox_n
            n = max(1, len(clean_lines))
            total_h = max(1.0, float(y1 - y0))

            ranges = _split_bbox_by_ink_projection(row, n_lines=n)

            for line_idx, text_line in enumerate(clean_lines):
                if ranges is not None and line_idx < len(ranges):
                    ly0, ly1 = ranges[line_idx]
                else:
                    ly0 = y0 + total_h * float(line_idx) / float(n)
                    ly1 = y0 + total_h * float(line_idx + 1) / float(n)
                if ly1 - ly0 < 1.0:
                    continue

                new_item = dict(original)
                new_item["text"] = text_line
                new_item["bbox"] = [float(x0), float(ly0), float(x1), float(ly1)]
                out_items.append(new_item)

            split_count += 1

        if split_count > 0:
            logger.info(
                "AI OCR line-break assist applied: split_boxes=%s/%s (fallback=%s)",
                split_count,
                len(items),
                fallback_split_count,
            )

        return out_items


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
        self.secret_key = (secret_key or os.getenv("BAIDU_OCR_SECRET_KEY") or "").strip()

        if not all([self.app_id, self.api_key, self.secret_key]):
            raise ValueError(
                "Baidu OCR credentials not found. "
                "Set BAIDU_OCR_APP_ID, BAIDU_OCR_API_KEY, BAIDU_OCR_SECRET_KEY"
            )

        try:
            from aip import AipOcr

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
                call_candidates.append(("basicGeneral", getattr(self.client, "basicGeneral")))

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
                    if area_ratio >= 0.16:
                        continue
                    if width_ratio >= 0.85 and height_ratio >= 0.08 and len(compact) <= 24:
                        continue
                    if area_ratio >= 0.06 and len(compact) <= 6 and height_ratio >= 0.06:
                        continue

                elements.append(
                    {
                        "text": text,
                        "bbox": [x0, y0, x0 + w, y0 + h],
                        # Baidu does not reliably return confidences across
                        # endpoints; keep a high default so downstream can treat
                        # it as a strong signal.
                        "confidence": 0.95,
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


class TesseractOcrClient(OcrProvider):
    """Tesseract OCR client implementation."""

    def __init__(
        self, min_confidence: float = 50.0, language: str = "chi_sim+eng"
    ):
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

    def _extract_elements_from_data(self, data: dict, *, min_conf: float) -> tuple[list[dict], dict]:
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
            psm_candidates: list[int] = [11]

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
                return (int(stats.get("lines") or 0) * 10) + int(stats.get("words") or 0)

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
                elems, stats = _run(lang, 11, min_conf=min_conf_primary)
                if elems is None or stats is None:
                    continue
                if best_lang is None or _score(stats) > _score(best_stats):
                    best_elements = elems
                    best_stats = stats
                    best_lang = lang
                    best_psm = 11

            # If the first pass looks low recall, try a couple more modes.
            if best_lang is not None:
                if int(best_stats.get("lines") or 0) < 12 and int(best_stats.get("words") or 0) < 80:
                    psm_candidates = [11, 6, 3]

            for psm in psm_candidates:
                if psm == 11:
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
                raise RuntimeError("Tesseract OCR failed for all languages") from last_error

            # If the configured min_conf is too strict, Tesseract can return an
            # empty/near-empty result on scan-heavy slides. In that case we
            # retry with a lower confidence threshold so we at least get line
            # geometry; downstream can filter obvious noise and (optionally)
            # refine text with an AI vision model.
            if min_conf_primary > 25.0:
                lines_n = int(best_stats.get("lines") or 0)
                words_n = int(best_stats.get("words") or 0)
                looks_empty = (not best_elements) or (lines_n < 8 and words_n < 40)
                if looks_empty:
                    low_min_conf = 25.0
                    low_best_elems: list[dict] = []
                    low_best_stats: dict = {"words": 0, "lines": 0, "avg_conf": 0.0}
                    low_best_lang: str | None = None
                    low_best_psm: int | None = None

                    # Start from the best (lang, psm) choice, but also probe a
                    # couple other modes to avoid pathological edge cases.
                    psm_probe: list[int] = []
                    if best_psm is not None:
                        psm_probe.append(int(best_psm))
                    for p in (11, 6, 3):
                        if p not in psm_probe:
                            psm_probe.append(p)

                    for psm in psm_probe:
                        for lang in lang_candidates:
                            elems, stats = _run(lang, int(psm), min_conf=low_min_conf)
                            if elems is None or stats is None:
                                continue
                            if low_best_lang is None or _score(stats) > _score(low_best_stats):
                                low_best_elems = elems
                                low_best_stats = stats
                                low_best_lang = lang
                                low_best_psm = int(psm)

                    if low_best_lang is not None and low_best_elems and _score(low_best_stats) > _score(best_stats):
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
                        best_psm = low_best_psm if low_best_psm is not None else best_psm
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
                best_psm if best_psm is not None else 11,
                used_min_conf,
            )
            return best_elements

        except Exception as e:
            logger.error(f"Tesseract OCR failed on {image_path}: {str(e)}")
            raise


class PaddleOcrClient(OcrProvider):
    """PaddleOCR local client implementation."""

    def __init__(self, language: str = "ch"):
        self.language = _normalize_paddle_language(language)
        self._engine: Any | None = None
        # PaddleOCR 3.x (PaddleX pipeline) can be memory-hungry on large page
        # renders. Downscale long-edge to keep CPU inference stable.
        self._max_side_px: int = 2200

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

    def ocr_image(self, image_path: str) -> List[Dict]:
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
                    import numpy as np

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

            if hasattr(texts, "tolist"):
                try:
                    texts = texts.tolist()
                except Exception:
                    pass
            if hasattr(polys, "tolist"):
                try:
                    polys = polys.tolist()
                except Exception:
                    pass
            if hasattr(scores, "tolist"):
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

                confidence_raw: Any = None
                if isinstance(scores, list) and i < len(scores):
                    confidence_raw = scores[i]
                try:
                    confidence = (
                        float(confidence_raw)
                        if confidence_raw is not None
                        else 0.85
                    )
                except Exception:
                    confidence = 0.85
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
                confidence = float(confidence_raw) if confidence_raw is not None else 0.85
            except Exception:
                confidence = 0.85
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
        if isinstance(raw_result, list) and raw_result and all(
            isinstance(v, dict) for v in raw_result
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
                        el["bbox"] = [x0 * scale_x, y0 * scale_y, x1 * scale_x, y1 * scale_y]
                logger.info(
                    "PaddleOCR extracted %s text elements from %s (paddlex pipeline)",
                    len(elements),
                    image_path,
                )
                return elements

        stack: list[Any] = [raw_result]
        max_nodes = 20000
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
                                else 0.85
                            )
                        except Exception:
                            confidence = 0.85
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

        logger.info("PaddleOCR extracted %s text elements from %s", len(elements), image_path)
        return elements


class OcrManager:
    """
    OCR manager with strict provider behavior.

    Policy:
    - If provider is explicitly `tesseract`/`local`, use Tesseract only.
    - For explicit providers (`aiocr`, `paddle`, `paddle_local`, `baidu`), do not
      implicitly fall back to local Tesseract.
    - With `strict_no_fallback=True`, `auto` mode does not use local fallback
      providers; it requires AI OCR and fails fast on setup/runtime failures.
    - With `strict_no_fallback=False`, `auto` mode keeps hybrid fallback behavior.
    """

    def __init__(
        self,
        provider: str | None = None,
        *,
        ai_provider: str | None = None,
        ai_api_key: str | None = None,
        ai_base_url: str | None = None,
        ai_model: str | None = None,
        baidu_app_id: str | None = None,
        baidu_api_key: str | None = None,
        baidu_secret_key: str | None = None,
        tesseract_min_confidence: float | None = None,
        tesseract_language: str | None = None,
        strict_no_fallback: bool = True,
        allow_paddle_model_downgrade: bool = False,
    ):
        """Initialize OCR manager with primary and fallback providers."""
        self.providers: list[OcrProvider] = []
        self.primary_provider: Optional[OcrProvider] = None
        self.fallback_provider: Optional[OcrProvider] = None
        self.last_provider_name: str | None = None
        self.provider_id: str = "auto"
        self.strict_no_fallback: bool = bool(strict_no_fallback)
        self.allow_paddle_model_downgrade: bool = bool(allow_paddle_model_downgrade)
        # Keep typed references so `auto` mode can combine results.
        self.baidu_provider: BaiduOcrClient | None = None
        self.tesseract_provider: TesseractOcrClient | None = None
        self.paddle_provider: AiOcrClient | PaddleOcrClient | None = None
        self.ai_provider: AiOcrClient | None = None

        provider_id = (provider or "auto").strip().lower()
        # Backward compatibility: legacy ids map to canonical provider names.
        if provider_id in {"remote", "ai"}:
            provider_id = "aiocr"
        if provider_id in {"paddle-local", "local_paddle"}:
            provider_id = "paddle_local"
        if provider_id not in {"auto", "aiocr", "baidu", "tesseract", "local", "paddle", "paddle_local"}:
            raise ValueError(f"Unsupported OCR provider: {provider_id}")
        self.provider_id = provider_id
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
                    min_confidence=tesseract_min_conf or 50.0,
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

        if provider_id == "aiocr":
            if not ai_api_key:
                raise ValueError("AI OCR requires api_key")
            ai_provider_id = ai_provider
            if _is_paddleocr_vl_model(ai_model):
                normalized = _normalize_ai_ocr_provider(ai_provider)
                if normalized == "auto" and not _clean_str(ai_base_url):
                    ai_provider_id = "siliconflow"
            self.ai_provider = AiOcrClient(
                api_key=ai_api_key,
                base_url=ai_base_url,
                model=ai_model,
                provider=ai_provider_id,
            )
            self.ai_provider.allow_model_downgrade = self.allow_paddle_model_downgrade
            self.providers.append(self.ai_provider)
            logger.info(
                "Using AI OCR as primary provider (vendor=%s, model=%s, base_url=%s)",
                self.ai_provider.provider_id,
                self.ai_provider.model,
                self.ai_provider.base_url or "<default>",
            )
            _maybe_add_tesseract_fallback(reason="aiocr")
        if provider_id in {"baidu"}:
            self.baidu_provider = BaiduOcrClient(
                app_id=baidu_app_id,
                api_key=baidu_api_key,
                secret_key=baidu_secret_key,
            )
            self.providers.append(self.baidu_provider)
            logger.info("Using Baidu OCR (explicit)")
            _maybe_add_tesseract_fallback(reason="baidu")
        if provider_id in {"tesseract", "local"}:
            self.tesseract_provider = TesseractOcrClient(
                min_confidence=tesseract_min_conf or 50.0,
                language=tesseract_lang,
            )
            self.providers.append(self.tesseract_provider)
            logger.info("Using Tesseract OCR (explicit)")
        if provider_id == "paddle_local":
            paddle_lang = "en" if tesseract_lang.strip().lower() == "eng" else "ch"
            self.paddle_provider = PaddleOcrClient(language=paddle_lang)
            self.providers.append(self.paddle_provider)
            logger.info("Using local PaddleOCR (explicit, lang=%s)", paddle_lang)
            _maybe_add_tesseract_fallback(reason="paddle_local")
        if provider_id == "paddle":
            if not ai_api_key:
                raise ValueError("Paddle OCR requires api_key")

            paddle_model = _clean_str(ai_model) or _DEFAULT_PADDLE_OCR_VL_MODEL
            if not _is_paddleocr_vl_model(paddle_model):
                raise ValueError(
                    "Paddle OCR provider requires a PaddleOCR-VL model (for example PaddlePaddle/PaddleOCR-VL or PaddlePaddle/PaddleOCR-VL-1.5)"
                )

            paddle_provider_id = _normalize_ai_ocr_provider(ai_provider)
            if paddle_provider_id == "auto" and not _clean_str(ai_base_url):
                paddle_provider_id = "siliconflow"

            self.paddle_provider = AiOcrClient(
                api_key=ai_api_key,
                base_url=ai_base_url,
                model=paddle_model,
                provider=paddle_provider_id,
            )
            self.paddle_provider.allow_model_downgrade = self.allow_paddle_model_downgrade
            self.providers.append(self.paddle_provider)
            logger.info(
                "Using PaddleOCR-VL as primary provider (vendor=%s, model=%s, base_url=%s)",
                self.paddle_provider.provider_id,
                self.paddle_provider.model,
                self.paddle_provider.base_url or "<default>",
            )
            _maybe_add_tesseract_fallback(reason="paddle_vl")

        if provider_id == "auto":
            if self.strict_no_fallback:
                if not ai_api_key:
                    raise RuntimeError(
                        "Strict OCR mode with provider=auto requires AI OCR credentials; "
                        "set ocr_provider=paddle/aiocr (recommended) or disable strict mode explicitly."
                    )

                self.ai_provider = AiOcrClient(
                    api_key=ai_api_key,
                    base_url=ai_base_url,
                    model=ai_model,
                    provider=ai_provider,
                )
                self.ai_provider.allow_model_downgrade = self.allow_paddle_model_downgrade
                self.providers.append(self.ai_provider)
                logger.info(
                    "Using AI OCR as primary provider in strict auto mode (vendor=%s, model=%s)",
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
                        min_confidence=tesseract_min_conf or 50.0,
                        language=tesseract_lang,
                    )
                    self.providers.append(self.tesseract_provider)
                    logger.info("Using Tesseract OCR as fallback provider in auto mode")
                except ImportError as e:
                    logger.warning("Tesseract OCR not available in auto mode: %s", e)

                try:
                    if ai_api_key:
                        self.ai_provider = AiOcrClient(
                            api_key=ai_api_key,
                            base_url=ai_base_url,
                            model=ai_model,
                            provider=ai_provider,
                        )
                        self.ai_provider.allow_model_downgrade = self.allow_paddle_model_downgrade
                        self.providers.append(self.ai_provider)
                        logger.info("Using AI OCR as supplementary provider in auto mode")
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
                if widths and heights and len(widths) >= 140:
                    widths.sort()
                    heights.sort()
                    median_w = float(widths[len(widths) // 2])
                    median_h = float(heights[len(heights) // 2])
                    # Word-level output tends to have narrow boxes compared to
                    # page width and relative to glyph height.
                    if median_w <= max(0.18 * float(W), 2.9 * float(median_h)):
                        allow_merge = True

                if allow_merge:
                    return _merge_ocr_items_to_lines(
                        normalized,
                        image_width=W,
                        image_height=H,
                        allow_merge=True,
                    )
                return normalized
            if self.provider_id == "paddle_local":
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
                if widths and heights and len(widths) >= 80:
                    widths.sort()
                    heights.sort()
                    median_w = float(widths[len(widths) // 2])
                    median_h = float(heights[len(heights) // 2])
                    # Word-level output tends to have narrow boxes compared to
                    # the page width and relative to glyph height.
                    if median_w <= max(0.22 * float(W), 3.2 * float(median_h)):
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
        ai_lines: list[dict] = []

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

        if self.ai_provider is not None:
            try:
                raw_ai = self.ai_provider.ocr_image(image_path)
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
                    if h >= max(3.0 * baseline_h, 0.14 * float(H)) and (
                        w >= 0.20 * float(W) or len(text) >= 8
                    ):
                        continue
                    if w >= 0.90 * float(W) and h >= max(
                        1.8 * baseline_h, 0.08 * float(H)
                    ):
                        continue
                else:
                    if h >= 0.16 * float(H) and w >= 0.20 * float(W):
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
        if ai_lines:
            _merge_in(ai_lines, "AI")

        if merged:
            self.last_provider_name = (
                f"HybridOcr({'+'.join(providers_used)})"
                if len(providers_used) > 1
                else (
                    "BaiduOcrClient"
                    if providers_used[0] == "Baidu"
                    else (
                        "TesseractOcrClient"
                        if providers_used[0] == "Tesseract"
                        else "AiOcrClient"
                    )
                )
            )
            return merged

        # Defensive fallback: re-run AI OCR directly if all merged lists are empty.
        if self.ai_provider is not None:
            try:
                raw_ai = self.ai_provider.ocr_image(image_path)
                self.last_provider_name = "AiOcrClient"
                return _normalize_ocr_items_as_lines(
                    raw_ai, image_width=W, image_height=H
                )
            except Exception as e:
                last_error = e
                logger.warning("AI OCR failed (auto mode): %s", e)

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
        for provider in self.providers:
            try:
                out = provider.ocr_image(image_path)
                self.last_provider_name = provider.__class__.__name__
                return out
            except Exception as e:
                last_error = e
                logger.warning(f"OCR provider failed: {str(e)}")
                continue

        raise RuntimeError("All OCR providers failed") from last_error

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
    ai_provider: str | None = None,
    ai_api_key: str | None = None,
    ai_base_url: str | None = None,
    ai_model: str | None = None,
    baidu_app_id: str | None = None,
    baidu_api_key: str | None = None,
    baidu_secret_key: str | None = None,
    tesseract_min_confidence: float | None = None,
    tesseract_language: str | None = None,
    strict_no_fallback: bool = True,
    allow_paddle_model_downgrade: bool = False,
) -> OcrManager:
    """
    Factory function to create OCR manager.

    Returns:
        Configured OcrManager instance
    """
    return OcrManager(
        provider=provider,
        ai_provider=ai_provider,
        ai_api_key=ai_api_key,
        ai_base_url=ai_base_url,
        ai_model=ai_model,
        baidu_app_id=baidu_app_id,
        baidu_api_key=baidu_api_key,
        baidu_secret_key=baidu_secret_key,
        tesseract_min_confidence=tesseract_min_confidence,
        tesseract_language=tesseract_language,
        strict_no_fallback=strict_no_fallback,
        allow_paddle_model_downgrade=allow_paddle_model_downgrade,
    )


def _clamp_int(value: float, low: int, high: int) -> int:
    return max(low, min(int(value), high))


def _rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
    r, g, b = rgb
    return f"#{r:02x}{g:02x}{b:02x}"


def _sample_text_color(image: Image.Image, bbox: List[float]) -> str:
    width, height = image.size
    if width <= 0 or height <= 0:
        return "#000000"

    x0, y0, x1, y1 = bbox
    x0 = _clamp_int(x0, 0, width - 1)
    y0 = _clamp_int(y0, 0, height - 1)
    x1 = _clamp_int(x1, 0, width - 1)
    y1 = _clamp_int(y1, 0, height - 1)

    cx = (x0 + x1) // 2
    cy = (y0 + y1) // 2

    # Estimate local background from samples just *outside* the bbox.
    pad = 3
    bg_points = [
        (x0 - pad, y0 - pad),
        (x1 + pad, y0 - pad),
        (x0 - pad, y1 + pad),
        (x1 + pad, y1 + pad),
        (x0 - pad, cy),
        (x1 + pad, cy),
        (cx, y0 - pad),
        (cx, y1 + pad),
    ]
    bg_samples: list[tuple[int, int, int]] = []
    for px, py in bg_points:
        px = _clamp_int(px, 0, width - 1)
        py = _clamp_int(py, 0, height - 1)
        r, g, b = image.getpixel((px, py))
        bg_samples.append((int(r), int(g), int(b)))

    if not bg_samples:
        br, bg, bb = 255.0, 255.0, 255.0
    else:
        # Median is more robust than mean when the outside samples hit a glyph
        # or a nearby icon/highlight.
        rs = sorted(c[0] for c in bg_samples)
        gs = sorted(c[1] for c in bg_samples)
        bs = sorted(c[2] for c in bg_samples)
        mid = len(rs) // 2
        br, bg, bb = float(rs[mid]), float(gs[mid]), float(bs[mid])

    bg_luma = 0.2126 * br + 0.7152 * bg + 0.0722 * bb

    # Candidate "foreground" samples inside bbox. Prefer the most contrasting,
    # but make the result less noisy by averaging a few extreme samples.
    fg_points: list[tuple[int, int]] = []
    grid_x = 6
    grid_y = 4
    for gx in range(1, grid_x):
        for gy in range(1, grid_y):
            px = x0 + (x1 - x0) * gx // grid_x
            py = y0 + (y1 - y0) * gy // grid_y
            fg_points.append((int(px), int(py)))

    candidates: list[tuple[float, float, tuple[int, int, int]]] = []  # (dist, luma, rgb)
    for px, py in fg_points:
        px = _clamp_int(px, 0, width - 1)
        py = _clamp_int(py, 0, height - 1)
        r, g, b = image.getpixel((px, py))
        dist = (float(r) - br) ** 2 + (float(g) - bg) ** 2 + (float(b) - bb) ** 2
        luma = 0.2126 * float(r) + 0.7152 * float(g) + 0.0722 * float(b)
        candidates.append((dist, luma, (int(r), int(g), int(b))))

    if not candidates:
        return "#000000"

    # Keep only pixels that are meaningfully different from background.
    candidates.sort(key=lambda t: t[0], reverse=True)
    top = [c for c in candidates[:10] if c[0] >= 400.0]  # (>=20 rgb distance)
    if not top:
        top = candidates[:5]

    # If the background is light, text tends to be dark (lower luma), and vice
    # versa. Pick a few candidates consistent with that and average.
    if bg_luma >= 128.0:
        top.sort(key=lambda t: t[1])  # darker first
    else:
        top.sort(key=lambda t: t[1], reverse=True)  # lighter first

    chosen = top[:3] if len(top) >= 3 else top[:1]
    r = int(round(sum(c[2][0] for c in chosen) / len(chosen)))
    g = int(round(sum(c[2][1] for c in chosen) / len(chosen)))
    b = int(round(sum(c[2][2] for c in chosen) / len(chosen)))
    return _rgb_to_hex((max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b))))


def _contains_cjk(text: str) -> bool:
    # Rough test: any character in common CJK blocks.
    for ch in text:
        code = ord(ch)
        if (
            0x4E00 <= code <= 0x9FFF  # CJK Unified Ideographs
            or 0x3400 <= code <= 0x4DBF  # CJK Unified Ideographs Extension A
            or 0x3040 <= code <= 0x30FF  # Hiragana + Katakana
            or 0xAC00 <= code <= 0xD7AF  # Hangul Syllables
        ):
            return True
    return False


def _is_cjk_char(ch: str) -> bool:
    if not ch:
        return False
    code = ord(ch)
    return (
        0x4E00 <= code <= 0x9FFF  # CJK Unified Ideographs
        or 0x3400 <= code <= 0x4DBF  # CJK Unified Ideographs Extension A
        or 0x3040 <= code <= 0x30FF  # Hiragana + Katakana
        or 0xAC00 <= code <= 0xD7AF  # Hangul Syllables
    )


def _should_insert_space(prev: str, nxt: str) -> bool:
    if not prev or not nxt:
        return False
    if _contains_cjk(prev) or _contains_cjk(nxt):
        return False
    # Insert spaces for Latin words/numbers where OCR gives tokens without spaces.
    return prev[-1].isalnum() and nxt[0].isalnum()


def _normalize_bbox_px(bbox: list[float]) -> tuple[float, float, float, float] | None:
    if not isinstance(bbox, list) or len(bbox) != 4:
        return None
    try:
        x0, y0, x1, y1 = (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
    except Exception:
        return None
    if math.isnan(x0) or math.isnan(y0) or math.isnan(x1) or math.isnan(y1):
        return None
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def _merge_ocr_items_to_lines(
    items: list[dict],
    *,
    image_width: int,
    image_height: int,
    allow_merge: bool = True,
) -> list[dict]:
    """Merge word-level OCR items into line-level items.

    Many OCR engines return per-word boxes which creates thousands of PPT shapes.
    Merging improves editability and fidelity when masking over a background render.
    """

    if not items:
        return []

    # If items contain Tesseract's structural fields, merge by (block, paragraph,
    # line) first. This is significantly more stable than purely geometric
    # clustering for multi-column pages and tables.
    if any(
        isinstance(it, dict) and it.get("line_num") is not None and it.get("block_num") is not None
        for it in items
    ):
        words: list[dict] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            text = str(it.get("text") or "").strip()
            bbox_n = _normalize_bbox_px(it.get("bbox"))
            if not text or bbox_n is None:
                continue
            try:
                block_num = int(it.get("block_num") or 0)
                par_num = int(it.get("par_num") or 0)
                line_num = int(it.get("line_num") or 0)
                word_num = int(it.get("word_num") or 0)
            except Exception:
                continue

            x0, y0, x1, y1 = bbox_n
            if x1 <= x0 or y1 <= y0:
                continue
            # Clamp.
            x0 = max(0.0, min(x0, float(image_width - 1)))
            x1 = max(0.0, min(x1, float(image_width)))
            y0 = max(0.0, min(y0, float(image_height - 1)))
            y1 = max(0.0, min(y1, float(image_height)))
            if x1 <= x0 or y1 <= y0:
                continue

            words.append(
                {
                    "text": text,
                    "bbox": [x0, y0, x1, y1],
                    "confidence": float(it.get("confidence") or 0.0),
                    "block_num": block_num,
                    "par_num": par_num,
                    "line_num": line_num,
                    "word_num": word_num,
                }
            )

        if words:
            heights = sorted(max(1.0, it["bbox"][3] - it["bbox"][1]) for it in words)
            median_h = heights[len(heights) // 2] if heights else 10.0
            median_h = max(4.0, float(median_h))
            # Split "line" groups when a large horizontal gap is present.
            #
            # Tesseract can sometimes assign the same (block,par,line) to text
            # tokens that are on the same Y baseline but belong to different
            # visual regions (e.g. paragraph text + a nearby diagram label).
            # Using a slightly stricter gap threshold reduces these accidental
            # cross-region merges while keeping normal word spacing intact.
            gap_thresh = max(1.8 * median_h, 0.025 * float(image_width))

            groups: dict[tuple[int, int, int], list[dict]] = {}
            for w in words:
                key = (int(w["block_num"]), int(w["par_num"]), int(w["line_num"]))
                groups.setdefault(key, []).append(w)

            merged: list[dict] = []
            for group in groups.values():
                # Tesseract occasionally assigns the same (block,par,line) to
                # tokens from multiple visual lines (especially in dense
                # paragraphs on scanned slides). Before splitting by horizontal
                # gaps, we split by Y-center to avoid merging multiple lines
                # into a single tall paragraph-like box.
                def _y_center_word(it: dict) -> float:
                    y0, y1 = float(it["bbox"][1]), float(it["bbox"][3])
                    return (y0 + y1) / 2.0

                y_thresh = max(0.70 * float(median_h), 0.006 * float(image_height))

                by_y = sorted(group, key=lambda it: (_y_center_word(it), float(it["bbox"][0])))
                sublines: list[list[dict]] = []
                current: list[dict] = []
                current_y: float | None = None
                for it in by_y:
                    yc = _y_center_word(it)
                    if not current:
                        current = [it]
                        current_y = yc
                        continue
                    assert current_y is not None
                    if abs(float(yc) - float(current_y)) > y_thresh:
                        sublines.append(current)
                        current = [it]
                        current_y = yc
                    else:
                        n = len(current)
                        current.append(it)
                        current_y = (float(current_y) * float(n) + float(yc)) / float(n + 1)
                if current:
                    sublines.append(current)

                for line_words in sublines:
                    group_sorted = sorted(
                        line_words,
                        key=lambda it: (
                            int(it.get("word_num") or 0),
                            float(it["bbox"][0]),
                        ),
                    )

                    segment: list[dict] = []
                    prev = None
                    for it in group_sorted:
                        if not segment:
                            segment = [it]
                            prev = it
                            continue
                        gap = float(it["bbox"][0]) - float(prev["bbox"][2])
                        if gap > gap_thresh:
                            merged.append(_merge_segment(segment))
                            segment = [it]
                        else:
                            segment.append(it)
                        prev = it
                    if segment:
                        merged.append(_merge_segment(segment))

            merged.sort(key=lambda it: ((it["bbox"][1] + it["bbox"][3]) / 2.0, it["bbox"][0]))
            out: list[dict] = []
            for m in merged:
                if not isinstance(m, dict):
                    continue
                text = str(m.get("text") or "").strip()
                bbox_n = _normalize_bbox_px(m.get("bbox"))
                if not text or bbox_n is None:
                    continue
                if _is_probably_noise_line(
                    text,
                    bbox_n,
                    image_width=int(image_width),
                    image_height=int(image_height),
                ):
                    continue
                out.append(m)
            return out

    normalized: list[dict] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        text = str(it.get("text") or "").strip()
        bbox_n = _normalize_bbox_px(it.get("bbox"))
        if not text or bbox_n is None:
            continue
        x0, y0, x1, y1 = bbox_n
        if x1 <= x0 or y1 <= y0:
            continue
        # Clamp.
        x0 = max(0.0, min(x0, float(image_width - 1)))
        x1 = max(0.0, min(x1, float(image_width - 1)))
        y0 = max(0.0, min(y0, float(image_height - 1)))
        y1 = max(0.0, min(y1, float(image_height - 1)))
        if x1 <= x0 or y1 <= y0:
            continue
        normalized.append(
            {
                "text": text,
                "bbox": [x0, y0, x1, y1],
                "confidence": float(it.get("confidence") or 0.0),
            }
        )

    if not normalized:
        return []

    if not allow_merge:
        normalized.sort(key=lambda it: ((it["bbox"][1] + it["bbox"][3]) / 2.0, it["bbox"][0]))
        out_no_merge: list[dict] = []
        for it in normalized:
            bbox_n = _normalize_bbox_px(it.get("bbox"))
            if bbox_n is None:
                continue
            text_value = str(it.get("text") or "").strip()
            if not text_value:
                continue
            if _is_probably_noise_line(
                text_value,
                bbox_n,
                image_width=int(image_width),
                image_height=int(image_height),
            ):
                continue
            out_no_merge.append({**it, "bbox": list(bbox_n), "text": text_value})
        return out_no_merge

    heights = sorted(max(1.0, it["bbox"][3] - it["bbox"][1]) for it in normalized)
    median_h = heights[len(heights) // 2] if heights else 10.0
    median_h = max(4.0, float(median_h))

    def y_center(it: dict) -> float:
        y0, y1 = it["bbox"][1], it["bbox"][3]
        return (y0 + y1) / 2.0

    normalized.sort(key=lambda it: (y_center(it), it["bbox"][0]))

    # Band clustering by vertical proximity/overlap.
    #
    # IMPORTANT: scanned slides often have multiple "cards" (left/right columns)
    # whose text lines share similar Y ranges. Purely Y-based banding can merge
    # unrelated items across columns; a tall bbox on the right column can then
    # expand the band's Y range and accidentally merge multiple rows from the
    # left column (we observed this with Baidu OCR tokens in small tables).
    #
    # To keep line merging stable, we also gate band membership by horizontal
    # proximity (x-gap threshold).
    bands: list[list[dict]] = []
    band_stats: list[dict[str, float]] = []  # min_y0, max_y1, min_x0, max_x1, center_y, n
    for it in normalized:
        x0, y0, x1, y1 = it["bbox"]
        yc = y_center(it)
        if not bands:
            bands.append([it])
            band_stats.append(
                {
                    "min_y0": float(y0),
                    "max_y1": float(y1),
                    "min_x0": float(x0),
                    "max_x1": float(x1),
                    "center_y": float(yc),
                    "n": 1.0,
                }
            )
            continue

        st = band_stats[-1]
        min_y0 = float(st.get("min_y0", 0.0))
        max_y1 = float(st.get("max_y1", 0.0))
        min_x0 = float(st.get("min_x0", 0.0))
        max_x1 = float(st.get("max_x1", 0.0))
        center_y = float(st.get("center_y", (min_y0 + max_y1) / 2.0))

        overlap = min(y1, max_y1) - max(y0, min_y0)
        band_h = max(1.0, max_y1 - min_y0)
        it_h = max(1.0, y1 - y0)

        # Horizontal gap between this item and the band's x-range.
        if x1 < min_x0:
            x_gap = float(min_x0 - x1)
        elif x0 > max_x1:
            x_gap = float(x0 - max_x1)
        else:
            x_gap = 0.0

        # Allow modest gaps for table columns (e.g. "label 70%"), but prevent
        # merging across distinct slide columns/cards.
        x_gap_thresh = max(0.04 * float(image_width), 6.0 * float(median_h))

        close = abs(float(yc) - center_y) <= 0.55 * float(median_h)
        same_line = (x_gap <= x_gap_thresh) and (
            close or (overlap >= 0.35 * min(band_h, it_h))
        )
        if same_line:
            bands[-1].append(it)
            st["min_y0"] = float(min(min_y0, y0))
            st["max_y1"] = float(max(max_y1, y1))
            st["min_x0"] = float(min(min_x0, x0))
            st["max_x1"] = float(max(max_x1, x1))
            n = int(float(st.get("n", 1.0) or 1.0))
            st["n"] = float(n + 1)
            st["center_y"] = float((center_y * n + float(yc)) / float(n + 1))
        else:
            bands.append([it])
            band_stats.append(
                {
                    "min_y0": float(y0),
                    "max_y1": float(y1),
                    "min_x0": float(x0),
                    "max_x1": float(x1),
                    "center_y": float(yc),
                    "n": 1.0,
                }
            )

    # Within each band, split by large horizontal gaps (multi-column / table cells).
    merged: list[dict] = []
    # Split segments on gaps that likely indicate a separate column/region.
    gap_thresh = max(1.8 * median_h, 0.025 * float(image_width))

    for band in bands:
        band_sorted = sorted(band, key=lambda it: it["bbox"][0])
        segment: list[dict] = []
        prev = None
        for it in band_sorted:
            if not segment:
                segment = [it]
                prev = it
                continue
            gap = float(it["bbox"][0]) - float(prev["bbox"][2])
            if gap > gap_thresh:
                # Flush current segment.
                merged.append(_merge_segment(segment))
                segment = [it]
            else:
                segment.append(it)
            prev = it
        if segment:
            merged.append(_merge_segment(segment))

    # Filter empty merges.
    out: list[dict] = []
    for m in merged:
        if not isinstance(m, dict):
            continue
        text = str(m.get("text") or "").strip()
        bbox_n = _normalize_bbox_px(m.get("bbox"))
        if not text or bbox_n is None:
            continue
        if _is_probably_noise_line(
            text,
            bbox_n,
            image_width=int(image_width),
            image_height=int(image_height),
        ):
            continue
        out.append(m)
    return out


def _merge_segment(segment: list[dict]) -> dict:
    seg_sorted = sorted(segment, key=lambda it: it["bbox"][0])
    parts: list[str] = []
    prev_text = ""
    for it in seg_sorted:
        t = str(it.get("text") or "").strip()
        if not t:
            continue
        if parts and _should_insert_space(prev_text, t):
            parts.append(" ")
        parts.append(t)
        prev_text = t
    text = "".join(parts).strip()

    x0 = min(float(it["bbox"][0]) for it in seg_sorted)
    y0 = min(float(it["bbox"][1]) for it in seg_sorted)
    x1 = max(float(it["bbox"][2]) for it in seg_sorted)
    y1 = max(float(it["bbox"][3]) for it in seg_sorted)
    confs = [float(it.get("confidence") or 0.0) for it in seg_sorted]
    confidence = sum(confs) / len(confs) if confs else 0.0
    return {"text": text, "bbox": [x0, y0, x1, y1], "confidence": confidence}


def _normalize_ocr_items_as_lines(
    items: list[dict],
    *,
    image_width: int,
    image_height: int,
) -> list[dict]:
    """Normalize OCR items that are already *line-level*.

    Some providers (notably Baidu's general/accurate OCR and many AI OCR
    prompts) output one item per visual line. Re-running the geometric merge
    step on such items can accidentally merge unrelated lines into huge boxes,
    which then causes over-masking and missing text in the generated PPT.
    """

    if not items:
        return []

    W = int(image_width)
    H = int(image_height)

    out: list[dict] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        text = str(it.get("text") or "").strip()
        bbox_n = _normalize_bbox_px(it.get("bbox"))
        if not text or bbox_n is None:
            continue
        if _looks_like_ocr_prompt_echo_text(text):
            continue
        if _is_probably_noise_line(text, bbox_n, image_width=W, image_height=H):
            continue

        x0, y0, x1, y1 = bbox_n
        if x1 <= x0 or y1 <= y0:
            continue
        # Clamp to image bounds.
        x0 = max(0.0, min(x0, float(W - 1)))
        x1 = max(0.0, min(x1, float(W)))
        y0 = max(0.0, min(y0, float(H - 1)))
        y1 = max(0.0, min(y1, float(H)))
        if x1 <= x0 or y1 <= y0:
            continue

        out.append({**it, "text": text, "bbox": [x0, y0, x1, y1]})

    out.sort(key=lambda it: ((it["bbox"][1] + it["bbox"][3]) / 2.0, it["bbox"][0]))
    return out


def _bbox_iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0 = max(ax0, bx0)
    iy0 = max(ay0, by0)
    ix1 = min(ax1, bx1)
    iy1 = min(ay1, by1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = (ix1 - ix0) * (iy1 - iy0)
    area_a = max(1.0, (ax1 - ax0) * (ay1 - ay0))
    area_b = max(1.0, (bx1 - bx0) * (by1 - by0))
    union = area_a + area_b - inter
    return float(inter) / float(max(1.0, union))


def _bbox_overlap_smaller(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0 = max(ax0, bx0)
    iy0 = max(ay0, by0)
    ix1 = min(ax1, bx1)
    iy1 = min(ay1, by1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = (ix1 - ix0) * (iy1 - iy0)
    area_a = max(1.0, (ax1 - ax0) * (ay1 - ay0))
    area_b = max(1.0, (bx1 - bx0) * (by1 - by0))
    return float(inter) / float(min(area_a, area_b))


def _normalize_text_for_dedupe(text: str) -> str:
    # Keep alnum/CJK, drop punctuation/whitespace for robust OCR text matching.
    return "".join(ch.lower() for ch in str(text or "") if ch.isalnum())


def _texts_are_similar_for_dedupe(a: str, b: str) -> bool:
    na = _normalize_text_for_dedupe(a)
    nb = _normalize_text_for_dedupe(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if na in nb or nb in na:
        short = min(len(na), len(nb))
        long = max(len(na), len(nb))
        return short >= 3 and (float(short) / float(long)) >= 0.65
    return False


def _dedupe_overlapping_ocr_items(items: list[dict]) -> list[dict]:
    """Drop near-duplicate OCR items caused by multi-engine merge/refinement.

    For single-provider runs (for example pure AI OCR), we only remove exact-ish
    duplicates and keep potentially overlapping lines/paragraph splits. Aggressive
    overlap dedupe is used only for mixed-provider merges.
    """

    candidates: list[dict] = []
    providers_seen: set[str] = set()
    heights: list[float] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        text = str(it.get("text") or "").strip()
        bbox_n = _normalize_bbox_px(it.get("bbox"))
        if not text or bbox_n is None:
            continue
        x0, y0, x1, y1 = bbox_n
        if x1 <= x0 or y1 <= y0:
            continue
        conf = float(it.get("confidence") or 0.0)
        area = float((x1 - x0) * (y1 - y0))
        h = float(y1 - y0)
        heights.append(max(1.0, h))
        provider_name = str(it.get("provider") or it.get("source") or "").strip().lower()
        if provider_name:
            providers_seen.add(provider_name)
        candidates.append(
            {
                **it,
                "text": text,
                "bbox": [x0, y0, x1, y1],
                "_bbox_t": (x0, y0, x1, y1),
                "_conf": conf,
                "_area": area,
                "_provider": provider_name,
                "_cx": float(x0 + x1) / 2.0,
                "_cy": float(y0 + y1) / 2.0,
                "_h": float(h),
            }
        )

    if len(candidates) <= 1:
        for it in candidates:
            it.pop("_bbox_t", None)
            it.pop("_conf", None)
            it.pop("_area", None)
            it.pop("_provider", None)
        return candidates

    # Prefer higher confidence, then smaller area (usually tighter line bbox).
    candidates.sort(key=lambda it: (-float(it["_conf"]), float(it["_area"])))

    multi_provider = len(providers_seen) >= 2
    heights.sort()
    median_h = float(heights[len(heights) // 2]) if heights else 10.0
    median_h = max(4.0, float(median_h))

    kept: list[dict] = []
    dropped = 0
    for cur in candidates:
        cur_bbox = cur["_bbox_t"]
        cur_text = str(cur.get("text") or "")
        cur_cx = float(cur.get("_cx") or 0.0)
        cur_cy = float(cur.get("_cy") or 0.0)
        duplicate = False
        for prev in kept:
            prev_bbox = prev["_bbox_t"]
            prev_cx = float(prev.get("_cx") or 0.0)
            prev_cy = float(prev.get("_cy") or 0.0)
            iou = _bbox_iou(cur_bbox, prev_bbox)
            overlap_small = _bbox_overlap_smaller(cur_bbox, prev_bbox)

            # Same-geometry duplicates can appear in malformed AI grounding output
            # (different text strings mapped to the exact same bbox). Keep only one.
            strong_same_bbox = overlap_small >= 0.985 and iou >= 0.90
            if strong_same_bbox:
                duplicate = True
                break

            # AI OCR (and some gateways) can also output near-identical boxes with
            # small jitter. Treat them as duplicates even if the text differs.
            near_same_bbox = overlap_small >= 0.965 and iou >= 0.85
            if near_same_bbox:
                duplicate = True
                break

            # Exact-ish duplicate candidate.
            exact_like = (
                overlap_small >= 0.93
                and _texts_are_similar_for_dedupe(cur_text, str(prev.get("text") or ""))
            )
            if exact_like:
                duplicate = True
                break

            # In single-provider runs we are intentionally conservative, but we
            # still want to suppress obvious "same text, slightly shifted bbox"
            # duplicates which otherwise show up as stacked/offset glyphs.
            if not multi_provider:
                if _texts_are_similar_for_dedupe(cur_text, str(prev.get("text") or "")):
                    if overlap_small >= 0.85:
                        duplicate = True
                        break
                    # Some AI OCR engines (notably DeepSeek grounding outputs on
                    # gateways) can emit the same line twice with a slightly
                    # larger jitter (overlap ~0.70-0.85). Use a vertical-center
                    # guard to avoid deleting distinct nearby lines.
                    dy = abs(cur_cy - prev_cy)
                    if dy <= (0.55 * median_h) and (overlap_small >= 0.70 or iou >= 0.55):
                        duplicate = True
                        break

            if multi_provider:
                # Only do aggressive overlap pruning for mixed-provider merges,
                # where stacked duplicate lines are common.
                if overlap_small >= 0.88 or iou >= 0.78:
                    duplicate = True
                    break
                if iou >= 0.62 and _texts_are_similar_for_dedupe(
                    cur_text, str(prev.get("text") or "")
                ):
                    duplicate = True
                    break

        if duplicate:
            dropped += 1
            continue
        kept.append(cur)

    if dropped > 0:
        logger.info("OCR dedupe dropped %s overlapping items", dropped)

    out: list[dict] = []
    for it in kept:
        cp = dict(it)
        cp.pop("_bbox_t", None)
        cp.pop("_conf", None)
        cp.pop("_area", None)
        cp.pop("_provider", None)
        cp.pop("_cx", None)
        cp.pop("_cy", None)
        cp.pop("_h", None)
        out.append(cp)

    # Stable reading order for downstream conversion.
    out.sort(key=lambda it: ((it["bbox"][1] + it["bbox"][3]) / 2.0, it["bbox"][0]))
    return out


def _is_probably_noise_line(
    text: str,
    bbox: tuple[float, float, float, float],
    *,
    image_width: int,
    image_height: int,
) -> bool:
    t = str(text or "").strip()
    if not t:
        return True

    if _looks_like_ocr_prompt_echo_text(t):
        return True

    # Skip pure punctuation / dots (common false positives in scans).
    stripped = "".join(ch for ch in t if not ch.isspace())
    if stripped and all((not ch.isalnum()) for ch in stripped):
        return True
    if len(stripped) >= 6 and set(stripped) <= {"."}:
        return True

    cjk = _contains_cjk(t)
    has_digit = any(ch.isdigit() for ch in t)
    has_alpha = any(ch.isalpha() for ch in t)

    x0, y0, x1, y1 = bbox
    w = max(0.0, x1 - x0)
    h = max(0.0, y1 - y0)
    area = w * h
    img_area = float(max(1, int(image_width) * int(image_height)))

    # Common acronyms that can appear as standalone tokens in slide decks.
    # We keep these even when other heuristics would treat them as noise.
    # Short Latin-only tokens inside small/odd boxes are frequently garbage
    # (icons/logos or screenshot UI chrome). However, 2-letter ALLCAPS tokens
    # like "AI" / "EF" can be meaningful abbreviations in decks, so we keep them
    # unless they are extremely tiny.
    if (not cjk) and (not has_digit) and has_alpha:
        alpha_only = "".join(ch for ch in stripped if ch.isalpha())
        if alpha_only and alpha_only.upper() in _ACRONYM_ALLOWLIST:
            return False

        if len(stripped) == 1:
            # Single-letter hits are almost always noise on scanned slides.
            if area / img_area < 0.002:
                return True
            if image_height > 0 and (h / float(image_height)) >= 0.08:
                return True
        elif len(stripped) == 2:
            if stripped.isupper():
                # Two-letter ALLCAPS tokens can be meaningful ("AI", "UI"), but
                # most random ones on scanned slides are icon false positives.
                # Keep a small allowlist and be stricter otherwise.
                min_area = 0.00035 if stripped.upper() in _ACRONYM_ALLOWLIST else 0.00070
                if area / img_area < min_area:
                    return True
                if image_height > 0 and (h / float(image_height)) >= 0.10:
                    return True
            else:
                if area / img_area < 0.0012:
                    return True
                # If the bbox is *very* tall relative to the page but contains
                # only 1-2 Latin letters, it is almost certainly an icon false
                # positive.
                if image_height > 0 and (h / float(image_height)) >= 0.08:
                    return True
        elif stripped.isupper() and 3 <= len(stripped) <= 4:
            # 3-4 uppercase tokens are often noise ("FRM", "GFE") produced by
            # icons / diagram strokes. Keep only if the bbox is reasonably large.
            if area / img_area < 0.0009:
                return True
            if image_height > 0 and (h / float(image_height)) >= 0.11:
                return True

    return False


def _filter_contextual_noise_items(
    items: list[dict],
    *,
    image_width: int,
    image_height: int,
) -> list[dict]:
    """Page-contextual OCR cleanup to reduce image-internal gibberish tokens.

    This is intentionally conservative and only applies stricter rules when the
    page is clearly CJK-dominant (common in scanned slides where icons/figures
    leak short Latin fragments like "T os", "RAN," etc.).
    """

    W = max(1, int(image_width))
    H = max(1, int(image_height))

    candidates: list[dict] = []
    cjk_chars = 0
    total_chars = 0
    for it in items:
        if not isinstance(it, dict):
            continue
        text = str(it.get("text") or "").strip()
        bbox_n = _normalize_bbox_px(it.get("bbox"))
        if not text or bbox_n is None:
            continue
        candidates.append({**it, "text": text, "bbox": list(bbox_n)})
        for ch in text:
            if ch.isspace():
                continue
            total_chars += 1
            if _is_cjk_char(ch):
                cjk_chars += 1

    if not candidates:
        return []

    cjk_ratio = (float(cjk_chars) / float(total_chars)) if total_chars > 0 else 0.0
    cjk_dominant = cjk_ratio >= 0.32

    out: list[dict] = []
    for it in candidates:
        text = str(it.get("text") or "").strip()
        bbox = _normalize_bbox_px(it.get("bbox"))
        if not text or bbox is None:
            continue
        x0, y0, x1, y1 = bbox
        w = max(1.0, float(x1 - x0))
        h = max(1.0, float(y1 - y0))
        area_ratio = (w * h) / float(W * H)

        stripped = "".join(ch for ch in text if not ch.isspace())
        alpha_only = "".join(ch for ch in stripped if ch.isalpha())
        has_alpha = bool(alpha_only)
        has_digit = any(ch.isdigit() for ch in stripped)
        has_cjk = any(_is_cjk_char(ch) for ch in stripped)
        conf = float(it.get("confidence") or 0.0)

        drop = False

        if cjk_dominant:
            if has_alpha and not has_digit:
                up = alpha_only.upper()
                # Very short Latin tokens on CJK pages are usually icon/UI noise.
                if len(alpha_only) <= 4 and up not in _ACRONYM_ALLOWLIST:
                    if area_ratio < 0.012:
                        drop = True
                # Lowercase short words are rarely meaningful in CJK titles/body.
                if (
                    len(alpha_only) <= 6
                    and alpha_only.islower()
                    and area_ratio < 0.015
                ):
                    drop = True
                # Long pure-Latin words on CJK-dominant pages are commonly
                # labels from embedded screenshots/diagrams (e.g. "Probability").
                # Keep larger heading-like words, drop tiny ones.
                if (not has_cjk) and len(alpha_only) >= 7 and area_ratio < 0.0035:
                    drop = True
                # Mixed short CJK+Latin fragments like "它crt".
                if has_cjk and len(stripped) <= 7 and len(alpha_only) <= 4:
                    drop = True

            # Repetitive ultra-short CJK fragments like "一国一一".
            if (not has_alpha) and has_cjk and len(stripped) <= 4:
                freq: dict[str, int] = {}
                for ch in stripped:
                    freq[ch] = freq.get(ch, 0) + 1
                max_freq = max(freq.values()) if freq else 0
                if max_freq >= max(3, len(stripped) - 1):
                    drop = True

            # Small mixed alpha+digit snippets on CJK pages are usually from
            # UI fragments in screenshots (e.g. "worst70%", "A1", "x3.2").
            if has_alpha and has_digit and (not has_cjk):
                if len(stripped) <= 14 and area_ratio < 0.0040:
                    drop = True

            # Tiny numeric-only fragments (e.g. "5%", "14%") are often chart
            # labels inside image regions and should not become editable text.
            if has_digit and (not has_alpha) and (not has_cjk):
                if len(stripped) <= 5 and area_ratio < 0.0015:
                    drop = True

        # Confidence-aware cleanup for tiny non-CJK snippets.
        if (not has_cjk) and len(stripped) <= 8 and conf > 0.0 and conf < 0.45:
            if area_ratio < 0.02:
                drop = True

        if not drop:
            out.append({**it, "bbox": [x0, y0, x1, y1]})

    out.sort(key=lambda it: ((it["bbox"][1] + it["bbox"][3]) / 2.0, it["bbox"][0]))
    return out


def _merge_line_items_prefer_primary(
    primary: list[dict],
    secondary: list[dict],
    *,
    image_width: int,
    image_height: int,
) -> list[dict]:
    """Merge two *line-level* OCR item lists.

    We keep all primary items and only add secondary items that do not overlap
    meaningfully with any primary bbox. This improves recall without producing
    duplicate lines.
    """

    W = int(image_width)
    H = int(image_height)

    prim: list[dict] = []
    prim_boxes: list[tuple[float, float, float, float]] = []
    prim_heights: list[float] = []

    for it in primary:
        if not isinstance(it, dict):
            continue
        text = str(it.get("text") or "").strip()
        bbox_n = _normalize_bbox_px(it.get("bbox"))
        if not text or bbox_n is None:
            continue
        if _is_probably_noise_line(text, bbox_n, image_width=W, image_height=H):
            continue
        x0, y0, x1, y1 = bbox_n
        if x1 <= x0 or y1 <= y0:
            continue
        prim.append({**it, "text": text, "bbox": [x0, y0, x1, y1]})
        prim_boxes.append((x0, y0, x1, y1))
        prim_heights.append(max(1.0, y1 - y0))

    prim_heights.sort()
    median_prim_h = prim_heights[len(prim_heights) // 2] if prim_heights else 10.0
    median_prim_h = max(4.0, float(median_prim_h))

    out: list[dict] = list(prim)

    def _matches_primary(bbox: tuple[float, float, float, float]) -> bool:
        x0, y0, x1, y1 = bbox
        cx = (x0 + x1) / 2.0
        cy = (y0 + y1) / 2.0
        for pb in prim_boxes:
            iou = _bbox_iou(bbox, pb)
            # Use a slightly stricter IoU threshold so we don't incorrectly
            # treat nearby-but-distinct lines as duplicates.
            if iou >= 0.45:
                return True
            px0, py0, px1, py1 = pb
            p_w = max(1.0, px1 - px0)
            p_h = max(1.0, py1 - py0)
            s_w = max(1.0, x1 - x0)
            s_h = max(1.0, y1 - y0)

            # Center-in-box match is helpful for minor jitter, but it's also
            # very aggressive when the primary box is abnormally large (e.g.
            # paragraph-level). In those cases we avoid suppressing secondary
            # lines which may contain the missing text geometry.
            primary_is_reasonable_line = (
                p_h <= (2.2 * median_prim_h) and p_w <= (0.98 * float(W))
            )
            secondary_is_reasonable_line = s_h <= (2.6 * median_prim_h)
            if primary_is_reasonable_line and secondary_is_reasonable_line:
                if (
                    cx >= (px0 - 2.0)
                    and cx <= (px1 + 2.0)
                    and cy >= (py0 - 2.0)
                    and cy <= (py1 + 2.0)
                ):
                    return True
            # High overlap relative to the smaller box.
            ix0 = max(x0, px0)
            iy0 = max(y0, py0)
            ix1 = min(x1, px1)
            iy1 = min(y1, py1)
            if ix1 <= ix0 or iy1 <= iy0:
                continue
            inter = (ix1 - ix0) * (iy1 - iy0)
            area_s = max(1.0, (x1 - x0) * (y1 - y0))
            area_p = max(1.0, (px1 - px0) * (py1 - py0))
            if inter >= 0.85 * float(min(area_s, area_p)):
                return True
        return False

    for it in secondary:
        if not isinstance(it, dict):
            continue
        text = str(it.get("text") or "").strip()
        bbox_n = _normalize_bbox_px(it.get("bbox"))
        if not text or bbox_n is None:
            continue
        if _is_probably_noise_line(text, bbox_n, image_width=W, image_height=H):
            continue
        if _matches_primary(bbox_n):
            continue
        x0, y0, x1, y1 = bbox_n
        out.append({**it, "text": text, "bbox": [x0, y0, x1, y1]})

    # Stable reading order.
    out.sort(key=lambda it: ((it["bbox"][1] + it["bbox"][3]) / 2.0, it["bbox"][0]))
    return out


def ocr_image_to_elements(
    image_path: str,
    *,
    page_width_pt: float,
    page_height_pt: float,
    ocr_manager: OcrManager,
    text_refiner: AiOcrTextRefiner | None = None,
    linebreak_refiner: AiOcrTextRefiner | None = None,
    strict_no_fallback: bool = True,
    linebreak_assist: bool | None = None,
) -> List[Dict]:
    image = Image.open(image_path).convert("RGB")
    width, height = image.size
    if width <= 0 or height <= 0:
        return []

    def _split_text_into_n_lines(text: str, *, n: int) -> list[str] | None:
        """Heuristically split a paragraph into N lines (no OCR re-run).

        This is a best-effort fallback used when we can *see* multi-line ink
        in a bbox (via projection), but do not have an AI vision model to
        split the text accurately. The main goal is layout fidelity (line
        count + approximate balance) rather than perfect linguistic wrapping.
        """

        n = int(n)
        raw = str(text or "").strip()
        if n <= 1 or not raw:
            return None

        # Punctuation line-breaking guards. We do not want a line to *start*
        # with closing punctuation (e.g. "：" or "）") because it is visually
        # jarring and causes obvious layout drift in PPT output.
        NO_BREAK_BEFORE = set(",.;:!?)]}、，。！？：；）】」』》〉%‰°")
        NO_BREAK_AFTER = set("([{（《【「『“‘")

        def _fix_punctuation_breaks(lines: list[str]) -> list[str]:
            if len(lines) <= 1:
                return lines

            out = [str(seg or "") for seg in lines]
            for _ in range(3):
                changed = False
                for i in range(1, len(out)):
                    prev = out[i - 1]
                    cur = out[i]
                    if not prev or not cur:
                        continue

                    # If current line begins with forbidden punctuation, move it
                    # to the end of previous line.
                    while cur and cur[0] in NO_BREAK_BEFORE and prev:
                        prev = prev + cur[0]
                        cur = cur[1:].lstrip()
                        changed = True
                        if not cur:
                            break

                    # If previous line ends with an opening punctuation, move it
                    # to the start of current line.
                    while prev and prev[-1] in NO_BREAK_AFTER and cur:
                        cur = prev[-1] + cur
                        prev = prev[:-1].rstrip()
                        changed = True
                        if not prev:
                            break

                    out[i - 1] = prev
                    out[i] = cur

                if not changed:
                    break

            return [seg for seg in (s.strip() for s in out) if seg]

        # If the upstream provider already inserted line breaks, do not
        # override them here.
        if "\n" in raw:
            lines = [seg.strip() for seg in raw.splitlines() if seg.strip()]
            if len(lines) >= 2:
                return _fix_punctuation_breaks(lines)
            return None

        is_cjk = _contains_cjk(raw)

        # Prefer word-level split when there is whitespace and we are not on a
        # CJK-heavy string.
        if (not is_cjk) and re.search(r"\s", raw):
            words = [w for w in re.split(r"\s+", raw) if w]
            if len(words) <= 1:
                return None
            total_chars = sum(len(w) for w in words) + max(0, len(words) - 1)
            target = max(1.0, float(total_chars) / float(n))
            lines: list[str] = []
            cur: list[str] = []
            cur_len = 0

            def _flush() -> None:
                nonlocal cur, cur_len
                if cur:
                    lines.append(" ".join(cur).strip())
                cur = []
                cur_len = 0

            for word in words:
                add_len = len(word) + (1 if cur else 0)
                if (
                    lines
                    and len(lines) < (n - 1)
                    and cur
                    and (float(cur_len + add_len) >= (1.12 * target))
                ):
                    _flush()
                cur.append(word)
                cur_len += add_len
            _flush()

            if len(lines) == n and all(lines):
                return _fix_punctuation_breaks(lines)
            # Try to rebalance by splitting the longest line(s).
            while len(lines) < n:
                longest_idx = max(range(len(lines)), key=lambda i: len(lines[i]))
                parts = lines[longest_idx].split()
                if len(parts) <= 1:
                    break
                mid = max(1, len(parts) // 2)
                left = " ".join(parts[:mid]).strip()
                right = " ".join(parts[mid:]).strip()
                if not left or not right:
                    break
                lines[longest_idx : longest_idx + 1] = [left, right]

            if len(lines) == n and all(lines):
                return _fix_punctuation_breaks(lines)
            return None

        # CJK or compact text: split by character count with punctuation-aware cuts.
        compact = re.sub(r"\s+", "", raw)
        if len(compact) < max(4, n * 2):
            return None

        break_chars = set("，。、；：！？,.!?:;）)】]》>、")
        breakpoints = [
            idx + 1
            for idx, ch in enumerate(compact)
            if ch in break_chars and idx + 1 < len(compact)
        ]
        target = float(len(compact)) / float(n)
        cuts: list[int] = []
        last = 0
        for k in range(1, n):
            ideal = int(round(float(k) * target))
            ideal = max(last + 1, min(len(compact) - 1, ideal))
            chosen = ideal
            # Pick a nearby punctuation breakpoint when available.
            if breakpoints:
                candidates = [p for p in breakpoints if (last + 1) <= p <= (len(compact) - 1)]
                if candidates:
                    nearest = min(candidates, key=lambda p: abs(p - ideal))
                    if abs(nearest - ideal) <= max(2, int(round(0.45 * target))):
                        chosen = nearest
            chosen = max(last + 1, min(len(compact) - 1, chosen))
            cuts.append(chosen)
            last = chosen

        parts: list[str] = []
        start = 0
        for cut in cuts + [len(compact)]:
            seg = compact[start:cut].strip()
            if seg:
                parts.append(seg)
            start = cut

        if len(parts) != n or not all(parts):
            return None
        return _fix_punctuation_breaks(parts)

    def _estimate_line_ranges_by_ink(
        bbox_n: tuple[float, float, float, float],
        *,
        typical_line_height: float,
        max_lines: int,
    ) -> list[tuple[float, float]] | None:
        """Estimate per-line vertical ranges using ink projection inside a bbox."""

        try:
            import numpy as np
        except Exception:
            return None

        x0, y0, x1, y1 = bbox_n
        W = int(width)
        H = int(height)

        xi0 = max(0, min(W - 1, int(math.floor(float(x0)))))
        yi0 = max(0, min(H - 1, int(math.floor(float(y0)))))
        xi1 = max(0, min(W, int(math.ceil(float(x1)))))
        yi1 = max(0, min(H, int(math.ceil(float(y1)))))
        if xi1 - xi0 < 6 or yi1 - yi0 < 10:
            return None

        try:
            gray = image.crop((xi0, yi0, xi1, yi1)).convert("L")
            arr = np.asarray(gray, dtype=np.float32)
        except Exception:
            return None

        if arr.ndim != 2 or arr.size <= 0:
            return None
        h_px, w_px = arr.shape
        if h_px < 10 or w_px < 6:
            return None

        p95 = float(np.percentile(arr, 95.0))
        p10 = float(np.percentile(arr, 10.0))
        contrast = max(1.0, p95 - p10)
        if contrast < 8.0:
            return None

        ink = np.clip((p95 - arr) / contrast, 0.0, 1.0)
        ink_mask = (ink >= 0.16).astype(np.float32)
        row_profile = ink_mask.mean(axis=1)
        if float(np.sum(row_profile)) <= max(0.02 * h_px, 1.0):
            return None

        k = max(1, int(round(h_px / 54.0)))
        if k > 1:
            kernel = np.ones((k,), dtype=np.float32) / float(k)
            smooth = np.convolve(row_profile, kernel, mode="same")
        else:
            smooth = row_profile

        # Use an adaptive threshold: above this value we consider the row part
        # of a text line. Keep a floor to avoid missing very light text.
        th = float(np.percentile(smooth, 70.0))
        th = max(0.055, min(0.20, th))

        active = smooth >= th
        segments: list[tuple[int, int]] = []
        start: int | None = None
        for idx, on in enumerate(active.tolist()):
            if on and start is None:
                start = idx
            elif (not on) and start is not None:
                segments.append((start, idx))
                start = None
        if start is not None:
            segments.append((start, h_px))

        if not segments:
            return None

        min_seg_h = max(2, int(round(0.25 * float(typical_line_height))))
        filtered: list[tuple[int, int]] = []
        for s, e in segments:
            if e - s < min_seg_h:
                continue
            filtered.append((s, e))
        segments = filtered
        if len(segments) < 2:
            return None

        # Merge segments separated by tiny gaps (diacritics / punctuation noise).
        merge_gap = max(1, int(round(0.22 * float(typical_line_height))))
        merged: list[tuple[int, int]] = []
        cur_s, cur_e = segments[0]
        for s, e in segments[1:]:
            if s - cur_e <= merge_gap:
                cur_e = e
            else:
                merged.append((cur_s, cur_e))
                cur_s, cur_e = s, e
        merged.append((cur_s, cur_e))
        segments = merged

        if len(segments) < 2:
            return None
        if len(segments) > max(2, int(max_lines)):
            return None

        ranges: list[tuple[float, float]] = []
        prev_y = float(y0)
        for s, e in segments:
            ly0 = float(y0) + float(s)
            ly1 = float(y0) + float(e)
            # Clamp and enforce monotonic.
            ly0 = max(float(y0), min(float(y1) - 1.0, ly0))
            ly1 = max(ly0 + 1.0, min(float(y1), ly1))
            if ly0 < prev_y:
                ly0 = prev_y
            if ly1 <= ly0:
                continue
            ranges.append((ly0, ly1))
            prev_y = ly1

        if len(ranges) < 2:
            return None
        return ranges

    def _heuristic_assist_line_breaks(items: list[dict], *, force: bool) -> list[dict]:
        if not items:
            return items

        heights: list[float] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            bbox_n = _normalize_bbox_px(it.get("bbox"))
            if bbox_n is None:
                continue
            _, y0, _, y1 = bbox_n
            h = float(y1 - y0)
            if h > 0:
                heights.append(h)
        if heights:
            heights.sort()
            # Use a lower quantile to avoid paragraph boxes dominating the median.
            q_idx = int(round(0.35 * float(len(heights) - 1)))
            typical_h = max(4.0, float(heights[max(0, min(len(heights) - 1, q_idx))]))
        else:
            typical_h = max(10.0, 0.02 * float(height))

        max_lines = 8
        split_count = 0
        out: list[dict] = []

        candidates: list[tuple[int, dict, tuple[float, float, float, float], str]] = []
        for idx, original in enumerate(items):
            if not isinstance(original, dict):
                continue
            text = str(original.get("text") or "").strip()
            bbox_n = _normalize_bbox_px(original.get("bbox"))
            if not text or bbox_n is None:
                continue
            if "\n" in text:
                continue
            if _is_multiline_candidate_for_linebreak_assist(
                text=text,
                bbox=bbox_n,
                image_width=int(width),
                image_height=int(height),
                median_line_height=float(typical_h),
            ):
                candidates.append((idx, original, bbox_n, text))

        # Auto-mode guard: only apply the heuristic when we have enough strong
        # multiline candidates to justify splitting. This avoids accidentally
        # splitting a small number of tall headings on otherwise line-level OCR.
        if (not force) and len(candidates) < max(3, int(round(0.18 * float(len(items))))):
            return items

        candidate_by_idx: dict[int, tuple[dict, tuple[float, float, float, float], str]] = {
            int(idx): (orig, bb, txt) for idx, orig, bb, txt in candidates
        }

        for idx, original in enumerate(items):
            if not isinstance(original, dict):
                continue
            cand = candidate_by_idx.get(int(idx))
            if cand is None:
                out.append(dict(original))
                continue
            cand_original, bbox_n, text = cand

            x0, y0, x1, y1 = bbox_n
            box_h = max(1.0, float(y1 - y0))

            ranges = _estimate_line_ranges_by_ink(
                bbox_n,
                typical_line_height=float(typical_h),
                max_lines=max_lines,
            )

            n_lines = 0
            if ranges is not None:
                n_lines = len(ranges)
            else:
                est = int(round(box_h / max(1.0, float(typical_h))))
                n_lines = max(1, min(max_lines, est))
                if n_lines < 2:
                    out.append(dict(original))
                    continue
                total_h = float(y1 - y0)
                ranges = [
                    (
                        float(y0) + total_h * float(i) / float(n_lines),
                        float(y0) + total_h * float(i + 1) / float(n_lines),
                    )
                    for i in range(n_lines)
                ]

            if ranges is None or len(ranges) < 2:
                out.append(dict(cand_original))
                continue

            # Text split fallback: balance text across detected lines.
            lines = _split_text_into_n_lines(text, n=len(ranges))
            if not lines or len(lines) != len(ranges):
                out.append(dict(cand_original))
                continue

            for (ly0, ly1), text_line in zip(ranges, lines):
                cleaned_line = str(text_line or "").strip()
                if not cleaned_line:
                    continue
                if float(ly1 - ly0) < 1.0:
                    continue
                new_item = dict(cand_original)
                new_item["text"] = cleaned_line
                new_item["bbox"] = [float(x0), float(ly0), float(x1), float(ly1)]
                out.append(new_item)

            split_count += 1

        if split_count > 0:
            logger.info(
                "Heuristic line-break assist applied (no AI): split_boxes=%s/%s",
                split_count,
                len(items),
            )
        return out

    elements: List[Dict] = []
    merged_items = ocr_manager.ocr_image_lines(
        image_path, image_width=width, image_height=height
    )
    if linebreak_refiner is not None and merged_items and linebreak_assist is True:
        try:
            merged_items = linebreak_refiner.assist_line_breaks(
                image_path,
                items=merged_items,
                allow_heuristic_fallback=not bool(strict_no_fallback),
            )
        except Exception as e:
            logger.warning("AI OCR line-break assist failed: %s", e)
    elif linebreak_assist is True and merged_items:
        # Fallback: when user requests line-break assist (or backend auto-enabled
        # it) but no AI vision refiner is available, split coarse paragraph-like
        # boxes using pixel projection + text balancing. This is much better
        # than letting PPT guess wraps, and keeps the pipeline usable in fully
        # open-source deployments.
        try:
            merged_items = _heuristic_assist_line_breaks(merged_items, force=True)
        except Exception as e:
            logger.warning("Heuristic line-break assist failed: %s", e)
    elif (
        merged_items
        and linebreak_assist is None
        and (not strict_no_fallback)
        and linebreak_refiner is None
    ):
        # Auto best-effort: AI OCR and some gateways return paragraph-like boxes
        # even when the user didn't enable explicit line-break assist. In
        # non-strict mode we can try a conservative heuristic split to reduce
        # wrap drift in PPT output.
        try:
            provider_id = str(getattr(ocr_manager, "provider_id", "") or "").lower()
            last_provider = str(getattr(ocr_manager, "last_provider_name", "") or "")
            should_try = provider_id in {"aiocr", "paddle"} or last_provider == "AiOcrClient"
            if should_try:
                merged_items = _heuristic_assist_line_breaks(merged_items, force=False)
        except Exception as e:
            logger.warning("Auto heuristic line-break assist failed: %s", e)

    if (
        text_refiner is not None
        and merged_items
        and getattr(ocr_manager, "last_provider_name", None) != "AiOcrClient"
    ):
        try:
            merged_items = text_refiner.refine_items(image_path, items=merged_items)
        except Exception as e:
            logger.warning("AI OCR text refinement failed: %s", e)
    # Multi-engine merge + AI refinement can still leave near-identical line boxes.
    # Deduplicate here to prevent stacked text boxes in PPT output.
    merged_items = _dedupe_overlapping_ocr_items(merged_items)
    merged_items = _filter_contextual_noise_items(
        merged_items, image_width=width, image_height=height
    )
    for item in merged_items:
        bbox = item.get("bbox")
        text = str(item.get("text") or "").strip()
        if not bbox or not text:
            continue

        try:
            bbox_pt = ocr_manager.convert_bbox_to_pdf_coords(
                bbox=bbox,
                image_width=width,
                image_height=height,
                page_width_pt=page_width_pt,
                page_height_pt=page_height_pt,
            )
        except Exception:
            continue

        elements.append(
            {
                "type": "text",
                "bbox_pt": bbox_pt,
                "text": text,
                "confidence": item.get("confidence"),
                "source": "ocr",
                "color": _sample_text_color(image, bbox),
                # Lightweight provenance for downstream QA/dedupe (no secrets).
                "ocr_provider": item.get("provider") or item.get("source"),
                "ocr_model": item.get("model"),
            }
        )

    return elements
