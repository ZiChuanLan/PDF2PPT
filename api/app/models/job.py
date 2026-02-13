# pyright: reportMissingImports=false, reportMissingTypeArgument=false

"""Job models for async PDF to PPT conversion."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    """Job execution status."""

    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class JobStage(str, Enum):
    """Detailed job processing stages."""

    upload_received = "upload_received"
    queued = "queued"
    parsing = "parsing"
    ocr = "ocr"
    layout_assist = "layout_assist"
    pptx_generating = "pptx_generating"
    packaging = "packaging"
    cleanup = "cleanup"
    done = "done"


class LayoutMode(str, Enum):
    """Layout strategy selection."""

    fidelity = "fidelity"
    assist = "assist"


class Job(BaseModel):
    """Job metadata model."""

    job_id: str = Field(..., description="Unique job identifier")
    status: JobStatus = Field(..., description="Current job status")
    stage: JobStage = Field(..., description="Current processing stage")
    progress: int = Field(0, ge=0, le=100, description="Progress percentage")
    created_at: datetime = Field(..., description="Job creation timestamp")
    expires_at: datetime = Field(..., description="Job expiration timestamp")
    message: Optional[str] = Field(None, description="Human-readable status message")
    error: Optional[dict[str, Any]] = Field(None, description="Error details if failed")
    layout_mode: LayoutMode = Field(
        LayoutMode.fidelity,
        description="Layout mode: fidelity (no AI) or assist (LLM-assisted)",
    )


class JobCreateRequest(BaseModel):
    """Request model for job creation."""

    enable_ocr: bool = Field(False, description="Enable OCR for scanned PDFs")
    text_erase_mode: Optional[str] = Field(
        "fill",
        description="Text erase mode for scanned/mineru pages (smart, fill)",
    )
    scanned_page_mode: Optional[str] = Field(
        "segmented",
        description=(
            "Scanned page rendering mode (segmented, fullpage). "
            "Controls whether scanned pages are split into editable image blocks."
        ),
    )
    enable_layout_assist: bool = Field(True, description="Enable AI layout assistance")
    layout_assist_apply_image_regions: bool = Field(
        False,
        description="Apply AI-suggested image regions in layout assist (experimental)",
    )
    layout_mode: LayoutMode = Field(
        LayoutMode.fidelity,
        description="Layout mode: fidelity (no AI) or assist (LLM-assisted)",
    )
    provider: Optional[str] = Field(
        "openai", description="LLM provider identifier (openai, claude, domestic)"
    )
    api_key: Optional[str] = Field(None, description="Optional API key for AI services")
    base_url: Optional[str] = Field(
        None, description="Optional OpenAI-compatible base URL"
    )
    model: Optional[str] = Field(
        None, description="Optional OpenAI-compatible model identifier"
    )
    page_start: Optional[int] = Field(
        None, description="Optional 1-based start page for conversion"
    )
    page_end: Optional[int] = Field(
        None, description="Optional 1-based end page for conversion"
    )
    parse_provider: Optional[str] = Field(
        "local",
        description=(
            "Parser provider (local, mineru). Legacy `v2` is accepted for backward compatibility "
            "and maps to local+fullpage+AI OCR."
        ),
    )
    mineru_api_token: Optional[str] = Field(
        None, description="Optional MinerU API token"
    )
    mineru_base_url: Optional[str] = Field(
        None, description="Optional MinerU API base URL"
    )
    mineru_model_version: Optional[str] = Field(
        "vlm", description="MinerU model version (pipeline, vlm, MinerU-HTML)"
    )
    mineru_enable_formula: Optional[bool] = Field(
        True, description="Enable formula recognition in MinerU"
    )
    mineru_enable_table: Optional[bool] = Field(
        True, description="Enable table recognition in MinerU"
    )
    mineru_language: Optional[str] = Field(
        None, description="Optional MinerU language hint (e.g. ch, en)"
    )
    mineru_is_ocr: Optional[bool] = Field(
        None, description="Optional MinerU per-file OCR switch"
    )
    mineru_hybrid_ocr: Optional[bool] = Field(
        False,
        description="Enable local hybrid OCR alignment in MinerU mode (no AI text refiner)",
    )
    ocr_provider: Optional[str] = Field(
        "auto",
        description="OCR provider (auto, aiocr, baidu, tesseract, paddle, paddle_local); legacy ai/remote are accepted",
    )
    ocr_baidu_app_id: Optional[str] = Field(
        None, description="Optional Baidu OCR App ID"
    )
    ocr_baidu_api_key: Optional[str] = Field(
        None, description="Optional Baidu OCR API key"
    )
    ocr_baidu_secret_key: Optional[str] = Field(
        None, description="Optional Baidu OCR secret key"
    )
    ocr_tesseract_min_confidence: Optional[float] = Field(
        None, description="Optional Tesseract min confidence (0-100)"
    )
    ocr_tesseract_language: Optional[str] = Field(
        None, description="Optional Tesseract language code (e.g. eng, chi_sim)"
    )
    ocr_ai_api_key: Optional[str] = Field(
        None, description="Optional AI OCR API key (OpenAI-compatible)"
    )
    ocr_ai_provider: Optional[str] = Field(
        "auto",
        description=(
            "Optional AI OCR vendor adapter (auto, openai, siliconflow, deepseek, ppio, novita)"
        ),
    )
    ocr_ai_base_url: Optional[str] = Field(
        None, description="Optional AI OCR base URL (OpenAI-compatible)"
    )
    ocr_ai_model: Optional[str] = Field(
        None, description="Optional AI OCR model name"
    )
    ocr_ai_linebreak_assist: Optional[bool] = Field(
        None,
        description=(
            "Optional AI visual line-break assist for OCR blocks (split coarse boxes into line-level boxes). "
            "When omitted (null), the backend may auto-enable this for some OCR providers/models."
        ),
    )
    ocr_strict_mode: Optional[bool] = Field(
        False,
        description=(
            "Strict OCR quality mode: disable implicit OCR fallbacks/downgrades and fail fast on OCR errors"
        ),
    )


class JobCreateResponse(BaseModel):
    """Response model for job creation."""

    job_id: str = Field(..., description="Unique job identifier")
    status: JobStatus = Field(..., description="Initial job status")
    created_at: datetime = Field(..., description="Job creation timestamp")
    expires_at: datetime = Field(..., description="Job expiration timestamp")


class LocalOcrCheckRequest(BaseModel):
    """Request model for local OCR runtime checks."""

    provider: Optional[str] = Field(
        "tesseract", description="Local OCR provider to check (tesseract, paddle)"
    )
    language: Optional[str] = Field(
        None,
        description=(
            "Requested OCR language hint. For tesseract use chi_sim+eng; "
            "for paddle use ch/en etc."
        ),
    )


class LocalOcrCheckResult(BaseModel):
    """Detailed local OCR environment check result."""

    provider: str
    requested_language: str
    requested_languages: list[str] = Field(default_factory=list)
    python_package_available: bool
    binary_available: bool
    version: Optional[str] = None
    available_languages: list[str] = Field(default_factory=list)
    missing_languages: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    ready: bool
    message: str


class LocalOcrCheckResponse(BaseModel):
    """Response model for local OCR runtime checks."""

    ok: bool = Field(..., description="Whether local OCR is ready")
    check: LocalOcrCheckResult


class JobStatusResponse(BaseModel):
    """Response model for job status query."""

    job_id: str
    status: JobStatus
    stage: JobStage
    progress: int
    created_at: datetime
    expires_at: datetime
    message: Optional[str] = None
    error: Optional[dict[str, Any]] = None


class JobListItem(BaseModel):
    """Response item for job list query."""

    job_id: str
    status: JobStatus
    stage: JobStage
    progress: int
    created_at: datetime
    expires_at: datetime
    message: Optional[str] = None
    error: Optional[dict[str, Any]] = None
    # 1-based queue position when the job is still waiting in Redis queue.
    queue_position: Optional[int] = None
    # queued | running | waiting | done
    queue_state: Optional[str] = None


class JobListResponse(BaseModel):
    """Response model for job list query."""

    jobs: list[JobListItem]
    queue_size: int = 0
    returned: int = 0


class JobEvent(BaseModel):
    """SSE event model for job progress updates."""

    job_id: str
    status: JobStatus
    stage: JobStage
    progress: int
    message: Optional[str] = None
    error: Optional[dict[str, Any]] = None


class JobArtifactImage(BaseModel):
    """Single artifact image metadata."""

    page_index: int
    path: str
    url: str


class JobArtifactsResponse(BaseModel):
    """Artifact manifest used by frontend tracking/diff views."""

    job_id: str
    status: Optional[JobStatus] = None
    source_pdf_url: Optional[str] = None
    original_images: list[JobArtifactImage] = Field(default_factory=list)
    cleaned_images: list[JobArtifactImage] = Field(default_factory=list)
    final_preview_images: list[JobArtifactImage] = Field(default_factory=list)
    ocr_overlay_images: list[JobArtifactImage] = Field(default_factory=list)
    layout_before_images: list[JobArtifactImage] = Field(default_factory=list)
    layout_after_images: list[JobArtifactImage] = Field(default_factory=list)
    available_pages: list[int] = Field(default_factory=list)
