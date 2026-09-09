@echo off
setlocal
cd /d "%~dp0"
if exist "%LOCALAPPDATA%\Programs\Engineering Diagram Studio\EngineeringDiagramStudio.exe" (
  start "" "%LOCALAPPDATA%\Programs\Engineering Diagram Studio\EngineeringDiagramStudio.exe"
  exit /b
)
if exist "dist\EngineeringDiagramStudio\EngineeringDiagramStudio.exe" (
  start "" "dist\EngineeringDiagramStudio\EngineeringDiagramStudio.exe"
  exit /b
)
if exist "release\EngineeringDiagramStudio-Setup.exe" (
  start "" "release\EngineeringDiagramStudio-Setup.exe"
  exit /b
)
where pythonw >nul 2>nul
if errorlevel 1 (
  echo Please run EngineeringDiagramStudio-Setup.exe to install the app.
  echo This source folder has not been packaged yet. See README.md for build instructions.
  pause
  exit /b 1
)
start "" pythonw studio_launcher.py
