# Stop this repository's local web processes and databases; preserve all volumes.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Use-LocalLab.ps1')

$labStateDirectory = Join-Path $labRepositoryRoot '.local-replication/mcf-todicode'
$labPython = [IO.Path]::GetFullPath((Join-Path $labRepositoryRoot '.venv/Scripts/python.exe'))
$labProcesses = @()

foreach ($labRecordName in @('web.json', 'proxy.json')) {
    $labRecordPath = Join-Path $labStateDirectory $labRecordName
    if (-not (Test-Path -LiteralPath $labRecordPath)) { continue }
    $labRecord = Get-Content -Raw -LiteralPath $labRecordPath | ConvertFrom-Json
    $labEntries = if ($labRecordName -eq 'web.json') { @($labRecord.aws, $labRecord.azure) } else { @($labRecord) }
    foreach ($labEntry in $labEntries) {
        $labProcessId = [int]$labEntry.pid
        $labProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $labProcessId"
        if (-not $labProcess) { continue }
        $labModule = if ($labRecordName -eq 'web.json') { 'app.main:app' } else { 'app.local_proxy:app' }
        $labExpectedPort = '--port\s+' + [regex]::Escape([string]$labEntry.port) + '(\s|$)'
        if (-not $labProcess.ExecutablePath -or
            -not [string]::Equals([IO.Path]::GetFullPath($labProcess.ExecutablePath), $labPython, [StringComparison]::OrdinalIgnoreCase) -or
            $labProcess.CommandLine -notmatch [regex]::Escape($labModule) -or
            $labProcess.CommandLine -notmatch $labExpectedPort) {
            throw "PID $labProcessId does not match this repository's web process; stopped without killing it."
        }
        $labProcesses += $labProcess
    }
}

foreach ($labProcess in $labProcesses) {
    # Windows venv launchers have a child Python process that owns the socket.
    # Stop the verified process tree so the child cannot keep the web port open.
    & taskkill.exe /PID ([string]$labProcess.ProcessId) /T /F | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Failed to stop verified web process $($labProcess.ProcessId)." }
}

& $labPython -c "from scripts import local_replication as lab; lab.compose('stop')"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stop this lab database project; inspect Docker Desktop.' }
Write-Host 'Local lab stopped. Database volumes and topology state are preserved.'
