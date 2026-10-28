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
        self.assertIn('#f37021', theme.STYLE)          # 4.2.0: Hermès orange
        self.assertNotIn('#208fe1', theme.STYLE)
        self.assertIn("header_box.setObjectName('header')", (ROOT/'app.py').read_text(encoding='utf-8'))
