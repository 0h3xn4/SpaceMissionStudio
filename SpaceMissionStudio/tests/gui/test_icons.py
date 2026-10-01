"""Tests for gui.icons."""

import pytest

pytestmark = pytest.mark.requires_gui


def test_app_icon_returns_a_non_null_icon(qapp):
    from spacemissionstudio.gui.icons import app_icon

    icon = app_icon()
    assert not icon.isNull()
    assert len(icon.availableSizes()) > 0


def test_app_icon_pixmap_is_not_blank(qapp):
    """Regression test: an earlier version of the icon-drawing code
    reused ``painter.pen()`` for the orbit ring after having just set
    ``Qt.PenStyle.NoPen`` for the central body -- setColor()/setWidthF()
    don't change a pen's STYLE, so the ring silently never drew, and only
    the two dots rendered. Checking for more than 2 distinct non
    -transparent colors catches that class of bug without pinning down
    exact pixel values (which would break on any legitimate color tweak).
    """
    from PySide6.QtGui import QColor

    from spacemissionstudio.gui.icons import _render

    pixmap = _render(64)
    image = pixmap.toImage()
    colors = set()
    for x in range(0, image.width(), 2):
        for y in range(0, image.height(), 2):
            pixel = QColor(image.pixel(x, y))
            if pixel.alpha() > 0:
                colors.add((pixel.red(), pixel.green(), pixel.blue()))
    assert len(colors) >= 3, f"expected at least 3 distinct colors (body/ring/satellite), got {colors}"


def test_large_icon_includes_the_gold_body_color(qapp):
    """Regression guard for the current (satellite-glyph) design: real
    user feedback on the ORIGINAL design ("refine it to read clearer at
    small sizes") led to a full redesign, not a parameter tweak -- see
    icons.py's own module docstring for why. This pins the one part of
    that redesign a generic "at least N colors" check (the test above)
    wouldn't catch regressing: the body is specifically gold (chosen for
    light/dark-background contrast, not just aesthetics), not the
    original design's near-black.
    """
    from PySide6.QtGui import QColor

    from spacemissionstudio.gui.icons import _GOLD, _render

    pixmap = _render(256)
    image = pixmap.toImage()
    gold = QColor(_GOLD)
    colors = {
        (QColor(image.pixel(x, y)).red(), QColor(image.pixel(x, y)).green(), QColor(image.pixel(x, y)).blue())
        for x in range(0, image.width(), 2)
        for y in range(0, image.height(), 2)
        if QColor(image.pixel(x, y)).alpha() > 0
    }
    assert (gold.red(), gold.green(), gold.blue()) in colors


def test_small_icon_omits_fine_detail_that_would_render_illegibly(qapp):
    """The antenna and panel/body grid-line detail are omitted below
    their own size thresholds (found by rendering both and comparing --
    see icons.py's module docstring) rather than drawn at a thickness
    that anti-aliases away to noise. A 16px render should have
    meaningfully fewer distinct colors than a 256px one as a result.
    """
    from PySide6.QtGui import QColor

    from spacemissionstudio.gui.icons import _render

    def distinct_colors(size):
        image = _render(size).toImage()
        return {
            (QColor(image.pixel(x, y)).red(), QColor(image.pixel(x, y)).green(), QColor(image.pixel(x, y)).blue())
            for x in range(image.width())
            for y in range(image.height())
            if QColor(image.pixel(x, y)).alpha() > 0
        }

    assert len(distinct_colors(16)) < len(distinct_colors(256))


def test_ensure_icon_file_creates_a_real_png(qapp, tmp_path):
    from spacemissionstudio.gui.icons import ensure_icon_file

    target = tmp_path / "icons" / "spacemissionstudio.png"
    result = ensure_icon_file(target)

    assert result == target
    assert target.exists()
    assert target.stat().st_size > 0
    assert target.read_bytes().startswith(b"\x89PNG")


def test_ensure_icon_file_does_not_overwrite_an_existing_file(qapp, tmp_path):
    from spacemissionstudio.gui.icons import ensure_icon_file

    target = tmp_path / "spacemissionstudio.png"
    target.write_bytes(b"not a real png, just a marker")

    result = ensure_icon_file(target)

    assert result == target
    assert target.read_bytes() == b"not a real png, just a marker"
