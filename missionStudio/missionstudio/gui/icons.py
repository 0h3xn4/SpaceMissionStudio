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

"""The application icon -- drawn procedurally with :class:`QPainter`
(a satellite glyph: a gold body between two blue solar panels, plus an
antenna at larger sizes, matching ``theme.py``'s accent color for the
panels) rather than shipped as a bitmap asset, so there is no binary
file to keep in sync with the theme and no new packaging step
(``packaging/build_wheel.sh``/the installer's ``.desktop`` entry already
just point at whatever :func:`app_icon`/:func:`window_icon_path`
produce). Used as both the ``QApplication``/``QMainWindow`` window icon
(see ``app.py``) and, cached to a PNG on disk, the ``.desktop`` entry's
``Icon=`` target (see ``packaging/``) -- a ``.desktop`` file needs a
real file path, not an in-memory ``QIcon``.

Real user feedback, with a rendered side-by-side comparison, on the
FIRST design this module drew (a dark central body inside a thin
inclined orbit ellipse, with a small dot on the ring): "refine it to
read clearer at small sizes" -- at 16-32px (window titlebar/taskbar,
where this icon is actually seen most) it read as a cartoon eye, not
an orbit. Root cause, confirmed by rendering variants and comparing
them side by side rather than guessing: "a filled circle centered
inside a surrounding ring" is essentially the universal flat-icon glyph
for an eye (pupil + iris), and no amount of stroke-width/dot-size
tuning on that same structure fixed it -- several tuning passes made it
read MORE eye-like, not less (a bigger, lighter dot became an
eye-catchlight). Fixing it needed a structurally different silhouette,
not parameter tweaks on the same one.

Replaced with an angular satellite glyph (body + two solar-panel
wings), which stays legible at every size tested (256 down to 16px)
specifically because it has no closed ring-around-a-disc shape to be
mistaken for an eye, and reads clearly as spacecraft hardware instead --
also a better thematic fit for a *mission-analysis* tool than a single
orbit-and-dot, which only depicts one specific orbit rather than the
domain generally. The body's gold color is not arbitrary: real
satellites commonly use gold-foil (multi-layer insulation) thermal
blankets, so a gold body next to blue solar panels is representationally
accurate, not just decorative -- and it was ALSO found (by rendering the
icon against both light and dark backgrounds, not assumed) to be the
fix for a real contrast bug the first gold-free attempt had: this
module's original near-black body color is nearly invisible against a
dark-mode taskbar, where a gold body stays clearly visible against both
light and dark surfaces.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPen, QPixmap

_ACCENT = "#3457D5"  # solar panels -- theme.py's own accent color
_ACCENT_DARK = "#243C99"  # antenna + panel grid lines
_GOLD = "#CFB87C"  # satellite body -- see module docstring for why gold, not decorative
_GOLD_DARK = "#A88F53"  # body centerline detail

# Below these sizes the corresponding detail is omitted entirely rather
# than drawn illegibly thin -- confirmed by rendering both thresholds
# and comparing (the antenna line/dot were already invisible by 24px;
# the panel grid lines by 40px), not guessed.
_ANTENNA_MIN_SIZE = 40
_GRID_MIN_SIZE = 56


def _ensure_application() -> None:
    """``QPixmap``/``QPainter`` need a ``QGuiApplication`` instance to
    already exist in the process -- constructing one before it does is a
    silent no-op in Qt (a stderr warning, not a raised exception): the
    resulting pixmap is null and ``.save()`` just returns ``False``, so a
    caller that doesn't check that return value (``app_icon()`` doesn't;
    :func:`ensure_icon_file` does, see below) would appear to succeed
    while producing nothing. Every caller in THIS module runs inside
    ``gui/app.py``'s already-running ``QApplication`` except
    ``packaging/install.sh``'s standalone icon-render step, which imports
    only this module -- so this constructs a minimal, display-less
    ``QGuiApplication`` there rather than trusting every future call site
    to remember to.
    """
    if QGuiApplication.instance() is None:
        QGuiApplication([])


def _render(size: int) -> QPixmap:
    """See module docstring for why this is a satellite glyph (body +
    two solar panels + an antenna at larger sizes) and not the earlier
    orbit-ellipse design. ``scale``/rotation/proportions below were
    tuned by rendering actual candidates side by side at 256 down to
    16px and comparing them, not picked once and trusted -- an earlier
    tuning pass that only adjusted the old design's stroke width/dot
    size made it read MORE like an eye, not less, which is why this is
    a different silhouette entirely rather than a parameter change.
    """
    _ensure_application()
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    painter.translate(size / 2.0, size / 2.0)
    painter.rotate(-32.0)

    # s: a 256px design grid, scaled to the actual requested size, with
    # an extra 1.22x so the glyph fills more of the icon's canvas than a
    # literal 256-grid mapping would -- confirmed by rendering both and
    # comparing that the larger one reads better at 16-24px, where every
    # extra pixel of actual shape matters.
    s = (size / 256.0) * 1.22

    panel_w, panel_h = 58 * s, 96 * s
    gap = 7 * s
    body_w, body_h = 46 * s, 46 * s
    left_panel = QRectF(-body_w / 2 - gap - panel_w, -panel_h / 2, panel_w, panel_h)
    right_panel = QRectF(body_w / 2 + gap, -panel_h / 2, panel_w, panel_h)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(_ACCENT))
    painter.drawRoundedRect(left_panel, 5 * s, 5 * s)
    painter.drawRoundedRect(right_panel, 5 * s, 5 * s)

    if size >= _GRID_MIN_SIZE:
        grid_pen = QPen(QColor(_ACCENT_DARK))
        grid_pen.setWidthF(max(1.0, 1.5 * s))
        painter.setPen(grid_pen)
        for panel in (left_panel, right_panel):
            for frac in (0.33, 0.66):
                y = panel.top() + panel.height() * frac
                painter.drawLine(QPointF(panel.left() + 2 * s, y), QPointF(panel.right() - 2 * s, y))

    body_rect = QRectF(-body_w / 2, -body_h / 2, body_w, body_h)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(_GOLD))
    painter.drawRoundedRect(body_rect, 9 * s, 9 * s)
    if size >= _GRID_MIN_SIZE:
        centerline_pen = QPen(QColor(_GOLD_DARK))
        centerline_pen.setWidthF(max(1.0, 1.4 * s))
        painter.setPen(centerline_pen)
        painter.drawLine(QPointF(-body_w / 2 + 3 * s, 0), QPointF(body_w / 2 - 3 * s, 0))

    if size >= _ANTENNA_MIN_SIZE:
        antenna_pen = QPen(QColor(_ACCENT_DARK))
        antenna_pen.setWidthF(max(4 * s, 1.8))
        antenna_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(antenna_pen)
        antenna_tip = QPointF(0, -body_h / 2 - 22 * s)
        painter.drawLine(QPointF(0, -body_h / 2), antenna_tip)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(_ACCENT_DARK))
        painter.drawEllipse(antenna_tip, max(5 * s, 2.2), max(5 * s, 2.2))

    painter.end()
    return pixmap


def app_icon() -> QIcon:
    """A multi-resolution :class:`QIcon` -- Qt picks the best size for
    each context (window titlebar, taskbar, alt-tab switcher, ...) from
    whichever sizes are registered.
    """
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(_render(size))
    return icon


def ensure_icon_file(path: "str | Path", size: int = 256) -> Path:
    """Renders the icon to a PNG at ``path`` (creating parent directories
    as needed) if it doesn't already exist, and returns the path. Used by
    ``packaging/`` for the ``.desktop`` entry's ``Icon=`` target, which
    needs a real file, not an in-memory :class:`QIcon`.

    Raises :class:`OSError` if the render/save fails (e.g. no usable Qt
    platform plugin) -- ``QPixmap.save()`` only returns ``False`` on
    failure rather than raising, which would otherwise let
    ``install.sh``'s calling ``python3 -c ...`` exit 0 having silently
    written nothing, and its shell ``if`` guard report success anyway.
    """
    path = Path(path)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        if not _render(size).save(str(path), "PNG"):
            raise OSError(f"could not render/save the app icon to {path}")
    return path
