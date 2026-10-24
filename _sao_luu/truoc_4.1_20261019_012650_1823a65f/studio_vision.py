"""Foreground-only Studio image backend. OCR and actions remain local/offline.

No blind retry: every click uses a fresh window capture; unreadable != empty.
The serial StudioWorker owns calls. Windows execution still needs native QA.

4.0.2: strict draft/author checks, typed stop/attention errors, fresh warning
checks before submission and scheduled probes, session-scoped caches, bundled
Vietnamese recognition, explicit actual model status, no silent fallback.
"""
import base64
import ctypes
import io
import hashlib
import json
import os
import sys
import threading
import time
from pathlib import Path
from studio_vision_logic import (validate_regions, clock_advancing, clock_reading, draft_state,
                                own_message_hits, message_confirmed, greeting_key, guard_revoked,
                                lines_beside, alert_texts, dismiss_button, faint_placeholder, is_placeholder, NotTouched, StudioAttention, InteractionCancelled, CommandExpired, NotSentCleaned)

BASE = Path(__file__).resolve().parent
if os.name == 'nt' and (BASE/'ocr_vendor').is_dir():
    sys.path.insert(0, str(BASE/'ocr_vendor'))
_dll_handles = []
if os.name == 'nt' and hasattr(os, 'add_dll_directory'):
    # The standalone status child also needs the bundled Microsoft C++ libraries.
    for directory in (Path(sys.executable).parent/'site-packages'/'PySide6',
                      Path(sys.executable).parent/'site-packages'/'shiboken6'):
        if directory.is_dir():
            _dll_handles.append(os.add_dll_directory(str(directory)))
_ocr = None
_ocr_retry_at = 0.0
_ocr_signature = None
_ocr_lock = threading.Lock()
_cache_lock = threading.Lock()
_live_cache = {}    # profile key -> (monotonic time, bool)
_alert_cache = {}   # profile key -> monotonic time of last clean scan
_dismissed_at = {}  # (profile key, x/10, y/10) -> time a popup button was clicked


def report(kind, nick, title, detail='', image=None):
    try:
        import nbl_reports
        return nbl_reports.add(kind, nick, title, detail, image)
    except Exception:
        return ''
LIVE_TTL, ALERT_TTL = 4.0, 20.0
SESSION_ALERT_REUSE = 30.0


_ocr_status = dict(state='not_loaded', name='PP-OCRv6 tiếng Việt (OcrDoc Run 6)', error='')


def ocr_model_info():
    folder = BASE/'ocr_models'/'vi'
    model, keys = folder/'rec.onnx', folder/'keys.txt'
    options = dict(rec_model_path=str(model), rec_keys_path=str(keys)) if model.is_file() and keys.is_file() else {}
    state = dict(_ocr_status)
    if state['state'] == 'loaded':
        label = 'Đang dùng: ' + state['name']
    elif state['state'] == 'error':
        label = 'Lỗi bộ đọc chữ: ' + state['error']
    elif not options:
        label = 'Thiếu bộ đọc tiếng Việt; cài lại gói cập nhật đầy đủ.'
    else:
        label = 'Bộ đọc tiếng Việt: chưa nạp / đang khởi động'
    return options, label


def _engine():
    global _ocr, _ocr_retry_at, _ocr_signature
    with _ocr_lock:
        if _ocr is None:
            files=[BASE/'ocr_models'/'vi'/name for name in ('rec.onnx','keys.txt')]
            signature=tuple((f.stat().st_size,f.stat().st_mtime_ns) if f.exists() else None for f in files)
            if time.monotonic()<_ocr_retry_at and signature==_ocr_signature:
                raise StudioAttention('Bộ đọc chữ chưa nạp được; đang chờ thử lại: '+_ocr_status.get('error',''))
            _ocr_signature=signature
            vendor = BASE/'ocr_vendor'
            if os.name == 'nt' and vendor.is_dir() and str(vendor) not in sys.path:
                sys.path.insert(0, str(vendor))
            try:
                from rapidocr_onnxruntime import RapidOCR
                extra, _ = ocr_model_info()
                if not extra:
                    raise RuntimeError('Thiếu rec.onnx hoặc keys.txt. Cài lại gói 4.0.2 đầy đủ.')
                import hashlib
                metadata=BASE/'ocr_models'/'vi'/'MODEL_INFO.json'
                info=json.loads(metadata.read_text(encoding='utf-8')) if metadata.is_file() else {}
                match=(hashlib.sha256(Path(extra['rec_model_path']).read_bytes()).hexdigest()==info.get('rec_sha256') and hashlib.sha256(Path(extra['rec_keys_path']).read_bytes()).hexdigest()==info.get('keys_sha256'))
                _ocr_status['name']=info.get('name','Mô hình tùy chỉnh') if match else 'Mô hình tùy chỉnh (khác bộ kèm theo)'
                candidate = RapidOCR(intra_op_num_threads=max(2, min(6, (os.cpu_count() or 2)-1)), inter_op_num_threads=1, **extra)
                if match:configure_fixed_width(candidate)
                _ocr = candidate
                _ocr_retry_at=0
                _ocr_status.update(state='loaded', error='')
            except Exception as error:
                _ocr_status.update(state='error', error=str(error)[:400])
                _ocr_retry_at=time.monotonic()+60
                # Never silently claim Vietnamese while using a Chinese model.
                raise StudioAttention('Không nạp được bộ đọc tiếng Việt: '+str(error)) from error
        return _ocr


def configure_fixed_width(engine):
    """The bundled recognizer was trained at width 320/640, not arbitrary widths.
    RapidOCR supplies the maximum aspect ratio for the entire batch, so all
    images in that batch keep identical tensor dimensions.
    """
    recognizer=engine.text_rec
    original=recognizer.resize_norm_img
    recognizer.resize_norm_img=lambda image,ratio: original(image,(320 if ratio<=320/48 else 640)/48)


def warmup():
    """Load OCR models in the background so the first send is not 5-10 s late."""
    try:
        from PIL import Image
        read_image(Image.new('RGB', (120, 40), 'white'))
        return True
    except Exception:
        return False


def read_image(image):
    import numpy as np
    engine = _engine()
    # Small, dim Studio text needs enlargement; scale coordinates back afterwards.
    scale = 3 if image.height < 80 else 2 if image.height < 300 else 1
    from PIL import ImageEnhance
    if scale > 1:
        image = ImageEnhance.Contrast(image.resize((image.width*scale, image.height*scale))).enhance(2)
    # RapidOCR accepts BGR arrays. Coordinates returned here are crop-local.
    with _ocr_lock:
        result, _ = engine(np.asarray(image.convert('RGB'))[:, :, ::-1].copy(), use_cls=False)
    lines = []
    for box, text, score in result or []:
        x, y = min(p[0] for p in box)/scale, min(p[1] for p in box)/scale
        lines.append(dict(text=text, score=float(score), x=x, y=y,
                          w=max(p[0] for p in box)/scale-x, h=max(p[1] for p in box)/scale-y))
    return sorted(lines, key=lambda line: (line['y'], line['x']))



# 4.0.3: the account image is compared with tolerance. 4.0.2 required pixel-exact
# equality (mean difference <= 7) at the exact saved position, so a hover
# highlight captured while the mouse rested on the name, a 1-2 px layout shift or
# a slightly different window tint made every action fail.
ANCHOR_SHIFT = 6          # pixels searched around the saved position
ANCHOR_MAX_DIFF = 10.0    # mean absolute difference (0-255) at the best offset
ANCHOR_MIN_CORR = 0.93    # brightness-independent correlation, for hover tints


def anchor_match(sample, image, x, y, shift=ANCHOR_SHIFT):
    """Best match of `sample` near (x, y) in `image`. Returns (ok, diff, corr, crop)."""
    import numpy as np
    a = np.asarray(sample.convert('L'), dtype=np.float32)
    h, w = a.shape
    left, top = max(0, x - shift), max(0, y - shift)
    right, bottom = min(image.width, x + w + shift), min(image.height, y + h + shift)
    area = np.asarray(image.crop((left, top, right, bottom)).convert('L'), dtype=np.float32)
    best = (1e9, -1.0, None)
    za = a - a.mean(); na = float(np.sqrt((za * za).sum())) or 1.0
    for dy in range(0, area.shape[0] - h + 1):
        for dx in range(0, area.shape[1] - w + 1):
            b = area[dy:dy + h, dx:dx + w]
            diff = float(np.abs(a - b).mean())
            zb = b - b.mean(); nb = float(np.sqrt((zb * zb).sum())) or 1.0
            corr = float((za * zb).sum() / (na * nb))
            if diff < best[0] or (corr > best[1] and diff <= best[0] + 1):
                best = (diff, corr, (left + dx, top + dy))
    diff, corr, pos = best
    if pos is None:
        return False, 255.0, 0.0, image.crop((x, y, x + w, y + h))
    crop = image.crop((pos[0], pos[1], pos[0] + w, pos[1] + h))
    return (diff <= ANCHOR_MAX_DIFF or corr >= ANCHOR_MIN_CORR), diff, corr, crop


def save_anchor_debug(sample, found):
    """Save saved-vs-current account images side by side so the user can see why."""
    try:
        from PIL import Image
        folder = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'NBL_LIVE_2' / 'logs'
        folder.mkdir(parents=True, exist_ok=True)
        scale = 4
        w, h = sample.width * scale, sample.height * scale
        board = Image.new('RGB', (w, h * 2 + 8), 'red')
        board.paste(sample.resize((w, h)), (0, 0))
        board.paste(found.resize((w, h)), (0, h + 8))
        path = folder / ('anh_ten_nick_' + time.strftime('%Y%m%d_%H%M%S') + '.png')
        board.save(path)
        return str(path)
    except Exception:
        return ''


_clock_debug_at = [0.0]


def save_clock_debug(image, frames, raw):
    """At most once a minute: save the clock box and what OCR read, for support."""
    if time.monotonic() - _clock_debug_at[0] < 60:
        return ''
    _clock_debug_at[0] = time.monotonic()
    try:
        folder = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'NBL_LIVE_2' / 'logs'
        folder.mkdir(parents=True, exist_ok=True)
        stem = folder / ('dong_ho_' + time.strftime('%Y%m%d_%H%M%S'))
        image.resize((image.width * 3, image.height * 3)).save(str(stem) + '.png')
        Path(str(stem) + '.txt').write_text(json.dumps(dict(frames=[f[0] for f in frames], ocr=raw), ensure_ascii=False, indent=1), encoding='utf-8')
        return str(stem) + '.png'
    except Exception:
        return ''

def save_send_debug(steps):
    """Save the input row after each send step plus what OCR read, for support."""
    try:
        from PIL import Image
        folder = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'NBL_LIVE_2' / 'logs'
        folder.mkdir(parents=True, exist_ok=True)
        stem = folder / ('gui_tin_' + time.strftime('%Y%m%d_%H%M%S'))
        images = [step[3] for step in steps if step[3] is not None]
        if images:
            width = max(i.width for i in images); height = sum(i.height+4 for i in images)
            sheet = Image.new('RGB', (width, height), 'white'); y = 0
            for image in images:
                sheet.paste(image, (0, y)); y += image.height+4
            sheet.resize((sheet.width*2, sheet.height*2)).save(str(stem)+'.png')
        Path(str(stem)+'.txt').write_text('\n'.join('%s: "%s" (%s)' % step[:3] for step in steps), encoding='utf-8')
        return str(stem)+'.png'
    except Exception:
        return ''


class NativeStudio:
    def __init__(self, profile, deadline=0, verify_geometry=True):
        if os.name != 'nt':
            raise RuntimeError('Điều khiển bằng ảnh chỉ chạy trên Windows.')
        from ctypes import wintypes as W
        self.W = W
        self.touched = False
        self.p, self.deadline = profile, deadline
        self.u = ctypes.WinDLL('user32', use_last_error=True)
        self.k = ctypes.WinDLL('kernel32', use_last_error=True)
        self.u.GetForegroundWindow.restype = W.HWND
        self.u.WindowFromPoint.argtypes = [W.POINT]; self.u.WindowFromPoint.restype = W.HWND
        self.u.GetAncestor.argtypes = [W.HWND, W.UINT]; self.u.GetAncestor.restype = W.HWND
        self.u.IsWindow.argtypes = [W.HWND]; self.u.IsIconic.argtypes = [W.HWND]
        self.u.GetWindowRect.argtypes = [W.HWND, ctypes.POINTER(W.RECT)]
        self.u.GetWindowThreadProcessId.argtypes = [W.HWND, ctypes.POINTER(W.DWORD)]
        self.u.GetWindowThreadProcessId.restype = W.DWORD
        self.u.AttachThreadInput.argtypes = [W.DWORD, W.DWORD, W.BOOL]
        self.u.BringWindowToTop.argtypes = [W.HWND]
        self.k.GetCurrentThreadId.restype = W.DWORD
        self.k.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]; self.k.OpenProcess.restype = W.HANDLE
        self.k.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, ctypes.POINTER(W.DWORD)]
        self.k.CloseHandle.argtypes = [W.HANDLE]
        self.u.GetDpiForWindow.argtypes = [W.HWND]; self.u.GetDpiForWindow.restype = W.UINT
        self.u.GetWindowTextW.argtypes = [W.HWND, W.LPWSTR, ctypes.c_int]
        self.u.SetForegroundWindow.argtypes = [W.HWND]
        self.u.ShowWindow.argtypes = [W.HWND, ctypes.c_int]
        try:
            self.u.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
            self.u.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
        except AttributeError:
            pass
        self.handle = int(profile.get('windowHandle') or 0)
        if not self.handle or not self.u.IsWindow(self.handle):
            raise StudioAttention('Cửa sổ Studio đã đổi. Kết nối lại cửa sổ, giữ các vùng đã lưu.')
        pid = W.DWORD()
        self.u.GetWindowThreadProcessId(self.handle, ctypes.byref(pid))
        self.studio_pid = pid.value
        if pid.value != int(profile['pid']):
            raise StudioAttention('Cửa sổ này không còn thuộc Studio đã lưu.')
        proc = self.k.OpenProcess(0x1000, False, pid.value)
        if not proc:
            raise PermissionError('Windows không cho kiểm tra Studio. Chạy NBL cùng mức quyền với Studio.')
        try:
            path, size = ctypes.create_unicode_buffer(32768), W.DWORD(32768)
            if not self.k.QueryFullProcessImageNameW(proc, 0, path, ctypes.byref(size)):
                raise ctypes.WinError(ctypes.get_last_error())
            if os.path.normcase(path.value) != os.path.normcase(profile['exePath']):
                raise StudioAttention('Đường dẫn Studio khác bản đã kết nối.')
        finally:
            self.k.CloseHandle(proc)
        self.config = profile.get('vision', {})
        self.verify_geometry = verify_geometry

    def _mouse_allowed(self):
        if not self.p.get('allowMouse'):
            return False
        permission = self.p.get('mousePermissionFile')
        try:
            return not permission or Path(permission).read_text(encoding='utf-8').strip() == '1'
        except OSError:
            return False

    def is_studio(self, hwnd):
        """Any window of the Studio process (main window, its dialogs, popups)."""
        if not hwnd:
            return False
        if hwnd == self.handle or self.u.GetAncestor(hwnd, 2) == self.handle or self.u.GetAncestor(hwnd, 3) == self.handle:
            return True
        pid = self.W.DWORD()
        self.u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value == self.studio_pid

    def in_front(self):
        # 4.0.3: a Studio dialog in front counts as Studio in front. 4.0.2 compared
        # with the main window only, so a Studio popup made every step fail.
        return self.is_studio(self.u.GetForegroundWindow())

    def _force_foreground(self):
        """Windows refuses SetForegroundWindow to background apps ("foreground
        lock"). 4.0.3 adds the usual ways round it: a harmless Alt tap counts as
        our own input, and a brief topmost toggle raises the window."""
        if self.u.SetForegroundWindow(self.handle) and self.in_front():
            return
        self.u.keybd_event.argtypes = [ctypes.c_ubyte, ctypes.c_ubyte, self.W.DWORD, ctypes.c_size_t]
        self.u.keybd_event(0x12, 0, 0, 0); self.u.keybd_event(0x12, 0, 2, 0)   # Alt down/up
        foreground = self.u.GetForegroundWindow()
        target_thread = self.u.GetWindowThreadProcessId(self.handle, None)
        fore_thread = self.u.GetWindowThreadProcessId(foreground, None) if foreground else 0
        mine = self.k.GetCurrentThreadId()
        attached = []
        try:
            for thread in {fore_thread, target_thread} - {0, mine}:
                if self.u.AttachThreadInput(mine, thread, True):
                    attached.append(thread)
            self.u.ShowWindow(self.handle, 5)
            self.u.SetWindowPos.argtypes = [self.W.HWND, self.W.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, self.W.UINT]
            self.u.SetWindowPos(self.handle, -1, 0, 0, 0, 0, 0x43)   # HWND_TOPMOST, no move/size, show
            self.u.SetWindowPos(self.handle, -2, 0, 0, 0, 0, 0x43)   # back to normal z-order
            self.u.BringWindowToTop(self.handle)
            self.u.SetForegroundWindow(self.handle)
        finally:
            for thread in attached:
                self.u.AttachThreadInput(mine, thread, False)

    def _click_title_bar(self):
        """Last resort: one click on an empty spot of Studio's own title bar, the
        same thing the user did by hand. Never on a button, never if covered."""
        r = self.W.RECT()
        if not self.u.GetWindowRect(self.handle, ctypes.byref(r)):
            return False
        scale = (self.u.GetDpiForWindow(self.handle) or 96) / 96.0
        x = int(r.left + min(260*scale, (r.right-r.left)*.22))
        y = int(r.top + 10*scale)
        if self.covering_window(x, y):
            return False
        old = self.W.POINT(); self.u.GetCursorPos(ctypes.byref(old))
        try:
            self.u.SetCursorPos(x, y)
            self.u.mouse_event(2, 0, 0, 0, 0); self.u.mouse_event(4, 0, 0, 0, 0)
        finally:
            self.u.SetCursorPos(old.x, old.y)
        time.sleep(.3)
        return self.in_front()

    # 4.0.3: when a LIVE starts, Studio may open "Trò chuyện LIVE" as its own
    # floating window over the main one. The saved regions are for the docked
    # layout, so NBL docks it back with the window's own "ghép" button: the
    # second icon from the right in its top bar (lock, settings, GHÉP, close).
    _dock_tried = {}

    def floating_windows(self):
        W = self.W; found = []
        proc = ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
        def visit(hwnd, _):
            if hwnd and hwnd != self.handle and self.u.IsWindowVisible(hwnd) and not self.u.IsIconic(hwnd):
                pid = W.DWORD(); self.u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value == self.studio_pid:
                    r = W.RECT()
                    try:   # visible bounds, without the invisible resize border
                        ok = ctypes.windll.dwmapi.DwmGetWindowAttribute(W.HWND(hwnd), 9, ctypes.byref(r), ctypes.sizeof(r)) == 0
                    except Exception:
                        ok = False
                    if ok or self.u.GetWindowRect(hwnd, ctypes.byref(r)):
                        found.append((hwnd, (r.left, r.top, r.right, r.bottom)))
            return True
        self.u.IsWindowVisible.argtypes = [W.HWND]
        self.u.EnumWindows(proc(visit), 0)
        scale = (self.u.GetDpiForWindow(self.handle) or 96) / 96.0
        return [(h, r) for h, r in found
                if 250*scale <= r[2]-r[0] <= 900*scale and r[3]-r[1] >= 300*scale], scale

    def dock_chat_window(self):
        """Dock a floating chat window. Returns (text, picture) when docked, else None."""
        if not self._mouse_allowed():
            return None
        windows, scale = self.floating_windows()
        for hwnd, rect in windows:
            if time.time() - self._dock_tried.get(hwnd, 0) < 120:
                continue
            from PIL import ImageGrab
            picture = ImageGrab.grab(rect, all_screens=True)
            icon = dock_icon(picture, scale)
            if icon is None:
                continue
            x, y = rect[0] + icon[0], rect[1] + icon[1]
            hit = self.u.WindowFromPoint(self.W.POINT(int(x), int(y)))
            if not hit or (hit != hwnd and self.u.GetAncestor(hit, 2) != hwnd):
                continue
            self.guard(True)
            self._dock_tried[hwnd] = time.time()
            old = self.W.POINT(); self.u.GetCursorPos(ctypes.byref(old))
            try:
                self.u.SetCursorPos(int(x), int(y))
                self.u.mouse_event(2, 0, 0, 0, 0); self.u.mouse_event(4, 0, 0, 0, 0)
            finally:
                self.u.SetCursorPos(old.x, old.y)
            for _ in range(10):
                time.sleep(.2)
                if not self.u.IsWindow(hwnd) or not self.u.IsWindowVisible(hwnd):
                    return ('Đã ghép cửa sổ Trò chuyện LIVE về Studio', picture)
            raise ValueError('Đã bấm nút ghép nhưng cửa sổ Trò chuyện LIVE vẫn nổi; bấm ghép tay một lần.')
        # Not dockable but lying over the input/chat NBL uses: clicking now would
        # type into the wrong window.
        main = self.W.RECT(); self.u.GetWindowRect(self.handle, ctypes.byref(main))
        for hwnd, rect in windows:
            for name in ('input', 'send', 'chat'):
                region = self.config.get('regions', {}).get(name)
                if not region:
                    continue
                cx, cy = main.left + region[0] + region[2]/2, main.top + region[1] + region[3]/2
                if rect[0] <= cx <= rect[2] and rect[1] <= cy <= rect[3]:
                    raise ValueError('Cửa sổ Trò chuyện LIVE đang nổi đè lên ô nhập/khung chat và chưa ghép được; bấm nút ghép trên cửa sổ đó một lần.')
        return None

    def activate(self):
        if self.in_front() and not self.u.IsIconic(self.handle):
            return
        if not self._mouse_allowed():
            raise InteractionCancelled('Cho phép chuột / bàn phím Studio trước khi đưa cửa sổ lên.')
        if self.deadline and time.time() >= self.deadline:
            if self.touched:raise TimeoutError('Hết thời gian sau khi đã thao tác; cần kiểm tra kết quả.')
            raise CommandExpired('Lệnh chờ quá hạn; chưa thao tác, sẽ thử lại sau.')
        if self.u.IsIconic(self.handle):
            self.u.ShowWindow(self.handle, 9)
            time.sleep(.3)
        # 4.0.3: Studio (Chromium) can take well over 200 ms to come to the front
        # while it is streaming, so each way is given up to a second, and there
        # are more ways before giving up. Used by every action, messages and
        # greetings alike.
        self._activating = True
        try:
            for method in (self._force_foreground, self._force_foreground, self._switch_to,
                           self._click_title_bar):
                try:
                    method()
                except Exception:
                    pass
                if self.wait_front(1.0):
                    break
            self.guard()
        finally:
            self._activating = False

    def wait_front(self, seconds):
        until = time.time() + seconds
        while True:
            if self.in_front():
                return True
            if time.time() >= until:
                return False
            time.sleep(.05)

    def _switch_to(self):
        self.u.SwitchToThisWindow.argtypes = [self.W.HWND, self.W.BOOL]
        self.u.SwitchToThisWindow(self.handle, True)

    def front_name(self):
        hwnd = self.u.GetForegroundWindow()
        if not hwnd:
            return 'không có cửa sổ nào'
        r = self.W.RECT()
        if not self.u.GetWindowRect(hwnd, ctypes.byref(r)):
            return 'không xác định'
        return self.covering_window((r.left+r.right)//2, (r.top+r.bottom)//2) or 'Studio'

    def guard(self, input_action=False):
        token = self.p.get('_interactionGuard')
        if token:
            try:
                current = Path(token['path']).read_text(encoding='utf-8')
            except OSError:
                current = ''
            if guard_revoked(token['token']) or current != token['token']:
                raise InteractionCancelled('Mục này đã dừng; hủy thao tác đang chờ.')
        if input_action and not self._mouse_allowed():
            raise InteractionCancelled('Chuột / bàn phím Studio đang tắt.')
        if self.deadline and time.time() >= self.deadline:
            if self.touched:raise TimeoutError('Hết thời gian sau khi đã thao tác; cần kiểm tra kết quả.')
            raise CommandExpired('Lệnh chờ quá hạn; chưa thao tác, sẽ thử lại sau.')
        if self.u.IsIconic(self.handle):
            raise ValueError('Studio đang thu xuống thanh tác vụ. Mở Studio để đọc bằng ảnh.')
        if not self.in_front():
            # 4.0.3: focus was lost between two steps (OCR takes seconds): bring
            # Studio back instead of failing at once.
            if self._mouse_allowed() and not getattr(self, '_activating', False):
                self.activate()
                return
            raise ValueError('Chưa đưa được Studio lên trước sau 4 cách thử (đang ở trước: %s). Thử lại sau.' % self.front_name())

    def points_to_check(self, width, height):
        """Corners and centre of every configured region and the account image."""
        rects = [r for r in (self.config.get('regions') or {}).values() if isinstance(r, list) and len(r) == 4]
        try:
            a = json.loads(self.p.get('accountAnchor') or '{}')
            rects.append([int(a['x']), int(a['y']), int(a['width']), int(a['height'])])
        except (ValueError, KeyError, TypeError):
            pass
        if not rects:  # nothing configured yet (e.g. capturing the setup image)
            rects = [[int(width*.1), int(height*.1), int(width*.8), int(height*.8)]]
        points = []
        for x, y, w, h in rects:
            for px, py in ((x+2, y+2), (x+w-3, y+2), (x+2, y+h-3), (x+w-3, y+h-3), (x+w//2, y+h//2)):
                if 0 <= px < width and 0 <= py < height:
                    points.append((px, py))
        return points

    def covering_window(self, x, y):
        """'' if (x, y) shows Studio (any window of the Studio process), else who covers it."""
        hwnd = self.u.WindowFromPoint(self.W.POINT(int(x), int(y)))
        if not hwnd:
            return 'không xác định'
        root = self.u.GetAncestor(hwnd, 2)
        if root == self.handle or self.u.GetAncestor(hwnd, 3) == self.handle:
            return ''
        pid = self.W.DWORD()
        self.u.GetWindowThreadProcessId(root or hwnd, ctypes.byref(pid))
        if pid.value == self.studio_pid:
            return ''
        title = ctypes.create_unicode_buffer(256)
        self.u.GetWindowTextW(root or hwnd, title, 256)
        name = 'PID %d' % pid.value
        proc = self.k.OpenProcess(0x1000, False, pid.value)
        if proc:
            try:
                buf, size = ctypes.create_unicode_buffer(32768), self.W.DWORD(32768)
                if self.k.QueryFullProcessImageNameW(proc, 0, buf, ctypes.byref(size)):
                    name = os.path.basename(buf.value)
            finally:
                self.k.CloseHandle(proc)
        return name + ((' · ' + title.value) if title.value else '')

    def snapshot(self, account=True):
        # 4.0.3: if focus was lost between steps (a click on NBL, a popup), bring
        # Studio back once instead of failing the whole check.
        if not self.in_front() and self._mouse_allowed():
            self.activate()
        self.guard()
        r = self.W.RECT()
        if not self.u.GetWindowRect(self.handle, ctypes.byref(r)):
            raise ctypes.WinError(ctypes.get_last_error())
        width, height = r.right-r.left, r.bottom-r.top
        if width < 100 or height < 100 or width > 10000 or height > 10000:
            raise ValueError('Kích thước cửa sổ Studio không hợp lệ.')
        dpi = int(self.u.GetDpiForWindow(self.handle))
        if self.verify_geometry and (width != self.config.get('width') or height != self.config.get('height') or dpi != self.config.get('dpi')):
            raise StudioAttention('Kích thước / tỷ lệ Studio đã đổi. Khoanh lại các vùng đọc bằng ảnh.')
        # 4.0.3: check only the areas NBL reads or clicks, and accept Studio's own
        # child/popup windows (chat panel, preview, tooltips belong to the same
        # process). 4.0.2 demanded the whole window be one top-level window, so
        # Studio's own panels or any small popup over an unused corner blocked all.
        for x, y in self.points_to_check(width, height):
            cover = self.covering_window(r.left + x, r.top + y)
            if cover:
                raise ValueError('Studio đang bị cửa sổ khác che (' + cover + '). Chưa thao tác.')
        from PIL import ImageGrab
        image = ImageGrab.grab((r.left, r.top, r.right, r.bottom), all_screens=True)
        self.origin = (r.left, r.top)
        if account:
            self.verify_account(image)
        self.guard()
        return image, dpi

    def verify_account(self, image):
        from PIL import Image, ImageStat
        try:
            d = json.loads(self.p['accountAnchor'])
        except (TypeError, ValueError, KeyError):
            raise StudioAttention('Chọn ảnh tên nick trên Studio trước khi dùng đọc bằng ảnh.')
        if d.get('kind') != 'visual':
            raise StudioAttention('Cần ảnh tên nick riêng để đối chiếu khi đọc bằng ảnh.')
        if (d.get('windowWidth'), d.get('windowHeight'), d.get('dpi')) != (image.width, image.height, self.config.get('dpi')):
            raise StudioAttention('Ảnh tên nick khác kích thước Studio. Chọn lại ảnh tên nick.')
        sample = Image.open(io.BytesIO(base64.b64decode(d['image']))).convert('RGB')
        low, high = ImageStat.Stat(sample.convert('L')).extrema[0]
        if high - low < 25:
            raise StudioAttention('Ảnh tên nick trống hoặc không hợp lệ.')
        ok, diff, corr, found = anchor_match(sample, image, d['x'], d['y'])
        if not ok:
            saved = save_anchor_debug(sample, found)
            raise StudioAttention('Ảnh tên nick đã thay đổi (lệch %.1f, tương quan %.2f); chưa thao tác trên cửa sổ này. '
                                  'Nếu đã chọn trong khung video xem trước hoặc chỗ có số/đếm thay đổi, hãy chọn lại '
                                  'ảnh đại diện nick ở góc trên bên phải Studio.%s' % (diff, corr, (' Ảnh so sánh: ' + saved) if saved else ''))

    def cursor_out_of(self, rect):
        """The LIVE timer doubles as the End button and changes look on hover:
        if the pointer rests on it, move the pointer just outside first."""
        if not self._mouse_allowed() or not hasattr(self, 'origin'):
            return False
        x, y, w, h = rect
        left, top = self.origin[0] + x, self.origin[1] + y
        cur = self.W.POINT(); self.u.GetCursorPos(ctypes.byref(cur))
        if left - 4 <= cur.x <= left + w + 4 and top - 4 <= cur.y <= top + h + 4:
            self.u.SetCursorPos(int(left - 60), int(top + h // 2))
            time.sleep(.35)
            return True
        return False

    def click(self, x, y):
        self.guard(True)
        point = self.W.POINT(int(self.origin[0]+x), int(self.origin[1]+y))
        cover = self.covering_window(point.x, point.y)
        if cover:
            raise ValueError('Nút đang bị cửa sổ khác che (' + cover + '); chưa bấm.')
        old = self.W.POINT(); self.u.GetCursorPos(ctypes.byref(old))
        try:
            if not self.u.SetCursorPos(point.x, point.y):
                raise ctypes.WinError(ctypes.get_last_error())
            self.guard(True)
            self.touched = True
            self.u.mouse_event(2, 0, 0, 0, 0)
            self.u.mouse_event(4, 0, 0, 0, 0)
        finally:
            self.u.SetCursorPos(old.x, old.y)

    def type_text(self, text):
        self._input_focus=self.focus_handle()
        W = self.W
        class KEY(ctypes.Structure):
            _fields_ = [('vk', W.WORD), ('scan', W.WORD), ('flags', W.DWORD), ('time', W.DWORD), ('extra', ctypes.c_size_t)]
        class MOUSE(ctypes.Structure):
            _fields_ = [('x', W.LONG), ('y', W.LONG), ('data', W.DWORD), ('flags', W.DWORD), ('time', W.DWORD), ('extra', ctypes.c_size_t)]
        class UNION(ctypes.Union):
            _fields_ = [('key', KEY), ('mouse', MOUSE)]
        class INPUT(ctypes.Structure):
            _fields_ = [('type', W.DWORD), ('data', UNION)]
        self.u.SendInput.argtypes = [W.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
        raw = text.encode('utf-16-le')
        for offset in range(0, len(raw), 2):
            self.guard(True)
            scan = int.from_bytes(raw[offset:offset+2], 'little')
            events = (INPUT*2)()
            for i, flags in enumerate((4, 6)):
                events[i].type = 1; events[i].data.key = KEY(0, scan, flags, 0, 0)
            self.touched = True
            if self.u.SendInput(2, events, ctypes.sizeof(INPUT)) != 2:
                raise ValueError('Windows chưa nhận đủ chữ; dừng để tránh gửi sai.')


    def focus_handle(self):
        W=self.W
        class GUIINFO(ctypes.Structure):
            _fields_=[('size',W.DWORD),('flags',W.DWORD)]+[(name,W.HWND) for name in ('active','focus','capture','menu','move','caret')]+[('rect',W.RECT)]
        info=GUIINFO();info.size=ctypes.sizeof(info)
        self.u.GetGUIThreadInfo.argtypes=[W.DWORD,ctypes.POINTER(GUIINFO)]
        if not self.u.GetGUIThreadInfo(self.u.GetWindowThreadProcessId(self.handle,None),ctypes.byref(info)):
            raise ValueError('Không đọc được ô đang nhận phím; chưa xóa bản nháp.')
        return info.focus

    def _send_keys(self, keys, name):
        """Real key presses via SendInput: keys = [(vk, scan, flags)], flags 2 = key up,
        1 = extended key. Some Chromium-based inputs ignore keys without a scan code."""
        self.guard(True)
        W = self.W
        class KEY(ctypes.Structure):
            _fields_ = [('vk', W.WORD), ('scan', W.WORD), ('flags', W.DWORD), ('time', W.DWORD), ('extra', ctypes.c_size_t)]
        class MOUSE(ctypes.Structure):
            _fields_ = [('x', W.LONG), ('y', W.LONG), ('data', W.DWORD), ('flags', W.DWORD), ('time', W.DWORD), ('extra', ctypes.c_size_t)]
        class UNION(ctypes.Union):
            _fields_ = [('key', KEY), ('mouse', MOUSE)]
        class INPUT(ctypes.Structure):
            _fields_ = [('type', W.DWORD), ('data', UNION)]
        self.u.SendInput.argtypes = [W.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
        events = (INPUT*len(keys))()
        for i, (vk, scan, flags) in enumerate(keys):
            events[i].type = 1; events[i].data.key = KEY(vk, scan, flags, 0, 0)
        if self.u.SendInput(len(keys), events, ctypes.sizeof(INPUT)) != len(keys):
            raise ValueError('Windows chưa nhận phím ' + name + '.')

    def _press_key(self, vk, scan, name, extended=0):
        self._send_keys([(vk, scan, extended), (vk, scan, 2 | extended)], name)

    def _ctrl(self, vk, scan, name):
        self._send_keys([(0x11, 0x1D, 0), (vk, scan, 0), (vk, scan, 2), (0x11, 0x1D, 2)], 'Ctrl+' + name)

    # 4.0.3: the input box is checked through the clipboard (Ctrl+A, Ctrl+C) and
    # filled with Ctrl+V, instead of reading it from the screen. Exact text, any
    # length, any number of lines, caret or no caret.
    def _clipboard(self):
        u, k, W = self.u, self.k, self.W
        if not getattr(self, '_clip_ready', False):
            u.OpenClipboard.argtypes = [W.HWND]; u.GetClipboardData.argtypes = [W.UINT]; u.GetClipboardData.restype = W.HANDLE
            u.SetClipboardData.argtypes = [W.UINT, W.HANDLE]; u.SetClipboardData.restype = W.HANDLE
            u.IsClipboardFormatAvailable.argtypes = [W.UINT]
            k.GlobalAlloc.argtypes = [W.UINT, ctypes.c_size_t]; k.GlobalAlloc.restype = W.HGLOBAL
            k.GlobalLock.argtypes = [W.HGLOBAL]; k.GlobalLock.restype = ctypes.c_void_p
            k.GlobalUnlock.argtypes = [W.HGLOBAL]; k.GlobalFree.argtypes = [W.HGLOBAL]
            self._clip_ready = True
        for _ in range(25):
            if u.OpenClipboard(None):
                return
            time.sleep(.04)
        raise ValueError('Clipboard đang bị phần mềm khác giữ; chưa gửi.')

    def clip_get(self):
        """Text on the clipboard, or None when it holds no text."""
        self._clipboard()
        try:
            if not self.u.IsClipboardFormatAvailable(13):
                return None
            handle = self.u.GetClipboardData(13)
            if not handle:
                return None
            pointer = self.k.GlobalLock(handle)
            try:
                return ctypes.wstring_at(pointer) if pointer else None
            finally:
                self.k.GlobalUnlock(handle)
        finally:
            self.u.CloseClipboard()

    def clip_set(self, text):
        data = (text or '').encode('utf-16-le') + b'\0\0'
        self._clipboard()
        try:
            self.u.EmptyClipboard()
            if text is None:
                return
            handle = self.k.GlobalAlloc(0x0002, len(data))
            pointer = self.k.GlobalLock(handle)
            ctypes.memmove(pointer, data, len(data))
            self.k.GlobalUnlock(handle)
            if not self.u.SetClipboardData(13, handle):
                self.k.GlobalFree(handle)
                raise ValueError('Không ghi được clipboard.')
        finally:
            self.u.CloseClipboard()

    def read_box(self):
        """Text copied from the focused input with Ctrl+A, Ctrl+C; None when the
        copy produced nothing (empty box, or copying not possible here)."""
        import uuid
        sentinel = '\u2063NBL-' + uuid.uuid4().hex
        self.clip_set(sentinel)
        self._ctrl(0x41, 0x1E, 'A')
        time.sleep(.08)
        self._ctrl(0x43, 0x2E, 'C')
        for _ in range(8):
            time.sleep(.08)
            value = self.clip_get()
            if value != sentinel:
                return None if value is None else value.replace('\r\n', '\n')
        return None

    def paste_text(self, text):
        self._input_focus = self.focus_handle()
        self.clip_set(text)
        self.touched = True
        self._ctrl(0x56, 0x2F, 'V')

    def press_end(self):
        self._press_key(0x23, 0x4F, 'End', extended=1)

    def press_enter(self):
        self.touched = True
        self._press_key(0x0D, 0x1C, 'Enter')

    def press_escape(self):
        """4.0.3: leave the input box so its hint text shows normally again.
        Not a chat action, so it does not count as having touched the chat."""
        self._press_key(0x1B, 0x01, 'Esc')

    def clear_text(self):
        self.guard(True)
        if not getattr(self,'_input_focus',None) or self.focus_handle()!=self._input_focus:
            raise ValueError('Ô nhận phím đã đổi; giữ bản nháp để kiểm tra.')
        # One bounded key chord; never clicks Send or presses Enter.
        self.u.keybd_event.argtypes=[ctypes.c_ubyte,ctypes.c_ubyte,self.W.DWORD,ctypes.c_size_t]
        try:
            self.u.keybd_event(0x11,0,0,0)
            self.u.keybd_event(0x41,0,0,0);self.u.keybd_event(0x41,0,2,0)
        finally:self.u.keybd_event(0x11,0,2,0)
        self.guard(True)
        if self.focus_handle()!=self._input_focus:raise ValueError('Ô nhận phím đã đổi; không xóa chữ.')
        self.u.keybd_event(0x08,0,0,0);self.u.keybd_event(0x08,0,2,0)


def crop(frame, rect):
    x, y, w, h = rect
    return frame.crop((x, y, x+w, y+h))


def masked(frame, rects):
    """Copy of the frame with the given regions blacked out."""
    from PIL import ImageDraw
    image = frame.copy()
    draw = ImageDraw.Draw(image)
    for x, y, w, h in rects:
        draw.rectangle((x, y, x+w, y+h), fill='black')
    return image


def changed_boxes(before, after, cell=24, threshold=24, full_share=.6, pad=10):
    """Pixel boxes around areas that differ between two same-size images.
    Returns [] when nothing changed and None when a full scan is safer."""
    import numpy as np
    if before.size != after.size:
        return None
    a = np.asarray(before.convert('RGB'), dtype=np.int16)
    b = np.asarray(after.convert('RGB'), dtype=np.int16)
    changed = (np.abs(a-b).max(axis=2) > threshold)
    height, width = changed.shape
    rows, cols = -(-height//cell), -(-width//cell)
    grid = np.zeros((rows, cols), dtype=bool)
    for r in range(rows):
        band = changed[r*cell:(r+1)*cell]
        for c in range(cols):
            grid[r, c] = band[:, c*cell:(c+1)*cell].any()
    if grid.mean() > full_share:
        return None
    # Grow by one cell so text cut at a cell edge is read whole.
    grown = grid.copy()
    grown[1:] |= grid[:-1]; grown[:-1] |= grid[1:]
    grown[:, 1:] |= grid[:, :-1]; grown[:, :-1] |= grid[:, 1:]
    seen = np.zeros_like(grown); boxes = []
    for r in range(rows):
        for c in range(cols):
            if not grown[r, c] or seen[r, c]:
                continue
            stack = [(r, c)]; seen[r, c] = True; r0 = r1 = r; c0 = c1 = c
            while stack:
                i, j = stack.pop()
                r0, r1, c0, c1 = min(r0, i), max(r1, i), min(c0, j), max(c1, j)
                for ni, nj in ((i+1, j), (i-1, j), (i, j+1), (i, j-1)):
                    if 0 <= ni < rows and 0 <= nj < cols and grown[ni, nj] and not seen[ni, nj]:
                        seen[ni, nj] = True; stack.append((ni, nj))
            x0, y0 = max(0, c0*cell-pad), max(0, r0*cell-pad)
            x1, y1 = min(width, (c1+1)*cell+pad), min(height, (r1+1)*cell+pad)
            boxes.append((x0, y0, x1-x0, y1-y0))
    return boxes


def dock_icon(window_image, scale=1.0):
    """(x, y) inside the floating chat window of its dock ("ghép") icon: in the
    top bar, the 2nd icon from the right in a row of 3-5 small icons."""
    import numpy as np
    w, h = window_image.size
    top = int(min(h, 64*scale)); left = int(w*.55)
    band = np.asarray(window_image.crop((left, 0, w, top)).convert('L'), dtype=np.int16)
    if band.size == 0:
        return None
    full = np.abs(band - int(np.median(band))) > 60
    full[full.mean(axis=1) > .5, :] = False          # horizontal borders / separators
    full[:, full.mean(axis=0) > .5] = False          # vertical borders
    rows_on = list(full.sum(axis=1) >= 3)
    runs, r = [], 0
    while r < len(rows_on):
        if rows_on[r]:
            r1 = r
            while r1+1 < len(rows_on) and (rows_on[r1+1] or (r1+2 < len(rows_on) and rows_on[r1+2])):
                r1 += 1
            runs.append((r, r1)); r = r1+1
        else:
            r += 1
    for r0, r1 in runs:
        if not 6*scale <= r1-r0+1 <= 34*scale or r0 < 4*scale:
            continue   # too tall/short, or touching the top edge (not inside this window)
        mask = full[r0:r1+1].copy()
        mask[:, mask.mean(axis=0) > .8] = False
        blobs, start, gap, end = [], None, 0, 0
        for x, on in enumerate(list(mask.any(axis=0)) + [False]*8):
            if on:
                if start is None: start = x
                gap = 0; end = x
            elif start is not None:
                gap += 1
                if gap > max(2, int(3*scale)):
                    blobs.append((start, end)); start = None
        blobs = [(a, b) for a, b in blobs if 6*scale <= b-a+1 <= 34*scale and b < mask.shape[1]-2]
        if 3 <= len(blobs) <= 5:
            a, b = sorted(blobs, key=lambda blob: -blob[0])[1]
            return (left + (a+b)/2, (r0+r1)/2)
    return None

# 4.0.3: decide "input box is empty" from pixels, not only from OCR. Typed text is
# drawn bright (≈239 on Studio's dark box, background ≈49); the hint "Thêm bình
# luận" is dim grey (≈111). After a send the box stays focused, the caret blinks
# in front of the dim hint and OCR reads just "I" or nothing, so every next send
# was postponed ("Ô nhập chưa đọc rõ"). Only the left 60 % of the box is checked:
# typed text starts at the left edge, the emoji / Send icons sit at the right.
HINT_CONTRAST_DEFAULT = 90
_hint_contrast = {}   # profile key -> learned contrast of the dim hint text


def input_pixels(image, threshold=HINT_CONTRAST_DEFAULT, caret_width=3):
    """'empty' when nothing brighter than the hint is drawn in the left 60 % of
    the box except one caret-wide vertical stripe, else 'occupied'."""
    import numpy as np
    gray = np.asarray(image.convert('L'), dtype=np.int16)
    if gray.size == 0:
        return 'occupied'
    gray = gray[:, :max(1, int(gray.shape[1]*.6))]
    background = int(np.median(gray))
    columns = np.where((np.abs(gray - background) > threshold).any(axis=0))[0]
    if len(columns) == 0:
        return 'empty'
    return 'empty' if columns[-1] - columns[0] + 1 <= caret_width else 'occupied'


def hint_contrast(image):
    import numpy as np
    gray = np.asarray(image.convert('L'), dtype=np.int16)
    gray = gray[:, :max(1, int(gray.shape[1]*.6))]
    return int(np.abs(gray - int(np.median(gray))).max()) if gray.size else 0


def same_draft(before, after, caret_width=3):
    """True when two input-box images are identical except for the blinking
    caret: one stripe at most 3 px wide and at least ~text height tall. Any
    other difference (a dot, a letter, a changed word) means someone edited."""
    from PIL import ImageChops
    if before.size != after.size:
        return False
    box = ImageChops.difference(before.convert('RGB'), after.convert('RGB')).convert('L').point(lambda v: 255 if v > 30 else 0).getbbox()
    if box is None:
        return True
    width, height = box[2]-box[0], box[3]-box[1]
    return width <= caret_width and height >= max(10, before.height*.4)


def button_matches(frame, rect, encoded, edges=False):
    import cv2
    import numpy as np
    from PIL import Image
    sample = np.asarray(Image.open(io.BytesIO(base64.b64decode(encoded))).convert('RGB'))
    region = np.asarray(crop(frame, rect).convert('RGB'))
    if sample.std() < 10 or min(sample.shape[:2]) < 8 or sample.shape[0] > region.shape[0] or sample.shape[1] > region.shape[1]:
        return []
    if edges:
        sample = cv2.Canny(sample, 40, 120)
        region = cv2.Canny(region, 40, 120)
        if np.count_nonzero(sample) < 15:
            return []
    scores = cv2.matchTemplate(region, sample, cv2.TM_CCOEFF_NORMED)
    found = []
    for _ in range(30):
        _, score, _, (x, y) = cv2.minMaxLoc(scores)
        if score < .94:
            break
        found.append((rect[0]+x+sample.shape[1]/2, rect[1]+y+sample.shape[0]/2))
        scores[max(0, y-sample.shape[0]):y+sample.shape[0], max(0, x-sample.shape[1]):x+sample.shape[1]] = -1
    return found


class VisionSession:
    def __init__(self, profile, deadline=0, native=None, reader=read_image, sleep=time.sleep, clock=time.monotonic):
        self.p, self.cfg = profile, profile.get('vision', {})
        self.native = native or NativeStudio(profile, deadline)
        self.read, self.sleep, self.clock = reader, sleep, clock
        self.key = hashlib.sha256(json.dumps([profile.get('id'),profile.get('pid'),profile.get('windowHandle'),profile.get('accountAnchor'),self.cfg],sort_keys=True,ensure_ascii=False).encode('utf-8')).hexdigest()
        with _cache_lock:
            for cache in (_live_cache,_alert_cache):
                while len(cache)>64:cache.pop(next(iter(cache)))

    def account_name(self):
        return self.p.get('accountName') or self.p.get('name', '')

    def region_lines(self, frame, name):
        rect = self.input_rect() if name == 'input' else self.cfg['regions'][name]
        return self.read(crop(frame, rect))

    def input_rect(self):
        """4.0.3: the text part of the input box only. When the saved input
        region also covers the emoji and Send icons (the Send arrow turns pink
        once text is typed and OCR reads it as "VAAA IAA"), stop the region
        before them, using the saved Send button position."""
        x, y, w, h = self.cfg['regions']['input']
        send = self.cfg.get('regions', {}).get('send')
        if not send:
            return [x, y, w, h]
        sx, sy, sw, sh = send
        same_row = sy < y+h and sy+sh > y
        if same_row and x+w*.4 < sx < x+w:   # the Send button lies INSIDE the saved input region
            right = int(sx - sw*1.6)      # the emoji button sits just left of Send
            if right-x >= max(40, w*.4):
                return [x, y, min(w, right-x), h]
        return [x, y, w, h]

    def frame(self):
        self.last_frame = self.native.snapshot()[0]
        return self.last_frame

    def scan_alerts(self, frame, fresh=False):
        """OCR the whole window except chat/input, at most every ALERT_TTL seconds.

        4.0.3: a send used to OCR the whole window twice ~10 s apart (15-20 s each
        with the Vietnamese model). A "fresh" recheck inside the SAME command now
        reads only the parts of the window that changed since this command's
        last clean scan; a new warning or dialog changes pixels, so it is still
        read. Large changes, other sizes or older scans fall back to a full scan.
        """
        now = self.clock()
        with _cache_lock:
            if not fresh and now - _alert_cache.get(self.key, -1e9) < ALERT_TTL:
                return
        hidden = [self.cfg['regions'][name] for name in ('chat', 'input') if name in self.cfg.get('regions', {})]
        image = masked(frame, hidden)
        previous = getattr(self, '_clean_frame', None)
        boxes = None
        if fresh and previous is not None and now - self._scanned_at < SESSION_ALERT_REUSE:
            boxes = changed_boxes(previous, image)
        if boxes is None:
            lines = self.read(image)
        else:
            lines = []
            for x, y, w, h in boxes:
                # window coordinates, so a found button can be clicked
                lines += [{**l, 'x': l['x']+x, 'y': l['y']+y} for l in self.read(crop(image, (x, y, w, h)))]
        alerts = alert_texts(lines)
        if self.close_notice(frame, lines, alerts, hidden):
            return
        if alerts:
            self._clean_frame = None
            with _cache_lock:
                _alert_cache.pop(self.key, None); _live_cache.pop(self.key, None)
            raise StudioAttention('Studio đang có cảnh báo: '+'; '.join(alerts))
        with _cache_lock:
            _alert_cache[self.key] = now
        self._clean_frame, self._scanned_at = image, now

    def close_notice(self, frame, lines, alerts, hidden):
        """4.0.3: close a Studio popup with its own OK/Đã hiểu/Đóng button and
        continue. Only for commands that may use the mouse; every close is
        written to the activity report with a picture of the popup."""
        if not getattr(self, 'allow_dismiss', False):
            return False
        point = dismiss_button(lines)
        if point is None:
            return False
        spot = (self.key, round(point[0]/10), round(point[1]/10))
        if time.time() - _dismissed_at.get(spot, 0) < 60:
            return False          # clicked here a minute ago and it is back: do not loop
        _dismissed_at[spot] = time.time()
        title = '; '.join(alerts) or next((l['text'] for l in lines if l['y'] < point[1] and abs(l['y']-point[1]) < 450 and len(l['text'].split()) >= 3), 'thông báo')
        before = self.native.touched
        try:
            self.native.click(*point)
        finally:
            self.native.touched = before   # closing a popup is not a chat action
        self.sleep(1.0)
        after = masked(self.native.snapshot()[0], hidden)
        remaining = self.read(after)
        if alert_texts(remaining):
            return False
        self.dismissed = getattr(self, 'dismissed', []) + [title]
        report('hoat_dong', self.account_name(), 'Tự đóng thông báo Studio', title, frame)
        now = self.clock()
        if not alert_texts(remaining):
            with _cache_lock:
                _alert_cache[self.key] = now
            self._clean_frame, self._scanned_at = after, now
        return True

    def live(self, fresh=False, fresh_alerts=False):
        validate_regions(self.cfg, ('clock',))
        now = self.clock()
        if not fresh:
            with _cache_lock:
                cached = _live_cache.get(self.key)
            if cached and now - cached[0] < LIVE_TTL:
                return cached[1]
        frames = []
        for index in range(2):
            frame = self.frame()
            mover = getattr(self.native, 'cursor_out_of', None)
            if index == 0 and mover and self.native.cursor_out_of(self.cfg['regions']['clock']):
                frame = self.frame()  # pointer was on the timer: read a frame without hover
            # 4.0.3: time of the SCREENSHOT, not of the end of OCR. The warning scan
            # on frame 1 can take 10-20 s with the Vietnamese model, so stamping
            # after OCR made a correct 00:01:37 -> 00:01:54 look like a 17 s jump
            # in ~2 s and rejected a running LIVE.
            taken = self.clock()
            if index == 0:
                self.scan_alerts(frame, fresh=fresh_alerts)
            text = self.read_clock(frame)
            frames.append((text, taken))
            if index == 0:
                self.sleep(1.3)
        result = None
        if clock_advancing(frames[0][0], frames[1][0], frames[1][1]-frames[0][1]):
            result = True
        else:
            # A missing/frozen clock alone never proves that a broadcast ended.
            for indicator in ('startButton','summaryClose'):
                try:
                    d = json.loads(self.p.get(indicator, ''))
                    rect = [d['x'], d['y'], d['width'], d['height']]
                    if d.get('kind') == 'visual' and (d['windowWidth'], d['windowHeight'], d['dpi']) == (frame.width, frame.height, self.cfg['dpi']):
                        if len(button_matches(frame, rect, d['image'])) == 1:
                            result = False
                            break
                except (ValueError, KeyError, TypeError):
                    pass
        if result is None:
            with _cache_lock:
                _live_cache.pop(self.key, None)
            saved = save_clock_debug(crop(frame, self.cfg['regions']['clock']), frames, getattr(self, '_clock_raw', []))
            raise ValueError('Chưa đọc được đồng hồ LIVE đang tăng (đọc được: %s → %s); không coi là LIVE đã tắt.%s'
                             % (frames[0][0] or 'trống', frames[1][0] or 'trống', (' Ảnh đồng hồ: ' + saved) if saved else ''))
        with _cache_lock:
            _live_cache[self.key] = (self.clock(), result)
        return result

    def read_clock(self, frame):
        """Read HH:MM:SS from the clock box; retry on a cleaned-up copy (white digits on a dark button)."""
        from PIL import ImageOps
        box = crop(frame, self.cfg['regions']['clock'])
        self._clock_raw = []
        for variant in ('plain', 'inverted', 'threshold'):
            if variant == 'plain':
                image = box
            else:
                gray = ImageOps.autocontrast(box.convert('L'))
                if variant == 'inverted':
                    image = ImageOps.invert(gray).convert('RGB')
                else:
                    image = gray.point(lambda v: 0 if v > 150 else 255).convert('RGB')
                image = ImageOps.expand(image, border=8, fill='white')
            lines = self.read(image)
            self._clock_raw.append((variant, [(l['text'], round(l['score'], 2)) for l in lines]))
            value = clock_reading(lines)
            if value:
                return value
        return ''

    def check(self):
        validate_regions(self.cfg, ('input', 'send', 'chat', 'clock'))
        if not self.live():
            raise ValueError('Chưa LIVE; không gửi tin.')
        state, frame = self.empty_input_frame()
        if state=='unknown':raise NotTouched('Ô nhập chưa đọc rõ; thử lại sau, chưa gõ gì.'+self._draft_note())
        if state != 'empty':
            raise ValueError('Ô nhập có chữ. Giữ ô trống và thử lại; không gửi tin.'+self._draft_note())
        if not self.region_lines(frame, 'chat'):
            raise ValueError('Chưa đọc được chữ trong khung chat; không gửi tin.')
        return dict(readable=True, confirmed=True, live=True, method='offline-ocr')

    # 4.0.3: the blinking text caret sits right after the typed text, so one
    # screenshot can read "Hello anh em" and the next "Hello anh eml", and two
    # screenshots of the same draft differ by a 1-2 px column. Read a few frames
    # across the blink (Windows blinks every ~530 ms) instead of trusting one.
    DRAFT_READS = 4
    DRAFT_GAP = .3

    def draft_frame(self, text, own=False):
        rect = self.input_rect()
        self._draft_seen = []
        for attempt in range(self.DRAFT_READS):
            if attempt:
                self.sleep(self.DRAFT_GAP)
            frame = self.frame()
            if own and attempt == 0:
                self._owned_draft = crop(frame, rect).copy()
            lines = self.region_lines(frame, 'input')
            self._draft_seen.append(' '.join(l['text'] for l in lines) or 'trống')
            if draft_state(lines, text) == 'expected':
                if own:
                    self._owned_draft = crop(frame, rect).copy()
                return frame
        return None

    def pixel_state(self, frame):
        learned = _hint_contrast.get(self.key)
        threshold = min(160, max(60, learned + 30)) if learned is not None else HINT_CONTRAST_DEFAULT
        return input_pixels(crop(frame, self.input_rect()), threshold)

    def box_empty(self, frame, lines):
        """OCR first; if OCR is unsure, the pixels decide. A confident OCR read of
        real words (2+ words) always wins over pixels."""
        state = draft_state(lines)
        if state == 'empty':
            # remember how bright the hint text is on this PC / theme
            _hint_contrast[self.key] = hint_contrast(crop(frame, self.input_rect()))
            return 'empty'
        words = [l for l in lines if l['score'] >= .9 and len(l['text'].split()) >= 2 and not is_placeholder(l['text'])]
        if words:
            return 'occupied'
        if self.pixel_state(frame) == 'empty':
            return 'empty'
        return state

    def empty_input_frame(self, first=None, allow_escape=True):
        """4.0.3: read the input box over ~1 s (caret blink) and return
        (state, frame). OCR, then pixels; if still unsure, press Esc once to
        leave the box (its hint text then shows normally) and look again."""
        state, frame, faint_before = 'unknown', first, False
        self._draft_seen = []
        rounds = 2 if allow_escape else 1
        for round_ in range(rounds):
            if round_:
                self.native.press_escape()
                self.sleep(.4)
                frame = None
            for attempt in range(self.DRAFT_READS):
                if attempt or frame is None:
                    if attempt:
                        self.sleep(self.DRAFT_GAP)
                    frame = self.frame()
                lines = self.region_lines(frame, 'input')
                self._draft_seen.append(' '.join(l['text'] for l in lines) or 'trống')
                state = self.box_empty(frame, lines)
                faint = faint_placeholder(lines)
                if state == 'empty' or (faint and faint_before):
                    return 'empty', frame
                faint_before = faint
            if state == 'occupied':
                break      # real text in the box: never press anything
        return state, frame

    def _draft_note(self):
        seen = list(dict.fromkeys(getattr(self, '_draft_seen', [])))
        return (' Đọc được: ' + ' | '.join('"%s"' % t for t in seen[:3])) if seen else ''

    def _clear_owned_draft(self):
        if self._send_clicked:return False
        if getattr(self,'_clip_owned',False):
            try:
                # Erase only if the box holds exactly the line WE pasted.
                box=self.native.read_box()
                if box is None or box.strip()!=self._typed_text.strip():return False
                self.native.clear_text();self.sleep(.2)
                return self.native.read_box() is None
            except Exception:return False
        if self._owned_draft is None:return False
        try:
            rect=self.input_rect()
            # Same pixels as the draft we typed (allowing only the caret), not fuzzy
            # OCR: never erase a draft another person edited.
            for attempt in range(self.DRAFT_READS):
                if attempt:self.sleep(self.DRAFT_GAP)
                if same_draft(self._owned_draft,crop(self.frame(),rect)):break
            else:
                return False
            self.native.clear_text();self.sleep(.2)
            cleared=self.frame()
            return self.box_empty(cleared,self.region_lines(cleared,'input'))=='empty'
        except Exception:return False

    def send(self,text):
        self._owned_draft=None;self._send_clicked=False;self._clip_owned=False;self._typed_text=text
        try:return self._send_impl(text)
        except Exception as error:
            cleaned=False if isinstance(error,(StudioAttention,InteractionCancelled)) else self._clear_owned_draft()
            if cleaned and not isinstance(error,(StudioAttention,InteractionCancelled)):
                raise NotSentCleaned('Chưa bấm Gửi; đã xóa và xác nhận ô trống. '+str(error)) from error
            if (self._owned_draft is not None or self._clip_owned) and not cleaned and not self._send_clicked:
                error.args=(str(error)+' · Chưa xóa được bản nháp; kiểm tra ô nhập trước khi bật lại.',)
            error.submitted=self._send_clicked
            raise

    def _send_impl(self, text):
        if not isinstance(text, str) or not text.strip() or len(text) > 100 or '\n' in text or '\r' in text:
            raise StudioAttention('Tin nhắn cần từ 1 đến 100 ký tự, trên một dòng.')
        validate_regions(self.cfg, ('input', 'send', 'chat', 'clock'))
        if not self.live():
            raise ValueError('Chưa LIVE; không gửi tin.')
        if hasattr(self.native, 'read_box'):
            saved = self.native.clip_get()
            try:
                return self._send_clipboard(text)
            finally:
                try:
                    self.native.clip_set(saved)    # give the user's clipboard text back
                except Exception:
                    pass
        input_state, before = self.empty_input_frame()
        if input_state=='unknown':raise NotTouched('Ô nhập chưa đọc rõ; thử lại sau, chưa gõ gì.'+self._draft_note())
        if input_state != 'empty':
            raise StudioAttention('Ô nhập có chữ; chưa gõ tin.'+self._draft_note())
        chat_before = self.region_lines(before, 'chat')
        account = self.account_name()
        x, y, w, h = self.cfg['regions']['input']
        self.native.click(x+w/2, y+h/2)
        if self.empty_input_frame(allow_escape=False)[0] != 'empty':
            raise ValueError('Ô nhập sau khi bấm chưa trống rõ ràng; chưa gõ tin.'+self._draft_note())
        self.native.type_text(text)
        self.sleep(.25)
        typed = self.draft_frame(text, own=True)
        if typed is None:
            raise ValueError('Chưa đọc đúng câu vừa gõ. Giữ bản nháp để kiểm tra; không bấm Gửi.'+self._draft_note())
        # A fresh LIVE check and then fresh draft check precede the one send click.
        if not self.live(fresh=True,fresh_alerts=True):
            raise ValueError('LIVE đã kết thúc; không gửi tin.')
        ready = self.draft_frame(text)
        if ready is None:
            raise ValueError('Bản nháp đã đổi; không bấm Gửi.'+self._draft_note())
        return self._submit(text, chat_before, account, clip=False)

    def _submit(self, text, chat_before, account, clip):
        """Send what is in the box and confirm it.
        4.0.3: Enter, then Enter again, then a click on the CENTRE of the saved
        Send region. Each next step runs only while the box still holds exactly
        our sentence, so nothing can be sent twice (Enter or a click on an empty
        box sends nothing). With the clipboard the box content is known exactly
        (clip=True); otherwise OCR and pixels decide."""
        self._send_clicked = True   # also fixes 4.0.2, where this flag was never set
        chat_height = self.cfg['regions']['chat'][3]
        steps = []
        ix, iy, iw, ih = self.input_rect()
        sx, sy, sw, sh = self.cfg['regions']['send']
        if clip:
            self.native.press_end()     # drop the Ctrl+A selection, keep focus in the box
            actions = [('enter', self.native.press_enter),
                       ('enter lần 2', self.native.press_enter),
                       ('bấm giữa vùng nút Gửi', lambda: self.native.click(sx+sw/2, sy+sh/2))]
        else:
            actions = [('enter', lambda: (self.native.click(ix+iw/2, iy+ih/2), self.native.press_enter())),
                       ('enter lần 2', self.native.press_enter),
                       ('bấm giữa vùng nút Gửi', lambda: self.native.click(sx+sw/2, sy+sh/2))]
        empty_reads = 0
        seen = set()
        for name, act in actions:
            act()
            seen = set()
            if clip:
                self.sleep(.8)
                after = self.frame()
                if message_confirmed(chat_before, self.region_lines(after, 'chat'), account, text, chat_height):
                    return dict(sent=True, confirmed=True, method='offline-ocr')
                box = self.native.read_box()
                steps.append((name, box if box is not None else 'trống (copy ra rỗng)', 'clipboard', crop(after, [ix, iy, sx+sw-ix if sx > ix else iw, max(ih, sh)])))
                if box is None:
                    # Copying the focused box gave nothing: it is empty, Studio took the message.
                    return dict(sent=True, confirmed=True, method='clipboard-empty')
                if box.strip() == text.strip():
                    seen = {'expected'}
                    self.native.press_end()
                    continue            # still waiting in the box: next step
                # Something else was copied (focus left the box): fall through to OCR checks.
            for _ in range(4):
                self.sleep(.6)
                after = self.frame()
                lines = self.region_lines(after, 'input')
                state = draft_state(lines, text)
                seen.add(state)
                steps.append((name, ' '.join(l['text'] for l in lines) or 'trống', state, crop(after, [ix, iy, sx+sw-ix if sx > ix else iw, max(ih, sh)])))
                if message_confirmed(chat_before, self.region_lines(after, 'chat'), account, text, chat_height):
                    return dict(sent=True, confirmed=True, method='offline-ocr')
                empty_reads = empty_reads+1 if state == 'empty' or faint_placeholder(lines) or \
                    (state != 'expected' and self.box_empty(after, lines) == 'empty') else 0
                if empty_reads >= 2:
                    # The box we typed into emptied right after Enter: Studio took it.
                    return dict(sent=True, confirmed=True, method='draft-cleared')
            # Next step only while our exact sentence is clearly still waiting in the box.
            if 'expected' not in seen or 'empty' in seen or 'occupied' in seen:
                break
        saved = save_send_debug(steps)
        note = (' Ảnh các bước: ' + saved) if saved else ''
        if 'expected' in seen and 'empty' not in seen and 'occupied' not in seen:
            raise ValueError('Đã nhấn Enter 2 lần và bấm vùng nút Gửi nhưng ô nhập vẫn còn câu vừa gõ; Studio chưa gửi.' + note)
        raise ValueError('Đã gửi nhưng chưa xác nhận được trong chat (ô nhập: ' + str(steps[-1][1])[:80] + '). Không tự gửi lại; kiểm tra thủ công.' + note)

    def _send_clipboard(self, text):
        """4.0.3: click the box, Ctrl+A/C to see what it holds, Ctrl+V our line,
        Ctrl+A/C again to compare character by character, then send."""
        before = self.frame()
        chat_before = self.region_lines(before, 'chat')
        account = self.account_name()
        ix, iy, iw, ih = self.input_rect()
        self.native.click(ix+min(iw/2, 60), iy+ih/2)
        self.sleep(.2)
        box = self.native.read_box()
        if box and box.strip():
            raise StudioAttention('Ô nhập đang có chữ: "%s"; chưa gõ tin.' % box.strip()[:60])
        if box is None and self.empty_input_frame(allow_escape=False)[0] == 'occupied':
            raise StudioAttention('Ô nhập có chữ; chưa gõ tin.'+self._draft_note())
        self.native.paste_text(text)
        self._typed_text = text
        self.sleep(.3)
        box = self.native.read_box()
        if box is None:
            # Copying is not possible here: check the pasted line on screen instead.
            self.native.press_end()
            if self.draft_frame(text, own=True) is None:
                raise ValueError('Chưa đọc đúng câu vừa dán. Giữ bản nháp để kiểm tra; không gửi.'+self._draft_note())
            if not self.live(fresh=True, fresh_alerts=True):
                raise ValueError('LIVE đã kết thúc; không gửi tin.')
            if self.draft_frame(text) is None:
                raise ValueError('Bản nháp đã đổi; không gửi.'+self._draft_note())
            return self._submit(text, chat_before, account, clip=False)
        self._clip_owned = True
        if box.strip() != text.strip():
            raise ValueError('Câu trong ô khác câu mẫu (ô đang có: "%s"); không gửi.' % box.strip()[:80])
        self.native.press_end()
        # A fresh LIVE check, then the box is compared once more right before sending.
        if not self.live(fresh=True, fresh_alerts=True):
            raise ValueError('LIVE đã kết thúc; không gửi tin.')
        box = self.native.read_box()
        if box is None or box.strip() != text.strip():
            raise ValueError('Bản nháp đã đổi (ô đang có: "%s"); không gửi.' % (box or 'trống').strip()[:80])
        return self._submit(text, chat_before, account, clip=True)

    def greetings(self, frame, lines=None):
        """Map visible viewer name -> button centre. One OCR pass over the chat."""
        validate_regions(self.cfg, ('chat', 'greeting'))
        if not self.cfg.get('greetingImage'):
            raise ValueError('Khoanh một nút Chào mẫu trước.')
        chat = self.cfg['regions']['chat']
        hits = button_matches(frame, chat, self.cfg['greetingImage'])
        if lines is None:
            lines = self.region_lines(frame, 'chat') if hits else []
        rows = {}
        height = self.cfg['regions']['greeting'][3]
        for x, y in hits:
            key = greeting_key(lines_beside(lines, x-chat[0]-self.cfg['regions']['greeting'][2]/2, y-chat[1], height))
            if key:
                rows.setdefault(key, []).append((x, y))
        return {key: points[0] for key, points in rows.items() if len(points) == 1}

    def greet(self, key):
        if not self.live(fresh=True):
            raise ValueError('LIVE đã kết thúc; không bấm Chào.')
        rows = self.greetings(self.frame())
        if key not in rows:
            return dict(gone=True)
        self.sleep(.2)
        located = self.frame()
        fresh = self.greetings(located)
        if key not in fresh or any(abs(a-b) > 3 for a, b in zip(rows[key], fresh[key])):
            return dict(gone=True)
        # OCR may take time. Recheck the row pixels immediately before clicking.
        from PIL import ImageChops, ImageStat
        chat = self.cfg['regions']['chat']; x, y = fresh[key]
        height = self.cfg['regions']['greeting'][3]
        rect = [chat[0], max(chat[1], int(y-height)), int(chat[2]),
                min(height*2, chat[1]+chat[3]-max(chat[1], int(y-height)))]
        current = self.frame()
        if sum(ImageStat.Stat(ImageChops.difference(crop(located, rect), crop(current, rect))).mean)/3 > 2:
            return dict(gone=True)
        self.scan_alerts(current,fresh=True)
        checked=self.frame()
        if ImageChops.difference(crop(current,rect),crop(checked,rect)).getbbox() is not None:return dict(gone=True)
        self.native.click(*fresh[key])
        # Require the SAME joined row to remain readable while its button is gone.
        confirmations = 0
        for _ in range(4):
            self.sleep(.5)
            after = self.frame()
            lines = self.region_lines(after, 'chat')
            remaining = self.greetings(after, lines)
            visible = any(greeting_key([line]) == key for line in lines)
            confirmations = confirmations+1 if visible and key not in remaining else 0
            if confirmations >= 2:
                return dict(greeted=True, confirmed=True)
        return dict(greeted=False, attempted=True, uncertain=True)


DISMISS_ACTIONS = ('send', 'greet', 'greet_scan', 'chat_check')


def _run(session, profile, action, payload):
    result = _run_action(session, profile, action, payload)
    if isinstance(result, dict) and getattr(session, 'dismissed', None):
        result = {**result, 'dismissed': list(session.dismissed)}
    return result


def _run_action(session, profile, action, payload):
    session.allow_dismiss = action in DISMISS_ACTIONS
    session.native.activate()
    if session.allow_dismiss:
        docker = getattr(session.native, 'dock_chat_window', None)
        docked = docker() if docker else None
        if docked:
            report('hoat_dong', profile.get('accountName') or profile.get('name', ''), docked[0],
                   'Cửa sổ trò chuyện nổi lên khi bắt đầu LIVE; NBL bấm nút ghép.', docked[1])
            session.dismissed = getattr(session, 'dismissed', []) + [docked[0]]
            time.sleep(.5)
            session.native.activate()
    if action == 'vision_capture':
        session.native.verify_geometry = False
        frame, dpi = session.native.snapshot(account=False)
        stream = io.BytesIO(); frame.save(stream, format='PNG')
        return dict(image=base64.b64encode(stream.getvalue()).decode(), width=frame.width, height=frame.height, dpi=dpi)
    if action == 'status':
        live = session.live(fresh=True,fresh_alerts=bool((payload or {}).get('fresh_alerts')))
        return dict(live=live, confirmed=True, warnings=[], pid=profile['pid'], warningDetection='ocr-limited')
    if action == 'chat_check':
        return session.check()
    if action == 'send':
        return session.send((payload or {}).get('text'))
    if action == 'greet_scan':
        if not session.live():
            return dict(live=False, viewers=[])
        return dict(live=True, viewers=list(session.greetings(session.frame())))
    if action == 'greet':
        return session.greet((payload or {}).get('key'))
    raise ValueError('Thao tác ảnh chưa được hỗ trợ.')


# 4.0.3: the 20 s command deadline is a START-BY time (do not act on a stale
# queued command). It used to be the whole budget, but one warning scan of the
# full Studio window with the Vietnamese model takes 10-20 s on ordinary PCs,
# so every send expired before its first click ("Lệnh chờ quá hạn").
VISION_BUDGET = 90.0
BUDGET_ACTIONS = ('send', 'greet', 'greet_scan', 'chat_check')


def working_deadline(profile, action, deadline, now=None):
    now = time.time() if now is None else now
    if not deadline or action not in BUDGET_ACTIONS:
        return deadline
    if now >= deadline:
        raise CommandExpired('Lệnh chờ quá hạn; chưa thao tác, sẽ thử lại sau.')
    until = max(deadline, now + VISION_BUDGET)
    if profile.get('activeUntil'):
        until = min(until, max(deadline, profile['activeUntil']))
    return until


ACTION_NAMES = {'send': 'Gửi tin nhắn', 'greet': 'Chào khách', 'greet_scan': 'Dò khách mới', 'chat_check': 'Kiểm tra ô nhắn tin'}


def _report_error(session, profile, action, error):
    if action not in ACTION_NAMES:
        return
    image = getattr(session, 'last_frame', None) if session is not None else None
    report('loi', profile.get('accountName') or profile.get('name', ''), ACTION_NAMES[action] + ' chưa được',
           str(error), image)


def execute_vision(profile,action,deadline=0,payload=None):
    holder=[]
    try:
        return _execute_vision_inner(profile,action,deadline,payload,holder)
    except BaseException as error:
        _report_error(holder[0] if holder else None, profile, action, error)
        raise


def _execute_vision_inner(profile,action,deadline,payload,holder):
    session=None
    try:
        deadline=working_deadline(profile,action,deadline)
        session=VisionSession(profile,deadline)
        holder.append(session)
        return _run(session,profile,action,payload)
    except NotSentCleaned as error:
        error.touched=True;error.submitted=False
        raise
    except (StudioAttention,InteractionCancelled) as error:
        error.touched=bool(session is not None and session.native.touched)
        if session is not None:
            with _cache_lock:
                _live_cache.pop(session.key,None);_alert_cache.pop(session.key,None)
        raise
    except Exception as error:
        touched=bool(session is not None and session.native.touched)
        if not touched:
            retry=error if isinstance(error,NotTouched) else NotTouched(str(error))
            retry.touched=False
            raise retry from error
        # A retryable read failure after a click is not evidence that a send failed.
        if isinstance(error,NotTouched):error=RuntimeError(str(error))
        error.touched=True
        raise error


if __name__ == '__main__':
    try:
        profile = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8-sig'))
        print(json.dumps(execute_vision(profile, 'status', time.time()+15), ensure_ascii=False))
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
