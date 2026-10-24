"""4.0.3: activity and error reports, kept apart so one kind never deletes the other.

    %LOCALAPPDATA%\\NBL_LIVE_2\\bao_cao\\hoat_dong\\   what NBL did (sent, greeted, closed a popup...)
    %LOCALAPPDATA%\\NBL_LIVE_2\\bao_cao\\loi\\         what failed, with a screenshot when there is one

Each report is one .txt (plus an optional .png with the same name). The file name
starts with the date and time, e.g. 2026-10-18_20-41-07_003.txt. Only the newest
KEEP reports of EACH kind are kept; older ones of that kind are deleted. The same
event repeating within REPEAT_WINDOW seconds updates the previous report instead
of filling the 100 slots with copies.
"""
import os
import threading
import time
from datetime import datetime
from pathlib import Path

KEEP = 100
REPEAT_WINDOW = 300
KINDS = {'hoat_dong': 'Hoạt động', 'loi': 'Lỗi'}
_lock = threading.Lock()
_last = {}   # kind -> (key, stem, first time, count)
_seq = [0]


def root():
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'NBL_LIVE_2' / 'bao_cao'


def _readme(base):
    note = base / 'DOC_TRUOC.txt'
    if not note.exists():
        note.write_text(
            'BÁO CÁO NBL LIVE\n'
            '- hoat_dong: việc NBL đã làm (gửi tin, chào khách, tự đóng thông báo, ghép cửa sổ trò chuyện...)\n'
            '- loi: việc chưa làm được, kèm ảnh Studio lúc lỗi nếu có\n'
            'Tên tệp bắt đầu bằng ngày_giờ. Mỗi loại giữ 100 báo cáo mới nhất; báo cáo cũ hơn của\n'
            'LOẠI ĐÓ tự xóa. Hai loại nằm riêng nên không bao giờ xóa lẫn nhau.\n', encoding='utf-8')


def add(kind, nick, title, detail='', image=None):
    """Write one report. Never raises: reporting must not break the automation."""
    if kind not in KINDS:
        kind = 'loi'
    try:
        with _lock:
            base = root(); folder = base / kind
            folder.mkdir(parents=True, exist_ok=True); _readme(base)
            now = time.time(); stamp = datetime.now()
            key = (nick, title, detail)
            last = _last.get(kind)
            if last and last[0] == key and now - last[2] < REPEAT_WINDOW and (folder / (last[1] + '.txt')).exists():
                count = last[3] + 1
                _last[kind] = (key, last[1], now, count, last[4])
                _write(folder / (last[1] + '.txt'), kind, nick, title, detail, last[4], stamp, count,
                       (last[1] + '.png') if (folder / (last[1] + '.png')).exists() else '')
                return str(folder / (last[1] + '.txt'))
            _seq[0] = (_seq[0] + 1) % 1000
            stem = stamp.strftime('%Y-%m-%d_%H-%M-%S') + '_%03d' % _seq[0]
            picture = ''
            if image is not None:
                try:
                    shot = image.convert('RGB')
                    if shot.width > 1400:
                        shot = shot.resize((1400, int(shot.height * 1400 / shot.width)))
                    shot.save(str(folder / (stem + '.png')))
                    picture = stem + '.png'
                except Exception:
                    picture = ''
            _last[kind] = (key, stem, now, 1, stamp)
            _write(folder / (stem + '.txt'), kind, nick, title, detail, stamp, stamp, 1, picture)
            prune(folder)
            return str(folder / (stem + '.txt'))
    except Exception:
        return ''


def _write(path, kind, nick, title, detail, first, last, count, picture):
    lines = ['Loại: ' + KINDS[kind],
             'Ngày giờ: ' + first.strftime('%d/%m/%Y %H:%M:%S'),
             'Nick: ' + (nick or '-'),
             'Việc: ' + title]
    if detail:
        lines.append('Chi tiết: ' + detail)
    if count > 1:
        lines.append('Lặp lại: %d lần · lần cuối %s' % (count, last.strftime('%d/%m/%Y %H:%M:%S')))
    if picture:
        lines.append('Ảnh: ' + picture)
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def prune(folder, keep=KEEP):
    """Delete the oldest reports in THIS folder only, keeping the newest `keep`."""
    stems = sorted({p.stem for p in Path(folder).glob('*.txt')})
    for stem in stems[:-keep] if len(stems) > keep else []:
        for ext in ('.txt', '.png'):
            try:
                (Path(folder) / (stem + ext)).unlink()
            except OSError:
                pass
