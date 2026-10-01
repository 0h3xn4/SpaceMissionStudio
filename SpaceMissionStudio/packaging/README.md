# Packaging

This directory covers packaging SpaceMissionStudio into a real, installable,
out-of-the-box application for both Linux and Windows -- not just a
`pip install` a developer runs from a terminal. Two tiers exist for each
platform:

1. **A real double-click installer** -- a `.deb` package on Linux
   (`build_deb.sh`), an Inno Setup wizard on Windows
   (`windows/spacemissionstudio.iss`). No terminal, no typed `pip`/`venv`
   commands for the end user: install, get a menu entry, click it, done.
2. **The scriptable install path** (`build_wheel.sh`/`install.sh` and
   their `.ps1` counterparts) these installers are themselves built on
   top of -- still useful directly for anyone who'd rather script an
   install or doesn't want a system-wide package manager entry.

**A real update, made while building the `.deb` installer above:** this
development sandbox's Basilisk story has changed since earlier sections
of this file (and `../HISTORY.md`) were written. `pip install "bsk[all]"`
(Basilisk's own published PyPI wheel) now genuinely installs here --
confirmed directly, not assumed, by actually running it and then running
a real Basilisk build's `printBuildInfo()`. What's STILL blocked in this
sandbox specifically is network access to the NAIF SPICE kernel host
(`naif.jpl.nasa.gov`) and its backup mirror, needed for an actual
simulation RUN past kernel loading -- a narrower, later gap than "no
Basilisk at all". See "The `.deb` package" below for exactly what this
made possible to verify end-to-end for the first time.

## What's here

* **`build_wheel.sh`** -- builds `spacemissionstudio`'s own wheel + sdist
  (`python -m build`). Genuinely run here: `dist/spacemissionstudio-<version>-py3-none-any.whl`
  was built, installed into a throwaway venv, and its CLI entry point
  (`spacemissionstudio validate ...`) and GUI (`spacemissionstudio.gui.main_window.MainWindow`,
  constructed headless) were both exercised against the INSTALLED copy,
  not the checkout.

  A real bug was caught doing this: `spacemissionstudio/scenarios/*.json` (the
  two-body validation scenario) was silently missing from the built wheel,
  because `setuptools.packages.find()` only picks up Python packages
  (directories with `__init__.py`), and `scenarios/` has none. Fixed via
  `pyproject.toml`'s `[tool.setuptools.package-data]` -- re-verified by
  rebuilding and confirming the file is now present in the wheel and
  loadable from the installed copy.

  A second real bug was caught running this script TWICE in a row:
  `python -m build`'s own temp output directory (`./build/`, gitignored)
  is left behind after a run, and because Python inserts the current
  directory at the front of `sys.path` for both `-c` and `-m` invocations,
  that leftover directory silently SHADOWED the real installed `build`
  package on the next run (`ModuleNotFoundError`-adjacent: `No module
  named build.__main__`). Fixed by having the script clean `./build/`
  before it starts, and by checking installedness with `pip show build`
  instead of `python -c "import build"` (which was itself vulnerable to
  the same shadowing). Re-verified by running the script twice
  back-to-back after the fix.

* **`install.sh`** -- an end-user installer: creates a private venv,
  builds (or accepts) a spacemissionstudio wheel and installs it with the
  `gui` extra, optionally installs a vendored Basilisk wheel into the same
  venv (`--basilisk-wheel PATH_OR_URL`), writes a `spacemissionstudio` launcher
  script, and installs a `~/.local/share/applications/spacemissionstudio.desktop`
  entry (skippable with `--no-desktop-entry`). Genuinely run here TWICE in
  a row (the regression check for the bug above) with a fake `$HOME`/
  `$XDG_DATA_HOME`, confirming: the venv installs cleanly, the launcher
  script's `spacemissionstudio validate` works against the installed scenario
  file, and the desktop entry is written with the correct `Exec=` path.
  **The `--basilisk-wheel` path itself is now ALSO genuinely verified**
  (re-run while building the `.deb` package below, once PyPI turned out
  to be reachable from this sandbox after all --
  `./install.sh --basilisk-wheel "bsk[all]"` installed a real Basilisk
  build end-to-end and the launcher's `spacemissionstudio validate` worked
  against it), not just asserted to be "ordinary, non-spacemissionstudio
  -specific `pip` behavior" as an earlier revision of this note had to
  settle for.

* **`spacemissionstudio.desktop.in`** -- the desktop-entry template `install.sh`
  fills in (`@INSTALL_PREFIX@` -> the venv's parent directory).
  `Icon=spacemissionstudio` now resolves to a real icon: `install.sh` renders
  `gui/icons.py`'s procedurally-drawn app icon (QPainter, no bitmap asset
  in the repo -- see that module's docstring) to
  `$XDG_DATA_HOME/icons/hicolor/256x256/apps/spacemissionstudio.png` (the
  standard hicolor icon theme location) right after writing the desktop
  entry, using the `offscreen` Qt platform plugin so no display is needed
  even on a headless install. Non-fatal if it fails (e.g. no Qt platform
  plugins present at all) -- the desktop entry still installs, just with
  the icon theme's generic fallback.

## The real installers

### The `.deb` package (Linux)

`build_deb.sh` produces `spacemissionstudio_<version>_all.deb` -- a real
Debian/Ubuntu package. It bundles SpaceMissionStudio's own wheel (built the
same way `build_wheel.sh` always has) plus a small set of maintainer
scripts (`deb/DEBIAN/postinst`/`prerm`/`postrm`) and a desktop entry
(`deb/usr/share/applications/spacemissionstudio.desktop`); it does NOT bundle
Basilisk itself (see "The vendoring decision" below for why not) --
`postinst` creates a dedicated virtualenv at `/opt/spacemissionstudio/venv`
and pip-installs `bsk[all]` there the moment the package is configured
(`apt install`/`dpkg -i`'s normal "configure" step), which needs
internet access on the installing machine.

**Genuinely built AND installed for real in this project's development
sandbox** -- this is the first time ANY Basilisk-dependent path in this
whole project has been exercised against a real Basilisk build from
inside the sandbox itself, not just written carefully against verified
API sequences:

```bash
./build_deb.sh                       # -> dist/spacemissionstudio_1.0.0_all.deb
sudo apt install ./dist/spacemissionstudio_1.0.0_all.deb
```

ran end-to-end with no errors: the venv was created, `bsk[all]` installed
for real from PyPI (confirmed with a real build's own `printBuildInfo()`),
SpaceMissionStudio installed from the bundled wheel, the `/usr/bin/spacemissionstudio`
launcher and the desktop entry + a real rendered PNG icon were all
written correctly. `spacemissionstudio validate` against a real bundled
scenario file, and `spacemissionstudio kernels-status`, were both run against
the installed copy afterward and behaved exactly as expected -- including
`kernels-status` correctly reporting the NAIF SPICE kernel host as
unreachable, this sandbox's one remaining, already-documented network
gap (see the note at the top of this file), not a bug in the package.

Went further: `SpaceMissionStudio`'s own real `pytest` suite was then run from
the installed venv (`/opt/spacemissionstudio/venv/bin/python3 -m pytest tests/`)
against this real Basilisk build. Every test up through
`tests/test_mission_engine.py` passed genuinely -- hundreds of tests,
including every Basilisk-IMPORTING module that doesn't need an actual
kernel-loaded simulation run (schema, GUI, link budget, logging,
constellation generation, and more) -- confirmed real, not the
auto-skip-without-Basilisk path this suite normally takes. It only starts
failing exactly at the tests that DO need kernel loading
(`test_mission_engine.py`, `test_two_body_validation.py`, and similar),
and for exactly the expected reason: the agent proxy's own connection log
for that run shows rejected `CONNECT` attempts to `naif.jpl.nasa.gov` and
`celestrak.org` specifically -- the same already-documented network gap,
not a new or different problem.

Uninstalling (`apt remove`/`apt purge spacemissionstudio`) correctly removes
the venv and rendered icon too (`postrm`) -- these aren't part of the
package's own tracked payload (they're created at configure time), so
without `postrm` they'd survive an uninstall silently.

**1.1.0 release note**: `build_deb.sh` was re-run for the 1.1.0 release
and still produces a valid, installable `spacemissionstudio_1.1.0_all.deb`
(`dpkg-deb --build` succeeds; the version string above comes from
`spacemissionstudio.__version__`, never hardcoded, so this needed no script
change). The full real-Basilisk install/test pass described above was
not independently re-run against that specific 1.1.0 artifact this
release -- it was run once, at 1.0.0, against install logic that hasn't
changed since.

**2.0.0 release note**: the 2.0.0 bump is the missionStudio ->
SpaceMissionStudio rename (see README.md's "Version 2.0.0" for the full
list of what changed) -- a new package/command/installer identity, not
new install LOGIC. `build_deb.sh` was re-run again under the renamed
package and still produces a valid, installable
`spacemissionstudio_2.0.0_all.deb`; the real-Basilisk install/test pass
has still only been run once, at 1.0.0, against logic that is unchanged
through both the 1.1.0 feature release and this rename.

### The Windows installer (Inno Setup)

`windows/spacemissionstudio.iss` is an [Inno Setup](https://jrsoftware.org/isinfo.php)
script producing `spacemissionstudio-<version>-setup.exe`: a real wizard --
Welcome, license, install-location, Install, an optional "launch now"
checkbox on Finish -- built on the exact same idea as the `.deb` above
(bundle SpaceMissionStudio's own wheel, create a venv, pip-install `bsk[all]`
at install time) via a companion script (`windows/bootstrap_env.ps1`)
the installer's `[Run]` step invokes. It checks for a working `python`
on `PATH` before the wizard even starts, and guides the user to
python.org (rather than failing silently) if none is found. Installs
per-user (`{localappdata}`, no admin/UAC prompt needed), and creates a
Start Menu entry (plus an optional desktop shortcut) that launches the
GUI directly via `pythonw.exe` (no console-window flash).

Building it (on a real Windows machine, with Inno Setup installed):

```powershell
cd SpaceMissionStudio
powershell -File packaging\build_wheel.ps1 packaging\windows\dist
ISCC packaging\windows\spacemissionstudio.iss
```

**NOT compiled or run** -- Inno Setup is Windows-only software with no
equivalent in this Linux-only development sandbox, unlike the `.deb`
above. Written carefully against Inno Setup's documented, stable script
syntax and `install.ps1`'s own already-written logic, but flagged here
rather than claimed as verified; please report any issues building or
running this on a real Windows 11 machine.

## Windows support (the scriptable install path)

Not the Inno Setup wizard above -- this is `build_wheel.ps1`/`install.ps1`,
the Windows counterpart of `build_wheel.sh`/`install.sh` (tier 2 from the
top of this file: scriptable, for anyone who'd rather not use a GUI
installer). Added for the 1.0.0 release, direct PowerShell ports --
same steps, same flags (`-Prefix`/`-BasiliskWheel`/`-SpaceMissionStudioWheel`/`-NoShortcut`
instead of `--prefix`/`--basilisk-wheel`/`--spacemissionstudio-wheel`/
`--no-desktop-entry`), same two already-verified bugs from the Linux
side pre-emptively fixed (the `scenarios/*.json` package-data glob is in
`pyproject.toml`, platform-independent; the stale-`./build/`-directory
shadowing fix is ported into `build_wheel.ps1` unchanged, since it's
about `python -m build`'s own behavior, not the shell). Windows'
equivalent of a `.desktop` entry is a Start Menu shortcut (`.lnk`),
created via the standard `WScript.Shell` COM object at
`%APPDATA%\Microsoft\Windows\Start Menu\Programs\SpaceMissionStudio.lnk`.

**Honesty note, matching this project's own discipline elsewhere:**
these two scripts have NOT been run against a real Windows 11 machine --
this development sandbox is Linux-only, with no Windows environment
available at any point in this project's history. They were written
against documented, standard PowerShell/`venv`/`pip`/`WScript.Shell`
behavior and against `build_wheel.sh`/`install.sh`'s own
already-verified logic (matched step-for-step), and reviewed for syntax
by hand since no `pwsh`/`powershell.exe` was available in this sandbox
to actually execute them either -- but "written carefully" is not the
same claim as "run and confirmed working" that the rest of this
directory makes for the Linux scripts. One specific, known gap: the
Start Menu shortcut does not get a custom icon (`gui/icons.py`'s
`ensure_icon_file()` always writes PNG data -- see that function's own
docstring -- and a `.lnk`'s `IconLocation` needs a real `.ico`/`.exe`/
`.dll`; rather than ship an icon file that wouldn't actually resolve,
the shortcut just uses `spacemissionstudio.exe`'s own embedded icon). If you
run these on a real Windows 11 machine, please report anything that
doesn't work as documented here.

## The vendoring decision (why Basilisk isn't bundled inside the installers)

Flagged since Phase 0's README: **vendor a prebuilt Basilisk wheel pinned
to a specific release/commit** as the default install path for end users,
keeping "build Basilisk from source" a documented, opt-in developer path
only. Building from source in an automated/sandboxed context is fragile
-- this project hit exactly that failure mode (a Conan Center network
block) before Phase 0 even started, and that specific block is STILL true
of this development sandbox today.

That's no longer the whole picture, though (corrected here, since an
earlier revision of this section conflated "can't build Basilisk from
source" with "no Basilisk wheel available at all" -- they turned out to
be two different things): AVS Lab already publishes Basilisk's wheel to
PyPI (`pip install "bsk[all]"`), and PyPI IS reachable from this
sandbox -- confirmed directly while building the `.deb` package above,
not assumed. So "vendor a Basilisk wheel" no longer needs a from-source
build at all; every installer in this directory (`install.sh`/`.ps1`,
the `.deb`, the Inno Setup installer) gets Basilisk the same simple way:
`pip install "bsk[all]"` at install time, needing only ordinary internet
access, not a Basilisk build toolchain anywhere.

What's genuinely still NOT done here: actually bundling a Basilisk
`.whl` FILE inside an installer (so install works fully offline, with no
PyPI access needed at all) -- `pip download "bsk[all]"` would produce
one, but doing that for every dependency, embedding the result, and
testing the fully-offline path is real, separate follow-on work, not
attempted blind here. `install.sh`/`install.ps1`'s `--basilisk-wheel`/
`-BasiliskWheel` flag already accepts a local `.whl` file for exactly
this purpose whenever someone does produce one (a pinned/older release,
a custom build, or an offline bundle) -- that RECEIVING end was already
built and (on Linux) verified; only producing the bundled file itself is
the open item.

## Producing a full offline installable bundle

Not built yet: the natural next step, now that "the vendored Basilisk
wheel" is just `pip download "bsk[all]"` away (see above), is doing
exactly that -- plus SpaceMissionStudio's own dependencies -- into a local
directory (`--no-deps` per package, or a `requirements.txt` with hashes)
so `install.sh`/the `.deb`/the Windows installer can all run fully
offline, with no PyPI access needed at install time. Flagged here rather
than attempted blind, per this project's "don't fabricate what can't be
verified" discipline -- the pieces (a bundled SpaceMissionStudio wheel, a
working `--basilisk-wheel`/`-BasiliskWheel` receiving end) are already
in place; only the "download everything into one bundle" step is
missing.
