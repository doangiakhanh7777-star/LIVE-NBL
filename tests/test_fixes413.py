"""4.1.3 (owner, 19/10/2026 03:37): next schedule did not start, end pages stayed open,
the mouse wheel changed numbers / choices. Real code, fake Qt / Chrome."""
import importlib, sys, time, types, unittest
from concurrent.futures import Future
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from panel_harness import make, job


def fake_qt():
    """Just enough of PySide6 for no_wheel.py (the real one is not on this test machine)."""
    core = types.ModuleType('PySide6.QtCore'); widgets = types.ModuleType('PySide6.QtWidgets')
    class QObject:
        def __init__(self, parent=None): self.parent = parent
    class QEvent:
        class Type: Wheel = 31; MouseButtonPress = 2
    core.QObject, core.QEvent = QObject, QEvent
    class QWidget:
        def __init__(self, parent=None): self._parent = parent
        def parentWidget(self): return self._parent
    class Bar(QWidget):
        def __init__(self, parent=None): super().__init__(parent); self.v = 500; self.shown = True
        def isVisible(self): return self.shown
        def value(self): return self.v
        def setValue(self, v): self.v = v
        def singleStep(self): return 10
    class QAbstractScrollArea(QWidget):
        def __init__(self, parent=None): super().__init__(parent); self.bar = Bar(self)
        def verticalScrollBar(self): return self.bar
    class QAbstractSlider(QWidget): pass
    class QScrollBar(QAbstractSlider): pass
    class QAbstractSpinBox(QWidget): pass
    class QComboBox(QWidget): pass
    for name, cls in dict(QWidget=QWidget, QAbstractScrollArea=QAbstractScrollArea, QAbstractSlider=QAbstractSlider,
                          QScrollBar=QScrollBar, QAbstractSpinBox=QAbstractSpinBox, QComboBox=QComboBox).items():
        setattr(widgets, name, cls)
    pyside = types.ModuleType('PySide6'); pyside.QtCore = core; pyside.QtWidgets = widgets
    return {'PySide6': pyside, 'PySide6.QtCore': core, 'PySide6.QtWidgets': widgets}


class Wheel(unittest.TestCase):
    def setUp(self):
        self.mods = fake_qt()
        self.patch = unittest.mock.patch.dict(sys.modules, self.mods); self.patch.start()
        sys.modules.pop('no_wheel', None); self.nw = importlib.import_module('no_wheel')
        self.W = self.mods['PySide6.QtWidgets']

    def tearDown(self):
        self.patch.stop(); sys.modules.pop('no_wheel', None)

    def wheel(self, target, dy=-120):
        ev = types.SimpleNamespace(type=lambda: 31, angleDelta=lambda: types.SimpleNamespace(y=lambda: dy))
        return self.nw.WheelGuard().eventFilter(target, ev)

    def test_wheel_never_reaches_numbers_dates_dropdowns_or_sliders(self):
        W = self.W; page = W.QAbstractScrollArea(); body = W.QWidget(page)
        for cls in (W.QAbstractSpinBox, W.QComboBox, W.QAbstractSlider):
            box = cls(body); inner = W.QWidget(box)       # e.g. the line edit inside a spin box
            self.assertTrue(self.wheel(box)); self.assertTrue(self.wheel(inner))
        self.assertEqual(page.bar.v, 500 + 6 * 30)            # the page scrolled instead (6 wheel notches down)

    def test_lists_text_boxes_scroll_bars_and_open_dropdown_lists_scroll_normally(self):
        W = self.W; page = W.QAbstractScrollArea(); body = W.QWidget(page)
        combo = W.QComboBox(body); popup_list = W.QAbstractScrollArea(combo); viewport = W.QWidget(popup_list)
        self.assertFalse(self.wheel(viewport))
        self.assertFalse(self.wheel(W.QWidget(W.QAbstractScrollArea(body))))
        self.assertFalse(self.wheel(page.bar.__class__(page)))
        self.assertFalse(self.wheel(W.QWidget(body)))

    def test_other_events_pass(self):
        ev = types.SimpleNamespace(type=lambda: 2)
        self.assertFalse(self.nw.WheelGuard().eventFilter(self.W.QComboBox(), ev))

    def test_app_installs_the_guard(self):
        src = (Path(__file__).resolve().parents[1] / 'app.py').read_text(encoding='utf-8')
        self.assertIn('from no_wheel import install as no_wheel;no_wheel(app)', src)


def done(result):
    f = Future(); f.set_result(result); return f


class Cart(unittest.TestCase):
    def test_busy_chrome_is_retried_in_20_seconds_without_using_an_attempt(self):
        now = time.time(); j = job(start=now + 400, cart=dict(state='preparing', attempts=0, next=0, command='cmd1', kind='add', until=now + 100))
        p = make([j]); p.owner.bridge.control = dict(id='cmd1', state='failed', error='Dừng tương tác và đợi thao tác chuẩn bị trước', busy='1')
        p.poll_cart(now)
        # 4.1.7: shown as "Chrome bận, chờ", not as a failed cart
        self.assertEqual((j['cart']['attempts'], j['cart']['state'], j['cart']['wait']), (0, 'none', 'Chrome đang bận')); self.assertAlmostEqual(j['cart']['next'], now + 20, delta=1)
        self.assertEqual(p.alerts, [])
        j['cart']['probe'] = dict(at=now + 21, live=False); j['cart']['reloaded_at'] = now; p.poll_cart(now + 21); self.assertEqual(p.owner.bridge.commands[-1]['action'], 'prepare_bundle')

    def test_real_failure_near_the_live_is_retried_after_one_minute(self):
        now = time.time(); j = job(start=now + 400, cart=dict(state='preparing', attempts=0, next=0, command='cmd1', kind='add', until=now + 100))
        p = make([j]); p.owner.bridge.control = dict(id='cmd1', state='failed', error='Chưa thấy nút "Thêm sản phẩm"')
        p.poll_cart(now)
        self.assertEqual(j['cart']['attempts'], 1); self.assertAlmostEqual(j['cart']['next'], now + 60, delta=1)
        self.assertTrue(any('thử lại sau 1 phút' in a for a in p.alerts))


class ChromeModules(unittest.TestCase):
    def test_no_reply_rules_means_pin_only_not_an_error(self):
        now = time.time(); j = job(state='running', chrome_start_at=now - 1, chrome_tries=1)
        p = make([j]); p.owner.bridge.modules = dict(reply=dict(running=False, error='Chưa có câu trả lời theo từ khóa · nhập nội dung thật vào ô'),
                                                     pin=dict(running=True))
        p.poll_chrome_modules(now)
        self.assertTrue(j['reply_skipped']); self.assertNotIn('chrome_start_at', j); self.assertEqual(p.alerts, [])
        p.start_chrome_modules(j); self.assertEqual([c['module'] for c in p.owner.bridge.commands], ['pin'])

    def test_notice_says_why_pin_did_not_start(self):
        now = time.time(); j = job(state='running', chrome_start_at=now - 1, chrome_tries=3)
        p = make([j]); p.owner.bridge.modules = dict(reply=dict(running=True), pin=dict(running=False))
        p.owner.bridge.snapshot = lambda: {'client': dict(modules=p.owner.bridge.modules, ackErrors=dict(pin='Chưa chọn sản phẩm muốn ghim'))}
        p.poll_chrome_modules(now)
        self.assertTrue(any('Ghim: Chưa chọn sản phẩm muốn ghim' in a for a in p.alerts))

    def test_bridge_keeps_the_last_start_error_per_module(self):
        import chrome_bridge, threading
        b = chrome_bridge.ChromeBridge.__new__(chrome_bridge.ChromeBridge)
        b.lock = threading.Lock(); b.clients = {'c': {}}; b.pending_commands = {'x1': dict(client='c', action='start', module='pin')}
        b.accept_acks('c', [dict(id='x1', error='Chưa chọn sản phẩm muốn ghim')], {})
        self.assertEqual(b.clients['c']['ackErrors'], {'pin': 'Chưa chọn sản phẩm muốn ghim'})


import unittest.mock  # noqa: E402

if __name__ == '__main__':
    unittest.main()


class StuckJob(unittest.TestCase):
    """The LIVE before ended but its end page was not recognised: 5 failed stops left
    the job in "Cần kiểm tra" for ever, so the next schedule of the nick got no cart."""
    def stuck(self):
        now = time.time()
        a = job(id='a', start=now - 900, end=now - 60, state='attention', end_stop_attempted=True, stop_attempts=5)
        b = job(id='b', start=now + 300, end=now + 1200)
        return now, a, b

    def test_stuck_job_is_looked_at_again(self):
        import studio_scheduler as S
        now, a, b = self.stuck()
        self.assertIn((a, 'status'), S.decisions([a, b], now))

    def test_studio_off_finishes_it_and_frees_the_next_schedule(self):
        now, a, b = self.stuck()
        p = make([a, b]); p.futures = {done(dict(live=False)): ('a', None, 'status')}
        p.tick()
        self.assertEqual(a['state'], 'finished')
        self.assertEqual([c['action'] for c in p.owner.bridge.commands[:2]], ['stop', 'finish_live'])   # 4.1.8: pin/reply off too
        p.poll_cart(time.time())
        self.assertEqual(p.owner.bridge.commands[-1]['action'], 'prepare_bundle')

    def test_still_live_after_its_end_is_ended_again_later(self):
        now, a, b = self.stuck()
        p = make([a, b]); p.futures = {done(dict(live=True)): ('a', None, 'status')}
        p.tick()
        self.assertEqual(a['state'], 'stop_retry'); self.assertGreater(a['retry_at'], time.time() + 170)

    def test_unreadable_studio_while_stuck_does_not_flood_telegram(self):
        now, a, b = self.stuck()
        f = Future(); f.set_exception(ValueError('Chưa đọc được trạng thái LIVE'))
        p = make([a, b]); p.futures = {f: ('a', None, 'status')}
        p.tick()
        self.assertEqual(a['state'], 'attention'); self.assertEqual(p.alerts, [])
