"""4.0.3: Studio's own popups are not a cover; only areas NBL uses are checked."""
import ctypes,json,sys,types,unittest
from ctypes import wintypes
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import studio_vision as V

STUDIO,PANEL,OTHER=100,200,300
class User:
 def __init__(self,layout):self.layout=layout
 def WindowFromPoint(self,p):return self.layout(p.x,p.y)
 def GetAncestor(self,h,flag):return h
 def GetWindowThreadProcessId(self,h,pid):ctypes.cast(pid,ctypes.POINTER(wintypes.DWORD))[0]=7 if h in (STUDIO,PANEL) else 9;return 1
 def GetWindowTextW(self,h,buf,n):buf.value='Zalo';return 4
class Kernel:
 def OpenProcess(self,*a):return 0

def native(layout,regions=None):
 n=object.__new__(V.NativeStudio);n.W=wintypes;n.u=User(layout);n.k=Kernel();n.handle=STUDIO;n.studio_pid=7
 n.p={'accountAnchor':json.dumps(dict(x=300,y=10,width=96,height=28))};n.config={'regions':regions if regions is not None else {'chat':[300,100,200,300],'input':[300,420,200,30]}}
 return n

def covered(n):return [c for x,y in n.points_to_check(600,500) if (c:=n.covering_window(x,y))]

class CoverTests(unittest.TestCase):
 def test_studio_own_panel_is_fine(self):
  self.assertEqual(covered(native(lambda x,y:PANEL if x>=300 else STUDIO)),[])
 def test_other_app_over_unused_corner_is_fine(self):
  self.assertEqual(covered(native(lambda x,y:OTHER if x<100 and y<100 else STUDIO)),[])
 def test_other_app_over_chat_is_reported(self):
  found=covered(native(lambda x,y:OTHER if 300<=x<=500 and 100<=y<=400 else STUDIO))
  self.assertTrue(found);self.assertIn('Zalo',found[0])
 def test_nothing_configured_checks_middle(self):
  self.assertTrue(covered(native(lambda x,y:OTHER,regions={})))

if __name__=='__main__':unittest.main()
