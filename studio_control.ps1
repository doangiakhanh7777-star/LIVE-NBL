param([string]$ConfigFile,[string]$Action,[double]$Deadline=0)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding($false)
trap {[Console]::Error.WriteLine($_.Exception.Message+' | '+$_.InvocationInfo.ScriptName+':'+$_.InvocationInfo.ScriptLineNumber);exit 1}
Add-Type -AssemblyName WindowsBase
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type @'
using System;using System.Runtime.InteropServices;
public static class NblInput {
 [DllImport("user32.dll")] public static extern bool SetProcessDpiAwarenessContext(IntPtr value);
 [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
 [DllImport("user32.dll")] public static extern bool IsWindow(IntPtr h);
 [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h,out uint pid);
 [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h,int cmd);
 [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
 [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
 [DllImport("user32.dll")] public static extern bool SetCursorPos(int x,int y);
 [DllImport("user32.dll")] public static extern bool GetCursorPos(out POINT p);
 [DllImport("user32.dll")] public static extern void mouse_event(uint f,uint x,uint y,uint d,UIntPtr e);
 [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X,Y; }
 [StructLayout(LayoutKind.Sequential)] struct KEYBDINPUT { public ushort vk,scan; public uint flags,time; public UIntPtr extra; }
 [StructLayout(LayoutKind.Sequential)] struct MOUSEINPUT { public int x,y;public uint data,flags,time;public UIntPtr extra; }
 [StructLayout(LayoutKind.Explicit)] struct UNION { [FieldOffset(0)] public KEYBDINPUT key; [FieldOffset(0)] public MOUSEINPUT mouse; }
 [StructLayout(LayoutKind.Sequential)] struct INPUT { public uint type;public UNION data; }
 [DllImport("user32.dll",SetLastError=true)] static extern uint SendInput(uint n,INPUT[] input,int size);
 public static void TypeUnicode(string text) {
  foreach(char ch in text) {
   INPUT[] inputs=new INPUT[2];inputs[0].type=inputs[1].type=1;
   inputs[0].data.key.scan=inputs[1].data.key.scan=ch;
   inputs[0].data.key.flags=4;inputs[1].data.key.flags=6;
   if(SendInput(2,inputs,Marshal.SizeOf(typeof(INPUT)))!=2) throw new Exception("Unicode input failed");
  }
 }
}
'@
try{$null=[NblInput]::SetProcessDpiAwarenessContext([IntPtr](-4))}catch{$null=[NblInput]::SetProcessDPIAware()}
. (Join-Path $PSScriptRoot 'studio_visual.ps1')
. (Join-Path $PSScriptRoot 'warning_filter.ps1')
. (Join-Path $PSScriptRoot 'studio_vision_client.ps1')
$c=Get-Content -LiteralPath $ConfigFile -Raw -Encoding UTF8 | ConvertFrom-Json
function Check-Deadline {if($c._controlGuard -and ((Get-Content -LiteralPath $c._controlGuard.path -Raw -Encoding UTF8).Trim() -ne $c._controlGuard.token)){throw 'NBL cancelled this control action'};if($Deadline -gt 0 -and [DateTimeOffset]::UtcNow.ToUnixTimeSeconds() -ge $Deadline){throw 'Action expired'}}
Check-Deadline
function Descriptor($e){
 $d=@{name=$e.Current.Name;automationId=$e.Current.AutomationId;controlType=$e.Current.ControlType.Id}
 # A LIVE clock changes every second. Keep its shape rather than the captured value.
 if($d.name -match '^\d{1,3}:\d{2}(:\d{2})?$'){$d.Remove('name');$d.namePattern='^\d{1,3}:\d{2}(:\d{2})?$'}
 return $d
}
function Find-Items([string]$spec,$scope=$root){
 if([string]::IsNullOrWhiteSpace($spec)){throw 'Missing calibrated element'}
 if($spec.Trim().StartsWith('{')){$d=$spec|ConvertFrom-Json}else{$d=[pscustomobject]@{name=$spec}}
 if($d.kind -eq 'visual'){return ,@(Resolve-Visual $d)}
 $conditions=New-Object 'System.Collections.Generic.List[System.Windows.Automation.Condition]'
 if($d.name){$conditions.Add((New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty,[string]$d.name)))}
 if($d.automationId){$conditions.Add((New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty,[string]$d.automationId)))}
 if($d.controlType){$conditions.Add((New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::LookupById([int]$d.controlType))))}
 if($conditions.Count -eq 0){throw 'Empty descriptor'}
 $cond=$conditions[0];if($conditions.Count -gt 1){$cond=New-Object System.Windows.Automation.AndCondition(,$conditions.ToArray())}
 $found=$scope.FindAll([System.Windows.Automation.TreeScope]::Descendants,$cond)
 if($d.namePattern){return ,@($found|Where-Object {$_.Current.Name -match $d.namePattern})}
 return ,$found
}
function Find-One([string]$spec,$scope=$root){$items=Find-Items $spec $scope;if($items.Count -ne 1){throw "Expected one calibrated element; found $($items.Count)"};return $items[0]}
# Re-resolve a restarted process only by exact EXE/title/account, never by order.
$p=Get-Process -Id ([int]$c.pid) -ErrorAction SilentlyContinue
$studioHandle=[IntPtr]::Zero
if($p){$studioHandle=if($c.windowHandle){[IntPtr]([long]$c.windowHandle)}else{$p.MainWindowHandle}}
$valid=$false
if($p -and $studioHandle -ne [IntPtr]::Zero -and [NblInput]::IsWindow($studioHandle)){
 $ownerId=[uint32]0;$null=[NblInput]::GetWindowThreadProcessId($studioHandle,[ref]$ownerId)
 $valid=($ownerId -eq $p.Id -and $p.Path -eq $c.exePath)
}
if(-not $valid){
 if($Action -in @('inspect','pick','probe')){throw 'Select the current Studio window first'}
 $candidates=@()
 foreach($candidate in (Get-Process|Where-Object {$_.MainWindowHandle -ne 0 -and $_.MainWindowTitle -eq $c.windowTitle})){
  try{
   if($candidate.Path -ne $c.exePath){continue}
   $candidateRoot=[System.Windows.Automation.AutomationElement]::FromHandle($candidate.MainWindowHandle)
   $null=Find-One $c.accountAnchor $candidateRoot;$candidates+=$candidate
  }catch{continue}
 }
 if($candidates.Count -ne 1){throw 'Cannot resolve exactly one Studio window for this account; reconnect'}
 $p=$candidates[0];$studioHandle=$p.MainWindowHandle
}
if($Action -eq 'probe'){@{windowFound=$true;pid=$p.Id;windowHandle=[string]$studioHandle.ToInt64()}|ConvertTo-Json -Compress;exit}
$root=[System.Windows.Automation.AutomationElement]::FromHandle($studioHandle)
function Present([string]$spec){$items=Find-Items $spec;if($items.Count -gt 1){throw 'Ambiguous LIVE state indicator'};return ($items.Count -eq 1)}
function Live-State([bool]$FreshAlerts=$false) {
 if($c.vision.enabled){
  Check-Deadline
  if(-not $c._visionRpc){throw 'OCR service lease missing; connect through NBL LIVE'}
  $state=Invoke-NblVisionProbe $c._visionRpc $FreshAlerts
  if(-not $state.confirmed){throw 'Image LIVE state not confirmed'}
  return [bool]$state.live
 }
 if(Present $c.liveIndicator){return $true}
 # Absence alone is not proof of being offline.
 if($c.startButton -and (Present $c.startButton)){return $false}
 if($c.summaryClose -and (Present $c.summaryClose)){return $false}
 $endLabels=@((Names $root)|Where-Object {$_ -match '^LIVE đã kết thúc$|^Buổi LIVE đã kết thúc$|^Phát trực tiếp đã kết thúc$|^LIVE ended$|^LIVE summary$'})
 if($endLabels.Count -gt 0){return $false}
 throw 'LIVE state unknown; no confirmed live/offline indicator'
}
function Permit-Input {
 if(-not $c.allowMouse){throw 'Studio mouse/keyboard actions paused'}
 if($c.mousePermissionFile -and (Get-Content -LiteralPath $c.mousePermissionFile -Raw).Trim() -ne '1'){throw 'Studio mouse/keyboard actions paused'}
}
function Invoke-Target($e){
 Check-Deadline
 if($c.vision.enabled -and $Action -in @('start','stop')){$null=Live-State $true};Check-Deadline
 if($e.Visual){$matches=@(Resolve-Visual $e.VisualSpec);if($matches.Count -ne 1){throw 'Ảnh nút đã thay đổi; chưa bấm gì.'};$e=$matches[0]}
 $null=Find-One $c.accountAnchor
 if(-not $e.Current.IsEnabled){throw 'Target disabled'}
 $pattern=$null
 if($e.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern,[ref]$pattern)){$pattern.Invoke();return}
 Permit-Input
 if([NblVisual]::IsIconic($studioHandle)){$null=[NblInput]::ShowWindow($studioHandle,9)};$null=[NblInput]::SetForegroundWindow($studioHandle);Start-Sleep -Milliseconds 150
 if([NblInput]::GetForegroundWindow() -ne $studioHandle){throw 'Cannot focus the correct Studio window'}
 $r=$e.Current.BoundingRectangle
 if($r.IsEmpty -or $r.Width -le 0 -or $r.Height -le 0){throw 'Invalid target bounds'}
 $old=New-Object NblInput+POINT;$null=[NblInput]::GetCursorPos([ref]$old)
 try{Permit-Input;$null=[NblInput]::SetCursorPos([int]($r.X+$r.Width/2),[int]($r.Y+$r.Height/2));Check-Deadline;[NblInput]::mouse_event(2,0,0,0,[UIntPtr]::Zero);[NblInput]::mouse_event(4,0,0,0,[UIntPtr]::Zero)}finally{$null=[NblInput]::SetCursorPos($old.X,$old.Y)}
}
function Names($scope){if($scope.Visual){throw 'Khung trò chuyện chỉ nhận bằng ảnh; chưa đọc được nội dung để xác nhận gửi/chào. Phần này chưa tự chạy.'};$all=$scope.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition);$names=@();for($i=0;$i -lt [Math]::Min($all.Count,2500);$i++){if($all.Item($i).Current.Name){$names+=$all.Item($i).Current.Name}};return $names}
function Warnings {return @(Get-NblWarningNames $root)}
if($Action -eq 'inspect'){
 $all=$root.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition);$controls=@()
 for($i=0;$i -lt [Math]::Min($all.Count,1500);$i++){$e=$all.Item($i);if($e.Current.Name -or $e.Current.AutomationId){$controls+=Descriptor $e}}
 @{pid=$p.Id;exePath=$p.Path;windowTitle=$p.MainWindowTitle;controls=$controls}|ConvertTo-Json -Depth 5 -Compress;exit
}
if($Action -eq 'pick'){
 Start-Sleep -Seconds 4
 if([NblVisual]::IsIconic($studioHandle)){$null=[NblInput]::ShowWindow($studioHandle,9)};$null=[NblInput]::SetForegroundWindow($studioHandle);Start-Sleep -Milliseconds 200
 $pt=New-Object NblInput+POINT;$null=[NblInput]::GetCursorPos([ref]$pt)
 $e=[System.Windows.Automation.AutomationElement]::FromPoint((New-Object System.Windows.Point($pt.X,$pt.Y)))
 $ancestor=$e;$inside=$false
 for($i=0;$i -lt 40 -and $ancestor;$i++){if($ancestor.Current.NativeWindowHandle -eq $studioHandle){$inside=$true;break};$ancestor=[System.Windows.Automation.TreeWalker]::ControlViewWalker.GetParent($ancestor)}
 if(-not $inside){throw 'Point at a control inside the selected Studio window'}
 # Icons and custom drawn leaves may have no useful name. Try a small number of
 # accessible ancestors, never guess the whole window or an arbitrary position.
 for($level=0;$level -lt 6 -and $e;$level++){
  $current=$e.Current;$type=$current.ControlType.Id
  if(($current.Name -or $current.AutomationId) -and $type -ne 50032 -and ($type -ne 50033 -or $c.payload.field -eq 'chatRegion')){
   try{$descriptor=Descriptor $e;$spec=$descriptor|ConvertTo-Json -Compress;$null=Find-One $spec;@{descriptor=$spec;name=$current.Name}|ConvertTo-Json -Compress;exit}catch{}
  }
  if($current.NativeWindowHandle -eq $studioHandle){break}
  $e=[System.Windows.Automation.TreeWalker]::ControlViewWalker.GetParent($e)
 }
 if($c.payload.visualFallback){$spec=Capture-Visual $pt.X $pt.Y;@{descriptor=$spec;name='Ảnh vị trí đã chọn · giữ nguyên kích thước Studio'}|ConvertTo-Json -Compress;exit}
 throw 'Studio không cung cấp tên nút. Bật chọn bằng ảnh rồi chọn lại.'
}
$null=Find-One $c.accountAnchor
$alerts=Warnings
$live=if($Action -eq 'collapse_chat'){$true}else{Live-State}
if($Action -eq 'status'){@{live=$live;warnings=@($alerts);confirmed=$true;pid=$p.Id}|ConvertTo-Json -Depth 4 -Compress;exit}
if($alerts.Count -gt 0 -and $Action -ne 'stop'){throw ('Studio warning: '+($alerts -join '; '))}
if($Action -eq 'collapse_chat'){
 Add-Type -AssemblyName System.Drawing
 Add-Type -ReferencedAssemblies @('System.Drawing','System') -TypeDefinition @'
using System;using System.Collections.Generic;using System.Drawing;using System.Drawing.Imaging;using System.Runtime.InteropServices;
public static class NblChatWindow {
 public delegate bool EnumProc(IntPtr h,IntPtr arg);
 [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc cb,IntPtr arg);
 [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h,out uint pid);
 [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
 [DllImport("user32.dll")] static extern bool IsIconic(IntPtr h);
 [DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr h,out RECT r);
 [StructLayout(LayoutKind.Sequential)] struct RECT {public int Left,Top,Right,Bottom;}
 public static IntPtr[] Windows(uint pid,IntPtr main){var list=new List<IntPtr>();EnumWindows((h,arg)=>{uint found;GetWindowThreadProcessId(h,out found);if(found==pid&&h!=main&&IsWindowVisible(h))list.Add(h);return true;},IntPtr.Zero);return list.ToArray();}
 public static bool Visible(IntPtr handle){return IsWindowVisible(handle)&&!IsIconic(handle);}
 public static Point[] FindButton(IntPtr handle,string file){return FindButton(handle,file,0,0,0,0);}
 public static Point[] FindButton(IntPtr handle,string file,int left,int top,int regionWidth,int regionHeight){
  RECT r;if(!GetWindowRect(handle,out r))return new Point[0];if(regionWidth>0&&regionHeight>0){int right=Math.Min(r.Right,left+regionWidth),bottom=Math.Min(r.Bottom,top+regionHeight);r.Left=Math.Max(r.Left,left);r.Top=Math.Max(r.Top,top);r.Right=right;r.Bottom=bottom;}int width=r.Right-r.Left,height=r.Bottom-r.Top;
  if(width<4||height<4||width>5000||height>5000)return new Point[0];var hits=new List<Point>();var timer=System.Diagnostics.Stopwatch.StartNew();
  using(var screenshot=new Bitmap(width,height)){using(var g=Graphics.FromImage(screenshot)){g.CopyFromScreen(r.Left,r.Top,0,0,new Size(width,height));}
   using(var original=new Bitmap(file)){if(original.Width>300||original.Height>300||original.Width<8||original.Height<8)throw new Exception("Button sample must be cropped to 8-300 pixels");
    foreach(double scale in new double[]{1.0,0.8,1.25}){int tw=(int)(original.Width*scale),th=(int)(original.Height*scale);if(tw>width||th>height)continue;
     using(var template=new Bitmap(original,new Size(tw,th))){
      for(int y=0;y<=height-th;y+=2)for(int x=0;x<=width-tw;x+=2){if(timer.ElapsedMilliseconds>1200)throw new TimeoutException("Chat image scan incomplete; nothing clicked");int error=0,count=0;
       for(int sy=1;sy<6;sy++)for(int sx=1;sx<6;sx++){var a=template.GetPixel(sx*tw/6,sy*th/6);if(a.A<200)continue;var b=screenshot.GetPixel(x+sx*tw/6,y+sy*th/6);error+=Math.Abs(a.R-b.R)+Math.Abs(a.G-b.G)+Math.Abs(a.B-b.B);count+=3;}
       if(count<30||error>count*12)continue;
       // Confirm the entire button, not just the coarse search grid.
       long fullError=0,fullCount=0;int step=Math.Max(1,Math.Min(tw,th)/25);
       for(int yy=0;yy<th;yy+=step)for(int xx=0;xx<tw;xx+=step){var aa=template.GetPixel(xx,yy);if(aa.A<200)continue;var bb=screenshot.GetPixel(x+xx,y+yy);fullError+=Math.Abs(aa.R-bb.R)+Math.Abs(aa.G-bb.G)+Math.Abs(aa.B-bb.B);fullCount+=3;}
       if(fullCount<100||fullError>fullCount*10)continue;bool near=false;foreach(var hit in hits)if(Math.Abs(hit.X-(r.Left+x+tw/2))<tw&&Math.Abs(hit.Y-(r.Top+y+th/2))<th){near=true;break;}
       if(!near)hits.Add(new Point(r.Left+x+tw/2,r.Top+y+th/2));if(hits.Count>1)return hits.ToArray();
      }
     }
    }
   }
  }return hits.ToArray();
 }
}
'@
 # This helper deliberately never treats the MAIN window's generic Minimize as chat.
 function Chat-Region {
  if(-not $c.chatRegion){return $null}
  try{$items=Find-Items $c.chatRegion;if($items.Count -eq 1 -and -not $items[0].Current.IsOffscreen){return $items[0]}}catch{}
  return $null
 }
 function Chat-Collapsed($handle,[bool]$main){
  if($main){try{$items=Find-Items $c.chatRegion;if($items.Count -eq 0){return $true};if($items.Count -eq 1){return $items[0].Current.IsOffscreen};return $false}catch{return $false}}
  return (-not [NblChatWindow]::Visible($handle))
 }
 function Collapse-Buttons($scope,[bool]$generic){
  $buttons=$scope.FindAll([System.Windows.Automation.TreeScope]::Descendants,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::Button)))
  $matches=@();for($i=0;$i -lt $buttons.Count;$i++){$button=$buttons.Item($i);$name=$button.Current.Name
   if($button.Current.IsOffscreen){continue}
   if($name -match '^(Thu nhỏ trò chuyện|Thu gọn trò chuyện|Ẩn trò chuyện|Collapse chat|Minimize chat|Hide chat)$' -or ($generic -and $name -match '^(Thu nhỏ|Thu gọn|Minimize|Collapse)$')){$matches+=$button}
  };return ,$matches
 }
 $until=(Get-Date).AddSeconds(6);$hasSample=$c.collapseImage -and (Test-Path -LiteralPath $c.collapseImage)
 do{
  Check-Deadline;$null=Find-One $c.accountAnchor;$region=Chat-Region;$candidates=@();$handles=@([NblChatWindow]::Windows([uint32]$p.Id,$studioHandle))
  # Integrated sidebar: use only chat-specific captions, or generic captions INSIDE chat.
  if($region){
   $specific=Collapse-Buttons $root $false;$inside=Collapse-Buttons $region $true
   $unique=@{};foreach($button in @($specific)+@($inside)){$key=$button.GetRuntimeId() -join '.';$unique[$key]=$button}
   foreach($button in $unique.Values){$candidates+=@{button=$button;handle=$studioHandle;main=$true}}
  }
  # Auxiliary windows need a chat identity for the accessible-button path.
  foreach($handle in $handles){
   try{$popup=[System.Windows.Automation.AutomationElement]::FromHandle($handle);$labels=@(Names $popup)}catch{continue}
   if(($popup.Current.Name+' '+($labels -join ' ')) -notmatch '(?i)trò chuyện|chat'){continue}
   foreach($button in (Collapse-Buttons $popup $true)){$candidates+=@{button=$button;handle=$handle;main=$false}}
  }
  if($candidates.Count -eq 1){
   $candidate=$candidates[0];$pattern=$null
   if($candidate.button.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern,[ref]$pattern)){
    Check-Deadline;$null=Find-One $c.accountAnchor;$pattern.Invoke()
    $verifyUntil=(Get-Date).AddSeconds(2)
    do{Start-Sleep -Milliseconds 200;if(Chat-Collapsed $candidate.handle $candidate.main){@{collapsed=$true;confirmed=$true;method='accessible-chat-button'}|ConvertTo-Json -Compress;exit}}while((Get-Date) -lt $verifyUntil)
    @{collapsed=$false;reason='Đã bấm thu trò chuyện nhưng chưa xác nhận được; không tự bấm lại'}|ConvertTo-Json -Compress;exit
   }
  }
  if($candidates.Count -gt 1){break}
  if($hasSample){
   # Image-only auxiliary windows are allowed; uniqueness is checked across ALL candidates.
   # Scan at most four windows. An incomplete scan never authorizes a click.
   $targets=@();foreach($handle in $handles){$targets+=@{handle=$handle;main=$false;region=$null}}
   if($region){$targets+=@{handle=$studioHandle;main=$true;region=$region.Current.BoundingRectangle}}
   if($targets.Count -gt 4){break}
   $hits=@();$complete=$true
   foreach($target in $targets){
    Check-Deadline;Permit-Input;$null=[NblInput]::SetForegroundWindow($target.handle);Start-Sleep -Milliseconds 100
    if([NblInput]::GetForegroundWindow() -ne $target.handle){$complete=$false;break}
    if($target.main){$r=$target.region;$points=[NblChatWindow]::FindButton($target.handle,[string]$c.collapseImage,[int]$r.X,[int]$r.Y,[int]$r.Width,[int]$r.Height)}else{$points=[NblChatWindow]::FindButton($target.handle,[string]$c.collapseImage)}
    foreach($point in $points){$hits+=@{target=$target;point=$point}}
   }
   if($complete -and $hits.Count -eq 1){
    $hit=$hits[0];$target=$hit.target;Check-Deadline;Permit-Input;$null=[NblInput]::SetForegroundWindow($target.handle);Start-Sleep -Milliseconds 100
    # Re-locate after the focus changes. Never use a previously cached point.
    if($target.main){$current=Chat-Region;if(-not $current){break};$r=$current.Current.BoundingRectangle;$points=[NblChatWindow]::FindButton($target.handle,[string]$c.collapseImage,[int]$r.X,[int]$r.Y,[int]$r.Width,[int]$r.Height)}else{$points=[NblChatWindow]::FindButton($target.handle,[string]$c.collapseImage)}
    if($points.Count -ne 1 -or [NblInput]::GetForegroundWindow() -ne $target.handle){break}
    $old=New-Object NblInput+POINT;$null=[NblInput]::GetCursorPos([ref]$old)
    try{Check-Deadline;Permit-Input;$null=Find-One $c.accountAnchor;$under=[System.Windows.Automation.AutomationElement]::FromPoint((New-Object System.Windows.Point($points[0].X,$points[0].Y)));if($under.Current.ProcessId -ne $p.Id){throw 'Chat button is covered by another app; nothing clicked'};$null=[NblInput]::SetCursorPos($points[0].X,$points[0].Y);[NblInput]::mouse_event(2,0,0,0,[UIntPtr]::Zero);[NblInput]::mouse_event(4,0,0,0,[UIntPtr]::Zero)}finally{$null=[NblInput]::SetCursorPos($old.X,$old.Y)}
    $verifyUntil=(Get-Date).AddSeconds(2)
    do{Start-Sleep -Milliseconds 200;if(Chat-Collapsed $target.handle $target.main){@{collapsed=$true;confirmed=$true;method='saved-image'}|ConvertTo-Json -Compress;exit}}while((Get-Date) -lt $verifyUntil)
    @{collapsed=$false;reason='Đã bấm mẫu nút thu trò chuyện nhưng chưa xác nhận được; không tự bấm lại'}|ConvertTo-Json -Compress;exit
   }
  }
  Start-Sleep -Milliseconds 400
 }while((Get-Date) -lt $until)
 @{collapsed=$false;reason='Chưa thấy đúng nút thu cửa sổ trò chuyện; các mục khác tiếp tục'}|ConvertTo-Json -Compress;exit
}
if($Action -eq 'chat_check'){
 $region=Find-One $c.chatRegion;$input=Find-One $c.chatInput;$send=Find-One $c.chatSend
 if($region.Visual -or $input.Visual){throw 'Chưa đọc được nội dung ô nhập/khung chat bằng ảnh. Nhắn mẫu chưa sẵn sàng; các mục khác vẫn chạy.'}
 $value=$null;$tp=$null
 if(-not $input.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern,[ref]$value) -and -not $input.TryGetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern,[ref]$tp)){throw 'Ô nhập chưa cho đọc bản nháp. Chọn lại ô nhập; không gửi tin.'}
 if($value -and $value.Current.IsReadOnly){throw 'Ô nhập đang chỉ đọc; chưa gửi được tin.'}
 if(-not $send.Current.IsEnabled){throw 'Nút gửi hiện bị khóa; kiểm tra khi đang LIVE.'}
 $null=Names $region
 @{readable=$true;confirmed=$true;live=$live}|ConvertTo-Json -Compress;exit
}
if($Action -eq 'send'){
 if(-not $live){throw 'Not LIVE; message cancelled'}
 $text=[string]$c.payload.text;if(-not $text.Trim() -or $text.Length -gt 100){throw 'Message must contain 1-100 characters'}
 $region=Find-One $c.chatRegion;$input=Find-One $c.chatInput;$send=Find-One $c.chatSend
 if($input.Visual){throw 'Ô nhập tin nhắn chỉ nhận bằng ảnh; chưa đọc được bản nháp nên chưa tự gửi. Cần bật khả năng truy cập của Studio hoặc dùng ô nhập đọc được.'}
 $value=$null;$hasValue=$input.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern,[ref]$value)
 function Draft {
  if($hasValue){return $value.Current.Value}
  $tp=$null;if($input.TryGetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern,[ref]$tp)){return $tp.DocumentRange.GetText(-1)}
  throw 'Cannot read Studio draft; select the actual edit box. Nothing sent'
 }
 if((Draft).Trim() -or ($hasValue -and $value.Current.IsReadOnly)){throw 'Chat draft is occupied or read-only; message not sent'}
 $before=@((Names $region)|Where-Object {$_ -eq $text}).Count
 Check-Deadline
 if($hasValue){$value.SetValue($text)}else{
  Permit-Input;if([NblVisual]::IsIconic($studioHandle)){$null=[NblInput]::ShowWindow($studioHandle,9)};$null=[NblInput]::SetForegroundWindow($studioHandle);$input.SetFocus();Start-Sleep -Milliseconds 150
  if([NblInput]::GetForegroundWindow() -ne $studioHandle){throw 'Studio focus not confirmed'}
  $focused=[System.Windows.Automation.AutomationElement]::FocusedElement
  if(($focused.GetRuntimeId() -join '.') -ne ($input.GetRuntimeId() -join '.')){throw 'Chat input focus not confirmed'}
  if((Draft).Trim()){throw 'Draft changed'};Check-Deadline;Permit-Input;[NblInput]::TypeUnicode($text)
 }
 $clicked=$false
 try{
  if((Draft) -ne $text){throw 'Chat draft changed; message cancelled'}
  $null=Find-One $c.accountAnchor;if(-not (Live-State)){throw 'LIVE ended'}
  Invoke-Target $send;$clicked=$true
  $until=(Get-Date).AddSeconds(8)
  do{Start-Sleep -Milliseconds 400;if(@((Names $region)|Where-Object {$_ -eq $text}).Count -gt $before){@{sent=$true;confirmed=$true}|ConvertTo-Json -Compress;exit}}while((Get-Date) -lt $until)
  throw 'Message result uncertain; inspect chat manually. Automatic retry disabled'
 }finally{if(-not $clicked -and $hasValue -and (Draft) -eq $text){$value.SetValue('')}}
}
function Greetings {
 throw 'Chào khách: bổ sung sau, chạy độc lập với nhắn mẫu và lịch LIVE.'
 $region=Find-One $c.chatRegion
 $condition=New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::Button)
 $buttons=$region.FindAll([System.Windows.Automation.TreeScope]::Descendants,$condition);$rows=@()
 for($i=0;$i -lt $buttons.Count;$i++){
  $button=$buttons.Item($i);if($button.Current.Name -notmatch '^(👋\s*)?(Chào|Say hi|Greet)$' -or $button.Current.IsOffscreen){continue}
  $row=[System.Windows.Automation.TreeWalker]::ControlViewWalker.GetParent($button)
  for($depth=0;$depth -lt 3 -and $row;$depth++){
   $labels=@((Names $row)|Where-Object {$_ -notmatch '^(👋\s*)?(Chào|Say hi|Greet)$'}|Select-Object -Unique)
   $raw=$labels -join ' | '
   if($raw -match 'đã tham gia|joined'){
    $candidate=$raw -replace 'đã tham gia|joined','';$candidate=$candidate.Trim(' ','|')
    if($candidate -and $candidate.Length -lt 180){$rows+=@{key=$candidate;button=$button};break}
   }
   $row=[System.Windows.Automation.TreeWalker]::ControlViewWalker.GetParent($row)
  }
 }
 return $rows
}
if($Action -eq 'greet_scan'){
 if(-not $live){@{live=$false;viewers=@()}|ConvertTo-Json -Compress;exit}
 $rows=@(Greetings);$unique=@($rows|Group-Object key|Where-Object {$_.Count -eq 1}|ForEach-Object {$_.Name})
 @{live=$true;viewers=@($unique)}|ConvertTo-Json -Depth 4 -Compress;exit
}
if($Action -eq 'greet'){
 if(-not $live){throw 'LIVE ended'}
 $rows=@((Greetings)|Where-Object {$_.key -eq $c.payload.key})
 if($rows.Count -eq 0){@{gone=$true}|ConvertTo-Json -Compress;exit}
 if($rows.Count -ne 1){throw 'Viewer row ambiguous'}
 Invoke-Target $rows[0].button
 $until=(Get-Date).AddSeconds(4)
 do{Start-Sleep -Milliseconds 300;if(@((Greetings)|Where-Object {$_.key -eq $c.payload.key}).Count -eq 0){@{greeted=$true}|ConvertTo-Json -Compress;exit}}while((Get-Date) -lt $until)
 throw 'Greeting result uncertain; automatic retry disabled'
}
if($Action -notin @('start','stop')){throw 'Unsupported action'}
if(($Action -eq 'start' -and $live) -or ($Action -eq 'stop' -and -not $live)){@{live=$live;already=$true;confirmed=$true}|ConvertTo-Json -Compress;exit}
if($Action -eq 'stop' -and $c.stopMenu){Invoke-Target (Find-One $c.stopMenu);Start-Sleep -Milliseconds 350}
$target=if($Action -eq 'start'){$c.startButton}else{$c.stopButton};Invoke-Target (Find-One $target)
$confirm=if($Action -eq 'start'){$c.startConfirm}else{$c.stopConfirm}
# A first-login setup confirmation is OPTIONAL on later broadcasts.
$confirmClicked=$false
$until=(Get-Date).AddSeconds(3)
if($confirm){
 do{
  Check-Deadline;$matches=Find-Items $confirm
  if($matches.Count -gt 1){throw 'More than one confirmation button; nothing clicked'}
  if($matches.Count -eq 1){Invoke-Target $matches[0];$confirmClicked=$true;break}
  try{if((Live-State) -eq ($Action -eq 'start')){break}}catch{}
  Start-Sleep -Milliseconds 250
 }while((Get-Date) -lt $until)
}
$until=(Get-Date).AddSeconds(10)
do{Check-Deadline;Start-Sleep -Milliseconds 500;$present=$null;try{$present=Live-State}catch{continue};if(($Action -eq 'start' -and $present) -or ($Action -eq 'stop' -and -not $present)){$cleanupWarning='';if($Action -eq 'stop' -and $c.summaryClose){try{$close=Find-Items $c.summaryClose;if($close.Count -eq 1){Invoke-Target $close[0]}}catch{$cleanupWarning='LIVE đã kết thúc nhưng chưa đóng được bảng tổng kết'}};@{live=$present;confirmed=$true;cleanupWarning=$cleanupWarning}|ConvertTo-Json -Compress;exit}}while((Get-Date) -lt $until)
throw 'Studio state uncertain; inspect manually. Automatic retry disabled'
