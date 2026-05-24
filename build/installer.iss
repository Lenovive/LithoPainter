; Inno Setup script for Lithopainter.
; Compiled by ..\build_exe.ps1 after PyInstaller + JRE staging.
; Produces ..\installer-out\LithopainterSetup.exe.
;
; Per-user install by default (no UAC), so generated `output\` next to the
; EXE is user-writable. Admin users may opt into a per-machine install.

#define MyAppName     "Lithopainter"
#define MyAppVersion  "1.0.0"
#define MyAppExeName  "Lithopainter.exe"

[Setup]
AppId={{6E2A8B3C-7A1F-4F7D-9E3C-2D7D1A6E4C12}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=Lithopainter
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\installer-out
OutputBaseFilename=LithopainterSetup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\Lithopainter\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
