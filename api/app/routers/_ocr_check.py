# pyright: reportMissingImports=false

"""AI OCR capability check helpers for job endpoints."""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from ..models.job import (
    AiOcrCheckResponse,
    AiOcrCheckResult,
    AiOcrCheckSampleItem,
)
from ..convert.ocr import (
    _coerce_bbox_xyxy,
    create_remote_ocr_client,
)

_AI_OCR_PROBE_FONT_CACHE: dict[tuple[int, bool], tuple[Any, bool]] = {}


def load_ai_ocr_probe_font(*, size_px: int, prefer_cjk: bool) -> tuple[Any, bool]:
    key = (int(max(8, size_px)), bool(prefer_cjk))
    cached = _AI_OCR_PROBE_FONT_CACHE.get(key)
    if cached is not None:
        return cached

    from ..utils.fonts import load_pil_font

    font, is_fallback = load_pil_font(
        size_px=size_px,
        prefer_cjk=prefer_cjk,
    )
    result: tuple[Any, bool] = (font, is_fallback)
    _AI_OCR_PROBE_FONT_CACHE[key] = result
    return result


def create_ai_ocr_probe_image() -> Path:
    """Create a synthetic OCR probe image with large, low-risk text blocks."""
    fd, raw_path = tempfile.mkstemp(prefix="ai-ocr-probe-", suffix=".png")
    os.close(fd)
    out = Path(raw_path)

    image = Image.new("RGB", (1440, 960), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    title_font, title_fallback = load_ai_ocr_probe_font(size_px=56, prefer_cjk=False)
    body_font, body_fallback = load_ai_ocr_probe_font(size_px=42, prefer_cjk=False)

    draw.rounded_rectangle(
        (48, 48, 1392, 912),
        radius=28,
        outline=(224, 228, 236),
        width=4,
        fill=(255, 255, 255),
    )
    draw.text((104, 116), "PPT OpenCode OCR Check", font=title_font, fill=(18, 18, 18))
    draw.text((104, 260), "Vision OCR Probe 2026", font=body_font, fill=(18, 18, 18))
    draw.text(
        (104, 400),
        "Invoice ID: A-2048-17   Total: 97.5",
        font=body_font,
        fill=(18, 18, 18),
    )
    draw.text(
        (104, 540),
        "Email: hello@example.com",
        font=body_font,
        fill=(18, 18, 18),
    )
    draw.text(
        (104, 680),
        "Status: Ready / bbox check",
        font=body_font,
        fill=(18, 18, 18),
    )

    if title_fallback or body_fallback:
        image = image.resize((2160, 1440), Image.Resampling.BICUBIC)

    image.save(out, format="PNG")
    return out


def truncate_error(value: Exception | str, *, limit: int = 400) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


def run_ai_ocr_capability_check(
    *,
    provider: str | None,
    api_key: str,
    base_url: str | None,
    model: str,
    ocr_ai_chain_mode: str | None = None,
    ocr_ai_layout_model: str | None = None,
    ocr_ai_prompt_preset: str | None = None,
    ocr_ai_direct_prompt_override: str | None = None,
    ocr_ai_layout_block_prompt_override: str | None = None,
    ocr_ai_image_region_prompt_override: str | None = None,
    ocr_paddle_vl_docparser_max_side_px: int | None = None,
    ocr_ai_block_concurrency: int | None = None,
    ocr_ai_requests_per_minute: int | None = None,
    ocr_ai_tokens_per_minute: int | None = None,
    ocr_ai_max_retries: int | None = None,
) -> AiOcrCheckResponse:
    """Run AI OCR capability check and validate whether bbox items are returned."""
    start = time.perf_counter()
    image_path = create_ai_ocr_probe_image()
    normalized_provider = (provider or "auto").strip() or "auto"
    normalized_base_url = (base_url or "").strip() or None
    normalized_model = model.strip()

    try:
        effective_block_concurrency = ocr_ai_block_concurrency
        if ocr_ai_chain_mode == "layout_block" and effective_block_concurrency is None:
            effective_block_concurrency = 1

        client = create_remote_ocr_client(
            requested_provider="aiocr",
            ai_api_key=api_key.strip(),
            ai_provider=normalized_provider,
            ai_base_url=normalized_base_url,
            ai_model=normalized_model,
            route_kind=ocr_ai_chain_mode,
            ai_layout_model=ocr_ai_layout_model,
            prompt_preset=ocr_ai_prompt_preset,
            direct_prompt_override=ocr_ai_direct_prompt_override,
            layout_block_prompt_override=ocr_ai_layout_block_prompt_override,
            image_region_prompt_override=ocr_ai_image_region_prompt_override,
            paddle_doc_max_side_px=ocr_paddle_vl_docparser_max_side_px,
            layout_block_max_concurrency=effective_block_concurrency,
            request_rpm_limit=ocr_ai_requests_per_minute,
            request_tpm_limit=ocr_ai_tokens_per_minute,
            request_max_retries=ocr_ai_max_retries,
        )
        raw_items: list[dict[str, Any]] = client.ocr_image(str(image_path))

        valid_bbox_items = 0
        sample_items: list[AiOcrCheckSampleItem] = []
        for item in raw_items or []:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()
            bbox = _coerce_bbox_xyxy(item.get("bbox"))
            if not text or not bbox:
                continue
            if float(bbox[2]) <= float(bbox[0]) or float(bbox[3]) <= float(bbox[1]):
                continue
            valid_bbox_items += 1
            if len(sample_items) >= 3:
                continue
            confidence: float | None = None
            try:
                conf_raw = item.get("confidence")
                if conf_raw is not None:
                    confidence = float(conf_raw)
            except Exception:
                confidence = None
            sample_items.append(
                AiOcrCheckSampleItem(
                    text=text[:120],
                    bbox=[
                        float(bbox[0]),
                        float(bbox[1]),
                        float(bbox[2]),
                        float(bbox[3]),
                    ],
                    confidence=confidence,
                )
            )

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        ready = valid_bbox_items > 0
        message = (
            "模型可返回有效 bbox OCR 结果" if ready else "模型未返回有效 bbox OCR 结果"
        )
        check = AiOcrCheckResult(
            provider=normalized_provider,
            model=normalized_model,
            base_url=normalized_base_url,
            route_kind=getattr(client, "route_kind", None),
            elapsed_ms=elapsed_ms,
            items_count=len(raw_items or []),
            valid_bbox_items=valid_bbox_items,
            ready=ready,
            message=message,
            sample_items=sample_items,
        )
        return AiOcrCheckResponse(ok=ready, check=check)
    except Exception as e:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        check = AiOcrCheckResult(
            provider=normalized_provider,
            model=normalized_model,
            base_url=normalized_base_url,
            route_kind=None,
            elapsed_ms=elapsed_ms,
            items_count=0,
            valid_bbox_items=0,
            ready=False,
            message="模型调用失败",
            error=truncate_error(e),
            sample_items=[],
        )
        return AiOcrCheckResponse(ok=False, check=check)
    finally:
        try:
            image_path.unlink(missing_ok=True)
        except Exception:
            pass
