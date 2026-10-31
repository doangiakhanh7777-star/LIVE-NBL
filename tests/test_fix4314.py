"""4.3.14: thông báo (chỉ captcha báo 5 lần), chọn micro / đổi định dạng âm thanh, dùng lại cửa sổ NBL VIDEO."""
import array
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import notifications
import ptt_core
import video_commands as V


class NotifyTest(unittest.TestCase):
    def make(self):
        sent = []
        n = notifications.Notifier(sender=lambda cfg, text: sent.append(text), sleep=lambda s: None)
        n.configure(dict(enabled=True)); return n, sent

    def wait(self, sent, count):
        end = time.time() + 3
        while len(sent) < count and time.time() < end:
            time.sleep(0.02)
        time.sleep(0.1)

    def test_non_captcha_alarm_is_sent_once(self):
        n, sent = self.make()
        msg = 'SĂN DEAL GIÁ RẺ · Cửa sổ Trò chuyện LIVE đang nổi, NBL chưa tự gộp được.'
        self.assertTrue(n.alarm('chatdock:x', msg)); self.wait(sent, 1)
        self.assertEqual(sent, [msg])
        self.assertFalse(n.alarm('chatdock:x', msg))          # lần sau trong 10 phút: không gửi
        n.closed = True

    def test_captcha_still_rings_five_times(self):
        n, sent = self.make()
        self.assertTrue(n.alarm('captcha:studio:x', 'CAPTCHA / XÁC MINH trong Studio')); self.wait(sent, 5)
        self.assertEqual(len(sent), 5); self.assertTrue(sent[-1].endswith('(5/5)'))
        n.closed = True

    def test_publish_custom_cooldown(self):
        clock = [1000.0]
        sent = []
        n = notifications.Notifier(sender=lambda c, t: sent.append(t), clock=lambda: clock[0], sleep=lambda s: None)
        n.configure(dict(enabled=True))
        self.assertTrue(n.publish('k', 'a', cooldown=6 * 3600))
        clock[0] += 3600; self.assertFalse(n.publish('k', 'a', cooldown=6 * 3600))
        clock[0] += 6 * 3600; self.assertTrue(n.publish('k', 'a', cooldown=6 * 3600))
        n.closed = True

    def test_chatdock_message_does_not_use_burst(self):
        src = (BASE / 'studio_panel.py').read_text(encoding='utf-8')
        self.assertNotIn("notifier.alarm('chatdock", src)


class MicChoiceTest(unittest.TestCase):
    def test_default_cable_is_replaced_by_real_mic(self):
        inputs = [('CABLE Output (VB-Audio Virtual Cable)', 'c'), ('Microphone (Realtek(R) Audio)', 'm')]
        got, why = ptt_core.choose_input(inputs, inputs[0])
        self.assertEqual(got, 'm'); self.assertIn('cáp ảo', why)

    def test_real_default_kept(self):
        inputs = [('CABLE Output (VB-Audio Virtual Cable)', 'c'), ('Headset Microphone', 'h')]
        self.assertEqual(ptt_core.choose_input(inputs, inputs[1]), ('h', ''))

    def test_only_cables_or_nothing(self):
        got, why = ptt_core.choose_input([('CABLE Output (VB-Audio Virtual Cable)', 'c')], ('CABLE Output (VB-Audio Virtual Cable)', 'c'))
        self.assertIsNone(got); self.assertIn('chưa có micro thật', why)
        self.assertEqual(ptt_core.choose_input([], None), (None, ''))

    def test_user_pick_wins_but_warns_for_cable(self):
        inputs = [('CABLE Output (VB-Audio Virtual Cable)', 'c'), ('Mic', 'm')]
        self.assertEqual(ptt_core.choose_input(inputs, inputs[1], 'm'), ('m', ''))
        got, why = ptt_core.choose_input(inputs, inputs[1], 'c'); self.assertEqual(got, 'c'); self.assertIn('thiết bị ảo', why)


class PipelineTest(unittest.TestCase):
    def sine(self, rate, n, start, ch=1, kind='i16', amp=0.5):
        vals = []
        for i in range(n):
            v = amp * math.sin(2 * math.pi * 440 * (start + i) / rate)
            vals += [v] * ch
        return ptt_core.encode(vals, kind)

    def run_case(self, ir, ic, ik, orr, oc, ok):
        p = ptt_core.Pipeline(ir, ic, ik, orr, oc, ok); frames = 0; out = []
        step = ir // 100
        for k in range(100):                                # 1 giây, khúc 10 ms
            o = ptt_core.decode(p.process(self.sine(ir, step, k * step, ic, ik)), ok)
            o = list(o); frames += len(o) // oc; out += o[0::oc]
        self.assertLessEqual(abs(frames - orr), 3, (ir, orr, frames))
        jump = max(abs(out[i + 1] - out[i]) for i in range(len(out) - 1))
        self.assertLess(jump, 2 * math.pi * 440 / orr * 0.5 * 1.3)   # liền mạch, không gãy giữa các khúc
        self.assertGreater(p.level, 0.4)

    def test_all_common_pairs(self):
        for case in [(44100, 1, 'i16', 48000, 2, 'f32'), (48000, 2, 'f32', 44100, 2, 'i16'), (48000, 1, 'i16', 48000, 2, 'i16'),
                     (16000, 1, 'i16', 48000, 2, 'f32'), (48000, 2, 'i32', 48000, 1, 'i16'), (44100, 2, 'u8', 48000, 2, 'f32')]:
            with self.subTest(case=case):
                self.run_case(*case)

    def test_pure_python_matches_numpy(self):
        if ptt_core._np is None:
            self.skipTest('máy này không có numpy')
        data = self.sine(44100, 441, 0, 2, 'f32')
        a = ptt_core.decode(ptt_core.Pipeline(44100, 2, 'f32', 48000, 2, 'i16').process(data), 'i16')
        keep = ptt_core._np
        try:
            ptt_core._np = None
            b = ptt_core.decode(ptt_core.Pipeline(44100, 2, 'f32', 48000, 2, 'i16').process(data), 'i16')
        finally:
            ptt_core._np = keep
        n = min(len(a), len(b)); self.assertLessEqual(abs(len(a) - len(b)), 2)
        self.assertLess(max(abs(float(a[i]) - float(b[i])) for i in range(n)), 0.001)

    def test_is_cable(self):
        for name in ('CABLE Output (VB-Audio Virtual Cable)', 'VoiceMeeter Output', 'Stereo Mix (Realtek)'):
            self.assertTrue(ptt_core.is_cable(name), name)
        self.assertFalse(ptt_core.is_cable('Microphone (USB Audio Device)'))


class ReuseWindowTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp()) / 'runtime'
        self.mine = self.root / 'nick_moi'; self.other = self.root / 'nick_cu'
        self.mine.mkdir(parents=True); self.other.mkdir(parents=True)
        self.proc = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])

    def tearDown(self):
        self.proc.kill(); self.proc.wait(); shutil.rmtree(self.root.parent, ignore_errors=True)

    def status(self, folder, age):
        (folder / 'status.json').write_text(json.dumps(dict(time=time.time() - age)), encoding='utf-8')

    def test_stale_status_but_live_process_is_reused(self):
        self.status(self.mine, 120)
        (self.mine / 'player.json').write_text(json.dumps(dict(pid=self.proc.pid)), encoding='utf-8')
        launched = []
        V.dispatch_video_command(self.mine, 'play', dict(playlist=[]), None, lambda f: launched.append(f) or 'new')
        self.assertEqual(launched, []); self.assertEqual(len(list((self.mine / 'commands').glob('*.json'))), 1)
        self.assertFalse(V.LAST['opened'])

    def test_window_of_another_nick_folder_is_reused(self):
        self.status(self.other, 1)
        launched = []
        V.dispatch_video_command(self.mine, 'play', dict(playlist=['a.mp4']), None, lambda f: launched.append(f) or 'new')
        self.assertEqual(launched, [])
        cmds = list((self.other / 'commands').glob('*.json')); self.assertEqual(len(cmds), 1)
        self.assertEqual(json.loads(cmds[0].read_text(encoding='utf-8'))['action'], 'play')
        self.assertTrue(V.LAST['redirected'])

    def test_closed_window_or_dead_process_opens_new(self):
        (self.mine / 'player.json').write_text(json.dumps(dict(pid=self.proc.pid, closed=True)), encoding='utf-8')
        (self.other / 'player.json').write_text(json.dumps(dict(pid=999999)), encoding='utf-8')
        launched = []
        r = V.dispatch_video_command(self.mine, 'play', dict(playlist=[]), None, lambda f: launched.append(f) or 'new')
        self.assertEqual(r, 'new'); self.assertEqual(launched, [self.mine]); self.assertTrue(V.LAST['opened'])

    def test_unreadable_status_is_read_again(self):
        self.status(self.mine, 1)
        real = Path.read_text; calls = {'n': 0}

        def flaky(path, *a, **k):
            if path.name == 'status.json' and calls['n'] == 0:
                calls['n'] += 1; raise PermissionError('đang ghi')
            return real(path, *a, **k)
        Path.read_text = flaky
        try:
            self.assertTrue(V._fresh(self.mine))
        finally:
            Path.read_text = real


if __name__ == '__main__':
    unittest.main()
