@echo off
chcp 65001 >nul
title Cài đặt điều khiển NBL LIVE bằng Telegram
echo.
echo ================================================
echo   CÀI ĐẶT ĐIỀU KHIỂN NBL LIVE BẰNG TELEGRAM
echo ================================================
echo.
echo Đang chuẩn bị bản cập nhật...
set "TMPPS=%TEMP%\NBL_CAI_TELEGRAM_%RANDOM%.ps1"
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -UseBasicParsing 'https://raw.githubusercontent.com/doangiakhanh7777-star/LIVE-NBL/openclaw-local-api/CAP_NHAT_API_TELEGRAM.ps1' -OutFile '%TMPPS%' } catch { Write-Host 'Không tải được bản cập nhật từ GitHub.'; exit 1 }"
if errorlevel 1 goto :loi
powershell -NoProfile -ExecutionPolicy Bypass -File "%TMPPS%"
set "RC=%ERRORLEVEL%"
del /q "%TMPPS%" >nul 2>&1
if not "%RC%"=="0" goto :loi
echo.
echo ================================================
echo   ĐÃ CÀI XONG
echo ================================================
echo.
echo Bây giờ mở NBL LIVE bằng biểu tượng như bình thường.
echo Sau đó vào Telegram và gửi: /kiemtra
echo.
pause
exit /b 0
:loi
echo.
echo ================================================
echo   CÀI ĐẶT KHÔNG THÀNH CÔNG
echo ================================================
echo Gửi ảnh cửa sổ này để kiểm tra lỗi.
echo.
pause
exit /b 1
