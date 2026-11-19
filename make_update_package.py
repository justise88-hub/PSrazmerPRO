#!/usr/bin/env python3
"""Create a SHA-256 protected update ZIP and manifest from a PyInstaller onedir build.
Usage: python make_update_package.py 2.9.0 --notes "Исправления;Улучшения"
"""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("version", help="Новая версия, например 2.9.0")
    parser.add_argument("--notes", default="", help="Пункты списка изменений через ;")
    parser.add_argument("--build-dir", default=str(ROOT / "dist" / "PSrazmer_PRO"))
    args = parser.parse_args()
    build = Path(args.build_dir).resolve()
    if not build.is_dir():
        raise SystemExit(f"Не найдена сборка: {build}. Сначала запустите build_windows.bat")
    out_dir = ROOT / "update_release"
    out_dir.mkdir(exist_ok=True)
    package_name = f"PSrazmer_PRO_{args.version}_update.zip"
    package_path = out_dir / package_name
    excluded = {"Config", "Logs", "Cache", "History", "Presets", "Exports", "Temp", "Backups", "Employees", "Templates", "__pycache__"}
    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=7) as archive:
        for file in sorted(build.rglob("*")):
            if not file.is_file():
                continue
            relative = file.relative_to(build)
            if any(part in excluded for part in relative.parts):
                continue
            archive.write(file, Path("program") / relative)
    digest = hashlib.sha256(package_path.read_bytes()).hexdigest()
    manifest = {
        "version": args.version,
        "package": package_name,
        "sha256": digest,
        "notes": [item.strip() for item in args.notes.split(";") if item.strip()],
    }
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Создано: {package_path}")
    print(f"Создано: {manifest_path}")
    print(f"SHA-256: {digest}")
    print("Загрузите ZIP и manifest.json в одну публичную папку Яндекс Диска.")
    print("В программе укажите публичную ссылку на эту папку (не ссылку на ZIP).")


if __name__ == "__main__":
    main()
