"""4.3.8: every place that carries the version must say the same thing.

The 4.3.4 installer failed its own post-install check on a clean machine because
kiem_tra_cai_dat.py compared the Chrome manifest against the literal '4.3.0'.
"""
import ast
import json
import re
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
from diagnostics import VERSION


class VersionTest(unittest.TestCase):
    def test_manifest_matches(self):
        manifest = json.loads((BASE / 'CHROME_NBL_LIVE' / 'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['version'], VERSION)

    def test_window_title_matches(self):
        title = re.search(r"setWindowTitle\(([^)]*)\)", (BASE / 'app.py').read_text(encoding='utf-8'))
        self.assertTrue(title, 'app.py has no setWindowTitle')
        self.assertIn(VERSION, title.group(1), 'window title does not carry ' + VERSION)

    def test_setup_check_has_no_hardcoded_version(self):
        """kiem_tra_cai_dat.py must read the version, never spell one out."""
        src = (BASE / 'kiem_tra_cai_dat.py').read_text(encoding='utf-8')
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                self.assertFalse(re.fullmatch(r'\d+\.\d+\.\d+(\.\d+)?', node.value),
                                 'kiem_tra_cai_dat.py spells out a version: ' + node.value)


if __name__ == '__main__':
    unittest.main()
