@echo off
cd /d "%~dp0"
if exist "runtime\python.exe" (
 "runtime\python.exe" bootstrap.py
) else (
 ".venv\Scripts\python.exe" bootstrap.py
)
if errorlevel 1 pause
