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

"""Tests for engine.service's gravity gradient torque wiring
(schema.scenario.SpacecraftConfig.enable_gravity_gradient ->
Basilisk.simulation.GravityGradientEffector).

Requires a Basilisk build (marked ``requires_basilisk``; see
tests/conftest.py).

These deliberately use a spacecraft with fsw_mode = None (no attitude
control loop) rather than the usual scenario-level ResultSet: with a
controller active, mrpFeedback would simply reject gravity-gradient
torque as one more disturbance, masking it entirely from any output
series -- the only way to see the raw effector's real physical effect is
an uncontrolled spacecraft's own attitude drifting away from its initial
value, read directly off scStateOutMsg's recorder (SimulationService's
public ResultSet does not report attitude at all when fsw_mode is None --
see engine.service.SimulationService.run()'s docstring -- so this reaches
into build(initialize=False) + spacecraft_handles to attach one, the same
public seam engine.service itself documents for exactly this purpose).
"""

from pathlib import Path

import numpy as np
import pytest

from spacemissionstudio.schema import load_scenario

pytestmark = pytest.mark.requires_basilisk

SCENARIO_PATH = Path(__file__).resolve().parent.parent / "spacemissionstudio" / "scenarios" / "two_body_validation.json"


def _run_and_get_sigma_history(enable_gravity_gradient: bool) -> np.ndarray:
    from Basilisk.utilities import macros

    from spacemissionstudio.engine.service import SimulationService

    scenario = load_scenario(SCENARIO_PATH)
    sc = scenario.spacecraft[0]
    # Spherically symmetric inertia (the scenario file's default, and this
    # schema's own SpacecraftConfig default) makes the real gravity
    # -gradient torque cross(rHat, I . rHat) identically zero for ANY
    # inertia tensor of the form k*Identity -- an elongated principal
    # -inertia spread is required for this effector to produce a nonzero
    # torque at all, not a test-construction choice.
    sc.inertia_kg_m2 = [5.0, 0.0, 0.0, 0.0, 10.0, 0.0, 0.0, 0.0, 20.0]
    sc.enable_gravity_gradient = enable_gravity_gradient
    assert sc.fsw_mode is None, "test assumes the bundled scenario has no attitude control loop"

    service = SimulationService(scenario)
    service.build(initialize=False)
    handle = service.spacecraft_handles[sc.name]
    recorder = handle.sc_object.scStateOutMsg.recorder()
    service.scSim.AddModelToTask(service.dyn_task_name, recorder)
    service.scSim.InitializeSimulation()
    stop_time_s = scenario.sim_settings.duration_days * 86400.0
    service.scSim.ConfigureStopTime(macros.sec2nano(stop_time_s))
    service.scSim.ExecuteSimulation()

    return np.array(recorder.sigma_BN)


def test_gravity_gradient_torque_perturbs_an_otherwise_frozen_attitude():
    sigma_with_gg = _run_and_get_sigma_history(enable_gravity_gradient=True)
    # With zero initial body rate and no torque of any kind, attitude is
    # exactly frozen for the whole run -- the real physical contrast this
    # effector must produce.
    assert not np.allclose(sigma_with_gg[0], sigma_with_gg[-1]), (
        "enabling gravity gradient torque on an elongated, uncontrolled spacecraft must perturb its "
        "attitude away from the frozen initial value -- got no change at all"
    )


def test_disabled_gravity_gradient_leaves_attitude_exactly_frozen():
    sigma_without_gg = _run_and_get_sigma_history(enable_gravity_gradient=False)
    assert np.allclose(sigma_without_gg[0], sigma_without_gg[-1]), (
        "with enable_gravity_gradient=False and no other torque source, attitude must stay exactly at "
        "its initial value -- regression guard for this effector leaking in when not requested"
    )
