# Shared by LIVE Studio control and the independent alarm reader.
# Read leaf warning labels, never aggregated chat containers or text being typed.
function Test-NblChatElement($element) {
 $walker=[System.Windows.Automation.TreeWalker]::ControlViewWalker
 $node=$element
 for($i=0;$i -lt 12 -and $node;$i++) {
  try {
   $t=$node.Current.ControlType
   if($t -eq [System.Windows.Automation.ControlType]::ListItem -or
      $t -eq [System.Windows.Automation.ControlType]::DataItem -or
      $t -eq [System.Windows.Automation.ControlType]::Edit){return $true}
   $node=$walker.GetParent($node)
  } catch {return $true}
 }
 return $false
}
function Test-NblWarningText([string]$Text) {
 if(-not $Text -or $Text.Length -gt 700){return $false}
 return ($Text -match '(?i)Vi phạm của video LIVE|Phiên LIVE đã bị hạn chế|LIVE violation|xác minh bảo mật|security verification|CAPTCHA' -or
  ($Text -match '(?i)không có hoạt động|không hoạt động|inactivity|inactive' -and $Text -match '(?i)xác minh|verification|verify|phiên live|live.*end'))
}
function Get-NblVisibleNames($scope) {
 $A=[System.Windows.Automation.AutomationElement]
 $named=[System.Windows.Automation.NotCondition]::new([System.Windows.Automation.PropertyCondition]::new($A::NameProperty,''))
 $items=$scope.FindAll([System.Windows.Automation.TreeScope]::Descendants,$named)
 $result=[System.Collections.Generic.List[string]]::new()
 foreach($item in $items){
  try{
   if($item.Current.IsOffscreen -or (Test-NblChatElement $item)){continue}
   $name=$item.Current.Name.Trim()
   if($name -and $name.Length -le 2000){$result.Add($name)}
  }catch{continue}
 }
 return @($result.ToArray()|Select-Object -Unique)
}
function Get-NblWarningNames($scope) {
 return @((Get-NblVisibleNames $scope)|Where-Object {Test-NblWarningText $_})
}
