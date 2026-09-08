@echo off
setlocal

rem Always run from the project directory, including when this file is double-clicked.
cd /d "%~dp0"
set "PROJECT_PYTHON=%~dp0.venv\Scripts\python.exe"

if not exist "%PROJECT_PYTHON%" (
    echo [PUNARVAAS] Creating Python virtual environment...
    where py >nul 2>&1
    if not errorlevel 1 py -3 -m venv "%~dp0.venv"

    if not exist "%PROJECT_PYTHON%" (
        where python >nul 2>&1
        if errorlevel 1 (
            echo [PUNARVAAS] Python 3 was not found. Install Python 3.11 or newer.
            exit /b 1
        )
        python -m venv "%~dp0.venv"
    )
)

if not exist "%PROJECT_PYTHON%" (
    echo [PUNARVAAS] Could not create .venv.
    exit /b 1
)

"%PROJECT_PYTHON%" -c "import fastapi, uvicorn, numpy, pandas, pyarrow, scipy, shapely, yaml, jinja2" >nul 2>&1
if errorlevel 1 (
    echo [PUNARVAAS] Installing missing dependencies...
    "%PROJECT_PYTHON%" -m pip install -r "%~dp0requirements.txt"
    if errorlevel 1 (
        echo [PUNARVAAS] Dependency installation failed.
        exit /b 1
    )
)

if /i "%~1"=="--check" (
    echo [PUNARVAAS] Ready. Run run.cmd to start the project.
    exit /b 0
)

echo [PUNARVAAS] Starting at http://127.0.0.1:8000
echo [PUNARVAAS] Press Ctrl+C to stop the server.
"%PROJECT_PYTHON%" -X utf8 -m uvicorn api.main:app --host 127.0.0.1 --port 8000
exit /b %errorlevel%
