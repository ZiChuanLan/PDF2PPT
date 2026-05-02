# pyright: reportMissingImports=false, reportMissingTypeArgument=false

"""Structured job configuration schema.

This module defines Pydantic models that replace the 60+ flat Form() parameters
currently used in the job creation endpoint. The structured config is designed to:

1. Group related settings into logical sub-models
2. Provide sensible defaults
3. Enable JSON-based API (v2 endpoint) alongside the legacy Form-based API
4. Support conversion to the flat kwargs format expected by the worker

Usage:
    config = JobConfig.model_validate(json_body)
    kwargs = config.to_worker_kwargs()
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AiProviderConfig(BaseModel):
    """AI provider credentials and connection settings.

    Used for both layout-assist LLM and OCR AI providers.
    All providers must be OpenAI-compatible (base_url + api_key + model).
    """

    model_config = ConfigDict(populate_by_name=True)

    base_url: str | None = Field(
        None,
        description="OpenAI-compatible API base URL",
    )
    api_key: str | None = Field(
        None,
        description="API key for the AI provider",
    )
    model: str | None = Field(
        None,
        description="Model identifier (e.g. gpt-4o-mini, Qwen/Qwen2.5-VL-72B-Instruct)",
    )


class LlmConfig(BaseModel):
    """LLM configuration for layout assist (PPT generation)."""

    model_config = ConfigDict(populate_by_name=True)

    provider: Literal["openai", "claude"] = Field(
        "openai",
        description="LLM provider identifier",
    )
    api_key: str | None = Field(
        None,
        description="Optional API key for layout assist LLM",
    )
    base_url: str | None = Field(
        None,
        description="Optional OpenAI-compatible base URL for layout assist",
    )
    model: str | None = Field(
        None,
        description="Optional model identifier for layout assist",
    )


class BaiduOcrConfig(BaseModel):
    """Baidu OCR credentials."""

    model_config = ConfigDict(populate_by_name=True)

    app_id: str | None = Field(None, description="Baidu OCR App ID")
    api_key: str | None = Field(None, description="Baidu OCR API key")
    secret_key: str | None = Field(None, description="Baidu OCR secret key")


class TesseractConfig(BaseModel):
    """Tesseract OCR settings."""

    model_config = ConfigDict(populate_by_name=True)

    language: str | None = Field(
        None,
        description="Tesseract language code (e.g. eng, chi_sim)",
    )
    min_confidence: float | None = Field(
        None,
        description="Minimum confidence threshold (0-100)",
    )


class OcrAiConfig(BaseModel):
    """AI OCR specific configuration.

    This groups all AI OCR settings that were previously scattered across
    14+ separate Form fields.
    """

    model_config = ConfigDict(populate_by_name=True)

    provider: Literal["auto", "openai", "siliconflow", "deepseek", "ppio", "novita"] = (
        Field("auto", description="AI OCR vendor adapter")
    )
    api_key: str | None = Field(None, description="AI OCR API key")
    base_url: str | None = Field(None, description="AI OCR base URL")
    model: str | None = Field(None, description="AI OCR model name")
    chain_mode: Literal["direct", "doc_parser", "layout_block"] = Field(
        "direct",
        description="AI OCR chain mode",
    )
    layout_model: str = Field(
        "pp_doclayout_v3",
        description="Local layout model for layout_block chain",
    )
    prompt_preset: str | None = Field(
        "auto",
        description="OCR prompt preset (auto, generic_vision, openai_vision, qwen_vl, glm_v, deepseek_ocr)",
    )
    direct_prompt_override: str | None = Field(
        None,
        description="Direct OCR prompt override",
    )
    layout_block_prompt_override: str | None = Field(
        None,
        description="Local layout block OCR prompt override",
    )
    image_region_prompt_override: str | None = Field(
        None,
        description="Image region detection prompt override",
    )
    paddle_vl_docparser_max_side_px: int | None = Field(
        None,
        ge=0,
        le=6000,
        description="Max long-edge in pixels for PaddleOCR-VL doc_parser input images",
    )
    page_concurrency: int | None = Field(
        1,
        ge=1,
        le=8,
        description="Multi-page AI OCR concurrency for direct/layout_block chains",
    )
    block_concurrency: int | None = Field(
        None,
        ge=1,
        le=8,
        description="Per-page block concurrency override for layout_block OCR",
    )
    requests_per_minute: int | None = Field(
        None,
        ge=1,
        le=2000,
        description="Shared requests-per-minute cap for AI OCR requests",
    )
    tokens_per_minute: int | None = Field(
        None,
        ge=1,
        le=2_000_000,
        description="Shared tokens-per-minute cap for AI OCR requests",
    )
    max_retries: int | None = Field(
        0,
        ge=0,
        le=8,
        description="Retry count for retryable AI OCR failures",
    )
    linebreak_assist: bool | None = Field(
        None,
        description="AI OCR line-break post-process for OCR blocks",
    )


class OcrConfig(BaseModel):
    """OCR provider and settings configuration."""

    model_config = ConfigDict(populate_by_name=True)

    provider: Literal["auto", "aiocr", "baidu", "tesseract", "paddle", "paddle_local"] = (
        Field("auto", description="OCR provider selection")
    )
    ai: OcrAiConfig = Field(
        default_factory=OcrAiConfig,
        description="AI OCR specific settings",
    )
    baidu: BaiduOcrConfig = Field(
        default_factory=BaiduOcrConfig,
        description="Baidu OCR credentials",
    )
    tesseract: TesseractConfig = Field(
        default_factory=TesseractConfig,
        description="Tesseract OCR settings",
    )
    render_dpi: int | None = Field(
        None,
        ge=72,
        le=400,
        description="OCR render DPI for scanned-page rasterization",
    )
    strict_mode: bool | None = Field(
        True,
        description="Strict OCR quality mode: disable implicit fallbacks/downgrades",
    )


class MineruConfig(BaseModel):
    """MinerU document parser configuration."""

    model_config = ConfigDict(populate_by_name=True)

    api_token: str | None = Field(
        None,
        description="MinerU API token (required when parse_provider=mineru)",
    )
    base_url: str | None = Field(None, description="MinerU API base URL")
    model_version: str | None = Field("vlm", description="MinerU model version")
    enable_formula: bool | None = Field(True, description="Enable formula recognition")
    enable_table: bool | None = Field(True, description="Enable table recognition")
    language: str | None = Field(None, description="Language hint (e.g. ch, en)")
    is_ocr: bool | None = Field(None, description="Per-file OCR switch")


class BaiduDocConfig(BaseModel):
    """Baidu document parser configuration."""

    model_config = ConfigDict(populate_by_name=True)

    parse_type: Literal["general", "paddle_vl"] = Field(
        "paddle_vl",
        description="Baidu parser variant",
    )


class ParseConfig(BaseModel):
    """Document parsing configuration."""

    model_config = ConfigDict(populate_by_name=True)

    provider: Literal["local", "mineru", "baidu_doc"] = Field(
        "local",
        description="Parser provider",
    )
    mineru: MineruConfig = Field(
        default_factory=MineruConfig,
        description="MinerU settings (when parse_provider=mineru)",
    )
    baidu_doc: BaiduDocConfig = Field(
        default_factory=BaiduDocConfig,
        description="Baidu document parser settings (when parse_provider=baidu_doc)",
    )


class ImageRegionConfig(BaseModel):
    """Image region tuning parameters for scanned page processing."""

    model_config = ConfigDict(populate_by_name=True)

    bg_clear_expand_min_pt: float | None = Field(
        None,
        description="Min expansion (pt) when clearing background under image overlays",
    )
    bg_clear_expand_max_pt: float | None = Field(
        None,
        description="Max expansion (pt) when clearing background under image overlays",
    )
    bg_clear_expand_ratio: float | None = Field(
        None,
        description="Expansion ratio for image-overlay background clearing",
    )
    scanned_image_region_min_area_ratio: float | None = Field(
        None,
        description="Min page-area ratio for scanned image region candidates",
    )
    scanned_image_region_max_area_ratio: float | None = Field(
        None,
        description="Max page-area ratio for scanned image region candidates",
    )
    scanned_image_region_max_aspect_ratio: float | None = Field(
        None,
        description="Max aspect ratio threshold for scanned image region candidates",
    )


class PptConfig(BaseModel):
    """PPT generation configuration."""

    model_config = ConfigDict(populate_by_name=True)

    generation_mode: Literal["standard", "fast", "turbo"] = Field(
        "standard",
        description="PPT generation mode",
    )
    text_erase_mode: Literal["smart", "fill"] = Field(
        "fill",
        description="Text erase mode for scanned/mineru pages",
    )
    scanned_page_mode: Literal["segmented", "fullpage"] = Field(
        "segmented",
        description="Image placement mode in PPT generation",
    )
    image_regions: ImageRegionConfig = Field(
        default_factory=ImageRegionConfig,
        description="Image region tuning parameters",
    )


class PageRangeConfig(BaseModel):
    """Page range for conversion."""

    model_config = ConfigDict(populate_by_name=True)

    start: int | None = Field(
        None,
        ge=1,
        description="1-based start page",
    )
    end: int | None = Field(
        None,
        ge=1,
        description="1-based end page",
    )


class JobConfig(BaseModel):
    """Complete job configuration.

    This replaces the 60+ flat Form() parameters with a structured model.
    Use `to_worker_kwargs()` to convert back to the flat format expected
    by the worker function.
    """

    model_config = ConfigDict(populate_by_name=True)

    # Core flags
    enable_ocr: bool = Field(False, description="Enable OCR for scanned PDFs or images")
    retain_process_artifacts: bool = Field(
        False,
        description="Keep process/debug artifacts for tracking",
    )
    remove_footer_notebooklm: bool = Field(
        False,
        description="Remove NotebookLM footer branding text",
    )

    # Structured sub-configs
    parse: ParseConfig = Field(
        default_factory=ParseConfig,
        description="Document parsing configuration",
    )
    ocr: OcrConfig = Field(
        default_factory=OcrConfig,
        description="OCR provider and settings",
    )
    llm: LlmConfig = Field(
        default_factory=LlmConfig,
        description="LLM configuration for layout assist",
    )
    ppt: PptConfig = Field(
        default_factory=PptConfig,
        description="PPT generation configuration",
    )
    page_range: PageRangeConfig = Field(
        default_factory=PageRangeConfig,
        description="Page range for conversion",
    )

    def to_worker_kwargs(self) -> dict[str, Any]:
        """Convert structured config to flat kwargs for the worker.

        This method produces the exact same kwargs dict that the old
        create_job() endpoint builds from 60+ Form() parameters.
        """
        ocr_ai = self.ocr.ai
        ocr_baidu = self.ocr.baidu
        ocr_tesseract = self.ocr.tesseract
        mineru = self.parse.mineru
        baidu_doc = self.parse.baidu_doc
        img_regions = self.ppt.image_regions
        page_range = self.page_range

        return {
            # Core flags
            "enable_ocr": self.enable_ocr,
            "retain_process_artifacts": self.retain_process_artifacts,
            "remove_footer_notebooklm": self.remove_footer_notebooklm,
            # Deprecated (always False)
            "enable_layout_assist": False,
            "layout_assist_apply_image_regions": False,
            # LLM config
            "provider": self.llm.provider,
            "api_key": self.llm.api_key,
            "base_url": self.llm.base_url,
            "model": self.llm.model,
            # Parse config
            "parse_provider": self.parse.provider,
            "baidu_doc_parse_type": baidu_doc.parse_type,
            # MinerU config
            "mineru_api_token": mineru.api_token,
            "mineru_base_url": mineru.base_url,
            "mineru_model_version": mineru.model_version,
            "mineru_enable_formula": mineru.enable_formula,
            "mineru_enable_table": mineru.enable_table,
            "mineru_language": mineru.language,
            "mineru_is_ocr": mineru.is_ocr,
            "mineru_hybrid_ocr": False,  # deprecated
            # OCR provider
            "ocr_provider": self.ocr.provider,
            # Baidu OCR
            "ocr_baidu_app_id": ocr_baidu.app_id,
            "ocr_baidu_api_key": ocr_baidu.api_key,
            "ocr_baidu_secret_key": ocr_baidu.secret_key,
            # Tesseract
            "ocr_tesseract_min_confidence": ocr_tesseract.min_confidence,
            "ocr_tesseract_language": ocr_tesseract.language,
            # AI OCR
            "ocr_ai_api_key": ocr_ai.api_key,
            "ocr_ai_provider": ocr_ai.provider,
            "ocr_ai_base_url": ocr_ai.base_url,
            "ocr_ai_model": ocr_ai.model,
            "ocr_ai_chain_mode": ocr_ai.chain_mode,
            "ocr_ai_layout_model": ocr_ai.layout_model,
            "ocr_ai_prompt_preset": ocr_ai.prompt_preset,
            "ocr_ai_direct_prompt_override": ocr_ai.direct_prompt_override,
            "ocr_ai_layout_block_prompt_override": ocr_ai.layout_block_prompt_override,
            "ocr_ai_image_region_prompt_override": ocr_ai.image_region_prompt_override,
            "ocr_paddle_vl_docparser_max_side_px": ocr_ai.paddle_vl_docparser_max_side_px,
            "ocr_ai_page_concurrency": ocr_ai.page_concurrency,
            "ocr_ai_block_concurrency": ocr_ai.block_concurrency,
            "ocr_ai_requests_per_minute": ocr_ai.requests_per_minute,
            "ocr_ai_tokens_per_minute": ocr_ai.tokens_per_minute,
            "ocr_ai_max_retries": ocr_ai.max_retries,
            "ocr_render_dpi": self.ocr.render_dpi,
            "ocr_geometry_mode": "auto",  # deprecated
            "ocr_ai_linebreak_assist": ocr_ai.linebreak_assist,
            "ocr_strict_mode": self.ocr.strict_mode,
            # PPT config
            "text_erase_mode": self.ppt.text_erase_mode,
            "scanned_page_mode": self.ppt.scanned_page_mode,
            "ppt_generation_mode": self.ppt.generation_mode,
            # Image region tuning
            "image_bg_clear_expand_min_pt": img_regions.bg_clear_expand_min_pt,
            "image_bg_clear_expand_max_pt": img_regions.bg_clear_expand_max_pt,
            "image_bg_clear_expand_ratio": img_regions.bg_clear_expand_ratio,
            "scanned_image_region_min_area_ratio": img_regions.scanned_image_region_min_area_ratio,
            "scanned_image_region_max_area_ratio": img_regions.scanned_image_region_max_area_ratio,
            "scanned_image_region_max_aspect_ratio": img_regions.scanned_image_region_max_aspect_ratio,
            # Page range
            "page_start": page_range.start,
            "page_end": page_range.end,
        }
