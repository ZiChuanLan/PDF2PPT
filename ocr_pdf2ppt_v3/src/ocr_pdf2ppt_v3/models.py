from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class OcrLine(BaseModel):
    text: str
    bbox: list[float] = Field(description="[x0, y0, x1, y1] in pixel coords")
    confidence: float | None = None
    source: Literal["ai_primary", "ai_retry"] = "ai_primary"
    group_id: str | None = None
    group_bbox: list[float] | None = Field(default=None, description="Optional group bbox in pixel coords")


class VisualRegion(BaseModel):
    bbox: list[float] = Field(description="[x0, y0, x1, y1] in pixel coords")
    label: str | None = None
    confidence: float | None = None
    source: Literal["ai_layout"] = "ai_layout"
    crop_path: Path | None = None


class PageRender(BaseModel):
    page_index: int
    width_px: int
    height_px: int
    width_pt: float
    height_pt: float
    image_path: Path


class OcrQualityStats(BaseModel):
    total: int = 0
    low_conf: int = 0
    noisy: int = 0
    too_wide: int = 0
    too_tall: int = 0
    coverage: float = 0.0


class PageResult(BaseModel):
    page_index: int
    render: PageRender
    ocr_lines: list[OcrLine]
    image_regions: list[VisualRegion] = []
    cleaned_image_path: Path
    ocr_source: Literal["ai_primary", "ai_retry", "empty"]
    fallback_reason: str | None = None
    quality_stats: OcrQualityStats | None = None


class ConvertResult(BaseModel):
    output_pptx: Path
    pages: int
    work_dir: Path
    fallback_pages: int = 0
    empty_pages: int = 0
    debug_json: Path
