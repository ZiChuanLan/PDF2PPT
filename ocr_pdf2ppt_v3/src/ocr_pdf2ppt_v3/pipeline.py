from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from PIL import Image

from .geometry import clamp_bbox_px
from .models import ConvertResult, OcrLine, PageResult, VisualRegion
from .page_cleaner import erase_text_and_image_regions
from .paddle_doc_parser_ocr import PaddleDocParserOcrClient
from .pdf_renderer import render_pdf_pages
from .ppt_builder import build_ppt_from_pages
from .quality_gate import assess_quality, sanitize_lines
from .siliconflow_ocr import SiliconFlowOcrClient

OcrBackend = Literal["auto", "openai_chat", "paddle_doc_parser"]


def _resolve_ocr_backend(*, requested: OcrBackend, model: str) -> OcrBackend:
    if requested != "auto":
        return requested
    model_lower = str(model or "").strip().lower()
    if "paddleocr-vl" in model_lower:
        return "paddle_doc_parser"
    return "openai_chat"


def _build_ocr_client(
    *,
    api_key: str,
    base_url: str,
    model: str,
    backend: OcrBackend,
):
    resolved = _resolve_ocr_backend(requested=backend, model=model)
    if resolved == "paddle_doc_parser":
        return PaddleDocParserOcrClient(
            api_key=api_key,
            base_url=base_url,
            model=model,
        ), resolved
    return SiliconFlowOcrClient(
        api_key=api_key,
        base_url=base_url,
        model=model,
    ), resolved


def _sanitize_image_regions(
    *,
    regions: list[VisualRegion],
    width: int,
    height: int,
) -> list[VisualRegion]:
    page_area = float(max(1, width * height))
    cleaned: list[VisualRegion] = []
    dedup: set[tuple[int, int, int, int]] = set()

    for region in regions:
        bbox = clamp_bbox_px([float(v) for v in region.bbox], width=width, height=height)
        if bbox is None:
            continue
        x0, y0, x1, y1 = bbox
        box_w = max(1.0, x1 - x0)
        box_h = max(1.0, y1 - y0)
        area_ratio = (box_w * box_h) / page_area

        if area_ratio < 0.0025:
            continue
        if area_ratio > 0.82:
            continue
        if box_h / max(1.0, float(height)) < 0.03:
            continue

        confidence = region.confidence
        if confidence is not None and float(confidence) < 0.35:
            continue

        label = (region.label or "").strip().lower()
        if "text" in label:
            continue

        key = (int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1)))
        if key in dedup:
            continue
        dedup.add(key)
        cleaned.append(
            VisualRegion(
                bbox=[x0, y0, x1, y1],
                label=region.label,
                confidence=region.confidence,
                source="ai_layout",
                crop_path=None,
            )
        )

    cleaned.sort(key=lambda item: (float(item.bbox[1]), float(item.bbox[0])))
    return cleaned


def _crop_image_regions(
    *,
    page_image_path: Path,
    regions: list[VisualRegion],
    out_dir: Path,
    page_index: int,
) -> list[VisualRegion]:
    if not regions:
        return []
    out_dir.mkdir(parents=True, exist_ok=True)

    image = Image.open(page_image_path).convert("RGB")
    width, height = image.size

    enriched: list[VisualRegion] = []
    for idx, region in enumerate(regions, start=1):
        bbox = clamp_bbox_px([float(v) for v in region.bbox], width=width, height=height)
        if bbox is None:
            continue
        x0, y0, x1, y1 = bbox
        ix0 = max(0, int(round(x0)))
        iy0 = max(0, int(round(y0)))
        ix1 = min(width, int(round(x1)))
        iy1 = min(height, int(round(y1)))
        if ix1 <= ix0 or iy1 <= iy0:
            continue

        crop = image.crop((ix0, iy0, ix1, iy1))
        crop_path = out_dir / f"page-{page_index + 1:04d}.img-{idx:03d}.png"
        crop.save(crop_path)

        enriched.append(
            VisualRegion(
                bbox=[x0, y0, x1, y1],
                label=region.label,
                confidence=region.confidence,
                source="ai_layout",
                crop_path=crop_path,
            )
        )

    return enriched


def convert_pdf_to_ppt(
    *,
    input_pdf: Path,
    output_pptx: Path,
    api_key: str,
    base_url: str,
    model: str,
    ocr_backend: OcrBackend = "auto",
    render_dpi: int = 220,
    max_pages: int | None = None,
    work_dir: Path | None = None,
) -> ConvertResult:
    if not input_pdf.exists():
        raise FileNotFoundError(f"Input PDF not found: {input_pdf}")

    root = work_dir or (output_pptx.parent / f"{output_pptx.stem}.v3-work")
    pages_dir = root / "pages"
    ocr_dir = root / "ocr"
    image_regions_dir = root / "image_regions"
    clean_dir = root / "clean"
    debug_dir = root / "debug"
    root.mkdir(parents=True, exist_ok=True)
    ocr_dir.mkdir(parents=True, exist_ok=True)
    image_regions_dir.mkdir(parents=True, exist_ok=True)
    debug_dir.mkdir(parents=True, exist_ok=True)

    renders = render_pdf_pages(input_pdf, pages_dir, dpi=render_dpi, max_pages=max_pages)

    client, resolved_backend = _build_ocr_client(
        api_key=api_key,
        base_url=base_url,
        model=model,
        backend=ocr_backend,
    )

    page_results: list[PageResult] = []
    debug_pages: list[dict[str, object]] = []

    for render in renders:
        ai_primary_raw = client.ocr_page(render, pass_mode="primary")
        ai_primary_lines = sanitize_lines(
            lines=ai_primary_raw,
            width=render.width_px,
            height=render.height_px,
            source="ai_primary",
        )

        need_retry, quality_reason, quality_stats = assess_quality(
            lines=ai_primary_lines,
            width=render.width_px,
            height=render.height_px,
        )

        final_lines: list[OcrLine] = ai_primary_lines
        ocr_source = "ai_primary"
        fallback_reason: str | None = None
        ai_retry_raw: list[OcrLine] = []
        ai_retry_lines: list[OcrLine] = []

        if need_retry:
            fallback_reason = f"primary_{quality_reason}"
            ai_retry_raw = client.ocr_page(render, pass_mode="retry")
            ai_retry_lines = sanitize_lines(
                lines=ai_retry_raw,
                width=render.width_px,
                height=render.height_px,
                source="ai_retry",
            )

            retry_need_empty, retry_reason, retry_stats = assess_quality(
                lines=ai_retry_lines,
                width=render.width_px,
                height=render.height_px,
            )

            if ai_retry_lines and not retry_need_empty:
                final_lines = ai_retry_lines
                ocr_source = "ai_retry"
                quality_stats = retry_stats
            elif ai_retry_lines and retry_reason != "empty":
                final_lines = ai_retry_lines
                ocr_source = "ai_retry"
                quality_stats = retry_stats
                fallback_reason = f"{fallback_reason}_retry_{retry_reason}"
            else:
                final_lines = []
                ocr_source = "empty"
                fallback_reason = f"{fallback_reason}_retry_empty"

        layout_raw: list[VisualRegion] = []
        try:
            layout_raw = client.detect_layout_regions(render)
        except Exception:
            layout_raw = []

        layout_regions = _sanitize_image_regions(
            regions=layout_raw,
            width=render.width_px,
            height=render.height_px,
        )
        layout_regions = _crop_image_regions(
            page_image_path=render.image_path,
            regions=layout_regions,
            out_dir=image_regions_dir,
            page_index=render.page_index,
        )

        ocr_json_path = ocr_dir / f"page-{render.page_index + 1:04d}.json"
        ocr_json_path.write_text(
            json.dumps([line.model_dump() for line in final_lines], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        layout_json_path = ocr_dir / f"page-{render.page_index + 1:04d}.layout.json"
        layout_json_path.write_text(
            json.dumps([region.model_dump(mode="json") for region in layout_regions], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        clean_path = erase_text_and_image_regions(
            render.image_path,
            final_lines,
            layout_regions,
            out_path=clean_dir / f"page-{render.page_index + 1:04d}.clean.png",
            padding_px=1,
            inpaint_radius=1.6,
            inpaint_method="ns",
            erase_image_regions=False,
        )

        page_result = PageResult(
            page_index=render.page_index,
            render=render,
            ocr_lines=final_lines,
            image_regions=layout_regions,
            cleaned_image_path=clean_path,
            ocr_source=ocr_source,
            fallback_reason=fallback_reason,
            quality_stats=quality_stats,
        )
        page_results.append(page_result)

        debug_pages.append(
            {
                "page_index": render.page_index + 1,
                "ai_primary_raw_count": len(ai_primary_raw),
                "ai_primary_clean_count": len(ai_primary_lines),
                "ai_retry_raw_count": len(ai_retry_raw),
                "ai_retry_clean_count": len(ai_retry_lines),
                "layout_raw_count": len(layout_raw),
                "layout_clean_count": len(layout_regions),
                "final_count": len(final_lines),
                "ocr_source": ocr_source,
                "fallback_reason": fallback_reason,
                "quality_stats": quality_stats.model_dump(),
                "ocr_json": str(ocr_json_path),
                "layout_json": str(layout_json_path),
                "clean_image": str(clean_path),
            }
        )

    build_ppt_from_pages(page_results, output_pptx)

    fallback_pages = sum(1 for page in page_results if page.ocr_source == "ai_retry")
    empty_pages = sum(1 for page in page_results if page.ocr_source == "empty")

    debug_payload = {
        "version": "v3",
        "provider": "siliconflow",
        "base_url": base_url,
        "model": model,
        "ocr_backend": resolved_backend,
        "render_dpi": int(render_dpi),
        "summary": {
            "pages": len(page_results),
            "fallback_pages": fallback_pages,
            "empty_pages": empty_pages,
        },
        "pages": debug_pages,
    }
    debug_json = debug_dir / "v3_debug.json"
    debug_json.write_text(
        json.dumps(debug_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return ConvertResult(
        output_pptx=output_pptx,
        pages=len(page_results),
        work_dir=root,
        fallback_pages=fallback_pages,
        empty_pages=empty_pages,
        debug_json=debug_json,
    )
