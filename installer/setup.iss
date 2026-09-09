#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
[Setup]
AppId={{3142A572-8F04-42F4-8F91-57C5C63390F7}
AppName=Engineering Diagram Studio
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\Engineering Diagram Studio
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
DisableWelcomePage=yes
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=no
DisableFinishedPage=yes
OutputDir=..\release
OutputBaseFilename=EngineeringDiagramStudio-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\EngineeringDiagramStudio.exe
CloseApplications=yes
SetupLogging=yes
[Files]
Source: "..\dist\EngineeringDiagramStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{userprograms}\Engineering Diagram Studio"; Filename: "{app}\EngineeringDiagramStudio.exe"
Name: "{userdesktop}\Engineering Diagram Studio"; Filename: "{app}\EngineeringDiagramStudio.exe"
[Run]
Filename: "{app}\EngineeringDiagramStudio.exe"; Flags: nowait skipifsilent
