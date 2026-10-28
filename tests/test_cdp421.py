"""4.2.1: kết nối Studio tự động — driven against a page built like Studio 1.38.0
(measured 28/10/2026). Needs a Chromium; skipped when none is installed."""
import os, shutil, subprocess, sys, time, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
import studio_cdp as C

PAGE = Path(__file__).resolve().parent / 'data' / 'fakestudio' / 'html' / 'main' / 'index.html'


def chromium():
    for name in ('chromium', 'chromium-browser', 'google-chrome'):
        if shutil.which(name): return shutil.which(name)
    try:
        return subprocess.run(['node', '-e', "console.log(require('playwright').chromium.executablePath())"], capture_output=True, text=True, timeout=20).stdout.strip() or None
    except Exception:
        return None


class Health(unittest.TestCase):
    def test_reads_upload_and_fps(self):
        self.assertEqual(C.health({'Tải lên:': '1825 kbps', 'FPS:': '30/30'}), dict(upload=1825, fps=30))
        self.assertEqual(C.health({'Upload:': '0 kbps', 'FPS:': '0/30'}), dict(upload=0, fps=0))
        self.assertEqual(C.health({}), dict(upload=None, fps=None))


@unittest.skipUnless(os.name != 'nt' and chromium() and Path(chromium() or '/').exists(), 'cần Chromium')
class FakeStudio(unittest.TestCase):
    PORT = 9361

    @classmethod
    def setUpClass(cls):
        cls.proc = subprocess.Popen([chromium(), '--headless=new', '--no-sandbox', '--remote-debugging-port=%d' % cls.PORT,
                                     '--remote-allow-origins=http://127.0.0.1:%d' % cls.PORT, PAGE.as_uri()], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.studio = C.Studio(cls.PORT)
        for _ in range(40):
            time.sleep(.25)
            if cls.studio.alive() and cls.studio.page('/html/main/'): break

    @classmethod
    def tearDownClass(cls):
        cls.proc.kill()

    def test_full_live(self):
        s = self.studio
        self.assertFalse(s.status('Khánh Car Auto')['live'])
        with self.assertRaises(C.NotTouched):
            s.start('Nick Khác')                       # wrong nick: nothing is clicked
        self.assertFalse(s.status('Khánh Car Auto')['live'])
        self.assertTrue(s.start('Khánh Car Auto')['confirmed'])
        st = s.status('Khánh Car Auto'); self.assertTrue(st['live']); self.assertEqual(st['health'], dict(upload=1825, fps=30))
        self.assertTrue(s.send('Chào cả nhà 🚗', 'Khánh Car Auto')['confirmed'])
        self.assertIn('Chào cả nhà 🚗', s.js(s.main(), 'document.getElementById("log").textContent'))
        r = s.stop('Khánh Car Auto'); self.assertFalse(r['live']); self.assertFalse(r['summaryOpen'])
        self.assertEqual(s.js(s.main(), 'document.getElementById("sum").className'), 'hide')   # end page closed
        self.assertTrue(s.stop('Khánh Car Auto')['already'])


class Routing(unittest.TestCase):
    def test_closed_studio_means_live_over_and_nothing_opened_for_status(self):
        r = C.execute_cdp(dict(cdp=True, cdpPort=9399, exePath='/none/studio.exe', name='A'), 'status')
        self.assertEqual(r, dict(live=False, studioClosed=True, closed=True, method='cdp'))
        self.assertEqual(C.execute_cdp(dict(cdp=True, cdpPort=9399, exePath='/none'), 'probe'), dict(windowFound=False))

    def test_send_without_studio_is_not_touched(self):
        with self.assertRaises(C.NotTouched):
            C.execute_cdp(dict(cdp=True, cdpPort=9399, exePath='/none', name='A'), 'send', payload={'text': 'x'})


if __name__ == '__main__':
    unittest.main()
