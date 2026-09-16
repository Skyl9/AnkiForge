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


def test_chunking_zero_based_page_markers_are_normalized():
    """Les transcriptions PDF 0-based sont exposées avec des pages 1-based."""
    content = """{0}------------------------------------------------
Première page transcrite avec suffisamment de contenu.

{1}------------------------------------------------
Deuxième page transcrite avec suffisamment de contenu.
"""

    chunks = ChunkingService.extract_chunks(content, file_type="pdf")

    assert [chunk["page_number"] for chunk in chunks] == [1, 2]


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


def test_preferred_strategy_selects_markdown_ast_for_continuous_types():
    """Les documents continus (Markdown, Web, texte, notebooks, code) privilégient la stratégie AST la plus fine."""
    for ft in ("md", "markdown", "txt", "text", "web", "youtube", "yt", "ipynb", "py"):
        assert ChunkingService.preferred_strategy(ft) == ChunkingService.STRATEGY_MARKDOWN_AST

    # Les documents paginés et audio conservent leur découpage natif
    for ft in ("pdf", "pptx", "epub", "audio", "mp3", "wav"):
        assert ChunkingService.preferred_strategy(ft) is None

    assert ChunkingService.preferred_strategy(None) is None
    assert ChunkingService.preferred_strategy("") is None


def test_chunking_markdown_ast_fine_granularity_h5_h6():
    """Vérifie une granularité fine jusqu'aux titres H5/H6 via la stratégie markdown_ast."""
    content = """# Anatomie
## Cellule
### Noyau
#### Membrane nucléaire
##### Pores nucléaires
Texte des pores nucléaires.
###### Lamina nucléaire
Texte de la lamina.
"""
    chunks = ChunkingService.extract_chunks(content, file_type="md", strategy=ChunkingService.preferred_strategy("md"))

    heading_paths = [c["heading_path"] for c in chunks]
    assert len(chunks) == 6
    assert "Anatomie" in heading_paths[0]
    assert "Anatomie > Cellule" in heading_paths[1]
    assert "Anatomie > Cellule > Noyau" in heading_paths[2]
    assert "Anatomie > Cellule > Noyau > Membrane nucléaire" in heading_paths[3]
    assert "Anatomie > Cellule > Noyau > Membrane nucléaire > Pores nucléaires" in heading_paths[4]
    assert "Anatomie > Cellule > Noyau > Membrane nucléaire > Pores nucléaires > Lamina nucléaire" in heading_paths[5]

    # Chaque fragment porte un fil d'Ariane complet descendant jusqu'au titre feuille
    assert all(" > " in p for p in heading_paths[1:])


def test_chunking_code_fence_headings_not_split():
    """Les titres Markdown présents À L'INTÉRIEUR d'un bloc de code ne découpent pas de sections."""
    content = """# MonModule

Module docstring.

```python
# Ceci est un commentaire avec #
## Ceci ressemble à un titre
def f():
    # Et encore un heading
    return 42
```

## Autre section
Contenu de l'autre section.
"""
    chunks = ChunkingService.extract_chunks(content, file_type="py", strategy=ChunkingService.preferred_strategy("py"))

    paths = [c["heading_path"] for c in chunks]
    assert len(chunks) == 2
    assert paths[0] == "MonModule"
    assert paths[1].endswith("Autre section")


def test_extract_by_section_flushes_h5_h6_leaf_headings():
    """Le découpage par section (fallback non-AST) crée aussi des fragments pour H5/H6."""
    content = """# Chapitre 1
## Résumé
Texte du résumé.
##### Détail fin
Texte du détail fin.
###### Sous-détail
Texte du sous-détail.
"""
    chunks = ChunkingService.extract_chunks(content)

    paths = [c["heading_path"] for c in chunks]
    assert any(p.endswith("Détail fin") for p in paths)
    assert any(p.endswith("Sous-détail") for p in paths)
    assert len(chunks) >= 3


def test_pdf_marker_detected_as_rich_markdown_uses_ast_with_pages():
    """Un PDF traité par Marker (markdown riche + marqueurs {N}---) est découpé par sections AST."""
    content = """{0}------------------------------------------------
# Variables aléatoires réelles

Une variable aléatoire est une application.

## Quelques lois continues usuelles

### <span id="page-1-0"></span>**Fonction de répartition**

La fonction de répartition est croissante.

{1}------------------------------------------------
## Loi exponentielle

### <span id="page-2-0"></span>**Espérance**

L'espérance est linéaire.

#### **Théorème de transfert**

Formule de transfert.
"""
    chunks = ChunkingService.extract_chunks(content, file_type="pdf")

    # Découpage fin par section AST (pas un chunk par page)
    assert len(chunks) >= 5
    paths = [c["heading_path"] for c in chunks]
    assert any(p == "Variables aléatoires réelles" for p in paths)
    assert any(p.endswith("Fonction de répartition") for p in paths)
    assert any(p.endswith("Théorème de transfert") for p in paths)

    # Pas de pollution par les spans HTML / gras Marker dans les chemins
    assert all("<span" not in p for p in paths)
    assert all("**" not in p for p in paths)

    # Les pages sont conservées sur les sections
    pages = [c["page_number"] for c in chunks]
    assert pages[0] == 1
    assert any(p == 2 for p in pages)


def test_pdf_plain_text_no_marker_stays_page_based():
    """Un PDF natif PyPDF (## Page N, [SPLIT], sans marqueurs {N}---) reste découpé par page."""
    content = """<!-- PAGE: 1 -->
## Page 1

Texte brut de la première page sans structure Markdown.
Toujours du texte.

<!-- PAGE: 2 -->
## Page 2

Contenu de la deuxième page sans titres riches.
Suite du texte brut.
"""
    chunks = ChunkingService.extract_chunks(content, file_type="pdf")
    assert len(chunks) == 2
    assert chunks[0]["page_number"] == 1
    assert chunks[1]["page_number"] == 2


def test_pdf_marker_without_headings_stays_page_based():
    """Un PDF Marker sans vrais titres (seulement des paragraphes) reste découpé par page."""
    content = """{0}------------------------------------------------
Première page avec uniquement du texte au kilomètre sans aucun titre.
Le contenu est assez long pour être retenu comme fragment.

{1}------------------------------------------------
Deuxième page, toujours sans titres, uniquement du texte descriptif.
Le contenu de la page dépasse le seuil minimal de longueur.
"""
    chunks = ChunkingService.extract_chunks(content, file_type="pdf")
    assert [c["page_number"] for c in chunks] == [1, 2]


def test_pdf_marker_ast_preserves_page_number_map():
    """La page attribuée à chaque section AST correspond au marqueur {N}--- où elle débute."""
    content = """{0}------------------------------------------------
# Chapitre 1

Corps du chapitre 1 sur la première page.

{1}------------------------------------------------
## Chapitre 2

Corps du chapitre 2 qui commence à la page deux.
Contenu suffisamment long pour la section.
"""
    chunks = ChunkingService.extract_chunks(content, file_type="pdf")
    chapter1 = next(c for c in chunks if c["heading_path"].endswith("Chapitre 1"))
    chapter2 = next(c for c in chunks if c["heading_path"].endswith("Chapitre 2"))
    assert chapter1["page_number"] == 1
    assert chapter2["page_number"] == 2
