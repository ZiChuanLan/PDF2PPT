from __future__ import annotations

import time
import urllib.error

import anyio

from app.convert.ocr import _sam_provider as sam_provider
from app.routers import _download_manager as download_manager


def test_download_task_file_uses_app_data_dir(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path))

    assert download_manager._get_downloads_dir() == tmp_path / "downloads"
    assert (
        download_manager._get_download_tasks_file()
        == tmp_path / "downloads" / "tasks.json"
    )


def test_sam_checkpoint_url_supports_env_override(monkeypatch) -> None:
    monkeypatch.delenv("MOBILE_SAM_CHECKPOINT_URL", raising=False)
    monkeypatch.delenv("SAM_CHECKPOINT_URL", raising=False)

    monkeypatch.setenv("SAM_CHECKPOINT_URL", "https://mirror.example/sam.pt")
    assert sam_provider.get_sam_checkpoint_url() == "https://mirror.example/sam.pt"

    monkeypatch.setenv(
        "MOBILE_SAM_CHECKPOINT_URL", "https://cdn.example/mobile_sam.pt"
    )
    assert sam_provider.get_sam_checkpoint_url() == "https://cdn.example/mobile_sam.pt"


def test_sam_checkpoint_can_be_installed_from_configured_local_path(
    monkeypatch, tmp_path
) -> None:
    source = tmp_path / "source" / "mobile_sam.pt"
    source.parent.mkdir()
    source.write_bytes(b"checkpoint-bytes")
    target = tmp_path / "data" / "models" / "sam" / "mobile_sam.pt"

    monkeypatch.setenv("MOBILE_SAM_CHECKPOINT_PATH", str(source))

    sam_provider._download_checkpoint(target)

    assert target.read_bytes() == b"checkpoint-bytes"


def test_sam_dns_download_error_mentions_actionable_workarounds() -> None:
    error = urllib.error.URLError(OSError(-5, "No address associated with hostname"))

    message = download_manager._format_sam_download_error(error)

    assert "DNS" in message
    assert "代理" in message
    assert "MOBILE_SAM_CHECKPOINT_URL" in message
    assert "SAM_CHECKPOINT_URL" in message
    assert "MOBILE_SAM_CHECKPOINT_PATH" in message
    assert "SAM_CHECKPOINT_PATH" in message


def test_download_status_persists_expired_cleanup_outside_lock(monkeypatch) -> None:
    now = time.time()
    with download_manager._download_tasks_lock:
        download_manager._download_tasks.clear()
        download_manager._download_tasks["old-model"] = download_manager.DownloadTask(
            model_id="old-model",
            status="completed",
            started_at=now - 301,
        )
        download_manager._download_tasks["active-model"] = download_manager.DownloadTask(
            model_id="active-model",
            status="downloading",
            started_at=now,
        )

    save_calls = 0

    def _fake_save_download_tasks() -> None:
        nonlocal save_calls
        acquired = download_manager._download_tasks_lock.acquire(blocking=False)
        try:
            assert acquired, "_save_download_tasks called while download lock is held"
            save_calls += 1
        finally:
            if acquired:
                download_manager._download_tasks_lock.release()

    monkeypatch.setattr(
        download_manager, "_save_download_tasks", _fake_save_download_tasks
    )

    try:
        response = anyio.run(download_manager.get_download_status)

        assert "old-model" not in response.downloads
        assert response.downloads["active-model"].status == "downloading"
        assert save_calls == 1
    finally:
        with download_manager._download_tasks_lock:
            download_manager._download_tasks.clear()
