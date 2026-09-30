from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from PySide6.QtCore import Qt

from ankiforge.database.models import DocumentChunkModel, DocumentModel
from ankiforge.repositories.document_repository import DocumentRepository
from ankiforge.ui.dialogs.document_scope_dialog import DocumentScopeDialog
from ankiforge.ui.views.documents_view.dialogs.delimitation_dialog import (
    DocumentDelimitationDialog,
    SectionRowWidget,
)

pytestmark = pytest.mark.ui

CHAPTER_PAGES = 3
ALL_CHAPTERS = [f"Chapitre {p}" for p in range(1, CHAPTER_PAGES + 1)]


def _make_paginated_doc(prefix: str) -> DocumentModel:
    """Construit un PDF paginé à chapitres (1 chapitre par page) exploitable par les 3 modes."""
    uid = uuid.uuid4().hex[:6]
    content = "\n\n".join(f"<!-- PAGE: {p} -->\n# Chapitre {p}\nContenu pédagogique du chapitre {p}." for p in range(1, CHAPTER_PAGES + 1))
    doc = DocumentModel.create(title=f"{prefix} {uid}", file_type="pdf", total_pages=CHAPTER_PAGES, content=content)
    for p in range(1, CHAPTER_PAGES + 1):
        DocumentChunkModel.create(
            document=doc,
            chunk_index=p - 1,
            page_number=p,
            heading_path=f"Chapitre {p}",
            content=f"Contenu pédagogique du chapitre {p}.",
            content_hash=f"hash_{prefix}_{uid}_{p}",
        )
    return doc


class _Probe:
    """Adaptateur à noms d'attributs uniformes pour DocumentScopeDialog / DocumentDelimitationDialog."""

    def __init__(self, dlg: Any, prefix: str) -> None:
        self.dlg = dlg
        self.btn_all = getattr(dlg, f"btn_{prefix}mode_all")
        self.btn_range = getattr(dlg, f"btn_{prefix}mode_range")
        self.btn_chapters = getattr(dlg, f"btn_{prefix}mode_structure")
        self.btn_sections = getattr(dlg, f"btn_{prefix}mode_sections")

    def __getattr__(self, name: str) -> Any:
        return getattr(self.dlg, name)

    def row(self, index: int) -> SectionRowWidget:
        row = self.sections_list.itemWidget(self.sections_list.item(index))
        assert isinstance(row, SectionRowWidget)
        return row

    def headings(self) -> list[str]:
        return [str(chunk.get("heading_path") or "") for chunk in self.dlg._selected_chunks_for_mode()]

    @property
    def publishes_result(self) -> bool:
        """Seule DocumentScopeDialog publie un résultat de portée complet (payload pages/chapitres)."""
        return isinstance(self.dlg, DocumentScopeDialog)

    def result(self) -> dict[str, Any]:
        """Résultat de portée exposé par la dialogue, ou son seul mode actif si elle ne publie pas de payload."""
        if self.publishes_result:
            return self.dlg.get_result()
        return {"selection_mode": self.dlg.selection_mode}


def _probes(doc: DocumentModel, qtbot: Any) -> list[_Probe]:
    scope = DocumentScopeDialog(doc)
    qtbot.addWidget(scope)
    delimitation = DocumentDelimitationDialog(doc)
    qtbot.addWidget(delimitation)
    return [_Probe(scope, ""), _Probe(delimitation, "scope_")]


# --- Critère 3 : masquage dynamique de pages_card ---------------------------------------


@pytest.mark.parametrize("mode", ["chapters", "sections"])
def test_pages_card_hidden_outside_pages_mode(qtbot: Any, mock_db: Any, mode: str) -> None:
    """`pages_card` n'est visible qu'en mode pages : plus de filtre croisé visuel possible."""
    doc = _make_paginated_doc("Masquage")
    for probe in _probes(doc, qtbot):
        assert probe.selection_mode == "pages"
        assert not probe.pages_card.isHidden()

        button = probe.btn_chapters if mode == "chapters" else probe.btn_sections
        button.click()

        assert probe.selection_mode == mode
        assert probe.pages_card.isHidden()
        assert probe.slider_scope_container.isHidden()
        assert probe.range_presets_container.isHidden()
        assert probe.range_info_card.isHidden()

        probe.btn_all.click()
        assert probe.selection_mode == "pages"
        assert not probe.pages_card.isHidden()


def test_pages_card_reappears_in_range_sub_mode(qtbot: Any, mock_db: Any) -> None:
    """Le sous-mode 'Plage de pages' reste un mode pages : le panneau revient avec ses curseurs."""
    doc = _make_paginated_doc("Plage")
    for probe in _probes(doc, qtbot):
        probe.btn_sections.click()
        assert probe.pages_card.isHidden()

        probe.btn_range.click()
        assert probe.selection_mode == "pages"
        assert not probe.pages_card.isHidden()
        assert not probe.slider_scope_container.isHidden()


# --- Critère 1 : activation automatique --------------------------------------------------


def test_chapter_card_interaction_auto_activates_chapters_mode(qtbot: Any, mock_db: Any) -> None:
    """Cocher une carte chapitre depuis le mode pages bascule le mode, sans clic sur la barre."""
    doc = _make_paginated_doc("AutoChapitre")
    for probe in _probes(doc, qtbot):
        assert probe.selection_mode == "pages"
        assert not probe.btn_chapters.isHidden()

        probe._chapter_cards[-1].checkbox.setChecked(False)

        assert probe.selection_mode == "chapters"
        assert probe.btn_chapters.isChecked()
        assert probe.pages_card.isHidden()
        assert ALL_CHAPTERS[-1] not in probe.headings()


def test_chapter_range_combo_interaction_auto_activates_chapters_mode(qtbot: Any, mock_db: Any) -> None:
    """Le sélecteur de plage de chapitres est une interaction chapitre : il active son mode."""
    doc = _make_paginated_doc("AutoCombo")
    for probe in _probes(doc, qtbot):
        assert probe.combo_c_end.count() == CHAPTER_PAGES
        probe.combo_c_end.setCurrentIndex(0)

        assert probe.selection_mode == "chapters"
        assert probe.pages_card.isHidden()
        assert [card.chapter_index for card in probe._chapter_cards if card.is_checked()] == [0]
        assert probe.headings() == ALL_CHAPTERS[:1]


def test_section_checkbox_interaction_auto_activates_sections_mode(qtbot: Any, mock_db: Any) -> None:
    """Cocher une section depuis un autre mode active le mode sections et révèle son volet."""
    doc = _make_paginated_doc("AutoSection")
    for probe in _probes(doc, qtbot):
        probe.btn_chapters.click()
        assert probe.selection_mode == "chapters"
        assert probe.sections_list.isHidden()

        probe.row(0).checkbox.setChecked(False)

        assert probe.selection_mode == "sections"
        assert probe.btn_sections.isChecked()
        assert not probe.sections_list.isHidden()
        assert probe.pages_card.isHidden()
        assert probe.sections_list.item(0).checkState() == Qt.CheckState.Unchecked
        assert probe.sections_list.item(1).checkState() == Qt.CheckState.Checked
        assert ALL_CHAPTERS[0] not in probe.headings()


def test_page_control_interaction_auto_activates_pages_mode(qtbot: Any, mock_db: Any) -> None:
    """Manipuler un curseur de page depuis les modes chapitres/sections réactive le mode pages."""
    doc = _make_paginated_doc("AutoPage")
    for probe in _probes(doc, qtbot):
        probe.btn_sections.click()
        assert probe.selection_mode == "sections"

        probe.slider_p_end.setValue(2)

        assert probe.selection_mode == "pages"
        assert not probe.pages_card.isHidden()
        assert probe._selected_pages == {1, 2}
        assert [int(chunk.get("page_number") or 1) for chunk in probe.dlg._selected_chunks_for_mode()] == [1, 2]


def test_page_pill_interaction_auto_activates_pages_mode(qtbot: Any, mock_db: Any) -> None:
    """La pastille de page est un curseur de page : elle active également le mode pages."""
    doc = _make_paginated_doc("AutoPill")
    for probe in _probes(doc, qtbot):
        probe.btn_sections.click()
        probe._on_page_pill_toggled(2)  # bascule : la page 2 quitte la sélection

        assert probe.selection_mode == "pages"
        assert probe._selected_pages == {1, 3}
        assert [int(chunk.get("page_number") or 1) for chunk in probe.dlg._selected_chunks_for_mode()] == [1, 3]


# --- Critère 2 : exclusivité stricte ------------------------------------------------------


def test_mode_governs_result_without_cross_filtering(qtbot: Any, mock_db: Any) -> None:
    """Le mode actif gouverne seul le résultat : pages, chapitres et sections ne se croisent pas."""
    doc = _make_paginated_doc("Exclusivite")
    for probe in _probes(doc, qtbot):
        # 1. Mode pages restreint : les cases de sections dérivées ne reignent pas.
        probe.btn_range.click()
        probe._apply_page_selection({2}, trigger_jump=False, update_text=True)
        assert [int(chunk["page_number"]) for chunk in probe.dlg._selected_chunks_for_mode()] == [2]
        if probe.publishes_result:
            assert probe.result()["selected_pages"] == [2]

        # 2. Bascule en sections : plus aucun filtrage par pages résiduel.
        probe.btn_sections.click()
        assert probe.headings() == ALL_CHAPTERS
        result = probe.result()
        assert result["selection_mode"] == "sections"
        if probe.publishes_result:
            assert result["selected_pages"] == []
            assert result["selected_chapters"] == []

        # 3. Décocher une section agit réellement sur le résultat.
        probe.row(0).checkbox.setChecked(False)
        assert probe.headings() == ALL_CHAPTERS[1:]
        assert probe.pages_card.isHidden()


def test_page_mode_ignores_stale_section_state(qtbot: Any, mock_db: Any) -> None:
    """Après un passage en sections puis retour en pages, la plage de pages redevient gouvernante."""
    doc = _make_paginated_doc("RetourPages")
    for probe in _probes(doc, qtbot):
        probe.btn_sections.click()
        probe.row(0).checkbox.setChecked(False)
        probe.row(1).checkbox.setChecked(False)
        assert probe.headings() == ALL_CHAPTERS[2:]

        probe.btn_range.click()
        assert probe.selection_mode == "pages"
        assert [int(chunk["page_number"]) for chunk in probe.dlg._selected_chunks_for_mode()] == [1, 2, 3]


def test_chapter_mode_ignores_stale_section_state(qtbot: Any, mock_db: Any) -> None:
    """En mode chapitres, les cases de sections décochées ne rognent pas la portée choisie."""
    doc = _make_paginated_doc("RetourChapitres")
    for probe in _probes(doc, qtbot):
        probe.btn_sections.click()
        probe.row(0).checkbox.setChecked(False)
        probe.row(1).checkbox.setChecked(False)

        probe.btn_chapters.click()
        assert probe.selection_mode == "chapters"
        assert probe.headings() == ALL_CHAPTERS
        if probe.publishes_result:
            assert probe.result()["selected_chapters"] == list(range(CHAPTER_PAGES))


def test_sections_mode_ignores_stale_chapter_state(qtbot: Any, mock_db: Any) -> None:
    """En mode sections, les cartes chapitre décochées ne filtrent pas le résultat."""
    doc = _make_paginated_doc("RetourSections")
    for probe in _probes(doc, qtbot):
        probe.btn_chapters.click()
        probe._chapter_cards[0].checkbox.setChecked(False)
        probe.btn_sections.click()
        probe.row(0).checkbox.setChecked(True)

        assert probe.headings() == ALL_CHAPTERS
        if probe.publishes_result:
            assert probe.result()["selected_chapters"] == []


def test_persisted_page_holes_survive_reopening(qtbot: Any, mock_db: Any) -> None:
    """Une exclusion ``page:N`` est une délimitation de pages, pas un filtre croisé : elle survit à la réouverture."""
    doc = _make_paginated_doc("Trous")
    doc.excluded_headings = '["page:2"]'
    doc.save()

    for probe in _probes(doc, qtbot):
        assert probe._selected_pages == {1, 3}
        assert [int(chunk["page_number"]) for chunk in probe.dlg._selected_chunks_for_mode()] == [1, 3]

    # Basculer de mode ne doit pas effacer le trou persisté.
    scope = DocumentScopeDialog(doc)
    qtbot.addWidget(scope)
    scope.widget.btn_mode_sections.click()
    scope.widget.btn_mode_all.click()
    assert scope._selected_pages == {1, 3}


# --- Critère 4 : restauration à la réouverture -------------------------------------------


def test_reopening_restores_sections_mode_without_contamination(qtbot: Any, mock_db: Any) -> None:
    """Réouvrir le dialogue restaure fidèlement mode + sélection, sans rémanence croisée."""
    doc = _make_paginated_doc("Restauration")
    first = DocumentScopeDialog(doc)
    qtbot.addWidget(first)
    first.widget.btn_mode_sections.click()
    _row_for(first.widget, 0).checkbox.setChecked(False)
    _row_for(first.widget, 1).checkbox.setChecked(False)
    result = first.get_result()
    assert result["selection_mode"] == "sections"
    assert [str(c.get("heading_path") or "") for c in result["chunks"]] == ALL_CHAPTERS[2:]

    reopened = DocumentScopeDialog(doc, initial_scope_str=result["range_str"], initial_scope_result=result)
    qtbot.addWidget(reopened)
    assert reopened.selection_mode == "sections"
    assert reopened.btn_mode_sections.isChecked()
    assert reopened.pages_card.isHidden()
    assert reopened.sections_list.item(0).checkState() == Qt.CheckState.Unchecked
    assert reopened.sections_list.item(1).checkState() == Qt.CheckState.Unchecked
    assert reopened.sections_list.item(2).checkState() == Qt.CheckState.Checked
    assert [str(c.get("heading_path") or "") for c in reopened.get_result()["chunks"]] == ALL_CHAPTERS[2:]


def test_reopening_restores_chapters_mode_only(qtbot: Any, mock_db: Any) -> None:
    """Une portée chapitres restaurée ne réactive ni la plage de pages ni les cases de sections."""
    doc = _make_paginated_doc("RestaurationChapitres")
    first = DocumentScopeDialog(doc)
    qtbot.addWidget(first)
    first.widget.btn_mode_structure.click()
    first.widget._chapter_cards[-1].checkbox.setChecked(False)
    result = first.get_result()
    assert result["selection_mode"] == "chapters"
    assert result["selected_chapters"] == [0, 1]
    assert result["selected_pages"] == []

    reopened = DocumentScopeDialog(doc, initial_scope_str=result["range_str"], initial_scope_result=result)
    qtbot.addWidget(reopened)
    assert reopened.selection_mode == "chapters"
    assert reopened.btn_mode_structure.isChecked()
    assert reopened.pages_card.isHidden()
    assert [card.chapter_index for card in reopened._chapter_cards if card.is_checked()] == [0, 1]
    assert [str(c.get("heading_path") or "") for c in reopened.get_result()["chunks"]] == ALL_CHAPTERS[:2]


def test_reopening_delimitation_restores_persisted_section_exclusions(qtbot: Any, mock_db: Any) -> None:
    """Les exclusions de titres persistées survivent à la réouverture et restent gouvernantes.

    Elles ne sont honorables que par le mode sections : les rouvrir en mode pages les effacerait
    silencieusement de la délimitation du document.
    """
    doc = _make_paginated_doc("RestaurationDelimitation")
    first = DocumentDelimitationDialog(doc)
    qtbot.addWidget(first)
    first.btn_scope_mode_sections.click()
    _row_for(first, 0).checkbox.setChecked(False)
    first._on_apply()
    # Adresse canonique typée : le persisté est une règle lisible, pas un sous-chaîne.
    assert "heading:chapitre 1" in _persisted_exclusions(doc)

    reopened = DocumentDelimitationDialog(doc)
    qtbot.addWidget(reopened)
    assert reopened.selection_mode == "sections"
    assert reopened.btn_scope_mode_sections.isChecked()
    assert reopened.sections_list.item(0).checkState() == Qt.CheckState.Unchecked
    assert reopened.sections_list.item(1).checkState() == Qt.CheckState.Checked
    assert [str(chunk.get("heading_path") or "") for chunk in reopened._selected_chunks_for_mode()] == ALL_CHAPTERS[1:]

    # Réappliquer sans rien toucher ne doit pas effacer la délimitation mémorisée.
    reopened._on_apply()
    assert "heading:chapitre 1" in _persisted_exclusions(doc)


def test_reopening_delimitation_keeps_pages_mode_without_heading_exclusions(qtbot: Any, mock_db: Any) -> None:
    """Sans exclusion de titres persistée, la réouverture conserve le mode pages des bornes."""
    doc = _make_paginated_doc("RestaurationBornes")
    doc.start_page = 1
    doc.end_page = 2
    doc.excluded_headings = '["page:2"]'
    doc.save()

    reopened = DocumentDelimitationDialog(doc)
    qtbot.addWidget(reopened)
    assert reopened.selection_mode == "pages"
    assert not reopened.pages_card.isHidden()
    assert reopened._selected_pages == {1}


def _persisted_exclusions(doc: DocumentModel) -> set[str]:
    raw = DocumentModel.get_by_id(doc.id).excluded_headings or "[]"
    return {str(entry).lower() for entry in json.loads(raw)}


def _row_for(dlg: Any, index: int) -> SectionRowWidget:
    row = dlg.sections_list.itemWidget(dlg.sections_list.item(index))
    assert isinstance(row, SectionRowWidget)
    return row


def test_reincluding_a_section_actually_clears_its_persisted_exclusion(qtbot: Any, mock_db: Any) -> None:
    """Réintégrer une section efface son exclusion persistée, casse d'affichage comprise.

    L'exclusion est relue dans la casse du document, mais comparée à la casse du titre courant :
    une comparaison de chaînes brutes laissait l'entrée périmée en place, si bien que la case
    se ré-cochait sans que la région revienne au périmètre — un état que rien n'affichait et que
    seul un réexamen de la règle persistée pouvait révéler.
    """
    doc = _make_paginated_doc("Reintegration")
    first = DocumentDelimitationDialog(doc)
    qtbot.addWidget(first)
    first.btn_scope_mode_sections.click()
    _row_for(first, 0).checkbox.setChecked(False)
    first._on_apply()
    assert "heading:chapitre 1" in _persisted_exclusions(doc)

    reopened = DocumentDelimitationDialog(doc)
    qtbot.addWidget(reopened)
    assert reopened.selection_mode == "sections"
    assert reopened.sections_list.item(0).checkState() == Qt.CheckState.Unchecked

    _row_for(reopened, 0).checkbox.setChecked(True)
    reopened._on_apply()

    assert not _persisted_exclusions(doc)
    assert [str(chunk.get("heading_path") or "") for chunk in reopened._selected_chunks_for_mode()] == ALL_CHAPTERS
    assert DocumentRepository.is_section_excluded(DocumentModel.get_by_id(doc.id), ALL_CHAPTERS[0]) is False


def test_reincluding_a_legacy_unprefixed_exclusion_clears_it(qtbot):
    """Une exclusion héritée, sans préfixe, disparaît réellement quand on décoche sa section.

    Les profils d'avant les adresses typées stockent « chapitre 1 » : la réintégration doit
    reconnaître cette forme, sinon la case se décoche, la matière reste écartée, et Apply
    réinscrit l'exclusion que l'utilisateur vient d'annuler.
    """
    doc = _make_paginated_doc("ReintegrationLegacy")
    DocumentModel.update(excluded_headings=json.dumps(["chapitre 1"])).where(DocumentModel.id == doc.id).execute()

    dialog = DocumentDelimitationDialog(DocumentModel.get_by_id(doc.id))
    qtbot.addWidget(dialog)
    dialog.btn_scope_mode_sections.click()
    assert _row_for(dialog, 0).checkbox.isChecked() is False

    _row_for(dialog, 0).checkbox.setChecked(True)
    dialog._on_apply()

    assert not _persisted_exclusions(doc)
    assert DocumentRepository.is_section_excluded(DocumentModel.get_by_id(doc.id), ALL_CHAPTERS[0]) is False
    assert [str(chunk.get("heading_path") or "") for chunk in dialog._selected_chunks_for_mode()] == ALL_CHAPTERS
