@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if errorlevel 1 goto :failed

if not exist "dist\PSrazmer_PRO\PSrazmer_PRO.exe" goto :build_missing

set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ISCC%" goto :compile
set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist "%ISCC%" goto :compile

echo Не найден Inno Setup 6.
echo Установите Inno Setup 6 и повторите запуск.
echo https://jrsoftware.org/isinfo.php
pause
exit /b 1

:compile
"%ISCC%" "PSrazmer_PRO.iss"
if errorlevel 1 goto :failed
echo.
echo Установщик создан в папке installer_output.
pause
exit /b 0

:build_missing
echo Сначала успешно выполните build_windows.bat.
pause
exit /b 1

:failed
echo Ошибка создания установщика. Проверьте сообщения выше.
pause
exit /b 1
