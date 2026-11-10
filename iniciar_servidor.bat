@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

rem Se relanza a si mismo minimizado: la ventana negra queda en la barra de tareas.
if /i not "%~1"=="min" (
    start "Sistema de Entradas - MHN" /min cmd /c ""%~f0" min"
    exit /b
)
title Sistema de Entradas - MHN

if not exist "venv\Scripts\python.exe" (
    set "MSG=No se encontro el entorno virtual en la carpeta venv. Revisa que el proyecto este completo."
    goto :falla
)

rem La base de datos solo se revisa cuando cambio el sistema o no existe.
rem Se compara una firma de los archivos del esquema con la guardada.
set "SIG="
for %%F in ("app\db_upgrade.py" "app\models\*.py") do set "SIG=!SIG!%%~zF-%%~tF;"
set "ACTUAL="
if exist "instance\.esquema_ok" set /p ACTUAL=<"instance\.esquema_ok"
if not exist "instance\museo.db" set "ACTUAL="

if not "!ACTUAL!"=="!SIG!" (
    set "FLASK_APP=run.py"
    "venv\Scripts\python.exe" -m flask upgrade-db
    if errorlevel 1 (
        set "MSG=No se pudo actualizar la base de datos. No se inicia el sistema."
        goto :falla
    )
    >"instance\.esquema_ok" echo !SIG!
)

rem Abre el navegador predeterminado en cuanto el servidor responde.
start "" /min cmd /c "_abrir_navegador.bat"

"venv\Scripts\python.exe" -m waitress --host=0.0.0.0 --port=8472 run:app
if errorlevel 1 (
    set "MSG=El sistema no pudo iniciar. Puede que el puerto 8472 ya este en uso o que falten dependencias."
    goto :falla
)
exit /b 0

:falla
powershell -NoProfile -Command "Add-Type -AssemblyName PresentationFramework; [void][System.Windows.MessageBox]::Show($env:MSG,'Sistema de Entradas - MHN','OK','Error')"
exit /b 1
