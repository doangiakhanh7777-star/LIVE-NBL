"""4.1.13 (owner 26/10/2026 20:34): the clip list of "Video & âm thanh" shows the pin script
("video 2.mp4 · 🚩 đã có kịch bản · 5 cờ"). The text is only for the eyes: the real file
path stays in the item data, otherwise saving the session would store the label as a path."""
import ast, sys, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT/'app.py').read_text(encoding='utf-8')


class Playlist(unittest.TestCase):
    def test_paths_are_never_read_from_the_label(self):
        self.assertIn('playlist=self.playlist_paths()', SRC)
        self.assertIn('existing=set(self.playlist_paths())', SRC)
        self.assertNotIn("self.playlist.addItems(", SRC)
        # the only place that reads the item text uses it as a fallback for old items
        uses = [l for l in SRC.splitlines() if 'self.playlist.item(i).text()' in l]
        self.assertEqual(len(uses), 1); self.assertIn('data(Qt.ItemDataRole.UserRole) or', uses[0])

    def test_each_item_keeps_its_path_and_shows_the_script_state(self):
        self.assertIn("it.setData(Qt.ItemDataRole.UserRole,path);it.setToolTip(path)", SRC)
        self.assertIn("'   🚩 đã có kịch bản · '", SRC); self.assertIn("'   · chưa có kịch bản'", SRC)
        self.assertIn("đã gửi kịch bản cho Chrome", SRC)
        self.assertIn('self.label_timer.start(5000)', SRC)

    def test_double_click_or_button_opens_the_editor_and_the_old_page_is_gone(self):
        self.assertIn('itemDoubleClicked.connect(lambda item:self.open_pin_script(item.data(Qt.ItemDataRole.UserRole)))', SRC)
        self.assertNotIn("self.page('Kịch bản ghim giỏ hàng')", SRC)
        ast.parse(SRC)


if __name__ == '__main__':
    unittest.main()
