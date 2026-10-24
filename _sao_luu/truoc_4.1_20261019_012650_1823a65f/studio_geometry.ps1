# Pure scalar geometry. No Windows input, screen capture or live actions.
function Get-NblImageCorners([int]$x,[int]$y,[int]$width,[int]$height){
 if($width -lt 1 -or $height -lt 1){throw 'Invalid image dimensions'}
 $right=[int]($x+$width-1)
 $bottom=[int]($y+$height-1)
 [pscustomobject]@{X=$x;Y=$y}
 [pscustomobject]@{X=$right;Y=$y}
 [pscustomobject]@{X=$x;Y=$bottom}
 [pscustomobject]@{X=$right;Y=$bottom}
}
function Test-NblGeometry {
 $a=@(Get-NblImageCorners 10 20 96 28)
 if($a.Count -ne 4 -or $a[1].X -ne 105 -or $a[2].Y -ne 47 -or $a[3].X -ne 105 -or $a[3].Y -ne 47){throw 'Studio geometry self-check failed'}
 $b=@(Get-NblImageCorners -120 -40 96 28)
 if($b[3].X -ne -25 -or $b[3].Y -ne -13){throw 'Studio negative-coordinate self-check failed'}
 $c=@(Get-NblImageCorners 0 0 1 1)
 if($c[3].X -ne 0 -or $c[3].Y -ne 0){throw 'Studio one-pixel self-check failed'}
}
Test-NblGeometry
