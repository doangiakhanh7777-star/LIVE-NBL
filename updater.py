"""4.3.0 (owner, 28/10/2026): NBL tự cập nhật.

Checks the public release repo NBL-LIVE-2 (installers only, the source stays private),
downloads the installer, checks its SHA256 against the release, then starts it silently;
the installer closes nothing by itself, waits for NBL to quit, installs and opens NBL
again. Settings in %LOCALAPPDATA%\\NBL_LIVE_2 are not touched. Never during a LIVE.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.request import Request, urlopen

REPO = 'doangiakhanh7777-star/NBL-LIVE-2'
API = 'https://api.github.com/repos/' + REPO + '/releases/latest'


def parse_version(text):
    nums = re.findall(r'\d+', str(text or ''))[:4]
    return tuple(int(n) for n in nums) if nums else (0,)


def latest(timeout=15, fetch=None):
    """{'version', 'url', 'sha256', 'name', 'notes'} of the newest release, or None."""
    if fetch is None:
        def fetch(url):
            with urlopen(Request(url, headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'NBL-LIVE'}), timeout=timeout) as r:
                return r.read()
    data = json.loads(fetch(API).decode('utf-8'))
    assets = data.get('assets') or []
    exe = next((a for a in assets if str(a.get('name', '')).lower().endswith('.exe')), None)
    if not exe:
        return None
    sha = ''
    m = re.search(r'\b([0-9a-f]{64})\b', str(data.get('body') or ''), re.I)
    if m:
        sha = m.group(1).lower()
    side = next((a for a in assets if str(a.get('name', '')).lower().endswith(('.sha256', 'sha256.txt'))), None)
    if side and not sha:
        try:
            m = re.search(r'\b([0-9a-f]{64})\b', fetch(side['browser_download_url']).decode('utf-8', 'replace'), re.I)
            sha = m.group(1).lower() if m else ''
        except Exception:
            pass
    return dict(version=str(data.get('tag_name') or '').lstrip('vV'), url=exe.get('browser_download_url'), sha256=sha,
                name=exe.get('name'), notes=str(data.get('body') or '')[:1500], size=int(exe.get('size') or 0))


def newer(release, current):
    return bool(release) and parse_version(release['version']) > parse_version(current)


def download(release, folder, progress=None, timeout=60):
    """Downloads into folder and checks SHA256; returns the installer path."""
    if not release.get('sha256'):
        raise RuntimeError('Bản phát hành không có mã kiểm SHA256; không cài.')
    folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
    target = folder / re.sub(r'[^\w.\-]', '_', release['name'] or 'NBL_LIVE_Setup.exe')
    part = target.with_suffix('.part')
    h = hashlib.sha256(); done = 0
    with urlopen(Request(release['url'], headers={'User-Agent': 'NBL-LIVE'}), timeout=timeout) as r, open(part, 'wb') as out:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            out.write(chunk); h.update(chunk); done += len(chunk)
            if progress:
                progress(done, release.get('size') or 0)
    if h.hexdigest().lower() != release['sha256']:
        part.unlink(missing_ok=True)
        raise RuntimeError('File tải về sai mã kiểm (hỏng hoặc không phải bản chính thức); đã xóa, không cài.')
    part.replace(target)
    return target


def run_installer(path, app_dir=None):
    """Silent install; the installer waits until NBL has quit, then opens NBL again.

    NBL VIDEO / alarm windows from the same runtime keep python312.dll locked, so they are
    closed first (only called when no LIVE is running or due within 30 minutes; a schedule
    opens NBL VIDEO again by itself). If the installer gives up, NBL is opened again as it was.
    """
    if os.name != 'nt':
        raise RuntimeError('Chỉ cài được trên Windows.')
    app_dir = Path(app_dir or Path(__file__).resolve().parent)
    runtime = str(app_dir / 'runtime').lower()
    ps = ("Get-Process python,pythonw -ErrorAction SilentlyContinue | Where-Object { $_.Id -ne %d -and $_.Path -and "
          "$_.Path.ToLower().StartsWith('%s') } | Stop-Process -Force") % (os.getpid(), runtime.replace("'", "''"))
    no_window = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    try:
        subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', ps], timeout=30, creationflags=no_window)
    except Exception:
        pass
    line = 'start "" /wait "%s" /S /RUN || start "" "%s"' % (path, app_dir / 'NBL_LIVE.exe')
    flags = getattr(subprocess, 'DETACHED_PROCESS', 0) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0) | no_window
    subprocess.Popen('cmd /c "' + line + '"', close_fds=True, creationflags=flags)
