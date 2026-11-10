@echo off
cd /d "%~dp0"
call venv\Scripts\activate.bat
set FLASK_APP=run.py
echo Actualizando la base de datos ^(se guarda un respaldo antes^)...
flask upgrade-db
pause
