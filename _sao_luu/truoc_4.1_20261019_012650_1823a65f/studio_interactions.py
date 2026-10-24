"""Independent Studio interactions. Each attempt is journaled before submission.
No background re-send after an uncertain result, restart, or an occupied draft.

4.0: a failure that happened before any click/keystroke (NotTouched: Studio
covered, not in front, OCR unreadable, LIVE clock not read yet...) no longer
switches the feature off. It is retried with a growing pause (30 s → 5 min);
after several in a row the phone alert fires once. Anything that may already
have reached Studio still stops the feature, as in 3.9.
"""
import copy,time,uuid
from collections import deque
from pathlib import Path
from studio_scheduler import execute,message_capability
from studio_vision_logic import NotTouched,SeenNames
from model import write_json

BACKOFF=(30,60,120,300)
ALERT_AFTER=4      # consecutive not-sent failures before a phone alert
GIVE_UP_AFTER=40   # roughly 3 hours of 5-minute retries


def backoff(failures):
 return BACKOFF[min(max(failures,1),len(BACKOFF))-1]


def report(kind,nick,title,detail=''):
 try:
  import nbl_reports;nbl_reports.add(kind,nick,title,detail)
 except Exception:pass


class StudioInteractions:
 def __init__(self,pool,path,log,notify=lambda key,text:None,clock=time.time,executor=execute):
  self.pool,self.path,self.log,self.notify,self.clock,self.executor=pool,path,log,notify,clock,executor
  self.states={};self.attempts=[]
 def state(self,pid):
  return self.states.setdefault(pid,dict(message=False,greeting=False,message_status='Đã dừng',greeting_status='Đã dừng',next_message=0,next_scan=0,next_greet=0,index=0,seen=SeenNames(5000),pending=deque(maxlen=100),baseline=False,future=None,failures=dict(message=0,greeting=0),sent=0,greeted=0,generations=dict(message=0,greeting=0)))
 def enable(self,p,kind,config):
  s=self.state(p['id']);required=['pid','windowTitle','exePath','accountAnchor','liveIndicator','startButton','chatRegion']
  if kind=='message':required+=['chatInput','chatSend']
  if p.get('vision',{}).get('enabled'):required=['pid','windowTitle','exePath','accountAnchor']
  if any(not p.get(k) for k in required):raise ValueError('Trong Kết nối LIVE Studio, chọn tên nick, đồng hồ LIVE, khung trò chuyện và các nút cần dùng trước.')
  if kind=='message':
   ready,reason=message_capability(p)
   if not ready:raise ValueError(reason)
   lines=[x.strip() for x in config.get('messages','').splitlines() if x.strip()]
   interval=config.get('interval',300)
   if not lines or any(len(x)>100 for x in lines):raise ValueError('Mỗi câu cần 1–100 ký tự; mỗi dòng một câu.')
   if type(interval) is not int or not 60<=interval<=86400:raise ValueError('Khoảng nhắn cần từ 60 đến 86400 giây.')
   s['lines']=lines;s['interval']=interval;s['next_message']=self.clock()+interval;s['index']=0
  elif kind=='greeting':
   wait=config.get('greeting_interval',10)
   if type(wait) is not int or not 10<=wait<=3600:raise ValueError('Khoảng nghỉ chào cần từ 10 đến 3600 giây.')
   s['greeting_interval']=wait;s['seen'].clear();s['pending'].clear();s['baseline']=False;s['next_scan']=0;s['next_greet']=0
  else:raise ValueError('Mục không hợp lệ')
  if p.get('vision',{}).get('enabled') and kind=='greeting':
   from studio_vision_logic import validate_regions
   validate_regions(p['vision'],('chat','clock','greeting'))
   if not p['vision'].get('greetingImage'):raise ValueError('Khoanh một nút Chào mẫu trước.')
  self.stop(p['id'],kind)  # revoke the previous run, including in-flight input
  s['generations'][kind]+=1
  guard=Path(self.path).parent/('studio_guard_'+p['id']+'_'+kind+'.txt')
  token=uuid.uuid4().hex;guard.write_text(token,encoding='utf-8');s[kind+'_guard']={'path':str(guard),'token':token}
  s['failures'][kind]=0
  s[kind]=True;s[kind+'_status']='Đang chờ LIVE / đến lượt';self.log(p['name']+' · bật '+kind)
 def stop(self,pid,kind):
  s=self.state(pid)
  s['generations'][kind]+=1
  s[kind]=False;s[kind+'_status']='Đã dừng'
  guard=s.get(kind+'_guard')
  if guard:
   from studio_vision_logic import revoke_guard
   revoke_guard(guard['token'])
   try:Path(guard['path']).write_text('0',encoding='utf-8')
   except OSError:self.log('Đã dừng trong app; chưa ghi được tệp trạng thái dừng Studio.')
  if kind=='greeting':s['pending'].clear()
  current=s.get('future')
  if current and current[1].startswith('greet' if kind=='greeting' else 'send'):current[0].cancel()
 def stop_all(self):
  for pid in self.states:
   for kind in ('message','greeting'):self.stop(pid,kind)
 def _journal(self):
  write_json(self.path,dict(attempts=self.attempts))
 def _submit(self,p,s,action,payload=None):
  # Durable reservation is committed BEFORE a command can reach Studio.
  attempt=None
  if action in ('send','greet'):
   attempt=dict(id=uuid.uuid4().hex,profile=p['id'],action=action,time=self.clock(),state='attempted')
   if payload and payload.get('text'):attempt['text']=payload['text'][:100]
   self.attempts.append(attempt);self.attempts=self.attempts[-200:];self._journal()
  deadline=min(self.clock()+20,p['activeUntil']) if p.get('activeUntil') else self.clock()+20
  command_profile=copy.deepcopy(p)
  kind='greeting' if action.startswith('greet') else 'message'
  if s.get(kind+'_guard'):command_profile['_interactionGuard']=s[kind+'_guard']
  future=self.pool.submit_priority(40 if action.startswith('greet') else 30,self.executor,command_profile,action,deadline,payload)
  s['future']=(future,action,attempt,payload,s['generations'][kind])
 def _not_sent(self,p,s,kind,action,payload,error,now):
  """Nothing reached Studio: keep the feature on and try again later."""
  s['failures'][kind]+=1;n=s['failures'][kind];wait=backoff(n)
  if n>=GIVE_UP_AFTER:
   self.stop(p['id'],kind);s[kind+'_status']='Đã dừng sau '+str(n)+' lần không thao tác được: '+str(error)
   report('loi',p['name'],('Nhắn mẫu' if kind=='message' else 'Chào khách')+' đã DỪNG sau '+str(n)+' lần',str(error))
   self.notify('studio:'+p['id']+':'+kind,p['name']+' · '+s[kind+'_status']);return
  if kind=='message':
   if action=='send':s['index']=max(0,s['index']-1)   # resend the same line next time
   s['next_message']=now+wait
  else:
   if action=='greet' and payload and payload.get('key') and len(s['pending'])<100:s['pending'].appendleft((payload['key'],now+wait+30))
   s['next_scan']=now+wait;s['next_greet']=max(s['next_greet'],now+wait)
  s[kind+'_status']='Tạm hoãn ('+str(n)+'): '+str(error)+' · thử lại sau '+str(wait)+' giây'
  if n==1:self.log(p['name']+' · '+kind+' tạm hoãn: '+str(error))
  if n==ALERT_AFTER:self.notify('studio:'+p['id']+':'+kind,p['name']+' · '+kind+' chưa thao tác được '+str(n)+' lần liên tiếp: '+str(error))
 def tick(self,profiles,blocked=()):
  now=self.clock()
  for p in profiles:
   s=self.state(p['id'])
   try:
    current=s.get('future')
    if current:
     future,action,attempt,payload,generation=current
     if not future.done():continue
     s['future']=None
     if future.cancelled():
      if attempt:attempt['state']='cancelled';self._journal()
      continue
     kind='greeting' if action.startswith('greet') else 'message'
     if generation!=s['generations'][kind] or not s[kind]:
      if attempt:
       try:
        outcome=future.result()
        attempt['state']='confirmed_after_stop' if outcome.get('confirmed') else 'skipped' if outcome.get('gone') else 'uncertain'
       except NotTouched:attempt['state']='not_sent'
       except Exception as error:attempt['state']='not_sent' if getattr(error,'touched',None) is False else 'uncertain'
       self._journal()
      continue
     try:
      result=future.result()
      for notice in (result.get('dismissed') or []) if isinstance(result,dict) else []:
       # 4.0.3: an informational Studio notice was closed with its OK button.
       self.log(p['name']+' · đã tự đóng thông báo Studio: '+notice)
       self.notify('studio:'+p['id']+':notice',p['name']+' · Studio báo: '+notice+' (NBL đã bấm OK, vẫn tiếp tục)')
      if action=='greet_scan' and s['greeting']:
       if not result.get('live'):s['greeting_status']='Chờ phiên LIVE';s['baseline']=False;s['pending'].clear()
       else:
        values=list(dict.fromkeys(result.get('viewers',[])))
        if s['baseline']:
         queued={k for k,_ in s['pending']}
         for key in values:
          if key not in s['seen'] and key not in queued and len(s['pending'])<100:s['pending'].append((key,now+30))
        else:s['baseline']=True
        s['seen'].update(values)
        s['greeting_status']='Đang theo dõi khách mới · đã chào '+str(s['greeted'])
       s['next_scan']=now+5;s['failures']['greeting']=0
      elif action=='send':
       if not result.get('sent') or not result.get('confirmed'):raise ValueError('Chưa xác nhận tin nhắn; kiểm tra chat rồi bật lại')
       s['sent']+=1;s['failures']['message']=0
       self.log(p['name']+' · đã gửi: '+(payload or {}).get('text',''))
       report('hoat_dong',p['name'],'Đã gửi tin nhắn',(payload or {}).get('text','')+' · cách xác nhận: '+str(result.get('method','')))
       s['message_status']='Đã xác nhận gửi '+str(s['sent'])+' tin · lần tới '+time.strftime('%H:%M:%S',time.localtime(now+s['interval']));s['next_message']=now+s['interval']
      elif action=='greet':
       if not result.get('gone') and not result.get('greeted'):raise ValueError('Chưa xác nhận chào; kiểm tra chat rồi bật lại')
       if result.get('greeted'):s['greeted']+=1;report('hoat_dong',p['name'],'Đã chào khách',str((payload or {}).get('key','')))
       s['failures']['greeting']=0
       s['greeting_status']='Khách đã rời dòng chat' if result.get('gone') else 'Đã xác nhận chào · tổng '+str(s['greeted']);s['next_greet']=now+s.get('greeting_interval',10)
      if attempt:attempt['state']='confirmed' if result.get('confirmed') or result.get('greeted') else 'skipped' if result.get('gone') else 'uncertain';self._journal()
     except NotTouched as e:
      if attempt:attempt['state']='not_sent';self._journal()
      if s[kind]:self._not_sent(p,s,kind,action,payload,e,now)
     except Exception as e:
      if not s[kind]:
       if attempt:attempt['state']='uncertain';self._journal()
       continue
      self.stop(p['id'],kind);s[kind+'_status']='Cần kiểm tra: '+str(e)
      report('loi',p['name'],('Nhắn mẫu' if kind=='message' else 'Chào khách')+' đã DỪNG',str(e))
      if attempt:attempt['state']='uncertain';self._journal()
      self.log(p['name']+' · '+str(e));self.notify('studio:'+p['id']+':'+kind,p['name']+' · '+str(e))
    if p.get('activeUntil') and now>=p['activeUntil']:
     for kind in ('message','greeting'):self.stop(p['id'],kind)
     continue
    if p['id'] in blocked or s.get('future'):continue
    if s['message'] and now>=s['next_message']:
     text=s['lines'][s['index']%len(s['lines'])];s['index']+=1;s['next_message']=now+s['interval'];self._submit(p,s,'send',dict(text=text));continue
    if s['greeting']:
     while s['pending'] and s['pending'][0][1]<now:s['pending'].popleft()
     if s['pending'] and now>=s['next_greet']:
      key,_=s['pending'].popleft();s['next_greet']=now+s.get('greeting_interval',10);self._submit(p,s,'greet',dict(key=key))
     elif now>=s['next_scan']:s['next_scan']=now+5;self._submit(p,s,'greet_scan')
   except Exception as e:
    # Configuration/journal failures remain local to this account.
    for kind in ('message','greeting'):self.stop(p['id'],kind)
    self.log(p['name']+' · Tương tác Studio: '+str(e))
