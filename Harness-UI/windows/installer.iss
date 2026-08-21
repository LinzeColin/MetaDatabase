#ifndef AppArch
  #define AppArch "x64"
#endif
#ifndef SourceDir
  #define SourceDir "publish"
#endif
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

#define AppName "Harness UI"
#define AppPublisher "LinzeColin"
#define AppExeName "HarnessUI.exe"

[Setup]
AppId={{28ED7767-7871-4303-9B51-4CF9C67315B7}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\Harness UI
DefaultGroupName=Harness UI
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Harness-UI-{#AppVersion}-windows-{#AppArch}-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#AppExeName}
ArchitecturesAllowed={#AppArch}
ArchitecturesInstallIn64BitMode={#AppArch}

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Harness UI"; Filename: "{app}\{#AppExeName}"
Name: "{userdesktop}\Harness UI"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加图标："; Flags: unchecked
Name: "startup"; Description: "登录 Windows 后自动启动"; GroupDescription: "启动选项："

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Harness UI"; ValueData: """{app}\{#AppExeName}"""; Flags: uninsdeletevalue; Tasks: startup

[Run]
Filename: "{app}\{#AppExeName}"; Description: "启动 Harness UI"; Flags: nowait postinstall skipifsilent
