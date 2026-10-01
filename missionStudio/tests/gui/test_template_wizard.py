"""Tests for gui.template_wizard -- the guided, multi-step "Customize..."
wizard built over a curated subset of a bundled template's own
parameters (see that module's own docstring for scope/rationale).
"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.requires_gui

_ALL_TEMPLATE_FILENAMES = sorted(
    p.name for p in (Path(__file__).resolve().parent.parent.parent
                      / "missionstudio" / "scenarios" / "templates").glob("*.json")
)


def test_every_registered_spec_matches_a_real_bundled_template():
    """Regression guard: a typo'd filename in _SPECS would otherwise
    silently mean that template's "Customize..." button never lights up,
    with no error anywhere pointing at why.
    """
    from missionstudio.gui.load_scenario_widget import TEMPLATES_DIR
    from missionstudio.gui.template_wizard import _SPECS

    bundled = {p.name for p in TEMPLATES_DIR.glob("*.json")}
    for filename in _SPECS:
        assert filename in bundled, f"{filename} has a wizard spec but no matching bundled template file"


def test_every_bundled_template_has_a_registered_spec():
    """Every template ('01' through '18') has one -- see this module's
    own docstring for the staged rollout history (a 3-template pilot,
    then every other template in one follow-up pass).
    """
    from missionstudio.gui.load_scenario_widget import TEMPLATES_DIR
    from missionstudio.gui.template_wizard import get_wizard_spec

    bundled = sorted(p.name for p in TEMPLATES_DIR.glob("*.json"))
    assert len(bundled) >= 18
    missing = [name for name in bundled if get_wizard_spec(name) is None]
    assert missing == [], f"these bundled templates have no registered wizard spec: {missing}"


def test_get_wizard_spec_returns_none_for_an_unregistered_template():
    from missionstudio.gui.template_wizard import get_wizard_spec

    assert get_wizard_spec("99_not_a_real_template.json") is None


@pytest.mark.parametrize("filename", _ALL_TEMPLATE_FILENAMES)
def test_wizard_pages_are_prefilled_with_the_templates_own_current_values(qtbot, filename):
    from missionstudio.gui.load_scenario_widget import TEMPLATES_DIR
    from missionstudio.gui.template_wizard import TemplateCustomizeWizard, get_wizard_spec
    from missionstudio.schema import load_scenario

    scenario = load_scenario(TEMPLATES_DIR / filename)
    spec = get_wizard_spec(filename)
    wizard = TemplateCustomizeWizard(scenario, spec)
    qtbot.addWidget(wizard)

    for page_id, page_spec in zip(wizard.pageIds(), spec.pages):
        page = wizard.page(page_id)
        assert page.title() == page_spec.title
        for field_spec, box in zip(page_spec.fields, page._boxes):
            assert box.value() == pytest.approx(field_spec.get(scenario))


def test_finishing_without_changes_reproduces_the_original_scenario(qtbot):
    from missionstudio.gui.load_scenario_widget import TEMPLATES_DIR
    from missionstudio.gui.template_wizard import TemplateCustomizeWizard, get_wizard_spec
    from missionstudio.schema import load_scenario

    path = TEMPLATES_DIR / "03_geo_station_keeping.json"
    scenario = load_scenario(path)
    wizard = TemplateCustomizeWizard(scenario, get_wizard_spec(path.name))
    qtbot.addWidget(wizard)

    wizard.accept()

    result = wizard.result_scenario()
    result.validate()
    assert result.to_dict() == scenario.to_dict()


def test_finishing_applies_edited_values_and_leaves_the_original_scenario_untouched(qtbot):
    from missionstudio.gui.load_scenario_widget import TEMPLATES_DIR
    from missionstudio.gui.template_wizard import TemplateCustomizeWizard, get_wizard_spec
    from missionstudio.schema import load_scenario

    path = TEMPLATES_DIR / "03_geo_station_keeping.json"
    scenario = load_scenario(path)
    wizard = TemplateCustomizeWizard(scenario, get_wizard_spec(path.name))
    qtbot.addWidget(wizard)

    controller_page = wizard.page(0)
    controller_page._boxes[0].setValue(2.5)  # deadband_km
    controller_page._boxes[1].setValue(0.75)  # thrust_n
    duration_page = wizard.page(1)
    duration_page._boxes[0].setValue(30.0)  # duration_days

    wizard.accept()

    result = wizard.result_scenario()
    result.validate()
    sat = result.spacecraft[0]
    assert sat.station_keeping.deadband_km == 2.5
    assert sat.station_keeping.thrust_n == 0.75
    assert result.sim_settings.duration_days == 30.0
    # The Scenario the wizard was constructed from must be untouched --
    # it operates on its own internal copy (see TemplateCustomizeWizard's
    # own docstring).
    assert scenario.spacecraft[0].station_keeping.deadband_km == 5.0
    assert scenario.sim_settings.duration_days == 14.0
    # And the bundled template FILE itself must be untouched too.
    assert load_scenario(path).spacecraft[0].station_keeping.deadband_km == 5.0


def test_leo_altitude_field_moves_both_target_altitude_and_orbit_semi_major_axis(qtbot):
    """The one field in this first pass whose setter touches two
    dataclass locations at once -- see template_wizard._set_leo_altitude_km's
    own comment for why (orbit.semi_major_axis_km is measured from the
    central body's CENTER, station_keeping.target_altitude_km from its
    surface). The expected offset is THIS TEMPLATE's own
    (semi_major_axis_km - target_altitude_km = 6778.0 - 400.0 = 6378.0,
    not Basilisk's more precise earth.radEquator (6378.1366) -- see
    _set_leo_altitude_km's own comment for why using that constant
    directly instead of this template's own offset was a real,
    now-fixed bug).
    """
    from missionstudio.gui.load_scenario_widget import TEMPLATES_DIR
    from missionstudio.gui.template_wizard import TemplateCustomizeWizard, get_wizard_spec
    from missionstudio.schema import load_scenario

    path = TEMPLATES_DIR / "18_leo_station_keeping.json"
    scenario = load_scenario(path)
    original_offset_km = scenario.spacecraft[0].orbit.semi_major_axis_km - 400.0
    wizard = TemplateCustomizeWizard(scenario, get_wizard_spec(path.name))
    qtbot.addWidget(wizard)

    altitude_page = wizard.page(0)
    altitude_page._boxes[0].setValue(350.0)
    wizard.accept()

    result = wizard.result_scenario()
    result.validate()
    sat = result.spacecraft[0]
    assert sat.station_keeping.target_altitude_km == 350.0
    assert sat.orbit.semi_major_axis_km == pytest.approx(350.0 + original_offset_km)


def test_reaction_wheel_max_momentum_applies_to_every_wheel_uniformly(qtbot):
    from missionstudio.gui.load_scenario_widget import TEMPLATES_DIR
    from missionstudio.gui.template_wizard import TemplateCustomizeWizard, get_wizard_spec
    from missionstudio.schema import load_scenario

    path = TEMPLATES_DIR / "07_attitude_pointing_with_adcs_hardware.json"
    scenario = load_scenario(path)
    wizard = TemplateCustomizeWizard(scenario, get_wizard_spec(path.name))
    qtbot.addWidget(wizard)

    wizard.page(0)._boxes[0].setValue(250.0)
    wizard.accept()

    result = wizard.result_scenario()
    result.validate()
    wheel_momenta = [a.params["maxMomentum"] for a in result.spacecraft[0].actuators if a.kind == "reaction_wheel"]
    assert wheel_momenta == [250.0, 250.0, 250.0]


@pytest.mark.parametrize("filename", _ALL_TEMPLATE_FILENAMES)
def test_wizard_is_sized_to_fit_its_own_busiest_page_not_a_flat_default(qtbot, filename):
    """Regression test for a real bug, found from a user screenshot:
    QWizard.sizeHint() does NOT reflect its own pages' content at all --
    it measures a flat 500x360 regardless of what spec/pages were given
    (confirmed directly), so several pages' intro text and field rows
    rendered clipped. TemplateCustomizeWizard.__init__ now explicitly
    sizes itself from the widest/tallest page across the WHOLE wizard.
    """
    from missionstudio.gui.load_scenario_widget import TEMPLATES_DIR
    from missionstudio.gui.template_wizard import TemplateCustomizeWizard, get_wizard_spec
    from missionstudio.schema import load_scenario

    scenario = load_scenario(TEMPLATES_DIR / filename)
    wizard = TemplateCustomizeWizard(scenario, get_wizard_spec(filename))
    qtbot.addWidget(wizard)

    busiest_page_width = max(p.sizeHint().width() for p in wizard._field_pages)
    busiest_page_height = max(p.sizeHint().height() for p in wizard._field_pages)
    assert wizard.size().width() >= busiest_page_width
    assert wizard.size().height() >= busiest_page_height + 100  # room for QWizard's own title/nav chrome


@pytest.mark.parametrize("filename", _ALL_TEMPLATE_FILENAMES)
def test_every_spec_round_trips_with_no_edits(qtbot, filename):
    """Every registered spec, finished with no edits at all, must
    reproduce the original template byte-for-byte -- confirms every
    field's get()/set() pair agrees on the same value (a get() that
    reads the wrong list index/attribute would otherwise still "work"
    right up until a round-trip test like this one actually compared
    before/after).
    """
    from missionstudio.gui.load_scenario_widget import TEMPLATES_DIR
    from missionstudio.gui.template_wizard import TemplateCustomizeWizard, get_wizard_spec
    from missionstudio.schema import load_scenario

    scenario = load_scenario(TEMPLATES_DIR / filename)
    wizard = TemplateCustomizeWizard(scenario, get_wizard_spec(filename))
    qtbot.addWidget(wizard)

    wizard.accept()

    result = wizard.result_scenario()
    result.validate()
    assert result.to_dict() == scenario.to_dict()


@pytest.mark.parametrize("filename", _ALL_TEMPLATE_FILENAMES)
def test_every_spec_still_validates_after_nudging_every_field(qtbot, filename):
    """Nudges every field by one step within its own declared range and
    confirms the result is still a schema-valid Scenario -- a cheap,
    broad check that no field's chosen (minimum, maximum, step) combination
    can produce an invalid Scenario via entirely ordinary use of the
    spin box (as opposed to typing an extreme value by hand).
    """
    from missionstudio.gui.load_scenario_widget import TEMPLATES_DIR
    from missionstudio.gui.template_wizard import TemplateCustomizeWizard, get_wizard_spec
    from missionstudio.schema import load_scenario

    scenario = load_scenario(TEMPLATES_DIR / filename)
    spec = get_wizard_spec(filename)
    wizard = TemplateCustomizeWizard(scenario, spec)
    qtbot.addWidget(wizard)

    for page, page_spec in zip(wizard._field_pages, spec.pages):
        for box, field_spec in zip(page._boxes, page_spec.fields):
            nudged = box.value() + field_spec.step
            if nudged > field_spec.maximum:
                nudged = box.value() - field_spec.step
            box.setValue(nudged)

    wizard.accept()
    result = wizard.result_scenario()
    result.validate()  # must not raise
