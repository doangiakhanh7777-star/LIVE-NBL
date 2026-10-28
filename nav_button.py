"""4.3.0 (owner video 29/10/2026 "đi tìm ẩn số"): the page list was a QComboBox whose
popup drew every row white on white on the owner's Windows (only the row under the
mouse showed). Pages are now chosen from a QMenu, the same kind of list as
"Kết nối nick ▾" which shows correctly. Keeps the few QComboBox calls app.py uses."""
from PySide6.QtCore import Signal
from PySide6.QtGui import QActionGroup
from PySide6.QtWidgets import QMenu, QToolButton, QSizePolicy


class NavButton(QToolButton):
    currentIndexChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('navigation')
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.menu_ = QMenu(self); self.menu_.setObjectName('navigationMenu')
        self.group = QActionGroup(self); self.group.setExclusive(True)
        self.setMenu(self.menu_)
        self.items = []; self.index = -1

    def addItem(self, text):
        action = self.menu_.addAction(text); action.setCheckable(True); self.group.addAction(action)
        i = len(self.items); self.items.append(text)
        action.triggered.connect(lambda checked=False, i=i: self.setCurrentIndex(i))
        if self.index < 0:
            self.setCurrentIndex(0)

    def count(self):
        return len(self.items)

    def itemText(self, i):
        return self.items[i] if 0 <= i < len(self.items) else ''

    def findText(self, text):
        return self.items.index(text) if text in self.items else -1

    def currentIndex(self):
        return self.index

    def currentText(self):
        return self.itemText(self.index)

    def setCurrentIndex(self, i):
        if not 0 <= i < len(self.items):
            return
        self.menu_.actions()[i].setChecked(True)
        self.setText('☰  ' + self.items[i] + '   ▾')
        if i != self.index:
            self.index = i; self.currentIndexChanged.emit(i)
