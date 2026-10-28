"""4.1.15 (owner log 27/10/2026 02:00): the LIVE ended (Studio showed "Đã kết thúc! 11 người
xem đã tham gia…") but every "Kết thúc LIVE" failed with "Ảnh tên nick đã thay đổi (lệch 26.6,
tương quan 0.82)" → false "LIVE CÓ THỂ VẪN ĐANG CHẠY. Tắt tay ngay!". Cause: the end page
covers the nick avatar, so verify_account threw before the summary could be detected/closed.
NBL must read and close the end page WITHOUT the avatar check (the window is already verified)."""
import sys, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import studio_vision as V
import test_studio_live41 as T
import test_summary413 as E


def around(fake):
    # verify_account on a live/idle frame passes; on the end page it would raise, but the
    # end page must be handled before any verify_account call.
    fake.verified = []
    def verify(image):
        fake.verified.append(fake.screen)
        if fake.screen in ('summary', 'summary2', 'summary3', 'flash'):
            raise V.StudioAttention('Ảnh tên nick đã thay đổi (lệch 26.6, tương quan 0.82)')
        return True
    fake.verify_account = verify
    return fake


class EndPageCoversAvatar(unittest.TestCase):
    def setUp(self):
        self.p = patch.object(V, 'report', lambda *a, **k: ''); self.p.start()
    def tearDown(self):
        self.p.stop()

    def test_stop_on_the_end_page_succeeds_instead_of_failing_on_the_avatar(self):
        fake = around(T.FakeStudio('summary')); r = T.session(fake).stop_live()
        self.assertEqual(r['live'], False); self.assertEqual(fake.screen, 'idle')     # closed, not "tắt tay ngay"
        self.assertEqual(fake.verified, [])                                           # avatar never checked on the end page

    def test_new_end_page_layout_that_hides_the_avatar(self):
        fake = around(E.EndPage('summary2')); r = E.session(fake).stop_live()
        self.assertEqual((r['live'], fake.screen), (False, 'idle'))

    def test_stop_from_live_still_verifies_the_nick_before_clicking_end(self):
        fake = around(T.FakeStudio('live')); r = T.session(fake).stop_live()
        self.assertEqual(r['live'], False); self.assertIn('live', fake.verified)       # checked while still live

    def test_a_wrong_nick_live_window_is_still_refused(self):
        fake = T.FakeStudio('live')
        fake.verify_account = lambda image: (_ for _ in ()).throw(V.StudioAttention('Ảnh tên nick đã thay đổi'))
        with self.assertRaises(V.StudioAttention): T.session(fake).stop_live()
        self.assertNotIn(('click', *(0, 0)), [])  # sanity; the clock was never clicked
        self.assertFalse(any(e[0] == 'click' for e in fake.log))

    def test_end_page_appearing_after_end_now_is_closed_not_called_a_failure(self):
        fake = around(E.EndPage('live', flash=2)); r = E.session(fake).stop_live()
        self.assertEqual((r['live'], fake.screen), (False, 'idle'))

    def test_status_probe_sees_the_live_as_ended_when_the_avatar_is_covered(self):
        fake = around(T.FakeStudio('summary'))
        self.assertEqual(T.session(fake).live(fresh=True), False)                      # not an "Ảnh tên nick" error

    def test_cleanup_summary_closes_the_late_page_without_the_avatar_check(self):
        fake = around(T.FakeStudio('summary')); r = T.session(fake).cleanup_summary(20)
        self.assertEqual(r, dict(closed=True, seen=True)); self.assertEqual(fake.verified, [])


if __name__ == '__main__':
    unittest.main()
