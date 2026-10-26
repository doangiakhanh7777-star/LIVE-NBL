# 4.1.6: update SETUP_FILES.json hashes only for the files this patch copied (keeps every other entry).
import hashlib, json, sys
from pathlib import Path
base = Path(sys.argv[1]); man = base / 'SETUP_FILES.json'
data = json.loads(man.read_text(encoding='utf-8')) if man.is_file() else {}
for name in sys.argv[2:]:
    p = base / name
    key = name.replace('\\', '/')
    if p.name == 'SETUP_FILES.json': continue
    if p.is_file(): data[key] = hashlib.sha256(p.read_bytes()).hexdigest()
    else: data.pop(key, None)          # a file the patch removed
data.pop('shop_login.py', None); data.pop('CHROME_NBL_LIVE/shop_login.js', None)
man.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')
