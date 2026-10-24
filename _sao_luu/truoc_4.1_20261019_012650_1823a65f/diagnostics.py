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

VERSION = '4.0.2'
SECRET_KEYS = {'token', 'protected_token', 'password', 'image', 'sendImage', 'greetingImage', 'qrDataUrl'}
FILES = ('profiles.json', 'profiles.json.bak', 'studio_schedules.json', 'studio_interactions_journal.json', 'native_alarm_check.json')


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
    return destination
