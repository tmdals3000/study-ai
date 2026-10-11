param([int]$Port = 8000, [switch]$NoBrowser)
$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"
$frontendDir = Join-Path $projectRoot "frontend"
$runtimeDir = Join-Path $projectRoot ".runtime"
New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null

# Windows PowerShell 5.1 turns native stderr (e.g. npm/pip warnings) into terminating errors under "Stop"
# when output is redirected. Judge external tools by exit code only.
function Invoke-Native([scriptblock]$Command, [string]$Failure) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { & $Command 2>&1 | ForEach-Object { "$_" } } finally { $ErrorActionPreference = $previous }
    if ($LASTEXITCODE -ne 0) { throw $Failure }
}

if (-not (Test-Path -LiteralPath $pythonExe)) {
    Invoke-Native { python -m venv (Join-Path $projectRoot ".venv") } "Python 3.11+ is required."
}
$requirements = Join-Path $projectRoot "backend\requirements.txt"
$requirementsHash = (Get-FileHash -LiteralPath $requirements -Algorithm SHA256).Hash
$installedHash = Join-Path $runtimeDir "requirements.sha256"
if (-not (Test-Path -LiteralPath $installedHash) -or (Get-Content -LiteralPath $installedHash -Raw).Trim() -ne $requirementsHash) {
    Invoke-Native { & $pythonExe -m pip install -r $requirements } "Backend dependency installation failed."
    Set-Content -LiteralPath $installedHash -Value $requirementsHash
}
Push-Location $frontendDir
try {
    $packageHash = (Get-FileHash -LiteralPath "package-lock.json" -Algorithm SHA256).Hash
    $nodeHash = Join-Path $runtimeDir "node.sha256"
    if (-not (Test-Path "node_modules") -or -not (Test-Path $nodeHash) -or (Get-Content $nodeHash -Raw).Trim() -ne $packageHash) {
        Invoke-Native { npm.cmd ci } "Frontend dependency installation failed."
        Set-Content -LiteralPath $nodeHash -Value $packageHash
    }
    Invoke-Native { npm.cmd run build } "Frontend build failed."
} finally { Pop-Location }

$url = "http://127.0.0.1:$Port"
try { $health = Invoke-RestMethod "$url/api/health" -TimeoutSec 2 } catch { $health = $null }
$expectedId = & $pythonExe -c "import hashlib,sys; print(hashlib.sha256(sys.argv[1].encode()).hexdigest()[:16])" $projectRoot
if ($health) {
    if ($health.installation_id -ne $expectedId) { throw "Port $Port belongs to another application. Choose -Port 8012." }
    Write-Host "Study AI is already running: $url"
} else {
    $backendDir = Join-Path $projectRoot "backend"
    $process = Start-Process -FilePath $pythonExe -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$Port", "--workers", "1") -WorkingDirectory $backendDir -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimeDir "server.log") -RedirectStandardError (Join-Path $runtimeDir "server-error.log")
    @{ pid = $process.Id; port = $Port; executable = $process.Path; project = $projectRoot; started = $process.StartTime.ToUniversalTime().ToString("o") } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtimeDir "server.json")
    $ready = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        Start-Sleep -Milliseconds 500
        if ($process.HasExited) { throw "Server exited. See .runtime\server-error.log." }
        try {
            $health = Invoke-RestMethod "$url/api/health" -TimeoutSec 1
            if ($health.installation_id -eq $expectedId) { $ready = $true; break }
        } catch {}
    }
    if (-not $ready) { throw "Server did not become ready. See .runtime\server-error.log." }
    Write-Host "Study AI is ready: $url"
}
if (-not $NoBrowser) { Start-Process $url }
