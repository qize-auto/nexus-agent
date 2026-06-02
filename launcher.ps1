$Host.UI.RawUI.WindowTitle = "NexusAgent Desktop v3.3"
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  NexusAgent Desktop v3.3" -ForegroundColor White
Write-Host "  Personal AI Agent System" -ForegroundColor Gray
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Set-Location "$PSScriptRoot"

try { $null = python --version 2>&1 } catch {
    Write-Host "[ERROR] Python not found" -ForegroundColor Red
    Read-Host "Press Enter"; exit 1
}

$pyqtOk = python -c "from PyQt6.QtWidgets import QApplication; import aiohttp" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "[INSTALL] Installing dependencies..." -ForegroundColor Yellow
    python -m pip install PyQt6 PyQt6-WebEngine aiohttp cryptography python-dotenv pyyaml -q
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[FAILED] pip install PyQt6 PyQt6-WebEngine" -ForegroundColor Red
        Read-Host "Press Enter"; exit 1
    }
}

Write-Host "[START] Launching..." -ForegroundColor Green
python run_desktop.py

Read-Host "Press Enter"
