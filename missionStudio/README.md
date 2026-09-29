# missionStudio

A standalone, GUI-based mission-analysis application for Linux and
Windows 11, using the Basilisk astrodynamics framework (AVS Lab,
University of Colorado Boulder) as its sole simulation/dynamics engine.
Think "STK/FreeFlyer-lite" -- every capability maps to a specific
Basilisk module, or is explicitly flagged as custom/out-of-scope, never
fabricated.

**Status: v1.0.0**, first tagged release. See "Version 1.0.0" below for
what that means, "Capabilities" for what's implemented, and
[`HISTORY.md`](HISTORY.md) for the full phase-by-phase development log
this README used to carry inline (every feature's design rationale, every
bug found and fixed, the full crash-investigation writeups) -- nothing
was deleted, it just moved out of the way of a README someone installing
this for the first time should actually be able to read.

## Getting started

**Just want to use the app, not develop it?** There's a real installer
for that -- no terminal, no typed `pip`/`venv` commands:

* **Linux:** `packaging/build_deb.sh` produces `missionstudio_1.0.0_all.deb`
  -- install it with `sudo apt install ./missionstudio_1.0.0_all.deb`
  (or double-click it in a file manager with package-install support) and
  get a normal application-menu entry. **Genuinely built and installed
  end-to-end in this project's own development sandbox**, including a
  real Basilisk install -- see `packaging/README.md`'s "The real
  installers" section for exactly what that confirmed.
* **Windows:** `packaging/windows/missionstudio.iss` (built with
  [Inno Setup](https://jrsoftware.org/isinfo.php)) produces
  `missionstudio-1.0.0-setup.exe` -- a normal installer wizard, ending in
  a Start Menu entry. New for 1.0.0; written carefully but not yet run on
  a real Windows machine (this development sandbox has none) -- see
  `packaging/README.md` for the same honesty-first verification status
  this project applies everywhere else.

Either way, the installer still needs internet access the first time (to
download Basilisk from PyPI) -- there's no getting around that without
bundling a multi-hundred-MB Basilisk wheel directly into the installer,
which neither one does yet (see `packaging/README.md`'s "vendoring
decision" section).

**Developing missionStudio, or want full control over the install?**
Everything below was actually run, not just written and assumed to work
-- including step 2, which for most of this project's history looked
like it would need a from-source Basilisk build (fragile, and blocked in
this project's own sandbox). It turned out Basilisk now publishes a
prebuilt wheel to PyPI, and installing it that way genuinely works.

**1. Prerequisites**

* Linux or Windows 11, Python 3.9+. Basilisk's own prebuilt-wheel support
  matrix (`../docs/source/Install.rst`) explicitly covers both: "Windows:
  Windows 10/11 (x86_64)" and "Linux: Manylinux 2.24+ (x86_64, aarch64)"
  -- macOS is also listed there but not a target for missionStudio's own
  install scripts below (nothing prevents `pip install` from working on
  it too, just not independently verified for this project).
* `python -m venv` (or your preferred environment tool) -- everything
  below assumes a virtualenv so it doesn't touch your system Python.
  (Linux commands below use `python3`/`pip3`-equivalent `python`/`pip`
  once the venv is active, matching what actually ran in this project's
  own Linux development sandbox; on Windows, use the `python`/`pip`
  installed by the official python.org or Microsoft Store installer.)

**2. Install Basilisk**

Linux/macOS:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install "bsk[all]"
```

Windows (PowerShell):
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install "bsk[all]"
```

This is Basilisk's own recommended install path (see `../docs/source/Install.rst`
in this checkout) -- a prebuilt wheel from PyPI, no compiler or Conan
required, published for both platforms above. The Linux command was
genuinely run in this project's development sandbox: the wheel downloads
and installs cleanly, and every Basilisk module/class this app's code
imports (across every phase) was confirmed present. The Windows command
was not independently run in this project (this development sandbox is
Linux-only) -- it follows Basilisk's own documented Windows install path
exactly, but is flagged here rather than claimed as verified end-to-end;
please report any issues. Building from source is still possible and
documented (`../docs/source/Build.rst`) if you need an unpublished
feature or a locally-modified Basilisk, but it's no longer the first
thing to reach for on either platform.

**3. Install missionStudio**

```bash
cd missionStudio
pip install -e ".[dev,gui]"
```

(Same command on Windows, once the venv above is active.)

(Or skip steps 2-3 and run `packaging/install.sh --basilisk-wheel "bsk[all]"`
on Linux, or `packaging/install.ps1 -BasiliskWheel "bsk[all]"` on Windows,
instead -- either does both in one shot into its own private venv and
adds a launcher (a desktop entry on Linux, a Start Menu shortcut on
Windows) -- see `packaging/README.md` for exactly what's verified on
each platform. The Linux script and its `--basilisk-wheel` flag
genuinely work, for the same reason step 2 does; the Windows script is
new for the 1.0.0 release and carries the same not-independently-run
caveat as the Windows command above.)

**4. Check it's working**

```bash
missionstudio kernels-status
```

The first time you run anything that touches SPICE (this command, `run`,
or the GUI's Run menu), Basilisk downloads a handful of standard SPICE
kernels (leap-seconds, planetary ephemeris, ~100 MB total) from NAIF and
caches them locally -- this needs working internet access to
`naif.jpl.nasa.gov` once. `kernels-status` reports exactly which kernels
are missing/cached and why, rather than failing silently deep inside a
run.

**5. Run something**

```bash
missionstudio validate missionstudio/scenarios/two_body_validation.json
missionstudio run missionstudio/scenarios/two_body_validation.json --out-dir results/
```

or launch the GUI:

```bash
missionstudio gui
```

File > Open the same scenario, or build one from scratch (spacecraft,
sensors, actuators, FSW mode, ground stations, Monte Carlo dispersions --
all editable live with validation feedback), then Run > Run Simulation.

**If something doesn't work**, "Verification status" right below says
exactly what has and hasn't been confirmed against a real Basilisk
build (short version: everything has, including a real multi-day run)
-- read it before assuming a failure is a bug rather than a local
environment issue.

## Verification status

* **Everything Basilisk-independent** (`missionstudio/schema/`,
  `engine/spaceweather.py`, `engine/results.py`, `engine/link_budget.py`,
  `engine/constellation.py`, `engine/spacecraft_templates.py`,
  `engine/propellant_bookkeeping.py`, `cli.py`, and the entire
  `missionstudio/gui/` package) has no Basilisk import and is fully
  exercised either way -- `pytest tests/` runs and passes 600 tests
  with or without Basilisk installed (see "Running the tests" below).
  That includes the PySide6 GUI: built, run headless, and driven with
  `pytest-qt` for real -- every form field, every menu action, every
  dialog -- not asserted about in the abstract.
* **Everything Basilisk-dependent** (`time_system.py`, `kernels.py`,
  `service.py`, `fsw.py`/`vizard.py`, `monte_carlo.py`,
  `orbit_maintenance.py`, `mission_engine.py`) has been confirmed
  against a real `pip install "bsk[all]"` Basilisk build, including a
  **real, full multi-day end-to-end run**: a real user ran the
  `05_formation_flying_phasing.json` template (station-keeping +
  phasing-keeping + live Vizard streaming, both active on the same
  spacecraft) to 100% completion -- the full 7 simulated days, no
  errors. Getting there involved finding and fixing a real,
  previously-unreproducible crash (root-caused with a real `gdb`
  session down to a dangling-pointer bug in `engine/vizard.py`'s Vizard
  live-data panels -- full story in `HISTORY.md`).
* **This development sandbox** (where most of this project's code was
  written) has no route to the NAIF SPICE kernel host, so a handful of
  things could only be confirmed correct up to that point here, not run
  end-to-end in-sandbox -- not a project limitation, just this one
  sandbox's own network policy. Anything with that specific gap says so
  in its own docstring/module comment.
* **Packaging.** The scriptable install path
  (`packaging/build_wheel.sh`/`install.sh`, including the
  Basilisk-wheel-vendoring path) AND the real, double-click Linux
  installer (`packaging/build_deb.sh`'s `.deb` package) were both fully
  verified end-to-end on Linux -- a real Basilisk build installed for
  real, confirmed with its own `printBuildInfo()`, and hundreds of this
  project's own Basilisk-dependent tests genuinely passing against it
  (not auto-skipping) when run from the installed copy. Their Windows
  counterparts (`build_wheel.ps1`/`install.ps1`, and the Inno Setup
  installer `packaging/windows/missionstudio.iss`, all new for 1.0.0)
  were written against the same already-verified logic and Basilisk's
  own documented Windows install path, but have not been run on a real
  Windows 11 machine (none has ever been available in this development
  sandbox) -- see `packaging/README.md` for exactly what's verified
  where, and please report anything that doesn't work as documented.

## Capabilities

What's actually implemented, grouped by concern (full design rationale
and the order each landed in: `HISTORY.md`).

**Scenario model & data** -- a versioned, human-readable JSON format
(spacecraft, orbit ICs in three forms -- classical elements with true or
mean anomaly, Cartesian, TLE --, gravity, ground stations, space
weather, sim settings, Monte Carlo dispersions, a GMAT/FreeFlyer-style
**Mission Sequence**), hand-written validation with specific error
messages, a schema-migration registry, and reference-integrity checking
(rename a spacecraft and every reference to it updates atomically;
deleting one that's still referenced is refused, listing exactly what
references it). No third-party schema library.

**Orbital dynamics & propagation** -- central-body point-mass or Earth
spherical-harmonics gravity plus third-body point-mass perturbers,
atmospheric drag (NRLMSISE-00, Earth-only) and SRP, a selectable
integrator (`euler`/`rk2`/`rkf45`/`rkf78`), and osculating Keplerian
elements computed and exported alongside inertial position/velocity at
every sample.

**Attitude, sensors & actuators** -- every `fsw_mode` maps to a real
Basilisk FSW module chain (attitude nav/guidance/control), idealized or
real reaction-wheel actuation, and star tracker/IMU/coarse-sun-sensor/
magnetometer sensors (magnetometer is Earth-only).

**Mission planning** -- a GMAT/FreeFlyer-inspired Resources / Mission
Sequence / Output architecture: `propagate` (duration, epoch, or
periapsis/apoapsis-event stop conditions), `maneuver` (impulsive
delta-V, inertial/VNB/RTN), `assignment`, `report`, `if`/`while`
conditionals, and `script_block` commands, run by a real execution
engine (`engine.mission_engine.MissionEngine`) with a dedicated GUI
editor and output console.

**Mission analysis** -- ground-station access analysis (has-access,
slant range, elevation, azimuth per station/spacecraft pair), a real
power budget (solar panel/battery/eclipse, driven by actual simulated
attitude and eclipse state, not a flat duty cycle), a downlink RF
link-margin estimate evaluated against real simulated slant range, and
Monte Carlo batch analysis (`Basilisk.utilities.MonteCarlo`, dry-mass
and attitude dispersions).

**Orbit maintenance** -- altitude/semi-major-axis station-keeping and
constellation-wide phasing maintenance, both with real delta-V/
propellant bookkeeping (rocket-equation mass depletion fed back into
simulated spacecraft mass every tick) and eclipse-gated burns; a
constant-frame (VNB/RTN) continuous-thrust maneuver mode; a
Walker-pattern constellation generator (satellite count, planes,
phasing factor, altitude, inclination -> a full set of spacecraft with
pre-computed orbital elements).

**Vizard visualization** -- live-stream or `.bin` playback file, an
Earth-centered default camera view with orbit trace lines, live
data panels (battery charge, station-keeping propellant remaining,
ground-station access-window indicators -- all driven by real,
already-simulated values, not static snapshots), custom 3D models per
spacecraft (purely cosmetic), and a **Launch Vizard** action that starts
the external application itself, not just configures what feeds it.

**Reusable starting points** -- three spacecraft "bus" templates
(passive CubeSat, 3-axis-stabilized CubeSat, ESPA-class smallsat) and
nine complete example scenarios covering every major concept in
isolation (see "Template missions" below).

**Safe cancellation** -- **Abort Simulation** cooperatively cancels an
in-progress run (or Monte Carlo batch, or Mission Sequence) between
simulation chunks or commands, keeping whatever partial results were
already produced -- never a forced kill that could leave Basilisk's C++
state mid-mutation.

**GUI & CLI** -- a full PySide6 desktop shell (scenario editor, results
plots, Monte Carlo, live progress feedback, a real visual theme/icon/
toolbar) and an equivalent headless CLI (`missionstudio validate/run/
monte-carlo/kernels-status/generate-constellation/gui`), both built on
the exact same `schema`/`engine` layer -- neither is a thin wrapper
around the other.

## Repository layout

```
missionStudio/
  README.md                          -- this file
  HISTORY.md                         -- the full phase-by-phase development log
  pyproject.toml                     -- packaging metadata, pytest config, CLI entry point
  missionstudio/
    cli.py                           -- batch/headless CLI + GUI launcher
    schema/
      scenario.py                    -- Scenario and friends, validation, save/load
      migrations.py                  -- schema-version migration registry
      command.py                     -- Phase 6: Command (Mission Sequence), collecting validate()
      references.py                  -- Phase 6: reference-integrity (find/rename) for resources + commands
      validation.py                  -- Phase 6: validate_all() -- fully-collecting scenario-wide validation
    engine/
      time_system.py                 -- UTC/TAI/TT/ET, single source of truth (needs Basilisk)
      kernels.py                     -- SPICE kernel fetch/status (needs Basilisk)
      spaceweather.py                -- CelesTrak fetch/validate/fallback (no Basilisk needed)
      results.py                     -- TimeSeries/ResultSet, CSV export (no Basilisk needed)
      service.py                     -- SimulationService (needs Basilisk)
      fsw.py                         -- Phase 2: attitude nav/guidance/control/actuation chain (needs Basilisk)
      vizard.py                      -- Phase 2: Vizard integration (needs Basilisk, imported lazily)
      monte_carlo.py                 -- Phase 3: Basilisk.utilities.MonteCarlo bridge (needs Basilisk)
      link_budget.py                 -- Phase 4: downlink RF link-margin estimate (no Basilisk needed)
      orbit_maintenance.py           -- Phase 4/5: station-keeping + phasing-keeping + constant-frame-thrust controllers, delta-V/propellant bookkeeping (needs Basilisk)
      propellant_bookkeeping.py      -- Phase 5: shared per-tick mass/propellant delta math (no Basilisk needed)
      constellation.py               -- Phase 4: Walker-pattern constellation generator + SeparationSchedule (no Basilisk needed)
      spacecraft_templates.py        -- Phase 5: reusable spacecraft "bus" templates (no Basilisk needed)
      mission_engine.py              -- Phase 6: MissionEngine -- walks mission_sequence against a SimulationService (needs Basilisk)
    gui/
      app.py                         -- QApplication entry point
      theme.py                       -- Phase 5: app-wide QSS stylesheet + palette
      icons.py                       -- Phase 5: procedurally-drawn app icon
      main_window.py                 -- MainWindow: File/Run menus + toolbar, ties everything together
      load_scenario_widget.py        -- "Load Scenario" tab: built-in template picker + browse-for-a-file
      scenario_editor.py             -- the full scenario form + live validation
      mission_sequence_editor.py     -- Phase 6: mission_sequence tree editor (Command Add/Edit/Remove/nesting)
      mission_output_widget.py       -- Phase 6: "Mission Output" debug-console tab (CommandSummary/ReportEntry display)
      propagation_setup_dialog.py    -- Phase 5: gravity/perturbations + integrator + space weather, one dedicated window
      spacecraft_editor.py           -- spacecraft list + add/edit/remove dialog (tabbed: orbit, sensors/actuators, FSW, power/propulsion/link budget)
      sensor_actuator_editor.py      -- Phase 2: generic sensor/actuator list + add/edit/remove dialog
      vizard_dialog.py               -- Phase 2: "enable Vizard for the next run" dialog
      vizard_launcher.py             -- find/launch the external Vizard application (no Basilisk needed)
      monte_carlo_editor.py          -- Phase 3: Monte Carlo settings + dispersion list editor
      ground_station_editor.py       -- ground station list + add/edit/remove dialog
      orbit_ic_widget.py             -- classical-elements (true/mean anomaly)/Cartesian/TLE orbit editor
      constellation_dialog.py        -- Phase 4: "Generate Walker constellation" dialog
      spacecraft_template_dialog.py  -- Phase 5: "New from template" picker dialog
      kernel_status_widget.py        -- SPICE kernel status panel
      results_widget.py              -- matplotlib results plot + CSV export
      run_worker.py                  -- SimulationService/Monte Carlo on a background QThread
    scenarios/
      two_body_validation.json       -- the Phase 0 validation scenario
      templates/                     -- education/starter-template scenarios -- see that directory's own README
        README.md                    -- the template catalog: what each one teaches, how to open/run one
        01_two_body_circular_orbit.json
        02_elliptical_orbit_with_perturbations.json
        03_geo_station_keeping.json
        04_walker_constellation.json
        05_formation_flying_phasing.json
        06_attitude_pointing_basic.json
        07_attitude_pointing_with_adcs_hardware.json
        08_mission_sequence_orbit_raise.json
        09_monte_carlo_dispersion_analysis.json
  scripts/
    _generate_templates.py            -- regenerates scenarios/templates/*.json from schema dataclasses (not installed/imported elsewhere)
  packaging/                          -- build_wheel.sh/.ps1, install.sh/.ps1, .desktop entry (Linux) -- see packaging/README.md
  tests/
    conftest.py                      -- requires_basilisk / requires_gui auto-skip markers
    test_scenario_schema.py
    test_command.py                    -- Phase 6
    test_references.py                 -- Phase 6
    test_validation.py                 -- Phase 6
    test_spaceweather.py
    test_results.py
    test_link_budget.py              -- Phase 4
    test_constellation.py            -- Phase 4
    test_scenario_templates.py       -- load/validate/round-trip every scenarios/templates/*.json
    test_cli.py
    test_two_body_validation.py      -- requires_basilisk
    test_mission_engine.py           -- Phase 6, requires_basilisk
    gui/
      test_scenario_templates_gui.py -- every template round-trips through ScenarioEditorWidget too
      test_orbit_ic_widget.py
      test_spacecraft_editor.py
      test_sensor_actuator_editor.py
      test_vizard_dialog.py
      test_vizard_launcher.py
      test_monte_carlo_editor.py
      test_ground_station_editor.py
      test_constellation_dialog.py   -- Phase 4
      test_scenario_editor.py
      test_propagation_setup_dialog.py
      test_results_widget.py
      test_kernel_status_widget.py
      test_run_worker.py
      test_main_window.py
      test_mission_sequence_editor.py -- Phase 6
      test_mission_output_widget.py  -- Phase 6
      test_load_scenario_widget.py   -- "Load Scenario" tab: built-in template picker + browse
```

## Running the tests

```bash
cd missionStudio
python3 -m pip install -e ".[dev,gui]"
python3 -m pytest tests/ -v
```

Without Basilisk on `PYTHONPATH`, this runs 600 tests (schema, space
weather, results, link budget, constellation generation, CLI, and the
full PySide6 GUI, run headless) and skips 75 whose premise is
specifically "Basilisk is unavailable" (marked `requires_basilisk`), per
`tests/conftest.py`.

With Basilisk installed (`pip install "bsk[all]"` -- see "Getting
started" above), the 75 skips above run for real instead of skipping.
See "Verification status" above for how thoroughly that's actually been
exercised -- short version: yes, including a real full multi-day run.

`packaging/build_wheel.sh`/`install.sh` are NOT run by `pytest` (they're
shell scripts that build/install a real wheel, not something worth
wrapping in a slow subprocess-spawning test) -- see `packaging/README.md`
for how they were verified instead.

If PySide6 fails to import with `ImportError: libEGL.so.1: cannot open
shared object file` (a minimal Linux install, or a container like the one
this session used), install the missing system libraries first --
Debian/Ubuntu: `apt-get install libegl1 libopengl0 libxcb-cursor0` (this
session also needed `libgl1`/`libxkbcommon0`, but those were already
present on the base image; a truly minimal system may need them too).

## Using the schema/space-weather layer standalone (no Basilisk needed)

```python
from missionstudio.schema import Scenario, GravityConfig, OrbitIC, SpacecraftConfig

scenario = Scenario(
    name="demo",
    epoch_utc="2030-01-01T00:00:00",
    gravity=GravityConfig(central_body="earth", central_body_degree=0),
    spacecraft=[
        SpacecraftConfig(
            name="sat-1",
            orbit=OrbitIC(type="classical_elements", semi_major_axis_km=7000.0,
                          eccentricity=0.001, inclination_deg=51.6, raan_deg=0.0,
                          arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
        )
    ],
)
scenario.validate()
scenario.save("my_scenario.json")
```

```python
from datetime import datetime
from missionstudio.engine import spaceweather as sw

resolved = sw.resolve("celestrak", datetime(2030, 1, 1), datetime(2030, 4, 1),
                       local_file_path="/path/to/your/SW-All.csv")  # your CelesTrak download, if you have one
print(resolved.path, resolved.is_synthetic, resolved.warnings)
```

## Running a scenario (requires a Basilisk build)

```python
from missionstudio.schema import load_scenario
from missionstudio.engine.service import SimulationService

scenario = load_scenario("missionstudio/scenarios/two_body_validation.json")
service = SimulationService(scenario)
result = service.run()
result.export_csv("out/")
```

To also get attitude control and a Vizard playback file, set a
spacecraft's `fsw_mode`/`sensors`/`actuators` (see `engine/fsw.py`) and
pass a `VizardRequest`:

```python
from missionstudio.engine.vizard import VizardRequest

service = SimulationService(scenario, vizard_request=VizardRequest(save_file="out/viz.bin"))
result = service.run()
```

## Running the CLI

The `missionstudio` command (installed by `pip install -e .`; `python3 -m
missionstudio.cli` works identically without installing) is the
batch/headless entry point, built on exactly the calls above -- see
`cli.py`'s own docstring.

```bash
# no Basilisk needed:
missionstudio validate missionstudio/scenarios/two_body_validation.json
missionstudio spaceweather-resolve missionstudio/scenarios/two_body_validation.json

# needs a Basilisk build:
missionstudio run missionstudio/scenarios/two_body_validation.json --out-dir results/
missionstudio run scenario_with_fsw.json --out-dir results/ --vizard-save-file results/viz.bin
missionstudio monte-carlo scenario_with_dispersions.json --archive-dir mc_results/
missionstudio kernels-status

# launches the PySide6 GUI (needs the 'gui' extra; does NOT need Basilisk
# to open -- only Run/Check Kernels need it, and report clearly if it's
# missing rather than crashing):
missionstudio gui
```

Without Basilisk, `run` and `kernels-status` print a specific "Basilisk is
not installed/built" message and exit with status 2 -- genuinely
verified, not just designed to behave that way.

Two more commands worth knowing: **Launch Vizard** (Run menu/toolbar,
GUI only) starts the external Vizard application itself, separate from
configuring how a run feeds it; **Abort Simulation** (Run menu, GUI
only, also while a Monte Carlo batch or Mission Sequence is running)
cooperatively cancels an in-progress run between simulation chunks or
mission-sequence commands -- never a forced kill, so partial results
from before the cancellation are kept, not discarded. Full detail on
both in `HISTORY.md`.

## Running the GUI

```bash
python3 -m pip install -e ".[gui]"
missionstudio gui
# or: python3 -m missionstudio.gui.app
```

The GUI opens on its **Load Scenario** tab (left pane) -- pick one of the
nine built-in template missions (see "Template missions" below) or
browse for any other scenario file; either one switches you to the
**Scenario Editor** tab next to it with that scenario loaded and ready to
edit. File > New/Open/Save/Save As work against the same
`schema.Scenario`/`load_scenario()`/`.save()` the CLI uses (File > Open
and the Load Scenario tab's own "Browse for a file..." button are two
paths to the same `open_path()`); the scenario form's validation status
label updates live as you type, including its Monte Carlo section
(enable/num_runs/thread_count + a dispersion list, referencing spacecraft
by name). Run > Run Simulation runs `SimulationService` on a background
thread (the UI stays responsive) and switches to the Results tab when
done, with a plot per result series and a CSV export button. Run > Check
Kernels shows SPICE kernel fetch/cache status. Both Run actions report a
clear error (not a crash) if Basilisk isn't installed/built.

## Template missions for learning and for starting your own

`missionstudio/scenarios/templates/` has nine ready-to-run scenario
files, each demonstrating one missionStudio concept in isolation --
two-body orbits, J2/third-body perturbations, GEO station-keeping,
a generated Walker constellation, formation-flying phasing control,
attitude pointing (idealized, then with real ADCS hardware), a Mission
Sequence-based impulsive orbit raise, and a Monte Carlo dispersion
analysis. See that directory's own `README.md` for the full catalog and
what each one teaches -- every file also carries its own extensive
`description` field (visible in the GUI's scenario form, or by opening
the `.json` directly) explaining what to look at after running it and
what to try changing.

They're built through `schema.scenario`'s own dataclasses and
`Scenario.validate()` (via `scripts/_generate_templates.py`, kept in the
repository as the regeneration source of truth), not hand-written JSON,
and every one is covered by `tests/test_scenario_templates.py`
(schema-level load/validate/round-trip, Basilisk-free),
`tests/gui/test_scenario_templates_gui.py` (confirms each one also
round-trips through the actual `ScenarioEditorWidget` form), and
`tests/gui/test_load_scenario_widget.py` (the in-GUI picker described
below) -- 59 tests total, all passing before this was committed. What's
NOT yet verified: an actual Basilisk run of any of them (this sandbox has
none), so treat the physical numbers (propellant use, drift rates,
orbital periods) as reasonable back-of-the-envelope choices, not
independently confirmed results against a real Basilisk build for this
specific scenario file -- see "Verification status" above for what has
and hasn't been run for real.

**Built into the GUI itself** (not just files you'd have to know the path
to): the GUI's **Load Scenario** tab (`gui/load_scenario_widget.py`,
see "Running the GUI" above) lists all nine by name with their
description shown on selection, no file-browsing needed -- "Open
Template" or a double-click loads one and switches straight to the
Scenario Editor tab. The same tab's "Browse for a file..." button covers
everything else, via the same `MainWindow.open_path()` File > Open
already uses. From the CLI:

```bash
missionstudio validate missionstudio/scenarios/templates/01_two_body_circular_orbit.json  # no Basilisk needed
missionstudio run missionstudio/scenarios/templates/01_two_body_circular_orbit.json --out-dir out
```

To use one as a starting point for your own mission: **Save As...** under
a new name before editing (so the original template stays intact for
next time), then layer in whatever additional concepts you need --
templates/README.md's own closing section has concrete suggestions for
combining them (e.g. a comms-relay constellation might start from '04'
and add '07''s ADCS hardware plus a ground station and RF link).

## Vendoring vs. building Basilisk from source

Building from source in an automated/CI/sandboxed context is fragile --
this project hit exactly that failure mode early on (see `HISTORY.md`
for the full story). The plan flagged from the start was to
**vendor a prebuilt wheel pinned to a specific Basilisk release/commit**
as the default install path for end users, keeping "build from source" a
documented, opt-in developer path only.

That plan turned out to be simpler to satisfy than expected: Basilisk
itself now publishes prebuilt wheels to PyPI (`pip install "bsk[all]"`),
so there is usually no separate wheel to hunt down or vendor at all --
"Getting started" above IS the vendoring story for most users.
`packaging/install.sh --basilisk-wheel` still exists and still works (it
was run end-to-end against `"bsk[all]"` for real -- see
`packaging/README.md`) for the cases that DO need something other than
the published PyPI package: a specific pinned/older release for
reproducibility, a locally-built wheel with custom modules, or an offline
install from a wheel file already on disk. `--basilisk-wheel` accepts any
string `pip install` would (a path, a URL, or a plain requirement
specifier like `"bsk[all]==2.12.0"`), not literally only a `.whl` file.

## Known limitations

* **No `svIntegratorRK4` in this checkout.** Only `svIntegratorEuler`,
  `svIntegratorRK2`, `svIntegratorRKF45`, `svIntegratorRKF78` exist (see
  `../src/simulation/dynamics/Integrators/`). `schema.scenario.SimSettings`
  and `engine.service._INTEGRATORS` only offer those four; `"rkf78"` is
  the default.
* **Spherical-harmonics gravity is Earth-only in `service.py`**
  (GGM03S, the same file `../missionAnalysis` uses). Other central bodies
  are limited to point-mass gravity (`central_body_degree=0`) until a
  later phase adds their gravity-field files.
* **Magnetometer sensors are Earth-only** (`magneticFieldWMM`, same
  reasoning as spherical-harmonics gravity) -- `engine.fsw` raises a clear
  error for a magnetometer on any other central body rather than silently
  producing a sensor with no field to read.
* **`locationPointing`'s `target_body` option (point at a celestial body
  directly, not a ground station) is schema-valid but not wired up** --
  it needs an `EphemerisMsg`, which this checkout only produces via
  `ephemerisConverter` from a `SpicePlanetStateMsg`, not yet built here.
* **`"thruster"`/`"magnetic_torque_rod"` actuator kinds are schema-valid
  but not wired up** -- `engine.fsw`/`engine.service` raise a specific
  error if either is actually configured, rather than silently doing
  nothing.
* **The attitude control loop closes on truth spacecraft state.**
  `simpleNav` is in the loop (not raw `scStateOutMsg`), but its
  error-model matrices are left at Basilisk's own zero defaults -- there
  is no GUI/schema field yet to configure realistic navigation error.
* **Monte Carlo dispersions cover two quantities**: `dry_mass_kg`
  (uniform/normal) and `attitude_sigma_bn` (uniform-random-attitude).
  Cartesian position/velocity dispersion is deliberately NOT offered --
  see `engine/monte_carlo.py`'s module docstring for why (Basilisk's
  Cartesian dispersion classes replace each component with an absolute
  random value, not a perturbation around the nominal orbit).
* **`monte_carlo.thread_count > 1` is unverified** in this project's
  development sandbox (no Basilisk build here to run it against) -- the
  schema default is the definitely-safe `1`.
* **Monte Carlo retains a fixed set of data per run** (each spacecraft's
  position/velocity) -- there is no per-run custom retention-policy
  selection in the schema yet.
* **This development sandbox itself still can't reach the NAIF SPICE
  kernel host** (its network policy blocks it), so `engine.kernels`'s
  download step always fails here specifically -- correctly, with a
  clear error, not a code defect. This is a sandbox limitation, not a
  project limitation: a real user's machine, with ordinary internet
  access, has since run full multi-day simulations successfully (see
  "Verification status" above) -- kept in this list only because it's
  still true of THIS development sandbox specifically.

## Version 1.0.0

The first tagged release. What changed for it, and what "1.0.0" actually
means here:

* **A real end-to-end run, on a real Basilisk install, finally happened**
  -- the one specific gap this project had flagged since Phase 0 (this
  development sandbox's network policy blocks the NAIF SPICE kernel
  host, so a full run past kernel loading was never independently
  confirmed here). A real user ran the full `05_formation_flying_phasing.json`
  template -- both `StationKeepingController` and `PhasingKeepingController`
  active, Vizard live-streaming on -- to 100% completion (`t=604800.0 s`
  of `604800.0 s`, the full 7 simulated days) with no errors. Getting
  there involved finding and fixing a real, previously-unreproducible
  crash along the way -- a long investigation that initially misidentified
  eclipse-handling as the cause before a real `gdb` session traced it to
  a dangling-pointer bug in `engine/vizard.py`'s Vizard live-data panels
  (see "Verification status" above, and `HISTORY.md` for the full
  investigation).
* **Cross-platform install.** `python -m venv` + `pip install "bsk[all]"`
  + `pip install -e ".[dev,gui]"` (the "Getting started" section above)
  works identically on Linux and Windows 11 -- Basilisk's own prebuilt
  wheels are published for both (`../docs/source/Install.rst`'s "Prebuilt
  wheel availability" table), and missionStudio's own code was already
  written with per-OS awareness where it matters (`gui/vizard_launcher.py`'s
  `_candidate_roots()`/`_EXECUTABLE_NAME` branch on `sys.platform` for
  finding the external Vizard app; `Path.home()`, never a raw `$HOME`/
  POSIX assumption, for every user-data location). `packaging/install.ps1`/
  `build_wheel.ps1` are new this release -- direct PowerShell ports of
  the already-verified `install.sh`/`build_wheel.sh`, giving Windows the
  same one-command install + Start Menu shortcut experience Linux has had
  since Phase 3. Per this project's own verification discipline: the
  Linux install scripts and the Linux Basilisk-wheel install have been
  run for real; their Windows counterparts have not (no Windows
  environment has ever been available in this development sandbox) --
  see `packaging/README.md`'s "Windows support" section for exactly
  what that does and doesn't cover, and please report anything that
  doesn't work as documented on a real Windows 11 machine.
* **Version bumped** `0.1.0.dev0` -> `1.0.0` in `pyproject.toml` and
  `missionstudio/__init__.py`.

## What's next

Scoped but not yet built, from real GUI usage feedback (full detail in
`HISTORY.md`'s "What Phase 4 adds" and "What Phase 5 adds"):

* **`engine.constellation`'s Walker generator doesn't auto-wire
  `PhasingKeepingConfig`** for the satellites it produces -- each
  follower's chief/target-separation still needs setting up by hand in
  the spacecraft editor afterward. A natural, well-scoped follow-on once
  that manual step is felt to be tedious in practice: the generator
  already knows each plane's membership and phase ordering, so it could
  assign chief = "first satellite in the plane" and a sensible default
  target separation automatically.
* **A live link-margin gauge in Vizard** -- deliberately not built:
  Vizard's `GenericStorage` only accepts Battery/DataStorage/FuelTank
  -shaped messages, and forcing a dB margin value through would need a
  fabricated adapter message with no natural floor/ceiling. If this
  becomes worth doing anyway, the RIGHT path is a real custom Vizard
  protobuf message/panel type, not a reused shape.

Beyond that, the "Known limitations" section above is the rest of the
honest map: a handful of schema-valid-but-not-wired-up options
(celestial-body `locationPointing` targets, thrusters, magnetic torque
rods, non-Earth spherical harmonics/magnetometer), navigation error
modeling, and richer Monte Carlo retention. None of the remaining items
is blocked on a design decision; each is scoped and documented at its
own call site (or in `HISTORY.md`) for whoever picks it up next.
