import sys, time, types, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import studio_vision as V
import studio_vision_logic as L


class Budget(unittest.TestCase):
    def test_stale_queued_command_still_expires(self):
        with self.assertRaises(L.CommandExpired):
            V.working_deadline({}, 'send', 100.0, now=101.0)

    def test_started_send_gets_time_for_slow_ocr(self):
        self.assertEqual(V.working_deadline({}, 'send', 120.0, now=100.0), 100.0+V.VISION_BUDGET)

    def test_schedule_end_still_caps(self):
        self.assertEqual(V.working_deadline({'activeUntil': 130.0}, 'send', 120.0, now=100.0), 130.0)

    def test_other_actions_unchanged(self):
        self.assertEqual(V.working_deadline({}, 'status', 120.0, now=100.0), 120.0)
        self.assertEqual(V.working_deadline({}, 'send', 0, now=100.0), 0)


class AlertReuse(unittest.TestCase):
    def session(self, now, found=()):
        s = V.VisionSession.__new__(V.VisionSession)
        s.cfg = {'regions': {'chat': [300, 0, 100, 300]}}; s.key = 'k%f' % now[0]; s.clock = lambda: now[0]
        s.sizes = []
        def read(image):
            s.sizes.append(image.size); return [dict(text=t, score=.99, x=0, y=0, w=10, h=10) for t in found]
        s.read = read
        return s

    def frame(self):
        from PIL import Image
        return Image.new('RGB', (400, 300), 'white')

    def test_unchanged_window_is_not_read_twice(self):
        now = [1000.0]; s = self.session(now); img = self.frame()
        s.scan_alerts(img, fresh=True); now[0] += 12
        s.scan_alerts(img.copy(), fresh=True)
        self.assertEqual(s.sizes, [(400, 300)])

    def test_only_changed_area_is_read_and_warning_found(self):
        from PIL import ImageDraw
        now = [2000.0]; s = self.session(now); img = self.frame()
        s.scan_alerts(img, fresh=True); now[0] += 10
        popup = img.copy(); ImageDraw.Draw(popup).rectangle((40, 40, 120, 90), fill='red')
        s.read = (lambda old: (lambda image: (old(image), [dict(text='Vi phạm nguyên tắc', score=.99, x=0, y=0, w=1, h=1)])[1]))(s.read)
        with self.assertRaises(L.StudioAttention):
            s.scan_alerts(popup, fresh=True)
        w, h = s.sizes[-1]
        self.assertLess(w*h, 400*300/4)

    def test_chat_changes_are_ignored(self):
        from PIL import ImageDraw
        now = [3000.0]; s = self.session(now); img = self.frame()
        s.scan_alerts(img, fresh=True); now[0] += 5
        chat = img.copy(); ImageDraw.Draw(chat).rectangle((320, 50, 390, 250), fill='blue')
        s.scan_alerts(chat, fresh=True)
        self.assertEqual(len(s.sizes), 1)

    def test_old_scan_or_big_change_reads_everything(self):
        from PIL import Image
        now = [4000.0]; s = self.session(now); img = self.frame()
        s.scan_alerts(img, fresh=True); now[0] += 31
        s.scan_alerts(img, fresh=True)
        s.scan_alerts(Image.new('RGB', (400, 300), 'black'), fresh=True)
        self.assertEqual(s.sizes, [(400, 300)]*3)

    def test_new_command_scans_fresh(self):
        now = [5000.0]; img = self.frame()
        a = self.session(now); a.scan_alerts(img, fresh=True)
        b = self.session(now); b.scan_alerts(img, fresh=True)
        self.assertEqual(b.sizes, [(400, 300)])


if __name__ == '__main__':
    unittest.main()
