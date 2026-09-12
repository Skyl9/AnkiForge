"""Tests unitaires pour MarkdownStructurer."""

from ankiforge.services.markdown.structurer import MarkdownStructurer


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
