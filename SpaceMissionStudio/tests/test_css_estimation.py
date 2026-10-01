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

"""Tests for engine.fsw.build_css_sun_estimation -- real sun-heading
ESTIMATION (not truth) from a dedicated CoarseSunSensor cluster +
cssWlsEst, feeding fsw_mode 'sunSafePoint' via build_guidance's
sun_direction_override_msg (schema.scenario's
SpacecraftConfig.fsw_params['use_css_estimation']).

Like tests/test_mtb_desaturation.py, this calls engine.fsw's builder
functions directly against a bare SimulationBaseClass rather than going
through SimulationService (SPICE-blocked in this sandbox) -- the sun is
stood in with a fixed, motionless SpicePlanetStateMsgPayload rather than a
real SPICE ephemeris (no orientation-matrix concern here: cssWlsEst only
needs the sun's POSITION, not its own body-fixed orientation, unlike
magneticFieldWMM's planet message).

This also exercises a real CSSConstellation Python-object lifetime
hazard found while building this feature: CSSConstellation.sensorList
does not own the CoarseSunSensor Python objects assigned to it, only a
reference -- a function-local, discarded css_devices list segfaults
Basilisk at InitializeSimulation() with no error message. See
engine.fsw.build_css_sun_estimation's own docstring; this test keeps the
returned css_devices list alive for its own duration the same way
engine.service.SimulationService does (its _css_estimation_devices list).

engine.fsw.DEFAULT_MRP_GAINS (K=3.5, P=30.0) is lifted directly from
Basilisk's own examples/BskSim reference (BSK_Fsw.py's mrpFeedbackRWs),
tuned for that example's 900 kg*m^2 spacecraft. Applied unscaled to this
test's (and templates/14's) 5 kg*m^2 hub it is roughly 180x too stiff --
confirmed directly against a real Basilisk build to produce a persistent,
non-decaying ~30-degree pointing oscillation (bounded by RW torque
saturation, not a crash, but never actually converging). Scaling K and P
by this hub's inertia relative to that reference (both x 5/900) converges
cleanly instead -- this test uses that same scaled gain pair. See
HISTORY.md for the full investigation.

Requires a Basilisk build (marked ``requires_basilisk``; see
tests/conftest.py).
"""

import numpy as np
import pytest

from spacemissionstudio.schema.scenario import ActuatorConfig, SensorConfig

pytestmark = pytest.mark.requires_basilisk

# Same 8-CSS cube layout as examples/BskSim/models/BSK_Dynamics.py's own
# SetCSSConstellation() -- a real, shipped configuration.
_CSS_NHAT_B = [
    [0.0, 0.707107, 0.707107], [0.707107, 0.0, 0.707107],
    [0.0, -0.707107, 0.707107], [-0.707107, 0.0, 0.707107],
    [0.0, -0.965926, -0.258819], [-0.707107, -0.353553, -0.612372],
    [0.0, 0.258819, -0.965926], [0.707107, -0.353553, -0.612372],
]
_INERTIA = [5.0, 0.0, 0.0, 0.0, 5.0, 0.0, 0.0, 0.0, 5.0]
# Scaled from DEFAULT_MRP_GAINS (K=3.5, P=30.0) by this test's inertia
# relative to the 900 kg*m^2 BSK_Fsw.py reference it's tuned for -- see
# module docstring.
_SCALED_GAINS = {"K": 0.0194, "P": 0.167}


def _run_css_sun_safe_point(duration_s: float, use_real_estimate: bool):
    from Basilisk.architecture import messaging
    from Basilisk.simulation import spacecraft
    from Basilisk.utilities import RigidBodyKinematics as rbk
    from Basilisk.utilities import SimulationBaseClass, macros, simHelpers

    from spacemissionstudio.engine import fsw

    scSim = SimulationBaseClass.SimBaseClass()
    task_name = "task"
    process = scSim.CreateNewProcess("proc")
    process.addTask(scSim.CreateNewTask(task_name, macros.sec2nano(1.0)))

    sc_object = spacecraft.Spacecraft()
    sc_object.ModelTag = "sat"
    sc_object.hub.mHub = 50.0
    sc_object.hub.IHubPntBc_B = simHelpers.np2EigenMatrix3d(_INERTIA)
    sc_object.hub.sigma_BNInit = [[0.1], [0.2], [-0.15]]
    sc_object.hub.omega_BN_BInit = [[0.001], [-0.001], [0.0005]]
    scSim.AddModelToTask(task_name, sc_object, 10)

    sun_dir = np.array([0.1, 0.15, 0.98])
    sun_dir = sun_dir / np.linalg.norm(sun_dir)
    sun_state = messaging.SpicePlanetStateMsgPayload()
    sun_state.PositionVector = list(sun_dir * 1.496e11)
    sun_msg = messaging.SpicePlanetStateMsg().write(sun_state)

    nav = fsw.build_simple_nav(scSim, task_name, "sat", sc_object, sun_state_out_msg=sun_msg)
    veh_config_msg = fsw.build_vehicle_config_msg(_INERTIA)

    css_sensors = [
        SensorConfig(kind="coarse_sun_sensor", name=f"css{i}", params={"nHat_B": nhat, "fov_deg": 160.0})
        for i, nhat in enumerate(_CSS_NHAT_B)
    ]
    sun_est_msg, css_devices = fsw.build_css_sun_estimation(
        scSim, task_name, "sat", sc_object, css_sensors, sun_msg
    )

    guid_msg = fsw.build_guidance(
        scSim, task_name, "sat", "sunSafePoint", {"sHatBdyCmd": [0.0, 0.0, 1.0]}, nav, None, {},
        sun_direction_override_msg=sun_est_msg if use_real_estimate else None,
    )

    rw_actuators = [
        ActuatorConfig(kind="reaction_wheel", name="rw-1",
                        params={"gsHat_B": [1.0, 0.0, 0.0], "rw_type": "Honeywell_HR16", "maxMomentum": 100.0}),
        ActuatorConfig(kind="reaction_wheel", name="rw-2",
                        params={"gsHat_B": [0.0, 1.0, 0.0], "rw_type": "Honeywell_HR16", "maxMomentum": 100.0}),
        ActuatorConfig(kind="reaction_wheel", name="rw-3",
                        params={"gsHat_B": [0.0, 0.0, 1.0], "rw_type": "Honeywell_HR16", "maxMomentum": 100.0}),
    ]
    _, rw_state_effector, rw_config_msg = fsw.build_reaction_wheels(scSim, task_name, "sat", sc_object, rw_actuators)
    mrp = fsw.build_mrp_feedback(
        scSim, task_name, "sat", guid_msg, veh_config_msg, _SCALED_GAINS,
        rw_config_msg=rw_config_msg, rw_speed_out_msg=rw_state_effector.rwSpeedOutMsg,
    )
    fsw.build_rw_motor_torque(scSim, task_name, "sat", mrp, rw_config_msg, rw_state_effector)

    sc_rec = sc_object.scStateOutMsg.recorder()
    scSim.AddModelToTask(task_name, sc_rec)
    est_rec = sun_est_msg.recorder()
    scSim.AddModelToTask(task_name, est_rec)

    scSim.InitializeSimulation()
    scSim.ConfigureStopTime(macros.sec2nano(duration_s))
    scSim.ExecuteSimulation()

    sigma = np.array(sc_rec.sigma_BN)
    angle_errors_deg = np.array([
        np.degrees(np.arccos(np.clip(np.dot(rbk.MRP2C(s).T @ np.array([0.0, 0.0, 1.0]), sun_dir), -1.0, 1.0)))
        for s in sigma
    ])
    est_sun_final = np.array(est_rec.vehSunPntBdy)[-1]
    return sigma, angle_errors_deg, est_sun_final


def test_css_sun_heading_estimate_drives_sun_safe_point_to_point_at_the_sun():
    """Closed loop driven by the REAL CSS-WLS estimate (not truth) --
    confirms the segfault fix (css_devices kept alive) and that the
    scaled gains converge the body +Z axis (sHatBdyCmd) onto the real sun
    direction, using only the estimate as feedback.
    """
    sigma, angle_errors_deg, est_sun_final = _run_css_sun_safe_point(duration_s=1500.0, use_real_estimate=True)
    assert not np.any(np.isnan(sigma)), "attitude went non-physical (NaN) -- see module docstring on gain scaling"
    assert angle_errors_deg[-1] < 1.0, (
        f"body +Z axis did not converge onto the true sun direction: final pointing error "
        f"{angle_errors_deg[-1]:.4f} degrees"
    )
    # The CSS estimate itself should also have settled near the body +Z
    # axis (sHatBdyCmd) by the time the real attitude has converged.
    assert np.linalg.norm(est_sun_final - np.array([0.0, 0.0, 1.0])) < 0.05, (
        f"CSS sun-heading estimate did not settle near sHatBdyCmd=[0,0,1] in the body frame at the end "
        f"of the run: final estimate {est_sun_final}"
    )


def test_css_sun_heading_estimate_matches_truth_driven_behavior():
    """The CSS estimate is accurate enough (well-conditioned 4-of-8 CSS
    geometry for this sun direction) that driving sunSafePoint from it
    converges to essentially the same final pointing accuracy as driving
    it from simpleNav's own noise-free truth sun direction.
    """
    _, truth_errors_deg, _ = _run_css_sun_safe_point(duration_s=1500.0, use_real_estimate=False)
    _, css_errors_deg, _ = _run_css_sun_safe_point(duration_s=1500.0, use_real_estimate=True)
    assert abs(truth_errors_deg[-1] - css_errors_deg[-1]) < 1.0, (
        f"CSS-driven final pointing error ({css_errors_deg[-1]:.4f} deg) diverged meaningfully from the "
        f"truth-driven one ({truth_errors_deg[-1]:.4f} deg) for this well-conditioned sun direction"
    )
