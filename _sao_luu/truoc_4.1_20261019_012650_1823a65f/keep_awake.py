"""Request system wakefulness only while the application runs, allow screen off."""
import sys

def set_awake(enabled):
    if sys.platform!='win32':return False
    import ctypes
    flags=0x80000000 | (0x00000001 if enabled else 0)
    return bool(ctypes.windll.kernel32.SetThreadExecutionState(flags))
