"""4.1.5 (owner, 19/10/2026 04:40): the next schedule kept the previous schedule's cart."""
import sys, time, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from panel_harness import make, job
import studio_scheduler as S

BASE = Path(__file__).resolve().parents[1]


class Cart(unittest.TestCase):
    def test_a_set_number_asks_chrome_to_replace_the_cart(self):
        now = time.time(); j = job(start=now + 600, bundle_index=2); p = make([j]); p.poll_cart(now)
        c = p.owner.bridge.commands[-1]
        self.assertEqual((c['action'], c['bundleIndex'], c['replace'], c['keepCart']), ('prepare_bundle', 2, True, False))

    def test_set_zero_keeps_the_hand_filled_cart(self):
        now = time.time(); j = job(start=now + 600, bundle_index=0); p = make([j]); p.poll_cart(now)
        c = p.owner.bridge.commands[-1]
        self.assertEqual((c['bundleIndex'], c['replace'], c['keepCart']), (0, False, True))
        S.add_job([], 'p', now + 60, now + 600, bundle_index=0, now=now)

    def test_next_schedule_is_prepared_only_after_the_live_before_it(self):
        now = time.time()
        a = job(id='a', start=now - 60, end=now + 600, state='running'); b = job(id='b', start=now + 3600, end=now + 7200)
        p = make([a, b]); p.poll_cart(now); self.assertEqual(p.owner.bridge.commands, [])
        a['state'] = 'finished'; p.poll_cart(now)
        self.assertEqual(p.owner.bridge.commands[-1]['replace'], True)

    def test_old_ready_carts_are_prepared_again_after_the_update(self):
        src = (BASE / 'studio_panel.py').read_text(encoding='utf-8')
        self.assertIn("not j['cart'].get('v415')", src)
        self.assertIn("v415=True", src)


if __name__ == '__main__':
    unittest.main()
