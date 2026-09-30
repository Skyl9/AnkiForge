"""
Unit tests for DocumentRepository.
"""

from __future__ import annotations

import json

import pytest

from ankiforge.database.models import DocumentChunkModel, DocumentModel, NoteModel, NoteTypeModel
from ankiforge.repositories.document_repository import DocumentRepository
from ankiforge.services.markdown.structurer import MarkdownStructurer
from ankiforge.utils.region_address import RegionAddress, RegionScope

pytestmark = pytest.mark.integration


def test_document_repository_crud() -> None:
    repo = DocumentRepository()

    # Folders
    folder = repo.create_folder("Computer Science")
    assert repo.get_folder_by_id(folder.id) is not None
    assert repo.get_folder_by_name("Computer Science") is not None
    assert len(repo.get_all_folders()) == 1

    # Documents
    doc = repo.create_document(
        title="Algorithms 101",
        content="Lecture on sorting algorithms...",
        file_type="pdf",
        folder=folder,
    )
    assert doc is not None
    assert repo.get_document_by_id(doc.id) is not None
    assert repo.get_document_by_title("Algorithms 101") is not None
    assert len(repo.get_all_documents(folder_id=folder.id)) == 1

    # Chunks
    chunks_data = [
        {"chunk_index": 1, "content": "Bubble sort...", "content_hash": "h1", "page_number": 1},
        {"chunk_index": 2, "content": "Quick sort...", "content_hash": "h2", "page_number": 2},
    ]
    created_chunks = repo.create_chunks(doc, chunks_data)
    assert len(created_chunks) == 2

    # Note-Chunk Link & Coverage stats
    nt = NoteTypeModel.create(name="Basic", fields_schema="[]")
    note = NoteModel.create(note_type=nt)
    link = repo.link_note_to_chunk(note, created_chunks[0])
    assert link is not None

    stats = repo.get_coverage_stats(doc.id)
    assert stats["total_chunks"] == 2
    assert stats["covered_chunks"] == 1
    assert stats["coverage_pct"] == 50.0

    # Delete Document
    deleted = repo.delete_document(doc.id)
    assert deleted is True
    assert repo.get_document_by_id(doc.id) is None
    assert len(repo.get_chunks_for_document(doc.id)) == 0


def test_ensure_folder_hierarchy_creates_parents_and_leaf() -> None:
    repo = DocumentRepository()
    leaf = repo.ensure_folder_hierarchy("Faculté::Semestre 1::Biologie")

    assert leaf is not None
    assert leaf.name == "Faculté::Semestre 1::Biologie"

    # Vérifie que les niveaux parents ont bien été créés en base
    assert repo.get_folder_by_name("Faculté") is not None
    assert repo.get_folder_by_name("Faculté::Semestre 1") is not None
    assert repo.get_folder_by_name("Faculté::Semestre 1::Biologie") is not None

    # Idempotence : un second appel retourne le même dossier sans doublon
    leaf2 = repo.ensure_folder_hierarchy("Faculté::Semestre 1::Biologie")
    assert leaf2.id == leaf.id


def test_heal_folder_hierarchies_creates_missing_parents() -> None:
    from ankiforge.database.models import FolderModel

    repo = DocumentRepository()
    # Création directe d'un dossier sans ses parents
    FolderModel.create(name="Sciences::Physique::Thermodynamique")

    assert repo.get_folder_by_name("Sciences") is None
    assert repo.get_folder_by_name("Sciences::Physique") is None

    healed_count = repo.heal_folder_hierarchies()
    assert healed_count == 2
    assert repo.get_folder_by_name("Sciences") is not None
    assert repo.get_folder_by_name("Sciences::Physique") is not None

    # Deuxième passage idempotent
    assert repo.heal_folder_hierarchies() == 0


def test_rename_folder_cascades_to_children() -> None:
    repo = DocumentRepository()
    repo.ensure_folder_hierarchy("Fac::L1::Maths")
    repo.ensure_folder_hierarchy("Fac::L1::Physique")
    root_fac = repo.get_folder_by_name("Fac")
    assert root_fac is not None

    renamed_root = repo.rename_folder(root_fac.id, "Université")
    assert renamed_root.name == "Université"

    assert repo.get_folder_by_name("Fac") is None
    assert repo.get_folder_by_name("Fac::L1") is None
    assert repo.get_folder_by_name("Fac::L1::Maths") is None

    assert repo.get_folder_by_name("Université") is not None
    assert repo.get_folder_by_name("Université::L1") is not None
    assert repo.get_folder_by_name("Université::L1::Maths") is not None
    assert repo.get_folder_by_name("Université::L1::Physique") is not None


def _document_with_numbered_sections(title: str, sections: list[str]) -> int:
    """Crée un cours Markdown dont chaque section porte un fragment distinct."""
    repo = DocumentRepository()
    doc = repo.create_document(title=title, content="\n\n".join(f"# {name}\nContenu de {name}." for name in sections), file_type="md")
    repo.create_chunks(
        doc,
        [{"chunk_index": index, "heading_path": name, "content": f"Contenu de {name}.", "content_hash": f"h{index}"} for index, name in enumerate(sections)],
    )
    return doc.id


def _stored_exclusions(doc_id: int) -> list[str]:
    return DocumentRepository().get_excluded_headings(DocumentModel.get_by_id(doc_id))


def test_excluding_a_section_removes_it_from_the_gaps_and_the_coverage_ratio() -> None:
    """Exclure une section la sort des lacunes à combler et du dénominateur de couverture."""
    repo = DocumentRepository()
    doc_id = _document_with_numbered_sections("Cours exclusions 1", ["Préface", "Partie 1", "Corrigés"])

    before = repo.get_coverage_stats(doc_id)
    assert before["total_units"] == 3
    assert before["coverage_pct"] == 0.0
    assert before["orphan_units"] == ["Préface", "Partie 1", "Corrigés"]

    assert repo.set_section_excluded(doc_id, "Corrigés", True) is True

    after = repo.get_coverage_stats(doc_id)
    assert after["total_units"] == 2
    assert after["excluded_units"] == 1
    assert "Corrigés" not in after["orphan_units"]


def test_reincluding_a_section_puts_its_gap_back() -> None:
    """Ré-inclure une section réintègre sa lacune et rétablit le ratio de couverture."""
    repo = DocumentRepository()
    doc_id = _document_with_numbered_sections("Cours exclusions 2", ["Préface", "Partie 1"])
    repo.set_section_excluded(doc_id, "Préface", True)
    assert repo.get_coverage_stats(doc_id)["total_units"] == 1

    assert repo.set_section_excluded(doc_id, "Préface", False) is True

    restored = repo.get_coverage_stats(doc_id)
    assert restored["total_units"] == 2
    assert restored["excluded_units"] == 0
    assert "Préface" in restored["orphan_units"]


def test_excluding_a_section_preserves_the_persisted_page_holes() -> None:
    """Une exclusion de section ne doit pas effacer les trous de pages de la délimitation."""
    repo = DocumentRepository()
    doc_id = _document_with_numbered_sections("Cours exclusions 3", ["Partie 1", "Annexes"])
    doc = DocumentModel.get_by_id(doc_id)
    doc.excluded_headings = json.dumps(["page:2"], ensure_ascii=False)
    doc.save()

    repo.set_section_excluded(doc_id, "Annexes", True)
    assert _stored_exclusions(doc_id) == ["heading:Annexes", "page:2"]

    repo.set_section_excluded(doc_id, "Annexes", False)
    assert _stored_exclusions(doc_id) == ["page:2"]


def test_reincluding_a_node_lifts_the_ancestor_entry_that_still_covers_it() -> None:
    """Une entrée plus large laissée persistée ne doit pas figer le bouton sur « Ré-inclure ».

    ``heading:Annexe A`` englobe ``Annexe A > 1`` : ré-inclure ce descendant doit lever aussi
    l'entrée de son ancêtre, sans quoi l'utilisateur n'a aucun moyen de la débloquer depuis
    l'interface — l'état affiché et l'état réel divergeraient.
    """
    repo = DocumentRepository()
    doc_id = _document_with_numbered_sections("Cours exclusions 7", ["Annexe A", "Annexe A > 1", "Partie 1"])
    doc = DocumentModel.get_by_id(doc_id)
    doc.excluded_headings = json.dumps(["heading:Annexe A"], ensure_ascii=False)
    doc.save()

    assert repo.set_region_excluded(doc_id, RegionAddress(RegionScope.NODE, "Annexe A > 1"), False) is True

    assert repo.is_section_excluded(DocumentModel.get_by_id(doc_id), "Annexe A > 1") is False
    assert _stored_exclusions(doc_id) == []


def test_a_shorter_title_cannot_be_written_as_a_cover_of_a_longer_one() -> None:
    """« Annexe » ne peut pas désigner « Annexe A » : la frontière du fil d'Ariane n'est pas négociable.

    L'ancien test par sous-chaîne le permettait, ce qui rendait une exclusion capable d'emporter
    une section voisine sans que l'utilisateur l'ait demandée.
    """
    repo = DocumentRepository()
    doc_id = _document_with_numbered_sections("Cours exclusions 7b", ["Annexe A", "Partie 1"])
    doc = DocumentModel.get_by_id(doc_id)
    doc.excluded_headings = json.dumps(["heading:Annexe"], ensure_ascii=False)
    doc.save()

    assert repo.is_section_excluded(DocumentModel.get_by_id(doc_id), "Annexe A") is False


def test_excluding_a_section_stays_visible_to_the_delimitation_consumers() -> None:
    """L'exclusion doit rester effective là où le chemin de titre est nettoyé avant comparaison."""
    repo = DocumentRepository()
    raw_path = '<span id="p12">Partie **1**</span> > <a href="#x">Cas limites</a>'
    doc_id = _document_with_numbered_sections("Cours exclusions 8", [raw_path, "Annexes"])

    assert repo.set_section_excluded(doc_id, raw_path, True) is True

    doc = DocumentModel.get_by_id(doc_id)
    cleaned = MarkdownStructurer.clean_heading_title(raw_path)
    assert cleaned != raw_path
    assert repo.is_section_excluded(doc, cleaned) is True
    assert repo.is_section_excluded(doc, "Annexes") is False


def test_coverage_stats_counts_the_sections_actually_removed_from_the_scope() -> None:
    """`excluded_units` compte les sections sorties du périmètre, pas les entrées brutes.

    Quatre entrées persistées ici, dont deux ne recoupent aucun fragment et une qui en
    recouvre trois : compter les entrées donnerait 4 au lieu de 3.
    """
    repo = DocumentRepository()
    doc_id = _document_with_numbered_sections("Cours exclusions 9", ["Partie 1", "Partie 1 > A", "Partie 1 > B", "Annexes"])
    doc = DocumentModel.get_by_id(doc_id)
    doc.excluded_headings = json.dumps(["partie 1", "page:2", "entrée orpheline", "autre annexe"], ensure_ascii=False)
    doc.save()

    stats = repo.get_coverage_stats(doc_id)
    assert stats["total_units"] == 1
    assert stats["excluded_units"] == 3


def test_exclusion_matching_ignores_case_and_follows_the_heading_path() -> None:
    """Le prédicat d'exclusion est insensible à la casse et suit le fil d'Ariane complet."""
    repo = DocumentRepository()
    doc_id = _document_with_numbered_sections("Cours exclusions 4", ["Remerciements", "Partie 1"])

    repo.set_section_excluded(doc_id, "Remerciements", True)
    doc = DocumentModel.get_by_id(doc_id)
    assert repo.is_section_excluded(doc, "REMERCIEMENTS") is True
    assert repo.is_section_excluded(doc, "Partie 1") is False

    repo.set_section_excluded(doc_id, "Remerciements", False)
    assert repo.is_section_excluded(DocumentModel.get_by_id(doc_id), "Remerciements") is False
    assert repo.get_coverage_stats(doc_id)["excluded_units"] == 0


def test_an_excluded_heading_covers_its_whole_lineage() -> None:
    """Écarter un titre emporte ses descendants, mais pas un titre voisin de racine commune."""
    repo = DocumentRepository()
    doc_id = _document_with_numbered_sections("Cours exclusions 4b", ["Partie 1", "Partie 1 > A", "Partie 10"])

    repo.set_section_excluded(doc_id, "Partie 1", True)
    doc = DocumentModel.get_by_id(doc_id)
    assert repo.is_section_excluded(doc, "Partie 1 > A") is True
    # Frontière du fil d'Ariane : « Partie 1 » n'englobe pas « Partie 10 », là où une simple
    # recherche de sous-chaîne englobait les deux.
    assert repo.is_section_excluded(doc, "Partie 10") is False


def test_set_section_excluded_rejects_blank_heading_and_unknown_document() -> None:
    """Une exclusion sans titre exploitable, ou sur un document absent, ne touche à rien."""
    repo = DocumentRepository()
    doc_id = _document_with_numbered_sections("Cours exclusions 5", ["Partie 1"])

    assert repo.set_section_excluded(doc_id, "   ", True) is False
    assert repo.set_section_excluded(-1, "Partie 1", True) is False

    assert _stored_exclusions(doc_id) == []


def test_set_section_excluded_rejects_a_generic_page_label() -> None:
    """Un libellé « Page N » auto-généré ne désigne pas une section : l'écrire exclurait la page entière."""
    repo = DocumentRepository()
    doc_id = _document_with_numbered_sections("Cours exclusions 6", ["Partie 1"])

    assert repo.is_excludable_heading("Partie 1") is True
    assert repo.is_excludable_heading("Page 12") is False
    assert repo.is_excludable_heading(None) is False

    assert repo.set_section_excluded(doc_id, "Page 12", True) is False
    assert _stored_exclusions(doc_id) == []


def test_ingestion_persists_the_structural_container_flag() -> None:
    """Le drapeau calculé au découpage doit atteindre la base, sur les deux chemins d'écriture.

    Sans cela, la colonne reste à zéro pour tout document nouvellement indexé : la
    couverture compterait comme unité à couvrir un titre qui n'est qu'un nœud
    d'organisation, et l'affinement lui logerait une carte pour solde un trou fictif.
    """
    repo = DocumentRepository()
    markdown = "\n\n".join(["# Cours", "## 2 Structures", "### 2.1 La Membrane", "### 2.2 Le Noyau"])

    doc = repo.save_imported_document(title="Cours drapeaux 1", content=markdown, file_type="md")
    stored = {chunk.heading_path: chunk.is_structural_container for chunk in repo.get_chunks_for_document(doc.id)}
    assert stored["Cours > 2 Structures"] is True
    assert stored["Cours > 2 Structures > 2.1 La Membrane"] is False

    chunks_data = [
        {"chunk_index": 0, "heading_path": "Thème > Section", "content": "Six mots ici.", "content_hash": "f1", "is_structural_container": True},
        {"chunk_index": 1, "heading_path": "Thème > Section > 2.1 La Membrane", "content": "La membrane délimite la cellule.", "content_hash": "f2", "is_structural_container": False},
    ]
    created = repo.create_chunks(DocumentModel.create(title="Cours drapeaux 2", file_type="md"), chunks_data)
    assert [chunk.is_structural_container for chunk in created] == [True, False]


def test_excluding_a_section_writes_a_canonical_typed_address() -> None:
    """L'exclusion s'écrit préfixée : l'entrée nue ne survit que comme lecture de tolérance."""
    repo = DocumentRepository()
    doc_id = _document_with_numbered_sections("Cours adresses 1", ["Partie 1", "Annexes"])

    repo.set_section_excluded(doc_id, "Annexes", True)

    assert _stored_exclusions(doc_id) == ["heading:Annexes"]


def test_a_bare_stored_entry_is_still_read_as_a_heading_exclusion() -> None:
    """Rétrocompatibilité sans migration : un profil existant garde exactement son exclusion."""
    repo = DocumentRepository()
    doc_id = _document_with_numbered_sections("Cours adresses 2", ["Partie 1", "Annexes"])
    doc = DocumentModel.get_by_id(doc_id)
    doc.excluded_headings = json.dumps(["Annexes"], ensure_ascii=False)
    doc.save()

    assert repo.is_section_excluded(DocumentModel.get_by_id(doc_id), "Annexes") is True
    assert repo.get_coverage_stats(doc_id)["total_units"] == 1


def test_a_bare_number_stays_a_title_and_no_longer_excludes_a_page() -> None:
    """« 4 » est un titre, pas un trou de page : la page 4 reste dans le dénominateur."""
    repo = DocumentRepository()
    doc_id = _document_with_numbered_sections("Cours adresses 3", ["Partie 1"])
    doc = DocumentModel.get_by_id(doc_id)
    doc.excluded_headings = json.dumps(["4"], ensure_ascii=False)
    doc.save()

    assert repo.is_section_excluded(DocumentModel.get_by_id(doc_id), "4") is True
    assert repo.get_coverage_stats(doc_id)["total_units"] == 1


def test_excluding_a_page_hole_shrinks_the_page_denominator() -> None:
    """Un trou `page:N` est une adresse de page : il sort la page du dénominateur de couverture."""
    repo = DocumentRepository()
    doc = repo.create_document(title="Cours adresses 4", content="Un contenu.", file_type="pdf")
    doc.total_pages = 4
    doc.save(only=[DocumentModel.total_pages])
    repo.create_chunks(doc, [{"chunk_index": i, "heading_path": f"Page {p}", "content": "Texte.", "content_hash": f"h{p}", "page_number": p} for p in range(1, 5) for i in [p - 1]])

    before = repo.get_coverage_stats(doc.id)
    assert before["unit_type"] == "pages"
    assert before["total_units"] == 4

    repo.set_region_excluded(doc.id, RegionAddress(RegionScope.PAGE, "2"), True)

    after = repo.get_coverage_stats(doc.id)
    assert after["total_units"] == 3
    assert 2 not in after["orphan_units"]
    assert 2 in after["excluded_pages"]


def test_a_node_address_excludes_only_the_node_and_not_its_descendants() -> None:
    """`node:` est le contenu propre du titre ; la lignée reste à couvrir."""
    repo = DocumentRepository()
    doc_id = _document_with_numbered_sections("Cours adresses 5", ["Partie 1", "Partie 1 > A", "Partie 1 > B"])
    doc = DocumentModel.get_by_id(doc_id)
    doc.excluded_headings = json.dumps(["node:Partie 1"], ensure_ascii=False)
    doc.save()

    assert repo.is_region_excluded(DocumentModel.get_by_id(doc_id), heading_path="Partie 1") is True
    assert repo.is_region_excluded(DocumentModel.get_by_id(doc_id), heading_path="Partie 1 > A") is False
    assert repo.get_coverage_stats(doc_id)["total_units"] == 2


def test_a_heading_address_excludes_the_whole_lineage() -> None:
    """`heading:` est le nœud *et* sa lignée — la forme legacy d'un titre simple."""
    repo = DocumentRepository()
    doc_id = _document_with_numbered_sections("Cours adresses 6", ["Partie 1", "Partie 1 > A", "Partie 1 > A > 1.1", "Annexes"])
    doc = DocumentModel.get_by_id(doc_id)
    doc.excluded_headings = json.dumps(["heading:Partie 1"], ensure_ascii=False)
    doc.save()

    assert repo.get_coverage_stats(doc_id)["total_units"] == 1
    assert repo.get_coverage_stats(doc_id)["orphan_units"] == ["Annexes"]


def test_a_page_address_never_matches_a_heading_region() -> None:
    """Une adresse de page ne peut pas écarter une section : les portées ne se contaminent pas."""
    repo = DocumentRepository()
    doc_id = _document_with_numbered_sections("Cours adresses 7", ["Partie 1", "Partie 2"])
    doc = DocumentModel.get_by_id(doc_id)
    doc.excluded_headings = json.dumps(["page:1"], ensure_ascii=False)
    doc.save()

    assert repo.is_region_excluded(DocumentModel.get_by_id(doc_id), heading_path="Partie 1") is False
    assert repo.get_coverage_stats(doc_id)["total_units"] == 2


def test_the_page_predicate_agrees_with_the_region_predicate() -> None:
    """Une page écartée est une page hors périmètre, par le même prédicat que l'inspecteur."""
    repo = DocumentRepository()
    doc_id = _document_with_numbered_sections("Cours adresses 8", ["Partie 1"])
    doc = DocumentModel.get_by_id(doc_id)
    doc.excluded_headings = json.dumps(["page:4"], ensure_ascii=False)
    doc.save()

    assert repo.is_region_excluded(DocumentModel.get_by_id(doc_id), page_number=4) is True
    assert repo.is_region_excluded(DocumentModel.get_by_id(doc_id), page_number=5) is False


def test_reincluding_a_region_only_removes_the_addresses_that_cover_it() -> None:
    """Le retrait est le symétrique exact du test d'appartenance, pas un vidage de la colonne.

    Ré-inclure le *nœud* « Partie 1 » lève l'exclusion qui le couvre encore — la lignée, plus
    large, qui laisserait sinon le bouton « Ré-inclure » figé — mais laisse intacte l'exclusion
    d'une région voisine, et bien sûr les trous de pages.
    """
    repo = DocumentRepository()
    doc_id = _document_with_numbered_sections("Cours adresses 9", ["Partie 1", "Partie 1 > A"])
    doc = DocumentModel.get_by_id(doc_id)
    doc.excluded_headings = json.dumps(["heading:Partie 1", "heading:Partie 1 > A", "page:2"], ensure_ascii=False)
    doc.save()

    assert repo.set_region_excluded(doc_id, RegionAddress(RegionScope.NODE, "Partie 1"), False) is True

    assert _stored_exclusions(doc_id) == ["heading:Partie 1 > A", "page:2"]


def test_excluding_a_region_preserves_the_page_holes() -> None:
    """Écarter un nœud ne doit pas effacer les trous de pages : ce sont deux portées distinctes."""
    repo = DocumentRepository()
    doc_id = _document_with_numbered_sections("Cours adresses 10", ["Partie 1", "Annexes"])
    doc = DocumentModel.get_by_id(doc_id)
    doc.excluded_headings = json.dumps(["page:2"], ensure_ascii=False)
    doc.save()

    repo.set_region_excluded(doc_id, RegionAddress(RegionScope.HEADING, "Annexes"), True)

    assert _stored_exclusions(doc_id) == ["heading:Annexes", "page:2"]


def test_neutralizing_a_region_persists_a_declaration_and_leaves_the_exclusions_alone() -> None:
    """Les deux verbes ne se confondent pas : neutraliser n'écrit pas dans `excluded_headings`."""
    repo = DocumentRepository()
    doc_id = _document_with_numbered_sections("Cours adresses 11", ["Partie 1", "Partie 1 > A"])
    repo.set_section_excluded(doc_id, "Partie 1 > A", True)

    assert repo.set_region_neutralized(doc_id, RegionAddress(RegionScope.NODE, "Partie 1"), True) is True

    assert repo.get_neutralized_regions(DocumentModel.get_by_id(doc_id)) == [RegionAddress(RegionScope.NODE, "Partie 1")]
    assert _stored_exclusions(doc_id) == ["heading:Partie 1 > A"]


def test_neutralizing_is_reevaluated_on_every_ingestion(mock_db) -> None:
    """La neutralisation est une règle, pas un drapeau figé : elle survit à la réingestion.

    Une déclaration ne peut pas être mémorisée sous forme d'identifiants de fragments, réattribués
    à chaque réingestion : elle est réévaluée depuis l'adresse du document.
    """
    repo = DocumentRepository()
    markdown = "\n\n".join(["# Cours", "## 2 Structures", "### 2.1 La Membrane", "### 2.2 Le Noyau"])
    doc = repo.save_imported_document(title="Cours neutre 1", content=markdown, file_type="md")
    repo.set_region_neutralized(doc.id, RegionAddress(RegionScope.HEADING, "Cours > 2 Structures"), True)

    repo.save_imported_document(doc_id_to_update=doc.id, title=doc.title, content=markdown, file_type="md")

    reindexed = {chunk.heading_path: (chunk.is_structural_container, chunk.container_origin) for chunk in repo.get_chunks_for_document(doc.id)}
    assert reindexed["Cours > 2 Structures"][1] == "declared"
    # La déclaration englobe la lignée : le sous-titre est neutralisé avec elle.
    assert reindexed["Cours > 2 Structures > 2.1 La Membrane"] == (True, "declared")
    assert reindexed["Cours"][1] in (None, "derived")


def test_reingestion_restores_a_derived_origin_when_the_declaration_is_withdrawn(mock_db) -> None:
    """Retirer la déclaration rend au conteneur son origine dérivée : l'axe suit la règle courante."""
    repo = DocumentRepository()
    markdown = "\n\n".join(["# Cours", "## 2 Structures", "### 2.1 La Membrane"])
    doc = repo.save_imported_document(title="Cours neutre 2", content=markdown, file_type="md")
    chapter = DocumentChunkModel.document == doc.id
    repo.set_region_neutralized(doc.id, RegionAddress(RegionScope.HEADING, "Cours > 2 Structures"), True)
    repo.save_imported_document(doc_id_to_update=doc.id, title=doc.title, content=markdown, file_type="md")
    assert DocumentChunkModel.get(chapter, DocumentChunkModel.heading_path == "Cours > 2 Structures").container_origin == "declared"

    repo.set_region_neutralized(doc.id, RegionAddress(RegionScope.HEADING, "Cours > 2 Structures"), False)
    repo.save_imported_document(doc_id_to_update=doc.id, title=doc.title, content=markdown, file_type="md")

    assert DocumentChunkModel.get(chapter, DocumentChunkModel.heading_path == "Cours > 2 Structures").container_origin == "derived"


def test_declaring_a_neutralization_does_not_rewrite_the_existing_fragments(mock_db) -> None:
    """La déclaration est une règleAttachée au document : elle ne court-circuite pas la réingestion.

    Réécrire les fragments existants au moment de la déclaration donnerait un résultat correct
    jusqu'à la prochaine réingestion, où le découpage — et donc l'ensemble des identifiants de
    fragments — change. La règle doit être l'unique source de vérité.
    """
    repo = DocumentRepository()
    markdown = "\n\n".join(["# Cours", "## 2 Structures", "### 2.1 La Membrane"])
    doc = repo.save_imported_document(title="Cours neutre 3", content=markdown, file_type="md")

    repo.set_region_neutralized(doc.id, RegionAddress(RegionScope.HEADING, "Cours > 2 Structures"), True)

    chapter = DocumentChunkModel.get(DocumentChunkModel.document == doc.id, DocumentChunkModel.heading_path == "Cours > 2 Structures")
    assert chapter.container_origin == "derived"
    assert repo.is_region_neutralized(DocumentModel.get_by_id(doc.id), heading_path="Cours > 2 Structures") is True


def test_syncing_chunks_preserves_the_fragments_that_did_not_change(mock_db) -> None:
    """La resynchronisation apparie les fragments : ce qui n'a pas bougé garde son identité.

    Supprimer puis recréer tout le découpage renumérote les fragments et emporte les rattachements
    de cartes au passage. Un lot réingéré n'a pas à être un raz, et même un fragment dont le texte
    a changé mais qui occupe la même place garde son ``id`` : son rattachement est réévalué par la
    couverture plutôt que perdu, ce qui laisse au lien la chance d'être encore exact.
    """
    repo = DocumentRepository()
    doc = repo.save_imported_document(title="Cours Sync", content="# A\nAlpha.\n\n# B\nBeta.\n\n# D\nDelta.", file_type="md")
    alpha = DocumentChunkModel.get(DocumentChunkModel.document == doc.id, DocumentChunkModel.heading_path == "A")
    beta = DocumentChunkModel.get(DocumentChunkModel.document == doc.id, DocumentChunkModel.heading_path == "B")

    report = repo.sync_extracted_chunks(
        doc,
        [
            {"heading_path": "A", "content": "Alpha modifie.", "page_number": None, "is_structural_container": False, "container_origin": None},
            {"heading_path": "B", "content": "Beta.", "page_number": None, "is_structural_container": False, "container_origin": None},
            {"heading_path": "C", "content": "Gamma.", "page_number": None, "is_structural_container": False, "container_origin": None},
        ],
    )

    assert (report.preserved, report.created, report.deleted) == (2, 1, 1)
    assert DocumentChunkModel.get_by_id(alpha.id).content == "Alpha modifie."
    assert DocumentChunkModel.get_by_id(beta.id).chunk_index == 1


def test_syncing_chunks_forgets_only_what_the_ingestion_dropped(mock_db) -> None:
    """Ce que la réingestion ne produit plus disparaît ; ce qu'elle ajoute apparaît."""
    repo = DocumentRepository()
    doc = repo.save_imported_document(title="Cours Sync 2", content="# A\nAlpha.\n\n# B\nBeta.", file_type="md")

    report = repo.sync_extracted_chunks(doc, [{"heading_path": "A", "content": "Alpha.", "page_number": None}])

    assert (report.preserved, report.created, report.deleted) == (1, 0, 1)
    assert not DocumentChunkModel.select().where(DocumentChunkModel.document == doc.id, DocumentChunkModel.heading_path == "B").exists()
    assert DocumentChunkModel.get(DocumentChunkModel.document == doc.id, DocumentChunkModel.heading_path == "A").content == "Alpha."


def test_syncing_chunks_derives_the_container_origin_from_the_document_rules(mock_db) -> None:
    """L'origine écrite vient des règles du document, jamais de ce qu'un appelant avance.

    Une charge utile porte un drapeau calculé par un découpeur qui ignore tout du document ;
    s'y fier laisserait une déclaration se dégrader en dérivée au premier réalignement.
    """
    repo = DocumentRepository()
    doc = repo.save_imported_document(title="Cours Sync 3", content="# A\nAlpha.", file_type="md")

    repo.sync_extracted_chunks(
        doc,
        [{"heading_path": "A", "content": "Alpha.", "page_number": None, "is_structural_container": True, "container_origin": "declared"}],
    )

    # Rien n'a été déclaré : le seuil de production tranche, et la charge utile est ignorée.
    assert DocumentChunkModel.get(DocumentChunkModel.document == doc.id).container_origin is None


def test_syncing_chunks_reapplies_the_declared_neutralizations(mock_db) -> None:
    """La couture réaligne, elle n'a pas à se souvenir qu'une neutralisation est déclarée.

    Faire porter cette obligation à chaque appelant est la façon la plus sûre de la faire
    manquer : la délimitation elle-même, qui est le geste que la déclaration accompagne,
    réalignait sans la transmettre et effaçait l'origine déclarée au premier réalignement.
    """
    repo = DocumentRepository()
    markdown = "\n\n".join(["# Cours", "## 2 Structures", "### 2.1 La Membrane"])
    doc = repo.save_imported_document(title="Cours Declare", content=markdown, file_type="md")
    repo.set_region_neutralized(doc.id, RegionAddress(RegionScope.HEADING, "Cours > 2 Structures"), True)

    extracted = [
        {"heading_path": "Cours", "content": "Introduction", "page_number": None},
        {"heading_path": "Cours > 2 Structures", "content": "Des structures", "page_number": None},
        {"heading_path": "Cours > 2 Structures > 2.1 La Membrane", "content": "La membrane", "page_number": None},
    ]

    repo.sync_extracted_chunks(doc, extracted)

    declared = DocumentChunkModel.get(DocumentChunkModel.document == doc.id, DocumentChunkModel.heading_path == "Cours > 2 Structures")
    assert (declared.is_structural_container, declared.container_origin) == (True, "declared")


def test_syncing_chunks_drops_a_declaration_that_has_been_withdrawn(mock_db) -> None:
    """Réaligner après un retrait de déclaration rend au conteneur son origine dérivée."""
    repo = DocumentRepository()
    markdown = "\n\n".join(["# Cours", "## 2 Structures", "### 2.1 La Membrane"])
    doc = repo.save_imported_document(title="Cours Reactive", content=markdown, file_type="md")
    target = RegionAddress(RegionScope.HEADING, "Cours > 2 Structures")
    repo.set_region_neutralized(doc.id, target, True)
    extracted = [
        {"heading_path": "Cours", "content": "Introduction", "page_number": None},
        {"heading_path": "Cours > 2 Structures", "content": "Des structures", "page_number": None},
        {"heading_path": "Cours > 2 Structures > 2.1 La Membrane", "content": "La membrane", "page_number": None},
    ]

    repo.set_region_neutralized(doc.id, target, False)
    repo.sync_extracted_chunks(doc, extracted)

    reverted = DocumentChunkModel.get(DocumentChunkModel.document == doc.id, DocumentChunkModel.heading_path == "Cours > 2 Structures")
    assert reverted.container_origin == "derived"


def test_a_fully_holed_page_span_has_no_coverage_denominator(mock_db) -> None:
    """Un périmètre entièrement troué ne se notes pas 0 % : il n'a plus rien à mesurer.

    Réinjecter une page retirée dans le dénominateur affichait un score et un trou de
    couverture sur une matière que l'utilisateur avait explicitement écartée.
    """
    repo = DocumentRepository()
    doc = DocumentModel.create(title="Cours Tout Hole", content="# A\nAlpha.", file_type="pdf", total_pages=2)
    # Deux pages sans titre : la granularité se lit alors en pages, qui est la seule unité
    # qu'un trou de page puisse vider.
    DocumentChunkModel.create(document=doc, chunk_index=0, content="Alpha.", page_number=1, content_hash="h1")
    DocumentChunkModel.create(document=doc, chunk_index=1, content="Beta.", page_number=2, content_hash="h2")
    repo.set_region_excluded(doc.id, RegionAddress(RegionScope.PAGE, "1"), True)
    repo.set_region_excluded(doc.id, RegionAddress(RegionScope.PAGE, "2"), True)

    stats = DocumentRepository().get_coverage_stats(doc.id)

    assert stats["unit_type"] == "pages"
    assert stats["total_units"] == 0
    assert stats["orphan_units"] == []
    assert stats["excluded_pages"] == [1, 2]
