param([ValidateSet('list','point')][string]$Action='list')
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding($false)
trap {[Console]::Error.WriteLine($_.Exception.Message);exit 1}
Add-Type @'
using System;using System.Text;using System.Collections.Generic;using System.Runtime.InteropServices;
public static class NblWindows {
 public delegate bool EnumProc(IntPtr h,IntPtr p);
 [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc f,IntPtr p);
 [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
 [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h,out uint pid);
 [DllImport("user32.dll",CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h,StringBuilder s,int n);
 [DllImport("user32.dll")] public static extern bool GetCursorPos(out POINT p);
 [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(POINT p);
 [DllImport("user32.dll")] public static extern IntPtr GetAncestor(IntPtr h,uint flag);
 [StructLayout(LayoutKind.Sequential)] public struct POINT {public int X,Y;}
 [StructLayout(LayoutKind.Sequential)] public struct RECT {public int Left,Top,Right,Bottom;}
 [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h,out RECT r);
 public static IntPtr[] All(){var result=new List<IntPtr>();EnumWindows((h,p)=>{if(IsWindowVisible(h))result.Add(h);return true;},IntPtr.Zero);return result.ToArray();}
 public static string Title(IntPtr h){var s=new StringBuilder(2048);GetWindowText(h,s,s.Capacity);return s.ToString();}
}
'@
function Read-Window([IntPtr]$h){
 $ownerId=[uint32]0;$null=[NblWindows]::GetWindowThreadProcessId($h,[ref]$ownerId)
 $p=Get-Process -Id $ownerId -ErrorAction SilentlyContinue
 if(-not $p -or -not $p.Path){return}
 $exe=[IO.Path]::GetFileName($p.Path)
 if($exe -match '^(chrome|msedge|firefox|brave|opera|browser|coccoc|msedgewebview2)\.exe$'){return}
 if($exe -notmatch '(tiktok.*(live|studio)|live[ ._-]*studio)'){return}
 $title=[NblWindows]::Title($h)
 if(-not $title -or $title -notmatch 'live|studio'){return}
 $r=New-Object NblWindows+RECT;$null=[NblWindows]::GetWindowRect($h,[ref]$r)
 return @{pid=[string]$ownerId;windowTitle=$title;exePath=$p.Path;windowHandle=[string]$h.ToInt64();width=[int]($r.Right-$r.Left);height=[int]($r.Bottom-$r.Top)}
}
if($Action -eq 'point'){
 Start-Sleep -Seconds 4
 $pt=New-Object NblWindows+POINT;$null=[NblWindows]::GetCursorPos([ref]$pt)
 $h=[NblWindows]::GetAncestor([NblWindows]::WindowFromPoint($pt),2)
 $result=Read-Window $h
 if(-not $result){throw 'Không nhận được cửa sổ TikTok LIVE Studio dưới chuột. Đưa chuột vào phần chính của Studio, không phải Chrome hoặc NBL LIVE.'}
 $result|ConvertTo-Json -Compress;exit
}
$results=@();foreach($h in [NblWindows]::All()){try{$r=Read-Window $h;if($r){$results+=$r}}catch{}}
ConvertTo-Json -InputObject @($results) -Compress
