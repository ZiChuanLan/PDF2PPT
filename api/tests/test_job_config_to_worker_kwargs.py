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


def test_to_worker_kwargs_layout_assist_default_false() -> None:
    """Default config produces enable_layout_assist=False in kwargs."""
    config = _default_config()
    kwargs = config.to_worker_kwargs()
    assert kwargs["enable_layout_assist"] is False
    assert kwargs["layout_assist_apply_image_regions"] is False


def test_to_worker_kwargs_layout_assist_explicit_true() -> None:
    """When enable_layout_assist=True, kwargs carries True (not hardcoded False)."""
    config = JobConfig(enable_layout_assist=True)
    kwargs = config.to_worker_kwargs()
    assert kwargs["enable_layout_assist"] is True


def test_to_worker_kwargs_layout_assist_apply_image_regions_true() -> None:
    """When both flags are True, kwargs correctly propagates them."""
    config = JobConfig(
        enable_layout_assist=True,
        layout_assist_apply_image_regions=True,
    )
    kwargs = config.to_worker_kwargs()
    assert kwargs["enable_layout_assist"] is True
    assert kwargs["layout_assist_apply_image_regions"] is True


def test_to_worker_kwargs_does_not_affect_other_fields() -> None:
    """Setting layout assist flags should not unexpectedly alter other kwargs."""
    config = JobConfig(
        enable_layout_assist=True,
        layout_assist_apply_image_regions=True,
    )
    kwargs = config.to_worker_kwargs()

    # Core flags should still reflect defaults
    assert kwargs["enable_ocr"] is False
    assert kwargs["retain_process_artifacts"] is False
    assert kwargs["remove_footer_notebooklm"] is False

    # Parse provider should still be 'local' by default
    assert kwargs["parse_provider"] == "local"

    # OCR provider should be 'auto' by default
    assert kwargs["ocr_provider"] == "auto"

    # PPT mode should be 'standard' by default
    assert kwargs["ppt_generation_mode"] == "standard"


def test_to_worker_kwargs_layout_assist_independent_of_ocr() -> None:
    """Layout assist flags should be independent of OCR enablement."""
    config_ocr = JobConfig(enable_ocr=True, enable_layout_assist=False)
    config_layout = JobConfig(enable_ocr=False, enable_layout_assist=True)
    config_both = JobConfig(enable_ocr=True, enable_layout_assist=True)

    kwargs_ocr = config_ocr.to_worker_kwargs()
    kwargs_layout = config_layout.to_worker_kwargs()
    kwargs_both = config_both.to_worker_kwargs()

    # OCR-only config: layout assist is False
    assert kwargs_ocr["enable_layout_assist"] is False
    assert kwargs_ocr["enable_ocr"] is True

    # Layout-only config: OCR is False
    assert kwargs_layout["enable_layout_assist"] is True
    assert kwargs_layout["enable_ocr"] is False

    # Both enabled
    assert kwargs_both["enable_layout_assist"] is True
    assert kwargs_both["enable_ocr"] is True
