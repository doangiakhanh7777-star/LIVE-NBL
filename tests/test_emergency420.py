"""4.2.0 (owner, 28/10/2026): tắt LIVE khẩn cấp — one nick or every nick."""
import sys, time, unittest
from concurrent.futures import Future
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent)); sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from panel_harness import make, job

P2 = dict(id='p2', name='Nick Hai', session='s1', vision=dict(enabled=True, regions=dict(clock=[1, 1, 50, 20])), exePath='x', windowTitle='TikTok LIVE Studio', accountAnchor='a', interaction={})


def two():
    p = make([])
    p.profiles.append(P2)
    return p


def done(p, j, result):
    f = Future(); f.set_result(result); p.futures[f] = (j['id'], None, 'stop'); p.tick()


class Emergency(unittest.TestCase):
    def test_all_ends_running_cancels_pending_and_ends_hand_live(self):
        now = time.time(); p = two()
        run = job(id='r', state='running', start=now - 60, end=now + 3600)
        later = job(id='l', profile='p1', start=now + 7200, end=now + 9000)
        p.jobs = [run, later]
        p.emergency(None)
        self.assertEqual(later['state'], 'cancelled')
        self.assertIn(('r', 'stop'), p.submitted)
        hand = [j for j in p.jobs if j['profile'] == 'p2']
        self.assertEqual(len(hand), 1); self.assertIn((hand[0]['id'], 'stop'), p.submitted)
        self.assertTrue(any('TẮT KHẨN CẤP' in a for a in p.alerts))
        self.assertNotIn('play', [x[0] for x in p.played])          # NBL VIDEO untouched

    def test_one_nick_only(self):
        now = time.time(); p = two()
        a = job(id='a', state='running', start=now - 60, end=now + 3600)
        b = job(id='b', profile='p2', state='running', start=now - 60, end=now + 3600)
        p.jobs = [a, b]
        p.emergency('p2')
        self.assertIn(('b', 'stop'), p.submitted); self.assertNotIn(('a', 'stop'), p.submitted)
        self.assertEqual(a['state'], 'running')

    def test_result_is_sent_with_reminder_to_schedule_again(self):
        now = time.time(); p = two()
        run = job(id='r', state='running', start=now - 60, end=now + 3600)
        later = job(id='l', start=now + 7200, end=now + 9000)
        p.jobs = [run, later]; p.profiles.pop()
        p.emergency(None)
        done(p, run, dict(live=False))
        text = p.alerts[-1]
        self.assertIn('Đã tắt', text); self.assertIn('Đã hủy 1 lịch', text); self.assertIn('NHỚ LÊN LỊCH LẠI', text)

    def test_not_ended_is_said_loudly(self):
        now = time.time(); p = two(); p.profiles.pop()
        run = job(id='r', state='running', start=now - 60, end=now + 3600); p.jobs = [run]
        p.emergency(None)
        run['state'] = 'attention'; p.poll_emergency(time.time())
        self.assertIn('CHƯA TẮT ĐƯỢC', p.alerts[-1])


if __name__ == '__main__':
    unittest.main()
