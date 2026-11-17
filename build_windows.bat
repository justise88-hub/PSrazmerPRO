@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if errorlevel 1 goto :failed

echo ================================================
echo   PSrazmer PRO 2.8.2 - сборка Windows-программы
echo ================================================

where python >nul 2>nul
if errorlevel 1 goto :python_missing

if not exist ".venv\Scripts\python.exe" python -m venv ".venv"
if errorlevel 1 goto :failed

set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
"%PYTHON_EXE%" -m pip install --upgrade pip
if errorlevel 1 goto :failed
"%PYTHON_EXE%" -m pip install -r requirements.txt
if errorlevel 1 goto :failed

"%PYTHON_EXE%" -m PyInstaller --noconfirm --clean --windowed --onedir ^
  --name "PSrazmer_PRO" ^
  --contents-directory "." ^
  --icon "Resources\PSrazmer.ico" ^
  --add-data "Resources;Resources" ^
  --add-data "Templates;Templates" ^
  --collect-all PySide6 ^
  --collect-all cv2 ^
  app\main.py
if errorlevel 1 goto :failed

if not exist "dist\PSrazmer_PRO\Resources" mkdir "dist\PSrazmer_PRO\Resources"
copy /Y "create_shortcuts.ps1" "dist\PSrazmer_PRO\create_shortcuts.ps1" >nul
if errorlevel 1 goto :failed

echo.
echo Сборка завершена: dist\PSrazmer_PRO\PSrazmer_PRO.exe
echo Теперь запустите build_installer.bat для создания Setup.exe.
echo.
pause
exit /b 0

:python_missing
echo Не найден Python. Установите Python 3.11 или 3.12 x64 и включите Add Python to PATH.
pause
exit /b 1

:failed
echo.
echo ОШИБКА сборки. Проверьте сообщения выше.
pause
exit /b 1
