import ast,copy,json,os,queue,socket,subprocess,sys,tempfile,time,types,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT))
from studio_vision_rpc import VisionRPC
PWSH=os.environ.get('NBL_PWSH')

class RPCTests(unittest.TestCase):
 def setUp(self):
  self.calls=[];self.rpc=VisionRPC(lambda p,a,d,payload:self.calls.append((p,a,payload)) or dict(live=True,confirmed=True))
  self.addCleanup(self.rpc.close);self.lease=self.rpc.acquire(dict(id='p',name='Nick'))
 def request(self,data):
  with socket.create_connection(('127.0.0.1',self.lease['port']),timeout=3) as s:
   s.sendall(json.dumps(data).encode()+b'\n');return json.loads(s.makefile('rb').readline())
 def test_shared_executor_across_requests(self):
  for i in range(3):self.assertTrue(self.request({**self.lease,'fresh':False})['ok'])
  self.assertEqual(len(self.calls),3)
 def test_wrong_auth_rejected(self):self.assertFalse(self.request({**self.lease,'token':'wrong'})['ok']);self.assertEqual(self.calls,[])
 def test_revoked_profile_cannot_probe(self):
  self.rpc.release(self.lease['lease']);self.assertFalse(self.request(self.lease)['ok'])
 @unittest.skipUnless(PWSH,'PowerShell needed for real client test')
 def test_actual_powershell_client_uses_same_service(self):
  with tempfile.TemporaryDirectory() as d:
   script=Path(d)/'client.ps1';script.write_text(". $args[0]\n$lease=$args[1]|ConvertFrom-Json\nInvoke-NblVisionProbe $lease $true|ConvertTo-Json -Compress\n",encoding='utf-8-sig')
   for i in range(2):
    result=subprocess.run([PWSH,'-NoLogo','-NoProfile','-File',str(script),str(ROOT/'studio_vision_client.ps1'),json.dumps(self.lease)],capture_output=True,text=True,encoding='utf-8',timeout=10)
    self.assertEqual(result.returncode,0,result.stderr);self.assertTrue(json.loads(result.stdout)['confirmed'])
   self.assertEqual(len(self.calls),2);self.assertTrue(all(c[2]['fresh_alerts'] for c in self.calls))

class CloseTests(unittest.TestCase):
 def run_close(self,attempted=False,answer=False,stop_error=False):
  tree=ast.parse((ROOT/'app.py').read_text(encoding='utf-8'));cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Console');fn=copy.deepcopy(next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='closeEvent'))
  calls=[];button=types.SimpleNamespace(Yes=1,No=2)
  msg=types.SimpleNamespace(StandardButton=button,question=lambda *a:calls.append('question') or (1 if answer else 2))
  parent=types.SimpleNamespace(closeEvent=lambda e:calls.append('accepted'))
  ns=dict(QMessageBox=msg,QTimer=types.SimpleNamespace(singleShot=lambda *a:None),time=time,write_json=lambda *a:None,set_awake=lambda *a:None,super=lambda:parent)
  exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),str(ROOT/'app.py'),'exec'),ns)
  noop=lambda *a:None
  panel=types.SimpleNamespace(active=lambda:True,jobs=[dict(id='j',profile='p',state='attention' if attempted else 'running')],stop_all=lambda:calls.append('try_stop'),cancel_pending_starts=noop,stop_chrome=noop,shutdown=noop)
  if stop_error:
   def fail_stop():raise RuntimeError('Queue closed')
   panel.stop_all=fail_stop
  obj=types.SimpleNamespace(studio_panel=panel,_closing_live=attempted,_close_requested_at=time.monotonic()-2,_poll_requested_close=noop,log=noop,timer=types.SimpleNamespace(stop=noop),collect=noop,path='unused',data=dict(sessions=[]),cancel_cycle=noop,alarm_window=None,shop_login=types.SimpleNamespace(shutdown=noop),studio_chat=types.SimpleNamespace(shutdown=noop),notifier=types.SimpleNamespace(close=noop),bridge=types.SimpleNamespace(close=noop),obs=types.SimpleNamespace(close=noop),logger=types.SimpleNamespace(handlers=[]))
  event=types.SimpleNamespace(ignore=lambda:calls.append('ignored'));ns['closeEvent'](obj,event)
  return obj,calls
 def test_stop_submission_failure_does_not_trap_close(self):
  obj,calls=self.run_close(stop_error=True);self.assertTrue(obj._close_stop_failed);self.assertIn('ignored',calls)
 def test_first_close_tries_stop_once(self):
  obj,calls=self.run_close();self.assertIn('try_stop',calls);self.assertIn('ignored',calls);self.assertNotIn('question',calls)
 def test_failed_stop_can_keep_app_open(self):
  obj,calls=self.run_close(attempted=True,answer=False);self.assertIn('question',calls);self.assertIn('ignored',calls);self.assertNotIn('accepted',calls)
 def test_failed_stop_can_close_with_warning(self):
  obj,calls=self.run_close(attempted=True,answer=True);self.assertIn('accepted',calls);self.assertEqual(obj.studio_panel.jobs[0]['state'],'recovery_review')

@unittest.skipUnless(PWSH,'PowerShell required')
class WarningFilterTests(unittest.TestCase):
 def test_actual_regex_matches_prefixed_warning_labels(self):
  cases=[['Thông báo: Vi phạm của video LIVE',True],['Cảnh báo — Phiên LIVE đã bị hạn chế hiển thị',True],['Yêu cầu xác minh bảo mật',True],['Please complete security verification',True],['LIVE violation notice',True],['Không hoạt động trong phiên LIVE',True],['Sản phẩm giá rẻ',False],['Phiên LIVE đang chạy bình thường',False]]
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'test.ps1';p.write_text(". $args[0]\n$cases=$args[1]|ConvertFrom-Json\n$results=@($cases|ForEach-Object {Test-NblWarningText $_[0]})\nConvertTo-Json -InputObject $results -Compress",encoding='utf-8-sig')
   r=subprocess.run([PWSH,'-NoLogo','-NoProfile','-File',str(p),str(ROOT/'warning_filter.ps1'),json.dumps(cases,ensure_ascii=False)],capture_output=True,text=True,encoding='utf-8',timeout=10)
   self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(json.loads(r.stdout),[x[1] for x in cases])

if __name__=='__main__':unittest.main()
