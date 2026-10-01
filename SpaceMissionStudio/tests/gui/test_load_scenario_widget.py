"""Tests for gui.load_scenario_widget.LoadScenarioWidget -- exercised
against the REAL bundled templates (spacemissionstudio/scenarios/templates/),
not synthetic fixtures, since the whole point of this widget is
surfacing exactly those files.
"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.requires_gui


def test_populates_one_item_per_bundled_template(qtbot):
    from spacemissionstudio.gui.load_scenario_widget import TEMPLATES_DIR, LoadScenarioWidget

    widget = LoadScenarioWidget()
    qtbot.addWidget(widget)

    expected_count = len(list(TEMPLATES_DIR.glob("*.json")))
    assert expected_count >= 9
    assert widget.list_widget.count() == expected_count


def test_items_are_in_filename_order(qtbot):
    from spacemissionstudio.gui.load_scenario_widget import LoadScenarioWidget

    widget = LoadScenarioWidget()
    qtbot.addWidget(widget)

    # Filenames are zero-padded ("01_...", "02_...", ...), so their
    # scenario "name" fields (which each start with the same number,
    # e.g. "01 - Two-body circular orbit") sort the same way -- this
    # confirms the list wasn't accidentally reordered by e.g. an
    # unsorted glob() or dict iteration.
    titles = [widget.list_widget.item(i).text() for i in range(widget.list_widget.count())]
    assert titles == sorted(titles)
    assert titles[0].startswith("01")


def test_no_selection_disables_open_button_and_clears_description(qtbot):
    from spacemissionstudio.gui.load_scenario_widget import LoadScenarioWidget

    widget = LoadScenarioWidget()
    qtbot.addWidget(widget)

    assert not widget.open_template_button.isEnabled()
    assert widget.description_label.text() == ""


def _customize_button(widget, name_substring: str):
    """Finds the standalone "Customize: <template name>..." button for a
    given template -- see _build_customize_buttons's own docstring for
    why these are separate, always-enabled buttons rather than one
    shared, selection-dependent button.
    """
    from PySide6.QtWidgets import QPushButton

    matches = [b for b in widget.findChildren(QPushButton) if name_substring in b.text()]
    assert len(matches) == 1, f"expected exactly one Customize button matching {name_substring!r}, got {matches}"
    return matches[0]


def test_customize_button_exists_for_every_template_with_a_registered_wizard_spec(qtbot):
    """Every bundled template has a registered spec now (see
    gui.template_wizard's own docstring for the rollout history), so this
    confirms the button LIST tracks the spec registry -- not that some
    templates are excluded (there's a dedicated unit test for that,
    gui.template_wizard's own test_get_wizard_spec_returns_none_for_an
    _unregistered_template).
    """
    from spacemissionstudio.gui.load_scenario_widget import LoadScenarioWidget
    from spacemissionstudio.gui.template_wizard import get_wizard_spec

    widget = LoadScenarioWidget()
    qtbot.addWidget(widget)

    for scenario_name, path in widget._template_paths.items():
        if get_wizard_spec(path.name) is None:
            continue
        # Has one, and it's enabled without any prior list selection --
        # these buttons are standalone actions, not gated on
        # widget.list_widget.currentItem().
        button = _customize_button(widget, scenario_name)
        assert button.isEnabled()


def test_customize_clicked_emits_scenario_customized_on_accept(qtbot, monkeypatch):
    from spacemissionstudio.gui.load_scenario_widget import LoadScenarioWidget
    from spacemissionstudio.gui.template_wizard import TemplateCustomizeWizard

    widget = LoadScenarioWidget()
    qtbot.addWidget(widget)

    monkeypatch.setattr(TemplateCustomizeWizard, "exec",
                         lambda self: TemplateCustomizeWizard.DialogCode.Accepted)

    emitted = []
    widget.scenario_customized.connect(lambda scenario: emitted.append(scenario))
    _customize_button(widget, "03 - GEO station-keeping").click()

    assert len(emitted) == 1
    assert emitted[0].name == "03 - GEO station-keeping"


def test_customize_clicked_emits_nothing_on_cancel(qtbot, monkeypatch):
    from spacemissionstudio.gui.load_scenario_widget import LoadScenarioWidget
    from spacemissionstudio.gui.template_wizard import TemplateCustomizeWizard

    widget = LoadScenarioWidget()
    qtbot.addWidget(widget)

    monkeypatch.setattr(TemplateCustomizeWizard, "exec",
                         lambda self: TemplateCustomizeWizard.DialogCode.Rejected)

    emitted = []
    widget.scenario_customized.connect(lambda scenario: emitted.append(scenario))
    _customize_button(widget, "03 - GEO station-keeping").click()

    assert emitted == []


def test_customize_clicked_is_independent_of_the_lists_current_selection(qtbot, monkeypatch):
    """Regression test for the earlier (replaced) design, where a single
    shared "Customize..." button only worked for whatever template was
    currently selected in the list above -- these standalone buttons
    must work regardless of that selection.
    """
    from spacemissionstudio.gui.load_scenario_widget import LoadScenarioWidget
    from spacemissionstudio.gui.template_wizard import TemplateCustomizeWizard

    widget = LoadScenarioWidget()
    qtbot.addWidget(widget)
    widget.list_widget.setCurrentRow(0)  # "01 - Two-body circular orbit" -- unrelated to '18'

    monkeypatch.setattr(TemplateCustomizeWizard, "exec",
                         lambda self: TemplateCustomizeWizard.DialogCode.Accepted)

    emitted = []
    widget.scenario_customized.connect(lambda scenario: emitted.append(scenario))
    _customize_button(widget, "18 - LEO station-keeping").click()

    assert len(emitted) == 1
    assert emitted[0].name == "18 - LEO station-keeping"


def test_selecting_an_item_enables_open_and_shows_its_description(qtbot):
    from spacemissionstudio.gui.load_scenario_widget import LoadScenarioWidget

    widget = LoadScenarioWidget()
    qtbot.addWidget(widget)

    widget.list_widget.setCurrentRow(0)

    assert widget.open_template_button.isEnabled()
    assert len(widget.description_label.text()) > 50


def test_open_template_button_emits_the_matching_path(qtbot):
    from spacemissionstudio.gui.load_scenario_widget import TEMPLATES_DIR, LoadScenarioWidget

    widget = LoadScenarioWidget()
    qtbot.addWidget(widget)
    widget.list_widget.setCurrentRow(0)

    emitted = []
    widget.path_chosen.connect(lambda path: emitted.append(path))
    widget._on_open_template_clicked()

    assert len(emitted) == 1
    assert emitted[0].parent == TEMPLATES_DIR
    assert emitted[0].name.startswith("01_")


def test_double_click_opens_the_template(qtbot):
    from spacemissionstudio.gui.load_scenario_widget import LoadScenarioWidget

    widget = LoadScenarioWidget()
    qtbot.addWidget(widget)

    emitted = []
    widget.path_chosen.connect(lambda path: emitted.append(path))
    widget.list_widget.itemDoubleClicked.emit(widget.list_widget.item(2))

    # itemDoubleClicked alone doesn't change currentItem() in a headless
    # test (no real mouse click drove selection first) -- select it
    # explicitly first, matching what a real double-click does in
    # practice (it also selects the row), then fire the signal.
    widget.list_widget.setCurrentRow(2)
    widget.list_widget.itemDoubleClicked.emit(widget.list_widget.item(2))

    assert len(emitted) == 1
    assert emitted[0].name.startswith("03_")


def test_browse_emits_the_picked_path(qtbot, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog

    from spacemissionstudio.gui.load_scenario_widget import LoadScenarioWidget

    picked = tmp_path / "my_scenario.json"
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(picked), "")))

    widget = LoadScenarioWidget()
    qtbot.addWidget(widget)
    emitted = []
    widget.path_chosen.connect(lambda path: emitted.append(path))

    widget._on_browse_clicked()

    assert emitted == [picked]


def test_browse_cancelled_emits_nothing(qtbot, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    from spacemissionstudio.gui.load_scenario_widget import LoadScenarioWidget

    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: ("", "")))

    widget = LoadScenarioWidget()
    qtbot.addWidget(widget)
    emitted = []
    widget.path_chosen.connect(lambda path: emitted.append(path))

    widget._on_browse_clicked()

    assert emitted == []


def test_content_is_wrapped_in_a_resizable_scroll_area(qtbot):
    """Regression guard for a real bug, found from a user screenshot
    taken while resizing/maximizing the main window: this tab's content
    (18 template rows, the description label, and one standalone
    "Customize: <template name>..." button per template -- see
    _build_customize_buttons) is tall enough to exceed a real window's
    available height. Before this fix, everything was added straight to
    this widget's own top-level layout with no QScrollArea, so squeezing
    it into less height than it needed didn't clip cleanly -- QLabel
    does not clip wrapped text to its own allocated rect, so
    description_label's text painted past its own boundary and visibly
    overlapped the list widget above it. Matches the same pattern
    scenario_editor.ScenarioEditorWidget and spacecraft_editor.py's
    _scrollable() already use for this exact reason.
    """
    from PySide6.QtWidgets import QScrollArea

    from spacemissionstudio.gui.load_scenario_widget import LoadScenarioWidget

    widget = LoadScenarioWidget()
    qtbot.addWidget(widget)

    scroll_areas = widget.findChildren(QScrollArea)
    assert len(scroll_areas) == 1
    assert scroll_areas[0].widgetResizable()
    # description_label must live inside the scroll area's own content
    # widget, not directly on widget's top-level layout.
    content = scroll_areas[0].widget()
    assert widget.description_label in content.findChildren(type(widget.description_label))


def test_description_label_is_never_squeezed_below_its_needed_height(qtbot):
    """A real window resized/maximized smaller than this tab's natural
    content height must not reproduce the overlapping-text bug: the
    QScrollArea should scroll instead of shrinking description_label
    below what it needs to render without clipping/overlap -- same
    verification approach as
    test_propagation_setup_dialog.test_srp_pointer_label_gets_its_full_wrapped_height_not_clipped,
    which caught a real instance of this same QLabel-overflow failure
    mode elsewhere in this app.
    """
    from PySide6.QtWidgets import QApplication

    from spacemissionstudio.gui.load_scenario_widget import LoadScenarioWidget

    widget = LoadScenarioWidget()
    qtbot.addWidget(widget)
    widget.list_widget.setCurrentRow(0)  # gives description_label real, long text to wrap

    widget.resize(500, 150)  # far shorter than this tab's natural content height
    widget.show()
    for _ in range(3):
        QApplication.processEvents()

    label = widget.description_label
    needed_height = label.heightForWidth(label.geometry().width())
    assert label.geometry().height() >= needed_height


def test_a_malformed_template_is_skipped_not_crashed_on(qtbot, monkeypatch, tmp_path):
    from spacemissionstudio.gui import load_scenario_widget

    broken_dir = tmp_path / "templates"
    broken_dir.mkdir()
    (broken_dir / "broken.json").write_text("not valid json at all")
    monkeypatch.setattr(load_scenario_widget, "TEMPLATES_DIR", broken_dir)

    widget = load_scenario_widget.LoadScenarioWidget()
    qtbot.addWidget(widget)

    assert widget.list_widget.count() == 0
