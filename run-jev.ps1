[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $Url,
    [Parameter(Mandatory)][string] $Goal,
    [ValidateRange(1, 60)][int] $MaxSteps = 20
)
. (Join-Path $PSScriptRoot 'jev-env.ps1')
if (-not $env:TYPESAFE_API_KEY) { throw 'Set JEV_API_KEY or TYPESAFE_API_KEY in your Windows user environment.' }
$taskPython = Join-Path $PSScriptRoot 'jev-ultrafast\.venv\Scripts\python.exe'
& $taskPython (Join-Path $PSScriptRoot 'run-jev.py') --url $Url --goal $Goal --max-steps $MaxSteps --keep-open
if ($LASTEXITCODE -ne 0) { throw "Jev runner exited with code $LASTEXITCODE." }
