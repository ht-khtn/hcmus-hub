[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('dashboard', 'sync', 'share-publish', 'share-pull', 'help')]
    [string]$Action = 'dashboard',

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CommandArgs = @()
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = $PSScriptRoot
$EnvPath = Join-Path $ProjectRoot '.env'
$ExamplePath = Join-Path $ProjectRoot '.env.example'
$GitIgnorePath = Join-Path $ProjectRoot '.gitignore'

if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot 'hcmus_hub'))) {
    throw 'Khong tim thay thu muc hcmus_hub. Hay dat file nay vao thu muc goc D:\app\hcmus-hub.'
}

function Read-DotEnvFile {
    param([string]$Path)
    $result = @{}
    if (-not (Test-Path -LiteralPath $Path)) { return ,$result }

    foreach ($rawLine in Get-Content -LiteralPath $Path) {
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith('#')) { continue }
        $equals = $line.IndexOf('=')
        if ($equals -le 0) { continue }

        $name = $line.Substring(0, $equals).Trim()
        $value = $line.Substring($equals + 1).Trim()
        if ($value.Length -ge 2) {
            if (($value.StartsWith('"') -and $value.EndsWith('"')) -or
                ($value.StartsWith("'") -and $value.EndsWith("'"))) {
                $value = $value.Substring(1, $value.Length - 2)
            }
        }
        $result[$name] = $value
    }
    return ,$result
}

function Write-DotEnvFile {
    param(
        [string]$Path,
        [string]$AutoPublish,
        [string]$Token
    )
    $content = "HUB_AUTO_PUBLISH=$AutoPublish`r`nHUB_WRITE_TOKEN=$Token`r`n"
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $content, $utf8NoBom)
}

function Normalize-AutoPublish {
    param([string]$Value)
    if ($Value -match '^(1|true|yes|on)$') { return '1' }
    return '0'
}

# Respect the current PowerShell process first, then the saved .env, then the
# Windows user environment. On first setup, persist existing values into .env.
$existing = Read-DotEnvFile -Path $EnvPath
$processToken = [Environment]::GetEnvironmentVariable('HUB_WRITE_TOKEN', 'Process')
$userToken = [Environment]::GetEnvironmentVariable('HUB_WRITE_TOKEN', 'User')
$token = if (-not [string]::IsNullOrWhiteSpace($processToken)) {
    $processToken
} elseif (-not [string]::IsNullOrWhiteSpace([string]$existing['HUB_WRITE_TOKEN'])) {
    [string]$existing['HUB_WRITE_TOKEN']
} else {
    $userToken
}

$processAuto = [Environment]::GetEnvironmentVariable('HUB_AUTO_PUBLISH', 'Process')
$userAuto = [Environment]::GetEnvironmentVariable('HUB_AUTO_PUBLISH', 'User')
$autoValue = if (-not [string]::IsNullOrWhiteSpace($processAuto)) {
    $processAuto
} elseif (-not [string]::IsNullOrWhiteSpace([string]$existing['HUB_AUTO_PUBLISH'])) {
    [string]$existing['HUB_AUTO_PUBLISH']
} elseif (-not [string]::IsNullOrWhiteSpace($userAuto)) {
    $userAuto
} else {
    '1'
}
$autoPublish = Normalize-AutoPublish -Value $autoValue

if ([string]::IsNullOrWhiteSpace($token)) {
    $secureToken = Read-Host 'Nhap HUB_WRITE_TOKEN (ky tu se duoc an)' -AsSecureString
    $bstr = [IntPtr]::Zero
    try {
        $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
        $token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    } finally {
        if ($bstr -ne [IntPtr]::Zero) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
        }
    }
    if ([string]::IsNullOrWhiteSpace($token)) {
        throw 'Chua co HUB_WRITE_TOKEN. Da dung truoc khi chay lenh.'
    }
}

# Store the configuration locally for future PowerShell sessions.
if (-not (Test-Path -LiteralPath $EnvPath) -or
    [string]::IsNullOrWhiteSpace([string]$existing['HUB_WRITE_TOKEN']) -or
    [string]::IsNullOrWhiteSpace([string]$existing['HUB_AUTO_PUBLISH'])) {
    Write-DotEnvFile -Path $EnvPath -AutoPublish $autoPublish -Token $token
}

# Load .env values only when an environment variable is not already set.
$envValues = Read-DotEnvFile -Path $EnvPath
foreach ($name in @('HUB_AUTO_PUBLISH', 'HUB_WRITE_TOKEN')) {
    $current = [Environment]::GetEnvironmentVariable($name, 'Process')
    if ([string]::IsNullOrWhiteSpace($current) -and
        -not [string]::IsNullOrWhiteSpace([string]$envValues[$name])) {
        [Environment]::SetEnvironmentVariable($name, [string]$envValues[$name], 'Process')
    }
}
# Normalize accepted boolean spellings to the exact 1/0 values expected by Python.
[Environment]::SetEnvironmentVariable('HUB_AUTO_PUBLISH', $autoPublish, 'Process')

# Keep .env out of Git without overwriting the user's existing ignore rules.
if (-not (Test-Path -LiteralPath $GitIgnorePath)) {
    [System.IO.File]::WriteAllText($GitIgnorePath, ".env`r`n")
} else {
    $ignoreLines = @(Get-Content -LiteralPath $GitIgnorePath)
    $hasEnvIgnore = $false
    foreach ($ignoreLine in $ignoreLines) {
        if ($ignoreLine.Trim() -in @('.env', '/.env')) { $hasEnvIgnore = $true; break }
    }
    if (-not $hasEnvIgnore) {
        Add-Content -LiteralPath $GitIgnorePath -Value '.env'
    }
}

if (-not (Test-Path -LiteralPath $ExamplePath)) {
    $example = "# Copy to .env and fill in local settings.`r`nHUB_AUTO_PUBLISH=0`r`nHUB_WRITE_TOKEN=`r`n"
    [System.IO.File]::WriteAllText($ExamplePath, $example)
}

Set-Location -LiteralPath $ProjectRoot

switch ($Action) {
    'dashboard' {
        $launcher = Join-Path $ProjectRoot 'start-dashboard.ps1'
        if (-not (Test-Path -LiteralPath $launcher)) {
            throw 'Khong tim thay start-dashboard.ps1 trong thu muc goc du an.'
        }
        Write-Host 'Dang khoi dong dashboard (HUB_AUTO_PUBLISH da duoc nap).' 
        & $launcher @CommandArgs
        break
    }
    'sync' {
        & python.exe -m hcmus_hub sync @CommandArgs
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        break
    }
    'share-publish' {
        & python.exe -m hcmus_hub share-publish @CommandArgs
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        break
    }
    'share-pull' {
        & python.exe -m hcmus_hub share-pull @CommandArgs
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        break
    }
    'help' {
        @'
Usage:
  .\hcmus-hub.ps1                       Start dashboard
  .\hcmus-hub.ps1 sync                  Run incremental sync (auto-publish if enabled)
  .\hcmus-hub.ps1 sync --full-rescan    Run full rescan
  .\hcmus-hub.ps1 share-pull            Pull cloud snapshot (preview/default behavior follows CLI)
  .\hcmus-hub.ps1 share-publish         Publish manually
  .\hcmus-hub.ps1 help                  Show this help

Config: .env (HUB_AUTO_PUBLISH, HUB_WRITE_TOKEN)
Current-process environment variables override .env.
'@ | Write-Host
        break
    }
}
