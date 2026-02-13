from __future__ import annotations

import json
from pathlib import Path

from .models import ConvertResult, PageResult
from .page_cleaner import erase_text_regions
from .pdf_renderer import render_pdf_pages
from .ppt_builder import build_ppt_from_pages
from .siliconflow_ocr import SiliconFlowOcrClient


def convert_pdf_to_ppt(
    *,
    input_pdf: Path,
    output_pptx: Path,
    api_key: str,
    base_url: str,
    model: str,
    render_dpi: int = 220,
    max_pages: int | None = None,
    work_dir: Path | None = None,
) -> ConvertResult:
    if not input_pdf.exists():
        raise FileNotFoundError(f"Input PDF not found: {input_pdf}")

    root = work_dir or (output_pptx.parent / f"{output_pptx.stem}.v2-work")
    pages_dir = root / "pages"
    ocr_dir = root / "ocr"
    clean_dir = root / "clean"
    root.mkdir(parents=True, exist_ok=True)
    ocr_dir.mkdir(parents=True, exist_ok=True)

    renders = render_pdf_pages(input_pdf, pages_dir, dpi=render_dpi, max_pages=max_pages)

    client = SiliconFlowOcrClient(api_key=api_key, base_url=base_url, model=model)

    page_results: list[PageResult] = []
    for render in renders:
        ocr_lines = client.ocr_page(render)
        (ocr_dir / f"page-{render.page_index + 1:04d}.json").write_text(
            json.dumps([line.model_dump() for line in ocr_lines], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        clean_path = erase_text_regions(
            render.image_path,
            ocr_lines,
            out_path=clean_dir / f"page-{render.page_index + 1:04d}.clean.png",
        )

        page_results.append(
            PageResult(
                page_index=render.page_index,
                render=render,
                ocr_lines=ocr_lines,
                cleaned_image_path=clean_path,
            )
        )

    build_ppt_from_pages(page_results, output_pptx)

    return ConvertResult(
        output_pptx=output_pptx,
        pages=len(page_results),
        work_dir=root,
    )
