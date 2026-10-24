"""4.1.4 (owner video 19/10/2026 04:09): Studio had been opened again (new window), so
every action failed with "Cửa sổ Studio đã đổi"; the job stayed in "Cần kiểm tra",
"Hủy / kết thúc" only retried the failing stop, and reconnecting / unlinking were
refused while that job existed. Nothing could be done."""
import sys, time, unittest
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from panel_harness import make, job
import studio_scheduler as S
import studio_vision as V
from studio_vision_logic import StudioAttention

EXE = r'C:\Program Files\TikTok LIVE Studio\TikTok LIVE Studio.exe'
OLD = dict(name='giakhanhdoxe', exePath=EXE, windowTitle='TikTok LIVE Studio', windowHandle='111', pid='10', accountAnchor='a',
           vision=dict(enabled=True, regions=dict(clock=[1, 1, 9, 9])))


def win(handle, pid, exe=EXE, title='TikTok LIVE Studio'):
    return dict(windowHandle=str(handle), pid=str(pid), exePath=exe, windowTitle=title)


class Rebind(unittest.TestCase):
    def test_one_free_studio_window_is_taken(self):
        new = S.rebind_window(OLD, [win(222, 20), win(5, 5, exe=r'C:\Chrome\chrome.exe', title='LIVE Studio - Chrome')])
        self.assertEqual((new['windowHandle'], new['pid']), ('222', '20'))
        self.assertEqual(new['accountAnchor'], 'a')          # the nick picture is still checked before any click

    def test_never_guesses_between_two_studios(self):
        self.assertIsNone(S.rebind_window(OLD, [win(222, 20), win(333, 30)]))

    def test_the_other_nicks_studio_is_not_taken(self):
        other = dict(OLD, _otherHandles=['333'])
        self.assertEqual(S.rebind_window(other, [win(222, 20), win(333, 30)])['windowHandle'], '222')

    def test_no_studio_open(self):
        self.assertIsNone(S.rebind_window(OLD, []))

    def test_execute_reattaches_and_reports_the_new_window(self):
        calls = []
        def fake(profile, action, deadline=0, payload=None):
            calls.append(profile['windowHandle'])
            if profile['windowHandle'] == '111':
                raise StudioAttention('Cửa sổ Studio đã đổi. Kết nối lại cửa sổ, giữ các vùng đã lưu.')
            return dict(live=False, confirmed=True)
        with patch.object(S.os, 'name', 'nt'), patch.object(V, 'execute_vision', fake), patch.object(S, 'list_windows', lambda: [win(222, 20)]):
            result = S.execute(dict(OLD), 'status')
        self.assertEqual(calls, ['111', '222'])
        self.assertEqual((result['rebound'], result['windowHandle'], result['pid']), (True, '222', '20'))

    def test_unclear_new_window_says_what_to_do(self):
        def fake(profile, action, deadline=0, payload=None):
            raise StudioAttention('Cửa sổ Studio đã đổi. Kết nối lại cửa sổ, giữ các vùng đã lưu.')
        with patch.object(S.os, 'name', 'nt'), patch.object(V, 'execute_vision', fake), patch.object(S, 'list_windows', lambda: [win(222, 20), win(333, 30)]):
            with self.assertRaises(StudioAttention) as caught:
                S.execute(dict(OLD), 'status')
        self.assertIn('Kết nối LIVE Studio', str(caught.exception))


class Panel(unittest.TestCase):
    def test_rebound_window_is_saved_on_the_nick(self):
        now = time.time(); j = job(state='attention', end=now - 60, end_stop_attempted=True)
        p = make([j]); f = Future(); f.set_result(dict(live=False, rebound=True, windowHandle='222', pid='20', windowTitle='TikTok LIVE Studio'))
        p.futures = {f: ('j1', None, 'status')}; p.tick()
        self.assertEqual((p.profiles[0]['windowHandle'], p.profiles[0]['pid']), ('222', '20'))
        self.assertEqual(j['state'], 'finished')

    def test_stuck_job_can_always_be_dropped_without_touching_studio(self):
        j = job(state='attention', error='LIVE CÓ THỂ VẪN ĐANG CHẠY'); p = make([j])
        pending = Future(); p.futures = {pending: ('j1', None, 'stop')}
        p.drop_job(j)
        self.assertEqual(j['state'], 'cancelled'); self.assertEqual(p.futures, {}); self.assertEqual(p.submitted, [])
        self.assertEqual(p.owner.bridge.commands[-1], dict(action='stop', module='all'))

    def test_cancel_offers_drop_and_reconnect_is_not_blocked_by_a_stuck_job(self):
        src = (Path(__file__).resolve().parents[1] / 'studio_panel.py').read_text(encoding='utf-8')
        cancel = src[src.index(' def cancel(self):'):src.index(' def drop_job(self,j):')]
        self.assertIn("'Chỉ hủy lịch'", cancel); self.assertIn('self.drop_job(j)', cancel)
        edit = src[src.index(' def edit_profile('):src.index("dialog=QDialog(self)", src.index(' def edit_profile('))]
        self.assertNotIn('self.active()', edit); self.assertNotIn("'attention'", edit)
        vision = (Path(__file__).resolve().parents[1] / 'studio_vision_panel.py').read_text(encoding='utf-8')
        self.assertIn('panel.studio.driving()', vision)

    def test_closing_nbl_leaves_nbl_video_playing(self):
        src = (Path(__file__).resolve().parents[1] / 'app.py').read_text(encoding='utf-8')
        close = src[src.index('    def closeEvent(self,event):'):]
        self.assertNotIn("self.command('close'", close)


if __name__ == '__main__':
    unittest.main()
