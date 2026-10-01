"""Tests for gui.mission_output_widget.MissionOutputWidget."""

import numpy as np
import pytest

pytestmark = pytest.mark.requires_gui


def test_none_summary_clears_text(qtbot):
    from spacemissionstudio.gui.mission_output_widget import MissionOutputWidget

    widget = MissionOutputWidget()
    qtbot.addWidget(widget)
    widget.text_edit.setPlainText("stale content")

    widget.set_command_summary(None)
    assert widget.text_edit.toPlainText() == ""


def test_summary_lists_reports_in_order_with_values(qtbot):
    from spacemissionstudio.engine.results import CommandSummary, ReportEntry
    from spacemissionstudio.gui.mission_output_widget import MissionOutputWidget

    widget = MissionOutputWidget()
    qtbot.addWidget(widget)

    summary = CommandSummary(reports=[
        ReportEntry(label="checkpoint", t_s=100.0, values={"sat-1.position_N": np.array([1.0, 2.0, 3.0])}),
        ReportEntry(label=None, t_s=200.0, values={"sat-1.mass_kg": np.array([500.0])}),
    ], commands_executed=7)

    widget.set_command_summary(summary)
    text = widget.text_edit.toPlainText()

    assert "7 command(s) executed, 2 report(s)" in text
    assert "t = 100.000 s (checkpoint)" in text
    assert "sat-1.position_N = [1.0, 2.0, 3.0]" in text
    assert "t = 200.000 s" in text
    assert "sat-1.mass_kg = [500.0]" in text


def test_clear_empties_text(qtbot):
    from spacemissionstudio.gui.mission_output_widget import MissionOutputWidget

    widget = MissionOutputWidget()
    qtbot.addWidget(widget)
    widget.text_edit.setPlainText("something")
    widget.clear()
    assert widget.text_edit.toPlainText() == ""


def test_export_button_disabled_until_a_summary_with_reports_is_set(qtbot):
    """Regression guard for a real gap found while auditing this tab:
    CommandSummary.export_csv() already existed and was already tested
    at the engine layer, but nothing in this widget ever called it --
    the neighboring Results tab has had CSV export since the Plotly
    migration, but mission-sequence report output had no way out of the
    GUI except manually copying the text log.
    """
    from spacemissionstudio.engine.results import CommandSummary, ReportEntry
    from spacemissionstudio.gui.mission_output_widget import MissionOutputWidget

    widget = MissionOutputWidget()
    qtbot.addWidget(widget)
    assert not widget.export_button.isEnabled()

    widget.set_command_summary(CommandSummary(commands_executed=3, reports=[]))
    assert not widget.export_button.isEnabled()  # nothing to export -- no report commands ran

    widget.set_command_summary(CommandSummary(commands_executed=3, reports=[
        ReportEntry(label=None, t_s=1.0, values={"sat-1.mass_kg": np.array([500.0])}),
    ]))
    assert widget.export_button.isEnabled()

    widget.clear()
    assert not widget.export_button.isEnabled()


def test_export_writes_a_csv_file(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    from spacemissionstudio.engine.results import CommandSummary, ReportEntry
    from spacemissionstudio.gui.mission_output_widget import MissionOutputWidget

    widget = MissionOutputWidget()
    qtbot.addWidget(widget)
    widget.set_command_summary(CommandSummary(commands_executed=1, reports=[
        ReportEntry(label="checkpoint", t_s=100.0, values={"sat-1.position_N": np.array([1.0, 2.0, 3.0])}),
    ]))

    dest = tmp_path / "output.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(dest), "")))
    info_calls = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: info_calls.append(a)))

    widget._on_export()

    assert dest.exists()
    content = dest.read_text()
    assert "sat-1.position_N" in content
    assert len(info_calls) == 1


def test_export_with_no_summary_is_a_no_op(qtbot, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    from spacemissionstudio.gui.mission_output_widget import MissionOutputWidget

    widget = MissionOutputWidget()
    qtbot.addWidget(widget)
    calls = []
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: calls.append(1) or ("", "")))
    widget._on_export()  # self._summary is None
    assert calls == []
