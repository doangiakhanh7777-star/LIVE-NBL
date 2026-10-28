"""4.1.7 (owner 20–21/10/2026):
- The owner started a LIVE by hand, then saved schedules → "thêm giỏ lỗi" and the LIVE
  never started. Rule now: while the nick is LIVE NBL does not touch the cart; when a
  schedule is due and the hand LIVE is still on, NBL ends it and moves the schedule
  30 minutes (default rule).
- The set could not be added 3 times but the cart has products → the LIVE goes ahead.
- 13:58 "Studio đã mở lại thành cửa sổ mới nhưng NBL không chắc…": Studio's own
  small windows made two candidates; a Studio that is closed means the LIVE is over."""
import sys, time, unittest
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from panel_harness import make, job
import studio_scheduler as S
import studio_vision as V
from studio_vision_logic import StudioAttention

EXE = r'C:\Program Files\TikTok LIVE Studio\TikTok LIVE Studio.exe'
OLD = dict(name='giakhanhdoxe', exePath=EXE, windowTitle='TikTok LIVE Studio', windowHandle='111', pid='10', accountAnchor='a',
           vision=dict(enabled=True, regions=dict(clock=[1, 1, 9, 9])))


def win(handle, pid, w=0, h=0, title='TikTok LIVE Studio'):
    return dict(windowHandle=str(handle), pid=str(pid), exePath=EXE, windowTitle=title, width=w, height=h)


def done(result=None, error=None):
    f = Future()
    f.set_exception(error) if error else f.set_result(result)
    return f


def feed(p, j, action, result=None, error=None):
    p.futures[done(result, error)] = (j['id'], None, action); p.tick()


class HandLiveCart(unittest.TestCase):
    def test_nick_is_looked_at_before_the_cart_is_touched(self):
        now = time.time(); j = job(start=now + 3600, cart=dict(state='none', attempts=0, next=0, reloaded_at=now - 60)); p = make([j])
        p.poll_cart(now)
        self.assertEqual(p.owner.bridge.commands, []); self.assertIn(('j1', 'live_probe'), p.submitted)

    def test_cart_waits_while_the_nick_is_live_by_hand(self):
        now = time.time(); j = job(start=now + 3600, cart=dict(state='none', attempts=0, next=0, reloaded_at=now - 60)); p = make([j])
        feed(p, j, 'live_probe', dict(live=True))
        self.assertTrue(j['cart']['probe']['live'])
        p.poll_cart(time.time() + 1)
        self.assertEqual([c for c in p.owner.bridge.commands if c['action'] == 'prepare_bundle'], [])
        self.assertEqual(j['cart']['attempts'], 0); self.assertEqual(j['state'], 'pending')
        feed(p, j, 'live_probe', dict(live=False))       # the hand LIVE ended
        p.poll_cart(time.time() + 1)
        self.assertEqual(p.owner.bridge.commands[-1]['action'], 'prepare_bundle')

    def test_unreadable_studio_does_not_block_the_cart(self):
        now = time.time(); j = job(start=now + 3600, cart=dict(state='none', attempts=0, next=0, reloaded_at=now - 60)); p = make([j])
        feed(p, j, 'live_probe', error=RuntimeError('timed out'))
        self.assertEqual(j['state'], 'pending'); self.assertIsNone(j['cart']['probe']['live'])
        p.poll_cart(time.time() + 1); self.assertEqual(p.owner.bridge.commands[-1]['action'], 'prepare_bundle')

    def test_due_schedule_goes_on_to_studio_when_the_nick_is_live_by_hand(self):
        now = time.time(); j = job(start=now - 5, end=now + 3600, cart=dict(state='none', attempts=0, next=0, probe=dict(at=now, live=True)))
        p = make([j]); self.assertTrue(p.cart_ready(j))


class HandLiveTakeover(unittest.TestCase):
    def test_hand_live_at_schedule_time_is_ended_and_the_schedule_moves_30_minutes(self):
        now = time.time(); j = job(start=now - 5, end=now + 3595, state='preparing', prepare_phase='preflight'); p = make([j])
        feed(p, j, 'preflight', dict(live=True))
        self.assertEqual((j['state'], j['takeover']), ('stopping', True)); self.assertIn(('j1', 'stop'), p.submitted)
        self.assertTrue(any('LIVE bật tay' in a for a in p.alerts))
        feed(p, j, 'stop', dict(live=False))
        t = time.time()
        self.assertEqual(j['state'], 'pending'); self.assertNotIn('takeover', j)
        self.assertAlmostEqual(j['start'], t + 1800, delta=5); self.assertAlmostEqual(j['end'] - j['start'], 3600, delta=1)
        self.assertEqual(j['cart'], dict(state='none', attempts=0, next=0))      # cart prepared again
        self.assertTrue(any('dời sang' in a for a in p.alerts))

    def test_moved_schedule_never_runs_into_the_next_one(self):
        now = time.time()
        j = job(start=now - 5, end=now + 3595, state='stopping', takeover=True)
        nxt = job(id='j2', start=now + 3600, end=now + 7200)
        p = make([j, nxt]); feed(p, j, 'stop', dict(live=False))
        self.assertEqual(j['state'], 'pending'); self.assertLessEqual(j['end'], nxt['start'] - 60)

    def test_no_room_left_means_the_schedule_is_dropped(self):
        now = time.time()
        j = job(start=now - 5, end=now + 3595, state='stopping', takeover=True)
        nxt = job(id='j2', start=now + 1850, end=now + 7200)
        p = make([j, nxt]); feed(p, j, 'stop', dict(live=False))
        self.assertEqual(j['state'], 'skipped')

    def test_hand_live_that_could_not_be_ended_and_then_stops_moves_the_schedule(self):
        now = time.time(); j = job(start=now - 5, end=now + 3595, state='attention', takeover=True); p = make([j])
        feed(p, j, 'status', dict(live=False))
        self.assertEqual(j['state'], 'pending')

    def test_own_live_after_an_earlier_click_is_still_adopted(self):
        now = time.time(); j = job(start=now - 5, end=now + 3595, state='preparing', start_attempts=1); p = make([j])
        feed(p, j, 'preflight', dict(live=True))
        self.assertEqual(j['state'], 'running')


class StrictCart(unittest.TestCase):
    # 4.2.0 (owner, 28/10/2026): NO VERIFIED CART = NO SALES LIVE. No old cart, no fallback.
    def failed(self, now):
        return job(start=now - 5, end=now + 3600, cart=dict(state='failed', attempts=3, next=now + 60, probe=dict(at=now, live=False), reloaded_at=now - 30))

    def test_set_not_added_never_goes_live_even_with_products_in_the_cart(self):
        now = time.time(); j = self.failed(now); p = make([j])
        p.poll_cart(now)
        self.assertNotIn('cart_check', [c['action'] for c in p.owner.bridge.commands])
        self.assertFalse(p.cart_ready(j))
        self.assertTrue(any('CHƯA PHÁT' in a for a in p.alerts))

    def test_failed_add_retries_on_a_reloaded_page(self):
        now = time.time(); j = self.failed(now); p = make([j])
        p.cart_failed(j, j['cart'], 'lỗi', now)
        self.assertEqual(j['cart']['reloaded_at'], 0)
        j['cart']['probe'] = dict(at=now + 61, live=False)     # Studio seen NOT LIVE
        p.poll_cart(now + 61); self.assertEqual(p.owner.bridge.commands[-1]['action'], 'reload_page')
        p.poll_cart(now + 82); self.assertEqual(p.owner.bridge.commands[-1]['action'], 'prepare_bundle')

    def test_added_set_is_checked_before_it_counts(self):
        now = time.time(); j = job(start=now + 50, end=now + 3600); p = make([j])
        j['cart'].update(command='cmd1', kind='add', until=now + 160, state='preparing'); p.owner.bridge.control = dict(id='cmd1', state='done', added=5, total=5)
        p.poll_cart(now)
        self.assertEqual(j['cart']['state'], 'ready'); self.assertFalse(p.cart_ready(j))
        p.poll_cart(now + 1); self.assertEqual(p.owner.bridge.commands[-1]['action'], 'cart_check')
        p.owner.bridge.control = dict(id=j['cart']['command'], state='done', count='5'); p.poll_cart(now + 2)
        self.assertTrue(p.cart_ready(j))

    def test_unreadable_or_empty_cart_is_not_ready(self):
        for count in ('-1', '0'):
            now = time.time(); j = job(start=now + 100, end=now + 3600); p = make([j])
            j['cart'].update(state='ready', verified=False, v420=True, for_bundle=2, count=0, command='cmd1', kind='check', until=now + 20)
            p.owner.bridge.control = dict(id='cmd1', state='done', count=count); p.poll_cart(now)
            self.assertFalse(p.cart_ready(j), count)

    def test_old_fallback_or_other_bundle_is_not_ready(self):
        now = time.time(); p = make([])
        for cart in (dict(state='ready', verified=True, v420=True, for_bundle=2, count=9, fallback=True),
                     dict(state='ready', verified=True, v420=True, for_bundle=1, count=9),
                     dict(state='ready', verified=True, count=9)):
            j = job(start=now - 5, cart=cart); self.assertFalse(p.cart_ok(j))

    def test_hand_live_over_at_preflight_without_cart_does_not_start(self):
        now = time.time(); j = job(start=now - 5, end=now + 3600, state='preparing', cart=dict(state='none', attempts=0, next=0, probe=dict(at=now, live=True)))
        p = make([j]); feed(p, j, 'preflight', dict(live=False))
        self.assertEqual(j['state'], 'pending'); self.assertEqual(p.played, [])

    def test_slot_over_without_cart_is_dropped_and_told(self):
        now = time.time(); j = job(start=now - 3000, end=now + 30, cart=dict(state='failed', attempts=9, next=now + 60, probe=dict(at=now, live=False)))
        p = make([j]); p.tick()
        self.assertEqual(j['state'], 'skipped'); self.assertTrue(any('BỎ LỊCH' in a and 'giỏ chưa xác nhận' in a for a in p.alerts))


class Rebind(unittest.TestCase):
    def test_main_window_wins_over_studio_small_windows(self):
        new = S.rebind_window(OLD, [win(222, 20, 1600, 900), win(223, 20, 340, 600)])
        self.assertEqual(new['windowHandle'], '222')

    def test_two_big_windows_are_still_not_guessed(self):
        self.assertIsNone(S.rebind_window(OLD, [win(222, 20, 1600, 900), win(333, 30, 1500, 850)]))

    def broken_vision(self, profile, action, deadline=0, payload=None):
        raise StudioAttention('Cửa sổ Studio đã đổi. Kết nối lại cửa sổ, giữ các vùng đã lưu.')

    def test_closed_studio_means_the_live_is_over(self):
        with patch.object(S.os, 'name', 'nt'), patch.object(V, 'execute_vision', self.broken_vision), patch.object(S, 'list_windows', lambda: []):
            self.assertEqual(S.execute(dict(OLD), 'stop'), {'live': False, 'studioClosed': True, 'closed': True})
            with self.assertRaises(StudioAttention):
                S.execute(dict(OLD), 'start')          # never "started" on a closed Studio

    def test_window_list_failure_is_not_taken_as_closed(self):
        def broken(): raise RuntimeError('powershell')
        with patch.object(S.os, 'name', 'nt'), patch.object(V, 'execute_vision', self.broken_vision), patch.object(S, 'list_windows', broken):
            with self.assertRaises(StudioAttention):
                S.execute(dict(OLD), 'stop')

    def test_window_list_reports_the_size(self):
        src = (Path(S.__file__).with_name('studio_window.ps1')).read_text(encoding='utf-8-sig')
        self.assertIn('GetWindowRect', src); self.assertIn('width=', src)


if __name__ == '__main__':
    unittest.main()
