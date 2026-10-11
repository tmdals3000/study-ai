$ErrorActionPreference = "Stop"
$record = Join-Path $PSScriptRoot ".runtime\server.json"
if (-not (Test-Path -LiteralPath $record)) { Write-Host "No server record."; exit }
$info = Get-Content -LiteralPath $record -Raw | ConvertFrom-Json
$process = Get-Process -Id $info.pid -ErrorAction SilentlyContinue
if ($process) {
    if ($info.project -ne $PSScriptRoot -or $process.Path -ne $info.executable -or $process.StartTime.ToUniversalTime().ToString("o") -ne $info.started) {
        throw "PID no longer identifies this Study AI server; refusing to stop it."
    }
    function Stop-StudyChildren([int]$ParentId) {
        $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $ParentId"
        foreach ($child in $children) {
            Stop-StudyChildren -ParentId $child.ProcessId
            Stop-Process -Id $child.ProcessId -ErrorAction SilentlyContinue
        }
    }
    Stop-StudyChildren -ParentId $process.Id
    Stop-Process -Id $process.Id -ErrorAction SilentlyContinue
    Write-Host "Study AI stopped."
}
Remove-Item -LiteralPath $record
