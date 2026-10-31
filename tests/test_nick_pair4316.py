"""4.3.16: nick SĂN DEAL GIÁ RẺ (@bechaudethuong12) bị chặn vì NBL còn nhớ @giakhanhdoxe của nick Studio cũ."""
import importlib.util, os, sys, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT)); os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'cần PySide6')
class NickPairTest(unittest.TestCase):
    def setUp(self):
        import studio_panel
        self.SP = studio_panel.StudioPanel
        self.logs = []; saved = []
        owner = type('O', (), {})(); owner.log = self.logs.append
        owner.data = {'sessions': [{'id': 's1', 'chrome_binding': {'account': 'bechaudethuong12'}}]}
        self.fake = type('F', (), {})(); self.fake.owner = owner; self.fake.save = lambda: saved.append(1)
        self.saved = saved

    def session(self, p):
        return self.SP.session(self.fake, p)

    def test_legacy_pair_from_old_studio_nick_is_repaired(self):
        p = {'session': 's1', 'cdp': True, 'name': 'SĂN DEAL GIÁ RẺ', 'handle': 'giakhanhdoxe'}   # bản cũ: không có handle_for
        self.session(p)                                             # trước 4.3.16: ValueError "Chrome đang là @bechaudethuong12…"
        self.assertEqual((p['handle'], p['handle_for']), ('bechaudethuong12', 'SĂN DEAL GIÁ RẺ'))
        self.assertTrue(self.saved); self.assertIn('ghép lại', self.logs[-1])

    def test_same_studio_nick_with_another_chrome_login_is_still_refused(self):
        p = {'session': 's1', 'cdp': True, 'name': 'SĂN DEAL GIÁ RẺ', 'handle': 'nickkhac', 'handle_for': 'SĂN DEAL GIÁ RẺ'}
        with self.assertRaises(ValueError) as e:
            self.session(p)
        self.assertIn('@bechaudethuong12', str(e.exception))

    def test_studio_switched_nick_repairs(self):
        p = {'session': 's1', 'cdp': True, 'name': 'SĂN DEAL GIÁ RẺ', 'handle': 'giakhanhdoxe', 'handle_for': 'Khánh Car Auto'}
        self.session(p); self.assertEqual(p['handle'], 'bechaudethuong12')

    def test_first_time_pairs(self):
        p = {'session': 's1', 'cdp': True, 'name': 'SĂN DEAL GIÁ RẺ'}
        self.session(p); self.assertEqual((p['handle'], p['handle_for']), ('bechaudethuong12', 'SĂN DEAL GIÁ RẺ'))


if __name__ == '__main__':
    unittest.main()
