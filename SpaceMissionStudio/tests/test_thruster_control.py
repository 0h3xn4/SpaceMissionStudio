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

"""Tests for engine.fsw's "thruster" actuator control path
(build_thrusters/build_thruster_force_mapping): mrpFeedback ->
thrForceMapping -> thrFiringSchmitt -> thrusterDynamicEffector, the
real-hardware alternative to the idealized extForceTorque/reaction-wheel
paths.

Unlike most of this app's dynamics (see tests/test_gravity_gradient.py's
docstring), this test does NOT go through engine.service.SimulationService
-- it calls engine.fsw's builder functions directly against a bare
SimulationBaseClass.SimBaseClass() with a free-floating spacecraft (no
gravity effector, no SPICE). Attitude-only dynamics need neither, so this
sidesteps the SPICE-kernel network restriction that blocks every
SimulationService-level test in this sandbox (see engine/kernels.py's
docstring) entirely -- confirmed by actually running it here against the
real Basilisk build, not just written against a verified call sequence
like the SPICE-blocked tests are.

Requires a Basilisk build (marked ``requires_basilisk``; see
tests/conftest.py).
"""

import numpy as np
import pytest

from spacemissionstudio.schema.scenario import ActuatorConfig

pytestmark = pytest.mark.requires_basilisk

# An 8-thruster cluster giving full bidirectional 3-axis torque authority,
# the same corner-mounted "cube satellite ACS" layout (though renumbered
# axes) as examples/scenarioMomentumDumping.py's own thruster set -- not
# hand-picked to make this test pass, a standard real configuration.
_THRUSTER_ACTUATORS = [
    ActuatorConfig(kind="thruster", name="t1", params={"r_B": [1, 1, 0], "tHat_B": [0, 0, 1], "MaxThrust": 1.0}),
    ActuatorConfig(kind="thruster", name="t2", params={"r_B": [1, -1, 0], "tHat_B": [0, 0, -1], "MaxThrust": 1.0}),
    ActuatorConfig(kind="thruster", name="t3", params={"r_B": [-1, 1, 0], "tHat_B": [0, 0, -1], "MaxThrust": 1.0}),
    ActuatorConfig(kind="thruster", name="t4", params={"r_B": [-1, -1, 0], "tHat_B": [0, 0, 1], "MaxThrust": 1.0}),
    ActuatorConfig(kind="thruster", name="t5", params={"r_B": [1, 0, 1], "tHat_B": [0, 1, 0], "MaxThrust": 1.0}),
    ActuatorConfig(kind="thruster", name="t6", params={"r_B": [-1, 0, 1], "tHat_B": [0, -1, 0], "MaxThrust": 1.0}),
    ActuatorConfig(kind="thruster", name="t7", params={"r_B": [0, 1, 1], "tHat_B": [1, 0, 0], "MaxThrust": 1.0}),
    ActuatorConfig(kind="thruster", name="t8", params={"r_B": [0, -1, 1], "tHat_B": [-1, 0, 0], "MaxThrust": 1.0}),
]


def _run_thruster_attitude_control(duration_s: float):
    from Basilisk.simulation import spacecraft
    from Basilisk.utilities import SimulationBaseClass, macros, simHelpers

    from spacemissionstudio.engine import fsw

    scSim = SimulationBaseClass.SimBaseClass()
    task_name = "task"
    process = scSim.CreateNewProcess("proc")
    process.addTask(scSim.CreateNewTask(task_name, macros.sec2nano(0.5)))

    sc_object = spacecraft.Spacecraft()
    sc_object.ModelTag = "sat"
    inertia = [10.0, 0.0, 0.0, 0.0, 10.0, 0.0, 0.0, 0.0, 10.0]
    sc_object.hub.mHub = 100.0
    sc_object.hub.IHubPntBc_B = simHelpers.np2EigenMatrix3d(inertia)
    sc_object.hub.sigma_BNInit = [[0.3], [0.2], [-0.1]]
    sc_object.hub.omega_BN_BInit = [[0.0], [0.0], [0.0]]
    scSim.AddModelToTask(task_name, sc_object, 10)

    nav = fsw.build_simple_nav(scSim, task_name, "sat", sc_object)
    veh_config_msg = fsw.build_vehicle_config_msg(inertia)
    guid_msg = fsw.build_guidance(
        scSim, task_name, "sat", "inertial3D", {"sigma_R0N": [0.0, 0.0, 0.0]}, nav, None, {}
    )
    mrp = fsw.build_mrp_feedback(scSim, task_name, "sat", guid_msg, veh_config_msg, {})

    _, thruster_effector, thr_config_msg = fsw.build_thrusters(
        scSim, task_name, "sat", sc_object, _THRUSTER_ACTUATORS
    )
    _, firing_logic = fsw.build_thruster_force_mapping(
        scSim, task_name, "sat", mrp, thr_config_msg, veh_config_msg, thruster_effector
    )

    sc_rec = sc_object.scStateOutMsg.recorder()
    scSim.AddModelToTask(task_name, sc_rec)
    on_time_rec = firing_logic.onTimeOutMsg.recorder()
    scSim.AddModelToTask(task_name, on_time_rec)

    scSim.InitializeSimulation()
    scSim.ConfigureStopTime(macros.sec2nano(duration_s))
    scSim.ExecuteSimulation()

    sigma = np.array(sc_rec.sigma_BN)
    on_times = np.array(on_time_rec.OnTimeRequest)[:, : len(_THRUSTER_ACTUATORS)]
    return sigma, on_times


def test_thruster_chain_commands_nonzero_on_times():
    _, on_times = _run_thruster_attitude_control(duration_s=60.0)
    assert np.any(on_times > 0.0), (
        "an 8-thruster cluster controlling a spacecraft with nonzero initial attitude error commanded "
        "zero on-time for every thruster over the whole run -- the mrpFeedback -> thrForceMapping -> "
        "thrFiringSchmitt -> thrusterDynamicEffector chain produced no actuation at all"
    )


def test_thruster_chain_reduces_attitude_error():
    sigma, _ = _run_thruster_attitude_control(duration_s=60.0)
    initial_error = np.linalg.norm(sigma[0])
    final_error = np.linalg.norm(sigma[-1])
    assert final_error < initial_error, (
        f"thruster-actuated attitude control did not reduce attitude error toward the inertial3D target "
        f"(sigma_R0N=[0,0,0]) over 60s: |sigma| went from {initial_error} to {final_error}"
    )
