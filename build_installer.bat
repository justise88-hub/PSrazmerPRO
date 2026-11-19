@echo off
setlocal
cd /d "%~dp0"
if not exist "dist\PSrazmer_PRO\PSrazmer_PRO.exe" (
  echo Сначала запустите build_windows.bat
  pause
  exit /b 1
)
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
  echo Не найден Inno Setup 6.
  echo Установите Inno Setup 6, затем повторите запуск.
  echo https://jrsoftware.org/isinfo.php
  pause
  exit /b 1
)
"%ISCC%" "PSrazmer_PRO.iss"
if errorlevel 1 (
  echo Ошибка создания установщика.
  pause
  exit /b 1
)
echo.
echo Установщик создан в папке installer_output.
pause
