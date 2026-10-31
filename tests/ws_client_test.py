"""Máy khách WebSocket tối giản cho test (giả app điện thoại). Không phải file test (không có test*)."""
import base64, json, os, socket, struct


class Client:
    def __init__(self, port, path, host='127.0.0.1', timeout=10):
        self.s = socket.create_connection((host, port), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall(('GET %s HTTP/1.1\r\nHost: %s:%d\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
                        'Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n' % (path, host, port, key)).encode())
        head = b''
        while b'\r\n\r\n' not in head:
            c = self.s.recv(1)
            if not c:
                break
            head += c
        self.status = int(head.split(b' ')[1]) if head else 0
        self.head = head.decode('latin1')

    def send(self, op, data):
        n = len(data); mask = os.urandom(4)
        if n < 126:
            h = struct.pack('>BB', 0x80 | op, 0x80 | n)
        elif n < 65536:
            h = struct.pack('>BBH', 0x80 | op, 0x80 | 126, n)
        else:
            h = struct.pack('>BBQ', 0x80 | op, 0x80 | 127, n)
        self.s.sendall(h + mask + bytes(b ^ mask[i & 3] for i, b in enumerate(data)))

    def text(self, obj):
        self.send(1, json.dumps(obj).encode())

    def binary(self, data):
        self.send(2, data)

    def _read(self, n):
        d = b''
        while len(d) < n:
            c = self.s.recv(n - len(d))
            if not c:
                raise ConnectionError('đóng')
            d += c
        return d

    def recv(self):
        b1, b2 = self._read(2); n = b2 & 0x7F
        if n == 126:
            n = struct.unpack('>H', self._read(2))[0]
        elif n == 127:
            n = struct.unpack('>Q', self._read(8))[0]
        data = self._read(n); op = b1 & 0x0F
        return op, (json.loads(data) if op == 1 else data)

    def close(self):
        try:
            self.s.close()
        except OSError:
            pass
