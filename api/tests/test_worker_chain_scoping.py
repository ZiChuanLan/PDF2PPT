from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace


API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app import worker
from app.worker_helpers._job_options import JobOptions


def test_resolve_enable_layout_defaults_missing_legacy_option() -> None:
    assert worker._resolve_enable_layout(SimpleNamespace()) is True
    assert worker._resolve_enable_layout(SimpleNamespace(enable_layout=None)) is True
    assert worker._resolve_enable_layout(SimpleNamespace(enable_layout=True)) is True
    assert worker._resolve_enable_layout(SimpleNamespace(enable_layout=False)) is False


def test_resolve_enable_sam_defaults_missing_legacy_option() -> None:
    assert worker._resolve_enable_sam(SimpleNamespace()) is None
    assert worker._resolve_enable_sam(SimpleNamespace(enable_sam=True)) is True
    assert worker._resolve_enable_sam(SimpleNamespace(enable_sam=False)) is False


class _FakeRedisService:
    def __init__(self) -> None:
        self.updates: list[dict] = []

    def is_cancelled(self, job_id: str) -> bool:
        _ = job_id
        return False

    def update_job(self, job_id: str, **kwargs) -> None:
        self.updates.append({"job_id": job_id, **kwargs})

    def refresh_job_ttl(self, job_id: str) -> None:
        _ = job_id


class _FakeSettings:
    redis_url = "memory://"
    job_ttl_minutes = 60
    job_debug_events_limit = 200
    ocr_render_dpi = 200
    scanned_render_dpi = 200
    job_keepalive_interval_s = 15
    export_ocr_overlay_images = False
    export_final_preview_images = False
    export_final_preview_max_pages = 0
    ocr_ai_page_concurrency_default = 1
    ocr_ai_page_concurrency_max = 8
    ocr_ai_block_concurrency_default = 1
    ocr_ai_block_concurrency_max = 8
    ocr_ai_rpm_default = 1
    ocr_ai_rpm_max = 2000
    ocr_ai_tpm_default = 1000
    ocr_ai_tpm_max = 2_000_000
    ocr_ai_max_retries_default = 0
    ocr_ai_max_retries_max = 8


def test_fast_ppt_generation_forwards_ocr_image_region_skip(
    monkeypatch, tmp_path
) -> None:
    job_dir = tmp_path / "job-fast-ocr"
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "input.pdf").write_bytes(b"%PDF-1.4\n")

    redis_service = _FakeRedisService()
    captured_ocr_kwargs: dict[str, object] = {}
    captured_setup_kwargs: list[dict[str, object]] = []

    monkeypatch.setattr(worker, "_job_dir", lambda job_id: job_dir)
    monkeypatch.setattr(worker, "get_settings", lambda: _FakeSettings())
    monkeypatch.setattr(worker, "get_redis_service", lambda: redis_service)
    monkeypatch.setattr(
        worker,
        "parse_pdf_to_ir",
        lambda *args, **kwargs: {
            "source_pdf": str(job_dir / "input.pdf"),
            "warnings": [],
            "pages": [
                {
                    "page_index": 0,
                    "page_width_pt": 100.0,
                    "page_height_pt": 100.0,
                    "has_text_layer": False,
                    "ocr_used": False,
                    "elements": [],
                }
            ],
        },
    )
    def _fake_setup_ocr_runtime(**kwargs):
        captured_setup_kwargs.append(kwargs)
        return SimpleNamespace(
            ocr_manager=object(),
            text_refiner=None,
            linebreak_refiner=None,
            effective_ocr_provider="aiocr",
            effective_ocr_ai_provider="siliconflow",
            effective_ocr_ai_base_url="https://example.test/v1",
            effective_ocr_ai_model="deepseek-ocr",
            effective_tesseract_language="chi_sim+eng",
            effective_tesseract_min_conf=0.0,
            strict_ocr_mode=True,
            linebreak_enabled=False,
            auto_linebreak_enabled=False,
            setup_warning=None,
            linebreak_mode="disabled",
            linebreak_unavailable_reason=None,
        )

    monkeypatch.setattr(worker, "setup_ocr_runtime", _fake_setup_ocr_runtime)
    monkeypatch.setattr(
        worker,
        "build_ocr_debug_payload",
        lambda **kwargs: {"provider_effective": "aiocr", "pages": []},
    )
    monkeypatch.setattr(
        worker,
        "run_ocr_stage",
        lambda **kwargs: captured_ocr_kwargs.update(kwargs),
    )

    def _fake_run_ppt_stage(**kwargs):
        kwargs["output_pptx"].write_bytes(b"pptx")
        return SimpleNamespace(worker_compat_mode=False)

    monkeypatch.setattr(worker, "run_ppt_stage", _fake_run_ppt_stage)

    worker.process_pdf_job(
        "job-fast-ocr",
        options=JobOptions(
            parse_provider="local",
            enable_ocr=True,
            ocr_provider="aiocr",
            ppt_generation_mode="fast",
            scanned_page_mode="fullpage",
        ),
    )

    assert captured_ocr_kwargs["skip_image_region_detection"] is True
    assert captured_setup_kwargs[0]["enable_layout"] is True
    captured_ocr_kwargs["ocr_runtime_factory"]()
    assert captured_setup_kwargs[1]["enable_layout"] is True
    assert (job_dir / "output.pptx").exists()
