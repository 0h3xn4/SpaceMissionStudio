"""Tests for engine.vizard._rtn_panel_label/_usable_label_width_px -- plain
functions, no Basilisk import needed (engine.vizard's own Basilisk imports
are all lazy, inside enable_vizard() -- see that module's docstring), so
this runs even in this development sandbox without a Basilisk build,
unlike tests/test_vizard.py (marked requires_basilisk).

Regression coverage for two real user reports on the RTN separation
panels (see engine.vizard's own docstring, "Real bug found from a real
running Vizard screenshot, FOURTH round"): the panels didn't say WHOSE
offset they showed, fixed by folding the chief's name into the label; and
Vizard truncates a panel row's own label -- but at a width that SCALES
with the follower spacecraft's own name (see _usable_label_width_px's own
docstring, reverse-engineered directly from 0h3xn4/vizard's Unity
source), not a flat per-row constant as an earlier revision of this fix
assumed. A chief name (or even the short generic fallback) long enough to
risk exceeding that scenario's own budget must fall back further rather
than risk being cut off mid-word.
"""

from spacemissionstudio.engine.vizard import _rtn_panel_label, _usable_label_width_px


def test_usable_width_stays_at_the_minimum_for_a_short_spacecraft_name():
    # len("sat-1" + " Storage") == 13, <= 16 -- Vizard's own
    # GenericStoragePanelMethods.cs never widens the bar past its
    # hardcoded 90px default in this case.
    assert _usable_label_width_px("sat-1") == 90.0 - 3.0


def test_usable_width_grows_with_a_longer_spacecraft_name():
    # len("follower-1" + " Storage") == 18, > 16 -- widened to 18*7px.
    assert _usable_label_width_px("follower-1") == 18 * 7.0 - 3.0
    assert _usable_label_width_px("follower-1") > _usable_label_width_px("sat-1")


def test_short_chief_name_is_used_directly_on_a_wide_enough_panel():
    # follower-1's own panel (123px usable) is wide enough for all three.
    assert _rtn_panel_label("R", "chief-1", "follower-1") == "R vs chief-1"
    assert _rtn_panel_label("T", "chief-1", "follower-1") == "T vs chief-1"
    assert _rtn_panel_label("N", "chief-1", "follower-1") == "N vs chief-1"


def test_long_chief_name_falls_back_to_the_generic_label():
    long_name = "a-very-long-chief-spacecraft-name"
    label = _rtn_panel_label("R", long_name, "follower-1")
    assert label == "R vs chief"
    assert long_name not in label  # never a half-truncated name


def test_narrow_panel_falls_back_further_than_the_generic_label():
    """Regression guard for the real gap this investigation found: a
    SHORT follower spacecraft name gives a narrower panel (87px usable)
    than the one a real screenshot confirmed ("follower-1", 123px) --
    even the generic "R vs chief" (10 characters) doesn't safely fit
    there, so this must fall back all the way to the bare axis letter
    rather than assume the generic fallback is always narrow enough.
    """
    label = _rtn_panel_label("R", "chief-1", "sat-1")
    assert label == "R"


def test_label_never_exceeds_that_scenarios_own_usable_width():
    for follower_name in ("sat-1", "follower-1", "a-very-long-follower-spacecraft-name", "x"):
        max_len = _usable_label_width_px(follower_name) / 9.5  # _PIXELS_PER_LABEL_CHARACTER_ESTIMATE
        for axis in ("R", "T", "N"):
            for chief_name in ("", "c", "chief-1", "a-very-long-chief-spacecraft-name"):
                assert len(_rtn_panel_label(axis, chief_name, follower_name)) <= max_len + 1e-9


def test_empty_chief_name_falls_back_to_the_generic_label():
    assert _rtn_panel_label("N", "", "follower-1") == "N vs chief"


def test_bare_axis_letter_always_fits_even_on_the_narrowest_realistic_panel():
    # A single-character follower name is the narrowest realistic case
    # (still under the widening threshold) -- the bare axis letter (1
    # character) must always be a safe last resort.
    for axis in ("R", "T", "N"):
        assert _rtn_panel_label(axis, "a-very-long-chief-spacecraft-name", "x") == axis
