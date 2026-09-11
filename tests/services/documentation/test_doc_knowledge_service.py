"""Tests unitaires pour le service de base de connaissances AppDocumentationService."""

from pathlib import Path

import pytest

from ankiforge.services.documentation.doc_service import (
    AppDocumentationService,
    _clean_header_text,
    _slugify,
    get_feature_quick_help,
    list_app_doc_topics,
    read_app_doc_page,
    search_app_documentation,
)


@pytest.fixture
def temp_docs_env(tmp_path: Path) -> tuple[Path, Path]:
    """Crée un environnement temporaire avec zensical.toml et des documents Markdown."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    feat_dir = docs_dir / "features"
    feat_dir.mkdir()

    # Création de zensical.toml
    config_file = tmp_path / "zensical.toml"
    config_content = """
    [project]
    site_name = "Test AnkiForge"
    nav = [
        { "Accueil" = "index.md" },
        { "Fonctionnalités" = [
            { "Moteur MCP" = "features/mcp.md" },
            { "KaTeX Live" = "features/katex.md" },
        ]},
    ]
    """
    config_file.write_text(config_content, encoding="utf-8")

    # index.md
    index_md = docs_dir / "index.md"
    index_md.write_text(
        "# Bienvenue sur AnkiForge\n\nVoici la page d'accueil avec des détails d'installation.",
        encoding="utf-8",
    )

    # features/mcp.md
    mcp_md = feat_dir / "mcp.md"
    mcp_content = """# Serveur MCP In-Process 🤝

Introduction au serveur MCP d'AnkiForge.

## 🛠️ 1. Architecture ReAct

Le consultant IA fonctionne avec la boucle ReAct (Thought, Action, Observation).

## ⚡ 2. Outils de Diagnostic

Des outils sécurisés permettent d'auditer les paquets et d'analyser les cartes.
"""
    mcp_md.write_text(mcp_content, encoding="utf-8")

    # features/katex.md
    katex_md = feat_dir / "katex.md"
    katex_content = """# Éditeur KaTeX 📐

Éditeur de formules mathématiques en direct.
"""
    katex_md.write_text(katex_content, encoding="utf-8")

    return docs_dir, config_file


def test_slugify_and_clean_header():
    assert _slugify("⚡ 1. Pourquoi Nuitka ?") == "1-pourquoi-nuitka"
    assert _slugify("Serveur MCP & In-Process") == "serveur-mcp-in-process"
    assert _clean_header_text("## ⚡ 1. Pourquoi Nuitka ?") == "⚡ 1. Pourquoi Nuitka ?"
    assert _clean_header_text("# Titre Principal") == "Titre Principal"


def test_app_doc_service_indexing_and_search(temp_docs_env: tuple[Path, Path]):
    docs_dir, config_file = temp_docs_env
    service = AppDocumentationService(docs_dir=docs_dir, config_path=config_file)
    service.ensure_indexed()

    topics = service.get_topics()
    assert len(topics) >= 3

    # Recherche mot clé présent
    results = service.search("ReAct")
    assert len(results) >= 1
    best = results[0]
    assert "mcp.md" in best.page_path
    assert "ReAct" in best.section_title or "ReAct" in best.snippet

    # Recherche filtrée par catégorie
    res_cat = service.search("KaTeX", category="Fonctionnalités")
    assert len(res_cat) >= 1
    assert "katex.md" in res_cat[0].page_path

    # Recherche inexistante
    res_none = service.search("terme_completement_inconnu_xyz123")
    assert len(res_none) == 0


def test_get_page_content(temp_docs_env: tuple[Path, Path]):
    docs_dir, config_file = temp_docs_env
    service = AppDocumentationService(docs_dir=docs_dir, config_path=config_file)

    # Page entière
    full = service.get_page_content("features/mcp.md")
    assert full is not None
    assert "Serveur MCP In-Process" in full

    # Section spécifique avec ancre
    section = service.get_page_content("features/mcp.md", "#1-architecture-react")
    assert section is not None
    assert "Architecture ReAct" in section
    assert "Éditeur KaTeX" not in section

    # Page inexistante
    assert service.get_page_content("inconnu.md") is None


def test_get_feature_quick_help_and_export_functions(temp_docs_env: tuple[Path, Path]):
    docs_dir, config_file = temp_docs_env
    service = AppDocumentationService(docs_dir=docs_dir, config_path=config_file)

    # Fiche prédéfinie
    help_wozniak = service.get_feature_quick_help("wozniak")
    assert "Linter Wozniak" in help_wozniak

    # Fiche via recherche
    help_react = service.get_feature_quick_help("ReAct")
    assert "Serveur MCP" in help_react or "Architecture ReAct" in help_react


def test_real_docs_service_singleton():
    """Vérifie que la documentation réelle du projet s'indexe et se consulte sans erreur."""
    service = AppDocumentationService.get_instance()
    service.ensure_indexed()

    topics = service.get_topics()
    assert len(topics) >= 20

    res_fts = search_app_documentation("nuitka compilation")
    assert "Résultats de recherche" in res_fts
    assert "nuitka" in res_fts.lower()

    page_content = read_app_doc_page("features/consultant_mcp.md")
    assert "Consultant IA Autonome & Serveur MCP" in page_content

    topics_list = list_app_doc_topics()
    assert "Sommaire de la Documentation Officielle" in topics_list

    quick_dag = get_feature_quick_help("dag")
    assert "Moteur d'Orchestration DAG" in quick_dag
