[CmdletBinding()]
param(
    [string]$SourcePath = $env:MODELLATOR_IBKR_API_SOURCE,
    [string]$PythonPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $SourcePath) {
    $SourcePath = "C:\TWS API\source\pythonclient"
}

if ($PythonPath) {
    $python = (Resolve-Path -LiteralPath $PythonPath -ErrorAction Stop).Path
} elseif ($env:VIRTUAL_ENV) {
    $venvPython = Join-Path $env:VIRTUAL_ENV "Scripts\python.exe"
    $python = (Resolve-Path -LiteralPath $venvPython -ErrorAction Stop).Path
} else {
    $pythonCommand = Get-Command python.exe -ErrorAction Stop
    $python = $pythonCommand.Source
}

$source = (Resolve-Path -LiteralPath $SourcePath -ErrorAction Stop).Path
$requiredFiles = @(
    "setup.py",
    "ibapi\__init__.py",
    "ibapi\client.py",
    "ibapi\wrapper.py",
    "ibapi\protobuf"
)
foreach ($relativePath in $requiredFiles) {
    if (-not (Test-Path -LiteralPath (Join-Path $source $relativePath))) {
        throw "The selected source is not an official TWS API Python client project: missing $relativePath"
    }
}

$sourceFilesToVerify = $requiredFiles | Where-Object { $_ -ne "ibapi\protobuf" }
$sourceHashes = @{}
foreach ($relativePath in $sourceFilesToVerify) {
    $sourceHashes[$relativePath] = (Get-FileHash -LiteralPath (Join-Path $source $relativePath) -Algorithm SHA256).Hash
}

$tempBase = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath()).TrimEnd("\")
$tempRoot = Join-Path $tempBase ("modellator-official-ibkr-api-" + [guid]::NewGuid().ToString("N"))
$workingSource = Join-Path $tempRoot "pythonclient"

try {
    New-Item -ItemType Directory -Path $tempRoot | Out-Null
    Copy-Item -LiteralPath $source -Destination $workingSource -Recurse

    Write-Host "Installing the official IBKR Python client with: $python"
    Write-Host "Verified official source: $source"
    Write-Host "Building from a disposable copy so the official source directory remains unchanged."
    & $python -m pip install --upgrade $workingSource
    if ($LASTEXITCODE -ne 0) {
        throw "The official IBKR Python client installation failed with exit code $LASTEXITCODE."
    }

    $compatibilityCheck = @'
import inspect
import ibapi
from ibapi.ticktype import TickTypeEnum
from ibapi.wrapper import EWrapper

expected = (
    'self',
    'reqId',
    'errorTime',
    'errorCode',
    'errorString',
    'advancedOrderRejectJson',
)
actual = tuple(inspect.signature(EWrapper.error).parameters)
if actual != expected:
    raise SystemExit(f'Incompatible EWrapper.error signature: {actual}')
if not callable(getattr(TickTypeEnum, 'toStr', None)):
    raise SystemExit('Incompatible TickTypeEnum: modern toStr converter is missing')
print(f'Installed ibapi version: {ibapi.__version__}')
print('Modern IBKR callback compatibility check passed.')
'@
    & $python -c $compatibilityCheck
    if ($LASTEXITCODE -ne 0) {
        throw "The installed IBKR client failed the modern compatibility check."
    }

    foreach ($relativePath in $sourceFilesToVerify) {
        $currentHash = (Get-FileHash -LiteralPath (Join-Path $source $relativePath) -Algorithm SHA256).Hash
        if ($currentHash -ne $sourceHashes[$relativePath]) {
            throw "The official source changed unexpectedly during installation: $relativePath"
        }
    }
    Write-Host "Official TWS API source verification passed; source files were not modified."
} finally {
    $resolvedTempRoot = [System.IO.Path]::GetFullPath($tempRoot).TrimEnd("\")
    if (
        (Test-Path -LiteralPath $resolvedTempRoot) -and
        $resolvedTempRoot.StartsWith(
            $tempBase + [System.IO.Path]::DirectorySeparatorChar,
            [System.StringComparison]::OrdinalIgnoreCase
        )
    ) {
        Remove-Item -LiteralPath $resolvedTempRoot -Recurse -Force
    }
}
