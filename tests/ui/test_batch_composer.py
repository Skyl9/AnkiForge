"""Tests de la modale fusionnée de composition d'un lot (BatchSliceComposerDialog)
et de son widget embarqué AutoSliceWidget."""

from typing import Any

import pytest
from PySide6.QtCore import Qt

from ankiforge.database.models import DocumentChunkModel, DocumentModel
from ankiforge.services.batch.slicing_service import SliceUnit
from ankiforge.ui.dialogs.document_scope_dialog import DocumentScopeWidget
from ankiforge.ui.views.batch_view.dialogs.batch_slice_composer_dialog import BatchSliceComposerDialog, _RecapTaskCard
from ankiforge.ui.views.batch_view.widgets import AutoSliceWidget

pytestmark = pytest.mark.ui


LONG_PART1 = (
    "La triangulation des mesures permet de croiser plusieurs sources afin de réduire l'incertitude "
    "globale. Cette méthode, largement employée en géodésie, consiste à relever les angles et les "
    "distances observés depuis au moins trois points distincts du terrain, puis à comparer les "
    "écarts obtenus pour estimer la précision réelle des instruments."
)
LONG_PART2 = (
    "Le calcul des intervalles de confiance constitue une étape essentielle de l'analyse statistique. "
    "En pondérant chaque résultat par la variance mesurée, on obtient une plage plausible pour la "
    "valeur cible, ce qui facilite la comparaison entre les groupes expérimentaux et confirme la "
    "reproductibilité des observations sur la durée."
)


def _markdown_doc() -> DocumentModel:
    content = f"# Première partie\n\n{LONG_PART1}\n\n# Seconde partie\n\n{LONG_PART2}\n"
    doc = DocumentModel.create(title="Manuel Composer.md", content=content, file_type="md")
    DocumentChunkModel.create(document=doc, chunk_index=0, heading_path="Première partie", content=f"# Première partie\n\n{LONG_PART1}", content_hash="c0")
    DocumentChunkModel.create(document=doc, chunk_index=1, heading_path="Seconde partie", content=f"# Seconde partie\n\n{LONG_PART2}", content_hash="c1")
    return doc


def _nested_doc() -> DocumentModel:
    """Document imbriqué : un chapitre parent (H1) avec une introduction et deux sous-sections (H2)."""
    doc = DocumentModel.create(title="Chapitre Niche.md", file_type="md", content=f"# Chapitre\n\n{LONG_PART1}\n\n## Sous A\n\n{LONG_PART2}\n\n## Sous B\n\n{LONG_PART2}\n")
    DocumentChunkModel.create(document=doc, chunk_index=0, heading_path="Chapitre", content=f"# Chapitre\n\n{LONG_PART1}", content_hash="n0")
    DocumentChunkModel.create(document=doc, chunk_index=1, heading_path="Chapitre > Sous A", content=f"## Sous A\n\n{LONG_PART2}", content_hash="n1")
    DocumentChunkModel.create(document=doc, chunk_index=2, heading_path="Chapitre > Sous B", content=f"## Sous B\n\n{LONG_PART2}", content_hash="n2")
    return doc


def _paginated_doc() -> DocumentModel:
    """Document paginé : une plage utile 1-5, chaque page portant un fragment unique."""
    doc = DocumentModel.create(title="Rapport.pdf", file_type="pdf", content="", start_page=1, end_page=5, total_pages=5)
    for page in range(1, 6):
        DocumentChunkModel.create(
            document=doc,
            chunk_index=page - 1,
            page_number=page,
            heading_path="",
            content=f"Contenu page {page}",
            content_hash=f"dbg_pg{page}",
        )
    return doc


def _resolve_doc_chunks(doc: DocumentModel) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    persisted = list(DocumentChunkModel.select().where(DocumentChunkModel.document == doc).order_by(DocumentChunkModel.chunk_index.asc()))
    for chunk in persisted:
        chunks.append(
            {
                "index": chunk.chunk_index,
                "title": chunk.heading_path,
                "heading_path": chunk.heading_path,
                "content": chunk.content,
                "tokens": 30,
            }
        )
    return chunks


def _task_from_chunk(d: DocumentModel, chunk: dict[str, Any]) -> dict[str, Any]:
    return {
        "doc": d,
        "doc_title": f"{d.title} — {chunk.get('title')}",
        "doc_content": chunk.get("content", ""),
        "chunk_label": chunk.get("title") or str(chunk.get("heading_path")),
        "tokens_est": 10,
        "status": "En attente",
    }


def _task_from_slice(d: DocumentModel, s: SliceUnit) -> dict[str, Any]:
    return {
        "doc": d,
        "doc_title": f"{d.title} — {s.title}",
        "doc_content": s.content,
        "chunk_label": s.title,
        "tokens_est": s.tokens_estimate or len(s.content.split()) * 4,
        "status": "En attente",
    }


def _composer(doc: DocumentModel | None, scope_memory: dict[str, Any] | None = None) -> BatchSliceComposerDialog:
    return BatchSliceComposerDialog(
        doc=doc,
        resolve_chunks=_resolve_doc_chunks,
        scope_memory=(lambda _d: scope_memory),
        task_from_chunk=_task_from_chunk,
        task_from_slice=_task_from_slice,
    )


def test_composer_without_doc_is_inactive(qtbot: Any) -> None:
    """Sans document, aucune tâche n'est proposée, la navigation est bloquée et l'insertion est désactivée."""
    dlg = _composer(doc=None)
    qtbot.addWidget(dlg)
    dlg.show()
    assert dlg.doc is None
    assert dlg._tasks == []
    assert not dlg.hasattr_scope_widget()
    assert not hasattr(dlg, "btn_delimit")
    assert dlg.lbl_doc_hint.isVisible()
    assert not dlg.btn_next.isEnabled()

    # Bloquer la navigation : cliquer « Suivant » sans document ne change pas d'étape
    dlg._on_next()
    assert dlg._current_step == 0

    result = dlg.get_result()
    assert result["doc"] is None
    assert result["tasks"] == []


def test_composer_unblocks_after_document_selection(qtbot: Any) -> None:
    """Choisir un document via le picker masque l'alerte et débloque la navigation (étape 1)."""
    doc = _markdown_doc()
    dlg = _composer(doc=None)
    qtbot.addWidget(dlg)
    dlg.show()
    assert dlg.lbl_doc_hint.isVisible()
    assert not dlg.btn_next.isEnabled()

    dlg.doc_picker.set_document(doc)
    assert dlg.doc is not None and dlg.doc.id == doc.id
    assert not dlg.lbl_doc_hint.isVisible()
    assert dlg.btn_next.isEnabled()
    assert len(dlg._tasks) == 2


def test_composer_mode_cards_prefill_direct(qtbot: Any) -> None:
    """L'étape 1 expose deux cartes de mode (Direct par défaut) ; la carte Auto révèle la règle de découpage."""
    dlg = _composer(doc=None)
    qtbot.addWidget(dlg)
    assert dlg._mode == "direct"
    assert dlg.card_direct.property("selected") is True
    assert dlg.card_auto.property("selected") is False
    assert dlg.decoupage_stack.currentIndex() == 0

    dlg.card_auto.clicked.emit()
    assert dlg._mode == "auto"
    assert dlg.card_auto.property("selected") is True
    assert dlg.card_direct.property("selected") is False
    assert dlg.decoupage_stack.currentIndex() == 1


def test_composer_direct_seeds_tasks_and_live_update(qtbot: Any) -> None:
    """Le mode Direct préremplit les tâches dès l'ouverture et recale en direct à chaque coche (étape 2)."""
    doc = _markdown_doc()
    dlg = _composer(doc)
    qtbot.addWidget(dlg)

    # Direct : sections cochées par défaut => 1 tâche par partie
    assert dlg.hasattr_scope_widget()
    assert len(dlg._tasks) == 2
    assert {t["chunk_label"] for t in dlg._tasks} == {"Première partie", "Seconde partie"}
    assert "2 partie(s) sélectionnée(s)" in dlg.lbl_parties_count.text()

    # Live : décocher la 1re section ne garde que la seconde
    scope = dlg.scope_widget
    scope.sections_list.itemWidget(scope.sections_list.item(0)).set_checked(False)
    assert len(dlg._tasks) == 1
    assert dlg._tasks[0]["chunk_label"] == "Seconde partie"
    assert "1 partie(s) sélectionnée(s)" in dlg.lbl_parties_count.text()


def test_composer_scope_memory_prefills_but_live_selection_wins(qtbot: Any) -> None:
    """La portée mémorisée préremplit le widget ; seule la sélection live produit les tâches."""
    doc = _markdown_doc()
    memory = {
        "chunks": [
            {"index": 0, "title": "Première partie", "heading_path": "Première partie", "content": LONG_PART1, "tokens": 30},
            {"index": 1, "title": "Seconde partie", "heading_path": "Seconde partie", "content": LONG_PART2, "tokens": 30},
        ],
        "scope_title": "Portée : 2 sections",
        "scope_stats": "",
        "range_str": "",
        "selection_mode": "sections",
        "selected_headings": ["Première partie", "Seconde partie"],
        "selected_chunk_indices": [0, 1],
    }
    dlg = _composer(doc, scope_memory=memory)
    qtbot.addWidget(dlg)
    assert len(dlg._tasks) == 2

    # La sélection live restreint immédiatement les tâches (la mémoire ne réapplique plus rien)
    scope = dlg.scope_widget
    scope._set_all_checked(False)
    scope.sections_list.item(1).setCheckState(0, Qt.CheckState.Checked)
    scope.notify_changed()
    assert len(dlg._tasks) == 1
    assert dlg._tasks[0]["chunk_label"] == "Seconde partie"


def test_composer_auto_mode_slices_delimited_document(qtbot: Any) -> None:
    """Le mode Auto découpe le texte des chunks (périmètre de l'onglet document) et permet d'en cocher les tranches."""
    doc = _markdown_doc()
    dlg = _composer(doc)
    qtbot.addWidget(dlg)

    # Carte Auto : la règle s'applique aux chunks du document délimité
    dlg.card_auto.clicked.emit()
    assert dlg._mode == "auto"
    assert dlg.decoupage_stack.currentIndex() == 1
    assert dlg.auto_widget.doc_content.strip()
    assert len(dlg._tasks) == 2
    assert {"Première partie", "Seconde partie"}.intersection({t["chunk_label"] for t in dlg._tasks})

    # Étape 2 : liste à cocher des tranches, toutes cochées par défaut
    dlg._on_next()
    assert dlg.parties_stack.currentIndex() == 1
    assert dlg.lst_slices.count() == 2
    assert len(dlg._tasks) == 2
    assert "2 tranche(s) sélectionnée(s) sur 2" in dlg.lbl_parties_count.text()

    # Décocher une tranche réduit immédiatement le lot
    dlg.lst_slices.item(1).setCheckState(Qt.CheckState.Unchecked)
    assert len(dlg._tasks) == 1
    assert "1 tranche(s) sélectionnée(s) sur 2" in dlg.lbl_parties_count.text()


def test_composer_auto_mode_without_resolver_has_no_tasks(qtbot: Any) -> None:
    """Sans chunks résolus pour le document, le découpage Auto ne produit aucune tâche."""
    doc = _markdown_doc()
    dlg = BatchSliceComposerDialog(doc=doc, resolve_chunks=lambda _d: [], scope_memory=lambda _d: None, task_from_chunk=_task_from_chunk, task_from_slice=_task_from_slice)
    qtbot.addWidget(dlg)
    dlg.card_auto.clicked.emit()
    assert dlg.auto_widget.doc_content == ""
    assert dlg.lst_slices.count() == 0
    assert dlg._tasks == []


def test_composer_document_info_card_shows_stats(qtbot: Any) -> None:
    """La fiche document de l'étape 1 expose type, structure et volume (choix en connaissance de cause)."""
    dlg = _composer(doc=None)
    qtbot.addWidget(dlg)
    dlg.show()
    assert not dlg.doc_info_card.isVisible()

    dlg.doc_picker.set_document(_markdown_doc())
    assert dlg.doc_info_card.isVisible()
    assert dlg.doc_info_type.text() == "Markdown"
    chip_texts = [c.text() for c in dlg._doc_info_chips if c.isVisible()]
    assert any("2 section(s)" in t for t in chip_texts)
    assert any("mots" in t for t in chip_texts)
    assert any("tokens" in t for t in chip_texts)
    assert not dlg.doc_info_delim.isVisible()

    # Document paginé : pages + plage de délimitation active affichées
    dlg.doc_picker.set_document(_paginated_doc())
    assert dlg.doc_info_type.text() == "PDF"
    chip_texts = [c.text() for c in dlg._doc_info_chips if c.isVisible()]
    assert any("5 page(s)" in t for t in chip_texts)
    assert any("5 section(s)" in t for t in chip_texts)
    assert dlg.doc_info_delim.isVisible()
    assert "plage de pages active" in dlg.doc_info_delim.text()

    # Désélection : la fiche disparaît
    dlg.doc_picker.clear_document()
    assert not dlg.doc_info_card.isVisible()


def test_composer_auto_options_live_in_parties_step_collapsible(qtbot: Any) -> None:
    """Les options de découpage automatique sont désormais dans l'étape 2, dans un panneau pliable."""
    doc = _markdown_doc()
    dlg = _composer(doc)
    qtbot.addWidget(dlg)
    dlg.show()

    # Étape 1 : la règle n'est plus embarquée dans decoupage_stack, elle vit dans le panneau de l'étape 2
    dlg.card_auto.clicked.emit()
    assert dlg.decoupage_stack.currentIndex() == 1
    assert dlg.auto_widget.doc_content.strip()
    assert dlg.auto_widget.parent() is dlg.auto_panel.body

    # Étape 2 : le panneau « Règle de découpage » est déplié et surplombe la liste
    dlg._on_next()
    assert dlg.parties_stack.currentIndex() == 1
    assert not dlg.auto_panel.is_collapsed()
    assert dlg.auto_panel.body.isVisibleTo(dlg)
    assert dlg.lst_slices.count() == 2

    # Plier le panneau : la liste reste accessible et le compteur inchangé
    dlg.auto_panel.toggle()
    assert dlg.auto_panel.is_collapsed()
    assert not dlg.auto_panel.body.isVisibleTo(dlg)
    assert dlg.lst_slices.count() == 2
    assert len(dlg._tasks) == 2

    # Revenir puis re-entrer à l'étape 2 : le panneau se redéplie automatiquement
    dlg._on_back()
    assert dlg._current_step == 0
    dlg._on_next()
    assert not dlg.auto_panel.is_collapsed()
    assert dlg.lst_slices.count() == 2


def test_auto_slice_widget_headings_and_tokens(qtbot: Any) -> None:
    """AutoSliceWidget découpe par titres et par tokens et émet slices_changed."""
    content = f"# Chapitre A\n\n{LONG_PART1}\n\n# Chapitre B\n\n{LONG_PART2}\n"
    widget = AutoSliceWidget()
    qtbot.addWidget(widget)

    emitted: list[list[Any]] = []
    widget.slices_changed.connect(emitted.append)
    widget.set_content(content)

    assert widget.rb_headings.isChecked()
    slices = widget.get_slices()
    assert len(slices) == 2

    widget.rb_tokens.setChecked(True)
    token_slices = widget.get_slices()
    assert len(token_slices) >= 1
    assert emitted


def test_auto_slice_widget_granularity_tiers_and_custom_sync(qtbot: Any) -> None:
    """Vérifie les 4 paliers de granularité, les presets et le basculement automatique en Personnalisé."""
    from ankiforge.services.batch.slicing_service import GranularityLevel

    content = f"# Chapitre 1\n\n{LONG_PART1}\n\n## Section 1.1\n\n{LONG_PART2}\n\n### Sous-section 1.1.1\n\n{LONG_PART1}\n"
    widget = AutoSliceWidget()
    qtbot.addWidget(widget)
    widget.set_content(content)

    # 1. Par défaut : Équilibré (Standard)
    assert widget.get_granularity_level() == GranularityLevel.BALANCED
    assert widget.rb_gran_balanced.isChecked()
    assert widget.combo_depth.currentIndex() == 1  # H1 + H2
    assert widget.spin_min_words.value() == 50
    assert widget.slider_tokens.value() == 2000
    assert widget.spin_pages.value() == 5

    # 2. Bascule vers Large (Macro)
    widget.rb_gran_coarse.setChecked(True)
    assert widget.get_granularity_level() == GranularityLevel.COARSE
    assert widget.combo_depth.currentIndex() == 0  # H1 uniquement
    assert widget.spin_min_words.value() == 100
    assert widget.slider_tokens.value() == 3500
    assert widget.spin_pages.value() == 10

    # 3. Bascule vers Fin (Atomique)
    widget.rb_gran_fine.setChecked(True)
    assert widget.get_granularity_level() == GranularityLevel.FINE
    assert widget.combo_depth.currentIndex() == 2  # H1 + H2 + H3
    assert widget.spin_min_words.value() == 30
    assert widget.slider_tokens.value() == 1000
    assert widget.spin_pages.value() == 1

    # 4. Modification manuelle d'un contrôle -> bascule automatique en CUSTOM
    widget.spin_min_words.setValue(75)
    assert widget.get_granularity_level() == GranularityLevel.CUSTOM
    assert widget.rb_gran_custom.isChecked()

    # 5. Modification de profondeur -> reste en CUSTOM
    widget.combo_depth.setCurrentIndex(0)
    assert widget.get_granularity_level() == GranularityLevel.CUSTOM

    # 6. Vérification du dictionnaire get_result()
    res = widget.get_result()
    assert res["granularity"] == GranularityLevel.CUSTOM.value
    assert res["max_depth"] == 1
    assert res["min_words"] == 75
    assert len(res["slices"]) >= 1

    # 7. Carte de prévisualisation : jamais rognée
    assert widget.preview_card.minimumHeight() >= 44
    assert widget.lbl_preview_result.text()
    assert "tâche(s)" in widget.lbl_preview_result.text()


# ── Mode Direct : 1 partie cochée = 1 tâche (branches agrégées) ─────────────────────────────


def test_composer_direct_nested_branch_aggregates_into_one_task(qtbot: Any) -> None:
    """Un chapitre imbriqué entièrement coché devient UNE partie agrégée (intro + sous-sections), pas une tâche par fragment."""
    doc = _nested_doc()
    dlg = _composer(doc)
    qtbot.addWidget(dlg)

    assert len(dlg._tasks) == 1
    task = dlg._tasks[0]
    assert task["chunk_label"] == "Chapitre"
    assert LONG_PART1 in task["doc_content"]
    assert LONG_PART2 in task["doc_content"]
    assert "1 partie(s) sélectionnée(s)" in dlg.lbl_parties_count.text()

    # Le résultat embarque la portée en parties agrégées avec leurs fragments sources
    result = dlg.get_result()
    parts = result["scope_result"]["parts"]
    assert len(parts) == 1
    assert len(parts[0]["chunks"]) == 3


def test_composer_direct_partial_branch_merges_intro_into_first_active_child(qtbot: Any) -> None:
    """Sélection partielle : l'introduction du parent est fusionnée dans la 1ère sous-section active (aucun contenu perdu)."""
    doc = _nested_doc()
    dlg = _composer(doc)
    qtbot.addWidget(dlg)

    scope = dlg.scope_widget
    # Décocher "Sous B" (row 2) -> le parent devient partiellement coché
    scope.sections_list.itemWidget(scope.sections_list.item(2)).set_checked(False)
    scope.notify_changed()

    assert len(dlg._tasks) == 1
    task = dlg._tasks[0]
    assert task["chunk_label"] == "Sous A"
    assert LONG_PART1 in task["doc_content"]
    assert LONG_PART2 in task["doc_content"]
    assert "1 partie(s) sélectionnée(s)" in dlg.lbl_parties_count.text()


def test_composer_direct_parts_fallback_to_chunks_for_legacy_scope(qtbot: Any) -> None:
    """Un scope mémorisé sans clé 'parts' retombe sur les fragments (rétro-compatibilité Base)."""
    doc = _markdown_doc()
    dlg = _composer(doc)
    qtbot.addWidget(dlg)

    dlg.scope_result = {
        "chunks": [
            {"index": 0, "title": "Legacy A", "heading_path": "Legacy A", "content": "Ancien fragment A", "tokens": 20},
            {"index": 1, "title": "Legacy B", "heading_path": "Legacy B", "content": "Ancien fragment B", "tokens": 20},
        ],
        "selection_mode": "sections",
    }
    dlg._recompute_tasks()
    assert len(dlg._tasks) == 2
    assert {t["chunk_label"] for t in dlg._tasks} == {"Legacy A", "Legacy B"}
    assert "2 partie(s) sélectionnée(s)" in dlg.lbl_parties_count.text()


def test_scope_widget_parts_chapters_per_chapter(qtbot: Any) -> None:
    """Mode chapitres : chaque chapitre actif produit une seule partie agrégée."""
    doc = _nested_doc()
    widget = DocumentScopeWidget(doc)
    qtbot.addWidget(widget)

    widget._on_mode_structure_clicked()
    parts = widget._compute_parts()
    assert len(parts) == 1
    assert parts[0]["title"] == "Chapitre"
    assert len(parts[0]["chunks"]) == 3


def test_scope_widget_parts_pages_aggregate_into_one(qtbot: Any) -> None:
    """Mode pages (document non paginé) : la sélection entière est agrégée en UNE seule partie (1 partie = 1 tâche)."""
    doc = _nested_doc()
    widget = DocumentScopeWidget(doc)
    qtbot.addWidget(widget)

    widget.selection_mode = "pages"
    parts = widget._compute_parts()
    useful = widget._useful_chunks
    assert len(parts) == 1
    assert parts[0]["title"] == "Document entier"
    assert len(parts[0]["chunks"]) == len(useful) == 3
    assert LONG_PART1 in parts[0]["content"]
    assert LONG_PART2 in parts[0]["content"]


def test_scope_widget_parts_pages_range_aggregates_selected_pages(qtbot: Any) -> None:
    """Mode pages paginé : une plage de pages cochée devient UNE partie agrégée, pas une tâche par page."""
    doc = _paginated_doc()
    widget = DocumentScopeWidget(doc)
    qtbot.addWidget(widget)

    assert widget.selection_mode == "pages"
    widget._selected_pages = {2, 3, 4}
    parts = widget._compute_parts()
    assert len(parts) == 1
    assert parts[0]["title"] == "Pages 2-4"
    assert len(parts[0]["chunks"]) == 3
    assert "Contenu page 2" in parts[0]["content"]
    assert "Contenu page 4" in parts[0]["content"]
    assert "Contenu page 1" not in parts[0]["content"]


# ── Récapitulatif : données brutes & formatées par tâche ───────────────────────────────────


def test_recap_card_shows_raw_and_formatted_views(qtbot: Any) -> None:
    """Une carte du récapitulatif expose la donnée formatée (Markdown rendu) et la source brute."""
    card = _RecapTaskCard("Label", "~10 tokens", "# Titre\n\nParagraphe avec **du gras**.")
    qtbot.addWidget(card)

    assert card.preview_stack.currentIndex() == 0
    assert "Paragraphe" in card.browser_formatted.toHtml()
    assert "du gras" in card.browser_formatted.toHtml()

    card.btn_source.click()
    assert card.preview_stack.currentIndex() == 1
    assert "**du gras**" in card.browser_source.toPlainText()


def test_composer_recap_builds_one_card_per_task_with_checked_content(qtbot: Any) -> None:
    """Le récapitulatif affiche une carte par tâche avec le contenu réellement expédié (brut + formaté)."""
    doc = _markdown_doc()
    dlg = _composer(doc)
    qtbot.addWidget(dlg)

    assert len(dlg._tasks) == 2
    cards = [dlg.tasks_layout.itemAt(i).widget() for i in range(dlg.tasks_layout.count())]
    cards = [c for c in cards if isinstance(c, _RecapTaskCard)]
    assert len(cards) == 2

    assert LONG_PART1 in cards[0].browser_source.toPlainText()
    assert LONG_PART2 in cards[1].browser_source.toPlainText()
    assert all(LONG_PART2 in card.browser_formatted.toHtml() or LONG_PART1 in card.browser_formatted.toHtml() for card in cards)


def test_composer_step_chips_navigation_with_and_without_doc(qtbot: Any) -> None:
    """Les puces d'étapes en haut permettent la navigation directe ; l'accès est bloqué sans document."""
    # 1. Sans document : cliquer sur l'étape 1 ou 2 reste à l'étape 0
    dlg = _composer(doc=None)
    qtbot.addWidget(dlg)
    dlg.show()

    assert dlg._current_step == 0
    dlg._chips[1].click()
    assert dlg._current_step == 0
    dlg._chips[2].click()
    assert dlg._current_step == 0

    # 2. Avec document : navigation directe vers n'importe quelle étape
    doc = _markdown_doc()
    dlg.doc_picker.set_document(doc)
    assert dlg.doc is not None

    # Clic sur étape 1 (Choix des parties)
    dlg._chips[1].click()
    assert dlg._current_step == 1
    assert dlg.body_stack.currentIndex() == 1

    # Clic sur étape 2 (Récapitulatif)
    dlg._chips[2].click()
    assert dlg._current_step == 2
    assert dlg.body_stack.currentIndex() == 2

    # Clic retour sur étape 0 (Document & découpage)
    dlg._chips[0].click()
    assert dlg._current_step == 0
    assert dlg.body_stack.currentIndex() == 0
