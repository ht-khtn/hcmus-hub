$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$ConfigPath = Join-Path $Root 'config\sources.json'

if (-not (Test-Path -LiteralPath $ConfigPath)) {
    throw "Khong tim thay file cau hinh: $ConfigPath"
}

$Config = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
$FitSources = @($Config.sources | Where-Object { $_.id -eq 'fit' })
if ($FitSources.Count -ne 1) {
    throw "Can dung chinh xac mot nguon co id='fit'; khong thay doi file cau hinh."
}

$Fit = $FitSources[0]
$Current = [int]$Fit.max_pages
if ($Current -ge 5) {
    Write-Host "FIT max_pages da la $Current; khong can thay doi." -ForegroundColor Green
    exit 0
}

$BackupPath = "$ConfigPath.bak-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
Copy-Item -LiteralPath $ConfigPath -Destination $BackupPath
$Fit.max_pages = 5
$Json = $Config | ConvertTo-Json -Depth 100
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($ConfigPath, ($Json + [Environment]::NewLine), $Utf8NoBom)
Write-Host "Da cap nhat FIT max_pages: $Current -> 5" -ForegroundColor Green
Write-Host "Ban sao luu: $BackupPath" -ForegroundColor Cyan
