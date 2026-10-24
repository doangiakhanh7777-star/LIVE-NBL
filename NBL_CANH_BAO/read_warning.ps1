param([int]$TestProcessId=0)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
. (Join-Path (Split-Path $PSScriptRoot -Parent) 'warning_filter.ps1')
$A=[System.Windows.Automation.AutomationElement]
$root=$A::RootElement
$windows=$root.FindAll([System.Windows.Automation.TreeScope]::Children,[System.Windows.Automation.Condition]::TrueCondition)
$warnings=[System.Collections.Generic.List[object]]::new();$checked=0
foreach($window in $windows){
 try {
  $p=Get-Process -Id $window.Current.ProcessId -ErrorAction Stop
  if($p.Id -ne $TestProcessId -and $p.ProcessName -notmatch '(?i)tiktok|live.?studio|chrome|msedge'){continue}
  if($p.ProcessName -match '(?i)chrome|msedge' -and $window.Current.Name -notmatch '(?i)tiktok'){continue}
  $checked++
  $names=@(Get-NblWarningNames $window)
  if($names.Count -gt 0){
   $text=(Get-NblVisibleNames $window) -join ' '
   $countdown=[regex]::Match($text,'(?i)(?:còn|remaining|time left|kết thúc sau|ends? in|xác minh trong)\D{0,30}(\d{1,2}:\d{2}|\d+\s*(?:giây|seconds?))')
   $warnings.Add(@{title=$window.Current.Name;process=$p.ProcessName;pid=$p.Id;handle=$window.Current.NativeWindowHandle;countdown=$countdown.Groups[1].Value})
  }
 } catch {continue}
}
@{warning=($warnings.Count -gt 0);windows=$checked;warnings=@($warnings.ToArray())}|ConvertTo-Json -Compress
