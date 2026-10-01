"""Tests for gui.feedback -- the toast/inline-validation UX primitives."""

import pytest

pytestmark = pytest.mark.requires_gui


@pytest.fixture
def window(qtbot):
    from PySide6.QtWidgets import QWidget

    w = QWidget()
    w.resize(600, 400)
    qtbot.addWidget(w)
    w.show()
    return w


def test_show_toast_creates_a_visible_labeled_widget(window):
    from missionstudio.gui.feedback import show_toast

    toast = show_toast(window, "Saved scenario.json")

    assert toast.isVisible()
    assert toast.text() == "Saved scenario.json"
    assert toast.parent() is window


def test_show_toast_positions_within_the_window_bottom_right(window):
    from missionstudio.gui.feedback import show_toast

    toast = show_toast(window, "Saved")

    assert toast.geometry().right() <= window.width()
    assert toast.geometry().bottom() <= window.height()
    # Anchored toward the bottom-right, not floating at the origin.
    assert toast.geometry().left() > window.width() / 2
    assert toast.geometry().top() > window.height() / 2


def test_show_toast_auto_dismisses_after_duration(window, qtbot):
    from missionstudio.gui.feedback import show_toast

    toast = show_toast(window, "Saved", duration_ms=50)
    assert toast.isVisible()

    qtbot.wait(200)

    assert not toast.isVisible()


def test_multiple_toasts_stack_without_overlapping(window):
    from missionstudio.gui.feedback import show_toast

    first = show_toast(window, "First", duration_ms=10_000)
    second = show_toast(window, "Second", duration_ms=10_000)

    assert first.geometry().bottom() < second.geometry().top() or \
        second.geometry().bottom() < first.geometry().top()


def test_toast_kind_selects_a_different_color(window):
    from missionstudio.gui.feedback import show_toast

    success = show_toast(window, "ok", kind="success", duration_ms=10_000)
    error = show_toast(window, "bad", kind="error", duration_ms=10_000)

    assert success.styleSheet() != error.styleSheet()


def test_mark_invalid_sets_error_state_and_tooltip():
    from PySide6.QtWidgets import QLineEdit

    from missionstudio.gui.feedback import mark_invalid

    field = QLineEdit()
    mark_invalid(field, "must not be empty")

    assert field.property("state") == "error"
    assert field.toolTip() == "must not be empty"


def test_clear_invalid_undoes_mark_invalid():
    from PySide6.QtWidgets import QLineEdit

    from missionstudio.gui.feedback import clear_invalid, mark_invalid

    field = QLineEdit()
    mark_invalid(field, "bad value")
    clear_invalid(field)

    assert field.property("state") != "error"
    assert field.toolTip() == ""


def test_clear_invalid_on_an_unmarked_field_is_a_no_op():
    from PySide6.QtWidgets import QLineEdit

    from missionstudio.gui.feedback import clear_invalid

    field = QLineEdit()
    clear_invalid(field)  # must not raise

    assert field.property("state") != "error"
