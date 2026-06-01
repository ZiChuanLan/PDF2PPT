from __future__ import annotations

import io
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import anyio
import pymupdf
import pytest
from PIL import Image


API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.routers import jobs


class _FakeRedisJob:
    def __init__(self, job_id: str) -> None:
        now = datetime.now(timezone.utc)
        self.job_id = job_id
        self.status = jobs.JobStatus.pending
        self.created_at = now
        self.expires_at = now + timedelta(hours=24)


class _FakeRedisService:
    def __init__(self) -> None:
        self.updated: list[tuple[str, jobs.JobStatus, jobs.JobStage, str]] = []

    def is_memory_backend(self) -> bool:
        return True

    def create_job(self, job_id: str, *, user_id: int | None = None) -> _FakeRedisJob:
        _ = user_id
        return _FakeRedisJob(job_id)

    def update_job(
        self,
        job_id: str,
        *,
        status: jobs.JobStatus,
        stage: jobs.JobStage,
        message: str,
    ) -> None:
        self.updated.append((job_id, status, stage, message))


def _build_png_bytes(*, size: tuple[int, int] = (400, 200)) -> bytes:
    image = Image.new("RGBA", size, (0, 128, 255, 160))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    image.close()
    return buffer.getvalue()


def _normalized_job_options() -> SimpleNamespace:
    return SimpleNamespace(
        parse_provider="local",
        provider="openai",
        baidu_doc_parse_type="paddle_vl",
        ocr_provider="auto",
        ocr_ai_provider="auto",
        ocr_ai_chain_mode="direct",
        ocr_ai_layout_model="pp_doclayout_v3",
        ocr_geometry_mode="auto",
        text_erase_mode="fill",
        scanned_page_mode="segmented",
        ppt_generation_mode="standard",
    )


def _settings(job_root_dir: Path) -> SimpleNamespace:
    return SimpleNamespace(
        max_file_mb=20,
        job_root_dir=str(job_root_dir),
        min_disk_space_mb=1,
        job_timeout_seconds=3600,
    )


class _FakeUploadFile:
    def __init__(self, *, filename: str, content: bytes, content_type: str) -> None:
        self.filename = filename
        self.content_type = content_type
        self._content = content
        self._offset = 0

    async def read(self, size: int = -1) -> bytes:
        if self._offset >= len(self._content):
            return b""
        if size is None or size < 0:
            end = len(self._content)
        else:
            end = min(len(self._content), self._offset + int(size))
        chunk = self._content[self._offset:end]
        self._offset = end
        return chunk


def _upload_file(*, filename: str, content: bytes, content_type: str) -> _FakeUploadFile:
    return _FakeUploadFile(
        filename=filename,
        content=content,
        content_type=content_type,
    )


def _job_kwargs() -> dict[str, object]:
    options = _normalized_job_options()
    return {
        "parse_provider": options.parse_provider,
        "baidu_doc_parse_type": options.baidu_doc_parse_type,
        "ocr_provider": options.ocr_provider,
        "ocr_ai_provider": options.ocr_ai_provider,
        "ocr_ai_chain_mode": options.ocr_ai_chain_mode,
        "ocr_ai_layout_model": options.ocr_ai_layout_model,
        "ocr_geometry_mode": options.ocr_geometry_mode,
        "text_erase_mode": options.text_erase_mode,
        "scanned_page_mode": options.scanned_page_mode,
        "ppt_generation_mode": options.ppt_generation_mode,
    }


def _create_job_from_upload(file: _FakeUploadFile):
    async def _call():
        return await jobs._create_job_core(file, _job_kwargs(), current_user=None)

    return anyio.run(_call)


def test_create_job_accepts_png_and_normalizes_to_input_pdf(
    monkeypatch, tmp_path: Path
) -> None:
    redis_service = _FakeRedisService()
    submitted: dict[str, object] = {}

    def _ensure_job_dir(job_id: str) -> Path:
        target = tmp_path / job_id
        target.mkdir(parents=True, exist_ok=True)
        return target

    monkeypatch.setattr(
        jobs,
        "validate_and_normalize_job_options",
        lambda **kwargs: _normalized_job_options(),
    )
    monkeypatch.setattr(jobs, "get_settings", lambda: _settings(tmp_path))
    monkeypatch.setattr(jobs, "get_redis_service", lambda: redis_service)
    monkeypatch.setattr(jobs, "ensure_job_dir", _ensure_job_dir)
    monkeypatch.setattr(
        jobs,
        "_submit_job",
        lambda job_id, kwargs: submitted.update({"job_id": job_id, "kwargs": kwargs}),
    )

    response = _create_job_from_upload(
        _upload_file(
            filename="slide.png",
            content=_build_png_bytes(),
            content_type="image/png",
        )
    )

    job_id = str(response.job_id)
    input_pdf = tmp_path / job_id / "input.pdf"
    assert input_pdf.exists()
    assert submitted["job_id"] == job_id
    assert isinstance(submitted["kwargs"], dict)
    assert redis_service.updated == [
        (
            job_id,
            jobs.JobStatus.pending,
            jobs.JobStage.queued,
            "Job queued for processing",
        )
    ]

    doc = pymupdf.open(str(input_pdf))
    try:
        assert doc.page_count == 1
        page = doc.load_page(0)
        assert page.rect.width > 0
        assert page.rect.height > 0
    finally:
        doc.close()


def test_create_job_rejects_unsupported_upload_type(monkeypatch, tmp_path: Path) -> None:
    def _ensure_job_dir(job_id: str) -> Path:
        target = tmp_path / job_id
        target.mkdir(parents=True, exist_ok=True)
        return target

    monkeypatch.setattr(
        jobs,
        "validate_and_normalize_job_options",
        lambda **kwargs: _normalized_job_options(),
    )
    monkeypatch.setattr(jobs, "get_settings", lambda: _settings(tmp_path))
    monkeypatch.setattr(jobs, "get_redis_service", lambda: _FakeRedisService())
    monkeypatch.setattr(jobs, "ensure_job_dir", _ensure_job_dir)

    with pytest.raises(jobs.AppException) as exc_info:
        _create_job_from_upload(
            _upload_file(
                filename="notes.txt",
                content=b"hello",
                content_type="text/plain",
            )
        )

    assert exc_info.value.code == "validation_error"
    assert (
        "Only PDF, PNG, JPG, JPEG, and WEBP files are supported"
        in exc_info.value.message
    )
