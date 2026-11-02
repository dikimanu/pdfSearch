[Setup]
AppId={{6F3B8C1E-4A52-4D7B-9C1A-2E8F5B7D3A10}
AppName=PDF Knowledge Search
AppVersion=1.2
AppPublisher=Satyabrata Pal 
DefaultDirName={autopf}\PDF Knowledge Search
DefaultGroupName=PDF Knowledge Search
OutputDir=installer_output
OutputBaseFilename=PDF-Knowledge-Search-Setup-v1.2
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayName=PDF Knowledge Search
UninstallDisplayIcon={app}\PDF Knowledge Search.exe
WizardStyle=modern
SetupIconFile=logo.ico

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "dist\PDF Knowledge Search\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\PDF Knowledge Search"; Filename: "{app}\PDF Knowledge Search.exe"
Name: "{autodesktop}\PDF Knowledge Search"; Filename: "{app}\PDF Knowledge Search.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\PDF Knowledge Search.exe"; Description: "Start PDF Knowledge Search"; Flags: nowait postinstall skipifsilent