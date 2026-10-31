"""4.3.11 (chủ máy, 31/10/2026): NBL VIDEO trên máy thứ hai hình đứng rồi tự tắt.

Đo trên đúng máy đó (card Intel), cùng một clip, cùng tốc độ giải mã 29,9 hình/giây:
    cách cũ (nhờ card màn hình) : 0,5 lần vẽ/giây  — và nhiều khi giết luôn tiến trình
    cách mới (NBL tự vẽ bằng CPU): 29,6 lần vẽ/giây
Cửa sổ này là thứ Studio chụp lại để phát LIVE nên nó phải vẽ được trên mọi máy.
"""
import ast, sys, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SRC = (ROOT / 'player.py').read_text(encoding='utf-8')


def letterbox(fw, fh, aw, ah):
    """Bản sao của hàm trong player.py, nạp mà không cần Qt."""
    ns = {}
    tree = ast.parse(SRC)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'letterbox')
    exec(compile(ast.Module(body=[fn], type_ignores=[]), 'player.py', 'exec'), ns)
    return ns['letterbox'](fw, fh, aw, ah)


class GiuDungTiLe(unittest.TestCase):
    def ti_le(self, fw, fh, aw, ah):
        x, y, w, h = letterbox(fw, fh, aw, ah)
        return x, y, w, h, w / h

    def test_hinh_doc_trong_o_doc_vua_khit(self):
        x, y, w, h, r = self.ti_le(720, 1280, 405, 720)
        self.assertEqual((w, h), (405, 720)); self.assertEqual((x, y), (0, 0))

    def test_hinh_doc_trong_o_ngang_thi_vien_den_hai_ben(self):
        x, y, w, h, r = self.ti_le(720, 1280, 1920, 1080)
        self.assertEqual(h, 1080)                      # chạm trên dưới
        self.assertAlmostEqual(r, 720 / 1280, places=2)  # KHÔNG kéo méo
        self.assertGreater(x, 0); self.assertEqual(y, 0)
        self.assertEqual(x, (1920 - w) // 2)           # nằm giữa

    def test_hinh_ngang_trong_o_doc_thi_vien_den_tren_duoi(self):
        x, y, w, h, r = self.ti_le(1920, 1080, 405, 720)
        self.assertEqual(w, 405)
        self.assertAlmostEqual(r, 1920 / 1080, places=2)
        self.assertGreater(y, 0); self.assertEqual(x, 0)

    def test_khong_bao_gio_tran_ra_ngoai_o_ve(self):
        for fw, fh in ((720, 1280), (1920, 1080), (1, 999), (999, 1), (1080, 1080)):
            for aw, ah in ((405, 720), (1920, 1080), (100, 100), (7, 300)):
                x, y, w, h, _ = self.ti_le(fw, fh, aw, ah)
                self.assertGreaterEqual(x, 0); self.assertGreaterEqual(y, 0)
                self.assertLessEqual(x + w, aw, (fw, fh, aw, ah))
                self.assertLessEqual(y + h, ah, (fw, fh, aw, ah))

    def test_so_0_khong_lam_vang_loi(self):
        self.assertEqual(letterbox(0, 0, 405, 720), (0, 0, 405, 720))
        self.assertEqual(letterbox(720, 1280, 0, 0), (0, 0, 0, 0))


class TuVeBangCPU(unittest.TestCase):
    def test_khong_con_dung_khung_video_cua_qt(self):
        self.assertNotIn('QVideoWidget', SRC, 'QVideoWidget là cách cũ, vẽ 0,5 lần/giây trên máy chủ máy')
        self.assertNotIn('QtMultimediaWidgets', SRC)

    def test_dua_hinh_vao_khung_tu_ve(self):
        self.assertIn('class VideoCanvas', SRC)
        self.assertIn('QVideoSink', SRC)
        self.assertIn('setVideoOutput(self.video.sink)', SRC)
        self.assertIn('videoFrameChanged.connect', SRC)

    def test_ve_xong_phai_bao_ve_lai(self):
        """Nhận khung hình mà quên gọi update() thì màn hình đứng y như lỗi cũ."""
        tree = ast.parse(SRC)
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'VideoCanvas')
        fn = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'on_frame')
        goi = [n.func.attr for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
        self.assertIn('update', goi)


if __name__ == '__main__':
    unittest.main()
