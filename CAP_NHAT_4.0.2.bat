@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Cap nhat NBL LIVE 4.0.2
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0cap_nhat.ps1" -Source "%~dp0." -Target "%~1"
if errorlevel 1 (
 echo Cap nhat chua thanh cong. Xem ly do phia tren. Khong mo app khi chua xac nhan khoi phuc.
 pause
 exit /b 1
)
pause
