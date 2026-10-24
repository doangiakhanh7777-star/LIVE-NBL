"""Regression coverage for the 19-item audit. Real native checks remain separate."""
import ast,copy,hashlib,importlib.util,io,json,os,queue,socket,subprocess,sys,tempfile,time,types,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT))
import studio_vision_logic as L
import studio_vision as V
from chrome_bridge import ChromeBridge

def line(t,score=.99):return dict(text=t,score=score,x=0,y=0,w=80,h=15)
class EncodingAlarmTests(unittest.TestCase):
 def test_actual_checker_under_cp1258_and_cp1252_default(self):
  import kiem_tra_cai_dat as check
  original=Path.read_text
  for encoding in ('cp1258','cp1252'):
   def read(path,*a,**kw):
    if not a and not kw.get('encoding'):kw['encoding']=encoding
    return original(path,*a,**kw)
   with self.subTest(encoding=encoding),patch.object(Path,'read_text',read),patch('sys.stdout',io.StringIO()):check.check()
 def test_runtime_text_reads_specify_encoding(self):
  bad=[]
  for p in ROOT.rglob('*.py'):
   if 'tests' in p.parts:continue
   for n in ast.walk(ast.parse(p.read_text(encoding='utf-8-sig'))):
    if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='read_text' and not n.args and not any(k.arg=='encoding' for k in n.keywords):bad.append((p.name,n.lineno))
  self.assertEqual(bad,[])
 def test_alarm_runs_actual_file(self):
  from NBL_CANH_BAO.alarm import Alarm
  owner=types.SimpleNamespace(results=queue.Queue());calls=[]
  def run(command,**kw):calls.append(command);return types.SimpleNamespace(returncode=0,stdout='{"warning":true,"windows":1,"warnings":[]}')
  with patch('NBL_CANH_BAO.alarm.subprocess.run',run):Alarm.scan(owner,7)
  cmd=calls[0];self.assertIn('-File',cmd);self.assertNotIn('-Command',cmd);self.assertTrue(Path(cmd[cmd.index('-File')+1]).is_file());self.assertEqual(owner.results.get()['_generation'],7)

class MatcherTests(unittest.TestCase):
 def test_currency_glyph_missing_or_dong_alias(self):
  for a,b in [('Giá 100.000₫ hôm nay','Gia 100.000d hom nay'),('Giá 100€ hôm nay','Gia 100 hom nay'),('Giá 100£','Gia 100'),('Giá 100¥','Gia 100')]:
   with self.subTest(a=a):self.assertTrue(L.exact_message(a,b))
 def test_common_ocr_rn_m(self):self.assertEqual(L.draft_state([line('Xern gio hang nhe')],'Xem giỏ hàng nhé'),'expected')
 def test_numeric_confusion_is_not_guessed(self):self.assertFalse(L.exact_message('Mua 1 tang 1','Mua l tang 1'))
 def test_no_price_phone_or_negative_regression(self):
  for a,b in [('Gia 100k','Gia 900k'),('Mua 1 tang 1','Mua 2 tang 1'),('Goi 0901234567','Goi 0901234568'),('KHONG bao hanh','CO bao hanh'),('Giam 10%','Giam 10')]:self.assertFalse(L.exact_message(a,b))
 def test_emoji_author(self):self.assertTrue(L.same_author('🚗 Khánh Car Auto 1 ✨','KHANH CAR AUTO 1'))
 def test_decorated_other_author_not_equal(self):self.assertFalse(L.same_author('🚗 Khánh Car Auto 2','Khánh Car Auto 1'))
 def test_decorated_inline_author(self):self.assertEqual(L.own_message_count([line('🚗 Khánh Car Auto 1: Xem giỏ hàng nhé')],'Khanh Car Auto 1','Xem gio hang nhe'),1)

class VisionAuditTests(unittest.TestCase):
 def test_queue_timeout_before_input_retries(self):
  native=V.NativeStudio.__new__(V.NativeStudio);native.deadline=time.time()-1;native.touched=False;native.p={};native.handle=1;native.u=types.SimpleNamespace(IsIconic=lambda h:False,GetForegroundWindow=lambda:1)
  with self.assertRaises(L.CommandExpired):native.guard()
 def test_timeout_after_input_stays_uncertain(self):
  native=V.NativeStudio.__new__(V.NativeStudio);native.deadline=time.time()-1;native.touched=True;native.p={};native.handle=1;native.u=types.SimpleNamespace(IsIconic=lambda h:False,GetForegroundWindow=lambda:1)
  with self.assertRaises(TimeoutError):native.guard()
 def test_expired_cancelled_guard_stays_user_cancel(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'guard';p.write_text('0',encoding='utf-8');native=V.NativeStudio.__new__(V.NativeStudio);native.deadline=time.time()-1;native.touched=False;native.p={'_interactionGuard':{'path':str(p),'token':'old'}}
   with self.assertRaises(L.InteractionCancelled):native.guard()
 def fixture(self,unknown=False,changed=False):
  from PIL import Image
  counts=dict(input=0,snapshot=0,click=0,clear=0)
  p=dict(id='p',pid='1',name='Nick',vision=dict(enabled=True,width=400,height=300,dpi=96,regions=dict(clock=[0,0,80,20],input=[0,100,100,20],send=[110,100,30,20],chat=[0,150,200,100]),sendImage='sample'))
  def snapshot():
   counts['snapshot']+=1;im=Image.new('RGB',(400,300),'white')
   if changed and counts['snapshot']>=4:im.putpixel((5,105),(0,0,0))
   return im,96
  def click(*a):counts['click']+=1;native.touched=True
  def clear():counts['clear']+=1
  native=types.SimpleNamespace(touched=False,snapshot=snapshot,click=click,type_text=lambda t:None,clear_text=clear)
  def reader(im):
   if im.size!=(100,20):return []
   counts['input']+=1
   if unknown:return [line('Thêm bình luận...',.6)]
   return [line('Thêm bình luận...')] if counts['input']<3 or counts['clear'] else [line('Totally different words')]
  session=V.VisionSession(p,native=native,reader=reader,sleep=lambda s:None);session.live=lambda **kw:True
  return session,counts
 def test_unknown_empty_input_is_retryable_before_click(self):
  session,counts=self.fixture(unknown=True)
  with self.assertRaises(L.NotTouched):session.send('Xem giỏ hàng nhé')
  self.assertEqual(counts['click'],0)
 def test_owned_failed_draft_is_cleared_without_send(self):
  session,counts=self.fixture()
  with self.assertRaises(L.NotSentCleaned):session.send('Xem giỏ hàng nhé')
  self.assertEqual(counts['clear'],1);self.assertEqual(counts['click'],1)
 def test_changed_draft_is_never_erased(self):
  session,counts=self.fixture(changed=True)
  with self.assertRaises(ValueError):session.send('Xem giỏ hàng nhé')
  self.assertEqual(counts['clear'],0)
 def test_periodic_status_reuses_warning_ocr(self):
  from PIL import Image
  cfg=dict(enabled=True,width=400,height=300,dpi=96,regions=dict(clock=[0,0,80,20]));p=dict(id='probe',pid='1',vision=cfg);n=[0,0]
  def read(im):
   if im.size==(400,300):n[0]+=1;return []
   n[1]+=1;return [line('00:10:'+str(n[1]).zfill(2))]
  V._alert_cache.clear();V._live_cache.clear();native=types.SimpleNamespace(activate=lambda:None,snapshot=lambda:(Image.new('RGB',(400,300),'white'),96))
  s=V.VisionSession(p,native=native,reader=read,sleep=lambda s:None,clock=lambda:1000)
  for i in range(3):V._run(s,p,'status',{})
  self.assertEqual(n[0],1);s.live(fresh=True,fresh_alerts=True);self.assertEqual(n[0],2)
 def test_focus_change_before_backspace_does_not_erase_other_field(self):
  import ctypes
  events=[];native=V.NativeStudio.__new__(V.NativeStudio);native.guard=lambda *a:None;native._input_focus=1
  focus=iter([1,2]);native.focus_handle=lambda:next(focus);native.W=types.SimpleNamespace(DWORD=ctypes.c_uint32)
  native.u=types.SimpleNamespace(keybd_event=lambda key,*a:events.append(key))
  with self.assertRaises(ValueError):native.clear_text()
  self.assertNotIn(0x08,events)
 def test_fixed_recognizer_width_uses_batch_maximum(self):
  calls=[];e=types.SimpleNamespace(text_rec=types.SimpleNamespace(resize_norm_img=lambda img,ratio:calls.append(round(ratio*48))))
  V.configure_fixed_width(e);e.text_rec.resize_norm_img(None,2);e.text_rec.resize_norm_img(None,20);self.assertEqual(calls,[320,640])
 def test_failed_model_load_has_backoff(self):
  import rapidocr_onnxruntime
  with patch.object(V,'_ocr',None),patch.object(V,'_ocr_retry_at',0),patch.object(V,'_ocr_signature',None),patch.object(V,'_ocr_status',dict(state='not_loaded',name='vi',error='')),patch.object(rapidocr_onnxruntime,'RapidOCR',side_effect=RuntimeError('broken')) as ctor:
   for i in range(2):
    with self.assertRaises(L.StudioAttention):V._engine()
   self.assertEqual(ctor.call_count,1)

class RecoveryBridgeTests(unittest.TestCase):
 def test_studio_backup_and_recovery(self):
  import studio_store,model
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'studio_schedules.json';v=dict(profiles=[dict(id='p',name='Nick',pid='1',session='s')],jobs=[])
   model.write_json(p,v);model.write_json(p,v);p.write_text('{broken',encoding='utf-8');loaded,note=studio_store.load(p)
   self.assertEqual(loaded['profiles'][0]['id'],'p');self.assertTrue(note);self.assertTrue(list(Path(d).glob('*.broken-*')))
 def test_studio_salvage_keeps_valid_profile(self):
  import studio_store
  v=studio_store.salvage(dict(profiles=[dict(id='p',name='Nick',pid='1',session='s'),{}],jobs=[{}]));self.assertEqual(len(v['profiles']),1);self.assertEqual(v['jobs'],[])
 def test_lost_tab_does_not_leave_pending_commands(self):
  b=ChromeBridge(port=1);b.clients['c']=dict(queue=[],ws=None);b.command('c',dict(action='stop',module='all'));b.drop_client('c');start=time.monotonic();self.assertFalse(b.flush(.5));self.assertLess(time.monotonic()-start,.1);self.assertEqual(b.pending_commands,{})
 def test_repeated_stop_bookkeeping_is_bounded(self):
  b=ChromeBridge(port=1);b.clients['c']=dict(queue=[],ws=None)
  for i in range(600):b.command('c',dict(action='stop',module='all'));b.clients['c']['queue']=[]
  self.assertEqual(len(b.pending_commands),1)
 def test_stale_attempt_preserves_uncertainty(self):
  from test_regressions401 import InteractionsTests
  case=InteractionsTests();case.setUp()
  try:
   f=case.old();f.set_exception(ValueError('May have sent'));case.e.tick([case.p]);self.assertEqual(case.e.attempts[-1]['state'],'uncertain')
  finally:case.doCleanups()

if __name__=='__main__':unittest.main()
