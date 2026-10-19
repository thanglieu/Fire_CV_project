@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist venv (
    echo [*] Tao moi truong ao Python...
    python -m venv venv || (echo Khong tim thay Python. Hay cai Python 3.9-3.12 & pause & exit /b 1)
    call venv\Scripts\activate.bat
    python -m pip install --upgrade pip
    pip install -r requirements.txt
) else (
    call venv\Scripts\activate.bat
)
python main.py %*
pause
