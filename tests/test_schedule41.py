import sys, time, unittest
from concurrent.futures import Future
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from panel_harness import make, job, CLIP
import studio_scheduler as S
import studio_vision_logic as L


def done(result=None, error=None):
    f = Future()
    f.set_exception(error) if error else f.set_result(result or {})
    return f


class Decisions(unittest.TestCase):
    def test_late_start_is_still_made_while_time_remains(self):
        now = time.time(); j = job(start=now-240, end=now+3000)
        self.assertEqual(S.decisions([j], now), [(j, 'prepare')])

    def test_no_start_in_the_last_minute(self):
        now = time.time(); j = job(start=now-3000, end=now+30)
        self.assertEqual(S.decisions([j], now), []); self.assertEqual(j['state'], 'skipped')

    def test_sales_live_waits_for_cart(self):
        now = time.time(); j = job(start=now-5, end=now+3000)
        self.assertEqual(S.decisions([j], now, lambda j: False), []); self.assertEqual(j['state'], 'pending')

    def test_failed_stop_is_retried(self):
        now = time.time(); j = job(state='stop_retry', retry_at=now-1)
        self.assertEqual(S.decisions([j], now), [(j, 'stop')])

    def test_add_job_needs_bundle_and_two_minutes(self):
        now = time.time()
        with self.assertRaises(ValueError): S.add_job([], 'p', now+60, now+100, ['/a.mp4'], now=now)
        j = S.add_job([], 'p', now+60, now+3600, ['/a.mp4'], bundle_index=3, now=now)
        self.assertEqual((j['bundle_index'], j['cart']['state']), (3, 'none'))


class Cart(unittest.TestCase):
    def test_cart_is_prepared_right_away_with_chosen_set(self):
        p = make([job()]); p.poll_cart(time.time())
        cmd = p.owner.bridge.commands[-1]
        self.assertEqual((cmd['action'], cmd['bundleIndex'], cmd['preLive']), ('prepare_bundle', 2, True))

    def test_never_adds_while_the_nick_is_live(self):
        now = time.time()
        p = make([job(id='live', state='running', start=now-60, end=now+60), job(id='next', start=now+600)])
        p.poll_cart(now); self.assertEqual(p.owner.bridge.commands, [])

    def test_next_live_without_sales_means_no_cart_now(self):
        now = time.time(); p = make([job(id='a', no_sales=True, start=now+300), job(id='b', start=now+3000)])
        p.poll_cart(now); self.assertEqual(p.owner.bridge.commands, [])

    def test_done_partial_add_is_ready_and_checked_before_start(self):
        now = time.time(); j = job(start=now+600); p = make([j]); p.poll_cart(now)
        p.owner.bridge.control = dict(id='cmd1', state='done', added='8', total='10', bundle='MỚI NHẤT')
        p.poll_cart(now)
        self.assertEqual(j['cart']['state'], 'ready'); self.assertFalse(j['cart']['verified'])
        p.poll_cart(j['start']-100)
        self.assertEqual(p.owner.bridge.commands[-1]['action'], 'cart_check')
        p.owner.bridge.control = dict(id='cmd2', state='done', count='8'); p.poll_cart(j['start']-95)
        self.assertTrue(j['cart']['verified']); self.assertTrue(p.cart_ready(j))

    def test_cart_emptied_by_tiktok_is_added_again_once(self):
        now = time.time(); j = job(start=now+100, cart=dict(state='ready', attempts=0, next=0, verified=False, probe=dict(at=now, live=False))); p = make([j])
        p.poll_cart(now)
        p.owner.bridge.control = dict(id='cmd1', state='done', count='0'); p.poll_cart(now)
        self.assertEqual(j['cart']['state'], 'none'); self.assertTrue(any('TRỐNG' in a for a in p.alerts))
        p.poll_cart(now); self.assertEqual(p.owner.bridge.commands[-1]['action'], 'prepare_bundle')

    def test_three_failures_mean_no_live(self):
        now = time.time(); j = job(start=now+60); p = make([j])
        for i in range(3):
            j['cart']['probe'] = dict(at=now + i*400, live=False); p.poll_cart(now + i*400)
            p.owner.bridge.control = dict(id='cmd%d' % (i+1), state='failed', error='Không có bộ sản phẩm số 2')
            p.poll_cart(now + i*400 + 1)
        p.poll_cart(now + 2000)            # 4.1.7: first looks whether the cart still has products
        self.assertEqual(p.owner.bridge.commands[-1]['action'], 'cart_check')
        p.owner.bridge.control = dict(id='cmd4', state='done', count='0'); p.poll_cart(now + 2001); p.poll_cart(now + 2002)
        self.assertEqual(j['cart']['attempts'], 3); self.assertTrue(any('KHÔNG PHÁT' in a for a in p.alerts))
        self.assertFalse(p.cart_ready(j))

    def test_chrome_not_connected_counts_as_failure(self):
        now = time.time(); j = job(); p = make([j]); p.owner.bridge.down = True
        p.poll_cart(now); self.assertEqual((j['cart']['state'], j['cart']['attempts']), ('failed', 1))


class StartStop(unittest.TestCase):
    def test_failed_start_is_retried_then_adopted_when_studio_is_live(self):
        now = time.time(); j = job(state='starting', start=now-10, end=now+3000); p = make([j])
        p.action_failed(j, 'start', ValueError('Chưa thấy nút "Phát LIVE"'))
        self.assertEqual(j['state'], 'start_retry'); self.assertTrue(p.alerts)
        j['state'] = 'preparing'; p.futures = {done(dict(live=True)): ('j1', None, 'preflight')}
        p.tick(); self.assertEqual(j['state'], 'running')

    def test_start_failing_near_the_end_gives_up_loudly(self):
        now = time.time(); j = job(state='starting', start=now-3000, end=now+70); p = make([j])
        p.action_failed(j, 'start', ValueError('x')); self.assertEqual(j['state'], 'failed')
        self.assertTrue(any('KHÔNG phát được' in a for a in p.alerts))

    def test_stop_is_retried_five_times_then_shouts(self):
        j = job(state='stopping'); p = make([j])
        for _ in range(S.STOP_TRIES): p.action_failed(j, 'stop', ValueError('menu'))
        self.assertEqual(j['state'], 'attention'); self.assertIn('CÓ THỂ VẪN ĐANG CHẠY', p.alerts[-1])

    def test_started_enables_messages_greetings_and_chrome(self):
        j = job(state='starting'); p = make([j]); p.profiles[0]['interaction'] = dict(auto_message=True, auto_greeting=True)
        p.on_started(j, 'Đã phát LIVE')
        self.assertEqual(sorted(p.enabled), ['greeting', 'message'])
        p.poll_chrome_modules(time.time()+11)
        self.assertEqual([c['module'] for c in p.owner.bridge.commands], ['reply', 'pin'])

    def test_stop_success_keeps_video_playing_and_closes_chrome_summary(self):
        # 4.1.2 (owner, 19/10/2026 02:40): NBL never stops the owner's NBL VIDEO.
        j = job(state='stopping'); p = make([j]); p.futures = {done(dict(live=False)): ('j1', None, 'stop')}
        p.tick()
        self.assertEqual(j['state'], 'finished'); self.assertNotIn(('stop', 's1'), p.played)
        self.assertEqual(p.owner.bridge.commands[-1]['action'], 'finish_live')

    def test_status_warning_still_marks_attention(self):
        j = job(state='running', start=time.time()-60); p = make([j])
        p.futures = {done(error=L.StudioAttention('Violation')): ('j1', None, 'status')}
        p.tick(); self.assertEqual(j['state'], 'attention'); self.assertEqual(len(p.alerts), 1)


class Dark(unittest.TestCase):
    def test_black_screen_alerts_restarts_video_then_ends_live(self):
        now = time.time(); j = job(state='running', started_at=now-60); p = make([j])
        p.watch_dark(j, dict(fps=0, upload=0))
        self.assertTrue(any('MÀN HÌNH ĐEN' in a for a in p.alerts)); self.assertIn(('play', 's1'), p.played)
        j['dark_since'] = now - 130; p.watch_dark(j, dict(fps=0, upload=0))
        self.assertEqual(j['state'], 'stopping'); self.assertIn(('j1', 'stop'), p.submitted)

    def test_picture_back_resets(self):
        j = job(state='running', started_at=time.time()-60, dark_since=time.time()-30); p = make([j])
        p.watch_dark(j, dict(fps=30, upload=3000)); self.assertEqual(j['dark_since'], 0)

    def test_unreadable_status_line_is_not_black(self):
        j = job(state='running', started_at=time.time()-60); p = make([j])
        p.watch_dark(j, dict(fps=None, upload=None)); self.assertFalse(j.get('dark_since'))


class TwoNicks(unittest.TestCase):
    def test_same_speaker_for_two_lives_is_warned(self):
        profiles = [dict(id='p1', name='A', session='s1', vision={}), dict(id='p2', name='B', session='s2', vision={})]
        sessions = {'s1': dict(id='s1', device='', mute=False, playlist=[CLIP]), 's2': dict(id='s2', device='', mute=False, playlist=[CLIP])}
        a = job(id='a', profile='p1', state='preparing'); b = job(id='b', profile='p2', state='running')
        p = make([a, b], profiles, sessions); p.start_video(a)
        self.assertTrue(any('CHUNG một loa' in x for x in p.alerts)); self.assertIn(('play', 's1'), p.played)

    def test_separate_devices_are_fine(self):
        profiles = [dict(id='p1', name='A', session='s1', vision={}), dict(id='p2', name='B', session='s2', vision={})]
        sessions = {'s1': dict(id='s1', device='CABLE-A', mute=False, playlist=[CLIP]), 's2': dict(id='s2', device='CABLE-B', mute=False, playlist=[CLIP])}
        a = job(id='a', profile='p1', state='preparing'); b = job(id='b', profile='p2', state='running')
        p = make([a, b], profiles, sessions); p.start_video(a); self.assertEqual(p.alerts, [])

    def test_other_nick_overlap_is_reported(self):
        now = time.time(); jobs = [job(profile='p2', start=now+100, end=now+1000)]
        self.assertEqual(len(S.overlapping_other_nicks(jobs, 'p1', now+500, now+2000)), 1)


if __name__ == '__main__':
    unittest.main()
