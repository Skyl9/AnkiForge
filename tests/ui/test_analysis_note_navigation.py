"""Navigation Analyse ➔ Éditeur : un clic sur une carte liée ouvre la note dans EditionView.

Couvre le ticket « Navigation : ouvrir une note dans EditionView au clic sur une carte
liée dans DocumentInspectorPanel » : les cartes Anki du panneau de droite ne sont plus
des blocs statiques, ce sont des cibles d'ouverture vers l'éditeur.

Seams exercés (composants tels que l'application les câble, jamais leurs détails internes) :
- `LinkedNoteCard` : affordances pointeur / survol / focus clavier, activation à la souris
  et au clavier, et restitution du `note_id` de la note qu'elle représente ;
- `DocumentInspectorPanel.request_navigation` : relais `("edition", {"note_id": ...})` ;
- `AISourcesDiagnosticTab.request_navigation` : relais depuis l'inspecteur de document ;
- `AnalysisView.request_navigation` ➔ `MainWindow._on_view_selected` ➔
  `EditionView.select_note_by_id` : bascule réelle de vue et sélection de la note.
"""

import re
import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    DocumentChunkModel,
    DocumentModel,
    NoteChunkLinkModel,
    NoteModel,
    NoteTypeModel,
)
from ankiforge.ui.style_engine import JETBRAINS_DARK, get_style_engine
from ankiforge.ui.views.analysis_view import (
    AISourcesDiagnosticTab,
    AnalysisView,
    DocumentInspectorPanel,
    LinkedNoteCard,
)

pytestmark = pytest.mark.ui

_COLOR_LITERAL = re.compile(r"#[0-9a-fA-F]{3,8}|rgba?\([^)]*\)")


def _document_with_linked_note() -> tuple[DocumentModel, DocumentChunkModel, NoteModel]:
    """Construit le cas nominal : une section couverte par une unique note Anki."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Cours Navigation {uid}",
        content="# Article 1\nLe contrat est un accord de volontés.",
        file_type="md",
    )
    chunk = DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        heading_path="Droit > Article 1",
        content="Le contrat est un accord de volontés.",
        content_hash=f"hash_{uid}",
    )
    deck = DeckModel.create(name=f"Deck Navigation {uid}")
    note_type = NoteTypeModel.select().first() or NoteTypeModel.create(
        name=f"Model Navigation {uid}",
        fields_schema='["Front", "Back"]',
        templates='[{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]',
        css_style="",
    )
    note = NoteModel.create(guid=uuid.uuid4().hex, note_type=note_type)
    note.add_version({"Front": "Définition du contrat ?", "Back": "Accord de volontés."}, source="manual")
    CardModel.create(note=note, deck=deck, template_index=0)
    NoteChunkLinkModel.create(note=note, chunk=chunk)
    return doc, chunk, note


def _linked_cards(panel: DocumentInspectorPanel) -> list[LinkedNoteCard]:
    """Cartes liées actuellement affichées dans le panneau droit de l'inspecteur.

    On lit le layout plutôt que l'arbre des enfants : les cartes de l'inspection précédente
    restent parentées jusqu'à leur suppression différée, alors qu'elles ne sont plus affichées.
    """
    return [widget for widget in (panel.cards_layout.itemAt(row).widget() for row in range(panel.cards_layout.count())) if isinstance(widget, LinkedNoteCard)]


def _left_click(widget: Any) -> None:
    """Clic principal au centre du widget, comme le ferait l'utilisateur."""
    QTest.mouseClick(widget, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, widget.rect().center())


def _engine_rule(selector: str) -> str:
    """Règle QSS du design system correspondant à un sélecteur de widget."""
    qss = get_style_engine().generate_stylesheet(JETBRAINS_DARK)
    match = re.search(rf"{re.escape(selector)}\s*\{{(.*?)\}}", qss, re.DOTALL)
    assert match is not None, f"sélecteur absent du QSS global : {selector}"
    return match.group(1)


@pytest.fixture
def inspector(qtbot: Any, mock_db: Any) -> SimpleNamespace:
    """Inspecteur affichant une section couverte, sa carte liée prête à être cliquée."""
    doc, chunk, note = _document_with_linked_note()
    panel = DocumentInspectorPanel(doc)
    qtbot.addWidget(panel)
    panel.show()
    panel.inspect_chunk(chunk.id)
    return SimpleNamespace(panel=panel, note=note, chunk=chunk)


@pytest.fixture
def navigation(inspector: SimpleNamespace) -> list[tuple[str, object]]:
    """Demandes de navigation émises par l'inspecteur, dans l'ordre."""
    emitted: list[tuple[str, object]] = []
    inspector.panel.request_navigation.connect(lambda target, payload: emitted.append((target, payload)))
    return emitted


# ---------------------------------------------------------------------------
# Critère 1 : la carte liée est une cible cliquable, survolable et focusable
# ---------------------------------------------------------------------------


class TestLinkedNoteCardAffordances:
    def test_panel_builds_one_clickable_card_per_linked_note(self, inspector: SimpleNamespace) -> None:
        assert len(_linked_cards(inspector.panel)) == 1

    def test_card_advertises_a_pointer_cursor(self, inspector: SimpleNamespace) -> None:
        card = _linked_cards(inspector.panel)[0]

        assert card.cursor().shape() == Qt.CursorShape.PointingHandCursor

    def test_card_hover_and_focus_styles_live_in_the_central_stylesheet(self, inspector: SimpleNamespace) -> None:
        """La règle d'or DESIGN.md : le style d'un widget va dans le `StyleEngine`, pas dans le widget."""
        card = _linked_cards(inspector.panel)[0]

        assert card.styleSheet() == ""
        assert f"border: 1px solid {JETBRAINS_DARK.accent_primary}" in _engine_rule("QFrame#LinkedNoteCard:hover")
        assert f"background-color: {JETBRAINS_DARK.bg_hover}" in _engine_rule("QFrame#LinkedNoteCard:hover")
        assert f"border: 1px solid {JETBRAINS_DARK.accent_primary}" in _engine_rule("QFrame#LinkedNoteCard:focus")

    def test_card_styles_come_from_the_theme_profile_only(self, inspector: SimpleNamespace) -> None:
        rule = _engine_rule("QFrame#LinkedNoteCard")
        colors = set(_COLOR_LITERAL.findall(rule))
        profile_colors = {value for name in dir(JETBRAINS_DARK) if not name.startswith("_") and isinstance(value := getattr(JETBRAINS_DARK, name), str)}

        assert colors, "la carte ne porte aucune couleur : le contrôle ne prouve rien"
        assert colors <= profile_colors

    def test_card_keeps_the_breathing_room_of_the_previous_static_card(self, inspector: SimpleNamespace) -> None:
        """La carte cliquable ne doit pas resserrer le contenu de la carte statique qu'elle remplace."""
        assert "padding: 10px" in _engine_rule("QFrame#LinkedNoteCard")

    def test_card_shows_deck_question_and_answer(self, inspector: SimpleNamespace) -> None:
        card = _linked_cards(inspector.panel)[0]
        texts = [lbl.text() for lbl in card.findChildren(QLabel)]

        assert "Paquet : Deck Navigation" in [t for t in texts if t.startswith("Paquet")][0]
        assert any(t.startswith("Q : Définition du contrat") for t in texts)
        assert any(t.startswith("R : Accord de volontés") for t in texts)

    def test_card_is_reachable_by_keyboard(self, inspector: SimpleNamespace) -> None:
        card = _linked_cards(inspector.panel)[0]

        assert card.focusPolicy() == Qt.FocusPolicy.StrongFocus
        assert card.accessibleName()
        assert "éditeur" in card.accessibleDescription().lower()


# ---------------------------------------------------------------------------
# Critère 2 : le clic émet la navigation vers l'éditeur avec le bon `note_id`
# ---------------------------------------------------------------------------


class TestLinkedNoteCardActivation:
    def test_left_click_requests_the_edition_view_for_that_note(self, inspector: SimpleNamespace, navigation: list[tuple[str, object]]) -> None:
        _left_click(_linked_cards(inspector.panel)[0])

        assert navigation == [("edition", {"note_id": inspector.note.id})]

    def test_clicking_the_question_text_still_navigates(self, inspector: SimpleNamespace, navigation: list[tuple[str, object]]) -> None:
        """Les libellés de la carte ne capturent pas l'événement : le clic remonte à la carte."""
        card = _linked_cards(inspector.panel)[0]
        question = next(lbl for lbl in card.findChildren(QLabel) if lbl.text().startswith("Q :"))

        _left_click(question)

        assert navigation == [("edition", {"note_id": inspector.note.id})]

    def test_right_click_never_navigates(self, inspector: SimpleNamespace, navigation: list[tuple[str, object]]) -> None:
        card = _linked_cards(inspector.panel)[0]

        QTest.mouseClick(card, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, card.rect().center())

        assert navigation == []

    @pytest.mark.parametrize("key", [Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space])
    def test_keyboard_activation_requests_the_edition_view(self, inspector: SimpleNamespace, navigation: list[tuple[str, object]], qtbot: Any, key: Any) -> None:
        qtbot.keyClick(_linked_cards(inspector.panel)[0], key)

        assert navigation == [("edition", {"note_id": inspector.note.id})]

    def test_mouse_click_gives_the_keyboard_focus_to_the_card(self, inspector: SimpleNamespace) -> None:
        card = _linked_cards(inspector.panel)[0]

        _left_click(card)

        assert card.hasFocus()


# ---------------------------------------------------------------------------
# Critère 2 (relais) : l'onglet Documents relaie la navigation de l'inspecteur
# ---------------------------------------------------------------------------


def test_documents_tab_relays_the_click_on_a_linked_note(qtbot: Any, mock_db: Any) -> None:
    doc, chunk, note = _document_with_linked_note()
    tab = AISourcesDiagnosticTab()
    qtbot.addWidget(tab)
    tab.show_inspector(doc.id)
    panel = tab.page_inspector.findChild(DocumentInspectorPanel)
    assert panel is not None
    panel.inspect_chunk(chunk.id)

    emitted: list[tuple[str, object]] = []
    tab.request_navigation.connect(lambda target, payload: emitted.append((target, payload)))

    _left_click(_linked_cards(panel)[0])

    assert emitted == [("edition", {"note_id": note.id})]


# ---------------------------------------------------------------------------
# Critère 3 : la fenêtre bascule sur l'éditeur et sélectionne la note cliquée
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_clicking_a_linked_note_opens_it_in_the_edition_view(qtbot: Any, mock_db: Any) -> None:
    """Parcours utilisateur complet : Analyse ➔ clic sur la carte ➔ note ouverte dans l'éditeur."""
    from ankiforge.ui.main_window import MainWindow
    from ankiforge.ui.views.edition_view import EditionView

    doc, chunk, note = _document_with_linked_note()
    with (
        patch("ankiforge.ui.views.dashboard_view.StatsWorker.start"),
        patch("ankiforge.utils.environment.is_testing", return_value=True),
    ):
        window = MainWindow(ai_manager=None)
    qtbot.addWidget(window)

    analysis = AnalysisView(ai_manager=None)
    qtbot.addWidget(analysis)
    analysis.request_navigation.connect(window._on_view_selected)
    analysis.tab_sources.show_inspector(doc.id)
    panel = analysis.tab_sources.page_inspector.findChild(DocumentInspectorPanel)
    assert panel is not None
    panel.inspect_chunk(chunk.id)

    _left_click(_linked_cards(panel)[0])

    assert window._current_view_id == "edition"
    edition = window._view_widgets["edition"]
    assert isinstance(edition, EditionView)
    assert edition._current_note is not None
    assert edition._current_note.id == note.id
    # La ligne de la note cliquée est bien celle qui est sélectionnée dans le tableau.
    selected_row = edition.note_table_model.find_row_by_note_id(note.id)
    assert selected_row >= 0
    assert edition.card_table.currentIndex().row() == selected_row
