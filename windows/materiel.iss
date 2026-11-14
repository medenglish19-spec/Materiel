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
; The data directory is hardened after installation (see HardenDataDirectory).
; Do not grant BUILTIN\Users or Authenticated Users modify access here: the
; operator account, SYSTEM and Administrators are the only writers.
Name: "{code:GetDataDir}"; Flags: uninsneveruninstall
Name: "{code:GetDataDir}\backups"; Flags: uninsneveruninstall

[Registry]
; Remember the chosen data location so an update/reinstall finds it even when
; the sidecar file is missing. The value is intentionally kept on uninstall.
Root: HKCU; Subkey: "Software\Materiel"; ValueType: string; ValueName: "DataDir"; ValueData: "{code:GetDataDir}"; Flags: uninsneveruninstall
Root: HKLM; Subkey: "Software\Materiel"; ValueType: string; ValueName: "DataDir"; ValueData: "{code:GetDataDir}"; Flags: uninsneveruninstall

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
; A normal uninstall preserves the database, accounts, password hashes,
; roles, secret.key, uploads and backups. The command below only writes an
; audit log entry; erasing authentication data requires the separate,
; explicitly confirmed --uninstall-erase-data mode.
Filename: "{app}\Materiel.exe"; Parameters: "--uninstall-cleanup"; Flags: runhidden waituntilterminated; RunOnceId: "PreserveMaterielData"

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

function RegistryDataDir: String;
var
  ConfiguredDir: String;
begin
  Result := '';
  if RegQueryStringValue(HKCU, 'Software\Materiel', 'DataDir', ConfiguredDir) then
    Result := Trim(ConfiguredDir)
  else if RegQueryStringValue(HKLM, 'Software\Materiel', 'DataDir', ConfiguredDir) then
    Result := Trim(ConfiguredDir);
end;

function ExistingDataDir: String;
var
  Drives: String;
  Index: Integer;
  Candidate: String;
begin
  Result := '';
  { A custom location such as D:\MaterielData must survive an update even when
    materiel-data-dir.txt was lost. Only accept a folder that already contains
    real state, never an empty or unrelated directory. }
  Drives := 'CDEFGHIJKLMNOPQRSTUVWXYZ';
  for Index := 1 to Length(Drives) do begin
    Candidate := Copy(Drives, Index, 1) + ':\MaterielData';
    if FileExists(Candidate + '\fleet_assets.db') or
       FileExists(Candidate + '\secret.key') then begin
      Result := Candidate;
      Exit;
    end;
  end;
  Candidate := ExpandConstant('{commonappdata}\Materiel\data');
  if FileExists(Candidate + '\fleet_assets.db') or
     FileExists(Candidate + '\secret.key') then
    Result := Candidate;
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

  ConfiguredDir := RegistryDataDir();
  if (ConfiguredDir <> '') and DirExists(ConfiguredDir) then begin
    Result := ConfiguredDir;
    Exit;
  end;

  ConfiguredDir := ExistingDataDir();
  if ConfiguredDir <> '' then begin
    Result := ConfiguredDir;
    Exit;
  end;

  Result := DefaultDataDir();
end;

function CurrentUserAccount: String;
var
  Domain, UserName: String;
begin
  Domain := Trim(GetEnv('USERDOMAIN'));
  UserName := Trim(GetEnv('USERNAME'));
  if Domain <> '' then
    Result := Domain + '\' + UserName
  else
    Result := UserName;
end;

procedure RunIcacls(const Parameters: String);
var
  ResultCode: Integer;
begin
  if not Exec(ExpandConstant('{sys}\icacls.exe'), Parameters, '', SW_HIDE,
    ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0) then
    RaiseException('تعذر تأمين صلاحيات مجلد البيانات.');
end;

procedure ResetChildAcls(const Dir: String);
begin
  { icacls /inheritance:r together with /T protects every traversed child but
    only writes the inheritable grants to the directory. Files would be left
    with an empty DACL (nobody can read them). Apply the policy to the
    directory first, then reset children so they inherit exactly those ACEs. }
  RunIcacls('"' + Dir + '\*" /reset /T /C /Q');
end;

procedure HardenDataDirectory;
var
  DataDir, Parameters, Account: String;
begin
  DataDir := GetDataDir('');
  if not DirExists(DataDir) then
    Exit;

  { Remove explicit/inherited access (including BUILTIN\Users and Authenticated
    Users modify rights) and grant only SYSTEM, Administrators and the
    installing operator. SQLite side files inherit these permissions when they
    are created, so -wal/-shm files and future uploads stay private too. }
  Parameters := '"' + DataDir + '" /inheritance:r /remove:g ' +
    '*S-1-5-32-545 *S-1-5-11 /grant:r ' +
    '*S-1-5-18:(OI)(CI)F *S-1-5-32-544:(OI)(CI)F';
  Account := CurrentUserAccount();
  if Account <> '' then
    Parameters := Parameters + ' "' + Account + '":(OI)(CI)M';

  RunIcacls(Parameters);
  ResetChildAcls(DataDir);
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
begin
  if CurStep = ssPostInstall then begin
    ConfigFile := ExpandConstant('{app}\materiel-data-dir.txt');
    if not FileExists(ConfigFile) then
      SaveStringToFile(ConfigFile, GetDataDir('') + #13#10, False);

    { Stop granting broad write access to the operational data. }
    HardenDataDirectory;

    { Brand assets ship with the application. Standard users may read them,
      but only elevated administrators can replace them between releases. }
    SplashDir := ExpandConstant('{app}\_internal\splash-screen');
    Parameters := '"' + SplashDir + '" /inheritance:r /remove:g ' +
      '*S-1-5-32-545 *S-1-5-11 /grant:r ' +
      '*S-1-5-18:(OI)(CI)F *S-1-5-32-544:(OI)(CI)F ' +
      '*S-1-5-32-545:(OI)(CI)RX';
    RunIcacls(Parameters);
    ResetChildAcls(SplashDir);

    { The upgrade has finished copying the new release. Any uninstaller that
      ran as part of it has already seen the marker and preserved the users. }
    InstallationCompleted := True;
    RemoveUpdateMarker();
  end;
end;
