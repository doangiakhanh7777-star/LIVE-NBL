"""Start the app with a readable error if Windows fails to load a dependency."""
import os
import runpy
import sys
import traceback
from pathlib import Path
base=Path(__file__).resolve().parent
try:
    if sys.platform=='win32':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('NBL.Live.Desktop.4.0.2')
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.CreateMutexW.argtypes=[ctypes.c_void_p,ctypes.c_bool,ctypes.c_wchar_p];kernel.CreateMutexW.restype=ctypes.c_void_p
        app_mutex=kernel.CreateMutexW(None,False,'Local\\NBL_LIVE_Desktop_Console')
        if not app_mutex:raise ctypes.WinError(ctypes.get_last_error())
        if ctypes.get_last_error()==183:
            ctypes.windll.user32.MessageBoxW(None,'NBL LIVE đang mở. Dùng cửa sổ hiện tại để tránh chạy trùng lịch.','NBL LIVE',0x40)
            raise SystemExit(0)
    os.chdir(base)
    runpy.run_path(str(base/'app.py'),run_name='__main__')
except SystemExit:
    raise
except Exception:
    detail=traceback.format_exc()
    folder=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'NBL_LIVE_2';folder.mkdir(parents=True,exist_ok=True)
    path=folder/'startup_error.txt';path.write_text(detail,encoding='utf-8')
    if sys.platform=='win32':
        import ctypes
        ctypes.windll.user32.MessageBoxW(None,'NBL LIVE không mở được. Gửi file lỗi này để kiểm tra:\n'+str(path)+'\n\n'+detail[-900:],'NBL LIVE · Lỗi khởi động',0x10)
    else:print(detail,file=sys.stderr)
    raise SystemExit(1)
