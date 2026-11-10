@echo off
title MRP - Paginas (puerto 5500)
cd /d "%~dp0"

rem 1. The page file must exist where this script expects it.
if not exist "frontend\index.html" goto missing_index

rem 2. Find a Python launcher: "py" (Windows launcher) first, then "python".
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY goto missing_python

echo.
echo Sirviendo la carpeta frontend en http://localhost:5500
echo Deja esta ventana abierta mientras uses el sistema.
echo Para detenerla, cierra la ventana o pulsa Ctrl+C.
echo.

rem 3. Give the server two seconds to start, then open the browser.
start "" cmd /c "timeout /t 2 /nobreak >nul & start http://localhost:5500"

%PY% -m http.server 5500 --directory frontend
echo.
echo El servidor de paginas se detuvo.
echo Si dice "Address already in use", el puerto 5500 ya esta ocupado:
echo cierra la otra ventana que lo use y vuelve a abrir este archivo.
pause
exit /b 0

:missing_index
echo [ERROR] No encuentro frontend\index.html
echo Este archivo debe estar en la carpeta mrp-system, junto a la carpeta frontend.
echo Carpeta actual: %cd%
pause
exit /b 1

:missing_python
echo [ERROR] No encuentro Python.
echo Instalalo desde python.org y marca la casilla "Add python.exe to PATH".
pause
exit /b 1