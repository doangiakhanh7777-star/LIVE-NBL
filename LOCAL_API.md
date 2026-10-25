# NBL LIVE Local API

Nhánh này thêm API cục bộ để OpenClaw/Telegram điều khiển lịch LIVE của NBL LIVE.

## Địa chỉ mặc định

- `http://0.0.0.0:8766`
- Health: `GET /health`
- Các endpoint `/api/*` yêu cầu Bearer token.

Token được tự sinh ở:

`%LOCALAPPDATA%\NBL_LIVE_2\local_api_token.txt`

Không đưa token lên GitHub hoặc chat công khai.

## Endpoint

- `GET /health`
- `GET /api/accounts`
- `GET /api/schedules`
- `GET /api/live/status`
- `POST /api/schedules`
- `POST /api/schedules/<JOB_ID>/cancel`
- `POST /api/schedules/<JOB_ID>/stop`
- `POST /api/schedules/<JOB_ID>/cart/retry`
- `DELETE /api/schedules/<JOB_ID>`

## Tạo lịch

Ví dụ JSON:

```json
{
  "account_number": 2,
  "start": "2026-10-24T20:00:00+07:00",
  "end": "2026-10-24T23:00:00+07:00",
  "bundle_index": 1,
  "no_sales": false,
  "allow_overlap": false
}
```

API dùng `studio_scheduler.add_job()` hiện có nên vẫn kiểm tra giờ tương lai, độ dài tối thiểu, lịch cùng nick chồng giờ, playlist và kết nối LIVE Studio.

## Tải lại giỏ và thử lại

NBL có hai lớp bảo vệ:

1. Khi thêm giỏ thất bại thật ở lần 1 hoặc 2, NBL yêu cầu reload **tab TikTok Shop LIVE product dashboard** rồi thử lại sau khoảng 10 giây. Logic thêm giỏ gốc vẫn giới hạn tối đa 3 lần.
2. Telegram/OpenClaw có tool `nbl_retry_cart` để người dùng chủ động yêu cầu reload + thử lại cho một lịch cụ thể.

`nbl_retry_cart` chỉ nhận `JOB_ID` chính xác và chỉ chạy trước khi LIVE. Nếu NBL chưa xác nhận nick đang không LIVE, API từ chối reload và yêu cầu kiểm tra Studio trước.

Ví dụ API:

```powershell
Invoke-RestMethod -Method Post `
  http://127.0.0.1:8766/api/schedules/<JOB_ID>/cart/retry `
  -Headers $headers `
  -ContentType 'application/json' `
  -Body '{}'
```

Lệnh này **không F5 TikTok LIVE Studio**. Nó chỉ reload trang sản phẩm TikTok Shop đã ghép với NBL.

## Sau khi cập nhật source

```powershell
cd C:\Users\ADMIN\Desktop\4.0.2
git pull
```

Sau đó:

1. Nếu đang LIVE, chờ phiên kết thúc trước khi cập nhật/restart app.
2. Mở `chrome://extensions`.
3. Tìm tiện ích NBL LIVE và bấm **Reload**.
4. Tải lại tab `https://shop.tiktok.com/streamer/live/product/dashboard` một lần nếu Chrome chưa tự tải lại.
5. Mở lại NBL LIVE.
6. Trong Ubuntu kiểm tra MCP:

```bash
openclaw mcp doctor nbl-live --probe
```

## Test trên Windows PowerShell

```powershell
$token = Get-Content "$env:LOCALAPPDATA\NBL_LIVE_2\local_api_token.txt"
$headers = @{ Authorization = "Bearer $token" }

Invoke-RestMethod http://127.0.0.1:8766/health
Invoke-RestMethod http://127.0.0.1:8766/api/accounts -Headers $headers
Invoke-RestMethod http://127.0.0.1:8766/api/schedules -Headers $headers
```

Health của bản này trả API `1.1`.

## Test từ WSL/OpenClaw

```bash
WINHOST=$(ip route | awk '/default/ {print $3; exit}')
TOKEN=$(cat /mnt/c/Users/ADMIN/AppData/Local/NBL_LIVE_2/local_api_token.txt)

curl "http://$WINHOST:8766/health"
curl -H "Authorization: Bearer $TOKEN" "http://$WINHOST:8766/api/accounts"
```

Nếu Windows gọi được nhưng WSL không gọi được, kiểm tra Windows Firewall cho cổng 8766 và chỉ cho phép phạm vi WSL cần thiết.

## Câu lệnh Telegram mẫu

```text
Kiểm tra lịch của nick số 2 giakhanhdoxe. Nếu lịch chưa LIVE và giỏ đang lỗi, dùng nbl_retry_cart cho đúng ID lịch đó. Không reload nếu nick đang LIVE. Sau khi yêu cầu thử lại, đọc lại trạng thái lịch cho tao.
```
