"""Tests for gui.vizard_dialog.VizardDialog."""

import pytest

pytestmark = pytest.mark.requires_gui


def test_description_label_wraps_instead_of_blowing_up_dialog_width(qtbot):
    """Regression guard for the same real bug fixed in
    phasing_formation_dialog.py (found via an actual user screenshot of
    that dialog) -- this dialog copied the identical top-description
    -QLabel shape, missing word-wrap the same way. See that test's own
    docstring for the full explanation.
    """
    from PySide6.QtWidgets import QLabel

    from spacemissionstudio.gui.vizard_dialog import VizardDialog

    dialog = VizardDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.wait(10)

    description_labels = [w for w in dialog.findChildren(QLabel) if len(w.text()) > 100]
    assert description_labels, "expected to find the long top description QLabel"
    assert all(w.wordWrap() for w in description_labels)


def test_defaults_to_disabled(qtbot):
    from spacemissionstudio.gui.vizard_dialog import VizardDialog

    dialog = VizardDialog()
    qtbot.addWidget(dialog)
    assert dialog.disabled_radio.isChecked()
    assert dialog.to_request() is None


def test_save_file_mode(qtbot):
    from spacemissionstudio.gui.vizard_dialog import VizardDialog

    dialog = VizardDialog()
    qtbot.addWidget(dialog)
    dialog.save_file_edit.setText("/tmp/out.bin")
    dialog.save_file_radio.setChecked(True)
    request = dialog.to_request()
    assert request.save_file == "/tmp/out.bin"
    assert request.live_stream is False


def test_live_stream_mode(qtbot):
    from spacemissionstudio.gui.vizard_dialog import VizardDialog

    dialog = VizardDialog()
    qtbot.addWidget(dialog)
    dialog.live_stream_radio.setChecked(True)
    request = dialog.to_request()
    assert request.live_stream is True
    assert request.save_file is None


def test_camera_target_and_orbit_lines_default(qtbot):
    from spacemissionstudio.gui.vizard_dialog import VizardDialog

    dialog = VizardDialog()
    qtbot.addWidget(dialog)
    dialog.live_stream_radio.setChecked(True)
    request = dialog.to_request()
    assert request.camera_target is None  # blank field -> None -> engine.vizard defaults to central body
    assert request.show_orbit_lines is True  # checked by default


def test_camera_target_and_orbit_lines_overridden(qtbot):
    from spacemissionstudio.gui.vizard_dialog import VizardDialog

    dialog = VizardDialog()
    qtbot.addWidget(dialog)
    dialog.live_stream_radio.setChecked(True)
    dialog.camera_target_edit.setText("sat-1")
    dialog.orbit_lines_check.setChecked(False)
    request = dialog.to_request()
    assert request.camera_target == "sat-1"
    assert request.show_orbit_lines is False


def test_preselects_camera_target_and_orbit_lines(qtbot):
    from spacemissionstudio.gui.vizard_dialog import VizardDialog

    dialog = VizardDialog(current_live_stream=True, current_camera_target="earth", current_show_orbit_lines=False)
    qtbot.addWidget(dialog)
    assert dialog.camera_target_edit.text() == "earth"
    assert not dialog.orbit_lines_check.isChecked()


def test_preselects_from_current_request(qtbot):
    from spacemissionstudio.gui.vizard_dialog import VizardDialog

    dialog = VizardDialog(current_live_stream=True)
    qtbot.addWidget(dialog)
    assert dialog.live_stream_radio.isChecked()

    dialog2 = VizardDialog(current_save_file="/tmp/existing.bin")
    qtbot.addWidget(dialog2)
    assert dialog2.save_file_radio.isChecked()
    assert dialog2.save_file_edit.text() == "/tmp/existing.bin"


def test_accept_blocked_when_save_file_mode_has_no_path(qtbot, monkeypatch):
    from PySide6.QtWidgets import QDialog, QMessageBox

    from spacemissionstudio.gui.vizard_dialog import VizardDialog

    critical_calls = []
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: critical_calls.append(a)))

    dialog = VizardDialog()
    qtbot.addWidget(dialog)
    dialog.save_file_radio.setChecked(True)
    dialog.save_file_edit.setText("")
    dialog._on_accept()
    assert dialog.result() != QDialog.DialogCode.Accepted
    # Regression guard: this used to silently move focus back to the empty
    # field with no explanation at all -- every sibling dialog in this app
    # (dispersion/ground-station/propagation-setup/constellation) tells the
    # user why OK didn't do anything via QMessageBox.critical; this dialog
    # must too.
    assert len(critical_calls) == 1


def test_dialog_resizes_to_its_own_sizehint_on_construction(qtbot):
    """See test_constellation_dialog.py's identical test for why."""
    from spacemissionstudio.gui.vizard_dialog import VizardDialog

    dialog = VizardDialog()
    qtbot.addWidget(dialog)

    assert dialog.size() == dialog.sizeHint()
