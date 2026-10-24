"""4.1.2 (log 19/10/2026 02:31): a nick without image regions fell back to the 4.0.2
button path and every start failed with "LIVE state unknown". Now NBL refuses with
what to do, never clicks, and still starts once the regions are saved."""
import sys, tempfile, time, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from panel_harness import make, job, panel_class
import ast

BASE = Path(__file__).resolve().parents[1]


def vision_missing():
    tree = ast.parse((BASE / 'studio_panel.py').read_text(encoding='utf-8'))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'vision_missing')
    ns = {}
    exec(compile(ast.Module(body=[node], type_ignores=[]), 'studio_panel.py', 'exec'), ns)
    return ns['vision_missing']


class VisionRequired(unittest.TestCase):
    def setUp(self):
        self.clip = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False); self.clip.close()

    def tearDown(self):
        Path(self.clip.name).unlink(missing_ok=True)

    def profile(self, vision):
        return [dict(id='p1', name='giakhanhdoxe', session='s1', vision=vision, exePath='x', windowTitle='TikTok LIVE Studio',
                     accountAnchor='a', liveIndicator='old', startButton='old', stopButton='old', interaction={})]

    def due(self, vision):
        now = time.time()
        j = job(start=now - 5, end=now + 3000, clips=[self.clip.name], cart=dict(state='ready', attempts=0, next=0, verified=True))
        p = make([j], profiles=self.profile(vision))
        p.cart_ready = lambda j: True
        p.tick()
        return p, j

    def test_nick_without_regions_is_refused_and_nothing_is_sent_to_studio(self):
        p, j = self.due({})
        self.assertEqual(p.submitted, [])
        self.assertEqual(j['state'], 'start_retry')
        self.assertIn('chưa khoanh vùng Studio', j['error'])
        self.assertIn('Đồng hồ LIVE', j['error'])
        self.assertTrue(any('chưa khoanh vùng Studio' in a for a in p.alerts))

    def test_regions_without_clock_are_refused(self):
        p, j = self.due(dict(enabled=True, regions=dict(chat=[1, 1, 50, 50])))
        self.assertEqual(p.submitted, []); self.assertIn('Đồng hồ LIVE', j['error'])

    def test_once_regions_are_saved_the_start_goes_ahead(self):
        p, j = self.due(dict(enabled=True, regions=dict(clock=[1, 1, 50, 20], chat=[1, 1, 50, 50])))
        self.assertEqual(p.submitted, [('j1', 'preflight')])

    def test_old_picked_buttons_are_no_longer_enough(self):
        f = vision_missing()
        self.assertTrue(f(dict(name='A', liveIndicator='x', startButton='y', stopButton='z')))
        self.assertEqual(f(dict(name='A', vision=dict(enabled=True, regions=dict(clock=[0, 0, 9, 9])))), '')

    def test_saving_a_schedule_checks_the_regions(self):
        src = (BASE / 'studio_panel.py').read_text(encoding='utf-8')
        body = src[src.index(' def create_job(self):'):src.index(' def selected_job(self):')]
        self.assertIn('vision_missing(self.effective_profile(p))', body)
        self.assertLess(body.index('vision_missing'), body.index('add_job('))


if __name__ == '__main__':
    unittest.main()
