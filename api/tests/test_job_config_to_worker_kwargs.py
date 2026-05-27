"""Tests for JobConfig.to_worker_kwargs() propagation.

Verifies that structured JobConfig fields are correctly propagated
to the flat kwargs dict consumed by the worker.
"""

from __future__ import annotations

import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.schemas.job_config import JobConfig


def _default_config() -> JobConfig:
    """Create a default JobConfig with minimal changes from default."""
    return JobConfig()


def test_to_worker_kwargs_defaults() -> None:
    """Default config produces expected default values in kwargs."""
    config = _default_config()
    kwargs = config.to_worker_kwargs()
    assert kwargs["enable_ocr"] is False
    assert kwargs["retain_process_artifacts"] is False
    assert kwargs["remove_footer_notebooklm"] is False


def test_to_worker_kwargs_does_not_affect_other_fields() -> None:
    """Setting one flag should not unexpectedly alter other kwargs."""
    config = JobConfig(
        enable_ocr=True,
        remove_footer_notebooklm=True,
    )
    kwargs = config.to_worker_kwargs()

    # Core flags should reflect the config
    assert kwargs["enable_ocr"] is True
    assert kwargs["remove_footer_notebooklm"] is True
    assert kwargs["retain_process_artifacts"] is False

    # Parse provider should still be 'local' by default
    assert kwargs["parse_provider"] == "local"

    # OCR provider should be 'auto' by default
    assert kwargs["ocr_provider"] == "auto"

    # PPT mode should be 'standard' by default
    assert kwargs["ppt_generation_mode"] == "standard"


def test_to_worker_kwargs_ocr_independent() -> None:
    """OCR enablement should be independent of other flags."""
    config_ocr = JobConfig(enable_ocr=True)
    config_no_ocr = JobConfig(enable_ocr=False)

    kwargs_ocr = config_ocr.to_worker_kwargs()
    kwargs_no_ocr = config_no_ocr.to_worker_kwargs()

    assert kwargs_ocr["enable_ocr"] is True
    assert kwargs_no_ocr["enable_ocr"] is False
