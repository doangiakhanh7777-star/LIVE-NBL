"""4.1.3 (owner photo 19/10/2026 03:33): Studio's end page said "Đã kết thúc! 2 người
xem đã tham gia phiên LIVE của bạn…" (no "Bạn đang làm rất tốt") and stayed open, so
the next schedule could not press Phát LIVE. Also Studio may show "Phát LIVE" for a
moment before the end page appears."""
import sys, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import studio_vision as V
import test_studio_live41 as T
from PIL import Image, ImageDraw

T.SCREENS['summary2'] = [T.L('Trung tâm LIVE', 1010, 48, 110), T.L('Thời lượng: 00: 12: 13', 300, 84, 200),
                         T.L('Đã kết thúc! 2 người xem đã tham gia phiên LIVE của bạn thông', 300, 105, 700),
                         T.L('qua các điểm nhấn. Hãy cứ thoải mái đăng thêm!', 300, 140, 600),
                         T.L('Tổng số lượt xem', 70, 222, 120), T.L('Lượt thích', 220, 222, 80)]
T.SCREENS['summary3'] = [T.L('Trung tâm LIVE', 1010, 48, 110), T.L('Đã kết thúc! 2 người xem đã tham gia phiên LIVE của bạn thông', 300, 105, 700),
                         T.L('Tổng số lượt xem', 70, 222, 120)]


class EndPage(T.FakeStudio):
    """Kết thúc ngay → "Phát LIVE" for `flash` frames → end page (layout `page`)."""
    def __init__(self, screen, page='summary2', flash=0):
        super().__init__(screen); self.page = page; self.flash = flash; self.frames = 0
    def snapshot(self, account=True):
        if account and self.screen in ('summary2', 'summary3'):
            raise V.StudioAttention('Ảnh tên nick đã thay đổi (lệch 26.6, tương quan 0.82)')
        if self.screen == 'flash':
            self.frames += 1
            if self.frames > self.flash: self.screen = self.page
        im = Image.new('RGB', (T.W, T.H), (20, 20, 20))
        if self.screen in ('summary2', 'summary3'):
            d = ImageDraw.Draw(im); d.line((1150, 52, 1162, 64), fill='white', width=2); d.line((1162, 52, 1150, 64), fill='white', width=2)
        return im, 96
    def click(self, x, y):
        if self.screen in ('summary2', 'summary3'):
            self.touched = True; self.log.append(('click', round(x), round(y)))
            if x > 1135 and 40 < y < 76: self.screen = 'idle'
            return
        before = self.screen
        super().click(x, y)
        if before == 'dialog' and self.screen == 'summary':
            self.screen = 'flash' if self.flash else self.page
    def press_escape(self):
        self.log.append('esc')
        if self.screen in ('menu', 'dialog'): self.screen = 'live'


def session(fake):
    s = T.session(fake)
    inner = s.lines_in
    def lines_in(frame, rect):
        screen = 'idle' if fake.screen == 'flash' else fake.screen
        x, y, w, h = s.box(frame, rect)
        return [l for l in T.SCREENS[screen] if x <= l['x'] < x+w and y <= l['y'] < y+h]
    s.lines_in = lines_in
    return s


class EndPageTests(unittest.TestCase):
    def setUp(self):
        self.p = patch.object(V, 'report', lambda *a, **k: ''); self.p.start()

    def tearDown(self):
        self.p.stop()

    def test_new_end_page_layout_is_recognised(self):
        for page in ('summary2', 'summary3'):
            s = session(EndPage(page))
            self.assertEqual(s.screen_state(s.frame(account=False)), 'summary', page)

    def test_new_end_page_is_closed_with_its_x_not_the_window_x(self):
        fake = EndPage('summary2'); session(fake).close_summary()
        self.assertEqual(fake.screen, 'idle')
        x, y = fake.log[-1][1:]
        self.assertGreater(y, 40)        # never the title bar (Studio's own close button)
        self.assertGreater(x, 1135)

    def test_stop_closes_an_end_page_that_appears_after_phat_live(self):
        fake = EndPage('live', flash=2); r = session(fake).stop_live()
        self.assertEqual(r['live'], False); self.assertEqual(fake.screen, 'idle')
        self.assertNotIn(('click', 700 + 55, 610 + 10), fake.log)   # never "Tạm dừng LIVE"

    def test_next_schedule_closes_the_old_end_page_then_starts(self):
        fake = EndPage('summary2'); r = session(fake).start_live()
        self.assertEqual(r['live'], True); self.assertEqual(fake.screen, 'live')

    def test_ordinary_screens_are_not_end_pages(self):
        for screen in ('idle', 'live', 'menu', 'dialog'):
            self.assertNotEqual(session(EndPage(screen)).screen_state(), 'summary', screen)


if __name__ == '__main__':
    unittest.main()
