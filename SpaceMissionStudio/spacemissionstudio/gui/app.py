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

"""GUI entry point. Launch with ``python3 -m spacemissionstudio.gui.app``, or
via ``spacemissionstudio gui`` (see ``../cli.py``).
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from ..logging_setup import configure_logging
from .icons import app_icon
from .main_window import MainWindow
from .theme import apply_theme


def main(argv: list | None = None) -> int:
    # First thing, before anything else can fail -- see logging_setup's
    # own module docstring for why (direct user feedback: a crash whose
    # only information anywhere was one bare line in a GUI error dialog).
    configure_logging()
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("SpaceMissionStudio")
    # Needed for QSettings() (used by gui.vizard_launcher to remember a
    # user-picked Vizard executable path) to resolve to a stable
    # per-platform location -- QSettings() with no explicit org/app name
    # falls back to whatever these two are set to.
    app.setOrganizationName("AVSLab")
    # Real user report: the taskbar/dock always shows a generic cog icon,
    # never the app icon below. Root cause confirmed by inspecting how
    # Linux desktop shells actually resolve a running window's icon: most
    # (GNOME Shell, KDE Plasma, and Wayland compositors generally) match
    # the window to an installed .desktop entry by "desktop file name" /
    # app-id, then use THAT entry's Icon= -- they do not look at the QIcon
    # passed to setWindowIcon() below at all. Without this call, Qt never
    # tells the compositor which .desktop entry this process corresponds
    # to, so the match fails and the shell falls back to its generic
    # "unknown application" icon (a gear/cog glyph in Adwaita/Breeze/Yaru
    # -derived themes -- exactly what was reported). Matches the
    # "spacemissionstudio" basename used everywhere else a .desktop entry is
    # referenced (packaging/spacemissionstudio.desktop.in's own filename and
    # Icon= key, packaging/deb's desktop entry, install.sh's icon install
    # path). Still needs a matching spacemissionstudio.desktop to actually be
    # installed (via packaging/install.sh or the .deb) for the lookup to
    # resolve to anything -- a from-source run with no .desktop entry
    # installed anywhere on the system falls back to the generic icon
    # regardless of this call, which this alone can't fix.
    app.setDesktopFileName("spacemissionstudio")
    apply_theme(app)
    icon = app_icon()
    app.setWindowIcon(icon)
    window = MainWindow()
    window.setWindowIcon(icon)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
