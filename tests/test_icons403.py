import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import studio_vision as V
import studio_vision_logic as L


def line(t):
    return dict(text=t, score=.95, x=0, y=0, w=1, h=1)


def session(input_rect, send_rect):
    s = V.VisionSession.__new__(V.VisionSession)
    s.cfg = {'regions': {'input': input_rect, 'send': send_rect}}
    return s


class Icons(unittest.TestCase):
    def test_send_arrow_noise_is_ignored(self):
        for read in ('Hello anh em VAAAIAAA', 'Hello anh em VAAA IAA'):
            self.assertEqual(L.draft_state([line(read)], 'Hello anh em'), 'expected')

    def test_real_words_are_never_ignored(self):
        self.assertEqual(L.draft_state([line('Hello anh em OK')], 'Hello anh em'), 'occupied')
        self.assertEqual(L.draft_state([line('Hello chi em VAAA')], 'Hello anh em'), 'occupied')
        self.assertEqual(L.draft_state([line('VAAAIAAA')], 'Hello anh em'), 'occupied')

    def test_region_covering_icons_stops_before_them(self):
        # Studio row in the user's screenshot: text from 1612, emoji ~1843, Send ~1860
        s = session([1605, 686, 285, 24], [1858, 688, 22, 20])
        x, y, w, h = s.input_rect()
        self.assertEqual((x, y, h), (1605, 686, 24))
        self.assertLessEqual(x+w, 1858-22)

    def test_text_only_region_is_unchanged(self):
        s = session([1605, 686, 220, 24], [1858, 688, 22, 20])
        self.assertEqual(s.input_rect(), [1605, 686, 220, 24])
        s = session([100, 100, 200, 24], [500, 400, 22, 20])
        self.assertEqual(s.input_rect(), [100, 100, 200, 24])


if __name__ == '__main__':
    unittest.main()
