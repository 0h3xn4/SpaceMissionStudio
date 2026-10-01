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

"""Regression test for a codebase-audit completeness finding:
``engine.fsw.build_mtb_desaturation`` returns ``(mtb_effector,
mtb_management)``, but ``engine.service.SimulationService`` used to
discard the second value entirely (``mtb_effector, _ = fsw.
build_mtb_desaturation(...)``) -- so a spacecraft with
``schema.scenario.MagneticMomentumManagementConfig`` configured had its
commanded dipole (``mtbMomentumManagement.mtbCmdOutMsg``) invisible to
both the results UI and Vizard, unlike every other actuator-management
feature (``momentum_dumping``, ``station_keeping``, ``phasing_keeping``),
which all got a matching result series the moment they shipped.

Fixed: ``engine.service`` now records ``mtbCmdOutMsg`` and publishes it
as a new ``{name}.mtb_dipole_commanded`` result series (one column per
magnetic torque rod, matching ``{name}.rw_speeds``/``{name}.
thruster_on_time``'s existing per-actuator-column pattern -- see
``gui/results_widget.py``'s matching display spec).

This confirms the underlying message field this result series reads
(``MTBCmdMsgPayload.mtbDipoleCmds``) is real and populated with nonzero
commands by a running ``mtbMomentumManagement`` module -- the actual
``engine.service`` wiring (SPICE-blocked in this sandbox) is exercised
indirectly via ``tests/test_mtb_desaturation.py``'s own
SimulationService-bypass pattern, which this test also follows.

Requires a Basilisk build (marked ``requires_basilisk``; see
tests/conftest.py).
"""

import numpy as np
import pytest

from missionstudio.schema.scenario import ActuatorConfig, MagneticMomentumManagementConfig

pytestmark = pytest.mark.requires_basilisk

# Same 4-wheel skewed pyramid layout as tests/test_mtb_desaturation.py --
# a real, shipped configuration (examples/scenarioMtbMomentumManagement.py),
# not hand-picked to make this test pass.
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


def test_mtb_cmd_out_msg_produces_a_real_nonzero_recordable_dipole_command():
    from Basilisk.architecture import messaging
    from Basilisk.simulation import spacecraft
    from Basilisk.utilities import SimulationBaseClass, macros, orbitalMotion, simHelpers, simIncludeGravBody

    from missionstudio.engine import fsw

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

    planet_state = messaging.SpicePlanetStateMsgPayload()
    planet_state.PositionVector = [0.0, 0.0, 0.0]
    planet_state.J20002Pfix = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    planet_msg = messaging.SpicePlanetStateMsg().write(planet_state)
    mag_field_model = fsw.build_magnetic_field_wmm(scSim, task_name, planet_msg, earth.radEquator)

    config = MagneticMomentumManagementConfig(
        wheel_speed_biases_rad_s=[rpm * macros.rpm2radsec for rpm in _BIASES_RPM], c_gain=0.003,
    )
    _mtb_effector, mtb_management = fsw.build_mtb_desaturation(
        scSim, task_name, "sat", sc_object, _MTB_ACTUATORS, rw_motor_torque_mod, rw_config_msg, rw_state_effector,
        mag_field_model, config,
    )

    # Exactly what engine.service now does: record the SECOND return value
    # (mtb_management), not just the first (mtb_effector) -- this is the
    # regression the audit finding was about.
    dipole_rec = mtb_management.mtbCmdOutMsg.recorder()
    scSim.AddModelToTask(task_name, dipole_rec)

    scSim.InitializeSimulation()
    scSim.ConfigureStopTime(macros.min2nano(30.0))
    scSim.ExecuteSimulation()

    dipoles = np.asarray(dipole_rec.mtbDipoleCmds)[:, : len(_MTB_ACTUATORS)]
    assert dipoles.shape[0] > 1, "the recorder captured no ticks at all"
    assert np.any(dipoles != 0.0), (
        "mtbCmdOutMsg.mtbDipoleCmds was all-zero for the whole run -- this result series would show "
        "nothing even though the desaturation loop is actively running"
    )
    assert not np.any(np.isnan(dipoles)), "commanded dipole went non-physical (NaN)"
