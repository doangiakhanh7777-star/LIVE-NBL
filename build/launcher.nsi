Unicode true
Name "NBL LIVE"
OutFile "app\NBL_LIVE.exe"
Icon "nbl.ico"
RequestExecutionLevel admin
SilentInstall silent
VIProductVersion "4.3.0.0"
VIAddVersionKey /LANG=0 "ProductName" "NBL LIVE"
VIAddVersionKey /LANG=0 "FileDescription" "NBL LIVE"
VIAddVersionKey /LANG=0 "FileVersion" "4.3.0"
VIAddVersionKey /LANG=0 "ProductVersion" "4.3.0"
VIAddVersionKey /LANG=0 "CompanyName" "NBL"
VIAddVersionKey /LANG=0 "LegalCopyright" "NBL"
Section
  SetOutPath "$EXEDIR"
  IfFileExists "$EXEDIR\runtime\pythonw.exe" 0 missing
  Exec '"$EXEDIR\runtime\pythonw.exe" "$EXEDIR\bootstrap.py"'
  Goto done
  missing:
  MessageBox MB_ICONSTOP "Thiếu thư mục runtime của NBL LIVE. Hãy cài lại bằng NBL_LIVE_Setup_4.3.0.exe."
  done:
SectionEnd
