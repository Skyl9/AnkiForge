"""Tests d'intégration pour le formatteur et structurateur Markdown (Chunking, Ingestion, MCP)."""

from ankiforge.services.ai.consultant_engine import ConsultantToolRegistry
from ankiforge.services.parsing.chunking_service import ChunkingService
from ankiforge.services.parsing.document_parser import DocumentParser


def test_chunking_service_markdown_ast_strategy() -> None:
    content = (
        "# Partie 1 : Principes Généraux\n\n"
        "Explication des principes fondamentaux.\n\n"
        "## Sous-partie 1.1 : Détails\n\n"
        "Données approfondies sur les principes.\n\n"
        "# Partie 2 : Applications Pratiques\n\n"
        "Cas d'usage concrets."
    )
    chunks = ChunkingService.extract_chunks(
        content,
        file_type="md",
        strategy=ChunkingService.STRATEGY_MARKDOWN_AST,
    )
    assert len(chunks) == 3
    assert chunks[0]["heading_path"] == "Partie 1 : Principes Généraux"
    assert chunks[1]["heading_path"] == "Partie 1 : Principes Généraux > Sous-partie 1.1 : Détails"
    assert chunks[2]["heading_path"] == "Partie 2 : Applications Pratiques"
    assert all("content_hash" in c for c in chunks)


def test_document_parser_auto_format(tmp_path: object) -> None:
    test_file = tmp_path / "test_doc.md"  # type: ignore[operator]
    raw_content = "#Titre Sans Espace\n\nCette infor-\nmation est essen-\ntielle.\n\nFormule : \\[ E = mc^2 \\]"
    test_file.write_text(raw_content, encoding="utf-8")

    parser = DocumentParser()
    result = parser.parse_document(str(test_file), auto_format=True)

    assert "# Titre Sans Espace" in result
    assert "information" in result
    assert "essentielle" in result
    assert "$$\nE = mc^2\n$$" in result


def test_consultant_mcp_format_markdown_document_raw_content() -> None:
    raw = "## Titre ##\n\nCalcul : \\( x + y = z \\)\n\n| A | B |\n|---|---|\n| 1 | 2 |"
    res = ConsultantToolRegistry.format_markdown_document(content=raw)
    assert "Formatage Markdown achevé" in res
    assert "## Titre" in res
    assert "$x + y = z$" in res


def test_consultant_mcp_get_document_outline_raw_content() -> None:
    raw = "# Neurosciences\n\n## Cerveau\n\n### Hémisphère gauche"
    res = ConsultantToolRegistry.get_document_outline(content=raw)
    assert "Neurosciences" in res
    assert "Cerveau" in res
    assert "Hémisphère gauche" in res
    assert "H1:" in res
    assert "H2:" in res
    assert "H3:" in res


def test_consultant_mcp_structure_document_sections_raw_content() -> None:
    raw = "# Chapitre 1\n\nTexte chapitre 1.\n\n## Section A\n\nTexte section A."
    res = ConsultantToolRegistry.structure_document_sections(content=raw, max_tokens=500)
    assert "Découpage sémantique" in res
    assert "Chapitre 1" in res
    assert "Section A" in res


def test_consultant_mcp_structure_transcript_for_ai_raw_content(monkeypatch: object) -> None:
    from unittest.mock import MagicMock

    from ankiforge.services.ai.base import LLMProvider
    from ankiforge.services.markdown.ai_structurer import AIDocumentStructurer

    mock_provider = MagicMock(spec=LLMProvider)
    mock_provider.generate.return_value = "# Cours de Biologie\n\n## [00:15] Introduction à la cellule\n\nLa cellule est l'unité de base du vivant.\n\nLa formule énergétique est $ATP = ADP + Pi$."
    monkeypatch.setattr(AIDocumentStructurer, "_resolve_provider", lambda: mock_provider)  # type: ignore[attr-defined]

    raw = "00:15 alors bonjour à tous aujourd'hui on parle de la cellule et de l'ATP"
    res = ConsultantToolRegistry.structure_transcript_for_ai(content=raw, profile="didactic")

    assert "Document restructuré par IA avec succès" in res
    assert "didactic" in res
    assert "Cours de Biologie" in res
    assert "[00:15]" in res
    assert "$ATP = ADP + Pi$" in res
