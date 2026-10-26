"""Tests headless de la galerie de widgets (mode développeur)."""

from __future__ import annotations

import importlib
import inspect
import os
from pathlib import Path

import pytest
from PySide6.QtWidgets import QDialog, QLabel, QWidget

from ankiforge.dev import is_dev_mode
from ankiforge.ui.widget_gallery import (
    WidgetGalleryRegistry,
    WidgetGalleryWindow,
    gallery_widget,
)
from ankiforge.ui.widget_gallery.families import family_names, load_families
from ankiforge.ui.widget_gallery.families.dialogs import DIALOG_FACTORIES, dialog_labels

pytestmark = pytest.mark.ui


@pytest.fixture(autouse=True)
def reset_registry():
    WidgetGalleryRegistry.clear()
    yield
    WidgetGalleryRegistry.clear()


@pytest.fixture(autouse=True)
def dev_mode():
    os.environ["ANKIFORGE_ENV"] = "development"
    import ankiforge.utils.environment as env_mod

    env_mod._current_env = None
    yield
    env_mod._current_env = None


@pytest.fixture(autouse=True)
def sample_entry():
    @gallery_widget(family="components", name="Label factice")
    def _make_label() -> QWidget:
        return QLabel("Widget factice")

    return None


def test_is_dev_mode_active_in_tests(dev_mode):
    assert is_dev_mode() is True


def test_gallery_window_opens(qtbot):
    win = WidgetGalleryWindow()
    qtbot.addWidget(win)
    win.show()
    assert win is not None
    assert win.tree.topLevelItemCount() >= 1


def test_gallery_instanciates_each_entry(qtbot):
    for entry in WidgetGalleryRegistry.list():
        widget = entry.factory()
        qtbot.addWidget(widget)
        assert isinstance(widget, QWidget)


def test_gallery_search_filters(qtbot):
    win = WidgetGalleryWindow()
    qtbot.addWidget(win)
    win.search_edit.setText("inexistant")
    assert win.tree.topLevelItemCount() == 0


def test_gallery_theme_and_layout_combo_present(qtbot):
    win = WidgetGalleryWindow()
    qtbot.addWidget(win)
    win.show()
    assert win.theme_combo.count() >= 1
    assert win.layout_combo.count() == 4


def test_gallery_theme_change_does_not_crash(qtbot):
    win = WidgetGalleryWindow()
    qtbot.addWidget(win)
    win.show()
    if win.theme_combo.count() > 1:
        win.theme_combo.setCurrentIndex(1)
    else:
        win.theme_combo.setCurrentIndex(0)


def test_gallery_layout_change_does_not_crash(qtbot):
    win = WidgetGalleryWindow()
    qtbot.addWidget(win)
    win.show()
    for idx in range(win.layout_combo.count()):
        win.layout_combo.setCurrentIndex(idx)


# ── Famille « dialogs » ────────────────────────────────────────────────────────

#: Exclusions figées *dans le test* : ajouter un nom ici ne doit pas suffire à
#: masquer un dialogue non enregistré. Les quatre variantes ``Isolated*`` sont des
#: doublons de démonstration internes à ``dialog_gallery_dialog.py``.
EXCLUDED_DIALOG_CLASSES = frozenset(
    {
        "IsolatedCrashReportDialog",
        "IsolatedTimeMachineDialog",
        "IsolatedGroupEditDialog",
        "IsolatedBatchSliceComposerDialog",
    }
)


def _dialog_classes_declared_in_package() -> set[str]:
    """Noms des classes QDialog déclarées par les modules de ``ui/dialogs``."""
    package = importlib.import_module("ankiforge.ui.dialogs")
    package_dir = Path(next(iter(package.__path__)))
    class_names: set[str] = set()
    for module_path in sorted(package_dir.glob("*.py")):
        if module_path.stem.startswith("_"):
            continue
        module = importlib.import_module(f"ankiforge.ui.dialogs.{module_path.stem}")
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if obj.__module__ == module.__name__ and issubclass(obj, QDialog):
                class_names.add(name)
    return class_names


def test_dialogs_family_covers_every_dialog_class():
    declared = _dialog_classes_declared_in_package()
    registered = set(DIALOG_FACTORIES)

    missing = declared - registered - EXCLUDED_DIALOG_CLASSES
    assert not missing, f"Dialogues non enregistrés dans la galerie : {sorted(missing)}"
    assert registered <= declared, f"Factories sans dialogue correspondant : {sorted(registered - declared)}"
    assert set(dialog_labels()) == registered, "Chaque dialogue doit avoir un libellé de galerie"


def test_families_loading_is_tolerant_and_exhaustive():
    loaded = load_families()

    assert loaded == family_names()


def test_dialogs_family_is_registered_in_gallery():
    load_families()

    entries = WidgetGalleryRegistry.list(family="dialogs")

    assert entries
    assert len(entries) == len(DIALOG_FACTORIES)
    assert {entry.factory for entry in entries} == set(DIALOG_FACTORIES.values())


def test_gallery_window_exposes_dialogs_family(qtbot):
    win = WidgetGalleryWindow()
    qtbot.addWidget(win)

    families = {win.tree.topLevelItem(index).text(0) for index in range(win.tree.topLevelItemCount())}

    assert "dialogs" in families


@pytest.mark.parametrize(("class_name", "factory"), list(DIALOG_FACTORIES.items()))
def test_each_dialog_instantiates_without_crash(qtbot, class_name, factory):
    widget = factory()
    qtbot.addWidget(widget)

    assert isinstance(widget, QDialog), f"{class_name} n'est pas un QDialog"

    # Aucun dialogue n'ouvre de worker à la construction ; la garde couvre les deux
    # conventions d'attribut du dépôt pour immuniser le teardown de ``mock_db``.
    worker = getattr(widget, "worker", None)
    if worker is None:
        worker = getattr(widget, "_worker", None)
    if worker is not None and hasattr(worker, "wait"):
        assert worker.wait(10_000), f"Le worker de {class_name} n'a pas terminé"

    widget.close()
