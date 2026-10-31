"""One process per numbered source. No TikTok session control.

4.0: the 3-retry limit counts only stalls close together (it resets after a
minute of clean playback, so a 6-hour LIVE is not killed by three unrelated
hiccups), and playlist edits keep the current clip on Windows paths.
"""
import json
import os
import random
import sys
import time
from pathlib import Path
from PySide6.QtGui import QIcon, QColor, QImage, QPainter
from PySide6.QtCore import QTimer, QUrl, Qt, QRect
from PySide6.QtWidgets import QApplication, QMainWindow, QLabel, QWidget
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QMediaDevices, QVideoSink
from model import write_json
from video_commands import same_file


HEALTHY_SECONDS = 60


def letterbox(frame_w, frame_h, area_w, area_h):
    """Ô vẽ (x, y, rộng, cao) để hình nằm GIỮA và GIỮ ĐÚNG TỈ LỆ, viền đen hai bên.

    Kéo méo hình LIVE là hỏng cả phiên, nên phần tính này tách riêng ra để kiểm được."""
    if frame_w <= 0 or frame_h <= 0 or area_w <= 0 or area_h <= 0:
        return 0, 0, max(area_w, 0), max(area_h, 0)
    if frame_w * area_h > area_w * frame_h:      # hình bè hơn ô vẽ: chạm hai mép trái phải
        w = area_w; h = max(1, round(frame_h * area_w / frame_w))
    else:                                         # hình cao hơn: chạm hai mép trên dưới
        h = area_h; w = max(1, round(frame_w * area_h / frame_h))
    return (area_w - w) // 2, (area_h - h) // 2, w, h


def _hidden(widget):
    """4.3.15: cửa sổ bị kéo ra ngoài màn hình (Qt thôi vẽ vì coi là không hiển thị)."""
    win = widget.window(); wh = win.windowHandle()
    if wh is not None and not wh.isExposed() and win.isVisible() and not win.isMinimized():
        return True
    try:
        from PySide6.QtGui import QGuiApplication
        g = win.frameGeometry()
        return win.isVisible() and not win.isMinimized() and not any(sc.geometry().intersects(g) for sc in QGuiApplication.screens())
    except Exception:
        return False


def paint_hidden(widget, image):
    """4.3.15 (chủ máy, 31/10/2026): kéo NBL VIDEO khuất khỏi màn hình thì hình đứng, vì Windows/Qt không vẽ cửa sổ
    nằm ngoài màn hình nữa trong khi Studio vẫn chụp cửa sổ đó. Lúc đó NBL tự vẽ khung hình thẳng lên cửa sổ bằng GDI
    (SetDIBitsToDevice) để Studio vẫn chụp được hình chạy. Trả True nếu đã vẽ."""
    if sys.platform != 'win32' or image.isNull():
        return False
    try:
        import ctypes
        from ctypes import wintypes
        from PySide6.QtCore import QPoint
        win = widget.window(); hwnd = int(win.winId()); dpr = win.devicePixelRatioF() or 1.0
        pos = widget.mapTo(win, QPoint(0, 0)); w = max(1, int(round(widget.width() * dpr))); h = max(1, int(round(widget.height() * dpr)))
        frame = QImage(w, h, QImage.Format.Format_RGB32); frame.fill(QColor(0, 0, 0))
        p = QPainter(frame); p.drawImage(QRect(*letterbox(image.width(), image.height(), w, h)), image); p.end()

        class BIH(ctypes.Structure):
            _fields_ = [('biSize', wintypes.DWORD), ('biWidth', ctypes.c_long), ('biHeight', ctypes.c_long), ('biPlanes', wintypes.WORD),
                        ('biBitCount', wintypes.WORD), ('biCompression', wintypes.DWORD), ('biSizeImage', wintypes.DWORD),
                        ('biXPelsPerMeter', ctypes.c_long), ('biYPelsPerMeter', ctypes.c_long), ('biClrUsed', wintypes.DWORD), ('biClrImportant', wintypes.DWORD)]
        bih = BIH(ctypes.sizeof(BIH), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        bits = (ctypes.c_char * frame.sizeInBytes()).from_buffer_copy(frame.constBits())
        user32 = ctypes.windll.user32; gdi32 = ctypes.windll.gdi32
        user32.GetDC.restype = ctypes.c_void_p; user32.GetDC.argtypes = [ctypes.c_void_p]
        user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        gdi32.SetDIBitsToDevice.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, wintypes.DWORD, wintypes.DWORD, ctypes.c_int, ctypes.c_int,
                                            wintypes.UINT, wintypes.UINT, ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]
        hdc = user32.GetDC(hwnd)
        if not hdc:
            return False
        try:
            n = gdi32.SetDIBitsToDevice(hdc, int(pos.x() * dpr), int(pos.y() * dpr), w, h, 0, 0, 0, h, bits, ctypes.byref(bih), 0)
        finally:
            user32.ReleaseDC(hwnd, hdc)
        return bool(n)
    except Exception:
        return False


class VideoCanvas(QWidget):
    """4.3.11 (chủ máy, 31/10/2026): NBL tự vẽ hình bằng CPU thay vì nhờ card màn hình.

    Máy thứ hai của chủ máy (card Intel) vẽ được 0,5 lần/giây — hình đứng — và nhiều
    khi giết luôn cả chương trình ("mở lên nó tự tắt"). Đo trên đúng máy đó: giải mã
    vẫn chạy đủ 29,9 hình/giây, chỉ khâu vẽ là chết. Tự vẽ bằng CPU: 29,6 lần/giây.

    Cửa sổ này là thứ TikTok LIVE Studio chụp lại để phát LIVE, nên nó phải vẽ được
    trên mọi máy; chạy chắc quan trọng hơn chạy nhẹ.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setAutoFillBackground(False)
        self.frame = QImage()
        self.frame_hook = None          # 4.3.16: NBL Camera nhận từng khung
        self.wants = None               # 4.3.16: hỏi có cần khung này không (cửa sổ đang ẩn)
        self.sink = QVideoSink(self)
        self.sink.videoFrameChanged.connect(self.on_frame)

    def on_frame(self, frame):
        if not frame.isValid():
            return
        win = self.window()
        if (not win.isVisible() or win.isMinimized()) and self.wants is not None and not self.wants():
            return                     # 4.3.16: ẩn + chưa app nào dùng NBL Camera: khỏi đổi khung (đỡ CPU)
        image = frame.toImage()
        if image.isNull():
            return
        self.frame = image
        if self.frame_hook is not None:
            try:
                self.frame_hook(image)
            except Exception:
                pass
        win = self.window()
        if not win.isVisible() or win.isMinimized():
            return                     # 4.3.16: cửa sổ đang ẩn / thu nhỏ: không vẽ (đỡ CPU), camera vẫn nhận hình
        self.update()
        if _hidden(self):            # 4.3.15: bị kéo khuất -> Qt không vẽ, tự vẽ bằng GDI để Studio vẫn chụp được
            paint_hidden(self, image)

    def clear(self):
        self.frame = QImage(); self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0))
        if self.frame.isNull():
            return
        area = self.rect()
        painter.drawImage(QRect(*letterbox(self.frame.width(), self.frame.height(), area.width(), area.height())), self.frame)


class Output(QMainWindow):
    def __init__(self, folder):
        super().__init__(); self.folder = folder; self.token = ''; self.last_error = ''; self.config = {}; self.order = []; self.index = -1
        self.wanted = 'stopped'; self.generation = 0; self.end_pending = False
        self.stopped_since = None; self.recovery_count = 0; self.playing_since = None
        self.setWindowIcon(QIcon(str(Path(__file__).parent/'assets/logo_38.ico')));self.setWindowTitle('NBL VIDEO'); self.resize(405, 720)
        self.video = VideoCanvas(); self.setCentralWidget(self.video)
        self.cam = None; self.cam_want = True; self.cam_tried = 0.0
        self.video.frame_hook = self.cam_send; self.video.wants = self.cam_wants; self.cam_last = 0.0
        self.audio = QAudioOutput(self); self.audio.setMuted(True)
        self.player = QMediaPlayer(self); self.player.setAudioOutput(self.audio); self.player.setVideoOutput(self.video.sink)
        self.player.mediaStatusChanged.connect(self.media_status)
        self.player.errorOccurred.connect(self.media_error)
        self.devices = QMediaDevices(self); self.devices.audioOutputsChanged.connect(self.refresh_audio)
        self.timer = QTimer(self); self.timer.timeout.connect(self.poll); self.timer.start(250)
        self.heartbeat = QTimer(self); self.heartbeat.timeout.connect(self.maintain); self.heartbeat.start(1000)
        # 4.3.14: ghi mã tiến trình để NBL nhận ra cửa sổ này còn sống (không mở cửa sổ thứ hai)
        try: write_json(self.folder/'player.json', dict(pid=os.getpid(), started=time.time()))
        except OSError: pass
        self.poll()
    def maintain(self):
        state = self.player.playbackState()
        media = self.player.mediaStatus()
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.stopped_since = None
            if self.playing_since is None: self.playing_since = time.monotonic()
            elif self.recovery_count and time.monotonic() - self.playing_since >= HEALTHY_SECONDS:
                self.recovery_count = 0
                if self.last_error.startswith('Video dừng ngoài ý muốn'): self.last_error = ''
        elif (self.wanted == 'playing' and not self.end_pending
              and media in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia)):
            self.playing_since = None
            if self.stopped_since is None: self.stopped_since = time.monotonic()
            elif time.monotonic() - self.stopped_since >= 5:
                self.stopped_since = None
                if self.recovery_count < 3:
                    self.recovery_count += 1
                    self.player.play()
                    self.status('Video dừng ngoài ý muốn; đã thử tiếp tục ('+str(self.recovery_count)+'/3).')
                else:
                    self.wanted = 'stopped'
                    self.status('Video không tiếp tục được sau 3 lần thử. Kiểm tra file và thiết bị.')
        else: self.stopped_since = None
        self.status()
    def status(self, error=''):
        if error: self.last_error = error
        write_json(self.folder/'status.json', dict(time=time.time(), state=self.player.playbackState().name, position=self.player.position(), duration=self.player.duration(), path=self.player.source().toLocalFile(), error=self.last_error, title=self.windowTitle(), muted=self.audio.isMuted(), device=self.audio.device().description(), camera=self.cam_state(), shown=self.isVisible() and not self.isMinimized()))
    def refresh_audio(self):
        if not self.config: return
        devices = QMediaDevices.audioOutputs()
        device_id = self.config['device']
        selected = next((d for d in devices if bytes(d.id()).hex() == device_id), None) if device_id else QMediaDevices.defaultAudioOutput()
        if selected is None or selected.isNull():
            self.audio.setMuted(True)
            self.status('Thiết bị âm thanh đã mất. Video vẫn chạy; chọn lại đầu ra âm thanh.')
            return
        if self.last_error.startswith('Thiết bị âm thanh đã mất'): self.last_error = ''
        if self.audio.device() != selected: self.audio.setDevice(selected)
        self.audio.setVolume(self.config['volume']/100)
        self.audio.setMuted(self.config['mute'])
    # ---------- 4.3.16: camera ảo NBL Camera ----------
    def cam_wants(self):
        """Chưa app nào mở NBL Camera thì 1 khung/giây là đủ (Studio mở camera là có hình ngay, rồi lên đủ 30 hình/giây)."""
        if not self.cam_want:
            return False
        if self.cam is None:
            return True
        try:
            return self.cam.connected() or time.monotonic() - self.cam_last >= 1.0
        except Exception:
            return True
    def cam_send(self, image):
        if not self.cam_want:
            return
        if self.cam is not None and not self.cam_wants():
            return
        self.cam_last = time.monotonic()
        if self.cam is None:
            if time.monotonic() - self.cam_tried < 10:
                return
            self.cam_tried = time.monotonic()
            try:
                import vcam
                cam = vcam.VirtualCam()
            except Exception as e:
                self.cam_error = str(e)[:120]; return
            if not cam.ok:
                self.cam_error = cam.error; cam.close(); return
            self.cam = cam; self.cam_error = ''
        self.cam.send_image(image)
    def cam_state(self):
        if not self.cam_want:
            return dict(state='off')
        if self.cam is None:
            return dict(state='error' if getattr(self, 'cam_error', '') else 'waiting', error=getattr(self, 'cam_error', ''))
        return dict(state='connected' if self.cam.connected() else 'ready', sent=self.cam.sent)
    def set_camera(self, on):
        self.cam_want = bool(on)
        if not on and self.cam is not None:
            self.cam.close(); self.cam = None
    def apply(self, config):
        old_playlist = self.config.get('playlist', [])
        current_path = self.player.source().toLocalFile()
        self.config = dict(config)
        if old_playlist != config['playlist']:
            self.order = list(range(len(config['playlist'])))
            if config['shuffle']: random.shuffle(self.order)
            matching = next((i for i in self.order if same_file(config['playlist'][i], current_path)), None)
            self.index = self.order.index(matching) if matching is not None else -1
            # Keep the current clip running; edited playlist is used at the next boundary.
        self.setWindowTitle(f"NBL VIDEO {config['number']:02d}" + (f" — {config['account']}" if config['account'] else ''))
        self.set_camera(config.get('camera', True))
        self.refresh_audio()
        return True
    def cancel_transition(self):
        self.generation += 1
        self.end_pending = False
    def media_error(self, *args):
        self.wanted = 'stopped'; self.cancel_transition()
        self.status(self.player.errorString() or 'Không đọc được video.')
    def poll(self):
        try:
            files=sorted((self.folder/'commands').glob('*.json'))
            if not files:return
            try:command=json.loads(files[0].read_text(encoding='utf-8'))
            except (ValueError,UnicodeError):
                files[0].rename(files[0].with_suffix('.invalid'));raise
            files[0].unlink()
            if command.get('deadline',time.time()+1)<time.time():return
            if command['token'] == self.token: return
            self.token = command['token']; self.last_error = ''
            action = command['action']
            if action not in ('play','next','pause','stop','close','settings','window'):raise ValueError('Lệnh không hợp lệ')
            if action == 'window':
                # 4.3.16: "Ẩn hết khi LIVE": ẩn / hiện cửa sổ (đang phát qua NBL Camera thì Studio vẫn có hình)
                if command.get('config', {}).get('show'):
                    self.showNormal(); self.raise_(); self.activateWindow()
                else:
                    self.hide()
                self.status(); return
            if action == 'stop':
                self.wanted='stopped';self.cancel_transition();self.player.stop();self.status();return
            if action == 'close':self.close();return
            if not self.apply(command['config']): return
            if action == 'play':
                # 4.1: "phát lại từ đầu": always clip 1 from 0 s; shuffling (if on)
                # starts from the second round.
                self.cancel_transition(); self.wanted = 'playing'; self.recovery_count = 0
                self.order = list(range(len(self.config['playlist'])))
                self.index = -1; self.next()
            elif action == 'next':
                self.cancel_transition(); self.wanted = 'playing'; self.next()
            elif action == 'pause':
                self.cancel_transition()
                if self.wanted == 'playing':
                    self.wanted = 'paused'; self.player.pause()
                else:
                    self.wanted = 'playing'
                    if self.player.mediaStatus() == QMediaPlayer.MediaStatus.EndOfMedia: self.next()
                    else: self.player.play()
            elif action == 'stop':
                self.wanted = 'stopped'; self.cancel_transition(); self.player.stop()
            elif action == 'close': self.close()
            self.status()
        except (OSError, ValueError, KeyError, TypeError) as e:
            self.status('Lỗi đọc lệnh: '+str(e))
    def next(self):
        if not self.order:
            self.wanted = 'stopped'; self.player.stop(); self.status('Playlist trống.'); return
        self.index += 1
        if self.index >= len(self.order):
            # 4.1: the playlist always loops (owner, 19/10/2026); no "loop" option.
            previous = self.order[-1]
            if self.config['shuffle']:
                random.shuffle(self.order)
                if len(self.order)>1 and self.order[0] == previous: self.order[0], self.order[1] = self.order[1], self.order[0]
            self.index = 0
        path = Path(self.config['playlist'][self.order[self.index]])
        if not path.is_file(): self.wanted = 'stopped'; self.player.stop(); self.status('Không tìm thấy video: '+str(path)); return
        source = QUrl.fromLocalFile(str(path.resolve()))
        self.cancel_transition()
        if self.player.source() == source:
            self.player.setPosition(0)
        else:
            self.player.setSource(source)
        self.player.play()
    def media_status(self, state):
        if state == QMediaPlayer.MediaStatus.EndOfMedia and self.wanted == 'playing' and not self.end_pending:
            self.end_pending = True
            generation = self.generation
            QTimer.singleShot(0, lambda: self.finish_clip(generation))
    def finish_clip(self, generation):
        if generation != self.generation or self.wanted != 'playing': return
        self.end_pending = False
        self.next()
    def closeEvent(self, event):
        self.wanted = 'stopped'; self.cancel_transition(); self.player.stop(); self.status('Cửa sổ đã đóng.')
        if self.cam is not None:
            self.cam.close(); self.cam = None
        try: write_json(self.folder/'player.json', dict(pid=os.getpid(), closed=True))
        except OSError: pass
        super().closeEvent(event)

if __name__ == '__main__':
    app = QApplication(sys.argv); window = Output(Path(sys.argv[1])); window.show(); sys.exit(app.exec())
