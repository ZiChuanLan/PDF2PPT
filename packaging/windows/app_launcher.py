#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path
from typing import Sequence


def _find_project_root() -> Path:
    candidates: list[Path] = []

    try:
        candidates.append(Path.cwd())
    except Exception:
        pass

    exe_path = Path(sys.executable).resolve()
    script_path = Path(__file__).resolve()
    candidates.extend(
        [
            exe_path.parent,
            exe_path.parent.parent,
            script_path.parent,
            script_path.parent.parent,
            script_path.parent.parent.parent,
        ]
    )

    checked: set[Path] = set()
    for candidate in candidates:
        if candidate in checked:
            continue
        checked.add(candidate)
        if (candidate / "docker-compose.yml").exists():
            return candidate

    raise RuntimeError(
        "未找到项目根目录（缺少 docker-compose.yml）。请在项目目录运行该程序。"
    )


def _pick_compose_cmd() -> list[str]:
    probes = [["docker", "compose", "version"], ["docker-compose", "version"]]
    for probe in probes:
        try:
            result = subprocess.run(
                probe,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            if result.returncode == 0:
                return probe[:2] if probe[0] == "docker" else [probe[0]]
        except FileNotFoundError:
            continue

    raise RuntimeError(
        "未检测到 Docker Compose。请先安装 Docker Desktop 并确保命令行可用。"
    )


def _run(
    cmd: Sequence[str],
    *,
    cwd: Path,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(cmd),
        cwd=str(cwd),
        text=True,
        check=False,
        capture_output=capture,
    )


def _check_http(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            code = int(getattr(resp, "status", 0) or 0)
            return 200 <= code < 500
    except Exception:
        return False


def _wait_services(timeout_seconds: int) -> bool:
    started = time.time()
    while time.time() - started < timeout_seconds:
        api_ok = _check_http("http://127.0.0.1:8000/health")
        web_ok = _check_http("http://127.0.0.1:3000")
        if api_ok and web_ok:
            return True
        time.sleep(2)
    return False


def _print_header(title: str) -> None:
    print("=" * 60)
    print(title)
    print("=" * 60)


def cmd_start(project_root: Path, compose_cmd: list[str], timeout: int, open_browser: bool) -> int:
    _print_header("PPT OpenCode 启动器")
    print(f"项目目录: {project_root}")
    print("正在启动服务（web/api/worker/redis）...")

    result = _run([*compose_cmd, "up", "-d", "--build"], cwd=project_root)
    if result.returncode != 0:
        print("启动失败，请检查 Docker Desktop 是否已启动。")
        return result.returncode or 1

    print("服务已提交启动，正在等待就绪...")
    ready = _wait_services(timeout)
    if not ready:
        print(f"等待超时（{timeout}s）。你可以运行 logs 查看详情。")
        return 2

    print("服务已就绪: http://127.0.0.1:3000")
    if open_browser:
        webbrowser.open("http://127.0.0.1:3000")
    return 0


def cmd_stop(project_root: Path, compose_cmd: list[str]) -> int:
    _print_header("停止服务")
    result = _run([*compose_cmd, "down"], cwd=project_root)
    if result.returncode == 0:
        print("已停止并移除容器。")
    else:
        print("停止失败，请手动执行 docker compose down。")
    return result.returncode or 0


def cmd_restart(project_root: Path, compose_cmd: list[str], timeout: int, open_browser: bool) -> int:
    stop_code = cmd_stop(project_root, compose_cmd)
    if stop_code != 0:
        return stop_code
    return cmd_start(project_root, compose_cmd, timeout, open_browser)


def cmd_status(project_root: Path, compose_cmd: list[str]) -> int:
    _print_header("服务状态")
    result = _run([*compose_cmd, "ps"], cwd=project_root)
    return result.returncode or 0


def cmd_logs(project_root: Path, compose_cmd: list[str], lines: int) -> int:
    _print_header("最近日志")
    result = _run(
        [*compose_cmd, "logs", "--tail", str(max(1, lines))],
        cwd=project_root,
    )
    return result.returncode or 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ppt-opencode-launcher",
        description="PPT OpenCode Windows 启动器（可打包为 EXE）",
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="start",
        choices=["start", "stop", "restart", "status", "logs"],
        help="默认 start",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=180,
        help="启动等待秒数（默认 180）",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="启动后不自动打开浏览器",
    )
    parser.add_argument(
        "--lines",
        type=int,
        default=120,
        help="logs 命令输出行数（默认 120）",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        project_root = _find_project_root()
        compose_cmd = _pick_compose_cmd()
    except Exception as exc:
        print(f"[错误] {exc}")
        return 1

    os.environ.setdefault("COMPOSE_CONVERT_WINDOWS_PATHS", "1")

    if args.command == "start":
        return cmd_start(project_root, compose_cmd, args.timeout, not args.no_browser)
    if args.command == "stop":
        return cmd_stop(project_root, compose_cmd)
    if args.command == "restart":
        return cmd_restart(project_root, compose_cmd, args.timeout, not args.no_browser)
    if args.command == "status":
        return cmd_status(project_root, compose_cmd)
    if args.command == "logs":
        return cmd_logs(project_root, compose_cmd, args.lines)

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
