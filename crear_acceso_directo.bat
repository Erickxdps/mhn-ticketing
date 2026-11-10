@echo off
setlocal
cd /d "%~dp0"
echo Creando accesos directos en el Escritorio...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$d=(Get-Location).Path; $w=New-Object -ComObject WScript.Shell; $esc=[Environment]::GetFolderPath('Desktop'); $items=@(@('Sistema de Entradas MHN','iniciar_servidor.bat','Sistema de Entradas - Museo de Historia Natural (HTTP)'),@('Sistema de Entradas MHN (HTTPS)','iniciar_https.bat','Sistema de Entradas - Museo de Historia Natural (HTTPS, para usar la camara del celular)')); foreach($i in $items){ $s=$w.CreateShortcut($esc+'\'+$i[0]+'.lnk'); $s.TargetPath=$d+'\'+$i[1]; $s.WorkingDirectory=$d; $s.IconLocation=$d+'\app\static\img\icono_mhn.ico'; $s.Description=$i[2]; $s.WindowStyle=7; $s.Save() }"
if errorlevel 1 (
    echo [ERROR] No se pudieron crear los accesos directos.
    pause
    exit /b 1
)
echo.
echo Listo. En tu Escritorio quedaron dos accesos con el icono del museo:
echo   - Sistema de Entradas MHN          ^(uso normal^)
echo   - Sistema de Entradas MHN ^(HTTPS^)  ^(para usar la camara del celular^)
echo Usa uno solo a la vez. Ambos inician minimizados y abren el navegador.
echo.
pause
