#ifndef SourceDir
  #define SourceDir "..\..\release\portable\NetSimSweeper"
#endif

#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

#define AppName "NetSim Multi-Parameter Sweeper"
#define Publisher "TETCOS"
#define LauncherExe "NetSimSweeperLauncher.exe"

[Setup]
AppId={{A401FA38-B6A4-4E82-9380-4E55B8D0B3F0}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#Publisher}
DefaultDirName={autopf}\NetSimSweeper
DefaultGroupName=NetSim Sweeper
DisableProgramGroupPage=yes
OutputBaseFilename=NetSimSweeperSetup_{#AppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\NetSim Sweeper"; Filename: "{app}\{#LauncherExe}"
Name: "{autodesktop}\NetSim Sweeper"; Filename: "{app}\{#LauncherExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#LauncherExe}"; Description: "Launch NetSim Sweeper"; Flags: nowait postinstall skipifsilent
