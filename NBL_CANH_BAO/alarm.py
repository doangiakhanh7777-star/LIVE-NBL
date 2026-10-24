"""Qt warning monitor for the bundled runtime. Reads text only."""
import json
import queue
import subprocess
import sys
import threading
from pathlib import Path
from PySide6.QtCore import QTimer,Qt
from PySide6.QtWidgets import QApplication,QMainWindow,QWidget,QVBoxLayout,QLabel,QPushButton
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from theme import STYLE

class Alarm(QMainWindow):
    def __init__(self,parent=None,on_alert=None):
        super().__init__(parent);self.on_alert=on_alert;self.setWindowTitle('NBL LIVE · Cảnh báo');self.resize(430,350)
        self.running=False;self.latched=False;self.busy=False;self.ticks=0;self.generation=0;self.warnings=[];self.results=queue.Queue()
        w=QWidget();self.setCentralWidget(w);v=QVBoxLayout(w)
        label=QLabel('CẢNH BÁO LIVE · CẦN NGƯỜI XỬ LÝ');label.setObjectName('title');label.setWordWrap(True);v.addWidget(label)
        note=QLabel('Đọc chữ qua Windows; không xử lý xác minh. Không nhận diện cảnh báo dạng ảnh.');note.setWordWrap(True);v.addWidget(note)
        self.status=QLabel('Chưa theo dõi. Mở LIVE Studio rồi bấm BẮT ĐẦU.');self.status.setWordWrap(True);v.addWidget(self.status)
        for text,action in [('BẮT ĐẦU',self.start),('DỪNG',self.stop),('MỞ CỬA SỔ CẦN CHÚ Ý',self.open_warning),('THỬ CHUÔNG',self.alert),('TÔI ĐÃ XỬ LÝ',self.ack)]:
            b=QPushButton(text);b.clicked.connect(action);v.addWidget(b)
        self.timer=QTimer(self);self.timer.timeout.connect(self.tick);self.timer.start(500)
    def start(self):
        if not self.running:self.generation+=1;self.running=True;self.timer.start(500);self.status.setText('Đang theo dõi · khoảng 5 giây/lần.')
    def stop(self):self.generation+=1;self.running=False;self.ack();self.status.setText('Đã dừng.')
    def ack(self):
        self.generation+=1;self.latched=False;self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint,False);self.show();self.status.setText('Đã tắt chuông; cảnh báo còn thì sẽ báo lại.')
        if sys.platform=='win32':
            import winsound
            winsound.PlaySound(None,0)
    def open_warning(self):
        if sys.platform!='win32' or not self.warnings:self.status.setText('Chưa có cửa sổ Windows cần mở.');return
        import ctypes
        from ctypes import wintypes
        handle=int(self.warnings[0].get('handle',0))&0xffffffff
        user=ctypes.WinDLL('user32',use_last_error=True)
        user.IsWindow.argtypes=[wintypes.HWND];user.IsWindow.restype=wintypes.BOOL
        user.ShowWindow.argtypes=[wintypes.HWND,ctypes.c_int];user.ShowWindow.restype=wintypes.BOOL
        user.SetForegroundWindow.argtypes=[wintypes.HWND];user.SetForegroundWindow.restype=wintypes.BOOL
        if not handle or not user.IsWindow(handle):self.status.setText('Cửa sổ đã đóng hoặc chưa đọc được vị trí.');return
        user.ShowWindow(handle,9);user.SetForegroundWindow(handle)
    def alert(self):self.latched=True;self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint,True);self.showNormal();self.raise_();self.status.setText('Cần chú ý: quay lại LIVE Studio để xử lý.')
    def scan(self,generation):
        try:
            script=Path(__file__).with_name('read_warning.ps1')
            p=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(script)],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=15,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if p.returncode:raise RuntimeError('Không đọc được giao diện Windows.')
            result=json.loads(p.stdout);result['_generation']=generation;self.results.put(result)
        except Exception as e:self.results.put({'error':str(e),'_generation':generation})
    def tick(self):
        try:
            result=self.results.get_nowait();self.busy=False
            if self.running and result.get('_generation')==self.generation:
                if result.get('error'):self.status.setText('Không đọc được giao diện; theo dõi LIVE Studio trực tiếp.')
                elif result.get('warning'):
                    self.warnings=result.get('warnings',[])
                    fresh=not self.latched;self.alert();self.status.setText('Cần xác minh:\n'+'\n'.join(str(x.get('title',''))+' · '+str(x.get('countdown','')) for x in result.get('warnings',[])))
                    if fresh and self.on_alert:self.on_alert(result.get('warnings',[]))
                elif not self.latched:self.warnings=[];self.status.setText('Đã quét '+str(result.get('windows',0))+' cửa sổ; chưa thấy chữ cảnh báo.')
        except queue.Empty:pass
        if self.latched:
            try:
                import winsound
                winsound.PlaySound('SystemExclamation',winsound.SND_ALIAS|winsound.SND_ASYNC)
            except ImportError:QApplication.beep()
        if self.running and not self.busy and self.ticks%10==0:self.busy=True;threading.Thread(target=self.scan,args=(self.generation,),daemon=True).start()
        self.ticks+=1
    def closeEvent(self,event):
        self.generation+=1;self.running=False;self.latched=False;self.timer.stop();super().closeEvent(event)
if __name__=='__main__':
    a=QApplication(sys.argv);a.setStyleSheet(STYLE);w=Alarm();w.show();sys.exit(a.exec())
