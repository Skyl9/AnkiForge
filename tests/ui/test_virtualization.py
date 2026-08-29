"""
Tests unitaires pour l'architecture Model/View et la virtualisation haute performance (60 FPS) d'AnkiForge.
Valide BasePaginatedPeeweeModel, NoteVirtualTableModel, VirtualChunkListModel, VirtualTableView,
VirtualListView et les délégués graphiques vectoriels QStyledItemDelegate.
"""

import json
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QModelIndex, QRect, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QStyleOptionViewItem, QWidget

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    DocumentChunkModel,
    DocumentModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
    db,
)
from ankiforge.ui.components.lists import VirtualListView
from ankiforge.ui.components.tables import VirtualTableView
from ankiforge.ui.models import (
    IS_INVALID_CARD_ROLE,
    NOTE_ID_ROLE,
    TAGS_LIST_ROLE,
    BadgeItemDelegate,
    BasePaginatedPeeweeModel,
    CheckboxItemDelegate,
    NoteVirtualTableModel,
    ProgressBarItemDelegate,
    SimilarityBadgeDelegate,
    SrsMasteryDelegate,
    TagItemDelegate,
    VirtualChunkListModel,
    strip_html,
)
from ankiforge.ui.theme import DesignTokens


@pytest.fixture
def sample_virtual_data(mock_db):
    """Crée une collection de test pour valider la pagination et le batch prefetch."""
    with db.atomic():
        deck_main = DeckModel.create(name="Médecine")
        deck_sub = DeckModel.create(name="Médecine::Cardiologie")

        nt_basic = NoteTypeModel.create(
            name="Basique",
            fields_schema=json.dumps(["Front", "Back"]),
            templates="[]",
            css_style="",
        )
        nt_cloze = NoteTypeModel.create(
            name="Texte à trou",
            fields_schema=json.dumps(["Text", "Extra"]),
            templates="[]",
            css_style="",
        )

        notes = []
        for i in range(1, 25):
            nt = nt_basic if i % 2 == 1 else nt_cloze
            d = deck_main if i <= 10 else deck_sub
            tags = ["urgent", "bio"] if i % 3 == 0 else ["cours"]

            n = NoteModel.create(
                note_type=nt,
                tags=json.dumps(tags),
                status="new",
                guid=f"guid_virt_{i}",
            )
            content = {"Front": f"Question {i}", "Back": f"Réponse <b>{i}</b>"} if nt == nt_basic else {"Text": f"Cloze {{c1::{i}}}", "Extra": f"Remarque {i}"}
            NoteVersionModel.create(note=n, content=json.dumps(content), is_active=True, version_number=1)
            CardModel.create(note=n, deck=d)
            notes.append(n)

    return {"deck_main": deck_main, "deck_sub": deck_sub, "notes": notes, "nt_basic": nt_basic, "nt_cloze": nt_cloze}


def test_strip_html_helper():
    assert strip_html("<b>Bonjour</b> &amp; <i>Monde</i>") == "Bonjour & Monde"
    assert strip_html(None) == ""
    assert strip_html("Simple text") == "Simple text"


def test_base_paginated_peewee_model(sample_virtual_data):
    """Teste le protocole canFetchMore / fetchMore sur la classe abstraite de base."""
    query = NoteModel.select().order_by(NoteModel.id.asc())
    model = BasePaginatedPeeweeModel[NoteModel](query=query, total_count=24, chunk_size=10)

    assert model.total_count == 24
    assert model.loaded_count == 10
    assert model.rowCount() == 10
    assert model.columnCount() == 0
    assert model.canFetchMore() is True

    # 2ème batch
    model.fetchMore()
    assert model.loaded_count == 20
    assert model.rowCount() == 20
    assert model.canFetchMore() is True

    # 3ème batch (reliquat de 4)
    model.fetchMore()
    assert model.loaded_count == 24
    assert model.rowCount() == 24
    assert model.canFetchMore() is False

    # fetchMore quand complet
    model.fetchMore()
    assert model.loaded_count == 24

    # Accesseurs
    first_note = model.get_row(0)
    assert first_note is not None
    assert first_note.id == sample_virtual_data["notes"][0].id
    assert model.get_row(999) is None

    # Clear
    model.clear()
    assert model.total_count == 0
    assert model.loaded_count == 0
    assert model.rowCount() == 0


def test_note_virtual_table_model_standard_mode(sample_virtual_data):
    """Teste le modèle NoteVirtualTableModel en mode générique (Tous les modèles)."""
    query = NoteModel.select().order_by(NoteModel.id.asc())
    model = NoteVirtualTableModel(query=query, chunk_size=15)

    assert model.columnCount() == 6
    assert model.headerData(0, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole) == ""
    assert model.headerData(1, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole) == "Recto (Tri)"
    assert model.headerData(3, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole) == "Modèle"
    assert model.headerData(4, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole) == "Deck"
    assert model.headerData(5, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole) == "Tags"

    # Vérification des données de ligne 0 (Basique, Question 1, Réponse 1)
    idx_chk = model.index(0, 0)
    assert model.data(idx_chk, Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Unchecked
    assert model.data(idx_chk, NOTE_ID_ROLE) == sample_virtual_data["notes"][0].id

    idx_recto = model.index(0, 1)
    assert model.data(idx_recto, Qt.ItemDataRole.DisplayRole) == "Question 1"
    assert model.data(idx_recto, IS_INVALID_CARD_ROLE) is False

    idx_verso = model.index(0, 2)
    assert "Réponse 1" in model.data(idx_verso, Qt.ItemDataRole.DisplayRole)

    idx_model = model.index(0, 3)
    assert model.data(idx_model, Qt.ItemDataRole.DisplayRole) == "Basique"

    idx_deck = model.index(0, 4)
    assert model.data(idx_deck, Qt.ItemDataRole.DisplayRole) == "Médecine"

    idx_tags = model.index(0, 5)
    assert "#cours" in model.data(idx_tags, Qt.ItemDataRole.DisplayRole)
    assert model.data(idx_tags, TAGS_LIST_ROLE) == ["cours"]

    # Toggle Checkbox
    model.setData(idx_chk, Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole)
    assert model.data(idx_chk, Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked
    assert model.get_checked_note_ids() == [sample_virtual_data["notes"][0].id]

    # Select All O(1)
    model.set_all_checked(True)
    assert len(model.get_checked_note_ids()) == 24
    model.set_all_checked(False)
    assert len(model.get_checked_note_ids()) == 0


def test_note_virtual_table_model_dynamic_fields_mode(sample_virtual_data):
    """Teste le modèle NoteVirtualTableModel avec colonnes dynamiques par modèle de note."""
    query = NoteModel.select().where(NoteModel.note_type == sample_virtual_data["nt_basic"].id)
    model = NoteVirtualTableModel(query=query, active_model_fields=["Front", "Back"])

    assert model.columnCount() == 5  # "", "Front", "Back", "Deck", "Tags" -> 1 + 2 + 2 = 5
    assert model.headerData(1, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole) == "Front"
    assert model.headerData(2, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole) == "Back"
    assert model.headerData(3, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole) == "Deck"
    assert model.headerData(4, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole) == "Tags"

    # Mise à jour de contenu à chaud
    first_nid = sample_virtual_data["notes"][0].id
    model.update_note_content(first_nid, {"Front": "Question 1 Modifiée", "Back": "Nouvelle Réponse"})
    assert model.data(model.index(0, 1), Qt.ItemDataRole.DisplayRole) == "Question 1 Modifiée"
    assert model.data(model.index(0, 2), Qt.ItemDataRole.DisplayRole) == "Nouvelle Réponse"


def test_note_virtual_table_model_crud_and_invalid_card(sample_virtual_data):
    """Teste la détection de carte invalide, l'insertion au sommet et la suppression."""
    query = NoteModel.select()
    model = NoteVirtualTableModel(query=query)

    # Nouvelle note vide (Invalide)
    with db.atomic():
        empty_note = NoteModel.create(note_type=sample_virtual_data["nt_basic"], tags="[]", status="new", guid="empty_note")
        NoteVersionModel.create(note=empty_note, content=json.dumps({"Front": "", "Back": ""}), is_active=True)

    model.prepend_note(empty_note)
    assert model.rowCount() == 25
    assert model.data(model.index(0, 1), IS_INVALID_CARD_ROLE) is True
    assert "CARTE INVALIDE" in model.data(model.index(0, 1), Qt.ItemDataRole.DisplayRole)

    # Suppression
    model.remove_notes_by_ids([empty_note.id])
    assert model.rowCount() == 24
    assert model.find_row_by_note_id(empty_note.id) == -1


def test_virtual_chunk_list_model(mock_db):
    """Teste le modèle de fragments RAG VirtualChunkListModel."""
    with db.atomic():
        doc = DocumentModel.create(title="Physiologie.pdf", file_type="pdf", total_pages=10)
        chunks = []
        for i in range(1, 15):
            c = DocumentChunkModel.create(
                document=doc,
                chunk_index=i,
                page_number=i,
                heading_path=f"Chapitre 1 > Section {i}",
                content=f"Extrait de cours pour le paragraphe {i} concernant le système nerveux.",
            )
            chunks.append(c)

    query = DocumentChunkModel.select().where(DocumentChunkModel.document == doc)
    model = VirtualChunkListModel()
    model.set_document_query(query)

    assert model.rowCount() == 14
    first_item = model.data(model.index(0, 0), Qt.ItemDataRole.DisplayRole)
    assert "p.1" in first_item
    assert "Chapitre 1 > Section 1" in first_item

    # Test avec résultats statiques RAG Sandbox
    model.set_static_results(
        [
            {"id": 101, "heading_path": "Recherche", "content": "Résultat top 1", "score": 0.94},
            {"id": 102, "heading_path": "Recherche", "content": "Résultat top 2", "score": 0.81},
        ]
    )
    assert model.rowCount() == 2
    assert "Similarité: 94%" in model.data(model.index(0, 0), Qt.ItemDataRole.DisplayRole)
    assert "Similarité: 81%" in model.data(model.index(1, 0), Qt.ItemDataRole.DisplayRole)


def test_virtual_components_rendering(qtbot):
    """Teste l'instanciation et la configuration haute performance des composants VirtualTableView et VirtualListView."""
    tbl = VirtualTableView()
    lst = VirtualListView()
    qtbot.addWidget(tbl)
    qtbot.addWidget(lst)

    # Vérifications des propriétés de virtualisation
    assert tbl.verticalHeader().isVisible() is False
    assert tbl.showGrid() is False
    assert lst.uniformItemSizes() is True

    # Test de refresh_theme sans crash
    mock_profile = MagicMock()
    mock_profile.bg_panel = "#1e1e2e"
    mock_profile.bg_sidebar = "#181825"
    mock_profile.border_color = "#313244"
    mock_profile.radius_md = 8
    mock_profile.text_primary = "#cdd6f4"
    mock_profile.text_muted = "#a6adc8"
    mock_profile.bg_active = "#45475a"
    mock_profile.bg_hover = "#313244"

    tbl.refresh_theme(mock_profile)
    lst.refresh_theme(mock_profile)


def test_delegates_painting(qtbot):
    """Teste le rendu vectoriel QPainter des délégués (sans fuite ni widget enfant)."""
    from PySide6.QtWidgets import QStyle

    widget = QWidget()
    qtbot.addWidget(widget)

    image = QImage(300, 100, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.black)
    painter = QPainter(image)

    opt = QStyleOptionViewItem()
    opt.rect = QRect(0, 0, 200, 34)
    opt.state = QStyle.StateFlag.State_Enabled

    # 1. BadgeItemDelegate
    badge_del = BadgeItemDelegate(parent=widget)
    idx_mock = MagicMock(spec=QModelIndex)
    idx_mock.data.side_effect = lambda role: "MÉDECINE" if role == Qt.ItemDataRole.DisplayRole else None
    badge_del.paint(painter, opt, idx_mock)

    # 2. TagItemDelegate
    tag_del = TagItemDelegate(parent=widget)
    idx_tag_mock = MagicMock(spec=QModelIndex)
    idx_tag_mock.data.side_effect = lambda role: ["tag1", "tag2"] if role == TAGS_LIST_ROLE else "tag1 tag2"
    tag_del.paint(painter, opt, idx_tag_mock)

    # 3. CheckboxItemDelegate
    chk_del = CheckboxItemDelegate(parent=widget)
    idx_chk_mock = MagicMock(spec=QModelIndex)
    idx_chk_mock.data.side_effect = lambda role: Qt.CheckState.Checked if role == Qt.ItemDataRole.CheckStateRole else None
    chk_del.paint(painter, opt, idx_chk_mock)

    # 4. SimilarityBadgeDelegate
    sim_del = SimilarityBadgeDelegate(parent=widget)
    idx_sim_mock = MagicMock(spec=QModelIndex)
    idx_sim_mock.data.side_effect = lambda role: "97.5%" if role == Qt.ItemDataRole.DisplayRole else None
    sim_del.paint(painter, opt, idx_sim_mock)

    # 5. SrsMasteryDelegate
    srs_del = SrsMasteryDelegate(parent=widget)
    idx_srs_mock = MagicMock(spec=QModelIndex)
    srs_data = (("🟢 Maîtrisée", DesignTokens.COLOR_GREEN), ("🔴 Nouvelle", DesignTokens.COLOR_RED))
    idx_srs_mock.data.side_effect = lambda role: srs_data if role == Qt.ItemDataRole.UserRole else "🟢 Maîtrisée vs 🔴 Nouvelle"
    srs_del.paint(painter, opt, idx_srs_mock)

    # 6. ProgressBarItemDelegate
    prog_del = ProgressBarItemDelegate(parent=widget)
    idx_prog_mock = MagicMock(spec=QModelIndex)
    idx_prog_mock.data.side_effect = lambda role: 65 if role == Qt.ItemDataRole.UserRole else "65"
    prog_del.paint(painter, opt, idx_prog_mock)

    painter.end()
