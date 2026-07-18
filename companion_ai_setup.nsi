; Companion AI - NSIS Installer
; Build order:
;   1. python build_exe.py
;   2. makensis companion_ai_setup.nsi
; Requires: NSIS 3+ (https://nsis.sourceforge.io/Download)

!define MyAppName "AI陪伴桌宠"
!define MyAppVersion "1.0.65"
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

Name "$(AppDisplayName)"
OutFile "installer_output\CompanionAI-Setup.exe"
InstallDir "$LOCALAPPDATA\${MyAppDirName}"
InstallDirRegKey HKCU "Software\${MyAppDirName}" "InstallDir"
RequestExecutionLevel admin
ShowInstDetails hide
ShowUnInstDetails hide
BrandingText "$(AppDisplayName) ${MyAppVersion}"

; Version Info
VIProductVersion "1.0.65.0"
VIAddVersionKey "ProductName" "Companion AI"
VIAddVersionKey "CompanyName" "${MyAppPublisher}"
VIAddVersionKey "FileVersion" "${MyAppVersion}"
VIAddVersionKey "ProductVersion" "${MyAppVersion}"
VIAddVersionKey "FileDescription" "Companion AI"
VIAddVersionKey "LegalCopyright" "Companion AI"

; ===== MUI Settings =====
!define MUI_ABORTWARNING
; Always ask at installer startup instead of silently using the system or a
; previously saved language.
!define MUI_LANGDLL_ALWAYSSHOW
!define MUI_ICON "pet_icon.ico"
!define MUI_UNICON "pet_icon.ico"
!define MUI_WELCOMEFINISHPAGE_BITMAP "installer_sidebar.bmp"
!define MUI_UNWELCOMEFINISHPAGE_BITMAP "installer_sidebar.bmp"
!define MUI_WELCOMEPAGE_TITLE "$(WelcomeTitle)"
!define MUI_WELCOMEPAGE_TEXT "$(WelcomeText)"
!define MUI_LICENSEPAGE_TEXT_TOP "$(LicenseTextTop)"
!define MUI_LICENSEPAGE_TEXT_BOTTOM "$(LicenseTextBottom)"
!define MUI_COMPONENTSPAGE_TEXT_TOP "$(ComponentsTextTop)"
!define MUI_COMPONENTSPAGE_TEXT_COMPLIST "$(ComponentsListText)"
!define MUI_DIRECTORYPAGE_TEXT_TOP "$(DirectoryTextTop)"
!define MUI_DIRECTORYPAGE_TEXT_DESTINATION "$(DirectoryDestinationText)"
!define MUI_INSTFILESPAGE_FINISHHEADER_TEXT "$(InstallFinishedTitle)"
!define MUI_INSTFILESPAGE_FINISHHEADER_SUBTEXT "$(InstallFinishedText)"
!define MUI_FINISHPAGE_TITLE "$(FinishTitle)"
!define MUI_FINISHPAGE_TEXT "$(FinishText)"
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_TEXT "$(FinishRunText)"
!define MUI_FINISHPAGE_RUN_FUNCTION LaunchCompanionPet
!define MUI_FINISHPAGE_RUN_NOTCHECKED
!define MUI_LICENSEPAGE_CHECKBOX
!define MUI_LICENSEPAGE_CHECKBOX_TEXT "$(LicenseCheckboxText)"

; Installer Pages
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "$(PrivacyPolicyFile)"
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

LicenseLangString PrivacyPolicyFile ${LANG_SIMPCHINESE} "installer_privacy_zh.txt"
LicenseLangString PrivacyPolicyFile ${LANG_ENGLISH} "installer_privacy_en.txt"

; ===== Localized installer strings =====
LangString AppDisplayName ${LANG_SIMPCHINESE} "AI陪伴桌宠"
LangString AppDisplayName ${LANG_ENGLISH} "AI Companion Pet"
LangString WelcomeTitle ${LANG_SIMPCHINESE} "欢迎安装 AI陪伴桌宠"
LangString WelcomeTitle ${LANG_ENGLISH} "Welcome to AI Companion Pet Setup"
LangString WelcomeText ${LANG_SIMPCHINESE} "安装向导将把 AI陪伴桌宠 安装到你的电脑。$\r$\n$\r$\n安装过程中可以选择是否创建桌面快捷方式和开始菜单快捷方式。$\r$\n$\r$\n建议先关闭正在运行的 AI陪伴桌宠，然后点击“下一步”继续。"
LangString WelcomeText ${LANG_ENGLISH} "This wizard will install AI Companion Pet on your computer.$\r$\n$\r$\nYou can choose whether to create Desktop and Start Menu shortcuts.$\r$\n$\r$\nClose any running AI Companion Pet windows, then click Next to continue."
LangString LicenseTextTop ${LANG_SIMPCHINESE} "请阅读以下隐私政策。继续安装前需要同意其条款。"
LangString LicenseTextTop ${LANG_ENGLISH} "Please review the privacy policy. You must accept it before continuing."
LangString LicenseTextBottom ${LANG_SIMPCHINESE} "如果你接受隐私政策，请勾选同意选项，然后点击“下一步”。"
LangString LicenseTextBottom ${LANG_ENGLISH} "Select the acceptance option and click Next if you accept the privacy policy."
LangString ComponentsTextTop ${LANG_SIMPCHINESE} "请选择要安装的附加选项。主程序和必要运行环境会自动安装。"
LangString ComponentsTextTop ${LANG_ENGLISH} "Choose optional items to install. The main program and required runtime are installed automatically."
LangString ComponentsListText ${LANG_SIMPCHINESE} "可选安装项："
LangString ComponentsListText ${LANG_ENGLISH} "Optional components:"
LangString DirectoryTextTop ${LANG_SIMPCHINESE} "请选择 AI陪伴桌宠 的安装位置。"
LangString DirectoryTextTop ${LANG_ENGLISH} "Choose where to install AI Companion Pet."
LangString DirectoryDestinationText ${LANG_SIMPCHINESE} "安装目录"
LangString DirectoryDestinationText ${LANG_ENGLISH} "Destination folder"
LangString InstallFinishedTitle ${LANG_SIMPCHINESE} "安装完成"
LangString InstallFinishedTitle ${LANG_ENGLISH} "Installation complete"
LangString InstallFinishedText ${LANG_SIMPCHINESE} "AI陪伴桌宠 已安装到你的电脑。"
LangString InstallFinishedText ${LANG_ENGLISH} "AI Companion Pet has been installed on your computer."
LangString FinishTitle ${LANG_SIMPCHINESE} "AI陪伴桌宠 安装完成"
LangString FinishTitle ${LANG_ENGLISH} "AI Companion Pet Setup Complete"
LangString FinishText ${LANG_SIMPCHINESE} "安装已完成。你可以立即启动桌面宠物，也可以稍后通过已创建的快捷方式或安装目录启动。"
LangString FinishText ${LANG_ENGLISH} "Setup is complete. You can start the desktop pet now, or later from the shortcuts or installation folder."
LangString FinishRunText ${LANG_SIMPCHINESE} "立即启动桌面宠物"
LangString FinishRunText ${LANG_ENGLISH} "Start the desktop pet now"
LangString LicenseCheckboxText ${LANG_SIMPCHINESE} "我已阅读并同意此隐私政策"
LangString LicenseCheckboxText ${LANG_ENGLISH} "I have read and accept this privacy policy"
LangString SecCoreName ${LANG_SIMPCHINESE} "核心程序（必需）"
LangString SecCoreName ${LANG_ENGLISH} "Core application (required)"
LangString SecDesktopName ${LANG_SIMPCHINESE} "桌面快捷方式"
LangString SecDesktopName ${LANG_ENGLISH} "Desktop shortcut"
LangString SecStartMenuName ${LANG_SIMPCHINESE} "开始菜单快捷方式"
LangString SecStartMenuName ${LANG_ENGLISH} "Start Menu shortcuts"
LangString SecPythonName ${LANG_SIMPCHINESE} "AI 运行环境：Python 3.12（必需）"
LangString SecPythonName ${LANG_ENGLISH} "AI runtime: Python 3.12 (required)"
LangString StoppingProcesses ${LANG_SIMPCHINESE} "正在停止 Companion AI 相关进程..."
LangString StoppingProcesses ${LANG_ENGLISH} "Stopping Companion AI processes..."
LangString PetShortcut ${LANG_SIMPCHINESE} "AI陪伴桌宠 - 桌宠"
LangString PetShortcut ${LANG_ENGLISH} "Companion AI - Desktop Pet"
LangString StopShortcut ${LANG_SIMPCHINESE} "停止 Companion AI"
LangString StopShortcut ${LANG_ENGLISH} "Stop Companion AI"
LangString Live2DShortcut ${LANG_SIMPCHINESE} "Live2D 查看器"
LangString Live2DShortcut ${LANG_ENGLISH} "Live2D Viewer"
LangString UninstallShortcut ${LANG_SIMPCHINESE} "卸载 Companion AI"
LangString UninstallShortcut ${LANG_ENGLISH} "Uninstall Companion AI"
LangString DetectingPython ${LANG_SIMPCHINESE} "正在检测 Python 环境..."
LangString DetectingPython ${LANG_ENGLISH} "Checking the Python environment..."
LangString DetectedPython ${LANG_SIMPCHINESE} "已检测到 Python: $0"
LangString DetectedPython ${LANG_ENGLISH} "Detected Python: $0"
LangString DownloadingPython ${LANG_SIMPCHINESE} "未检测到兼容的 Python，正在下载 Python 3.12..."
LangString DownloadingPython ${LANG_ENGLISH} "No compatible Python was found. Downloading Python 3.12..."
LangString PythonDownloadFailed ${LANG_SIMPCHINESE} "Python 下载失败：$0$\r$\n请从 https://www.python.org/downloads/ 手动安装 Python 3.10-3.13。"
LangString PythonDownloadFailed ${LANG_ENGLISH} "Python download failed: $0$\r$\nInstall Python 3.10-3.13 manually from https://www.python.org/downloads/."
LangString InstallingPython ${LANG_SIMPCHINESE} "正在安装 Python 3.12..."
LangString InstallingPython ${LANG_ENGLISH} "Installing Python 3.12..."
LangString PythonInstallFailed ${LANG_SIMPCHINESE} "Python 安装失败：$1$\r$\n请从 https://www.python.org/downloads/ 手动安装 Python 3.10-3.13。"
LangString PythonInstallFailed ${LANG_ENGLISH} "Python installation failed: $1$\r$\nInstall Python 3.10-3.13 manually from https://www.python.org/downloads/."
LangString PythonInstalled ${LANG_SIMPCHINESE} "Python 3.12 安装完成"
LangString PythonInstalled ${LANG_ENGLISH} "Python 3.12 installation complete"
LangString LaunchMissing ${LANG_SIMPCHINESE} "未找到 $INSTDIR\${MyAppExeName}，无法启动桌面宠物。"
LangString LaunchMissing ${LANG_ENGLISH} "Could not find $INSTDIR\${MyAppExeName}. The desktop pet cannot be started."
LangString KeepDataQuestion ${LANG_SIMPCHINESE} "是否保留用户数据？$\r$\n$\r$\n是(Y) - 保留配置文件、历史记录、模型等$\r$\n否(N) - 删除所有数据"
LangString KeepDataQuestion ${LANG_ENGLISH} "Keep user data?$\r$\n$\r$\nYes - Keep settings, history, models, and other user data$\r$\nNo - Delete all user data"
LangString RemovingProgram ${LANG_SIMPCHINESE} "正在删除程序文件..."
LangString RemovingProgram ${LANG_ENGLISH} "Removing program files..."

; ===== Helper: Kill Companion processes =====
!macro _KillCompanionProcesses un
Function ${un}KillCompanionProcesses
  DetailPrint "$(StoppingProcesses)"
  nsExec::Exec `cmd /c "taskkill /f /t /im CompanionAI.exe >nul 2>&1 & taskkill /f /t /im CompanionPet.exe >nul 2>&1 & taskkill /f /t /im 智能伙伴.exe >nul 2>&1"`
  nsExec::Exec `powershell -NoProfile -ExecutionPolicy Bypass -Command "$$targets = Get-CimInstance Win32_Process -Filter 'Name=''electron.exe'' OR Name=''msedge.exe'' OR Name=''msedgewebview2.exe''' | Where-Object { $$_.CommandLine -match 'CompanionAI|electron_pet|model_browser_|model_layer_' }; foreach ($$p in $$targets) { Stop-Process -Id $$p.ProcessId -Force -ErrorAction SilentlyContinue }; $$ports = Get-NetTCPConnection -LocalPort 59137 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique; foreach ($$pid in $$ports) { Stop-Process -Id $$pid -Force -ErrorAction SilentlyContinue }"`
FunctionEnd
!macroend

!insertmacro _KillCompanionProcesses ""
!insertmacro _KillCompanionProcesses "un."

!macro _CreateStartMenuShortcuts
  CreateDirectory "$SMPROGRAMS\$(AppDisplayName)"
  CreateShortcut "$SMPROGRAMS\$(AppDisplayName)\$(AppDisplayName).lnk" "$INSTDIR\${MyAppExeName}" "--web" "$INSTDIR\pet_icon.ico"
  CreateShortcut "$SMPROGRAMS\$(AppDisplayName)\$(PetShortcut).lnk" "$INSTDIR\${MyAppExeName}" "--pet" "$INSTDIR\pet_icon.ico"
  CreateShortcut "$SMPROGRAMS\$(AppDisplayName)\$(StopShortcut).lnk" "$INSTDIR\${MyAppExeName}" "--stop" "$INSTDIR\pet_icon.ico"
  WriteINIStr "$SMPROGRAMS\$(AppDisplayName)\$(Live2DShortcut).url" "InternetShortcut" "URL" "http://127.0.0.1:59137/live2d"
  WriteINIStr "$SMPROGRAMS\$(AppDisplayName)\$(Live2DShortcut).url" "InternetShortcut" "IconFile" "$INSTDIR\pet_icon.ico"
  WriteINIStr "$SMPROGRAMS\$(AppDisplayName)\$(Live2DShortcut).url" "InternetShortcut" "IconIndex" "0"
  CreateShortcut "$SMPROGRAMS\$(AppDisplayName)\$(UninstallShortcut).lnk" "$INSTDIR\Uninstall.exe" "" "$INSTDIR\pet_icon.ico"
!macroend

!macro _RemoveStartMenuShortcuts
  RMDir /r "$SMPROGRAMS\$(AppDisplayName)"
  RMDir /r "$SMPROGRAMS\AI陪伴桌宠"
  RMDir /r "$SMPROGRAMS\AI Companion Pet"
!macroend

; ===== Variables =====
Var DeleteDataOption

; ===== Install Sections =====
Section "$(SecCoreName)" SecCore
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

  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${AppId}" "DisplayName" "$(AppDisplayName)"
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

Section /o "$(SecDesktopName)" SecDesktop
  Delete "$DESKTOP\${MyAppName}.lnk"
  Delete "$DESKTOP\Companion AI.lnk"
  Delete "$DESKTOP\Companion Pet.lnk"
  Delete "$DESKTOP\$(PetShortcut).lnk"
  Delete "$DESKTOP\AI陪伴桌宠 - 桌宠.lnk"
  Delete "$DESKTOP\Companion AI - Desktop Pet.lnk"
  CreateShortcut "$DESKTOP\$(PetShortcut).lnk" "$INSTDIR\${MyAppExeName}" "--pet" "$INSTDIR\pet_icon.ico"
SectionEnd

Section /o "$(SecStartMenuName)" SecStartMenu
  SetShellVarContext current
  !insertmacro _CreateStartMenuShortcuts
  SetShellVarContext all
  !insertmacro _CreateStartMenuShortcuts
  SetShellVarContext current
SectionEnd

Section "$(SecPythonName)" SecPython
  SectionIn RO
  DetailPrint "$(DetectingPython)"
  ReadRegStr $0 HKLM "SOFTWARE\Python\PythonCore" "CurrentVersion"
  StrCmp $0 "" python_check_paths
  DetailPrint "$(DetectedPython)"
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
  DetailPrint "$(DownloadingPython)"
  SetOutPath "$TEMP"
  NSISdl::download "https://www.python.org/ftp/python/3.12.0/python-3.12.0-amd64.exe" "$TEMP\python-3.12.0-amd64.exe"
  Pop $0
  StrCmp $0 "success" python_install_start
  DetailPrint "Python download failed: $0"
  MessageBox MB_ICONEXCLAMATION|MB_OK "$(PythonDownloadFailed)"
  Goto python_install_done

python_install_start:
  DetailPrint "$(InstallingPython)"
  nsExec::ExecToStack '"$TEMP\python-3.12.0-amd64.exe" /quiet InstallAllUsers=1 PrependPath=1 Include_pip=1 Include_test=0 SimpleInstall=1'
  Pop $0
  Pop $1
  StrCmp $0 "0" python_install_success
  DetailPrint "Python install failed (exit code: $0): $1"
  MessageBox MB_ICONEXCLAMATION|MB_OK "$(PythonInstallFailed)"
  Goto python_install_done

python_install_success:
  DetailPrint "$(PythonInstalled)"
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
  !insertmacro MUI_LANGDLL_DISPLAY
FunctionEnd

Function LaunchCompanionPet
  IfFileExists "$INSTDIR\${MyAppExeName}" 0 launch_missing
  SetOutPath "$INSTDIR"
  ExecShell "open" "$INSTDIR\${MyAppExeName}" "--pet" SW_SHOWNORMAL
  Return

launch_missing:
  MessageBox MB_ICONEXCLAMATION|MB_OK "$(LaunchMissing)"
FunctionEnd

; ===== Uninstall Section =====
Section "Uninstall"
  Call un.KillCompanionProcesses
  Sleep 300

  IfSilent keep_data
  MessageBox MB_ICONQUESTION|MB_YESNO "$(KeepDataQuestion)" IDYES keep_data IDNO del_data
  keep_data:
    StrCpy $DeleteDataOption 0
    Goto after_ask
  del_data:
    StrCpy $DeleteDataOption 1
  after_ask:

  DetailPrint "$(RemovingProgram)"
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
  Delete "$DESKTOP\$(PetShortcut).lnk"
  Delete "$DESKTOP\AI陪伴桌宠 - 桌宠.lnk"
  Delete "$DESKTOP\Companion AI - Desktop Pet.lnk"
  Delete "$DESKTOP\${MyAppName}.lnk"
  Delete "$DESKTOP\Companion AI.lnk"
  Delete "$DESKTOP\Companion Pet.lnk"
  SetShellVarContext all
  Delete "$DESKTOP\$(PetShortcut).lnk"
  Delete "$DESKTOP\AI陪伴桌宠 - 桌宠.lnk"
  Delete "$DESKTOP\Companion AI - Desktop Pet.lnk"
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
