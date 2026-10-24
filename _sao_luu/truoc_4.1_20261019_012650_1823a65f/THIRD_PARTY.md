# Thành phần bên thứ ba
- Qt/PySide6: LGPLv3/GPLv3 hoặc giấy phép thương mại, https://doc.qt.io/qtforpython-6/licenses.html . Bản nguồn dùng Qt động; nếu phân phối binary hãy kèm giấy phép Qt/PySide và đáp ứng nghĩa vụ tương ứng.
- Qt Multimedia có thể sử dụng FFmpeg; giấy phép phụ thuộc binary backend. Xem giấy phép trong gói Qt trước khi phân phối.
- obsws-python: MIT, https://github.com/aatikt/obsws-python .
- Tiện ích Chrome / engine và LiveCycle kế thừa mã TOOL NBL LIVE đã tạo trong phiên này.
- Logo PNG được bỏ nền trắng ngoài huy hiệu từ ảnh người dùng cung cấp; ICO được chuyển định dạng từ PNG này.
Không liên kết hay được TikTok bảo trợ.

NBL LIVE 3.6 includes official CPython 3.12.10 embeddable runtime (PSF license in runtime/LICENSE.txt), PySide6 Essentials/Addons/Shiboken6 6.12.0 (Qt LGPL/GPL/commercial notices in bundled packages and license texts in licenses/), obsws-python 1.8.0, websocket-client 1.9.2, websockets 16.1.1 (licenses in dist-info directories). NSIS 3.09 generates installer/launcher. Application and installer source provided separately. Upstream sources: https://www.python.org/ftp/python/3.12.10/ ; https://code.qt.io/cgit/pyside/pyside-setup.git/ ; https://code.qt.io/cgit/qt/ ; https://github.com/python-websockets/websockets ; https://github.com/aatikturk/obsws-python ; https://github.com/websocket-client/websocket-client ; https://nsis.sourceforge.io/ .


## NBL 3.9 offline OCR
RapidOCR 1.4.4 and bundled ONNX models; ONNX Runtime 1.20.1; NumPy 1.26.4; OpenCV 4.10.0.84, Pillow, Shapely, PyClipper and transitive dependencies. Original license/notice files are preserved in ocr_vendor/*.dist-info (including licenses directories) and package directories. OCR runs locally; no cloud OCR endpoint is configured.


## Vietnamese recognition model (4.0.2)

PP-OCRv6 medium, fine-tuned OcrDoc Run 6, by truonggiabao7/e4glevlr.
Source: https://huggingface.co/truonggiabao7/ocrdoc-models
Weights licensed Apache-2.0 per the author model card. License text bundled at
ocr_models/vi/LICENSE-PaddleOCR.txt. Exact SHA256 recorded in MODEL_INFO.json.
Only recognition weights and their matching charset are redistributed.
