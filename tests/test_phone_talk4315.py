"""4.3.15: nói qua điện thoại — WebSocket /api/talk (ws_mini) + bộ đệm chống giật (ptt_core.Jitter). Không cần Qt."""
import shutil, socket, sys, tempfile, threading, time, unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(Path(__file__).resolve().parent))
import phone_api
import ws_mini
from ptt_core import Jitter
from ws_client_test import Client


class FakeTalk:
    def __init__(self, refuse=''):
        self.events = []; self.bytes = 0; self.refuse = refuse; self.ended = threading.Event()
    def begin(self, rate, peer):
        self.events.append(('begin', rate)); return self.refuse
    def feed(self, data):
        self.bytes += len(data)
    def end(self):
        self.events.append(('end',)); self.ended.set()


class Actions:
    def status(self):
        return dict(version='4.3.15')


class TalkTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0)); self.port = s.getsockname()[1]
        cfg = phone_api.Config(self.tmp / 'p.json'); d = cfg.load(); d['port'] = self.port; cfg.save(d); self.token = d['token']
        self.talk = FakeTalk()
        self.server = phone_api.Server(Actions(), cfg, None, self.talk); self.server.start()
        self.stop = threading.Event()
        threading.Thread(target=self.fake_qt, daemon=True).start()

    def fake_qt(self):
        while not self.stop.is_set():
            self.server.drain(); time.sleep(0.02)

    def tearDown(self):
        self.stop.set(); self.server.stop(); shutil.rmtree(self.tmp, ignore_errors=True)

    def connect(self, token=None):
        return Client(self.port, '/api/talk?t=' + (self.token if token is None else token))

    def test_accept_key_rfc_example(self):
        self.assertEqual(ws_mini.accept_key('dGhlIHNhbXBsZSBub25jZQ=='), 's3pPLMBiTxaQ9kYGzzhZRbK+xOo=')

    def test_talk_start_audio_stop(self):
        c = self.connect(); self.assertEqual(c.status, 101)
        self.assertEqual(c.recv(), (1, {'type': 'ready'}))
        c.binary(b'\x00' * 100)                                  # trước start: bỏ qua
        c.text({'type': 'start', 'rate': 48000}); self.assertEqual(c.recv()[1]['type'], 'talking')
        for size in (2048, 200, 70000):                           # độ dài 7 bit, 16 bit, 64 bit
            c.binary(bytes(range(256)) * (size // 256) + b'\x01' * (size % 256))
        c.send(9, b'hi'); self.assertEqual(c.recv(), (10, b'hi'))   # ping -> pong
        c.text({'type': 'ping'}); self.assertEqual(c.recv()[1]['type'], 'pong')
        c.text({'type': 'stop'}); self.assertEqual(c.recv()[1]['type'], 'stopped')
        self.assertEqual(self.talk.events, [('begin', 48000), ('end',)])
        self.assertEqual(self.talk.bytes, 2048 + 200 + 70000)
        c.close()

    def test_phone_vanishes_mid_talk_ends_the_talk(self):
        c = self.connect(); c.recv(); c.text({'type': 'start', 'rate': 44100}); c.recv(); c.binary(b'\x00' * 960)
        c.close()                                                 # mất mạng giữa lúc đang nói
        self.assertTrue(self.talk.ended.wait(5)); self.assertEqual(self.talk.events[-1], ('end',))

    def test_wrong_code_refused(self):
        c = self.connect('sai'); self.assertEqual(c.status, 401); c.close()
        self.assertEqual(self.talk.events, [])

    def test_bad_rate_and_pc_cannot_open(self):
        c = self.connect(); c.recv()
        c.text({'type': 'start', 'rate': 5}); self.assertEqual(c.recv()[1]['type'], 'error')
        self.talk.refuse = 'Không mở được cáp ảo'
        c.text({'type': 'start', 'rate': 48000}); m = c.recv()[1]
        self.assertEqual((m['type'], m['text']), ('error', 'Không mở được cáp ảo'))
        c.close()

    def test_plain_get_is_not_websocket(self):
        import http.client, json
        h = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        h.request('GET', '/api/talk', headers={'Authorization': 'Bearer ' + self.token}); r = h.getresponse()
        self.assertEqual(r.status, 400); self.assertFalse(json.loads(r.read())['ok'])
        h2 = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        h2.request('GET', '/api/status', headers={'Authorization': 'Bearer ' + self.token}); self.assertEqual(h2.getresponse().status, 200)


class JitterTest(unittest.TestCase):
    def test_preroll_then_flow_and_never_lags(self):
        bps = 48000 * 4; j = Jitter(bps, 4)            # 48 kHz stereo 16-bit
        j.push(b'\x00' * (bps * 40 // 1000)); self.assertEqual(j.take(10**6), b'')       # 40 ms < 80 ms: chờ
        j.push(b'\x00' * (bps * 50 // 1000)); out = j.take(10**6)
        self.assertEqual(len(out) % 4, 0); self.assertGreater(len(out), 0)
        j.push(b'\x01' * (bps * 2))                     # mạng dồn 2 giây một lúc
        self.assertLessEqual(len(j.buf), bps * 320 // 1000); self.assertGreater(j.dropped, 0)
        self.assertEqual(len(j.take(1001)) % 4, 0)

    def test_take_respects_free_space(self):
        j = Jitter(1000, 2, preroll_ms=0); j.push(b'ab' * 50)
        self.assertEqual(len(j.take(11)), 10); self.assertEqual(j.take(0), b'')


if __name__ == '__main__':
    unittest.main()
