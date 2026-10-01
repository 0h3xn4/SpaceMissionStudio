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

"""Regression test for a codebase-audit finding: ``engine.orbit_maintenance``'s
:class:`~missionstudio.engine.orbit_maintenance.StationKeepingController`
(and ``PhasingKeepingController``/``ConstantFrameThrustController``, which
share the identical pattern) used to compute its achieved-acceleration/
delta-V estimate as ``thrustMag / scObject.hub.mHub`` -- which undercounts
the spacecraft's TRUE total mass whenever a
``schema.scenario.FuelTankConfig`` "fuel_tank" state effector is ALSO
configured on the same spacecraft (e.g. for an unrelated thruster
actuator's own attitude-control or momentum-dumping propellant). Confirmed
directly in Basilisk's ``fuelTank.cpp``: that effector tracks its own mass
via ``effProps.mEff``, contributing correctly to the spacecraft's REAL
simulated dynamics, but never touching ``hub.mHub`` at all -- so reading
only ``hub.mHub`` here silently misses it, inflating the controller's own
acceleration/delta-V estimate and ending a burn early (an achieved-delta-V
undershoot), purely in this controller's own bookkeeping (the real
simulated dynamics were always physically correct, since Basilisk's own
integrator sums every state effector's mass correctly regardless of what
this controller reads).

The fix (see ``engine.orbit_maintenance``'s module docstring, "Shared mass
bookkeeping" section): the acceleration/delta-V estimate now reads
``scObject.scMassOutMsg.read().massSC`` -- Basilisk's own hub+state
-effector mass aggregate -- while the propellant-burn write-back
(``hub.mHub = ...``) deliberately keeps reading/writing ``hub.mHub``
specifically (using the aggregate there would double-count the fuel
tank's own mass).

This builds a real, running ``SimBaseClass`` (spacecraft + a real
``fuelTank`` state effector + ``StationKeepingController`` via
:func:`build_station_keeping`) below the station-keeping deadband (so the
controller burns immediately) and confirms the controller's own
``_cumulativeDv`` after one tick matches ``thrust / (hub_mass +
tank_mass)``, not the smaller (buggy) ``thrust / hub_mass`` alone.

Requires a Basilisk build (marked ``requires_basilisk``; see
tests/conftest.py).
"""

import numpy as np
import pytest

pytestmark = pytest.mark.requires_basilisk

_THRUST_N = 0.05
_ISP_S = 1500.0
_DRY_MASS_KG = 400.0
_SK_PROPELLANT_KG = 5.0
_TANK_PROPELLANT_KG = 20.0
_MU = 3.986004418e14
_R_PLANET_M = 6378137.0


def _run_one_tick(include_fuel_tank: bool, dt_s: float = 1.0):
    from Basilisk.simulation import extForceTorque, fuelTank, spacecraft
    from Basilisk.utilities import SimulationBaseClass, macros, simHelpers

    from missionstudio.engine.orbit_maintenance import StationKeepingConfig, build_station_keeping

    scSim = SimulationBaseClass.SimBaseClass()
    task_name = "task"
    process = scSim.CreateNewProcess("proc")
    process.addTask(scSim.CreateNewTask(task_name, macros.sec2nano(dt_s)))

    sc_object = spacecraft.Spacecraft()
    sc_object.ModelTag = "sat"
    hub_mass = _DRY_MASS_KG + _SK_PROPELLANT_KG
    sc_object.hub.mHub = hub_mass
    sc_object.hub.r_BcB_B = [0.0, 0.0, 0.0]
    inertia = [10.0, 0.0, 0.0, 0.0, 10.0, 0.0, 0.0, 0.0, 10.0]
    sc_object.hub.IHubPntBc_B = simHelpers.np2EigenMatrix3d(inertia)
    # Circular orbit well below the deadband (target 550 km) -> the
    # controller's smoothed-altitude burn logic engages immediately.
    sc_object.hub.r_CN_NInit = [[_R_PLANET_M + 500e3], [0.0], [0.0]]
    sc_object.hub.v_CN_NInit = [[0.0], [7600.0], [0.0]]
    scSim.AddModelToTask(task_name, sc_object, 10)

    if include_fuel_tank:
        tank_model = fuelTank.FuelTankModelUniformBurn()
        tank_model.propMassInit = _TANK_PROPELLANT_KG
        tank_model.maxFuelMass = _TANK_PROPELLANT_KG
        tank_model.r_TcT_TInit = [[0.0], [0.0], [0.0]]
        tank = fuelTank.FuelTank()
        tank.ModelTag = "tank"
        tank.setTankModel(tank_model)
        tank.setR_TB_B([[0.0], [0.0], [0.0]])
        # No addThrusterSet() -- this tank models an UNRELATED actuator's
        # propellant (e.g. attitude-control thrusters), present on the
        # spacecraft but with nothing to do with station-keeping's own
        # burn; it must never fire/deplete on its own, only contribute
        # its own static mass, exactly the scenario this bug missed.
        sc_object.addStateEffector(tank)
        scSim.AddModelToTask(task_name, tank, 20)

    config = StationKeepingConfig(
        target_altitude_km=550.0, deadband_km=2.0, thrust_n=_THRUST_N, isp_s=_ISP_S,
        propellant_kg=_SK_PROPELLANT_KG,
    )
    controller = build_station_keeping(
        scSim, task_name, "sat", sc_object, _MU, _R_PLANET_M, _DRY_MASS_KG, config,
    )

    scSim.InitializeSimulation()
    scSim.ConfigureStopTime(macros.sec2nano(dt_s))
    scSim.ExecuteSimulation()

    return controller, hub_mass


def test_station_keeping_cumulative_dv_uses_true_total_mass_including_fuel_tank():
    controller, hub_mass = _run_one_tick(include_fuel_tank=True, dt_s=1.0)

    assert controller.burnLog[-1] == 1, "test setup must actually trigger a burn to be meaningful"

    true_total_mass = hub_mass + _TANK_PROPELLANT_KG
    expected_dv = (_THRUST_N / true_total_mass) * 1.0
    buggy_dv_if_hub_only = (_THRUST_N / hub_mass) * 1.0

    assert controller._cumulativeDv == pytest.approx(expected_dv, rel=1e-9), (
        f"StationKeepingController's own delta-V estimate ({controller._cumulativeDv}) does not match "
        f"thrust / TRUE total mass ({expected_dv}) -- the fuel_tank's mass contribution was not picked up"
    )
    assert controller._cumulativeDv < buggy_dv_if_hub_only, (
        "delta-V estimate should be SMALLER with the fuel tank's extra mass correctly included than the "
        "old (buggy) hub.mHub-only computation would give"
    )


def test_station_keeping_cumulative_dv_unchanged_without_a_fuel_tank():
    """No fuel_tank at all (the common case, and every existing template)
    must behave exactly as before -- hub.mHub alone IS the true total
    mass in that case, so scMassOutMsg.massSC must agree with it exactly.
    """
    controller, hub_mass = _run_one_tick(include_fuel_tank=False, dt_s=1.0)

    assert controller.burnLog[-1] == 1, "test setup must actually trigger a burn to be meaningful"

    expected_dv = (_THRUST_N / hub_mass) * 1.0
    assert controller._cumulativeDv == pytest.approx(expected_dv, rel=1e-9)


def test_station_keeping_propellant_burn_write_back_does_not_double_count_fuel_tank_mass():
    """The hub.mHub write-back must stay a strict delta against hub.mHub
    itself -- NOT trueTotalMass -- or a coexisting fuel tank's mass would
    get double-counted (once in the tank's own state, once baked into
    hub.mHub).
    """
    controller, hub_mass = _run_one_tick(include_fuel_tank=True, dt_s=1.0)

    mdot = _THRUST_N / (_ISP_S * controller.g0)
    burned_kg = mdot * 1.0
    expected_hub_mass_after = hub_mass - burned_kg

    assert controller.scObject.hub.mHub == pytest.approx(expected_hub_mass_after, rel=1e-9), (
        f"hub.mHub after the burn ({controller.scObject.hub.mHub}) does not match hub_mass - burned_kg "
        f"({expected_hub_mass_after}) -- the fuel tank's mass leaked into the hub.mHub write-back"
    )
    # Sanity: the written-back mass must be far below hub_mass + tank mass
    # (which is what a double-counting bug would produce).
    assert controller.scObject.hub.mHub < hub_mass
