"""One bounded, prioritized Windows action queue for both Studio accounts."""
import itertools,queue,threading
from concurrent.futures import Future

class StudioWorker:
 def __init__(self,max_workers=1):
  self.queue=queue.PriorityQueue(maxsize=40);self.sequence=itertools.count();self.closed=False;self.lock=threading.Lock();self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
 def submit(self,fn,*args,**kwargs):return self.submit_priority(30,fn,*args,**kwargs)
 def submit_priority(self,priority,fn,*args,**kwargs):
  future=Future()
  with self.lock:
   if self.closed:future.set_exception(RuntimeError('Hàng đợi Studio đã đóng'));return future
   try:
    if priority>=20 and self.queue.qsize()>=32:raise queue.Full
    self.queue.put_nowait((priority,next(self.sequence),future,fn,args,kwargs))
   except queue.Full:future.set_exception(RuntimeError('Studio đang bận; hàng đợi đầy'))
  return future
 def run(self):
  while True:
   item=self.queue.get();_,_,future,fn,args,kwargs=item
   if fn is None:return
   if not future.set_running_or_notify_cancel():continue
   try:future.set_result(fn(*args,**kwargs))
   except BaseException as e:future.set_exception(e)
 def shutdown(self,wait=False,cancel_futures=True):
  with self.lock:
   self.closed=True
   if cancel_futures:
    while True:
     try:item=self.queue.get_nowait();item[2].cancel()
     except queue.Empty:break
   try:self.queue.put_nowait((-100,next(self.sequence),Future(),None,(),{}))
   except queue.Full:pass
  if wait:self.thread.join(timeout=30)
