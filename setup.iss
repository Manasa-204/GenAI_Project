; =====================================================================
; Inno Setup 6 Script for Demon Study Monitor
; Creates DemonSetup-v1.0.exe standalone installer with automatic UAC hosts provisioning
; =====================================================================

[Setup]
AppId={{D3E4F5A1-9B8C-4E7F-9A2D-7B5E8A9C1D2E}
AppName=Demon Study Monitor
AppVersion=1.0.0
AppPublisher=Demon AI Team
AppPublisherURL=http://127.0.0.1:8000
DefaultDirName={autopf}\Demon
DefaultGroupName=Demon Study Monitor
OutputDir=Output
OutputBaseFilename=DemonSetup-v1.0
Compression=lzma2/max
SolidCompression=yes
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\Demon.exe

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Copy compiled PyInstaller onedir distribution
Source: "dist\Demon\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Demon Study Monitor"; Filename: "{app}\Demon.exe"
Name: "{autodesktop}\Demon Study Monitor"; Filename: "{app}\Demon.exe"; Tasks: desktopicon

[Run]
; 1. Configure OS hosts write permission for Users group during elevated installation
; This ensures day-to-day runs of Demon.exe never require UAC prompts!
Filename: "icacls.exe"; Parameters: """{sys}\drivers\etc\hosts"" /grant Users:(M)"; Flags: runhidden

; 2. Offer to launch Demon immediately after setup
Filename: "{app}\Demon.exe"; Description: "{cm:LaunchProgram,Demon Study Monitor}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Cleanly unblock any remnant hosts file redirects upon uninstall
Filename: "{sys}\cmd.exe"; Parameters: "/c cd /d ""{app}"" && Grant_Hosts_Permission.bat"; Flags: runhidden
