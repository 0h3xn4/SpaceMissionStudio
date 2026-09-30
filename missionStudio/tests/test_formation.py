"""Tests for missionstudio.engine.formation -- needs a Basilisk build
(generate_phasing_follower() imports Basilisk.utilities.orbitalMotion/
simIncludeGravBody lazily, at call time -- see that module's docstring),
so this whole file is requires_basilisk, unlike tests/test_constellation.py
(engine.constellation is deliberately Basilisk-free).
"""

import numpy as np
import pytest

pytestmark = pytest.mark.requires_basilisk

from missionstudio.engine.formation import PhasingFormationRequest, generate_phasing_follower
from missionstudio.schema.scenario import OrbitIC, PowerConfig, ScenarioValidationError, SpacecraftConfig


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


def test_along_track_offset_round_trips_through_hill_frame():
    """The along-track component of the Hill-frame offset used to place
    the follower must match what a direct rv2hill of the generated
    follower's own state recovers -- confirms generate_phasing_follower
    calls hill2rv/elem2rv consistently, not some other convention.
    """
    from Basilisk.utilities import orbitalMotion, simIncludeGravBody

    chief = _chief()
    request = _request(radial_km=1.0, along_track_km=50.0, cross_track_km=2.0)
    follower = generate_phasing_follower(request, chief, chief, central_body="earth")

    grav_factory = simIncludeGravBody.gravBodyFactory()
    mu = grav_factory.createBodies(["earth"])["earth"].mu

    chief_oe = orbitalMotion.ClassicElements()
    chief_oe.a = chief.orbit.semi_major_axis_km * 1000.0
    chief_oe.e = chief.orbit.eccentricity
    chief_oe.i = np.radians(chief.orbit.inclination_deg)
    chief_oe.Omega = np.radians(chief.orbit.raan_deg)
    chief_oe.omega = np.radians(chief.orbit.arg_periapsis_deg)
    chief_oe.f = np.radians(chief.orbit.true_anomaly_deg)
    r_chief, v_chief = orbitalMotion.elem2rv(mu, chief_oe)

    follower_oe = orbitalMotion.ClassicElements()
    follower_oe.a = follower.orbit.semi_major_axis_km * 1000.0
    follower_oe.e = follower.orbit.eccentricity
    follower_oe.i = np.radians(follower.orbit.inclination_deg)
    follower_oe.Omega = np.radians(follower.orbit.raan_deg)
    follower_oe.omega = np.radians(follower.orbit.arg_periapsis_deg)
    follower_oe.f = np.radians(follower.orbit.true_anomaly_deg)
    r_follower, v_follower = orbitalMotion.elem2rv(mu, follower_oe)

    rho_h, _rho_prime_h = orbitalMotion.rv2hill(r_chief, v_chief, r_follower, v_follower)
    assert rho_h[0] == pytest.approx(1000.0, abs=1.0)
    assert rho_h[1] == pytest.approx(50000.0, abs=1.0)
    assert rho_h[2] == pytest.approx(2000.0, abs=1.0)


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
