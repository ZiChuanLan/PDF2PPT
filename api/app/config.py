"""Application configuration."""

import os
from functools import lru_cache

from pydantic_settings import BaseSettings

# ---------------------------------------------------------------------------
# Shared defaults (used in Settings and parse_cors_allow_origins)
# ---------------------------------------------------------------------------
_DEFAULT_CORS_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]
_DEFAULT_CORS_ORIGINS_STR = ",".join(_DEFAULT_CORS_ORIGINS)



class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    api_bind_host: str = "127.0.0.1"
    api_bearer_token: str | None = None
    max_file_mb: int = 100
    max_pages: int = 200
    # Terminal job metadata and on-disk job directories are retained for 24h by
    # default, then deleted by the cleanup daemon.
    job_ttl_minutes: int = 1440
    # Background cleanup sweep cadence for expired job directories.
    job_cleanup_interval_minutes: int = 15
    # Keepalive heartbeat interval for long-running blocking stages.
    # Used to refresh job metadata TTL while no progress update is emitted.
    job_keepalive_interval_s: int = 15
    # Maximum number of per-job debug events retained in job status payloads.
    job_debug_events_limit: int = 200
    # Root directory for per-job runtime artifacts.
    # Relative paths are resolved under the `api/` directory.
    job_root_dir: str = "data/jobs"
    redis_url: str = "redis://redis:6379/0"
    log_level: str = "INFO"
    # Rendering quality knobs for scanned PDFs.
    #
    # - ocr_render_dpi: higher DPI improves OCR recall/accuracy on scan-heavy decks.
    # - scanned_render_dpi: controls the background render quality in the PPTX
    #   output (higher DPI looks sharper but increases file size).
    # NOTE: Higher values (250-300) can improve OCR on some documents but may
    # degrade on others and increases CPU/memory usage. Keep conservative defaults.
    ocr_render_dpi: int = 200
    scanned_render_dpi: int = 200
    # Large multi-page jobs can spend a lot of time exporting debug/preview
    # images that are not required for the final PPTX output.
    export_ocr_overlay_images: bool = False
    # Final preview images are useful for QA, but they are pure extra output and
    # add avoidable rendering work. Keep them opt-in for speed-focused runs.
    export_final_preview_images: bool = False
    export_final_preview_max_pages: int = 5
    # Per-page OCR timeout in seconds.  If a single page takes longer than
    # this the page is skipped with a warning instead of blocking the whole job.
    ocr_page_timeout_s: int = 300
    # Circuit-breaker for repeated page-level timeouts. When consecutive OCR
    # pages hit timeout this many times, skip remaining OCR pages so the job
    # can continue to PPTX generation instead of appearing stuck.
    ocr_max_consecutive_timeouts: int = 2
    # Overall OCR stage timeout in seconds.  When exceeded the remaining pages
    # are skipped and the job continues to PPTX generation.
    ocr_total_timeout_s: int = 3600
    # Best-effort timeout for AI image-region detection. This should stay much
    # shorter than page OCR so image-region probing cannot make OCR appear stuck.
    ocr_image_region_timeout_s: int = 12
    cors_allow_origins: str = _DEFAULT_CORS_ORIGINS_STR
    cors_allow_origin_regex: str | None = None
    # LinuxDo OAuth settings
    linuxdo_client_id: str | None = None
    linuxdo_client_secret: str | None = None
    linuxdo_redirect_uri: str = "http://localhost:3000/auth/callback"
    # JWT settings
    jwt_secret: str = ""
    # Cookie secure flag - set to false for HTTP/local dev
    cookie_secure: bool = True
    # SQLite database path (relative to api/ directory)
    sqlite_path: str = "data/pdf2ppt.db"
    # Comma-separated LinuxDo usernames that should be auto-promoted to admin
    admin_usernames: str = ""
    # Deploy mode: "self" (self-use, localStorage) or "public" (multi-user, DB settings)
    deploy_mode: str = "self"
    # Rate limiting (requests per window per client IP)
    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60
    # Minimum free disk space (MB) required before accepting uploads
    min_disk_space_mb: int = 500
    # -------------------------------------------------------------------
    # Job timeout (seconds) — used as the RQ / inline-thread job timeout.
    # When exceeded the worker is killed and the job is marked failed.
    # Default: 3600 (1 hour).  Set via env JOB_TIMEOUT_S.
    # -------------------------------------------------------------------
    job_timeout_seconds: int = 3600

    # -------------------------------------------------------------------
    # OCR AI pipeline tunables — exposed as env vars so deployments can
    # adjust retry / backoff / vendor timeouts without touching code.
    # -------------------------------------------------------------------
    # PaddleOCR-VL predict timeout (seconds).  Default 180 (3 minutes).
    ocr_paddle_vl_predict_timeout_s: float = 180.0
    # Base retry backoff for AI OCR calls (seconds).  Default 8.
    ocr_ai_retry_backoff_base_s: float = 8.0
    # Minimum delay after a rate-limited response (seconds).  Default 2.
    ocr_ai_rate_limited_min_delay_s: float = 2.0
    # OCR AI concurrency defaults & caps.
    ocr_ai_page_concurrency_default: int = 1
    ocr_ai_page_concurrency_max: int = 8
    ocr_ai_block_concurrency_default: int = 1
    ocr_ai_block_concurrency_max: int = 8
    ocr_ai_rpm_default: int = 1
    ocr_ai_rpm_max: int = 2000
    ocr_ai_tpm_default: int = 1000
    ocr_ai_tpm_max: int = 2_000_000
    ocr_ai_max_retries_default: int = 0
    ocr_ai_max_retries_max: int = 8

    # -------------------------------------------------------------------
    # Feature toggles
    # -------------------------------------------------------------------
    # Enable CSRF token validation for state-changing requests.
    # Disabled by default — session auth is sufficient for self-hosted setups.
    enable_csrf: bool = False

    # -------------------------------------------------------------------
    # Font discovery
    # -------------------------------------------------------------------
    # Comma-separated extra font paths to search before the built-in
    # platform-specific fallback lists (Linux / macOS / Windows).
    extra_font_paths: str = ""

    # -------------------------------------------------------------------
    # AI OCR timeout / tuning (P0)
    # -------------------------------------------------------------------
    # PaddleOCR-VL DocParser: max side pixels for downscaling. 2200 is the
    # sweet spot that balances OCR accuracy vs. API latency / token cost.
    # Also defined in local_providers / result_parsing — this is the canonical
    # env-overridable source.
    ocr_paddle_vl_docparser_max_side_px: int = 2200
    # PaddleOCR-VL DocParser: explicit max-pixel override (integer pixels).
    # When set, bypasses the side-px-based max-pixel derivation.  Leave empty
    # to auto-derive from max_side_px.
    ocr_paddle_vl_docparser_max_pixels: str = ""
    # AiOcrTextRefiner chat-completion timeout (seconds).  Default 60.
    ocr_ai_text_refiner_timeout_s: float = 60.0

    # -------------------------------------------------------------------
    # JWT expiry overrides (configured here so the backend and frontend
    # cookie maxAge can be kept in sync from a single env-var source).
    # Keep these in sync with web/src/app/auth/callback/route.ts.
    # -------------------------------------------------------------------
    jwt_access_expire_minutes: int = 60
    jwt_refresh_expire_days: int = 30

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


def get_deploy_mode(db=None) -> str:
    """Get deploy mode, checking DB (site_settings) first, then falling back to env.

    Args:
        db: SQLAlchemy session. If None, falls back to env var directly.

    Returns:
        "self" or "public"
    """
    if db is not None:
        try:
            from app.models.user import SiteSettingsORM
            row = db.query(SiteSettingsORM).filter(SiteSettingsORM.key == "deploy_mode").first()
            if row and row.value in ("self", "public"):
                return row.value
        except Exception:
            pass
    return get_settings().deploy_mode


def parse_cors_allow_origins(raw: str | None) -> list[str]:
    value = str(raw or "").strip()
    if not value:
        return list(_DEFAULT_CORS_ORIGINS)
    if value == "*":
        return ["*"]
    items: list[str] = []
    for item in value.split(","):
        origin = item.strip()
        if origin and origin not in items:
            items.append(origin)
    return items or list(_DEFAULT_CORS_ORIGINS)
