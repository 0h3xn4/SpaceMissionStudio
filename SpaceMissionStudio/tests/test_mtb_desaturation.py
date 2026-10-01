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

"""Tests for engine.fsw.build_mtb_desaturation -- continuous reaction
-wheel momentum management via magnetic torque bars
(mtbMomentumManagement), the alternative desaturation strategy to
tests/test_momentum_dumping.py's thruster-based one.

Like those tests, this calls engine.fsw's builder functions directly
against a bare SimulationBaseClass rather than going through
SimulationService (SPICE-blocked in this sandbox; see
tests/test_gravity_gradient.py's docstring) -- but magneticFieldWMM needs
a real (non-degenerate) planet orientation matrix to produce a sane
field, which only a real SPICE-sourced planet state message normally
provides. Rather than skip real execution entirely, this builds a
minimal stand-in SpicePlanetStateMsgPayload with an IDENTITY
orientation matrix (correct for this test's Earth-centered-inertial-only
setup, where there is no real SPICE ephemeris rotating the Earth-fixed
frame away from inertial at all) -- found necessary by direct
experimentation: an all-zero (Python-default) orientation matrix made
wheel speeds converge nowhere near their commanded bias (errors of
150-370 RPM out of 200-800 RPM targets); the identity-orientation
version converges to within 0.5 RPM, matching
examples/scenarioMtbMomentumManagement.py's own documented behavior.
engine.service.SimulationService always supplies a real, non-degenerate
SPICE-sourced planet message in production, so this gap is specific to
this bypass-SPICE test harness, not a bug in engine.fsw.

Requires a Basilisk build (marked ``requires_basilisk``; see
tests/conftest.py).
"""

import numpy as np
import pytest

from spacemissionstudio.schema.scenario import ActuatorConfig, MagneticMomentumManagementConfig

pytestmark = pytest.mark.requires_basilisk

# Same 4-wheel skewed pyramid layout and 10 kg / 0.02-0.1256 kg*m^2 small
# -sat inertia as examples/scenarioMtbMomentumManagement.py -- a real,
# shipped configuration, not hand-picked to make this test pass.
_BETA_RAD = 52.0 * np.pi / 180.0
_GS = np.array([
    [0.0, 0.0, np.cos(_BETA_RAD), -np.cos(_BETA_RAD)],
    [np.cos(_BETA_RAD), np.sin(_BETA_RAD), -np.sin(_BETA_RAD), -np.sin(_BETA_RAD)],
    [np.sin(_BETA_RAD), -np.cos(_BETA_RAD), 0.0, 0.0],
])
_RW_ACTUATORS = [
    ActuatorConfig(kind="reaction_wheel", name=f"rw{i + 1}",
                    params={"gsHat_B": list(_GS[:, i]), "rw_type": "BCT_RWP015", "Omega_max": 5000.0,
                            "useRWfriction": False})
    for i in range(4)
]
_MTB_ACTUATORS = [
    ActuatorConfig(kind="magnetic_torque_rod", name="mtb-1",
                    params={"gtHat_B": [1.0, 0.0, 0.0], "max_dipole_a_m2": 0.1}),
    ActuatorConfig(kind="magnetic_torque_rod", name="mtb-2",
                    params={"gtHat_B": [0.0, 1.0, 0.0], "max_dipole_a_m2": 0.1}),
    ActuatorConfig(kind="magnetic_torque_rod", name="mtb-3",
                    params={"gtHat_B": [0.0, 0.0, 1.0], "max_dipole_a_m2": 0.1}),
    ActuatorConfig(kind="magnetic_torque_rod", name="mtb-4",
                    params={"gtHat_B": [0.70710678, 0.70710678, 0.0], "max_dipole_a_m2": 0.1}),
]
_BIASES_RPM = [800.0, 600.0, 400.0, 200.0]


def _run_mtb_momentum_management(duration_min: float):
    from Basilisk.architecture import messaging
    from Basilisk.simulation import spacecraft
    from Basilisk.utilities import SimulationBaseClass, macros, orbitalMotion, simHelpers, simIncludeGravBody

    from spacemissionstudio.engine import fsw

    scSim = SimulationBaseClass.SimBaseClass()
    task_name = "task"
    process = scSim.CreateNewProcess("proc")
    process.addTask(scSim.CreateNewTask(task_name, macros.sec2nano(2.0)))

    sc_object = spacecraft.Spacecraft()
    sc_object.ModelTag = "sat"
    inertia = [0.02 / 3, 0.0, 0.0, 0.0, 0.1256 / 3, 0.0, 0.0, 0.0, 0.1256 / 3]
    sc_object.hub.mHub = 10.0
    sc_object.hub.IHubPntBc_B = simHelpers.np2EigenMatrix3d(inertia)
    sc_object.hub.sigma_BNInit = [[0.1], [0.2], [-0.3]]
    sc_object.hub.omega_BN_BInit = [[0.001], [-0.01], [0.03]]
    scSim.AddModelToTask(task_name, sc_object, 1)

    grav_factory = simIncludeGravBody.gravBodyFactory()
    earth = grav_factory.createEarth()
    earth.isCentralBody = True
    grav_factory.addBodiesTo(sc_object)

    oe = orbitalMotion.ClassicElements()
    oe.a = 6778.14 * 1000.0
    oe.e = 0.0
    oe.i = 45.0 * macros.D2R
    oe.Omega = 60.0 * macros.D2R
    oe.omega = 0.0
    oe.f = 0.0
    r_n, v_n = orbitalMotion.elem2rv(earth.mu, oe)
    sc_object.hub.r_CN_NInit = r_n
    sc_object.hub.v_CN_NInit = v_n

    nav = fsw.build_simple_nav(scSim, task_name, "sat", sc_object)
    veh_config_msg = fsw.build_vehicle_config_msg(inertia)
    guid_msg = fsw.build_guidance(
        scSim, task_name, "sat", "inertial3D", {"sigma_R0N": [0.0, 0.0, 0.0]}, nav, None, {}
    )

    _, rw_state_effector, rw_config_msg = fsw.build_reaction_wheels(
        scSim, task_name, "sat", sc_object, _RW_ACTUATORS
    )
    mrp = fsw.build_mrp_feedback(scSim, task_name, "sat", guid_msg, veh_config_msg, {"K": 0.0001, "P": 0.002},
                                  rw_config_msg=rw_config_msg, rw_speed_out_msg=rw_state_effector.rwSpeedOutMsg)
    rw_motor_torque_mod = fsw.build_rw_motor_torque(scSim, task_name, "sat", mrp, rw_config_msg, rw_state_effector)

    # Earth motionless at the inertial origin (no SPICE in this bypass
    # setup) -- IDENTITY orientation is the correct stand-in here, not a
    # simplification; see module docstring for what an all-zero one does.
    planet_state = messaging.SpicePlanetStateMsgPayload()
    planet_state.PositionVector = [0.0, 0.0, 0.0]
    planet_state.J20002Pfix = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    planet_msg = messaging.SpicePlanetStateMsg().write(planet_state)
    mag_field_model = fsw.build_magnetic_field_wmm(scSim, task_name, planet_msg, earth.radEquator)

    config = MagneticMomentumManagementConfig(
        wheel_speed_biases_rad_s=[rpm * macros.rpm2radsec for rpm in _BIASES_RPM], c_gain=0.003,
    )
    fsw.build_mtb_desaturation(
        scSim, task_name, "sat", sc_object, _MTB_ACTUATORS, rw_motor_torque_mod, rw_config_msg, rw_state_effector,
        mag_field_model, config,
    )

    rw_speed_rec = rw_state_effector.rwSpeedOutMsg.recorder()
    scSim.AddModelToTask(task_name, rw_speed_rec)

    scSim.InitializeSimulation()
    scSim.ConfigureStopTime(macros.min2nano(duration_min))
    scSim.ExecuteSimulation()

    return np.array(rw_speed_rec.wheelSpeeds)[:, : len(_RW_ACTUATORS)] / macros.RPM


def test_mtb_momentum_management_drives_wheel_speeds_to_the_commanded_biases():
    speeds_rpm = _run_mtb_momentum_management(duration_min=120.0)
    final_error_rpm = speeds_rpm[-1] - np.array(_BIASES_RPM)
    assert np.all(np.abs(final_error_rpm) < 2.0), (
        f"wheel speeds did not converge to their commanded biases {_BIASES_RPM} RPM within 2 RPM: "
        f"final speeds {speeds_rpm[-1]} RPM, error {final_error_rpm} RPM"
    )


def test_mtb_momentum_management_actually_moves_wheel_speeds_from_zero():
    speeds_rpm = _run_mtb_momentum_management(duration_min=120.0)
    assert np.linalg.norm(speeds_rpm[0]) < 1e-9, "test setup expects wheels starting at rest"
    assert np.linalg.norm(speeds_rpm[-1]) > 100.0, (
        "wheel speeds barely changed from their zero initial condition -- the MTB desaturation chain "
        "likely produced no real commanded dipole/torque"
    )
