"""Job artifact directory helpers.

Keep all job path resolution in one place so worker, routers and scripts
behave consistently regardless of current working directory.
"""

from __future__ import annotations

from pathlib import Path

from .config import get_settings
from .models.error import AppException, ErrorCode

_API_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_JOB_ROOT = _API_ROOT / "data" / "jobs"


def get_job_root_dir() -> Path:
    """Return absolute job root directory.

    - Absolute `JOB_ROOT_DIR` is used as-is.
    - Relative `JOB_ROOT_DIR` is resolved under API project root (`api/`).
    - Empty value falls back to `api/data/jobs`.
    """

    settings = get_settings()
    raw = str(getattr(settings, "job_root_dir", "") or "").strip()
    if not raw:
        return _DEFAULT_JOB_ROOT

    root = Path(raw)
    if root.is_absolute():
        return root
    return (_API_ROOT / root).resolve()


def get_job_dir(job_id: str) -> Path:
    """Return absolute job directory for a job id."""

    return get_job_root_dir() / str(job_id)


def ensure_job_dir(job_id: str) -> Path:
    """Create and return job directory for a job id."""

    job_dir = get_job_dir(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    return job_dir


def resolve_artifact_file(job_id: str, rel_path: str) -> Path:
    """Resolve artifact file safely under job directory.

    Raises `AppException` with a stable API error payload on invalid path or
    missing target file.
    """

    job_dir = get_job_dir(job_id).resolve()
    rel = Path(rel_path)
    if rel.is_absolute() or any(part == ".." for part in rel.parts):
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            message="Invalid artifact path",
            details={"path": rel_path},
            status_code=400,
        )

    target = (job_dir / rel).resolve()
    try:
        target.relative_to(job_dir)
    except Exception:
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            message="Invalid artifact path",
            details={"path": rel_path},
            status_code=400,
        ) from None

    if not target.exists() or not target.is_file():
        raise AppException(
            code=ErrorCode.JOB_NOT_FOUND,
            message="Artifact file not found",
            details={"path": rel_path},
            status_code=404,
        )
    return target

