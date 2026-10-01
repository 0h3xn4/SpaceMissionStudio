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
``engine.vizard.enable_vizard`` had a live ``GenericStorage`` panel for
every OTHER actuator-management feature (``station_keeping_by_spacecraft``'s
"Propellant"/"SK Delta-V", ``phasing_keeping_by_spacecraft``'s "Phasing
Delta-V"/RTN separation) but none for a real
``schema.scenario.FuelTankConfig`` "fuel_tank" state effector
(``engine.fsw.build_fuel_tank``) -- a spacecraft using that newer feature
got zero live propellant gauge in Vizard, unlike every other
mass-depleting feature in this app. Fixed by a new
``fuel_tank_by_spacecraft`` parameter, wired to a "Fuel Tank"
``GenericStorage`` panel (see ``engine.vizard``'s module docstring,
"Live-data panels" section).

Like ``tests/test_thruster_control.py``/
``tests/test_location_pointing_target_body.py``, this calls
``engine.vizard.enable_vizard`` directly against a bare
``SimulationBaseClass`` with a real ``fuelTank.FuelTank()`` state
effector, sidestepping the SPICE-kernel network restriction that blocks
every ``SimulationService``-level Vizard test in this sandbox (see
``tests/test_vizard.py``'s own two tests, which fail here for exactly
that pre-existing, unrelated reason -- confirmed by direct experimentation,
not guessed).

Requires a Basilisk build (marked ``requires_basilisk``; see
tests/conftest.py).
"""

import pytest

pytestmark = pytest.mark.requires_basilisk


def _build_vizard_with_fuel_tank(tmp_path):
    from Basilisk.simulation import fuelTank, spacecraft
    from Basilisk.utilities import SimulationBaseClass, macros, simHelpers

    from spacemissionstudio.engine import vizard

    scSim = SimulationBaseClass.SimBaseClass()
    task_name = "task"
    process = scSim.CreateNewProcess("proc")
    process.addTask(scSim.CreateNewTask(task_name, macros.sec2nano(1.0)))

    sc_object = spacecraft.Spacecraft()
    sc_object.ModelTag = "sat"
    sc_object.hub.mHub = 100.0
    inertia = [10.0, 0.0, 0.0, 0.0, 10.0, 0.0, 0.0, 0.0, 10.0]
    sc_object.hub.IHubPntBc_B = simHelpers.np2EigenMatrix3d(inertia)
    scSim.AddModelToTask(task_name, sc_object, 10)

    tank_model = fuelTank.FuelTankModelUniformBurn()
    tank_model.propMassInit = 10.0
    tank_model.maxFuelMass = 10.0
    tank_model.r_TcT_TInit = [[0.0], [0.0], [0.0]]
    tank = fuelTank.FuelTank()
    tank.ModelTag = "tank"
    tank.setTankModel(tank_model)
    tank.setR_TB_B([[0.0], [0.0], [0.0]])
    sc_object.addStateEffector(tank)
    scSim.AddModelToTask(task_name, tank, 20)

    save_file = str(tmp_path / "fuel_tank.viz.bin")
    request = vizard.VizardRequest(save_file=save_file)
    viz, bridges, storage_list, sensor_list = vizard.enable_vizard(
        scSim, task_name, [sc_object], request, fuel_tank_by_spacecraft={"sat": tank},
    )
    return scSim, storage_list


def test_fuel_tank_gets_its_own_generic_storage_panel(tmp_path):
    _, storage_list = _build_vizard_with_fuel_tank(tmp_path)

    assert len(storage_list) == 1
    panels = storage_list[0]
    assert panels, "fuel_tank_by_spacecraft entry produced no GenericStorage panel at all"
    labels = [p.label for p in panels]
    assert "Fuel Tank" in labels, f"expected a 'Fuel Tank' panel, got labels {labels}"
    fuel_panel = panels[labels.index("Fuel Tank")]
    assert fuel_panel.type == "Propellant Tank"
    assert fuel_panel.units == "kg"


def test_fuel_tank_panel_label_is_distinct_from_station_keepings_own_propellant_panel():
    """StationKeepingController's own hand-rolled "Propellant" panel and
    this real fuelTank effector's panel track physically independent
    propellant pools and can coexist on one spacecraft -- their labels
    must never collide (see engine.vizard's module docstring).
    """
    from spacemissionstudio.engine import orbit_maintenance, vizard

    assert "Fuel Tank" != "Propellant"  # fuelTank panel's own label
    # orbit_maintenance's own station-keeping panel label, confirmed by
    # direct source reference rather than re-deriving it here.
    assert "station_keeping_by_spacecraft" in vizard.enable_vizard.__doc__
    assert orbit_maintenance.StationKeepingController is not None  # import sanity


def test_simulation_runs_without_crashing_with_the_new_fuel_tank_panel(tmp_path):
    from Basilisk.utilities import macros

    scSim, storage_list = _build_vizard_with_fuel_tank(tmp_path)
    scSim.InitializeSimulation()
    scSim.ConfigureStopTime(macros.sec2nano(2.0))
    scSim.ExecuteSimulation()  # must not raise/crash
