# Windows EXE 打包与使用

这个项目是 `web + api + worker + redis` 的多服务架构，推荐用 Docker Compose 运行。  
这里提供了一个 **Windows 启动器 EXE**，用于一键启动/停止服务。

## 先决条件

- Windows 10/11
- 已安装并启动 Docker Desktop
- 命令行可用 `docker compose`
- 已安装 Python 3.10+（仅打包时需要）

## 打包 EXE

在项目根目录执行（PowerShell）：

```powershell
.\packaging\windows\build_exe.ps1
```

或（CMD）：

```bat
packaging\windows\build_exe.bat
```

生成文件：

```text
release/windows/PPT-OpenCode-Launcher.exe
```

## 使用 EXE

默认双击（或命令行不带参数）= `start`：

```bat
PPT-OpenCode-Launcher.exe
```

常用命令：

```bat
PPT-OpenCode-Launcher.exe start
PPT-OpenCode-Launcher.exe stop
PPT-OpenCode-Launcher.exe restart
PPT-OpenCode-Launcher.exe status
PPT-OpenCode-Launcher.exe logs --lines 200
```

可选参数：

- `--timeout 180` 启动等待秒数
- `--no-browser` 启动后不自动打开浏览器

## 说明

- 该 EXE 是“启动器”，不会把 Docker/模型环境打进一个单文件应用。
- 运行后服务入口：
  - 前端：`http://127.0.0.1:3000`
  - API：`http://127.0.0.1:8000`
