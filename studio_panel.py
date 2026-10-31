"""Two-account Studio scheduling UI. Windows calls run outside the GUI thread."""
import copy,json,re,time,uuid,math,os
from studio_worker import StudioWorker
from pathlib import Path
from PySide6.QtCore import QTimer,QDateTime,Qt
from PySide6.QtWidgets import (QSpinBox,QApplication,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QComboBox,QLineEdit,QListWidget,QAbstractItemView,QDateTimeEdit,QCheckBox,QFileDialog,QMessageBox,QDialog,QFormLayout,QTextEdit,QScrollArea,QGroupBox)
from model import write_json
from session_binding import resolve_binding
from video_commands import same_file
from studio_scheduler import add_job,decisions,execute,list_windows,window_from_pointer,explain_studio_error,overlapping_other_nicks,ACTIVE,START_MARGIN,RETRY_GAP,STOP_TRIES


def report(kind,nick,title,detail=''):
 try:
  import nbl_reports;nbl_reports.add(kind,nick,title,detail)
 except Exception:pass
from studio_vision_logic import NotTouched,same_author
CONTROL_FIELDS={'liveIndicator','startButton','startConfirm','stopMenu','stopButton','stopConfirm','summaryClose','chatRegion','chatInput','chatSend','collapseImage'}
OPTIONAL_FIELDS={'startConfirm','stopMenu','stopConfirm','summaryClose'}
def vision_missing(profile):
 if profile.get('cdp'):return ''          # 4.2.1: kết nối tự động needs no regions
 """4.1.2: '' when the nick can be started/ended by image; otherwise what to do."""
 vision=profile.get('vision') or {}
 if vision.get('enabled') and (vision.get('regions') or {}).get('clock'):return ''
 name=str(profile.get('accountName') or profile.get('name') or '')
 return ('Nick '+name+' chưa khoanh vùng Studio nên NBL không bấm Phát / Kết thúc LIVE được. '
         'Chọn nick này ở đầu app → Tin nhắn & chào khách → Thiết lập đọc bằng ảnh → khoanh "Đồng hồ LIVE" '
         '(chỗ nút Phát LIVE) và "Khung chat" → Lưu các vùng đã khoanh. Chưa bấm gì trên Studio.')
def video_problem(session):
 """4.1.2: the nick's NBL VIDEO playlist (trang Video & âm thanh) must exist."""
 playlist=[x for x in (session or {}).get('playlist',[]) if x]
 if not playlist:raise ValueError('Nick này chưa có video: vào trang Video & âm thanh → Thêm video → MỞ & PHÁT, rồi gắn cửa sổ NBL VIDEO vào Studio.')
 lost=[x for x in playlist if not Path(x).is_file()]
 if lost:raise ValueError('Video không còn trong máy: '+lost[0]+' (trang Video & âm thanh). Chưa bấm gì trên Studio.')
GROUP_GAP=30          # 4.2.0: the 2nd nick of a lịch nhóm starts 30 s later (one mouse)
MAX_NICKS=1          # 4.3.0 (owner): 1 nick; lịch nhóm hidden, code kept
def now_due(j):return time.time()>=j['start']
POSTPONE=1800        # 4.1.7: a hand-started LIVE at schedule time is ended and the schedule moves 30 minutes
# 4.2.0 (owner, 28/10/2026): the test LIVE that reset the cart (4.1.10–4.1.16) is gone.
# Strict cart rule: a sales LIVE starts ONLY with this schedule's own set added and
# re-checked (>0 products). No old cart, no fallback, unreadable = not ready.
RESET_HOLD=5
NO_RESET=re.compile('Nick trên Chrome khác|Không có bộ sản phẩm số|chưa chọn bộ|Không tìm thấy bộ|Chưa có đúng tab|mất kết nối|giữ giỏ tự thêm tay|Nick Chrome đã thay đổi',re.I)
PROBE_GAP=60         # 4.1.7: how often a nick waiting for its cart is looked at on Studio
class ChromeWait(ValueError):
 pass   # 4.3.4: Chrome LIVE is reopening / reloading the page: wait, not a failed attempt
STATE_LABELS={'start_retry':'Đang thử phát lại','stop_retry':'Đang thử kết thúc lại','pending':'Chờ đến giờ','preparing':'Đang chuẩn bị','starting':'Đang mở LIVE','running':'Đang LIVE','stopping':'Đang kết thúc','finished':'Đã kết thúc','failed':'Cần kiểm tra','attention':'Cần kiểm tra','manual_stop':'Đã dừng thủ công','skipped':'Đã bỏ lịch quá giờ','cancelled':'Đã hủy','recovery_review':'Cần kiểm tra sau khi mở lại app','recovering':'Đang kiểm tra'}

class StudioPanel(QWidget):
 def __init__(self,owner):
  super().__init__();self.owner=owner;self.setWindowTitle('NBL LIVE 4.3.16 · Lịch phát LIVE');self.resize(450,740)
  self.connection_checks={};self.probe_futures={};self.last_connection_probe=0;self.current_session_id='';self.controls={};self.path=owner.path.parent/'studio_schedules.json';self.pool=StudioWorker();self.futures={};self.profiles=[];self.jobs=[];self.library=[];self.stopped=False
  from studio_store import load as load_studio
  saved,self.recovery_notice=load_studio(self.path)
  self.profiles=saved['profiles'];self.controls=saved.get('controls',{}) if isinstance(saved.get('controls'),dict) else {}
  if not self.controls and self.profiles:self.controls={k:self.profiles[0][k] for k in CONTROL_FIELDS if self.profiles[0].get(k)}
  self.jobs=saved['jobs']
  self.auto_enabled=self.controls.get('autoHelpers',True) is not False
  # 4.1.5: carts marked ready by 4.1.4 or older may hold the PREVIOUS schedule's
  # products; prepare them again (replace with the schedule's own set).
  for j in self.jobs:
   if j.get('state') in ('pending','start_retry') and not j.get('no_sales') and (j.get('cart') or {}).get('state')=='ready' and not j['cart'].get('v415'):
    j['cart']=dict(state='none',attempts=0,next=0)
  self.library=[x for x in saved.get('library',[]) if isinstance(x,str)]
  for j in self.jobs:
   # 4.1: after a restart NBL checks Studio itself and resumes the automation.
   j.setdefault('cart',dict(state='none',attempts=0,next=0));j['cart'].pop('command',None);j['cart'].pop('kind',None)
   if j['cart'].get('state')=='preparing':j['cart']['state']='none'
   if j['state']=='skipped':j['skip_noted']=True
   if j['state'] in ('pending','start_retry') and (j['cart'].get('fallback') or j['cart'].get('state')=='ready' and not j['cart'].get('v420')):
    j['cart']=dict(state='none',attempts=0,next=0)     # 4.2.0: re-add under the strict rule
   # 4.1.10: closed in the middle of a test LIVE (reset giỏ) → first make sure it is off.
   if j['cart'].get('state') in ('resetting','reset_stopping'):j['cart'].update(state='reset_stopping',reset_stop_next=0)
   if j['state'] in ('preparing','start_retry'):j['state']='start_retry';j['retry_at']=0;j['start_attempts']=max(1,j.get('start_attempts',0))
   elif j['state'] in ('running','starting','recovering','attention','recovery_review'):j['state']='recovering';j['resume']=True;j['error']='App vừa mở lại: đang kiểm tra Studio rồi chạy tiếp'
   elif j['state'] in ('stopping','stop_retry'):j['state']='stop_retry';j['retry_at']=0
  if self.recovery_notice:
   self.owner.log(self.recovery_notice)
   QTimer.singleShot(0,lambda:QMessageBox.warning(self,'Đã khôi phục lịch Studio',self.recovery_notice))
  v=QVBoxLayout(self);notice=QLabel('Chọn nick ở đầu app. Kết nối cửa sổ LIVE Studio một lần; các nút đã chọn được dùng chung giữa các nick.');notice.setWordWrap(True);v.addWidget(notice)
  self.nick=QComboBox();self.nick.hide();v.addWidget(self.nick)
  self.connection_label=QLabel('Chưa kết nối LIVE Studio cho nick này');self.connection_label.setWordWrap(True);v.addWidget(self.connection_label)
  # 4.3.0: no "Kết nối" button — NBL opens/finds Studio and connects by itself (auto_connect).
  self.auto_at=0;self.auto_note=''
  from hold_button import HoldButton
  v.addWidget(HoldButton('🛑 Tắt LIVE nick này (giữ 2 giây)',self.emergency_current))
  self.start=QDateTimeEdit(QDateTime.currentDateTime().addSecs(300));self.end=QDateTimeEdit(QDateTime.currentDateTime().addSecs(3900))
  for label,w in [('Bắt đầu (giờ Windows)',self.start),('Kết thúc',self.end)]:v.addWidget(QLabel(label));w.setDisplayFormat('dd/MM/yyyy HH:mm:ss');w.setCalendarPopup(True);v.addWidget(w)
  self.clips=QListWidget();self.clips.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection);self.clips.hide()
  video_note=QLabel('Video: tới giờ, NBL cho cửa sổ NBL VIDEO đang mở của nick này PHÁT LẠI TỪ ĐẦU (video ở trang Video & âm thanh). Mở sẵn NBL VIDEO và gắn vào Studio trước. NBL không dừng, không đóng video.');video_note.setWordWrap(True);v.addWidget(video_note)
  for file in dict.fromkeys(self.library+[p for s in owner.data['sessions'] for p in s['playlist']]):self.clips.addItem(file)
  self.shuffle=QCheckBox();self.shuffle.hide()
  self.no_sales=QCheckBox('Phiên này không bán hàng');v.addWidget(self.no_sales)
  row=QHBoxLayout();row.addWidget(QLabel('Bộ sản phẩm số (1 = bộ đầu tiên trên Chrome)'));self.bundle_index=QSpinBox();self.bundle_index.setRange(0,200);self.bundle_index.setSpecialValueText('0 · giữ giỏ tự thêm tay');self.bundle_index.setValue(1);row.addWidget(self.bundle_index);v.addLayout(row)
  self.no_sales.toggled.connect(lambda on:self.bundle_index.setEnabled(not on))
  # 4.2.0 (owner, 28/10/2026): lịch nhóm — 2 nicks LIVE at the same time (max 2 per PC).
  self.group=QCheckBox('Lịch nhóm: phát CÙNG GIỜ thêm 1 nick nữa (tối đa 2 nick)');v.addWidget(self.group);self.group.hide()
  grow=QHBoxLayout();self.group_nick=QComboBox();self.group_bundle=QSpinBox();self.group_bundle.setRange(0,200);self.group_bundle.setValue(1);self.group_bundle.setSpecialValueText('0 · giỏ tay')
  grow.addWidget(QLabel('Nick 2'));grow.addWidget(self.group_nick,1);grow.addWidget(QLabel('bộ số'));grow.addWidget(self.group_bundle);self.group_box=QWidget();self.group_box.setLayout(grow);self.group_box.hide();v.addWidget(self.group_box)
  self.group.toggled.connect(lambda on:(self.group_box.setVisible(on),self.fill_group()))
  hint=QLabel('Giỏ hàng được chuẩn bị trên Chrome ngay khi lưu lịch (hoặc ngay sau phiên trước của nick): NBL XOÁ giỏ cũ rồi thêm đúng bộ số của lịch. Bộ số 0 = giữ nguyên giỏ bạn tự thêm tay. Thêm bộ lỗi thì NBL tải lại trang và thử lại suốt khung giờ; giỏ chưa xác nhận đúng bộ thì KHÔNG phát (xong lúc nào phát lúc đó), hết khung giờ thì bỏ lịch và báo Telegram.');hint.setWordWrap(True);v.addWidget(hint)
  b=QPushButton('Lưu lịch');b.clicked.connect(self.create_job);v.addWidget(b)
  self.list=QListWidget();v.addWidget(self.list);b=QPushButton('Hủy / kết thúc lịch đã chọn');b.clicked.connect(self.cancel);v.addWidget(b)
  b=QPushButton('Kiểm tra lại trạng thái lịch đã chọn');b.clicked.connect(self.recheck);v.addWidget(b)
  b=QPushButton('Gỡ liên kết nick đã chọn');b.clicked.connect(self.remove_profile);v.addWidget(b)
  self.status=QLabel('Sẵn sàng');self.status.setWordWrap(True);v.addWidget(self.status)
  self.mouse_path=owner.path.parent/'studio_mouse_allowed.txt'
  self.mouse_path.write_text('1',encoding='utf-8')
  for p in self.profiles:p['mousePermissionFile']=str(self.mouse_path)
  self.refresh_profiles();self.render();self.timer=QTimer(self);self.timer.timeout.connect(self.tick);self.timer.start(1000)
  if os.name=='nt':
   import threading
   from studio_cdp import fix_shortcuts
   def fix():self.icons_fixed=fix_shortcuts()   # logged from the Qt thread (auto_connect)
   threading.Thread(target=fix,daemon=True,name='studio-icons').start()
 def save(self):
  if not self.stopped:write_json(self.path,dict(profiles=self.profiles,controls=self.controls,jobs=self.jobs,library=[self.clips.item(i).text() for i in range(self.clips.count())]))
 def refresh_profiles(self):
  previous=self.nick.currentData();self.nick.blockSignals(True);self.nick.clear()
  for p in self.profiles:self.nick.addItem(p['name'],p['id'])
  selected=self.current_profile();index=self.nick.findData(selected['id'] if selected else previous);self.nick.setCurrentIndex(index);self.nick.blockSignals(False)
  self.connection_label.setText(self.connection_status())
 def connection_status(self):
  p=self.current_profile()
  if not p:return 'Chưa kết nối LIVE Studio'
  if p.get('cdp'):
   ok=self.connection_checks.get(p['id'],{})
   if time.monotonic()-ok.get('at',0)>20:return 'Studio: kết nối tự động · '+str(p.get('name',''))
   return 'Studio: kết nối tự động ✓ · '+str(p.get('name','')) if ok.get('ok') else 'Studio: chưa mở · NBL tự mở khi tới giờ phát'
  state=self.connection_checks.get(p['id'],{})
  if state.get('signature')!=(p.get('pid'),p.get('windowHandle'),p.get('exePath')) or time.monotonic()-state.get('at',0)>20:return 'Studio: đã lưu · chưa kiểm tra cửa sổ'
  return 'Studio: cửa sổ đang mở' if state.get('ok') else 'Studio: mất cửa sổ · kết nối lại'
 def poll_connection(self):
  for future,(key,signature) in list(self.probe_futures.items()):
   if not future.done():continue
   del self.probe_futures[future]
   try:ok=future.result().get('windowFound') is True
   except Exception:ok=False
   self.connection_checks[key]=dict(ok=ok,signature=signature,at=time.monotonic())
  if os.name=='nt' and time.monotonic()-self.last_connection_probe>=10:
   self.last_connection_probe=time.monotonic()
   busy={key for key,_ in self.probe_futures.values()}
   for p in self.profiles:
    if p['id'] not in busy:
     signature=(p.get('pid'),p.get('windowHandle'),p.get('exePath'))
     f=self.pool.submit_priority(50,execute,copy.deepcopy(p),'probe');self.probe_futures[f]=(p['id'],signature)
  self.connection_label.setText(self.connection_status())
 def set_session(self,session_id):
  if hasattr(self,'group'):QTimer.singleShot(0,self.fill_group)
  self.current_session_id=str(session_id);self.refresh_profiles();self.render()
 def current_profile(self):
  return next((p for p in self.profiles if p.get('session')==self.current_session_id),None)
 def effective_profile(self,p):
  return {**p,**{k:v for k,v in self.controls.items() if k in CONTROL_FIELDS},'accountAnchor':p.get('accountAnchor','')}
 def profile(self,key):return next((p for p in self.profiles if p['id']==key),None)
 def connect_current(self):self.edit_profile(False)
 def connect_auto(self):
  """4.2.1 (owner, 28/10/2026): NBL opens Studio itself and reads the nick from inside it."""
  session=next((s for s in self.owner.data['sessions'] if s['id']==self.current_session_id),None)
  if not session:QMessageBox.warning(self,'Chọn nick','Chọn nick ở đầu app trước.');return
  current=self.current_profile() or {}
  if current and any(j['profile']==current['id'] and j['state'] in ('preparing','starting','running','stopping','recovering') for j in self.jobs):QMessageBox.information(self,'Đang chạy','Nick này đang LIVE theo lịch; kết nối lại sau khi phiên kết thúc.');return
  if not current and len(self.profiles)>=2:QMessageBox.information(self,'Tối đa 2 nick','Bản này hỗ trợ 2 nick. Gỡ liên kết nick cũ trước.');return
  from studio_cdp import find_exe,BASE_PORT
  exe=find_exe(current.get('exePath') or next((q.get('exePath','') for q in self.profiles if q.get('exePath')),''))
  if not exe:
   exe,_=QFileDialog.getOpenFileName(self,'Chọn file TikTok LIVE Studio.exe','C:/Program Files','TikTok LIVE Studio (*.exe)')
   if not exe:return
  used={int(q['cdpPort']) for q in self.profiles if q.get('cdpPort') and q is not current}
  port=int(current.get('cdpPort') or next(p for p in range(BASE_PORT,BASE_PORT+50) if p not in used))
  probe=dict(cdp=True,cdpPort=port,exePath=exe,_otherPorts=sorted(used))
  self.status.setText('Đang mở TikTok LIVE Studio và chờ Studio tải xong (có thể mất 1–2 phút)… Không cần bấm gì.');self.connection_label.setText('Đang kết nối Studio tự động…')
  future=self.pool.submit_priority(20,execute,probe,'connect');timer=QTimer(self)
  def ready():
   if not future.done():return
   timer.stop();timer.deleteLater()
   try:r=future.result()
   except Exception as e:
    self.status.setText('Chưa kết nối được: '+str(e));QMessageBox.warning(self,'Kết nối Studio tự động',str(e));self.refresh_profiles();return
   nick=r.get('nickname','')
   if not nick:
    QMessageBox.information(self,'Vào màn hình phát','Studio đã mở và NBL đã kết nối được, nhưng Studio đang ở TRANG CHỦ nên chưa thấy tên nick.\n\nTrong Studio bấm nút "Phát LIVE" lớn ở trang chủ để vào màn hình phát (chưa lên sóng), rồi bấm lại "Kết nối Studio tự động".');self.status.setText('Vào màn hình phát của Studio rồi bấm Kết nối tự động lại.');return
   expected=session.get('chrome_binding',{}).get('account') or session.get('account') or ''
   if expected and not same_author(nick,expected) and QMessageBox.question(self,'Tên nick khác','Studio đang là nick "'+nick+'", nick đang chọn trong NBL là "'+expected+'". Vẫn gắn Studio này cho nick đang chọn?')!=QMessageBox.StandardButton.Yes:return
   if any(q is not current and q.get('cdpPort')==port for q in self.profiles):QMessageBox.warning(self,'Trùng','Cổng này đã gắn nick khác.');return
   value={**current,'id':current.get('id',uuid.uuid4().hex),'name':nick,'accountName':nick,'session':session['id'],'exePath':exe,'cdp':True,'cdpPort':port,
          'interaction':current.get('interaction',session.get('studio_interaction',{})),'allowMouse':current.get('allowMouse',True),'mousePermissionFile':str(self.mouse_path)}
   if current.get('name') and not same_author(current.get('name'),nick):value.pop('handle',None);value.pop('handle_for',None)   # 4.3.16: Studio đổi nick -> quên @ Chrome của nick cũ
   if current:self.profiles[self.profiles.index(current)]=value
   else:self.profiles.append(value)
   self.connection_checks.pop(value['id'],None);self.save();self.refresh_profiles();self.render()
   self.status.setText('Đã kết nối tự động: '+nick+(' · đang LIVE' if r.get('live') else '')+'. Không cần khoanh vùng. Từ giờ để NBL mở Studio (đừng mở bằng icon ngoài Desktop).')
   self.owner.log('Studio kết nối tự động: '+nick+' (cổng nội bộ '+str(port)+')')
  timer.timeout.connect(ready);timer.start(300)
 def add_clips(self):
  files,_=QFileDialog.getOpenFileNames(self,'Chọn clip','','Video (*.mp4 *.mov *.mkv *.avi *.webm)');existing={self.clips.item(i).text() for i in range(self.clips.count())}
  for f in files:
   if f not in existing:self.clips.addItem(f);existing.add(f)
  self.save()
 def edit_profile(self,new=False):
  session=next((s for s in self.owner.data['sessions'] if s['id']==self.current_session_id),None)
  if not session:QMessageBox.warning(self,'Chọn nick','Chọn nick ở đầu app trước.');return
  current=self.current_profile() or {};original={'allowMouse':True,'mousePermissionFile':str(self.mouse_path),**self.effective_profile(current)}
  busy_chat=hasattr(self.owner,'studio_chat') and any(self.owner.studio_chat.engine.state(p['id'])[kind] for p in self.profiles for kind in ('message','greeting'))
  # 4.1.4: a job stuck in "Cần kiểm tra" / "thử kết thúc lại" no longer blocks
  # re-connecting Studio (reconnecting is usually what fixes it).
  driving=any(j['state'] in ('preparing','starting','running','stopping','recovering') for j in self.jobs)
  if driving or busy_chat:QMessageBox.warning(self,'Đang chạy','Các nick dùng chung thiết lập nút. Kết thúc lịch LIVE và dừng nhắn tin, chào khách trước khi thay đổi các nút.');return
  if current and any(j['profile']==current['id'] and j['state'] in ('preparing','starting','running','stopping','recovering') for j in self.jobs):QMessageBox.warning(self,'Đang chạy','Kết thúc LIVE và dừng tin nhắn, chào khách trước khi chọn lại nút.');return
  dialog=QDialog(self);dialog.setWindowTitle('Kết nối TikTok LIVE Studio');dialog.resize(440,680);v=QVBoxLayout(dialog)
  info=QLabel('Chọn cửa sổ và các nút đang hiện; nút khác bổ sung sau. Các nút dùng chung, nick nhớ riêng. Chọn bằng ảnh: giữ kích thước Studio, không chọn số đồng hồ đang đổi.');info.setWordWrap(True);v.addWidget(info)
  windows=QComboBox();windows.setPlaceholderText('Chọn cửa sổ TikTok LIVE Studio');v.addWidget(windows);scan=QPushButton('Tìm cửa sổ TikTok LIVE Studio');v.addWidget(scan)
  point=QPushButton('Chọn cửa sổ bằng chuột · 4 giây');v.addWidget(point)
  last_error=[''];picking=[False]
  scroll=QScrollArea();scroll.setWidgetResizable(True);body=QWidget();f=QFormLayout(body);f.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows);scroll.setWidget(body);v.addWidget(scroll,1)
  fields={};rows={}
  account_name=QLineEdit(str(original.get('accountName') or session.get('chrome_binding',{}).get('account') or session.get('account') or ''));account_name.setObjectName('studioAccountName');account_name.setPlaceholderText('Ví dụ: NGỌC BẢO LONG AUTO');account_name.setMinimumHeight(36);f.addRow('Tên nick — gõ vào ô bên dưới',account_name)
  visual=QCheckBox('Chọn bằng ảnh khi Studio không đọc được nút');visual.setChecked(True);f.addRow(visual)
  for key in ('pid','windowTitle','exePath','windowHandle'):
   fields[key]=QLineEdit(str(original.get(key,'')));fields[key].hide()
  labels={'accountAnchor':'Ảnh tên nick — chọn trên Studio','liveIndicator':'Dấu hiệu đang LIVE — chọn biểu tượng cố định','startButton':'Nút Phát LIVE','startConfirm':'Nút xác nhận phát LIVE — nếu có','stopMenu':'Nút mở menu kết thúc — nếu có','stopButton':'Nút Kết thúc LIVE','stopConfirm':'Nút Kết thúc ngay — nếu có','summaryClose':'Nút đóng bảng tổng kết — nếu có','chatRegion':'Khung trò chuyện chính','chatInput':'Ô nhập tin nhắn','chatSend':'Nút gửi tin nhắn'}
  for key,label in labels.items():
   value=str(original.get(key,''));field=QLineEdit(value,body);field.hide();fields[key]=field
   row=QHBoxLayout();status=QLabel('Đã chọn ✓' if value else 'Chưa chọn'+(' · không bắt buộc' if key in OPTIONAL_FIELDS else ''));status.setWordWrap(True);rows[key]=status;row.addWidget(status,1);button=QPushButton('Chọn lại' if value else 'Chọn');row.addWidget(button);f.addRow(label,row)
   def choose(checked=False,target=field,label=label,status=status,button=button,target_key=key):
    profile={**original,**{k:w.text().strip() for k,w in fields.items()}}
    if picking[0]:output.setText('Đang chọn một nút khác. Đợi kết quả rồi chọn tiếp.');return
    if not profile.get('pid'):QMessageBox.information(dialog,'Chọn cửa sổ','Bấm Tìm cửa sổ TikTok LIVE Studio và chọn đúng nick trước.');return
    status.setText('Trong 4 giây, đưa chuột lên '+label.lower()+'…');button.setEnabled(False);picking[0]=True;windows.setEnabled(False);scan.setEnabled(False);point.setEnabled(False)
    future=self.pool.submit_priority(20,execute,profile,'pick',payload={'field':target_key,'visualFallback':visual.isChecked()});timer=QTimer(dialog)
    def ready():
     if not future.done():return
     timer.stop();button.setEnabled(True);picking[0]=False;windows.setEnabled(True);scan.setEnabled(True);point.setEnabled(True)
     try:result=future.result();target.setText(result['descriptor']);status.setText('Đọc được: '+str(result.get('name') or 'nút đã nhận diện'));button.setText('Chọn lại');last_error[0]=''
     except Exception as e:
      last_error[0]=str(e);message=explain_studio_error(e);status.setText(message);output.setText(message);self.owner.log('Chọn '+label+' thất bại: '+str(e))
    timer.timeout.connect(ready);timer.start(150)
   button.clicked.connect(choose)
  sample=QPushButton('Chọn ảnh mẫu nút thu cửa sổ trò chuyện');f.addRow(sample);sample_path=[original.get('collapseImage','')]
  sample_note=QLabel('Sau khi mở LIVE, app tự tìm nút thu cửa sổ trò chuyện bằng mẫu đã lưu. Chỉ bấm khi tìm thấy đúng một nút.');sample_note.setWordWrap(True);f.addRow(sample_note)
  def choose_sample():
   file,_=QFileDialog.getOpenFileName(dialog,'Ảnh mẫu nút thu trò chuyện','','Ảnh (*.png *.jpg *.jpeg *.bmp)')
   if file:
    from PySide6.QtGui import QImage
    image=QImage(file)
    if image.isNull() or not 8<=image.width()<=300 or not 8<=image.height()<=300:QMessageBox.information(dialog,'Ảnh mẫu nút','Chọn ảnh cắt sát nút thu trò chuyện, cạnh từ 8 đến 300 điểm ảnh. Không chọn ảnh cả màn hình.');return
    import shutil
    dest=self.path.parent/('studio_chat_collapse'+Path(file).suffix.lower());shutil.copy2(file,dest);sample_path[0]=str(dest);sample_note.setText('Đã lưu ảnh mẫu ✓')
  sample.clicked.connect(choose_sample)
  output=QLabel('Chọn cửa sổ rồi chọn các nút cần sử dụng.');output.setWordWrap(True);v.addWidget(output)
  def choose_window(index):
   selected=windows.itemData(index)
   if selected:
    for key in ('pid','windowTitle','exePath','windowHandle'):fields[key].setText(str(selected.get(key,'')))
  windows.currentIndexChanged.connect(choose_window)
  def scan_windows():
   if picking[0]:return
   picking[0]=True;windows.setEnabled(False);future=self.pool.submit(list_windows);scan.setEnabled(False);point.setEnabled(False);timer=QTimer(dialog)
   def ready():
    if not future.done():return
    timer.stop();scan.setEnabled(True);point.setEnabled(True);picking[0]=False;windows.setEnabled(True)
    try:
     windows.clear()
     for key in ('pid','windowTitle','exePath','windowHandle'):fields[key].clear()
     for window in future.result():windows.addItem(window['windowTitle'],window)
     choose_window(windows.currentIndex());output.setText('Chọn đúng cửa sổ của nick này.' if windows.count() else 'Chưa thấy TikTok LIVE Studio. Mở và đăng nhập app đó trước.')
    except Exception as e:last_error[0]=str(e);output.setText(explain_studio_error(e))
   timer.timeout.connect(ready);timer.start(200)
  scan.clicked.connect(scan_windows)
  def point_window():
   if picking[0]:return
   picking[0]=True;windows.setEnabled(False);point.setEnabled(False);scan.setEnabled(False);output.setText('Trong 4 giây, đưa chuột vào phần chính của TikTok LIVE Studio. Không bấm gì.')
   future=self.pool.submit_priority(20,window_from_pointer);timer=QTimer(dialog)
   def ready():
    if not future.done():return
    timer.stop();picking[0]=False;windows.setEnabled(True);point.setEnabled(True);scan.setEnabled(True)
    try:
     window=future.result();windows.addItem(window['windowTitle'],window);windows.setCurrentIndex(windows.count()-1);choose_window(windows.currentIndex());output.setText('Đã nhận cửa sổ. Gõ tên nick, chọn ảnh tên nick và các nút đang hiện.');last_error[0]=''
    except Exception as e:last_error[0]=str(e);output.setText(explain_studio_error(e))
   timer.timeout.connect(ready);timer.start(150)
  point.clicked.connect(point_window)
  copy_error=QPushButton('Sao chép lỗi kết nối');copy_error.clicked.connect(lambda:QApplication.clipboard().setText(last_error[0] or output.text()));v.addWidget(copy_error)
  check=QPushButton('Kiểm tra kết nối — không phát LIVE');v.addWidget(check)
  def check_link():
   if picking[0]:output.setText('Đợi chọn cửa sổ/nút xong rồi kiểm tra.');return
   profile={**original,**{k:w.text().strip() for k,w in fields.items()}};future=self.pool.submit_priority(20,execute,profile,'status');timer=QTimer(dialog)
   def ready():
    if not future.done():return
    timer.stop()
    try:r=future.result();output.setText('Đã kiểm tra cửa sổ và trạng thái ✓ · '+('Đang LIVE' if r.get('live') else 'Chưa phát LIVE'))
    except Exception as e:last_error[0]=str(e);output.setText(explain_studio_error(e));self.owner.log('Kiểm tra Studio: '+str(e))
   timer.timeout.connect(ready);timer.start(200)
  check.clicked.connect(check_link)
  save=QPushButton('Lưu kết nối');v.addWidget(save)
  def accept():
   if picking[0]:output.setText('Đợi chọn cửa sổ/nút xong rồi lưu.');return
   try:
    value={k:w.text().strip() for k,w in fields.items()}
    if not value['pid'].isdigit() or not value['exePath']:raise ValueError('Chọn cửa sổ TikTok LIVE Studio trước.')
    value['accountName']=account_name.text().strip()
    if not value['accountName']:raise ValueError('Gõ tên nick vào ô Tên nick ở đầu phần thiết lập.')
    expected=session.get('chrome_binding',{}).get('account') or session.get('account')
    if expected and not same_author(value['accountName'],expected):raise ValueError('Tên nick khác nick đang chọn ở đầu app: '+expected+'. Chọn đúng nick trước khi lưu.')
    if not value['accountAnchor']:raise ValueError('Chọn ảnh tên nick trên Studio để đối chiếu trước khi thao tác.')
    try:anchor=json.loads(value['accountAnchor'])
    except ValueError:anchor={'name':value['accountAnchor']}
    if anchor.get('kind')!='visual' and anchor.get('name') and not same_author(anchor['name'],value['accountName']):raise ValueError('Tên đọc trên Studio khác tên đã nhập. Chọn lại đúng tên nick.')
    if current and hasattr(self.owner,'studio_chat') and any(self.owner.studio_chat.engine.state(current['id'])[kind] for kind in ('message','greeting')):raise ValueError('Dừng tin nhắn và chào của nick này trước khi sửa kết nối.')
    if not current and len(self.profiles)>=2:raise ValueError('Bản này hỗ trợ 2 nick. Gỡ kết nối nick cũ trước khi thêm nick khác.')
    if any(p['id']!=current.get('id') and p.get('pid')==value['pid'] for p in self.profiles):raise ValueError('Cửa sổ này đã gắn với nick khác. Chọn đúng cửa sổ riêng cho nick đang dùng.')
    name=value['accountName']
    self.controls.update({k:value.get(k,'') for k in CONTROL_FIELDS});self.controls['collapseImage']=sample_path[0]
    value['vision']=copy.deepcopy(current.get('vision',{}))
    value.update(id=current.get('id',uuid.uuid4().hex),name=name,session=session['id'],interaction=current.get('interaction',session.get('studio_interaction',{})),allowMouse=current.get('allowMouse',True),mousePermissionFile=str(self.mouse_path))
    if current:self.profiles[self.profiles.index(current)]=value
    else:self.profiles.append(value)
    self.connection_checks.pop(value['id'],None)
    if not session.get('account'):
     session['account']=value['accountName'];self.owner.account.setText(value['accountName']);write_json(self.owner.path,self.owner.data);self.owner.refresh_list()
    self.save();self.refresh_profiles();dialog.accept()
   except Exception as e:QMessageBox.warning(dialog,'Kết nối',str(e))
  save.clicked.connect(accept);dialog.exec()
 def remove_profile(self):
  p=self.current_profile()
  if not p:return
  if any(j['profile']==p['id'] and j['state'] in ('pending','preparing','starting','running','stopping','recovering','attention') for j in self.jobs):QMessageBox.warning(self,'Đang có lịch','Hủy hoặc kết thúc lịch của nick trước khi gỡ liên kết.');return
  if hasattr(self.owner,'studio_chat'):
   for kind in ('message','greeting'):self.owner.studio_chat.engine.stop(p['id'],kind)
  self.profiles.remove(p);self.save();self.refresh_profiles()
 def fill_group(self):
  cur=self.current_profile();keep=self.group_nick.currentData();self.group_nick.clear()
  for q in self.profiles:
   if cur and q['id']==cur['id']:continue
   self.group_nick.addItem(str(q.get('accountName') or q.get('name') or q['id']),q['id'])
  i=self.group_nick.findData(keep)
  if i>=0:self.group_nick.setCurrentIndex(i)
 def check_nick(self,p):
  lacking=vision_missing(self.effective_profile(p))
  if lacking:raise ValueError(str(p.get('name',''))+': '+lacking)
  video_problem(self.session(p))
 def create_job(self):
  try:
   p=self.current_profile();clips=[]
   if not p:raise ValueError('Bấm Kết nối LIVE Studio cho nick đang chọn trước.')
   self.check_nick(p)
   start,end=self.start.dateTime().toSecsSinceEpoch(),self.end.dateTime().toSecsSinceEpoch()
   second=None
   if self.group.isChecked():
    second=self.profile(self.group_nick.currentData())
    if not second:raise ValueError('Lịch nhóm: chọn nick thứ 2 (nick đó phải kết nối LIVE Studio trước).')
    self.check_nick(second)
   plan=[(p,start,self.bundle_index.value())]+([(second,start+GROUP_GAP,self.group_bundle.value())] if second else [])
   for q,s0,_ in plan:
    nicks={o['profile'] for o in overlapping_other_nicks(self.jobs,q['id'],s0,end)}|{x['id'] for x,_,_ in plan if x is not q}
    if len(nicks)>=MAX_NICKS:raise ValueError('Bản này chỉ cho tối đa '+str(MAX_NICKS)+' nick LIVE cùng lúc trên một máy; giờ này đã có lịch của nick khác.')
   if (second or overlapping_other_nicks(self.jobs,p['id'],start,end)) and QMessageBox.question(self,'2 nick LIVE cùng lúc','Hai nick LIVE cùng giờ: hai NBL VIDEO cùng phát sẽ LẪN ÂM THANH nếu dùng chung một loa. Chọn thiết bị âm thanh riêng cho từng nick (ví dụ cáp ảo VB-Cable) hoặc tắt tiếng một phiên. Vẫn lưu lịch?')!=QMessageBox.StandardButton.Yes:return
   made=[];group=uuid.uuid4().hex[:8] if second else ''
   try:
    for q,s0,bundle in plan:
     j=add_job(self.jobs,q['id'],s0,end,clips,'',self.no_sales.isChecked(),self.shuffle.isChecked(),bundle);made.append(j)
     if group:j['group']=group
   except Exception:
    for j in made:self.jobs.remove(j)
    raise
   self.save();self.render()
   if second:self.status.setText('Đã lưu lịch nhóm: '+str(p.get('name',''))+' phát trước, '+str(second.get('name',''))+' phát sau '+str(GROUP_GAP)+' giây. Nick nào giỏ lỗi thì nick đó chờ/bỏ, nick kia vẫn phát.')
  except Exception as e:QMessageBox.warning(self,'Lịch',str(e))
 def selected_job(self):
  item=self.list.currentItem();return next((j for j in self.jobs if item and j['id']==item.data(Qt.ItemDataRole.UserRole)),None)
 def render(self):
  selected=self.selected_job();selected_id=selected['id'] if selected else None;self.list.clear();p=self.current_profile()
  for j in self.jobs:
   if not p or j['profile']!=p['id']:continue
   cart=j.get('cart',{});cart_text='' if j.get('no_sales') else ' · '+('giỏ tự thêm' if j.get('bundle_index')==0 else 'bộ '+str(j.get('bundle_index') or '?'))+': '+('đang tắt phiên phát thử cũ' if cart.get('state') in ('resetting','reset_stopping') else 'chờ phiên LIVE bật tay kết thúc' if (cart.get('probe') or {}).get('live') and cart.get('state')!='ready' else 'Chrome bận, chờ thêm giỏ' if cart.get('wait') and cart.get('state')=='none' else {'ready':'giỏ đã xác nhận' if cart.get('verified') else 'giỏ đã thêm, chờ kiểm tra lại','preparing':'đang thêm giỏ','failed':'thêm giỏ lỗi '+str(cart.get('attempts',0))+' lần, đang tự thử lại'}.get(cart.get('state'),'chờ thêm giỏ'))
   self.list.addItem(time.strftime('%d/%m %H:%M',time.localtime(j['start']))+' → '+time.strftime('%H:%M',time.localtime(j['end']))+' · '+STATE_LABELS.get(j['state'],j['state'])+cart_text+(' · nhóm' if j.get('group') else '')+(' · '+j.get('error','') if j.get('error') else ''))
   item=self.list.item(self.list.count()-1);item.setData(Qt.ItemDataRole.UserRole,j['id'])
   if j['id']==selected_id:self.list.setCurrentItem(item)
 def session(self,p):
  session=next(s for s in self.owner.data['sessions'] if s['id']==p['session'])
  account=session.get('chrome_binding',{}).get('account')
  if p.get('cdp'):
   # 4.3.0 (owner, 28/10/2026): "giakhanhdoxe" (TikTok @, read on TikTok Shop) and "Khánh Car
   # Auto" (display name, read in Studio) are the same nick: the pair is remembered the first
   # time both are seen; afterwards only another @ is refused.
   # 4.3.16 (chủ máy, 31/10/2026): cặp nhớ từ nick Studio cũ (Khánh Car Auto ↔ @giakhanhdoxe) làm nick mới
   # SĂN DEAL GIÁ RẺ (@bechaudethuong12) bị chặn mãi. Cặp giờ nhớ kèm tên nick Studio (handle_for): Studio đổi nick
   # hoặc cặp do bản cũ ghi (không có handle_for) thì ghép lại; cùng nick Studio mà Chrome là @ khác thì vẫn chặn.
   if account and p.get('handle') and p.get('handle_for')!=p.get('name'):
    old=p['handle'];p['handle']=account;p['handle_for']=p.get('name')
    if not same_author(old,account):self.owner.log(str(p.get('name',''))+': ghép lại Chrome @'+account+' (cặp cũ @'+old+' là của nick Studio trước).')
    try:self.save()
    except Exception:pass
   if account and not p.get('handle'):
    p['handle']=account;p['handle_for']=p.get('name')
    try:self.save()
    except Exception:pass
   if account and p.get('handle') and not same_author(account,p['handle']):raise ValueError('Chrome đang là @'+account+', không phải @'+p['handle']+' của nick này. Đăng nhập đúng nick trên TikTok Shop.')
   return session
  if account and not same_author(account,p['name']):raise ValueError('Nick Chrome đã thay đổi. Kết nối lại đúng cửa sổ LIVE Studio cho nick này trước.')
  return session
 def client(self,p):
  s=self.session(p);client=resolve_binding(s.get('chrome_binding'),self.owner.bridge.snapshot())
  if not client:
   # 4.3.4: NBL's own Chrome keeps the LIVE page by itself (opens / reloads the SAME tab).
   # A short miss (page reloading) is a wait, not a failure; Telegram only after 2 minutes.
   now=time.time();since=getattr(self,'chrome_missing_since',0) or now;self.chrome_missing_since=since
   opener=getattr(self.owner,'open_chrome',None)
   if opener and any(j['profile']==p['id'] and j['state'] in ('pending','start_retry','running') for j in self.jobs):
    try:opener(s)
    except Exception:pass
   if now-since>=120 and any(j['profile']==p['id'] and (j['state']=='running' or j['state'] in ('pending','start_retry') and j['start']-now<900) for j in self.jobs):
    state=getattr(self.owner,'live_chrome_state','')
    why={'login':'TikTok Shop đòi đăng nhập lại: đăng nhập đúng nick trong cửa sổ Chrome LIVE.','no_extension':'Trang LIVE trong Chrome LIVE chưa trả lời; NBL đang tự tải lại.'}.get(state,'NBL đang tự mở lại / tải lại Chrome LIVE.')
    try:self.owner.notifier.publish('studio:'+p['id']+':chrome','⚠ '+str(p.get('name',''))+' · Chrome LIVE chưa kết nối trang LIVE TikTok Shop hơn 2 phút. '+why)
    except Exception:pass
   raise ChromeWait('Chrome LIVE chưa sẵn sàng (đang mở / tải lại trang).') if now-since<120 else ValueError('Chưa có đúng tab Chrome/nick kết nối.')
  self.chrome_missing_since=0
  return s,client
 def submit(self,j,action,payload=None):
  p=self.profile(j['profile'])
  if action in ('stop','emergency_stop'):
   self.cancel_pending_starts(j)
   if hasattr(self.owner,'studio_chat'):
    for kind in ('message','greeting'):self.owner.studio_chat.engine.stop(j['profile'],kind)
  if not p:raise ValueError('Thiếu liên kết LIVE Studio')
  if any(key[0]==j['id'] and key[2]==action for key in self.futures.values()):return
  try:self.save()
  except OSError:
   if action not in ('stop','emergency_stop'):raise
   self.owner.log('Chưa lưu được lịch; vẫn gửi lệnh kết thúc Studio.')
  future=self.pool.submit_priority(0 if action in ('stop','emergency_stop','reset_stop','quit_studio') else 5 if action=='reset_live' else 10 if action=='start' else 25 if action=='close_summary' else 20,execute,dict(copy.deepcopy(self.effective_profile(p)),_otherHandles=[str(q.get('windowHandle','')) for q in self.profiles if q is not p and q.get('windowHandle')],_otherPorts=[q['cdpPort'] for q in self.profiles if q is not p and q.get('cdpPort')]),'status' if action in ('preflight','live_probe') else 'stop' if action=='reset_stop' else action,j['end'] if action=='start' else 0,payload);self.futures[future]=(j['id'],None,action)
 def notify(self,j,key,text,kind='loi',image=None):
  p=self.profile(j['profile']);name=p['name'] if p else j['profile']
  self.owner.log(name+' · '+text)
  try:self.owner.notifier.publish('studio:'+j['profile']+':'+key,name+' · '+text)
  except Exception:pass
  report(kind,name,text)
 def tick(self):
  if self.stopped:return
  self.poll_connection()
  now=time.time()
  try:
   for future,key in list(self.futures.items()):
    if not future.done():continue
    del self.futures[future];jid,widget,action=key
    if jid=='pick':
     try:widget.setText(future.result()['descriptor'])
     except Exception as e:
      try:widget.setPlaceholderText(str(e))
      except RuntimeError:pass
     continue
    if jid=='autoconnect':
     self.auto_connected(future,widget);continue
    if jid=='quitstudio':
     try:r=future.result() or {}
     except Exception as e:self.owner.log('Chưa tắt được TikTok LIVE Studio: '+str(e)[:200]);continue
     self.owner.log('Đã tắt hẳn TikTok LIVE Studio.' if r.get('closed') else 'Chưa tắt được TikTok LIVE Studio; tắt tay giúp NBL.')
     continue
    if jid=='chatdock':
     try:r=future.result() or {}
     except Exception:r={}
     if r.get('floating') and not r.get('docked') and r.get('found') is False:
      # 4.3.14: báo 1 lần (6 giờ mới nhắc lại), không dồn 5 lần như captcha; NBL tự lưu các nút của cửa sổ nổi
      msg=str(widget)+' · Cửa sổ Trò chuyện LIVE đang nổi, NBL chưa tự gộp được. AI vẫn đọc bình luận ở cửa sổ nổi. NBL đã lưu dữ liệu nút vào logs/khung_chat_noi.json để sửa; muốn gộp ngay thì bấm nút ghép trên cửa sổ đó 1 lần.'
      if self.owner.notifier.publish('chatdock:'+str(widget),msg,cooldown=6*3600):self.owner.log(msg)
     elif r.get('docked') and r.get('how'):self.owner.log(str(widget)+' · Đã tự ghép cửa sổ Trò chuyện LIVE về Studio.')
     continue
    if jid=='studiocaptcha':
     try:text=(future.result() or {}).get('captcha') or ''
     except Exception:text=''
     if text:
      msg=str(widget)+' · ⚠ CAPTCHA / XÁC MINH trong TikTok LIVE Studio — vào giải ngay: '+text
      if self.owner.notifier.alarm('captcha:studio:'+str(widget),msg):self.owner.log(msg);report('loi',str(widget),msg)
     continue
    if isinstance(jid,str) and jid.startswith('hand:'):
     self.hand_result(jid[5:],future);continue
    if jid=='inspect':
     try:widget.setPlainText(json.dumps(future.result(),ensure_ascii=False,indent=2))
     except RuntimeError:pass
     except Exception as e:
      try:widget.setPlainText(str(e))
      except RuntimeError:pass
     continue
    j=next((j for j in self.jobs if j['id']==jid),None)
    if not j:continue
    try:
     result=future.result()
     if result.get('pid'):self.profile(j['profile'])['pid']=str(result['pid'])
     if result.get('rebound'):
      prof=self.profile(j['profile']);prof.update(windowHandle=str(result['windowHandle']),windowTitle=result.get('windowTitle') or prof.get('windowTitle',''))
      self.owner.log('Studio đã mở lại; NBL tự nhận cửa sổ mới cho nick '+str(prof.get('name','')));self.save()
     if action=='preflight':
      if j['state']!='preparing':continue
      if result.get('warnings'):raise ValueError('Studio đang cảnh báo: '+str(result['warnings']))
      if result.get('live'):
       if j.get('start_attempts'):self.on_started(j,'Studio đã LIVE sau lần bấm trước; nhận lại phiên');continue
       if time.time()-(j.get('cart') or {}).get('reset_at',0)<180:raise ValueError('Phiên phát thử reset giỏ vừa tắt, Studio chưa về nút Phát LIVE; thử lại sau 30 giây')
       # 4.3.0 (owner, 28/10/2026): a LIVE started by hand at schedule time is TAKEN OVER
       # (runs until the schedule's end), never ended and moved any more.
       self.on_started(j,'Nick đang LIVE tay lúc tới giờ lịch: NBL nhận phiên này, chạy tới '+time.strftime('%H:%M',time.localtime(j['end'])));continue
      if not self.cart_ok(j):
       # 4.2.0: the hand LIVE seen earlier is over, but this schedule's cart is not
       # confirmed: back to waiting, never start.
       cart=j.setdefault('cart',dict(state='none',attempts=0,next=0));cart['probe']=dict(at=time.time(),live=False)
       j['state']='pending';j.pop('prepare_phase',None);j['error']='Chờ xác nhận giỏ đúng bộ của lịch mới phát';continue
      self.start_video(j)
     elif action=='live_probe':
      cart=j.setdefault('cart',dict(state='none',attempts=0,next=0));was=(cart.get('probe') or {}).get('live')
      cart['probe']=dict(at=time.time(),live=bool(result.get('live')))
      if cart['probe']['live'] and not was:self.owner.log(str(self.profile(j['profile']).get('name',''))+' · Nick đang LIVE (bật tay): chưa đụng giỏ, chờ phiên này kết thúc.')
     elif action in ('stop','emergency_stop'):
      if result.get('live'):raise ValueError('Chưa xác nhận LIVE đã kết thúc')
      if result.get('quit'):self.owner.log('Không kết thúc LIVE bằng nút được ('+str(result.get('why') or '')[:120]+') nên NBL đã TẮT HẲN TikTok LIVE Studio: nguồn phát đứt, LIVE dừng theo.')
      elif result.get('studioClosed'):self.owner.log('Không còn cửa sổ TikTok LIVE Studio nào: Studio đã tắt nên LIVE đã dừng.')
      if j.get('takeover'):self.postpone(j);continue
      self.on_stopped(j,studio_closed=bool(result.get('studioClosed')))
     elif action=='quit_studio':
      self.owner.log('Đã tắt hẳn TikTok LIVE Studio.' if result.get('closed') else 'Chưa tắt được TikTok LIVE Studio; tắt tay giúp NBL.')
     elif action=='start':
      if j['state']=='attention':continue
      if not result.get('live'):raise ValueError('Chưa xác nhận bắt đầu LIVE')
      if time.time()>=j['end'] or j['state']=='stopping':self.submit(j,'stop')
      else:self.on_started(j,'Đã phát LIVE' if not result.get('already') else 'Studio đã đang LIVE; nhận phiên')
     elif action in ('reset_live','reset_stop'):
      cart=j.setdefault('cart',dict(state='none',attempts=0,next=0))
      if result.get('live'):raise RuntimeError('Studio vẫn đang LIVE sau lệnh kết thúc phiên phát thử')
      self.reset_done(j,cart,action=='reset_live')
     elif action=='close_summary':
      if result.get('closed'):
       j.pop('summary_until',None);j.pop('summary_next',None)
       if result.get('seen'):self.owner.log(str(self.profile(j['profile']).get('name',''))+' · Đã đóng trang tổng kết LIVE trên Studio.')
     elif action=='collapse_chat':
      if not result.get('collapsed'):self.owner.log('Chưa thu được cửa sổ trò chuyện; các mục khác tiếp tục.')
     elif action=='status':
      if j['state'] not in ('running','recovering','attention','recovery_review'):continue
      if not result.get('live'):
       if j.get('takeover'):self.postpone(j);continue
       if result.get('studioClosed'):self.owner.log('Không còn cửa sổ TikTok LIVE Studio nào: Studio đã tắt nên LIVE đã dừng.')
       if j.get('dark_stop'):self.on_stopped(j);continue
       if j['state']=='attention' and (j.get('end_stop_attempted') or time.time()>=j['end']):
        self.on_stopped(j);continue
       j['state']='manual_stop';j['error']='LIVE đã dừng; không tự mở lại';self.stop_chrome(j);self.stop_owned_video(j,force=True);self.close_chrome_summary(j);self.watch_summary(j)
       self.notify(j,'ended','LIVE đã dừng ngoài lịch (bị tắt tay hoặc TikTok kết thúc); không tự mở lại.')
       continue
      if result.get('warnings'):raise ValueError('Studio đang cảnh báo: '+str(result['warnings']))
      if j['state']=='attention' and j.get('end_stop_attempted'):
       # Past its end and still LIVE: try to end it again every 3 minutes (one more
       # failure brings the "tắt tay" notice back), never resume the automation.
       j['state']='stop_retry';j['retry_at']=time.time()+180;j['stop_attempts']=max(j.get('stop_attempts',0),STOP_TRIES-1);continue
      if j['state'] in ('recovering','attention','recovery_review'):
       resume=j.pop('resume',False);j['state']='running';j['error']=''
       if resume:self.resume_automation(j)
      j['probe_failures']=0
      if j['state']=='running' and j.get('error','').startswith('Tạm chưa đọc được Studio'):j['error']=''
      self.watch_dark(j,result.get('health') or {})
    except Exception as e:
     self.action_failed(j,action,e)
   for j in self.jobs:
    try:
     if j['state']=='preparing' and j.get('prepare_phase')=='video':
      p=self.profile(j['profile']);session=self.session(p)
      try:video=json.loads((self.owner.path.parent/'runtime'/session['id']/'status.json').read_text(encoding='utf-8'))
      except (OSError,ValueError):video={}
      if video.get('state')=='PlayingState' and time.time()-video.get('time',0)<3 and video.get('time',0)>=j.get('video_sent',0) and int(video.get('position') or 0)<15000 and any(same_file(video.get('path',''),clip) for clip in session.get('playlist',[])):
       j['prepare_phase']='start';j['state']='starting';self.submit(j,'start')
      elif time.time()>j['video_until']:
       self.action_failed(j,'start',ValueError('NBL VIDEO chưa phát ổn định trong 20 giây (cửa sổ NBL VIDEO có đang mở không?)'))
    except Exception as e:
     self.action_failed(j,'start',e)
   self.poll_cart(now)
   self.poll_chrome_modules(now)
   self.poll_summary(now)
   self.poll_clip(now)
   self.poll_captcha(now)
   self.poll_emergency(now)
   self.poll_hand_live(now)
   self.auto_connect(now)
   self.poll_studio_captcha(now)
   self.poll_chat_dock(now)
   for j,action in decisions(self.jobs,time.time(),self.cart_ready):
    try:
     p=self.profile(j['profile'])
     if action=='prepare':
      s=self.session(p)
      video_problem(s)
      eff=self.effective_profile(p)
      # 4.1.2: Phát / Kết thúc LIVE only by reading the Studio image. The old 4.0.2
      # button path cannot see Studio's buttons ("LIVE state unknown"), so a nick
      # without image regions is refused with what to do, before anything is clicked.
      missing=vision_missing(eff)
      if missing:raise ValueError(missing)
      if not eff.get('cdp') and any(not eff.get(k) for k in ('exePath','windowTitle','accountAnchor')):raise ValueError('Chưa kết nối đủ LIVE Studio cho nick '+str(p.get('name') or '')+' (cửa sổ, ảnh tên nick): bấm Kết nối LIVE Studio. Chưa bấm gì trên Studio.')
      j['prepare_phase']='preflight';self.submit(j,'preflight')
     elif action=='stop':
      try:s,client=self.client(p);self.owner.bridge.command(client,dict(action='stop',module='all'))
      except Exception:pass
      self.submit(j,'stop')
     else:self.submit(j,'status',payload={'health':True})
    except Exception as e:self.action_failed(j,action if action!='prepare' else 'start',e)
   for j in self.jobs:
    if j['state']=='skipped' and not j.get('skip_noted'):
     j['skip_noted']=True;cart=j.get('cart') or {}
     why='giỏ chưa xác nhận được đúng bộ '+str(j.get('bundle_index'))+' (thử '+str(cart.get('attempts',0))+' lần)' if not j.get('no_sales') and not self.cart_ok(j) else (j.get('error') or 'không còn đủ thời gian')
     self.notify(j,'skip','⚠ BỎ LỊCH '+time.strftime('%H:%M',time.localtime(j['start']))+' → '+time.strftime('%H:%M %d/%m',time.localtime(j['end']))+': KHÔNG phát vì '+why+'. Lên lịch lại khi giỏ ổn.')
   signature=json.dumps(self.jobs,sort_keys=True)
   if signature!=getattr(self,'signature',''):self.save();self.render();self.signature=signature
  except Exception as e:self.owner.log('Lịch Studio: '+str(e))
 # ---------------- 4.1 schedule logic ----------------
 def action_failed(self,j,action,e):
  """Start problems are retried while the slot lasts; stop problems are retried
  STOP_TRIES times; a still-running LIVE is never silently left on."""
  now=time.time();text=str(e)
  if action=='close_summary':
   j['summary_next']=now+10;j['summary_error']=text;return
  if action in ('reset_live','reset_stop'):
   self.reset_failed(j,action,e,now);return
  if action=='live_probe':
   # Not known whether the nick is LIVE: carry on as before 4.1.7 (prepare the cart).
   cart=j.setdefault('cart',dict(state='none',attempts=0,next=0));cart['probe']=dict(at=now,live=None)
   self.owner.log('Chưa đọc được Studio để biết nick có đang LIVE không: '+text);return
  if action=='collapse_chat':self.owner.log('Chưa thu được cửa sổ trò chuyện; các mục khác tiếp tục.');return
  if isinstance(e,NotTouched) and action=='status' and j['state']=='running':
   j['probe_failures']=j.get('probe_failures',0)+1
   if j['probe_failures']<4:
    j['error']='Tạm chưa đọc được Studio ('+str(j['probe_failures'])+'/3): '+text;self.status.setText(j['error']);return
  if action in ('start','preflight') and j['state'] in ('preparing','starting','start_retry'):
   j['start_attempts']=j.get('start_attempts',0)+1
   if now<j['end']-START_MARGIN-RETRY_GAP:
    j['state']='start_retry';j['retry_at']=now+RETRY_GAP;j['error']='Phát LIVE chưa được (lần '+str(j['start_attempts'])+'), thử lại sau 30 giây: '+text
    self.notify(j,'start','Phát LIVE chưa được, lần '+str(j['start_attempts'])+'; tự thử lại sau 30 giây. Lý do: '+text)
   else:
    j['state']='failed';j['error']='Không phát được LIVE trong khung giờ: '+text;self.stop_owned_video(j,force=True)
    self.notify(j,'start','KHÔNG phát được LIVE sau '+str(j['start_attempts'])+' lần thử. Lý do cuối: '+text)
   self.status.setText(j['error']);return
  if action=='status' and j['state']=='attention':
   j['error']=j.get('error') or text;return     # silent: it is already reported
  if action=='quit_studio':
   self.owner.log('Chưa tắt được TikTok LIVE Studio: '+text);return
  if action in ('stop','emergency_stop'):
   j['stop_attempts']=j.get('stop_attempts',0)+1
   if j['stop_attempts']<STOP_TRIES:
    j['state']='stop_retry';j['retry_at']=now+RETRY_GAP;j['error']='Kết thúc LIVE chưa được (lần '+str(j['stop_attempts'])+'): '+text
    self.notify(j,'stop','Kết thúc LIVE chưa được, lần '+str(j['stop_attempts'])+'/'+str(STOP_TRIES)+'; thử lại sau 30 giây. Lý do: '+text)
   else:
    j['state']='attention';j['error']='LIVE CÓ THỂ VẪN ĐANG CHẠY: kết thúc thất bại '+str(STOP_TRIES)+' lần: '+text
    self.notify(j,'stop','⚠ LIVE CÓ THỂ VẪN ĐANG CHẠY. Đã thử kết thúc '+str(STOP_TRIES)+' lần không được. Tắt tay ngay! Lý do: '+text)
   self.status.setText(j['error']);return
  j['state']='attention' if action in ('start','stop','emergency_stop','status') else 'failed';j['error']=text;self.status.setText(text)
  if hasattr(self.owner,'studio_chat'):
   for kind in ('message','greeting'):self.owner.studio_chat.engine.stop(j['profile'],kind)
  self.notify(j,'status',text)
 def start_video(self,j):
  """4.1.2: replay the nick's OWN NBL VIDEO (already captured by Studio) from its
  first clip. The playlist is never replaced and the window is never re-created."""
  p=self.profile(j['profile']);session=self.session(p)
  video_problem(session);session['loop']=True
  self.warn_shared_audio(j,session)
  j['video_sent']=time.time();self.owner.command('play',False,session);j['prepare_phase']='video';j['video_until']=time.time()+20
  # 4.3.14: phát lại trong cửa sổ đang mở; phải mở cửa sổ mới (Studio chưa nhận hình) thì báo chủ máy
  from video_commands import LAST
  if LAST.get('redirected'):self.owner.log(str(p.get('name',''))+' · NBL VIDEO: dùng cửa sổ đang mở, phát lại từ đầu.')
  if LAST.get('opened'):
   msg=str(p.get('name',''))+' · ⚠ Không thấy cửa sổ NBL VIDEO nào đang mở nên NBL phải mở cửa sổ mới. Studio có thể chưa nhận hình cửa sổ mới: vào Studio chọn lại nguồn cửa sổ "NBL VIDEO".'
   self.owner.log(msg)
   try:self.owner.notifier.publish('video_new:'+str(p.get('id','')),msg)
   except Exception:pass
 def warn_shared_audio(self,j,session):
  """Two LIVEs on one PC: both NBL VIDEO windows playing to the same speaker are
  heard by both Studios (owner, 19/10/2026)."""
  others=[o for o in self.jobs if o['profile']!=j['profile'] and o['state'] in ('preparing','starting','running','recovering','stop_retry','attention')]
  for o in others:
   try:other=self.session(self.profile(o['profile']))
   except Exception:continue
   if not session.get('mute') and not other.get('mute') and str(session.get('device',''))==str(other.get('device','')):
    self.notify(j,'audio','2 phiên LIVE cùng lúc đang dùng CHUNG một loa/thiết bị âm thanh ("'+(str(session.get('device','')) or 'mặc định')+'"): tiếng 2 video sẽ lẫn vào nhau. Chọn thiết bị âm thanh riêng cho từng NBL VIDEO (ví dụ VB-Cable) hoặc tắt tiếng 1 phiên.','loi')
 def on_started(self,j,text):
  j['state']='running';j['error']='';j['start_attempts']=0;j['started_at']=time.time();j['dark_since']=0;j['dark_restarted']=False;j['dark_stop']=False
  self.notify(j,'started',text,'hoat_dong')
  self.resume_automation(j)
 def resume_automation(self,j):
  p=self.profile(j['profile'])
  if hasattr(self.owner,'studio_chat'):
   cfg=p.get('interaction',{})
   for kind in ('message','greeting'):
    if cfg.get('auto_'+kind):
     try:self.owner.studio_chat.engine.enable(self.effective_profile(p),kind,cfg)
     except Exception as e:self.owner.log('Studio '+kind+': '+str(e))
  ai=getattr(self.owner,'ai',None)
  if ai and getattr(self,'auto_enabled',True):
   try:ai.start(self.effective_profile(p))
   except Exception as e:self.owner.log('AI: '+str(e))
  # Chrome's dashboard follows Studio a few seconds later; start pin/reply then.
  j['chrome_start_at']=time.time()+10;j['chrome_tries']=0
  if not p.get('vision',{}).get('enabled') and not p.get('cdp'):
   try:
    future=self.pool.submit_priority(25,execute,copy.deepcopy(self.effective_profile(p)),'collapse_chat',min(j['end'],time.time()+15));self.futures[future]=(j['id'],None,'collapse_chat')
   except Exception as e:self.owner.log('Thu cửa sổ trò chuyện: '+str(e))
 def on_stopped(self,j,studio_closed=False):
  dark=j.get('dark_stop')
  j['state']='finished';j['error']='Tự kết thúc vì màn hình đen' if dark else '';self.stop_owned_video(j,force=True);self.stop_chrome(j);self.close_chrome_summary(j);self.watch_summary(j)
  # 4.3.9 (chủ máy, 31/10/2026): kết thúc LIVE xong thì đóng hẳn ứng dụng Studio luôn,
  # không bấm dấu X (captcha che màn hình là bấm X không được).
  if not studio_closed:
   try:self.submit(j,'quit_studio')
   except Exception as e:self.owner.log('Chưa gửi được lệnh tắt Studio: '+str(e)[:150])
  if j.get('emergency'):self.owner.log(str((self.profile(j['profile']) or {}).get('name',''))+' · Đã tắt LIVE (TẮT KHẨN CẤP).');return
  self.notify(j,'stopped','Đã kết thúc LIVE'+(' (vì màn hình đen quá 2 phút)' if dark else ' theo lịch'),'hoat_dong')
 def watch_dark(self,j,health):
  """Black screen = Studio shows FPS 0 or upload 0 kbps while LIVE. Telegram at
  once, restart NBL VIDEO from the first clip once, end the LIVE after 2 min."""
  if j['state']!='running' or time.time()-j.get('started_at',0)<20:return
  dark=health.get('fps')==0 or health.get('upload')==0
  if not dark:
   if j.get('dark_since'):self.notify(j,'dark','Hình LIVE đã có lại (FPS '+str(health.get('fps'))+', tải lên '+str(health.get('upload'))+' kbps).','hoat_dong')
   j['dark_since']=0;return
  now=time.time()
  if not j.get('dark_since'):
   j['dark_since']=now
   self.notify(j,'dark','⚠ LIVE đang phát MÀN HÌNH ĐEN (FPS '+str(health.get('fps'))+', tải lên '+str(health.get('upload'))+' kbps). Đang cho NBL VIDEO phát lại từ đầu.')
  if not j.get('dark_restarted'):
   j['dark_restarted']=True
   try:session=self.session(self.profile(j['profile']));session['loop']=True;self.owner.command('play',False,session)
   except Exception as e:self.owner.log('Phát lại NBL VIDEO: '+str(e))
  elif now-j['dark_since']>=120 and not j.get('dark_stop'):
   j['dark_stop']=True;j['state']='stopping';self.stop_chrome(j)
   self.notify(j,'dark','Màn hình đen quá 2 phút: TỰ KẾT THÚC LIVE.')
   self.submit(j,'stop')
 def poll_chrome_modules(self,now):
  for j in self.jobs:
   if j['state']!='running' or not j.get('chrome_start_at') or now<j['chrome_start_at']:continue
   try:
    p=self.profile(j['profile']);session,client=self.client(p);snap=self.owner.bridge.snapshot().get(client,{})
    modules=snap.get('modules',{});acks=snap.get('ackErrors',{}) or {}
    why=lambda m:str((modules.get(m) or {}).get('error') or acks.get(m) or '')
    # 4.1.3: no reply rules on Chrome = the owner does not use auto-reply; not an error.
    if not j.get('reply_skipped') and re.search('Chưa có câu trả lời|Chưa có quy tắc',why('reply')):
     j['reply_skipped']=True;self.owner.log('Trả lời bình luận: chưa có quy tắc trên Chrome; bỏ qua, chỉ bật ghim.')
    want=[] if j['no_sales'] else ['pin']      # 4.3.0: comments are answered in Studio (AI), not on Chrome
    if all((modules.get(m) or {}).get('running') for m in want):j.pop('chrome_start_at',None);continue
    if j.get('chrome_tries',0)>=3:
     names={'pin':'Ghim','reply':'Trả lời'}
     j.pop('chrome_start_at',None);self.notify(j,'chrome','Chrome chưa bật được '+', '.join(names[m] for m in want if not (modules.get(m) or {}).get('running'))+' sau 3 lần: '+'; '.join(names[m]+': '+(why(m) or 'chưa chạy, xem nhật ký Chrome') for m in want if not (modules.get(m) or {}).get('running')));continue
    j['chrome_tries']=j.get('chrome_tries',0)+1;j['chrome_start_at']=now+20
    self.start_chrome_modules(j)
   except Exception as e:
    j['chrome_tries']=j.get('chrome_tries',0)+1;j['chrome_start_at']=now+20
    if j['chrome_tries']>=3:j.pop('chrome_start_at',None);self.notify(j,'chrome','Chrome chưa sẵn sàng: '+str(e))
 def start_chrome_modules(self,j,include_pin=True):
  p=self.profile(j['profile']);session,client=self.client(p)
  for module in (('pin',) if include_pin and not j['no_sales'] else ()):
   config=self.owner.pin_command_config(session) if hasattr(self.owner,'pin_command_config') else {}
   try:self.owner.bridge.command(client,dict(action='start',module=module,config=config,expectedAccount=session.get('chrome_binding',{}).get('account') or p['name']))
   except Exception as e:self.owner.log('Chrome '+module+': '+str(e))
 # ---- cart (giỏ hàng) prepared on Chrome BEFORE the LIVE ----
 def cart_ready(self,j):
  """decisions() gate: a sales LIVE starts only with a ready, re-checked cart."""
  if j['no_sales']:return True
  cart=j.setdefault('cart',dict(state='none',attempts=0,next=0))
  if self.cart_ok(j):return True
  # A LIVE started by hand: preflight only ends it and moves the schedule 30 minutes;
  # preflight re-checks the cart before any start (never a start on this path alone).
  if (cart.get('probe') or {}).get('live') is True:return True
  if not cart.get('waiting_noted'):
   cart['waiting_noted']=True;j['error']='Chờ xác nhận giỏ đúng bộ của lịch (>0 sản phẩm) mới phát'
  if now_due(j) and not cart.get('due_noted'):
   cart['due_noted']=True
   self.notify(j,'cart','Tới giờ LIVE '+time.strftime('%H:%M',time.localtime(j['start']))+' nhưng giỏ CHƯA xác nhận đúng bộ '+str(j.get('bundle_index'))+': CHƯA PHÁT. NBL tải lại trang và thử tiếp tới hết khung giờ; xong lúc nào phát lúc đó.')
  return False
 def cart_ok(self,j):
  """4.2.0 strict rule: added by THIS schedule (this bundle), re-checked with >0 products."""
  if j.get('no_sales'):return True
  cart=j.get('cart') or {}
  return (cart.get('state')=='ready' and cart.get('verified') is True and cart.get('v420') is True and not cart.get('fallback')
          and cart.get('for_bundle')==int(j.get('bundle_index') or 0) and int(cart.get('count') or 0)>0)
 def poll_cart(self,now):
  busy={j['profile'] for j in self.jobs if j['state'] in ACTIVE}
  nexts={}
  for j in sorted(self.jobs,key=lambda j:j['start']):
   if j['state'] in ('pending','start_retry') and j['profile'] not in nexts:nexts[j['profile']]=j
  for profile,j in nexts.items():
   # Only the NEXT LIVE of each nick. A no-sales LIVE next means no cart now
   # (it would end up in that LIVE), and never add while that nick is LIVE.
   if j['no_sales'] or (profile in busy and j['state']=='pending'):continue
   cart=j.setdefault('cart',dict(state='none',attempts=0,next=0))
   try:
    if cart.get('command'):
     p=self.profile(profile);session,client=self.client(p);result=self.owner.bridge.snapshot().get(client,{}).get('control',{})
     if result.get('id')==cart['command'] and result.get('state') in ('done','failed'):
      kind=cart.pop('kind');cart.pop('command',None)
      if kind=='fallback':continue     # 4.2.0: no fallback any more (old saved command)
      if kind=='check':
       try:count=int(float(result.get('count','-1')))
       except ValueError:count=-1
       if count>0 and cart['state']=='ready':cart.update(verified=True,count=count);j['error']='' if j['error'].startswith('Chờ') else j['error']
       elif count<0:
        cart['check_next']=now+15     # unreadable: not confirmed, look again (4.2.0)
        if not cart.get('unreadable_noted'):cart['unreadable_noted']=True;self.owner.log('Không đọc được số sản phẩm trong giỏ; chưa xác nhận, kiểm tra lại sau 15 giây.')
       else:
        cart.update(state='none',verified=False,attempts=max(cart.get('attempts',0),2),next=0)
        self.notify(j,'cart','Giỏ trên Chrome đang TRỐNG trước giờ phát (có thể bị TikTok xoá); '+('thêm lại bộ số '+str(j.get('bundle_index')) if j.get('bundle_index') else 'lịch chọn giữ giỏ tự thêm tay: hãy thêm sản phẩm')+'.')
      elif result['state']=='done':
       # 4.2.0: added = not yet confirmed; a cart_check (>0) confirms it before the LIVE.
       cart.update(state='ready',attempts=0,verified=False,v415=True,v420=True,for_bundle=int(j.get('bundle_index') or 0),count=0,ready_at=now,check_next=0);cart.pop('due_noted',None);j.pop('script_check',None)
       detail='giỏ đã có sẵn sản phẩm, bỏ qua thêm' if result.get('skipped') else 'đã thêm '+str(result.get('added','?'))+'/'+str(result.get('total','?'))+' · '+str(result.get('bundle',''))
       self.notify(j,'cart','Giỏ hàng sẵn sàng cho LIVE '+time.strftime('%H:%M %d/%m',time.localtime(j['start']))+': '+detail,'hoat_dong')
      else:self.cart_failed(j,cart,result.get('error','Chưa thêm được bộ sản phẩm'),now,transient=bool(result.get('busy')))
     elif now>cart.get('until',0):
      kind=cart.pop('kind',None);cart.pop('command',None)
      if kind=='check':cart['verified']=False
      elif kind=='fallback':pass
      else:self.cart_failed(j,cart,'Chrome chưa trả lời lệnh thêm giỏ',now)
     continue
    if cart['state']=='reset_stopping':
     if now>=cart.get('reset_stop_next',0) and not any(key[0]==j['id'] and key[2] in ('reset_live','reset_stop') for key in self.futures.values()):
      cart['reset_stop_next']=now+15;self.submit(j,'reset_stop')
     continue
    if cart['state']=='resetting':
     if not any(key[0]==j['id'] and key[2]=='reset_live' for key in self.futures.values()):cart.update(state='reset_stopping',reset_stop_next=0)
     continue
    if cart['state'] in ('none','failed') and now>=cart.get('next',0):
     # 4.1.7: never touch the cart while this nick is LIVE (also a LIVE started by
     # hand): look at Studio first, at most once a minute.
     probe=cart.get('probe') or {}
     if any(key[0]==j['id'] and key[2]=='live_probe' for key in self.futures.values()):continue
     if now-probe.get('at',0)>=PROBE_GAP:
      self.submit(j,'live_probe');continue
     if probe.get('live'):continue
     p=self.profile(profile);session,client=self.client(p)
     # 4.1.9 (owner, 26/10/2026): reload the LIVE page before adding the cart (old
     # boxes and a stale page made the cart fail); the add follows 20 s later.
     if now-cart.get('reloaded_at',0)>120:
      self.owner.bridge.command(client,dict(action='reload_page',module='all',stopModules=True))
      cart.update(reloaded_at=now,next=now+20);continue
     # 4.1.8: pin/reply left switched on after a LIVE made Chrome refuse every cart
     # ("đang bận") for ever. No NBL LIVE of this nick is on and Studio is not LIVE.
     cart['command']=self.owner.bridge.command(client,dict(action='prepare_bundle',stopModules=True,module='all',bundleIndex=int(j.get('bundle_index') or 0),keepCart=j.get('bundle_index')==0,replace=j.get('bundle_index')!=0,preLive=True,expectedAccount=session.get('chrome_binding',{}).get('account') or p['name']))
     cart.update(kind='add',until=now+160,state='preparing');cart.pop('wait',None)
    elif cart['state']=='ready' and not cart.get('verified') and not cart.get('pre_reload') and j['start']-180<=now<j['start']-60:
     # Never reload under a LIVE the owner started by hand (look at Studio first).
     probe=cart.get('probe') or {}
     if now-probe.get('at',0)>=PROBE_GAP:
      if not any(key[0]==j['id'] and key[2]=='live_probe' for key in self.futures.values()):self.submit(j,'live_probe')
      continue
     cart['pre_reload']=True
     if not probe.get('live') and now-cart.get('reloaded_at',0)>120:
      p=self.profile(profile);session,client=self.client(p)
      self.owner.bridge.command(client,dict(action='reload_page',module='all',stopModules=True));cart['reloaded_at']=now
    elif cart['state']=='ready' and not cart.get('verified') and now>=j['start']-120 and now-cart.get('reloaded_at',0)>=15 and now>=cart.get('check_next',0):
     p=self.profile(profile);session,client=self.client(p)
     cart['command']=self.owner.bridge.command(client,dict(action='cart_check',module='all'));cart.update(kind='check',until=now+20)
   except Exception as e:
    if cart.get('command'):
     # 4.1.8: the Chrome tab could not even be found while waiting (page reloading,
     # nick unreadable) → this used to wait for ever ("không tự thử lại").
     if now<=cart.get('until',0):continue
     kind=cart.pop('kind',None);cart.pop('command',None)
     if kind in ('check','fallback'):continue
    if now>=cart.get('next',0):self.cart_failed(j,cart,str(e),now,transient=isinstance(e,ChromeWait))
 def cart_failed(self,j,cart,reason,now,transient=False):
  # 4.1.3: Chrome still busy (pin/reply of the LIVE that just ended, another cart
  # job) is not a failed attempt: try again in 20 s. Real failures are retried after
  # 1 minute when the LIVE is near (5 minutes otherwise), at most 3 times.
  if transient:
   cart.update(state='none',next=now+20,wait='Chrome đang bận');self.owner.log('Giỏ hàng: Chrome đang bận ('+reason+'); thử lại sau 20 giây.');return
  # 4.1.8 (owner, 25/10/2026: "không tự thử lại"): no limit any more — keep trying
  # until the LIVE (1 minute apart when it is near, 3 minutes otherwise); tell the
  # owner on the 1st failure and then every 5th, not every time.
  gap=60 if j['start']-now<900 else 180
  cart['attempts']=cart.get('attempts',0)+1;cart.update(state='failed',next=now+gap)
  # 4.2.0: the next try reloads the TikTok Shop page first (reloaded_at is cleared;
  # reloading only happens after Studio was seen NOT LIVE).
  cart['reloaded_at']=0
  text='Thêm giỏ hàng chưa được (lần '+str(cart['attempts'])+'): '+reason+'; tải lại trang và thử lại sau '+('1 phút' if gap==60 else '3 phút')
  if cart['attempts']==1 or cart['attempts']%5==0:self.notify(j,'cart',text)
  else:self.owner.log(text)
 def close_chrome_summary(self,j):
  try:p=self.profile(j['profile']);session,client=self.client(p);self.owner.bridge.command(client,dict(action='finish_live',module='all',expectedAccount=session.get('chrome_binding',{}).get('account') or p['name']))
  except Exception as e:self.owner.log('Đóng bảng tổng kết Chrome: '+str(e))
 def end_hand_live(self,j):
  # 4.1.7 (owner, 21/10/2026): the nick is still in a LIVE the owner started by hand
  # when a schedule is due → NBL ends that LIVE and moves the schedule 30 minutes
  # later (default rule). The cart is prepared again once the LIVE is over.
  j['takeover']=True;j['state']='stopping';j['error']='Nick đang LIVE bật tay lúc tới giờ lịch: NBL kết thúc phiên đó rồi dời lịch 30 phút'
  self.notify(j,'takeover','Tới giờ lịch '+time.strftime('%H:%M',time.localtime(j['start']))+' mà nick đang LIVE bật tay: NBL kết thúc phiên đó và dời lịch 30 phút.')
  self.stop_chrome(j);self.submit(j,'stop')
 def postpone(self,j,now=None):
  now=time.time() if now is None else now
  length=j['end']-j['start'];start=now+POSTPONE;end=start+length
  later=[o['start'] for o in self.jobs if o is not j and o['profile']==j['profile'] and o['state'] in ('pending','start_retry') and o['start']>=j['start']]
  if later and end>min(later)-60:end=min(later)-60
  self.stop_chrome(j);self.close_chrome_summary(j);self.watch_summary(j)
  for key in ('takeover','start_attempts','stop_attempts','end_stop_attempted','retry_at','prepare_phase','video_sent','video_until','last_probe'):j.pop(key,None)
  j['postponed']=j.get('postponed',0)+1;j['cart']=dict(state='none',attempts=0,next=0);j.pop('script_check',None)
  if end-start<120:
   j['state']='skipped';j['skip_noted']=True;j['error']='Đã kết thúc phiên LIVE bật tay; không còn chỗ để dời lịch (vướng lịch sau)'
   self.notify(j,'takeover','Đã kết thúc phiên LIVE bật tay. Không dời được lịch vì vướng lịch sau của nick; bỏ lịch này.');return
  j['start'],j['end']=start,end;j['state']='pending';j['error']='Đã dời 30 phút vì nick đang LIVE bật tay'
  self.notify(j,'takeover','Đã kết thúc phiên LIVE bật tay. Lịch dời sang '+time.strftime('%H:%M',time.localtime(start))+' → '+time.strftime('%H:%M',time.localtime(end))+'; giỏ được chuẩn bị lại.','hoat_dong')
 def reset_done(self,j,cart,clean):
  # Back to adding the cart at once, on a freshly reloaded page; Studio is not LIVE.
  now=time.time();cart.update(state='none',next=now,reloaded_at=0,probe=dict(at=now,live=False),reset_at=now,reset_stop_tries=0,wait='')
  self.notify(j,'cart','Đã phát thử và kết thúc LIVE để reset giỏ'+('' if clean else ' (kiểm tra lại: Studio đã tắt)')+'; đang tải lại trang Chrome và thêm giỏ lại.','hoat_dong')
  self.close_chrome_summary(j);self.watch_summary(j)
 def reset_failed(self,j,action,e,now):
  cart=j.setdefault('cart',dict(state='none',attempts=0,next=0))
  if action=='reset_live' and getattr(e,'touched',True) is False:
   # Nothing was clicked (Studio not readable / already LIVE): normal retry.
   cart.update(state='failed',next=now+60);self.owner.log('Phát thử reset giỏ chưa làm được (chưa bấm gì): '+str(e));return
  # Phát LIVE may have been pressed: make sure the test LIVE is off, every 15 s.
  cart['reset_stop_tries']=cart.get('reset_stop_tries',0)+1;cart.update(state='reset_stopping',reset_stop_next=now+(0 if action=='reset_live' else 15))
  if cart['reset_stop_tries']>=8 and getattr(e,'touched',True) is False:
   # Studio cannot even be read for 2 minutes: say so loudly and go back to adding.
   cart.update(state='failed',next=now+60,reset_stop_tries=0)
   self.notify(j,'cart','⚠ Không đọc được Studio sau phiên phát thử reset giỏ. KIỂM TRA TAY xem Studio còn LIVE không! NBL quay lại thêm giỏ: '+str(e));return
  if cart['reset_stop_tries'] in (1,4) or cart['reset_stop_tries']%20==0:
   self.notify(j,'cart',('⚠ PHIÊN PHÁT THỬ CÒN ĐANG CHẠY? ' if cart['reset_stop_tries']>=4 else 'Phát thử reset giỏ trục trặc; ')+'NBL đang kiểm tra và tắt LIVE thử (lần '+str(cart['reset_stop_tries'])+'): '+str(e)+('. Tắt tay trên Studio nếu còn LIVE!' if cart['reset_stop_tries']>=4 else ''))
 def poll_captcha(self,now):
  # 4.1.16 (owner, 27/10/2026): a captcha on the nick's Chrome LIVE page → Telegram 5 times
  # in a row (the notifier sends at most one such burst per nick every 5 minutes).
  try:snap=self.owner.bridge.snapshot()
  except Exception:return
  for p in self.profiles:
   try:
    session,client=self.client(p)
    text=(snap.get(client) or {}).get('captcha') or ''
    if not text:continue
    msg=str(p.get('name',''))+' · ⚠ CAPTCHA / XÁC MINH trên Chrome (TikTok Shop) — vào giải ngay: '+text
    if self.owner.notifier.alarm('captcha:chrome:'+p['id'],msg):self.owner.log(msg);report('loi',p.get('name',''),msg)
   except Exception:pass
 def watch_summary(self,j):
  # 4.1.9 (owner, 26/10/2026): after EVERY LIVE end — another schedule or not — keep
  # looking at Studio for ~2.5 minutes and close its end page ("tab cuối cùng").
  p=self.profile(j['profile'])
  if not p or not (p.get('vision',{}).get('enabled') or p.get('cdp')):return
  now=time.time();j['summary_until']=now+150;j['summary_next']=now+2;j.pop('summary_error',None)
 def poll_summary(self,now):
  for j in self.jobs:
   if not j.get('summary_until'):continue
   if now>j['summary_until']:
    j.pop('summary_until',None);j.pop('summary_next',None)
    if j.get('summary_error'):self.notify(j,'summary','Chưa đóng được trang tổng kết LIVE trên Studio: '+str(j.pop('summary_error'))+'. Đóng tay giúp.')
    continue
   if now<j.get('summary_next',0):continue
   # Never while this nick's Studio is being driven (a new LIVE closes the page itself).
   if any(o['profile']==j['profile'] and o['state'] in ('preparing','starting','running','stopping','recovering') for o in self.jobs):continue
   if any(k[0]==j['id'] and k[2]=='close_summary' for k in self.futures.values()):continue
   j['summary_next']=now+3
   # Short looks (8 s) so a start/stop of another nick never waits long behind it.
   try:self.submit(j,'close_summary',payload={'wait':8})
   except Exception as e:j['summary_next']=now+10;j['summary_error']=str(e)
 def poll_clip(self,now):
  # 4.1.9/4.1.11: every 10 s each nick's Chrome gets the NBL VIDEO position and the
  # "kịch bản ghim giỏ hàng" of the clip that is playing (made in the app). Also for
  # a LIVE started by hand: the script follows the real clip, not the schedule.
  import pin_scripts
  store=pin_scripts.Store(self.owner.path.parent/'kich_ban_ghim.json')
  sent=getattr(self,'clip_sync_at',None)
  if sent is None:sent=self.clip_sync_at={}
  for p in self.profiles:
   if now-sent.get(p['id'],0)<10:continue
   sent[p['id']]=now
   try:
    session,client=self.client(p)
    video=json.loads((self.owner.path.parent/'runtime'/session['id']/'status.json').read_text(encoding='utf-8'))
    if now-float(video.get('time',0))>5:continue
    msg=pin_scripts.sync_payload(store,video);self.owner.bridge.command(client,msg)
    if not hasattr(self,'sync_info'):self.sync_info={}
    self.sync_info[p['session']]=dict(at=now,clip=msg['clip'],flags=len(msg['script']))   # shown in the clip list
   except Exception:pass
 def stop_owned_video(self,j,force=False):
  # 4.1.2 (owner, 19/10/2026 02:40): NBL never stops the owner's video. A stopped
  # NBL VIDEO is a black picture in Studio; the next LIVE replays it from the start.
  return
 def recheck(self):
  j=self.selected_job()
  if j and j['state'] in ('running','recovering','attention','recovery_review'):
   if j['state']=='recovery_review' and QMessageBox.question(self,'Kiểm tra lịch sau khi mở lại app','Xác nhận cửa sổ đang đúng phiên LIVE. Tiếp tục quản lý và kết thúc LIVE theo giờ đã lưu?')!=QMessageBox.StandardButton.Yes:return
   try:self.submit(j,'status')
   except Exception as e:self.status.setText(str(e))
 def cancel(self):
  j=self.selected_job()
  if not j:return
  if j['state'] in ('running','starting','preparing','recovering','stopping','attention','stop_retry','recovery_review'):
   # 4.1.4 (owner video 19/10/2026 04:09): a job stuck in "Cần kiểm tra" could not be
   # removed — every "Kết thúc" failed again (Studio window had changed). The owner
   # can now always just drop the job.
   box=QMessageBox(self);box.setIcon(QMessageBox.Icon.Question);box.setWindowTitle('Hủy / kết thúc lịch')
   box.setText('Lịch này đang chạy hoặc đang kẹt. Bạn muốn làm gì?')
   box.setInformativeText('Kết thúc LIVE: NBL bấm Kết thúc LIVE trên Studio.\nChỉ hủy lịch: NBL thôi quản lý lịch này NGAY. Nếu LIVE còn chạy thì bạn tự tắt trên Studio.')
   end=box.addButton('Kết thúc LIVE',QMessageBox.ButtonRole.AcceptRole);drop=box.addButton('Chỉ hủy lịch',QMessageBox.ButtonRole.DestructiveRole);box.addButton('Thôi',QMessageBox.ButtonRole.RejectRole)
   box.exec();clicked=box.clickedButton()
   if clicked is end:j['state']='stopping';self.stop_chrome(j);self.submit(j,'stop')
   elif clicked is drop:self.drop_job(j)
   else:return
  else:j['state']='cancelled';j['retry_at']=0
  self.save();self.render()
 def drop_job(self,j):
  """Stop managing this job at once, whatever Studio says; never clicks Studio."""
  for future,key in list(self.futures.items()):
   if key[0]==j['id']:
    future.cancel();del self.futures[future]   # a result still on its way is ignored
  j['state']='cancelled';j['error']='Đã hủy lịch bằng tay; NBL không quản lý LIVE này nữa';j.pop('chrome_start_at',None)
  self.stop_chrome(j);self.owner.log('Đã hủy lịch '+time.strftime('%H:%M',time.localtime(j['start']))+' bằng tay.')
 def cancel_pending_starts(self,j):
  for future,key in list(self.futures.items()):
   if key[0]==j['id'] and key[2] in ('start','preflight','bundle','collapse_chat') and future.cancel():del self.futures[future]
 def stop_chrome(self,j):
  ai=getattr(self.owner,'ai',None)
  if ai:ai.stop(j['profile'])
  if hasattr(self.owner,'studio_chat'):
   for kind in ('message','greeting'):self.owner.studio_chat.engine.stop(j['profile'],kind)
  try:p=self.profile(j['profile']);session,client=self.client(p);self.owner.bridge.command(client,dict(action='stop',module='all'))
  except Exception:pass
 # ---------------- 4.2.0 tắt LIVE khẩn cấp ----------------
 def quit_studio_now(self):
  """4.3.9: tắt hẳn ứng dụng TikTok LIVE Studio bằng tay (không bấm dấu X)."""
  p=self.current_profile()
  if not p:raise ValueError('Chưa có nick nào kết nối LIVE Studio.')
  if any(key[0]=='quitstudio' for key in self.futures.values()):return
  future=self.pool.submit_priority(0,execute,copy.deepcopy(self.effective_profile(p)),'quit_studio',0,None)
  self.futures[future]=('quitstudio',None,'quit_studio')
 def emergency(self,profile_id=None):
  """Owner, 28/10/2026: one nick (profile_id) or every nick (None). Cancels the
  schedules not started yet, ends every LIVE (also one started by hand), switches
  off pin/reply on Chrome. NBL VIDEO keeps playing. Telegram gets the result."""
  now=time.time();targets=[p for p in self.profiles if profile_id in (None,p['id'])]
  if not targets:raise ValueError('Chưa có nick nào kết nối LIVE Studio.')
  ids={p['id'] for p in targets};cancelled=[];watch=[]
  for j in self.jobs:
   if j['profile'] not in ids:continue
   if j['state'] in ('pending','start_retry'):
    self.cancel_pending_starts(j);j['state']='cancelled';j['retry_at']=0;j['error']='Hủy bởi TẮT KHẨN CẤP'
    cancelled.append(j['id'])
  for p in targets:
   j=next((x for x in self.jobs if x['profile']==p['id'] and x['state'] in ('preparing','starting','running','recovering','attention','stop_retry','stopping','recovery_review')),None)
   if j is None:
    # no schedule of NBL on this nick: still end a LIVE started by hand (idle = nothing clicked)
    j=dict(id=uuid.uuid4().hex,profile=p['id'],start=now,end=now,clips=[],bundle='',bundle_index=0,no_sales=True,shuffle=False,state='stopping',error='',cart=dict(state='none',attempts=0,next=0),emergency=True)
    self.jobs.append(j)
   j['state']='stopping';j['emergency']=True;j['end_stop_attempted']=True;j.pop('takeover',None);j['stop_attempts']=0
   self.stop_chrome(j)
   try:self.submit(j,'emergency_stop')
   except Exception as e:self.action_failed(j,'emergency_stop',e)
   watch.append(j['id'])
  self.emergency_watch=dict(at=now,jobs=watch,cancelled=cancelled,all=profile_id is None)
  names=', '.join(str(p.get('name','')) for p in targets)
  self.owner.log('TẮT KHẨN CẤP: '+names)
  self.publish('emergency:'+str(now),'🛑 TẮT KHẨN CẤP ('+('TẤT CẢ NICK' if profile_id is None else names)+'): đang kết thúc LIVE, hủy '+str(len(cancelled))+' lịch chưa chạy, tắt ghim/trả lời Chrome. NBL VIDEO vẫn phát.')
  try:self.save()
  except Exception as e:self.owner.log('Chưa lưu được lịch sau TẮT KHẨN CẤP: '+str(e))
  self.render()
 def emergency_current(self):
  p=self.current_profile()
  if not p:QMessageBox.information(self,'Tắt LIVE','Nick đang chọn chưa kết nối LIVE Studio.');return
  self.emergency(p['id'])
 def publish(self,key,text):
  try:self.owner.notifier.publish(key,text)
  except Exception:pass
 # ---------------- 4.3.0 Studio tự kết nối (không nút) ----------------
 def auto_connect(self,now):
  """Owner, 28/10/2026: opening NBL is enough. NBL finds Studio (or opens it when it is not
  running), waits until it is loaded, reads the nick and links it to the nick of NBL.
  Studio already open without NBL's port: NBL says so and never closes it."""
  if getattr(self,'icons_fixed',0):self.owner.log('Đã chỉnh '+str(self.icons_fixed)+' icon TikTok LIVE Studio để NBL tự kết nối.');self.icons_fixed=0
  if os.name!='nt' or now<self.auto_at or any(k[0]=='autoconnect' for k in self.futures.values()):return
  session=next((s for s in self.owner.data['sessions'] if s['id']==self.current_session_id),None)
  if not session:return
  current=self.current_profile() or {}
  ok=self.connection_checks.get(current.get('id'),{})
  if current.get('cdp') and ok.get('ok') and time.monotonic()-ok.get('at',0)<30:self.auto_at=now+30;return
  self.auto_at=now+20
  from studio_cdp import find_exe,BASE_PORT
  # ask_windows=False: hàm này chạy trên luồng giao diện, không được gọi PowerShell kẻo NBL khựng.
  # Luồng thợ sẽ tự hỏi Windows khi cần mở Studio, rồi trả đường dẫn về cho NBL lưu lại.
  exe=find_exe(current.get('exePath') or '',ask_windows=False)
  port=int(current.get('cdpPort') or BASE_PORT)
  # 4.3.10 (chủ máy, 31/10/2026): TRƯỚC ĐÂY không tìm thấy file Studio là NBL bỏ về luôn,
  # không thèm thử kết nối. Máy khách cài Studio có tầng thư mục phiên bản nên dò không ra,
  # dù Studio đang mở sẵn và đã mở cổng điều khiển — NBL thừa sức đọc. File .exe chỉ cần khi
  # NBL phải TỰ MỞ Studio, nên không có thì vẫn nối, chỉ là không tự mở được thôi.
  try:
   # Studio is opened by NBL only once (when NBL starts); later NBL only looks for it.
   f=self.pool.submit_priority(30,execute,dict(cdp=True,cdpPort=port,exePath=exe,noLaunch=bool(getattr(self,'auto_launched',False)) or not exe),'connect');self.futures[f]=('autoconnect',(session['id'],exe,port),'connect')
   self.auto_launched=True
  except Exception:pass
 def auto_connected(self,future,info):
  sid,exe,port=info
  try:r=future.result()
  except Exception as e:
   text=str(e)
   # 4.3.10: trước đây lỗi y hệt chỉ ghi MỘT LẦN rồi im luôn, nên chủ máy nhìn nhật ký
   # chỉ thấy "Đang tìm và kết nối lại Studio…" mà không bao giờ biết vì sao hỏng.
   if text!=self.auto_note or time.time()-getattr(self,'auto_note_at',0)>300:
    self.auto_note=text;self.auto_note_at=time.time();self.owner.log('Studio: '+text)
   if 'KHÔNG phải do NBL mở' in text:
    try:self.owner.notifier.publish('studio:noport','⚠ TikTok LIVE Studio đang mở nhưng không mở qua NBL nên NBL chưa đọc được. Đóng Studio (khi không LIVE) rồi mở lại bằng icon TikTok LIVE Studio.')
    except Exception:pass
   self.auto_at=time.time()+30;return
  nick=r.get('nickname','')
  session=next((s for s in self.owner.data['sessions'] if s['id']==sid),None)
  if not nick or not session:return
  current=next((p for p in self.profiles if p.get('session')==sid),None) or {}
  value={**current,'id':current.get('id',uuid.uuid4().hex),'name':nick,'accountName':nick,'session':sid,'exePath':r.get('exePath') or exe or current.get('exePath',''),'cdp':True,'cdpPort':port,
         'interaction':current.get('interaction',session.get('studio_interaction',{})),'allowMouse':current.get('allowMouse',True),'mousePermissionFile':str(self.mouse_path)}
  if current.get('name') and not same_author(current.get('name'),nick):value.pop('handle',None);value.pop('handle_for',None)   # 4.3.16: Studio đổi nick -> quên @ Chrome của nick cũ
  if current:self.profiles[self.profiles.index(current)]=value
  else:self.profiles.append(value)
  self.connection_checks[value['id']]=dict(ok=True,signature=(value.get('pid'),value.get('windowHandle'),value.get('exePath')),at=time.monotonic())
  if self.auto_note!='ok:'+nick:self.auto_note='ok:'+nick;self.owner.log('Đã tự kết nối TikTok LIVE Studio: '+nick)
  self.save();self.refresh_profiles();self.render();self.auto_at=time.time()+30
 def poll_studio_captcha(self,now):
  if now-getattr(self,'captcha_at',0)<20:return
  self.captcha_at=now
  for p in self.profiles:
   if p.get('cdp') and not any(k[0]=='studiocaptcha' for k in self.futures.values()):
    try:f=self.pool.submit_priority(48,execute,copy.deepcopy(self.effective_profile(p)),'captcha');self.futures[f]=('studiocaptcha',p.get('name',''),'captcha')
    except Exception:pass
 def poll_chat_dock(self,now):
  """4.3.8: whenever a nick is LIVE, keep the Studio chat docked (no mouse) so AI reads
  comments and greeting can type. Every 20 s, only when that nick is LIVE."""
  if now-getattr(self,'dock_at',0)<20:return
  self.dock_at=now
  for p in self.profiles:
   if not p.get('cdp'):continue
   live=p['id'] in getattr(self,'hand_live',{}) or any(j['profile']==p['id'] and j['state'] in ('running','recovering') for j in self.jobs)
   if not live or any(k[0]=='chatdock' for k in self.futures.values()):continue
   try:f=self.pool.submit_priority(44,execute,copy.deepcopy(self.effective_profile(p)),'dock_chat');self.futures[f]=('chatdock',p.get('name',''),'dock_chat')
   except Exception:pass
 # ---------------- 4.3.0 LIVE bật tay: tự bật ghim + AI ----------------
 def poll_hand_live(self,now):
  """Owner, 28/10/2026: whenever Studio is LIVE (also started by hand), pinning and the
  AI switch on by themselves and switch off when it ends. Read from inside Studio every
  10 s; a nick with a schedule running is left to the schedule."""
  if not hasattr(self,'hand_live'):self.hand_live={};self.hand_probe={}
  for p in self.profiles:
   if not p.get('cdp'):continue
   if any(j['profile']==p['id'] and j['state'] in ACTIVE for j in self.jobs):
    self.hand_live.pop(p['id'],None);continue
   if now-self.hand_probe.get(p['id'],0)<10 or any(k[0]=='hand:'+p['id'] for k in self.futures.values()):continue
   self.hand_probe[p['id']]=now
   try:
    f=self.pool.submit_priority(45,execute,copy.deepcopy(self.effective_profile(p)),'status',0,None);self.futures[f]=('hand:'+p['id'],None,'status')
   except Exception:pass
 def hand_result(self,pid,future):
  p=self.profile(pid)
  if not p:return
  try:live=bool(future.result().get('live'))
  except Exception as e:
   from studio_cdp import StudioChanged
   if isinstance(e,StudioChanged):
    self.owner.log('Studio: '+str(e))
    try:self.owner.notifier.publish('studio:changed:'+pid,'⚠ '+str(p.get('name',''))+' · '+str(e)+' NBL dừng tự thao tác; kiểm tra Studio.')
    except Exception:pass
   return
  was=pid in self.hand_live
  if live and not was:
   self.hand_live[pid]=time.time()
   if not getattr(self,'auto_enabled',True):self.owner.log(str(p.get('name',''))+' · Studio đang LIVE, nhưng BẮT ĐẦU đang tắt: chưa bật ghim/AI.');return
   self.owner.log(str(p.get('name',''))+' · Studio đang LIVE (bật tay): tự bật ghim + AI.')
   self.start_live_helpers(p)
  elif not live and was:
   self.hand_live.pop(pid,None);self.owner.log(str(p.get('name',''))+' · LIVE bật tay đã kết thúc: tắt ghim + AI.')
   self.stop_live_helpers(p)
 def start_live_helpers(self,p):
  try:
   session,client=self.client(p);config=self.owner.pin_command_config(session) if hasattr(self.owner,'pin_command_config') else {}
   self.owner.bridge.command(client,dict(action='start',module='pin',config=config,expectedAccount=session.get('chrome_binding',{}).get('account') or p['name']))
  except Exception as e:self.owner.log('Ghim: '+str(e))
  ai=getattr(self.owner,'ai',None)
  if ai:
   try:ai.start(self.effective_profile(p))
   except Exception as e:self.owner.log('AI: '+str(e))
 def stop_live_helpers(self,p):
  try:session,client=self.client(p);self.owner.bridge.command(client,dict(action='stop',module='all'))
  except Exception:pass
  ai=getattr(self.owner,'ai',None)
  if ai:ai.stop(p['id'])
 def set_auto(self,on):
  """Nút BẮT ĐẦU / DỪNG: DỪNG tắt ghim + AI ngay và không tự bật lại; BẮT ĐẦU bật lại (nếu đang LIVE thì bật ngay)."""
  self.auto_enabled=bool(on);self.controls['autoHelpers']=self.auto_enabled
  try:self.save()
  except Exception:pass
  for p in self.profiles:
   live=p['id'] in getattr(self,'hand_live',{}) or any(j['profile']==p['id'] and j['state']=='running' for j in self.jobs)
   if not live:continue
   if on:self.start_live_helpers(p)
   else:self.stop_live_helpers(p)
 def poll_emergency(self,now):
  w=getattr(self,'emergency_watch',None)
  if not w:return
  jobs=[x for x in self.jobs if x['id'] in w['jobs']]
  if any(x['state'] in ('stopping','stop_retry') for x in jobs) and now-w['at']<600:return
  self.emergency_watch=None
  name=lambda x:str((self.profile(x['profile']) or {}).get('name') or x['profile'])
  done=[name(x) for x in jobs if x['state'] in ('finished','cancelled','manual_stop')]
  left=[name(x) for x in jobs if x['state'] not in ('finished','cancelled','manual_stop')]
  lines=['🛑 KẾT QUẢ TẮT KHẨN CẤP']
  if done:lines.append('✅ Đã tắt: '+', '.join(done))
  if left:lines.append('⚠ CHƯA TẮT ĐƯỢC (tắt tay trên Studio ngay!): '+', '.join(left))
  gone=[x for x in self.jobs if x['id'] in w['cancelled']]
  if gone:lines.append('🗓 Đã hủy '+str(len(gone))+' lịch: '+'; '.join(name(x)+' '+time.strftime('%H:%M %d/%m',time.localtime(x['start'])) for x in gone))
  lines.append('📌 NHỚ LÊN LỊCH LẠI các phiên đã hủy. NBL VIDEO vẫn đang phát.')
  text='\n'.join(lines);self.owner.log(text.replace('\n',' · '));self.publish('emergency:done:'+str(now),text)
 def stop_all(self):
  for j in self.jobs:
   if j['state'] in ('pending','start_retry'):j['state']='cancelled'
   elif j['state'] in ('running','starting','preparing','recovering','attention','stop_retry'):
    j['state']='stopping';self.stop_chrome(j);self.submit(j,'stop')
  try:self.save()
  except Exception as e:self.owner.log('Không lưu được trạng thái dừng Studio: '+str(e))
  self.render()
 def active(self):return any(j['state'] in ACTIVE for j in self.jobs)
 def driving(self):return any(j['state'] in ('preparing','starting','running','stopping','recovering') for j in self.jobs)
 def shutdown(self):
  try:self.save()
  except Exception as e:self.owner.log('Chưa lưu được Studio: '+str(e))
  self.stopped=True;self.timer.stop()
  for future in self.futures:future.cancel()
  self.pool.shutdown(wait=False,cancel_futures=True);self.save();self.close()
