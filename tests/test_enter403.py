import sys, types, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import studio_vision as V
from PIL import Image


def line(text, y=0):
    return dict(text=text, score=.95, x=0, y=y, w=10, h=10)


EMPTY = 'Thêm bình luận...'


def fixture(after_reads, chat_after=(), enter_works_on=None):
    """after_reads: input-box reads AFTER the draft is accepted (4 reads before that)."""
    regions = dict(clock=[0, 0, 80, 20], input=[0, 100, 100, 20], send=[110, 100, 30, 20], chat=[0, 150, 200, 100])
    p = dict(id='p', pid='1', name='Nick', accountName='Khánh Car Auto',
             vision=dict(enabled=True, width=400, height=300, dpi=96, regions=regions))
    log = []
    native = types.SimpleNamespace(touched=False, snapshot=lambda: (Image.new('RGB', (400, 300), 'white'), 96),
                                   click=lambda x, y: log.append(('click', x, y)), press_enter=lambda: log.append('enter'),
                                   type_text=lambda t: log.append('type'), clear_text=lambda: log.append('clear'))
    reads = [EMPTY, EMPTY, 'Hello anh em', 'Hello anh em'] + list(after_reads)
    def reader(im):
        if im.size == (100, 20):
            return [line(reads.pop(0) if reads else 'Hello anh em')]
        if im.size == (200, 100):
            return list(chat_after) if 'enter' in log else []
        return []
    s = V.VisionSession(p, native=native, reader=reader, sleep=lambda s: None)
    s.live = lambda **kw: True
    return s, log


class Enter(unittest.TestCase):
    def setUp(self):
        self.debug = patch.object(V, 'save_send_debug', return_value='')
        self.debug.start()

    def tearDown(self):
        self.debug.stop()

    def test_enter_confirmed_in_chat(self):
        s, log = fixture([EMPTY], [line('Khánh Car Auto', 10), line('Hello anh em', 25)])
        self.assertEqual(s.send('Hello anh em')['method'], 'offline-ocr')
        self.assertEqual(log.count('enter'), 1)

    def test_box_emptied_counts_as_sent_without_chat_match(self):
        s, log = fixture([EMPTY, EMPTY])
        self.assertEqual(s.send('Hello anh em'), dict(sent=True, confirmed=True, method='draft-cleared'))
        self.assertEqual(log.count('enter'), 1)

    def test_second_enter_when_first_ignored(self):
        s, log = fixture(['Hello anh em']*4 + [EMPTY, EMPTY])
        s.send('Hello anh em')
        self.assertEqual(log.count('enter'), 2)
        self.assertEqual(len([e for e in log if isinstance(e, tuple)]), 2)   # input box twice, no Send click

    def test_send_region_click_when_enter_ignored_twice(self):
        s, log = fixture(['Hello anh em']*8 + [EMPTY, EMPTY])
        s.send('Hello anh em')
        self.assertEqual(log.count('enter'), 2)
        self.assertEqual([e for e in log if isinstance(e, tuple)][-1], ('click', 125.0, 110.0))

    def test_never_more_than_two_enters_and_one_send_click(self):
        s, log = fixture(['Hello anh em']*40)
        with self.assertRaises(ValueError) as caught:
            s.send('Hello anh em')
        self.assertIn('vẫn còn câu vừa gõ', str(caught.exception))
        self.assertEqual(log.count('enter'), 2)
        self.assertEqual(sum(1 for e in log if isinstance(e, tuple) and e[1] == 125.0), 1)
        self.assertTrue(caught.exception.submitted)

    def test_changed_box_after_enter_stops_further_keys(self):
        s, log = fixture(['Hello chị em']*4)
        with self.assertRaises(ValueError):
            s.send('Hello anh em')
        self.assertEqual(log.count('enter'), 1)


if __name__ == '__main__':
    unittest.main()
