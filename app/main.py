
import sys, os, io, json, logging, shutil, subprocess, platform, gc, time
from pathlib import Path
from datetime import datetime
from PIL import Image, ImageOps
from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QPixmap, QImage, QIcon, QFont, QColor, QPainter, QLinearGradient, QPen, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QFileDialog, QListWidget, QSplashScreen,
    QListWidgetItem, QVBoxLayout, QHBoxLayout, QGridLayout, QTabWidget, QSpinBox,
    QDoubleSpinBox, QComboBox, QCheckBox, QLineEdit, QMessageBox, QGroupBox,
    QSplitter, QProgressBar, QPlainTextEdit, QFormLayout, QAbstractItemView, QSizePolicy
)
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage

APP_NAME = "PSразмер изображений PRO"

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
RESOURCES_DIR = ROOT / "Resources"

for folder in (
    CONFIG_DIR, LOG_DIR, CACHE_DIR, HISTORY_DIR, PRESETS_DIR,
    OUTPUT_DIR, TEMP_DIR, BACKUP_DIR, RESOURCES_DIR
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
        reset_crop_btn = QPushButton("Сбросить кадрирование")
        reset_crop_btn.clicked.connect(self.preview.reset_crop)
        rl.addWidget(reset_crop_btn)
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
            "Визовый формат США (51 × 51 мм)"
        ])
        self.preset.currentIndexChanged.connect(self.apply_preset)
        self.width_cm = QDoubleSpinBox(); self.width_cm.setRange(0.5, 30); self.width_cm.setDecimals(2); self.width_cm.setSingleStep(0.1); self.width_cm.setValue(3); self.width_cm.setSuffix(" см")
        self.height_cm = QDoubleSpinBox(); self.height_cm.setRange(0.5, 30); self.height_cm.setDecimals(2); self.height_cm.setSingleStep(0.1); self.height_cm.setValue(4); self.height_cm.setSuffix(" см")
        self.dpi = QSpinBox(); self.dpi.setRange(72, 1200); self.dpi.setValue(300); self.dpi.setSuffix(" DPI")
        self.mode = QComboBox(); self.mode.addItems(["Заполнить (обрезать)", "Вписать целиком (с полями)"])
        self.format = QComboBox(); self.format.addItems(FORMATS)
        self.quality = QSpinBox(); self.quality.setRange(50, 100); self.quality.setValue(95)
        self.name_prefix = QLineEdit("Фото")
        form.addWidget(QLabel("Быстрый шаблон"),0,0); form.addWidget(self.preset,0,1,1,3)
        form.addWidget(QLabel("Ширина"),0,4); form.addWidget(self.width_cm,0,5)
        form.addWidget(QLabel("Высота"),0,6); form.addWidget(self.height_cm,0,7)
        form.addWidget(QLabel("Разрешение"),1,0); form.addWidget(self.dpi,1,1)
        form.addWidget(QLabel("Кадрирование"),1,2); form.addWidget(self.mode,1,3,1,2)
        form.addWidget(QLabel("Формат сохранения"),1,5); form.addWidget(self.format,1,6)
        form.addWidget(QLabel("Качество JPG/WEBP"),1,7); form.addWidget(self.quality,1,8)
        form.addWidget(QLabel("Префикс имени"),2,0); form.addWidget(self.name_prefix,2,1)
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
        intro = QLabel("Передача фотографий в Magicard HUB. Фото подготавливается в точном размере 3 × 4 см при 300 DPI (настройки можно изменить на первой вкладке).")
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
        al.addWidget(QLabel("Без доступа к окну HUB нельзя безопасно определить поле фотографии и нажимать элементы интерфейса автоматически. Поэтому режим не имитирует успешную вставку: он копирует фото, открывает HUB и даёт понятные шаги. После этого в HUB выберите поле фотографии и нажмите Ctrl+V."))
        auto_btn = QPushButton("Подготовить фото и открыть HUB"); auto_btn.clicked.connect(self.guided_insert)
        al.addWidget(auto_btn)
        ml.addWidget(auto); ml.addStretch()
        tabs.addTab(magic, "Magicard HUB")

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

    def apply_preset(self, index):
        presets_cm = {
            1: (3.5, 4.5),       # common passport / ID photo size; check local authority rules
            2: (3.0, 4.0),
            3: (4.0, 6.0),
            4: (9.0, 13.0),
            5: (10.0, 15.0),
            6: (4.0, 4.0),
            7: (5.1, 5.1),       # US-style square photo
        }
        if index in presets_cm:
            w, h = presets_cm[index]
            self.width_cm.setValue(w)
            self.height_cm.setValue(h)
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
                im, w, h = make_photo(source, self.width_cm.value(), self.height_cm.value(), self.dpi.value(), self.mode.currentText(), self.preview.focus_x, self.preview.focus_y, self.preview.zoom)
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
                target = OUTPUT_DIR / f"{Path(src).stem}_3x4.jpg"
                self.prepared[src][0].save(target, "JPEG", quality=95, dpi=(self.dpi.value(), self.dpi.value()))
                self.add_history(str(target), self.prepared[src][1], self.prepared[src][2], "JPG")
                self.refresh_history()
                return str(target)
            QMessageBox.information(self, APP_NAME, "Сначала нажмите «Подготовить выбранные / все».")
        elif self.prepared:
            src, (im,w,h) = next(iter(self.prepared.items()))
            target = OUTPUT_DIR / f"{Path(src).stem}_3x4.jpg"
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
        QMessageBox.information(
            self, "Подготовка для Magicard HUB",
            "Фото сохранено локально:\n" + path +
            "\n\nВ Magicard HUB откройте нужную карточку и выберите файл через поле фотографии. "
            "Передача через буфер обмена отключена."
        )

    def closeEvent(self, event):
        self.settings["hub_path"] = self.hub_path.text().strip()
        save_json(SETTINGS_FILE, self.settings)
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
    gradient.setColorAt(0.0, QColor("#263b4b"))
    gradient.setColorAt(1.0, QColor("#111b24"))
    painter.fillRect(pixmap.rect(), gradient)

    # Subtle decorative accent.
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(50, 160, 190, 35))
    painter.drawEllipse(390, -115, 310, 310)
    painter.setBrush(QColor(50, 160, 190, 20))
    painter.drawEllipse(425, -80, 240, 240)
    painter.fillRect(0, 0, 7, 300, QColor("#31a6bd"))

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
