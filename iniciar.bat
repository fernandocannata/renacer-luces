@echo off
chcp 65001 >nul
title Renacer LightShow
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
  py -3 renacer_luces.py %*
  goto fin
)
where python >nul 2>nul
if %errorlevel%==0 (
  python renacer_luces.py %*
  goto fin
)

echo.
echo  No se encontro Python en esta computadora.
echo  Opcion 1: usa RenacerLightShow.exe (no necesita Python).
echo  Opcion 2: instala Python desde https://www.python.org/downloads/
echo            (marca "Add python.exe to PATH" al instalar) y volve a abrir este archivo.
echo.
pause

:fin
