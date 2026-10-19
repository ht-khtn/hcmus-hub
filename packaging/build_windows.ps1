$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Get-Command python.exe -ErrorAction SilentlyContinue)) {
    throw 'Khong tim thay python.exe. Hay cai Python 3.11+ truoc.'
}
python.exe -m PyInstaller --version | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw 'Chua cai PyInstaller. Chay: python -m pip install pyinstaller'
}

$BuildDir = Join-Path $Root 'build\windows'
$DistDir = Join-Path $Root 'dist\windows'
if (Test-Path $BuildDir) { Remove-Item $BuildDir -Recurse -Force }
if (Test-Path $DistDir) { Remove-Item $DistDir -Recurse -Force }

python.exe -m PyInstaller `
    --noconfirm `
    --clean `
    --distpath $DistDir `
    --workpath $BuildDir `
    (Join-Path $Root 'packaging\hcmus_hub.spec')
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build that bai.' }

$Iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if (-not $Iscc) {
    throw 'Khong tim thay Inno Setup (ISCC.exe). Cai Inno Setup roi chay lai script nay.'
}
& $Iscc.Source (Join-Path $Root 'packaging\hcmus_hub.iss')
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup build that bai.' }
Write-Host 'Da tao bo cai dat trong dist\installer.' -ForegroundColor Green
