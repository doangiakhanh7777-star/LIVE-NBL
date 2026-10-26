"""4.1.11 (owner, 26/10/2026): "Kịch bản ghim giỏ hàng".

The owner watches a clip in the app, stops where it fits, plants a flag with the
exact product NAME and how long to keep it pinned. The script is saved per clip.
During a LIVE the app sends the script of the clip NBL VIDEO is playing to Chrome,
where the flag pauses the shuffle pin, pins that product, and then the shuffle
pins its next product.

No Qt here: storage, clip identity, validation and paste parsing only.
"""
import json
import os
import re
import time
import unicodedata
from pathlib import Path

DEFAULT_HOLD = 60
MIN_HOLD = 3
MAX_HOLD = 6 * 3600
EARLY = 20          # flags in the first seconds may pin late (LIVE / Chrome still starting)


def norm(text):
    """Same comparison as Chrome (NBL.norm): no accents, đ→d, lower case, single spaces."""
    t = unicodedata.normalize('NFD', str(text or ''))
    t = ''.join(c for c in t if unicodedata.category(c) != 'Mn').replace('đ', 'd').replace('Đ', 'd')
    return re.sub(r'\s+', ' ', t).strip().lower()


def clip_key(path):
    """A clip is known by its file name and size, so moving the file keeps its script."""
    try:
        size = os.stat(path).st_size
    except OSError:
        return None
    return Path(str(path)).name.lower() + '|' + str(size)


def fmt(seconds):
    s = max(0, int(round(float(seconds))))
    h, m, sec = s // 3600, s % 3600 // 60, s % 60
    return (str(h) + ':' + str(m).zfill(2) if h else str(m)) + ':' + str(sec).zfill(2)


def parse_time(text, plain='minutes'):
    """'5:30', '1:05:30', '90s', '2p'; a plain number is minutes (time) or seconds (hold)."""
    t = re.sub(r'\s+', '', str(text or '').lower())
    m = re.fullmatch(r'(\d+(?:[.,]\d+)?)(s|giây|giay)', t)
    if m:
        return float(m.group(1).replace(',', '.'))
    m = re.fullmatch(r'(\d+(?:[.,]\d+)?)(p|ph|phút|phut|m)', t)
    if m:
        return float(m.group(1).replace(',', '.')) * 60
    if re.fullmatch(r'\d+(?:[.,]\d+)?', t):
        v = float(t.replace(',', '.'))
        return v * 60 if plain == 'minutes' else v
    parts = t.split(':')
    if len(parts) in (2, 3) and all(re.fullmatch(r'\d+', p) for p in parts[:-1]) and re.fullmatch(r'\d+(?:[.,]\d+)?', parts[-1]):
        nums = [float(p.replace(',', '.')) for p in parts]
        if all(n < 60 for n in nums[1:]):
            total = 0.0
            for n in nums:
                total = total * 60 + n
            return total
    return None


def clean(entries, duration=None):
    """Sorted, validated flags + warnings. Raises ValueError for flags that cannot run."""
    out, warnings = [], []
    for i, e in enumerate(entries or []):
        try:
            at = float(e.get('at'))
            hold = float(e.get('hold', DEFAULT_HOLD))
        except (TypeError, ValueError, AttributeError):
            raise ValueError('Cờ thứ ' + str(i + 1) + ': thời điểm hoặc thời gian giữ không hợp lệ')
        name = str(e.get('name', '')).strip()
        if not name:
            raise ValueError('Cờ ' + fmt(at) + ': chưa có tên sản phẩm')
        if at < 0:
            raise ValueError('Cờ ' + fmt(at) + ': thời điểm phải từ 0:00')
        if not MIN_HOLD <= hold <= MAX_HOLD:
            raise ValueError('Cờ ' + fmt(at) + ': giữ ghim từ ' + str(MIN_HOLD) + ' giây tới 6 giờ')
        out.append(dict(at=round(at, 1), name=name, hold=round(hold)))
    out.sort(key=lambda x: x['at'])
    for a, b in zip(out, out[1:]):
        if a['at'] == b['at']:
            raise ValueError('Hai cờ cùng thời điểm ' + fmt(a['at']))
        if a['at'] + a['hold'] > b['at']:
            warnings.append('Cờ ' + fmt(a['at']) + ' (' + a['name'] + ') bị cờ ' + fmt(b['at']) + ' cắt ngắn còn ' + str(int(b['at'] - a['at'])) + ' giây')
    for x in out:
        if x['at'] < EARLY:
            warnings.append('Cờ ' + fmt(x['at']) + ': trong ' + str(EARLY) + ' giây đầu clip LIVE và Chrome còn đang khởi động, có thể ghim trễ')
        if duration and duration > 0:
            if x['at'] >= duration:
                raise ValueError('Cờ ' + fmt(x['at']) + ' nằm sau cuối clip (' + fmt(duration) + ')')
            if x['at'] + x['hold'] > duration:
                warnings.append('Cờ ' + fmt(x['at']) + ': giữ tới quá cuối clip, sẽ tháo lúc clip hết (' + fmt(duration) + ')')
    return out, warnings


def parse_paste(text):
    """Script pasted from Notepad/Excel: 'thời điểm | tên sản phẩm | giữ' (or tabs).
    Hold may be left out (60 s)."""
    entries = []
    for n, raw in enumerate(str(text or '').splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        parts = [p.strip() for p in re.split(r'\t|\|', line)]
        parts = [p for p in parts if p != '']
        if len(parts) < 2:
            raise ValueError('Dòng ' + str(n) + ': cần "thời điểm | tên sản phẩm | giữ bao lâu"')
        at = parse_time(parts[0], 'minutes')
        if at is None:
            raise ValueError('Dòng ' + str(n) + ': thời điểm viết kiểu 5:30 (phút:giây)')
        hold = parse_time(parts[2], 'seconds') if len(parts) >= 3 else DEFAULT_HOLD
        if hold is None:
            raise ValueError('Dòng ' + str(n) + ': thời gian giữ viết kiểu 60 (giây) hoặc 1:00')
        entries.append(dict(at=at, name=parts[1], hold=hold))
    return entries


def to_text(entries):
    return '\n'.join(fmt(e['at']) + ' | ' + e['name'] + ' | ' + str(int(e['hold'])) for e in entries)


def missing(entries, titles):
    """Flag names that no product in the cart carries (same rule as Chrome:
    exact name, or a single product whose name contains it)."""
    have = [norm(t) for t in titles or [] if str(t).strip()]
    out = []
    for e in entries:
        want = norm(e['name'])
        if want in have:
            continue
        if sum(1 for t in have if want in t) == 1:
            continue
        if e['name'] not in out:
            out.append(e['name'])
    return out


class Store:
    """kich_ban_ghim.json in the NBL data folder: {clip key: {name, path, duration, entries, updated}}."""
    def __init__(self, path):
        self.path = Path(path)

    def load(self):
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _write(self, data):
        from model import write_json
        write_json(self.path, data, backup=True)

    def get(self, clip_path):
        key = clip_key(clip_path)
        return (self.load().get(key) or {}) if key else {}

    def entries(self, clip_path):
        return list(self.get(clip_path).get('entries') or [])

    def save(self, clip_path, entries, duration=None):
        key = clip_key(clip_path)
        if not key:
            raise ValueError('Không đọc được file clip: ' + str(clip_path))
        entries, warnings = clean(entries, duration)
        data = self.load()
        data[key] = dict(name=Path(str(clip_path)).name, path=str(clip_path), duration=duration or 0, entries=entries, updated=time.time())
        self._write(data)
        return entries, warnings

    def delete(self, clip_path):
        key = clip_key(clip_path)
        data = self.load()
        if key in data:
            del data[key]
            self._write(data)

    def export(self, clip_path, target):
        item = self.get(clip_path)
        if not item:
            raise ValueError('Clip này chưa có kịch bản')
        Path(target).write_text(json.dumps(dict(nbl='kich_ban_ghim', **item), ensure_ascii=False, indent=1), encoding='utf-8')

    def import_into(self, clip_path, source, duration=None):
        data = json.loads(Path(source).read_text(encoding='utf-8'))
        if not isinstance(data, dict) or data.get('nbl') != 'kich_ban_ghim':
            raise ValueError('File này không phải kịch bản ghim của NBL')
        return self.save(clip_path, data.get('entries') or [], duration)


def sync_payload(store, video):
    """What the app sends to Chrome every 10 s: the NBL VIDEO position and the script
    of the clip that is playing (empty when that clip has none)."""
    path = str(video.get('path') or '')
    key = clip_key(path) if path else None
    item = (store.load().get(key) or {}) if key else {}
    return dict(action='clip_sync', module='all', position=int(video.get('position') or 0),
                duration=int(video.get('duration') or 0), playing=video.get('state') == 'PlayingState',
                path=path[-200:], at=float(video.get('time') or 0), clip=key or '', clipName=Path(path).name[:120],
                script=[dict(at=e['at'], name=e['name'], hold=e['hold']) for e in item.get('entries') or []])


def pick_cable(devices, used=()):
    """'Phát vào cáp ảo': a VB-CABLE style output not used by another nick.
    devices: [(description, id)]. Returns (id, description, studio input name) or None."""
    used = set(used)
    cables = [(d, i) for d, i in devices if i and re.search(r'cable.*input|vb-audio|virtual cable', d, re.I)]
    for d, i in cables:
        if i not in used:
            return i, d, re.sub(r'(?i)input', 'Output', d, count=1)
    return None
