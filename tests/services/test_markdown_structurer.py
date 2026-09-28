"""Tests unitaires pour MarkdownStructurer."""

from typing import Any

import pytest

from ankiforge.services.markdown.structurer import MarkdownStructurer
from ankiforge.services.markdown.table_of_contents import TableOfContentsDetector
from ankiforge.services.parsing.chunking_service import ChunkingService

pytestmark = pytest.mark.unit

# Document Marker typique : un sommaire dont les entrées sont balisées comme des
# titres, suivi du corps réel des chapitres sous les MÊMES titres.


def test_slugify() -> None:
    assert MarkdownStructurer.slugify("Système Nerveux Central") == "système-nerveux-central"
    assert MarkdownStructurer.slugify("Section 1: Introduction & Principes") == "section-1-introduction-principes"
    assert MarkdownStructurer.slugify("   ***Titre Gras***   ") == "titre-gras"


def test_get_outline_simple() -> None:
    md = "# Chapitre 1 : Introduction\n\nContenu de l'intro.\n\n## 1.1 Contexte\n\nDétails sur le contexte.\n\n### 1.1.1 Historique\n\nOrigines.\n\n## 1.2 Objectifs\n\nButs recherchés."
    outline = MarkdownStructurer.get_outline(md)
    assert len(outline) == 4

    assert outline[0].level == 1
    assert outline[0].title == "Chapitre 1 : Introduction"
    assert outline[0].breadcrumb == "Chapitre 1 : Introduction"
    assert outline[0].line_number == 1

    assert outline[1].level == 2
    assert outline[1].title == "1.1 Contexte"
    assert outline[1].breadcrumb == "Chapitre 1 : Introduction > 1.1 Contexte"

    assert outline[2].level == 3
    assert outline[2].title == "1.1.1 Historique"
    assert outline[2].breadcrumb == "Chapitre 1 : Introduction > 1.1 Contexte > 1.1.1 Historique"

    assert outline[3].level == 2
    assert outline[3].title == "1.2 Objectifs"
    assert outline[3].breadcrumb == "Chapitre 1 : Introduction > 1.2 Objectifs"


def test_get_outline_tree() -> None:
    md = "# Grand Titre\n\nTexte du grand titre.\n\n## Sous-Titre A\n\nTexte sous-titre A.\n\n## Sous-Titre B\n\nTexte sous-titre B."
    tree = MarkdownStructurer.get_outline_tree(md)
    assert len(tree) == 1
    root = tree[0]
    assert root.title == "Grand Titre"
    assert len(root.children) == 2
    assert root.children[0].title == "Sous-Titre A"
    assert root.children[1].title == "Sous-Titre B"
    assert root.word_count > 0


def test_repair_heading_hierarchy() -> None:
    # Saut illégal : H1 suivi d'un H3 puis d'un H4
    md = "# Titre Principal\n\nIntroduction.\n\n### Sous-partie Orpheline (H3)\n\nDétails.\n\n#### Détail Profond (H4)\n\nExplications."
    repaired, changes = MarkdownStructurer.repair_heading_hierarchy(md)
    assert len(changes) == 2
    # H3 should become H2, H4 should become H3
    assert "## Sous-partie Orpheline (H3)" in repaired
    assert "### Détail Profond (H4)" in repaired

    # Nouveau parsing pour vérifier
    new_outline = MarkdownStructurer.get_outline(repaired)
    assert [o.level for o in new_outline] == [1, 2, 3]


def test_generate_toc_unordered() -> None:
    md = "# Manuel AnkiForge\n\n## Installation\n\n### uv sync\n\n## Utilisation"
    toc = MarkdownStructurer.generate_toc(md, max_depth=3, ordered=False)
    assert "## Table des Matières" in toc
    assert "- [Manuel AnkiForge](#manuel-ankiforge)" in toc
    assert "  - [Installation](#installation)" in toc
    assert "    - [uv sync](#uv-sync)" in toc
    assert "  - [Utilisation](#utilisation)" in toc


def test_generate_toc_ordered() -> None:
    md = "# Module 1\n\n## Leçon A\n\n## Leçon B\n\n# Module 2"
    toc = MarkdownStructurer.generate_toc(md, max_depth=2, ordered=True)
    assert "1. [Module 1](#module-1)" in toc
    assert "  1. [Leçon A](#leçon-a)" in toc
    assert "  2. [Leçon B](#leçon-b)" in toc
    assert "2. [Module 2](#module-2)" in toc


def test_extract_sections() -> None:
    md = "# Anatomie\n\nCorps humain.\n\n## Système Nerveux\n\nLe système nerveux coordonne les actions.\n\n## Système Cardiovasculaire\n\nLe cœur propulse le sang."
    sections = MarkdownStructurer.extract_sections(md)
    assert len(sections) == 3
    assert sections[0].heading_path == "Anatomie"
    assert sections[1].heading_path == "Anatomie > Système Nerveux"
    assert "système nerveux coordonne" in sections[1].content
    assert sections[2].heading_path == "Anatomie > Système Cardiovasculaire"
    assert sections[2].word_count > 0
    assert sections[2].token_estimate > 0


def test_extract_sections_fallback_no_headings() -> None:
    md = "Un paragraphe simple sans aucun titre Markdown dans le texte."
    sections = MarkdownStructurer.extract_sections(md)
    assert len(sections) == 1
    assert sections[0].heading_path == "Document"
    assert sections[0].title == "Document"
    assert sections[0].content == md


def test_clean_heading_title() -> None:
    # Tags HTML (ex: scans OCR)
    assert MarkdownStructurer.clean_heading_title('<span id="page-1-0"></span>1. Variables aléatoires') == "1. Variables aléatoires"
    # Liens Markdown
    assert MarkdownStructurer.clean_heading_title("Voir [La documentation](https://example.com)") == "Voir La documentation"
    # Gras, italique, code inline
    assert MarkdownStructurer.clean_heading_title("**Important** et *notable* avec `code`") == "Important et notable avec code"
    # Math inline KaTeX
    assert MarkdownStructurer.clean_heading_title("Formule $E = mc^2$ et espace") == "Formule E = mc^2 et espace"
    # Commentaire HTML (marqueur de page) et balises imbriquées
    assert MarkdownStructurer.clean_heading_title("<!-- PAGE: 3 --> Titre") == "Titre"
    assert MarkdownStructurer.clean_heading_title("<span>Chapitre <b>2</b></span>") == "Chapitre 2"
    # Balises de page Marker : le numéro de page ne doit pas fuiter dans le titre
    assert MarkdownStructurer.clean_heading_title('<span class="page">12</span> L\u2019évolution du droit') == "L\u2019évolution du droit"
    assert MarkdownStructurer.clean_heading_title('Titre avec <span class="page">7</span> insérée') == "Titre avec insérée"
    assert MarkdownStructurer.clean_heading_title('<span class="page">3</span>') == ""


def test_clean_heading_title_strips_page_markers_from_chunk_titles() -> None:
    """P1 — Les balises de page HTML ne doivent jamais apparaître dans les titres de chunks
    ni de parties (affichage document + sélection), sans toucher au contenu brut du chunk."""
    md_marker = "\n".join(
        [
            "{0}------------------------------------------------",
            "# 1 - Variables aléatoires",
            "",
            "Le contenu de la première page.",
            "",
            '## <span class="page">12</span> L\u2019évolution du droit',
            "",
            '### <span id="page-3-4"></span> Sous-section A',
            "",
            "Contenu de la sous-section.",
            "",
            '## <span class="page">2</span> Distribution',
            "",
            "Contenu de la seconde page.",
        ]
    )

    outline = MarkdownStructurer.get_outline(md_marker)
    titles = [o.title for o in outline]
    assert titles == ["1 - Variables aléatoires", "L\u2019évolution du droit", "Sous-section A", "Distribution"]
    for t in titles:
        assert "<" not in t and ">" not in t

    chunks = ChunkingService.extract_chunks(md_marker, file_type="pdf")
    for c in chunks:
        h_path = c.get("heading_path") or ""
        assert "<" not in h_path
        assert 'class="page"' not in h_path
        assert "page-" not in h_path

    tree = ChunkingService.extract_heading_tree_with_pages(md_marker, total_pages=12)
    flat: list[Any] = []

    def flatten(nodes: list[Any]) -> None:
        for node in nodes:
            flat.append(node)
            flatten(list(getattr(node, "children", []) or []))

    flatten(tree)
    assert flat, "l'arbre de titres ne doit pas être vide"
    for item in flat:
        assert "<" not in item.title and ">" not in item.title
        assert item.title not in ("12", "2", "7")


def test_get_outline_cleans_html_page_spans_in_titles() -> None:
    md = '# <span id="page-1-0"></span>Chapitre **1**\n\nContenu du chapitre.'
    outline = MarkdownStructurer.get_outline(md)
    assert outline[0].title == "Chapitre 1"
    assert outline[0].breadcrumb == "Chapitre 1"
    assert "span" not in outline[0].slug
    assert "page-1-0" not in outline[0].slug


def test_slugify_with_html_tags() -> None:
    raw = '<span id="page-1-0"></span>Chapitre 1 : Introduction'
    slug = MarkdownStructurer.slugify(raw)
    assert "span" not in slug
    assert "page-1-0" not in slug
    assert slug == "chapitre-1-introduction"


def test_detect_heading_hierarchy_issues_and_apply() -> None:
    md = "# Chapitre 1\n\nContenu.\n\n### Sous-partie H3 directe\n\nDétail.\n\n##### Sous-sous H5 directe\n\nFin."
    repairs = MarkdownStructurer.detect_heading_hierarchy_issues(md)
    assert len(repairs) == 2

    # Première anomalie : Ligne 5 (H3 -> H2)
    assert repairs[0].line_number == 5
    assert repairs[0].old_level == 3
    assert repairs[0].new_level == 2
    assert "H1 ➔ H3" in repairs[0].reason

    # Deuxième anomalie : Ligne 9 (H5 -> H3)
    assert repairs[1].line_number == 9
    assert repairs[1].old_level == 5
    assert repairs[1].new_level == 3

    # Application sélective : réparer uniquement la première anomalie
    repaired_partial = MarkdownStructurer.apply_heading_repairs(md, [repairs[0]])
    assert "## Sous-partie H3 directe" in repaired_partial
    assert "##### Sous-sous H5 directe" in repaired_partial

    # Application totale
    repaired_all = MarkdownStructurer.apply_heading_repairs(md, repairs)
    assert "## Sous-partie H3 directe" in repaired_all
    assert "### Sous-sous H5 directe" in repaired_all


def test_detect_heading_hierarchy_skips_code_fences() -> None:
    md = "# Titre Valide\n\n```python\n# Commentaire python avec dièse\n### Autre commentaire qui ne doit pas être un titre\n```\n\n## Sous-titre normal\n"
    repairs = MarkdownStructurer.detect_heading_hierarchy_issues(md)
    assert len(repairs) == 0


def test_detect_heading_hierarchy_does_not_force_h1() -> None:
    # Un document qui démarre avec H2 ne doit pas être forcé en H1
    md = "## Section Principale (H2)\n\nContenu.\n\n### Sous-section (H3)\n\nContenu."
    repairs = MarkdownStructurer.detect_heading_hierarchy_issues(md)
    assert len(repairs) == 0


def test_insert_or_update_toc_in_place_no_duplication() -> None:
    md = "# Manuel AnkiForge\n\nIntroduction au projet.\n\n## Installation\n\nuv sync\n\n## Configuration\n\nVariables d'environnement."
    # Première insertion
    with_toc, changed1 = MarkdownStructurer.insert_or_update_toc(md)
    assert changed1 is True
    assert "<!-- toc -->" in with_toc
    assert "<!-- /toc -->" in with_toc
    assert "## Table des Matières" in with_toc
    assert "- [Installation](#installation)" in with_toc
    assert "- [Configuration](#configuration)" in with_toc

    # Deuxième insertion (mise à jour in-place)
    updated_toc, changed2 = MarkdownStructurer.insert_or_update_toc(with_toc)
    assert changed2 is True
    # Vérifie qu'il n'y a AUCUNE duplication des balises ni du titre de sommaire
    assert with_toc.count("<!-- toc -->") == 1
    assert with_toc.count("<!-- /toc -->") == 1
    assert with_toc.count("## Table des Matières") == 1
    assert updated_toc == with_toc


def test_insert_or_update_toc_with_ocr_header() -> None:
    md = "{0}------------------------------------------------\n\n# 1 - Variables aléatoires\n\nContenu de la première page.\n\n## 1.1 Définitions\n\nUne variable aléatoire est une fonction..."
    with_toc, changed = MarkdownStructurer.insert_or_update_toc(md)
    assert changed is True
    lines = with_toc.splitlines()
    # La première ligne doit rester le marqueur OCR {0}--------
    assert lines[0].startswith("{0}-")
    # Le H1 doit venir après le marqueur OCR
    assert "# 1 - Variables aléatoires" in lines[2]
    # Le sommaire doit être inséré après le premier H1, pas tout en haut
    assert "<!-- toc -->" in with_toc
    h1_idx = with_toc.find("# 1 - Variables aléatoires")
    toc_idx = with_toc.find("<!-- toc -->")
    assert toc_idx > h1_idx


class TestTableOfContentsDisambiguation:
    """P1 — Collision entre titres du sommaire et titres réels du corps de cours."""

    def test_get_outline_drops_toc_entries_and_keeps_clean_breadcrumbs(self, marker_toc_paginated: str) -> None:
        outline = MarkdownStructurer.get_outline(marker_toc_paginated)

        titles = [o.title for o in outline]
        assert "Sommaire" not in titles
        assert titles.count("1 - Introduction aux données") == 1
        assert titles.count("2 - Statistiques descriptives") == 1
        # Le corps réel garde un fil d'Ariane propre : aucun préfixe « Sommaire ».
        assert outline[1].breadcrumb == "1 - Introduction aux données"
        assert outline[2].breadcrumb == "2 - Statistiques descriptives"
        # Le titre retenu pointe bien sur le corps de cours (page 5), pas sur le sommaire.
        assert outline[1].line_number == 16

    def test_get_outline_can_still_expose_toc_entries(self, marker_toc_paginated: str) -> None:
        outline = MarkdownStructurer.get_outline(marker_toc_paginated, skip_toc=False)

        titles = [o.title for o in outline]
        assert "Sommaire" in titles
        assert titles.count("1 - Introduction aux données") == 2

    def test_get_outline_tree_respects_skip_toc(self, marker_toc_paginated: str) -> None:
        without = MarkdownStructurer.get_outline_tree(marker_toc_paginated)
        with_toc = MarkdownStructurer.get_outline_tree(marker_toc_paginated, skip_toc=False)

        assert all(node.title != "Sommaire" for node in without)
        assert any(node.title == "Sommaire" for node in with_toc)

    def test_extract_sections_excludes_toc_block(self, marker_toc_paginated: str) -> None:
        sections = MarkdownStructurer.extract_sections(marker_toc_paginated)

        paths = [s.heading_path for s in sections]
        assert paths == ["Polycopié de Statistiques", "1 - Introduction aux données", "2 - Statistiques descriptives"]
        assert "Page de couverture du polycopié." in sections[0].content
        # Les lignes d'index du sommaire ne fusionnent jamais avec le cours.
        assert "Sommaire" not in sections[0].content
        assert "## 3 - Probabilités" not in sections[0].content
        assert "fonction de répartition" in sections[1].content

    def test_extract_sections_still_splits_consecutive_headings(self) -> None:
        md = "# Anatomie\n## Cellule\n### Noyau\n#### Membrane\nTexte de la membrane.\n"
        sections = MarkdownStructurer.extract_sections(md)
        assert len(sections) == 4

    def test_resolve_heading_line_number_skips_toc_and_returns_body(self, marker_toc_paginated: str) -> None:
        line = MarkdownStructurer.resolve_heading_line_number(marker_toc_paginated, "1 - Introduction aux données")
        assert line == 16

    def test_resolve_heading_line_number_prefers_substantive_body(self) -> None:
        md = "\n".join(
            [
                "# Titre du chapitre",
                "",
                "Résumé de la section en une phrase.",
                "",
                "# Titre du chapitre",
                "",
                "Corps de cours très developed. " * 20,
            ]
        )

        line = MarkdownStructurer.resolve_heading_line_number(md, "Titre du chapitre")

        assert line == 5

    def test_resolve_heading_line_number_uses_page_hint(self) -> None:
        md = "\n".join(
            [
                "{1}------------------------------------------------",
                "# Repechage",
                "",
                "Version de l'index page une, tres courte.",
                "",
                "{9}------------------------------------------------",
                "# Repechage",
                "",
                "Corps de cours de la page neuf, consequent et bien plus long. " * 5,
            ]
        )
        line_to_page = ChunkingService.build_line_to_page_map(md)

        line = MarkdownStructurer.resolve_heading_line_number(md, "Repechage", page_number=9, line_page_map=line_to_page)
        assert line == 7

        # Sans la page d'origine, le corps réel l'emporte de lui-même par son volume.
        fallback = MarkdownStructurer.resolve_heading_line_number(md, "Repechage", line_page_map=line_to_page)
        assert fallback == 7

    def test_resolve_heading_line_number_page_hint_beats_richer_other_page(self) -> None:
        """La page d'origine prime sur le volume : c'est elle qui identifie le bon chapitre."""
        md = "\n".join(
            [
                "{3}------------------------------------------------",
                "# Repechage",
                "",
                "Annonce page trois. " * 30,
                "",
                "{9}------------------------------------------------",
                "# Repechage",
                "",
                "Corps de la page neuf. " * 2,
            ]
        )
        line_to_page = ChunkingService.build_line_to_page_map(md)

        # Page 3 : le plus riche, mais c'est bien la page demandée.
        assert MarkdownStructurer.resolve_heading_line_number(md, "Repechage", page_number=3, line_page_map=line_to_page) == 2
        # Page 9 : le plus maigre, mais seul fragment de la page d'origine.
        assert MarkdownStructurer.resolve_heading_line_number(md, "Repechage", page_number=9, line_page_map=line_to_page) == 7
        # Sans contrainte de page : le plus riche.
        assert MarkdownStructurer.resolve_heading_line_number(md, "Repechage", line_page_map=line_to_page) == 2

    def test_resolve_heading_line_number_prefers_occurrence_after_the_toc(self) -> None:
        """Le titre de garde en page de couverture ne doit pas l'emporter sur le corps réel."""
        md = "\n".join(
            [
                "# 1 - Introduction",
                "",
                "Titre courant de la page de couverture.",
                "",
                "# Sommaire",
                "",
                "## 1 - Introduction ...... 5",
                "## 2 - Statistiques ....... 9",
                "",
                "# 1 - Introduction",
                "",
                "Corps réel de l'introduction aux données. " * 4,
            ]
        )

        assert MarkdownStructurer.resolve_heading_line_number(md, "1 - Introduction") == 10

    def test_resolve_heading_line_number_leaf_fallback_and_misses(self) -> None:
        md = "# Chapitre 1\n\nTexte.\n\n## Noyau\n\nCorps du noyau.\n"

        assert MarkdownStructurer.resolve_heading_line_number(md, "Noyau") == 5
        assert MarkdownStructurer.resolve_heading_line_number(md, "Inexistant") is None
        assert MarkdownStructurer.resolve_heading_line_number("", "Noyau") is None
        assert MarkdownStructurer.resolve_heading_line_number(md, "") is None

    def test_toc_free_document_is_untouched(self) -> None:
        md = "# Sommaire\n\nPage 1.\n\n# Chapitre 1 : La Cellule\n\nStructure cellulaire."
        outline = MarkdownStructurer.get_outline(md)
        assert [o.title for o in outline] == ["Sommaire", "Chapitre 1 : La Cellule"]
        assert TableOfContentsDetector.detect(md) is None
