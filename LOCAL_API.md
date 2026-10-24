# NBL LIVE Local API

Nhánh này thêm API cục bộ để OpenClaw/Telegram điều khiển lịch LIVE của NBL LIVE mà không thay đổi ChromeBridge.

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

## Test trên Windows PowerShell

```powershell
$token = Get-Content "$env:LOCALAPPDATA\NBL_LIVE_2\local_api_token.txt"
$headers = @{ Authorization = "Bearer $token" }

Invoke-RestMethod http://127.0.0.1:8766/health
Invoke-RestMethod http://127.0.0.1:8766/api/accounts -Headers $headers
Invoke-RestMethod http://127.0.0.1:8766/api/schedules -Headers $headers
```

## Test từ WSL/OpenClaw

```bash
WINHOST=$(ip route | awk '/default/ {print $3; exit}')
TOKEN=$(cat /mnt/c/Users/ADMIN/AppData/Local/NBL_LIVE_2/local_api_token.txt)

curl "http://$WINHOST:8766/health"
curl -H "Authorization: Bearer $TOKEN" "http://$WINHOST:8766/api/accounts"
```

Nếu Windows gọi được nhưng WSL không gọi được, kiểm tra Windows Firewall cho cổng 8766 và chỉ cho phép phạm vi WSL cần thiết.
