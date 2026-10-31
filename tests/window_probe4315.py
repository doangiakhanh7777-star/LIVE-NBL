"""4.3.15: đo vì sao NBL VIDEO đứng hình khi kéo cửa sổ ra ngoài màn hình (Windows thật, cửa sổ thật).

Cửa sổ VideoCanvas thật (player.py) nhận khung hình đổi màu 30 lần/giây qua đúng on_frame. Ở mỗi vị trí
(trong màn hình / khuất một phần / khuất hẳn phải / khuất hẳn trái) đo: Qt có vẽ không (paintEvent/giây),
cửa sổ có "exposed" không, và chụp nội dung cửa sổ bằng PrintWindow(PW_RENDERFULLCONTENT) — giống cách
phần mềm phát LIVE chụp cửa sổ — xem màu có theo khung hình mới nhất không.
Thử cả các cách sửa (vẽ ngay bằng repaint, vẽ thẳng bằng GDI khi bị khuất).
"""
import ctypes
import os
import sys
import time
from ctypes import wintypes
from pathlib import Path

os.environ['QT_QPA_PLATFORM'] = 'windows'
BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
from PySide6.QtCore import QRect, QTimer, QPoint
from PySide6.QtGui import QColor, QImage, QGuiApplication
from PySide6.QtMultimedia import QVideoFrame
from PySide6.QtWidgets import QApplication, QMainWindow

app = QApplication(sys.argv)
import player

user32 = ctypes.windll.user32; gdi32 = ctypes.windll.gdi32
for f in (user32.GetWindowDC, user32.GetDC, gdi32.CreateCompatibleDC, gdi32.CreateCompatibleBitmap, gdi32.SelectObject):
    f.restype = ctypes.c_void_p
user32.GetWindowDC.argtypes = user32.GetDC.argtypes = [ctypes.c_void_p]
user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
gdi32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]; gdi32.CreateCompatibleBitmap.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]; gdi32.DeleteObject.argtypes = [ctypes.c_void_p]; gdi32.DeleteDC.argtypes = [ctypes.c_void_p]
gdi32.GetPixel.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]; gdi32.GetPixel.restype = ctypes.c_uint32
user32.PrintWindow.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint]


def capture_r(hwnd):
    """Màu đỏ (R) ở giữa vùng hình, chụp bằng PrintWindow(PW_RENDERFULLCONTENT)."""
    r = wintypes.RECT(); user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(r)); w, h = r.right - r.left, r.bottom - r.top
    hdc = user32.GetWindowDC(hwnd); mdc = gdi32.CreateCompatibleDC(hdc); bmp = gdi32.CreateCompatibleBitmap(hdc, w, h); old = gdi32.SelectObject(mdc, bmp)
    ok = user32.PrintWindow(hwnd, mdc, 2)
    px = gdi32.GetPixel(mdc, w // 2, h // 2)
    gdi32.SelectObject(mdc, old); gdi32.DeleteObject(bmp); gdi32.DeleteDC(mdc); user32.ReleaseDC(hwnd, hdc)
    return bool(ok), px & 0xFF


scr = QGuiApplication.primaryScreen().geometry()
print('Màn hình:', scr.width(), 'x', scr.height(), '| dpr', QGuiApplication.primaryScreen().devicePixelRatio(), flush=True)


class Probe(QMainWindow):
    def __init__(self, mode):
        super().__init__(); self.mode = mode; self.resize(360, 640); self.setWindowTitle('NBL VIDEO probe ' + mode)
        self.canvas = player.VideoCanvas(); self.setCentralWidget(self.canvas)
        self.paints = 0; orig = self.canvas.paintEvent
        def counted(ev, orig=orig):
            self.paints += 1; orig(ev)
        self.canvas.paintEvent = counted
        self.k = 0; self.timer = QTimer(self); self.timer.timeout.connect(self.tick)

    def tick(self):
        self.k += 1
        img = QImage(320, 568, QImage.Format.Format_RGB32); img.fill(QColor((self.k * 7) % 256, 80, 160))
        self.canvas.on_frame(QVideoFrame(img))
        if self.mode == 'repaint':
            self.canvas.repaint()


ORIG_HIDDEN = player._hidden


def run(mode):
    player._hidden = ORIG_HIDDEN if mode == 'ban_sua_4315' else (lambda widget: False)   # 'cu' = 4.3.11–4.3.14
    w = Probe(mode); w.move(100, 100); w.show(); w.timer.start(33)
    end = time.time() + 1.0
    while time.time() < end:
        app.processEvents(); time.sleep(0.003)
    hwnd = int(w.winId()); out = []
    for name, x in (('trong màn hình', 100), ('khuất 90% bên phải', scr.right() - 36), ('khuất hẳn bên phải', scr.right() + 300), ('khuất hẳn bên trái', -2500)):
        w.move(x, 100)
        t0 = time.time()
        while time.time() - t0 < 0.5:
            app.processEvents(); time.sleep(0.003)
        p0 = w.paints; caps = []; t0 = time.time()
        while time.time() - t0 < 1.5:
            app.processEvents(); time.sleep(0.003)
            if len(caps) < 6 and time.time() - t0 > len(caps) * 0.25:
                ok, r = capture_r(hwnd); caps.append((r, (w.k * 7) % 256, ok))
        paints = (w.paints - p0) / 1.5
        fresh = sum(1 for r, want, ok in caps if ok and min((r - want) % 256, (want - r) % 256) <= 7 * 4)
        changing = len(set(r for r, _, _ in caps)) > 2
        exposed = w.windowHandle().isExposed()
        out.append((name, paints, exposed, fresh, len(caps), changing, [c[0] for c in caps]))
        print('  [%s] %-20s vẽ %5.1f lần/s | exposed=%s | chụp khớp khung mới %d/%d | hình đổi=%s | R=%s' %
              (mode, name, paints, exposed, fresh, len(caps), changing, [c[0] for c in caps]), flush=True)
    w.timer.stop(); w.close(); app.processEvents()
    return out


res = {m: run(m) for m in ('cu', 'repaint', 'ban_sua_4315')}
print('\nTÓM TẮT (hình còn chạy khi khuất hẳn?):', flush=True)
for m, rows in res.items():
    hidden = [r for r in rows if 'hẳn' in r[0]]
    print('  %-15s %s' % (m, 'CÒN CHẠY' if all(r[5] for r in hidden) else 'ĐỨNG HÌNH'), flush=True)
os._exit(0)
