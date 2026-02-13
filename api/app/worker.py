# pyright: reportMissingImports=false

"""Background job processing.

Production mode uses RQ + Redis.
Local QA mode supports an in-memory job store (REDIS_URL=memory://) and runs
the conversion inline via threads (see jobs router).
"""

from __future__ import annotations

import json
import os
import io
import re
import copy
import inspect
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable

import redis
import pymupdf
from rq import Connection, Queue, Worker

from .config import get_settings
from .job_paths import get_job_dir
from .convert.mineru_adapter import parse_pdf_to_ir_with_mineru
from .convert.pdf_parser import parse_pdf_to_ir
from .convert.pptx_generator import generate_pptx_from_ir
from .convert.llm_adapter import AnthropicProvider, LlmLayoutService, OpenAiProvider
from .convert.ocr import AiOcrTextRefiner, create_ocr_manager, ocr_image_to_elements
from .logging_config import get_logger
from .logging_config import set_job_id, setup_logging
from .models.error import AppException, ErrorCode
from .models.job import JobStage, JobStatus
from .services.redis_service import get_redis_service


logger = get_logger(__name__)


class JobCancelledError(Exception):
    """Internal control-flow exception used to abort cancelled jobs."""


def _build_ocr_effective_runtime_debug(
    *,
    ocr_manager: Any,
    fallback_provider: str | None,
) -> dict[str, Any]:
    debug: dict[str, Any] = {
        "runtime_provider": fallback_provider or "unknown",
        "paddle_doc_parser": None,
    }

    try:
        primary_provider = getattr(ocr_manager, "primary_provider", None)
    except Exception:
        primary_provider = None

    if primary_provider is None:
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
        }

    return debug


def _apply_ai_tables(ir: dict[str, Any]) -> dict[str, Any]:
    pages = ir.get("pages")
    if not isinstance(pages, list):
        return ir

    for page in pages:
        if not isinstance(page, dict):
            continue
        grids = page.get("table_grids")
        if not isinstance(grids, list) or not grids:
            continue

        elements = page.get("elements")
        if not isinstance(elements, list):
            continue

        text_elements: list[dict[str, Any]] = []
        other_elements: list[dict[str, Any]] = []
        for el in elements:
            if not isinstance(el, dict):
                continue
            if el.get("type") == "text" and str(el.get("source") or "") == "ocr":
                text_elements.append(el)
            else:
                other_elements.append(el)

        used_text_indices: set[int] = set()
        new_tables: list[dict[str, Any]] = []

        for grid in grids:
            if not isinstance(grid, dict):
                continue
            bbox = grid.get("bbox")
            try:
                rows = int(grid.get("rows") or 0)
                cols = int(grid.get("cols") or 0)
            except Exception:
                rows, cols = 0, 0
            if (
                not isinstance(bbox, list)
                or len(bbox) != 4
                or rows <= 0
                or cols <= 0
            ):
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
            if x1 <= x0 or y1 <= y0:
                continue

            cell_w = (x1 - x0) / cols
            cell_h = (y1 - y0) / rows
            if cell_w <= 0 or cell_h <= 0:
                continue

            cell_texts: list[list[str]] = [[] for _ in range(rows * cols)]
            for idx, el in enumerate(text_elements):
                bbox_pt = el.get("bbox_pt")
                if not isinstance(bbox_pt, list) or len(bbox_pt) != 4:
                    continue
                try:
                    cx = (float(bbox_pt[0]) + float(bbox_pt[2])) / 2.0
                    cy = (float(bbox_pt[1]) + float(bbox_pt[3])) / 2.0
                except Exception:
                    continue
                if cx < x0 or cx > x1 or cy < y0 or cy > y1:
                    continue
                col = int((cx - x0) / cell_w)
                row = int((cy - y0) / cell_h)
                col = min(max(col, 0), cols - 1)
                row = min(max(row, 0), rows - 1)
                cell_texts[row * cols + col].append(str(el.get("text") or "").strip())
                used_text_indices.add(idx)

            cells: list[dict[str, Any]] = []
            for r in range(rows):
                for c in range(cols):
                    cell_bbox = [
                        x0 + c * cell_w,
                        y0 + r * cell_h,
                        x0 + (c + 1) * cell_w,
                        y0 + (r + 1) * cell_h,
                    ]
                    text = " ".join(t for t in cell_texts[r * cols + c] if t)
                    cells.append(
                        {
                            "r": r,
                            "c": c,
                            "bbox_pt": cell_bbox,
                            "text": text,
                        }
                    )

            new_tables.append(
                {
                    "type": "table",
                    "bbox_pt": [x0, y0, x1, y1],
                    "rows": rows,
                    "cols": cols,
                    "cells": cells,
                    "source": "ai",
                }
            )

        if new_tables:
            remaining_text = [
                el for idx, el in enumerate(text_elements) if idx not in used_text_indices
            ]
            page["elements"] = other_elements + remaining_text + new_tables

    return ir


def _to_page_map(ir: dict[str, Any]) -> dict[int, dict[str, Any]]:
    pages = ir.get("pages")
    if not isinstance(pages, list):
        return {}
    out: dict[int, dict[str, Any]] = {}
    for page in pages:
        if not isinstance(page, dict):
            continue
        try:
            page_index = int(page.get("page_index") or 0)
        except Exception:
            continue
        out[page_index] = page
    return out


def _layout_page_signature(page: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(page, dict):
        return {}
    return {
        "elements": page.get("elements"),
        "reading_order": page.get("reading_order"),
        "table_grids": page.get("table_grids"),
        "image_regions": page.get("image_regions"),
    }


def _count_layout_assist_page_changes(
    before_ir: dict[str, Any], after_ir: dict[str, Any]
) -> tuple[int, int]:
    before_pages = _to_page_map(before_ir)
    after_pages = _to_page_map(after_ir)
    page_indices = sorted(set(before_pages.keys()) | set(after_pages.keys()))
    pages_total = 0
    pages_changed = 0
    for page_index in page_indices:
        before_page = before_pages.get(page_index)
        after_page = after_pages.get(page_index)
        if not isinstance(before_page, dict) and not isinstance(after_page, dict):
            continue
        pages_total += 1
        if _layout_page_signature(before_page) != _layout_page_signature(after_page):
            pages_changed += 1
    return pages_changed, pages_total


def _extract_warning_suffix(
    warnings: list[Any] | None, *, prefix: str
) -> str | None:
    if not isinstance(warnings, list):
        return None
    for item in warnings:
        if not isinstance(item, str):
            continue
        if item.startswith(prefix):
            return item[len(prefix) :]
    return None


def _bbox_pt_to_px(
    bbox: Any,
    *,
    page_w_pt: float,
    page_h_pt: float,
    img_w_px: int,
    img_h_px: int,
) -> tuple[int, int, int, int] | None:
    box = _coerce_bbox_pt(bbox)
    if box is None:
        return None
    x0, y0, x1, y1 = box
    if page_w_pt <= 0 or page_h_pt <= 0 or img_w_px <= 0 or img_h_px <= 0:
        return None
    sx = float(img_w_px) / float(page_w_pt)
    sy = float(img_h_px) / float(page_h_pt)
    x0p = max(0, min(int(round(x0 * sx)), int(img_w_px - 1)))
    y0p = max(0, min(int(round(y0 * sy)), int(img_h_px - 1)))
    x1p = max(0, min(int(round(x1 * sx)), int(img_w_px)))
    y1p = max(0, min(int(round(y1 * sy)), int(img_h_px)))
    if x1p <= x0p or y1p <= y0p:
        return None
    return (x0p, y0p, x1p, y1p)


def _draw_layout_assist_overlay(
    *,
    base_img: Any,
    page: dict[str, Any] | None,
    page_w_pt: float,
    page_h_pt: float,
) -> tuple[Any, dict[str, int]]:
    from PIL import ImageDraw

    img = base_img.copy()
    draw = ImageDraw.Draw(img)
    img_w, img_h = img.size
    stats = {
        "text": 0,
        "image": 0,
        "table": 0,
        "table_grids": 0,
        "image_regions": 0,
    }

    if isinstance(page, dict):
        elements = page.get("elements")
        if isinstance(elements, list):
            for el in elements:
                if not isinstance(el, dict):
                    continue
                el_type = str(el.get("type") or "").strip().lower()
                color = (
                    (220, 53, 69)
                    if el_type == "text"
                    else (52, 152, 219)
                    if el_type == "image"
                    else (46, 204, 113)
                    if el_type == "table"
                    else (120, 120, 120)
                )
                rect = _bbox_pt_to_px(
                    el.get("bbox_pt"),
                    page_w_pt=page_w_pt,
                    page_h_pt=page_h_pt,
                    img_w_px=img_w,
                    img_h_px=img_h,
                )
                if rect is None:
                    continue
                draw.rectangle(rect, outline=color, width=2)
                if el_type in stats:
                    stats[el_type] += 1

        for grid in page.get("table_grids") or []:
            rect = _bbox_pt_to_px(
                grid.get("bbox") if isinstance(grid, dict) else None,
                page_w_pt=page_w_pt,
                page_h_pt=page_h_pt,
                img_w_px=img_w,
                img_h_px=img_h,
            )
            if rect is None:
                continue
            draw.rectangle(rect, outline=(128, 0, 255), width=2)
            stats["table_grids"] += 1

        for region in page.get("image_regions") or []:
            rect = _bbox_pt_to_px(
                region,
                page_w_pt=page_w_pt,
                page_h_pt=page_h_pt,
                img_w_px=img_w,
                img_h_px=img_h,
            )
            if rect is None:
                continue
            draw.rectangle(rect, outline=(255, 140, 0), width=2)
            stats["image_regions"] += 1

    return img, stats


def _export_layout_assist_debug_images(
    *,
    source_pdf: Path,
    before_ir: dict[str, Any],
    after_ir: dict[str, Any],
    out_dir: Path,
    render_dpi: int = 144,
    assist_status: str | None = None,
    assist_error: str | None = None,
) -> dict[str, Any]:
    from PIL import Image

    out_dir.mkdir(parents=True, exist_ok=True)
    before_pages = _to_page_map(before_ir)
    after_pages = _to_page_map(after_ir)
    page_indices = sorted(set(before_pages.keys()) | set(after_pages.keys()))
    manifest: dict[str, Any] = {
        "render_dpi": int(render_dpi),
        "assist_status": str(assist_status or "unknown"),
        "assist_error": str(assist_error or ""),
        "pages": [],
    }
    if not page_indices:
        manifest["summary"] = {"pages_exported": 0, "pages_changed": 0}
        (out_dir / "layout_assist_debug.json").write_text(
            json.dumps(manifest, ensure_ascii=True, indent=2) + "\n",
            encoding="utf-8",
        )
        return {"pages_exported": 0, "pages_changed": 0}

    doc = pymupdf.open(str(source_pdf))
    pages_changed = 0
    try:
        for page_index in page_indices:
            if page_index < 0 or page_index >= int(doc.page_count or 0):
                continue
            pdf_page = doc.load_page(page_index)
            pix = pdf_page.get_pixmap(dpi=int(max(72, render_dpi)), alpha=False)
            base_img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")

            before_page = before_pages.get(page_index)
            after_page = after_pages.get(page_index)
            page_changed = _layout_page_signature(before_page) != _layout_page_signature(
                after_page
            )
            if page_changed:
                pages_changed += 1
            page_w_pt = float(
                (
                    (after_page or {}).get("page_width_pt")
                    or (before_page or {}).get("page_width_pt")
                    or float(pdf_page.rect.width)
                )
                or float(pdf_page.rect.width)
            )
            page_h_pt = float(
                (
                    (after_page or {}).get("page_height_pt")
                    or (before_page or {}).get("page_height_pt")
                    or float(pdf_page.rect.height)
                )
                or float(pdf_page.rect.height)
            )

            before_img, before_stats = _draw_layout_assist_overlay(
                base_img=base_img,
                page=before_page,
                page_w_pt=page_w_pt,
                page_h_pt=page_h_pt,
            )
            after_img, after_stats = _draw_layout_assist_overlay(
                base_img=base_img,
                page=after_page,
                page_w_pt=page_w_pt,
                page_h_pt=page_h_pt,
            )

            before_name = f"page-{page_index:04d}.before.png"
            after_name = f"page-{page_index:04d}.after.png"
            before_path = out_dir / before_name
            after_path = out_dir / after_name
            before_img.save(before_path)
            after_img.save(after_path)

            manifest["pages"].append(
                {
                    "page_index": int(page_index),
                    "before_image": str(before_path),
                    "after_image": str(after_path),
                    "before_stats": before_stats,
                    "after_stats": after_stats,
                    "changed": bool(page_changed),
                }
            )
    finally:
        doc.close()

    manifest["summary"] = {
        "pages_exported": len(manifest.get("pages") or []),
        "pages_changed": int(pages_changed),
    }
    (out_dir / "layout_assist_debug.json").write_text(
        json.dumps(manifest, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "pages_exported": len(manifest.get("pages") or []),
        "pages_changed": int(pages_changed),
    }


def get_redis_connection() -> Any:
    """Create a Redis connection for RQ.

    NOTE: In local QA mode (REDIS_URL=memory://) this should not be used.
    """

    settings = get_settings()
    return redis.from_url(settings.redis_url)


def _job_dir(job_id: str) -> Path:
    return get_job_dir(job_id)


def _coerce_bbox_pt(value: Any) -> tuple[float, float, float, float] | None:
    if not isinstance(value, list) or len(value) != 4:
        return None
    try:
        x0, y0, x1, y1 = (
            float(value[0]),
            float(value[1]),
            float(value[2]),
            float(value[3]),
        )
    except Exception:
        return None
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def _normalize_match_text(text: str) -> str:
    cleaned = re.sub(r"\s+", "", str(text or "").lower())
    cleaned = re.sub(r"[^\w\u4e00-\u9fff]+", "", cleaned)
    return cleaned


def _bbox_overlap_ratio(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> float:
    lx0, ly0, lx1, ly1 = left
    rx0, ry0, rx1, ry1 = right
    ix0 = max(lx0, rx0)
    iy0 = max(ly0, ry0)
    ix1 = min(lx1, rx1)
    iy1 = min(ly1, ry1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = float((ix1 - ix0) * (iy1 - iy0))
    left_area = max(1.0, float((lx1 - lx0) * (ly1 - ly0)))
    right_area = max(1.0, float((rx1 - rx0) * (ry1 - ry0)))
    return float(inter) / float(min(left_area, right_area))


def _bbox_center_distance_ratio(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
    *,
    page_w_pt: float,
    page_h_pt: float,
) -> float:
    lcx = (left[0] + left[2]) / 2.0
    lcy = (left[1] + left[3]) / 2.0
    rcx = (right[0] + right[2]) / 2.0
    rcy = (right[1] + right[3]) / 2.0
    dist = float(((lcx - rcx) ** 2 + (lcy - rcy) ** 2) ** 0.5)
    diag = max(1.0, float((page_w_pt**2 + page_h_pt**2) ** 0.5))
    return dist / diag


def _apply_mineru_hybrid_ocr_alignment(
    ir: dict[str, Any],
    *,
    source_pdf: Path,
    artifacts_dir: Path,
    ocr_render_dpi: int,
    ocr_provider: str | None,
    ocr_baidu_app_id: str | None,
    ocr_baidu_api_key: str | None,
    ocr_baidu_secret_key: str | None,
    ocr_tesseract_min_confidence: float | None,
    ocr_tesseract_language: str | None,
    ocr_ai_provider: str | None = None,
    ocr_strict_mode: bool = False,
) -> dict[str, Any]:
    pages = ir.get("pages")
    if not isinstance(pages, list) or not pages:
        return ir

    provider_id = (ocr_provider or "auto").strip().lower()
    if provider_id in {"paddle-local", "local_paddle"}:
        provider_id = "paddle_local"
    if provider_id in {"aiocr", "ai", "remote", "paddle"}:
        provider_id = "auto"
    if provider_id not in {"auto", "baidu", "tesseract", "local", "paddle", "paddle_local"}:
        provider_id = "auto"

    try:
        ocr_manager = create_ocr_manager(
            provider=provider_id,
            ai_provider=ocr_ai_provider,
            ai_api_key=None,
            ai_base_url=None,
            ai_model=None,
            baidu_app_id=ocr_baidu_app_id,
            baidu_api_key=ocr_baidu_api_key,
            baidu_secret_key=ocr_baidu_secret_key,
            tesseract_min_confidence=ocr_tesseract_min_confidence,
            tesseract_language=ocr_tesseract_language or "chi_sim+eng",
            strict_no_fallback=bool(ocr_strict_mode),
            allow_paddle_model_downgrade=not bool(ocr_strict_mode),
        )
    except Exception as e:
        ir.setdefault("warnings", []).append(f"mineru_hybrid_ocr_init_failed:{e!s}")
        logger.warning("MinerU hybrid OCR init failed: %s", e)
        return ir

    ocr_dir = artifacts_dir / "mineru_hybrid_ocr"
    ocr_dir.mkdir(parents=True, exist_ok=True)

    matched_total = 0
    mineru_text_total = 0
    pages_used = 0

    try:
        doc = pymupdf.open(str(source_pdf))
    except Exception as e:
        ir.setdefault("warnings", []).append(f"mineru_hybrid_ocr_open_pdf_failed:{e!s}")
        logger.warning("MinerU hybrid OCR failed to open source PDF: %s", e)
        return ir

    try:
        for page in pages:
            if not isinstance(page, dict):
                continue
            elements = page.get("elements")
            if not isinstance(elements, list) or not elements:
                continue

            page_index = int(page.get("page_index") or 0)
            page_w_pt = float(page.get("page_width_pt") or 0.0)
            page_h_pt = float(page.get("page_height_pt") or 0.0)
            if page_w_pt <= 0 or page_h_pt <= 0:
                continue

            mineru_text_indices = [
                idx
                for idx, el in enumerate(elements)
                if isinstance(el, dict)
                and el.get("type") == "text"
                and str(el.get("source") or "").strip().lower() == "mineru"
                and _coerce_bbox_pt(el.get("bbox_pt")) is not None
                and str(el.get("text") or "").strip()
            ]
            if not mineru_text_indices:
                continue

            mineru_text_indices.sort(
                key=lambda idx: (
                    float(elements[idx]["bbox_pt"][1]),
                    float(elements[idx]["bbox_pt"][0]),
                )
            )

            try:
                pdf_page = doc.load_page(page_index)
                pix = pdf_page.get_pixmap(dpi=int(max(72, ocr_render_dpi)), alpha=False)
                page_img_path = ocr_dir / f"page-{page_index:04d}.png"
                pix.save(str(page_img_path))
            except Exception as e:
                logger.warning("MinerU hybrid OCR render failed on page %s: %s", page_index, e)
                continue

            try:
                ocr_elements = ocr_image_to_elements(
                    str(page_img_path),
                    page_width_pt=page_w_pt,
                    page_height_pt=page_h_pt,
                    ocr_manager=ocr_manager,
                    text_refiner=None,
                    strict_no_fallback=bool(ocr_strict_mode),
                )
            except Exception as e:
                logger.warning("MinerU hybrid OCR failed on page %s: %s", page_index, e)
                continue

            ocr_lines = [
                el
                for el in ocr_elements
                if isinstance(el, dict)
                and el.get("type") == "text"
                and _coerce_bbox_pt(el.get("bbox_pt")) is not None
            ]
            if not ocr_lines:
                continue
            ocr_lines.sort(
                key=lambda el: (
                    float(el["bbox_pt"][1]),
                    float(el["bbox_pt"][0]),
                )
            )

            used_ocr_indices: set[int] = set()
            page_matched = 0

            for idx in mineru_text_indices:
                mineru_el = elements[idx]
                mineru_bbox = _coerce_bbox_pt(mineru_el.get("bbox_pt"))
                if mineru_bbox is None:
                    continue
                mineru_text = str(mineru_el.get("text") or "")
                mineru_norm_text = _normalize_match_text(mineru_text)

                best_idx: int | None = None
                best_score = -1.0
                best_overlap = 0.0
                best_center = 0.0
                best_text_ratio = 0.0

                for oidx, ocr_el in enumerate(ocr_lines):
                    if oidx in used_ocr_indices:
                        continue
                    ocr_bbox = _coerce_bbox_pt(ocr_el.get("bbox_pt"))
                    if ocr_bbox is None:
                        continue

                    overlap = _bbox_overlap_ratio(mineru_bbox, ocr_bbox)
                    dist_ratio = _bbox_center_distance_ratio(
                        mineru_bbox,
                        ocr_bbox,
                        page_w_pt=page_w_pt,
                        page_h_pt=page_h_pt,
                    )
                    center_score = max(0.0, 1.0 - min(1.0, dist_ratio * 2.5))

                    ocr_norm_text = _normalize_match_text(str(ocr_el.get("text") or ""))
                    if mineru_norm_text and ocr_norm_text:
                        text_ratio = SequenceMatcher(
                            None, mineru_norm_text, ocr_norm_text
                        ).ratio()
                    else:
                        text_ratio = 0.0

                    score = (0.55 * overlap) + (0.30 * text_ratio) + (0.15 * center_score)
                    if score > best_score:
                        best_idx = oidx
                        best_score = score
                        best_overlap = overlap
                        best_center = center_score
                        best_text_ratio = text_ratio

                if best_idx is None:
                    continue

                acceptable = (
                    (best_overlap >= 0.24 and best_center >= 0.40)
                    or (best_text_ratio >= 0.72 and best_center >= 0.35)
                    or (best_score >= 0.58)
                )
                if not acceptable:
                    continue

                matched_bbox = _coerce_bbox_pt(ocr_lines[best_idx].get("bbox_pt"))
                if matched_bbox is None:
                    continue
                mineru_el["bbox_pt"] = [
                    float(matched_bbox[0]),
                    float(matched_bbox[1]),
                    float(matched_bbox[2]),
                    float(matched_bbox[3]),
                ]
                used_ocr_indices.add(best_idx)
                page_matched += 1

            page.setdefault("warnings", []).append(
                f"mineru_hybrid_ocr_matched={page_matched}/{len(mineru_text_indices)}"
            )
            mineru_text_total += len(mineru_text_indices)
            matched_total += page_matched
            pages_used += 1
    finally:
        doc.close()

    ir.setdefault("warnings", []).append(
        f"mineru_hybrid_ocr=pages:{pages_used},matched:{matched_total}/{mineru_text_total}"
    )
    return ir


def process_pdf_job(
    job_id: str,
    *,
    enable_ocr: bool = False,
    text_erase_mode: str | None = None,
    enable_layout_assist: bool = True,
    layout_assist_apply_image_regions: bool = False,
    provider: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    page_start: int | None = None,
    page_end: int | None = None,
    parse_provider: str | None = None,
    mineru_api_token: str | None = None,
    mineru_base_url: str | None = None,
    mineru_model_version: str | None = None,
    mineru_enable_formula: bool | None = None,
    mineru_enable_table: bool | None = None,
    mineru_language: str | None = None,
    mineru_is_ocr: bool | None = None,
    mineru_hybrid_ocr: bool | None = None,
    ocr_provider: str | None = None,
    ocr_baidu_app_id: str | None = None,
    ocr_baidu_api_key: str | None = None,
    ocr_baidu_secret_key: str | None = None,
    ocr_tesseract_min_confidence: float | None = None,
    ocr_tesseract_language: str | None = None,
    ocr_ai_api_key: str | None = None,
    ocr_ai_provider: str | None = None,
    ocr_ai_base_url: str | None = None,
    ocr_ai_model: str | None = None,
    scanned_page_mode: str | None = None,
    ocr_ai_linebreak_assist: bool | None = None,
    ocr_strict_mode: bool | None = False,
    job_timeout: str | None = None,
) -> None:
    """RQ job handler: process a single PDF-to-PPT conversion job."""

    _ = (
        enable_ocr,
        text_erase_mode,
        enable_layout_assist,
        layout_assist_apply_image_regions,
        provider,
        api_key,
        base_url,
        model,
        page_start,
        page_end,
        parse_provider,
        mineru_api_token,
        mineru_base_url,
        mineru_model_version,
        mineru_enable_formula,
        mineru_enable_table,
        mineru_language,
        mineru_is_ocr,
        mineru_hybrid_ocr,
        ocr_provider,
        ocr_baidu_app_id,
        ocr_baidu_api_key,
        ocr_baidu_secret_key,
        ocr_tesseract_min_confidence,
        ocr_tesseract_language,
        ocr_ai_api_key,
        ocr_ai_provider,
        ocr_ai_base_url,
        ocr_ai_model,
        scanned_page_mode,
        ocr_ai_linebreak_assist,
        ocr_strict_mode,
        job_timeout,
    )
    redis_service = get_redis_service()
    set_job_id(job_id)
    settings = get_settings()
    ocr_render_dpi = int(getattr(settings, "ocr_render_dpi", 300) or 300)
    scanned_render_dpi = int(getattr(settings, "scanned_render_dpi", 200) or 200)

    job_path = _job_dir(job_id)
    input_pdf = job_path / "input.pdf"
    output_pptx = job_path / "output.pptx"
    ir_path = job_path / "ir.json"
    artifacts_dir = job_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    if redis_service.is_cancelled(job_id):
        redis_service.update_job(
            job_id,
            status=JobStatus.cancelled,
            stage=JobStage.cleanup,
            progress=100,
            message="Job cancelled",
        )
        return

    def _clean_str(value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned if cleaned else None

    def _select_provider() -> OpenAiProvider | AnthropicProvider | None:
        key = _clean_str(api_key)
        if not key:
            return None

        provider_id = (_clean_str(provider) or "openai").lower()
        if provider_id == "claude":
            return AnthropicProvider(key)

        return OpenAiProvider(
            key,
            base_url=_clean_str(base_url),
            model=_clean_str(model),
        )

    normalized_text_erase_mode = (_clean_str(text_erase_mode) or "fill").lower()
    if normalized_text_erase_mode not in {"smart", "fill"}:
        normalized_text_erase_mode = "fill"

    normalized_scanned_page_mode = (_clean_str(scanned_page_mode) or "segmented").lower()
    if normalized_scanned_page_mode in {"chunk", "chunked", "split", "blocks"}:
        normalized_scanned_page_mode = "segmented"
    if normalized_scanned_page_mode in {"page", "full", "full_page"}:
        normalized_scanned_page_mode = "fullpage"
    if normalized_scanned_page_mode not in {"segmented", "fullpage"}:
        normalized_scanned_page_mode = "segmented"

    try:
        if not input_pdf.exists():
            raise AppException(
                code=ErrorCode.INVALID_PDF,
                message="Input PDF not found",
                details={"path": str(input_pdf)},
                status_code=400,
            )

        parse_provider_id = (_clean_str(parse_provider) or "local").lower()
        if parse_provider_id not in {"local", "mineru", "v2"}:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                message="Unsupported parse provider",
                details={"parse_provider": parse_provider},
            )

        reported_progress = 0

        def _progress_in_span(
            done: int,
            total: int,
            *,
            start: int,
            end: int,
        ) -> int:
            if total <= 0:
                return int(end)
            ratio = max(0.0, min(1.0, float(done) / float(total)))
            return int(round(float(start) + (float(end - start) * ratio)))

        def _set_processing_progress(stage: JobStage, progress: int, message: str) -> None:
            nonlocal reported_progress
            if redis_service.is_cancelled(job_id):
                redis_service.update_job(
                    job_id,
                    status=JobStatus.cancelled,
                    stage=stage,
                    progress=100,
                    message="Job cancelled",
                )
                raise JobCancelledError()
            clamped = max(0, min(99, int(progress)))
            if clamped < reported_progress:
                clamped = reported_progress
            reported_progress = clamped
            redis_service.update_job(
                job_id,
                status=JobStatus.processing,
                stage=stage,
                progress=clamped,
                message=message,
            )

        def _abort_if_cancelled(*, stage: JobStage | None = None, message: str | None = None) -> None:
            if not redis_service.is_cancelled(job_id):
                return
            redis_service.update_job(
                job_id,
                status=JobStatus.cancelled,
                stage=stage or JobStage.cleanup,
                progress=100,
                message=message or "Job cancelled",
            )
            raise JobCancelledError()

        _set_processing_progress(
            JobStage.parsing,
            5,
            (
                "正在调用 MinerU 解析文档…"
                if parse_provider_id == "mineru"
                else "正在解析文档结构…"
            ),
        )
        _abort_if_cancelled(stage=JobStage.parsing, message="Job cancelled")

        legacy_v2_mode = parse_provider_id == "v2"
        if legacy_v2_mode:
            # Legacy compatibility: `parse_provider=v2` used to call a separate
            # "full-page OCR overlay" pipeline. That path duplicated logic and
            # produced unstable output quality. We now route it through the main
            # pipeline while keeping behavior similar:
            # - force OCR on
            # - prefer full-page scanned rendering mode (no image crops)
            # - force AI OCR credentials via SiliconFlow/OpenAI-compatible config
            parse_provider_id = "local"
            normalized_scanned_page_mode = "fullpage"
            enable_ocr = True

            resolved_api_key = (
                _clean_str(ocr_ai_api_key)
                or _clean_str(api_key)
                or _clean_str(getattr(settings, "siliconflow_api_key", None))
                or _clean_str(os.getenv("SILICONFLOW_API_KEY"))
            )
            resolved_base_url = (
                _clean_str(ocr_ai_base_url)
                or _clean_str(base_url)
                or _clean_str(getattr(settings, "siliconflow_base_url", None))
                or _clean_str(os.getenv("SILICONFLOW_BASE_URL"))
                or "https://api.siliconflow.cn/v1"
            )
            resolved_model = (
                _clean_str(ocr_ai_model)
                or _clean_str(model)
                or _clean_str(getattr(settings, "siliconflow_model", None))
                or _clean_str(os.getenv("SILICONFLOW_MODEL"))
                or "Pro/deepseek-ai/deepseek-ocr"
            )

            if not resolved_api_key:
                raise AppException(
                    code=ErrorCode.VALIDATION_ERROR,
                    message="Missing API key for parse_provider=v2",
                    details={
                        "hint": "Use api_key or ocr_ai_api_key, or set SILICONFLOW_API_KEY",
                    },
                    status_code=400,
                )

            ocr_provider = "aiocr"
            ocr_ai_api_key = resolved_api_key
            ocr_ai_base_url = resolved_base_url
            ocr_ai_model = resolved_model
            if not _clean_str(ocr_ai_provider):
                ocr_ai_provider = "auto"

        if parse_provider_id == "mineru":
            ir = parse_pdf_to_ir_with_mineru(
                input_pdf,
                artifacts_dir / "mineru",
                token=_clean_str(mineru_api_token),
                base_url=_clean_str(mineru_base_url),
                model_version=_clean_str(mineru_model_version) or "vlm",
                enable_formula=mineru_enable_formula,
                enable_table=mineru_enable_table,
                language=_clean_str(mineru_language),
                is_ocr=mineru_is_ocr,
                page_start=page_start,
                page_end=page_end,
                data_id=job_id,
            )
        else:
            ir = parse_pdf_to_ir(
                input_pdf,
                artifacts_dir,
                page_start=page_start,
                page_end=page_end,
            )
        # Persist parsed IR for debugging. We'll overwrite with the final IR at end.
        (job_path / "ir.parsed.json").write_text(
            json.dumps(ir, ensure_ascii=True, indent=2) + "\n", encoding="utf-8"
        )
        parsed_pages = sum(
            1 for page in (ir.get("pages") or []) if isinstance(page, dict)
        )
        _set_processing_progress(
            JobStage.parsing,
            22,
            f"文档解析完成，共 {parsed_pages} 页",
        )
        _abort_if_cancelled(stage=JobStage.parsing, message="Job cancelled")

        if parse_provider_id == "mineru" and bool(mineru_hybrid_ocr):
            _set_processing_progress(
                JobStage.ocr,
                26,
                "正在执行 MinerU 混合 OCR 定位…",
            )
            _abort_if_cancelled(stage=JobStage.ocr, message="Job cancelled")
            ir = _apply_mineru_hybrid_ocr_alignment(
                ir,
                source_pdf=input_pdf,
                artifacts_dir=artifacts_dir,
                ocr_render_dpi=int(ocr_render_dpi),
                ocr_provider=ocr_provider,
                ocr_baidu_app_id=ocr_baidu_app_id,
                ocr_baidu_api_key=ocr_baidu_api_key,
                ocr_baidu_secret_key=ocr_baidu_secret_key,
                ocr_tesseract_min_confidence=ocr_tesseract_min_confidence,
                ocr_tesseract_language=ocr_tesseract_language,
                ocr_ai_provider=ocr_ai_provider,
                ocr_strict_mode=bool(False if ocr_strict_mode is None else ocr_strict_mode),
            )
            _abort_if_cancelled(stage=JobStage.ocr, message="Job cancelled")
            _set_processing_progress(
                JobStage.ocr,
                32,
                "MinerU 混合 OCR 定位完成",
            )
            (job_path / "ir.mineru_hybrid_ocr.json").write_text(
                json.dumps(ir, ensure_ascii=True, indent=2) + "\n",
                encoding="utf-8",
            )

        # For pages without text layer, only run local OCR when no OCR output
        # already exists in IR (for example from an external parser like MinerU).
        scanned_pages_exist = any(
            isinstance(page, dict)
            and not page.get("has_text_layer")
            and not page.get("ocr_used")
            for page in (ir.get("pages") or [])
        )
        should_attempt_ocr = scanned_pages_exist and (
            bool(enable_ocr) or bool(enable_layout_assist)
        )

        if not scanned_pages_exist:
            _set_processing_progress(
                JobStage.parsing,
                30,
                "文档已有文本层，跳过 OCR 阶段",
            )
        elif not should_attempt_ocr:
            _set_processing_progress(
                JobStage.ocr,
                34,
                "检测到扫描页，但未启用 OCR，将按图片方式生成",
            )

        if should_attempt_ocr and scanned_pages_exist:
            ocr_target_pages = sum(
                1
                for page in (ir.get("pages") or [])
                if isinstance(page, dict) and not page.get("has_text_layer")
            )
            _set_processing_progress(
                JobStage.ocr,
                35,
                f"正在准备 OCR（目标 {ocr_target_pages} 页）",
            )

            try:
                # If the user didn't configure separate AI OCR credentials, reuse
                # the layout-assist OpenAI-compatible settings (when available).
                effective_ocr_ai_api_key = _clean_str(ocr_ai_api_key)
                effective_ocr_ai_provider = (_clean_str(ocr_ai_provider) or "auto").lower()
                if effective_ocr_ai_provider in {"openai_compatible", "openai-compatible"}:
                    effective_ocr_ai_provider = "openai"
                effective_ocr_ai_base_url = _clean_str(ocr_ai_base_url)
                effective_ocr_ai_model = _clean_str(ocr_ai_model)
                provider_id = (_clean_str(provider) or "openai").lower()
                if (
                    not effective_ocr_ai_api_key
                    and provider_id != "claude"
                    and _clean_str(api_key)
                ):
                    effective_ocr_ai_api_key = _clean_str(api_key)
                    effective_ocr_ai_base_url = _clean_str(base_url)
                    effective_ocr_ai_model = _clean_str(model)

                requested_ocr_provider = (_clean_str(ocr_provider) or "auto").lower()
                if requested_ocr_provider in {"remote", "ai"}:
                    requested_ocr_provider = "aiocr"
                if requested_ocr_provider in {"paddle-local", "local_paddle"}:
                    requested_ocr_provider = "paddle_local"
                # Keep explicit provider choice. `auto` remains hybrid, while
                # `aiocr` now truly means AI OCR as primary engine.
                effective_ocr_provider = requested_ocr_provider
                strict_ocr_mode = bool(False if ocr_strict_mode is None else ocr_strict_mode)

                effective_tesseract_language = (
                    _clean_str(ocr_tesseract_language) or "chi_sim+eng"
                )
                effective_tesseract_min_conf: float | None = None
                if ocr_tesseract_min_confidence is not None:
                    try:
                        effective_tesseract_min_conf = float(ocr_tesseract_min_confidence)
                    except Exception:
                        effective_tesseract_min_conf = None

                # High recall helps text erase completeness; noise can be cleaned
                # downstream. Keep conservative auto-overrides in machine/hybrid
                # modes so users don't accidentally run with eng-only + high conf.
                if (
                    effective_ocr_provider in {"auto", "tesseract", "local"}
                    and not strict_ocr_mode
                ):
                    if effective_tesseract_language.strip().lower() == "eng":
                        effective_tesseract_language = "chi_sim+eng"
                    if effective_tesseract_min_conf is None:
                        effective_tesseract_min_conf = 35.0
                    else:
                        effective_tesseract_min_conf = min(
                            float(effective_tesseract_min_conf), 35.0
                        )

                ocr_manager = create_ocr_manager(
                    provider=effective_ocr_provider,
                    ai_provider=effective_ocr_ai_provider,
                    ai_api_key=effective_ocr_ai_api_key,
                    ai_base_url=effective_ocr_ai_base_url,
                    ai_model=effective_ocr_ai_model,
                    baidu_app_id=ocr_baidu_app_id,
                    baidu_api_key=ocr_baidu_api_key,
                    baidu_secret_key=ocr_baidu_secret_key,
                    tesseract_min_confidence=effective_tesseract_min_conf,
                    tesseract_language=effective_tesseract_language,
                    strict_no_fallback=strict_ocr_mode,
                    allow_paddle_model_downgrade=not strict_ocr_mode,
                )
                # Optional: refine line texts using an AI vision model while keeping
                # bbox geometry from a bbox-accurate OCR engine (e.g. Tesseract).
                text_refiner: AiOcrTextRefiner | None = None
                linebreak_refiner: AiOcrTextRefiner | None = None
                try:
                    provider_choice = effective_ocr_provider
                    is_paddle_vl_model = "paddleocr-vl" in (
                        str(effective_ocr_ai_model or "").strip().lower()
                    )
                    text_refiner_allowed = provider_choice in {"auto", "aiocr"}
                    linebreak_refiner_allowed = provider_choice in {
                        "auto",
                        "aiocr",
                        "tesseract",
                        "local",
                        "baidu",
                        "paddle",
                        "paddle_local",
                    }
                    linebreak_requested = ocr_ai_linebreak_assist
                    linebreak_enabled = bool(linebreak_requested)
                    auto_linebreak_enabled = False
                    # PaddleOCR-VL doc_parser often returns paragraph-like bboxes.
                    # Auto-enable line-break assist (when user didn't specify)
                    # so downstream PPT rendering doesn't have to guess wraps.
                    if linebreak_requested is None and (
                        provider_choice == "paddle"
                        or (
                            provider_choice in {"aiocr", "auto"}
                            and is_paddle_vl_model
                        )
                    ):
                        linebreak_enabled = True
                        auto_linebreak_enabled = True
                    needs_refiner = text_refiner_allowed or (
                        linebreak_enabled and linebreak_refiner_allowed
                    )
                    if (
                        needs_refiner
                        and effective_ocr_ai_api_key
                    ):
                        shared_refiner = AiOcrTextRefiner(
                            api_key=effective_ocr_ai_api_key,
                            provider=effective_ocr_ai_provider,
                            base_url=effective_ocr_ai_base_url,
                            model=effective_ocr_ai_model,
                        )
                        # If the user enabled line-break assist, we can also
                        # reuse the same vision model to refine OCR texts
                        # (keeping machine bboxes) and improve transcription
                        # quality in non-AI providers.
                        text_refine_enabled = bool(text_refiner_allowed) or bool(
                            linebreak_enabled
                        )
                        if text_refine_enabled and not is_paddle_vl_model:
                            text_refiner = shared_refiner

                        if linebreak_enabled and linebreak_refiner_allowed:
                            linebreak_refiner = shared_refiner
                except Exception as e:
                    logger.warning("AI OCR text refiner setup failed: %s", e)
                    text_refiner = None
                    linebreak_refiner = None
            except Exception as e:
                # In strict mode, fail loudly. In non-strict mode we degrade
                # gracefully to image-only output if OCR cannot be set up.
                strict_setup = bool(
                    strict_ocr_mode
                    if "strict_ocr_mode" in locals()
                    else (False if ocr_strict_mode is None else ocr_strict_mode)
                )
                if strict_setup:
                    raise AppException(
                        code=ErrorCode.OCR_FAILED,
                        message=f"OCR setup failed: {e!s}",
                        details={"error": str(e)},
                    )
                logger.warning("OCR setup failed (best-effort): %s", e)
                ir.setdefault("warnings", []).append(
                    f"ocr_setup_failed_best_effort: error={e!s}"
                )
                ocr_manager = None
                text_refiner = None
                linebreak_refiner = None

            if ocr_manager is None:
                # No OCR possible; continue conversion as image-only.
                scanned_pages_exist = False

        if scanned_pages_exist and should_attempt_ocr and "ocr_manager" in locals() and ocr_manager:
            ocr_dir = artifacts_dir / "ocr"
            ocr_dir.mkdir(parents=True, exist_ok=True)
            ocr_debug: dict[str, Any] = {
                "provider_requested": (ocr_provider or "auto"),
                "provider_effective": (
                    effective_ocr_provider
                    if "effective_ocr_provider" in locals()
                    else (ocr_provider or "auto")
                ),
                "tesseract_language": (
                    effective_tesseract_language
                    if "effective_tesseract_language" in locals()
                    else ocr_tesseract_language
                ),
                "tesseract_min_confidence": (
                    effective_tesseract_min_conf
                    if "effective_tesseract_min_conf" in locals()
                    else ocr_tesseract_min_confidence
                ),
                "ocr_render_dpi": int(ocr_render_dpi),
                "scanned_render_dpi": int(scanned_render_dpi),
                "ai_ocr": {
                    "provider": (
                        effective_ocr_ai_provider
                        if "effective_ocr_ai_provider" in locals()
                        else (_clean_str(ocr_ai_provider) or "auto")
                    ),
                    "base_url": effective_ocr_ai_base_url,
                    "model": effective_ocr_ai_model,
                },
                "ai_text_refiner": {
                    "enabled": bool("text_refiner" in locals() and text_refiner),
                    "provider": (
                        effective_ocr_ai_provider
                        if "effective_ocr_ai_provider" in locals()
                        else (_clean_str(ocr_ai_provider) or "auto")
                    ),
                    "base_url": effective_ocr_ai_base_url,
                    "model": effective_ocr_ai_model,
                },
                "ai_linebreak_refiner": {
                    "enabled": bool(
                        "linebreak_refiner" in locals() and linebreak_refiner
                    ),
                    # Keep raw request so QA can tell None vs explicit false.
                    "requested": ocr_ai_linebreak_assist,
                    "auto_enabled": bool(
                        "auto_linebreak_enabled" in locals()
                        and auto_linebreak_enabled
                    ),
                    "effective": bool(
                        "linebreak_enabled" in locals() and linebreak_enabled
                    ),
                    "provider": (
                        effective_ocr_ai_provider
                        if "effective_ocr_ai_provider" in locals()
                        else (_clean_str(ocr_ai_provider) or "auto")
                    ),
                    "base_url": effective_ocr_ai_base_url,
                    "model": effective_ocr_ai_model,
                },
                "ocr_strict_mode": (
                    strict_ocr_mode
                    if "strict_ocr_mode" in locals()
                    else bool(False if ocr_strict_mode is None else ocr_strict_mode)
                ),
                "env_PATH": os.environ.get("PATH"),
                "pages": [],
            }
            ocr_debug["runtime"] = _build_ocr_effective_runtime_debug(
                ocr_manager=ocr_manager,
                fallback_provider=ocr_debug.get("provider_effective"),
            )
            try:
                import shutil

                ocr_debug["which_tesseract"] = shutil.which("tesseract")
            except Exception as e:
                ocr_debug["which_tesseract"] = f"error: {e!s}"
            try:
                import pytesseract

                ocr_debug["pytesseract_cmd"] = getattr(
                    getattr(pytesseract, "pytesseract", None),
                    "tesseract_cmd",
                    None,
                )
            except Exception as e:
                ocr_debug["pytesseract_cmd"] = f"error: {e!s}"

            doc = pymupdf.open(str(input_pdf))
            ocr_page_targets = sum(
                1
                for page in (ir.get("pages") or [])
                if isinstance(page, dict) and not page.get("has_text_layer")
            )
            ocr_page_processed = 0
            try:
                for page in ir.get("pages") or []:
                    _abort_if_cancelled(stage=JobStage.ocr, message="Job cancelled")
                    if not isinstance(page, dict):
                        continue
                    if page.get("has_text_layer"):
                        ocr_debug["pages"].append(
                            {
                                "page_index": page.get("page_index"),
                                "skipped": "has_text_layer",
                            }
                        )
                        continue

                    ocr_page_processed += 1
                    _set_processing_progress(
                        JobStage.ocr,
                        _progress_in_span(
                            ocr_page_processed - 1,
                            max(1, ocr_page_targets),
                            start=36,
                            end=68,
                        ),
                        f"OCR 识别中（第 {ocr_page_processed}/{max(1, ocr_page_targets)} 页）",
                    )
                    _abort_if_cancelled(stage=JobStage.ocr, message="Job cancelled")

                    page_index = int(page.get("page_index") or 0)
                    page_w_pt = float(page.get("page_width_pt") or 0)
                    page_h_pt = float(page.get("page_height_pt") or 0)
                    if page_w_pt <= 0 or page_h_pt <= 0:
                        ocr_debug["pages"].append(
                            {
                                "page_index": page_index,
                                "skipped": "invalid_dimensions",
                                "page_width_pt": page_w_pt,
                                "page_height_pt": page_h_pt,
                            }
                        )
                        continue

                    try:
                        pdf_page = doc.load_page(page_index)
                        pix = pdf_page.get_pixmap(dpi=int(ocr_render_dpi), alpha=False)
                    except Exception as e:
                        logger.warning(
                            "Failed to render OCR page %s: %s", page_index, e
                        )
                        ocr_debug["pages"].append(
                            {
                                "page_index": page_index,
                                "error": f"render_failed: {e!s}",
                            }
                        )
                        continue

                    image_path = ocr_dir / f"page-{page_index:04d}.png"
                    try:
                        pix.save(str(image_path))
                    except Exception as e:
                        logger.warning(
                            "Failed to save OCR image %s: %s", image_path, e
                        )
                        ocr_debug["pages"].append(
                            {
                                "page_index": page_index,
                                "error": f"image_save_failed: {e!s}",
                            }
                        )
                        continue

                    fallback_reason: str | None = None

                    try:
                        _abort_if_cancelled(stage=JobStage.ocr, message="Job cancelled")
                        ocr_elements = ocr_image_to_elements(
                            str(image_path),
                            page_width_pt=page_w_pt,
                            page_height_pt=page_h_pt,
                            ocr_manager=ocr_manager,
                            text_refiner=(text_refiner if "text_refiner" in locals() else None),
                            linebreak_refiner=(
                                linebreak_refiner
                                if "linebreak_refiner" in locals()
                                else None
                            ),
                            linebreak_assist=(
                                False
                                if ocr_ai_linebreak_assist is False
                                else (
                                    True
                                    if ("linebreak_enabled" in locals() and linebreak_enabled)
                                    else None
                                )
                            ),
                            strict_no_fallback=(
                                strict_ocr_mode
                                if "strict_ocr_mode" in locals()
                                else bool(False if ocr_strict_mode is None else ocr_strict_mode)
                            ),
                        )
                    except Exception as e:
                        cause = getattr(e, "__cause__", None)
                        details = f"{e!s}"
                        if cause is not None:
                            details = f"{details}; cause={cause!s}"
                        provider_choice = (
                            effective_ocr_provider
                            if "effective_ocr_provider" in locals()
                            else (_clean_str(ocr_provider) or "auto").lower()
                        )
                        logger.warning(
                            "OCR failed for page %s (provider=%s): %s",
                            page_index,
                            provider_choice,
                            details,
                        )

                        details_lower = details.lower()
                        nonfatal_empty_ocr = any(
                            marker in details_lower
                            for marker in (
                                "ai ocr returned no items",
                                "ai ocr returned empty elements",
                                "ai ocr returned no parseable items",
                            )
                        )

                        # Strict policy: fail fast on OCR errors.
                        # Non-strict mode is best-effort: keep the background
                        # image-only page and continue conversion.
                        strict_now = (
                            strict_ocr_mode
                            if "strict_ocr_mode" in locals()
                            else bool(False if ocr_strict_mode is None else ocr_strict_mode)
                        )
                        if nonfatal_empty_ocr:
                            if strict_now:
                                raise AppException(
                                    code=ErrorCode.OCR_FAILED,
                                    message=(
                                        f"{provider_choice.upper()} returned empty OCR result on page {page_index + 1}"
                                    ),
                                    details={
                                        "page_index": page_index,
                                        "provider": provider_choice,
                                        "reason": details,
                                    },
                                )
                            logger.warning(
                                "OCR returned empty result on page %s (provider=%s); keep background-only page",
                                page_index,
                                provider_choice,
                            )
                            page.setdefault("warnings", []).append(
                                f"ocr_empty_result: provider={provider_choice}, page={page_index + 1}"
                            )
                            ocr_debug["pages"].append(
                                {
                                    "page_index": page_index,
                                    "warning": "ocr_empty_result",
                                    "provider": provider_choice,
                                    "error": details,
                                }
                            )
                            continue

                        if strict_now:
                            provider_label = provider_choice.upper()
                            raise AppException(
                                code=ErrorCode.OCR_FAILED,
                                message=f"{provider_label} failed on page {page_index + 1}: {details}",
                                details={
                                    "page_index": page_index,
                                    "provider": provider_choice,
                                    "reason": details,
                                },
                            )

                        ocr_debug["pages"].append(
                            {
                                "page_index": page_index,
                                "error": f"ocr_failed: {details}",
                            }
                        )
                        page.setdefault("warnings", []).append(
                            f"ocr_failed_best_effort: provider={provider_choice}, page={page_index + 1}"
                        )
                        continue

                    used_provider = getattr(ocr_manager, "last_provider_name", None)

                    # Strict policy: do not switch to local Tesseract geometry
                    # unless the user explicitly selected `tesseract/local`.
                    # Keep the original provider result as-is.

                    # Debug/self-check: write an overlay image with OCR bboxes drawn
                    # on top of the rendered page. This makes coordinate issues
                    # immediately visible without opening PowerPoint.
                    overlay_path: Path | None = None
                    bbox_stats: dict[str, Any] = {}
                    try:
                        from PIL import Image, ImageDraw

                        img = Image.open(image_path).convert("RGB")
                        gray = img.convert("L")
                        W, H = img.size
                        draw = ImageDraw.Draw(img)

                        stds: list[float] = []
                        out_of_bounds = 0
                        low_variance = 0
                        low_std_threshold = 5.0

                        sx = float(W) / float(page_w_pt) if page_w_pt else 1.0
                        sy = float(H) / float(page_h_pt) if page_h_pt else 1.0

                        for el in ocr_elements or []:
                            bbox_pt = el.get("bbox_pt")
                            if not isinstance(bbox_pt, list) or len(bbox_pt) != 4:
                                continue
                            try:
                                x0, y0, x1, y1 = (
                                    float(bbox_pt[0]),
                                    float(bbox_pt[1]),
                                    float(bbox_pt[2]),
                                    float(bbox_pt[3]),
                                )
                            except Exception:
                                continue

                            x0p = int(round(x0 * sx))
                            y0p = int(round(y0 * sy))
                            x1p = int(round(x1 * sx))
                            y1p = int(round(y1 * sy))

                            if x0p < 0 or y0p < 0 or x1p > W or y1p > H:
                                out_of_bounds += 1

                            # Clamp for drawing/stat sampling.
                            x0c = max(0, min(W - 1, x0p))
                            y0c = max(0, min(H - 1, y0p))
                            x1c = max(0, min(W, x1p))
                            y1c = max(0, min(H, y1p))
                            if x1c <= x0c or y1c <= y0c:
                                continue

                            draw.rectangle(
                                [x0c, y0c, x1c, y1c], outline=(255, 0, 0), width=2
                            )

                            crop = gray.crop((x0c, y0c, x1c, y1c))
                            target_w = max(8, min(64, crop.width // 8))
                            target_h = max(8, min(64, crop.height // 8))
                            small = crop.resize((target_w, target_h))
                            pixels = list(small.getdata())
                            if not pixels:
                                continue
                            mean = sum(pixels) / len(pixels)
                            var = sum((p - mean) ** 2 for p in pixels) / len(pixels)
                            std = float(var**0.5)
                            stds.append(std)
                            if std <= low_std_threshold:
                                low_variance += 1

                        overlay_path = ocr_dir / f"page-{page_index:04d}.overlay.png"
                        img.save(overlay_path)

                        bbox_stats = {
                            "out_of_bounds": out_of_bounds,
                            "low_variance": low_variance,
                            "low_std_threshold": low_std_threshold,
                            "median_std": (
                                sorted(stds)[len(stds) // 2] if stds else None
                            ),
                        }
                    except Exception as e:
                        bbox_stats = {"overlay_error": str(e)}
                    if ocr_elements:
                        page.setdefault("elements", []).extend(ocr_elements)
                        page["ocr_used"] = True
                        # Keep has_text_layer=False for scanned PDFs so the PPTX
                        # generator can use the scanned-page strategy (background
                        # render + masking + editable overlay text).
                        ocr_debug["pages"].append(
                            {
                                "page_index": page_index,
                                "elements": len(ocr_elements),
                                "used_provider": used_provider,
                                "fallback_reason": fallback_reason,
                                "overlay_image": str(overlay_path) if overlay_path else None,
                                "bbox_stats": bbox_stats,
                            }
                        )
                    else:
                        ocr_debug["pages"].append(
                            {
                                "page_index": page_index,
                                "elements": 0,
                                "used_provider": used_provider,
                                "fallback_reason": fallback_reason,
                                "overlay_image": str(overlay_path) if overlay_path else None,
                                "bbox_stats": bbox_stats,
                            }
                        )
                _set_processing_progress(
                    JobStage.ocr,
                    68,
                    f"OCR 阶段完成（已处理 {ocr_page_processed}/{max(1, ocr_page_targets)} 页）",
                )
                _abort_if_cancelled(stage=JobStage.ocr, message="Job cancelled")
            finally:
                doc.close()
                ocr_debug["runtime"] = _build_ocr_effective_runtime_debug(
                    ocr_manager=ocr_manager,
                    fallback_provider=ocr_debug.get("provider_effective"),
                )
                (ocr_dir / "ocr_debug.json").write_text(
                    json.dumps(ocr_debug, ensure_ascii=True, indent=2) + "\n",
                    encoding="utf-8",
                )
                # Persist IR after OCR for debugging.
                (job_path / "ir.ocr.json").write_text(
                    json.dumps(ir, ensure_ascii=True, indent=2) + "\n",
                    encoding="utf-8",
                )

        llm_provider = None
        layout_assist_status = "disabled"
        layout_assist_error: str | None = None
        layout_assist_pages_changed = 0
        layout_assist_pages_total = 0
        if enable_layout_assist:
            _set_processing_progress(
                JobStage.layout_assist,
                72,
                "准备执行 AI 版式辅助…",
            )
            _abort_if_cancelled(stage=JobStage.layout_assist, message="Job cancelled")
            llm_provider = _select_provider()
            if llm_provider:
                before_ai_ir = copy.deepcopy(ir)
                _set_processing_progress(
                    JobStage.layout_assist,
                    74,
                    "AI 版式辅助处理中…",
                )
                _abort_if_cancelled(stage=JobStage.layout_assist, message="Job cancelled")
                ir = LlmLayoutService(llm_provider).enhance_ir(
                    ir,
                    layout_mode="assist",
                    force_ai=True,
                    allow_image_regions=bool(layout_assist_apply_image_regions),
                )
                _abort_if_cancelled(stage=JobStage.layout_assist, message="Job cancelled")
                ir = _apply_ai_tables(ir)
                layout_assist_pages_changed, layout_assist_pages_total = (
                    _count_layout_assist_page_changes(before_ai_ir, ir)
                )
                layout_assist_error = _extract_warning_suffix(
                    ir.get("warnings") if isinstance(ir.get("warnings"), list) else None,
                    prefix="layout_assist_failed:",
                )
                if layout_assist_error:
                    layout_assist_status = "failed"
                    logger.warning(
                        "Layout assist failed and fell back: job=%s error=%s",
                        job_id,
                        layout_assist_error,
                    )
                elif layout_assist_pages_changed > 0:
                    layout_assist_status = "applied"
                    logger.info(
                        "Layout assist applied: job=%s changed_pages=%s/%s",
                        job_id,
                        layout_assist_pages_changed,
                        layout_assist_pages_total,
                    )
                else:
                    layout_assist_status = "no_change"
                    logger.info(
                        "Layout assist produced no structural changes: job=%s",
                        job_id,
                    )
                ir.setdefault("warnings", []).append(
                    f"layout_assist_status={layout_assist_status}"
                )
                ir.setdefault("warnings", []).append(
                    f"layout_assist_pages_changed={layout_assist_pages_changed}/{layout_assist_pages_total}"
                )
                # Persist IR after layout assist for debugging.
                (job_path / "ir.ai.json").write_text(
                    json.dumps(ir, ensure_ascii=True, indent=2) + "\n",
                    encoding="utf-8",
                )
                try:
                    debug_result = _export_layout_assist_debug_images(
                        source_pdf=input_pdf,
                        before_ir=before_ai_ir,
                        after_ir=ir,
                        out_dir=artifacts_dir / "layout_assist",
                        render_dpi=max(96, int(scanned_render_dpi)),
                        assist_status=layout_assist_status,
                        assist_error=layout_assist_error,
                    )
                    ir.setdefault("warnings", []).append(
                        f"layout_assist_debug_pages={int(debug_result.get('pages_exported') or 0)}"
                    )
                    ir.setdefault("warnings", []).append(
                        f"layout_assist_debug_changed_pages={int(debug_result.get('pages_changed') or 0)}"
                    )
                except Exception as e:
                    logger.warning("Failed to export layout assist debug images: %s", e)
                _set_processing_progress(
                    JobStage.layout_assist,
                    82,
                    f"AI 版式辅助完成（变更 {layout_assist_pages_changed}/{layout_assist_pages_total} 页）",
                )
            else:
                layout_assist_status = "skipped_missing_provider"
                logger.info(
                    "Layout assist skipped (missing API key or provider): job=%s",
                    job_id,
                )
                _set_processing_progress(
                    JobStage.layout_assist,
                    80,
                    "未配置可用 AI 提供方，已跳过版式辅助",
                )
            _abort_if_cancelled(stage=JobStage.layout_assist, message="Job cancelled")

        ppt_page_total = sum(
            1 for page in (ir.get("pages") or []) if isinstance(page, dict)
        )
        _set_processing_progress(
            JobStage.pptx_generating,
            84,
            f"开始生成 PPT（共 {ppt_page_total} 页）",
        )
        _abort_if_cancelled(stage=JobStage.pptx_generating, message="Job cancelled")

        def _on_ppt_page_done(done: int, total: int) -> None:
            _set_processing_progress(
                JobStage.pptx_generating,
                _progress_in_span(done, max(1, total), start=85, end=97),
                f"正在生成 PPT 页面（{done}/{max(1, total)}）",
            )
            _abort_if_cancelled(stage=JobStage.pptx_generating, message="Job cancelled")

        generator_params = inspect.signature(generate_pptx_from_ir).parameters
        missing_generator_features: list[str] = []
        if "text_erase_mode" not in generator_params:
            missing_generator_features.append("text_erase_mode")
        if "progress_callback" not in generator_params:
            missing_generator_features.append("progress_callback")
        worker_compat_mode = bool(missing_generator_features)
        generator_kwargs: dict[str, Any] = {
            "artifacts_dir": artifacts_dir,
            "scanned_render_dpi": int(scanned_render_dpi),
        }
        if "text_erase_mode" in generator_params:
            generator_kwargs["text_erase_mode"] = normalized_text_erase_mode
        if "scanned_page_mode" in generator_params:
            generator_kwargs["scanned_page_mode"] = normalized_scanned_page_mode
        if "progress_callback" in generator_params:
            generator_kwargs["progress_callback"] = _on_ppt_page_done

        if worker_compat_mode:
            compat_features = ",".join(missing_generator_features)
            ir.setdefault("warnings", []).append(
                f"worker_compat_mode_missing_features={compat_features}"
            )
            _set_processing_progress(
                JobStage.pptx_generating,
                84,
                "检测到 worker 兼容模式（旧转换内核），建议升级 worker",
            )
            _abort_if_cancelled(stage=JobStage.pptx_generating, message="Job cancelled")

        _abort_if_cancelled(stage=JobStage.pptx_generating, message="Job cancelled")
        generate_pptx_from_ir(
            ir,
            output_pptx,
            **generator_kwargs,
        )
        _set_processing_progress(
            JobStage.packaging,
            98,
            (
                "正在打包转换结果…（兼容模式，建议升级 worker）"
                if worker_compat_mode
                else "正在打包转换结果…"
            ),
        )
        _abort_if_cancelled(stage=JobStage.packaging, message="Job cancelled")
        # Persist final IR so users can inspect what the generator saw.
        ir_path.write_text(
            json.dumps(ir, ensure_ascii=True, indent=2) + "\n", encoding="utf-8"
        )

        redis_service.update_job(
            job_id,
            status=JobStatus.completed,
            stage=JobStage.done,
            progress=100,
            message=(
                "转换完成，可下载 PPTX（兼容模式，建议升级 worker）"
                if worker_compat_mode
                else "转换完成，可下载 PPTX"
            ),
        )

    except JobCancelledError:
        logger.info("Job %s cancelled", job_id)
        return
    except AppException as e:
        logger.warning(f"Job {job_id} failed: {e.code} {e.message}")
        redis_service.update_job(
            job_id,
            status=JobStatus.failed,
            stage=JobStage.cleanup,
            progress=100,
            message=e.message,
            error={"code": e.code, "message": e.message, "details": e.details},
        )
        return
    except Exception as e:
        logger.exception(f"Job {job_id} crashed: {e!s}")
        redis_service.update_job(
            job_id,
            status=JobStatus.failed,
            stage=JobStage.cleanup,
            progress=100,
            message="Conversion failed",
            error={"code": ErrorCode.INTERNAL_ERROR.value, "message": str(e)},
        )
        return


def run_worker() -> None:
    """Run the RQ worker."""

    setup_logging(os.getenv("LOG_LEVEL", "INFO"))
    settings = get_settings()
    if str(settings.redis_url).startswith("memory://"):
        raise RuntimeError("RQ worker is not supported with REDIS_URL=memory://")

    conn = redis.from_url(settings.redis_url)
    with Connection(conn):
        # Do not log full job kwargs; requests carry user API keys (OpenAI/Baidu/etc).
        worker = Worker(Queue("default"), log_job_description=False)
        worker.work()


if __name__ == "__main__":
    run_worker()
