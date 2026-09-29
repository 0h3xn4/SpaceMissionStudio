; missionStudio Windows installer -- Inno Setup script.
;
; A real installer wizard: no terminal, no typed pip/venv commands for the
; end user. Double-click missionstudio-setup.exe, click through Welcome ->
; License -> install location -> Install, and get a Start Menu (and
; optional Desktop) shortcut that launches the GUI directly.
;
; What it does NOT avoid: this still needs (1) a system Python 3.9+
; already installed (checked before the wizard even starts -- see
; InitializeSetup below -- with a guided prompt to python.org if missing,
; not a silent failure) and (2) internet access during setup, to
; pip-install Basilisk ("bsk[all]") from PyPI, the one dependency this
; installer cannot practically bundle (a multi-hundred-MB compiled wheel
; with mujoco/rust bits -- see ../README.md's "The vendoring decision").
; missionStudio itself IS bundled (its own wheel, pure Python, no network
; needed for that part) -- see [Files] below.
;
; This mirrors ../install.ps1's own logic almost exactly (same venv
; -under-the-install-dir approach, same "bsk[all]" + bundled-wheel[gui]
; install sequence -- see packaging/windows/bootstrap_env.ps1, which IS
; that logic, trimmed for a fixed non-interactive install directory), just
; wrapped in a GUI wizard instead of a script the user runs from a
; terminal.
;
; Building this installer (on a real Windows machine, with Inno Setup
; https://jrsoftware.org/isinfo.php installed -- ISCC.exe on PATH):
;
;   1. Build missionStudio's own wheel into packaging\windows\dist\:
;        cd missionStudio
;        powershell -File packaging\build_wheel.ps1 packaging\windows\dist
;   2. Compile this script:
;        ISCC packaging\windows\missionstudio.iss
;      -> packaging\windows\Output\missionstudio-1.0.0-setup.exe
;
; Verification status: written carefully against Inno Setup's documented,
; stable script syntax and packaging/install.ps1's own already-written
; (though itself not yet run-on-real-Windows) logic, but NOT compiled or
; run -- Inno Setup is Windows-only software with no equivalent in this
; project's own (Linux-only) development sandbox. Flagged here rather
; than claimed as verified; please report any issues building or running
; this on a real Windows 11 machine. See packaging/README.md's "Windows
; support" section for the full picture, including what HAS been
; genuinely tested (the Linux .deb installer, end-to-end, with real
; Basilisk, in this project's own sandbox).

#define MyAppName "missionStudio"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "missionStudio contributors"
#define MyAppURL "https://github.com/AVSLab/basilisk"

[Setup]
; A fixed, random GUID identifying this application across upgrades --
; generated once for this project; do not reuse for a different app.
AppId={{B96F3E9D-6C0B-4C61-9C1E-8B9E3E5B6F7A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
; Installs under the current user's local app data by default -- no admin
; rights/UAC prompt needed, matching install.ps1's own default
; ($env:LOCALAPPDATA\missionstudio) and philosophy (a per-user tool, not
; a system-wide one).
DefaultDirName={localappdata}\missionStudio
DefaultGroupName=missionStudio
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
LicenseFile=..\..\LICENSE
OutputDir=Output
OutputBaseFilename=missionstudio-{#MyAppVersion}-setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
; Basilisk publishes wheels for Windows 10/11 (x86_64) specifically (see
; ../../docs/source/Install.rst's "Prebuilt wheel availability" table) --
; this installer targets the same.
MinVersion=10.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
; The wheel this installer bundles -- built separately, ahead of
; compiling this script; see the header comment above. Wildcarded so a
; version bump here needs no edit to this script.
Source: "dist\missionstudio-*.whl"; DestDir: "{app}\dist"; Flags: ignoreversion
Source: "bootstrap_env.ps1"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; missionstudio.exe (the [project.scripts] console entry point pip
; installs into the venv) is a CONSOLE-mode executable -- launching it
; directly would flash a console window. pythonw.exe (the venv's own
; windowless Python interpreter) running the same CLI module instead
; gives a normal, console-free GUI launch, the same fix
; packaging/install.ps1's own launcher note documents for the same
; reason.
Name: "{group}\missionStudio"; Filename: "{app}\venv\Scripts\pythonw.exe"; Parameters: "-m missionstudio.cli gui"; WorkingDir: "{app}"; IconFilename: "{app}\venv\Scripts\python.exe"
Name: "{group}\Uninstall missionStudio"; Filename: "{uninstallexe}"
Name: "{autodesktop}\missionStudio"; Filename: "{app}\venv\Scripts\pythonw.exe"; Parameters: "-m missionstudio.cli gui"; WorkingDir: "{app}"; IconFilename: "{app}\venv\Scripts\python.exe"; Tasks: desktopicon

[Run]
; The actual environment setup -- see bootstrap_env.ps1's own docstring.
; Not "runhidden": left visible (a console window) so the user sees SOME
; feedback during what can be several minutes of PyPI downloads, rather
; than an installer that looks frozen. ExecutionPolicy Bypass is scoped
; to this one process only (the -File invocation), not a system-wide
; policy change.
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\bootstrap_env.ps1"" -InstallDir ""{app}"""; StatusMsg: "Installing Python packages (needs internet access, can take a few minutes)..."; Flags: waituntilterminated
Filename: "{app}\venv\Scripts\pythonw.exe"; Parameters: "-m missionstudio.cli gui"; WorkingDir: "{app}"; Description: "Launch missionStudio now"; Flags: postinstall skipifsilent nowait unchecked

[UninstallDelete]
; The venv (and everything pip installed into it, Basilisk included) is
; created by bootstrap_env.ps1 at install time, not tracked in [Files],
; so the uninstaller needs telling explicitly to remove it too -- same
; reasoning as the .deb package's postrm script.
Type: filesandordirs; Name: "{app}\venv"
Type: filesandordirs; Name: "{app}\dist"

[Code]
function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
begin
  Result := True;
  // Checks that SOME python.exe resolves on PATH and actually runs --
  // the same check bootstrap_env.ps1 itself implicitly relies on
  // (`python -m venv`). Does not parse/enforce the exact version (3.9+):
  // Inno Setup's Exec() doesn't capture stdout without extra plumbing,
  // and every actively-supported Python release today already clears
  // 3.9, so this is a practical, not exhaustive, check -- if it resolves
  // to something too old, pip itself will fail with a clear version
  // error during the [Run] step instead of silently misbehaving.
  if not Exec('cmd.exe', '/C python --version', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0) then
  begin
    if MsgBox('missionStudio needs Python 3.9 or later, which was not found on this system (or not on PATH).' + #13#10 + #13#10 +
              'Click OK to open the Python download page, then re-run this installer after installing it -- make sure to check "Add python.exe to PATH" during Python''s own setup.',
              mbError, MB_OKCANCEL) = IDOK then
      ShellExec('open', 'https://www.python.org/downloads/', '', '', SW_SHOWNORMAL, ewNoWait, ResultCode);
    Result := False;
  end;
end;
