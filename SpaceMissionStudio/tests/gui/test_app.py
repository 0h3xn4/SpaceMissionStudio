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

"""Tests for gui.app.

``main()`` itself can't be unit tested directly -- it calls
``QApplication.exec()``, which blocks in an event loop forever under
pytest. These instead check the specific things a real user report
("the taskbar always shows a generic cog icon") traced back to: Qt only
lets Linux desktop shells (GNOME Shell, KDE Plasma, Wayland compositors
generally) resolve a running window to its intended icon if they can
match it to an installed ``.desktop`` entry, and that match needs
``setDesktopFileName()``/``StartupWMClass`` to agree with the
``.desktop`` files' own basename -- see app.py's inline comment and
packaging/spacemissionstudio.desktop.in for the full story.
"""

import inspect
from pathlib import Path

import pytest

pytestmark = pytest.mark.requires_gui

_PACKAGING_DIR = Path(__file__).resolve().parents[2] / "packaging"


def test_main_sets_the_desktop_file_name_to_match_the_installed_desktop_entries():
    from spacemissionstudio.gui.app import main

    source = inspect.getsource(main)
    assert 'setDesktopFileName("spacemissionstudio")' in source, (
        "main() must call setDesktopFileName('spacemissionstudio') so GNOME/KDE/Wayland "
        "shells can match this running window to the installed spacemissionstudio.desktop "
        "entry and its icon, instead of falling back to a generic (cog) icon"
    )


@pytest.mark.parametrize(
    "desktop_file",
    [
        _PACKAGING_DIR / "spacemissionstudio.desktop.in",
        _PACKAGING_DIR / "deb" / "usr" / "share" / "applications" / "spacemissionstudio.desktop",
    ],
)
def test_desktop_entry_declares_a_matching_startup_wm_class(desktop_file):
    text = desktop_file.read_text()
    assert "StartupWMClass=spacemissionstudio" in text, (
        f"{desktop_file} must set StartupWMClass=spacemissionstudio so X11 window managers "
        "that match by WM_CLASS (rather than the Wayland desktop-file-name path) can "
        "also resolve this window to its icon"
    )


def test_desktop_file_name_matches_the_desktop_entries_own_basename():
    """The three places a ".desktop"-matching identifier is spelled out --
    app.py's setDesktopFileName() call, and each installed .desktop
    file's own filename -- must agree, or the match this whole mechanism
    depends on silently fails.
    """
    from spacemissionstudio.gui.app import main

    source = inspect.getsource(main)
    start = source.index('setDesktopFileName("') + len('setDesktopFileName("')
    end = source.index('"', start)
    desktop_file_name = source[start:end]

    for desktop_file in (
        _PACKAGING_DIR / "spacemissionstudio.desktop.in",
        _PACKAGING_DIR / "deb" / "usr" / "share" / "applications" / "spacemissionstudio.desktop",
    ):
        # Strip a ".desktop" suffix and, for the .in template, the
        # templating suffix after that -- both install as plain
        # "spacemissionstudio.desktop", which is what actually has to agree
        # with setDesktopFileName().
        installed_name = desktop_file.name
        assert installed_name.endswith(".desktop") or installed_name.endswith(".desktop.in")
        installed_stem = installed_name.removesuffix(".in").removesuffix(".desktop")
        assert installed_stem == desktop_file_name, (
            f"{desktop_file.name} is installed under a basename that doesn't match "
            f"setDesktopFileName({desktop_file_name!r})"
        )
