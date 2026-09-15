"""Tests unitaires pour MarkdownFormatter."""

from ankiforge.services.markdown.formatter import MarkdownFormatter
from ankiforge.services.markdown.models import FormatOptions


def test_formatter_empty_string() -> None:
    res = MarkdownFormatter.format("")
    assert res.formatted_text == ""
    assert not res.changed
    assert res.changes_summary == []


def test_formatter_dehyphenate_ocr() -> None:
    raw = "Cette infor-\nmation est essen-\ntielle pour les inter-\nvenants du projet."
    res = MarkdownFormatter.format(raw, FormatOptions(dehyphenate_ocr=True, clean_whitespace=False))
    assert res.changed
    assert "information" in res.formatted_text
    assert "essentielle" in res.formatted_text
    assert "intervenants" in res.formatted_text
    assert any("césure" in c for c in res.changes_summary)


def test_formatter_dehyphenate_preserves_code_fences() -> None:
    raw = "Texte nor-\nmal.\n\n```python\n# Ceci est un com-\n# mentaire dans le code\n```"
    res = MarkdownFormatter.format(raw, FormatOptions(dehyphenate_ocr=True, clean_whitespace=False))
    assert "Texte normal." in res.formatted_text
    assert "# Ceci est un com-\n# mentaire dans le code" in res.formatted_text


def test_formatter_katex_normalization() -> None:
    raw = "L'équation d'Einstein est \\[ E = mc^2 \\] et la variable \\( x \\) est inconnue."
    res = MarkdownFormatter.format(raw, FormatOptions(normalize_katex=True))
    assert "$$\nE = mc^2\n$$" in res.formatted_text
    assert "$x$" in res.formatted_text
    assert any("KaTeX" in c for c in res.changes_summary)


def test_formatter_katex_preserves_inline_code() -> None:
    raw = "Ne pas toucher à `\\[ non math \\]` ni à `\\( test \\)`."
    res = MarkdownFormatter.format(raw, FormatOptions(normalize_katex=True))
    assert "`\\[ non math \\]`" in res.formatted_text
    assert "`\\( test \\)`" in res.formatted_text


def test_formatter_atx_headings() -> None:
    raw = "#Titre Sans Espace\n## Titre Avec Hash De Fin ##\n###Titre Mixte ###"
    res = MarkdownFormatter.format(raw, FormatOptions(normalize_headings=True))
    assert "# Titre Sans Espace" in res.formatted_text
    assert "## Titre Avec Hash De Fin" in res.formatted_text
    assert "### Titre Mixte" in res.formatted_text


def test_formatter_table_alignment() -> None:
    raw = "| Nom | Rôle | Score |\n|:---|:---:|---:|\n| Alice | Admin | 100 |\n| Bob | Utilisateur | 5 |"
    res = MarkdownFormatter.format(raw, FormatOptions(align_tables=True))
    assert res.changed
    lines = res.formatted_text.strip().split("\n")
    # All rows should have identical column delimiters
    assert len(lines) == 4
    for line in lines:
        assert line.startswith("| ")
        assert line.endswith(" |")
        assert line.count("|") == 4


def test_formatter_normalize_code_fences() -> None:
    raw = "~~~python   \nprint('hello')\n~~~"
    res = MarkdownFormatter.format(raw, FormatOptions(normalize_code_fences=True))
    assert "```python\n" in res.formatted_text
    assert "print('hello')" in res.formatted_text


def test_formatter_clean_whitespace() -> None:
    raw = "# Titre   \n\n\n\nParagraphe avec espaces en fin.    \nLigne avec hard break markdown.  \nFin de texte."
    res = MarkdownFormatter.format(raw, FormatOptions(clean_whitespace=True))
    # Should collapse multiple blank lines to exactly one blank line (\n\n)
    assert "\n\n\n" not in res.formatted_text
    # Should preserve the 2 spaces for hard break
    assert "Ligne avec hard break markdown.  \n" in res.formatted_text
    # Should strip the 4 spaces
    assert "Paragraphe avec espaces en fin.\n" in res.formatted_text
