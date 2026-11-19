"""Safe, opt-in updater for PSразмер PRO.

Update manifest format (hosted over HTTPS):
{
  "version": "2.9.0",
  "package": "PSrazmer_PRO_2.9.0_update.zip",
  "sha256": "<64 hex chars>",
  "notes": ["Исправления и улучшения"]
}
The ZIP must contain program/ with the new application runtime files.
User data folders are deliberately never overwritten by the updater.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QProgressBar, QMessageBox, QPlainTextEdit
)

APP_VERSION = "2.9.0"
DEFAULT_UPDATE_SOURCE_URL = "https://disk.yandex.ru/d/3-8I5L5VUQpoEA"
USER_DATA_DIRS = {
    "Config", "Logs", "Cache", "History", "Presets", "Exports",
    "Temp", "Backups", "Employees", "Templates"
}


from version_utils import version_tuple


def _is_yandex_share_url(value: str) -> bool:
    parsed = urllib.parse.urlparse(value.strip())
    host = (parsed.hostname or "").lower()
    return parsed.scheme.lower() == "https" and (
        host == "disk.yandex.ru" or host.endswith(".yandex.ru") or
        host == "yadi.sk" or host.endswith(".yadi.sk")
    ) and not parsed.path.lower().endswith("manifest.json")


def _yandex_public_download_url(public_key: str, remote_path: str) -> str:
    """Resolve a file inside a public Yandex Disk folder without OAuth."""
    endpoint = "https://cloud-api.yandex.net/v1/disk/public/resources/download"
    query = urllib.parse.urlencode({"public_key": public_key, "path": "/" + remote_path.lstrip("/")})
    request = urllib.request.Request(
        endpoint + "?" + query,
        headers={"User-Agent": "PSrazmer-PRO-Updater/1.0", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read(1024 * 1024).decode("utf-8-sig"))
    href = payload.get("href")
    if not isinstance(href, str) or not href.startswith("https://"):
        raise ValueError("Яндекс Диск не вернул безопасную ссылку на скачивание.")
    return href


def _read_manifest(source_url: str) -> tuple[dict, bool]:
    is_yandex_folder = _is_yandex_share_url(source_url)
    if is_yandex_folder:
        manifest_url = _yandex_public_download_url(source_url, "manifest.json")
    else:
        if not source_url.lower().startswith("https://"):
            raise ValueError("Укажите HTTPS-ссылку на папку Яндекс Диска или manifest.json.")
        manifest_url = source_url
    request = urllib.request.Request(
        manifest_url,
        headers={"User-Agent": "PSrazmer-PRO-Updater/1.0", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        manifest = json.loads(response.read(1024 * 1024).decode("utf-8-sig"))
    if not isinstance(manifest, dict):
        raise ValueError("Файл manifest.json имеет неверный формат.")
    return manifest, is_yandex_folder


class UpdateWorker(QThread):
    succeeded = Signal(dict)
    failed = Signal(str)
    progress = Signal(int)

    def __init__(self, manifest_url: str, action: str, staging_root: Path):
        super().__init__()
        self.manifest_url = manifest_url.strip()
        self.action = action
        self.staging_root = staging_root

    def run(self):
        try:
            manifest, is_yandex_folder = _read_manifest(self.manifest_url)
            version = str(manifest["version"])
            version_tuple(version)
            package_name = str(manifest["package"])
            package_path = PurePosixPath(package_name)
            if package_path.is_absolute() or ".." in package_path.parts or not package_path.parts:
                raise ValueError("В manifest.json указан небезопасный путь к ZIP.")
            if is_yandex_folder:
                package_url = _yandex_public_download_url(self.manifest_url, package_path.as_posix())
            else:
                package_url = urllib.parse.urljoin(self.manifest_url, package_name)
            if urllib.parse.urlparse(package_url).scheme.lower() != "https":
                raise ValueError("Ссылка на ZIP обновления должна использовать HTTPS.")
            digest = str(manifest["sha256"]).lower()
            if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise ValueError("В manifest.json отсутствует корректная SHA-256 сумма.")
            result = {"manifest": manifest, "version": version, "package_url": package_url}
            if self.action == "download" and version_tuple(version) <= version_tuple(APP_VERSION):
                raise ValueError("В опубликованном манифесте нет версии новее установленной. Обновление отменено.")
            if self.action == "check":
                self.succeeded.emit(result)
                return

            self.staging_root.mkdir(parents=True, exist_ok=True)
            archive_path = self.staging_root / "update.zip"
            req = urllib.request.Request(package_url, headers={"User-Agent": "PSrazmer-PRO-Updater/1.0"})
            hasher = hashlib.sha256()
            total = 0
            with urllib.request.urlopen(req, timeout=60) as response, archive_path.open("wb") as out:
                length = int(response.headers.get("Content-Length", "0") or 0)
                while True:
                    chunk = response.read(1024 * 256)
                    if not chunk:
                        break
                    out.write(chunk)
                    hasher.update(chunk)
                    total += len(chunk)
                    if total > 1024 * 1024 * 1024:
                        raise ValueError("Размер пакета превышает допустимый лимит 1 ГБ.")
                    if length:
                        self.progress.emit(min(99, int(total * 100 / length)))
            if hasher.hexdigest() != digest:
                archive_path.unlink(missing_ok=True)
                raise ValueError("Контрольная сумма обновления не совпала. Установка отменена.")

            program_dir = self.staging_root / "program"
            if program_dir.exists():
                shutil.rmtree(program_dir)
            program_dir.mkdir(parents=True)
            with zipfile.ZipFile(archive_path) as archive:
                members = archive.infolist()
                if len(members) > 20000 or sum(item.file_size for item in members) > 2 * 1024 * 1024 * 1024:
                    raise ValueError("Архив обновления превышает допустимые ограничения.")
                for info in members:
                    raw = PurePosixPath(info.filename)
                    if (raw.is_absolute() or ".." in raw.parts or not raw.parts
                            or "\\" in info.filename or any(":" in part for part in raw.parts)):

                        raise ValueError("Архив содержит небезопасный путь. Установка отменена.")
                    if raw.parts[0] != "program" or len(raw.parts) == 1:
                        continue
                    relative = Path(*raw.parts[1:])
                    if relative.parts[0] in USER_DATA_DIRS:
                        continue
                    target = program_dir / relative
                    if info.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with archive.open(info) as src, target.open("wb") as dst:
                            shutil.copyfileobj(src, dst)
            if not any(p.is_file() for p in program_dir.rglob("*")):
                raise ValueError("В архиве нет файлов program/. Проверьте формат пакета обновления.")
            archive_path.unlink(missing_ok=True)
            self.progress.emit(100)
            result["staging_program"] = str(program_dir)
            self.succeeded.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class UpdateDialog(QDialog):
    def __init__(self, parent, app_root: Path, settings: dict):
        super().__init__(parent)
        self.setWindowTitle("Обновление PSразмер PRO")
        self.setMinimumWidth(560)
        self.app_root = Path(app_root)
        self.settings = settings
        self.worker = None
        self.latest_result = None
        self.staging_root = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "PSrazmer PRO" / "UpdateStaging"

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Установленная версия: <b>{APP_VERSION}</b>"))
        layout.addWidget(QLabel("Ссылка на публичную папку Яндекс Диска (или HTTPS manifest.json):"))
        self.url_edit = QLineEdit(str(settings.get("update_source_url", settings.get("update_manifest_url", DEFAULT_UPDATE_SOURCE_URL))))
        self.url_edit.setPlaceholderText("https://disk.yandex.ru/d/ВашаПубличнаяПапка")
        layout.addWidget(self.url_edit)
        self.status = QLabel("Источник обновлений уже настроен: ваша публичная папка Яндекс Диска. В ней должны лежать manifest.json и ZIP последнего выпуска. Данные сотрудников никуда не отправляются.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.notes = QPlainTextEdit()
        self.notes.setReadOnly(True)
        self.notes.setMaximumHeight(130)
        self.notes.setPlaceholderText("Здесь появится список изменений новой версии.")
        layout.addWidget(self.notes)
        self.progress = QProgressBar()
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        buttons = QHBoxLayout()
        self.check_btn = QPushButton("Проверить обновления")
        self.check_btn.clicked.connect(self.check_updates)
        self.install_btn = QPushButton("Скачать и установить")
        self.install_btn.setEnabled(False)
        self.install_btn.clicked.connect(self.download_update)
        self.close_btn = QPushButton("Закрыть")
        self.close_btn.clicked.connect(self.accept)
        buttons.addWidget(self.check_btn)
        buttons.addWidget(self.install_btn)
        buttons.addWidget(self.close_btn)
        layout.addLayout(buttons)
        if not getattr(sys, "frozen", False) or os.name != "nt":
            self.install_btn.setToolTip("Автоматическая установка доступна в установленной Windows-версии программы.")

    def check_updates(self):
        self.settings["update_source_url"] = self.url_edit.text().strip()
        self._start_worker("check")

    def download_update(self):
        if not self.latest_result:
            return
        if not getattr(sys, "frozen", False) or os.name != "nt":
            QMessageBox.information(self, "Обновление", "Автоустановка работает в установленной Windows-версии. Для исходного кода используйте новый установочный пакет.")
            return
        self._start_worker("download")

    def _start_worker(self, action):
        if self.worker and self.worker.isRunning():
            return
        self.settings["update_source_url"] = self.url_edit.text().strip()
        self.check_btn.setEnabled(False)
        self.install_btn.setEnabled(False)
        self.status.setText("Проверка обновлений…" if action == "check" else "Загрузка и проверка пакета…")
        self.progress.setValue(0)
        self.worker = UpdateWorker(self.url_edit.text(), action, self.staging_root)
        self.worker.succeeded.connect(lambda result, a=action: self._worker_succeeded(result, a))
        self.worker.failed.connect(self._worker_failed)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.finished.connect(lambda: self.check_btn.setEnabled(True))
        self.worker.start()

    def _worker_succeeded(self, result, action):
        self.latest_result = result
        manifest = result["manifest"]
        notes = manifest.get("notes", [])
        if isinstance(notes, str):
            notes = [notes]
        self.notes.setPlainText("\n".join(f"• {line}" for line in notes) or "Список изменений не опубликован.")
        if action == "check":
            try:
                available = version_tuple(result["version"]) > version_tuple(APP_VERSION)
            except ValueError as exc:
                self._worker_failed(str(exc))
                return
            if available:
                self.status.setText(f"Доступна новая версия: {result['version']}.")
                self.install_btn.setEnabled(True)
            else:
                self.status.setText(f"Установлена актуальная версия ({APP_VERSION}).")
        else:
            self._prepare_installer(result)

    def _prepare_installer(self, result):
        app_exe = Path(sys.executable).resolve()
        install_dir = app_exe.parent
        ps1 = self.staging_root / "install_update.ps1"
        backup_root = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "PSrazmer PRO" / "UpdateBackups" / (result["version"] + "-" + str(os.getpid()))
        stage = Path(result["staging_program"])
        # PowerShell waits for this process to exit, backs up replaced files, overlays the new runtime,
        # and restores the backup if copying fails. User data directories are not touched.
        script = r'''$ErrorActionPreference = 'Stop'
$install = __INSTALL__
$stage = __STAGE__
$backup = __BACKUP__
$exe = __EXE__
New-Item -ItemType Directory -Force -Path $backup | Out-Null
$files = Get-ChildItem -LiteralPath $stage -File -Recurse
try {
  foreach ($f in $files) {
    $rel = $f.FullName.Substring($stage.Length).TrimStart('\\')
    $dest = Join-Path $install $rel
    if (Test-Path -LiteralPath $dest) {
      $b = Join-Path $backup $rel
      New-Item -ItemType Directory -Force -Path (Split-Path $b) | Out-Null
      Copy-Item -LiteralPath $dest -Destination $b -Force
    }
  }
  foreach ($f in $files) {
    $rel = $f.FullName.Substring($stage.Length).TrimStart('\\')
    $dest = Join-Path $install $rel
    New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null
    Copy-Item -LiteralPath $f.FullName -Destination $dest -Force
  }
  Start-Process -FilePath $exe -WorkingDirectory $install
} catch {
  Get-ChildItem -LiteralPath $backup -File -Recurse | ForEach-Object {
    $rel = $_.FullName.Substring($backup.Length).TrimStart('\\')
    $dest = Join-Path $install $rel
    New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null
    Copy-Item -LiteralPath $_.FullName -Destination $dest -Force
  }
  foreach ($f in $files) {
    $rel = $f.FullName.Substring($stage.Length).TrimStart('\\')
    $dest = Join-Path $install $rel
    $b = Join-Path $backup $rel
    if (!(Test-Path -LiteralPath $b) -and (Test-Path -LiteralPath $dest)) { Remove-Item -LiteralPath $dest -Force }
  }
  Start-Process -FilePath $exe -WorkingDirectory $install
  throw
}
'''
        replacements = {
            "__INSTALL__": str(install_dir), "__STAGE__": str(stage),
            "__BACKUP__": str(backup_root), "__EXE__": str(app_exe),
        }
        for key, value in replacements.items():
            script = script.replace(key, "'" + value.replace("'", "''") + "'")
        ps1.write_text(script, encoding="utf-8-sig")
        bat = self.staging_root / "start_update.bat"
        bat.write_text(
            '@echo off\r\ntimeout /t 3 /nobreak >nul\r\n'
            f'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{ps1}"\r\n',
            encoding="utf-8",
        )
        answer = QMessageBox.question(
            self, "Установить обновление",
            f"Пакет версии {result['version']} проверен. Программа закроется, обновится и запустится снова.\n\n"
            "Перед заменой файлов будет создана резервная копия. Данные сотрудников и настройки не затрагиваются. Продолжить?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
        )
        if answer == QMessageBox.Yes:
            subprocess.Popen(["cmd.exe", "/c", "start", "", str(bat)], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.parent().close()
            self.accept()
        else:
            self.status.setText("Обновление загружено и проверено, установка отложена.")

    def _worker_failed(self, message):
        self.status.setText("Не удалось выполнить обновление.")
        QMessageBox.warning(self, "Обновление PSразмер PRO", message)
