param(
    [string]$Python = 'python',
    [string]$Iscc = 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
)
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    & $Python -m venv .build-venv
    if ($LASTEXITCODE) { throw 'Could not create build environment' }
    $buildPython = Join-Path $PSScriptRoot '.build-venv\Scripts\python.exe'
    & $buildPython -m pip install -r requirements-build.txt
    if ($LASTEXITCODE) { throw 'Could not install build dependencies' }
    & $buildPython -m PyInstaller --noconfirm --clean EngineeringDiagramStudio.spec
    if ($LASTEXITCODE) { throw 'Executable build failed' }
    $report = Join-Path $PSScriptRoot 'build\self-test.json'
    if (Test-Path $report) { Remove-Item -LiteralPath $report }
    $process = Start-Process 'dist\EngineeringDiagramStudio\EngineeringDiagramStudio.exe' -ArgumentList @('--self-test', ('"' + $report + '"')) -WindowStyle Hidden -PassThru
    if (-not $process.WaitForExit(120000)) { $process.Kill(); throw 'Packaged app check timed out' }
    if ($process.ExitCode -ne 0 -or -not (Test-Path $report)) { throw 'Packaged app check failed' }
    if (-not (Get-Content $report -Raw | ConvertFrom-Json).ok) { throw 'Packaged app check failed' }
    & $Iscc installer\setup.iss
    if ($LASTEXITCODE) { throw 'Installer build failed' }
    Write-Host 'Ready: release\EngineeringDiagramStudio-Setup.exe'
} finally { Pop-Location }
