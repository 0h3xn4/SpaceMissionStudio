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

"""Tests for engine.fsw.build_momentum_dumping -- reaction-wheel momentum
desaturation via thrusters (thrMomentumManagement -> thrForceMapping
[momentum-dump mode] -> thrMomentumDumping), and for the "prime one
dynamics tick, then re-Reset() the desat module" dance
engine.service.SimulationService.build() performs automatically (see that
method's own comment).

Like tests/test_thruster_control.py, this calls engine.fsw's builder
functions directly against a bare SimulationBaseClass -- no gravity, no
SPICE -- rather than going through SimulationService (which this sandbox
cannot exercise end-to-end; see tests/test_gravity_gradient.py's
docstring). The exact priming/Reset() sequence here duplicates
SimulationService.build()'s own, so this is also a real regression test
for that logic.

Requires a Basilisk build (marked ``requires_basilisk``; see
tests/conftest.py).
"""

import numpy as np
import pytest

from missionstudio.schema.scenario import ActuatorConfig, MomentumDumpingConfig

pytestmark = pytest.mark.requires_basilisk

# Same pre-saturated 4-wheel cluster and 8-thruster ACS layout as
# examples/scenarioMomentumDumping.py -- a real, shipped configuration,
# not hand-picked to make this test pass.
_RW_ACTUATORS = [
    ActuatorConfig(kind="reaction_wheel", name="rw1",
                    params={"gsHat_B": [0.7071, 0, 0.7071], "rw_type": "Honeywell_HR16",
                            "maxMomentum": 100.0, "Omega": 4000.0}),
    ActuatorConfig(kind="reaction_wheel", name="rw2",
                    params={"gsHat_B": [0, 0.7071, 0.7071], "rw_type": "Honeywell_HR16",
                            "maxMomentum": 100.0, "Omega": 2000.0}),
    ActuatorConfig(kind="reaction_wheel", name="rw3",
                    params={"gsHat_B": [-0.7071, 0, 0.7071], "rw_type": "Honeywell_HR16",
                            "maxMomentum": 100.0, "Omega": 3500.0}),
    ActuatorConfig(kind="reaction_wheel", name="rw4",
                    params={"gsHat_B": [0, -0.7071, 0.7071], "rw_type": "Honeywell_HR16",
                            "maxMomentum": 100.0, "Omega": 0.0}),
]
_THRUSTER_LOCATIONS = [[-1, -1, 1.28], [1, -1, -1.28], [1, -1, 1.28], [1, 1, -1.28],
                       [1, 1, 1.28], [-1, 1, -1.28], [-1, 1, 1.28], [-1, -1, -1.28]]
_THRUSTER_DIRECTIONS = [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0],
                        [-1, 0, 0], [1, 0, 0], [0, -1, 0], [0, 1, 0]]
_THRUSTER_ACTUATORS = [
    ActuatorConfig(kind="thruster", name=f"t{i}",
                    params={"r_B": loc, "tHat_B": direction, "MaxThrust": 5.0, "thruster_type": "MOOG_Monarc_5"})
    for i, (loc, direction) in enumerate(zip(_THRUSTER_LOCATIONS, _THRUSTER_DIRECTIONS))
]
_DYNAMICS_TASK_RATE_S = 1.0


def _run_momentum_dumping(duration_s: float, prime_before_reset: bool, momentum_config: MomentumDumpingConfig):
    from Basilisk.simulation import spacecraft
    from Basilisk.utilities import SimulationBaseClass, macros, simHelpers

    from missionstudio.engine import fsw

    scSim = SimulationBaseClass.SimBaseClass()
    task_name = "task"
    process = scSim.CreateNewProcess("proc")
    process.addTask(scSim.CreateNewTask(task_name, macros.sec2nano(_DYNAMICS_TASK_RATE_S)))

    sc_object = spacecraft.Spacecraft()
    sc_object.ModelTag = "sat"
    inertia = [1700.0, 0.0, 0.0, 0.0, 1700.0, 0.0, 0.0, 0.0, 1800.0]
    sc_object.hub.mHub = 2500.0
    sc_object.hub.IHubPntBc_B = simHelpers.np2EigenMatrix3d(inertia)
    sc_object.hub.sigma_BNInit = [[0.0], [0.0], [0.0]]
    sc_object.hub.omega_BN_BInit = [[0.0], [0.0], [0.0]]
    scSim.AddModelToTask(task_name, sc_object, 10)

    nav = fsw.build_simple_nav(scSim, task_name, "sat", sc_object)
    veh_config_msg = fsw.build_vehicle_config_msg(inertia)
    guid_msg = fsw.build_guidance(
        scSim, task_name, "sat", "inertial3D", {"sigma_R0N": [0.0, 0.0, 0.0]}, nav, None, {}
    )

    _, rw_state_effector, rw_config_msg = fsw.build_reaction_wheels(scSim, task_name, "sat", sc_object, _RW_ACTUATORS)
    mrp = fsw.build_mrp_feedback(scSim, task_name, "sat", guid_msg, veh_config_msg, {},
                                  rw_config_msg=rw_config_msg, rw_speed_out_msg=rw_state_effector.rwSpeedOutMsg)
    fsw.build_rw_motor_torque(scSim, task_name, "sat", mrp, rw_config_msg, rw_state_effector)

    _, thruster_effector, thr_config_msg = fsw.build_thrusters(
        scSim, task_name, "sat_desat", sc_object, _THRUSTER_ACTUATORS
    )
    desat_control, _, dumping = fsw.build_momentum_dumping(
        scSim, task_name, "sat", rw_config_msg, rw_state_effector.rwSpeedOutMsg, thr_config_msg, veh_config_msg,
        thruster_effector, momentum_config,
    )

    rw_speed_rec = rw_state_effector.rwSpeedOutMsg.recorder()
    scSim.AddModelToTask(task_name, rw_speed_rec)
    on_time_rec = dumping.thrusterOnTimeOutMsg.recorder()
    scSim.AddModelToTask(task_name, on_time_rec)

    scSim.InitializeSimulation()
    if prime_before_reset:
        # Duplicates engine.service.SimulationService.build()'s own
        # priming dance -- see that method's comment.
        priming_time_ns = macros.sec2nano(min(_DYNAMICS_TASK_RATE_S, duration_s))
        scSim.ConfigureStopTime(priming_time_ns)
        scSim.ExecuteSimulation()
        desat_control.Reset(priming_time_ns)
    scSim.ConfigureStopTime(macros.sec2nano(duration_s))
    scSim.ExecuteSimulation()

    speeds = np.array(rw_speed_rec.wheelSpeeds)[:, : len(_RW_ACTUATORS)]
    on_times = np.array(on_time_rec.OnTimeRequest)[:, : len(_THRUSTER_ACTUATORS)]
    return speeds, on_times


def test_momentum_dumping_reduces_wheel_speed_when_primed():
    speeds, on_times = _run_momentum_dumping(
        duration_s=300.0, prime_before_reset=True, momentum_config=MomentumDumpingConfig(hs_max=80.0)
    )
    initial_norm = np.linalg.norm(speeds[0])
    final_norm = np.linalg.norm(speeds[-1])
    assert final_norm < initial_norm, (
        f"reaction wheel speed magnitude did not shrink after desaturation: {initial_norm} -> {final_norm}"
    )
    assert np.any(on_times > 0.0), "desaturation thrusters never commanded a nonzero on-time"


def test_momentum_dumping_never_fires_without_the_priming_reset():
    """Regression guard for the real bug this feature's own design is
    built around: thrMomentumManagement compares against a never
    -populated rwSpeedsInMsg if its Reset() is only ever called at t=0
    (which InitializeSimulation() already does for every module) --
    confirmed by running this exact scenario both ways against a real
    Basilisk build. engine.service.SimulationService.build() always primes
    before the real run specifically to avoid this; this test pins the
    "without priming" side of that comparison so a future refactor can't
    silently drop the priming step and have it go unnoticed (no exception
    is raised either way -- it just quietly never desaturates).
    """
    speeds, on_times = _run_momentum_dumping(
        duration_s=300.0, prime_before_reset=False, momentum_config=MomentumDumpingConfig(hs_max=80.0)
    )
    assert np.allclose(speeds[0], speeds[-1], atol=1e-6), (
        "wheel speed changed even without the priming Reset() -- if thrMomentumManagement's behavior here "
        "changed, SimulationService.build()'s priming step may no longer be necessary (or may need updating)"
    )
    assert not np.any(on_times > 0.0)
