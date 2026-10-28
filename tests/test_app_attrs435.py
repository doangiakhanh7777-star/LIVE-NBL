"""4.3.5 (owner 29/10 03:54, NBL không mở được: 'Console' object has no attribute 'LIVE_CHROME_TEXT').
No Qt here, so check statically: every self.<name> used in app.py's Console is defined somewhere
(method, class attribute, or assigned on self / by setattr)."""
import ast, re, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QT = set('''show hide close resize size setWindowTitle setMinimumSize setMaximumWidth setWindowFlag setCentralWidget
setStyleSheet style isVisible raise_ activateWindow windowHandle closeEvent menuBar statusBar setWindowIcon move
geometry width height setFixedSize update repaint showNormal showMinimized isMinimized setAttribute event screen
setFocus findChild findChildren deleteLater installEventFilter windowState setWindowState winId adjustSize'''.split())


class AppAttributes(unittest.TestCase):
    def test_every_self_attribute_exists(self):
        src = (ROOT / 'app.py').read_text(encoding='utf-8'); tree = ast.parse(src)
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Console')
        defined = set(QT)
        for n in cls.body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)): defined.add(n.name)
            if isinstance(n, ast.Assign): defined |= {t.id for t in n.targets if isinstance(t, ast.Name)}
        for n in ast.walk(cls):
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == 'self' and isinstance(n.ctx, ast.Store):
                defined.add(n.attr)
            if isinstance(n, ast.Tuple):
                for e in n.elts:
                    if isinstance(e, ast.Attribute) and isinstance(e.value, ast.Name) and e.value.id == 'self' and isinstance(e.ctx, ast.Store): defined.add(e.attr)
        defined |= set(re.findall(r"setattr\(self,'(\w+)'", src)) | set(re.findall(r"getattr\(self,'(\w+)'", src))
        used = {n.attr for n in ast.walk(cls) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == 'self' and isinstance(n.ctx, ast.Load)}
        self.assertEqual(sorted(used - defined), [])


if __name__ == '__main__':
    unittest.main()
