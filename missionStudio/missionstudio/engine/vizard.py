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

r"""
Vizard integration: satisfies the user's explicit "no embedded 3D viewer is
okay, as long as you ... provide good Vizard visualization with valuable
'live simulation data'" requirement.

Vizard is a separate, precompiled Unity application -- it cannot be
embedded in a Qt window (confirmed during the pre-Phase-0 capability audit;
see missionStudio/README.md), so this module wraps Basilisk's own
``vizSupport.enableUnityVisualization()``, which either streams live to a
running Vizard instance over TCP (``liveStream=True`` -- the user launches
Vizard themselves and this app just feeds it) or writes a ``.bin``
playback file Vizard opens afterward (``saveFile=...``). Both modes are
native Basilisk functionality; nothing here reimplements or emulates
Vizard's rendering.

"Live simulation data", concretely, for what ``engine.service`` actually
wires up in Phase 2:

* Reaction wheel speeds/torques -- passed via ``rwEffectorList``, which
  makes Vizard draw its native per-wheel speed/torque bars. Only present
  for spacecraft with ``"reaction_wheel"`` actuators (see ``engine.fsw``);
  ``None`` otherwise, matching ``enableUnityVisualization``'s own
  ``ensure_correct_len_list`` handling of a per-spacecraft ``None`` entry.
* Ground stations -- drawn via ``vizSupport.addLocation`` (lat/lon/alt,
  field of view, minimum-elevation cone) for every
  :class:`schema.scenario.GroundStationConfig`, so the access geometry
  ``locationPointing``/``groundLocation`` compute is actually visible in
  Vizard, not just in a CSV.
* Attitude, position, and (natively, always) eclipse/sun-direction
  indication come from ``enableUnityVisualization``'s own per-spacecraft
  state message wiring -- no extra work needed here.

Thruster plumes (``thrEffectorList``) are NOT passed: Phase 2 does not
wire up thruster actuators (see ``engine.fsw``'s module docstring), so
there is nothing to visualize there yet.

Default camera / orbit-line view (fixed after user feedback that Vizard
opened locked onto the spacecraft with no context -- "improve" per that
feedback, since a viewer that opens on an unrecognizable close-up isn't
"understandable live data" no matter what panels are attached to it)
-------------------------------------------------------------------------
``enableUnityVisualization()`` on its own does not configure the VIEWER's
starting camera or orbit-trace lines at all -- those are separate fields
on the ``VizSettings`` message it creates (``viz.settings``), read
directly from ``src/simulation/vizard/_GeneralModuleFiles/vizStructures.h``
in this checkout (not guessed): ``mainCameraTarget`` ("if a valid
spacecraft or celestial body name is provided, the main camera will be
targeted at that body at start"), ``orbitLinesOn``/``trueTrajectoryLinesOn``
(osculating/true orbit trace lines, off by default), and the
``show*Labels`` flags. Left unset, Vizard falls back to its own built-in
default, which is a spacecraft-locked view with no orbit trace -- exactly
the complaint. :func:`enable_vizard` now sets these explicitly: camera
targeted at the central body (an Earth-centered view with the orbit
tracing around it, matching STK/GMAT/FreeFlyer's default framing) unless
:attr:`VizardRequest.camera_target` names something else (a specific
spacecraft, to watch it up close, or another body), plus both orbit-trace
line types and spacecraft/body labels on.

Verification status: ``vizSupport.enableUnityVisualization``'s signature
and ``addLocation``'s signature were read directly from
``src/utilities/vizSupport.py`` in this checkout (not assumed); the
``rwEffectorList``/``saveFile``/``liveStream`` usage pattern matches
``examples/scenarioAttitudeFeedbackRW.py``. The ``VizSettings`` fields
this module now sets were confirmed to exist under these exact names by
reading ``vizStructures.h`` directly; a real user's own running Vizard
instance (a screenshot of the ``05_formation_flying_phasing`` template)
has since confirmed the camera/orbit-line/spacecraft-label behavior
documented here matches exactly what was intended -- this development
sandbox itself still has no display to confirm rendered results with,
but that specific gap is now closed by a real report, not left assumed.

Live-data panels (fixed after user feedback that the live Vizard stream
wasn't "understandable" -- a moving dot with no other readout doesn't
answer "is the battery draining, is the tank running dry, is this pass
actually in contact with the ground")
-------------------------------------------------------------------------
Three more ``VizSettings``/``vizInterface`` structures, all populated from
REAL, already-simulated messages (nothing here is a static snapshot or an
analytical estimate -- see each source module's own docstring):

* **Battery state of charge** -- a Vizard ``GenericStorage`` bar panel per
  spacecraft with ``PowerConfig`` configured, wired directly to that
  spacecraft's ``simpleBattery.SimpleBattery.batPowerOutMsg``
  (``engine.service``). Pattern copied from
  ``examples/MultiSatBskSim/scenariosMultiSat/scenario_StationKeepingMultiSat.py``
  (a real, shipped Basilisk example -- not guessed).
* **Station-keeping propellant remaining** -- a second ``GenericStorage``
  panel per spacecraft with ``StationKeepingConfig`` configured, wired to
  ``engine.orbit_maintenance.StationKeepingController.fuelTankOutMsg`` (a
  real ``FuelTankMsgPayload`` that controller publishes specifically for
  this -- see its own module docstring). Same example's pattern for the
  "Tank" panel.
* **Delta-V used** -- one more ``GenericStorage`` panel per spacecraft
  with ``StationKeepingConfig`` configured (station-keeping delta-V,
  ``StationKeepingController.deltaVOutMsg``), plus, for a spacecraft that
  ALSO has ``PhasingKeepingConfig`` configured, two more:
  ``PhasingKeepingController.deltaVOutMsg`` (phasing delta-V, kept as a
  SEPARATE panel from station-keeping's own -- see that controller's
  docstring for why: both draw from the one shared tank, but reporting
  them separately shows the propellant cost of altitude-keeping and
  phasing-keeping individually) and ``...separationOutMsg`` (the live
  along-track separation from the chief, against the currently-scheduled
  target -- "is the formation actually holding", arguably the single most
  relevant live number for a phasing/formation-flying scenario). All
  three are real ``DataStorageStatusMsgPayload`` messages those
  controllers publish specifically for this (again, see their own module
  docstring) -- deliberately not a second ``FuelTankMsgPayload`` reuse, so
  the propellant and delta-V/separation panels are never racing to
  overwrite the same message.
* **Live numeric values, on every panel above** -- a real Vizard
  screenshot (from an actual user, not this project's own -- no display
  in this development sandbox) showed every ``GenericStorage`` bar's
  ``label`` text as static (e.g. "Propellant"), never the live number
  itself, leaving the bar's fill fraction as the only "how much"
  indicator. :func:`enable_vizard` now attaches one small
  ``_LiveValueLabelBridge`` ``SysModel`` per panel (same locally-defined
  -inside-this-function, kept-alive-via-the-returned-list pattern as
  ``_AccessIndicatorBridge`` above) that rewrites that panel's own
  ``label`` every tick to ``"<name>: <current>/<max> <units>"``, so the
  same screenshot's static caption becomes a live readout instead.
  **Also fixes a real, screenshot-confirmed bug**: the separation panel's
  ``storageCapacity`` used to equal the along-track TARGET itself, so
  normal, on-target operation already sat at ~100% fill with no headroom
  before an ordinary correction transient pushed ``storageLevel`` past
  ``storageCapacity`` -- which rendered as a bar overflowing its own
  panel, full window width, in that same screenshot.
  ``PhasingKeepingController`` now gives that gauge 2x the target as
  headroom and clamps what it actually writes to ``separationOutMsg``
  (see that class's own docstring); the live-value label above still
  shows the TRUE, unclamped separation (``lastSeparationKm``), so nothing
  is hidden, only the bar's own fill is kept from visually breaking.
* **Ground-station access windows** -- one ``GenericSensor`` marker per
  (ground station, spacecraft) pair that Phase 3's access analysis tracks,
  changing color LIVE between "no access" and "access" as
  ``groundLocation.GroundLocation``'s already-computed ``hasAccess`` flag
  changes each tick. ``GenericSensor`` has no boolean/message-driven color
  input on its own -- it takes an integer "mode" via a
  ``DeviceCmdMsgPayload``, so :func:`enable_vizard` adds one small bridge
  ``SysModel`` per pair (defined locally inside this function, not at
  module scope, to keep this module's own Basilisk import lazy -- see
  below) that republishes ``AccessMsgPayload.hasAccess`` as that command
  value. Per ``GenericSensor``'s own field comment in ``vizStructures.h``
  ("Modes 0 and 1 will use the 0th color, Mode 2 will use the color
  indexed to 1"), the bridge commands 0 for no-access and 2 (not 1) for
  access, so the two colors actually differ. This marker's position/
  boresight (``r_SB_B``/``normalVector``) is a placeholder (body origin,
  +X) since neither the schema nor Basilisk's ``groundLocation`` model a
  real antenna mounting direction -- it is a status indicator, not an
  antenna visualization (compare ``Transceiver``/comm-ring visualization,
  which needs a real data-node system this project does not have -- see
  ``PowerConfig``'s docstring on scope).

None of this feeds back into simulated physics or the exported CSV/plot
data -- ``engine.service.run()`` already reports the same battery/
propellant/access numbers there; this only makes them visible live in
Vizard too.

Verification status: the ``GenericStorage``/battery+fuel-tank wiring
matches a real, shipped multi-satellite Basilisk example line-for-line
(cited above), AND has since been confirmed rendering correctly against
a real running Vizard instance (the same screenshot cited above --
"Propellant"/"Delta-V"/"Separation" panels all visible and updating).
The ``GenericSensor``/``DeviceCmdMsgPayload``/bridge-module wiring
matches the field-level pattern in a second real shipped example
(``examples/scenarioGroundLocationImaging.py``), but the specific
"republish an access flag as a sensor mode" composition is this module's
own, not copied from an example verbatim, and -- unlike the
``GenericStorage`` panels above -- has NOT yet been confirmed against a
real running Vizard instance (that screenshot's scenario had no ground
stations configured).

**Real bug found on first actual run** (reported: ``basic_string::_M_create``,
a C++ ``std::length_error``, thrown well after setup completed, during an
otherwise-unrelated-looking string operation): every
``_AccessIndicatorBridge`` instance this function created was referenced
ONLY by a local loop variable -- ``engine.service`` discarded this
function's return value entirely, so nothing kept those Python objects
(or ``viz`` itself) alive past this function returning. Unlike the plain
-data ``vizInterface`` structs (``GenericStorage``/``GenericSensor``,
whose relevant state ``enableUnityVisualization()`` copies into its own
C++ containers), ``_AccessIndicatorBridge`` is a custom Python
``SysModel`` with virtual ``UpdateState``/``Reset`` methods Basilisk calls
back into via a SWIG director -- letting the Python side of that get
garbage-collected while the C++ side is still task-registered is
undefined behavior, and heap corruption manifesting later as an unrelated
string-construction crash is a textbook symptom. Every OTHER custom
Python ``SysModel`` in this codebase (this module's own
``StationKeepingController``/``PhasingKeepingController``,
``../missionAnalysis``'s ``PowerLoadGate``/``InstrumentEclipseGate``) is
deliberately kept alive by its caller storing the returned object
somewhere persistent; this bridge class was the one place that pattern
was broken.

First fix attempt -- also broken, caught on the next real run: attaching
every bridge instance to ``viz`` itself as ``viz._missionstudio_access_
indicator_bridges``. ``viz`` is a SWIG proxy for a C++ ``VizInterface``,
and SWIG-generated proxy classes raise (not silently ignore) an attempt
to set any attribute they don't already know about -- confirmed against
a real run, which failed immediately with "You tried to add this
variable: _missionstudio_access_indicator_bridges To this class:
<...VizInterface ...>" before a single simulation step ran. Fixed for
real by returning ``access_indicator_bridges`` alongside ``viz`` instead
of bolting it onto ``viz`` (see :func:`enable_vizard`'s own Returns
docs) and having ``engine.service`` retain BOTH (previously just
``viz``, and before that, neither) as plain attributes of its own
``SimulationService`` instance -- an ordinary Python object with no such
restriction -- for that instance's lifetime.

**Same bug found again, second occurrence, this time in GenericStorage**
(reported: same ``basic_string::_M_create``/``std::length_error``
signature as above, this time thrown from ``VizInterface::WriteProtobuffer()``
-> ``google::protobuf::internal::ArenaStringPtr::Set()`` on VizInterface's
own background write thread -- confirmed with a real ``gdb``
``catch throw``/``bt`` on an otherwise-clean, fully-isolated repro: a
station-keeping-only scenario, headless CLI, no live Vizard connection,
just ``--vizard-save-file``). The paragraph above's claim that
``GenericStorage``/``GenericSensor`` don't need this same retention --
because their "relevant state is copied into Basilisk's own C++
containers by ``enableUnityVisualization()``" -- was never actually
verified against ``vizStructures.h`` and turned out to be wrong:
``VizSpacecraftData::genericStorageList``/``genericSensorList`` are
``std::vector<GenericStorage *>``/``std::vector<GenericSensor *>`` --
POINTER vectors, not value vectors. ``enableUnityVisualization()`` only
stores the pointers it's handed; it does not clone the pointed-to
structs. The ``panel``/``sensor`` objects built in the loop below (and
their embedded ``tank_reader``/``battery_reader``/``cmd_reader``
``ReadFunctor``s) were local variables, never returned, never retained
by ``engine.service`` -- garbage-collected the moment this function
returned, while ``VizInterface`` kept dangling pointers to them and
dereferenced one every tick in ``WriteProtobuffer()``, eventually
reading freed/reused memory as a corrupt string length. Only
spacecraft with a ``GenericStorage``/``GenericSensor`` panel (i.e. only
``station_keeping``/ground-station-access scenarios -- never
``constant_thrust``, which creates no panel at all) can hit this,
which is exactly the split a long real-repro investigation across
several scenario variants eventually converged on before this was
found. Fixed the same way as the bridge fix: ``generic_storage_list``/
``generic_sensor_list`` (built below, parallel per-spacecraft lists)
are now returned alongside ``viz``/``access_indicator_bridges`` (see
:func:`enable_vizard`'s own Returns docs) and ``engine.service`` retains
all four for the ``SimulationService`` instance's lifetime.

**Real UX bug found from a real running Vizard screenshot** (a genuine
user report, not this project's own repro -- the FIRST real look at any
of this module's panels actually rendered): the phasing-formation
"Separation from chief" ``GenericStorage`` bar rendered broken --
overflowing its own panel box, full window width, unlike the compact
"Propellant"/"Delta-V" bars right next to it in the same screenshot.
Root cause: that panel's ``storageCapacity`` was set to the along-track
TARGET separation itself, so ordinary, ON-TARGET holding already sat at
~100% fill with zero headroom, and a real correction transient (this
project's own manual repro, once alerted to look: a fresh scenario's
initial along-track mismatch, well before the controller has converged)
pushed ``storageLevel`` well past ``storageCapacity`` -- confirmed
directly against a real Basilisk run, not just theorized: a 600 s manual
repro read back ``storageLevel`` at over 4x ``storageCapacity`` before
the fix. Vizard does not appear to clamp an overflowing bar itself.
Fixed in ``engine.orbit_maintenance.PhasingKeepingController.UpdateState``:
the gauge now gets 2x the target as headroom, and the value actually
WRITTEN to ``separationOutMsg`` is clamped to that capacity (``min()``,
confirmed against the same manual repro to now read exactly at the
capacity rather than 4x it) -- the true, unclamped number is kept
separately (``lastSeparationKm``/``lastTargetSeparationKm``, plain
Python attributes) for the live-value label below to still show.
Same screenshot surfaced a second, unrelated gap: every panel's ``label``
was static text (e.g. "Propellant"), never the live number itself --
fixed by :class:`_LiveValueLabelBridge` below, which rewrites each
panel's ``label`` every tick to embed its current/max value as visible
text (confirmed, via the same manual repro, to read e.g.
``"Propellant: 5.00/5.00 kg"`` after a real run, not just the static
caption).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


class VizardError(Exception):
    """Raised when Vizard support (``vizSupport``/``vizInterface``) cannot
    be set up -- carries the specific underlying error, not a bare
    traceback.
    """


@dataclass
class VizardRequest:
    """What the GUI/CLI ask for. Exactly one of ``save_file``/``live_stream``
    should be set -- see :func:`enable_vizard`.
    """

    save_file: Optional[str] = None  # path for a .bin playback file Vizard opens after the run
    live_stream: bool = False  # stream live to a Vizard instance already running on this machine
    # Name of the spacecraft or celestial body Vizard's main camera starts
    # targeted at. None (the default) targets the scenario's central body --
    # an Earth-centered view with the orbit tracing around it, matching
    # STK/GMAT/FreeFlyer's default framing, rather than a spacecraft-locked
    # close-up. Set this to a spacecraft name to start zoomed in on it instead.
    camera_target: Optional[str] = None
    # Draw osculating + true orbit-trace lines so the orbit path is visible,
    # not just a moving dot. On by default for the same "understandable at a
    # glance" reason as camera_target.
    show_orbit_lines: bool = True


def enable_vizard(scSim, task_name: str, sc_objects: List, request: VizardRequest,
                   rw_effectors_by_spacecraft: Optional[List] = None,
                   ground_stations: Optional[Dict[str, object]] = None,
                   central_body_name: str = "earth",
                   battery_by_spacecraft: Optional[Dict[str, object]] = None,
                   station_keeping_by_spacecraft: Optional[Dict[str, object]] = None,
                   phasing_keeping_by_spacecraft: Optional[Dict[str, object]] = None,
                   access_out_msgs: Optional[Dict[tuple, object]] = None,
                   custom_models_by_spacecraft: Optional[Dict[str, dict]] = None):
    """Call once, after every spacecraft/sensor/actuator/FSW module for
    this run has been added to ``scSim`` and BEFORE ``InitializeSimulation()``
    (matches every ``vizSupport.enableUnityVisualization`` call site in
    this checkout's own examples).

    Returns:
        ``(viz, access_indicator_bridges, generic_storage_list, generic_sensor_list, label_bridges)``
        -- the ``vizInterface.VizInterface`` instance
        ``vizSupport.enableUnityVisualization()`` built; the (possibly
        empty) list of ``_AccessIndicatorBridge`` ``SysModel`` instances
        this function registered on ``scSim``'s task; the per-spacecraft
        ``GenericStorage``/``GenericSensor`` panel lists (each entry
        ``None`` or a list, parallel to ``sc_objects``) this function
        built and handed to ``enableUnityVisualization()``; and the
        (possibly empty) list of ``_LiveValueLabelBridge`` ``SysModel``
        instances that keep each ``GenericStorage`` panel's ``label``
        showing its live current/max value as text (see "Live-data
        panels" below). The caller MUST keep ALL FIVE alive (e.g. as
        attributes on a long-lived object) for as long as the simulation
        runs -- see ``access_indicator_bridges``' own comment below,
        which turned out to apply to
        ``generic_storage_list``/``generic_sensor_list`` too (see the
        "Real bug found" note below, second occurrence), and applies to
        ``label_bridges`` for the exact same reason
        ``access_indicator_bridges`` needs it in the first place (a
        custom Python ``SysModel`` with virtual methods Basilisk calls
        back into via a SWIG director).

    Args:
        sc_objects: every ``spacecraft.Spacecraft`` in this run, in the
            same order as ``rw_effectors_by_spacecraft`` if given.
        rw_effectors_by_spacecraft: one ``reactionWheelStateEffector.ReactionWheelStateEffector``
            (or ``None``) per entry in ``sc_objects`` -- see module
            docstring.
        ground_stations: ``{name: groundLocation.GroundLocation}`` for
            every ``GroundStationConfig`` already built for this scenario.
        battery_by_spacecraft: ``{spacecraft_name: simpleBattery.SimpleBattery}``
            for every spacecraft with ``PowerConfig`` set -- see module
            docstring's "Live-data panels" section.
        station_keeping_by_spacecraft: ``{spacecraft_name: engine.orbit_maintenance.StationKeepingController}``
            for every spacecraft with ``StationKeepingConfig`` set -- same
            section.
        phasing_keeping_by_spacecraft: ``{spacecraft_name: engine.orbit_maintenance.PhasingKeepingController}``
            for every spacecraft with ``PhasingKeepingConfig`` set -- same
            section.
        access_out_msgs: ``{(ground_station_name, spacecraft_name): groundLocation.accessOutMsgs[i]}``
            for every station/spacecraft pair Phase 3's access analysis
            tracks (``engine.service``'s own ``_access_out_msgs``) -- same
            section.
        custom_models_by_spacecraft: ``{spacecraft_name: {"path": str, "offset_m": [x,y,z],
            "rotation_deg": [z,y,x], "scale": [x,y,z]}}`` for every spacecraft with
            ``SpacecraftConfig.vizard_model_path`` set -- Phase 5, PURELY
            cosmetic (see that field's docstring): replaces the spacecraft's
            default cube icon with a custom CAD model via
            ``vizSupport.createCustomModel()``.
    """
    from Basilisk.architecture import messaging, sysModel
    from Basilisk.simulation import vizInterface
    from Basilisk.utilities import vizSupport

    if request.save_file and request.live_stream:
        raise VizardError("VizardRequest: set at most one of save_file/live_stream, not both")
    if not request.save_file and not request.live_stream:
        raise VizardError("VizardRequest: set save_file or live_stream=True -- nothing to do otherwise")

    if request.save_file:
        save_path = Path(request.save_file)
        save_path.parent.mkdir(parents=True, exist_ok=True)

    battery_by_spacecraft = battery_by_spacecraft or {}
    station_keeping_by_spacecraft = station_keeping_by_spacecraft or {}
    phasing_keeping_by_spacecraft = phasing_keeping_by_spacecraft or {}
    access_out_msgs = access_out_msgs or {}

    class _AccessIndicatorBridge(sysModel.SysModel):
        """See this module's docstring, "Live-data panels" section,
        "Ground-station access windows" bullet, for why this exists and
        why 0/2 (not 0/1) are the two command values used.
        """

        _NO_ACCESS_CMD = 0
        _ACCESS_CMD = 2

        def __init__(self, name: str, access_out_msg):
            super().__init__()
            self.ModelTag = name
            self.accessInMsg = messaging.AccessMsgReader()
            self.accessInMsg.subscribeTo(access_out_msg)
            self.cmdOutMsg = messaging.DeviceCmdMsg()

        def Reset(self, CurrentSimNanos):
            pass

        def UpdateState(self, CurrentSimNanos):
            has_access = bool(self.accessInMsg().hasAccess)
            payload = messaging.DeviceCmdMsgPayload()
            payload.deviceCmd = self._ACCESS_CMD if has_access else self._NO_ACCESS_CMD
            self.cmdOutMsg.write(payload, CurrentSimNanos, self.moduleID)

    class _LiveValueLabelBridge(sysModel.SysModel):
        """Rewrites a GenericStorage panel's own ``label`` field each tick
        to embed its live current/max value as visible on-screen text --
        real user feedback (a screenshot from an actual running Vizard
        instance) confirmed Vizard renders ``GenericStorage.label`` as
        text next to/on the bar, but does not print the numeric value
        itself anywhere on its own, leaving the bar's fill fraction as
        the only thing communicating "how much" -- this closes that gap.

        ``value_source`` is EITHER a Basilisk message reader (called each
        tick for a fresh payload, ``is_reader=True``) or a plain Python
        object whose attributes are read directly (``is_reader=False`` --
        used for :attr:`PhasingKeepingController.lastSeparationKm`/
        ``lastTargetSeparationKm``, the TRUE unclamped numbers, since that
        controller's own ``separationOutMsg`` deliberately reports a
        clamped ``storageLevel`` instead -- see that class's docstring).
        Every argument is captured as an explicit constructor parameter
        (never a closure over a ``for sc_object in sc_objects`` loop
        variable, which would see only the LAST spacecraft's values by
        the time Basilisk actually calls UpdateState) -- same reason
        _AccessIndicatorBridge's own constructor takes ``access_out_msg``
        explicitly rather than closing over it.
        """

        def __init__(self, name: str, panel, base_label: str, units: str, decimals: int,
                     value_source, current_field: str, max_field: str, is_reader: bool):
            super().__init__()
            self.ModelTag = name
            self.panel = panel
            self.base_label = base_label
            self.units = units
            self.decimals = decimals
            self.value_source = value_source
            self.current_field = current_field
            self.max_field = max_field
            self.is_reader = is_reader

        def Reset(self, CurrentSimNanos):
            pass

        def UpdateState(self, CurrentSimNanos):
            source = self.value_source() if self.is_reader else self.value_source
            current = getattr(source, self.current_field)
            maximum = getattr(source, self.max_field)
            self.panel.label = (
                f"{self.base_label}: {current:.{self.decimals}f}/{maximum:.{self.decimals}f} {self.units}"
            )

    generic_storage_list: List[Optional[list]] = []
    generic_sensor_list: List[Optional[list]] = []
    spacecraft_with_storage_panel: List[str] = []
    spacecraft_with_sensor_labels: List[str] = []
    # _AccessIndicatorBridge instances MUST be kept alive by a persistent
    # Python reference for as long as they're registered on scSim's task --
    # they have virtual UpdateState/Reset methods Basilisk calls back into
    # (a SWIG director), unlike the plain-data vizInterface structs below
    # (GenericStorage/GenericSensor), whose relevant state is copied into
    # Basilisk's own C++ containers by enableUnityVisualization() and so
    # don't need this. A Python object garbage-collected while its C++
    # counterpart is still task-registered is undefined behavior -- see
    # where this list is attached to ``viz`` below, and
    # ``engine.service``'s own retention of the returned ``viz``.
    access_indicator_bridges: List[object] = []
    # Same MUST-stay-alive reasoning as access_indicator_bridges above --
    # _LiveValueLabelBridge is a custom Python SysModel too.
    label_bridges: List[object] = []

    def _add_label_bridge(sc_name: str, tag: str, panel, base_label: str, units: str, decimals: int,
                           value_source, current_field: str, max_field: str, is_reader: bool) -> None:
        bridge = _LiveValueLabelBridge(f"{sc_name}_{tag}_label", panel, base_label, units, decimals,
                                        value_source, current_field, max_field, is_reader)
        scSim.AddModelToTask(task_name, bridge)
        label_bridges.append(bridge)

    for sc_object in sc_objects:
        sc_name = sc_object.ModelTag
        storages = []

        battery = battery_by_spacecraft.get(sc_name)
        if battery is not None:
            panel = vizInterface.GenericStorage()
            panel.label = "Battery"
            panel.type = "Battery"
            panel.units = "W-s"
            panel.color = vizInterface.IntVector(vizSupport.toRGBA255("red") + vizSupport.toRGBA255("lightgreen"))
            panel.thresholds = vizInterface.IntVector([20])  # [%] below this, use the first (red) color
            battery_reader = messaging.PowerStorageStatusMsgReader()
            battery_reader.subscribeTo(battery.batPowerOutMsg)
            panel.batteryStateInMsg = battery_reader
            storages.append(panel)

            label_reader = messaging.PowerStorageStatusMsgReader()
            label_reader.subscribeTo(battery.batPowerOutMsg)
            _add_label_bridge(sc_name, "battery", panel, "Battery", panel.units, 1,
                               label_reader, "storageLevel", "storageCapacity", True)

        controller = station_keeping_by_spacecraft.get(sc_name)
        if controller is not None:
            panel = vizInterface.GenericStorage()
            panel.label = "Propellant"
            panel.type = "Propellant Tank"
            panel.units = "kg"
            panel.color = vizInterface.IntVector(vizSupport.toRGBA255("cyan"))
            tank_reader = messaging.FuelTankMsgReader()
            tank_reader.subscribeTo(controller.fuelTankOutMsg)
            panel.fuelTankStateInMsg = tank_reader
            storages.append(panel)

            label_reader = messaging.FuelTankMsgReader()
            label_reader.subscribeTo(controller.fuelTankOutMsg)
            _add_label_bridge(sc_name, "propellant", panel, "Propellant", panel.units, 2,
                               label_reader, "fuelMass", "maxFuelMass", True)

            dv_panel = vizInterface.GenericStorage()
            dv_panel.label = "Delta-V (station-keeping)"
            dv_panel.type = "Delta-V"
            dv_panel.units = "m/s"
            dv_panel.color = vizInterface.IntVector(vizSupport.toRGBA255("yellow"))
            dv_reader = messaging.DataStorageStatusMsgReader()
            dv_reader.subscribeTo(controller.deltaVOutMsg)
            dv_panel.dataStorageStateInMsg = dv_reader
            storages.append(dv_panel)

            label_reader = messaging.DataStorageStatusMsgReader()
            label_reader.subscribeTo(controller.deltaVOutMsg)
            _add_label_bridge(sc_name, "sk_dv", dv_panel, "Delta-V (station-keeping)", dv_panel.units, 2,
                               label_reader, "storageLevel", "storageCapacity", True)

        phasing_controller = phasing_keeping_by_spacecraft.get(sc_name)
        if phasing_controller is not None:
            phasing_dv_panel = vizInterface.GenericStorage()
            phasing_dv_panel.label = "Delta-V (phasing)"
            phasing_dv_panel.type = "Delta-V"
            phasing_dv_panel.units = "m/s"
            phasing_dv_panel.color = vizInterface.IntVector(vizSupport.toRGBA255("orange"))
            phasing_dv_reader = messaging.DataStorageStatusMsgReader()
            phasing_dv_reader.subscribeTo(phasing_controller.deltaVOutMsg)
            phasing_dv_panel.dataStorageStateInMsg = phasing_dv_reader
            storages.append(phasing_dv_panel)

            label_reader = messaging.DataStorageStatusMsgReader()
            label_reader.subscribeTo(phasing_controller.deltaVOutMsg)
            _add_label_bridge(sc_name, "phasing_dv", phasing_dv_panel, "Delta-V (phasing)",
                               phasing_dv_panel.units, 2, label_reader, "storageLevel", "storageCapacity", True)

            separation_panel = vizInterface.GenericStorage()
            separation_panel.label = "Separation from chief"
            separation_panel.type = "Separation"
            separation_panel.units = "km"
            separation_panel.color = vizInterface.IntVector(vizSupport.toRGBA255("magenta"))
            separation_reader = messaging.DataStorageStatusMsgReader()
            separation_reader.subscribeTo(phasing_controller.separationOutMsg)
            separation_panel.dataStorageStateInMsg = separation_reader
            storages.append(separation_panel)

            # is_reader=False: reads phasing_controller.lastSeparationKm/
            # lastTargetSeparationKm directly (the TRUE, unclamped
            # numbers), NOT separationOutMsg's own storageLevel (which is
            # deliberately clamped so the BAR can't overflow -- see
            # PhasingKeepingController's own docstring).
            _add_label_bridge(sc_name, "separation", separation_panel, "Separation from chief",
                               separation_panel.units, 2, phasing_controller,
                               "lastSeparationKm", "lastTargetSeparationKm", False)

        generic_storage_list.append(storages or None)
        if storages:
            spacecraft_with_storage_panel.append(sc_name)

        sensors = []
        for (gs_name, paired_sc_name), access_out_msg in access_out_msgs.items():
            if paired_sc_name != sc_name:
                continue
            bridge = _AccessIndicatorBridge(f"{sc_name}_{gs_name}_accessIndicator", access_out_msg)
            scSim.AddModelToTask(task_name, bridge)
            access_indicator_bridges.append(bridge)

            cmd_reader = messaging.DeviceCmdMsgReader()
            cmd_reader.subscribeTo(bridge.cmdOutMsg)

            sensor = vizInterface.GenericSensor()
            sensor.r_SB_B = [0.0, 0.0, 0.0]  # placeholder -- see module docstring
            sensor.normalVector = [1.0, 0.0, 0.0]  # placeholder -- see module docstring
            sensor.fieldOfView.push_back(0.1)  # [rad] small symbolic cone, not a real antenna beamwidth
            sensor.color = vizInterface.IntVector(vizSupport.toRGBA255("red") + vizSupport.toRGBA255("lightgreen"))
            sensor.label = f"Access: {gs_name}"
            sensor.genericSensorCmdInMsg = cmd_reader
            sensors.append(sensor)

        generic_sensor_list.append(sensors or None)
        if sensors:
            spacecraft_with_sensor_labels.append(sc_name)

    try:
        viz = vizSupport.enableUnityVisualization(
            scSim, task_name, sc_objects,
            saveFile=str(request.save_file) if request.save_file else None,
            liveStream=request.live_stream,
            rwEffectorList=rw_effectors_by_spacecraft,
            genericStorageList=generic_storage_list if any(generic_storage_list) else None,
            genericSensorList=generic_sensor_list if any(generic_sensor_list) else None,
        )
    except Exception as exc:  # noqa: BLE001 -- report ANY Vizard setup failure with a specific message
        raise VizardError(f"vizSupport.enableUnityVisualization failed: {exc}") from exc

    # Phase 5: custom CAD models -- purely cosmetic (see this function's
    # docstring), applied after enableUnityVisualization() itself per
    # createCustomModel()'s own docstring ("This method creates a
    # CustomModel" against the already-built ``viz``).
    for sc_name, model in (custom_models_by_spacecraft or {}).items():
        try:
            vizSupport.createCustomModel(
                viz, modelPath=model["path"], simBodiesToModify=[sc_name],
                offset=list(model.get("offset_m", [0.0, 0.0, 0.0])),
                rotation=[math.radians(v) for v in model.get("rotation_deg", [0.0, 0.0, 0.0])],
                scale=list(model.get("scale", [1.0, 1.0, 1.0])),
            )
        except Exception as exc:  # noqa: BLE001 -- report ANY custom-model failure with a specific message
            raise VizardError(f"vizSupport.createCustomModel failed for {sc_name!r}: {exc}") from exc

    # See module docstring: without these, Vizard falls back to its own
    # default (spacecraft-locked, no orbit trace) instead of an
    # STK/GMAT/FreeFlyer-style central-body-centered view.
    viz.settings.mainCameraTarget = request.camera_target or central_body_name
    if request.show_orbit_lines:
        viz.settings.orbitLinesOn = 1  # osculating orbit line, relative to parent body
        viz.settings.trueTrajectoryLinesOn = 1  # true (propagated) trajectory line, inertial
    viz.settings.showSpacecraftLabels = 1
    viz.settings.showCelestialBodyLabels = 1

    for gs_name, gs in (ground_stations or {}).items():
        # Edge-to-edge cone angle for the access region above gs.minimumElevation
        # (elevation measured from the local horizon): a zenith-centered cone of
        # half-angle (pi/2 - minimumElevation) has full angle pi - 2*minimumElevation.
        field_of_view = math.pi - 2.0 * gs.minimumElevation
        vizSupport.addLocation(
            viz, stationName=gs_name, parentBodyName=central_body_name,
            r_GP_P=list(gs.r_LP_P_Init), fieldOfView=field_of_view,
            color="cyan", label=gs_name,
        )

    # showGenericStoragePanel/showGenericSensorLabels default to "use Vizard's
    # own default" (which may be off) unless explicitly requested per
    # spacecraft -- without this, a live battery/propellant panel or access
    # -window label could silently not be visible despite being wired up.
    # ONE setInstrumentGuiSetting call per spacecraft (not one per flag):
    # each call appends a new entry to vizSupport's own module-level
    # settings list rather than merging into an existing one, so a
    # spacecraft needing both flags must set them together.
    for sc_name in set(spacecraft_with_storage_panel) | set(spacecraft_with_sensor_labels):
        kwargs = {}
        if sc_name in spacecraft_with_storage_panel:
            kwargs["showGenericStoragePanel"] = True
        if sc_name in spacecraft_with_sensor_labels:
            kwargs["showGenericSensorLabels"] = True
        vizSupport.setInstrumentGuiSetting(viz, spacecraftName=sc_name, **kwargs)

    # Returned alongside viz (not attached to it as an attribute -- viz is
    # a SWIG proxy for a C++ VizInterface, and SWIG-generated proxy
    # classes reject assigning any attribute they don't already know
    # about; this was tried, and every real run of the live-stream path
    # raised exactly that "You tried to add this variable ... To this
    # class" error before initialization ever got as far as running a
    # single step) so the caller (engine.service.SimulationService.build())
    # can retain all five for the instance's lifetime -- see this
    # function's docstring (both "Real bug found" notes) for why these
    # specifically need a persistent Python reference at all.
    # generic_storage_list/generic_sensor_list are the exact objects
    # already handed to enableUnityVisualization() above (genericStorageList=/
    # genericSensorList=) -- VizSpacecraftData's matching fields are
    # std::vector<GenericStorage *>/std::vector<GenericSensor *> (raw
    # pointers), so those are the SAME objects VizInterface now holds
    # dangling pointers to unless something keeps them alive. label_bridges
    # is a custom Python SysModel list, same "must stay task-registered
    # AND Python-alive together" reasoning as access_indicator_bridges.
    return viz, access_indicator_bridges, generic_storage_list, generic_sensor_list, label_bridges
