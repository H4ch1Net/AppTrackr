; Inno Setup script for AppTrackr. Build after PyInstaller from the repository root:
;   iscc /DAppVersion=1.2.0 packaging\installer.iss

#ifndef AppVersion
  #define AppVersion "1.2.0"
#endif

[Setup]
; Same AppId as v1.0 (Inno defaults it to AppName) so upgrades replace the old install.
AppId=AppTrackr
AppName=AppTrackr
AppVersion={#AppVersion}
AppVerName=AppTrackr {#AppVersion}
AppPublisher=H4ch1Net
AppPublisherURL=https://github.com/H4ch1Net/AppTrackr
AppSupportURL=https://github.com/H4ch1Net/AppTrackr/issues
DefaultDirName={localappdata}\AppTrackr
DefaultGroupName=AppTrackr
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=AppTrackr_Setup
SetupIconFile=apptrackr.ico
UninstallDisplayIcon={app}\AppTrackr.exe
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=force
RestartApplications=no
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "autostart"; Description: "Start AppTrackr when I sign in"; GroupDescription: "Startup:"

[InstallDelete]
; Replace the previous build's runtime wholesale so files from an older version never mix with this one.
; User data lives in %APPDATA%\AppTrackr and is not touched.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\AppTrackr\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\AppTrackr"; Filename: "{app}\AppTrackr.exe"
Name: "{autodesktop}\AppTrackr"; Filename: "{app}\AppTrackr.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; \
    ValueName: "AppTrackr"; ValueData: """{app}\AppTrackr.exe"" --minimized"; \
    Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\AppTrackr.exe"; Description: "Launch AppTrackr"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C taskkill /IM AppTrackr.exe /F"; Flags: runhidden; RunOnceId: "StopAppTrackr"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
