@echo off
chcp 65001 >nul
powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -File "%~dp0kiem_tra_canh_bao_windows.ps1"
if errorlevel 1 echo CHUA DAT. Giu noi dung loi tren man hinh de kiem tra.
pause
