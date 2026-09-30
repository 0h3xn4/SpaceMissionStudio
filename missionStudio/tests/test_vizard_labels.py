"""Tests for engine.vizard._rtn_panel_label -- a plain string function,
no Basilisk import needed (engine.vizard's own Basilisk imports are all
lazy, inside enable_vizard() -- see that module's docstring), so this
runs even in this development sandbox without a Basilisk build, unlike
tests/test_vizard.py (marked requires_basilisk).

Regression coverage for two real user reports on the RTN separation
panels (see engine.vizard's own docstring, "Real bug found from a real
running Vizard screenshot, FOURTH round"): the panels didn't say WHOSE
offset they showed, fixed by folding the chief's name into the label;
and Vizard truncates a panel row's own label at a fixed per-row width
(confirmed against a real screenshot elsewhere in this module's history),
so a chief name long enough to risk exceeding that budget must fall back
to a short, generic label rather than risk being cut off mid-word.
"""

from missionstudio.engine.vizard import _rtn_panel_label


def test_short_chief_name_is_used_directly():
    assert _rtn_panel_label("R", "chief-1") == "R vs chief-1"
    assert _rtn_panel_label("T", "chief-1") == "T vs chief-1"
    assert _rtn_panel_label("N", "chief-1") == "N vs chief-1"


def test_long_chief_name_falls_back_to_the_generic_label():
    long_name = "a-very-long-chief-spacecraft-name"
    label = _rtn_panel_label("R", long_name)
    assert label == "R vs chief"
    assert long_name not in label  # never a half-truncated name


def test_label_never_exceeds_the_confirmed_safe_width():
    for axis in ("R", "T", "N"):
        for chief_name in ("", "c", "chief-1", "a-very-long-chief-spacecraft-name"):
            assert len(_rtn_panel_label(axis, chief_name)) <= 14


def test_empty_chief_name_falls_back_to_the_generic_label():
    assert _rtn_panel_label("N", "") == "N vs chief"
