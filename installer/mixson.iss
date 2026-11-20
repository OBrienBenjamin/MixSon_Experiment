; Inno Setup script for the MixSon Windows installer.
; Built by GitHub Actions (see .github/workflows/build.yml):
;     ISCC /DMyAppVersion=1.0.3 installer\mixson.iss
; Expects, relative to this file:
;     ..\dist\MixSon\            the PyInstaller output folder (MixSon.exe + _internal)
;     vc_redist.x64.exe          downloaded by the workflow (not stored in git)

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0-dev"
#endif
#define MyAppName "MixSon"
#define MyAppExeName "MixSon.exe"

[Setup]
; Never change AppId: it is how newer installers recognise and update an existing installation.
AppId={{7E54B9E1-EE07-43A1-B084-1E4A5AF36DE9}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=MixSon project
AppPublisherURL=https://github.com/OBrienBenjamin/MixSon_Experiment
; Per-user install: no administrator rights needed, and the app folder stays writable, so
; media\ and Responses\ can live next to MixSon.exe (the app looks for them there).
; Default location: C:\Users\<name>\AppData\Local\Programs\MixSon
PrivilegesRequired=lowest
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\installer_output
OutputBaseFilename=MixSon-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Dirs]
; Created empty; the installer never touches their content, and uninstalling keeps your data.
Name: "{app}\media"
Name: "{app}\Responses"

[Files]
Source: "..\dist\MixSon\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Microsoft Visual C++ runtime: unpacked only if the PC does not have it (see [Code])
Source: "vc_redist.x64.exe"; DestDir: "{tmp}"; Flags: dontcopy

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autoprograms}\{#MyAppName} - stimuli folder (media)"; Filename: "{win}\explorer.exe"; Parameters: """{app}\media"""
Name: "{autoprograms}\{#MyAppName} - results folder (Responses)"; Filename: "{win}\explorer.exe"; Parameters: """{app}\Responses"""
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; shellexec lets Windows show its administrator prompt for the runtime installer
Filename: "{tmp}\vc_redist.x64.exe"; Parameters: "/install /quiet /norestart"; StatusMsg: "Installing the Microsoft Visual C++ runtime..."; Check: VCRedistNeedsInstall; Flags: shellexec waituntilterminated
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
function VCRedistNeedsInstall: Boolean;
var
  Installed: Cardinal;
begin
  // Documented registry marker of the Visual C++ 2015-2022 x64 runtime
  Result := not (RegQueryDWordValue(HKLM, 'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64',
                                    'Installed', Installed) and (Installed = 1));
  if Result then
    ExtractTemporaryFile('vc_redist.x64.exe');
end;