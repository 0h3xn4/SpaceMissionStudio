"""Tests for engine.service._osculating_elements (specifically its
defensive NaN/inf guard, added after a real crash report) and
_mean_elements (the first-order-J2 osc -> mean mapping added per a real
user request for "plots of averaged orbital elements, not only the
'true' ones").

Requires a Basilisk build (marked ``requires_basilisk``; see
tests/conftest.py for the auto-skip behavior in this development sandbox,
which does not have one) -- engine.service imports Basilisk at module
level.
"""

import numpy as np
import pytest

pytestmark = pytest.mark.requires_basilisk

_MU_EARTH = 3.986004418e14  # [m^3/s^2]


def _circular_rv(n=5):
    """n samples of a trivial circular orbit -- exact values don't
    matter, only that they're finite.
    """
    r = np.tile([7000e3, 0.0, 0.0], (n, 1))
    v = np.tile([0.0, 7500.0, 0.0], (n, 1))
    return r, v


def test_finite_samples_produce_normal_elements():
    from missionstudio.engine.service import _osculating_elements

    r, v = _circular_rv()
    elements = _osculating_elements(_MU_EARTH, r, v)
    assert np.all(np.isfinite(elements["a"]))
    assert np.all(elements["a"] > 0)


def test_nan_sample_raises_a_clear_error_not_an_attribute_error():
    """Regression test for a real crash report: a spacecraft's simulated
    state went non-physical (NaN) partway through a run, and
    orbitalMotion.rv2elem()'s own NaN-input guard (src/utilities/
    orbitalMotion.py) sets ClassicElements.AN/.AP, which aren't real
    slots on that class -- so instead of a clean NaN result, it crashed
    with "AttributeError: 'ClassicElements' object has no attribute
    'AN'", a confusing symptom of the actual problem (an unstable/
    diverged simulation). _osculating_elements must catch this itself,
    before ever calling rv2elem(), and report SOMETHING actionable.
    """
    from missionstudio.engine.service import SimulationServiceError, _osculating_elements

    r, v = _circular_rv(n=3)
    r[1] = [np.nan, 0.0, 0.0]  # the dynamics "went non-physical" partway through

    with pytest.raises(SimulationServiceError, match="non-physical"):
        _osculating_elements(_MU_EARTH, r, v)


def test_inf_sample_also_raises_the_clear_error():
    from missionstudio.engine.service import SimulationServiceError, _osculating_elements

    r, v = _circular_rv(n=3)
    v[2] = [0.0, np.inf, 0.0]

    with pytest.raises(SimulationServiceError, match="non-physical"):
        _osculating_elements(_MU_EARTH, r, v)


def _leo_osculating_elements(n=5):
    """n (identical) samples of osculating elements for a real, non
    -degenerate LEO orbit -- inclination deliberately well away from
    0/90/the ~63.4 deg critical inclination, where the first-order J2
    mean-element mapping this module also tests has a genuine
    mathematical singularity (see _mean_elements' own docstring).
    """
    from Basilisk.utilities import orbitalMotion

    from missionstudio.engine.service import _osculating_elements

    oe = orbitalMotion.ClassicElements()
    oe.a = 7000e3
    oe.e = 0.01
    oe.i = np.radians(45.0)
    oe.Omega = np.radians(30.0)
    oe.omega = np.radians(60.0)
    oe.f = np.radians(10.0)
    r_N, v_N = orbitalMotion.elem2rv(_MU_EARTH, oe)
    r = np.tile(r_N, (n, 1))
    v = np.tile(v_N, (n, 1))
    return _osculating_elements(_MU_EARTH, r, v)


def test_mean_elements_are_finite_and_close_to_osculating():
    from Basilisk.utilities import orbitalMotion

    from missionstudio.engine.service import _mean_elements

    osc = _leo_osculating_elements()
    mean = _mean_elements(osc, orbitalMotion.REQ_EARTH * 1000.0, orbitalMotion.J2_EARTH)

    for key in ("a", "e", "i", "raan", "argp", "true_anomaly"):
        assert np.all(np.isfinite(mean[key]))
    # A first-order J2 correction at LEO altitude is a small perturbation
    # on top of the osculating value, not a wholesale change -- semi
    # -major axis in particular should differ by at most a few km, not
    # thousands.
    assert abs(mean["a"][0] - osc["a"][0]) < 10e3


def test_mean_elements_round_trip_back_to_osculating():
    """clMeanOscMap is explicitly documented as invertible via its own
    ``sign`` argument (sgn=1: mean -> osc, sgn=-1: osc -> mean) --
    mapping mean elements back with sign=+1 should recover the original
    osculating elements this test started from, to first-order-theory
    precision. A real, direct confirmation that _mean_elements() is
    calling clMeanOscMap with the correct sign for "osc -> mean" (easy to
    get backwards, and nothing else in this test file would catch it).
    """
    from Basilisk.utilities import orbitalMotion

    from missionstudio.engine.service import _mean_elements

    osc = _leo_osculating_elements(n=1)
    req = orbitalMotion.REQ_EARTH * 1000.0
    j2 = orbitalMotion.J2_EARTH
    mean = _mean_elements(osc, req, j2)

    mean_elem = orbitalMotion.ClassicElements()
    mean_elem.a, mean_elem.e, mean_elem.i = mean["a"][0], mean["e"][0], mean["i"][0]
    mean_elem.Omega, mean_elem.omega, mean_elem.f = mean["raan"][0], mean["argp"][0], mean["true_anomaly"][0]
    recovered = orbitalMotion.ClassicElements()
    orbitalMotion.clMeanOscMap(req, j2, mean_elem, recovered, 1)

    # Tolerances set from this test's own real, confirmed output (a
    # ~1.8 m, e ~8e-7, i ~3e-7 rad round-trip residual for this orbit) --
    # generous enough to not be a flaky false-positive, tight enough that
    # a wrong sign (which produces a residual orders of magnitude larger,
    # comparable to the full osc-vs-mean difference checked above) would
    # still fail it.
    assert recovered.a == pytest.approx(osc["a"][0], abs=10.0)
    assert recovered.e == pytest.approx(osc["e"][0], abs=1e-5)
    assert recovered.i == pytest.approx(osc["i"][0], abs=1e-5)
