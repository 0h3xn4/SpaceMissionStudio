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

"""Two small, reusable UX primitives, built once here and reused across
gui/ rather than re-invented per widget -- real user feedback ("make the
GUI more 'reactive'... the user always knows and understands what they
did. visual cues would help... currently, everything looks very raw and
unfinished"), and a follow-up survey of this app's own existing widgets
found the same two gaps repeating across most of them (add/remove
actions with no positive feedback beyond a list silently changing;
invalid input only ever caught by a blocking dialog at Save/Run time,
never at the specific field, at the moment it's typed):

* :func:`show_toast` -- a small, non-blocking, auto-dismissing
  notification, for "did my action actually do something" feedback on
  actions where a blocking ``QMessageBox`` would be overkill (Save, Add
  spacecraft, Remove sensor, ...) and a status-bar message alone is too
  easy to miss. That's not a guess: ``MainWindow.on_launch_vizard``'s own
  docstring already documents exactly this problem for ONE case (a
  status-bar message "easy to miss/get overwritten by the 'Running...'
  message that follows moments later") and had to be promoted to a
  one-time blocking dialog to be noticed at all -- a toast is the
  general-purpose fix that case shouldn't have needed a bespoke one-off
  dialog for.
* :func:`mark_invalid`/:func:`clear_invalid` -- inline, per-field
  validation feedback (a red border, via theme.py's own
  ``[state="error"]`` QSS rule, plus the reason as a tooltip), so a
  field the user is actively typing into can show it's wrong immediately
  rather than only at Save/Run time via a dialog that names the problem
  but not which of a dialog's many fields caused it.

Both are intentionally widget-library-free (no new PyPI dependency) --
plain ``QLabel``/dynamic-Qt-property mechanisms the Qt Style Sheets
system already documents, matching this project's own "no third-party
GUI-chrome dependency beyond PySide6 itself" precedent (see theme.py).
"""

from __future__ import annotations

from typing import List

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel, QWidget
from shiboken6 import isValid

from .theme import PALETTE

_TOAST_KIND_COLORS = {
    "success": (PALETTE["success"], PALETTE["on_accent"]),
    "error": (PALETTE["danger"], PALETTE["on_accent"]),
    "info": (PALETTE["text"], PALETTE["surface"]),
}
_TOAST_MARGIN_PX = 16
_TOAST_GAP_PX = 8
_TOAST_STACK_ATTR = "_spacemissionstudio_active_toasts"


class _Toast(QLabel):
    """Not meant to be constructed directly -- see :func:`show_toast`."""

    def __init__(self, parent: QWidget, message: str, kind: str) -> None:
        super().__init__(message, parent)
        bg, fg = _TOAST_KIND_COLORS.get(kind, _TOAST_KIND_COLORS["info"])
        self.setStyleSheet(
            f"background-color: {bg}; color: {fg}; border-radius: 6px; "
            f"padding: 8px 14px; font-weight: 600;"
        )
        self.setWordWrap(True)
        self.setMaximumWidth(360)
        self.adjustSize()


def show_toast(window: QWidget, message: str, kind: str = "success", duration_ms: int = 2600) -> QLabel:
    """Shows ``message`` in a small notification anchored to the
    bottom-right corner of ``window`` (the app's top-level window, or any
    dialog), auto-dismissing after ``duration_ms``. ``kind`` is
    ``"success"`` (default), ``"error"``, or ``"info"`` -- picks the
    toast's color from theme.py's own palette so it reads as part of the
    same themed system, not a visually foreign popup.

    Multiple toasts shown in quick succession (e.g. several list rows
    added back-to-back) stack upward rather than overlapping -- ``window``
    carries its own small list of currently-visible toasts
    (a plain attribute, not a class member, so this works on ANY QWidget
    without every window/dialog that wants toasts needing to inherit from
    a shared base class). Returns the created ``QLabel`` -- mainly useful
    for tests; normal callers can ignore the return value.
    """
    stack: List[QLabel] = getattr(window, _TOAST_STACK_ATTR, None)
    if stack is None:
        stack = []
        setattr(window, _TOAST_STACK_ATTR, stack)

    toast = _Toast(window, message, kind)
    stack.append(toast)
    _reposition_toasts(window, stack)
    toast.show()
    toast.raise_()

    def _dismiss() -> None:
        # The QTimer below can fire AFTER `window` (and so `toast`, its
        # child) was already destroyed -- e.g. the app/dialog was closed
        # while a toast was still showing, a real sequence several
        # existing tests hit (close a window right after an action that
        # shows a toast). shiboken6.isValid() is the documented way to
        # check whether a QObject's underlying C++ object is still alive
        # before touching it; skipping silently here is correct -- there
        # is nothing left to dismiss.
        if not isValid(toast):
            return
        if toast in stack:
            stack.remove(toast)
        # hide(), not deleteLater(): a caller that kept the QLabel
        # show_toast() returned (tests do) must not end up holding a
        # dangling C++ pointer once the auto-dismiss timer fires -- Qt's
        # normal parent-child ownership (toast's parent is `window`)
        # already cleans it up for real once `window` itself is
        # destroyed, so there is nothing to leak by not deleting sooner.
        toast.hide()
        if isValid(window):
            _reposition_toasts(window, stack)

    QTimer.singleShot(duration_ms, _dismiss)
    return toast


def _reposition_toasts(window: QWidget, stack: List[QLabel]) -> None:
    y = window.height() - _TOAST_MARGIN_PX
    for toast in reversed(stack):
        y -= toast.height()
        toast.move(window.width() - toast.width() - _TOAST_MARGIN_PX, y)
        y -= _TOAST_GAP_PX


_ERROR_STATE_PROPERTY = "state"
_ERROR_STATE_VALUE = "error"


def mark_invalid(widget: QWidget, message: str) -> None:
    """Flags ``widget`` (a ``QLineEdit``/``QDoubleSpinBox``/``QSpinBox``/
    ``QComboBox``) as holding an invalid value -- a red border (theme.py's
    ``[state="error"]`` QSS rule) plus ``message`` as its tooltip, so the
    user sees WHICH field is wrong and WHY without waiting for a blocking
    Save/Run dialog. Does not clear itself -- call :func:`clear_invalid`
    once the field holds an acceptable value again (typically wired to
    that widget's own ``textChanged``/``valueChanged`` signal).
    """
    widget.setProperty(_ERROR_STATE_PROPERTY, _ERROR_STATE_VALUE)
    widget.setToolTip(message)
    _repolish(widget)


def clear_invalid(widget: QWidget) -> None:
    """Undoes :func:`mark_invalid` -- a no-op if the widget wasn't
    marked, so this is always safe to call unconditionally (e.g. at the
    top of a field's change handler, before re-validating).
    """
    if widget.property(_ERROR_STATE_PROPERTY) == _ERROR_STATE_VALUE:
        widget.setProperty(_ERROR_STATE_PROPERTY, "")
        widget.setToolTip("")
        _repolish(widget)


def _repolish(widget: QWidget) -> None:
    """Qt caches a widget's QSS match against its dynamic properties --
    changing one (``state`` above) has no visible effect until the style
    is explicitly told to re-evaluate it (Qt docs, "Qt Style Sheets
    Reference" -> "Qt Style Sheets and Widget Style" -> "Dynamic
    Properties").
    """
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
