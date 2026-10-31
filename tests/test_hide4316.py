"""4.3.16: Ẩn hết khi LIVE — không bao giờ dùng chuột/bàn phím khi đang ẩn; camera ảo vừa khung; lệnh ẩn/hiện video."""
import sys, tempfile, unittest
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))


class NoMouseTest(unittest.TestCase):
    def setUp(self):
        import studio_scheduler
        from unittest import mock
        self.S = studio_scheduler; self.S.NO_MOUSE = True
        self.p = mock.patch.object(studio_scheduler.os, 'name', 'nt'); self.p.start()     # execute chỉ chạy trên Windows

    def tearDown(self):
        self.S.NO_MOUSE = False; self.p.stop()

    def test_old_mouse_path_refused_when_hidden(self):
        from studio_vision_logic import NotTouched
        prof = dict(id='a' * 32, name='SĂN DEAL GIÁ RẺ', pid=1, windowTitle='TikTok LIVE Studio', exePath='x.exe', accountAnchor=1,
                    liveIndicator=1, chatInput=1, chatSend=1, chatRegion=1)
        for action in ('send', 'start', 'stop', 'status'):
            with self.assertRaises(NotTouched) as e:
                self.S.execute(prof, action, 0, {'text': 'x'})
            self.assertIn('không dùng chuột', str(e.exception))

    def test_vision_path_refused_when_hidden(self):
        from studio_vision_logic import NotTouched
        prof = dict(id='b' * 32, vision={'enabled': True}, pid=1, windowTitle='TikTok LIVE Studio', exePath='x.exe')
        with self.assertRaises(NotTouched):
            self.S.execute(prof, 'send', 0, {'text': 'x'})


class CameraFitTest(unittest.TestCase):
    def test_fit_portrait(self):
        import vcam
        self.assertEqual(vcam.fit(720, 1440), (40, 0, 640, 1280))      # video 720x1440 của chủ máy: viền đen hai bên
        self.assertEqual(vcam.fit(720, 1280), (0, 0, 720, 1280))
        self.assertEqual(vcam.fit(1280, 720), (0, 437, 720, 405))
        self.assertEqual(vcam.WIDTH % 4, 0); self.assertEqual(vcam.HEIGHT % 4, 0)

    def test_missing_dll_is_quiet(self):
        import vcam
        c = vcam.VirtualCam(Path(tempfile.gettempdir()) / 'khong_co.dll')
        self.assertFalse(c.ok); self.assertIn('NBL Camera', c.error); self.assertFalse(c.send_bgr(b'\0' * 10)); c.close()


class WindowCommandTest(unittest.TestCase):
    def test_window_command_accepted_and_never_opens_a_window(self):
        from video_commands import dispatch_video_command
        opened = []
        with tempfile.TemporaryDirectory() as d:
            r = dispatch_video_command(Path(d) / 'x', 'window', {'show': False}, None, lambda f: opened.append(f))
        self.assertIsNone(r); self.assertEqual(opened, [])


class WinhideTest(unittest.TestCase):
    def test_noop_off_windows(self):
        import winhide
        if sys.platform != 'win32':
            self.assertEqual(winhide.windows(), []); self.assertEqual(winhide.minimize([1]), [])


class StudioFlagsTest(unittest.TestCase):
    def test_studio_launched_without_background_throttling(self):
        import studio_cdp
        for f in ('--disable-renderer-backgrounding', '--disable-background-timer-throttling', '--disable-backgrounding-occluded-windows'):
            self.assertIn(f, studio_cdp.NO_THROTTLE); self.assertIn(f, studio_cdp.SHORTCUT_PS)


if __name__ == '__main__':
    unittest.main()
