"""Validate and recover Studio data independently of Qt/Windows."""
import copy,json,math,shutil,time
from pathlib import Path
STATES={'pending','preparing','starting','running','stopping','recovering','recovery_review','attention','finished','failed','manual_stop','skipped','cancelled'}

def validate(saved):
 if not isinstance(saved,dict) or not isinstance(saved.get('profiles'),list) or len(saved['profiles'])>2 or not isinstance(saved.get('jobs'),list):raise ValueError('Sai cấu trúc lịch')
 if any(not isinstance(p,dict) or any(not isinstance(p.get(k),str) for k in ('id','name','pid','session')) for p in saved['profiles']):raise ValueError('Sai liên kết nick')
 if not isinstance(saved.get('controls',{}),dict):raise ValueError('Sai thiết lập nút Studio')
 if not isinstance(saved.get('library',[]),list) or not all(isinstance(x,str) for x in saved.get('library',[])):raise ValueError('Sai thư viện clip Studio')
 ids={p['id'] for p in saved['profiles']}
 if len(ids)!=len(saved['profiles']):raise ValueError('Trùng nick Studio')
 for j in saved['jobs']:
  if not isinstance(j,dict) or any(k not in j for k in ('id','profile','state','start','end','clips','no_sales')):raise ValueError('Sai mốc lịch')
  if j['state'] not in STATES or not all(type(j[k]) in (int,float) and math.isfinite(j[k]) for k in ('start','end')) or j['end']<=j['start']:raise ValueError('Thời gian/trạng thái không hợp lệ')
  if not isinstance(j['clips'],list) or not all(isinstance(x,str) for x in j['clips']) or type(j['no_sales']) is not bool:raise ValueError('Sai clip hoặc tùy chọn')
  if j['state'] in ('pending','preparing','starting','running','stopping','recovering','attention','recovery_review') and j['profile'] not in ids:raise ValueError('Lịch mất liên kết nick')
 return saved

def salvage(value):
 if not isinstance(value,dict):raise ValueError('Dữ liệu lịch không hợp lệ')
 result=dict(profiles=[],jobs=[],controls=value.get('controls',{}) if isinstance(value.get('controls'),dict) else {},library=[x for x in value.get('library',[]) if isinstance(x,str)] if isinstance(value.get('library'),list) else [])
 for p in value.get('profiles',[]) if isinstance(value.get('profiles'),list) else []:
  try:validate({**result,'profiles':result['profiles']+[p]});result['profiles'].append(p)
  except (ValueError,TypeError,KeyError):pass
 for j in value.get('jobs',[]) if isinstance(value.get('jobs'),list) else []:
  try:validate({**result,'jobs':result['jobs']+[j]});result['jobs'].append(j)
  except (ValueError,TypeError,KeyError):pass
 if not result['profiles'] and value.get('profiles'):raise ValueError('Không còn nick Studio hợp lệ')
 return validate(result)

def load(path):
 path=Path(path);empty=dict(profiles=[],jobs=[],controls={},library=[])
 if not path.exists():return empty,''
 try:return validate(json.loads(path.read_text(encoding='utf-8-sig'))),''
 except (OSError,ValueError,TypeError,KeyError) as error:
  damaged=path.with_name(path.name+'.broken-'+str(time.time_ns()))
  try:shutil.copy2(path,damaged)
  except OSError:pass
  notice='Tệp lịch Studio lỗi: '+str(error)+'. Bản lỗi giữ tại '+damaged.name+'. '
  try:value=validate(json.loads(path.with_name(path.name+'.bak').read_text(encoding='utf-8-sig')));notice+='Đã mở bản sao lưu.'
  except (OSError,ValueError,TypeError,KeyError):
   try:value=salvage(json.loads(path.read_text(encoding='utf-8-sig')));notice+='Đã giữ phần dữ liệu còn đọc được.'
   except (OSError,ValueError,TypeError,KeyError):value=empty;notice+='Không khôi phục được; có thể thiết lập lại.'
  value=copy.deepcopy(value)
  # A recovered backup must never open an old scheduled LIVE automatically.
  for j in value['jobs']:
   if j['state']=='pending':j['state']='cancelled';j['error']='Lịch khôi phục cần tạo lại để xác nhận giờ/nick.'
  return value,notice
