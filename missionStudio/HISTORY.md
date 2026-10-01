# missionStudio development history

The full phase-by-phase development log: every feature's design
rationale as it was built, every real bug found and fixed (never swept
under the rug), and the complete crash-investigation writeups --
including one that took an extensive real-hardware debugging session
(culminating in a `gdb` backtrace) to actually root-cause. Moved out of
`README.md` for the 1.0.0 release so that file can be a normal,
readable project README; nothing below was deleted or altered beyond
fixing a handful of now-dangling `README.md` cross-references to point
here instead.

Read `README.md` first for current install/usage/status. Read this file
for *why* things are the way they are, or to see a real, honest account
of an AI-assisted development process working through real bugs on a
real user's machine.

---

## Environment honesty note (read this first)

Earlier in this project, this checkout had no Basilisk Python package
available: a from-source build was attempted and failed (`conanfile.py`
couldn't reach Conan Center through this sandbox's outbound-network
policy). That's no longer the full picture -- `pip install "bsk[all]"`
(Basilisk's own published PyPI wheel) turned out to work in the same
sandbox, and was used to genuinely re-verify most of the Basilisk
-dependent code below for the first time. `celestrak.org` and the NAIF
kernel host (`naif.jpl.nasa.gov`, plus its `hanspeterschaub.info` backup
mirror) remain blocked, which is the one gap left -- see the per-item
notes below for exactly what that does and doesn't affect.

Status, as of this Basilisk-build re-verification pass:

* Everything in `missionstudio/schema/`, `missionstudio/engine/spaceweather.py`,
  `missionstudio/engine/results.py`, `missionstudio/cli.py`, and **the
  entire `missionstudio/gui/` package** (including Phase 2's sensor/
  actuator/FSW-mode/Vizard-request editors and Phase 3's Monte Carlo
  editor) has **no Basilisk import** and has been fully exercised, with or
  without Basilisk present -- `pytest tests/` genuinely runs and passes
  150 tests either way (see ``README.md``'s "Running the tests" section
  for the current, up-to-date with-Basilisk count -- this number is a
  Phase 0-era snapshot, kept here as-written). That includes the PySide6 GUI: it was built, run
  headless (`QT_QPA_PLATFORM=offscreen`, set automatically by
  `tests/conftest.py`), and driven with `pytest-qt` for real -- every form
  field, every Save/Open/Run menu action, dirty-state tracking, and the
  unsaved-changes close-confirmation prompt is exercised by an actual
  running `QApplication`, not asserted about in the abstract. Getting
  PySide6 itself running headless needed three system packages beyond
  what was preinstalled (`libegl1 libopengl0 libxcb-cursor0` on the
  Ubuntu-based image this was developed on, via `apt-get`) -- worth
  knowing if a deployment target hits the same `ImportError:
  libEGL.so.1: cannot open shared object file`.
* `missionstudio/engine/time_system.py`, `kernels.py`, `service.py`,
  `fsw.py`/`vizard.py` (Phase 2), and `monte_carlo.py` (Phase 3) import
  Basilisk. Against a real `bsk[all]` install: every Basilisk module/class
  any of these files import was confirmed to exist under the expected
  name; `time_system.py`'s SPICE call sequence was run for real
  (round-tripping an epoch through ET and back, computing TAI/TT) and a
  real bug was found and fixed doing so (a bare `import pyswice` that
  doesn't match the published package's layout -- see that module's own
  docstring); `service.py`'s `build()` was confirmed to run correctly
  through gravity/spacecraft/attitude/sensor/actuator/ground-station
  construction, failing only at the SPICE kernel DOWNLOAD step (blocked
  network to NAIF, not a code issue -- see `kernels.py`'s own note). A
  FULL run past kernel loading -- and so `fsw.py`/`vizard.py`/
  `monte_carlo.py`'s own module-construction logic, and
  `tests/test_two_body_validation.py`'s analytical check -- was NOT
  achieved, purely because that needs the blocked kernel download to
  succeed first. Each file's own docstring says precisely what was and
  wasn't confirmed, updated after this pass -- nothing here should be
  trusted as "tested" beyond what its docstring claims.
* **Packaging (`packaging/build_wheel.sh`, `packaging/install.sh`) was
  fully verified, including the Basilisk-vendoring path**: with a real
  `bsk[all]` available, `install.sh --basilisk-wheel "bsk[all]"` was run
  end-to-end and the resulting installed venv's `missionstudio.engine.service`
  imported correctly. See `packaging/README.md`.
* The GUI/CLI's no-Basilisk error handling (`gui.run_worker.RunWorker`,
  `gui.kernel_status_widget`, `cli.py`'s `run`/`kernels-status`) was
  separately confirmed for real in an environment WITHOUT Basilisk
  installed: each correctly reports "Basilisk is not installed/built"
  (no crash, no hang, no silent no-op) rather than a bare traceback.
* `tests/test_two_body_validation.py` -- the end-to-end analytical
  validation scenario this project's own requirements call for -- is
  written and ready, correctly auto-skips without Basilisk (see
  `tests/conftest.py`), and correctly ATTEMPTS a real run with Basilisk
  present, but could not complete because of the blocked kernel download
  above. **Run it on a machine with ordinary internet access** to get the
  first full confirmation that `engine.service.SimulationService`
  actually produces correct physics.

None of this is a reason to distrust the design -- it's the same
"write carefully against verified source, disclose what's untested"
discipline `../missionAnalysis` used throughout this project, now backed
by an actual Basilisk install for most of it. The one thing a user should
take away: get this running on a machine with normal internet access
(specifically, access to `naif.jpl.nasa.gov`) and the whole pipeline
should work end-to-end -- that's the one link in the chain this project's
own sandbox could never close.

## What Phase 0 delivers

* **`missionstudio/schema/`** -- a versioned, human-readable JSON scenario
  format (spacecraft, orbit ICs in three forms, gravity, ground stations,
  space weather, sim settings), with hand-written validation (clear,
  specific error messages -- never a silent NaN or a bare `KeyError`) and
  a migration registry so old scenario files keep loading as the schema
  grows. No Basilisk dependency; no third-party schema library.
* **`missionstudio/engine/time_system.py`** -- single source of truth for
  time: every scenario stores exactly one epoch representation
  (`epoch_utc`, ISO 8601 UTC); every other representation (SPICE ET, TAI,
  TT, or a Basilisk `EpochMsg`) is derived from it on demand by this
  module, via the real CSPICE time API (through `pyswice`) -- not
  hand-rolled date math.
* **`missionstudio/engine/kernels.py`** -- SPICE kernel management: wraps
  Basilisk's own versioned, `pooch`-cached kernel fetcher
  (`Basilisk.utilities.supportDataTools.dataFetcher`) and adds a status
  report (path, fetched-or-not, cache-file modified time) so kernel state
  is always visible, never silently assumed current.
* **`missionstudio/engine/spaceweather.py`** -- CelesTrak space-weather
  fetch → validate → fallback, exactly per this project's own
  instruction: try CelesTrak first; if that isn't possible, fall back to
  a user-provided local file; only fall back further than that (a
  synthetic, solar-cycle-shaped profile) loudly, with an explicit warning
  in the returned result, never silently. The CSV format check mirrors
  Basilisk's own `spaceWeatherData.cpp` loader validation exactly (same
  required columns, same duplicate/sort checks), so a bad file is caught
  here with a specific message instead of failing deep inside Basilisk.
* **`missionstudio/engine/results.py`** -- a typed result container
  (`TimeSeries`/`ResultSet`) with CSV export, independent of how the data
  was produced -- reusable by the future GUI (plotting) and by headless
  runs (export) without either depending on the other.
* **`missionstudio/engine/service.py`** -- `SimulationService`: the one
  GUI-agnostic backend class both the GUI and a headless/batch CLI call.
  Phase 0/1 scope: central-body point-mass or Earth spherical-harmonics
  gravity, PLUS third-body point-mass perturbers (`gravity.third_body_perturbers`
  -- genuinely wired up via `addBodiesTo()`, the same mechanism already
  verified in `../missionAnalysis`; an earlier draft of this file's
  docstring incorrectly called this schema-only, since corrected), one or
  more spacecraft from a classical-elements/Cartesian/TLE initial
  condition, propagation with a selectable integrator
  (`euler`/`rk2`/`rkf45`/`rkf78` -- **note: no `rk4`**, this Basilisk
  checkout doesn't ship one; see `schema.scenario.SUPPORTED_INTEGRATORS`'s
  docstring). Drag, SRP, sensors/actuators/FSW modes, ground stations, and
  Monte Carlo are validated by the schema and carried through save/load
  starting now, but not yet wired into the service -- that's Phase 2/3.
  The Phase 1 GUI's scenario editor mirrors this exactly: it edits
  everything the service actually consumes, and deliberately has no
  editor for the not-yet-wired-up fields, so nothing in the GUI looks
  like it does something it doesn't.
* **`missionstudio/scenarios/two_body_validation.json`** +
  **`tests/test_two_body_validation.py`** -- the required end-to-end
  validation scenario: Earth point-mass gravity only, propagated for
  several orbital periods, checked against an independently-computed
  analytical Kepler solution (position/velocity) and against conservation
  of specific orbital energy and angular momentum.

Two Phase 0 bugs were also found and fixed while building Phase 1 on top
of it (both are visible in `git log` for this file's history, not swept
under the rug): `schema.SimSettings` used to carry a second,
redundant `earth_grav_degree` field alongside `GravityConfig.
central_body_degree`, which could disagree with it -- removed, there is
now one field; and `schema.load_scenario()` didn't catch a missing/
unreadable file (`FileNotFoundError` propagated as a raw traceback
instead of the promised `ScenarioValidationError`) -- fixed, with a
regression test.

## What Phase 1 adds

* **`missionstudio/gui/`** -- the PySide6 GUI shell, one widget module per
  concern, none of it duplicating scenario/sim state or logic that
  already lives in `schema`/`engine`:
  * `scenario_editor.py` -- the full scenario form (name/epoch/description,
    gravity incl. third-body perturbers, sim settings, space weather
    source), with a live-updating "valid / here's exactly what's wrong"
    status label re-evaluated on every edit.
  * `spacecraft_editor.py` / `ground_station_editor.py` -- list + add/edit/
    remove dialogs for each. Spacecraft editing deliberately covers only
    what `engine.service.SimulationService` actually consumes (name,
    orbit IC, dry mass, inertia, initial attitude/rate) -- no
    sensors/actuators/FSW-mode/drag/SRP editor yet, so nothing in the GUI
    implies an effect the engine doesn't actually have. Ground stations
    ARE editable despite not being consumed yet, since they're pure
    scenario data (this project's own spec draws exactly that
    distinction) rather than a "looks like it does something" control.
  * `orbit_ic_widget.py` -- one widget covering all three
    `schema.OrbitIC` forms (classical elements / Cartesian / TLE).
  * `kernel_status_widget.py` -- SPICE kernel fetch/cache status with a
    "Check / fetch kernels" button, runs on a background thread.
  * `results_widget.py` -- matplotlib-embedded (`FigureCanvasQTAgg`) plot
    of any `ResultSet` series, plus a "export all series to CSV" button.
  * `run_worker.py` -- runs `SimulationService` on a background `QThread`
    so propagation never freezes the UI.
  * `main_window.py` / `app.py` -- ties it together: File (New/Open/Save/
    Save As, with an unsaved-changes indicator and close-confirmation) and
    Run (Run Simulation, Check Kernels) menus.
* **`missionstudio/cli.py`** -- the batch/headless CLI, built on exactly
  the same `schema`/`engine` calls the GUI makes (`validate`, `run`,
  `kernels-status`, `spaceweather-resolve`, `gui`) -- see "Running the
  CLI" below.

## What Phase 2 adds

* **`missionstudio/engine/fsw.py`** -- builds the attitude navigation/
  guidance/control/actuation module chain per spacecraft, kept separate
  from `service.py` so that file stays orchestration-only. Every
  `schema.scenario.SpacecraftConfig.fsw_mode` maps to a real Basilisk FSW
  module: `inertial3D`/`hillPoint`/`velocityPoint` (routed through
  `attTrackingError`) and `sunSafePoint`/`locationPointing` (which already
  output an `AttGuidMsg`), all closing on `mrpFeedback` control. Actuation
  is either idealized (`extForceTorque`, the default) or real reaction
  -wheel hardware (`simIncludeRW`/`reactionWheelStateEffector`/
  `rwMotorTorque`) when a spacecraft has `"reaction_wheel"` actuators.
  Sensors (`star_tracker`/`imu`/`coarse_sun_sensor`/`magnetometer`) attach
  independently of `fsw_mode` since they read truth state/SPICE/the
  magnetic-field model directly. `"thruster"`/`"magnetic_torque_rod"`
  actuators and `locationPointing`'s `target_body` option are schema-valid
  but raise a specific, actionable error rather than being silently
  ignored -- see `fsw.py`'s module docstring for the full scoping list and
  exactly which example script each call sequence was copied from.
* **`missionstudio/engine/vizard.py`** -- the "no embedded 3D viewer, but
  good Vizard visualization with valuable live simulation data"
  requirement: wraps `vizSupport.enableUnityVisualization()` (live-stream
  or `.bin` playback file), passes reaction-wheel effectors through so
  Vizard draws its native per-wheel speed bars, and draws every ground
  station via `vizSupport.addLocation()` (lat/lon/alt + elevation-mask
  cone) so `locationPointing`'s target geometry is actually visible.
* **`ResultSet` now carries Phase 2 series** for any spacecraft that has
  them configured: `{name}.attitude_sigma_BN`, `{name}.body_rate_omega_BN_B`,
  `{name}.sun_heading_body`, `{name}.control_torque`, `{name}.rw_speeds`,
  and one `{name}.sensor.{sensor_name}` series per attached sensor --
  always in addition to, never instead of, the Phase 0 position/velocity
  series.
* **GUI**: `spacecraft_editor.py` gained a tabbed dialog (Orbit/mass,
  Sensors/actuators, Attitude control) backed by the new
  `gui/sensor_actuator_editor.py` (a generic Add/Edit/Remove list widget
  shared by sensors and actuators, since their shape is identical --
  `params` is edited as raw JSON text rather than a bespoke form per kind,
  since the schema deliberately keeps `params` an open dict). A real bug
  was fixed along the way: editing an existing spacecraft used to silently
  DROP its `sensors`/`actuators`/`fsw_mode`/`fsw_params`/`control_params`
  (the dialog built a brand new `SpacecraftConfig` without passing them
  through) -- harmless while nothing set them, a real data-loss bug the
  moment this phase's own editors did; fixed with a regression test. The
  Run menu gained a **Vizard...** action (`gui/vizard_dialog.py`) to pick
  disabled / save-a-playback-file / live-stream for the next run, plumbed
  through `RunWorker` into `SimulationService`.
* **CLI**: `missionstudio run` gained `--vizard-save-file`/
  `--vizard-live-stream` (mutually exclusive).

## What Phase 3 adds

* **Ground-station access analysis.** `engine.service.SimulationService`
  now builds a `groundLocation.GroundLocation` for EVERY
  `GroundStationConfig` in a scenario (not just ones a spacecraft's
  `locationPointing` mode targets), and calls the new
  `engine.fsw.add_access_analysis()` once every spacecraft exists so every
  station sees every spacecraft -- the standard access-analysis question.
  `ResultSet` gains four series per (station, spacecraft) pair:
  `{station}.access_to_{spacecraft}.has_access`/`.slant_range`/
  `.elevation`/`.azimuth`.
* **`missionstudio/engine/monte_carlo.py`** -- wraps
  `Basilisk.utilities.MonteCarlo` (`Controller`/`Dispersions`/
  `RetentionPolicy`, real native Basilisk infrastructure, not reimplemented
  here). `schema.scenario.MonteCarloConfig`/`DispersionConfig` describe a
  batch (`num_runs`, `thread_count`, `verbose`) and per-spacecraft
  dispersions (`dry_mass_kg` uniform/normal, `attitude_sigma_bn`
  uniform-random-attitude via `UniformEulerAngleMRPDispersion`) --
  deliberately NOT Cartesian position/velocity dispersion, since
  Basilisk's Cartesian dispersion classes replace each component with an
  ABSOLUTE random value rather than perturbing around the nominal orbit,
  which would silently produce a physically nonsensical result (see that
  module's docstring). `engine.service.SimulationService.build()` gained
  an `initialize` parameter so Monte Carlo can apply dispersions BEFORE
  `InitializeSimulation()` runs (applying them after would silently have
  no effect, since `Reset()` would already have latched the un-dispersed
  values). `missionstudio monte-carlo` (CLI) and Run > **Run Monte
  Carlo...** (GUI, via the new `gui/monte_carlo_editor.py` scenario-form
  section) both drive it.
* **`packaging/`** -- `build_wheel.sh`/`install.sh`/`missionstudio.desktop.in`,
  genuinely built and run in this sandbox (see the honesty note above and
  `packaging/README.md` for two real bugs found and fixed this way: a
  missing scenario data file in the wheel, and a `./build/`-directory
  import-shadowing bug in repeated builds).

## What Phase 4 adds

Driven directly by feedback from actually using the Phase 3 GUI:

* **Vizard's default view is now Earth-centered with the orbit visible**,
  not locked onto the spacecraft with no context. `engine.vizard`'s
  `VizardRequest` gained `camera_target` (defaults to the scenario's
  central body) and `show_orbit_lines` (osculating + true trajectory
  lines, on by default), set via `VizSettings.mainCameraTarget`/
  `orbitLinesOn`/`trueTrajectoryLinesOn` -- `enableUnityVisualization()`
  itself doesn't expose these. Configurable from the GUI's Vizard dialog
  or `--vizard-camera-target`/`--vizard-no-orbit-lines` (CLI).
* **Live feedback while a run is in progress.** `gui.main_window` used to
  show only a static "Running..." status-bar string with no other
  indication anything was happening. Run Simulation and Run Monte Carlo
  now show a busy indicator (indeterminate progress bar + elapsed-time
  label) and disable every Run-menu action until the worker finishes --
  Basilisk exposes no per-step/per-run progress callback to drive a real
  percentage, so this is deliberately indeterminate rather than a
  fabricated number.
* **Mean anomaly as a classical-elements orbit input.** `OrbitIC` gained
  `anomaly_type` (`"true"`/`"mean"`, default `"true"` for backward
  compatibility) and `mean_anomaly_deg`; `engine.service` converts mean to
  true anomaly via Kepler's equation (`orbitalMotion.M2E`/`E2f`) before
  calling `elem2rv`, which only accepts true anomaly. The GUI orbit editor
  exposes this as a combo box next to the angle field.
* **Real power budget.** `schema.scenario.PowerConfig` (optional, per
  spacecraft) wires Basilisk's actual `simpleSolarPanel`/
  `simplePowerSink`/`simpleBattery`/`eclipse` modules into
  `engine.service` -- the same pattern `../missionAnalysis/power_budget.py`
  already uses -- so generated power depends on the real simulated
  attitude (panel-normal-to-sun angle) and eclipse state, not a flat duty
  cycle. `ResultSet` gains `{spacecraft}.battery_charge` [W\*hr] and
  `{spacecraft}.battery_net_power` [W] per spacecraft that opts in; no
  per-subsystem (instrument/downlink) load gating is modeled yet, only a
  constant bus load, since missionStudio has no EO-payload data model to
  gate against (unlike `../missionAnalysis`).
* **Downlink RF link-margin estimate.** `schema.scenario.RFLinkConfig`
  (optional, per spacecraft) plus two new `GroundStationConfig` fields
  (`rx_antenna_gain_dbi`, `system_noise_temp_k`) feed the new
  `engine.link_budget` module -- a simplified free-space-path-loss Eb/N0
  budget ported directly from `../missionAnalysis`'s
  `_rf_link_margin_db()`. It is evaluated against the REAL simulated slant
  range from Phase 3's access analysis (not a worst-case estimate), giving
  `{station}.access_to_{spacecraft}.link_margin_db` in `ResultSet` --
  `NaN` outside access windows, since there's no link (and so no
  meaningful margin) when there's no access. Like the missionAnalysis
  original, this is a reported ESTIMATE only (no atmosphere/rain/
  pointing-loss/coding-gain terms) and does not feed back into simulated
  physics anywhere.
* **Orbit-maintenance / station-keeping automation, with delta-V and
  propellant bookkeeping.** `schema.scenario.StationKeepingConfig`
  (optional, per spacecraft) wires the new `engine.orbit_maintenance`
  module -- `StationKeepingController`, ported from `../missionAnalysis`'s
  `AltitudeKeepingController` -- into `engine.service`: a dedicated
  `extForceTorque` effector fires a continuous prograde reboost burn
  whenever a smoothed altitude estimate decays `deadband_km` below
  `target_altitude_km`, gated off during eclipse and once propellant is
  depleted. Propellant use is tracked via the rocket equation
  (explicit-Euler) and fed back into the spacecraft's simulated mass every
  tick, so thrust-to-mass stays physically consistent as it burns off --
  see `SpacecraftConfig.dry_mass_kg`'s docstring for how that field's
  meaning sharpens once `station_keeping` is set (it becomes the mass
  *without* propellant; the initial simulated mass becomes
  `dry_mass_kg + station_keeping.propellant_kg`). `ResultSet` gains
  `{spacecraft}.station_keeping.altitude` (raw + smoothed),
  `.burn_on`, `.propellant_remaining`, and `.delta_v` (cumulative);
  `missionstudio run` also prints a one-line delta-V/propellant-used
  summary per spacecraft so the headline numbers don't require opening a
  CSV. This needs something actually decaying the orbit to have any
  effect -- with only point-mass gravity (the default), altitude never
  decays and the burn never fires; enable `SpacecraftConfig.enable_drag`
  for a station-keeping scenario. Shares the same eclipse model
  `PowerConfig` uses when both are configured on the same spacecraft.
* **Constellation design: a Walker-pattern generator.** The new
  `engine.constellation` module ("user supplies the requirement, the tool
  designs the constellation") turns a handful of high-level numbers --
  total satellite count, number of planes, Walker phasing factor,
  altitude, inclination -- into a full set of `SpacecraftConfig`s with
  every satellite's orbital elements pre-computed via the standard
  Walker-Delta/Walker-Star RAAN/mean-anomaly formula (Vallado; Wertz's
  SMAD). Every generated satellite is a deep copy of ONE template
  spacecraft the user configures the normal way (mass, sensors, actuators,
  power, station-keeping, RF link, ...) -- only `name`/`orbit` differ, so
  designing a 12-satellite constellation is exactly as much data entry as
  designing one satellite. Pure orbital mechanics, no Basilisk import
  (central-body radii for the altitude-to-semi-major-axis conversion are
  copied from Basilisk's own `astroConstants.h`, so they match what
  `engine.service` actually simulates). Available from the GUI (spacecraft
  list's new "Generate Walker constellation..." button -- central body is
  read from the scenario, not independently selectable, so it can't drift
  out of sync with what actually gets simulated) and the CLI
  (`missionstudio generate-constellation`, `--append` to add to an
  existing scenario instead of replacing its spacecraft).
* **Constellation-wide phasing maintenance, with its own delta-V and
  propellant bookkeeping.** `schema.scenario.PhasingKeepingConfig`
  (optional, per follower spacecraft) wires
  `engine.orbit_maintenance.PhasingKeepingController` -- ported from
  `../missionAnalysis`'s controller of the same name -- to hold a
  follower's along-track separation from a `chief_spacecraft` at a target
  value (optionally stepped through a schedule of several values over the
  mission, e.g. tightening a formation from 1000 km to 100 km every few
  months) via a drift-orbit maneuver: a small temporary semi-major-axis
  offset, natural drift, then a restoring burn -- the same technique a
  differential corrector (GMAT's Target/Vary/Achieve) would normally
  automate, done here as a direct two-body calculation re-evaluated every
  tick. REQUIRES `station_keeping` to also be set on the same spacecraft:
  phasing and altitude-keeping share ONE physical thruster and propellant
  tank (this config deliberately has no `thrust_n`/`isp_s`/`propellant_kg`
  fields of its own -- `engine.service` reads those off `station_keeping`
  instead), with altitude-keeping taking priority whenever both want to
  fire on the same tick. `ResultSet` gains
  `{spacecraft}.phasing_keeping.separation_error`/`.state`/`.delta_v`
  (its own delta-V, tracked separately from -- but drawing from the same
  shared tank as -- `station_keeping`'s); `missionstudio run`'s
  delta-V/propellant summary line now includes a breakdown when both are
  configured. Not yet wired into `engine.constellation`'s Walker generator
  automatically (each follower's chief/target-separation still needs
  setting up by hand in the spacecraft editor after generating the
  constellation) -- a natural follow-on if that manual step turns out to
  be tedious in practice.
* **Live Vizard data panels**, responding directly to "the live-stream of
  the simulation with Vizard is not really understandable, improve" --
  three real, already-simulated data feeds now drive native Vizard HUD
  elements (`engine.vizard`, extended), not a static snapshot or an
  analytical estimate:
  * **Battery state of charge**, for any spacecraft with `PowerConfig` --
    a `GenericStorage` bar panel wired straight to that spacecraft's
    `simpleBattery.SimpleBattery.batPowerOutMsg`.
  * **Station-keeping propellant remaining**, for any spacecraft with
    `StationKeepingConfig` -- a second `GenericStorage` panel, fed by a
    new `FuelTankMsgPayload` output
    `engine.orbit_maintenance.StationKeepingController` now publishes
    specifically for this (that controller still doesn't use a Basilisk
    `fuelTank` state effector for the actual physics -- see its own
    docstring).
  * **Ground-station access windows** -- one `GenericSensor` marker per
    (station, spacecraft) pair Phase 3's access analysis tracks, changing
    color live between "no access"/"access" as the real, already
    -simulated `hasAccess` flag changes, via a small bridge module this
    phase adds (`GenericSensor` takes an integer mode, not a boolean, so
    something has to republish `hasAccess` as one -- see `engine.vizard`'s
    docstring for exactly how and why 0/2, not 0/1, are the two values
    used).

  The battery/propellant panel pattern is copied line-for-line from a
  real, shipped Basilisk example
  (`examples/MultiSatBskSim/scenariosMultiSat/scenario_StationKeepingMultiSat.py`);
  the access-window bridge composes verified pieces
  (`examples/scenarioGroundLocationImaging.py`'s `GenericSensor`/
  `DeviceCmdMsgPayload` wiring, `../missionAnalysis/attitude_controllers.py`'s
  `AccessMsgReader` usage) in a way that's this module's own, not copied
  from one example -- like the Phase 4 camera/orbit-line work, none of
  this has been checked against a real running Vizard display (no display
  in this development sandbox). A live **link-margin** panel was
  considered and deliberately NOT built: Vizard's `GenericStorage` only
  accepts Battery/DataStorage/FuelTank-shaped messages, and forcing a dB
  margin value through the DataStorage shape would need a fabricated
  adapter message with no natural floor/ceiling -- the link-margin numbers
  stay exactly where they already were (the plotted/exported
  `.link_margin_db` series from `engine.link_budget`), which is the
  honest choice over a misleading gauge.

`PowerConfig`, `RFLinkConfig`, `StationKeepingConfig`, and
`PhasingKeepingConfig` all default to `None` (off) on every existing
scenario -- turning any one on is the only input needed; the GUI's new
"Power / propulsion / link budget" spacecraft-editor tab (its "Phasing
keeping" group reads the chief-spacecraft choice from the OTHER
spacecraft already in the scenario, not a free-text field, so it can't
name one that doesn't exist) and the ground-station editor's two new
fields are pre-filled with reasonable placeholder defaults, matching this
phase's "user only supplies numbers, the tool does the rest" design goal.

Four real bugs were found by a full codebase audit after this phase
shipped, and fixed (all visible in `git log` for the files below, not
swept under the rug):

* **`SpacecraftConfig.enable_drag`/`enable_srp` were schema-valid and
  documented above as functional (see the station-keeping bullet's
  "enable `enable_drag`" instruction) but were never actually wired into
  `engine.service` -- station-keeping's reboost burn could never fire on
  any scenario, since nothing ever decayed the orbit.** Fixed: `enable_drag`
  now wires `engine.spaceweather`'s resolver into `spaceWeatherData` ->
  `msisAtmosphere` -> `zeroWindModel` -> a per-spacecraft
  `dragDynamicEffector`, ported from
  `../missionAnalysis/run_constellation_mission.py`'s verified chain;
  `enable_srp` wires a per-spacecraft `radiationPressure` effector off the
  same eclipse model `PowerConfig`/`StationKeepingConfig` already share.
  Both are Earth-only (NRLMSISE-00 has no other-body atmosphere model
  here), matching the spherical-harmonics-gravity precedent.
* **`_AccessIndicatorBridge` (the Live Vizard access-window indicator
  above) could be garbage-collected while still registered on the
  Basilisk sim task** -- a SWIG-director use-after-free (the Python side
  of a custom `SysModel` must outlive its C++ task registration, same
  requirement `StationKeepingController`/`PhasingKeepingController`
  already followed), surfacing as a `basic_string::_M_create` crash deep
  in an unrelated libstdc++ call, well after the actual corruption.
  Fixed: `engine.vizard`/`engine.service` now retain it the same way.
* **Editing an existing spacecraft with `enable_drag`/`enable_srp` already
  set silently reset them to the schema defaults** -- the spacecraft-editor
  dialog has no UI for these fields (by design, per above) but also never
  carried them through from the original config in `to_dataclass()`, unlike
  every other not-yet-editable field. Fixed.
* **The phasing-keeping chief-spacecraft combo, and the Monte Carlo
  dispersion spacecraft combo, silently fell back to whichever spacecraft
  happened to be first** whenever the stored name didn't match a current
  spacecraft (e.g. renamed after the config was saved) -- re-targeting a
  controller or dispersion at the wrong spacecraft with no visible
  indication. Fixed: the stale name is now surfaced as its own selectable
  entry and round-tripped as-is instead.

## What Phase 5 adds

Driven directly by feedback from actually using the Phase 4 GUI + engine
(this phase is in progress; bullets are added as pieces land):

* **Result plots/CSV export now include osculating Keplerian elements**,
  not just inertial position/velocity. `engine.service` computes semi-major
  axis, eccentricity, inclination, RAAN, argument of periapsis, and true
  anomaly at every recorded sample (`orbitalMotion.rv2elem`, the exact
  inverse of the classical-elements orbit-IC conversion already used
  elsewhere in this file) and adds them to `ResultSet` as
  `{spacecraft}.orbit_elements.{semi_major_axis,eccentricity,inclination,
  raan,arg_periapsis,true_anomaly}` -- one series per element (mixed units:
  m/-/rad), matching the existing convention for e.g.
  `station_keeping.burn_on`/`.delta_v`. `gui.results_widget`/the CLI's CSV
  export need no changes for these to show up -- both are already driven
  generically by whatever `ResultSet.series` contains. Near-circular
  and/or near-equatorial orbits have an inherent singularity in RAAN/
  argument of periapsis/true anomaly (see
  `engine.service._osculating_elements`'s docstring) -- not a bug, just
  how classical elements behave at those limits.
* **Sensor/actuator/FSW-mode setup is no longer a blank JSON box with zero
  guidance.** User feedback: configuring a spacecraft's sensors, actuators,
  and attitude-control mode was "confusing and not beginner friendly" --
  each dialog offered only a Kind/mode combo and an empty `{}` params box,
  so a user had to already know (by reading `engine/fsw.py`'s source)
  which JSON keys a given kind needs, their units, and which are required.
  A missing required key (e.g. `coarse_sun_sensor`'s `nHat_B`,
  `reaction_wheel`'s `gsHat_B`, `locationPointing`'s
  `target_ground_station`) wasn't caught there either -- only much later,
  decontextualized, when the whole spacecraft dialog's
  `SpacecraftConfig.validate()` ran (sensors/actuators) or not at all
  until `Run Simulation` actually failed deep inside `engine.fsw`
  (FSW mode). Fixed in both `gui.sensor_actuator_editor` and
  `gui.spacecraft_editor`'s FSW tab: a per-kind/per-mode help label (key
  name, required/optional, units, one-line description) that updates live
  as the Kind/FSW-mode combo changes; a new spacecraft/sensor/actuator
  starts pre-filled with a working example instead of `{}`; a "Reset to
  template" button refills the params box for the CURRENTLY selected
  kind/mode on demand (switching kind never silently overwrites what's
  already typed, to avoid destroying in-progress edits); and both dialogs
  now check required keys themselves and raise an immediate, specific
  error naming exactly what's missing, right where the params box is.
  `SUPPORTED_ACTUATOR_KINDS`'s `"thruster"`/`"magnetic_torque_rod"`
  (schema-valid but not wired up -- see the Phase 0 section above) and
  `locationPointing`'s `fsw_params["target_body"]` option now show an
  explicit in-dialog warning instead of silently accepting a
  configuration that fails only when the simulation actually runs.
* **Sensor/actuator body-frame direction vectors get dedicated X/Y/Z spin
  boxes**, not a bare 3-element array inside the params JSON box -- see
  `gui.sensor_actuator_editor`'s module docstring for exactly why
  DIRECTION (not position) is the one thing about sensor/actuator
  "placement" that actually affects the physics these Basilisk modules
  simulate here, plus a Normalize button since Basilisk does not
  renormalize a non-unit vector itself.
* **Reusable spacecraft "bus" templates.** A brand-new spacecraft used to
  start from `SpacecraftConfig()`'s bare dataclass defaults (100 kg, flat
  10 kg*m^2 inertia, no sensors/actuators/power/attitude control) -- a
  placeholder, not anything resembling a real vehicle. The new
  `engine.spacecraft_templates` module (pure schema data, no Basilisk
  import, same split as `engine.constellation`) ships three starting
  points -- a passive 3U CubeSat (drag/SRP enabled, no ADCS, good for
  orbit-only delta-V/lifetime studies), a 3-axis-stabilized 3U CubeSat
  (coarse sun sensor + 3 reaction wheels + `sunSafePoint` + a small power
  budget), and a 100 kg ESPA-class smallsat (star tracker + coarse sun
  sensor + 3 reaction wheels + `inertial3D` + a ~1 m-class power budget) --
  each internally consistent and validated, with rounded,
  order-of-magnitude-reasonable numbers (never a fabricated-precision
  datasheet figure; see that module's docstring). The spacecraft list's
  new "New from template..." button (next to "Add...") opens a small
  picker, then the ordinary `SpacecraftEditorDialog` pre-filled with the
  chosen template so the user still sets the actual name/orbit/anything
  else themselves, exactly like editing any other spacecraft.
* **Custom 3D models in Vizard.** The last piece of "adequately represent
  the correct placement" feedback: `SpacecraftConfig.vizard_model_path`
  (plus `vizard_model_offset_m`/`_rotation_deg`/`_scale`) wires
  `Basilisk.utilities.vizSupport.createCustomModel()` in, replacing a
  spacecraft's default cube icon with a real `.obj` mesh (or Vizard's
  `CUBE`/`CYLINDER`/`SPHERE` primitives) at a chosen body-frame offset/
  rotation/scale. PURELY COSMETIC -- it changes nothing about simulated
  physics (mass, drag/SRP area, etc. are unaffected either way); the
  spacecraft editor's new "Vizard model (cosmetic)" tab says so up front,
  same "don't offer a control that looks like it does something it
  doesn't" discipline as everywhere else in this app.
* **Orbit-only simulation mode, plus a constant-frame thrust maneuver.**
  `Scenario.simulation_mode` ("full_attitude", the default and everything
  this schema always supported, or "orbit_only") is the first field in
  the scenario editor's form, chosen before anything else per the
  feature request this responds to. "Orbit only" is a stricter,
  beginner-friendly mode for pure orbit-propagation questions (delta-V
  budgets, orbit lifetime, station-keeping cadence, ...): no spacecraft
  may have `fsw_mode`/`sensors`/`actuators`/`power` set (`Scenario.
  validate()` rejects it with a specific per-field error), so the
  spacecraft editor hides the Sensors/actuators and FSW tabs and the
  Power budget group while it's selected -- the spacecraft is simulated
  as a cannonball with `drag_area_m2`/`srp_area_m2` (which finally got a
  real editor too, on the Orbit/mass tab -- previously round-tripped only,
  with no UI to actually SET them anywhere) as its average cross-section.
  `station_keeping`/`phasing_keeping`/the new `constant_thrust` remain
  available in EITHER mode, since none of them need attitude knowledge.

  `SpacecraftConfig.constant_thrust` is new: a continuous (always-on),
  constant-magnitude thrust with a fixed direction in a ROTATING orbit
  frame -- VNB (velocity/orbit-normal/binormal) or RTN (radial/
  transverse/orbit-normal), re-evaluated every simulation tick from the
  spacecraft's current state (`engine.orbit_maintenance._vnb_basis`/
  `_rtn_basis`) -- rather than a direction fixed in the inertial frame,
  which would drift relative to the orbit as the spacecraft moves. Delta
  -V/propellant bookkeeping mirrors `StationKeepingConfig`'s own rocket
  -equation approach (station-keeping's burn model itself is UNCHANGED --
  still a fixed prograde reboost -- this is a separate, independent
  mechanism with its own propellant tank, addable alongside station
  -keeping on the same spacecraft). `missionstudio run` prints a
  "Constant-thrust summary" line per spacecraft, same idea as the
  existing station-keeping summary.
* **A real visual theme, an app icon, a toolbar, and assorted UI polish.**
  Direct user feedback: "looks very unfinished... not very intuitive and
  comfortable". The app previously ran on whatever the platform's native
  Qt style happened to render, with no icon and no toolbar. Now:
  * `gui/theme.py` -- one QSS stylesheet + palette (`apply_theme()`,
    called once from `gui/app.py`), on top of Qt's "Fusion" base style
    (the one built-in style that renders identically, and predictably
    styleable via QSS, across Linux/macOS/Windows). A small, consistent
    color system (one neutral slate scale + one accent blue, reused
    everywhere -- focus rings, selection highlight, the primary action
    button, progress bars) rather than per-widget rules picked ad hoc.
    Pure presentation layer: no widget's behavior, signals, or layout
    structure changed because of it.
  * `gui/icons.py` -- the app icon, drawn procedurally with `QPainter`
    (a central body + an inclined orbit ellipse + a satellite dot) rather
    than shipped as a bitmap asset, so there's no binary file to keep in
    sync with the theme's colors. Used as the window/taskbar icon
    (`app.py`) and, rendered to a real PNG under the standard XDG
    hicolor icon theme location, the Linux desktop entry's icon
    (`packaging/install.sh`, closing a gap that `Icon=missionstudio` was
    falling back to a generic icon).
  * `MainWindow` gained a toolbar (New/Open/Save, Run Simulation/Monte
    Carlo/Vizard/Check Kernels) using the SAME `QAction` instances the
    menu bar already had -- one signal connection each, so toolbar and
    menu always agree, including which actions are disabled while a run
    is in flight. "Run Simulation" is visually the primary action
    (accent-colored), the same "one obvious main button" convention a
    web app would use.
  * The results panel used to be a blank white plot with no explanation
    before any run -- now shows "Run a simulation to see results here".
  * `SpacecraftEditorDialog`'s five tabs used to share ONE height (a
    `QTabWidget` sizes every tab to fit whichever page is tallest, a
    real, easy-to-miss Qt behavior -- the "Power / propulsion / link
    budget" tab's five stacked groups forced "Orbit / mass", a third the
    height, to render with a large dead-space gap, and pushed the whole
    dialog's natural size to over 1000px tall). Caught by actually
    rendering the dialog and looking at it, not from reading the layout
    code. Fixed: each tab now scrolls independently (`_scrollable()`),
    same pattern `gui.scenario_editor.ScenarioEditorWidget`'s own
    top-level form already used.
  * The Monte Carlo group box was labeled "Monte Carlo (Phase 3)" --
    internal development-phase numbering with no meaning to an end user,
    now just "Monte Carlo".
* **Fixed a silent mass-bookkeeping bug found by a full-codebase audit.**
  `StationKeepingController`/`PhasingKeepingController`/
  `ConstantFrameThrustController` each used to recompute an ABSOLUTE
  `scObject.hub.mHub = dryMass + propellant` every tick, from their own
  construction-time-captured belief about the spacecraft's mass. That's
  fine in isolation, but two real, previously-silent failure modes fall out
  of it: (1) `station_keeping` and the new `constant_thrust` are an
  explicitly supported combination on the same spacecraft, and whichever
  controller's `UpdateState` happened to run last each tick would overwrite
  `hub.mHub`, discarding the other controller's propellant burn entirely;
  (2) a Monte Carlo `dry_mass_kg` dispersion writes directly to `hub.mHub`
  before any controller's first tick (see `engine.monte_carlo`'s "why
  `SimulationService.build(initialize=False)`" docstring section) -- the
  very first `UpdateState` call would then silently reset that dispersed
  mass back to the nominal, undispersed value, quietly defeating the
  dispersion for the rest of the run. Fixed at the root: all three
  controllers now read the spacecraft's CURRENT total mass at the top of
  each tick and subtract only what THIS tank burns THIS tick -- a
  self-contained delta, order-independent no matter how many other
  controllers or a prior dispersion already touched the same mass. The
  shared fix lives in a new `engine.propellant_bookkeeping.
  apply_propellant_burn()` (pure math, no Basilisk import -- same "pure
  math, no Basilisk" split as `engine.constellation`/
  `engine.spacecraft_templates`, and for the same reason:
  `engine.orbit_maintenance` itself can never be unit-tested in a sandbox
  without a Basilisk build, so factoring the actual arithmetic out is what
  makes `tests/test_propellant_bookkeeping.py`'s regression coverage for
  this bug possible at all).
* **A live-updating Results plot.** Previously the plot stayed on "Run a
  simulation to see results here" for the entire duration of a run, then
  jumped straight to the finished result -- no feedback beyond the
  indeterminate busy bar for however long the run took. `engine.service.
  SimulationService` gained `run_live(on_progress, live_step_s=None)`: a
  variant of `run()` that executes the simulation in small time chunks
  (repeated `ConfigureStopTime()`/`ExecuteSimulation()` pairs -- a
  documented, supported Basilisk pattern, since `ExecuteSimulation()`
  always resumes from wherever it last stopped rather than restarting)
  instead of one uninterrupted call, calling `on_progress(partial_result,
  fraction_complete)` after each chunk. Recorders keep accumulating
  samples across chunks exactly as they would across one call, so each
  chunk's result is genuinely "whatever has been logged so far", not a
  separate/approximate bookkeeping path from `run()` -- confirmed by
  `tests/test_service_run_live.py`, which checks a chunked `run_live()`
  run reproduces a plain `run()` run's final position/velocity exactly.
  The new "Live Plot" toggle (Run menu and toolbar, on by default)
  controls whether `gui.run_worker.RunWorker` drives the run through
  `run_live()` (emitting a new `progress` Qt signal per chunk, connected
  to `gui.results_widget.ResultsWidget.set_live_result()`) or the
  original one-shot `run()`; the status bar's busy indicator also becomes
  a real 0-100% progress bar instead of the indeterminate one whenever
  Live Plot is on, since `run_live()` is the one case where a genuine
  completion fraction exists. `set_live_result()` deliberately never
  rebuilds the series dropdown once it already holds the running result's
  series names (which are fixed from the first chunk -- only the amount
  of data grows), so watching a live run doesn't keep resetting whichever
  series the user is currently looking at.
* **Another full-codebase audit, this time with real fan-out coverage.**
  A single-pass review of the live-plot/mass-bookkeeping commits found
  and fixed two issues in `engine.service.run_live()`: a scenario whose
  `duration_days` is small enough to round to 0 ns via `macros.sec2nano()`
  (schema-valid -- `sim_settings.validate()` only requires `> 0`) used to
  raise a bare `ZeroDivisionError` computing `fraction_complete` instead
  of a clear error; and `_LIVE_DEFAULT_FRAMES` was lowered from 200 to 60,
  since each live callback's `_extract_results()` redoes O(samples-so-far)
  work from the FULL recorder history rather than just the new samples,
  so total extraction cost scaled with frame count. A follow-up pass
  fanned out across the rest of the codebase (GUI layer, remaining engine
  modules, schema/CLI/packaging) and found six more real, independently
  -verified bugs:
  * `gui.main_window._on_run_finished` called `ResultsWidget.set_result()`
    instead of `set_live_result()` -- so the moment a live-watched run
    actually finished, whichever series the user had selected to watch
    snapped back to the first one, undoing the whole point of
    `set_live_result()`'s selection-preserving design at the one moment
    the final data matters most.
  * `gui.kernel_status_widget.KernelStatusWidget.refresh()` had no
    re-entrancy guard: `MainWindow`'s "Check Kernels" menu/toolbar action
    calls it directly, independent of `refresh_button`'s own disabled
    -while-fetching state, so triggering it again mid-fetch reassigned
    `self._worker`, dropping the only Python reference to the
    still-running (unparented) `QThread` -- a real Qt crash risk ("QThread:
    Destroyed while thread is still running"). Now a no-op while a fetch
    is already in flight.
  * `gui.main_window.MainWindow.closeEvent` never checked whether
    `_run_worker`/`_mc_worker` was still running before accepting the
    close -- starting a run doesn't mark the scenario dirty, so closing
    the window mid-run (no cooperative-cancellation hook exists for a
    synchronous `SimulationService.run()`/`run_live()`/`run_monte_carlo()`
    call) could tear down the process out from under a live `QThread`.
    Now refuses to close (with a clear message) while either worker is
    running.
  * `engine.spaceweather.validate_file()`'s `covers_range` check compared
    a date-only (midnight) timestamp parsed from the CSV's last row
    against a full `end_utc` datetime that can carry a non-zero
    time-of-day (`scenario.epoch_utc` isn't required to be midnight) --
    so a CelesTrak file that genuinely covered the scenario's end date
    was often misclassified as not covering it, forcing an unnecessary
    fallback to synthetic (fabricated) space weather. Fixed to compare
    calendar dates.
  * `engine.time_system.utc_iso_to_spice_string()` hardcoded a literal
    `.000` milliseconds field instead of deriving it from `epoch_utc`,
    silently discarding any sub-second precision a user specified.
  * `cli.py`'s `cmd_spaceweather_resolve` had no exception handling
    around `sw.resolve()` (every other command in the file does), and
    `engine.monte_carlo.run_monte_carlo()`'s `archive_dir.mkdir(...)`
    sat outside its own `try`/`except` -- both let a real, reachable
    failure (a missing `local_file_path`; `--archive-dir` already
    existing as a plain file) surface as a raw traceback instead of this
    project's "ERROR: ..." + specific exit code convention. Both now
    report cleanly.
  * `packaging/install.sh` picked the just-built wheel with
    `ls | tail -n1` (lexicographic order) -- since `build_wheel.sh` never
    cleans its output directory, re-running `install.sh` against the same
    `--prefix` after a version bump left old and new wheels side by side,
    and `"...-1.10.0..."` sorts BEFORE `"...-1.9.0..."` as a string,
    silently installing the OLDER version. Fixed to pick by modification
    time (`ls -t`) instead, so the wheel `build_wheel.sh` just built is
    always the one selected.
* **A dedicated "Propagation setup" window, and an explicit on/off switch
  for every perturbation.** Direct feedback: gravity/integrator/space
  -weather settings were three separate, always-visible group boxes
  buried in the middle of the main scenario form, and spherical-harmonics
  gravity had no explicit enable control -- unchecking it meant zeroing
  out (and losing) whatever degree/order the user had typed. Fixed:
  * New `gui.propagation_setup_dialog.PropagationSetupDialog` -- one
    window for everything that governs how a scenario's orbits
    propagate: central body, gravity model, the numerical integrator/
    step/duration, and the space-weather source atmospheric drag reads.
    `gui.scenario_editor.ScenarioEditorWidget`'s main form now shows a
    compact read-only summary of the current settings plus a single
    "Edit Propagation Setup..." button that opens it, replacing the three
    scattered group boxes.
  * Every perturbation this app actually wires up in `engine.service` now
    has its own explicit on/off control: a new "Enable spherical
    -harmonics gravity" checkbox (GUI-only concept -- `schema.scenario.
    GravityConfig` still has just the one `central_body_degree` field,
    `0` still means point-mass; the checkbox folds back into it on OK,
    but the spin box's value is never reset by unchecking it, so
    re-checking it brings the same degree/order right back); third-body
    point-mass perturbers (already a per-body checkbox list, moved into
    the new dialog unchanged); atmospheric drag and solar radiation
    pressure (`enable_drag`/`enable_srp`, already per-spacecraft -- see
    below for why). The harmonics checkbox is also auto-disabled (and
    unchecked) whenever the central body isn't Earth, since
    `engine.service.build()` only has gravity-field data (GGM03S) for
    Earth -- the GUI can no longer construct that invalid combination in
    the first place, rather than letting the user discover it only when
    a run fails.
  * **Cannonball (orbit-only) mode already exposed every spacecraft
    parameter the active perturbations need** -- confirmed, not new:
    `dry_mass_kg`, `drag_coeff`/`drag_area_m2`, and `srp_coeff`/
    `srp_area_m2` all live on `SpacecraftEditorDialog`'s "Orbit / mass"
    tab, which (unlike Sensors/actuators/FSW/Power) is never hidden in
    "orbit_only" mode, from Phase 5's earlier drag/SRP work.
  * Caught while rendering the new dialog and looking at it, not from
    reading the layout code (same discipline as every other UI bug this
    project has found this way): a word-wrapped `QLabel`'s `sizeHint()`
    reports the width needed to lay its text out on ONE line unless
    something else constrains it -- without a cap, the dialog's intro
    label alone stretched the whole window to ~1360px wide.
* **Another audit round, two more real bugs found and fixed.** A
  fan-out re-sweep after the Propagation Setup work landed:
  * `schema.scenario.GravityConfig.validate()` never checked that
    spherical-harmonics gravity (`central_body_degree > 0`) is only wired
    up for Earth -- `engine.service.SimulationService.build()` already
    rejects any other central body with that combination, but only at
    simulation time. Without a matching schema-layer check,
    `missionstudio validate`/`Scenario.save()` (both deliberately
    Basilisk-independent, meant as an early correctness check) gave a
    clean bill of health to a scenario guaranteed to fail the moment it
    was actually run. Now rejected at the schema layer too.
  * `engine.monte_carlo`'s `dry_mass_kg` dispersion wrote its generated
    value ABSOLUTELY to `hub.mHub` (Basilisk's dispersion framework has
    no notion of "add this on top of what's already there") -- but
    `hub.mHub` is `dry_mass_kg + propellant` for any spacecraft with
    `station_keeping`/`constant_thrust` configured, not just
    `dry_mass_kg` (see `SpacecraftConfig.dry_mass_kg`'s own documented
    contract). A `dry_mass_kg` dispersion on such a spacecraft was
    therefore silently dispersing the TOTAL mass under that name --
    bounds picked to disperse just the dry mass actually dispersed dry
    mass + propellant, quietly shrinking the effective dry-mass spread by
    exactly the propellant amount on every run, with the station-keeping
    controller's own (unaffected, independently-tracked) propellant
    belief silently inconsistent with the result from tick zero. Fixed
    with two small dispersion subclasses
    (`_DryMassPlusPropellantUniformDispersion`/
    `_DryMassPlusPropellantNormalDispersion`) that add the target
    spacecraft's configured propellant back on top of the generated
    dry-mass value before it's written to `hub.mHub`, matching
    `service.py`'s own `initial_mass_kg` computation exactly. Also fixed,
    same audit: `migrations.migrate()`'s `schema_version` type check used
    `isinstance(version, int)`, but `bool` is a subclass of `int` in
    Python, so a malformed `"schema_version": true` silently passed
    through instead of raising the same clear error every other malformed
    `schema_version` value gets.

## What Phase 6 (Mission Sequence architecture) adds -- landed

A GMAT/FreeFlyer-inspired **Resources / Mission Sequence / Output**
organization, requested directly: separate "what exists" (spacecraft,
gravity, ground stations, ... -- everything the schema already had) from
"what happens, in time order" (propagate, maneuver, assign, report,
conditionals) and "what a run produced". Explicitly NOT a port of GMAT's
or FreeFlyer's own object model -- the organizing idea (resources vs. a
time-ordered sequence) is what's borrowed; everywhere Basilisk's own
architecture is a better fit than copying either tool's shape (its native
event mechanism, its continuous feedback controllers, its message/recorder
architecture, its own Monte Carlo framework), this keeps using Basilisk's
own mechanism rather than reshaping it to look like GMAT/FreeFlyer.

This phase is landing in reviewable stages, matching its own plan: data
model first (this section), then an execution engine, then file-format/
GUI-sync work, then the GUI itself -- each stage additive, so every
existing scenario file and every existing test keeps passing unchanged at
every step (confirmed after each stage: the full suite's pass count only
ever grows).

**Data model (`schema/command.py`, `schema/references.py`,
`schema/validation.py`) -- landed:**

* `schema.command.Command`: one envelope dataclass (`kind`, optional
  `label`, `params` dict, `children` for `if`/`while` nesting) covering
  the minimum command set this phase scoped: `propagate` (duration/epoch/
  event-based stop conditions -- events deliberately limited to periapsis/
  apoapsis passage for now, meant to be built on Basilisk's own
  `SimulationBaseClass.EventHandlerClass` rather than a hand-rolled
  polling loop), `maneuver` (impulsive delta-V, inertial/VNB/RTN frame --
  VNB/RTN meant to reuse `engine.orbit_maintenance`'s already-written,
  already-tested `_vnb_basis`/`_rtn_basis` helpers), `assignment`,
  `report`, `if`/`while`, `script_block`. One envelope dataclass rather
  than one Python class per kind, matching the exact shape
  `SensorConfig`/`ActuatorConfig`/`fsw_params` already use in this schema
  for the same reason (very different per-kind shapes, no
  discriminated-union (de)serialization mechanism elsewhere in this
  schema to reuse). Targeting/optimization commands are explicitly out of
  scope for now, per this feature's own scoping decision.
* `Command.validate()` is a COLLECTING validator -- returns every problem
  found in a command (and its `children` subtree) as a list, each with an
  item path, rather than raising on the first one. `Scenario.validate()`
  (unchanged, still raise-fast, exactly as before this phase) now also
  walks `mission_sequence`, folding each command's collected errors into
  one combined message per command -- still raise-fast ACROSS commands,
  preserving that method's existing behavior/contract exactly.
  `schema.validation.validate_all(scenario)` is the genuinely
  fully-collecting entry point requested: every command's every problem,
  plus every dangling spacecraft/ground-station reference across the
  whole sequence, all at once -- stated plainly in its own docstring that
  the RESOURCE side of that same call is still at-most-one-message (since
  it delegates to the unchanged, raise-fast `scenario.validate()`
  rather than retrofitting ~15 existing resource validators into
  collecting ones, which was judged out of proportion to this change).
* `Scenario.mission_sequence: list[Command] = []` -- additive, empty by
  default, so it changes nothing about how any existing scenario file
  loads, validates, or runs; `engine.service.SimulationService.run()`/
  `run_live()` are untouched. Round-trips losslessly through the existing
  JSON format (`Command` is a plain dataclass, so `dataclasses.asdict()`
  -- already how `Scenario.to_dict()` works -- recurses through it with
  no extra code; only the read direction needed a hand-written
  `Command.from_dict()`, matching every other nested dataclass in
  `Scenario.from_dict()`). The existing JSON file format itself now
  reads as GMAT's `BeginMissionSequence` split in miniature -- every
  existing top-level field is "resources", the new `mission_sequence` key
  is the sequence -- without inventing a new text format.
* `schema.references`: `find_spacecraft_references()`/
  `find_ground_station_references()` (an empty list means "safe to
  delete" -- GMAT's own "delete refused, listing every referencing item"
  behavior, which this project's spacecraft/ground-station list widgets
  did not have before this: `_on_remove()` deleted unconditionally, with
  no reference check of any kind, confirmed by reading both before
  writing this) and `rename_spacecraft()`/`rename_ground_station()`
  (FreeFlyer's "rename symbol" behavior -- renames the resource AND
  every reference to it, atomically). Every reference site is hand-listed
  (`phasing_keeping.chief_spacecraft`, Monte Carlo `dispersion.
  spacecraft`, `fsw_params['target_ground_station']`, and every command
  kind/nesting depth that can name a resource) rather than found via
  generic reflection, matching this schema's own established style
  (explicit and auditable over generic) at the cost of needing a new
  entry here whenever a new reference site is added elsewhere.

**Verification:** 62 new tests (`tests/test_command.py`,
`tests/test_references.py`, `tests/test_validation.py`, plus additions to
`tests/test_scenario_schema.py`), all Basilisk-independent (this whole
layer has no Basilisk import) -- model round-trip (including through a
real `save()`/`load_scenario()` file round-trip, and an explicit
command-ordering/reordering check), reference-integrity (find/rename,
including references nested inside `if`/`while` and the dotted-path form
`assignment.target` uses), and collecting-validation (multiple bad
commands and multiple dangling references, all reported at once, not just
the first). Full suite after this stage: 430 passed, 22 skipped (was 366
passed/22 skipped before -- the 22 skips are unrelated, pre-existing
`requires_basilisk` tests; zero regressions, zero new skips, since this
stage adds no Basilisk-dependent code).

**Execution engine (`engine/mission_engine.py`) -- landed:**

* `MissionEngine(scenario, service=None).run() -> (ResultSet, CommandSummary)`
  walks `scenario.mission_sequence` against a real `SimulationService`,
  dispatching each `Command` by `kind`. Every Basilisk call sequence is
  copied from an actually-running official example or this checkout's own
  source, not written from memory (see the module's own docstring for the
  full citation list) -- most notably:
  * `propagate` (duration/epoch): repeated `ConfigureStopTime()`/
    `ExecuteSimulation()` pairs, `ConfigureStopTime()` taking an ABSOLUTE
    cumulative time (not a delta) -- `examples/scenarioOrbitManeuver.py`'s
    own comment on this, and already exercised by this project's own
    `SimulationService.run_live()`/`tests/test_service_run_live.py`.
  * `propagate` (event -- periapsis/apoapsis): Basilisk's native
    `SimBaseClass.createNewEvent(name, eventRate, eventActive,
    conditionFunction=..., terminal=True)`, copied from
    `examples/scenarioDragDeorbit.py`'s own terminal-event block. Detected
    as a sign change in radial velocity (`dot(r, v) / |r|`) rather than
    reconstructing true anomaly every check, capped by a generous
    duration-based safety multiplier so a trajectory that never reaches
    the event raises a clear `MissionEngineError` instead of hanging.
  * `maneuver` (impulsive delta-V, inertial/VNB/RTN): `scObject.dynManager.
    getStateObject(scObject.hub.nameOfHubPosition/nameOfHubVelocity)`
    fetched once, `simHelpers.EigenVector3d2np(velRef.getState())` to read
    the current velocity, plain numpy arithmetic (VNB/RTN via
    `engine.orbit_maintenance`'s already-tested `_vnb_basis`/`_rtn_basis`),
    `velRef.setState(...)` to apply it -- the exact pattern
    `examples/scenarioOrbitManeuver.py` itself uses for its two maneuvers.
* `assignment`/`report`/`if`/`while`/`script_block` have no Basilisk-API
  precedent -- this project's own design, deliberately narrow: `assignment`
  only varies a small, hand-listed whitelist of live controller parameters
  (`thrust_n`/`isp_s` on `station_keeping`/`phasing_keeping`/
  `constant_thrust`), not generic attribute access; `report` snapshots the
  CURRENT value of requested series (GMAT `Report`-command semantics, not
  the whole time history the `ResultSet` already carries) into
  `CommandSummary.reports`; `if`/`while` conditions and `script_block` code
  run against a small, explicit namespace (`t_s`, `spacecraft[name].
  {r_BN_N, v_BN_N, altitude_m, mass_kg}`) -- `script_block` runs full,
  unrestricted Python (a deliberate trust boundary matching GMAT/FreeFlyer's
  own script commands and this checkout's own `examples/` scripts: only run
  a mission file you trust). `while` has a 10,000-iteration safety cap so a
  condition that never becomes false fails fast with a clear error rather
  than hanging.
* Every command failure raises `MissionEngineError` naming the specific
  command's path (e.g. `"mission_sequence[2].children[0] (maneuver): ..."`)
  and kind, never a bare exception from inside Basilisk/`eval`/`exec`.

**Verification:** 23 tests (`tests/test_mission_engine.py`,
`requires_basilisk`-marked like every other `engine.*` test -- this layer
imports `engine.service`, which itself needs Basilisk at import time), and
this is the first Phase 6 stage actually RUN against a real Basilisk
build (by the user, who has a working install this project's own sandbox
doesn't) rather than only written against verified-but-unexecuted call
sequences. All 23 pass now, but only after three real bugs the first
real run surfaced and this project's own "no guessing" discipline caught
by actually checking rather than assuming:

* `TimeSeries` crashed on a genuinely zero-sample recorder: a
  `mission_sequence` with no `propagate` command never calls
  `ExecuteSimulation()`, and Basilisk's own recorder accessor returns a
  bare 1-D array (losing the column count) rather than an `(0, ncols)`
  array when nothing was ever logged. Fixed in `engine/results.py`.
* Chaining each `propagate` command's absolute `ConfigureStopTime()`
  target off `scSim.TotalSim.CurrentNanos` read back after the previous
  command compounds rounding loss across segments whenever a requested
  duration isn't an exact multiple of `dynamics_task_rate_s` -- confirmed
  directly against `sim_model.cpp`: `CurrentNanos` is set to
  `NextTaskTime`, i.e. it snaps DOWN to the last task-grid point at or
  before the actual stop time. Three real chained `propagate` commands
  ended up 20 s short of one equivalent single `propagate`. Fixed by
  tracking the cumulative REQUESTED mission time in a separate counter,
  decoupled from the sim's own grid-snapped clock (`propagate`'s `event`
  stop condition is the one exception: it re-syncs to the actual,
  inherently grid-snapped firing time instead, since there's no
  requested target to track there).
* `propagate`'s `event` stop condition checked `scSim.terminate` after
  `ExecuteSimulation()` to tell whether the event fired, always reading
  `False` and raising a bogus "did not occur" error -- confirmed directly
  against `SimulationBaseClass.py` (and with a live diagnostic against a
  real Basilisk build) that `ExecuteSimulation()` unconditionally resets
  `self.terminate = False` as its own last statement before returning,
  whether the loop broke early on a terminal event or ran to completion,
  so that flag can never answer "did a terminal event fire" after the
  fact. The event mechanism itself was correct the whole time (confirmed
  by the same diagnostic: the sim genuinely stopped at the exact
  periapsis crossing, `CurrentNanos` matching the analytically-predicted
  orbital period to the second). Fixed by checking the fired event's own
  `occurCounter` via `scSim.eventMap[event_name]` instead.

A fourth finding was a wrong test assumption, not an engine bug:
`InitializeSimulation()` alone produces ZERO recorder samples (a
recorder only gets one once `ExecuteSimulation()` has actually ticked),
not one as originally assumed -- `_run_report` now raises a specific
`MissionEngineError` naming which series have no samples yet (a
`report` before any `propagate` has run) instead of a bare `IndexError`.

Test coverage itself: multi-segment `propagate` accumulating rather than
restarting (matches a single equivalent-duration `run()` bit-for-bit),
`epoch`/`event` stop conditions, both maneuver frames (checked against
the LIVE state object directly, not the recorder, since a maneuver alone
doesn't trigger a new `scStateOutMsg` write), `assignment` mutating a
live controller, `report` snapshotting the value AT that mission time
(not the final one), `if`/`while` (including nested, including the
iteration-cap safety net), `script_block` (including exception
wrapping), and clear-error cases for every "names something that doesn't
exist" case.

**File-format/CLI sync (`cli.py`, `engine/results.py`) -- landed:**

The mission-sequence JSON round-trip itself was already complete as of
the data-model stage (`Command` is a plain dataclass, so it falls out of
`Scenario.to_dict()`/`from_dict()` for free -- see that stage's own
notes). What was still missing was a way to actually RUN a
`mission_sequence` outside of a Python script calling `MissionEngine`
directly (the tests, in other words) -- there was no CLI or GUI path to
it at all. Since the GUI doesn't exist yet (Phase 6's last stage), this
stage closes that gap on the CLI side, the same "headless-first" order
the rest of this project has followed:

* `missionstudio run` now dispatches on `scenario.mission_sequence`: a
  non-empty one is executed via `MissionEngine` instead of a single
  `SimulationService.run()` call. An empty one (still the default)
  behaves exactly as before -- zero change for every existing scenario
  file, matching this whole phase's additive design.
* `engine.results.CommandSummary.export_csv()`: a Command Summary needs a
  file-format story too, not just an in-memory dataclass -- writes one
  CSV per run, long format (`report_index, t_s, label, series, component,
  value`) rather than one column per series, since different `report`
  commands can request series with different shapes (a position 3-vector
  alongside a scalar mass, say) and there is no single fixed column set a
  wide table could use across every row. `missionstudio run` writes it
  to `<out-dir>/command_summary.csv` alongside the existing per-series
  CSVs, only when at least one `report` command actually ran.
* `ReportEntry`/`CommandSummary` moved from `engine/mission_engine.py`
  (which imports `engine.service` -> Basilisk at module level) to
  `engine/results.py` (deliberately Basilisk-free, exactly like
  `TimeSeries`/`ResultSet` already are) -- a design-consistency fix
  more than new functionality: these are plain data containers with no
  Basilisk dependency of their own, and belonged with this project's
  other Basilisk-independent, synthetic-data-testable result types.

**Verification:** 3 new tests in `tests/test_results.py` (Basilisk-free,
covers the CSV's long-format shape, nested-directory creation, and the
zero-reports/header-only case). `cli.py`'s actual `run` dispatch logic
itself is not independently unit-tested (same as its pre-existing
`SimulationService`-calling code -- this file's tests only cover argument
parsing and Basilisk-free helper functions, see `tests/test_cli.py`'s own
scope).

**GUI (`gui/mission_sequence_editor.py`, `gui/mission_output_widget.py`,
`gui/run_worker.py`, `gui/main_window.py`, `gui/scenario_editor.py`) --
landed:**

The final Phase 6 stage: a `mission_sequence` is now editable and runnable
end-to-end from the GUI, not just from a scenario JSON file or a script
calling `MissionEngine` directly.

* `gui.mission_sequence_editor.MissionSequenceEditorWidget` -- a new
  "Mission sequence" group box in `ScenarioEditorWidget`, right below
  Ground stations. This is the first `QTreeWidget` used anywhere in
  `gui/` (every other list -- spacecraft, sensors/actuators, ground
  stations -- is flat); `Command` is the first schema type that nests
  (`if`/`while` carry `children`), so a tree is the first of its shape
  this app has needed. Add/Edit/Remove mirror
  `gui.sensor_actuator_editor.SensorActuatorListWidget`'s existing
  shape; Add Child (enabled only when the current selection is an
  `if`/`while`) and Move Up/Move Down are new, for nesting and ordering
  a flat list doesn't need. A tree node's `children` are always taken
  from the tree's own nesting, never from a stored `Command`'s own
  `children` field (which is deliberately cleared on every node --
  see the module's docstring) -- editing a child can never leave a
  parent's copy stale.
* `_CommandEditorDialog` -- modeled directly on
  `gui.sensor_actuator_editor._ItemEditorDialog`'s Kind-combo-plus
  -conditional-fields shape, with one page per `Command` kind (`if`/
  `while` share a page -- both are just a `condition` string). Unlike
  that dialog, this one doesn't hand-check each field: it builds a real
  `schema.command.Command` and calls its own `validate()`, so the
  dialog can never drift out of sync with what `Command.validate()`
  actually requires. `script_block.code` gets a `QPlainTextEdit` in a
  monospace font -- this is "the script editor" from the original
  Resources/Mission/Output request. Spacecraft-name fields
  (`propagate`'s event target, `maneuver`'s target, `assignment`'s
  target) are `QComboBox`es fed from a snapshot list taken when the
  dialog opens, via `MissionSequenceEditorWidget.
  set_spacecraft_names_provider()` -- mirrors
  `gui.spacecraft_editor.SpacecraftListWidget.
  set_central_body_provider()`'s existing zero-argument-callable
  convention. `assignment`'s controller/parameter fields are
  `QComboBox`es built from a small whitelist duplicated from (not
  imported from) `engine.mission_engine._ASSIGNMENT_CONTROLLERS`/
  `_ASSIGNMENT_ATTRIBUTES` -- duplicated because
  `engine.mission_engine` imports `engine.service` -> Basilisk at
  module level, and this dialog has to work with no Basilisk installed;
  kept in sync by hand, same as `_KIND_PARAM_SPECS` already documents
  doing for `engine.fsw`.
* `gui.mission_output_widget.MissionOutputWidget` -- the "debug
  console" from the original request: a new read-only "Mission Output"
  tab in `MainWindow.right_tabs` (between Results and Kernel Status)
  that lists every `report` command's `ReportEntry` in execution order
  once a `mission_sequence` run finishes, plus the total
  `commands_executed` count from its `CommandSummary`.
* `gui.run_worker.RunWorker` now dispatches on
  `scenario.mission_sequence` exactly like `cli.py`'s `cmd_run()`
  already did: a non-empty sequence runs through `MissionEngine`
  instead of `SimulationService.run()`/`run_live()` directly, and
  `finished_ok` now always carries `(ResultSet, Optional[
  CommandSummary])` instead of just a `ResultSet` -- `None` for every
  existing (`mission_sequence`-free) scenario, so nothing about the
  non-mission-sequence path changed. `MissionEngine.run()` has no
  `run_live()` equivalent (no per-command progress callback to drive
  one), so `MainWindow.on_run()` ignores the Live Plot toggle whenever
  `mission_sequence` is non-empty rather than silently hanging a
  progress bar at 0%.
* `MainWindow._on_run_finished()` switches `right_tabs` to Mission
  Output instead of Results when a run produced a `CommandSummary`,
  and clears the Mission Output tab on New/Open/Run, matching how
  Results already behaves.

**Verification:** every new/changed GUI file above has direct
`pytest-qt` coverage in `tests/gui/` (`test_mission_sequence_editor.py`,
`test_mission_output_widget.py`, plus additions to
`test_scenario_editor.py`/`test_main_window.py`). Confirmed against a
real Basilisk build (`pytest tests/ -v`): **501 passed, 8 skipped** --
the 8 skips are exclusively the "Basilisk is not installed" error
-path tests, which correctly skip once Basilisk *is* installed; every
other test in the suite ran for real, including all 23
`test_mission_engine.py` tests and this stage's own GUI tests. One
thing that pass doesn't cover: `test_main_window.py`'s
mission-sequence-dispatch tests monkeypatch `RunWorker.start` to avoid
spinning up a real thread, so no automated test yet drives a genuine
GUI click-through (build a `mission_sequence` in the running app,
click Run, watch the "Mission Output" tab populate from a live
`RunWorker` thread executing `MissionEngine.run()`) -- worth doing
once, since every prior Phase 6 stage turned up real bugs only
reachable that way, but no longer the open question this note used to
flag.

## Launching Vizard from the GUI

A **Launch Vizard** action in the Run menu/toolbar starts the external
Vizard application, added in response to a direct request. Previously
the only Vizard-related GUI surface was the Run menu's **Vizard...**
action -- renamed to **Vizard Configuration...** here to keep the two
apart -- which only configures how the *next simulation run* feeds an
already-running Vizard instance (a playback `.bin` file or a live
stream); nothing anywhere actually started the external application
itself. (An earlier version of this feature added a whole extra
"Vizard" status tab next to Results/Mission Output/Kernel Status --
scrapped after user feedback that a plain menu/toolbar action next to
the existing Vizard Configuration one, not a new persistent tab, was
what was actually wanted.)

* `gui/vizard_launcher.py` -- Basilisk-free (launching an external
  process needs no Basilisk build) module with `find_vizard_executable()`,
  `remember_vizard_executable()`, and `launch_vizard()`. Vizard ships as
  a platform `.zip` the user extracts wherever they like (see
  `docs/source/Vizard/VizardDownload.rst`'s "install in the typical
  Applications folder or Desktop") -- there is no single guaranteed
  install path, so finding it is inherently best-effort: a previously
  remembered path (persisted via `QSettings`, under
  `vizard/executable_path`) is tried first, then a shallow search of a
  handful of common per-OS locations (`/Applications`, Desktop,
  Downloads, `Program Files`, ...), and `None` if neither turns up
  anything. `launch_vizard()` resolves a macOS `.app` bundle to its real
  `Contents/MacOS/` binary before calling `subprocess.Popen` (rather
  than shelling out to `open`, which would hand off and exit
  immediately, losing any way to track whether Vizard is still running)
  and returns the live `Popen` handle.
* `main_window.py` -- a new **Launch Vizard** `QAction`
  (`self.vizard_launch_action`, distinct from the renamed
  `self.vizard_action` "Vizard Configuration..."), wired to
  `on_launch_vizard()`: a no-op while Vizard is already running (checked
  via `Popen.poll() is None` on `self._vizard_process`, the last handle
  `launch_vizard()` returned), otherwise looks the executable up via
  `find_vizard_executable()` and launches it -- falling back to a
  `QFileDialog` browse prompt (remembered via
  `remember_vizard_executable()`, so asked at most once) when it can't
  be found automatically.
* `app.py` -- gained `app.setOrganizationName("AVSLab")`, needed for
  `QSettings()` (used above with no explicit org/app name) to resolve to
  a stable per-platform settings location.

**Verification:** `tests/gui/test_vizard_launcher.py` (path search/
persistence, all real filesystem/`QSettings` I/O redirected into
`tmp_path` -- never touches the developer machine's real Vizard
install or settings), plus `test_main_window.py` additions covering
`on_launch_vizard()`'s launch/no-relaunch-while-running/relaunch-after
-exit/browse-fallback/browse-cancelled/launch-failure paths
(`find_vizard_executable`/`launch_vizard` monkeypatched so nothing
spawns a real process). This sandbox has no real Vizard binary to
launch against, so `launch_vizard()`'s actual `subprocess.Popen` call
itself (as opposed to its argument-construction logic, which the
macOS-bundle-resolution tests in `test_vizard_launcher.py` do cover) is
unverified against the real thing -- worth confirming Vizard actually
opens on a real machine with Vizard installed.

## Second round of GUI feedback

Five pieces of direct feedback from a real run against the actual GUI (a
"Simulation failed" dialog referencing `VizInterface` came with it):

* **Vizard live-stream crash, fixed.** `engine/vizard.py`'s
  `enable_vizard()` used to keep every `_AccessIndicatorBridge` alive by
  attaching them to `viz` as `viz._missionstudio_access_indicator_bridges`.
  `viz` is a SWIG proxy for a C++ `VizInterface`, and SWIG-generated
  proxy classes raise on any attribute they don't already know about --
  confirmed against the reported crash, which failed immediately with
  "You tried to add this variable: ... To this class: <...VizInterface
  ...>" before a single simulation step ran, whenever a scenario used
  the Vizard live-stream option. Fixed by having `enable_vizard()` return
  `access_indicator_bridges` alongside `viz` instead of bolting it onto
  `viz`, and having `SimulationService` retain both as plain attributes
  of itself (an ordinary Python object with no such restriction).
* **Plots now show km/km-s, not raw meters** (`results_widget.py`).
  Length/length-rate series (`units in {"m", "m/s"}` -- position,
  velocity, altitude, slant range, delta-V, ...) are converted for
  display only; a LEO position plot's y-axis used to be in the millions.
  Deliberately narrow -- everything else (accelerometer m/s^2, torque
  N*m, angles, ...) is left alone, since km-scale units would be worse
  there, not better. CSV export (`ResultSet.export_csv()`) is unaffected
  -- it keeps writing the raw SI units `TimeSeries` already holds, since
  a CSV handed to another tool should stay unambiguous.
* **A new X-axis combo** (Elapsed time / Epoch (UTC)) on the Results
  plot. `MainWindow.on_run()` captures `scenario.epoch_utc` before
  starting the run (so it reflects the scenario that was actually run,
  not whatever the editor holds by the time the run finishes) and passes
  it through `_on_run_progress()`/`_on_run_finished()` into
  `ResultsWidget.set_live_result()`. `set_result()`/`set_live_result()`
  both take an optional `epoch_utc` (default `None`), so every existing
  caller/test keeps working unchanged; "Epoch (UTC)" with no epoch
  available (or one that fails to parse) falls back to elapsed time
  rather than raising.
* **The Description box in the Scenario Editor is bigger**
  (`scenario_editor.py`'s `description_edit`, `setFixedHeight(60)` ->
  `220`) -- it needed constant scrolling to read a template's full
  description at the old size.
* **Abort a running simulation, without breaking the tool.** See its own
  section below.

**Verification:** `tests/gui/test_results_widget.py` (km conversion +
Epoch axis, including the "no epoch given"/"unparseable epoch" fallback
paths) and `tests/gui/test_main_window.py` (epoch capture/passthrough).
The Vizard crash fix has no dedicated regression test -- there is no
Basilisk-free way to construct a real `VizInterface` SWIG proxy to
assert against -- but it was confirmed against the exact real run that
originally hit it.

## Abort Simulation

Direct user feedback: "there should also be the option to abort a
running simulation, if needed, without breaking the tool." Basilisk's
`SimBaseClass.ExecuteSimulation()` is a single, blocking C++ call with no
hook to interrupt it mid-flight, and `QThread.terminate()` was
deliberately never considered -- it could leave Basilisk's C++
simulation state mid-mutation, exactly the kind of "breaking the tool"
this was asked to avoid. The design is cooperative cancellation instead,
checked between simulation chunks or mission-sequence commands -- never
a forced kill:

* `engine/service.py` -- a new `SimulationCancelled` exception carrying
  whatever partial `ResultSet` had been produced so far
  (`.partial_result`). `run_live()` gained an optional
  `should_cancel: Optional[Callable[[], bool]] = None` parameter, checked
  once after each chunk's `ExecuteSimulation()` call; when it returns
  `True`, `run_live()` raises `SimulationCancelled` with that chunk's
  results rather than silently discarding them. `should_cancel=None` (the
  default, matching every pre-existing caller) leaves behavior unchanged.
* `engine/mission_engine.py` -- the mission-sequence equivalent:
  `MissionEngineCancelled` (carrying both `.partial_result` and
  `.summary`), and `MissionEngine.__init__` gained the same
  `should_cancel` parameter, checked once per top-level command in
  `_run_commands()` -- which also naturally covers `while`-loop
  iterations, since `_run_while()` re-enters `_run_commands()` once per
  iteration -- AND, since then (see "Abort during a single long
  propagate command, fixed" below), mid-command too: a single
  `propagate` command's own `ExecuteSimulation()` call is chunked via
  `_advance_to()`/the chunked branch of `_run_propagate_event()`, not
  just between top-level commands.
* `gui/run_worker.py` -- `RunWorker` gained `request_cancel()` (sets a
  `threading.Event`, safe to call from the GUI thread while `run()` is
  executing on its own thread) and a new `cancelled` Qt signal
  (`Signal(object, object)`: partial `ResultSet`, optional
  `CommandSummary`). The non-`mission_sequence` path now ALWAYS runs
  through `run_live()` (never the plain, non-chunked `run()`)
  specifically so it's always cancellable regardless of the Live Plot
  toggle -- `self.live` now only controls whether the `progress` signal
  is actually emitted (i.e. whether the plot redraws as the run
  proceeds), not whether the run is chunked at all;
  `run_live()`'s own `_LIVE_DEFAULT_FRAMES` (60) bounds this to a small,
  fixed number of extra `ExecuteSimulation()` calls regardless of run
  length, negligible next to the actual simulated work either way.
* `main_window.py` -- a new **Abort Run** `QAction` (Run menu and
  toolbar, between Run Simulation and Live Plot), disabled except while a
  single (non-Monte-Carlo) run is actually in flight -- `on_run()`
  enables it right after starting `RunWorker`, `_stop_busy()` disables it
  again on any of finished/failed/cancelled. Monte Carlo batches are
  deliberately out of scope: `engine/monte_carlo.py`'s
  `Controller.executeSimulations()` uses a different, single-call
  execution model with no exposed chunking/cancellation hook in this
  checkout, and adding one would be unverifiable against a real Basilisk
  build in this development sandbox anyway. `on_abort_run()` calls
  `RunWorker.request_cancel()` and immediately disables the action (so
  there's nothing to double-click while waiting for the next
  checkpoint -- cancellation is cooperative, not instant); a new
  `_on_run_cancelled()` slot (connected to `RunWorker.cancelled`) shows
  whatever partial results/command summary had been produced, with
  "Run cancelled by user." status-bar messaging instead of "Run
  complete", exactly like a normal finish otherwise.

**Verification:** `tests/test_service_run_live.py` and
`tests/test_mission_engine.py` gained `should_cancel` tests
(`requires_basilisk`, auto-skipped in this development sandbox -- see
the honesty note above); `tests/gui/test_run_worker.py` covers the
dispatch/cancellation plumbing Basilisk-free by faking
`engine.service`/`engine.mission_engine` in `sys.modules` (works
regardless of whether a real Basilisk build is present); and
`tests/gui/test_main_window.py` covers the `abort_action`
enable/disable wiring plus an end-to-end real-`QThread` test proving the
`cancelled` signal is actually connected through to
`_on_run_cancelled()`. All of it (except the `requires_basilisk`-marked
engine-level checkpoint tests) was run and confirmed passing in this
sandbox; the `requires_basilisk` tests were then run for real, on an
actual Basilisk build, which caught one genuine bug:
`_run_command()` wrapped every non-`MissionEngineError` exception a
handler raised into a `MissionEngineError`, including a
`MissionEngineCancelled` bubbling up from several levels down the
command tree (e.g. cancelling mid-`while`-loop, where the cancellation
is raised inside the loop body's own nested `_run_commands()` call,
inside `_run_while()`, inside the enclosing `_run_command()`'s `try`
block) -- masking a clean, user-requested abort as a simulation
failure. Fixed by re-raising `MissionEngineCancelled` unchanged before
the generic `except Exception` clause runs (see its own comment in
`mission_engine.py`): `612 passed, 8 skipped, 1 failed` on that real
build before the fix (only `test_should_cancel_checked_between_while_
loop_iterations` failing), `613 passed, 8 skipped` on the same real
build after it -- the whole Abort Simulation feature, cancellation
inside a `while` loop included, is now confirmed against a real
Basilisk build, not just this sandbox's Basilisk-free suite.

### Abort during a single long propagate command, fixed

More direct user feedback, on the real build: clicking Abort mid-run
showed "Aborting... this takes effect at the next checkpoint, not
instantly" and then simply never finished -- minutes of waiting, no
effect. Root cause: a single `propagate` command's own
`ExecuteSimulation()` call ran straight through to its requested target
in ONE unchunked call, so `should_cancel` (only checked BETWEEN
top-level commands, per `run()`'s own docstring at the time) had no
opportunity to fire at all until that one command finished on its own --
for a mission sequence with one long `propagate` (duration/epoch/event),
that's the entire run.

Fixed the same way `engine.service.run_live()` already fixes it for the
non-mission_sequence path: chunk it.

* `_advance_to()` (new) -- runs the simulation from `self._elapsed_ns`
  to a target time, in one unchunked `ConfigureStopTime()`/
  `ExecuteSimulation()` pair when `should_cancel is None` (unchanged
  behavior, zero extra overhead), or in roughly
  `_PROPAGATE_CANCEL_CHECK_FRAMES` (60, mirroring
  `engine.service._LIVE_DEFAULT_FRAMES`) pieces otherwise, checking
  `should_cancel()` after each one and raising `MissionEngineCancelled`
  if it fires. `_run_propagate`'s `"duration"`/`"epoch"` branches now
  both call it instead of executing straight to their target.
* `_run_propagate_event()`'s safety-capped search (periapsis/apoapsis)
  got the same treatment: chunked when `should_cancel` is set, checking
  both the registered Basilisk event's own `occurCounter` (so a real
  periapsis/apoapsis crossing mid-chunk still stops the search exactly
  as before -- chunking never delays detecting it) and `should_cancel()`
  after each chunk. Its chunk size is deliberately based on the
  scenario's own `duration_days`, not `cap_days` (`duration_days *
  _EVENT_PROPAGATE_SAFETY_MULTIPLIER` -- a rarely-hit upper bound on the
  search, not a meaningful step size): sizing off `cap_days` would make
  each chunk roughly `_EVENT_PROPAGATE_SAFETY_MULTIPLIER` (10x) too
  coarse relative to how soon the event realistically fires in a real
  mission, right back to the same problem.
* `run()`'s own docstring updated to describe the new mid-command
  checkpoint, alongside the existing between-commands one.

**Verification:** two new `tests/test_mission_engine.py` cases
(`test_should_cancel_checked_mid_single_long_propagate_command`,
`test_should_cancel_checked_mid_propagate_event_command`) assert a
cancelled run's partial result is strictly shorter than letting the
same command finish would have produced -- the actual behavior this bug
report was about. The existing
`test_should_cancel_checked_between_while_loop_iterations` and the
renamed `test_should_cancel_stops_before_the_first_command_and_raises_
mission_engine_cancelled` (previously named
"...stops_between_commands..." -- its own duration was short enough
that it used to complete in a single old-style unchunked call, so
"between commands" and "before the first command" were the same thing;
now that a command can itself be chunked, the name says precisely which
checkpoint it exercises) were reworked to keep testing the
between-commands/between-iterations checkpoint specifically, now that a
command can also be interrupted mid-way. **This round has NOT yet been
re-run against a real Basilisk build** -- only this sandbox's
Basilisk-free suite (570 passed, 53 skipped, two more than before for
the two new `requires_basilisk` tests) confirms the plumbing compiles
and the untouched paths still pass; the chunk-timing arithmetic behind
the `while`-loop test's exact `commands_executed == 3` expectation, and
the event test's assumption that its chunk size lands comfortably
inside one ~90-minute orbital period, are worked out by hand in each
test's own docstring/comments, not confirmed by actually running them.

### Vizard live-stream: auto-connect instead of a manual launcher step

Direct user feedback, with a screenshot: running a live-stream scenario
showed Vizard just sitting on its own "Load Data Using One of the
Following" launcher screen doing nothing, while missionStudio itself sat
at 0% progress, elapsed time climbing, with Abort having no effect at
all no matter how long it waited.

Root cause, confirmed against `docs/source/Vizard/vizardAdvanced/
vizardLiveComm.rst` and `vizInterface.cpp` directly: in live-stream mode,
`SimBaseClass.InitializeSimulation()`'s very first step is a **blocking**
ZeroMQ handshake -- Basilisk connects out to `tcp://<vizInterface's
reqComAddress>:<reqPortNumber>` (defaults `0.0.0.0:5556`, i.e.
`localhost:5556` locally -- never overridden anywhere in this checkout)
and sends a PING it waits for Vizard to reply to, before a single
simulation step ever runs. Vizard only replies once its OWN launcher
screen has been told what to connect to (typing the address into
"Socket Address") and "Start Visualization" has actually been clicked --
skip that manual step (as our own "Launch Vizard" button previously
did -- it just started the bare app with no arguments) and that PING
never gets a reply, so `InitializeSimulation()` blocks forever. This is
native C++ with no Python-level hook at all -- not even the Abort
feature's own chunk-boundary checkpoints are reachable yet, since this
happens before the first chunk.

Fixed by never requiring that manual step in the first place: Vizard's
own `-directComm <address>` command-line flag (`docs/source/Vizard/
vizardAdvanced/vizardCommandLine.rst`) makes it connect automatically on
launch, with nothing to type or click.

* `gui/vizard_launcher.py` -- new `DEFAULT_LIVE_STREAM_ADDRESS =
  "tcp://localhost:5556"` (matching vizInterface's own unmodified
  defaults). `launch_vizard()` gained an optional `direct_comm_address`
  parameter, appended as `-directComm <address>` to the launched
  process's arguments when given.
* `main_window.py` -- `on_launch_vizard()` now passes
  `DEFAULT_LIVE_STREAM_ADDRESS` whenever Vizard Configuration is set to
  live-stream (`None`, i.e. no flag at all, otherwise -- a save-file run
  still launches Vizard exactly as before), and returns `True`/`False`
  instead of nothing, so a caller can tell whether Vizard is actually
  confirmed running. `on_run()` calls it FIRST, before starting a
  live-stream run's `RunWorker` at all, refusing to start (with a clear
  explanation, never a silent hang) if Vizard couldn't be confirmed --
  an ordinary (non-live-stream) run never touches Vizard at all, so this
  adds no new behavior there.

**A residual gap, since closed:** the first version of this fix only
covered the case where `on_launch_vizard()` was actually starting a new
Vizard instance -- an ALREADY-running one (e.g. launched earlier in the
same session for a save-file run, or before Vizard Configuration was
ever set to live-stream) was still trusted as-is, matching the
pre-existing "never relaunch while already running" behavior, so the
same hang could still happen one launch later. Closed by tracking which
`-directComm` address (if any) `self._vizard_process` was actually
launched with (`self._vizard_direct_comm_address`): `on_launch_vizard()`
now only trusts an already-running instance if it already matches what
this call needs -- a mismatch (specifically, live-stream needed but the
tracked instance has no live-stream connection) terminates it
(`_terminate_vizard_process()`: `terminate()`, then `kill()` only if it
doesn't exit within a bounded 5 s wait) and relaunches a correct one in
its place. The other direction (a live-stream-ready instance already
running, but a save-file/no-request launch is what's needed now) is
deliberately left alone -- `-directComm` being active doesn't stop
Vizard from also opening a save file. An instance this session never
itself launched (`self._vizard_process` is still `None` -- started by
the user outside missionStudio entirely, or in an earlier session) is
still left completely alone rather than killed -- there is no reliable
way to ask an arbitrary already-running Vizard process "are you actually
connected" from outside it, so a second, correctly-configured instance
is launched alongside it instead of guessing about (or killing) a
process this app doesn't own. That specific case -- an untracked,
already-running, not-actually-connected Vizard instance -- is the one
genuinely irreducible gap left: there is nothing missionStudio can
inspect from outside to detect it.

**Verification:** `tests/gui/test_vizard_launcher.py` gained two new
`launch_vizard()` tests (the flag is appended when given, omitted when
not); `tests/gui/test_main_window.py` gained eight new tests covering
`on_launch_vizard()`'s address selection, the mismatch-relaunch/
matching-instance-kept/untracked-instance-left-alone cases above, and
`on_run()`'s new Vizard-confirmation gate (including that an ordinary
run never calls `on_launch_vizard()` at all). All pass in this sandbox
(580 passed, 53 skipped). Like the Vizard crash fix earlier in this
document, there is no way to exercise a real Vizard connection handshake
without an actual Vizard binary and display, so the `-directComm` flag's
effect on Vizard itself (as opposed to the argument list missionStudio
constructs, and the process-tracking logic around it) is unverified
here -- report back if a live-stream run still doesn't
connect after this.

**One remaining click, made obvious instead of silent** (further direct
user feedback, after the fix above): `-directComm` pre-fills Vizard's
socket address field and pre-selects DirectComm/Live Display, but does
NOT click Vizard's own "Start Visualization" button -- confirmed by
this same user actually running it, contradicting `vizardLiveComm.rst`'s
more optimistic-sounding wording. Checked directly against
`vizardCommandLine.rst` for an alternative: the only documented flag
combination that skips this click entirely is `-batchmode -noDisplay`,
which is headless OpNav mode -- it renders nothing to the screen at all,
which defeats the entire point of a LIVE VISUALIZATION. No flag exists
(documented, at least) that both skips the click and keeps the visible
3D view, so this one click could not be eliminated outright.

Made unmissable instead: `MainWindow.__init__` gained
`self._vizard_live_stream_hint_shown = False`. The first time
`on_launch_vizard()` actually starts a NEW Vizard process with a
`-directComm` address in a given session, it shows a one-time
`QMessageBox.information` explaining exactly this -- that the address is
already filled in, but "Start Visualization" still needs one click in
Vizard's own window before the run can proceed -- rather than leaving
the user to wonder (again) why the run looks stuck. Every launch (not
just the first) also gets an updated status-bar message saying the same
thing more briefly, for when the hint dialog isn't shown again. The
dialog deliberately fires only once per session, not once per
launch/run, so it doesn't turn into a repeated interruption once the
user already knows what to do.

**Verification:** `tests/gui/test_main_window.py` gained
`test_launch_vizard_shows_the_one_click_hint_once_per_session` (fires
exactly once even across repeated `on_launch_vizard()` calls); the four
existing tests that trigger a real live-stream launch had
`QMessageBox.information` mocked so the new dialog doesn't block them.
581 passed, 53 skipped in this sandbox. As with the fix above, there is
no way to confirm the dialog's wording matches what a user actually
needs without a real Vizard binary and display to try it against.

## Three more real-run bugs, caught by the user testing templates

All three were caught by the user actually clicking through the bundled
templates one by one, with screenshots -- not found by this sandbox's
own (Basilisk-free) test suite, which had no way to catch any of them.

**1. Templates '05' and '07' failed to run: missing sun ephemeris.**
`SimulationService.build()` raises a clear `SimulationServiceError` when
any spacecraft has `power`/`station_keeping`/`enable_srp` configured but
`'sun'` isn't in `gravity.third_body_perturbers` (`simpleSolarPanel`/the
eclipse gate/SRP all need a real eclipse shadow factor, which needs a
sun ephemeris) -- exactly the error the user hit on both '05' (formation
flying, `station_keeping` required by `phasing_keeping`) and '07'
(attitude pointing with ADCS hardware, has a `PowerConfig`). Both
templates' own `scripts/_generate_templates.py` builder functions
simply never included `third_body_perturbers=["sun"]` in their
`GravityConfig` -- a real bug in this project's own bundled templates,
not a user configuration mistake. Fixed at the source (the generator
functions, each with a comment explaining why) and regenerated both
JSON files (`python3 scripts/_generate_templates.py`, run from
`missionStudio/`) -- every other template was already correct, so only
these two files changed.

Also promoted to a **schema-level check**: `Scenario.validate()` gained
a mirror of this same engine-layer condition, following the exact
precedent `GravityConfig.validate()` already set for the
`central_body_degree`/`central_body` mismatch (see its own comment) --
without this, `missionstudio validate`/the GUI's live "valid" indicator
(both Basilisk-independent) would keep reporting a clean bill of health
for a scenario guaranteed to fail the moment it's actually run, exactly
as it did here. Now caught immediately in the editor, not after
clicking Run.

**Verification:** a scan of all 9 bundled templates (any spacecraft with
`power`/`station_keeping`/`enable_srp` but no `'sun'` third-body
perturber) confirms only '05'/'07' were affected and both are now
clean. `tests/test_scenario_schema.py` gained
`test_power_station_keeping_or_srp_without_sun_third_body_is_rejected`/
`..._with_sun_third_body_validates`/
`test_no_power_station_keeping_or_srp_does_not_need_sun_third_body`
(parametrized over all three triggering fields), plus fixed seven
existing tests whose own fixtures had exactly this same gap (legitimate
staleness this new check exposed, not false positives -- those fixtures
would already have failed at `SimulationService.build()` if ever run
for real). 588 passed, 53 skipped in this sandbox.

**2. Load Scenario's description text was unreadable.** Screenshot:
near-invisible light-gray-on-white text. Root cause: several widgets'
own inline stylesheets use `"color: palette(mid);"` for muted hint/
description text (`LoadScenarioWidget`'s template description,
`SpacecraftTemplateDialog`'s description, several "how to use this
field" hints across the spacecraft/sensor/mission-sequence editors) --
`QPalette.Mid` was never explicitly set by `gui/theme.py`'s
`apply_theme()`, so it stayed at Qt's own computed default (a subtle
3D-bevel shading tone meant for shadow lines, not body text), which
reads as near-invisible against this theme's light background. Fixed
with a single one-line change in `theme.py` -- `QPalette.Mid` mapped to
the same `text_muted` color the theme already uses for
`PlaceholderText` -- which fixes every `"palette(mid)"` usage across the
whole app at once, not just `LoadScenarioWidget`. Confirmed visually
with an offscreen-rendered screenshot of both `LoadScenarioWidget` and
`SpacecraftTemplateDialog` before considering this done, not just by
reading the CSS.

**Verification:** `tests/gui/test_theme.py` gained
`test_mid_palette_role_is_readable_not_left_at_qt_default`. 589 passed,
53 skipped in this sandbox.

**3. Template '06' crashed with a confusing internal error.**
`'ClassicElements' object has no attribute 'AN'`. Traced directly (not
guessed) to a genuine bug in Basilisk's OWN `src/utilities/
orbitalMotion.py`: `rv2elem()`'s NaN-input guard sets `elements.AN`/
`elements.AP`, but `ClassicElements.__slots__` only defines `Omega`/
`omega` (no `AN`/`AP` at all) -- so instead of returning a clean all-NaN
element set for a non-physical (NaN) position/velocity sample, it
crashes with that `AttributeError`. `engine.service._osculating_elements`
calls `rv2elem()` once per recorded sample (to plot how the orbit's
shape/orientation evolves over the run) -- reaching this crash means the
spacecraft's OWN propagated position/velocity had already gone
non-physical partway through the run, an actual numerical instability
this sandbox has no Basilisk build to reproduce or trace further (inertia
`_INERTIA_MEDIUM` and `mrpFeedback` gains `K=3.5`/`P=30` both look like
reasonable, standard-example-scale values on inspection, not an obvious
mismatch, but that's as far as static inspection alone can go).

Fixed what's actually fixable from here: `_osculating_elements` now
checks each sample for `NaN`/`inf` itself, before ever calling the
buggy `rv2elem()`, and raises a clear, actionable
`SimulationServiceError` naming the sample index and likely causes
(control gains too aggressive for the inertia/rates involved, excessive
actuator torque, too coarse a `dynamics_task_rate_s`) instead of that
confusing `AttributeError` -- turning an inscrutable crash into a
diagnosable one. The Basilisk-side bug itself is not patched here (out
of scope for this checkout's own code); this is a defensive workaround
on the missionStudio side.

**This does NOT fix why template '06' actually diverges** -- only makes
the failure mode legible instead of cryptic. If it still fails after
this, the new error message will say which recorded sample first went
non-physical (and, from `sim_settings.dynamics_task_rate_s`, roughly
what elapsed time that corresponds to) -- that detail would help narrow
down the real cause on a real Basilisk build, which this sandbox cannot
do.

**Verification:** new `tests/test_osculating_elements.py`
(`requires_basilisk`, auto-skipped in this development sandbox --
`engine.service` imports Basilisk at module level) directly exercises
`_osculating_elements` with a synthetic NaN/inf sample, confirming the
clear error fires instead of the `AttributeError`, alongside a
finite-input sanity check. 589 passed, 56 skipped in this sandbox
(three more skipped, matching the three new `requires_basilisk` tests).
**Confirmed for real** on the user's own real Basilisk build, right
after this shipped: re-running '06' produced exactly the new message
("the simulated position/velocity became non-physical (NaN/inf) at
recorded sample 15 of 73...") instead of the old `AttributeError` --
the diagnostic works as designed. The underlying divergence itself is
still open; that sample index/count is the concrete lead needed to
chase it further, next.

## Template '05' crashing with heap corruption, root-caused

Direct follow-up from the "template '06' crashed with a confusing
internal error" entry above: the user then hit template '05' (formation
flying, `station_keeping` + `phasing_keeping`) crashing too -- but with
TWO DIFFERENT native crash signatures on different runs of the exact
same scenario (`basic_string::_M_create`, then `std::bad_alloc`). That
variability is the signature of genuine memory corruption, not a
deterministic bug -- exactly like the very first Vizard crash earlier in
this project (a Python object garbage-collected while Basilisk's C++
side still held a live callback into it).

Root cause, this time: `PhasingKeepingController.UpdateState()` (called
every dynamics tick, directly by Basilisk's C++ scheduler through a SWIG
director override) calls `orbitalMotion.rv2elem()` via its own
`_mean_anomaly()` helper, to compute the chief/follower's current mean
anomaly for the phasing control law. That's the exact same buggy
Basilisk function `engine.service._osculating_elements` was already
fixed to avoid (see above) -- but `_osculating_elements` is ordinary
Python code with an ordinary `try`/`except` around it; `UpdateState()`
is not. A Python exception escaping a SWIG director-overridden virtual
method is undefined behavior, not a clean propagated exception -- which
is exactly consistent with two different native crashes from the same
root cause on different runs.

The state fed into `rv2elem()` there comes straight from
`scStateInMsgA()`/`scStateInMsgB()` with no validity check at all --
either genuinely non-physical (the simulation having already diverged)
or simply not written yet (read before either spacecraft's own dynamics
has published a first sample this run, an ordering question this
function has no control over). Either way, calling `rv2elem()` with it
was never safe.

Fixed in `engine/orbit_maintenance.py`: both `PhasingKeepingController.
UpdateState()` and `StationKeepingController.UpdateState()` (the same
class of risk -- a non-finite or exactly-zero velocity would otherwise
divide-by-zero computing a thrust direction) now check the spacecraft
state for finiteness (and, for station-keeping, non-zero velocity)
*before* doing anything with it. On a non-finite/degenerate tick, both
command zero thrust and log a placeholder (NaN error/altitude, matching
every other tick's log-once-per-call invariant) rather than ever
reaching the buggy call -- there is no safe way to raise from inside a
director callback either, so "degrade gracefully, never crash" is the
only sound option here regardless of why the state went bad.

**This does not, by itself, explain why the state went non-physical (or
unwritten) in the first place** -- same honesty as the '06' entry above.
But it does mean template '05' can no longer crash the whole process
over it: if the underlying cause is "read before write" (an ordering
question), the controller will now simply no-op for a tick or two until
real data arrives; if the underlying cause is a genuine divergence, the
run will still fail, but cleanly -- most likely via
`_osculating_elements`'s own clear `SimulationServiceError` during
result extraction, exactly like '06' now does, rather than a crash with
no useful message at all.

**Verification:** four new tests in `tests/test_orbit_maintenance.py`
(`requires_basilisk`, auto-skipped in this sandbox) construct each
controller directly, write a `SCStatesMsg` with NaN (or, for
station-keeping, zero-velocity) state, call `UpdateState()` directly,
and confirm it returns cleanly with zero commanded thrust instead of
reaching `rv2elem()` -- plus one confirming the guard doesn't change
behavior for the ordinary finite-state path. 590 passed, 60 skipped in
this sandbox (four more skipped, matching the four new tests).

**Confirmed for real** on the user's own Basilisk build: the fix itself
worked first try -- `UpdateState()` returned cleanly with no crash on
every non-finite/degenerate-state test, exactly as designed. Three of
the four new tests still failed, but only on an assertion detail: a
real `ExtForceTorque`'s `extForce_N` reads back as a nested `[[0.0],
[0.0], [0.0]]` column-vector shape, not the flat `[0.0, 0.0, 0.0]` list
these tests assumed -- fixed with a small `_flat()` helper. That same
real run also re-confirmed every other fix from this session still
holds: both sun-ephemeris-validation directions, all four
`should_cancel` checkpoints, `run_live` cancellation, the toolbar split,
and templates '05'/'06'/'07' all loading/validating/round-tripping
cleanly (639 passed, 8 skipped, only the three assertion-shape failures
above, now fixed).

## A toolbar action invisible on one real platform

Direct user report, with a screenshot: the "Launch Vizard" toolbar
button was simply not there -- while confirmed present in the **Run**
menu (built from the exact same `QAction` object as the toolbar button),
ruling out a construction failure. `_build_toolbar()`'s single,
un-movable `QToolBar` held 9 text-beside-icon buttons plus 2 separators
-- wide enough that real-world font/DPI rendering on at least one real
desktop environment ran out of horizontal room before the window itself
did, something this sandbox's own offscreen-Fusion-style screenshots
never reproduced (they consistently rendered narrower). Rather than
chase the platform-specific overflow behavior itself (Qt's overflow
handling for a fixed single-row toolbar is not obviously predictable
across styles/platforms), removed the dependency on window width
entirely: `_build_toolbar()` now builds two shorter, fixed rows (File
ops + Run ops; Vizard + Check Kernels) via `addToolBarBreak()`, each
comfortably narrow enough to never need to overflow at all.

**Verification:** confirmed visually with offscreen screenshots at both
the default window width and a deliberately narrower one (1000px) --
every button fully visible at both. `tests/gui/test_main_window.py`
gained `test_toolbar_actions_are_all_visible`, asserting every one of
this window's actions is present on one of the (now two)
`QToolBar`s and actually visible, not just constructed as a `QAction`
object somewhere. 590 passed, 56 skipped in this sandbox. Not
independently confirmed against the specific real platform/window size
that originally lost the button (this sandbox has no way to reproduce
that environment), but the fix removes the mechanism (window-width
-dependent single-row overflow) entirely rather than patching around a
guessed cause, so it should hold regardless of the exact platform
details.

## Template '05' crash recurred -- added a debug-logging mode

The "root-caused" fix above turned out not to be the whole story: the user
hit the **same** `basic_string::_M_create`/`std::bad_alloc` crash again on
template '05', on a build that already had the `orbit_maintenance.py`
finiteness guards deployed and confirmed working (per that section's own
"Confirmed for real" note). That rules out the guarded `rv2elem()` call
sites as the *only* source -- there is some other path into this crash
that guarding those two call sites didn't cover, and guessing at more
call sites blind, the same way the first fix was found, was not working.

What actually blocked root-causing it further: this app had **no
diagnostic output anywhere**. Every background-thread failure (`RunWorker`,
`MonteCarloWorker`, the kernel-fetch worker) was caught with a bare
`except Exception as exc: self.failed.emit(str(exc))` -- the GUI shows a
one-line message, nothing is logged, and the terminal the user launched
`missionstudio-gui` from prints nothing but Unity's own startup noise. A
native crash inside a SWIG director callback (see above) doesn't even
leave that much -- there is no Python traceback to catch in the first
place. Direct user request: "would be good, if you could add some kind of
debug mode, that outputs everything that happens in the terminal and also
saves it in a log file."

Added `missionstudio/logging_setup.py`: a single `configure_logging()`
entry point, called once as the very first line of both `cli.main()` and
`gui.app.main()` (idempotent -- `cli.main()` dispatching into
`gui.app.main()` for `missionstudio gui` must not double up handlers).
It attaches two handlers to the root logger -- a `FileHandler` at
`~/.missionstudio/logs/missionstudio_<UTC timestamp>.log` (`DEBUG` level,
so nothing is filtered out of the file) and a `StreamHandler` on stderr
(`INFO` level, so the terminal stays readable) -- and installs
`sys.excepthook` so an exception that would otherwise just crash silently
is logged with its full traceback before the process exits. The three
background-worker `except Exception` catch-alls (`run_worker.py` x2,
`kernel_status_widget.py`) now call `logger.exception(...)` before
emitting their `failed` signal, so a worker failure's full traceback lands
in the log file, not just the one-line message the GUI dialog shows.
`main_window.py`'s "Simulation failed"/"Monte Carlo failed" dialogs now
also name the current log file's path directly in the dialog text, so the
next report doesn't depend on the user knowing where to look.

This does not, by itself, fix the template '05' crash -- a crash
originating inside a SWIG director callback can still take the whole
process down before Python-level logging gets a chance to run (the same
reason `orbit_maintenance.py`'s guards can only degrade gracefully, never
raise). But it turns every *other* class of failure -- anything that
raises a normal Python exception anywhere in this app, including on a
background thread -- into something with an actual traceback to read
afterward, and it is the only way forward for the next reproduction: if
the crash again leaves nothing in the log file, that itself narrows it
back down to "inside Basilisk's C++/SWIG layer, not this app's Python
code," which the two conflicting crash signatures already suggested but
didn't confirm.

**Verification:** `tests/test_logging_setup.py` (7 tests, no
Basilisk/Qt dependency, run unconditionally) cover log-file creation,
idempotency, an exception logged via `logger.exception()` landing in the
file with its full traceback, and the `sys.excepthook` install. Three new
`tests/gui/test_main_window.py` tests confirm the failure dialogs mention
the log file's path when logging is configured and omit the hint
otherwise. Running `cli.main()` directly (as `tests/test_cli.py` already
does, dozens of times, without a subprocess) now triggers a real
`configure_logging()` call every time this suite runs -- an autouse
`tests/conftest.py` fixture isolates it per test (resets
`logging_setup`'s internal state, redirects `Path.home()` to a per-test
`tmp_path` so nothing touches this machine's real
`~/.missionstudio/logs`, and restores the root logger's handlers/level
and `sys.excepthook` afterward) so no test leaks a stale `StreamHandler`
bound to a since-closed, pytest-captured `stderr` into any later test.
600 passed, 60 skipped in this sandbox. Not yet confirmed against a real
Basilisk build -- that confirmation depends on the user reproducing the
template '05' crash again and sharing the new log file's contents, which
is the actual blocker on finishing the root-cause fix.

**If you hit this (or any other) crash:** the log file's path is printed
at GUI/CLI startup and is also named directly in any "Simulation
failed"/"Monte Carlo failed" dialog. Check
`~/.missionstudio/logs/missionstudio_<timestamp>.log` (the most recent
one) for a full traceback before reporting a crash -- it will have far
more detail than whatever the dialog or terminal showed on their own.

## Template '05' crash, actually root-caused this time

The logging mode above paid off immediately: the user reproduced the
crash and the new log file's traceback showed something genuinely
different from every earlier assumption in this project's history --

```
RuntimeError: std::bad_alloc
  File ".../missionstudio/engine/service.py", line 1023, in run_live
    self.scSim.ExecuteSimulation()
  File ".../Basilisk/utilities/SimulationBaseClass.py", line 2006, in ExecuteSimulation
    self.TotalSim.StepUntilStop(...)
  File ".../Basilisk/architecture/sim_model.py", line 1524, in StepUntilStop
    return _sim_model.SimModel_StepUntilStop(self, SimStopTime, stopPri)
```

A clean, catchable Python `RuntimeError` -- not a raw native crash with no
Python frame at all. That directly contradicts this project's own earlier
theory (written into `orbit_maintenance.py`'s guard comments): that a
Python exception escaping `UpdateState()` (a SWIG director callback) is
undefined behavior, and that's what produced the two different crash
signatures. Reading Basilisk's actual C++ source
(`src/architecture/system_model/sim_model.cpp`) shows that theory was
wrong -- `SimThreadExecution`'s worker-thread loop wraps every tick in
`catch (...) { threadException = std::current_exception(); }`, and the
parent thread cleanly `std::rethrow_exception`s it, which SWIG surfaces
as an ordinary Python exception. No UB; this project's Basilisk version
has real cross-thread exception safety.

The ACTUAL mechanism, found by then reading
`src/simulation/dynamics/_GeneralModuleFiles/svIntegratorAdaptiveRungeKutta.h`
(the code behind `rkf45`/`rkf78`, the integrators this project's
templates use): once the integrated state goes non-finite (NaN/inf, from
any cause), `computeMaxRelativeError()` returns NaN. The step-acceptance
check `maxRelError <= 1.` is then always false (every comparison against
NaN is false in IEEE 754), so `integrate()`'s `while (time < startingTime
+ desiredTimeStep)` loop never advances `time` and never exits. Worse,
the "shrink the step and retry" fallback that would normally recover from
a rejected step can't either: `std::min`/`std::max` called with a NaN
first argument return that same NaN argument (both are implemented as
`(b < a) ? b : a`, and any `< NaN` comparison is false), so the computed
`newTimeStep` stays NaN forever too. The result is a genuine infinite
C++ loop, re-evaluating the same NaN state and allocating fresh `Eigen`
temporaries every iteration, until the process's heap is exhausted --
`std::bad_alloc` (a clean allocation failure) on one run, heap corruption
(`basic_string::_M_create`, an unrelated allocation tripping over an
already-exhausted/corrupted heap) on another: same root cause, whichever
allocation happens to be the one that finally fails. This also explains
the near-instant crash timing (the whole thing happens inside one C++
call, a tight allocate-and-retry loop with no artificial delay) regardless
of how much simulated time had already completed successfully before it.

**What is NOT the cause, now confirmed:** the `orbit_maintenance.py`
finiteness guards (the earlier fix) were never wrong to add -- a
non-finite spacecraft state was never safe input to `rv2elem()` -- but
they were never going to be *sufficient* either. The state can go
non-finite entirely inside Basilisk's own equations-of-motion/integrator,
strictly between one tick's guarded read and the next, with no Python
-level hook in between to catch it. `orbit_maintenance.py`'s own comments
are corrected to reflect this (and to drop the wrong "UB" claim).

**What this project CAN fix**, since the underlying integrator bug lives
in Basilisk's own C++ (not something this app controls, and not
something a from-source rebuild is practical to depend on here -- see
this README's own "Environment honesty note" on why a from-source build
has historically been avoided): turn the resulting crash into an
immediately actionable message instead of a bare native exception string.
New `engine.service.raise_clear_execution_error()` wraps every
`scSim.ExecuteSimulation()` call in this codebase (`SimulationService.run()`/
`run_live()`, and all three call sites in `MissionEngine._advance_to()`/
`_run_propagate_event()`) in `try`/`except RuntimeError`, re-raising as a
`SimulationServiceError` that explains the actual mechanism above and
points at the concrete things that commonly cause a state to go
non-physical in the first place (a runaway commanded force/torque -- check
station-keeping/phasing-keeping/constant-thrust configuration for a sign
or magnitude error -- or an orbit decaying into the central body).
`SimulationService.run_live()` also now logs progress (`INFO`, sim time
and percent complete) after every chunk, and logs an `ERROR` with exactly
how far the mission clock got before a failure -- so a future crash's log
file will show precisely which portion of the run diverged, rather than
leaving that as a guess.

This still doesn't identify *why* template '05' specifically ends up with
a non-finite state in the first place -- that remains open, and would
need either a reproducible local Basilisk build (not available in this
sandbox) or the user narrowing down which of the two spacecraft's
controllers (or plain two-body dynamics) is responsible from a future,
now-far-more-informative log file. But "Run failed: std::bad_alloc" with
nothing else to go on is no longer where this ends.

**Verification:** `tests/test_service_execution_errors.py` (3 tests) and
one new test in `tests/test_mission_engine.py`
(`test_propagate_translates_execute_simulation_runtime_error`), all
`requires_basilisk` (auto-skipped in this sandbox): construct a real
`SimulationService`/`MissionEngine`, monkeypatch the real, already-built
`scSim.ExecuteSimulation` to raise `RuntimeError("std::bad_alloc")` (an
injected failure -- reproducing the actual integrator bug isn't a
reliable thing to build a fast unit test around), and confirm a
`SimulationServiceError` mentioning "non-physical" is raised with the
original exception preserved as `__cause__`. 600 passed, 64 skipped in
this sandbox (4 more skipped, matching the 4 new tests).

**Confirmed for real** on the user's own Basilisk build: 655 passed, 1
failed, 8 skipped. The one failure was a bug in the new MissionEngine
test, not in the production fix --
`test_propagate_translates_execute_simulation_runtime_error` asserted
that `SimulationServiceError` propagates out of `engine.run()`
unwrapped, but `MissionEngine._run_command()`'s existing generic
`except Exception` handler (the same one that already wraps, say, a
script-block exception -- see
`test_script_block_exception_is_wrapped_in_mission_engine_error`) wraps
ANY non-`MissionEngineError`/`MissionEngineCancelled` exception into a
path-qualified `MissionEngineError` -- correct, existing behavior the
test just modeled wrong. Fixed by asserting `MissionEngineError`
instead (whose message still contains the clear "non-physical"
explanation). `SimulationService.run()`/`run_live()`'s own two tests,
which are not wrapped by anything, passed as written the first time.

## Template '05' crash, narrowed further -- last-known-state diagnostic

The clear-error fix above paid off immediately: the user reproduced the
crash again, and the new error and log showed something genuinely
useful for the first time --

```
run_live: ExecuteSimulation failed at t=10080.0 s of 604800.0 s (1.7% complete)
```

The failure is in the very FIRST live chunk (`run_live`'s default chunk
size for this scenario -- `max(dynamics_task_rate_s, duration_days*86400
/60)` -- works out to 10080 s, about 336 dynamics ticks). 10080 s is
under two orbital periods for this scenario's ~550 km circular orbit
(period ≈ 5740 s) -- so whatever drives the state non-finite happens
almost immediately, not from a slow multi-day drift. That rules out a
large class of otherwise-plausible explanations (e.g. propellant
depletion, a multi-day accumulated phasing error) -- there simply isn't
enough elapsed time for those.

Reasoning through `orbit_maintenance.py`'s actual numbers for this
template by hand (`target_altitude_km=550`, `thrust_n=0.05`,
`target_separation_km=50`, `max_delta_semi_major_axis_km=3.0`) suggests
the commanded maneuvers themselves are tiny (a back-of-envelope
phasing correction here works out to on the order of tens of METERS of
semi-major-axis change, a few cm/s of delta-v) -- nowhere near large
enough on their own to explain a near-instant divergence. One real,
separate finding from this exercise: `PhasingKeepingConfig.
target_separation_km`'s docstring and validation (`schema/scenario.py`)
define it as a distance strictly "ahead of the chief" (validated `> 0`
only, no way to express "behind"), but template '05's own description
and initial conditions (follower's `true_anomaly_deg=-0.5` vs chief's
`0.0`) explicitly set up and describe a TRAILING formation. Worth fixing
as its own follow-up (either allowing a signed value, or documenting
that "ahead"/"behind" is just a label and the schedule is always
interpreted as the magnitude of `mB - mA`), but the hand-computed
maneuver size shows this specific mismatch is not large enough to be
what crashes here.

Without a local Basilisk build to actually step through this, further
narrowing by hand-reasoning about the physics has reached its limit --
what's actually needed is the state at the exact moment it goes
non-finite, which no existing diagnostic captured (the failing tick
itself is never recorded at all -- see `raise_clear_execution_error`'s
own docstring for why). New `SimulationService.log_last_known_state()`,
called right before `raise_clear_execution_error` re-raises at all four
`ExecuteSimulation()` call sites, logs (`ERROR`) the LAST successfully
recorded sample for every spacecraft straight from each handle's own
recorder/controller logs -- position/velocity, and (when configured)
station-keeping's altitude/burn-on/propellant and phasing-keeping's
separation error/state-machine state -- deliberately bypassing
`_extract_results()`/`_osculating_elements()` (which would itself raise
on a non-finite sample) so this works even if the last state is already
bad. This is the closest thing to a debugger breakpoint available
without one: the next crash's log file will show exactly where each
spacecraft was, what each controller was doing, and how far each
propellant tank had been drawn down, one tick before Basilisk's own
stepping failed.

**Verification:** two new tests in `tests/test_service_execution_errors.py`
(`requires_basilisk`, auto-skipped in this sandbox) -- one confirms the
method doesn't raise before any tick has completed (logs "no samples
recorded yet" instead), the other runs a few real dynamics ticks first
and confirms the logged text actually contains `r_BN_N=`/`v_BN_N=` data.
600 passed, 66 skipped in this sandbox (2 more skipped, matching the 2
new tests). Not yet confirmed against a real Basilisk build -- that
confirmation depends on the user reproducing the crash again and sharing
the new log, which will finally show the exact last-good state rather
than just which chunk failed.

## Template '05' crash -- root cause found and fixed at the template level

The last-known-state diagnostic paid off immediately -- the user's next
crash log showed:

```
follower-1: last recorded state before failure -- t=30.000 s, r_BN_N=[...] m, v_BN_N=[...] m/s
follower-1: phasing_keeping last tick -- t=30.000 s, error=-0.0882 deg, state=BURN_OUT, ...
```

The state at t=30 s (the very FIRST dynamics tick) is completely sane --
hand-verified against a from-scratch two-body propagation in plain numpy
(no Basilisk needed) that matched the logged r/v to 6+ significant
digits. The failure happens between t=30 s and t=60 s -- the SECOND
tick, as early as this scenario's finest possible resolution can show.

That ruled out slow drift/depletion explanations and pointed at the
`phasing_keeping` error value itself: -0.0882 degrees, when the actual
along-track separation between these two near-identical orbits (0.5
degrees apart by construction) plus the 50 km/6928 km target works out to
-0.9135 degrees by hand -- a ~10x, suspiciously specific discrepancy.
Root cause, found by reading `orbitalMotion.rv2elem()`'s real algorithm
(`src/utilities/orbitalMotion.py`): this template's two orbits were
defined with `eccentricity=0.0` EXACTLY. `rv2elem()` has a dedicated
branch for a genuinely circular orbit (`e < 1e-11`) that measures the
along-track phase from the ascending node -- numerically stable. But this
scenario's real, propagated eccentricity (perturbed by the sun
third-body gravity this project added earlier to fix a different bug,
and by the phasing controller's own commanded thrust) only needs to
drift a hair above that extremely tight threshold to fall onto a
DIFFERENT branch, which measures the same angle from the eccentricity
vector's direction instead -- numerically meaningless once eccentricity
is that close to zero, since that direction becomes dominated by
floating-point noise rather than physics. Reproducing the real crash's
logged state through that unstable branch by hand gave
argument-of-periapsis values 160 vs 184 degrees apart for two spacecraft
that are physically 0.5 degrees apart -- a ~24 degree spurious
"separation," matching the instability's fingerprint exactly.

**A first attempt at this fix was wrong and has been reverted:**
replacing `PhasingKeepingController`'s call into `rv2elem()` with a
custom, hand-written along-track-angle computation. That is exactly the
kind of change this project does not make -- orbit mechanics goes through
Basilisk, not a parallel implementation of it, however numerically
well-reasoned. The actually-correct fix is at the TEMPLATE level: this
scenario asked for an EXACTLY circular orbit, which is itself an edge
case Basilisk's own `rv2elem()` only handles safely below an extremely
tight, real-perturbation-sensitive eccentricity threshold. Both orbits
now use `eccentricity=0.001` (about 7 km of altitude variation, well
inside `station_keeping`'s 2 km deadband once smoothed over one orbital
period -- see `StationKeepingController.UpdateState()`'s own boxcar
average, which exists for exactly this kind of periodic, non-decay
variation) instead of `0.0` -- large enough to keep `rv2elem()` reliably
on its normal, stable branch for the whole run (comfortably above any
perturbation-induced noise), small enough not to meaningfully change the
scenario's own "near-identical orbits" story. `scripts/_generate_templates.py`
is the source of truth (see that script's own comment on
`build_05_formation_flying_phasing()`'s chief-1 orbit for the full
reasoning); `05_formation_flying_phasing.json` was regenerated from it,
not hand-edited.

**This does not, by itself, prove the crash is fully resolved** -- there
may be a second contributing factor this investigation hasn't isolated.
But it is a definite, real, well-evidenced bug in how this ONE template
was configured (an exactly-circular orbit is a genuine Basilisk edge
case, not something Basilisk itself is wrong about), fixed the way this
project fixes that class of problem: by giving Basilisk's own,
unmodified math a configuration it handles well, not by working around
it.

**Verification:** `tests/test_scenario_templates.py`/
`tests/gui/test_scenario_templates_gui.py`'s existing template
round-trip tests cover `05_formation_flying_phasing.json` structurally
(schema-valid, round-trips through the GUI editor) and pass unchanged --
this is a numeric-value-only change, not a structural one. 600 passed,
66 skipped in this sandbox (matching the count before this fix -- no new
tests needed; the actual regression check is a real Basilisk run of
template '05' no longer crashing, or crashing with a materially
different error/last-known-state, which only the user's own build can
confirm).

## Audit: every other place a degenerate/zero state could reach Basilisk

Direct follow-up request after the template '05' investigation: check the
whole codebase for other places a similar "zero" (or other degenerate)
input could break something, now that one real instance was found. Two
more were found, both in `engine/orbit_maintenance.py`, both existing
gaps in an ALREADY-established defensive pattern (`StationKeepingController.
UpdateState()`'s own guard checks BOTH non-finite AND exactly-zero
velocity before dividing by it) rather than new problems introduced by
anything in this investigation:

1. **`PhasingKeepingController.UpdateState()`** only checked for
   NaN/inf, not for `vA`/`vB` being exactly zero -- `vHatB = vB /
   np.linalg.norm(vB)` a few lines later would divide by zero, and
   `orbitalMotion.rv2elem()` (called just before that, to compute the
   phasing error) also divides by velocity-derived quantities
   internally. Its own existing guard comment on `StationKeepingController`
   even said "Same reasoning as PhasingKeepingController.UpdateState()'s
   own matching guard" -- which was no longer true once written, since
   that guard never actually got the zero-velocity check. Fixed by
   adding it, matching `StationKeepingController`'s exact pattern.

2. **`ConstantFrameThrustController.UpdateState()`** (the `constant_thrust`
   config -- not currently used by any bundled template, but a fully
   supported, documented feature a user can configure) had **no guard at
   all**: neither a finite check nor a zero-velocity one. Its
   `_vnb_basis()`/`_rtn_basis()` helpers (VNB/RTN frame construction)
   divide by `norm(vVec)` (both frames), `norm(rVec)` (RTN), and
   `norm(cross(rVec, vVec))` (both -- the orbit-normal magnitude, zero
   whenever r and v happen to be parallel, e.g. a purely radial
   trajectory, which neither an individual finite check nor a
   zero-velocity check alone would catch). Fixed with a guard covering
   all three degenerate cases, same "command no thrust, hold state"
   pattern as the other two controllers.

Also checked and found NOT to need a fix, with the reasoning for each:

* **`engine.service._osculating_elements()`** (the OTHER
  `orbitalMotion.rv2elem()` call site in this codebase) hits the exact
  same near-circular/near-equatorial classical-elements singularity, but
  its output only feeds plots/CSV export, never a commanded force -- a
  "wrong-looking reported angle" is not a "the simulation crashes"
  problem, and this was already correctly documented as an inherent,
  accepted limitation of osculating classical elements (not something a
  per-sample computation could avoid) rather than a bug, well before this
  audit.
* **`mission_engine.py`'s periapsis/apoapsis event detector**
  (`radial_velocity = dot(r, v) / np.linalg.norm(r)`) divides by
  `norm(r)`, which is only zero if a spacecraft's position has already
  reached the central body's exact center -- a state that requires the
  orbit to have already gone catastrophically non-physical by some OTHER
  cause first, not an independent trigger the way an ordinary near-circular
  or radial-trajectory configuration is.
* **`link_budget.py`'s free-space-path-loss** divides by nothing risky (a
  physical constant, the speed of light); `np.log10(range_m)` would only
  misbehave at `range_m == 0` (spacecraft exactly co-located with a
  ground station -- not a real orbital state), and even then only
  produces a nonsensical reported number, not a crash, for the same
  "reporting-only, not fed back into dynamics" reason as
  `_osculating_elements()`.
* **`engine.constellation`'s Walker-pattern math**
  (`raan_spread/num_planes`, `360/sats_per_plane`, etc.) divides by
  request parameters that `ConstellationRequest.validate()` already
  requires to be positive (see `test_request_validation_rejects_bad_input`)
  before any of this math runs -- pure Python arithmetic, not
  Basilisk-facing, and already schema-guarded.
* **`engine/fsw.py`** (attitude guidance/control wiring) has no custom
  vector-normalization math at all -- it only configures Basilisk's own
  `hillPoint`/`velocityPoint`/`mrpFeedback`/etc. modules directly,
  consistent with this project's convention of never reimplementing
  Basilisk's own math.

Also documented (not a code fix): `PhasingKeepingConfig`'s own docstring
(`schema/scenario.py`) now states the "use a small nonzero eccentricity,
not exactly 0.0" caveat directly, so a user authoring their own
phasing-keeping scenario (not just the bundled template) has a chance to
avoid this landmine before hitting it for real.

**Verification:** 5 new tests in `tests/test_orbit_maintenance.py`
(`requires_basilisk`, auto-skipped in this sandbox) --
`test_phasing_keeping_skips_thrust_on_zero_velocity` (the new
`PhasingKeepingController` guard), and four for
`ConstantFrameThrustController`:
`test_constant_thrust_skips_on_nan_state`,
`test_constant_thrust_skips_on_zero_velocity`,
`test_constant_thrust_skips_on_parallel_r_and_v` (the case neither a
finite check nor a zero-velocity check alone would catch), and
`test_constant_thrust_runs_normally_with_finite_state` (confirms the new
guard doesn't change behavior for the ordinary case). 600 passed, 71
skipped in this sandbox (5 more skipped, matching the 5 new tests). Not
yet confirmed against a real Basilisk build.

## Template '05' crash persists after the eccentricity fix -- isolating the cause

The eccentricity fix's OWN target bug is confirmed fixed: the user's next
crash log shows `phasing_keeping` reporting `error=-0.9125 deg` -- almost
exactly the true physical separation (hand-computed: -0.9135 deg), not
the wildly wrong `-0.0882 deg` from before. But **the crash still
happens, at the exact same point** (t=30 s to t=60 s, the first real
dynamics tick). That rules out the phasing-error noise as the (sole)
trigger -- it was a real, separate, worth-fixing bug, but not the reason
this scenario crashes.

One side effect of the fix, visible in this same log, that hadn't been
exercised before: `station_keeping` is now ACTIVELY BURNING
(`burn_on=True`) at t=30 s, where it previously was not. Both spacecraft
start at `true_anomaly_deg=0` -- with the new `eccentricity=0.001`,
that's PERIAPSIS, the lowest point of the orbit, about 7 km below the
mean/target altitude. `StationKeepingController`'s altitude smoothing
only has ONE sample on the very first tick, so it immediately sees
"6.9 km below deadband" and fires -- a real, if minor, side effect of the
eccentricity fix worth knowing about even independent of the crash
investigation.

That the crash persists with an entirely DIFFERENT controller now doing
the (small, bounded, ordinary) commanded burning is itself informative:
it suggests the trigger may have nothing to do with WHICH
`engine.orbit_maintenance` controller fires, or possibly nothing to do
with `engine.orbit_maintenance` at all. To find out directly rather than
keep guessing from either side, this repository now also includes
`missionstudio/scenarios/diagnostic_05_no_orbit_maintenance.json` -- NOT
a bundled template (it does not appear in the GUI's Load Scenario tab;
open it via Open/Browse, or `missionstudio run
missionstudio/scenarios/diagnostic_05_no_orbit_maintenance.json` from
the CLI). It is otherwise IDENTICAL to `05_formation_flying_phasing.json`
(same two near-circular, 45-degree-inclination, sun-perturbed orbits,
same 7-day/30-second-tick/rkf78 settings) with `station_keeping` and
`phasing_keeping` removed entirely from `follower-1` -- plain two-body
-plus-sun-third-body dynamics for both spacecraft, no custom force
effector active on either one at all.

**If this diagnostic scenario ALSO crashes** around the same t=30-60 s
window, that proves the crash has nothing to do with
`engine.orbit_maintenance` -- something in the core gravity/integrator
setup for two co-located, sun-perturbed, `orbit_only`-mode spacecraft is
the actual trigger, and the investigation moves to `engine.service.build()`
and Basilisk's own dynamics/gravity wiring instead. **If it does NOT
crash**, that rules core dynamics out and points the investigation back
at the force-effector wiring itself -- e.g. `StationKeepingController`'s
own burn, or two controllers sharing one `ExtForceTorque` object.

**Result, confirmed by the user: this diagnostic ran the FULL 7 days with
no crash at all** (`run_live: 100.0% complete`, no error). Conclusive:
the crash is NOT in core gravity/integrator/two-spacecraft setup -- it
requires a force effector actually being active on follower-1. Rules out
an entire class of hypothesis (sun ephemeris timing, task priority
ordering, generic two-spacecraft interaction) and narrows the
investigation specifically to `engine.orbit_maintenance`'s force
-effector wiring or control logic.

## Second diagnostic: isolating which part of orbit_maintenance is responsible

Both real crashes so far had SOME `orbit_maintenance` controller
actively commanding nonzero thrust through follower-1's `ExtForceTorque`
effector at the failing tick (phasing's `BURN_OUT` state in the first
crash, station-keeping's altitude burn in the second) -- but those two
controllers share more than just "a force": the same propellant/mass
-bookkeeping pattern (`engine.propellant_bookkeeping.
apply_propellant_burn`, which writes `scObject.hub.mHub` every tick,
including on non-thrusting ticks), the same `ExtForceTorque` effector
object (phasing shares station-keeping's), and each has its OWN extra
logic on top (station-keeping's altitude-deadband/smoothing/eclipse
gating; phasing's drift-orbit state machine and thruster arbitration).

New `missionstudio/scenarios/diagnostic_05b_constant_thrust_only.json`
(same non-template placement as the first diagnostic) isolates which
part: identical orbits/duration/rate/integrator/gravity, but follower-1
has ONLY `constant_thrust` configured (a small constant 0.05 N prograde
burn -- same magnitude used elsewhere in this template) instead of
`station_keeping`/`phasing_keeping`. `ConstantFrameThrustController` is
about as simple as a force effector in this codebase gets: no state
machine, no altitude smoothing, no thruster arbitration, no eclipse
gating -- just a fixed-direction force and the same shared
mass-bookkeeping write every tick.

**If this ALSO crashes**, the trigger is in the shared force-effector/
mass-bookkeeping mechanism common to all three controllers (most likely
suspect: the every-tick `scObject.hub.mHub` write, possibly interacting
with the RK78 adaptive integrator's own internal substepping in a way
that's fine for `missionAnalysis`'s original, coarser-task-rate version
of this pattern but not for running it on the SAME task as the dynamics
integration itself, which is what `engine.orbit_maintenance`'s own
module docstring already flags as the one deliberate difference from the
ported original). **If it does NOT crash**, the trigger is specifically
in `StationKeepingController`'s or `PhasingKeepingController`'s own extra
logic, not the shared mechanism -- narrowing to the altitude-smoothing/
thruster-arbitration/eclipse-gating code neither shares with
`ConstantFrameThrustController`.

**Result, confirmed by the user: this diagnostic ALSO ran the full 7 days
with no crash.** Rules out the shared mass-bookkeeping mechanism -- the
trigger is specifically in `StationKeepingController`'s and/or
`PhasingKeepingController`'s own extra logic (eclipse-gating,
altitude/error-smoothing history, or the two-controllers-sharing-one
-thruster arbitration), none of which `ConstantFrameThrustController`
has.

## Third diagnostic: station-keeping alone, no sharing with a second controller

One structural difference between the two clean diagnostics and the real
crash stands out: template '05' has TWO controllers
(`StationKeepingController` + `PhasingKeepingController`) sharing ONE
`ExtForceTorque` effector and one propellant tank, with explicit
thruster-arbitration logic (`thrusterHeldByAltCtrl`) deciding which one's
`extForce_N` write wins each tick -- neither of the two clean diagnostics
tested that sharing at all (constant_thrust is the only controller on its
spacecraft). Comparing `build_station_keeping()`/`build_constant_thrust()`
directly shows their `ExtForceTorque` wiring is otherwise structurally
identical (same `addDynamicEffector`/`AddModelToTask` pattern, no
priority difference) -- ruling out a wiring bug as the remaining
explanation.

New `missionstudio/scenarios/diagnostic_05c_station_keeping_only.json`
isolates the sharing question directly: identical to the real template
except `phasing_keeping` is removed from follower-1 entirely --
`station_keeping` alone, with its own eclipse-gating and
altitude-smoothing history intact, but no second controller and no
thruster arbitration.

**If this crashes**, the trigger is in `station_keeping`'s own logic
(eclipse-gating and/or altitude-smoothing), independent of any sharing.
**If it does NOT crash**, that implicates the two-controllers-sharing-one
-effector/arbitration mechanism specifically -- something about
`phasing_keeping` being present and sharing `station_keeping`'s effector,
not either controller's logic in isolation.

**Result, confirmed by the user: `station_keeping` alone crashes, at the
identical point, with identical state.** Conclusive: NOT the
two-controllers-sharing-one-effector mechanism (there's only one
controller here) -- the trigger is specifically in
`StationKeepingController`'s own logic.

## Fourth diagnostic: eclipse machinery present vs. actually read

Comparing the one clean diagnostic (`constant_thrust` alone) against the
one crashing diagnostic (`station_keeping` alone) with everything else
held equal (same thrust magnitude 0.05 N, same VNB-prograde direction,
same mass-bookkeeping write, same fuel-tank message, both start applying
nonzero force on their very first tick): the one remaining code
difference is eclipse-gating.
`StationKeepingController.UpdateState()` reads
`self.eclipseInMsg.isLinked()` / `.shadowFactor` every tick;
`ConstantFrameThrustController` has no eclipse message reader at all --
and because `constant_thrust` alone doesn't trigger
`engine.service.build()`'s `needs_eclipse` condition
(`power`/`station_keeping`/`enable_srp`), that earlier clean diagnostic
never even built the shared `Eclipse()` model in the first place.

New `missionstudio/scenarios/diagnostic_05d_constant_thrust_with_eclipse_model.json`
isolates whether it's the mere PRESENCE of that machinery, or the ACT of
reading it, that matters: `constant_thrust` alone again (no eclipse
message reader, same as the clean diagnostic), but with `enable_srp=True`
added -- this forces `needs_eclipse` true and builds the real shared
`Eclipse()` model/SRP effector, exactly as `station_keeping` does,
WITHOUT `constant_thrust` itself ever reading `eclipseInMsg`.

**If this crashes**, the `Eclipse()`/SRP machinery itself is implicated,
independent of which controller reads it -- something about that model's
construction or its interaction with the integrator. **If it does NOT
crash**, that points specifically at `station_keeping`'s/
`phasing_keeping`'s own act of reading `eclipseInMsg.isLinked()`/
`.shadowFactor` from within their `UpdateState()` callback as the actual
trigger -- an unusual but very specific, actionable finding to chase down
next (e.g. in how `EclipseMsgReader()` behaves when read from a Python
`SysModel` callback versus a C++ one).

**Result, confirmed by the user: this diagnostic ran the full 7 days with
no crash.** Fully exonerates the `Eclipse()`/SRP machinery itself --
narrows the trigger to the ACT of reading `eclipseInMsg` from a custom
Python `UpdateState()` callback, specifically via
`StationKeepingController`'s/`PhasingKeepingController`'s own
`.shadowFactor` read.

## A deprecated-field theory that turned out not to hold on a real build

Reading Basilisk's own C++/SWIG source (not this project's code) turned
up the actual field. `EclipseMsgPayload.shadowFactor`
(`src/architecture/msgPayloadDefC/EclipseMsgPayload.h`) is DEPRECATED in
favor of `illuminationFactor` (same value, same semantics -- confirmed by
Basilisk's own unit test,
`src/simulation/environment/eclipse/_UnitTest/test_eclipse.py`'s
`test_shadow_vs_illumination_alias_and_deprecation_behavior`, with a
removal deadline of 2026-12-31).

**Correction, since an earlier revision of this section named a specific
internal mechanism that turned out to be wrong -- caught by going back
and verifying it directly against Basilisk's generator source rather
than leaving the claim standing on inference:** the generic
`swig_deprecated.i`/`_inject_deprecated_property` machinery (which DOES
re-inject a class-level `property()` on every read, and was this
project's first guess) is NOT what backs `shadowFactor`/
`illuminationFactor`. That field has its own hand-written, one-off
aliasing block, specific to `EclipseMsg` alone among every message type
(`src/architecture/messaging/msgAutoSource/msgInterfacePy.i.in`, the
`if "{type}" == "EclipseMsg":` block): it assigns
`EclipseMsgPayload.illuminationFactor`/`.shadowFactor` as plain
`property()` objects on the class exactly ONCE, at Python import time --
not re-injected per read, per tick, or per instance. So the specific
"repeated class mutation from a hot loop" story in an earlier revision of
this section does not hold up, and no other confirmed mechanism has
replaced it: what Basilisk's own C++/SWIG layer does internally that
makes reading this one deprecated property unsafe from a Python
`SysModel` callback is NOT established here, only that it empirically is
-- proven by elimination, not inferred from a plausible-sounding
mechanism. Four separate diagnostic scenarios agree: `constant_thrust`
(no eclipse reader at all) ran clean; the SRP effector with the SAME
shared `Eclipse()` model present, read only in C++, ran clean;
`station_keeping` alone -- the one thing that reads `.shadowFactor` from
Python every tick -- reliably crashed at the identical point every time.
That is the actual evidence for this fix; the mechanism inside Basilisk
remains an open question, not something this project's investigation
resolved.

**This theory did not survive contact with a real build.** Switching to
`.illuminationFactor` was pushed and the user tried it -- and it failed
immediately with `AttributeError: 'EclipseMsgPayload' object has no
attribute 'illuminationFactor'`. That field does not exist at all on
their installed Basilisk build, which means: their build predates
`illuminationFactor` being added, `shadowFactor` was never deprecated in
their actual runtime (there is no aliasing/deprecation machinery on a
build that doesn't have the new name to alias to), and this project's
`illuminationFactor`/`shadowFactor` deprecation story -- while accurate
for the LATEST Basilisk source tree available for reading in this
environment -- was never the right frame for what is actually installed
on the user's machine. This project does not pin an exact Basilisk
version (see `pyproject.toml`'s own comment on why), so a fix that only
works against one specific source-tree snapshot was never going to be
correct in the first place.

**What this means for the original crash: the root cause is still
open.** The diagnostic sequence that isolated eclipse-reading as the
empirical trigger (`constant_thrust` clean, SRP-with-eclipse-model clean,
`station_keeping` alone reliably crashing) is still valid evidence -- it
ran on the user's real, unchanged Basilisk build throughout, reading
`.shadowFactor` the entire time (the only field that build has). But the
explanation for WHY reading it crashes cannot be "it's deprecated and
unstable," because on this build it isn't deprecated at all -- it's
simply the current, only, ordinary field. Whatever actually makes
reading the eclipse message from a Python `SysModel` callback unsafe on
this specific installed build remains unidentified.

**Fixed for real, scoped correctly this time:** new
`_eclipse_illumination_fraction()` in `engine/orbit_maintenance.py` tries
`.illuminationFactor` first (Basilisk's current documented name, per this
checkout's own source) and falls back to `.shadowFactor` only on
`AttributeError` (i.e. only on a Basilisk build old enough not to have
the new name at all) -- both `StationKeepingController.UpdateState()`
and `PhasingKeepingController.UpdateState()` now go through it. This does
NOT claim to fix the underlying crash (it can't, without knowing the real
mechanism) -- it only makes this one read tolerant of both Basilisk API
generations instead of hard-crashing with an `AttributeError` on an
older build, which is what the previous, now-reverted `.illuminationFactor`
-only version did. Expect the ORIGINAL crash (the one `diagnostic_05c_
station_keeping_only.json` reliably reproduced, reading `.shadowFactor`
either way) to still occur on the next run -- this fixes the regression
this project itself introduced, not the crash the investigation started
with.

**Verification:** two new tests,
`test_eclipse_illumination_fraction_prefers_new_name` and
`test_eclipse_illumination_fraction_falls_back_to_old_name` (the second
one directly modeling the real user's build: a stub payload object with
`shadowFactor` but no `illuminationFactor` attribute at all), in
`tests/test_orbit_maintenance.py` (`requires_basilisk`, auto-skipped in
this sandbox since even constructing the stub payload's consumer needs
the module's Basilisk imports to succeed). 600 passed, 73 skipped in
this sandbox (2 more skipped, matching the 2 new tests).

## The actual root cause, found for real: not eclipse at all

Everything in the sections above -- the deprecated-field theory, the
`illuminationFactor`/`shadowFactor` fallback, "the root cause is still
open" -- was a dead end. Eclipse was never involved in the original
crash. Here is what actually happened, found by continuing the
diagnostic sequence with real repros rather than assuming the eclipse
angle was the only thread left to pull.

**Two more real diagnostics fully exonerated eclipse.** A debug log of
the raw value `StationKeepingController`/`PhasingKeepingController`
read from `EclipseMsgPayload` every tick showed it was always a
completely sane `1.0` (fully sunlit) right up to the crash -- ruling
out a bad/NaN value. A follow-up diagnostic switch that skipped the
eclipse message's `subscribeTo()` call entirely (not just the read --
`isLinked()` stayed `False` the whole run, confirmed by zero
eclipse-related log lines) still crashed identically. Eclipse, the
value it carries, and the act of reading or even subscribing to it,
are conclusively not the trigger.

**A controlled A/B comparison then ruled out `station_keeping`'s own
control logic too.** `diagnostic_05b_constant_thrust_only.json` (clean)
and `diagnostic_05c_station_keeping_only.json` (crashes) use
byte-for-byte identical orbits, and -- because station-keeping's
altitude deadband trips on tick 1 in this configuration -- identical
thrust magnitude, direction, and timing throughout. Both write a
`FuelTankMsgPayload` every tick. Swapping the adaptive `rkf78`
integrator for the fixed-step, non-adaptive `rk2` (which structurally
cannot exhibit "the adaptive step-size search spins forever on a NaN
error estimate," the mechanism this project's own error message
blames) made no difference either -- same crash, same signature. Every
hypothesis this project could test from the Python side was tried and
eliminated.

**The actual break: the headless CLI (`missionstudio.cli run`) ran the
exact same crashing scenario to completion, clean, first try.** Every
single crash report collected across this entire investigation came
from the GUI's `run_live()` path, and every one of them logged
`Basilisk-Vizard connection made` -- something this project had not
isolated as a variable until debugging under `gdb` forced a
Vizard-free headless run. That pointed at Vizard, not station-keeping,
not eclipse, not the integrator.

**Confirmed with a real `gdb catch throw`/`bt`** on a fully isolated
repro: headless CLI, `--vizard-save-file` (no live Vizard connection
needed, just exercises the same `enable_vizard()` build path), station-
keeping only. Full native backtrace:

```
VizInterface::WriteProtobuffer(unsigned long)
  -> google::protobuf::internal::ArenaStringPtr::Set(std::string const&, Arena*)
    -> std::string::_M_create()
      -> throws std::length_error
```

thrown on `vizInterface`'s own background write thread -- not the main
simulation thread, and not anywhere near `orbit_maintenance.py`.

**Root cause:** `engine/vizard.py`'s `enable_vizard()` builds a
`vizInterface.GenericStorage` "Propellant" panel for every spacecraft
with `station_keeping` configured (never for `constant_thrust`, which
is exactly the split every diagnostic above kept finding). Reading
Basilisk's own `vizStructures.h`: `VizSpacecraftData::genericStorageList`/
`genericSensorList` are `std::vector<GenericStorage *>`/
`std::vector<GenericSensor *>` -- raw POINTER vectors.
`vizSupport.enableUnityVisualization()` only stores the pointers it's
handed; it never clones the pointed-to structs. The `panel`/`sensor`
objects `enable_vizard()` built (and their embedded
`FuelTankMsgReader`/`PowerStorageStatusMsgReader`/`DeviceCmdMsgReader`
readers) were local variables, never returned, never retained anywhere
-- garbage-collected the instant `enable_vizard()` returned, while
`VizInterface` kept dangling pointers to them and dereferenced one
every tick from its background thread, eventually reading freed/reused
memory as a corrupt string length.

This is the exact same bug class this same module already found and
fixed once before, for `_AccessIndicatorBridge` (see that section's
own history above the "Live-data panels" docstring in
`engine/vizard.py`) -- right down to the identical
`basic_string::_M_create`/`std::length_error` signature. That earlier
fix's own justification for not extending the same retention to
`GenericStorage`/`GenericSensor` ("their relevant state is copied into
Basilisk's own C++ containers") was an unverified assumption, never
checked against `vizStructures.h`, and it was wrong for these two
specific pointer-vector fields.

**Fixed the same way as the bridge fix:** `enable_vizard()` now also
returns `generic_storage_list`/`generic_sensor_list` alongside
`viz`/`access_indicator_bridges`, and `engine.service.SimulationService`
retains all four (`_viz`/`_viz_access_indicator_bridges`/
`_viz_generic_storage_list`/`_viz_generic_sensor_list`) for the
instance's lifetime instead of just the first two.

**Verification:** `tests/test_vizard.py` (new,
`requires_basilisk`) -- `test_station_keeping_with_vizard_save_file_does_not_crash`
runs `diagnostic_05f_station_keeping_fixed_step_integrator.json` with a
real `VizardRequest(save_file=...)` through `SimulationService.run()`
end to end (this is the actual regression check: it used to raise
`SimulationServiceError` wrapping `std::length_error`/`std::bad_alloc`
within the first couple of ticks, every time); `test_generic_storage_
and_sensor_lists_are_retained_after_build` checks the fix directly --
`service._viz_generic_storage_list` is non-`None` and carries a real
entry after `build()`. Both auto-skip in this sandbox (no Basilisk
build here) but were designed directly from, and match, the real
crash this project's user reproduced and debugged with `gdb` on their
own machine. 600 passed, 75 skipped in this sandbox (2 more than the
count above, matching these 2 new tests). The temporary
`MISSIONSTUDIO_DIAG_SKIP_ECLIPSE_READ`/`_SUBSCRIBE` diagnostic switches
used to isolate eclipse as a non-cause have been removed from
`engine/orbit_maintenance.py` now that the real root cause is fixed.

## RTN separation panels: "Unavailable" readout, and whose offset is it

Two more real bugs/gaps found from a live Vizard screenshot, on the
Radial/Transverse/Normal separation panels a previous round (see
`engine/vizard.py`'s own docstring, "A THIRD round of feedback") had
just replaced the single vague "Separation" scalar with.

**Bug 1: Radial and Normal showed "Unavailable"; Transverse rendered
fine.** All three panels are built identically (same
`vizInterface.GenericStorage` construction, same
`DataStorageStatusMsgReader` wiring) -- the only difference at that
moment was sign: Transverse happened to be positive, Radial and Normal
happened to be negative. `PhasingKeepingController.UpdateState` clamped
`storageLevel` SYMMETRICALLY (`[-storageCapacity, storageCapacity]`),
specifically to preserve "ahead of"/"behind the chief" direction in
Vizard's own native numeric readout. Checked directly against
Basilisk's own field comments -- both `vizStructures.h`'s
(`GenericStorage::currentValue`/`maxValue`, `"current/maximum absolute
value of the storage device"`) and the wire-format
`vizMessage.proto`'s (identical wording) -- `GenericStorage` is
documented as a non-negative gauge, the same kind of quantity as the
battery/propellant/delta-V panels right next to it. A negative
`storageLevel` is out of that contract; Vizard's own client evidently
rejects it outright rather than rendering a broken bar the way an
OVER-capacity value did in an earlier round.

**Later CONFIRMED directly, not just inferred from field comments:**
the `0h3xn4/vizard` Unity project (cloned into this session separately
-- Vizard's client had been assumed closed-source/unavailable to this
project up to that point, which turned out not to be the case) was
checked against this exact question.
`GenericStorageUnitMethods.cs`'s `UpdateCurrentValue()` reads:

```csharp
float value = (float) myMsg.CurrentValue;
...
if (value >= 0) { /* normal bar + "<value> / <maxValue> <units>" */ }
else
{
    hoverText.text = "Unavailable";
    verboseText.text = "Unavailable";   // "Stale" in VR
    verboseText.color = Color.gray;
    measurementRect.GetComponent<Image>().color = Color.gray;
    measurementRect.sizeDelta = new Vector2(0, barHeight);
}
```

A hard `value >= 0` branch, unconditional -- no tolerance for a small
negative number, nothing to do with `maxValue` or color thresholds.
Exactly the mechanism this section's own reasoning (field-comment
wording plus the screenshot's positive/negative split) had inferred,
now confirmed from the actual rendering code rather than circumstantial
evidence.

Fixed in `orbit_maintenance.py`: `_clamp_symmetric` replaced with
`_clamp_magnitude` (`min(abs(value), limit)`) -- `storageLevel` now
publishes MAGNITUDE, not signed direction. A real, honest trade-off,
not a full fix: Vizard's live panels can no longer show "ahead of"/
"behind the chief"; the signed numbers remain available as
`lastRadialKm`/`lastTransverseKm`/`lastNormalKm` on the controller
itself, just not live in Vizard.

**Bug 2 (same round): the panels never said whose offset they were
measuring.** "Radial (R)" on a follower's own storage panel doesn't say
which chief it's relative to. Fixed by threading the chief spacecraft's
own `ModelTag` through as `PhasingKeepingController.chiefName` (wired
by `build_phasing_keeping` from `chief_sc_object.ModelTag`), and a new
`engine.vizard._rtn_panel_label(axis_letter, chief_name, follower_name)`
helper that folds it into the label itself (e.g. `"R vs chief-1"`) --
originally falling back to a generic `"R vs chief"` past a flat,
14-character budget (the longest confirmed NOT to truncate against one
real screenshot).

**Later refined once the Unity source was available (see above):**
that flat 14-character budget turned out to be specific to the
screenshot's own scenario, not a universal constant.
`GenericStoragePanelMethods.cs`'s `InitializePanel()` sets
`panelName = spacecraftName + " Storage"` and only widens the row's bar
(and hence its label's usable width) past a hardcoded 90px default when
`panelName.Length > 16` -- to `panelName.Length * 7` pixels, applied
via `SetBarWidth()` UNIFORMLY to every row in that spacecraft's own
panel. The confirming screenshot's spacecraft ("follower-1", 10
characters) crossed that threshold (123px usable); a SHORTER name (8
characters or fewer, e.g. "sat-1") never does, leaving only 87px --
narrower than what "14 characters" was actually confirmed against. The
prefab (`GenericStoragePanelUnit.prefab`) also confirms the render mode
this matters for: `m_enableAutoSizing: 0`, `m_TextWrappingMode: 1`
(NoWrap), `m_overflowMode: 3` (`TextOverflowModes.Truncate`) -- a hard
per-pixel cutoff.

Fixed: `_usable_label_width_px(follower_name)` computes the real,
per-scenario usable width from Vizard's own formula; no glyph-metrics
table is available for the font in this repo (a built-in TMP font, not
a checked-in asset), so pixel width is converted to a character budget
via a conservative estimate (`_PIXELS_PER_LABEL_CHARACTER_ESTIMATE`,
calibrated against the one confirmed real data point and padded up so
it underestimates rather than overestimates). `_rtn_panel_label` now
has THREE fallback tiers, not two: `"{axis} vs {chief}"` ->
`"{axis} vs chief"` -> the bare axis letter alone (always 1 character,
always fits) -- since on a narrow enough panel even the generic
fallback can exceed the budget.

**Verification:** `tests/test_orbit_maintenance.py`'s two RTN tests
rewritten for magnitude semantics (real Basilisk, both pass -- 27
tests total in that file with the new `chiefName` wiring smoke-tested
separately, not added as a permanent test); `tests/test_vizard_labels.py`
rewritten (8 tests, no Basilisk needed -- these functions have no
Basilisk import, unlike the rest of `engine.vizard`) to cover the
width-aware budget directly, including the narrow-panel/deeper-fallback
case. `chiefName` wiring confirmed end-to-end against real Basilisk
with a standalone script (`build_phasing_keeping()` called directly,
`controller.chiefName == "chief-1"` after); label output for this
project's own `05_formation_flying_phasing` template's actual
spacecraft names confirmed the same way. Both the magnitude fix (bug 1)
and the truncation-width formula (bug 2) are now confirmed directly
against Vizard's own Unity source rather than inferred from a
screenshot or field comments -- only the characters-per-pixel
conversion remains an estimate (no font glyph metrics available).

## Perturbation-model audit: gravity/third-body on every template, atmosphere-model choice, a historical-percentile drag margin

Real user request, in three parts: "why can't I select the atmospheric
drag model, other tools let me choose Jacchia-Roberts or NRLMSISE-00";
"I am missing solar radiation pressure [in Propagation Setup]"; and "I
need all example scenarios to have all perturbations activated ...
spherical harmonics of 10th order, sun and moon third-body
perturbations, 95th percentile/+2sigma atmospheric drag".

**Atmosphere-model choice.** Checked Basilisk's own
`src/simulation/environment/` tree directly (not assumed): it ships
exactly `ExponentialAtmosphere`, `MsisAtmosphere` (NRLMSISE-00), and
`TabularAtmosphere` -- no Jacchia-Roberts model at all, so that specific
option genuinely cannot be offered. New
`SpaceWeatherConfig.atmosphere_model` (`"nrlmsise00"` | `"exponential"`)
lets `engine.service` build either; `"exponential"` is configured via
Basilisk's own `simSetPlanetEnvironment.exponentialAtmosphere()` helper
(the same sea-level Earth constants a real shipped Basilisk example,
`examples/scenarioDragDeorbit.py`, uses for its own exponential-model
deorbit case). Confirmed directly against real Basilisk (a standalone
density-recorder run, not guessed) that this simple model under
-predicts LEO density by many orders of magnitude versus NRLMSISE-00 --
documented plainly as an inherent limitation of the model, not a wiring
bug: pick it for speed/simplicity, never for an accurate drag estimate.
`TabularAtmosphere` (a user-supplied density table) was deliberately
left out -- it would need a new file-upload schema/GUI concept of its
own.

**Conservative ("worst-case") drag margin.** No such concept exists in
Basilisk itself, and this project has no authoritative source for a
specific fixed "worst-case" F10.7/Ap constant to hand-code -- asked the
user how to define it rather than guessing a physical constant; answer:
derive it statistically from REAL historical data. New
`engine.spaceweather.compute_worst_case_activity()`/`generate_worst_case()`
compute the requested percentile (default 95th) of `F10.7_OBS`/`AP_AVG`
across a real historical CelesTrak extract (refuses fewer than 365 days
of real history, and refuses `source="synthetic"` outright -- a
percentile of a fabricated profile is not a real historical "worst
case") and write a CSV holding that value CONSTANT across the whole
scenario (a sustained-worst-case assumption, not a single spike).
`SpaceWeatherConfig.activity_level`/`activity_percentile` expose it;
`PropagationSetupDialog` gained matching combo/spinner controls, grey
-ing out correctly when `atmosphere_model="exponential"` is selected
(no F10.7/Ap dependence at all in that case).

**Solar radiation pressure discoverability.** Already existed as a
per-spacecraft `enable_srp` toggle on `SpacecraftEditorDialog`'s "Orbit
/ mass" tab -- not a missing feature, a UX gap: looking for it
specifically in `PropagationSetupDialog` and not finding it read as
"not supported." Fixed with an explicit pointer `QLabel` in that
dialog's space-weather group (never a docstring the user never sees).

**Every example template audited individually, not blanket-edited** --
`01` (clean two-body Kepler baseline) and `09` (Monte Carlo dispersion
analysis whose own description explains its lesson specifically
requires the ABSENCE of drag/SRP) were deliberately left untouched;
`02`/`03` got gravity-only updates (drag would muddy `02`'s J2 -
precession visual, or is physically negligible at `03`'s GEO altitude);
`04`/`05`/`07`/`08` got the full set (10th-degree gravity, Sun+Moon
third-body, drag, SRP, the conservative margin) since none of their own
stated lessons depend on a clean/unperturbed baseline. `06` got gravity
-only, preserving its explicit role as "the simple version" (`07` being
"the realistic counterpart"). All built through
`scripts/_generate_templates.py` (the existing regeneration source of
truth, updated in place, not hand-edited JSON) -- see that script's own
`_conservative_drag_margin()` helper and each `build_*()` function's
comments for the per-template reasoning.

**Earth-albedo/IR radiation pressure -- investigated, deliberately NOT
added.** A second real user request. Basilisk's `earthRadiationModel`
computes albedo/IR flux, but its own payload doc names
`facetERPDynamicEffector` as the consumer that turns that flux into an
actual orbital force -- and that module doesn't exist anywhere in this
Basilisk build (checked the source tree and the installed package, not
assumed). Adding it for real would mean writing a brand-new,
never-before-exercised force-effector from scratch (the same
`extForceTorque` manual-force-injection pattern this project's own
thrust controllers already use, plus the standard flux/c * area * Cr
formula solar SRP already uses) -- asked the user rather than silently
writing untested physics code under a broader "add perturbations"
instruction; answer: skip it, document the finding (see README's
"Known limitations").

**Verification:** `tests/test_spaceweather.py` grew from 14 to 21 tests
(percentile computation matches `numpy.percentile` directly, short
-history rejection, synthetic-source refusal, the full `resolve()`
conservative-mode path) -- no Basilisk needed, this module has none.
`tests/test_scenario_schema.py` grew by 6 (new field validation/round
-trip). `tests/gui/test_propagation_setup_dialog.py` grew from 10 to 17
(new controls' enable/disable gating, round-trip, the SRP pointer
label's presence). `tests/test_scenario_templates.py` (41 tests)
re-passes unchanged against the regenerated templates. The exponential
-atmosphere wiring itself was confirmed against real Basilisk with a
standalone density-recorder script (bypassing `SimulationService.build()`,
which needs SPICE kernels this sandbox cannot fetch) -- plausible,
positive LEO density recorded end-to-end. 644 passed, 99 skipped in
this sandbox without a Basilisk build; the conservative-margin
templates (`04`/`05`/`07`/`08`) need real network access to CelesTrak
(or a local historical file) to actually RUN, not just validate --
disclosed plainly in each file's own `description` and in this
project's README, not a silent gap.

## "Seamlessly integrate Basilisk and Vizard" -- auto-fetching a pre-built binary

Real user request: merge the Basilisk and Vizard repositories/builds so
neither has to be set up separately. Investigated both repositories
directly (not assumed) before answering: Basilisk builds via CMake +
SWIG + Python; Vizard's OWN repository has no scripted/CLI build path
at all -- only an interactive Unity Editor GUI workflow (install Unity
Hub, install a specific licensed Unity Editor version, open the
project, click through a "Build Profiles" panel per platform; no CI
config, no build scripts exist in that repo). A single build step that
produces both isn't realistic without the user already having Unity
Editor installed and licensed, which this project cannot do on their
behalf. The two are also deliberately separate PROCESSES at runtime --
Vizard plays back a saved `.bin` file with zero Basilisk involvement by
design, not as an artifact of being separate repos.

Asked the user what would actually make this feel seamless; answer: skip
building Vizard from source entirely, auto-fetch AVS's own pre-built
binary instead. `docs/source/Vizard/VizardDownload.rst` (in this
Basilisk checkout) already publishes exactly that -- three fixed,
per-platform `.zip` links a human downloads and unzips manually.

**`gui/vizard_launcher.py`** gained `fetch_vizard()`: downloads the
correct-platform `.zip`, extracts it with an explicit zip-slip guard
(`_safe_extract` -- refuses any entry that would resolve outside the
extraction directory; the URL itself is a hardcoded trusted constant,
not user-supplied, so this is defense in depth, not a response to a
known issue), locates the executable inside (same shallow-search idiom
`find_vizard_executable` already used), and sets the executable bit on
non-Windows platforms (zip extraction doesn't reliably preserve it).
Chunked, cooperatively-cancellable reads (`should_cancel`, checked
between chunks) -- the same pattern `gui.run_worker.RunWorker` already
uses for a running simulation, never a forced thread kill. Raises
`VizardFetchError` on any failure (network, corrupt zip, no executable
found, cancelled) -- one error-reporting path, never a silent partial
install.

**`VizardFetchWorker`** (`QThread`) wraps it for the GUI.
**`MainWindow._locate_or_fetch_vizard`**/**`_fetch_vizard_with_progress`**
wire it into `on_launch_vizard()`'s existing "not found" branch: a
`QMessageBox` now offers "Download Vizard" alongside the original
"Browse...", and the download runs behind a modal, cancellable progress
dialog -- implemented as a NESTED `QEventLoop` (not connecting to the
worker's signals and returning immediately) specifically so
`on_launch_vizard()`'s existing synchronous `bool` return contract
(also relied on by `on_run()`'s live-stream gate) needed no changes.

**Real bug caught while testing this, not a network issue:** the first
version assumed `QEventLoop.quit()` called BEFORE `exec()` would make
the very next `exec()` call return immediately. Confirmed the hard way
(a test using a synchronous fake worker hung indefinitely) that this is
wrong -- Qt's own documented behavior is that `quit()` is a no-op if
the loop isn't running yet. Only matters for a worker that happens to
finish synchronously inside `start()` (never the real, genuinely
-threaded case, where `start()` returns almost instantly, well before
any background work could finish) -- fixed by checking whether the
outcome was already populated before calling `loop.exec()` at all.

**Verification:** `tests/gui/test_vizard_launcher.py` grew by 14 tests
(`fetch_vizard`'s download/extract/error paths, `_safe_extract`'s
zip-slip guard on both a malicious and a normal zip, `VizardFetchWorker`'s
signal wiring) -- network always mocked
(`urllib.request.urlopen` never touches the real
`hanspeterschaub.info`, confirmed blocked by this project's development
sandbox elsewhere, e.g. `engine.kernels`'s own SPICE-kernel fetch using
the same host as a backup URL). `tests/gui/test_main_window.py` grew by
7 (the new `QMessageBox` routing, the progress-dialog flow's success/
failure paths, using a fake `QObject`-based worker rather than a real
`QThread` -- mirrors this file's own existing `RunWorker`-patching
convention). 667 passed, 99 skipped in this sandbox. The real
network fetch itself is unverified end-to-end here (same sandbox
network-policy limitation as CelesTrak/SPICE elsewhere in this
project) -- written directly against `VizardDownload.rst`'s documented
links and Vizard's own documented `.zip` contents; verify on first
real-network use.

## First real-network run of fetch_vizard() -- a real bug, found and fixed

Asked a real user to run `fetch_vizard()` on their own machine, since
this project's own development sandbox can't reach
`hanspeterschaub.info` at all (confirmed via the sandbox's own proxy
status endpoint: an organization egress-policy denial, not a timeout --
every environment available to this session shares the same policy, so
there was no way to test this from here no matter which environment a
new session used).

**Real result:** `HTTPError: 403 Forbidden`, straight from the server,
on the very first `urlopen()` call. Root-caused (not guessed, though the
signature is a well-known one): `urllib.request.urlopen(url, ...)`
called with a bare URL string sends Python's own default `User-Agent`
header (`"Python-urllib/<version>"`), which is routinely blocked by
basic bot-protection on static-file hosts that have no issue with an
ordinary browser downloading the exact same public file by hand --
`VizardDownload.rst` already publishes this exact link for anyone to
click.

**Fixed** in both `gui.vizard_launcher.fetch_vizard()` (the one
actually reported broken) and, proactively, `engine.spaceweather.fetch()`
(the identical bare-`urlopen()` pattern against a different host,
`celestrak.org`, never itself exercised against the real network in
this sandbox either) -- both now send a realistic browser `User-Agent`
via an explicit `urllib.request.Request(url, headers={...})` instead of
a bare URL string. A standard, widely-used workaround for exactly this
kind of blocking, not an attempt to bypass any real access control.

**Verification:** a new regression test in each affected file
(`test_fetch_vizard_sends_a_browser_like_user_agent`,
`test_fetch_sends_a_browser_like_user_agent`) asserts the actual
outgoing `Request` carries a real `User-Agent` header -- neither
existing test suite would have caught this regressing, since their fake
`urlopen()` never inspected what it was called with, only that some
response came back. 669 passed, 99 skipped in this sandbox. The fix
itself has NOT yet been re-confirmed against the real network with a
second real-machine run -- the user's next run should get past the
download step to whatever (if anything) comes after; report back if it
doesn't.

## Second real-network run -- genuine end-to-end success, plus one cosmetic fix

Same user, same real machine, re-ran `fetch_vizard()` after the
User-Agent fix above. **Real result:** the download succeeded, the
`.zip` extracted, and the executable was found --
`Exists: True`, confirmed against the actual binary on disk, not
assumed. This is the first genuine confirmation that `fetch_vizard()`
works end-to-end against the real `hanspeterschaub.info` host, not just
against a mocked one.

The resulting path was one directory deeper than expected though:
`.../vizard/Vizard_Linux/Vizard_Linux/Vizard.x86_64`, a doubled
`Vizard_Linux` segment. Root cause (confirmed from the real `.zip`
the user actually downloaded, not guessed): `extract_dir` was named
after the zip's own filename with `.zip` stripped (`"Vizard_Linux"`),
but AVS's real `Vizard_Linux.zip` *also* wraps its own contents in a
top-level folder of that exact same name -- so extracting it into a
directory of the same name nests it one level deeper than intended.
`_search_one_root()`'s one-level subdirectory search still found the
executable correctly either way, so this was never a functional bug,
only a cosmetically redundant path.

**Fixed** by decoupling `extract_dir` from the zip's filename
entirely -- it is now a fixed `dest_dir / "extracted"` regardless of
what the `.zip` is called, so a real zip's own wrapper folder (of
whatever name) nests exactly once, not twice. Since `extract_dir` no
longer varies per fetch, a second fix rides along: `fetch_vizard()` now
`shutil.rmtree()`s any existing `extract_dir` before extracting, so a
later re-fetch (e.g. after Vizard publishes a new version) can't leave
an older version's files mixed in with the new one's.

**Verification:** two new regression tests in
`tests/gui/test_vizard_launcher.py` --
`test_fetch_vizard_finds_the_executable_inside_a_same_named_wrapper_folder`
builds a `.zip` whose single entry is `"Vizard_Linux/Vizard.x86_64"`
(mirroring the real zip's own layout) and asserts the resulting path is
exactly `extracted/Vizard_Linux/Vizard.x86_64`, one level of nesting,
not two; `test_fetch_vizard_clears_stale_files_from_an_earlier_extraction`
fetches an "old" zip containing an extra file, then a "new" zip without
it, and asserts the stale file does not survive into the second fetch's
result. 671 passed, 99 skipped in this sandbox. `fetch_vizard()` is now
confirmed working end-to-end on real hardware against the real
`hanspeterschaub.info` host, for both the download and the extraction
steps.

## Third real-network round -- the downloaded binary actually launches

Downloading and extracting is one thing; whether the resulting file is
actually executable was still an open question (fetching leaves the
executable bit fix-up, `subprocess.Popen`, and Vizard's own startup
all unexercised against a real download). Asked the same user to clear
their cache (`rm -rf ~/.cache/missionStudio/vizard`, so the fix above
was actually exercised fresh rather than reusing the earlier doubled
-nested extraction) and use the Run menu's "Launch Vizard" action
directly -- on `on_launch_vizard()` -> `_locate_or_fetch_vizard()` ->
the progress dialog -> `launch_vizard()`'s `subprocess.Popen` on the
freshly-extracted binary.

**Real result:** a Vizard window opened. This is the first
confirmation that the full chain -- download, extraction, the
post-extraction executable-bit fix-up
(`os.chmod`), and `subprocess.Popen` actually starting the Unity
player -- works end-to-end on real hardware, not just against mocked
`urlopen`/zip fixtures. `fetch_vizard()` and `launch_vizard()` together
are now confirmed to take a machine with nothing pre-installed all the
way to a running Vizard window with zero manual steps beyond the one
"Download Vizard" click.

Still unconfirmed: the live-stream path specifically (`-directComm`
pre-filling the socket address, clicking "Start Visualization",
spacecraft actually rendering during a run) -- that additionally needs
Basilisk itself installed, which this user's machine does not yet
have.

## First real live-stream run: a genuine label-legibility bug in the RTN panel colors

The user got Basilisk built from source and registered into the venv
missionStudio runs in, then ran a live-stream scenario end-to-end for
the first time -- the full pipeline (Basilisk -> live socket -> Vizard,
downloaded and launched entirely through this project's own auto-fetch
feature from the last few rounds) worked, and the RTN separation
panels (see the "RTN separation panels" section above) showed real,
correctly-labeled numbers. A screenshot of the running panel showed
the next real problem: the "R vs chief-1" row's dark blue fill made its
own label nearly impossible to read.

**Root-caused, not guessed**, by reading Vizard's own
`GenericStoragePanelUnit.prefab` directly (cloned earlier this
session): the on-bar device-name label
(`StorageName`'s `TextMeshProUGUI`) has its font color hardcoded to a
dark gray, `m_fontColor: {r: 0.19607843, g: 0.19607843, b: 0.19607843,
a: 1}` -- Vizard itself never recolors this text to contrast against
whatever fill color a `GenericStorage` message requests. Computing
perceived luminance (`0.2126*R + 0.7152*G + 0.0722*B`, 0-255 scale)
for that gray (~50) against the fill colors this project had been
using: plain `"blue"` is itself only ~18 -- literally *darker* than its
own label text -- and `"magenta"` (~73) isn't much better. Both R and T
happened to read at/near their max value in the screenshot (100/100
km), so their bars were fully saturated-color for their entire width,
with nothing to break up the low-contrast label. `"green"` (~92, used
for N) fares a little better, and wasn't the one flagged, likely
because N's own value was far below its max (0.45/100 km) so most of
its row was still the neutral gray "unfilled" background, not the
saturated fill. The panel's *other* rows (`"cyan"`, `"yellow"`,
`"orange"`, `"lightgreen"`) were never reported as unreadable -- and
indeed all compute to luminance 170-235, comfortably above the label's
own ~50.

**Fixed** by swapping the three RTN fill colors for lighter,
higher-luminance alternatives with the same computed margin as the
panel's already-readable rows, while keeping each visually distinct
from its neighbors: `"blue"` -> `"lightskyblue"` (~194), `"magenta"`
-> `"violet"` (~161), `"green"` -> `"springgreen"` (~192) -- all
`matplotlib`-recognized names accepted by `vizSupport.toRGBA255()`
exactly like the originals, so no new dependency or plumbing. Not
guessed -- computed directly with `matplotlib.colors.to_rgba()` against
the exact hardcoded label-gray value read from the real prefab file.

**Verification:** no existing test pinned the specific color-name
strings (`grep` confirmed), so this is a pure improvement with nothing
to update test-side; the luminance math above is reproducible directly
from Vizard's own checked-in prefab and `vizSupport.toRGBA255()`'s
`matplotlib` color table, not a subjective guess. Full suite still 671
passed, 99 skipped. Not yet re-confirmed visually against a live
Vizard window by the user -- that's the natural next real-machine
check.

## Result plots: titles/axes/legends, mean orbital elements, and a per-category unit policy

Real user feedback on the result plots, all in one request: "they shall
convey more information"; "should all have titles and more descriptive
axes names and legends"; add plots of AVERAGED (not just osculating/
"true") orbital elements, pointing at STK's "Brouwer-Lyd Mean (Short)"
data provider as the reference concept; "delta-V shall always be
displayed in m/s"; "altitudes, semi-major axes shall be displayed in
km"; "state vector elements shall be displayed in meters for position
and m/s for velocity".

**The unit-display part directly reversed an earlier decision.** This
project's own Plotly-migration work (see above) had added one blanket
rule: every series recorded in "m"/"m/s" displays in km/km-s on the
plot. That rule can't satisfy this new request at all -- it's keyed on
the literal unit STRING, but position (km requested: NO, stay meters)
and semi-major axis (km requested: YES) are both recorded in plain
"m"; velocity (stay m/s) and delta-V (stay m/s) are both plain "m/s".
Fixed by replacing that blanket rule with `results_widget._categorize()`,
which keys off what each named series actually *is* (its category:
state vector, orbit element, controller delta-V, ground-station access,
...), each with its own explicit, independently-chosen unit -- not a
per-unit-string rule at all. An unrecognized/future series still falls
back to the OLD blanket rule (`_legacy_display()`), so nothing regresses
silently for a series this registry hasn't been taught about yet.

**Titles/axis names/legends**: every one of the ~30 series categories
`engine.service`/`engine.link_budget` produce (position, velocity, all
6 osculating + 6 new mean orbital elements, attitude, body rate, sun
heading, control torque, reaction wheel speeds, every sensor type,
battery, all three controllers' delta-V/propellant/altitude/state,
ground-station access/slant-range/elevation/azimuth/link-margin) now
gets a real descriptive title (spacecraft name + a human category name,
e.g. "sat-1: Osculating Semi-Major Axis" instead of the bare
"sat-1.orbit_elements.semi_major_axis" dotted key), a y-axis label
combining a plain-English quantity name with its display unit (e.g.
"Semi-major axis [km]"), and legend entries relabeled from raw column
codes where that helps ("x"/"y"/"z" -> "X"/"Y"/"Z", "raw"/"smoothed" ->
"Raw"/"Smoothed (filtered)", "cumulative_delta_v" -> "Delta-V"). Orbit
-element angles (inclination/RAAN/argument of periapsis/true anomaly)
and ground-station elevation/azimuth additionally display in degrees,
not Basilisk's native radians -- matching every angle INPUT field this
app's own Scenario Editor already uses.

**Mean orbital elements**: the user's own reference (STK's "Brouwer-Lyd
Mean (Short)" data provider) describes a Brouwer-Lyddane-family mean
-element theory; rather than write a bespoke implementation of that
(real orbital-mechanics code this project's own standing rule is never
to hand-write/guess), checked what Basilisk itself ships first --
`orbitalMotion.clMeanOscMap()`, a real, already-used-elsewhere-in
-Basilisk first-order-J2 osculating<->mean mapping (Schaub & Junkins,
*Analytical Mechanics of Space Systems*; the exact same tool Basilisk's
own `meanOEFeedback` FSW module uses for closed-loop mean-element
control). Conceptually the same "strip the once-per-orbit J2 wobble off
the true elements" idea the user's own STK reference describes, built
from a tool Basilisk ships and Basilisk's own FSW code already trusts,
not invented here. `engine.service._mean_elements()` calls it per
-sample (sign=-1: osc -> mean) alongside the existing per-sample
osculating-element loop, publishing `.orbit_elements_mean.*` series
only when a real J2 term is actually being modeled (Earth, spherical
-harmonics degree >= 2) -- a point-mass-only central body has no J2
short-period oscillation in its simulated motion to remove, so applying
the map there would inject an artificial correction instead of
stripping out a real one, which `SimulationService`'s own gating
avoids entirely rather than computing something misleading.

Known, inherited (not introduced) limitation, documented directly in
`_mean_elements()`'s own docstring: first-order J2 mean-element theory
has a genuine mathematical singularity at the critical inclination
(~63.4/~116.6 deg) and degrades near 0/180 deg -- the same well-known
caveat STK's own Brouwer-Lyddane-based "Mean" elements carry. A
scenario at/near either inclination can show NaN/spiky mean-element
samples; Plotly leaves a gap for a NaN rather than erroring, so this is
a visible plot artifact, not a crash.

**Verification:** the core math was checked directly against a real
Basilisk build (this development sandbox has one, unlike most of this
project's work, which needed a real user's machine) -- for a real
non-degenerate LEO orbit (a=7000 km, e=0.01, i=45 deg, away from every
singular inclination), osc-vs-mean semi-major axis differs by ~3.7 km
(matching the expected order of magnitude for a J2 short-period term at
this altitude, `J2*(Re/a)^2*a`), and a round-trip through
`clMeanOscMap` with the sign flipped back (mean -> osc) recovers the
original osculating elements to ~1.8 m / ~8e-7 (e) / ~3e-7 rad (i) --
confirming both the math AND that this code calls `clMeanOscMap` with
the correct sign for "osc -> mean" (easy to get backwards, and nothing
else would have caught it). The gravity-setup wiring
(`central_body.radEquator` matching `orbitalMotion.REQ_EARTH*1000`
exactly) was also checked directly. Two new tests in
`tests/test_osculating_elements.py` encode these exact confirmed
numbers as regression tolerances (not guessed bounds). 24 tests in
`tests/gui/test_results_widget.py` cover the new per-category display
policy, including the two inverted-behavior regression guards (position
-in-meters, velocity-in-m/s) and new delta-V/altitude/mean-element
tests. Full suite: 674 passed, 101 skipped. NOT yet run end-to-end
through a full `SimulationService.run()` with live SPICE/network (this
sandbox's network policy denies `naif.jpl.nasa.gov`, the same
limitation noted throughout this project's history) -- the isolated
Basilisk-API-level verification above is real, but the full wiring
through an actual multi-sample run hasn't been watched end-to-end here.

## GUI "reactiveness": toasts, inline validation, and a real data-loss bug found along the way

Real user feedback: "make the GUI more 'reactive'... the user always
knows and understands what they did. visual cues would help... a better
display of settings, setups, parameters and values would help.
currently, everything looks very raw and unfinished." theme.py already
covers the app's visual CHROME (colors/borders/spacing -- an earlier
session's response to similar "looks unfinished" feedback), so this
request was really about something one level down: does the app
visibly react when you DO something?

A survey of the widget layer (spawned as a subagent to keep this out of
the main context, since it only needed to report back concrete
file:line findings, not make any changes) found the app already does
several of these right -- a window-title asterisk for unsaved changes,
a busy progress bar + disabled Run action + working Abort during a run,
QMessageBox.critical for every real error path -- but two patterns
repeated across most of the individual editor dialogs:

1. **No feedback on success**, only on failure. Add/remove/save a
   spacecraft (or sensor, or mission-sequence step) and the only signal
   anything happened is a list silently changing length -- no
   confirmation, no indication of WHICH item just changed.
2. **No live validation**, only a blocking dialog at Save/Run time that
   names the problem but not which of a dialog's many fields caused it.

Built two small, reusable primitives in a new `gui/feedback.py` (no new
dependency -- plain `QLabel`/Qt's own documented dynamic-property QSS
mechanism) rather than a one-off fix per dialog:

* `show_toast(window, message, kind=...)` -- a small, non-blocking,
  auto-dismissing notification anchored to a window's bottom-right
  corner, multiple stacking without overlapping. Not a guess at what
  "better feedback" should look like -- this exact gap was ALREADY
  documented in this app's own code: `MainWindow.on_launch_vizard`'s
  docstring admits a status-bar message is "easy to miss/get
  overwritten by the 'Running...' message that follows moments later"
  and had to be promoted to a one-time blocking dialog just to be
  noticed. A toast is the general-purpose version of that fix.
* `mark_invalid(widget, message)`/`clear_invalid(widget)` -- a red
  border (a new `[state="error"]` QSS rule in theme.py, using Qt's
  documented dynamic-property selector mechanism -- Qt only ships a
  fixed set of built-in pseudo-states like `:hover`/`:focus`, so a
  custom one like this is the officially sanctioned way to add another)
  plus the reason as a tooltip, live as the user types.

Wired into `main_window.py` (a toast on New/Open/Save/Run
complete/Run cancelled) and, as a complete worked example for the
inline-validation half, `spacecraft_editor.py`'s Name field (live,
per-keystroke empty/duplicate-name checking -- the dialog already knows
the other spacecraft names at construction time, no extra plumbing
needed) plus a toast on every Add/Edit/Remove, with the newly added/
edited row auto-selected in the list so it's obvious at a glance which
one just changed.

**A real bug found while wiring this in, not a hypothetical**:
`SpacecraftEditorDialog._on_accept()` called `self.accept()`
unconditionally -- an empty/duplicate name wasn't checked until AFTER
the dialog had already closed, in the caller
(`_on_add`/`_on_edit`/`_on_new_from_template`), which then showed a
`QMessageBox` and returned -- by which point the dialog (and every
other edit the user had just made in it) was already gone and silently
discarded. The exact same duplicate-name mistake this feature was
built to catch inline was ALSO capable of quietly destroying a user's
work. Fixed by checking the name (empty AND duplicate) inside
`_on_accept()` itself, before `accept()`, so the dialog only closes
once the name is actually valid -- the outer checks in
`_on_add`/`_on_edit`/`_on_new_from_template` are now unreachable in
practice but left in place as a harmless second guard.

**A real Qt lifetime bug found by the test suite, not guessed**: the
first version of `show_toast()`'s auto-dismiss timer called
`toast.deleteLater()`. Running the full `main_window` test suite
surfaced `RuntimeError: libshiboken: Internal C++ object (_Toast)
already deleted` on three tests -- a window can legitimately be closed
(destroying its child toast along with it, via Qt's normal parent-child
ownership) BEFORE that toast's own auto-dismiss timer fires, and the
timer's callback still tried to touch the now-dangling wrapper. Fixed
with `shiboken6.isValid()` (the documented way to check whether a
`QObject`'s underlying C++ object is still alive) guarding the dismiss
callback, and switched to `hide()` instead of `deleteLater()`
regardless (avoids a caller -- tests do this -- holding a dangling
reference to whatever `show_toast()` returned).

**Verification:** 13 new tests (`tests/gui/test_feedback.py`: toast
visibility/position/stacking/auto-dismiss/kind-coloring, inline mark/
clear; `tests/gui/test_spacecraft_editor.py`: live inline validation on
the Name field, the accept-blocks-and-keeps-the-dialog-open regression
guard for the data-loss bug above, toast-on-add/remove). Full suite:
687 passed, 101 skipped. All of this is Basilisk-free GUI-layer code,
run and confirmed headless (`QT_QPA_PLATFORM=offscreen`) in this
development sandbox exactly like every other GUI test in this project
-- nothing here needed a real display or a real user's machine to
verify.

## Rolling gui/feedback.py out to every other list-editor dialog

Explicit follow-up request: "roll it out to the other editor dialogs
too" -- the toast/inline-validation primitives above had only been
wired into `spacecraft_editor.py` as a worked example. Rolled out to
every other dialog with the same "Add/Edit/Remove a named/unnamed list
item" shape: `sensor_actuator_editor.py`
(`SensorActuatorListWidget`/`_ItemEditorDialog`), `ground_station_editor.py`
(`GroundStationListWidget`/`GroundStationEditorDialog`),
`mission_sequence_editor.py` (`MissionSequenceEditorWidget` -- no name
-uniqueness concept here, commands aren't named, so toasts only, no
inline validation), and `monte_carlo_editor.py`
(`DispersionListWidget` -- same reasoning, dispersions aren't named
either). Also added a completion toast to
`spacecraft_editor.py`'s two bulk-generate actions (Walker constellation,
phasing formation) that hadn't been covered in the first pass.

**The exact same data-loss bug found and fixed in
`SpacecraftEditorDialog` turned up, unchanged, in both other named-item
dialogs** -- not a coincidence: `sensor_actuator_editor.py`'s
`_ItemEditorDialog` and `ground_station_editor.py`'s
`GroundStationEditorDialog` were both written following
`SpacecraftEditorDialog`'s own shape (their docstrings say so
explicitly -- "mirrors ... SpacecraftListWidget's shape"), so the bug
(`_on_accept()` closing the dialog unconditionally, with the duplicate
-name check only happening afterward, in the now-unreachable-if-wrong
caller) had been copied right along with the pattern it came from.
Fixed identically in both: the dialog now takes the other items' names
at construction, validates the Name field live as the user types
(`textChanged` -> `mark_invalid`/`clear_invalid`), and `_on_accept()`
checks empty/duplicate BEFORE calling `accept()`, so the dialog only
closes once the name is actually valid. The outer checks in each list
widget's `_on_add`/`_on_edit` are now unreachable in practice but left
in place as a harmless second guard, matching the fix already applied
to `SpacecraftEditorDialog`.

**Verification:** every dialog's existing test suite still passes
unchanged (the new pre-check in `_on_accept()` is never exercised by
tests that monkeypatch `.exec()` directly to bypass it, exactly as
already noted for `SpacecraftEditorDialog`'s own tests) plus new tests
mirroring that same file's pattern: live inline-error-on-duplicate,
accept-blocks-and-keeps-the-dialog-open, and toast-shown-on-add/edit/
remove, for each rolled-out widget. Full suite: 695 passed, 101
skipped, including the one `requires_basilisk`-marked phasing-formation
toast test, re-run directly against this sandbox's real Basilisk build
(`/tmp/bsk_venv4`) rather than left unverified.

## "Propagation setup" summary: from three pipe-joined lines to a labeled form

Real user feedback, with a screenshot: the "Propagation setup" group's
read-only summary (`ScenarioEditorWidget._refresh_propagation_summary`)
rendered as three unlabeled, ``" | "``-joined lines in a single QLabel
(``"earth | spherical harmonics (degree 10) | +sun, moon"``, etc.) --
"looks incredibly unfinished, raw and unprofessional and very cluttered
and doesnt help the user understanding what those values stand for".
Checked directly: correct complaint -- this was the ONE settings
summary in the whole app built as free text instead of the labeled
field-name/value rows every other panel already uses
(`spacecraft_editor.py`, `ground_station_editor.py`, and
`PropagationSetupDialog` ITSELF, the exact dialog this summary is
summarizing).

**Fixed** by replacing the single `QLabel` with a `QFormLayout` of
label/value rows, rebuilt on every refresh (row count varies -- the
third-body-perturbers and space-weather rows only appear when
relevant). Every row label is copied VERBATIM from
`PropagationSetupDialog`'s own `form.addRow(...)` calls ("Central
body", "Integrator", "Dynamics task rate [s]", "Duration [days]",
"Atmosphere model", ...) -- the summary and the dialog that edits it
now use identical terminology instead of two different ways of saying
the same thing.

**Verification:** rendered the actual widget headless
(`QT_QPA_PLATFORM=offscreen`, `QGroupBox.grab()` to a PNG) and looked
at it directly rather than trusting the code -- confirmed it now reads
as a clean label/value table instead of the cluttered original. Two
existing tests that asserted against the old single-label `.text()`
were updated (a small `_propagation_summary_text()` test helper
flattens the new form's rows back into one string so the same substring
assertions still work), plus one new test asserting every expected row
label is actually present. Full suite: 696 passed, 101 skipped.

## A visual sweep for "raw panels" elsewhere in the app, and one real bug found by it

Follow-up request: "check the rest of the app for similar raw panels".
Grepped for the same free-text-summary shape across every `gui/*.py`
file, and found nothing else built that way -- the Propagation setup
summary really was the one outlier; every other panel
(`kernel_status_widget.py`'s table, `monte_carlo_editor.py`'s own
`QFormLayout`, every editor dialog) already uses labeled rows.
`mission_output_widget.py`'s plain-text report log was deliberately
left alone -- it's documented as a "debug console" for arbitrary,
variable-shaped report data (series names/array values the user
defines via `report` commands), where a monospace log is the
appropriate format, not a settings dump with a fixed field set.

Grepping isn't the same as looking, so every major screen was also
actually RENDERED headless (`QT_QPA_PLATFORM=offscreen`,
`QWidget.grab()` to a PNG) and inspected as an image, not just read as
code: the full Scenario Editor tab, all 4 tabs of
`SpacecraftEditorDialog`, the main window overview, `VizardDialog`,
`GroundStationEditorDialog`, and `PropagationSetupDialog` itself (not
just its scenario-editor summary). That caught a real bug the grep
alone would have missed entirely: `PropagationSetupDialog`'s
"Atmosphere & drag" `QGroupBox` title rendered as the visibly broken
"Atmosphere _drag" in the actual screenshot -- Qt treats a lone `&` in
a group box title as a mnemonic marker (the same mechanism behind
`"&File"`/`"&Save"` menu shortcuts elsewhere in this app, which are all
correct, intentional uses -- this was the one place a literal `&` was
meant as prose, not a mnemonic). Fixed with `"&&"`, Qt's own documented
escape for a literal ampersand -- confirmed by re-rendering and looking
at the PNG again, not just trusting the source change.

**Verification:** one new regression test
(`test_propagation_setup_dialog.py`) asserts the group's stored title
is the escaped `"Atmosphere && drag"` form, not the single-`&` one --
`QGroupBox.title()` returns Qt's raw stored string, not the rendered/
mnemonic-resolved text, confirmed directly (the first version of this
test asserted the wrong thing and failed against the real widget,
caught before it was ever committed). Full suite: 697 passed, 101
skipped.

## A real user screenshot: "Generate phasing formation" rendered almost entirely off-screen

A real user sent a screenshot of the "Generate phasing formation"
dialog that looked badly broken: every row's own label was missing --
only thin fragments of text were visible hugging the LEFT edge of the
screen ("t holds a target along-track separation from an existing
chief spacecraft...", "pied from here)"), with each input field
stretched to fill the entire visible width.

**Root-caused directly from the fragments themselves**, not guessed:
those fragments are the TAIL ENDS of longer strings -- the visible
"...pied from here)" is the end of the row label "Template spacecraft
(everything else copied from here)", and the long visible sentence
fragment is the middle of this dialog's own top description paragraph.
That only makes sense if the dialog's true left edge sits far off the
left of the screen (a large NEGATIVE x position) -- which happens when
a window manager centers a dialog that's far wider than the screen
(`center_x = (screen_width - dialog_width) / 2`, strongly negative once
`dialog_width` is in the thousands of pixels). Checked
`phasing_formation_dialog.py` directly: its top description `QLabel`
(a full paragraph, matching the visible fragment exactly) had no
`setWordWrap(True)` call -- without it, Qt sizes a `QLabel` to fit its
ENTIRE text on one line, and everything else in the dialog's
`QVBoxLayout` is forced just as wide. Confirmed the mechanism by
actually reproducing it: rendering the dialog at its natural size
(`.show()`, no forced resize -- the earlier "raw panels" sweep's own
blind spot, since every dialog checked there WAS explicitly resized in
the test script, accidentally masking exactly this bug) showed the
same oversized layout.

**The same copy-pasted shape (a `QVBoxLayout` starting with an
unwrapped top description `QLabel`) turned up, with the identical bug,
in four more places** once checked systematically:
`constellation_dialog.py` (`WalkerConstellationDialog`, the sibling
dialog `phasing_formation_dialog.py`'s own docstring says it mirrors),
`vizard_dialog.py`, `spacecraft_template_dialog.py`'s static banner
label, and `spacecraft_editor.py`'s Vizard-model tab description. Fixed
identically in all five: assign the `QLabel` to a variable,
`.setWordWrap(True)`, then add it to the layout -- matching the
word-wrap pattern this codebase already uses correctly elsewhere (e.g.
`sensor_actuator_editor.py`'s hint label,
`propagation_setup_dialog.py`'s own top label, which rendered correctly
in the earlier sweep specifically BECAUSE it already had this call).

**Verification:** re-rendered both `PhasingFormationDialog` and
`WalkerConstellationDialog` at natural size (no forced resize) and
looked at the resulting PNGs -- both now render at a sane size (569x682
and 743x531) with every label fully visible. Five new regression tests
(one per fixed dialog) assert the long description label's
`wordWrap()` is `True`, plus a loose upper bound on the dialog's
`sizeHint().width()` for the two dialogs most likely to regress
visibly. Full suite: 702 passed, 101 skipped.

## Two more real UX bugs, found by continuing the same check

Follow-up request: "check the rest of the app for other UX issues".
Two genuine bugs found, neither a guess:

**Monte Carlo dispersion dialog showed all three value fields at
once, regardless of Kind.** `_DispersionEditorDialog` always displayed
Bounds AND Mean AND Std-deviation, editable, no matter which "Kind"
(uniform/normal/uniform_euler_mrp) was selected -- but
`to_dataclass()` only ever uses the pair matching the current kind,
silently discarding the rest. A user could type a Mean/Std-deviation
value while Kind="uniform" and have it vanish with zero indication
anything was ignored. Fixed by hiding whichever row(s) don't apply to
the selected kind (`_on_kind_changed`, wired to `kind_combo`'s own
signal), so the dialog only shows what will actually be used.

**`PropagationSetupDialog`'s "Atmosphere & drag" description text was
silently cut off mid-sentence**, ending at "...open a" with the rest
of the paragraph missing -- found by rendering the dialog and looking
at the PNG (again), not by reading the source, where the text is
complete. Root-caused precisely by comparing the label's actual
`geometry().height()` (27px) against its own `heightForWidth(520)`
(68px): `QFormLayout.addRow(single_spanning_widget)` did not reserve
this label its full wrapped height, unlike this dialog's OWN top-level
`intro_label` (added via plain `QVBoxLayout.addWidget()`, which has
never had this problem). Fixed by restructuring the group to use a
`QVBoxLayout` for the description label plus a nested `QFormLayout`
for the actual fields, mirroring the already-proven-correct pattern.
Fixing that alone uncovered a SECOND, related bug: the dialog's window
never grew to match its new (taller) `sizeHint()` on first `show()`
(measured directly: window stayed 871x734 while `sizeHint()` said
871x768), clipping the group's own last two rows against its border.
Fixed with an explicit `self.resize(self.sizeHint())` at the end of
`__init__`, after every group is built.

Searched for the same `form.addRow(wrapped_label)` shape (the root
cause of the second bug) everywhere else in `gui/`; one more instance
turned up (`mission_sequence_editor.py`'s "assignment" command page),
but direct measurement showed it was NOT actually clipped (no
`setMaximumWidth` cap and no extra `QGroupBox` nesting meant it
happened to converge correctly on the first layout pass) -- left alone
rather than "fixed" on spec, since it isn't broken.

**Verification, more rigorous than the pattern-matching used to find
the bugs**: wrote a script that renders every dialog in the app (every
`_CommandEditorDialog`/`_ItemEditorDialog`/`_DispersionEditorDialog`
"kind" selection included -- 25 total dialog/state combinations) and
directly compares every word-wrapped `QLabel`'s allocated
`geometry().height()` against its own `heightForWidth()`, rather than
trusting that fixing the two found instances covered everything.
Confirmed clean everywhere, including cycling through every tab of
`SpacecraftEditorDialog` (`QTabWidget` defers layout for hidden tabs,
so checking only the initially-visible one could have missed a real
bug on another tab). Two new regression tests
(`test_dispersion_dialog_hides_fields_not_used_by_the_selected_kind`,
`test_srp_pointer_label_gets_its_full_wrapped_height_not_clipped`)
plus one for the resize fix
(`test_dialog_resizes_to_its_own_sizehint_on_construction`). Full
suite: 705 passed, 101 skipped.

## Results and Mission Output tabs: a searchable series picker, and a real missing export button

Follow-up request: "check for more UX issues in the results and
mission output tabs".

**Results tab's "Series:" picker had no way to search.** A real
scenario (the built-in 6-satellite Walker constellation template, for
one) produces 30-40+ series, all named after the dotted scheme
`engine.service`/`engine.link_budget` use
(`leo-02-03.orbit_elements_mean.inclination`, ...) -- confirmed
directly by building a synthetic multi-spacecraft `ResultSet` and
listing what the combo box actually shows. Scrolling a flat, plain
`QComboBox` that long to find one series is tedious, and the useful
discriminator (spacecraft name, or the category after the first dot)
is usually in the MIDDLE of the name, not the start. Made the combo
editable with a substring-matching (`MatchContains`, not the default
prefix-only `MatchStartsWith`), case-insensitive `QCompleter` bound to
the combo's own model -- confirmed the completer stays correctly in
sync after `set_result()` clears and rebuilds the combo (same model
object throughout, not a stale one), rather than assuming Qt's
`QComboBox.clear()`/`addItem()` mutate the model in place.

**Mission Output tab had no CSV export at all.** Checked
`engine/results.py` directly: `CommandSummary.export_csv()` already
existed, fully implemented and already covered by its own tests at the
engine layer -- but nothing in `mission_output_widget.py` ever called
it. The neighboring Results tab has had an "Export all series to
CSV..." button since the Plotly migration; a user running a
`mission_sequence` with `report` commands had no equivalent way to get
that data out except manually selecting/copying the plain-text debug
log. Added an "Export to CSV..." button mirroring
`ResultsWidget._on_export()`'s exact pattern (a single
`QFileDialog.getSaveFileName`, not `getExistingDirectory` --
`CommandSummary.export_csv()` writes ONE file, unlike
`ResultSet.export_csv()`'s one-file-per-series), disabled until a
summary with at least one report exists (a summary with zero `report`
commands has nothing meaningful to export).

**Verification:** 2 new tests confirm the completer's filter mode/case
-sensitivity and that it survives a `set_result()` rebuild pointing at
the same model object; 4 new tests cover the export button's enabled
-state transitions (no summary / a summary with zero reports / a
summary with reports / after `clear()`) and a genuine round-trip
(writes a real temp-dir CSV, confirms the expected series name appears
in its content). Both tabs re-rendered headless and looked at directly
-- the Results tab's actual Plotly canvas can't be screenshotted in
this sandbox (`QWebEngineView` doesn't rasterize under this sandbox's
software-only GL fallback, a pre-existing, already-documented
limitation -- verified via JS introspection instead, per this file's
own module docstring), but the picker/toolbar row above it, and the
entire Mission Output tab, render and were inspected as images. Full
suite: 710 passed, 101 skipped.

## Kernel Status tab: a table whose own header didn't fit, and an error message that made it worse

Follow-up request: "check the rest of the app for other UX issues".
First checked every other dialog with a "kind"/"pattern" selector for
the same shown-regardless-of-relevance bug class the Monte Carlo
dispersion dialog had -- none found (constellation/phasing-formation
dialogs use every field unconditionally; `spacecraft_editor.py`'s
optional sections are all CHECKABLE `QGroupBox`es, which already
auto-disable their own contents when unchecked, the correct pattern).
Then rendered the tabs/widgets not yet looked at directly: Load
Scenario (clean), and the Kernel Status tab, which had a real, two
-layer bug.

**The table's own column headers didn't fit.** `KernelStatusWidget`'s
4-column table used a blanket `QHeaderView.ResizeMode.Stretch` on every
column -- found by actually populating the table and looking at it:
"Cache last modified (UTC)" (by far the longest header) rendered
truncated on BOTH ends ("ache last modified (UTC"), while "Kernel" sat
in a column much wider than its content needed, since Stretch forces
every column to the exact same width regardless of what's in it. Fixed
by stretching only "Path" (the one column whose content -- real
filesystem paths -- genuinely benefits from claiming the remaining
space) and sizing the other three to their own content
(`ResizeToContents`).

**Fixing that uncovered a second problem**: the "Available" column
embedded the full error message inline (`f"NO: {status.error}"`), so
once its own sizing was fixed to `ResizeToContents`, a single long
error message (e.g. "download failed: connection refused") now forced
THAT column wide instead -- stealing width right back from "Path", the
more important column to keep readable. Fixed by showing just "NO" in
the cell and moving the full error to the item's tooltip (the same
"short status at a glance, detail on demand" pattern `gui.feedback`'s
inline-validation already uses). Added the same tooltip to the "Path"
cell itself while at it: `Stretch`-mode columns can't be interactively
widened by the user the way `Interactive`-mode ones can, so a
genuinely long real path can still end up visually truncated with no
way to fix it except hovering.

**Verification:** rendered the table both empty and populated (with
synthetic `KernelStatus`-shaped data -- duck-typed via
`SimpleNamespace`, since the real dataclass needs a Basilisk import
this sandbox doesn't have) and looked at the PNGs before and after each
fix. 3 new tests: every column's actual `sectionResizeMode()` matches
the intended per-column policy (not just "some column somewhere
stretches"), the unavailable-kernel row's cell text is exactly "NO"
with the real error as its tooltip, and the path cell's tooltip holds
the untruncated path. Full suite: 713 passed, 101 skipped.

## A missing Monte Carlo toast, and a version nowhere in a versioned, packaged app

Follow-up request: "check the rest of the app for other UX issues".
Checked whether Basilisk's own `MonteCarlo.Controller` exposes any
real per-run progress hook, since an earlier survey flagged Monte Carlo
runs as having no progress reporting -- confirmed directly from
Basilisk's own source (`src/utilities/MonteCarlo/Controller.py`,
`src/utilities/simulationProgessBar.py`): its only "progress" is a
`tqdm` terminal bar with no programmatic callback at all, and
`main_window.py`'s own code already documents this exact limitation
honestly (the indeterminate busy bar IS the correct, deliberate choice
here -- not a bug to fix, and not something to fake a fraction for).

Two real, smaller gaps found instead:

* **`_on_monte_carlo_finished`'s all-succeeded branch had no toast**,
  unlike its single-run sibling `_on_run_finished` (added a few rounds
  ago in this same audit). The partial-failure branch already shows a
  `QMessageBox.warning` -- strong enough feedback on its own, same
  reasoning as `_on_run_failed` having no toast alongside its own
  `QMessageBox.critical` -- so only the silent all-succeeded case
  needed one.
* **No way to check the app's own version from inside the app.**
  `missionstudio.__version__` ("1.0.0") already existed, but nothing in
  the GUI ever surfaced it -- no Help menu, no About dialog, no version
  string anywhere, despite this being a packaged desktop app shipping
  `.deb`/Windows installers. A user filing a bug report had no way to
  even state which version they were running without checking
  `pyproject.toml` by hand. Added a `&Help` menu with an "About
  missionStudio" action showing the version plus whether Basilisk is
  actually available in this install (the same
  `importlib.util.find_spec("Basilisk")` check this project's own test
  suite already uses to gate `requires_basilisk` tests).

**Verification:** rendered the menu bar and confirmed "Help" appears
correctly. 3 new tests: the all-succeeded Monte Carlo toast fires and
mentions "Monte Carlo complete", the partial-failure branch does NOT
also show one, and the About dialog's shown text contains both the
real `missionstudio.__version__` string and the word "Basilisk". Full
suite: 716 passed, 101 skipped.

## App icon: from an accidental eye to a satellite, after it was shown to the user first

Explicit request: "create an app icon for the app". One already
existed (a procedurally-drawn `QPainter` icon from an earlier Phase 5
round -- a dark central body inside a thin, inclined orbit ellipse
with a small dot on the ring) -- rather than silently building a
second, competing icon, it was rendered at several sizes and shown to
the user first, who confirmed: keep the concept, but "refine it to
read clearer at small sizes".

**Diagnosed why, rather than guessing at a fix**: at 16-32px (the
sizes this icon is actually seen at most -- window titlebar, taskbar)
it read as a cartoon eye, not an orbit. Tried several parameter-tuning
passes on the SAME structure first (thicker ring stroke, a bigger/
brighter satellite dot) and rendered each one -- they made it read MORE
eye-like, not less (a bigger, lighter dot became an eye's catchlight).
The real problem was structural: "a filled disc centered inside a
surrounding ring" is close to the universal flat-icon glyph for an eye
(pupil + iris) regardless of stroke width or color, so no amount of
tuning on that same silhouette was ever going to fix it.

**Redesigned around a different silhouette instead**: a satellite
glyph (an angular body between two solar-panel wings, plus a thin
antenna at larger sizes) -- confirmed by rendering it at every size
from 256px down to 16px that it stays legible and reads clearly as
spacecraft hardware, with no closed ring-around-a-disc shape left to
be mistaken for an eye. Also a better thematic fit for a
*mission-analysis* tool generally than one specific orbit-and-dot.

**A second real bug found along the way**: rendering the new design
against both a light AND a dark background (not assumed -- many
desktop taskbars are dark) showed the body's original near-black color
nearly disappearing against a dark background. Fixed by making the
body gold instead -- not arbitrary: real satellites commonly use
gold-foil thermal-blanket bodies, so gold-body-next-to-blue-panels is
representationally accurate, not just decorative, and it happens to
have good contrast against both light and dark surfaces.

Fine detail (the antenna; grid lines on the panels/body) is omitted
below its own legibility threshold (found by rendering both and
comparing, same as everything else here) rather than drawn at a
thickness that just anti-aliases into noise at small sizes.

**Verification:** every candidate was rendered and actually looked at
-- individually, side by side across sizes, and against both light and
dark backgrounds -- at every stage of this redesign, not just the
final result. 2 new regression tests: the large-size render includes
the specific gold body color (pinning the part of this redesign a
generic color-count check wouldn't catch regressing), and a 16px
render has meaningfully fewer distinct colors than a 256px one
(confirming the size-gated detail thresholds actually take effect).
Full suite: 718 passed, 101 skipped.

## Taskbar always shows a generic cog icon, never the app icon

**Real user report**, asked right after the icon redesign above: "when
launching the GUI, in the task bar it always shows a cog symbol, why?"
-- not a rendering bug in the icon itself (that was already verified
extensively, see above), so the investigation went into how Linux
desktop shells actually source a running window's taskbar/dock icon.

**Root cause, confirmed by reading how `app.py` launches the window and
comparing it against the packaging/ `.desktop` entries**: most Linux
desktop shells (GNOME Shell, KDE Plasma, and Wayland compositors
generally) do not take a running window's icon from the `QIcon` passed
to Qt's `setWindowIcon()` at all. They match the window to an
*installed* `.desktop` entry -- by "desktop file name" / app-id on
Wayland, or by `WM_CLASS` against that entry's `StartupWMClass=` on
X11 -- and use THAT entry's `Icon=` key. `app.py`'s `main()` never
called `QApplication.setDesktopFileName()`, and neither
`packaging/missionstudio.desktop.in` nor `packaging/deb/.../missionstudio.desktop`
set `StartupWMClass`, so neither matching path could succeed. With no
match, the shell falls back to its own generic "unknown application"
icon, which in Adwaita/Breeze/Yaru-derived icon themes is exactly the
gear/cog glyph reported.

**Fix:** `app.py` now calls `app.setDesktopFileName("missionstudio")`
right after `setApplicationName`/`setOrganizationName`, and both
`.desktop` files gained `StartupWMClass=missionstudio` -- all three
spellings of this identifier now agree with each other and with the
`.desktop` files' own installed basename (`missionstudio.desktop`).
Documented inline in `app.py` that this alone is not sufficient for a
from-source run (`python3 -m missionstudio.gui.app`, or `missionstudio
gui` from a dev checkout): the match still needs a real
`missionstudio.desktop` entry present somewhere in `XDG_DATA_DIRS`,
which currently only `packaging/install.sh` (or the `.deb`) installs,
together with the rendered icon PNG under the `hicolor` icon theme --
so a plain source checkout will keep showing the generic icon
regardless, independent of this fix.

**Verification:** 3 new regression tests in `tests/gui/test_app.py`
(new file): `main()`'s source actually contains the
`setDesktopFileName("missionstudio")` call, both `.desktop` files
actually declare `StartupWMClass=missionstudio`, and the identifier
passed to `setDesktopFileName()` matches the `.desktop` files' own
installed basename (so the three spellings can't silently drift apart
again). Full suite: 722 passed, 101 skipped.

## Basilisk feature audit, and a backlog to close the gaps

**Real user question**: "What other features does basilisk have, that
were not yet integrated in the app?" A background agent inventoried
every capability module under `src/simulation/` and `src/fswAlgorithms/`
in this checkout and the answer, compared directly against what
`engine/service.py`/`engine/fsw.py` actually import, was sobering: this
app wires up 4 of ~8 sensor kinds, 1 of several actuator types, 5 of
~18 attitude-guidance modes, 1 control law, and none of attitude
determination/thermal/onboard-data-handling/communication/optical-nav/
small-body-nav/formation-flying-FSW at all -- sensors feed FSW modules
*truth* directly (`simpleNav`) rather than a real estimated state, and
every maneuver uses an idealized `extForceTorque` rather than a real
thruster. The user's follow-up, verbatim: "Yes please, all of them. But
make them useful end to end, meaning easy setup for user, useful
simulation run and visualization and helpful outputs and results." --
a real multi-week backlog, tracked as 19 prioritized tasks (schema +
engine + GUI + tests + docs per item, not a checkbox), starting with
the highest-value/most-tractable first.

**A significant, re-discovered sandbox constraint**: attempting to
verify the first item (gravity gradient torque, below) against the
real Basilisk build at `/tmp/bsk_venv4` failed -- not from a bug in the
new code, but because `engine.service.SimulationService.build()`
unconditionally needs SPICE kernels (`build_spice_interface()`), and
this sandbox's network egress to `naif.jpl.nasa.gov` and its
`hanspeterschaub.info` backup mirror is blocked by the outbound proxy
policy (confirmed with the proxy's own `recentRelayFailures` log:
`connect_rejected ... gateway answered 403`). Confirmed this is NOT new
or specific to this change by re-running an EXISTING, previously
-documented-as-passing test (`test_service_run_live.py`) here: it fails
with the identical blocked-kernel error. This is, in fact, already
`engine/kernels.py`'s own documented verification status ("the actual
KERNEL DOWNLOAD could not be completed in that same environment") --
not a new discovery, just re-confirmed here because it materially
changes what "verified end-to-end" can mean for the rest of this
backlog: every dynamics-level feature from here on can be verified at
the *API* level (real class/attribute names, confirmed against the
actual compiled Basilisk module and its own shipped unit test's exact
call sequence -- the same "never fabricate a Basilisk API" discipline
`engine/fsw.py` was already built under, before this sandbox had a
Basilisk build at all) but not at the *executed-dynamics* level, in
this sandbox, until kernel network access is available.

### Gravity gradient torque (task 1 of 19)

The first, quickest-to-land item: real torque from the central body's
gravity acting across a spacecraft's own (non-spherical) inertia,
currently missing entirely -- a real, physically meaningful disturbance
for anything coasting without active attitude control, or with a
notably non-uniform inertia tensor. Added
`SpacecraftConfig.enable_gravity_gradient` (default `False`, so every
existing scenario's dynamics are bit-for-bit unchanged), wired to
Basilisk's `GravityGradientEffector` in `engine/service.py` right
alongside the existing drag/SRP effector blocks: `addPlanetName()` on
the central body only (a third-body perturber's gravity-gradient
contribution is smaller by roughly the cube of the distance ratio --
negligible at any real mission distance, so skipped rather than adding
an import per perturber for no measurable effect), then
`addDynamicEffector()` -- it reads the spacecraft's own already
-registered inertia/position/attitude directly, no extra message
wiring needed. Added a matching checkbox next to the existing drag/SRP
toggles in the spacecraft editor's "Orbit / mass" tab (rendered
headless and inspected to confirm placement/round-trip, same discipline
as every other GUI change this project ships).

**Verification:** `GravityGradientEffector`'s constructor,
`addPlanetName()`, and `addDynamicEffector()` call sequence confirmed
directly against this checkout's own
`GravityGradientEffector/_UnitTest/test_gravityGradient.py`, and its
class/method names additionally confirmed to exist on a real built
Basilisk module (`/tmp/bsk_venv4`), not just read from source. Two new
`requires_basilisk` regression tests
(`tests/test_gravity_gradient.py`) are written to actually run the
physics -- an elongated-inertia, uncontrolled (`fsw_mode=None`)
spacecraft's attitude must stay frozen with the flag off and visibly
drift with it on -- but could not be EXECUTED here for the SPICE-kernel
reason above; they will run given kernel network access (a real dev
machine, or CI). GUI checkbox round-trip and rendering confirmed
headless. Full Basilisk-independent suite: 722 passed, 103 skipped (101
-> 103: the two new SPICE-gated tests join the existing
`requires_basilisk` skip bucket in this sandbox, same as every other
test in it).

### Real thruster actuator (task 2 of 19)

`"thruster"` was schema-valid since Phase 2 but `engine.service` hard
-rejected it at run time -- every maneuver/station-keeping/phasing burn
used an idealized `extForceTorque`/direct-mass-bookkeeping model, and a
spacecraft could not use real thruster hardware for attitude control at
all (only reaction wheels). Wired up the real chain from
`examples/scenarioAttitudeFeedback2T_TH.py`: `mrpFeedback` ->
`thrForceMapping` (torque -> per-thruster force) -> `thrFiringSchmitt`
(Schmitt-trigger on-time logic) -> `thrusterDynamicEffector`, with
thrusters built via `simIncludeThruster.thrusterFactory()` (new
`ActuatorConfig.params` keys: `r_B` [m], `tHat_B` [-], `MaxThrust` [N]
required; `thruster_type`, `steadyIsp`, `MinOnTime` optional). A
spacecraft may use `"reaction_wheel"` actuators or `"thruster"`
actuators, not both -- mixing them would need a control-allocation
module (Basilisk's `torqueScheduler`) this app doesn't build, so
`SpacecraftConfig.validate()` now rejects the mix early with a specific
message rather than engine.service silently using only one.

**A real, unrelated bug found and fixed along the way**: the sensor/
actuator editor's vector-param UI (`_ParamSpec`) gave EVERY 3-element
list-valued param -- direction or not -- a "Normalize" button. That's
correct for a direction (`nHat_B`, `gsHat_B`, and now `tHat_B`), but
`r_B` is a thruster's body-frame LOCATION in meters: clicking Normalize
on it would silently rescale a real thruster's mounting point to
exactly 1 meter from the body origin, corrupting the actual geometry.
Magnetometer's `noise_std_tesla` (a per-axis noise std-dev, also not a
direction) turned out to have the exact same latent bug already. Fixed
with a new `_ParamSpec.normalizable` flag (default `True`, so every
existing direction-valued spec is unaffected), set `False` for both
`r_B` and `noise_std_tesla`, and the Normalize button is now only
built when `normalizable` is set.

**Visualization**: `engine.vizard.enable_vizard()` gained
`thr_effectors_by_spacecraft`, so Vizard now draws native thruster
plume effects when a spacecraft's thrusters fire -- this was previously
explicitly documented as "not passed: nothing to visualize" in that
module's own docstring, now genuinely true. `SimulationService.run()`
also reports a new `{name}.thruster_on_time` result series (per
-thruster commanded on-time, seconds) alongside the existing
`{name}.rw_speeds`, with its own plot category ("Thruster On-Times") in
the results viewer.

**Verification**: unlike gravity gradient torque above, this one really
could be run end-to-end in this sandbox -- attitude-only dynamics (no
orbit, no gravity, no SPICE) don't hit the blocked-kernel restriction
at all, so a standalone script driving `engine.fsw`'s new builder
functions directly against a bare `SimulationBaseClass` was written,
run for real against `/tmp/bsk_venv4`'s Basilisk build, and genuinely
worked: an 8-thruster cluster controlling a spacecraft with initial
attitude error `[0.3, 0.2, -0.1]` (MRP) drove it down to
`[0.054, 0.049, -0.007]` in 60 simulated seconds, with real nonzero
per-thruster on-times throughout. Turned into two real, ACTUALLY
-PASSING `requires_basilisk` tests
(`tests/test_thruster_control.py::test_thruster_chain_commands_nonzero_on_times`/
`::test_thruster_chain_reduces_attitude_error`) -- confirmed by running
them through pytest against that same build, not just the standalone
script. Plus 5 new schema-validation tests (required `r_B`/`tHat_B`/
`MaxThrust`, valid-thruster-validates, reaction_wheel+thruster-mix
-rejected) and 2 new GUI tests (thruster kind no longer shows the
"not simulated yet" warning; `r_B`'s vector row has no Normalize button
while `tHat_B`'s keeps one) -- all real, all passing. Full
Basilisk-independent suite: 729 passed, 105 skipped.

### Reaction wheel momentum desaturation (task 3 of 19)

Reaction wheels had no way to shed accumulated momentum at all -- a long
-enough scenario would simply saturate them with no recourse, silently
losing attitude control once that happened. Wired up Basilisk's real
desaturation chain (`thrMomentumManagement` -> `thrForceMapping`,
reused in "momentum-dump mode" via `angErrThresh` set above pi -- the
module's own documented way to make it output an impulse instead of a
torque -- -> `thrMomentumDumping`), firing a spacecraft's `"thruster"`
actuators to bleed off reaction-wheel momentum while those SAME wheels
stay in control of attitude the whole time -- a genuinely different job
from task 2's thruster-as-primary-control path, built as a separate
signal path (`engine.fsw.build_momentum_dumping`) that is never built
for the same spacecraft as `build_thruster_force_mapping`.

New `SpacecraftConfig.momentum_dumping` (`MomentumDumpingConfig`:
`hs_max` [N*m*s] trigger threshold, firing-resolution/cooldown knobs).
Mixing `"reaction_wheel"` and `"thruster"` actuators on one spacecraft
-- previously flatly rejected by task 2's own validation -- is now
allowed in EXACTLY this one case (`SpacecraftConfig.validate()` requires
`momentum_dumping` to be set whenever both kinds are present, and still
rejects the mix otherwise, since mixing them for primary control would
need a control-allocation module this app doesn't build).

**A real, non-obvious Basilisk requirement found by direct
experimentation, not just reading the example's comment**: tried running
`thrMomentumManagement` both with and against a real Basilisk build
(`/tmp/bsk_venv4`) and found that calling its `Reset()` only at t=0 (all
`InitializeSimulation()` itself ever does) means desaturation NEVER
fires for the entire run -- no error, no warning, just silently nothing
-- because `rwSpeedsInMsg` has no real data yet at that exact moment.
Calling `Reset()` again after even ONE real dynamics tick fixes it
completely, and the exact amount of extra time barely matters (confirmed
both 1 s and 10 s delays work identically). `engine.service.SimulationService
.build()` now does this automatically -- primes one dynamics tick,
re-`Reset()`s every desaturation module, then continues to the
scenario's real configured duration via the same documented
"`ConfigureStopTime`/`ExecuteSimulation` resumes, never restarts"
pattern `run_live()` already relied on -- so no scenario author needs to
know this quirk exists.

Added a GUI "Momentum dumping (RW desaturation via thrusters)" group
(threshold + firing-resolution + cooldown fields) next to the spacecraft
editor's other optional propulsion configs.

**Verification**: like task 2, this feature's dynamics (no orbit
propagation needed, just attitude + reaction wheels + thrusters) don't
touch gravity or SPICE at all, so it was run for real against the real
Basilisk build -- confirmed, with the EXACT Reset-timing experiment
above, that a 4-wheel cluster starting pre-saturated (same real
configuration as `examples/scenarioMomentumDumping.py`) genuinely sheds
momentum (initial wheel-speed vector `[418.9, 209.4, 366.5, 0.0]` rad/s
down to `[335.7, 99.0, 296.1, -43.3]` rad/s over 300 s, 3 real
desaturation firings) when primed, and provably does nothing at all when
not. Two new `requires_basilisk` tests in `tests/test_momentum_dumping.py`
ACTUALLY PASS against that build (both the "it works when primed" case
and a pinned regression test for the "does nothing without priming"
case, so a future refactor that accidentally drops the priming step
fails loudly instead of silently). Plus 5 new schema-validation tests
and 3 new GUI round-trip tests, all passing.

### Comprehensive, runnable template scenarios for every new feature

**Real user request**, made explicit after task 2 landed: "for each one
[feature on the 19-item backlog], please create a comprehensive
template/example scenario that can be loaded and ran out of the box."
Added to `scripts/_generate_templates.py` (the existing templates
catalog's own generator -- schema dataclasses + `Scenario.validate()`,
never hand-written JSON, per that script's own docstring) and
regenerated the whole catalog (templates 01-09 picked up two new,
purely-additive fields with their defaults -- `enable_gravity_gradient:
false`, `momentum_dumping: null` -- confirmed via diff that nothing else
in any of them changed):

- **`10_gravity_gradient_torque.json`**: an uncontrolled, elongated
  -inertia spacecraft with `enable_gravity_gradient` set -- its own
  description explains why a spherically-symmetric inertia would make
  the effect disappear entirely, and suggests that exact experiment.
- **`11_thruster_attitude_control.json`**: the thruster counterpart to
  '06'/'07' -- the same `inertial3D` pointing problem, actuated by eight
  real ACS thrusters instead of reaction wheels, using the EXACT
  configuration already confirmed to work in
  `tests/test_thruster_control.py`.
- **`12_reaction_wheel_momentum_dumping.json`**: four pre-saturated
  reaction wheels plus an 8-thruster desaturation cluster, using the
  EXACT configuration already confirmed to work in
  `tests/test_momentum_dumping.py`.

Every new template got the same treatment every existing one already
has: a 200+ character `description` explaining the concept, what to
look at in the results, and what to try changing; a specific regression
test pinning its defining characteristic (`fsw_mode is None` + elongated
inertia for '10', thruster-only actuators for '11', the required
actuator mix for '12'); and a catalog row in both this directory's own
`README.md` and the top-level `README.md`. The GUI's Load Scenario tab
needed no code change at all to pick them up -- it already globs
`scenarios/templates/*.json` dynamically (`gui/load_scenario_widget.py`),
confirmed by rendering it headless and counting 12 listed templates.

**Verification status**: schema-validated and round-trip tested (same
generic parametrized tests every template goes through), and built from
actuator/sensor configurations already confirmed to run correctly
against real Basilisk in isolation (the exact `r_B`/`tHat_B`/`MaxThrust`/
`gsHat_B`/`Omega` values from the passing `test_thruster_control.py`/
`test_momentum_dumping.py` tests above) -- but NOT executed end-to-end
through `SimulationService` in this sandbox: every scenario-level run
needs SPICE kernels (`engine.service.SimulationService.build()` calls
`build_spice_interface()` unconditionally), and this sandbox's network
egress to fetch them is blocked (see task 1's entry above and
`engine/kernels.py`'s own docstring) -- the same pre-existing limitation
already true for all nine original templates, not something new to
these three. Full suite: 755 passed, 107 skipped.

### Magnetic torque rod actuator (task 4 of 19)

The last remaining schema-valid-but-unwired actuator kind. Unlike the
thruster-based desaturation in task 3, this uses a materially different
Basilisk strategy -- `mtbMomentumManagement` -- which continuously
biases each reaction wheel's speed toward a target using whatever
magnetic torque the real geomagnetic field (Basilisk's WMM model) can
produce at the spacecraft's current position, rather than waiting for a
threshold and firing a discrete burst. It sits BETWEEN `rwMotorTorque`
and the RW hardware: it reads the originally-commanded RW motor torque
and republishes a modified one, so `engine.fsw.build_mtb_desaturation`
re-subscribes the RW effector's command input to override
`build_rw_motor_torque`'s own direct subscription (safe: Basilisk
resolves message subscriptions at `InitializeSimulation()`, so the last
`subscribeTo()` call before that wins).

New `SpacecraftConfig.magnetic_momentum_management`
(`MagneticMomentumManagementConfig`: `wheel_speed_biases_rad_s` -- one
target speed per reaction-wheel actuator, in listed order -- and a
`c_gain` control gain), requiring BOTH `"reaction_wheel"` and
`"magnetic_torque_rod"` actuators, mirroring task 3's `momentum_dumping`
requirement structure. New `ActuatorConfig(kind="magnetic_torque_rod")`
params: `gtHat_B` (dipole-axis unit vector) and `max_dipole_a_m2`
(maximum commandable dipole). Unlike `"thruster"`, `"magnetic_torque_rod"`
has NO standalone attitude-control role in this app -- Basilisk ships no
ready-made B-dot-style detumble controller, so a `"magnetic_torque_rod"`
actuator without `magnetic_momentum_management` set is rejected early
with a specific message, rather than silently building a dead actuator.

**A real, independently-found UI bug, fixed opportunistically**: the
"magnetic_torque_rod" entry in `_UNIMPLEMENTED_ACTUATOR_KINDS` (which
used to show "not simulated yet") had to be removed now that it IS
simulated, so the sensor/actuator editor's hint text gained a new
`_CONDITIONAL_ACTUATOR_NOTES` mechanism -- a kind can be fully wired up
but still need an extra note ("needs magnetic_momentum_management set")
beyond its plain param list, which `_UNIMPLEMENTED_ACTUATOR_KINDS`'s
binary "simulated or not" flag couldn't express.

**Verification**: confirmed empirically, not assumed from the shipped
example's comment, that `mtbMomentumManagement` needs NO equivalent of
task 3's "prime one tick, re-Reset()" dance -- it's a continuous
proportional controller, not an event-triggered threshold system.
Running the exact production `engine.fsw` call sequence
(`build_reaction_wheels` + `build_mrp_feedback` + `build_rw_motor_torque`
+ `build_magnetic_field_wmm` + `build_mtb_desaturation`, exactly as
`engine.service` now calls them) against a real Basilisk build drove a
4-wheel cluster from rest to within 0.1-0.5 RPM of commanded targets
(800/600/400/200 RPM) over a 120-minute run, while the attitude
controller simultaneously converged to near-exact inertial pointing
(attitude error ~3e-21). A real test-harness pitfall caught and fixed
along the way: a bypass-SPICE verification needs `magneticFieldWMM` fed
a planet-orientation matrix, and a naive all-zero one (Python's default
for an unpopulated `SpicePlanetStateMsgPayload`) made wheel speeds
converge nowhere near their targets (150-370 RPM off) -- an IDENTITY
orientation matrix (correct for this inertial-only bypass setup) fixed
it completely; `engine.service.SimulationService` always supplies a
real, non-degenerate SPICE-sourced planet message in production, so
this was specific to the test harness, not a bug in the shipped code.
Two new `requires_basilisk` tests in `tests/test_mtb_desaturation.py`
ACTUALLY PASS against that build. Plus 9 new schema-validation tests
and 4 new GUI tests (including the "no longer shows not-simulated-yet,
now explains the real requirement" regression guard), all passing.

**Template**: `13_magnetic_torque_rod_momentum_management.json`, the
direct counterpart to '12' -- same reaction-wheel/attitude-control setup,
magnetic desaturation instead of thruster desaturation, so the two
templates' result plots can be compared side by side (smooth continuous
convergence vs. sharp discrete steps). Full suite: 774 passed, 109
skipped.

### Real sun-heading estimation from CSS hardware (task 5 of 19), and two unrelated crash bugs found along the way

The last sensing-side gap on the 19-item backlog: every `fsw_mode` so far
read `simpleNav`'s noise-free TRUTH sun direction even when a
`coarse_sun_sensor` sensor was configured -- the sensor was cosmetic.
New `engine.fsw.build_css_sun_estimation()` builds a dedicated 8-device
`CoarseSunSensor` cluster (same cube layout as
`examples/BskSim/models/BSK_Dynamics.py`'s own `SetCSSConstellation()`)
feeding Basilisk's `cssWlsEst` weighted-least-squares estimator, and new
`SpacecraftConfig.fsw_params['use_css_estimation']` (validated: requires
at least one `coarse_sun_sensor` sensor) routes that ESTIMATE into
`fsw_mode: sunSafePoint`'s `sunDirectionInMsg` instead of truth -- the
same `cssWlsEst -> sunSafePoint -> mrpFeedback -> reaction wheels` chain
as Basilisk's own `examples/BskSim/scenarios/scenario_AttEclipse.py`
reference. This dedicated CSS cluster is intentionally separate from the
user-visible per-sensor `coarse_sun_sensor` telemetry `attach_sensors()`
already builds, same reasoning as task 4's dedicated TAM: `cssWlsEst`
needs one aggregate `CSSArraySensorMsgPayload` across the whole cluster,
which only Basilisk's `CSSConstellation` container produces.

**A second, genuinely new Basilisk Python-binding lifetime hazard**,
found by careful bisection after a reproducible segfault with no error
message: `CSSConstellation.sensorList` does not take ownership of the
`CoarseSunSensor` Python objects assigned to it, only a reference -- a
function-local `css_devices` list, discarded once the builder function
returned, let Python's garbage collector destroy the underlying C++
objects, leaving a dangling reference that segfaulted Basilisk inside
`InitializeSimulation()`. Same category of bug as this app's own Vizard
wiring (`access_indicator_bridges`/`generic_storage_list`/
`generic_sensor_list` -- "the caller MUST keep ALL FOUR alive"), now the
SECOND time this exact pattern has been found in this codebase --
confirmed reproducibly both ways (segfaults when discarded, works when
kept alive) against a real Basilisk build. Fixed by returning
`css_devices` from `build_css_sun_estimation()` and having
`engine.service.SimulationService` retain it in a new
`self._css_estimation_devices` list for the run's lifetime, mirroring
the Vizard pattern exactly.

**A much bigger, previously-undiscovered finding, chased down while
debugging what first looked like a CSS-specific bug**: closing the loop
end-to-end (CSS estimate -> `sunSafePoint` -> `mrpFeedback` -> idealized
actuation) on a small-sat-scale spacecraft went numerically unstable --
`sigma_BN` reached NaN within seconds, regardless of initial attitude
error size, and regardless of whether the estimate or simpleNav's own
truth drove the loop (ruling out CSS estimation itself as the cause).
Root-caused by direct experimentation, not guesswork: `engine.fsw.
DEFAULT_MRP_GAINS` (`K=3.5`, `P=30.0`) is lifted directly from Basilisk's
own `examples/BskSim` reference (`BSK_Fsw.py`'s `mrpFeedbackRWs`), which
is tuned for THAT example's 900 kg*m^2 spacecraft (`BSK_Dynamics.py`'s
`I_sc`) running its FSW task at `fswRate=0.1`. Applied unscaled to a much
smaller spacecraft (this app's own schema default inertia is
10 kg*m^2) at a coarser `dynamics_task_rate_s`, the resulting discrete
-time control update is wildly over-aggressive for the body's actual
rotational inertia -- idealized (unsaturated) actuation then has nothing
stopping the commanded torque from growing without bound every tick
(confirmed: roughly 2x-29x growth per tick depending on the exact
rate/inertia combination, a textbook discrete-time instability, not a
Basilisk bug). Reaction-wheel actuation's own torque saturation bounds
the damage (no NaN) but still produces a persistent, non-decaying
~30-degree pointing oscillation rather than real convergence -- confirmed
on BOTH the CSS-estimate-driven and truth-driven versions identically,
again ruling out CSS estimation as the cause.

**Two real, independent fixes came out of this**, both general risks for
ANY attitude-controlled spacecraft left on schema/engine defaults, not
specific to this feature:

- Scaling `control_params` (`K`/`P`) by a spacecraft's own inertia
  relative to that 900 kg*m^2 reference (both x `I_new/900`) converges
  cleanly instead -- confirmed directly: this task's own CSS-driven
  closed loop went from a persistent ~30-degree oscillation to a final
  pointing error of 8.5e-7 degrees with scaled gains, everything else
  unchanged. Applied to this task's new template (below) AND retroactively
  to `07_attitude_pointing_with_adcs_hardware.json`'s existing
  `sunSafePoint` + bare-RW setup, which had this exact problem already
  shipped and never actually verified end-to-end.
- For IDEALIZED actuation specifically (no RW/thruster hardware, so no
  torque saturation to bound an over-aggressive control update), the fix
  is a fine enough `dynamics_task_rate_s` instead -- confirmed:
  `06_attitude_pointing_basic.json`'s existing `hillPoint` + idealized
  -actuation setup reliably reached NaN within ~15 task ticks at its
  previously-shipped 1.0s rate; 0.1s (matching the `BSK_Fsw.py` reference
  `fswRate` this gain pair is tuned against) runs the same scenario
  stably for its whole duration. `_osculating_elements()`'s own
  `SimulationServiceError` message in `engine/service.py` already named
  "`dynamics_task_rate_s` too coarse" as a known failure mode for
  exactly this reason -- this is the first time it was actually
  triggered and confirmed, not just anticipated.

**A third, unrelated crash bug found while building a safe reaction
-wheel configuration for this task's own verification**: `rwFactory.
create()` (Basilisk's `simIncludeRW.py`) calls `exit(1)` directly -- not
a raised exception, killing the whole missionStudio process, not just
one run -- when `rw_type="custom"` (this schema's own default) is given
without a positive `u_max`, or without enough information (`Js`, or
`Omega_max`+`maxMomentum` together) to derive the wheel's spin-axis
inertia, or with BOTH `Js` and the `Omega_max`+`maxMomentum` pair at
once (those build a custom wheel's inertia exactly one way, never both).
All three are now schema-validated `ActuatorConfig(kind="reaction_wheel")`
requirements, confirmed against `rwFactory.create()`'s actual source,
with a message that always suggests the fix (set the missing param, or
use a named `rw_type` like `"Honeywell_HR16"` with its own built-in
defaults). Two already-shipped, real places hit variants of this exact
crash and are fixed alongside the schema check: '07's own bare
`gsHat_B`-only reaction wheels (now `"Honeywell_HR16"` + `maxMomentum`),
and `engine.spacecraft_templates.py`'s/`gui.sensor_actuator_editor.py`'s
own "new reaction wheel" default params (which gave `Js` AND
`Omega_max`+`maxMomentum` together -- the mutually-exclusive case).

**Template**: `14_css_sun_heading_estimation.json` -- the same 8-CSS
cluster, `sunSafePoint`, and scaled `control_params` confirmed above,
with `use_css_estimation: true`. New result series
`{name}.sun_heading_body_estimated` (the CSS estimate, alongside the
existing `{name}.sun_heading_body` truth series) lets the two be
compared directly in the GUI's results plots. New
`fsw_params['use_css_estimation']` GUI support in the spacecraft
editor's `sunSafePoint` parameter spec list.

**Verification**: `tests/test_css_estimation.py` (2 new
`requires_basilisk` tests) confirms, against a real Basilisk build, that
the scaled-gain CSS-driven closed loop converges the commanded body axis
to within 1 degree of the true sun direction (no NaN), and that its
final accuracy matches the truth-driven version for this template's
well-conditioned sun-direction/CSS-geometry combination -- the CSS-WLS
estimate's accuracy remains purely geometry-dependent, same as the
already-documented finding from earlier exploration (an under-determined
2-of-8-illuminated case gives large errors, a well-conditioned 4-of-8
case is exact with zero sensor noise; real hardware has exactly this
coverage gap, it is not something to "fix"). Plus 6 new schema
-validation tests for the three new reaction-wheel requirements and the
`use_css_estimation` sensor requirement, and 1 new template regression
test. `InertialUKF` (a full star-tracker + RW UKF attitude filter) is
deliberately OUT of scope for this task -- no clean shipped Basilisk
example to verify it against safely was found; a future task should
revisit it on its own.

### Direct celestial-body pointing (task 6 of 19): closing an already-documented gap

Surveyed every module in `src/fswAlgorithms/attGuidance/` against what
`engine.fsw.build_guidance` already wires up (`inertial3D`, `hillPoint`,
`velocityPoint`, `sunSafePoint`, `locationPointing`) to find the next
real, verifiable guidance gap. The highest-value one turned out to be
one this project had already flagged and explicitly deferred:
`fsw_mode: "locationPointing"`'s `fsw_params["target_body"]` option
(point a body-fixed axis straight at a celestial body, as opposed to
`target_ground_station`'s ground-station targeting) was schema-valid
-- `Scenario.validate()` already enforced the xor between the two
-- but `engine.fsw.build_guidance` hard-raised `FswError` for it,
because `locationPointing.celBodyInMsg` needs an `EphemerisMsg`, and
this checkout only ever produced a SPICE-sourced `SpicePlanetStateMsg`,
never converted.

That conversion turned out to be a single, well-defined Basilisk
module -- `ephemerisConverter.EphemerisConverter` -- confirmed directly
against `examples/scenarioAsteroidArrival.py`'s own
`addSpiceInputMsg()`/`ephemOutMsgs[i]`/`celBodyInMsg.subscribeTo()`
usage (that example points THREE separate `locationPointing` instances
at Earth, an asteroid, and back at Earth again, via exactly this
converter). New `engine.fsw.build_ephemeris_converter()` wraps one
dedicated converter per targeted body (trading a few trivial
pass-through modules for never needing `ephemObject`'s own
call-order index bookkeeping across spacecraft/targets); new
`engine.service.SimulationService` state
(`self._planet_state_out_msgs: Dict[str, msg]`) generalizes the
existing sun-specific `self._sun_state_out_msg` to every SPICE-tracked
body (`gravity.central_body` plus every `gravity.third_body_perturbers`
entry), so `target_body` can name any of them. New schema validation:
`target_body` must actually be one of those names (a real SPICE
ephemeris), with a specific error otherwise.

**A real, independently-found GUI bug, fixed alongside this**: the
spacecraft editor's `locationPointing` FSW-param spec list had
`target_ground_station` hard-marked `required=True` with no
`target_body` entry at all -- editing a spacecraft to use `target_body`
alone would have been rejected by the dialog itself with a "missing
required param" error before ever reaching the (now-correct) schema
validation. Fixed by adding `target_body` as its own spec and teaching
`_fsw_missing_required_keys` the real xor (either key present satisfies
the requirement); a new `_FswParamSpec.fill_on_reset` flag (default
`True`, set `False` only for `target_body`) keeps the "Reset to
template" button from filling BOTH mutually-exclusive keys at once,
which would have otherwise immediately failed `Scenario.validate()`'s
own xor check.

**Verification**: `tests/test_location_pointing_target_body.py` (1 new
`requires_basilisk` test) confirms, against a real Basilisk build, that
`pHat_B` converges onto a stand-in target body's direction (93.9-degree
initial error down to under 1 degree) with NO NaN, using the SAME
`dynamics_task_rate_s=0.1`/`DEFAULT_MRP_GAINS`/idealized-actuation fix
already established for task 5's gain/inertia investigation -- confirmed
to hold for this mode too, not just `hillPoint`/`sunSafePoint`. Plus 2
new schema-validation tests (SPICE-tracking requirement, central-body
-as-target case) and all pre-existing `locationPointing` schema tests
updated for the now-real (not just structural) `target_body`
validation. GUI tests pass unchanged.

**Template**: `15_celestial_body_pointing.json` -- a spacecraft keeping
its +Z axis pointed at the Moon throughout its orbit, the direct
counterpart to '07'/'06's ground-relative and orbit-relative pointing
modes (here the commanded attitude keeps changing as the TARGET itself
moves, not just the spacecraft).

### Lambert transfer planning tool (task 7 of 19): a new Mission Sequence command, not an FSW mode

Unlike every prior item on the 19-item backlog (all attitude/sensor/
actuator features), "Lambert transfer planning" is an ORBIT-planning
tool -- Basilisk's own `lambertPlanner`/`lambertSolver`/
`lambertValidator` FSW module chain (confirmed against
`examples/scenarioLambertSolver.py`'s own usage) solves for the
impulsive delta-V that takes a spacecraft from a given state to a
target position after a given time of flight. The natural integration
point in this app isn't a new `fsw_mode` -- it's a new **Mission
Sequence command**, `lambert_transfer`, alongside the existing
`maneuver` command this project already has (`schema.command.Command`,
`engine.mission_engine.MissionEngine`): where `maneuver` takes an
explicit delta-V, `lambert_transfer` takes a TARGET POSITION and SOLVES
for the delta-V, then applies it the same way.

**A real test-harness pitfall worth documenting (not a module bug)**:
`lambertValidator`'s own convergence check (`failedDvSolutionConvergence`)
compares each tick's delta-V solution against the PREVIOUS tick's,
zero-initialized at `Reset()` -- confirmed directly in
`lambertValidator.cpp` -- so a SINGLE call always reads as
"unconverged" even for a perfectly good, deterministic solution; it
needs at least 2 ticks of IDENTICAL input to actually converge. This is
a real, deliberate noise-robustness feature of the module (meant for a
continuously-running real-time guidance loop sampling noisy navigation
each tick), not a bug -- `_run_lambert_transfer` runs a throwaway,
single-task, 2-tick mini `SimBaseClass` (fed a literal snapshot of the
live spacecraft's current truth state, not the real running sim) for
exactly this reason, then applies the resulting delta-V to the REAL
simulation's velocity state object, same mechanism `_run_maneuver`
already uses (`dynManager.getStateObject(...).setState(...)`).

**Verification, including catching my own test-harness bug**: the
first cross-check attempt (manually propagating the ORIGINAL t=0
orbital state forward by the post-burn velocity) showed a 20,382 km
miss -- which turned out to be my own mistake, not a Lambert-solver
bug: `lambertPlanner` internally propagates the given nav state forward
to the maneuver time itself and reports that propagated state as
`lambertProblemMsgPayload.r1_N` (confirmed directly in its own message
payload comment, "position vector at t0"). Re-deriving the cross-check
from `r1_N`/`lambertSolutionMsgPayload.v1_N` (the actual burn point and
post-burn velocity) instead of the raw initial state gave a miss
distance of 4 MICROmeters -- pure floating-point noise, confirming
Basilisk's own module is exactly correct and the earlier "miss" was a
verification-script bug, not a real one. `tests/test_lambert_transfer.py`
(2 new `requires_basilisk` tests) confirms this against the real
`_run_lambert_transfer` method itself: one applies a transfer and
RK4-propagates the result to confirm sub-meter arrival accuracy, the
other confirms an infeasible transfer (5-second time of flight with a
`min_orbit_radius_m` constraint) raises a clear `MissionEngineError`
naming which `lambertValidator` checks failed, rather than silently
doing nothing.

New `Command(kind="lambert_transfer")` params: `spacecraft`,
`target_position_m` (inertial, central-body-relative), `time_of_flight_s`
(from THIS command's own execution, not a separately-delayed burn --
the burn itself is always immediate, like `maneuver`), `num_revolutions`,
`max_distance_target_m`, `min_orbit_radius_m` (the last two map directly
to `lambertValidator`'s own constraint checks). New GUI support in
`gui/mission_sequence_editor.py` (a dedicated command-editor page,
following the exact same pattern `maneuver`'s page already uses). A
real, independently-found reference-tracking gap fixed alongside this:
`schema/references.py`'s spacecraft-rename/reference-scanning only knew
about `"maneuver"`/`"propagate"`/`"assignment"` command kinds -- without
adding `"lambert_transfer"` there too, renaming a spacecraft would have
silently left any `lambert_transfer` command pointing at the OLD name
(a real dangling reference), and reference validation wouldn't have
caught a `lambert_transfer` targeting a nonexistent spacecraft.

**Template**: `16_lambert_transfer.json` -- the exact configuration
verified above (same orbit, target, and time of flight as
`examples/scenarioLambertSolver.py`'s own scenario), wrapped in a
3-command Mission Sequence (report position, lambert_transfer, coast,
report position again) so the "before" and "after" snapshots in the
GUI's Mission Output tab show the transfer actually landing on
target_position_m.

### Real FuelTank state effector (task 8 of 19): a second, more physical propellant model alongside the existing one

A real codebase audit finding, not a feature request: this project
ALREADY had propellant bookkeeping (`engine.orbit_maintenance`'s
station-keeping/phasing/constant-thrust controllers), but it's a
hand-rolled Python estimate -- explicit-Euler rocket equation, fed back
into `hub.mHub` manually each tick -- and ONLY covers those three
long-duration maintenance burns. The attitude-control/desaturation
thrusters from task 2/3 of this backlog (`"thruster"` actuators via
`thrForceMapping`/`thrMomentumDumping`) have never tracked propellant at
all -- they fire with unlimited "free" fuel. New
`SpacecraftConfig.fuel_tank` (`FuelTankConfig`) closes that gap using
Basilisk's OWN `fuelTank` state effector (`FuelTankModelUniformBurn`),
confirmed against `examples/MultiSatBskSim/modelsMultiSat/
BSK_MultiSatDynamics.py`'s own `SetFuelTank()` -- `fuelTank.
addThrusterSet()` ties the tank directly to a `ThrusterDynamicEffector`,
so it reads the exact same mass-flow rate (`mDot = F / (steadyIsp *
g0)`, confirmed directly in `thrusterDynamicEffector.cpp`) the thruster
hardware already computes for its own force/torque physics, and
depletes `hub.mHub` by exactly that amount. This is a materially more
physical model than the hand-rolled one: a real state effector, not a
Python `UpdateState()` estimate, including the propellant's own
contribution to the hub's center of mass as it depletes
(`tank_position_b_m` -> `setR_TB_B`) -- something a scalar `hub.mHub`
adjustment cannot represent at all. The two propellant models are
unrelated and don't conflict: a spacecraft could in principle use both
(station-keeping's own bookkeeping AND a fuel tank on its ACS
thrusters), each tracking its own, different propellant budget.

New `ActuatorConfig(kind="thruster")` + `fuel_tank` requires at least
one `"thruster"` actuator present (checked by schema, with a specific
error otherwise -- a tank with nothing drawing from it would be
schema-valid in Basilisk itself but almost certainly not what was
intended). Wired into BOTH places this app builds a
`ThrusterDynamicEffector` from `"thruster"` actuators: the primary
-control path (`fsw_mode` + no reaction wheels) and `momentum_dumping`'s
separate desaturation-thruster path -- confirmed these are mutually
exclusive in practice (the existing reaction_wheel+thruster mixing rule
means a spacecraft reaches at most one of the two), so exactly one
`fuelTank` ever gets built per spacecraft regardless of which path fires.

**Verification**: `tests/test_fuel_tank.py` (2 new `requires_basilisk`
tests) confirms, against a real Basilisk build, that a continuously
-firing thruster depletes fuel at the exact rate the rocket equation
predicts (within 1%, over a long-enough run that a real, confirmed
1-task-tick startup transient -- the thruster doesn't start firing until
the tick after `InitializeSimulation()` -- becomes negligible rather
than needing to special-case it), and that a thruster that never fires
at all leaves fuel mass exactly unchanged. New GUI support (a checkable
"Fuel tank" group box in the spacecraft editor, mirroring
`momentum_dumping`'s own pattern) and a new `{name}.fuel_mass_remaining`
result series.

**Template**: `17_fuel_tank_depletion.json` -- '11's exact 8-thruster
attitude-control setup with a 0.5 kg fuel tank added. Confirmed directly
against a real Basilisk build: the attitude converges from its initial
tip within about 100-150 seconds, consuming ~0.185 kg of propellant
during that active correction burn, after which
`{sat-1}.fuel_mass_remaining` goes flat (thrusters stop firing once
converged) -- a clean, real before/during/after depletion curve, not a
hand-picked-to-look-plausible number.

## Full-codebase audit: a comprehensive review and fix pass across every subsystem

A direct request ("do a complete and comprehensive audit and review of
entire code and fix any problems you may encounter"), separate from and
interrupting the 19-item feature backlog above (resumed after this).
Five parallel read-only review passes, one per subsystem
(`schema/`, `engine/service.py`+`engine/fsw.py`, the remaining
`engine/` support modules, `gui/`, and tests+templates+docs), each
briefed on this project's own known bug patterns (Basilisk object
-lifetime hazards, factory `exit(1)` crash risks, task-priority/message
-ordering bugs, control-loop gain/rate instability, a feature wired up
in one place but not another) so the search was productive rather than
generic style nitpicking. Every finding below was independently
re-confirmed by reading the actual flagged source before being fixed --
nothing here was taken on a review pass's word alone -- and, where a
Basilisk build could verify the fix, against a real one (this sandbox
happened to have a working `pip install "bsk[all]"` virtualenv available
from the review pass's own verification work).

### The most severe finding: unscaled default MRP gains are still the out-of-the-box behavior for ANY new scenario

This project already found and fixed (task 5 of 19, above) that
`engine.fsw.DEFAULT_MRP_GAINS` (`K=3.5`, `P=30.0`) is lifted directly
from Basilisk's own `examples/BskSim` reference, tuned for a
900 kg*m^2 spacecraft at a 0.1s FSW rate -- applied unscaled to a much
smaller spacecraft, the resulting discrete-time control update is wildly
over-aggressive and reliably diverges to NaN within seconds. That fix
was applied BY HAND to specific templates (07/14's explicit scaled
`control_params`; 06/15's finer `dynamics_task_rate_s`) -- but never
built into `engine.fsw` itself. Concretely: this schema's own defaults
(`inertia_kg_m2` = 10 kg*m^2 diag, `control_params={}`,
`dynamics_task_rate_s` = 10.0s) are a MORE extreme combination than the
one already confirmed to diverge, so a brand-new spacecraft created in
the GUI with any `fsw_mode` and no actuators (or reaction wheels) and
left on every default reproduces the exact same documented crash, with
zero code-level protection.

**Fixed at the root, not per-template**: `engine.fsw.build_mrp_feedback`
now takes an `inertia_kg_m2` parameter and defaults `K`/`P` to
`_default_mrp_gains_for_inertia(inertia_kg_m2)` -- `DEFAULT_MRP_GAINS`
scaled by the spacecraft's own mean (trace/3) inertia relative to the
900 kg*m^2 reference -- whenever `control_params` doesn't explicitly
override them (an explicit `control_params={"K": ..., "P": ...}` still
wins unchanged, confirmed by `tests/test_location_pointing_target_body
.py`'s own deliberate unscaled-gains case, which continues to omit
`inertia_kg_m2` and so is untouched by this change). All three
`engine.service` call sites (reaction-wheel, thruster, and idealized
-actuation control paths) now pass `sc_config.inertia_kg_m2` through.
This is the exact same `K/P x I_new/900` scaling formula task 5 already
verified by hand for 07/14 (`0.0194`/`0.167` at `I=5` reproduces exactly) --
generalized to every spacecraft automatically rather than needing a
template author to discover and apply it manually.

**Verification, against a real Basilisk build**: direct experimentation
confirmed the UNSCALED reference gains at schema-default inertia (10
kg*m^2) reach NaN within 120 ticks at a 1.0s rate, matching the already
-documented failure mode exactly. The SAME setup with the new scaled
default converges cleanly -- and, more than just "no NaN", converges
cleanly even at the schema's own coarse 10.0s `dynamics_task_rate_s`
default (final attitude error on the order of 1e-9 degrees over a 1200s
run), closing both halves of the original finding (the gain/inertia
mismatch AND the rate-coarseness risk) with one change. Also confirmed
this doesn't regress the two already-shipped thruster-actuated templates
(11/17, `control_params={}`, previously running on unscaled gains) that
a separate review pass flagged as "only verified for ~7% of their own
run duration": re-run over each template's FULL `dynamics_task_rate_s`
=0.5s/864s duration with the new scaled gains, the 8-thruster Schmitt
-trigger chain still fires (61/1729 ticks) and attitude error still
converges (0.374 -> 0.0477), no NaN -- so this fix also closes that
separate, previously-unverified-duration finding as a side effect. New
`tests/test_default_mrp_gain_scaling.py` (3 `requires_basilisk` tests):
confirms the unscaled-gain divergence still reproduces (a sanity check
that the regression test is actually testing something real), confirms
every-schema-default now converges, and confirms an explicit
`control_params` override still reaches the old unscaled behavior
unchanged (by design -- a user who deliberately sets `K`/`P` is opting
out of the automatic scaling).

### `engine.orbit_maintenance`'s delta-V bookkeeping undercounts true mass when a `fuel_tank` coexists

A second, related finding: `StationKeepingController`/
`PhasingKeepingController`/`ConstantFrameThrustController`'s
acceleration/delta-V estimate (`thrustMag / currentMass`) read
`scObject.hub.mHub` for `currentMass` -- which is NOT the spacecraft's
true total mass whenever a `schema.scenario.FuelTankConfig` "fuel_tank"
state effector is ALSO configured on the same spacecraft (e.g. backing
an unrelated "thruster" actuator's attitude-control/momentum-dumping
propellant). Confirmed directly in Basilisk's `fuelTank.cpp`: that
effector tracks its own mass via `effProps.mEff`, which correctly
contributes to the spacecraft's REAL simulated dynamics (Basilisk's own
integrator sums every state effector's mass), but is NEVER added into
`hub.mHub`. So this controller's own acceleration estimate silently
undercounted the true mass, inflating the estimate and ending a burn
early (an achieved-delta-V undershoot) in the controller's OWN
bookkeeping -- while the actual simulated physics stayed correct
throughout, since it never depended on this controller's estimate.

**Fixed** by reading `scObject.scMassOutMsg.read().massSC` -- Basilisk's
own hub+state-effector mass aggregate -- for the acceleration/delta-V
estimate specifically, while the propellant-burn WRITE-BACK (the part
that depletes this controller's OWN tracked propellant) deliberately
keeps reading/writing `hub.mHub` alone: feeding the aggregate into that
write-back would double-count a coexisting fuel tank's mass (once in the
tank's own state, once baked into `hub.mHub`). Confirmed by direct
experimentation that `scMassOutMsg` is fresh and correctly aggregated
every tick regardless of this controller's `AddModelToTask` priority
relative to the spacecraft's (a `SysModel` probe at the controller's own
default priority read `massSC` = 120 = 100 kg hub + 20 kg tank correctly
at every tick, including t=0). New `tests/test_orbit_maintenance_true_mass
.py` (3 `requires_basilisk` tests, built on a real `StationKeepingController`
via `build_station_keeping` with a real `fuelTank.FuelTank()` alongside
it) confirms: the controller's `_cumulativeDv` now matches
`thrust / (hub_mass + tank_mass)` (smaller than, and no longer equal to,
the old buggy hub-only computation); is unchanged for the common
no-fuel-tank case; and that the `hub.mHub` write-back itself does NOT
double-count the tank's mass.

### Three completeness gaps: every other actuator-management feature got matching telemetry/Vizard wiring except two newer ones

- **`engine.vizard` had no live propellant gauge for a real `fuelTank`
  state effector.** `station_keeping_by_spacecraft`'s own hand-rolled
  propellant tracking already got a "Propellant" `GenericStorage` panel
  the moment it shipped, but `schema.scenario.FuelTankConfig` (task 8 of
  19, above) never got an equivalent -- a spacecraft using the newer,
  more physical fuel-tank feature had zero live propellant visibility in
  Vizard. Fixed: new `fuel_tank_by_spacecraft` parameter on
  `engine.vizard.enable_vizard`, wired to a distinctly-labeled "Fuel
  Tank" panel (deliberately different from station-keeping's own
  "Propellant" label -- the two track independent propellant pools and
  can coexist on one spacecraft). `engine.service` now retains the
  `fuelTank.FuelTank()` effector itself on `_SpacecraftHandle` (it
  previously only kept the recorder, not the effector object Vizard
  wiring needs) at both call sites that build one. New
  `tests/test_vizard_fuel_tank_panel.py` (3 `requires_basilisk` tests,
  calling `enable_vizard` directly against a bare `SimulationBaseClass`
  to sidestep this sandbox's SPICE-kernel network block, the same
  bypass pattern `tests/test_thruster_control.py` already uses).
- **`magnetic_momentum_management`'s commanded dipole was invisible to
  the results UI.** `engine.service` built
  `mtb_effector, _ = fsw.build_mtb_desaturation(...)`, discarding the
  second return value (`mtbMomentumManagement` itself) entirely -- so,
  unlike `rw_speeds`/`thruster_on_time`/`fuel_mass_remaining`, there was
  no `{name}.mtb_dipole_commanded` series at all. Fixed: the second
  return value is now kept, its `mtbCmdOutMsg` recorded, and a new
  `{name}.mtb_dipole_commanded` result series (one column per torque
  rod, `A*m^2`) added, with a matching `gui/results_widget.py` display
  spec. New `tests/test_mtb_dipole_result_series.py` confirms
  `mtbCmdOutMsg.mtbDipoleCmds` is real and nonzero over a running
  desaturation loop (not a placeholder that would silently plot as all
  -zero).
- **`load_scenario_widget.py`'s bundled-template loader swallowed every
  exception with zero logging** (`except Exception: continue`, no
  `_logger` at all) -- unlike every sibling `noqa: BLE001` catch
  elsewhere in the GUI (`kernel_status_widget.py`, `run_worker.py`),
  which all log the full traceback before reporting failure. A corrupted
  or future-incompatible bundled template would silently vanish from the
  "Load Scenario" list with no trace anywhere. Fixed: added a module
  logger and a `_logger.exception(...)` call naming the skipped path
  before the `continue`.

### GUI: a reachable dead-end, and three stale default values

- **`orbit_only` mode left three actuator-requiring group boxes
  checkable with no way to satisfy their requirements.** The
  Sensors/Actuators tab (where `reaction_wheel`/`thruster`/
  `magnetic_torque_rod` actuators are added) is already hidden in
  `orbit_only` mode, and `power_group` was already correctly disabled
  for the same reason -- but `momentum_dumping_group`/
  `magnetic_momentum_management_group`/`fuel_tank_group` were not: a
  user could check one, click OK, and hit `Scenario.validate()`'s
  actuator-requirement error with no way to get back into the dialog to
  un-check it (the Sensors/Actuators tab that would let them add the
  required actuator stays hidden). Fixed by applying the exact same
  `setChecked(False)`/`setVisible(False)` pattern `power_group` already
  used, to all three.
- **Three GUI spin-box defaults were hardcoded literals that could
  silently drift from the schema's own defaults**: `bus_idle_power_w`,
  `battery_capacity_wh`, `battery_initial_soc` (power) and
  `tx_antenna_gain_dbi` (RF link) used a bare numeric literal as their
  "nothing configured yet" fallback instead of referencing
  `PowerConfig`/`RFLinkConfig`'s own dataclass default -- meaning a
  spacecraft created via the GUI with that field left unset could
  physically differ from one created by hand-editing JSON with the same
  field omitted, despite both claiming to use "the default". Fixed by
  switching all four to the same `value=config.field if config else
  SchemaClass.field` pattern already used elsewhere in this file (e.g.
  `drag_coeff`).

### Four smaller schema/validation fixes

- **`momentum_dumping` and `magnetic_momentum_management` were never
  actually validated as mutually exclusive**, despite `engine.service`
  building them as two independent `if` blocks (not `elif`) that would
  both try to command the same reaction wheels if both were set --
  confirmed directly in `engine.service`'s source. Fixed with a new
  `Scenario.validate()` check and `tests/test_scenario_schema.py::
  test_momentum_dumping_and_magnetic_momentum_management_are_mutually_exclusive`.
- **No positivity validation on `drag_coeff`/`drag_area_m2`/
  `srp_coeff`/`srp_area_m2`.** These feed straight into Basilisk's
  drag/SRP effectors as a physical coefficient/projected area; neither
  effector rejects a non-positive value itself, so a `<= 0` entry
  (a plausible typo) would silently produce a reversed or zero-magnitude
  force instead of a clear error. Fixed with four new `_require` checks
  (validated unconditionally, not just when `enable_drag`/`enable_srp`
  is set, so toggling either on later can't resurface an
  already-invalid value unnoticed) and 8 new parametrized tests.
- **`validate_all()` could report the same mission-sequence problem
  twice.** `Scenario.validate()` itself validates mission-sequence
  commands/references too (raise-fast, stopping at the first bad one)
  -- so when every resource was already valid, `validate_all()`'s own
  `try`/`except` around `scenario.validate()` caught and appended that
  SAME first-bad-command/dangling-reference message a SECOND time, on
  top of the dedicated collecting loop below it that already reports
  every mission-sequence problem (including that same first one). Fixed
  by recognizing both error-message formats always start with
  `"mission_sequence["` and skipping the `scenario.validate()` exception
  in that case, leaving the dedicated loop as the sole source of
  mission-sequence errors. Two new regression tests in
  `tests/test_validation.py` confirm a bad first command/dangling
  reference is now reported exactly once.
- Stale `README.md` claims corrected to match the app's actual current
  state: "thirteen" -> "seventeen" template scenarios (two places, after
  tasks 6/7/8 of the 19-item backlog each added one since that count was
  last written), test counts updated to the currently-passing 827/116
  (verified by actually running `pytest tests/ -q`), and a stale "not
  yet wired up" parenthetical removed for celestial-body `locationPointing`
  targets/thrusters/magnetic torque rods, all three of which are now
  fully implemented.

### Findings investigated and deliberately NOT changed

Documented here rather than silently dropped, per this project's own
"never sweep a finding under the rug" standard:

- `_run_lambert_transfer` rebuilds a full throwaway mini-sim on every
  call with no caching -- a real perf/scale concern inside a `while`
  loop (up to 10,000 iterations supported), but not a correctness bug,
  and no existing scenario exercises it at a scale where it matters.
- `_run_lambert_transfer`'s `last_failures` dict comprehension could
  raise a bare `IndexError` instead of a clear `MissionEngineError` if
  the mini-sim recorded zero ticks -- unreachable given the fixed
  60s/2-tick mini-sim configuration, so left as a latent inconsistency
  rather than a real risk.
- `kernels.py:build_spice_interface`'s `kernel_dir = statuses[0].path
  .parent` assumes a non-empty `kernels` list -- a bare `IndexError` if
  ever called with an empty one; every actual call site always passes a
  non-empty, schema-validated list, so this is an edge-case-only latent
  risk, not a reachable bug.
- `references.py`'s spacecraft-reference scanning does not look inside
  `if`/`while` `condition` strings or `script_block.code` -- a
  spacecraft referenced ONLY from inside one of those (as opposed to a
  structured `params["spacecraft"]` field) could be renamed or deleted
  without `validate_all()`/the GUI's dangling-reference check catching
  it. Real, but would need a small expression-language decision (how
  much of an arbitrary Python-ish condition string to parse) that is out
  of scope for an audit pass to make unilaterally -- flagged for a
  future, deliberately-scoped task rather than guessed at here.
- `fsw_mode="velocityPoint"` has shipped since early in this project but
  has never been exercised by a template or a `requires_basilisk` test,
  and so never got its own verified gain/rate combination the way every
  other mode did. The new inertia-scaled default gains above (which
  apply to every mode uniformly, not per-mode) substantially reduce the
  risk this represented, but a dedicated template + test is still the
  right way to close this gap fully -- left for a future task rather
  than rushed here.

**Full verification**: `pytest tests/ -q` (no Basilisk) --
8 new passing tests (drag/SRP positivity) and 1 (momentum_dumping/
magnetic_momentum_management mutual exclusion) plus 2 (validate_all
double-report) = 11 new non-Basilisk tests, all passing, zero
regressions. Every new `requires_basilisk` test file above
(`test_default_mrp_gain_scaling.py`, `test_orbit_maintenance_true_mass.py`,
`test_vizard_fuel_tank_panel.py`, `test_mtb_dipole_result_series.py`)
run individually against a real Basilisk build, all passing. Pre
-existing `requires_basilisk` suites re-run to confirm no regressions
from the `build_mrp_feedback`/`orbit_maintenance`/`vizard.enable_vizard`
signature changes: `test_orbit_maintenance.py`, `test_mtb_desaturation.py`,
`test_momentum_dumping.py`, `test_thruster_control.py`,
`test_location_pointing_target_body.py`, `test_css_estimation.py`,
`test_fuel_tank.py` all pass unchanged; `test_vizard.py`'s and
`test_gravity_gradient.py`'s SimulationService-level tests fail in this
sandbox for the same PRE-EXISTING reason documented throughout this
project (the SPICE-kernel network block), confirmed unrelated to this
audit's changes by reproducing the identical failure on `test_vizard.py`
before any of this pass's edits were made.

## Template 18: LEO station-keeping, the direct counterpart to '03's GEO case

A real gap, found by a direct question: '03' demonstrates GEO station
-keeping (Sun/Moon third-body gravity + SRP as the drift driver, a wide
5 km deadband, occasional corrections), but nothing demonstrated the
other, arguably more common real-world case -- a LEO spacecraft actively
compensating CONTINUOUS atmospheric drag decay, which needs a materially
different control regime (tighter deadband, more frequent/smaller
burns). `StationKeepingConfig`/`engine.orbit_maintenance` were always
altitude-agnostic (nothing drag-specific needed adding), so this was a
missing template, not a missing feature.

**Finding the right parameters took real investigation, not guessing**:
Basilisk's `ExponentialAtmosphere` module's own `simSetPlanetEnvironment
.exponentialAtmosphere()` Earth preset (`baseDensity=1.217 kg/m^3`,
`scaleHeight=8500.0 m`) is a single exponential fit tuned near the
surface -- applied unmodified at LEO altitudes (300-450 km) it predicts
a density around 15 orders of magnitude too low (`exp(-400000/8500)`),
producing no meaningful orbital decay at all over weeks. Confirmed
directly: an initial sweep using the stock preset showed exactly zero
station-keeping burns over a 14-30 day run at 300-450 km, regardless of
drag area/mass/deadband. Re-parameterized for verification purposes only
(NOT shipped -- see below) with a realistic ~400 km reference density
(~2.8e-12 kg/m^3, moderate solar activity) and an altitude-appropriate
~60 km scale height, the SAME `engine.orbit_maintenance.
build_station_keeping` + a real `dragDynamicEffector` (built the exact
way `engine.service` wires one, bypassing SPICE the same way
`tests/test_mtb_desaturation.py` already does) produced 2-3 real reboost
burns over 14 days at 400 km with a 1 km deadband and a small (1.5 m^2 /
120 kg) satellite -- a believable, demonstrable multi-burn LEO profile,
confirmed directly against a real Basilisk build before committing to
these numbers.

**What's shipped vs. what's verification-only**: the template itself
uses the SAME `nrlmsise00` conservative-margin atmosphere model '04'/
'05'/'07'/'08' already use (not the reparameterized `ExponentialAtmosphere`
stand-in above, which was a verification tool only) -- consistent with
every other drag-enabled template in this project, and more physically
correct (real density varies with latitude/season/solar activity; a
single exponential fit never will). Like '05', this template's EXACT
decay rate under the real `nrlmsise00` model has not been re-verified
end-to-end in this sandbox (no route to CelesTrak or the NAIF SPICE
kernel host here) -- stated plainly in the template's own `description`,
matching this project's established honesty convention for this exact
situation, rather than silently shipping unverified numbers as if they
were confirmed.

**Template**: `18_leo_station_keeping.json` -- a single 120 kg satellite
at 400 km/51.6 deg, `enable_drag=True`/`enable_srp=False` (isolating
drag as the one dominant perturbation, the same "isolate the lesson"
approach '03' already uses for GEO's SRP/third-body case), `station_keeping`
with a 1 km deadband (vs. '03's 5 km) over the same 14-day window as
'03', for a direct propellant-budget comparison. New
`tests/test_scenario_templates.py::test_leo_station_keeping_template_is_drag_driven_not_srp_driven`
confirms the structural contrast against '03' (drag on/SRP off, a
genuinely-LEO target altitude, a tighter deadband than GEO's). Catalog
entry added to `missionstudio/scenarios/templates/README.md` (which also
had its own stale "Nine ready-to-run scenario files" intro corrected to
eighteen -- it was never updated as templates were added over time), and
every "seventeen"/template-count reference in the top-level `README.md`
updated to eighteen. Full non-Basilisk suite: 844 passed, 126 skipped,
zero regressions (up from 838/126 -- the new template's own 4 parametrized
schema tests + 1 dedicated structural test + its 1 new GUI round-trip
parametrization).

## A guided "Customize..." wizard over three templates' own key parameters

A direct request: let a user "recreate the desired scenario themselves
or even tweak some parameters a little bit" starting from a template,
without first learning the full `ScenarioEditorWidget` form (every field
on every spacecraft/sensor/actuator). The full editor already supported
"open a template, then edit anything, then Save As" -- what was missing
was a FASTER, more approachable path for the common case of wanting to
change a handful of obviously-interesting knobs (the ones each
template's own `description` already calls out under "Try changing:")
without hunting for them across several tabs.

Three explicit design choices, asked of and made by the user rather than
guessed: a TRUE multi-step `QWizard` (one page per decision, not a
single dense form); the wizard hands off an in-memory `Scenario` to the
existing Scenario Editor on Finish (reusing all of its validation/save
machinery, rather than writing a file directly); and a PILOT rollout on
three representative templates first (`'03'` GEO station-keeping --
simple orbit-only; `'18'` LEO station-keeping -- same controller shape
plus a field that touches two dataclass locations at once; `'07'`
attitude+hardware+power -- the most structurally complex single
-spacecraft template) rather than all eighteen at once, to validate the
spec format and the UX before a larger rollout.

New `gui/template_wizard.py`: a declarative `TemplateWizardSpec` (list of
`WizardPageSpec`, each a list of `WizardField` -- label, help text, a
`get(scenario)`/`set(scenario, value)` closure pair, and spin-box
range/decimals/step/suffix), one entry in a `_SPECS` registry per
template filename, and a generic `TemplateCustomizeWizard(QWizard)` that
builds one `QWizardPage` per page spec from whichever template's spec it
was given -- adding a fourth template later is just another registry
entry, no change to the wizard machinery itself. Each spec's fields were
chosen directly from that template's own already-published "Try
changing:" text (`scripts/_generate_templates.py`), not invented fresh:

* `'03'` (2 pages): station-keeping deadband/thrust/isp/propellant
  budget, then simulation duration.
* `'18'` (4 pages): target altitude (the one field that updates BOTH
  `station_keeping.target_altitude_km` and `orbit.semi_major_axis_km`
  together, since the latter is measured from the central body's center
  and the former from its surface -- a wrong value in only one would
  leave the Scenario internally inconsistent), drag area/coefficient,
  the same station-keeping controller knobs as '03', then duration.
* `'07'` (3 pages): reaction-wheel max momentum (applied identically to
  all three wheels, keeping their already-symmetric layout symmetric
  rather than letting the wizard silently create an asymmetric set),
  solar panel area / battery capacity, then duration.

**A real design subtlety, caught before it became a bug**: the wizard
must operate on a COPY of the template's `Scenario`, never the one
`LoadScenarioWidget` loaded from disk, or accepting the wizard would
mutate (and `MainWindow` could then accidentally save over) the original
bundled template file. `TemplateCustomizeWizard.__init__` makes that copy
via `Scenario.from_dict(base_scenario.to_dict())` -- the same round-trip
`tests/test_scenario_templates.py` already trusts -- and `MainWindow
._on_load_scenario_customized` additionally opens the result with
`current_path=None` (refactored out of the existing `open_path()` into a
shared `_open_scenario()` helper), so `on_save()` always routes through
`on_save_as()` for a customized scenario, exactly like File > New
already does, never silently overwriting anything. Confirmed directly:
editing every field across all three templates' wizards, finishing, and
re-loading the original template file afterward shows it completely
unchanged.

New `LoadScenarioWidget.scenario_customized` signal (parallel to the
existing `path_chosen`, but carrying a `Scenario` object instead of a
path, since there is no file yet) and a "Customize..." button next to
"Open Template", enabled only when `template_wizard.get_wizard_spec()`
returns non-`None` for the selected template -- disabled (not hidden,
matching how `open_template_button` already handles "no selection") for
every other template, which still only offers the existing "Open
Template" flow unchanged.

**Verification**: `tests/gui/test_template_wizard.py` (10 new tests)
confirms, for all three registered specs: pages/fields are pre-filled
with the template's own current values; finishing with no edits
reproduces the original scenario byte-for-byte (`to_dict()` equality);
edited values apply correctly and the ORIGINAL `Scenario` object (and
the bundled template file on disk) stay untouched; '18's altitude field
updates both dataclass locations correctly; '07's reaction-wheel field
applies to all three wheels identically. Plus new tests in
`tests/gui/test_load_scenario_widget.py` (button enable/disable per
-template, signal emission on accept/cancel/no-selection) and
`tests/gui/test_main_window.py` (the full hand-off: `_current_path`
stays `None`, unsaved-changes confirmation gates it the same as the
existing template-open path, an invalid customized scenario shows a
clear error instead of crashing). Full suite: 860 passed, 126 skipped,
zero regressions (up from 844/126).

## Two real user-screenshot bugs, found immediately after the wizard shipped

**SpacecraftEditorDialog opened absurdly small.** A real user screenshot
showed the dialog rendering tiny enough that even its own first tab's
"Name"/"Dry mass [kg]" rows were clipped behind scrollbars, with the
window title itself truncated to "Spa...". Root cause: unlike
`propagation_setup_dialog.py` (which already has its own documented fix
for a similar but much milder discrepancy), `SpacecraftEditorDialog` had
NO explicit `resize()` call anywhere -- and simply adding
`self.resize(self.sizeHint())` would not have been enough here either:
every tab is wrapped in its own `QScrollArea` (see `_scrollable()`'s own
docstring for why -- so one busy tab can't force every other tab that
tall), and a `QScrollArea`'s `sizeHint()` is a small, mostly-arbitrary
default, NOT the wrapped content's real size. Confirmed directly: this
dialog's own `sizeHint()` measured 530x416 while its "Orbit / mass" tab
content alone needed 572x789, and the widest tab ("Power / propulsion /
link budget") needed 715. Fixed with an explicit `self.resize(...)`
computed from the widest tab's own content width (so nothing clips
horizontally) and a fixed, generous height (700px -- deliberately NOT
tall enough to fit the busiest tab without scrolling, since that tab
alone wants ~1485px, far taller than most screens; scrolling the busiest
tab independently is `_scrollable()`'s whole intended design, not a
bug). New `tests/gui/test_spacecraft_editor.py::
test_dialog_opens_at_a_usable_size_not_just_a_reasonable_upper_bound` --
the existing `test_dialog_natural_size_stays_reasonable` only guarded
the UPPER bound (catching the dialog blowing back up past ~800px), which
is exactly why this lower-bound regression shipped unnoticed; this new
test closes that gap.

**The Customize wizard buttons were too easy to miss.** Direct user
feedback: "I don't see the wizards. where are they? I wanted something
like what you did for the generate walker constellation, but bespoke
for each template/example scenario." The shipped design (one generic
"Customize..." button next to "Open Template", enabled only once a
template was already selected in the list above) buried the feature
behind a plain, unlabeled secondary button whose behavior depended on
unrelated widget state -- unlike `gui.spacecraft_editor.
SpacecraftListWidget`'s own "Generate Walker constellation.../Generate
phasing formation..." buttons, which are standalone, self-describing,
always-enabled actions. Fixed by replacing the single context-dependent
button with one dedicated "Customize: <template name>..." button per
registered `template_wizard` spec, always visible (not gated on list
selection at all), vertically stacked rather than a row (matching
`SpacecraftListWidget`'s own documented reasoning for why a 5-button row
already didn't reliably fit this app's left pane). `LoadScenarioWidget
.scenario_customized` and the rest of the hand-off to `MainWindow`
(`_on_load_scenario_customized`, `_open_scenario`) are unchanged --
only how a wizard gets STARTED moved. `tests/gui/
test_load_scenario_widget.py` updated for the new per-template buttons
(including a new regression test confirming a Customize click works
regardless of the list's current selection, the exact failure mode of
the earlier design). Full suite: 861 passed, 126 skipped, zero
regressions.

## "Apparently the dialog windows open too small everywhere" -- an app-wide audit

Direct follow-up after the SpacecraftEditorDialog fix above: a second
real user screenshot showed `gui.template_wizard.TemplateCustomizeWizard`
(brand new this session) with the SAME class of bug -- intro text and
help labels cut off mid-sentence -- plus a blanket report that this
might not be isolated to just these two dialogs. Audited every
`QDialog`/`QWizard` subclass in `gui/` (11 total) rather than only
reacting to the two already reported.

**Root cause, confirmed for each one individually, not assumed**:
`propagation_setup_dialog.py` already had its own documented, measured
fix for this exact bug class (`self.resize(self.sizeHint())`, with a
comment noting Qt sized that window smaller than its own sizeHint() on
first `show()` on a real desktop -- 871x734 vs. 871x768). Of the 11
dialog/wizard classes, only 3 had picked up that same fix
(`PropagationSetupDialog`, the just-fixed `SpacecraftEditorDialog`, and
`SpacecraftTemplateDialog`'s own fixed `520x320`) -- the other 8 had NO
explicit sizing at all, silently relying on Qt's default first-show
behavior, exactly the behavior `propagation_setup_dialog.py` already
proved unreliable on a real desktop. Rendering all 11 through this
project's own offscreen Qt test backend did NOT reproduce the user's
screenshot (every dialog measured `size() == sizeHint()` there) --
confirming this is a genuine, platform-dependent Qt layout-convergence
gap that can only be caught by explicitly forcing the size, never by
trusting headless/offscreen rendering alone to rule a dialog safe.

**Fixed by applying the same explicit resize to every dialog that was
missing it**: `WalkerConstellationDialog`, `GroundStationEditorDialog`,
`_CommandEditorDialog` (mission sequence), `_DispersionEditorDialog`
(Monte Carlo), `PhasingFormationDialog`, `_ItemEditorDialog`
(sensor/actuator), and `VizardDialog` each now call
`self.resize(self.sizeHint())` at the end of `__init__`, identical to
`propagation_setup_dialog.py`'s own proven fix -- for
`PhasingFormationDialog` specifically, this closes a REAL, independently
-measured 56px shortfall (497x545 vs. its own 497x601 sizeHint()), not
just a defensive guess.

**`TemplateCustomizeWizard` needed a different fix, not just the same
one-liner**: confirmed directly that `QWizard.sizeHint()` does NOT
reflect its own pages' content at all -- it measured a flat 500x360
regardless of which of the three registered specs ('03'/'07'/'18') was
given, while the busiest actual page ("Station-keeping controller",
shared by '03' and '18') needs 367x326 just for its own fields, before
QWizard's own title/intro banner and Back/Next/Cancel row are added on
top. `self.resize(self.sizeHint())` alone would therefore have done
nothing here. Fixed by computing the explicit target size from the
widest/tallest `_WizardFieldPage` across the WHOLE wizard (not just
whichever page is shown first) plus fixed padding for QWizard's own
chrome -- confirmed by rendering every page of all three specs at the
new size and checking none of them clip. Sizing from every page (not
just the current one) also means paging through Back/Next never
triggers an awkward mid-flow resize.

**Verification**: one new `test_dialog_resizes_to_its_own_sizehint_on
_construction`-style regression test per fixed dialog (matching
`propagation_setup_dialog.py`'s own existing test for the same bug
class), plus a dedicated `test_wizard_is_sized_to_fit_its_own_busiest
_page_not_a_flat_default` for the wizard's different fix, parametrized
across all three registered specs. Full suite: 871 passed, 126 skipped,
zero regressions.

