"""4.2.0 (owner, 28/10/2026): emergency buttons fire only after being held 2 seconds."""
from PySide6.QtCore import QTimer, QElapsedTimer
from PySide6.QtWidgets import QPushButton

HOLD_MS = 2000


class HoldButton(QPushButton):
    def __init__(self, text, callback, hold_ms=HOLD_MS, parent=None):
        super().__init__(text, parent)
        self.base, self.callback, self.hold_ms = text, callback, hold_ms
        self.setObjectName('danger')
        self.setToolTip('Giữ chuột ' + str(hold_ms // 1000) + ' giây để thực hiện')
        self.clock = QElapsedTimer()
        self.ticker = QTimer(self); self.ticker.setInterval(100); self.ticker.timeout.connect(self._tick)
        self.pressed.connect(self._down); self.released.connect(self._up)

    def _down(self):
        self.clock.start(); self.ticker.start(); self._tick()

    def _tick(self):
        left = self.hold_ms - self.clock.elapsed()
        if left <= 0:
            self.ticker.stop(); self.setText(self.base); self.setDown(False)
            self.callback()
            return
        self.setText('Giữ… ' + str(round(left / 1000, 1)) + 's')

    def _up(self):
        if self.ticker.isActive():
            self.ticker.stop(); self.setText(self.base)
