"""4.3.14: dò vì sao QAudioSource không mở được micro trên Windows thật (chạy trên CI có VB-CABLE)."""
import os
import subprocess
import sys
import time
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt, qVersion
from PySide6.QtMultimedia import QAudio, QAudioFormat, QAudioSource, QMediaDevices
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
print('Qt', qVersion(), flush=True)


def spin(sec):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents(); time.sleep(0.005)


def reg():
    for root in ('HKLM', 'HKCU'):
        for sub in ('', '\\NonPackaged'):
            k = root + '\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\CapabilityAccessManager\\ConsentStore\\microphone' + sub
            r = subprocess.run(['reg', 'query', k, '/v', 'Value'], capture_output=True, text=True)
            print('  ', k, '->', (r.stdout.strip().splitlines() or ['(không có)'])[-1].strip(), flush=True)


def perm():
    try:
        from PySide6.QtCore import QMicrophonePermission
        st = app.checkPermission(QMicrophonePermission())
        print('  Qt checkPermission(Microphone):', st, flush=True)
        return st
    except Exception as e:
        print('  Qt permission API:', repr(e), flush=True)


mic = next((d for d in QMediaDevices.audioInputs() if 'cable' in d.description().lower()), QMediaDevices.defaultAudioInput())
print('mic:', mic.description(), '| null:', mic.isNull(), flush=True)
pf = mic.preferredFormat()
print('preferred:', pf.sampleRate(), pf.channelCount(), pf.sampleFormat(), '| min/max rate', mic.minimumSampleRate(), mic.maximumSampleRate(),
      '| ch', mic.minimumChannelCount(), mic.maximumChannelCount(), '| formats', mic.supportedSampleFormats(), flush=True)
print('Quyền micro (registry):'); reg(); perm()


def fmt(rate, ch, kind):
    f = QAudioFormat(); f.setSampleRate(rate); f.setChannelCount(ch); f.setSampleFormat(kind); return f


def attempt(name, f, mode, bufsize=None):
    src = QAudioSource(mic, f)
    if bufsize:
        src.setBufferSize(bufsize)
    states = []
    src.stateChanged.connect(lambda s: states.append((str(s).split('.')[-1], str(src.error()).split('.')[-1])))
    got = [0]
    if mode == 'push':
        io = src.start()
        e0 = str(src.error()).split('.')[-1]; s0 = str(src.state()).split('.')[-1]
        if io is not None:
            io.readyRead.connect(lambda: got.__setitem__(0, got[0] + len(bytes(io.readAll()))))
    else:
        buf = QBuffer(); buf.open(QIODevice.OpenModeFlag.ReadWrite); src.start(buf); io = buf
        e0 = str(src.error()).split('.')[-1]; s0 = str(src.state()).split('.')[-1]
    spin(1.5)
    if mode == 'pull':
        got[0] = buf.size()
    print('%-34s supported=%-5s io=%-5s ngay_sau_start: state=%s error=%s | 1,5s: state=%s error=%s bytes=%d | doi=%s' % (
        name, mic.isFormatSupported(f), io is not None, s0, e0, str(src.state()).split('.')[-1], str(src.error()).split('.')[-1], got[0], states[:4]), flush=True)
    src.stop()
    return got[0] > 0


SF = QAudioFormat.SampleFormat
cases = [('preferred push', pf, 'push', None),
         ('preferred push + buffer 20ms', pf, 'push', int(pf.sampleRate() * 0.02) * max(1, pf.bytesPerFrame())),
         ('preferred pull', pf, 'pull', None),
         ('48k 2ch Int16 push', fmt(48000, 2, SF.Int16), 'push', None),
         ('48k 1ch Int16 push', fmt(48000, 1, SF.Int16), 'push', None),
         ('44.1k 2ch Float push', fmt(44100, 2, SF.Float), 'push', None)]
print('\n--- lần 1 (quyền như mặc định) ---', flush=True)
first = [attempt(*c) for c in cases]
try:
    from PySide6.QtCore import QMicrophonePermission
    done = []
    app.requestPermission(QMicrophonePermission(), lambda p: done.append(p.status() if hasattr(p, 'status') else p))
    spin(1)
    print('requestPermission ->', done, '| check sau:', app.checkPermission(QMicrophonePermission()), flush=True)
except Exception as e:
    print('requestPermission lỗi:', repr(e), flush=True)
print('\n--- lần 2 (sau requestPermission) ---', flush=True)
second = [attempt(*c) for c in cases[:3]]
print('\n--- lần 3: mic + cáp cùng lúc (như NBL) ---', flush=True)
from PySide6.QtMultimedia import QAudioSink
from PySide6.QtCore import QObject
cin = next((d for d in QMediaDevices.audioOutputs() if 'cable input' in d.description().lower()), QMediaDevices.defaultAudioOutput())
of = cin.preferredFormat()


def combo(name, sink_first, parent=None, bufs=True, keep_tone=False):
    tone = None
    if keep_tone:
        tone = QAudioSink(cin, of); tone.start()
    src = QAudioSource(mic, pf, parent) if parent else QAudioSource(mic, pf)
    snk = QAudioSink(cin, of, parent) if parent else QAudioSink(cin, of)
    if bufs:
        src.setBufferSize(int(pf.sampleRate() * 0.02) * pf.bytesPerFrame()); snk.setBufferSize(int(of.sampleRate() * 0.06) * of.bytesPerFrame())
    if sink_first:
        o = snk.start(); i = src.start()
    else:
        i = src.start(); o = snk.start()
    got = [0]
    if i is not None:
        i.readyRead.connect(lambda: got.__setitem__(0, got[0] + len(bytes(i.readAll()))))
    spin(1.2)
    print('%-44s src: io=%s err=%s state=%s bytes=%d | sink: io=%s err=%s state=%s' % (name, i is not None, str(src.error()).split('.')[-1], str(src.state()).split('.')[-1], got[0],
          o is not None, str(snk.error()).split('.')[-1], str(snk.state()).split('.')[-1]), flush=True)
    src.stop(); snk.stop()
    if tone: tone.stop()


owner = QObject()
combo('nguồn trước, cáp sau', False)
combo('cáp trước, nguồn sau', True)
combo('cáp trước + bộ đệm nhỏ + có parent', True, owner)
combo('cáp trước, không đặt bộ đệm', True, None, False)
combo('đang phát tiếng thử + cáp trước', True, None, True, True)
combo('đang phát tiếng thử + nguồn trước', False, None, True, True)
print('\nKET QUA DO: lan1', first, 'lan2', second, flush=True)
os._exit(0)
