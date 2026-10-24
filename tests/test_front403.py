import sys, time, types, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import studio_vision as V


def native(front_after, methods_needed=1):
    """Studio comes to the front `front_after` seconds after the n-th attempt."""
    n = V.NativeStudio.__new__(V.NativeStudio)
    n.handle = 100; n.studio_pid = 7; n.deadline = 0; n.touched = False
    n.p = {'allowMouse': True}
    state = dict(fg=555, attempts=0, at=None)
    def attempt(*a):
        state['attempts'] += 1
        if state['attempts'] >= methods_needed and state['at'] is None:
            state['at'] = time.time() + front_after
    def fg():
        if state['at'] is not None and time.time() >= state['at']:
            state['fg'] = 100
        return state['fg']
    n.u = types.SimpleNamespace(GetForegroundWindow=fg, IsIconic=lambda h: False)
    n.is_studio = lambda h: h == 100
    n._force_foreground = attempt; n._switch_to = attempt; n._click_title_bar = attempt
    n.front_name = lambda: 'NBL_LIVE.exe'
    return n, state


class Front(unittest.TestCase):
    def test_slow_studio_still_comes_to_front(self):
        # 4.0.2/lan13 checked after 200 ms and gave up; Studio needed 600 ms here.
        n, state = native(.6)
        n.activate()
        self.assertTrue(n.in_front()); self.assertEqual(state['attempts'], 1)

    def test_title_click_used_when_other_ways_fail(self):
        n, state = native(.1, methods_needed=4)
        n.activate()
        self.assertEqual(state['attempts'], 4)

    def test_focus_lost_between_greeting_steps_is_recovered(self):
        n, state = native(.1)
        n.guard(True)            # e.g. right before clicking a Chào button
        self.assertTrue(n.in_front())

    def test_clear_error_names_the_window_in_front(self):
        n, state = native(99, methods_needed=99)
        with patch.object(V.NativeStudio, 'wait_front', lambda self, s: False):
            with self.assertRaises(ValueError) as caught:
                n.activate()
        self.assertIn('NBL_LIVE.exe', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
