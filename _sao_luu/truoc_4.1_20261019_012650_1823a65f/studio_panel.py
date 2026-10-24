"""Two-account Studio scheduling UI. Windows calls run outside the GUI thread."""
import copy,json,time,uuid,math,os
from studio_worker import StudioWorker
from pathlib import Path
from PySide6.QtCore import QTimer,QDateTime,Qt
from PySide6.QtWidgets import (QApplication,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QComboBox,QLineEdit,QListWidget,QAbstractItemView,QDateTimeEdit,QCheckBox,QFileDialog,QMessageBox,QDialog,QFormLayout,QTextEdit,QScrollArea,QGroupBox)
from model import write_json
from session_binding import resolve_binding
from video_commands import same_file
from studio_scheduler import add_job,decisions,execute,list_windows,window_from_pointer,explain_studio_error
from studio_vision_logic import NotTouched,same_author
CONTROL_FIELDS={'liveIndicator','startButton','startConfirm','stopMenu','stopButton','stopConfirm','summaryClose','chatRegion','chatInput','chatSend','collapseImage'}
OPTIONAL_FIELDS={'startConfirm','stopMenu','stopConfirm','summaryClose'}
STATE_LABELS={'pending':'Chờ đến giờ','preparing':'Đang chuẩn bị','starting':'Đang mở LIVE','running':'Đang LIVE','stopping':'Đang kết thúc','finished':'Đã kết thúc','failed':'Cần kiểm tra','attention':'Cần kiểm tra','manual_stop':'Đã dừng thủ công','skipped':'Đã bỏ lịch quá giờ','cancelled':'Đã hủy','recovery_review':'Cần kiểm tra sau khi mở lại app','recovering':'Đang kiểm tra'}

class StudioPanel(QWidget):
 def __init__(self,owner):
  super().__init__();self.owner=owner;self.setWindowTitle('NBL LIVE 4.0.2 · Lịch phát LIVE');self.resize(450,740)
  self.connection_checks={};self.probe_futures={};self.last_connection_probe=0;self.current_session_id='';self.controls={};self.path=owner.path.parent/'studio_schedules.json';self.pool=StudioWorker();self.futures={};self.profiles=[];self.jobs=[];self.library=[];self.stopped=False
  from studio_store import load as load_studio
  saved,self.recovery_notice=load_studio(self.path)
  self.profiles=saved['profiles'];self.controls=saved.get('controls',{}) if isinstance(saved.get('controls'),dict) else {}
  if not self.controls and self.profiles:self.controls={k:self.profiles[0][k] for k in CONTROL_FIELDS if self.profiles[0].get(k)}
  self.jobs=saved['jobs'];self.library=[x for x in saved.get('library',[]) if isinstance(x,str)]
  for j in self.jobs:
   if j['state'] in ('running','starting','preparing','stopping','recovering','attention'):
    j['state']='recovery_review';j['error']='App đã khởi động lại: kiểm tra và nhận lại lịch trước khi điều khiển Studio'
  if self.recovery_notice:
   self.owner.log(self.recovery_notice)
   QTimer.singleShot(0,lambda:QMessageBox.warning(self,'Đã khôi phục lịch Studio',self.recovery_notice))
  v=QVBoxLayout(self);notice=QLabel('Chọn nick ở đầu app. Kết nối cửa sổ LIVE Studio một lần; các nút đã chọn được dùng chung giữa các nick.');notice.setWordWrap(True);v.addWidget(notice)
  self.nick=QComboBox();self.nick.hide();v.addWidget(self.nick)
  self.connection_label=QLabel('Chưa kết nối LIVE Studio cho nick này');self.connection_label.setWordWrap(True);v.addWidget(self.connection_label)
  b=QPushButton('Kết nối / chọn nút trong LIVE Studio');b.clicked.connect(self.connect_current);v.addWidget(b)
  self.start=QDateTimeEdit(QDateTime.currentDateTime().addSecs(300));self.end=QDateTimeEdit(QDateTime.currentDateTime().addSecs(3900))
  for label,w in [('Bắt đầu (giờ Windows)',self.start),('Kết thúc',self.end)]:v.addWidget(QLabel(label));w.setDisplayFormat('dd/MM/yyyy HH:mm:ss');w.setCalendarPopup(True);v.addWidget(w)
  self.clips=QListWidget();self.clips.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection);v.addWidget(QLabel('Bấm chọn các clip của phiên; không giới hạn số clip'));v.addWidget(self.clips)
  for file in dict.fromkeys(self.library+[p for s in owner.data['sessions'] for p in s['playlist']]):self.clips.addItem(file)
  b=QPushButton('Thêm clip vào danh sách');b.clicked.connect(self.add_clips);v.addWidget(b)
  self.shuffle=QCheckBox('Xáo clip, lặp đến hết lịch');v.addWidget(self.shuffle)
  self.no_sales=QCheckBox('Phiên này không bán hàng');v.addWidget(self.no_sales)
  b=QPushButton('Lưu lịch');b.clicked.connect(self.create_job);v.addWidget(b)
  self.list=QListWidget();v.addWidget(self.list);b=QPushButton('Hủy / kết thúc lịch đã chọn');b.clicked.connect(self.cancel);v.addWidget(b)
  b=QPushButton('Kiểm tra lại trạng thái lịch đã chọn');b.clicked.connect(self.recheck);v.addWidget(b)
  b=QPushButton('Gỡ liên kết nick đã chọn');b.clicked.connect(self.remove_profile);v.addWidget(b)
  self.status=QLabel('Sẵn sàng');self.status.setWordWrap(True);v.addWidget(self.status)
  self.mouse_path=owner.path.parent/'studio_mouse_allowed.txt'
  self.mouse_path.write_text('1',encoding='utf-8')
  for p in self.profiles:p['mousePermissionFile']=str(self.mouse_path)
  self.refresh_profiles();self.render();self.timer=QTimer(self);self.timer.timeout.connect(self.tick);self.timer.start(1000)
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
  self.current_session_id=str(session_id);self.refresh_profiles();self.render()
 def current_profile(self):
  return next((p for p in self.profiles if p.get('session')==self.current_session_id),None)
 def effective_profile(self,p):
  return {**p,**{k:v for k,v in self.controls.items() if k in CONTROL_FIELDS},'accountAnchor':p.get('accountAnchor','')}
 def profile(self,key):return next((p for p in self.profiles if p['id']==key),None)
 def connect_current(self):self.edit_profile(False)
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
  if self.active() or busy_chat:QMessageBox.warning(self,'Đang chạy','Các nick dùng chung thiết lập nút. Kết thúc lịch LIVE và dừng nhắn tin, chào khách trước khi thay đổi các nút.');return
  if current and any(j['profile']==current['id'] and j['state'] in ('preparing','starting','running','stopping','recovering','attention') for j in self.jobs):QMessageBox.warning(self,'Đang chạy','Kết thúc LIVE và dừng tin nhắn, chào khách trước khi chọn lại nút.');return
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
 def create_job(self):
  try:
   p=self.current_profile();clips=[i.text() for i in self.clips.selectedItems()]
   if not p:raise ValueError('Bấm Kết nối LIVE Studio cho nick đang chọn trước.')
   missing=[x for x in clips if not Path(x).is_file()]
   if missing:raise ValueError('Clip không còn tồn tại: '+missing[0])
   j=add_job(self.jobs,p['id'],self.start.dateTime().toSecsSinceEpoch(),self.end.dateTime().toSecsSinceEpoch(),clips,'',self.no_sales.isChecked(),self.shuffle.isChecked())
   self.save();self.render()
  except Exception as e:QMessageBox.warning(self,'Lịch',str(e))
 def selected_job(self):
  item=self.list.currentItem();return next((j for j in self.jobs if item and j['id']==item.data(Qt.ItemDataRole.UserRole)),None)
 def render(self):
  selected=self.selected_job();selected_id=selected['id'] if selected else None;self.list.clear();p=self.current_profile()
  for j in self.jobs:
   if not p or j['profile']!=p['id']:continue
   self.list.addItem(time.strftime('%d/%m %H:%M',time.localtime(j['start']))+' → '+time.strftime('%H:%M',time.localtime(j['end']))+' · '+STATE_LABELS.get(j['state'],j['state'])+(' · '+j.get('error','') if j.get('error') else ''))
   item=self.list.item(self.list.count()-1);item.setData(Qt.ItemDataRole.UserRole,j['id'])
   if j['id']==selected_id:self.list.setCurrentItem(item)
 def session(self,p):
  session=next(s for s in self.owner.data['sessions'] if s['id']==p['session'])
  account=session.get('chrome_binding',{}).get('account')
  if account and not same_author(account,p['name']):raise ValueError('Nick Chrome đã thay đổi. Kết nối lại đúng cửa sổ LIVE Studio cho nick này trước.')
  return session
 def client(self,p):
  s=self.session(p);client=resolve_binding(s.get('chrome_binding'),self.owner.bridge.snapshot())
  if not client:raise ValueError('Chưa có đúng tab Chrome/nick kết nối.')
  return s,client
 def submit(self,j,action):
  p=self.profile(j['profile'])
  if action=='stop':
   self.cancel_pending_starts(j)
   if hasattr(self.owner,'studio_chat'):
    for kind in ('message','greeting'):self.owner.studio_chat.engine.stop(j['profile'],kind)
  if not p:raise ValueError('Thiếu liên kết LIVE Studio')
  if any(key[0]==j['id'] and key[2]==action for key in self.futures.values()):return
  try:self.save()
  except OSError:
   if action!='stop':raise
   self.owner.log('Chưa lưu được lịch; vẫn gửi lệnh kết thúc Studio.')
  future=self.pool.submit_priority(0 if action=='stop' else 10 if action=='start' else 20,execute,copy.deepcopy(self.effective_profile(p)),'status' if action=='preflight' else action,j['end'] if action=='start' else 0);self.futures[future]=(j['id'],None,action)
 def tick(self):
  if self.stopped:return
  self.poll_connection()
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
    if jid=='inspect':
     try:widget.setPlainText(json.dumps(future.result(),ensure_ascii=False,indent=2))
     except RuntimeError:pass
     except Exception as e:
      try:widget.setPlainText(str(e))
      except RuntimeError:pass
     continue
    j=next(j for j in self.jobs if j['id']==jid)
    try:
     result=future.result()
     if result.get('pid'):self.profile(j['profile'])['pid']=str(result['pid'])
     if action=='preflight':
      if j['state']!='preparing':continue
      if result.get('warnings'):raise ValueError('Studio đang cảnh báo: '+str(result['warnings']))
      if result.get('live'):raise ValueError('Nick đã LIVE trước lịch; không tự tiếp quản')
      p=self.profile(j['profile']);session=self.session(p)
      session.update(playlist=j['clips'],loop=True,shuffle=j['shuffle']);self.owner.command('play',False,session);j['prepare_phase']='video';j['video_until']=time.time()+15
     elif action=='stop':
      if result.get('live'):raise ValueError('Chưa xác nhận LIVE đã kết thúc')
      p=self.profile(j['profile']);s=next(s for s in self.owner.data['sessions'] if s['id']==p['session']);self.owner.command('stop',False,s);j['state']='finished';self.close_chrome_summary(j)
      if result.get('cleanupWarning'):self.owner.log(result['cleanupWarning'])
     elif action=='start':
      if j['state']=='attention':continue
      if not result.get('live'):raise ValueError('Chưa xác nhận bắt đầu LIVE')
      if time.time()>=j['end'] or j['state']=='stopping':self.submit(j,'stop')
      else:
       j['state']='running'
       if hasattr(self.owner,'studio_chat'):
        p=self.profile(j['profile']);cfg=p.get('interaction',{})
        for kind in ('message','greeting'):
         if cfg.get('auto_'+kind):
          try:self.owner.studio_chat.engine.enable(self.effective_profile(p),kind,cfg)
          except Exception as e:self.owner.log('Studio '+kind+': '+str(e))
       self.begin_chrome(j)
       try:
        p=self.profile(j['profile']);future=self.pool.submit_priority(25,execute,copy.deepcopy(self.effective_profile(p)),'collapse_chat',min(j['end'],time.time()+15));self.futures[future]=(j['id'],None,'collapse_chat')
       except Exception as e:self.owner.log('Thu cửa sổ trò chuyện: '+str(e))
     elif action=='collapse_chat':
      if not result.get('collapsed'):self.owner.log('Chưa thu được cửa sổ trò chuyện; các mục khác tiếp tục.')
     elif action=='status':
      if j['state'] not in ('running','recovering','attention','recovery_review'):continue
      if not result.get('live'):
       j['state']='manual_stop';j['error']='LIVE đã dừng; không tự mở lại';self.stop_chrome(j)
       p=self.profile(j['profile']);session=next(s for s in self.owner.data['sessions'] if s['id']==p['session']);self.owner.command('stop',False,session)
      elif result.get('warnings'):raise ValueError('Studio đang cảnh báo: '+str(result['warnings']))
      elif j['state'] in ('recovering','attention','recovery_review'):j['state']='running';j['error']=''
      j['probe_failures']=0
      if j['state']=='running' and j.get('error','').startswith('Tạm chưa đọc được Studio'):j['error']=''
    except Exception as e:
     if action=='collapse_chat':
      self.owner.log('Chưa thu được cửa sổ trò chuyện; các mục khác tiếp tục.');continue
     if isinstance(e,NotTouched) and action=='status' and j['state']=='running':
      # One unreadable probe (Studio briefly covered, clock mid-redraw) is not a stopped LIVE.
      j['probe_failures']=j.get('probe_failures',0)+1
      if j['probe_failures']<4:
       j['error']='Tạm chưa đọc được Studio ('+str(j['probe_failures'])+'/3): '+str(e);self.status.setText(j['error']);continue
     j['state']= 'attention' if action in ('start','stop','status') else 'failed';j['error']=str(e);self.owner.log('Studio: '+str(e));self.status.setText(str(e))
     if hasattr(self.owner,'studio_chat'):
      for kind in ('message','greeting'):self.owner.studio_chat.engine.stop(j['profile'],kind)
     self.owner.notifier.publish('studio:'+j['profile'],str(e))
   for j in self.jobs:
    try:
     if j['state']=='preparing' and j.get('prepare_phase')=='video':
      p=self.profile(j['profile']);session=self.session(p)
      try:video=json.loads((self.owner.path.parent/'runtime'/session['id']/'status.json').read_text(encoding='utf-8'))
      except (OSError,ValueError):video={}
      if video.get('state')=='PlayingState' and time.time()-video.get('time',0)<3 and any(same_file(video.get('path',''),clip) for clip in j['clips']):
       j['prepare_phase']='start';j['state']='starting';self.submit(j,'start')
      elif time.time()>j['video_until']:j['state']='failed';j['error']='Video chưa phát ổn định; chưa mở LIVE';self.stop_owned_video(j)
    except Exception as e:
     j['state']='failed';j['error']=str(e);self.owner.log('Chuẩn bị Studio: '+str(e));self.stop_owned_video(j)
   self.poll_chrome()
   for j,action in decisions(self.jobs,time.time()):
    try:
     p=self.profile(j['profile'])
     if action=='prepare':
      s=self.session(p)
      if any(not Path(x).is_file() for x in j['clips']):raise ValueError('Clip mất; không bắt đầu LIVE')
      # A separate status check is required before committing a scheduled start.
      required=('exePath','windowTitle','accountAnchor','liveIndicator','startButton','stopButton')
      if any(not self.effective_profile(p).get(k) for k in required):raise ValueError('Chưa chọn đủ nút LIVE Studio. Bấm Kết nối / chọn nút để bổ sung.')
      j['prepare_phase']='preflight';self.submit(j,'preflight')
     elif action=='stop':
      try:s,client=self.client(p);self.owner.bridge.command(client,dict(action='stop',module='all'))
      except Exception:pass
      self.submit(j,'stop')
     else:self.submit(j,'status')
    except Exception as e:j['state']='failed';j['error']=str(e);self.owner.log('Studio: '+str(e))
   signature=json.dumps(self.jobs,sort_keys=True)
   if signature!=getattr(self,'signature',''):self.save();self.render();self.signature=signature
  except Exception as e:self.owner.log('Lịch Studio: '+str(e))
 def stop_owned_video(self,j):
  if j.get('prepare_phase') in ('video','start'):
   try:self.owner.command('stop',False,self.session(self.profile(j['profile'])))
   except Exception as e:self.owner.log('Dừng clip chuẩn bị: '+str(e))
 def start_chrome_modules(self,j,include_pin=True):
  p=self.profile(j['profile']);session,client=self.client(p)
  for module in ('reply',)+(('pin',) if include_pin and not j['no_sales'] else ()):
   try:self.owner.bridge.command(client,dict(action='start',module=module,expectedAccount=session.get('chrome_binding',{}).get('account') or p['name']))
   except Exception as e:self.owner.log('Chrome '+module+': '+str(e))
 def begin_chrome(self,j):
  try:
   p=self.profile(j['profile']);session,client=self.client(p);snapshot=self.owner.bridge.snapshot().get(client,{});config=snapshot.get('config',{});bundle=config.get('bundleName','').strip()
   if j['no_sales']:self.start_chrome_modules(j,False);return
   if not bundle:
    self.owner.log('Chưa chọn bộ sản phẩm trên Chrome; LIVE vẫn chạy.');self.start_chrome_modules(j);return
   token=self.owner.bridge.command(client,dict(action='prepare_bundle',module='all',bundle=bundle,expectedAccount=session.get('chrome_binding',{}).get('account') or p['name']))
   j['chrome_prepare']=dict(id=token,until=time.time()+25)
  except Exception as e:j['error']='LIVE đang chạy · Chrome: '+str(e);self.owner.log(j['error'])
 def poll_chrome(self):
  for j in self.jobs:
   pending=j.get('chrome_prepare')
   if not pending:continue
   if j['state']!='running':j.pop('chrome_prepare',None);continue
   try:
    p=self.profile(j['profile']);session,client=self.client(p);result=self.owner.bridge.snapshot().get(client,{}).get('control',{})
    if result.get('id')==pending['id'] and result.get('state') in ('done','partial','failed'):
     j.pop('chrome_prepare',None)
     if result['state']=='failed':self.owner.log('Giỏ hàng: '+result.get('error','Chưa thêm được bộ sản phẩm')+' · LIVE tiếp tục.');self.start_chrome_modules(j,False)
     else:self.start_chrome_modules(j)
    elif time.time()>pending['until']:
     j.pop('chrome_prepare',None);self.owner.log('Chưa xác nhận giỏ hàng; LIVE vẫn chạy, không tự thêm lại.');self.start_chrome_modules(j,False)
   except Exception as e:
    if time.time()>pending['until']:j.pop('chrome_prepare',None);self.owner.log('Giỏ hàng chờ kết nối: '+str(e))
 def close_chrome_summary(self,j):
  try:p=self.profile(j['profile']);session,client=self.client(p);self.owner.bridge.command(client,dict(action='finish_live',module='all',expectedAccount=session.get('chrome_binding',{}).get('account') or p['name']))
  except Exception as e:self.owner.log('Đóng bảng tổng kết Chrome: '+str(e))
 def recheck(self):
  j=self.selected_job()
  if j and j['state'] in ('running','recovering','attention','recovery_review'):
   if j['state']=='recovery_review' and QMessageBox.question(self,'Kiểm tra lịch sau khi mở lại app','Xác nhận cửa sổ đang đúng phiên LIVE. Tiếp tục quản lý và kết thúc LIVE theo giờ đã lưu?')!=QMessageBox.StandardButton.Yes:return
   try:self.submit(j,'status')
   except Exception as e:self.status.setText(str(e))
 def cancel(self):
  j=self.selected_job()
  if not j:return
  if j['state'] in ('running','starting','preparing','recovering','stopping','attention'):
   if QMessageBox.question(self,'Kết thúc','Kết thúc LIVE của lịch này ngay?')!=QMessageBox.StandardButton.Yes:return
   j['state']='stopping';self.stop_chrome(j);self.submit(j,'stop')
  else:j['state']='cancelled'
  self.save();self.render()
 def cancel_pending_starts(self,j):
  for future,key in list(self.futures.items()):
   if key[0]==j['id'] and key[2] in ('start','preflight','bundle','collapse_chat') and future.cancel():del self.futures[future]
 def stop_chrome(self,j):
  if hasattr(self.owner,'studio_chat'):
   for kind in ('message','greeting'):self.owner.studio_chat.engine.stop(j['profile'],kind)
  try:p=self.profile(j['profile']);session,client=self.client(p);self.owner.bridge.command(client,dict(action='stop',module='all'))
  except Exception:pass
 def stop_all(self):
  for j in self.jobs:
   if j['state']=='pending':j['state']='cancelled'
   elif j['state'] in ('running','starting','preparing','recovering','attention'):
    j['state']='stopping';self.stop_chrome(j);self.submit(j,'stop')
  try:self.save()
  except Exception as e:self.owner.log('Không lưu được trạng thái dừng Studio: '+str(e))
  self.render()
 def active(self):return any(j['state'] in ('preparing','starting','running','stopping','recovering','attention') for j in self.jobs)
 def shutdown(self):
  try:self.save()
  except Exception as e:self.owner.log('Chưa lưu được Studio: '+str(e))
  self.stopped=True;self.timer.stop()
  for future in self.futures:future.cancel()
  self.pool.shutdown(wait=False,cancel_futures=True);self.save();self.close()
