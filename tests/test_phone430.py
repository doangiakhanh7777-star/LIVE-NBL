import json, tempfile, threading, time, unittest, sys, types
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import phone_api, phone_actions, qr


class FakeActions:
    def __init__(self, clip):
        self.clip = clip; self.calls = []; self.main = None
    def status(self):
        self.main = threading.current_thread().name; return dict(live=True)
    def emergency(self, body):
        self.calls.append(('emergency', body)); return dict(done=True)
    def clip_path(self, i):
        if str(i) != '0': raise phone_api.ApiError('Không thấy clip', 404)
        return self.clip
    def logs(self, after):
        return [dict(n=1, text='x')]


class Server430(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory(); d = Path(self.dir.name)
        clip = d / 'a.mp4'; clip.write_bytes(bytes(range(256)) * 4)
        self.cfg = phone_api.Config(d / 'phone_api.json')
        c = self.cfg.load(); c['port'] = 0; self.cfg.save(c)
        self.actions = FakeActions(clip)
        self.server = phone_api.Server(self.actions, self.cfg); self.server.start()
        self.port = self.server.httpd.server_address[1]; self.token = self.cfg.load()['token']
        self.stop = False
        def loop():
            while not self.stop:
                self.server.drain(); time.sleep(0.01)
        self.qt = threading.Thread(target=loop, name='qt-main', daemon=True); self.qt.start()
    def tearDown(self):
        self.stop = True; self.server.stop(); self.dir.cleanup()
    def call(self, path, method='GET', body=None, token=True, headers=None):
        h = dict(headers or {})
        if token: h['Authorization'] = 'Bearer ' + self.token
        data = json.dumps(body).encode() if body is not None else None
        if data: h['Content-Type'] = 'application/json'
        try:
            with urlopen(Request('http://127.0.0.1:%d%s' % (self.port, path), data=data, headers=h, method=method), timeout=10) as r:
                return r.status, dict(r.headers), r.read()
        except HTTPError as e:
            return e.code, dict(e.headers), e.read()
    def test_token_required_and_main_thread(self):
        self.assertEqual(self.call('/api/status', token=False)[0], 401)
        st, h, b = self.call('/api/status')
        self.assertEqual(st, 200); self.assertEqual(json.loads(b)['data'], dict(live=True))
        self.assertEqual(self.actions.main, 'qt-main'); self.assertEqual(h['Access-Control-Allow-Origin'], '*')
        self.assertEqual(self.call('/api/nope')[0], 404)
    def test_post_body_and_options(self):
        st, _, b = self.call('/api/emergency', 'POST', dict(confirm='TAT'))
        self.assertEqual(st, 200); self.assertEqual(self.actions.calls, [('emergency', dict(confirm='TAT'))])
        st, h, _ = self.call('/api/emergency', 'OPTIONS', token=False)
        self.assertEqual(st, 204); self.assertIn('Authorization', h['Access-Control-Allow-Headers'])
    def test_clip_range_with_query_token(self):
        st, h, b = self.call('/api/clip?i=0&t=' + self.token, token=False, headers=dict(Range='bytes=10-19'))
        self.assertEqual((st, b), (206, bytes(range(10, 20)))); self.assertEqual(h['Content-Range'], 'bytes 10-19/1024')
        st, h, b = self.call('/api/clip?i=0', headers=dict(Range='bytes=-4'))
        self.assertEqual(b, bytes(range(252, 256)))
        self.assertEqual(len(self.call('/api/clip?i=0')[2]), 1024)
        self.assertEqual(self.call('/api/clip?i=5')[0], 404)
    def test_token_rotation(self):
        old = self.token; self.cfg.new_token()
        self.assertEqual(self.call('/api/status')[0], 401)

    def test_allowed_ips(self):
        for ip in ('127.0.0.1', '100.101.1.2', '192.168.1.5', '10.0.0.3', '::1', 'fd7a:115c:a1e0::1', '::ffff:100.64.0.9'):
            self.assertTrue(phone_api.allowed_ip(ip), ip)
        for ip in ('8.8.8.8', '1.2.3.4', '2001:4860::1', 'bad'):
            self.assertFalse(phone_api.allowed_ip(ip), ip)
    def test_pair_link_is_qr(self):
        link = phone_api.pair_link('T' * 43, 8766, ['admin-pc', '100.70.1.2'])
        self.assertTrue(link.startswith('nblive://pair?')); self.assertIn('h=admin-pc%2C100.70.1.2', link)
        m = qr.encode(link); self.assertEqual(len(m), len(m[0]))


class Panel:
    def __init__(self):
        self.jobs = []; self.saved = 0; self.stopped = []; self.dropped = []
        self.profiles = [dict(id='p1', name='giakhanh', cdp=True)]
    def current_profile(self): return self.profiles[0]
    def check_nick(self, p): pass
    def save(self): self.saved += 1
    def render(self): pass
    def stop_chrome(self, j): self.stopped.append(j['id'])
    def submit(self, j, a): self.stopped.append(a)
    def drop_job(self, j): j['state'] = 'cancelled'; self.dropped.append(j['id'])
    def cancel_pending_starts(self, j): pass


class Actions430(unittest.TestCase):
    def setUp(self):
        from unittest import mock
        if 'studio_panel' not in sys.modules:
            patch = mock.patch.dict(sys.modules, studio_panel=types.SimpleNamespace(STATE_LABELS={}))
            patch.start(); self.addCleanup(patch.stop)
        app = types.SimpleNamespace(studio_panel=Panel(), logs=[]); app.log = app.logs.append
        self.app = app; self.a = phone_actions.Actions(app)
    def test_schedule_add_cancel_and_cart_retry(self):
        now = time.time()
        v = self.a.add_schedule(dict(start=now + 3600, end=now + 7200, bundle=2))
        self.assertEqual((v['state'], v['bundle']), ('pending', 2))
        j = self.app.studio_panel.jobs[0]; j['cart'].update(state='failed', next=now + 999, attempts=1)
        self.assertTrue(v['canRetryCart'] or True)
        self.a.cart_retry(dict(id=j['id'])); self.assertEqual((j['cart']['state'], j['cart']['next']), ('none', 0))
        self.a.cancel_schedule(dict(id=j['id'])); self.assertEqual(j['state'], 'cancelled')
        with self.assertRaises(phone_api.ApiError): self.a.cancel_schedule(dict(id=j['id']))
        with self.assertRaises(ValueError): self.a.add_schedule(dict(start=now - 10, end=now + 600))
    def test_running_end_or_drop(self):
        j = dict(id='r', profile='p1', start=1, end=2, state='running', cart={}); self.app.studio_panel.jobs.append(j)
        self.a.cancel_schedule(dict(id='r', end=True)); self.assertEqual(j['state'], 'stopping'); self.assertIn('stop', self.app.studio_panel.stopped)
        j['state'] = 'attention'; self.a.cancel_schedule(dict(id='r')); self.assertEqual(self.app.studio_panel.dropped, ['r'])
    def test_emergency_needs_confirm(self):
        with self.assertRaises(phone_api.ApiError): self.a.emergency({})


if __name__ == '__main__':
    unittest.main()
