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


class StudioChanged(NotTouched):
    """Studio answers but its buttons are not where NBL knows them (new Studio version?)."""

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
 // Measured 28/10/2026: the end page is a full-window dialog (.tt-live-modalV4, role=dialog)
 // with "Thời lượng: 00:06:36"; its close X has no text and sits in [class*=_title-bar-buttons].
 const vis = el => { if (!el) return false; const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
 const isEnd = t => /thời lượng\s*:|tổng kết|tóm tắt|phiên live đã kết thúc|live đã kết thúc|live summary|live ended|duration\s*:/i.test(t);
 for (const d of [...document.querySelectorAll('[role="dialog"], .tt-live-modalV4')].filter(vis)) {
   if (!isEnd(d.innerText)) continue;
   let b = [...d.querySelectorAll('[class*="_title-bar-buttons"] button, [class*="title-bar-buttons"] button')].filter(vis).find(b => !(b.innerText || '').trim());
   if (!b) b = [...d.querySelectorAll('button')].filter(vis).find(b => /^(đóng|xong|ok|close|done)$/i.test((b.innerText || '').trim()) || /close|đóng/i.test(b.getAttribute('aria-label') || '') || /close/i.test(String(b.className)));
   if (b) { b.click(); return {seen: true, closed: true}; }
   return {seen: true, closed: false};
 }
 return {seen: false, closed: false};
})()"""

# Measured 28/10/2026 (chat window html/liveChatFloat, also #live-chat in the main window):
# a comment = element id "-ChatMsg-<n>" holding the name (.username-*), its text in
# [class*=msg-content-] .text. Joins ("đã tham gia") and likes have no -ChatMsg- id.
CHAT_JS = r"""(() => {
 const out = [];
 for (const el of document.querySelectorAll('[id^="-ChatMsg-"]')) {
   const box = el.parentElement || el;
   const u = el.querySelector('[class*="username-"]') || el;
   const t = box.querySelector('[class*="msg-content-"] .text') || box.querySelector('[class*="msg-content-"]');
   const user = (u.innerText || '').trim(), text = t ? (t.innerText || '').trim() : '';
   if (user && text) out.push({id: el.id.replace('-ChatMsg-', ''), user: user.slice(0, 80), text: text.slice(0, 300)});
 }
 return out.slice(-60);
})()"""

# 4.3.8 (owner 29/10 04:37): the "Trò chuyện LIVE" window can float over the chat/input.
# NBL docks it back WITHOUT the mouse — a CDP in-page click on the merge button, found only
# by its own label (never the close/settings icon), so a wrong element is never clicked.
DOCK_JS = r"""(() => {
 const vis = el => { if (!el) return false; const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0 && r.top < 90; };
 const label = el => (el.getAttribute('aria-label') || el.getAttribute('title') || el.getAttribute('data-tooltip') || el.getAttribute('alt') || '').trim();
 const MERGE = /ghép|gộp|hợp nhất|thu về|gắn lại|đưa về|về studio|dock|merge|combine|attach|re-?dock|embed/i;
 const AVOID = /đóng|close|thoát|exit|tắt|cài đặt|setting|khóa|lock|phóng|minimi|maximi|full/i;
 const cands = [...document.querySelectorAll('button,[role=button],[class*=icon i],[class*=btn i],svg,span,div')].filter(vis);
 for (const el of cands) { const l = label(el); if (l && MERGE.test(l) && !AVOID.test(l)) { const r = el.getBoundingClientRect(); return {x: r.left + r.width/2, y: r.top + r.height/2, how: 'label:' + l.slice(0,40)}; } }
 return null;
})()"""

CAPTCHA_JS = r"""(() => {
 const vis = el => { if (!el) return false; const r = el.getBoundingClientRect(); return r.width > 20 && r.height > 20; };
 const re = /captcha|xác minh|kéo thanh trượt|kéo mảnh ghép|xoay hình|verify to continue|drag the slider|security check/i;
 for (const el of document.querySelectorAll('[id*="captcha" i], [class*="captcha" i], [role="dialog"], iframe')) {
   if (!vis(el)) continue;
   const t = (el.innerText || el.getAttribute('src') || el.id || el.className || '').toString();
   if (re.test(t) || /captcha/i.test(String(el.id) + String(el.className))) return t.replace(/\s+/g, ' ').slice(0, 160) || 'captcha';
 }
 return '';
})()"""


FLOAT_DUMP_JS = r"""(() => {
 // 4.3.14: mọi thứ bấm được / có biểu tượng trong cửa sổ, để đo nút ghép khung chat thật
 const out = [];
 const label = el => ['aria-label','title','data-tooltip','alt','data-e2e','data-testid','name'].map(a => el.getAttribute && el.getAttribute(a)).filter(Boolean).join(' | ');
 for (const el of document.querySelectorAll('button,[role=button],[tabindex],a,svg,[class*=icon i],[class*=btn i],[class*=button i],[class*=header i] *')) {
   const r = el.getBoundingClientRect(); if (r.width <= 0 || r.height <= 0 || r.width > 900) continue;
   const use = el.querySelector && el.querySelector('use');
   out.push({tag: el.tagName.toLowerCase(), cls: String(el.className && el.className.baseVal !== undefined ? el.className.baseVal : el.className).slice(0, 120),
     label: label(el).slice(0, 120), text: (el.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 60),
     icon: use ? (use.getAttribute('href') || use.getAttribute('xlink:href') || '') : '', x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height)});
   if (out.length >= 400) break;
 }
 return {title: document.title, url: location.href.slice(-80), w: innerWidth, h: innerHeight, items: out};
})()"""


_DOCK_TRIED = {}
_DOCK_DUMPED = {}


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

    def connect_screen(self, port, wait=90):
        """4.2.2 (owner, 28/10/2026): Studio needs time to open and lands on its home
        page. Wait for it, open the studio screen by itself (the home 'Phát LIVE' only
        opens that screen) and wait for the nick name."""
        end = time.time() + wait; entered = False; s = {}
        while time.time() < end:
            try:
                t, s = self.state()
            except Exception:
                time.sleep(1); continue
            if s.get('hasButton') and s.get('nickname'):
                break
            if s.get('launch') and not s.get('hasButton') and not entered:
                self.click(t, 'launch'); entered = True
            time.sleep(1)
        if s.get('living') and entered:
            raise ValueError('Studio vừa vào trạng thái LIVE sau khi NBL mở màn hình phát. Kiểm tra Studio và tắt nếu không muốn phát.')
        if not s.get('nickname'):
            raise NotTouched('Studio đã mở nhưng sau ' + str(wait) + ' giây vẫn chưa thấy tên nick (Studio chưa đăng nhập?). Đăng nhập Studio rồi bấm lại.')
        return dict(nickname=s['nickname'], live=bool(s.get('living')), home=False, port=port, entered=entered)

    # ---- actions ----
    def status(self, expected=''):
        t, s = self.state()
        if s.get('nickname') and expected and not same_author(s['nickname'], expected):
            raise NotTouched('Studio đang là nick "' + s['nickname'] + '", không phải "' + expected + '".')
        if not s.get('hasButton') and not s.get('launch'):
            raise StudioChanged('Studio đang mở nhưng không thấy nút Phát LIVE / đồng hồ LIVE (Studio đổi giao diện hoặc đang ở trang khác).')
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

    def browser_command(self, method, params=None):
        """Lệnh ở mức trình duyệt (không thuộc trang nào): Browser.close đóng cả ứng dụng."""
        from websockets.sync.client import connect
        url = (self.get('/json/version') or {}).get('webSocketDebuggerUrl')
        if not url:
            raise RuntimeError('Studio không mở đường điều khiển trình duyệt.')
        with connect(url, open_timeout=self.timeout) as ws:
            ws.send(json.dumps({'id': 1, 'method': method, 'params': params or {}}))
            try:
                ws.recv(timeout=3)
            except Exception:
                pass   # Browser.close cắt luôn đường truyền: không có trả lời là đúng

    def quit(self, exe='', wait=10):
        """Đóng hẳn ứng dụng TikTok LIVE Studio KHÔNG bấm dấu X.

        Browser.close là lệnh của DevTools, gửi thẳng vào ứng dụng, nên captcha hay
        hộp thoại đang che màn hình không chặn được. Còn sống thì tắt tiến trình đang
        giữ cổng điều khiển. Studio tắt = nguồn phát đứt, nên LIVE dừng theo (TikTok
        đánh dấu phiên kết thúc chậm hơn khoảng nửa phút)."""
        out = dict(closed=False, method='', pid=port_pid(self.port))
        if not self.alive():
            return dict(out, closed=True, already=True, method='da_tat')
        try:
            self.browser_command('Browser.close'); out['method'] = 'cdp'
        except Exception as e:
            out['error'] = str(e)[:150]
        end = time.time() + wait
        while time.time() < end:
            time.sleep(.5)
            if not self.alive() and not pid_alive(out['pid']):
                out['closed'] = True; break
        if not out['closed']:
            k = kill_studio(exe, self.port)
            out['closed'] = k['closed'] or (not self.alive() and not pid_alive(out['pid']))
            out['method'] = k['method'] or out['method']
        return out

    def stop_or_quit(self, expected, exe=''):
        """TẮT KHẨN CẤP: kết thúc LIVE như thường; vướng captcha hay hộp thoại lạ
        thì đóng hẳn Studio, nên LIVE chắc chắn dừng."""
        why = ''
        try:
            r = self.stop(expected)
            if not r.get('live'):
                return dict(r, quit=False)
            why = 'Studio vẫn báo đang LIVE sau lệnh kết thúc'
        except Exception as e:
            why = str(e)
        q = self.quit(exe)
        if not q.get('closed'):
            raise ValueError('Chưa kết thúc được LIVE và cũng chưa tắt được Studio. Lý do: ' + why[:200])
        return dict(live=False, confirmed=True, method='quit', quit=True, quitMethod=q.get('method'),
                    studioClosed=True, why=why[:200])

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

    def captcha(self):
        """Text of a captcha / security check shown anywhere in Studio ('' = none)."""
        for t in self.pages():
            try:
                found = self.js(t, CAPTCHA_JS)
            except Exception:
                continue
            if found:
                return str(found)
        return ''

    def screenshot(self, quality=60):
        """4.3.0 (phone app): picture of the Studio main window, read from inside (no screen capture)."""
        import base64
        r = self.call(self.main(), [('Page.captureScreenshot', {'format': 'jpeg', 'quality': int(quality)})])[0]
        return base64.b64decode(r.get('data') or '')

    def selfcheck(self):
        """4.3.0 chạy thử: what NBL can see in Studio right now; reads only, clicks nothing."""
        _, st = self.state()
        out = dict(nickname=st.get('nickname', ''), hasButton=bool(st.get('hasButton')), living=bool(st.get('living')), idle=bool(st.get('idle')),
                   buttonText=st.get('buttonText', ''), dialogs=[d.get('text', '')[:120] for d in st.get('dialogs') or []], health=st.get('health'))
        out['chatBox'] = bool(self.chat_page())
        out['chatFloating'] = bool(self.page('/html/liveChatFloat/'))
        try:
            out['comments'] = len(self.chat_read())
        except Exception:
            out['comments'] = -1
        try:
            out['captcha'] = self.captcha()
        except Exception:
            out['captcha'] = ''
        return out

    def dump_float_chat(self):
        """4.3.14: chưa biết nút ghép thật của khung chat nổi -> lưu các nút của cửa sổ nổi + cửa sổ chính
        (mỗi lần mở NBL tối đa 1 file mỗi 30 phút, giữ 5 file mới nhất) vào logs/khung_chat_noi_*.json."""
        import time as _t
        if _t.time() - _DOCK_DUMPED.get(self.port, 0) < 1800:
            return
        _DOCK_DUMPED[self.port] = _t.time()
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            data = []
            for t in self.pages():
                url = t.get('url', '')
                if '/html/liveChatFloat/' not in url and '/html/main/' not in url:
                    continue
                try:
                    data.append(dict(url=url[-80:], title=t.get('title', ''), dump=self.js(t, FLOAT_DUMP_JS)))
                except Exception as e:
                    data.append(dict(url=url[-80:], error=str(e)[:200]))
            (LOG_DIR / ('khung_chat_noi_' + _t.strftime('%Y%m%d_%H%M%S') + '.json')).write_text(
                json.dumps(dict(version=__import__('diagnostics').VERSION, pages=data), ensure_ascii=False, indent=1), encoding='utf-8')
            for old in sorted(LOG_DIR.glob('khung_chat_noi_*.json'))[:-5]:
                old.unlink(missing_ok=True)
        except Exception:
            pass

    def dock_chat(self):
        """If the chat window is floating, click its merge button in-page (no mouse). Returns
        {floating, docked, found}. Rate-limited per port so it never clicks on every read."""
        t = self.page('/html/liveChatFloat/')
        if not t:
            return dict(floating=False, docked=True)
        import time as _t
        last = _DOCK_TRIED.get(self.port, 0)
        if _t.time() - last < 20:
            return dict(floating=True, docked=False, found=None, waiting=True)
        _DOCK_TRIED[self.port] = _t.time()
        spot = self.js(t, DOCK_JS)
        if not spot:
            self.dump_float_chat()
            return dict(floating=True, docked=False, found=False)
        base = {'x': spot['x'], 'y': spot['y'], 'button': 'left', 'clickCount': 1}
        self.call(t, [('Input.dispatchMouseEvent', {**base, 'type': 'mouseMoved'}),
                      ('Input.dispatchMouseEvent', {**base, 'type': 'mousePressed'}),
                      ('Input.dispatchMouseEvent', {**base, 'type': 'mouseReleased'})])
        for _ in range(8):
            _t.sleep(.25)
            if not self.page('/html/liveChatFloat/'):
                return dict(floating=True, docked=True, how=spot.get('how'))
        return dict(floating=True, docked=False, found=True, how=spot.get('how'))

    def chat_read(self):
        """Comments shown in Studio's chat (newest last). Docks a floating chat window first so
        the comments live in one place, then reads the main window, then the float as a fallback."""
        try:
            self.dock_chat()
        except Exception:
            pass
        seen, out = set(), []
        for part in ('/html/main/', '/html/liveChatFloat/'):
            try:
                t = self.page(part)
                rows = self.js(t, CHAT_JS) if t else []
            except Exception:
                continue
            for r in rows or []:
                if r.get('id') and r['id'] not in seen:
                    seen.add(r['id']); out.append(r)
        return out

    def chat_page(self):
        try:
            self.dock_chat()
        except Exception:
            pass
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


# ---- 4.3.9: tắt hẳn Studio mà không bấm chuột ----
def port_pid(port):
    """PID của tiến trình đang giữ cổng điều khiển (Windows). 0 = không đọc được."""
    if os.name != 'nt':
        return 0
    try:
        out = subprocess.run(['netstat', '-ano', '-p', 'TCP'], capture_output=True, text=True, errors='replace',
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).stdout
    except Exception:
        return 0
    want = ':' + str(int(port))
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[0].upper() == 'TCP' and parts[1].endswith(want) and parts[3].upper() == 'LISTENING':
            try:
                return int(parts[4])
            except ValueError:
                return 0
    return 0


def pid_alive(pid):
    if os.name != 'nt' or not pid:
        return False
    try:
        out = subprocess.run(['tasklist', '/FI', 'PID eq ' + str(int(pid)), '/FO', 'CSV', '/NH'], capture_output=True,
                             text=True, errors='replace', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).stdout
    except Exception:
        return False
    return ('"' + str(int(pid)) + '"') in out


def taskkill(*args):
    if os.name != 'nt':
        return False
    try:
        r = subprocess.run(['taskkill', '/F', '/T'] + list(args), capture_output=True, text=True, errors='replace',
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return r.returncode == 0
    except Exception:
        return False


def kill_studio(exe='', port=0):
    """Tắt Studio khi không còn nói chuyện được qua cổng: theo PID giữ cổng trước,
    không có thì theo tên file Studio. Dùng cho cả nick chưa bật kết nối tự động."""
    out = dict(closed=False, method='', pid=0)
    pid = port_pid(port) if port else 0
    out['pid'] = pid
    if pid and taskkill('/PID', str(pid)):
        out.update(closed=not pid_alive(pid), method='taskkill-pid')
    if not out['closed'] and exe and Path(exe).name.lower().endswith('.exe'):
        if taskkill('/IM', Path(exe).name):
            time.sleep(1)
            out.update(closed=not running_studio(exe), method='taskkill-ten')
    return out


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


NO_THROTTLE = ('--disable-renderer-backgrounding', '--disable-background-timer-throttling', '--disable-backgrounding-occluded-windows')


def launch(exe, port, wait=90):
    if not exe or not Path(exe).is_file():
        raise NotTouched('Không thấy file TikTok LIVE Studio: ' + str(exe))
    flags = 0
    for f in ('DETACHED_PROCESS', 'CREATE_NEW_PROCESS_GROUP', 'CREATE_NO_WINDOW'):
        flags |= getattr(subprocess, f, 0)
    # 4.3.16: cờ chống bóp tốc độ khi Studio bị ẩn / thu nhỏ ("Ẩn hết khi LIVE") — giống Chrome LIVE của NBL
    subprocess.Popen([exe, '--remote-debugging-port=%d' % port, '--remote-allow-origins=http://127.0.0.1:%d' % port, *NO_THROTTLE],
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
    if not exe:
        exe = find_exe()                 # hỏi Windows: chỉ khi NBL thật sự phải tự mở Studio
    if running_studio(exe) and not any(Studio(p).alive() for p in other_ports):
        raise NotTouched('TikTok LIVE Studio đang mở nhưng KHÔNG phải do NBL mở, nên NBL chưa đọc được. Đóng hẳn Studio (khi không LIVE); NBL sẽ tự mở lại.')
    return launch(exe, port)


STUDIO_EXE = 'TikTok LIVE Studio.exe'


_EXE_CACHE = {'at': 0.0, 'path': ''}


def running_exe_path(max_age=300):
    r"""Đường dẫn thật của Studio ĐANG CHẠY, hỏi thẳng Windows.

    4.3.10 (chủ máy, 31/10/2026): máy khách cài Studio thành
    "...\TikTok LIVE Studio\1.38.0\TikTok LIVE Studio.exe" — có thêm tầng thư mục
    phiên bản — nên cách dò theo khuôn cố định không ra. Hỏi Windows thì đúng mọi kiểu cài."""
    if os.name != 'nt':
        return ''
    now = time.time()
    if now - _EXE_CACHE['at'] < (max_age if _EXE_CACHE['path'] else 60):
        return _EXE_CACHE['path']
    _EXE_CACHE['at'] = now
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='" + STUDIO_EXE + "'\" "
          "| Where-Object { $_.ExecutablePath } | Select-Object -First 1 -ExpandProperty ExecutablePath")
    try:
        out = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', ps], capture_output=True,
                             text=True, errors='replace', timeout=25,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).stdout.strip().splitlines()
    except Exception:
        return ''
    for line in out:
        line = line.strip().strip('"')
        if line and Path(line).is_file():
            _EXE_CACHE['path'] = line
            return line
    return ''


def find_exe(hint='', ask_windows=True):
    """Thứ tự: đường dẫn đã lưu → Studio đang chạy (chuẩn nhất) → các thư mục cài
    thường gặp → thư mục con theo phiên bản (1.38.0, 1.39.0…), bản mới nhất trước."""
    if hint and Path(hint).is_file():
        return hint
    if ask_windows:
        found = running_exe_path()
        if found:
            return found
    bases, cands = [], []
    for key in ('ProgramFiles', 'ProgramW6432', 'ProgramFiles(x86)'):
        if os.environ.get(key):
            bases.append(Path(os.environ[key]))
    if os.environ.get('LOCALAPPDATA'):
        bases += [Path(os.environ['LOCALAPPDATA']) / 'Programs', Path(os.environ['LOCALAPPDATA'])]
    for base in bases:
        root = base / 'TikTok LIVE Studio'
        cands.append(root / STUDIO_EXE)
        try:
            if root.is_dir():
                subs = [d for d in root.iterdir() if d.is_dir() and (d / STUDIO_EXE).is_file()]
                cands += [d / STUDIO_EXE for d in sorted(subs, key=lambda d: _ver(d.name), reverse=True)]
        except OSError:
            pass
    for c in cands:
        try:
            if c.is_file():
                return str(c)
        except OSError:
            pass
    return ''


def _ver(name):
    return [int(x) if x.isdigit() else 0 for x in re.split(r'[._-]', str(name))[:4]] or [0]


def execute_cdp(profile, action, deadline=0, payload=None):
    """Same results as the image path (studio_vision.execute_vision) for the actions it covers."""
    port = int(profile.get('cdpPort') or BASE_PORT)
    expected = profile.get('accountName') or profile.get('name') or ''
    others = [int(p) for p in profile.get('_otherPorts') or []]
    if action in ('status', 'stop', 'close_summary', 'probe', 'chat_check', 'send', 'chat_read', 'captcha', 'screenshot', 'selfcheck', 'dock_chat', 'quit_studio', 'emergency_stop'):
        studio = connect(profile.get('exePath'), port, others, open_if_closed=False)
        if studio is None:
            if action == 'probe':
                return dict(windowFound=False)
            if running_studio(profile.get('exePath')) and not any(Studio(p).alive() for p in others):
                raise NotTouched('TikTok LIVE Studio đang mở nhưng không phải do NBL mở; NBL chưa đọc được nick này.')
            if action in ('status', 'stop', 'close_summary', 'emergency_stop'):
                return dict(live=False, studioClosed=True, closed=True, method='cdp')
            if action == 'quit_studio':
                # cổng đã im: Studio của NBL đã tắt, nhưng có thể còn một Studio mở tay
                k = kill_studio(profile.get('exePath'), port) if running_studio(profile.get('exePath')) else dict(closed=True, method='da_tat')
                return dict(k, studioClosed=True, live=False, method='cdp')
            if action in ('screenshot', 'selfcheck'):
                raise NotTouched('TikTok LIVE Studio chưa mở.')
            if action in ('chat_read', 'captcha', 'dock_chat'):
                return dict(comments=[], captcha='', studioClosed=True, method='cdp')
            raise NotTouched('TikTok LIVE Studio chưa mở; chưa gửi.')
    else:
        studio = connect(profile.get('exePath'), port, others, open_if_closed=not profile.get('noLaunch'))
        if studio is None:
            if not profile.get('exePath'):
                raise NotTouched('TikTok LIVE Studio chưa mở, và NBL cũng chưa tìm thấy file Studio trên máy nên không tự mở được. '
                                 'Mở Studio lên là NBL tự kết nối.')
            raise NotTouched('TikTok LIVE Studio chưa mở. Mở Studio bằng icon TikTok LIVE Studio; NBL tự kết nối.')
    if action == 'probe':
        return dict(windowFound=True)
    if action == 'status':
        return studio.status(expected)
    if action == 'start':
        return studio.start(expected)
    if action == 'stop':
        return studio.stop(expected)
    if action == 'quit_studio':
        return dict(studio.quit(profile.get('exePath')), studioClosed=True, live=False, method='cdp')
    if action == 'emergency_stop':
        return studio.stop_or_quit(expected, profile.get('exePath'))
    if action == 'close_summary':
        r = studio.close_end_page()
        return dict(closed=not r['seen'] or r['closed'], seen=r['seen'], method='cdp')
    if action == 'chat_check':
        return studio.chat_check()
    if action == 'chat_read':
        return dict(comments=studio.chat_read(), method='cdp')
    if action == 'captcha':
        return dict(captcha=studio.captcha(), method='cdp')
    if action == 'dock_chat':
        return dict(studio.dock_chat(), method='cdp')
    if action == 'send':
        return studio.send(str((payload or {}).get('text', '')), expected)
    if action == 'selfcheck':
        return dict(studio.selfcheck(), port=port, method='cdp')
    if action == 'screenshot':
        return dict(jpeg=studio.screenshot(), method='cdp')
    if action == 'connect':
        out = studio.connect_screen(port)
        return dict(out, exePath=profile.get('exePath') or find_exe())
    raise NotTouched('Kết nối tự động chưa làm mục này: ' + action)


CDP_ACTIONS = ('probe', 'status', 'start', 'stop', 'close_summary', 'chat_check', 'send', 'connect', 'chat_read', 'captcha', 'screenshot', 'selfcheck', 'dock_chat', 'quit_studio', 'emergency_stop')


# ---- 4.3.0: Studio icons open Studio with NBL's port (owner agreed 28/10/2026) ----
SHORTCUT_PS = r'''
$ErrorActionPreference = 'SilentlyContinue'
$args2 = '--remote-debugging-port=%PORT% --remote-allow-origins=http://127.0.0.1:%PORT% --disable-renderer-backgrounding --disable-background-timer-throttling --disable-backgrounding-occluded-windows'
$sh = New-Object -ComObject WScript.Shell
$dirs = @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('CommonDesktopDirectory'), [Environment]::GetFolderPath('StartMenu'), [Environment]::GetFolderPath('CommonStartMenu'))
$n = 0
foreach ($d in $dirs) { if (-not $d) { continue }
  Get-ChildItem -Path $d -Filter '*.lnk' -Recurse -ErrorAction SilentlyContinue | ForEach-Object {
    $l = $sh.CreateShortcut($_.FullName)
    if ($l.TargetPath -match 'TikTok LIVE Studio[^\\]*\.exe$' -and ($l.Arguments -notmatch 'remote-debugging-port=%PORT%' -or $l.Arguments -notmatch 'disable-renderer-backgrounding')) { $l.Arguments = $args2; $l.Save(); $n++ } } }
Write-Output $n
'''


def fix_shortcuts(port=BASE_PORT):
    """Make every TikTok LIVE Studio icon (Desktop + Start) open Studio with the port.
    Studio's own updater may write the icons again, so NBL runs this at every start."""
    if os.name != 'nt':
        return 0
    try:
        out = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', SHORTCUT_PS.replace('%PORT%', str(int(port)))],
                             capture_output=True, text=True, timeout=40, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return int((out.stdout or '0').strip().splitlines()[-1] or 0)
    except Exception:
        return 0
