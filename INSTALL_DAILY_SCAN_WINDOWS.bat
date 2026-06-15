@echo off
cd /d %~dp0

echo Installing daily scheduled scan at 7:00 AM...

if not exist .venv (
    echo Creating Python environment...
    python -m venv .venv
)

call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt

set TASKNAME=Five Oaks RFP Daily Scan
set PYTHON=%CD%\.venv\Scripts\python.exe
set SCRIPT=%CD%\daily_scan.py

schtasks /Create /SC DAILY /TN "%TASKNAME%" /TR "\"%PYTHON%\" \"%SCRIPT%\"" /ST 07:00 /F

echo.
echo Daily scan installed. It will run every day at 7:00 AM.
echo You can still open the dashboard with START_APP_WINDOWS.bat.
pause
