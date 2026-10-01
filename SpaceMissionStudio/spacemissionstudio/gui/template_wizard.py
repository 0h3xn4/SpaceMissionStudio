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

"""A guided, multi-step ``QWizard`` for customizing a bundled template
mission (``spacemissionstudio/scenarios/templates/``) -- built in response to
a direct request that a user be able to "recreate the desired scenario
themselves or even tweak some parameters a little bit" from a template,
without first learning the full ``ScenarioEditorWidget`` form (every
field on every spacecraft/sensor/actuator/mission-sequence command).

Deliberately a CURATED subset, not a generic reflection of every
dataclass field: each :class:`TemplateWizardSpec` below exposes only the
handful of parameters that template's own ``description`` already calls
out under "Try changing:" (see ``scripts/_generate_templates.py``), each
with its own plain-language label/help text -- a focused, approachable
flow, not a second copy of the full editor. ``gui/load_scenario_widget.py``
shows one standalone "Customize: <template name>..." button for every
template with a registered spec here; every other template still only
opens straight into the full editor via the existing "Open Template"
button, unchanged.

Every bundled template ('01' through '18') has a registered spec. The
first pass covered three representative ones ('03' GEO station-keeping,
'18' LEO station-keeping, '07' full attitude + hardware + power) to
validate the spec format and the UX before this full rollout -- adding a
template's spec is just another :class:`TemplateWizardSpec` entry in
:data:`_SPECS` below; the wizard machinery itself
(:class:`TemplateCustomizeWizard`) is already generic over any spec.
Not every field is a literal copy of its template's own "Try changing:"
text: a few (e.g. '06'/'11'/'15's initial attitude tip, in place of a
fsw_mode STRING swap; '04's constellation altitude/inclination applied
uniformly across every generated satellite, in place of a
total_satellites/num_planes REGENERATION) were chosen as the closest
SAFE, scalar-field equivalent instead -- each such substitution is
explained in that spec's own ``intro``/comment. Two things no spec here
ever exposes, even when a template's own "Try changing:" mentions them:
``fsw_mode`` (switching it needs a structurally different fsw_params
set, not a spin-box edit) and ``dynamics_task_rate_s`` (several
templates' own comments document a real, confirmed NaN-divergence risk
from setting this too coarse -- see HISTORY.md).

The wizard operates on an in-memory COPY of the template's ``Scenario``
(via ``Scenario.from_dict(scenario.to_dict())``, the same round-trip
``tests/test_scenario_templates.py`` already trusts) -- the original
template file on disk is never touched, matching how "Open Template"
itself already behaves (templates are read-only starting points, saved
elsewhere via File > Save As). ``result_scenario()`` returns that copy
with every page's values applied; the caller (``MainWindow``) is
responsible for validating it and opening it in the full editor (see
``gui/main_window.py``'s ``_on_load_scenario_customized``) -- the exact
same "hand off a Scenario, let the one real editor own validation/save"
split every other GUI-vs-schema boundary in this app already uses.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from PySide6.QtWidgets import QDoubleSpinBox, QFormLayout, QLabel, QWizard, QWizardPage

from ..schema.scenario import Scenario

# SpacecraftConfig.orbit.semi_major_axis_km (OrbitIC, "classical_elements")
# is measured from the central body's CENTER, while
# StationKeepingConfig.target_altitude_km is measured from its surface --
# used below for DISPLAY purposes only (showing an initial altitude in a
# spin box) -- confirmed directly against a real Basilisk build
# (simIncludeGravBody.gravBodyFactory().createEarth().radEquator ==
# 6378136.6 m). Earth-specific; fine for this first pass (every current
# station_keeping/Walker-constellation template is Earth-centered) -- a
# non-Earth central body would need this generalized if a future
# template needs it.
#
# NEVER used to compute a field's WRITE-BACK value (see
# _set_leo_altitude_km's own comment for why: '03'/'18's own
# scripts/_generate_templates.py builders hand-picked a simpler "6378.0"
# round number instead of this precise constant, so recomputing
# semi_major_axis_km from this constant on every accept() -- even with
# zero user edits -- silently drifted it by ~137 m; a real bug, caught by
# this module's own round-trip regression tests).
_EARTH_RADIUS_KM = 6378.1366


@dataclass(frozen=True)
class WizardField:
    """One spin-box on one wizard page. ``get``/``set`` close over
    whichever dataclass field(s) this knob actually represents -- some
    are a single ``SpacecraftConfig`` attribute, others (like '18's
    altitude, above) touch more than one field together so the Scenario
    never passes through an inconsistent intermediate state.
    """

    label: str
    help_text: str
    get: Callable[[Scenario], float]
    set: Callable[[Scenario, float], None]
    minimum: float
    maximum: float
    decimals: int = 3
    step: float = 1.0
    suffix: str = ""


@dataclass(frozen=True)
class WizardPageSpec:
    title: str
    intro: str
    fields: List[WizardField]


@dataclass(frozen=True)
class TemplateWizardSpec:
    template_filename: str
    pages: List[WizardPageSpec]


def _sc(scenario: Scenario):
    """Every current wizard spec is single-spacecraft -- this is the one
    place that assumption lives, so a future multi-spacecraft template's
    spec would only need its own get/set closures, not a change here.
    """
    return scenario.spacecraft[0]


def _rw_max_momentum(scenario: Scenario) -> float:
    return float(_sc(scenario).actuators[0].params["maxMomentum"])


def _set_rw_max_momentum(scenario: Scenario, value: float) -> None:
    # Applied uniformly to every reaction wheel -- '07's own three wheels
    # are built symmetrically (orthogonal spin axes, identical
    # maxMomentum), and keeping them identical here avoids the wizard
    # silently creating an asymmetric wheel set a user never asked for.
    for actuator in _sc(scenario).actuators:
        if actuator.kind == "reaction_wheel":
            actuator.params["maxMomentum"] = value


def _leo_altitude_km(scenario: Scenario) -> float:
    return float(_sc(scenario).station_keeping.target_altitude_km)


def _set_leo_altitude_km(scenario: Scenario, value: float) -> None:
    sc = _sc(scenario)
    # Derives the radius offset from this scenario's OWN current
    # (pre-edit) semi_major_axis_km/target_altitude_km, rather than
    # applying _EARTH_RADIUS_KM fresh -- '18's own
    # scripts/_generate_templates.py builder used a simpler "6378.0"
    # round number, not that precise constant, so applying the constant
    # directly here silently drifted semi_major_axis_km by ~137 m on
    # EVERY accept(), even with zero edits (a real bug, caught by this
    # module's own round-trip regression tests). Reading both fields
    # before mutating either preserves whatever offset the template was
    # actually built with, exactly, regardless of which convention it
    # happens to use.
    radius_offset_km = sc.orbit.semi_major_axis_km - sc.station_keeping.target_altitude_km
    sc.station_keeping.target_altitude_km = value
    sc.orbit.semi_major_axis_km = value + radius_offset_km


def _follower(scenario: Scenario):
    """'05's own two-spacecraft template -- the one with phasing_keeping
    (always paired with its own station_keeping -- see
    PhasingKeepingConfig's own docstring) is the one every wizard field
    for this template targets; 'chief-1' has neither.
    """
    return next(sc for sc in scenario.spacecraft if sc.phasing_keeping is not None)


def _walker_altitude_km(scenario: Scenario) -> float:
    return float(scenario.spacecraft[0].orbit.semi_major_axis_km - _EARTH_RADIUS_KM)


def _set_walker_altitude_km(scenario: Scenario, value: float) -> None:
    # Applied uniformly to EVERY generated satellite -- a real Walker
    # constellation shares one altitude/inclination across every plane
    # and satellite by construction (engine.constellation.
    # generate_walker_constellation), only RAAN/mean-anomaly differ
    # between them, so this preserves that shared-altitude invariant
    # rather than making one satellite's orbit inconsistent with the rest.
    for sc in scenario.spacecraft:
        sc.orbit.semi_major_axis_km = value + _EARTH_RADIUS_KM


def _walker_inclination_deg(scenario: Scenario) -> float:
    return float(scenario.spacecraft[0].orbit.inclination_deg)


def _set_walker_inclination_deg(scenario: Scenario, value: float) -> None:
    for sc in scenario.spacecraft:
        sc.orbit.inclination_deg = value


def _thruster_max_thrust(scenario: Scenario) -> float:
    return float(_sc(scenario).actuators[0].params["MaxThrust"])


def _set_thruster_max_thrust(scenario: Scenario, value: float) -> None:
    # Applied uniformly to every thruster -- same "keep a symmetric
    # hardware layout symmetric" reasoning as _set_rw_max_momentum above.
    for actuator in _sc(scenario).actuators:
        if actuator.kind == "thruster":
            actuator.params["MaxThrust"] = value


def _css_fov_deg(scenario: Scenario) -> float:
    return float(_sc(scenario).sensors[0].params["fov_deg"])


def _set_css_fov_deg(scenario: Scenario, value: float) -> None:
    for sensor in _sc(scenario).sensors:
        if sensor.kind == "coarse_sun_sensor":
            sensor.params["fov_deg"] = value


# Matches scripts/_generate_templates.py's own "_RPM_TO_RAD_S = math.pi
# / 30.0" exactly -- name, value, AND operation direction (that script
# always MULTIPLIES by this to go RPM -> rad/s). _wheel_bias_rpm's get()
# below divides by this SAME constant (never a separately-precomputed
# reciprocal, e.g. "30.0 / math.pi") specifically so a true no-op
# round-trip (rpm = rad_s / _RPM_TO_RAD_S; rad_s_back = rpm *
# _RPM_TO_RAD_S) is bit-exact, not just numerically close -- confirmed
# directly: using a separately-precomputed reciprocal instead left a
# ~7e-15 (a few ULP) discrepancy after one round trip, invisible at this
# field's own display precision but caught by this module's own
# byte-for-byte round-trip regression tests (a real bug, now fixed).
_RPM_TO_RAD_S = math.pi / 30.0


def _wheel_bias_rpm(index: int):
    """One of '13's 4 wheel_speed_biases_rad_s entries, exposed in RPM
    (matching the template's own docstring, which always talks about
    "800/600/400/200 RPM", never the underlying rad/s) -- a closure
    factory (not 4 hand-written functions) since all 4 fields share the
    identical get/set shape, differing only by list index.
    """
    def get(scenario: Scenario) -> float:
        return _sc(scenario).magnetic_momentum_management.wheel_speed_biases_rad_s[index] / _RPM_TO_RAD_S

    def set_(scenario: Scenario, value: float) -> None:
        biases = _sc(scenario).magnetic_momentum_management.wheel_speed_biases_rad_s
        biases[index] = value * _RPM_TO_RAD_S

    return get, set_


def _wheel_omega_rpm(index: int):
    """One of '12's 4 reaction wheels' own initial Omega (RPM, matching
    simIncludeRW.py's own units for this parameter directly, unlike '13's
    biases above) -- same closure-factory reasoning as _wheel_bias_rpm.
    """
    def get(scenario: Scenario) -> float:
        return float(_sc(scenario).actuators[index].params.get("Omega", 0.0))

    def set_(scenario: Scenario, value: float) -> None:
        _sc(scenario).actuators[index].params["Omega"] = value

    return get, set_


def _maneuver_command(scenario: Scenario):
    return next(c for c in scenario.mission_sequence if c.kind == "maneuver")


def _coast_command(scenario: Scenario, label_substring: str):
    return next(c for c in scenario.mission_sequence if c.kind == "propagate" and label_substring in (c.label or ""))


def _lambert_command(scenario: Scenario):
    return next(c for c in scenario.mission_sequence if c.kind == "lambert_transfer")


def _lambert_coast_command(scenario: Scenario):
    return next(c for c in scenario.mission_sequence if c.kind == "propagate")


def _lambert_target_range_m(scenario: Scenario) -> float:
    return abs(_lambert_command(scenario).params["target_position_m"][0])


def _set_lambert_target_range_m(scenario: Scenario, value: float) -> None:
    # target_position_m is along -X only in this template (see its own
    # build script) -- preserves that direction, only the magnitude
    # (range from the central body's center) is this field's own concern.
    _lambert_command(scenario).params["target_position_m"][0] = -value


def _lambert_tof_s(scenario: Scenario) -> float:
    return float(_lambert_command(scenario).params["time_of_flight_s"])


def _set_lambert_tof_s(scenario: Scenario, value: float) -> None:
    # The coast-to-arrival propagate command's own duration_days must
    # stay in lockstep with time_of_flight_s, or the template's own
    # "after transfer" report would snapshot the state at the WRONG
    # time -- not actually at the arrival point lambert_transfer solved
    # for, silently breaking this template's entire "lands almost
    # exactly at target_position_m" lesson.
    _lambert_command(scenario).params["time_of_flight_s"] = value
    _lambert_coast_command(scenario).params["duration_days"] = value / 86400.0


_SPECS: Dict[str, TemplateWizardSpec] = {
    "03_geo_station_keeping.json": TemplateWizardSpec(
        template_filename="03_geo_station_keeping.json",
        pages=[
            WizardPageSpec(
                title="Station-keeping controller",
                intro="How aggressively the deadband thruster corrects GEO drift.",
                fields=[
                    WizardField(
                        "Deadband", "How far the satellite may drift from target altitude before a "
                        "correction burn starts -- tighter means more frequent, smaller burns.",
                        lambda s: _sc(s).station_keeping.deadband_km,
                        lambda s, v: setattr(_sc(s).station_keeping, "deadband_km", v),
                        0.1, 500.0, decimals=2, step=0.5, suffix=" km",
                    ),
                    WizardField(
                        "Thrust", "The station-keeping thruster's thrust magnitude.",
                        lambda s: _sc(s).station_keeping.thrust_n,
                        lambda s, v: setattr(_sc(s).station_keeping, "thrust_n", v),
                        0.001, 10.0, decimals=3, step=0.05, suffix=" N",
                    ),
                    WizardField(
                        "Specific impulse", "Thruster efficiency -- higher uses less propellant per "
                        "unit of delta-V.",
                        lambda s: _sc(s).station_keeping.isp_s,
                        lambda s, v: setattr(_sc(s).station_keeping, "isp_s", v),
                        50.0, 5000.0, decimals=0, step=50.0, suffix=" s",
                    ),
                    WizardField(
                        "Propellant budget", "Total propellant available for station-keeping over the run.",
                        lambda s: _sc(s).station_keeping.propellant_kg,
                        lambda s, v: setattr(_sc(s).station_keeping, "propellant_kg", v),
                        0.1, 1000.0, decimals=2, step=5.0, suffix=" kg",
                    ),
                ],
            ),
            WizardPageSpec(
                title="Simulation length",
                intro="How long to propagate -- longer runs show more (or, with a wide enough "
                      "deadband, possibly zero) correction burns.",
                fields=[
                    WizardField(
                        "Duration", "Total simulated time.",
                        lambda s: s.sim_settings.duration_days,
                        lambda s, v: setattr(s.sim_settings, "duration_days", v),
                        0.1, 3650.0, decimals=2, step=1.0, suffix=" days",
                    ),
                ],
            ),
        ],
    ),
    "18_leo_station_keeping.json": TemplateWizardSpec(
        template_filename="18_leo_station_keeping.json",
        pages=[
            WizardPageSpec(
                title="Orbit altitude",
                intro="Lower altitude means thicker atmosphere means faster drag decay means more "
                      "frequent corrections -- the single biggest knob for this template.",
                fields=[
                    WizardField(
                        "Altitude", "Target (and starting) altitude above the Earth's surface.",
                        _leo_altitude_km, _set_leo_altitude_km,
                        200.0, 2000.0, decimals=1, step=10.0, suffix=" km",
                    ),
                ],
            ),
            WizardPageSpec(
                title="Spacecraft drag properties",
                intro="How much drag force the satellite's own shape/mass produces.",
                fields=[
                    WizardField(
                        "Drag area", "Cross-sectional area exposed to the atmosphere.",
                        lambda s: _sc(s).drag_area_m2,
                        lambda s, v: setattr(_sc(s), "drag_area_m2", v),
                        0.01, 100.0, decimals=2, step=0.1, suffix=" m^2",
                    ),
                    WizardField(
                        "Drag coefficient", "A dimensionless shape factor -- most satellites fall "
                        "between about 2.0 and 2.5.",
                        lambda s: _sc(s).drag_coeff,
                        lambda s, v: setattr(_sc(s), "drag_coeff", v),
                        1.0, 4.0, decimals=2, step=0.1,
                    ),
                ],
            ),
            WizardPageSpec(
                title="Station-keeping controller",
                intro="How aggressively the deadband thruster corrects altitude decay.",
                fields=[
                    WizardField(
                        "Deadband", "How far the satellite may decay below target altitude before a "
                        "correction burn starts -- tighter means more frequent, smaller burns.",
                        lambda s: _sc(s).station_keeping.deadband_km,
                        lambda s, v: setattr(_sc(s).station_keeping, "deadband_km", v),
                        0.05, 50.0, decimals=2, step=0.1, suffix=" km",
                    ),
                    WizardField(
                        "Thrust", "The station-keeping thruster's thrust magnitude.",
                        lambda s: _sc(s).station_keeping.thrust_n,
                        lambda s, v: setattr(_sc(s).station_keeping, "thrust_n", v),
                        0.001, 10.0, decimals=3, step=0.01, suffix=" N",
                    ),
                    WizardField(
                        "Specific impulse", "Thruster efficiency -- higher uses less propellant per "
                        "unit of delta-V.",
                        lambda s: _sc(s).station_keeping.isp_s,
                        lambda s, v: setattr(_sc(s).station_keeping, "isp_s", v),
                        50.0, 5000.0, decimals=0, step=50.0, suffix=" s",
                    ),
                    WizardField(
                        "Propellant budget", "Total propellant available for station-keeping over the run.",
                        lambda s: _sc(s).station_keeping.propellant_kg,
                        lambda s, v: setattr(_sc(s).station_keeping, "propellant_kg", v),
                        0.01, 100.0, decimals=2, step=0.1, suffix=" kg",
                    ),
                ],
            ),
            WizardPageSpec(
                title="Simulation length",
                intro="How long to propagate -- longer runs at low altitude show faster cumulative decay.",
                fields=[
                    WizardField(
                        "Duration", "Total simulated time.",
                        lambda s: s.sim_settings.duration_days,
                        lambda s, v: setattr(s.sim_settings, "duration_days", v),
                        0.1, 365.0, decimals=2, step=1.0, suffix=" days",
                    ),
                ],
            ),
        ],
    ),
    "07_attitude_pointing_with_adcs_hardware.json": TemplateWizardSpec(
        template_filename="07_attitude_pointing_with_adcs_hardware.json",
        pages=[
            WizardPageSpec(
                title="Reaction wheels",
                intro="Applied to all three (identical, orthogonal-axis) wheels together.",
                fields=[
                    WizardField(
                        "Max momentum", "Each wheel's momentum storage capacity before it saturates "
                        "and needs desaturating.",
                        _rw_max_momentum, _set_rw_max_momentum,
                        1.0, 1000.0, decimals=1, step=10.0, suffix=" N*m*s",
                    ),
                ],
            ),
            WizardPageSpec(
                title="Power budget",
                intro="The solar array and battery backing this spacecraft's power draw.",
                fields=[
                    WizardField(
                        "Panel area", "Total solar panel area.",
                        lambda s: _sc(s).power.panel_area_m2,
                        lambda s, v: setattr(_sc(s).power, "panel_area_m2", v),
                        0.01, 50.0, decimals=2, step=0.1, suffix=" m^2",
                    ),
                    WizardField(
                        "Battery capacity", "Total energy storage.",
                        lambda s: _sc(s).power.battery_capacity_wh,
                        lambda s, v: setattr(_sc(s).power, "battery_capacity_wh", v),
                        1.0, 10000.0, decimals=1, step=10.0, suffix=" W*hr",
                    ),
                ],
            ),
            WizardPageSpec(
                title="Simulation length",
                intro="How long to propagate.",
                fields=[
                    WizardField(
                        "Duration", "Total simulated time.",
                        lambda s: s.sim_settings.duration_days,
                        lambda s, v: setattr(s.sim_settings, "duration_days", v),
                        0.001, 365.0, decimals=4, step=0.01, suffix=" days",
                    ),
                ],
            ),
        ],
    ),
    "01_two_body_circular_orbit.json": TemplateWizardSpec(
        template_filename="01_two_body_circular_orbit.json",
        pages=[
            WizardPageSpec(
                title="Orbit",
                intro="The basic two-body orbit this whole template is about.",
                fields=[
                    WizardField(
                        "Semi-major axis", "Higher means a slower, longer-period orbit (Kepler's third law).",
                        lambda s: _sc(s).orbit.semi_major_axis_km,
                        lambda s, v: setattr(_sc(s).orbit, "semi_major_axis_km", v),
                        6500.0, 100000.0, decimals=1, step=100.0, suffix=" km",
                    ),
                    WizardField(
                        "Inclination", "Watch the ground track in Vizard change with this.",
                        lambda s: _sc(s).orbit.inclination_deg,
                        lambda s, v: setattr(_sc(s).orbit, "inclination_deg", v),
                        0.0, 180.0, decimals=2, step=1.0, suffix=" deg",
                    ),
                    WizardField(
                        "Eccentricity", "0 is circular -- see '02' for a non-circular example.",
                        lambda s: _sc(s).orbit.eccentricity,
                        lambda s, v: setattr(_sc(s).orbit, "eccentricity", v),
                        0.0, 0.9, decimals=4, step=0.01,
                    ),
                ],
            ),
            WizardPageSpec(
                title="Simulation length",
                intro="How long to propagate.",
                fields=[
                    WizardField(
                        "Duration", "Total simulated time.",
                        lambda s: s.sim_settings.duration_days,
                        lambda s, v: setattr(s.sim_settings, "duration_days", v),
                        0.01, 365.0, decimals=2, step=0.5, suffix=" days",
                    ),
                ],
            ),
        ],
    ),
    "02_elliptical_orbit_with_perturbations.json": TemplateWizardSpec(
        template_filename="02_elliptical_orbit_with_perturbations.json",
        pages=[
            WizardPageSpec(
                title="Orbit",
                intro="The eccentric (GTO-like) orbit J2/third-body precession acts on.",
                fields=[
                    WizardField(
                        "Semi-major axis", "Higher means a slower, longer-period orbit.",
                        lambda s: _sc(s).orbit.semi_major_axis_km,
                        lambda s, v: setattr(_sc(s).orbit, "semi_major_axis_km", v),
                        6500.0, 100000.0, decimals=1, step=500.0, suffix=" km",
                    ),
                    WizardField(
                        "Eccentricity", "How elongated the orbit is -- 0.7 here is a real GTO-like value.",
                        lambda s: _sc(s).orbit.eccentricity,
                        lambda s, v: setattr(_sc(s).orbit, "eccentricity", v),
                        0.0, 0.95, decimals=4, step=0.01,
                    ),
                    WizardField(
                        "Inclination", "The orbit plane's tilt from the equator.",
                        lambda s: _sc(s).orbit.inclination_deg,
                        lambda s, v: setattr(_sc(s).orbit, "inclination_deg", v),
                        0.0, 180.0, decimals=2, step=1.0, suffix=" deg",
                    ),
                ],
            ),
            WizardPageSpec(
                title="Gravity fidelity",
                intro="How much of Earth's own non-spherical gravity to model.",
                fields=[
                    WizardField(
                        "Spherical-harmonics degree", "0 is the perturbation-free point-mass case "
                        "(compare against this template's own precession lesson); this template ships at 10.",
                        lambda s: float(s.gravity.central_body_degree),
                        lambda s, v: setattr(s.gravity, "central_body_degree", int(round(v))),
                        0.0, 20.0, decimals=0, step=2.0,
                    ),
                ],
            ),
            WizardPageSpec(
                title="Simulation length",
                intro="How long to propagate -- longer runs make the J2/third-body precession more visible.",
                fields=[
                    WizardField(
                        "Duration", "Total simulated time.",
                        lambda s: s.sim_settings.duration_days,
                        lambda s, v: setattr(s.sim_settings, "duration_days", v),
                        0.1, 30.0, decimals=2, step=0.5, suffix=" days",
                    ),
                ],
            ),
        ],
    ),
    "04_walker_constellation.json": TemplateWizardSpec(
        template_filename="04_walker_constellation.json",
        pages=[
            WizardPageSpec(
                title="Constellation geometry",
                intro="Applied uniformly to every satellite (a real Walker constellation shares one "
                      "altitude/inclination across every plane and satellite by construction -- only "
                      "RAAN/mean anomaly differ between them). To change the satellite/plane COUNT "
                      "itself, regenerate via the GUI's 'Generate Walker constellation...' dialog or the "
                      "'generate-constellation' CLI subcommand instead -- hand-editing that here would "
                      "leave this scenario's spacecraft list structurally wrong.",
                fields=[
                    WizardField(
                        "Altitude", "Every satellite's shared orbital altitude above Earth's surface.",
                        _walker_altitude_km, _set_walker_altitude_km,
                        # decimals=4, not 1: this field is DERIVED
                        # (semi_major_axis_km minus _EARTH_RADIUS_KM, see
                        # that constant's own comment) -- at decimals=1
                        # the spin box rounds away the sub-meter
                        # remainder from that subtraction, so even an
                        # unedited round-trip silently drifted
                        # semi_major_axis_km by ~0.4 m (a real bug,
                        # caught by this module's own round-trip
                        # regression tests). _EARTH_RADIUS_KM is
                        # Basilisk's own precise earth.radEquator, so at
                        # decimals=4 this template's own 700 km altitude
                        # now displays as a clean "700.0000", not
                        # "700.0004".
                        200.0, 2000.0, decimals=4, step=10.0, suffix=" km",
                    ),
                    WizardField(
                        "Inclination", "Every satellite's shared orbit-plane tilt from the equator.",
                        _walker_inclination_deg, _set_walker_inclination_deg,
                        0.0, 180.0, decimals=2, step=1.0, suffix=" deg",
                    ),
                ],
            ),
            WizardPageSpec(
                title="Simulation length",
                intro="How long to propagate.",
                fields=[
                    WizardField(
                        "Duration", "Total simulated time.",
                        lambda s: s.sim_settings.duration_days,
                        lambda s, v: setattr(s.sim_settings, "duration_days", v),
                        0.1, 30.0, decimals=2, step=0.5, suffix=" days",
                    ),
                ],
            ),
        ],
    ),
    "05_formation_flying_phasing.json": TemplateWizardSpec(
        template_filename="05_formation_flying_phasing.json",
        pages=[
            WizardPageSpec(
                title="Formation geometry",
                intro="How far behind the chief 'follower-1' should hold station, along-track.",
                fields=[
                    WizardField(
                        "Target separation", "The along-track distance phasing_keeping actively holds "
                        "'follower-1' at, behind 'chief-1'.",
                        lambda s: _follower(s).phasing_keeping.target_separation_km[0],
                        lambda s, v: _follower(s).phasing_keeping.target_separation_km.__setitem__(0, v),
                        1.0, 1000.0, decimals=2, step=5.0, suffix=" km",
                    ),
                ],
            ),
            WizardPageSpec(
                title="Station-keeping controller",
                intro="'follower-1's own altitude-holding burns (phasing_keeping always needs this "
                      "configured on the same spacecraft -- see PhasingKeepingConfig's own docstring).",
                fields=[
                    WizardField(
                        "Deadband", "How far 'follower-1' may decay below target altitude before a "
                        "correction burn starts.",
                        lambda s: _follower(s).station_keeping.deadband_km,
                        lambda s, v: setattr(_follower(s).station_keeping, "deadband_km", v),
                        0.05, 50.0, decimals=2, step=0.1, suffix=" km",
                    ),
                    WizardField(
                        "Thrust", "The station-keeping thruster's thrust magnitude.",
                        lambda s: _follower(s).station_keeping.thrust_n,
                        lambda s, v: setattr(_follower(s).station_keeping, "thrust_n", v),
                        0.001, 10.0, decimals=3, step=0.01, suffix=" N",
                    ),
                    WizardField(
                        "Specific impulse", "Thruster efficiency -- higher uses less propellant per "
                        "unit of delta-V.",
                        lambda s: _follower(s).station_keeping.isp_s,
                        lambda s, v: setattr(_follower(s).station_keeping, "isp_s", v),
                        50.0, 5000.0, decimals=0, step=50.0, suffix=" s",
                    ),
                    WizardField(
                        "Propellant budget", "Total propellant available, shared between "
                        "station-keeping and phasing burns.",
                        lambda s: _follower(s).station_keeping.propellant_kg,
                        lambda s, v: setattr(_follower(s).station_keeping, "propellant_kg", v),
                        0.01, 100.0, decimals=2, step=0.1, suffix=" kg",
                    ),
                ],
            ),
            WizardPageSpec(
                title="Simulation length",
                intro="How long to propagate.",
                fields=[
                    WizardField(
                        "Duration", "Total simulated time.",
                        lambda s: s.sim_settings.duration_days,
                        lambda s, v: setattr(s.sim_settings, "duration_days", v),
                        0.1, 60.0, decimals=2, step=1.0, suffix=" days",
                    ),
                ],
            ),
        ],
    ),
    "06_attitude_pointing_basic.json": TemplateWizardSpec(
        template_filename="06_attitude_pointing_basic.json",
        pages=[
            WizardPageSpec(
                title="Initial attitude tip",
                intro="How far off the hillPoint-commanded attitude this spacecraft starts -- watch "
                      "the controller drive this back to zero.",
                fields=[
                    WizardField(
                        "Sigma X", "MRP attitude-error component (body-to-reference), X axis.",
                        lambda s: _sc(s).sigma_bn_init[0],
                        lambda s, v: _sc(s).sigma_bn_init.__setitem__(0, v),
                        -0.9, 0.9, decimals=3, step=0.05,
                    ),
                    WizardField(
                        "Sigma Y", "MRP attitude-error component (body-to-reference), Y axis.",
                        lambda s: _sc(s).sigma_bn_init[1],
                        lambda s, v: _sc(s).sigma_bn_init.__setitem__(1, v),
                        -0.9, 0.9, decimals=3, step=0.05,
                    ),
                    WizardField(
                        "Sigma Z", "MRP attitude-error component (body-to-reference), Z axis.",
                        lambda s: _sc(s).sigma_bn_init[2],
                        lambda s, v: _sc(s).sigma_bn_init.__setitem__(2, v),
                        -0.9, 0.9, decimals=3, step=0.05,
                    ),
                ],
            ),
            WizardPageSpec(
                title="Simulation length",
                intro="How long to propagate -- deliberately kept short here (see this template's own "
                      "dynamics_task_rate_s comment on why a coarser rate is unsafe for idealized "
                      "actuation, not changed by this wizard).",
                fields=[
                    WizardField(
                        "Duration", "Total simulated time.",
                        lambda s: s.sim_settings.duration_days,
                        lambda s, v: setattr(s.sim_settings, "duration_days", v),
                        0.001, 1.0, decimals=4, step=0.01, suffix=" days",
                    ),
                ],
            ),
        ],
    ),
    "08_mission_sequence_orbit_raise.json": TemplateWizardSpec(
        template_filename="08_mission_sequence_orbit_raise.json",
        pages=[
            WizardPageSpec(
                title="Burn",
                intro="The single prograde maneuver command's own delta-V magnitude.",
                fields=[
                    WizardField(
                        "Delta-V (prograde)", "Positive raises the opposite side of the orbit; negative "
                        "(retrograde) lowers it instead.",
                        lambda s: _maneuver_command(s).params["delta_v_m_s"][0],
                        lambda s, v: _maneuver_command(s).params["delta_v_m_s"].__setitem__(0, v),
                        -500.0, 500.0, decimals=2, step=5.0, suffix=" m/s",
                    ),
                ],
            ),
            WizardPageSpec(
                title="Mission timeline",
                intro="How long each coast segment runs, before and after the burn.",
                fields=[
                    WizardField(
                        "Coast before burn", "How long to propagate before the maneuver command fires.",
                        lambda s: _coast_command(s, "before").params["duration_days"],
                        lambda s, v: _coast_command(s, "before").params.__setitem__("duration_days", v),
                        0.01, 5.0, decimals=3, step=0.05, suffix=" days",
                    ),
                    WizardField(
                        "Coast after burn", "How long to propagate after the maneuver command fires.",
                        lambda s: _coast_command(s, "after").params["duration_days"],
                        lambda s, v: _coast_command(s, "after").params.__setitem__("duration_days", v),
                        0.01, 5.0, decimals=3, step=0.05, suffix=" days",
                    ),
                ],
            ),
        ],
    ),
    "09_monte_carlo_dispersion_analysis.json": TemplateWizardSpec(
        template_filename="09_monte_carlo_dispersion_analysis.json",
        pages=[
            WizardPageSpec(
                title="Monte Carlo batch",
                intro="The dry_mass_kg dispersion every one of this batch's cases independently redraws.",
                fields=[
                    WizardField(
                        "Number of runs", "More runs give a smoother distribution of outcomes, at "
                        "proportional runtime cost.",
                        lambda s: float(s.monte_carlo.num_runs),
                        lambda s, v: setattr(s.monte_carlo, "num_runs", int(round(v))),
                        1.0, 1000.0, decimals=0, step=5.0,
                    ),
                    WizardField(
                        "Mean mass", "The normal distribution's own mean dry mass.",
                        lambda s: s.monte_carlo.dispersions[0].mean,
                        lambda s, v: setattr(s.monte_carlo.dispersions[0], "mean", v),
                        1.0, 1.0e6, decimals=2, step=10.0, suffix=" kg",
                    ),
                    WizardField(
                        "Std deviation", "A wider spread means more extreme cases appear in the batch.",
                        lambda s: s.monte_carlo.dispersions[0].std_deviation,
                        lambda s, v: setattr(s.monte_carlo.dispersions[0], "std_deviation", v),
                        0.0, 500.0, decimals=2, step=5.0, suffix=" kg",
                    ),
                ],
            ),
            WizardPageSpec(
                title="Simulation length",
                intro="How long each of the batch's cases propagates.",
                fields=[
                    WizardField(
                        "Duration", "Total simulated time, per case.",
                        lambda s: s.sim_settings.duration_days,
                        lambda s, v: setattr(s.sim_settings, "duration_days", v),
                        0.1, 30.0, decimals=2, step=0.5, suffix=" days",
                    ),
                ],
            ),
        ],
    ),
    "10_gravity_gradient_torque.json": TemplateWizardSpec(
        template_filename="10_gravity_gradient_torque.json",
        pages=[
            WizardPageSpec(
                title="Inertia spread",
                intro="A spherically-symmetric inertia (all three equal) makes gravity-gradient torque "
                      "identically zero -- the more elongated this spread, the stronger the effect.",
                fields=[
                    WizardField(
                        "Ixx", "Body-X principal moment of inertia.",
                        lambda s: _sc(s).inertia_kg_m2[0],
                        lambda s, v: _sc(s).inertia_kg_m2.__setitem__(0, v),
                        0.1, 1.0e5, decimals=2, step=1.0, suffix=" kg*m^2",
                    ),
                    WizardField(
                        "Iyy", "Body-Y principal moment of inertia.",
                        lambda s: _sc(s).inertia_kg_m2[4],
                        lambda s, v: _sc(s).inertia_kg_m2.__setitem__(4, v),
                        0.1, 1.0e5, decimals=2, step=1.0, suffix=" kg*m^2",
                    ),
                    WizardField(
                        "Izz", "Body-Z principal moment of inertia.",
                        lambda s: _sc(s).inertia_kg_m2[8],
                        lambda s, v: _sc(s).inertia_kg_m2.__setitem__(8, v),
                        0.1, 1.0e5, decimals=2, step=1.0, suffix=" kg*m^2",
                    ),
                ],
            ),
            WizardPageSpec(
                title="Orbit altitude",
                intro="Gravity-gradient torque falls off as 1/r^3 -- much stronger in a very low orbit "
                      "than at GEO altitude.",
                fields=[
                    WizardField(
                        "Semi-major axis", "Lower means a stronger gravity-gradient effect.",
                        lambda s: _sc(s).orbit.semi_major_axis_km,
                        lambda s, v: setattr(_sc(s).orbit, "semi_major_axis_km", v),
                        6500.0, 50000.0, decimals=1, step=100.0, suffix=" km",
                    ),
                ],
            ),
            WizardPageSpec(
                title="Simulation length",
                intro="How long to propagate.",
                fields=[
                    WizardField(
                        "Duration", "Total simulated time.",
                        lambda s: s.sim_settings.duration_days,
                        lambda s, v: setattr(s.sim_settings, "duration_days", v),
                        0.1, 10.0, decimals=2, step=0.1, suffix=" days",
                    ),
                ],
            ),
        ],
    ),
    "11_thruster_attitude_control.json": TemplateWizardSpec(
        template_filename="11_thruster_attitude_control.json",
        pages=[
            WizardPageSpec(
                title="Thruster strength",
                intro="Applied to all 8 thrusters uniformly -- weaker thrusters take longer to null "
                      "the same attitude error.",
                fields=[
                    WizardField(
                        "Max thrust", "Each thruster's own maximum thrust.",
                        _thruster_max_thrust, _set_thruster_max_thrust,
                        0.001, 100.0, decimals=3, step=0.1, suffix=" N",
                    ),
                ],
            ),
            WizardPageSpec(
                title="Initial attitude tip",
                intro="How far off the commanded inertial3D attitude this spacecraft starts.",
                fields=[
                    WizardField(
                        "Sigma X", "MRP attitude-error component, X axis.",
                        lambda s: _sc(s).sigma_bn_init[0],
                        lambda s, v: _sc(s).sigma_bn_init.__setitem__(0, v),
                        -0.9, 0.9, decimals=3, step=0.05,
                    ),
                    WizardField(
                        "Sigma Y", "MRP attitude-error component, Y axis.",
                        lambda s: _sc(s).sigma_bn_init[1],
                        lambda s, v: _sc(s).sigma_bn_init.__setitem__(1, v),
                        -0.9, 0.9, decimals=3, step=0.05,
                    ),
                    WizardField(
                        "Sigma Z", "MRP attitude-error component, Z axis.",
                        lambda s: _sc(s).sigma_bn_init[2],
                        lambda s, v: _sc(s).sigma_bn_init.__setitem__(2, v),
                        -0.9, 0.9, decimals=3, step=0.05,
                    ),
                ],
            ),
        ],
    ),
    "12_reaction_wheel_momentum_dumping.json": TemplateWizardSpec(
        template_filename="12_reaction_wheel_momentum_dumping.json",
        pages=[
            WizardPageSpec(
                title="Desaturation threshold",
                intro="momentum_dumping fires its desaturation thrusters once total wheel momentum "
                      "crosses this.",
                fields=[
                    WizardField(
                        "Momentum threshold", "A lower threshold triggers desaturation sooner and more often.",
                        lambda s: _sc(s).momentum_dumping.hs_max,
                        lambda s, v: setattr(_sc(s).momentum_dumping, "hs_max", v),
                        1.0, 1000.0, decimals=1, step=5.0, suffix=" N*m*s",
                    ),
                ],
            ),
            WizardPageSpec(
                title="Initial wheel speeds",
                intro="Closer to each wheel's own maxMomentum desaturates almost immediately.",
                fields=[
                    WizardField("Wheel 1", "rw-1's initial spin rate.", *_wheel_omega_rpm(0),
                                 0.0, 6000.0, decimals=1, step=100.0, suffix=" RPM"),
                    WizardField("Wheel 2", "rw-2's initial spin rate.", *_wheel_omega_rpm(1),
                                 0.0, 6000.0, decimals=1, step=100.0, suffix=" RPM"),
                    WizardField("Wheel 3", "rw-3's initial spin rate.", *_wheel_omega_rpm(2),
                                 0.0, 6000.0, decimals=1, step=100.0, suffix=" RPM"),
                    WizardField("Wheel 4", "rw-4's initial spin rate.", *_wheel_omega_rpm(3),
                                 0.0, 6000.0, decimals=1, step=100.0, suffix=" RPM"),
                ],
            ),
        ],
    ),
    "13_magnetic_torque_rod_momentum_management.json": TemplateWizardSpec(
        template_filename="13_magnetic_torque_rod_momentum_management.json",
        pages=[
            WizardPageSpec(
                title="Wheel speed targets",
                intro="The speed each reaction wheel is continuously biased toward via the magnetic "
                      "torque rods.",
                fields=[
                    WizardField("Wheel 1 target", "rw-1's target speed.", *_wheel_bias_rpm(0),
                                 0.0, 5000.0, decimals=1, step=50.0, suffix=" RPM"),
                    WizardField("Wheel 2 target", "rw-2's target speed.", *_wheel_bias_rpm(1),
                                 0.0, 5000.0, decimals=1, step=50.0, suffix=" RPM"),
                    WizardField("Wheel 3 target", "rw-3's target speed.", *_wheel_bias_rpm(2),
                                 0.0, 5000.0, decimals=1, step=50.0, suffix=" RPM"),
                    WizardField("Wheel 4 target", "rw-4's target speed.", *_wheel_bias_rpm(3),
                                 0.0, 5000.0, decimals=1, step=50.0, suffix=" RPM"),
                ],
            ),
            WizardPageSpec(
                title="Control gain and orbit",
                intro="How aggressively the magnetic torque rods react, and the field geometry they "
                      "react to.",
                fields=[
                    WizardField(
                        "Control gain", "A larger gain reacts faster but can overshoot/oscillate.",
                        lambda s: _sc(s).magnetic_momentum_management.c_gain,
                        lambda s, v: setattr(_sc(s).magnetic_momentum_management, "c_gain", v),
                        0.0001, 1.0, decimals=5, step=0.0005,
                    ),
                    WizardField(
                        "Orbit inclination", "A near-equatorial orbit sees a weaker, less "
                        "favorably-oriented geomagnetic field than a higher-inclination one.",
                        lambda s: _sc(s).orbit.inclination_deg,
                        lambda s, v: setattr(_sc(s).orbit, "inclination_deg", v),
                        0.0, 180.0, decimals=2, step=5.0, suffix=" deg",
                    ),
                ],
            ),
        ],
    ),
    "14_css_sun_heading_estimation.json": TemplateWizardSpec(
        template_filename="14_css_sun_heading_estimation.json",
        pages=[
            WizardPageSpec(
                title="Sensor field of view",
                intro="Applied to all 8 coarse sun sensors uniformly -- a narrower FOV sees fewer "
                      "sensors illuminated at once, degrading the WLS estimate's conditioning.",
                fields=[
                    WizardField(
                        "Field of view", "Each sensor's own half-cone field of view.",
                        _css_fov_deg, _set_css_fov_deg,
                        10.0, 180.0, decimals=1, step=5.0, suffix=" deg",
                    ),
                ],
            ),
            WizardPageSpec(
                title="Simulation length",
                intro="How long to propagate.",
                fields=[
                    WizardField(
                        "Duration", "Total simulated time.",
                        lambda s: s.sim_settings.duration_days,
                        lambda s, v: setattr(s.sim_settings, "duration_days", v),
                        0.001, 10.0, decimals=4, step=0.01, suffix=" days",
                    ),
                ],
            ),
        ],
    ),
    "15_celestial_body_pointing.json": TemplateWizardSpec(
        template_filename="15_celestial_body_pointing.json",
        pages=[
            WizardPageSpec(
                title="Target pointing axis",
                intro="Which body-fixed axis stays pointed at the Moon -- re-point a different "
                      "physical location on the spacecraft (e.g. an antenna mounted off a different face).",
                fields=[
                    WizardField(
                        "pHat X", "Pointing-axis component, body X.",
                        lambda s: _sc(s).fsw_params["pHat_B"][0],
                        lambda s, v: _sc(s).fsw_params["pHat_B"].__setitem__(0, v),
                        -1.0, 1.0, decimals=3, step=0.1,
                    ),
                    WizardField(
                        "pHat Y", "Pointing-axis component, body Y.",
                        lambda s: _sc(s).fsw_params["pHat_B"][1],
                        lambda s, v: _sc(s).fsw_params["pHat_B"].__setitem__(1, v),
                        -1.0, 1.0, decimals=3, step=0.1,
                    ),
                    WizardField(
                        "pHat Z", "Pointing-axis component, body Z.",
                        lambda s: _sc(s).fsw_params["pHat_B"][2],
                        lambda s, v: _sc(s).fsw_params["pHat_B"].__setitem__(2, v),
                        -1.0, 1.0, decimals=3, step=0.1,
                    ),
                ],
            ),
            WizardPageSpec(
                title="Simulation length",
                intro="How long to propagate -- deliberately kept short here (see this template's own "
                      "dynamics_task_rate_s comment on why a coarser rate is unsafe for idealized "
                      "actuation, not changed by this wizard).",
                fields=[
                    WizardField(
                        "Duration", "Total simulated time.",
                        lambda s: s.sim_settings.duration_days,
                        lambda s, v: setattr(s.sim_settings, "duration_days", v),
                        0.001, 1.0, decimals=4, step=0.01, suffix=" days",
                    ),
                ],
            ),
        ],
    ),
    "16_lambert_transfer.json": TemplateWizardSpec(
        template_filename="16_lambert_transfer.json",
        pages=[
            WizardPageSpec(
                title="Transfer target",
                intro="Where lambert_transfer solves for a delta-V to reach, and when -- the coast-to"
                      "-arrival command's own duration is kept in lockstep with time of flight "
                      "automatically, so the 'after transfer' report still snapshots the real arrival.",
                fields=[
                    WizardField(
                        "Target range", "Distance from the central body's center (along the same "
                        "-X direction this template already targets).",
                        _lambert_target_range_m, _set_lambert_target_range_m,
                        1.0e5, 1.0e8, decimals=0, step=1000.0, suffix=" m",
                    ),
                    WizardField(
                        "Time of flight", "Very short times need very large (often rejected) delta-Vs.",
                        _lambert_tof_s, _set_lambert_tof_s,
                        10.0, 100000.0, decimals=1, step=10.0, suffix=" s",
                    ),
                ],
            ),
            WizardPageSpec(
                title="Transfer constraints",
                intro="lambertValidator's own feasibility checks on the solved transfer.",
                fields=[
                    WizardField(
                        "Max distance from target", "Reject a solution that misses target_position_m "
                        "by more than this.",
                        lambda s: _lambert_command(s).params["max_distance_target_m"],
                        lambda s, v: _lambert_command(s).params.__setitem__("max_distance_target_m", v),
                        1.0, 1.0e6, decimals=1, step=10.0, suffix=" m",
                    ),
                    WizardField(
                        "Min orbit radius", "Reject any transfer trajectory that would dip below this "
                        "radius (e.g. through the central body's own surface).",
                        lambda s: _lambert_command(s).params["min_orbit_radius_m"],
                        lambda s, v: _lambert_command(s).params.__setitem__("min_orbit_radius_m", v),
                        1.0e5, 1.0e8, decimals=0, step=1000.0, suffix=" m",
                    ),
                ],
            ),
        ],
    ),
    "17_fuel_tank_depletion.json": TemplateWizardSpec(
        template_filename="17_fuel_tank_depletion.json",
        pages=[
            WizardPageSpec(
                title="Fuel tank",
                intro="Set propellant_mass_kg below what the convergence burn needs (confirmed "
                      "~0.185 kg for this template's own setup) to see the tank run dry mid-maneuver.",
                fields=[
                    WizardField(
                        "Initial propellant", "How much propellant the tank starts with.",
                        lambda s: _sc(s).fuel_tank.propellant_mass_kg,
                        lambda s, v: setattr(_sc(s).fuel_tank, "propellant_mass_kg", v),
                        0.001, 100.0, decimals=3, step=0.05, suffix=" kg",
                    ),
                    WizardField(
                        "Tank capacity", "The tank's own maximum propellant mass.",
                        lambda s: _sc(s).fuel_tank.max_propellant_mass_kg,
                        lambda s, v: setattr(_sc(s).fuel_tank, "max_propellant_mass_kg", v),
                        0.001, 100.0, decimals=3, step=0.05, suffix=" kg",
                    ),
                ],
            ),
        ],
    ),
}


def get_wizard_spec(template_filename: str) -> Optional[TemplateWizardSpec]:
    """``None`` means this template has no curated wizard yet -- callers
    (``LoadScenarioWidget``) fall back to the plain "Open Template" flow,
    exactly as they did before this feature existed.
    """
    return _SPECS.get(template_filename)


class _WizardFieldPage(QWizardPage):
    def __init__(self, page_spec: WizardPageSpec, scenario: Scenario, parent=None):
        super().__init__(parent)
        self.setTitle(page_spec.title)
        self._scenario = scenario
        self._fields = page_spec.fields
        self._boxes: List[QDoubleSpinBox] = []

        layout = QFormLayout(self)
        intro = QLabel(page_spec.intro)
        intro.setWordWrap(True)
        layout.addRow(intro)

        for field_spec in self._fields:
            box = QDoubleSpinBox()
            box.setRange(field_spec.minimum, field_spec.maximum)
            box.setDecimals(field_spec.decimals)
            box.setSingleStep(field_spec.step)
            box.setSuffix(field_spec.suffix)
            box.setValue(field_spec.get(scenario))
            box.setToolTip(field_spec.help_text)
            help_label = QLabel(field_spec.help_text)
            help_label.setWordWrap(True)
            help_label.setStyleSheet("color: palette(mid); font-size: 90%;")
            layout.addRow(field_spec.label, box)
            layout.addRow("", help_label)
            self._boxes.append(box)

    def apply_to_scenario(self) -> None:
        """Writes every spin box's current value back into the Scenario
        this page was built from -- called on Finish (see
        TemplateCustomizeWizard.accept()), not live on every edit, so an
        in-progress Back/Next doesn't matter.
        """
        for field_spec, box in zip(self._fields, self._boxes):
            field_spec.set(self._scenario, box.value())


class TemplateCustomizeWizard(QWizard):
    """One page per :class:`WizardPageSpec` in ``spec.pages``, built from
    a COPY of ``base_scenario`` (see this module's own docstring for why
    a copy) -- call :meth:`result_scenario` after ``exec()`` returns
    ``QDialog.Accepted`` to get the customized ``Scenario``.
    """

    def __init__(self, base_scenario: Scenario, spec: TemplateWizardSpec, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Customize: {base_scenario.name}")
        self._scenario = Scenario.from_dict(base_scenario.to_dict())
        self._field_pages: List[_WizardFieldPage] = []
        for page_spec in spec.pages:
            page = _WizardFieldPage(page_spec, self._scenario, self)
            self._field_pages.append(page)
            self.addPage(page)

        # Real bug, found from a user screenshot: QWizard.sizeHint() does
        # NOT reflect its own pages' content at all -- it measured a flat
        # 500x360 here regardless of which spec/pages were given, while
        # this wizard's own busiest page ("Station-keeping controller")
        # needs 367x326 just for its fields, before QWizard's own
        # title/intro banner and Back/Next/Cancel row are added on top --
        # so several pages' intro text and field rows rendered clipped.
        # Sized from the widest/tallest PAGE across the whole wizard (not
        # just the one shown first), so paging through Back/Next never
        # needs a mid-flow resize -- plus fixed padding for QWizard's own
        # chrome, confirmed by actually rendering every page in this
        # wizard and checking nothing clips.
        widest_page = max((p.sizeHint().width() for p in self._field_pages), default=0)
        tallest_page = max((p.sizeHint().height() for p in self._field_pages), default=0)
        self.resize(max(500, widest_page + 60), max(420, tallest_page + 220))

    def accept(self) -> None:
        for page in self._field_pages:
            page.apply_to_scenario()
        super().accept()

    def result_scenario(self) -> Scenario:
        return self._scenario
