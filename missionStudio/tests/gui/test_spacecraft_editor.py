"""Tests for gui.spacecraft_editor."""

import pytest

pytestmark = pytest.mark.requires_gui


def test_dialog_default_spacecraft(qtbot):
    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    sc = dialog.to_dataclass()
    assert sc.name == "sat-1"
    assert sc.orbit.type == "classical_elements"
    assert sc.inertia_kg_m2 == [10.0, 0.0, 0.0, 0.0, 10.0, 0.0, 0.0, 0.0, 10.0]


def test_dialog_every_tab_is_independently_scrollable(qtbot):
    """Regression test: QTabWidget sizes EVERY tab page to fit whichever
    page is tallest (its internal QStackedWidget's size hint is the max
    across ALL pages, not just the current one) -- without each tab
    wrapped in its own QScrollArea, the "Power / propulsion / link
    budget" tab (five stacked group boxes) forced every other tab,
    including "Orbit / mass", to render with a huge dead-space gap and
    made the whole dialog's natural size well over 1000px tall. Caught by
    actually rendering the dialog and looking at it, not from reading the
    layout code.
    """
    from PySide6.QtWidgets import QScrollArea

    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    for i in range(dialog.tabs.count()):
        assert isinstance(dialog.tabs.widget(i), QScrollArea), f"tab {i} ({dialog.tabs.tabText(i)!r}) isn't scrollable"


def test_long_description_labels_wrap_instead_of_blowing_up_dialog_width(qtbot):
    """Regression guard for a real bug, found via an actual user
    screenshot of gui.phasing_formation_dialog.PhasingFormationDialog
    (same copy-pasted top-description-QLabel shape, same missing
    word-wrap): the Vizard-model tab's own description QLabel had the
    identical problem. See that dialog's own test docstring for the
    full explanation of what goes wrong without setWordWrap(True).
    """
    from PySide6.QtWidgets import QLabel

    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.wait(10)

    description_labels = [w for w in dialog.findChildren(QLabel) if len(w.text()) > 100]
    assert description_labels, "expected to find at least one long description QLabel"
    assert all(w.wordWrap() for w in description_labels)


def test_dialog_natural_size_stays_reasonable(qtbot):
    """A loose upper bound, not a pixel-exact check: guards against the
    whole-dialog-height blowing up again (it briefly reached ~1450px
    tall before the per-tab QScrollArea fix -- see the test above) without
    being so tight that an unrelated, legitimate content change trips it.
    """
    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.wait(10)
    assert dialog.sizeHint().height() < 800


def test_dialog_edits_existing_config(qtbot):
    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog
    from missionstudio.schema.scenario import OrbitIC, SpacecraftConfig

    existing = SpacecraftConfig(
        name="sat-existing",
        orbit=OrbitIC(type="cartesian", position_km=[1.0, 2.0, 3.0], velocity_km_s=[4.0, 5.0, 6.0]),
        dry_mass_kg=250.0,
    )
    dialog = SpacecraftEditorDialog(config=existing)
    qtbot.addWidget(dialog)
    got = dialog.to_dataclass()
    assert got.name == "sat-existing"
    assert got.dry_mass_kg == 250.0
    assert got.orbit.position_km == [1.0, 2.0, 3.0]


def test_dialog_round_trips_sensors_actuators_and_fsw_mode(qtbot):
    """Regression test: editing an existing spacecraft used to silently
    DROP sensors/actuators/fsw_mode/fsw_params/control_params (the dialog
    built a brand new SpacecraftConfig without passing them through). This
    is exactly the round trip that bug broke.
    """
    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog
    from missionstudio.schema.scenario import ActuatorConfig, OrbitIC, SensorConfig, SpacecraftConfig

    existing = SpacecraftConfig(
        name="sat-with-fsw",
        orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0], velocity_km_s=[0, 7.5, 0]),
        sensors=[SensorConfig(kind="star_tracker", name="st-1", params={"noise_arcsec": 5.0})],
        actuators=[ActuatorConfig(kind="reaction_wheel", name="rw-1", params={"gsHat_B": [1, 0, 0]})],
        fsw_mode="hillPoint",
        fsw_params={"foo": "bar"},
        control_params={"K": 4.0, "P": 25.0},
    )
    dialog = SpacecraftEditorDialog(config=existing)
    qtbot.addWidget(dialog)
    got = dialog.to_dataclass()

    assert len(got.sensors) == 1
    assert got.sensors[0].kind == "star_tracker"
    assert got.sensors[0].params == {"noise_arcsec": 5.0}
    assert len(got.actuators) == 1
    assert got.actuators[0].params == {"gsHat_B": [1, 0, 0]}
    assert got.fsw_mode == "hillPoint"
    assert got.fsw_params == {"foo": "bar"}
    assert got.control_params == {"K": 4.0, "P": 25.0}


def test_dialog_defaults_fsw_mode_to_none(qtbot):
    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    sc = dialog.to_dataclass()
    assert sc.fsw_mode is None
    assert sc.sensors == []
    assert sc.actuators == []


def test_dialog_catches_missing_locationpointing_target_immediately(qtbot):
    """Regression test: locationPointing's required
    fsw_params['target_ground_station'] used to only be caught deep inside
    engine.fsw at Run Simulation time (an FswError with no connection back
    to this dialog), or not at all if the scenario was never actually run.
    This dialog should catch it itself, right where the params box is.
    """
    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    index = dialog.fsw_mode_combo.findData("locationPointing")
    dialog.fsw_mode_combo.setCurrentIndex(index)
    dialog.fsw_params_edit.setPlainText("{}")  # no target_ground_station

    with pytest.raises(ValueError, match="target_ground_station"):
        dialog.to_dataclass()


def test_dialog_fsw_reset_template_fills_working_example(qtbot):
    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    index = dialog.fsw_mode_combo.findData("locationPointing")
    dialog.fsw_mode_combo.setCurrentIndex(index)
    dialog._on_fsw_reset_template()

    sc = dialog.to_dataclass()
    assert "target_ground_station" in sc.fsw_params


def test_dialog_fsw_hint_updates_with_mode(qtbot):
    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    assert "no attitude control" in dialog.fsw_hint_label.text().lower()

    index = dialog.fsw_mode_combo.findData("locationPointing")
    dialog.fsw_mode_combo.setCurrentIndex(index)
    assert "target_ground_station" in dialog.fsw_hint_label.text()


def test_dialog_power_and_rf_link_default_to_none(qtbot):
    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    assert not dialog.power_group.isChecked()
    assert not dialog.rf_link_group.isChecked()
    sc = dialog.to_dataclass()
    assert sc.power is None
    assert sc.rf_link is None


def test_dialog_builds_power_config_when_group_checked(qtbot):
    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    dialog.power_group.setChecked(True)
    dialog.panel_area_m2.setValue(2.5)
    dialog.panel_efficiency.setValue(0.3)
    dialog.bus_idle_power_w.setValue(30.0)
    dialog.battery_capacity_wh.setValue(200.0)
    dialog.battery_initial_soc.setValue(0.8)

    sc = dialog.to_dataclass()
    assert sc.power is not None
    assert sc.power.panel_area_m2 == 2.5
    assert sc.power.panel_efficiency == 0.3
    assert sc.power.bus_idle_power_w == 30.0
    assert sc.power.battery_capacity_wh == 200.0
    assert sc.power.battery_initial_soc == 0.8
    assert sc.rf_link is None  # unrelated group, still unchecked


def test_dialog_builds_rf_link_config_when_group_checked(qtbot):
    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    dialog.rf_link_group.setChecked(True)
    dialog.tx_power_w.setValue(20.0)
    dialog.frequency_ghz.setValue(2.2)
    dialog.data_rate_mbps.setValue(0.5)
    dialog.tx_antenna_gain_dbi.setValue(8.0)
    dialog.rf_implementation_loss_db.setValue(3.0)
    dialog.required_ebno_db.setValue(5.0)

    sc = dialog.to_dataclass()
    assert sc.rf_link is not None
    assert sc.rf_link.tx_power_w == 20.0
    assert sc.rf_link.frequency_hz == pytest.approx(2.2e9)
    assert sc.rf_link.data_rate_bps == pytest.approx(0.5e6)
    assert sc.rf_link.tx_antenna_gain_dbi == 8.0
    assert sc.rf_link.implementation_loss_db == 3.0
    assert sc.rf_link.required_ebno_db == 5.0
    assert sc.power is None  # unrelated group, still unchecked


def test_dialog_round_trips_power_and_rf_link(qtbot):
    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog
    from missionstudio.schema.scenario import OrbitIC, PowerConfig, RFLinkConfig, SpacecraftConfig

    existing = SpacecraftConfig(
        name="sat-power",
        orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0], velocity_km_s=[0, 7.5, 0]),
        power=PowerConfig(panel_area_m2=1.5, panel_efficiency=0.28, panel_normal_b=[1.0, 0.0, 0.0],
                           bus_idle_power_w=20.0, battery_capacity_wh=150.0, battery_initial_soc=0.95),
        rf_link=RFLinkConfig(tx_power_w=12.0, frequency_hz=8.4e9, data_rate_bps=2.0e6),
    )
    dialog = SpacecraftEditorDialog(config=existing)
    qtbot.addWidget(dialog)

    assert dialog.power_group.isChecked()
    assert dialog.rf_link_group.isChecked()

    got = dialog.to_dataclass()
    assert got.power == existing.power
    assert got.rf_link == existing.rf_link


def test_dialog_station_keeping_defaults_to_none(qtbot):
    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    assert not dialog.station_keeping_group.isChecked()
    sc = dialog.to_dataclass()
    assert sc.station_keeping is None


def test_dialog_builds_station_keeping_config_when_group_checked(qtbot):
    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    dialog.station_keeping_group.setChecked(True)
    dialog.sk_target_altitude_km.setValue(600.0)
    dialog.sk_deadband_km.setValue(2.0)
    dialog.sk_thrust_n.setValue(0.02)
    dialog.sk_isp_s.setValue(1600.0)
    dialog.sk_propellant_kg.setValue(3.5)
    dialog.sk_eclipse_sunlit_threshold.setValue(0.95)

    sc = dialog.to_dataclass()
    assert sc.station_keeping is not None
    assert sc.station_keeping.target_altitude_km == 600.0
    assert sc.station_keeping.deadband_km == 2.0
    assert sc.station_keeping.thrust_n == 0.02
    assert sc.station_keeping.isp_s == 1600.0
    assert sc.station_keeping.propellant_kg == 3.5
    assert sc.station_keeping.eclipse_sunlit_threshold == 0.95


def test_dialog_round_trips_station_keeping(qtbot):
    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog
    from missionstudio.schema.scenario import OrbitIC, SpacecraftConfig, StationKeepingConfig

    existing = SpacecraftConfig(
        name="sat-sk",
        orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0], velocity_km_s=[0, 7.5, 0]),
        station_keeping=StationKeepingConfig(target_altitude_km=550.0, deadband_km=1.5, thrust_n=0.015,
                                              isp_s=1550.0, propellant_kg=2.5),
    )
    dialog = SpacecraftEditorDialog(config=existing)
    qtbot.addWidget(dialog)

    assert dialog.station_keeping_group.isChecked()

    got = dialog.to_dataclass()
    assert got.station_keeping == existing.station_keeping


def test_dialog_phasing_keeping_defaults_to_none(qtbot):
    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    assert not dialog.phasing_keeping_group.isChecked()
    sc = dialog.to_dataclass()
    assert sc.phasing_keeping is None


def test_dialog_phasing_keeping_chief_combo_lists_other_spacecraft(qtbot):
    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog(other_spacecraft_names=["chief", "follower-2"])
    qtbot.addWidget(dialog)
    dialog.phasing_keeping_group.setChecked(True)  # a checkable QGroupBox disables its children while unchecked
    assert dialog.pk_chief_combo.isEnabled()
    names = {dialog.pk_chief_combo.itemData(i) for i in range(dialog.pk_chief_combo.count())}
    assert names == {"chief", "follower-2"}


def test_dialog_phasing_keeping_disabled_combo_with_no_other_spacecraft(qtbot):
    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    dialog.phasing_keeping_group.setChecked(True)  # isolate this widget's OWN disabled state from the group's
    assert not dialog.pk_chief_combo.isEnabled()
    assert dialog.pk_chief_combo.currentData() is None


def test_dialog_phasing_keeping_requires_a_selectable_chief(qtbot):
    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog
    from missionstudio.schema.scenario import ScenarioValidationError

    dialog = SpacecraftEditorDialog()  # no other_spacecraft_names -- combo disabled
    qtbot.addWidget(dialog)
    dialog.station_keeping_group.setChecked(True)
    dialog.phasing_keeping_group.setChecked(True)
    with pytest.raises(ScenarioValidationError, match="no chief spacecraft is selectable"):
        dialog.to_dataclass()


def test_dialog_builds_phasing_keeping_config_when_group_checked(qtbot):
    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog(other_spacecraft_names=["chief"])
    qtbot.addWidget(dialog)
    dialog.station_keeping_group.setChecked(True)  # phasing_keeping requires this
    dialog.phasing_keeping_group.setChecked(True)
    dialog.pk_target_separation_edit.setText("1000, 500, 100")
    dialog.pk_reconfiguration_interval_days.setValue(60.0)
    dialog.pk_tolerance_fraction.setValue(0.2)
    dialog.pk_restore_tolerance_fraction.setValue(0.05)
    dialog.pk_correction_window_days.setValue(14.0)
    dialog.pk_max_drift_days.setValue(45.0)
    dialog.pk_max_delta_sma_km.setValue(2.0)

    sc = dialog.to_dataclass()
    assert sc.phasing_keeping is not None
    assert sc.phasing_keeping.chief_spacecraft == "chief"
    assert sc.phasing_keeping.target_separation_km == [1000.0, 500.0, 100.0]
    assert sc.phasing_keeping.reconfiguration_interval_days == 60.0
    assert sc.phasing_keeping.tolerance_fraction == 0.2
    assert sc.phasing_keeping.restore_tolerance_fraction == 0.05
    assert sc.phasing_keeping.correction_window_days == 14.0
    assert sc.phasing_keeping.max_drift_days == 45.0
    assert sc.phasing_keeping.max_delta_semi_major_axis_km == 2.0


def test_dialog_phasing_keeping_rejects_malformed_separation_list(qtbot):
    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog
    from missionstudio.schema.scenario import ScenarioValidationError

    dialog = SpacecraftEditorDialog(other_spacecraft_names=["chief"])
    qtbot.addWidget(dialog)
    dialog.station_keeping_group.setChecked(True)
    dialog.phasing_keeping_group.setChecked(True)
    dialog.pk_target_separation_edit.setText("not, a, number")
    with pytest.raises(ScenarioValidationError, match="comma-separated numbers"):
        dialog.to_dataclass()


def test_dialog_stale_chief_spacecraft_is_preserved_not_silently_swapped(qtbot):
    """Regression test: pk0.chief_spacecraft naming a spacecraft that no
    longer exists in other_spacecraft_names (e.g. renamed/removed since
    this config was saved) used to be silently dropped -- findData()
    returned -1, nothing set the combo's index, and it stayed on
    whatever was first, re-targeting phasing_keeping at the WRONG chief
    with no indication anything had changed. It must instead be
    round-tripped as-is (surfaced as its own combo entry) so
    to_dataclass() either preserves it or a later validate() call catches
    it as a real, visible error -- never a silent swap.
    """
    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog
    from missionstudio.schema.scenario import OrbitIC, PhasingKeepingConfig, SpacecraftConfig, StationKeepingConfig

    existing = SpacecraftConfig(
        name="sat-follower",
        orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0], velocity_km_s=[0, 7.5, 0]),
        station_keeping=StationKeepingConfig(target_altitude_km=550.0, deadband_km=1.5, thrust_n=0.015,
                                              isp_s=1550.0, propellant_kg=2.5),
        phasing_keeping=PhasingKeepingConfig(chief_spacecraft="renamed-chief", target_separation_km=[250.0]),
    )
    # "renamed-chief" is NOT in other_spacecraft_names -- simulates the
    # chief having been renamed/removed after this config was saved.
    dialog = SpacecraftEditorDialog(config=existing, other_spacecraft_names=["some-other-sat"])
    qtbot.addWidget(dialog)

    assert dialog.pk_chief_combo.currentData() == "renamed-chief"
    got = dialog.to_dataclass()
    assert got.phasing_keeping.chief_spacecraft == "renamed-chief"


def test_dialog_round_trips_drag_and_srp_fields(qtbot):
    """Regression test: to_dataclass() used to build a brand new
    SpacecraftConfig without passing enable_drag/drag_coeff/drag_area_m2/
    enable_srp/srp_coeff/srp_area_m2 at all (there was no editor for them
    at the time), silently resetting them to SpacecraftConfig's defaults
    every time an existing spacecraft with these set was edited and
    re-saved. There is now a real editor (drag_srp_group) -- this checks
    both that it round-trips an existing config's values AND (below) that
    editing it actually changes what to_dataclass() returns.
    """
    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog
    from missionstudio.schema.scenario import OrbitIC, SpacecraftConfig

    existing = SpacecraftConfig(
        name="sat-drag",
        orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0], velocity_km_s=[0, 7.5, 0]),
        enable_drag=True,
        drag_coeff=2.5,
        drag_area_m2=3.3,
        enable_srp=True,
        srp_coeff=1.5,
        srp_area_m2=4.4,
    )
    dialog = SpacecraftEditorDialog(config=existing)
    qtbot.addWidget(dialog)

    assert dialog.enable_drag_check.isChecked()
    assert dialog.drag_coeff.value() == 2.5
    assert dialog.drag_area_m2.value() == 3.3
    assert dialog.enable_srp_check.isChecked()
    assert dialog.srp_coeff.value() == 1.5
    assert dialog.srp_area_m2.value() == 4.4

    got = dialog.to_dataclass()
    assert got.enable_drag is True
    assert got.drag_coeff == 2.5
    assert got.drag_area_m2 == 3.3
    assert got.enable_srp is True
    assert got.srp_coeff == 1.5
    assert got.srp_area_m2 == 4.4


def test_dialog_drag_srp_editor_actually_edits(qtbot):
    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    assert not dialog.enable_drag_check.isChecked()  # default off

    dialog.enable_drag_check.setChecked(True)
    dialog.drag_coeff.setValue(2.7)
    dialog.drag_area_m2.setValue(0.05)
    dialog.enable_srp_check.setChecked(True)
    dialog.srp_coeff.setValue(1.4)
    dialog.srp_area_m2.setValue(0.05)

    sc = dialog.to_dataclass()
    assert sc.enable_drag is True
    assert sc.drag_coeff == 2.7
    assert sc.drag_area_m2 == 0.05
    assert sc.enable_srp is True
    assert sc.srp_coeff == 1.4
    assert sc.srp_area_m2 == 0.05


def test_dialog_defaults_to_no_constant_thrust(qtbot):
    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    assert not dialog.constant_thrust_group.isChecked()
    sc = dialog.to_dataclass()
    assert sc.constant_thrust is None


def test_dialog_builds_constant_thrust_when_group_checked(qtbot):
    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    dialog.constant_thrust_group.setChecked(True)
    dialog.ct_frame_combo.setCurrentText("RTN")
    dialog.ct_dir_x.setValue(0.0)
    dialog.ct_dir_y.setValue(1.0)
    dialog.ct_dir_z.setValue(0.0)
    dialog.ct_thrust_n.setValue(0.05)
    dialog.ct_isp_s.setValue(2000.0)
    dialog.ct_propellant_kg.setValue(1.5)

    sc = dialog.to_dataclass()
    assert sc.constant_thrust is not None
    assert sc.constant_thrust.frame == "RTN"
    assert sc.constant_thrust.direction == [0.0, 1.0, 0.0]
    assert sc.constant_thrust.thrust_n == 0.05
    assert sc.constant_thrust.isp_s == 2000.0
    assert sc.constant_thrust.propellant_kg == 1.5


def test_dialog_round_trips_constant_thrust(qtbot):
    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog
    from missionstudio.schema.scenario import ConstantThrustConfig, OrbitIC, SpacecraftConfig

    existing = SpacecraftConfig(
        name="sat-thrust",
        orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0], velocity_km_s=[0, 7.5, 0]),
        constant_thrust=ConstantThrustConfig(frame="VNB", direction=[1.0, 0.0, 0.0], thrust_n=0.02,
                                              isp_s=1800.0, propellant_kg=3.0),
    )
    dialog = SpacecraftEditorDialog(config=existing)
    qtbot.addWidget(dialog)
    assert dialog.constant_thrust_group.isChecked()
    assert dialog.ct_frame_combo.currentText() == "VNB"

    got = dialog.to_dataclass()
    assert got.constant_thrust == existing.constant_thrust


def test_dialog_orbit_only_mode_hides_attitude_tabs_and_power(qtbot):
    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog(simulation_mode="orbit_only")
    qtbot.addWidget(dialog)
    assert not dialog.tabs.isTabVisible(dialog._sensors_tab_index)
    assert not dialog.tabs.isTabVisible(dialog._fsw_tab_index)
    # isHidden() (not isVisible()): tracks whether THIS widget was
    # explicitly hidden, independent of whether the dialog itself was ever
    # shown (it isn't, in this test) -- isVisible() would be False either
    # way since the dialog is never .show()n.
    assert dialog.power_group.isHidden()


def test_dialog_orbit_only_mode_force_clears_attitude_fields(qtbot):
    """Even if a spacecraft being edited already has sensors/actuators/
    fsw_mode/power set (e.g. the scenario's mode was just switched to
    orbit_only without yet touching this spacecraft), the dialog must not
    let those hidden, stale values silently pass through to_dataclass().
    """
    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog
    from missionstudio.schema.scenario import OrbitIC, PowerConfig, SensorConfig, SpacecraftConfig

    existing = SpacecraftConfig(
        name="sat-orbit-only",
        orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0], velocity_km_s=[0, 7.5, 0]),
        sensors=[SensorConfig(kind="imu", name="imu-1")],
        fsw_mode="hillPoint",
        power=PowerConfig(panel_area_m2=1.0, panel_efficiency=0.29),
    )
    dialog = SpacecraftEditorDialog(config=existing, simulation_mode="orbit_only")
    qtbot.addWidget(dialog)

    sc = dialog.to_dataclass()
    assert sc.sensors == []
    assert sc.actuators == []
    assert sc.fsw_mode is None
    assert sc.power is None
    sc.validate()  # must not raise


def test_dialog_full_attitude_mode_keeps_tabs_visible(qtbot):
    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog(simulation_mode="full_attitude")
    qtbot.addWidget(dialog)
    assert dialog.tabs.isTabVisible(dialog._sensors_tab_index)
    assert dialog.tabs.isTabVisible(dialog._fsw_tab_index)
    assert not dialog.power_group.isHidden()


def test_dialog_defaults_to_no_vizard_model(qtbot):
    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    assert not dialog.viz_model_group.isChecked()
    sc = dialog.to_dataclass()
    assert sc.vizard_model_path is None
    assert sc.vizard_model_offset_m == [0.0, 0.0, 0.0]
    assert sc.vizard_model_rotation_deg == [0.0, 0.0, 0.0]
    assert sc.vizard_model_scale == [1.0, 1.0, 1.0]


def test_dialog_builds_vizard_model_when_group_checked(qtbot):
    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    dialog.viz_model_group.setChecked(True)
    dialog.viz_model_path_edit.setText("/tmp/my_bus.obj")
    dialog.viz_offset_x.setValue(0.1)
    dialog.viz_offset_y.setValue(-0.2)
    dialog.viz_offset_z.setValue(0.3)
    dialog.viz_rotation_z.setValue(90.0)
    dialog.viz_scale_x.setValue(2.0)
    dialog.viz_scale_y.setValue(2.0)
    dialog.viz_scale_z.setValue(2.0)

    sc = dialog.to_dataclass()
    assert sc.vizard_model_path == "/tmp/my_bus.obj"
    assert sc.vizard_model_offset_m == [0.1, -0.2, 0.3]
    assert sc.vizard_model_rotation_deg == [90.0, 0.0, 0.0]
    assert sc.vizard_model_scale == [2.0, 2.0, 2.0]


def test_dialog_vizard_model_checked_but_blank_path_is_none(qtbot):
    """Checking the group box without filling in a path shouldn't produce
    an unvalidatable half-configured model -- it's simply treated as "no
    custom model", same as leaving the group box unchecked.
    """
    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    dialog.viz_model_group.setChecked(True)

    sc = dialog.to_dataclass()
    assert sc.vizard_model_path is None


def test_dialog_round_trips_vizard_model(qtbot):
    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog
    from missionstudio.schema.scenario import OrbitIC, SpacecraftConfig

    existing = SpacecraftConfig(
        name="sat-with-model",
        orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0], velocity_km_s=[0, 7.5, 0]),
        vizard_model_path="CYLINDER",
        vizard_model_offset_m=[0.0, 0.0, -0.5],
        vizard_model_rotation_deg=[0.0, 45.0, 0.0],
        vizard_model_scale=[1.5, 1.5, 3.0],
    )
    dialog = SpacecraftEditorDialog(config=existing)
    qtbot.addWidget(dialog)
    assert dialog.viz_model_group.isChecked()
    assert dialog.viz_model_path_edit.text() == "CYLINDER"

    got = dialog.to_dataclass()
    assert got.vizard_model_path == "CYLINDER"
    assert got.vizard_model_offset_m == [0.0, 0.0, -0.5]
    assert got.vizard_model_rotation_deg == [0.0, 45.0, 0.0]
    assert got.vizard_model_scale == [1.5, 1.5, 3.0]


def test_dialog_round_trips_phasing_keeping(qtbot):
    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog
    from missionstudio.schema.scenario import (
        OrbitIC,
        PhasingKeepingConfig,
        SpacecraftConfig,
        StationKeepingConfig,
    )

    existing = SpacecraftConfig(
        name="sat-follower",
        orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0], velocity_km_s=[0, 7.5, 0]),
        station_keeping=StationKeepingConfig(target_altitude_km=550.0, deadband_km=1.5, thrust_n=0.015,
                                              isp_s=1550.0, propellant_kg=2.5),
        phasing_keeping=PhasingKeepingConfig(chief_spacecraft="chief", target_separation_km=[250.0, 100.0],
                                              reconfiguration_interval_days=45.0),
    )
    dialog = SpacecraftEditorDialog(config=existing, other_spacecraft_names=["chief"])
    qtbot.addWidget(dialog)

    assert dialog.phasing_keeping_group.isChecked()
    assert dialog.pk_chief_combo.currentData() == "chief"
    assert dialog.pk_target_separation_edit.text() == "250, 100"

    got = dialog.to_dataclass()
    assert got.phasing_keeping == existing.phasing_keeping


def test_dialog_rejects_invalid_fsw_params_json(qtbot):
    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    dialog.fsw_params_edit.setPlainText("{not valid json")
    with pytest.raises(ValueError, match="not valid JSON"):
        dialog.to_dataclass()


def test_dialog_rejects_empty_name(qtbot):
    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog
    from missionstudio.schema.scenario import ScenarioValidationError

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    dialog.name_edit.setText("")
    with pytest.raises(ScenarioValidationError, match="name must not be empty"):
        dialog.to_dataclass()


def test_dialog_name_field_shows_inline_error_while_empty(qtbot):
    """gui.feedback's inline-validation primitive, live as the user
    types -- not just the to_dataclass()-time exception the test above
    already covers.
    """
    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)

    dialog.name_edit.setText("")
    assert dialog.name_edit.property("state") == "error"

    dialog.name_edit.setText("sat-42")
    assert dialog.name_edit.property("state") != "error"


def test_dialog_name_field_shows_inline_error_on_duplicate(qtbot):
    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog(other_spacecraft_names=["sat-1", "sat-2"])
    qtbot.addWidget(dialog)

    dialog.name_edit.setText("sat-2")
    assert dialog.name_edit.property("state") == "error"
    assert "sat-2" in dialog.name_edit.toolTip()

    dialog.name_edit.setText("sat-3")
    assert dialog.name_edit.property("state") != "error"


def test_dialog_accept_blocks_and_keeps_dialog_open_on_empty_name(qtbot):
    """Regression guard for a real data-loss UX bug: _on_accept() used to
    call self.accept() unconditionally, so a duplicate/empty name wasn't
    caught until the (already-closed) dialog's caller checked afterward
    -- silently discarding every edit the user just made. _on_accept()
    must now refuse to close the dialog itself.
    """
    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    dialog.name_edit.setText("")

    dialog._on_accept()

    assert dialog.result() == 0  # neither Accepted nor Rejected -- still open
    assert dialog.name_edit.property("state") == "error"


def test_dialog_accept_blocks_on_duplicate_name(qtbot):
    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog(other_spacecraft_names=["sat-1"])
    qtbot.addWidget(dialog)
    dialog.name_edit.setText("sat-1")

    dialog._on_accept()

    assert dialog.result() == 0
    assert dialog.name_edit.property("state") == "error"


def test_list_widget_from_list_to_list_round_trip(qtbot):
    from missionstudio.gui.spacecraft_editor import SpacecraftListWidget
    from missionstudio.schema.scenario import OrbitIC, SpacecraftConfig

    lw = SpacecraftListWidget()
    qtbot.addWidget(lw)
    configs = [
        SpacecraftConfig(name="a", orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0], velocity_km_s=[0, 7.5, 0])),
        SpacecraftConfig(name="b", orbit=OrbitIC(type="cartesian", position_km=[8000, 0, 0], velocity_km_s=[0, 7.0, 0])),
    ]
    lw.from_list(configs)
    assert lw.list_widget.count() == 2
    assert [c.name for c in lw.to_list()] == ["a", "b"]


def test_list_widget_add_via_dialog(qtbot, monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDialog

    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog, SpacecraftListWidget

    lw = SpacecraftListWidget()
    qtbot.addWidget(lw)

    def fake_exec(self):
        self.name_edit.setText("added-sat")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(SpacecraftEditorDialog, "exec", fake_exec)
    changed_count = []
    lw.changed.connect(lambda: changed_count.append(1))

    qtbot.mouseClick(lw.add_button, Qt.MouseButton.LeftButton)

    assert lw.list_widget.count() == 1
    assert lw.to_list()[0].name == "added-sat"
    assert changed_count == [1]
    assert lw.list_widget.currentRow() == 0  # the new spacecraft is selected, not left unselected


def test_list_widget_add_and_remove_show_a_toast(qtbot, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog, SpacecraftListWidget

    lw = SpacecraftListWidget()
    qtbot.addWidget(lw)

    def fake_exec(self):
        self.name_edit.setText("toasted-sat")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(SpacecraftEditorDialog, "exec", fake_exec)
    lw._on_add()

    toasts = getattr(lw.window(), "_missionstudio_active_toasts", [])
    assert any("toasted-sat" in t.text() for t in toasts)

    lw.list_widget.setCurrentRow(0)
    lw._on_remove()

    toasts = getattr(lw.window(), "_missionstudio_active_toasts", [])
    assert any("toasted-sat" in t.text() and "Removed" in t.text() for t in toasts)


def test_list_widget_new_from_template(qtbot, monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDialog

    from missionstudio.engine.spacecraft_templates import SPACECRAFT_TEMPLATES
    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog, SpacecraftListWidget
    from missionstudio.gui.spacecraft_template_dialog import SpacecraftTemplateDialog

    lw = SpacecraftListWidget()
    qtbot.addWidget(lw)

    stabilized = next(t for t in SPACECRAFT_TEMPLATES if "stabilized" in t.name.lower() and "3u" in t.name.lower())

    def fake_picker_exec(self):
        return QDialog.DialogCode.Accepted

    def fake_picker_selected_template(self):
        return stabilized

    def fake_editor_exec(self):
        return QDialog.DialogCode.Accepted  # accept whatever the template pre-filled, unchanged

    monkeypatch.setattr(SpacecraftTemplateDialog, "exec", fake_picker_exec)
    monkeypatch.setattr(SpacecraftTemplateDialog, "selected_template", fake_picker_selected_template)
    monkeypatch.setattr(SpacecraftEditorDialog, "exec", fake_editor_exec)
    changed_count = []
    lw.changed.connect(lambda: changed_count.append(1))

    qtbot.mouseClick(lw.new_from_template_button, Qt.MouseButton.LeftButton)

    assert lw.list_widget.count() == 1
    added = lw.to_list()[0]
    assert len(added.actuators) == 3
    assert added.fsw_mode == "sunSafePoint"
    assert changed_count == [1]


def test_list_widget_new_from_template_dedupes_name_on_collision(qtbot, monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDialog

    from missionstudio.engine.spacecraft_templates import SPACECRAFT_TEMPLATES
    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog, SpacecraftListWidget
    from missionstudio.gui.spacecraft_template_dialog import SpacecraftTemplateDialog
    from missionstudio.schema.scenario import OrbitIC, SpacecraftConfig

    lw = SpacecraftListWidget()
    qtbot.addWidget(lw)
    lw.from_list([SpacecraftConfig(name="template",
                                    orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0],
                                                  velocity_km_s=[0, 7.5, 0]))])

    passive = next(t for t in SPACECRAFT_TEMPLATES if "passive" in t.name.lower())

    monkeypatch.setattr(SpacecraftTemplateDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(SpacecraftTemplateDialog, "selected_template", lambda self: passive)
    captured_names = []

    def fake_editor_exec(self):
        captured_names.append(self.name_edit.text())
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(SpacecraftEditorDialog, "exec", fake_editor_exec)

    qtbot.mouseClick(lw.new_from_template_button, Qt.MouseButton.LeftButton)

    assert lw.list_widget.count() == 2
    assert captured_names == ["template-2"]  # "template" already taken by the pre-existing spacecraft


def test_list_widget_new_from_template_cancel_does_nothing(qtbot, monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDialog

    from missionstudio.gui.spacecraft_editor import SpacecraftListWidget
    from missionstudio.gui.spacecraft_template_dialog import SpacecraftTemplateDialog

    lw = SpacecraftListWidget()
    qtbot.addWidget(lw)
    monkeypatch.setattr(SpacecraftTemplateDialog, "exec", lambda self: QDialog.DialogCode.Rejected)

    qtbot.mouseClick(lw.new_from_template_button, Qt.MouseButton.LeftButton)

    assert lw.list_widget.count() == 0


def test_list_widget_edit_and_remove(qtbot, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog, SpacecraftListWidget
    from missionstudio.schema.scenario import OrbitIC, SpacecraftConfig

    lw = SpacecraftListWidget()
    qtbot.addWidget(lw)
    lw.from_list([SpacecraftConfig(name="orig",
                                    orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0], velocity_km_s=[0, 7.5, 0]))])
    lw.list_widget.setCurrentRow(0)

    def fake_exec(self):
        self.name_edit.setText("renamed")
        self.dry_mass_kg.setValue(321.0)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(SpacecraftEditorDialog, "exec", fake_exec)
    lw._on_edit()
    assert lw.to_list()[0].name == "renamed"
    assert lw.to_list()[0].dry_mass_kg == 321.0

    lw.list_widget.setCurrentRow(0)
    lw._on_remove()
    assert lw.to_list() == []


def test_list_widget_rejects_duplicate_name_on_add(qtbot, monkeypatch):
    from PySide6.QtWidgets import QDialog, QMessageBox

    from missionstudio.gui.spacecraft_editor import SpacecraftEditorDialog, SpacecraftListWidget
    from missionstudio.schema.scenario import OrbitIC, SpacecraftConfig

    lw = SpacecraftListWidget()
    qtbot.addWidget(lw)
    lw.from_list([SpacecraftConfig(name="dup",
                                    orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0], velocity_km_s=[0, 7.5, 0]))])

    def fake_exec(self):
        self.name_edit.setText("dup")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(SpacecraftEditorDialog, "exec", fake_exec)
    critical_calls = []
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: critical_calls.append(a)))

    lw._on_add()
    assert len(lw.to_list()) == 1  # not added
    assert len(critical_calls) == 1


def test_list_widget_generate_constellation_appends_generated_spacecraft(qtbot, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from missionstudio.gui.constellation_dialog import WalkerConstellationDialog
    from missionstudio.gui.spacecraft_editor import SpacecraftListWidget
    from missionstudio.schema.scenario import OrbitIC, SpacecraftConfig

    lw = SpacecraftListWidget()
    qtbot.addWidget(lw)
    lw.from_list([SpacecraftConfig(
        name="template-sat", dry_mass_kg=42.0,
        orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0], velocity_km_s=[0, 7.5, 0]),
    )])

    def fake_exec(self):
        self.total_satellites.setValue(4)
        self.num_planes.setValue(2)
        self.phasing_factor.setValue(0)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(WalkerConstellationDialog, "exec", fake_exec)
    changed_calls = []
    lw.changed.connect(lambda: changed_calls.append(1))

    lw._on_generate_constellation()

    configs = lw.to_list()
    assert len(configs) == 1 + 4  # original template + 4 generated
    generated = [c for c in configs if c.name != "template-sat"]
    assert len(generated) == 4
    assert all(c.dry_mass_kg == 42.0 for c in generated)  # cloned from the template
    assert len(changed_calls) == 1
    toasts = getattr(lw.window(), "_missionstudio_active_toasts", [])
    assert any("4" in t.text() and "constellation" in t.text() for t in toasts)


def test_list_widget_generate_constellation_uses_default_template_when_list_empty(qtbot, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from missionstudio.gui.constellation_dialog import WalkerConstellationDialog
    from missionstudio.gui.spacecraft_editor import SpacecraftListWidget

    lw = SpacecraftListWidget()
    qtbot.addWidget(lw)

    def fake_exec(self):
        self.total_satellites.setValue(2)
        self.num_planes.setValue(1)
        self.phasing_factor.setValue(0)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(WalkerConstellationDialog, "exec", fake_exec)
    lw._on_generate_constellation()
    assert len(lw.to_list()) == 2


def test_list_widget_generate_constellation_reports_name_collision(qtbot, monkeypatch):
    from PySide6.QtWidgets import QDialog, QMessageBox

    from missionstudio.gui.constellation_dialog import WalkerConstellationDialog
    from missionstudio.gui.spacecraft_editor import SpacecraftListWidget
    from missionstudio.schema.scenario import OrbitIC, SpacecraftConfig

    lw = SpacecraftListWidget()
    qtbot.addWidget(lw)
    # This name collides with the first satellite generate_walker_constellation
    # would produce for a 1-satellite/1-plane request with the default prefix.
    lw.from_list([SpacecraftConfig(
        name="sat-01-01",
        orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0], velocity_km_s=[0, 7.5, 0]),
    )])

    def fake_exec(self):
        self.total_satellites.setValue(1)
        self.num_planes.setValue(1)
        self.phasing_factor.setValue(0)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(WalkerConstellationDialog, "exec", fake_exec)
    critical_calls = []
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: critical_calls.append(a)))

    lw._on_generate_constellation()
    assert len(lw.to_list()) == 1  # nothing added
    assert len(critical_calls) == 1


def test_list_widget_generate_constellation_cancel_does_nothing(qtbot, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from missionstudio.gui.constellation_dialog import WalkerConstellationDialog
    from missionstudio.gui.spacecraft_editor import SpacecraftListWidget

    lw = SpacecraftListWidget()
    qtbot.addWidget(lw)
    monkeypatch.setattr(WalkerConstellationDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    lw._on_generate_constellation()
    assert lw.to_list() == []


def test_list_widget_uses_central_body_provider(qtbot, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from missionstudio.gui.constellation_dialog import WalkerConstellationDialog
    from missionstudio.gui.spacecraft_editor import SpacecraftListWidget

    lw = SpacecraftListWidget()
    qtbot.addWidget(lw)
    lw.set_central_body_provider(lambda: "mars")

    captured = {}

    def fake_exec(self):
        captured["central_body"] = self.to_request().central_body
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(WalkerConstellationDialog, "exec", fake_exec)
    lw._on_generate_constellation()
    assert captured["central_body"] == "mars"


@pytest.mark.requires_basilisk
def test_list_widget_generate_phasing_formation_appends_follower(qtbot, monkeypatch):
    """generate_phasing_follower() needs a real Basilisk build (see
    engine.formation's own docstring) -- unlike the Walker-constellation
    tests above, this one is requires_basilisk in addition to this file's
    own requires_gui.
    """
    from PySide6.QtWidgets import QDialog

    from missionstudio.gui.phasing_formation_dialog import PhasingFormationDialog
    from missionstudio.gui.spacecraft_editor import SpacecraftListWidget
    from missionstudio.schema.scenario import OrbitIC, SpacecraftConfig

    lw = SpacecraftListWidget()
    qtbot.addWidget(lw)
    lw.from_list([SpacecraftConfig(
        name="chief-1", dry_mass_kg=100.0,
        orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6928.0, eccentricity=0.001,
                      inclination_deg=45.0, raan_deg=0.0, arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
    )])

    def fake_exec(self):
        self.chief_combo.setCurrentIndex(0)
        self.follower_name_edit.setText("follower-1")
        self.along_track_km.setValue(50.0)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(PhasingFormationDialog, "exec", fake_exec)
    changed_calls = []
    lw.changed.connect(lambda: changed_calls.append(1))

    lw._on_generate_phasing_formation()

    configs = lw.to_list()
    assert [c.name for c in configs] == ["chief-1", "follower-1"]
    follower = configs[1]
    assert follower.phasing_keeping.chief_spacecraft == "chief-1"
    assert follower.phasing_keeping.target_separation_km == [50.0]
    assert follower.station_keeping is not None
    assert follower.dry_mass_kg == 100.0  # cloned from the chief (also the default template)
    assert len(changed_calls) == 1
    toasts = getattr(lw.window(), "_missionstudio_active_toasts", [])
    assert any("follower-1" in t.text() for t in toasts)


@pytest.mark.requires_basilisk
def test_list_widget_generate_phasing_formation_reports_name_collision(qtbot, monkeypatch):
    from PySide6.QtWidgets import QDialog, QMessageBox

    from missionstudio.gui.phasing_formation_dialog import PhasingFormationDialog
    from missionstudio.gui.spacecraft_editor import SpacecraftListWidget
    from missionstudio.schema.scenario import OrbitIC, SpacecraftConfig

    lw = SpacecraftListWidget()
    qtbot.addWidget(lw)
    lw.from_list([
        SpacecraftConfig(
            name="chief-1",
            orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6928.0, eccentricity=0.001,
                          inclination_deg=45.0, raan_deg=0.0, arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
        ),
        SpacecraftConfig(
            name="follower-1",
            orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6928.0, eccentricity=0.001,
                          inclination_deg=45.0, raan_deg=0.0, arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
        ),
    ])

    def fake_exec(self):
        self.chief_combo.setCurrentIndex(0)
        self.follower_name_edit.setText("follower-1")  # collides with the existing spacecraft
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(PhasingFormationDialog, "exec", fake_exec)
    critical_calls = []
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: critical_calls.append(a)))

    lw._on_generate_phasing_formation()
    assert len(lw.to_list()) == 2  # nothing added
    assert len(critical_calls) == 1


def test_list_widget_generate_phasing_formation_cancel_does_nothing(qtbot, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from missionstudio.gui.phasing_formation_dialog import PhasingFormationDialog
    from missionstudio.gui.spacecraft_editor import SpacecraftListWidget

    lw = SpacecraftListWidget()
    qtbot.addWidget(lw)
    monkeypatch.setattr(PhasingFormationDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    lw._on_generate_phasing_formation()
    assert lw.to_list() == []


def test_list_widget_generate_phasing_formation_reports_missing_basilisk(qtbot, monkeypatch):
    """Does NOT need requires_basilisk: generate_phasing_follower is
    monkeypatched to simulate the "no Basilisk build" case directly, same
    "clear error, not a traceback" pattern every other Basilisk-needing
    GUI action already uses (gui.run_worker) -- exercised here without
    actually needing Basilisk uninstalled.
    """
    from PySide6.QtWidgets import QDialog, QMessageBox

    from missionstudio.gui.phasing_formation_dialog import PhasingFormationDialog
    from missionstudio.gui.spacecraft_editor import SpacecraftListWidget
    from missionstudio.schema.scenario import OrbitIC, SpacecraftConfig

    lw = SpacecraftListWidget()
    qtbot.addWidget(lw)
    lw.from_list([SpacecraftConfig(
        name="chief-1",
        orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6928.0, eccentricity=0.001,
                      inclination_deg=45.0, raan_deg=0.0, arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
    )])

    def fake_exec(self):
        self.chief_combo.setCurrentIndex(0)
        self.follower_name_edit.setText("follower-1")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(PhasingFormationDialog, "exec", fake_exec)

    def fake_generate(*args, **kwargs):
        raise ImportError("No module named 'Basilisk'")

    monkeypatch.setattr("missionstudio.engine.formation.generate_phasing_follower", fake_generate)
    critical_calls = []
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: critical_calls.append(a)))

    lw._on_generate_phasing_formation()
    configs = lw.to_list()
    assert len(configs) == 1  # nothing added beyond the original chief
    assert configs[0].name == "chief-1"
    assert len(critical_calls) == 1
    assert "Basilisk" in critical_calls[0][1]


def test_list_widget_generate_phasing_formation_without_basilisk_reports_clear_error(qtbot, monkeypatch):
    """Same as the test above, but against the REAL no-Basilisk import
    path (no mocking of generate_phasing_follower itself) -- regression
    test for a real bug found while writing this feature: the ImportError
    this needs to catch is raised lazily INSIDE generate_phasing_follower()
    (see engine.formation's own docstring), not by importing the name
    itself (engine.formation has no Basilisk import at module level) --
    wrapping the wrong statement in try/except ImportError (as this
    file's cli.py sibling command originally did) lets it propagate
    uncaught. Skipped on a machine that DOES have Basilisk, where this
    test's premise doesn't hold.
    """
    import importlib.util

    from PySide6.QtWidgets import QDialog, QMessageBox

    from missionstudio.gui.phasing_formation_dialog import PhasingFormationDialog
    from missionstudio.gui.spacecraft_editor import SpacecraftListWidget
    from missionstudio.schema.scenario import OrbitIC, SpacecraftConfig

    if importlib.util.find_spec("Basilisk") is not None:
        pytest.skip("this test's premise is specifically that Basilisk is unavailable")

    lw = SpacecraftListWidget()
    qtbot.addWidget(lw)
    lw.from_list([SpacecraftConfig(
        name="chief-1",
        orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6928.0, eccentricity=0.001,
                      inclination_deg=45.0, raan_deg=0.0, arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
    )])

    def fake_exec(self):
        self.chief_combo.setCurrentIndex(0)
        self.follower_name_edit.setText("follower-1")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(PhasingFormationDialog, "exec", fake_exec)
    critical_calls = []
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: critical_calls.append(a)))

    lw._on_generate_phasing_formation()  # must not raise

    assert len(lw.to_list()) == 1
    assert len(critical_calls) == 1
    assert "Basilisk" in critical_calls[0][1]
