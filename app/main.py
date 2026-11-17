
import sys, os, io, json, logging, shutil, subprocess, platform, gc, time, sqlite3, csv, re
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime
from PIL import Image, ImageOps, ImageDraw, ImageFont
from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QPixmap, QImage, QIcon, QFont, QColor, QPainter, QLinearGradient, QPen, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QFileDialog, QListWidget, QSplashScreen,
    QListWidgetItem, QVBoxLayout, QHBoxLayout, QGridLayout, QTabWidget, QSpinBox,
    QDoubleSpinBox, QComboBox, QCheckBox, QLineEdit, QMessageBox, QGroupBox,
    QSplitter, QProgressBar, QPlainTextEdit, QFormLayout, QAbstractItemView, QSizePolicy,
    QTableWidget, QTableWidgetItem, QDialog, QDialogButtonBox, QDateEdit, QHeaderView
)
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage

APP_NAME = "PSразмер изображений PRO 2.3 — Внуково / Magicard"

# Estimated portrait frame measured proportionally from the user's HUB screenshot.
VNUKOVO_PHOTO_WIDTH_MM = 21.8
VNUKOVO_PHOTO_HEIGHT_MM = 29.0
VNUKOVO_PHOTO_WIDTH_CM = VNUKOVO_PHOTO_WIDTH_MM / 10
VNUKOVO_PHOTO_HEIGHT_CM = VNUKOVO_PHOTO_HEIGHT_MM / 10
VNUKOVO_PHOTO_SUFFIX = "21_8x29mm_300dpi"

# Portable mode: all application-owned files stay beside the program.
if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).resolve().parent
else:
    ROOT = Path(__file__).resolve().parent.parent

CONFIG_DIR = ROOT / "Config"
LOG_DIR = ROOT / "Logs"
CACHE_DIR = ROOT / "Cache"
HISTORY_DIR = ROOT / "History"
PRESETS_DIR = ROOT / "Presets"
OUTPUT_DIR = ROOT / "Exports"
TEMP_DIR = ROOT / "Temp"
BACKUP_DIR = ROOT / "Backups"
EMPLOYEE_DIR = ROOT / "Employees"
DB_FILE = EMPLOYEE_DIR / "employees.sqlite3"
RESOURCES_DIR = ROOT / "Resources"

for folder in (
    CONFIG_DIR, LOG_DIR, CACHE_DIR, HISTORY_DIR, PRESETS_DIR,
    OUTPUT_DIR, TEMP_DIR, BACKUP_DIR, EMPLOYEE_DIR, RESOURCES_DIR
):
    folder.mkdir(parents=True, exist_ok=True)

for stale_file in TEMP_DIR.iterdir():
    try:
        if stale_file.is_file():
            stale_file.unlink()
        elif stale_file.is_dir():
            shutil.rmtree(stale_file, ignore_errors=True)
    except Exception:
        pass

logging.basicConfig(
    filename=str(LOG_DIR / "psrazmer.log"), level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8"
)
HISTORY_FILE = HISTORY_DIR / "history.json"
SETTINGS_FILE = CONFIG_DIR / "settings.json"
PRESETS_FILE = PRESETS_DIR / "presets.json"

if not PRESETS_FILE.exists():
    PRESETS_FILE.write_text(json.dumps({
        "Паспорт / ID": [3.5, 4.5],
        "Фото 3 × 4": [3.0, 4.0],
        "Фото 4 × 6": [4.0, 6.0],
        "Фото 9 × 13": [9.0, 13.0],
        "Фото 10 × 15": [10.0, 15.0],
        "Квадрат": [4.0, 4.0],
        "Виза США": [5.1, 5.1]
    }, ensure_ascii=False, indent=2), encoding="utf-8")

# Локальная база сотрудников. Фотографии и персональные данные остаются на этом ПК.
@contextmanager
def db_connect():
    con = sqlite3.connect(DB_FILE)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

def init_employee_db():
    with db_connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL, organization TEXT DEFAULT '', department TEXT DEFAULT '',
            position TEXT DEFAULT '', badge_number TEXT DEFAULT '', valid_until TEXT DEFAULT '',
            photo_path TEXT DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")

init_employee_db()

FORMATS = ["JPG", "PNG", "WEBP", "TIFF", "BMP", "GIF"]
SUPPORTED = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp", ".gif"}

def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        logging.exception("Не удалось прочитать %s", path)
        return default

def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")

def make_photo(source, width_cm=3.0, height_cm=4.0, dpi=300, mode="Заполнить (обрезать)", focus_x=0.5, focus_y=0.5, zoom=1.0):
    with Image.open(source) as raw:
        im = ImageOps.exif_transpose(raw).convert("RGB")
        w, h = max(1, round(width_cm / 2.54 * dpi)), max(1, round(height_cm / 2.54 * dpi))
        if mode.startswith("Заполнить"):
            src_ratio, dst_ratio = im.width / im.height, w / h
            # Выбираем область нужного соотношения сторон. focus_x/focus_y задают
            # положение рамки, zoom > 1 приближает изображение внутри рамки.
            if src_ratio > dst_ratio:
                crop_h = im.height / zoom
                crop_w = crop_h * dst_ratio
                if crop_w > im.width:
                    crop_w = im.width / zoom
                    crop_h = crop_w / dst_ratio
            else:
                crop_w = im.width / zoom
                crop_h = crop_w / dst_ratio
                if crop_h > im.height:
                    crop_h = im.height / zoom
                    crop_w = crop_h * dst_ratio
            cx = min(max(focus_x, 0.0), 1.0) * im.width
            cy = min(max(focus_y, 0.0), 1.0) * im.height
            left = min(max(0, round(cx - crop_w / 2)), max(0, round(im.width - crop_w)))
            top = min(max(0, round(cy - crop_h / 2)), max(0, round(im.height - crop_h)))
            right = min(im.width, round(left + crop_w))
            bottom = min(im.height, round(top + crop_h))
            im = im.crop((left, top, right, bottom))
            im = im.resize((w, h), Image.Resampling.LANCZOS)
        else:
            im.thumbnail((w, h), Image.Resampling.LANCZOS)
            canvas = Image.new("RGB", (w, h), "white")
            canvas.paste(im, ((w-im.width)//2, (h-im.height)//2))
            im = canvas
        return im, w, h

def detect_face_focus(source):
    """Return normalized crop focus around the largest detected face.

    OpenCV is optional. When unavailable or no face is detected, return None
    so the normal centered/manual crop remains available.
    """
    try:
        import cv2
        import numpy as np
        with Image.open(source) as raw:
            rgb = np.array(ImageOps.exif_transpose(raw).convert("RGB"))
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        cascade_path = str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")
        cascade = cv2.CascadeClassifier(cascade_path)
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(36, 36))
        if len(faces) == 0:
            return None
        x, y, w, h = max(faces, key=lambda r: int(r[2]) * int(r[3]))
        # Place crop center slightly below face center to retain head and shoulders.
        cx = (x + w / 2) / rgb.shape[1]
        cy = min(0.92, (y + h * 1.10) / rgb.shape[0])
        return (float(cx), float(cy), (int(x), int(y), int(w), int(h)))
    except ImportError:
        return None
    except Exception:
        logging.exception("Face detection failed: %s", source)
        return None


class DropList(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DropOnly)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls(): e.acceptProposedAction()
        else: e.ignore()
    def dragMoveEvent(self, e): e.acceptProposedAction()
    def dropEvent(self, e: QDropEvent):
        paths = [u.toLocalFile() for u in e.mimeData().urls()]
        self.window().add_files(paths)
        e.acceptProposedAction()


class CropPreview(QLabel):
    """Preview with drag-to-reframe and mouse-wheel zoom."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(320, 420)
        self.setMouseTracking(True)
        self.focus_x = 0.5
        self.focus_y = 0.5
        self.zoom = 1.0
        self.on_change = None
        self._drag_pos = None
        self.setToolTip("Перетаскивайте фото мышью, чтобы изменить кадр. Колёсико мыши — приблизить/отдалить.")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.position()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None:
            delta = event.position() - self._drag_pos
            self._drag_pos = event.position()
            # Moving the visible crop frame to the right reveals more of the
            # source image on the left, hence the inverse movement of focus.
            self.focus_x = min(1.0, max(0.0, self.focus_x - delta.x() / max(1, self.width()) * 0.9))
            self.focus_y = min(1.0, max(0.0, self.focus_y - delta.y() / max(1, self.height()) * 0.9))
            if self.on_change:
                self.on_change()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = None
            self.setCursor(Qt.ArrowCursor)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        step = 1.08 if event.angleDelta().y() > 0 else 1 / 1.08
        self.zoom = min(3.0, max(1.0, self.zoom * step))
        if self.on_change:
            self.on_change()
        event.accept()

    def reset_crop(self):
        self.focus_x = 0.5
        self.focus_y = 0.5
        self.zoom = 1.0
        if self.on_change:
            self.on_change()

class EmployeeDialog(QDialog):
    def __init__(self, parent=None, record=None):
        super().__init__(parent)
        self.setWindowTitle("Карточка сотрудника")
        self.setMinimumWidth(460)
        form = QFormLayout(self)
        record = dict(record) if record else {}
        self.full_name = QLineEdit(record.get("full_name", ""))
        self.organization = QLineEdit(record.get("organization", "ООО \"Пирог Улыбка\""))
        self.department = QLineEdit(record.get("department", ""))
        self.position = QLineEdit(record.get("position", ""))
        self.badge_number = QLineEdit(record.get("badge_number", ""))
        self.valid_until = QLineEdit(record.get("valid_until", ""))
        self.photo_path = QLineEdit(record.get("photo_path", ""))
        photo_row = QHBoxLayout(); photo_row.addWidget(self.photo_path)
        browse = QPushButton("Выбрать…")
        browse.clicked.connect(self.pick_photo)
        photo_row.addWidget(browse)
        photo_wrap = QWidget(); photo_wrap.setLayout(photo_row)
        form.addRow("ФИО *", self.full_name)
        form.addRow("Организация", self.organization)
        form.addRow("Подразделение", self.department)
        form.addRow("Должность", self.position)
        form.addRow("Номер пропуска", self.badge_number)
        form.addRow("Действует до (ДД.ММ.ГГГГ)", self.valid_until)
        form.addRow("Исходная фотография", photo_wrap)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def pick_photo(self):
        path, _ = QFileDialog.getOpenFileName(self, "Фотография сотрудника", "", "Изображения (*.jpg *.jpeg *.png *.bmp *.webp *.tif)")
        if path: self.photo_path.setText(path)

    def values(self):
        return {"full_name": self.full_name.text().strip(), "organization": self.organization.text().strip(),
                "department": self.department.text().strip(), "position": self.position.text().strip(),
                "badge_number": self.badge_number.text().strip(), "valid_until": self.valid_until.text().strip(),
                "photo_path": self.photo_path.text().strip()}

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        icon_path = RESOURCES_DIR / "PSrazmer.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.resize(1180, 780)
        self.setMinimumSize(900, 620)
        self.files = []
        self.prepared = {}
        self.settings = load_json(SETTINGS_FILE, {})
        self.history = load_json(HISTORY_FILE, [])
        self.build_ui()
        self.apply_settings()
        self.refresh_history()
        self.statusBar().showMessage("Готово к работе")

    def build_ui(self):
        self.setStyleSheet("""
        /* Unified compact desktop typography inspired by Hikvision iVMS-4200 */
        QMainWindow, QWidget {
          background:#171c26; color:#e8edf5;
          font-family:"Arial","Segoe UI",sans-serif;
          font-size:9pt; font-weight:normal;
        }
        QLabel { font-family:"Arial","Segoe UI",sans-serif; font-size:9pt; }
        QPushButton {
          background:#315f9c; color:white; border:0; border-radius:4px;
          padding:6px 9px; min-height:30px;
          font-family:"Arial","Segoe UI",sans-serif;
          font-size:8.5pt; font-weight:normal;
        }
        QPushButton:hover { background:#4078bd; }
        QPushButton:pressed { background:#284d7e; }
        QPushButton:disabled { background:#3a414d; color:#9aa4b2; }
        QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QListWidget,
        QPlainTextEdit {
          background:#202735; border:1px solid #3a4659; border-radius:4px;
          padding:5px 7px; color:#f0f3f8;
          font-family:"Arial","Segoe UI",sans-serif; font-size:9pt;
        }
        QComboBox QAbstractItemView {
          background:#202735; color:#f0f3f8; selection-background-color:#35445b;
          border:1px solid #3a4659; font-family:"Arial","Segoe UI",sans-serif;
          font-size:9pt;
        }
        QTabWidget::pane { border:1px solid #30394a; border-radius:5px; }
        QTabBar::tab {
          background:#222a38; padding:7px 12px; margin-right:3px; min-height:26px;
          border-top-left-radius:4px; border-top-right-radius:4px;
          font-family:"Arial","Segoe UI",sans-serif; font-size:9pt;
        }
        QTabBar::tab:selected { background:#35445b; color:#ffffff; }
        QGroupBox {
          border:1px solid #354154; border-radius:5px; margin-top:10px;
          padding:10px; font-family:"Arial","Segoe UI",sans-serif;
          font-size:9pt; font-weight:bold;
        }
        QGroupBox::title { subcontrol-origin:margin; left:10px; padding:0 4px; }
        QLabel#muted { color:#9eacbf; }
        QProgressBar {
          border:1px solid #3a4659; border-radius:4px; text-align:center;
          background:#202735; font-family:"Arial","Segoe UI",sans-serif;
          font-size:8pt;
        }
        QProgressBar::chunk { background:#3c91d8; border-radius:3px; }
        QMenu, QMenuBar, QStatusBar, QToolTip, QMessageBox {
          font-family:"Arial","Segoe UI",sans-serif; font-size:9pt;
        }
        QMenu { background:#202735; color:#e8edf5; border:1px solid #3a4659; }
        QMenu::item { padding:6px 24px 6px 20px; }
        QMenu::item:selected { background:#35445b; }
        QToolTip { background:#222a38; color:#f0f3f8; border:1px solid #526078; padding:4px; }
        QScrollBar:vertical { background:#202735; width:11px; margin:0; }
        QScrollBar::handle:vertical { background:#526078; min-height:24px; border-radius:4px; }
        QScrollBar:horizontal { background:#202735; height:11px; margin:0; }
        QScrollBar::handle:horizontal { background:#526078; min-width:24px; border-radius:4px; }
        """)
        tabs = QTabWidget()
        self.setCentralWidget(tabs)

        prep = QWidget(); root = QVBoxLayout(prep)
        top = QHBoxLayout()
        self.add_btn = QPushButton("＋ Добавить фотографии")
        self.add_btn.clicked.connect(self.choose_files)
        self.remove_btn = QPushButton("Удалить выбранные")
        self.remove_btn.clicked.connect(self.remove_selected)
        self.clear_btn = QPushButton("Очистить список")
        self.clear_btn.clicked.connect(self.clear_files)
        top.addWidget(self.add_btn); top.addWidget(self.remove_btn); top.addWidget(self.clear_btn); top.addStretch()
        root.addLayout(top)
        splitter = QSplitter()
        left = QWidget(); ll = QVBoxLayout(left)
        ll.addWidget(QLabel("Фотографии — можно перетащить сюда файлы или целую группу"))
        self.file_list = DropList()
        self.file_list.currentItemChanged.connect(self.preview_selected)
        ll.addWidget(self.file_list)
        self.count_label = QLabel("Файлов: 0"); self.count_label.setObjectName("muted")
        ll.addWidget(self.count_label)
        right = QWidget(); rl = QVBoxLayout(right)
        self.preview = CropPreview()
        self.preview.setText("Предварительный просмотр")
        self.preview.on_change = self.preview_selected
        self.preview.setStyleSheet("background:#10151d;border:1px dashed #526078;border-radius:10px;")
        rl.addWidget(self.preview, 1)
        self.info = QLabel("Выберите фото. Перетаскивайте его мышью для кадрирования; колёсико — масштаб.")
        self.info.setObjectName("muted")
        rl.addWidget(self.info)
        crop_actions = QHBoxLayout()
        reset_crop_btn = QPushButton("Сбросить кадрирование")
        reset_crop_btn.clicked.connect(self.preview.reset_crop)
        self.face_btn = QPushButton("Найти лицо")
        self.face_btn.setToolTip("Определить положение лица на выбранной фотографии")
        self.face_btn.clicked.connect(self.detect_selected_face)
        crop_actions.addWidget(reset_crop_btn); crop_actions.addWidget(self.face_btn)
        rl.addLayout(crop_actions)
        splitter.addWidget(left); splitter.addWidget(right); splitter.setSizes([420, 650])
        root.addWidget(splitter, 1)
        settings_box = QGroupBox("Параметры подготовки")
        form = QGridLayout(settings_box)
        self.preset = QComboBox()
        self.preset.addItems([
            "Свои размеры",
            "Паспорт / ID (35 × 45 мм)",
            "Фото 3 × 4 см",
            "Фото 4 × 6 см",
            "Фото 9 × 13 см",
            "Фото 10 × 15 см",
            "Квадрат (1:1)",
            "Визовый формат США (51 × 51 мм)",
            "Пропуск Внуково (окно фото ≈ 21,8 × 29 мм)"
        ])
        self.preset.currentIndexChanged.connect(self.apply_preset)
        self.width_cm = QDoubleSpinBox(); self.width_cm.setRange(0.5, 30); self.width_cm.setDecimals(2); self.width_cm.setSingleStep(0.1); self.width_cm.setValue(3); self.width_cm.setSuffix(" см")
        self.height_cm = QDoubleSpinBox(); self.height_cm.setRange(0.5, 30); self.height_cm.setDecimals(2); self.height_cm.setSingleStep(0.1); self.height_cm.setValue(4); self.height_cm.setSuffix(" см")
        self.dpi = QSpinBox(); self.dpi.setRange(72, 1200); self.dpi.setValue(300); self.dpi.setSuffix(" DPI")
        self.mode = QComboBox(); self.mode.addItems(["Заполнить (обрезать)", "Вписать целиком (с полями)"])
        self.format = QComboBox(); self.format.addItems(FORMATS)
        self.quality = QSpinBox(); self.quality.setRange(50, 100); self.quality.setValue(95)
        self.name_prefix = QLineEdit("Фото")
        self.auto_face = QCheckBox("Автоподгон лица при пакетной обработке")
        self.auto_face.setChecked(True)
        self.auto_face.setToolTip("Для каждого фото пакетно определять лицо, если установлен OpenCV")
        form.addWidget(QLabel("Быстрый шаблон"),0,0); form.addWidget(self.preset,0,1,1,3)
        form.addWidget(QLabel("Ширина"),0,4); form.addWidget(self.width_cm,0,5)
        form.addWidget(QLabel("Высота"),0,6); form.addWidget(self.height_cm,0,7)
        form.addWidget(QLabel("Разрешение"),1,0); form.addWidget(self.dpi,1,1)
        form.addWidget(QLabel("Кадрирование"),1,2); form.addWidget(self.mode,1,3,1,2)
        form.addWidget(QLabel("Формат сохранения"),1,5); form.addWidget(self.format,1,6)
        form.addWidget(QLabel("Качество JPG/WEBP"),1,7); form.addWidget(self.quality,1,8)
        form.addWidget(QLabel("Префикс имени"),2,0); form.addWidget(self.name_prefix,2,1)
        form.addWidget(self.auto_face,2,2,1,4)
        root.addWidget(settings_box)
        actions = QHBoxLayout()
        self.prepare_btn = QPushButton("Подготовить фото")
        self.prepare_btn.setToolTip("Подготовить выбранные фотографии или все фотографии")
        self.prepare_btn.clicked.connect(self.prepare_all)
        self.export_btn = QPushButton("Сохранить фото…")
        self.export_btn.setToolTip("Сохранить выбранное фото как…")
        self.export_btn.clicked.connect(self.save_one_as)
        self.export_all_btn = QPushButton("Сохранить все…")
        self.export_all_btn.setToolTip("Сохранить все фотографии в папку…")
        self.export_all_btn.clicked.connect(self.export_all)
        self.xlsx_btn = QPushButton("Excel-каталог")
        self.xlsx_btn.setToolTip("Создать Excel-каталог")
        self.xlsx_btn.clicked.connect(self.export_xlsx)
        actions.addWidget(self.prepare_btn); actions.addWidget(self.export_btn); actions.addWidget(self.export_all_btn); actions.addWidget(self.xlsx_btn)
        root.addLayout(actions)
        self.progress = QProgressBar(); self.progress.setValue(0); root.addWidget(self.progress)
        tabs.addTab(prep, "Подготовка фото")

        magic = QWidget(); ml = QVBoxLayout(magic)
        intro = QLabel("Профиль оборудования: Magicard 300 + Magicard HUB 2.0.6. В редакторе выбран CR80 (85,60 × 53,98 мм). По присланному скриншоту рамка портрета оценена примерно в 21,8 × 29,0 мм (ширина × высота), JPG, 300 DPI. Это оценка по экранному изображению; перед серийной печатью проверьте Width/Height/Position объекта Image в HUB.")
        intro.setWordWrap(True); ml.addWidget(intro)
        mbox = QGroupBox("Быстрый перенос")
        mf = QFormLayout(mbox)
        self.hub_path = QLineEdit(self.settings.get("hub_path",""))
        hubrow = QHBoxLayout(); hubrow.addWidget(self.hub_path)
        browse = QPushButton("Обзор…"); browse.clicked.connect(self.choose_hub); hubrow.addWidget(browse)
        hubwrap = QWidget(); hubwrap.setLayout(hubrow)
        self.magicard_file = QLineEdit()
        self.magicard_file.setPlaceholderText("Выберите готовое фото на первой вкладке")
        mf.addRow("Приложение Magicard HUB (необязательно)", hubwrap)
        mf.addRow("Текущее фото", self.magicard_file)
        row = QHBoxLayout()
        copy_btn = QPushButton("Подготовить для HUB"); copy_btn.setToolTip("Подготовить фото для Magicard HUB"); copy_btn.clicked.connect(self.copy_for_hub)
        open_hub_btn = QPushButton("Открыть Magicard HUB"); open_hub_btn.clicked.connect(self.open_hub)
        open_folder_btn = QPushButton("Папка готовых фото"); open_folder_btn.setToolTip("Открыть папку готовых фото"); open_folder_btn.clicked.connect(self.open_output)
        row.addWidget(copy_btn); row.addWidget(open_hub_btn); row.addWidget(open_folder_btn)
        mf.addRow(row); ml.addWidget(mbox)
        auto = QGroupBox("Пошаговая вставка в карточку человека")
        al = QVBoxLayout(auto)
        al.addWidget(QLabel("Magicard HUB поддерживает импорт данных CSV/Excel. Кнопка «CSV для HUB + фото» готовит таблицу сотрудников и локальные JPG. В мастере импорта HUB сопоставьте поля; возможность связать столбец PhotoFile с полем изображения нужно проверить на установленной версии. Для одиночной записи используйте выделенный JPG и штатную команду выбора фотографии."))
        auto_btn = QPushButton("Подготовить фото и открыть HUB"); auto_btn.clicked.connect(self.guided_insert)
        al.addWidget(auto_btn)
        ml.addWidget(auto); ml.addStretch()
        tabs.addTab(magic, "Magicard HUB")

        emp = QWidget(); el = QVBoxLayout(emp)
        intro_emp = QLabel("Локальный реестр сотрудников Внуково. Данные хранятся в SQLite на этом компьютере; портреты готовятся примерно 21,8 × 29,0 мм / 300 DPI по присланному скриншоту CR80. Перед тиражом сверьте точный размер Image в свойствах элемента HUB.")
        intro_emp.setWordWrap(True); el.addWidget(intro_emp)
        self.employee_table = QTableWidget(0, 6)
        self.employee_table.setHorizontalHeaderLabels(["ID", "ФИО", "Организация", "Должность", "№ пропуска", "Действует до"])
        self.employee_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.employee_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.employee_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.employee_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.employee_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        el.addWidget(self.employee_table, 1)
        erow = QHBoxLayout()
        for label, slot in [("＋ Добавить", self.add_employee), ("Изменить", self.edit_employee), ("Удалить", self.delete_employee), ("Подготовить фото", self.prepare_employee_photo), ("Открыть HUB с фото", self.send_employee_to_hub), ("Экспорт карточки PNG", self.export_employee_card), ("Импорт CSV", self.import_employees_csv), ("Экспорт CSV", self.export_employees_csv), ("CSV для HUB + фото", self.export_hub_bundle_csv)]:
            b = QPushButton(label); b.clicked.connect(slot); erow.addWidget(b)
        el.addLayout(erow)
        tabs.addTab(emp, "Сотрудники Внуково")
        self.refresh_employees()

        hist = QWidget(); hl = QVBoxLayout(hist)
        hl.addWidget(QLabel("История подготовленных файлов"))
        self.history_list = QListWidget(); hl.addWidget(self.history_list)
        hrow = QHBoxLayout()
        refresh = QPushButton("Обновить"); refresh.clicked.connect(self.refresh_history)
        open_hist = QPushButton("Открыть папку"); open_hist.clicked.connect(self.open_output)
        clear_hist = QPushButton("Очистить историю"); clear_hist.clicked.connect(self.clear_history)
        hrow.addWidget(refresh); hrow.addWidget(open_hist); hrow.addWidget(clear_hist); hl.addLayout(hrow)
        tabs.addTab(hist, "История")

        about = QWidget(); abl = QVBoxLayout(about)
        abl.addWidget(QLabel("<h2>PSразмер изображений PRO</h2><p>Универсальный редактор размера изображений и фотографий: для паспорта, ID-карты, визы, пропуска, печати и публикации в интернете.</p><p>Быстрые шаблоны размеров, точные сантиметры и DPI, сохранение одного фото через «Сохранить как…» или пакетный экспорт.</p><p>Логи: logs/psrazmer.log<br>Настройки и история: data/</p><p>Пароли и данные Magicard HUB программа не запрашивает и не хранит.</p>"))
        tabs.addTab(about, "О программе")

        # Keep button labels readable at different window sizes and Windows DPI scales.
        for button in self.findChildren(QPushButton):
            button.setMinimumHeight(36)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            button.setToolTip(button.toolTip() or button.text())

        # Long explanatory labels wrap instead of being cut off.
        for label in self.findChildren(QLabel):
            label.setWordWrap(True)

    def apply_settings(self):
        self.hub_path.setText(self.settings.get("hub_path",""))
        self.settings.setdefault("printer_model", "Magicard 300")
        self.settings.setdefault("hub_version", "2.0.6")
        self.settings.setdefault("photo_profile", "Vnukovo portrait approx. 21.8x29.0mm 300dpi (estimated from HUB screenshot)")

    def apply_preset(self, index):
        presets_cm = {
            1: (3.5, 4.5),       # common passport / ID photo size; check local authority rules
            2: (3.0, 4.0),
            3: (4.0, 6.0),
            4: (9.0, 13.0),
            5: (10.0, 15.0),
            6: (4.0, 4.0),
            7: (5.1, 5.1),       # US-style square photo
            8: (VNUKOVO_PHOTO_WIDTH_CM, VNUKOVO_PHOTO_HEIGHT_CM),  # estimated from supplied HUB screenshot
        }
        if index in presets_cm:
            w, h = presets_cm[index]
            self.width_cm.setValue(w)
            self.height_cm.setValue(h)
            if index == 8:
                self.name_prefix.setText("Vnukovo")
                self.dpi.setValue(300)
                self.format.setCurrentText("JPG")
                self.mode.setCurrentText("Заполнить (обрезать)")
            self.preview_selected()

    def save_one_as(self):
        row = self.file_list.currentRow()
        if row < 0 or row >= len(self.files):
            QMessageBox.information(self, APP_NAME, "Выберите фотографию в списке.")
            return
        source = self.files[row]
        try:
            im, w, h = make_photo(source, self.width_cm.value(), self.height_cm.value(),
                                  self.dpi.value(), self.mode.currentText(),
                                  self.preview.focus_x, self.preview.focus_y, self.preview.zoom)
            ext = self.format.currentText().lower()
            suffix = "jpg" if ext == "jpg" else ext
            default_name = f"{Path(source).stem}_{w}x{h}.{suffix}"
            target, _ = QFileDialog.getSaveFileName(
                self, "Сохранить изображение как…", str(OUTPUT_DIR / default_name),
                "Изображения (*.jpg *.jpeg *.png *.webp *.tif *.tiff *.bmp *.gif)"
            )
            if not target:
                im.close()
                return
            target_path = Path(target)
            fmt = target_path.suffix.lower().lstrip(".")
            if fmt in ("jpg", "jpeg"):
                im.save(target_path, "JPEG", quality=self.quality.value(),
                        dpi=(self.dpi.value(), self.dpi.value()), optimize=True)
                fmt_label = "JPG"
            elif fmt == "png":
                im.save(target_path, "PNG", dpi=(self.dpi.value(), self.dpi.value()), optimize=True)
                fmt_label = "PNG"
            elif fmt == "webp":
                im.save(target_path, "WEBP", quality=self.quality.value(),
                        method=6, dpi=(self.dpi.value(), self.dpi.value()))
                fmt_label = "WEBP"
            elif fmt in ("tif", "tiff"):
                im.save(target_path, "TIFF", dpi=(self.dpi.value(), self.dpi.value()),
                        compression="tiff_lzw")
                fmt_label = "TIFF"
            elif fmt == "bmp":
                im.save(target_path, "BMP", dpi=(self.dpi.value(), self.dpi.value()))
                fmt_label = "BMP"
            elif fmt == "gif":
                im.convert("P", palette=Image.Palette.ADAPTIVE).save(target_path, "GIF", optimize=True)
                fmt_label = "GIF"
            else:
                target_path = target_path.with_suffix(".jpg")
                im.save(target_path, "JPEG", quality=self.quality.value(),
                        dpi=(self.dpi.value(), self.dpi.value()), optimize=True)
                fmt_label = "JPG"
            self.prepared[source] = (im.copy(), w, h)
            self.add_history(str(target_path), w, h, fmt_label)
            self.refresh_history()
            self.magicard_file.setText(str(target_path))
            self.statusBar().showMessage(f"Сохранено: {target_path}", 6000)
            im.close()
        except Exception as e:
            logging.exception("Save one as error")
            QMessageBox.critical(self, APP_NAME, f"Не удалось сохранить изображение:\\n{e}")

    def choose_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Добавить фотографии", "", "Изображения (*.jpg *.jpeg *.png *.webp *.tif *.tiff *.bmp *.gif)")
        self.add_files(paths)

    def add_files(self, paths):
        added = 0
        for path in paths:
            p = Path(path)
            if p.is_dir():
                candidates = [x for x in p.iterdir() if x.suffix.lower() in SUPPORTED]
            else:
                candidates = [p] if p.suffix.lower() in SUPPORTED else []
            for f in candidates:
                s = str(f.resolve())
                if s not in self.files and f.is_file():
                    self.files.append(s); self.file_list.addItem(QListWidgetItem(f.name)); added += 1
        self.count_label.setText(f"Файлов: {len(self.files)}")
        if added: self.statusBar().showMessage(f"Добавлено файлов: {added}", 4000)
        if self.file_list.count(): self.file_list.setCurrentRow(0)

    def remove_selected(self):
        rows = sorted({self.file_list.row(i) for i in self.file_list.selectedItems()}, reverse=True)
        for r in rows:
            self.file_list.takeItem(r); self.files.pop(r)
        self.count_label.setText(f"Файлов: {len(self.files)}")
        self.preview_selected()

    def clear_files(self):
        self.files.clear(); self.prepared.clear(); self.file_list.clear()
        self.preview.clear(); self.preview.setText("Предварительный просмотр"); self.preview.reset_crop()
        self.count_label.setText("Файлов: 0"); self.magicard_file.clear()

    def preview_selected(self, *args):
        row = self.file_list.currentRow()
        if row < 0 or row >= len(self.files): return
        path = self.files[row]
        try:
            im, w, h = make_photo(path, self.width_cm.value(), self.height_cm.value(), self.dpi.value(), self.mode.currentText(), self.preview.focus_x, self.preview.focus_y, self.preview.zoom)
            buf = io.BytesIO(); im.save(buf, format="PNG")
            qimg = QImage.fromData(buf.getvalue())
            pix = QPixmap.fromImage(qimg).scaled(self.preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.preview.setPixmap(pix)
            self.info.setText(f"{Path(path).name} · результат {w} × {h} px · {self.dpi.value()} DPI")
            im.close(); buf.close()
        except Exception as e:
            self.preview.setText("Не удалось открыть изображение")
            self.info.setText(str(e)); logging.exception("Preview error: %s", path)

    def detect_selected_face(self):
        row = self.file_list.currentRow()
        if row < 0 or row >= len(self.files):
            QMessageBox.information(self, APP_NAME, "Сначала выберите фотографию.")
            return
        result = detect_face_focus(self.files[row])
        if result is None:
            QMessageBox.information(self, APP_NAME,
                "Лицо не найдено или модуль распознавания не установлен.\n"
                "Можно установить OpenCV командой: pip install opencv-python-headless\n"
                "Либо выполнить кадрирование вручную мышью.")
            return
        self.preview.focus_x, self.preview.focus_y, _ = result
        self.preview_selected()
        self.statusBar().showMessage("Лицо найдено — кадрирование обновлено", 5000)

    def prepare_all(self):
        if not self.files:
            QMessageBox.information(self, APP_NAME, "Сначала добавьте фотографии."); return
        selected = sorted({self.file_list.row(i) for i in self.file_list.selectedItems()})
        indexes = selected if selected else list(range(len(self.files)))
        self.progress.setMaximum(len(indexes)); self.progress.setValue(0)
        success = 0
        for n, idx in enumerate(indexes, 1):
            source = self.files[idx]
            try:
                fx, fy = self.preview.focus_x, self.preview.focus_y
                zoom = self.preview.zoom
                if self.auto_face.isChecked():
                    face = detect_face_focus(source)
                    if face is not None:
                        fx, fy, _ = face
                        zoom = max(zoom, 1.08)
                im, w, h = make_photo(source, self.width_cm.value(), self.height_cm.value(), self.dpi.value(), self.mode.currentText(), fx, fy, zoom)
                self.prepared[source] = (im.copy(), w, h)
                success += 1
            except Exception:
                logging.exception("Prepare error: %s", source)
            self.progress.setValue(n)
        self.statusBar().showMessage(f"Подготовлено: {success} из {len(indexes)}", 6000)
        self.preview_selected()

    def export_all(self):
        if not self.prepared: self.prepare_all()
        if not self.prepared: return
        ext = self.format.currentText().lower()
        outdir_text = QFileDialog.getExistingDirectory(self, "Папка для экспорта", str(OUTPUT_DIR))
        if not outdir_text: return
        outdir = Path(outdir_text)
        saved = 0
        for i, (src, (im, w, h)) in enumerate(self.prepared.items(), 1):
            try:
                stem = Path(src).stem
                name = f"{self.name_prefix.text().strip() or 'Фото'}_{stem}"
                target = outdir / f"{name}.{ext.lower()}"
                if ext == "JPG":
                    im.save(target, "JPEG", quality=self.quality.value(), dpi=(self.dpi.value(), self.dpi.value()), optimize=True)
                elif ext == "WEBP":
                    im.save(target, "WEBP", quality=self.quality.value(), method=6, dpi=(self.dpi.value(), self.dpi.value()))
                elif ext == "PNG":
                    im.save(target, "PNG", dpi=(self.dpi.value(), self.dpi.value()), optimize=True)
                elif ext == "TIFF":
                    im.save(target, "TIFF", dpi=(self.dpi.value(), self.dpi.value()), compression="tiff_lzw")
                elif ext == "BMP":
                    im.save(target, "BMP", dpi=(self.dpi.value(), self.dpi.value()))
                else:
                    im.convert("P", palette=Image.Palette.ADAPTIVE).save(target, "GIF", optimize=True)
                self.add_history(str(target), w, h, ext)
                saved += 1
            except Exception:
                logging.exception("Export error: %s", src)
        self.refresh_history()
        QMessageBox.information(self, APP_NAME, f"Экспортировано файлов: {saved}\nПапка: {outdir}")

    def export_xlsx(self):
        if not self.prepared: self.prepare_all()
        if not self.prepared: return
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить Excel-каталог", str(OUTPUT_DIR / "Каталог_фото.xlsx"), "Excel (*.xlsx)")
        if not path: return
        wb = Workbook(); ws = wb.active; ws.title = "Фотографии"
        ws.append(["Исходный файл", "Ширина, см", "Высота, см", "Размер, px", "DPI", "Формат"])
        tempfiles = []
        try:
            for row, (src, (im, w, h)) in enumerate(self.prepared.items(), 2):
                ws.cell(row,1,Path(src).name); ws.cell(row,2,self.width_cm.value()); ws.cell(row,3,self.height_cm.value())
                ws.cell(row,4,f"{w} × {h}"); ws.cell(row,5,self.dpi.value()); ws.cell(row,6,self.format.currentText())
                tmp = TEMP_DIR / f"excel_image_{row}.png"; im.save(tmp, "PNG"); tempfiles.append(tmp)
                pic = XLImage(str(tmp)); pic.width = 90; pic.height = 120; ws.add_image(pic, f"G{row}")
                ws.row_dimensions[row].height = 95
            ws.column_dimensions["A"].width = 32
            for col in "BCDEF": ws.column_dimensions[col].width = 16
            ws.column_dimensions["G"].width = 18
            wb.save(path)
            QMessageBox.information(self, APP_NAME, f"Excel-каталог сохранён:\n{path}")
        except Exception as e:
            logging.exception("XLSX export error")
            QMessageBox.critical(self, APP_NAME, f"Ошибка создания Excel:\n{e}")
        finally:
            for f in tempfiles:
                try: f.unlink(missing_ok=True)
                except Exception: pass

    def add_history(self, path, w, h, fmt):
        self.history.insert(0, {"path":path, "date":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "pixels":f"{w}x{h}", "format":fmt})
        self.history = self.history[:500]
        save_json(HISTORY_FILE, self.history)

    def refresh_history(self):
        if not hasattr(self, "history_list"): return
        self.history_list.clear()
        for item in self.history:
            self.history_list.addItem(f"{item.get('date','')} | {Path(item.get('path','')).name} | {item.get('pixels','')} | {item.get('format','')}")

    def clear_history(self):
        if QMessageBox.question(self, APP_NAME, "Очистить историю?") == QMessageBox.Yes:
            self.history = []; save_json(HISTORY_FILE, self.history); self.refresh_history()

    def current_prepared_path(self):
        row = self.file_list.currentRow()
        if row >= 0 and row < len(self.files):
            src = self.files[row]
            if src in self.prepared:
                target = OUTPUT_DIR / f"{Path(src).stem}_prepared.jpg"
                self.prepared[src][0].save(target, "JPEG", quality=95, dpi=(self.dpi.value(), self.dpi.value()))
                self.add_history(str(target), self.prepared[src][1], self.prepared[src][2], "JPG")
                self.refresh_history()
                return str(target)
            QMessageBox.information(self, APP_NAME, "Сначала нажмите «Подготовить выбранные / все».")
        elif self.prepared:
            src, (im,w,h) = next(iter(self.prepared.items()))
            target = OUTPUT_DIR / f"{Path(src).stem}_prepared.jpg"
            im.save(target, "JPEG", quality=95, dpi=(self.dpi.value(), self.dpi.value()))
            return str(target)
        return None

    def copy_for_hub(self):
        # Privacy-first: never place an ID photo into the Windows clipboard.
        path = self.current_prepared_path()
        if not path:
            return
        self.magicard_file.setText(path)
        self.statusBar().showMessage("Фото сохранено локально для Magicard HUB.", 8000)
        QMessageBox.information(
            self, APP_NAME,
            "Фото подготовлено и сохранено локально:\n\n" + path +
            "\n\nОткройте Magicard HUB и выберите этот файл через кнопку добавления фотографии. "
            "Буфер обмена Windows не используется для защиты конфиденциальности."
        )

    def choose_hub(self):
        path, _ = QFileDialog.getOpenFileName(self, "Выбрать Magicard HUB", "", "Программы (*.exe);;Все файлы (*)")
        if path:
            self.hub_path.setText(path); self.settings["hub_path"] = path; save_json(SETTINGS_FILE, self.settings)

    def open_hub(self):
        path = self.hub_path.text().strip()
        if path and Path(path).exists():
            try: os.startfile(path) if os.name == "nt" else subprocess.Popen([path])
            except Exception as e: QMessageBox.warning(self, APP_NAME, f"Не удалось открыть HUB:\n{e}")
        else:
            QMessageBox.information(self, APP_NAME, "Укажите путь к исполняемому файлу Magicard HUB в поле выше. Если HUB уже открыт, переключитесь в его окно.")

    def open_output(self):
        OUTPUT_DIR.mkdir(exist_ok=True)
        try: os.startfile(str(OUTPUT_DIR)) if os.name == "nt" else subprocess.Popen(["xdg-open", str(OUTPUT_DIR)])
        except Exception: logging.exception("Open folder error")

    def guided_insert(self):
        # Save a local file and optionally launch HUB; no clipboard or network transfer.
        path = self.current_prepared_path()
        if not path:
            return
        self.magicard_file.setText(path)
        hub = self.hub_path.text().strip()
        if hub and Path(hub).exists():
            try:
                os.startfile(hub) if os.name == "nt" else subprocess.Popen([hub])
            except Exception as e:
                QMessageBox.warning(self, APP_NAME, f"Не удалось открыть HUB:\n{e}")
        try:
            if os.name == "nt":
                subprocess.Popen(["explorer", "/select,", str(Path(path).resolve())])
            else:
                self.open_output()
        except Exception:
            logging.exception("Could not reveal prepared photo")
        QMessageBox.information(
            self, "Фото подготовлено для Magicard HUB",
            "Готовый JPG сохранён:\n" + path +
            "\n\nПапка с файлом открыта. В HUB откройте карточку сотрудника и импортируйте выделенный JPG штатной командой. "
            "Прямое заполнение карточки пока не заявляется: оно зависит от версии HUB и доступных способов интеграции."
        )

    def refresh_employees(self):
        if not hasattr(self, "employee_table"): return
        with db_connect() as con:
            rows = con.execute("SELECT * FROM employees ORDER BY full_name COLLATE NOCASE").fetchall()
        self.employee_table.setRowCount(len(rows))
        for r, rec in enumerate(rows):
            values = [rec["id"], rec["full_name"], rec["organization"], rec["position"], rec["badge_number"], rec["valid_until"]]
            for c, value in enumerate(values):
                self.employee_table.setItem(r, c, QTableWidgetItem(str(value or "")))
        self.employee_table.resizeRowsToContents()

    def selected_employee_id(self):
        row = self.employee_table.currentRow() if hasattr(self, "employee_table") else -1
        if row < 0: return None
        item = self.employee_table.item(row, 0)
        return int(item.text()) if item else None

    def get_employee(self):
        emp_id = self.selected_employee_id()
        if emp_id is None:
            QMessageBox.information(self, APP_NAME, "Сначала выберите сотрудника."); return None
        with db_connect() as con:
            rec = con.execute("SELECT * FROM employees WHERE id=?", (emp_id,)).fetchone()
        return dict(rec) if rec else None

    def add_employee(self):
        dlg = EmployeeDialog(self)
        if dlg.exec() != QDialog.Accepted: return
        data = dlg.values()
        if not data["full_name"]:
            QMessageBox.warning(self, APP_NAME, "Заполните ФИО сотрудника."); return
        now = datetime.now().isoformat(timespec="seconds")
        with db_connect() as con:
            con.execute("INSERT INTO employees(full_name,organization,department,position,badge_number,valid_until,photo_path,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (*[data[k] for k in ("full_name","organization","department","position","badge_number","valid_until","photo_path")], now, now))
        self.refresh_employees()

    def edit_employee(self):
        rec = self.get_employee()
        if not rec: return
        dlg = EmployeeDialog(self, rec)
        if dlg.exec() != QDialog.Accepted: return
        data = dlg.values()
        if not data["full_name"]: QMessageBox.warning(self, APP_NAME, "Заполните ФИО."); return
        now = datetime.now().isoformat(timespec="seconds")
        with db_connect() as con:
            con.execute("UPDATE employees SET full_name=?,organization=?,department=?,position=?,badge_number=?,valid_until=?,photo_path=?,updated_at=? WHERE id=?",
                (*[data[k] for k in ("full_name","organization","department","position","badge_number","valid_until","photo_path")], now, rec["id"]))
        self.refresh_employees()

    def delete_employee(self):
        rec = self.get_employee()
        if not rec: return
        if QMessageBox.question(self, APP_NAME, f"Удалить запись сотрудника «{rec['full_name']}»? Фото на диске останется.") != QMessageBox.Yes: return
        with db_connect() as con: con.execute("DELETE FROM employees WHERE id=?", (rec["id"],))
        self.refresh_employees()

    def prepare_employee_photo(self):
        rec = self.get_employee()
        if not rec: return None
        src = Path(rec.get("photo_path", ""))
        if not src.is_file():
            QMessageBox.warning(self, APP_NAME, "У выбранного сотрудника не задана доступная фотография. Откройте «Изменить» и выберите файл."); return None
        try:
            focus = detect_face_focus(str(src))
            fx, fy = (focus[0], focus[1]) if focus else (0.5, 0.5)
            im, w, h = make_photo(str(src), VNUKOVO_PHOTO_WIDTH_CM, VNUKOVO_PHOTO_HEIGHT_CM, 300, "Заполнить (обрезать)", fx, fy, 1.08 if focus else 1.0)
            safe = re.sub(r"[^A-Za-zА-Яа-яЁё0-9_-]+", "_", rec.get("badge_number") or str(rec["id"])).strip("_") or str(rec["id"])
            target = OUTPUT_DIR / f"Vnukovo_{safe}_21_8x29mm_300dpi.jpg"
            im.save(target, "JPEG", quality=96, dpi=(300,300), optimize=True)
            im.close()
            with db_connect() as con: con.execute("UPDATE employees SET updated_at=? WHERE id=?", (datetime.now().isoformat(timespec="seconds"), rec["id"]))
            self.magicard_file.setText(str(target))
            self.statusBar().showMessage(f"Фото подготовлено: {target}", 7000)
            return target
        except Exception as e:
            logging.exception("Employee photo prepare failed")
            QMessageBox.critical(self, APP_NAME, f"Не удалось подготовить фотографию:\n{e}"); return None

    def send_employee_to_hub(self):
        target = self.prepare_employee_photo()
        if not target: return
        hub = self.hub_path.text().strip()
        try:
            if hub and Path(hub).is_file():
                if os.name == "nt": os.startfile(hub)
                else: subprocess.Popen([hub])
            if os.name == "nt": subprocess.Popen(["explorer", "/select,", str(target.resolve())])
            else: self.open_output()
            QMessageBox.information(self, APP_NAME, "Фото подготовлено и выделено в Проводнике. В Magicard HUB откройте запись сотрудника и импортируйте этот JPG штатной командой. Прямое заполнение карточки зависит от версии HUB и пока не имитируется.")
        except Exception as e: QMessageBox.warning(self, APP_NAME, f"Не удалось открыть HUB или Проводник:\n{e}")

    def export_employee_card(self):
        rec = self.get_employee()
        if not rec: return
        # Превью формата ID-1 (CR80), не является готовым макетом для печати без калибровки HUB.
        W, H = 1016, 638
        card = Image.new("RGB", (W,H), "white"); d = ImageDraw.Draw(card)
        d.rounded_rectangle((8,8,W-8,H-8), radius=26, outline="#2879ad", width=8)
        def font(sz, bold=False):
            candidates = ["C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
            for f in candidates:
                try: return ImageFont.truetype(f, sz)
                except Exception: pass
            return ImageFont.load_default()
        d.text((420,28), f"№ {rec.get('badge_number') or '—'}", fill="#111111", font=font(34,True))
        d.text((45,80), "ВНУКОВО", fill="#202a35", font=font(56,True))
        d.text((48,143), "Международный аэропорт", fill="#394553", font=font(24))
        d.text((55,235), rec.get("organization") or "Организация", fill="#111111", font=font(34,True))
        name = rec.get("full_name") or "ФИО сотрудника"
        d.text((55,320), name[:32], fill="#111111", font=font(34,True))
        d.text((55,382), (rec.get("department") or "")[:36], fill="#111111", font=font(30,True))
        d.text((55,438), (rec.get("position") or "Должность")[:36], fill="#222222", font=font(28))
        d.text((270,560), f"действует до {rec.get('valid_until') or '—'}", fill="#111111", font=font(26,True))
        photo_path = Path(rec.get("photo_path") or "")
        prepared = OUTPUT_DIR / f"Vnukovo_{re.sub(r'[^A-Za-zА-Яа-яЁё0-9_-]+','_', rec.get('badge_number') or str(rec['id']))}.jpg"
        if prepared.is_file(): photo_path = prepared
        if photo_path.is_file():
            try:
                with Image.open(photo_path) as ph:
                    ph = ImageOps.fit(ph.convert("RGB"), (240,300))
                    card.paste(ph, (710,45))
            except Exception: pass
        else:
            d.rectangle((710,45,950,345), outline="#8796a5", width=3)
            d.text((755,180), "ФОТО", fill="#8796a5", font=font(28,True))
        d.text((730,380), "CATERING", fill="#3d579f", font=font(34,True))
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить предварительный макет карты", str(OUTPUT_DIR / "card_preview.png"), "PNG (*.png)")
        if path:
            card.save(path, "PNG", dpi=(300,300))
            QMessageBox.information(self, APP_NAME, "Предварительный макет сохранён. Перед печатью нужно сверить поля, логотипы и физический размер с шаблоном Magicard HUB.")

    def import_employees_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, "Импорт сотрудников CSV", "", "CSV (*.csv)")
        if not path: return
        count = 0
        try:
            with open(path, "r", encoding="utf-8-sig", newline="") as f:
                sample = f.read(2048); f.seek(0)
                dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
                reader = csv.DictReader(f, dialect=dialect)
                aliases = {"ФИО":"full_name", "Организация":"organization", "Подразделение":"department", "Должность":"position", "Номер пропуска":"badge_number", "Действует до":"valid_until", "Фото":"photo_path"}
                with db_connect() as con:
                    for row in reader:
                        data = {aliases.get(k, k): (v or "").strip() for k,v in row.items() if k}
                        if not data.get("full_name"): continue
                        now = datetime.now().isoformat(timespec="seconds")
                        con.execute("INSERT INTO employees(full_name,organization,department,position,badge_number,valid_until,photo_path,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                            (data.get("full_name"),data.get("organization",""),data.get("department",""),data.get("position",""),data.get("badge_number",""),data.get("valid_until",""),data.get("photo_path",""),now,now)); count += 1
            self.refresh_employees(); QMessageBox.information(self, APP_NAME, f"Импортировано записей: {count}")
        except Exception as e: QMessageBox.critical(self, APP_NAME, f"Ошибка импорта CSV:\n{e}")

    def export_hub_bundle_csv(self):
        """Create a neutral CSV bridge plus locally prepared portrait files.
        HUB field mapping is completed by the operator during its supported import wizard.
        """
        with db_connect() as con:
            rows = [dict(r) for r in con.execute("SELECT * FROM employees ORDER BY full_name COLLATE NOCASE").fetchall()]
        if not rows:
            QMessageBox.information(self, APP_NAME, "Реестр сотрудников пуст."); return
        path, _ = QFileDialog.getSaveFileName(self, "Пакет CSV для Magicard HUB", str(OUTPUT_DIR / "Magicard_HUB_import.csv"), "CSV (*.csv)")
        if not path: return
        count, no_photo = 0, 0
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f, delimiter=";")
                writer.writerow(["FullName", "Organization", "Department", "Position", "BadgeNumber", "ValidUntil", "PhotoFile"])
                for rec in rows:
                    photo_out = ""
                    source = Path(rec.get("photo_path") or "")
                    if source.is_file():
                        face = detect_face_focus(str(source))
                        fx, fy = (face[0], face[1]) if face else (0.5, 0.5)
                        im, w, h = make_photo(str(source), VNUKOVO_PHOTO_WIDTH_CM, VNUKOVO_PHOTO_HEIGHT_CM, 300, "Заполнить (обрезать)", fx, fy, 1.08 if face else 1.0)
                        safe = re.sub(r"[^A-Za-zА-Яа-яЁё0-9_-]+", "_", rec.get("badge_number") or str(rec["id"])).strip("_") or str(rec["id"])
                        photo_target = OUTPUT_DIR / f"Vnukovo_{safe}_21_8x29mm_300dpi.jpg"
                        im.save(photo_target, "JPEG", quality=96, dpi=(300,300), optimize=True); im.close()
                        photo_out = str(photo_target.resolve())
                    else:
                        no_photo += 1
                    writer.writerow([rec.get("full_name", ""), rec.get("organization", ""), rec.get("department", ""),
                                     rec.get("position", ""), rec.get("badge_number", ""), rec.get("valid_until", ""), photo_out])
                    count += 1
            QMessageBox.information(self, APP_NAME,
                f"Подготовлен CSV-пакет: {count} записей\nБез исходного фото: {no_photo}\nCSV: {path}\n\nВ Magicard HUB используйте штатный импорт CSV/Excel и сопоставьте текстовые поля. Поле PhotoFile содержит путь к локальному JPG; возможность автоматического связывания этого столбца с image-полем зависит от конкретного мастера импорта HUB и должна быть проверена.")
        except Exception as e:
            logging.exception("Magicard HUB CSV export failed")
            QMessageBox.critical(self, APP_NAME, f"Ошибка создания пакета для HUB:\n{e}")

    def export_employees_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Экспорт сотрудников CSV", str(OUTPUT_DIR / "employees.csv"), "CSV (*.csv)")
        if not path: return
        with db_connect() as con: rows = con.execute("SELECT full_name,organization,department,position,badge_number,valid_until,photo_path FROM employees ORDER BY full_name").fetchall()
        headers = ["ФИО","Организация","Подразделение","Должность","Номер пропуска","Действует до","Фото"]
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f, delimiter=";"); writer.writerow(headers)
                for r in rows: writer.writerow(list(r))
            QMessageBox.information(self, APP_NAME, f"Экспортировано записей: {len(rows)}\n{path}")
        except Exception as e: QMessageBox.critical(self, APP_NAME, f"Ошибка экспорта:\n{e}")

    def closeEvent(self, event):
        self.settings["hub_path"] = self.hub_path.text().strip()
        self.settings["printer_model"] = "Magicard 300"
        self.settings["hub_version"] = "2.0.6"
        self.settings["photo_profile"] = "Vnukovo portrait approx. 21.8x29.0mm 300dpi (estimated from HUB screenshot)"
        save_json(SETTINGS_FILE, self.settings)
        try:
            db_backup = BACKUP_DIR / f"employees_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sqlite3"
            shutil.copy2(DB_FILE, db_backup)
            db_backups = sorted(BACKUP_DIR.glob("employees_*.sqlite3"), key=lambda x: x.stat().st_mtime, reverse=True)
            for old_db in db_backups[10:]: old_db.unlink(missing_ok=True)
            backup_name = BACKUP_DIR / f"settings_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            shutil.copy2(SETTINGS_FILE, backup_name)
            backups = sorted(BACKUP_DIR.glob("settings_*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
            for old_backup in backups[20:]:
                old_backup.unlink(missing_ok=True)
        except Exception:
            logging.exception("Settings backup failed")
        for im, _, _ in self.prepared.values():
            try: im.close()
            except Exception: pass
        self.prepared.clear(); gc.collect()
        event.accept()

def create_splash_pixmap():
    """Create a compact branded startup screen without external dependencies."""
    pixmap = QPixmap(560, 300)
    pixmap.fill(QColor("#17232d"))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    gradient = QLinearGradient(0, 0, 560, 300)
    gradient.setColorAt(0.0, QColor("#263442"))
    gradient.setColorAt(1.0, QColor("#111b24"))
    painter.fillRect(pixmap.rect(), gradient)

    # Subtle decorative accent.
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(50, 160, 190, 35))
    painter.drawEllipse(390, -115, 310, 310)
    painter.setBrush(QColor(50, 160, 190, 20))
    painter.drawEllipse(425, -80, 240, 240)
    painter.fillRect(0, 0, 6, 300, QColor("#31a6bd"))
    painter.fillRect(6, 0, 2, 300, QColor("#d5b45b"))

    icon_path = RESOURCES_DIR / "PSrazmer.png"
    if not icon_path.exists():
        icon_path = RESOURCES_DIR / "PSrazmer.ico"
    icon = QPixmap(str(icon_path))
    if not icon.isNull():
        icon = icon.scaled(76, 76, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        painter.drawPixmap(44, 66, icon)

    painter.setPen(QColor("#f4f7f9"))
    title_font = QFont("Arial", 22, QFont.Bold)
    painter.setFont(title_font)
    painter.drawText(140, 105, "PSразмер изображений PRO")

    painter.setPen(QColor("#b9c8d1"))
    sub_font = QFont("Arial", 10)
    painter.setFont(sub_font)
    painter.drawText(142, 139, "Подготовка и обработка фотографий")

    painter.setPen(QColor("#8fa4b1"))
    painter.drawText(44, 246, "Загрузка программы…")

    painter.setPen(QPen(QColor("#3c5665"), 1))
    painter.drawLine(44, 263, 516, 263)
    painter.setPen(QPen(QColor("#36a9bf"), 3))
    painter.drawLine(44, 263, 174, 263)

    painter.setPen(QColor("#718894"))
    small_font = QFont("Arial", 8)
    painter.setFont(small_font)
    painter.drawText(44, 283, "Локальная обработка изображений")
    painter.end()
    return pixmap


if __name__ == "__main__":
    try:
        app = QApplication(sys.argv)
        app.setApplicationName(APP_NAME)
        # Arial is a close, widely available Windows UI match for iVMS-4200.
        # Qt falls back to Segoe UI if Arial is unavailable.
        ui_font = QFont("Arial", 9)
        ui_font.setStyleStrategy(QFont.PreferAntialias)
        app.setFont(ui_font)

        splash_started = time.perf_counter()
        splash = QSplashScreen(create_splash_pixmap(), Qt.WindowStaysOnTopHint)
        splash.show()
        app.processEvents()

        win = MainWindow()
        remaining_ms = max(0, 2500 - int((time.perf_counter() - splash_started) * 1000))

        def show_main_window():
            win.show()
            splash.finish(win)

        QTimer.singleShot(remaining_ms, show_main_window)
        sys.exit(app.exec())
    except Exception:
        logging.exception("Fatal application error")
        raise
