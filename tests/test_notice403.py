import sys, types, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import studio_vision as V
import studio_vision_logic as L
from PIL import Image


def line(text, x, y, w=200, h=20, score=.95):
    return dict(text=text, score=score, x=x, y=y, w=w, h=h)


# The dialog from the user's screenshot (window coordinates)
NOTICE = [line('Phiên LIVE đã bị hạn chế hiển thị', 474, 252, 240),
          line('Buổi LIVE của bạn không đủ điều kiện để được đề', 474, 285, 320),
          line('xuất và đang bị hạn chế trong kết quả tìm kiếm vì', 474, 305, 320),
          line('OK', 760, 452, 20, 18)]


class Button(unittest.TestCase):
    def test_ok_of_restriction_notice_is_found(self):
        self.assertEqual(L.dismiss_button(NOTICE), (770.0, 461.0))

    def test_captcha_security_or_end_live_is_never_closed(self):
        for words in ('Hoàn thành captcha để tiếp tục', 'Xác minh bảo mật tài khoản của bạn', 'Kết thúc LIVE ngay bây giờ'):
            self.assertIsNone(L.dismiss_button(NOTICE[:2] + [line(words, 474, 330, 300)] + NOTICE[3:]))

    def test_violation_notice_is_closed_now(self):
        # 4.0.3: the owner asked for every popup to be closed so automation continues.
        lines = NOTICE[:2] + [line('Bạn đã vi phạm nguyên tắc cộng đồng', 474, 330, 300)] + NOTICE[3:]
        self.assertEqual(L.dismiss_button(lines), (770.0, 461.0))

    def test_any_popup_with_close_button(self):
        lines = [line('Chúc mừng ngày Phụ nữ Việt Nam 20.10', 400, 300, 300), line('Đã hiểu', 520, 380, 60, 20)]
        self.assertEqual(L.dismiss_button(lines), (550.0, 390.0))

    def test_lone_button_word_without_message_is_ignored(self):
        self.assertIsNone(L.dismiss_button([line('Đóng', 520, 380, 40, 20)]))

    def test_no_button_or_two_buttons(self):
        self.assertIsNone(L.dismiss_button(NOTICE[:3]))
        self.assertIsNone(L.dismiss_button(NOTICE + [line('OK', 600, 452, 20, 18)]))

    def test_far_away_text_does_not_block(self):
        self.assertIsNotNone(L.dismiss_button(NOTICE + [line('Kết thúc', 900, 670, 60)]))


class Close(unittest.TestCase):
    def session(self, reads_after, allow=True):
        log = []
        native = types.SimpleNamespace(touched=False, click=lambda x, y: log.append((x, y)),
                                       snapshot=lambda: (Image.new('RGB', (1200, 720)), 96))
        s = V.VisionSession.__new__(V.VisionSession)
        V._dismissed_at.clear()
        s.cfg = {'regions': {}}; s.key = 'n'; s.native = native; s.clock = lambda: 50.0
        s.p = {'name': 'Nick'}
        s.sleep = lambda t: None; s.allow_dismiss = allow
        reads = [NOTICE, reads_after]
        s.read = lambda im: reads.pop(0)
        return s, log

    def test_notice_closed_and_work_continues(self):
        s, log = self.session([])
        s.scan_alerts(Image.new('RGB', (1200, 720)), fresh=True)
        self.assertEqual(log, [(770.0, 461.0)])
        self.assertFalse(s.native.touched)
        self.assertEqual(len(s.dismissed), 1)

    def test_notice_still_there_stops(self):
        s, log = self.session(NOTICE)
        with self.assertRaises(L.StudioAttention):
            s.scan_alerts(Image.new('RGB', (1200, 720)), fresh=True)

    def test_read_only_status_never_clicks(self):
        s, log = self.session([], allow=False)
        with self.assertRaises(L.StudioAttention):
            s.scan_alerts(Image.new('RGB', (1200, 720)), fresh=True)
        self.assertEqual(log, [])

    def test_result_reports_dismissed(self):
        session = types.SimpleNamespace(native=types.SimpleNamespace(activate=lambda: None), dismissed=['x'],
                                        check=lambda: dict(readable=True))
        self.assertEqual(V._run(session, {'pid': '1'}, 'chat_check', None), dict(readable=True, dismissed=['x']))
        self.assertTrue(session.allow_dismiss)


class Front(unittest.TestCase):
    def native(self, fg, pid_of):
        n = V.NativeStudio.__new__(V.NativeStudio)
        n.handle = 100; n.studio_pid = 7
        class D:
            def __init__(self): self.value = 0
        n.W = types.SimpleNamespace(DWORD=D)
        def tpid(h, ref):
            ref._obj.value = pid_of.get(h, 1); return 1
        n.u = types.SimpleNamespace(GetForegroundWindow=lambda: fg, GetAncestor=lambda h, f: h,
                                    GetWindowThreadProcessId=tpid)
        return n

    def test_studio_dialog_counts_as_in_front(self):
        import ctypes
        orig = ctypes.byref
        ctypes.byref = lambda o: types.SimpleNamespace(_obj=o)
        try:
            self.assertTrue(self.native(100, {}).in_front())
            self.assertTrue(self.native(555, {555: 7}).in_front())
            self.assertFalse(self.native(999, {999: 3}).in_front())
        finally:
            ctypes.byref = orig


if __name__ == '__main__':
    unittest.main()
