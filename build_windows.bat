@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
if errorlevel 1 goto :error

echo ================================================
echo   PSrazmer PRO 2.9.1 - сборка Windows-программы
echo ================================================
echo.

where python >nul 2>nul
if errorlevel 1 goto :python_missing

if exist ".venv\Scripts\python.exe" goto :venv_ready
echo Создание изолированного окружения Python...
python -m venv ".venv"
if errorlevel 1 goto :error

:venv_ready
echo Установка зависимостей...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :error
".venv\Scripts\python.exe" -m pip install -r "requirements.txt"
if errorlevel 1 goto :error

echo Сборка приложения через PyInstaller...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --windowed --onedir ^
  --name "PSrazmer_PRO" ^
  --contents-directory "." ^
  --icon "Resources\PSrazmer.ico" ^
  --add-data "Resources;Resources" ^
  --add-data "Templates;Templates" ^
  --collect-all PySide6 ^
  --collect-all cv2 ^
  "app\main.py"
if errorlevel 1 goto :error

if not exist "dist\PSrazmer_PRO\Resources" mkdir "dist\PSrazmer_PRO\Resources"
if errorlevel 1 goto :error
copy /Y "create_shortcuts.ps1" "dist\PSrazmer_PRO\create_shortcuts.ps1" >nul
if errorlevel 1 goto :error

echo.
echo Сборка завершена: dist\PSrazmer_PRO\PSrazmer_PRO.exe
echo Для создания Setup.exe запустите build_installer.bat.
echo.
exit /b 0

:python_missing
echo ОШИБКА: Python 3.11 или 3.12 x64 не найден в PATH.
echo Установите Python с python.org и включите Add Python to PATH.
exit /b 1

:error
echo.
echo СБОРКА НЕ УДАЛАСЬ. Подробности указаны выше.
exit /b 1
