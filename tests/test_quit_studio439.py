"""4.3.9 (chủ máy, 31/10/2026): kết thúc LIVE xong phải TẮT HẲN ứng dụng TikTok LIVE Studio.

Lý do: hôm 30/10 đang LIVE thì hiện captcha, chủ máy bấm TẮT KHẨN CẤP trên điện thoại —
NBL chỉ hủy lịch, Studio vẫn chạy. Captcha che màn hình nên bấm dấu X cũng không được.
Bản này gửi lệnh đóng từ bên trong (Browser.close), không được thì tắt tiến trình.
"""
import sys, time, unittest
from concurrent.futures import Future
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent)); sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from panel_harness import make, job
import studio_cdp


def finish(p, j, action, result):
    f = Future(); f.set_result(result); p.futures[f] = (j['id'], None, action); p.tick()


class TatStudio(unittest.TestCase):
    def test_het_lich_live_thi_tat_han_studio(self):
        now = time.time(); p = make([])
        j = job(id='r', state='stopping', start=now - 60, end=now - 1)
        p.jobs = [j]
        finish(p, j, 'stop', dict(live=False, confirmed=True, method='cdp'))
        self.assertEqual(j['state'], 'finished')
        self.assertIn(('r', 'quit_studio'), p.submitted)

    def test_studio_da_tat_roi_thi_khong_gui_them(self):
        now = time.time(); p = make([])
        j = job(id='r', state='stopping', start=now - 60, end=now - 1)
        p.jobs = [j]
        finish(p, j, 'stop', dict(live=False, confirmed=True, studioClosed=True, method='cdp'))
        self.assertNotIn(('r', 'quit_studio'), p.submitted)

    def test_captcha_chan_thi_bao_da_tat_han_studio(self):
        now = time.time(); p = make([])
        j = job(id='r', state='stopping', start=now - 60, end=now - 1)
        p.jobs = [j]
        finish(p, j, 'emergency_stop', dict(live=False, confirmed=True, quit=True, studioClosed=True,
                                            quitMethod='cdp', why='chua thay dong Ket thuc LIVE'))
        self.assertEqual(j['state'], 'finished')
        self.assertTrue(any('TẮT HẲN' in str(a) for a in p.logs), p.logs)

    def test_tat_studio_that_bai_thi_khong_lam_hong_lich(self):
        now = time.time(); p = make([])
        j = job(id='r', state='finished', start=now - 60, end=now - 1)
        p.jobs = [j]
        f = Future(); f.set_exception(RuntimeError('khong tat duoc'))
        p.futures[f] = (j['id'], None, 'quit_studio'); p.tick()
        self.assertEqual(j['state'], 'finished')      # lịch vẫn là đã xong, không chuyển sang lỗi

    def test_quit_studio_nam_trong_danh_sach_lenh_tu_dong(self):
        self.assertIn('quit_studio', studio_cdp.CDP_ACTIONS)
        self.assertIn('emergency_stop', studio_cdp.CDP_ACTIONS)

    def test_doc_dung_pid_giu_cong_dieu_khien(self):
        """netstat liệt kê nhiều cổng: phải lấy đúng PID của cổng Studio, không lấy nhầm."""
        out = ('  TCP    0.0.0.0:135            0.0.0.0:0              LISTENING       1120\n'
               '  TCP    127.0.0.1:9339         0.0.0.0:0              LISTENING       7788\n'
               '  TCP    127.0.0.1:9340         0.0.0.0:0              LISTENING       9911\n'
               '  TCP    127.0.0.1:9339         127.0.0.1:55012        ESTABLISHED     7788\n')
        class R:
            stdout = out; returncode = 0
        old_name, old_run = studio_cdp.os.name, studio_cdp.subprocess.run
        studio_cdp.os.name = 'nt'; studio_cdp.subprocess.run = lambda *a, **k: R()
        try:
            self.assertEqual(studio_cdp.port_pid(9339), 7788)
            self.assertEqual(studio_cdp.port_pid(9340), 9911)
            self.assertEqual(studio_cdp.port_pid(9999), 0)
        finally:
            studio_cdp.os.name = old_name; studio_cdp.subprocess.run = old_run


if __name__ == '__main__':
    unittest.main()
