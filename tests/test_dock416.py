"""4.1.6 (owner photos 19/10/2026 16:18): NBL pressed the floating chat's SETTINGS gear
instead of GHÉP (that window had no close icon, so "2nd from the right" was wrong);
and the owner's "👋 Chào" button is shipped as the built-in sample."""
import base64, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import studio_vision as V
from studio_vision_logic import default_greeting
from PIL import Image, ImageDraw

DATA = Path(__file__).resolve().parent / 'data'
BASE = Path(__file__).resolve().parents[1]


class Dock(unittest.TestCase):
    def test_window_with_close_icon_still_docks(self):
        x, y = V.dock_icon(Image.open(DATA/'cua_so_tro_chuyen_noi.png'))
        self.assertAlmostEqual(x, 1150-864, delta=4)

    def test_window_without_close_icon_picks_ghep_not_the_gear(self):
        im = Image.open(DATA/'cua_so_tro_chuyen_noi.png').convert('RGB')
        ImageDraw.Draw(im).rectangle((308, 14, 328, 36), fill=im.getpixel((300, 10)))   # remove the close icon
        x, y = V.dock_icon(im)
        self.assertAlmostEqual(x, 1150-864, delta=4)            # still GHÉP, not the gear at ≈254

    def test_owner_photo_of_the_bug(self):
        photo = Image.open(DATA/'cua_so_noi_khong_x.jpg')       # lock, gear, GHÉP — no close icon
        x, y = V.dock_icon(photo, 1.8)
        self.assertAlmostEqual(x, 541, delta=8); self.assertAlmostEqual(y, 40, delta=8)

    def test_no_dock_icon_means_no_click(self):
        im = Image.open(DATA/'cua_so_tro_chuyen_noi.png').convert('RGB')
        ImageDraw.Draw(im).rectangle((276, 14, 296, 36), fill=im.getpixel((300, 10)))   # remove GHÉP itself
        self.assertIsNone(V.dock_icon(im))


class Greeting(unittest.TestCase):
    def test_builtin_sample_finds_every_chao_button_on_the_owner_screen(self):
        cfg = default_greeting({'regions': {'chat': [905, 470, 295, 210]}})
        self.assertTrue(cfg['greetingDefault']); self.assertEqual(cfg['regions']['greeting'][2:], [68, 28])
        frame = Image.open(DATA/'studio_ghep_chao.png')
        hits = V.button_matches(frame, cfg['regions']['chat'], cfg['greetingImage'])
        self.assertEqual(sorted(round(y) for x, y in hits), [577, 613, 649])
        self.assertTrue(all(abs(x-1148) <= 2 for x, y in hits))

    def test_a_button_the_owner_picked_wins(self):
        mine = {'greetingImage': 'abc', 'regions': {'greeting': [1, 2, 30, 20]}}
        self.assertEqual(default_greeting(mine), mine)

    def test_sample_is_installed_with_the_app(self):
        self.assertTrue((BASE/'assets'/'chao_mau.png').is_file())


if __name__ == '__main__':
    unittest.main()
