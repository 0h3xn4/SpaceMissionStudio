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

"""ScenarioEditorWidget: the full scenario form, composing every
sub-editor into one :class:`schema.scenario.Scenario`. This is the single
place that assembles/disassembles a ``Scenario`` from widget state --
``MainWindow`` never touches individual fields itself.

Only edits what ``engine.service.SimulationService`` actually consumes
PLUS ground stations (pure scenario data, see
``ground_station_editor.py``'s docstring for why that's different from
sensors/actuators/FSW modes, which this editor deliberately omits).
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..schema.scenario import (
    GravityConfig,
    Scenario,
    ScenarioValidationError,
    SimSettings,
    SpaceWeatherConfig,
)
from .ground_station_editor import GroundStationListWidget
from .mission_sequence_editor import MissionSequenceEditorWidget
from .monte_carlo_editor import MonteCarloGroupWidget
from .spacecraft_editor import SpacecraftListWidget


class ScenarioEditorWidget(QWidget):
    """Emits :attr:`changed` on any edit anywhere in the form (including
    inside the spacecraft/ground-station dialogs), so :class:`MainWindow`
    can track an unsaved-changes flag and re-run live validation.
    """

    changed = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer_layout.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)
        layout = QVBoxLayout(content)

        layout.addWidget(self._build_identity_group())
        layout.addWidget(self._build_propagation_group())
        layout.addWidget(self._build_spacecraft_group())
        layout.addWidget(self._build_ground_station_group())
        layout.addWidget(self._build_mission_sequence_group())
        layout.addWidget(self._build_monte_carlo_group())
        layout.addStretch(1)

        self.validation_label = QLabel()
        self.validation_label.setWordWrap(True)
        outer_layout.addWidget(self.validation_label)

        self.changed.connect(self.revalidate)
        self.revalidate()

    # -- construction ------------------------------------------------------
    def _build_identity_group(self) -> QGroupBox:
        group = QGroupBox("Scenario")
        form = QFormLayout(group)
        self.name_edit = QLineEdit("new scenario")
        self.name_edit.textChanged.connect(self.changed)
        form.addRow("Name", self.name_edit)

        # First choice in the form, deliberately -- per the feature
        # request this responds to, simulation mode should be picked
        # "before starting with anything else". "Orbit only" is a
        # stricter, beginner-friendly mode: Scenario.validate() rejects
        # any spacecraft with fsw_mode/sensors/actuators/power set while
        # this is selected (see Scenario.simulation_mode's docstring) --
        # switching TO "Orbit only" on a scenario that already has those
        # set will make Save/Run fail with a specific error naming what to
        # remove, same "surface it, don't silently drop it" discipline as
        # everywhere else in this app.
        self.simulation_mode_combo = QComboBox()
        self.simulation_mode_combo.addItem("Full attitude (sensors, actuators, FSW, power)",
                                            userData="full_attitude")
        self.simulation_mode_combo.addItem("Orbit only (cannonball -- no attitude features)",
                                            userData="orbit_only")
        self.simulation_mode_combo.setToolTip(
            "Full attitude: sensors, actuators, FSW pointing/control, and power budgets are all available.\n"
            "Orbit only: a simpler cannonball spacecraft (drag_area_m2/srp_area_m2 as its average cross-section) "
            "for pure orbit-propagation questions (delta-V budgets, orbit lifetime, station-keeping cadence, ...) "
            "-- no sensors/actuators/FSW/power on any spacecraft in this mode."
        )
        self.simulation_mode_combo.currentIndexChanged.connect(self.changed)
        form.addRow("Simulation mode", self.simulation_mode_combo)

        self.epoch_edit = QLineEdit("2030-01-01T00:00:00")
        self.epoch_edit.setPlaceholderText("ISO 8601 UTC, e.g. 2030-01-01T00:00:00")
        self.epoch_edit.textChanged.connect(self.changed)
        form.addRow("Epoch (UTC)", self.epoch_edit)

        self.description_edit = QPlainTextEdit()
        # Was 60px (~2 lines) -- nowhere near enough for the built-in
        # template missions' own multi-paragraph descriptions (see
        # missionstudio/scenarios/templates/), which needed constant
        # scrolling just to read a few lines at a time. Tall enough to
        # show most of one of those at once without letting this one
        # field dominate the whole scenario form (Propagation setup/
        # Spacecraft/Ground stations/Mission sequence/Monte Carlo all
        # need their own visible room below it) -- it still scrolls
        # internally for anything longer, same as before, just far less
        # eagerly.
        self.description_edit.setFixedHeight(220)
        self.description_edit.textChanged.connect(self.changed)
        form.addRow("Description", self.description_edit)
        return group

    def _build_propagation_group(self) -> QGroupBox:
        """Gravity/perturbations, integrator/duration, and space weather
        all live in a dedicated :class:`PropagationSetupDialog` now (user
        feedback specifically asked for "a full and comprehensive
        propagate setup window" plus the ability to switch each
        perturbation on/off individually) -- this group box is just a
        read-only summary of the current settings plus the button that
        opens it. ``self._gravity``/``self._sim_settings``/
        ``self._space_weather`` are this widget's actual source of truth
        for those three dataclasses (mirroring how ``self.spacecraft_list``
        owns the spacecraft list); the dialog only ever replaces them
        wholesale, on OK.
        """
        self._gravity = GravityConfig()
        self._sim_settings = SimSettings()
        self._space_weather = SpaceWeatherConfig()

        group = QGroupBox("Propagation setup")
        layout = QVBoxLayout(group)
        # A labeled form (field name -> value), not a single free-text
        # line -- real user feedback, with a screenshot: three
        # pipe-joined, unlabeled lines ("earth | spherical harmonics
        # (degree 10) | +sun, moon") read as "cluttered" and "doesn't
        # help the user understand what those values stand for". Every
        # row label below is copied VERBATIM from PropagationSetupDialog's
        # own field labels (propagation_setup_dialog.py's form.addRow()
        # calls) -- this summary and the dialog that edits it now use
        # identical terminology, and the row/value-label QFormLayout
        # shape matches every other settings panel in this app
        # (spacecraft_editor.py, ground_station_editor.py, the dialog
        # itself), instead of being the one place that looked different.
        self._propagation_form = QFormLayout()
        self._propagation_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        layout.addLayout(self._propagation_form)
        edit_button = QPushButton("Edit Propagation Setup...")
        edit_button.clicked.connect(self._on_edit_propagation_setup)
        layout.addWidget(edit_button)
        self._refresh_propagation_summary()
        return group

    def _on_edit_propagation_setup(self) -> None:
        from .propagation_setup_dialog import PropagationSetupDialog

        dialog = PropagationSetupDialog(self._gravity, self._sim_settings, self._space_weather, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._gravity = dialog.to_gravity()
            self._sim_settings = dialog.to_sim_settings()
            self._space_weather = dialog.to_space_weather()
            self._refresh_propagation_summary()
            self.changed.emit()

    def _refresh_propagation_summary(self) -> None:
        gravity, sim, sw = self._gravity, self._sim_settings, self._space_weather

        while self._propagation_form.rowCount():
            self._propagation_form.removeRow(0)

        def add_row(label: str, value: str) -> None:
            value_label = QLabel(value)
            value_label.setWordWrap(True)
            self._propagation_form.addRow(label, value_label)

        add_row("Central body", gravity.central_body)
        add_row(
            "Gravity model",
            f"Spherical harmonics (degree {gravity.central_body_degree})"
            if gravity.central_body_degree > 0 else "Point-mass",
        )
        if gravity.third_body_perturbers:
            add_row("Third-body perturbers", ", ".join(gravity.third_body_perturbers))

        add_row("Integrator", sim.integrator)
        add_row("Dynamics task rate [s]", f"{sim.dynamics_task_rate_s:g}")
        add_row("Duration [days]", f"{sim.duration_days:g}")

        if sw.atmosphere_model == "exponential":
            add_row("Atmosphere model", "Exponential (no space weather)")
        else:
            add_row("Atmosphere model", "NRLMSISE-00")
            add_row("Space weather source", sw.source)
            add_row(
                "Drag margin",
                f"Conservative (P{sw.activity_percentile:g} historical worst-case)"
                if sw.activity_level == "conservative" else "Nominal",
            )

    def _build_spacecraft_group(self) -> QGroupBox:
        group = QGroupBox("Spacecraft")
        layout = QVBoxLayout(group)
        self.spacecraft_list = SpacecraftListWidget()
        self.spacecraft_list.set_central_body_provider(lambda: self._gravity.central_body)
        self.spacecraft_list.set_simulation_mode_provider(lambda: self.simulation_mode_combo.currentData())
        self.spacecraft_list.changed.connect(self.changed)
        self.spacecraft_list.changed.connect(self._refresh_monte_carlo_spacecraft_names)
        layout.addWidget(self.spacecraft_list)
        return group

    def _build_ground_station_group(self) -> QGroupBox:
        group = QGroupBox("Ground stations")
        layout = QVBoxLayout(group)
        self.ground_station_list = GroundStationListWidget()
        self.ground_station_list.changed.connect(self.changed)
        layout.addWidget(self.ground_station_list)
        return group

    def _build_mission_sequence_group(self) -> QGroupBox:
        group = QGroupBox("Mission sequence")
        layout = QVBoxLayout(group)
        self.mission_sequence_editor = MissionSequenceEditorWidget()
        self.mission_sequence_editor.set_spacecraft_names_provider(
            lambda: [sc.name for sc in self.spacecraft_list.to_list()]
        )
        self.mission_sequence_editor.changed.connect(self.changed)
        layout.addWidget(self.mission_sequence_editor)
        return group

    def _build_monte_carlo_group(self) -> MonteCarloGroupWidget:
        self.monte_carlo_group = MonteCarloGroupWidget()
        self.monte_carlo_group.changed.connect(self.changed)
        self._refresh_monte_carlo_spacecraft_names()
        return self.monte_carlo_group

    def _refresh_monte_carlo_spacecraft_names(self) -> None:
        self.monte_carlo_group.set_spacecraft_names([sc.name for sc in self.spacecraft_list.to_list()])

    # -- (dis)assembly -------------------------------------------------------
    def to_scenario(self) -> Scenario:
        """Raises :class:`ScenarioValidationError` with a specific message
        on anything invalid -- callers (Save, Run, the live-validation
        label) all go through this one method.
        """
        scenario = Scenario(
            name=self.name_edit.text().strip(),
            epoch_utc=self.epoch_edit.text().strip(),
            simulation_mode=self.simulation_mode_combo.currentData(),
            description=self.description_edit.toPlainText(),
            gravity=self._gravity,
            sim_settings=self._sim_settings,
            space_weather=self._space_weather,
            spacecraft=self.spacecraft_list.to_list(),
            ground_stations=self.ground_station_list.to_list(),
            monte_carlo=self.monte_carlo_group.to_dataclass(),
            mission_sequence=self.mission_sequence_editor.to_command_list(),
        )
        scenario.validate()
        return scenario

    def from_scenario(self, scenario: Scenario) -> None:
        self.name_edit.setText(scenario.name)
        self.epoch_edit.setText(scenario.epoch_utc)
        mode_index = self.simulation_mode_combo.findData(scenario.simulation_mode)
        if mode_index >= 0:
            self.simulation_mode_combo.setCurrentIndex(mode_index)
        self.description_edit.setPlainText(scenario.description)

        self._gravity = scenario.gravity
        self._sim_settings = scenario.sim_settings
        self._space_weather = scenario.space_weather
        self._refresh_propagation_summary()

        self.spacecraft_list.from_list(scenario.spacecraft)
        self.ground_station_list.from_list(scenario.ground_stations)
        self._refresh_monte_carlo_spacecraft_names()
        self.monte_carlo_group.from_dataclass(scenario.monte_carlo)
        self.mission_sequence_editor.from_command_list(scenario.mission_sequence)

        self.revalidate()

    def reset_to_default(self) -> None:
        self.from_scenario(Scenario(
            name="new scenario",
            epoch_utc="2030-01-01T00:00:00",
            spacecraft=[],
        ))

    def revalidate(self) -> None:
        try:
            self.to_scenario()
        except ScenarioValidationError as exc:
            self.validation_label.setText(f"⚠ {exc}")
            self.validation_label.setStyleSheet("color: #b00020;")
        else:
            self.validation_label.setText("✓ valid")
            self.validation_label.setStyleSheet("color: #1a7a1a;")
