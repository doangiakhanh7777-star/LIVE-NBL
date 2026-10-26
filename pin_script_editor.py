"""4.1.11 (owner, 26/10/2026): watch a clip like on YouTube (play, pause, seek, step),
stop where a product fits, plant a flag with the product NAME and how long to keep it
pinned; the flags are saved as the clip's "kịch bản ghim giỏ hàng".

The preview is its own player (muted by default) — it never touches NBL VIDEO and its
window is not called "NBL VIDEO", so Studio never captures it."""
from pathlib import Path
from PySide6.QtCore import Qt, QUrl, QRect
from PySide6.QtGui import QKeySequence, QShortcut, QPainter, QColor, QPen
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSlider, QTableWidget,
                               QTableWidgetItem, QAbstractItemView, QHeaderView, QMessageBox, QComboBox, QSpinBox,
                               QFormLayout, QDialogButtonBox, QPlainTextEdit, QFileDialog, QStyle, QStyleOptionSlider)
import pin_scripts as P


class FlagSlider(QSlider):
    """Seek bar with the flags drawn as orange marks; a click jumps there."""
    def __init__(self):
        super().__init__(Qt.Orientation.Horizontal)
        self.flags = []; self.setRange(0, 0); self.setMinimumHeight(30)

    def set_flags(self, seconds):
        self.flags = list(seconds); self.update()

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton and self.maximum() > 0:
            value = QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), int(event.position().x()), self.width())
            self.setValue(value); self.sliderMoved.emit(value)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.maximum() <= 0:
            return
        painter = QPainter(self); painter.setPen(QPen(QColor('#ea580c'), 3))
        for s in self.flags:
            x = QStyle.sliderPositionFromValue(self.minimum(), self.maximum(), int(s * 1000), self.width())
            painter.drawLine(x, 2, x, self.height() - 2)
        painter.end()


class FlagDialog(QDialog):
    def __init__(self, parent, at, names, entry=None):
        super().__init__(parent); self.setWindowTitle('Cắm cờ ghim · ' + P.fmt(at))
        form = QFormLayout(self)
        form.addRow(QLabel('Tại giây <b>' + P.fmt(at) + '</b> của clip, NBL sẽ ghim món này rồi tháo sau thời gian giữ.'))
        self.name = QComboBox(); self.name.setEditable(True); self.name.addItems(names)
        self.name.setCurrentText(entry['name'] if entry else ''); self.name.lineEdit().setPlaceholderText('Dán đúng tên sản phẩm hoặc chọn từ giỏ')
        form.addRow('Tên sản phẩm', self.name)
        self.hold = QSpinBox(); self.hold.setRange(P.MIN_HOLD, P.MAX_HOLD); self.hold.setSuffix(' giây')
        self.hold.setValue(int(entry['hold']) if entry else P.DEFAULT_HOLD)
        form.addRow('Giữ ghim bao lâu (ít nhất 3 giây)', self.hold)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Lưu cờ'); buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('Hủy')
        buttons.accepted.connect(self.check); buttons.rejected.connect(self.reject); form.addRow(buttons)

    def check(self):
        if not self.name.currentText().strip():
            QMessageBox.warning(self, 'Thiếu tên', 'Nhập hoặc chọn tên sản phẩm.'); return
        self.accept()


class PinScriptEditor(QDialog):
    def __init__(self, parent, clip, store, titles=lambda: []):
        super().__init__(parent)
        from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
        from PySide6.QtMultimediaWidgets import QVideoWidget
        self.clip, self.store, self.titles = str(clip), store, titles
        self.entries = [dict(e) for e in store.entries(clip)]; self.dirty = False
        self.setWindowTitle('Kịch bản ghim giỏ hàng — ' + Path(self.clip).name); self.resize(980, 760)
        v = QVBoxLayout(self)
        self.video = QVideoWidget(); self.video.setMinimumHeight(300); v.addWidget(self.video, 3)
        self.player = QMediaPlayer(self); self.audio = QAudioOutput(self); self.audio.setMuted(True)
        self.player.setAudioOutput(self.audio); self.player.setVideoOutput(self.video); self.player.setSource(QUrl.fromLocalFile(self.clip))
        self.seek = FlagSlider(); v.addWidget(self.seek)
        row = QHBoxLayout(); v.addLayout(row)
        self.play = QPushButton('▶ Phát'); self.play.setObjectName('primary'); self.play.clicked.connect(self.toggle); row.addWidget(self.play)
        for text, delta in (('⏪ 5 giây', -5), ('◀ 1 giây', -1), ('1 giây ▶', 1), ('5 giây ⏩', 5)):
            b = QPushButton(text); b.clicked.connect(lambda checked=False, d=delta: self.step(d)); row.addWidget(b)
        self.clock = QLabel('0:00 / 0:00'); self.clock.setStyleSheet('font-weight:700;color:#9a3412'); row.addWidget(self.clock)
        self.sound = QPushButton('🔇 Đang tắt tiếng'); self.sound.clicked.connect(self.toggle_sound); row.addWidget(self.sound)
        flag = QPushButton('🚩 Cắm cờ tại đây'); flag.setObjectName('primary'); flag.clicked.connect(self.add_flag); v.addWidget(flag)
        self.table = QTableWidget(0, 3); self.table.setHorizontalHeaderLabels(['Thời điểm', 'Tên sản phẩm', 'Giữ (giây)'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows); self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.cellClicked.connect(self.jump); self.table.cellDoubleClicked.connect(lambda r, c: self.edit_flag())
        v.addWidget(self.table, 2)
        tools = QHBoxLayout(); v.addLayout(tools)
        for text, action in (('Sửa cờ', self.edit_flag), ('Dời cờ tới chỗ đang xem', self.move_flag), ('Xóa cờ', self.remove_flag),
                             ('Dán kịch bản', self.paste), ('Xuất', self.export), ('Nhập', self.import_file)):
            b = QPushButton(text); b.clicked.connect(action); tools.addWidget(b)
        bottom = QHBoxLayout(); v.addLayout(bottom)
        self.status = QLabel('Bấm ▶ để xem, ⏸ để dừng (phím cách cũng được). Dừng đúng chỗ rồi bấm 🚩 Cắm cờ.'); self.status.setWordWrap(True); bottom.addWidget(self.status, 1)
        save = QPushButton('💾 Lưu kịch bản'); save.setObjectName('primary'); save.clicked.connect(self.save); bottom.addWidget(save)
        close = QPushButton('Đóng'); close.clicked.connect(self.reject); bottom.addWidget(close)
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, activated=self.toggle)
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, activated=lambda: self.step(-1))
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, activated=lambda: self.step(1))
        self.player.durationChanged.connect(lambda d: (self.seek.setRange(0, int(d)), self.redraw()))
        self.player.positionChanged.connect(self.moved)
        self.player.playbackStateChanged.connect(lambda s: self.play.setText('⏸ Dừng' if s == QMediaPlayer.PlaybackState.PlayingState else '▶ Phát'))
        self.player.errorOccurred.connect(lambda e, text: self.status.setText('Không mở được clip: ' + text))
        self.seek.sliderMoved.connect(lambda value: self.player.setPosition(int(value)))
        self.QMediaPlayer = QMediaPlayer
        self.redraw()

    # ---- player -------------------------------------------------------------
    def duration(self):
        return self.player.duration() / 1000 if self.player.duration() > 0 else None

    def now(self):
        return self.player.position() / 1000

    def toggle(self):
        if self.player.playbackState() == self.QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def pause(self):
        self.player.pause()

    def step(self, seconds):
        self.player.setPosition(max(0, min(self.player.duration() or 0, self.player.position() + int(seconds * 1000))))

    def moved(self, ms):
        if not self.seek.isSliderDown():
            self.seek.blockSignals(True); self.seek.setValue(int(ms)); self.seek.blockSignals(False)
        self.clock.setText(P.fmt(ms / 1000) + ' / ' + P.fmt(self.duration() or 0))

    def toggle_sound(self):
        self.audio.setMuted(not self.audio.isMuted())
        self.sound.setText('🔇 Đang tắt tiếng' if self.audio.isMuted() else '🔊 Đang mở tiếng (bấm để tắt)')

    # ---- flags --------------------------------------------------------------
    def names(self):
        seen = []
        for name in list(self.titles() or []) + [e['name'] for e in self.entries]:
            if name and name not in seen:
                seen.append(name)
        return seen

    def redraw(self, select=None):
        self.entries.sort(key=lambda e: e['at'])
        self.table.setRowCount(len(self.entries))
        for r, e in enumerate(self.entries):
            for c, text in enumerate((P.fmt(e['at']), e['name'], str(int(e['hold'])))):
                self.table.setItem(r, c, QTableWidgetItem(text))
        self.seek.set_flags([e['at'] for e in self.entries])
        if select is not None and select in self.entries:
            self.table.selectRow(self.entries.index(select))

    def selected(self):
        rows = sorted({i.row() for i in self.table.selectedItems()})
        return self.entries[rows[0]] if rows else None

    def jump(self, row, column=0):
        if 0 <= row < len(self.entries):
            self.pause(); self.player.setPosition(int(self.entries[row]['at'] * 1000))

    def add_flag(self):
        self.pause(); at = round(self.now(), 1)
        if any(abs(e['at'] - at) < 0.05 for e in self.entries):
            QMessageBox.information(self, 'Đã có cờ', 'Chỗ này đã có cờ; bấm vào cờ đó để sửa.'); return
        d = FlagDialog(self, at, self.names())
        if d.exec():
            e = dict(at=at, name=d.name.currentText().strip(), hold=d.hold.value())
            self.entries.append(e); self.dirty = True; self.redraw(e); self.hint()

    def edit_flag(self):
        e = self.selected()
        if not e:
            self.status.setText('Chọn một cờ trong bảng trước.'); return
        d = FlagDialog(self, e['at'], self.names(), e)
        if d.exec():
            e.update(name=d.name.currentText().strip(), hold=d.hold.value()); self.dirty = True; self.redraw(e); self.hint()

    def move_flag(self):
        e = self.selected()
        if not e:
            self.status.setText('Chọn cờ cần dời, tua tới chỗ mới rồi bấm lại.'); return
        e['at'] = round(self.now(), 1); self.dirty = True; self.redraw(e); self.hint()

    def remove_flag(self):
        e = self.selected()
        if e and QMessageBox.question(self, 'Xóa cờ', 'Xóa cờ ' + P.fmt(e['at']) + ' · ' + e['name'] + '?') == QMessageBox.StandardButton.Yes:
            self.entries.remove(e); self.dirty = True; self.redraw()

    def hint(self):
        try:
            _, warnings = P.clean(self.entries, self.duration())
            self.status.setText('⚠ ' + '; '.join(warnings[:3]) if warnings else str(len(self.entries)) + ' cờ. Nhớ bấm 💾 Lưu kịch bản.')
        except ValueError as error:
            self.status.setText('⚠ ' + str(error))

    def paste(self):
        d = QDialog(self); d.setWindowTitle('Dán kịch bản'); lay = QVBoxLayout(d)
        lay.addWidget(QLabel('Mỗi dòng: thời điểm | tên sản phẩm | giữ bao lâu (giây). Ví dụ: 5:30 | Bơm lốp ô tô mini | 60\nDán từ Excel cũng được (3 cột). Các cờ dán vào được THÊM vào kịch bản đang có.'))
        box = QPlainTextEdit(); lay.addWidget(box)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel); lay.addWidget(buttons)
        buttons.accepted.connect(d.accept); buttons.rejected.connect(d.reject)
        if d.exec():
            try:
                new = P.parse_paste(box.toPlainText())
                P.clean(self.entries + new, self.duration())
            except ValueError as error:
                QMessageBox.warning(self, 'Chưa dán được', str(error)); return
            self.entries += new; self.dirty = True; self.redraw(); self.hint()

    def save(self):
        try:
            self.entries, warnings = self.store.save(self.clip, self.entries, self.duration())
        except Exception as error:
            QMessageBox.warning(self, 'Chưa lưu', str(error)); return False
        self.dirty = False; self.redraw()
        self.status.setText('Đã lưu ' + str(len(self.entries)) + ' cờ cho clip này.' + (' ⚠ ' + '; '.join(warnings[:3]) if warnings else ''))
        return True

    def export(self):
        if self.dirty and not self.save():
            return
        target, _ = QFileDialog.getSaveFileName(self, 'Xuất kịch bản', Path(self.clip).stem + '_kich_ban_ghim.json', 'Kịch bản (*.json)')
        if target:
            try:
                self.store.export(self.clip, target); self.status.setText('Đã xuất: ' + target)
            except Exception as error:
                QMessageBox.warning(self, 'Chưa xuất', str(error))

    def import_file(self):
        source, _ = QFileDialog.getOpenFileName(self, 'Nhập kịch bản', '', 'Kịch bản (*.json)')
        if source:
            try:
                self.entries, warnings = self.store.import_into(self.clip, source, self.duration())
                self.dirty = False; self.redraw(); self.status.setText('Đã nhập ' + str(len(self.entries)) + ' cờ.')
            except Exception as error:
                QMessageBox.warning(self, 'Chưa nhập', str(error))

    def leave_ok(self):
        if self.dirty:
            answer = QMessageBox.question(self, 'Chưa lưu', 'Kịch bản có thay đổi chưa lưu. Lưu trước khi đóng?',
                                          QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
            if answer == QMessageBox.StandardButton.Cancel or (answer == QMessageBox.StandardButton.Save and not self.save()):
                return False
            self.dirty = False
        self.player.stop()
        return True

    def reject(self):          # Esc / Đóng / the window X all come here
        if self.leave_ok():
            super().reject()

    def closeEvent(self, event):
        if self.leave_ok():
            event.accept(); super().reject()
        else:
            event.ignore()
