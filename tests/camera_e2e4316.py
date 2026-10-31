"""4.3.16: thử camera ảo NBL Camera trên Windows thật (DLL đã regsvr32).

NBL gửi hình (nửa trên đỏ, nửa dưới xanh) qua vcam.VirtualCam đúng như NBL VIDEO; ffmpeg đọc camera
"NBL Camera" bằng DirectShow (cùng cách TikTok LIVE Studio/OBS đọc camera) -> so màu trên/dưới (bắt lỗi
lật ngược, sai thứ tự màu), kiểm Studio-giả có "kết nối", đo thời gian đẩy một khung.
"""
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter

app = QGuiApplication(sys.argv)
import vcam

dll = Path(os.environ.get('NBL_CAMERA_DLL') or vcam.DLL)
print('DLL:', dll, dll.is_file(), '| đã đăng ký với Windows:', vcam.registered(), flush=True)
cam = vcam.VirtualCam(dll)
print('Tạo camera:', cam.ok, cam.error, flush=True)
results = [('tạo được NBL Camera', cam.ok, cam.error)]
if not cam.ok:
    for n, g, i in results:
        print(('OK   ' if g else 'FAIL ') + n + '  [' + str(i) + ']')
    os._exit(1)

src = QImage(360, 640, QImage.Format.Format_RGB32)
p = QPainter(src); p.fillRect(0, 0, 360, 320, QColor(200, 30, 30)); p.fillRect(0, 320, 360, 320, QColor(20, 40, 220)); p.end()
t0 = time.perf_counter()
for _ in range(60):
    cam.send_image(src)
per = (time.perf_counter() - t0) / 60 * 1000
print('Đẩy một khung 360x640 -> 720x1280: %.1f ms' % per, flush=True)
results.append(('đẩy một khung dưới 25 ms (đủ 30 hình/giây)', per < 25, round(per, 1)))

stop = threading.Event(); seen_connected = []


def pump():
    while not stop.is_set():
        cam.send_image(src)
        if cam.connected():
            seen_connected.append(1)
        time.sleep(1 / 30)


threading.Thread(target=pump, daemon=True).start()
lst = subprocess.run(['ffmpeg', '-hide_banner', '-list_devices', 'true', '-f', 'dshow', '-i', 'dummy'], capture_output=True, text=True, errors='replace')
devices = lst.stderr
print(devices[-1500:], flush=True)
results.append(('Windows liệt kê camera "NBL Camera" (DirectShow)', '"NBL Camera"' in devices, ''))
raw = BASE / 'cap.raw'
cap = subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'dshow', '-i', 'video=NBL Camera', '-frames:v', '8',
                      '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-y', str(raw)], capture_output=True, text=True, errors='replace', timeout=60)
print('ffmpeg đọc camera: mã', cap.returncode, cap.stderr[-800:], flush=True)
stop.set()
data = raw.read_bytes() if raw.is_file() else b''
fsize = vcam.WIDTH * vcam.HEIGHT * 3
frames = len(data) // fsize
results.append(('ffmpeg đọc được khung hình 720x1280 từ NBL Camera', frames >= 1, frames))
if frames:
    last = data[(frames - 1) * fsize: frames * fsize]
    px = lambda x, y: tuple(last[(y * vcam.WIDTH + x) * 3:(y * vcam.WIDTH + x) * 3 + 3])
    top, bottom = px(360, 300), px(360, 1000)
    near = lambda a, b: all(abs(i - j) <= 24 for i, j in zip(a, b))
    print('Điểm ảnh trên', top, '| dưới', bottom, flush=True)
    results.append(('nửa trên ĐỎ (không lật, đúng thứ tự màu)', near(top, (200, 30, 30)), top))
    results.append(('nửa dưới XANH', near(bottom, (20, 40, 220)), bottom))
results.append(('NBL thấy có app đang dùng camera (scIsConnected)', bool(seen_connected), len(seen_connected)))
cam.close()
for n, g, i in results:
    print(('OK   ' if g else 'FAIL ') + n + '  [' + str(i) + ']', flush=True)
good = all(r[1] for r in results)
print('KET QUA CAMERA AO: %d/%d' % (sum(r[1] for r in results), len(results)), flush=True)
os._exit(0 if good else 1)
