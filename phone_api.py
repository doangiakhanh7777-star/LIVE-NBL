"""4.3.0 (owner, 28/10/2026): điều khiển NBL từ app điện thoại Android.

A small HTTP API on port 8766, answered only to the phone's network (Tailscale
100.64.0.0/10, the home wifi, this PC) and only with the pairing code. Everything that
touches NBL runs on the Qt thread (Server.drain, called by a 100 ms timer); the HTTP
threads only wait for the answer, read a Studio screenshot or stream a clip file.
"""
import hmac
import ipaddress
import json
import os
import queue
import re
import secrets
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

PORT = 8766
TAILSCALE = ipaddress.ip_network('100.64.0.0/10')
TAILSCALE6 = ipaddress.ip_network('fd7a:115c:a1e0::/48')
VIDEO_TYPES = {'.mp4': 'video/mp4', '.m4v': 'video/mp4', '.mov': 'video/quicktime', '.webm': 'video/webm', '.mkv': 'video/x-matroska', '.avi': 'video/x-msvideo'}


def allowed_ip(text):
    try:
        ip = ipaddress.ip_address(str(text).split('%')[0])
    except ValueError:
        return False
    if getattr(ip, 'ipv4_mapped', None):
        ip = ip.ipv4_mapped
    return ip.is_loopback or ip in TAILSCALE or (ip.version == 6 and ip in TAILSCALE6) or ip.is_private and not ip.is_global


class Config:
    """phone_api.json in the NBL data folder: {enabled, token, port}."""
    def __init__(self, path):
        self.path = Path(path)

    def load(self):
        try:
            d = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            d = {}
        changed = False
        if not re.fullmatch(r'[A-Za-z0-9_-]{32,}', str(d.get('token', ''))):
            d['token'] = secrets.token_urlsafe(32); changed = True
        d.setdefault('enabled', True); d.setdefault('port', PORT)
        if changed:
            self.save(d)
        return d

    def save(self, d):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps(d, ensure_ascii=False), encoding='utf-8')
        os.replace(tmp, self.path)

    def new_token(self):
        d = self.load(); d['token'] = secrets.token_urlsafe(32); self.save(d)
        return d


def addresses():
    """Names/addresses the phone can reach this PC by: computer name (Tailscale MagicDNS), Tailscale IP, wifi IP."""
    name = socket.gethostname()
    ips = []
    try:
        for info in socket.getaddrinfo(name, None, socket.AF_INET):
            ip = info[4][0]
            a = ipaddress.ip_address(ip)
            if (a in TAILSCALE or a.is_private) and not a.is_loopback and ip not in ips:
                ips.append(ip)
    except OSError:
        pass
    return [name.lower()] + sorted(ips, key=lambda ip: 0 if ipaddress.ip_address(ip) in TAILSCALE else 1)


def pair_link(token, port=PORT, hosts=None):
    hosts = hosts or addresses()
    return 'nblive://pair?n=' + quote(socket.gethostname()) + '&h=' + quote(','.join(hosts)) + '&p=' + str(port) + '&t=' + quote(token)


class ApiError(Exception):
    def __init__(self, text, status=400):
        super().__init__(text); self.status = status


class Server:
    def __init__(self, actions, config):
        self.actions = actions; self.config = config
        self.calls = queue.Queue(); self.httpd = None; self.thread = None; self.error = ''

    # ---- Qt side ----
    def start(self):
        cfg = self.config.load()
        if not cfg.get('enabled') or self.httpd:
            return
        server = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'
            def log_message(self, *a):
                pass
            def do_OPTIONS(self):
                self.send_response(204); self.cors(); self.send_header('Content-Length', '0'); self.end_headers()
            def do_GET(self):
                server.handle(self, 'GET')
            def do_POST(self):
                server.handle(self, 'POST')
            def do_PUT(self):
                server.handle(self, 'PUT')
            def do_DELETE(self):
                server.handle(self, 'DELETE')
            def cors(self):
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Access-Control-Allow-Headers', 'Authorization, Content-Type')
                self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')

        try:
            self.httpd = ThreadingHTTPServer(('0.0.0.0', int(cfg.get('port') or PORT)), Handler)
            self.httpd.daemon_threads = True
        except OSError as e:
            self.httpd = None; self.error = 'Không mở được cổng ' + str(cfg.get('port') or PORT) + ': ' + str(e)
            return
        self.error = ''
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True, name='nbl-phone-api')
        self.thread.start()

    def stop(self):
        if self.httpd:
            try:
                self.httpd.shutdown(); self.httpd.server_close()
            except Exception:
                pass
        self.httpd = None

    def drain(self):
        """Runs waiting phone requests on the Qt thread."""
        for _ in range(20):
            try:
                fn, box, done = self.calls.get_nowait()
            except queue.Empty:
                return
            try:
                box['value'] = fn()
            except ApiError as e:
                box['error'] = e
            except Exception as e:
                box['error'] = ApiError(str(e) or type(e).__name__, 400)
            done.set()

    # ---- HTTP side ----
    def on_main(self, fn, timeout=20):
        box, done = {}, threading.Event()
        self.calls.put((fn, box, done))
        if not done.wait(timeout):
            raise ApiError('NBL đang bận, thử lại.', 503)
        if 'error' in box:
            raise box['error']
        return box.get('value')

    def handle(self, h, method):
        url = urlparse(h.path); q = {k: v[-1] for k, v in parse_qs(url.query).items()}
        try:
            if not allowed_ip(h.client_address[0]):
                raise ApiError('Chỉ nhận điện thoại trong Tailscale / cùng wifi.', 403)
            token = self.config.load()['token']
            given = (h.headers.get('Authorization') or '').replace('Bearer ', '', 1).strip() or q.get('t', '')
            if not hmac.compare_digest(given.encode(), token.encode()):
                time.sleep(0.5)
                raise ApiError('Sai mã ghép. Quét lại mã QR trên NBL.', 401)
            body = {}
            n = int(h.headers.get('Content-Length') or 0)
            if n:
                if n > 2 << 20:
                    raise ApiError('Dữ liệu quá lớn.', 413)
                body = json.loads(h.rfile.read(n).decode('utf-8') or '{}')
            route = method + ' ' + url.path.rstrip('/')
            a = self.actions
            if route == 'GET /api/screenshot':
                profile = self.on_main(a.screenshot_profile)
                self.send(h, 200, a.screenshot(profile), 'image/jpeg'); return
            if route == 'GET /api/clip':
                self.stream(h, self.on_main(lambda: a.clip_path(q.get('i')))); return
            table = {
                'GET /api/status': lambda: a.status(),
                'GET /api/logs': lambda: a.logs(q.get('after', 0)),
                'GET /api/schedules': lambda: a.schedules(),
                'POST /api/schedules': lambda: a.add_schedule(body),
                'POST /api/schedules/cancel': lambda: a.cancel_schedule(body),
                'POST /api/cart/retry': lambda: a.cart_retry(body),
                'POST /api/pin': lambda: a.set_pin(body),
                'POST /api/ai': lambda: a.set_ai(body),
                'POST /api/auto': lambda: a.set_auto(body),
                'POST /api/emergency': lambda: a.emergency(body),
                'GET /api/pin/settings': lambda: a.pin_settings(),
                'PUT /api/pin/settings': lambda: a.save_pin_settings(body),
                'GET /api/clips': lambda: a.clips(),
                'GET /api/script': lambda: a.script(q.get('i')),
                'PUT /api/script': lambda: a.save_script(q.get('i'), body),
                'GET /api/ai/settings': lambda: a.ai_settings(),
                'PUT /api/ai/settings': lambda: a.save_ai_settings(body),
            }
            if route not in table:
                raise ApiError('Không có mục này.', 404)
            self.send(h, 200, json.dumps(dict(ok=True, data=self.on_main(table[route])), ensure_ascii=False).encode('utf-8'))
        except ApiError as e:
            self.send(h, e.status, json.dumps(dict(ok=False, error=str(e)), ensure_ascii=False).encode('utf-8'))
        except (ValueError, KeyError, TypeError) as e:
            self.send(h, 400, json.dumps(dict(ok=False, error='Yêu cầu không hợp lệ: ' + str(e)), ensure_ascii=False).encode('utf-8'))
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            try:
                self.send(h, 500, json.dumps(dict(ok=False, error=type(e).__name__ + ': ' + str(e)), ensure_ascii=False).encode('utf-8'))
            except Exception:
                pass

    def send(self, h, status, data, kind='application/json; charset=utf-8'):
        h.send_response(status); h.cors()
        h.send_header('Content-Type', kind); h.send_header('Content-Length', str(len(data)))
        h.send_header('Cache-Control', 'no-store'); h.end_headers(); h.wfile.write(data)

    def stream(self, h, path):
        path = Path(path); size = path.stat().st_size
        start, end = 0, size - 1
        m = re.fullmatch(r'bytes=(\d*)-(\d*)', (h.headers.get('Range') or '').strip())
        if m and (m.group(1) or m.group(2)):
            if m.group(1):
                start = int(m.group(1)); end = int(m.group(2)) if m.group(2) else size - 1
            else:
                start = max(0, size - int(m.group(2)))
            end = min(end, size - 1)
            if start > end:
                h.send_response(416); h.cors(); h.send_header('Content-Range', 'bytes */' + str(size)); h.send_header('Content-Length', '0'); h.end_headers(); return
            h.send_response(206); h.send_header('Content-Range', 'bytes %d-%d/%d' % (start, end, size))
        else:
            h.send_response(200)
        h.cors(); h.send_header('Accept-Ranges', 'bytes')
        h.send_header('Content-Type', VIDEO_TYPES.get(path.suffix.lower(), 'application/octet-stream'))
        h.send_header('Content-Length', str(end - start + 1)); h.end_headers()
        with open(path, 'rb') as f:
            f.seek(start); left = end - start + 1
            while left > 0:
                chunk = f.read(min(1 << 18, left))
                if not chunk:
                    break
                h.wfile.write(chunk); left -= len(chunk)
