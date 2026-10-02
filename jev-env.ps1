$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$env:BH_HOME = Join-Path $PSScriptRoot '.runtime\browser-harness'
$env:BH_UPDATE_CHECK = '0'
$env:BU_NAME = 'jev-demo'
$env:BU_CDP_URL = 'http://127.0.0.1:9227'
$env:JEV_BACKGROUND_TABS = '0'

function Get-JevEnvironmentValue([string] $Name) {
    foreach ($taskScope in @('Process', 'User', 'Machine')) {
        $taskValue = [Environment]::GetEnvironmentVariable($Name, $taskScope)
        if (-not [string]::IsNullOrWhiteSpace($taskValue)) { return $taskValue }
    }
    return $null
}

foreach ($taskName in @('TYPESAFE_API_KEY', 'TYPESAFE_MODEL', 'TEXT_MODEL_API_KEY', 'TEXT_MODEL_BASE_URL', 'TEXT_MODEL', 'TEXT_MODEL_REASONING')) {
    $taskValue = Get-JevEnvironmentValue $taskName
    if ($taskValue) { [Environment]::SetEnvironmentVariable($taskName, $taskValue, 'Process') }
}

if (-not $env:TYPESAFE_API_KEY) {
    $taskJevKey = Get-JevEnvironmentValue 'JEV_API_KEY'
    if ($taskJevKey) { $env:TYPESAFE_API_KEY = $taskJevKey }
    $taskJevKey = $null
}

if (-not $env:TEXT_MODEL_API_KEY) {
    $taskTextKey = Get-JevEnvironmentValue 'OPENROUTER_API_KEY'
    if ($taskTextKey) { $env:TEXT_MODEL_API_KEY = $taskTextKey }
    $taskTextKey = $null
}
$taskValue = $null
