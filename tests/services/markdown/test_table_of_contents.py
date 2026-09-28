"""Tests unitaires du détecteur de Table des Matières (collision sommaire / titres réels)."""

import pytest

from ankiforge.services.markdown.table_of_contents import TableOfContentsDetector

pytestmark = pytest.mark.unit


class TestDetection:
    def test_detects_marker_toc_block_with_duplicate_headings(self, marker_toc_paginated: str) -> None:
        span = TableOfContentsDetector.detect(marker_toc_paginated)

        assert span is not None
        assert span.title == "Sommaire"
        assert span.anchor_line == 7
        assert span.start_line == 7
        assert span.entry_titles == (
            "1 - Introduction aux données",
            "2 - Statistiques descriptives",
            "3 - Probabilités",
        )
        # Le bloc s'arrête avant le vrai chapitre 1 (page 5), pas après.
        assert span.end_line == 13
        assert span.contains_line(9)
        assert not span.contains_line(16)

    def test_detects_toc_with_dot_leaders_and_page_numbers(self, marker_toc_paginated: str) -> None:
        md = "\n".join(
            [
                "# Manuel de chimie",
                "",
                "## Sommaire",
                "",
                "1 - Atomes ...................... 3",
                "2 - Liaisons chimiques .......... 12",
                "3 - Réactions .................... 40",
                "",
                "{3}------------------------------------------------",
                "# 1 - Atomes",
                "",
                "Un atome est constitué d'un noyau et d'un nuage électronique. Les électrons occupent des orbitales de différentes énergies selon le principe d'exclusion.",
            ]
        )

        span = TableOfContentsDetector.detect(md)

        assert span is not None
        assert span.title == "Sommaire"
        assert span.entry_titles == ("1 - Atomes", "2 - Liaisons chimiques", "3 - Réactions")

    def test_detects_generated_toc_block_with_anchor_links(self, marker_toc_paginated: str) -> None:
        md = "\n".join(
            [
                "<!-- toc -->",
                "## Table des Matières",
                "",
                "- [Manuel AnkiForge](#manuel-ankiforge)",
                "  - [Installation](#installation)",
                "  - [Utilisation](#utilisation)",
                "<!-- /toc -->",
                "",
                "# Manuel AnkiForge",
                "",
                "## Installation",
                "",
                "Installez les dépendances avec uv sync puis lancez l'application en mode développement.",
            ]
        )

        span = TableOfContentsDetector.detect(md)

        assert span is not None
        assert span.title == "Table des Matières"
        assert span.entry_titles == ("Manuel AnkiForge", "Installation", "Utilisation")

    def test_detects_headless_anchor_block_at_document_start(self, marker_toc_paginated: str) -> None:
        md = "\n".join(
            [
                "{0}------------------------------------------------",
                "- [Variables aléatoires](#variables-aléatoires) .... 15",
                "- [Statistiques descriptives](#statistiques-descriptives) .... 20",
                "- [Probabilités](#probabilités) .... 33",
                "",
                "# Variables aléatoires",
                "",
                "Une variable aléatoire est une fonction qui associe chaque issue d'une expérience aléatoire à une valeur numérique, définie par une loi de probabilité.",
            ]
        )

        span = TableOfContentsDetector.detect(md)

        assert span is not None
        assert span.title == ""
        assert span.anchor_line is None
        assert len(span.entry_titles) == 3

    def test_ignores_toc_title_without_index_entries(self, marker_toc_paginated: str) -> None:
        """Un titre « Sommaire » suivi d'un vrai contenu n'est pas un bloc d'index."""
        md = "# Sommaire\n\nPage 1.\n\n# Chapitre 1 : La Cellule\n\nStructure cellulaire."

        assert TableOfContentsDetector.detect(md) is None

    def test_ignores_sommaire_anchor_inside_document_body(self, marker_toc_paginated: str) -> None:
        """Un titre ancre hors zone d'ouverture n'est jamais un sommaire."""
        lines = ["# Introduction", "", "Texte d'introduction.", ""]
        for i in range(1, 40):
            lines += [f"## Section {i}", "", f"Contenu de la section {i} avec suffisamment de mots.", ""]
        lines += ["# Sommaire", "", "## Récapitulatif", "", "Synthèse du chapitre en quelques lignes."]
        md = "\n".join(lines)

        assert TableOfContentsDetector.detect(md) is None

    def test_detects_toc_with_ocr_page_span_in_anchor_title(self, marker_toc_paginated: str) -> None:
        md = "\n".join(
            [
                '# <span id="page-1-3"></span>Sommaire',
                "",
                "## Alpha .......... 12",
                "## Beta ........... 18",
                "",
                "# Alpha",
                "",
                "Contenu suffisamment riche pour ne pas être une entrée d'index de sommaire.",
            ]
        )

        span = TableOfContentsDetector.detect(md)

        assert span is not None
        assert span.title == "Sommaire"
        assert span.entry_titles == ("Alpha", "Beta")

    def test_detect_is_none_on_empty_documents(self, marker_toc_paginated: str) -> None:
        assert TableOfContentsDetector.detect("") is None
        assert TableOfContentsDetector.detect("   \n\n  ") is None

    def test_single_toc_entry_is_not_enough(self, marker_toc_paginated: str) -> None:
        md = "# Sommaire\n\n## Unique ....... 4\n\n# Unique\n\nUn corps de texte suffisamment long."

        assert TableOfContentsDetector.detect(md) is None

    def test_toc_followed_by_heading_without_body_is_still_absorbed(self, marker_toc_paginated: str) -> None:
        md = "\n".join(
            [
                "# Sommaire",
                "",
                "## Alpha ....... 12",
                "## Beta ........ 18",
                "",
                "# Gamma",
                "## Delta",
                "",
                "Contenu de delta.",
            ]
        )

        span = TableOfContentsDetector.detect(md)

        assert span is not None
        # « Gamma » n'a pas de corps propre : il appartient encore au sommaire.
        # « Delta » possède un corps : le bloc s'arrête avant lui.
        assert span.entry_titles == ("Alpha", "Beta", "Gamma")
        assert span.end_line == 6


class TestIsTocTitle:
    @pytest.mark.parametrize(
        "title",
        [
            "Sommaire",
            "sommaire",
            "SOMMAIRE",
            "Table des matières",
            "Table des matieres",
            "Table of Contents",
            "Table of content",
            "Contents",
            "Inhaltsverzeichnis",
            "Índice",
            "Sommaire général",
            "Plan du cours",
            "TOC",
            "Index",
        ],
    )
    def test_recognized_titles(self, title: str) -> None:
        assert TableOfContentsDetector.is_toc_title(title) is True

    @pytest.mark.parametrize(
        "title",
        [
            "Introduction",
            "Plan marketing",
            "Index des termes",
            "Le sommaire du cours",
            "Systèmes de fichiers",
            "Table de matière première",
        ],
    )
    def test_rejected_titles(self, title: str) -> None:
        assert TableOfContentsDetector.is_toc_title(title) is False


class TestIndexEntryLines:
    @pytest.mark.parametrize(
        "line",
        [
            "## 1 - Introduction",
            "1 - Atomes ...................... 3",
            "- [Installation](#installation)",
            "  - [Utilisation](#utilisation)",
            "1. Atomes .......... 3",
            "* Beta ....... 18",
        ],
    )
    def test_index_lines(self, line: str) -> None:
        assert TableOfContentsDetector.is_index_entry_line(line) is True

    @pytest.mark.parametrize(
        "line",
        [
            "",
            "   ",
            "La moyenne arithmétique est la somme des valeurs observées.",
            "- un point de liste normal",
            "{3}------------------------------------------------",
            "<!-- PAGE: 3 -->",
            "![schéma](image.png)",
        ],
    )
    def test_non_index_lines(self, line: str) -> None:
        assert TableOfContentsDetector.is_index_entry_line(line) is False


class TestRealChapterIsNotAToc:
    """Un chapitre réellement intitulé « Sommaire » (sous-titres sans prose) reste du cours."""

    REALTIME_SOMMAIRE = "\n".join(
        [
            "# Sommaire",
            "",
            "## Module A",
            "",
            "## Module B",
            "",
            "## Module C",
            "",
            "# Cours",
            "",
            "Texte du cours.",
        ]
    )

    def test_detect_ignores_sommaire_without_index_markers(self, marker_toc_paginated: str) -> None:
        assert TableOfContentsDetector.detect(self.REALTIME_SOMMAIRE) is None

    def test_outline_keeps_every_module(self, marker_toc_paginated: str) -> None:
        from ankiforge.services.markdown.structurer import MarkdownStructurer

        titles = [item.title for item in MarkdownStructurer.get_outline(self.REALTIME_SOMMAIRE)]

        assert titles == ["Sommaire", "Module A", "Module B", "Module C", "Cours"]

    def test_sections_keeps_every_module(self, marker_toc_paginated: str) -> None:
        from ankiforge.services.markdown.structurer import MarkdownStructurer

        sections = MarkdownStructurer.extract_sections(self.REALTIME_SOMMAIRE)

        assert [s.title for s in sections] == ["Sommaire", "Module A", "Module B", "Module C", "Cours"]

    def test_numbered_modules_are_not_taken_for_page_numbers(self, marker_toc_paginated: str) -> None:
        """« ## Module 2 » se termine par un nombre, mais ce n'est pas un numéro de page."""
        md = "\n".join(["# Sommaire", "", "## Module 1", "", "## Module 2", "", "## Module 3", "", "# Cours", "", "Texte."])

        assert TableOfContentsDetector.detect(md) is None


class TestLooksLikeIndexBlock:
    def test_rejects_section_whose_lines_end_with_a_number(self, marker_toc_paginated: str) -> None:
        """Un fragment de cours dont les lignes se terminent par un nombre n'est pas un index."""
        fragment = "# Titre H1\n    Texte 1\n    \n    ## Titre H2\n    Texte 2"

        assert TableOfContentsDetector.looks_like_index_block(fragment) is False

    def test_detects_toc_fragment_with_explicit_markers(self, marker_toc_paginated: str) -> None:
        fragment = "## Table des matières\n\n## 1 - Introduction .... 2\n\n## 2 - Statistiques .... 5"

        assert TableOfContentsDetector.looks_like_index_block(fragment) is True

    @pytest.mark.parametrize(
        "title",
        ["Sommaire", "Index", "Plan du cours", "Table des matières"],
    )
    def test_rejects_chapter_titled_like_a_toc_without_markers(self, title: str) -> None:
        """« Sommaire » + sous-titres sans prose : un vrai chapitre, pas une preuve d'index."""
        fragment = f"# {title}\n\n## Module A\n\n## Module B"

        assert TableOfContentsDetector.looks_like_index_block(fragment) is False

    def test_rejects_heading_only_section_without_index_signal(self, marker_toc_paginated: str) -> None:
        """Une section de cours faite de sous-titres sans prose n'est pas un sommaire."""
        fragment = "## Introduction\n\n## Déroulement\n\n## Bilan"

        assert TableOfContentsDetector.looks_like_index_block(fragment) is False

    def test_detects_leader_fragment(self, marker_toc_paginated: str) -> None:
        fragment = "1 - Atomes ..... 3\n2 - Liaisons .... 12"

        assert TableOfContentsDetector.looks_like_index_block(fragment) is True

    def test_rejects_substantive_section(self, marker_toc_paginated: str) -> None:
        section = "## 1 - Introduction\n\n" + ("Un texte de cours suffisamment riche. " * 12)

        assert TableOfContentsDetector.looks_like_index_block(section) is False

    def test_rejects_short_prose(self, marker_toc_paginated: str) -> None:
        assert TableOfContentsDetector.looks_like_index_block("Une phrase unique.") is False
        assert TableOfContentsDetector.looks_like_index_block("") is False
        assert TableOfContentsDetector.looks_like_index_block("   ") is False
