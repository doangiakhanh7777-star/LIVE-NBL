"""NBL LIVE 4.1 desktop console. Local sources, profiles, OBS and alerts."""
import copy
import html
import json
import logging
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from logging.handlers import RotatingFileHandler
from PySide6.QtCore import QTimer, Qt, QUrl, QDateTime
from PySide6.QtGui import QIcon, QDesktopServices, QPixmap
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget, QListWidgetItem, QTabWidget, QLineEdit, QTextEdit, QCheckBox, QComboBox, QSpinBox, QDoubleSpinBox, QFileDialog, QMessageBox, QFormLayout, QGroupBox, QSlider, QDateTimeEdit, QScrollArea, QGridLayout, QSizePolicy, QStyle, QToolButton, QMenu, QAbstractSpinBox, QDialog)
from PySide6.QtMultimedia import QMediaDevices
from model import load, validate, write_json, new_session
from obs_bridge import OBSBridge
from live_cycle import LiveCycle
from theme import STYLE
from chrome_bridge import ChromeBridge
from keep_awake import set_awake
from video_commands import dispatch_video_command
from session_binding import make_binding, resolve_binding
from notifications import NotificationSettings, Notifier
BASE = Path(__file__).resolve().parent
DATA = Path(os.environ.get('LOCALAPPDATA', str(Path.home()/'.local/share')))/'NBL_LIVE_2'

def button(text, callback, kind=''):
    b = QPushButton(text); b.setObjectName(kind); b.clicked.connect(callback); return b

class Console(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle('TOOL NBL LIVE • 4.1.11'); screen=QApplication.primaryScreen();self.resize(430,max(420,min(790,screen.availableGeometry().height()-60)) if screen else 790); self.setMinimumSize(400,120);self.setMaximumWidth(480);self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint,False)
        self.setWindowIcon(QIcon(str(BASE/'assets/logo_38.ico')))
        self.path = DATA/'profiles.json'
        self.startup_notices=[]
        self.data = load(self.path, self.startup_notices.append)
        self.processes = {}; self.errors = {}; self.selected = 0; self.loading = False
        self.alarm_window=None;self.phone_error=''
        self.phone_settings=NotificationSettings(DATA/'notifications.json');self.notifier=Notifier()
        try:self.phone_config=self.phone_settings.load()
        except Exception:
            self.phone_config=dict(enabled=False,chat_id='',token='');self.phone_error='Chưa đọc được thiết lập điện thoại. Nhập lại mã bot và lưu trên Windows.'
        self.notifier.configure(self.phone_config)
        self.logger=logging.getLogger('NBL_LIVE.'+uuid.uuid4().hex);self.logger.setLevel(logging.INFO);self.logger.propagate=False
        logdir=DATA/'logs';logdir.mkdir(parents=True,exist_ok=True)
        handler=RotatingFileHandler(logdir/'app.log',maxBytes=2_000_000,backupCount=3,encoding='utf-8');handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'));self.logger.addHandler(handler)
        self.obs = OBSBridge(); self.cycle = LiveCycle(); self.cycle_id = None; self.obs_active = False; self.obs_at = 0; self.last_poll = 0
        self.bridge = ChromeBridge(token_path=DATA/'pairing_token.txt'); self.bridge.start()
        self.chrome_available = self.bridge.server is not None
        self.compact = False; self.full_size = None
        central = QWidget(); self.setCentralWidget(central)
        layout = QVBoxLayout(central); layout.setContentsMargins(10,10,10,10); layout.setSpacing(8)
        header_box = QWidget(); header_box.setObjectName('header'); header = QHBoxLayout(header_box); header.setContentsMargins(10,6,8,6)
        logo = QLabel(); logo.setPixmap(QPixmap(str(BASE/'assets/logo.png')).scaled(46,46,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)); header.addWidget(logo)
        title = QLabel('NBL LIVE'); title.setObjectName('title'); header.addWidget(title); header.addStretch()
        self.fold_button = button('Thu gọn',self.toggle_compact); header.addWidget(self.fold_button)
        header.addWidget(button('■',self.emergency,'danger')); layout.addWidget(header_box)
        self.full_panel=QWidget(); body=QVBoxLayout(self.full_panel);body.setContentsMargins(0,0,0,0);body.setSpacing(8)
        self.sessions=QListWidget();self.sessions.hide();self.sessions.currentRowChanged.connect(self.switch)
        self.account_selector=QComboBox();self.account_selector.setObjectName('accountSelector');self.account_selector.setMinimumHeight(44);self.account_selector.currentIndexChanged.connect(self.sessions.setCurrentRow);body.addWidget(self.account_selector)
        self.account_status=QLabel('Chọn nick để bắt đầu');self.account_status.setObjectName('accountStatus');self.account_status.setWordWrap(True);body.addWidget(self.account_status)
        manage=QToolButton();manage.setText('Quản lý nick  ▾');manage.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup);menu=QMenu(manage)
        for text,callback in [('+ Thêm nick',self.add_session),('Xóa nick',self.remove_session),('Xuất cấu hình',self.export),('Nhập cấu hình',self.import_config),('Xuất gói chẩn đoán (không kèm mã bí mật)',self.export_diagnostics)]:menu.addAction(text,callback)
        manage.setMenu(menu);connect=QToolButton();connect.setText('Kết nối nick  ▾');connect.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup);connect_menu=QMenu(connect)
        connect_menu.addAction('Kết nối Chrome',lambda:self.navigation.setCurrentIndex(2))
        connect_menu.addAction('Kết nối LIVE Studio',lambda:self.studio_panel.connect_current())
        connect.setMenu(connect_menu);actions=QHBoxLayout();actions.addWidget(connect,1);actions.addWidget(manage,1);body.addLayout(actions)
        self.navigation=QComboBox();self.navigation.setMinimumHeight(42);body.addWidget(self.navigation)
        self.tabs=QTabWidget();self.tabs.tabBar().hide();self.navigation.currentIndexChanged.connect(self.tabs.setCurrentIndex);body.addWidget(self.tabs,1)
        self.build_video();self.build_script();self.build_chrome();self.build_pin_scripts();self.build_obs();self.build_schedule();self.build_tools()
        for form in self.findChildren(QFormLayout): form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        self.logbox=QTextEdit();self.logbox.setReadOnly(True);self.logbox.setMaximumHeight(80);self.logbox.hide();body.addWidget(self.logbox)
        body.addWidget(button('Hiện / ẩn nhật ký',lambda:self.logbox.setVisible(not self.logbox.isVisible())))
        layout.addWidget(self.full_panel,1)
        self.label=QLabel('Sẵn sàng');self.label.setWordWrap(True);layout.addWidget(self.label)
        from studio_panel import StudioPanel
        self.studio_panel=StudioPanel(self)
        self.page('Lịch phát LIVE').addWidget(self.studio_panel)
        from studio_chat_panel import StudioChatPanel
        self.studio_chat=StudioChatPanel(self,self.studio_panel)
        self.page('Tin nhắn & chào khách').addWidget(self.studio_chat)
        for widget in (self.live_minutes,self.rest_minutes):
            widget.lineEdit().setReadOnly(True);widget.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.PlusMinus);widget.setSuffix(' phút')
        self.ui_save_timer=QTimer(self);self.ui_save_timer.setSingleShot(True);self.ui_save_timer.setInterval(600);self.ui_save_timer.timeout.connect(self.autosave_current)
        for signal in (self.playlist.model().rowsInserted,self.playlist.model().rowsRemoved,self.playlist.model().rowsMoved):signal.connect(self.schedule_autosave)
        for signal in (self.account.textEdited,self.volume.valueChanged,self.loop.toggled,self.shuffle.toggled,self.mute.toggled,self.device.currentIndexChanged):signal.connect(self.schedule_autosave)
        self.refresh_list(); self.sessions.setCurrentRow(0); self.fill()
        self.timer = QTimer(self); self.timer.timeout.connect(self.tick); self.timer.start(1000)
        for notice in self.startup_notices:
            self.log(notice);QMessageBox.warning(self,'Đã khôi phục cấu hình',notice)
        if sys.platform=='win32' and (BASE/'ocr_vendor').is_dir():
            # 4.0: load the OCR models now so the first Studio send is not 5-10 s late.
            import threading
            def warm():
                from studio_vision import warmup
                warmup()
            threading.Thread(target=warm,daemon=True,name='ocr-warmup').start()
        if not self.chrome_available:
            self.log('Chrome chưa kết nối: cổng đang bận hoặc không mở được. Video và các mục khác vẫn hoạt động. Đóng chương trình chiếm cổng rồi mở lại app để kết nối Chrome.')
    def toggle_compact(self):
        if not self.compact:
            self.full_size=self.size();self.full_panel.hide();self.compact=True
            self.fold_button.setText('Mở');self.label.setMaximumHeight(34);self.resize(430,120)
        else:
            self.full_panel.show();self.compact=False;self.fold_button.setText('Thu gọn');self.label.setMaximumHeight(16777215)
            self.resize(self.full_size or self.size())
    def page(self, title):
        scroll=QScrollArea();scroll.setWidgetResizable(True)
        w=QWidget();layout=QVBoxLayout(w);layout.setContentsMargins(8,8,8,8);layout.setSpacing(10)
        scroll.setWidget(w);self.tabs.addTab(scroll,title);self.navigation.addItem(title);return layout
    def build_video(self):
        v = self.page('Video & âm thanh'); form = QFormLayout();form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows); self.account = QLineEdit(); form.addRow('Tên hiển thị của nick trong NBL LIVE', self.account); v.addLayout(form)
        self.playlist = QListWidget(); self.playlist.setMaximumHeight(140); v.addWidget(self.playlist,1)
        row = QGridLayout()
        for i,(text, action) in enumerate([('Thêm video',self.add_video),('Xóa video',self.remove_video),('↑',lambda:self.move_video(-1)),('↓',lambda:self.move_video(1))]): row.addWidget(button(text,action),i//2,i%2)
        v.addLayout(row)
        options = QHBoxLayout(); self.loop = QCheckBox('Lặp playlist vô hạn'); self.shuffle = QCheckBox('Xáo video mỗi vòng'); self.mute = QCheckBox('Tắt tiếng phiên này')
        options = QVBoxLayout()
        for w in (self.loop,self.shuffle,self.mute): options.addWidget(w)
        self.loop.setChecked(True); self.loop.hide()  # 4.1: playlist always loops
        v.addLayout(options)
        self.device = QComboBox(); self.device.addItem('Thiết bị mặc định của Windows','')
        for d in QMediaDevices.audioOutputs(): self.device.addItem(d.description(),bytes(d.id()).hex())
        self.audio_devices=QMediaDevices(self);self.audio_devices.audioOutputsChanged.connect(self.refresh_devices)
        form = QFormLayout();form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows); form.addRow('Đầu ra âm thanh riêng',self.device); self.volume = QSlider(Qt.Orientation.Horizontal); self.volume.setRange(0,100); form.addRow('Âm lượng',self.volume); v.addLayout(form)
        v.addWidget(button('🎧 Phát vào cáp ảo (máy không nghe, LIVE vẫn có tiếng)',self.use_virtual_cable,'primary'))
        note = QLabel('Nhiều phiên: chọn thiết bị / cáp âm thanh ảo riêng cho từng cửa sổ và chọn đúng đầu vào trong LIVE Studio. Tắt nguồn thu âm thanh máy dùng chung. App không tự tạo cáp âm thanh ảo.'); note.setWordWrap(True); note.setObjectName('subtitle'); v.addWidget(note)
        row = QGridLayout()
        for i,(text, action, kind) in enumerate( [('LƯU PHIÊN',self.save_current,''),('MỞ & PHÁT',lambda:self.command('play'),'primary'),('Tạm dừng / tiếp',lambda:self.command('pause'),''),('Video tiếp',lambda:self.command('next'),''),('Dừng video',lambda:self.command('stop'),'danger')]):row.addWidget(button(text,action,kind),i//2,i%2)
        v.addLayout(row)
    def use_virtual_cable(self):
        # 4.1.11 (owner, 26/10/2026): NBL VIDEO plays into a VB-CABLE, Studio takes its
        # sound from the cable — the PC speakers stay quiet, the LIVE keeps the sound.
        from pin_scripts import pick_cable
        devices=[(self.device.itemText(i),self.device.itemData(i)) for i in range(self.device.count())]
        mine=self.current().get('id');used=[s.get('device') for s in self.data['sessions'] if s.get('id')!=mine and s.get('device')]
        found=pick_cable(devices,used)
        if not found:
            cables=pick_cable(devices,())
            QMessageBox.information(self,'Cáp âm thanh ảo',('Máy có cáp ảo nhưng nick khác đang dùng rồi. 2 nick phát cùng lúc cần 2 cáp riêng (VB-CABLE A+B), nếu không tiếng 2 LIVE trộn vào nhau.' if cables else 'Máy chưa có cáp âm thanh ảo.')+'\n\nCài VB-CABLE (miễn phí, vb-audio.com) → khởi động lại máy → bấm lại nút này.');return
        index=self.device.findData(found[0]);self.device.setCurrentIndex(index);self.save_current()
        QMessageBox.information(self,'Đã chọn cáp ảo','NBL VIDEO của nick này giờ phát vào: '+found[1]+' (loa máy sẽ im).\n\nTrong TikTok LIVE Studio: thêm nguồn âm thanh / micro là "'+found[2]+'" và TẮT thu âm thanh hệ thống (để không lặp tiếng).\n\nMuốn nghe thử: Windows → Âm thanh → Ghi âm → '+found[2]+' → Thuộc tính → Nghe → tick "Nghe thiết bị này".')
    def build_pin_scripts(self):
        # 4.1.11 (owner, 26/10/2026): "Kịch bản ghim giỏ hàng" — watch a clip, stop, plant
        # flags (product name + how long), saved per clip; used by Chrome during the LIVE.
        import pin_scripts
        self.pin_store=pin_scripts.Store(DATA/'kich_ban_ghim.json')
        v=self.page('Kịch bản ghim giỏ hàng')
        info=QLabel('Mở clip ra xem như YouTube: phát, dừng, tua. Thấy chỗ hợp thì bấm 🚩 Cắm cờ, chọn tên sản phẩm và giữ bao lâu, rồi Lưu. Kịch bản lưu riêng từng clip. Khi LIVE phát clip đó, Chrome tự ghim chèn đúng giây đã cắm cờ, xong ghim xáo trộn chạy tiếp.');info.setWordWrap(True);v.addWidget(info)
        self.script_clips=QListWidget();self.script_clips.setMinimumHeight(180);self.script_clips.itemDoubleClicked.connect(lambda item:self.open_pin_script());v.addWidget(self.script_clips,1)
        row=QGridLayout()
        for i,(text,action,kind) in enumerate([('🎬 Soạn kịch bản clip đã chọn',self.open_pin_script,'primary'),('Chọn file video khác…',self.open_pin_script_file,''),('Xóa kịch bản clip đã chọn',self.delete_pin_script,'danger'),('Làm mới danh sách',self.refresh_pin_scripts,'')]):row.addWidget(button(text,action,kind),i//2,i%2)
        v.addLayout(row);self.navigation.currentIndexChanged.connect(lambda i:self.refresh_pin_scripts());self.refresh_pin_scripts()
    def refresh_pin_scripts(self):
        if not hasattr(self,'script_clips'):return
        clips=[];selected=self.script_clips.currentItem().data(Qt.ItemDataRole.UserRole) if self.script_clips.currentItem() else None
        for s in self.data.get('sessions',[]):
            for clip in s.get('playlist',[]):
                if clip not in clips:clips.append(clip)
        for item in self.pin_store.load().values():
            if item.get('path') and item['path'] not in clips:clips.append(item['path'])
        self.script_clips.clear()
        for clip in clips:
            n=len(self.pin_store.entries(clip));missing=not Path(clip).exists()
            it=QListWidgetItem(('✅ '+str(n)+' cờ · ' if n else '◻ chưa có kịch bản · ')+Path(clip).name+(' (không thấy file)' if missing else ''));it.setData(Qt.ItemDataRole.UserRole,clip);self.script_clips.addItem(it)
            if clip==selected:self.script_clips.setCurrentItem(it)
    def cart_titles(self):
        titles=[]
        try:
            snap=self.bridge.snapshot();binding=self.current().get('chrome_binding')
            from session_binding import resolve_binding
            client=resolve_binding(binding,snap) if binding else None
            for key,state in ([(client,snap.get(client,{}))] if client else list(snap.items())):
                for t in state.get('cartTitles') or []:
                    if t not in titles:titles.append(t)
        except Exception:pass
        return titles
    def open_pin_script(self,clip=None):
        clip=clip or (self.script_clips.currentItem().data(Qt.ItemDataRole.UserRole) if self.script_clips.currentItem() else None)
        if not clip:QMessageBox.information(self,'Kịch bản ghim','Chọn một clip trong danh sách (hoặc Chọn file video khác…).');return
        if not Path(clip).exists():QMessageBox.warning(self,'Kịch bản ghim','Không thấy file clip: '+clip);return
        try:
            from pin_script_editor import PinScriptEditor
            PinScriptEditor(self,clip,self.pin_store,self.cart_titles).exec()
        except Exception as error:QMessageBox.warning(self,'Kịch bản ghim','Chưa mở được trình xem clip: '+str(error))
        self.refresh_pin_scripts()
    def open_pin_script_file(self):
        path,_=QFileDialog.getOpenFileName(self,'Chọn clip','','Video (*.mp4 *.mkv *.mov *.avi *.webm);;Tất cả (*)')
        if path:self.open_pin_script(path)
    def delete_pin_script(self):
        item=self.script_clips.currentItem()
        if item and QMessageBox.question(self,'Xóa kịch bản','Xóa kịch bản ghim của clip '+Path(item.data(Qt.ItemDataRole.UserRole)).name+'?')==QMessageBox.StandardButton.Yes:
            self.pin_store.delete(item.data(Qt.ItemDataRole.UserRole));self.refresh_pin_scripts()
    def refresh_devices(self):
        selected=self.device.currentData() or '';self.device.blockSignals(True);self.device.clear();self.device.addItem('Thiết bị mặc định của Windows','')
        for d in QMediaDevices.audioOutputs():self.device.addItem(d.description(),bytes(d.id()).hex())
        index=self.device.findData(selected)
        if selected and index<0:self.device.addItem('Thiết bị đã mất — chọn lại',selected);index=self.device.count()-1
        self.device.setCurrentIndex(max(0,index));self.device.blockSignals(False)
    def build_script(self):
        v=self.page('Xem nội dung trên Chrome');self.pins=QTextEdit();self.rules=QTextEdit();self.messages=QTextEdit();self.messages.hide()
        note=QLabel('Chỉnh ghim và quy tắc trả lời trong tiện ích Chrome. Bản sao bên dưới tự cập nhật khi kết nối đúng nick. Nhắn định kỳ chỉnh ở Tin nhắn & chào khách.');note.setWordWrap(True);v.addWidget(note)
        for title,w in [('Sản phẩm đã chọn để ghim',self.pins),('Quy tắc trả lời trên Chrome',self.rules)]:v.addWidget(QLabel(title));w.setReadOnly(True);w.setMaximumHeight(150);v.addWidget(w)
        v.addWidget(button('Sao chép mẫu tin từ bản cũ',lambda:QApplication.clipboard().setText(self.messages.toPlainText())))
        v.addStretch()
    def build_chrome(self):
        v=self.page('Giỏ hàng & trả lời · Chrome')
        info=QLabel('Giỏ hàng, chọn bộ sản phẩm, ghim và trả lời bình luận đều thực hiện trên Chrome. Cài tiện ích một lần; thiết lập các nút được dùng chung, nội dung lưu riêng theo nick.');info.setWordWrap(True);v.addWidget(info)
        self.pair_code=QLineEdit(self.bridge.token);self.pair_code.setReadOnly(True);v.addWidget(QLabel('Mã ghép đôi — dán vào tiện ích Chrome trên máy này'));v.addWidget(self.pair_code)
        v.addWidget(button('Sao chép mã',lambda:QApplication.clipboard().setText(self.bridge.token)))
        v.addWidget(button('Mở thư mục tiện ích',lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(BASE/'CHROME_NBL_LIVE')))))
        v.addWidget(button('Mở bảng LIVE',lambda:QDesktopServices.openUrl(QUrl('https://shop.tiktok.com/streamer/live/product/dashboard'))))
        self.chrome_clients=QComboBox();v.addWidget(QLabel('Chrome đang kết nối với app'));v.addWidget(self.chrome_clients)
        self.chrome_binding_label=QLabel('Chưa gắn tab cho phiên này');self.chrome_binding_label.setWordWrap(True);v.addWidget(self.chrome_binding_label)
        v.addWidget(button('Dùng Chrome này cho nick đang chọn',self.bind_chrome,'primary'))
        v.addWidget(button('Ngắt liên kết Chrome của nick này',self.unbind_chrome))
        self.chrome_owner=QLineEdit();self.chrome_interval=QSpinBox();self.chrome_interval.setRange(60,86400);self.chrome_interval.setValue(300)
        self.chrome_scheduled=QTextEdit();self.chrome_repeat=QCheckBox();self.chrome_cycle=QLineEdit('00:10:00');self.chrome_reply=QComboBox();self.chrome_reply.addItem('Tự gửi theo quy tắc','auto');self.chrome_reply.addItem('Gợi ý để duyệt trên Chrome','suggest');self.chrome_cooldown=QSpinBox();self.chrome_cooldown.setRange(15,86400);self.chrome_cooldown.setValue(60)
        for w in (self.chrome_owner,self.chrome_interval,self.chrome_scheduled,self.chrome_repeat,self.chrome_cycle,self.chrome_reply,self.chrome_cooldown):w.hide()
        self.chrome_status={}
        for key,title in [('pin','Ghim sản phẩm'),('reply','Trả lời bình luận')]:
            box=QGroupBox(title);f=QVBoxLayout(box);lab=QLabel('Chưa bật');lab.setWordWrap(True);self.chrome_status[key]=lab;f.addWidget(lab)
            row=QHBoxLayout();row.addWidget(button('BẬT / THỬ LẠI',lambda checked=False,k=key:self.chrome_action(k,'start'),'primary'));row.addWidget(button('DỪNG',lambda checked=False,k=key:self.chrome_action(k,'stop'),'danger'));f.addLayout(row);v.addWidget(box)
        self.chrome_sync_label=QLabel('Đang chờ cấu hình từ Chrome');self.chrome_sync_label.setWordWrap(True);v.addWidget(self.chrome_sync_label)
        note=QLabel('Ghim và trả lời dùng thiết lập lưu trực tiếp trên tiện ích Chrome. Nhắn định kỳ dùng LIVE Studio ở mục Tin nhắn & chào khách. Trong tiện ích, bấm Chọn ô nhập tin nhắn, Chọn nút gửi… một lần; các lần sau app nhớ lại. Không cần giữ tab ở phía trước; Chrome, tab và máy vẫn phải hoạt động.');note.setWordWrap(True);v.addWidget(note)
    def chrome_config(self):
        return dict(owner=self.chrome_owner.text().strip(),repeatPins='on' if self.chrome_repeat.isChecked() else 'off',cycle=self.chrome_cycle.text().strip(),replyMode=self.chrome_reply.currentData(),cooldown=str(self.chrome_cooldown.value()))
    def save_chrome(self):
        self.collect();self.current()['chrome']={**self.current().get('chrome',{}),**self.chrome_config()};write_json(self.path,self.data);self.log('Đã lưu thiết lập Chrome theo phiên.')
    def bind_chrome(self):
        try:
            client=self.chrome_clients.currentData();clients=self.bridge.snapshot()
            if client not in clients:raise ValueError('Chọn tab đã ghép đôi với app trước.')
            state=clients[client]
            if state.get('accountVerified') is False or state.get('account') in ('Chưa chọn tài khoản','Chưa hiệu chỉnh','Không đọc được trang','Đang đọc trang','Chưa đăng nhập','Chưa xác định',''):
                raise ValueError(self.chrome_account_hint(state.get('account','')))
            binding=make_binding(client,state)
            for s in self.data['sessions']:
                if s is not self.current() and resolve_binding(s.get('chrome_binding'),clients)==client:raise ValueError('Tab này đã gắn với phiên '+str(s['number'])+'. Bỏ gắn ở phiên đó trước.')
            old=resolve_binding(self.current().get('chrome_binding'),clients)
            if old and old!=client:self.bridge.command(old,dict(action='stop',module='all'))
            self.current().pop('chrome_login_binding',None);self.current()['chrome_binding']=binding;self.current()['account']=binding['account'];self.account.setText(binding['account']);write_json(self.path,self.data);self.refresh_list();self.fill();self.log('Đã kết nối Chrome với nick '+str(self.current()['number']))
        except Exception as e:QMessageBox.warning(self,'Chrome',str(e))
    def unbind_chrome(self):
        client=resolve_binding(self.current().get('chrome_binding'),self.bridge.snapshot())
        if client:self.bridge.command(client,dict(action='stop',module='all'))
        self.current().pop('chrome_binding',None);write_json(self.path,self.data);self.chrome_tick()
    def chrome_action(self,key,action):
        try:
            if not self.chrome_available:raise ValueError('Cầu nối Chrome chưa mở được. Các mục khác vẫn chạy; kiểm tra cổng kết nối rồi mở lại app.')
            self.save_chrome();binding=self.current().get('chrome_binding');client=resolve_binding(binding,self.bridge.snapshot())
            if not binding:raise ValueError('Gắn tab Chrome với phiên này trước khi bật.')
            if not client:raise ValueError('Tab/tài khoản đã gắn không còn kết nối. Không gửi lệnh sang tài khoản khác. Ghép đôi lại hoặc gắn lại đúng tab.')
            self.bridge.command(client,dict(action=action,module=key,expectedAccount=binding['account']));self.log('Đã gửi '+action+' · '+key+'; chờ Chrome xác nhận.')
        except Exception as e:QMessageBox.warning(self,'Chrome',str(e))
    def chrome_tick(self,reset_selection=False):
        clients=self.bridge.snapshot();binding=self.current().get('chrome_binding');resolved=resolve_binding(binding,clients)
        selected=resolved if reset_selection else self.chrome_clients.currentData()
        if selected not in clients:selected=resolved
        if not self.chrome_clients.view().isVisible():
            self.chrome_clients.blockSignals(True);self.chrome_clients.clear();self.chrome_clients.addItem('Chọn tab Chrome',None)
            for client,st in clients.items():self.chrome_clients.addItem(st.get('account','Chưa hiệu chỉnh')+' · tab '+str(st.get('tab','?')),client)
            index=self.chrome_clients.findData(selected);self.chrome_clients.setCurrentIndex(index if index>=0 else 0);self.chrome_clients.blockSignals(False)
        st=clients.get(resolve_binding(binding,clients),{}) if binding else {}
        self.account_status.setText(('Chrome: đã kết nối · ' if st else 'Chrome: chưa kết nối · ')+(self.studio_panel.connection_status() if hasattr(self,'studio_panel') else 'Studio: chưa kết nối'))
        self.chrome_binding_label.setText(('Đã gắn: '+binding['account']+' · tab '+str(binding['tab'])+(' · đang kết nối' if st else ' · chưa có kết nối đúng tab/tài khoản')) if binding else 'Chưa gắn tab cho phiên này')
        if st and st.get('configAck'):
            cfg=st.get('config',{});self.current()['chrome']={**self.current().get('chrome',{}),**cfg};self.chrome_sync_label.setText('Đã tự lưu cấu hình Chrome · '+st.get('account',''))
            self.pins.setPlainText(cfg.get('pins',self.pins.toPlainText()));self.rules.setPlainText(cfg.get('rules',self.rules.toPlainText()))
        for key,lab in self.chrome_status.items():
            item=st.get('modules',{}).get(key,{})
            lab.setText(item.get('error') or ((item.get('detail') or 'Đang chạy') if item.get('running') else 'Đã dừng') if st else 'Mất / chưa có kết nối')
        for msg in self.bridge.drain():self.log(msg)
    def build_obs(self):
        v=self.page('Nâng cao · OBS'); group=QGroupBox('Kết nối OBS WebSocket'); f=QFormLayout(group)
        settings=self.data.get('settings',{})
        self.host=QLineEdit(settings.get('obs_host','127.0.0.1'));self.port=QSpinBox();self.port.setRange(1,65535);self.port.setValue(settings.get('obs_port',4455));self.password=QLineEdit();self.password.setEchoMode(QLineEdit.EchoMode.Password)
        for label,w in [('Địa chỉ',self.host),('Cổng',self.port),('Mật khẩu (không lưu)',self.password)]:f.addRow(label,w)
        f.addRow(button('Kết nối',lambda:self.obs.submit('connect',self.host.text(),self.port.value(),self.password.text())));v.addWidget(group)
        f=QFormLayout();self.live_minutes=QDoubleSpinBox();self.live_minutes.setRange(.5,1440);self.live_minutes.setValue(settings.get('live_minutes',60));self.rest_minutes=QDoubleSpinBox();self.rest_minutes.setRange(.2,1440);self.rest_minutes.setValue(settings.get('rest_minutes',5));self.repeat=QCheckBox('Lặp chu kỳ và xáo playlist');self.repeat.setChecked(settings.get('repeat',False));f.addRow('Phút phát',self.live_minutes);f.addRow('Phút nghỉ',self.rest_minutes);f.addRow(self.repeat);v.addLayout(f)
        self.obs_label=QLabel('Chưa kết nối OBS');v.addWidget(self.obs_label)
        row=QVBoxLayout();row.addWidget(button('Bắt đầu lịch cho phiên đã chọn',self.start_cycle,'primary'));row.addWidget(button('Hủy lịch',self.cancel_cycle,'danger'));v.addLayout(row)
        note=QLabel('Điều khiển OBS đã được cấu hình stream. Không tự bấm Phát LIVE / Kết thúc trong TikTok LIVE Studio. Một kết nối OBS phục vụ một lịch. Chrome cần kiểm tra và bật lại sau mỗi phiên LIVE mới.');note.setWordWrap(True);v.addWidget(note);v.addStretch()
    def build_schedule(self):
        v=self.page('Nâng cao · hẹn giờ'); self.jobs=QListWidget();v.addWidget(self.jobs)
        self.when=QDateTimeEdit(QDateTime.currentDateTime().addSecs(60));self.when.setCalendarPopup(True);self.when.setDisplayFormat('dd/MM/yyyy HH:mm:ss');v.addWidget(self.when)
        self.job_action=QComboBox()
        for label,action in [('Phát playlist','play'),('Dừng video','stop'),('Bật stream OBS','obs_start'),('Tắt stream OBS','obs_stop')]:self.job_action.addItem(label,action)
        v.addWidget(self.job_action);v.addWidget(button('Thêm lịch cho phiên đang chọn',self.add_job,'primary'));v.addWidget(button('Xóa lịch đã chọn',self.remove_job))
        lab=QLabel('Theo giờ máy Windows. App và máy phải đang mở. Lệnh quá hạn trên 30 giây được bỏ qua. OBS phải kết nối sẵn. Không chạy cùng lịch chu kỳ OBS.');lab.setWordWrap(True);v.addWidget(lab);self.render_jobs()
    def render_jobs(self):
        self.jobs.clear()
        for j in self.data.get('jobs',[]):
            self.jobs.addItem(time.strftime('%d/%m %H:%M:%S',time.localtime(j['at']))+' • '+j['action']+' • phiên '+str(j['number'])+' • '+j.get('state','pending'))
    def add_job(self):
        at=self.when.dateTime().toSecsSinceEpoch()
        if at<=time.time():QMessageBox.warning(self,'Chưa thêm','Chọn thời gian tương lai.');return
        self.collect();s=self.current();self.data.setdefault('jobs',[]).append(dict(id=uuid.uuid4().hex,session=s['id'],number=s['number'],action=self.job_action.currentData(),at=at,state='pending'));write_json(self.path,self.data);self.render_jobs()
    def remove_job(self):
        i=self.jobs.currentRow()
        if i>=0:del self.data['jobs'][i];write_json(self.path,self.data);self.render_jobs()
    def scheduled_tick(self):
        changed=False
        for j in self.data.get('jobs',[]):
            if j['state']!='pending' or time.time()<j['at']:continue
            j['state']='skipped' if time.time()-j['at']>30 else 'dispatched';changed=True
            s=next((s for s in self.data['sessions'] if s['id']==j['session']),None)
            if not s or j['state']=='skipped':self.log('Bỏ lịch quá hạn hoặc phiên không tồn tại.');continue
            # Persist before dispatch so a restart cannot execute a job twice.
            write_json(self.path,self.data)
            if j['action'].startswith('obs_'):
                if self.cycle.state!='idle' or not self.obs.connected:j['state']='skipped';self.log('Bỏ lịch OBS: đang chạy chu kỳ hoặc chưa kết nối.')
                elif not self.obs.submit('start' if j['action']=='obs_start' else 'stop'):j['state']='failed';self.log('Lịch OBS chưa gửi được: hàng đợi đang đầy.')
            else:
                try:self.command(j['action'],False,s)
                except Exception:j['state']='failed';self.log('Lịch video chưa thực hiện được. Kiểm tra nguồn video và quyền đọc file.')
        if changed:write_json(self.path,self.data);self.render_jobs()
    def open_reports(self,kind):
        folder=DATA/'bao_cao'/kind;folder.mkdir(parents=True,exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def build_tools(self):
        v=self.page('Thiết lập & cảnh báo')
        self.awake=QCheckBox('Giữ máy thức · cho phép tắt màn hình');self.awake.setChecked(self.data.get('settings',{}).get('keep_awake',True));self.awake.toggled.connect(set_awake);v.addWidget(self.awake);set_awake(self.awake.isChecked())
        for title,desc,action in [
            ('Bật bộ báo động LIVE','Phát chuông khi đọc được cảnh báo cần xác minh; hiển thị cửa sổ cần chú ý.',self.open_alarm),
            ('Mở thư mục tiện ích Chrome','Chrome → chrome://extensions → Chế độ nhà phát triển → Tải tiện ích đã giải nén → chọn CHROME_NBL_LIVE.',lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(BASE/'CHROME_NBL_LIVE')))),
            ('Mở hướng dẫn','Cách cài tiện ích, tách âm thanh và nhận thông báo điện thoại.',lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(BASE/'HUONG_DAN_SU_DUNG.pdf' if (BASE/'HUONG_DAN_SU_DUNG.pdf').exists() else BASE/'HUONG_DAN_4.1.txt')))),
            ('Mở nhật ký','Nhật ký các phiên, Chrome, OBS và cảnh báo.',lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(DATA/'logs')))),
            ('Mở báo cáo hoạt động','Việc NBL đã làm: gửi tin, chào khách, tự đóng thông báo, ghép cửa sổ trò chuyện. Giữ 100 báo cáo mới nhất.',lambda:self.open_reports('hoat_dong')),
            ('Mở báo cáo lỗi','Việc chưa làm được, kèm ảnh Studio lúc lỗi. Giữ 100 báo cáo mới nhất, riêng với báo cáo hoạt động.',lambda:self.open_reports('loi'))]:
            v.addWidget(button(title,action,'primary'));lab=QLabel(desc);lab.setWordWrap(True);v.addWidget(lab)
        group=QGroupBox('Thông báo Android qua Telegram');form=QFormLayout(group)
        self.phone_enabled=QCheckBox('Gửi cảnh báo về điện thoại');self.phone_enabled.setChecked(self.phone_config['enabled']);form.addRow(self.phone_enabled)
        self.phone_token=QLineEdit(self.phone_config['token']);self.phone_token.setEchoMode(QLineEdit.EchoMode.Password);form.addRow('Token bot Telegram',self.phone_token)
        self.phone_chat=QLineEdit(self.phone_config['chat_id']);form.addRow('Chat ID nhận',self.phone_chat)
        form.addRow(button('Lưu thông báo điện thoại',self.save_phone));form.addRow(button('THỬ THÔNG BÁO ĐIỆN THOẠI',self.test_phone))
        self.phone_status=QLabel(self.phone_error or ('Đã bật' if self.phone_config['enabled'] else 'Chưa bật'));self.phone_status.setWordWrap(True);form.addRow(self.phone_status)
        note=QLabel('Trên Android, mở Telegram và nhắn /start cho bot nhận cảnh báo. Điền Token và Chat ID, lưu rồi thử thông báo.');note.setWordWrap(True);form.addRow(note);v.addWidget(group)
        v.addStretch()
    def save_phone(self):
        try:
            self.phone_config=self.phone_settings.save(self.phone_enabled.isChecked(),self.phone_chat.text(),self.phone_token.text());self.notifier.configure(self.phone_config)
            self.phone_status.setText('Đã lưu · '+('đang bật' if self.phone_config['enabled'] else 'đã tắt'))
            return True
        except Exception as e:self.phone_status.setText(str(e));return False
    def test_phone(self):
        if not self.save_phone():return
        if not self.notifier.publish('test','NBL LIVE: thông báo thử từ máy tính.',test=True):self.phone_status.setText('Bật và lưu thiết lập điện thoại trước khi thử.')
        else:self.phone_status.setText('Đang gửi thông báo thử…')
    def open_alarm(self):
        from NBL_CANH_BAO.alarm import Alarm
        if self.alarm_window is None:self.alarm_window=Alarm(parent=self,on_alert=self.on_warning)
        self.alarm_window.show();self.alarm_window.start()
    def on_warning(self,warnings):
        lines=[str(w.get('title') or w.get('process') or 'LIVE Studio')+(' · PID '+str(w['pid']) if w.get('pid') else '')+(' · '+str(w['countdown']) if w.get('countdown') else '') for w in warnings]
        text='NBL LIVE cần chú ý:\n'+'\n'.join(lines)
        key='|'.join(sorted(str(w.get('process',''))+':'+str(w.get('handle') or w.get('pid') or '')+':'+str(w.get('title','')) for w in warnings))
        self.log(text);self.notifier.publish(key,text)
        if hasattr(self,'studio_panel'):
            affected={str(w.get('pid','')) for w in warnings}
            for p in self.studio_panel.profiles:
                if p['pid'] not in affected:continue
                if hasattr(self,'studio_chat'):
                    for kind in ('message','greeting'):self.studio_chat.engine.stop(p['id'],kind)
                for job in self.studio_panel.jobs:
                    if job['profile']==p['id'] and job['state'] in ('preparing','starting','running','recovering'):
                        self.studio_panel.cancel_pending_starts(job);self.studio_panel.stop_chrome(job);job['state']='attention';job['error']='Cần xử lý cảnh báo Studio'
                self.studio_panel.save();self.studio_panel.render()
    def current(self):return self.data['sessions'][self.selected]
    def log(self,text):
        text=str(text)
        secret=self.phone_config.get('token','')
        if secret:text=text.replace(secret,'[ẩn mã bot]')
        self.logbox.append(html.escape(time.strftime('%H:%M:%S')+'  '+text));self.logger.info(text)
        if self.logbox.document().blockCount()>500:self.logbox.document().setMaximumBlockCount(500)
    def refresh_list(self):
        self.sessions.blockSignals(True);self.account_selector.blockSignals(True);self.sessions.clear();self.account_selector.clear()
        for account in self.data['sessions']:
            name=account.get('chrome_binding',{}).get('account') or account['account'] or 'Nick mới · chưa kết nối'
            label=f"{account['number']:02d}  {name}"
            self.sessions.addItem(label);self.account_selector.addItem(label,account['id'])
        self.sessions.setCurrentRow(self.selected);self.account_selector.setCurrentIndex(self.selected);self.sessions.blockSignals(False);self.account_selector.blockSignals(False)
    def schedule_autosave(self,*args):
        if not self.loading and hasattr(self,'ui_save_timer'):self.ui_save_timer.start()
    def autosave_current(self):
        try:
            self.collect();validate(self.data);write_json(self.path,self.data);self.refresh_list()
            if self.current()['id'] in self.processes:self.command('settings',False)
        except Exception as error:self.log('Chưa tự lưu được thiết lập nick: '+str(error))
    @staticmethod
    def chrome_account_hint(account):
        """4.1.1: QR login was removed; say exactly why the tab cannot be bound yet."""
        account=str(account or '')
        if account in ('','Chưa đăng nhập'):
            return ('Tab Chrome này chưa ở trang Bảng điều khiển LIVE.\n'
                    'Đăng nhập TikTok Shop trên Chrome như bình thường, mở trang Bảng điều khiển LIVE '
                    '(nút "Mở bảng LIVE"), đợi trang tải xong rồi bấm lại.')
        if account in ('Chưa chọn tài khoản','Chưa hiệu chỉnh','Chưa xác định'):
            return ('Tiện ích chưa đọc được tên nick trên trang LIVE.\n'
                    'Trên trang Bảng điều khiển LIVE: mở bảng NBL → "Chọn các nút trên trang — làm một lần" → '
                    'bấm Chọn ở mục "Tên tài khoản", rồi bấm vào tên nick hiện trên trang. Xong bấm lại.')
        return ('Trang LIVE đang tải hoặc chưa đọc được (' + account + ').\n'
                'Đợi vài giây rồi bấm lại. Vẫn vậy thì tải lại trang LIVE (F5).')
    def discover_accounts(self,clients):
        if self.loading or (hasattr(self,'ui_save_timer') and self.ui_save_timer.isActive()):return
        changed=False
        placeholders={'Chưa chọn tài khoản','Chưa hiệu chỉnh','Không đọc được trang','Đang đọc trang','Chưa đăng nhập','Chưa xác định',''}
        for client,state in clients.items():
            name=state.get('account','')
            if state.get('accountVerified') is not True or name in placeholders or not isinstance(name,str) or not state.get('instance') or type(state.get('tab')) is not int:continue
            # One account in one Chrome profile is a binding; duplicates require an explicit choice.
            matches=[x for x in clients.values() if x.get('instance')==state['instance'] and x.get('account')==name]
            if len(matches)!=1:continue
            bound=[account for account in self.data['sessions'] if account.get('chrome_binding',{}).get('instance')==state['instance'] and account.get('chrome_binding',{}).get('account')==name]
            if bound:continue
            # Never reassign an existing browser/tab slot to a newly logged-in account.
            if any(account.get('chrome_binding',{}).get('instance')==state['instance'] and account.get('chrome_binding',{}).get('tab')==state['tab'] for account in self.data['sessions']):continue
            candidates=[account for account in self.data['sessions'] if not account.get('chrome_binding') and account['account']==name]
            if len(candidates)>1:continue
            if candidates:account=candidates[0]
            else:
                empty=[account for account in self.data['sessions'] if not account.get('chrome_binding') and not account['account'] and not account['playlist']]
                if empty:account=empty[0]
                elif len(self.data['sessions'])<16:
                    used={account['number'] for account in self.data['sessions']};account=new_session(next(i for i in range(1,100) if i not in used));self.data['sessions'].append(account)
                else:continue
            account['chrome_binding']=make_binding(client,state);account['account']=name;changed=True
        if changed:
            write_json(self.path,self.data);self.refresh_list()
            if not self.loading:self.fill()
    def collect(self):
        if self.loading or not self.data['sessions']:return
        s=self.current();s['chrome']={**s.get('chrome',{}),**self.chrome_config()};s.update(account=self.account.text().strip(),playlist=[self.playlist.item(i).text() for i in range(self.playlist.count())],volume=self.volume.value(),device=self.device.currentData() or '',mute=self.mute.isChecked(),loop=True,shuffle=self.shuffle.isChecked(),pins=self.pins.toPlainText(),rules=self.rules.toPlainText(),messages=self.messages.toPlainText())
        self.data['settings']=dict(keep_awake=self.awake.isChecked(),obs_host=self.host.text().strip(),obs_port=self.port.value(),live_minutes=self.live_minutes.value(),rest_minutes=self.rest_minutes.value(),repeat=self.repeat.isChecked())
    def save_current(self):
        self.collect();validate(self.data);write_json(self.path,self.data);self.refresh_list();self.log('Đã lưu phiên '+str(self.current()['number']))
        if self.current()['id'] in self.processes:self.command('settings',save=False)
    def fill(self):
        self.loading=True;s=self.current();self.account.setText(s['account']);self.playlist.clear();self.playlist.addItems(s['playlist']);self.volume.setValue(s['volume']);self.mute.setChecked(s['mute']);self.loop.setChecked(True);self.shuffle.setChecked(s['shuffle']);self.device.setCurrentIndex(max(0,self.device.findData(s['device'])))
        if s['device'] and self.device.findData(s['device'])<0:
            self.device.addItem('Thiết bị đã mất — chọn lại',s['device']);self.device.setCurrentIndex(self.device.count()-1)
        for key,w in [('pins',self.pins),('rules',self.rules),('messages',self.messages)]:w.setPlainText(s[key])
        c=s.get('chrome',{})
        self.chrome_owner.setText(c.get('owner',s.get('account','')))
        self.chrome_interval.setValue(int(c.get('interval',300)))
        self.chrome_scheduled.setPlainText(c.get('scheduled',''))
        self.chrome_repeat.setChecked(c.get('repeatPins')=='on');self.chrome_cycle.setText(c.get('cycle','00:10:00'))
        self.chrome_reply.setCurrentIndex(max(0,self.chrome_reply.findData(c.get('replyMode','auto'))));self.chrome_cooldown.setValue(int(c.get('cooldown',60)))
        self.loading=False
        self.account_selector.blockSignals(True);self.account_selector.setCurrentIndex(self.selected);self.account_selector.blockSignals(False)
        if hasattr(self,'studio_panel'):self.studio_panel.set_session(s['id'])
        if hasattr(self,'studio_chat'):self.studio_chat.set_session(s['id'])
        self.chrome_tick(reset_selection=True)
    def switch(self,index):
        if index<0:return
        if hasattr(self,'ui_save_timer') and self.ui_save_timer.isActive():self.ui_save_timer.stop();self.autosave_current()
        if not self.loading:self.current()['chrome']={**self.current().get('chrome',{}),**self.chrome_config()}
        self.collect();self.selected=index;self.fill()
    def add_session(self):
        if len(self.data['sessions'])>=16:QMessageBox.information(self,'Giới hạn','Tối đa 16 phiên cấu hình; số phiên phát đồng thời tùy sức máy.');return
        self.collect();used={s['number'] for s in self.data['sessions']};n=next(i for i in range(1,100) if i not in used);self.data['sessions'].append(new_session(n));self.selected=len(self.data['sessions'])-1;write_json(self.path,self.data);self.refresh_list();self.fill()
    def remove_session(self):
        if hasattr(self,'studio_panel') and any(p['session']==self.current()['id'] for p in self.studio_panel.profiles):QMessageBox.information(self,'Phiên đã liên kết Studio','Gỡ liên kết nick trong Lịch LIVE Studio trước khi xóa phiên.');return
        if len(self.data['sessions'])==1:return
        s=self.current()
        clients=self.bridge.snapshot();bound=resolve_binding(s.get('chrome_binding'),clients)
        chrome_active=bool(bound and any(m.get('running') for m in clients[bound].get('modules',{}).values()))
        if chrome_active or s['id']==self.cycle_id or (s['id'] in self.processes and self.processes[s['id']].poll() is None):QMessageBox.information(self,'Phiên đang dùng','Dừng Chrome, đóng cửa sổ video và hủy lịch trước khi xóa.');return
        if QMessageBox.question(self,'Xóa phiên','Xóa cấu hình phiên này? Video gốc không bị xóa.')!=QMessageBox.StandardButton.Yes:return
        del self.data['sessions'][self.selected];self.selected=0;write_json(self.path,self.data);self.refresh_list();self.fill()
    def add_video(self):
        paths,_=QFileDialog.getOpenFileNames(self,'Thêm video','','Video (*.mp4 *.mkv *.mov *.avi *.webm);;Tất cả (*)');existing={self.playlist.item(i).text() for i in range(self.playlist.count())};self.playlist.addItems([p for p in paths if p not in existing])
    def remove_video(self):
        for i in reversed([self.playlist.row(x) for x in self.playlist.selectedItems()]):self.playlist.takeItem(i)
    def move_video(self,delta):
        i=self.playlist.currentRow();n=i+delta
        if i>=0 and 0<=n<self.playlist.count():self.playlist.insertItem(n,self.playlist.takeItem(i));self.playlist.setCurrentRow(n)
    def launch(self,path,args=()):
        if getattr(sys,'frozen',False):
            mode='--player' if path.name=='player.py' else '--alarm'
            return subprocess.Popen([sys.executable,mode,*map(str,args)],cwd=str(BASE))
        return subprocess.Popen([sys.executable,str(path),*map(str,args)],cwd=str(BASE))
    def command(self,action,save=True,session=None):
        if save:self.collect();write_json(self.path,self.data)
        s=session or self.current();folder=DATA/'runtime'/s['id']
        process=dispatch_video_command(folder,action,s,self.processes.get(s['id']),lambda f:self.launch(BASE/'player.py',[f]))
        if process is not None:self.processes[s['id']]=process
    def export_diagnostics(self):
        from diagnostics import build
        path,_=QFileDialog.getSaveFileName(self,'Xuất gói chẩn đoán','NBL_chan_doan_'+time.strftime('%Y%m%d_%H%M')+'.zip','ZIP (*.zip)')
        if not path:return
        try:
            extra={}
            try:
                from studio_vision import ocr_model_info
                extra['ocr']=ocr_model_info()[1]
            except Exception as e:extra['ocr']='Chưa nạp được: '+type(e).__name__
            extra['chrome_port']=self.bridge.port;extra['chrome_tabs']=len(self.bridge.snapshot())
            build(DATA,path,extra);self.log('Đã xuất gói chẩn đoán: '+path)
        except Exception as e:QMessageBox.warning(self,'Chưa xuất được',str(e))
    def export(self):
        self.collect();path,_=QFileDialog.getSaveFileName(self,'Xuất cấu hình','NBL_profiles.json','JSON (*.json)')
        if path:write_json(path,self.data)
    def import_config(self):
        if hasattr(self,'studio_panel') and (self.studio_panel.profiles or self.studio_panel.active()):QMessageBox.information(self,'Liên kết Studio','Cấu hình nhập phải giữ các phiên đang liên kết Studio. Sao lưu và gỡ liên kết Studio trước khi thay bộ cấu hình.');return
        chrome_active=any(m.get('running') for c in self.bridge.snapshot().values() for m in c.get('modules',{}).values() if isinstance(m,dict))
        if any(p.poll() is None for p in self.processes.values()) or self.cycle.state!='idle' or chrome_active:QMessageBox.information(self,'Đang chạy','Đóng các cửa sổ video, hủy lịch và dừng các mục Chrome trước khi nhập.');return
        path,_=QFileDialog.getOpenFileName(self,'Nhập cấu hình','','JSON (*.json)')
        if not path:return
        try:
            if Path(path).stat().st_size>2_000_000:raise ValueError('Tệp quá lớn.')
            data=validate(json.loads(Path(path).read_text(encoding='utf-8')))
            if not data['sessions']:raise ValueError('Cần ít nhất một phiên.')
            write_json(self.path.with_suffix('.backup.json'),self.data);write_json(self.path,data);self.data=data;self.selected=0;self.refresh_list();self.fill();self.render_jobs()
        except Exception as e:QMessageBox.warning(self,'Chưa nhập',str(e))
    def start_cycle(self):
        try:
            if not self.obs.connected:raise ValueError('Kết nối OBS trước.')
            if self.cycle.state!='idle':raise ValueError('Lịch đã chạy; hủy lịch cũ trước.')
            self.collect()
            if not self.current()['playlist']:raise ValueError('Thêm video trước.')
            self.cycle.begin(time.monotonic(),self.live_minutes.value()*60,self.rest_minutes.value()*60,self.repeat.isChecked());self.cycle_id=self.current()['id'];self.command('play')
        except Exception as e:QMessageBox.warning(self,'Chưa bắt đầu',str(e))
    def cancel_cycle(self):
        if self.cycle.cancel():self.obs.submit('stop')
        self.cycle_id=None;self.log('Đã hủy lịch OBS.')
    def emergency(self):
        if hasattr(self,'studio_chat'):self.studio_chat.engine.stop_all()
        if hasattr(self,"studio_panel"):
            try:self.studio_panel.stop_all()
            except Exception as e:self.log('Studio cần dừng thủ công: '+str(e))
        for j in self.data.get('jobs',[]):
            if j['state']=='pending':j['state']='skipped'
        self.render_jobs()
        self.bridge.stop_all()
        if self.alarm_window:self.alarm_window.stop()
        self.cancel_cycle()
        for s in self.data['sessions']:
            if s['id'] in self.processes:self.command('stop',False,s)
        if self.obs.connected or self.obs.busy:self.obs.submit('emergency')
        try:write_json(self.path,self.data)
        except Exception as e:self.log('Đã dừng, nhưng chưa lưu được cấu hình: '+type(e).__name__)
        self.log('Đã gửi lệnh dừng tất cả: video, Chrome, lịch OBS và bộ báo động.')
    def tick(self):
        self.discover_accounts(self.bridge.snapshot())
        self.chrome_tick()
        for msg in self.notifier.drain():self.phone_status.setText(msg);self.log(msg)
        self.scheduled_tick()
        now=time.monotonic()
        for action,ok,data in self.obs.drain():
            if ok:
                if 'outputActive' in data:self.obs_active=bool(data['outputActive']);self.obs_at=now
                
                if action!='status':self.log('OBS xác nhận: '+action)
            else:
                self.log('OBS lỗi: '+action+' / '+str(data))
                if self.cycle.state!='idle':self.cancel_cycle()
        if self.obs.connected and not self.obs.busy and now-self.last_poll>=2:self.obs.submit('status');self.last_poll=now
        self.obs_label.setText(('Đã kết nối' if self.obs.connected else 'Chưa kết nối')+' • '+{'idle':'Chưa chạy lịch','prepare':'Đợi video và OBS','starting':'Đợi OBS bắt đầu','live':'Đang phát','stopping':'Đợi OBS dừng','rest':'Đang nghỉ'}.get(self.cycle.state,self.cycle.state))
        statuses={}
        for s in self.data['sessions']:
            try:
                st=json.loads((DATA/'runtime'/s['id']/'status.json').read_text(encoding='utf-8'))
                if time.time()-st['time']<4:statuses[s['id']]=st
                if st.get('error'):
                    if self.errors.get(s['id'])!=st['error']:self.log(f"VIDEO {s['number']:02d}: "+st['error'])
                    self.errors[s['id']]=st['error']
                else:self.errors.pop(s['id'],None)
            except (OSError,ValueError,KeyError):pass
        st=statuses.get(self.current()['id']);self.label.setText(f"NBL VIDEO {self.current()['number']:02d} • "+(f"{ {'PlayingState':'Đang phát','PausedState':'Tạm dừng','StoppedState':'Đã dừng'}.get(st['state'],st['state'])} • {'Tắt tiếng' if st['muted'] else st['device']} • {Path(st['path']).name}" if st else 'Chưa mở / không có tín hiệu cập nhật'))
        clients=self.bridge.snapshot();chrome_errors=sum(bool(m.get('error')) for c in clients.values() for m in c.get('modules',{}).values() if isinstance(m,dict))
        self.label.setText(self.label.text()+f' • Chrome: {len(clients)} tab / {chrome_errors} lỗi')
        binding=self.current().get('chrome_binding');bound=resolve_binding(binding,clients)
        chrome_text='Chưa gắn Chrome' if not binding else 'Chrome mất kết nối' if not bound else 'Chrome '+str(sum(bool(m.get('error')) for m in clients[bound].get('modules',{}).values()))+' lỗi'
        self.label.setToolTip((st.get('error','')+'\n' if st else '')+self.chrome_binding_label.text())
        if self.compact:self.label.setText(f"VIDEO {self.current()['number']:02d} · "+('Đang phát' if st and st.get('state')=='PlayingState' else 'Chưa phát / tạm dừng')+' · '+chrome_text)
        if self.cycle.state!='idle':
            try:
                s=next(s for s in self.data['sessions'] if s['id']==self.cycle_id);st=statuses.get(s['id'],{});action=self.cycle.tick(now,st.get('state')=='PlayingState',self.obs_active,now-self.obs_at<4)
                if action in ('start','stop'):self.obs.submit(action)
                elif action=='video_stop':self.command('stop',False,s)
                elif action=='shuffle_play':
                    self.command('play',False,{**s,'shuffle':True})
            except Exception as e:self.log('Lịch dừng: '+str(e));self.cancel_cycle()
    def _poll_requested_close(self):
        if not getattr(self,'_closing_live',False):return
        failed=getattr(self,'_close_stop_failed',False) or any(j.get('state')=='attention' for j in self.studio_panel.jobs)
        if not self.studio_panel.active() or failed or time.monotonic()-self._close_requested_at>=90:
            self.close();return
        QTimer.singleShot(500,self._poll_requested_close)
    def closeEvent(self,event):
        if hasattr(self,'studio_panel') and self.studio_panel.active() and not getattr(self,'_force_close',False):
            attempted=getattr(self,'_closing_live',False)
            failed=attempted and (getattr(self,'_close_stop_failed',False) or any(j.get('state')=='attention' for j in self.studio_panel.jobs) or time.monotonic()-self._close_requested_at>=90)
            if failed:
                answer=QMessageBox.question(self,'Chưa xác nhận LIVE đã tắt','Không kết thúc được LIVE qua app. Phiên LIVE có thể vẫn đang chạy.\nHãy kết thúc thủ công trên Studio nếu cần. Đóng NBL ngay và ngừng toàn bộ tác vụ của tool?',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
                if answer!=QMessageBox.StandardButton.Yes:
                    self._closing_live=False;event.ignore();return
                self._force_close=True;self._closing_live=False
                for job in self.studio_panel.jobs:
                    if job.get('state') in ('preparing','starting','running','stopping','recovering','attention'):
                        self.studio_panel.cancel_pending_starts(job);self.studio_panel.stop_chrome(job)
                        job['state']='recovery_review';job['error']='Đã đóng NBL khi chưa xác nhận LIVE kết thúc; kiểm tra thủ công.'
                from studio_scheduler import cancel_controls
                cancel_controls()
            else:
                if not attempted:
                    self._closing_live=True;self._close_requested_at=time.monotonic()
                    self._close_stop_failed=False
                    try:self.studio_panel.stop_all();self.log('Đang kết thúc lịch LIVE Studio; đợi xác nhận rồi đóng app.')
                    except Exception as error:self._close_stop_failed=True;self.log('Chưa gửi được lệnh kết thúc: '+str(error))
                    QTimer.singleShot(500,self._poll_requested_close)
                event.ignore();return
        self.timer.stop()
        try:self.collect();write_json(self.path,self.data)
        except Exception as e:
            self.log('Chưa lưu được cấu hình trước khi đóng: '+type(e).__name__)
            QMessageBox.warning(self,'Chưa lưu được','Không lưu được thay đổi vừa sửa. Cấu hình đã lưu trước đó được giữ lại. Các chức năng đang chạy sẽ được dừng.')
        self.cancel_cycle()
        # 4.1.4 (owner, 19/10/2026): NBL VIDEO is opened by the owner and captured by
        # Studio; closing NBL leaves it playing. The next NBL run finds it again
        # (video_commands: a window that reported in the last 3 s gets the commands).
        if self.alarm_window:self.alarm_window.close()
        self.studio_chat.shutdown();self.studio_panel.shutdown();__import__('studio_vision_rpc').close_service();self.notifier.close();set_awake(False);self.bridge.close();self.obs.close()
        for handler in self.logger.handlers[:]:handler.close();self.logger.removeHandler(handler)
        super().closeEvent(event)

if __name__=='__main__':
    if '--player' in sys.argv:
        from player import Output
        a=QApplication(sys.argv);w=Output(Path(sys.argv[-1]));w.show();sys.exit(a.exec())
    if '--alarm' in sys.argv:
        from NBL_CANH_BAO.alarm import Alarm
        r=QApplication(sys.argv);r.setStyleSheet(STYLE);w=Alarm();w.show();sys.exit(r.exec())
    app=QApplication(sys.argv);app.setStyle('Fusion');app.setStyleSheet(STYLE)
    # 4.1.3: the mouse wheel never changes numbers, dates or dropdown choices.
    from no_wheel import install as no_wheel;no_wheel(app)
    window=Console();window.show();sys.exit(app.exec())
