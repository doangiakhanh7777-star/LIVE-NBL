"""4.3.13 (chủ máy, 31/10/2026): giữ phím CÁCH để nói thẳng vào LIVE.

Mic của máy -> cáp âm thanh ảo mà Studio đang thu (cùng đầu ra với NBL VIDEO của nick),
thời gian thực, không thu rồi phát lại. Thả phím là ngắt.

- Giữ phím cách từ HOLD_MS trở lên mới mở mic: gõ dấu cách bình thường (chạm nhanh)
  trong Zalo, Chrome… không bao giờ lọt tiếng lên LIVE.
- Thả phím vẫn mở thêm TAIL_MS để không cụt chữ cuối.
- Mic và đường ra cáp ảo chạy sẵn khi bật chế độ này, nên nhấn là có tiếng ngay; lúc
  không nói thì tiếng mic bị bỏ đi, không ghi vào cáp.
- Đang nói: AI trả lời bình luận ngừng đọc, NBL VIDEO nhỏ tiếng, có nhãn đỏ nổi trên
  màn hình (owner.ptt_changed).

Phím đọc bằng GetAsyncKeyState (chỉ hỏi phím có đang giữ không): không chặn, không
nuốt phím của app khác, không cần quyền quản trị.
"""
import os
import sys
import time
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Qt, QEvent
from PySide6.QtMultimedia import QAudioFormat, QAudioSink, QAudioSource, QMediaDevices

from ptt_core import POLL_MS, SINK_MS, TEXT_WIDGETS, VK_SPACE, Gate, Settings, convert, peak


def space_down_windows():
    try:
        import ctypes
        return bool(ctypes.windll.user32.GetAsyncKeyState(VK_SPACE) & 0x8000)
    except Exception:
        return False


def foreground_pid():
    try:
        import ctypes
        from ctypes import wintypes
        hwnd = ctypes.windll.user32.GetForegroundWindow(); pid = wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value
    except Exception:
        return None


def pick_format(inp, out):
    """Định dạng chung cho mic và cáp: ưu tiên 48 kHz 16-bit, kênh mỗi bên tự chọn."""
    for rate in (48000, 44100):
        for kind in (QAudioFormat.SampleFormat.Int16, QAudioFormat.SampleFormat.Float):
            fi = fo = None
            for ch in (1, 2):
                f = QAudioFormat(); f.setSampleRate(rate); f.setChannelCount(ch); f.setSampleFormat(kind)
                if fi is None and inp.isFormatSupported(f):
                    fi = f
            for ch in (2, 1):
                f = QAudioFormat(); f.setSampleRate(rate); f.setChannelCount(ch); f.setSampleFormat(kind)
                if fo is None and out.isFormatSupported(f):
                    fo = f
            if fi is not None and fo is not None:
                return fi, fo
    fo = out.preferredFormat(); fi = QAudioFormat(fo)
    return fi, fo


class PushToTalk(QObject):
    """Giữ phím cách -> mic vào cáp ảo. owner cần: log(text), ptt_changed(on), ptt_target() -> (session, QAudioDevice)."""

    def __init__(self, owner, data_dir, key_reader=None):
        super().__init__(owner)
        self.owner = owner
        self.settings = Settings(Path(data_dir) / 'giong_noi.json')
        self.gate = Gate()
        self.key_reader = key_reader or (space_down_windows if sys.platform == 'win32' else None)
        self.app_space = False            # phím cách khi NBL đang được chọn (đường dự phòng ngoài Windows)
        self.source = self.sink = self.inp = self.out = None
        self.fi = self.fo = None
        self.level = 0.0; self.talking = False; self.armed = False; self.error = ''; self.anywhere = True
        self.target_name = ''; self.mic_name = ''
        self.talk_started = 0.0; self.total_talk = 0.0
        self.timer = QTimer(self); self.timer.timeout.connect(self.tick)

    # ---------- bật / tắt ----------
    def arm(self, cfg=None):
        cfg = cfg or self.settings.load()
        self.disarm(quiet=True)
        mic = self.find_input(cfg.get('mic'))
        out = self.owner.ptt_target(cfg.get('out'))
        if mic is None or mic.isNull():
            self.error = 'Máy chưa có micro.'; self.owner.log('Giọng nói: ' + self.error); return False
        if out is None or out.isNull():
            self.error = 'Không thấy đầu ra âm thanh.'; self.owner.log('Giọng nói: ' + self.error); return False
        self.fi, self.fo = pick_format(mic, out)
        self.source = QAudioSource(mic, self.fi, self)
        self.sink = QAudioSink(out, self.fo, self)
        bpf_in = max(1, self.fi.bytesPerFrame()); bpf_out = max(1, self.fo.bytesPerFrame())
        self.source.setBufferSize(int(self.fi.sampleRate() * 0.02) * bpf_in)
        self.sink.setBufferSize(int(self.fo.sampleRate() * SINK_MS / 1000) * bpf_out)
        self.out = self.sink.start()
        self.inp = self.source.start()
        if self.inp is None or self.out is None:
            self.error = 'Không mở được micro hoặc cáp ảo (thiết bị đang bị chiếm?).'
            self.owner.log('Giọng nói: ' + self.error); self.disarm(quiet=True); return False
        self.inp.readyRead.connect(self.pump)
        self.mic_name = mic.description(); self.target_name = out.description()
        self.anywhere = bool(cfg.get('anywhere', True))
        self.armed = True; self.error = ''; self.gate.reset()
        self.timer.start(POLL_MS)
        self.owner.log('Giọng nói: SẴN SÀNG — giữ phím cách để nói (mic "' + self.mic_name + '" → "' + self.target_name + '").')
        return True

    def disarm(self, quiet=False):
        self.timer.stop()
        if self.talking:
            self.set_talking(False)
        for dev in (self.source, self.sink):
            if dev is not None:
                try:
                    dev.stop(); dev.deleteLater()
                except Exception:
                    pass
        self.source = self.sink = self.inp = self.out = None
        was = self.armed; self.armed = False; self.level = 0.0; self.gate.reset()
        if was and not quiet:
            self.owner.log('Giọng nói: TẮT')

    @staticmethod
    def find_input(want):
        for d in QMediaDevices.audioInputs():
            if want and bytes(d.id()).hex() == want:
                return d
        return QMediaDevices.defaultAudioInput()

    # ---------- phím ----------
    def pressed(self):
        if self.key_reader is None:
            return self.app_space
        if not self.key_reader():
            return False
        if self.owner_active():
            return not self.typing_in_nbl()
        return self.anywhere

    def owner_active(self):
        if sys.platform != 'win32':
            return True
        return foreground_pid() == os.getpid()

    @staticmethod
    def typing_in_nbl():
        from PySide6.QtWidgets import QApplication
        w = QApplication.focusWidget()
        while w is not None:          # ô chữ bên trong ô số / ô chọn cũng tính
            if any(w.inherits(n) for n in TEXT_WIDGETS):
                return True
            w = w.parentWidget()
        return False

    def tick(self):
        if not self.armed:
            return
        on = self.gate.update(self.pressed(), time.monotonic())
        if on != self.talking:
            self.set_talking(on)
        if not self.talking:
            self.level *= 0.6

    def set_talking(self, on):
        self.talking = on
        if on:
            self.talk_started = time.monotonic()
        else:
            self.total_talk += time.monotonic() - self.talk_started
        try:
            self.owner.ptt_changed(on)
        except Exception as e:
            self.owner.log('Giọng nói: ' + str(e)[:150])

    # ---------- âm thanh ----------
    def pump(self):
        if self.inp is None:
            return
        data = bytes(self.inp.readAll())
        if not data:
            return
        f_in = self.fi.sampleFormat() == QAudioFormat.SampleFormat.Float
        self.level = max(self.level * 0.7, peak(data, f_in))
        if not self.talking or self.out is None:
            return
        f_out = self.fo.sampleFormat() == QAudioFormat.SampleFormat.Float
        data = convert(data, self.fi.channelCount(), self.fo.channelCount(), f_in, f_out)
        free = self.sink.bytesFree()
        if free <= 0:
            return
        if len(data) > free:
            frame = max(1, self.fo.bytesPerFrame())
            cut = len(data) - free; cut += (-cut) % frame
            data = data[cut:]
        self.out.write(data)

    def status(self):
        if self.error:
            return '⚠ ' + self.error
        if not self.armed:
            return 'Đang tắt. Bật lên rồi giữ phím cách để nói vào LIVE.'
        if self.talking:
            return '🔴 ĐANG NÓI VÀO LIVE — thả phím cách để ngắt'
        return '🟢 Sẵn sàng — giữ phím cách để nói (mic: ' + self.mic_name + ' → ' + self.target_name + ')'


class SpaceFilter(QObject):
    """Khi chế độ nói bật: phím cách trong NBL không bấm nút đang chọn nữa (trừ khi đang gõ chữ)."""

    def __init__(self, ptt):
        super().__init__(ptt); self.ptt = ptt

    def eventFilter(self, obj, ev):
        if ev.type() in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease) and self.ptt.armed:
            if ev.key() == Qt.Key.Key_Space and not self.ptt.typing_in_nbl():
                if not ev.isAutoRepeat():
                    self.ptt.app_space = ev.type() == QEvent.Type.KeyPress
                return True
        return False


class TalkBadge:
    """Nhãn đỏ nổi trên cùng màn hình khi đang nói (không nhận chuột, không lấy focus)."""

    def __init__(self):
        from PySide6.QtWidgets import QLabel
        self.w = QLabel('🔴  ĐANG NÓI VÀO LIVE')
        self.w.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
                              | Qt.WindowType.WindowTransparentForInput | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.w.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.w.setStyleSheet('QLabel{background:#d92d20;color:white;font-size:18px;font-weight:700;padding:10px 22px;border-radius:10px;}')
        self.w.adjustSize()

    def show(self):
        from PySide6.QtGui import QGuiApplication
        scr = QGuiApplication.primaryScreen()
        if scr is not None:
            g = scr.availableGeometry(); self.w.adjustSize()
            self.w.move(g.x() + (g.width() - self.w.width()) // 2, g.y() + 12)
        self.w.show(); self.w.raise_()

    def hide(self):
        self.w.hide()
