@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Cap nhat NBL LIVE 4.1
echo Cap nhat NBL LIVE len 4.1. Dong NBL LIVE va tat ca cua so NBL VIDEO truoc.
echo Neu khong tu tim thay thu muc NBL, keo tha THU MUC cai NBL (co app.py) vao file nay.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0cap_nhat.ps1" -Source "%~dp0." -Target "%~1"
if errorlevel 1 (
 echo Cap nhat chua thanh cong. Xem ly do phia tren. Khong mo app khi chua xac nhan khoi phuc.
 pause
 exit /b 1
)
echo.
echo XONG. Doc HUONG_DAN_4.1.txt: con 3 buoc (Chrome tai lai tien ich, Chrome dan ma 1 lan, lich LIVE chon bo so may).
pause
