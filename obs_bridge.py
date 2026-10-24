"""Single worker serializes OBS requests so the GUI never blocks on network."""
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
import threading
import time


class OBSBridge:
    def __init__(self):
        self.worker=ThreadPoolExecutor(max_workers=1)
        self.results=Queue(); self.client=None; self.connected=False; self.busy=0
        self.lock=threading.RLock();self.generation=0;self.closed=False;self.pending={}

    def submit(self,action,host='127.0.0.1',port=4455,password='',scene=''):
        starters=('start','record_start','camera_start','scene')
        with self.lock:
            if self.closed:return False
            if action in ('stop','emergency'):
                self.generation+=1
                for future,pending_action in list(self.pending.items()):
                    if pending_action in starters or (action=='emergency' and pending_action not in ('stop','emergency')):
                        future.cancel()
                if action in self.pending.values():return True
            if self.busy>=4 and action not in ('stop','emergency'):return False
            generation=self.generation;self.busy+=1
        def check_current():
            if action in starters:
                with self.lock:
                    if generation!=self.generation or self.closed:raise InterruptedError('OBS action cancelled')
        def work():
            try:
                check_current()
                if action=='connect':
                    import obsws_python
                    if self.client:
                        try:self.client.disconnect()
                        except Exception:pass
                    self.client=obsws_python.ReqClient(host=host,port=int(port),password=password,timeout=3)
                    data=self.client.send('GetVersion',raw=True)
                    self.connected=True
                elif self.client is None:
                    raise RuntimeError('Chưa kết nối OBS.')
                elif action=='emergency':
                    data={'failed':[]}
                    for request,status_request in (('StopStream','GetStreamStatus'),('StopRecord','GetRecordStatus'),('StopVirtualCam','GetVirtualCamStatus')):
                        try:self.client.send(request,raw=True)
                        except Exception:pass  # OBS may reject a stop when that output is already inactive.
                        try:
                            active=bool(self.client.send(status_request,raw=True).get('outputActive'))
                            if active:data['failed'].append(request+': vẫn hoạt động')
                            if request=='StopStream':data['outputActive']=active
                        except Exception as exc:data['failed'].append(request+': '+type(exc).__name__)
                elif action=='status':
                    data=self.client.send('GetStreamStatus',raw=True)
                    data['scenes']=self.client.send('GetSceneList',raw=True)
                elif action=='scene':
                    check_current()
                    data=self.client.send('SetCurrentProgramScene',{'sceneName':scene},raw=True)
                elif action in ('start','stop'):
                    target=action=='start'
                    status=self.client.send('GetStreamStatus',raw=True)
                    check_current()
                    if bool(status.get('outputActive'))!=target:self.client.send('StartStream' if target else 'StopStream',raw=True)
                    end=time.monotonic()+8
                    while True:
                        check_current()
                        data=self.client.send('GetStreamStatus',raw=True)
                        if bool(data.get('outputActive'))==target:break
                        if time.monotonic()>=end:raise RuntimeError('OBS chưa xác nhận trạng thái stream.')
                        time.sleep(0.25)
                elif action=='record_start':
                    check_current();data=self.client.send('StartRecord',raw=True)
                elif action=='record_stop':data=self.client.send('StopRecord',raw=True)
                elif action=='camera_start':
                    check_current();data=self.client.send('StartVirtualCam',raw=True)
                elif action=='camera_stop':data=self.client.send('StopVirtualCam',raw=True)
                else:raise ValueError('Lệnh OBS không hợp lệ.')
                self.results.put((action,not (action=='emergency' and data['failed']),data))
            except Exception as exc:
                if action in ('connect','status'):self.connected=False
                if action=='connect' and self.client is not None:
                    # 4.0: never keep using a client from a failed (re)connect.
                    try:self.client.disconnect()
                    except Exception:pass
                    self.client=None
                # Do not expose exception text that may contain credentials.
                self.results.put((action,False,'Đã hủy lệnh chờ' if isinstance(exc,InterruptedError) else type(exc).__name__))
        def finished(future):
            with self.lock:self.pending.pop(future,None)
            if future.cancelled():self.results.put((action,False,'Đã hủy lệnh chờ'))
        with self.lock:
            if self.closed:
                self.busy-=1;return False
            future=self.worker.submit(work);self.pending[future]=action;future.add_done_callback(finished)
        return True

    def drain(self):
        while not self.results.empty():
            with self.lock:self.busy=max(0,self.busy-1)
            yield self.results.get_nowait()

    def close(self):
        with self.lock:
            if self.closed:return
            self.closed=True;self.generation+=1;self.connected=False
            for future,action in list(self.pending.items()):
                if action not in ('stop','emergency'):future.cancel()
        def disconnect():
            if self.client:
                try:self.client.disconnect()
                except Exception:pass
        self.worker.submit(disconnect)
        self.worker.shutdown(wait=False,cancel_futures=False)
