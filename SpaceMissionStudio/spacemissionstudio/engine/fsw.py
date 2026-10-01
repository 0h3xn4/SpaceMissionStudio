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
Phase 2: builds the attitude navigation/guidance/control/actuation module
chain for one spacecraft -- kept separate from ``engine/service.py`` so
that file stays orchestration-only (build gravity, build spacecraft, call
into here once per spacecraft that wants attitude control).

Every call sequence below (module class names, attribute names,
``subscribeTo`` message wiring) is copied from an ACTUALLY RUNNING example
script in this checkout, not written from memory or guessed, per this
project's "never fabricate a Basilisk API" rule:

* ``simpleNav``, ``inertial3D`` + ``attTrackingError`` + ``mrpFeedback`` +
  ``rwMotorTorque`` + ``reactionWheelStateEffector`` + ``VehicleConfigMsg``:
  ``examples/scenarioAttitudeFeedbackRW.py``.
* ``hillPoint``, ``extForceTorque`` (idealized actuation) +
  ``scObject.addDynamicEffector``: ``examples/scenarioAttitudeGuidance.py``.
* ``velocityPoint``: ``examples/scenarioHohmann.py``.
* ``locationPointing`` + ``groundLocation.GroundLocation``:
  ``examples/scenarioAttLocPoint.py``.
* ``sunSafePoint`` (``sHatBdyCmd``/``minUnitMag``/``sunDirectionInMsg``/
  ``imuInMsg``): ``src/fswAlgorithms/attGuidance/sunSafePoint/_UnitTest/test_sunSafePoint.py``.
  ``sunSafePoint.imuInMsg`` is REQUIRED (``sunSafePoint.c`` raises
  ``BSK_ERROR`` via an ``isLinked()`` check if it is not connected) --
  confirmed by reading that source directly, not assumed. Both
  ``sunDirectionInMsg`` and ``imuInMsg`` are the same ``NavAttMsgPayload``
  type and ``simpleNav``'s single ``attOutMsg`` already carries both the
  ``vehSunPntBdy`` sun-heading field and ``omega_BN_B``, so both subscribe
  to the same ``simpleNav`` output -- there is no second sensor needed.
* ``magneticFieldWMM`` (``configureWMMFile``, ``addSpacecraftToModel``,
  ``envOutMsgs[i]`` indexed by call order):
  ``src/simulation/environment/magneticFieldWMM/_UnitTest/test_magneticFieldWMM.py``
  and that module's own ``.rst`` user guide.
* ``thrusterDynamicEffector`` + ``simIncludeThruster.thrusterFactory()`` +
  ``thrForceMapping`` + ``thrFiringSchmitt`` (the "thruster" actuator kind's
  control-torque path, replacing ``rwMotorTorque``/
  ``reactionWheelStateEffector``): ``examples/scenarioAttitudeFeedback2T_TH.py``.
* ``MtbEffector`` + ``tamComm`` + ``mtbMomentumManagement`` (continuous
  RW momentum management via magnetic torque rods,
  :func:`build_mtb_desaturation`), including the real, un-doctored
  ``rwMotorTorqueOutMsg``-sits-between-``rwMotorTorque``-and-the-RW
  -hardware wiring: ``examples/scenarioMtbMomentumManagement.py``, run
  directly against a real Basilisk build to confirm the exact wiring
  works (see this feature's ``HISTORY.md`` entry for the actual
  numbers) -- notably WITHOUT a ``magneticFieldWMM.epochInMsg``
  subscription, matching this file's own pre-existing
  ``build_magnetic_field_wmm()`` precedent (confirmed that omitting it,
  unlike the shipped example which sets one, does not break anything).
* ``thrMomentumManagement`` + ``thrForceMapping`` (momentum-dump mode,
  ``angErrThresh`` > pi) + ``thrMomentumDumping`` (RW desaturation via
  thrusters, :func:`build_momentum_dumping`), including the "re-``Reset()``
  after the first real tick" requirement that function's own docstring
  documents: ``examples/scenarioMomentumDumping.py``, and confirmed
  directly by running both with and without that extra ``Reset()`` call
  against a real Basilisk build (not assumed from the example's comment
  alone) -- see this feature's ``HISTORY.md`` entry for the actual
  before/after numbers.

Scoping decisions made explicit here (see ``engine/service.py``'s Phase 2
docstring for the full list):

* ``hillPoint``/``velocityPoint`` do NOT subscribe ``celBodyInMsg``: every
  orbit IC in this app is already given relative to ``gravity.central_body``
  (``central_body.isCentralBody = True``, matching every example scenario
  in this checkout), so the spacecraft's own ``r_BN_N``/``v_BN_N`` from
  ``simpleNav.transOutMsg`` is central-body-relative -- leaving
  ``celBodyInMsg`` unlinked is correct here, not a missing feature (see
  ``hillPoint.h``'s ``planetMsgIsLinked`` flag, which exists precisely to
  make this optional). This DEPENDS on ``engine/service.py`` setting
  ``spice_object.zeroBase = gravity.central_body`` (see that module's
  ``build()``): without it, the central body's own SPICE-linked position
  gets added into every spacecraft's ``r_BN_N``/``v_BN_N``
  (``GravityEffector::updateInertialPosAndVel()`` in
  ``gravityEffector.cpp`` always adds the central body's own position on
  top of the propagated central-body-relative state), which would make
  this assumption false again -- a real bug this project shipped and only
  caught once Basilisk actually ran end-to-end (see ``engine/service.py``'s
  ``zeroBase`` comment for the full explanation).
* ``locationPointing``'s ``fsw_params["target_body"]`` (point at a
  celestial body directly, vs. a ground station) is built via
  :func:`build_ephemeris_converter` (``SpicePlanetStateMsg`` ->
  ``EphemerisMsg``, confirmed against
  ``examples/scenarioAsteroidArrival.py``'s own usage) feeding
  ``locationPointing.celBodyInMsg`` -- ``engine.service`` builds one
  converter per targeted body from ``gravity.central_body``/
  ``gravity.third_body_perturbers``'s already-SPICE-tracked state
  messages, same source ``build_css_sun_estimation``'s sun direction and
  ``simpleNav``'s own truth sun heading already use.
* The attitude control loop is closed on TRUTH spacecraft state
  (``simpleNav``'s error model defaults to zero, i.e. ``PMatrix``/noise are
  left at Basilisk's own zero defaults unless a future phase adds a GUI/
  schema field for them) -- ``simpleNav`` is still the module in the loop
  (not raw ``scStateOutMsg``), so wiring in real navigation error later is
  a matter of setting its ``PMatrix``, not restructuring this chain.

Verification status: same as ``engine/service.py`` -- cannot be executed in
this development sandbox (no Basilisk build here), written directly
against the verified call sequences cited above.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np

from Basilisk.architecture import messaging
from Basilisk.fswAlgorithms import (
    attTrackingError,
    cssWlsEst,
    hillPoint,
    inertial3D,
    locationPointing,
    mrpFeedback,
    rwMotorTorque,
    sunSafePoint,
    tamComm,
    thrFiringSchmitt,
    thrForceMapping,
    thrMomentumDumping,
    thrMomentumManagement,
    mtbMomentumManagement,
    velocityPoint,
)
from Basilisk.simulation import (
    coarseSunSensor,
    ephemerisConverter,
    extForceTorque,
    fuelTank,
    groundLocation,
    imuSensor,
    magnetometer,
    magneticFieldWMM,
    MtbEffector,
    reactionWheelStateEffector,
    simpleNav,
    starTracker,
    thrusterDynamicEffector,
)
from Basilisk.utilities import simIncludeRW, simIncludeThruster

from ..schema.scenario import SUPPORTED_FSW_MODES

DEFAULT_MRP_GAINS: Dict[str, float] = {"K": 3.5, "P": 30.0}

# DEFAULT_MRP_GAINS is lifted directly from Basilisk's own examples/BskSim
# reference (BSK_Fsw.py's mrpFeedbackRWs), tuned for THAT example's
# 900 kg*m^2 spacecraft (BSK_Dynamics.py's I_sc) at its fswRate=0.1.
# Applied unscaled to a much smaller spacecraft (this app's own schema
# default inertia is 10 kg*m^2 -- 90x smaller), the resulting discrete-time
# control update is wildly over-aggressive for the body's actual rotational
# inertia and reliably reaches NaN within seconds (root-caused and fixed,
# by hand, per-template, in HISTORY.md's "attitude determination pipeline"
# entry -- this constant generalizes that same fix to every spacecraft by
# default, not just the templates it was manually applied to).
_MRP_GAIN_REFERENCE_INERTIA_KG_M2 = 900.0


def _default_mrp_gains_for_inertia(inertia_kg_m2: Optional[List[float]]) -> Dict[str, float]:
    """``DEFAULT_MRP_GAINS`` scaled by a spacecraft's own (isotropic-
    equivalent) inertia relative to the 900 kg*m^2 reference it was tuned
    for -- confirmed in HISTORY.md to converge cleanly where the unscaled
    gains diverge to NaN, for both RW- and thruster-actuated spacecraft.
    ``inertia_kg_m2`` is the row-major 3x3 hub inertia
    (``SpacecraftConfig.inertia_kg_m2``); its trace/3 is used as the
    scaling quantity so an anisotropic inertia still gets a sensible
    scalar gain pair (``mrpFeedback``'s K/P are themselves scalars, not
    per-axis). Falls back to the unscaled reference gains if no inertia is
    given (callers that have no spacecraft inertia in scope).
    """
    if not inertia_kg_m2:
        return dict(DEFAULT_MRP_GAINS)
    mean_inertia = (inertia_kg_m2[0] + inertia_kg_m2[4] + inertia_kg_m2[8]) / 3.0
    if mean_inertia <= 0.0:  # unreachable if Scenario.validate() passed
        return dict(DEFAULT_MRP_GAINS)
    scale = mean_inertia / _MRP_GAIN_REFERENCE_INERTIA_KG_M2
    return {"K": DEFAULT_MRP_GAINS["K"] * scale, "P": DEFAULT_MRP_GAINS["P"] * scale}

# RW factory create() kwargs that must be Python float (rwFactory.create()
# calls exit(1) directly -- not a raised exception -- on a type mismatch;
# see simIncludeRW.py's own isinstance(..., float) checks), so any of
# these coming from JSON-loaded params (which may deserialize as int) are
# coerced defensively before being passed through.
_RW_FLOAT_KWARGS = (
    "Omega", "Omega_max", "maxMomentum", "P_max", "betaStatic",
    "fCoulomb", "fStatic", "cViscous", "u_min", "u_max", "Js",
)

# thrusterFactory.create() kwargs that must be Python float, same
# isinstance(..., float)-then-exit(1) hazard as _RW_FLOAT_KWARGS above
# (see simIncludeThruster.py's own checks) -- coerced defensively for the
# same reason.
_THRUSTER_FLOAT_KWARGS = (
    "areaNozzle", "steadyIsp", "MaxThrust", "thrusterMagDisp", "MinOnTime",
    "cutoffFrequency", "MaxSwirlTorque",
)


class FswError(Exception):
    """Raised for an FSW configuration this module cannot (yet) build --
    always names the specific unsupported combination.
    """


def build_simple_nav(scSim, task_name: str, tag: str, sc_object, sun_state_out_msg=None):
    """Always built for any spacecraft with ``fsw_mode`` set -- the
    truth-to-navigation-message bridge every guidance mode reads from (see
    module docstring). ``sun_state_out_msg`` is the central SPICE
    interface's per-body output message for "sun" (only when "sun" is
    SPICE-tracked in this scenario); when given, ``simpleNav`` populates
    ``NavAttMsgPayload.vehSunPntBdy`` (verified directly in
    ``simpleNav.cpp``'s ``computeTrueOutput()``), which ``sunSafePoint``
    and any ``coarse_sun_sensor`` need.
    """
    nav = simpleNav.SimpleNav()
    nav.ModelTag = f"{tag}_simpleNav"
    nav.scStateInMsg.subscribeTo(sc_object.scStateOutMsg)
    if sun_state_out_msg is not None:
        nav.sunStateInMsg.subscribeTo(sun_state_out_msg)
    scSim.AddModelToTask(task_name, nav)
    return nav


def _wrap_with_att_tracking_error(scSim, task_name: str, tag: str, att_ref_out_msg, nav):
    """``inertial3D``/``hillPoint``/``velocityPoint`` only produce an
    ``AttRefMsg`` (a reference, not yet an error relative to the actual
    spacecraft attitude) -- ``mrpFeedback`` needs an ``AttGuidMsg``, so
    every one of those three modes is routed through this same
    ``attTrackingError`` step. ``sunSafePoint``/``locationPointing``
    produce ``AttGuidMsg`` directly and skip this (see ``build_guidance``).
    """
    err = attTrackingError.attTrackingError()
    err.ModelTag = f"{tag}_attTrackingError"
    err.attNavInMsg.subscribeTo(nav.attOutMsg)
    err.attRefInMsg.subscribeTo(att_ref_out_msg)
    scSim.AddModelToTask(task_name, err)
    return err.attGuidOutMsg


def build_css_sun_estimation(scSim, task_name: str, tag: str, sc_object, css_sensor_configs: List,
                              sun_state_out_msg):
    """Real sun-heading ESTIMATION (not truth) from a spacecraft's own
    ``coarse_sun_sensor`` hardware: a dedicated ``CSSConstellation`` (one
    ``CoarseSunSensor`` device per entry in ``css_sensor_configs``, same
    ``nHat_B``/``fov_deg``/``noise_std`` params as :func:`attach_sensors`
    builds for the user-visible sensor of the same name) feeds
    ``cssWlsEst``'s weighted-least-squares sun-direction estimator.
    Returns ``cssWlsEst.navStateOutMsg`` (``NavAttMsg``-typed, directly
    compatible with ``sunSafePoint.sunDirectionInMsg`` -- see
    :func:`build_guidance`'s ``sun_direction_override_msg`` parameter).

    This dedicated CSS cluster is intentionally separate from
    :func:`attach_sensors`'s own per-sensor ``coarse_sun_sensor`` output
    messages, same reasoning as :func:`build_mtb_desaturation`'s dedicated
    TAM: those exist for user-visible per-sensor telemetry (one message
    per sensor); ``cssWlsEst`` needs ONE aggregate ``CSSArraySensorMsgPayload``
    across the whole cluster, which only Basilisk's ``CSSConstellation``
    container produces (confirmed directly against
    ``examples/BskSim/models/BSK_Dynamics.py``'s/``BSK_Fsw.py``'s own
    ``SetCSSConstellation()``/``SetCSSWlsEst()`` -- notably, individual
    ``CoarseSunSensor`` devices are NEVER added to the sim task directly
    in that reference; only the ``CSSConstellation`` container is, which
    drives each device's own update internally).

    Verification note: confirmed directly against a real Basilisk build
    that this chain's accuracy is governed entirely by sensor GEOMETRY
    (how many of the cluster's sensors are actually sunlit for a given
    sun direction, not a module bug) -- a sun direction illuminating only
    2 of this function's 8-sensor layout gave a 14.5-degree error (an
    under-determined 3-axis WLS fit from too few active sensors), while a
    direction illuminating 4 gave an EXACT match (0.0-degree error, zero
    sensor noise). Real spacecraft CSS clusters have exactly this
    direction-dependent coverage gap; it is not something to "fix" here.

    Returns ``(nav_state_out_msg, css_devices)`` -- the SECOND element is
    NOT optional to discard. Caught directly as a real, reproducible
    segfault: ``CSSConstellation.sensorList`` does not take ownership of
    the ``CoarseSunSensor`` Python objects assigned to it (only a
    reference) -- if ``css_devices`` is a purely-local list (e.g. this
    function's own, if it didn't return it), Python garbage-collects the
    devices once the function returns, and Basilisk segfaults inside
    ``InitializeSimulation()``/``ExecuteSimulation()`` on the now-dangling
    reference, with no error message pointing at the cause. Confirmed by
    reproducing it both ways (segfaults when discarded, works when kept
    alive) against a real Basilisk build -- the same category of lifetime
    hazard this codebase's own Vizard wiring already documents
    (``access_indicator_bridges``/``generic_storage_list``/
    ``generic_sensor_list`` -- "the caller MUST keep ALL FOUR alive").
    The caller must hold this list alive for as long as the simulation
    runs (e.g. as an attribute on a long-lived object), exactly like
    those Vizard lists.
    """
    css_devices = []
    for sensor in css_sensor_configs:
        css = coarseSunSensor.CoarseSunSensor()
        css.ModelTag = f"{tag}_{sensor.name}_est"
        css.nHat_B = [float(v) for v in sensor.params["nHat_B"]]
        css.fov = np.radians(float(sensor.params.get("fov_deg", 90.0)) / 2.0)
        css.senNoiseStd = float(sensor.params.get("noise_std", 0.0))
        css.sunInMsg.subscribeTo(sun_state_out_msg)
        css.stateInMsg.subscribeTo(sc_object.scStateOutMsg)
        css_devices.append(css)

    constellation = coarseSunSensor.CSSConstellation()
    constellation.ModelTag = f"{tag}_cssConstellation_est"
    constellation.sensorList = coarseSunSensor.CSSVector(css_devices)
    scSim.AddModelToTask(task_name, constellation)

    css_config_payload = messaging.CSSConfigMsgPayload(
        nCSS=len(css_devices),
        cssVals=[
            messaging.CSSUnitConfigMsgPayload(CBias=1.0, nHat_B=[float(v) for v in sensor.params["nHat_B"]])
            for sensor in css_sensor_configs
        ],
    )
    css_config_msg = messaging.CSSConfigMsg().write(css_config_payload)

    estimator = cssWlsEst.cssWlsEst()
    estimator.ModelTag = f"{tag}_cssWlsEst"
    estimator.cssDataInMsg.subscribeTo(constellation.constellationOutMsg)
    estimator.cssConfigInMsg.subscribeTo(css_config_msg)
    scSim.AddModelToTask(task_name, estimator)

    return estimator.navStateOutMsg, css_devices


def build_ephemeris_converter(scSim, task_name: str, tag: str, body_name: str, planet_state_msg):
    """Converts a single SPICE-sourced ``SpicePlanetStateMsg`` into the
    ``EphemerisMsg`` ``locationPointing.celBodyInMsg`` needs for direct
    celestial-body pointing (``fsw_params['target_body']``) -- confirmed
    against ``examples/scenarioAsteroidArrival.py``'s own
    ``ephemerisConverter`` + ``locationPointing`` usage (that example calls
    ``addSpiceInputMsg()`` once per body on a single shared converter and
    indexes ``ephemOutMsgs`` by call order; this builds one dedicated
    converter per target body instead, trading a few extra trivial
    pass-through modules for never needing that index bookkeeping across
    spacecraft/targets).

    Returns the single ``EphemerisMsg`` this converter produces.
    """
    converter = ephemerisConverter.EphemerisConverter()
    converter.ModelTag = f"{tag}_ephemConverter_{body_name}"
    converter.addSpiceInputMsg(planet_state_msg)
    scSim.AddModelToTask(task_name, converter)
    return converter.ephemOutMsgs[0]


def build_guidance(scSim, task_name: str, tag: str, fsw_mode: str, fsw_params: dict, nav, mu: float,
                    ground_locations: Dict[str, object], sun_direction_override_msg=None,
                    target_body_eph_msg=None):
    """Builds the guidance mode named by ``fsw_mode`` (one of
    :data:`schema.scenario.SUPPORTED_FSW_MODES`) and returns its
    ``AttGuidMsg``-typed output message, ready for :func:`build_mrp_feedback`.

    Args:
        ground_locations: ``{ground_station_name: groundLocation.GroundLocation}``
            for every ``GroundStationConfig`` already built for this
            scenario's central body -- only consulted for ``"locationPointing"``.
        sun_direction_override_msg: ``"sunSafePoint"`` only -- when given (a
            ``NavAttMsg``-typed message, e.g. :func:`build_css_sun_estimation`'s
            ``navStateOutMsg`` return value), ``sunDirectionInMsg`` subscribes
            to THIS instead of ``nav.attOutMsg`` (truth). ``imuInMsg`` (body
            rate) still always reads truth either way -- CSS-WLS estimates
            sun-heading only, not rate; see module docstring's "attitude
            control loop closes on truth" note for why rate stays
            unestimated.
        target_body_eph_msg: ``"locationPointing"`` only, required exactly
            when ``fsw_params['target_body']`` is set (xor'd against
            ``target_ground_station`` by ``Scenario.validate()``) -- an
            ``EphemerisMsg``-typed message (e.g.
            :func:`build_ephemeris_converter`'s return value) subscribed to
            ``celBodyInMsg`` for direct celestial-body pointing, confirmed
            against ``examples/scenarioAsteroidArrival.py``'s own
            ``locationPointing`` + ``ephemerisConverter`` usage.
    """
    if fsw_mode not in SUPPORTED_FSW_MODES:
        raise FswError(f"fsw_mode {fsw_mode!r} must be one of {SUPPORTED_FSW_MODES}")  # unreachable if validated

    if fsw_mode == "inertial3D":
        mod = inertial3D.inertial3D()
        mod.ModelTag = f"{tag}_inertial3D"
        mod.sigma_R0N = list(fsw_params.get("sigma_R0N", [0.0, 0.0, 0.0]))
        scSim.AddModelToTask(task_name, mod)
        return _wrap_with_att_tracking_error(scSim, task_name, tag, mod.attRefOutMsg, nav)

    if fsw_mode == "hillPoint":
        mod = hillPoint.hillPoint()
        mod.ModelTag = f"{tag}_hillPoint"
        mod.transNavInMsg.subscribeTo(nav.transOutMsg)
        scSim.AddModelToTask(task_name, mod)
        return _wrap_with_att_tracking_error(scSim, task_name, tag, mod.attRefOutMsg, nav)

    if fsw_mode == "velocityPoint":
        mod = velocityPoint.velocityPoint()
        mod.ModelTag = f"{tag}_velocityPoint"
        mod.mu = mu
        mod.transNavInMsg.subscribeTo(nav.transOutMsg)
        scSim.AddModelToTask(task_name, mod)
        return _wrap_with_att_tracking_error(scSim, task_name, tag, mod.attRefOutMsg, nav)

    if fsw_mode == "sunSafePoint":
        mod = sunSafePoint.sunSafePoint()
        mod.ModelTag = f"{tag}_sunSafePoint"
        mod.sHatBdyCmd = list(fsw_params.get("sHatBdyCmd", [0.0, 0.0, 1.0]))
        mod.minUnitMag = float(fsw_params.get("min_unit_mag", 0.1))
        mod.sunAxisSpinRate = float(fsw_params.get("sun_axis_spin_rate_rad_s", 0.0))
        mod.sunDirectionInMsg.subscribeTo(
            sun_direction_override_msg if sun_direction_override_msg is not None else nav.attOutMsg
        )
        mod.imuInMsg.subscribeTo(nav.attOutMsg)  # see module docstring: same NavAttMsgPayload, both fields needed
        scSim.AddModelToTask(task_name, mod)
        return mod.attGuidanceOutMsg

    if fsw_mode == "locationPointing":
        mod = locationPointing.locationPointing()
        mod.ModelTag = f"{tag}_locationPointing"
        mod.pHat_B = list(fsw_params.get("pHat_B", [0.0, 0.0, 1.0]))
        mod.useBoresightRateDamping = 1
        mod.scAttInMsg.subscribeTo(nav.attOutMsg)
        mod.scTransInMsg.subscribeTo(nav.transOutMsg)
        if fsw_params.get("target_body"):
            # Scenario.validate() already guarantees target_body_eph_msg is
            # given whenever fsw_params['target_body'] is set (xor'd against
            # target_ground_station) -- see engine.service's own build()
            # wiring, which builds the ephemerisConverter this subscribes to.
            if target_body_eph_msg is None:  # unreachable if validate() passed
                raise FswError("locationPointing fsw_params['target_body'] needs target_body_eph_msg")
            mod.celBodyInMsg.subscribeTo(target_body_eph_msg)
        else:
            target_name = fsw_params.get("target_ground_station")
            ground_location = ground_locations.get(target_name)
            if ground_location is None:  # unreachable if Scenario.validate() passed
                raise FswError(f"locationPointing target_ground_station {target_name!r} has no built GroundLocation")
            mod.locationInMsg.subscribeTo(ground_location.currentGroundStateOutMsg)
        scSim.AddModelToTask(task_name, mod)
        return mod.attGuidOutMsg

    raise FswError(f"fsw_mode {fsw_mode!r} is schema-valid but has no engine.fsw builder")  # unreachable


def build_vehicle_config_msg(inertia_kg_m2: List[float]):
    """The ``VehicleConfigMsg`` ``mrpFeedback`` needs for its gyroscopic
    RW-coupling term -- built with the SAME inertia as the simulated
    spacecraft hub (``sc_object.hub.IHubPntBc_B``), matching
    ``examples/scenarioAttitudeFeedbackRW.py``'s "use the same inertia in
    the FSW algorithm as in the simulation" comment (this app has no
    separate FSW-vs-truth inertia model yet, so they are always equal).
    """
    payload = messaging.VehicleConfigMsgPayload(ISCPntB_B=list(inertia_kg_m2))
    return messaging.VehicleConfigMsg().write(payload)


def build_mrp_feedback(scSim, task_name: str, tag: str, guid_out_msg, veh_config_msg, control_params: dict,
                        rw_config_msg=None, rw_speed_out_msg=None, inertia_kg_m2: Optional[List[float]] = None):
    """``mrpFeedback``'s "simple mode" control law (Ki < 0 disables the
    integral feedback term, matching every example's default). RW
    gyroscopic compensation is enabled automatically whenever
    ``rw_config_msg``/``rw_speed_out_msg`` are given (reaction-wheel
    actuation path); left ``None`` for the idealized-torque path.

    K/P default to ``DEFAULT_MRP_GAINS`` scaled by ``inertia_kg_m2`` (see
    ``_default_mrp_gains_for_inertia``) rather than the raw reference
    values whenever ``control_params`` doesn't explicitly set them --
    the unscaled reference gains are tuned for a 900 kg*m^2 spacecraft and
    reliably diverge to NaN on this app's much smaller schema-default
    inertia (confirmed in HISTORY.md). Passing ``control_params={"K":
    ..., "P": ...}`` always overrides this, same as before.
    """
    default_gains = _default_mrp_gains_for_inertia(inertia_kg_m2)
    mrp = mrpFeedback.mrpFeedback()
    mrp.ModelTag = f"{tag}_mrpFeedback"
    mrp.K = float(control_params.get("K", default_gains["K"]))
    mrp.P = float(control_params.get("P", default_gains["P"]))
    mrp.Ki = float(control_params.get("Ki", -1.0))
    mrp.integralLimit = float(control_params.get("integral_limit", 0.0))
    mrp.guidInMsg.subscribeTo(guid_out_msg)
    mrp.vehConfigInMsg.subscribeTo(veh_config_msg)
    if rw_config_msg is not None:
        mrp.rwParamsInMsg.subscribeTo(rw_config_msg)
        mrp.rwSpeedsInMsg.subscribeTo(rw_speed_out_msg)
    scSim.AddModelToTask(task_name, mrp)
    return mrp


def build_idealized_actuation(scSim, task_name: str, tag: str, sc_object, mrp_feedback_module):
    """Idealized direct-torque actuation: ``mrpFeedback``'s commanded
    torque is applied straight to the hub via ``extForceTorque``, with no
    actuator hardware (no saturation, no momentum buildup, no motor
    dynamics) -- the default when a spacecraft has ``fsw_mode`` set but no
    ``"reaction_wheel"`` actuators. Matches
    ``examples/scenarioAttitudeGuidance.py``.
    """
    ext = extForceTorque.ExtForceTorque()
    ext.ModelTag = f"{tag}_extForceTorque"
    ext.cmdTorqueInMsg.subscribeTo(mrp_feedback_module.cmdTorqueOutMsg)
    sc_object.addDynamicEffector(ext)
    scSim.AddModelToTask(task_name, ext)
    return ext


def _coerce_rw_kwargs(params: dict) -> dict:
    kwargs = {k: v for k, v in params.items() if k not in ("gsHat_B", "rw_type")}
    for key in _RW_FLOAT_KWARGS:
        if key in kwargs:
            kwargs[key] = float(kwargs[key])
    if "rWB_B" in kwargs:
        kwargs["rWB_B"] = [float(v) for v in kwargs["rWB_B"]]
    return kwargs


def build_reaction_wheels(scSim, task_name: str, tag: str, sc_object, actuator_configs: List):
    """Builds one reaction wheel per ``ActuatorConfig(kind="reaction_wheel")``
    entry via ``simIncludeRW.rwFactory()`` (see that module for every
    accepted ``params`` key -- ``gsHat_B`` is required by schema validation,
    everything else is optional and defaults exactly as ``rwFactory.create()``
    itself defaults). Returns ``(rw_state_effector, rw_config_msg)`` for
    :func:`build_rw_motor_torque`/:func:`build_mrp_feedback` and Vizard.

    RW device labels use ``"RW1"``, ``"RW2"``, ... (the module's own
    auto-labeling scheme) rather than ``actuator.name``, because
    ``rwFactory.create()`` hard-rejects any label longer than 5 characters
    -- ``actuator.name`` stays the identifier on the SpaceMissionStudio side
    (schema, results) and is never passed into Basilisk as the RW label.
    """
    rw_factory = simIncludeRW.rwFactory()
    for actuator in actuator_configs:
        params = actuator.params
        gsHat_B = [float(v) for v in params["gsHat_B"]]
        rw_type = params.get("rw_type", "custom")
        kwargs = _coerce_rw_kwargs(params)
        rw_factory.create(rw_type, gsHat_B, **kwargs)

    rw_state_effector = reactionWheelStateEffector.ReactionWheelStateEffector()
    rw_state_effector.ModelTag = f"{tag}_reactionWheels"
    rw_factory.addToSpacecraft(rw_state_effector.ModelTag, rw_state_effector, sc_object)
    # Priority 20 > engine.service's spacecraft priority (10): higher
    # priority runs first in a Basilisk task, and the RW effector's
    # UpdateState() must publish a fresh rwSpeedOutMsg before anything else
    # in this same step reads it (mrpFeedback's rwSpeedsInMsg in
    # particular) -- the effectors -> dynamics -> sensors ordering rule
    # from examples/scenarioAttitudeFeedbackRW.py, re-derived here for
    # THIS app's own priority scheme rather than copying its literal
    # numbers (which used spacecraft priority 1, not 10).
    scSim.AddModelToTask(task_name, rw_state_effector, 20)
    rw_config_msg = rw_factory.getConfigMessage()
    return rw_factory, rw_state_effector, rw_config_msg


def _coerce_thruster_kwargs(params: dict) -> dict:
    kwargs = {k: v for k, v in params.items() if k not in ("r_B", "tHat_B", "thruster_type")}
    for key in _THRUSTER_FLOAT_KWARGS:
        if key in kwargs:
            kwargs[key] = float(kwargs[key])
    return kwargs


def build_thrusters(scSim, task_name: str, tag: str, sc_object, actuator_configs: List):
    """Builds one thruster per ``ActuatorConfig(kind="thruster")`` entry via
    ``simIncludeThruster.thrusterFactory()`` (see that module for every
    accepted ``params`` key -- ``r_B``/``tHat_B``/``MaxThrust`` are required
    by schema validation, everything else is optional and defaults exactly
    as ``thrusterFactory.create()`` itself defaults). Returns
    ``(thruster_effector, thr_config_msg)`` for
    :func:`build_thruster_force_mapping` and Vizard.

    ``thruster_type`` defaults to ``"Blank_Thruster"`` -- ``thrusterFactory``
    has no bare "custom" type the way ``rwFactory`` does (confirmed by
    reading ``simIncludeThruster.py`` directly: every named type method sets
    some defaults, and an UNRECOGNIZED type name makes ``create()`` call
    ``exit(1)`` -- not raise -- which would kill the whole GUI process, not
    just fail validation); ``Blank_Thruster`` is that module's own
    "no type-specific defaults, rely on kwargs" entry, the direct equivalent.
    Matches ``examples/scenarioAttitudeFeedback2T_TH.py``'s thruster setup.
    """
    thr_factory = simIncludeThruster.thrusterFactory()
    for actuator in actuator_configs:
        params = actuator.params
        r_B = [float(v) for v in params["r_B"]]
        tHat_B = [float(v) for v in params["tHat_B"]]
        thruster_type = params.get("thruster_type", "Blank_Thruster")
        kwargs = _coerce_thruster_kwargs(params)
        thr_factory.create(thruster_type, r_B, tHat_B, **kwargs)

    thruster_effector = thrusterDynamicEffector.ThrusterDynamicEffector()
    thruster_effector.ModelTag = f"{tag}_thrusters"
    thr_factory.addToSpacecraft(thruster_effector.ModelTag, thruster_effector, sc_object)
    # Same priority reasoning as build_reaction_wheels: must run before
    # mrpFeedback/thrForceMapping read anything derived from it this tick.
    scSim.AddModelToTask(task_name, thruster_effector, 20)
    thr_config_msg = thr_factory.getConfigMessage()
    return thr_factory, thruster_effector, thr_config_msg


def build_fuel_tank(scSim, task_name: str, tag: str, sc_object, thruster_effector, fuel_tank_config):
    """Real propellant depletion for ``thruster_effector`` -- Basilisk's
    ``fuelTank`` state effector (``FuelTankModelUniformBurn``, the
    "fuel mass depletes directly, no slosh/CoM-within-tank modeling"
    model), tied to the thruster hardware via ``fuelTank.addThrusterSet()``
    so it reads the SAME mass-flow rate the thruster hardware already
    computes for its own physics each tick (``mDot = F / (steadyIsp *
    g0)``, confirmed directly in ``thrusterDynamicEffector.cpp``) and
    depletes ``hub.mHub`` by exactly that amount -- unlike
    ``engine.orbit_maintenance``'s hand-rolled Python propellant
    bookkeeping (an explicit-Euler rocket-equation estimate fed back into
    ``hub.mHub`` manually, used for station-keeping/phasing/
    constant-thrust burns), this is Basilisk's own effector, including
    the resulting center-of-mass shift as propellant depletes. Matches
    ``examples/MultiSatBskSim/modelsMultiSat/BSK_MultiSatDynamics.py``'s
    own ``SetFuelTank()``.

    ``schema.scenario.FuelTankConfig.tank_position_b_m`` is the tank's
    OWN position in the body frame (``setR_TB_B``) -- a materially
    different vector from the thruster nozzle positions
    (``ActuatorConfig(kind="thruster").params["r_B"]``) already set in
    :func:`build_thrusters`; both matter for a fully physical model (the
    nozzle position for thrust/torque, the tank position for the
    propellant's own contribution to the hub's center of mass), so
    neither can stand in for the other.

    Returns the ``fuelTank.FuelTank()`` state effector itself (its
    ``fuelTankOutMsg`` -- a real ``FuelTankMsgPayload`` -- is what
    ``engine.service`` records for the ``{name}.fuel_mass_remaining``
    result series and any live Vizard propellant gauge).
    """
    tank_model = fuelTank.FuelTankModelUniformBurn()
    tank_model.propMassInit = float(fuel_tank_config.propellant_mass_kg)
    tank_model.maxFuelMass = float(fuel_tank_config.max_propellant_mass_kg)
    tank_model.r_TcT_TInit = [[0.0], [0.0], [0.0]]

    tank = fuelTank.FuelTank()
    tank.ModelTag = f"{tag}_fuelTank"
    tank.setTankModel(tank_model)
    tank.setR_TB_B([[float(v)] for v in fuel_tank_config.tank_position_b_m])
    tank.addThrusterSet(thruster_effector)

    sc_object.addStateEffector(tank)
    scSim.AddModelToTask(task_name, tank, 20)
    return tank


def build_thruster_force_mapping(scSim, task_name: str, tag: str, mrp_feedback_module, thr_config_msg,
                                  veh_config_msg, thruster_effector):
    """Maps ``mrpFeedback``'s 3D torque command onto individual thruster
    on-times: ``thrForceMapping`` (torque -> per-thruster force) followed by
    ``thrFiringSchmitt`` (force -> Schmitt-trigger on-time logic), connected
    to the thruster hardware's command input. ``thrForceSign = 1`` and
    Schmitt-trigger ``thrMinFireTime``/``level_on``/``level_off`` match
    ``examples/scenarioAttitudeFeedback2T_TH.py``'s single-cluster (ACS
    -only) case -- this app only ever builds one thruster cluster per
    spacecraft, never that example's separate ACS/DV split.
    """
    force_mapping = thrForceMapping.thrForceMapping()
    force_mapping.ModelTag = f"{tag}_thrForceMapping"
    force_mapping.controlAxes_B = [1, 0, 0, 0, 1, 0, 0, 0, 1]
    force_mapping.thrForceSign = 1
    force_mapping.cmdTorqueInMsg.subscribeTo(mrp_feedback_module.cmdTorqueOutMsg)
    force_mapping.thrConfigInMsg.subscribeTo(thr_config_msg)
    force_mapping.vehConfigInMsg.subscribeTo(veh_config_msg)
    scSim.AddModelToTask(task_name, force_mapping)

    firing_logic = thrFiringSchmitt.thrFiringSchmitt()
    firing_logic.ModelTag = f"{tag}_thrFiringSchmitt"
    firing_logic.thrMinFireTime = 0.002  # [s]
    firing_logic.level_on = 0.75  # [-] duty-cycle fraction (of thrMinFireTime) above which a thruster turns on
    firing_logic.level_off = 0.25  # [-] duty-cycle fraction below which a thruster turns back off
    firing_logic.thrConfInMsg.subscribeTo(thr_config_msg)
    firing_logic.thrForceInMsg.subscribeTo(force_mapping.thrForceCmdOutMsg)
    scSim.AddModelToTask(task_name, firing_logic)

    thruster_effector.cmdsInMsg.subscribeTo(firing_logic.onTimeOutMsg)
    return force_mapping, firing_logic


def build_momentum_dumping(scSim, task_name: str, tag: str, rw_config_msg, rw_speed_out_msg, thr_config_msg,
                            veh_config_msg, thruster_effector, config):
    """Reaction-wheel momentum desaturation via thrusters --
    ``thrMomentumManagement`` (how much momentum to dump) ->
    ``thrForceMapping`` (momentum -> per-thruster impulse, ``angErrThresh``
    set above pi to disable the torque-command scaling that module
    normally does -- see its own docs, this is the documented way to reuse
    it for an impulse rather than a torque) -> ``thrMomentumDumping``
    (impulse -> thruster on-times), connected to the SAME thruster
    hardware :func:`build_thrusters` already built. Matches
    ``examples/scenarioMomentumDumping.py`` exactly (module names,
    attribute names, message wiring).

    This is a SEPARATE signal path from :func:`build_thruster_force_mapping`
    -- the two are never built for the same spacecraft (one is for primary
    attitude control via thrusters, this one is for desaturating reaction
    wheels that remain in control via :func:`build_rw_motor_torque`; see
    ``schema.scenario.MomentumDumpingConfig``'s docstring for why mixing
    "reaction_wheel" and "thruster" actuators is otherwise rejected).

    IMPORTANT -- caller must also re-``Reset()`` the returned
    ``thrMomentumManagement`` module after the simulation has produced at
    least one real dynamics tick (NOT at t=0, which is all
    ``InitializeSimulation()`` itself does): confirmed by direct
    experimentation against a real Basilisk build that without this,
    ``thrMomentumManagement`` compares against a never-populated
    ``rwSpeedsInMsg`` reading and desaturation never fires for the entire
    run, with no error of any kind -- see ``engine.service.SimulationService
    .build()``'s own handling of this.
    """
    desat_control = thrMomentumManagement.thrMomentumManagement()
    desat_control.ModelTag = f"{tag}_thrMomentumManagement"
    desat_control.hs_min = config.hs_max  # [N*m*s] -- Basilisk's own field name, despite the schema's hs_max
    desat_control.rwSpeedsInMsg.subscribeTo(rw_speed_out_msg)
    desat_control.rwConfigDataInMsg.subscribeTo(rw_config_msg)
    scSim.AddModelToTask(task_name, desat_control)

    force_mapping = thrForceMapping.thrForceMapping()
    force_mapping.ModelTag = f"{tag}_desatThrForceMapping"
    force_mapping.controlAxes_B = [1, 0, 0, 0, 1, 0, 0, 0, 1]
    force_mapping.thrForceSign = 1
    # > pi: disables thrForceMapping's torque-magnitude output scaling,
    # the documented way to feed it an IMPULSE (from thrMomentumManagement)
    # rather than a torque command -- see examples/scenarioMomentumDumping.py's
    # own comment on this exact field for this exact reuse.
    force_mapping.angErrThresh = 3.15
    force_mapping.cmdTorqueInMsg.subscribeTo(desat_control.deltaHOutMsg)
    force_mapping.thrConfigInMsg.subscribeTo(thr_config_msg)
    force_mapping.vehConfigInMsg.subscribeTo(veh_config_msg)
    scSim.AddModelToTask(task_name, force_mapping)

    dumping = thrMomentumDumping.thrMomentumDumping()
    dumping.ModelTag = f"{tag}_thrMomentumDumping"
    dumping.maxCounterValue = config.max_counter_value
    dumping.thrMinFireTime = config.thr_min_fire_time
    dumping.thrusterConfInMsg.subscribeTo(thr_config_msg)
    dumping.deltaHInMsg.subscribeTo(desat_control.deltaHOutMsg)
    dumping.thrusterImpulseInMsg.subscribeTo(force_mapping.thrForceCmdOutMsg)
    scSim.AddModelToTask(task_name, dumping)

    thruster_effector.cmdsInMsg.subscribeTo(dumping.thrusterOnTimeOutMsg)
    return desat_control, force_mapping, dumping


def build_mtb_desaturation(scSim, task_name: str, tag: str, sc_object, actuator_configs: List,
                            rw_motor_torque_module, rw_config_msg, rw_state_effector, mag_field_model, config):
    """Continuous reaction-wheel momentum management via magnetic torque
    bars: a dedicated magnetometer ("TAM") + ``tamComm`` (raw sensor-frame
    -> body-frame conversion) feed Basilisk's ``mtbMomentumManagement``,
    which sits BETWEEN ``rwMotorTorque`` and the RW hardware -- it reads
    the ORIGINAL commanded RW motor torque (``rwMotorTorqueInMsg``) and
    republishes a modified one (``rwMotorTorqueOutMsg``) that also biases
    each wheel toward ``config.wheel_speed_biases_rad_s`` using whatever
    magnetic torque ``MtbEffector`` can actually produce from the current
    field -- this function re-subscribes ``rw_state_effector``'s command
    input to that modified output, OVERRIDING the direct subscription
    :func:`build_rw_motor_torque` already made (safe: Basilisk resolves
    message subscriptions at ``InitializeSimulation()``, so the last
    ``subscribeTo()`` call before that wins). Matches
    ``examples/scenarioMtbMomentumManagement.py`` exactly.

    This dedicated TAM is intentionally separate from any user-configured
    ``"magnetometer"`` SensorConfig on the same spacecraft (see
    :func:`attach_sensors`) -- one is this control loop's own near-truth
    sensor (zero noise, matching the shipped example), the other is a
    user-visible, independently-configurable (and possibly noisy)
    instrument for navigation/results. Keeping them separate means a
    user's sensor noise setting can never silently degrade (or a removed
    sensor silently break) the desaturation control loop.

    No equivalent of :func:`build_momentum_dumping`'s "prime one tick,
    then re-Reset()" dance is needed here -- confirmed by running this
    exact chain against a real Basilisk build (see this function's
    verification note in HISTORY.md): ``mtbMomentumManagement`` is a
    continuous proportional controller, not an event-triggered threshold
    -and-burst system, so it has no equivalent startup requirement.
    """
    mtb_configs = actuator_configs
    gt_hats = [[float(v) for v in a.params["gtHat_B"]] for a in mtb_configs]
    max_dipoles = [float(a.params["max_dipole_a_m2"]) for a in mtb_configs]

    mtb_config_payload = messaging.MTBArrayConfigMsgPayload()
    mtb_config_payload.numMTB = len(mtb_configs)
    # Row-major 3xN alignment matrix: all N bars' X components, then all N
    # Y components, then all N Z components -- matches
    # examples/scenarioMtbMomentumManagement.py's own GtMatrix_B layout.
    mtb_config_payload.GtMatrix_B = (
        [g[0] for g in gt_hats] + [g[1] for g in gt_hats] + [g[2] for g in gt_hats]
    )
    mtb_config_payload.maxMtbDipoles = max_dipoles
    mtb_params_msg = messaging.MTBArrayConfigMsg().write(mtb_config_payload)

    mtb_effector = MtbEffector.MtbEffector()
    mtb_effector.ModelTag = f"{tag}_mtbEffector"
    sc_object.addDynamicEffector(mtb_effector)
    scSim.AddModelToTask(task_name, mtb_effector)

    env_index = len(mag_field_model.scStateInMsgs)
    mag_field_model.addSpacecraftToModel(sc_object.scStateOutMsg)

    tam = magnetometer.Magnetometer()
    tam.ModelTag = f"{tag}_desatTAM"
    tam.senNoiseStd = [0.0, 0.0, 0.0]
    tam.stateInMsg.subscribeTo(sc_object.scStateOutMsg)
    tam.magInMsg.subscribeTo(mag_field_model.envOutMsgs[env_index])
    scSim.AddModelToTask(task_name, tam)

    tam_comm_mod = tamComm.tamComm()
    tam_comm_mod.ModelTag = f"{tag}_tamComm"
    tam_comm_mod.dcm_BS = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
    tam_comm_mod.tamInMsg.subscribeTo(tam.tamDataOutMsg)
    scSim.AddModelToTask(task_name, tam_comm_mod)

    mtb_management = mtbMomentumManagement.mtbMomentumManagement()
    mtb_management.ModelTag = f"{tag}_mtbMomentumManagement"
    mtb_management.wheelSpeedBiases = [float(v) for v in config.wheel_speed_biases_rad_s]
    mtb_management.cGain = config.c_gain
    mtb_management.rwParamsInMsg.subscribeTo(rw_config_msg)
    mtb_management.mtbParamsInMsg.subscribeTo(mtb_params_msg)
    mtb_management.tamSensorBodyInMsg.subscribeTo(tam_comm_mod.tamOutMsg)
    mtb_management.rwSpeedsInMsg.subscribeTo(rw_state_effector.rwSpeedOutMsg)
    mtb_management.rwMotorTorqueInMsg.subscribeTo(rw_motor_torque_module.rwMotorTorqueOutMsg)
    scSim.AddModelToTask(task_name, mtb_management)

    rw_state_effector.rwMotorCmdInMsg.subscribeTo(mtb_management.rwMotorTorqueOutMsg)

    mtb_effector.mtbCmdInMsg.subscribeTo(mtb_management.mtbCmdOutMsg)
    mtb_effector.mtbParamsInMsg.subscribeTo(mtb_params_msg)
    mtb_effector.magInMsg.subscribeTo(mag_field_model.envOutMsgs[env_index])

    return mtb_effector, mtb_management


def build_rw_motor_torque(scSim, task_name: str, tag: str, mrp_feedback_module, rw_config_msg, rw_state_effector):
    """Maps ``mrpFeedback``'s 3D torque command onto individual RW motor
    torques (all three body axes controlled) and connects the result to
    the RW hardware's command input. Matches
    ``examples/scenarioAttitudeFeedbackRW.py``.
    """
    mod = rwMotorTorque.rwMotorTorque()
    mod.ModelTag = f"{tag}_rwMotorTorque"
    mod.controlAxes_B = [1, 0, 0, 0, 1, 0, 0, 0, 1]
    mod.rwParamsInMsg.subscribeTo(rw_config_msg)
    mod.vehControlInMsg.subscribeTo(mrp_feedback_module.cmdTorqueOutMsg)
    scSim.AddModelToTask(task_name, mod)
    rw_state_effector.rwMotorCmdInMsg.subscribeTo(mod.rwMotorTorqueOutMsg)
    return mod


def build_ground_location(scSim, task_name: str, gs_config, central_body_radius_m: float, planet_state_out_msg,
                           sc_state_out_msgs: List):
    """One ``groundLocation.GroundLocation`` per
    :class:`schema.scenario.GroundStationConfig`. Matches
    ``examples/scenarioAttLocPoint.py``. Its ``currentGroundStateOutMsg`` is
    what ``locationPointing`` targets (:func:`build_guidance`).

    ``engine.service`` calls this BEFORE any spacecraft exist (ground
    stations don't depend on them), so ``sc_state_out_msgs`` is normally
    ``[]`` here -- access analysis (populating ``accessOutMsgs``) is added
    in a second pass once every spacecraft is built, via
    :func:`add_access_analysis`.
    """
    gl = groundLocation.GroundLocation()
    gl.ModelTag = f"groundStation_{gs_config.name}"
    gl.planetRadius = central_body_radius_m
    gl.specifyLocation(np.radians(gs_config.latitude_deg), np.radians(gs_config.longitude_deg), gs_config.altitude_m)
    gl.minimumElevation = np.radians(gs_config.min_elevation_deg)
    gl.maximumRange = -1.0  # no maximum slant range
    gl.planetInMsg.subscribeTo(planet_state_out_msg)
    for sc_state_out_msg in sc_state_out_msgs:
        gl.addSpacecraftToModel(sc_state_out_msg)
    scSim.AddModelToTask(task_name, gl)
    return gl


def add_access_analysis(ground_location, sc_objects: List) -> None:
    """Phase 3: calls ``addSpacecraftToModel`` on ``ground_location`` for
    every spacecraft in ``sc_objects``, in order -- populates
    ``ground_location.accessOutMsgs[i]`` (index == this call's position in
    ``sc_objects``, verified the same way as ``magneticFieldWMM``'s
    ``envOutMsgs`` indexing in :func:`build_magnetic_field_wmm`) for
    ``engine.service`` to record as ``hasAccess``/``slantRange``/
    ``elevation``/``azimuth`` time series. Safe to call once per ground
    station for the scenario's full spacecraft list -- each
    ``GroundLocation`` keeps its own independent ``accessOutMsgs`` index
    sequence, so calling this for several stations against the same
    ``sc_objects`` list does not cross-contaminate indices.
    """
    for sc_object in sc_objects:
        ground_location.addSpacecraftToModel(sc_object.scStateOutMsg)


def build_magnetic_field_wmm(scSim, task_name: str, planet_state_out_msg, central_body_radius_m: float):
    """One shared ``magneticFieldWMM`` environment model for the whole
    scenario's central body (Earth only -- see module docstring); every
    spacecraft with a ``magnetometer`` sensor calls
    ``addSpacecraftToModel`` on this SAME instance and reads back its own
    indexed ``envOutMsgs[i]`` entry (index == call order, verified via
    ``magneticFieldWMM``'s own unit test).
    """
    from Basilisk.utilities.supportDataTools.dataFetcher import DataFile, get_path

    mod = magneticFieldWMM.MagneticFieldWMM()
    mod.ModelTag = "magneticFieldWMM"
    mod.configureWMMFile(str(get_path(DataFile.MagneticFieldData.WMM)))
    mod.planetRadius = central_body_radius_m
    mod.planetPosInMsg.subscribeTo(planet_state_out_msg)
    scSim.AddModelToTask(task_name, mod)
    return mod


def attach_sensors(scSim, task_name: str, tag: str, sc_object, sensor_configs: List,
                    sun_state_out_msg=None, mag_field_model=None) -> Dict[str, object]:
    """Builds every :class:`schema.scenario.SensorConfig` entry for one
    spacecraft and returns ``{sensor.name: output_message}`` for
    :class:`~spacemissionstudio.engine.results.ResultSet` recording.
    ``sun_state_out_msg``/``mag_field_model`` are ``None`` unless the
    scenario actually provides them (see ``engine.service`` for the
    preconditions -- "sun" SPICE-tracked, Earth central body respectively);
    a ``coarse_sun_sensor``/``magnetometer`` entry without the matching
    precondition raises :class:`FswError` with a specific message rather
    than silently building a sensor that would output nothing.
    """
    out_msgs: Dict[str, object] = {}
    for sensor in sensor_configs:
        params = sensor.params
        if sensor.kind == "star_tracker":
            mod = starTracker.StarTracker()
            mod.ModelTag = f"{tag}_{sensor.name}"
            mod.scStateInMsg.subscribeTo(sc_object.scStateOutMsg)
            noise_rad = np.radians(float(params.get("noise_arcsec", 0.0)) / 3600.0)
            mod.PMatrix = (noise_rad * np.eye(3)).tolist()
            scSim.AddModelToTask(task_name, mod)
            out_msgs[sensor.name] = mod.sensorOutMsg

        elif sensor.kind == "imu":
            mod = imuSensor.ImuSensor()
            mod.ModelTag = f"{tag}_{sensor.name}"
            mod.scStateInMsg.subscribeTo(sc_object.scStateOutMsg)
            gyro_noise = float(params.get("gyro_noise_rad_s", 0.0))
            accel_noise = float(params.get("accel_noise_m_s2", 0.0))
            mod.PMatrixGyro = (gyro_noise * np.eye(3)).tolist()
            mod.PMatrixAccel = (accel_noise * np.eye(3)).tolist()
            scSim.AddModelToTask(task_name, mod)
            out_msgs[sensor.name] = mod.sensorOutMsg

        elif sensor.kind == "coarse_sun_sensor":
            if sun_state_out_msg is None:
                raise FswError(
                    f"{tag}: coarse_sun_sensor {sensor.name!r} needs 'sun' to be SPICE-tracked -- add 'sun' to "
                    "gravity.third_body_perturbers (or set it as gravity.central_body)"
                )
            mod = coarseSunSensor.CoarseSunSensor()
            mod.ModelTag = f"{tag}_{sensor.name}"
            mod.nHat_B = [float(v) for v in params["nHat_B"]]  # required, schema-validated
            # params["fov_deg"] is the FULL field of view (see
            # gui.sensor_actuator_editor's "full field of view [deg]" label),
            # but CoarseSunSensor.fov is the HALF angle from boresight
            # (coarseSunSensor.cpp gates on signal >= cos(fov), i.e. fov is
            # the max off-boresight angle) -- halve it here or every CSS
            # would silently accept twice the field of view the user asked for.
            mod.fov = np.radians(float(params.get("fov_deg", 90.0)) / 2.0)
            mod.senNoiseStd = float(params.get("noise_std", 0.0))
            mod.sunInMsg.subscribeTo(sun_state_out_msg)
            mod.stateInMsg.subscribeTo(sc_object.scStateOutMsg)
            scSim.AddModelToTask(task_name, mod)
            out_msgs[sensor.name] = mod.cssDataOutMsg

        elif sensor.kind == "magnetometer":
            if mag_field_model is None:
                raise FswError(
                    f"{tag}: magnetometer {sensor.name!r} needs an Earth central body in Phase 2 "
                    "(magneticFieldWMM is only wired up for gravity.central_body == 'earth')"
                )
            mod = magnetometer.Magnetometer()
            mod.ModelTag = f"{tag}_{sensor.name}"
            noise_tesla = params.get("noise_std_tesla", [0.0, 0.0, 0.0])
            mod.senNoiseStd = [float(v) for v in noise_tesla]
            mod.stateInMsg.subscribeTo(sc_object.scStateOutMsg)
            env_index = len(mag_field_model.scStateInMsgs)
            mag_field_model.addSpacecraftToModel(sc_object.scStateOutMsg)
            mod.magInMsg.subscribeTo(mag_field_model.envOutMsgs[env_index])
            scSim.AddModelToTask(task_name, mod)
            out_msgs[sensor.name] = mod.tamDataOutMsg

        else:  # unreachable if SpacecraftConfig.validate() passed
            raise FswError(f"sensor {sensor.name!r} kind {sensor.kind!r} has no engine.fsw builder")

    return out_msgs
