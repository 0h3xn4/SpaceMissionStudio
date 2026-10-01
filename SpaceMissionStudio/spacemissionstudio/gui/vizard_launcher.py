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

"""Locating, fetching, and launching the external Vizard application -- a
separate, non-Python Unity app (see ``docs/source/Vizard/VizardDownload.rst``
in this checkout) that is NOT bundled with SpaceMissionStudio's own Python
package. This module only starts the standalone process and hands back a
way to tell whether it's still running; actually feeding it simulation
data (a playback ``.bin`` file or a live stream) is ``engine.vizard``'s
job, wired through ``SimulationService`` via
``gui.vizard_dialog.VizardRequest`` -- entirely separate from starting
the app itself.

Vizard's own download instructions say only "install the program in the
typical Applications folder or Desktop" -- there's no single guaranteed
install path, so :func:`find_vizard_executable` is inherently best
-effort: it checks a remembered path from a previous
:func:`remember_vizard_executable` call first (an exact answer the user
already gave us), then falls back to guessing a small set of common
per-OS install locations, and returns ``None`` if neither turns up
anything -- at which point the caller (``gui.main_window.MainWindow
.on_launch_vizard``) offers :func:`fetch_vizard` (automatic download) or
a manual browse prompt.

Real user request: "seamlessly integrate" Basilisk and Vizard instead of
building/installing each separately. A true single build step isn't
realistic (Vizard's own repository has no scripted/CLI build path at
all -- only an interactive Unity Editor GUI workflow, checked directly,
not assumed) and the two are deliberately separate PROCESSES at runtime
regardless (Vizard can play back a saved ``.bin`` file with zero
Basilisk involvement). What IS realistic, and what :func:`fetch_vizard`
does: skip building Vizard from source entirely by downloading AVS's own
published pre-built binary for this platform -- the exact same
``Vizard_<platform>.zip`` links ``docs/source/Vizard/VizardDownload.rst``
already points a human to, just fetched automatically instead.
"""

from __future__ import annotations

import shutil
import stat
import subprocess
import sys
import threading
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, List, Optional

from PySide6.QtCore import QSettings, QThread, Signal

_SETTINGS_KEY = "vizard/executable_path"

# engine.vizard/SimulationService never overrides vizInterface's own
# reqComProtocol="tcp"/reqComAddress="0.0.0.0"/reqPortNumber="5556"
# defaults (see docs/source/Vizard/vizardAdvanced/vizardLiveComm.rst) --
# "0.0.0.0" binds to all interfaces but is reachable locally via
# "localhost", so this is the address a live-stream run's Vizard
# instance actually needs to connect to. Passed to :func:`launch_vizard`
# as its ``-directComm`` command-line argument (see
# docs/source/Vizard/vizardAdvanced/vizardCommandLine.rst) so Vizard
# connects automatically instead of sitting on its own manual "Load Data
# Using One of the Following" launcher screen waiting for the user to
# type this address in by hand and click "Start Visualization" --
# direct user feedback: a live-stream run appeared to "do nothing" and
# then froze with Abort having no effect, because Basilisk's
# InitializeSimulation() blocks (inside native C++, no Python-level
# hook -- see gui.main_window.MainWindow.on_run()'s own comment) waiting
# for exactly that handshake, which never arrived.
DEFAULT_LIVE_STREAM_ADDRESS = "tcp://localhost:5556"

# The actual launchable binary/bundle name Vizard's own Unity build
# produces per platform (see VizardDownload.rst's Vizard_<platform>.zip
# contents) -- used to search candidate directories.
if sys.platform == "darwin":
    _EXECUTABLE_NAME = "Vizard.app"
elif sys.platform.startswith("win"):
    _EXECUTABLE_NAME = "Vizard.exe"
else:
    _EXECUTABLE_NAME = "Vizard.x86_64"


def _candidate_roots() -> List[Path]:
    """Best-effort per-OS locations to search, per VizardDownload.rst's
    own "install in the typical Applications folder or Desktop" guidance
    -- there's no single guaranteed location since Vizard ships as a
    .zip the user extracts wherever they like.
    """
    home = Path.home()
    if sys.platform == "darwin":
        return [Path("/Applications"), home / "Applications", home / "Desktop", home / "Downloads"]
    if sys.platform.startswith("win"):
        return [
            Path("C:/Program Files"), Path("C:/Program Files (x86)"),
            home / "Desktop", home / "Downloads", home,
        ]
    return [home / "Desktop", home / "Downloads", home]


def _search_candidate_roots() -> Optional[Path]:
    for root in _candidate_roots():
        if not root.is_dir():
            continue
        # Shallow search: the root itself, plus one level of
        # subdirectories -- covers both "unzipped straight into Desktop"
        # and "unzipped into its own Vizard/ or Vizard_Windows64/
        # subfolder", without an unbounded recursive walk of e.g. the
        # user's whole home directory.
        for candidate in (root / _EXECUTABLE_NAME, *sorted(root.glob(f"*/{_EXECUTABLE_NAME}"))):
            if candidate.exists():
                return candidate
    return None


class VizardFetchError(Exception):
    """Raised when fetching/installing a pre-built Vizard binary fails --
    network, HTTP, a corrupt/unsafe zip, or "extracted fine but no
    recognizable executable was inside it" are all reported here with a
    specific reason. Never returns a partial/unusable install for the
    caller to discover only later.
    """


# The exact three links docs/source/Vizard/VizardDownload.rst in the
# Basilisk checkout publishes -- AVS's own pre-built Vizard binaries, not
# a third-party mirror. sys.platform branching matches _EXECUTABLE_NAME's
# own above (darwin / win* / else-linux).
_DOWNLOAD_URLS = {
    "darwin": "https://hanspeterschaub.info/bskFiles/Vizard_macOS.zip",
    "win": "https://hanspeterschaub.info/bskFiles/Vizard_Windows64.zip",
    "linux": "https://hanspeterschaub.info/bskFiles/Vizard_Linux.zip",
}

DEFAULT_FETCH_DIR = Path.home() / ".cache" / "SpaceMissionStudio" / "vizard"

# Real user report: a plain urllib.request.urlopen(url) (no custom
# headers) against hanspeterschaub.info returned "HTTPError: 403
# Forbidden" -- confirmed against a real machine with real internet
# access, not this project's own sandbox network policy (that gives a
# distinguishable proxy-level CONNECT rejection instead, never an
# HTTPError from the destination server itself). The classic cause:
# urllib's own default User-Agent ("Python-urllib/<version>") gets
# fingerprinted and blocked by basic bot-protection on countless static
# -file hosts that have no issue with an ordinary browser downloading the
# exact same public file by hand -- this is a well-known, standard
# workaround (setting a realistic User-Agent), not an attempt to bypass
# any actual access control (VizardDownload.rst already publishes this
# exact link for anyone to click).
_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# [bytes] A Unity build is typically a few hundred MB -- cap well above
# that so a legitimate download never trips this, but refuse to buffer an
# unbounded response into memory. Same convention/value as
# engine.spaceweather's own _MAX_DOWNLOAD_BYTES, scaled up for a much
# larger expected payload (a Unity application build vs. a CSV).
_MAX_DOWNLOAD_BYTES = 2 * 1024 * 1024 * 1024
_DOWNLOAD_CHUNK_BYTES = 1024 * 1024  # [bytes] read size for cooperative cancellation between chunks


def _download_url_for_platform() -> str:
    if sys.platform == "darwin":
        return _DOWNLOAD_URLS["darwin"]
    if sys.platform.startswith("win"):
        return _DOWNLOAD_URLS["win"]
    return _DOWNLOAD_URLS["linux"]


def _safe_extract(zip_path: Path, extract_dir: Path) -> None:
    """``zipfile.extractall()`` with an explicit zip-slip guard -- refuses
    ANY entry whose name resolves outside ``extract_dir`` (an absolute
    path, or one using ``..`` to escape it) rather than relying solely on
    the extraction library's own built-in sanitization. The download URL
    itself is a hardcoded, trusted constant (not user-supplied), so this
    is defense in depth, not a response to a specific known issue with
    AVS's own published Vizard archives.
    """
    extract_dir = extract_dir.resolve()
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.namelist():
            resolved = (extract_dir / member).resolve()
            if extract_dir not in resolved.parents and resolved != extract_dir:
                raise VizardFetchError(f"{zip_path} contains an unsafe entry {member!r} (escapes {extract_dir})")
        zf.extractall(extract_dir)


def fetch_vizard(dest_dir: Optional[Path] = None, timeout_s: float = 30.0,
                  should_cancel: Optional[Callable[[], bool]] = None,
                  on_status: Optional[Callable[[str], None]] = None) -> Path:
    """Downloads and extracts AVS's own pre-built Vizard binary for this
    platform (see this module's own docstring -- the same links
    ``docs/source/Vizard/VizardDownload.rst`` already publishes for a
    human to follow manually) into ``dest_dir`` (default
    :data:`DEFAULT_FETCH_DIR`), then returns the path to the extracted
    executable. Raises :class:`VizardFetchError` on any failure -- never
    returns a partial/unusable path.

    ``should_cancel``, checked between each ``_DOWNLOAD_CHUNK_BYTES``
    chunk read, is the same cooperative-cancellation idiom
    ``gui.run_worker.RunWorker`` already uses for a running simulation --
    never a forced thread kill, which could leave a half-written file
    (see :class:`VizardFetchWorker`, this function's own GUI-thread
    wrapper, for where a real ``threading.Event`` comes from). A
    cancelled fetch raises :class:`VizardFetchError` too (with a message
    saying so), the same single error-reporting path as any other
    failure -- there is no separate "was it cancelled or did it
    genuinely fail" signal for the caller to check.

    Verification status: this project's own development sandbox can't
    reach ``hanspeterschaub.info`` at all (blocked at the organization
    egress-policy level, confirmed via the proxy's own status endpoint --
    the same host ``engine.kernels``'s SPICE-kernel fetch uses as a
    backup URL), so a real user ran this on their own machine instead --
    TWICE. First attempt got ``HTTPError: 403 Forbidden`` straight from
    the server -- root-caused (not guessed) to urllib's own default
    ``User-Agent`` header (``"Python-urllib/<version>"``) tripping basic
    bot-protection; fixed by sending a realistic browser ``User-Agent``
    instead (see :data:`_USER_AGENT`'s own comment -- this is a standard,
    widely-used workaround for exactly this kind of blocking, not an
    attempt to bypass any real access control on what
    ``VizardDownload.rst`` already publishes as a direct public download
    link). Second attempt, with that fix, genuinely succeeded end-to-end
    -- downloaded, extracted, and found a real, existing
    ``Vizard.x86_64`` executable. That same real run is also what caught
    AVS's actual ``.zip`` layout (a same-named top-level folder, e.g.
    ``Vizard_Linux/Vizard.x86_64``) producing a redundant-looking nested
    extraction path -- cosmetic, not a functional bug (the executable was
    still found correctly), fixed anyway (see ``extract_dir``'s own
    comment below).
    """
    dest_dir = Path(dest_dir) if dest_dir else DEFAULT_FETCH_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)

    url = _download_url_for_platform()
    zip_name = url.rsplit("/", 1)[-1]
    zip_path = dest_dir / zip_name

    if on_status:
        on_status(f"Downloading {url} ...")
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            chunks = []
            total = 0
            while True:
                if should_cancel is not None and should_cancel():
                    raise VizardFetchError("download cancelled")
                chunk = response.read(_DOWNLOAD_CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > _MAX_DOWNLOAD_BYTES:
                    raise VizardFetchError(
                        f"{url} response exceeded {_MAX_DOWNLOAD_BYTES} bytes -- refusing to buffer an "
                        f"unbounded download"
                    )
                chunks.append(chunk)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise VizardFetchError(f"could not download {url}: {exc}") from exc
    data = b"".join(chunks)

    tmp = zip_path.with_suffix(zip_path.suffix + ".part")
    tmp.write_bytes(data)
    tmp.replace(zip_path)  # atomic-ish: never leave a half-written file at zip_path

    # A plain "extracted" staging name, not one derived from the zip's own
    # filename: confirmed against a real download that AVS's own
    # Vizard_<platform>.zip already wraps its contents in a same-named
    # top-level folder (e.g. "Vizard_Linux/Vizard.x86_64") -- naming this
    # directory after the zip too produced a redundant-looking (though
    # harmless -- _search_one_root's own one-level-of-subdirectories
    # search still found it) nested path,
    # .../vizard/Vizard_Linux/Vizard_Linux/Vizard.x86_64.
    extract_dir = dest_dir / "extracted"
    if extract_dir.exists():
        # extract_dir's name no longer varies per zip (see the comment
        # above), so a re-fetch (e.g. after Vizard publishes an update)
        # would otherwise extract on TOP OF whatever an earlier version
        # left behind -- stale files a newer .zip doesn't itself contain
        # would silently survive. Cleared first so every fetch's result
        # reflects exactly what that fetch's own .zip contained.
        shutil.rmtree(extract_dir)
    if on_status:
        on_status(f"Extracting to {extract_dir} ...")
    try:
        _safe_extract(zip_path, extract_dir)
    except zipfile.BadZipFile as exc:
        raise VizardFetchError(f"{zip_path} is not a valid zip file: {exc}") from exc

    executable = _search_one_root(extract_dir)
    if executable is None:
        raise VizardFetchError(
            f"downloaded and extracted {url} to {extract_dir}, but could not find a {_EXECUTABLE_NAME} "
            f"inside it -- the download may be corrupt, or Vizard's published .zip layout has changed."
        )
    if sys.platform != "win32" and executable.is_file():
        # zip extraction doesn't reliably preserve the executable bit --
        # confirmed necessary for the Linux .x86_64 binary. A no-op on
        # macOS, where launch_vizard() resolves the .app bundle's own
        # Contents/MacOS/<binary> separately and chmods nothing itself.
        mode = executable.stat().st_mode
        executable.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return executable


def _search_one_root(root: Path) -> Optional[Path]:
    """Same shallow-search idiom as :func:`_search_candidate_roots` (the
    root itself, plus one level of subdirectories) -- Vizard's published
    .zip layout (a bare binary vs. nested inside its own folder) isn't
    documented, so this doesn't assume a specific structure.
    """
    for candidate in (root / _EXECUTABLE_NAME, *sorted(root.glob(f"*/{_EXECUTABLE_NAME}"))):
        if candidate.exists():
            return candidate
    return None


def find_vizard_executable(settings: Optional[QSettings] = None) -> Optional[Path]:
    """Returns a path to the Vizard executable/app bundle, or ``None`` if
    it can't be found automatically.
    """
    settings = settings if settings is not None else QSettings()
    remembered = settings.value(_SETTINGS_KEY, "", type=str)
    if remembered:
        path = Path(remembered)
        if path.exists():
            return path
    return _search_candidate_roots()


def remember_vizard_executable(path: Path, settings: Optional[QSettings] = None) -> None:
    """Persists ``path`` so the next :func:`find_vizard_executable` call
    (in this run or a future one) returns it directly, without needing to
    guess or ask the user again.
    """
    settings = settings if settings is not None else QSettings()
    settings.setValue(_SETTINGS_KEY, str(path))


def launch_vizard(executable_path: Path, direct_comm_address: Optional[str] = None) -> "subprocess.Popen[bytes]":
    """Starts Vizard as a background process and returns the
    :class:`subprocess.Popen` handle so the caller can poll whether it's
    still running (``.poll() is None``). On macOS this resolves an
    ``.app`` bundle to its actual Mach-O binary inside
    ``Contents/MacOS/`` first -- ``Popen`` can't launch a bundle
    directory itself, only a real executable file, and using the ``open``
    command instead would lose the process handle (``open`` exits
    immediately after handing off to the app, so there would be nothing
    left to poll).

    Args:
        direct_comm_address: when given (typically
            :data:`DEFAULT_LIVE_STREAM_ADDRESS`), passed as Vizard's own
            ``-directComm <address>`` command-line argument (see
            ``docs/source/Vizard/vizardAdvanced/vizardCommandLine.rst``)
            so it connects to a live-stream automatically instead of
            sitting on its manual launcher screen -- see this module's
            own ``DEFAULT_LIVE_STREAM_ADDRESS`` comment for why. ``None``
            (the default) launches Vizard with no arguments, exactly as
            before.
    """
    if sys.platform == "darwin" and executable_path.suffix == ".app":
        macos_dir = executable_path / "Contents" / "MacOS"
        binaries = [p for p in macos_dir.glob("*") if p.is_file()]
        if not binaries:
            raise FileNotFoundError(
                f"{executable_path} does not look like a valid macOS app bundle "
                f"(no executable found in {macos_dir})"
            )
        executable_path = binaries[0]
    args = [str(executable_path)]
    if direct_comm_address:
        args += ["-directComm", direct_comm_address]
    return subprocess.Popen(args)


class VizardFetchWorker(QThread):
    """Runs :func:`fetch_vizard` on a background thread, the same
    ``QThread`` + cooperative-cancellation pattern
    ``gui.run_worker.RunWorker`` already uses for a running simulation --
    a multi-hundred-MB download must not freeze the GUI's event loop, and
    a user-initiated cancel must not risk a half-written file the way a
    forced ``QThread.terminate()`` could.

    ``gui.main_window.MainWindow.on_launch_vizard`` runs this inside a
    local, blocking ``QEventLoop`` (not by connecting to its signals and
    returning immediately) specifically so that method's own existing
    synchronous ``bool`` return contract -- also relied on by
    ``on_run()``'s live-stream gate -- needs no changes: from every
    existing caller's point of view, fetching Vizard is just a slower
    version of the browse-a-path prompt it already blocks on.
    """

    finished_ok = Signal(str)  # str(Path) to the fetched executable
    failed = Signal(str)
    status = Signal(str)  # human-readable progress text (download vs. extract phase)

    def __init__(self, dest_dir: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self.dest_dir = dest_dir
        self._cancel_requested = threading.Event()

    def request_cancel(self) -> None:
        """Thread-safe -- see this class's own docstring on why this is
        cooperative, not a forced kill.
        """
        self._cancel_requested.set()

    def run(self) -> None:
        try:
            executable = fetch_vizard(
                self.dest_dir,
                should_cancel=self._cancel_requested.is_set,
                on_status=self.status.emit,
            )
        except VizardFetchError as exc:
            self.failed.emit(str(exc))
            return
        self.finished_ok.emit(str(executable))
