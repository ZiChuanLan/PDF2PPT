@echo off
setlocal

echo [1/4] Installing PyInstaller...
python -m pip install --upgrade pyinstaller
if errorlevel 1 (
  echo Failed to install pyinstaller.
  exit /b 1
)

echo [2/4] Building launcher exe...
python -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --name PPT-OpenCode-Launcher ^
  packaging/windows/app_launcher.py
if errorlevel 1 (
  echo Build failed.
  exit /b 1
)

echo [3/4] Copying output...
if not exist release\windows mkdir release\windows
copy /Y dist\PPT-OpenCode-Launcher.exe release\windows\PPT-OpenCode-Launcher.exe >nul

echo [4/4] Done.
echo Output: release\windows\PPT-OpenCode-Launcher.exe
endlocal
