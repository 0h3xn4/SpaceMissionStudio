# Template missions

Eighteen ready-to-run scenario files, each demonstrating one missionStudio
concept in isolation -- for learning the tool and the orbital-mechanics
concepts it simulates, and as starting points for your own missions
(copy one, edit it, save it under a new name).

Every file is a complete, independently valid `Scenario` (built through
`schema.scenario`'s own dataclasses and `Scenario.validate()`, not
hand-written JSON -- see `scripts/_generate_templates.py` in this
repository, the source of truth these were generated from) with an
extensive `description` field explaining what it teaches, what to look at
after running it, and what to try changing. Read that field (open the
`.json` file directly, or look at the Description box at the top of the
GUI's scenario form after opening one) before diving into the raw numbers.

## Opening a template

```bash
# GUI: File -> Open..., then browse to one of these files, or:
python3 -m missionstudio.gui.app

# CLI (needs a real Basilisk build):
missionstudio run missionstudio/scenarios/templates/01_two_body_circular_orbit.json --out-dir out

# Just check it's schema-valid, no Basilisk needed:
missionstudio validate missionstudio/scenarios/templates/01_two_body_circular_orbit.json
```

Once opened in the GUI, **Save As...** under a new name/location before
editing if you want to keep the original template intact for next time.

## Catalog

Roughly progressive order -- each one builds on ideas from the ones
before it, but none of them depend on running an earlier one first.

| # | File | Teaches |
|---|------|---------|
| 01 | `01_two_body_circular_orbit.json` | The basics: a single circular orbit, point-mass Earth, no perturbations, no attitude (`simulation_mode: orbit_only`). Kepler's third law. Deliberately kept perturbation-free (see '09' too) -- the clean baseline the others contrast against. |
| 02 | `02_elliptical_orbit_with_perturbations.json` | An eccentric (GTO-like) orbit with Earth oblateness (J2 and higher-order terms, via 10th-degree spherical harmonics) and Sun/Moon third-body gravity switched on -- nodal regression, apsidal rotation, why a fine `dynamics_task_rate_s` matters once `central_body_degree > 0`. Drag deliberately left off so the J2/third-body precession lesson stays visually clean. |
| 03 | `03_geo_station_keeping.json` | A GEO satellite actively correcting real perturbation-driven drift with a deadband thrust controller (`station_keeping`) -- propellant budgeting for a multi-week station-keeping campaign. 10th-degree gravity (Earth's own longitudinal/tesseral resonance is a real GEO drift driver); no drag (physically negligible at GEO altitude). |
| 04 | `04_walker_constellation.json` | A 6-satellite, 2-plane Walker delta constellation, generated programmatically via `engine.constellation.generate_walker_constellation()` -- the same code path the GUI's "Generate Walker constellation..." dialog and the `generate-constellation` CLI subcommand use. Full perturbation set (10th-degree gravity, Sun/Moon, drag, SRP) on every satellite -- 700 km is genuinely drag-relevant; drag uses a conservative, historical-percentile margin (needs network access to CelesTrak, or a local historical file, to actually run -- see the file's own `description`). |
| 05 | `05_formation_flying_phasing.json` | Two spacecraft, one holding a fixed in-track separation behind the other (`phasing_keeping`, always paired with its own `station_keeping` -- see that config's own docstring for why) -- a basic formation-flying/proximity-operations control model. Full perturbation set on both spacecraft identically, same conservative drag margin as '04' -- see the file's own `description` for the network-access caveat and a not-yet-re-verified-in-sandbox note. |
| 06 | `06_attitude_pointing_basic.json` | Attitude pointing as a pure concept: `fsw_mode: hillPoint` (nadir pointing) with no sensors/actuators configured, so control torque is applied through an idealized effector rather than modeled hardware. Watch the attitude error converge. Gravity harmonics/third-body added for realism; drag/SRP deliberately left off -- '06' stays the simple version, '07' is the realistic one. `dynamics_task_rate_s` is deliberately 0.1 (not the schema default of 10, nor this template's own earlier 1.0) -- confirmed directly against a real Basilisk build that the earlier, coarser rate drove the idealized-actuation control loop numerically unstable (`sigma_BN` reached NaN) with this template's inertia; see HISTORY.md. |
| 07 | `07_attitude_pointing_with_adcs_hardware.json` | The same pointing problem as '06', but with a realistic hardware suite: star tracker, IMU, coarse sun sensor, three reaction wheels, and a solar-array/battery power budget -- what a real small-sat `SpacecraftConfig` actually looks like. Full perturbation set (drag/SRP included) to match its own "realistic counterpart" role, same conservative drag margin as '04'/'05'. |
| 08 | `08_mission_sequence_orbit_raise.json` | The Mission Sequence layer: a time-ordered command list (coast, snapshot, impulsive prograde burn, coast, snapshot) instead of one flat propagate-to-duration run -- edit it as a tree in the GUI's "Mission sequence" panel. The building block for a full two-burn Hohmann transfer (see the file's own description for how to extend it into one). Full perturbation set at 400 km (drag/SRP included, same conservative margin as '04'/'05'/'07') -- doesn't undermine this template's own lesson, unlike '01'/'09'. |
| 09 | `09_monte_carlo_dispersion_analysis.json` | Uncertainty quantification: the same orbit as '01', run as a 20-case Monte Carlo batch with `dry_mass_kg` independently redrawn per run from a normal distribution. Deliberately kept perturbation-free, same as '01' -- the file's own `description` explains why (mass doesn't affect pure two-body trajectories at all; only drag/SRP/maneuvers would show mass sensitivity). |
| 10 | `10_gravity_gradient_torque.json` | An uncontrolled (`fsw_mode: null`), elongated-inertia spacecraft with `enable_gravity_gradient` set -- Basilisk's real `GravityGradientEffector`, a disturbance torque with no GUI/schema path to model at all until this feature. With zero initial body rate, attitude normally stays frozen for the whole run; here it visibly drifts instead, purely from gravity acting across the spacecraft's own non-uniform mass distribution. |
| 11 | `11_thruster_attitude_control.json` | The thruster counterpart to '06'/'07': the same `inertial3D` pointing problem, but actuated by eight real ACS thrusters (`thrForceMapping` -> `thrFiringSchmitt` -> `thrusterDynamicEffector`) instead of reaction wheels or an idealized effector -- real hardware, real on-times, real Vizard thruster plumes. |
| 12 | `12_reaction_wheel_momentum_dumping.json` | Four reaction wheels under normal attitude control, started already heavily spun up -- `MomentumDumpingConfig` fires a separate 8-thruster desaturation cluster (`thrMomentumManagement` -> `thrForceMapping` -> `thrMomentumDumping`) to bleed the excess momentum off while the wheels stay in control the whole time. Watch `{sat-1}.rw_speeds` drop in discrete steps as each desaturation burn fires. |
| 13 | `13_magnetic_torque_rod_momentum_management.json` | The alternative to '12': four magnetic torque rods continuously bias the same four reaction wheels toward target speeds using the real geomagnetic field (`MagneticMomentumManagementConfig` -> `mtbMomentumManagement`), rather than firing discrete thruster bursts. Watch `{sat-1}.rw_speeds` climb smoothly from zero toward 800/600/400/200 RPM instead of '12''s sharp steps -- same problem, a structurally different real Basilisk solution. |
| 14 | `14_css_sun_heading_estimation.json` | Real sun-direction ESTIMATION, not truth: eight `coarse_sun_sensor` devices feed a dedicated `cssWlsEst` weighted-least-squares estimator, and `fsw_params['use_css_estimation']` routes that ESTIMATE (rather than `simpleNav`'s noise-free truth) into `fsw_mode: sunSafePoint` -- the same architecture as Basilisk's own `examples/BskSim/scenarios/scenario_AttEclipse.py` reference. `control_params` is deliberately scaled down from `engine.fsw.DEFAULT_MRP_GAINS` for this template's small-sat inertia -- see HISTORY.md for why an unscaled default never actually converges here. Watch `{sat-1}.sun_heading_body_estimated` settle onto the real sun direction as the estimate itself stabilizes. |
| 15 | `15_celestial_body_pointing.json` | `fsw_mode: locationPointing`'s OTHER target option: `fsw_params['target_body']` points a body-fixed axis straight at a celestial body (here, the Moon) instead of a ground station, built via `engine.fsw.build_ephemeris_converter` (`SpicePlanetStateMsg` -> `EphemerisMsg` -> `locationPointing.celBodyInMsg`), the same converter + guidance pairing Basilisk's own `examples/scenarioAsteroidArrival.py` uses. `target_body` must name `gravity.central_body` or a `gravity.third_body_perturbers` entry. Unlike '06'/'07's fixed-relative-to-orbit targets, the commanded attitude here keeps changing as the target body moves along its own orbit. |
| 16 | `16_lambert_transfer.json` | A new Mission Sequence command kind, the counterpart to '08's `maneuver`: `lambert_transfer` solves for WHATEVER delta-V takes the spacecraft from its current state to a target position after a given time of flight (rather than you specifying the delta-V directly), via Basilisk's own `lambertPlanner` -> `lambertSolver` -> `lambertValidator` chain (`engine.mission_engine.MissionEngine._run_lambert_transfer`), then applies it immediately. This exact configuration was confirmed directly against a real Basilisk build to land within sub-millimeter precision of `target_position_m` once propagated forward by `time_of_flight_s`. |
| 17 | `17_fuel_tank_depletion.json` | The exact '11' thruster-attitude-control setup, with a real `FuelTankConfig` added: Basilisk's own `fuelTank` state effector (`engine.fsw.build_fuel_tank`) now tracks real propellant depletion as the thrusters fire, reading the same mass-flow rate each thruster already computes for its own physics -- unlike this app's older hand-rolled station-keeping/phasing/constant-thrust propellant bookkeeping, this is Basilisk's own effector doing the real physics. Confirmed directly against a real Basilisk build: ~0.185 kg of the 0.5 kg starting load is consumed during the attitude-convergence burn, then `{sat-1}.fuel_mass_remaining` goes flat once the thrusters stop firing. |
| 18 | `18_leo_station_keeping.json` | The direct LEO counterpart to '03': a 400 km satellite correcting atmospheric-drag-driven altitude decay with the same `station_keeping` deadband controller, instead of '03's GEO-scale Sun/Moon/SRP drift. A tight 1 km deadband (vs. '03's 5 km) and continuous drag mean noticeably more frequent, smaller corrections than GEO's occasional ones -- the contrast is the lesson. `enable_srp` deliberately off, same "isolate the one dominant perturbation" approach as '03'. Same conservative drag margin as '04'/'05'/'07'/'08'; like '05', its exact nrlmsise00 decay rate has not been re-verified in this sandbox (no CelesTrak/SPICE route here) -- the station_keeping/drag parameters were instead tuned against a bypass-SPICE build with a realistically-reparameterized atmosphere model (2-3 real reboost burns over 14 days). |

## Using one as a starting point for your own mission

These are deliberately minimal and self-contained -- no ground stations,
no RF links, no Monte Carlo batches layered on top of an attitude
scenario, etc. -- so each idea is easy to see in isolation. A real mission
scenario will usually combine several of these concepts (e.g. a
comms-relay constellation might start from '04' and add '07''s ADCS
hardware plus a ground station and RF link to each satellite, matching
what `gui/ground_station_editor.py`/`RFLinkConfig` add). Copying the
closest template and layering in the next concept from this list is
generally easier than starting from a blank scenario.
