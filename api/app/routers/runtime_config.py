"""Runtime configuration endpoints — read/write server-side config values.

Provides GET/PUT /api/v1/config/runtime for admin users to inspect and
update runtime configuration values stored in the .env file.

The GET endpoint reads current values from the live Settings object (memory).
The PUT endpoint writes updated values to the .env file, reusing the same
parsing/update logic as the admin env editor.
"""

import os
import re
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.config import get_settings
from app.dependencies import require_admin
from app.logging_config import get_logger
from app.models.user import UserORM

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/config", tags=["config"])

# ---------------------------------------------------------------------------
# .env file path (same as admin.py)
# ---------------------------------------------------------------------------
ENV_FILE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"
)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class RuntimeConfigValues(BaseModel):
    """Flat key-value map of runtime config fields."""

    JOB_TIMEOUT_SECONDS: int = Field(default=3600, description="Job timeout in seconds (RQ / inline-thread)")
    OCR_PAGE_TIMEOUT_S: int = Field(default=300, description="Per-page OCR timeout in seconds")
    OCR_TOTAL_TIMEOUT_S: int = Field(default=3600, description="Overall OCR stage timeout in seconds")
    OCR_PADDLE_VL_PREDICT_TIMEOUT_S: float = Field(default=180.0, description="PaddleOCR-VL predict timeout (seconds)")
    OCR_AI_RETRY_BACKOFF_BASE_S: float = Field(default=8.0, description="Base retry backoff for AI OCR calls (seconds)")
    OCR_AI_RATE_LIMITED_MIN_DELAY_S: float = Field(default=2.0, description="Min delay after rate-limited response (seconds)")
    ENABLE_LAYOUT_ASSIST: bool = Field(default=False, description="Enable AI layout assist stage")
    SCANNED_RENDER_DPI: int = Field(default=200, description="PPTX background render DPI")
    OCR_AI_PAGE_CONCURRENCY_MAX: int = Field(default=8, description="Max page concurrency cap")
    OCR_AI_BLOCK_CONCURRENCY_MAX: int = Field(default=8, description="Max block concurrency cap")
    OCR_AI_RPM_MAX: int = Field(default=2000, description="Max RPM cap")
    OCR_AI_TPM_MAX: int = Field(default=2_000_000, description="Max TPM cap")
    OCR_AI_MAX_RETRIES_MAX: int = Field(default=8, description="Max retries cap")
    OCR_AI_PAGE_CONCURRENCY_DEFAULT: int = Field(default=1, description="Default page concurrency")
    OCR_AI_BLOCK_CONCURRENCY_DEFAULT: int = Field(default=1, description="Default block concurrency")
    OCR_AI_RPM_DEFAULT: int = Field(default=1, description="Default RPM")
    OCR_AI_TPM_DEFAULT: int = Field(default=1000, description="Default TPM")
    OCR_AI_MAX_RETRIES_DEFAULT: int = Field(default=0, description="Default max retries")
    OCR_MAX_CONSECUTIVE_TIMEOUTS: int = Field(default=2, description="Circuit-breaker: consecutive timeout limit")
    OCR_IMAGE_REGION_TIMEOUT_S: int = Field(default=12, description="AI image-region detection timeout (seconds)")


class RuntimeConfigResponse(BaseModel):
    """Wrapper for GET response."""

    config: RuntimeConfigValues
    message: str = "Current runtime configuration"


# ---------------------------------------------------------------------------
# Helpers — .env file parsing (mirrors admin.py pattern)
# ---------------------------------------------------------------------------


def _parse_env_content(raw: str) -> dict[str, str]:
    """Parse .env file content into a key→value dict.

    Handles quoted values and duplicate keys (last wins).
    """
    env: dict[str, str] = {}
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", stripped)
        if not match:
            continue
        key = match.group(1)
        value = match.group(2)
        # Strip surrounding quotes
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        env[key] = value
    return env


def _update_env_content(raw: str, updates: dict[str, str]) -> str:
    """Update or insert key=value lines in .env content.

    Existing keys are updated in-place (preserving comments, blank lines,
    and ordering).  New keys are appended at the end.
    """
    updated_keys: set[str] = set()
    new_lines: list[str] = []

    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", stripped)
        if not match:
            new_lines.append(line)
            continue
        key = match.group(1)
        if key in updates:
            # Preserve original quoting style by checking current value
            current_value = match.group(2)
            if len(current_value) >= 2 and current_value[0] == current_value[-1] and current_value[0] in ('"', "'"):
                # Keep quoting
                new_lines.append(f'{key}={current_value[0]}{updates[key]}{current_value[-1]}')
            else:
                new_lines.append(f"{key}={updates[key]}")
            updated_keys.add(key)
        else:
            new_lines.append(line)

    # Append any new keys not found in the file
    for key, value in updates.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={value}")

    return "\n".join(new_lines) + "\n"


# ---------------------------------------------------------------------------
# Value serialization helpers
# ---------------------------------------------------------------------------

_FIELD_ENV_MAP: dict[str, tuple[str, type]] = {
    "JOB_TIMEOUT_SECONDS": ("JOB_TIMEOUT_SECONDS", int),
    "OCR_PAGE_TIMEOUT_S": ("OCR_PAGE_TIMEOUT_S", int),
    "OCR_TOTAL_TIMEOUT_S": ("OCR_TOTAL_TIMEOUT_S", int),
    "OCR_PADDLE_VL_PREDICT_TIMEOUT_S": ("OCR_PADDLE_VL_PREDICT_TIMEOUT_S", float),
    "OCR_AI_RETRY_BACKOFF_BASE_S": ("OCR_AI_RETRY_BACKOFF_BASE_S", float),
    "OCR_AI_RATE_LIMITED_MIN_DELAY_S": ("OCR_AI_RATE_LIMITED_MIN_DELAY_S", float),
    "ENABLE_LAYOUT_ASSIST": ("ENABLE_LAYOUT_ASSIST", bool),
    "SCANNED_RENDER_DPI": ("SCANNED_RENDER_DPI", int),
    "OCR_AI_PAGE_CONCURRENCY_MAX": ("OCR_AI_PAGE_CONCURRENCY_MAX", int),
    "OCR_AI_BLOCK_CONCURRENCY_MAX": ("OCR_AI_BLOCK_CONCURRENCY_MAX", int),
    "OCR_AI_RPM_MAX": ("OCR_AI_RPM_MAX", int),
    "OCR_AI_TPM_MAX": ("OCR_AI_TPM_MAX", int),
    "OCR_AI_MAX_RETRIES_MAX": ("OCR_AI_MAX_RETRIES_MAX", int),
    "OCR_AI_PAGE_CONCURRENCY_DEFAULT": ("OCR_AI_PAGE_CONCURRENCY_DEFAULT", int),
    "OCR_AI_BLOCK_CONCURRENCY_DEFAULT": ("OCR_AI_BLOCK_CONCURRENCY_DEFAULT", int),
    "OCR_AI_RPM_DEFAULT": ("OCR_AI_RPM_DEFAULT", int),
    "OCR_AI_TPM_DEFAULT": ("OCR_AI_TPM_DEFAULT", int),
    "OCR_AI_MAX_RETRIES_DEFAULT": ("OCR_AI_MAX_RETRIES_DEFAULT", int),
    "OCR_MAX_CONSECUTIVE_TIMEOUTS": ("OCR_MAX_CONSECUTIVE_TIMEOUTS", int),
    "OCR_IMAGE_REGION_TIMEOUT_S": ("OCR_IMAGE_REGION_TIMEOUT_S", int),
}


def _build_get_response() -> RuntimeConfigResponse:
    """Build the GET response from the live Settings object."""
    settings = get_settings()
    config = RuntimeConfigValues(
        JOB_TIMEOUT_SECONDS=settings.job_timeout_seconds,
        OCR_PAGE_TIMEOUT_S=settings.ocr_page_timeout_s,
        OCR_TOTAL_TIMEOUT_S=settings.ocr_total_timeout_s,
        OCR_PADDLE_VL_PREDICT_TIMEOUT_S=settings.ocr_paddle_vl_predict_timeout_s,
        OCR_AI_RETRY_BACKOFF_BASE_S=settings.ocr_ai_retry_backoff_base_s,
        OCR_AI_RATE_LIMITED_MIN_DELAY_S=settings.ocr_ai_rate_limited_min_delay_s,
        ENABLE_LAYOUT_ASSIST=settings.enable_layout_assist,
        SCANNED_RENDER_DPI=settings.scanned_render_dpi,
        OCR_AI_PAGE_CONCURRENCY_MAX=settings.ocr_ai_page_concurrency_max,
        OCR_AI_BLOCK_CONCURRENCY_MAX=settings.ocr_ai_block_concurrency_max,
        OCR_AI_RPM_MAX=settings.ocr_ai_rpm_max,
        OCR_AI_TPM_MAX=settings.ocr_ai_tpm_max,
        OCR_AI_MAX_RETRIES_MAX=settings.ocr_ai_max_retries_max,
        OCR_AI_PAGE_CONCURRENCY_DEFAULT=settings.ocr_ai_page_concurrency_default,
        OCR_AI_BLOCK_CONCURRENCY_DEFAULT=settings.ocr_ai_block_concurrency_default,
        OCR_AI_RPM_DEFAULT=settings.ocr_ai_rpm_default,
        OCR_AI_TPM_DEFAULT=settings.ocr_ai_tpm_default,
        OCR_AI_MAX_RETRIES_DEFAULT=settings.ocr_ai_max_retries_default,
        OCR_MAX_CONSECUTIVE_TIMEOUTS=settings.ocr_max_consecutive_timeouts,
        OCR_IMAGE_REGION_TIMEOUT_S=settings.ocr_image_region_timeout_s,
    )
    return RuntimeConfigResponse(config=config)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/runtime", response_model=RuntimeConfigResponse)
async def get_runtime_config(
    admin: UserORM = Depends(require_admin),
):
    """Read current runtime configuration values (admin only).

    Returns the live Settings values currently in memory.  These may differ
    from the .env file if the server hasn't been restarted after env edits.
    """
    return _build_get_response()


@router.put("/runtime", response_model=RuntimeConfigResponse)
async def update_runtime_config(
    payload: RuntimeConfigValues,
    admin: UserORM = Depends(require_admin),
):
    """Update runtime configuration values in the .env file (admin only).

    Writes the provided fields to the .env file.  Other keys are preserved.
    Changes take effect after server restart.

    Only the fields present in the request body are updated; omitted fields
    keep their current .env values.
    """
    # Build the updates dict — only include fields that were explicitly set
    # in the request body (Pydantic excludes unset fields from model_dump by
    # default, but the user may send all fields.  We write all received fields.)
    updates: dict[str, str] = {}

    # Serialize each field to its env-var string form
    for api_field, (env_key, _type) in _FIELD_ENV_MAP.items():
        value = getattr(payload, api_field, None)
        if value is not None:
            if isinstance(value, bool):
                updates[env_key] = str(value).lower()  # "true" / "false"
            else:
                updates[env_key] = str(value)

    if not updates:
        # Nothing to update — just return current values
        return _build_get_response()

    try:
        with open(ENV_FILE_PATH, "r", encoding="utf-8") as f:
            raw = f.read()
    except FileNotFoundError:
        raw = ""

    new_content = _update_env_content(raw, updates)
    os.makedirs(os.path.dirname(ENV_FILE_PATH), exist_ok=True)

    # Create backup before writing
    backup_path = ENV_FILE_PATH + ".bak"
    try:
        if os.path.exists(ENV_FILE_PATH):
            import shutil
            shutil.copy2(ENV_FILE_PATH, backup_path)
    except Exception:
        logger.warning("Failed to create .env backup", exc_info=True)

    with open(ENV_FILE_PATH, "w", encoding="utf-8") as f:
        f.write(new_content)

    logger.info(
        "Admin updated runtime config in .env: %s", list(updates.keys())
    )

    return RuntimeConfigResponse(
        config=payload,
        message="Runtime configuration updated. Restart server for changes to take effect.",
    )
