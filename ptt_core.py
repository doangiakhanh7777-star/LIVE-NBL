"""4.3.13: phần logic của "giữ phím cách để nói" không dính Qt (test được ở mọi máy)."""
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
