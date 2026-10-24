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
    folder = Path(folder)
    # 4.1.2: an NBL VIDEO window this app run did not start (opened before NBL was
    # restarted) is still alive when it wrote its status in the last 3 seconds.
    # Send it the command; never open a second window (Studio captures the first).
    running = alive or _fresh(folder)
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
    return process if alive else launch(folder)


def _fresh(folder, seconds=3):
    try:
        import json
        state = json.loads((Path(folder) / 'status.json').read_text(encoding='utf-8'))
        return time.time() - float(state.get('time', 0)) < seconds
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def same_file(a, b):
    """Compare paths the Windows way: Qt gives C:/x/y.mp4, Path.resolve gives C:\\x\\y.mp4."""
    if not a or not b:
        return False
    norm = lambda p: os.path.normcase(os.path.normpath(os.path.abspath(str(p))))
    return norm(a) == norm(b)
