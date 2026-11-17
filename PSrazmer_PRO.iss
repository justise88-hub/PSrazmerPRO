#define MyAppName "PSразмер PRO"
#define MyAppVersion "2.8.2"
#define MyAppPublisher "P.Sveshnikov"
#define MyAppExeName "PSrazmer_PRO.exe"

[Setup]
AppId={{8C34C71A-7B25-4F31-A77E-9D2D0F9D28B8}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\PSrazmer PRO
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=installer_output
OutputBaseFilename=PSrazmer_PRO_2_8_2_Setup
SetupIconFile=Resources\PSrazmer.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesInstallIn64BitMode=x64
ArchitecturesAllowed=x64
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
UsePreviousAppDir=yes

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительные параметры:"; Flags: unchecked

[Files]
Source: "dist\PSrazmer_PRO\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\PSразмер PRO"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\PSразмер PRO"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить PSразмер PRO"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
; Пользовательские данные (Employees, Config, Exports, Backups и т.п.) намеренно сохраняются.
