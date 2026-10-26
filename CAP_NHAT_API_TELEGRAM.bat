@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0CAP_NHAT_API_TELEGRAM.ps1"
if errorlevel 1 (
  echo.
  echo CAP NHAT API THAT BAI. XEM DONG LOI PHIA TREN.
  pause
  exit /b 1
)
echo.
echo XONG. MO NBL LIVE BANG ICON NHU BINH THUONG.
pause
