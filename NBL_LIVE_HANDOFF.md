# NBL LIVE — Project Handoff / Context Pack

_Last updated: 2026-10-28_

> Tài liệu này bàn giao toàn bộ bối cảnh dự án **NBL LIVE** cho AI khác (Claude, ChatGPT, Codex...) hoặc người tiếp tục phát triển.
>
> **Không làm lại từ đầu.** Tiếp tục từ trạng thái hiện tại của branch `openclaw-local-api`.
>
> **Không chứa secret**: không có Telegram Bot Token, OpenRouter API key, OmniRoute key, Local API token hay mật khẩu TikTok.

---

## 1. Mục tiêu dự án

NBL LIVE là công cụ Windows hỗ trợ vận hành TikTok LIVE với các mục tiêu chính:

- Điều khiển TikTok LIVE Studio.
- Chạy lịch LIVE theo giờ.
- Chuẩn bị giỏ hàng / bộ sản phẩm trước khi LIVE.
- Kiểm tra trạng thái LIVE.
- Điều khiển từ xa qua Telegram.
- Telegram có thể dùng lệnh direct không cần AI cho các tác vụ cơ bản.
- OpenClaw + MCP + Local API kết nối Telegram/AI với app NBL LIVE.
- Chrome Extension thao tác TikTok Shop LIVE product dashboard.
- Mỗi PC có thể chạy độc lập với một bot Telegram riêng.

Kiến trúc tổng quát:

```text
Telegram
   ↓
OpenClaw
   ↓
MCP nbl-live
   ↓
NBL Local API
   ↓
NBL LIVE
   ↓
TikTok LIVE Studio

Song song:

NBL LIVE
   ↓
ChromeBridge WebSocket
   ↓
Chrome Extension NBL LIVE
   ↓
TikTok Shop LIVE product dashboard
```

---

## 2. Repo GitHub

Repository:

```text
https://github.com/doangiakhanh7777-star/LIVE-NBL.git
```

Branch đang phát triển:

```text
openclaw-local-api
```

Không tự ý merge vào `main`.

Commit quan trọng gần nhất đã dùng trong quá trình cập nhật:

```text
1a7859412256fcf3465511e9d1d706b3b1d8f9c9
```

Commit này có bản vá an toàn quan trọng về giỏ hàng.

---

## 3. Quy tắc làm việc bắt buộc

Khi AI khác nhận tài liệu này:

- Không rewrite toàn bộ app.
- Không đổi kiến trúc nếu chưa có lý do rõ ràng.
- Không xóa logic hiện có chỉ để “làm sạch”.
- Không merge vào `main` nếu chưa được yêu cầu.
- Mọi thay đổi tiếp tục trên `openclaw-local-api`.
- Đọc code thật trong repo trước khi sửa.
- Xác định luồng runtime hiện tại.
- Sửa tối thiểu, tránh tạo hệ thống song song trùng chức năng.

---

## 4. Kiến trúc Windows / WSL

### Windows

Các thành phần chính:

```text
NBL LIVE
Python
Chrome
Chrome Extension NBL LIVE
TikTok LIVE Studio
OmniRoute
```

NBL LIVE chạy Local API:

```text
0.0.0.0:8766
```

Health endpoint:

```text
GET /health
```

Token Local API được app tự tạo tại:

```text
%LOCALAPPDATA%\NBL_LIVE_2\local_api_token.txt
```

Ví dụ:

```text
C:\Users\ADMIN\AppData\Local\NBL_LIVE_2\local_api_token.txt
```

Không hardcode token vào source.

### WSL / Ubuntu

Ubuntu WSL chạy:

```text
OpenClaw
MCP nbl-live
Telegram Gateway
```

Gateway thường chạy bằng:

```bash
openclaw gateway run
```

Nếu chưa cài service tự khởi động thì cửa sổ này phải giữ mở.

### OmniRoute

OmniRoute chạy trên Windows, port:

```text
20128
```

Trong WSL lấy IP Windows động bằng:

```bash
WINHOST=$(ip route | awk '/default/ {print $3; exit}')
```

Không hardcode IP vì IP có thể thay đổi sau reboot.

---

## 5. Local API của NBL LIVE

Các endpoint hiện tại:

```text
GET    /health
GET    /api/accounts
GET    /api/schedules
GET    /api/live/status
POST   /api/schedules
POST   /api/schedules/<JOB_ID>/cancel
POST   /api/schedules/<JOB_ID>/stop
POST   /api/schedules/<JOB_ID>/cart/retry
DELETE /api/schedules/<JOB_ID>
```

Tất cả `/api/*` dùng Bearer token. `/health` không yêu cầu token.

Test Windows:

```powershell
Invoke-RestMethod http://127.0.0.1:8766/health
```

---

## 6. MCP `nbl-live`

File:

```text
nbl_mcp_server.py
```

Các MCP tool quan trọng:

```text
nbl_accounts
nbl_schedules
nbl_live_status
nbl_create_schedule
nbl_retry_cart
nbl_cancel_schedule
nbl_stop_schedule
```

Test MCP:

```bash
openclaw mcp doctor nbl-live --probe
```

Kết quả mong muốn:

```text
nbl-live: ok
```

---

## 7. Telegram

### Kiến trúc khuyến nghị nhiều PC

Khuyến nghị hiện tại:

```text
PC1 → Bot Telegram riêng
PC2 → Bot Telegram riêng
PC3 → Bot Telegram riêng
```

Tức là:

```text
1 bot = 1 PC
```

Lợi ích:

- Không nhầm máy.
- Không tranh polling.
- Debug dễ.
- Lỗi PC này không ảnh hưởng PC khác.

Sau này có thể làm bot tổng chỉ huy nhiều máy, nhưng chưa phải ưu tiên hiện tại.

### Lệnh Telegram direct hiện tại

Các lệnh đã chốt cần nhớ:

```text
/kiemtra
/huylich JOB_ID
/dunglive JOB_ID
```

Một số code cũ có namespace dạng:

```text
/nbl_help
/nbl_status
/nbl_schedules
/nbl_create
/nbl_cancel
/nbl_stop
```

Nhưng UX hiện tại ưu tiên lệnh tiếng Việt direct.

`/huylich` và `/dunglive` hiện cần đúng `JOB_ID`.

---

## 8. Chrome Extension NBL LIVE

Thư mục:

```text
CHROME_NBL_LIVE
```

Load trong Chrome:

```text
chrome://extensions
```

Bật Developer mode → Load unpacked → chọn thư mục `CHROME_NBL_LIVE`.

Sau mỗi `git pull` nếu extension thay đổi:

1. Vào `chrome://extensions`.
2. Bấm `Reload` extension NBL LIVE.
3. Reload TikTok Shop LIVE product dashboard.

---

## 9. ChromeBridge

Chrome extension kết nối NBL qua WebSocket.

Dải port đã dùng:

```text
17869–17871
```

Các action chính:

```text
prepare_bundle
cart_check
start
stop
finish_live
reload_dashboard
```

`reload_dashboard` được thêm để reload dashboard khi giỏ hàng bị lỗi.

---

## 10. Reload giỏ hàng

Vấn đề cũ:

- TikTok Shop dashboard đôi khi không thêm được giỏ hàng.
- Người dùng thường không ở trước PC.
- Cần app tự reload trang và thử lại trước giờ LIVE.

Các file liên quan:

```text
cart_retry_patch.py
chrome_reload_patch.py
CHROME_NBL_LIVE/background.js
app_with_api.py
```

Luồng:

```text
Chuẩn bị giỏ thất bại
→ kiểm tra TikTok LIVE Studio chắc chắn chưa LIVE
→ ChromeBridge gửi reload_dashboard
→ Chrome Extension reload dashboard
→ đợi trang lên
→ thử prepare cart lại
```

Không reload dashboard nếu LIVE đang chạy hoặc trạng thái LIVE không xác định.

---

## 11. STRICT CART GATE — quy tắc an toàn quan trọng nhất

### Yêu cầu bất biến

**LIVE bán hàng tuyệt đối không được bắt đầu nếu đúng bộ sản phẩm của lịch đó chưa được chuẩn bị và xác nhận thành công.**

Không được phép:

- Dùng giỏ cũ.
- Dùng fallback giỏ cũ.
- Cho LIVE chạy khi không đọc được số lượng sản phẩm.
- Cho LIVE chạy chỉ vì cart state trước đó là ready.
- Cho LIVE chạy khi add bundle thất bại.

### Bug cũ đã phát hiện

#### Lỗ hổng 1

Khi không đọc được số lượng cart (`count = -1`), logic cũ có thể vẫn coi là verified nếu cart state đã `ready`.

#### Lỗ hổng 2

Sau nhiều lần add cart thất bại, code cũ có thể `cart_check`; nếu thấy cart hiện có > 0 thì dùng cart cũ làm fallback và vẫn cho LIVE chạy.

Điều này không được chấp nhận.

### Bản vá strict cart gate

File:

```text
strict_cart_gate_patch.py
```

Được cài trong:

```text
app_with_api.py
```

Điều kiện cho sales LIVE:

```text
cart.state == "ready"
cart.verified == True
cart.prepared_for == bundle_index hiện tại
cart.last_count > 0
```

Nếu thiếu bất kỳ điều kiện nào:

```text
KHÔNG ĐƯỢC START LIVE
```

Nếu cart có:

```text
fallback == True
```

thì phải coi là thất bại.

---

## 12. Các runtime patch hiện tại

Các file patch quan trọng:

```text
chrome_reload_patch.py
cart_retry_patch.py
strict_cart_gate_patch.py
```

Thứ tự install hiện tại trong `app_with_api.py` cần giữ tương thích:

```text
install_chrome_reload()
install_cart_retry()
install_strict_cart_gate()
```

Nếu các import/install nằm trong một `try` chung thì lỗi patch trước có thể làm patch sau không được cài. Khi debug startup phải xem log runtime.

---

## 13. Scheduler / StudioPanel

File scheduler chính:

```text
studio_scheduler.py
```

Luồng tổng quát:

```text
pending
→ preparing
→ preflight
→ prepare video
→ prepare cart
→ verify cart
→ start LIVE
→ running
→ stop/finish
```

Các logic quan trọng của StudioPanel nằm ở:

```text
studio_panel.py
```

Điểm cần đọc:

```text
tick()
poll_cart()
cart_ready()
cart_failed()
```

`poll_cart()` chạy trước scheduler decision.

Một edge case cần kiểm tra sau: core cũ có xử lý manual LIVE/hand-live riêng. Strict cart gate có thể ảnh hưởng luồng đó. Ưu tiên hiện tại vẫn là không bao giờ tự LIVE khi giỏ bán hàng chưa đúng.

---

## 14. Cài trên máy mới

### Phần mềm cần có

```text
Git
Python 64-bit
Node.js
Google Chrome
TikTok LIVE Studio
WSL2 + Ubuntu
OmniRoute
NBL LIVE source
```

### Clone source

```powershell
cd C:\Users\<WINDOWS_USER>\Desktop
git clone -b openclaw-local-api https://github.com/doangiakhanh7777-star/LIVE-NBL.git 4.0.2
cd 4.0.2
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python bootstrap.py
```

### requirements.txt hiện tại

```text
PySide6-Essentials==6.12.0
PySide6-Addons==6.12.0
obsws-python==1.8.0
websockets>=15,<17
```

### Cài Ubuntu WSL

PowerShell Administrator:

```powershell
wsl --install -d Ubuntu
```

Không cần tải Ubuntu Desktop ISO.

---

## 15. OpenClaw trên máy mới

Ubuntu:

```bash
openclaw gateway run
```

Kiểm tra:

```bash
openclaw health
openclaw mcp doctor nbl-live --probe
```

---

## 16. Local API token trên máy mới

Mỗi máy dùng token riêng. Không copy token từ máy cũ.

NBL LIVE sẽ tự tạo token ở:

```text
C:\Users\<WINDOWS_USER>\AppData\Local\NBL_LIVE_2\local_api_token.txt
```

Trong WSL:

```bash
export NBL_API_TOKEN_FILE="/mnt/c/Users/<WINDOWS_USER>/AppData/Local/NBL_LIVE_2/local_api_token.txt"
```

---

## 17. Startup mỗi lần bật PC

Thứ tự vận hành hiện tại:

```text
1. Chrome
2. TikTok Shop LIVE dashboard
3. TikTok LIVE Studio
4. NBL LIVE
5. OmniRoute
6. Ubuntu / OpenClaw Gateway
7. Telegram test /kiemtra
```

NBL LIVE có thể chạy:

```powershell
cd C:\Users\<WINDOWS_USER>\Desktop\4.0.2
python bootstrap.py
```

OpenClaw:

```bash
openclaw gateway run
```

Telegram test:

```text
/kiemtra
```

---

## 18. Update source bằng Git

Đã từng gặp `git pull` bị chặn vì local file `CHROME_NBL_LIVE/background.js` đã sửa.

Cách an toàn:

```bash
git stash push -m "backup-background-truoc-update" -- CHROME_NBL_LIVE/background.js
git pull
git log -1 --oneline
```

Không chạy `git stash pop` mù quáng nếu source mới đã sửa cùng file. Phải xem diff trước.

Không dùng `git reset --hard` trừ khi người dùng xác nhận chấp nhận mất toàn bộ thay đổi local.

---

## 19. Sau khi pull có thay đổi Chrome Extension

Phải làm:

```text
chrome://extensions
→ NBL LIVE
→ Reload
```

Sau đó reload TikTok Shop LIVE product dashboard.

Nếu không làm bước này, background.js cũ có thể không hiểu action mới như `reload_dashboard`.

---

## 20. Kiểm tra pipeline

Windows:

```powershell
Invoke-RestMethod http://127.0.0.1:8766/health
```

Ubuntu:

```bash
openclaw mcp doctor nbl-live --probe
```

Mong muốn:

```text
nbl-live: ok
```

Telegram:

```text
/kiemtra
```

Nếu nhận được lịch/trạng thái thì pipeline đã thông.

---

## 21. OpenClaw / AI rate limit

Đã từng gặp lỗi model miễn phí:

```text
429
credentials cooling down
```

và:

```text
Context overflow
```

Cần hiểu:

- Tạo nhiều agent không làm tăng quota model.
- Nhiều agent dùng chung model free có thể làm rate limit nhanh hơn.
- Agent separation giúp tách context, không giúp tăng quota.
- Direct Telegram command nên được ưu tiên cho tác vụ cơ bản để không tốn AI quota.

Các lệnh hữu ích:

```bash
openclaw models status
openclaw models list
openclaw models fallbacks list
```

---

## 22. Agent topology từng định hướng

```text
coordinator-nbl-giam-doc
   ├── nbl-review
   ├── nbl-scheduler
   └── nbl-monitor
```

Vai trò:

```text
coordinator-nbl-giam-doc → tổng điều phối
nbl-review               → kiểm tra / validate
nbl-scheduler            → tạo/hủy lịch
nbl-monitor              → read-only trạng thái
```

---

## 23. Quy tắc cart tuyệt đối

```text
SALES LIVE:
NO VERIFIED CART
= NO LIVE
```

Cụ thể:

```text
Không đọc được cart → không LIVE
Cart count = 0 → không LIVE
Add cart lỗi → không LIVE
Reload lỗi → không LIVE
Cart là fallback / cart cũ → không LIVE
Bundle chưa verify đúng lịch → không LIVE
```

---

## 24. Test strict cart gate cần làm

### Test A — cart success

```text
Tạo lịch sales trong tương lai
→ bundle add thành công
→ cart_check > 0
→ prepared_for đúng bundle
→ được phép LIVE
```

### Test B — cart add fail

```text
Tạo lịch sales
→ cố tình để bundle không add được
→ retry/reload có thể chạy
→ cuối cùng vẫn fail
→ TUYỆT ĐỐI KHÔNG START LIVE
```

### Test C — có cart cũ

```text
Dashboard đang còn sản phẩm cũ
→ bundle mới add fail
→ cart_check thấy > 0
→ vẫn KHÔNG được LIVE
```

### Test D — unreadable cart

```text
cart_check không đọc được
count = -1
→ không verified
→ không LIVE
```

---

## 25. CAPTCHA

Dự án có thể:

- phát hiện CAPTCHA
- báo Telegram
- dừng automation an toàn
- có màn mô phỏng CAPTCHA để test UI

Không tích hợp bypass CAPTCHA hoặc cơ chế vượt biện pháp bảo vệ nền tảng.

---

## 26. Multi-PC

Khuyến nghị:

```text
NBL PC 1 → Telegram Bot 1
NBL PC 2 → Telegram Bot 2
NBL PC 3 → Telegram Bot 3
```

Nhắn bot nào → điều khiển máy đó.

---

## 27. File/module cần đọc trước khi sửa

AI tiếp quản nên đọc ít nhất:

```text
bootstrap.py
app_with_api.py
local_api.py
nbl_mcp_server.py
studio_panel.py
studio_scheduler.py
chrome_reload_patch.py
cart_retry_patch.py
strict_cart_gate_patch.py
CHROME_NBL_LIVE/background.js
CHROME_NBL_LIVE/content.js
LOCAL_API.md
requirements.txt
```

---

## 28. Debug checklist

Nếu Telegram không điều khiển được:

```text
1. NBL LIVE có mở không?
2. /health có trả ok không?
3. OpenClaw Gateway có chạy không?
4. MCP nbl-live có probe ok không?
5. Telegram bot có kết nối đúng Gateway không?
6. Chrome extension có bật không?
7. TikTok Shop dashboard có mở không?
8. TikTok LIVE Studio có đúng nick không?
9. OmniRoute có cần cho luồng này không?
10. Nếu là direct command thì kiểm tra plugin direct command.
```

Nếu giỏ không add được:

```text
1. Chrome extension có Reload sau update chưa?
2. background.js có bản reload_dashboard chưa?
3. dashboard có đúng tab TikTok Shop LIVE không?
4. ChromeBridge có connected không?
5. cart_retry_patch có install không?
6. strict_cart_gate_patch có install không?
7. Studio probe có báo live=False không?
8. Nếu live=True thì không reload cart.
9. Sau reload content script có reconnect không?
10. prepared_for có đúng bundle_index không?
```

---

## 29. Nguyên tắc sửa bug

```text
Đọc source
→ xác định nguyên nhân thật
→ patch tối thiểu
→ test
→ commit vào openclaw-local-api
→ pull trên máy Windows
→ reload extension nếu cần
→ restart app nếu không đang LIVE
→ test Local API
→ test MCP
→ test Telegram
```

Không restart NBL LIVE/TikTok LIVE Studio giữa một phiên LIVE đang chạy nếu chưa có lý do an toàn rõ ràng.

---

## 30. Reset app config

Dữ liệu app nằm trong:

```text
%LOCALAPPDATA%\NBL_LIVE_2
```

Nếu cần reset toàn bộ:

```text
đóng app
→ đổi tên NBL_LIVE_2 thành NBL_LIVE_2_BACKUP
→ mở lại app
```

Không nên xóa ngay vì có thể cần lấy lại config.

Reset này sẽ làm Local API token mới được sinh.

---

## 31. Handoff instruction cho AI tiếp quản

Nếu bạn là Claude / ChatGPT / Codex đang đọc file này:

1. Đọc toàn bộ file.
2. Đọc source thật của branch `openclaw-local-api`.
3. Không làm lại project từ đầu.
4. Không merge `main`.
5. Không đổi kiến trúc nếu chưa cần.
6. Ưu tiên giữ hệ thống hiện tại hoạt động.
7. Nếu sửa cart/start LIVE: giữ strict gate, tuyệt đối không cho sales LIVE start với cart cũ/fallback/unverified.
8. Nếu sửa Telegram: giữ direct command không cần AI cho tác vụ cơ bản.
9. Nếu sửa multi-PC: ưu tiên 1 bot = 1 PC.
10. Nếu chỉnh source: commit rõ ràng trên `openclaw-local-api`.

---

## 32. Prompt gợi ý khi đưa tài liệu này cho Claude

```text
Đây là file bàn giao toàn bộ dự án NBL LIVE đang được phát triển trước đó.

Hãy đọc toàn bộ file NBL_LIVE_HANDOFF.md trước.

Sau đó đọc source thật trong repository:
doangiakhanh7777-star/LIVE-NBL

Branch:
openclaw-local-api

Không làm lại từ đầu.
Không merge main.
Không thay đổi kiến trúc nếu chưa cần.
Không bỏ các patch an toàn hiện có.

Quy tắc quan trọng nhất:
Sales LIVE tuyệt đối không được bắt đầu nếu bộ sản phẩm của lịch đó chưa được chuẩn bị và xác nhận thành công.

Trước khi sửa bất cứ thứ gì, hãy:
1. đọc source thật
2. mô tả luồng hiện tại
3. chỉ ra nguyên nhân lỗi
4. đề xuất patch tối thiểu
5. sau đó mới sửa code
```

---

## 33. Trạng thái hiện tại — tóm tắt nhanh

```text
Repo:
doangiakhanh7777-star/LIVE-NBL

Branch:
openclaw-local-api

NBL Local API:
port 8766

OmniRoute:
port 20128

ChromeBridge:
17869–17871

Telegram direct:
/kiemtra
/huylich JOB_ID
/dunglive JOB_ID

MCP:
nbl-live

Strict rule:
NO VERIFIED CART = NO SALES LIVE

Quan trọng:
Reload Chrome Extension sau khi update background.js.
Không merge main.
Không copy secret/token giữa máy.
```

---

## END

Nếu tài liệu này khác source thật, **source thật trên branch `openclaw-local-api` là nguồn ưu tiên**, nhưng phải kiểm tra lịch sử commit trước khi thay đổi hành vi đã chốt.
