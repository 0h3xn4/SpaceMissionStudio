"""Tests for missionstudio.engine.spaceweather -- no Basilisk import, runs
anywhere. The CelesTrak network fetch itself is exercised against whatever
network this test runs on (it will genuinely fail in an offline/blocked
sandbox, which is itself the thing test_resolve_celestrak_unreachable_falls_back_to_synthetic
below checks: the fallback chain has to work when the network call fails,
not just when it's mocked to fail).
"""

from datetime import datetime

import pytest

from missionstudio.engine import spaceweather as sw


def test_generate_synthetic_passes_its_own_validation(tmp_path):
    start, end = datetime(2030, 1, 1), datetime(2030, 1, 10)
    path = sw.generate_synthetic(start, end, tmp_path / "synth.csv")
    result = sw.validate_file(path, start, end)
    assert result.ok, result.message


def test_generate_synthetic_is_deterministic(tmp_path):
    start, end = datetime(2030, 1, 1), datetime(2030, 1, 5)
    path_a = sw.generate_synthetic(start, end, tmp_path / "a.csv", seed=7)
    path_b = sw.generate_synthetic(start, end, tmp_path / "b.csv", seed=7)
    assert path_a.read_text() == path_b.read_text()


def test_validate_file_rejects_missing_file(tmp_path):
    result = sw.validate_file(tmp_path / "nope.csv", datetime(2030, 1, 1), datetime(2030, 1, 2))
    assert not result.ok
    assert "does not exist" in result.message


def test_validate_file_rejects_missing_required_columns(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("DATE,AP1\n2030-01-01,5\n")
    result = sw.validate_file(path, datetime(2030, 1, 1), datetime(2030, 1, 2))
    assert not result.ok
    assert "AP_AVG" in result.message


def test_validate_file_rejects_insufficient_date_range(tmp_path):
    path = tmp_path / "short.csv"
    header = ",".join(sw.REQUIRED_COLUMNS)
    row = "2030-01-01," + ",".join(["5"] * 8) + ",5,100,100"
    path.write_text(header + "\n" + row + "\n")
    result = sw.validate_file(path, datetime(2030, 1, 1), datetime(2030, 1, 10))
    assert not result.ok
    assert not result.covers_range


def test_validate_file_covers_range_ignores_time_of_day(tmp_path):
    """Regression test for an audit finding: covers_range used to compare
    a date-only (midnight) timestamp parsed from the CSV's last row
    against a full end_utc datetime, so a file whose last row IS the
    scenario's own end date was wrongly rejected whenever end_utc carried
    a non-zero time-of-day (daily-resolution data covers its whole day,
    not just its midnight instant). service.py builds end_utc as
    datetime.fromisoformat(scenario.epoch_utc) + a timedelta, and
    Scenario.validate() does not require epoch_utc to be midnight, so this
    is a real, reachable scenario shape.
    """
    path = tmp_path / "covers.csv"
    header = ",".join(sw.REQUIRED_COLUMNS)
    row_tail = "," + ",".join(["5"] * 8) + ",5,100,100"
    path.write_text(header + "\n" + "2030-01-01" + row_tail + "\n" + "2030-01-05" + row_tail + "\n")

    start_utc = datetime(2030, 1, 1, 14, 0, 0)
    end_utc = datetime(2030, 1, 5, 14, 0, 0)  # same calendar date as the file's last row, but later in the day
    result = sw.validate_file(path, start_utc, end_utc)

    assert result.covers_range, result.message


def test_validate_file_detects_unsorted_dates(tmp_path):
    path = tmp_path / "unsorted.csv"
    header = ",".join(sw.REQUIRED_COLUMNS)
    row_tail = "," + ",".join(["5"] * 8) + ",5,100,100"
    path.write_text(header + "\n" + "2030-01-05" + row_tail + "\n" + "2030-01-01" + row_tail + "\n")
    result = sw.validate_file(path, datetime(2030, 1, 1), datetime(2030, 1, 5))
    assert not result.ok
    assert result.unsorted


def test_validate_file_detects_duplicate_dates(tmp_path):
    path = tmp_path / "dupe.csv"
    header = ",".join(sw.REQUIRED_COLUMNS)
    row_tail = "," + ",".join(["5"] * 8) + ",5,100,100"
    path.write_text(header + "\n" + "2030-01-01" + row_tail + "\n" + "2030-01-01" + row_tail + "\n")
    result = sw.validate_file(path, datetime(2030, 1, 1), datetime(2030, 1, 1))
    assert not result.ok
    assert result.duplicate_dates == ["2030-01-01"]


def test_resolve_synthetic_source_returns_flagged_synthetic(tmp_path):
    resolved = sw.resolve("synthetic", datetime(2030, 1, 1), datetime(2030, 1, 5), cache_dir=tmp_path)
    assert resolved.is_synthetic
    assert any("SYNTHETIC" in w for w in resolved.warnings)


def test_resolve_local_file_source_uses_exact_file(tmp_path):
    start, end = datetime(2030, 1, 1), datetime(2030, 1, 5)
    local_path = sw.generate_synthetic(start, end, tmp_path / "mine.csv")
    resolved = sw.resolve("local_file", start, end, local_file_path=str(local_path))
    assert resolved.path == local_path
    assert not resolved.is_synthetic


def test_resolve_local_file_source_raises_if_missing():
    with pytest.raises(sw.SpaceWeatherError, match="does not exist"):
        sw.resolve("local_file", datetime(2030, 1, 1), datetime(2030, 1, 5), local_file_path="/nonexistent.csv")


def test_resolve_local_file_source_raises_without_path():
    with pytest.raises(sw.SpaceWeatherError, match="local_file_path was not set"):
        sw.resolve("local_file", datetime(2030, 1, 1), datetime(2030, 1, 5))


def test_resolve_unknown_source_raises():
    with pytest.raises(sw.SpaceWeatherError, match="unknown space_weather.source"):
        sw.resolve("magic", datetime(2030, 1, 1), datetime(2030, 1, 5))


def test_resolve_celestrak_falls_back_when_unreachable_or_insufficient(tmp_path):
    """This is the fallback chain the user explicitly asked for: fetch from
    CelesTrak; if that isn't possible, fall back (here: no local_file_path
    was given, so all the way to synthetic), never raising and never
    silently returning an unusable/empty result. Genuinely exercises the
    real network call (no mocking) -- in this project's own development
    sandbox that call is blocked by network policy, which is exactly the
    "not possible" case this test proves is handled gracefully; on a
    machine where CelesTrak IS reachable, this either succeeds via the
    real fetch (is_synthetic False) or still falls back correctly if the
    fetched data doesn't cover the (deliberately far-future) requested
    range -- either outcome is a pass.
    """
    start, end = datetime(2030, 1, 1), datetime(2030, 1, 5)
    resolved = sw.resolve("celestrak", start, end, cache_dir=tmp_path)
    assert resolved.path.exists()
    # A clean, real CelesTrak fetch (is_synthetic False, no warnings) is a
    # perfectly good outcome -- see the docstring above, "either outcome is
    # a pass". A warning is only expected on the FALLBACK path
    # (is_synthetic True or a warning-carrying local_file_path substitution);
    # requiring one unconditionally was a real bug in this test, caught on a
    # machine where CelesTrak is actually reachable (this project's own
    # development sandbox never exercised the "success" branch, only the
    # "blocked" one, so this was never caught until now).
    if resolved.is_synthetic:
        assert resolved.warnings, "expected at least one warning explaining the fallback to synthetic data"
    # Whatever happened, the file it points to must itself be valid.
    result = sw.validate_file(resolved.path, start, end)
    assert result.ok, f"resolve() returned an unusable file: {result.message}"


# -- Conservative ("worst-case") drag margin -------------------------------
# See this module's own docstring, "Conservative ('worst-case') drag
# margin", for the real user request this implements. generate_synthetic()
# stands in for "a real historical CSV" purely as test data here (its
# solar-cycle-shaped F10.7 and storm-episode Ap give a genuinely varied
# distribution to compute a percentile over) -- compute_worst_case_activity
# itself is source-agnostic file parsing + percentile math; the "must
# actually BE real data" policy is enforced one layer up, in resolve()'s
# own source handling, and tested separately below.

def _write_long_history(tmp_path, years: int = 15, seed: int = 3):
    start = datetime(2000, 1, 1)
    end = datetime(2000 + years, 1, 1)
    return sw.generate_synthetic(start, end, tmp_path / "history.csv", seed=seed), start, end


def test_compute_worst_case_activity_matches_numpy_percentile(tmp_path):
    import numpy as np

    path, _start, _end = _write_long_history(tmp_path)
    f107_all, ap_all = sw._load_historical_activity(path)

    f107_p, ap_p, n_samples = sw.compute_worst_case_activity(path, 95.0)

    assert n_samples == len(f107_all) == len(ap_all)
    assert f107_p == pytest.approx(np.percentile(f107_all, 95.0))
    assert ap_p == pytest.approx(np.percentile(ap_all, 95.0))


def test_compute_worst_case_activity_rejects_short_history(tmp_path):
    start, end = datetime(2030, 1, 1), datetime(2030, 6, 1)  # well under a year
    path = sw.generate_synthetic(start, end, tmp_path / "short.csv")
    with pytest.raises(sw.SpaceWeatherError, match="need at least"):
        sw.compute_worst_case_activity(path, 95.0)


def test_generate_worst_case_holds_values_constant_and_validates(tmp_path):
    start, end = datetime(2030, 1, 1), datetime(2030, 1, 10)
    path = sw.generate_worst_case(230.5, 45.0, start, end, tmp_path / "worst.csv")

    result = sw.validate_file(path, start, end)
    assert result.ok, result.message

    import csv as _csv
    with open(path, newline="") as f:
        rows = list(_csv.DictReader(f))
    assert rows  # non-empty
    for row in rows:
        assert float(row["F10.7_OBS"]) == pytest.approx(230.5)
        assert float(row["F10.7_OBS_CENTER81"]) == pytest.approx(230.5)
        assert float(row["AP_AVG"]) == pytest.approx(45.0)
        for i in range(1, 9):
            assert float(row[f"AP{i}"]) == pytest.approx(45.0)


def test_resolve_conservative_local_file_computes_real_percentile(tmp_path):
    import numpy as np

    history_path, _hist_start, _hist_end = _write_long_history(tmp_path)
    f107_all, ap_all = sw._load_historical_activity(history_path)
    expected_f107 = np.percentile(f107_all, 95.0)
    expected_ap = np.percentile(ap_all, 95.0)

    scenario_start, scenario_end = datetime(2030, 1, 1), datetime(2030, 1, 5)
    resolved = sw.resolve("local_file", scenario_start, scenario_end, local_file_path=str(history_path),
                           cache_dir=tmp_path / "cache", activity_level="conservative", activity_percentile=95.0)

    assert resolved.is_synthetic  # not real per-day data for THESE dates -- see resolve()'s own docstring
    assert any("CONSERVATIVE" in w for w in resolved.warnings)
    result = sw.validate_file(resolved.path, scenario_start, scenario_end)
    assert result.ok, result.message

    import csv as _csv
    with open(resolved.path, newline="") as f:
        first_row = next(_csv.DictReader(f))
    # abs=0.05: generate_worst_case's CSV rounds to 1 decimal place, so the
    # round-tripped value can differ from the unrounded percentile by up to
    # half of that -- real float formatting, not slack for a bug.
    assert float(first_row["F10.7_OBS"]) == pytest.approx(expected_f107, abs=0.05)
    assert float(first_row["AP_AVG"]) == pytest.approx(expected_ap, abs=0.05)


def test_resolve_conservative_synthetic_source_raises():
    with pytest.raises(sw.SpaceWeatherError, match="needs REAL historical"):
        sw.resolve("synthetic", datetime(2030, 1, 1), datetime(2030, 1, 5), activity_level="conservative")


def test_resolve_conservative_local_file_without_path_raises():
    with pytest.raises(sw.SpaceWeatherError, match="local_file_path was not set"):
        sw.resolve("local_file", datetime(2030, 1, 1), datetime(2030, 1, 5), activity_level="conservative")


def test_resolve_unknown_activity_level_raises():
    with pytest.raises(sw.SpaceWeatherError, match="unknown space_weather.activity_level"):
        sw.resolve("synthetic", datetime(2030, 1, 1), datetime(2030, 1, 5), activity_level="extreme")


def test_fetch_sends_a_browser_like_user_agent(tmp_path, monkeypatch):
    """Regression guard, applied proactively here on the precedent of a
    real bug a user hit with gui.vizard_launcher.fetch_vizard's own
    identical bare-urlopen pattern against a different host: urllib's own
    default User-Agent ("Python-urllib/<version>") got "HTTPError: 403
    Forbidden" from that other host's basic bot-protection. Asserts the
    actual outgoing urllib.request.Request carries a real User-Agent
    header, not just that some response gets consumed.
    """
    import io

    captured = {}

    class _FakeResponse:
        def __init__(self, data):
            self._buf = io.BytesIO(data)

        def read(self, n=-1):
            return self._buf.read(n)

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

    def _fake_urlopen(request, timeout=None):
        captured["request"] = request
        return _FakeResponse(b"DATE,AP1,AP2,AP3,AP4,AP5,AP6,AP7,AP8,AP_AVG,F10.7_OBS,F10.7_OBS_CENTER81\n")

    monkeypatch.setattr(sw.urllib.request, "urlopen", _fake_urlopen)

    sw.fetch(cache_dir=tmp_path)

    sent_request = captured["request"]
    assert isinstance(sent_request, sw.urllib.request.Request)
    user_agent = sent_request.get_header("User-agent")  # urllib title-cases header names internally
    assert user_agent
    assert "python-urllib" not in user_agent.lower()
