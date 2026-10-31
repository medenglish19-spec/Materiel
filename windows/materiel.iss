#ifndef SourceDir
  #error SourceDir must point to the PyInstaller onedir output.
#endif
#ifndef OutputDir
  #define OutputDir "D:\Materiel-release"
#endif
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{B8C2C5F7-2B2D-4F62-95B4-78D6F44C0501}
AppName=تسيير ومحاسبة العتاد
AppVersion={#AppVersion}
AppPublisher=تسيير ومحاسبة العتاد
DefaultDirName=D:\Materiel
DefaultGroupName=تسيير ومحاسبة العتاد
OutputDir={#OutputDir}
OutputBaseFilename=Materiel-Setup-{#AppVersion}
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
Source: "{app}\fleet_assets.db"; DestDir: "{code:GetDataDir}"; Check: FileExists(ExpandConstant('{app}\fleet_assets.db')); Flags: external onlyifdoesntexist uninsneveruninstall
Source: "{app}\_internal\fleet_assets.db"; DestDir: "{code:GetDataDir}"; Check: FileExists(ExpandConstant('{app}\_internal\fleet_assets.db')); Flags: external onlyifdoesntexist uninsneveruninstall
; Preserve image uploads from earlier package layouts. Existing user files always win.
Source: "{app}\static\uploads\*"; DestDir: "{code:GetDataDir}\uploads"; Check: DirExists(ExpandConstant('{app}\static\uploads')); Flags: external onlyifdoesntexist recursesubdirs createallsubdirs uninsneveruninstall
Source: "{app}\_internal\static\uploads\*"; DestDir: "{code:GetDataDir}\uploads"; Check: DirExists(ExpandConstant('{app}\_internal\static\uploads')); Flags: external onlyifdoesntexist recursesubdirs createallsubdirs uninsneveruninstall
; Create an external copy before any Alembic upgrade can change the installed database.
Source: "{code:GetDataDir}\fleet_assets.db"; DestDir: "{code:GetDataDir}\backups"; DestName: "{code:GetBackupName}"; Flags: external skipifsourcedoesntexist uninsneveruninstall
Source: "{#SourceDir}\Materiel.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceDir}\_internal\*"; DestDir: "{app}\_internal"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\تسيير ومحاسبة العتاد"; Filename: "{app}\Materiel.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\تسيير ومحاسبة العتاد"; Filename: "{app}\Materiel.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "إنشاء اختصار على سطح المكتب"; GroupDescription: "الاختصارات:"; Flags: unchecked

[Run]
Filename: "{app}\Materiel.exe"; Description: "تشغيل تسيير ومحاسبة العتاد"; WorkingDir: "{app}"; Flags: postinstall nowait skipifsilent unchecked runasoriginaluser

[Code]
function DefaultDataDir: String;
var
  EnvDir: String;
begin
  EnvDir := Trim(GetEnv('MATERIEL_DATA_DIR'));
  if EnvDir <> '' then begin
    Result := EnvDir;
    Exit;
  end;
  if DirExists('D:\') then
    Result := 'D:\MaterielData'
  else
    Result := ExpandConstant('{localappdata}\Materiel\data');
end;

function GetDataDir(Param: String): String;
var
  ConfigFile, ConfiguredDir: String;
  ConfiguredLines: TArrayOfString;
begin
  ConfigFile := ExpandConstant('{app}\materiel-data-dir.txt');
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
  end;
end;
