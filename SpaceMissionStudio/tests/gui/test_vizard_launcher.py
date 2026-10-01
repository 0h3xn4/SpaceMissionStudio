"""Tests for gui.vizard_launcher -- path lookup/persistence, process
launch, and fetching a pre-built Vizard binary, all with real
filesystem/QSettings I/O redirected into tmp_path (never touching the
real developer machine's actual Vizard install or settings store) and
the network itself always mocked (urllib.request.urlopen -- this module's
own docstring notes the real fetch is unverified end-to-end in this
project's development sandbox, hanspeterschaub.info being blocked here).
"""

import io
import subprocess
import sys
import zipfile

import pytest
from PySide6.QtCore import QSettings

pytestmark = pytest.mark.requires_gui


def _settings(tmp_path):
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


def test_find_returns_none_with_no_remembered_path_and_nothing_on_disk(tmp_path, monkeypatch):
    from spacemissionstudio.gui import vizard_launcher

    monkeypatch.setattr(vizard_launcher, "_candidate_roots", lambda: [tmp_path / "does_not_exist"])
    assert vizard_launcher.find_vizard_executable(settings=_settings(tmp_path)) is None


def test_remember_then_find_returns_the_remembered_path(tmp_path, monkeypatch):
    from spacemissionstudio.gui import vizard_launcher

    fake_exe = tmp_path / "Vizard.x86_64"
    fake_exe.write_bytes(b"")
    settings = _settings(tmp_path)

    vizard_launcher.remember_vizard_executable(fake_exe, settings=settings)
    assert vizard_launcher.find_vizard_executable(settings=settings) == fake_exe


def test_remembered_path_that_no_longer_exists_falls_back_to_search(tmp_path, monkeypatch):
    from spacemissionstudio.gui import vizard_launcher

    settings = _settings(tmp_path)
    vizard_launcher.remember_vizard_executable(tmp_path / "gone" / "Vizard.x86_64", settings=settings)

    search_root = tmp_path / "search_root"
    search_root.mkdir()
    found_exe = search_root / vizard_launcher._EXECUTABLE_NAME
    found_exe.write_bytes(b"")
    monkeypatch.setattr(vizard_launcher, "_candidate_roots", lambda: [search_root])

    assert vizard_launcher.find_vizard_executable(settings=settings) == found_exe


def test_search_finds_executable_directly_in_a_candidate_root(tmp_path, monkeypatch):
    from spacemissionstudio.gui import vizard_launcher

    root = tmp_path / "Desktop"
    root.mkdir()
    exe = root / vizard_launcher._EXECUTABLE_NAME
    exe.write_bytes(b"")
    monkeypatch.setattr(vizard_launcher, "_candidate_roots", lambda: [root])

    assert vizard_launcher.find_vizard_executable(settings=_settings(tmp_path)) == exe


def test_search_finds_executable_one_level_down_in_a_candidate_root(tmp_path, monkeypatch):
    """Covers "unzipped into its own subfolder" (e.g. Desktop/Vizard_Windows64/Vizard.exe)."""
    from spacemissionstudio.gui import vizard_launcher

    root = tmp_path / "Downloads"
    nested = root / "Vizard_Windows64"
    nested.mkdir(parents=True)
    exe = nested / vizard_launcher._EXECUTABLE_NAME
    exe.write_bytes(b"")
    monkeypatch.setattr(vizard_launcher, "_candidate_roots", lambda: [root])

    assert vizard_launcher.find_vizard_executable(settings=_settings(tmp_path)) == exe


def test_search_skips_a_nonexistent_root_without_raising(tmp_path, monkeypatch):
    from spacemissionstudio.gui import vizard_launcher

    real_root = tmp_path / "real"
    real_root.mkdir()
    exe = real_root / vizard_launcher._EXECUTABLE_NAME
    exe.write_bytes(b"")
    # A missing root ahead of a real one must be skipped, not raise.
    monkeypatch.setattr(vizard_launcher, "_candidate_roots", lambda: [tmp_path / "missing", real_root])

    assert vizard_launcher.find_vizard_executable(settings=_settings(tmp_path)) == exe


def test_launch_starts_the_given_executable_directly_on_non_macos(tmp_path, monkeypatch):
    from spacemissionstudio.gui import vizard_launcher

    monkeypatch.setattr(vizard_launcher.sys, "platform", "linux")
    exe = tmp_path / "Vizard.x86_64"
    exe.write_bytes(b"")

    captured = {}

    class _FakeProcess:
        pid = 4242

        def poll(self):
            return None

    def fake_popen(args):
        captured["args"] = args
        return _FakeProcess()

    monkeypatch.setattr(vizard_launcher.subprocess, "Popen", fake_popen)
    result = vizard_launcher.launch_vizard(exe)

    assert captured["args"] == [str(exe)]
    assert result.pid == 4242


def test_launch_appends_direct_comm_flag_when_given(tmp_path, monkeypatch):
    """See DEFAULT_LIVE_STREAM_ADDRESS's own comment: -directComm is what
    makes Vizard connect to a live-stream run automatically instead of
    sitting on its own manual launcher screen.
    """
    from spacemissionstudio.gui import vizard_launcher

    monkeypatch.setattr(vizard_launcher.sys, "platform", "linux")
    exe = tmp_path / "Vizard.x86_64"
    exe.write_bytes(b"")

    captured = {}
    monkeypatch.setattr(vizard_launcher.subprocess, "Popen", lambda args: captured.setdefault("args", args))

    vizard_launcher.launch_vizard(exe, direct_comm_address="tcp://localhost:5556")

    assert captured["args"] == [str(exe), "-directComm", "tcp://localhost:5556"]


def test_launch_omits_direct_comm_flag_when_not_given(tmp_path, monkeypatch):
    from spacemissionstudio.gui import vizard_launcher

    monkeypatch.setattr(vizard_launcher.sys, "platform", "linux")
    exe = tmp_path / "Vizard.x86_64"
    exe.write_bytes(b"")

    captured = {}
    monkeypatch.setattr(vizard_launcher.subprocess, "Popen", lambda args: captured.setdefault("args", args))

    vizard_launcher.launch_vizard(exe)

    assert captured["args"] == [str(exe)]


def test_launch_resolves_macos_app_bundle_to_its_inner_binary(tmp_path, monkeypatch):
    from spacemissionstudio.gui import vizard_launcher

    monkeypatch.setattr(vizard_launcher.sys, "platform", "darwin")
    bundle = tmp_path / "Vizard.app"
    macos_dir = bundle / "Contents" / "MacOS"
    macos_dir.mkdir(parents=True)
    inner_binary = macos_dir / "Vizard"
    inner_binary.write_bytes(b"")

    captured = {}
    monkeypatch.setattr(vizard_launcher.subprocess, "Popen", lambda args: captured.setdefault("args", args))

    vizard_launcher.launch_vizard(bundle)
    assert captured["args"] == [str(inner_binary)]


def test_launch_raises_a_clear_error_for_an_empty_macos_bundle(tmp_path, monkeypatch):
    from spacemissionstudio.gui import vizard_launcher

    monkeypatch.setattr(vizard_launcher.sys, "platform", "darwin")
    bundle = tmp_path / "Vizard.app"
    (bundle / "Contents" / "MacOS").mkdir(parents=True)

    with pytest.raises(FileNotFoundError, match="does not look like a valid macOS app bundle"):
        vizard_launcher.launch_vizard(bundle)


# -- fetch_vizard() -- downloading and extracting a pre-built Vizard -------

def test_download_url_for_platform_covers_all_three():
    from spacemissionstudio.gui import vizard_launcher

    for platform_value, expected_substring in (("darwin", "macOS"), ("win32", "Windows"), ("linux", "Linux")):
        vizard_launcher.sys.platform = platform_value
        try:
            assert expected_substring in vizard_launcher._download_url_for_platform()
        finally:
            vizard_launcher.sys.platform = sys.platform  # restore -- this one doesn't use monkeypatch


class _FakeUrlResponse:
    """Minimal stand-in for ``urllib.request.urlopen``'s return value --
    a context manager with a chunked ``.read(n)``, matching how
    :func:`fetch_vizard` actually reads it (cooperative-cancellation
    checks happen BETWEEN chunks).
    """

    def __init__(self, data: bytes):
        self._data = data
        self._pos = 0

    def read(self, n: int = -1) -> bytes:
        if n < 0:
            chunk, self._pos = self._data[self._pos:], len(self._data)
            return chunk
        chunk = self._data[self._pos: self._pos + n]
        self._pos += len(chunk)
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def _build_zip(entries: dict) -> bytes:
    """``entries``: {archive_path: bytes_content}."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    return buf.getvalue()


def test_fetch_vizard_downloads_extracts_and_finds_the_executable(tmp_path, monkeypatch):
    from spacemissionstudio.gui import vizard_launcher

    monkeypatch.setattr(vizard_launcher.sys, "platform", "linux")
    zip_bytes = _build_zip({"Vizard_Linux/Vizard.x86_64": b"fake binary contents"})
    monkeypatch.setattr(vizard_launcher.urllib.request, "urlopen", lambda url, timeout=None: _FakeUrlResponse(zip_bytes))

    executable = vizard_launcher.fetch_vizard(dest_dir=tmp_path)

    assert executable.name == "Vizard.x86_64"
    assert executable.exists()


def test_fetch_vizard_sends_a_browser_like_user_agent(tmp_path, monkeypatch):
    """Regression guard for a real bug a user hit on their own machine:
    urllib's own default User-Agent ("Python-urllib/<version>") got
    "HTTPError: 403 Forbidden" from hanspeterschaub.info -- this asserts
    the actual outgoing urllib.request.Request carries a real
    User-Agent header, not just that SOME response gets consumed (the
    other fetch_vizard tests wouldn't have caught this regressing, since
    their fake urlopen doesn't inspect what it was called with).
    """
    from spacemissionstudio.gui import vizard_launcher

    monkeypatch.setattr(vizard_launcher.sys, "platform", "linux")
    zip_bytes = _build_zip({"Vizard.x86_64": b"fake binary contents"})
    captured = {}

    def _fake_urlopen(request, timeout=None):
        captured["request"] = request
        return _FakeUrlResponse(zip_bytes)

    monkeypatch.setattr(vizard_launcher.urllib.request, "urlopen", _fake_urlopen)

    vizard_launcher.fetch_vizard(dest_dir=tmp_path)

    sent_request = captured["request"]
    assert isinstance(sent_request, vizard_launcher.urllib.request.Request)
    user_agent = sent_request.get_header("User-agent")  # urllib title-cases header names internally
    assert user_agent
    assert "python-urllib" not in user_agent.lower()


def test_fetch_vizard_sets_the_executable_bit_on_non_windows(tmp_path, monkeypatch):
    import stat

    from spacemissionstudio.gui import vizard_launcher

    monkeypatch.setattr(vizard_launcher.sys, "platform", "linux")
    zip_bytes = _build_zip({"Vizard.x86_64": b"fake binary contents"})
    monkeypatch.setattr(vizard_launcher.urllib.request, "urlopen", lambda url, timeout=None: _FakeUrlResponse(zip_bytes))

    executable = vizard_launcher.fetch_vizard(dest_dir=tmp_path)

    assert executable.stat().st_mode & stat.S_IXUSR


def test_fetch_vizard_reports_network_failure(tmp_path, monkeypatch):
    from spacemissionstudio.gui import vizard_launcher

    def _raise(url, timeout=None):
        raise OSError("connection refused")

    monkeypatch.setattr(vizard_launcher.urllib.request, "urlopen", _raise)

    with pytest.raises(vizard_launcher.VizardFetchError, match="could not download"):
        vizard_launcher.fetch_vizard(dest_dir=tmp_path)


def test_fetch_vizard_reports_a_corrupt_zip(tmp_path, monkeypatch):
    from spacemissionstudio.gui import vizard_launcher

    monkeypatch.setattr(vizard_launcher.urllib.request, "urlopen",
                         lambda url, timeout=None: _FakeUrlResponse(b"not actually a zip file"))

    with pytest.raises(vizard_launcher.VizardFetchError, match="not a valid zip file"):
        vizard_launcher.fetch_vizard(dest_dir=tmp_path)


def test_fetch_vizard_reports_a_zip_with_no_recognizable_executable(tmp_path, monkeypatch):
    from spacemissionstudio.gui import vizard_launcher

    monkeypatch.setattr(vizard_launcher.sys, "platform", "linux")
    zip_bytes = _build_zip({"readme.txt": b"not an executable"})
    monkeypatch.setattr(vizard_launcher.urllib.request, "urlopen", lambda url, timeout=None: _FakeUrlResponse(zip_bytes))

    with pytest.raises(vizard_launcher.VizardFetchError, match="could not find"):
        vizard_launcher.fetch_vizard(dest_dir=tmp_path)


def test_fetch_vizard_honors_cooperative_cancellation(tmp_path, monkeypatch):
    from spacemissionstudio.gui import vizard_launcher

    zip_bytes = _build_zip({"Vizard.x86_64": b"x" * (vizard_launcher._DOWNLOAD_CHUNK_BYTES * 3)})
    monkeypatch.setattr(vizard_launcher.urllib.request, "urlopen", lambda url, timeout=None: _FakeUrlResponse(zip_bytes))

    with pytest.raises(vizard_launcher.VizardFetchError, match="cancelled"):
        vizard_launcher.fetch_vizard(dest_dir=tmp_path, should_cancel=lambda: True)


def test_fetch_vizard_rejects_a_response_over_the_size_cap(tmp_path, monkeypatch):
    from spacemissionstudio.gui import vizard_launcher

    monkeypatch.setattr(vizard_launcher, "_MAX_DOWNLOAD_BYTES", 10)
    zip_bytes = _build_zip({"Vizard.x86_64": b"x" * 1000})
    monkeypatch.setattr(vizard_launcher.urllib.request, "urlopen", lambda url, timeout=None: _FakeUrlResponse(zip_bytes))

    with pytest.raises(vizard_launcher.VizardFetchError, match="exceeded"):
        vizard_launcher.fetch_vizard(dest_dir=tmp_path)


def test_fetch_vizard_reports_progress_status(tmp_path, monkeypatch):
    from spacemissionstudio.gui import vizard_launcher

    monkeypatch.setattr(vizard_launcher.sys, "platform", "linux")
    zip_bytes = _build_zip({"Vizard.x86_64": b"fake binary contents"})
    monkeypatch.setattr(vizard_launcher.urllib.request, "urlopen", lambda url, timeout=None: _FakeUrlResponse(zip_bytes))

    statuses = []
    vizard_launcher.fetch_vizard(dest_dir=tmp_path, on_status=statuses.append)

    assert any("Downloading" in s for s in statuses)
    assert any("Extracting" in s for s in statuses)


def test_fetch_vizard_finds_the_executable_inside_a_same_named_wrapper_folder(tmp_path, monkeypatch):
    """Confirmed against a real download, not assumed: AVS's own
    Vizard_Linux.zip wraps its contents in a top-level folder with the
    SAME name as the zip itself (Vizard_Linux/Vizard.x86_64) --
    extract_dir uses a fixed "extracted" name specifically so this
    doesn't produce a redundant-looking nested path
    (.../extracted/Vizard_Linux/Vizard.x86_64, not
    .../Vizard_Linux/Vizard_Linux/Vizard.x86_64).
    """
    from spacemissionstudio.gui import vizard_launcher

    monkeypatch.setattr(vizard_launcher.sys, "platform", "linux")
    zip_bytes = _build_zip({"Vizard_Linux/Vizard.x86_64": b"fake binary contents"})
    monkeypatch.setattr(vizard_launcher.urllib.request, "urlopen", lambda url, timeout=None: _FakeUrlResponse(zip_bytes))

    executable = vizard_launcher.fetch_vizard(dest_dir=tmp_path)

    assert executable == tmp_path / "extracted" / "Vizard_Linux" / "Vizard.x86_64"


def test_fetch_vizard_clears_stale_files_from_an_earlier_extraction(tmp_path, monkeypatch):
    """extract_dir's name no longer varies per zip (see its own comment)
    -- a re-fetch must not silently leave behind files an OLDER .zip
    extracted that the NEWER one doesn't itself contain.
    """
    from spacemissionstudio.gui import vizard_launcher

    monkeypatch.setattr(vizard_launcher.sys, "platform", "linux")

    old_zip = _build_zip({"Vizard.x86_64": b"old version", "stale_leftover_file.txt": b"should not survive"})
    monkeypatch.setattr(vizard_launcher.urllib.request, "urlopen", lambda url, timeout=None: _FakeUrlResponse(old_zip))
    vizard_launcher.fetch_vizard(dest_dir=tmp_path)
    assert (tmp_path / "extracted" / "stale_leftover_file.txt").exists()

    new_zip = _build_zip({"Vizard.x86_64": b"new version"})
    monkeypatch.setattr(vizard_launcher.urllib.request, "urlopen", lambda url, timeout=None: _FakeUrlResponse(new_zip))
    executable = vizard_launcher.fetch_vizard(dest_dir=tmp_path)

    assert executable.read_bytes() == b"new version"
    assert not (tmp_path / "extracted" / "stale_leftover_file.txt").exists()


def test_safe_extract_rejects_a_zip_slip_entry(tmp_path):
    from spacemissionstudio.gui import vizard_launcher

    malicious_zip = tmp_path / "evil.zip"
    with zipfile.ZipFile(malicious_zip, "w") as zf:
        zf.writestr("../../etc/escaped", b"pwned")

    extract_dir = tmp_path / "extract_here"
    with pytest.raises(vizard_launcher.VizardFetchError, match="unsafe entry"):
        vizard_launcher._safe_extract(malicious_zip, extract_dir)


def test_safe_extract_allows_a_normal_zip(tmp_path):
    from spacemissionstudio.gui import vizard_launcher

    normal_zip = tmp_path / "fine.zip"
    with zipfile.ZipFile(normal_zip, "w") as zf:
        zf.writestr("subdir/file.txt", b"hello")

    extract_dir = tmp_path / "extract_here"
    vizard_launcher._safe_extract(normal_zip, extract_dir)

    assert (extract_dir / "subdir" / "file.txt").read_bytes() == b"hello"


# -- VizardFetchWorker -- the QThread wrapper -------------------------------

def test_vizard_fetch_worker_emits_finished_ok_on_success(tmp_path, monkeypatch, qtbot):
    from spacemissionstudio.gui import vizard_launcher

    fake_path = tmp_path / "Vizard.x86_64"
    monkeypatch.setattr(vizard_launcher, "fetch_vizard", lambda *a, **k: fake_path)

    worker = vizard_launcher.VizardFetchWorker(dest_dir=tmp_path)
    with qtbot.waitSignal(worker.finished_ok, timeout=5000) as blocker:
        worker.start()

    assert blocker.args == [str(fake_path)]


def test_vizard_fetch_worker_emits_failed_on_error(tmp_path, monkeypatch, qtbot):
    from spacemissionstudio.gui import vizard_launcher

    def _raise(*a, **k):
        raise vizard_launcher.VizardFetchError("could not download: boom")

    monkeypatch.setattr(vizard_launcher, "fetch_vizard", _raise)

    worker = vizard_launcher.VizardFetchWorker(dest_dir=tmp_path)
    with qtbot.waitSignal(worker.failed, timeout=5000) as blocker:
        worker.start()

    assert blocker.args == ["could not download: boom"]


def test_vizard_fetch_worker_request_cancel_is_passed_through(tmp_path, monkeypatch, qtbot):
    from spacemissionstudio.gui import vizard_launcher

    seen_should_cancel = {}

    def _fake_fetch(dest_dir, should_cancel=None, on_status=None):
        seen_should_cancel["callable"] = should_cancel
        return tmp_path / "Vizard.x86_64"

    monkeypatch.setattr(vizard_launcher, "fetch_vizard", _fake_fetch)

    worker = vizard_launcher.VizardFetchWorker(dest_dir=tmp_path)
    worker.request_cancel()
    with qtbot.waitSignal(worker.finished_ok, timeout=5000):
        worker.start()

    assert seen_should_cancel["callable"]() is True  # the Event was already set before start()
