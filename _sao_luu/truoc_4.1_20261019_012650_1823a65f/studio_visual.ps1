# Visual calibration is scoped to the selected, foreground native Studio window.
. (Join-Path $PSScriptRoot 'studio_geometry.ps1')
Add-Type -AssemblyName System.Drawing
Add-Type -ReferencedAssemblies @('System.Drawing','System') -TypeDefinition @'
using System;using System.Drawing;using System.Drawing.Imaging;using System.IO;using System.Runtime.InteropServices;
public static class NblVisual {
 [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left,Top,Right,Bottom; }
 [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h,out RECT r);
 [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(Point p);
 [DllImport("user32.dll")] public static extern IntPtr GetAncestor(IntPtr h,uint flags);
 [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
 [DllImport("user32.dll")] public static extern uint GetDpiForWindow(IntPtr h);
 public static string Capture(int x,int y,int w,int h){
  using(var b=new Bitmap(w,h)){using(var g=Graphics.FromImage(b))g.CopyFromScreen(x,y,0,0,new Size(w,h));using(var m=new MemoryStream()){b.Save(m,ImageFormat.Png);return Convert.ToBase64String(m.ToArray());}}
 }
 public static bool Match(string encoded,int x,int y){
  using(var m=new MemoryStream(Convert.FromBase64String(encoded)))using(var sample=new Bitmap(m))using(var screen=new Bitmap(sample.Width,sample.Height)){
   using(var g=Graphics.FromImage(screen))g.CopyFromScreen(x,y,0,0,screen.Size);
   long error=0,count=0;int dark=255,light=0;
   for(int yy=0;yy<sample.Height;yy+=2)for(int xx=0;xx<sample.Width;xx+=2){var a=sample.GetPixel(xx,yy);var b=screen.GetPixel(xx,yy);int v=(a.R+a.G+a.B)/3;dark=Math.Min(dark,v);light=Math.Max(light,v);error+=Math.Abs(a.R-b.R)+Math.Abs(a.G-b.G)+Math.Abs(a.B-b.B);count+=3;}
   return light-dark>=25&&count>0&&error<=count*7;
  }
 }
}
'@
function Test-StudioPoint([int]$x,[int]$y){
 # 4.0.3: Studio's own panels/popups (same process) count as Studio, not as a cover.
 $h=[NblVisual]::WindowFromPoint((New-Object Drawing.Point($x,$y)))
 if($h -eq [IntPtr]::Zero){return $false}
 $root=[NblVisual]::GetAncestor($h,2)
 if($root -eq $studioHandle -or [NblVisual]::GetAncestor($h,3) -eq $studioHandle){return $true}
 $owner=[uint32]0;$null=[NblInput]::GetWindowThreadProcessId($root,[ref]$owner)
 $studioPid=[uint32]0;$null=[NblInput]::GetWindowThreadProcessId($studioHandle,[ref]$studioPid)
 return ($owner -ne 0 -and $owner -eq $studioPid)
}
function Visual-Bounds {
 if([NblVisual]::IsIconic($studioHandle)){throw 'Mở cửa sổ Studio để đối chiếu ảnh; chưa bấm gì.'}
 $r=New-Object NblVisual+RECT
 if(-not [NblVisual]::GetWindowRect($studioHandle,[ref]$r)){throw 'Không đọc được khung cửa sổ Studio.'}
 return $r
}
function Capture-Visual([int]$x,[int]$y){
 if([NblInput]::GetForegroundWindow() -ne $studioHandle){throw 'Đưa cửa sổ Studio lên trước rồi chọn lại.'}
 if(-not (Test-StudioPoint $x $y)){throw 'Vị trí chọn bị cửa sổ khác che; không ghi nhận.'}
 $r=Visual-Bounds;$w=$r.Right-$r.Left;$h=$r.Bottom-$r.Top
 $tw=96;$th=28;$left=[Math]::Max($r.Left,[Math]::Min($x-$tw/2,$r.Right-$tw));$top=[Math]::Max($r.Top,[Math]::Min($y-$th/2,$r.Bottom-$th))
 if($w -lt $tw -or $h -lt $th){throw 'Cửa sổ Studio quá nhỏ.'}
 # 4.0.3: the mouse rests on the target while picking, so 4.0.2 saved the HOVER
 # look of the element; later checks (mouse elsewhere) never matched. Move the
 # pointer off Studio first, then require the area to stay identical for ~1.2 s
 # so live video, counters and animations cannot be saved as an anchor.
 $old=New-Object NblInput+POINT;$null=[NblInput]::GetCursorPos([ref]$old)
 try{
  $null=[NblInput]::SetCursorPos([int]($r.Left-40),[int]($r.Top-40))
  if([NblVisual]::GetAncestor([NblVisual]::WindowFromPoint((New-Object Drawing.Point(($r.Left-40),($r.Top-40)))),2) -eq $studioHandle){$null=[NblInput]::SetCursorPos([int]($r.Right+40),[int]($r.Bottom+40))}
  Start-Sleep -Milliseconds 450
  $encoded=[NblVisual]::Capture($left,$top,$tw,$th)
  foreach($i in 1..3){
   Start-Sleep -Milliseconds 400
   if(-not [NblVisual]::Match($encoded,$left,$top)){throw 'Vùng chọn đang thay đổi (khung video xem trước, số đếm hoặc hiệu ứng). Chọn chữ/biểu tượng cố định ngoài khung video, ví dụ ảnh đại diện nick ở góc trên bên phải.'}
  }
 }finally{$null=[NblInput]::SetCursorPos($old.X,$old.Y)}
 return (@{kind='visual';image=$encoded;x=($left-$r.Left);y=($top-$r.Top);width=$tw;height=$th;windowWidth=$w;windowHeight=$h;dpi=[NblVisual]::GetDpiForWindow($studioHandle);clickX=($x-$left);clickY=($y-$top)}|ConvertTo-Json -Compress)
}
function Resolve-Visual($d){
 $r=Visual-Bounds
 if(($r.Right-$r.Left) -ne $d.windowWidth -or ($r.Bottom-$r.Top) -ne $d.windowHeight -or [NblVisual]::GetDpiForWindow($studioHandle) -ne $d.dpi){throw 'Kích thước hoặc tỷ lệ màn hình Studio đã đổi. Chọn lại ảnh nút; chưa bấm gì.'}
 if([NblInput]::GetForegroundWindow() -ne $studioHandle){Permit-Input;$null=[NblInput]::SetForegroundWindow($studioHandle);Start-Sleep -Milliseconds 150}
 if([NblInput]::GetForegroundWindow() -ne $studioHandle){throw 'Chưa đưa được Studio lên trước để đối chiếu ảnh.'}
 $x=$r.Left+[int]$d.x;$y=$r.Top+[int]$d.y
 # All corners must belong to Studio, not an overlay or another application's window.
 $points=@(Get-NblImageCorners $x $y ([int]$d.width) ([int]$d.height))
 foreach($point in $points){
  $position=New-Object Drawing.Point($point.X,$point.Y)
  if(-not (Test-StudioPoint $point.X $point.Y)){throw 'Ảnh nút bị cửa sổ khác che; chưa bấm gì.'}
 }
 if(-not [NblVisual]::Match([string]$d.image,$x,$y)){return}
 $rect=New-Object Windows.Rect(($x+[int]$d.clickX-1),($y+[int]$d.clickY-1),2,2)
 $item=[pscustomobject]@{Visual=$true;VisualSpec=$d;Current=[pscustomobject]@{IsEnabled=$true;IsOffscreen=$false;BoundingRectangle=$rect;Name='Vị trí đã đối chiếu ảnh'}}
 $item|Add-Member ScriptMethod TryGetCurrentPattern {param($pattern,$result) return $false}
 return $item
}
