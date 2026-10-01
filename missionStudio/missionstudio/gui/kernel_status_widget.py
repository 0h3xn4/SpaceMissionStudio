#
#  ISC License
#
#  Copyright (c) 2026, Autonomous Vehicle Systems Lab, University of Colorado at Boulder
#
#  Permission to use, copy, modify, and/or distribute this software for any
#  purpose with or without fee is hereby granted, provided that the above
#  copyright notice and this permission notice appear in all copies.
#
#  THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
#  WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
#  MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
#  ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
#  WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
#  ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
#  OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
#

"""KernelStatusWidget: shows SPICE kernel fetch/cache status (see
``engine.kernels``) with a "Check / fetch kernels" button, satisfying the
"kernel management surfaced in the UI, not silently resolved in the
background" Phase 1 goal.

The actual fetch runs on a background ``QThread`` (it can trigger a
network download -- see ``engine.kernels.ensure_kernels()``), so it never
freezes the GUI. Importing ``engine.kernels`` needs a Basilisk build; when
it's missing, this widget reports that clearly instead of crashing --
genuinely exercised in this development sandbox (no Basilisk here), not
just handled in theory.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QHeaderView, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

_logger = logging.getLogger(__name__)


class _KernelFetchWorker(QThread):
    finished_ok = Signal(list)  # list[engine.kernels.KernelStatus]
    failed = Signal(str)

    def run(self) -> None:
        try:
            from ..engine import kernels
        except ImportError as exc:
            self.failed.emit(
                f"Basilisk is not installed/built ({exc}) -- kernel status is unavailable until it is. "
                f"See missionStudio/README.md."
            )
            return
        try:
            statuses = kernels.ensure_kernels()
        except Exception as exc:  # noqa: BLE001 -- surface ANY failure, never crash the worker thread silently
            # Full traceback to the log file/terminal -- see
            # logging_setup's own module docstring for why.
            _logger.exception("Kernel fetch failed")
            self.failed.emit(str(exc))
            return
        self.finished_ok.emit(statuses)


class KernelStatusWidget(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        self.status_label = QLabel("Kernel status not checked yet.")
        layout.addWidget(self.status_label)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Kernel", "Available", "Path", "Cache last modified (UTC)"])
        # A blanket Stretch on every column (the original setting) forces
        # all 4 to the SAME width regardless of content -- found by
        # actually rendering this widget and looking at it: "Cache last
        # modified (UTC)" (by far the longest header) came out truncated
        # on both ends ("ache last modified (UTC"), while "Kernel" sat in
        # a column much wider than it needed. Only "Path" (arbitrarily
        # long filesystem paths) benefits from claiming the remaining
        # width -- the other three size to fit their own header/content.
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)  # "Path"
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)

        self.refresh_button = QPushButton("Check / fetch kernels")
        self.refresh_button.clicked.connect(self.refresh)
        layout.addWidget(self.refresh_button)

        self._worker: _KernelFetchWorker | None = None

    def refresh(self) -> None:
        # Re-entrancy guard: refresh_button disables itself for the
        # duration of a fetch, but MainWindow's "Check Kernels"
        # menu/toolbar action calls this method directly and isn't tied to
        # that button's enabled state (see main_window.py's Run menu). Without
        # this guard, triggering that action again while a fetch is still
        # in flight would reassign self._worker, dropping the only Python
        # reference to the still-running QThread -- undefined behavior in
        # Qt ("QThread: Destroyed while thread is still running"), up to
        # and including a hard process abort.
        if self._worker is not None and self._worker.isRunning():
            return
        self.refresh_button.setEnabled(False)
        self.status_label.setText("Checking kernels...")
        self.table.setRowCount(0)
        self._worker = _KernelFetchWorker()
        self._worker.finished_ok.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_finished(self, statuses: list) -> None:
        self.refresh_button.setEnabled(True)
        ok_count = sum(1 for s in statuses if s.available)
        self.status_label.setText(f"{ok_count}/{len(statuses)} kernel(s) available.")
        self.table.setRowCount(len(statuses))
        for row, status in enumerate(statuses):
            self.table.setItem(row, 0, QTableWidgetItem(status.filename))
            # "NO" alone, not "NO: {error}" -- a real rendering bug, found
            # by actually populating this table and looking at it: the
            # "Available" column's ResizeToContents sizing had to grow to
            # fit the longest error message in the whole table, stealing
            # width from the "Path" column (the more important one to
            # keep readable -- a real filesystem path, not a diagnostic).
            # The error is still one hover away, just via setToolTip()
            # instead of inline text, matching the "short status at a
            # glance, detail on demand" pattern already used elsewhere in
            # this app (e.g. gui.feedback's inline-validation tooltips).
            available_item = QTableWidgetItem("yes" if status.available else "NO")
            if not status.available and status.error:
                available_item.setToolTip(status.error)
            self.table.setItem(row, 1, available_item)
            # A real cached path can still be longer than even the
            # Stretch-mode "Path" column's share of the window (Stretch
            # sections can't be interactively widened by the user to
            # compensate, unlike Interactive ones) -- a tooltip with the
            # full, untruncated path is a hover away either way.
            path_item = QTableWidgetItem(str(status.path) if status.path else "")
            if status.path:
                path_item.setToolTip(str(status.path))
            self.table.setItem(row, 2, path_item)
            self.table.setItem(row, 3, QTableWidgetItem(status.modified_utc or ""))

    def _on_failed(self, message: str) -> None:
        self.refresh_button.setEnabled(True)
        self.status_label.setText(message)
        self.table.setRowCount(0)
