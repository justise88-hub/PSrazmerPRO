@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  call .venv\Scripts\activate
  python -m pip install --upgrade pip
  pip install -r requirements.txt
) else (
  call .venv\Scripts\activate
)
pyinstaller --noconfirm --clean --windowed --name "PSrazmer_PRO" --icon "Resources\PSrazmer.ico" --add-data "Resources;Resources" --collect-all PySide6 app\main.py
if errorlevel 1 (
  echo Ошибка сборки. Проверьте сообщения выше.
  pause
  exit /b 1
)
copy /Y create_shortcuts.ps1 dist\PSrazmer_PRO\create_shortcuts.ps1 >nul
echo.
echo Готовая программа: dist\PSrazmer_PRO\PSrazmer_PRO.exe
echo Для ярлыков запустите create_shortcuts.ps1 из папки dist\PSrazmer_PRO.
pause
