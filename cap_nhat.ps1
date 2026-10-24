param([Parameter(Mandatory=$true)][string]$Source,[string]$Target='')
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)
$backup=$null;$copyStarted=$false;$original=@();$newFiles=@()
try {
 $Source=(Resolve-Path -LiteralPath $Source).Path
 if(-not $Target){
  # 4.1: also the folder the 4.0.2 installer recorded in Windows (e.g. Desktop\4.0.2).
  $candidates=@()
  foreach($key in @('HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\NBL_LIVE_4.0.2','HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\NBL_LIVE_4.0.2','HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\NBL_LIVE_4.0.2')){
   try{$loc=(Get-ItemProperty -LiteralPath $key -ErrorAction Stop).InstallLocation;if($loc){$candidates+=$loc.Trim('"')}}catch{}
  }
  $candidates+=@("$env:USERPROFILE\Desktop\4.0.2","$env:LOCALAPPDATA\Programs\NBL_LIVE\4.0.2","$env:LOCALAPPDATA\Programs\NBL_LIVE","$env:ProgramFiles\NBL_LIVE","${env:ProgramFiles(x86)}\NBL_LIVE")
  $Target=$candidates|Where-Object {(Test-Path -LiteralPath (Join-Path $_ 'runtime\python.exe')) -and (Test-Path -LiteralPath (Join-Path $_ 'app.py'))}|Select-Object -First 1
 }
 if(-not $Target){throw 'Khong tim thay NBL LIVE. Keo tha thu muc cai NBL (thu muc co app.py) vao CAP_NHAT_4.1.bat.'}
 $Target=(Resolve-Path -LiteralPath $Target).Path
 if(-not (Test-Path -LiteralPath (Join-Path $Target 'app.py')) -or -not (Test-Path -LiteralPath (Join-Path $Target 'runtime\python.exe'))){throw 'Thu muc da chon thieu app.py hoac runtime\python.exe. Can ban NBL da cai dat.'}
 if($Target.TrimEnd('\') -eq $Source.TrimEnd('\')){throw 'Giai nen ban cap nhat vao thu muc rieng, khong de trung thu muc NBL dang cai.'}
 $prefix=$Target.TrimEnd('\')+'\'
 $busy=@(Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe' OR Name='NBL_LIVE.exe'"|Where-Object {$_.ExecutablePath -and $_.ExecutablePath.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)})
 if($busy.Count){throw 'Dong NBL LIVE va tat ca NBL VIDEO truoc khi cap nhat.'}
 $manifest=Get-Content -LiteralPath (Join-Path $Source 'SHA256.json') -Raw -Encoding UTF8|ConvertFrom-Json
 $files=@($manifest.PSObject.Properties)
 if(-not $files.Count){throw 'Goi cap nhat khong co danh sach kiem tra.'}
 foreach($entry in $files){
  $relative=$entry.Name.Replace('/','\')
  if([IO.Path]::IsPathRooted($relative) -or $relative.Split('\') -contains '..'){throw 'Duong dan trong goi cap nhat khong hop le.'}
  $file=Join-Path $Source $relative
  if(-not (Test-Path -LiteralPath $file -PathType Leaf) -or (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ne $entry.Value){throw ('Goi tai ve thieu hoac hong tep: '+$relative)}
 }
 # Parse every PowerShell file before modifying the installed application.
 foreach($entry in $files){
  if($entry.Name -like '*.ps1'){
   $tokens=$null;$parseErrors=$null
   $null=[System.Management.Automation.Language.Parser]::ParseFile((Join-Path $Source $entry.Name),[ref]$tokens,[ref]$parseErrors)
   if($parseErrors.Count){throw ('Loi cu phap PowerShell: '+$entry.Name+' '+($parseErrors.Message -join '; '))}
  }
 }
 $backup=Join-Path $Target ('_sao_luu\truoc_4.1_'+(Get-Date -Format 'yyyyMMdd_HHmmss')+'_'+[guid]::NewGuid().ToString('N').Substring(0,8))
 New-Item -ItemType Directory -Path $backup -Force|Out-Null
 # Complete and verify every backup before replacing the first application file.
 foreach($entry in $files){
  $relative=$entry.Name.Replace('/','\');$dest=Join-Path $Target $relative
  if(Test-Path -LiteralPath $dest -PathType Leaf){
   $saved=Join-Path $backup $relative;New-Item -ItemType Directory -Path (Split-Path $saved -Parent) -Force|Out-Null
   Copy-Item -LiteralPath $dest -Destination $saved -Force
   if((Get-FileHash -LiteralPath $dest).Hash -ne (Get-FileHash -LiteralPath $saved).Hash){throw ('Sao luu khong khop: '+$relative)}
   $original+= $relative
  }else{$newFiles+= $relative}
 }
 @{original=$original;newFiles=$newFiles;target=$Target}|ConvertTo-Json -Depth 5|Set-Content -LiteralPath (Join-Path $backup 'KHOI_PHUC.json') -Encoding UTF8
 $copyStarted=$true
 foreach($entry in $files){
  $relative=$entry.Name.Replace('/','\');$dest=Join-Path $Target $relative
  New-Item -ItemType Directory -Path (Split-Path $dest -Parent) -Force|Out-Null
  Copy-Item -LiteralPath (Join-Path $Source $relative) -Destination $dest -Force
  if((Get-FileHash -LiteralPath $dest -Algorithm SHA256).Hash -ne $entry.Value){throw ('Chep tep khong khop: '+$relative)}
 }
 & (Join-Path $Target 'runtime\python.exe') (Join-Path $Target 'kiem_tra_cai_dat.py')
 if($LASTEXITCODE -ne 0){throw 'Kiem tra thu vien hoac bo doc chu sau cap nhat chua dat.'}
 Write-Host ('DA CAP NHAT NBL LIVE 4.1. Ban cu: '+$backup)
 Write-Host ('Chrome: vao chrome://extensions, Tai lai tien ich tu thu muc '+(Join-Path $Target 'CHROME_NBL_LIVE')+', sau do tai lai trang LIVE.')
 Write-Host 'Neu tien ich cu duoc nap tu thu muc khac, Go tien ich cu va Tai tien ich da giai nen tu thu muc moi tren.'
 Write-Host 'Mo NBL LIVE bang shortcut cu. Thiet lap nick, lich va noi dung duoc giu lai.'
 exit 0
} catch {
 $reason=$_.Exception.Message
 if($copyStarted){
  try {
   foreach($relative in $original){Copy-Item -LiteralPath (Join-Path $backup $relative) -Destination (Join-Path $Target $relative) -Force}
   foreach($relative in $newFiles){$file=Join-Path $Target $relative;if(Test-Path -LiteralPath $file){Remove-Item -LiteralPath $file -Force}}
   foreach($relative in $original){if((Get-FileHash -LiteralPath (Join-Path $backup $relative)).Hash -ne (Get-FileHash -LiteralPath (Join-Path $Target $relative)).Hash){throw 'Kiem tra khoi phuc khong khop'}}
   Write-Host 'Cap nhat loi. DA KHOI PHUC va kiem tra ban truoc cap nhat.'
  } catch {Write-Host ('CHUA KHOI PHUC DAY DU. Khong mo NBL. Giu thu muc sao luu: '+$backup)}
 }
 Write-Host ('LOI: '+$reason)
 exit 1
}
