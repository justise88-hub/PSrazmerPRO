@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ================================================
echo   PSразмер PRO 2.8.2 - сборка Windows-программы
echo ================================================

where py >nul 2>nul
if errorlevel 1 (
  echo Не найден Python Launcher (py). Установите Python 3.11/3.12 x64 с python.org.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  if errorlevel 1 goto :error
)
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
if errorlevel 1 goto :error
python -m pip install -r requirements.txt
if errorlevel 1 goto :error

python -m PyInstaller --noconfirm --clean --windowed --onedir ^
  --name "PSrazmer_PRO" ^
  --contents-directory "." ^
  --icon "Resources\PSrazmer.ico" ^
  --add-data "Resources;Resources" ^
  --add-data "Templates;Templates" ^
  --collect-all PySide6 ^
  --collect-all cv2 ^
  app\main.py
if errorlevel 1 goto :error

if not exist "dist\PSrazmer_PRO\Resources" mkdir "dist\PSrazmer_PRO\Resources"
copy /Y "create_shortcuts.ps1" "dist\PSrazmer_PRO\create_shortcuts.ps1" >nul
if errorlevel 1 goto :error

echo.
echo Сборка завершена: dist\PSrazmer_PRO\PSrazmer_PRO.exe
echo Теперь запустите build_installer.bat для создания Setup.exe.
echo.
pause
exit /b 0

:error
echo.
echo ОШИБКА сборки. Смотрите сообщения выше.
pause
exit /b 1
