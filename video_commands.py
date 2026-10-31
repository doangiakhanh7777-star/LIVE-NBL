"""Deliver video commands only to a live worker or a freshly started one."""
import os
import time
import uuid
from pathlib import Path
from model import write_json


LAST = {}          # 4.3.14: lần gửi gần nhất: {'folder': …, 'redirected': bool, 'opened': bool} (để app ghi nhật ký)


def dispatch_video_command(folder, action, config, process, launch):
    if action not in ('play', 'pause', 'next', 'stop', 'close', 'settings', 'window'):
        raise ValueError('Lệnh video không hợp lệ.')
    alive = process is not None and process.poll() is None
    folder = Path(folder)
    LAST.clear(); LAST.update(folder=str(folder), redirected=False, opened=False)
    # 4.1.2: an NBL VIDEO window this app run did not start (opened before NBL was
    # restarted) is still alive when it wrote its status in the last 3 seconds.
    # Send it the command; never open a second window (Studio captures the first).
    # 4.3.14 (chủ máy, 31/10/2026): tới lịch NBL vẫn mở cửa sổ MỚI dù cửa sổ cũ đang chạy -> Studio không nhận
    # hình. Nay cửa sổ còn sống = trạng thái mới HOẶC tiến trình ghi trong player.json còn chạy (không đếm
    # giây nữa), đọc trượt thì đọc lại; thư mục nick này không có thì dùng cửa sổ NBL VIDEO đang chạy của
    # thư mục khác (bản này chạy 1 nick). Chỉ mở cửa sổ mới khi thật sự không còn cửa sổ nào.
    running = alive or window_alive(folder)
    if not running and not alive:
        other = running_elsewhere(folder)
        if other is not None:
            folder = other; running = True; LAST.update(folder=str(folder), redirected=True)
    if not running and action != 'play':
        return process
    if running and not alive:
        token = str(time.time_ns()) + '-' + uuid.uuid4().hex
        write_json(folder / 'commands' / (token + '.json'),
                   dict(token=token, action=action, config=config, deadline=time.time()+15))
        return process
    if not alive:
        # Commands from an earlier worker must not close or pause a new worker.
        for pending in (folder / 'commands').glob('*.json'):
            pending.unlink(missing_ok=True)
        (folder / 'status.json').unlink(missing_ok=True)
    token = str(time.time_ns()) + '-' + uuid.uuid4().hex
    write_json(folder / 'commands' / (token + '.json'),
               dict(token=token, action=action, config=config, deadline=time.time()+15))
    if not alive:
        LAST['opened'] = True
    return process if alive else launch(folder)


def _fresh(folder, seconds=3):
    import json
    for attempt in range(3):            # Windows: đang bị ghi đè thì đọc trượt -> đọc lại
        try:
            state = json.loads((Path(folder) / 'status.json').read_text(encoding='utf-8'))
            return time.time() - float(state.get('time', 0)) < seconds
        except FileNotFoundError:
            return False
        except (OSError, ValueError, TypeError, AttributeError):
            time.sleep(0.15)
    return False


def pid_alive(pid):
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if os.name == 'nt':
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, pid)          # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        try:
            code = ctypes.c_ulong()
            return bool(k.GetExitCodeProcess(h, ctypes.byref(code))) and code.value == 259    # STILL_ACTIVE
        finally:
            k.CloseHandle(h)
    try:
        os.kill(pid, 0); return True
    except OSError:
        return False


def window_alive(folder):
    """Cửa sổ NBL VIDEO của thư mục này còn chạy: vừa ghi trạng thái, hoặc tiến trình của nó còn sống."""
    folder = Path(folder)
    if _fresh(folder, 10):
        return True
    try:
        import json
        info = json.loads((folder / 'player.json').read_text(encoding='utf-8'))
        return pid_alive(info.get('pid')) and info.get('closed') is not True
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def running_elsewhere(folder):
    """Thư mục khác trong DATA/runtime có cửa sổ NBL VIDEO đang chạy (mới nhất trước), hoặc None."""
    folder = Path(folder)
    if folder.parent.name != 'runtime' or not folder.parent.is_dir():
        return None
    found = []
    for other in folder.parent.iterdir():
        if other.is_dir() and other != folder and window_alive(other):
            try:
                found.append(((other / 'status.json').stat().st_mtime, other))
            except OSError:
                found.append((0, other))
    return max(found)[1] if found else None


def any_window(folder):
    folder = Path(folder)
    return window_alive(folder) or running_elsewhere(folder) is not None


def same_file(a, b):
    """Compare paths the Windows way: Qt gives C:/x/y.mp4, Path.resolve gives C:\\x\\y.mp4."""
    if not a or not b:
        return False
    norm = lambda p: os.path.normcase(os.path.normpath(os.path.abspath(str(p))))
    return norm(a) == norm(b)
