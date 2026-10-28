"""Simple region selection on a frozen Studio image, never clicks live controls."""
import base64
import copy
import io
from pathlib import Path
from PySide6.QtCore import Qt, QRect, QPoint, QTimer
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                              QComboBox, QRubberBand, QMessageBox, QApplication)

LABELS = {'input':'Ô nhập tin nhắn — chỉ phần chữ, bỏ nút mặt cười',
          'send':'Nút Gửi — khoanh sát mũi tên và vòng tròn',
          'chat':'Khung chat — gồm tên khách, tin nhắn và nút Chào',
          'clock':'Đồng hồ LIVE — chỉ khoanh 00:00:00',
          'greeting':'Một nút Chào — khoanh sát cả nút'}

# 4.1.10 (owner, 26/10/2026): show the owner's own Studio screen with the right frame
# drawn in orange next to the picture, so choosing the regions is easy.
ASSETS = Path(__file__).resolve().parent / 'assets'
GUIDES = {'greeting': ('mau_khoanh_chao.png', 'Khoanh SÁT một nút "👋 Chào" như khung cam (nút nào cũng được).\nKhông khoanh thì NBL dùng nút Chào mẫu có sẵn.'),
          'chat': ('mau_khoanh_khung_chat.png', 'Khoanh cả khung chat như khung cam: tên khách, tin nhắn và cột nút Chào. Không lấy ô nhập tin.'),
          'input': ('', 'Khoanh phần chữ của ô nhập tin nhắn ở dưới khung chat, bỏ nút mặt cười.'),
          'send': ('', 'Khoanh sát nút Gửi (mũi tên trong vòng tròn) bên phải ô nhập.'),
          'clock': ('', 'Khoanh đúng đồng hồ 00:00:00 (khi chưa LIVE: khoanh quanh nút Phát LIVE).')}


def guide_for(key):
    """(image path or None, hint text) shown beside the Studio picture."""
    name, text = GUIDES.get(key, ('', ''))
    path = ASSETS / name if name else None
    return (path if path and path.is_file() else None), text


class RegionImage(QLabel):
    def __init__(self, pixmap, chosen):
        super().__init__()
        self.original = pixmap
        screen = QApplication.primaryScreen()
        available = screen.availableGeometry() if screen else QRect(0,0,1200,800)
        self.scale = min(1., min(920,max(300,available.width()-420))/pixmap.width(),
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
    selector.setStyleSheet('QComboBox{border:2px solid #f37021;border-radius:8px;padding:6px;font-weight:600}')
    layout.addWidget(selector)
    status = QLabel(); status.setWordWrap(True)
    guide_image = QLabel(); guide_text = QLabel(); guide_text.setWordWrap(True); guide_text.setFixedWidth(300)
    guide_text.setStyleSheet('color:#8a3a12;font-weight:600')
    reset_greeting = QPushButton('Bỏ nút Chào đã khoanh, dùng nút Chào mẫu có sẵn')
    def show_guide(*_):
        path, text = guide_for(selector.currentData())
        guide_text.setText(text)
        if path:
            guide_image.setPixmap(QPixmap(str(path)).scaledToWidth(300, Qt.TransformationMode.SmoothTransformation)); guide_image.show()
        else:
            guide_image.clear(); guide_image.hide()
        reset_greeting.setVisible(selector.currentData() == 'greeting' and bool(config.get('greetingImage')))
    def use_sample_greeting():
        config.pop('greetingImage', None); regions.pop('greeting', None); config.pop('greetingDefault', None)
        status.setText('Đã bỏ nút Chào tự khoanh; NBL sẽ dùng nút Chào mẫu có sẵn.'); show_guide()
    reset_greeting.clicked.connect(use_sample_greeting)
    selector.currentIndexChanged.connect(show_guide)
    def chosen(rect):
        key = selector.currentData(); regions[key] = rect
        if key in ('send','greeting'):
            x,y,w,h = rect; stream = io.BytesIO(); image.crop((x,y,x+w,y+h)).save(stream,format='PNG')
            config[key+'Image'] = base64.b64encode(stream.getvalue()).decode()
        status.setText('Đã khoanh: '+', '.join(LABELS[k].split(' — ')[0] for k in LABELS if k in regions))
        show_guide()
    row = QHBoxLayout(); layout.addLayout(row)
    row.addWidget(RegionImage(pixmap, chosen), 0, Qt.AlignmentFlag.AlignTop)
    side = QVBoxLayout(); row.addLayout(side)
    head = QLabel('MẪU KHOANH'); head.setStyleSheet('color:#d85f12;font-weight:700'); side.addWidget(head)
    side.addWidget(guide_image); side.addWidget(guide_text); side.addWidget(reset_greeting); side.addStretch(1)
    show_guide()
    layout.addWidget(status)
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
