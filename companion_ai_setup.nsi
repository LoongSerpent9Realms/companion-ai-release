; Companion AI - NSIS Installer
; Build order:
;   1. python build_exe.py
;   2. makensis companion_ai_setup.nsi
; Requires: NSIS 3+ (https://nsis.sourceforge.io/Download)

!define MyAppName "AI陪伴桌宠"
!define MyAppVersion "1.0.42"
!define MyAppPublisher "Companion AI"
!define MyAppExeName "CompanionAI.exe"
!define MyAppURL "http://127.0.0.1:59137"
!define MyAppDirName "CompanionAI"
!define AppId "A1B2C3D4-E5F6-7890-ABCD-EF1234567890"

Unicode true
ManifestDPIAware true
SetCompressor /SOLID lzma

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "x64.nsh"
!include "FileFunc.nsh"

Name "${MyAppName}"
OutFile "installer_output\CompanionAI-Setup.exe"
InstallDir "$LOCALAPPDATA\${MyAppDirName}"
InstallDirRegKey HKCU "Software\${MyAppDirName}" "InstallDir"
RequestExecutionLevel admin
ShowInstDetails hide
ShowUnInstDetails hide
BrandingText "${MyAppName} ${MyAppVersion}"

; Version Info
VIProductVersion "1.0.42.0"
VIAddVersionKey "ProductName" "${MyAppName}"
VIAddVersionKey "CompanyName" "${MyAppPublisher}"
VIAddVersionKey "FileVersion" "${MyAppVersion}"
VIAddVersionKey "ProductVersion" "${MyAppVersion}"
VIAddVersionKey "FileDescription" "${MyAppName}"
VIAddVersionKey "LegalCopyright" "Companion AI"

; ===== MUI Settings =====
!define MUI_ABORTWARNING
!define MUI_ICON "pet_icon.ico"
!define MUI_UNICON "pet_icon.ico"
!define MUI_WELCOMEFINISHPAGE_BITMAP "installer_sidebar.bmp"
!define MUI_UNWELCOMEFINISHPAGE_BITMAP "installer_sidebar.bmp"
!define MUI_WELCOMEPAGE_TITLE "欢迎安装 ${MyAppName}"
!define MUI_WELCOMEPAGE_TEXT "安装向导将把 ${MyAppName} 安装到你的电脑。$\r$\n$\r$\n安装过程中可以选择是否创建桌面快捷方式和开始菜单快捷方式。$\r$\n$\r$\n建议先关闭正在运行的 ${MyAppName}，然后点击“下一步”继续。"
!define MUI_LICENSEPAGE_TEXT_TOP "请阅读以下许可协议。继续安装前需要同意协议条款。"
!define MUI_LICENSEPAGE_TEXT_BOTTOM "如果你接受协议条款，请勾选同意选项，然后点击“下一步”。"
!define MUI_COMPONENTSPAGE_TEXT_TOP "请选择要安装的附加选项。主程序和必要运行环境会自动安装。"
!define MUI_COMPONENTSPAGE_TEXT_COMPLIST "可选安装项："
!define MUI_DIRECTORYPAGE_TEXT_TOP "请选择 ${MyAppName} 的安装位置。"
!define MUI_DIRECTORYPAGE_TEXT_DESTINATION "安装目录"
!define MUI_INSTFILESPAGE_FINISHHEADER_TEXT "安装完成"
!define MUI_INSTFILESPAGE_FINISHHEADER_SUBTEXT "${MyAppName} 已安装到你的电脑。"
!define MUI_FINISHPAGE_TITLE "${MyAppName} 安装完成"
!define MUI_FINISHPAGE_TEXT "安装已完成。你可以立即启动桌面宠物，也可以稍后通过已创建的快捷方式或安装目录启动。"
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_TEXT "立即启动桌面宠物"
!define MUI_FINISHPAGE_RUN_FUNCTION LaunchCompanionPet
!define MUI_FINISHPAGE_RUN_NOTCHECKED
!define MUI_LICENSEPAGE_CHECKBOX
!define MUI_LICENSEPAGE_CHECKBOX_TEXT "我已阅读并同意此许可协议"

; Installer Pages
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "LICENSE.txt"
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

; Uninstaller Pages
!insertmacro MUI_UNPAGE_WELCOME
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH

; Languages (SimpChinese first = default)
!insertmacro MUI_LANGUAGE "SimpChinese"
!insertmacro MUI_LANGUAGE "English"

; ===== Helper: Kill Companion processes =====
!macro _KillCompanionProcesses un
Function ${un}KillCompanionProcesses
  DetailPrint "正在停止 Companion AI 相关进程..."
  nsExec::Exec `cmd /c "taskkill /f /t /im CompanionAI.exe >nul 2>&1 & taskkill /f /t /im CompanionPet.exe >nul 2>&1 & taskkill /f /t /im 智能伙伴.exe >nul 2>&1"`
  nsExec::Exec `powershell -NoProfile -ExecutionPolicy Bypass -Command "$$targets = Get-CimInstance Win32_Process -Filter 'Name=''electron.exe'' OR Name=''msedge.exe'' OR Name=''msedgewebview2.exe''' | Where-Object { $$_.CommandLine -match 'CompanionAI|electron_pet|model_browser_|model_layer_' }; foreach ($$p in $$targets) { Stop-Process -Id $$p.ProcessId -Force -ErrorAction SilentlyContinue }; $$ports = Get-NetTCPConnection -LocalPort 59137 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique; foreach ($$pid in $$ports) { Stop-Process -Id $$pid -Force -ErrorAction SilentlyContinue }"`
FunctionEnd
!macroend

!insertmacro _KillCompanionProcesses ""
!insertmacro _KillCompanionProcesses "un."

!macro _CreateStartMenuShortcuts
  CreateDirectory "$SMPROGRAMS\${MyAppName}"
  CreateShortcut "$SMPROGRAMS\${MyAppName}\${MyAppName}.lnk" "$INSTDIR\${MyAppExeName}" "--web" "$INSTDIR\pet_icon.ico"
  CreateShortcut "$SMPROGRAMS\${MyAppName}\AI陪伴桌宠 - 桌宠.lnk" "$INSTDIR\${MyAppExeName}" "--pet" "$INSTDIR\pet_icon.ico"
  CreateShortcut "$SMPROGRAMS\${MyAppName}\停止 Companion AI.lnk" "$INSTDIR\${MyAppExeName}" "--stop" "$INSTDIR\pet_icon.ico"
  WriteINIStr "$SMPROGRAMS\${MyAppName}\Live2D 查看器.url" "InternetShortcut" "URL" "http://127.0.0.1:59137/live2d"
  WriteINIStr "$SMPROGRAMS\${MyAppName}\Live2D 查看器.url" "InternetShortcut" "IconFile" "$INSTDIR\pet_icon.ico"
  WriteINIStr "$SMPROGRAMS\${MyAppName}\Live2D 查看器.url" "InternetShortcut" "IconIndex" "0"
  CreateShortcut "$SMPROGRAMS\${MyAppName}\卸载 Companion AI.lnk" "$INSTDIR\Uninstall.exe" "" "$INSTDIR\pet_icon.ico"
!macroend

!macro _RemoveStartMenuShortcuts
  RMDir /r "$SMPROGRAMS\${MyAppName}"
!macroend

; ===== Variables =====
Var DeleteDataOption

; ===== Install Sections =====
Section "核心程序（必需）" SecCore
  SectionIn RO
  Call KillCompanionProcesses
  Sleep 300

  SetOutPath "$INSTDIR"
  File /r /x "runtime" /x "_rocm_sdk_core" /x "_rocm_sdk_libraries" "dist\CompanionAI\*.*"
  File "ai_icon.ico"
  File "pet_icon.ico"
  File "README.md"

  CreateDirectory "$APPDATA\CompanionAI"
  CreateDirectory "$APPDATA\CompanionAI\uploads"
  CreateDirectory "$APPDATA\CompanionAI\runtime"
  CreateDirectory "$APPDATA\CompanionAI\live2d"
  CreateDirectory "$APPDATA\CompanionAI\models"
  CreateDirectory "$APPDATA\CompanionAI\ocr"
  CreateDirectory "$INSTDIR\plugins"

  WriteRegStr HKCU "Software\${MyAppDirName}" "InstallDir" "$INSTDIR"

  WriteUninstaller "$INSTDIR\Uninstall.exe"

  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${AppId}" "DisplayName" "${MyAppName}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${AppId}" "UninstallString" "$\"$INSTDIR\Uninstall.exe$\""
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${AppId}" "QuietUninstallString" "$\"$INSTDIR\Uninstall.exe$\" /S"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${AppId}" "DisplayIcon" "$INSTDIR\pet_icon.ico"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${AppId}" "DisplayVersion" "${MyAppVersion}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${AppId}" "Publisher" "${MyAppPublisher}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${AppId}" "URLInfoAbout" "${MyAppURL}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${AppId}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${AppId}" "NoModify" "1"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${AppId}" "NoRepair" "1"

  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  IntFmt $0 "0x%08X" $0
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${AppId}" "EstimatedSize" "$0"
SectionEnd

Section /o "桌面快捷方式" SecDesktop
  Delete "$DESKTOP\${MyAppName}.lnk"
  Delete "$DESKTOP\Companion AI.lnk"
  Delete "$DESKTOP\Companion Pet.lnk"
  CreateShortcut "$DESKTOP\AI陪伴桌宠 - 桌宠.lnk" "$INSTDIR\${MyAppExeName}" "--pet" "$INSTDIR\pet_icon.ico"
SectionEnd

Section /o "开始菜单快捷方式" SecStartMenu
  SetShellVarContext current
  !insertmacro _CreateStartMenuShortcuts
  SetShellVarContext all
  !insertmacro _CreateStartMenuShortcuts
  SetShellVarContext current
SectionEnd

Section "AI 运行环境：Python 3.12（必需）" SecPython
  SectionIn RO
  DetailPrint "正在检测 Python 环境..."
  ReadRegStr $0 HKLM "SOFTWARE\Python\PythonCore" "CurrentVersion"
  StrCmp $0 "" python_check_paths
  DetailPrint "已检测到 Python: $0"
  StrCpy $1 $0 1
  StrCmp $1 "3" python_check_version python_install_needed
python_check_version:
  StrCpy $1 $0 3 2
  StrCmp $1 "10" python_install_done
  StrCmp $1 "11" python_install_done
  StrCmp $1 "12" python_install_done
  StrCmp $1 "13" python_install_done
  Goto python_install_needed
python_check_paths:
  IfFileExists "$LOCALAPPDATA\Programs\Python\Python312\python.exe" python_install_done
  IfFileExists "$ProgramFiles\Python312\python.exe" python_install_done
  IfFileExists "$ProgramFiles(x86)\Python312\python.exe" python_install_done
python_install_needed:
  DetailPrint "未检测到兼容的 Python，正在下载 Python 3.12..."
  SetOutPath "$TEMP"
  NSISdl::download "https://www.python.org/ftp/python/3.12.0/python-3.12.0-amd64.exe" "$TEMP\python-3.12.0-amd64.exe"
  Pop $0
  StrCmp $0 "success" python_install_start
  DetailPrint "Python download failed: $0"
  MessageBox MB_ICONEXCLAMATION|MB_OK "Python download failed. Please install Python 3.10-3.13 manually. Download from: https://www.python.org/downloads/"
  Goto python_install_done

python_install_start:
  DetailPrint "正在安装 Python 3.12..."
  nsExec::ExecToStack '"$TEMP\python-3.12.0-amd64.exe" /quiet InstallAllUsers=1 PrependPath=1 Include_pip=1 Include_test=0 SimpleInstall=1'
  Pop $0
  Pop $1
  StrCmp $0 "0" python_install_success
  DetailPrint "Python install failed (exit code: $0): $1"
  MessageBox MB_ICONEXCLAMATION|MB_OK "Python install failed. Please install Python 3.10-3.13 manually. Download from: https://www.python.org/downloads/"
  Goto python_install_done

python_install_success:
  DetailPrint "Python 3.12 安装完成"
  Sleep 3000

python_install_done:
SectionEnd

; ===== Section descriptions =====
LangString DESC_SecCore ${LANG_SIMPCHINESE} "安装桌宠主程序、资源文件和卸载程序。此项为必需。"
LangString DESC_SecDesktop ${LANG_SIMPCHINESE} "在桌面创建“AI陪伴桌宠 - 桌宠”快捷方式。"
LangString DESC_SecStartMenu ${LANG_SIMPCHINESE} "在开始菜单创建启动、桌宠、停止、Live2D 查看器和卸载入口。"
LangString DESC_SecPython ${LANG_SIMPCHINESE} "检测并安装兼容的 Python 运行环境，用于 AI、数据集和部分本地能力。此项为必需。"
LangString DESC_SecCore ${LANG_ENGLISH} "Install Companion AI core (required)"
LangString DESC_SecDesktop ${LANG_ENGLISH} "Create the Companion AI Pet desktop shortcut."
LangString DESC_SecStartMenu ${LANG_ENGLISH} "Create Start Menu entries for launch, pet, stop, Live2D viewer, and uninstall."
LangString DESC_SecPython ${LANG_ENGLISH} "Detect and install a compatible Python runtime for AI and local features (required)."

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecCore} $(DESC_SecCore)
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} $(DESC_SecDesktop)
  !insertmacro MUI_DESCRIPTION_TEXT ${SecStartMenu} $(DESC_SecStartMenu)
  !insertmacro MUI_DESCRIPTION_TEXT ${SecPython} $(DESC_SecPython)
!insertmacro MUI_FUNCTION_DESCRIPTION_END

; ===== .onInit =====
Function .onInit
FunctionEnd

Function LaunchCompanionPet
  IfFileExists "$INSTDIR\${MyAppExeName}" 0 launch_missing
  SetOutPath "$INSTDIR"
  ExecShell "open" "$INSTDIR\${MyAppExeName}" "--pet" SW_SHOWNORMAL
  Return

launch_missing:
  MessageBox MB_ICONEXCLAMATION|MB_OK "未找到 $INSTDIR\${MyAppExeName}，无法启动桌面宠物。"
FunctionEnd

; ===== Uninstall Section =====
Section "Uninstall"
  Call un.KillCompanionProcesses
  Sleep 300

  IfSilent keep_data
  MessageBox MB_ICONQUESTION|MB_YESNO "是否保留用户数据？$\r$\n$\r$\n是(Y) - 保留配置文件、历史记录、模型等$\r$\n否(N) - 删除所有数据" IDYES keep_data IDNO del_data
  keep_data:
    StrCpy $DeleteDataOption 0
    Goto after_ask
  del_data:
    StrCpy $DeleteDataOption 1
  after_ask:

  DetailPrint "正在删除程序文件..."
  SetDetailsPrint none
  RMDir /r "$INSTDIR"

  ${If} $DeleteDataOption == 1
    RMDir /r "$APPDATA\CompanionAI"
  ${EndIf}

  SetShellVarContext current
  !insertmacro _RemoveStartMenuShortcuts
  SetShellVarContext all
  !insertmacro _RemoveStartMenuShortcuts
  SetShellVarContext current
  SetDetailsPrint both

  SetShellVarContext current
  Delete "$DESKTOP\AI陪伴桌宠 - 桌宠.lnk"
  Delete "$DESKTOP\${MyAppName}.lnk"
  Delete "$DESKTOP\Companion AI.lnk"
  Delete "$DESKTOP\Companion Pet.lnk"
  SetShellVarContext all
  Delete "$DESKTOP\AI陪伴桌宠 - 桌宠.lnk"
  Delete "$DESKTOP\${MyAppName}.lnk"
  Delete "$DESKTOP\Companion AI.lnk"
  Delete "$DESKTOP\Companion Pet.lnk"
  SetShellVarContext current

  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${AppId}"
  DeleteRegKey HKCU "Software\${MyAppDirName}"
SectionEnd

Function un.onInit
  !insertmacro MUI_UNGETLANGUAGE
FunctionEnd
