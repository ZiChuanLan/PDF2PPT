$ErrorActionPreference = "Stop"

Write-Host "[1/4] Installing PyInstaller..."
python -m pip install --upgrade pyinstaller

Write-Host "[2/4] Building launcher exe..."
python -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --name "PPT-OpenCode-Launcher" `
  packaging/windows/app_launcher.py

Write-Host "[3/4] Copying output..."
New-Item -ItemType Directory -Path "release/windows" -Force | Out-Null
Copy-Item "dist/PPT-OpenCode-Launcher.exe" "release/windows/PPT-OpenCode-Launcher.exe" -Force

Write-Host "[4/4] Done."
Write-Host "Output: release/windows/PPT-OpenCode-Launcher.exe"
