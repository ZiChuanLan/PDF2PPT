from __future__ import annotations

import time
import subprocess
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


def test_sam_runtime_package_url_supports_env_override(monkeypatch) -> None:
    monkeypatch.delenv("MOBILE_SAM_PACKAGE_URL", raising=False)
    monkeypatch.delenv("SAM_PACKAGE_URL", raising=False)

    monkeypatch.setenv("SAM_PACKAGE_URL", "https://mirror.example/mobilesam.zip")
    assert sam_provider.get_sam_package_url() == "https://mirror.example/mobilesam.zip"

    monkeypatch.setenv("MOBILE_SAM_PACKAGE_URL", "https://cdn.example/mobilesam.zip")
    assert sam_provider.get_sam_package_url() == "https://cdn.example/mobilesam.zip"


def test_sam_runtime_target_uses_app_data_dir(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("MOBILE_SAM_RUNTIME_TARGET", raising=False)
    monkeypatch.delenv("SAM_RUNTIME_TARGET", raising=False)
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path))

    assert (
        sam_provider.get_sam_runtime_target_path()
        == tmp_path / "python-packages" / "sam-runtime"
    )


def test_sam_runtime_install_uses_persistent_target_and_urls(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MOBILE_SAM_PACKAGE_URL", "https://cdn.example/mobilesam.zip")
    monkeypatch.setenv("PYTORCH_CPU_INDEX_URL", "https://torch.example/cpu")
    runtime_checks = iter([["mobile_sam_not_installed"], []])
    run_calls: list[list[str]] = []
    progress: list[tuple[float | None, str | None]] = []

    monkeypatch.setattr(
        sam_provider,
        "get_sam_runtime_issues",
        lambda: next(runtime_checks, []),
    )

    def fake_run(
        cmd: list[str],
        *,
        check: bool,
        text: bool,
        capture_output: bool,
    ) -> subprocess.CompletedProcess[str]:
        run_calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(sam_provider.subprocess, "run", fake_run)

    installed = sam_provider.install_sam_runtime_dependencies(
        progress_callback=lambda value, message: progress.append((value, message))
    )

    assert installed is True
    assert run_calls
    cmd = run_calls[0]
    assert "--target" in cmd
    assert str(tmp_path / "python-packages" / "sam-runtime") in cmd
    assert "--extra-index-url" in cmd
    assert "https://torch.example/cpu" in cmd
    assert "torch==2.12.0+cpu" in cmd
    assert "torchvision==0.27.0+cpu" in cmd
    assert "timm==1.0.27" in cmd
    assert "https://cdn.example/mobilesam.zip" in cmd
    assert progress[0] == (0.0, "正在下载 SAM 运行依赖…")
    assert progress[-1] == (0.2, "SAM 运行依赖安装完成")


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
    assert "MOBILE_SAM_PACKAGE_URL" in message
    assert "PYTORCH_CPU_INDEX_URL" in message


def test_background_sam_download_installs_runtime_checkpoint_and_verifies(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path))
    events: list[str] = []

    def fake_install(progress_callback=None) -> bool:
        events.append("runtime")
        if progress_callback is not None:
            progress_callback(0.2, "runtime ready")
        return True

    def fake_download(path, reporthook=None) -> None:
        events.append("checkpoint")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"checkpoint")
        if reporthook is not None:
            reporthook(1, 1, 1)

    def fake_ensure_model():
        events.append("verify")
        return object()

    monkeypatch.setattr(
        sam_provider, "install_sam_runtime_dependencies", fake_install
    )
    monkeypatch.setattr(sam_provider, "_download_checkpoint", fake_download)
    monkeypatch.setattr(sam_provider, "_ensure_model", fake_ensure_model)
    monkeypatch.setattr(sam_provider, "get_sam_checkpoint_source_path", lambda: None)

    with download_manager._download_tasks_lock:
        download_manager._download_tasks.clear()
        download_manager._download_tasks["sam"] = download_manager.DownloadTask(
            model_id="sam"
        )

    try:
        download_manager._background_download_sam("sam")

        with download_manager._download_tasks_lock:
            task = download_manager._download_tasks["sam"]
            assert task.status == "completed"
            assert task.progress == 1.0
            assert task.message == "下载并验证完成"
        assert events == ["runtime", "checkpoint", "verify"]
    finally:
        with download_manager._download_tasks_lock:
            download_manager._download_tasks.clear()


def test_delete_sam_removes_checkpoint_and_runtime_cache(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path))
    sam_dir = tmp_path / "models" / "sam"
    runtime_dir = tmp_path / "python-packages" / "sam-runtime"
    sam_dir.mkdir(parents=True)
    runtime_dir.mkdir(parents=True)
    (sam_dir / "mobile_sam.pt").write_bytes(b"checkpoint")
    (runtime_dir / "mobile_sam.py").write_text("# runtime", encoding="utf-8")

    with download_manager._download_tasks_lock:
        download_manager._download_tasks.clear()

    response = anyio.run(
        download_manager.delete_model,
        download_manager.ModelDeleteRequest(model="sam"),
        object(),
    )

    assert response.success is True
    assert not sam_dir.exists()
    assert not runtime_dir.exists()


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
