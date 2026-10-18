@echo off
rem Windows: double-click to start Photobook. The very first start installs what it needs (about a minute).
cd /d "%~dp0"
if exist .venv\Scripts\pythonw.exe goto start
echo First start: setting up Photobook (one time only, needs internet)...
py -3 -m venv .venv || python -m venv .venv || goto failed
.venv\Scripts\python -m pip install -q -r requirements.txt || goto failed
:start
start "" .venv\Scripts\pythonw.exe photobook.py
exit /b
:failed
rmdir /s /q .venv 2>nul
echo Setup failed. Please install Python from https://www.python.org/downloads/
echo and tick "Add python.exe to PATH" during installation. Then try again.
pause
