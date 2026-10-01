"""Tests for missionstudio/scenarios/templates/*.json -- the education/
starter-template scenarios (see that directory's own README). Basilisk
-free: these only exercise schema.scenario.load_scenario()/validate(),
the same path the GUI's File > Open and the CLI's `validate`/`run`
subcommands go through, never an actual Basilisk propagation.
"""

from pathlib import Path

import pytest

from missionstudio.schema import load_scenario

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "missionstudio" / "scenarios" / "templates"
_TEMPLATE_PATHS = sorted(_TEMPLATES_DIR.glob("*.json"))


def test_at_least_one_template_exists():
    # A guard against the glob above silently matching nothing (e.g. the
    # directory got renamed/moved) and every parametrized test below
    # collecting zero cases, which would pass "successfully" while
    # testing nothing at all.
    assert len(_TEMPLATE_PATHS) >= 14


@pytest.mark.parametrize("path", _TEMPLATE_PATHS, ids=lambda p: p.name)
def test_template_loads_and_validates(path):
    scenario = load_scenario(path)
    scenario.validate()  # must not raise


@pytest.mark.parametrize("path", _TEMPLATE_PATHS, ids=lambda p: p.name)
def test_template_has_at_least_one_spacecraft(path):
    scenario = load_scenario(path)
    assert len(scenario.spacecraft) >= 1


@pytest.mark.parametrize("path", _TEMPLATE_PATHS, ids=lambda p: p.name)
def test_template_has_a_substantial_description(path):
    """Every template's whole point is to explain a concept -- a blank or
    one-line description would defeat that, so this is checked directly
    rather than just trusting the generator script forever gets it right.
    """
    scenario = load_scenario(path)
    assert len(scenario.description) > 200


@pytest.mark.parametrize("path", _TEMPLATE_PATHS, ids=lambda p: p.name)
def test_template_round_trips_through_save_load(path, tmp_path):
    scenario = load_scenario(path)
    out_path = tmp_path / path.name
    scenario.save(out_path)
    round_tripped = load_scenario(out_path)
    round_tripped.validate()
    assert round_tripped.to_dict() == scenario.to_dict()


def test_walker_constellation_template_has_six_uniquely_named_satellites():
    scenario = load_scenario(_TEMPLATES_DIR / "04_walker_constellation.json")
    names = [sc.name for sc in scenario.spacecraft]
    assert len(names) == 6
    assert len(set(names)) == 6


def test_mission_sequence_template_has_a_maneuver_command():
    scenario = load_scenario(_TEMPLATES_DIR / "08_mission_sequence_orbit_raise.json")
    kinds = [c.kind for c in scenario.mission_sequence]
    assert "maneuver" in kinds


def test_monte_carlo_template_has_monte_carlo_enabled():
    scenario = load_scenario(_TEMPLATES_DIR / "09_monte_carlo_dispersion_analysis.json")
    assert scenario.monte_carlo.enabled
    assert len(scenario.monte_carlo.dispersions) >= 1


def test_gravity_gradient_template_has_no_attitude_control_and_an_elongated_inertia():
    """Regression guard for '10's own stated lesson: gravity-gradient
    torque is identically zero for a spherically-symmetric inertia, and
    invisible behind an active controller that just rejects it as one
    more disturbance -- both conditions must hold for the template to
    actually demonstrate the effect it claims to.
    """
    scenario = load_scenario(_TEMPLATES_DIR / "10_gravity_gradient_torque.json")
    sat = scenario.spacecraft[0]
    assert sat.fsw_mode is None
    assert sat.enable_gravity_gradient is True
    ixx, iyy, izz = sat.inertia_kg_m2[0], sat.inertia_kg_m2[4], sat.inertia_kg_m2[8]
    assert not (ixx == iyy == izz)


def test_thruster_attitude_control_template_has_only_thruster_actuators():
    scenario = load_scenario(_TEMPLATES_DIR / "11_thruster_attitude_control.json")
    sat = scenario.spacecraft[0]
    kinds = {a.kind for a in sat.actuators}
    assert kinds == {"thruster"}
    assert len(sat.actuators) >= 6  # fewer cannot produce a pure 3-axis torque solution
    assert sat.fsw_mode is not None


def test_momentum_dumping_template_mixes_reaction_wheel_and_thruster_actuators():
    scenario = load_scenario(_TEMPLATES_DIR / "12_reaction_wheel_momentum_dumping.json")
    sat = scenario.spacecraft[0]
    kinds = {a.kind for a in sat.actuators}
    assert kinds == {"reaction_wheel", "thruster"}
    assert sat.momentum_dumping is not None
    assert sat.momentum_dumping.hs_max > 0


def test_magnetic_momentum_management_template_mixes_reaction_wheel_and_mtb_actuators():
    scenario = load_scenario(_TEMPLATES_DIR / "13_magnetic_torque_rod_momentum_management.json")
    sat = scenario.spacecraft[0]
    kinds = {a.kind for a in sat.actuators}
    assert kinds == {"reaction_wheel", "magnetic_torque_rod"}
    assert sat.magnetic_momentum_management is not None
    num_rw = sum(1 for a in sat.actuators if a.kind == "reaction_wheel")
    assert len(sat.magnetic_momentum_management.wheel_speed_biases_rad_s) == num_rw


def test_css_sun_heading_estimation_template_wires_use_css_estimation():
    scenario = load_scenario(_TEMPLATES_DIR / "14_css_sun_heading_estimation.json")
    sat = scenario.spacecraft[0]
    assert sat.fsw_mode == "sunSafePoint"
    assert sat.fsw_params.get("use_css_estimation") is True
    assert sum(1 for s in sat.sensors if s.kind == "coarse_sun_sensor") == 8
    assert "sun" in scenario.gravity.third_body_perturbers
    # DEFAULT_MRP_GAINS (K=3.5/P=30) scaled down for this template's 5 kg*m^2
    # hub -- see scripts/_generate_templates.py's own comment and
    # HISTORY.md for why an unscaled default never converges here.
    assert sat.control_params.get("K", 3.5) < 1.0
    assert sat.control_params.get("P", 30.0) < 1.0


def test_phasing_template_pairs_phasing_keeping_with_station_keeping():
    """Regression guard for PhasingKeepingConfig's own documented
    requirement (also enforced by Scenario.validate() itself) -- if a
    future edit to this template ever drops the paired station_keeping,
    this fails clearly instead of only failing deep inside validate()'s
    generic error message.
    """
    scenario = load_scenario(_TEMPLATES_DIR / "05_formation_flying_phasing.json")
    follower = next(sc for sc in scenario.spacecraft if sc.phasing_keeping is not None)
    assert follower.station_keeping is not None
