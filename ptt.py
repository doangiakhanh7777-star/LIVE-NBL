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

from ptt_core import POLL_MS, SINK_MS, TEXT_WIDGETS, VK_SPACE, Gate, Pipeline, Settings, choose_input, is_cable


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


KIND = {QAudioFormat.SampleFormat.UInt8: 'u8', QAudioFormat.SampleFormat.Int16: 'i16',
        QAudioFormat.SampleFormat.Int32: 'i32', QAudioFormat.SampleFormat.Float: 'f32'}

MIC_PRIVACY = ('Windows có thể đang chặn quyền micro: Cài đặt → Quyền riêng tư & bảo mật → Micro → bật "Truy cập micro" '
               'và "Cho phép ứng dụng máy tính truy cập micro". Hoặc micro đang bị app khác giữ riêng (tắt chế độ độc quyền '
               'trong Âm thanh → Ghi âm → Thuộc tính → Nâng cao).')


MIC_KEY = r'SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone'


def mic_privacy():
    """4.3.14 (đo trên Windows thật): quyền micro của Windows. Tắt "Cho phép ứng dụng máy tính truy cập micro"
    thì QAudioSource luôn OpenError (Qt vẫn báo Granted). Trả {'machine','user','desktop'}: 'Allow'/'Deny'/''."""
    out = dict(machine='', user='', desktop='')
    try:
        import winreg
    except ImportError:
        return out
    for name, root, sub in (('machine', winreg.HKEY_LOCAL_MACHINE, MIC_KEY), ('user', winreg.HKEY_CURRENT_USER, MIC_KEY),
                            ('desktop', winreg.HKEY_CURRENT_USER, MIC_KEY + '\\NonPackaged')):
        try:
            with winreg.OpenKey(root, sub) as k:
                out[name] = str(winreg.QueryValueEx(k, 'Value')[0])
        except OSError:
            pass
    return out


def allow_mic_for_user():
    """Bật quyền micro cho tài khoản Windows đang dùng (HKCU, không cần quyền quản trị). Chỉ gọi khi chủ máy bấm Có.
    Trả True nếu ghi được; máy khóa ở mức cả máy (HKLM = Deny) thì trả False."""
    import winreg
    if mic_privacy().get('machine') == 'Deny':
        return False
    for sub in (MIC_KEY, MIC_KEY + '\\NonPackaged'):
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, sub, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, 'Value', 0, winreg.REG_SZ, 'Allow')
    return True


def err_name(e):
    """Tên lỗi âm thanh ('NoError', 'OpenError'…). PySide6 6.12 trả QtAudio.Error, không bằng QAudio.Error
    -> phải so theo tên (4.3.14: so kiểu làm NBL tưởng micro hỏng dù Qt báo NoError)."""
    return str(getattr(e, 'name', '') or str(e).split('.')[-1])


def native_format(dev):
    """4.3.14: định dạng gốc của thiết bị (Windows chia sẻ: luôn mở được). Hỏng thì 48 kHz 16-bit."""
    f = dev.preferredFormat()
    if f.sampleRate() <= 0 or f.channelCount() <= 0 or f.sampleFormat() not in KIND:
        f = QAudioFormat(); f.setSampleRate(48000); f.setChannelCount(2); f.setSampleFormat(QAudioFormat.SampleFormat.Int16)
    return f


def describe(f):
    return '%d Hz %d kênh %s' % (f.sampleRate(), f.channelCount(), KIND.get(f.sampleFormat(), '?'))


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
        self.fi = self.fo = None; self.pipe = None; self.got = 0; self.warn = ''; self.blocked = False
        self.level = 0.0; self.talking = False; self.armed = False; self.error = ''; self.anywhere = True
        self.target_name = ''; self.mic_name = ''
        self.talk_started = 0.0; self.total_talk = 0.0
        self.timer = QTimer(self); self.timer.timeout.connect(self.tick)

    # ---------- bật / tắt ----------
    def arm(self, cfg=None):
        cfg = cfg or self.settings.load()
        self.disarm(quiet=True)
        self.error = ''; self.warn = ''
        mic, why = self.find_input(cfg.get('mic'))
        out = self.owner.ptt_target(cfg.get('out'))
        inputs = [d.description() for d in QMediaDevices.audioInputs()]
        if mic is None or mic.isNull():
            self.error = why or ('Máy chưa có micro nào (Windows không thấy thiết bị ghi âm). Cắm tai nghe có mic / mic USB rồi bật lại.')
            self.owner.log('Giọng nói: ' + self.error + ' Thiết bị ghi âm Windows thấy: ' + (', '.join(inputs) or 'không có')); return False
        if out is None or out.isNull():
            self.error = 'Không thấy đầu ra âm thanh (cáp ảo).'; self.owner.log('Giọng nói: ' + self.error); return False
        self.fi, self.fo = native_format(mic), native_format(out)
        self.pipe = Pipeline(self.fi.sampleRate(), self.fi.channelCount(), KIND[self.fi.sampleFormat()],
                             self.fo.sampleRate(), self.fo.channelCount(), KIND[self.fo.sampleFormat()])
        self.source = QAudioSource(mic, self.fi, self)
        self.sink = QAudioSink(out, self.fo, self)
        self.source.setBufferSize(int(self.fi.sampleRate() * 0.02) * max(1, self.fi.bytesPerFrame()))
        self.sink.setBufferSize(int(self.fo.sampleRate() * SINK_MS / 1000) * max(1, self.fo.bytesPerFrame()))
        self.out = self.sink.start()
        self.inp = self.source.start()
        self.mic_name = mic.description(); self.target_name = out.description()
        self.owner.log('Giọng nói: mic "' + self.mic_name + '" (' + describe(self.fi) + ') → "' + self.target_name + '" (' + describe(self.fo) + '). Thiết bị ghi âm: ' + ', '.join(inputs))
        err_in = err_name(self.source.error()) != 'NoError' if self.source is not None else True
        err_out = err_name(self.sink.error()) != 'NoError' if self.sink is not None else True
        if self.inp is None or err_in:
            code = err_name(self.source.error())
            priv = mic_privacy()
            self.owner.log('Giọng nói: micro báo ' + code + ' / ' + err_name(self.source.state()) + ('' if self.inp is not None else ' (không có luồng)') + ' · quyền micro Windows: ' + str(priv))
            self.blocked = 'Deny' in priv.values() or (code == 'OpenError' and sys.platform == 'win32' and (priv.get('user') != 'Allow' or priv.get('desktop') != 'Allow'))
            self.error = 'Không mở được micro "' + self.mic_name + '". ' + MIC_PRIVACY
            self.owner.log('Giọng nói: ' + self.error); self.disarm(quiet=True)
            if self.blocked:
                try:
                    self.owner.ptt_mic_blocked(priv)
                except Exception as e:
                    self.owner.log('Giọng nói: ' + str(e)[:150])
            return False
        if self.out is None or err_out:
            self.error = 'Không mở được đầu ra "' + self.target_name + '" (cáp ảo đang bị chiếm hoặc đã gỡ?).'
            self.owner.log('Giọng nói: ' + self.error); self.disarm(quiet=True); return False
        self.inp.readyRead.connect(self.pump)
        self.source.stateChanged.connect(self.source_state)
        self.got = 0
        self.warn = why
        self.anywhere = bool(cfg.get('anywhere', True))
        self.armed = True; self.gate.reset()
        self.timer.start(POLL_MS)
        QTimer.singleShot(2500, self.check_data)
        self.owner.log('Giọng nói: SẴN SÀNG — giữ phím cách để nói.' + (' ' + why if why else ''))
        return True

    def source_state(self, state):
        if self.source is not None and self.armed and err_name(self.source.error()) not in ('NoError', 'UnderrunError'):
            self.error = 'Micro "' + self.mic_name + '" ngừng gửi tiếng (' + err_name(self.source.error()) + '). ' + MIC_PRIVACY
            self.owner.log('Giọng nói: ' + self.error)

    def check_data(self):
        """Bật xong 2,5 giây mà micro không gửi byte nào: gần như chắc Windows chặn quyền micro."""
        if self.armed and self.got == 0 and not self.error:
            self.error = 'Micro "' + self.mic_name + '" không gửi tiếng nào. ' + MIC_PRIVACY
            self.owner.log('Giọng nói: ' + self.error)

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
        """Micro sẽ dùng + lời nhắc (ptt_core.choose_input)."""
        inputs = QMediaDevices.audioInputs()
        d = QMediaDevices.defaultAudioInput()
        hexid = lambda x: bytes(x.id()).hex()
        got, why = choose_input([(x.description(), hexid(x)) for x in inputs], None if d.isNull() else (d.description(), hexid(d)), want)
        return next((x for x in inputs if hexid(x) == got), None), why

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
        self.got += len(data)
        if not self.talking or self.out is None:
            self.level = max(self.level * 0.7, self.quick_level(data))
            return
        out = self.pipe.process(data)
        self.level = max(self.level * 0.7, self.pipe.level)
        free = self.sink.bytesFree()
        if free <= 0:
            return
        if len(out) > free:
            frame = max(1, self.fo.bytesPerFrame())
            cut = len(out) - free; cut += (-cut) % frame
            out = out[cut:]
        self.out.write(out)

    def quick_level(self, data):
        """Mức tiếng mic cho thanh thử mic (cả lúc chưa giữ phím)."""
        from ptt_core import decode
        try:
            x = decode(data[-8192:], KIND[self.fi.sampleFormat()])
            if len(x) == 0:
                return 0.0
            return min(1.0, float(abs(x).max()) if hasattr(x, 'max') else max(abs(v) for v in x))
        except Exception:
            return 0.0

    def status(self):
        if self.error:
            return '⚠ ' + self.error
        if not self.armed:
            return 'Đang tắt. Bật lên rồi giữ phím cách để nói vào LIVE.'
        if self.talking:
            return '🔴 ĐANG NÓI VÀO LIVE — thả phím cách để ngắt'
        return '🟢 Sẵn sàng — giữ phím cách để nói (mic: ' + self.mic_name + ' → ' + self.target_name + ')' + ('\nℹ ' + self.warn if self.warn else '')


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
