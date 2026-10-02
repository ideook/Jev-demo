[CmdletBinding()]
param(
    [ValidateRange(1, 65535)][int] $Port = 8766,
    [switch] $Headless
)

. (Join-Path $PSScriptRoot 'jev-env.ps1')
$taskRepo = Join-Path $PSScriptRoot 'jev-ultrafast'
$taskPython = Join-Path $taskRepo '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Jev Ultrafast is not installed in this folder.' }

$taskListener = Get-NetTCPConnection -LocalPort 9227 -State Listen -ErrorAction SilentlyContinue
if (-not $taskListener) {
    $taskChrome = @(
        'C:\Program Files\Google\Chrome\Application\chrome.exe',
        'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
        (Join-Path $env:LOCALAPPDATA 'Google\Chrome\Application\chrome.exe')
    ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not $taskChrome) { throw 'Google Chrome was not found.' }
    $taskProfile = Join-Path $PSScriptRoot '.runtime\chrome'
    New-Item -ItemType Directory -Path $taskProfile -Force | Out-Null
    $taskChromeArgs = @(
        '--remote-debugging-port=9227', '--remote-debugging-address=127.0.0.1',
        ('--user-data-dir="' + $taskProfile + '"'), '--no-first-run', '--no-default-browser-check', 'about:blank'
    )
    $taskWindowStyle = 'Normal'
    if ($Headless) {
        $taskChromeArgs = @('--headless=new') + $taskChromeArgs
        $taskWindowStyle = 'Hidden'
    } else {
        $taskChromeArgs = @('--new-window') + $taskChromeArgs
    }
    $taskBrowser = Start-Process -FilePath $taskChrome -ArgumentList $taskChromeArgs -WindowStyle $taskWindowStyle -PassThru
    $taskBrowser.Id | Set-Content -LiteralPath (Join-Path $PSScriptRoot '.runtime\chrome.pid')
} else {
    $taskProfile = Join-Path $PSScriptRoot '.runtime\chrome'
    $taskOwner = Get-CimInstance Win32_Process -Filter ('ProcessId=' + ($taskListener | Select-Object -First 1).OwningProcess)
    if (-not $taskOwner.CommandLine -or -not $taskOwner.CommandLine.Contains($taskProfile)) {
        throw 'Port 9227 is occupied by another browser or application.'
    }
}

$env:TYPESAFE_DEMO_PORT = [string] $Port
Write-Host "Jev Ultrafast: http://127.0.0.1:$Port"
Write-Host ('TypeSafe API key configured: ' + [bool] $env:TYPESAFE_API_KEY)
Write-Host ('Text model API key configured: ' + [bool] $env:TEXT_MODEL_API_KEY)
Push-Location $taskRepo
try {
    & $taskPython -m jev_ultrafast.demo
    if ($LASTEXITCODE -ne 0) { throw "Jev Ultrafast exited with code $LASTEXITCODE." }
} finally {
    Pop-Location
}
