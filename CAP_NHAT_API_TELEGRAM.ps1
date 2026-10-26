param([string]$Target='')
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)

function Fail([string]$m){ throw $m }

if(-not $Target){
  $candidates=@(
    "$env:USERPROFILE\Desktop\NBL_LIVE",
    "$env:LOCALAPPDATA\Programs\NBL_LIVE",
    "$env:ProgramFiles\NBL_LIVE"
  )
  $Target=$candidates | Where-Object {
    (Test-Path -LiteralPath (Join-Path $_ 'app.py')) -and
    (Test-Path -LiteralPath (Join-Path $_ 'runtime\python.exe'))
  } | Select-Object -First 1
}
if(-not $Target){ Fail 'Khong tim thay thu muc NBL_LIVE. Dat script trong thu muc cai dat hoac truyen -Target.' }
$Target=(Resolve-Path -LiteralPath $Target).Path
$prefix=$Target.TrimEnd('\')+'\'

$busy=@(Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe' OR Name='NBL_LIVE.exe'" | Where-Object {
  $_.ExecutablePath -and $_.ExecutablePath.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)
})
if($busy.Count){ Fail 'Dong NBL LIVE va NBL VIDEO truoc khi cap nhat API Telegram.' }

$stamp=Get-Date -Format 'yyyyMMdd_HHmmss'
$backup=Join-Path $Target ("_sao_luu\api_telegram_"+$stamp)
New-Item -ItemType Directory -Path $backup -Force | Out-Null

$branch='openclaw-local-api'
$base='https://raw.githubusercontent.com/doangiakhanh7777-star/LIVE-NBL/'+$branch+'/'
$files=@(
  'bootstrap.py',
  'app_with_api.py',
  'local_api.py',
  'chrome_reload_patch.py',
  'cart_retry_patch.py',
  'strict_cart_gate_patch.py'
)

foreach($name in $files){
  $dest=Join-Path $Target $name
  if(Test-Path -LiteralPath $dest){ Copy-Item -LiteralPath $dest -Destination (Join-Path $backup $name) -Force }
  $tmp=Join-Path $env:TEMP ('nbl_'+[guid]::NewGuid().ToString('N')+'_'+$name)
  Invoke-WebRequest -UseBasicParsing -Uri ($base+$name) -OutFile $tmp
  if((Get-Item -LiteralPath $tmp).Length -lt 20){ Fail ('Tai file loi: '+$name) }
  Move-Item -LiteralPath $tmp -Destination $dest -Force
}

$appPath=Join-Path $Target 'app.py'
Copy-Item -LiteralPath $appPath -Destination (Join-Path $backup 'app.py') -Force
$appText=[IO.File]::ReadAllText($appPath,[Text.Encoding]::UTF8)
$marker='# NBL Telegram/OpenClaw Local API integrated'
if(-not $appText.Contains($marker)){
  $old='    window=Console();window.show();sys.exit(app.exec())'
  if(-not $appText.Contains($old)){ Fail 'Khong tim thay diem chen API trong app.py. Khong sua file.' }
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
  Fail 'Kiem tra cu phap loi. Da khoi phuc app.py cu.'
}

Write-Host ''
Write-Host '========================================='
Write-Host 'DA CAP NHAT API TELEGRAM / OPENCLAW'
Write-Host ('Thu muc: '+$Target)
Write-Host ('Backup : '+$backup)
Write-Host 'Mo NBL LIVE bang icon nhu binh thuong.'
Write-Host 'Sau khi app mo, kiem tra: http://127.0.0.1:8766/health'
Write-Host '========================================='
