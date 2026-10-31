"""Schedule decisions are separate from Windows actions; never infer success from a click."""
import json,math,os,subprocess,tempfile,time,uuid,threading
from pathlib import Path

_control_lock=threading.Lock()
_controls={}
NO_MOUSE = False          # 4.3.16: app đặt True khi "Ẩn hết khi LIVE"

def cancel_controls():
 with _control_lock:
  for path in list(_controls):
   try:Path(path).write_text('0',encoding='utf-8')
   except OSError:pass


ACTIVE=('preparing','starting','running','stopping','recovering','attention','start_retry','stop_retry')
START_MARGIN=60      # 4.1: a late start is still made while at least 60 s of the slot remain
STOP_TRIES=5
RETRY_GAP=30


def add_job(jobs,profile,start,end,clips=(),bundle='',no_sales=False,shuffle=False,bundle_index=1,now=None):
 # 4.1.2: a schedule has no clips of its own; the nick's open NBL VIDEO is replayed
 # from its first clip (owner, 19/10/2026 02:40).
 now=time.time() if now is None else now
 if not profile:raise ValueError('Chọn nick trước.')
 if not all(type(v) in (int,float) and math.isfinite(v) for v in (start,end)) or end<=start:raise ValueError('Giờ kết thúc phải sau giờ bắt đầu.')
 if start<=now:raise ValueError('Chọn thời gian tương lai; không phát bù lịch đã qua.')
 if end-start<120:raise ValueError('Phiên LIVE cần dài ít nhất 2 phút.')
 if any(j['profile']==profile and j['state'] not in ('finished','cancelled','skipped','failed','manual_stop') and start<j['end'] and j['start']<end for j in jobs):raise ValueError('Lịch cùng nick bị chồng giờ.')
 # 4.1.5: bộ số 0 = keep the cart the owner filled by hand (NBL does not touch it).
 if not no_sales and (type(bundle_index) is not int or not 0<=bundle_index<=200):raise ValueError('Chọn bộ sản phẩm số mấy (1 = bộ đầu tiên, 0 = giữ giỏ tự thêm tay).')
 j=dict(id=uuid.uuid4().hex,profile=profile,start=start,end=end,clips=list(dict.fromkeys(clips)),bundle=bundle,bundle_index=0 if no_sales else bundle_index,no_sales=no_sales,shuffle=shuffle,state='pending',error='',cart=dict(state='none',attempts=0,next=0))
 jobs.append(j);return j


def overlapping_other_nicks(jobs,profile,start,end):
 """4.1: two nicks may LIVE at the same time on one PC (owner, 19/10/2026)."""
 return [j for j in jobs if j['profile']!=profile and j['state'] not in ('finished','cancelled','skipped','failed','manual_stop') and start<j['end'] and j['start']<end]


def decisions(jobs,now,can_start=lambda j:True):
 """What to do now. 4.1: late starts are retried while time remains, failed
 stops are retried, and a sales LIVE never starts without a ready cart."""
 actions=[]
 for j in jobs:
  state=j['state']
  if state in ('running','starting','preparing','recovering','attention','start_retry') and now>=j['end'] and not (state=='attention' and j.get('end_stop_attempted')):
   if state=='start_retry':j['state']='skipped';j['error']='Hết giờ lịch trước khi phát được';continue
   j['state']='stopping';j['end_stop_attempted']=True;actions.append((j,'stop'));continue
  if state=='stop_retry' and now>=j.get('retry_at',0):
   j['state']='stopping';actions.append((j,'stop'));continue
  if state in ('pending','start_retry') and now>=j['start'] and now>=j.get('retry_at',0):
   if now>=j['end']-START_MARGIN:
    j['state']='skipped';j['error']=j.get('error') or 'Bỏ lịch: không còn đủ thời gian để phát';continue
   if not can_start(j):continue
   j['state']='preparing';actions.append((j,'prepare'));continue
  if state in ('running','recovering') and now-j.get('last_probe',0)>=10:
   j['last_probe']=now;actions.append((j,'status'))
  # 4.1.3: a job left in "Cần kiểm tra" used to stay there for ever and blocked the
  # next schedule of the same nick (no cart, no start). Keep looking at Studio: once
  # the LIVE is off the job is finished; a LIVE still on after its end is retried.
  elif state=='attention' and now-j.get('last_probe',0)>=15 and now<j['end']+6*3600:
   j['last_probe']=now;actions.append((j,'status'))
 return actions

def execute(profile,action,deadline=0,payload=None):
 if os.name!='nt':raise RuntimeError('Điều khiển LIVE Studio chỉ chạy trên Windows; chưa xác minh trên máy này.')
 # 4.3.9: tắt hẳn Studio phải làm được với MỌI nick, kể cả nick chưa bật kết nối tự động
 # (lúc đó không có cổng điều khiển nên tắt thẳng tiến trình theo tên file Studio).
 if action in ('quit_studio','emergency_stop') and not profile.get('cdp'):
  from studio_cdp import kill_studio
  why=''
  if action=='emergency_stop':
   try:
    r=execute(profile,'stop',deadline,payload)
    if not r.get('live'):return dict(r,quit=False)
    why='Studio vẫn báo đang LIVE sau lệnh kết thúc'
   except Exception as e:why=str(e)
  k=kill_studio(profile.get('exePath'),int(profile.get('cdpPort') or 0))
  if action=='emergency_stop' and not k.get('closed'):raise ValueError('Chưa kết thúc được LIVE và cũng chưa tắt được Studio. Lý do: '+why[:200])
  return dict(k,studioClosed=True,live=False,quit=action=='emergency_stop',why=why[:200])
 required=['pid','windowTitle','exePath']
 # 4.2.1 (owner, 28/10/2026): "kết nối tự động" — Studio is read and driven from the
 # inside (DevTools port opened by NBL); no regions, no window, no mouse.
 if profile.get('cdp'):
  from studio_cdp import execute_cdp,CDP_ACTIONS
  from studio_vision_logic import NotTouched as _NotTouched
  if action in CDP_ACTIONS:
   try:return execute_cdp(profile,action,deadline,payload)
   except _NotTouched:
    # the image path is kept as a fallback for a nick that still has its regions
    # 4.3.0 (owner): never take the mouse unless the owner switched the old way on
    if not (profile.get('useMouse') and profile.get('vision',{}).get('enabled') and profile.get('windowHandle') and action not in ('probe','connect','chat_read','captcha')):raise
 # 4.1: with reading-by-image set up, starting and ending the LIVE also go through it.
 if action=='vision_capture' or (profile.get('vision',{}).get('enabled') and action in ('send','chat_check','greet_scan','greet','status','start','stop','close_summary','reset_live')):
  # 4.3.16 (chủ máy): đang "Ẩn hết khi LIVE" thì không bao giờ dùng đường ảnh + chuột (chủ máy đang dùng PC việc khác)
  if NO_MOUSE:
   from studio_vision_logic import NotTouched as _NT
   raise _NT('NBL đang ẩn: không dùng chuột/bàn phím. Kết nối tự động (DevTools) với Studio đang hỏng — hiện lại NBL để xử lý.')
  if not is_studio_window(profile):raise ValueError('Chọn đúng cửa sổ LIVE Studio trước.')
  from studio_vision import execute_vision
  try:return execute_vision(profile,action,deadline,payload)
  except Exception as error:
   if not window_gone(error):raise
   # 4.1.4: Studio was closed and opened again (new window). Attach to the new one
   # by itself when exactly one free TikTok LIVE Studio window of the same program
   # is open; the saved nick picture is still checked before anything is clicked.
   try:windows=list_windows()
   except Exception:windows=None
   fresh=rebind_window(profile,windows) if windows is not None else None
   # 4.1.7 (owner log 20/10/2026 13:58): no TikTok LIVE Studio window is left at all
   # = Studio was closed, so the LIVE is over. Say so instead of "tắt tay ngay".
   if not fresh and windows is not None and action in ('status','stop','close_summary') and not studio_windows(profile,windows,free_only=False):
    return {'live':False,'studioClosed':True,'closed':True}
   if not fresh:raise type(error)('Studio đã mở lại thành cửa sổ mới nhưng NBL không chắc cửa sổ nào của nick này. Bấm Kết nối LIVE Studio → Tìm cửa sổ, chọn lại rồi Lưu (vùng đã khoanh được giữ).') from error
   result=execute_vision(fresh,action,deadline,payload)
   if isinstance(result,dict):result.update(windowHandle=fresh['windowHandle'],pid=fresh['pid'],windowTitle=fresh['windowTitle'],rebound=True)
   return result
 if NO_MOUSE and action not in ('inspect','probe'):
  # 4.3.16: đường cũ (studio_control.ps1) kéo cửa sổ lên trước / bấm chuột -> cấm khi đang ẩn
  from studio_vision_logic import NotTouched as _NT
  raise _NT('NBL đang ẩn: không dùng chuột/bàn phím (nick này chưa có kết nối tự động với Studio).')
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

def window_gone(error):
 text=str(error)
 return 'Cửa sổ Studio đã đổi' in text or 'không còn thuộc Studio đã lưu' in text


def studio_windows(profile,windows,free_only=True):
 exe=os.path.normcase(str(profile.get('exePath','')))
 taken={str(h) for h in profile.get('_otherHandles',[]) if h} if free_only else set()
 return [w for w in windows if isinstance(w,dict) and is_studio_window(w) and os.path.normcase(str(w.get('exePath','')))==exe and str(w.get('windowHandle')) not in taken]


def _area(w):
 try:return max(0,int(w.get('width') or 0))*max(0,int(w.get('height') or 0))
 except (TypeError,ValueError):return 0


def rebind_window(profile,windows=None):
 """The TikTok LIVE Studio window of the same program that no other nick uses, or None.
 4.1.7: Studio also opens small windows of its own (floating chat, pop-ups). When
 there are several, the main one is taken only if it is clearly the biggest
 (at least twice the next); the saved nick picture is still checked before a click."""
 try:windows=list_windows() if windows is None else windows
 except Exception:return None
 found=sorted(studio_windows(profile,windows),key=_area,reverse=True)
 if not found:return None
 if len(found)>1 and not (_area(found[0])>0 and _area(found[0])>=2*_area(found[1])):return None
 w=found[0]
 return {**profile,'windowHandle':str(w['windowHandle']),'pid':str(w['pid']),'windowTitle':w.get('windowTitle') or profile.get('windowTitle','')}


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
 if profile.get('cdp'):return True,''     # 4.2.1: comment box read from inside Studio
 if profile.get('vision',{}).get('enabled'):
  from studio_vision_logic import validate_regions
  try:validate_regions(profile['vision'],('input','send','chat','clock'))
  except ValueError as error:return False,str(error)
  return True,''   # 4.1: sending uses Enter; the Send icon image is only a fallback
 for key in ('chatRegion','chatInput','chatSend'):
  value=profile.get(key,'')
  if not value:return False,'Chưa chọn đủ ô nhập, nút gửi và khung trò chuyện.'
  try:kind=json.loads(value).get('kind') if value.startswith('{') else None
  except (ValueError,AttributeError):return False,'Thiết lập trò chuyện không hợp lệ; chọn lại mục này.'
  if kind=='visual' and key in ('chatRegion','chatInput'):return False,'Nhắn mẫu chưa sẵn sàng: ảnh ô nhập/khung chat chưa cho đọc bản nháp. Các mục khác vẫn chạy.'
 return True,''
