# Исправление сборки Windows — PSразмер PRO 2.8.2

В предоставленном журнале GitHub Actions сборка остановилась сразу после заголовка с сообщением:

` . was unexpected at this time.`

Ошибка возникла на этапе разбора командного файла CMD, до запуска PyInstaller. Скрипт сборки переписан без вложенных блоков `IF (...)`, чтобы избежать проблем парсера CMD и различий между локальной Windows и GitHub Actions.

Также:
- убрана зависимость от Python Launcher `py`; используется `python` из PATH (в GitHub Actions он добавляется `actions/setup-python`);
- команды выполняются через явный путь к Python из `.venv`;
- аналогично упрощён скрипт Inno Setup;
- имя установщика приведено к версии 2.8.2.

## Сборка

1. Установить Python 3.11 или 3.12 x64 и включить `Add Python to PATH`.
2. Запустить `build_windows.bat`.
3. Для `Setup.exe` установить Inno Setup 6 и запустить `build_installer.bat`.

В этой среде проверены синтаксис Python и автоматические тесты. Сам `.bat` и итоговый EXE необходимо исполнить в Windows/GitHub Actions.
