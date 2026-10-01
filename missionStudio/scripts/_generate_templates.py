#
#  ISC License
#
#  Copyright (c) 2026, Autonomous Vehicle Systems Lab, University of Colorado at Boulder
#
#  Permission to use, copy, modify, and/or distribute this software for any
#  purpose with or without fee is hereby granted, provided that the above
#  copyright notice and this permission notice appear in all copies.
#
#  THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
#  WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
#  MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
#  ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
#  WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
#  ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
#  OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
#

"""One-off generator for missionstudio/scenarios/templates/*.json -- run
directly (``python3 scripts/_generate_templates.py``) whenever a template
needs regenerating after a schema change. Not part of the installed
package and not imported by anything else; building the templates through
``schema.scenario`` dataclasses + ``Scenario.validate()`` (rather than
hand-writing JSON) is what guarantees they're actually schema-valid --
this script is the source of truth for that construction logic, kept
around instead of thrown away so future schema/field changes have a clear
place to regenerate from.
"""

from __future__ import annotations

import math
from pathlib import Path

from missionstudio.engine.constellation import WalkerConstellationRequest, generate_walker_constellation
from missionstudio.schema.scenario import (
    DispersionConfig,
    FuelTankConfig,
    GravityConfig,
    GroundStationConfig,
    MagneticMomentumManagementConfig,
    MomentumDumpingConfig,
    MonteCarloConfig,
    OrbitIC,
    PhasingKeepingConfig,
    PowerConfig,
    Scenario,
    SensorConfig,
    ActuatorConfig,
    SimSettings,
    SpacecraftConfig,
    SpaceWeatherConfig,
    StationKeepingConfig,
)

OUT_DIR = Path(__file__).resolve().parent.parent / "missionstudio" / "scenarios" / "templates"

_INERTIA_SMALL = [5.0, 0.0, 0.0, 0.0, 5.0, 0.0, 0.0, 0.0, 5.0]
_INERTIA_MEDIUM = [12.5, 0.0, 0.0, 0.0, 12.5, 0.0, 0.0, 0.0, 7.5]
_RPM_TO_RAD_S = math.pi / 30.0

# Skewed-pyramid 4-wheel layout, beta=52deg -- the exact spin axes
# examples/scenarioMtbMomentumManagement.py uses, computed here (not
# copied as decimals) so the values stay traceably derived from that
# same beta angle.
_MTB_DEMO_BETA_RAD = 52.0 * math.pi / 180.0
_MTB_DEMO_RW_AXES = [
    [0.0, math.cos(_MTB_DEMO_BETA_RAD), math.sin(_MTB_DEMO_BETA_RAD)],
    [0.0, math.sin(_MTB_DEMO_BETA_RAD), -math.cos(_MTB_DEMO_BETA_RAD)],
    [math.cos(_MTB_DEMO_BETA_RAD), -math.sin(_MTB_DEMO_BETA_RAD), 0.0],
    [-math.cos(_MTB_DEMO_BETA_RAD), -math.sin(_MTB_DEMO_BETA_RAD), 0.0],
]

def _conservative_drag_margin() -> SpaceWeatherConfig:
    """A conservative, sustained-worst-case atmospheric-drag margin -- a
    fresh instance per call (like ``list(_INERTIA_SMALL)`` above, not a
    single shared object, since ``SpaceWeatherConfig`` is mutable) for
    every template where drag is physically relevant (a LEO altitude) and
    doesn't undermine that template's own stated lesson (see each
    ``build_*()`` function's own comment for why some are, or aren't,
    drag-enabled at all). Real user request; see engine/spaceweather.py's
    own docstring, "Conservative ('worst-case') drag margin", for exactly
    what this computes (derived from real historical CelesTrak data,
    never a fabricated constant). Needs network access to CelesTrak (or a
    local historical space-weather file set via
    ``space_weather.local_file_path``) to actually resolve when the
    scenario is RUN -- schema validation/``save()`` itself never touches
    the network.
    """
    return SpaceWeatherConfig(
        source="celestrak", atmosphere_model="nrlmsise00", activity_level="conservative", activity_percentile=95.0,
    )


def _save(scenario: Scenario, filename: str) -> None:
    scenario.validate()  # fail loudly here, not for whoever opens the file later
    path = OUT_DIR / filename
    scenario.save(path)
    print(f"wrote {path}")


def build_01_two_body_circular_orbit() -> Scenario:
    return Scenario(
        name="01 - Two-body circular orbit",
        description=(
            "The simplest possible orbit: a single spacecraft in a circular low-Earth orbit around a "
            "point-mass Earth (no J2, no drag, no third-body gravity, no attitude dynamics -- "
            "simulation_mode is 'orbit_only'). This is the orbital-mechanics equivalent of a 'hello "
            "world' -- a clean two-body Keplerian orbit with nothing else going on.\n\n"
            "What to look at: plot 'sat-1.position_N' after running -- it traces a perfect circle in "
            "the orbit plane. The orbital period should match Kepler's third law, "
            "T = 2*pi*sqrt(a^3/mu), for a = 6778 km and Earth's mu (~398600.4418 km^3/s^2): about "
            "5554 s (~92.6 minutes), so a 1-day run completes about 15.5 orbits.\n\n"
            "Try changing: the semi_major_axis_km (higher = slower, longer period), the "
            "inclination_deg (watch the ground track in Vizard change), or the eccentricity (still "
            "0 here -- see '02 - Elliptical orbit with perturbations' for a non-circular example)."
        ),
        epoch_utc="2030-01-01T00:00:00",
        simulation_mode="orbit_only",
        gravity=GravityConfig(central_body="earth", central_body_degree=0),
        sim_settings=SimSettings(duration_days=1.0, dynamics_task_rate_s=30.0, integrator="rkf78"),
        spacecraft=[
            SpacecraftConfig(
                name="sat-1",
                orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6778.0, eccentricity=0.0,
                               inclination_deg=51.6, raan_deg=0.0, arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
                dry_mass_kg=500.0,
            ),
        ],
    )


def build_02_elliptical_orbit_with_perturbations() -> Scenario:
    return Scenario(
        name="02 - Elliptical orbit with perturbations",
        description=(
            "A geostationary transfer orbit (GTO)-like eccentric orbit, with Earth's oblateness (J2 "
            "and higher-order terms, via 10th-degree spherical harmonics) and third-body gravity from "
            "the Sun and Moon all switched on. Drag is deliberately NOT enabled here (unlike other "
            "templates updated for full perturbations) -- this one's whole point is isolating J2 + "
            "third-body precession cleanly (see 'What to look at' below); a third perturbation source "
            "would muddy that specific visual lesson. dynamics_task_rate_s is deliberately fine (1.0 s) "
            "here: coarser rates "
            "introduce real truncation error into the spherical-harmonics gravity term itself (see "
            "this project's own HISTORY.md, 'What Phase 6 (Mission Sequence architecture) adds', for the "
            "measured effect of this on a real Basilisk run) -- always use a fine rate together with "
            "central_body_degree > 0, not just for point-mass orbits.\n\n"
            "What to look at: plot 'sat-1.position_N' and watch the orbit visibly precess over the "
            "3-day run -- J2 causes the right ascension of the ascending node (RAAN) to regress and "
            "the argument of periapsis to rotate, effects a pure two-body orbit ('01') never shows. "
            "Compare 'sat-1.velocity_N' magnitude at periapsis vs. apoapsis to see orbital speed vary "
            "with a large eccentricity (0.7) -- much faster near Earth, much slower far away.\n\n"
            "Try changing: central_body_degree back to 0 to see the perturbation-free case for "
            "comparison, or third_body_perturbers to just [\"moon\"] or [\"sun\"] to isolate each "
            "effect."
        ),
        epoch_utc="2030-01-01T00:00:00",
        simulation_mode="orbit_only",
        gravity=GravityConfig(central_body="earth", central_body_degree=10, third_body_perturbers=["sun", "moon"]),
        sim_settings=SimSettings(duration_days=3.0, dynamics_task_rate_s=1.0, integrator="rkf78"),
        spacecraft=[
            SpacecraftConfig(
                name="sat-1",
                orbit=OrbitIC(type="classical_elements", semi_major_axis_km=24396.0, eccentricity=0.7,
                               inclination_deg=28.5, raan_deg=0.0, arg_periapsis_deg=180.0, true_anomaly_deg=0.0),
                dry_mass_kg=1000.0,
            ),
        ],
    )


def build_03_geo_station_keeping() -> Scenario:
    return Scenario(
        name="03 - GEO station-keeping",
        description=(
            "A geostationary communications satellite that actively maintains its altitude against "
            "real perturbations (Sun/Moon third-body gravity and solar radiation pressure -- the "
            "actual drivers of GEO longitude/altitude drift in practice) using a simple deadband "
            "thrust controller: it fires station_keeping's thruster whenever the propagated altitude "
            "drifts more than deadband_km from target_altitude_km, burning propellant tracked in "
            "propellant_kg.\n\n"
            "What to look at: run the CLI ('missionstudio run ... --out-dir out') and check "
            "command_summary/results for the propellant used over the 14-day run (see this project's "
            "README, 'Running the CLI', for the station-keeping summary output) -- a real budget "
            "question a mission designer has to answer: how much propellant does a decade of GEO "
            "station-keeping cost?\n\n"
            "Try changing: deadband_km (tighter = more frequent, smaller burns), thrust_n/isp_s (a "
            "more efficient thruster uses less propellant per correction), or removing "
            "third_body_perturbers/enable_srp to see how much slower the drift becomes without them "
            "(and how rarely the controller then needs to fire).\n\n"
            "central_body_degree is 10 (not 0) despite GEO altitude: geosynchronous longitude drift "
            "is driven in real life partly by Earth's own longitudinal (tesseral) gravity anomalies, "
            "not just Sun/Moon/SRP -- a real GEO perturbation this spherical-harmonics degree can "
            "represent. Atmospheric drag is deliberately NOT enabled -- physically negligible at "
            "42164 km (no meaningful atmosphere there); enabling it would misrepresent the physics, "
            "not add realism."
        ),
        epoch_utc="2030-01-01T00:00:00",
        simulation_mode="orbit_only",
        gravity=GravityConfig(central_body="earth", central_body_degree=10, third_body_perturbers=["sun", "moon"]),
        sim_settings=SimSettings(duration_days=14.0, dynamics_task_rate_s=30.0, integrator="rkf78"),
        spacecraft=[
            SpacecraftConfig(
                name="geo-sat-1",
                orbit=OrbitIC(type="classical_elements", semi_major_axis_km=42164.0, eccentricity=0.0,
                               inclination_deg=0.0, raan_deg=0.0, arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
                dry_mass_kg=1200.0,
                enable_srp=True, srp_coeff=1.3, srp_area_m2=15.0,
                station_keeping=StationKeepingConfig(
                    target_altitude_km=35786.0, deadband_km=5.0, thrust_n=0.5, isp_s=1600.0,
                    propellant_kg=50.0,
                ),
            ),
        ],
    )


def build_04_walker_constellation() -> Scenario:
    # 700 km is genuinely drag-relevant LEO altitude -- drag/SRP enabled
    # on the shared template so generate_walker_constellation() copies it
    # onto every satellite (see this function's own description update
    # below for the reasoning and the conservative-margin caveat).
    template = SpacecraftConfig(
        name="placeholder",  # replaced per-satellite by generate_walker_constellation()
        orbit=OrbitIC(type="classical_elements", semi_major_axis_km=1.0, eccentricity=0.0,
                       inclination_deg=0.0, raan_deg=0.0, arg_periapsis_deg=0.0, mean_anomaly_deg=0.0,
                       anomaly_type="mean"),
        dry_mass_kg=180.0,
        enable_drag=True, drag_coeff=2.2, drag_area_m2=1.0,
        enable_srp=True, srp_coeff=1.3, srp_area_m2=1.0,
    )
    request = WalkerConstellationRequest(
        total_satellites=6, num_planes=2, phasing_factor=1, altitude_km=700.0, inclination_deg=53.0,
        pattern="delta", name_prefix="leo",
    )
    spacecraft = generate_walker_constellation(request, template)
    return Scenario(
        name="04 - Walker delta constellation",
        description=(
            "A small 6-satellite Walker delta constellation (2 orbital planes, 3 satellites per "
            "plane, phasing factor 1) at 700 km altitude / 53 deg inclination -- generated "
            "programmatically via engine.constellation.generate_walker_constellation() rather than "
            "hand-written, exactly how the GUI's 'Generate Walker constellation...' dialog "
            "(gui/constellation_dialog.py, off the spacecraft list's own button) and "
            "'missionstudio generate-constellation' CLI subcommand build one.\n\n"
            "What to look at: open this in the GUI and look at Vizard's ground track (or plot each "
            "satellite's 'position_N' series) -- the 2 planes are spread 180 deg apart in RAAN "
            "('delta' pattern; a 'star' pattern spreads them over 360 deg total instead), and "
            "satellites within a plane are evenly spaced by mean anomaly, offset between planes by "
            "the phasing factor. This is the standard way real LEO broadband/imaging constellations "
            "(the thing 'Starlink-shell-like' parameters like these are modeled after) achieve "
            "repeatable global coverage with a minimal satellite count.\n\n"
            "Try changing: total_satellites/num_planes (regenerate via the CLI/GUI, not by hand "
            "-editing this file's spacecraft list) to see how coverage geometry changes, or "
            "phasing_factor to change how planes interleave relative to each other.\n\n"
            "Updated to include 10th-degree spherical-harmonics gravity, Sun/Moon third-body gravity, "
            "atmospheric drag, and solar radiation pressure on every satellite -- a 700 km Walker "
            "constellation genuinely experiences all of these. Drag uses a CONSERVATIVE, "
            "95th-percentile sustained-worst-case F10.7/Ap margin computed from real historical "
            "CelesTrak data (see engine/spaceweather.py's own docstring) rather than day-to-day space "
            "weather -- running this template needs network access to CelesTrak (or a local historical "
            "space-weather file set via space_weather.local_file_path); set "
            "space_weather.activity_level back to 'nominal' to use ordinary resolved space weather "
            "instead."
        ),
        epoch_utc="2030-01-01T00:00:00",
        simulation_mode="orbit_only",
        gravity=GravityConfig(central_body="earth", central_body_degree=10, third_body_perturbers=["sun", "moon"]),
        sim_settings=SimSettings(duration_days=1.0, dynamics_task_rate_s=30.0, integrator="rkf78"),
        space_weather=_conservative_drag_margin(),
        spacecraft=spacecraft,
    )


def build_05_formation_flying_phasing() -> Scenario:
    return Scenario(
        name="05 - Formation flying (phasing control)",
        description=(
            "Two spacecraft in near-identical orbits, 'follower-1' actively holding a fixed in-track "
            "separation behind chief 'chief-1' using phasing_keeping -- a closed-loop controller that "
            "measures the along-track separation and fires small along-track burns to correct drift, "
            "on top of its OWN station_keeping (phasing_keeping always needs station_keeping "
            "configured on the same spacecraft -- see PhasingKeepingConfig's own docstring for why: "
            "phasing needs altitude held steady first, or a semi-major-axis mismatch would make "
            "along-track drift and true phasing error indistinguishable).\n\n"
            "What to look at: after running, compare 'follower-1.position_N' and 'chief-1.position_N' "
            "-- the along-track (velocity-direction) separation should stay near "
            "target_separation_km despite neither orbit being perfectly matched to start, a basic "
            "model of formation-flying/rendezvous-proximity-operations control (e.g. trailing "
            "satellite formations, or a servicer holding station behind a target). "
            "'missionstudio run' also prints a phasing delta-V breakdown in its station-keeping "
            "summary (see README, 'Running the CLI').\n\n"
            "Try changing: target_separation_km (a schedule -- see PhasingKeepingConfig; a single "
            "-element list holds one separation for the whole run, more elements step through a "
            "schedule), or chief-1's own orbit to start with a larger initial mismatch and watch "
            "follower-1 correct it.\n\n"
            "Updated to include 10th-degree spherical-harmonics gravity, Sun/Moon third-body gravity, "
            "atmospheric drag, and solar radiation pressure on both spacecraft (identically, so any "
            "chief/follower difference in behavior is real physics, not asymmetric configuration) -- a "
            "CONSERVATIVE, 95th-percentile sustained-worst-case drag margin from real historical "
            "CelesTrak data (see engine/spaceweather.py's own docstring), needing network access to "
            "CelesTrak or a local historical file to actually run. NOTE: this specific change has NOT "
            "been re-verified against a real multi-day Basilisk run the way this template's original "
            "dynamics were (see README's 'Verification status') -- this development sandbox has no "
            "route to the NAIF SPICE kernel host needed to run it at all; please report back if the "
            "phasing controller's propellant budget or behavior looks off under the added "
            "perturbations."
        ),
        epoch_utc="2030-01-01T00:00:00",
        simulation_mode="orbit_only",
        # third_body_perturbers=["sun", "moon"]: follower-1's station_keeping
        # (below, required by phasing_keeping) needs the real eclipse shadow
        # factor for its eclipse-gated reboost burn, which needs a sun
        # ephemeris -- see engine.service.SimulationService.build()'s own
        # SimulationServiceError if this is missing (caught on a real run:
        # this template originally had an empty third_body_perturbers list).
        # "moon" added alongside "sun" for full-perturbation realism (see
        # this function's own description update above).
        gravity=GravityConfig(central_body="earth", central_body_degree=10, third_body_perturbers=["sun", "moon"]),
        sim_settings=SimSettings(duration_days=7.0, dynamics_task_rate_s=30.0, integrator="rkf78"),
        space_weather=_conservative_drag_margin(),
        spacecraft=[
            SpacecraftConfig(
                name="chief-1",
                # eccentricity=0.001, not 0.0 -- both orbits used to be exactly
                # circular, which crashed on a real run: orbitalMotion.rv2elem()
                # (used by engine.orbit_maintenance.PhasingKeepingController to
                # measure each spacecraft's along-track phase) only trusts its
                # stable near-circular formula below e=1e-11, and this
                # template's own sun third-body perturbation and commanded
                # thrust are enough to push a nominally-circular orbit's real,
                # propagated eccentricity above that -- at which point rv2elem()
                # silently falls back to measuring phase from the eccentricity
                # VECTOR's direction, which is numerically meaningless (noise
                # -dominated) once eccentricity is that close to zero, and fed
                # a garbage phasing error into the controller. A small,
                # deliberate eccentricity (0.001, ~7 km of altitude variation --
                # well inside station_keeping's 2 km deadband once smoothed over
                # one orbital period, see StationKeepingController.UpdateState())
                # keeps rv2elem() safely on its normal, stable branch instead,
                # using Basilisk's own orbit-element math the way it's designed
                # to be used rather than routing around it.
                orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6928.0, eccentricity=0.001,
                               inclination_deg=45.0, raan_deg=0.0, arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
                dry_mass_kg=400.0,
                enable_drag=True, drag_coeff=2.2, drag_area_m2=1.0,
                enable_srp=True, srp_coeff=1.3, srp_area_m2=1.0,
            ),
            SpacecraftConfig(
                name="follower-1",
                orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6928.0, eccentricity=0.001,
                               inclination_deg=45.0, raan_deg=0.0, arg_periapsis_deg=0.0, true_anomaly_deg=-0.5),
                dry_mass_kg=400.0,
                enable_drag=True, drag_coeff=2.2, drag_area_m2=1.0,
                enable_srp=True, srp_coeff=1.3, srp_area_m2=1.0,
                station_keeping=StationKeepingConfig(
                    target_altitude_km=550.0, deadband_km=2.0, thrust_n=0.05, isp_s=1500.0, propellant_kg=5.0,
                ),
                phasing_keeping=PhasingKeepingConfig(
                    chief_spacecraft="chief-1", target_separation_km=[50.0],
                ),
            ),
        ],
    )


def build_06_attitude_pointing_basic() -> Scenario:
    return Scenario(
        name="06 - Basic attitude pointing (idealized actuation)",
        description=(
            "A spacecraft pointing its body frame to track the local vertical/local horizontal frame "
            "(fsw_mode 'hillPoint' -- nadir-pointing, the natural first attitude-control example: see "
            "engine/fsw.py's own docstring, copied from examples/scenarioAttitudeGuidance.py) with NO "
            "sensors or actuators configured -- with no 'reaction_wheel' actuators present, the "
            "control torque is applied directly to the hub via an idealized ExtForceTorque effector "
            "(see engine/fsw.py's build_idealized_actuation()), skipping real hardware modeling "
            "entirely so this example is only about the pointing CONCEPT. See '07' for the same idea "
            "with real ADCS hardware in the loop.\n\n"
            "The spacecraft starts tipped away from the target attitude (sigma_bn_init is non-zero) "
            "with a small initial body rate -- watch the attitude error converge to zero as the "
            "controller (mrpFeedback, closing the loop on simpleNav's truth attitude) drives it to "
            "track hillPoint's commanded frame.\n\n"
            "What to look at: this scenario's own attitude state isn't in the CSV export series by "
            "default; add a 'report' mission_sequence command (see '08') or inspect "
            "sat-1.omega_BN_B/attitude state directly via the schema/engine layer if you extend this "
            "-- or simplest, watch it converge visually in Vizard's live attitude indicator.\n\n"
            "Try changing: fsw_mode to 'velocityPoint' (tracks the velocity vector instead of nadir) "
            "or 'inertial3D' (points at a fixed inertial attitude, ignoring the orbit entirely) to "
            "compare pointing behaviors."
        ),
        epoch_utc="2030-01-01T00:00:00",
        simulation_mode="full_attitude",
        # Gravity harmonics/third-body added for realism (invisible to the
        # attitude-pointing lesson below); drag/SRP deliberately NOT
        # enabled -- this template's own role is to stay the SIMPLE
        # version ('07' is explicitly "the realistic counterpart").
        gravity=GravityConfig(central_body="earth", central_body_degree=10, third_body_perturbers=["sun", "moon"]),
        # dynamics_task_rate_s=0.1 (NOT the schema's own 10.0 default, and
        # NOT this template's previous 1.0): confirmed directly against a
        # real Basilisk build that idealized-actuation mrpFeedback control
        # (engine/fsw.py's DEFAULT_MRP_GAINS, K=3.5/P=30 -- lifted from
        # Basilisk's own examples/BskSim reference, which runs its FSW task
        # at fswRate=0.1s) goes numerically unstable -- sigma_BN reaches
        # NaN within ~15 task ticks -- at 1.0s with this template's inertia
        # (_INERTIA_MEDIUM), because mrpFeedback's commanded torque is a
        # zero-order hold applied for the WHOLE task period: a coarser
        # period needs a proportionally weaker P relative to inertia to stay
        # discrete-time stable (see _osculating_elements()'s own
        # SimulationServiceError message in engine/service.py, which already
        # names exactly this failure mode). 0.1s matches the reference
        # fswRate this K/P pair is tuned against and was confirmed stable
        # (no NaN) over this template's full duration. See HISTORY.md for
        # the full investigation -- this is a general risk for ANY
        # idealized-actuation spacecraft left on a coarse
        # dynamics_task_rate_s, not specific to this template.
        sim_settings=SimSettings(duration_days=0.05, dynamics_task_rate_s=0.1, integrator="rkf78"),
        spacecraft=[
            SpacecraftConfig(
                name="sat-1",
                orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6928.0, eccentricity=0.0,
                               inclination_deg=45.0, raan_deg=0.0, arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
                dry_mass_kg=300.0,
                inertia_kg_m2=list(_INERTIA_MEDIUM),
                sigma_bn_init=[0.1, 0.2, -0.15],
                omega_bn_b_init_rad_s=[0.001, -0.001, 0.0005],
                fsw_mode="hillPoint",
            ),
        ],
    )


def build_07_attitude_pointing_with_adcs_hardware() -> Scenario:
    return Scenario(
        name="07 - Attitude pointing with real ADCS hardware",
        description=(
            "The realistic counterpart to '06': the same pointing problem, but with an actual ADCS "
            "hardware suite modeled -- a star tracker and IMU for attitude/rate sensing, a coarse sun "
            "sensor, and three reaction wheels (orthogonal spin axes) providing the real control "
            "torque instead of an idealized effector, plus a solar array + battery power budget "
            "(power draw from the sensors/wheels isn't modeled per-component here, but this shows how "
            "a full spacecraft config -- attitude AND power -- fits together). fsw_mode 'sunSafePoint' "
            "is a safe-mode-style controller that points a body axis at the Sun using simpleNav's own "
            "Sun-direction output (see engine/fsw.py's docstring for why no separate sensor message "
            "is strictly required even though a coarse_sun_sensor is configured here for realism).\n\n"
            "What to look at: this is the shape a real small-sat's SpacecraftConfig looks like in "
            "practice -- compare it side-by-side with '06' to see exactly what real hardware adds "
            "(sensors/actuators/power blocks) on top of the bare pointing-mode concept.\n\n"
            "Try changing: the reaction wheels' Js/u_max/maxMomentum (see the GUI's sensor/actuator "
            "editor for the full per-kind parameter list and units), or swap fsw_mode to "
            "'locationPointing' with fsw_params={'target_ground_station': '<name>'} once a "
            "ground_stations entry exists in this scenario.\n\n"
            "Updated to include 10th-degree spherical-harmonics gravity, Sun/Moon third-body gravity, "
            "atmospheric drag, and solar radiation pressure -- consistent with this template's own "
            "role as the 'realistic counterpart' to '06'. Drag uses a CONSERVATIVE, 95th-percentile "
            "sustained-worst-case F10.7/Ap margin from real historical CelesTrak data (see "
            "engine/spaceweather.py's own docstring), needing network access to CelesTrak or a local "
            "historical file to actually run."
        ),
        epoch_utc="2030-01-01T00:00:00",
        simulation_mode="full_attitude",
        # third_body_perturbers=["sun", "moon"]: sat-1's PowerConfig (below)
        # needs the real eclipse shadow factor for its solar-panel power
        # generation, which needs a sun ephemeris -- same reasoning as '05'
        # -- and sunSafePoint's own sun-pointing already conceptually wants
        # a real sun to point at. See engine.service.SimulationService.
        # build()'s own SimulationServiceError if this is missing (caught
        # on a real run: this template originally had an empty
        # third_body_perturbers list). "moon" added alongside "sun" for
        # full-perturbation realism (see this function's own description
        # update above).
        gravity=GravityConfig(central_body="earth", central_body_degree=10, third_body_perturbers=["sun", "moon"]),
        sim_settings=SimSettings(duration_days=0.05, dynamics_task_rate_s=1.0, integrator="rkf78"),
        space_weather=_conservative_drag_margin(),
        spacecraft=[
            SpacecraftConfig(
                name="sat-1",
                orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6928.0, eccentricity=0.0,
                               inclination_deg=45.0, raan_deg=0.0, arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
                dry_mass_kg=50.0,
                enable_drag=True, drag_coeff=2.2, drag_area_m2=1.0,
                enable_srp=True, srp_coeff=1.3, srp_area_m2=1.0,
                inertia_kg_m2=list(_INERTIA_SMALL),
                sigma_bn_init=[0.1, 0.2, -0.15],
                omega_bn_b_init_rad_s=[0.001, -0.001, 0.0005],
                sensors=[
                    SensorConfig(kind="star_tracker", name="st-1", params={"noise_arcsec": 5.0}),
                    SensorConfig(kind="imu", name="imu-1", params={"gyro_noise_rad_s": 1e-5}),
                    SensorConfig(kind="coarse_sun_sensor", name="css-1", params={"nHat_B": [1.0, 0.0, 0.0]}),
                ],
                actuators=[
                    ActuatorConfig(kind="reaction_wheel", name="rw-1",
                                    params={"gsHat_B": [1.0, 0.0, 0.0], "rw_type": "Honeywell_HR16",
                                            "maxMomentum": 100.0}),
                    ActuatorConfig(kind="reaction_wheel", name="rw-2",
                                    params={"gsHat_B": [0.0, 1.0, 0.0], "rw_type": "Honeywell_HR16",
                                            "maxMomentum": 100.0}),
                    ActuatorConfig(kind="reaction_wheel", name="rw-3",
                                    params={"gsHat_B": [0.0, 0.0, 1.0], "rw_type": "Honeywell_HR16",
                                            "maxMomentum": 100.0}),
                ],
                fsw_mode="sunSafePoint",
                # DEFAULT_MRP_GAINS (engine/fsw.py: K=3.5, P=30.0) is lifted
                # directly from Basilisk's own examples/BskSim reference
                # (BSK_Fsw.py's mrpFeedbackRWs), which is tuned for THAT
                # example's 900 kg*m^2 spacecraft (BSK_Dynamics.py's I_sc).
                # Applied unscaled to this template's 5 kg*m^2 _INERTIA_SMALL
                # hub, it is roughly 180x too stiff for this inertia and
                # produces a persistent, non-decaying ~30-degree pointing
                # oscillation (confirmed directly against a real Basilisk
                # build: sigma_BN never settles, even from a dead-rest
                # initial rate, over a 1500s run) -- bounded by RW torque
                # saturation rather than NaN, but not a real "pointed and
                # holding" safe mode. Scaled by this template's inertia
                # relative to that reference (K,P both x (5/900)) converges
                # cleanly instead (confirmed: sub-1e-6-degree final pointing
                # error over the same run). See HISTORY.md for the full
                # investigation -- this gain/inertia mismatch is a general
                # risk for ANY small-sat-scale spacecraft left on
                # DEFAULT_MRP_GAINS, not specific to this template.
                control_params={"K": 0.0194, "P": 0.167},
                power=PowerConfig(panel_area_m2=0.3, panel_efficiency=0.28, battery_capacity_wh=80.0),
            ),
        ],
    )


def build_08_mission_sequence_orbit_raise() -> Scenario:
    from missionstudio.schema.command import Command

    return Scenario(
        name="08 - Mission sequence: impulsive orbit raise",
        description=(
            "Introduces the Mission Sequence layer (Resources/Mission Sequence/Output -- see this "
            "project's HISTORY.md, 'What Phase 6 (Mission Sequence architecture) adds'): rather than one "
            "single propagate-to-duration run, this scenario is a time-ordered list of commands, "
            "editable as a tree in the GUI's 'Mission sequence' panel: coast, snapshot the orbit "
            "state, apply a single prograde impulsive delta-V, coast again, snapshot again. The "
            "maneuver command applies delta_v_m_s in the 'vnb' frame (velocity/normal/binormal -- "
            "'inertial' applies it directly in the N frame instead, useful when you already know the "
            "exact inertial-frame vector you want), so [50, 0, 0] here means '+50 m/s prograde', the "
            "simplest kind of orbit-raising burn.\n\n"
            "What to look at: run it and check the 'Mission Output' tab (or, from the CLI, "
            "command_summary.csv) -- the two 'report' commands snapshot sat-1.position_N/velocity_N "
            "before and after the burn. A prograde burn on a circular orbit raises the OPPOSITE side "
            "of the orbit into an ellipse -- the orbit is no longer circular after the burn, with a "
            "higher apoapsis where the spacecraft now moves slower and a periapsis back at the "
            "original altitude.\n\n"
            "Try changing: delta_v_m_s's magnitude (bigger burn = bigger apoapsis raise) or sign "
            "(negative = retrograde, LOWERS the opposite side of the orbit instead), or add a second "
            "maneuver command half an orbit later to circularize at the new higher altitude -- a "
            "genuine two-burn Hohmann transfer, built entirely from this project's own mission "
            "-sequence commands.\n\n"
            "Updated to include 10th-degree spherical-harmonics gravity, Sun/Moon third-body gravity, "
            "atmospheric drag, and solar radiation pressure -- physically relevant at 400 km, and this "
            "template's own lesson (the Mission Sequence command layer / maneuver mechanics) doesn't "
            "depend on a clean two-body baseline the way '01'/'09' deliberately do. Drag uses a "
            "CONSERVATIVE, 95th-percentile sustained-worst-case F10.7/Ap margin from real historical "
            "CelesTrak data (see engine/spaceweather.py's own docstring), needing network access to "
            "CelesTrak or a local historical file to actually run."
        ),
        epoch_utc="2030-01-01T00:00:00",
        simulation_mode="orbit_only",
        gravity=GravityConfig(central_body="earth", central_body_degree=10, third_body_perturbers=["sun", "moon"]),
        sim_settings=SimSettings(duration_days=1.0, dynamics_task_rate_s=10.0, integrator="rkf78"),
        space_weather=_conservative_drag_margin(),
        spacecraft=[
            SpacecraftConfig(
                name="sat-1",
                orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6778.0, eccentricity=0.0,
                               inclination_deg=28.5, raan_deg=0.0, arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
                dry_mass_kg=500.0,
                enable_drag=True, drag_coeff=2.2, drag_area_m2=1.0,
                enable_srp=True, srp_coeff=1.3, srp_area_m2=1.0,
            ),
        ],
        mission_sequence=[
            Command(kind="propagate", label="Coast before burn",
                    params={"stop_condition": "duration", "duration_days": 0.1}),
            Command(kind="report", label="Before burn", params={"series": []}),
            Command(kind="maneuver", label="Prograde raise burn",
                    params={"spacecraft": "sat-1", "delta_v_m_s": [50.0, 0.0, 0.0], "frame": "vnb"}),
            Command(kind="propagate", label="Coast after burn",
                    params={"stop_condition": "duration", "duration_days": 0.5}),
            Command(kind="report", label="After burn", params={"series": []}),
        ],
    )


def build_09_monte_carlo_dispersion_analysis() -> Scenario:
    return Scenario(
        name="09 - Monte Carlo dispersion analysis",
        description=(
            "The same circular LEO orbit as '01', but run as a Monte Carlo batch of 20 cases instead "
            "of a single deterministic run: each case's dry_mass_kg is independently redrawn from a "
            "normal distribution (mean 500 kg, std deviation 25 kg -- a stand-in for, e.g., propellant "
            "-loading or manufacturing-tolerance uncertainty). This is the basic pattern behind real "
            "uncertainty-quantification questions: 'given that I don't know this spacecraft's exact "
            "mass to the kilogram, how much does that affect the outcome I care about?'\n\n"
            "What to look at: run via the GUI's 'Run Monte Carlo...' action (or "
            "'missionstudio monte-carlo') and pick an archive directory -- each of the 20 runs is "
            "archived separately, so you can compare e.g. final position across cases to see how much "
            "(or how little) an 5% mass uncertainty actually perturbs the resulting orbit over a "
            "1-day propagation (physically: not much, for pure two-body motion -- mass doesn't affect "
            "trajectory at all, only propellant-consuming maneuvers/drag/SRP would show sensitivity; "
            "try enabling one of those, or add an 'attitude_sigma_bn' dispersion, to see a case where "
            "it does matter).\n\n"
            "Try changing: num_runs (more runs = a smoother distribution of outcomes, at proportional "
            "runtime cost), std_deviation (a wider spread), or add a second DispersionConfig with "
            "quantity='attitude_sigma_bn'/kind='uniform_euler_mrp' for an initial-attitude dispersion "
            "instead (needs simulation_mode='full_attitude')."
        ),
        epoch_utc="2030-01-01T00:00:00",
        simulation_mode="orbit_only",
        gravity=GravityConfig(central_body="earth", central_body_degree=0),
        sim_settings=SimSettings(duration_days=1.0, dynamics_task_rate_s=30.0, integrator="rkf78"),
        spacecraft=[
            SpacecraftConfig(
                name="sat-1",
                orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6778.0, eccentricity=0.0,
                               inclination_deg=51.6, raan_deg=0.0, arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
                dry_mass_kg=500.0,
            ),
        ],
        monte_carlo=MonteCarloConfig(
            enabled=True, num_runs=20, thread_count=1,
            dispersions=[
                DispersionConfig(spacecraft="sat-1", quantity="dry_mass_kg", kind="normal",
                                   mean=500.0, std_deviation=25.0),
            ],
        ),
    )


def build_10_gravity_gradient_torque() -> Scenario:
    return Scenario(
        name="10 - Gravity gradient torque (uncontrolled)",
        description=(
            "A spacecraft with NO attitude control (fsw_mode is None) and an elongated, non-spherical "
            "inertia tensor (Ixx=Iyy=12.5, Izz=7.5 kg*m^2) with SpacecraftConfig.enable_gravity_gradient "
            "set -- Basilisk's real GravityGradientEffector, the torque the central body's own gravity "
            "exerts across a spacecraft's non-uniform mass distribution. With zero initial body rate "
            "and no other torque source, a spacecraft normally stays frozen at its initial attitude for "
            "the entire run (see '06'/'07' for what active control looks like); this one does NOT, "
            "because gravity gradient torque is real physics, not a bug.\n\n"
            "What to look at: this is a Basilisk-truth-level effect, not exposed as a named result "
            "series when fsw_mode is None (see engine.service.SimulationService.run()'s own docstring) "
            "-- the clearest way to see it is tests/test_gravity_gradient.py's own technique (reading "
            "scStateOutMsg.sigma_BN directly), or simply watching the spacecraft's attitude indicator "
            "drift in Vizard over the run instead of staying locked to its starting orientation. For a "
            "spherically-symmetric inertia (Ixx=Iyy=Izz), this torque is identically zero -- try setting "
            "all three equal and confirm it stays frozen again.\n\n"
            "Try changing: the inertia spread (more elongated = stronger torque), the orbit altitude "
            "(gravity gradient torque falls off as 1/r^3 -- much stronger effect in a very low orbit "
            "than at GEO), or enable fsw_mode='inertial3D' with reaction wheels (see '07') to see an "
            "active controller simply reject this as one more disturbance torque."
        ),
        epoch_utc="2030-01-01T00:00:00",
        simulation_mode="full_attitude",
        # Point-mass gravity only, no third-body perturbers, no drag/SRP --
        # isolates the gravity-gradient effect from every other torque/
        # perturbation source, same "isolate the one concept" role as '01'/
        # '06'/'09'.
        gravity=GravityConfig(central_body="earth", central_body_degree=0),
        sim_settings=SimSettings(duration_days=0.5, dynamics_task_rate_s=5.0, integrator="rkf78"),
        spacecraft=[
            SpacecraftConfig(
                name="sat-1",
                orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6778.0, eccentricity=0.0,
                               inclination_deg=51.6, raan_deg=0.0, arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
                dry_mass_kg=500.0,
                inertia_kg_m2=list(_INERTIA_MEDIUM),
                sigma_bn_init=[0.0, 0.0, 0.0],
                omega_bn_b_init_rad_s=[0.0, 0.0, 0.0],
                enable_gravity_gradient=True,
            ),
        ],
    )


def build_11_thruster_attitude_control() -> Scenario:
    return Scenario(
        name="11 - Attitude control via thrusters (no reaction wheels)",
        description=(
            "The thruster counterpart to '06'/'07': instead of reaction wheels or an idealized "
            "actuator, this spacecraft points itself using eight real ACS thrusters (an 8-thruster "
            "corner-mounted cube layout, the same real configuration "
            "examples/scenarioAttitudeFeedback2T_TH.py/scenarioMomentumDumping.py ship) via Basilisk's "
            "real thrForceMapping -> thrFiringSchmitt -> thrusterDynamicEffector chain (see "
            "engine.fsw.build_thrusters/build_thruster_force_mapping). fsw_mode 'inertial3D' commands a "
            "fixed inertial attitude; the spacecraft starts tipped away from it with a small initial "
            "body rate.\n\n"
            "What to look at: result series '{sat-1}.thruster_on_time' (one column per thruster, "
            "seconds) shows which thrusters fired and for how long as the controller worked to null "
            "the attitude error -- compare against '07''s '{sat-1}.rw_speeds' to see the equivalent "
            "signal for the reaction-wheel case. In Vizard, thruster plumes render natively "
            "(engine.vizard.enable_vizard's thr_effectors_by_spacecraft) when a thruster is firing.\n\n"
            "Try changing: each actuator's MaxThrust (weaker thrusters take longer to null the same "
            "attitude error), or the thruster layout itself (fewer than 6 well-placed thrusters cannot "
            "produce a pure torque about all three axes -- thrForceMapping will report a degraded/"
            "saturated solution)."
        ),
        epoch_utc="2030-01-01T00:00:00",
        simulation_mode="full_attitude",
        gravity=GravityConfig(central_body="earth", central_body_degree=0),
        sim_settings=SimSettings(duration_days=0.01, dynamics_task_rate_s=0.5, integrator="rkf78"),
        spacecraft=[
            SpacecraftConfig(
                name="sat-1",
                orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6928.0, eccentricity=0.0,
                               inclination_deg=45.0, raan_deg=0.0, arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
                dry_mass_kg=100.0,
                inertia_kg_m2=[10.0, 0.0, 0.0, 0.0, 10.0, 0.0, 0.0, 0.0, 10.0],
                sigma_bn_init=[0.3, 0.2, -0.1],
                omega_bn_b_init_rad_s=[0.0, 0.0, 0.0],
                fsw_mode="inertial3D",
                fsw_params={"sigma_R0N": [0.0, 0.0, 0.0]},
                actuators=[
                    ActuatorConfig(kind="thruster", name=f"thr-{i + 1}",
                                     params={"r_B": pos, "tHat_B": direction, "MaxThrust": 1.0})
                    for i, (pos, direction) in enumerate(zip(
                        [[-1, -1, 1.28], [1, -1, -1.28], [1, -1, 1.28], [1, 1, -1.28],
                         [1, 1, 1.28], [-1, 1, -1.28], [-1, 1, 1.28], [-1, -1, -1.28]],
                        [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0],
                         [-1, 0, 0], [1, 0, 0], [0, -1, 0], [0, 1, 0]],
                    ))
                ],
            ),
        ],
    )


def build_12_reaction_wheel_momentum_dumping() -> Scenario:
    return Scenario(
        name="12 - Reaction wheel momentum dumping",
        description=(
            "A spacecraft under normal reaction-wheel attitude control (fsw_mode 'inertial3D', same "
            "control chain as '07') whose four wheels start out already heavily spun up (the same "
            "pre-saturated Omega values as examples/scenarioMomentumDumping.py) -- MomentumDumpingConfig "
            "(hs_max=80 N*m*s) fires an 8-thruster desaturation cluster via thrMomentumManagement -> "
            "thrForceMapping -> thrMomentumDumping (engine.fsw.build_momentum_dumping) to bleed the "
            "excess momentum off, while the SAME reaction wheels stay in control of attitude the whole "
            "time -- the thrusters here never do attitude control, only desaturation. "
            "engine.service.SimulationService.build() automatically primes one dynamics tick and "
            "re-Resets the desaturation module before the real run starts, a real Basilisk requirement "
            "confirmed against this checkout's own build (see engine.fsw.build_momentum_dumping's "
            "docstring) -- nothing about that is visible here, it just works.\n\n"
            "What to look at: result series '{sat-1}.rw_speeds' should show all four wheel speeds "
            "dropping in sharp steps (each step is one desaturation firing) rather than staying flat or "
            "climbing; '{sat-1}.thruster_on_time' shows exactly when the desaturation thrusters fired.\n\n"
            "Try changing: momentum_dumping.hs_max (a lower threshold triggers desaturation sooner/more "
            "often), the wheels' initial Omega (closer to maxMomentum = desaturates almost immediately), "
            "or remove momentum_dumping entirely to see the wheel speeds never decrease on their own."
        ),
        epoch_utc="2030-01-01T00:00:00",
        simulation_mode="full_attitude",
        gravity=GravityConfig(central_body="earth", central_body_degree=0),
        sim_settings=SimSettings(duration_days=0.01, dynamics_task_rate_s=1.0, integrator="rkf78"),
        spacecraft=[
            SpacecraftConfig(
                name="sat-1",
                orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6928.0, eccentricity=0.0,
                               inclination_deg=45.0, raan_deg=0.0, arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
                dry_mass_kg=2500.0,
                inertia_kg_m2=[1700.0, 0.0, 0.0, 0.0, 1700.0, 0.0, 0.0, 0.0, 1800.0],
                sigma_bn_init=[0.0, 0.0, 0.0],
                omega_bn_b_init_rad_s=[0.0, 0.0, 0.0],
                fsw_mode="inertial3D",
                fsw_params={"sigma_R0N": [0.0, 0.0, 0.0]},
                actuators=[
                    ActuatorConfig(kind="reaction_wheel", name="rw-1",
                                     params={"gsHat_B": [0.7071, 0.0, 0.7071], "rw_type": "Honeywell_HR16",
                                             "maxMomentum": 100.0, "Omega": 4000.0}),
                    ActuatorConfig(kind="reaction_wheel", name="rw-2",
                                     params={"gsHat_B": [0.0, 0.7071, 0.7071], "rw_type": "Honeywell_HR16",
                                             "maxMomentum": 100.0, "Omega": 2000.0}),
                    ActuatorConfig(kind="reaction_wheel", name="rw-3",
                                     params={"gsHat_B": [-0.7071, 0.0, 0.7071], "rw_type": "Honeywell_HR16",
                                             "maxMomentum": 100.0, "Omega": 3500.0}),
                    ActuatorConfig(kind="reaction_wheel", name="rw-4",
                                     params={"gsHat_B": [0.0, -0.7071, 0.7071], "rw_type": "Honeywell_HR16",
                                             "maxMomentum": 100.0, "Omega": 0.0}),
                    *[
                        ActuatorConfig(kind="thruster", name=f"desat-{i + 1}",
                                         params={"r_B": pos, "tHat_B": direction, "MaxThrust": 5.0,
                                                 "thruster_type": "MOOG_Monarc_5"})
                        for i, (pos, direction) in enumerate(zip(
                            [[-1, -1, 1.28], [1, -1, -1.28], [1, -1, 1.28], [1, 1, -1.28],
                             [1, 1, 1.28], [-1, 1, -1.28], [-1, 1, 1.28], [-1, -1, -1.28]],
                            [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0],
                             [-1, 0, 0], [1, 0, 0], [0, -1, 0], [0, 1, 0]],
                        ))
                    ],
                ],
                momentum_dumping=MomentumDumpingConfig(hs_max=80.0, thr_min_fire_time=0.02, max_counter_value=100),
            ),
        ],
    )


def build_13_magnetic_torque_rod_momentum_management() -> Scenario:
    return Scenario(
        name="13 - Reaction wheel momentum management via magnetic torque rods",
        description=(
            "The alternative desaturation strategy to '12': instead of waiting for total momentum to "
            "cross a threshold and firing a discrete thruster burst, this spacecraft's four reaction "
            "wheels (same skewed-pyramid layout as examples/scenarioMtbMomentumManagement.py) are "
            "CONTINUOUSLY biased toward target speeds (800/600/400/200 RPM) the whole run, using four "
            "magnetic torque rods and the real geomagnetic field (Basilisk's WMM model) via "
            "MagneticMomentumManagementConfig (engine.fsw.build_mtb_desaturation: a dedicated "
            "magnetometer + tamComm feed mtbMomentumManagement, which sits BETWEEN rwMotorTorque and "
            "the RW hardware, modifying the commanded motor torque). No control-allocation conflict "
            "with the fsw_mode='inertial3D' attitude pointing running at the same time -- magnetic "
            "torque rods never do attitude control here, only this continuous momentum bias.\n\n"
            "What to look at: result series '{sat-1}.rw_speeds' should climb from zero and settle near "
            "800/600/400/200 RPM (converted: ~83.8/62.8/41.9/20.9 rad/s) over the ~2 hour run -- "
            "confirmed by direct experimentation against a real Basilisk build to converge to within "
            "about 0.5 RPM of each target. Compare the SHAPE of this convergence against '12''s sharp, "
            "discrete desaturation steps -- same underlying problem (reaction wheels accumulating "
            "momentum), two structurally different real Basilisk solutions.\n\n"
            "Try changing: wheel_speed_biases_rad_s (different target speeds per wheel), c_gain (a "
            "larger gain reacts faster but can overshoot/oscillate), or the orbit inclination (a "
            "near-equatorial orbit sees a weaker, less favorably-oriented geomagnetic field than a "
            "higher-inclination one, which can slow convergence noticeably)."
        ),
        epoch_utc="2030-01-01T00:00:00",
        simulation_mode="full_attitude",
        gravity=GravityConfig(central_body="earth", central_body_degree=0),
        sim_settings=SimSettings(duration_days=120.0 / 1440.0, dynamics_task_rate_s=2.0, integrator="rkf78"),
        spacecraft=[
            SpacecraftConfig(
                name="sat-1",
                orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6778.14, eccentricity=0.0,
                               inclination_deg=45.0, raan_deg=60.0, arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
                dry_mass_kg=10.0,
                inertia_kg_m2=[0.02 / 3, 0.0, 0.0, 0.0, 0.1256 / 3, 0.0, 0.0, 0.0, 0.1256 / 3],
                sigma_bn_init=[0.1, 0.2, -0.3],
                omega_bn_b_init_rad_s=[0.001, -0.01, 0.03],
                fsw_mode="inertial3D",
                fsw_params={"sigma_R0N": [0.0, 0.0, 0.0]},
                control_params={"K": 0.0001, "P": 0.002},
                actuators=[
                    *[
                        ActuatorConfig(kind="reaction_wheel", name=f"rw-{i + 1}",
                                         params={"gsHat_B": axis, "rw_type": "BCT_RWP015", "Omega_max": 5000.0})
                        for i, axis in enumerate(_MTB_DEMO_RW_AXES)
                    ],
                    ActuatorConfig(kind="magnetic_torque_rod", name="mtb-1",
                                     params={"gtHat_B": [1.0, 0.0, 0.0], "max_dipole_a_m2": 0.1}),
                    ActuatorConfig(kind="magnetic_torque_rod", name="mtb-2",
                                     params={"gtHat_B": [0.0, 1.0, 0.0], "max_dipole_a_m2": 0.1}),
                    ActuatorConfig(kind="magnetic_torque_rod", name="mtb-3",
                                     params={"gtHat_B": [0.0, 0.0, 1.0], "max_dipole_a_m2": 0.1}),
                    ActuatorConfig(kind="magnetic_torque_rod", name="mtb-4",
                                     params={"gtHat_B": [0.70710678, 0.70710678, 0.0], "max_dipole_a_m2": 0.1}),
                ],
                magnetic_momentum_management=MagneticMomentumManagementConfig(
                    wheel_speed_biases_rad_s=[
                        800.0 * _RPM_TO_RAD_S, 600.0 * _RPM_TO_RAD_S, 400.0 * _RPM_TO_RAD_S, 200.0 * _RPM_TO_RAD_S,
                    ],
                    c_gain=0.003,
                ),
            ),
        ],
    )


def build_14_css_sun_heading_estimation() -> Scenario:
    return Scenario(
        name="14 - Sun-heading estimation from coarse sun sensors",
        description=(
            "Real sun-direction ESTIMATION (not truth) feeding a closed attitude-control loop: eight "
            "coarse_sun_sensor devices in a cube layout (same directions as "
            "examples/BskSim/models/BSK_Dynamics.py's SetCSSConstellation()) feed a dedicated "
            "CSSConstellation + cssWlsEst weighted-least-squares estimator (engine.fsw."
            "build_css_sun_estimation), and fsw_params['use_css_estimation']=True routes that ESTIMATE "
            "(rather than simpleNav's truth) into fsw_mode 'sunSafePoint''s sunDirectionInMsg -- the "
            "same architecture as examples/BskSim/scenarios/scenario_AttEclipse.py's real reference "
            "(cssWlsEst -> sunSafePoint -> mrpFeedback -> reaction wheels).\n\n"
            "control_params is deliberately NOT left at engine.fsw.DEFAULT_MRP_GAINS (K=3.5/P=30): that "
            "default is lifted directly from Basilisk's own BSK_Fsw.py reference, tuned for THAT "
            "example's 900 kg*m^2 spacecraft. Applied unscaled to this template's 5 kg*m^2 hub it is "
            "roughly 180x too stiff -- confirmed directly against a real Basilisk build to produce a "
            "persistent, non-decaying ~30-degree pointing oscillation (bounded by RW torque saturation, "
            "not a crash, but never actually 'pointed and holding'). Scaling K and P by this hub's "
            "inertia relative to that reference (both x 5/900) converges cleanly instead -- confirmed: "
            "sub-1e-6-degree final pointing error. See HISTORY.md for the full investigation; this "
            "gain/inertia mismatch is a general risk for ANY small-sat-scale spacecraft left on "
            "DEFAULT_MRP_GAINS, worth checking on every new fsw_mode spacecraft this small, not "
            "something specific to CSS estimation.\n\n"
            "What to look at: '{sat-1}.sun_heading_body_estimated' (the CSS estimate) should settle near "
            "[0, 0, 1] in the body frame as sunSafePoint drives the commanded body +Z axis "
            "(sHatBdyCmd) onto the real sun direction -- compare its early, still-converging samples "
            "against its settled final value to see the estimate itself stabilize as the attitude "
            "stops moving. The WLS estimate's accuracy is purely geometry-dependent (how many of the "
            "8 sensors are actually sunlit for the current sun direction, confirmed directly against a "
            "real Basilisk build: an under-determined 2-of-8-illuminated case gave 14.5 degrees of "
            "error, a well-conditioned 4-of-8 case gave an exact 0.0-degree match with zero sensor "
            "noise) -- real hardware has exactly this coverage gap, it is not something to 'fix' here.\n\n"
            "Try changing: the coarse_sun_sensor fov_deg values (a narrower FOV sees fewer sensors "
            "illuminated at once, degrading the WLS conditioning), or fsw_params['use_css_estimation'] "
            "to False to compare against simpleNav's noise-free truth sun direction instead."
        ),
        epoch_utc="2030-01-01T00:00:00",
        simulation_mode="full_attitude",
        # "sun" must be SPICE-tracked (third_body_perturbers) -- the CSS
        # estimation chain's sunInMsg needs the same SpicePlanetStateMsg
        # simpleNav's own truth sun direction uses (see engine.service.py's
        # SimulationServiceError guard for this exact requirement).
        gravity=GravityConfig(central_body="earth", central_body_degree=0, third_body_perturbers=["sun"]),
        sim_settings=SimSettings(duration_days=2160.0 / 86400.0, dynamics_task_rate_s=1.0, integrator="rkf78"),
        spacecraft=[
            SpacecraftConfig(
                name="sat-1",
                orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6928.0, eccentricity=0.0,
                               inclination_deg=45.0, raan_deg=0.0, arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
                dry_mass_kg=50.0,
                inertia_kg_m2=list(_INERTIA_SMALL),
                sigma_bn_init=[0.1, 0.2, -0.15],
                omega_bn_b_init_rad_s=[0.001, -0.001, 0.0005],
                sensors=[
                    SensorConfig(kind="coarse_sun_sensor", name=f"css-{i + 1}",
                                   params={"nHat_B": nhat, "fov_deg": 160.0})
                    for i, nhat in enumerate([
                        [0.0, 0.707107, 0.707107], [0.707107, 0.0, 0.707107],
                        [0.0, -0.707107, 0.707107], [-0.707107, 0.0, 0.707107],
                        [0.0, -0.965926, -0.258819], [-0.707107, -0.353553, -0.612372],
                        [0.0, 0.258819, -0.965926], [0.707107, -0.353553, -0.612372],
                    ])
                ],
                actuators=[
                    ActuatorConfig(kind="reaction_wheel", name="rw-1",
                                     params={"gsHat_B": [1.0, 0.0, 0.0], "rw_type": "Honeywell_HR16",
                                             "maxMomentum": 100.0}),
                    ActuatorConfig(kind="reaction_wheel", name="rw-2",
                                     params={"gsHat_B": [0.0, 1.0, 0.0], "rw_type": "Honeywell_HR16",
                                             "maxMomentum": 100.0}),
                    ActuatorConfig(kind="reaction_wheel", name="rw-3",
                                     params={"gsHat_B": [0.0, 0.0, 1.0], "rw_type": "Honeywell_HR16",
                                             "maxMomentum": 100.0}),
                ],
                fsw_mode="sunSafePoint",
                fsw_params={"sHatBdyCmd": [0.0, 0.0, 1.0], "use_css_estimation": True},
                control_params={"K": 0.0194, "P": 0.167},
            ),
        ],
    )


def build_15_celestial_body_pointing() -> Scenario:
    return Scenario(
        name="15 - Direct celestial-body pointing (locationPointing + target_body)",
        description=(
            "fsw_mode 'locationPointing' has TWO target options: '07'-style pointing at a ground "
            "station (fsw_params['target_ground_station']), or pointing straight at a celestial body "
            "(fsw_params['target_body']) -- this template is the second one. A body-fixed axis "
            "(pHat_B, here the spacecraft +Z) stays pointed at the Moon throughout the orbit, built via "
            "engine.fsw.build_ephemeris_converter() (SpicePlanetStateMsg -> EphemerisMsg -> "
            "locationPointing.celBodyInMsg), the same converter + guidance pairing as Basilisk's own "
            "examples/scenarioAsteroidArrival.py (there pointing an antenna at Earth and a camera at an "
            "asteroid; here, at the Moon). target_body must name gravity.central_body or one of "
            "gravity.third_body_perturbers -- 'moon' is SPICE-tracked here for exactly that reason.\n\n"
            "What to look at: there is no separate result series for the body-to-target pointing error "
            "yet (add a 'report' mission_sequence command on sat-1.attitude_sigma_bn, see '08', or watch "
            "Vizard's live attitude indicator) -- but unlike '06'/'07's hillPoint/sunSafePoint, the "
            "target direction here keeps changing as the Moon moves along its own orbit while the "
            "spacecraft moves along its much faster one, so the commanded attitude is never constant.\n\n"
            "Try changing: target_body to 'sun' (already SPICE-tracked here too) to compare a much "
            "farther, slower-moving target's pointing behavior against the Moon's; or pHat_B to a "
            "different body axis to re-point a different physical location on the spacecraft (e.g. a "
            "antenna mounted off the +Z face) at the same target."
        ),
        epoch_utc="2030-01-01T00:00:00",
        simulation_mode="full_attitude",
        gravity=GravityConfig(central_body="earth", central_body_degree=10, third_body_perturbers=["sun", "moon"]),
        # dynamics_task_rate_s=0.1: idealized (no actuator hardware)
        # mrpFeedback control with DEFAULT_MRP_GAINS needs this fine a rate
        # to stay discrete-time stable -- see '06's own comment and
        # HISTORY.md for the full investigation; confirmed directly for
        # this exact locationPointing/target_body combination in
        # tests/test_location_pointing_target_body.py.
        sim_settings=SimSettings(duration_days=0.05, dynamics_task_rate_s=0.1, integrator="rkf78"),
        spacecraft=[
            SpacecraftConfig(
                name="sat-1",
                orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6928.0, eccentricity=0.0,
                               inclination_deg=45.0, raan_deg=0.0, arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
                dry_mass_kg=300.0,
                inertia_kg_m2=list(_INERTIA_MEDIUM),
                sigma_bn_init=[0.1, 0.2, -0.15],
                omega_bn_b_init_rad_s=[0.001, -0.001, 0.0005],
                fsw_mode="locationPointing",
                fsw_params={"target_body": "moon", "pHat_B": [0.0, 0.0, 1.0]},
            ),
        ],
    )


def build_16_lambert_transfer() -> Scenario:
    from missionstudio.schema.command import Command

    r_earth_m = 6378.0e3
    time_of_flight_s = 2490.0

    return Scenario(
        name="16 - Lambert transfer: solving for a point-to-point delta-V",
        description=(
            "A new Mission Sequence command kind: 'lambert_transfer' solves for whatever impulsive "
            "delta-V takes the spacecraft from its CURRENT state to target_position_m after "
            "time_of_flight_s, via Basilisk's own lambertPlanner -> lambertSolver -> lambertValidator "
            "chain (engine.mission_engine.MissionEngine._run_lambert_transfer), then applies it "
            "immediately -- unlike '08's 'maneuver' command, you specify WHERE you want to end up, not "
            "the delta-V itself. Same underlying 3 Basilisk modules, same validation/reporting "
            "philosophy as Basilisk's own examples/scenarioLambertSolver.py.\n\n"
            "This exact configuration (orbit, target_position_m, time_of_flight_s) was confirmed "
            "directly against a real Basilisk build to land within floating-point noise (sub-millimeter) "
            "of target_position_m when the resulting delta-V is propagated forward by time_of_flight_s -- "
            "not a hand-picked-to-look-plausible example.\n\n"
            "What to look at: the 'Mission Output' tab's two 'report' commands snapshot "
            "sat-1.position_N before and after the transfer -- after propagating for time_of_flight_s, "
            "the 'after' position should sit almost exactly at target_position_m "
            f"([{-(r_earth_m + 200.0e3):.0f}, 0, 0] m here).\n\n"
            "Try changing: target_position_m (any reachable point works, not just ones near the current "
            "orbit), time_of_flight_s (very short times need very large, often rejected, delta-Vs -- try "
            "making it unreasonably small to see lambert_transfer raise a clear "
            "'lambertValidator reported' error instead of silently doing nothing), or "
            "min_orbit_radius_m (set it to the central body's own radius to reject any transfer "
            "trajectory that would dip through the surface)."
        ),
        epoch_utc="2030-01-01T00:00:00",
        simulation_mode="orbit_only",
        gravity=GravityConfig(central_body="earth", central_body_degree=0),
        sim_settings=SimSettings(duration_days=0.2, dynamics_task_rate_s=10.0, integrator="rkf78"),
        spacecraft=[
            SpacecraftConfig(
                name="sat-1",
                orbit=OrbitIC(type="classical_elements", semi_major_axis_km=10000.0, eccentricity=0.001,
                               inclination_deg=5.0, raan_deg=10.0, arg_periapsis_deg=10.0, true_anomaly_deg=10.0),
                dry_mass_kg=330.0,
            ),
        ],
        mission_sequence=[
            Command(kind="report", label="Before transfer", params={"series": []}),
            Command(kind="lambert_transfer", label="Lambert transfer burn", params={
                "spacecraft": "sat-1",
                "target_position_m": [-(r_earth_m + 200.0e3), 0.0, 0.0],
                "time_of_flight_s": time_of_flight_s,
                "max_distance_target_m": 500.0,
                "min_orbit_radius_m": r_earth_m,
            }),
            Command(kind="propagate", label="Coast to arrival",
                    params={"stop_condition": "duration", "duration_days": time_of_flight_s / 86400.0}),
            Command(kind="report", label="After transfer (should match target_position_m)", params={"series": []}),
        ],
    )


def build_17_fuel_tank_depletion() -> Scenario:
    return Scenario(
        name="17 - Real propellant depletion (fuel tank)",
        description=(
            "The exact same 8-thruster attitude control setup as '11' (inertial3D pointing, the real "
            "thrForceMapping -> thrFiringSchmitt -> thrusterDynamicEffector chain), with a real "
            "FuelTankConfig added -- Basilisk's own fuelTank state effector (engine.fsw.build_fuel_tank, "
            "confirmed against examples/MultiSatBskSim/modelsMultiSat/BSK_MultiSatDynamics.py's own "
            "SetFuelTank()) now tracks REAL propellant depletion as the thrusters fire, reading the same "
            "mass-flow rate (mDot = F / (steadyIsp * g0)) each thruster already computes for its own "
            "physics -- unlike this app's older station-keeping/phasing/constant-thrust propellant "
            "bookkeeping (engine.orbit_maintenance, a hand-rolled Python estimate), this is Basilisk's "
            "own state effector doing the real physics, including the resulting center-of-mass shift as "
            "propellant depletes.\n\n"
            "This exact configuration was confirmed directly against a real Basilisk build: the "
            "spacecraft's attitude error converges from its initial tip (sigma norm ~0.37) to near-zero "
            "(~0.002) within about 100-150 seconds, consuming roughly 0.185 kg of the tank's 0.5 kg "
            "starting load during that active correction burn -- then '{sat-1}.fuel_mass_remaining' goes "
            "flat once the attitude has converged and the thrusters stop firing, a clean before "
            "/during/after depletion curve.\n\n"
            "What to look at: result series '{sat-1}.fuel_mass_remaining' alongside '{sat-1}"
            ".thruster_on_time' -- the fuel-depletion curve's steep drop should line up exactly with the "
            "period where thrusters are actively firing, then both go flat together.\n\n"
            "Try changing: fuel_tank.propellant_mass_kg (set it below the ~0.185 kg this convergence "
            "burn needs to see what happens when the tank runs dry mid-maneuver -- thrusterDynamicEffector "
            "keeps commanding thrust, but fuelTank has nothing left to give), or each thruster's "
            "steadyIsp (a lower Isp burns through the same delta-V budget using more propellant, a "
            "higher Isp less)."
        ),
        epoch_utc="2030-01-01T00:00:00",
        simulation_mode="full_attitude",
        gravity=GravityConfig(central_body="earth", central_body_degree=0),
        sim_settings=SimSettings(duration_days=0.01, dynamics_task_rate_s=0.5, integrator="rkf78"),
        spacecraft=[
            SpacecraftConfig(
                name="sat-1",
                orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6928.0, eccentricity=0.0,
                               inclination_deg=45.0, raan_deg=0.0, arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
                dry_mass_kg=100.0,
                inertia_kg_m2=[10.0, 0.0, 0.0, 0.0, 10.0, 0.0, 0.0, 0.0, 10.0],
                sigma_bn_init=[0.3, 0.2, -0.1],
                omega_bn_b_init_rad_s=[0.0, 0.0, 0.0],
                fsw_mode="inertial3D",
                fsw_params={"sigma_R0N": [0.0, 0.0, 0.0]},
                actuators=[
                    ActuatorConfig(kind="thruster", name=f"thr-{i + 1}",
                                     params={"r_B": pos, "tHat_B": direction, "MaxThrust": 1.0})
                    for i, (pos, direction) in enumerate(zip(
                        [[-1, -1, 1.28], [1, -1, -1.28], [1, -1, 1.28], [1, 1, -1.28],
                         [1, 1, 1.28], [-1, 1, -1.28], [-1, 1, 1.28], [-1, -1, -1.28]],
                        [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0],
                         [-1, 0, 0], [1, 0, 0], [0, -1, 0], [0, 1, 0]],
                    ))
                ],
                fuel_tank=FuelTankConfig(propellant_mass_kg=0.5, max_propellant_mass_kg=1.0),
            ),
        ],
    )


def build_18_leo_station_keeping() -> Scenario:
    # Verification note (see this function's own description string
    # below for the user-facing version): this sandbox has no route to
    # CelesTrak, so the shipped nrlmsise00 atmosphere model's exact decay
    # rate couldn't be re-verified end-to-end here (same gap as '04'/'05'
    # already document). The station_keeping/drag parameters below WERE
    # tuned and confirmed against a real Basilisk build, bypassing SPICE
    # the same way tests/test_mtb_desaturation.py does, using
    # engine.orbit_maintenance.build_station_keeping() directly against a
    # bare SimulationBaseClass with a real dragDynamicEffector fed by
    # ExponentialAtmosphere -- NOT the shipped nrlmsise00 model, but
    # re-parameterized with a realistic ~400 km reference density
    # (~2.8e-12 kg/m^3, moderate solar activity) and a LEO-appropriate
    # ~60 km scale height (ExponentialAtmosphere's own built-in Earth
    # preset uses an 8.5 km scale height -- correct near the surface, but
    # it underestimates LEO density by roughly 15 orders of magnitude and
    # produces no meaningful decay at all over weeks). With that
    # realistic density, these parameters produced 2-3 real reboost burns
    # over the same 14-day window as '03' and used well under the
    # propellant_kg budget below -- the dragDynamicEffector/
    # StationKeepingController code paths themselves are the SAME
    # already-shipped, already-verified code every other enable_drag
    # template uses, only the verification harness differs.
    return Scenario(
        name="18 - LEO station-keeping",
        description=(
            "The direct LEO counterpart to '03' (GEO station-keeping): a 400 km small satellite "
            "actively maintaining its altitude against atmospheric drag -- the actual dominant driver "
            "of LEO altitude decay, the same way Sun/Moon/SRP drive GEO drift in '03' -- using the "
            "exact same station_keeping deadband thrust controller. Unlike GEO's typically-infrequent "
            "corrections, LEO drag is continuous and altitude-dependent (denser air lower down means "
            "faster decay), so this spacecraft needs noticeably more frequent, smaller corrections.\n\n"
            "What to look at: same as '03' -- run the CLI and check command_summary/results for "
            "propellant used over the 14-day run, and compare the number/frequency of burns against "
            "'03's GEO case in the station-keeping summary (README, 'Running the CLI'). The contrast "
            "is the lesson: GEO drift is slow and the deadband is wide (5 km) because the perturbing "
            "forces are weak and roughly constant; LEO drag is faster and the deadband here is tight "
            "(1 km) because a satellite this low can lose multiple km of altitude in days, not years.\n\n"
            "Try changing: the orbit's semi_major_axis_km (lower = thicker atmosphere = much faster "
            "decay = more frequent burns -- try 350 km or 300 km to see the effect accelerate "
            "sharply), drag_area_m2/drag_coeff (a satellite with more cross-sectional area per unit "
            "mass decays faster), or deadband_km (tighter means more frequent, smaller corrections, "
            "the same trade '03' suggests for GEO).\n\n"
            "enable_srp is deliberately OFF here (unlike '04'/'05', which enable it alongside drag): "
            "the point of this template, like '03's point about GEO, is to isolate the ONE dominant "
            "perturbation (drag) rather than mix in a secondary effect SRP is at this altitude. Uses "
            "the same CONSERVATIVE, 95th-percentile sustained-worst-case nrlmsise00 drag margin from "
            "real historical CelesTrak data as '04'/'05' (see engine/spaceweather.py's own docstring) "
            "-- needs network access to CelesTrak (or a local historical space-weather file set via "
            "space_weather.local_file_path) to actually run. NOTE: like '05', this template's exact "
            "decay rate under the real nrlmsise00 model has NOT been re-verified against a real "
            "multi-day Basilisk run in this development sandbox (no route to the NAIF SPICE kernel "
            "host or CelesTrak here) -- the station_keeping/drag parameters were instead tuned and "
            "confirmed against a bypass-SPICE build using a realistically-reparameterized simple "
            "exponential atmosphere model (2-3 real reboost burns over 14 days, well under budget); "
            "please report back if the real nrlmsise00 propellant budget looks off."
        ),
        epoch_utc="2030-01-01T00:00:00",
        simulation_mode="orbit_only",
        gravity=GravityConfig(central_body="earth", central_body_degree=10, third_body_perturbers=["sun", "moon"]),
        sim_settings=SimSettings(duration_days=14.0, dynamics_task_rate_s=30.0, integrator="rkf78"),
        space_weather=_conservative_drag_margin(),
        spacecraft=[
            SpacecraftConfig(
                name="leo-sat-1",
                orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6778.0, eccentricity=0.0,
                               inclination_deg=51.6, raan_deg=0.0, arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
                dry_mass_kg=120.0,
                enable_drag=True, drag_coeff=2.2, drag_area_m2=1.5,
                station_keeping=StationKeepingConfig(
                    target_altitude_km=400.0, deadband_km=1.0, thrust_n=0.05, isp_s=1500.0,
                    propellant_kg=2.0,
                ),
            ),
        ],
    )


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    _save(build_01_two_body_circular_orbit(), "01_two_body_circular_orbit.json")
    _save(build_02_elliptical_orbit_with_perturbations(), "02_elliptical_orbit_with_perturbations.json")
    _save(build_03_geo_station_keeping(), "03_geo_station_keeping.json")
    _save(build_04_walker_constellation(), "04_walker_constellation.json")
    _save(build_05_formation_flying_phasing(), "05_formation_flying_phasing.json")
    _save(build_06_attitude_pointing_basic(), "06_attitude_pointing_basic.json")
    _save(build_07_attitude_pointing_with_adcs_hardware(), "07_attitude_pointing_with_adcs_hardware.json")
    _save(build_08_mission_sequence_orbit_raise(), "08_mission_sequence_orbit_raise.json")
    _save(build_09_monte_carlo_dispersion_analysis(), "09_monte_carlo_dispersion_analysis.json")
    _save(build_10_gravity_gradient_torque(), "10_gravity_gradient_torque.json")
    _save(build_11_thruster_attitude_control(), "11_thruster_attitude_control.json")
    _save(build_12_reaction_wheel_momentum_dumping(), "12_reaction_wheel_momentum_dumping.json")
    _save(build_13_magnetic_torque_rod_momentum_management(),
          "13_magnetic_torque_rod_momentum_management.json")
    _save(build_14_css_sun_heading_estimation(), "14_css_sun_heading_estimation.json")
    _save(build_15_celestial_body_pointing(), "15_celestial_body_pointing.json")
    _save(build_16_lambert_transfer(), "16_lambert_transfer.json")
    _save(build_17_fuel_tank_depletion(), "17_fuel_tank_depletion.json")
    _save(build_18_leo_station_keeping(), "18_leo_station_keeping.json")


if __name__ == "__main__":
    main()
