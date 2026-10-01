"""Tests for gui.ground_station_editor."""

import pytest

pytestmark = pytest.mark.requires_gui


def test_dialog_default(qtbot):
    from spacemissionstudio.gui.ground_station_editor import GroundStationEditorDialog

    dialog = GroundStationEditorDialog()
    qtbot.addWidget(dialog)
    gs = dialog.to_dataclass()
    assert gs.name == "gs-1"
    assert gs.min_elevation_deg == 10.0
    assert gs.rx_antenna_gain_dbi == 45.0
    assert gs.system_noise_temp_k == 290.0


def test_dialog_round_trips_rf_link_fields(qtbot):
    from spacemissionstudio.gui.ground_station_editor import GroundStationEditorDialog
    from spacemissionstudio.schema.scenario import GroundStationConfig

    existing = GroundStationConfig(name="gs-existing", latitude_deg=10.0, longitude_deg=20.0,
                                    rx_antenna_gain_dbi=50.0, system_noise_temp_k=600.0)
    dialog = GroundStationEditorDialog(config=existing)
    qtbot.addWidget(dialog)
    got = dialog.to_dataclass()
    assert got.rx_antenna_gain_dbi == 50.0
    assert got.system_noise_temp_k == 600.0


def test_dialog_rejects_out_of_range_latitude(qtbot):
    from spacemissionstudio.gui.ground_station_editor import GroundStationEditorDialog

    dialog = GroundStationEditorDialog()
    qtbot.addWidget(dialog)
    # QDoubleSpinBox clamps to its own range, which is already [-90, 90] --
    # confirm the widget itself enforces that rather than allowing an
    # out-of-range value to reach the dataclass.
    dialog.lat_deg.setValue(999.0)
    assert dialog.lat_deg.value() <= 90.0


def test_list_widget_round_trip(qtbot):
    from spacemissionstudio.gui.ground_station_editor import GroundStationListWidget
    from spacemissionstudio.schema.scenario import GroundStationConfig

    lw = GroundStationListWidget()
    qtbot.addWidget(lw)
    lw.from_list([GroundStationConfig(name="svalbard", latitude_deg=78.23, longitude_deg=15.38)])
    assert lw.list_widget.count() == 1
    assert lw.to_list()[0].name == "svalbard"


def test_list_widget_add_via_dialog(qtbot, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from spacemissionstudio.gui.ground_station_editor import GroundStationEditorDialog, GroundStationListWidget

    lw = GroundStationListWidget()
    qtbot.addWidget(lw)

    def fake_exec(self):
        self.name_edit.setText("boulder")
        self.lat_deg.setValue(40.0)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(GroundStationEditorDialog, "exec", fake_exec)
    lw._on_add()
    assert lw.to_list()[0].name == "boulder"
    assert lw.to_list()[0].latitude_deg == 40.0
    assert lw.list_widget.currentRow() == 0
    toasts = getattr(lw.window(), "_spacemissionstudio_active_toasts", [])
    assert any("boulder" in t.text() for t in toasts)


def test_dialog_name_field_shows_inline_error_on_duplicate(qtbot):
    from spacemissionstudio.gui.ground_station_editor import GroundStationEditorDialog

    dialog = GroundStationEditorDialog(other_names=["gs-1", "gs-2"])
    qtbot.addWidget(dialog)

    dialog.name_edit.setText("gs-2")
    assert dialog.name_edit.property("state") == "error"

    dialog.name_edit.setText("gs-3")
    assert dialog.name_edit.property("state") != "error"


def test_dialog_accept_blocks_and_keeps_dialog_open_on_duplicate_name(qtbot):
    """Regression guard for the same data-loss UX bug fixed in
    SpacecraftEditorDialog -- see that dialog's own test of the same
    name for the full explanation.
    """
    from spacemissionstudio.gui.ground_station_editor import GroundStationEditorDialog

    dialog = GroundStationEditorDialog(other_names=["gs-1"])
    qtbot.addWidget(dialog)
    dialog.name_edit.setText("gs-1")

    dialog._on_accept()

    assert dialog.result() == 0
    assert dialog.name_edit.property("state") == "error"


def test_list_widget_remove_shows_a_toast(qtbot):
    from spacemissionstudio.gui.ground_station_editor import GroundStationListWidget
    from spacemissionstudio.schema.scenario import GroundStationConfig

    lw = GroundStationListWidget()
    qtbot.addWidget(lw)
    lw.from_list([GroundStationConfig(name="svalbard", latitude_deg=78.23, longitude_deg=15.38)])
    lw.list_widget.setCurrentRow(0)

    lw._on_remove()

    toasts = getattr(lw.window(), "_spacemissionstudio_active_toasts", [])
    assert any("svalbard" in t.text() and "Removed" in t.text() for t in toasts)


def test_dialog_resizes_to_its_own_sizehint_on_construction(qtbot):
    """See test_constellation_dialog.py's identical test for why."""
    from spacemissionstudio.gui.ground_station_editor import GroundStationEditorDialog

    dialog = GroundStationEditorDialog()
    qtbot.addWidget(dialog)

    assert dialog.size() == dialog.sizeHint()
