"""Tests for spacemissionstudio.engine.formation -- needs a Basilisk build
(generate_phasing_follower() imports Basilisk.utilities.orbitalMotion/
simIncludeGravBody lazily, at call time -- see that module's docstring),
so this whole file is requires_basilisk, unlike tests/test_constellation.py
(engine.constellation is deliberately Basilisk-free).
"""

import numpy as np
import pytest

pytestmark = pytest.mark.requires_basilisk

from spacemissionstudio.engine.formation import PhasingFormationRequest, generate_phasing_follower
from spacemissionstudio.schema.scenario import OrbitIC, PowerConfig, ScenarioValidationError, SpacecraftConfig


def _chief(**overrides):
    defaults = dict(
        name="chief-1", dry_mass_kg=100.0,
        orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6928.0, eccentricity=0.001,
                      inclination_deg=45.0, raan_deg=0.0, arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
    )
    defaults.update(overrides)
    return SpacecraftConfig(**defaults)


def _request(**overrides):
    defaults = dict(chief_name="chief-1", follower_name="follower-1", along_track_km=50.0)
    defaults.update(overrides)
    return PhasingFormationRequest(**defaults)


def test_follower_orbit_type_is_classical_elements():
    follower = generate_phasing_follower(_request(), _chief(), _chief(), central_body="earth")
    assert follower.orbit.type == "classical_elements"
    assert all(
        isinstance(getattr(follower.orbit, field), (float, type(None)))
        for field in ("semi_major_axis_km", "eccentricity", "inclination_deg", "raan_deg",
                      "arg_periapsis_deg", "true_anomaly_deg")
    )


def test_zero_cross_track_offset_keeps_the_chiefs_orbital_plane():
    """A pure in-plane (R, T) offset -- cross_track_km == 0 -- must keep
    the follower in the SAME orbital plane as the chief (inclination/RAAN
    unchanged): a Hill-frame offset with no N component never leaves the
    plane spanned by the chief's own R/T axes at epoch. It does NOT,
    however, leave the semi-major axis unperturbed in general (a straight
    -line Hill-frame displacement is a chord, not an arc, so it moves the
    follower off the chief's exact circle/ellipse by construction) --
    that's covered separately, and confirmed against the real Hill-frame
    math directly, by test_along_track_offset_round_trips_through_hill_frame.
    """
    chief = _chief(orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6928.0, eccentricity=0.0,
                                  inclination_deg=45.0, raan_deg=0.0, arg_periapsis_deg=0.0, true_anomaly_deg=0.0))
    follower = generate_phasing_follower(
        _request(radial_km=1.0, along_track_km=50.0, cross_track_km=0.0), chief, chief, central_body="earth",
    )
    assert follower.orbit.inclination_deg == pytest.approx(chief.orbit.inclination_deg, abs=1e-6)
    assert follower.orbit.raan_deg == pytest.approx(chief.orbit.raan_deg, abs=1e-6)


def test_nonzero_cross_track_offset_changes_orbital_plane():
    chief = _chief()
    follower = generate_phasing_follower(
        _request(radial_km=0.0, along_track_km=50.0, cross_track_km=5.0), chief, chief, central_body="earth",
    )
    assert follower.orbit.inclination_deg != pytest.approx(chief.orbit.inclination_deg, abs=1e-6)


def _measured_separation_km(chief, follower):
    """What PhasingKeepingController's OWN mean-anomaly-difference
    tracking (engine.orbit_maintenance._mean_anomaly, replicated here
    rather than imported since that module needs a full SysModel/task
    context to construct) would read for this pair at epoch -- the exact
    property the real bug (see test below) broke.
    """
    from Basilisk.utilities import orbitalMotion, simIncludeGravBody

    grav_factory = simIncludeGravBody.gravBodyFactory()
    mu = grav_factory.createBodies(["earth"])["earth"].mu

    def rv(orbit):
        oe = orbitalMotion.ClassicElements()
        oe.a = orbit.semi_major_axis_km * 1000.0
        oe.e = orbit.eccentricity
        oe.i = np.radians(orbit.inclination_deg)
        oe.Omega = np.radians(orbit.raan_deg)
        oe.omega = np.radians(orbit.arg_periapsis_deg)
        oe.f = np.radians(orbit.true_anomaly_deg)
        return orbitalMotion.elem2rv(mu, oe)

    def mean_anomaly(r, v):
        oe = orbitalMotion.rv2elem(mu, r, v)
        eccentric_anomaly = orbitalMotion.f2E(oe.f, oe.e)
        return orbitalMotion.E2M(eccentric_anomaly, oe.e), oe.a

    r_c, v_c = rv(chief.orbit)
    r_f, v_f = rv(follower.orbit)
    m_c, _ = mean_anomaly(r_c, v_c)
    m_f, a_f = mean_anomaly(r_f, v_f)
    wrapped = (m_f - m_c + np.pi) % (2 * np.pi) - np.pi
    return abs(wrapped) * chief.orbit.semi_major_axis_km * 1000.0 / 1000.0


def test_along_track_separation_matches_target_exactly_with_zero_radial_and_cross_track():
    """Regression test for the real bug this generator's docstring
    describes: a real user's Vizard run showed a requested along-track
    separation reading as ~0 km to PhasingKeepingController. With R and N
    both 0, the along-track separation the controller will actually
    measure at epoch must match the request to high precision.
    """
    chief = _chief()
    follower = generate_phasing_follower(
        _request(radial_km=0.0, along_track_km=500.0, cross_track_km=0.0), chief, chief, central_body="earth",
    )
    assert _measured_separation_km(chief, follower) == pytest.approx(500.0, abs=0.01)


def test_along_track_separation_is_far_off_when_placed_via_a_single_hill2rv_call():
    """Negative control for the test above: confirms the OLD (buggy)
    approach -- a single hill2rv(chief_r, chief_v, [R, T, N]) call, then
    rv2elem straight back to classical elements -- really does misread a
    500 km along-track request as approximately 0 km, the exact failure
    a real user reported. If this ever stops failing, orbitalMotion's own
    near-circular rv2elem convention changed and this generator's whole
    T-vs-R/N split (see its module docstring) should be re-examined.
    """
    from Basilisk.utilities import orbitalMotion, simIncludeGravBody

    chief = _chief()
    grav_factory = simIncludeGravBody.gravBodyFactory()
    mu = grav_factory.createBodies(["earth"])["earth"].mu
    chief_oe = orbitalMotion.ClassicElements()
    chief_oe.a = chief.orbit.semi_major_axis_km * 1000.0
    chief_oe.e = chief.orbit.eccentricity
    chief_oe.i = np.radians(chief.orbit.inclination_deg)
    chief_oe.Omega = np.radians(chief.orbit.raan_deg)
    chief_oe.omega = np.radians(chief.orbit.arg_periapsis_deg)
    chief_oe.f = np.radians(chief.orbit.true_anomaly_deg)
    r_c, v_c = orbitalMotion.elem2rv(mu, chief_oe)

    rho_h = np.array([0.0, 500.0, 0.0]) * 1000.0
    r_f, v_f = orbitalMotion.hill2rv(r_c, v_c, rho_h, np.zeros(3))
    follower_oe = orbitalMotion.rv2elem(mu, r_f, v_f)

    assert abs(np.degrees(follower_oe.f) % 360.0) < 0.01  # ~ same f as the chief's own 0 deg -- the bug


def test_along_track_separation_degrades_gracefully_with_nonzero_radial_and_cross_track():
    """R/N are layered on AFTER the along-track placement (see module
    docstring) -- the resulting along-track reading won't be exact
    anymore, but must stay in the right ballpark (nowhere near the total
    failure -- ~0 km -- the single-hill2rv-call approach produced).
    """
    chief = _chief()
    follower = generate_phasing_follower(
        _request(radial_km=1.0, along_track_km=500.0, cross_track_km=50.0), chief, chief, central_body="earth",
    )
    measured = _measured_separation_km(chief, follower)
    assert 250.0 < measured < 500.0  # meaningfully close to 500, nowhere near the ~0 km bug


def test_phasing_keeping_targets_abs_along_track_km():
    follower = generate_phasing_follower(_request(along_track_km=-50.0), _chief(), _chief(), central_body="earth")
    assert follower.phasing_keeping.target_separation_km == [50.0]
    assert follower.phasing_keeping.chief_spacecraft == "chief-1"


def test_station_keeping_is_required_and_set():
    follower = generate_phasing_follower(_request(), _chief(), _chief(), central_body="earth")
    assert follower.station_keeping is not None
    assert follower.station_keeping.propellant_kg == 5.0  # PhasingFormationRequest's own default


def test_default_target_altitude_is_derived_from_chief():
    chief = _chief()  # a = 6928.0 km, earth radius ~6378.1366 km -> alt ~549.86 km
    follower = generate_phasing_follower(_request(), chief, chief, central_body="earth")
    assert follower.station_keeping.target_altitude_km == pytest.approx(549.8634, abs=1e-3)


def test_explicit_target_altitude_overrides_derived_default():
    follower = generate_phasing_follower(
        _request(station_keeping_target_altitude_km=600.0), _chief(), _chief(), central_body="earth",
    )
    assert follower.station_keeping.target_altitude_km == 600.0


def test_template_fields_other_than_orbit_are_cloned():
    template = _chief(name="chief-1", power=PowerConfig(panel_area_m2=0.5, panel_efficiency=0.3,
                                                          battery_capacity_wh=100.0))
    follower = generate_phasing_follower(_request(), _chief(), template, central_body="earth")
    assert follower.power is not None
    assert follower.power.battery_capacity_wh == 100.0
    assert follower.name == "follower-1"  # NOT the template's own name


def test_generated_follower_passes_full_scenario_validation():
    follower = generate_phasing_follower(_request(), _chief(), _chief(), central_body="earth")
    follower.validate()  # must not raise


def test_rejects_zero_along_track_km():
    with pytest.raises(ScenarioValidationError, match="along_track_km"):
        generate_phasing_follower(_request(along_track_km=0.0), _chief(), _chief(), central_body="earth")


def test_rejects_follower_name_matching_chief_name():
    with pytest.raises(ScenarioValidationError, match="differ from chief_name"):
        generate_phasing_follower(
            _request(chief_name="chief-1", follower_name="chief-1"), _chief(), _chief(), central_body="earth",
        )


def test_rejects_non_classical_elements_chief_orbit():
    chief = _chief(orbit=OrbitIC(type="cartesian", position_km=[7000.0, 0.0, 0.0], velocity_km_s=[0.0, 7.5, 0.0]))
    with pytest.raises(ScenarioValidationError, match="classical_elements"):
        generate_phasing_follower(_request(), chief, chief, central_body="earth")
