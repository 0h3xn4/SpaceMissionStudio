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

"""PhasingFormationDialog: collects a
:class:`engine.formation.PhasingFormationRequest` plus which existing
spacecraft to use as the chief (its orbit) and the template (every other
field) -- see that module's docstring for the Hill-frame math and why
only orbit/name/station_keeping/phasing_keeping vary.

Same "doesn't import the Basilisk-needing engine module beyond its
Basilisk-free request dataclass" split ``constellation_dialog.py`` already
uses -- ``engine.formation`` imports Basilisk lazily, at
``generate_phasing_follower()`` call time, not at module import time (see
that module's docstring), so importing ``PhasingFormationRequest`` here is
still safe without Basilisk installed; the ImportError (if Basilisk truly
isn't available) only surfaces when the caller actually clicks
Generate -- see ``spacecraft_editor.py``'s ``_on_generate_phasing_formation``.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from ..engine.formation import PhasingFormationRequest
from ..schema.scenario import ScenarioValidationError


def _double_spin(minimum: float, maximum: float, decimals: int, step: float, value: float) -> QDoubleSpinBox:
    box = QDoubleSpinBox()
    box.setRange(minimum, maximum)
    box.setDecimals(decimals)
    box.setSingleStep(step)
    box.setValue(value)
    return box


class PhasingFormationDialog(QDialog):
    """Modal "Generate phasing formation..." dialog. ``spacecraft_names``
    lists the scenario's current spacecraft (by name) -- the chief must be
    one of them (its orbit is read directly, not re-entered); the
    template (every OTHER field the new follower clones) defaults to the
    same spacecraft but may be any of them, same pattern as
    ``WalkerConstellationDialog``'s own template picker. ``central_body``
    is the scenario's ACTUAL current central body (read-only here, not a
    combo), same reasoning as that dialog's own central-body display.
    """

    def __init__(self, spacecraft_names: list[str], central_body: str = "earth", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Generate phasing formation")
        self._central_body = central_body

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Generates a new follower spacecraft that holds a target along-track separation from an "
            "existing chief spacecraft (schema.scenario.PhasingKeepingConfig), from a Radial/Transverse/"
            "Normal (Hill-frame) offset at epoch -- see the Radial/Cross-track fields' own tooltips for an "
            "important limitation. Added to (not replacing) this scenario's spacecraft list."
        ))

        form = QFormLayout()
        form.addRow("Central body (from this scenario)", QLabel(central_body))

        self.chief_combo = QComboBox()
        self.template_combo = QComboBox()
        if spacecraft_names:
            for name in spacecraft_names:
                self.chief_combo.addItem(name, userData=name)
                self.template_combo.addItem(name, userData=name)
        else:
            self.chief_combo.addItem("(no spacecraft in this scenario yet)", userData=None)
            self.chief_combo.setEnabled(False)
            self.template_combo.addItem("(no spacecraft in this scenario yet)", userData=None)
            self.template_combo.setEnabled(False)
        form.addRow("Chief spacecraft (orbit copied from here)", self.chief_combo)
        form.addRow("Template spacecraft (everything else copied from here)", self.template_combo)

        self.follower_name_edit = QLineEdit("follower-1")
        form.addRow("New follower name", self.follower_name_edit)

        self.radial_km = _double_spin(-10000.0, 10000.0, 3, 1.0, 0.0)
        self.radial_km.setToolTip(
            "Radial offset at epoch [km] -- outward along the chief's position vector. This is a STARTING "
            "geometry only: the active phasing controller does not hold radial separation, so this will "
            "drift over the run (see the dialog's own top note)."
        )
        self.along_track_km = _double_spin(-100000.0, 100000.0, 3, 1.0, 50.0)
        self.along_track_km.setToolTip(
            "Along-track offset at epoch [km] -- ahead of the chief along its velocity direction. This IS "
            "actively held: it becomes phasing_keeping.target_separation_km, the one separation component "
            "the controller maintains via along-track burns for the whole run."
        )
        self.cross_track_km = _double_spin(-10000.0, 10000.0, 3, 1.0, 0.0)
        self.cross_track_km.setToolTip(
            "Cross-track offset at epoch [km] -- along the chief's orbit-normal direction (out of its "
            "orbital plane). Same starting-geometry-only caveat as the radial offset above -- not actively "
            "held by the controller."
        )
        form.addRow("Radial (R) offset [km]", self.radial_km)
        form.addRow("Along-track (T) offset [km]", self.along_track_km)
        form.addRow("Cross-track (N) offset [km]", self.cross_track_km)

        self.thrust_n = _double_spin(1e-6, 1000.0, 6, 0.01, 0.05)
        self.isp_s = _double_spin(1.0, 1.0e5, 1, 10.0, 1500.0)
        self.propellant_kg = _double_spin(0.0, 1.0e6, 3, 1.0, 5.0)
        self.deadband_km = _double_spin(1e-6, 1.0e5, 3, 0.5, 2.0)
        form.addRow("Thruster thrust [N]", self.thrust_n)
        form.addRow("Thruster Isp [s]", self.isp_s)
        form.addRow("Propellant available [kg]", self.propellant_kg)
        form.addRow("Station-keeping deadband [km]", self.deadband_km)

        self.reconfiguration_interval_days = _double_spin(0.0, 1.0e5, 2, 1.0, 90.0)
        self.tolerance_fraction = _double_spin(1e-6, 10.0, 4, 0.01, 0.10)
        self.restore_tolerance_fraction = _double_spin(1e-6, 10.0, 4, 0.01, 0.02)
        self.correction_window_days = _double_spin(1e-3, 1.0e4, 2, 1.0, 21.0)
        self.max_drift_days = _double_spin(1e-3, 1.0e4, 2, 1.0, 90.0)
        self.max_delta_sma_km = _double_spin(1e-6, 1.0e4, 3, 0.5, 3.0)
        form.addRow("Reconfiguration interval [day]", self.reconfiguration_interval_days)
        form.addRow("Tolerance fraction [-]", self.tolerance_fraction)
        form.addRow("Restore tolerance fraction [-]", self.restore_tolerance_fraction)
        form.addRow("Correction window [day]", self.correction_window_days)
        form.addRow("Max drift [day]", self.max_drift_days)
        form.addRow("Max SMA offset [km]", self.max_delta_sma_km)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self) -> None:
        try:
            self.to_request()
        except ScenarioValidationError as exc:
            QMessageBox.critical(self, "Invalid phasing formation request", str(exc))
            return
        if self.selected_chief_name() is None:
            QMessageBox.critical(self, "No chief spacecraft",
                                  "Add at least one spacecraft to this scenario before generating a formation.")
            return
        self.accept()

    def to_request(self) -> PhasingFormationRequest:
        request = PhasingFormationRequest(
            chief_name=self.chief_combo.currentData() or "",
            follower_name=self.follower_name_edit.text().strip(),
            radial_km=self.radial_km.value(),
            along_track_km=self.along_track_km.value(),
            cross_track_km=self.cross_track_km.value(),
            reconfiguration_interval_days=self.reconfiguration_interval_days.value(),
            tolerance_fraction=self.tolerance_fraction.value(),
            restore_tolerance_fraction=self.restore_tolerance_fraction.value(),
            correction_window_days=self.correction_window_days.value(),
            max_drift_days=self.max_drift_days.value(),
            max_delta_semi_major_axis_km=self.max_delta_sma_km.value(),
            station_keeping_deadband_km=self.deadband_km.value(),
            thrust_n=self.thrust_n.value(),
            isp_s=self.isp_s.value(),
            propellant_kg=self.propellant_kg.value(),
        )
        request.validate()  # raises ScenarioValidationError with a specific message on anything bad
        return request

    def selected_chief_name(self) -> str | None:
        return self.chief_combo.currentData()

    def selected_template_name(self) -> str | None:
        return self.template_combo.currentData()
