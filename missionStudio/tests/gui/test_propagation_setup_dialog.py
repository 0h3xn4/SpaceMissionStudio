"""Tests for gui.propagation_setup_dialog.PropagationSetupDialog."""

import pytest

pytestmark = pytest.mark.requires_gui


def _dialog(gravity=None, sim_settings=None, space_weather=None):
    from missionstudio.gui.propagation_setup_dialog import PropagationSetupDialog
    from missionstudio.schema.scenario import GravityConfig, SimSettings, SpaceWeatherConfig

    return PropagationSetupDialog(
        gravity or GravityConfig(), sim_settings or SimSettings(), space_weather or SpaceWeatherConfig(),
    )


@pytest.fixture
def dialog(qtbot):
    d = _dialog()
    qtbot.addWidget(d)
    return d


def test_atmosphere_drag_group_title_escapes_its_ampersand(dialog):
    """Regression guard: QGroupBox("Atmosphere & drag") (a single "&")
    used to render as visibly broken ("Atmosphere _drag" in a rendered
    screenshot) because Qt treats a lone "&" in a group box title as a
    mnemonic marker, consuming it instead of displaying it -- found by
    actually rendering this dialog headless and looking at the PNG, not
    by reading the source. "&&" is Qt's own escape for a literal "&";
    QGroupBox.title() returns the raw (still-escaped) string Qt stores,
    not the rendered/mnemonic-resolved text -- confirmed directly here,
    not assumed -- so the regression to guard against is the single-"&"
    form reappearing, not asserting against rendered pixels.
    """
    from PySide6.QtWidgets import QGroupBox

    titles = [gb.title() for gb in dialog.findChildren(QGroupBox)]
    assert "Atmosphere && drag" in titles
    assert "Atmosphere & drag" not in titles


def test_srp_pointer_label_gets_its_full_wrapped_height_not_clipped(dialog):
    """Regression guard for a real rendering bug, found by actually
    looking at this dialog (not just reading the code): the SRP-pointer
    QLabel inside the "Atmosphere & drag" group used to be added via
    QFormLayout.addRow(single_widget), which did not reserve it its full
    wrapped height -- its geometry() was 27px tall while its own
    heightForWidth() said it needed 68px, silently clipping 2 of its 3
    lines. Moved to a plain QVBoxLayout.addWidget() (the same mechanism
    this dialog's own top-level intro_label already used successfully),
    which doesn't have that negotiation problem.
    """
    from PySide6.QtWidgets import QLabel

    dialog.show()
    for _ in range(3):
        from PySide6.QtWidgets import QApplication

        QApplication.processEvents()

    srp_labels = [w for w in dialog.findChildren(QLabel) if "PER SPACECRAFT" in w.text()]
    assert srp_labels, "expected to find the SRP-pointer QLabel"
    label = srp_labels[0]
    needed_height = label.heightForWidth(label.geometry().width())
    assert label.geometry().height() >= needed_height


def test_dialog_resizes_to_its_own_sizehint_on_construction(dialog):
    """Regression guard: this dialog's window used to stay at whatever
    size Qt's FIRST layout pass guessed (871x734, measured directly),
    smaller than its own later-computed sizeHint() (871x768) once every
    group was actually built -- clipping the bottom rows of the last
    group against its own border. Explicitly resizing to sizeHint() at
    the end of __init__ (after every group exists) fixes it.
    """
    assert dialog.size() == dialog.sizeHint()


def test_defaults_round_trip(dialog):
    got_gravity = dialog.to_gravity()
    got_sim = dialog.to_sim_settings()
    got_sw = dialog.to_space_weather()
    from missionstudio.schema.scenario import GravityConfig, SimSettings, SpaceWeatherConfig

    assert got_gravity == GravityConfig()
    assert got_sim == SimSettings()
    assert got_sw == SpaceWeatherConfig()


def test_central_body_removed_from_third_body_choices(dialog):
    dialog.central_body_combo.setCurrentText("sun")
    choices = [dialog.third_body_list.item(i).text() for i in range(dialog.third_body_list.count())]
    assert "sun" not in choices
    assert "earth" in choices


def test_third_body_perturbers_round_trip(qtbot):
    from missionstudio.schema.scenario import GravityConfig

    d = _dialog(gravity=GravityConfig(central_body="earth", third_body_perturbers=["sun", "moon"]))
    qtbot.addWidget(d)
    assert sorted(d.to_gravity().third_body_perturbers) == ["moon", "sun"]


def test_space_weather_local_file_field_enabled_only_for_local_file_source(dialog):
    assert not dialog.local_file_edit.isEnabled()
    dialog.space_weather_source_combo.setCurrentText("local_file")
    assert dialog.local_file_edit.isEnabled()
    dialog.space_weather_source_combo.setCurrentText("synthetic")
    assert not dialog.local_file_edit.isEnabled()


def test_harmonics_checkbox_off_by_default_forces_point_mass(dialog):
    assert not dialog.enable_harmonics_check.isChecked()
    assert dialog.to_gravity().central_body_degree == 0


def test_harmonics_checkbox_preserves_spinner_value_when_toggled_off(dialog):
    """Regression guard for the actual UX fix this dialog makes: unchecking
    "enable spherical harmonics" must not reset/lose the degree the user
    typed -- only fold it to 0 in the OUTPUT (to_gravity()), leaving the
    spinner itself untouched so re-checking the box brings it right back.
    """
    dialog.enable_harmonics_check.setChecked(True)
    dialog.central_body_degree_spin.setValue(20)
    assert dialog.to_gravity().central_body_degree == 20

    dialog.enable_harmonics_check.setChecked(False)
    assert dialog.to_gravity().central_body_degree == 0
    assert dialog.central_body_degree_spin.value() == 20  # not reset

    dialog.enable_harmonics_check.setChecked(True)
    assert dialog.to_gravity().central_body_degree == 20  # comes right back


def test_checking_harmonics_with_zero_degree_bumps_to_a_sane_default(dialog):
    dialog.central_body_degree_spin.setValue(0)
    dialog.enable_harmonics_check.setChecked(True)
    assert dialog.central_body_degree_spin.value() > 0
    assert dialog.to_gravity().central_body_degree > 0


def test_non_earth_central_body_disables_and_clears_harmonics(dialog):
    dialog.enable_harmonics_check.setChecked(True)
    dialog.central_body_degree_spin.setValue(20)

    dialog.central_body_combo.setCurrentText("mars")

    assert not dialog.enable_harmonics_check.isEnabled()
    assert not dialog.enable_harmonics_check.isChecked()
    assert dialog.to_gravity().central_body_degree == 0


def test_loading_existing_harmonics_degree_checks_the_box(qtbot):
    from missionstudio.schema.scenario import GravityConfig

    d = _dialog(gravity=GravityConfig(central_body="earth", central_body_degree=8))
    qtbot.addWidget(d)
    assert d.enable_harmonics_check.isChecked()
    assert d.central_body_degree_spin.value() == 8
    assert d.to_gravity().central_body_degree == 8


def test_accept_with_valid_state_closes_dialog(dialog, qtbot):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDialogButtonBox

    ok_button = dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok)
    qtbot.mouseClick(ok_button, Qt.MouseButton.LeftButton)
    assert dialog.result() == dialog.DialogCode.Accepted


def test_atmosphere_model_defaults_to_nrlmsise00(dialog):
    assert dialog._selected_atmosphere_model() == "nrlmsise00"
    assert dialog.to_space_weather().atmosphere_model == "nrlmsise00"


def test_selecting_exponential_atmosphere_model_round_trips(dialog):
    dialog.atmosphere_model_combo.setCurrentIndex(1)
    assert dialog._selected_atmosphere_model() == "exponential"
    assert dialog.to_space_weather().atmosphere_model == "exponential"


def test_exponential_atmosphere_model_disables_space_weather_controls(dialog):
    """Real user question this answers: 'why can't I select the drag
    model' -- once they can, switching to the model that has no F10.7/Ap
    dependence at all should visibly grey out the controls that only
    apply to NRLMSISE-00, not leave them looking live but silently unused.
    """
    dialog.space_weather_source_combo.setCurrentText("local_file")
    assert dialog.local_file_edit.isEnabled()

    dialog.atmosphere_model_combo.setCurrentIndex(1)  # exponential

    assert not dialog.space_weather_source_combo.isEnabled()
    assert not dialog.local_file_edit.isEnabled()
    assert not dialog.activity_level_combo.isEnabled()
    assert not dialog.activity_percentile_spin.isEnabled()

    dialog.atmosphere_model_combo.setCurrentIndex(0)  # back to nrlmsise00
    assert dialog.space_weather_source_combo.isEnabled()
    assert dialog.local_file_edit.isEnabled()  # source is still "local_file" from above
    assert dialog.activity_level_combo.isEnabled()


def test_activity_level_defaults_to_nominal_with_percentile_disabled(dialog):
    assert dialog._selected_activity_level() == "nominal"
    assert not dialog.activity_percentile_spin.isEnabled()
    assert dialog.to_space_weather().activity_level == "nominal"


def test_selecting_conservative_activity_level_enables_percentile_and_round_trips(dialog):
    dialog.activity_level_combo.setCurrentIndex(1)  # conservative
    assert dialog._selected_activity_level() == "conservative"
    assert dialog.activity_percentile_spin.isEnabled()

    dialog.activity_percentile_spin.setValue(97.7)
    sw = dialog.to_space_weather()
    assert sw.activity_level == "conservative"
    assert sw.activity_percentile == pytest.approx(97.7)


def test_loading_existing_conservative_config_checks_the_right_controls(qtbot):
    from missionstudio.schema.scenario import SpaceWeatherConfig

    d = _dialog(space_weather=SpaceWeatherConfig(activity_level="conservative", activity_percentile=90.0))
    qtbot.addWidget(d)
    assert d._selected_activity_level() == "conservative"
    assert d.activity_percentile_spin.isEnabled()
    assert d.activity_percentile_spin.value() == pytest.approx(90.0)


def test_srp_location_pointer_label_is_present(dialog):
    """Real user report: looked for solar radiation pressure in this
    dialog specifically and didn't find it -- this label is the fix (see
    this module's own docstring); regression guard that it doesn't
    silently disappear in some later refactor.
    """
    from PySide6.QtWidgets import QLabel

    labels = [w.text() for w in dialog.findChildren(QLabel)]
    assert any("solar radiation pressure" in text.lower() and "per spacecraft" in text.lower()
               for text in labels)
