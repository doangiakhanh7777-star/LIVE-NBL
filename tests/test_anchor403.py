"""4.0.3: account-image check tolerates hover tint and small shifts, still rejects another nick."""
import base64,io,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from PIL import Image,ImageDraw,ImageEnhance
import studio_vision as V
from studio_vision_logic import StudioAttention

def window(name,shift=(0,0),hover=0):
 im=Image.new('RGB',(400,300),(24,24,30));d=ImageDraw.Draw(im)
 x,y=300+shift[0],10+shift[1]
 d.rectangle((x-4,y-4,x+92,y+22),fill=(24+hover,24+hover,30+hover))
 d.ellipse((x,y,x+18,y+18),fill=(200,120,60));d.text((x+24,y+4),name,fill=(235,235,235))
 return im

class Native:
 def __init__(self,profile):self.p=profile;self.config=profile['vision']
 verify_account=V.NativeStudio.verify_account

def profile(saved):
 sample=saved.crop((296,6,392,34));b=io.BytesIO();sample.save(b,'PNG')
 anchor=dict(kind='visual',image=base64.b64encode(b.getvalue()).decode(),x=296,y=6,width=96,height=28,windowWidth=400,windowHeight=300,dpi=96)
 return dict(accountAnchor=json.dumps(anchor),vision=dict(dpi=96))

class AnchorTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.env=patch.dict(os.environ,{'LOCALAPPDATA':self.tmp.name});self.env.start();self.addCleanup(self.env.stop)
 def check(self,saved,current):Native(profile(saved)).verify_account(current)
 def test_same(self):self.check(window('Khanh Car'),window('Khanh Car'))
 def test_saved_while_hovered(self):self.check(window('Khanh Car',hover=40),window('Khanh Car'))
 def test_small_layout_shift(self):self.check(window('Khanh Car'),window('Khanh Car',shift=(2,-1)))
 def test_dimmed_inactive_window(self):self.check(window('Khanh Car'),ImageEnhance.Brightness(window('Khanh Car')).enhance(.9))
 def test_other_nick_rejected_and_debug_saved(self):
  with self.assertRaises(StudioAttention) as e:self.check(window('Khanh Car'),window('Phu Kien MT'))
  self.assertIn('Ảnh so sánh',str(e.exception))
  self.assertTrue(list((Path(self.tmp.name)/'NBL_LIVE_2'/'logs').glob('anh_ten_nick_*.png')))
 def test_moved_far_rejected(self):
  with self.assertRaises(StudioAttention):self.check(window('Khanh Car'),window('Khanh Car',shift=(-60,40)))

if __name__=='__main__':unittest.main()
