#define MyAppName "HCMUS Hub"
#define MyAppVersion "0.8.0"
#define MyAppPublisher "HCMUS Hub"
#define MyAppExeName "HCMUS-Hub.exe"

[Setup]
AppId={{8F4B9D2D-2C7C-4D2E-AE9A-6A5E8B7AA001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\HCMUS Hub
DefaultGroupName={#MyAppName}
OutputDir=..\dist\installer
OutputBaseFilename=HCMUS-Hub-Setup
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
Uninstallable=yes

[Files]
Source: "..\dist\windows\HCMUS-Hub\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Dirs]
Name: "{localappdata}\HCMUS Hub\data"

[Icons]
Name: "{autodesktop}\HCMUS Hub"; Filename: "{app}\HCMUS-Hub.exe"; WorkingDir: "{app}"
Name: "{group}\HCMUS Hub"; Filename: "{app}\HCMUS-Hub.exe"; WorkingDir: "{app}"
Name: "{group}\Uninstall HCMUS Hub"; Filename: "{uninstallexe}"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
