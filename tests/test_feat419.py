"""4.1.9 (owner 26/10/2026):
1. After EVERY LIVE end (another schedule or not) NBL keeps looking at Studio and
   closes its end page ("tab cuối cùng").
2. Chrome reloads the LIVE page before adding the cart and once before the LIVE.
3. "Lịch ghim theo giờ clip": the app sends the NBL VIDEO position to Chrome."""
import json, sys, tempfile, time, types, unittest
from concurrent.futures import Future
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from panel_harness import make, job
import studio_vision as V


def done(result=None, error=None):
    f = Future(); f.set_exception(error) if error else f.set_result(result); return f


def feed(p, j, action, result=None, error=None):
    p.futures[done(result, error)] = (j['id'], None, action); p.tick()


class StudioEndPage(unittest.TestCase):
    def test_every_finished_live_is_watched_and_the_page_closed(self):
        now = time.time(); j = job(start=now - 600, end=now - 5, state='stopping'); p = make([j])
        p.on_stopped(j)
        self.assertGreater(j['summary_until'], now + 100)
        p.poll_summary(time.time() + 3); self.assertIn(('j1', 'close_summary'), p.submitted)
        feed(p, j, 'close_summary', dict(closed=True, seen=True))
        self.assertNotIn('summary_until', j)

    def test_page_not_there_yet_is_looked_for_again(self):
        now = time.time(); j = job(start=now - 600, end=now - 5, state='finished', summary_until=now + 100, summary_next=0); p = make([j])
        feed(p, j, 'close_summary', dict(closed=False, seen=False))
        self.assertIn('summary_until', j)
        p.submitted.clear(); p.poll_summary(time.time() + 4); self.assertIn(('j1', 'close_summary'), p.submitted)

    def test_live_ended_outside_the_schedule_is_cleaned_too(self):
        now = time.time(); j = job(start=now - 600, end=now + 600, state='running'); p = make([j])
        feed(p, j, 'status', dict(live=False))
        self.assertEqual(j['state'], 'manual_stop'); self.assertIn('summary_until', j)
        self.assertIn('finish_live', [c['action'] for c in p.owner.bridge.commands])

    def test_never_while_the_next_live_of_the_nick_is_being_started(self):
        now = time.time()
        a = job(id='a', start=now - 600, end=now - 5, state='finished', summary_until=now + 100, summary_next=0)
        b = job(id='b', start=now - 2, end=now + 3600, state='preparing')
        p = make([a, b]); p.poll_summary(now)
        self.assertNotIn(('a', 'close_summary'), p.submitted)

    def test_a_failure_never_touches_the_job_and_is_reported_at_the_end(self):
        now = time.time(); j = job(start=now - 600, end=now - 5, state='finished', summary_until=now + 100, summary_next=0); p = make([j])
        feed(p, j, 'close_summary', error=ValueError('Chưa đóng được trang tổng kết LIVE trên Studio.'))
        self.assertEqual(j['state'], 'finished')
        p.poll_summary(now + 200)
        self.assertNotIn('summary_until', j); self.assertTrue(any('Đóng tay' in a for a in p.alerts))

    def test_nick_without_image_reading_is_not_watched(self):
        now = time.time(); j = job(start=now - 600, end=now - 5, state='stopping'); p = make([j])
        p.profiles[0]['vision']['enabled'] = False; p.on_stopped(j)
        self.assertNotIn('summary_until', j)

    def test_vision_waits_for_a_late_page_and_closes_it(self):
        s = object.__new__(V.VisionSession)
        t = [0.0]; frames = iter([False, False, True])
        s.clock = lambda: t[0]; s.sleep = lambda d: t.__setitem__(0, t[0] + d)
        s.frame = lambda account=True: next(frames); s.summary_lines = lambda f: f; s.is_summary = lambda lines: lines
        closed = []; s.close_summary = lambda f: closed.append(f)
        self.assertEqual(s.cleanup_summary(20), dict(closed=True, seen=True)); self.assertEqual(closed, [True])

    def test_vision_gives_up_after_the_wait(self):
        s = object.__new__(V.VisionSession); t = [0.0]
        s.clock = lambda: t[0]; s.sleep = lambda d: t.__setitem__(0, t[0] + d)
        s.frame = lambda account=True: None; s.summary_lines = lambda f: []; s.is_summary = lambda lines: False
        self.assertEqual(s.cleanup_summary(10), dict(closed=False, seen=False))


class ChromeReload(unittest.TestCase):
    def test_page_is_reloaded_before_the_cart_is_added(self):
        now = time.time(); j = job(start=now + 3600, cart=dict(state='none', attempts=0, next=0, probe=dict(at=now, live=False)))
        p = make([j]); p.poll_cart(now)
        c = p.owner.bridge.commands[-1]
        self.assertEqual((c['action'], c['stopModules']), ('reload_page', True))
        p.poll_cart(now + 5); self.assertEqual(len(p.owner.bridge.commands), 1)          # waits for the page
        j['cart']['probe'] = dict(at=now + 21, live=False); p.poll_cart(now + 21)
        self.assertEqual(p.owner.bridge.commands[-1]['action'], 'prepare_bundle')

    def test_a_quick_retry_does_not_reload_again(self):
        now = time.time(); j = job(start=now + 600, cart=dict(state='failed', attempts=1, next=0, probe=dict(at=now, live=False), reloaded_at=now - 80))
        p = make([j]); p.poll_cart(now); self.assertEqual(p.owner.bridge.commands[-1]['action'], 'prepare_bundle')

    def test_page_is_reloaded_once_before_the_live_and_then_checked(self):
        now = time.time(); start = now + 170
        j = job(start=start, cart=dict(state='ready', attempts=0, next=0, verified=False, v415=True, probe=dict(at=now, live=False), reloaded_at=now - 3000))
        p = make([j]); p.poll_cart(now)
        self.assertEqual(p.owner.bridge.commands[-1]['action'], 'reload_page')
        p.poll_cart(start - 119); self.assertEqual(p.owner.bridge.commands[-1]['action'], 'cart_check')
        self.assertEqual([c['action'] for c in p.owner.bridge.commands].count('reload_page'), 1)

    def test_no_reload_under_a_live_the_owner_started_by_hand(self):
        now = time.time(); start = now + 170
        j = job(start=start, cart=dict(state='ready', attempts=0, next=0, verified=False, v415=True, probe=dict(at=now - 300, live=False), reloaded_at=now - 3000))
        p = make([j]); p.poll_cart(now)
        self.assertIn(('j1', 'live_probe'), p.submitted); self.assertEqual(p.owner.bridge.commands, [])
        j['cart']['probe'] = dict(at=now + 1, live=True); p.poll_cart(now + 1)
        self.assertNotIn('reload_page', [c['action'] for c in p.owner.bridge.commands])

    def test_bridge_accepts_the_new_commands(self):
        from chrome_bridge import ChromeBridge
        b = ChromeBridge(port=1); b.clients['c'] = dict(queue=[], ws=None)
        for action in ('reload_page', 'clip_sync'):
            b.command('c', dict(action=action, module='all'))
        self.assertEqual([c['action'] for c in b.clients['c']['queue']], ['reload_page', 'clip_sync'])


class ClipSync(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()); (self.tmp/'runtime'/'s1').mkdir(parents=True)

    def write(self, t=None, **kw):
        (self.tmp/'runtime'/'s1'/'status.json').write_text(json.dumps(dict(time=t or time.time(), state='PlayingState', position=65000, duration=600000, path='C:/clip.mp4', **kw)), encoding='utf-8')

    def test_running_live_sends_the_video_position_every_10_seconds(self):
        now = time.time(); j = job(start=now - 60, end=now + 3600, state='running'); p = make([j])
        p.owner.path = types.SimpleNamespace(parent=self.tmp); self.write()
        p.poll_clip(now); c = p.owner.bridge.commands[-1]
        self.assertEqual((c['action'], c['position'], c['duration'], c['playing']), ('clip_sync', 65000, 600000, True))
        p.poll_clip(now + 5); self.assertEqual(len(p.owner.bridge.commands), 1)
        self.write(now + 10); p.poll_clip(now + 10); self.assertEqual(len(p.owner.bridge.commands), 2)

    def test_old_video_status_is_not_sent(self):
        now = time.time(); j = job(start=now - 60, end=now + 3600, state='running'); p = make([j])
        p.owner.path = types.SimpleNamespace(parent=self.tmp)
        (self.tmp/'runtime'/'s1'/'status.json').write_text(json.dumps(dict(time=now - 60, state='PlayingState', position=1)), encoding='utf-8')
        p.poll_clip(now); self.assertEqual(p.owner.bridge.commands, [])


if __name__ == '__main__':
    unittest.main()


import test_summary413 as E
from unittest.mock import patch as _patch


class StuckEndPage(unittest.TestCase):
    """4.1.9: an end page whose X does nothing must not turn "LIVE ended" into
    "kết thúc thất bại 5 lần / LIVE CÓ THỂ VẪN ĐANG CHẠY"."""
    def setUp(self):
        self.p = _patch.object(V, 'report', lambda *a, **k: ''); self.p.start()
    def tearDown(self):
        self.p.stop()

    class Stuck(E.EndPage):
        def click(self, x, y):
            if self.screen in ('summary2', 'summary3'):
                self.log.append(('click', round(x), round(y))); return     # X does nothing
            E.EndPage.click(self, x, y)

    def test_live_ended_with_an_end_page_that_will_not_close(self):
        fake = self.Stuck('live'); r = E.session(fake).stop_live()
        self.assertEqual((r['live'], r['summaryOpen']), (False, True))

    def test_end_page_already_there_and_stuck(self):
        fake = self.Stuck('summary2'); r = E.session(fake).stop_live()
        self.assertEqual((r['live'], r['summaryOpen']), (False, True))
