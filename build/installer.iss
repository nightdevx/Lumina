; LUMINA installer - per-user, no admin prompt.
;
; PrivilegesRequired=lowest keeps UAC out of the way: everything lands under
; %LOCALAPPDATA%\Programs\Lumina and the uninstall entry is per-user too.

#define AppName "LUMINA"
#define AppVersion "2.0.0"
#define AppPublisher "Lumina"
#define AppExeName "LUMINA.exe"

[Setup]
AppId={{8F3A2C91-5D47-4B8E-9A12-7C6E1F0B4D23}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\Lumina
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=output
OutputBaseFilename=LuminaSetup-{#AppVersion}
SetupIconFile=..\src\lumina\resources\lumina.ico
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName} {#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Restart Manager closes a running LUMINA instead of failing on locked files.
CloseApplications=yes
RestartApplications=no
MinVersion=10.0

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startupicon"; Description: "Windows ile birlikte başlat"; GroupDescription: "Başlangıç:"

[Files]
Source: "output\dist\LUMINA\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "output\dist\LUMINA\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Registry]
; --tray so a logon start goes straight to the notification area.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "LUMINA"; ValueData: """{app}\{#AppExeName}"" --tray"; \
    Flags: uninsdeletevalue; Tasks: startupicon
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: none; ValueName: "LUMINA"; Flags: deletevalue uninsdeletevalue; Tasks: not startupicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Logs and cache are ours; the config under %APPDATA% is the user's and stays.
Type: filesandordirs; Name: "{localappdata}\Lumina"
