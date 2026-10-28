import hashlib, json, tempfile, time, unittest, zipfile
from pathlib import Path
import updater, diagnostics


def release(body, assets):
    return json.dumps(dict(tag_name='v4.3.1', body=body, assets=assets)).encode()


class Update430(unittest.TestCase):
    def test_latest_reads_exe_and_sha(self):
        sha = 'a' * 64
        r = updater.latest(fetch=lambda url: release('SHA256: ' + sha, [dict(name='NBL_LIVE_Setup_4.3.1.exe', browser_download_url='u', size=5)]))
        self.assertEqual((r['version'], r['sha256'], r['url']), ('4.3.1', sha, 'u'))
        self.assertTrue(updater.newer(r, '4.3.0'))
        self.assertFalse(updater.newer(r, '4.3.1'))
        self.assertFalse(updater.newer(r, '4.10.0'))

    def test_no_exe_is_none(self):
        self.assertIsNone(updater.latest(fetch=lambda url: release('', [])))

    def test_download_checks_sha(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / 'src.exe'; src.write_bytes(b'installer')
            good = dict(name='NBL_LIVE_Setup_4.3.1.exe', url=src.as_uri(), sha256=hashlib.sha256(b'installer').hexdigest())
            out = updater.download(good, Path(d) / 'u')
            self.assertEqual(out.read_bytes(), b'installer')
            with self.assertRaises(RuntimeError):
                updater.download(dict(good, sha256='0' * 64), Path(d) / 'v')
            self.assertEqual(list((Path(d) / 'v').glob('*')), [])
            with self.assertRaises(RuntimeError):
                updater.download(dict(good, sha256=''), Path(d) / 'w')


class Diag430(unittest.TestCase):
    def test_auto_rate_limit_keep_and_no_keys(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / 'ai_reply.json').write_text(json.dumps(dict(keys='SECRETKEY', prompt='shop')), encoding='utf-8')
            (d / 'bao_cao' / 'loi').mkdir(parents=True)
            (d / 'bao_cao' / 'loi' / 'x.json').write_text(json.dumps(dict(token='T', msg='lỗi')), encoding='utf-8')
            t = time.time()
            first = diagnostics.auto(d, 'captcha', now=t)
            self.assertIsNotNone(first)
            self.assertIsNone(diagnostics.auto(d, 'again', now=t + 60))
            with zipfile.ZipFile(first) as z:
                body = ''.join(z.read(n).decode('utf-8', 'replace') for n in z.namelist())
            self.assertNotIn('SECRETKEY', body); self.assertNotIn('"T"', body)
            self.assertIn('lỗi', body); self.assertIn('captcha', body)
            for i in range(7):
                p = diagnostics.auto(d, 'r', every=0, now=t + 10 + i)
            self.assertLessEqual(len(list((d / 'chan_doan').glob('*.zip'))), 5)


if __name__ == '__main__':
    unittest.main()
