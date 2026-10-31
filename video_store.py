"""4.3.13 (chủ máy, 31/10/2026): kho video của NBL — video gửi từ điện thoại.

Điện thoại gửi video theo từng khúc (tối đa CHUNK_MAX mỗi lần) qua Tailscale tới cổng
điều khiển 8766. Rớt mạng thì hỏi lại đã nhận bao nhiêu rồi gửi tiếp từ đó, không phải
gửi lại từ đầu. Đủ file thì đổi tên thành video thật trong thư mục kho
(%LOCALAPPDATA%\\NBL_LIVE_2\\videos) và NBL tự thêm vào playlist của nick đang chọn.

Không dính Qt: phần HTTP chạy ở luồng riêng của phone_api.
"""
import json
import os
import re
import shutil
import threading
import time
from pathlib import Path

VIDEO_EXT = ('.mp4', '.m4v', '.mov', '.webm', '.mkv', '.avi')
CHUNK_MAX = 16 << 20          # mỗi khúc tối đa 16 MB
FILE_MAX = 16 << 30           # một video tối đa 16 GB
KEEP_FREE = 1 << 30           # luôn chừa trống 1 GB ổ đĩa
STALE = 3 * 86400             # khúc dở quá 3 ngày thì dọn


class StoreError(Exception):
    def __init__(self, text, status=400, received=None):
        super().__init__(text); self.status = status; self.received = received


def safe_name(name):
    """Tên file từ điện thoại -> tên an toàn trên Windows, giữ đuôi video."""
    name = str(name or '').replace('\\', '/').split('/')[-1]
    name = re.sub(r'[\x00-\x1f<>:"|?*]', '', name).strip().strip('.')
    stem, ext = os.path.splitext(name)
    if ext.lower() not in VIDEO_EXT:
        raise StoreError('Chỉ nhận file video (' + ', '.join(VIDEO_EXT) + ').', 415)
    stem = stem.strip() or 'video'
    if stem.upper() in ('CON', 'PRN', 'AUX', 'NUL') or re.fullmatch(r'(?i)(COM|LPT)\d', stem):
        stem = '_' + stem
    return stem[:120] + ext.lower()


def human(n):
    n = float(n or 0)
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return ('%d %s' if unit == 'B' else '%.1f %s') % (n, unit)
        n /= 1024


class VideoStore:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.parts = self.folder / '.dang_tai'
        self.lock = threading.Lock()
        self.busy = set()                 # mã đang nhận dở (một khúc mỗi lúc)
        try:
            self.cleanup()
        except OSError:
            pass

    # ---------- nhận file ----------
    def _paths(self, uid):
        if not re.fullmatch(r'[A-Za-z0-9_-]{8,64}', str(uid or '')):
            raise StoreError('Mã tải lên không hợp lệ.')
        return self.parts / (uid + '.part'), self.parts / (uid + '.json')

    def status(self, uid):
        part, meta = self._paths(uid)
        return dict(received=part.stat().st_size if part.exists() else 0)

    def write(self, uid, name, size, off, stream, length):
        """Nhận một khúc. Trả {received, done, path?, name?}."""
        part, meta = self._paths(uid)
        name = safe_name(name); size = int(size); off = int(off); length = int(length)
        if size <= 0 or size > FILE_MAX:
            raise StoreError('Video phải nhỏ hơn ' + human(FILE_MAX) + '.', 413)
        if length <= 0 or length > CHUNK_MAX or off < 0 or off + length > size:
            raise StoreError('Khúc dữ liệu không hợp lệ.')
        with self.lock:
            if uid in self.busy:
                raise StoreError('Khúc trước của video này chưa nhận xong.', 409, self.status(uid)['received'])
            self.busy.add(uid)
        try:
            self.parts.mkdir(parents=True, exist_ok=True)
            have = part.stat().st_size if part.exists() else 0
            if off != have:
                raise StoreError('Lệch vị trí, gửi tiếp từ ' + str(have) + '.', 409, have)
            if off == 0:
                free = shutil.disk_usage(self.folder.parent if not self.folder.exists() else self.folder).free
                if free < size + KEEP_FREE:
                    raise StoreError('Ổ đĩa PC không đủ chỗ (còn ' + human(free) + ', cần ' + human(size + KEEP_FREE) + ').', 507)
                meta.write_text(json.dumps(dict(name=name, size=size, at=time.time()), ensure_ascii=False), encoding='utf-8')
            elif meta.exists():
                old = json.loads(meta.read_text(encoding='utf-8'))
                if int(old.get('size', -1)) != size:
                    raise StoreError('Video này khác video đang gửi dở (khác dung lượng).', 409, have)
            left = length; got = 0
            with open(part, 'ab') as f:
                while left > 0:
                    chunk = stream.read(min(1 << 18, left))
                    if not chunk:
                        break
                    f.write(chunk); left -= len(chunk); got += len(chunk)
            if got != length:                      # mạng đứt giữa khúc: bỏ phần dở của khúc này
                with open(part, 'r+b') as f:
                    f.truncate(off)
                raise StoreError('Mạng đứt giữa chừng, gửi lại khúc này.', 400, off)
            received = off + length
            if received < size:
                return dict(received=received, done=False)
            final = self.unique(name)
            self.folder.mkdir(parents=True, exist_ok=True)
            os.replace(part, final)
            meta.unlink(missing_ok=True)
            return dict(received=received, done=True, path=str(final), name=final.name)
        finally:
            with self.lock:
                self.busy.discard(uid)

    def unique(self, name):
        stem, ext = os.path.splitext(name)
        path = self.folder / name; n = 2
        while path.exists():
            path = self.folder / ('%s (%d)%s' % (stem, n, ext)); n += 1
        return path

    def cleanup(self):
        if not self.parts.exists():
            return
        now = time.time()
        for f in self.parts.iterdir():
            try:
                if now - f.stat().st_mtime > STALE:
                    f.unlink()
            except OSError:
                pass

    # ---------- kho ----------
    def owns(self, path):
        try:
            p = Path(path).resolve(); root = self.folder.resolve()
        except OSError:
            return False
        return p.parent == root and p.suffix.lower() in VIDEO_EXT

    def files(self):
        if not self.folder.exists():
            return []
        out = []
        for f in self.folder.iterdir():
            if f.is_file() and f.suffix.lower() in VIDEO_EXT:
                st = f.stat(); out.append(dict(path=str(f), name=f.name, size=st.st_size, at=st.st_mtime))
        return sorted(out, key=lambda x: -x['at'])

    def find(self, name):
        name = str(name or '')
        p = self.folder / name
        if '/' in name or '\\' in name or not self.owns(p) or not p.is_file():
            raise StoreError('Không thấy video này trong kho NBL.', 404)
        return p

    def delete(self, path):
        """Xóa file trong kho. File đang phát (Windows khóa) -> PermissionError cho bên gọi xử lý."""
        if not self.owns(path):
            raise StoreError('Chỉ xóa được file trong kho video của NBL.', 403)
        Path(path).unlink(missing_ok=True)
