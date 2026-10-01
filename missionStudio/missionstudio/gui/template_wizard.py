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

"""A guided, multi-step ``QWizard`` for customizing a bundled template
mission (``missionstudio/scenarios/templates/``) -- built in response to
a direct request that a user be able to "recreate the desired scenario
themselves or even tweak some parameters a little bit" from a template,
without first learning the full ``ScenarioEditorWidget`` form (every
field on every spacecraft/sensor/actuator/mission-sequence command).

Deliberately a CURATED subset, not a generic reflection of every
dataclass field: each :class:`TemplateWizardSpec` below exposes only the
handful of parameters that template's own ``description`` already calls
out under "Try changing:" (see ``scripts/_generate_templates.py``), each
with its own plain-language label/help text -- a focused, approachable
flow, not a second copy of the full editor. ``gui/load_scenario_widget.py``
only offers "Customize..." for a template with a registered spec here;
every other template still opens straight into the full editor via the
existing "Open Template" button, unchanged.

Scope (first pass, three representative templates -- see each spec's own
comment for why these three): '03' (GEO station-keeping, a simple
orbit-only scenario), '18' (LEO station-keeping, the same controller
shape but with an orbit-altitude knob that touches two dataclass fields
at once), and '07' (full attitude + hardware + power, the most complex
single-spacecraft template). Adding a fourth template's spec is just
another :class:`TemplateWizardSpec` entry in :data:`_SPECS` below -- the
wizard machinery itself (:class:`TemplateCustomizeWizard`) is already
generic over any spec.

The wizard operates on an in-memory COPY of the template's ``Scenario``
(via ``Scenario.from_dict(scenario.to_dict())``, the same round-trip
``tests/test_scenario_templates.py`` already trusts) -- the original
template file on disk is never touched, matching how "Open Template"
itself already behaves (templates are read-only starting points, saved
elsewhere via File > Save As). ``result_scenario()`` returns that copy
with every page's values applied; the caller (``MainWindow``) is
responsible for validating it and opening it in the full editor (see
``gui/main_window.py``'s ``_on_load_scenario_customized``) -- the exact
same "hand off a Scenario, let the one real editor own validation/save"
split every other GUI-vs-schema boundary in this app already uses.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from PySide6.QtWidgets import QDoubleSpinBox, QFormLayout, QLabel, QWizard, QWizardPage

from ..schema.scenario import Scenario

# SpacecraftConfig.orbit.semi_major_axis_km (OrbitIC, "classical_elements")
# is measured from the central body's CENTER, while
# StationKeepingConfig.target_altitude_km is measured from its surface --
# the same relationship scripts/_generate_templates.py's own '03'/'18'
# builders use (e.g. 400.0 target_altitude_km + 6378.0 = 6778.0
# semi_major_axis_km), reproduced here so '18's altitude field can move
# both in lockstep. Earth-specific; fine for this first pass (every
# current station_keeping template is Earth-centered) -- a non-Earth
# central body would need this generalized if a future template needs it.
_EARTH_RADIUS_KM = 6378.137


@dataclass(frozen=True)
class WizardField:
    """One spin-box on one wizard page. ``get``/``set`` close over
    whichever dataclass field(s) this knob actually represents -- some
    are a single ``SpacecraftConfig`` attribute, others (like '18's
    altitude, above) touch more than one field together so the Scenario
    never passes through an inconsistent intermediate state.
    """

    label: str
    help_text: str
    get: Callable[[Scenario], float]
    set: Callable[[Scenario, float], None]
    minimum: float
    maximum: float
    decimals: int = 3
    step: float = 1.0
    suffix: str = ""


@dataclass(frozen=True)
class WizardPageSpec:
    title: str
    intro: str
    fields: List[WizardField]


@dataclass(frozen=True)
class TemplateWizardSpec:
    template_filename: str
    pages: List[WizardPageSpec]


def _sc(scenario: Scenario):
    """Every current wizard spec is single-spacecraft -- this is the one
    place that assumption lives, so a future multi-spacecraft template's
    spec would only need its own get/set closures, not a change here.
    """
    return scenario.spacecraft[0]


def _rw_max_momentum(scenario: Scenario) -> float:
    return float(_sc(scenario).actuators[0].params["maxMomentum"])


def _set_rw_max_momentum(scenario: Scenario, value: float) -> None:
    # Applied uniformly to every reaction wheel -- '07's own three wheels
    # are built symmetrically (orthogonal spin axes, identical
    # maxMomentum), and keeping them identical here avoids the wizard
    # silently creating an asymmetric wheel set a user never asked for.
    for actuator in _sc(scenario).actuators:
        if actuator.kind == "reaction_wheel":
            actuator.params["maxMomentum"] = value


def _leo_altitude_km(scenario: Scenario) -> float:
    return float(_sc(scenario).station_keeping.target_altitude_km)


def _set_leo_altitude_km(scenario: Scenario, value: float) -> None:
    sc = _sc(scenario)
    sc.station_keeping.target_altitude_km = value
    sc.orbit.semi_major_axis_km = value + _EARTH_RADIUS_KM


_SPECS: Dict[str, TemplateWizardSpec] = {
    "03_geo_station_keeping.json": TemplateWizardSpec(
        template_filename="03_geo_station_keeping.json",
        pages=[
            WizardPageSpec(
                title="Station-keeping controller",
                intro="How aggressively the deadband thruster corrects GEO drift.",
                fields=[
                    WizardField(
                        "Deadband", "How far the satellite may drift from target altitude before a "
                        "correction burn starts -- tighter means more frequent, smaller burns.",
                        lambda s: _sc(s).station_keeping.deadband_km,
                        lambda s, v: setattr(_sc(s).station_keeping, "deadband_km", v),
                        0.1, 500.0, decimals=2, step=0.5, suffix=" km",
                    ),
                    WizardField(
                        "Thrust", "The station-keeping thruster's thrust magnitude.",
                        lambda s: _sc(s).station_keeping.thrust_n,
                        lambda s, v: setattr(_sc(s).station_keeping, "thrust_n", v),
                        0.001, 10.0, decimals=3, step=0.05, suffix=" N",
                    ),
                    WizardField(
                        "Specific impulse", "Thruster efficiency -- higher uses less propellant per "
                        "unit of delta-V.",
                        lambda s: _sc(s).station_keeping.isp_s,
                        lambda s, v: setattr(_sc(s).station_keeping, "isp_s", v),
                        50.0, 5000.0, decimals=0, step=50.0, suffix=" s",
                    ),
                    WizardField(
                        "Propellant budget", "Total propellant available for station-keeping over the run.",
                        lambda s: _sc(s).station_keeping.propellant_kg,
                        lambda s, v: setattr(_sc(s).station_keeping, "propellant_kg", v),
                        0.1, 1000.0, decimals=2, step=5.0, suffix=" kg",
                    ),
                ],
            ),
            WizardPageSpec(
                title="Simulation length",
                intro="How long to propagate -- longer runs show more (or, with a wide enough "
                      "deadband, possibly zero) correction burns.",
                fields=[
                    WizardField(
                        "Duration", "Total simulated time.",
                        lambda s: s.sim_settings.duration_days,
                        lambda s, v: setattr(s.sim_settings, "duration_days", v),
                        0.1, 3650.0, decimals=2, step=1.0, suffix=" days",
                    ),
                ],
            ),
        ],
    ),
    "18_leo_station_keeping.json": TemplateWizardSpec(
        template_filename="18_leo_station_keeping.json",
        pages=[
            WizardPageSpec(
                title="Orbit altitude",
                intro="Lower altitude means thicker atmosphere means faster drag decay means more "
                      "frequent corrections -- the single biggest knob for this template.",
                fields=[
                    WizardField(
                        "Altitude", "Target (and starting) altitude above the Earth's surface.",
                        _leo_altitude_km, _set_leo_altitude_km,
                        200.0, 2000.0, decimals=1, step=10.0, suffix=" km",
                    ),
                ],
            ),
            WizardPageSpec(
                title="Spacecraft drag properties",
                intro="How much drag force the satellite's own shape/mass produces.",
                fields=[
                    WizardField(
                        "Drag area", "Cross-sectional area exposed to the atmosphere.",
                        lambda s: _sc(s).drag_area_m2,
                        lambda s, v: setattr(_sc(s), "drag_area_m2", v),
                        0.01, 100.0, decimals=2, step=0.1, suffix=" m^2",
                    ),
                    WizardField(
                        "Drag coefficient", "A dimensionless shape factor -- most satellites fall "
                        "between about 2.0 and 2.5.",
                        lambda s: _sc(s).drag_coeff,
                        lambda s, v: setattr(_sc(s), "drag_coeff", v),
                        1.0, 4.0, decimals=2, step=0.1,
                    ),
                ],
            ),
            WizardPageSpec(
                title="Station-keeping controller",
                intro="How aggressively the deadband thruster corrects altitude decay.",
                fields=[
                    WizardField(
                        "Deadband", "How far the satellite may decay below target altitude before a "
                        "correction burn starts -- tighter means more frequent, smaller burns.",
                        lambda s: _sc(s).station_keeping.deadband_km,
                        lambda s, v: setattr(_sc(s).station_keeping, "deadband_km", v),
                        0.05, 50.0, decimals=2, step=0.1, suffix=" km",
                    ),
                    WizardField(
                        "Thrust", "The station-keeping thruster's thrust magnitude.",
                        lambda s: _sc(s).station_keeping.thrust_n,
                        lambda s, v: setattr(_sc(s).station_keeping, "thrust_n", v),
                        0.001, 10.0, decimals=3, step=0.01, suffix=" N",
                    ),
                    WizardField(
                        "Specific impulse", "Thruster efficiency -- higher uses less propellant per "
                        "unit of delta-V.",
                        lambda s: _sc(s).station_keeping.isp_s,
                        lambda s, v: setattr(_sc(s).station_keeping, "isp_s", v),
                        50.0, 5000.0, decimals=0, step=50.0, suffix=" s",
                    ),
                    WizardField(
                        "Propellant budget", "Total propellant available for station-keeping over the run.",
                        lambda s: _sc(s).station_keeping.propellant_kg,
                        lambda s, v: setattr(_sc(s).station_keeping, "propellant_kg", v),
                        0.01, 100.0, decimals=2, step=0.1, suffix=" kg",
                    ),
                ],
            ),
            WizardPageSpec(
                title="Simulation length",
                intro="How long to propagate -- longer runs at low altitude show faster cumulative decay.",
                fields=[
                    WizardField(
                        "Duration", "Total simulated time.",
                        lambda s: s.sim_settings.duration_days,
                        lambda s, v: setattr(s.sim_settings, "duration_days", v),
                        0.1, 365.0, decimals=2, step=1.0, suffix=" days",
                    ),
                ],
            ),
        ],
    ),
    "07_attitude_pointing_with_adcs_hardware.json": TemplateWizardSpec(
        template_filename="07_attitude_pointing_with_adcs_hardware.json",
        pages=[
            WizardPageSpec(
                title="Reaction wheels",
                intro="Applied to all three (identical, orthogonal-axis) wheels together.",
                fields=[
                    WizardField(
                        "Max momentum", "Each wheel's momentum storage capacity before it saturates "
                        "and needs desaturating.",
                        _rw_max_momentum, _set_rw_max_momentum,
                        1.0, 1000.0, decimals=1, step=10.0, suffix=" N*m*s",
                    ),
                ],
            ),
            WizardPageSpec(
                title="Power budget",
                intro="The solar array and battery backing this spacecraft's power draw.",
                fields=[
                    WizardField(
                        "Panel area", "Total solar panel area.",
                        lambda s: _sc(s).power.panel_area_m2,
                        lambda s, v: setattr(_sc(s).power, "panel_area_m2", v),
                        0.01, 50.0, decimals=2, step=0.1, suffix=" m^2",
                    ),
                    WizardField(
                        "Battery capacity", "Total energy storage.",
                        lambda s: _sc(s).power.battery_capacity_wh,
                        lambda s, v: setattr(_sc(s).power, "battery_capacity_wh", v),
                        1.0, 10000.0, decimals=1, step=10.0, suffix=" W*hr",
                    ),
                ],
            ),
            WizardPageSpec(
                title="Simulation length",
                intro="How long to propagate.",
                fields=[
                    WizardField(
                        "Duration", "Total simulated time.",
                        lambda s: s.sim_settings.duration_days,
                        lambda s, v: setattr(s.sim_settings, "duration_days", v),
                        0.001, 365.0, decimals=4, step=0.01, suffix=" days",
                    ),
                ],
            ),
        ],
    ),
}


def get_wizard_spec(template_filename: str) -> Optional[TemplateWizardSpec]:
    """``None`` means this template has no curated wizard yet -- callers
    (``LoadScenarioWidget``) fall back to the plain "Open Template" flow,
    exactly as they did before this feature existed.
    """
    return _SPECS.get(template_filename)


class _WizardFieldPage(QWizardPage):
    def __init__(self, page_spec: WizardPageSpec, scenario: Scenario, parent=None):
        super().__init__(parent)
        self.setTitle(page_spec.title)
        self._scenario = scenario
        self._fields = page_spec.fields
        self._boxes: List[QDoubleSpinBox] = []

        layout = QFormLayout(self)
        intro = QLabel(page_spec.intro)
        intro.setWordWrap(True)
        layout.addRow(intro)

        for field_spec in self._fields:
            box = QDoubleSpinBox()
            box.setRange(field_spec.minimum, field_spec.maximum)
            box.setDecimals(field_spec.decimals)
            box.setSingleStep(field_spec.step)
            box.setSuffix(field_spec.suffix)
            box.setValue(field_spec.get(scenario))
            box.setToolTip(field_spec.help_text)
            help_label = QLabel(field_spec.help_text)
            help_label.setWordWrap(True)
            help_label.setStyleSheet("color: palette(mid); font-size: 90%;")
            layout.addRow(field_spec.label, box)
            layout.addRow("", help_label)
            self._boxes.append(box)

    def apply_to_scenario(self) -> None:
        """Writes every spin box's current value back into the Scenario
        this page was built from -- called on Finish (see
        TemplateCustomizeWizard.accept()), not live on every edit, so an
        in-progress Back/Next doesn't matter.
        """
        for field_spec, box in zip(self._fields, self._boxes):
            field_spec.set(self._scenario, box.value())


class TemplateCustomizeWizard(QWizard):
    """One page per :class:`WizardPageSpec` in ``spec.pages``, built from
    a COPY of ``base_scenario`` (see this module's own docstring for why
    a copy) -- call :meth:`result_scenario` after ``exec()`` returns
    ``QDialog.Accepted`` to get the customized ``Scenario``.
    """

    def __init__(self, base_scenario: Scenario, spec: TemplateWizardSpec, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Customize: {base_scenario.name}")
        self._scenario = Scenario.from_dict(base_scenario.to_dict())
        self._field_pages: List[_WizardFieldPage] = []
        for page_spec in spec.pages:
            page = _WizardFieldPage(page_spec, self._scenario, self)
            self._field_pages.append(page)
            self.addPage(page)

    def accept(self) -> None:
        for page in self._field_pages:
            page.apply_to_scenario()
        super().accept()

    def result_scenario(self) -> Scenario:
        return self._scenario
