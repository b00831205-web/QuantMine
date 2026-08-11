# Build the production frontend, refresh WSL runtimes, and restart QuantMine.
# Run from Windows PowerShell; the WSL distribution is always explicit.
param(
    [string]$Distro = "Ubuntu",
    [switch]$Offline,
    [switch]$SkipRuntimeSync
)

$ErrorActionPreference = "Stop"
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$frontend = Join-Path $repo "frontend"
$dist = Join-Path $frontend "dist"
$static = Join-Path $repo "webapi\app\static"

Write-Host "Building the production frontend..."
Push-Location $frontend
try {
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend build failed ($LASTEXITCODE)" }
} finally {
    Pop-Location
}

New-Item -ItemType Directory -Force -Path $static | Out-Null
& robocopy $dist $static /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -gt 7) { throw "Frontend deployment failed (robocopy $LASTEXITCODE)" }

if ($repo -notmatch '^([A-Za-z]):\\(.*)$') {
    throw "Expected a drive-letter Windows path, got: $repo"
}
$drive = $Matches[1].ToLowerInvariant()
$tail = $Matches[2].Replace('\', '/')
$wslRepo = "/mnt/$drive/$tail"
if ($wslRepo.Contains("'")) {
    throw "Repository paths containing an apostrophe are not supported: $wslRepo"
}

if (-not $SkipRuntimeSync) {
    $syncArg = if ($Offline) { " --offline" } else { "" }
    Write-Host "Refreshing isolated Ubuntu runtime environments..."
    & wsl.exe -d $Distro -- bash -lc "cd '$wslRepo' && bash deploy/sync-runtime-envs.sh$syncArg"
    if ($LASTEXITCODE -ne 0) { throw "WSL runtime synchronization failed ($LASTEXITCODE)" }
}

Write-Host "Installing/restarting systemd user services..."
& wsl.exe -d $Distro -- bash -lc "cd '$wslRepo' && bash deploy/install-services.sh"
if ($LASTEXITCODE -ne 0) { throw "Service restart failed ($LASTEXITCODE)" }

$health = $null
for ($attempt = 1; $attempt -le 30; $attempt++) {
    try {
        $health = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8000/api/v1/health" -TimeoutSec 3
        if ($health.StatusCode -eq 200) { break }
    } catch {
        Start-Sleep -Seconds 2
    }
}
if (-not $health -or $health.StatusCode -ne 200) {
    throw "Service did not become healthy at http://localhost:8000 within 60 seconds."
}

Write-Host "Ready: http://localhost:8000" -ForegroundColor Green
