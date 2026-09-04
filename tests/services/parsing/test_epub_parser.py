"""Tests unitaires pour le service de parsage de livres EPUB (EpubParser) et conversion MathML."""

import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from bs4 import BeautifulSoup

from ankiforge.services.parsing.chunking_service import ChunkingService
from ankiforge.services.parsing.document_parser import DocumentParser
from ankiforge.services.parsing.epub_parser import (
    EpubParser,
    convert_mathml_to_latex,
)


def create_sample_epub(
    file_path: Path,
    is_epub3: bool = False,
    include_mathml: bool = True,
    include_image: bool = True,
) -> Path:
    """Helper pour générer une archive EPUB valide en mémoire ou sur disque pour les tests."""
    with zipfile.ZipFile(str(file_path), "w") as zf:
        # 1. Mimetype
        zf.writestr("mimetype", "application/epub+zip")

        # 2. Container
        zf.writestr(
            "META-INF/container.xml",
            """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
    <rootfiles>
        <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
    </rootfiles>
</container>""",
        )

        # 3. OPF Package
        manifest_items = [
            '<item id="ch1" href="chapters/ch1.xhtml" media-type="application/xhtml+xml"/>',
            '<item id="ch2" href="chapters/ch2.xhtml" media-type="application/xhtml+xml"/>',
        ]
        if is_epub3:
            manifest_items.append('<item id="nav" href="nav.xhtml" properties="nav" media-type="application/xhtml+xml"/>')
        else:
            manifest_items.append('<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>')

        if include_image:
            manifest_items.append('<item id="img1" href="images/fig1.png" media-type="image/png"/>')

        spine_tag = "<spine>" if is_epub3 else '<spine toc="ncx">'
        manifest_str = "\n        ".join(manifest_items)

        zf.writestr(
            "OEBPS/content.opf",
            f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="{"3.0" if is_epub3 else "2.0"}" unique-identifier="pub-id">
    <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
        <dc:title>Traité de Physiologie</dc:title>
        <dc:creator>Dr. Jean Dupont</dc:creator>
        <dc:language>fr</dc:language>
    </metadata>
    <manifest>
        {manifest_str}
    </manifest>
    {spine_tag}
        <itemref idref="ch1"/>
        <itemref idref="ch2"/>
    </spine>
</package>""",
        )

        # 4. Table des matières
        if is_epub3:
            zf.writestr(
                "OEBPS/nav.xhtml",
                """<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<body>
    <nav epub:type="toc">
        <h1>Sommaire</h1>
        <ol>
            <li><a href="chapters/ch1.xhtml">Chapitre 1 : Les Glucides</a></li>
            <li><a href="chapters/ch2.xhtml">Chapitre 2 : Énergie Cellulaire</a></li>
        </ol>
    </nav>
</body>
</html>""",
            )
        else:
            zf.writestr(
                "OEBPS/toc.ncx",
                """<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
    <navMap>
        <navPoint id="np1" playOrder="1">
            <navLabel><text>Chapitre 1 : Les Glucides</text></navLabel>
            <content src="chapters/ch1.xhtml"/>
        </navPoint>
        <navPoint id="np2" playOrder="2">
            <navLabel><text>Chapitre 2 : Énergie Cellulaire</text></navLabel>
            <content src="chapters/ch2.xhtml"/>
        </navPoint>
    </navMap>
</ncx>""",
            )

        # 5. Chapitres
        img_tag = '<p><img src="../images/fig1.png" alt="Cycle de Krebs"/></p>' if include_image else ""
        math_tag = (
            """
        <p>Formule :</p>
        <math xmlns="http://www.w3.org/1998/Math/MathML" display="block">
            <mrow><mi>E</mi><mo>=</mo><mi>m</mi><msup><mi>c</mi><mn>2</mn></msup></mrow>
        </math>
        """
            if include_mathml
            else ""
        )

        zf.writestr(
            "OEBPS/chapters/ch1.xhtml",
            f"""<!DOCTYPE html>
<html>
<head><title>Ch 1</title></head>
<body>
    <h1>Les Glucides</h1>
    <p>Le glucose est la source d'énergie essentielle.</p>
    {img_tag}
</body>
</html>""",
        )

        zf.writestr(
            "OEBPS/chapters/ch2.xhtml",
            f"""<!DOCTYPE html>
<html>
<head><title>Ch 2</title></head>
<body>
    <h1>Énergie Cellulaire</h1>
    <p>La respiration cellulaire permet de générer de l'ATP.</p>
    {math_tag}
</body>
</html>""",
        )

        if include_image:
            # Fake 1x1 PNG bytes
            fake_png = (
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
                b"\x00\x00\x00\nIDATx\x9cc`\x00\x00\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82"
            )
            zf.writestr("OEBPS/images/fig1.png", fake_png)

    return file_path


# =========================================================================
# Tests Unitaires MathML vers LaTeX
# =========================================================================


def test_convert_mathml_basic_symbols():
    """Vérifie la conversion des identifiants, nombres et symboles grecs/opérateurs."""
    html = "<math><mrow><mi>α</mi><mo>+</mo><mi>β</mi><mo>=</mo><mn>42</mn></mrow></math>"
    soup = BeautifulSoup(html, "html.parser")
    res = convert_mathml_to_latex(soup.find("math"))
    assert r"\alpha + \beta = 42" in res


def test_convert_mathml_fraction_and_roots():
    """Vérifie les fractions, racines carrées et racines nièmes."""
    html = """
    <math>
        <mfrac>
            <msqrt><mi>x</mi></msqrt>
            <mroot><mi>y</mi><mn>3</mn></mroot>
        </mfrac>
    </math>
    """
    soup = BeautifulSoup(html, "html.parser")
    res = convert_mathml_to_latex(soup.find("math"))
    assert r"\frac{\sqrt{x}}{\sqrt[3]{y}}" in res


def test_convert_mathml_sub_sup():
    """Vérifie les indices, exposants et indices+exposants combinés."""
    html = """
    <math>
        <mrow>
            <msubsup><mi>x</mi><mn>1</mn><mn>2</mn></msubsup>
            <mo>+</mo>
            <msub><mi>y</mi><mi>i</mi></msub>
        </mrow>
    </math>
    """
    soup = BeautifulSoup(html, "html.parser")
    res = convert_mathml_to_latex(soup.find("math"))
    assert "{x}_{1}^{2}" in res
    assert "{y}_{i}" in res


def test_convert_mathml_annotations():
    """Vérifie que l'annotation TeX originale est utilisée si disponible."""
    html = """
    <math>
        <semantics>
            <mrow><mi>complex</mi></mrow>
            <annotation encoding="application/x-tex">\\int_{0}^{\\infty} e^{-x} dx</annotation>
        </semantics>
    </math>
    """
    soup = BeautifulSoup(html, "html.parser")
    res = convert_mathml_to_latex(soup.find("math"))
    assert res == r"\int_{0}^{\infty} e^{-x} dx"


def test_convert_mathml_alt_attribute():
    """Vérifie le repli sur l'attribut alt ou alttext."""
    html = '<math alt="E = mc^2"><mrow><mi>junk</mi></mrow></math>'
    soup = BeautifulSoup(html, "html.parser")
    res = convert_mathml_to_latex(soup.find("math"))
    assert res == "E = mc^2"


def test_convert_mathml_matrix():
    """Vérifie la conversion d'une table / matrice MathML."""
    html = """
    <math>
        <mtable>
            <mtr><mtd><mn>1</mn></mtd><mtd><mn>2</mn></mtd></mtr>
            <mtr><mtd><mn>3</mn></mtd><mtd><mn>4</mn></mtd></mtr>
        </mtable>
    </math>
    """
    soup = BeautifulSoup(html, "html.parser")
    res = convert_mathml_to_latex(soup.find("math"))
    assert r"\begin{matrix}" in res
    assert "1 & 2" in res
    assert "3 & 4" in res
    assert r"\end{matrix}" in res


# =========================================================================
# Tests Unitaires EpubParser
# =========================================================================


def test_epub_parser_epub2_ncx(tmp_path):
    """Vérifie le parsage complet d'un EPUB 2 avec table des matières NCX."""
    epub_path = tmp_path / "manuel_epub2.epub"
    create_sample_epub(epub_path, is_epub3=False)

    mock_media = MagicMock()
    mock_media.store_media_bytes.return_value = MagicMock(filename="hash_fig1.png")

    parser = EpubParser(media_manager=mock_media)
    progress_calls = []
    result = parser.parse(epub_path, progress_callback=lambda msg: progress_calls.append(msg))

    assert len(progress_calls) >= 2
    assert "<!-- PAGE: 1 -->" in result
    assert "<!-- PAGE: 2 -->" in result
    assert "Les Glucides" in result
    assert "Énergie Cellulaire" in result
    assert "hash_fig1.png" in result
    assert "$$E = m {c}^{2}$$" in result or "$$E = m{c}^{2}$$" in result
    assert "[SPLIT]" in result


def test_epub_parser_epub3_nav(tmp_path):
    """Vérifie le parsage complet d'un EPUB 3 avec document de navigation nav.xhtml."""
    epub_path = tmp_path / "manuel_epub3.epub"
    create_sample_epub(epub_path, is_epub3=True)

    mock_media = MagicMock()
    mock_media.store_media_bytes.return_value = MagicMock(filename="hash_fig1.png")

    parser = EpubParser(media_manager=mock_media)
    result = parser.parse(epub_path)

    assert "<!-- PAGE: 1 -->" in result
    assert "<!-- PAGE: 2 -->" in result
    assert "Le glucose est la source d'énergie" in result
    assert "La respiration cellulaire permet" in result


def test_epub_parser_file_not_found():
    """Vérifie qu'une erreur claire est levée si le fichier n'existe pas."""
    parser = EpubParser()
    with pytest.raises(FileNotFoundError):
        parser.parse("inexistant.epub")


def test_epub_parser_invalid_zip(tmp_path):
    """Vérifie qu'une archive corrompue sans OPF est signalée proprement."""
    corrupted_path = tmp_path / "corrupted.epub"
    with zipfile.ZipFile(str(corrupted_path), "w") as zf:
        zf.writestr("test.txt", "not an epub")

    parser = EpubParser()
    with pytest.raises(ValueError) as exc:
        parser.parse(corrupted_path)
    assert "impossible de trouver le fichier de manifeste .opf" in str(exc.value)


def test_epub_parser_cancellation(tmp_path):
    """Vérifie que le check_cancel interrompt proprement l'extraction."""
    epub_path = tmp_path / "manuel_cancel.epub"
    create_sample_epub(epub_path)

    parser = EpubParser()
    # Interrompt immédiatement après la première vérification
    call_count = 0

    def cancel_check() -> bool:
        nonlocal call_count
        call_count += 1
        return call_count > 1

    result = parser.parse(epub_path, check_cancel=cancel_check)
    # Ne doit contenir que la première page
    assert "<!-- PAGE: 1 -->" in result
    assert "<!-- PAGE: 2 -->" not in result


# =========================================================================
# Tests Intégration DocumentParser & ChunkingService
# =========================================================================


def test_document_parser_epub_integration(tmp_path):
    """Vérifie que DocumentParser prend en charge le format .epub nativement."""
    epub_path = tmp_path / "manuel_integ.epub"
    create_sample_epub(epub_path)

    doc_parser = DocumentParser()
    result = doc_parser.parse_document(str(epub_path))

    assert "<!-- PAGE: 1 -->" in result
    assert "<!-- PAGE: 2 -->" in result
    assert "Les Glucides" in result


def test_chunking_service_epub_integration(tmp_path):
    """Vérifie que ChunkingService découpe les chapitres EPUB en chunks avec page_number et heading_path."""
    epub_path = tmp_path / "manuel_chunks.epub"
    create_sample_epub(epub_path)

    parser = EpubParser()
    raw_md = parser.parse(epub_path)

    chunks = ChunkingService.extract_chunks(raw_md, file_type="epub")

    assert len(chunks) == 2
    # Premier chunk = Chapitre 1
    assert chunks[0]["page_number"] == 1
    assert "Glucides" in chunks[0]["heading_path"]
    assert "glucose" in chunks[0]["content"]

    # Deuxième chunk = Chapitre 2
    assert chunks[1]["page_number"] == 2
    assert "Énergie" in chunks[1]["heading_path"]
    assert "ATP" in chunks[1]["content"]
