# Native Windows UIA fixture: no TikTok, mouse, keyboard, credentials or broadcast.
$ErrorActionPreference='Stop'
Add-Type -AssemblyName PresentationFramework
Add-Type -AssemblyName UIAutomationClient
$window=[Windows.Window]::new();$window.Title='NBL - kiem tra canh bao';$window.Width=480;$window.Height=250
$panel=[Windows.Controls.StackPanel]::new();$window.Content=$panel
$heading=[Windows.Controls.TextBlock]::new();$heading.Text='Thông báo: Vi phạm của video LIVE';$panel.Children.Add($heading)|Out-Null
$countdown=[Windows.Controls.TextBlock]::new();$countdown.Text='còn 30 giây';$panel.Children.Add($countdown)|Out-Null
$chat=[Windows.Controls.ListBox]::new();$chat.Items.Add('Khách: Vi phạm của video LIVE')|Out-Null;$panel.Children.Add($chat)|Out-Null
$window.Show()
function Scan-Fixture {
 $psi=[Diagnostics.ProcessStartInfo]::new();$psi.FileName='powershell.exe'
 $reader=Join-Path $PSScriptRoot 'NBL_CANH_BAO\read_warning.ps1'
 $psi.Arguments='-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+$reader+'" -TestProcessId '+$PID
 $psi.UseShellExecute=$false;$psi.RedirectStandardOutput=$true;$psi.RedirectStandardError=$true;$psi.CreateNoWindow=$true
 $psi.StandardOutputEncoding=[Text.UTF8Encoding]::new($false)
 $proc=[Diagnostics.Process]::Start($psi);$frame=[Windows.Threading.DispatcherFrame]::new();$timer=[Windows.Threading.DispatcherTimer]::new();$timer.Interval=[TimeSpan]::FromMilliseconds(30);$until=(Get-Date).AddSeconds(20)
 $timer.Add_Tick({if($proc.HasExited -or (Get-Date) -gt $until){$frame.Continue=$false}})
 $timer.Start();[Windows.Threading.Dispatcher]::PushFrame($frame);$timer.Stop()
 if(-not $proc.HasExited){$proc.Kill();throw 'UIA fixture timed out'}
 $out=$proc.StandardOutput.ReadToEnd();$err=$proc.StandardError.ReadToEnd()
 if($proc.ExitCode -ne 0){throw $err}
 return ($out|ConvertFrom-Json)
}
try {
 $first=Scan-Fixture
 if(-not $first.warning -or -not (@($first.warnings)|Where-Object {$_.countdown -match '30'})){throw 'Dedicated warning/countdown was not detected'}
 $heading.Text='Phiên LIVE đang chạy bình thường';$countdown.Text=''
 $second=Scan-Fixture
 if($second.warning){throw 'A chat row was incorrectly detected as a warning'}
 $report=@{warning_label=$true;countdown=$true;chat_excluded=$true;real_tiktok_live_tested=$false;time=(Get-Date).ToString('o')}
 $folder=Join-Path $env:LOCALAPPDATA 'NBL_LIVE_2';New-Item -ItemType Directory -Path $folder -Force|Out-Null
 $report|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $folder 'native_alarm_check.json') -Encoding UTF8
 Write-Host 'DAT: nhan canh bao, doc dem nguoc, bo qua loi khach trong cua so thu. Chua kiem thu LIVE that.'
} finally {$window.Close()}
