@echo off
rem Espera a que el servidor responda y abre el navegador predeterminado (nueva pestana si ya esta abierto).
rem Sin argumentos usa el modo normal (HTTP, puerto 8472). Uso: _abrir_navegador.bat URL_PRUEBA URL_ABRIR
set "PRUEBA=%~1"
set "ABRIR=%~2"
if not defined PRUEBA set "PRUEBA=http://127.0.0.1:8472/login"
if not defined ABRIR set "ABRIR=http://localhost:8472"
set /a n=0
where curl >nul 2>&1 || goto :sin_curl
:esperar
curl -f -k --ssl-no-revoke -s -o nul --max-time 1 "%PRUEBA%"
if not errorlevel 1 goto :abrir
set /a n+=1
if %n% geq 60 exit /b 1
ping -n 2 127.0.0.1 >nul
goto :esperar
:sin_curl
ping -n 5 127.0.0.1 >nul
:abrir
start "" "%ABRIR%"
exit /b 0
