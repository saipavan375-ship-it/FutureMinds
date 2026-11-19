@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  py -m venv .venv
  if errorlevel 1 goto error
)
echo Installing/checking dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto error
echo Starting Student Goal Setting and Review Tool...
".venv\Scripts\python.exe" app.py
pause
exit /b 0
:error
echo Failed to set up or start LearnWise AI. Read the error above.
pause
exit /b 1
