"""Tests headless de la galerie de widgets (mode développeur)."""

from __future__ import annotations

import importlib
import inspect
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import QAbstractItemModel
from PySide6.QtWidgets import QAbstractItemDelegate, QDialog, QLabel, QMainWindow, QWidget

from ankiforge.dev import is_dev_mode
from ankiforge.ui.layouts.base_layout import BaseLayout
from ankiforge.ui.layouts.layout_manager import LayoutManager
from ankiforge.ui.viewmodels.base import BaseViewModel
from ankiforge.ui.widget_gallery import (
    WidgetGalleryRegistry,
    WidgetGalleryWindow,
    gallery_widget,
)
from ankiforge.ui.widget_gallery.families import family_names, load_families
from ankiforge.ui.widget_gallery.families.components import (
    COMPONENT_CLASS_IDS,
    COMPONENT_FACTORIES,
    component_labels,
)
from ankiforge.ui.widget_gallery.families.dialogs import DIALOG_FACTORIES, dialog_labels
from ankiforge.ui.widget_gallery.families.layouts import LAYOUT_FACTORIES, layout_labels
from ankiforge.ui.widget_gallery.families.models import (
    EXCLUDED_QT_MODEL_CLASSES,
    MODEL_FACTORIES,
    model_labels,
)
from ankiforge.ui.widget_gallery.families.shell import SHELL_CLASS_IDS, SHELL_FACTORIES, shell_labels
from ankiforge.ui.widget_gallery.families.viewmodels import VIEWMODEL_FACTORIES, viewmodel_labels
from ankiforge.ui.widget_gallery.previews import ObjectPreview, ShellPreviewWindow
from ankiforge.ui.widget_gallery.registry import GalleryEntry

pytestmark = pytest.mark.ui

#: Familles attendues dans la galerie (l'ordre d'affichage est alphabétique).
EXPECTED_FAMILIES = frozenset({"components", "dialogs", "layouts", "models", "shell", "viewmodels"})


def _collect_all_entries() -> list[GalleryEntry]:
    """Photographie le registre complet avant que la fixture d'isolation ne le purge."""
    load_families()
    return WidgetGalleryRegistry.list()


#: Paramétrage figé à la collecte : les factories restent valides après la purge du registre.
ALL_ENTRIES = _collect_all_entries()


@pytest.fixture(autouse=True)
def reset_registry():
    WidgetGalleryRegistry.clear()
    yield
    WidgetGalleryRegistry.clear()


@pytest.fixture(autouse=True)
def dev_mode(monkeypatch: pytest.MonkeyPatch):
    # ``monkeypatch`` restaure ``ANKIFORGE_ENV`` en fin de test : sans cela la variable
    # fuiterait vers les tests suivants du même worker xdist et réveillerait le démarrage
    # différé du démon MCP de ``MainWindow`` (timer non annulable).
    monkeypatch.setenv("ANKIFORGE_ENV", "development")
    import ankiforge.utils.environment as env_mod

    monkeypatch.setattr(env_mod, "_current_env", None)
    yield
    env_mod._current_env = None


@pytest.fixture(autouse=True)
def sample_entry():
    # Famille neutre : la famille « components » doit rester mesurable par les tests dédiés.
    @gallery_widget(family="fixtures", name="Label factice")
    def _make_label() -> QWidget:
        return QLabel("Widget factice")

    return None


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Isole la galerie du dossier de données du développeur (snippets personnalisés)."""
    monkeypatch.setenv("ANKIFORGE_DATA_DIR", str(tmp_path / "data"))


def _assert_no_pending_worker(widget: QWidget, label: str) -> None:
    """Attend tout worker lancé à la construction pour immuniser le teardown de ``mock_db``.

    Les aperçus non visuels (ViewModel encapsulé dans un ``ObjectPreview``) portent leur
    cible sur ``_target`` : le worker peut donc être lancé par l'objet observé et non par
    le conteneur.
    """
    for candidate in (widget, getattr(widget, "_target", None)):
        if candidate is None:
            continue
        worker = getattr(candidate, "worker", None)
        if worker is None:
            worker = getattr(candidate, "_worker", None)
        if worker is not None and hasattr(worker, "wait"):
            assert worker.wait(10_000), f"Le worker de {label} n'a pas terminé"


def _select_entry(win: WidgetGalleryWindow, family: str, name: str) -> None:
    """Sélectionne une entrée de l'arbre et laisse la fenêtre construire son aperçu."""
    root = next(win.tree.topLevelItem(index) for index in range(win.tree.topLevelItemCount()) if win.tree.topLevelItem(index).text(0) == family)
    item = next(root.child(index) for index in range(root.childCount()) if root.child(index).text(0) == name)
    win.tree.setCurrentItem(item)


def test_is_dev_mode_active_in_tests(dev_mode):
    assert is_dev_mode() is True


def test_gallery_window_opens(qtbot):
    win = WidgetGalleryWindow()
    qtbot.addWidget(win)
    win.show()
    assert win is not None
    assert win.tree.topLevelItemCount() >= 1


def test_registry_covers_expected_families():
    load_families()

    assert set(WidgetGalleryRegistry.families()) >= EXPECTED_FAMILIES


def test_collected_snapshot_matches_expected_families():
    # Invariant de collecte : la photographie paramétrée doit couvrir exactement les
    # familles annoncées, faute de quoi une famille entière échapperait aux tests.
    assert {entry.family for entry in ALL_ENTRIES} == EXPECTED_FAMILIES
    assert len({(entry.family, entry.name) for entry in ALL_ENTRIES}) == len(ALL_ENTRIES)


def test_gallery_window_exposes_every_registered_family(qtbot):
    load_families()
    win = WidgetGalleryWindow()
    qtbot.addWidget(win)

    families = {win.tree.topLevelItem(index).text(0): win.tree.topLevelItem(index).childCount() for index in range(win.tree.topLevelItemCount())}

    assert set(families) == set(WidgetGalleryRegistry.families())
    # La famille « fixtures » est ajoutée par la fixture autouse : elle complète
    # l'ensemble attendu sans jamais le remplacer.
    assert set(families) == EXPECTED_FAMILIES | {"fixtures"}
    for family, child_count in families.items():
        assert child_count == len(WidgetGalleryRegistry.list(family=family)), f"Famille incomplète dans l'arbre : {family}"


@pytest.mark.parametrize(
    ("family", "name", "factory"),
    [(entry.family, entry.name, entry.factory) for entry in ALL_ENTRIES],
    ids=[f"{entry.family}-{index:03d}" for index, entry in enumerate(ALL_ENTRIES)],
)
def test_every_registered_entry_instantiates_without_crash(qtbot, family, name, factory):
    widget = factory()
    qtbot.addWidget(widget)

    assert isinstance(widget, QWidget), f"L'entrée « {family}/{name} » n'instancie pas un widget"

    _assert_no_pending_worker(widget, f"{family}/{name}")

    widget.close()


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


# ── Câblage de la barre d'outils ───────────────────────────────────────────────


def test_gallery_modal_button_follows_the_selected_entry(qtbot):
    load_families()
    win = WidgetGalleryWindow()
    qtbot.addWidget(win)
    win.show()

    _select_entry(win, "shell", shell_labels()["SettingsModal"])
    assert win.open_modal_btn.isEnabled(), "Les paramètres doivent pouvoir s'ouvrir en modal"

    _select_entry(win, "dialogs", dialog_labels()[next(iter(DIALOG_FACTORIES))])
    assert win.open_modal_btn.isEnabled(), "Les dialogues doivent pouvoir s'ouvrir en modal"

    _select_entry(win, "layouts", layout_labels()["IdeLayout"])
    assert not win.open_modal_btn.isEnabled(), "Un layout n'a pas de sens en modal"


def test_gallery_layout_combo_targets_the_shell_preview(qtbot):
    load_families()
    win = WidgetGalleryWindow()
    qtbot.addWidget(win)
    win.show()

    assert win.layout_combo.count() == len(LayoutManager.get_available_layouts())

    _select_entry(win, "shell", shell_labels()["MainWindow"])
    preview = win.preview.current_widget
    assert isinstance(preview, ShellPreviewWindow)
    assert win.layout_combo.isEnabled(), "La disposition doit être applicable à la coquille"

    target_index = next(index for index in range(win.layout_combo.count()) if win.layout_combo.itemData(index) == "macos")
    win.layout_combo.setCurrentIndex(target_index)

    assert preview.current_layout is not None
    assert preview.current_layout.get_layout_id() == LayoutManager.resolve_layout_id("macos")

    _select_entry(win, "viewmodels", viewmodel_labels()["BaseViewModel"])
    assert not win.layout_combo.isEnabled(), "Un ViewModel n'applique aucune disposition"


def test_gallery_closing_releases_the_current_viewmodel(qtbot):
    load_families()
    win = WidgetGalleryWindow()
    qtbot.addWidget(win)
    win.show()

    _select_entry(win, "viewmodels", viewmodel_labels()["BaseViewModel"])
    preview = win.preview.current_widget
    assert isinstance(preview, ObjectPreview)

    received: list[str] = []
    preview.target.subscribe_event("galerie-test", received.append)
    preview.target.publish_event("galerie-test", "avant fermeture")

    win.close()
    preview.target.publish_event("galerie-test", "apres fermeture")

    assert received == ["avant fermeture"], "La fermeture de la galerie doit libérer les abonnements du ViewModel"
    assert win.preview.current_widget is None, "L'aperçu courant doit être libéré à la fermeture"


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

    _assert_no_pending_worker(widget, class_name)

    widget.close()


# ── Famille « components » ─────────────────────────────────────────────────────

# Aucune exclusion : tous les composants ``QWidget`` déclarés doivent être
# prévisualisables. Les composants non ``QWidget`` (``QCompleter``, surligneurs, …)
# ne sont pas des aperçus de widget et sortent donc du périmètre de cette famille.


def _component_classes_declared_in_package() -> dict[str, type[QWidget]]:
    """Index des classes QWidget de ``ui/components`` par nom simple et identifiant qualifié.

    Les homonymes inter-modules ne sont accessibles que par leur identifiant qualifié,
    afin qu'aucun d'eux ne puisse être couvert par l'autre.
    """
    package = importlib.import_module("ankiforge.ui.components")
    package_dir = Path(next(iter(package.__path__)))
    declared: list[type[QWidget]] = []
    for module_path in sorted(package_dir.rglob("*.py")):
        if module_path.stem.startswith("_"):
            continue
        relative = module_path.relative_to(package_dir).with_suffix("")
        module = importlib.import_module("ankiforge.ui.components." + ".".join(relative.parts))
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if obj.__module__ == module.__name__ and issubclass(obj, QWidget) and not name.startswith("_"):
                declared.append(obj)

    homonyms = Counter(cls.__qualname__ for cls in declared)
    index: dict[str, type[QWidget]] = {}
    for cls in declared:
        index[f"{cls.__module__}.{cls.__qualname__}"] = cls
        if homonyms[cls.__qualname__] == 1:
            index[cls.__qualname__] = cls
    return index


@pytest.fixture(scope="module")
def declared_components() -> dict[str, type[QWidget]]:
    return _component_classes_declared_in_package()


def _component_class(key: str, declared: dict[str, type[QWidget]]) -> type[QWidget]:
    class_id = COMPONENT_CLASS_IDS[key]
    cls = declared.get(class_id)
    assert cls is not None, f"Classe introuvable pour l'entrée « {key} » : {class_id}"
    return cls


def test_components_family_covers_every_widget_class(declared_components):
    qualified_ids = {class_id for class_id in declared_components if "." in class_id}
    covered = {_component_class(key, declared_components) for key in COMPONENT_FACTORIES}

    missing = sorted(class_id for class_id in qualified_ids if declared_components[class_id] not in covered)
    extra = sorted(cls.__name__ for cls in covered - {declared_components[class_id] for class_id in qualified_ids})

    assert not missing, f"Composants non enregistrés dans la galerie : {missing}"
    assert not extra, f"Factories sans composant déclaré : {extra}"
    assert set(component_labels()) == set(COMPONENT_FACTORIES), "Chaque composant doit avoir un libellé de galerie"
    assert set(COMPONENT_CLASS_IDS) == set(COMPONENT_FACTORIES), "Chaque composant doit déclarer sa classe"


def test_components_family_is_registered_in_gallery():
    load_families()

    entries = WidgetGalleryRegistry.list(family="components")

    assert len(entries) == len(COMPONENT_FACTORIES)
    assert {entry.factory for entry in entries} == set(COMPONENT_FACTORIES.values())
    assert {entry.name for entry in entries} == set(component_labels().values())


def test_components_family_registration_is_idempotent():
    load_families()
    first_pass = len(WidgetGalleryRegistry.list(family="components"))

    load_families()

    assert len(WidgetGalleryRegistry.list(family="components")) == first_pass


def test_gallery_window_exposes_components_family(qtbot):
    win = WidgetGalleryWindow()
    qtbot.addWidget(win)

    families = {win.tree.topLevelItem(index).text(0) for index in range(win.tree.topLevelItemCount())}

    assert "components" in families


@pytest.mark.parametrize(("key", "factory"), list(COMPONENT_FACTORIES.items()))
def test_each_component_instantiates_without_crash(qtbot, declared_components, key, factory):
    expected_class = _component_class(key, declared_components)

    widget = factory()
    qtbot.addWidget(widget)

    # Les aperçus contextualisés (gouttière, barre d'état, voile de panneau) renvoient un
    # conteneur : le composant annoncé doit alors y être réellement présent.
    assert isinstance(widget, expected_class) or widget.findChild(expected_class) is not None, f"L'aperçu « {key} » n'instancie pas {expected_class.__name__}"

    _assert_no_pending_worker(widget, key)

    widget.close()


# ── Familles « layouts », « viewmodels », « models » et « shell » ──────────────


def _classes_declared_in_package(package_name: str, base: type[object], *, include_base: bool = False) -> dict[str, type[object]]:
    """Indexe les classes concrètes déclarées par les modules d'un paquet.

    La classe de base elle-même est exclue par défaut : les bases Qt du projet
    (``BaseLayout``, ``BasePaginatedPeeweeModel``) ne fixent pas de métaclasse ABC et
    ne sont donc pas détectées comme abstraites par :func:`inspect.isabstract`.
    """
    package = importlib.import_module(package_name)
    package_dir = Path(next(iter(package.__path__)))
    declared: dict[str, type[object]] = {}
    for module_path in sorted(package_dir.glob("*.py")):
        if module_path.stem.startswith("_"):
            continue
        module = importlib.import_module(f"{package_name}.{module_path.stem}")
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if obj is base and not include_base:
                continue
            if obj.__module__ == module.__name__ and issubclass(obj, base) and not inspect.isabstract(obj):
                declared[name] = obj
    return declared


def test_layouts_family_covers_every_layout_class():
    declared = _classes_declared_in_package("ankiforge.ui.layouts", BaseLayout)

    assert set(LAYOUT_FACTORIES) == set(declared)
    assert set(layout_labels()) == set(LAYOUT_FACTORIES)


def test_layouts_family_is_registered_in_gallery():
    load_families()

    entries = WidgetGalleryRegistry.list(family="layouts")

    assert {entry.name for entry in entries} == set(layout_labels().values())
    assert {entry.factory for entry in entries} == set(LAYOUT_FACTORIES.values())


def test_viewmodels_family_covers_every_viewmodel_class():
    declared = _classes_declared_in_package("ankiforge.ui.viewmodels", BaseViewModel, include_base=True)

    assert set(VIEWMODEL_FACTORIES) == set(declared)
    assert set(viewmodel_labels()) == set(VIEWMODEL_FACTORIES)


def test_viewmodels_family_is_registered_in_gallery():
    load_families()

    entries = WidgetGalleryRegistry.list(family="viewmodels")

    assert {entry.name for entry in entries} == set(viewmodel_labels().values())
    assert {entry.factory for entry in entries} == set(VIEWMODEL_FACTORIES.values())


def test_models_family_covers_every_qt_model_and_delegate_class():
    declared: dict[str, type[object]] = {}
    for package_name in ("ankiforge.ui.models",):
        for base in (QAbstractItemModel, QAbstractItemDelegate):
            declared.update(_classes_declared_in_package(package_name, base))

    covered = set(MODEL_FACTORIES) | EXCLUDED_QT_MODEL_CLASSES

    assert set(declared) == covered
    assert set(model_labels()) == set(MODEL_FACTORIES)


def test_models_family_is_registered_in_gallery():
    load_families()

    entries = WidgetGalleryRegistry.list(family="models")

    assert {entry.name for entry in entries} == set(model_labels().values())
    assert {entry.factory for entry in entries} == set(MODEL_FACTORIES.values())


def test_shell_family_covers_main_window_and_settings():
    main_window_module = importlib.import_module("ankiforge.ui.main_window")
    preferences_module = importlib.import_module("ankiforge.ui.preferences_dialog")

    main_windows = {name for name, obj in inspect.getmembers(main_window_module, inspect.isclass) if obj.__module__ == main_window_module.__name__ and issubclass(obj, QMainWindow)}

    assert main_windows == {"MainWindow"}
    assert preferences_module.PreferencesDialog is preferences_module.SettingsModal
    assert set(SHELL_CLASS_IDS) == set(SHELL_FACTORIES) == {"MainWindow", "SettingsModal"}
    assert set(shell_labels()) == set(SHELL_FACTORIES)


def test_shell_preview_renders_the_real_main_window_registry(qtbot):
    from ankiforge.ui.main_window import MainWindow

    load_families()
    entry = next(item for item in WidgetGalleryRegistry.list(family="shell") if item.name == shell_labels()["MainWindow"])

    widget = entry.factory()
    qtbot.addWidget(widget)

    assert isinstance(widget, QMainWindow)
    assert set(widget.navigation_ids()) == set(MainWindow.view_registry())
    assert widget.current_layout is not None
    assert widget.current_layout.get_layout_id() == "ide"


def test_shell_settings_entry_opens_in_modal(qtbot):
    load_families()
    entries = {item.name: item for item in WidgetGalleryRegistry.list(family="shell")}

    assert entries[shell_labels()["SettingsModal"]].modal is True
    assert entries[shell_labels()["MainWindow"]].modal is False

    dialogs = {item.name: item for item in WidgetGalleryRegistry.list(family="dialogs")}
    assert all(item.modal for item in dialogs.values())


def test_settings_modal_exposes_developer_tab_only_in_dev_mode(qtbot):
    from ankiforge.ui.widgets.settings_modal.modal import SettingsModal

    modal = SettingsModal()
    qtbot.addWidget(modal)
    assert modal.dev_tab is not None, "Le mode développement doit exposer l'onglet Développeur"
    assert modal.stacked_widget.count() == 10

    with patch("ankiforge.ui.widgets.settings_modal.modal.is_development", return_value=False):
        standard = SettingsModal()
        qtbot.addWidget(standard)

        assert standard.dev_tab is None, "Hors mode développement, l'onglet Développeur doit être absent"
        assert standard.stacked_widget.count() == 9
