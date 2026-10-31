"""4.3.14: thử giữ-phím-cách-để-nói trên THIẾT BỊ ÂM THANH THẬT (Windows có VB-CABLE).

Phát tiếng 440 Hz vào "CABLE Input" -> NBL mở "CABLE Output" làm micro (định dạng gốc của thiết bị,
đúng code PushToTalk.arm) -> kiểm micro gửi tiếng, nhận đúng mức tiếng, giữ phím thì ghi được vào cáp.
Không có cáp ảo thì in BO QUA và thoát 0.
"""
import math
import os
import sys
import time
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from PySide6.QtCore import QObject, QTimer
from PySide6.QtMultimedia import QAudioSink, QMediaDevices
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
import ptt
from ptt_core import encode

ins = QMediaDevices.audioInputs(); outs = QMediaDevices.audioOutputs()
print('Thiết bị ghi âm:', [d.description() for d in ins])
print('Thiết bị phát:', [d.description() for d in outs])
cin = next((d for d in outs if 'cable' in d.description().lower()), None)
cout = next((d for d in ins if 'cable' in d.description().lower()), None)
if cin is None or cout is None:
    print('BO QUA: máy này không có VB-CABLE'); sys.exit(0)


class Owner(QObject):
    def __init__(self):
        super().__init__(); self.logs = []; self.changes = []
    def log(self, t):
        self.logs.append(t); print('LOG', t, flush=True)
    def ptt_changed(self, on):
        self.changes.append(on)
    def ptt_target(self, out_id=''):
        return cin


def spin(sec):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents(); time.sleep(0.005)


# tiếng thử vào CABLE Input, định dạng gốc của cáp
tone_fmt = ptt.native_format(cin)
tone = QAudioSink(cin, tone_fmt); tone_io = tone.start(); phase = [0]
kind = ptt.KIND[tone_fmt.sampleFormat()]; rate = tone_fmt.sampleRate(); ch = tone_fmt.channelCount()
print('Cáp ảo:', ptt.describe(tone_fmt), '| micro ảo:', ptt.describe(ptt.native_format(cout)), flush=True)


def feed():
    n = rate // 50; vals = []
    for i in range(n):
        v = 0.4 * math.sin(2 * math.pi * 440 * (phase[0] + i) / rate); vals += [v] * ch
    phase[0] += n
    if tone_io is not None and tone.bytesFree() >= len(vals) * 4:
        tone_io.write(encode(vals, kind))


feeder = QTimer(); feeder.timeout.connect(feed); feeder.start(15)
owner = Owner()
p = ptt.PushToTalk(owner, Path(os.environ.get('TEMP', '/tmp')), key_reader=lambda: False)
ok = p.arm(dict(enabled=True, mic=bytes(cout.id()).hex(), out='', anywhere=True, duck=True))
results = []
results.append(('arm() mở được micro + cáp thật bằng định dạng gốc', ok and not p.error, p.error))
spin(3)
results.append(('micro gửi tiếng (byte nhận > 0)', p.got > 0, p.got))
results.append(('nhận ra tiếng thử 440 Hz (mức > 0,05)', p.level > 0.05, round(p.level, 3)))
results.append(('không báo lỗi quyền micro sau 2,5 giây', not p.error, p.error))
before = p.sink.processedUSecs() if p.sink else 0
p.talking = True; spin(1.5); p.talking = False
after = p.sink.processedUSecs() if p.sink else 0
results.append(('giữ phím: tiếng ghi vào cáp (processedUSecs tăng)', after > before, (before, after)))
p.disarm(quiet=True)
for name, good, info in results:
    print(('OK   ' if good else 'FAIL ') + name + '  [' + str(info) + ']', flush=True)
good = all(r[1] for r in results)
print('KET QUA AM THANH THAT: %d/%d' % (sum(r[1] for r in results), len(results)), flush=True)
os._exit(0 if good else 1)
