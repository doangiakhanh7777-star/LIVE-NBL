"""Real Qt offscreen smoke; no native Windows/TikTok automation is executed."""
import importlib.util,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT));os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
@unittest.skipUnless(importlib.util.find_spec('PySide6'),'Qt test requires requirements-test.txt')
class QtSmokeTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  from PySide6.QtWidgets import QApplication
  cls.qt=QApplication.instance() or QApplication([])
 def test_actual_console_opens_and_closes(self):
  import app
  with tempfile.TemporaryDirectory() as d,patch.object(app,'DATA',Path(d)):
   window=app.Console()
   try:
    window.show();self.qt.processEvents();self.assertIn(__import__('diagnostics').VERSION,window.windowTitle());self.assertFalse(window.studio_panel.stopped)
   finally:window.close();self.qt.processEvents()
 def test_actual_console_recovers_bad_studio_file_and_notifies(self):
  import app
  from PySide6.QtWidgets import QMessageBox
  with tempfile.TemporaryDirectory() as d,patch.object(app,'DATA',Path(d)),patch.object(QMessageBox,'warning') as warning:
   (Path(d)/'studio_schedules.json').write_text('{broken',encoding='utf-8')
   window=app.Console()
   try:
    window.show();self.qt.processEvents();self.assertFalse(window.studio_panel.stopped);self.assertTrue(window.studio_panel.recovery_notice);self.assertTrue(warning.called)
   finally:window.close();self.qt.processEvents()
if __name__=='__main__':unittest.main()
