import os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import nbl_reports as R
import studio_vision as V
import studio_vision_logic as L
from PIL import Image

DATA = Path(__file__).resolve().parent / 'data'


class Reports(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'LOCALAPPDATA': self.tmp.name}); self.env.start()
        R._last.clear()

    def tearDown(self):
        self.env.stop(); self.tmp.cleanup()

    def test_two_kinds_in_two_folders_with_date_time(self):
        R.add('hoat_dong', 'Khánh Car Auto', 'Đã gửi tin', 'Hello anh em')
        R.add('loi', 'Khánh Car Auto', 'Gửi tin nhắn chưa được', 'Ô nhập chưa đọc rõ', Image.new('RGB', (50, 50)))
        a = list((R.root()/'hoat_dong').glob('*.txt')); e = list((R.root()/'loi').glob('*.txt'))
        self.assertEqual((len(a), len(e)), (1, 1))
        self.assertRegex(a[0].name, r'^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_\d{3}\.txt$')
        text = e[0].read_text(encoding='utf-8')
        self.assertIn('Loại: Lỗi', text); self.assertIn('Ngày giờ: ', text); self.assertIn('Ảnh: ', text)
        self.assertTrue(e[0].with_suffix('.png').exists())

    def test_only_newest_100_per_kind_and_kinds_never_touch_each_other(self):
        for i in range(3):
            R.add('loi', 'n', 'lỗi %d' % i)
        for i in range(130):
            R.add('hoat_dong', 'n', 'việc %d' % i)
        acts = sorted((R.root()/'hoat_dong').glob('*.txt'))
        self.assertEqual(len(acts), 100)
        self.assertIn('việc 129', acts[-1].read_text(encoding='utf-8'))
        self.assertIn('việc 30', acts[0].read_text(encoding='utf-8'))
        self.assertEqual(len(list((R.root()/'loi').glob('*.txt'))), 3)

    def test_same_error_repeating_updates_one_report(self):
        for _ in range(5):
            R.add('loi', 'n', 'Dò khách mới chưa được', 'Ô nhập chưa đọc rõ')
        files = list((R.root()/'loi').glob('*.txt'))
        self.assertEqual(len(files), 1)
        self.assertIn('Lặp lại: 5 lần', files[0].read_text(encoding='utf-8'))

    def test_failed_vision_action_writes_error_report_with_picture(self):
        session = type('S', (), {'last_frame': Image.new('RGB', (80, 60))})()
        V._report_error(session, {'name': 'Nick'}, 'send', ValueError('Bản nháp đã đổi'))
        V._report_error(None, {'name': 'Nick'}, 'status', ValueError('probe'))
        files = list((R.root()/'loi').glob('*.txt'))
        self.assertEqual(len(files), 1)
        self.assertIn('Bản nháp đã đổi', files[0].read_text(encoding='utf-8'))


class Dock(unittest.TestCase):
    def test_dock_icon_found_on_real_floating_chat(self):
        # Screenshot from the owner's PC: lock, settings, GHÉP, close at the top right.
        x, y = V.dock_icon(Image.open(DATA/'cua_so_tro_chuyen_noi.png'))
        self.assertAlmostEqual(x, 1150-864, delta=4); self.assertAlmostEqual(y, 57-32, delta=4)

    def test_dock_icon_with_invisible_border_and_150_percent(self):
        im = Image.open(DATA/'cua_so_tro_chuyen_noi.png')
        framed = Image.new('RGB', (im.width+16, im.height+8), (20, 20, 20)); framed.paste(im, (8, 0))
        x, y = V.dock_icon(framed); self.assertAlmostEqual(x, 1150-864+8, delta=4)
        big = im.resize((int(im.width*1.5), int(im.height*1.5)))
        x, y = V.dock_icon(big, 1.5); self.assertAlmostEqual(x, (1150-864)*1.5, delta=6)


class Caret(unittest.TestCase):
    def test_faint_hint_twice_counts_as_empty_once_does_not(self):
        faint = [dict(text='|Thêm bình luận...', score=.6, x=0, y=0, w=1, h=1)]
        self.assertTrue(L.faint_placeholder(faint))
        self.assertEqual(L.draft_state(faint), 'unknown')
        self.assertFalse(L.faint_placeholder([dict(text='Thêm bình luận đi', score=.6, x=0, y=0, w=1, h=1)]))

    def test_send_after_previous_send_with_blinking_caret(self):
        reads = [('|Thêm bình luận...', .6), ('Thêm bình luận...', .65)]
        s = V.VisionSession.__new__(V.VisionSession)
        s.cfg = {'regions': {'input': [0, 0, 100, 20]}}; s.sleep = lambda t: None; s.key = 'caret'
        s.native = type('N', (), {'press_escape': lambda self: None})()
        s.frame = lambda: Image.new('RGB', (200, 50))
        s.read = lambda im: [dict(text=t, score=sc, x=0, y=0, w=1, h=1) for t, sc in [reads.pop(0)]]
        self.assertEqual(s.empty_input_frame()[0], 'empty')


if __name__ == '__main__':
    unittest.main()
