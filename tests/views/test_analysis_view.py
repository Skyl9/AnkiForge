"""Tests unitaires et UI pour AnalysisView et l'onglet Fusions & Doublons."""

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import QSplitter, QWidget

from ankiforge.database.models import DeckModel, NoteModel, NoteTypeModel
from ankiforge.ui.components.buttons import IconButton
from ankiforge.ui.components.deck_select_window import DeckSelectWindow
from ankiforge.ui.components.duplicate_widgets import DuplicateMergeInspector
from ankiforge.ui.views.analysis_view.tabs.duplicates_merge_tab import AIDuplicatesMergeTab
from ankiforge.ui.views.analysis_view.view import AnalysisView

pytestmark = pytest.mark.ui


def test_ai_duplicates_merge_tab_has_vertical_splitter(qtbot) -> None:
    """Vérifie que AIDuplicatesMergeTab intègre un QSplitter vertical."""
    tab = AIDuplicatesMergeTab()
    qtbot.addWidget(tab)

    assert hasattr(tab, "splitter")
    assert isinstance(tab.splitter, QSplitter)
    assert tab.splitter.orientation() == Qt.Orientation.Vertical
    assert tab.splitter.indexOf(tab.matrix_table) != -1
    assert tab.splitter.indexOf(tab.merge_inspector) != -1


def test_ai_duplicates_merge_tab_initial_deck_id(qtbot) -> None:
    """Vérifie que self.selected_deck_id est initialisé à -1 (Tous les paquets)."""
    tab = AIDuplicatesMergeTab()
    qtbot.addWidget(tab)

    assert tab.selected_deck_id == -1
    assert tab.matrix_table.btn_deck.text() == "L'ensemble des paquets"


def test_ai_duplicates_merge_tab_run_scan_with_global_deck(qtbot) -> None:
    """Vérifie que run_duplicate_scan s'exécute dès l'arrivée ou au clic avec deck_id=-1."""
    tab = AIDuplicatesMergeTab()
    qtbot.addWidget(tab)

    with patch("ankiforge.ui.views.analysis_view.tabs.duplicates_merge_tab.DuplicateWorker") as mock_worker_cls:
        mock_instance = MagicMock()
        mock_worker_cls.return_value = mock_instance

        tab.run_duplicate_scan()

        mock_worker_cls.assert_called_once_with(deck_id=-1, parent=tab)
        assert mock_instance.start.called
        assert tab.matrix_table.btn_reanalyze.text() == "Recherche..."
        assert not tab.matrix_table.btn_reanalyze.isEnabled()


def test_duplicate_merge_inspector_katex_base_url(qtbot) -> None:
    """Vérifie que la bascule en mode KaTeX passe un base_url de fichier local valide à setHtmlSafe."""
    inspector = DuplicateMergeInspector()
    qtbot.addWidget(inspector)

    deck = DeckModel.create(name="Deck KaTeX Test")
    nt = NoteTypeModel.create(name="Type KaTeX", fields_schema='["Front", "Back"]', templates="[]", css_style="")
    note_a = NoteModel.create(guid="katex_a", deck=deck, note_type=nt)
    note_b = NoteModel.create(guid="katex_b", deck=deck, note_type=nt)

    conflict_data = {
        "note_a": note_a,
        "content_a": {"Front": "Formule $x^2 + y^2 = z^2$", "Back": "Pythagore"},
        "note_b": note_b,
        "content_b": {"Front": "Formule $x^2 + y^2 = z^2$", "Back": "Théorème de Pythagore"},
        "sim": 0.95,
    }
    inspector.load_conflict(conflict_data)

    calls = []

    def fake_set_html_safe(html: str, base_url: QUrl | None = None) -> None:
        calls.append((html, base_url))

    # Basculer la colonne A en mode KaTeX
    inspector.view_modes["A"] = "katex"
    web_view = inspector._get_or_create_web_view("A")
    web_view.setHtmlSafe = fake_set_html_safe  # type: ignore[assignment]

    inspector._refresh_col("A")

    assert len(calls) == 1
    html, base_url = calls[0]
    assert "katex" in html.lower()
    assert base_url is not None
    assert isinstance(base_url, QUrl)
    assert base_url.isLocalFile()


def test_deck_select_window_selects_all_decks_option(qtbot) -> None:
    """Vérifie que DeckSelectWindow pré-sélectionne 'Tous les paquets' quand selected_deck_id=-1."""
    win = DeckSelectWindow(allow_all=True, selected_deck_id=-1)
    qtbot.addWidget(win)

    current_item = win.tree.currentItem()
    assert current_item is not None
    assert current_item.text(0) == "Tous les paquets"
    assert current_item.data(0, Qt.ItemDataRole.UserRole) == -1
    assert win.btn_confirm.isEnabled()


def test_splitter_distribution_on_conflict_selected(qtbot) -> None:
    """Vérifie l'affichage de l'inspecteur et la répartition de l'espace dans le splitter."""
    tab = AIDuplicatesMergeTab()
    qtbot.addWidget(tab)
    tab.resize(800, 600)
    tab.show()

    assert tab.merge_inspector.isHidden()

    deck = DeckModel.create(name="Deck Splitter")
    nt = NoteTypeModel.create(name="Type Splitter", fields_schema='["Front", "Back"]', templates="[]", css_style="")
    note_a = NoteModel.create(guid="split_a", deck=deck, note_type=nt)
    note_b = NoteModel.create(guid="split_b", deck=deck, note_type=nt)

    row_data = {
        "idx": 0,
        "note_a": note_a,
        "content_a": {"Front": "Q1", "Back": "A1"},
        "note_b": note_b,
        "content_b": {"Front": "Q2", "Back": "A2"},
        "sim": 0.91,
    }
    tab.matrix_table.add_row(note_a, row_data["content_a"], note_b, row_data["content_b"], 0.91, row_data)
    tab.matrix_table.table.selectRow(0)

    assert not tab.merge_inspector.isHidden()
    sizes = tab.splitter.sizes()
    assert len(sizes) == 2
    assert sizes[0] > 0
    assert sizes[1] > 0


def test_analysis_view_header_has_no_orphan_settings_button(qtbot) -> None:
    """Vérifie qu'aucun bouton de paramètres inactif ne subsiste dans le header de l'IdePanel."""
    view = AnalysisView()
    qtbot.addWidget(view)

    assert not hasattr(view, "btn_settings")

    header_zone = view.main_panel.findChild(QWidget, "extraWidgetsZone")
    assert header_zone is not None
    assert header_zone.findChildren(IconButton) == []

    view.refresh_theme(MagicMock(color_yellow="#ffd43b"))


def test_analysis_view_integration(qtbot) -> None:
    """Vérifie l'intégration globale de l'onglet dans AnalysisView."""
    view = AnalysisView()
    qtbot.addWidget(view)

    assert view.tab_duplicates is not None
    assert isinstance(view.tab_duplicates, AIDuplicatesMergeTab)
    assert hasattr(view.tab_duplicates, "splitter")

    # Activation de l'onglet Doublons & vérification refresh_data
    view.set_active_tab_by_name("duplicates")
    with patch.object(view.tab_duplicates, "refresh_data") as mock_refresh:
        view.refresh_data()
        mock_refresh.assert_called_once()


def test_analysis_view_open_document_inspector(qtbot, mock_db) -> None:
    """Vérifie que open_document_inspector active l'onglet Documents et pré-remplit la recherche."""
    from ankiforge.database.models import DocumentModel

    doc = DocumentModel.create(title="Cours Anatomie Cardio", file_type="md")
    view = AnalysisView()
    qtbot.addWidget(view)

    with patch.object(view.tab_sources, "show_inspector") as mock_show:
        view.open_document_inspector(doc.id)
        assert view.main_panel.content_stack.currentIndex() == 1
        assert view.tab_sources.search_input.text() == "Cours Anatomie Cardio"
        mock_show.assert_called_once_with(doc.id)
