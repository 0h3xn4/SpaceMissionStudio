"""Tests for gui.kernel_status_widget.KernelStatusWidget.

This development sandbox genuinely has no Basilisk build, so
``test_refresh_without_basilisk_reports_clear_status`` below exercises the
REAL no-Basilisk path through an actual background QThread -- not a mock
of what that path "should" do.

``test_refresh_disables_button_while_running`` mocks the worker's ``run()``
instead: a REAL kernel fetch is a genuine network call (``engine.kernels.
ensure_kernels()``), and on a machine that DOES have Basilisk but a slow or
blocked network, that call can take far longer than any reasonable test
timeout -- confirmed directly: running this suite against a real Basilisk
install in an environment that blocks the NAIF kernel host, the un-mocked
version of this test genuinely timed out past 5 seconds (pooch's retry
-with-backoff loop across two kernels-and-mirrors). The button's disable
-then-re-enable behavior is what this test is actually about, so it's
verified with a fast, deterministic stand-in for the worker's real body,
independent of Basilisk's availability or the network's.
"""

import importlib.util

import pytest

pytestmark = pytest.mark.requires_gui

_BASILISK_AVAILABLE = importlib.util.find_spec("Basilisk") is not None


@pytest.fixture
def widget(qtbot):
    from missionstudio.gui.kernel_status_widget import KernelStatusWidget

    w = KernelStatusWidget()
    qtbot.addWidget(w)
    return w


def test_initial_state(widget):
    assert "not checked" in widget.status_label.text()
    assert widget.table.rowCount() == 0


def test_only_the_path_column_stretches(widget):
    """Regression guard for a real rendering bug, found by actually
    rendering this table and looking at it: a blanket Stretch on every
    column forced all 4 to the SAME width regardless of content, so
    "Cache last modified (UTC)" (by far the longest header) came out
    truncated on both ends. Only "Path" should stretch -- the rest size
    to their own content.
    """
    from PySide6.QtWidgets import QHeaderView

    header = widget.table.horizontalHeader()
    for col in range(widget.table.columnCount()):
        expected = QHeaderView.ResizeMode.Stretch if col == 2 else QHeaderView.ResizeMode.ResizeToContents
        assert header.sectionResizeMode(col) == expected, f"column {col}"


def test_unavailable_kernel_shows_short_status_with_error_as_tooltip(widget):
    """Regression guard: the "Available" cell used to embed the full
    error message inline ("NO: download failed: connection refused"),
    which (once the blanket-Stretch bug above was fixed) forced THAT
    column wide instead, stealing width from "Path" -- the more
    important column to keep readable. The short "NO" plus a tooltip
    keeps every column's width driven by genuinely short content while
    still surfacing the detail one hover away.
    """
    from types import SimpleNamespace

    statuses = [
        SimpleNamespace(filename="de430.bsp", available=False, error="download failed: connection refused",
                         path=None, modified_utc=None),
    ]
    widget._on_finished(statuses)

    item = widget.table.item(0, 1)
    assert item.text() == "NO"
    assert item.toolTip() == "download failed: connection refused"


def test_path_cell_carries_the_full_path_as_a_tooltip(widget):
    """The "Path" column can't be interactively widened by the user (it's
    Stretch-mode, by design, so it always claims the remaining space
    rather than needing a scrollbar) -- a long real path can still get
    visually truncated, so the full path is always available as a
    tooltip regardless.
    """
    from pathlib import Path
    from types import SimpleNamespace

    statuses = [
        SimpleNamespace(filename="naif0012.tls", available=True, error=None,
                         path=Path("/home/user/.cache/basilisk/naif0012.tls"), modified_utc="2026-01-15T08:23:11"),
    ]
    widget._on_finished(statuses)

    item = widget.table.item(0, 2)
    assert item.toolTip() == "/home/user/.cache/basilisk/naif0012.tls"


def test_refresh_disables_button_while_running(widget, qtbot, monkeypatch):
    from missionstudio.gui.kernel_status_widget import _KernelFetchWorker

    monkeypatch.setattr(_KernelFetchWorker, "run", lambda self: self.finished_ok.emit([]))

    widget.refresh()
    assert not widget.refresh_button.isEnabled()
    qtbot.waitUntil(lambda: widget.refresh_button.isEnabled(), timeout=5000)


def test_refresh_while_already_running_does_not_orphan_the_worker(widget, qtbot, monkeypatch):
    """Regression test for an audit finding: MainWindow's "Check Kernels"
    menu/toolbar action calls refresh() directly, independent of
    refresh_button's enabled state -- so calling refresh() again while a
    fetch is still in flight used to reassign self._worker, dropping the
    only Python reference to the still-running QThread (a real Qt crash
    risk: "QThread: Destroyed while thread is still running").
    """
    import threading

    from missionstudio.gui.kernel_status_widget import _KernelFetchWorker

    release = threading.Event()
    monkeypatch.setattr(_KernelFetchWorker, "run", lambda self: release.wait(5) and self.finished_ok.emit([]))

    widget.refresh()
    qtbot.waitUntil(lambda: widget._worker.isRunning(), timeout=5000)
    first_worker = widget._worker

    widget.refresh()  # e.g. the toolbar action firing again -- must be a no-op
    assert widget._worker is first_worker

    release.set()
    qtbot.waitUntil(lambda: widget.refresh_button.isEnabled(), timeout=5000)


@pytest.mark.skipif(_BASILISK_AVAILABLE, reason="this test's premise is specifically that Basilisk is unavailable")
def test_refresh_without_basilisk_reports_clear_status(widget, qtbot):
    widget.refresh()
    qtbot.waitUntil(lambda: widget.refresh_button.isEnabled(), timeout=5000)
    assert "Basilisk is not installed" in widget.status_label.text()
    assert widget.table.rowCount() == 0
