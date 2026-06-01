$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot

function Get-BackendPython {
    $venvPython = Join-Path $Root "backend\.venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return $venvPython
    }
    return "python"
}

$python = Get-BackendPython
$backendDir = Join-Path $Root "backend"
$frontendDir = Join-Path $Root "frontend"

if (-not (Test-Path $backendDir)) {
    throw "Backend klasörü bulunamadı: $backendDir"
}

if (-not (Test-Path $frontendDir)) {
    throw "Frontend klasörü bulunamadı: $frontendDir"
}

$backendCommand = @"
Set-Location '$backendDir'
Write-Host 'Backend: http://localhost:8000' -ForegroundColor Cyan
& '$python' -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
"@

$frontendCommand = @"
Set-Location '$frontendDir'
Write-Host 'Frontend: http://localhost:5173' -ForegroundColor Green
npm run dev
"@

Write-Host "Local CV Analyzer geliştirme sunucuları başlatılıyor..." -ForegroundColor Yellow
Write-Host "Backend  -> http://localhost:8000"
Write-Host "Frontend -> http://localhost:5173"
Write-Host ""
Write-Host "Her iki servis ayrı pencerede açılacak. Durdurmak için o pencereleri kapatın."
Write-Host ""

Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCommand
Start-Sleep -Seconds 1
Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCommand

Write-Host "Sunucular başlatıldı."
