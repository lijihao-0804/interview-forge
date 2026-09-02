[CmdletBinding()]
param(
    [int]$Port = 8765,
    [switch]$Quiet
)

$ErrorActionPreference = "SilentlyContinue"

function Write-Info {
    param([string]$Message)
    if (-not $Quiet) {
        Write-Host $Message
    }
}

# First pass: kill every python process whose command line clearly mentions the site server.
$studyProcs = @(
    Get-CimInstance Win32_Process |
        Where-Object {
            $_.Name -like "python*" -and
            $_.CommandLine -like "*study_server.py*"
        }
)

foreach ($proc in $studyProcs) {
    Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
    Write-Info "[Info] Killed old study server PID $($proc.ProcessId)"
}

Start-Sleep -Milliseconds 800

# Second pass: whatever still listens on the dedicated port must go away before a new server starts.
$listeners = @(
    Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
)

foreach ($conn in $listeners) {
    $ownerPid = $conn.OwningProcess
    $owner = Get-CimInstance Win32_Process -Filter "ProcessId=$ownerPid" -ErrorAction SilentlyContinue
    if (-not $owner) {
        continue
    }

    $cmdLine = [string]$owner.CommandLine
    $procName = [string]$owner.Name
    $isPython = $procName -like "python*" -or $procName -ieq "py.exe"

    if ($cmdLine -like "*study_server.py*" -or ($isPython -and $cmdLine.Length -eq 0)) {
        Stop-Process -Id $ownerPid -Force -ErrorAction SilentlyContinue
        Write-Info "[Info] Killed old study server PID $ownerPid"
    }
    else {
        Write-Info "[Info] Port $Port used by PID $ownerPid ($procName); not study_server.py, skip"
        exit 1
    }
}

Start-Sleep -Milliseconds 800

$stillListening = @(
    Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
)

if ($stillListening.Count -gt 0) {
    Write-Info "[Info] Port $Port is still in use by another process."
    Write-Info "Please close that process manually, then start again."
    exit 1
}

exit 0
