param(
    [int]$Port = 8000,
    [string]$BindAddress = '0.0.0.0',
    [switch]$LocalTest
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$projectPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
$bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$previousPythonPath = $env:PYTHONPATH
Push-Location $projectRoot
try {
    if (Test-Path -LiteralPath $projectPython) {
        $pythonExecutable = $projectPython
    } elseif (Test-Path -LiteralPath $bundledPython) {
        $pythonExecutable = $bundledPython
        $env:PYTHONPATH = "$projectRoot;$(Join-Path $projectRoot 'venv\Lib\site-packages')"
    } else {
        throw 'Buat .venv dan install requirements.txt terlebih dahulu; lihat docs/mobile/README.md.'
    }
    Write-Host "Dashboard: http://localhost:$Port/dashboard"
    Write-Host 'Untuk menghentikan backend, tekan Ctrl+C pada terminal ini.'
    if ($LocalTest) {
        & $pythonExecutable scripts/run_local_backend.py --host $BindAddress --port $Port
    } else {
        & $pythonExecutable -m uvicorn app.main:app --host $BindAddress --port $Port
    }
    if ($LASTEXITCODE -ne 0) { throw "Backend berhenti dengan kode $LASTEXITCODE" }
} finally {
    $env:PYTHONPATH = $previousPythonPath
    Pop-Location
}
