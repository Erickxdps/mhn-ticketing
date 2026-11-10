@echo off
cd /d "%~dp0"
echo Programa un respaldo diario de la base de datos a las 18:30.
schtasks /Create /SC DAILY /ST 18:30 /TN "MHN Respaldo BD" /TR "\"%~dp0respaldar_bd.bat\"" /F
if errorlevel 1 (
    echo [ERROR] No se pudo crear la tarea. Prueba ejecutando este archivo como administrador.
) else (
    echo Listo: tarea "MHN Respaldo BD" creada.
)
pause
