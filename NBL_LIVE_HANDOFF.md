# NBL LIVE — Bàn giao dự án (nhánh `nbl-4.2`)

_Cập nhật: 28/10/2026 · bản 4.2.0_

Tài liệu cho người/AI tiếp tục phát triển. Không chứa token, mã bot hay mật khẩu.

## Nhánh

| Nhánh | Dùng cho |
|---|---|
| `nbl-4.2` | **Nhánh đang phát triển.** Lõi 4.1.16 + 4.2.0. |
| `openclaw-local-api` | Bản cũ (lõi 4.1.14 + OpenClaw/MCP/Local API + 3 file patch). Giữ để tra cứu, không phát triển tiếp. |
| `main` | Không đụng khi chưa được yêu cầu. |

## Kiến trúc

```
NBL LIVE (Windows, PySide6, Python nhúng trong runtime/)
 ├─ Studio: đọc ảnh màn hình (OCR RapidOCR) + chuột Win32 → TikTok LIVE Studio
 ├─ ChromeBridge WebSocket 17869–17871 → tiện ích CHROME_NBL_LIVE → TikTok Shop LIVE dashboard
 ├─ NBL VIDEO (player.py) phát clip vào Studio
 └─ Telegram: CHỈ GỬI THÔNG BÁO (không nhận lệnh)
```

Đã bỏ ở 4.2.0: OpenClaw, MCP `nbl-live`, WSL, OmniRoute, lệnh chat Telegram, `app_with_api.py`, 3 file patch (`cart_retry/chrome_reload/strict_cart_gate`). Điều khiển từ xa sẽ là **app điện thoại Android (4.2.1)** qua Tailscale.

## Quy tắc bất biến

1. **Giỏ hàng (luật cứng):** LIVE bán hàng chỉ phát khi giỏ của đúng lịch đó đã thêm đúng bộ VÀ kiểm tra lại > 0 sản phẩm (`StudioPanel.cart_ok`). Không dùng giỏ cũ, không fallback, đọc không được = chưa sẵn sàng. Thêm lỗi → tải lại trang (chỉ khi Studio chắc chắn không LIVE) → thử lại suốt khung giờ; xong thì phát trễ; hết khung → bỏ lịch + báo Telegram. Không còn "LIVE thử 5 giây để reset giỏ".
2. **CAPTCHA:** chỉ phát hiện + báo Telegram 5 lần. Không bao giờ tích hợp bộ giải/vượt CAPTCHA.
3. **NBL VIDEO:** NBL không bao giờ dừng/đóng video của chủ (kể cả khi tắt khẩn cấp).
4. Không bấm Studio khi chưa xác nhận đúng nick (ảnh tên nick).

## 4.2.0 có gì

- Giao diện: nền xanh/trắng, cam Hermès `#f37021` (theme.py), trang dạng thẻ.
- **Tắt khẩn cấp:** nút `🛑 TẮT HẾT` (giữ 2 giây) và `Tắt LIVE nick này` (trang Lịch). Hủy lịch chưa chạy, kết thúc mọi LIVE kể cả bật tay, tắt ghim/trả lời Chrome; Telegram báo kết quả + nhắc lên lịch lại (`StudioPanel.emergency / poll_emergency`).
- **Lịch nhóm:** 2 nick cùng giờ, nick 2 phát sau 30 giây; tối đa 2 nick LIVE cùng lúc trên một máy (`GROUP_GAP`, `MAX_NICKS`).
- Bộ cài nén LZMA solid 128 MB, bỏ phần Qt/OCR không dùng (`build/build_installer.py`): ~119 MB (cũ 187 MB).

## Lộ trình

1. ~~4.2.0~~ (xong)
2. ~~4.2.1 — kết nối Studio tự động (DevTools, `studio_cdp.py`) + Chrome tự mở và tự ghép (`#nbl=<mã>`)~~ (xong; chào khách qua kết nối mới chưa có, trang tổng kết Studio được ghi vào `logs/studio_trang_ket_thuc_*.json` để làm tiếp)
3. 4.2.2 — app Android "NBL thu nhỏ": giao diện như NBL PC, nhiều PC (ghép QR), có cắm cờ kịch bản ghim trên video; kết nối Tailscale; APK build bằng GitHub Actions.
4. AI trả lời bình luận (Gemini) + giọng đọc.
5. Khóa bản quyền (để sau).

## Làm việc

- Test: `python -m unittest discover -s tests` (4 lỗi môi trường ở `test_audit402` khi không chạy trên Windows là bình thường) và `node --test tests/*.test.js`.
- Giao bản cho chủ: bản vá zip + `CAI_BAN_VA.bat` (chép file, sao lưu, cập nhật `SETUP_FILES.json`) hoặc bộ cài đầy đủ (`build/HOW_TO_BUILD.txt`).
- Dữ liệu người dùng: `%LOCALAPPDATA%\NBL_LIVE_2` (không bị bộ cài/bản vá đụng tới).
- Không có gì được kiểm chứng trên Windows thật khi chưa chạy trên máy chủ — nói rõ điều đó khi giao bản.
