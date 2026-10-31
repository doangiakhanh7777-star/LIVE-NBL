"""4.3.15: thử "nói qua điện thoại" trên THIẾT BỊ ÂM THANH THẬT (Windows có VB-CABLE).

Điện thoại giả (WebSocket thật tới phone_api) gửi tiếng 440 Hz 48 kHz -> RemoteTalk phát vào "CABLE Input"
-> thu lại ở "CABLE Output" (đúng như Studio thu) -> kiểm có tiếng 440 Hz, đo độ trễ, kiểm tự ngắt khi
điện thoại mất mạng. Không có cáp ảo thì in BO QUA và thoát 0.
"""
import math
import os
import socket
import struct
import sys
import tempfile
import threading
import time
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtCore import QObject
from PySide6.QtMultimedia import QAudioSource, QMediaDevices
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
import phone_api
import ptt
from ptt_core import Settings, decode
from ws_client_test import Client

ins = QMediaDevices.audioInputs(); outs = QMediaDevices.audioOutputs()
cin = next((d for d in outs if 'cable' in d.description().lower()), None)
cout = next((d for d in ins if 'cable' in d.description().lower()), None)
if cin is None or cout is None:
    print('BO QUA: máy này không có VB-CABLE'); sys.exit(0)
tmp = Path(tempfile.mkdtemp())


class Owner(QObject):
    def __init__(self):
        super().__init__(); self.changes = []
        self.ptt = type('P', (), {})(); self.ptt.settings = Settings(tmp / 'giong_noi.json')
    def log(self, t):
        print('LOG', t, flush=True)
    def ptt_changed(self, on, who='phim'):
        self.changes.append((on, who))
    def ptt_target(self, out_id=''):
        return cin


def spin(sec):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents(); time.sleep(0.003)


owner = Owner(); rt = ptt.RemoteTalk(owner)
with socket.socket() as s:
    s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]
cfg = phone_api.Config(tmp / 'p.json'); d = cfg.load(); d['port'] = port; cfg.save(d); token = d['token']
server = phone_api.Server(object(), cfg, None, rt); server.start()

# thu ở CABLE Output như Studio
fi = ptt.native_format(cout); kind = ptt.KIND[fi.sampleFormat()]; ch = fi.channelCount(); rate_in = fi.sampleRate()
src = QAudioSource(cout, fi); io = src.start()
print('Thu tại CABLE Output:', ptt.describe(fi), '| lỗi', ptt.err_name(src.error()), '| phát vào CABLE Input:', ptt.describe(ptt.native_format(cin)), flush=True)
cap = []                    # (thời điểm, mẫu mono)


def grab():
    if io is None:
        return
    data = bytes(io.readAll())
    if data:
        x = decode(data, kind); x = list(x)
        mono = [sum(x[i:i + ch]) / ch for i in range(0, len(x) - ch + 1, ch)]
        cap.append((time.monotonic(), mono))


sent = {}


def phone(seconds, close_abruptly=False):
    c = Client(port, '/api/talk?t=' + token)
    assert c.status == 101, c.head
    c.recv(); c.text({'type': 'start', 'rate': 48000}); c.recv()
    n = 1024; ph = 0; t0 = time.monotonic(); sent['first'] = t0; k = 0
    while time.monotonic() - t0 < seconds:
        vals = [int(0.5 * 32767 * math.sin(2 * math.pi * 440 * (ph + i) / 48000)) for i in range(n)]; ph += n
        c.binary(struct.pack('<%dh' % n, *vals)); k += 1
        wait = t0 + k * n / 48000 - time.monotonic()
        if wait > 0:
            time.sleep(wait)
    sent['last'] = time.monotonic()
    if close_abruptly:
        c.close(); return
    c.text({'type': 'stop'})
    try:
        c.recv()
    except Exception:
        pass
    c.close()


results = []
spin(0.5); cap.clear()
th = threading.Thread(target=phone, args=(2.0,)); th.start()
end = time.time() + 3.5
while time.time() < end:
    app.processEvents(); grab(); time.sleep(0.003)
th.join()
# phân tích: khối 10 ms
loud = [(t, m) for t, m in cap if m and max(abs(v) for v in m) > 0.1]
first = loud[0][0] if loud else None
latency = (first - sent['first']) if first else None
samples = [v for _, m in loud for v in m]
zc = sum(1 for a, b in zip(samples, samples[1:]) if a < 0 <= b)
dur = len(samples) / float(rate_in) if samples else 0
freq = zc / dur if dur else 0
print('  tiếng thu được: %.2f s, tần số ~%.0f Hz, trễ ~%s ms, RemoteTalk nhận %d byte ghi %d byte' %
      (dur, freq, int(latency * 1000) if latency else '-', rt.received, rt.written), flush=True)
results.append(('tiếng điện thoại vào tới CABLE Output (Studio thu được)', dur > 1.0, round(dur, 2)))
results.append(('đúng tiếng 440 Hz (±40)', 400 < freq < 480, round(freq)))
results.append(('độ trễ điện thoại -> cáp dưới 400 ms (mạng nội bộ)', latency is not None and latency < 0.4, latency))
results.append(('bật/tắt "đang nói" đúng một lần', owner.changes[:2] == [(True, 'dien_thoai'), (False, 'dien_thoai')], owner.changes))
# mất mạng giữa chừng
owner.changes.clear()
th = threading.Thread(target=phone, args=(0.6, True)); th.start()
spin(1.0); mid = rt.talking; th.join(); spin(2.5)
results.append(('điện thoại mất mạng giữa lúc nói -> NBL tự ngắt', mid and not rt.talking and owner.changes[-1:] == [(False, 'dien_thoai')], (mid, rt.talking, owner.changes)))
server.stop()
for name, good, info in results:
    print(('OK   ' if good else 'FAIL ') + name + '  [' + str(info) + ']', flush=True)
good = all(r[1] for r in results)
print('KET QUA NOI QUA DIEN THOAI: %d/%d' % (sum(r[1] for r in results), len(results)), flush=True)
os._exit(0 if good else 1)
