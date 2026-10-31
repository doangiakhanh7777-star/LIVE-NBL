Unicode true
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "x64.nsh"
!include "FileFunc.nsh"

!define APP "NBL LIVE"
!ifndef VER
!define VER "4.3.16"
!endif
!define UKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\NBL_LIVE"

Name "${APP} ${VER}"
OutFile "NBL_LIVE_Setup_${VER}.exe"
InstallDir "$PROGRAMFILES64\NBL_LIVE"
InstallDirRegKey HKLM "${UKEY}" "InstallLocation"
RequestExecutionLevel admin
SetCompressor /SOLID /FINAL lzma
SetCompressorDictSize 128
BrandingText "${APP} ${VER}"
ShowInstDetails show
ShowUninstDetails show

VIProductVersion "4.3.16.0"
VIAddVersionKey /LANG=0 "ProductName" "${APP}"
VIAddVersionKey /LANG=0 "FileDescription" "Cài đặt ${APP} ${VER}"
VIAddVersionKey /LANG=0 "FileVersion" "${VER}"
VIAddVersionKey /LANG=0 "ProductVersion" "${VER}"
VIAddVersionKey /LANG=0 "CompanyName" "NBL"
VIAddVersionKey /LANG=0 "LegalCopyright" "NBL"

!define MUI_ICON "nbl.ico"
!define MUI_UNICON "nbl.ico"
!define MUI_WELCOMEFINISHPAGE_BITMAP "wizard.bmp"
!define MUI_UNWELCOMEFINISHPAGE_BITMAP "wizard.bmp"
!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_RIGHT
!define MUI_HEADERIMAGE_BITMAP "header.bmp"
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "Cài đặt NBL LIVE ${VER}"
!define MUI_WELCOMEPAGE_TEXT "Bộ cài đầy đủ cho Windows 10/11 64-bit: đã có sẵn Python, thư viện video và đọc chữ (OCR), không cần cài thêm gì.$\r$\n$\r$\nDữ liệu nick, lịch và tin nhắn (%LOCALAPPDATA%\NBL_LIVE_2) được giữ nguyên.$\r$\n$\r$\nHãy đóng NBL LIVE và các cửa sổ NBL VIDEO trước khi cài."
!define MUI_FINISHPAGE_RUN "$INSTDIR\NBL_LIVE.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Mở NBL LIVE"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Vietnamese"

Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "NBL LIVE cần Windows 64-bit."
    Abort
  ${EndIf}
  SetRegView 64
FunctionEnd

Function un.onInit
  SetRegView 64
FunctionEnd

; NBL / NBL VIDEO still running from this folder keeps runtime\python312.dll locked.
Function CheckRunning
  retry:
  IfFileExists "$INSTDIR\runtime\python312.dll" 0 free
  ClearErrors
  Rename "$INSTDIR\runtime\python312.dll" "$INSTDIR\runtime\python312.dll.nbl_check"
  IfErrors busy
  Rename "$INSTDIR\runtime\python312.dll.nbl_check" "$INSTDIR\runtime\python312.dll"
  Goto free
  busy:
  ; silent auto-update from NBL: NBL is closing by itself, wait up to 3 minutes, never ask
  IfSilent 0 ask
  IntOp $9 $9 + 1
  IntCmp $9 90 giveup 0 giveup
  Sleep 2000
  Goto retry
  giveup:
  SetErrorLevel 2
  Abort
  ask:
  MessageBox MB_RETRYCANCEL|MB_ICONEXCLAMATION "NBL LIVE hoặc cửa sổ NBL VIDEO đang mở.$\r$\nĐóng hết rồi bấm Thử lại." IDRETRY retry
  Abort
  free:
FunctionEnd

Section "NBL LIVE" SecMain
  SectionIn RO
  StrCpy $9 0
  Call CheckRunning
  SetOutPath "$INSTDIR"
  ; files of older NBL versions that 4.3.4 no longer uses (also the trimmed Qt/OCR parts)
!include "cleanup_old.nsh"
  Delete "$INSTDIR\HUONG_DAN_SU_DUNG.pdf"
  Delete "$INSTDIR\ocr_models\vi\.rec.onnx.aTBUPz"
  Delete "$INSTDIR\THAY_DOI_4.1.txt"
  Delete "$INSTDIR\KET_QUA_KIEM_TRA_4.1.txt"
  Delete "$INSTDIR\requirements-test.txt"
  Delete "$INSTDIR\run_tests.py"
  RMDir /r "$INSTDIR\tests"
  Delete "$INSTDIR\shop_login.py"
  Delete "$INSTDIR\CHROME_NBL_LIVE\shop_login.js"
  Delete "$INSTDIR\SHA256.json"
  Delete "$INSTDIR\cap_nhat.ps1"
  RMDir /r "$INSTDIR\__pycache__"
  RMDir /r "$INSTDIR\_update"
  DetailPrint "Đang chép NBL LIVE (khoảng 400 MB)…"
  File /r /x nbl_camera.dll "app\*.*"
  ; 4.3.16: camera ảo NBL Camera. Studio đang dùng camera thì file bị khóa -> giữ file cũ (cùng bản), không hỏng lượt cài
  SetOutPath "$INSTDIR\camera"
  SetOverwrite try
  File "app\camera\nbl_camera.dll"
  SetOverwrite on
  SetOutPath "$INSTDIR"
  DetailPrint "Đang cài camera ảo NBL Camera…"
  ${DisableX64FSRedirection}
  nsExec::ExecToLog '"$WINDIR\System32\regsvr32.exe" /s "$INSTDIR\camera\nbl_camera.dll"'
  Pop $3
  ${EnableX64FSRedirection}
  DetailPrint "Camera ảo: mã $3"
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  SetShellVarContext all
  CreateShortCut "$DESKTOP\NBL LIVE.lnk" "$INSTDIR\NBL_LIVE.exe" "" "$INSTDIR\assets\logo.ico" 0
  CreateDirectory "$SMPROGRAMS\NBL LIVE"
  CreateShortCut "$SMPROGRAMS\NBL LIVE\NBL LIVE.lnk" "$INSTDIR\NBL_LIVE.exe" "" "$INSTDIR\assets\logo.ico" 0
  CreateShortCut "$SMPROGRAMS\NBL LIVE\Thư mục tiện ích Chrome.lnk" "$INSTDIR\CHROME_NBL_LIVE"
  CreateShortCut "$SMPROGRAMS\NBL LIVE\Gỡ NBL LIVE.lnk" "$INSTDIR\Uninstall.exe" "" "$INSTDIR\assets\logo.ico" 0

  WriteRegStr HKLM "${UKEY}" "DisplayName" "${APP}"
  WriteRegStr HKLM "${UKEY}" "DisplayVersion" "${VER}"
  WriteRegStr HKLM "${UKEY}" "Publisher" "NBL"
  WriteRegStr HKLM "${UKEY}" "DisplayIcon" "$INSTDIR\assets\logo.ico"
  WriteRegStr HKLM "${UKEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKLM "${UKEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegDWORD HKLM "${UKEY}" "NoModify" 1
  WriteRegDWORD HKLM "${UKEY}" "NoRepair" 1
  WriteRegDWORD HKLM "${UKEY}" "EstimatedSize" 376562

  ; 4.3.4: app điện thoại — chỉ mở cổng 8766 cho Tailscale và mạng nhà
  nsExec::Exec 'netsh advfirewall firewall delete rule name="NBL LIVE dien thoai"'
  nsExec::Exec 'netsh advfirewall firewall add rule name="NBL LIVE dien thoai" dir=in action=allow program="$INSTDIR\runtime\pythonw.exe" protocol=TCP localport=8766 remoteip=100.64.0.0/10,LocalSubnet profile=any'
  DetailPrint "Đang kiểm tra bản cài (tệp, thư viện video, OCR, tiện ích Chrome)…"
  nsExec::ExecToLog '"$INSTDIR\runtime\python.exe" "$INSTDIR\setup_verify.py"'
  Pop $0
  ${If} $0 != 0
    MessageBox MB_ICONEXCLAMATION "Kiểm tra sau cài đặt CHƯA ĐẠT.$\r$\nĐừng chạy LIVE bằng bản này; gửi tệp SETUP_CHECK.log trong:$\r$\n$INSTDIR" /SD IDOK
  ${Else}
    DetailPrint "Kiểm tra đạt."
  ${EndIf}
  ; auto-update: open NBL again after a silent install started with /RUN
  ${GetParameters} $1
  ClearErrors
  ${GetOptions} $1 "/RUN" $2
  ${IfNot} ${Errors}
    Exec '"$INSTDIR\NBL_LIVE.exe"'
  ${EndIf}
SectionEnd

Section "Uninstall"
  SetShellVarContext all
  ${DisableX64FSRedirection}
  nsExec::Exec '"$WINDIR\System32\regsvr32.exe" /s /u "$INSTDIR\camera\nbl_camera.dll"'
  ${EnableX64FSRedirection}
  Delete "$DESKTOP\NBL LIVE.lnk"
  RMDir /r "$SMPROGRAMS\NBL LIVE"
!include "uninstall_list.nsh"
  RMDir /r "$INSTDIR\_update"
  RMDir "$INSTDIR"
  nsExec::Exec 'netsh advfirewall firewall delete rule name="NBL LIVE dien thoai"'
  DeleteRegKey HKLM "${UKEY}"
SectionEnd
