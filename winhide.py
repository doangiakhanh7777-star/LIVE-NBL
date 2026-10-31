"""4.3.16 (chủ máy, 31/10/2026): "Ẩn hết khi LIVE" — thu nhỏ cửa sổ TikTok LIVE Studio mà không bấm chuột.

Win32 thuần (ShowWindow), không lấy focus, không đụng chuột / bàn phím. NBL vẫn điều khiển Studio từ bên trong
(DevTools). Studio được NBL mở với cờ chống bóp tốc độ khi ẩn (studio_cdp.launch).
"""
import ctypes
import sys

SW_SHOWMINNOACTIVE = 7
SW_SHOWNOACTIVATE = 4
SW_RESTORE = 9
STUDIO = 'tiktok live studio'


def _api():
    from ctypes import wintypes
    u = ctypes.windll.user32; k = ctypes.windll.kernel32
    u.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM), wintypes.LPARAM]
    u.IsWindowVisible.argtypes = [wintypes.HWND]; u.IsIconic.argtypes = [wintypes.HWND]
    u.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]; u.GetWindow.restype = wintypes.HWND
    u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    u.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    u.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    k.OpenProcess.restype = wintypes.HANDLE; k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    return u, k, wintypes


def exe_of(pid):
    u, k, wt = _api()
    h = k.OpenProcess(0x1000, False, pid)            # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ''
    try:
        buf = ctypes.create_unicode_buffer(1024); n = wt.DWORD(1024)
        return buf.value if k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)) else ''
    finally:
        k.CloseHandle(h)


def windows(match=STUDIO, include_minimized=True):
    """Cửa sổ chính (hiện, không có chủ) của các tiến trình có tên file chứa `match`. [(hwnd, tiêu đề, đang thu nhỏ)]"""
    if sys.platform != 'win32':
        return []
    u, k, wt = _api(); out = []; cache = {}

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(hwnd, _):
        if not u.IsWindowVisible(hwnd) or u.GetWindow(hwnd, 4):        # GW_OWNER: bỏ cửa sổ phụ / menu
            return True
        pid = wt.DWORD(); u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value not in cache:
            cache[pid.value] = exe_of(pid.value).lower()
        if match in cache[pid.value].replace('\\', '/').split('/')[-1]:
            t = ctypes.create_unicode_buffer(256); u.GetWindowTextW(hwnd, t, 256)
            mini = bool(u.IsIconic(hwnd))
            if t.value and (include_minimized or not mini):
                out.append((int(hwnd), t.value, mini))
        return True

    u.EnumWindows(cb, 0)
    return out


def minimize(hwnds):
    """Thu nhỏ, không lấy focus. Trả các hwnd đã thu nhỏ (để hiện lại đúng những cái đó)."""
    if sys.platform != 'win32':
        return []
    u, _, _ = _api(); done = []
    for h in hwnds:
        if not u.IsIconic(h):
            u.ShowWindow(h, SW_SHOWMINNOACTIVE); done.append(h)
    return done


def restore(hwnds):
    if sys.platform != 'win32':
        return
    u, _, _ = _api()
    for h in hwnds:
        if u.IsIconic(h):
            u.ShowWindow(h, SW_RESTORE)
