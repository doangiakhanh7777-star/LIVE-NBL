"""4.1.11 (owner 26/10/2026): "Kịch bản ghim giỏ hàng" — watch the clip, stop, plant a flag
with the product NAME and how long; saved per clip; sent to Chrome during the LIVE."""
import json, os, sys, tempfile, time, types, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pin_scripts as P
from panel_harness import make, job

ROOT = Path(__file__).resolve().parents[1]


class Logic(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp()); self.clip = self.dir/'clip_ban_hang.mp4'; self.clip.write_bytes(b'x' * 1234)
        self.store = P.Store(self.dir/'kich_ban_ghim.json')

    def test_times_the_way_the_owner_writes_them(self):
        self.assertEqual([P.parse_time(x) for x in ('5', '5:30', '1:05:30', '90s', '2p')], [300, 330, 3930, 90, 120])
        self.assertEqual(P.parse_time('60', 'seconds'), 60); self.assertIsNone(P.parse_time('5:75'))
        self.assertEqual(P.fmt(330), '5:30'); self.assertEqual(P.fmt(3930), '1:05:30')

    def test_flags_are_saved_per_clip_and_survive_moving_the_file(self):
        entries, warnings = self.store.save(self.clip, [dict(at=95, name='Bơm lốp mini', hold=60), dict(at=30, name='Vietmap Live Pro', hold=45)], 600)
        self.assertEqual([e['at'] for e in entries], [30, 95])
        moved = self.dir/'khac'/'clip_ban_hang.mp4'; moved.parent.mkdir(); os.replace(self.clip, moved)
        self.assertEqual(len(self.store.entries(moved)), 2)

    def test_hold_rules_3_seconds_to_6_hours_default_60(self):
        with self.assertRaises(ValueError): P.clean([dict(at=10, name='A', hold=2)])
        self.assertEqual(P.parse_paste('5:00 | Bơm lốp')[0]['hold'], 60)
        self.assertEqual((P.MIN_HOLD, P.DEFAULT_HOLD), (3, 60))

    def test_mistakes_are_caught_before_saving(self):
        with self.assertRaises(ValueError): P.clean([dict(at=10, name='', hold=60)])
        with self.assertRaises(ValueError): P.clean([dict(at=10, name='A', hold=60), dict(at=10, name='B', hold=60)])
        with self.assertRaises(ValueError): P.clean([dict(at=700, name='A', hold=60)], 600)
        _, w = P.clean([dict(at=5, name='A', hold=60), dict(at=40, name='B', hold=900)], 600)
        self.assertTrue(any('20 giây đầu' in x for x in w)); self.assertTrue(any('cắt ngắn' in x for x in w)); self.assertTrue(any('cuối clip' in x for x in w))

    def test_paste_from_notepad_or_excel(self):
        e = P.parse_paste('0:30 | Vietmap Live Pro | 45\n5:00\tBơm lốp mini\t1:00\n# ghi chú\n')
        self.assertEqual([(x['at'], x['name'], x['hold']) for x in e], [(30, 'Vietmap Live Pro', 45), (300, 'Bơm lốp mini', 60)])
        with self.assertRaises(ValueError): P.parse_paste('abc | Bơm')

    def test_export_and_import_to_another_pc(self):
        self.store.save(self.clip, [dict(at=30, name='A', hold=30)], 600)
        out = self.dir/'kb.json'; self.store.export(self.clip, out)
        other = P.Store(self.dir/'may2.json'); clip2 = self.dir/'ten_khac.mp4'; clip2.write_bytes(b'y')
        entries, _ = other.import_into(clip2, out, 600); self.assertEqual(entries[0]['name'], 'A')

    def test_names_missing_from_the_cart(self):
        titles = ['Vietmap Live Pro Dẫn đường & Cảnh báo tốc độ', 'Bộ sạc điện thoại xe hơi nhanh 4 trong 1']
        entries = [dict(at=1, name='Vietmap Live Pro', hold=9), dict(at=20, name='bộ sạc  điện thoại', hold=9), dict(at=40, name='Bơm lốp mini', hold=9)]
        self.assertEqual(P.missing(entries, titles), ['Bơm lốp mini'])

    def test_what_chrome_receives(self):
        self.store.save(self.clip, [dict(at=30, name='A', hold=30)], 600)
        msg = P.sync_payload(self.store, dict(time=time.time(), state='PlayingState', position=31000, duration=600000, path=str(self.clip)))
        self.assertEqual((msg['action'], msg['position'], msg['clip'], msg['script']), ('clip_sync', 31000, P.clip_key(self.clip), [dict(at=30, name='A', hold=30)]))
        self.assertEqual(P.sync_payload(self.store, dict(time=1, path=str(self.dir/'none.mp4')))['script'], [])

    def test_virtual_cable_choice(self):
        devs = [('Loa (Realtek)', 'a'), ('CABLE Input (VB-Audio Virtual Cable)', 'b'), ('CABLE-A Input (VB-Audio Cable A)', 'c')]
        self.assertEqual(P.pick_cable(devs), ('b', 'CABLE Input (VB-Audio Virtual Cable)', 'CABLE Output (VB-Audio Virtual Cable)'))
        self.assertEqual(P.pick_cable(devs, ['b'])[0], 'c')                     # second nick, second cable
        self.assertIsNone(P.pick_cable(devs, ['b', 'c'])); self.assertIsNone(P.pick_cable([('Loa', 'a')]))


class AppSide(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()); (self.tmp/'runtime'/'s1').mkdir(parents=True)
        self.clip = self.tmp/'clip.mp4'; self.clip.write_bytes(b'z' * 99)
        P.Store(self.tmp/'kich_ban_ghim.json').save(self.clip, [dict(at=30, name='Bơm lốp mini', hold=60)], 600)

    def video(self, t):
        (self.tmp/'runtime'/'s1'/'status.json').write_text(json.dumps(dict(time=t, state='PlayingState', position=31000, duration=600000, path=str(self.clip))), encoding='utf-8')

    def test_script_reaches_chrome_even_for_a_live_started_by_hand(self):
        now = time.time(); p = make([]); p.owner.path = types.SimpleNamespace(parent=self.tmp); self.video(now)
        p.poll_clip(now); c = p.owner.bridge.commands[-1]
        self.assertEqual((c['action'], c['script'][0]['name']), ('clip_sync', 'Bơm lốp mini'))

    def test_missing_names_are_reported_once_the_cart_is_ready(self):
        now = time.time(); j = job(start=now + 600, cart=dict(state='ready', ready_at=now - 30))
        sessions = {'s1': dict(id='s1', device='', mute=False, playlist=[str(self.clip)])}
        p = make([j], sessions=sessions); p.owner.path = types.SimpleNamespace(parent=self.tmp)
        p.owner.bridge.snapshot = lambda: {'client': dict(cartTitles=['Vietmap Live Pro'])}
        p.check_scripts(now, P.Store(self.tmp/'kich_ban_ghim.json'))
        self.assertTrue(any('KHÔNG có trong giỏ' in a and 'Bơm lốp mini' in a for a in p.alerts))
        p.alerts.clear(); p.check_scripts(now + 5, P.Store(self.tmp/'kich_ban_ghim.json')); self.assertEqual(p.alerts, [])   # once

    def test_app_has_the_page_the_editor_and_the_cable_button(self):
        app = (ROOT/'app.py').read_text(encoding='utf-8'); ed = (ROOT/'pin_script_editor.py').read_text(encoding='utf-8')
        for text in ("self.page('Kịch bản ghim giỏ hàng')", 'Phát vào cáp ảo', 'PinScriptEditor(self,clip,self.pin_store,self.cart_titles)'):
            self.assertIn(text, app)
        for text in ("'⏸ Dừng'", 'Qt.Key.Key_Space', '🚩 Cắm cờ tại đây', 'self.audio.setMuted(True)', 'Dời cờ tới chỗ đang xem', 'P.MIN_HOLD, P.MAX_HOLD'):
            self.assertIn(text, ed)
        self.assertNotIn('NBL VIDEO', ed.split('"""', 2)[2])            # Studio must never take it for NBL VIDEO


if __name__ == '__main__':
    unittest.main()
