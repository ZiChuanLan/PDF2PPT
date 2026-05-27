from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pymupdf

from .geometry_utils import _bbox_pt_to_px
from .layout import _layout_page_signature, _to_page_map


def _build_ocr_effective_runtime_debug(
    *,
    ocr_manager: Any,
    fallback_provider: str | None,
) -> dict[str, Any]:
    debug: dict[str, Any] = {
        "configured_provider": getattr(ocr_manager, "provider_id", None) or fallback_provider or "unknown",
        "runtime_provider": fallback_provider or "unknown",
        "provider_chain": [],
        "paddle_doc_parser": None,
    }

    try:
        providers = getattr(ocr_manager, "providers", None)
        if isinstance(providers, list):
            debug["provider_chain"] = [type(provider).__name__ for provider in providers]
    except Exception:
        pass

    try:
        primary_provider = getattr(ocr_manager, "primary_provider", None)
    except Exception:
        primary_provider = None

    if primary_provider is None:
        try:
            debug["ai_provider_disabled"] = bool(
                getattr(ocr_manager, "ai_provider_disabled", False)
            )
            debug["ai_provider_disabled_reason"] = getattr(
                ocr_manager, "ai_provider_disabled_reason", None
            )
        except Exception:
            pass
        return debug

    runtime_provider_name = type(primary_provider).__name__
    if runtime_provider_name:
        debug["runtime_provider"] = runtime_provider_name

    provider_id = str(getattr(primary_provider, "provider_id", "") or "").lower()
    model = str(getattr(primary_provider, "model", "") or "").strip()
    is_paddle_vl = "paddleocr-vl" in model.lower()
    if provider_id == "paddle" or is_paddle_vl:
        debug["paddle_doc_parser"] = {
            "provider": provider_id or None,
            "requested_model": model or None,
            "effective_model": getattr(
                primary_provider,
                "_paddle_doc_effective_model",
                None,
            ),
            "pipeline_version": getattr(
                primary_provider,
                "_paddle_doc_pipeline_version",
                None,
            ),
            "server_url": getattr(
                primary_provider,
                "_paddle_doc_server_url",
                None,
            ),
            "backend": getattr(
                primary_provider,
                "_paddle_doc_backend",
                None,
            ),
            "last_predict": getattr(
                primary_provider,
                "_paddle_doc_last_predict_debug",
                None,
            ),
            "recent_predicts": getattr(
                primary_provider,
                "_paddle_doc_recent_predict_debug",
                None,
            ),
        }

    try:
        debug["ai_provider_disabled"] = bool(
            getattr(ocr_manager, "ai_provider_disabled", False)
        )
        debug["ai_provider_disabled_reason"] = getattr(
            ocr_manager, "ai_provider_disabled_reason", None
        )
        debug["last_provider_error"] = getattr(
            ocr_manager, "last_provider_error", None
        )
        quality_notes = getattr(ocr_manager, "last_quality_notes", [])
        debug["last_quality_notes"] = (
            list(quality_notes) if isinstance(quality_notes, list) else []
        )
    except Exception:
        pass

    return debug

