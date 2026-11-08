#ifndef SourceDir
  #error SourceDir must point to the PyInstaller onedir output.
#endif
#ifndef OutputDir
  #error OutputDir must be supplied by windows\build_windows.ps1.
#endif
#ifndef AppVersion
  #error AppVersion must be supplied by windows\build_windows.ps1.
#endif

[Setup]
AppId={{B8C2C5F7-2B2D-4F62-95B4-78D6F44C0501}
AppName=تسيير ومحاسبة العتاد
AppVersion={#AppVersion}
AppPublisher=تسيير ومحاسبة العتاد
AppMutex=Local\Materiel,Global\Materiel
DefaultDirName={autopf64}\Materiel
DefaultGroupName=تسيير ومحاسبة العتاد
OutputDir={#OutputDir}
OutputBaseFilename=Materiel-Setup
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=admin
CloseApplications=yes
RestartApplications=no
Uninstallable=yes
UninstallDisplayName=تسيير ومحاسبة العتاد
UninstallDisplayIcon={app}\Materiel.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
SetupLogging=yes

[Dirs]
Name: "{code:GetDataDir}"; Permissions: users-modify; Flags: uninsneveruninstall
Name: "{code:GetDataDir}\backups"; Flags: uninsneveruninstall

[Files]
; If this replaces an older installation, move its database to the durable data path only when that path is empty.
Source: "{app}\fleet_assets.db"; DestDir: "{code:GetDataDir}"; Check: ExistingInstallFileExists('fleet_assets.db'); Flags: external onlyifdoesntexist uninsneveruninstall
Source: "{app}\_internal\fleet_assets.db"; DestDir: "{code:GetDataDir}"; Check: ExistingInstallFileExists('_internal\fleet_assets.db'); Flags: external onlyifdoesntexist uninsneveruninstall
; Preserve image uploads from earlier package layouts. Existing user files always win.
Source: "{app}\static\uploads\*"; DestDir: "{code:GetDataDir}\uploads"; Check: ExistingInstallDirExists('static\uploads'); Flags: external onlyifdoesntexist recursesubdirs createallsubdirs uninsneveruninstall
Source: "{app}\_internal\static\uploads\*"; DestDir: "{code:GetDataDir}\uploads"; Check: ExistingInstallDirExists('_internal\static\uploads'); Flags: external onlyifdoesntexist recursesubdirs createallsubdirs uninsneveruninstall
; Create an external copy before any Alembic upgrade can change the installed database.
Source: "{code:GetDataDir}\fleet_assets.db"; DestDir: "{code:GetDataDir}\backups"; DestName: "{code:GetBackupName}"; Flags: external skipifsourcedoesntexist uninsneveruninstall
Source: "{#SourceDir}\Materiel.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceDir}\_internal\*"; DestDir: "{app}\_internal"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\تسيير ومحاسبة العتاد"; Filename: "{app}\Materiel.exe"; WorkingDir: "{app}"
Name: "{autoprograms}\إيقاف تسيير ومحاسبة العتاد"; Filename: "{app}\Materiel.exe"; Parameters: "--shutdown"; WorkingDir: "{app}"
Name: "{autodesktop}\تسيير ومحاسبة العتاد"; Filename: "{app}\Materiel.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "إنشاء اختصار على سطح المكتب"; GroupDescription: "الاختصارات:"; Flags: unchecked

[Run]
Filename: "{app}\Materiel.exe"; Description: "تشغيل تسيير ومحاسبة العتاد"; WorkingDir: "{app}"; Flags: postinstall nowait skipifsilent unchecked runasoriginaluser

[UninstallRun]
; Remove only the user identity and authentication data. The operational
; database and uploads live under GetDataDir and are never uninstalled.
; Materiel.exe reads the update marker written by Setup and skips this cleanup
; when the uninstaller is running as part of an upgrade.
Filename: "{app}\Materiel.exe"; Parameters: "--uninstall-cleanup"; Flags: runhidden waituntilterminated; RunOnceId: "RemoveMaterielUserAccounts"

[Code]
var
  UpdateMarkerWritten: Boolean;
  InstallationCompleted: Boolean;

function GetCurrentProcessId: DWORD; external 'GetCurrentProcessId@kernel32.dll stdcall';

function UpdateMarkerPath: String;
begin
  Result := ExpandConstant('{commonappdata}\Materiel\update-in-progress');
end;

procedure WriteUpdateMarker;
var
  MarkerDirectory, MarkerContent: String;
begin
  MarkerDirectory := ExtractFileDir(UpdateMarkerPath());
  if ForceDirectories(MarkerDirectory) then begin
    MarkerContent := IntToStr(GetCurrentProcessId()) + '|' +
      GetDateTimeString('yyyymmdd-hhnnss', '-', ':');
    UpdateMarkerWritten := SaveStringToFile(UpdateMarkerPath(), MarkerContent, False);
  end;
end;

procedure RemoveUpdateMarker;
begin
  if UpdateMarkerWritten then begin
    DeleteFile(UpdateMarkerPath());
    UpdateMarkerWritten := False;
  end;
end;

function PreviousInstallationExists: Boolean;
var
  FindRec: TFindRec;
begin
  Result := FindFirst(ExpandConstant('{app}') + '\unins*.exe', FindRec);
  if Result then
    FindClose(FindRec);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  { Remember that this run upgrades an existing installation.  The uninstaller
    checks the marker and preserves the user accounts if it is ever started
    while Setup is still running. }
  Result := '';
  if PreviousInstallationExists() then
    WriteUpdateMarker();
end;

procedure DeinitializeSetup;
begin
  if not InstallationCompleted then
    RemoveUpdateMarker();
end;

function DefaultDataDir: String;
var
  EnvDir: String;
begin
  EnvDir := Trim(GetEnv('MATERIEL_DATA_DIR'));
  if EnvDir <> '' then begin
    Result := EnvDir;
    Exit;
  end;
  Result := ExpandConstant('{commonappdata}\Materiel\data');
end;

function GetDataDir(Param: String): String;
var
  ConfigFile, ConfiguredDir: String;
  ConfiguredLines: TArrayOfString;
begin
  { This code constant may run before the application directory is initialized on a first install.
    WizardDirValue safely returns the selected or default install directory. }
  ConfigFile := WizardDirValue + '\materiel-data-dir.txt';
  if FileExists(ConfigFile) and LoadStringsFromFile(ConfigFile, ConfiguredLines) then begin
    if GetArrayLength(ConfiguredLines) > 0 then
      ConfiguredDir := Trim(ConfiguredLines[0]);
    if ConfiguredDir <> '' then begin
      Result := ConfiguredDir;
      Exit;
    end;
  end;
  Result := DefaultDataDir();
end;

function ExistingInstallFileExists(Param: String): Boolean;
begin
  Result := FileExists(WizardDirValue + '\' + Param);
end;

function ExistingInstallDirExists(Param: String): Boolean;
begin
  Result := DirExists(WizardDirValue + '\' + Param);
end;

function GetBackupName(Param: String): String;
begin
  Result := 'fleet_assets.before-update-' + GetDateTimeString('yyyymmdd-hhnnss', '-', ':') + '.db';
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ConfigFile, SplashDir, Parameters: String;
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then begin
    ConfigFile := ExpandConstant('{app}\materiel-data-dir.txt');
    if not FileExists(ConfigFile) then
      SaveStringToFile(ConfigFile, GetDataDir('') + #13#10, False);

    { Brand assets ship with the application. Standard users may read them,
      but only elevated administrators can replace them between releases. }
    SplashDir := ExpandConstant('{app}\_internal\splash-screen');
    Parameters := '"' + SplashDir + '" /inheritance:r /grant:r ' +
      '*S-1-5-18:(OI)(CI)F *S-1-5-32-544:(OI)(CI)F ' +
      '*S-1-5-32-545:(OI)(CI)RX /T /C';
    if not Exec(ExpandConstant('{sys}\icacls.exe'), Parameters, '', SW_HIDE,
      ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0) then
      RaiseException('تعذر حماية ملفات شاشة البداية من التعديل بعد التثبيت.');

    { Grant standard users explicit read/execute on existing bundled files.
      Inheritable permissions on the folder alone do not repair their ACLs. }
    Parameters := '"' + SplashDir + '\*" /grant:r *S-1-5-32-545:(RX) /T /C';
    if not Exec(ExpandConstant('{sys}\icacls.exe'), Parameters, '', SW_HIDE,
      ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0) then
      RaiseException('تعذر منح المستخدمين صلاحية قراءة ملفات شاشة البداية.');

    { The upgrade has finished copying the new release. Any uninstaller that
      ran as part of it has already seen the marker and preserved the users. }
    InstallationCompleted := True;
    RemoveUpdateMarker();
  end;
end;
