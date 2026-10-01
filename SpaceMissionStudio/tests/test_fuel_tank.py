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

"""Tests for engine.fsw.build_fuel_tank -- real propellant depletion for
"thruster" actuators via Basilisk's own fuelTank state effector
(FuelTankModelUniformBurn), tied to a ThrusterDynamicEffector via
fuelTank.addThrusterSet() (confirmed against
examples/MultiSatBskSim/modelsMultiSat/BSK_MultiSatDynamics.py's own
SetFuelTank()).

Like the rest of this project's requires_basilisk tests, this calls
engine.fsw's builder functions directly against a bare SimulationBaseClass
rather than going through SimulationService (SPICE-blocked in this
sandbox).

Requires a Basilisk build (marked ``requires_basilisk``; see
tests/conftest.py).
"""

import numpy as np
import pytest

from spacemissionstudio.schema.scenario import ActuatorConfig, FuelTankConfig

pytestmark = pytest.mark.requires_basilisk

_G0 = 9.80665  # [m/s^2] standard gravity, matches EARTH_GRAV in thrusterDynamicEffector.cpp


def _run_fuel_tank(duration_s: float, max_thrust_n: float, steady_isp_s: float,
                    propellant_mass_kg: float, max_propellant_mass_kg: float):
    from Basilisk.architecture import messaging
    from Basilisk.simulation import spacecraft
    from Basilisk.utilities import SimulationBaseClass, macros, simHelpers

    from spacemissionstudio.engine import fsw

    scSim = SimulationBaseClass.SimBaseClass()
    task_name = "task"
    process = scSim.CreateNewProcess("proc")
    process.addTask(scSim.CreateNewTask(task_name, macros.sec2nano(1.0)))

    sc_object = spacecraft.Spacecraft()
    sc_object.ModelTag = "sat"
    inertia = [10.0, 0.0, 0.0, 0.0, 10.0, 0.0, 0.0, 0.0, 10.0]
    sc_object.hub.mHub = 100.0
    sc_object.hub.IHubPntBc_B = simHelpers.np2EigenMatrix3d(inertia)
    sc_object.hub.r_CN_NInit = [[7000.0e3], [0.0], [0.0]]
    sc_object.hub.v_CN_NInit = [[0.0], [7.5e3], [0.0]]
    scSim.AddModelToTask(task_name, sc_object, 10)

    thruster_actuators = [
        ActuatorConfig(kind="thruster", name="thr-1", params={
            "r_B": [1.0, 0.0, 0.0], "tHat_B": [1.0, 0.0, 0.0], "MaxThrust": max_thrust_n,
            "steadyIsp": steady_isp_s,
        }),
    ]
    _, thruster_effector, _ = fsw.build_thrusters(scSim, task_name, "sat", sc_object, thruster_actuators)

    fuel_tank_config = FuelTankConfig(propellant_mass_kg=propellant_mass_kg,
                                        max_propellant_mass_kg=max_propellant_mass_kg)
    tank = fsw.build_fuel_tank(scSim, task_name, "sat", sc_object, thruster_effector, fuel_tank_config)

    on_time = messaging.THRArrayOnTimeCmdMsgPayload()
    on_time.OnTimeRequest = [1.0e9]  # fire continuously for the whole run
    on_time_msg = messaging.THRArrayOnTimeCmdMsg().write(on_time)
    thruster_effector.cmdsInMsg.subscribeTo(on_time_msg)

    tank_rec = tank.fuelTankOutMsg.recorder()
    scSim.AddModelToTask(task_name, tank_rec)
    sc_rec = sc_object.scStateOutMsg.recorder()
    scSim.AddModelToTask(task_name, sc_rec)

    scSim.InitializeSimulation()
    scSim.ConfigureStopTime(macros.sec2nano(duration_s))
    scSim.ExecuteSimulation()

    return np.array(tank_rec.fuelMass)


def test_firing_thruster_depletes_fuel_at_the_expected_rocket_equation_rate():
    max_thrust_n = 5.0
    steady_isp_s = 220.0
    duration_s = 200.0
    fuel_mass = _run_fuel_tank(duration_s=duration_s, max_thrust_n=max_thrust_n, steady_isp_s=steady_isp_s,
                                 propellant_mass_kg=10.0, max_propellant_mass_kg=20.0)

    expected_mdot_kg_s = max_thrust_n / (steady_isp_s * _G0)
    actual_depletion_kg = fuel_mass[0] - fuel_mass[-1]
    # The task's own first tick (t=0) always reads the thruster as not yet
    # firing (one task-rate-worth, 1.0s here, of startup delay before mDot
    # ramps up) -- confirmed directly: a short run's depletion consistently
    # matches expected_mdot * (duration_s - 1.0) exactly, not
    # expected_mdot * duration_s. Using a long duration here makes that
    # fixed 1-tick offset negligible instead of needing to special-case it.
    expected_depletion_kg = expected_mdot_kg_s * duration_s

    assert fuel_mass[-1] < fuel_mass[0], "firing the thruster did not deplete any fuel at all"
    assert actual_depletion_kg == pytest.approx(expected_depletion_kg, rel=0.01), (
        f"fuel depletion rate does not match the expected mDot = MaxThrust / (steadyIsp * g0): "
        f"actual {actual_depletion_kg:.6f} kg vs expected {expected_depletion_kg:.6f} kg over {duration_s}s"
    )


def test_no_firing_command_leaves_fuel_mass_unchanged():
    from Basilisk.simulation import spacecraft
    from Basilisk.utilities import SimulationBaseClass, macros, simHelpers

    from spacemissionstudio.engine import fsw

    scSim = SimulationBaseClass.SimBaseClass()
    task_name = "task"
    process = scSim.CreateNewProcess("proc")
    process.addTask(scSim.CreateNewTask(task_name, macros.sec2nano(1.0)))

    sc_object = spacecraft.Spacecraft()
    sc_object.ModelTag = "sat"
    inertia = [10.0, 0.0, 0.0, 0.0, 10.0, 0.0, 0.0, 0.0, 10.0]
    sc_object.hub.mHub = 100.0
    sc_object.hub.IHubPntBc_B = simHelpers.np2EigenMatrix3d(inertia)
    sc_object.hub.r_CN_NInit = [[7000.0e3], [0.0], [0.0]]
    sc_object.hub.v_CN_NInit = [[0.0], [7.5e3], [0.0]]
    scSim.AddModelToTask(task_name, sc_object, 10)

    thruster_actuators = [
        ActuatorConfig(kind="thruster", name="thr-1",
                        params={"r_B": [1.0, 0.0, 0.0], "tHat_B": [1.0, 0.0, 0.0], "MaxThrust": 5.0}),
    ]
    _, thruster_effector, _ = fsw.build_thrusters(scSim, task_name, "sat", sc_object, thruster_actuators)
    fuel_tank_config = FuelTankConfig(propellant_mass_kg=10.0, max_propellant_mass_kg=20.0)
    tank = fsw.build_fuel_tank(scSim, task_name, "sat", sc_object, thruster_effector, fuel_tank_config)
    # No cmdsInMsg subscription at all -- the thruster never fires.

    tank_rec = tank.fuelTankOutMsg.recorder()
    scSim.AddModelToTask(task_name, tank_rec)

    scSim.InitializeSimulation()
    scSim.ConfigureStopTime(macros.sec2nano(10.0))
    scSim.ExecuteSimulation()

    fuel_mass = np.array(tank_rec.fuelMass)
    assert fuel_mass[0] == pytest.approx(10.0)
    assert fuel_mass[-1] == pytest.approx(10.0), "fuel mass changed despite the thruster never firing"
