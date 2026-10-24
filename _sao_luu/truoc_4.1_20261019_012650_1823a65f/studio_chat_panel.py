from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QComboBox,QGroupBox,QTextEdit,QSpinBox,QPushButton,QHBoxLayout,QCheckBox,QMessageBox
from PySide6.QtCore import QTimer,Qt
from studio_interactions import StudioInteractions
from model import write_json

class StudioChatPanel(QWidget):
 def __init__(self,owner,studio):
  super().__init__();self.owner=owner;self.studio=studio;self.loading=False;self.current_session_id=''
  self.engine=StudioInteractions(studio.pool,owner.path.parent/'studio_interactions_journal.json',owner.log,lambda k,t:owner.notifier.publish(k,t))
  v=QVBoxLayout(self);heading=QLabel('Tin nhắn & chào khách');heading.setObjectName('title');v.addWidget(heading)
  note=QLabel('Thiết lập tại NBL LIVE · gửi qua LIVE Studio. Trả lời bình luận vẫn ở Chrome. Bật lại từng mục sau khi mở app; không tự gửi bù.');note.setWordWrap(True);v.addWidget(note)
  self.nick=QComboBox();self.nick.hide();v.addWidget(self.nick)
  self.mouse=QCheckBox('Cho phép chuột / bàn phím Studio');self.mouse.setChecked(True);v.addWidget(self.mouse);self.mouse.toggled.connect(self.mouse_change)
  box=QGroupBox('Nhắn theo mẫu');b=QVBoxLayout(box);self.messages=QTextEdit();self.messages.setPlaceholderText('Tin nhắn mẫu — mỗi dòng một câu · tối đa 100 ký tự\nAnh/chị xem sản phẩm trong giỏ hàng nhé.');self.messages.setMaximumHeight(140);b.addWidget(self.messages)
  b.addWidget(QLabel('Khoảng cách gửi (giây)'));self.interval=QSpinBox();self.interval.setRange(60,86400);self.interval.setValue(300);self.interval.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons);self.interval.setReadOnly(True);self.interval.setMinimumWidth(60);self.interval.setMaximumWidth(90);self.interval.lineEdit().setStyleSheet('border:0;padding:0;background:transparent;color:#203a50;');row=QHBoxLayout();minus=QPushButton('−15 giây');plus=QPushButton('+15 giây');minus.clicked.connect(lambda:self.interval.setValue(self.interval.value()-15));plus.clicked.connect(lambda:self.interval.setValue(self.interval.value()+15));self.interval.hide();self.interval_display=QLabel(str(self.interval.value()));self.interval_display.setMinimumWidth(60);self.interval_display.setAlignment(Qt.AlignmentFlag.AlignCenter);self.interval_display.setStyleSheet('background:white;color:#203a50;border:1px solid #b5d6e9;border-radius:10px;padding:8px;');self.interval.valueChanged.connect(lambda value:self.interval_display.setText(str(value)));row.addWidget(minus);row.addWidget(self.interval_display,1);row.addWidget(plus);b.addLayout(row)
  self.auto_message=QCheckBox('Bật cùng lịch LIVE của nick này');b.addWidget(self.auto_message)
  self.message_status=QLabel('Đã dừng');self.message_status.setWordWrap(True);b.addWidget(self.message_status)
  row=QHBoxLayout()
  for title,fn in [('Bật nhắn mẫu',lambda:self.start('message')),('Dừng',lambda:self.stop('message'))]:w=QPushButton(title);w.clicked.connect(fn);row.addWidget(w)
  b.addLayout(row);check=QPushButton('Kiểm tra ô nhắn tin — không gửi');check.clicked.connect(self.check_message);b.addWidget(check);v.addWidget(box)
  box=QGroupBox('Nút 👋 Chào trong LIVE Studio');b=QVBoxLayout(box);note=QLabel('Chào khách mới sau khi bật. Bỏ qua danh sách cũ, không bấm lặp cùng tên trong lượt chạy; tối thiểu 10 giây giữa hai lần chào.');note.setWordWrap(True);b.addWidget(note)
  b.addWidget(QLabel('Nghỉ giữa hai lần chào (giây)'));self.greeting_interval=QSpinBox();self.greeting_interval.setRange(10,3600);self.greeting_interval.setValue(10);self.greeting_interval.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons);self.greeting_interval.setReadOnly(True);self.greeting_interval.setMinimumWidth(60);self.greeting_interval.setMaximumWidth(90);self.greeting_interval.lineEdit().setStyleSheet('border:0;padding:0;background:transparent;color:#203a50;');row=QHBoxLayout();minus=QPushButton('−5 giây');plus=QPushButton('+5 giây');minus.clicked.connect(lambda:self.greeting_interval.setValue(self.greeting_interval.value()-5));plus.clicked.connect(lambda:self.greeting_interval.setValue(self.greeting_interval.value()+5));self.greeting_interval.hide();self.greeting_interval_display=QLabel(str(self.greeting_interval.value()));self.greeting_interval_display.setMinimumWidth(60);self.greeting_interval_display.setAlignment(Qt.AlignmentFlag.AlignCenter);self.greeting_interval_display.setStyleSheet('background:white;color:#203a50;border:1px solid #b5d6e9;border-radius:10px;padding:8px;');self.greeting_interval.valueChanged.connect(lambda value:self.greeting_interval_display.setText(str(value)));row.addWidget(minus);row.addWidget(self.greeting_interval_display,1);row.addWidget(plus);b.addLayout(row)
  self.auto_greeting=QCheckBox('Bật Chào cùng lịch LIVE của nick này');b.addWidget(self.auto_greeting)
  self.greeting_status=QLabel('Đã dừng');self.greeting_status.setWordWrap(True);b.addWidget(self.greeting_status);row=QHBoxLayout()
  for title,fn in [('Bật Chào khách',lambda:self.start('greeting')),('Dừng Chào',lambda:self.stop('greeting'))]:w=QPushButton(title);w.clicked.connect(fn);row.addWidget(w)
  b.addLayout(row);v.addWidget(box)
  vision=QPushButton('Thiết lập đọc bằng ảnh — khoanh vùng Studio');vision.clicked.connect(self.configure_vision);v.addWidget(vision)
  vision_note=QLabel('Đọc bằng ảnh: Studio cần hiện rõ. App có thể đưa Studio lên trước để thao tác. Thay kích thước Studio thì khoanh lại. Chào nhận theo tên hiển thị nên có thể bỏ qua khách trùng tên.');vision_note.setWordWrap(True);v.addWidget(vision_note)
  self.ocr_status=QLabel('Bộ đọc tiếng Việt: đang khởi động');self.ocr_status.setWordWrap(True);v.addWidget(self.ocr_status)
  saved_note=QLabel('Nội dung tự lưu riêng theo nick đang chọn ở đầu app.');saved_note.setWordWrap(True);v.addWidget(saved_note);v.addStretch()
  self.timer=QTimer(self);self.timer.timeout.connect(self.tick);self.timer.start(1000);self.refresh()
  self.autosave=QTimer(self);self.autosave.setSingleShot(True);self.autosave.setInterval(450);self.autosave.timeout.connect(self.safe_save)
  for signal in (self.messages.textChanged,self.interval.valueChanged,self.greeting_interval.valueChanged,self.auto_message.toggled,self.auto_greeting.toggled):signal.connect(self.schedule_save)
 def safe_save(self):
  try:self.save()
  except Exception as e:self.owner.log('Chưa lưu được tin nhắn Studio: '+str(e))
 def schedule_save(self,*args):
  if not self.loading:
   self.autosave.start()
   p=self.profile()
   kind='greeting' if self.sender() in (self.greeting_interval,self.auto_greeting) else 'message'
   if p and self.engine.state(p['id'])[kind]:
    self.engine.stop(p['id'],kind)
    self.engine.state(p['id'])[kind+'_status']='Đã lưu thay đổi · bấm Bật '+('Chào' if kind=='greeting' else 'nhắn mẫu')+' để áp dụng'
 def set_session(self,session_id):
  if str(session_id)==self.current_session_id:return
  if hasattr(self,'autosave') and self.autosave.isActive():self.autosave.stop();self.save(getattr(self,'active_profile',None),getattr(self,'active_session',self.current_session_id))
  self.current_session_id=str(session_id);self.refresh()
 def refresh(self):
  selected=self.profile();self.nick.blockSignals(True);self.nick.clear()
  if selected:self.nick.addItem(selected['name'],selected['id'])
  self.nick.blockSignals(False);self.fill()
 def session(self):return next((s for s in self.owner.data['sessions'] if s['id']==self.current_session_id),None)
 def profile(self):return next((p for p in self.studio.profiles if p.get('session')==self.current_session_id),None)
 def fill(self):
  if hasattr(self,'autosave') and self.autosave.isActive():
   self.autosave.stop();self.save(getattr(self,'active_profile',None),getattr(self,'active_session',self.current_session_id))
  p=self.profile();self.active_profile=p['id'] if p else None;self.active_session=self.current_session_id;self.loading=True
  p=self.profile();cfg=p.get('interaction',{}) if p else (self.session() or {}).get('studio_interaction',{});self.messages.setPlainText(cfg.get('messages',''));self.interval.setValue(cfg.get('interval',300));self.greeting_interval.setValue(cfg.get('greeting_interval',10));self.mouse.blockSignals(True);self.mouse.setChecked(p.get('allowMouse',True) if p else True);self.mouse.blockSignals(False);self.auto_message.setChecked(cfg.get('auto_message',False));self.auto_greeting.setChecked(cfg.get('auto_greeting',False));self.loading=False
 def save(self,profile_id=None,session_id=None):
  sid=session_id if isinstance(session_id,str) else self.current_session_id
  session=next((s for s in self.owner.data['sessions'] if s['id']==sid),None)
  p=self.studio.profile(profile_id) if isinstance(profile_id,str) else next((p for p in self.studio.profiles if p.get('session')==sid),None)
  config=dict(messages=self.messages.toPlainText(),interval=self.interval.value(),greeting_interval=self.greeting_interval.value(),auto_message=self.auto_message.isChecked(),auto_greeting=self.auto_greeting.isChecked())
  if session:session['studio_interaction']=config;write_json(self.owner.path,self.owner.data)
  if p:p['interaction']=config;p['allowMouse']=self.mouse.isChecked();self.studio.save()
 def mouse_change(self,value):
  # Change all copies, including queued commands: pause blocks new interaction work.
  self.studio.mouse_path.write_text('1' if value else '0',encoding='utf-8')
  for p in self.studio.profiles:p['allowMouse']=value
  self.engine.stop_all();self.studio.save()
 def start(self,kind):
  try:
   if kind=='greeting' and not (self.profile() or {}).get('vision',{}).get('enabled'):raise ValueError('Bấm Thiết lập đọc bằng ảnh và khoanh vùng trước khi bật Chào.')
   p=self.profile()
   if not p:raise ValueError('Bấm Kết nối LIVE Studio cho nick đang chọn trước.')
   self.save();self.engine.enable(self.studio.effective_profile(p),kind,p.get('interaction',{}))
  except Exception as e:QMessageBox.warning(self,'Tương tác Studio',str(e))
 def configure_vision(self):
  from studio_vision_panel import configure_vision
  configure_vision(self)
 def check_message(self):
  try:
   p=self.profile()
   if not p:raise ValueError('Kết nối cửa sổ Studio trước.')
   from studio_scheduler import execute,message_capability
   profile=self.studio.effective_profile(p);ok,reason=message_capability(profile)
   if not ok:self.message_status.setText(reason);return
   future=self.studio.pool.submit_priority(20,execute,profile,'chat_check');timer=QTimer(self)
   self.message_status.setText('Đang kiểm tra ô nhập và khung chat; không gửi tin…')
   def ready():
    if not future.done():return
    timer.stop();timer.deleteLater()
    try:
     result=future.result()
     if self.profile() and self.profile()['id']==p['id']:self.message_status.setText('Đọc được bản nháp và khung chat ✓' if result.get('readable') else 'Ô nhập chưa sẵn sàng')
    except Exception as e:
     if self.profile() and self.profile()['id']==p['id']:self.message_status.setText(str(e))
   timer.timeout.connect(ready);timer.start(200)
  except Exception as e:self.message_status.setText(str(e))
 def stop(self,kind):
  if self.profile():self.engine.stop(self.profile()['id'],kind)
 def tick(self):
  from studio_vision import ocr_model_info
  self.ocr_status.setText(ocr_model_info()[1])
  signature=tuple((p['id'],p['name']) for p in self.studio.profiles)
  if signature!=getattr(self,'signature',None):self.signature=signature;self.refresh()
  blocked={j['profile'] for j in self.studio.jobs if j['state'] in ('preparing','starting','stopping','recovering','attention','recovery_review')}
  profiles=[]
  for profile in self.studio.profiles:
   active=[j['end'] for j in self.studio.jobs if j['profile']==profile['id'] and j['state'] in ('running','starting','preparing','stopping','recovering','attention','recovery_review')]
   profiles.append({**self.studio.effective_profile(profile),'activeUntil':min(active) if active else 0})
  self.engine.tick(profiles,blocked)
  p=self.profile()
  if not p:self.message_status.setText('Chưa kết nối LIVE Studio');self.greeting_status.setText('Chưa kết nối LIVE Studio')
  if p:
   s=self.engine.state(p['id']);self.message_status.setText(s['message_status']);self.greeting_status.setText(s['greeting_status'])
 def shutdown(self):
  self.timer.stop();self.engine.stop_all()
  if self.autosave.isActive():
   try:self.save()
   except Exception as e:self.owner.log('Chưa lưu được tin nhắn Studio: '+str(e))
  self.autosave.stop()
