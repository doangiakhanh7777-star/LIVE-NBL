"""4.1.1: the QR login feature is removed; Chrome is linked only by the pairing code."""
import ast
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]


def hint_function():
    tree = ast.parse((BASE / 'app.py').read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == 'chrome_account_hint':
            node.decorator_list = []
            scope = {}
            exec(compile(ast.Module(body=[node], type_ignores=[]), 'app.py', 'exec'), scope)
            return scope['chrome_account_hint']
    raise AssertionError('chrome_account_hint missing')


class QrRemoved(unittest.TestCase):
    def test_files_are_gone(self):
        self.assertFalse((BASE / 'shop_login.py').exists())
        self.assertFalse((BASE / 'CHROME_NBL_LIVE' / 'shop_login.js').exists())

    def test_app_has_no_qr_page_or_menu(self):
        src = (BASE / 'app.py').read_text(encoding='utf-8')
        for word in ('shop_login', 'ShopLoginPanel', 'def login_binding', 'self.login_binding', 'bằng QR', 'Đăng nhập TikTok Shop · QR',
                     'Lấy mã đăng nhập', 'setCurrentIndex(8)'):
            self.assertNotIn(word, src)
        self.assertIn("'TOOL NBL LIVE • 4.3.2'", src)

    def test_bridge_refuses_login_commands(self):
        import sys
        sys.path.insert(0, str(BASE))
        from chrome_bridge import ChromeBridge
        bridge = ChromeBridge.__new__(ChromeBridge)
        with self.assertRaises(ValueError):
            bridge.command('client', dict(action='shop_login', module='login'))
        with self.assertRaises(ValueError):
            bridge.command('client', dict(action='start', module='login'))
        src = (BASE / 'chrome_bridge.py').read_text(encoding='utf-8')
        self.assertNotIn('shopLogin', src)
        self.assertNotIn('qrDataUrl', src)

    def test_unreadable_nick_explains_what_to_do(self):
        hint = hint_function()
        self.assertIn('Bảng điều khiển LIVE', hint('Chưa đăng nhập'))
        self.assertIn('Bảng điều khiển LIVE', hint(''))
        self.assertIn('Tên tài khoản', hint('Chưa chọn tài khoản'))
        self.assertIn('F5', hint('Đang đọc trang'))
        for account in ('Chưa đăng nhập', 'Chưa chọn tài khoản', 'Đang đọc trang'):
            self.assertNotIn('QR', hint(account))

    def test_bind_never_jumps_to_a_login_page(self):
        src = (BASE / 'app.py').read_text(encoding='utf-8')
        body = src[src.index('    def bind_chrome(self):'):src.index('    def ', src.index('    def bind_chrome(self):') + 10)]
        self.assertIn('raise ValueError(self.chrome_account_hint(', body)
        self.assertNotIn("chrome_login_binding']=", body)


if __name__ == '__main__':
    unittest.main()
