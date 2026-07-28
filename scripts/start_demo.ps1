[CmdletBinding()]
param(
    [string]$BindAddress = "127.0.0.1",
    [int]$Port = 8765,
    [switch]$Reload
)

$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw @"
The unified project environment does not exist at:
  $python

Create it first:
  Set-Location "$repoRoot"
  uv sync --dev
"@
}

$uvicornArguments = @(
    "-m", "uvicorn",
    "app.demo:app",
    "--host", $BindAddress,
    "--port", $Port
)
if ($Reload) {
    $uvicornArguments += "--reload"
}

Push-Location $repoRoot
try {
    & $python @uvicornArguments
}
finally {
    Pop-Location
}
