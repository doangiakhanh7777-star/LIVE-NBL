from pathlib import Path

STYLE = """
QWidget { background:#ffffff; color:#203a50; font-family:"Segoe UI"; font-size:14px; }
QMainWindow { background:#f3faff; }
QLabel#title { color:#ef741c; font-size:23px; font-weight:700; }
QLabel#subtitle { color:#55748a; }
QLabel#accountStatus { background:#eaf7ff; border:1px solid #b8e1f7; border-radius:10px; padding:7px; color:#245a7b; }
QPushButton,QToolButton { background:#eaf6ff; color:#195c89; border:1px solid #a9d8f3; border-radius:11px; padding:9px 10px; min-height:20px; }
QPushButton:hover,QToolButton:hover { background:#d3efff; border-color:#2197e5; }
QPushButton:pressed,QToolButton:pressed { background:#bce6ff; }
QPushButton:disabled,QToolButton:disabled { color:#8095a5; background:#f1f5f8; border-color:#dce5ec; }
QPushButton#primary { background:#208fe1; color:white; border-color:#208fe1; font-weight:600; }
QPushButton#primary:hover { background:#147dcc; }
QPushButton#danger { background:#f48132; color:#ffffff; border-color:#e86c1b; font-weight:600; }
QPushButton#danger:hover { background:#e86c1b; }
QLineEdit,QTextEdit,QPlainTextEdit,QListWidget,QComboBox,QSpinBox,QDoubleSpinBox,QDateTimeEdit { background:#ffffff; color:#203a50; border:1px solid #b5d6e9; border-radius:10px; padding:8px; selection-background-color:#d7eeff; selection-color:#0c4e7b; }
QLineEdit:focus,QTextEdit:focus,QComboBox:focus,QSpinBox:focus,QDateTimeEdit:focus { border:2px solid #42a7eb; }
QLineEdit:read-only,QTextEdit:read-only { background:#f6fbff; }
QListWidget::item { padding:7px; border-radius:6px; }
QListWidget::item:selected { background:#d7efff; color:#155e8d; }
QComboBox#accountSelector { background:#e8f6ff; border:1px solid #70bee9; font-size:16px; font-weight:600; padding:10px; }
QCheckBox { spacing:8px; }
QCheckBox::indicator { width:17px; height:17px; border:1px solid #8fb9d3; border-radius:5px; background:#ffffff; }
QCheckBox::indicator:checked { background:#208fe1; border-color:#208fe1; image:url($ASSETS/check.svg); }
QComboBox::drop-down { width:26px; border:0; }
QComboBox::down-arrow { width:10px; height:7px; image:url($ASSETS/down.svg); }
QSpinBox::up-button,QDoubleSpinBox::up-button,QDateTimeEdit::up-button { width:29px; background:#e8f6ff; border-left:1px solid #b5d6e9; border-top-right-radius:7px; }
QSpinBox::down-button,QDoubleSpinBox::down-button,QDateTimeEdit::down-button { width:29px; background:#e8f6ff; border-left:1px solid #b5d6e9; border-bottom-right-radius:7px; }
QSpinBox::up-arrow,QDoubleSpinBox::up-arrow,QDateTimeEdit::up-arrow { width:10px; height:7px; image:url($ASSETS/up.svg); }
QSpinBox::down-arrow,QDoubleSpinBox::down-arrow,QDateTimeEdit::down-arrow { width:10px; height:7px; image:url($ASSETS/down.svg); }
QSlider::groove:horizontal { height:6px; background:#d8eaf5; border-radius:3px; }
QSlider::handle:horizontal { width:18px; background:#ff8b35; margin:-6px 0; border-radius:9px; }
QGroupBox { background:#f8fcff; border:1px solid #c5e4f6; border-radius:14px; margin-top:24px; padding:12px; }
QGroupBox::title { subcontrol-origin:margin; left:11px; color:#1478b8; font-weight:600; padding:0 4px; }
QScrollArea,QTabWidget::pane { border:0; }
QScrollBar:vertical { background:#edf7fd; width:9px; margin:0; }
QScrollBar::handle:vertical { background:#90ccef; min-height:32px; border-radius:4px; }
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical { height:0; }
QMenu { background:#ffffff; border:1px solid #b5d6e9; padding:6px; }
QMenu::item { padding:9px 14px; }
QMenu::item:selected { background:#e1f3ff; color:#165f91; }
QToolTip { color:#203a50; background:#fff5e9; border:1px solid #f8bf88; padding:6px; }
""".replace('$ASSETS',(Path(__file__).resolve().parent/'assets').as_posix())
