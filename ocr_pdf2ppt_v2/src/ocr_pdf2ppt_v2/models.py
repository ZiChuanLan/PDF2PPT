from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class OcrLine(BaseModel):
    text: str
    bbox: list[float] = Field(description="[x0, y0, x1, y1] in pixel coords")
    confidence: float | None = None


class PageRender(BaseModel):
    page_index: int
    width_px: int
    height_px: int
    width_pt: float
    height_pt: float
    image_path: Path


class PageResult(BaseModel):
    page_index: int
    render: PageRender
    ocr_lines: list[OcrLine]
    cleaned_image_path: Path


class ConvertResult(BaseModel):
    output_pptx: Path
    pages: int
    work_dir: Path
