"""4.3.15: WebSocket tối giản (RFC 6455) cho đường "nói qua điện thoại" trên cổng 8766.

Chỉ phía máy chủ, chạy trong luồng HTTP của phone_api. Không dính Qt, không thêm thư viện.
"""
import base64
import hashlib
import json
import socket
import struct

GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
MAX_FRAME = 1 << 20


class Closed(Exception):
    pass


def accept_key(key):
    return base64.b64encode(hashlib.sha1((key.strip() + GUID).encode()).digest()).decode()


def handshake(h):
    """h = BaseHTTPRequestHandler. Trả True nếu đã nâng cấp lên WebSocket."""
    key = h.headers.get('Sec-WebSocket-Key') or ''
    if 'websocket' not in (h.headers.get('Upgrade') or '').lower() or not key:
        return False
    h.send_response(101, 'Switching Protocols')
    h.send_header('Upgrade', 'websocket'); h.send_header('Connection', 'Upgrade')
    h.send_header('Sec-WebSocket-Accept', accept_key(key)); h.end_headers()
    h.wfile.flush()
    return True


def _read(f, n):
    data = b''
    while len(data) < n:
        chunk = f.read(n - len(data))
        if not chunk:
            raise Closed('mất kết nối')
        data += chunk
    return data


def read_message(f):
    """(opcode, bytes) của một tin hoàn chỉnh (ghép các khúc). Ping được trả về để bên gọi trả pong."""
    parts = []; first = None
    while True:
        b1, b2 = _read(f, 2)
        fin, op = b1 & 0x80, b1 & 0x0F
        masked, n = b2 & 0x80, b2 & 0x7F
        if n == 126:
            n = struct.unpack('>H', _read(f, 2))[0]
        elif n == 127:
            n = struct.unpack('>Q', _read(f, 8))[0]
        if n > MAX_FRAME:
            raise Closed('khung quá lớn')
        mask = _read(f, 4) if masked else None
        data = _read(f, n)
        if mask:
            data = bytes(b ^ mask[i & 3] for i, b in enumerate(data)) if n < 64 else _unmask(data, mask)
        if op >= 8:                      # điều khiển: không bị chia khúc, có thể chen giữa
            return op, data
        if first is None:
            first = op
        parts.append(data)
        if fin:
            return first, b''.join(parts)


def _unmask(data, mask):
    n = len(data)
    m = int.from_bytes((mask * (n // 4 + 1))[:n], 'big')
    return (int.from_bytes(data, 'big') ^ m).to_bytes(n, 'big')


def frame(op, data=b''):
    n = len(data)
    if n < 126:
        head = struct.pack('>BB', 0x80 | op, n)
    elif n < 65536:
        head = struct.pack('>BBH', 0x80 | op, 126, n)
    else:
        head = struct.pack('>BBQ', 0x80 | op, 127, n)
    return head + data


def send_text(h, obj):
    h.wfile.write(frame(1, json.dumps(obj, ensure_ascii=False).encode('utf-8'))); h.wfile.flush()


def talk_session(h, sink, timeout=25):
    """Vòng nhận tiếng từ điện thoại.

    Tin chữ: {"type":"start","rate":48000} · {"type":"stop"} · {"type":"ping"}.
    Tin nhị phân: PCM 16-bit một kênh (chỉ nhận giữa start và stop).
    sink: begin(rate, peer) -> lỗi (str) hoặc '' ; feed(bytes) ; end(). Mọi hàm của sink phải an toàn khi gọi từ luồng này.
    """
    try:
        h.connection.settimeout(timeout)
    except Exception:
        pass
    peer = h.client_address[0]; talking = False
    send_text(h, dict(type='ready'))
    try:
        while True:
            try:
                op, data = read_message(h.rfile)
            except (socket.timeout, TimeoutError, OSError):
                raise Closed('hết giờ chờ')
            if op == 8:
                try:
                    h.wfile.write(frame(8, data[:2])); h.wfile.flush()
                except OSError:
                    pass
                return
            if op == 9:
                h.wfile.write(frame(10, data)); h.wfile.flush(); continue
            if op == 10:
                continue
            if op == 2:
                if talking and data:
                    sink.feed(data)
                continue
            if op == 1:
                try:
                    msg = json.loads(data.decode('utf-8'))
                except ValueError:
                    continue
                kind = msg.get('type')
                if kind == 'start':
                    rate = int(msg.get('rate') or 48000)
                    if not 8000 <= rate <= 96000:
                        send_text(h, dict(type='error', text='Tần số mic không hợp lệ.')); continue
                    err = sink.begin(rate, peer) if not talking else ''
                    if err:
                        send_text(h, dict(type='error', text=err)); continue
                    talking = True; send_text(h, dict(type='talking'))
                elif kind == 'stop':
                    if talking:
                        talking = False; sink.end()
                    send_text(h, dict(type='stopped'))
                elif kind == 'ping':
                    send_text(h, dict(type='pong'))
    except Closed:
        return
    finally:
        if talking:
            sink.end()
