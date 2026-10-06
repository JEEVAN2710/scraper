@echo off
REM Launcher script for Financial AI Intelligence Suite
setlocal

cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    echo [INFO] Starting Financial AI Assistant using project virtual environment...
    ".venv\Scripts\python.exe" run.py %*
) else (
    echo [WARNING] Project virtual environment (.venv) not found. Falling back to system python...
    python run.py %*
)

endlocal
