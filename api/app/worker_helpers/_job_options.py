"""JobOptions dataclass — all configuration for process_pdf_job()."""

from __future__ import annotations

from dataclasses import dataclass


# Count these carefully — there should be 57.
# This field count MUST match process_pdf_job()'s keyword-only parameters.

@dataclass
class JobOptions:
    """All configuration options for process_pdf_job in a single dataclass."""

    # Top-level flags
    enable_ocr: bool = False
    retain_process_artifacts: bool = False
    remove_footer_notebooklm: bool = False
    text_erase_mode: str | None = None

    # LLM / AI provider
    provider: str | None = None
    api_key: str | None = None

    # Parse provider
    baidu_doc_parse_type: str | None = None
    base_url: str | None = None
    model: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    parse_provider: str | None = None

    # MinerU
    mineru_api_token: str | None = None
    mineru_base_url: str | None = None
    mineru_model_version: str | None = None
    mineru_enable_formula: bool | None = None
    mineru_enable_table: bool | None = None
    mineru_language: str | None = None
    mineru_is_ocr: bool | None = None
    mineru_hybrid_ocr: bool | None = None

    # OCR
    ocr_provider: str | None = None
    ocr_baidu_app_id: str | None = None
    ocr_baidu_api_key: str | None = None
    ocr_baidu_secret_key: str | None = None
    ocr_tesseract_min_confidence: float | None = None
    ocr_tesseract_language: str | None = None

    # AI OCR
    ocr_ai_api_key: str | None = None
    ocr_ai_provider: str | None = None
    ocr_ai_base_url: str | None = None
    ocr_ai_model: str | None = None
    ocr_ai_chain_mode: str | None = None
    ocr_ai_layout_model: str | None = None
    ocr_ai_prompt_preset: str | None = None
    ocr_ai_direct_prompt_override: str | None = None
    ocr_ai_layout_block_prompt_override: str | None = None
    ocr_ai_image_region_prompt_override: str | None = None
    ocr_paddle_vl_docparser_max_side_px: int | None = None

    # AI OCR concurrency / rate limits
    ocr_ai_page_concurrency: int | None = None
    ocr_ai_block_concurrency: int | None = None
    ocr_ai_requests_per_minute: int | None = None
    ocr_ai_tokens_per_minute: int | None = None
    ocr_ai_max_retries: int | None = None

    # OCR rendering
    ocr_render_dpi: int | None = None
    ocr_geometry_mode: str | None = None

    # PPT generation
    scanned_page_mode: str | None = None
    ppt_generation_mode: str | None = None

    # Image background clear
    image_bg_clear_expand_min_pt: float | None = None
    image_bg_clear_expand_max_pt: float | None = None
    image_bg_clear_expand_ratio: float | None = None

    # Scanned image region detection
    scanned_image_region_min_area_ratio: float | None = None
    scanned_image_region_max_area_ratio: float | None = None
    scanned_image_region_max_aspect_ratio: float | None = None

    # Misc
    ocr_ai_linebreak_assist: bool | None = None
    ocr_strict_mode: bool | None = True
    job_timeout: str | None = None
