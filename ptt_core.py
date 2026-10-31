"""4.3.13: phần logic của "giữ phím cách để nói" không dính Qt (test được ở mọi máy).

4.3.14: mic và cáp ảo mỗi bên dùng đúng định dạng gốc của nó (tần số mẫu, số kênh, kiểu mẫu có thể khác
nhau), Pipeline tự đổi: trộn về 1 kênh -> đổi tần số (nội suy tuyến tính, nối liền giữa các khúc) -> ra số
kênh / kiểu mẫu của cáp. 4.3.13 bắt hai bên chung một tần số nên mic 44,1 kHz + cáp 48 kHz là không mở được.
"""
import array
import json
import os
from pathlib import Path

HOLD_MS = 250          # giữ ít nhất chừng này mới mở mic
TAIL_MS = 150          # thả phím rồi vẫn mở thêm chừng này
POLL_MS = 15
SINK_MS = 60           # bộ đệm phía cáp ảo; dư hơn thì bỏ phần cũ để không trễ dần
VK_SPACE = 0x20
TEXT_WIDGETS = ('QLineEdit', 'QTextEdit', 'QPlainTextEdit', 'QAbstractSpinBox', 'QSpinBox', 'QDoubleSpinBox', 'QDateTimeEdit', 'QComboBox')


class Gate:
    """Quyết định mic mở hay đóng từ trạng thái phím theo thời gian (không đụng Qt, test được)."""

    def __init__(self, hold_ms=HOLD_MS, tail_ms=TAIL_MS):
        self.hold = hold_ms / 1000.0; self.tail = tail_ms / 1000.0
        self.down_at = None; self.up_at = None; self.open = False

    def update(self, pressed, now):
        if pressed:
            if self.down_at is None:
                self.down_at = now
            self.up_at = None
            if not self.open and now - self.down_at >= self.hold:
                self.open = True
        else:
            self.down_at = None
            if self.open:
                if self.up_at is None:
                    self.up_at = now
                if now - self.up_at >= self.tail:
                    self.open = False; self.up_at = None
        return self.open

    def reset(self):
        self.down_at = self.up_at = None; self.open = False


def convert(data, src_ch, dst_ch, src_float=False, dst_float=False):
    """PCM 16-bit / float32, 1 <-> 2 kênh. Trả bytes."""
    if src_ch == dst_ch and src_float == dst_float:
        return bytes(data)
    a = array.array('f' if src_float else 'h'); a.frombytes(bytes(data)[:len(data) - len(data) % a.itemsize])
    if src_float != dst_float:
        if src_float:
            a = array.array('h', (max(-32768, min(32767, int(x * 32767))) for x in a))
        else:
            a = array.array('f', (x / 32768.0 for x in a))
    if src_ch == 1 and dst_ch == 2:
        b = array.array(a.typecode, bytes(len(a) * 2 * a.itemsize)); b[0::2] = a; b[1::2] = a; a = b
    elif src_ch == 2 and dst_ch == 1:
        a = array.array(a.typecode, a[0::2])
    return a.tobytes()


def peak(data, is_float=False):
    a = array.array('f' if is_float else 'h'); a.frombytes(bytes(data)[:len(data) - len(data) % a.itemsize])
    if not a:
        return 0.0
    m = max(abs(min(a)), abs(max(a)))
    return min(1.0, m if is_float else m / 32768.0)


KINDS = {'u8': ('B', 1), 'i16': ('h', 2), 'i32': ('i', 4), 'f32': ('f', 4)}
SCALE = {'u8': 128.0, 'i16': 32768.0, 'i32': 2147483648.0, 'f32': 1.0}

def _load_numpy():
    try:
        import numpy
        return numpy
    except Exception:
        pass
    vendor = Path(__file__).resolve().parent / 'ocr_vendor'      # bộ cài Windows để numpy ở đây
    if os.name == 'nt' and vendor.is_dir():
        import sys
        if str(vendor) not in sys.path:
            sys.path.insert(0, str(vendor))
        try:
            import numpy
            return numpy
        except Exception:
            pass
    return None                # không có numpy: chạy bằng Python thuần (chậm hơn, vẫn đúng)


_np = _load_numpy()


def decode(data, kind):
    """bytes PCM -> danh sách float [-1, 1] (xen kẽ kênh)."""
    code, size = KINDS[kind]
    data = bytes(data)[:len(data) - len(data) % size]
    if _np is not None:
        a = _np.frombuffer(data, dtype={'B': _np.uint8, 'h': _np.int16, 'i': _np.int32, 'f': _np.float32}[code]).astype(_np.float32)
        return (a - 128.0) / 128.0 if kind == 'u8' else (a if kind == 'f32' else a / SCALE[kind])
    a = array.array(code); a.frombytes(data)
    if kind == 'u8':
        return [(x - 128) / 128.0 for x in a]
    if kind == 'f32':
        return list(a)
    k = SCALE[kind]
    return [x / k for x in a]


def encode(samples, kind):
    code, _ = KINDS[kind]
    if _np is not None:
        a = _np.clip(_np.asarray(samples, dtype=_np.float32), -1.0, 1.0)
        if kind == 'f32':
            return a.astype(_np.float32).tobytes()
        if kind == 'u8':
            return _np.round(a * 127.0 + 128.0).astype(_np.uint8).tobytes()
        m = SCALE[kind] - 1
        return _np.round(a * m).astype(_np.int16 if kind == 'i16' else _np.int32).tobytes()
    if kind == 'f32':
        return array.array('f', (max(-1.0, min(1.0, x)) for x in samples)).tobytes()
    if kind == 'u8':
        return array.array('B', (int(round(max(-1.0, min(1.0, x)) * 127 + 128)) for x in samples)).tobytes()
    m = SCALE[kind] - 1
    return array.array(code, (int(round(max(-1.0, min(1.0, x)) * m)) for x in samples)).tobytes()


class Pipeline:
    """Mic (rate/kênh/kiểu bất kỳ) -> cáp ảo (rate/kênh/kiểu bất kỳ). Giữ trạng thái giữa các khúc."""

    def __init__(self, in_rate, in_ch, in_kind, out_rate, out_ch, out_kind):
        self.ir = int(in_rate); self.ic = max(1, int(in_ch)); self.ik = in_kind
        self.orr = int(out_rate); self.oc = max(1, int(out_ch)); self.ok = out_kind
        self.step = self.ir / float(self.orr)
        self.pos = 0.0; self.last = 0.0; self.level = 0.0

    def mono(self, data):
        x = decode(data, self.ik)
        n = len(x) // self.ic
        if self.ic == 1:
            return x[:n] if _np is None else x[:n]
        if _np is not None:
            return x[:n * self.ic].reshape(n, self.ic).mean(axis=1)
        return [sum(x[i * self.ic:(i + 1) * self.ic]) / self.ic for i in range(n)]

    def resample(self, m):
        if self.ir == self.orr or len(m) == 0:
            if len(m):
                self.last = float(m[-1])
            return m
        if _np is not None:
            x = _np.concatenate(([self.last], _np.asarray(m, dtype=_np.float32)))
            end = len(x) - 1
            t = _np.arange(self.pos, end, self.step)
            i = t.astype(_np.int64); f = t - i
            out = x[i] * (1 - f) + x[_np.minimum(i + 1, end)] * f
            self.pos = (t[-1] + self.step - end) if len(t) else self.pos - end
        else:
            x = [self.last] + list(m); end = len(x) - 1
            out = []; t = self.pos
            while t < end:
                i = int(t); f = t - i
                out.append(x[i] * (1 - f) + x[i + 1] * f); t += self.step
            self.pos = t - end
        self.last = float(x[-1])
        return out

    def process(self, data):
        m = self.mono(data)
        if len(m):
            pk = float(_np.max(_np.abs(m))) if _np is not None else max(abs(v) for v in m)
            self.level = min(1.0, pk)
        r = self.resample(m)
        if self.oc > 1:
            if _np is not None:
                r = _np.repeat(_np.asarray(r, dtype=_np.float32), self.oc)
            else:
                r = [v for v in r for _ in range(self.oc)]
        return encode(r, self.ok)


def is_cable(name):
    """Thiết bị âm thanh ảo (VB-CABLE, VoiceMeeter…) — không phải micro thật."""
    import re
    return bool(re.search(r'cable|vb-audio|voicemeeter|virtual|stereo mix|trộn âm thanh nổi', str(name or ''), re.I))


def choose_input(inputs, default, want=''):
    """inputs: [(tên, id)], default: (tên, id) hoặc None. Trả (id hoặc None, lời nhắc).
    Mặc định của Windows là cáp ảo (CABLE Output — hay bị đặt lúc cài Studio) thì chọn micro thật đầu tiên."""
    for name, i in inputs:
        if want and i == want:
            return i, ('Đang dùng thiết bị ảo "' + name + '" làm micro — Studio sẽ nghe tiếng video, không phải giọng mày.' if is_cable(name) else '')
    if default and default[1] and not is_cable(default[0]):
        return default[1], ''
    real = [(n, i) for n, i in inputs if not is_cable(n)]
    if real:
        return real[0][1], ('Micro mặc định của Windows đang là "' + default[0] + '" (cáp ảo), NBL dùng micro thật "' + real[0][0] + '".' if default and default[1] else '')
    if inputs:
        return None, 'Máy chỉ có micro ảo (' + ', '.join(n for n, _ in inputs) + '), chưa có micro thật. Cắm tai nghe có mic / mic USB rồi bật lại.'
    return None, ''


class Settings:
    DEFAULTS = dict(enabled=False, mic='', out='', anywhere=True, duck=True)

    def __init__(self, path):
        self.path = Path(path)

    def load(self):
        try:
            d = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            d = {}
        return {**self.DEFAULTS, **{k: d[k] for k in self.DEFAULTS if k in d}}

    def save(self, d):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps({k: d.get(k, v) for k, v in self.DEFAULTS.items()}, ensure_ascii=False), encoding='utf-8')
        os.replace(tmp, self.path)


class Jitter:
    """4.3.15: bộ đệm chống giật cho tiếng từ điện thoại (bytes PCM của đầu ra cáp).

    Gom đủ PREROLL rồi mới bắt đầu phát (đệm sẵn trong cáp để mạng chập chờn không hụt tiếng); dồn quá MAXBUF thì bỏ phần cũ, giữ lại KEEP (không trễ dần).
    """

    def __init__(self, bytes_per_sec, frame=1, preroll_ms=80, max_ms=320, keep_ms=120):
        self.bps = max(1, int(bytes_per_sec)); self.frame = max(1, int(frame))
        al = lambda ms: (int(self.bps * ms / 1000) // self.frame) * self.frame
        self.preroll, self.maxbuf, self.keep = al(preroll_ms), al(max_ms), al(keep_ms)
        self.buf = bytearray(); self.started = False; self.dropped = 0

    def push(self, data):
        self.buf += data
        if len(self.buf) > self.maxbuf:
            cut = len(self.buf) - self.keep; cut -= cut % self.frame
            del self.buf[:cut]; self.dropped += cut

    def take(self, free):
        """Lấy tối đa free byte để ghi vào cáp (bội số khung)."""
        if not self.started:
            if len(self.buf) < self.preroll:
                return b''
            self.started = True
        n = min(len(self.buf), max(0, int(free))); n -= n % self.frame
        out = bytes(self.buf[:n]); del self.buf[:n]
        return out

    def clear(self):
        self.buf = bytearray(); self.started = False
