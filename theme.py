from pathlib import Path

# 4.1.10 (owner, 26/10/2026): "thêm nhiều màu cam hơn, app trắng quá" — warm cream
# background, orange header bar, orange buttons and frames that match the logo.
STYLE = """
QWidget { background:#fffaf4; color:#3b2414; font-family:"Segoe UI"; font-size:14px; }
QMainWindow { background:#fff3e6; }
QWidget#header { background:qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #f97316, stop:1 #fb923c); border-radius:16px; }
QWidget#header QLabel { background:transparent; }
QLabel#title { color:#ffffff; font-size:23px; font-weight:800; }
QWidget#header QPushButton { background:rgba(255,255,255,0.22); color:#ffffff; border:1px solid rgba(255,255,255,0.6); font-weight:600; }
QWidget#header QPushButton:hover { background:rgba(255,255,255,0.35); }
QWidget#header QPushButton#danger { background:#b91c1c; border-color:#fecaca; color:#ffffff; }
QLabel#subtitle { color:#8a5a3b; }
QLabel#accountStatus { background:#ffedd5; border:1px solid #fdba74; border-radius:10px; padding:7px; color:#9a3412; font-weight:600; }
QPushButton,QToolButton { background:#ffedd5; color:#9a3412; border:1px solid #fdba74; border-radius:11px; padding:9px 10px; min-height:20px; }
QPushButton:hover,QToolButton:hover { background:#fed7aa; border-color:#f97316; }
QPushButton:pressed,QToolButton:pressed { background:#fdba74; }
QPushButton:disabled,QToolButton:disabled { color:#a8927f; background:#f7efe8; border-color:#eadfd4; }
QPushButton#primary { background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #fb923c, stop:1 #f97316); color:white; border-color:#ea580c; font-weight:700; }
QPushButton#primary:hover { background:#ea580c; }
QPushButton#primary:pressed { background:#c2410c; }
QPushButton#danger { background:#dc2626; color:#ffffff; border-color:#b91c1c; font-weight:700; }
QPushButton#danger:hover { background:#b91c1c; }
QLineEdit,QTextEdit,QPlainTextEdit,QListWidget,QComboBox,QSpinBox,QDoubleSpinBox,QDateTimeEdit { background:#ffffff; color:#3b2414; border:1px solid #fdba74; border-radius:10px; padding:8px; selection-background-color:#fed7aa; selection-color:#7c2d12; }
QLineEdit:focus,QTextEdit:focus,QComboBox:focus,QSpinBox:focus,QDateTimeEdit:focus { border:2px solid #f97316; }
QLineEdit:read-only,QTextEdit:read-only { background:#fff7ed; }
QListWidget::item { padding:7px; border-radius:6px; }
QListWidget::item:selected { background:#fed7aa; color:#7c2d12; }
QListWidget::item:hover { background:#fff1e3; }
QComboBox#accountSelector { background:#fff1e3; border:2px solid #fb923c; font-size:16px; font-weight:700; padding:10px; color:#9a3412; }
QCheckBox { spacing:8px; }
QCheckBox::indicator { width:17px; height:17px; border:1px solid #fb923c; border-radius:5px; background:#ffffff; }
QCheckBox::indicator:checked { background:#f97316; border-color:#ea580c; image:url($ASSETS/check.svg); }
QComboBox::drop-down { width:26px; border:0; }
QComboBox::down-arrow { width:10px; height:7px; image:url($ASSETS/down.svg); }
QSpinBox::up-button,QDoubleSpinBox::up-button,QDateTimeEdit::up-button { width:29px; background:#fff1e3; border-left:1px solid #fdba74; border-top-right-radius:7px; }
QSpinBox::down-button,QDoubleSpinBox::down-button,QDateTimeEdit::down-button { width:29px; background:#fff1e3; border-left:1px solid #fdba74; border-bottom-right-radius:7px; }
QSpinBox::up-arrow,QDoubleSpinBox::up-arrow,QDateTimeEdit::up-arrow { width:10px; height:7px; image:url($ASSETS/up.svg); }
QSpinBox::down-arrow,QDoubleSpinBox::down-arrow,QDateTimeEdit::down-arrow { width:10px; height:7px; image:url($ASSETS/down.svg); }
QSlider::groove:horizontal { height:6px; background:#fde3cc; border-radius:3px; }
QSlider::handle:horizontal { width:18px; background:#f97316; margin:-6px 0; border-radius:9px; }
QGroupBox { background:#ffffff; border:1px solid #fed7aa; border-top:4px solid #fb923c; border-radius:14px; margin-top:24px; padding:12px; }
QGroupBox::title { subcontrol-origin:margin; left:11px; color:#ea580c; font-weight:700; padding:0 4px; }
QScrollArea,QTabWidget::pane { border:0; }
QScrollBar:vertical { background:#fff1e3; width:9px; margin:0; }
QScrollBar::handle:vertical { background:#fdba74; min-height:32px; border-radius:4px; }
QScrollBar::handle:vertical:hover { background:#fb923c; }
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical { height:0; }
QMenu { background:#ffffff; border:1px solid #fdba74; padding:6px; }
QMenu::item { padding:9px 14px; }
QMenu::item:selected { background:#ffedd5; color:#9a3412; }
QToolTip { color:#3b2414; background:#fff5e9; border:1px solid #f8bf88; padding:6px; }
QDialog { background:#fffaf4; }
""".replace('$ASSETS',(Path(__file__).resolve().parent/'assets').as_posix())
