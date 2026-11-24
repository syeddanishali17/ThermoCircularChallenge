@echo off
setlocal
cd /d "%~dp0"
set "TC_LOCAL_STORAGE=1"
set "PYTHONUTF8=1"
set "TC_PORT=%~1"
if not defined TC_PORT set "TC_PORT=8501"
set "TC_VERSION_CHECK=from importlib.metadata import version; from pathlib import Path; assert all(version(k) == v for k,v in (line.split('==') for line in Path('requirements.txt').read_text().splitlines() if '==' in line))"
if not exist ".venv\Scripts\python.exe" (
  py -3.12 -c "pass" >nul 2>&1
  if errorlevel 1 (
    set "TC_BASE_PY=python"
  ) else (
    set "TC_BASE_PY=py -3.12"
  )
  call :make_venv
  if errorlevel 1 goto :error
)
set "TC_PY=.venv\Scripts\python.exe"
"%TC_PY%" -c "%TC_VERSION_CHECK%" >nul 2>&1
if errorlevel 1 (
  "%TC_PY%" -m pip install --disable-pip-version-check -r requirements.txt
  if errorlevel 1 goto :error
)
"%TC_PY%" -c "import socket,sys; s=socket.socket(); s.bind(('127.0.0.1',int(sys.argv[1]))); s.close()" "%TC_PORT%" >nul 2>&1
if errorlevel 1 (
  echo Port %TC_PORT% is unavailable. Try START_THERMOCIRCULAR.bat 8502.
  pause
  exit /b 1
)
echo Open http://127.0.0.1:%TC_PORT% in your browser.
"%TC_PY%" -m streamlit run app.py --server.address 127.0.0.1 --server.port "%TC_PORT%"
if errorlevel 1 goto :error
exit /b 0
:make_venv
%TC_BASE_PY% -c "import sys; assert sys.version_info[:2] == (3, 12)" >nul 2>&1
if errorlevel 1 (
  echo Python 3.12 is required. Install it and retry.
  exit /b 1
)
%TC_BASE_PY% -c "%TC_VERSION_CHECK%" >nul 2>&1
if errorlevel 1 (
  %TC_BASE_PY% -m venv .venv
) else (
  %TC_BASE_PY% -m venv --system-site-packages .venv
)
exit /b %errorlevel%
:error
echo ThermoCircular failed to start. See the error above.
pause
exit /b 1
