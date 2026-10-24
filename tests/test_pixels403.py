import sys, types, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import studio_vision as V
from PIL import Image, ImageDraw

DATA = Path(__file__).resolve().parent / 'data'


def box(text=False, caret=False, hint=True, icons=True):
    """Studio's dark comment box as measured on the owner's screenshots."""
    im = Image.new('RGB', (280, 24), (49, 49, 49)); d = ImageDraw.Draw(im)
    if hint: d.rectangle((12, 8, 110, 16), fill=(111, 111, 111))       # dim "Thêm bình luận"
    if text: d.rectangle((12, 7, 90, 17), fill=(239, 239, 239))         # typed white text
    if caret: d.line((10, 4, 10, 20), fill=(235, 235, 235))
    if icons: d.ellipse((236, 4, 252, 20), outline=(235, 235, 235)); d.ellipse((258, 3, 276, 21), fill=(240, 240, 240))
    return im


class Pixels(unittest.TestCase):
    def test_owner_screens(self):
        empty = Image.open(DATA/'o_nhap_trong.png'); typed = Image.open(DATA/'o_nhap_co_chu.png')
        self.assertEqual(V.input_pixels(empty), 'empty')
        self.assertEqual(V.input_pixels(typed), 'occupied')

    def test_hint_caret_icons_are_empty_text_is_not(self):
        self.assertEqual(V.input_pixels(box()), 'empty')
        self.assertEqual(V.input_pixels(box(caret=True)), 'empty')
        self.assertEqual(V.input_pixels(box(text=True, hint=False)), 'occupied')
        self.assertEqual(V.input_pixels(box(text=True, caret=True, hint=False)), 'occupied')


def session(frames, reads):
    s = V.VisionSession.__new__(V.VisionSession)
    s.cfg = {'regions': {'input': [0, 0, 280, 24]}}; s.key = 'px'; s.sleep = lambda t: None
    log = []
    s.native = types.SimpleNamespace(press_escape=lambda: log.append('esc'))
    s.frame = lambda: frames.pop(0) if len(frames) > 1 else frames[0]
    s.read = lambda im: [dict(text=t, score=sc, x=0, y=0, w=1, h=1) for t, sc in reads.pop(0)] if reads else []
    return s, log


class Flow(unittest.TestCase):
    def test_after_send_caret_only_ocr_is_empty_by_pixels(self):
        s, log = session([box(caret=True)], [[('I', .5)]])
        self.assertEqual(s.empty_input_frame()[0], 'empty')
        self.assertEqual(log, [])

    def test_typed_text_never_empty_and_no_esc(self):
        s, log = session([box(text=True, hint=False)], [[('Hello anh em', .95)]]*8)
        self.assertEqual(s.empty_input_frame()[0], 'occupied')
        self.assertEqual(log, [])

    def test_unsure_then_esc_then_hint_readable(self):
        # pixels unsure (something bright, OCR unreadable) -> Esc once -> hint read normally
        busy = box(hint=False); ImageDraw.Draw(busy).rectangle((12, 7, 60, 17), fill=(200, 200, 200))
        s, log = session([busy]*4 + [box()], [[('', .3)]]*4 + [[('Thêm bình luận...', .95)]])
        self.assertEqual(s.empty_input_frame()[0], 'empty')
        self.assertEqual(log, ['esc'])

    def test_confident_words_beat_pixels(self):
        s, log = session([box()], [[('Xin chào shop', .95)]]*8)
        self.assertEqual(s.empty_input_frame()[0], 'occupied')


if __name__ == '__main__':
    unittest.main()
