"""Tests for gui.sensor_actuator_editor.SensorActuatorListWidget."""

import json

import pytest

pytestmark = pytest.mark.requires_gui


def test_from_list_to_list_round_trip(qtbot):
    from spacemissionstudio.gui.sensor_actuator_editor import SensorActuatorListWidget
    from spacemissionstudio.schema.scenario import SUPPORTED_SENSOR_KINDS, SensorConfig

    widget = SensorActuatorListWidget(SensorConfig, SUPPORTED_SENSOR_KINDS)
    qtbot.addWidget(widget)
    sensors = [
        SensorConfig(kind="star_tracker", name="st-1", params={"noise_arcsec": 5.0}),
        SensorConfig(kind="imu", name="imu-1", params={}),
    ]
    widget.from_list(sensors)
    assert widget.list_widget.count() == 2
    assert [s.name for s in widget.to_list()] == ["st-1", "imu-1"]
    assert widget.to_list()[0].params == {"noise_arcsec": 5.0}


def test_add_via_dialog(qtbot, monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDialog

    from spacemissionstudio.gui.sensor_actuator_editor import SensorActuatorListWidget, _ItemEditorDialog
    from spacemissionstudio.schema.scenario import SUPPORTED_ACTUATOR_KINDS, ActuatorConfig

    widget = SensorActuatorListWidget(ActuatorConfig, SUPPORTED_ACTUATOR_KINDS)
    qtbot.addWidget(widget)

    def fake_exec(self):
        self.name_edit.setText("rw-1")
        index = self.kind_combo.findText("reaction_wheel")
        self.kind_combo.setCurrentIndex(index)
        x, y, z = self._vector_boxes["gsHat_B"]  # spin-box row, not the JSON params box -- see module docstring
        x.setValue(1.0)
        y.setValue(0.0)
        z.setValue(0.0)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(_ItemEditorDialog, "exec", fake_exec)
    changed_count = []
    widget.changed.connect(lambda: changed_count.append(1))

    qtbot.mouseClick(widget.add_button, Qt.MouseButton.LeftButton)

    assert widget.list_widget.count() == 1
    added = widget.to_list()[0]
    assert added.name == "rw-1"
    assert added.kind == "reaction_wheel"
    assert added.params["gsHat_B"] == [1.0, 0.0, 0.0]
    assert changed_count == [1]


def test_edit_and_remove(qtbot, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from spacemissionstudio.gui.sensor_actuator_editor import SensorActuatorListWidget, _ItemEditorDialog
    from spacemissionstudio.schema.scenario import SUPPORTED_SENSOR_KINDS, SensorConfig

    widget = SensorActuatorListWidget(SensorConfig, SUPPORTED_SENSOR_KINDS)
    qtbot.addWidget(widget)
    widget.from_list([SensorConfig(kind="imu", name="orig", params={})])
    widget.list_widget.setCurrentRow(0)

    def fake_exec(self):
        self.name_edit.setText("renamed")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(_ItemEditorDialog, "exec", fake_exec)
    widget._on_edit()
    assert widget.to_list()[0].name == "renamed"

    widget.list_widget.setCurrentRow(0)
    widget._on_remove()
    assert widget.to_list() == []


def test_rejects_duplicate_name_on_add(qtbot, monkeypatch):
    from PySide6.QtWidgets import QDialog, QMessageBox

    from spacemissionstudio.gui.sensor_actuator_editor import SensorActuatorListWidget, _ItemEditorDialog
    from spacemissionstudio.schema.scenario import SUPPORTED_SENSOR_KINDS, SensorConfig

    widget = SensorActuatorListWidget(SensorConfig, SUPPORTED_SENSOR_KINDS)
    qtbot.addWidget(widget)
    widget.from_list([SensorConfig(kind="imu", name="dup", params={})])

    def fake_exec(self):
        self.name_edit.setText("dup")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(_ItemEditorDialog, "exec", fake_exec)
    critical_calls = []
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: critical_calls.append(a)))

    widget._on_add()
    assert len(widget.to_list()) == 1
    assert len(critical_calls) == 1


def test_item_editor_dialog_rejects_invalid_json(qtbot):
    from spacemissionstudio.gui.sensor_actuator_editor import _ItemEditorDialog
    from spacemissionstudio.schema.scenario import SUPPORTED_SENSOR_KINDS, SensorConfig

    dialog = _ItemEditorDialog(SensorConfig, SUPPORTED_SENSOR_KINDS)
    qtbot.addWidget(dialog)
    dialog.name_edit.setText("s1")
    dialog.params_edit.setPlainText("not json")
    with pytest.raises(ValueError, match="not valid JSON"):
        dialog.to_dataclass()


def test_item_editor_dialog_rejects_empty_name(qtbot):
    from spacemissionstudio.gui.sensor_actuator_editor import _ItemEditorDialog
    from spacemissionstudio.schema.scenario import SUPPORTED_SENSOR_KINDS, SensorConfig

    dialog = _ItemEditorDialog(SensorConfig, SUPPORTED_SENSOR_KINDS)
    qtbot.addWidget(dialog)
    dialog.name_edit.setText("")
    with pytest.raises(ValueError, match="name must not be empty"):
        dialog.to_dataclass()


def test_item_editor_dialog_name_field_shows_inline_error_on_duplicate(qtbot):
    from spacemissionstudio.gui.sensor_actuator_editor import _ItemEditorDialog
    from spacemissionstudio.schema.scenario import SUPPORTED_SENSOR_KINDS, SensorConfig

    dialog = _ItemEditorDialog(SensorConfig, SUPPORTED_SENSOR_KINDS, other_names=["st-1"])
    qtbot.addWidget(dialog)

    dialog.name_edit.setText("st-1")
    assert dialog.name_edit.property("state") == "error"

    dialog.name_edit.setText("st-2")
    assert dialog.name_edit.property("state") != "error"


def test_item_editor_dialog_accept_blocks_and_keeps_dialog_open_on_duplicate_name(qtbot):
    """Regression guard for the same data-loss UX bug fixed in
    SpacecraftEditorDialog -- see that dialog's own test of the same
    name for the full explanation.
    """
    from spacemissionstudio.gui.sensor_actuator_editor import _ItemEditorDialog
    from spacemissionstudio.schema.scenario import SUPPORTED_SENSOR_KINDS, SensorConfig

    dialog = _ItemEditorDialog(SensorConfig, SUPPORTED_SENSOR_KINDS, other_names=["st-1"])
    qtbot.addWidget(dialog)
    dialog.name_edit.setText("st-1")

    dialog._on_accept()

    assert dialog.result() == 0
    assert dialog.name_edit.property("state") == "error"


def test_add_via_dialog_shows_a_toast_and_selects_the_row(qtbot, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from spacemissionstudio.gui.sensor_actuator_editor import SensorActuatorListWidget, _ItemEditorDialog
    from spacemissionstudio.schema.scenario import SUPPORTED_SENSOR_KINDS, SensorConfig

    widget = SensorActuatorListWidget(SensorConfig, SUPPORTED_SENSOR_KINDS)
    qtbot.addWidget(widget)

    def fake_exec(self):
        self.name_edit.setText("st-toast")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(_ItemEditorDialog, "exec", fake_exec)
    widget._on_add()

    assert widget.list_widget.currentRow() == 0
    toasts = getattr(widget.window(), "_spacemissionstudio_active_toasts", [])
    assert any("st-toast" in t.text() for t in toasts)


def test_new_item_dialog_prefills_params_with_kind_template(qtbot):
    """Regression test: a brand-new sensor/actuator used to start with an
    empty ``{}`` params box no matter the kind, forcing a beginner to
    already know (from reading engine/fsw.py's source) which keys that
    kind needs. It should now start pre-filled with a working example for
    whichever kind is selected when the dialog opens (the first entry in
    SUPPORTED_SENSOR_KINDS, "star_tracker", by default).
    """
    from spacemissionstudio.gui.sensor_actuator_editor import _ItemEditorDialog, _template_params
    from spacemissionstudio.schema.scenario import SUPPORTED_SENSOR_KINDS, SensorConfig

    dialog = _ItemEditorDialog(SensorConfig, SUPPORTED_SENSOR_KINDS)
    qtbot.addWidget(dialog)
    assert dialog.kind_combo.currentText() == "star_tracker"
    dialog.name_edit.setText("st-1")

    config = dialog.to_dataclass()
    assert config.params == _template_params("star_tracker")


def test_switching_kind_does_not_clobber_params_until_reset_clicked(qtbot):
    """Switching Kind must not silently overwrite whatever the user has
    already typed into params (or set in the vector spin boxes) -- only
    the explicit 'Reset to template' button does that (see this dialog's
    module docstring).
    """
    from spacemissionstudio.gui.sensor_actuator_editor import (
        _ItemEditorDialog,
        _non_vector_template_params,
        _vector_specs,
    )
    from spacemissionstudio.schema.scenario import SUPPORTED_SENSOR_KINDS, SensorConfig

    dialog = _ItemEditorDialog(SensorConfig, SUPPORTED_SENSOR_KINDS)
    qtbot.addWidget(dialog)
    dialog.params_edit.setPlainText('{"hand_typed": true}')

    index = dialog.kind_combo.findText("coarse_sun_sensor")
    dialog.kind_combo.setCurrentIndex(index)
    assert json.loads(dialog.params_edit.toPlainText()) == {"hand_typed": True}

    dialog._on_reset_template()
    assert json.loads(dialog.params_edit.toPlainText()) == _non_vector_template_params("coarse_sun_sensor")
    for spec in _vector_specs("coarse_sun_sensor"):
        x, y, z = dialog._vector_boxes[spec.key]
        assert [x.value(), y.value(), z.value()] == spec.example


def test_switching_kind_away_and_back_preserves_vector_edit(qtbot):
    """Regression test: _rebuild_vector_rows() used to only re-use the
    ORIGINAL item's saved vector value when Kind was switched back to the
    exact kind this dialog opened on, and used the kind's static template
    example for every other kind -- even one the user had already typed
    a value into earlier in this same dialog session. So editing
    reaction_wheel's gsHat_B, switching to star_tracker and back to
    reaction_wheel silently reverted gsHat_B to whatever the item
    originally had, discarding the edit with no warning. Only 'Reset to
    template' is supposed to be able to throw away a typed value (see
    this module's docstring and
    test_switching_kind_does_not_clobber_params_until_reset_clicked above,
    which covers the non-vector JSON params box's side of this same rule).
    """
    from spacemissionstudio.gui.sensor_actuator_editor import _ItemEditorDialog
    from spacemissionstudio.schema.scenario import SUPPORTED_ACTUATOR_KINDS, ActuatorConfig

    item = ActuatorConfig(kind="reaction_wheel", name="rw-1", params={"gsHat_B": [0.0, 0.0, 1.0]})
    dialog = _ItemEditorDialog(ActuatorConfig, SUPPORTED_ACTUATOR_KINDS, item=item)
    qtbot.addWidget(dialog)

    x, y, z = dialog._vector_boxes["gsHat_B"]
    x.setValue(1.0)
    y.setValue(0.0)
    z.setValue(0.0)

    other_index = dialog.kind_combo.findText("star_tracker")
    dialog.kind_combo.setCurrentIndex(other_index)
    original_index = dialog.kind_combo.findText("reaction_wheel")
    dialog.kind_combo.setCurrentIndex(original_index)

    x, y, z = dialog._vector_boxes["gsHat_B"]
    assert [x.value(), y.value(), z.value()] == [1.0, 0.0, 0.0]

    # The item passed in must never be mutated by this dialog -- not even
    # by the cache write-back that fixes the above -- since the dialog
    # may yet be cancelled.
    assert item.params["gsHat_B"] == [0.0, 0.0, 1.0]


def test_missing_required_vector_key_is_caught_defensively():
    """The dialog's own spin-box rows make it structurally impossible to
    submit a required vector key (e.g. coarse_sun_sensor's nHat_B) with no
    value -- there's always a row, defaulting to the kind's template
    example. _missing_required_keys() is exercised directly here as
    defense in depth (e.g. against a future non-vector required key, or
    programmatic construction that bypasses the dialog).
    """
    from spacemissionstudio.gui.sensor_actuator_editor import _missing_required_keys

    assert _missing_required_keys("coarse_sun_sensor", {}) == ["nHat_B"]
    assert _missing_required_keys("coarse_sun_sensor", {"nHat_B": [1.0, 0.0, 0.0]}) == []
    assert _missing_required_keys("reaction_wheel", {}) == ["gsHat_B"]


def test_reset_to_template_button_overwrites_params(qtbot):
    from spacemissionstudio.gui.sensor_actuator_editor import _ItemEditorDialog
    from spacemissionstudio.schema.scenario import SUPPORTED_ACTUATOR_KINDS, ActuatorConfig

    dialog = _ItemEditorDialog(ActuatorConfig, SUPPORTED_ACTUATOR_KINDS,
                                item=ActuatorConfig(kind="reaction_wheel", name="rw-1", params={"stale": True}))
    qtbot.addWidget(dialog)
    assert dialog.params_edit.toPlainText() == json.dumps({"stale": True}, indent=2)

    dialog._on_reset_template()
    config = dialog.to_dataclass()
    assert "gsHat_B" in config.params
    assert "stale" not in config.params


def test_magnetic_torque_rod_shows_a_conditional_requirement_note(qtbot):
    """Regression guard: "magnetic_torque_rod" used to be in
    _UNIMPLEMENTED_ACTUATOR_KINDS (engine.service rejected it outright).
    It's wired up now, but ONLY for magnetic momentum management -- this
    checks the hint explains that extra requirement rather than either
    claiming it's unsimulated (false now) or saying nothing about the
    requirement at all (which would silently surprise a user at Run
    Simulation time).
    """
    from spacemissionstudio.gui.sensor_actuator_editor import _ItemEditorDialog
    from spacemissionstudio.schema.scenario import SUPPORTED_ACTUATOR_KINDS, ActuatorConfig

    dialog = _ItemEditorDialog(ActuatorConfig, SUPPORTED_ACTUATOR_KINDS)
    qtbot.addWidget(dialog)
    index = dialog.kind_combo.findText("magnetic_torque_rod")
    dialog.kind_combo.setCurrentIndex(index)
    assert "not simulated yet" not in dialog.hint_label.text()
    assert "magnetic_momentum_management" in dialog.hint_label.text()


def test_thruster_kind_is_implemented_and_round_trips(qtbot):
    """Regression guard: "thruster" used to be in _UNIMPLEMENTED_ACTUATOR_KINDS
    (engine.service rejected it at run time). Now that engine.fsw/
    engine.service build a real thrusterDynamicEffector control path for
    it, this kind must no longer show the "not simulated yet" warning, and
    its vector params (r_B, tHat_B) must round-trip through to_dataclass().
    """
    from spacemissionstudio.gui.sensor_actuator_editor import _ItemEditorDialog
    from spacemissionstudio.schema.scenario import SUPPORTED_ACTUATOR_KINDS, ActuatorConfig

    dialog = _ItemEditorDialog(ActuatorConfig, SUPPORTED_ACTUATOR_KINDS)
    qtbot.addWidget(dialog)
    index = dialog.kind_combo.findText("thruster")
    dialog.kind_combo.setCurrentIndex(index)
    assert "not simulated yet" not in dialog.hint_label.text()

    dialog.name_edit.setText("thr-1")
    dialog._on_reset_template()
    config = dialog.to_dataclass()
    assert config.params["r_B"] == [1.0, 0.0, 0.0]
    assert config.params["tHat_B"] == [1.0, 0.0, 0.0]
    assert config.params["MaxThrust"] == 1.0


def test_thruster_position_vector_row_has_no_normalize_button(qtbot):
    """Regression guard for a real bug caught while adding "thruster":
    every 3-element vector param used to get a "Normalize" button
    unconditionally, which is correct for a direction (tHat_B) but would
    silently corrupt a thruster's actual body-frame location (r_B, in
    meters) if clicked. Also protects magnetometer's noise_std_tesla,
    which had the same latent bug.
    """
    from PySide6.QtWidgets import QPushButton

    from spacemissionstudio.gui.sensor_actuator_editor import _ItemEditorDialog
    from spacemissionstudio.schema.scenario import SUPPORTED_ACTUATOR_KINDS, ActuatorConfig

    dialog = _ItemEditorDialog(ActuatorConfig, SUPPORTED_ACTUATOR_KINDS)
    qtbot.addWidget(dialog)
    index = dialog.kind_combo.findText("thruster")
    dialog.kind_combo.setCurrentIndex(index)

    r_b_row_widget = dialog._vector_form.itemAt(0, dialog._vector_form.ItemRole.FieldRole).widget()
    t_hat_row_widget = dialog._vector_form.itemAt(1, dialog._vector_form.ItemRole.FieldRole).widget()
    assert not r_b_row_widget.findChildren(QPushButton), "r_B (a position, not a direction) must have no Normalize button"
    assert len(t_hat_row_widget.findChildren(QPushButton)) == 1, "tHat_B (a direction) must keep its Normalize button"


def test_item_editor_dialog_resizes_to_its_own_sizehint_on_construction(qtbot):
    """See test_constellation_dialog.py's identical test for why."""
    from spacemissionstudio.gui.sensor_actuator_editor import _ItemEditorDialog
    from spacemissionstudio.schema.scenario import SUPPORTED_SENSOR_KINDS, SensorConfig

    dialog = _ItemEditorDialog(SensorConfig, SUPPORTED_SENSOR_KINDS)
    qtbot.addWidget(dialog)

    assert dialog.size() == dialog.sizeHint()
