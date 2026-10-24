"""Authenticated local HTTP API for OpenClaw / Telegram control."""
import json, os, queue, secrets, threading, time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from PySide6.QtCore import QTimer

TERMINAL={'finished','cancelled','skipped','failed','manual_stop'}
ACTIVE={'preparing','starting','running','stopping','recovering','attention','start_retry','stop_retry','recovery_review'}

class APIError(Exception):
    def __init__(self,status,message):
        super().__init__(message); self.status=status; self.message=str(message)

def parse_time(value,name):
    if isinstance(value,(int,float)) and not isinstance(value,bool): return float(value)
    if isinstance(value,str) and value.strip():
        raw=value.strip()
        try:return float(raw)
        except ValueError:pass
        try:dt=datetime.fromisoformat(raw.replace('Z','+00:00'))
        except ValueError as e:raise APIError(400,name+' không hợp lệ.') from e
        if dt.tzinfo is None:dt=dt.astimezone()
        return dt.timestamp()
    raise APIError(400,'Thiếu '+name+'.')

class LocalAPI:
    def __init__(self,owner,host=None,port=None):
        self.owner=owner
        self.host=host or os.environ.get('NBL_LOCAL_API_HOST','0.0.0.0')
        self.port=int(port or os.environ.get('NBL_LOCAL_API_PORT','8766'))
        self.calls=queue.Queue(maxsize=100)
        token_path=Path(owner.path).parent/'local_api_token.txt'
        token=''
        if token_path.exists():
            try:token=token_path.read_text(encoding='ascii').strip()
            except OSError:pass
        if len(token)<32:
            token=secrets.token_urlsafe(32)
            token_path.write_text(token,encoding='ascii')
        self.token=token; self.token_path=token_path
        api=self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):return
            def reply(self,status,data):
                body=json.dumps(data,ensure_ascii=False).encode('utf-8')
                self.send_response(status)
                self.send_header('Content-Type','application/json; charset=utf-8')
                self.send_header('Content-Length',str(len(body)))
                self.send_header('Cache-Control','no-store'); self.end_headers()
                self.wfile.write(body)
            def auth(self):
                h=self.headers.get('Authorization','')
                return h.startswith('Bearer ') and secrets.compare_digest(h[7:].strip(),api.token)
            def body(self):
                try:n=int(self.headers.get('Content-Length','0') or 0)
                except ValueError:raise APIError(400,'Content-Length không hợp lệ.')
                if n>65536:raise APIError(413,'Yêu cầu quá lớn.')
                try:v=json.loads((self.rfile.read(n) if n else b'{}').decode('utf-8'))
                except Exception as e:raise APIError(400,'JSON không hợp lệ.') from e
                if not isinstance(v,dict):raise APIError(400,'JSON phải là object.')
                return v
            def call(self,action,payload=None):
                if not self.auth():return self.reply(401,{'ok':False,'error':'Authentication required'})
                item={'action':action,'payload':payload or {},'event':threading.Event(),'status':500,'result':None}
                try:api.calls.put_nowait(item)
                except queue.Full:return self.reply(503,{'ok':False,'error':'API busy'})
                if not item['event'].wait(15):return self.reply(504,{'ok':False,'error':'NBL LIVE did not answer'})
                if item['status']>=400:return self.reply(item['status'],{'ok':False,'error':str(item['result'])})
                return self.reply(item['status'],{'ok':True,'data':item['result']})
            def do_GET(self):
                p=urlparse(self.path).path.rstrip('/') or '/'
                if p=='/health':return self.reply(200,{'ok':True,'app':'NBL LIVE','api':'1.0','port':api.port,'auth':'bearer'})
                if p=='/api/accounts':return self.call('accounts')
                if p=='/api/schedules':return self.call('schedules')
                if p=='/api/live/status':return self.call('status')
                return self.reply(404,{'ok':False,'error':'Not found'})
            def do_POST(self):
                try:
                    p=urlparse(self.path).path.rstrip('/'); data=self.body()
                    if p=='/api/schedules':return self.call('create',data)
                    if p.startswith('/api/schedules/') and p.endswith('/cancel'):
                        return self.call('cancel',{'id':p.split('/')[-2]})
                    if p.startswith('/api/schedules/') and p.endswith('/stop'):
                        return self.call('stop',{'id':p.split('/')[-2]})
                    return self.reply(404,{'ok':False,'error':'Not found'})
                except APIError as e:return self.reply(e.status,{'ok':False,'error':e.message})
            def do_DELETE(self):
                p=urlparse(self.path).path.rstrip('/')
                if p.startswith('/api/schedules/'):return self.call('cancel',{'id':p.split('/')[-1]})
                return self.reply(404,{'ok':False,'error':'Not found'})

        self.server=ThreadingHTTPServer((self.host,self.port),Handler)
        self.server.daemon_threads=True
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True,name='nbl-local-api');self.thread.start()
        self.timer=QTimer(owner);self.timer.setInterval(50);self.timer.timeout.connect(self.drain);self.timer.start()
        owner.log('Local API: http://'+self.host+':'+str(self.port)+' · token: '+str(token_path))

    def drain(self):
        for _ in range(20):
            try:item=self.calls.get_nowait()
            except queue.Empty:return
            try:item['result']=self.dispatch(item['action'],item['payload']);item['status']=200
            except APIError as e:item['status']=e.status;item['result']=e.message
            except Exception as e:item['status']=500;item['result']=str(e)[:800]
            finally:item['event'].set()

    def panel(self):
        p=getattr(self.owner,'studio_panel',None)
        if not p:raise APIError(503,'StudioPanel chưa sẵn sàng.')
        return p

    def account_rows(self):
        panel=self.panel(); rows=[]
        for s in self.owner.data.get('sessions',[]):
            p=next((x for x in panel.profiles if x.get('session')==s.get('id')),None)
            chrome=s.get('chrome_binding',{}) or {}
            rows.append({'number':s.get('number'),'session_id':s.get('id'),
                         'account':(p or {}).get('accountName') or chrome.get('account') or s.get('account') or 'Nick '+str(s.get('number')),
                         'studio_connected':bool(p),'profile_id':(p or {}).get('id'),
                         'playlist_count':len(s.get('playlist',[]))})
        return rows

    def resolve_profile(self,data):
        panel=self.panel()
        pid=data.get('profile_id')
        if pid:
            p=panel.profile(str(pid))
            if p:return p
        number=data.get('account_number')
        if number is not None:
            try:number=int(number)
            except Exception as e:raise APIError(400,'account_number phải là số.') from e
        sid=str(data.get('session_id') or '')
        name=str(data.get('account') or '').strip().casefold()
        found=[]
        for s in self.owner.data.get('sessions',[]):
            p=next((x for x in panel.profiles if x.get('session')==s.get('id')),None)
            names={str(s.get('account') or '').strip().casefold()}
            if p:names|={str(p.get('name') or '').strip().casefold(),str(p.get('accountName') or '').strip().casefold()}
            if (number is not None and s.get('number')==number) or (sid and s.get('id')==sid) or (name and name in names):found.append(p)
        if not found:raise APIError(404,'Không tìm thấy nick/phiên.')
        if len(found)>1:raise APIError(409,'Tên nick khớp nhiều phiên; dùng account_number.')
        if not found[0]:raise APIError(409,'Nick này chưa kết nối LIVE Studio.')
        return found[0]

    def job_json(self,j):
        panel=self.panel(); p=panel.profile(j.get('profile')) if j.get('profile') else None
        s=next((x for x in self.owner.data.get('sessions',[]) if p and x.get('id')==p.get('session')),None)
        return {'id':j.get('id'),'state':j.get('state'),'error':j.get('error',''),
                'start':j.get('start'),'end':j.get('end'),'account_number':(s or {}).get('number'),
                'account':(p or {}).get('accountName') or (s or {}).get('account') or 'Nick '+str((s or {}).get('number')),
                'profile_id':j.get('profile'),'no_sales':bool(j.get('no_sales')),
                'bundle_index':j.get('bundle_index',0),'cart_state':(j.get('cart') or {}).get('state')}

    def find_job(self,jid):
        j=next((x for x in self.panel().jobs if x.get('id')==str(jid)),None)
        if not j:raise APIError(404,'Không tìm thấy lịch.')
        return j

    def dispatch(self,action,data):
        panel=self.panel()
        if action=='accounts':return self.account_rows()
        if action=='schedules':return [self.job_json(j) for j in panel.jobs]
        if action=='status':
            active=[self.job_json(j) for j in panel.jobs if j.get('state') in ACTIVE]
            return {'count':len(active),'active':active}
        if action=='create':
            from studio_panel import vision_missing,video_problem
            from studio_scheduler import add_job,overlapping_other_nicks
            p=self.resolve_profile(data); session=panel.session(p)
            lacking=vision_missing(panel.effective_profile(p))
            if lacking:raise APIError(409,lacking)
            try:video_problem(session)
            except ValueError as e:raise APIError(409,str(e)) from e
            start=parse_time(data.get('start'),'start');end=parse_time(data.get('end'),'end')
            if overlapping_other_nicks(panel.jobs,p['id'],start,end) and not bool(data.get('allow_overlap')):
                raise APIError(409,'Lịch trùng giờ nick khác; dùng allow_overlap=true nếu đã tách âm thanh.')
            no_sales=bool(data.get('no_sales',False))
            try:bundle=int(data.get('bundle_index',1))
            except Exception as e:raise APIError(400,'bundle_index phải là số.') from e
            try:j=add_job(panel.jobs,p['id'],start,end,(),'',no_sales,False,bundle)
            except ValueError as e:raise APIError(409,str(e)) from e
            panel.save();panel.render();return self.job_json(j)
        if action=='cancel':
            j=self.find_job(data.get('id'));state=j.get('state')
            if state in TERMINAL:return self.job_json(j)
            if state in ACTIVE and state!='start_retry':raise APIError(409,'Lịch đang hoạt động; dùng /stop.')
            panel.cancel_pending_starts(j);panel.stop_chrome(j)
            j['state']='cancelled';j['retry_at']=0;j['error']='Đã hủy qua Local API'
            panel.save();panel.render();return self.job_json(j)
        if action=='stop':
            j=self.find_job(data.get('id'));state=j.get('state')
            if state in TERMINAL:return self.job_json(j)
            panel.cancel_pending_starts(j);panel.stop_chrome(j)
            if state in ('pending','start_retry'):
                j['state']='cancelled';j['error']='Đã hủy trước giờ phát qua Local API'
            else:
                j['state']='stopping'
                try:panel.submit(j,'stop')
                except Exception as e:j['state']='attention';j['error']=str(e)[:500];raise APIError(409,str(e)) from e
            panel.save();panel.render();return self.job_json(j)
        raise APIError(404,'Action not found')

    def close(self):
        try:self.timer.stop()
        except Exception:pass
        try:self.server.shutdown();self.server.server_close()
        except Exception:pass
