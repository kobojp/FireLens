#ifndef AppVersion
  #error AppVersion is required, for example /DAppVersion=1.5.0
#endif

#ifndef SourceExe
  #error SourceExe is required
#endif

#define AppName "FireLens"
#define AppExeName "FireLens.exe"
#define SetupBaseName "FireLens-" + AppVersion + "-setup"

[Setup]
AppId={{A7D7F4AD-8E8B-4A60-AC14-7FC4B2BDA73E}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
DefaultDirName={localappdata}\Programs\FireLens
DefaultGroupName=FireLens
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputBaseFilename={#SetupBaseName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
SetupIconFile=assets\firelens.ico
UninstallDisplayIcon={app}\{#AppExeName}
CloseApplications=yes
CloseApplicationsFilter={#AppExeName}
RestartApplications=no
SetupLogging=yes
ShowLanguageDialog=no
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppName}
VersionInfoDescription=FireLens Windows 安裝程式

[Languages]
Name: "chinesetraditional"; MessagesFile: "lang\ChineseTraditional.isl"

[Tasks]
Name: "desktopicon"; Description: "建立桌面捷徑"; GroupDescription: "其他工作："; Flags: unchecked

[Dirs]
Name: "{app}\data"

[Files]
Source: "{#SourceExe}"; DestDir: "{app}"; DestName: "{#AppExeName}"; Flags: ignoreversion
Source: "install.marker"; DestDir: "{app}"; DestName: ".firelens-installed"; Flags: ignoreversion

[Icons]
Name: "{group}\FireLens"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\FireLens"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "啟動 FireLens"; Flags: nowait postinstall skipifsilent
