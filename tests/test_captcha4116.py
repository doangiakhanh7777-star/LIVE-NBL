"""4.1.16 (owner 27/10/2026): "khi xuất hiện captcha là thông báo liên tục 5 lần cho tao"."""
import sys, threading, time, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import notifications as N
from panel_harness import make

ROOT = Path(__file__).resolve().parents[1]


def notifier(clock):
    sent = []; done = threading.Event()
    def sender(config, text):
        sent.append(text)
        if len(sent) >= 5: done.set()
        return True
    n = N.Notifier(sender=sender, clock=lambda: clock[0], sleep=lambda s: None)
    n.configure(dict(enabled=True, chat_id='1', token='x'))
    return n, sent, done


def settle(sent, count, wait=2.0):
    end = time.time() + wait
    while len(sent) < count and time.time() < end: time.sleep(.01)
    time.sleep(.05)


class Burst(unittest.TestCase):
    def test_captcha_is_sent_5_times_in_a_row(self):
        clock = [0.0]; n, sent, _ = notifier(clock)
        self.assertTrue(n.publish('studio:p1:status', 'giakhanhdoxe · Studio đang có cảnh báo: Hoàn thành xác minh bảo mật'))
        settle(sent, 5)
        self.assertEqual(len(sent), 5)
        self.assertEqual([t[-5:] for t in sent], ['(1/5)', '(2/5)', '(3/5)', '(4/5)', '(5/5)'])
        self.assertTrue(all(t.startswith('🚨 ') for t in sent)); n.close()

    def test_a_captcha_that_stays_does_not_flood_the_chat(self):
        clock = [0.0]; n, sent, _ = notifier(clock)
        n.publish('k', 'CAPTCHA'); settle(sent, 5)
        clock[0] = 120; self.assertFalse(n.publish('k', 'CAPTCHA'))          # 2 minutes later: no new burst
        clock[0] = 301; self.assertTrue(n.publish('k', 'CAPTCHA'))           # still there after 5 minutes: again
        settle(sent, 10); self.assertEqual(len(sent), 10); n.close()

    def test_without_accents_and_english_too(self):
        for text in ('xac minh bao mat', 'Security verification', 'Please complete the captcha', 'Kéo thanh trượt để xác minh', 'Cần xác minh'):
            self.assertTrue(N.is_captcha(text), text)

    def test_ordinary_alerts_are_unchanged(self):
        for text in ('Đã phát LIVE', 'Kết thúc LIVE chưa được, lần 1/5', 'Giỏ hàng sẵn sàng', 'LIVE vi phạm tiêu chuẩn cộng đồng'):
            self.assertFalse(N.is_captcha(text), text)
        clock = [0.0]; n, sent, _ = notifier(clock)
        n.publish('a', 'Đã phát LIVE'); settle(sent, 1); self.assertEqual(sent, ['Đã phát LIVE'])
        self.assertFalse(n.publish('a', 'Đã phát LIVE')); n.close()           # the 60 s rule still applies


class ChromeCaptcha(unittest.TestCase):
    def test_captcha_on_the_chrome_live_page_raises_the_alarm(self):
        p = make([]); p.owner.bridge.snapshot = lambda: {'client': dict(captcha='Kéo thanh trượt để hoàn thành ghép hình')}
        p.poll_captcha(time.time())
        self.assertEqual(len(p.alarms), 1); key, text = p.alarms[0]
        self.assertEqual(key, 'captcha:chrome:p1'); self.assertIn('CAPTCHA', text); self.assertIn('Kéo thanh trượt', text)

    def test_no_captcha_no_alarm(self):
        p = make([]); p.owner.bridge.snapshot = lambda: {'client': dict(captcha='')}
        p.poll_captcha(time.time()); self.assertEqual(p.alarms, [])

    def test_the_page_reports_it_every_tick_and_the_bridge_keeps_it(self):
        src = (ROOT/'CHROME_NBL_LIVE'/'content.js').read_text(encoding='utf-8')
        self.assertIn('captcha:captchaText()', src); self.assertIn('[class*=captcha i]', src)
        bridge = (ROOT/'chrome_bridge.py').read_text(encoding='utf-8')
        self.assertIn("state['captcha']=", bridge); self.assertIn("'findResult','captcha')}", bridge)


if __name__ == '__main__':
    unittest.main()
