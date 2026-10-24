"""Deliver video commands only to a live worker or a freshly started one."""
import os
import time
import uuid
from pathlib import Path
from model import write_json


def dispatch_video_command(folder, action, config, process, launch):
    if action not in ('play', 'pause', 'next', 'stop', 'close', 'settings'):
        raise ValueError('Lệnh video không hợp lệ.')
    alive = process is not None and process.poll() is None
    if not alive and action != 'play':
        return process
    folder = Path(folder)
    if not alive:
        # Commands from an earlier worker must not close or pause a new worker.
        for pending in (folder / 'commands').glob('*.json'):
            pending.unlink(missing_ok=True)
        (folder / 'status.json').unlink(missing_ok=True)
    token = str(time.time_ns()) + '-' + uuid.uuid4().hex
    write_json(folder / 'commands' / (token + '.json'),
               dict(token=token, action=action, config=config, deadline=time.time()+15))
    return process if alive else launch(folder)


def same_file(a, b):
    """Compare paths the Windows way: Qt gives C:/x/y.mp4, Path.resolve gives C:\\x\\y.mp4."""
    if not a or not b:
        return False
    norm = lambda p: os.path.normcase(os.path.normpath(os.path.abspath(str(p))))
    return norm(a) == norm(b)
