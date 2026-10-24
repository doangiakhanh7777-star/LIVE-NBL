"""4.0.3: LIVE timer inside the End button is read reliably; failures leave a debug image."""
import os,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from PIL import Image
import studio_vision as V
import studio_vision_logic as L

def line(t,s=.8):return dict(text=t,score=s,x=0,y=0,w=10,h=10)
CFG=dict(enabled=True,width=400,height=300,dpi=96,regions=dict(clock=[300,250,90,30]))

def session(reads):
 frame=Image.new('RGB',(400,300),'black')
 native=types.SimpleNamespace(touched=False,snapshot=lambda:(frame.copy(),96))
 it=iter(reads)
 def reader(im):
  if im.size==(400,300):return []
  return next(it)
 return V.VisionSession(dict(id='p',pid='1',vision=CFG),native=native,reader=reader,sleep=lambda s:None)

class ClockTests(unittest.TestCase):
 def setUp(self):
  V._live_cache.clear();V._alert_cache.clear();V._clock_debug_at[0]=-1e9
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  p=patch.dict(os.environ,{'LOCALAPPDATA':self.tmp.name});p.start();self.addCleanup(p.stop)
 def test_timer_with_button_text_and_dots(self):
  self.assertTrue(session([[line('Kết thúc'),line('00.05.24',.7)],[line('00:05:25')]]).live(fresh=True))
 def test_plain_unreadable_then_inverted_copy(self):
  self.assertTrue(session([[],[line('00:05:24')],[line('0O:05:26',.6)]]).live(fresh=True))
 def test_frozen_timer_is_not_live(self):
  with self.assertRaises(ValueError) as e:session([[line('00:05:24')],[line('00:05:24')]]).live(fresh=True)
  self.assertIn('00:05:24 → 00:05:24',str(e.exception))
 def test_failure_saves_debug(self):
  with self.assertRaises(ValueError) as e:session([[],[],[],[],[],[]]).live(fresh=True)
  self.assertIn('Ảnh đồng hồ',str(e.exception))
  logs=Path(self.tmp.name)/'NBL_LIVE_2'/'logs'
  self.assertTrue(list(logs.glob('dong_ho_*.png')) and list(logs.glob('dong_ho_*.txt')))
 def test_slow_warning_scan_uses_screenshot_time(self):
  # The full-window warning OCR takes 17 s; the timer moves 17 s between screenshots.
  t=[100.0]
  frame=Image.new('RGB',(400,300),'black')
  native=types.SimpleNamespace(touched=False,snapshot=lambda:(frame.copy(),96))
  reads=iter([[line('00:01:37')],[line('00:01:54')]])
  def reader(im):
   if im.size==(400,300):t[0]+=17;return []
   return next(reads)
  s=V.VisionSession(dict(id='p',pid='1',vision=CFG),native=native,reader=reader,sleep=lambda x:t.__setitem__(0,t[0]+1.3),clock=lambda:t[0])
  self.assertTrue(s.live(fresh=True))
 def test_wrong_jump_rejected(self):
  self.assertFalse(L.clock_advancing('00:05:24','00:09:24',1.5))
  self.assertFalse(L.clock_advancing('00:05:24','00:05:25',18))  # frozen-ish timer vs 18 s real time

if __name__=='__main__':unittest.main()
