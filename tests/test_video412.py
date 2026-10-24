"""4.1.2 (owner, 19/10/2026 02:40): the owner opens NBL VIDEO and attaches it to Studio
beforehand. At the LIVE time NBL only replays THAT video from the start. NBL never
replaces its playlist, never opens a second window and never stops it (a stopped
NBL VIDEO is a black picture in Studio)."""
import json, sys, tempfile, time, types, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from panel_harness import make, job, CLIP
import studio_scheduler as S
import video_commands as V

BASE = Path(__file__).resolve().parents[1]
VISION = dict(enabled=True, regions=dict(clock=[1, 1, 50, 20], chat=[1, 1, 50, 50]))


def nick(playlist):
    profiles = [dict(id='p1', name='giakhanhdoxe', session='s1', vision=VISION, exePath='x', windowTitle='TikTok LIVE Studio',
                     accountAnchor='a', interaction={})]
    return profiles, {'s1': dict(id='s1', device='', mute=False, shuffle=False, playlist=playlist)}


class Replay(unittest.TestCase):
    def test_start_replays_the_nicks_own_playlist_without_replacing_it(self):
        profiles, sessions = nick([CLIP])
        j = job(state='preparing', clips=['/old/schedule_clip.mp4'], shuffle=True)
        p = make([j], profiles, sessions); p.start_video(j)
        self.assertEqual(p.played, [('play', 's1')])
        self.assertEqual(sessions['s1']['playlist'], [CLIP]); self.assertFalse(sessions['s1']['shuffle'])
        self.assertTrue(sessions['s1']['loop'])

    def test_nick_without_video_is_refused_before_studio(self):
        profiles, sessions = nick([])
        now = time.time(); j = job(start=now - 5, end=now + 3000, cart=dict(state='ready', attempts=0, next=0, verified=True))
        p = make([j], profiles, sessions); p.cart_ready = lambda j: True; p.tick()
        self.assertEqual(p.submitted, []); self.assertIn('chưa có video', j['error'])

    def test_lost_video_file_is_refused(self):
        profiles, sessions = nick(['/khong/con/video.mp4'])
        now = time.time(); j = job(start=now - 5, end=now + 3000)
        p = make([j], profiles, sessions); p.cart_ready = lambda j: True; p.tick()
        self.assertEqual(p.submitted, []); self.assertIn('không còn trong máy', j['error'])

    def ready(self, status):
        profiles, sessions = nick([CLIP])
        folder = Path(tempfile.mkdtemp()); (folder / 'runtime' / 's1').mkdir(parents=True)
        (folder / 'runtime' / 's1' / 'status.json').write_text(json.dumps(status), encoding='utf-8')
        j = job(state='preparing', prepare_phase='video', video_sent=time.time() - 2, video_until=time.time() + 15)
        p = make([j], profiles, sessions); p.owner.path = types.SimpleNamespace(parent=folder); p.tick()
        return p

    def test_press_phat_live_only_after_the_video_restarted(self):
        now = time.time()
        old = self.ready(dict(state='PlayingState', time=now - 5, path=CLIP, position=1000))
        self.assertEqual(old.submitted, [])
        middle = self.ready(dict(state='PlayingState', time=now, path=CLIP, position=420000))
        self.assertEqual(middle.submitted, [])
        fresh = self.ready(dict(state='PlayingState', time=now, path=CLIP, position=800))
        self.assertEqual(fresh.submitted, [('j1', 'start')])


class NeverStop(unittest.TestCase):
    def test_no_path_sends_stop_to_nbl_video(self):
        for state, result, action in (('stopping', dict(live=False), 'stop'), ('running', dict(live=False), 'status')):
            j = job(state=state); p = make([j])
            from concurrent.futures import Future
            f = Future(); f.set_result(result); p.futures = {f: ('j1', None, action)}
            p.tick(); self.assertNotIn(('stop', 's1'), p.played)
        j = job(state='start_retry', start_attempts=3); p = make([j]); p.stop_owned_video(j, force=True)
        self.assertEqual(p.played, [])

    def test_schedule_needs_no_clips(self):
        now = time.time()
        j = S.add_job([], 'p1', now + 60, now + 600, bundle_index=1, now=now)
        self.assertEqual(j['clips'], [])
        src = (BASE / 'studio_panel.py').read_text(encoding='utf-8')
        body = src[src.index(' def create_job(self):'):src.index(' def selected_job(self):')]
        self.assertIn('clips=[]', body); self.assertIn('video_problem(self.session(p))', body)


class OneWindow(unittest.TestCase):
    def folder(self, age):
        f = Path(tempfile.mkdtemp())
        (f / 'status.json').write_text(json.dumps(dict(time=time.time() - age, state='PlayingState')), encoding='utf-8')
        return f

    def test_open_window_from_before_a_restart_gets_the_command(self):
        launched = []
        f = self.folder(1)
        result = V.dispatch_video_command(f, 'play', dict(playlist=[CLIP]), None, lambda x: launched.append(x) or 'new')
        self.assertIsNone(result); self.assertEqual(launched, [])
        self.assertEqual([json.loads(x.read_text(encoding='utf-8'))['action'] for x in (f / 'commands').glob('*.json')], ['play'])

    def test_no_window_opens_one(self):
        launched = []
        f = self.folder(60)
        result = V.dispatch_video_command(f, 'play', dict(playlist=[CLIP]), None, lambda x: launched.append(x) or 'new')
        self.assertEqual((result, len(launched)), ('new', 1))

    def test_stop_to_a_closed_window_does_nothing(self):
        f = self.folder(60)
        self.assertIsNone(V.dispatch_video_command(f, 'stop', {}, None, lambda x: 'new'))
        self.assertFalse((f / 'commands').exists())


if __name__ == '__main__':
    unittest.main()
