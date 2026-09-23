@echo off
setlocal EnableExtensions
cd /d "%~dp0"

rem Prefer python3 when it exists.
set "PY="
where python3 >nul 2>nul && set "PY=python3"
if not defined PY (
    where py >nul 2>nul && set "PY=py -3"
)
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo Python 3 was not found. Install Python 3 ^(python3 / py -3 / python^) and add it to PATH.
    exit /b 1
)

echo Using interpreter: %PY%

if not exist "go_self_venv\Scripts\python.exe" (
    echo Creating virtual environment for go.py ...
    %PY% -m venv go_self_venv
    if errorlevel 1 (
        echo Failed to create venv with %PY%.
        exit /b 1
    )
)

call "go_self_venv\Scripts\activate.bat"
python -m pip install --upgrade pip
python -m pip install pygame
python go.py %*
endlocal