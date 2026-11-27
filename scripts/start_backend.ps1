param(
    [string]$EnvFile = (Join-Path (Split-Path -Parent $PSScriptRoot) '.env')
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$envPath = (Resolve-Path -LiteralPath $EnvFile -ErrorAction Stop).Path

foreach ($rawLine in Get-Content -LiteralPath $envPath) {
    $line = $rawLine.Trim()
    if (-not $line -or $line.StartsWith('#')) { continue }
    if ($line -notmatch '^(?<key>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?<value>.*)$') {
        throw "Invalid .env line in ${envPath}: $rawLine"
    }
    $name = $Matches.key
    $value = $Matches.value.Trim()
    if (($value.StartsWith('"') -and $value.EndsWith('"')) -or
        ($value.StartsWith("'") -and $value.EndsWith("'"))) {
        $value = $value.Substring(1, $value.Length - 2)
    }
    [Environment]::SetEnvironmentVariable($name, $value, 'Process')
}

$pythonSetting = $env:AIT3040_PYTHON
if ([string]::IsNullOrWhiteSpace($pythonSetting)) {
    $pythonSetting = '.venv\Scripts\python.exe'
}
if ([System.IO.Path]::IsPathRooted($pythonSetting)) {
    $pythonPath = [System.IO.Path]::GetFullPath($pythonSetting)
} else {
    $pythonPath = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $pythonSetting))
}
if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "Python environment not found: $pythonPath. Set AIT3040_PYTHON in .env."
}
$env:AIT3040_PYTHON = $pythonPath

foreach ($name in @('AIT3040_MODEL_PACKAGE', 'AIT3040_MODEL_MANIFEST_PIN',
                    'AIT3040_RUNTIME_DEVICE', 'AIT3040_RUNTIME_AUTHORITY',
                    'AIT3040_DEMO_MAX_VESSELS', 'AIT3040_MAX_CONCURRENCY')) {
    if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($name, 'Process'))) {
        throw "Missing required configuration $name. Edit $envPath."
    }
}

$packagePath = [System.IO.Path]::GetFullPath($env:AIT3040_MODEL_PACKAGE)
$repoPrefix = $repoRoot.TrimEnd('\') + '\'
if (-not (Test-Path -LiteralPath $packagePath -PathType Container)) {
    throw "External model package directory not found: $packagePath"
}
if ($packagePath.StartsWith($repoPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'AIT3040_MODEL_PACKAGE must be stored outside the Git repository.'
}
if (-not (Test-Path -LiteralPath $env:AIT3040_MODEL_MANIFEST_PIN -PathType Leaf)) {
    throw "External manifest pin not found: $($env:AIT3040_MODEL_MANIFEST_PIN)"
}
if ($env:DATASET_ROOT -and -not (Test-Path -LiteralPath $env:DATASET_ROOT -PathType Container)) {
    throw "DATASET_ROOT was set but does not exist: $($env:DATASET_ROOT)"
}

$portProbe = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 8000)
try {
    $portProbe.Start()
} catch {
    throw 'Backend port 8000 is already in use. Stop the existing listener before starting this server.'
} finally {
    $portProbe.Stop()
}

Set-Location -LiteralPath $repoRoot
$env:PYTHONDONTWRITEBYTECODE = '1'
$probe = 'import os, torch, uvicorn; from src.runtime.config import load_config; c=load_config(os.environ); print("Python", __import__("sys").version.split()[0], "Torch", torch.__version__, "device", c.device, "model package", c.package_path)'
& $pythonPath -B -c $probe
if ($LASTEXITCODE -ne 0) {
    throw 'Python environment or runtime configuration validation failed.'
}

Write-Host 'Starting AIT3040 backend on http://127.0.0.1:8000'
Write-Host 'Health: http://127.0.0.1:8000/health'
& $pythonPath -B -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --log-level info
exit $LASTEXITCODE
