import sys, types, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import studio_vision as V
import studio_vision_logic as L
from PIL import Image, ImageDraw


def line(text, score=.95):
    return dict(text=text, score=score, x=0, y=0, w=10, h=10)


def box(caret=False, extra=None):
    im = Image.new('RGB', (100, 24), 'white')
    d = ImageDraw.Draw(im); d.rectangle((5, 6, 60, 18), fill='black')
    if caret: d.line((64, 3, 64, 21), fill='black')
    if extra: d.rectangle(extra, fill='black')
    return im


class Caret(unittest.TestCase):
    def test_caret_only_difference_is_same_draft(self):
        self.assertTrue(V.same_draft(box(), box(caret=True)))
        self.assertTrue(V.same_draft(box(), box()))

    def test_real_edits_are_not_same_draft(self):
        self.assertFalse(V.same_draft(box(), box(extra=(64, 15, 66, 18))))     # a dot
        self.assertFalse(V.same_draft(box(), box(extra=(64, 6, 72, 18))))      # a letter
        self.assertFalse(V.same_draft(box(), box(caret=True, extra=(80, 6, 88, 18))))

    def test_caret_before_placeholder_is_empty(self):
        self.assertEqual(L.draft_state([line('|Thêm bình luận...')]), 'empty')
        self.assertEqual(L.draft_state([line('IThêm bình luận')]), 'empty')
        self.assertEqual(L.draft_state([line('Xin chào Thêm bình luận')]), 'occupied')

    def send_fixture(self, reads):
        """reads: list of OCR texts returned for the input box, in order."""
        p = dict(id='p', pid='1', name='Nick', vision=dict(enabled=True, width=400, height=300, dpi=96,
                 regions=dict(clock=[0, 0, 80, 20], input=[0, 100, 100, 20], send=[110, 100, 30, 20], chat=[0, 150, 200, 100]), sendImage='s'))
        counts = dict(click=0, input=0, enter=0)
        native = types.SimpleNamespace(touched=False, snapshot=lambda: (Image.new('RGB', (400, 300), 'white'), 96),
                                       click=lambda *a: counts.__setitem__('click', counts['click']+1),
                                       press_enter=lambda: counts.__setitem__('enter', counts['enter']+1),
                                       type_text=lambda t: None, clear_text=lambda: None)
        queue = list(reads)
        def reader(im):
            if im.size == (100, 20):
                counts['input'] += 1
                return [line(queue.pop(0) if queue else 'Thêm bình luận...')]
            return []
        s = V.VisionSession(p, native=native, reader=reader, sleep=lambda s: None)
        s.live = lambda **kw: True
        return s, counts

    def test_blinking_caret_read_does_not_block_send_click(self):
        # empty, empty-after-focus, typed (caret visible), typed OK, ready (caret), ready OK
        s, counts = self.send_fixture(['Thêm bình luận...', 'Thêm bình luận...',
                                       'Hello anh eml', 'Hello anh em', 'Hello anh eml', 'Hello anh em'])
        result = s.send('Hello anh em')
        # Enter WAS pressed once after one click into the input; the box then emptied.
        self.assertEqual(result['sent'], True)
        self.assertEqual((counts['enter'], counts['click']), (1, 2))

    def test_changed_draft_still_blocks(self):
        s, counts = self.send_fixture(['Thêm bình luận...', 'Thêm bình luận...', 'Hello anh em'] + ['Hello chị em']*4)
        with self.assertRaises(Exception) as caught:
            s.send('Hello anh em')
        self.assertIn('Bản nháp đã đổi', str(caught.exception))
        self.assertIn('Hello chị em', str(caught.exception))
        self.assertEqual(counts['click'], 1)


if __name__ == '__main__':
    unittest.main()
