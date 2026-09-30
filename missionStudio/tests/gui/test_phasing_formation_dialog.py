"""Tests for gui.phasing_formation_dialog.PhasingFormationDialog. No
Basilisk needed -- this dialog only builds a
engine.formation.PhasingFormationRequest (that module's own Basilisk
import is lazy, inside generate_phasing_follower() -- see this module's
own docstring), so these tests are requires_gui only, not
requires_basilisk (unlike tests/test_formation.py's own).
"""

import pytest

pytestmark = pytest.mark.requires_gui


def test_defaults_produce_a_valid_request(qtbot):
    from missionstudio.gui.phasing_formation_dialog import PhasingFormationDialog

    dialog = PhasingFormationDialog(["chief-1", "follower-1"], central_body="earth")
    qtbot.addWidget(dialog)
    request = dialog.to_request()
    assert request.chief_name == "chief-1"
    assert dialog.selected_chief_name() == "chief-1"
    assert dialog.selected_template_name() == "chief-1"
    assert request.along_track_km != 0.0


def test_central_body_is_not_independently_selectable(qtbot):
    from missionstudio.gui.phasing_formation_dialog import PhasingFormationDialog

    dialog = PhasingFormationDialog(["chief-1"], central_body="mars")
    qtbot.addWidget(dialog)
    # No combo/edit for it -- just the read-only label built in __init__;
    # nothing here should let central_body drift from what the caller passed.
    assert dialog._central_body == "mars"


def test_empty_spacecraft_list_disables_combos(qtbot):
    from missionstudio.gui.phasing_formation_dialog import PhasingFormationDialog

    dialog = PhasingFormationDialog([])
    qtbot.addWidget(dialog)
    assert not dialog.chief_combo.isEnabled()
    assert not dialog.template_combo.isEnabled()
    assert dialog.selected_chief_name() is None


def test_editing_fields_updates_request(qtbot):
    from missionstudio.gui.phasing_formation_dialog import PhasingFormationDialog

    dialog = PhasingFormationDialog(["chief-1", "chief-2"])
    qtbot.addWidget(dialog)
    dialog.chief_combo.setCurrentIndex(1)
    dialog.follower_name_edit.setText("wingman")
    dialog.radial_km.setValue(1.5)
    dialog.along_track_km.setValue(-75.0)
    dialog.cross_track_km.setValue(3.0)
    dialog.thrust_n.setValue(0.1)

    request = dialog.to_request()
    assert request.chief_name == "chief-2"
    assert request.follower_name == "wingman"
    assert request.radial_km == 1.5
    assert request.along_track_km == -75.0
    assert request.cross_track_km == 3.0
    assert request.thrust_n == 0.1


def test_accept_blocked_on_invalid_request(qtbot, monkeypatch):
    from PySide6.QtWidgets import QDialog, QMessageBox

    from missionstudio.gui.phasing_formation_dialog import PhasingFormationDialog

    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: None))
    dialog = PhasingFormationDialog(["chief-1"])
    qtbot.addWidget(dialog)
    dialog.along_track_km.setValue(0.0)  # invalid: phasing needs a nonzero along-track target
    dialog._on_accept()
    assert dialog.result() != QDialog.DialogCode.Accepted


def test_accept_blocked_when_follower_name_equals_chief_name(qtbot, monkeypatch):
    from PySide6.QtWidgets import QDialog, QMessageBox

    from missionstudio.gui.phasing_formation_dialog import PhasingFormationDialog

    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: None))
    dialog = PhasingFormationDialog(["chief-1"])
    qtbot.addWidget(dialog)
    dialog.follower_name_edit.setText("chief-1")
    dialog._on_accept()
    assert dialog.result() != QDialog.DialogCode.Accepted
