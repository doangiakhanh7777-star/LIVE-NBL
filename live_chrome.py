"""4.3.4 (owner, 29/10/2026): "Chrome riêng của NBL" — a separate Chrome only for the LIVE.

NBL starts its own Chrome (own profile folder in the NBL data folder, nothing shared with the
owner's normal Chrome) with a DevTools port on 127.0.0.1 and keeps it in order by itself:
exactly one TikTok Shop LIVE dashboard tab, extra ones closed, a frozen / orphaned page
reloaded, Chrome reopened when it was closed. The owner logs in once and installs the NBL
extension once in that window. The tab -> NBL link is exact: the extension writes the id of
its NBL connection into the page (data-nbl-client) and NBL reads it through the DevTools port.
No mouse, no keyboard, no reading of the owner's other browser.

Pure Python (no Qt): Watchdog.step() is run off the Qt thread every few seconds.
"""
import json
import os
import subprocess
import time
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

PORT = 9340
DASHBOARD = 'https://shop.tiktok.com/streamer/live/product/dashboard'
HEARTBEAT_JS = ("(()=>{const d=document.documentElement;return {url:location.href,ready:document.readyState,"
                "client:d.getAttribute('data-nbl-client')||'',beat:+(d.getAttribute('data-nbl-beat')||0),now:Date.now(),"
                "login:/\\/(login|account\\/register)|passport/.test(location.href)||!!document.querySelector('input[type=password]')}})()")


def chrome_exe():
    for base in (os.environ.get('ProgramFiles', ''), os.environ.get('ProgramFiles(x86)', ''), os.environ.get('LOCALAPPDATA', '')):
        p = Path(base) / 'Google' / 'Chrome' / 'Application' / 'chrome.exe'
        if base and p.is_file():
            return p
    return None


def is_dashboard(url):
    return str(url or '').split('#')[0].split('?')[0].rstrip('/') == DASHBOARD


def host_of(url):
    try:
        from urllib.parse import urlparse
        return (urlparse(str(url)).hostname or '').lower()
    except Exception:
        return ''


def kind(url):
    """'dashboard' | 'login' (TikTok page where the owner must log in / the not-logged-in landing,
    never touched by NBL) | 'tiktok' (other TikTok page after logging in) | 'blank' | 'other'."""
    u = str(url or ''); h = host_of(u)
    if is_dashboard(u):
        return 'dashboard'
    if u.startswith(('chrome://newtab', 'chrome://new-tab-page', 'about:blank')) or u in ('', 'about:blank'):
        return 'blank'
    tik = h.endswith(('tiktok.com', 'tiktokshop.com', 'tiktokglobalshop.com', 'tiktokcdn.com', 'tiktokv.com', 'byteoversea.com'))
    if not tik:
        return 'other'
    low = u.lower()
    # not logged in: shop.tiktok.com sends the dashboard to business.tiktokshop.com/…/creator/live
    if h.startswith('business.') or any(k in low for k in ('login', 'passport', 'register', 'signup', 'oauth', 'verify', 'captcha', '/account/')):
        return 'login'
    return 'tiktok'


def is_tiktok(url):
    return kind(url) in ('login', 'tiktok', 'dashboard')


class Chrome:
    """The DevTools port of NBL's own Chrome."""
    def __init__(self, port=PORT, timeout=4):
        self.port = port; self.timeout = timeout

    def get(self, path, method='GET'):
        with urlopen(Request('http://127.0.0.1:%d%s' % (self.port, path), method=method), timeout=self.timeout) as r:
            body = r.read().decode('utf-8', 'replace')
        try:
            return json.loads(body)
        except ValueError:
            return body

    def alive(self):
        try:
            return bool(self.get('/json/version'))
        except Exception:
            return False

    def pages(self):
        return [t for t in self.get('/json/list') if t.get('type') == 'page']

    def open(self, url):
        return self.get('/json/new?' + quote(url, safe=':/?#=&'), method='PUT')

    def close(self, target_id):
        return self.get('/json/close/' + target_id)

    def activate(self, target_id):
        return self.get('/json/activate/' + target_id)

    def call(self, target, method, params=None):
        from websockets.sync.client import connect
        with connect(target['webSocketDebuggerUrl'], max_size=4 << 20, open_timeout=self.timeout) as ws:
            ws.send(json.dumps({'id': 1, 'method': method, 'params': params or {}}))
            while True:
                msg = json.loads(ws.recv(timeout=self.timeout))
                if msg.get('id') == 1:
                    if 'error' in msg:
                        raise RuntimeError(str(msg['error'].get('message')))
                    return msg.get('result') or {}

    def quit(self):
        """Close NBL's Chrome (the watchdog opens it again with fresh extension files)."""
        try:
            self.call({'webSocketDebuggerUrl': self.get('/json/version')['webSocketDebuggerUrl']}, 'Browser.close')
        except Exception:
            pass

    def page_state(self, target):
        r = self.call(target, 'Runtime.evaluate', {'expression': HEARTBEAT_JS, 'returnByValue': True})
        return (r.get('result') or {}).get('value') or {}

    def navigate(self, target, url):
        return self.call(target, 'Page.navigate', {'url': url})

    def reload(self, target):
        """A real reload: Page.navigate to the same address + #nbl=… is only a jump inside the
        page (the extension is not loaded again); the extension pairs a reloaded tab by itself."""
        return self.call(target, 'Page.reload', {'ignoreCache': True})


def launch(profile_dir, url, port=PORT, exe=None, extra=()):
    exe = exe or chrome_exe()
    if not exe:
        raise RuntimeError('Không tìm thấy Google Chrome trên máy (cần cài Chrome).')
    Path(profile_dir).mkdir(parents=True, exist_ok=True)
    args = [str(exe), '--user-data-dir=' + str(profile_dir), '--remote-debugging-port=%d' % port,
            '--remote-allow-origins=http://127.0.0.1:%d' % port, '--no-first-run', '--no-default-browser-check',
            '--disable-features=CalculateNativeWinOcclusion', '--disable-background-timer-throttling',
            '--disable-renderer-backgrounding', '--disable-backgrounding-occluded-windows', *extra, '--new-window', url]
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0) | getattr(subprocess, 'DETACHED_PROCESS', 0)
    subprocess.Popen(args, creationflags=flags, close_fds=True)


class Watchdog:
    """Keeps NBL's Chrome in order. step() returns a report dict; it never touches another Chrome.

    state: 'off' (not started yet), 'starting', 'login' (TikTok asks to log in), 'no_extension'
    (the NBL extension is not installed in this Chrome), 'loading', 'ok'.
    """
    STALE = 25          # s without a heartbeat from the extension -> page considered frozen
    RELOAD_GAP = 60     # s between two reloads of the dashboard
    START_WAIT = 45     # s to wait after starting Chrome before judging it

    def __init__(self, profile_dir, pair_url, chrome=None, launcher=None, now=time.time):
        self.profile_dir = Path(profile_dir); self.pair_url = pair_url
        self.chrome = chrome or Chrome(); self.launcher = launcher or launch; self.now = now
        self.started_at = 0; self.reload_at = 0; self.opened_at = 0; self.loaded = {}
        self.no_beat_reloads = 0; self.wanted = False

    def setup_done(self):
        return (self.profile_dir / 'nbl_setup_ok').exists()

    def mark_setup(self):
        self.profile_dir.mkdir(parents=True, exist_ok=True); (self.profile_dir / 'nbl_setup_ok').write_text('1')

    def start(self):
        self.wanted = True
        if not self.chrome.alive():
            self.launcher(self.profile_dir, self.pair_url()); self.started_at = self.opened_at = self.now()

    def step(self, busy=False):
        """busy: pinning / cart running — never reload a page that still answers."""
        now = self.now(); out = dict(state='off', client='', actions=[])
        if not self.chrome.alive():
            if not (self.wanted or self.setup_done()):
                return out
            if now - self.started_at > self.START_WAIT:
                self.launcher(self.profile_dir, self.pair_url()); self.started_at = self.opened_at = now; out['actions'].append('mở Chrome LIVE')
            out['state'] = 'starting'; return out
        pages = self.chrome.pages()
        dash = [p for p in pages if is_dashboard(p.get('url'))]
        states = {}
        for p in dash:
            try:
                states[p['id']] = self.chrome.page_state(p)
            except Exception:
                states[p['id']] = {}
            self.loaded.setdefault(p['id'], now)
        # the tab NBL keeps: the one that is linked, else the oldest seen
        linked = [p for p in dash if states[p['id']].get('client')]
        keep = (linked or sorted(dash, key=lambda p: self.loaded[p['id']]))[:1]
        for p in dash:
            if keep and p['id'] != keep[0]['id']:
                try:
                    self.chrome.close(p['id']); out['actions'].append('đóng tab LIVE dư')
                except Exception:
                    pass
        if not keep:
            # 4.3.4 vá 1 (owner, 29/10 03:22): not logged in, TikTok sends the dashboard to its
            # landing page; NBL used to open another dashboard tab every 30 s. Now: a TikTok
            # page where the owner logs in is never touched and NO new tab is opened; duplicates
            # of the same page are closed; a logged-in TikTok page / New Tab is turned into the
            # dashboard (the same tab, at most once every 2 minutes).
            seen = set()
            for p in pages:
                k = kind(p.get('url'))
                if k in ('login', 'tiktok'):
                    key = str(p.get('url')).split('#')[0]
                    if key in seen:
                        try:
                            self.chrome.close(p['id']); out['actions'].append('đóng tab trùng')
                        except Exception:
                            pass
                        continue
                    seen.add(key)
            pages = [p for p in self.chrome.pages()]
            login = [p for p in pages if kind(p.get('url')) == 'login' or kind(p.get('url')) == 'tiktok' and self._login(p)]
            if login:
                out['state'] = 'login'; return out
            target = next((p for p in pages if kind(p.get('url')) == 'tiktok'), None) or next((p for p in pages if kind(p.get('url')) == 'blank'), None)
            if now - self.opened_at >= 120:
                try:
                    if target:
                        self.chrome.navigate(target, self.pair_url()); out['actions'].append('chuyển tab sang trang LIVE')
                    elif not [p for p in pages if kind(p.get('url')) != 'other']:
                        self.chrome.open(self.pair_url()); out['actions'].append('mở trang LIVE')
                    self.opened_at = now
                except Exception as e:
                    out['error'] = str(e)
            out['state'] = 'loading'; return out
        tab = keep[0]; st = states[tab['id']]
        if st.get('login'):
            out['state'] = 'login'; return out
        beat_age = (st.get('now', 0) - st.get('beat', 0)) / 1000 if st.get('beat') else None
        age = now - self.loaded.get(tab['id'], now)
        if st.get('client') and beat_age is not None and beat_age < self.STALE:
            self.no_beat_reloads = 0
            out.update(state='ok', client=st['client']); return out
        # no (fresh) heartbeat: page frozen, orphaned after the extension reloaded, or no extension
        if age < self.START_WAIT or now - max(self.reload_at, self.started_at) < self.START_WAIT:
            out['state'] = 'loading'; return out
        if self.no_beat_reloads >= 2 and not st.get('beat'):
            out['state'] = 'no_extension'
            if now - self.reload_at < 300:
                return out
        if busy and st.get('beat') and beat_age is not None and beat_age < self.STALE * 2:
            out['state'] = 'loading'; return out
        if now - self.reload_at >= self.RELOAD_GAP:
            try:
                self.chrome.reload(tab); self.reload_at = now; self.loaded[tab['id']] = now
                self.no_beat_reloads += 1; out['actions'].append('tải lại trang LIVE (trang không trả lời)')
            except Exception as e:
                out['error'] = str(e)
        if out['state'] != 'no_extension':
            out['state'] = 'loading'
        return out

    def _login(self, page):
        try:
            return bool(self.chrome.page_state(page).get('login'))
        except Exception:
            return False

    def reload_now(self):
        """Fresh page before a LIVE (called by the schedule; the same tab, never a new one)."""
        dash = [p for p in self.chrome.pages() if is_dashboard(p.get('url'))]
        if not dash:
            return False
        self.chrome.reload(dash[0]); self.reload_at = self.now(); self.loaded[dash[0]['id']] = self.reload_at
        return True

    def show_setup(self, extension_dir):
        """One-time: open chrome://extensions in NBL's Chrome (the owner loads the extension folder)."""
        self.start()
        for _ in range(20):
            if self.chrome.alive():
                break
            time.sleep(.5)
        try:
            self.chrome.open('chrome://extensions/')
        except Exception:
            pass
