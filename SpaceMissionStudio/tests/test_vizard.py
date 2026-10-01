"""Regression test for the GenericStorage/GenericSensor dangling-pointer
bug in engine.vizard.enable_vizard() -- see that function's docstring,
second "Real bug found" note, for the full story: VizSpacecraftData's
genericStorageList/genericSensorList (vizStructures.h) are raw pointer
vectors (std::vector<GenericStorage *>/std::vector<GenericSensor *>),
not value vectors, so the panel objects enable_vizard() builds were
being garbage-collected the moment the function returned while
VizInterface kept dangling pointers to them -- surfacing, several ticks
later, as an unrelated-looking ``basic_string::_M_create``/
``std::length_error`` crash from VizInterface's own background write
thread. Confirmed with a real ``gdb`` ``catch throw``/``bt`` on a
minimal, fully-isolated repro (station-keeping only, headless CLI,
``--vizard-save-file``, no live Vizard connection needed).

Requires a Basilisk build (marked ``requires_basilisk``; see
tests/conftest.py for the auto-skip behavior in this development
sandbox, which does not have one).
"""

from pathlib import Path

import pytest

from spacemissionstudio.schema import load_scenario

pytestmark = pytest.mark.requires_basilisk

SCENARIO_PATH = (
    Path(__file__).resolve().parent.parent
    / "spacemissionstudio"
    / "scenarios"
    / "diagnostic_05f_station_keeping_fixed_step_integrator.json"
)


def test_station_keeping_with_vizard_save_file_does_not_crash(tmp_path):
    """The real bug: a station-keeping spacecraft (the only controller that
    creates a GenericStorage panel -- see engine.vizard's "Live-data
    panels" docstring section) run with Vizard output enabled used to
    crash within the first couple of dynamics ticks with a
    ``SimulationServiceError`` wrapping ``std::length_error``/
    ``std::bad_alloc`` from VizInterface's background write thread. This
    scenario is diagnostic_05f, a real, previously-reproducing crash --
    run() completing at all (an unhandled RuntimeError would otherwise
    propagate straight out of run()) is the actual regression check.
    """
    from spacemissionstudio.engine.service import SimulationService
    from spacemissionstudio.engine.vizard import VizardRequest

    scenario = load_scenario(SCENARIO_PATH)
    save_file = tmp_path / "diag.viz.bin"
    service = SimulationService(scenario, vizard_request=VizardRequest(save_file=str(save_file)))

    result = service.run()

    assert result is not None
    assert save_file.exists()


def test_generic_storage_and_sensor_lists_are_retained_after_build(tmp_path):
    """The actual fix: enable_vizard()'s GenericStorage/GenericSensor
    panel objects (and their embedded ReadFunctor readers) must survive
    past enable_vizard() returning, same as access_indicator_bridges --
    engine.service.SimulationService must hold the last Python reference
    to them for the simulation's lifetime, not just enable_vizard()'s own
    stack frame.
    """
    from spacemissionstudio.engine.service import SimulationService
    from spacemissionstudio.engine.vizard import VizardRequest

    scenario = load_scenario(SCENARIO_PATH)
    save_file = tmp_path / "diag.viz.bin"
    service = SimulationService(scenario, vizard_request=VizardRequest(save_file=str(save_file)))
    service.build()

    assert service._viz is not None
    assert service._viz_generic_storage_list is not None
    # follower-1 has station_keeping configured -- exactly one spacecraft's
    # entry in the per-spacecraft-parallel list should carry a real panel.
    assert any(entry for entry in service._viz_generic_storage_list)
