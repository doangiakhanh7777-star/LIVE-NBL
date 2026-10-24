"""Validated, atomic local profiles and commands.

4.0: profiles.json keeps a last-good copy (profiles.json.bak). A damaged file
no longer closes the app: the backup is loaded, or broken sessions are left
out, and the damaged file is kept aside as profiles.json.broken-<time>.
"""
import json
import math
import shutil
import time
import os
import uuid
from pathlib import Path

def write_json(path, value, backup=False):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    backup = backup or path.name in ('profiles.json','studio_schedules.json')
    if backup and path.exists():
        try:
            json.loads(path.read_text(encoding='utf-8'))  # only a readable file becomes the backup
            shutil.copy2(path, path.with_name(path.name + '.bak'))
        except (OSError, ValueError):
            pass
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)

def validate(value):
    if not isinstance(value, dict) or value.get('schema') != 2: raise ValueError('Cấu hình không thuộc NBL LIVE 2.')
    sessions = value.get('sessions')
    if not isinstance(sessions, list) or not sessions or len(sessions) > 16: raise ValueError('Tối đa 16 phiên.')
    numbers = set(); ids = set(); bindings=set()
    for s in sessions:
        if not isinstance(s, dict): raise ValueError('Phiên không hợp lệ.')
        if type(s.get('number')) is not int or not 1 <= s['number'] <= 99 or s['number'] in numbers: raise ValueError('Số cửa sổ trùng hoặc không hợp lệ.')
        if not isinstance(s.get('id'), str) or len(s['id']) != 32 or any(c not in '0123456789abcdef' for c in s['id']) or s['id'] in ids: raise ValueError('Mã phiên không hợp lệ.')
        numbers.add(s['number']); ids.add(s['id'])
        if not isinstance(s.get('playlist'), list) or not all(isinstance(p, str) for p in s['playlist']): raise ValueError('Playlist không hợp lệ.')
        if type(s.get('volume')) is not int or not 0 <= s['volume'] <= 100: raise ValueError('Âm lượng phải từ 0 đến 100.')
        for key in ('account', 'device', 'pins', 'rules', 'messages'):
            if not isinstance(s.get(key, ''), str): raise ValueError('Nội dung phiên không hợp lệ.')
            s.setdefault(key,'')
        for key in ('loop', 'shuffle', 'mute'):
            if not isinstance(s.get(key), bool): raise ValueError('Tùy chọn phiên không hợp lệ.')
        chrome=s.get('chrome',{})
        if not isinstance(chrome,dict):raise ValueError('Thiết lập Chrome không hợp lệ.')
        for key in ('owner','scheduled','cycle','repeatPins','replyMode','interval','cooldown'):
            if key in chrome and not isinstance(chrome[key],str):raise ValueError('Thiết lập Chrome phải là chữ.')
        for key,minimum in [('interval',60),('cooldown',15)]:
            if key in chrome:
                try:n=int(chrome[key])
                except (ValueError,TypeError):raise ValueError('Khoảng thời gian Chrome không hợp lệ.')
                if not minimum<=n<=86400:raise ValueError('Khoảng thời gian Chrome ngoài giới hạn.')
        binding=s.get('chrome_binding',{})
        if not isinstance(binding,dict):raise ValueError('Tab gắn với phiên không hợp lệ.')
        if binding:
            if type(binding.get('tab')) is not int or binding['tab']<0 or not isinstance(binding.get('account'),str) or not binding['account']:
                raise ValueError('Thông tin tài khoản Chrome không hợp lệ.')
            for field in ('instance','client'):
                if not isinstance(binding.get(field,''),str) or (binding.get(field) and (len(binding[field])!=32 or any(c not in '0123456789abcdef' for c in binding[field]))):
                    raise ValueError('Mã kết nối Chrome không hợp lệ.')
            if not binding.get('instance') and not binding.get('client'):raise ValueError('Thiếu mã gắn tab Chrome.')
            target=(binding.get('instance') or binding.get('client'),binding['tab'],binding['account'])
            if target in bindings:raise ValueError('Một tab Chrome đang được gắn với nhiều phiên.')
            bindings.add(target)
    jobs=value.get('jobs',[])
    if not isinstance(jobs,list) or len(jobs)>2000:raise ValueError('Lịch hẹn không hợp lệ.')
    for j in jobs:
        if not isinstance(j,dict) or j.get('action') not in ('play','stop','obs_start','obs_stop') or type(j.get('at')) not in (int,float) or not math.isfinite(j['at']) or j.get('state') not in ('pending','skipped','dispatched','failed') or type(j.get('number')) is not int or not isinstance(j.get('session'),str):raise ValueError('Mốc hẹn không hợp lệ.')
    settings=value.get('settings',{})
    if not isinstance(settings,dict):raise ValueError('Thiết lập chung không hợp lệ.')
    for field in ('keep_awake','repeat'):
        if field in settings and type(settings[field]) is not bool:raise ValueError('Thiết lập chung không hợp lệ.')
    if 'obs_host' in settings and not isinstance(settings['obs_host'],str):raise ValueError('Địa chỉ OBS không hợp lệ.')
    if 'obs_port' in settings and (type(settings['obs_port']) is not int or not 1<=settings['obs_port']<=65535):raise ValueError('Cổng OBS không hợp lệ.')
    for field,minimum in [('live_minutes',.5),('rest_minutes',.2)]:
        if field in settings and (type(settings[field]) not in (int,float) or not math.isfinite(settings[field]) or not minimum<=settings[field]<=1440):raise ValueError('Thời gian phát/nghỉ không hợp lệ.')
    return value

def new_session(number):
    return dict(id=uuid.uuid4().hex, number=number, account='', playlist=[], volume=80, device='', mute=False, loop=True, shuffle=False, pins='', rules='', messages='')

def salvage(value):
    """Keep the sessions that validate on their own; drop jobs/settings that do not."""
    if not isinstance(value, dict):
        raise ValueError('Cấu hình không đọc được.')
    good = []
    for session in value.get('sessions', []) if isinstance(value.get('sessions'), list) else []:
        try:
            validate({'schema': 2, 'sessions': good + [session]}); good.append(session)
        except (ValueError, TypeError, KeyError, AttributeError):
            pass
    if not good:
        raise ValueError('Không còn phiên hợp lệ.')
    result = {'schema': 2, 'sessions': good}
    for key in ('jobs', 'settings'):
        if key in value:
            try:
                validate({**result, key: value[key]}); result[key] = value[key]
            except (ValueError, TypeError, KeyError, AttributeError):
                pass
    for key, item in value.items():
        if key not in ('schema', 'sessions', 'jobs', 'settings'):
            result[key] = item
    return validate(result)


def load(path, report=None):
    """Load profiles; on damage fall back to backup or salvage. `report(text)` gets a notice."""
    p = Path(path)
    if not p.exists(): return {'schema': 2, 'sessions': [new_session(1)]}
    try:
        return validate(json.loads(p.read_text(encoding='utf-8')))
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        damaged = p.with_name(p.name + '.broken-' + time.strftime('%Y%m%d-%H%M%S'))
        try: shutil.copy2(p, damaged)
        except OSError: pass
        notice = 'profiles.json bị hỏng (' + str(error)[:120] + '). Bản lỗi giữ tại ' + damaged.name + '. '
        backup = p.with_name(p.name + '.bak')
        try:
            value = validate(json.loads(backup.read_text(encoding='utf-8')))
            if report: report(notice + 'Đã mở bản lưu tốt gần nhất.')
            return value
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            pass
        try:
            value = salvage(json.loads(p.read_text(encoding='utf-8')))
            if report: report(notice + 'Đã giữ ' + str(len(value['sessions'])) + ' phiên còn đọc được.')
            return value
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            if report: report(notice + 'Không cứu được phiên nào; tạo cấu hình mới.')
            return {'schema': 2, 'sessions': [new_session(1)]}
