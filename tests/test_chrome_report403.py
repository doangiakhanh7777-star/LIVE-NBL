import os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import nbl_reports as R
from chrome_bridge import ChromeBridge


class ChromeReports(unittest.TestCase):
    def test_tab_reports_land_in_the_two_report_folders(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {'LOCALAPPDATA': d}):
            R._last.clear()
            bridge = ChromeBridge(port=0)
            bridge.save_reports([
                {'kind': 'hoat_dong', 'title': 'Chrome · Tự đóng thông báo', 'detail': 'Phiên LIVE đã bị hạn chế hiển thị'},
                {'kind': 'loi', 'title': 'Chrome · Ghim sản phẩm đã dừng', 'detail': 'Nút ghim đang bị khóa'},
                {'kind': 'xoa_het', 'title': 'bad'}, 'rác', {'kind': 'loi', 'title': ''}], 'Khánh Car Auto')
            acts = list((R.root()/'hoat_dong').glob('*.txt')); errs = list((R.root()/'loi').glob('*.txt'))
            self.assertEqual((len(acts), len(errs)), (1, 1))
            self.assertIn('Nick: Khánh Car Auto', acts[0].read_text(encoding='utf-8'))
            self.assertIn('Nút ghim đang bị khóa', errs[0].read_text(encoding='utf-8'))
            self.assertTrue(any('đã tự đóng thông báo' in e for e in bridge.drain()))


if __name__ == '__main__':
    unittest.main()
