$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Db = Join-Path $Root 'data\hcmus_hub.sqlite3'
$VenvPython = Join-Path $Root '.venv\Scripts\python.exe'

if (-not (Test-Path $Db)) {
    throw "Khong tim thay CSDL: $Db. Hay dat CSDL hien tai vao data\hcmus_hub.sqlite3 truoc."
}
if (Test-Path $VenvPython) {
    $Python = $VenvPython
} else {
    $PythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    if (-not $PythonCommand) { throw 'Khong tim thay python.exe. Hay cai Python hoac tao .venv.' }
    $Python = $PythonCommand.Source
}
Set-Location $Root
Write-Host 'HCMUS Hub dashboard se mo tai http://127.0.0.1:8787' -ForegroundColor Cyan
Write-Host 'Giu cua so nay mo; nhan Ctrl+C de dung.'
& $Python -m hcmus_hub web --db $Db --host 127.0.0.1 --port 8787
if ($LASTEXITCODE -ne 0) { throw "Dashboard ket thuc voi ma loi $LASTEXITCODE" }
