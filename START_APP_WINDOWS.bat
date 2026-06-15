@echo off
cd /d %~dp0

echo =============================================
echo Five Oaks RFP Tracker
echo =============================================

if not exist .venv (
    echo Creating Python environment...
    python -m venv .venv
)

call .venv\Scripts\activate

echo Installing requirements...
python -m pip install --upgrade pip
pip install -r requirements.txt

echo Starting the app...
streamlit run app.py

pause
