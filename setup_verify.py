"""Read-only post-install validation; never operates Studio or Chrome."""
import hashlib
import json
import sys
import traceback
from pathlib import Path

base = Path(__file__).resolve().parent
log = base / 'SETUP_CHECK.log'
try:
    expected = json.loads((base / 'SETUP_FILES.json').read_text(encoding='utf-8'))
    for name, digest in expected.items():
        path = base / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise RuntimeError('Tep thieu hoac sai noi dung: ' + name)
    from kiem_tra_cai_dat import check
    with log.open('w', encoding='utf-8') as out:
        sys.stdout = sys.stderr = out
        check()
        print('SETUP 4.1: DA KIEM TRA TOAN VEN ' + str(len(expected)) + ' TEP.')
except Exception:
    with log.open('a', encoding='utf-8') as out:
        traceback.print_exc(file=out)
    raise SystemExit(1)
