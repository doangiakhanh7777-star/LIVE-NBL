"""4.0: one-click diagnostic bundle for support. Never includes secrets.

Included: logs, startup error, profiles (paths kept, no tokens exist there),
Studio schedules with screenshots/templates removed, interaction journal,
version and OCR model info. Excluded: notifications.json (Telegram bot token),
pairing_token.txt, chrome_accounts.json (page contents per nick).
"""
import json
import platform
import sys
import time
import zipfile
from pathlib import Path

VERSION = '4.3.13'
SECRET_KEYS = {'keys', 'key', 'api_key', 'apiKey', 'secret', 'pin_token', 'token', 'protected_token', 'password', 'image', 'sendImage', 'greetingImage', 'qrDataUrl'}
FILES = ('ai_reply.json', 'profiles.json', 'profiles.json.bak', 'studio_schedules.json', 'studio_interactions_journal.json', 'native_alarm_check.json')


def scrub(value):
    """Drop secret and image fields anywhere in a JSON value."""
    if isinstance(value, dict):
        return {k: ('[đã ẩn]' if k in SECRET_KEYS else scrub(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    if isinstance(value, str) and value.startswith('{') and '"image"' in value:
        try:
            return json.dumps(scrub(json.loads(value)), ensure_ascii=False)
        except ValueError:
            return value
    return value


def build(data_dir, destination, extra=None):
    data_dir, destination = Path(data_dir), Path(destination)
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as bundle:
        info = dict(version=VERSION, created=time.strftime('%Y-%m-%d %H:%M:%S'), python=sys.version,
                    platform=platform.platform(), **(extra or {}))
        bundle.writestr('info.json', json.dumps(info, ensure_ascii=False, indent=2))
        for name in FILES:
            path = data_dir/name
            if not path.is_file():
                continue
            try:
                text = json.dumps(scrub(json.loads(path.read_text(encoding='utf-8'))), ensure_ascii=False, indent=2)
            except (OSError, ValueError):
                text = '(không đọc được tệp này)'
            bundle.writestr(name, text)
        for path in sorted((data_dir/'logs').glob('app.log*')) + [data_dir/'startup_error.txt']:
            if path.is_file():
                bundle.write(path, 'logs/'+path.name)
        # 4.3.0: newest error / activity reports (with their Studio screenshots), small files only
        for kind, keep in (('loi', 12), ('hoat_dong', 6)):
            folder = data_dir/'bao_cao'/kind
            files = sorted((p for p in folder.glob('*') if p.is_file()), key=lambda p: p.stat().st_mtime)[-keep:] if folder.is_dir() else []
            for path in files:
                if path.stat().st_size <= 2 << 20 and path.suffix.lower() in ('.json', '.txt', '.log', '.png', '.jpg', '.html'):
                    if path.suffix.lower() == '.json':
                        try:
                            bundle.writestr('bao_cao/'+kind+'/'+path.name, json.dumps(scrub(json.loads(path.read_text(encoding='utf-8'))), ensure_ascii=False, indent=1))
                            continue
                        except (OSError, ValueError):
                            pass
                    bundle.write(path, 'bao_cao/'+kind+'/'+path.name)
    return destination


def auto(data_dir, reason, extra=None, every=1800, keep=5, now=None):
    """4.3.0 (owner): gather a diagnostic bundle by itself when something goes wrong.
    At most one per 30 minutes, newest 5 kept in %LOCALAPPDATA%\\NBL_LIVE_2\\chan_doan."""
    now = time.time() if now is None else now
    folder = Path(data_dir)/'chan_doan'
    folder.mkdir(parents=True, exist_ok=True)
    old = sorted(folder.glob('NBL_chan_doan_*.zip'), key=lambda p: p.stat().st_mtime)
    if old and now - old[-1].stat().st_mtime < every:
        return None
    target = folder/('NBL_chan_doan_'+time.strftime('%Y%m%d_%H%M%S', time.localtime(now))+'.zip')
    build(data_dir, target, dict(extra or {}, reason=str(reason)[:500]))
    for path in (old + [target])[:-keep]:
        try:
            path.unlink()
        except OSError:
            pass
    return target
