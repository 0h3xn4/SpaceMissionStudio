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

"""ResultsWidget: plots a :class:`engine.results.ResultSet` with Plotly,
embedded in a ``QWebEngineView`` -- replaces an earlier matplotlib
version, per explicit user request ("please rather use plotly, and not
matplotlib... make the plots visually more clear, professional and
appealing and informative") plus a real, separate complaint (matplotlib's
default axis formatting fell back to scientific/offset notation on
several series -- Plotly is configured below to never do that, on every
axis, regardless of data range). Takes a plain ``ResultSet`` -- no
Basilisk import in this module, so it's testable here with synthetic
data exactly like ``engine/results.py`` itself is.

``QWebEngineView``, not a static image: an embedded Plotly chart is a
real, interactive HTML/JS page (pan/zoom/box-select, a unified hover
tooltip showing every series' value at the cursor's x-position, a
built-in PNG-export button) -- a screenshot-style static render would
throw away exactly the interactivity that makes Plotly worth using over
matplotlib in the first place. ``plotly.js`` itself (~4.7 MB) is
referenced via a local ``file://`` src pointing directly at the copy
already installed as part of the ``plotly`` PyPI package's own
``package_data`` (:func:`_plotlyjs_path`) -- never a CDN reference (this
project avoids unnecessary network dependencies throughout, and a
missionStudio desktop install has no reason to need one just to redraw a
plot), and never a second bundled copy of a multi-megabyte file this
project doesn't need to ship or keep in sync itself.

Running as root (this project's own CI/dev sandbox is; most real desktop
installs are not): Chromium refuses to start its renderer process as
root unless ``--no-sandbox`` is passed (a Chromium policy, not a Qt one
-- process sandboxing normally works by dropping privileges via setuid,
which is meaningless starting from an already-root process) -- confirmed
directly against a real ``QWebEngineView`` in this development sandbox,
which failed exactly that way without it. Handled below by setting
``QTWEBENGINE_CHROMIUM_FLAGS`` BEFORE ``PySide6.QtWebEngineWidgets`` is
imported (the only point at which QtWebEngine reads it) -- and ONLY when
actually running as root (``os.geteuid() == 0``), left off for a normal
non-root install, where Chromium's own process sandbox is real
defense-in-depth worth keeping even though this widget only ever loads
its own locally-generated HTML/JS, never remote or otherwise untrusted
content.

Verification status: the full local-``plotly.min.js``-via-``file://``
plus ``QWebEngineView.setHtml()`` pipeline was confirmed end-to-end in
this development sandbox (``QT_QPA_PLATFORM=offscreen`` -- no real
display here either) -- ``loadFinished`` fires ``True`` and a real
in-page JS check (``document.getElementsByClassName("plotly").length``)
confirms the chart div actually renders, not just that ``setHtml()``
didn't raise. The chosen design (re-send the FULL html, plotly.js
``<script src>`` reference included, on every redraw, rather than
loading the page shell once and pushing incremental updates via
``Plotly.react()`` through ``page().runJavaScript()``) was picked for
simplicity and testability (the built ``go.Figure`` object is directly
inspectable in a test, same role matplotlib's ``Axes`` used to play) --
NOT benchmarked against the incremental-update alternative for redraw
latency during a live (``set_live_result``) run; if that turns out to
feel sluggish on a real machine for a long/fast-updating run, the
incremental-update approach is the documented next step, not something
ruled out here.

Two independent display choices, both user feedback, both PLOT-only
(``export_csv()``/``_on_export()`` below keep writing exactly what
``TimeSeries`` holds -- raw SI units, elapsed seconds -- since a CSV a
user hands to another tool should stay unambiguous, not follow a
plot-only display preference):

* Length/length-rate series (``units in {"m", "m/s"}`` -- position,
  velocity, altitude, slant range, delta-V, ...) are shown in km/km-s,
  not raw meters -- meter-scale numbers on an orbit-scale plot were the
  complaint (e.g. a LEO position plot's y-axis in the millions).
  ``_DISPLAY_UNIT_CONVERSIONS`` is deliberately narrow: everything else
  (accelerometer m/s^2, torque N*m, angles rad/deg, ...) is left as
  ``TimeSeries`` already has it, since km-scale units would be actively
  worse there, not better.
* The x-axis defaults to elapsed time (hours since the scenario epoch,
  as before) but can be switched to absolute epoch (UTC datetimes,
  ``series.time_s`` added to the epoch :meth:`set_result`/
  :meth:`set_live_result` were given) via ``x_axis_combo``. ``epoch_utc``
  is optional and defaults to ``None`` (falls back to elapsed time even
  if "Epoch (UTC)" is selected) so every existing caller/test that only
  ever passed a bare ``ResultSet`` keeps working unchanged.
"""

from __future__ import annotations

import os

# See module docstring's "Running as root" section -- MUST happen before
# PySide6.QtWebEngineWidgets is imported below (env var read at that
# module's own native init time; setting it any later has no effect).
if hasattr(os, "geteuid") and os.geteuid() == 0:
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox")

from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

import plotly.graph_objects as go
from PySide6.QtCore import QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QComboBox, QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from ..engine.results import ResultSet, TimeSeries

# unit -> (display unit, divisor) -- see module docstring for why this is
# narrowly scoped to length/length-rate units only.
_DISPLAY_UNIT_CONVERSIONS = {
    "m": ("km", 1000.0),
    "m/s": ("km/s", 1000.0),
}

# Categorical series colors -- the first three slots of a validated,
# colorblind-safe 8-hue palette (Claude's dataviz skill,
# references/palette.md: worst adjacent/all-pairs CVD Delta E clears the
# >= 8 target in both light and dark mode). Three is also exactly this
# project's own common case -- every (x, y, z) position/velocity/MRP
# series has three columns.
_SERIES_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]

# Chart chrome, matching gui/theme.py's own light palette (_C dict) --
# reused here rather than re-picked, so an embedded chart reads as part
# of the same application, not a visually foreign inserted widget.
_INK_PRIMARY = "#1F2530"  # theme.py's "text"
_INK_MUTED = "#5B6472"  # theme.py's "text_muted"
_GRID_COLOR = "#D8DCE3"  # theme.py's "border"
_SURFACE = "#FFFFFF"  # theme.py's "surface"
_EMPTY_STATE_TEXT = "#8A93A3"  # same color the previous matplotlib empty-state message used
_FONT_FAMILY = "system-ui, -apple-system, 'Segoe UI', sans-serif"


def _display_units(series: TimeSeries) -> Tuple["object", str]:
    """Returns ``(data, unit_label)`` for PLOTTING -- ``series.data``
    itself/``series.units`` unchanged unless a km-scale conversion
    applies (see ``_DISPLAY_UNIT_CONVERSIONS``).
    """
    conversion = _DISPLAY_UNIT_CONVERSIONS.get(series.units)
    if conversion is None:
        return series.data, series.units
    display_unit, divisor = conversion
    return series.data / divisor, display_unit


def _plotlyjs_path() -> Path:
    """Absolute filesystem path to the ``plotly.min.js`` bundle already
    installed as part of the ``plotly`` PyPI package -- see module
    docstring's "QWebEngineView, not a static image" section for why
    this is referenced directly rather than re-bundled or CDN-loaded.
    """
    import plotly

    return Path(plotly.__file__).parent / "package_data" / "plotly.min.js"


def _empty_state_html() -> str:
    """Shown before any run has produced a result -- previously a blank
    white canvas with no explanation (part of the "looks unfinished"
    feedback the matplotlib version's own docstring already addressed);
    kept as plain HTML/CSS here, no Plotly involved, so it costs nothing
    to render.
    """
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
  html, body {{ margin: 0; height: 100%; background: {_SURFACE};
                font-family: {_FONT_FAMILY}; }}
  .empty {{ display: flex; align-items: center; justify-content: center;
            height: 100%; color: {_EMPTY_STATE_TEXT}; font-size: 14px; }}
</style></head>
<body><div class="empty">Run a simulation to see results here</div></body></html>"""


class ResultsWidget(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._result: ResultSet | None = None
        self._epoch_utc: Optional[str] = None
        self.figure: Optional[go.Figure] = None  # the currently-plotted go.Figure, or None (empty state)

        layout = QVBoxLayout(self)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Series:"))
        self.series_combo = QComboBox()
        self.series_combo.currentIndexChanged.connect(self._redraw)
        top_row.addWidget(self.series_combo, stretch=1)
        top_row.addWidget(QLabel("X-axis:"))
        self.x_axis_combo = QComboBox()
        self.x_axis_combo.addItem("Elapsed time", "elapsed")
        self.x_axis_combo.addItem("Epoch (UTC)", "epoch")
        self.x_axis_combo.setToolTip(
            "\"Epoch (UTC)\" needs the scenario's epoch, which is only known once a run has actually "
            "produced this result -- falls back to elapsed time if it isn't available."
        )
        self.x_axis_combo.currentIndexChanged.connect(self._redraw)
        top_row.addWidget(self.x_axis_combo)
        self.export_button = QPushButton("Export all series to CSV...")
        self.export_button.clicked.connect(self._on_export)
        self.export_button.setEnabled(False)
        top_row.addWidget(self.export_button)
        layout.addLayout(top_row)

        self.web_view = QWebEngineView()
        layout.addWidget(self.web_view)
        self._redraw()  # shows the empty-state message immediately, not just after the first set_result() call

    def set_result(self, result: ResultSet | None, epoch_utc: Optional[str] = None) -> None:
        self._result = result
        self._epoch_utc = epoch_utc
        self.series_combo.blockSignals(True)
        self.series_combo.clear()
        if result is not None:
            for name in result.series:
                self.series_combo.addItem(name)
        self.series_combo.blockSignals(False)
        self.export_button.setEnabled(result is not None and bool(result.series))
        self._redraw()

    def set_live_result(self, result: ResultSet, epoch_utc: Optional[str] = None) -> None:
        """Updates the plot with one chunk's worth of a still-running
        simulation (see ``gui.run_worker.RunWorker``'s ``progress`` signal /
        :meth:`engine.service.SimulationService.run_live`). Unlike
        :meth:`set_result`, this never rebuilds ``series_combo`` once it
        already holds this result's series names -- the set of series a
        live run reports is fixed from its very first callback (which
        series exist is decided by the scenario, not by how much data has
        been recorded), so rebuilding it every chunk would keep resetting
        whatever series the user is currently looking at, fighting them
        while they watch it run.
        """
        is_first_update = self._result is None or set(self._result.series) != set(result.series)
        self._result = result
        self._epoch_utc = epoch_utc  # same every chunk of one run, but cheap enough not to bother guarding
        if is_first_update:
            self.series_combo.blockSignals(True)
            self.series_combo.clear()
            for name in result.series:
                self.series_combo.addItem(name)
            self.series_combo.blockSignals(False)
            self.export_button.setEnabled(bool(result.series))
        self._redraw()

    def _x_axis_values(self, time_s):
        """Returns ``(x_values, axis_label)``. "Epoch (UTC)" needs both a
        real epoch (``set_result``/``set_live_result`` were given one --
        absent for e.g. a bare synthetic ``ResultSet`` in a test, or
        before any run has actually happened yet) and for it to parse;
        either problem falls back to elapsed time rather than raising,
        matching this widget's existing "never crash the GUI over
        display preferences" behavior (see e.g. ``_redraw``'s own
        empty-state handling).
        """
        if self.x_axis_combo.currentData() == "epoch" and self._epoch_utc:
            try:
                base = datetime.fromisoformat(self._epoch_utc)
            except ValueError:
                pass
            else:
                return [base + timedelta(seconds=float(t)) for t in time_s], "Epoch (UTC)"
        return time_s / 3600.0, "Elapsed time [hr]"

    def _build_figure(self, name: str, series: TimeSeries) -> go.Figure:
        display_data, display_unit = _display_units(series)
        x_values, x_label = self._x_axis_values(series.time_s)
        is_datetime_axis = self.x_axis_combo.currentData() == "epoch" and x_label == "Epoch (UTC)"

        fig = go.Figure()
        for i, column in enumerate(series.columns):
            fig.add_trace(go.Scatter(
                x=x_values, y=display_data[:, i], mode="lines", name=column,
                line=dict(color=_SERIES_COLORS[i % len(_SERIES_COLORS)], width=2),
            ))

        axis_common = dict(
            gridcolor=_GRID_COLOR, zerolinecolor=_GRID_COLOR, linecolor=_GRID_COLOR,
            tickfont=dict(color=_INK_MUTED), title_font=dict(color=_INK_MUTED),
        )
        y_axis = dict(axis_common, title_text=f"[{display_unit}]" if display_unit else None)
        x_axis = dict(axis_common, title_text=x_label)
        if not is_datetime_axis:
            # Both fix the exact complaint that started this: matplotlib's
            # default tick formatter fell back to an offset/scientific
            # notation (e.g. "1e6") on several of this app's own plots.
            # exponentformat="none" forbids it entirely, on every axis,
            # regardless of how large/small the data range is;
            # separatethousands adds comma grouping so a plain large
            # number (e.g. "7,123,456") still reads cleanly instead of as
            # one long digit run. Skipped for a datetime axis, where
            # neither setting is meaningful (Plotly formats dates on its
            # own date-axis path).
            y_axis["exponentformat"] = "none"
            y_axis["separatethousands"] = True
            x_axis["exponentformat"] = "none"
            x_axis["separatethousands"] = True

        fig.update_layout(
            title=dict(text=name, font=dict(size=16, color=_INK_PRIMARY, family=_FONT_FAMILY)),
            xaxis=x_axis,
            yaxis=y_axis,
            font=dict(family=_FONT_FAMILY, color=_INK_PRIMARY),
            plot_bgcolor=_SURFACE,
            paper_bgcolor=_SURFACE,
            hovermode="x unified",
            showlegend=len(series.columns) > 1,  # a single series names itself in the title -- no legend box needed
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(color=_INK_MUTED)),
            margin=dict(l=70, r=30, t=60, b=50),
        )
        return fig

    def _redraw(self) -> None:
        self.figure = None
        if self._result is not None and self.series_combo.count() > 0:
            name = self.series_combo.currentText()
            series = self._result.series.get(name)
            if series is not None:
                self.figure = self._build_figure(name, series)

        if self.figure is None:
            html = _empty_state_html()
            base_url = QUrl()
        else:
            html = self.figure.to_html(
                include_plotlyjs=str(_plotlyjs_path()), full_html=True,
                config={"displaylogo": False, "responsive": True},
            )
            base_url = QUrl.fromLocalFile(str(_plotlyjs_path().parent) + "/")
        self.web_view.setHtml(html, base_url)

    def _on_export(self) -> None:
        if self._result is None:
            return
        out_dir = QFileDialog.getExistingDirectory(self, "Export results to CSV")
        if not out_dir:
            return
        try:
            paths = self._result.export_csv(Path(out_dir))
        except OSError as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        QMessageBox.information(self, "Export complete", f"Wrote {len(paths)} CSV file(s) to {out_dir}")
