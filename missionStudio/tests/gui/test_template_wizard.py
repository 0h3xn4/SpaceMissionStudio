"""Tests for gui.template_wizard -- the guided, multi-step "Customize..."
wizard built over a curated subset of a bundled template's own
parameters (see that module's own docstring for scope/rationale).
"""

import pytest

pytestmark = pytest.mark.requires_gui


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


def test_get_wizard_spec_returns_none_for_an_unregistered_template():
    from missionstudio.gui.template_wizard import get_wizard_spec

    assert get_wizard_spec("01_two_body_circular_orbit.json") is None


@pytest.mark.parametrize("filename", [
    "03_geo_station_keeping.json",
    "18_leo_station_keeping.json",
    "07_attitude_pointing_with_adcs_hardware.json",
])
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
    surface).
    """
    from missionstudio.gui.load_scenario_widget import TEMPLATES_DIR
    from missionstudio.gui.template_wizard import TemplateCustomizeWizard, get_wizard_spec
    from missionstudio.schema import load_scenario

    path = TEMPLATES_DIR / "18_leo_station_keeping.json"
    scenario = load_scenario(path)
    wizard = TemplateCustomizeWizard(scenario, get_wizard_spec(path.name))
    qtbot.addWidget(wizard)

    altitude_page = wizard.page(0)
    altitude_page._boxes[0].setValue(350.0)
    wizard.accept()

    result = wizard.result_scenario()
    result.validate()
    sat = result.spacecraft[0]
    assert sat.station_keeping.target_altitude_km == 350.0
    assert sat.orbit.semi_major_axis_km == pytest.approx(350.0 + 6378.137)


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
