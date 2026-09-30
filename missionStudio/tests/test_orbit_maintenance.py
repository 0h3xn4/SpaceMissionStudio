"""Tests for missionstudio.engine.orbit_maintenance's VNB/RTN frame math
(_vnb_basis/_rtn_basis), used by ConstantFrameThrustController
(schema.scenario.ConstantThrustConfig). The whole module needs a Basilisk
build to import (its SysModel controller classes do), even though this
specific math is pure numpy -- see tests/conftest.py for the auto-skip
behavior in this development sandbox, which does not have one.
"""

import numpy as np
import pytest

pytestmark = pytest.mark.requires_basilisk


def test_eclipse_illumination_fraction_prefers_new_name():
    from missionstudio.engine.orbit_maintenance import _eclipse_illumination_fraction

    class _NewStylePayload:
        illuminationFactor = 0.75
        shadowFactor = -1.0  # would be wrong if this were read instead

    assert _eclipse_illumination_fraction(_NewStylePayload()) == 0.75


def test_eclipse_illumination_fraction_falls_back_to_old_name():
    """Real gap found on a real user's installed Basilisk build:
    illuminationFactor does not exist there at all (an AttributeError,
    not a deprecation warning) -- only the older shadowFactor name is
    present. This project does not pin an exact Basilisk version, so
    both must work.
    """
    from missionstudio.engine.orbit_maintenance import _eclipse_illumination_fraction

    class _OldStylePayload:
        shadowFactor = 0.42
        # No illuminationFactor attribute at all -- matches the real
        # installed build that triggered this fix.

    assert _eclipse_illumination_fraction(_OldStylePayload()) == 0.42


def test_vnb_basis_circular_equatorial_prograde_orbit():
    """Hand-computed reference case: r along +x, v along +y (circular,
    equatorial, prograde). Orbit normal is +z; V=[0,1,0]=v-hat by
    definition; N=[0,0,1]; B=V x N=[1,0,0], which for a circular orbit
    coincides with the radial direction.
    """
    from missionstudio.engine.orbit_maintenance import _vnb_basis

    r = np.array([7000000.0, 0.0, 0.0])
    v = np.array([0.0, 7500.0, 0.0])
    v_hat, n_hat, b_hat = _vnb_basis(r, v)
    assert np.allclose(v_hat, [0.0, 1.0, 0.0])
    assert np.allclose(n_hat, [0.0, 0.0, 1.0])
    assert np.allclose(b_hat, [1.0, 0.0, 0.0])


def test_rtn_basis_circular_equatorial_prograde_orbit():
    """Same reference case as above: R=r-hat=[1,0,0]; N=[0,0,1] (same
    orbit normal as VNB's); T=N x R=[0,1,0], which for a CIRCULAR orbit
    coincides with the velocity direction (not true in general for an
    eccentric orbit -- see _rtn_basis's docstring).
    """
    from missionstudio.engine.orbit_maintenance import _rtn_basis

    r = np.array([7000000.0, 0.0, 0.0])
    v = np.array([0.0, 7500.0, 0.0])
    r_hat, t_hat, n_hat = _rtn_basis(r, v)
    assert np.allclose(r_hat, [1.0, 0.0, 0.0])
    assert np.allclose(t_hat, [0.0, 1.0, 0.0])
    assert np.allclose(n_hat, [0.0, 0.0, 1.0])


@pytest.mark.parametrize("seed", range(5))
def test_vnb_and_rtn_bases_are_orthonormal_and_right_handed(seed):
    """General (non-hand-picked) check across several random orbit states:
    both bases must be orthonormal AND right-handed (axis1 x axis2 ==
    axis3), regardless of orbit shape/orientation.
    """
    from missionstudio.engine.orbit_maintenance import _rtn_basis, _vnb_basis

    rng = np.random.default_rng(seed)
    r = rng.uniform(-1.0e7, 1.0e7, size=3)
    v = rng.uniform(-8000.0, 8000.0, size=3)
    # Ensure r, v are not (near-)parallel -- orbit normal would be undefined.
    if np.linalg.norm(np.cross(r, v)) < 1.0:
        v = v + np.array([1000.0, 0.0, 0.0])

    for basis_fn in (_vnb_basis, _rtn_basis):
        a1, a2, a3 = basis_fn(r, v)
        for axis in (a1, a2, a3):
            assert np.isclose(np.linalg.norm(axis), 1.0)
        assert np.isclose(np.dot(a1, a2), 0.0, atol=1e-9)
        assert np.isclose(np.dot(a2, a3), 0.0, atol=1e-9)
        assert np.isclose(np.dot(a1, a3), 0.0, atol=1e-9)
        assert np.allclose(np.cross(a1, a2), a3, atol=1e-9)


# -- Non-finite/degenerate spacecraft state must never reach
# orbitalMotion.rv2elem() from inside UpdateState() -----------------------
#
# Real crash report: a formation-flying scenario (station_keeping +
# phasing_keeping) crashed with two DIFFERENT native signatures on
# different runs ("basic_string::_M_create", "std::bad_alloc") -- the
# classic symptom of memory corruption, not a deterministic failure.
# Traced to PhasingKeepingController.UpdateState()'s own call to
# orbitalMotion.rv2elem() (via _mean_anomaly): that function has a real
# bug in its OWN NaN-input guard (src/utilities/orbitalMotion.py sets
# ClassicElements.AN/.AP, neither a real slot on that class -- see
# engine.service._osculating_elements's matching comment/fix), so it
# crashes with AttributeError instead of returning a clean NaN result --
# and an exception escaping a SWIG director callback (UpdateState()
# itself) is undefined behavior, not a clean Python exception. These
# tests confirm UpdateState() never reaches that call with non-finite
# input in the first place.

def _write_sc_state(msg, r_bn_n, v_bn_n, time_ns=0):
    from Basilisk.architecture import messaging

    payload = messaging.SCStatesMsgPayload()
    payload.r_BN_N = list(r_bn_n)
    payload.v_BN_N = list(v_bn_n)
    msg.write(payload, time_ns, -1)


def _flat(vec3) -> list:
    """extForce_N read back from a real ExtForceTorque as a nested
    [[x], [y], [z]] column-vector shape (confirmed against a real
    Basilisk build -- not the flat [x, y, z] list it's assigned as, via
    forceVec.tolist()), rather than guess at exactly which SWIG
    Eigen-vector property shapes do this and which don't.
    """
    return list(np.asarray(vec3).flatten())


def test_station_keeping_skips_thrust_on_nan_state():
    from Basilisk.architecture import messaging
    from Basilisk.simulation import extForceTorque

    from missionstudio.engine.orbit_maintenance import StationKeepingController

    controller = StationKeepingController(
        name="sk", mu=3.986004418e14, nominal_alt_m=550e3, deadband_m=2e3, r_planet_m=6378137.0,
        thrust_n=0.05, isp_s=1500.0, dry_mass_kg=400.0, propellant_kg=5.0,
    )
    controller.extForceEffector = extForceTorque.ExtForceTorque()
    sc_state_msg = messaging.SCStatesMsg()
    _write_sc_state(sc_state_msg, [np.nan, 0.0, 0.0], [0.0, 7500.0, 0.0])
    controller.scStateInMsg.subscribeTo(sc_state_msg)
    controller.Reset(0)

    controller.UpdateState(0)  # must not raise

    assert _flat(controller.extForceEffector.extForce_N) == [0.0, 0.0, 0.0]
    assert controller.burnLog[-1] == 0
    assert np.isnan(controller.altLog[-1])


def test_station_keeping_skips_thrust_on_zero_velocity():
    """A separate degenerate case from NaN -- np.linalg.norm(vVec) below
    would otherwise divide by zero when computing the thrust direction.
    """
    from Basilisk.architecture import messaging
    from Basilisk.simulation import extForceTorque

    from missionstudio.engine.orbit_maintenance import StationKeepingController

    controller = StationKeepingController(
        name="sk", mu=3.986004418e14, nominal_alt_m=550e3, deadband_m=2e3, r_planet_m=6378137.0,
        thrust_n=0.05, isp_s=1500.0, dry_mass_kg=400.0, propellant_kg=5.0,
    )
    controller.extForceEffector = extForceTorque.ExtForceTorque()
    sc_state_msg = messaging.SCStatesMsg()
    _write_sc_state(sc_state_msg, [7000e3, 0.0, 0.0], [0.0, 0.0, 0.0])
    controller.scStateInMsg.subscribeTo(sc_state_msg)
    controller.Reset(0)

    controller.UpdateState(0)  # must not raise

    assert _flat(controller.extForceEffector.extForce_N) == [0.0, 0.0, 0.0]


def test_phasing_keeping_skips_thrust_on_nan_state():
    from Basilisk.architecture import messaging
    from Basilisk.simulation import extForceTorque

    from missionstudio.engine.orbit_maintenance import PhasingKeepingController, SeparationSchedule

    controller = PhasingKeepingController(
        name="pk", mu=3.986004418e14, nominal_a_m=6928e3,
        separation_schedule=SeparationSchedule(distances_km=[50.0], interval_days=0.0, semi_major_axis_m=6928e3),
        tolerance_fraction=0.1, restore_tolerance_fraction=0.5, correction_window_days=1.0,
        max_drift_days=5.0, max_delta_a_m=1000.0, thrust_n=0.05, isp_s=1500.0, dry_mass_kg=400.0,
    )
    controller.extForceEffectorB = extForceTorque.ExtForceTorque()
    state_a = messaging.SCStatesMsg()
    state_b = messaging.SCStatesMsg()
    _write_sc_state(state_a, [7000e3, 0.0, 0.0], [0.0, 7500.0, 0.0])
    _write_sc_state(state_b, [np.nan, np.nan, np.nan], [np.nan, np.nan, np.nan])
    controller.scStateInMsgA.subscribeTo(state_a)
    controller.scStateInMsgB.subscribeTo(state_b)
    controller.Reset(0)

    controller.UpdateState(0)  # must not raise -- would crash inside orbitalMotion.rv2elem() otherwise

    assert _flat(controller.extForceEffectorB.extForce_N) == [0.0, 0.0, 0.0]
    assert np.isnan(controller.errorDegLog[-1])


def test_phasing_keeping_skips_thrust_on_zero_velocity():
    """Real gap found by audit: unlike StationKeepingController's own
    matching zero-velocity guard, this class only checked for NaN/inf,
    not for vA/vB being exactly zero -- `vHatB = vB / np.linalg.norm(vB)`
    further down would divide by zero, and orbitalMotion.rv2elem() (via
    _mean_anomaly, called before that) also divides by velocity-derived
    quantities internally.
    """
    from Basilisk.architecture import messaging
    from Basilisk.simulation import extForceTorque

    from missionstudio.engine.orbit_maintenance import PhasingKeepingController, SeparationSchedule

    controller = PhasingKeepingController(
        name="pk", mu=3.986004418e14, nominal_a_m=6928e3,
        separation_schedule=SeparationSchedule(distances_km=[50.0], interval_days=0.0, semi_major_axis_m=6928e3),
        tolerance_fraction=0.1, restore_tolerance_fraction=0.5, correction_window_days=1.0,
        max_drift_days=5.0, max_delta_a_m=1000.0, thrust_n=0.05, isp_s=1500.0, dry_mass_kg=400.0,
    )
    controller.extForceEffectorB = extForceTorque.ExtForceTorque()
    state_a = messaging.SCStatesMsg()
    state_b = messaging.SCStatesMsg()
    _write_sc_state(state_a, [7000e3, 0.0, 0.0], [0.0, 7500.0, 0.0])
    _write_sc_state(state_b, [0.0, 7000e3, 0.0], [0.0, 0.0, 0.0])  # zero velocity
    controller.scStateInMsgA.subscribeTo(state_a)
    controller.scStateInMsgB.subscribeTo(state_b)
    controller.Reset(0)

    controller.UpdateState(0)  # must not raise

    assert _flat(controller.extForceEffectorB.extForce_N) == [0.0, 0.0, 0.0]
    assert np.isnan(controller.errorDegLog[-1])


def test_constant_thrust_skips_on_nan_state():
    """ConstantFrameThrustController had NO guard at all before this audit
    -- _vnb_basis()/_rtn_basis() (called from UpdateState()) would
    silently propagate NaN into the commanded force.
    """
    from Basilisk.architecture import messaging
    from Basilisk.simulation import extForceTorque

    from missionstudio.engine.orbit_maintenance import ConstantFrameThrustController

    controller = ConstantFrameThrustController(
        name="ct", frame="VNB", direction=[1.0, 0.0, 0.0], thrust_n=0.05, isp_s=1500.0,
        dry_mass_kg=400.0, propellant_kg=5.0,
    )
    controller.extForceEffector = extForceTorque.ExtForceTorque()
    sc_state_msg = messaging.SCStatesMsg()
    _write_sc_state(sc_state_msg, [np.nan, 0.0, 0.0], [0.0, 7500.0, 0.0])
    controller.scStateInMsg.subscribeTo(sc_state_msg)
    controller.Reset(0)

    controller.UpdateState(0)  # must not raise

    assert _flat(controller.extForceEffector.extForce_N) == [0.0, 0.0, 0.0]


def test_constant_thrust_skips_on_zero_velocity():
    from Basilisk.architecture import messaging
    from Basilisk.simulation import extForceTorque

    from missionstudio.engine.orbit_maintenance import ConstantFrameThrustController

    controller = ConstantFrameThrustController(
        name="ct", frame="VNB", direction=[1.0, 0.0, 0.0], thrust_n=0.05, isp_s=1500.0,
        dry_mass_kg=400.0, propellant_kg=5.0,
    )
    controller.extForceEffector = extForceTorque.ExtForceTorque()
    sc_state_msg = messaging.SCStatesMsg()
    _write_sc_state(sc_state_msg, [7000e3, 0.0, 0.0], [0.0, 0.0, 0.0])
    controller.scStateInMsg.subscribeTo(sc_state_msg)
    controller.Reset(0)

    controller.UpdateState(0)  # must not raise

    assert _flat(controller.extForceEffector.extForce_N) == [0.0, 0.0, 0.0]


def test_constant_thrust_skips_on_parallel_r_and_v():
    """A purely radial trajectory (r, v collinear) -- individually
    nonzero, but their cross product (the orbit normal _vnb_basis()/
    _rtn_basis() both divide by) is zero. Not caught by a finite check
    or a zero-velocity check alone.
    """
    from Basilisk.architecture import messaging
    from Basilisk.simulation import extForceTorque

    from missionstudio.engine.orbit_maintenance import ConstantFrameThrustController

    controller = ConstantFrameThrustController(
        name="ct", frame="RTN", direction=[1.0, 0.0, 0.0], thrust_n=0.05, isp_s=1500.0,
        dry_mass_kg=400.0, propellant_kg=5.0,
    )
    controller.extForceEffector = extForceTorque.ExtForceTorque()
    sc_state_msg = messaging.SCStatesMsg()
    _write_sc_state(sc_state_msg, [7000e3, 0.0, 0.0], [100.0, 0.0, 0.0])  # v parallel to r
    controller.scStateInMsg.subscribeTo(sc_state_msg)
    controller.Reset(0)

    controller.UpdateState(0)  # must not raise

    assert _flat(controller.extForceEffector.extForce_N) == [0.0, 0.0, 0.0]


def test_constant_thrust_runs_normally_with_finite_state():
    """Confirms the new guard doesn't change behavior for the ordinary,
    finite/non-degenerate case.
    """
    from Basilisk.architecture import messaging
    from Basilisk.simulation import extForceTorque

    from missionstudio.engine.orbit_maintenance import ConstantFrameThrustController

    controller = ConstantFrameThrustController(
        name="ct", frame="VNB", direction=[1.0, 0.0, 0.0], thrust_n=0.05, isp_s=1500.0,
        dry_mass_kg=400.0, propellant_kg=5.0,
    )
    controller.extForceEffector = extForceTorque.ExtForceTorque()
    sc_state_msg = messaging.SCStatesMsg()
    _write_sc_state(sc_state_msg, [7000e3, 0.0, 0.0], [0.0, 7500.0, 0.0])
    controller.scStateInMsg.subscribeTo(sc_state_msg)
    controller.Reset(0)

    controller.UpdateState(0)

    assert _flat(controller.extForceEffector.extForce_N) != [0.0, 0.0, 0.0]
    assert len(controller.tLog) == 1


def test_phasing_keeping_runs_normally_with_finite_state():
    """Confirms the new guard doesn't change behavior for the ordinary,
    finite-state case -- the state machine still runs its normal IDLE
    logic (with a huge starting error, immediately transitions to
    BURN_OUT).
    """
    from Basilisk.architecture import messaging
    from Basilisk.simulation import extForceTorque

    from missionstudio.engine.orbit_maintenance import PhasingKeepingController, SeparationSchedule

    controller = PhasingKeepingController(
        name="pk", mu=3.986004418e14, nominal_a_m=6928e3,
        separation_schedule=SeparationSchedule(distances_km=[50.0], interval_days=0.0, semi_major_axis_m=6928e3),
        tolerance_fraction=0.1, restore_tolerance_fraction=0.5, correction_window_days=1.0,
        max_drift_days=5.0, max_delta_a_m=1000.0, thrust_n=0.05, isp_s=1500.0, dry_mass_kg=400.0,
    )
    controller.extForceEffectorB = extForceTorque.ExtForceTorque()
    state_a = messaging.SCStatesMsg()
    state_b = messaging.SCStatesMsg()
    _write_sc_state(state_a, [7000e3, 0.0, 0.0], [0.0, 7500.0, 0.0])
    _write_sc_state(state_b, [0.0, 7000e3, 0.0], [-7500.0, 0.0, 0.0])
    controller.scStateInMsgA.subscribeTo(state_a)
    controller.scStateInMsgB.subscribeTo(state_b)
    controller.Reset(0)

    controller.UpdateState(0)

    # The exact control-law numerics aren't what this test is about (see
    # the *_skips_thrust_on_nan_state tests above for that) -- only that
    # the new guard doesn't block the ordinary, finite-state path from
    # running its real logic and logging a real (non-placeholder) value.
    assert not np.isnan(controller.errorDegLog[-1])
    assert len(controller.tLog) == 1


# -- Live delta-V-used/separation telemetry (engine.vizard's GenericStorage
# panels) -------------------------------------------------------------------

def test_station_keeping_dv_budget_is_tsiolkovsky_closed_form():
    from missionstudio.engine.orbit_maintenance import StationKeepingController
    from missionstudio.engine.propellant_bookkeeping import total_delta_v_budget

    controller = StationKeepingController(
        name="sk", mu=3.986004418e14, nominal_alt_m=550e3, deadband_m=2e3, r_planet_m=6378137.0,
        thrust_n=0.05, isp_s=1500.0, dry_mass_kg=400.0, propellant_kg=5.0,
    )
    assert controller.dvBudgetMps == total_delta_v_budget(400.0, 5.0, 1500.0)
    assert controller.dvBudgetMps > 0.0


def test_station_keeping_publishes_delta_v_message_after_update():
    from Basilisk.architecture import messaging
    from Basilisk.simulation import extForceTorque

    from missionstudio.engine.orbit_maintenance import StationKeepingController

    controller = StationKeepingController(
        name="sk", mu=3.986004418e14, nominal_alt_m=550e3, deadband_m=2e3, r_planet_m=6378137.0,
        thrust_n=0.05, isp_s=1500.0, dry_mass_kg=400.0, propellant_kg=5.0,
    )
    controller.extForceEffector = extForceTorque.ExtForceTorque()
    sc_state_msg = messaging.SCStatesMsg()
    # Below the deadband -> burnOn immediately -> nonzero delta-V this tick.
    _write_sc_state(sc_state_msg, [6378137.0 + 540e3, 0.0, 0.0], [0.0, 7500.0, 0.0])
    controller.scStateInMsg.subscribeTo(sc_state_msg)
    controller.Reset(0)

    controller.UpdateState(int(1e9))  # dt = 1 s

    payload = controller.deltaVOutMsg.read()
    assert payload.storageLevel == controller._cumulativeDv
    assert payload.storageLevel > 0.0
    assert payload.storageCapacity == controller.dvBudgetMps


def test_phasing_keeping_dv_budget_is_passed_through_from_constructor():
    from missionstudio.engine.orbit_maintenance import PhasingKeepingController, SeparationSchedule

    controller = PhasingKeepingController(
        name="pk", mu=3.986004418e14, nominal_a_m=6928e3,
        separation_schedule=SeparationSchedule(distances_km=[50.0], interval_days=0.0, semi_major_axis_m=6928e3),
        tolerance_fraction=0.1, restore_tolerance_fraction=0.5, correction_window_days=1.0,
        max_drift_days=5.0, max_delta_a_m=1000.0, thrust_n=0.05, isp_s=1500.0, dry_mass_kg=400.0,
        dv_budget_mps=717.7,
    )
    assert controller.dvBudgetMps == 717.7


def test_phasing_keeping_publishes_rtn_separation_and_delta_v_messages():
    """Regression test for a real gap found while writing this feature:
    deltaVOutMsg must report a correct storageCapacity (the shared-tank
    budget) even on a tick where the thruster-arbitration branch returns
    before the state machine's own final block runs -- see UpdateState's
    two deltaVOutMsg.write() call sites and their comments for why.

    Also the main regression test for the RTN separation telemetry (real
    user feedback: a single "Separation" scalar was too vague) and for
    the screenshot-confirmed bugs it must still not reintroduce -- this
    scenario's chief/follower are 90 deg apart in true anomaly, which
    (see the R, T computed below) makes BOTH the radial and transverse
    raw offsets far exceed the shared capacity, in OPPOSITE signs, so a
    single tick here exercises the magnitude clamp on both an
    over-capacity NEGATIVE (radial) and an over-capacity POSITIVE
    (transverse) raw value at once -- storageLevel must come out
    non-negative and clamped either way (see _clamp_magnitude's own
    docstring for why: an earlier revision clamped signed, which a real
    Vizard screenshot showed rendering "Unavailable" for a negative
    storageLevel instead of a bar).
    """
    from Basilisk.architecture import messaging
    from Basilisk.simulation import extForceTorque
    from Basilisk.utilities import orbitalMotion

    from missionstudio.engine.orbit_maintenance import PhasingKeepingController, SeparationSchedule

    nominal_a_m = 6928e3
    controller = PhasingKeepingController(
        name="pk", mu=3.986004418e14, nominal_a_m=nominal_a_m,
        separation_schedule=SeparationSchedule(distances_km=[50.0], interval_days=0.0,
                                                semi_major_axis_m=nominal_a_m),
        tolerance_fraction=0.1, restore_tolerance_fraction=0.5, correction_window_days=1.0,
        max_drift_days=5.0, max_delta_a_m=1000.0, thrust_n=0.05, isp_s=1500.0, dry_mass_kg=400.0,
        dv_budget_mps=717.7,
    )
    controller.extForceEffectorB = extForceTorque.ExtForceTorque()
    state_a = messaging.SCStatesMsg()
    state_b = messaging.SCStatesMsg()
    # Same orbit shape (a, e, i, Omega, omega), true anomaly 90 deg apart.
    oe = orbitalMotion.ClassicElements()
    oe.a, oe.e, oe.i, oe.Omega, oe.omega = nominal_a_m, 0.001, 0.0, 0.0, 0.0
    oe.f = 0.0
    r_a, v_a = orbitalMotion.elem2rv(controller.mu, oe)
    oe.f = np.radians(90.0)
    r_b, v_b = orbitalMotion.elem2rv(controller.mu, oe)
    _write_sc_state(state_a, r_a, v_a)
    _write_sc_state(state_b, r_b, v_b)
    controller.scStateInMsgA.subscribeTo(state_a)
    controller.scStateInMsgB.subscribeTo(state_b)
    controller.Reset(0)

    controller.UpdateState(0)

    rho_h, _rho_prime_h = orbitalMotion.rv2hill(r_a, v_a, r_b, v_b)
    expected_radial_km, expected_transverse_km, expected_normal_km = np.array(rho_h) / 1000.0
    # Sanity on the scenario itself: R and T must both be far outside the
    # shared +/-100 km capacity (2x the 50 km target), in opposite signs --
    # otherwise this test isn't exercising the clamp both ways as intended.
    assert expected_radial_km < -100.0
    assert expected_transverse_km > 100.0

    radial_payload = controller.separationRadialOutMsg.read()
    transverse_payload = controller.separationTransverseOutMsg.read()
    normal_payload = controller.separationNormalOutMsg.read()

    for payload in (radial_payload, transverse_payload, normal_payload):
        assert payload.storageCapacity == pytest.approx(100.0)  # 2x the 50 km target, shared by all three
        assert payload.storageLevel >= 0.0  # MAGNITUDE only -- never negative, whatever the raw sign
    assert radial_payload.storageLevel == pytest.approx(100.0)  # clamped magnitude of the raw ~-6921 km
    assert transverse_payload.storageLevel == pytest.approx(100.0)  # clamped magnitude of the raw ~6928 km
    assert normal_payload.storageLevel == pytest.approx(0.0)  # co-planar case: genuinely ~0, not clamped

    # The true, unclamped numbers must still be the real geometry.
    assert controller.lastRadialKm == pytest.approx(expected_radial_km)
    assert controller.lastTransverseKm == pytest.approx(expected_transverse_km)
    assert controller.lastNormalKm == pytest.approx(expected_normal_km, abs=1e-9)
    assert controller.lastTargetSeparationKm == pytest.approx(50.0)

    # The gauge's max must be correct even before any phasing burn has
    # actually accumulated delta-V (this scenario's first tick is still
    # in IDLE -- see test_phasing_keeping_runs_normally_with_finite_state
    # above, which confirms IDLE -> BURN_OUT transitions on the NEXT tick).
    delta_v_payload = controller.deltaVOutMsg.read()
    assert delta_v_payload.storageCapacity == 717.7


def test_phasing_keeping_rtn_separation_is_unclamped_when_within_capacity():
    """Companion to the clamping regression test above: when the raw
    separation is comfortably within the shared 2x-target capacity,
    storageLevel must pass through as its (non-negative) MAGNITUDE
    unchanged, not always get pinned to the capacity -- confirms the
    clamp is a min(abs(...), limit), not an accidental hard-set. Also
    confirms the transverse (along-track) component reads close to the
    along-track target for a follower placed there, and radial/normal
    read close to zero for this co-planar, near-circular scenario.
    """
    from Basilisk.architecture import messaging
    from Basilisk.simulation import extForceTorque
    from Basilisk.utilities import orbitalMotion

    from missionstudio.engine.orbit_maintenance import PhasingKeepingController, SeparationSchedule

    nominal_a_m = 6928e3
    target_km = 50.0
    controller = PhasingKeepingController(
        name="pk", mu=3.986004418e14, nominal_a_m=nominal_a_m,
        separation_schedule=SeparationSchedule(distances_km=[target_km], interval_days=0.0,
                                                semi_major_axis_m=nominal_a_m),
        tolerance_fraction=0.1, restore_tolerance_fraction=0.5, correction_window_days=1.0,
        max_drift_days=5.0, max_delta_a_m=1000.0, thrust_n=0.05, isp_s=1500.0, dry_mass_kg=400.0,
    )
    controller.extForceEffectorB = extForceTorque.ExtForceTorque()
    state_a = messaging.SCStatesMsg()
    state_b = messaging.SCStatesMsg()
    target_rad = target_km * 1000.0 / nominal_a_m  # matches SeparationSchedule's own arc-length formula
    oe = orbitalMotion.ClassicElements()
    oe.a, oe.e, oe.i, oe.Omega, oe.omega = nominal_a_m, 0.001, 0.0, 0.0, 0.0
    oe.f = 0.0
    r_a, v_a = orbitalMotion.elem2rv(controller.mu, oe)
    oe.f = target_rad  # follower exactly on-target, ahead of the chief
    r_b, v_b = orbitalMotion.elem2rv(controller.mu, oe)
    _write_sc_state(state_a, r_a, v_a)
    _write_sc_state(state_b, r_b, v_b)
    controller.scStateInMsgA.subscribeTo(state_a)
    controller.scStateInMsgB.subscribeTo(state_b)
    controller.Reset(0)

    controller.UpdateState(0)

    radial_payload = controller.separationRadialOutMsg.read()
    transverse_payload = controller.separationTransverseOutMsg.read()
    normal_payload = controller.separationNormalOutMsg.read()
    for payload in (radial_payload, transverse_payload, normal_payload):
        assert payload.storageCapacity == pytest.approx(2.0 * target_km)

    # abs=0.5 (1% of target): a nonzero eccentricity (0.001 here) makes
    # the Hill-frame T offset slightly different from a pure arc-length
    # approximation -- real physics, not slack for a bug, and still small
    # enough to clearly distinguish "passed through near-unchanged" from
    # "clamped to 100.0".
    assert transverse_payload.storageLevel == pytest.approx(target_km, abs=0.5)
    assert transverse_payload.storageLevel < transverse_payload.storageCapacity
    assert radial_payload.storageLevel < 1.0  # near-circular, co-planar: small, not clamped
    assert normal_payload.storageLevel == pytest.approx(0.0, abs=1e-9)  # exactly co-planar here

    # storageLevel is the MAGNITUDE of the true, signed geometry (see
    # _clamp_magnitude's own docstring for why: GenericStorage cannot
    # render a negative currentValue) -- lastRadialKm itself may be
    # slightly negative here (near-circular, co-planar noise), unlike
    # lastTransverseKm, which is comfortably positive ("ahead of the
    # chief") in this scenario, so only the radial comparison needs abs().
    assert controller.lastTransverseKm == pytest.approx(transverse_payload.storageLevel, abs=1e-9)
    assert abs(controller.lastRadialKm) == pytest.approx(radial_payload.storageLevel, abs=1e-9)
    assert controller.lastNormalKm == pytest.approx(normal_payload.storageLevel, abs=1e-9)
