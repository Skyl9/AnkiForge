"""Tests du rafraîchissement réactif granulaire des vues sur mutation MCP externe.

Couvre :
- le filtrage sélectif des vues par `MainWindow._on_mcp_data_mutated` ;
- la mise à jour granulaire d'EditionView sans perte de sélection ni écrasement
  d'une saisie en cours, y compris créations et mutations `card_ids` ;
- la restitution réelle de la sélection, du tampon éditeur et de l'état `dirty`
  dans DocumentsView ;
- la préservation d'un gabarit CSS en cours d'édition dans CardModelsView.

La résolution pure du domaine est testée dans
`tests/services/ai/test_mcp_mutation_domains.py`.
"""

from __future__ import annotations

import json
import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    DocumentModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
)
from ankiforge.ui.main_window import MainWindow
from ankiforge.ui.views.card_models_view import CardModelsView
from ankiforge.ui.views.documents_view import DocumentsView
from ankiforge.ui.views.edition_view import EditionView

pytestmark = pytest.mark.ui


def _make_note_type(template_count: int = 3) -> NoteTypeModel:
    uid = uuid.uuid4().hex[:8]
    templates = [
        {
            "name": f"Gabarit {idx + 1}",
            "qfmt": "{{Front}}",
            "afmt": "{{FrontSide}}<hr>{{Back}}",
        }
        for idx in range(template_count)
    ]
    return NoteTypeModel.create(
        name=f"Modèle MCP {uid}",
        fields_schema=json.dumps(["Front", "Back"]),
        templates=json.dumps(templates),
        css_style=".card { font-size: 14px; }",
    )


def _make_note(note_type: NoteTypeModel, front: str = "Recto initial", back: str = "Verso initial") -> NoteModel:
    uid = uuid.uuid4().hex[:8]
    deck = DeckModel.create(name=f"Paquet MCP {uid}")
    note = NoteModel.create(
        guid=f"guid_mcp_{uid}",
        note_type=note_type,
        tags=json.dumps(["source", "mcp"]),
    )
    NoteVersionModel.create(
        note=note,
        content=json.dumps({"Front": front, "Back": back}),
        version_number=1,
        is_active=True,
    )
    CardModel.create(note=note, deck=deck, template_index=0)
    return note


def _install_mock_views(window: MainWindow) -> dict[str, Any]:
    """Remplace les vues de la fenêtre par des doubles instrumentés."""
    mocks: dict[str, Any] = {}
    for view_id in ("edition", "analysis", "documents", "card-models", "creation", "batch"):
        widget = QWidget(window)
        widget.refresh_data = MagicMock()  # type: ignore[attr-defined]
        if view_id == "edition":
            widget.apply_mcp_mutation = MagicMock()  # type: ignore[attr-defined]
        window._view_widgets[view_id] = widget
        mocks[view_id] = widget
    return mocks


def test_main_window_routes_mutation_to_domain_views_only(qtbot, mock_db: Any) -> None:
    """Seules les vues du domaine impacté sont réveillées par une mutation MCP."""
    with patch("ankiforge.ui.views.dashboard_view.StatsWorker.start"):
        window = MainWindow(ai_manager=None, profile_name="test_mcp_routing")
        qtbot.addWidget(window)
        mocks = _install_mock_views(window)

        window._on_mcp_data_mutated({"type": "note_update", "domain": "cards", "note_id": 1})

        mocks["edition"].apply_mcp_mutation.assert_called_once()
        mocks["analysis"].refresh_data.assert_called_once()
        mocks["documents"].refresh_data.assert_not_called()
        mocks["card-models"].refresh_data.assert_not_called()

        window._on_mcp_data_mutated({"type": "note_type_update", "domain": "models", "note_type_id": 2})
        mocks["card-models"].refresh_data.assert_called_once()
        assert mocks["edition"].apply_mcp_mutation.call_count == 2
        mocks["documents"].refresh_data.assert_not_called()

        window._on_mcp_data_mutated({"type": "create_deck", "domain": "decks", "deck_id": 3})
        assert mocks["edition"].apply_mcp_mutation.call_count == 3
        mocks["creation"].refresh_data.assert_called_once()
        mocks["batch"].refresh_data.assert_called_once()
        assert mocks["analysis"].refresh_data.call_count == 1
        mocks["documents"].refresh_data.assert_not_called()

        window._on_mcp_data_mutated({"type": "document_update", "domain": "docs", "doc_id": 4})
        mocks["documents"].refresh_data.assert_called_once()
        assert mocks["analysis"].refresh_data.call_count == 1
        mocks["creation"].refresh_data.assert_called_once()

        window.close()


def test_main_window_legacy_apply_patch_refreshes_card_models(qtbot, mock_db: Any) -> None:
    """Un patch legacy `type=model` atteint bien la vue des types de note."""
    with patch("ankiforge.ui.views.dashboard_view.StatsWorker.start"):
        window = MainWindow(ai_manager=None, profile_name="test_mcp_legacy")
        qtbot.addWidget(window)
        mocks = _install_mock_views(window)

        window._on_mcp_data_mutated({"type": "model", "note_type_name": "Basique"})

        mocks["card-models"].refresh_data.assert_called_once()
        mocks["edition"].apply_mcp_mutation.assert_called_once()
        mocks["analysis"].refresh_data.assert_not_called()
        window.close()


def test_main_window_prefers_granular_handler(qtbot, mock_db: Any) -> None:
    """`apply_mcp_mutation()` est préféré à `refresh_data()` lorsqu'il est exposé."""
    with patch("ankiforge.ui.views.dashboard_view.StatsWorker.start"):
        window = MainWindow(ai_manager=None, profile_name="test_mcp_granular")
        qtbot.addWidget(window)
        mocks = _install_mock_views(window)

        window._on_mcp_data_mutated({"type": "note_update", "domain": "cards", "note_id": 9})

        mocks["edition"].apply_mcp_mutation.assert_called_once()
        mocks["edition"].refresh_data.assert_not_called()
        window.close()


def test_edition_view_apply_mcp_mutation_updates_current_note_in_place(qtbot, mock_db: Any) -> None:
    """Le contenu de la note affichée est rafraîchi sans recharger le tableau."""
    note_type = _make_note_type(template_count=1)
    note = _make_note(note_type)

    view = EditionView(ai_manager=None)
    qtbot.addWidget(view)
    view.refresh_data()
    view.select_note_by_id(note.id)

    row_before = view.card_table.currentIndex().row()
    row_count_before = view.note_table_model.rowCount()
    selected_before = view.card_table.get_selected_rows()

    note.add_version({"Front": "Recto muté par MCP", "Back": "Verso muté par MCP"}, source="mcp")
    view.apply_mcp_mutation(
        {
            "type": "note_update",
            "domain": "cards",
            "note_id": note.id,
            "target_id": note.id,
        }
    )

    assert view._current_note is not None
    assert view._current_note.id == note.id
    assert view.dynamic_field_widgets["Front"].get_text() == "Recto muté par MCP"
    assert view.dynamic_field_widgets["Back"].get_text() == "Verso muté par MCP"
    assert view.card_table.currentIndex().row() == row_before
    assert view.card_table.get_selected_rows() == selected_before
    assert view.note_table_model.rowCount() == row_count_before

    model_row = view.note_table_model.find_row_by_note_id(note.id)
    display = view.note_table_model.data(view.note_table_model.index(model_row, 2), Qt.ItemDataRole.DisplayRole)
    assert "Recto muté par MCP" in str(display)


def test_edition_view_apply_mcp_mutation_preserves_dirty_form(qtbot, mock_db: Any) -> None:
    """Une saisie utilisateur en cours n'est jamais écrasée par une mutation externe."""
    note_type = _make_note_type(template_count=1)
    note = _make_note(note_type)

    view = EditionView(ai_manager=None)
    qtbot.addWidget(view)
    view.refresh_data()
    view.select_note_by_id(note.id)

    front_editor = view.dynamic_field_widgets["Front"]
    front_editor.set_text("Saisie locale en cours")
    assert view._dirty is True

    note.add_version({"Front": "Écriture externe MCP", "Back": "Verso externe"}, source="mcp")
    view.apply_mcp_mutation({"type": "note_update", "domain": "cards", "note_id": note.id})

    assert front_editor.get_text() == "Saisie locale en cours"
    assert view._dirty is True
    # Le modèle de table reflète bien la vérité base, même si le formulaire est préservé.
    row = view.note_table_model.find_row_by_note_id(note.id)
    display = view.note_table_model.data(view.note_table_model.index(row, 2), Qt.ItemDataRole.DisplayRole)
    assert "Écriture externe MCP" in str(display)


def test_edition_view_apply_mcp_mutation_inserts_created_note(qtbot, mock_db: Any) -> None:
    """Une note créée par MCP est insérée sans recharger ni perdre la sélection."""
    note_type = _make_note_type(template_count=1)
    existing = _make_note(note_type)

    view = EditionView(ai_manager=None)
    qtbot.addWidget(view)
    view.refresh_data()
    view.select_note_by_id(existing.id)
    row_count_before = view.note_table_model.rowCount()

    created_note = _make_note(note_type, front="Nouvelle note MCP", back="Réponse")
    view.apply_mcp_mutation({"type": "note_create", "domain": "cards", "note_id": created_note.id})

    assert view.note_table_model.rowCount() == row_count_before + 1
    assert view.note_table_model.find_row_by_note_id(created_note.id) >= 0
    assert view._current_note is not None
    assert view._current_note.id == existing.id


def test_edition_view_apply_mcp_mutation_resolves_card_ids(qtbot, mock_db: Any) -> None:
    """Une mutation carte (`card_ids`) met à jour la note et son paquet, jamais `target_id`."""
    note_type = _make_note_type(template_count=1)
    note = _make_note(note_type)
    target_deck = DeckModel.create(name=f"Paquet cible {uuid.uuid4().hex[:8]}")
    card = CardModel.get(CardModel.note == note.id)

    view = EditionView(ai_manager=None)
    qtbot.addWidget(view)
    view.refresh_data()
    view.select_note_by_id(note.id)

    card.deck = target_deck
    card.save()
    view.apply_mcp_mutation(
        {
            "type": "move_cards",
            "domain": "cards",
            "card_ids": [card.id],
            "target_id": target_deck.id,
            "target_deck": target_deck.name,
        }
    )

    row = view.note_table_model.find_row_by_note_id(note.id)
    headers = [view.note_table_model.headerData(col, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole) for col in range(view.note_table_model.columnCount())]
    deck_col = headers.index("Deck")
    display = view.note_table_model.data(view.note_table_model.index(row, deck_col), Qt.ItemDataRole.DisplayRole)
    assert display == target_deck.name


def test_documents_view_apply_mcp_mutation_preserves_selection_and_editor(qtbot, mock_db: Any) -> None:
    """Le document courant, sa saisie non enregistrée et l'état dirty survivent à la mutation."""
    uid = uuid.uuid4().hex[:8]
    document = DocumentModel.create(title=f"Document MCP {uid}", content="Contenu initial", file_type="md")

    view = DocumentsView()
    qtbot.addWidget(view)
    view.refresh_data()
    view._select_doc_id_in_tree(document.id)
    assert view._current_doc_id == document.id

    view.text_editor.set_content("Saisie locale non sauvegardée")
    view._dirty = True

    document.content = "Contenu muté par MCP"
    document.save()
    view.apply_mcp_mutation({"type": "document_update", "domain": "docs", "doc_id": document.id})

    assert view._current_doc_id == document.id
    assert view.text_editor.get_content() == "Saisie locale non sauvegardée"
    assert view.is_dirty() is True
    items = view.tree_explorer.selectedItems()
    assert items
    assert items[0].data(0, Qt.ItemDataRole.UserRole)["id"] == document.id


def test_documents_view_apply_mcp_mutation_clears_deleted_document(qtbot, mock_db: Any) -> None:
    """Un document supprimé en externe est retiré de l'état courant sans document fantôme."""
    uid = uuid.uuid4().hex[:8]
    document = DocumentModel.create(title=f"Document supprimé {uid}", content="Contenu", file_type="md")

    view = DocumentsView()
    qtbot.addWidget(view)
    view.refresh_data()
    view._select_doc_id_in_tree(document.id)
    assert view._current_doc_id == document.id

    document.delete_instance()
    view.apply_mcp_mutation({"type": "document_delete", "domain": "docs", "doc_id": document.id})

    assert view._current_doc_id is None
    assert view.text_editor.get_content() == ""
    assert view.is_dirty() is False


def test_card_models_view_apply_mcp_mutation_preserves_template_and_subtab(qtbot, mock_db: Any) -> None:
    """Le gabarit et le sous-onglet CSS/Recto/Verso actifs sont conservés après rechargement."""
    note_type = _make_note_type(template_count=3)

    view = CardModelsView(ai_manager=None)
    qtbot.addWidget(view)
    view.refresh_data()

    target_item = None
    for idx in range(view.list_widget.count()):
        item = view.list_widget.item(idx)
        model = item.data(Qt.ItemDataRole.UserRole)
        if model and model.id == note_type.id:
            target_item = item
            break
    assert target_item is not None
    view.list_widget.setCurrentItem(target_item)
    assert view._current_model is not None
    assert view._current_model.id == note_type.id

    view._current_template_idx = 2
    view._populate_template_selector()
    view._load_current_template_to_editors()
    view._switch_subtab(2)

    view.apply_mcp_mutation({"type": "note_type_update", "domain": "models", "note_type_id": note_type.id})

    assert view._current_model is not None
    assert view._current_model.id == note_type.id
    assert view._current_template_idx == 2
    assert view.editor_stack.currentIndex() == 2


def test_card_models_view_apply_mcp_mutation_defers_when_dirty(qtbot, mock_db: Any) -> None:
    """Un gabarit CSS en cours d'édition n'est jamais écrasé par une mutation externe."""
    note_type = _make_note_type(template_count=1)

    view = CardModelsView(ai_manager=None)
    qtbot.addWidget(view)
    view.refresh_data()

    for idx in range(view.list_widget.count()):
        item = view.list_widget.item(idx)
        model = item.data(Qt.ItemDataRole.UserRole)
        if model and model.id == note_type.id:
            view.list_widget.setCurrentItem(item)
            break

    view.css_editor_wrapper.setPlainText(".card { color: red; } /* saisie locale */")
    assert view.is_dirty() is True

    note_type.css_style = ".card { color: blue; }"
    note_type.save()
    view.apply_mcp_mutation({"type": "css_tune", "domain": "models", "note_type_id": note_type.id})

    assert "saisie locale" in view.css_editor_wrapper.toPlainText()
    assert view.is_dirty() is True
