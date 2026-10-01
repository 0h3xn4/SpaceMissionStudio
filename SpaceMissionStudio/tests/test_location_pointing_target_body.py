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

"""Tests for engine.fsw.build_ephemeris_converter + fsw_mode
'locationPointing'/fsw_params['target_body'] -- direct celestial-body
pointing (as opposed to the pre-existing 'target_ground_station' option),
confirmed against examples/scenarioAsteroidArrival.py's own
ephemerisConverter + locationPointing usage.

Like tests/test_mtb_desaturation.py, this calls engine.fsw's builder
functions directly against a bare SimulationBaseClass rather than going
through SimulationService (SPICE-blocked in this sandbox) -- the target
body is stood in with a fixed, motionless SpicePlanetStateMsgPayload
rather than a real SPICE ephemeris (celBodyInMsg only needs
r_BdyZero_N/v_BdyZero_N, both populated by ephemerisConverter from the
stand-in's PositionVector/VelocityVector, no orientation-matrix concern
here).

engine.fsw.DEFAULT_MRP_GAINS (K=3.5, P=30.0) is tuned for a 900 kg*m^2
reference spacecraft running its FSW task at a 0.1s rate (see
tests/test_css_estimation.py's own docstring and HISTORY.md for the full
investigation) -- this test uses that same fine task rate with the
default gains and a comparably large inertia, rather than scaling the
gains down, to additionally confirm the OTHER documented fix still holds
for idealized actuation.

Requires a Basilisk build (marked ``requires_basilisk``; see
tests/conftest.py).
"""

import numpy as np
import pytest

pytestmark = pytest.mark.requires_basilisk


def _run_location_pointing_at_target_body(target_dir, duration_s: float):
    from Basilisk.architecture import messaging
    from Basilisk.simulation import spacecraft
    from Basilisk.utilities import RigidBodyKinematics as rbk
    from Basilisk.utilities import SimulationBaseClass, macros, simHelpers

    from spacemissionstudio.engine import fsw

    scSim = SimulationBaseClass.SimBaseClass()
    task_name = "task"
    process = scSim.CreateNewProcess("proc")
    process.addTask(scSim.CreateNewTask(task_name, macros.sec2nano(0.1)))

    sc_object = spacecraft.Spacecraft()
    sc_object.ModelTag = "sat"
    inertia = [10.0, 0.0, 0.0, 0.0, 10.0, 0.0, 0.0, 0.0, 10.0]
    sc_object.hub.mHub = 100.0
    sc_object.hub.IHubPntBc_B = simHelpers.np2EigenMatrix3d(inertia)
    sc_object.hub.sigma_BNInit = [[0.05], [0.03], [-0.02]]
    sc_object.hub.omega_BN_BInit = [[0.0], [0.0], [0.0]]
    # Spacecraft position is small relative to the target body's own
    # distance below, so target_dir (an origin-relative direction) is also
    # a good approximation of the spacecraft-relative direction
    # locationPointing actually computes.
    sc_object.hub.r_CN_NInit = [[7000.0e3], [0.0], [0.0]]
    sc_object.hub.v_CN_NInit = [[0.0], [7.5e3], [0.0]]
    scSim.AddModelToTask(task_name, sc_object, 10)

    body_state = messaging.SpicePlanetStateMsgPayload()
    body_state.PlanetName = "moon"
    body_state.PositionVector = list(np.asarray(target_dir) * 3.844e8)
    body_msg = messaging.SpicePlanetStateMsg().write(body_state)

    nav = fsw.build_simple_nav(scSim, task_name, "sat", sc_object)
    veh_config_msg = fsw.build_vehicle_config_msg(inertia)
    eph_msg = fsw.build_ephemeris_converter(scSim, task_name, "sat", "moon", body_msg)

    guid_msg = fsw.build_guidance(
        scSim, task_name, "sat", "locationPointing", {"target_body": "moon", "pHat_B": [0.0, 0.0, 1.0]},
        nav, None, {}, target_body_eph_msg=eph_msg,
    )
    mrp = fsw.build_mrp_feedback(scSim, task_name, "sat", guid_msg, veh_config_msg, {})
    fsw.build_idealized_actuation(scSim, task_name, "sat", sc_object, mrp)

    sc_rec = sc_object.scStateOutMsg.recorder()
    scSim.AddModelToTask(task_name, sc_rec)

    scSim.InitializeSimulation()
    scSim.ConfigureStopTime(macros.sec2nano(duration_s))
    scSim.ExecuteSimulation()

    sigma = np.array(sc_rec.sigma_BN)
    angle_errors_deg = np.array([
        np.degrees(np.arccos(np.clip(
            np.dot(rbk.MRP2C(s).T @ np.array([0.0, 0.0, 1.0]), target_dir / np.linalg.norm(target_dir)),
            -1.0, 1.0,
        )))
        for s in sigma
    ])
    return sigma, angle_errors_deg


def test_location_pointing_target_body_converges_pHat_B_onto_the_target_direction():
    target_dir = np.array([0.2, 0.9, 0.1])
    sigma, angle_errors_deg = _run_location_pointing_at_target_body(target_dir, duration_s=1500.0)
    assert not np.any(np.isnan(sigma)), "attitude went non-physical (NaN)"
    assert angle_errors_deg[-1] < 1.0, (
        f"pHat_B did not converge onto the target body direction: final pointing error "
        f"{angle_errors_deg[-1]:.4f} degrees"
    )
    assert angle_errors_deg[0] > 45.0, "test setup expects a large initial pointing error to converge from"
