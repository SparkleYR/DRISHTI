<#
.SYNOPSIS
    Start every local DRISHTI service: FastAPI backend, AccessOps dashboard, and
    optionally the Expo physical-test harness.

.DESCRIPTION
    DRISHTI is local-only (AGENTS.md): the phone, the laptop backend, local
    SQLite, and the laptop dashboard all live on one private LAN. This script
    binds the backend to 0.0.0.0 so the phone can reach it at the laptop's LAN
    address, points the dashboard at the backend, and verifies both are actually
    answering before it reports success.

    Nothing here contacts the internet at runtime.

    Targets Windows PowerShell 5.1 (no PS7-only syntax).

.PARAMETER BindHost
    Interface the backend binds to. Default 0.0.0.0 (all interfaces), which is
    what makes the LAN address reachable from the phone.

.PARAMETER BackendPort
    Backend port. Default 8000.

.PARAMETER LanAddress
    The laptop's LAN IP the phone dials. Auto-detected when omitted. Must match
    DEFAULT_BACKEND_URL in the Android client
    (apps/android/.../settings/SettingsStore.kt) or the phone will not connect;
    the script warns when they disagree.

.PARAMETER DashboardPort
    Vite dev-server port. Default 5173.

.PARAMETER WithMobile
    Also start the Expo harness on the LAN. Off by default; the native Android
    client is the real client.

.PARAMETER SkipDashboard
    Start the backend only.

.PARAMETER Stop
    Stop whatever this script previously started, then exit.

.PARAMETER Status
    Report what is running and exit.

.EXAMPLE
    .\scripts\run-drishti.ps1
    .\scripts\run-drishti.ps1 -LanAddress 10.111.36.200
    .\scripts\run-drishti.ps1 -Status
    .\scripts\run-drishti.ps1 -Stop
#>
[CmdletBinding()]
param(
    [string] $BindHost = "0.0.0.0",
    [int]    $BackendPort = 8000,
    [string] $LanAddress,
    [int]    $DashboardPort = 5173,
    [switch] $WithMobile,
    [switch] $SkipDashboard,
    [switch] $Stop,
    [switch] $Status
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$LogDir      = Join-Path $ProjectRoot "logs"
$PidFile     = Join-Path $LogDir "drishti-services.json"
$Python      = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

function Write-Step { param([string] $Message) Write-Host "==> $Message" -ForegroundColor Cyan }
function Write-Ok   { param([string] $Message) Write-Host "    OK   $Message" -ForegroundColor Green }
function Write-Warn2{ param([string] $Message) Write-Host "    !    $Message" -ForegroundColor Yellow }
function Write-Fail { param([string] $Message) Write-Host "    X    $Message" -ForegroundColor Red }

function Get-RecordedServices {
    if (-not (Test-Path $PidFile)) { return @() }
    try {
        return @(Get-Content $PidFile -Raw | ConvertFrom-Json)
    } catch {
        return @()
    }
}

# ---------------------------------------------------------------------------
# -Status
# ---------------------------------------------------------------------------
if ($Status) {
    Write-Step "DRISHTI service status"
    $recorded = Get-RecordedServices
    if ($recorded.Count -eq 0) {
        Write-Warn2 "No services recorded in $PidFile"
    }
    foreach ($entry in $recorded) {
        $process = Get-Process -Id $entry.ProcessId -ErrorAction SilentlyContinue
        if ($process) {
            Write-Ok "$($entry.Name) running (PID $($entry.ProcessId))"
        } else {
            Write-Fail "$($entry.Name) is NOT running (recorded PID $($entry.ProcessId))"
        }
    }
    foreach ($probe in @(
        @{ Label = "Backend health"; Url = "http://127.0.0.1:$BackendPort/api/v1/health" },
        @{ Label = "Dashboard";      Url = "http://127.0.0.1:$DashboardPort/" }
    )) {
        try {
            $response = Invoke-WebRequest -Uri $probe.Url -TimeoutSec 3 -UseBasicParsing
            Write-Ok "$($probe.Label) -> HTTP $($response.StatusCode)"
        } catch {
            Write-Fail "$($probe.Label) -> unreachable"
        }
    }
    exit 0
}

# ---------------------------------------------------------------------------
# -Stop
# ---------------------------------------------------------------------------
if ($Stop) {
    Write-Step "Stopping DRISHTI services"
    $recorded = Get-RecordedServices
    if ($recorded.Count -eq 0) {
        Write-Warn2 "Nothing recorded to stop ($PidFile is absent or empty)."
        exit 0
    }
    foreach ($entry in $recorded) {
        $process = Get-Process -Id $entry.ProcessId -ErrorAction SilentlyContinue
        if ($null -eq $process) {
            Write-Warn2 "$($entry.Name) (PID $($entry.ProcessId)) is already gone."
            continue
        }
        # Kill the whole tree: npm and uvicorn both spawn children.
        & taskkill.exe /PID $entry.ProcessId /T /F 2>&1 | Out-Null
        Write-Ok "Stopped $($entry.Name) (PID $($entry.ProcessId))."
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    exit 0
}

# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------
Write-Step "Preflight"

if (-not (Test-Path $Python)) {
    Write-Fail "Python venv missing at $Python"
    Write-Host  "         Create it, then re-run:"
    Write-Host  "         py -3.12 -m venv .venv; .\.venv\Scripts\pip install -r backend\requirements.txt"
    exit 1
}
Write-Ok "Python venv found."

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# Resolve the LAN address the phone will dial.
if (-not $LanAddress) {
    $candidates = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object {
            $_.IPAddress -ne "127.0.0.1" -and
            $_.IPAddress -notlike "169.254.*" -and
            $_.InterfaceAlias -notmatch "Loopback|vEthernet|VirtualBox|VMware|Hyper-V"
        }
    # Prefer Wi-Fi: the phone is on Wi-Fi, so a wired/host-only NIC is the wrong answer.
    $preferred = $candidates | Where-Object { $_.InterfaceAlias -match "Wi-?Fi|Wireless" } | Select-Object -First 1
    if ($preferred) {
        $LanAddress = $preferred.IPAddress
    } elseif ($candidates) {
        $LanAddress = (@($candidates)[0]).IPAddress
    }
}
if (-not $LanAddress) {
    Write-Warn2 "Could not auto-detect a LAN address; using 127.0.0.1 (the phone will NOT reach the backend)."
    $LanAddress = "127.0.0.1"
} else {
    Write-Ok "LAN address: $LanAddress"
}

$BackendUrl = "http://" + $LanAddress + ":" + $BackendPort

# Warn loudly if the Android client is pinned to a different address.
$SettingsStore = Join-Path $ProjectRoot "apps\android\app\src\main\java\com\drishti\app\settings\SettingsStore.kt"
if (Test-Path $SettingsStore) {
    $match = Select-String -Path $SettingsStore -Pattern 'DEFAULT_BACKEND_URL\s*=\s*"([^"]+)"' | Select-Object -First 1
    if ($match) {
        $androidUrl = $match.Matches[0].Groups[1].Value
        if ($androidUrl.TrimEnd('/') -eq $BackendUrl.TrimEnd('/')) {
            Write-Ok "Android client agrees: $androidUrl"
        } else {
            Write-Warn2 "Android client targets $androidUrl but this run serves $BackendUrl."
            Write-Warn2 "Pass -LanAddress to match, or change the backend URL in the app's settings screen."
        }
    }
}

# Refuse to double-start on an occupied port.
$portChecks = @(@{ Name = "backend"; Port = $BackendPort })
if (-not $SkipDashboard) { $portChecks += @{ Name = "dashboard"; Port = $DashboardPort } }
foreach ($check in $portChecks) {
    $busy = Get-NetTCPConnection -State Listen -LocalPort $check.Port -ErrorAction SilentlyContinue
    if ($busy) {
        Write-Fail "Port $($check.Port) ($($check.Name)) is already in use by PID $(@($busy)[0].OwningProcess)."
        Write-Host  "         Stop the old run first:  .\scripts\run-drishti.ps1 -Stop"
        exit 1
    }
}
Write-Ok "Required ports are free."

$started = @()

function Start-BackgroundService {
    param(
        [string]   $Name,
        [string]   $FilePath,
        [string[]] $ArgumentList,
        [string]   $WorkingDirectory,
        [hashtable]$Environment = @{}
    )
    $log    = Join-Path $LogDir "$Name.log"
    $errLog = Join-Path $LogDir "$Name.err.log"
    foreach ($path in @($log, $errLog)) {
        if (Test-Path $path) { Remove-Item $path -Force }
    }

    # A child inherits this process's environment, so set, spawn, then restore.
    $restore = @{}
    foreach ($key in $Environment.Keys) {
        $restore[$key] = [Environment]::GetEnvironmentVariable($key)
        [Environment]::SetEnvironmentVariable($key, $Environment[$key])
    }
    try {
        $process = Start-Process -FilePath $FilePath `
                                 -ArgumentList $ArgumentList `
                                 -WorkingDirectory $WorkingDirectory `
                                 -RedirectStandardOutput $log `
                                 -RedirectStandardError $errLog `
                                 -WindowStyle Hidden `
                                 -PassThru
    } finally {
        foreach ($key in $restore.Keys) {
            [Environment]::SetEnvironmentVariable($key, $restore[$key])
        }
    }
    Write-Ok "$Name started (PID $($process.Id)) -> $log"
    return [pscustomobject]@{ Name = $Name; ProcessId = $process.Id; Log = $log }
}

function Wait-ForHttp {
    param([string] $Url, [int] $TimeoutSeconds = 120, [string] $Label = "Service")
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -TimeoutSec 3 -UseBasicParsing
            if ($response.StatusCode -eq 200) { return $response }
        } catch {
            Start-Sleep -Milliseconds 700
        }
    }
    throw "$Label did not answer at $Url within $TimeoutSeconds seconds."
}

function Save-ServiceRecord {
    param($Services)
    # PS 5.1 collapses a one-element array to an object; readers re-wrap with @().
    ConvertTo-Json -InputObject @($Services) -Depth 4 | Set-Content $PidFile -Encoding UTF8
}

# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------
Write-Step "Starting backend on ${BindHost}:${BackendPort}"
$started += Start-BackgroundService -Name "backend" `
    -FilePath $Python `
    -ArgumentList @("-m", "uvicorn", "app.main:app", "--app-dir", "backend", "--host", $BindHost, "--port", "$BackendPort") `
    -WorkingDirectory $ProjectRoot

Write-Host "         Loading models (YOLO11n, SegFormer-B0, Tesseract, Moondream2)..." -ForegroundColor DarkGray
try {
    $health = Wait-ForHttp -Url "http://127.0.0.1:$BackendPort/api/v1/health" -Label "Backend"
} catch {
    Write-Fail $_.Exception.Message
    Write-Host  "         Log: $(Join-Path $LogDir 'backend.log')"
    Save-ServiceRecord $started
    exit 1
}

$healthJson = $health.Content | ConvertFrom-Json
Write-Ok "Backend healthy: status=$($healthJson.status) device=$($healthJson.compute.device_name)"
foreach ($model in $healthJson.models.PSObject.Properties) {
    $tone = "DarkGray"
    if ($model.Value.status -ne "READY") { $tone = "Yellow" }
    Write-Host ("         {0,-15} {1}" -f $model.Name, $model.Value.status) -ForegroundColor $tone
}
if (-not $healthJson.walk_mode_available) {
    Write-Warn2 "walk_mode_available is false - the phone cannot start Walk Mode."
}

# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
$npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $npmCommand) { $npmCommand = Get-Command npm -ErrorAction SilentlyContinue }

if (-not $SkipDashboard) {
    Write-Step "Starting AccessOps dashboard on port $DashboardPort"
    if (-not $npmCommand) {
        Write-Fail "npm not found on PATH; skipping the dashboard."
    } else {
        # Vite reads VITE_* from the process environment when the dev server boots.
        # The dashboard runs on this laptop, so it dials the backend over loopback.
        $started += Start-BackgroundService -Name "dashboard" `
            -FilePath $npmCommand.Source `
            -ArgumentList @("run", "dev", "--workspace", "apps/dashboard", "--", "--port", "$DashboardPort") `
            -WorkingDirectory $ProjectRoot `
            -Environment @{ VITE_API_BASE_URL = "http://127.0.0.1:$BackendPort" }
        try {
            Wait-ForHttp -Url "http://127.0.0.1:$DashboardPort/" -TimeoutSeconds 60 -Label "Dashboard" | Out-Null
            Write-Ok "Dashboard serving at http://127.0.0.1:$DashboardPort"
        } catch {
            Write-Warn2 $_.Exception.Message
            Write-Warn2 "Check $(Join-Path $LogDir 'dashboard.log')"
        }
    }
}

# ---------------------------------------------------------------------------
# Expo harness (opt-in)
# ---------------------------------------------------------------------------
if ($WithMobile) {
    Write-Step "Starting Expo physical-test harness (LAN)"
    if (-not $npmCommand) {
        Write-Fail "npm not found on PATH; skipping Expo."
    } else {
        $started += Start-BackgroundService -Name "mobile" `
            -FilePath $npmCommand.Source `
            -ArgumentList @("run", "start", "--workspace", "apps/mobile", "--", "--lan") `
            -WorkingDirectory $ProjectRoot `
            -Environment @{ EXPO_PUBLIC_API_BASE_URL = $BackendUrl }
        Write-Ok "Expo starting; the QR code appears in $(Join-Path $LogDir 'mobile.log')"
    }
}

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
Save-ServiceRecord $started

Write-Host ""
Write-Step "DRISHTI is up"
Write-Host  "    Backend (phone dials this)   $BackendUrl"
Write-Host  "    Backend (this laptop)        http://127.0.0.1:$BackendPort"
Write-Host  "    Health                       http://127.0.0.1:$BackendPort/api/v1/health"
Write-Host  "    API docs                     http://127.0.0.1:$BackendPort/docs"
if (-not $SkipDashboard) {
    Write-Host "    Dashboard                    http://127.0.0.1:$DashboardPort"
}
Write-Host ""
Write-Host  "    Logs                         $LogDir"
Write-Host  "    Check status                 .\scripts\run-drishti.ps1 -Status"
Write-Host  "    Stop everything              .\scripts\run-drishti.ps1 -Stop"
Write-Host ""
Write-Host  "    The phone and this laptop must share one Wi-Fi network. If the" -ForegroundColor DarkGray
Write-Host  "    phone cannot reach $BackendUrl, allow python.exe on Private" -ForegroundColor DarkGray
Write-Host  "    networks in Windows Defender Firewall." -ForegroundColor DarkGray
