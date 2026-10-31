"""4.3.10 (chủ máy, 31/10/2026): NBL trên máy khách không kết nối được LIVE Studio.

Chẩn đoán từ chính máy chủ máy: find_exe() trả về rỗng vì Studio ở đó cài thành
"C:\\Program Files\\TikTok LIVE Studio\\1.38.0\\TikTok LIVE Studio.exe" — có thêm tầng thư
mục phiên bản. Tệ hơn: auto_connect() thấy rỗng là BỎ VỀ, không thèm thử kết nối, dù
Studio đang mở sẵn và cổng 9339 đang trả lời. NBL thừa sức đọc mà không chịu đọc.
"""
import sys, time, unittest
from concurrent.futures import Future
from pathlib import Path
import tempfile, shutil
sys.path.insert(0, str(Path(__file__).resolve().parent)); sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from panel_harness import make
import studio_cdp as S

EXE = S.STUDIO_EXE


class TimFileStudio(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()); self.old_env = dict(S.os.environ)
        for k in ('ProgramFiles', 'ProgramW6432', 'ProgramFiles(x86)', 'LOCALAPPDATA'):
            S.os.environ.pop(k, None)
        S.os.environ['ProgramFiles'] = str(self.tmp)
        self.old_run = S.running_exe_path; S.running_exe_path = lambda: ''

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        S.os.environ.clear(); S.os.environ.update(self.old_env); S.running_exe_path = self.old_run

    def make(self, *parts):
        f = self.tmp.joinpath(*parts); f.parent.mkdir(parents=True, exist_ok=True); f.write_text('x')
        return str(f)

    def test_cai_kieu_cu_ngay_trong_thu_muc(self):
        want = self.make('TikTok LIVE Studio', EXE)
        self.assertEqual(S.find_exe(), want)

    def test_cai_co_tang_thu_muc_phien_ban(self):
        """Đúng cảnh máy khách: ...\\TikTok LIVE Studio\\1.38.0\\TikTok LIVE Studio.exe"""
        want = self.make('TikTok LIVE Studio', '1.38.0', EXE)
        self.assertEqual(S.find_exe(), want)

    def test_nhieu_phien_ban_thi_lay_ban_moi_nhat(self):
        self.make('TikTok LIVE Studio', '1.9.0', EXE)
        self.make('TikTok LIVE Studio', '1.38.0', EXE)
        new = self.make('TikTok LIVE Studio', '1.40.2', EXE)
        self.assertEqual(S.find_exe(), new)          # không được so chuỗi (1.9 > 1.38)

    def test_hoi_windows_duoc_thi_uu_tien_duong_dan_do(self):
        self.make('TikTok LIVE Studio', EXE)
        that = self.make('O_khac', 'Studio la', EXE)
        S.running_exe_path = lambda: that
        self.assertEqual(S.find_exe(), that)

    def test_duong_dan_da_luu_con_dung_thi_khong_hoi_lai(self):
        saved = self.make('TikTok LIVE Studio', '1.38.0', EXE)
        S.running_exe_path = lambda: self.fail('không được hỏi Windows khi đường dẫn cũ còn dùng được')
        self.assertEqual(S.find_exe(saved), saved)

    def test_khong_co_gi_thi_tra_rong_chu_khong_vang_loi(self):
        self.assertEqual(S.find_exe(), '')
        self.assertEqual(S.find_exe('C:/khong/co/that.exe'), '')


class VanNoiKhiKhongThayFile(unittest.TestCase):
    """Lỗi chính hôm nay."""
    def setUp(self):
        self.p = make([])
        self.p.owner.data = dict(sessions=[dict(id='s1', number=1, account='bechaudethuong12')])
        self.p.current_session_id = 's1'
        self.sent = []
        import types
        self.p.pool = types.SimpleNamespace(
            submit_priority=lambda pr, fn, prof, act, *a, **k: (self.sent.append((prof, act)), Future())[1])
        self.p.connection_checks = {}
        self.p.current_profile = lambda: None
        self.p.auto_note = ''
        self.p.auto_at = 0; self.p.auto_launched = False
        self.old_name = S.os.name; S.os.name = 'nt'      # auto_connect chỉ chạy trên Windows

    def tearDown(self):
        S.os.name = self.old_name

    def test_khong_thay_file_studio_van_gui_lenh_ket_noi(self):
        old = S.find_exe
        S.find_exe = lambda hint='', ask_windows=True: ''
        try:
            self.p.auto_connect_real(time.time())
        finally:
            S.find_exe = old
        self.assertEqual(len(self.sent), 1, 'phải gửi lệnh kết nối dù không thấy file Studio')
        prof, act = self.sent[0]
        self.assertEqual(act, 'connect')
        self.assertEqual(prof['cdpPort'], 9339)
        self.assertTrue(prof['noLaunch'], 'không có file thì không được tự mở Studio')

    def test_co_file_studio_thi_duoc_tu_mo_lan_dau(self):
        old = S.find_exe
        S.find_exe = lambda hint='', ask_windows=True: r'C:\x\TikTok LIVE Studio.exe'
        try:
            self.p.auto_connect_real(time.time())
        finally:
            S.find_exe = old
        prof, act = self.sent[0]
        self.assertFalse(prof['noLaunch'])


class KhongNuotCauLoi(unittest.TestCase):
    def test_loi_lap_lai_van_nhac_lai_sau_5_phut(self):
        p = make([])
        p.owner.data = dict(sessions=[dict(id='s1', number=1)])
        p.auto_note = ''          # StudioPanel.__init__ đặt sẵn; khung test không chạy __init__
        def fail_once():
            f = Future(); f.set_exception(RuntimeError('Studio chưa mở')); return f
        p.auto_connected(fail_once(), ('s1', 'x', 9339))
        self.assertEqual(len(p.logs), 1, p.logs)
        p.auto_connected(fail_once(), ('s1', 'x', 9339))
        self.assertEqual(len(p.logs), 1, 'lỗi y hệt ngay sau đó thì không spam')
        p.auto_note_at -= 301
        p.auto_connected(fail_once(), ('s1', 'x', 9339))
        self.assertEqual(len(p.logs), 2, 'quá 5 phút phải nhắc lại, không được im luôn')


if __name__ == '__main__':
    unittest.main()


class KhongLamKhungGiaoDien(unittest.TestCase):
    """find_exe gọi PowerShell — chậm. Không được để nó chạy trên luồng giao diện."""
    def test_auto_connect_khong_hoi_windows(self):
        p = make([])
        p.owner.data = dict(sessions=[dict(id='s1', number=1)])
        p.current_session_id = 's1'; p.connection_checks = {}; p.current_profile = lambda: None
        p.auto_note = ''; p.auto_at = 0; p.auto_launched = False
        import types
        p.pool = types.SimpleNamespace(submit_priority=lambda *a, **k: Future())
        old_name, S.os.name = S.os.name, 'nt'
        asked = []
        old_ask, S.running_exe_path = S.running_exe_path, lambda *a, **k: asked.append(1) or ''
        try:
            p.auto_connect_real(time.time())
        finally:
            S.os.name = old_name; S.running_exe_path = old_ask
        self.assertEqual(asked, [], 'auto_connect chạy trên luồng giao diện: cấm gọi PowerShell')

    def test_nho_ket_qua_hoi_windows_khong_chay_lai_lien_tuc(self):
        """Giả os.name='nt' trên Linux thì pathlib chuyển sang kiểu Windows và kiểm tra
        file nào cũng ra False, nên ở đây thay luôn Path bằng khuôn giả."""
        import types as T
        calls = []
        old = (S.os.name, S.subprocess.run, S.Path)
        S.os.name = 'nt'
        S.Path = lambda x: T.SimpleNamespace(is_file=lambda: True)
        S.subprocess.run = lambda *a, **k: (calls.append(1), T.SimpleNamespace(stdout=r'C:\x\TikTok LIVE Studio.exe', returncode=0))[1]
        S._EXE_CACHE.update(at=0.0, path='')
        try:
            a1 = S.running_exe_path(); a2 = S.running_exe_path(); a3 = S.running_exe_path()
        finally:
            S.os.name, S.subprocess.run, S.Path = old; S._EXE_CACHE.update(at=0.0, path='')
        self.assertEqual(a1, r'C:\x\TikTok LIVE Studio.exe')
        self.assertEqual([a2, a3], [a1, a1])
        self.assertEqual(len(calls), 1, 'hỏi Windows 1 lần rồi nhớ lại, không chạy PowerShell mỗi lần')

    def test_hoi_hong_thi_cung_khong_chay_lai_ngay(self):
        import types as T
        calls = []
        old = (S.os.name, S.subprocess.run)
        S.os.name = 'nt'
        S.subprocess.run = lambda *a, **k: (calls.append(1), T.SimpleNamespace(stdout='', returncode=1))[1]
        S._EXE_CACHE.update(at=0.0, path='')
        try:
            self.assertEqual(S.running_exe_path(), '')
            self.assertEqual(S.running_exe_path(), '')
        finally:
            S.os.name, S.subprocess.run = old; S._EXE_CACHE.update(at=0.0, path='')
        self.assertEqual(len(calls), 1, 'hỏi hỏng thì chờ 1 phút mới hỏi lại, không dồn dập')
