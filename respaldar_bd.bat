@echo off
cd /d "%~dp0"
call venv\Scripts\activate.bat
python backup_db.py
if errorlevel 1 (
    echo [ERROR] El respaldo fallo.
    pause
    exit /b 1
)
