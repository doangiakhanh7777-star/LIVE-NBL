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


def analyse(cap, t_first):
    """Nối mẫu thu được; vùng từ mẫu to đầu tiên tới mẫu to cuối cùng; tần số theo số lần qua 0; hụt tiếng = đoạn im > 3 ms."""
    xs = []; t_start = None
    for t, m in cap:
        if t_start is None and m:
            t_start = t - len(m) / float(rate_in)
        xs += m
    idx = [i for i, v in enumerate(xs) if abs(v) > 0.1]
    if not idx:
        return 0, 0, None, 0
    a, b = idx[0], idx[-1]; seg = xs[a:b + 1]
    dur = len(seg) / float(rate_in)
    zc = sum(1 for u, v in zip(seg, seg[1:]) if u < 0 <= v)
    gaps = 0; run = 0
    for v in seg:
        if abs(v) < 0.02:
            run += 1
        else:
            if run > rate_in * 0.003:
                gaps += run
            run = 0
    lat = (t_start + a / float(rate_in)) - t_first if t_first else None
    return dur, zc / dur if dur else 0, lat, gaps / float(rate_in)


results = []
# ĐỐI CHỨNG: phát thẳng 2 giây 440 Hz vào CABLE Input (không qua điện thoại) để biết cách đo có đúng không
from PySide6.QtMultimedia import QAudioSink
from ptt_core import encode
fo = ptt.native_format(cin); ko = ptt.KIND[fo.sampleFormat()]
ref = QAudioSink(cin, fo); ref.setBufferSize(int(fo.sampleRate() * 0.2) * fo.bytesPerFrame()); rio = ref.start()
pcm = encode([0.5 * math.sin(2 * math.pi * 440 * i / fo.sampleRate()) for i in range(fo.sampleRate() * 2) for _ in range(fo.channelCount())], ko)
spin(0.5); cap.clear(); pos = [0]; t_ref = time.monotonic()
end = time.time() + 3.0
while time.time() < end:
    free = ref.bytesFree()
    if free > 0 and pos[0] < len(pcm):
        n = rio.write(pcm[pos[0]:pos[0] + free]); pos[0] += max(0, int(n or 0))
    app.processEvents(); grab(); time.sleep(0.003)
rd, rf, rl, rg = analyse(cap, t_ref)
print('  ĐỐI CHỨNG phát thẳng: %.2f s, ~%.0f Hz, hụt %.0f ms' % (rd, rf, rg * 1000), flush=True)
ref.stop()
spin(0.5); cap.clear()
th = threading.Thread(target=phone, args=(2.0,)); th.start()
end = time.time() + 3.5
while time.time() < end:
    app.processEvents(); grab(); time.sleep(0.003)
th.join()
dur, freq, latency, gap = analyse(cap, sent['first'])
print('  tiếng thu được: %.2f s, tần số ~%.0f Hz, trễ ~%s ms, hụt tiếng %.0f ms, RemoteTalk nhận %d byte ghi %d byte' %
      (dur, freq, None if latency is None else int(latency * 1000), gap * 1000, rt.received, rt.written), flush=True)
results.append(('tiếng điện thoại vào tới CABLE Output (Studio thu được)', dur > 1.0, round(dur, 2)))
results.append(('đúng tiếng 440 Hz (±40)', 400 < freq < 480, round(freq)))
results.append(('độ trễ điện thoại -> cáp 0–400 ms (mạng nội bộ)', latency is not None and 0 <= latency < 0.4, latency))
results.append(('không hụt tiếng quá 60 ms trong 2 giây (không rè)', gap < 0.06, round(gap, 3)))
results.append(('bật/tắt "đang nói" đúng một lần', owner.changes[:2] == [(True, 'dien_thoai'), (False, 'dien_thoai')], owner.changes))
# mất mạng giữa chừng
owner.changes.clear()
th = threading.Thread(target=phone, args=(0.8, True)); th.start()
spin(0.4); mid = rt.talking; th.join(); spin(2.5)
results.append(('điện thoại mất mạng giữa lúc nói -> NBL tự ngắt', mid and not rt.talking and owner.changes[-1:] == [(False, 'dien_thoai')], (mid, rt.talking, owner.changes)))
server.stop()
for name, good, info in results:
    print(('OK   ' if good else 'FAIL ') + name + '  [' + str(info) + ']', flush=True)
good = all(r[1] for r in results)
print('KET QUA NOI QUA DIEN THOAI: %d/%d' % (sum(r[1] for r in results), len(results)), flush=True)
os._exit(0 if good else 1)
