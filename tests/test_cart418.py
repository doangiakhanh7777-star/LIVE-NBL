"""4.1.8 (owner 25/10/2026): "kết thúc live nó không đóng cái tab cuối cùng, xong nó
không thêm được giỏ hàng nó vẫn không tự thử lại"."""
import sys, time, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from panel_harness import make, job


class Cart(unittest.TestCase):
    def test_lost_chrome_tab_while_waiting_does_not_freeze_the_cart(self):
        now = time.time(); j = job(start=now + 3600, cart=dict(state='preparing', attempts=0, next=0, command='cmd9', kind='add', until=now + 100))
        p = make([j])
        def gone(prof): raise ValueError('Chưa có đúng tab Chrome/nick kết nối.')
        p.client = gone
        p.poll_cart(now + 50); self.assertEqual(j['cart']['state'], 'preparing')        # still within its time
        p.poll_cart(now + 101)
        self.assertNotIn('command', j['cart']); self.assertEqual((j['cart']['state'], j['cart']['attempts']), ('failed', 1))

    def test_chrome_live_reloading_is_a_wait_not_a_failed_attempt(self):
        now = time.time(); j = job(start=now + 3600); p = make([j])
        Wait = p.poll_cart.__func__.__globals__['ChromeWait']
        def reloading(prof): raise Wait('Chrome LIVE chưa sẵn sàng')
        p.client = reloading; p.poll_cart(now)
        self.assertEqual(j['cart'].get('attempts', 0), 0); self.assertGreaterEqual(j['cart']['next'], now + 15)

    def test_cart_command_also_switches_off_pin_and_reply_of_the_live_before(self):
        now = time.time(); j = job(start=now + 3600); p = make([j]); p.poll_cart(now)
        self.assertTrue(p.owner.bridge.commands[-1]['stopModules'])

    def test_finished_live_switches_chrome_pin_reply_off(self):
        now = time.time(); j = job(start=now - 600, end=now - 5, state='stopping'); p = make([j])
        p.on_stopped(j)
        self.assertEqual([c['action'] for c in p.owner.bridge.commands[:2]], ['stop', 'finish_live'])


if __name__ == '__main__':
    unittest.main()
