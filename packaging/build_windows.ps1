$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

# ============================================================
# 1. Kiem tra Python
# ============================================================

if (-not (Get-Command python.exe -ErrorAction SilentlyContinue)) {
    throw 'Khong tim thay python.exe. Hay cai Python 3.11+ truoc.'
}

python.exe -m PyInstaller --version | Out-Host

if ($LASTEXITCODE -ne 0) {
    throw 'Chua cai PyInstaller. Chay: python -m pip install pyinstaller'
}

# ============================================================
# 2. Chuan bi thu muc build
# ============================================================

$BuildDir = Join-Path $Root 'build\windows'
$DistDir  = Join-Path $Root 'dist\windows'

if (Test-Path $BuildDir) {
    Remove-Item $BuildDir -Recurse -Force
}

if (Test-Path $DistDir) {
    Remove-Item $DistDir -Recurse -Force
}

# ============================================================
# 3. Build ung dung bang PyInstaller
# ============================================================

$SpecFile = Join-Path $Root 'packaging\hcmus_hub.spec'

if (-not (Test-Path $SpecFile -PathType Leaf)) {
    throw "Khong tim thay file cau hinh PyInstaller: $SpecFile"
}

python.exe -m PyInstaller `
    --noconfirm `
    --clean `
    --distpath $DistDir `
    --workpath $BuildDir `
    $SpecFile

if ($LASTEXITCODE -ne 0) {
    throw 'PyInstaller build that bai.'
}

Write-Host 'PyInstaller build thanh cong.' -ForegroundColor Green

# ============================================================
# 4. Tim Inno Setup Compiler (ISCC.exe)
# ============================================================

$IsccPath = $null

# Uu tien ISCC.exe da co trong PATH
$IsccCommand = Get-Command ISCC.exe -ErrorAction SilentlyContinue

if ($IsccCommand) {
    $IsccPath = $IsccCommand.Source
}

# Neu khong co trong PATH, thu cac vi tri cai dat pho bien
if (-not $IsccPath) {
    $Candidates = @(
        "$env:LOCALAPPDATA\Programs\Inno Setup 7\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 7\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 7\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
    )

    foreach ($Candidate in $Candidates) {
        if (Test-Path -LiteralPath $Candidate -PathType Leaf) {
            $IsccPath = $Candidate
            break
        }
    }
}

if (-not $IsccPath) {
    throw @'
Khong tim thay Inno Setup Compiler (ISCC.exe).

Hay kiem tra viec cai dat Inno Setup hoac them ISCC.exe vao PATH.
'@
}

Write-Host "Su dung Inno Setup: $IsccPath" -ForegroundColor Cyan

# ============================================================
# 5. Tao bo cai dat Windows
# ============================================================

$IssFile = Join-Path $Root 'packaging\hcmus_hub.iss'

if (-not (Test-Path $IssFile -PathType Leaf)) {
    throw "Khong tim thay file cau hinh Inno Setup: $IssFile"
}

& $IsccPath $IssFile

if ($LASTEXITCODE -ne 0) {
    throw 'Inno Setup build that bai.'
}

# ============================================================
# 6. Kiem tra ket qua
# ============================================================

$InstallerDir = Join-Path $Root 'dist\installer'

if (-not (Test-Path $InstallerDir -PathType Container)) {
    throw "Khong tim thay thu muc bo cai dat: $InstallerDir"
}

$Installers = @(
    Get-ChildItem $InstallerDir -Filter '*.exe' -File
)

if ($Installers.Count -eq 0) {
    throw "Khong tim thay file Setup.exe trong: $InstallerDir"
}

Write-Host ''
Write-Host 'BUILD THANH CONG!' -ForegroundColor Green
Write-Host 'Bo cai dat:' -ForegroundColor Green

$Installers | ForEach-Object {
    Write-Host "  $($_.FullName)" -ForegroundColor Cyan
    Write-Host "  Dung luong: $([math]::Round($_.Length / 1MB, 2)) MB"
}

Write-Host ''