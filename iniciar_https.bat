@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

rem Se relanza minimizado: las ventanas negras quedan en la barra de tareas.
if /i not "%~1"=="min" (
    start "MHN - HTTPS (Caddy)" /min cmd /c ""%~f0" min"
    exit /b
)

if not exist "venv\Scripts\python.exe" (
    set "MSG=No se encontro el entorno virtual en la carpeta venv. Revisa que el proyecto este completo."
    goto :falla
)
if not exist "caddy.exe" (
    set "MSG=Falta caddy.exe en la carpeta del sistema. Descargalo de https://caddyserver.com/download (Windows amd64) y copialo aqui. Mas detalles en el README."
    goto :falla
)

rem Revisa la base de datos solo cuando cambio el sistema (igual que iniciar_servidor.bat).
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

rem IP de la red real (la del adaptador con puerta de enlace), no la de adaptadores virtuales.
set "MHN_HOST="
for /f "usebackq delims=" %%a in (`powershell -NoProfile -Command "(Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway } | Select-Object -First 1).IPv4Address.IPAddress"`) do set "MHN_HOST=%%a"
if not defined MHN_HOST set "MHN_HOST=localhost"

rem Detras de Caddy: confiar en sus cabeceras y marcar las cookies como seguras.
set "BEHIND_PROXY=1"
set "COOKIE_SECURE=1"

start "MHN - Flask (interno)" /min cmd /c ""venv\Scripts\python.exe" -m waitress --host=127.0.0.1 --port=8473 run:app"
start "" /min cmd /c "_abrir_navegador.bat https://localhost/login https://localhost"

caddy.exe run --config Caddyfile
if errorlevel 1 (
    set "MSG=Caddy no pudo iniciar. Puede que el puerto 443 este en uso por otro programa."
    taskkill /f /fi "WINDOWTITLE eq MHN - Flask (interno)*" >nul 2>&1
    goto :falla
)
taskkill /f /fi "WINDOWTITLE eq MHN - Flask (interno)*" >nul 2>&1
exit /b 0

:falla
powershell -NoProfile -Command "Add-Type -AssemblyName PresentationFramework; [void][System.Windows.MessageBox]::Show($env:MSG,'Sistema de Entradas - MHN','OK','Error')"
exit /b 1
