from ankiforge.services.parsing.chunking_service import ChunkingService


def test_chunking_pdf_paginated_by_page():
    """Vérifie le découpage page par page pour un PDF paginé par Marker ou balises."""
    raw_pdf_markdown = """{1}------------------------------------------------
# Estimation statistique

L'estimation ponctuelle consiste à évaluer un paramètre inconnu theta à partir d'un échantillon.

{2}------------------------------------------------
## Propriétés des estimateurs

Un estimateur est dit sans biais si son espérance est égale à la vraie valeur du paramètre.
"""

    chunks = ChunkingService.extract_chunks(raw_pdf_markdown, file_type="pdf")

    assert len(chunks) == 2

    # Page 1
    assert chunks[0]["page_number"] == 1
    assert "Estimation statistique" in chunks[0]["heading_path"]
    assert "estimation ponctuelle" in chunks[0]["content"]
    assert "# Estimation statistique" in chunks[0]["content"]

    # Page 2
    assert chunks[1]["page_number"] == 2
    assert "Propriétés des estimateurs" in chunks[1]["heading_path"]
    assert "sans biais" in chunks[1]["content"]


def test_chunking_html_page_markers():
    """Vérifie le découpage avec des balises HTML <!-- PAGE: X -->."""
    content = """<!-- PAGE: 1 -->
# Chapitre 1
Introduction générale au sujet et définitions.

<!-- PAGE: 2 -->
# Chapitre 2
Approfondissement des théorèmes fondamentaux.
"""
    chunks = ChunkingService.extract_chunks(content)

    assert len(chunks) == 2
    assert chunks[0]["page_number"] == 1
    assert chunks[0]["heading_path"] == "Chapitre 1"
    assert "Introduction générale" in chunks[0]["content"]

    assert chunks[1]["page_number"] == 2
    assert chunks[1]["heading_path"] == "Chapitre 2"
    assert "théorèmes fondamentaux" in chunks[1]["content"]


def test_chunking_markdown_semantic_sections_no_isolated_headings():
    """Vérifie qu'aucun titre isolé seul (ex: '# Titre') ne devient un chunk orphelin."""
    content = """# Estimation statistique

Dans ce cours, nous allons étudier les lois de probabilités.

# Propriétés de convergence

La loi des grands nombres assure la convergence en probabilité.
"""
    chunks = ChunkingService.extract_chunks(content, file_type="md")

    assert len(chunks) == 2

    # Chunk 0
    assert chunks[0]["heading_path"] == "Estimation statistique"
    assert "# Estimation statistique" in chunks[0]["content"]
    assert "lois de probabilités" in chunks[0]["content"]
    # Vérifier que le chunk n'est pas uniquement le titre
    assert len(chunks[0]["content"].splitlines()) > 1

    # Chunk 1
    assert chunks[1]["heading_path"] == "Propriétés de convergence"
    assert "grands nombres" in chunks[1]["content"]


def test_chunking_nested_consecutive_headings():
    """Vérifie le traitement des titres consécutifs sans texte entre eux."""
    content = """# Partie 1 : Algèbre
## Chapitre 1 : Espaces Vectoriels

Un espace vectoriel est un ensemble muni de deux lois de composition.
"""
    chunks = ChunkingService.extract_chunks(content, file_type="md")

    assert len(chunks) == 1
    assert "Partie 1 : Algèbre > Chapitre 1 : Espaces Vectoriels" in chunks[0]["heading_path"]
    assert "espace vectoriel" in chunks[0]["content"]


def test_chunking_empty_or_too_short():
    """Vérifie la robustesse avec du contenu vide ou insignifiant."""
    assert ChunkingService.extract_chunks("") == []
    assert ChunkingService.extract_chunks("   \n\n  ") == []
