"""Tests unitaires pour l'outil MCP `render_anki_html` (Markdown + LaTeX/KaTeX -> HTML Anki)."""

import asyncio

import pytest

from ankiforge.database.models import DocumentModel
from ankiforge.services.ai.mcp_server import mcp
from ankiforge.services.ai.mcp_tool_registry import (
    DEFAULT_CONSULTANT_TOOLS,
    MCPToolRegistry,
)

pytestmark = pytest.mark.integration


def _extract_text(res: object) -> str:
    """Extrait le texte d'un `CallToolResult` retourné par `mcp.call_tool()`."""
    return str(res.content[0].text) if hasattr(res, "content") and res.content else str(res)


def test_render_anki_html_markdown_simple() -> None:
    """Une source Markdown basique est convertie en HTML structurel."""
    html = MCPToolRegistry.render_anki_html(content="# Les Stats\n\nDu texte en **gras** et une liste:\n\n- item 1\n- item 2")
    assert "<h1" in html or "<h3" in html
    assert "<strong>gras</strong>" in html
    assert "<li>item 1</li>" in html
    assert "<li>item 2</li>" in html


def test_render_anki_html_preserve_latex_delimiters() -> None:
    """Les délimiteurs LaTeX/KaTeX sont préservés intacts pour le rendu côté WebEngine."""
    source = "En ligne : $E=mc^2$ et \\(x \\in \\mathbb{R}\\).\nEn bloc : $$\\int_{0}^{\\infty} e^{-x} \\, dx = 1$$ et \\[ \\alpha + \\beta \\]."
    html = MCPToolRegistry.render_anki_html(content=source)
    assert "$E=mc^2$" in html
    assert "\\(x \\in \\mathbb{R}\\)" in html
    assert "$$\\int_{0}^{\\infty} e^{-x} \\, dx = 1$$" in html
    assert "\\[ \\alpha + \\beta \\]" in html
    # Aucun anti-slash LaTeX n'a été échappé/détruit par le convertisseur Markdown.
    assert "\\mathbb{R}" in html
    assert "\\int_{0}^{\\infty}" in html


def test_render_anki_html_mixed_content() -> None:
    """Markdown et formules coexistent sans corruption mutuelle."""
    source = "Soit la fonction \\(f(x) = x^2\\) :\n\n$$f'(x) = 2x$$"
    html = MCPToolRegistry.render_anki_html(content=source)
    assert "\\(f(x) = x^2\\)" in html
    assert "$$f'(x) = 2x$$" in html
    assert "<p>" in html


def test_render_anki_html_empty_content() -> None:
    """Une source vide produit une erreur explicite plutôt que du HTML vide silencieux."""
    assert MCPToolRegistry.render_anki_html(content="").startswith("Erreur :")
    assert MCPToolRegistry.render_anki_html(content="   \n  ").startswith("Erreur :")


def test_render_anki_html_document_id() -> None:
    """L'outil accepte un `document_id` en lieu et place du texte brut."""
    doc = DocumentModel.create(
        title="Polycopié de Physique",
        content="# Mécanique\n\nL'énergie : \\(E_k = \\frac{1}{2} m v^2\\).",
    )
    html = MCPToolRegistry.render_anki_html(document_id=doc.id)
    assert "\\frac{1}{2} m v^2" in html
    assert "Mécanique" in html

    html_unknown = MCPToolRegistry.render_anki_html(document_id=999999)
    assert html_unknown.startswith("Erreur :")


def test_render_anki_html_wrap_mathjax() -> None:
    """Avec wrap_mathjax=True, le bundle KaTeX local est injecté pour QWebEngineView."""
    html = MCPToolRegistry.render_anki_html(content="$E=mc^2$", wrap_mathjax=True)
    assert html.startswith("<!DOCTYPE html>")
    assert "<html" in html and "</html>" in html
    assert "katex.min.js" in html
    assert "renderMathInElement" in html
    assert "$E=mc^2$" in html


def test_render_anki_html_declared_in_consultant_tools() -> None:
    """L'outil est déclaré dans DEFAULT_CONSULTANT_TOOLS pour l'agent conversationnel."""
    tool_names = [t["function"]["name"] for t in DEFAULT_CONSULTANT_TOOLS]
    assert "render_anki_html" in tool_names
    entry = next(t for t in DEFAULT_CONSULTANT_TOOLS if t["function"]["name"] == "render_anki_html")
    assert "content" in entry["function"]["parameters"]["properties"]
    assert "document_id" in entry["function"]["parameters"]["properties"]
    assert "wrap_mathjax" in entry["function"]["parameters"]["properties"]


def test_render_anki_html_exposed_on_fastmcp_server() -> None:
    """L'outil est exposé par le serveur FastMCP et invoquable via call_tool()."""

    async def _run() -> str:
        tools = await mcp.list_tools()
        assert "render_anki_html" in [t.name for t in tools]
        call_res = await mcp.call_tool(
            "render_anki_html",
            {"content": "# Test\n\n\\(x > 0\\)", "wrap_mathjax": True},
        )
        text = _extract_text(call_res)
        assert "\\(x > 0\\)" in text
        assert "katex.min.js" in text
        return text

    html = asyncio.run(_run())
    assert html.startswith("<!DOCTYPE html>")


def test_render_anki_html_document_id_content_fallback() -> None:
    """`document_id` est utilisé lorsque le contenu brut est vide (convention `format_markdown_document`)."""
    doc = DocumentModel.create(title="Doc A", content="Contenu du document A")
    html = MCPToolRegistry.render_anki_html(document_id=doc.id)
    assert "Contenu du document A" in html

    # Quand le contenu brut est fourni non vide, il est utilisé tel quel.
    html_brut = MCPToolRegistry.render_anki_html(content="Contenu brute explicite", document_id=doc.id)
    assert "Contenu brute explicite" in html_brut
    assert "Contenu du document A" not in html_brut
