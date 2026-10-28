import tempfile, unittest
from pathlib import Path
import live_chrome as L

D = L.DASHBOARD


class FakeChrome:
    def __init__(self):
        self.up = False; self.tabs = []; self.states = {}; self.log = []; self.n = 0
    def alive(self): return self.up
    def pages(self): return [dict(t) for t in self.tabs]
    def open(self, url):
        self.n += 1; t = dict(id='t%d' % self.n, type='page', url=url.split('#')[0]); self.tabs.append(t); self.log.append(('open', t['id'])); return t
    def close(self, i): self.tabs = [t for t in self.tabs if t['id'] != i]; self.log.append(('close', i))
    def page_state(self, t): return self.states.get(t['id'], {})
    def reload(self, t): self.log.append(('reload', t['id']))


class Watch(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory(); self.t = [1000.0]; self.c = FakeChrome(); self.launched = []
        def launcher(profile, url): self.launched.append(url); self.c.up = True
        self.w = L.Watchdog(Path(self.dir.name) / 'p', lambda: D + '#nbl=' + 'a' * 32, chrome=self.c, launcher=launcher, now=lambda: self.t[0])
    def tearDown(self): self.dir.cleanup()
    def tick(self, s=5, busy=False): self.t[0] += s; return self.w.step(busy)

    def test_not_started_until_asked_then_relaunched_when_closed(self):
        self.assertEqual(self.tick()['state'], 'off'); self.assertEqual(self.launched, [])
        self.w.start(); self.assertEqual(len(self.launched), 1)
        self.c.up = False; self.assertEqual(self.tick()['state'], 'starting'); self.assertEqual(len(self.launched), 1)   # waits 45 s
        self.tick(50); self.assertEqual(len(self.launched), 2)

    def test_exactly_one_tab_extra_closed_linked_kept(self):
        self.c.up = True; self.w.wanted = True
        r = self.tick(); self.assertIn('mở trang LIVE', r['actions']); self.assertEqual(len(self.c.tabs), 1)
        self.tick(); self.assertEqual(len(self.c.tabs), 1)          # no second tab while loading
        self.c.tabs.append(dict(id='x', type='page', url=D)); self.c.states['x'] = dict(client='C1', beat=10_000, now=11_000)
        r = self.tick()
        self.assertEqual([t['id'] for t in self.c.tabs], ['x']); self.assertEqual((r['state'], r['client']), ('ok', 'C1'))

    def test_frozen_page_reloaded_same_tab_never_new(self):
        self.c.up = True; self.w.wanted = True; self.c.tabs.append(dict(id='a', type='page', url=D))
        self.c.states['a'] = dict(client='C1', beat=1000, now=1000 + 60_000)  # heartbeat 60 s old
        self.tick(); r = self.tick(60)
        self.assertIn(('reload', 'a'), self.c.log); self.assertFalse(any(x[0] == 'open' for x in self.c.log))
        self.tick(5); self.assertEqual(sum(1 for x in self.c.log if x[0] == 'reload'), 1)   # max once a minute

    def test_busy_page_with_recent_beat_is_not_reloaded(self):
        self.c.up = True; self.w.wanted = True; self.c.tabs.append(dict(id='a', type='page', url=D))
        self.c.states['a'] = dict(client='C1', beat=1000, now=1000 + 30_000)
        self.tick(); self.tick(60, busy=True); self.assertNotIn(('reload', 'a'), self.c.log)

    def test_login_and_no_extension(self):
        self.c.up = True; self.w.wanted = True
        self.c.tabs.append(dict(id='l', type='page', url='https://seller-vn.tiktok.com/account/login')); self.c.states['l'] = dict(login=True)
        self.assertEqual(self.tick()['state'], 'login'); self.assertFalse(any(x[0] == 'open' for x in self.c.log))
        self.c.tabs = [dict(id='a', type='page', url=D)]; self.c.states = {}
        states = [self.tick(65)['state'] for _ in range(5)]
        self.assertIn('no_extension', states)

    def test_dashboard_url_match(self):
        self.assertTrue(L.is_dashboard(D + '#nbl=x')); self.assertTrue(L.is_dashboard(D + '?a=1'))
        self.assertFalse(L.is_dashboard('https://shop.tiktok.com/streamer/live/product/dashboardx'))


if __name__ == '__main__':
    unittest.main()
