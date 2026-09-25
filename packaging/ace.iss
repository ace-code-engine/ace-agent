; ============================================================================
; ace.iss -- Inno Setup script for the ACE Windows installer.
;
; WHAT THIS INSTALLS
;   The PyInstaller bundle produced by packaging/build_exe.ps1 (dist\ace\), which
;   already carries its own Python interpreter and every runtime dependency.
;   That is the whole point of shipping an installer: the user does not install
;   Python, pip, or anything else -- there is no "environment" left to prepare.
;
; WHY NOT NSIS / MSI
;   Inno Setup is already present on GitHub's windows-latest runners (Chocolatey),
;   so CI needs no extra download step; it is a single self-contained compiler; and
;   its Pascal scripting covers exactly what we need (PATH entry, file associations
;   not required, clean uninstall). An MSI via WiX would need another toolchain for
;   no benefit at this size.
;
; ASCII-ONLY ON PURPOSE. Same rule as the other packaging scripts, same reason:
;   Windows PowerShell 5.1 and some console code pages read BOM-less files as ANSI,
;   and this repository has been bitten by that repeatedly. Non-ASCII text shown to
;   the user must therefore arrive as {cm:...} custom messages (defined below with
;   ASCII escapes) instead of being typed inline.
;
; BUILD: powershell -NoProfile -ExecutionPolicy Bypass -File packaging/build_installer.ps1
; ============================================================================

#define AppName        "ACE"
#define AppPublisher   "ace-code-engine"
#define AppURL         "https://github.com/ace-code-engine/ace-agent"
#define AppExeName     "ace.exe"

; --- build inputs (overridable with /D on the ISCC command line) ------------
#ifndef SrcDir
  #define SrcDir "..\dist\ace"
#endif
#ifndef OutDir
  #define OutDir "..\dist"
#endif
; Version is read from core/version.py by the build script and passed in as
; /DAppVersion=3.41.0 -- a single source, never typed twice.
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef BuildTag
  #define BuildTag ""
#endif
; OutputBaseFilename is what users see when they download it.
#ifndef OutBaseName
  #define OutBaseName "ace-" + AppVersion + "-windows-amd64-setup"
#endif

[Setup]
AppId={{8C4E1F62-2B7A-4E9D-9C31-5A7E0D4B6F18}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}{#BuildTag}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
OutputDir={#OutDir}
OutputBaseFilename={#OutBaseName}
; The installer's own icon is the application icon -- generated from assets/logo.svg
; by packaging/make_icon.py and committed as assets/ace.ico, so it is always present.
SetupIconFile=..\assets\ace.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; The app is a console program; no need to demand a recent Windows for a UI framework.
MinVersion=10.0
; Let the user install for all users (default) or just themselves.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
; Full uninstall: we add a PATH entry, so make sure it can be taken back out.
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExeName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; A noticeable description in Apps & features, in plain words.
AppComments=Local-first AI coding agent. Ships its own runtime: no Python needed.

[Languages]
; english is Inno's built-in language, so English text is the baseline and there
; are no custom-message indirections that could go stale or miss a language.
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "addtopath"; Description: "Add ACE to PATH (so you can type `ace` in any terminal)"; GroupDescription: "Additional options:"
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional options:"; Flags: unchecked

[Files]
; The bundle: exe + _internal\ plus the resources PyInstaller collected.
Source: "{#SrcDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; "Open a terminal with ACE": cmd /k keeps the window open so the user can actually
; read the landing screen -- a bare .exe shortcut would flash and vanish on exit.
Name: "{group}\{#AppName}"; Filename: "{cmd}"; Parameters: "/k ""{app}\{#AppExeName}"""; WorkingDir: "{app}"; IconFilename: "{app}\{#AppExeName}"
Name: "{group}\{#AppName} (offline demo)"; Filename: "{cmd}"; Parameters: "/k ""{app}\{#AppExeName}"" --mock"; WorkingDir: "{app}"; IconFilename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{cmd}"; Parameters: "/k ""{app}\{#AppExeName}"""; WorkingDir: "{app}"; IconFilename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
; Console app: there is nothing useful to "launch" at the end of setup, so the
; default (checked) option is to open a terminal that runs it.
Filename: "{cmd}"; Parameters: "/k ""{app}\{#AppExeName}"""; WorkingDir: "{app}"; Description: "Open a terminal with ACE (this is a console program)"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
; PyInstaller writes nothing outside its own folder, but the app may leave these
; next to the exe when someone runs it from the install dir.
Type: filesandordirs; Name: "{app}\_internal\__pycache__"

[Code]
const
  EnvironmentKey = 'Environment';

{ Add or remove {app} on the user/machine PATH. Written as a small helper pair so
  the install and uninstall paths cannot drift apart -- the classic bug here is
  adding it on install and forgetting to take it out on uninstall. }
function PathContains(const Paths, Dir: string): Boolean;
var
  I: Integer;
  Parts: TArrayOfString;
begin
  Result := False;
  if Paths = '' then Exit;
  Parts := StringSplit(Paths, ';', stSplitAll);
  for I := 0 to GetArrayLength(Parts) - 1 do
    if CompareText(Trim(Parts[I]), Dir) = 0 then
    begin
      Result := True;
      Exit;
    end;
end;

procedure RemoveFromPath(RootKey: Integer; const Dir: string);
var
  Paths, NewPaths: string;
  I: Integer;
  Parts: TArrayOfString;
begin
  if not RegQueryStringValue(RootKey, EnvironmentKey, 'Path', Paths) then Exit;
  NewPaths := '';
  Parts := StringSplit(Paths, ';', stSplitAll);
  for I := 0 to GetArrayLength(Parts) - 1 do
    if (Parts[I] <> '') and (CompareText(Trim(Parts[I]), Dir) <> 0) then
    begin
      if NewPaths <> '' then NewPaths := NewPaths + ';';
      NewPaths := NewPaths + Parts[I];
    end;
  if NewPaths <> Paths then
    RegWriteExpandStringValue(RootKey, EnvironmentKey, 'Path', NewPaths);
end;

procedure AddToPath(RootKey: Integer; const Dir: string);
var
  Paths: string;
begin
  if not RegQueryStringValue(RootKey, EnvironmentKey, 'Path', Paths) then
    Paths := '';
  if PathContains(Paths, Dir) then Exit;
  if Paths = '' then
    Paths := Dir
  else
    Paths := Paths + ';' + Dir;
  RegWriteExpandStringValue(RootKey, EnvironmentKey, 'Path', Paths);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and WizardIsTaskSelected('addtopath') then
  begin
    { Lowest privileges: we are writing to HKCU, so both cases are safe. }
    if IsAdminInstallMode then
      AddToPath(HKLM, ExpandConstant('{app}'))
    else
      AddToPath(HKCU, ExpandConstant('{app}'));
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    { Remove from BOTH hives: the install mode may have differed (an admin install
      later uninstalled by a standard user, or vice versa). Leaving a dangling path
      entry behind is worse than removing a line that was not there. }
    RemoveFromPath(HKCU, ExpandConstant('{app}'));
    RemoveFromPath(HKLM, ExpandConstant('{app}'));
  end;
end;
