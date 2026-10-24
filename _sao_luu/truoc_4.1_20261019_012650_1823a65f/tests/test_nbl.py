"""NBL LIVE 4.0 regression tests. Run: python -m unittest discover -s tests -v

Windows-only pieces (screen capture, input, websockets server) are replaced by
fakes; these tests cover the decisions that were wrong in 3.9.
"""
import json
import sys
import tempfile
import threading
import time
import types
import unittest
import zipfile
from concurrent.futures import Future
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import studio_vision_logic as L  # noqa: E402


def line(text, y, x=10, h=14, score=.95):
    return dict(text=text, score=score, x=x, y=y, w=200, h=h)


class MatchingTests(unittest.TestCase):
    def test_accentless_ocr_still_matches(self):
        # The bundled model has no Vietnamese letters: it reads "Anh chi xem san pham".
        self.assertTrue(L.similar('Anh chi xem san pham trong gio nhe', 'Anh/chị xem sản phẩm trong giỏ nhé.'))
        self.assertTrue(L.similar('Anh chi xem san pharn trong gio nhe', 'Anh/chị xem sản phẩm trong giỏ nhé.'))
        self.assertFalse(L.similar('Chao ca nha', 'Cảm ơn cả nhà'))
        self.assertFalse(L.similar('abc', 'abd'))  # short text must be exact

    def test_draft_state(self):
        self.assertEqual(L.draft_state([line('Thêm bình luận...', 0)]), 'empty')
        self.assertEqual(L.draft_state([line('Them binh luan', 0, score=.83)]), 'empty')
        self.assertEqual(L.draft_state([line('Them binh luan', 0, score=.5)]), 'unknown')
        self.assertEqual(L.draft_state([]), 'unknown')
        self.assertEqual(L.draft_state([line('Xa kho gia soc hom nay', 0)], 'Xả kho giá sốc hôm nay'), 'expected')
        self.assertEqual(L.draft_state([line('chu khac', 0)], 'Xả kho giá sốc hôm nay'), 'occupied')

    def test_wrapped_own_message_is_counted(self):
        lines = [line('Khanh Car Auto', 0), line('Anh chi xem san pham', 18), line('trong gio hang nhe', 34),
                 line('Khach A', 60), line('gia bao nhieu', 78)]
        self.assertEqual(L.own_message_count(lines, 'Khánh Car Auto', 'Anh/chị xem sản phẩm trong giỏ hàng nhé'), 1)

    def test_same_line_author_and_other_author(self):
        lines = [line('Khanh Car Auto: Xa kho hom nay', 0), line('Khach B', 30), line('Xa kho hom nay', 48)]
        self.assertEqual(L.own_message_count(lines, 'Khánh Car Auto', 'Xả kho hôm nay'), 1)

    def test_confirmation_when_old_copy_scrolled_away(self):
        before = [line('Khanh Car Auto', 0), line('Xa kho hom nay', 18)] + [line('k'+str(i), 40+i*20) for i in range(8)]
        after = [line('k'+str(i), i*20) for i in range(8)] + [line('Khanh Car Auto', 180), line('Xa kho hom nay', 198)]
        self.assertTrue(L.message_confirmed(before, after, 'Khánh Car Auto', 'Xả kho hôm nay', 220))

    def test_no_confirmation_when_same_text_was_already_newest(self):
        same = [line('k1', 0), line('Khanh Car Auto', 180), line('Xa kho hom nay', 198)]
        self.assertFalse(L.message_confirmed(same, same, 'Khánh Car Auto', 'Xả kho hôm nay', 220))

    def test_greeting_rows(self):
        lines = [line('Lan Anh da tham gia', 20, x=5), line('Minh joined', 60, x=5)]
        self.assertEqual(L.greeting_key(L.lines_beside(lines, 300, 27, 20)), 'lan anh')
        self.assertEqual(L.greeting_key(L.lines_beside(lines, 300, 67, 20)), 'minh')

    def test_clock_ocr_confusions(self):
        self.assertEqual(L.clock_reading([line('O1:2O:33', 0)]), '01:20:33')

    def test_seen_names_forgets_oldest(self):
        seen = L.SeenNames(3)
        seen.update(['a', 'b', 'c', 'd'])
        self.assertNotIn('a', seen)
        self.assertIn('d', seen)
        self.assertEqual(len(seen), 3)


class FakeNative:
    touched = False
    verify_geometry = True

    def __init__(self, frames):
        self.frames = frames

    def snapshot(self, account=True):
        return self.frames(), 96

    def activate(self):
        pass

    def click(self, x, y):
        self.touched = True


class VisionTests(unittest.TestCase):
    def setUp(self):
        import studio_vision as V
        self.V = V
        V._live_cache.clear(); V._alert_cache.clear()
        self.cfg = dict(enabled=True, width=400, height=300, dpi=96,
                        regions=dict(clock=[10, 10, 80, 20], chat=[10, 100, 200, 150], input=[10, 260, 200, 30]))

    def reader_factory(self, alert_in_chat=False, alert_outside=False):
        calls = []
        clock = iter(['00:10:01', '00:10:02', '00:10:03', '00:10:04', '00:10:05', '00:10:06'])

        def reader(image):
            calls.append(image.size)
            if image.size == (400, 300):  # full-window warning scan
                lines = []
                if alert_outside:
                    lines.append(line('Vi phạm của video LIVE', 50))
                # Masking blacks out the chat, so a viewer comment there is invisible.
                if alert_in_chat and image.getpixel((50, 150)) != (0, 0, 0):
                    lines.append(line('captcha vi pham ha shop', 150))
                return lines
            if image.size == (80, 20):
                return [line(next(clock), 0)]
            return []
        return reader, calls

    def session(self, reader):
        from PIL import Image
        frame = Image.new('RGB', (400, 300), 'white')
        profile = dict(id='p1', pid='1', name='Khanh', vision=self.cfg)
        return self.V.VisionSession(profile, native=FakeNative(lambda: frame.copy()), reader=reader, sleep=lambda s: None)

    def test_viewer_comment_does_not_raise_alert(self):
        reader, _ = self.reader_factory(alert_in_chat=True)
        self.assertTrue(self.session(reader).live())

    def test_real_alert_outside_chat_is_reported(self):
        reader, _ = self.reader_factory(alert_outside=True)
        with self.assertRaises(ValueError):
            self.session(reader).live()

    def test_live_and_alert_results_are_cached(self):
        reader, calls = self.reader_factory()
        s = self.session(reader)
        self.assertTrue(s.live())
        first = len(calls)
        self.assertTrue(s.live())
        self.assertEqual(len(calls), first)        # cached LIVE state
        s.live(fresh=True)
        self.assertNotIn((400, 300), calls[first:])  # probes reuse the warning cache

    def test_untouched_failures_become_not_touched(self):
        # NativeStudio cannot start off Windows -> nothing was clicked -> NotTouched.
        with self.assertRaises(L.NotTouched):
            self.V.execute_vision(dict(vision=self.cfg, pid='1'), 'status')

    def test_failure_after_click_stays_a_hard_error(self):
        V = self.V
        original = V.VisionSession

        class Clicked:
            def __init__(self, *a, **k):
                self.native = FakeNative(lambda: None); self.native.touched = True
        V.VisionSession = Clicked
        original_run = V._run
        V._run = lambda *a: (_ for _ in ()).throw(ValueError('Chưa xác nhận tin'))
        try:
            with self.assertRaises(ValueError) as caught:
                V.execute_vision({}, 'send')
            self.assertNotIsInstance(caught.exception, L.NotTouched)
        finally:
            V.VisionSession = original; V._run = original_run


class SyncPool:
    def submit_priority(self, priority, fn, *args, **kwargs):
        future = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except BaseException as error:
            future.set_exception(error)
        return future


class InteractionTests(unittest.TestCase):
    def setUp(self):
        import studio_interactions as I
        self.I = I
        self.tmp = tempfile.TemporaryDirectory()
        self.now = [1000.0]
        self.alerts = []
        self.profile = dict(id='p1', name='Nick 1', pid='1', windowTitle='LIVE Studio', exePath='x', accountAnchor='a',
                            vision=dict(enabled=True, width=400, height=300, regions=dict(
                                input=[0, 0, 50, 20], send=[0, 0, 50, 20], chat=[0, 0, 50, 50], clock=[0, 0, 50, 20]),
                                sendImage='x'))

    def tearDown(self):
        self.tmp.cleanup()

    def engine(self, executor):
        return self.I.StudioInteractions(SyncPool(), Path(self.tmp.name)/'journal.json', lambda t: None,
                                         lambda k, t: self.alerts.append(t), clock=lambda: self.now[0], executor=executor)

    def test_not_touched_keeps_feature_on_and_retries_same_line(self):
        sent = []

        def executor(profile, action, deadline, payload):
            sent.append(payload['text'])
            raise L.NotTouched('Studio đang bị cửa sổ khác che')
        e = self.engine(executor)
        e.enable(self.profile, 'message', dict(messages='Câu 1\nCâu 2', interval=60))
        self.now[0] += 61; e.tick([self.profile])   # submit (fails synchronously)
        e.tick([self.profile])                       # collect result
        s = e.state('p1')
        self.assertTrue(s['message'])
        self.assertIn('Tạm hoãn', s['message_status'])
        self.assertEqual(s['next_message'], self.now[0] + 30)
        self.now[0] += 31; e.tick([self.profile]); e.tick([self.profile])
        self.assertEqual(sent, ['Câu 1', 'Câu 1'])   # same line again, not skipped
        journal = json.loads((Path(self.tmp.name)/'journal.json').read_text(encoding='utf-8'))
        self.assertEqual({a['state'] for a in journal['attempts']}, {'not_sent'})

    def test_alert_after_repeated_not_touched(self):
        e = self.engine(lambda *a: (_ for _ in ()).throw(L.NotTouched('che')))
        e.enable(self.profile, 'message', dict(messages='A', interval=60))
        for _ in range(self.I.ALERT_AFTER):
            self.now[0] += 400; e.tick([self.profile]); e.tick([self.profile])
        self.assertEqual(len(self.alerts), 1)

    def test_uncertain_failure_still_stops(self):
        e = self.engine(lambda *a: (_ for _ in ()).throw(ValueError('Chưa xác nhận tin của đúng nick')))
        e.enable(self.profile, 'message', dict(messages='A', interval=60))
        self.now[0] += 61; e.tick([self.profile]); e.tick([self.profile])
        self.assertFalse(e.state('p1')['message'])
        self.assertIn('Cần kiểm tra', e.state('p1')['message_status'])


class ModelTests(unittest.TestCase):
    def test_backup_and_recovery(self):
        import model
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'profiles.json'
            good = {'schema': 2, 'sessions': [model.new_session(1)]}
            for key in ('loop', 'shuffle', 'mute'):
                good['sessions'][0].setdefault(key, False)
            model.write_json(path, good)
            model.write_json(path, good)               # second save makes the .bak
            self.assertTrue((Path(folder)/'profiles.json.bak').exists())
            path.write_text('{broken', encoding='utf-8')
            notes = []
            loaded = model.load(path, notes.append)
            self.assertEqual(loaded['sessions'][0]['id'], good['sessions'][0]['id'])
            self.assertTrue(notes and 'bản lưu tốt' in notes[0])
            self.assertTrue(list(Path(folder).glob('profiles.json.broken-*')))

    def test_salvage_keeps_valid_sessions(self):
        import model
        a, b = model.new_session(1), model.new_session(2)
        for s in (a, b):
            s.update(loop=True, shuffle=False, mute=False)
        b['volume'] = 999
        value = model.salvage({'schema': 2, 'sessions': [a, b], 'jobs': 'bad'})
        self.assertEqual([s['number'] for s in value['sessions']], [1])
        self.assertNotIn('jobs', value)


class ChromeBridgeTests(unittest.TestCase):
    def test_close_delivers_stop_before_shutdown(self):
        # websockets is replaced by a stub; the handler loop is emulated by a thread.
        original_modules={k:v for k,v in sys.modules.items() if k=='chrome_bridge' or k.startswith('websockets')}
        def restore_modules():
            for k in list(sys.modules):
                if k=='chrome_bridge' or k.startswith('websockets'):sys.modules.pop(k,None)
            sys.modules.update(original_modules)
        self.addCleanup(restore_modules)
        stub = types.ModuleType('websockets'); sync = types.ModuleType('websockets.sync'); server = types.ModuleType('websockets.sync.server')
        server.serve = lambda *a, **k: None
        sys.modules.update({'websockets': stub, 'websockets.sync': sync, 'websockets.sync.server': server})
        sys.modules.pop('chrome_bridge', None)
        import chrome_bridge
        bridge = chrome_bridge.ChromeBridge(port=1)
        delivered = []

        class WS:
            def close(self):
                pass
        bridge.clients['c1'] = dict(ws=WS(), queue=[], last=time.monotonic())

        def handler():
            while not bridge.closed:
                with bridge.lock:
                    commands, bridge.clients['c1']['queue'] = bridge.clients['c1']['queue'], []
                delivered.extend(commands)
                bridge.accept_acks('c1',[{'id':c['id'],'error':''} for c in commands],{'pin':{'running':False},'reply':{'running':False}})
                time.sleep(.2)
        thread = threading.Thread(target=handler, daemon=True); thread.start()
        bridge.close()
        thread.join(2)
        self.assertTrue(any(c['action'] == 'stop' and c['module'] == 'all' for c in delivered))


class MiscTests(unittest.TestCase):
    def test_windows_paths_compare_equal(self):
        import ntpath
        import video_commands
        original = video_commands.os.path
        video_commands.os.path = ntpath
        try:
            self.assertTrue(video_commands.same_file('C:/Videos/A.mp4', r'c:\videos\a.mp4'))
            self.assertFalse(video_commands.same_file('C:/Videos/A.mp4', r'C:\Videos\B.mp4'))
        finally:
            video_commands.os.path = original

    def test_backoff_steps(self):
        import studio_interactions as I
        self.assertEqual([I.backoff(n) for n in (1, 2, 3, 4, 9)], [30, 60, 120, 300, 300])

    def test_diagnostics_hide_secrets(self):
        import diagnostics
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder)
            (data/'studio_schedules.json').write_text(json.dumps({'profiles': [{'name': 'A', 'accountAnchor': json.dumps({'kind': 'visual', 'image': 'AAAA'}), 'vision': {'sendImage': 'BBBB'}}]}), encoding='utf-8')
            (data/'notifications.json').write_text('{"protected_token":"SECRET"}', encoding='utf-8')
            (data/'logs').mkdir(); (data/'logs'/'app.log').write_text('ok', encoding='utf-8')
            out = diagnostics.build(data, data/'d.zip')
            with zipfile.ZipFile(out) as z:
                names = z.namelist(); body = ''.join(z.read(n).decode('utf-8') for n in names)
            self.assertNotIn('notifications.json', names)
            self.assertNotIn('SECRET', body); self.assertNotIn('AAAA', body); self.assertNotIn('BBBB', body)
            self.assertIn('logs/app.log', names)


if __name__ == '__main__':
    unittest.main()
