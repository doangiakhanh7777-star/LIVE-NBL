"""Authenticated loopback bridge. The GUI thread never waits for Chrome I/O.

4.0.2: command-ID acknowledgements plus stopped module state, bounded shutdown
outside the GUI, connection epochs and fallback ports 17869-17871.
"""
import copy
import hashlib
import json
import queue
import re
import secrets
import threading
import time
import uuid
from pathlib import Path
from websockets.sync.server import serve
from model import write_json

PROTOCOL=402
PORTS=(17869,17870,17871)

class ChromeBridge:
    def __init__(self, port=None, token_path=None):
        self.config_path=Path(token_path).parent/"chrome_accounts.json" if token_path else None
        self.ports=(port,) if port is not None else PORTS;self.port=self.ports[0];self.token=secrets.token_hex(16)
        if token_path:
            path=Path(token_path);path.parent.mkdir(parents=True,exist_ok=True)
            if path.exists():
                token=path.read_text(encoding='ascii').strip()
                if len(token)!=32 or any(c not in '0123456789abcdef' for c in token):raise ValueError('Mã ghép đôi hỏng; đổi tên pairing_token.txt rồi mở lại.')
                self.token=token
            else:
                path.write_text(self.token,encoding='ascii')
                try:path.chmod(0o600)
                except OSError:pass
        self.lock=threading.RLock()
        self.clients={};self.events=queue.Queue(maxsize=200);self.server=None;self.thread=None;self.closed=False;self.shutdown_thread=None
        self.pending_commands={};self.closing=False;self._flush_unconfirmed=False
        self.connection_epoch=uuid.uuid4().hex
    def log(self,message):
        try:self.events.put_nowait(message)
        except queue.Full:pass
    def start(self):
        ready=threading.Event()
        def run():
            error=None
            for port in self.ports:
                try:
                    self.server=serve(self.handle,'127.0.0.1',port,max_size=512_000,open_timeout=5,close_timeout=2,ping_interval=20,ping_timeout=20)
                    break
                except OSError as e:error=e
            if self.server is None:
                self.log('Kết nối Chrome không mở được (cổng '+'/'.join(map(str,self.ports))+' đều bận): '+str(error));ready.set();return
            self.port=self.server.socket.getsockname()[1]
            if self.port!=self.ports[0]:self.log('Cổng '+str(self.ports[0])+' đang bận; dùng cổng '+str(self.port)+'. Tiện ích 4.1 tự dò cổng này.')
            ready.set()
            try:self.server.serve_forever()
            except Exception as e:self.log('Kết nối Chrome dừng: '+str(e))
        self.thread=threading.Thread(target=run,daemon=True);self.thread.start();ready.wait(3)
    def handle(self,ws):
        client=None
        try:
            origin=ws.request.headers.get('Origin','')
            if not origin.startswith('chrome-extension://'):ws.close(1008,'Extension origin required');return
            hello=json.loads(ws.recv(timeout=5))
            if not isinstance(hello,dict) or not secrets.compare_digest(str(hello.get('token','')),self.token):ws.close(1008,'Pairing required');return
            if hello.get('protocol')!=PROTOCOL:self.log('Cập nhật tiện ích NBL 4.1 (Tải lại trong chrome://extensions) rồi tải lại trang LIVE.');ws.close(1008,'NBL 4.0.2 extension required');return
            if self.closing:ws.close(1001,'App closing');return
        except Exception as e:
            if not self.closed:self.log('Tab Chrome ngắt kết nối: '+str(e)[:200])
            return
        self.serve(ws,hello)
    def serve(self,ws,hello,label='Chrome'):
        """One connected page: tick → reply loop. ws: the extension socket, or (4.3.5) a
        live_chrome.PageLink that answers through NBL's own Chrome (same send / recv / close)."""
        client=None
        try:
            client=getattr(ws,'client_id','') or uuid.uuid4().hex
            with self.lock:
                if len(self.clients)>=16:ws.close(1008,'Too many clients');return
                instance=hello.get('instance','')
                if not isinstance(instance,str) or (instance and not re.fullmatch('[a-f0-9]{32}',instance)):
                    ws.close(1008,'Invalid browser instance');return
                self.clients[client]=dict(ws=ws,tab=hello.get('tab'),instance=instance,account='Đang đọc trang',configAck='',modules={},queue=[],last=time.monotonic())
            self.log(label+' đã ghép đôi · tab '+str(hello.get('tab')))
            while not self.closed:
                with self.lock:
                    state=self.clients.get(client)
                    if not state:break
                    now=time.monotonic();commands=state['queue'];state['queue']=[]
                commands=[c for c in commands if c['expires']>now]
                ws.send(json.dumps(dict(type='tick',commands=commands,time=time.time(),configAck=state.get('configAck',''),connectionId=self.connection_epoch+':'+client,closing=self.closing),ensure_ascii=False))
                reply=json.loads(ws.recv(timeout=8))
                if not isinstance(reply,dict):raise ValueError('Invalid response')
                with self.lock:
                    state['account']=str(reply.get('account','Chưa chọn tài khoản'))[:200]
                    state['accountVerified']=reply.get('accountVerified') is True and bool(state['account'])
                    modules=reply.get('modules',{})
                    state['modules']={k:dict(running=bool(v.get('running')),error=str(v.get('error',''))[:500],detail=str(v.get('detail',''))[:500]) for k,v in modules.items() if k in ('pin','reply') and isinstance(v,dict)} if isinstance(modules,dict) else {};state['last']=time.monotonic()
                    if isinstance(reply.get('cartTitles'),list):state['cartTitles']=[str(x)[:200] for x in reply['cartTitles'][:300]]   # 4.1.11: check pin scripts
                    state['captcha']=str(reply.get('captcha') or '')[:200]   # 4.1.16: Telegram x5
                    state['version']=str(reply.get('version') or '')[:20]     # 4.3.0: extension version (self-reload after update)
                    asks=reply.get('aiAsk')                                  # 4.2.2: comments for the AI (Gemini)
                    if isinstance(asks,list):
                        queue=state.setdefault('aiQueue',[])
                        for a in asks[:10]:
                            if isinstance(a,dict) and str(a.get('text','')).strip() and len(queue)<30:queue.append(dict(id=str(a.get('id',''))[:40],user=str(a.get('user',''))[:80],text=str(a.get('text',''))[:300],at=time.time()))
                    fr=reply.get('findResult')
                    if isinstance(fr,dict):state['findResult']={k:str(v)[:400] for k,v in fr.items() if k in ('id','state','text')}   # 4.1.13: Tìm thử
                    control=reply.get('control',{});state['control']={k:str(v)[:500] for k,v in control.items() if k in ('id','state','error','bundle','added','total','skipped','count','index','busy')} if isinstance(control,dict) else {}
                config=reply.get('config');account=state['account']
                if self.config_path and state.get('accountVerified') and isinstance(config,dict) and config and account not in ('Chưa chọn tài khoản','Chưa đăng nhập','Chưa hiệu chỉnh','Không đọc được trang','Đang đọc trang'):
                    config={k:v for k,v in config.items() if isinstance(k,str) and isinstance(v,str) and len(k)<60 and len(v)<100000}
                    body=json.dumps(config,ensure_ascii=False,sort_keys=True);digest=hashlib.sha256(body.encode()).hexdigest()
                    if len(body)<200000 and digest!=state.get('configAck'):
                        with self.lock:
                            try:accounts=json.loads(self.config_path.read_text(encoding='utf-8')) if self.config_path.exists() else {}
                            except (OSError,ValueError):accounts={}
                            accounts[state['instance']+':'+account]=dict(account=account,instance=state['instance'],config=config,revision=digest,updated=time.time())
                            write_json(self.config_path,accounts);state['configAck']=digest;state['config']=config
                        self.log('Đã tự lưu Chrome theo nick: '+account)
                self.save_reports(reply.get('reports'),account)
                acks=reply.get('acks',[])
                self.accept_acks(client,acks,reply.get('modules',{}))
                for ack in (acks[:20] if isinstance(acks,list) else []):
                    if isinstance(ack,dict) and ack.get('error'):self.log('Chrome: '+str(ack['error'])[:300])
                # Socket activity drives content work even when its tab's timers are throttled.
                for _ in range(10):
                    if self.closed:break
                    time.sleep(.1)
        except Exception as e:
            if not self.closed:self.log('Tab Chrome ngắt kết nối: '+str(e)[:200])
        finally:
            if client:
                self.drop_client(client)
    def save_reports(self,items,account):
        """4.0.3: activity / errors from the Chrome tab go to NBL's report folders."""
        if not isinstance(items,list):return
        for item in items[:20]:
            if not isinstance(item,dict) or item.get('kind') not in ('hoat_dong','loi'):continue
            title=str(item.get('title',''))[:200];detail=str(item.get('detail',''))[:500]
            if not title:continue
            try:
                import nbl_reports
                nbl_reports.add(item['kind'],str(account or 'Chrome')[:100],title,detail)
            except Exception:pass
            if item['kind']=='hoat_dong' and title.endswith('Tự đóng thông báo'):self.log('Chrome · đã tự đóng thông báo: '+detail[:200])
    def drop_client(self,client):
        with self.lock:
            self.clients.pop(client,None)
            lost=[k for k,v in self.pending_commands.items() if v['client']==client]
            for key in lost:
                command=self.pending_commands.pop(key)
                if command['action']=='stop':self._flush_unconfirmed=True
            if lost:self.log('Tab đã ngắt; đã bỏ '+str(len(lost))+' lệnh chưa xác nhận. Không ghi thành công giả.')
    def prune_commands(self):
        now=time.monotonic()
        for key,command in list(self.pending_commands.items()):
            if command.get('expires',now+1)<=now:
                self.pending_commands.pop(key,None)
                if command['action']=='stop':self._flush_unconfirmed=True
    def snapshot(self):
        with self.lock:
            return {k:{a:copy.deepcopy(v) for a,v in s.items() if a in ('tab','instance','account','accountVerified','modules','control','config','configAck','ackErrors','cartTitles','findResult','captcha','version')} for k,s in self.clients.items() if time.monotonic()-s['last']<10}
    def command(self,client,payload):
        if payload.get('action') not in ('start','stop','prepare_bundle','finish_live','cart_check','reload_page','clip_sync','find_product','reload_extension'):raise ValueError('Lệnh không hợp lệ.')
        if payload.get('module') not in ('pin','reply','all'):raise ValueError('Mục không hợp lệ.')
        with self.lock:
            if self.closing and payload.get('action')!='stop':raise ValueError('App đang đóng; không nhận lệnh chạy mới.')
            if client not in self.clients:raise ValueError('Tab đã mất kết nối.')
            self.prune_commands()
            state=self.clients[client]
            if payload.get('action')=='stop':
                # A newer stop supersedes older stops for the same target; its
                # own ID still requires acknowledgement before shutdown succeeds.
                for key,old in list(self.pending_commands.items()):
                    if old['client']==client and old['action']=='stop' and (payload['module']=='all' or old['module']==payload['module']):self.pending_commands.pop(key,None)
                state['queue']=[c for c in state['queue'] if not (c.get('action') in ('start','prepare_bundle','stop') and (payload.get('module')=='all' or c.get('module')==payload.get('module')))]
            if len(state['queue'])>=20:raise ValueError('Hàng đợi đầy.')
            ttl=150 if payload.get('action')=='prepare_bundle' else 70 if payload.get('action')=='finish_live' else 10  # 4.1: adding 100 products takes a while
            command={**payload,'id':uuid.uuid4().hex,'expires':time.monotonic()+ttl,'deadline':time.time()+ttl}
            state['queue'].append(command)
            self.pending_commands[command['id']]=dict(client=client,action=payload['action'],module=payload['module'],expires=command['expires'])
            # Keep bounded command bookkeeping; stopping commands are never evicted.
            for old in list(self.pending_commands):
                if len(self.pending_commands)<=500:break
                if self.pending_commands[old]['action']!='stop':self.pending_commands.pop(old,None)
            return command['id']
    def accept_acks(self,client,acks,modules):
        with self.lock:
            for ack in acks[:20] if isinstance(acks,list) else []:
                if not isinstance(ack,dict):continue
                command=self.pending_commands.get(ack.get('id'))
                if command and command['client']==client and ack.get('error') and command.get('module') in ('pin','reply') and client in self.clients:
                    # 4.1.3: why a module did not start (shown in the Telegram notice).
                    self.clients[client].setdefault('ackErrors',{})[command['module']]=str(ack['error'])[:300]
                if not command or command['client']!=client or ack.get('error'):continue
                if command['action']=='stop':
                    targets=('pin','reply') if command['module']=='all' else (command['module'],)
                    if not isinstance(modules,dict) or any(not isinstance(modules.get(k),dict) or modules[k].get('running') is not False for k in targets):continue
                self.pending_commands.pop(ack['id'],None)
    def stop_all(self):
        with self.lock:
            self.pending_commands.clear();self._flush_unconfirmed=False
            for client,state in self.clients.items():
                state['queue']=[]
                self.command(client,dict(action='stop',module='all'))
    def drain(self):
        result=[]
        while True:
            try:result.append(self.events.get_nowait())
            except queue.Empty:return result
    def flush(self,timeout=2.5):
        """Wait for command acknowledgements; a drained outbound queue is not delivery."""
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            with self.lock:
                self.prune_commands()
                pending=list(self.pending_commands)
            if not pending:return not self._flush_unconfirmed
            time.sleep(.05)
        return False
    def close(self,wait=False):
        # Non-daemon shutdown keeps Python alive for the bounded acknowledgement
        # window after Qt closes, without freezing the GUI thread during that wait.
        with self.lock:
            if self.shutdown_thread is None:
                self.closing=True
                self.stop_all()
                def shutdown():
                    if not self.flush():
                        self.log('Chưa xác nhận mọi tab đã dừng. Khi nối lại, tiện ích yêu cầu bật lại; không tự chạy tiếp.')
                    self.closed=True
                    with self.lock:clients=list(self.clients.values())
                    if self.server:self.server.shutdown()
                    for state in clients:
                        try:state['ws'].close()
                        except Exception:pass
                self.shutdown_thread=threading.Thread(target=shutdown,daemon=False,name='chrome-stop-ack')
                self.shutdown_thread.start()
        if wait:self.shutdown_thread.join()
