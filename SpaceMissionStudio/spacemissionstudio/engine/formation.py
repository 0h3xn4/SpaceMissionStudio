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
Phasing-formation generator: turns an existing "chief" spacecraft's orbit
plus a desired chief -> follower offset in the RADIAL/TRANSVERSE/NORMAL
(Hill) frame at epoch into a new follower :class:`~spacemissionstudio.schema.scenario.SpacecraftConfig`
with ``phasing_keeping`` (and the ``station_keeping`` it requires)
pre-wired -- the initial-geometry counterpart to
``engine.constellation``'s Walker generator, built for exactly the
two-satellite "chief holds station, follower holds formation" case
``05_formation_flying_phasing.json`` demonstrates by hand ("Generate
phasing formation..." in the GUI).

Unlike ``engine.constellation`` (deliberately Basilisk-free -- see that
module's docstring: a Walker pattern is naturally expressed directly in
classical elements, no coordinate transform needed), this module uses
Basilisk's own ``Basilisk.utilities.orbitalMotion`` functions
(``elem2rv``/``hill2rv``/``rv2elem``/``M2E``/``E2f``) -- never a
hand-rolled equivalent -- plus ``Basilisk.utilities.simIncludeGravBody``
for a real ``mu``/``radEquator`` (the same body-constants source
``engine.service`` itself uses, rather than a second hardcoded copy like
``engine.constellation``'s own ``CENTRAL_BODY_EQUATORIAL_RADIUS_KM``).
Needs a real Basilisk build; gated ``requires_basilisk`` in tests, same
tier as ``engine.service``/``engine.orbit_maintenance`` -- the GUI action
that calls this catches ``ImportError`` and reports it the same way every
other Basilisk-needing GUI action already does (see ``gui.run_worker``).

The chief's orbit must already be ``type == "classical_elements"`` --
same requirement ``engine.service`` itself enforces for any
``phasing_keeping.chief_spacecraft`` (it needs the chief's semi-major
axis directly; see that module's matching check), surfaced here as a
:class:`~spacemissionstudio.schema.scenario.ScenarioValidationError` up front
rather than left to fail later inside a run.

**Along-track (T) is NOT placed via a single ``hill2rv`` call from the
chief's state, and this is deliberate, not an oversight** -- a real,
100%-reproducible bug, found from an actual user's report (a real
Vizard run showing a requested 500 km separation reading as ~0 km at
generation time): ``orbitalMotion.rv2elem()`` decomposing a
``hill2rv``-perturbed near-circular state puts essentially the ENTIRE
along-track angle into ``omega`` (argument of periapsis), not ``f`` (true
anomaly) -- confirmed directly, independent of offset size (1 km through
500 km all came back with ``f`` within floating-point noise of the
CHIEF's own ``f``). ``engine.orbit_maintenance.PhasingKeepingController``
only ever reads ``f``/mean-anomaly (never ``omega``) to measure
along-track separation, so a follower placed that way was invisible to
it: the controller believed it was already on target and never fired.
Fixed by placing T as a DIRECT mean-anomaly shift on the chief's own
``(a, e, i, Omega, omega)`` (Kepler's equation, via ``M2E``/``E2f``,
same arc-length convention ``engine.orbit_maintenance.SeparationSchedule``
itself uses) -- this is exactly what a real, propagated Basilisk state
started this way reports back through the SAME ``rv2elem`` call
``PhasingKeepingController`` makes every tick, confirmed numerically
(500 km requested reads back as exactly 500.000 km).

R/N (radial/cross-track) are layered on AFTERWARD via ``hill2rv``, on
top of that already-correct T placement -- see
:func:`generate_phasing_follower`'s own docstring for why, and for how
much each one, individually, still perturbs the along-track reading
(R much more than N).

IMPORTANT LIMITATION, stated here and surfaced in the GUI dialog itself:
:class:`engine.orbit_maintenance.PhasingKeepingController` only closes
the loop on the ALONG-TRACK (transverse) component of chief/follower
separation (see that class's own docstring) -- it has no radial or
cross-track control authority at all. Only T feeds
``phasing_keeping.target_separation_km`` as the actively-maintained
target; any radial/cross-track offset requested is a STARTING geometry
only and will drift over the run exactly as any other uncontrolled
orbital difference would (this also means the follower's resulting
semi-major-axis/inclination/RAAN will differ slightly from the chief's
own whenever a nonzero radial/cross-track offset is requested -- expected
and physically correct, not a bug: a real offset in those axes implies a
genuinely different, if nearby, orbital plane/altitude, exactly the same
way ``05_formation_flying_phasing.json``'s own hand-written
along-track-only offset already relies on the along-track control law
tolerating a small, otherwise-uncontrolled orbital mismatch).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Optional

import numpy as np

from ..schema.scenario import (
    PhasingKeepingConfig,
    ScenarioValidationError,
    OrbitIC,
    SpacecraftConfig,
    StationKeepingConfig,
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ScenarioValidationError(message)


@dataclass
class PhasingFormationRequest:
    """See module docstring. ``radial_km``/``along_track_km``/``cross_track_km``
    are the follower's desired offset from the chief in the CHIEF's own
    Hill (RTN) frame at epoch -- radial = outward along the chief's
    position vector, along-track = along the chief's velocity direction,
    cross-track = along the chief's orbit-normal (angular momentum)
    direction, exactly ``Basilisk.utilities.orbitalMotion.hillFrame``'s
    own axis convention -- but NOT all three are placed the same way; see
    module docstring for why ``along_track_km`` is a direct mean-anomaly
    shift while ``radial_km``/``cross_track_km`` are a genuine Hill-frame
    perturbation layered on afterward. Relative velocity at epoch is
    taken as zero for the R/N part (a fixed geometric offset "dropped in
    place", not a bounded/periodic relative orbit solved for -- the
    active along-track control law is what holds station over time, the
    same way the bundled template's own simpler true-anomaly-shift offset
    already relies on it).
    """

    chief_name: str
    follower_name: str
    radial_km: float = 0.0  # [km] Hill-frame R offset at epoch -- starting geometry only, see module docstring
    along_track_km: float = 50.0  # [km] direct mean-anomaly shift at epoch -- also phasing_keeping's target
    cross_track_km: float = 0.0  # [km] Hill-frame N offset at epoch -- starting geometry only, see module docstring
    reconfiguration_interval_days: float = 90.0  # [day]
    tolerance_fraction: float = 0.10  # [-]
    restore_tolerance_fraction: float = 0.02  # [-]
    correction_window_days: float = 21.0  # [day]
    max_drift_days: float = 90.0  # [day]
    max_delta_semi_major_axis_km: float = 3.0  # [km]
    # station_keeping is REQUIRED alongside phasing_keeping (shared
    # thruster/tank -- see PhasingKeepingConfig's own docstring); None
    # (the default) derives target_altitude_km from the CHIEF's own
    # altitude at generation time rather than asking for a value that, in
    # the common case, is just "the same altitude the chief is already at".
    station_keeping_target_altitude_km: Optional[float] = None  # [km]
    station_keeping_deadband_km: float = 2.0  # [km]
    thrust_n: float = 0.05  # [N]
    isp_s: float = 1500.0  # [s]
    propellant_kg: float = 5.0  # [kg]
    eclipse_sunlit_threshold: float = 0.99  # [-]

    def validate(self) -> None:
        _require(bool(self.chief_name), "phasing_formation.chief_name must not be empty")
        _require(bool(self.follower_name), "phasing_formation.follower_name must not be empty")
        _require(self.follower_name != self.chief_name,
                  "phasing_formation.follower_name must differ from chief_name")
        _require(abs(self.along_track_km) > 1e-6,
                  "phasing_formation.along_track_km must not be ~0 -- phasing_keeping needs a nonzero "
                  "along-track target separation to hold (radial_km/cross_track_km may still be 0)")
        _require(self.reconfiguration_interval_days >= 0,
                  "phasing_formation.reconfiguration_interval_days must be >= 0")
        _require(0.0 < self.tolerance_fraction,
                  "phasing_formation.tolerance_fraction must be > 0")
        _require(0.0 < self.restore_tolerance_fraction,
                  "phasing_formation.restore_tolerance_fraction must be > 0")
        _require(self.correction_window_days > 0,
                  "phasing_formation.correction_window_days must be > 0")
        _require(self.max_drift_days > 0,
                  "phasing_formation.max_drift_days must be > 0")
        _require(self.max_delta_semi_major_axis_km > 0,
                  "phasing_formation.max_delta_semi_major_axis_km must be > 0")
        if self.station_keeping_target_altitude_km is not None:
            _require(self.station_keeping_target_altitude_km > 0,
                      "phasing_formation.station_keeping_target_altitude_km must be > 0")
        _require(0.0 < self.station_keeping_deadband_km,
                  "phasing_formation.station_keeping_deadband_km must be > 0")
        _require(self.thrust_n > 0, "phasing_formation.thrust_n must be > 0")
        _require(self.isp_s > 0, "phasing_formation.isp_s must be > 0")
        _require(self.propellant_kg >= 0, "phasing_formation.propellant_kg must be >= 0")
        _require(0.0 < self.eclipse_sunlit_threshold <= 1.0,
                  "phasing_formation.eclipse_sunlit_threshold must be in (0, 1]")


def generate_phasing_follower(request: PhasingFormationRequest, chief: SpacecraftConfig,
                               template: SpacecraftConfig, central_body: str) -> SpacecraftConfig:
    """Returns a new follower :class:`SpacecraftConfig`, cloned from
    ``template`` (mass/sensors/actuators/FSW/power/... unchanged, same
    "you only supply what's needed" pattern as
    ``engine.constellation.generate_walker_constellation``), with:

    * ``orbit`` set from ``chief``'s current orbit at epoch, offset by
      ``request`` (see module docstring for exactly how T vs R/N are
      each applied, and why differently) -- computed via Basilisk's own
      ``orbitalMotion`` functions, never a hand-rolled equivalent.
    * ``station_keeping`` set from ``request`` (required alongside
      ``phasing_keeping`` -- see ``PhasingKeepingConfig``'s docstring).
    * ``phasing_keeping`` set, targeting ``chief.name`` at
      ``abs(request.along_track_km)`` -- the only component of the
      requested offset the controller actively maintains; see module
      docstring's limitation note. Achieved to that exact value (as
      independently confirmed by ``PhasingKeepingController``'s own
      mean-anomaly-difference tracking) whenever R and N are both 0;
      progressively less exact the larger a nonzero R/N is also
      requested (R affects it much more than N -- see module docstring),
      in which case the difference simply becomes the follower's real
      initial phasing error for the controller to correct with a small
      burn once the run starts, same as any other starting mismatch.

    Raises :class:`~spacemissionstudio.schema.scenario.ScenarioValidationError`
    if ``request`` is invalid or ``chief.orbit.type`` is not
    ``"classical_elements"``. Needs a real Basilisk build (imports
    ``Basilisk.utilities.orbitalMotion``/``simIncludeGravBody`` lazily, at
    call time, not at module import time -- same lazy-Basilisk-import
    convention ``engine.vizard`` uses).
    """
    request.validate()
    _require(chief.orbit.type == "classical_elements",
             f"phasing_formation: chief spacecraft {chief.name!r}'s orbit must be type "
             f"'classical_elements' (phasing_keeping needs its semi-major axis directly) -- "
             f"got {chief.orbit.type!r}")

    from Basilisk.utilities import orbitalMotion, simIncludeGravBody

    grav_factory = simIncludeGravBody.gravBodyFactory()
    try:
        central = grav_factory.createBodies([central_body])[central_body]
    except (KeyError, RuntimeError) as exc:
        raise ScenarioValidationError(
            f"phasing_formation: central body {central_body!r} is not one Basilisk's "
            f"simIncludeGravBody.gravBodyFactory().createBodies() recognizes: {exc}"
        ) from exc
    mu = central.mu  # [m^3/s^2]
    r_equator_km = central.radEquator / 1000.0  # [km]

    chief_oe = orbitalMotion.ClassicElements()
    chief_oe.a = chief.orbit.semi_major_axis_km * 1000.0
    chief_oe.e = chief.orbit.eccentricity
    chief_oe.i = np.radians(chief.orbit.inclination_deg)
    chief_oe.Omega = np.radians(chief.orbit.raan_deg)
    chief_oe.omega = np.radians(chief.orbit.arg_periapsis_deg)
    if chief.orbit.anomaly_type == "mean":
        chief_mean_anomaly = np.radians(chief.orbit.mean_anomaly_deg)
        eccentric_anomaly = orbitalMotion.M2E(chief_mean_anomaly, chief.orbit.eccentricity)
        chief_oe.f = orbitalMotion.E2f(eccentric_anomaly, chief.orbit.eccentricity)
    else:
        chief_oe.f = np.radians(chief.orbit.true_anomaly_deg)
        eccentric_anomaly = orbitalMotion.f2E(chief_oe.f, chief.orbit.eccentricity)
        chief_mean_anomaly = orbitalMotion.E2M(eccentric_anomaly, chief.orbit.eccentricity)

    # Along-track (T): a DIRECT mean-anomaly shift on the chief's own
    # (a, e, i, Omega, omega) -- deliberately NOT routed through
    # orbitalMotion.hill2rv (see below for why). Uses the exact same
    # arc-length approximation (theta = distance / a) as
    # engine.orbit_maintenance.SeparationSchedule itself, so this is
    # EXACTLY the separation PhasingKeepingController's own
    # mean-anomaly-difference tracking will read at epoch -- confirmed
    # against a real Basilisk run (see this function's docstring for the
    # bug this fixes).
    along_track_rad = request.along_track_km * 1000.0 / chief_oe.a  # [rad]
    follower_oe = orbitalMotion.ClassicElements()
    follower_oe.a, follower_oe.e, follower_oe.i = chief_oe.a, chief_oe.e, chief_oe.i
    follower_oe.Omega, follower_oe.omega = chief_oe.Omega, chief_oe.omega
    follower_eccentric_anomaly = orbitalMotion.M2E(chief_mean_anomaly + along_track_rad, chief_oe.e)
    follower_oe.f = orbitalMotion.E2f(follower_eccentric_anomaly, chief_oe.e)
    r_follower_n, v_follower_n = orbitalMotion.elem2rv(mu, follower_oe)

    # Radial/cross-track (R, N): layered on AFTERWARD as a Hill-frame
    # perturbation of the along-track-correct state above (rather than
    # applying the full 3-axis (R, T, N) offset to the CHIEF's state in
    # one hill2rv call, an earlier version of this function did and a
    # real user found broken -- see this function's own docstring).
    # ``orbitalMotion.rv2elem`` has to re-derive (a, e, omega, f) from
    # the perturbed state vectors, and for a near-circular orbit that
    # decomposition is inherently ambiguous -- ANY nonzero R (much more
    # than N; confirmed numerically: R=1 km alone already misreads a
    # 500 km along-track target as ~350 km, R=5 km as ~155 km, while
    # N=50 km alone only costs a few percent) shifts some of the
    # along-track angle into ``omega``/``a``/``e`` instead of leaving it
    # in ``f``, which is exactly what PhasingKeepingController's tracking
    # reads. Doing R/N SECOND, on top of an already-correct T placement,
    # keeps that leakage a small residual on top of a real target instead
    # of swallowing the entire requested separation (what a raw T-only
    # hill2rv call from the chief did: EVERY tested along-track offset,
    # regardless of magnitude, came back reading ~0 km). Any resulting
    # mismatch between the requested and actually-achieved along-track
    # separation is not silently hidden either way: it becomes the
    # follower's real initial phasing error, which
    # PhasingKeepingController will simply correct with a small burn once
    # the run starts, same as it would for any other initial mismatch.
    if request.radial_km != 0.0 or request.cross_track_km != 0.0:
        rho_h = np.array([request.radial_km, 0.0, request.cross_track_km]) * 1000.0  # [m]
        rho_prime_h = np.zeros(3)  # [m/s] see PhasingFormationRequest's own docstring
        r_follower_n, v_follower_n = orbitalMotion.hill2rv(r_follower_n, v_follower_n, rho_h, rho_prime_h)
        follower_oe = orbitalMotion.rv2elem(mu, r_follower_n, v_follower_n)

    follower = copy.deepcopy(template)
    follower.name = request.follower_name
    # float(...) throughout: orbitalMotion's return values are numpy
    # float64 scalars -- harmless for json.dumps (float64 subclasses
    # Python's own float), but every other OrbitIC built in this codebase
    # stores plain floats, so this keeps this one consistent rather than
    # leaking a numpy type into a schema object.
    follower.orbit = OrbitIC(
        type="classical_elements",
        semi_major_axis_km=float(follower_oe.a / 1000.0),
        eccentricity=float(follower_oe.e),
        inclination_deg=float(np.degrees(follower_oe.i)),
        raan_deg=float(np.degrees(follower_oe.Omega) % 360.0),
        arg_periapsis_deg=float(np.degrees(follower_oe.omega) % 360.0),
        anomaly_type="true",
        true_anomaly_deg=float(np.degrees(follower_oe.f) % 360.0),
    )

    target_altitude_km = request.station_keeping_target_altitude_km
    if target_altitude_km is None:
        target_altitude_km = float(chief_oe.a / 1000.0 - r_equator_km)

    follower.station_keeping = StationKeepingConfig(
        target_altitude_km=target_altitude_km,
        deadband_km=request.station_keeping_deadband_km,
        thrust_n=request.thrust_n,
        isp_s=request.isp_s,
        propellant_kg=request.propellant_kg,
        eclipse_sunlit_threshold=request.eclipse_sunlit_threshold,
    )
    follower.phasing_keeping = PhasingKeepingConfig(
        chief_spacecraft=chief.name,
        target_separation_km=[abs(request.along_track_km)],
        reconfiguration_interval_days=request.reconfiguration_interval_days,
        tolerance_fraction=request.tolerance_fraction,
        restore_tolerance_fraction=request.restore_tolerance_fraction,
        correction_window_days=request.correction_window_days,
        max_drift_days=request.max_drift_days,
        max_delta_semi_major_axis_km=request.max_delta_semi_major_axis_km,
    )
    return follower
