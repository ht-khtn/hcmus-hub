$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Db = Join-Path $Root 'data\hcmus_hub.sqlite3'
$Config = Join-Path $Root 'config\sources.json'
$VenvPython = Join-Path $Root '.venv\Scripts\python.exe'

if (-not (Test-Path $Db)) {
    throw "Khong tim thay CSDL hien tai: $Db. Script khong tao CSDL moi de tranh lam ban tuong da cap nhat du lieu cu."
}
if (-not (Test-Path $Config)) { throw "Khong tim thay cau hinh: $Config" }
if (Test-Path $VenvPython) {
    $Python = $VenvPython
} else {
    $PythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    if (-not $PythonCommand) { throw 'Khong tim thay python.exe. Hay cai Python hoac tao .venv.' }
    $Python = $PythonCommand.Source
}
Set-Location $Root
Write-Host 'Dang audit, sao luu, repair an toan, dong bo toi da 1000 URL/danh muc va lam giau toan bo bai yeu du lieu...' -ForegroundColor Cyan
Write-Host 'Luu y: tai chi tiet toi da 30 bai moi moi nguon trong mot luot; phan lam giau cu se duyet tat ca bai yeu du lieu, nen co the mat nhieu thoi gian.' -ForegroundColor DarkGray
& $Python -m hcmus_hub run-all --config $Config --db $Db --delay 1.0 --max-details 30 --max-items-per-listing 1000 --enrich-details all
if ($LASTEXITCODE -ne 0) { throw "Run-all ket thuc voi ma loi $LASTEXITCODE" }
Write-Host 'Hoan tat. Xem thu muc data\runs\run-* moi nhat, file run-report.md va quality\quality-report.md.' -ForegroundColor Green
