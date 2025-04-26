; —————————————————————————————
; Settings 
; —————————————————————————————
[Setup]
AppName=OSD
AppVersion=1.0
DefaultDirName={pf}\OSD
DefaultGroupName=OSD
OutputDir=installer
OutputBaseFilename=OSD_Installer
Compression=lzma
SolidCompression=yes

; —————————————————————————————
; Files 
; —————————————————————————————
[Files]
; The main executable
Source: "../build\OSD.exe"; DestDir: "{app}"; Flags: ignoreversion
; Static folder containing images or other files
Source: "../static/*"; DestDir: "{app}\static"; Flags: ignoreversion recursesubdirs createallsubdirs

; —————————————————————————————
; Icons and Shortcuts
; —————————————————————————————
[Icons]
Name: "{group}\OSD"; Filename: "{app}\OSD.exe"
Name: "{commondesktop}\OSD"; Filename: "{app}\OSD.exe"; Tasks: desktopicon

; —————————————————————————————
; Optional Tasks (e.g., option to create a desktop icon)
; —————————————————————————————
[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"
