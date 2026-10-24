import sys, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import studio_vision as V
import studio_vision_logic as L
from PIL import Image


class FakeStudio:
    """A Studio comment box driven through the clipboard, like the real one."""
    def __init__(self, box='', enter_sends=True, copy_works=True, typing_noise=''):
        self.box, self.enter_sends, self.copy_works, self.noise = box, enter_sends, copy_works, typing_noise
        self.clipboard = 'việc riêng của chủ máy'; self.log = []; self.touched = False; self.chat = []
    def snapshot(self): return Image.new('RGB', (400, 300), (49, 49, 49)), 96
    def click(self, x, y): self.log.append(('click', round(x), round(y))); self.touched = True
    def clip_get(self): return self.clipboard
    def clip_set(self, text): self.clipboard = text
    def read_box(self):
        self.log.append('copy')
        return (self.box or None) if self.copy_works else None
    def paste_text(self, text): self.log.append('paste'); self.box += text + self.noise; self.touched = True
    def press_end(self): self.log.append('end')
    def press_escape(self): self.log.append('esc')
    def press_enter(self):
        self.log.append('enter')
        if self.enter_sends and self.box: self.chat.append(self.box); self.box = ''
    def clear_text(self): self.log.append('clear'); self.box = ''


def session(fake):
    regions = dict(clock=[0, 0, 80, 20], input=[0, 100, 100, 20], send=[110, 100, 30, 20], chat=[0, 150, 200, 100])
    p = dict(id='p', pid='1', name='Nick', vision=dict(enabled=True, width=400, height=300, dpi=96, regions=regions))
    s = V.VisionSession(p, native=fake, reader=lambda im: [], sleep=lambda t: None)
    s.live = lambda **kw: True
    return s


LONG = 'anh em click vào giỏ hàng tham khảo nha'


class Clipboard(unittest.TestCase):
    def setUp(self):
        self.debug = patch.object(V, 'save_send_debug', return_value=''); self.debug.start()

    def tearDown(self):
        self.debug.stop()

    def test_long_two_line_message_is_verified_exactly_and_sent(self):
        fake = FakeStudio()
        self.assertEqual(session(fake).send(LONG)['method'], 'clipboard-empty')
        self.assertEqual(fake.chat, [LONG])
        self.assertEqual(fake.log.count('enter'), 1)
        self.assertEqual(fake.clipboard, 'việc riêng của chủ máy')   # given back

    def test_someone_typing_is_never_touched(self):
        fake = FakeStudio(box='chủ shop đang gõ dở')
        with self.assertRaises(L.StudioAttention):
            session(fake).send(LONG)
        self.assertNotIn('paste', fake.log); self.assertNotIn('enter', fake.log)
        self.assertEqual(fake.box, 'chủ shop đang gõ dở')

    def test_wrong_text_in_box_is_not_sent_and_our_paste_is_not_erased(self):
        fake = FakeStudio(typing_noise='x')
        with self.assertRaises(Exception) as caught:
            session(fake).send(LONG)
        self.assertIn('khác câu mẫu', str(caught.exception))
        self.assertNotIn('enter', fake.log); self.assertEqual(fake.chat, [])

    def test_enter_ignored_then_second_enter_then_send_click(self):
        fake = FakeStudio(enter_sends=False)
        with self.assertRaises(ValueError) as caught:
            session(fake).send(LONG)
        self.assertEqual(fake.log.count('enter'), 2)
        self.assertEqual([e for e in fake.log if isinstance(e, tuple)][-1], ('click', 125, 110))
        self.assertIn('vẫn còn câu', str(caught.exception))
        self.assertEqual(fake.clipboard, 'việc riêng của chủ máy')

    def test_live_ended_after_paste_erases_only_our_line(self):
        fake = FakeStudio()
        s = session(fake); calls = []
        s.live = lambda **kw: calls.append(kw) or not kw.get('fresh')
        with self.assertRaises(L.NotSentCleaned):
            s.send(LONG)
        self.assertEqual(fake.box, ''); self.assertIn('clear', fake.log); self.assertNotIn('enter', fake.log)

    def test_no_copy_support_falls_back_to_screen_reading(self):
        fake = FakeStudio(copy_works=False)
        s = session(fake)
        with patch.object(V.VisionSession, 'draft_frame', return_value=None):
            with self.assertRaises(ValueError) as caught:
                s.send(LONG)
        self.assertIn('Chưa đọc đúng câu vừa dán', str(caught.exception))
        self.assertNotIn('enter', fake.log)


if __name__ == '__main__':
    unittest.main()
