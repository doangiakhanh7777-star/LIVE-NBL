"""Schedule decisions are separate from Windows actions; never infer success from a click."""
import json,math,os,subprocess,tempfile,time,uuid,threading
from pathlib import Path

_control_lock=threading.Lock()
_controls={}
def cancel_controls():
 with _control_lock:
  for path in list(_controls):
   try:Path(path).write_text('0',encoding='utf-8')
   except OSError:pass


def add_job(jobs,profile,start,end,clips,bundle='',no_sales=False,shuffle=False):
 if not profile or not clips:raise ValueError('Chọn nick và ít nhất một clip.')
 if not all(type(v) in (int,float) and math.isfinite(v) for v in (start,end)) or end<=start:raise ValueError('Giờ kết thúc phải sau giờ bắt đầu.')
 if start<=time.time():raise ValueError('Chọn thời gian tương lai; không phát bù lịch đã qua.')
 if any(j['profile']==profile and j['state'] not in ('finished','cancelled','skipped','failed','manual_stop') and start<j['end'] and j['start']<end for j in jobs):raise ValueError('Lịch cùng nick bị chồng giờ.')
 j=dict(id=uuid.uuid4().hex,profile=profile,start=start,end=end,clips=list(dict.fromkeys(clips)),bundle=bundle,no_sales=no_sales,shuffle=shuffle,state='pending',error='')
 jobs.append(j);return j

def decisions(jobs,now):
 actions=[]
 for j in jobs:
  state=j['state']
  if state in ('running','starting','preparing','recovering','attention') and now>=j['end'] and not (state=='attention' and j.get('end_stop_attempted')):
   j['state']='stopping';j['end_stop_attempted']=True;actions.append((j,'stop'));continue
  if state=='pending' and now>=j['start']:
   if now>=j['end'] or now-j['start']>45:j['state']='skipped';j['error']='Bỏ lịch đã lỡ';continue
   j['state']='preparing';actions.append((j,'prepare'));continue
  if state in ('running','recovering') and now-j.get('last_probe',0)>=5:
   j['last_probe']=now;actions.append((j,'status'))
 return actions

def execute(profile,action,deadline=0,payload=None):
 if os.name!='nt':raise RuntimeError('Điều khiển LIVE Studio chỉ chạy trên Windows; chưa xác minh trên máy này.')
 required=['pid','windowTitle','exePath']
 if action=='vision_capture' or (profile.get('vision',{}).get('enabled') and action in ('send','chat_check','greet_scan','greet','status')):
  if not is_studio_window(profile):raise ValueError('Chọn đúng cửa sổ LIVE Studio trước.')
  from studio_vision import execute_vision
  return execute_vision(profile,action,deadline,payload)
 if action not in ('inspect','pick','probe'):required+=['accountAnchor']
 if action not in ('inspect','pick','probe','greet_scan','collapse_chat'):required+=['liveIndicator']
 if action=='start':required+=['startButton']
 if action=='stop':required+=['stopButton']
 if action in ('send','chat_check'):required+=['chatInput','chatSend','chatRegion']
 if any(not profile.get(k) for k in required):raise ValueError('Chọn cửa sổ, tên nick và các nút cần dùng trong Kết nối LIVE Studio trước.')
 if not is_studio_window(profile):raise ValueError('Cửa sổ chưa xác định là LIVE Studio.')
 rpc=None;lease=None
 if profile.get('vision',{}).get('enabled') and action in ('start','stop'):
  from studio_vision_rpc import service
  rpc=service();lease=rpc.acquire(profile,deadline);profile={**profile,'_visionRpc':lease}
 fd,name=tempfile.mkstemp(suffix='.json');os.close(fd)
 guard=name+'.guard';guard_token=uuid.uuid4().hex
 Path(guard).write_text(guard_token,encoding='utf-8')
 with _control_lock:_controls[guard]=True
 profile={**profile,'_controlGuard':{'path':guard,'token':guard_token}}
 try:
  Path(name).write_text(json.dumps({**profile,'payload':payload or {},'_pythonExecutable':str(Path(__import__('sys').executable).with_name('python.exe'))},ensure_ascii=False),encoding='utf-8')
  proc=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(Path(__file__).with_name('studio_control.ps1')),'-ConfigFile',name,'-Action',action,'-Deadline',str(deadline)],capture_output=True,timeout=60 if profile.get('vision',{}).get('enabled') and action in ('start','stop') else 25,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
  if proc.returncode:raise RuntimeError(proc.stderr.decode('utf-8','replace')[-1000:])
  return json.loads(proc.stdout.decode('utf-8-sig'))
 finally:
  Path(name).unlink(missing_ok=True)
  with _control_lock:_controls.pop(guard,None)
  Path(guard).unlink(missing_ok=True)
  if rpc and lease:rpc.release(lease['lease'])


def _window_command(action):
 if os.name!='nt':raise RuntimeError('Chọn cửa sổ LIVE Studio cần Windows.')
 proc=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(Path(__file__).with_name('studio_window.ps1')),'-Action',action],capture_output=True,timeout=15,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 if proc.returncode:raise RuntimeError(proc.stderr.decode('utf-8','replace')[-1500:].strip() or 'Không đọc được cửa sổ Studio.')
 try:return json.loads(proc.stdout.decode('utf-8-sig') or '[]')
 except ValueError:raise RuntimeError('Windows trả kết quả cửa sổ không hợp lệ. Kiểm tra PowerShell và quyền đọc LIVE Studio.')

def list_windows():
 values=_window_command('list');return values if isinstance(values,list) else [values]

def window_from_pointer():
 value=_window_command('point')
 if not isinstance(value,dict) or not is_studio_window(value):raise ValueError('Đưa chuột vào đúng cửa sổ TikTok LIVE Studio.')
 return value

def explain_studio_error(error):
 raw=str(error).strip()
 translations=[('Select the current Studio window first','Cửa sổ Studio đã thay đổi. Tìm lại hoặc chọn cửa sổ bằng chuột trước.'),('Point at a control inside the selected Studio window','Chuột đang ngoài cửa sổ Studio đã chọn. Chọn lại đúng cửa sổ rồi thử.'),('Expected one calibrated element','Vị trí đang khớp nhiều nút hoặc chưa thấy nút. Chọn lại khi nút hiện trên Studio.'),('Cannot resolve exactly one Studio window','Không nhận ra đúng cửa sổ của nick. Kết nối lại cửa sổ Studio.'),('Access is denied','Windows không cho đọc Studio. Kiểm tra hai app có cùng mức quyền chạy.'),('LIVE state unknown','Chưa xác định đang LIVE hay đã dừng. Chọn đồng hồ khi đang LIVE và nút Phát LIVE khi chưa phát.')]
 for text,message in translations:
  if text.lower() in raw.lower():return message
 if 'timed out' in raw.lower():return 'Studio phản hồi quá lâu. Đợi cửa sổ sẵn sàng rồi thử lại.'
 return (raw[-700:] if raw else 'Không đọc được nút Studio. Bấm Sao chép lỗi kết nối để xem chi tiết.')

def is_studio_window(window):
 """Reject browser windows even when their title contains LIVE Studio."""
 import re
 exe=Path(str(window.get('exePath','')).replace('\\','/')).name.lower()
 title=str(window.get('windowTitle','')).lower()
 return exe not in ('chrome.exe','msedge.exe','firefox.exe','brave.exe','opera.exe','browser.exe','coccoc.exe','msedgewebview2.exe') and bool(re.search(r'(tiktok.*(live|studio)|live[ ._-]*studio)',exe,re.I)) and ('live' in title or 'studio' in title)


def message_capability(profile):
 """Validate stored descriptors without sending or touching Studio."""
 if profile.get('vision',{}).get('enabled'):
  from studio_vision_logic import validate_regions
  try:validate_regions(profile['vision'],('input','send','chat','clock'))
  except ValueError as error:return False,str(error)
  return bool(profile['vision'].get('sendImage')),'Khoanh nút Gửi mẫu trước.' if not profile['vision'].get('sendImage') else ''
 for key in ('chatRegion','chatInput','chatSend'):
  value=profile.get(key,'')
  if not value:return False,'Chưa chọn đủ ô nhập, nút gửi và khung trò chuyện.'
  try:kind=json.loads(value).get('kind') if value.startswith('{') else None
  except (ValueError,AttributeError):return False,'Thiết lập trò chuyện không hợp lệ; chọn lại mục này.'
  if kind=='visual' and key in ('chatRegion','chatInput'):return False,'Nhắn mẫu chưa sẵn sàng: ảnh ô nhập/khung chat chưa cho đọc bản nháp. Các mục khác vẫn chạy.'
 return True,''
