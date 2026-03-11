; Inno Setup script for AppTrackr

[Setup]
AppName=AppTrackr
AppVersion=1.0.0
AppPublisher=AppTrackr
DefaultDirName={localappdata}\AppTrackr
DefaultGroupName=AppTrackr
OutputBaseFilename=AppTrackr_Setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
SetupIconFile=
UninstallDisplayIcon={app}\AppTrackr.exe

[Files]
Source: "..\dist\AppTrackr\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs

[Icons]
Name: "{group}\AppTrackr"; Filename: "{app}\AppTrackr.exe"
Name: "{autodesktop}\AppTrackr"; Filename: "{app}\AppTrackr.exe"

[Tasks]
Name: "autostart"; Description: "Launch AppTrackr on system startup"; GroupDescription: "System:"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "AppTrackr"; \
    ValueData: """{app}\AppTrackr.exe"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\AppTrackr.exe"; Description: "Launch AppTrackr"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Clean up autostart on uninstall
[UninstallDelete]
Type: filesandordirs; Name: "{app}"
