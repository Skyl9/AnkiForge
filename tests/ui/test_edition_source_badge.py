"""
Tests unitaires et UI pour le bandeau de traçabilité documentaire (DocumentSourceBadge)
et son intégration responsive au sein de la vue d'Édition (EditionView).
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QSizePolicy

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    DocumentChunkModel,
    DocumentModel,
    NoteChunkLinkModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
)
from ankiforge.ui.views.edition_view import DocumentSourceBadge, EditionView

pytestmark = pytest.mark.ui


def test_document_source_badge_initialization(qtbot: Any) -> None:
    """Vérifie la structure, les libellés, infobulles et contraintes de taille minimale."""
    badge = DocumentSourceBadge(
        doc_id=42,
        doc_title="Manuel de Neuroanatomie Clinique",
        heading="Chapitre 3 > 3.2 Transmission Synaptique",
        resolution="exact",
    )
    qtbot.addWidget(badge)
    badge.show()

    assert badge.doc_id == 42
    assert badge.doc_title == "Manuel de Neuroanatomie Clinique"
    assert badge.heading == "Chapitre 3 > 3.2 Transmission Synaptique"
    assert badge.lbl_title.text() == "Source : Manuel de Neuroanatomie Clinique"
    assert badge.lbl_src.text() == "Source : Manuel de Neuroanatomie Clinique"
    assert badge.lbl_heading is not None
    assert badge.lbl_heading.text() == "Chapitre 3 > 3.2 Transmission Synaptique"
    assert badge.ico_sub is not None

    # Bouton d'action et taille garantie
    assert badge.btn_go_doc.text() == "Voir le cours ➔"
    assert badge.btn_go_doc.cursor().shape() == Qt.CursorShape.PointingHandCursor
    assert badge.btn_go_doc.minimumWidth() >= 110
    assert badge.btn_go_doc.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Fixed
    assert badge.btn_go_doc.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Fixed

    # Tooltips
    assert "Manuel de Neuroanatomie Clinique" in badge.lbl_title.toolTip()
    assert "Chapitre 3 > 3.2 Transmission Synaptique" in badge.lbl_title.toolTip()
    assert "exact" in badge.lbl_title.toolTip()
    assert "Manuel de Neuroanatomie Clinique" in badge.btn_go_doc.toolTip()


def test_document_source_badge_without_heading(qtbot: Any) -> None:
    """Vérifie le repli propre sur une ligne unique lorsque la section est absente."""
    badge = DocumentSourceBadge(
        doc_id=10,
        doc_title="Document Général Sans Section",
        heading=None,
    )
    qtbot.addWidget(badge)
    badge.show()

    assert badge.lbl_title.text() == "Source : Document Général Sans Section"
    assert badge.lbl_heading is None
    assert badge.ico_sub is None
    assert badge.btn_go_doc.text() == "Voir le cours ➔"
    assert badge.btn_go_doc.minimumWidth() >= 110


def test_document_source_badge_navigation_signal(qtbot: Any) -> None:
    """Vérifie que le clic sur 'Voir le cours ➔' émet le signal request_navigation approprié."""
    badge = DocumentSourceBadge(
        doc_id=99,
        doc_title="Cours de Physiologie",
        heading="Section 1",
    )
    qtbot.addWidget(badge)
    badge.show()

    received_signals: list[tuple[str, Any]] = []
    badge.request_navigation.connect(lambda view, data: received_signals.append((view, data)))

    qtbot.mouseClick(badge.btn_go_doc, Qt.MouseButton.LeftButton)

    assert len(received_signals) == 1
    view_name, payload = received_signals[0]
    assert view_name == "documents"
    assert payload == {"doc_id": 99}


def test_document_source_badge_responsive_narrow_resize(qtbot: Any) -> None:
    """Vérifie que dans un contexte très étroit, le bouton d'action ne disparaît pas."""
    badge = DocumentSourceBadge(
        doc_id=7,
        doc_title="Titre de document extrêmement long destiné à tester l'élision automatique",
        heading="Hiérarchie très profonde > Sous-section A > Sous-section B > Détail technique précis",
    )
    qtbot.addWidget(badge)
    badge.resize(QSize(280, 80))
    badge.show()

    # Le titre et la section s'élident sans bloquer la largeur minimale du conteneur
    assert badge.lbl_title.minimumWidth() == 0
    assert badge.lbl_heading is not None
    assert badge.lbl_heading.minimumWidth() == 0

    # Le bouton d'action conserve impérativement sa largeur minimale protectrice
    assert badge.btn_go_doc.width() >= 110
    assert not badge.btn_go_doc.isHidden()


def test_edition_view_displays_source_badge_for_linked_note(qtbot: Any, mock_db: Any) -> None:
    """Vérifie l'affichage du DocumentSourceBadge dans EditionView pour une note liée à un chunk."""
    uid = uuid.uuid4().hex[:6]
    deck = DeckModel.create(name=f"Deck_{uid}")
    nt = NoteTypeModel.create(name=f"NT_{uid}", fields_schema='["Front", "Back"]')
    note = NoteModel.create(guid=f"guid_{uid}", note_type=nt)
    CardModel.create(note=note, deck=deck, template_index=0)
    NoteVersionModel.create(note=note, version_number=1, content=json.dumps({"Front": "Qu'est-ce que l'axone ?", "Back": "Un prolongement du neurone."}), is_active=True)

    doc = DocumentModel.create(title=f"Neurobiologie_{uid}", file_path=f"/tmp/neuro_{uid}.pdf", file_type="pdf")
    chunk = DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        content="Contenu de la section sur les axones...",
        page_number=14,
        heading_path="Chapitre 2 > Axone et Dendrites",
    )
    NoteChunkLinkModel.create(note=note, chunk=chunk, resolution="section")

    view = EditionView(ai_manager=None)
    qtbot.addWidget(view)
    view.refresh_data()

    # Capturer le signal de navigation applicative de la vue
    nav_calls: list[tuple[str, Any]] = []
    view.request_navigation.connect(lambda v, d: nav_calls.append((v, d)))

    view.select_note_by_id(note.id)

    # Trouver le badge dans le fields_layout
    badges = [view.fields_layout.itemAt(i).widget() for i in range(view.fields_layout.count()) if isinstance(view.fields_layout.itemAt(i).widget(), DocumentSourceBadge)]
    assert len(badges) == 1
    badge = badges[0]
    assert isinstance(badge, DocumentSourceBadge)
    assert badge.doc_id == doc.id
    assert badge.doc_title == f"Neurobiologie_{uid}"
    assert "Chapitre 2 > Axone et Dendrites" in badge.heading
    assert not badge.btn_go_doc.isHidden()

    # Déclencher la navigation au clic
    qtbot.mouseClick(badge.btn_go_doc, Qt.MouseButton.LeftButton)
    assert len(nav_calls) == 1
    assert nav_calls[0] == ("documents", {"doc_id": doc.id})


def test_edition_view_no_source_badge_for_unlinked_note(qtbot: Any, mock_db: Any) -> None:
    """Vérifie qu'aucune source_badge n'est instanciée lorsqu'une note n'a aucun document lié."""
    uid = uuid.uuid4().hex[:6]
    deck = DeckModel.create(name=f"Deck_Unlinked_{uid}")
    nt = NoteTypeModel.create(name=f"NT_Unlinked_{uid}", fields_schema='["Front", "Back"]')
    note = NoteModel.create(guid=f"guid_unlinked_{uid}", note_type=nt)
    CardModel.create(note=note, deck=deck, template_index=0)
    NoteVersionModel.create(note=note, version_number=1, content=json.dumps({"Front": "Q libre", "Back": "R libre"}), is_active=True)

    view = EditionView(ai_manager=None)
    qtbot.addWidget(view)
    view.refresh_data()
    view.select_note_by_id(note.id)

    badges = [view.fields_layout.itemAt(i).widget() for i in range(view.fields_layout.count()) if isinstance(view.fields_layout.itemAt(i).widget(), DocumentSourceBadge)]
    assert len(badges) == 0
