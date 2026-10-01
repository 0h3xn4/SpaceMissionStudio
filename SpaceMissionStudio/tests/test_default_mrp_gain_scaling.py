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

"""Regression test for a codebase-audit finding: ``engine.fsw.
DEFAULT_MRP_GAINS`` (K=3.5, P=30.0) is lifted from Basilisk's own
``examples/BskSim`` reference, tuned for a 900 kg*m^2 spacecraft at a
0.1s FSW rate (see HISTORY.md's "attitude determination pipeline" entry
and ``tests/test_location_pointing_target_body.py``'s docstring for the
full investigation). That fix was previously applied BY HAND to specific
templates (07, 14's explicit scaled ``control_params``; 06, 15's finer
``dynamics_task_rate_s``) but never built into ``engine.fsw`` itself --
so a brand-new spacecraft left on EVERY schema default (``inertia_kg_m2``
= 10 kg*m^2 diag, ``control_params={}``, ``dynamics_task_rate_s`` =
10.0s) hit the exact same documented NaN divergence, with no code-level
protection at all.

``engine.fsw.build_mrp_feedback`` now defaults K/P to
``_default_mrp_gains_for_inertia(inertia_kg_m2)`` (the reference gains
scaled by the spacecraft's own mean inertia relative to the 900 kg*m^2
reference) whenever ``inertia_kg_m2`` is given and ``control_params``
doesn't explicitly override K/P -- this test confirms, against a real
Basilisk build, that this closes the gap: the UNSCALED reference gains
reliably diverge to NaN at schema-default inertia, while the SAME
``engine.fsw``/``engine.service`` code path with the inertia now passed
through produces a clean, convergent response, even at the schema's own
coarse ``dynamics_task_rate_s`` default.

Like ``tests/test_location_pointing_target_body.py``, this calls
``engine.fsw``'s builder functions directly against a bare
``SimulationBaseClass`` (SPICE-free, no ``SimulationService`` needed for
a pure idealized-actuation attitude-control loop).

Requires a Basilisk build (marked ``requires_basilisk``; see
tests/conftest.py).
"""

import numpy as np
import pytest

pytestmark = pytest.mark.requires_basilisk

# Matches schema.scenario.SpacecraftConfig.inertia_kg_m2's own default.
_SCHEMA_DEFAULT_INERTIA = [10.0, 0.0, 0.0, 0.0, 10.0, 0.0, 0.0, 0.0, 10.0]
# Matches schema.scenario.SimSettingsConfig.dynamics_task_rate_s's own default.
_SCHEMA_DEFAULT_RATE_S = 10.0


def _run_inertial3d_idealized(control_params, inertia, rate_s, duration_s):
    from Basilisk.simulation import spacecraft
    from Basilisk.utilities import SimulationBaseClass, macros, simHelpers

    from spacemissionstudio.engine import fsw

    scSim = SimulationBaseClass.SimBaseClass()
    task_name = "task"
    process = scSim.CreateNewProcess("proc")
    process.addTask(scSim.CreateNewTask(task_name, macros.sec2nano(rate_s)))

    sc_object = spacecraft.Spacecraft()
    sc_object.ModelTag = "sat"
    sc_object.hub.mHub = 50.0
    sc_object.hub.IHubPntBc_B = simHelpers.np2EigenMatrix3d(inertia)
    sc_object.hub.sigma_BNInit = [[0.3], [0.2], [0.1]]
    sc_object.hub.omega_BN_BInit = [[0.001], [-0.001], [0.0005]]
    scSim.AddModelToTask(task_name, sc_object, 10)

    nav = fsw.build_simple_nav(scSim, task_name, "sat", sc_object)
    veh_config_msg = fsw.build_vehicle_config_msg(inertia)
    guid_msg = fsw.build_guidance(scSim, task_name, "sat", "inertial3D", {}, nav, None, {})
    mrp = fsw.build_mrp_feedback(
        scSim, task_name, "sat", guid_msg, veh_config_msg, control_params, inertia_kg_m2=inertia,
    )
    fsw.build_idealized_actuation(scSim, task_name, "sat", sc_object, mrp)

    sc_rec = sc_object.scStateOutMsg.recorder()
    scSim.AddModelToTask(task_name, sc_rec)

    scSim.InitializeSimulation()
    scSim.ConfigureStopTime(macros.sec2nano(duration_s))
    scSim.ExecuteSimulation()

    return np.array(sc_rec.sigma_BN)


def test_unscaled_reference_gains_reproduce_the_documented_nan_divergence():
    """Sanity check that this test setup actually reproduces the known bug
    (same reference gains, same undersized inertia) -- if this ever stops
    diverging, the scaling fix below would no longer be verifying anything
    real."""
    sigma = _run_inertial3d_idealized(
        control_params={"K": 3.5, "P": 30.0}, inertia=_SCHEMA_DEFAULT_INERTIA,
        rate_s=1.0, duration_s=120.0,
    )
    assert np.any(np.isnan(sigma)), "test setup no longer reproduces the documented NaN divergence"


def test_default_control_params_now_converge_at_schema_default_inertia_and_rate():
    sigma = _run_inertial3d_idealized(
        control_params={}, inertia=_SCHEMA_DEFAULT_INERTIA,
        rate_s=_SCHEMA_DEFAULT_RATE_S, duration_s=1200.0,
    )
    assert not np.any(np.isnan(sigma)), (
        "a spacecraft left on every schema default (inertia, control_params, dynamics_task_rate_s) "
        "went non-physical (NaN) -- the inertia-scaled default MRP gains did not fix the regression"
    )
    final_angle_deg = 4.0 * np.degrees(np.arctan(np.linalg.norm(sigma[-1])))
    assert final_angle_deg < 1.0, f"default control_params did not converge: final error {final_angle_deg:.4f} deg"


def test_explicit_control_params_still_override_the_scaled_default():
    sigma = _run_inertial3d_idealized(
        control_params={"K": 3.5, "P": 30.0}, inertia=_SCHEMA_DEFAULT_INERTIA,
        rate_s=1.0, duration_s=120.0,
    )
    assert np.any(np.isnan(sigma)), (
        "explicit control_params={'K': 3.5, 'P': 30.0} should still reach the documented NaN divergence "
        "unchanged -- the new inertia-scaled default must only apply when K/P are NOT given explicitly"
    )
