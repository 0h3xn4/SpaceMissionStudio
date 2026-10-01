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

"""Tests for engine.mission_engine.MissionEngine._run_lambert_transfer --
the 'lambert_transfer' Mission Sequence command kind, which solves for and
applies the impulsive delta-V that takes a spacecraft to a target position
after a given time of flight, via Basilisk's own lambertPlanner ->
lambertSolver -> lambertValidator chain (confirmed against
examples/scenarioLambertSolver.py's own usage).

Like the rest of this project's requires_basilisk tests, this calls the
method directly against a minimal stand-in for MissionEngine's own
`self.service` (just `.mu` and `.spacecraft_handles`, the only two
attributes `_run_lambert_transfer` actually reads) rather than going
through the full SimulationService.build() (SPICE-blocked in this
sandbox) -- the spacecraft's position/velocity state objects themselves
are real (dynManager.getStateObject(), exactly what engine.mission_engine
._run_maneuver already relies on), so this exercises the real Basilisk
Lambert chain and the real state-manipulation mechanism, just not routed
through a full scenario build.

Requires a Basilisk build (marked ``requires_basilisk``; see
tests/conftest.py).
"""

from types import SimpleNamespace

import numpy as np
import pytest

from spacemissionstudio.schema.command import Command

pytestmark = pytest.mark.requires_basilisk

_MU = 3.986004418e14
_R_EARTH = 6378.0e3


def _build_spacecraft_with_state(r_bn_n, v_bn_n):
    from Basilisk.simulation import spacecraft
    from Basilisk.utilities import SimulationBaseClass, macros

    scSim = SimulationBaseClass.SimBaseClass()
    process = scSim.CreateNewProcess("proc")
    process.addTask(scSim.CreateNewTask("task", macros.sec2nano(10.0)))

    sc_object = spacecraft.Spacecraft()
    sc_object.ModelTag = "sat"
    sc_object.hub.mHub = 330.0
    sc_object.hub.r_CN_NInit = list(r_bn_n)
    sc_object.hub.v_CN_NInit = list(v_bn_n)
    scSim.AddModelToTask("task", sc_object, 10)

    scSim.InitializeSimulation()  # builds dynManager's state objects
    return scSim, sc_object


def test_lambert_transfer_applies_a_delta_v_that_reaches_the_target():
    from Basilisk.utilities import orbitalMotion

    from spacemissionstudio.engine.mission_engine import MissionEngine

    oe = orbitalMotion.ClassicElements()
    oe.a = 10000.0e3
    oe.e = 0.001
    oe.i = np.radians(5.0)
    oe.Omega = np.radians(10.0)
    oe.omega = np.radians(10.0)
    oe.f = np.radians(10.0)
    r_bn_n, v_bn_n = orbitalMotion.elem2rv(_MU, oe)

    scSim, sc_object = _build_spacecraft_with_state(r_bn_n, v_bn_n)

    target_position_m = [-(_R_EARTH + 200.0e3), 0.0, 0.0]
    time_of_flight_s = 2490.0  # matches examples/scenarioLambertSolver.py's own tf-tm

    handle = SimpleNamespace(sc_object=sc_object)
    service = SimpleNamespace(mu=_MU, spacecraft_handles={"sat-1": handle})
    engine = SimpleNamespace(service=service)

    command = Command(kind="lambert_transfer", params={
        "spacecraft": "sat-1",
        "target_position_m": target_position_m,
        "time_of_flight_s": time_of_flight_s,
    })
    assert command.validate("test") == []

    MissionEngine._run_lambert_transfer(engine, command, summary=None, path="test")

    vel_ref = sc_object.dynManager.getStateObject(sc_object.hub.nameOfHubVelocity)
    pos_ref = sc_object.dynManager.getStateObject(sc_object.hub.nameOfHubPosition)
    from Basilisk.utilities import simHelpers
    v_after = simHelpers.EigenVector3d2np(vel_ref.getState())
    r_after = simHelpers.EigenVector3d2np(pos_ref.getState())

    assert not np.allclose(v_after, v_bn_n), "lambert_transfer did not change the spacecraft's velocity at all"
    np.testing.assert_allclose(r_after, r_bn_n, atol=1e-6), "lambert_transfer must not change position directly"

    # Propagate the post-burn state forward by time_of_flight_s with a
    # simple two-body RK4 integrator and confirm it actually reaches the
    # targeted position -- the real end-to-end correctness check.
    def accel(r):
        return -_MU * r / np.linalg.norm(r) ** 3

    def rk4_propagate(r0, v0, dt, steps=2000):
        r, v = np.array(r0, dtype=float), np.array(v0, dtype=float)
        h = dt / steps
        for _ in range(steps):
            k1r, k1v = v, accel(r)
            k2r, k2v = v + 0.5 * h * k1v, accel(r + 0.5 * h * k1r)
            k3r, k3v = v + 0.5 * h * k2v, accel(r + 0.5 * h * k2r)
            k4r, k4v = v + h * k3v, accel(r + h * k3r)
            r = r + (h / 6) * (k1r + 2 * k2r + 2 * k3r + k4r)
            v = v + (h / 6) * (k1v + 2 * k2v + 2 * k3v + k4v)
        return r, v

    r_final, _ = rk4_propagate(r_after, v_after, time_of_flight_s)
    miss_distance_m = np.linalg.norm(r_final - np.array(target_position_m))
    assert miss_distance_m < 1.0, (
        f"the computed delta-V does not actually reach the target position: miss distance "
        f"{miss_distance_m:.3f} m after propagating {time_of_flight_s} s"
    )


def test_lambert_transfer_unreachable_target_raises_a_clear_error():
    from spacemissionstudio.engine.mission_engine import MissionEngine, MissionEngineError

    # A circular low orbit with a target position barely outside it and an
    # absurdly short time of flight -- physically requires a huge delta-V
    # the minOrbitRadius constraint (set to the current orbit's own radius)
    # should reject as dipping through the central body.
    r_bn_n = [7000.0e3, 0.0, 0.0]
    v_bn_n = [0.0, np.sqrt(_MU / 7000.0e3), 0.0]
    scSim, sc_object = _build_spacecraft_with_state(r_bn_n, v_bn_n)

    handle = SimpleNamespace(sc_object=sc_object)
    service = SimpleNamespace(mu=_MU, spacecraft_handles={"sat-1": handle})
    engine = SimpleNamespace(service=service)

    command = Command(kind="lambert_transfer", params={
        "spacecraft": "sat-1",
        "target_position_m": [-7050.0e3, 0.0, 0.0],
        "time_of_flight_s": 5.0,
        "min_orbit_radius_m": _R_EARTH,
    })
    assert command.validate("test") == []

    with pytest.raises(MissionEngineError, match="lambertValidator reported"):
        MissionEngine._run_lambert_transfer(engine, command, summary=None, path="test")
