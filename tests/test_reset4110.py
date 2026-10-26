"""4.1.10 (owner 26/10/2026): "thêm 3 lần mà không được thì lần thứ 4 … bấm phát live xong
kết thúc ngay (dưới 10 s), giỏ cũ trên Chrome sẽ reset lại". The test LIVE must never be
taken for an official LIVE (nor for a LIVE started by hand)."""
import re, sys, time, unittest
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from panel_harness import make, job
import studio_vision as V
import test_summary413 as E

ROOT = Path(__file__).resolve().parents[1]


def done(result=None, error=None):
    f = Future(); f.set_exception(error) if error else f.set_result(result); return f


def feed(p, j, action, result=None, error=None):
    p.futures[done(result, error)] = (j['id'], None, action); p.tick()


def fail_add(p, j, now, error='Chưa thấy "Đã thêm x/y" sau khi chờ'):
    j['cart']['probe'] = dict(at=now, live=False); j['cart']['reloaded_at'] = now - 60
    p.poll_cart(now); assert p.owner.bridge.commands[-1]['action'] == 'prepare_bundle', p.owner.bridge.commands[-1]
    p.owner.bridge.control = dict(id=j['cart']['command'], state='failed', error=error); p.poll_cart(now + 1)


class Reset(unittest.TestCase):
    def test_after_3_failed_adds_the_4th_try_is_a_test_live(self):
        now = time.time(); j = job(start=now + 3600); p = make([j])
        for i in range(3): fail_add(p, j, now + i * 200)
        self.assertTrue(j['cart']['reset_due'])
        t = now + 601; j['cart']['probe'] = dict(at=t, live=False); p.poll_cart(t)
        self.assertEqual(j['cart']['state'], 'resetting'); self.assertIn(('j1', 'reset_live'), p.submitted)
        self.assertEqual(j['state'], 'pending')                              # NOT an official LIVE
        self.assertTrue(any('phát thử LIVE' in a for a in p.alerts))

    def test_after_the_test_live_the_cart_is_added_again_at_once_on_a_reloaded_page(self):
        now = time.time(); j = job(start=now + 3600, cart=dict(state='resetting', attempts=3, next=0, reset_at=now)); p = make([j])
        feed(p, j, 'reset_live', dict(live=False, reset=True))
        self.assertEqual((j['state'], j['cart']['state']), ('pending', 'none'))
        self.assertNotIn('started_at', j)
        p.poll_cart(time.time() + 1)                                          # next app tick
        acts = [c['action'] for c in p.owner.bridge.commands]
        self.assertIn('finish_live', acts)                                    # Chrome "Chúc mừng" box
        self.assertIn('reload_page', acts)                                    # then the add follows 20 s later
        self.assertIn('summary_until', j)                                     # Studio end page watched

    def test_a_reset_is_done_every_3_failures_without_limit(self):
        now = time.time(); j = job(start=now + 9000); p = make([j])
        for i in range(6): fail_add(p, j, now + i * 200); j['cart'].pop('reset_due', None) if i == 2 else None
        self.assertTrue(j['cart']['reset_due'])

    def test_errors_a_reset_cannot_fix_do_not_start_a_live(self):
        now = time.time(); j = job(start=now + 3600); p = make([j])
        for i in range(3): fail_add(p, j, now + i * 200, 'Không có bộ sản phẩm số 2 (danh sách ít bộ hơn)')
        self.assertFalse(j['cart'].get('reset_due'))

    def test_never_while_the_nick_is_live(self):
        now = time.time(); j = job(start=now + 3600, cart=dict(state='failed', attempts=3, next=0, reset_due=True, probe=dict(at=now, live=True))); p = make([j])
        p.poll_cart(now); self.assertNotIn(('j1', 'reset_live'), p.submitted)

    def test_studio_unreadable_means_no_test_live(self):
        now = time.time(); j = job(start=now + 3600, cart=dict(state='failed', attempts=3, next=0, reset_due=True, probe=dict(at=now, live=None), reloaded_at=now - 60)); p = make([j])
        p.poll_cart(now); self.assertNotIn(('j1', 'reset_live'), p.submitted)
        self.assertEqual(p.owner.bridge.commands[-1]['action'], 'prepare_bundle')

    def test_a_test_live_that_may_still_run_is_ended_by_itself(self):
        now = time.time(); j = job(start=now + 3600, cart=dict(state='resetting', attempts=3, next=0, reset_at=now)); p = make([j])
        err = RuntimeError('PHIÊN PHÁT THỬ CÒN ĐANG CHẠY'); err.touched = True
        feed(p, j, 'reset_live', error=err)
        self.assertEqual(j['cart']['state'], 'reset_stopping'); self.assertEqual(j['state'], 'pending')
        p.submitted.clear(); p.poll_cart(time.time()); self.assertIn(('j1', 'reset_stop'), p.submitted)
        feed(p, j, 'reset_stop', dict(live=False, confirmed=True))
        self.assertEqual((j['state'], j['cart']['state']), ('pending', 'none'))   # never "Đã kết thúc"

    def test_nothing_clicked_means_a_normal_retry(self):
        now = time.time(); j = job(start=now + 3600, cart=dict(state='resetting', attempts=3, next=0)); p = make([j])
        err = RuntimeError('Studio chưa đọc được'); err.touched = False
        feed(p, j, 'reset_live', error=err)
        self.assertEqual(j['cart']['state'], 'failed')

    def test_still_unreadable_after_2_minutes_warns_loudly_and_goes_back_to_adding(self):
        now = time.time(); j = job(start=now + 3600, cart=dict(state='reset_stopping', attempts=3, next=0, reset_stop_tries=7)); p = make([j])
        err = RuntimeError('Không đọc được Studio'); err.touched = False
        feed(p, j, 'reset_stop', error=err)
        self.assertEqual(j['cart']['state'], 'failed'); self.assertTrue(any('KIỂM TRA TAY' in a for a in p.alerts))

    def test_due_schedule_right_after_a_test_live_is_not_taken_for_a_hand_live(self):
        now = time.time(); j = job(start=now - 5, end=now + 3600, state='preparing', prepare_phase='preflight', cart=dict(state='ready', verified=True, reset_at=now - 30))
        p = make([j]); feed(p, j, 'preflight', dict(live=True))
        self.assertEqual(j['state'], 'start_retry'); self.assertNotIn('takeover', j)

    def test_app_closed_during_a_test_live_checks_studio_first(self):
        src = (ROOT/'studio_panel.py').read_text(encoding='utf-8')
        self.assertIn("if j['cart'].get('state') in ('resetting','reset_stopping'):j['cart'].update(state='reset_stopping',reset_stop_next=0)", src)

    def test_harness_uses_the_same_rules_as_the_app(self):
        src = (ROOT/'studio_panel.py').read_text(encoding='utf-8')
        self.assertIn("NO_RESET=re.compile('Nick trên Chrome khác|Không có bộ sản phẩm số|chưa chọn bộ|Không tìm thấy bộ|Chưa có đúng tab|mất kết nối|giữ giỏ tự thêm tay|Nick Chrome đã thay đổi',re.I)", src)
        self.assertIn('RESET_EVERY=3 ', src); self.assertIn('RESET_HOLD=5\n', src)


class VisionReset(unittest.TestCase):
    def setUp(self):
        self.p = patch.object(V, 'report', lambda *a, **k: ''); self.p.start()
    def tearDown(self):
        self.p.stop()

    def test_one_call_starts_waits_and_ends_under_10_seconds(self):
        fake = E.EndPage('idle'); s = E.session(fake)
        t = [0.0]; s.clock = lambda: t[0]; s.sleep = lambda d: t.__setitem__(0, t[0] + d)
        marks = {}
        start, stop = s.start_live, s.stop_live
        s.start_live = lambda dock=True: (marks.setdefault('dock', dock), start(dock=dock), marks.setdefault('on', t[0]))[1]
        s.stop_live = lambda: (marks.setdefault('off', t[0]), stop())[1]
        r = s.reset_live(5)
        self.assertEqual((r['live'], r['reset']), (False, True)); self.assertEqual(fake.screen, 'idle')
        self.assertFalse(marks['dock'])                                   # no 8 s chat docking before the stop
        self.assertLess(marks['off'] - marks['on'], 10)

    def test_refuses_when_studio_is_already_live(self):
        s = E.session(E.EndPage('live'))
        with self.assertRaises(V.NotTouched): s.reset_live(5)


if __name__ == '__main__':
    unittest.main()


class LookAndGuide(unittest.TestCase):
    def test_region_dialog_shows_the_owner_chao_picture(self):
        src = (ROOT/'studio_vision_panel.py').read_text(encoding='utf-8')
        for name in ('mau_khoanh_chao.png', 'mau_khoanh_khung_chat.png'):
            self.assertIn(name, src); self.assertTrue((ROOT/'assets'/name).is_file())
        for key in ('input', 'send', 'chat', 'clock', 'greeting'):
            self.assertIn("'" + key + "': (", src)               # every region has a hint
        self.assertIn('Bỏ nút Chào đã khoanh, dùng nút Chào mẫu có sẵn', src)

    def test_app_is_orange(self):
        import theme
        self.assertIn('QWidget#header { background:qlineargradient', theme.STYLE)
        self.assertIn('QPushButton#primary { background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #fb923c, stop:1 #f97316)', theme.STYLE)
        self.assertNotIn('#208fe1', theme.STYLE)
        self.assertIn("header_box.setObjectName('header')", (ROOT/'app.py').read_text(encoding='utf-8'))
