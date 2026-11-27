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

if ([string]::IsNullOrWhiteSpace($env:VITE_API_BASE_URL)) {
    $env:VITE_API_BASE_URL = 'http://127.0.0.1:8000'
}
if ($env:VITE_API_BASE_URL.TrimEnd('/') -ne 'http://127.0.0.1:8000') {
    throw 'The checked-in backend CORS policy supports VITE_API_BASE_URL=http://127.0.0.1:8000 only.'
}

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw 'Node.js was not found. Install the project Node.js prerequisite before starting the frontend.'
}
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw 'npm was not found. Install the project Node.js prerequisite before starting the frontend.'
}
$frontendPath = Join-Path $repoRoot 'frontend'
if (-not (Test-Path -LiteralPath (Join-Path $frontendPath 'node_modules\.bin\vite.cmd') -PathType Leaf)) {
    throw "Frontend dependencies are missing. Run 'npm ci' from $frontendPath."
}

$portProbe = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 5173)
try {
    $portProbe.Start()
} catch {
    throw 'Frontend port 5173 is already in use. Stop the existing listener before starting this server.'
} finally {
    $portProbe.Stop()
}

Set-Location -LiteralPath $frontendPath
Write-Host 'Starting AIT3040 frontend on http://127.0.0.1:5173'
& npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
exit $LASTEXITCODE
