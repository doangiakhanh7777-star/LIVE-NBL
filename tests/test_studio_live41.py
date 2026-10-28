"""Start / stop the LIVE on a simulated Studio laid out like the owner's photos (19/10/2026)."""
import sys, types, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import studio_vision as V
from PIL import Image

W, H = 1200, 730
CLOCK = [760, 655, 110, 30]


def L(text, x, y, w=100, h=20):
    return dict(text=text, score=.95, x=x, y=y, w=w, h=h)


SCREENS = {
    'idle': [L('Phát LIVE', 770, 660, 90), L('Trò chuyện LIVE', 900, 320, 120)],
    'live': [L('00:00:19', 775, 660, 80)],
    'menu': [L('00:00:19', 775, 660, 80), L('Kết thúc LIVE', 700, 560, 110), L('Tạm dừng LIVE', 700, 610, 110)],
    'dialog': [L('00:00:30', 775, 660, 80), L('Kết thúc phát trực tiếp?', 450, 300, 220), L('Kết thúc phiên LIVE? Hãy chia sẻ', 450, 330, 300),
               L('Kết thúc ngay', 450, 380, 120), L('Hủy', 640, 380, 60)],
    'summary': [L('Trung tâm LIVE', 1020, 70, 110), L('Thời lượng: 00: 00: 27', 300, 100, 200), L('Bạn đang làm rất tốt! Hãy tiếp tục phát huy nhé!', 300, 130, 500)],
    'paused': [L('00:00:19', 775, 660, 80)],
}
CLICKS = {('idle', 'Phát LIVE'): 'live', ('live', '00:00:19'): 'menu', ('menu', 'Kết thúc LIVE'): 'dialog',
          ('menu', 'Tạm dừng LIVE'): 'paused', ('dialog', 'Kết thúc ngay'): 'summary', ('dialog', 'Hủy'): 'live'}


class FakeStudio:
    def __init__(self, screen, menu_lines=None, summary_x=True):
        self.screen = screen; self.log = []; self.touched = False; self.summary_x = summary_x
        if menu_lines is not None: SCREENS['menu_custom'] = menu_lines
    def snapshot(self, account=True):
        if account and self.screen == 'summary':
            raise V.StudioAttention('Ảnh tên nick đã thay đổi (lệch 26.6, tương quan 0.82)')
        im = Image.new('RGB', (W, H), (20, 20, 20))
        if self.screen == 'summary' and self.summary_x:
            from PIL import ImageDraw
            ImageDraw.Draw(im).line((1150, 72, 1162, 84), fill='white', width=2); ImageDraw.Draw(im).line((1162, 72, 1150, 84), fill='white', width=2)
        return im, 96
    def click(self, x, y):
        self.touched = True; self.log.append(('click', round(x), round(y)))
        if self.screen == 'summary' and x > 1135 and 60 < y < 100:
            self.screen = 'idle'; return
        for line in SCREENS[self.screen]:
            if line['x'] <= x <= line['x']+line['w'] and line['y'] <= y <= line['y']+line['h']:
                self.screen = CLICKS.get((self.screen, line['text']), self.screen); return
        if self.screen == 'live' and CLOCK[0] <= x <= CLOCK[0]+CLOCK[2] and CLOCK[1] <= y <= CLOCK[1]+CLOCK[3]:
            self.screen = 'menu'
    def press_escape(self):
        self.log.append('esc')
        if self.screen in ('menu', 'dialog'): self.screen = 'live'
        elif self.screen == 'summary': self.screen = 'summary'
    def dock_chat_window(self):
        self.log.append('dock'); return ('Đã ghép cửa sổ Trò chuyện LIVE về Studio', None) if self.screen == 'live' else None
    def verify_account(self, image):
        return True


def session(fake):
    p = dict(id='p', pid='1', name='Khánh Car Auto', vision=dict(enabled=True, width=W, height=H, dpi=96, regions=dict(clock=CLOCK)))
    s = V.VisionSession(p, native=fake, reader=lambda im: [], sleep=lambda t: None)
    def lines_in(frame, rect):
        x, y, w, h = s.box(frame, rect)
        return [l for l in SCREENS[fake.screen] if x <= l['x'] < x+w and y <= l['y'] < y+h]
    s.lines_in = lines_in
    s.live = lambda **kw: fake.screen in ('live', 'menu', 'dialog')
    return s


class StudioLive(unittest.TestCase):
    def setUp(self):
        self.p = patch.object(V, 'report', lambda *a, **k: ''); self.p.start()

    def tearDown(self):
        self.p.stop()

    def test_start_clicks_phat_live_then_docks_chat(self):
        fake = FakeStudio('idle'); r = session(fake).start_live()
        self.assertEqual((r['live'], r['docked']), (True, True))
        self.assertEqual(fake.log[0], ('click', 815, 670)); self.assertIn('dock', fake.log)

    def test_start_on_a_live_studio_does_not_click(self):
        fake = FakeStudio('live'); r = session(fake).start_live()
        self.assertTrue(r['already']); self.assertEqual([e for e in fake.log if isinstance(e, tuple)], [])

    def test_start_without_button_touches_nothing(self):
        fake = FakeStudio('menu'); SCREENS['weird'] = []; fake.screen = 'weird'
        with self.assertRaises(V.NotTouched):
            session(fake).start_live()
        self.assertEqual(fake.log, [])

    def test_full_stop_sequence(self):
        fake = FakeStudio('live'); r = session(fake).stop_live()
        self.assertEqual(r, dict(live=False, confirmed=True)); self.assertEqual(fake.screen, 'idle')
        clicks = [e for e in fake.log if isinstance(e, tuple)]
        self.assertEqual(len(clicks), 4)       # clock, Kết thúc LIVE, Kết thúc ngay, X

    def test_never_clicks_tam_dung(self):
        fake = FakeStudio('live')
        SCREENS['menu'], saved = [L('00:00:19', 775, 660, 80), L('Tạm dừng LIVE', 700, 610, 110)], SCREENS['menu']
        try:
            with self.assertRaises(ValueError):
                session(fake).stop_live()
        finally:
            SCREENS['menu'] = saved
        self.assertNotEqual(fake.screen, 'paused'); self.assertIn('esc', fake.log)

    def test_dialog_without_ket_thuc_ngay_is_cancelled_with_esc(self):
        fake = FakeStudio('live')
        saved = SCREENS['dialog']; SCREENS['dialog'] = [L('Một hộp khác', 450, 300, 220), L('OK', 450, 380, 60)]
        try:
            with self.assertRaises(ValueError):
                session(fake).stop_live()
        finally:
            SCREENS['dialog'] = saved
        self.assertIn('esc', fake.log); self.assertEqual(fake.screen, 'live')

    def test_stop_when_already_idle_or_on_summary(self):
        self.assertTrue(session(FakeStudio('idle')).stop_live()['already'])
        fake = FakeStudio('summary'); session(fake).stop_live(); self.assertEqual(fake.screen, 'idle')

    def test_screen_state_reads_button_clock_and_summary(self):
        for screen, want in (('idle', 'idle'), ('live', 'live'), ('summary', 'summary')):
            fake = FakeStudio(screen); s = session(fake)
            self.assertEqual(s.screen_state(fake.snapshot(False)[0]), want)

    def test_health_reads_fps_and_upload(self):
        s = session(FakeStudio('live'))
        s.lines_in = lambda frame, rect: [L('CPU: 1.5%  Bộ nhớ: 2.7%  Tải lên: 0 kbps  Rớt khung hình: 0(0.0%)  FPS: 0/30', 300, 700, 800)]
        self.assertEqual(s.health(Image.new('RGB', (W, H))), dict(upload=0, fps=0))


class Placeholder(unittest.TestCase):
    def test_idle_chat_hint_counts_as_empty(self):
        self.assertEqual(V.draft_state([L('Thêm bình luận trong phiên LIVE', 0, 0)]), 'empty')


if __name__ == '__main__':
    unittest.main()
