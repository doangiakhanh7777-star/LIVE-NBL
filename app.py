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
from PySide6.QtGui import QIcon, QDesktopServices, QPixmap, QImage, QPainter, QColor
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget, QListWidgetItem, QTabWidget, QLineEdit, QTextEdit, QCheckBox, QComboBox, QSpinBox, QDoubleSpinBox, QFileDialog, QMessageBox, QFormLayout, QGroupBox, QSlider, QDateTimeEdit, QScrollArea, QProgressBar, QGridLayout, QSizePolicy, QStyle, QToolButton, QMenu, QAbstractSpinBox, QDialog)
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
        super().__init__(); self.setWindowTitle('TOOL NBL LIVE • 4.3.14'); screen=QApplication.primaryScreen();self.resize(430,max(420,min(790,screen.availableGeometry().height()-60)) if screen else 790); self.setMinimumSize(400,120);self.setMaximumWidth(480);self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint,False)
        self.setWindowIcon(QIcon(str(BASE/'assets/logo_38.ico')))
        self.path = DATA/'profiles.json'
        self.startup_notices=[]
        self.data = load(self.path, self.startup_notices.append)
        self.processes = {}; self.errors = {}; self.selected = 0; self.loading = False
        self.alarm_window=None;self.phone_error=''
        self.phone_settings=NotificationSettings(DATA/'notifications.json');self.notifier=Notifier();self.wrap_notifier()
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
        titlebox=QVBoxLayout();titlebox.setSpacing(0);titlebox.setContentsMargins(0,0,0,0)
        title = QLabel('NBL LIVE'); title.setObjectName('title'); titlebox.addWidget(title)
        tag = QLabel('TikTok Live Studio'); tag.setObjectName('tag'); titlebox.addWidget(tag)
        header.addLayout(titlebox); header.addStretch()
        self.fold_button = button('Thu gọn',self.toggle_compact); header.addWidget(self.fold_button)
        from hold_button import HoldButton
        # 4.3.0: BẮT ĐẦU / DỪNG = ghim + AI tự bật khi LIVE (mặc định bật)
        self.auto_btn=button('⏸ DỪNG',self.toggle_auto);self.auto_btn.setToolTip('Ghim + AI tự bật khi Studio LIVE. Bấm để tạm dừng / bật lại.');header.addWidget(self.auto_btn)
        header.addWidget(HoldButton('🛑 TẮT HẾT',self.emergency)); layout.addWidget(header_box)
        self.full_panel=QWidget(); body=QVBoxLayout(self.full_panel);body.setContentsMargins(0,0,0,0);body.setSpacing(8)
        self.sessions=QListWidget();self.sessions.hide();self.sessions.currentRowChanged.connect(self.switch)
        self.account_selector=QComboBox();self.account_selector.setObjectName('accountSelector');self.account_selector.setMinimumHeight(44);self.account_selector.currentIndexChanged.connect(self.sessions.setCurrentRow);body.addWidget(self.account_selector)
        self.account_status=QLabel('Chọn nick để bắt đầu');self.account_status.setObjectName('accountStatus');self.account_status.setWordWrap(True);body.addWidget(self.account_status)
        manage=QToolButton();manage.setText('Quản lý nick  ▾');manage.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup);menu=QMenu(manage)
        for text,callback in [('Xóa nick',self.remove_session),('Xuất cấu hình',self.export),('Nhập cấu hình',self.import_config),('Xuất gói chẩn đoán (không kèm mã bí mật)',self.export_diagnostics),('Mở gói chẩn đoán NBL tự gom',lambda:((DATA/'chan_doan').mkdir(parents=True,exist_ok=True),QDesktopServices.openUrl(QUrl.fromLocalFile(str(DATA/'chan_doan')))))]:menu.addAction(text,callback)
        manage.setMenu(menu);connect=QToolButton();connect.setText('Kết nối nick  ▾');connect.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup);connect_menu=QMenu(connect)
        connect_menu.addAction('Kết nối Chrome',lambda:self.navigation.setCurrentIndex(max(0,self.navigation.findText('Giỏ hàng & ghim · TikTok Shop'))))
        connect_menu.addAction('Tắt hẳn TikTok LIVE Studio',self.quit_studio)
        connect_menu.addAction('Kết nối lại TikTok LIVE Studio',lambda:(setattr(self.studio_panel,'auto_at',0),setattr(self.studio_panel,'auto_launched',False),self.log('Đang tìm và kết nối lại Studio…')))
        connect.setMenu(connect_menu);actions=QHBoxLayout();actions.addWidget(connect,1);actions.addWidget(manage,1);body.addLayout(actions)
        from nav_button import NavButton
        self.navigation=NavButton();self.navigation.setMinimumHeight(42);body.addWidget(self.navigation)
        self.tabs=QTabWidget();self.tabs.tabBar().hide();self.navigation.currentIndexChanged.connect(self.tabs.setCurrentIndex);body.addWidget(self.tabs,1)
        import pin_scripts;self.pin_store=pin_scripts.Store(DATA/'kich_ban_ghim.json');self.build_video();self.build_script();self.build_chrome();self.build_ai();self.build_voice();self.label_timer=QTimer(self);self.label_timer.timeout.connect(self.refresh_playlist_labels);self.label_timer.start(5000);self.build_obs();self.build_schedule();self.build_tools()
        for form in self.findChildren(QFormLayout): form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        # 4.3.0 (owner): the activity log is always shown
        logtitle=QLabel('📋 Nhật ký hoạt động');logtitle.setObjectName('subtitle');body.addWidget(logtitle)
        self.logbox=QTextEdit();self.logbox.setReadOnly(True);self.logbox.setMinimumHeight(90);self.logbox.setMaximumHeight(140);body.addWidget(self.logbox)
        layout.addWidget(self.full_panel,1)
        self.label=QLabel('Sẵn sàng');self.label.setWordWrap(True);layout.addWidget(self.label)
        from studio_panel import StudioPanel
        self.studio_panel=StudioPanel(self)
        self.refresh_auto_btn()
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
        import live_chrome
        from diagnostics import VERSION as NBL_VERSION
        # 4.3.5: no extension in NBL's Chrome — NBL puts the page code into the LIVE tab itself
        self.live_chrome=live_chrome.Watchdog(DATA/'chrome_live',lambda:live_chrome.DASHBOARD,serve=self.bridge.serve,
            source=lambda:live_chrome.page_source(BASE/'CHROME_NBL_LIVE',NBL_VERSION),version=NBL_VERSION)
        self.start_phone_api()
        QTimer.singleShot(4000,self.one_nick_cleanup)
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
    def toggle_auto(self):
        on=not getattr(self.studio_panel,'auto_enabled',True);self.studio_panel.set_auto(on);self.refresh_auto_btn()
        self.log('Ghim + AI tự động: '+('BẬT' if on else 'TẠM DỪNG'))
    def refresh_auto_btn(self):
        on=getattr(self.studio_panel,'auto_enabled',True)
        self.auto_btn.setText('⏸ DỪNG' if on else '▶ BẮT ĐẦU');self.auto_btn.setObjectName('' if on else 'primary');self.auto_btn.style().unpolish(self.auto_btn);self.auto_btn.style().polish(self.auto_btn)
    def toggle_compact(self):
        if not self.compact:
            self.full_size=self.size();self.full_panel.hide();self.compact=True
            self.fold_button.setText('Mở');self.label.setMaximumHeight(34);self.resize(430,120)
        else:
            self.full_panel.show();self.compact=False;self.fold_button.setText('Thu gọn');self.label.setMaximumHeight(16777215)
            self.resize(self.full_size or self.size())
    def page(self, title):
        scroll=QScrollArea();scroll.setWidgetResizable(True)
        w=QWidget();w.setObjectName('card');layout=QVBoxLayout(w);layout.setContentsMargins(14,14,14,14);layout.setSpacing(10)
        scroll.setWidget(w);self.tabs.addTab(scroll,title);self.navigation.addItem(title);return layout
    def build_video(self):
        v = self.page('Video & âm thanh'); form = QFormLayout();form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows); self.account = QLineEdit(); form.addRow('Tên hiển thị của nick trong NBL LIVE', self.account); v.addLayout(form)
        self.playlist = QListWidget(); self.playlist.setMaximumHeight(170); v.addWidget(self.playlist,1)
        self.playlist.itemDoubleClicked.connect(lambda item:self.open_pin_script(item.data(Qt.ItemDataRole.UserRole)))
        v.addWidget(button('🚩 Soạn kịch bản ghim cho clip đã chọn (bấm đúp vào clip cũng được)',lambda:self.open_pin_script(self.playlist.currentItem().data(Qt.ItemDataRole.UserRole) if self.playlist.currentItem() else None),'primary'))
        row = QGridLayout()
        for i,(text, action) in enumerate([('Thêm video',self.add_video),('Xóa video',self.remove_video),('↑',lambda:self.move_video(-1)),('↓',lambda:self.move_video(1))]): row.addWidget(button(text,action),i//2,i%2)
        v.addLayout(row)
        self.build_store(v)
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
    # 4.1.13 (owner, 26/10/2026): the script state is shown right in the clip list of
    # "Video & âm thanh" ("video 2.mp4 · 🚩 đã có kịch bản · 5 cờ"); no separate page.
    def playlist_paths(self):
        return [self.playlist.item(i).data(Qt.ItemDataRole.UserRole) or self.playlist.item(i).text() for i in range(self.playlist.count())]
    def clip_label(self,path):
        import pin_scripts
        n=len(self.pin_store.entries(path)) if Path(path).exists() else 0
        text=Path(path).name+('   🚩 đã có kịch bản · '+str(n)+' cờ' if n else '   · chưa có kịch bản')
        if not Path(path).exists():text+='   (không thấy file)'
        info=getattr(getattr(self,'studio_panel',None),'sync_info',{}).get(self.current().get('id')) if self.data.get('sessions') else None
        if info and info.get('clip')==pin_scripts.clip_key(path) and time.time()-info.get('at',0)<30:
            text+='   ▶ đang phát · '+('đã gửi kịch bản cho Chrome '+time.strftime('%H:%M:%S',time.localtime(info['at'])) if info.get('flags') else 'clip này chưa có cờ')
        return text
    def add_playlist_items(self,paths):
        for path in paths:
            it=QListWidgetItem(self.clip_label(path));it.setData(Qt.ItemDataRole.UserRole,path);it.setToolTip(path);self.playlist.addItem(it)
    def refresh_playlist_labels(self):
        for i in range(self.playlist.count()):
            it=self.playlist.item(i);path=it.data(Qt.ItemDataRole.UserRole) or it.text();label=self.clip_label(path)
            if it.text()!=label:it.setText(label)
    def refresh_pin_scripts(self):self.refresh_playlist_labels()
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
        if not clip:QMessageBox.information(self,'Kịch bản ghim','Chọn một clip trong danh sách video trước.');return
        if not Path(clip).exists():QMessageBox.warning(self,'Kịch bản ghim','Không thấy file clip: '+clip);return
        try:
            from pin_script_editor import PinScriptEditor
            PinScriptEditor(self,clip,self.pin_store,self.cart_titles,self.find_on_chrome).exec()
        except Exception as error:QMessageBox.warning(self,'Kịch bản ghim','Chưa mở được trình xem clip: '+str(error))
        self.refresh_pin_scripts()
    def find_on_chrome(self,text):
        """4.1.13 'Tìm thử': ask the nick's Chrome tab to look the product up (read only).
        Returns a function that gives the answer text, or None while waiting."""
        from session_binding import resolve_binding
        snap=self.bridge.snapshot();client=resolve_binding(self.current().get('chrome_binding'),snap) if self.current().get('chrome_binding') else None
        if not client:raise ValueError('Nick này chưa liên kết tab Chrome (Giỏ hàng & trả lời · Chrome → Dùng Chrome này cho nick đang chọn).')
        cid=self.bridge.command(client,dict(action='find_product',module='all',text=str(text)[:120]))
        def answer():
            r=self.bridge.snapshot().get(client,{}).get('findResult') or {}
            return r.get('text') or r.get('state') if r.get('id')==cid and r.get('state') in ('done','failed') else None
        return answer
    def refresh_devices(self):
        selected=self.device.currentData() or '';self.device.blockSignals(True);self.device.clear();self.device.addItem('Thiết bị mặc định của Windows','')
        for d in QMediaDevices.audioOutputs():self.device.addItem(d.description(),bytes(d.id()).hex())
        index=self.device.findData(selected)
        if selected and index<0:self.device.addItem('Thiết bị đã mất — chọn lại',selected);index=self.device.count()-1
        self.device.setCurrentIndex(max(0,index));self.device.blockSignals(False)
    def build_script(self):
        # 4.3.0: no "Xem nội dung trên Chrome" page any more — the app is where things are set.
        self.pins=QTextEdit();self.rules=QTextEdit();self.messages=QTextEdit()
        for w in (self.pins,self.rules,self.messages):w.hide()
    def build_chrome(self):
        # 4.3.0 (owner, 28/10/2026): the Chrome extension is only the bridge to the TikTok Shop
        # LIVE dashboard; everything is set here. Pinning switches on by itself when the LIVE starts.
        v=self.page('Giỏ hàng & ghim · TikTok Shop')
        self.chrome_binding_label=QLabel('Chưa kết nối Chrome');self.chrome_binding_label.setWordWrap(True);self.chrome_binding_label.setObjectName('accountStatus');v.addWidget(self.chrome_binding_label)
        lab=QLabel('NBL dùng một Chrome RIÊNG chỉ để LIVE (không đụng Chrome thường của bạn). NBL tự mở, tự giữ đúng 1 trang LIVE, tự tải lại khi trang đơ, tự mở lại khi lỡ tắt. Lần đầu: đăng nhập TikTok Shop đúng nick trong cửa sổ đó (1 lần). Không cần cài tiện ích.');lab.setWordWrap(True);v.addWidget(lab)
        v.addWidget(button('🌐 Mở Chrome LIVE của NBL',lambda:self.open_chrome(self.current(),True),'primary'))
        box=QGroupBox('Ghim sản phẩm');f=QFormLayout(box);f.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        self.pin_mode=QComboBox();self.pin_mode.addItem('Số thứ tự trong giỏ (1, 2, 3…)','number');self.pin_mode.addItem('Tên sản phẩm (3–4 chữ đầu)','name');f.addRow('Chọn sản phẩm theo',self.pin_mode)
        self.pin_list=QTextEdit();self.pin_list.setPlaceholderText('Mỗi dòng một món, ví dụ:\n1\n3\n5');self.pin_list.setMaximumHeight(120);f.addRow('Sản phẩm muốn ghim (xáo trộn)',self.pin_list)
        self.pin_times={}
        for key,label in [('pinMin','Giữ ghim ít nhất (giây)'),('pinMax','Giữ ghim nhiều nhất (giây)'),('gapMin','Nghỉ ít nhất sau khi tháo (giây)'),('gapMax','Nghỉ nhiều nhất (giây)')]:
            w=QSpinBox();w.setRange(0,86400);self.pin_times[key]=w;f.addRow(label,w)
        hint=QLabel('Để cả 4 ô bằng 0 (hoặc không có món nào) = tắt ghim xáo trộn; ghim theo kịch bản cờ của clip vẫn chạy. Ghim TỰ BẬT khi phát LIVE, tự tắt khi kết thúc.');hint.setWordWrap(True);hint.setObjectName('subtitle');f.addRow(hint)
        v.addWidget(box)
        for w in [self.pin_mode,self.pin_list]+list(self.pin_times.values()):
            (w.currentIndexChanged if isinstance(w,QComboBox) else w.textChanged if isinstance(w,QTextEdit) else w.valueChanged).connect(self.schedule_autosave)
        self.chrome_status={}
        st=QGroupBox('Trạng thái ghim');sf=QVBoxLayout(st);lab=QLabel('Chưa bật');lab.setWordWrap(True);self.chrome_status['pin']=lab;sf.addWidget(lab)
        row=QHBoxLayout();row.addWidget(button('BẬT / THỬ LẠI',lambda:self.chrome_action('pin','start'),'primary'));row.addWidget(button('DỪNG',lambda:self.chrome_action('pin','stop'),'danger'));sf.addLayout(row);v.addWidget(st)
        # hidden: kept so older code paths and saved settings stay valid
        self.chrome_clients=QComboBox();self.chrome_owner=QLineEdit();self.chrome_interval=QSpinBox();self.chrome_interval.setRange(60,86400)
        self.chrome_scheduled=QTextEdit();self.chrome_repeat=QCheckBox();self.chrome_cycle=QLineEdit('00:10:00');self.chrome_reply=QComboBox();self.chrome_reply.addItem('auto','auto');self.chrome_cooldown=QSpinBox();self.chrome_cooldown.setRange(15,86400)
        self.chrome_sync_label=QLabel()
        for w in (self.chrome_clients,self.chrome_owner,self.chrome_interval,self.chrome_scheduled,self.chrome_repeat,self.chrome_cycle,self.chrome_reply,self.chrome_cooldown,self.chrome_sync_label):w.hide()
        v.addStretch()
    # ---------------- 4.3.0 (owner, 28/10/2026): AI trả lời bình luận + giọng đọc ----------------
    def build_ai(self):
        import ai_reply as A
        from ai_engine import AIEngine
        self.ai=AIEngine(self,DATA);cfg=self.ai.settings.load()
        if not cfg.get('rules') and self.data.get('sessions'):
            cfg['rules']=next((s.get('rules') or (s.get('chrome') or {}).get('rules','') for s in self.data['sessions'] if s.get('rules') or (s.get('chrome') or {}).get('rules')),'')
        v=self.page('Trả lời bình luận AI')
        self.ai_on=QCheckBox('Bật AI trả lời bình luận khi LIVE (tự bật/tắt theo LIVE)');self.ai_on.setChecked(bool(cfg.get('enabled')));v.addWidget(self.ai_on)
        self.ai_stats=QLabel(self.ai.summary());self.ai_stats.setWordWrap(True);self.ai_stats.setObjectName('accountStatus');v.addWidget(self.ai_stats)
        # 4.3.12: chọn engine AI
        eb=QGroupBox('Nguồn AI');ef=QFormLayout(eb);ef.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        self.ai_engine=QComboBox();self.ai_engine.addItem('Gemini (Google) — miễn phí có hạn mức','gemini');self.ai_engine.addItem('ChatGPT (OpenAI) — tốn phí, ổn định hơn','openai')
        self.ai_engine.setCurrentIndex(max(0,self.ai_engine.findData(cfg.get('engine','gemini'))));ef.addRow('Dùng AI',self.ai_engine);v.addWidget(eb)
        # Gemini key box
        kb=QGroupBox('Gemini API key');kf=QVBoxLayout(kb)
        self.ai_keys=QLineEdit();self.ai_keys.setEchoMode(QLineEdit.EchoMode.Password);self.ai_keys.setPlaceholderText('Dán key Gemini; nhiều key cách dấu phẩy, rồi bấm Lưu key');kf.addWidget(self.ai_keys)
        self.ai_key_count=QLabel('Đã lưu '+str(len(self.ai.settings.api_keys(cfg)))+' key (mã hóa, chỉ trên máy này)');kf.addWidget(self.ai_key_count)
        row=QHBoxLayout();row.addWidget(button('Lưu key Gemini',self.ai_save_keys,'primary'));row.addWidget(button('Lấy key',lambda:QDesktopServices.openUrl(QUrl('https://aistudio.google.com/apikey'))));row.addWidget(button('Xóa',self.ai_clear_keys,'danger'));kf.addLayout(row)
        note=QLabel('Key tạo trong CÙNG tài khoản Google dùng chung hạn mức; muốn thêm lượt thì tạo key từ tài khoản khác.');note.setWordWrap(True);note.setObjectName('subtitle');kf.addWidget(note);v.addWidget(kb)
        # OpenAI key box
        okb=QGroupBox('ChatGPT (OpenAI) API key');okf=QVBoxLayout(okb)
        self.oai_keys=QLineEdit();self.oai_keys.setEchoMode(QLineEdit.EchoMode.Password);self.oai_keys.setPlaceholderText('Dán key OpenAI (sk-…), rồi bấm Lưu key');okf.addWidget(self.oai_keys)
        self.oai_key_count=QLabel('Đã lưu '+str(len(self.ai.settings.openai_api_keys(cfg)))+' key (mã hóa, chỉ trên máy này)');okf.addWidget(self.oai_key_count)
        row2=QHBoxLayout();row2.addWidget(button('Lưu key ChatGPT',self.ai_save_oai_keys,'primary'));row2.addWidget(button('Lấy key',lambda:QDesktopServices.openUrl(QUrl('https://platform.openai.com/api-keys'))));row2.addWidget(button('Xóa',self.ai_clear_oai_keys,'danger'));okf.addLayout(row2)
        onote=QLabel('Tạo tài khoản OpenAI → vào platform.openai.com → API keys → Create. Tốn phí theo lượt dùng (gpt-4o-mini rất rẻ).');onote.setWordWrap(True);onote.setObjectName('subtitle');okf.addWidget(onote);v.addWidget(okb)
        mb=QGroupBox('Cách trả lời');mf=QFormLayout(mb);mf.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        self.ai_mode=QComboBox()
        for k,t in [('chu','Chữ — gửi vào bình luận Studio'),('giong','Giọng đọc — đọc vào LIVE, không gửi chữ'),('ca_hai','Chữ + giọng đọc')]:self.ai_mode.addItem(t,k)
        self.ai_mode.setCurrentIndex(max(0,self.ai_mode.findData(cfg.get('mode','chu'))));mf.addRow('Kiểu trả lời',self.ai_mode)
        # Gemini voice
        self.ai_voice=QComboBox()
        for k,t in A.VOICES:self.ai_voice.addItem(k+' · '+t,k)
        self.ai_voice.setCurrentIndex(max(0,self.ai_voice.findData(cfg.get('voice','Kore'))));mf.addRow('Giọng Gemini',self.ai_voice)
        # OpenAI voice
        self.oai_voice=QComboBox()
        for k,t in A.OAI_VOICES:self.oai_voice.addItem(k+' · '+t,k)
        self.oai_voice.setCurrentIndex(max(0,self.oai_voice.findData(cfg.get('oai_voice','nova'))));mf.addRow('Giọng ChatGPT',self.oai_voice)
        self.ai_speed=QComboBox()
        for k in A.SPEEDS:self.ai_speed.addItem(k+'x',k)
        self.ai_speed.setCurrentIndex(max(0,self.ai_speed.findData(str(cfg.get('speed','1.0')))));mf.addRow('Tốc độ đọc',self.ai_speed)
        row=QHBoxLayout();self.ai_preview_btn=button('▶ Nghe thử',self.ai_preview,'primary');row.addWidget(self.ai_preview_btn);row.addWidget(button('■ Dừng',lambda:self.ai.stop_preview()));mf.addRow(row)
        self.ai_cooldown=QSpinBox();self.ai_cooldown.setRange(15,3600);self.ai_cooldown.setValue(int(cfg.get('cooldown',60)));self.ai_cooldown.setSuffix(' giây');mf.addRow('Nghỉ trước khi trả lời lại cùng một khách',self.ai_cooldown)
        self.ai_rate=QSpinBox();self.ai_rate.setRange(1,60);self.ai_rate.setValue(int(cfg.get('max_per_minute',10)));self.ai_rate.setSuffix(' câu/phút');mf.addRow('Hỏi AI tối đa',self.ai_rate)
        sound=QLabel('Giọng đọc phát ra cùng thiết bị âm thanh với NBL VIDEO của nick (cáp ảo nếu đang dùng) nên vào được LIVE; lúc đọc NBL tự giảm nhỏ tiếng video. Nghe thử phát ra loa máy.');sound.setWordWrap(True);sound.setObjectName('subtitle');mf.addRow(sound)
        v.addWidget(mb)
        pb=QGroupBox('Hướng dẫn cho AI (thông tin shop)');pf=QVBoxLayout(pb)
        self.ai_prompt=QTextEdit();self.ai_prompt.setPlainText(cfg.get('prompt') or A.DEFAULT_PROMPT);self.ai_prompt.setMinimumHeight(130);pf.addWidget(self.ai_prompt)
        hint=QLabel('💡 Ghi thông tin THẬT: giao hàng, bảo hành, cách xưng hô, ví dụ sản phẩm. AI tự biết danh sách sản phẩm trong giỏ.');hint.setWordWrap(True);hint.setObjectName('subtitle');pf.addWidget(hint)
        row=QHBoxLayout();row.addWidget(button('↺ Khôi phục mặc định',lambda:self.ai_prompt.setPlainText(A.DEFAULT_PROMPT)));row.addWidget(button('💾 Lưu cấu hình',self.ai_save,'primary'));pf.addLayout(row);v.addWidget(pb)
        rb=QGroupBox('Từ khóa trả lời sẵn (trả lời trước, không tốn lượt AI)');rf=QVBoxLayout(rb)
        self.ai_rules=QTextEdit();self.ai_rules.setPlaceholderText('Mỗi dòng: từ khóa;từ khóa khác | câu trả lời\nví dụ: giá;bao nhiêu | Giá có trong giỏ hàng màu cam ạ');self.ai_rules.setPlainText(cfg.get('rules',''));self.ai_rules.setMaximumHeight(110);rf.addWidget(self.ai_rules);v.addWidget(rb)
        tb=QGroupBox('Thử hỏi AI');tf=QVBoxLayout(tb);self.ai_question=QLineEdit();self.ai_question.setPlaceholderText('Gõ một câu bình luận, ví dụ: ship về Cần Thơ mấy ngày em?');tf.addWidget(self.ai_question)
        self.ai_answer=QLabel('');self.ai_answer.setWordWrap(True);tf.addWidget(button('Hỏi thử',self.ai_try));tf.addWidget(self.ai_answer);v.addWidget(tb)
        for w in (self.ai_on,):w.toggled.connect(self.ai_save)
        for w in (self.ai_engine,self.ai_mode,self.ai_voice,self.oai_voice,self.ai_speed):w.currentIndexChanged.connect(self.ai_save)
        for w in (self.ai_cooldown,self.ai_rate):w.valueChanged.connect(self.ai_save)
        self.ai_save(quiet=True);v.addStretch()
        self.ai_timer=QTimer(self);self.ai_timer.timeout.connect(lambda:self.ai_stats.setText(self.ai.summary()));self.ai_timer.start(2000)
    def ai_cfg(self):
        cfg=self.ai.settings.load()
        cfg.update(enabled=self.ai_on.isChecked(),engine=self.ai_engine.currentData(),mode=self.ai_mode.currentData(),
                   voice=self.ai_voice.currentData(),oai_voice=self.oai_voice.currentData(),speed=self.ai_speed.currentData(),
                   cooldown=self.ai_cooldown.value(),max_per_minute=self.ai_rate.value(),
                   prompt=self.ai_prompt.toPlainText().strip(),rules=self.ai_rules.toPlainText().strip())
        return cfg
    def ai_save(self,*args,quiet=False):
        if not hasattr(self,'ai_rate'):return
        try:
            self.ai.settings.save(self.ai_cfg())
            if not quiet and not args:self.log('Đã lưu cấu hình AI trả lời bình luận.')
            if not self.ai_on.isChecked():
                for pid in list(self.ai.active):self.ai.stop(pid)
            elif hasattr(self,'studio_panel'):
                for p in self.studio_panel.profiles:
                    if p['id'] in getattr(self.studio_panel,'hand_live',{}) or any(j['profile']==p['id'] and j['state']=='running' for j in self.studio_panel.jobs):self.ai.start(self.studio_panel.effective_profile(p))
        except Exception as e:QMessageBox.warning(self,'AI',str(e))
    def ai_save_keys(self):
        cfg=self.ai_cfg();keys=self.ai.settings.set_keys(cfg,self.ai_keys.text())
        if not keys:QMessageBox.information(self,'API key','Chưa thấy key hợp lệ (key Gemini dạng AIza…).');return
        self.ai.settings.save(cfg);self.ai_keys.clear();self.ai_key_count.setText('Đã lưu '+str(len(keys))+' key (mã hóa, chỉ trên máy này)');self.log('Đã lưu '+str(len(keys))+' Gemini API key.')
    def ai_clear_keys(self):
        cfg=self.ai_cfg();cfg['keys']='';self.ai.settings.save(cfg);self.ai_key_count.setText('Chưa có key');self.log('Đã xóa Gemini API key.')
    def ai_save_oai_keys(self):
        cfg=self.ai_cfg();keys=self.ai.settings.set_openai_keys(cfg,self.oai_keys.text())
        if not keys:QMessageBox.information(self,'API key','Chưa thấy key hợp lệ (key OpenAI dạng sk-…).');return
        self.ai.settings.save(cfg);self.oai_keys.clear();self.oai_key_count.setText('Đã lưu '+str(len(keys))+' key (mã hóa, chỉ trên máy này)');self.log('Đã lưu '+str(len(keys))+' OpenAI API key.')
    def ai_clear_oai_keys(self):
        cfg=self.ai_cfg();cfg['openai_keys']='';self.ai.settings.save(cfg);self.oai_key_count.setText('Chưa có key');self.log('Đã xóa OpenAI API key.')
    # ---------- 4.3.13: giữ phím cách để nói thẳng vào LIVE ----------
    def build_voice(self):
        from ptt import PushToTalk, SpaceFilter, TalkBadge
        from ptt import RemoteTalk
        self.ptt=PushToTalk(self,DATA);self.remote_talk=RemoteTalk(self);self.talk_badge=None;self.ptt_ducked=None;cfg=self.ptt.settings.load()
        v=self.page('🎤 Giọng nói · giữ phím cách')
        intro=QLabel('Giữ phím CÁCH (khoảng trắng) để nói thẳng vào LIVE bằng giọng thật của mày — thời gian thực, không thu rồi phát lại. Thả phím là ngắt.');intro.setWordWrap(True);v.addWidget(intro)
        self.voice_on=QCheckBox('BẬT chế độ giữ phím cách để nói');self.voice_on.setChecked(bool(cfg.get('enabled')));v.addWidget(self.voice_on)
        self.voice_state=QLabel('');self.voice_state.setWordWrap(True);self.voice_state.setObjectName('accountStatus');v.addWidget(self.voice_state)
        self.voice_phone=QLabel('');self.voice_phone.setWordWrap(True);self.voice_phone.setObjectName('subtitle');v.addWidget(self.voice_phone)
        self.voice_level=QProgressBar();self.voice_level.setRange(0,100);self.voice_level.setTextVisible(False);self.voice_level.setMaximumHeight(12);v.addWidget(self.voice_level)
        lv=QLabel('Thanh trên nhúc nhích theo tiếng mic (kể cả khi chưa giữ phím) — dùng để thử mic.');lv.setObjectName('subtitle');lv.setWordWrap(True);v.addWidget(lv)
        g=QGroupBox('Thiết bị');f=QFormLayout(g);f.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        self.voice_mic=QComboBox();self.voice_out=QComboBox();self.fill_voice_devices(cfg)
        f.addRow('Micro',self.voice_mic);f.addRow('Phát vào (Studio phải thu thiết bị này)',self.voice_out)
        self.voice_anywhere=QCheckBox('Nhận phím cách cả khi đang ở cửa sổ khác (Studio, Chrome…)');self.voice_anywhere.setChecked(bool(cfg.get('anywhere',True)));f.addRow(self.voice_anywhere)
        self.voice_duck=QCheckBox('Đang nói thì nhỏ tiếng NBL VIDEO');self.voice_duck.setChecked(bool(cfg.get('duck',True)));f.addRow(self.voice_duck);v.addWidget(g)
        note=QLabel('• Chạm nhanh phím cách (gõ chữ) KHÔNG phát tiếng — phải giữ từ 0,25 giây trở lên mới mở mic.\n'
                    '• Đang nói: AI trả lời bình luận tạm ngừng đọc, trên màn hình hiện nhãn đỏ "ĐANG NÓI VÀO LIVE".\n'
                    '• Mặc định phát vào cùng cáp ảo với NBL VIDEO của nick, nên Studio đang thu cáp đó là nghe được, không cần chỉnh Studio.\n'
                    '• Giữ phím cách khi đang đứng trong ô gõ chữ của app khác thì app đó cũng gõ thêm dấu cách — đứng ở Studio/NBL rồi giữ là gọn nhất.')
        note.setWordWrap(True);note.setObjectName('subtitle');v.addWidget(note);v.addStretch()
        self.voice_on.toggled.connect(self.voice_apply)
        for w in (self.voice_mic,self.voice_out):w.currentIndexChanged.connect(self.voice_apply)
        for w in (self.voice_anywhere,self.voice_duck):w.toggled.connect(self.voice_apply)
        self.space_filter=SpaceFilter(self.ptt);QApplication.instance().installEventFilter(self.space_filter)
        self.voice_devices=QMediaDevices(self);self.voice_devices.audioInputsChanged.connect(self.voice_devices_changed);self.voice_devices.audioOutputsChanged.connect(self.voice_devices_changed)
        self.voice_timer=QTimer(self);self.voice_timer.timeout.connect(self.voice_refresh);self.voice_timer.start(100)
        if cfg.get('enabled'):QTimer.singleShot(1500,self.voice_apply)
        self.voice_refresh()
    def fill_voice_devices(self,cfg):
        for w in (self.voice_mic,self.voice_out):w.blockSignals(True);w.clear()
        self.voice_mic.addItem('Micro mặc định của Windows','')
        for d in QMediaDevices.audioInputs():self.voice_mic.addItem(d.description(),bytes(d.id()).hex())
        self.voice_out.addItem('Giống NBL VIDEO của nick (cáp ảo) — nên dùng','')
        for d in QMediaDevices.audioOutputs():self.voice_out.addItem(d.description(),bytes(d.id()).hex())
        self.voice_mic.setCurrentIndex(max(0,self.voice_mic.findData(cfg.get('mic',''))));self.voice_out.setCurrentIndex(max(0,self.voice_out.findData(cfg.get('out',''))))
        for w in (self.voice_mic,self.voice_out):w.blockSignals(False)
    def voice_cfg(self):
        return dict(enabled=self.voice_on.isChecked(),mic=self.voice_mic.currentData() or '',out=self.voice_out.currentData() or '',anywhere=self.voice_anywhere.isChecked(),duck=self.voice_duck.isChecked())
    def voice_apply(self,*args):
        cfg=self.voice_cfg()
        try:self.ptt.settings.save(cfg)
        except Exception as e:self.log('Giọng nói: chưa lưu được cài đặt: '+str(e)[:120])
        if cfg['enabled']:self.ptt.arm(cfg)
        else:self.ptt.disarm()
        self.voice_refresh()
    def voice_devices_changed(self):
        cfg=self.voice_cfg();self.fill_voice_devices(cfg)
        if self.ptt.armed:self.ptt.arm(self.voice_cfg())
    def ptt_target(self,out_id=''):
        self.ptt_warn='';outs=QMediaDevices.audioOutputs()
        def find(want):return next((d for d in outs if want and bytes(d.id()).hex()==want),None)
        if out_id:return find(out_id) or QMediaDevices.defaultAudioOutput()
        dev=find((self.current() or {}).get('device','')) if self.data.get('sessions') else None
        if dev is not None:self.ptt_warn='';return dev
        from pin_scripts import pick_cable
        hit=pick_cable([(d.description(),bytes(d.id()).hex()) for d in outs])
        if hit:self.ptt_warn='';return find(hit[0])
        self.ptt_warn='Máy chưa có cáp âm thanh ảo — tiếng đang ra loa mặc định, Studio có thể không thu được.'
        return QMediaDevices.defaultAudioOutput()
    def ptt_mic_blocked(self,priv):
        """4.3.14: Windows chặn micro cho ứng dụng máy tính -> hỏi chủ máy, đồng ý thì NBL bật quyền (tài khoản này) rồi mở lại."""
        if getattr(self,'_mic_asking',False) or getattr(self,'_mic_declined',False):return
        self._mic_asking=True
        try:
            from ptt import allow_mic_for_user
            if priv.get('machine')=='Deny':
                QMessageBox.information(self,'Micro bị khóa','Windows đang khóa micro cho CẢ MÁY (cần quyền quản trị). NBL mở trang Cài đặt → Micro: bật "Truy cập micro" và "Cho phép ứng dụng máy tính truy cập micro", rồi bật lại giữ phím cách.')
                QDesktopServices.openUrl(QUrl('ms-settings:privacy-microphone'));return
            ans=QMessageBox.question(self,'Windows đang chặn micro','Windows đang chặn micro cho ứng dụng máy tính nên NBL không nghe được mic.\n\nCho NBL bật quyền micro cho tài khoản Windows này? (Tắt lại được trong Cài đặt → Quyền riêng tư → Micro.)')
            if ans!=QMessageBox.StandardButton.Yes:
                self._mic_declined=True;QDesktopServices.openUrl(QUrl('ms-settings:privacy-microphone'));return
            try:ok=allow_mic_for_user()
            except Exception as e:ok=False;self.log('Giọng nói: chưa bật được quyền micro: '+str(e)[:150])
            if not ok:
                QDesktopServices.openUrl(QUrl('ms-settings:privacy-microphone'));return
            # đo trên Windows thật: quyền mới chỉ áp dụng cho tiến trình mở SAU khi bật -> phải mở lại NBL
            self.log('Giọng nói: đã bật quyền micro Windows cho ứng dụng máy tính. Windows chỉ áp dụng khi mở lại NBL.')
            live=hasattr(self,'studio_panel') and self.studio_panel.active()
            if live:
                QMessageBox.information(self,'Đã bật quyền micro','Đã bật quyền micro. Windows chỉ áp dụng khi mở lại NBL — đang LIVE nên NBL KHÔNG tự mở lại; hết LIVE thì tắt NBL rồi mở lại là dùng được giữ phím cách.')
            elif QMessageBox.question(self,'Đã bật quyền micro','Đã bật quyền micro. Windows chỉ áp dụng khi mở lại NBL.\n\nMở lại NBL ngay bây giờ?')==QMessageBox.StandardButton.Yes:
                self.restart_app()
        finally:
            self._mic_asking=False
    def restart_app(self):
        """Mở lại NBL (chỉ khi không LIVE). NBL chỉ cho chạy 1 bản (khóa chống trùng) nên tiến trình phụ đợi bản này
        tắt hẳn rồi mới mở NBL_LIVE.exe (chạy từ mã nguồn: bootstrap.py)."""
        exe=BASE/'NBL_LIVE.exe';target=[str(exe)] if exe.is_file() else [sys.executable,str(BASE/'bootstrap.py')]
        code=('import sys,time,subprocess\nsys.path.insert(0,sys.argv[1])\nfrom video_commands import pid_alive\n'
              'pid=int(sys.argv[2]);end=time.time()+90\nwhile pid_alive(pid) and time.time()<end:time.sleep(0.5)\n'
              'time.sleep(1);subprocess.Popen(sys.argv[3:],cwd=sys.argv[1])')
        try:
            flags=0x00000008|0x00000200 if sys.platform=='win32' else 0      # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
            subprocess.Popen([sys.executable,'-c',code,str(BASE),str(os.getpid())]+target,cwd=str(BASE),creationflags=flags,close_fds=True)
        except Exception as e:
            self.log('Chưa tự mở lại được NBL: '+str(e)[:150]);QMessageBox.information(self,'Mở lại NBL','Tắt NBL rồi mở lại bằng biểu tượng NBL LIVE.');return
        self.log('Đang mở lại NBL…');QTimer.singleShot(300,self.close)
    def ptt_changed(self,on,who='phim'):
        # 4.3.15: phím cách và điện thoại có thể cùng nói; AI im / nhãn đỏ / nhỏ tiếng theo "có ai đang nói"
        talkers=getattr(self,'talkers',set());self.talkers=talkers
        was=bool(talkers);(talkers.add if on else talkers.discard)(who);on=bool(talkers)
        if on==was:return
        ai=getattr(self,'ai',None)
        if ai is not None:ai.set_hold(on)
        if self.talk_badge is None:
            from ptt import TalkBadge
            self.talk_badge=TalkBadge()
        self.talk_badge.show() if on else self.talk_badge.hide()
        s=self.current() if self.data.get('sessions') else None
        if on and s and self.voice_duck.isChecked() and not s.get('mute'):
            self.ptt_ducked=dict(s)
            try:self.command('settings',False,{**s,'volume':int(s.get('volume',80)*0.3)})
            except Exception:self.ptt_ducked=None
        elif not on and self.ptt_ducked is not None:
            try:self.command('settings',False,self.ptt_ducked)
            except Exception:pass
            self.ptt_ducked=None
        self.log('Giọng nói: '+('đang nói vào LIVE…' if on else 'đã ngắt mic.'))
    def voice_refresh(self):
        rt=getattr(self,'remote_talk',None)
        if hasattr(self,'voice_phone'):
            t=rt.status() if rt else ''
            t=t or '📱 Nói qua điện thoại: mở app NBL trên điện thoại → Tổng quan → giữ nút "🎤 Giữ để nói vào LIVE".'
            if self.voice_phone.text()!=t:self.voice_phone.setText(t)
        if not hasattr(self,'voice_state'):return
        text=self.ptt.status()
        if self.ptt.armed and getattr(self,'ptt_warn',''):text+='\n⚠ '+self.ptt_warn
        if self.voice_state.text()!=text:self.voice_state.setText(text)
        lv=max(self.ptt.level if self.ptt.armed else 0.0,rt.level if rt and rt.talking else 0.0)
        self.voice_level.setValue(int(min(1.0,lv*1.6)*100))
    def ai_wait(self,future,done):
        timer=QTimer(self)
        def check():
            if not future.done():return
            timer.stop();timer.deleteLater()
            try:done(future.result(),None)
            except Exception as e:done(None,e)
        timer.timeout.connect(check);timer.start(200)
    def ai_preview(self):
        self.ai_save(quiet=True);self.ai_preview_btn.setText('⏳ Đang tạo…');self.ai_preview_btn.setEnabled(False)
        def done(wav,err):
            self.ai_preview_btn.setText('▶ Nghe thử');self.ai_preview_btn.setEnabled(True)
            if err:QMessageBox.warning(self,'Nghe thử',str(err));return
            self.ai.play(wav,None,preview=True)
        self.ai_wait(self.ai.preview_voice(self.ai_cfg(),None),done)
    def ai_try(self):
        q=self.ai_question.text().strip()
        if not q:return
        self.ai_answer.setText('Đang hỏi…')
        p=self.studio_panel.current_profile() if hasattr(self,'studio_panel') else None
        self.ai_wait(self.ai.test_ask(self.ai_cfg(),q,p),lambda r,e:self.ai_answer.setText(str(e) if e else r))
    def pin_settings(self,session=None):
        """4.3.0: the session's pin settings (migrated once from what the old extension kept)."""
        s=session or self.current();p=s.get('pin')
        if not isinstance(p,dict):
            c=s.get('chrome',{}) or {}
            def n(k,d):
                try:return max(0,int(float(c.get(k,d))))
                except (TypeError,ValueError):return d
            p=dict(mode=c.get('productMode','number') if c.get('productMode') in ('number','name') else 'number',products=str(c.get('pins') or s.get('pins') or ''),
                   pinMin=n('pinMin',30),pinMax=n('pinMax',40),gapMin=n('gapMin',30),gapMax=n('gapMax',40))
            s['pin']=p
        return p
    def pin_command_config(self,session=None):
        p=self.pin_settings(session)
        return dict(pins=p['products'],productMode=p['mode'],pinMin=str(p['pinMin']),pinMax=str(p['pinMax']),gapMin=str(p['gapMin']),gapMax=str(p['gapMax']))
    def chrome_config(self):
        return dict(owner=self.chrome_owner.text().strip(),repeatPins='on' if self.chrome_repeat.isChecked() else 'off',cycle=self.chrome_cycle.text().strip(),replyMode=self.chrome_reply.currentData(),cooldown=str(self.chrome_cooldown.value()))
    def save_chrome(self):
        self.collect();self.current()['chrome']={**self.current().get('chrome',{}),**self.chrome_config()};write_json(self.path,self.data);self.log('Đã lưu thiết lập Chrome theo phiên.')
    # ---- 4.2.1 (owner, 28/10/2026): Chrome opened and paired by NBL itself ----
    def chrome_exe(self):
        for base in (os.environ.get('ProgramFiles',''),os.environ.get('ProgramFiles(x86)',''),os.environ.get('LOCALAPPDATA','')):
            p=Path(base)/'Google'/'Chrome'/'Application'/'chrome.exe'
            if base and p.is_file():return str(p)
        return ''
    def open_chrome(self,session=None,manual=False):
        """4.3.4: start (or show) NBL's own Chrome; it never opens a tab in the owner's normal Chrome."""
        try:self.live_chrome.start()
        except Exception as e:
            self.log('Không mở được Chrome LIVE: '+str(e))
            if manual:QMessageBox.warning(self,'Chrome LIVE',str(e))
            return False
        if manual:
            self.log('Đã mở Chrome LIVE của NBL.')
            if not self.live_chrome.setup_done():QMessageBox.information(self,'Chrome LIVE (làm 1 lần)','NBL vừa mở một Chrome RIÊNG chỉ để LIVE.\n\nĐăng nhập TikTok Shop đúng nick LIVE trong cửa sổ đó (nên chọn Tiếng Việt ở góc phải trang). Xong là NBL tự mở trang LIVE và tự nối, không cần cài tiện ích, không phải F5.')
        return True
    LIVE_CHROME_TEXT={'off':'Chrome LIVE chưa mở · bấm Mở Chrome LIVE của NBL','starting':'Đang mở Chrome LIVE…','loading':'Chrome LIVE đang tải trang LIVE…',
        'login':'Chrome LIVE: TikTok Shop đòi ĐĂNG NHẬP — đăng nhập đúng nick trong cửa sổ Chrome LIVE','no_extension':'Chrome LIVE: trang LIVE chưa trả lời, NBL đang tự tải lại','ok':'Chrome LIVE đã kết nối'}
    def live_chrome_session(self):
        """The one nick that uses NBL's Chrome: the nick linked to TikTok LIVE Studio, else the nick shown."""
        sp=getattr(self,'studio_panel',None)
        p=next((p for p in (sp.profiles if sp else []) if p.get('cdp')),None)
        return next((s for s in self.data['sessions'] if p and s['id']==p.get('session')),None) or self.current()
    def live_chrome_tick(self):
        """Qt side: start the watchdog step in a thread, then use its result (exact tab -> nick link)."""
        import threading
        res=getattr(self,'live_chrome_result',None)
        if res is not None:
            self.live_chrome_result=None;self.live_chrome_apply(res)
        t=getattr(self,'live_chrome_thread',None)
        if (t is None or not t.is_alive()) and time.time()-getattr(self,'live_chrome_at',0)>=4:
            self.live_chrome_at=time.time();clients=self.bridge.snapshot()
            busy=any(any(m.get('running') for m in (st.get('modules') or {}).values()) or (st.get('control') or {}).get('state')=='running' for st in clients.values())
            def work():
                try:self.live_chrome_result=self.live_chrome.step(busy)
                except Exception as e:self.live_chrome_result=dict(state='error',error=str(e),actions=[],client='')
            self.live_chrome_thread=threading.Thread(target=work,daemon=True,name='nbl-live-chrome');self.live_chrome_thread.start()
    def live_chrome_apply(self,res):
        for a in res.get('actions') or []:self.log('Chrome LIVE: '+a+'.')
        state=res.get('state','off');prev=getattr(self,'live_chrome_state','')
        self.live_chrome_state=state
        if state=='ok':
            self.live_chrome_ok_at=time.time()
            if not self.live_chrome.setup_done():self.live_chrome.mark_setup()
            clients=self.bridge.snapshot();client=res.get('client','')
            if client in clients:
                st=clients[client];session=self.live_chrome_session()
                if st.get('accountVerified') and resolve_binding(session.get('chrome_binding'),clients)!=client:
                    try:
                        session['chrome_binding']=make_binding(client,st);write_json(self.path,self.data)
                        self.log('Chrome LIVE đã kết nối nick '+str(session.get('number',''))+' · tài khoản Shop: '+str(st.get('account','')))
                    except Exception as e:self.log('Chưa gắn được Chrome LIVE: '+str(e))
        if state!=prev:
            if state in ('login','no_extension'):self.log(self.LIVE_CHROME_TEXT[state])
            if state=='login':
                try:self.notifier.publish('livechrome:login','⚠ Chrome LIVE: TikTok Shop đòi đăng nhập lại. Đăng nhập đúng nick trong cửa sổ Chrome LIVE trên máy tính.')
                except Exception:pass
        if res.get('error') and res.get('error')!=getattr(self,'live_chrome_err',''):self.live_chrome_err=res['error'];self.log('Chrome LIVE: '+res['error'][:200])
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
            if not binding:raise ValueError('Chrome chưa kết nối nick này: bấm "🌐 Mở Chrome LIVE của NBL".')
            if not client:raise ValueError('Tab/tài khoản đã gắn không còn kết nối. Không gửi lệnh sang tài khoản khác. Ghép đôi lại hoặc gắn lại đúng tab.')
            self.bridge.command(client,dict(action=action,module=key,expectedAccount=binding['account'],**({'config':self.pin_command_config()} if action=='start' else {})));self.log('Đã gửi '+action+' · '+key+'; chờ Chrome xác nhận.')
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
        lc=getattr(self,'live_chrome_state','off')
        self.chrome_binding_label.setText('✓ Chrome LIVE đã kết nối · tài khoản Shop: '+binding['account'] if st and binding else self.LIVE_CHROME_TEXT.get(lc,'Chrome LIVE: '+lc))
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
            ('🧪 Chạy thử (không phát LIVE)','NBL đọc Studio, trang TikTok Shop, AI và app điện thoại rồi báo mục nào thấy / chưa thấy. Chỉ đọc, không bấm gì, không phát LIVE.',self.run_selfcheck),
            ('Kiểm tra cập nhật NBL ngay','NBL tự kiểm tra bản mới khi mở và mỗi 6 giờ; tự cài lúc không LIVE, tự mở lại, giữ nguyên cài đặt.',lambda:self.check_update(manual=True)),
            ('Bật bộ báo động LIVE','Phát chuông khi đọc được cảnh báo cần xác minh; hiển thị cửa sổ cần chú ý.',self.open_alarm),
            ('Mở thư mục tiện ích Chrome','Chrome → chrome://extensions → Chế độ nhà phát triển → Tải tiện ích đã giải nén → chọn CHROME_NBL_LIVE.',lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(BASE/'CHROME_NBL_LIVE')))),
            ('Mở hướng dẫn','Cách cài tiện ích, tách âm thanh và nhận thông báo điện thoại.',lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(BASE/'HUONG_DAN_SU_DUNG.pdf' if (BASE/'HUONG_DAN_SU_DUNG.pdf').exists() else BASE/'HUONG_DAN_4.1.txt')))),
            ('Mở nhật ký','Nhật ký các phiên, Chrome, OBS và cảnh báo.',lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(DATA/'logs')))),
            ('Mở báo cáo hoạt động','Việc NBL đã làm: gửi tin, chào khách, tự đóng thông báo, ghép cửa sổ trò chuyện. Giữ 100 báo cáo mới nhất.',lambda:self.open_reports('hoat_dong')),
            ('Mở báo cáo lỗi','Việc chưa làm được, kèm ảnh Studio lúc lỗi. Giữ 100 báo cáo mới nhất, riêng với báo cáo hoạt động.',lambda:self.open_reports('loi'))]:
            v.addWidget(button(title,action,'primary'));lab=QLabel(desc);lab.setWordWrap(True);v.addWidget(lab)
        group=QGroupBox('App điện thoại NBL (Android)');pv=QVBoxLayout(group)
        lab=QLabel('Điện thoại và PC cùng Tailscale (hoặc cùng wifi). Cài APK NBL trên điện thoại → mở Camera quét mã QR dưới đây → app tự lưu PC này. Ai có mã QR là điều khiển được NBL: đừng gửi ảnh mã cho người lạ; lỡ lộ thì bấm Đổi mã.');lab.setWordWrap(True);pv.addWidget(lab)
        self.phone_qr=QLabel();self.phone_qr.setAlignment(Qt.AlignmentFlag.AlignCenter);pv.addWidget(self.phone_qr)
        self.phone_state=QLabel();self.phone_state.setWordWrap(True);self.phone_state.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse);pv.addWidget(self.phone_state)
        row=QHBoxLayout();self.phone_on=QCheckBox('Cho phép điều khiển từ điện thoại');row.addWidget(self.phone_on);row.addWidget(button('🔁 Đổi mã (điện thoại cũ phải quét lại)',self.phone_new_token));pv.addLayout(row);v.addWidget(group)
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
        self.logbox.append('<span>'+html.escape(time.strftime('%H:%M:%S')+'  '+text,quote=False).replace('\n','<br>')+'</span>');self.logger.info(text)   # 4.3.2: rich text, so & and " show as themselves
        if not hasattr(self,'phone_log'):
            import collections;self.phone_log=collections.deque(maxlen=400);self.phone_seq=0
        self.phone_seq+=1;self.phone_log.append((self.phone_seq,time.time(),text))
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
        s=self.current();s['chrome']={**s.get('chrome',{}),**self.chrome_config()}
        if hasattr(self,'pin_mode'):s['pin']=dict(mode=self.pin_mode.currentData(),products=self.pin_list.toPlainText().strip(),**{k:w.value() for k,w in self.pin_times.items()});s['pins']=s['pin']['products']
        s.update(account=self.account.text().strip(),playlist=self.playlist_paths(),volume=self.volume.value(),device=self.device.currentData() or '',mute=self.mute.isChecked(),loop=True,shuffle=self.shuffle.isChecked(),rules=self.rules.toPlainText(),messages=self.messages.toPlainText())
        self.data['settings']={**self.data.get('settings',{}),**dict(keep_awake=self.awake.isChecked(),obs_host=self.host.text().strip(),obs_port=self.port.value(),live_minutes=self.live_minutes.value(),rest_minutes=self.rest_minutes.value(),repeat=self.repeat.isChecked())}
    def save_current(self):
        self.collect();validate(self.data);write_json(self.path,self.data);self.refresh_list();self.log('Đã lưu phiên '+str(self.current()['number']))
        if self.current()['id'] in self.processes:self.command('settings',save=False)
    def fill(self):
        self.loading=True;s=self.current();self.account.setText(s['account']);self.playlist.clear();self.add_playlist_items(s['playlist']);self.volume.setValue(s['volume']);self.mute.setChecked(s['mute']);self.loop.setChecked(True);self.shuffle.setChecked(s['shuffle']);self.device.setCurrentIndex(max(0,self.device.findData(s['device'])))
        if s['device'] and self.device.findData(s['device'])<0:
            self.device.addItem('Thiết bị đã mất — chọn lại',s['device']);self.device.setCurrentIndex(self.device.count()-1)
        for key,w in [('pins',self.pins),('rules',self.rules),('messages',self.messages)]:w.setPlainText(s[key])
        p=self.pin_settings(s);self.pin_mode.setCurrentIndex(max(0,self.pin_mode.findData(p['mode'])));self.pin_list.setPlainText(p['products'])
        for k,w in self.pin_times.items():w.setValue(int(p.get(k,0)))
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
    def remove_session(self,session=None,ask=True):
        """4.3.4 (owner, 29/10/2026): any nick can be deleted, also one linked to TikTok LIVE Studio or
        Chrome (NBL unlinks it first). Never during its LIVE. A backup of the settings is kept."""
        s=session or self.current()
        if len(self.data['sessions'])<=1:
            if ask:QMessageBox.information(self,'Xóa nick','Phải còn ít nhất 1 nick.')
            return False
        sp=getattr(self,'studio_panel',None)
        linked=[p for p in (sp.profiles if sp else []) if p.get('session')==s['id']]
        ids={p['id'] for p in linked}
        if sp and any(j['profile'] in ids and j['state'] in ('preparing','starting','running','stopping','recovering','attention','stop_retry') for j in sp.jobs) or any(i in getattr(sp,'hand_live',{}) for i in ids):
            if ask:QMessageBox.information(self,'Nick đang LIVE','Nick này đang LIVE. Kết thúc LIVE trước rồi mới xóa nick.')
            return False
        pending=[j for j in (sp.jobs if sp else []) if j['profile'] in ids and j['state'] in ('pending','start_retry')]
        if ask:
            text='Xóa nick '+str(s.get('number',''))+' ('+str(s.get('account') or 'chưa đặt tên')+')?'
            if linked:text+='\n\nNick này đang nối TikTok LIVE Studio: NBL gỡ nối trước khi xóa (Studio sẽ tự nối vào nick còn lại).'
            if s.get('chrome_binding'):text+='\nNick này đang nối Chrome: NBL gỡ nối.'
            if pending:text+='\n\n'+str(len(pending))+' lịch LIVE chưa chạy của nick này sẽ bị HỦY.'
            text+='\n\nCó lưu bản sao cấu hình trước khi xóa.'
            if QMessageBox.question(self,'Xóa nick',text)!=QMessageBox.StandardButton.Yes:return False
        try:
            backup=DATA/'sao_luu';backup.mkdir(parents=True,exist_ok=True);stamp=time.strftime('%Y%m%d_%H%M%S')
            write_json(backup/('cau_hinh_truoc_xoa_nick_'+stamp+'.json'),self.data)
            if sp:write_json(backup/('lich_studio_truoc_xoa_nick_'+stamp+'.json'),dict(profiles=sp.profiles,jobs=sp.jobs))
        except Exception as e:
            if ask:QMessageBox.warning(self,'Xóa nick','Chưa lưu được bản sao, không xóa: '+str(e))
            return False
        try:
            client=resolve_binding(s.get('chrome_binding'),self.bridge.snapshot())
            if client:self.bridge.command(client,dict(action='stop',module='all'))
        except Exception:pass
        if s['id']==self.cycle_id:self.cancel_cycle()
        proc=self.processes.get(s['id'])
        if proc is not None and proc.poll() is None:
            try:proc.terminate()
            except Exception:pass
        if sp:
            for j in pending:sp.cancel_pending_starts(j);j['state']='cancelled';j['error']='Hủy vì đã xóa nick'
            for p in linked:sp.profiles.remove(p)
            sp.auto_at=0;sp.auto_launched=True
            try:sp.save()
            except Exception:pass
        index=self.data['sessions'].index(s);del self.data['sessions'][index]
        self.selected=0 if self.selected==index else self.selected-1 if index<self.selected else min(self.selected,len(self.data['sessions'])-1)
        write_json(self.path,self.data);self.refresh_list();self.fill()
        if sp:sp.refresh_profiles();sp.render()
        self.log('Đã xóa nick '+str(s.get('number',''))+(' (gỡ nối Studio/Chrome)' if linked or s.get('chrome_binding') else '')+(' · hủy '+str(len(pending))+' lịch' if pending else '')+'. Bản sao: '+str(DATA/'sao_luu'))
        return True
    def one_nick_cleanup(self):
        """4.3.4: this version runs ONE nick; leftover nick settings from the multi-nick time are offered for deletion once."""
        if len(self.data['sessions'])<=1 or self.data.get('settings',{}).get('one_nick_asked'):return
        keep=self.live_chrome_session()
        extra=[s for s in self.data['sessions'] if s is not keep]
        names=', '.join('nick '+str(s.get('number',''))+(' ('+str(s.get('account'))+')' if s.get('account') else '') for s in extra)
        answer=QMessageBox.question(self,'Bản này chỉ chạy 1 nick','NBL đang còn cấu hình nick thừa: '+names+'.\nGiữ lại nick '+str(keep.get('number',''))+' (đang dùng / đang nối Studio) và XÓA các nick thừa?\n\nCó lưu bản sao trước khi xóa.')
        self.data.setdefault('settings',{})['one_nick_asked']=True
        if answer==QMessageBox.StandardButton.Yes:
            self.selected=self.data['sessions'].index(keep)
            for s in extra:
                self.selected=self.data['sessions'].index(keep);self.remove_session(s,ask=False)
            self.selected=self.data['sessions'].index(keep);self.refresh_list();self.fill()
        try:write_json(self.path,self.data)
        except Exception:pass
    def add_video(self):
        paths,_=QFileDialog.getOpenFileNames(self,'Thêm video','','Video (*.mp4 *.mkv *.mov *.avi *.webm);;Tất cả (*)');existing=set(self.playlist_paths());self.add_playlist_items([p for p in paths if p not in existing])
    # ---------- 4.3.13: kho video NBL (gửi từ điện thoại) ----------
    def build_store(self,v):
        from video_store import VideoStore
        self.video_store=VideoStore(DATA/'videos');self.pending_deletes=[]
        g=QGroupBox('📱 Kho video NBL — gửi video từ điện thoại');gv=QVBoxLayout(g)
        self.store_list=QListWidget();self.store_list.setMaximumHeight(130);self.store_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection);gv.addWidget(self.store_list)
        grid=QGridLayout()
        for i,(text,action,kind) in enumerate([('📱 Mã QR gửi video từ điện thoại',self.store_qr,'primary'),('➕ Thêm vào playlist',self.store_add,''),('🗑 Xóa khỏi máy',self.store_delete,'danger'),('📂 Mở thư mục kho',lambda:(self.video_store.folder.mkdir(parents=True,exist_ok=True),QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.video_store.folder)))),'')]):
            grid.addWidget(button(text,action,kind),i//2,i%2)
        gv.addLayout(grid)
        self.store_note=QLabel('');self.store_note.setWordWrap(True);self.store_note.setObjectName('subtitle');gv.addWidget(self.store_note);v.addWidget(g)
        self.store_timer=QTimer(self);self.store_timer.timeout.connect(self.store_tick);self.store_timer.start(5000);self.refresh_store()
    def refresh_store(self):
        if not hasattr(self,'store_list'):return
        from video_store import human
        used=set()
        for s in self.data.get('sessions') or []:used.update(os.path.normcase(str(Path(p))) for p in s.get('playlist') or [])
        try:files=self.video_store.files()
        except OSError:files=[]
        keep={it.data(Qt.ItemDataRole.UserRole) for it in self.store_list.selectedItems()}
        rows=[(f['path'],f['name']+'   · '+human(f['size'])+('   ▶ trong playlist' if os.path.normcase(f['path']) in used else '   · chưa thêm playlist')+('   (đang chờ xóa)' if f['path'] in self.pending_deletes else '')) for f in files]
        if [(self.store_list.item(i).data(Qt.ItemDataRole.UserRole),self.store_list.item(i).text()) for i in range(self.store_list.count())]!=rows:
            self.store_list.clear()
            for path,text in rows:
                it=QListWidgetItem(text);it.setData(Qt.ItemDataRole.UserRole,path);it.setToolTip(path);self.store_list.addItem(it);it.setSelected(path in keep)
        total=sum(f['size'] for f in files)
        self.store_note.setText(('Kho có '+str(len(files))+' video ('+human(total)+'). ' if files else 'Kho chưa có video. ')+'Video gửi từ điện thoại tự vào playlist của nick đang chọn. Xóa ở đây là xóa hẳn file khỏi máy và gỡ khỏi playlist.')
    def store_tick(self):
        for path in list(self.pending_deletes):
            try:self.video_store.delete(path);self.pending_deletes.remove(path);self.log('Kho video: đã xóa '+Path(path).name+' (hết phát).')
            except PermissionError:pass
            except Exception:self.pending_deletes.remove(path)
        self.refresh_store()
    def store_selected(self):
        return [it.data(Qt.ItemDataRole.UserRole) for it in self.store_list.selectedItems()]
    def store_add(self):
        paths=self.store_selected()
        if not paths:QMessageBox.information(self,'Kho video','Chọn video trong kho trước.');return
        have={os.path.normcase(p) for p in self.playlist_paths()};new=[p for p in paths if os.path.normcase(p) not in have]
        self.add_playlist_items(new);self.save_current();self.refresh_store()
    def store_delete(self):
        paths=self.store_selected()
        if not paths:QMessageBox.information(self,'Kho video','Chọn video trong kho trước.');return
        if QMessageBox.question(self,'Xóa video','Xóa hẳn '+str(len(paths))+' video khỏi máy và gỡ khỏi playlist?\n\n'+'\n'.join(Path(p).name for p in paths[:8]))!=QMessageBox.StandardButton.Yes:return
        QMessageBox.information(self,'Kho video',self.delete_videos(paths))
    def video_uploaded(self,path,source='điện thoại'):
        """Video vừa gửi xong vào kho: thêm vào playlist của nick đang chọn."""
        from video_store import human
        nick=''
        if self.data.get('sessions'):
            if os.path.normcase(path) not in {os.path.normcase(p) for p in self.playlist_paths()}:
                self.add_playlist_items([path])
            self.save_current();nick=self.current().get('account') or ('nick '+str(self.current().get('number','')))
        size=Path(path).stat().st_size if Path(path).exists() else 0
        self.log('Kho video: nhận '+Path(path).name+' ('+human(size)+') từ '+source+(' → đã thêm vào playlist '+nick if nick else '')+'.')
        self.refresh_store()
        return dict(ok=True,name=Path(path).name,nick=nick)
    def delete_videos(self,paths,source=''):
        """Gỡ khỏi playlist mọi nick; file nằm trong kho NBL thì xóa hẳn (đang phát thì xóa khi hết phát)."""
        gone={os.path.normcase(str(Path(p))) for p in paths};touched=[]
        self.collect()
        for s in self.data.get('sessions') or []:
            keep=[p for p in s.get('playlist') or [] if os.path.normcase(str(Path(p))) not in gone]
            if len(keep)!=len(s.get('playlist') or []):s['playlist']=keep;touched.append(s)
        for i in reversed(range(self.playlist.count())):
            it=self.playlist.item(i)
            if os.path.normcase(str(Path(it.data(Qt.ItemDataRole.UserRole) or it.text()))) in gone:self.playlist.takeItem(i)
        write_json(self.path,self.data)
        for s in touched:
            try:self.command('settings',False,s)
            except Exception:pass
        deleted,later,kept=[],[],[]
        for p in paths:
            if not self.video_store.owns(p):kept.append(Path(p).name);continue
            try:self.video_store.delete(p);deleted.append(Path(p).name)
            except PermissionError:
                later.append(Path(p).name)
                if p not in self.pending_deletes:self.pending_deletes.append(p)
            except Exception as e:kept.append(Path(p).name+' ('+str(e)[:60]+')')
        parts=[]
        if deleted:parts.append('Đã xóa khỏi máy: '+', '.join(deleted))
        if later:parts.append('Đang phát nên sẽ tự xóa khi hết clip: '+', '.join(later))
        if kept:parts.append('Đã gỡ khỏi playlist (file không nằm trong kho NBL nên giữ nguyên): '+', '.join(kept))
        text='. '.join(parts) or 'Không có gì để xóa.'
        self.log('Kho video'+(' ('+source+')' if source else '')+': '+text);self.refresh_store();self.refresh_playlist_labels()
        return text
    def store_qr(self):
        import phone_api,qr,ipaddress
        if not hasattr(self,'phone_cfg'):return
        cfg=self.phone_cfg.load()
        if not cfg.get('enabled'):
            QMessageBox.information(self,'Gửi video từ điện thoại','Bật "Cho phép điều khiển từ điện thoại" ở trang Thiết lập & cảnh báo trước.');return
        hosts=phone_api.addresses()
        host=next((h for h in hosts if h[:1].isdigit() and ipaddress.ip_address(h) in phone_api.TAILSCALE),None) or next((h for h in hosts if h[:1].isdigit()),hosts[0])
        link='http://'+host+':'+str(cfg.get('port',phone_api.PORT))+'/upload?t='+cfg['token']
        m=qr.encode(link);n=len(m);scale=max(3,260//(n+8));img=QImage((n+8)*scale,(n+8)*scale,QImage.Format.Format_RGB32);img.fill(QColor('white'))
        painter=QPainter(img)
        for y,row in enumerate(m):
            for x,dark in enumerate(row):
                if dark:painter.fillRect((x+4)*scale,(y+4)*scale,scale,scale,QColor('black'))
        painter.end()
        d=QDialog(self);d.setWindowTitle('Gửi video từ điện thoại');lay=QVBoxLayout(d)
        pic=QLabel();pic.setPixmap(QPixmap.fromImage(img));pic.setAlignment(Qt.AlignmentFlag.AlignCenter);lay.addWidget(pic)
        t=QLabel('1. Điện thoại bật Tailscale (cùng tài khoản với PC này).\n2. Mở camera / Chrome quét mã → trang "Gửi video vào NBL".\n3. Chọn video → Gửi. Gửi xong video tự vào playlist nick đang chọn.\n\nKhông cần chung wifi. Mất mạng giữa chừng thì bấm Gửi lại, nó gửi tiếp chỗ dở.\n\nĐịa chỉ: '+link)
        t.setWordWrap(True);t.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse);lay.addWidget(t)
        row=QHBoxLayout();row.addWidget(button('Chép địa chỉ',lambda:QApplication.clipboard().setText(link)));row.addWidget(button('Đóng',d.accept,'primary'));lay.addLayout(row)
        d.exec()
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
    def quit_studio(self):
        """4.3.9 (chủ máy, 31/10/2026): đóng hẳn Studio bằng lệnh bên trong, không bấm
        dấu X — captcha hay hộp thoại che màn hình cũng tắt được."""
        try:self.studio_panel.quit_studio_now()
        except Exception as e:
            QMessageBox.warning(self,'Tắt TikTok LIVE Studio',str(e));return
        self.log('Đang tắt TikTok LIVE Studio…')
    def emergency(self):
        if hasattr(self,'studio_chat'):self.studio_chat.engine.stop_all()
        # 4.2.0 (owner, 28/10/2026): TẮT HẾT = end every LIVE (also by hand), cancel the
        # schedules not started, Telegram gets the result. NBL VIDEO keeps playing.
        if hasattr(self,"studio_panel"):
            try:self.studio_panel.emergency(None)
            except Exception as e:
                try:self.studio_panel.stop_all()
                except Exception as e2:self.log('Studio cần dừng thủ công: '+str(e2))
        for j in self.data.get('jobs',[]):
            if j['state']=='pending':j['state']='skipped'
        self.render_jobs()
        self.bridge.stop_all()
        if self.alarm_window:self.alarm_window.stop()
        self.cancel_cycle()
        if self.obs.connected or self.obs.busy:self.obs.submit('emergency')
        try:write_json(self.path,self.data)
        except Exception as e:self.log('Đã dừng, nhưng chưa lưu được cấu hình: '+type(e).__name__)
        self.log('Đã gửi lệnh dừng tất cả: video, Chrome, lịch OBS và bộ báo động.')
    # ---------------- 4.3.0 (owner): tự cập nhật ----------------
    # ---------------- 4.3.0 (owner): app điện thoại ----------------
    def start_phone_api(self):
        import phone_api,phone_actions
        self.phone_cfg=phone_api.Config(DATA/'phone_api.json')
        self.phone_server=phone_api.Server(phone_actions.Actions(self),self.phone_cfg,self.video_store,getattr(self,'remote_talk',None))
        self.phone_timer=QTimer(self);self.phone_timer.timeout.connect(self.phone_server.drain);self.phone_timer.start(100)
        cfg=self.phone_cfg.load();self.phone_on.blockSignals(True);self.phone_on.setChecked(bool(cfg.get('enabled')));self.phone_on.blockSignals(False)
        self.phone_on.toggled.connect(self.phone_toggle)
        if cfg.get('enabled'):self.phone_server.start()
        self.phone_refresh()
    def phone_toggle(self,on):
        cfg=self.phone_cfg.load();cfg['enabled']=bool(on);self.phone_cfg.save(cfg)
        if on:self.phone_server.start()
        else:self.phone_server.stop()
        self.log('App điện thoại: '+('cho phép' if on else 'đã tắt')+'.');self.phone_refresh()
    def phone_new_token(self):
        if QMessageBox.question(self,'Đổi mã ghép','Điện thoại đang ghép sẽ không điều khiển được nữa cho tới khi quét mã mới. Đổi mã?')!=QMessageBox.StandardButton.Yes:return
        self.phone_cfg.new_token();self.log('Đã đổi mã ghép điện thoại.');self.phone_refresh()
    def phone_refresh(self):
        import phone_api,qr
        cfg=self.phone_cfg.load();on=bool(cfg.get('enabled'))
        if not on:
            self.phone_qr.clear();self.phone_state.setText('Đang tắt điều khiển từ điện thoại.');return
        hosts=phone_api.addresses();link=phone_api.pair_link(cfg['token'],cfg.get('port',phone_api.PORT),hosts)
        m=qr.encode(link);n=len(m);scale=max(3,240//(n+8));img=QImage((n+8)*scale,(n+8)*scale,QImage.Format.Format_RGB32);img.fill(QColor('white'))
        painter=QPainter(img)
        for y,row in enumerate(m):
            for x,dark in enumerate(row):
                if dark:painter.fillRect((x+4)*scale,(y+4)*scale,scale,scale,QColor('black'))
        painter.end();self.phone_qr.setPixmap(QPixmap.fromImage(img))
        err=self.phone_server.error
        self.phone_state.setText(('⚠ '+err if err else '✓ Đang mở cổng '+str(cfg.get('port',phone_api.PORT))+' cho điện thoại.')+'\nĐịa chỉ PC: '+', '.join(hosts)+'\nKhông quét được thì trong app chọn "Thêm PC" và nhập địa chỉ + mã: '+cfg['token'])
    def run_selfcheck(self):
        """4.3.0 chế độ chạy thử: reads Studio + TikTok Shop + AI + phone; clicks nothing."""
        import threading,copy
        sp=self.studio_panel;p=sp.current_profile();lines=['STUDIO']
        profile=copy.deepcopy(sp.effective_profile(p)) if p and p.get('cdp') else None
        if not p:lines.append('✗ Chưa kết nối Studio: mở TikTok LIVE Studio bằng icon trên màn hình, NBL tự kết nối.')
        elif not p.get('cdp'):lines.append('✗ Nick đang dùng kiểu kết nối cũ (ảnh + chuột). Bấm menu → Kết nối lại TikTok LIVE Studio.')
        self.log('Chạy thử: đang đọc Studio, Chrome, AI…')
        box={}
        def work():
            try:
                from studio_cdp import execute_cdp
                box['studio']=execute_cdp(profile,'selfcheck')
            except Exception as e:box['studio_error']=str(e)
        if profile:
            t=threading.Thread(target=work,daemon=True,name='nbl-selfcheck');t.start()
        else:t=None
        def finish():
            if t and t.is_alive():QTimer.singleShot(300,finish);return
            r=box.get('studio')
            if box.get('studio_error'):lines.append('✗ '+box['studio_error'])
            if r:
                ok=lambda c:'✓' if c else '✗'
                lines.append(ok(r.get('nickname'))+' Nick trên Studio: '+(r.get('nickname') or 'chưa đọc được (Studio đang ở trang chủ?)'))
                lines.append(ok(r.get('hasButton'))+' Nút Phát LIVE / Kết thúc: '+('thấy' if r.get('hasButton') else 'KHÔNG thấy — Studio đổi giao diện?'))
                lines.append(('● Đang LIVE' if r.get('living') else '○ Chưa LIVE')+(' · ô bình luận '+('thấy' if r.get('chatBox') else 'KHÔNG thấy') if r.get('living') else ''))
                if r.get('comments',-1)>=0:lines.append('✓ Đọc khung chat: '+str(r['comments'])+' bình luận đang hiện')
                else:lines.append('✗ Chưa đọc được khung chat')
                if r.get('captcha'):lines.append('⚠ Captcha / xác minh đang hiện: '+str(r['captcha'])[:120])
                for d in r.get('dialogs') or []:lines.append('⚠ Thông báo đang mở: '+d)
            lines.append('');lines.append('TIKTOK SHOP (Chrome)')
            from session_binding import resolve_binding
            clients=self.bridge.snapshot();binding=self.current().get('chrome_binding')
            bound=resolve_binding(binding,clients) if binding else None
            if not clients:lines.append('✗ Chrome LIVE: '+self.LIVE_CHROME_TEXT.get(getattr(self,"live_chrome_state","off"),"chưa sẵn sàng")+'')
            else:
                st=clients.get(bound) or next(iter(clients.values()))
                try:want=json.loads((BASE/'CHROME_NBL_LIVE'/'manifest.json').read_text(encoding='utf-8')).get('version','')
                except Exception:want=''
                lines.append(('✓' if bound else '⚠')+' Tab trang LIVE: '+str(len(clients))+' tab'+('' if bound else ' (chưa gắn với nick này)'))
                lines.append(('✓' if st.get('version')==want else '✗')+' Tiện ích Chrome: '+(st.get('version') or 'bản cũ')+('' if st.get('version')==want else ' (cần '+want+'; NBL tự nạp lại, chưa được thì cài lại tiện ích)'))
                lines.append(('✓' if st.get('accountVerified') else '✗')+' Tài khoản trên trang Shop: '+str(st.get('account') or 'chưa đọc được'))
                n=len(st.get('cartTitles') or [])
                lines.append(('✓' if n else '⚠')+' Sản phẩm trong giỏ đọc được: '+str(n)+('' if n else ' (giỏ trống hoặc chưa tìm thấy thẻ sản phẩm)'))
                pin=(st.get('modules') or {}).get('pin') or {}
                if pin.get('error'):lines.append('✗ Ghim: '+pin['error'][:150])
                if st.get('captcha'):lines.append('⚠ Captcha trên trang Shop: '+st['captcha'][:120])
            lines.append('');lines.append('AI TRẢ LỜI BÌNH LUẬN')
            cfg=self.ai.settings.load();keys=self.ai.settings.api_keys(cfg)
            lines.append(('✓' if keys else '✗')+' Gemini API key: '+str(len(keys))+' key')
            lines.append(('✓ Bật' if cfg.get('enabled') else '○ Tắt')+' · kiểu '+{'chu':'chữ','giong':'giọng đọc','ca_hai':'chữ + giọng'}.get(cfg.get('mode'),'?'))
            if cfg.get('mode') in ('giong','ca_hai'):
                dev=self.current().get('device') or ''
                lines.append(('✓' if dev else '⚠')+' Giọng đọc phát chung thiết bị NBL VIDEO: '+(self.device.currentText() if dev else 'loa mặc định — chọn cáp ảo để giọng vào LIVE'))
            lines.append('');lines.append('APP ĐIỆN THOẠI')
            ps=getattr(self,'phone_server',None)
            lines.append(('✓ Đang mở cổng cho điện thoại' if ps and ps.httpd else '✗ '+(ps.error if ps and ps.error else 'Đang tắt')))
            text='\n'.join(lines);self.log('Kết quả chạy thử:\n'+text)
            box2=QMessageBox(self);box2.setWindowTitle('Chạy thử NBL (không phát LIVE)');box2.setText(text);box2.open()
        finish()
    def wrap_notifier(self):
        """4.3.0: every problem alert also gathers a diagnostic bundle by itself (max 1 / 30 min)."""
        publish=self.notifier.publish
        def wrapped(key,text,test=False):
            result=publish(key,text,test)
            if not test and str(key).split(':')[0] not in ('update','emergency_ok','info'):
                import threading
                def work():
                    try:
                        from diagnostics import auto
                        path=auto(DATA,str(key)+': '+str(text))
                        if path:self.auto_diag_path=str(path)
                    except Exception:pass
                threading.Thread(target=work,daemon=True,name='nbl-auto-diag').start()
            return result
        self.notifier.publish=wrapped
    def check_update(self,manual=False):
        if getattr(self,'update_busy',False):
            if manual:QMessageBox.information(self,'Cập nhật','Đang kiểm tra / tải bản mới…')
            return
        import threading,updater
        from diagnostics import VERSION
        self.update_busy=True;self.update_result=None;self.update_manual=manual
        def work():
            try:
                rel=updater.latest()
                if not updater.newer(rel,VERSION):self.update_result=('none',rel);return
                self.update_result=('found',rel)
            except Exception as e:self.update_result=('error',str(e))
        threading.Thread(target=work,daemon=True,name='nbl-update-check').start()
    def update_tick(self):
        now=time.time()
        if now>=getattr(self,'update_next',now+90):self.update_next=now+6*3600;self.check_update()
        if not hasattr(self,'update_next'):self.update_next=now+90
        r=getattr(self,'update_result',None)
        if not r:return
        kind,val=r
        if kind=='none':
            self.update_result=None;self.update_busy=False
            if getattr(self,'update_manual',False):QMessageBox.information(self,'Cập nhật','NBL đang là bản mới nhất.')
        elif kind=='error':
            self.update_result=None;self.update_busy=False;self.log('Kiểm tra cập nhật chưa được: '+val[:150])
            if getattr(self,'update_manual',False):QMessageBox.warning(self,'Cập nhật','Chưa kiểm tra được: '+val[:300])
        elif kind=='found':
            if not self.update_safe():
                if not getattr(self,'update_wait_noted',False):self.update_wait_noted=True;self.log('Có bản NBL '+val['version']+'; đợi lúc không LIVE / không có lịch trong 30 phút để tự cập nhật.')
                return
            self.update_result=None;self.log('Đang tải bản NBL '+val['version']+'…')
            import threading,updater
            def get():
                try:self.update_result=('ready',updater.download(val,BASE/'_update'))
                except Exception as e:self.update_result=('error',str(e))
            threading.Thread(target=get,daemon=True,name='nbl-update-get').start();self.update_version=val['version']
        elif kind=='ready':
            self.update_result=None
            if not self.update_safe():self.update_busy=False;return
            import updater
            try:
                self.notifier.publish('update','NBL LIVE đang tự cập nhật lên bản '+str(getattr(self,'update_version',''))+'; mở lại sau khoảng 1–2 phút.')
                self.log('Cài bản NBL '+str(getattr(self,'update_version',''))+'; NBL tự đóng rồi mở lại.')
                updater.run_installer(val)
                self._force_close=True;QTimer.singleShot(1500,self.close)
            except Exception as e:self.update_busy=False;self.log('Chưa cài được bản mới: '+str(e))
    def update_safe(self):
        sp=getattr(self,'studio_panel',None)
        if not sp:return False
        now=time.time()
        if sp.active():return False
        if any(j['state'] in ('pending','start_retry') and j['start']-now<1800 for j in sp.jobs):return False
        if getattr(sp,'hand_live',{}):return False
        return True
    def tick(self):
        self.update_tick()
        self.live_chrome_tick()
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
        getattr(self,'phone_server',None) and self.phone_server.stop()
        getattr(self,'ptt',None) and self.ptt.disarm(quiet=True)
        getattr(self,'remote_talk',None) and self.remote_talk.close(quiet=True)
        self.studio_chat.shutdown();getattr(self,'ai',None) and self.ai.shutdown();self.studio_panel.shutdown();__import__('studio_vision_rpc').close_service();self.notifier.close();set_awake(False);self.bridge.close();self.obs.close()
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
