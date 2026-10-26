param([string]$Target='')
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)

function BaoLoi([string]$m){ throw $m }
function HopLe([string]$p){
  if(-not $p){ return $false }
  try {
    return (Test-Path -LiteralPath (Join-Path $p 'app.py')) -and (Test-Path -LiteralPath (Join-Path $p 'runtime\python.exe'))
  } catch { return $false }
}
function ThemThuMuc([System.Collections.Generic.List[string]]$list,[string]$p){
  if(-not $p){ return }
  try { $p=[IO.Path]::GetFullPath($p).TrimEnd('\') } catch { return }
  if((HopLe $p) -and -not $list.Contains($p)){ $list.Add($p) }
}

$ungVien=[System.Collections.Generic.List[string]]::new()
if(HopLe $Target){ ThemThuMuc $ungVien $Target }
foreach($p in @(
  "$env:USERPROFILE\Desktop\NBL_LIVE",
  "$env:LOCALAPPDATA\Programs\NBL_LIVE",
  "$env:LOCALAPPDATA\NBL_LIVE",
  "$env:ProgramFiles\NBL_LIVE",
  "${env:ProgramFiles(x86)}\NBL_LIVE"
)){ ThemThuMuc $ungVien $p }

try {
  $ws=New-Object -ComObject WScript.Shell
  $shortcutRoots=@(
    [Environment]::GetFolderPath('Desktop'),
    "$env:PUBLIC\Desktop",
    [Environment]::GetFolderPath('StartMenu'),
    "$env:ProgramData\Microsoft\Windows\Start Menu"
  ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
  foreach($root in $shortcutRoots){
    Get-ChildItem -LiteralPath $root -Filter '*.lnk' -File -Recurse -ErrorAction SilentlyContinue | Where-Object { $_.Name -match 'NBL' } | ForEach-Object {
      try {
        $sc=$ws.CreateShortcut($_.FullName)
        $tp=$sc.TargetPath
        if($tp){
          $dir=Split-Path -Parent $tp
          ThemThuMuc $ungVien $dir
          if($dir){ ThemThuMuc $ungVien (Split-Path -Parent $dir) }
        }
        if($sc.WorkingDirectory){ ThemThuMuc $ungVien $sc.WorkingDirectory }
      } catch {}
    }
  }
} catch {}

foreach($key in @(
  'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\NBL_LIVE_4.0.2',
  'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\NBL_LIVE_4.0.2',
  'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\NBL_LIVE_4.0.2',
  'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\NBL_LIVE',
  'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\NBL_LIVE'
)){
  try { ThemThuMuc $ungVien ((Get-ItemProperty -LiteralPath $key -ErrorAction Stop).InstallLocation.Trim('"')) } catch {}
}

try {
  Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe' OR Name='NBL_LIVE.exe'" | ForEach-Object {
    if($_.ExecutablePath){
      $dir=Split-Path -Parent $_.ExecutablePath
      ThemThuMuc $ungVien $dir
      ThemThuMuc $ungVien (Split-Path -Parent $dir)
    }
  }
} catch {}

if($ungVien.Count -gt 0){ $Target=$ungVien[0] }
if(-not (HopLe $Target)){
  try {
    Add-Type -AssemblyName System.Windows.Forms
    $dlg=New-Object System.Windows.Forms.FolderBrowserDialog
    $dlg.Description='Chọn thư mục cài NBL LIVE (thư mục có app.py và thư mục runtime)'
    $dlg.ShowNewFolderButton=$false
    if($dlg.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK -and (HopLe $dlg.SelectedPath)){
      $Target=$dlg.SelectedPath
    }
  } catch {}
}
if(-not (HopLe $Target)){ BaoLoi 'Không tìm thấy thư mục cài NBL LIVE thật. Thư mục đúng phải có app.py và runtime\python.exe.' }
$Target=(Resolve-Path -LiteralPath $Target).Path
Write-Host ('Đã tìm thấy NBL LIVE tại: '+$Target)

$prefix=$Target.TrimEnd('\')+'\'
$busy=@(Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe' OR Name='NBL_LIVE.exe'" | Where-Object {
  $_.ExecutablePath -and $_.ExecutablePath.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)
})
if($busy.Count){ BaoLoi 'NBL LIVE đang mở. Đóng NBL LIVE và các cửa sổ NBL VIDEO, sau đó chạy lại file cài này.' }

$stamp=Get-Date -Format 'yyyyMMdd_HHmmss'
$backup=Join-Path $Target ("_sao_luu\api_telegram_"+$stamp)
New-Item -ItemType Directory -Path $backup -Force | Out-Null

$branch='openclaw-local-api'
$base='https://raw.githubusercontent.com/doangiakhanh7777-star/LIVE-NBL/'+$branch+'/'
$files=@('bootstrap.py','app_with_api.py','local_api.py','chrome_reload_patch.py','cart_retry_patch.py','strict_cart_gate_patch.py')
foreach($name in $files){
  $dest=Join-Path $Target $name
  if(Test-Path -LiteralPath $dest){ Copy-Item -LiteralPath $dest -Destination (Join-Path $backup $name) -Force }
  $tmp=Join-Path $env:TEMP ('nbl_'+[guid]::NewGuid().ToString('N')+'_'+$name)
  Invoke-WebRequest -UseBasicParsing -Uri ($base+$name) -OutFile $tmp
  if((Get-Item -LiteralPath $tmp).Length -lt 20){ BaoLoi ('Tải file bị lỗi: '+$name) }
  Move-Item -LiteralPath $tmp -Destination $dest -Force
}

$appPath=Join-Path $Target 'app.py'
Copy-Item -LiteralPath $appPath -Destination (Join-Path $backup 'app.py') -Force
$appText=[IO.File]::ReadAllText($appPath,[Text.Encoding]::UTF8)
$marker='# NBL Telegram/OpenClaw Local API integrated'
if(-not $appText.Contains($marker)){
  $old='    window=Console();window.show();sys.exit(app.exec())'
  if(-not $appText.Contains($old)){ BaoLoi 'Không tìm thấy vị trí ghép API trong app.py. Chưa thay đổi app.' }
  $new=@'
    # NBL Telegram/OpenClaw Local API integrated
    try:
        from chrome_reload_patch import install as install_chrome_reload
        install_chrome_reload()
        from cart_retry_patch import install as install_cart_retry
        install_cart_retry()
        from strict_cart_gate_patch import install as install_strict_cart_gate
        install_strict_cart_gate()
    except Exception as exc:
        print('NBL runtime patch khong tai duoc:', str(exc)[:300])
    window=Console()
    local_api=None
    try:
        from local_api import LocalAPI
        local_api=LocalAPI(window)
        app.aboutToQuit.connect(local_api.close)
    except Exception as exc:
        window.log('Local API khong mo duoc: '+str(exc)[:500])
    window.show();sys.exit(app.exec())
'@
  $appText=$appText.Replace($old,$new.TrimEnd("`r","`n"))
  [IO.File]::WriteAllText($appPath,$appText,[Text.UTF8Encoding]::new($false))
}

$py=Join-Path $Target 'runtime\python.exe'
& $py -m py_compile (Join-Path $Target 'app.py') (Join-Path $Target 'local_api.py') (Join-Path $Target 'app_with_api.py') (Join-Path $Target 'chrome_reload_patch.py') (Join-Path $Target 'cart_retry_patch.py') (Join-Path $Target 'strict_cart_gate_patch.py')
if($LASTEXITCODE -ne 0){
  Copy-Item -LiteralPath (Join-Path $backup 'app.py') -Destination $appPath -Force
  BaoLoi 'Kiểm tra file bị lỗi. Đã khôi phục app.py cũ.'
}

# Tạo launcher ẩn: icon NBL LIVE sẽ chạy bootstrap.py bằng runtime của chính app.
$pythonw=Join-Path $Target 'runtime\pythonw.exe'
if(-not (Test-Path -LiteralPath $pythonw)){ $pythonw=$py }
$bootstrap=Join-Path $Target 'bootstrap.py'
$wrapper=Join-Path $Target 'MO_NBL_LIVE_TELEGRAM.vbs'
$escPy=$pythonw.Replace('"','""')
$escBoot=$bootstrap.Replace('"','""')
$escDir=$Target.Replace('"','""')
$vbs="Set sh = CreateObject(`"WScript.Shell`")`r`nsh.CurrentDirectory = `"$escDir`"`r`nsh.Run `"`"`"$escPy`"`" `"`"$escBoot`"`"`", 0, False`r`n"
[IO.File]::WriteAllText($wrapper,$vbs,[Text.Encoding]::ASCII)

$ws=New-Object -ComObject WScript.Shell
$desktop=[Environment]::GetFolderPath('Desktop')
$desktopLink=Join-Path $desktop 'NBL LIVE.lnk'
$sc=$ws.CreateShortcut($desktopLink)
$sc.TargetPath=Join-Path $env:SystemRoot 'System32\wscript.exe'
$sc.Arguments='"'+$wrapper+'"'
$sc.WorkingDirectory=$Target
$sc.Description='Mở NBL LIVE có điều khiển Telegram'
$iconExe=Join-Path $Target 'NBL_LIVE.exe'
$iconIco=Join-Path $Target 'assets\logo_38.ico'
if(Test-Path -LiteralPath $iconExe){ $sc.IconLocation=$iconExe+',0' }
elseif(Test-Path -LiteralPath $iconIco){ $sc.IconLocation=$iconIco }
$sc.Save()

# Đồng bộ các shortcut NBL LIVE cũ trong Start Menu/Desktop về launcher mới.
$shortcutRoots=@(
  [Environment]::GetFolderPath('Desktop'),
  "$env:PUBLIC\Desktop",
  [Environment]::GetFolderPath('StartMenu'),
  "$env:ProgramData\Microsoft\Windows\Start Menu"
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
foreach($root in $shortcutRoots){
  Get-ChildItem -LiteralPath $root -Filter '*.lnk' -File -Recurse -ErrorAction SilentlyContinue | Where-Object { $_.BaseName -match '^NBL LIVE' } | ForEach-Object {
    try {
      $x=$ws.CreateShortcut($_.FullName)
      $x.TargetPath=Join-Path $env:SystemRoot 'System32\wscript.exe'
      $x.Arguments='"'+$wrapper+'"'
      $x.WorkingDirectory=$Target
      $x.Description='Mở NBL LIVE có điều khiển Telegram'
      if(Test-Path -LiteralPath $iconExe){ $x.IconLocation=$iconExe+',0' }
      elseif(Test-Path -LiteralPath $iconIco){ $x.IconLocation=$iconIco }
      $x.Save()
    } catch {}
  }
}

Write-Host ''
Write-Host '========================================='
Write-Host 'ĐÃ CẬP NHẬT ĐIỀU KHIỂN TELEGRAM'
Write-Host ('Thư mục NBL: '+$Target)
Write-Host ('Bản sao lưu : '+$backup)
Write-Host 'Đã sửa biểu tượng NBL LIVE trên Desktop để tự bật API.'
Write-Host 'Bây giờ mở NBL LIVE bằng biểu tượng NBL LIVE như bình thường.'
Write-Host 'Sau khi app mở, Telegram gửi /kiemtra.'
Write-Host '========================================='
