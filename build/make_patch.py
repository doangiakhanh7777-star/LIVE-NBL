"""Make NBL_VA_<ver>.zip with CAI_BAN_VA.bat from a source tree (cumulative from 4.1.11)."""
import shutil, sys, zipfile
from pathlib import Path
src, out, ver, title = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4]
notes = sys.argv[5].split('|') if len(sys.argv) > 5 else []
FILES = 'app.py chrome_bridge.py diagnostics.py hold_button.py kiem_tra_cai_dat.py notifications.py pin_script_editor.py studio_panel.py studio_vision.py studio_vision_panel.py theme.py studio_cdp.py studio_scheduler.py studio_interactions.py'.split()
EXT = 'background.js content.js manifest.json popup.html'.split()
ASSETS = 'down.svg up.svg'.split()
TESTS = sorted(p.name for p in (src / 'tests').iterdir() if p.is_file() and p.suffix in ('.py', '.js'))
d = out / ('NBL_VA_' + ver)
if d.exists(): shutil.rmtree(d)
for sub in ('files/CHROME_NBL_LIVE', 'files/tests', 'files/assets'): (d / sub).mkdir(parents=True)
for f in FILES: shutil.copy2(src / f, d / 'files' / f)
for f in EXT: shutil.copy2(src / 'CHROME_NBL_LIVE' / f, d / 'files/CHROME_NBL_LIVE' / f)
for f in ASSETS: shutil.copy2(src / 'assets' / f, d / 'files/assets' / f)
for f in TESTS: shutil.copy2(src / 'tests' / f, d / 'files/tests' / f)
shutil.copy2(Path(__file__).with_name('_ma_kiem.py'), d / 'files/_ma_kiem.py')
kiem = ' '.join(FILES + ['CHROME_NBL_LIVE\\' + f for f in EXT] + ['assets\\' + f for f in ASSETS] + ['tests\\' + f for f in TESTS])
bat = r'''@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Ban va @VER@ - NBL LIVE (@TITLE@)
set "SRC=%~dp0files"
set "TARGET=%~1"
if not defined TARGET for /f "tokens=2,*" %%A in ('reg query "HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall\NBL_LIVE" /v InstallLocation 2^>nul ^| find /I "InstallLocation"') do set "TARGET=%%B"
for %%D in ("%ProgramFiles%\NBL_LIVE" "%ProgramFiles(x86)%\NBL_LIVE" "%LOCALAPPDATA%\Programs\NBL_LIVE") do if not defined TARGET if exist "%%~D\pin_scripts.py" set "TARGET=%%~D"
if defined TARGET if "%TARGET:~-1%"=="\" set "TARGET=%TARGET:~0,-1%"
echo Thu muc NBL LIVE: %TARGET%
if not exist "%TARGET%\app.py" goto notfound
if not exist "%TARGET%\pin_scripts.py" (
  echo Thu muc nay chua phai NBL LIVE 4.1.11 tro len. Cai bo cai NBL_LIVE_Setup truoc, roi chay lai file nay.
  pause & exit /b 1
)
powershell -NoProfile -Command "$p=$env:TARGET.TrimEnd('\')+'\'; if(@(Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='pythonw.exe' OR Name='NBL_LIVE.exe'\" | Where-Object {$_.ExecutablePath -and $_.ExecutablePath.StartsWith($p,[StringComparison]::OrdinalIgnoreCase)}).Count){exit 1}" || (
  echo Dang mo NBL LIVE hoac NBL VIDEO. Dong NBL LIVE va moi cua so NBL VIDEO roi chay lai file nay.
  pause & exit /b 1
)
set "FILES=@FILES@"
set "EXT=@EXT@"
set "ASSETS=@ASSETS@"
set "TESTS=@TESTS@"
set "BACKUP=%TARGET%\_sao_luu\truoc_va_@VER@_%RANDOM%%RANDOM%"
mkdir "%BACKUP%\CHROME_NBL_LIVE" "%BACKUP%\assets" || (echo Khong tao duoc thu muc sao luu. Chay bang quyen Administrator. & pause & exit /b 1)
copy /Y "%TARGET%\SETUP_FILES.json" "%BACKUP%\" >nul
for %%F in (%FILES%) do if exist "%TARGET%\%%F" copy /Y "%TARGET%\%%F" "%BACKUP%\" >nul || goto fail
for %%F in (%EXT%) do copy /Y "%TARGET%\CHROME_NBL_LIVE\%%F" "%BACKUP%\CHROME_NBL_LIVE\" >nul || goto fail
for %%F in (%ASSETS%) do if exist "%TARGET%\assets\%%F" copy /Y "%TARGET%\assets\%%F" "%BACKUP%\assets\" >nul
for %%F in (%FILES%) do copy /Y "%SRC%\%%F" "%TARGET%\" >nul || goto restore
for %%F in (%EXT%) do copy /Y "%SRC%\CHROME_NBL_LIVE\%%F" "%TARGET%\CHROME_NBL_LIVE\" >nul || goto restore
for %%F in (%ASSETS%) do copy /Y "%SRC%\assets\%%F" "%TARGET%\assets\" >nul || goto restore
if exist "%TARGET%\tests" for %%F in (%TESTS%) do copy /Y "%SRC%\tests\%%F" "%TARGET%\tests\" >nul
if exist "%TARGET%\tests\chrome4112.test.js" del /F /Q "%TARGET%\tests\chrome4112.test.js"
set "PY=%TARGET%\runtime\python.exe"
if exist "%PY%" "%PY%" -I "%SRC%\_ma_kiem.py" "%TARGET%" @KIEM@ tests\chrome4112.test.js
echo.
echo DA VA XONG @VER@. Ban cu luu tai: %BACKUP%
echo Mo lai NBL LIVE: thanh tieu de phai ghi TOOL NBL LIVE @VER@.
@NOTES@
pause & exit /b 0
:restore
for %%F in (%FILES% SETUP_FILES.json) do if exist "%BACKUP%\%%F" copy /Y "%BACKUP%\%%F" "%TARGET%\" >nul
for %%F in (%EXT%) do if exist "%BACKUP%\CHROME_NBL_LIVE\%%F" copy /Y "%BACKUP%\CHROME_NBL_LIVE\%%F" "%TARGET%\CHROME_NBL_LIVE\" >nul
for %%F in (%ASSETS%) do if exist "%BACKUP%\assets\%%F" copy /Y "%BACKUP%\assets\%%F" "%TARGET%\assets\" >nul
:fail
echo Chep file loi; da tra lai ban cu. Chay file nay bang quyen Administrator (chuot phai ^> Run as administrator).
pause & exit /b 1
:notfound
echo Khong tim thay NBL LIVE 4.1.11 tro len tai: %TARGET%
echo Cach lam: keo tha THU MUC cai NBL (vi du C:\Program Files\NBL_LIVE) vao file CAI_BAN_VA.bat nay.
pause & exit /b 1
'''
rep = {'@VER@': ver, '@TITLE@': title, '@FILES@': ' '.join(FILES), '@EXT@': ' '.join(EXT), '@ASSETS@': ' '.join(ASSETS), '@TESTS@': ' '.join(TESTS), '@KIEM@': kiem,
       '@NOTES@': '\n'.join('echo ' + n.replace('>', '^>').replace('&', '^&') for n in notes)}
for k, v in rep.items(): bat = bat.replace(k, v)
(d / 'CAI_BAN_VA.bat').write_text(bat, encoding='utf-8', newline='\r\n')
z = out / ('NBL_VA_' + ver + '.zip')
with zipfile.ZipFile(z, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as f:
    for p in d.rglob('*'): f.write(p, p.relative_to(out))
print(z, z.stat().st_size)
