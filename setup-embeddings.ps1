param([string]$Model = "BAAI/bge-m3")
$ErrorActionPreference = "Stop"
$pythonExe = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $pythonExe)) { throw "Run start.ps1 once first." }
& $pythonExe -m pip install -r (Join-Path $PSScriptRoot "backend\requirements-embeddings.txt")
if ($LASTEXITCODE -ne 0) { throw "Embedding dependency installation failed." }
& $pythonExe (Join-Path $PSScriptRoot "scripts\download_embeddings.py") --model $Model
if ($LASTEXITCODE -ne 0) { throw "Model download failed." }
