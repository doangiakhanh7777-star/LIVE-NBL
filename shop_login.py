"""Show the selected Chrome profile's official login QR without taking its session.

Only transient PNG pixels enter the app. Browser cookies and credentials stay in
Chrome. A dashboard identity confirmation, not QR disappearance, completes login.
"""
import base64
import time
from urllib.parse import urlsplit


def resolve_login_client(binding, clients):
    """Never select another profile/account simply because it is connected."""
    if not isinstance(binding, dict) or not binding.get('instance'):
        return None
    matches = [(key, state) for key, state in clients.items()
               if state.get('instance') == binding['instance']]
    exact = [key for key, state in matches if state.get('tab') == binding.get('tab')]
    if len(exact) == 1:
        return exact[0]
    account = [key for key, state in matches
               if binding.get('account') and state.get('account') == binding['account']]
    return account[0] if len(account) == 1 else None


def decode_qr_image(value):
    """Bound PNG input before invoking Qt's image decoder; SVG/URLs are forbidden."""
    if not isinstance(value, str) or len(value) > 230000:
        raise ValueError('Ảnh mã QR không hợp lệ.')
    prefix = 'data:image/png;base64,'
    if not value.startswith(prefix):
        raise ValueError('Ảnh mã QR phải lấy trực tiếp từ trang đăng nhập.')
    try:
        data = base64.b64decode(value[len(prefix):], validate=True)
    except (ValueError, TypeError) as error:
        raise ValueError('Ảnh mã QR không đọc được.') from error
    if not data.startswith(b'\x89PNG\r\n\x1a\n') or len(data) < 24:
        raise ValueError('Ảnh mã QR không đọc được.')
    width, height = int.from_bytes(data[16:20], 'big'), int.from_bytes(data[20:24], 'big')
    if not (100 <= width <= 1024 and 100 <= height <= 1024):
        raise ValueError('Kích thước mã QR không hợp lệ.')
    return data


def safe_login_state(state, now=None):
    """Reject old/foreign-origin snapshots; callers must not persist QR pixels."""
    if not isinstance(state, dict):
        return {'state': 'waiting', 'error': 'Đang chờ Chrome trả về mã đăng nhập.'}
    result = {key: state[key] for key in ('state', 'error', 'account', 'pageUrl', 'observedAt', 'requestId', 'qrDataUrl') if key in state}
    page = urlsplit(str(result.get('pageUrl', '')))
    if page.scheme != 'https' or page.hostname not in ('shop.tiktok.com', 'www.tiktok.com', 'seller-vn.tiktok.com'):
        error = 'Chưa nhận được trang đăng nhập TikTok chính thức.'
        if result.get('state') not in ('qr', 'authenticated'):
            error = str(result.get('error') or error)[:500]
        return {'state': 'unavailable', 'error': error}
    try:
        age = (time.time() if now is None else now) - float(result.get('observedAt', 0))
    except (TypeError, ValueError):
        age = 999
    if not -5 <= age <= 20:
        return {'state': 'waiting', 'error': 'Đang cập nhật mã QR. Kiểm tra kết nối Chrome nếu chờ lâu.'}
    if result.get('state') == 'qr':
        decode_qr_image(result.get('qrDataUrl'))
    else:
        result.pop('qrDataUrl', None)
    return result


# Qt is imported after the pure validation helpers, so these can be checked on
# build hosts without the Windows UI runtime.
try:
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QImage, QPixmap
    from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
except ImportError:
    QWidget = None


if QWidget is not None:
    class ShopLoginPanel(QWidget):
        def __init__(self, bridge, binding_getter, parent=None):
            super().__init__(parent)
            self.bridge, self.binding_getter = bridge, binding_getter
            self.request_id = None
            self.request_account = None
            self.binding_signature = None
            self.last_image = None
            self.setWindowTitle('Đăng nhập TikTok Shop')
            layout = QVBoxLayout(self)
            title = QLabel('Đăng nhập TikTok Shop bằng mã QR')
            title.setWordWrap(True)
            layout.addWidget(title)
            self.account = QLabel('Chọn nick ở đầu app để đăng nhập.')
            self.account.setWordWrap(True)
            layout.addWidget(self.account)
            self.instructions = QLabel('Bấm Lấy mã đăng nhập, rồi dùng TikTok trên điện thoại quét mã và xác nhận.')
            self.instructions.setWordWrap(True)
            layout.addWidget(self.instructions)
            self.qr = QLabel('Mã QR sẽ hiện tại đây')
            self.qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.qr.setMinimumHeight(230)
            self.qr.setMaximumHeight(260)
            self.qr.setStyleSheet('background:white; color:#34556b; border:1px solid #c9e4f4; border-radius:14px; padding:12px;')
            row = QHBoxLayout()
            for text, operation in [('Lấy mã đăng nhập', 'open'), ('Lấy mã mới', 'refresh')]:
                button = QPushButton(text)
                button.clicked.connect(lambda _checked=False, op=operation: self.command(op))
                row.addWidget(button)
            layout.addLayout(row)
            layout.addWidget(self.qr)
            show = QPushButton('Mở trang trên Chrome')
            show.clicked.connect(lambda: self.command('show_browser'))
            layout.addWidget(show)
            self.status = QLabel('Chưa yêu cầu đăng nhập.')
            self.status.setTextFormat(Qt.TextFormat.PlainText)
            self.account.setTextFormat(Qt.TextFormat.PlainText)
            self.status.setWordWrap(True)
            layout.addWidget(self.status)
            layout.addStretch()
            self.timer = QTimer(self)
            self.timer.timeout.connect(self.poll)
            self.timer.start(1000)
            self.poll()

        def binding(self):
            value = self.binding_getter()
            return value if isinstance(value, dict) else {}

        def command(self, operation):
            binding = self.binding()
            client = resolve_login_client(binding, self.bridge.snapshot())
            if not client:
                self.clear_qr('Chưa kết nối đúng hồ sơ Chrome của nick này.')
                self.status.setText('Kết nối tiện ích Chrome của nick đang chọn trước. Mỗi nick dùng một hồ sơ Chrome riêng để giữ đúng đăng nhập.')
                return
            try:
                command_id = self.bridge.command(client, dict(action='shop_login', module='login', operation=operation, expectedAccount=binding.get('account', '')))
                if operation == 'show_browser':
                    self.status.setText('Đã yêu cầu mở đúng trang trên Chrome. Sau khi kiểm tra, quay lại app để xem mã QR.')
                    return
                self.request_id = command_id
                self.request_account = binding.get('account', '')
                self.clear_qr('Đang lấy mã QR từ TikTok…')
                self.status.setText('Đang chờ trang đăng nhập của đúng hồ sơ Chrome.')
            except Exception as error:
                self.status.setText(str(error))

        def clear_qr(self, text='Mã QR sẽ hiện tại đây'):
            self.last_image = None
            self.qr.clear()
            self.qr.setText(text)

        def poll(self):
            try:
                binding = self.binding()
                signature = (binding.get('instance'), binding.get('tab'), binding.get('account'))
                self.account.setText('Nick đang chọn: ' + str(binding.get('account') or 'Chưa kết nối Chrome'))
                if signature != self.binding_signature:
                    self.binding_signature = signature
                    self.request_id = self.request_account = None
                    self.clear_qr()
                    self.status.setText('Bấm Lấy mã đăng nhập khi cần.')
                if not self.request_id:
                    return
                clients = self.bridge.snapshot()
                client = resolve_login_client(binding, clients)
                if not client:
                    self.clear_qr('Mất kết nối với Chrome của nick này.')
                    return
                state = safe_login_state(clients[client].get('shopLogin'))
                if state.get('requestId') not in (None, self.request_id):
                    return
                status = state.get('state')
                if status == 'authenticated':
                    actual = str(state.get('account', ''))
                    if not actual or (self.request_account and actual != self.request_account):
                        self.clear_qr('Nick đăng nhập khác nick đang chọn.')
                        self.status.setText('Đăng nhập nhận được: ' + (actual or 'Chưa xác định') + '. Kiểm tra lại trước khi liên kết.')
                    else:
                        self.clear_qr('Đã đăng nhập ✓')
                        self.status.setText('Chrome đã xác nhận tài khoản: ' + actual)
                    return
                if status == 'qr':
                    data = state['qrDataUrl']
                    if data != self.last_image:
                        image = QImage.fromData(decode_qr_image(data), 'PNG')
                        if image.isNull():
                            raise ValueError('Không đọc được ảnh QR. Bấm Lấy mã mới.')
                        pixmap = QPixmap.fromImage(image).scaled(224, 224, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation)
                        self.qr.setPixmap(pixmap)
                        self.last_image = data
                    self.status.setText('Quét mã bằng TikTok trên điện thoại rồi xác nhận. App sẽ chờ Chrome xác nhận đúng nick.')
                else:
                    self.clear_qr('Mã đã hết hạn' if status == 'expired' else 'Đang chờ mã QR')
                    self.status.setText(str(state.get('error') or 'Chưa có mã QR. Bấm Mở trang trên Chrome để kiểm tra.'))
            except Exception as error:
                self.clear_qr('Chưa hiển thị được mã QR.')
                self.status.setText(str(error))

        def shutdown(self):
            self.timer.stop()
            self.clear_qr()
