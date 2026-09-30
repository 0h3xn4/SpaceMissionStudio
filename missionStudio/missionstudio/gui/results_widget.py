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

Display choices below are all PLOT-only (``export_csv()``/``_on_export()``
keep writing exactly what ``TimeSeries`` holds -- raw SI units, elapsed
seconds -- since a CSV a user hands to another tool should stay
unambiguous, not follow a plot-only display preference):

* Per-category unit display (``_categorize()``, replacing an earlier
  blanket "every m/m-s series -> km/km-s" rule this project's own
  earlier version used): real user feedback was that the blanket rule
  went too far -- it converted the state vector (position/velocity) AND
  delta-V to km/km-s along with genuinely orbit-scale quantities like
  altitude and semi-major axis, but the explicit ask was the opposite
  for the first two ("delta-V shall always be displayed in m/s",
  "state vector elements shall be displayed in meters for position and
  m/s for velocity") while keeping it for the second two ("altitudes,
  semi-major axes shall be displayed in km"). Both can't be satisfied by
  one rule keyed on the literal unit string alone (position and
  semi-major axis are both recorded in plain "m"; velocity and delta-V
  are both plain "m/s") -- ``_categorize()`` keys off what each named
  series actually *is* instead (see its own docstring), with each
  category's own explicit unit choice, and only an uncategorized/future
  series (``_legacy_display()``) falls back to the old blanket rule.
  Orbital angle elements (inclination/RAAN/argument of periapsis/true
  anomaly, osculating and mean alike) additionally display in degrees,
  not Basilisk's native radians -- matching every angle INPUT field this
  app's own Scenario Editor already uses (e.g. ``inclination_deg``), and
  part of the same "convey more information" feedback that asked for
  titles/axis names/legends on every plot (see ``_categorize()``).
* The x-axis defaults to elapsed time (hours since the scenario epoch,
  as before) but can be switched to absolute epoch (UTC datetimes,
  ``series.time_s`` added to the epoch :meth:`set_result`/
  :meth:`set_live_result` were given) via ``x_axis_combo``. ``epoch_utc``
  is optional and defaults to ``None`` (falls back to elapsed time even
  if "Epoch (UTC)" is selected) so every existing caller/test that only
  ever passed a bare ``ResultSet`` keeps working unchanged.
"""

from __future__ import annotations

import math
import os

# See module docstring's "Running as root" section -- MUST happen before
# PySide6.QtWebEngineWidgets is imported below (env var read at that
# module's own native init time; setting it any later has no effect).
if hasattr(os, "geteuid") and os.geteuid() == 0:
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox")

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

import plotly.graph_objects as go
from PySide6.QtCore import Qt, QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QCompleter,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..engine.results import ResultSet, TimeSeries

_RAD2DEG = 180.0 / math.pi

# "x"/"y"/"z" columns mean the same thing (an inertial-frame or body-frame
# vector component) everywhere they appear in this app's own series
# (position/velocity/body-rate/sun-heading/torque -- see engine.service),
# so every vector-column series below reuses this one label map.
_XYZ_LABELS = {"x": "X", "y": "Y", "z": "Z"}

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


@dataclass(frozen=True)
class _SeriesDisplay:
    """Everything :meth:`ResultsWidget._build_figure` needs to render one
    named series descriptively, beyond what the bare :class:`TimeSeries`
    itself already carries -- see :func:`_categorize`'s own docstring for
    where these come from. ``factor`` multiplies ``series.data`` for
    display only -- ``export_csv``/``_on_export`` never see it, matching
    this module's "display choices are plot-only" policy (module
    docstring). ``standalone_title`` is set for a category (access-window/
    link-margin series) whose own title already names every identifying
    detail -- everything else gets the owning spacecraft's name (the
    series name's own first dotted segment) prefixed automatically.
    """

    title: str
    y_label: str
    unit: str
    factor: float = 1.0
    columns: Optional[Dict[str, str]] = None
    standalone_title: bool = False


def _vector_display(name: str) -> Optional[_SeriesDisplay]:
    """State-vector and attitude/actuator vector series -- every one of
    these already has ("x","y","z") or equivalent columns in
    ``engine.service``. Position/velocity display in raw meters/m-s (NOT
    km/km-s) per explicit user request ("state vector elements shall be
    displayed in meters for position and m/s for velocity") -- a REVERSAL
    of this module's own earlier km-conversion decision for exactly these
    two series, which real user feedback showed went too far (see module
    docstring). Body rate/torque/etc. are left in Basilisk's own native
    units -- only position/velocity/delta-V/altitude/semi-major axis were
    named in that feedback.
    """
    if name.endswith(".position_N"):
        return _SeriesDisplay("Inertial Position (ECI)", "Position", "m", 1.0, dict(_XYZ_LABELS))
    if name.endswith(".velocity_N"):
        return _SeriesDisplay("Inertial Velocity (ECI)", "Velocity", "m/s", 1.0, dict(_XYZ_LABELS))
    if name.endswith(".attitude_sigma_BN"):
        return _SeriesDisplay("Attitude (MRP, Body to Inertial)", "MRP component", "-")
    if name.endswith(".body_rate_omega_BN_B"):
        return _SeriesDisplay("Body Angular Rate", "Angular rate", "rad/s", 1.0, dict(_XYZ_LABELS))
    if name.endswith(".sun_heading_body"):
        return _SeriesDisplay("Sun Heading (Body Frame)", "Unit vector component", "-", 1.0, dict(_XYZ_LABELS))
    if name.endswith(".control_torque"):
        return _SeriesDisplay("Commanded Control Torque", "Torque", "N*m", 1.0, dict(_XYZ_LABELS))
    if name.endswith(".rw_speeds"):
        return _SeriesDisplay("Reaction Wheel Speeds", "Wheel speed", "rad/s")
    if name.endswith(".thruster_on_time"):
        return _SeriesDisplay("Thruster On-Times", "Commanded on-time", "s")
    if name.endswith(".battery_charge"):
        return _SeriesDisplay("Battery State of Charge", "Charge", "W*hr", 1.0, {"charge": "Charge"})
    if name.endswith(".battery_net_power"):
        return _SeriesDisplay("Battery Net Power", "Net power", "W", 1.0, {"net_power": "Net power"})
    return None


def _orbit_element_display(name: str) -> Optional[_SeriesDisplay]:
    """The 6 osculating + 6 mean (first-order-J2) Keplerian element
    series ``engine.service._extract_results`` produces --
    ``.orbit_elements.*`` (per-sample ``orbitalMotion.rv2elem``, already
    existed) and ``.orbit_elements_mean.*`` (new: Basilisk's own
    ``orbitalMotion.clMeanOscMap``, osc -> mean, the same analytic J2
    short-period-removal its ``meanOEFeedback`` FSW module uses --
    conceptually the averaged-element idea the user pointed at via STK's
    "Brouwer-Lyddane Mean (Short)" data provider, built from a tool
    Basilisk itself ships rather than a bespoke implementation; see
    ``engine.service``'s own gating for why this is only computed when
    the scenario's central body actually has a modeled J2 term).

    Semi-major axis displays in km ("altitudes, semi-major axes shall be
    displayed in km"); the four angles (inclination/RAAN/argument of
    periapsis/true anomaly) display in degrees, matching every angle
    INPUT field this app's own Scenario Editor already uses (e.g.
    ``inclination_deg``) even though ``engine.service`` records them in
    Basilisk's native radians.
    """
    specs = [
        ("semi_major_axis", "Semi-Major Axis", "Semi-major axis", "km", 0.001),
        ("eccentricity", "Eccentricity", "Eccentricity", "-", 1.0),
        ("inclination", "Inclination", "Inclination", "deg", _RAD2DEG),
        ("raan", "RAAN", "RAAN", "deg", _RAD2DEG),
        ("arg_periapsis", "Argument of Periapsis", "Argument of periapsis", "deg", _RAD2DEG),
        ("true_anomaly", "True Anomaly", "True anomaly", "deg", _RAD2DEG),
    ]
    for field, title_suffix, y_label, unit, factor in specs:
        if name.endswith(f".orbit_elements.{field}"):
            return _SeriesDisplay(f"Osculating {title_suffix}", y_label, unit, factor)
        if name.endswith(f".orbit_elements_mean.{field}"):
            return _SeriesDisplay(f"Mean (first-order J2) {title_suffix}", y_label, unit, factor)
    return None


_CONTROLLER_TITLES = {
    "station_keeping": "Station-Keeping",
    "phasing_keeping": "Phasing-Keeping",
    "constant_thrust": "Constant-Thrust",
}


def _controller_display(name: str) -> Optional[_SeriesDisplay]:
    """``"{sc}.<controller>.<field>"`` series from
    ``engine.orbit_maintenance``'s three controllers. ``.delta_v`` is
    handled identically across all three (one shared branch below) and
    ALWAYS displays in raw m/s -- "delta-V shall always be displayed in
    m/s" -- a REVERSAL of this module's own earlier blanket km/s
    conversion, which real user feedback showed was wrong for delta-V
    specifically even though it shares the literal "m/s" unit string
    with velocity (see module docstring).
    """
    for key, label in _CONTROLLER_TITLES.items():
        marker = f".{key}."
        if marker not in name:
            continue
        field = name.rsplit(".", 1)[-1]
        if field == "delta_v":
            return _SeriesDisplay(f"{label} Cumulative Delta-V", "Cumulative delta-V", "m/s", 1.0,
                                   {"cumulative_delta_v": "Delta-V"})
        if field == "propellant_remaining":
            return _SeriesDisplay(f"{label} Propellant Remaining", "Propellant mass", "kg")
        if field == "altitude":
            return _SeriesDisplay(f"{label} Altitude Tracking", "Altitude", "km", 0.001,
                                   {"raw": "Raw", "smoothed": "Smoothed (filtered)"})
        if field == "burn_on":
            return _SeriesDisplay(f"{label} Thruster State", "Burn on (1) / off (0)", "-")
        if field == "separation_error":
            # Already recorded in degrees (engine.service: units="deg") --
            # factor 1.0, no conversion needed.
            return _SeriesDisplay(f"{label} Separation Error", "Angle error", "deg")
        if field == "state":
            return _SeriesDisplay(f"{label} Controller State", "State", "-")
        return None
    return None


def _access_pair_display(name: str) -> Optional[_SeriesDisplay]:
    """``"{gs}.access_to_{sc}.<field>"`` series (``engine.service``'s
    access-analysis loop, plus ``engine.link_budget.link_margin_series``)
    -- ``gs``/``sc`` recovered directly from the name (split on
    ``".access_to_"``, the literal separator both producers use) so the
    title names the actual ground-station/spacecraft pair. Slant range
    displays in km, elevation/azimuth in degrees -- same length/angle
    display policy as everywhere else in this module.
    """
    if ".access_to_" not in name:
        return None
    prefix, _, field = name.rpartition(".")
    gs, sep, sc = prefix.partition(".access_to_")
    if not sep:
        return None
    pair = f"{gs} -> {sc}"
    if field == "has_access":
        return _SeriesDisplay(f"Access Window: {pair}", "Has access", "-", 1.0,
                               {"has_access": "Has access"}, standalone_title=True)
    if field == "slant_range":
        return _SeriesDisplay(f"Slant Range: {pair}", "Slant range", "km", 0.001, standalone_title=True)
    if field == "elevation":
        return _SeriesDisplay(f"Elevation: {pair}", "Elevation angle", "deg", _RAD2DEG, standalone_title=True)
    if field == "azimuth":
        return _SeriesDisplay(f"Azimuth: {pair}", "Azimuth angle", "deg", _RAD2DEG, standalone_title=True)
    if field == "link_margin_db":
        return _SeriesDisplay(f"Link Margin: {pair}", "Link margin", "dB", 1.0, standalone_title=True)
    return None


def _sensor_display(name: str, series: TimeSeries) -> Optional[_SeriesDisplay]:
    """``"{sc}.sensor.{sensor_name}[.accel|.gyro]"`` series -- the sensor
    NAME is user-chosen (``schema.scenario``'s sensor config), so unlike
    every other category here the series name alone can't say which
    sensor TYPE produced it; ``series.columns``/``series.units``
    (already distinct per sensor type in ``engine.service``'s own
    recording code) disambiguate instead.
    """
    if ".sensor." not in name:
        return None
    if name.endswith(".accel"):
        sensor_name = name[: -len(".accel")].rsplit(".sensor.", 1)[-1]
        return _SeriesDisplay(f"IMU Accelerometer: {sensor_name}", "Acceleration", series.units, 1.0,
                               dict(_XYZ_LABELS))
    if name.endswith(".gyro"):
        sensor_name = name[: -len(".gyro")].rsplit(".sensor.", 1)[-1]
        return _SeriesDisplay(f"IMU Gyroscope: {sensor_name}", "Angular rate", series.units, 1.0,
                               dict(_XYZ_LABELS))
    sensor_name = name.rsplit(".sensor.", 1)[-1]
    if tuple(series.columns) == ("q0", "q1", "q2", "q3"):
        return _SeriesDisplay(f"Star Tracker Attitude: {sensor_name}", "Quaternion component", "-")
    if tuple(series.columns) == ("output",):
        return _SeriesDisplay(f"Coarse Sun Sensor: {sensor_name}", "Output", "-")
    if series.units == "T":
        return _SeriesDisplay(f"Magnetometer: {sensor_name}", "Magnetic field", "T", 1.0, dict(_XYZ_LABELS))
    return None


def _categorize(name: str, series: TimeSeries) -> Optional[_SeriesDisplay]:
    """Display metadata for every series ``engine.service``/
    ``engine.link_budget`` are known to produce -- ``None`` for anything
    else, which :func:`_legacy_display` falls back on: raw series name as
    title, ``series.units`` unconverted except the ORIGINAL narrow m/m-s
    -> km/km-s rule this module shipped with before this per-category
    system replaced it (see module docstring). That fallback means an
    uncategorized/future series still renders reasonably -- exactly as it
    would have before this feature existed -- rather than erroring or
    looking unfinished.
    """
    for fn in (_vector_display, _orbit_element_display, _controller_display, _access_pair_display):
        result = fn(name)
        if result is not None:
            return result
    return _sensor_display(name, series)


_LEGACY_UNIT_CONVERSIONS = {"m": ("km", 0.001), "m/s": ("km/s", 0.001)}


def _legacy_display(name: str, series: TimeSeries) -> _SeriesDisplay:
    display_unit, factor = _LEGACY_UNIT_CONVERSIONS.get(series.units, (series.units, 1.0))
    return _SeriesDisplay(title=name, y_label="", unit=display_unit, factor=factor, standalone_title=True)


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
        # Editable + a substring-matching QCompleter -- a real scenario
        # (e.g. the built-in 6-satellite Walker constellation template)
        # produces 30-40+ series, all named after the dotted scheme
        # engine.service/engine.link_budget use
        # ("leo-02-03.orbit_elements_mean.inclination", ...); a plain,
        # unsearchable dropdown list that long is tedious to scan.
        # MatchContains (not the default MatchStartsWith) matters here
        # specifically because the useful discriminator is usually in
        # the MIDDLE of the name (the spacecraft, or the category after
        # the first dot), not always the start. InsertPolicy.NoInsert
        # keeps typed-but-not-selected text from being added as a fake
        # new entry -- this combo's contents are always exactly
        # result.series's keys, nothing a user types can add to them.
        self.series_combo.setEditable(True)
        self.series_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.series_combo.setToolTip("Type to filter, or use the dropdown")
        completer = QCompleter(self.series_combo.model(), self.series_combo)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.series_combo.setCompleter(completer)
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
        display = _categorize(name, series) or _legacy_display(name, series)
        display_data = series.data * display.factor
        x_values, x_label = self._x_axis_values(series.time_s)
        is_datetime_axis = self.x_axis_combo.currentData() == "epoch" and x_label == "Epoch (UTC)"

        fig = go.Figure()
        column_labels = display.columns or {}
        for i, column in enumerate(series.columns):
            fig.add_trace(go.Scatter(
                x=x_values, y=display_data[:, i], mode="lines", name=column_labels.get(column, column),
                line=dict(color=_SERIES_COLORS[i % len(_SERIES_COLORS)], width=2),
            ))

        axis_common = dict(
            gridcolor=_GRID_COLOR, zerolinecolor=_GRID_COLOR, linecolor=_GRID_COLOR,
            tickfont=dict(color=_INK_MUTED), title_font=dict(color=_INK_MUTED),
        )
        y_title = f"{display.y_label} [{display.unit}]" if display.y_label else (f"[{display.unit}]" if display.unit else None)
        y_axis = dict(axis_common, title_text=y_title)
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

        subject = name.split(".", 1)[0]
        title_text = display.title if display.standalone_title else f"{subject}: {display.title}"
        fig.update_layout(
            title=dict(text=title_text, font=dict(size=16, color=_INK_PRIMARY, family=_FONT_FAMILY)),
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
