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
    from urllib.parse import urlparse
    low = (urlparse(u).path or '').lower()   # 4.3.5: only the path ("?is_login_callback=1" after logging in is not a login page)
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

    def set_window_state(self, state):
        """4.3.16: thu nhỏ ('minimized') / hiện lại ('normal') các cửa sổ Chrome LIVE của NBL qua DevTools (không chuột).
        Chỉ Chrome riêng của NBL (cổng của nó) — không bao giờ đụng Chrome của chủ máy."""
        browser = {'webSocketDebuggerUrl': self.get('/json/version')['webSocketDebuggerUrl']}
        seen = set(); n = 0
        for p in self.pages():
            if p.get('type') != 'page':
                continue
            try:
                wid = self.call(browser, 'Browser.getWindowForTarget', {'targetId': p['id']}).get('windowId')
            except Exception:
                continue
            if wid is None or wid in seen:
                continue
            seen.add(wid)
            self.call(browser, 'Browser.setWindowBounds', {'windowId': wid, 'bounds': {'windowState': state}}); n += 1
        return n

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

    def __init__(self, profile_dir, pair_url, chrome=None, launcher=None, now=time.time, serve=None, source=None, version=''):
        """serve: bridge.serve(link, hello, label) — 4.3.5: NBL talks to the page itself (no extension).
        source: () -> page code. Without serve (tests / old way) only the tabs are kept in order."""
        self.profile_dir = Path(profile_dir); self.pair_url = pair_url
        self.serve = serve; self.source = source; self.version = version; self.link = None; self.link_thread = None
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
        self.ensure_link(tab, out)
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

    def ensure_link(self, tab, out):
        """One direct line to the kept LIVE tab; a new one when the tab changed or the line died."""
        if not self.serve:
            return
        import threading
        alive = self.link_thread is not None and self.link_thread.is_alive()
        if alive and self.link and self.link.target.get('id') == tab['id']:
            return
        if time.time() - getattr(self, 'link_at', 0) < 10:
            return
        self.link_at = time.time()
        if self.link:
            self.link.close()
        link = PageLink(tab, self.source(), self.version)
        def run():
            try:
                link.open()
            except Exception as e:
                link.close(); out.setdefault('error', 'Chưa nối được trang LIVE: ' + str(e)[:150]); return
            hello = dict(tab=int(tab['id'][:7], 16) if all(c in '0123456789abcdefABCDEF' for c in tab['id'][:7]) else 1, instance=instance_id(self.profile_dir))
            self.serve(link, hello, 'Chrome LIVE')
        self.link = link
        self.link_thread = threading.Thread(target=run, daemon=True, name='nbl-live-page'); self.link_thread.start()
        out['actions'].append('nối trực tiếp trang LIVE')

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



# ---------------- 4.3.5: no extension any more — NBL puts the page code in itself ----------------
SHIM = r"""
(()=>{if(globalThis.__nblShim)return;globalThis.__nblShim=1;globalThis.__nblVersion='__VER__';
const L=[],C=[],P='nbl:';
const rd=k=>{try{const v=localStorage.getItem(P+k);return v==null?undefined:JSON.parse(v);}catch(e){return undefined;}};
const local={
 get:async keys=>{const all=()=>Object.keys(localStorage).filter(k=>k.startsWith(P)).map(k=>k.slice(P.length));
  const ks=keys==null?all():Array.isArray(keys)?keys:typeof keys==='string'?[keys]:Object.keys(keys);const o={};
  for(const k of ks){const v=rd(k);if(v!==undefined)o[k]=v;else if(keys&&typeof keys==='object'&&!Array.isArray(keys))o[k]=keys[k];}return o;},
 set:async obj=>{for(const [k,v] of Object.entries(obj||{})){const old=rd(k);try{localStorage.setItem(P+k,JSON.stringify(v));}catch(e){}for(const f of C){try{f({[k]:{oldValue:old,newValue:v}},'local');}catch(e){}}}},
 remove:async ks=>{for(const k of [].concat(ks))try{localStorage.removeItem(P+k);}catch(e){}}};
const api={runtime:{id:'nbl-live',onMessage:{addListener:f=>L.push(f)},sendMessage:()=>Promise.resolve({ok:false}),getManifest:()=>({version:'__VER__'})},storage:{local,onChanged:{addListener:f=>C.push(f)}}};
try{globalThis.chrome=api;}catch(e){}
if(globalThis.chrome!==api)Object.defineProperty(globalThis,'chrome',{value:api,configurable:true,writable:true});
globalThis.__nblCall=msg=>new Promise(res=>{let done=false,wait=false;const reply=v=>{if(!done){done=true;res(v===undefined?null:v);}};
 for(const f of L){try{if(f(msg,{id:'nbl-live'},reply)===true)wait=true;}catch(e){reply({__error:String(e&&e.message||e)});}}
 if(!wait)setTimeout(()=>reply(undefined),0);setTimeout(()=>reply({__error:'timeout'}),7000);});
})();
"""
WRAP = r"""
(()=>{const ok=()=>location.origin==='https://shop.tiktok.com'&&location.pathname.startsWith('/streamer/live/product/dashboard');
const go=()=>{if(!ok()||globalThis.__nblStarted)return;globalThis.__nblStarted=1;
__CODE__
};
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',go,{once:true});else go();
setInterval(()=>{if(ok()&&document.readyState!=='loading')go();},2000);   // reached by clicking inside the site (no reload)
})();
"""


def page_source(ext_dir, version):
    """The same files the extension used (engine, modules, pin engine, content), with a tiny
    stand-in for the chrome.* calls they make; run in an isolated world like an extension."""
    ext_dir = Path(ext_dir)
    code = '\n;\n'.join((ext_dir / f).read_text(encoding='utf-8') for f in ('engine.js', 'modules.js', 'pin_engine.js', 'content.js'))
    return SHIM.replace('__VER__', version) + WRAP.replace('__CODE__', code)


def instance_id(profile_dir):
    import hashlib
    return hashlib.md5(('nbl-live-chrome:' + str(profile_dir)).encode()).hexdigest()


class PageLink:
    """NBL's direct line to the LIVE tab of its own Chrome. Looks like an extension socket to
    the bridge (send / recv / close): send() takes the tick, recv() returns the page's answer."""
    WORLD = 'nbl'

    def __init__(self, target, source, version, timeout=8):
        import uuid
        self.target = target; self.source = source; self.version = version; self.timeout = timeout
        self.client_id = uuid.uuid4().hex; self.ws = None; self.n = 0; self.ctx = None; self.frame = None
        self.pending = None; self.closed = False; self.worlds = []

    # ---- DevTools ----
    def _event(self, msg):
        m = msg.get('method'); p = msg.get('params') or {}
        if m == 'Runtime.executionContextCreated':
            c = p.get('context') or {}
            if c.get('name') == self.WORLD and (c.get('auxData') or {}).get('frameId') == self.frame:
                self.worlds.append(c.get('id'))   # Chrome may make more than one "nbl" world; the one with our code is picked in find()
        elif m == 'Runtime.executionContextDestroyed':
            cid = p.get('executionContextId')
            self.worlds = [w for w in self.worlds if w != cid]
            if cid == self.ctx:
                self.ctx = None
        elif m == 'Runtime.executionContextsCleared':
            self.ctx = None; self.worlds = []
        elif m in ('Inspector.detached', 'Inspector.targetCrashed'):
            self.closed = True

    def cmd(self, method, params=None, timeout=None):
        if self.closed:
            raise ConnectionError('Tab LIVE đã đóng')
        self.n += 1; n = self.n
        self.ws.send(json.dumps({'id': n, 'method': method, 'params': params or {}}))
        end = time.time() + (timeout or self.timeout)
        while True:
            left = end - time.time()
            if left <= 0:
                raise TimeoutError('Trang LIVE không trả lời (' + method + ')')
            msg = json.loads(self.ws.recv(timeout=left))
            if msg.get('id') == n:
                if 'error' in msg:
                    raise RuntimeError(str(msg['error'].get('message')))
                return msg.get('result') or {}
            self._event(msg)

    def find(self):
        """The isolated world that holds NBL's page code (None while the page is loading)."""
        if self.ctx in self.worlds:
            return self.ctx
        self.ctx = None
        for cid in reversed(self.worlds):
            r = self.cmd('Runtime.evaluate', {'expression': '!!globalThis.__nblShim', 'contextId': cid, 'returnByValue': True}, 3)
            if (r.get('result') or {}).get('value') is True:
                self.ctx = cid; break
        return self.ctx

    def open(self):
        from websockets.sync.client import connect
        self.ws = connect(self.target['webSocketDebuggerUrl'], max_size=16 << 20, open_timeout=self.timeout)
        self.frame = self.cmd('Page.getFrameTree')['frameTree']['frame']['id']
        self.cmd('Page.enable'); self.cmd('Runtime.enable')       # Runtime.enable reports the worlds that exist
        self.cmd('Page.addScriptToEvaluateOnNewDocument', {'source': self.source, 'worldName': self.WORLD})
        if self.find():
            v = self.eval('globalThis.__nblVersion||""')
            if v != self.version:
                self.cmd('Page.reload', {'ignoreCache': True}); self.ctx = None   # code of an older NBL in the page
                return
        else:
            self.ctx = self.cmd('Page.createIsolatedWorld', {'frameId': self.frame, 'worldName': self.WORLD})['executionContextId']
            self.worlds.append(self.ctx); self.eval(self.source)

    def eval(self, expression, timeout=None):
        r = self.cmd('Runtime.evaluate', {'expression': expression, 'contextId': self.ctx, 'awaitPromise': True, 'returnByValue': True}, timeout)
        if r.get('exceptionDetails'):
            raise RuntimeError(str((r['exceptionDetails'].get('exception') or {}).get('description') or r['exceptionDetails'].get('text'))[:300])
        return (r.get('result') or {}).get('value')

    # ---- what the bridge calls ----
    def send(self, text):
        self.pending = json.loads(text)

    def recv(self, timeout=8):
        msg, self.pending = self.pending, None
        cmds = (msg or {}).get('commands') or []
        idle = dict(account='Đang đọc trang', accountVerified=False, modules={}, acks=[], config={})
        try:
            self.cmd('Runtime.evaluate', {'expression': '1'}, 3)   # lets the worlds of a reloaded page arrive
            if not self.find():
                return json.dumps(idle)
            ready = self.eval('typeof __nblCall==="function"&&!!globalThis.__nblStarted', 3)
            if not ready:
                idle.update(account='Chưa mở bảng LIVE', acks=[dict(id=c.get('id'), error='Chưa mở bảng LIVE trong Chrome LIVE.') for c in cmds])
                return json.dumps(idle)
            r = self.eval('__nblCall(' + json.dumps(msg, ensure_ascii=False) + ')', min(timeout, 8))
            if not isinstance(r, dict) or r.get('__error'):
                return json.dumps(idle)
            return json.dumps(r, ensure_ascii=False)
        except (TimeoutError, RuntimeError):
            return json.dumps(idle)

    def close(self, *a):
        self.closed = True
        try:
            if self.ws:
                self.ws.close()
        except Exception:
            pass
