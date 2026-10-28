from pathlib import Path

# 4.2.0 (owner, 28/10/2026): nền xanh (xanh cũ) + trắng, điểm nhấn CAM HERMÈS (#f37021).
# Bố cục kiểu thẻ (card) cho gọn, nhìn thông minh hơn.
ORANGE = '#f37021'          # cam Hermès
ORANGE_DK = '#d85f12'
ORANGE_SOFT = '#fff1e8'
BLUE = '#1f7fd0'            # xanh cũ
BLUE_DK = '#15639f'
BLUE_SOFT = '#eaf4fd'
INK = '#1f3b52'

STYLE = ("""
QWidget { background:#ffffff; color:#1f3b52; font-family:"Segoe UI"; font-size:14px; }
QMainWindow { background:#eef6fe; }
QWidget#header { background:qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #1f7fd0, stop:1 #2a93e6); border-radius:16px; }
QWidget#header QLabel { background:transparent; }
QLabel#title { color:#ffffff; font-size:22px; font-weight:800; }
QLabel#tag { color:#d8ecfb; font-size:12px; font-weight:600; }
QWidget#header QPushButton { background:rgba(255,255,255,0.20); color:#ffffff; border:1px solid rgba(255,255,255,0.55); font-weight:600; }
QWidget#header QPushButton:hover { background:rgba(255,255,255,0.33); }
QWidget#header QPushButton#danger { background:#d92d2d; border-color:#ffd4d4; }
QLabel#subtitle { color:#5b7488; }
QLabel#accountStatus { background:#eaf4fd; border:1px solid #b6dbf6; border-radius:10px; padding:8px; color:#15639f; font-weight:600; }
QPushButton,QToolButton { background:#eaf4fd; color:#15639f; border:1px solid #b6dbf6; border-radius:11px; padding:9px 10px; min-height:20px; }
QPushButton:hover,QToolButton:hover { background:#d6ebfc; border-color:#1f7fd0; }
QPushButton:pressed,QToolButton:pressed { background:#c3e1fa; }
QPushButton:disabled,QToolButton:disabled { color:#95a7b4; background:#f1f5f8; border-color:#dce6ee; }
QPushButton#primary { background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #ff8a3d, stop:1 #f37021); color:white; border-color:#d85f12; font-weight:700; }
QPushButton#primary:hover { background:#e86613; }
QPushButton#primary:pressed { background:#c9530c; }
QPushButton#danger { background:#d92d2d; color:#ffffff; border-color:#b31f1f; font-weight:700; }
QPushButton#danger:hover { background:#b31f1f; }
QLineEdit,QTextEdit,QPlainTextEdit,QListWidget,QComboBox,QSpinBox,QDoubleSpinBox,QDateTimeEdit { background:#ffffff; color:#1f3b52; border:1px solid #bcd9f2; border-radius:10px; padding:8px; selection-background-color:#ffd9c2; selection-color:#8a3a12; }
QLineEdit:focus,QTextEdit:focus,QComboBox:focus,QSpinBox:focus,QDateTimeEdit:focus { border:2px solid #f37021; }
QLineEdit:read-only,QTextEdit:read-only { background:#f6fbff; }
QListWidget::item { padding:7px; border-radius:6px; }
QListWidget::item:selected { background:#ffe3d0; color:#8a3a12; }
QListWidget::item:hover { background:#eef6fe; }
QComboBox#accountSelector { background:#eaf4fd; border:2px solid #2a93e6; font-size:16px; font-weight:700; padding:10px; color:#15639f; }
QCheckBox { spacing:8px; }
QCheckBox::indicator { width:17px; height:17px; border:1px solid #9cc6ec; border-radius:5px; background:#ffffff; }
QCheckBox::indicator:checked { background:#f37021; border-color:#d85f12; image:url($ASSETS/check.svg); }
QComboBox::drop-down { width:26px; border:0; }
QComboBox::down-arrow { width:10px; height:7px; image:url($ASSETS/down.svg); }
QSpinBox::up-button,QDoubleSpinBox::up-button,QDateTimeEdit::up-button { width:29px; background:#eaf4fd; border-left:1px solid #bcd9f2; border-top-right-radius:7px; }
QSpinBox::down-button,QDoubleSpinBox::down-button,QDateTimeEdit::down-button { width:29px; background:#eaf4fd; border-left:1px solid #bcd9f2; border-bottom-right-radius:7px; }
QSpinBox::up-arrow,QDoubleSpinBox::up-arrow,QDateTimeEdit::up-arrow { width:10px; height:7px; image:url($ASSETS/up.svg); }
QSpinBox::down-arrow,QDoubleSpinBox::down-arrow,QDateTimeEdit::down-arrow { width:10px; height:7px; image:url($ASSETS/down.svg); }
QSlider::groove:horizontal { height:6px; background:#d4e8fa; border-radius:3px; }
QSlider::handle:horizontal { width:18px; background:#f37021; margin:-6px 0; border-radius:9px; }
QGroupBox { background:#ffffff; border:1px solid #cfe6fa; border-top:4px solid #1f7fd0; border-radius:14px; margin-top:24px; padding:12px; }
QGroupBox::title { subcontrol-origin:margin; left:12px; color:#15639f; font-weight:700; padding:2px 8px; background:#eaf4fd; border-radius:8px; }
QScrollArea,QTabWidget::pane { border:0; }
QWidget#card { background:#ffffff; border:1px solid #cfe6fa; border-radius:14px; }
QToolButton#navigation { background:#1f7fd0; color:#ffffff; font-weight:700; font-size:15px; border:0; border-radius:12px; padding:8px 14px; text-align:left; }
QToolButton#navigation:hover { background:#15639f; }
QToolButton#navigation::menu-indicator { image:none; width:0; }
QMenu#navigationMenu { background:#ffffff; border:1px solid #bcd9f2; padding:6px; }
QMenu#navigationMenu::item { color:#1f3b52; background:#ffffff; font-weight:600; padding:10px 18px 10px 30px; }
QMenu#navigationMenu::item:selected { background:#f37021; color:#ffffff; }
QMenu#navigationMenu::item:checked { color:#f37021; }
QMenu#navigationMenu::item:checked:selected { color:#ffffff; }
QComboBox#navigation { background:#1f7fd0; color:#ffffff; font-weight:700; border:0; border-radius:12px; padding:6px 14px; }
QComboBox#navigation:hover { background:#15639f; }
QComboBox QAbstractItemView { background:#ffffff; color:#1f3b52; border:1px solid #bcd9f2; outline:0; selection-background-color:#ffe3d0; selection-color:#8a3a12; }
QComboBox QAbstractItemView::item { color:#1f3b52; background:#ffffff; min-height:30px; padding:4px 10px; }
QComboBox QAbstractItemView::item:selected, QComboBox QAbstractItemView::item:hover { background:#ffe3d0; color:#8a3a12; }
QComboBox#navigation QAbstractItemView, QComboBox#navigation QAbstractItemView::item { color:#1f3b52; background:#ffffff; font-weight:600; }
QComboBox#navigation QAbstractItemView::item:selected, QComboBox#navigation QAbstractItemView::item:hover { background:#f37021; color:#ffffff; }
QScrollBar:vertical { background:#eef6fe; width:9px; margin:0; }
QScrollBar::handle:vertical { background:#9cc6ec; min-height:32px; border-radius:4px; }
QScrollBar::handle:vertical:hover { background:#1f7fd0; }
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical { height:0; }
QMenu { background:#ffffff; border:1px solid #bcd9f2; padding:6px; }
QMenu::item { padding:9px 14px; }
QMenu::item:selected { background:#eaf4fd; color:#15639f; }
QToolTip { color:#1f3b52; background:#fff5ec; border:1px solid #f6b98a; padding:6px; }
QDialog { background:#eef6fe; }
""").replace('$ASSETS',(Path(__file__).resolve().parent/'assets').as_posix())
