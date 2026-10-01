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

r"""
The scenario file format: a versioned, human-readable JSON schema for
everything needed to define and run a mission-analysis case (spacecraft
config, orbit initial conditions, epoch, central body, sensors/actuators,
FSW mode, ground stations).

Deliberately dependency-light: standard-library ``dataclasses`` + hand
-written validation, not a pickled Python object and not a third-party
schema library (pydantic, etc.) -- consistent with keeping the backend
service layer's own dependency footprint small (Basilisk itself, plus
whatever the GUI needs, is already enough surface area). This module has
NO Basilisk import and is fully unit-testable without a Basilisk build --
see ``tests/test_scenario_schema.py``.

Versioning
----------
Every scenario file carries a top-level ``schema_version`` integer.
``load_scenario()`` runs the file through ``migrations.MIGRATIONS`` before
constructing a :class:`Scenario`, so old scenario files keep loading as the
schema grows -- see ``migrations.py``. Bump ``CURRENT_SCHEMA_VERSION`` and
add a migration function whenever a field is added, renamed, or removed in
a way that would break an older file.

Phase 0 scope note
-------------------
This schema is intentionally more complete than what Phase 0's
``engine.service.SimulationService`` actually consumes (see that module's
docstring for exactly what Phase 0 wires up: central-body point-mass/
spherical-harmonics gravity, one or more spacecraft with classical
-elements/Cartesian/TLE initial conditions, propagation only). Fields for
sensors, actuators, FSW modes, and ground stations are validated here and
carried through save/load round-trips starting now, precisely so the
schema does not need a disruptive reshape once Phase 2/3 start consuming
them -- retrofitting schema versioning after the fact is much more
painful than reserving the shape up front.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from .command import Command

CURRENT_SCHEMA_VERSION = 1

# SPICE-recognized central body name strings this schema accepts, matching
# Basilisk's simIncludeGravBody.gravBodyFactory named helpers
# (createSun/createEarth/createMoon/createMars/createMarsBarycenter/
# createVenus/createJupiter) -- see engine/service.py for where this list
# is actually consumed.
SUPPORTED_CENTRAL_BODIES = (
    "sun", "mercury", "venus", "earth", "moon", "mars", "mars barycenter", "jupiter",
)

ORBIT_IC_TYPES = ("classical_elements", "cartesian", "tle")

# classical_elements only: which anomaly field the user supplied (they're
# not interchangeable inputs -- mean anomaly needs Kepler's equation solved
# to get true anomaly, see engine.service._orbit_ic_to_rv).
ANOMALY_TYPES = ("true", "mean")

# Sensor/actuator/FSW-mode kinds engine.service.SimulationService actually
# wires up -- see that module's docstring for the exact Basilisk module
# each one maps to and for engine.fsw's guidance-chain construction.
# "reaction_wheel" (mrpFeedback + rwMotorTorque + reactionWheelStateEffector)
# and "thruster" (mrpFeedback + thrForceMapping + thrFiringSchmitt +
# thrusterDynamicEffector) are both real control-torque actuation paths --
# see SpacecraftConfig.validate() for why a spacecraft may use one or the
# other but not both. "magnetic_torque_rod" (MtbEffector + tamComm +
# mtbMomentumManagement) is wired up too, but ONLY for continuous
# reaction-wheel momentum management (see MagneticMomentumManagementConfig)
# -- there is no standalone attitude-control/detumble mode built on
# magnetic torque rods alone (Basilisk ships no ready-made B-dot-style
# controller for it), so a "magnetic_torque_rod" actuator with
# magnetic_momentum_management unset would simply never receive a
# command; SpacecraftConfig.validate() rejects that combination early
# rather than silently building a dead actuator (unlike Phase 0's drag/SRP
# flags, which stayed inert booleans, an actuator kind that silently did
# nothing would be a live foot-gun -- a spacecraft configured to detumble
# on magnetic torque rods that simply never fire).
SUPPORTED_SENSOR_KINDS = ("star_tracker", "imu", "coarse_sun_sensor", "magnetometer")
SUPPORTED_ACTUATOR_KINDS = ("reaction_wheel", "thruster", "magnetic_torque_rod")
SUPPORTED_FSW_MODES = ("inertial3D", "hillPoint", "velocityPoint", "sunSafePoint", "locationPointing")

# Phase 3: Monte Carlo dispersion quantities engine.monte_carlo actually
# builds a Basilisk.utilities.MonteCarlo.Dispersions class for, and which
# dispersion "kind" each quantity accepts -- see engine/monte_carlo.py's
# module docstring for exactly which Dispersions class each pairing maps
# to and why (e.g. a Cartesian position/velocity dispersion is deliberately
# NOT offered: Dispersions.UniformVectorCartDispersion/NormalVectorCartDispersion
# replace each component with an ABSOLUTE random value, not a perturbation
# around the nominal orbit, which would silently produce a physically
# nonsensical "dispersed" orbit).
DISPERSION_QUANTITIES = ("dry_mass_kg", "attitude_sigma_bn")
DISPERSION_KINDS_BY_QUANTITY = {
    "dry_mass_kg": ("uniform", "normal"),
    "attitude_sigma_bn": ("uniform_euler_mrp",),
}


class ScenarioValidationError(ValueError):
    """Raised by :meth:`Scenario.validate` (and the dataclass ``__post_init__``
    hooks it calls) with a specific, actionable message -- never a silent
    NaN or a bare ``KeyError``/``TypeError`` from malformed input, per the
    "clear error messages" requirement this project is built around.
    """


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ScenarioValidationError(message)


@dataclass
class OrbitIC:
    """One spacecraft's orbit initial condition, in exactly one of three
    forms. Only the fields for ``type`` need to be set; the others are
    left ``None`` and ignored -- this keeps the JSON readable (no
    all-fields-always-present clutter) while still being one dataclass, so
    ``engine.service.SimulationService`` has a single type to switch on.
    """

    type: str  # one of ORBIT_IC_TYPES

    # type == "classical_elements" (angles in degrees, matching the rest of
    # this codebase's convention -- see mission_config.py in ../missionAnalysis).
    # Exactly one of true_anomaly_deg/mean_anomaly_deg is used, chosen by
    # anomaly_type -- mean anomaly is the natural input for a mission
    # design spec (e.g. "M0 at epoch"), true anomaly for a specific
    # geometric snapshot; engine.service converts mean -> true via Kepler's
    # equation before calling elem2rv (which only accepts true anomaly).
    semi_major_axis_km: Optional[float] = None
    eccentricity: Optional[float] = None
    inclination_deg: Optional[float] = None
    raan_deg: Optional[float] = None
    arg_periapsis_deg: Optional[float] = None
    anomaly_type: str = "true"  # one of ANOMALY_TYPES
    true_anomaly_deg: Optional[float] = None
    mean_anomaly_deg: Optional[float] = None

    # type == "cartesian" (inertial frame of the scenario's central body)
    position_km: Optional[list] = None  # [x, y, z]
    velocity_km_s: Optional[list] = None  # [vx, vy, vz]

    # type == "tle"
    tle_line1: Optional[str] = None
    tle_line2: Optional[str] = None

    def validate(self) -> None:
        _require(self.type in ORBIT_IC_TYPES,
                  f"orbit.type {self.type!r} must be one of {ORBIT_IC_TYPES}")
        if self.type == "classical_elements":
            _require(self.semi_major_axis_km is not None and self.semi_major_axis_km > 0,
                      "classical_elements orbit needs semi_major_axis_km > 0")
            _require(self.eccentricity is not None and 0.0 <= self.eccentricity < 1.0,
                      "classical_elements orbit needs 0 <= eccentricity < 1 (elliptical only)")
            for name in ("inclination_deg", "raan_deg", "arg_periapsis_deg"):
                _require(getattr(self, name) is not None, f"classical_elements orbit needs {name}")
            _require(self.anomaly_type in ANOMALY_TYPES,
                      f"orbit.anomaly_type {self.anomaly_type!r} must be one of {ANOMALY_TYPES}")
            anomaly_field = "true_anomaly_deg" if self.anomaly_type == "true" else "mean_anomaly_deg"
            _require(getattr(self, anomaly_field) is not None,
                      f"classical_elements orbit with anomaly_type={self.anomaly_type!r} needs {anomaly_field}")
        elif self.type == "cartesian":
            for name in ("position_km", "velocity_km_s"):
                value = getattr(self, name)
                _require(value is not None and len(value) == 3,
                          f"cartesian orbit needs {name} as a 3-element [x, y, z] list")
        elif self.type == "tle":
            _require(bool(self.tle_line1) and bool(self.tle_line2),
                      "tle orbit needs both tle_line1 and tle_line2")


@dataclass
class SensorConfig:
    """One sensor instance. ``kind`` is one of :data:`SUPPORTED_SENSOR_KINDS`
    (see the capability matrix for which Basilisk module each one maps to:
    ``starTracker``, ``imuSensor``, ``coarseSunSensor``, ``magnetometer``).
    ``params`` is an open dict of module-specific settings (noise std devs,
    mounting direction, ...) -- kept generic here rather than one dataclass
    per sensor type so new sensor kinds can be added without another schema
    migration; :meth:`SpacecraftConfig.validate` checks the kind-specific
    params it can check early (e.g. ``coarse_sun_sensor`` needs ``nHat_B``).

    ``simpleNav`` (the truth-to-navigation-message bridge every FSW mode
    needs) is deliberately NOT a selectable sensor kind here: engine.service
    creates exactly one automatically for any spacecraft with ``fsw_mode``
    set, since every FSW guidance mode needs it and it is not itself a
    piece of hardware the user configures.
    """

    kind: str
    name: str
    params: dict = field(default_factory=dict)


@dataclass
class ActuatorConfig:
    """One actuator instance. ``kind`` is one of
    :data:`SUPPORTED_ACTUATOR_KINDS`. See :class:`SensorConfig` for why
    ``params`` is an open dict, and the module-level note above
    :data:`SUPPORTED_ACTUATOR_KINDS` for why ``"thruster"``/
    ``"magnetic_torque_rod"`` are accepted here but rejected by
    engine.service at run time.
    """

    kind: str
    name: str
    params: dict = field(default_factory=dict)


@dataclass
class PowerConfig:
    """A spacecraft's power budget: a body-fixed solar panel, a constant
    "bus" housekeeping load, and a battery -- Basilisk's real
    ``simpleSolarPanel``/``simplePowerSink``/``simpleBattery`` modules
    (see ``engine.service``, ported from the same wiring pattern
    ``../missionAnalysis/power_budget.py`` already uses), not an
    analytical estimate: generated power depends on the scenario's actual
    simulated attitude (panel-normal-to-sun angle) and eclipse state, so
    this needs a spacecraft's orbit to actually pass through sunlight and
    shadow -- there is no separate "power budget mode" to turn on beyond
    setting this field. ``None`` (the default) means no power budget is
    simulated for that spacecraft at all, matching every scenario written
    before this field existed.
    """

    panel_area_m2: float  # [m^2] total deployed solar panel area
    panel_efficiency: float  # [-] fraction of incident solar power converted to electrical power, 0 < x <= 1
    panel_normal_b: list = field(default_factory=lambda: [0.0, 0.0, 1.0])  # body-frame unit vector
    bus_idle_power_w: float = 0.0  # [W] constant always-on avionics/thermal/ADCS housekeeping load
    battery_capacity_wh: float = 100.0  # [W*hr]
    battery_initial_soc: float = 1.0  # [-] initial state of charge, fraction of capacity, 0 <= x <= 1

    def validate(self, spacecraft_name: str) -> None:
        _require(self.panel_area_m2 > 0, f"{spacecraft_name}: power.panel_area_m2 must be > 0")
        _require(0.0 < self.panel_efficiency <= 1.0,
                  f"{spacecraft_name}: power.panel_efficiency must be in (0, 1]")
        _require(len(self.panel_normal_b) == 3,
                  f"{spacecraft_name}: power.panel_normal_b must be a 3-element [x, y, z] list")
        _require(self.bus_idle_power_w >= 0, f"{spacecraft_name}: power.bus_idle_power_w must be >= 0")
        _require(self.battery_capacity_wh > 0, f"{spacecraft_name}: power.battery_capacity_wh must be > 0")
        _require(0.0 <= self.battery_initial_soc <= 1.0,
                  f"{spacecraft_name}: power.battery_initial_soc must be in [0, 1]")


@dataclass
class RFLinkConfig:
    """A spacecraft's downlink transmitter, for a reported link-margin
    ESTIMATE only (``engine.link_budget``) -- a simplified free-space-path
    -loss Eb/N0 budget (no atmosphere/rain/pointing-loss/coding-gain
    terms), ported directly from ``../missionAnalysis``'s
    ``run_constellation_mission.py::_rf_link_margin_db()``. It is evaluated
    against the real simulated slant range from ``engine.service``'s
    ground-station access analysis, but it does NOT feed back into the
    simulated physics anywhere (no data-rate/duty-cycle simulation) --
    see :class:`PowerConfig` for what IS actually simulated. ``None`` (the
    default) means no link margin is computed for that spacecraft.
    """

    tx_power_w: float  # [W] downlink transmitter RF output power
    frequency_hz: float  # [Hz] downlink carrier frequency
    data_rate_bps: float  # [bit/s] downlink data rate
    tx_antenna_gain_dbi: float = 0.0  # [dBi] spacecraft downlink antenna gain
    implementation_loss_db: float = 2.0  # [dB] combined pointing/polarization/implementation loss
    required_ebno_db: float = 6.0  # [dB] required Eb/N0 for the assumed modulation/coding

    def validate(self, spacecraft_name: str) -> None:
        _require(self.tx_power_w > 0, f"{spacecraft_name}: rf_link.tx_power_w must be > 0")
        _require(self.frequency_hz > 0, f"{spacecraft_name}: rf_link.frequency_hz must be > 0")
        _require(self.data_rate_bps > 0, f"{spacecraft_name}: rf_link.data_rate_bps must be > 0")
        _require(self.implementation_loss_db >= 0,
                  f"{spacecraft_name}: rf_link.implementation_loss_db must be >= 0")


@dataclass
class StationKeepingConfig:
    """Automated altitude/semi-major-axis station-keeping for one
    spacecraft, with delta-V and propellant bookkeeping
    (``engine.orbit_maintenance``, ported from
    ``../missionAnalysis``'s ``AltitudeKeepingController``): fires a
    continuous low-thrust reboost burn (prograde, along the inertial
    velocity direction) whenever a smoothed altitude estimate decays past
    ``deadband_km`` below ``target_altitude_km``, holding the burn until
    altitude is restored -- simple deadband/hysteresis control, gated off
    during eclipse (approximates a solar-electric bus that can't run the
    thruster off battery alone) and inhibited once propellant is
    depleted. Propellant use is tracked via the rocket equation and fed
    back into the spacecraft's simulated mass every tick, so thrust-to
    -mass stays physically consistent as propellant burns off -- see
    ``SpacecraftConfig.dry_mass_kg``'s docstring for how that interacts
    with ``propellant_kg`` below.

    This assumes something is actually decaying the orbit -- with only
    point-mass gravity (this schema's default), altitude never decays and
    the burn simply never fires. Enable atmospheric drag
    (``SpacecraftConfig.enable_drag``) for this to have any effect.
    ``None`` (the default) means no station-keeping is simulated for that
    spacecraft.
    """

    target_altitude_km: float  # [km] altitude above the central body's equatorial radius to maintain
    deadband_km: float  # [km] how far below target_altitude_km before a reboost burn starts
    thrust_n: float  # [N] reboost thruster thrust
    isp_s: float  # [s] reboost thruster specific impulse
    propellant_kg: float  # [kg] initial propellant mass available for station-keeping
    eclipse_sunlit_threshold: float = 0.99  # [-] shadow factor above which the spacecraft is treated as sunlit

    def validate(self, spacecraft_name: str) -> None:
        _require(self.target_altitude_km > 0, f"{spacecraft_name}: station_keeping.target_altitude_km must be > 0")
        _require(0.0 < self.deadband_km < self.target_altitude_km,
                  f"{spacecraft_name}: station_keeping.deadband_km must be > 0 and < target_altitude_km")
        _require(self.thrust_n > 0, f"{spacecraft_name}: station_keeping.thrust_n must be > 0")
        _require(self.isp_s > 0, f"{spacecraft_name}: station_keeping.isp_s must be > 0")
        _require(self.propellant_kg >= 0, f"{spacecraft_name}: station_keeping.propellant_kg must be >= 0")
        _require(0.0 < self.eclipse_sunlit_threshold <= 1.0,
                  f"{spacecraft_name}: station_keeping.eclipse_sunlit_threshold must be in (0, 1]")


SUPPORTED_THRUST_FRAMES = ("VNB", "RTN")


@dataclass
class ConstantThrustConfig:
    """Continuous (always-on), constant-magnitude thrust with a fixed
    DIRECTION IN A ROTATING FRAME (``frame``: ``"VNB"`` -- velocity/orbit
    -normal/binormal -- or ``"RTN"`` -- radial/transverse/orbit-normal;
    see ``engine.orbit_maintenance``'s ``_vnb_basis``/``_rtn_basis`` for
    the exact axis definitions), with delta-V and propellant bookkeeping
    (same rocket-equation approach as ``StationKeepingConfig`` -- see that
    class's docstring). Built for
    :data:`Scenario.simulation_mode`\\ 's ``"orbit_only"`` use case: a
    delta-V/propellant budget for a maneuver whose direction is defined
    relative to the orbit (e.g. always-prograde, or a fixed out-of-plane
    component) rather than needing any attitude model to point a specific
    body axis -- an INERTIALLY-fixed thrust direction would drift
    relative to the orbit as the spacecraft moves, which is why this is
    VNB/RTN-relative, re-evaluated every simulation tick from the
    spacecraft's current state, not a fixed inertial vector.

    Independent of ``StationKeepingConfig`` -- both may be set on the same
    spacecraft (separate propellant budgets/tanks, unlike
    ``StationKeepingConfig``/``PhasingKeepingConfig``'s deliberately
    shared one -- see ``PhasingKeepingConfig``'s docstring for that case)
    and not restricted to orbit-only mode; a full-attitude scenario can
    use this too if a simple always-on maneuver (rather than an
    altitude-deadband-triggered one) is what's wanted.

    ``None`` (the default) means no constant-frame thrust is simulated for
    that spacecraft.
    """

    frame: str = "VNB"  # one of SUPPORTED_THRUST_FRAMES
    direction: list = field(default_factory=lambda: [1.0, 0.0, 0.0])  # unit vector in `frame` [-]
    thrust_n: float = 0.01  # [N]
    isp_s: float = 1500.0  # [s]
    propellant_kg: float = 2.0  # [kg] initial propellant mass available

    def validate(self, spacecraft_name: str) -> None:
        _require(self.frame in SUPPORTED_THRUST_FRAMES,
                  f"{spacecraft_name}: constant_thrust.frame {self.frame!r} must be one of "
                  f"{SUPPORTED_THRUST_FRAMES}")
        _require(len(self.direction) == 3, f"{spacecraft_name}: constant_thrust.direction must have 3 elements")
        _require(any(abs(v) > 1e-12 for v in self.direction),
                  f"{spacecraft_name}: constant_thrust.direction must not be the zero vector")
        _require(self.thrust_n > 0, f"{spacecraft_name}: constant_thrust.thrust_n must be > 0")
        _require(self.isp_s > 0, f"{spacecraft_name}: constant_thrust.isp_s must be > 0")
        _require(self.propellant_kg >= 0, f"{spacecraft_name}: constant_thrust.propellant_kg must be >= 0")


@dataclass
class PhasingKeepingConfig:
    """Constellation-wide phasing maintenance: holds this (follower)
    spacecraft's along-track separation from a ``chief_spacecraft`` at a
    target value via a drift-orbit maneuver (a temporary semi-major-axis
    offset, natural drift, then a restoring burn) --
    ``engine.orbit_maintenance.PhasingKeepingController``, ported from
    ``../missionAnalysis``'s controller of the same name. Built for
    exactly the constellations ``engine.constellation`` generates (a set
    of co-planar, same-altitude satellites), but works for any two
    spacecraft sharing an orbital plane and altitude.

    Requires ``station_keeping`` to ALSO be set on this same spacecraft:
    phasing and altitude-keeping share ONE physical thruster and
    propellant tank (this config deliberately has no
    ``thrust_n``/``isp_s``/``propellant_kg`` fields of its own --
    ``engine.service`` reads those from ``station_keeping`` instead, so
    there is no way for the two to accidentally disagree about the same
    hardware), with altitude-keeping taking priority whenever both want to
    fire on the same tick -- see the controller's own docstring for why.

    ``target_separation_km`` is one or more along-track distances [km]
    ahead of the chief; with more than one entry, the target steps through
    them every ``reconfiguration_interval_days`` (holding at the last one
    once the list is exhausted) -- e.g. ``[1000, 500, 100]`` with
    ``reconfiguration_interval_days=90`` tightens the formation baseline
    roughly every 3 months. A single entry holds that separation for the
    whole mission. The remaining fields are maneuver-tuning knobs with
    reasonable ported defaults (``../missionAnalysis/mission_config.py``)
    -- widen ``tolerance_fraction``/``restore_tolerance_fraction`` for
    fewer, larger corrections, or narrow them for tighter formation
    -keeping at the cost of more frequent burns; there is no single
    "correct" answer, it depends on the mission's own ops concept.

    Caveat found by a real crash investigation: give this spacecraft's
    (and its ``chief_spacecraft``'s) orbit a small, deliberate, NONZERO
    ``eccentricity`` (e.g. ``0.001``) rather than exactly ``0.0``.
    ``engine.orbit_maintenance.PhasingKeepingController`` measures each
    spacecraft's along-track phase via ``orbitalMotion.rv2elem()``, which
    only trusts its stable near-circular formula below ``e < 1e-11`` --
    a genuinely circular scenario's real, propagated eccentricity (from
    third-body gravity, or this very controller's own commanded thrust)
    can easily drift just above that extremely tight threshold, at which
    point ``rv2elem()`` silently falls back to a formula that is
    numerically meaningless that close to zero eccentricity, feeding a
    garbage phasing error into this controller. See
    ``missionStudio/HISTORY.md``'s "Template '05' crash" writeups for the
    full investigation (bundled template ``05_formation_flying_phasing``
    hit exactly this and was fixed the same way).
    """

    chief_spacecraft: str
    target_separation_km: list  # [km] one or more along-track distances ahead of the chief
    reconfiguration_interval_days: float = 90.0  # [day] only matters if target_separation_km has >1 entry
    tolerance_fraction: float = 0.10  # [-] trigger threshold, as a fraction of the current target separation
    restore_tolerance_fraction: float = 0.02  # [-] "close enough, stop drifting" threshold, same units
    correction_window_days: float = 21.0  # [day] target time to null a fresh phasing error
    max_drift_days: float = 90.0  # [day] safety cap on the drift coast phase
    max_delta_semi_major_axis_km: float = 3.0  # [km] safety clamp on the drift-orbit SMA offset

    def validate(self, spacecraft_name: str) -> None:
        _require(bool(self.chief_spacecraft),
                  f"{spacecraft_name}: phasing_keeping.chief_spacecraft must not be empty")
        _require(self.chief_spacecraft != spacecraft_name,
                  f"{spacecraft_name}: phasing_keeping.chief_spacecraft cannot be the spacecraft itself")
        _require(len(self.target_separation_km) >= 1,
                  f"{spacecraft_name}: phasing_keeping.target_separation_km needs at least one entry")
        _require(all(d > 0 for d in self.target_separation_km),
                  f"{spacecraft_name}: phasing_keeping.target_separation_km entries must all be > 0")
        _require(self.reconfiguration_interval_days >= 0,
                  f"{spacecraft_name}: phasing_keeping.reconfiguration_interval_days must be >= 0")
        _require(0.0 < self.tolerance_fraction,
                  f"{spacecraft_name}: phasing_keeping.tolerance_fraction must be > 0")
        _require(0.0 < self.restore_tolerance_fraction,
                  f"{spacecraft_name}: phasing_keeping.restore_tolerance_fraction must be > 0")
        _require(self.correction_window_days > 0,
                  f"{spacecraft_name}: phasing_keeping.correction_window_days must be > 0")
        _require(self.max_drift_days > 0,
                  f"{spacecraft_name}: phasing_keeping.max_drift_days must be > 0")
        _require(self.max_delta_semi_major_axis_km > 0,
                  f"{spacecraft_name}: phasing_keeping.max_delta_semi_major_axis_km must be > 0")


@dataclass
class MomentumDumpingConfig:
    """Periodic reaction-wheel momentum desaturation via this spacecraft's
    ``"thruster"`` actuators -- Basilisk's ``thrMomentumManagement`` +
    ``thrForceMapping`` (momentum-dump mode) + ``thrMomentumDumping``,
    firing thrusters ONLY to bleed off accumulated wheel momentum, never
    for primary attitude control (that stays on ``"reaction_wheel"``
    actuators via the existing control path -- see ``engine.fsw``'s
    module docstring for why the two would otherwise need a control
    -allocation module this app doesn't build).

    Requires BOTH ``"reaction_wheel"`` actuators AND ``"thruster"``
    actuators configured on this same spacecraft: reaction wheels for
    the control they're already doing, thrusters as the desaturation
    hardware. ``SpacecraftConfig.validate()`` otherwise REJECTS mixing
    the two actuator kinds on one spacecraft (see that method) -- this
    is the one case where mixing them is well-defined and required,
    since the two are not competing for the same torque authority.

    ``hs_max`` is the total reaction-wheel angular-momentum magnitude
    [N*m*s] that triggers a desaturation burn; a spacecraft with
    :class:`ActuatorConfig` ``"reaction_wheel"`` entries carrying
    ``maxMomentum`` params should typically set this somewhat below the
    sum of those wheels' capacities, so desaturation fires before any
    wheel actually saturates, not after.

    ``None`` (the default) means no desaturation is simulated -- reaction
    wheels accumulate momentum indefinitely for the whole run, exactly as
    before this feature existed.
    """

    hs_max: float  # [N*m*s] total RW angular momentum magnitude that triggers desaturation
    thr_min_fire_time: float = 0.02  # [s] thruster firing pulse resolution
    max_counter_value: int = 100  # [-] control periods to wait between desaturation firings

    def validate(self, spacecraft_name: str) -> None:
        _require(self.hs_max > 0, f"{spacecraft_name}: momentum_dumping.hs_max must be > 0")
        _require(self.thr_min_fire_time > 0, f"{spacecraft_name}: momentum_dumping.thr_min_fire_time must be > 0")
        _require(self.max_counter_value >= 1, f"{spacecraft_name}: momentum_dumping.max_counter_value must be >= 1")


@dataclass
class MagneticMomentumManagementConfig:
    """Continuous reaction-wheel momentum management via this
    spacecraft's ``"magnetic_torque_rod"`` actuators -- Basilisk's
    ``mtbMomentumManagement``, a materially different strategy from
    :class:`MomentumDumpingConfig`'s thruster-based threshold-and-burst
    approach: rather than waiting for total momentum to cross a
    threshold and firing a discrete pulse, this continuously biases the
    commanded RW motor torque (sitting between ``rwMotorTorque`` and the
    RW hardware) so each wheel's speed is driven toward its own entry in
    ``wheel_speed_biases_rad_s``, using whatever magnetic torque the
    real geomagnetic field (Basilisk's WMM model) allows at the
    spacecraft's current position -- see ``examples/scenarioMtbMomentumManagement.py``,
    the real, shipped example this is built from.

    The two desaturation strategies are mutually exclusive alternatives
    (different actuator hardware, different control law) -- a spacecraft
    uses one or the other, never both.

    Requires BOTH ``"reaction_wheel"`` actuators AND
    ``"magnetic_torque_rod"`` actuators configured on this same
    spacecraft (mirroring :class:`MomentumDumpingConfig`'s own
    requirement), and ``gravity.central_body == "earth"`` (Basilisk's
    WMM magnetic field model is Earth-only, same restriction as a
    ``"magnetometer"`` sensor -- see ``engine.fsw``'s module docstring).
    That central-body check happens at the engine layer when the
    scenario actually runs (not here), matching this schema's existing
    precedent for the same Earth-only WMM restriction on magnetometer
    sensors.

    ``wheel_speed_biases_rad_s`` needs exactly one entry per
    ``"reaction_wheel"`` actuator on this spacecraft, in the same order
    those actuators are listed -- Basilisk's ``mtbMomentumManagement``
    maps them positionally, not by name. ``None`` (the default) means no
    magnetic momentum management is simulated -- reaction wheels
    accumulate momentum indefinitely, exactly as before this feature
    existed.
    """

    wheel_speed_biases_rad_s: list  # [rad/s] one entry per reaction_wheel actuator, in listed order
    c_gain: float = 0.003  # [-] control gain mapping wheel speed error to desired magnetic torque

    def validate(self, spacecraft_name: str, num_reaction_wheels: int) -> None:
        _require(len(self.wheel_speed_biases_rad_s) == num_reaction_wheels,
                  f"{spacecraft_name}: magnetic_momentum_management.wheel_speed_biases_rad_s needs exactly "
                  f"{num_reaction_wheels} entries (one per reaction_wheel actuator), got "
                  f"{len(self.wheel_speed_biases_rad_s)}")
        _require(self.c_gain > 0, f"{spacecraft_name}: magnetic_momentum_management.c_gain must be > 0")


@dataclass
class SpacecraftConfig:
    name: str
    orbit: OrbitIC
    # [kg] The spacecraft's mass WITHOUT station-keeping propellant. With
    # station_keeping unset (the default), this is simply the whole
    # spacecraft's simulated mass, exactly as before StationKeepingConfig
    # existed. With station_keeping set, engine.service initializes the
    # simulated mass to dry_mass_kg + station_keeping.propellant_kg, and
    # the station-keeping controller depletes it back toward dry_mass_kg
    # as propellant burns -- see StationKeepingConfig's docstring.
    dry_mass_kg: float = 100.0
    inertia_kg_m2: list = field(default_factory=lambda: [10.0, 0.0, 0.0, 0.0, 10.0, 0.0, 0.0, 0.0, 10.0])
    sigma_bn_init: list = field(default_factory=lambda: [0.0, 0.0, 0.0])
    omega_bn_b_init_rad_s: list = field(default_factory=lambda: [0.0, 0.0, 0.0])

    # Perturbations -- Phase 0's service only ever consumes central-body
    # gravity; these flags are validated/round-tripped now and read starting
    # Phase 1, matching the "reserve the shape, don't wire it all up yet" note.
    enable_drag: bool = False
    drag_coeff: float = 2.2
    drag_area_m2: float = 1.0
    enable_srp: bool = False
    srp_coeff: float = 1.3
    srp_area_m2: float = 1.0

    # Torque from the central body's (and, if present, any third-body
    # perturber's) gravity gradient across the spacecraft's own mass
    # distribution -- Basilisk's real GravityGradientEffector, not an
    # approximation: it reads the spacecraft's actual simulated inertia/
    # position/attitude every tick (see engine.service), so it stays
    # correct through inertia changes (e.g. FuelTank depletion, once that
    # exists) rather than being computed once from initial conditions.
    # Negligible in LEO for an actively-controlled spacecraft (the RW/MRP
    # feedback loop simply rejects it as one more disturbance torque), but
    # real for anything coasting without active control (fsw_mode=None) or
    # in a large/elongated inertia configuration -- exactly the case this
    # schema previously had no way to model at all. False by default:
    # every scenario written before this field existed keeps its exact
    # previous dynamics.
    enable_gravity_gradient: bool = False

    sensors: list = field(default_factory=list)  # list[SensorConfig]
    actuators: list = field(default_factory=list)  # list[ActuatorConfig]
    # One of SUPPORTED_FSW_MODES, or None for no attitude control (attitude
    # still integrates -- see engine.service -- it just isn't commanded).
    fsw_mode: Optional[str] = None
    # Mode-specific settings engine.fsw needs to build the guidance chain,
    # e.g. {"sigma_R0N": [...]} for "inertial3D" or
    # {"target_ground_station": "dsn-goldstone", "pHat_B": [0, 0, 1]} for
    # "locationPointing" -- see engine/fsw.py's per-mode builder docstrings
    # for the full set each mode reads.
    fsw_params: dict = field(default_factory=dict)
    # {"K": ..., "P": ...} MRP feedback control gains; see
    # engine.fsw.DEFAULT_MRP_GAINS for the defaults used when a key is absent.
    control_params: dict = field(default_factory=dict)

    power: Optional[PowerConfig] = None
    rf_link: Optional[RFLinkConfig] = None
    station_keeping: Optional[StationKeepingConfig] = None
    phasing_keeping: Optional[PhasingKeepingConfig] = None
    constant_thrust: Optional[ConstantThrustConfig] = None
    momentum_dumping: Optional[MomentumDumpingConfig] = None
    magnetic_momentum_management: Optional[MagneticMomentumManagementConfig] = None

    # Phase 5: PURELY COSMETIC Vizard display -- replaces this spacecraft's
    # default cube icon with a custom CAD model
    # (Basilisk.utilities.vizSupport.createCustomModel()). Never affects
    # simulated physics: mass properties, drag/SRP area, etc. still come
    # from dry_mass_kg/inertia_kg_m2/drag_area_m2/srp_area_m2 above, same
    # as when this is unset. None (the default) leaves Vizard's own
    # default icon in place.
    vizard_model_path: Optional[str] = None  # path to a .obj file, or "CUBE"/"CYLINDER"/"SPHERE"
    vizard_model_offset_m: list = field(default_factory=lambda: [0.0, 0.0, 0.0])
    vizard_model_rotation_deg: list = field(default_factory=lambda: [0.0, 0.0, 0.0])  # 3-2-1 Euler (z,y,x)
    vizard_model_scale: list = field(default_factory=lambda: [1.0, 1.0, 1.0])

    def validate(self) -> None:
        _require(bool(self.name), "spacecraft.name must not be empty")
        _require(self.dry_mass_kg > 0, f"{self.name}: dry_mass_kg must be > 0")
        _require(len(self.inertia_kg_m2) == 9, f"{self.name}: inertia_kg_m2 must have 9 elements (3x3, row-major)")
        _require(len(self.sigma_bn_init) == 3, f"{self.name}: sigma_bn_init must have 3 elements")
        _require(len(self.omega_bn_b_init_rad_s) == 3, f"{self.name}: omega_bn_b_init_rad_s must have 3 elements")
        self.orbit.validate()

        _require(self.fsw_mode is None or self.fsw_mode in SUPPORTED_FSW_MODES,
                  f"{self.name}: fsw_mode {self.fsw_mode!r} must be None or one of {SUPPORTED_FSW_MODES}")
        if self.fsw_mode == "locationPointing":
            has_gs = bool(self.fsw_params.get("target_ground_station"))
            has_body = bool(self.fsw_params.get("target_body"))
            _require(has_gs != has_body,  # xor: exactly one target
                      f"{self.name}: fsw_mode 'locationPointing' needs exactly one of "
                      "fsw_params['target_ground_station'] or fsw_params['target_body']")
        if self.fsw_mode == "sunSafePoint" and self.fsw_params.get("use_css_estimation"):
            _require(any(s.kind == "coarse_sun_sensor" for s in self.sensors),
                      f"{self.name}: fsw_params['use_css_estimation'] is set but this spacecraft has no "
                      "'coarse_sun_sensor' sensors to estimate sun-heading from")

        sensor_names = [s.name for s in self.sensors]
        _require(len(sensor_names) == len(set(sensor_names)),
                  f"{self.name}: sensor names must be unique, got {sensor_names}")
        for sensor in self.sensors:
            _require(bool(sensor.kind) and bool(sensor.name), f"{self.name}: every sensor needs kind and name")
            _require(sensor.kind in SUPPORTED_SENSOR_KINDS,
                      f"{self.name}: sensor {sensor.name!r} kind {sensor.kind!r} must be one of "
                      f"{SUPPORTED_SENSOR_KINDS}")
            if sensor.kind == "coarse_sun_sensor":
                nHat_B = sensor.params.get("nHat_B")
                _require(nHat_B is not None and len(nHat_B) == 3,
                          f"{self.name}: coarse_sun_sensor {sensor.name!r} needs params['nHat_B'] "
                          "as a 3-element body-frame boresight unit vector")

        actuator_names = [a.name for a in self.actuators]
        _require(len(actuator_names) == len(set(actuator_names)),
                  f"{self.name}: actuator names must be unique, got {actuator_names}")
        for actuator in self.actuators:
            _require(bool(actuator.kind) and bool(actuator.name), f"{self.name}: every actuator needs kind and name")
            _require(actuator.kind in SUPPORTED_ACTUATOR_KINDS,
                      f"{self.name}: actuator {actuator.name!r} kind {actuator.kind!r} must be one of "
                      f"{SUPPORTED_ACTUATOR_KINDS}")
            if actuator.kind == "reaction_wheel":
                gsHat_B = actuator.params.get("gsHat_B")
                _require(gsHat_B is not None and len(gsHat_B) == 3,
                          f"{self.name}: reaction_wheel {actuator.name!r} needs params['gsHat_B'] "
                          "as a 3-element body-frame spin-axis unit vector")
                rw_type = actuator.params.get("rw_type", "custom")
                if rw_type == "custom":
                    # Confirmed directly against simIncludeRW.py's rwFactory.create(): the
                    # "custom" type's own method (unlike every named hardware type, e.g.
                    # "Honeywell_HR16") does nothing -- it relies entirely on these two
                    # kwargs. Missing either one makes rwFactory.create() call exit(1)
                    # directly (not a raised exception) -- which kills the whole
                    # missionStudio process with no traceback, not just this one
                    # simulation run -- so this schema requires them explicitly instead
                    # of ever reaching that call with a bare rw_type="custom".
                    has_u_max_guard = (actuator.params.get("u_max") is not None
                                       or actuator.params.get("useMaxTorque") is False)
                    _require(has_u_max_guard,
                              f"{self.name}: reaction_wheel {actuator.name!r} uses rw_type='custom' (the "
                              "default) but has no params['u_max'] [N*m] -- rwFactory.create() hard-exits "
                              "the whole process (not a catchable error) on a non-positive u_max for a "
                              "default-saturating custom wheel; set params['u_max'], set "
                              "params['useMaxTorque']=False, or use a named params['rw_type'] (e.g. "
                              "'Honeywell_HR16') with its own built-in default instead")
                    has_inertia = (actuator.params.get("Js") is not None
                                   or (actuator.params.get("Omega_max") is not None
                                       and actuator.params.get("maxMomentum") is not None))
                    _require(has_inertia,
                              f"{self.name}: reaction_wheel {actuator.name!r} uses rw_type='custom' (the "
                              "default) but has no params['Js'] [kg*m^2] (spin-axis inertia) and no "
                              "params['Omega_max']+params['maxMomentum'] pair to derive it from -- "
                              "rwFactory.create() cannot build this wheel's inertia without one of those; "
                              "set one, or use a named params['rw_type'] with its own built-in default")
                    # Confirmed directly against simIncludeRW.py: giving Js
                    # AND the Omega_max+maxMomentum pair together is a
                    # SEPARATE exit(1) hard-crash (rwFactory.create() builds
                    # the wheel's inertia exactly one way, never both) --
                    # found by exactly this combination in a real, already
                    # -shipped params dict (engine.spacecraft_templates.py's
                    # _RW_EXAMPLE_PARAMS, fixed alongside this check).
                    _require(not (actuator.params.get("Js") is not None
                                  and actuator.params.get("Omega_max") is not None
                                  and actuator.params.get("maxMomentum") is not None),
                              f"{self.name}: reaction_wheel {actuator.name!r} uses rw_type='custom' (the "
                              "default) with params['Js'] AND both params['Omega_max']/params['maxMomentum'] "
                              "set -- rwFactory.create() hard-exits the whole process because it builds this "
                              "wheel's inertia exactly one way, never both; remove params['Js'] (let it be "
                              "derived from Omega_max/maxMomentum) or remove the Omega_max/maxMomentum pair")
            if actuator.kind == "thruster":
                r_B = actuator.params.get("r_B")
                _require(r_B is not None and len(r_B) == 3,
                          f"{self.name}: thruster {actuator.name!r} needs params['r_B'] as a 3-element "
                          "body-frame location [m]")
                tHat_B = actuator.params.get("tHat_B")
                _require(tHat_B is not None and len(tHat_B) == 3,
                          f"{self.name}: thruster {actuator.name!r} needs params['tHat_B'] as a 3-element "
                          "body-frame thrust-direction unit vector [-]")
                _require(actuator.params.get("MaxThrust") is not None,
                          f"{self.name}: thruster {actuator.name!r} needs params['MaxThrust'] [N] -- "
                          "simIncludeThruster.thrusterFactory()'s own default (0.2 N) is easy to mistake "
                          "for a wiring bug rather than a deliberately tiny thruster, so this schema "
                          "requires it explicitly rather than silently falling back to it")
            if actuator.kind == "magnetic_torque_rod":
                gtHat_B = actuator.params.get("gtHat_B")
                _require(gtHat_B is not None and len(gtHat_B) == 3,
                          f"{self.name}: magnetic_torque_rod {actuator.name!r} needs params['gtHat_B'] as a "
                          "3-element body-frame dipole-axis unit vector [-]")
                _require(actuator.params.get("max_dipole_a_m2") is not None,
                          f"{self.name}: magnetic_torque_rod {actuator.name!r} needs params['max_dipole_a_m2'] "
                          "[A*m^2] (maximum commandable dipole magnitude)")

        # engine.fsw/engine.service build exactly one PRIMARY control-torque
        # path per spacecraft (reaction wheels via rwMotorTorque, OR
        # thrusters via thrForceMapping/thrFiringSchmitt) -- mixing both for
        # primary control would need a control-allocation module (e.g.
        # Basilisk's torqueScheduler) this app does not build yet. The one
        # exception is momentum_dumping (below), where thrusters have a
        # DIFFERENT, non-competing job (bleeding off RW momentum, not
        # attitude control) -- so the mix is required there, not rejected.
        actuator_kinds_present = {a.kind for a in self.actuators}
        if (self.momentum_dumping is None
                and "reaction_wheel" in actuator_kinds_present and "thruster" in actuator_kinds_present):
            _require(False,
                      f"{self.name}: actuators mix 'reaction_wheel' and 'thruster' kinds -- only one control "
                      "-torque actuator type per spacecraft is simulated (unless momentum_dumping is set, which "
                      "requires exactly this mix); remove one kind's actuators, or set momentum_dumping")
        # "magnetic_torque_rod" has no PRIMARY attitude-control role in this
        # app at all (no B-dot-style detumble/pointing controller is built
        # -- see engine.fsw's module docstring) -- its only simulated job is
        # magnetic_momentum_management's continuous RW desaturation, so a
        # magnetic_torque_rod actuator with that config unset would simply
        # never receive a command.
        if "magnetic_torque_rod" in actuator_kinds_present:
            _require(self.magnetic_momentum_management is not None,
                      f"{self.name}: 'magnetic_torque_rod' actuators need magnetic_momentum_management set "
                      "(no other role for them is simulated); set it, or remove the magnetic_torque_rod "
                      "actuator(s)")

        if self.power is not None:
            self.power.validate(self.name)
        if self.rf_link is not None:
            self.rf_link.validate(self.name)
        if self.station_keeping is not None:
            self.station_keeping.validate(self.name)
        if self.phasing_keeping is not None:
            _require(self.station_keeping is not None,
                      f"{self.name}: phasing_keeping requires station_keeping to also be set on this spacecraft "
                      "-- they share one physical thruster/propellant tank (see PhasingKeepingConfig's docstring)")
            self.phasing_keeping.validate(self.name)
        if self.constant_thrust is not None:
            self.constant_thrust.validate(self.name)
        if self.momentum_dumping is not None:
            _require("reaction_wheel" in actuator_kinds_present,
                      f"{self.name}: momentum_dumping needs at least one 'reaction_wheel' actuator (momentum to "
                      "dump) on this spacecraft")
            _require("thruster" in actuator_kinds_present,
                      f"{self.name}: momentum_dumping needs at least one 'thruster' actuator (desaturation "
                      "hardware) on this spacecraft")
            self.momentum_dumping.validate(self.name)
        if self.magnetic_momentum_management is not None:
            _require("reaction_wheel" in actuator_kinds_present,
                      f"{self.name}: magnetic_momentum_management needs at least one 'reaction_wheel' actuator "
                      "(momentum to manage) on this spacecraft")
            _require("magnetic_torque_rod" in actuator_kinds_present,
                      f"{self.name}: magnetic_momentum_management needs at least one 'magnetic_torque_rod' "
                      "actuator (desaturation hardware) on this spacecraft")
            num_reaction_wheels = sum(1 for a in self.actuators if a.kind == "reaction_wheel")
            self.magnetic_momentum_management.validate(self.name, num_reaction_wheels)

        if self.vizard_model_path is not None:
            _require(bool(self.vizard_model_path.strip()), f"{self.name}: vizard_model_path must not be blank")
        _require(len(self.vizard_model_offset_m) == 3, f"{self.name}: vizard_model_offset_m must have 3 elements")
        _require(len(self.vizard_model_rotation_deg) == 3,
                  f"{self.name}: vizard_model_rotation_deg must have 3 elements")
        _require(len(self.vizard_model_scale) == 3, f"{self.name}: vizard_model_scale must have 3 elements")


@dataclass
class GravityConfig:
    central_body: str = "earth"
    central_body_degree: int = 0  # 0 == point-mass only
    third_body_perturbers: list = field(default_factory=list)  # e.g. ["sun", "moon"]

    def validate(self) -> None:
        _require(self.central_body in SUPPORTED_CENTRAL_BODIES,
                  f"gravity.central_body {self.central_body!r} must be one of {SUPPORTED_CENTRAL_BODIES}")
        _require(self.central_body_degree >= 0, "gravity.central_body_degree must be >= 0")
        # engine.service.SimulationService.build() only has spherical
        # -harmonics gravity-field data (GGM03S) for Earth, and raises
        # SimulationServiceError for any other central_body with
        # central_body_degree > 0 -- but that's an engine-layer check that
        # only runs when a scenario is actually simulated. Without this
        # mirrored check here, `missionstudio validate`/`Scenario.save()`
        # (both Basilisk-independent, schema-only) would report a clean
        # bill of health for a scenario guaranteed to fail the moment it's
        # actually run -- defeating the point of an early, engine
        # -independent correctness check.
        _require(self.central_body_degree == 0 or self.central_body == "earth",
                  f"gravity.central_body_degree > 0 (spherical-harmonics gravity) is only wired up for "
                  f"central_body 'earth', not {self.central_body!r} -- set central_body_degree = 0 "
                  f"(point-mass) or central_body = 'earth'")
        for name in self.third_body_perturbers:
            _require(name in SUPPORTED_CENTRAL_BODIES,
                      f"gravity.third_body_perturbers entry {name!r} must be one of {SUPPORTED_CENTRAL_BODIES}")


@dataclass
class GroundStationConfig:
    name: str
    latitude_deg: float
    longitude_deg: float
    altitude_m: float = 0.0
    min_elevation_deg: float = 10.0
    # Receive-side link-budget parameters -- only meaningful for a
    # spacecraft that also has RFLinkConfig set (see engine.link_budget);
    # harmless, unused defaults otherwise.
    rx_antenna_gain_dbi: float = 0.0  # [dBi] ground station receive antenna gain
    system_noise_temp_k: float = 290.0  # [K] ground receiver system noise temperature

    def validate(self) -> None:
        _require(bool(self.name), "ground_station.name must not be empty")
        _require(-90.0 <= self.latitude_deg <= 90.0, f"{self.name}: latitude_deg must be in [-90, 90]")
        _require(-180.0 <= self.longitude_deg <= 180.0, f"{self.name}: longitude_deg must be in [-180, 180]")
        _require(0.0 <= self.min_elevation_deg < 90.0, f"{self.name}: min_elevation_deg must be in [0, 90)")
        _require(self.system_noise_temp_k > 0, f"{self.name}: system_noise_temp_k must be > 0")


@dataclass
class SpaceWeatherConfig:
    """See engine/spaceweather.py and engine/service.py. ``source``
    selects the space-weather resolution strategy; ``local_file_path`` is
    used (and required) only for ``"local_file"``, matching the user's own
    fallback plan ("if fetching isn't possible I'll provide the file
    myself").

    ``atmosphere_model`` selects which Basilisk atmosphere-density model
    ``engine.service`` builds for ``enable_drag`` spacecraft:
    ``"nrlmsise00"`` (the original, only model this project used to wire
    up -- needs the ``source``/``activity_level`` space-weather machinery
    below) or ``"exponential"`` (Basilisk's ``ExponentialAtmosphere``, a
    simple per-planet scale-height model that ignores ``source``/
    ``activity_level``/``local_file_path`` entirely -- no F10.7/Ap
    dependence at all). ``engine.service`` configures it with Basilisk's
    own ``simSetPlanetEnvironment.exponentialAtmosphere()`` helper (the
    same sea-level Earth baseDensity/scaleHeight a real shipped Basilisk
    example, ``examples/scenarioDragDeorbit.py``, uses for its own
    exponential-model deorbit case -- not hand-picked constants). Confirmed
    directly against real Basilisk (a standalone density-recorder run, not
    guessed) that a single sea-level exponential decay under-predicts
    density at typical LEO altitudes by many orders of magnitude compared
    to NRLMSISE-00 -- an inherent limitation of this simple model, not a
    wiring bug: pick ``"exponential"`` for speed/simplicity (e.g. a quick
    order-of-magnitude check with no space-weather dependency), never for
    an accurate drag/decay estimate, which needs ``"nrlmsise00"``. Real
    user question: "why can't I select the
    atmospheric drag model, other tools let me choose Jacchia-Roberts or
    NRLMSISE-00" -- Basilisk (checked directly against its own
    ``src/simulation/environment/`` tree, not assumed) ships exactly
    three atmosphere models: ``MsisAtmosphere`` (NRLMSISE-00),
    ``ExponentialAtmosphere``, and ``TabularAtmosphere`` (a user-supplied
    altitude/density table, not wired up here -- would need a new file
    -upload schema/GUI concept of its own, out of scope for this round).
    There is no Jacchia-Roberts model in Basilisk at all, so that specific
    option genuinely cannot be offered here.

    ``activity_level``/``activity_percentile`` (``"nrlmsise00"`` only --
    ignored for ``"exponential"``) select a CONSERVATIVE, sustained-
    worst-case drag margin instead of the ordinary resolved space-weather
    data: see ``engine.spaceweather``'s own docstring, "Conservative
    ('worst-case') drag margin", for the real user request this
    implements and exactly what it computes.
    """

    source: str = "celestrak"  # "celestrak" | "local_file" | "synthetic"
    local_file_path: Optional[str] = None
    cache_dir: Optional[str] = None  # defaults to engine.spaceweather's own cache dir when None
    atmosphere_model: str = "nrlmsise00"  # "nrlmsise00" | "exponential"
    activity_level: str = "nominal"  # "nominal" | "conservative"
    activity_percentile: float = 95.0  # [-] percentile of REAL historical F10.7/Ap; "conservative" only

    def validate(self) -> None:
        _require(self.source in ("celestrak", "local_file", "synthetic"),
                  f"space_weather.source {self.source!r} must be 'celestrak', 'local_file', or 'synthetic'")
        if self.source == "local_file":
            _require(bool(self.local_file_path),
                      "space_weather.source is 'local_file' but local_file_path was not set")
        _require(self.atmosphere_model in ("nrlmsise00", "exponential"),
                  f"space_weather.atmosphere_model {self.atmosphere_model!r} must be 'nrlmsise00' or 'exponential'")
        _require(self.activity_level in ("nominal", "conservative"),
                  f"space_weather.activity_level {self.activity_level!r} must be 'nominal' or 'conservative'")
        if self.activity_level == "conservative":
            _require(50.0 <= self.activity_percentile < 100.0,
                      "space_weather.activity_percentile must be in [50, 100) when activity_level is "
                      f"'conservative' -- got {self.activity_percentile!r}")


@dataclass
class DispersionConfig:
    """One dispersed quantity for one spacecraft in a Monte Carlo batch --
    see :data:`DISPERSION_QUANTITIES`/:data:`DISPERSION_KINDS_BY_QUANTITY`
    for what's supported and ``engine/monte_carlo.py`` for how each pairing
    maps onto a ``Basilisk.utilities.MonteCarlo.Dispersions`` class.
    """

    spacecraft: str  # must match a SpacecraftConfig.name in this scenario
    quantity: str  # one of DISPERSION_QUANTITIES
    kind: str  # one of DISPERSION_KINDS_BY_QUANTITY[quantity]
    bounds: Optional[list] = None  # [lo, hi]; required for "uniform"/"uniform_euler_mrp"
    mean: Optional[float] = None  # required for "normal"
    std_deviation: Optional[float] = None  # required for "normal"

    def validate(self) -> None:
        _require(bool(self.spacecraft), "dispersion.spacecraft must not be empty")
        _require(self.quantity in DISPERSION_QUANTITIES,
                  f"dispersion.quantity {self.quantity!r} must be one of {DISPERSION_QUANTITIES}")
        allowed_kinds = DISPERSION_KINDS_BY_QUANTITY.get(self.quantity, ())
        _require(self.kind in allowed_kinds,
                  f"dispersion.kind {self.kind!r} for quantity {self.quantity!r} must be one of {allowed_kinds}")
        if self.kind in ("uniform", "uniform_euler_mrp"):
            _require(self.bounds is not None and len(self.bounds) == 2,
                      f"dispersion on {self.spacecraft}.{self.quantity}: kind {self.kind!r} needs "
                      "bounds as a 2-element [lo, hi] list")
        if self.kind == "normal":
            _require(self.mean is not None and self.std_deviation is not None,
                      f"dispersion on {self.spacecraft}.{self.quantity}: kind 'normal' needs "
                      "mean and std_deviation")


@dataclass
class MonteCarloConfig:
    """Batch execution settings -- see ``engine/monte_carlo.py``.
    ``thread_count`` > 1 uses ``multiprocessing.Pool`` under the hood
    (``Basilisk.utilities.MonteCarlo.Controller``); this has NOT been
    exercised in this project's development sandbox (no Basilisk build
    here -- see engine/monte_carlo.py's verification-status note), so the
    default is the conservative, definitely-safe ``1``.
    """

    enabled: bool = False
    num_runs: int = 10
    thread_count: int = 1
    verbose: bool = False
    dispersions: list = field(default_factory=list)  # list[DispersionConfig]

    def validate(self) -> None:
        _require(self.num_runs >= 1, "monte_carlo.num_runs must be >= 1")
        _require(self.thread_count >= 1, "monte_carlo.thread_count must be >= 1")
        for dispersion in self.dispersions:
            dispersion.validate()


# Matches the svIntegrator* classes this Basilisk checkout actually ships
# (src/simulation/dynamics/Integrators/) -- verified by directly listing
# that directory, not assumed. There is deliberately no "rk4" option: this
# checkout has no svIntegratorRK4 (only Euler/RK2 fixed-step and the
# RKF45/RKF78 adaptive pair), and fabricating one here would violate the
# "map every feature to a module Basilisk actually provides" requirement
# this whole project is built around.
SUPPORTED_INTEGRATORS = ("euler", "rk2", "rkf45", "rkf78")


@dataclass
class SimSettings:
    duration_days: float = 1.0
    dynamics_task_rate_s: float = 10.0
    integrator: str = "rkf78"  # see SUPPORTED_INTEGRATORS

    # NOTE: gravity-field degree/order lives on GravityConfig.central_body_degree,
    # not here -- an earlier draft of this schema had a second,
    # SimSettings.earth_grav_degree field that duplicated it, which meant
    # the two could disagree (one saying "point-mass", the other holding a
    # stale nonzero degree) with no validation catching it. Fixed before
    # anything (the GUI, saved scenario files) came to depend on the
    # redundant field -- there is deliberately only one place to set this now.

    def validate(self) -> None:
        _require(self.duration_days > 0, "sim_settings.duration_days must be > 0")
        _require(self.dynamics_task_rate_s > 0, "sim_settings.dynamics_task_rate_s must be > 0")
        _require(self.integrator in SUPPORTED_INTEGRATORS,
                  f"sim_settings.integrator {self.integrator!r} must be one of {SUPPORTED_INTEGRATORS}")


SUPPORTED_SIMULATION_MODES = ("full_attitude", "orbit_only")


@dataclass
class Scenario:
    name: str
    epoch_utc: str  # ISO 8601, e.g. "2030-01-01T00:00:00" -- single source of
    # truth for time; TAI/TT/ET are DERIVED (see engine/time_system.py), never
    # separately stored, so they cannot drift out of sync with epoch_utc.
    # Chosen up front (the GUI's scenario editor puts it at the top of the
    # form, "before starting with anything else" per the feature request
    # this responds to): "full_attitude" (the default, and everything this
    # schema always supported) simulates attitude/sensors/actuators/FSW/
    # power normally. "orbit_only" is a beginner-friendly, deliberately
    # STRICTER mode for pure orbit-propagation questions (delta-V budgets,
    # orbit lifetime, station-keeping cadence, ...) where attitude doesn't
    # matter and modeling it is only friction: no spacecraft may set
    # fsw_mode/sensors/actuators/power in this mode (Scenario.validate()
    # rejects it with a specific error naming the offending spacecraft and
    # field, same "don't let something look configured that isn't" honesty
    # as everywhere else in this schema) -- the spacecraft is simulated as
    # a cannonball with SpacecraftConfig.drag_area_m2/srp_area_m2 as its
    # average cross-section. station_keeping/phasing_keeping/
    # constant_thrust remain available in EITHER mode: none of them need
    # attitude knowledge (their thrust directions are prograde or
    # orbit-frame-relative, not a commanded body axis).
    simulation_mode: str = "full_attitude"
    gravity: GravityConfig = field(default_factory=GravityConfig)
    spacecraft: list = field(default_factory=list)  # list[SpacecraftConfig], >= 1 required
    ground_stations: list = field(default_factory=list)  # list[GroundStationConfig]
    space_weather: SpaceWeatherConfig = field(default_factory=SpaceWeatherConfig)
    sim_settings: SimSettings = field(default_factory=SimSettings)
    monte_carlo: MonteCarloConfig = field(default_factory=MonteCarloConfig)
    # Ordered "Mission Sequence" commands (Propagate/Maneuver/Assignment/
    # Report/If/While/ScriptBlock -- see schema.command.Command), walked in
    # order by engine.mission_engine. Empty (the default) for every
    # scenario written before this field existed, and for any scenario
    # that still just wants "propagate once for sim_settings.duration_days"
    # -- engine.service.SimulationService's existing run()/run_live()
    # behavior is completely unchanged and is still what an empty
    # mission_sequence means; engine.mission_engine is an ADDITIVE,
    # separate execution path only used when this is non-empty.
    mission_sequence: list = field(default_factory=list)  # list[Command]
    description: str = ""
    schema_version: int = CURRENT_SCHEMA_VERSION

    def validate(self) -> None:
        _require(bool(self.name), "scenario.name must not be empty")
        try:
            datetime.fromisoformat(self.epoch_utc)
        except ValueError as exc:
            raise ScenarioValidationError(
                f"scenario.epoch_utc {self.epoch_utc!r} is not a valid ISO 8601 datetime "
                f"(e.g. '2030-01-01T00:00:00'): {exc}"
            ) from exc
        _require(self.simulation_mode in SUPPORTED_SIMULATION_MODES,
                  f"scenario.simulation_mode {self.simulation_mode!r} must be one of {SUPPORTED_SIMULATION_MODES}")
        self.gravity.validate()
        _require(len(self.spacecraft) >= 1, "scenario needs at least one spacecraft")
        names = [sc.name for sc in self.spacecraft]
        _require(len(names) == len(set(names)), f"spacecraft names must be unique, got {names}")
        for sc in self.spacecraft:
            sc.validate()
        if self.simulation_mode == "orbit_only":
            for sc in self.spacecraft:
                _require(sc.fsw_mode is None,
                          f"{sc.name}: fsw_mode is set but scenario.simulation_mode is 'orbit_only' -- attitude "
                          "control needs 'full_attitude' mode, or remove fsw_mode from this spacecraft")
                _require(not sc.sensors,
                          f"{sc.name}: sensors are set but scenario.simulation_mode is 'orbit_only' -- sensors "
                          "need 'full_attitude' mode, or remove them from this spacecraft")
                _require(not sc.actuators,
                          f"{sc.name}: actuators are set but scenario.simulation_mode is 'orbit_only' -- "
                          "actuators need 'full_attitude' mode, or remove them from this spacecraft")
                _require(sc.power is None,
                          f"{sc.name}: power is set but scenario.simulation_mode is 'orbit_only' -- a real solar"
                          "-panel power budget needs the simulated attitude 'full_attitude' mode provides, or "
                          "remove power from this spacecraft")
        gs_names = [gs.name for gs in self.ground_stations]
        _require(len(gs_names) == len(set(gs_names)), f"ground_station names must be unique, got {gs_names}")
        for gs in self.ground_stations:
            gs.validate()
        for sc in self.spacecraft:
            target_gs = sc.fsw_params.get("target_ground_station") if sc.fsw_mode == "locationPointing" else None
            if target_gs is not None:
                _require(target_gs in gs_names,
                          f"{sc.name}: fsw_params['target_ground_station'] {target_gs!r} is not one of "
                          f"this scenario's ground_stations {gs_names}")
        for sc in self.spacecraft:
            if sc.phasing_keeping is not None:
                _require(sc.phasing_keeping.chief_spacecraft in names,
                          f"{sc.name}: phasing_keeping.chief_spacecraft {sc.phasing_keeping.chief_spacecraft!r} "
                          f"is not one of this scenario's spacecraft {names}")
        # engine.service.SimulationService.build() raises a
        # SimulationServiceError for this same condition (power/
        # station_keeping/enable_srp all need the real eclipse shadow
        # factor, which needs a sun ephemeris) -- but that's an
        # engine-layer check that only runs when a scenario is actually
        # simulated. Mirrored here for the same reason
        # GravityConfig.validate() mirrors the central_body_degree/
        # central_body check above: without this, `missionstudio
        # validate`/the GUI's live "valid" indicator would report a
        # clean bill of health for a scenario guaranteed to fail the
        # moment it's actually run (caught for real: two of this
        # project's own bundled templates had exactly this bug).
        needs_sun = any(sc.power is not None or sc.station_keeping is not None or sc.enable_srp
                         for sc in self.spacecraft)
        if needs_sun:
            _require("sun" in self.gravity.third_body_perturbers,
                      "a spacecraft has power, station_keeping, or enable_srp configured, but 'sun' is not "
                      "one of gravity.third_body_perturbers -- simpleSolarPanel/the eclipse gate/SRP all need "
                      "a sun ephemeris. Add 'sun' to gravity.third_body_perturbers, or remove power/"
                      "station_keeping/enable_srp from every spacecraft")
        self.space_weather.validate()
        self.sim_settings.validate()
        self.monte_carlo.validate()
        for dispersion in self.monte_carlo.dispersions:
            _require(dispersion.spacecraft in names,
                      f"monte_carlo dispersion.spacecraft {dispersion.spacecraft!r} is not one of "
                      f"this scenario's spacecraft {names}")

        # Mission sequence (schema.command.Command) -- structural
        # validation only (each command's own .validate() already
        # collects every problem IN that command into one combined
        # message here; raise-fast ACROSS commands, i.e. this stops at
        # the first bad command, same as every other check in this
        # method). schema.validation.validate_all() is the fully
        # -collecting, "every command's every problem" entry point --
        # see that module's docstring for why this method doesn't
        # attempt that itself.
        for i, command in enumerate(self.mission_sequence):
            command_errors = command.validate(f"mission_sequence[{i}]")
            _require(not command_errors, "; ".join(command_errors))
        # local import: schema.references only imports schema.scenario
        # under TYPE_CHECKING (never at runtime), so this has no real
        # import cycle to avoid -- kept local anyway, matching
        # load_scenario()'s own "from . import migrations" precedent, so
        # a future change to that TYPE_CHECKING guard can't silently
        # create one here.
        from .references import _command_references

        for ref in _command_references(self.mission_sequence, "mission_sequence"):
            known = names if ref.resource_kind == "spacecraft" else gs_names
            _require(ref.name in known,
                      f"{ref.path}: {ref.resource_kind} {ref.name!r} is not one of this scenario's "
                      f"{ref.resource_kind}s {sorted(known)}")

    # -- (de)serialization -------------------------------------------------
    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "Scenario":
        data = dict(data)  # shallow copy, don't mutate the caller's dict
        gravity = GravityConfig(**data.pop("gravity", {}))
        sim_settings = SimSettings(**data.pop("sim_settings", {}))
        space_weather = SpaceWeatherConfig(**data.pop("space_weather", {}))
        ground_stations = [GroundStationConfig(**gs) for gs in data.pop("ground_stations", [])]

        mc_data = dict(data.pop("monte_carlo", {}))
        dispersions = [DispersionConfig(**d) for d in mc_data.pop("dispersions", [])]
        monte_carlo = MonteCarloConfig(dispersions=dispersions, **mc_data)

        spacecraft = []
        for sc in data.pop("spacecraft", []):
            sc = dict(sc)
            orbit = OrbitIC(**sc.pop("orbit"))
            sensors = [SensorConfig(**s) for s in sc.pop("sensors", [])]
            actuators = [ActuatorConfig(**a) for a in sc.pop("actuators", [])]
            power_data = sc.pop("power", None)
            power = PowerConfig(**power_data) if power_data is not None else None
            rf_link_data = sc.pop("rf_link", None)
            rf_link = RFLinkConfig(**rf_link_data) if rf_link_data is not None else None
            station_keeping_data = sc.pop("station_keeping", None)
            station_keeping = StationKeepingConfig(**station_keeping_data) if station_keeping_data is not None else None
            phasing_keeping_data = sc.pop("phasing_keeping", None)
            phasing_keeping = PhasingKeepingConfig(**phasing_keeping_data) if phasing_keeping_data is not None else None
            constant_thrust_data = sc.pop("constant_thrust", None)
            constant_thrust = ConstantThrustConfig(**constant_thrust_data) if constant_thrust_data is not None else None
            momentum_dumping_data = sc.pop("momentum_dumping", None)
            momentum_dumping = (
                MomentumDumpingConfig(**momentum_dumping_data) if momentum_dumping_data is not None else None
            )
            magnetic_momentum_management_data = sc.pop("magnetic_momentum_management", None)
            magnetic_momentum_management = (
                MagneticMomentumManagementConfig(**magnetic_momentum_management_data)
                if magnetic_momentum_management_data is not None else None
            )
            spacecraft.append(SpacecraftConfig(orbit=orbit, sensors=sensors, actuators=actuators,
                                                power=power, rf_link=rf_link, station_keeping=station_keeping,
                                                phasing_keeping=phasing_keeping, constant_thrust=constant_thrust,
                                                momentum_dumping=momentum_dumping,
                                                magnetic_momentum_management=magnetic_momentum_management,
                                                **sc))

        mission_sequence = [Command.from_dict(c) for c in data.pop("mission_sequence", [])]

        return Scenario(
            gravity=gravity, sim_settings=sim_settings, space_weather=space_weather,
            ground_stations=ground_stations, spacecraft=spacecraft, monte_carlo=monte_carlo,
            mission_sequence=mission_sequence, **data,
        )

    def save(self, path: "str | Path") -> None:
        self.validate()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n")


def load_scenario(path: "str | Path") -> Scenario:
    """Load, migrate (if needed), and validate a scenario file. Raises
    :class:`ScenarioValidationError` with a specific message on anything
    malformed -- never returns a partially-populated or silently-defaulted
    :class:`Scenario`.
    """
    from . import migrations  # local import: avoids a cycle at module load time

    path = Path(path)
    try:
        text = path.read_text()
    except OSError as exc:
        # Covers a missing file, a directory given by mistake, a
        # permissions error, etc. -- all "can't read this path" failures,
        # not just the literal FileNotFoundError case.
        raise ScenarioValidationError(f"{path}: could not read file ({exc.strerror or exc})") from exc
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ScenarioValidationError(f"{path}: not valid JSON ({exc})") from exc

    if not isinstance(raw, dict) or "schema_version" not in raw:
        raise ScenarioValidationError(f"{path}: missing required top-level 'schema_version' field")

    raw = migrations.migrate(raw)

    try:
        scenario = Scenario.from_dict(raw)
    except (TypeError, KeyError) as exc:
        raise ScenarioValidationError(f"{path}: malformed scenario structure ({exc})") from exc

    scenario.validate()
    return scenario
