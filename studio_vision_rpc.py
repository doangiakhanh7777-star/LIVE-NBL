"""Process-local OCR service for PowerShell state probes. Read-only actions only.
Binds loopback on an ephemeral port; random secret and short-lived profile leases.
"""
import copy,json,secrets,socketserver,threading,time,uuid

class VisionRPC:
 def __init__(self,executor=None):
  if executor is None:
   from studio_vision import execute_vision
   executor=execute_vision
  self.executor=executor;self.secret=secrets.token_hex(32);self.lock=threading.Lock();self.leases={};owner=self
  class Handler(socketserver.StreamRequestHandler):
   def handle(self):
    self.connection.settimeout(30)
    try:
     raw=self.rfile.readline(4097)
     if len(raw)>4096 or not raw.endswith(b'\n'):raise ValueError('Invalid probe request')
     r=json.loads(raw)
     if not secrets.compare_digest(str(r.get('token','')),owner.secret):raise ValueError('Invalid probe authentication')
     with owner.lock:lease=copy.deepcopy(owner.leases.get(r.get('lease')))
     if not lease or time.time()>=lease['deadline']:raise ValueError('Probe lease expired')
     result=owner.executor(lease['profile'],'status',lease['deadline'],{'fresh_alerts':r.get('fresh') is True})
     response={'ok':True,'result':result}
    except Exception as e:response={'ok':False,'error':str(e)[:700]}
    self.wfile.write(json.dumps(response,ensure_ascii=False).encode('utf-8')+b'\n')
  class Server(socketserver.ThreadingTCPServer):
   daemon_threads=True;allow_reuse_address=False
  self.server=Server(('127.0.0.1',0),Handler)
  self.thread=threading.Thread(target=self.server.serve_forever,daemon=True,name='studio-ocr-probes');self.thread.start()
 def acquire(self,profile,deadline=0):
  until=min(deadline,time.time()+75) if deadline else time.time()+75;key=uuid.uuid4().hex
  with self.lock:
   self.leases={k:v for k,v in self.leases.items() if v['deadline']>time.time()}
   if len(self.leases)>=32:raise RuntimeError('Too many OCR leases')
   self.leases[key]=dict(profile=copy.deepcopy(profile),deadline=until)
  return dict(port=self.server.server_address[1],token=self.secret,lease=key)
 def release(self,key):
  with self.lock:self.leases.pop(key,None)
 def close(self):
  with self.lock:self.leases.clear()
  self.server.shutdown();self.server.server_close()
_instance=None
_lock=threading.Lock()
def service():
 global _instance
 with _lock:
  if _instance is None:_instance=VisionRPC()
  return _instance
def close_service():
 global _instance
 with _lock:instance=_instance;_instance=None
 if instance:instance.close()
