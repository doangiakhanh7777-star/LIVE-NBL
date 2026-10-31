"""4.3.16 (chủ máy, 31/10/2026): camera ảo "NBL Camera" cho TikTok LIVE Studio.

Studio bắt hình NBL VIDEO bằng "Chọn chương trình" (chụp cửa sổ): trên máy thật Windows chỉ cập nhật phần
cửa sổ nằm trên màn hình — kéo khuất là đứng hình, thu nhỏ là mất hình. Nay NBL VIDEO đẩy thẳng từng khung
hình vào một camera DirectShow tên "NBL Camera" (native/nbl_camera = softcam, MIT, đổi tên); trong Studio
thêm nguồn Camera → NBL Camera. Cửa sổ video ẩn / thu nhỏ / ra ngoài màn hình đều không sao.

camera/nbl_camera.dll được bộ cài đăng ký (regsvr32). Ảnh gửi: BGR 24-bit, từ trên xuống, WIDTH×HEIGHT.
"""
import ctypes
import os
import sys
from pathlib import Path

WIDTH, HEIGHT = 720, 1280            # dọc 9:16 như LIVE Studio
CLSID = '{49B46215-F6C1-4B8E-949D-ED6959D7B702}'
DLL = Path(__file__).resolve().parent / 'camera' / 'nbl_camera.dll'


def registered():
    """Bộ cài đã đăng ký NBL Camera với Windows chưa (HKCR\\CLSID\\{…}\\InprocServer32)."""
    if sys.platform != 'win32':
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, 'CLSID\\' + CLSID + '\\InprocServer32') as k:
            path = winreg.QueryValueEx(k, '')[0]
        return bool(path) and Path(path).is_file()
    except OSError:
        return False


def fit(src_w, src_h, dst_w=WIDTH, dst_h=HEIGHT):
    """Vừa khung, giữ tỉ lệ, viền đen (như cửa sổ NBL VIDEO cũ)."""
    if src_w <= 0 or src_h <= 0:
        return 0, 0, dst_w, dst_h
    s = min(dst_w / src_w, dst_h / src_h)
    w, h = max(1, round(src_w * s)), max(1, round(src_h * s))
    return (dst_w - w) // 2, (dst_h - h) // 2, w, h


class VirtualCam:
    """Một camera NBL Camera. Lỗi gì cũng không văng ra ngoài (NBL VIDEO phải chạy tiếp)."""

    def __init__(self, dll=DLL, width=WIDTH, height=HEIGHT):
        self.w, self.h = width, height; self.cam = None; self.lib = None; self.error = ''; self.sent = 0
        self.canvas = None
        try:
            self.lib = ctypes.CDLL(str(dll))
            self.lib.scCreateCamera.restype = ctypes.c_void_p
            self.lib.scCreateCamera.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_float]
            self.lib.scDeleteCamera.argtypes = [ctypes.c_void_p]
            self.lib.scSendFrame.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            self.lib.scIsConnected.argtypes = [ctypes.c_void_p]; self.lib.scIsConnected.restype = ctypes.c_bool
            self.cam = self.lib.scCreateCamera(width, height, ctypes.c_float(0.0))      # 0 = gửi ngay, nhịp theo video
            if not self.cam:
                self.error = 'Không tạo được NBL Camera (đang có cửa sổ NBL VIDEO khác giữ camera?).'
        except OSError as e:
            self.error = 'Chưa có NBL Camera (' + str(e)[:80] + '). Cài lại NBL để cài camera ảo.'

    @property
    def ok(self):
        return bool(self.cam)

    def connected(self):
        try:
            return bool(self.cam) and bool(self.lib.scIsConnected(self.cam))
        except Exception:
            return False

    def send_bgr(self, data):
        """data: bytes BGR 24-bit từ trên xuống, đúng w*h*3."""
        if not self.cam or len(data) < self.w * self.h * 3:
            return False
        self.lib.scSendFrame(self.cam, ctypes.c_char_p(data))
        self.sent += 1
        return True

    def send_image(self, image):
        """QImage bất kỳ -> vừa khung WIDTH×HEIGHT, viền đen -> camera."""
        if not self.cam or image is None or image.isNull():
            return False
        from PySide6.QtCore import QRect, Qt
        from PySide6.QtGui import QColor, QImage, QPainter
        if self.canvas is None:
            self.canvas = QImage(self.w, self.h, QImage.Format.Format_RGB32)
        self.canvas.fill(QColor(0, 0, 0))
        p = QPainter(self.canvas)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        p.drawImage(QRect(*fit(image.width(), image.height(), self.w, self.h)), image)
        p.end()
        bgr = self.canvas.convertToFormat(QImage.Format.Format_BGR888)
        if bgr.bytesPerLine() != self.w * 3:
            return False
        return self.send_bgr(bytes(bgr.constBits())[:self.w * self.h * 3])

    def close(self):
        if self.cam:
            try:
                self.lib.scDeleteCamera(self.cam)
            except Exception:
                pass
        self.cam = None
