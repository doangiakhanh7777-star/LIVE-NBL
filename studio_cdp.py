"""4.2.1 (owner, 28/10/2026): drive TikTok LIVE Studio from the inside, like the app
the owner showed — no regions, no window picking, no mouse, works with the screen
locked or off.

NBL starts Studio with Chromium's debugging port on 127.0.0.1 (never reachable from
another machine) and reads/clicks Studio's own page elements through the DevTools
protocol. Measured on Studio 1.38.0 (NBL_DO_STUDIO, 28/10/2026):

  main window  html/main/index.html
    [data-testid=main-start-live-button]   "Phát LIVE" (idle)
    button.live-btn-*  + .living-*          LIVE; child .live-btn-duration-* = 00:00:17
    .tt-live-dropdown-option-label          "Kết thúc LIVE" / "Tạm dừng LIVE"
    [class*=nickname-]                      "Khánh Car Auto"
    .d-performance-item-key/-val            "Tải lên:" "1825 kbps", "FPS:" "30/30"
    .tt-live-editor-textarea + [aria-label="Gửi bình luận"]   comment box
  launch page  button._go-live-button_*     opens the studio screen (not the broadcast)

Nothing here clicks anything until the nick shown in Studio is the nick of the
schedule. Every refusal before a click raises NotTouched.
"""
import json
import os
import re
import subprocess
import time
import unicodedata
from pathlib import Path
from urllib.request import urlopen

from studio_vision_logic import NotTouched, same_author

BASE_PORT = 9339
LOG_DIR = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local/share'))) / 'NBL_LIVE_2' / 'logs'

STATE_JS = r"""(() => {
 const vis = el => { if (!el) return false; const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
 const btn = document.querySelector('[data-testid="main-start-live-button"]') || [...document.querySelectorAll('button')].find(b => /(^|\s)live-btn-/.test(b.className));
 const dur = btn ? btn.querySelector('[class*="live-btn-duration"]') : null;
 const durText = dur ? dur.innerText.trim() : '';
 const text = btn ? btn.innerText.trim() : '';
 const living = !!btn && (/(^|\s)living-/.test(btn.className) || /^\d{1,2}:\d{2}:\d{2}$/.test(durText));
 const nick = [...document.querySelectorAll('[class*="nickname-"]')].map(n => n.innerText.trim()).find(Boolean) || '';
 const perf = {};
 document.querySelectorAll('[class*="d-performance-item-key"]').forEach(k => { const v = k.nextElementSibling; perf[k.innerText.trim()] = v ? v.innerText.trim() : ''; });
 const launch = [...document.querySelectorAll('button[class*="_go-live-button"]')].some(vis);
 const dialogs = [...document.querySelectorAll('[role="dialog"], .tt-live-modalV4')].filter(vis).map(d => ({
   text: d.innerText.replace(/\s+/g, ' ').slice(0, 300),
   buttons: [...d.querySelectorAll('button')].filter(vis).map(b => (b.innerText || b.getAttribute('aria-label') || '').trim()).slice(0, 12)}));
 const menu = [...document.querySelectorAll('.tt-live-dropdown-option-label')].filter(vis).map(o => o.innerText.trim());
 const editor = [...document.querySelectorAll('.tt-live-editor-textarea')].find(vis);
 return {hasButton: !!btn, buttonText: text, living, duration: durText, idle: !!btn && !living && /phát live|go live/i.test(text),
         buttonDisabled: !!btn && !!btn.disabled, launch, nickname: nick, perf, dialogs, menu, chat: !!editor, url: location.href};
})()"""

# returns the centre of the first visible element that matches, or null
FIND_JS = r"""((kind, pattern) => {
 const vis = el => { if (!el) return false; const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
 const re = pattern ? new RegExp(pattern, 'i') : null;
 let el = null;
 if (kind === 'live-button') el = document.querySelector('[data-testid="main-start-live-button"]') || [...document.querySelectorAll('button')].find(b => /(^|\s)live-btn-/.test(b.className));
 if (kind === 'launch') el = [...document.querySelectorAll('button[class*="_go-live-button"]')].find(vis);
 if (kind === 'menu') { const l = [...document.querySelectorAll('.tt-live-dropdown-option-label')].filter(vis).find(o => re.test(o.innerText.trim())); el = l ? (l.closest('.tt-live-dropdown-option') || l) : null; }
 if (kind === 'dialog-button') {
   for (const d of [...document.querySelectorAll('[role="dialog"], .tt-live-modalV4')].filter(vis)) {
     const b = [...d.querySelectorAll('button')].filter(vis).find(b => re.test((b.innerText || '').trim()));
     if (b) { el = b; break; }
   }
 }
 if (kind === 'editor') el = [...document.querySelectorAll('.tt-live-editor-textarea')].find(vis);
 if (kind === 'send') el = [...document.querySelectorAll('[aria-label="Gửi bình luận"], [aria-label="Send comment"], .tt-live-comment-input-post-button')].find(b => vis(b) && !/disabled/.test(b.className));
 if (!vis(el)) return null;
 el.scrollIntoView({block: 'center', inline: 'center'});
 const r = el.getBoundingClientRect();
 return {x: r.x + r.width / 2, y: r.y + r.height / 2, text: (el.innerText || '').trim().slice(0, 60)};
})"""

END_PAGE_JS = r"""(() => {
 const vis = el => { if (!el) return false; const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
 return [...document.querySelectorAll('[role="dialog"], .tt-live-modalV4, [class*="summary"], [class*="Summary"], [class*="end-live"], [class*="endLive"]')].filter(vis).map(d => ({
   cls: String(d.className).slice(0, 120), text: d.innerText.replace(/\s+/g, ' ').slice(0, 500),
   buttons: [...d.querySelectorAll('button')].filter(vis).map(b => ({text: (b.innerText || '').trim(), label: b.getAttribute('aria-label') || '', cls: String(b.className).slice(0, 80)})).slice(0, 15)}));
})()"""

CLOSE_END_JS = r"""(() => {
 const vis = el => { if (!el) return false; const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
 const isEnd = t => /tổng kết|tóm tắt|phiên live đã kết thúc|live đã kết thúc|đã kết thúc live|live summary|live ended|thời lượng/i.test(t);
 for (const d of [...document.querySelectorAll('[role="dialog"], .tt-live-modalV4')].filter(vis)) {
   if (!isEnd(d.innerText)) continue;
   const b = [...d.querySelectorAll('button')].filter(vis).find(b => /^(đóng|xong|ok|close|done)$/i.test((b.innerText || '').trim()) || /close|đóng/i.test(b.getAttribute('aria-label') || '') || /close/i.test(String(b.className)));
   if (b) { b.click(); return {seen: true, closed: true}; }
   return {seen: true, closed: false};
 }
 return {seen: false, closed: false};
})()"""


def plain(text):
    t = unicodedata.normalize('NFD', str(text or ''))
    return ''.join(c for c in t if unicodedata.category(c) != 'Mn').replace('đ', 'd').replace('Đ', 'D').lower()


class Studio:
    def __init__(self, port, timeout=10):
        self.port = int(port); self.timeout = timeout

    # ---- transport ----
    def get(self, path):
        with urlopen('http://127.0.0.1:%d%s' % (self.port, path), timeout=3) as r:
            return json.loads(r.read().decode('utf-8'))

    def alive(self):
        try:
            self.get('/json/version'); return True
        except Exception:
            return False

    def pages(self):
        return [t for t in self.get('/json/list') if t.get('type') == 'page' and t.get('webSocketDebuggerUrl')]

    def page(self, part):
        for t in self.pages():
            if part in t.get('url', ''):
                return t
        return None

    def call(self, target, calls):
        """Run several DevTools commands on one page; returns their results."""
        from websockets.sync.client import connect
        out = []
        with connect(target['webSocketDebuggerUrl'], max_size=16 * 1024 * 1024, open_timeout=self.timeout) as ws:
            for n, (method, params) in enumerate(calls, 1):
                ws.send(json.dumps({'id': n, 'method': method, 'params': params or {}}))
                while True:
                    msg = json.loads(ws.recv(timeout=self.timeout))
                    if msg.get('id') == n:
                        if 'error' in msg:
                            raise RuntimeError('Studio: ' + str(msg['error'].get('message')))
                        out.append(msg.get('result') or {}); break
        return out

    def js(self, target, expression):
        r = self.call(target, [('Runtime.evaluate', {'expression': expression, 'returnByValue': True, 'awaitPromise': True})])[0]
        if r.get('exceptionDetails'):
            raise RuntimeError('Studio JS: ' + str(r['exceptionDetails'].get('text')))
        return (r.get('result') or {}).get('value')

    def click(self, target, kind, pattern=''):
        """Click inside the page (DevTools mouse event, not the Windows mouse)."""
        spot = self.js(target, FIND_JS + '(' + json.dumps(kind) + ',' + json.dumps(pattern) + ')')
        if not spot:
            return None
        base = {'x': spot['x'], 'y': spot['y'], 'button': 'left', 'clickCount': 1}
        self.call(target, [('Input.dispatchMouseEvent', {**base, 'type': 'mouseMoved'}),
                           ('Input.dispatchMouseEvent', {**base, 'type': 'mousePressed'}),
                           ('Input.dispatchMouseEvent', {**base, 'type': 'mouseReleased'})])
        return spot

    # ---- reading ----
    def main(self):
        t = self.page('/html/main/')
        if not t:
            raise NotTouched('Studio đang mở nhưng chưa có cửa sổ chính (còn đang khởi động?); chưa bấm gì.')
        return t

    def state(self):
        t = self.main(); s = self.js(t, STATE_JS) or {}
        s['health'] = health(s.get('perf') or {})
        return t, s

    def check_nick(self, s, expected):
        nick = s.get('nickname') or ''
        if not nick:
            raise NotTouched('Chưa đọc được tên nick trên Studio (Studio đang ở trang chủ?); chưa bấm gì.')
        if expected and not same_author(nick, expected):
            raise NotTouched('Studio đang là nick "' + nick + '", không phải "' + expected + '"; chưa bấm gì.')
        return nick

    def open_studio_screen(self):
        """Studio sits on its home page after starting: its big 'Phát LIVE' only opens
        the studio screen (the broadcast needs the second Phát LIVE)."""
        t, s = self.state()
        if s.get('hasButton') or not s.get('launch'):
            return t, s
        self.click(t, 'launch')
        for _ in range(20):
            time.sleep(1)
            t, s = self.state()
            if s.get('hasButton'):
                return t, s
        raise NotTouched('Bấm vào màn hình phát của Studio nhưng chưa thấy nút Phát LIVE.')

    # ---- actions ----
    def status(self, expected=''):
        t, s = self.state()
        if s.get('nickname') and expected and not same_author(s['nickname'], expected):
            raise NotTouched('Studio đang là nick "' + s['nickname'] + '", không phải "' + expected + '".')
        if not s.get('hasButton') and not s.get('launch'):
            raise NotTouched('Chưa đọc được trạng thái LIVE trên Studio.')
        return dict(live=bool(s.get('living')), duration=s.get('duration', ''), health=s['health'], nickname=s.get('nickname', ''), method='cdp')

    def start(self, expected):
        t, s = self.open_studio_screen()
        if s.get('living'):
            self.check_nick(s, expected)
            return dict(live=True, already=True, confirmed=True, method='cdp')
        if not s.get('idle'):
            raise NotTouched('Chưa thấy nút "Phát LIVE" sẵn sàng trên Studio; chưa bấm gì.')
        if s.get('buttonDisabled'):
            raise NotTouched('Nút "Phát LIVE" của Studio đang mờ (chưa cho phát); chưa bấm gì.')
        self.check_nick(s, expected)
        self.click(t, 'live-button')
        confirmed = False
        for _ in range(30):
            time.sleep(1)
            t, s = self.state()
            if s.get('living'):
                confirmed = True; break
            # Studio may ask once more before going on air: only a button that says
            # exactly "Phát LIVE" / "Go LIVE" inside that box is pressed.
            if s.get('dialogs') and self.click(t, 'dialog-button', r'^(phát live|go live)$'):
                continue
        if not confirmed:
            boxes = '; '.join(d.get('text', '')[:120] for d in s.get('dialogs') or [])
            error = ValueError('Đã bấm Phát LIVE nhưng sau 30 giây chưa thấy đồng hồ LIVE chạy' + (' · Studio đang hiện: ' + boxes if boxes else ''))
            error.touched = True
            raise error
        return dict(live=True, confirmed=True, method='cdp')

    def stop(self, expected):
        t, s = self.state()
        if not s.get('hasButton') and not s.get('launch'):
            raise NotTouched('Chưa đọc được trạng thái LIVE trên Studio; chưa bấm kết thúc.')
        if not s.get('living'):
            self.dump_end_page('sau_ket_thuc')
            return dict(live=False, already=True, confirmed=True, method='cdp')
        self.check_nick(s, expected)
        self.click(t, 'live-button')                         # opens the small menu
        time.sleep(.8)
        if not self.click(t, 'menu', r'^(kết thúc live|end live)$'):
            t, s = self.state()
            raise NotTouched('Bấm đồng hồ LIVE nhưng chưa thấy dòng "Kết thúc LIVE" (menu: ' + ', '.join(s.get('menu') or []) + '); chưa kết thúc.')
        pressed = False
        for _ in range(10):
            time.sleep(.6)
            if self.click(t, 'dialog-button', r'^(kết thúc ngay|end now|kết thúc|end)$'):
                pressed = True; break
            if not self.state()[1].get('living'):
                break
        for _ in range(25):
            time.sleep(1)
            t, s = self.state()
            if not s.get('living'):
                self.dump_end_page('sau_ket_thuc')
                closed = self.close_end_page()
                return dict(live=False, confirmed=True, method='cdp', summaryOpen=closed.get('seen') and not closed.get('closed'))
        error = ValueError('Đã chọn Kết thúc LIVE' + (' và Kết thúc ngay' if pressed else '') + ' nhưng Studio vẫn đang LIVE sau 25 giây.')
        error.touched = True
        raise error

    def close_end_page(self):
        result = dict(seen=False, closed=False)
        try:
            for t in self.pages():
                r = self.js(t, CLOSE_END_JS) or {}
                result['seen'] = result['seen'] or bool(r.get('seen')); result['closed'] = result['closed'] or bool(r.get('closed'))
        except Exception:
            pass
        return result

    def dump_end_page(self, label):
        """The end page of a LIVE was not measured yet: keep what Studio shows after
        the first real ends (for the next version), never more than 5 files."""
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            old = sorted(LOG_DIR.glob('studio_trang_ket_thuc_*.json'))
            if len(old) >= 5:
                return
            data = []
            for t in self.pages():
                try:
                    data.append(dict(url=t.get('url', '')[-60:], boxes=self.js(t, END_PAGE_JS)))
                except Exception as e:
                    data.append(dict(url=t.get('url', '')[-60:], error=str(e)))
            (LOG_DIR / ('studio_trang_ket_thuc_' + time.strftime('%Y%m%d_%H%M%S') + '.json')).write_text(json.dumps(dict(label=label, pages=data), ensure_ascii=False, indent=1), encoding='utf-8')
        except Exception:
            pass

    def chat_page(self):
        for part in ('/html/main/', '/html/liveChatFloat/'):
            t = self.page(part)
            if t and self.js(t, FIND_JS + '("editor","")'):
                return t
        return None

    def chat_check(self):
        t = self.chat_page()
        return dict(ok=bool(t), live=bool(self.state()[1].get('living')), method='cdp')

    def send(self, text, expected):
        t0, s = self.state()
        if not s.get('living'):
            raise NotTouched('Chưa LIVE; chưa gửi tin.')
        self.check_nick(s, expected)
        t = self.chat_page()
        if not t:
            raise NotTouched('Chưa thấy ô bình luận của Studio; chưa gửi.')
        if not self.click(t, 'editor'):
            raise NotTouched('Chưa bấm được vào ô bình luận; chưa gửi.')
        self.call(t, [('Input.insertText', {'text': text})])
        time.sleep(.3)
        typed = self.js(t, '(() => { const e=[...document.querySelectorAll(".tt-live-editor-textarea")].find(x=>x.getBoundingClientRect().width>0); return e ? e.innerText.trim() : ""; })()') or ''
        if plain(typed) != plain(text).strip():
            self.js(t, '(() => { const e=[...document.querySelectorAll(".tt-live-editor-textarea")].find(x=>x.getBoundingClientRect().width>0); if(e){e.focus(); document.execCommand("selectAll"); document.execCommand("delete");} })()')
            raise NotTouched('Ô bình luận không nhận đúng chữ; đã xóa, chưa gửi.')
        if not self.click(t, 'send'):
            self.call(t, [('Input.dispatchKeyEvent', {'type': 'keyDown', 'key': 'Enter', 'code': 'Enter', 'windowsVirtualKeyCode': 13}),
                          ('Input.dispatchKeyEvent', {'type': 'keyUp', 'key': 'Enter', 'code': 'Enter', 'windowsVirtualKeyCode': 13})])
        for _ in range(10):
            time.sleep(.3)
            left = self.js(t, '(() => { const e=[...document.querySelectorAll(".tt-live-editor-textarea")].find(x=>x.getBoundingClientRect().width>0); return e ? e.innerText.trim() : ""; })()') or ''
            if not left:
                return dict(sent=True, confirmed=True, method='cdp')
        error = ValueError('Đã bấm gửi nhưng chữ vẫn còn trong ô bình luận.')
        error.touched = True
        raise error


def health(perf):
    up = fps = None
    for key, value in perf.items():
        k = plain(key)
        if 'tai len' in k or 'upload' in k:
            m = re.search(r'(\d+)', value); up = int(m.group(1)) if m else None
        if 'fps' in k:
            m = re.search(r'(\d+)\s*/', value); fps = int(m.group(1)) if m else None
    return dict(upload=up, fps=fps)


# ---- starting Studio with the port ----
def running_studio(exe):
    if os.name != 'nt':
        return False
    name = Path(exe).name.lower()
    try:
        out = subprocess.run(['tasklist', '/FO', 'CSV', '/NH'], capture_output=True, text=True, errors='replace',
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).stdout.lower()
    except Exception:
        return False
    return ('"' + name + '"') in out


def launch(exe, port, wait=90):
    if not exe or not Path(exe).is_file():
        raise NotTouched('Không thấy file TikTok LIVE Studio: ' + str(exe))
    flags = 0
    for f in ('DETACHED_PROCESS', 'CREATE_NEW_PROCESS_GROUP', 'CREATE_NO_WINDOW'):
        flags |= getattr(subprocess, f, 0)
    subprocess.Popen([exe, '--remote-debugging-port=%d' % port, '--remote-allow-origins=http://127.0.0.1:%d' % port],
                     cwd=str(Path(exe).parent), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=flags, close_fds=True)
    studio = Studio(port)
    end = time.time() + wait
    while time.time() < end:
        time.sleep(1)
        if studio.alive():
            try:
                if studio.page('/html/main/'):
                    return studio
            except Exception:
                pass
    raise NotTouched('Đã mở TikTok LIVE Studio nhưng sau ' + str(wait) + ' giây chưa kết nối được (Studio có chặn không?).')


def connect(exe, port, other_ports=(), open_if_closed=True):
    """The Studio of this nick, opening it with the port when it is not running."""
    studio = Studio(port)
    if studio.alive():
        return studio
    if not open_if_closed:
        return None
    if running_studio(exe) and not any(Studio(p).alive() for p in other_ports):
        raise NotTouched('TikTok LIVE Studio đang mở nhưng KHÔNG phải do NBL mở, nên NBL chưa đọc được. Đóng hẳn Studio (khi không LIVE); NBL sẽ tự mở lại.')
    return launch(exe, port)


def find_exe(hint=''):
    cands = [hint] if hint else []
    for base in (os.environ.get('ProgramFiles', ''), os.environ.get('ProgramFiles(x86)', ''), os.environ.get('LOCALAPPDATA', '') + r'\Programs'):
        cands.append(str(Path(base) / 'TikTok LIVE Studio' / 'TikTok LIVE Studio.exe'))
    for c in cands:
        if c and Path(c).is_file():
            return c
    return ''


def execute_cdp(profile, action, deadline=0, payload=None):
    """Same results as the image path (studio_vision.execute_vision) for the actions it covers."""
    port = int(profile.get('cdpPort') or BASE_PORT)
    expected = profile.get('accountName') or profile.get('name') or ''
    others = [int(p) for p in profile.get('_otherPorts') or []]
    if action in ('status', 'stop', 'close_summary', 'probe', 'chat_check', 'send'):
        studio = connect(profile.get('exePath'), port, others, open_if_closed=False)
        if studio is None:
            if action == 'probe':
                return dict(windowFound=False)
            if running_studio(profile.get('exePath')) and not any(Studio(p).alive() for p in others):
                raise NotTouched('TikTok LIVE Studio đang mở nhưng không phải do NBL mở; NBL chưa đọc được nick này.')
            if action in ('status', 'stop', 'close_summary'):
                return dict(live=False, studioClosed=True, closed=True, method='cdp')
            raise NotTouched('TikTok LIVE Studio chưa mở; chưa gửi.')
    else:
        studio = connect(profile.get('exePath'), port, others, open_if_closed=True)
    if action == 'probe':
        return dict(windowFound=True)
    if action == 'status':
        return studio.status(expected)
    if action == 'start':
        return studio.start(expected)
    if action == 'stop':
        return studio.stop(expected)
    if action == 'close_summary':
        r = studio.close_end_page()
        return dict(closed=not r['seen'] or r['closed'], seen=r['seen'], method='cdp')
    if action == 'chat_check':
        return studio.chat_check()
    if action == 'send':
        return studio.send(str((payload or {}).get('text', '')), expected)
    if action == 'connect':
        t, s = studio.state()
        return dict(nickname=s.get('nickname', ''), live=bool(s.get('living')), home=bool(s.get('launch')) and not s.get('hasButton'), port=port)
    raise NotTouched('Kết nối tự động chưa làm mục này: ' + action)


CDP_ACTIONS = ('probe', 'status', 'start', 'stop', 'close_summary', 'chat_check', 'send', 'connect')
