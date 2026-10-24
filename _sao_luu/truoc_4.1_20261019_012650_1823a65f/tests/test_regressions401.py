"""Cases reproduced in the audit; never contacts TikTok or generates desktop input."""
import ast,copy,importlib.util,json,sys,tempfile,time,types,unittest
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
import studio_vision_logic as L
import studio_vision as V
from studio_interactions import StudioInteractions
from video_commands import same_file

def line(text,y=0):return dict(text=text,score=.99,x=10,y=y,w=200,h=16)

class TextTests(unittest.TestCase):
 def test_wrong_price_draft(self):self.assertEqual(L.draft_state([line('San pham gia 900k')],'San pham gia 100k'),'occupied')
 def test_decimal_sign_currency_phone(self):
  for a,b in [('Gia 1.5 trieu','Gia 15 trieu'),('Giam 10%','Giam 10'),('So du -100','So du 100'),('Gia 100$','Gia 100€'),('Goi 0901234567','Goi 0901234568')]:
   with self.subTest(a=a):self.assertFalse(L.exact_message(a,b))
 def test_missing_negative_word(self):self.assertFalse(L.exact_message('Hang KHONG bao hanh','Hang bao hanh'))
 def test_accents_and_wrapping(self):
  self.assertTrue(L.exact_message('Anh chi xem san pham','Anh/chị xem sản phẩm.'))
  self.assertEqual(L.own_message_count([line('Khanh Car Auto 1'),line('San pham gia',20),line('100k nhe',40)],'Khánh Car Auto 1','Sản phẩm giá 100k nhé'),1)
 def test_wrong_author(self):self.assertEqual(L.own_message_count([line('Khanh Car Auto 2'),line('Xa kho hom nay',20)],'Khánh Car Auto 1','Xa kho hom nay'),0)
 def test_author_prefix(self):self.assertEqual(L.own_message_count([line('Nick 12: Xa kho')],'Nick 1','Xa kho'),0)
 def test_inline_author(self):self.assertEqual(L.own_message_count([line('Nick 1: Xa kho')],'Nick 1','Xa kho'),1)
 def test_wrong_price_body(self):self.assertEqual(L.own_message_count([line('Nick 1'),line('Gia 900k',20)],'Nick 1','Gia 100k'),0)
 def test_not_a_placeholder(self):self.assertNotEqual(L.draft_state([line('Them binh luon')]),'empty')

class Pool:
 def submit_priority(self,*a):self.future=Future();self.future.set_running_or_notify_cancel();return self.future
class InteractionsTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.now=[1000.];self.pool=Pool()
  self.p=dict(id='p',name='Nick',pid='1',windowTitle='LIVE Studio',exePath='x',accountAnchor='a',vision=dict(enabled=True,width=400,height=300,regions=dict(input=[0,0,50,20],send=[0,0,50,20],chat=[0,0,50,50],clock=[0,0,50,20]),sendImage='x'))
  self.e=StudioInteractions(self.pool,Path(self.tmp.name)/'journal.json',lambda s:None,clock=lambda:self.now[0])
 def enable(self,text='Tin moi'):self.e.enable(self.p,'message',dict(messages=text,interval=60))
 def old(self):
  self.enable('Tin cu');self.now[0]+=61;self.e.tick([self.p]);f=self.pool.future;self.e.stop('p','message');self.enable();return f
 def test_stale_error(self):
  f=self.old();f.set_exception(ValueError('old'));self.e.tick([self.p]);self.assertTrue(self.e.state('p')['message'])
 def test_stale_success(self):
  f=self.old();f.set_result(dict(sent=True,confirmed=True));self.e.tick([self.p]);self.assertEqual(self.e.state('p')['sent'],0)
 def test_stale_retry(self):
  f=self.old();due=self.e.state('p')['next_message'];f.set_exception(L.NotTouched('old'));self.e.tick([self.p]);self.assertEqual(self.e.state('p')['next_message'],due)
 def test_old_guard_revoked(self):
  self.enable();old=self.e.state('p')['message_guard']['token'];self.enable();self.assertTrue(L.guard_revoked(old))
 def test_deadline(self):
  self.enable();self.p['activeUntil']=999;self.e.tick([self.p]);self.assertFalse(self.e.state('p')['message'])

class VisionTests(unittest.TestCase):
 def setUp(self):V._alert_cache.clear();V._live_cache.clear()
 def test_real_warning_not_retry(self):
  from PIL import Image
  native=types.SimpleNamespace(touched=False,activate=lambda:None,snapshot=lambda:(Image.new('RGB',(400,300),'white'),96))
  p=dict(id='p',pid='1',vision=dict(enabled=True,width=400,height=300,regions=dict(clock=[0,0,80,20])))
  session=V.VisionSession(p,native=native,reader=lambda im:[line('Vi phạm của video LIVE')])
  with patch.object(V,'VisionSession',return_value=session),self.assertRaises(L.StudioAttention):V.execute_vision(p,'status')
 def test_cancel_not_retry(self):
  session=types.SimpleNamespace(native=types.SimpleNamespace(touched=False),key='k')
  with patch.object(V,'VisionSession',return_value=session),patch.object(V,'_run',side_effect=L.InteractionCancelled('stop')),self.assertRaises(L.InteractionCancelled):V.execute_vision({},'send')
 def test_cache_scope(self):
  p=dict(id='p',pid='1',windowHandle=1,accountAnchor='Nick1',vision={'clock':1});key=V.VisionSession(p,native=object()).key
  for delta in [dict(windowHandle=2),dict(accountAnchor='Nick2'),dict(vision={'clock':2})]:self.assertNotEqual(key,V.VisionSession({**p,**delta},native=object()).key)
 def test_fresh_warning(self):
  from PIL import Image
  s=V.VisionSession(dict(id='p',pid='1',vision=dict(regions={})),native=object(),reader=lambda im:[]);im=Image.new('RGB',(400,300),'white');s.scan_alerts(im);s.read=lambda im:[line('Vi phạm của video LIVE')]
  with self.assertRaises(L.StudioAttention):s.scan_alerts(im,fresh=True)
 def test_missing_model_status(self):
  with tempfile.TemporaryDirectory() as d,patch.object(V,'BASE',Path(d)),patch.object(V,'_ocr_status',dict(state='not_loaded',name='vi',error='')):self.assertIn('Thiếu',V.ocr_model_info()[1])
 def test_failed_model_status(self):
  with patch.object(V,'_ocr_status',dict(state='error',name='vi',error='broken ONNX')):self.assertIn('broken ONNX',V.ocr_model_info()[1])


 def test_scheduled_status_always_reads_fresh(self):
  calls=[];session=types.SimpleNamespace(native=types.SimpleNamespace(activate=lambda:None),live=lambda **kw:calls.append(kw) or True)
  V._run(session,{'pid':'1'},'status',None);self.assertEqual(calls,[{'fresh':True,'fresh_alerts':False}])
 def test_summary_image_confirms_offline(self):
  from PIL import Image
  cfg=dict(enabled=True,width=400,height=300,dpi=96,regions=dict(clock=[0,0,80,20]))
  summary=json.dumps(dict(kind='visual',x=0,y=0,width=20,height=20,windowWidth=400,windowHeight=300,dpi=96,image='sample'))
  native=types.SimpleNamespace(snapshot=lambda:(Image.new('RGB',(400,300),'white'),96))
  session=V.VisionSession(dict(id='offline',pid='1',vision=cfg,summaryClose=summary),native=native,reader=lambda im:[],sleep=lambda s:None)
  with patch.object(V,'button_matches',return_value=[(10,10)]):self.assertFalse(session.live(fresh=True))

class BridgeTests(unittest.TestCase):
 def setUp(self):
  spec=importlib.util.spec_from_file_location('bridge401',ROOT/'chrome_bridge.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);self.b=m.ChromeBridge(port=1);self.b.clients['c']=dict(queue=[],ws=None)
 def command(self):return self.b.command('c',dict(action='stop',module='all'))
 def test_queue_not_ack(self):
  t=self.command();self.b.clients['c']['queue']=[];self.assertFalse(self.b.flush(.001));self.assertIn(t,self.b.pending_commands)
 def test_still_running_not_ack(self):
  t=self.command();self.b.accept_acks('c',[dict(id=t,error='')],dict(pin=dict(running=True),reply=dict(running=False)));self.assertIn(t,self.b.pending_commands)
 def test_missing_module_not_ack(self):
  t=self.command();self.b.accept_acks('c',[dict(id=t,error='')],dict(pin=dict(running=False)));self.assertIn(t,self.b.pending_commands)
 def test_wrong_client_not_ack(self):
  t=self.command();self.b.accept_acks('other',[dict(id=t,error='')],dict(pin=dict(running=False),reply=dict(running=False)));self.assertIn(t,self.b.pending_commands)
 def test_error_not_ack(self):
  t=self.command();self.b.accept_acks('c',[dict(id=t,error='bad')],dict(pin=dict(running=False),reply=dict(running=False)));self.assertIn(t,self.b.pending_commands)
 def test_stopped_ack(self):
  t=self.command();self.b.clients['c']['queue']=[];self.b.accept_acks('c',[dict(id=t,error='')],dict(pin=dict(running=False),reply=dict(running=False)));self.assertTrue(self.b.flush(.01))
 def test_no_start_when_closing(self):
  self.b.closing=True
  with self.assertRaises(ValueError):self.b.command('c',dict(action='start',module='pin'))

class ScheduleTests(unittest.TestCase):
 def tick(self,obj):
  tree=ast.parse((ROOT/'studio_panel.py').read_text());cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='StudioPanel');fn=copy.deepcopy(next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='tick'))
  ns=dict(copy=copy,json=json,time=time,Path=Path,NotTouched=L.NotTouched,same_file=same_file,decisions=lambda jobs,now:[]);exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),str(ROOT/'studio_panel.py'),'exec'),ns);ns['tick'](obj)
 def test_actual_tick_accepts_windows_path(self):
  import ntpath,video_commands
  j=dict(id='j',profile='p',state='preparing',prepare_phase='video',end=time.time()+300,video_until=time.time()+15,clips=['C:/Videos/A.mp4']);submitted=[]
  class Status:
   def __truediv__(self,x):return self
   def read_text(self,**kw):return json.dumps(dict(state='PlayingState',time=time.time(),path='c:\\Videos\\A.mp4'))
  owner=types.SimpleNamespace(path=types.SimpleNamespace(parent=Status()),log=lambda s:None)
  obj=types.SimpleNamespace(stopped=False,poll_connection=lambda:None,futures={},jobs=[j],owner=owner,profile=lambda _:dict(session='s'),session=lambda p:dict(id='s'),stop_owned_video=lambda j:None,poll_chrome=lambda:None,save=lambda:None,render=lambda:None,submit=lambda j,a:submitted.append(a))
  with patch.object(video_commands.os,'path',ntpath):self.tick(obj)
  self.assertEqual(submitted,['start'])
 def test_actual_tick_reacts_to_warning_immediately(self):
  j=dict(id='j',profile='p',state='running',end=time.time()+300);f=Future();f.set_exception(L.StudioAttention('Violation'));alerts=[]
  owner=types.SimpleNamespace(log=lambda s:None,notifier=types.SimpleNamespace(publish=lambda *a:alerts.append(a)))
  obj=types.SimpleNamespace(stopped=False,poll_connection=lambda:None,futures={f:('j',None,'status')},jobs=[j],owner=owner,poll_chrome=lambda:None,save=lambda:None,render=lambda:None,status=types.SimpleNamespace(setText=lambda s:None))
  self.tick(obj);self.assertEqual(j['state'],'attention');self.assertEqual(len(alerts),1)

if __name__=='__main__':unittest.main()
