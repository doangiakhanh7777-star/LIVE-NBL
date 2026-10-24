"""Simple region selection on a frozen Studio image, never clicks live controls."""
import base64
import copy
import io
from PySide6.QtCore import Qt, QRect, QPoint, QTimer
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                              QComboBox, QRubberBand, QMessageBox, QApplication)

LABELS = {'input':'Ô nhập tin nhắn — chỉ phần chữ, bỏ nút mặt cười',
          'send':'Nút Gửi — khoanh sát mũi tên và vòng tròn',
          'chat':'Khung chat — gồm tên khách, tin nhắn và nút Chào',
          'clock':'Đồng hồ LIVE — chỉ khoanh 00:00:00',
          'greeting':'Một nút Chào — khoanh sát cả nút'}


class RegionImage(QLabel):
    def __init__(self, pixmap, chosen):
        super().__init__()
        self.original = pixmap
        screen = QApplication.primaryScreen()
        available = screen.availableGeometry() if screen else QRect(0,0,1200,800)
        self.scale = min(1., min(920,max(300,available.width()-80))/pixmap.width(),
                         max(180,available.height()-240)/pixmap.height())
        self.setPixmap(pixmap.scaled(round(pixmap.width()*self.scale), round(pixmap.height()*self.scale),
                                     Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.setFixedSize(self.pixmap().size())
        self.band = QRubberBand(QRubberBand.Shape.Rectangle, self)
        self.chosen, self.origin = chosen, None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.origin = event.position().toPoint()
            self.band.setGeometry(QRect(self.origin, self.origin)); self.band.show()

    def mouseMoveEvent(self, event):
        if self.origin is not None:
            self.band.setGeometry(QRect(self.origin, event.position().toPoint()).normalized().intersected(self.rect()))

    def mouseReleaseEvent(self, event):
        if self.origin is None:
            return
        r = QRect(self.origin, event.position().toPoint()).normalized().intersected(self.rect())
        self.origin = None
        if r.width() < 8 or r.height() < 8:
            return
        self.chosen([round(r.x()/self.scale), round(r.y()/self.scale),
                     min(round(r.width()/self.scale), self.original.width()-round(r.x()/self.scale)),
                     min(round(r.height()/self.scale), self.original.height()-round(r.y()/self.scale))])


def configure_vision(panel):
    p = panel.profile()
    if not p:
        QMessageBox.information(panel, 'Đọc bằng ảnh', 'Kết nối cửa sổ Studio cho nick này trước.'); return
    if panel.studio.driving() or any(panel.engine.state(p['id'])[k] for k in ('message','greeting')):
        QMessageBox.information(panel, 'Đang chạy', 'Dừng lịch, nhắn mẫu và Chào trước khi khoanh lại vùng.'); return
    from studio_scheduler import execute
    profile = panel.studio.effective_profile(p)
    future = panel.studio.pool.submit_priority(20, execute, profile, 'vision_capture')
    panel.message_status.setText('Đang lấy ảnh Studio; không bấm hay gửi tin…')
    timer = QTimer(panel)
    def ready():
        if not future.done(): return
        timer.stop(); timer.deleteLater()
        try:
            if panel.profile() is None or panel.profile()['id'] != p['id']:
                return
            result = future.result()
            show_regions(panel, p, result)
        except Exception as error:
            QMessageBox.warning(panel, 'Đọc bằng ảnh', str(error))
    timer.timeout.connect(ready); timer.start(200)


def show_regions(panel, profile, capture):
    from PIL import Image
    raw = base64.b64decode(capture['image'])
    image = Image.open(io.BytesIO(raw))
    pixmap = QPixmap.fromImage(QImage.fromData(raw, 'PNG'))
    config = copy.deepcopy(profile.get('vision', {}))
    geometry = (capture['width'], capture['height'], capture['dpi'])
    if (config.get('width'),config.get('height'),config.get('dpi')) != geometry:
        config = {}
    config.update(enabled=True, width=capture['width'], height=capture['height'], dpi=capture['dpi'])
    regions = config.setdefault('regions', {})
    dialog = QDialog(panel); dialog.setWindowTitle('Khoanh vùng Studio — ảnh tĩnh, không thao tác LIVE')
    layout = QVBoxLayout(dialog)
    note = QLabel('Chọn mục bên dưới rồi giữ chuột kéo một khung trên ảnh. Lưu riêng theo nick.\nCần khoanh lại nếu đổi kích thước Studio hoặc tỷ lệ màn hình.'); note.setWordWrap(True); layout.addWidget(note)
    selector = QComboBox()
    for key, label in LABELS.items(): selector.addItem(label, key)
    layout.addWidget(selector)
    status = QLabel(); status.setWordWrap(True)
    def chosen(rect):
        key = selector.currentData(); regions[key] = rect
        if key in ('send','greeting'):
            x,y,w,h = rect; stream = io.BytesIO(); image.crop((x,y,x+w,y+h)).save(stream,format='PNG')
            config[key+'Image'] = base64.b64encode(stream.getvalue()).decode()
        status.setText('Đã khoanh: '+', '.join(LABELS[k].split(' — ')[0] for k in LABELS if k in regions))
    layout.addWidget(RegionImage(pixmap, chosen)); layout.addWidget(status)
    note = QLabel('Nhắn mẫu cần: ô nhập, nút Gửi, khung chat, đồng hồ. Chào cần thêm một nút Chào mẫu.\nKhi chạy bằng ảnh, NBL có thể đưa Studio lên trước. Các mục Chrome vẫn không dùng chuột.'); note.setWordWrap(True); layout.addWidget(note)
    buttons = QHBoxLayout(); layout.addLayout(buttons)
    save = QPushButton('Lưu các vùng đã khoanh'); cancel = QPushButton('Hủy'); buttons.addWidget(save); buttons.addWidget(cancel)
    cancel.clicked.connect(dialog.reject)
    def accept():
        try:
            from studio_vision_logic import validate_regions
            validate_regions(config, ('clock', 'chat'))
            previous = profile.get('vision')
            profile['vision'] = config
            try:
                panel.studio.save()
            except Exception:
                if previous is None:profile.pop('vision', None)
                else:profile['vision'] = previous
                raise
            panel.message_status.setText('Đã lưu vùng theo nick. Bấm Kiểm tra ô nhắn tin trước khi bật.')
            dialog.accept()
        except Exception as error: QMessageBox.warning(dialog, 'Chưa lưu', str(error))
    save.clicked.connect(accept); dialog.exec()
