"""4.3.13: giữ phím cách để nói (ptt_core) + gửi video từ điện thoại (video_store, phone_api).

Không cần Qt: phần HTTP chạy server thật trên cổng tạm, gửi file thật theo khúc.
"""
import array
import hashlib
import http.client
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import phone_api
import ptt_core
import video_store
from video_store import StoreError, VideoStore, safe_name


class GateTest(unittest.TestCase):
    def run_keys(self, timeline, end):
        """timeline: [(t, pressed)] — trả danh sách (t, open) mỗi 10 ms."""
        g = ptt_core.Gate(); out = []; t = 0.0; i = 0; pressed = False
        while t <= end:
            while i < len(timeline) and timeline[i][0] <= t + 1e-9:
                pressed = timeline[i][1]; i += 1
            out.append((round(t, 3), g.update(pressed, t))); t += 0.01
        return out

    def test_quick_taps_never_open_the_mic(self):
        # gõ chữ: mỗi lần chạm phím cách ~100 ms
        taps = []
        for k in range(10):
            taps += [(k * 0.3, True), (k * 0.3 + 0.1, False)]
        self.assertFalse(any(o for _, o in self.run_keys(taps, 3.5)))

    def test_hold_opens_after_250ms_and_closes_150ms_after_release(self):
        r = dict(self.run_keys([(0.0, True), (1.0, False)], 1.6))
        self.assertFalse(r[0.2]); self.assertTrue(r[0.26]); self.assertTrue(r[1.0])
        self.assertTrue(r[1.1]); self.assertFalse(r[1.17])

    def test_short_gap_while_talking_does_not_cut(self):
        r = dict(self.run_keys([(0.0, True), (0.6, False), (0.7, True), (1.2, False)], 1.6))
        self.assertTrue(all(r[t] for t in (0.65, 0.7, 0.8, 1.0)))


class ConvertTest(unittest.TestCase):
    def test_mono_to_stereo_and_back(self):
        mono = array.array('h', [0, 1000, -2000, 32767]).tobytes()
        st = ptt_core.convert(mono, 1, 2)
        self.assertEqual(list(array.array('h', st)), [0, 0, 1000, 1000, -2000, -2000, 32767, 32767])
        self.assertEqual(ptt_core.convert(st, 2, 1), mono)

    def test_int16_float_roundtrip(self):
        mono = array.array('h', [0, 16384, -16384]).tobytes()
        f = array.array('f'); f.frombytes(ptt_core.convert(mono, 1, 1, False, True))
        self.assertAlmostEqual(f[1], 0.5, places=3); self.assertAlmostEqual(f[2], -0.5, places=3)
        back = array.array('h', ptt_core.convert(f.tobytes(), 1, 1, True, False))
        self.assertTrue(abs(back[1] - 16384) <= 1)

    def test_peak(self):
        self.assertEqual(ptt_core.peak(b''), 0.0)
        self.assertAlmostEqual(ptt_core.peak(array.array('h', [0, -16384, 100]).tobytes()), 0.5, places=3)

    def test_odd_byte_count_is_safe(self):
        self.assertEqual(len(ptt_core.convert(b'\x01\x02\x03', 1, 2)), 4)


class SettingsTest(unittest.TestCase):
    def test_defaults_and_unknown_keys(self):
        with tempfile.TemporaryDirectory() as d:
            st = ptt_core.Settings(Path(d) / 'giong_noi.json')
            self.assertEqual(st.load(), ptt_core.Settings.DEFAULTS)
            st.save(dict(enabled=True, mic='ab', junk=1))
            self.assertEqual(st.load()['enabled'], True); self.assertNotIn('junk', st.load())


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()); self.store = VideoStore(self.tmp / 'videos')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def send(self, uid, name, data, chunk):
        import io
        off = 0; res = None
        while off < len(data):
            part = data[off:off + chunk]
            res = self.store.write(uid, name, len(data), off, io.BytesIO(part), len(part)); off = res['received']
        return res

    def test_safe_name(self):
        self.assertEqual(safe_name('../../Windows/x.MP4'), 'x.mp4')
        self.assertEqual(safe_name('a<b>c:d.mov'), 'abcd.mov')
        self.assertEqual(safe_name('CON.mp4'), '_CON.mp4')
        for bad in ('virus.exe', 'x.mp4.bat', 'noext'):
            with self.assertRaises(StoreError):
                safe_name(bad)

    def test_chunks_assemble_exact_file_and_names_do_not_clash(self):
        data = os.urandom(3 * 1024 * 1024 + 123)
        r1 = self.send('aaaaaaaa1', 'clip.mp4', data, 1 << 20)
        r2 = self.send('aaaaaaaa2', 'clip.mp4', data[:1000], 1 << 20)
        self.assertTrue(r1['done']); self.assertEqual(Path(r1['path']).read_bytes(), data)
        self.assertEqual(Path(r2['path']).name, 'clip (2).mp4')
        self.assertEqual(sorted(f['name'] for f in self.store.files()), ['clip (2).mp4', 'clip.mp4'])
        self.assertFalse(any((self.tmp / 'videos' / '.dang_tai').iterdir()))

    def test_wrong_offset_tells_where_to_resume(self):
        import io
        data = os.urandom(5000)
        self.store.write('bbbbbbbb', 'v.mp4', 5000, 0, io.BytesIO(data[:2000]), 2000)
        with self.assertRaises(StoreError) as e:
            self.store.write('bbbbbbbb', 'v.mp4', 5000, 4000, io.BytesIO(data[4000:]), 1000)
        self.assertEqual((e.exception.status, e.exception.received), (409, 2000))
        self.assertEqual(self.store.status('bbbbbbbb')['received'], 2000)

    def test_network_cut_mid_chunk_rolls_back_that_chunk(self):
        import io
        data = os.urandom(6000)
        self.store.write('cccccccc', 'v.mp4', 6000, 0, io.BytesIO(data[:3000]), 3000)
        with self.assertRaises(StoreError) as e:      # nói gửi 3000 mà chỉ tới 1200 byte thì đứt
            self.store.write('cccccccc', 'v.mp4', 6000, 3000, io.BytesIO(data[3000:4200]), 3000)
        self.assertEqual(e.exception.received, 3000)
        r = self.store.write('cccccccc', 'v.mp4', 6000, 3000, io.BytesIO(data[3000:]), 3000)
        self.assertEqual(Path(r['path']).read_bytes(), data)

    def test_disk_full_is_refused_before_writing(self):
        import io
        with mock.patch('video_store.shutil.disk_usage', return_value=mock.Mock(free=500 << 20)):
            with self.assertRaises(StoreError) as e:
                self.store.write('dddddddd', 'big.mp4', 400 << 20, 0, io.BytesIO(b'x' * 10), 10)
        self.assertEqual(e.exception.status, 507); self.assertIn('không đủ chỗ', str(e.exception))

    def test_bad_ids_and_sizes(self):
        import io
        for uid in ('../x', 'short', '', 'a' * 70):
            with self.assertRaises(StoreError):
                self.store.status(uid)
        with self.assertRaises(StoreError):
            self.store.write('eeeeeeee', 'v.mp4', 10, 0, io.BytesIO(b'x' * 20), 20)
        with self.assertRaises(StoreError):
            self.store.write('eeeeeeee', 'v.mp4', 10, 0, io.BytesIO(b''), video_store.CHUNK_MAX + 1)

    def test_delete_only_inside_store(self):
        import io
        r = self.store.write('ffffffff', 'v.mp4', 4, 0, io.BytesIO(b'abcd'), 4)
        outside = self.tmp / 'mine.mp4'; outside.write_bytes(b'x')
        with self.assertRaises(StoreError):
            self.store.delete(outside)
        with self.assertRaises(StoreError):
            self.store.find('../mine.mp4')
        self.store.delete(r['path']); self.assertFalse(Path(r['path']).exists()); self.assertTrue(outside.exists())

    def test_stale_parts_are_cleaned(self):
        parts = self.tmp / 'videos' / '.dang_tai'; parts.mkdir(parents=True)
        old = parts / 'zzzzzzzz.part'; old.write_bytes(b'x'); t = time.time() - 4 * 86400; os.utime(old, (t, t))
        new = parts / 'yyyyyyyy.part'; new.write_bytes(b'x')
        VideoStore(self.tmp / 'videos')
        self.assertFalse(old.exists()); self.assertTrue(new.exists())


class FakeActions:
    def __init__(self):
        self.uploaded_paths = []

    def uploaded(self, path):
        self.uploaded_paths.append(path); return dict(ok=True, name=Path(path).name, nick='SĂN DEAL GIÁ RẺ')

    def status(self):
        return dict(version='4.3.13', pc='test')

    def videos(self):
        return dict(files=[])


class HttpUploadTest(unittest.TestCase):
    """Server phone_api thật, gửi qua HTTP như điện thoại."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0)); self.port = s.getsockname()[1]
        self.cfg = phone_api.Config(self.tmp / 'phone_api.json')
        d = self.cfg.load(); d['port'] = self.port; self.cfg.save(d); self.token = d['token']
        self.store = VideoStore(self.tmp / 'videos'); self.actions = FakeActions()
        self.server = phone_api.Server(self.actions, self.cfg, self.store); self.server.start()
        self.stop = threading.Event()
        self.qt = threading.Thread(target=self.fake_qt, daemon=True); self.qt.start()

    def fake_qt(self):               # thay cho QTimer 100 ms của NBL
        while not self.stop.is_set():
            self.server.drain(); time.sleep(0.02)

    def tearDown(self):
        self.stop.set(); self.server.stop(); shutil.rmtree(self.tmp, ignore_errors=True)

    def call(self, method, path, body=None, token=None, headers=None):
        c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=20)
        h = {'Authorization': 'Bearer ' + (self.token if token is None else token)}; h.update(headers or {})
        c.request(method, path, body=body, headers=h); r = c.getresponse(); data = r.read(); c.close()
        return r.status, data

    def test_upload_page_needs_the_code(self):
        st, page = self.call('GET', '/upload?t=' + self.token, token='')
        self.assertEqual(st, 200); self.assertIn('Gửi video vào NBL'.encode(), page)
        st, _ = self.call('GET', '/upload?t=sai', token='')
        self.assertEqual(st, 401)

    def test_upload_20mb_in_chunks_with_a_broken_connection_then_resume(self):
        data = os.urandom(20 * 1024 * 1024 + 777); uid = 'abcdef0123456789'; chunk = 8 << 20
        q = lambda off: '/api/upload?id=%s&name=%s&size=%d&off=%d' % (uid, 'Video%20live.mp4', len(data), off)
        st, b = self.call('POST', q(0), data[:chunk]); self.assertEqual(st, 200)
        self.assertEqual(json.loads(b)['data'], dict(received=chunk, done=False))
        # khúc 2: mạng đứt sau 1 MB (gửi thiếu rồi đóng kết nối)
        s = socket.create_connection(('127.0.0.1', self.port))
        head = ('POST %s HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer %s\r\nContent-Length: %d\r\n\r\n' % (q(chunk), self.token, chunk)).encode()
        s.sendall(head + data[chunk:chunk + (1 << 20)]); s.shutdown(socket.SHUT_WR)
        try:
            s.recv(4096)
        except OSError:
            pass
        s.close(); time.sleep(0.3)
        st, b = self.call('GET', '/api/upload?id=' + uid)
        self.assertEqual(json.loads(b)['data']['received'], chunk, 'phần dở của khúc đứt phải bị bỏ')
        # gửi nhầm vị trí -> 409 kèm chỗ đúng
        st, b = self.call('POST', q(chunk * 2), data[chunk * 2:chunk * 3])
        self.assertEqual(st, 409); self.assertEqual(json.loads(b)['received'], chunk)
        off = chunk
        while off < len(data):
            st, b = self.call('POST', q(off), data[off:off + chunk]); self.assertEqual(st, 200, b)
            res = json.loads(b)['data']; off = res['received']
        self.assertTrue(res['done']); self.assertEqual(res['name'], 'Video live.mp4')
        self.assertEqual(res['added']['nick'], 'SĂN DEAL GIÁ RẺ'); self.assertNotIn('path', res)
        saved = Path(self.actions.uploaded_paths[0])
        self.assertEqual(hashlib.sha256(saved.read_bytes()).hexdigest(), hashlib.sha256(data).hexdigest())

    def test_wrong_code_and_wrong_type(self):
        st, _ = self.call('POST', '/api/upload?id=abcdefgh&name=a.mp4&size=4&off=0', b'abcd', token='sai')
        self.assertEqual(st, 401)
        st, b = self.call('POST', '/api/upload?id=abcdefgh&name=a.exe&size=4&off=0', b'abcd')
        self.assertEqual(st, 415); self.assertFalse((self.tmp / 'videos').exists() and any((self.tmp / 'videos').glob('*.exe')))

    def test_json_routes_still_work(self):
        st, b = self.call('GET', '/api/status'); self.assertEqual(st, 200)
        self.assertEqual(json.loads(b)['data']['version'], '4.3.13')


if __name__ == '__main__':
    unittest.main()
