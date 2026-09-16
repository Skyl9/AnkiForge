import json
import stat
from pathlib import Path
from unittest.mock import MagicMock, patch

import docx
import pytest
from pptx import Presentation

import ankiforge.services.parsing.document_parser as document_parser
from ankiforge.services.parsing.document_parser import DocumentParser
from ankiforge.services.parsing.marker_service import MarkerService


def test_parse_document_file_not_found():
    """Test 1: Si le fichier n'existe pas, ça doit crasher tout de suite."""
    parser = DocumentParser()
    with pytest.raises(FileNotFoundError) as exc_info:
        parser.parse_document("fichier_fantome.pdf")

    assert "est introuvable" in str(exc_info.value)


def test_parse_document_unsupported_format(tmp_path):
    """Test 2: On passe un format exotique non géré (.xyz)."""
    fake_unsupported = tmp_path / "document.xyz"
    fake_unsupported.write_text("fake content")

    parser = DocumentParser()
    with pytest.raises(ValueError) as exc_info:
        parser.parse_document(str(fake_unsupported))

    assert "Format de fichier non supporté : .xyz" in str(exc_info.value)


def test_parse_text_file(tmp_path):
    """Test 3: Vérifie que les fichiers texte sont lus instantanément."""
    fake_md = tmp_path / "cours.md"
    fake_md.write_text("# Titre\nCeci est un cours.", encoding="utf-8")

    parser = DocumentParser()
    mock_callback = MagicMock()
    result = parser.parse_document(str(fake_md), progress_callback=mock_callback)

    assert "Ceci est un cours." in result
    mock_callback.assert_called_with("Lecture du fichier texte immédiate...")


# ==========================================
# TESTS BUREAUTIQUE (DOCX / PPTX)
# ==========================================


@pytest.mark.integration
def test_parse_docx_success(tmp_path):
    """Test 4: Vérifie l'extraction d'un Word et la traduction des styles en Markdown."""
    fake_docx_path = tmp_path / "test_cours.docx"

    # Création d'un vrai document Word en mémoire
    doc = docx.Document()
    doc.add_heading("Le Théorème de Pythagore", level=1)
    doc.add_paragraph("Voici le contenu du théorème.")
    doc.add_heading("Démonstration", level=2)
    doc.save(str(fake_docx_path))

    parser = DocumentParser()
    result = parser.parse_document(str(fake_docx_path))

    # Vérifications du Markdown généré
    assert "# Le Théorème de Pythagore" in result
    assert "Voici le contenu du théorème." in result
    assert "## Démonstration" in result


@pytest.mark.integration
def test_parse_pptx_success(tmp_path):
    """Test 5: Vérifie l'extraction d'un PowerPoint slide par slide avec balise SPLIT."""
    fake_pptx_path = tmp_path / "test_prez.pptx"

    # Création d'une vraie présentation PowerPoint en mémoire
    prs = Presentation()

    # Slide 1
    slide1 = prs.slides.add_slide(prs.slide_layouts[0])
    slide1.shapes.title.text = "Titre Slide 1"
    slide1.placeholders[1].text = "Contenu Slide 1"

    # Slide 2
    slide2 = prs.slides.add_slide(prs.slide_layouts[0])
    slide2.shapes.title.text = "Titre Slide 2"

    prs.save(str(fake_pptx_path))

    parser = DocumentParser()
    result = parser.parse_document(str(fake_pptx_path))

    # Vérifications de la structure générée
    assert "## Diapositive 1" in result
    assert "Titre Slide 1" in result
    assert "Contenu Slide 1" in result
    assert "\n\n[SPLIT]\n\n" in result
    assert "## Diapositive 2" in result
    assert "Titre Slide 2" in result


@patch("ankiforge.services.parsing.document_parser.docx", None)
def test_parse_docx_missing_lib(tmp_path):
    """Test 6: Si l'import de python-docx échoue, on doit lever une erreur claire."""
    fake_docx = tmp_path / "test.docx"
    fake_docx.touch()  # Le fichier doit exister pour passer le premier check

    parser = DocumentParser()
    with pytest.raises(RuntimeError) as exc_info:
        parser.parse_document(str(fake_docx))

    assert "python-docx n'est pas installé" in str(exc_info.value)


# ==========================================
# TESTS MARKER (PDF)
# ==========================================


@patch("ankiforge.services.parsing.document_parser.MediaManager")
@patch("ankiforge.services.parsing.document_parser.DocumentParser.get_marker_executable", return_value="/usr/local/bin/marker_single")
@patch("subprocess.Popen")
def test_parse_pdf_with_marker_success(mock_popen, mock_get_marker, MockMediaManager, tmp_path):
    """Test 7: Simule l'extraction d'un PDF avec Marker."""
    fake_pdf = tmp_path / "physique.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 mock pdf content")

    mock_media_instance = MockMediaManager.return_value
    mock_media_instance.process_extracted_folder.return_value = "Markdown final traité avec images"

    def side_effect_popen(cmd, *args, **kwargs):
        out_dir_idx = cmd.index("--output_dir") + 1
        temp_dir = Path(cmd[out_dir_idx])

        marker_folder = temp_dir / "physique"
        marker_folder.mkdir(parents=True, exist_ok=True)
        (marker_folder / "physique.md").write_text("Contenu brut", encoding="utf-8")

        mock_process = MagicMock()
        mock_process.__enter__.return_value = mock_process
        mock_process.stdout.readline.side_effect = ["Loading AI...\n", "Page 1...\n", ""]
        mock_process.returncode = 0
        return mock_process

    mock_popen.side_effect = side_effect_popen

    parser = DocumentParser()
    mock_callback = MagicMock()
    result = parser.parse_document(str(fake_pdf), progress_callback=mock_callback)

    assert result == "Markdown final traité avec images"
    mock_callback.assert_any_call("Loading AI...")


def test_marker_executable_is_found_in_bundle_resources(tmp_path, monkeypatch):
    """Le build autonome peut embarquer marker_single dans Contents/Resources/tools."""
    executable = tmp_path / "Contents" / "MacOS" / "AnkiForge"
    marker = tmp_path / "Contents" / "Resources" / "tools" / "marker_single"
    executable.parent.mkdir(parents=True)
    marker.parent.mkdir(parents=True)
    executable.write_text("", encoding="utf-8")
    marker.write_text("#!/bin/sh", encoding="utf-8")
    marker.chmod(marker.stat().st_mode | stat.S_IXUSR)

    monkeypatch.setattr(document_parser.sys, "executable", str(executable))
    monkeypatch.setattr(document_parser.shutil, "which", lambda _: None)
    monkeypatch.setattr("ankiforge.utils.paths.get_tools_search_dirs", lambda: [])

    assert DocumentParser.get_marker_executable() == str(marker)


def test_marker_executable_is_found_in_persistent_venv(tmp_path, monkeypatch):
    """Le Marker installé depuis une application packagée est résolu dans ~/.ankiforge/tools."""
    marker = tmp_path / "tools" / "marker" / "venv" / "bin" / "marker_single"
    marker.parent.mkdir(parents=True)
    marker.write_text("#!/bin/sh", encoding="utf-8")
    marker.chmod(marker.stat().st_mode | stat.S_IXUSR)

    monkeypatch.setattr("ankiforge.services.parsing.marker_service.get_tools_search_dirs", lambda: [tmp_path / "tools"])
    monkeypatch.setattr(MarkerService, "_is_venv_compatible", lambda _: True)
    monkeypatch.setattr(document_parser.shutil, "which", lambda _: None)
    monkeypatch.setattr(document_parser.sys, "executable", str(tmp_path / "app"))

    assert MarkerService.get_executable() == marker


def test_marker_installer_uses_external_python_and_persistent_venv(tmp_path, monkeypatch):
    commands: list[list[str]] = []
    tools_dir = tmp_path / "tools"
    monkeypatch.setattr("ankiforge.services.parsing.marker_service.get_tools_search_dirs", lambda: [tools_dir])
    monkeypatch.setattr(MarkerService, "_find_python", lambda: "/usr/local/bin/python3")
    monkeypatch.setattr(MarkerService, "_find_uv", lambda: None)
    monkeypatch.setattr(MarkerService, "_is_python_compatible", lambda _: True)

    class FakeProcess:
        stdout = ()

        def wait(self):
            return 0

    def fake_popen(command, **_):
        commands.append(command)
        bin_dir = tools_dir / "marker" / "venv" / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        (bin_dir / "python").write_text("#!/bin/sh")
        marker_file = bin_dir / "marker_single"
        marker_file.write_text("#!/bin/sh")
        marker_file.chmod(marker_file.stat().st_mode | stat.S_IXUSR)
        return FakeProcess()

    monkeypatch.setattr("ankiforge.services.parsing.marker_service.subprocess.Popen", fake_popen)
    executable = tools_dir / "marker" / "venv" / "bin" / "marker_single"

    assert MarkerService.install() == executable
    assert commands[0][:3] == ["/usr/local/bin/python3", "-m", "venv"]
    assert commands[1][1:4] == ["-m", "pip", "install"]


@patch("ankiforge.services.parsing.document_parser.DocumentParser.get_marker_executable", return_value="/usr/local/bin/marker_single")
@patch("subprocess.Popen")
def test_parse_pdf_marker_crash(mock_popen, mock_get_marker, tmp_path):
    """Test 8: Vérifie ce qui se passe si l'IA plante."""
    fake_pdf = tmp_path / "crash.pdf"
    fake_pdf.write_bytes(b"%PDF")

    def side_effect_popen(*args, **kwargs):
        mock_process = MagicMock()
        mock_process.__enter__.return_value = mock_process
        mock_process.stdout.readline.side_effect = ["Fatal Error", ""]
        mock_process.returncode = 1
        return mock_process

    mock_popen.side_effect = side_effect_popen

    parser = DocumentParser()
    with pytest.raises(RuntimeError) as exc_info:
        parser.parse_document(str(fake_pdf))

    assert "Marker a échoué avec le code erreur 1" in str(exc_info.value)


@patch("ankiforge.services.parsing.document_parser.DocumentParser.get_marker_executable", return_value="/usr/local/bin/marker_single")
@patch("subprocess.Popen")
def test_parse_pdf_no_md_generated(mock_popen, mock_get_marker, tmp_path):
    """Test 9: L'IA dit qu'elle a fini, mais le .md n'est pas là !"""
    fake_pdf = tmp_path / "vide.pdf"
    fake_pdf.write_bytes(b"%PDF")

    def side_effect_popen(*args, **kwargs):
        mock_process = MagicMock()
        mock_process.__enter__.return_value = mock_process
        mock_process.stdout.readline.side_effect = [""]
        mock_process.returncode = 0
        return mock_process

    mock_popen.side_effect = side_effect_popen

    parser = DocumentParser()
    with pytest.raises(FileNotFoundError) as exc_info:
        parser.parse_document(str(fake_pdf))

    assert "Marker n'a pas généré de fichier .md" in str(exc_info.value)


@patch("ankiforge.services.parsing.document_parser.DocumentParser.get_marker_executable", return_value=None)
@patch("pypdf.PdfReader")
def test_parse_pdf_pypdf_fallback_success(mock_reader_cls, mock_get_marker, tmp_path):
    """Test 10: Vérifie le fallback pypdf si Marker n'est pas installé."""
    fake_pdf = tmp_path / "simple.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 simple")

    mock_page1 = MagicMock()
    mock_page1.extract_text.return_value = "Première page de cours"
    mock_page2 = MagicMock()
    mock_page2.extract_text.return_value = "Deuxième page de cours"

    mock_reader = MagicMock()
    mock_reader.pages = [mock_page1, mock_page2]
    mock_reader_cls.return_value = mock_reader

    parser = DocumentParser()
    mock_callback = MagicMock()
    result = parser.parse_document(str(fake_pdf), progress_callback=mock_callback)

    assert "## Page 1" in result
    assert "Première page de cours" in result
    assert "## Page 2" in result
    assert "Deuxième page de cours" in result
    mock_callback.assert_any_call("Extraction PDF native en cours (pypdf)...")


# ==========================================
# TESTS NOTEBOOKS JUPYTER (.ipynb)
# ==========================================


def _build_notebook(cells):
    """Construit un dictionnaire notebook Jupyter v4 minimal."""
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {},
        "cells": cells,
    }


def test_parse_ipynb_success(tmp_path):
    """Un notebook mixte (markdown + code) est converti en Markdown structuré."""
    notebook = _build_notebook(
        [
            {"cell_type": "markdown", "metadata": {}, "source": "# Les boucles Python\n\nLe `for` en Python."},
            {
                "cell_type": "code",
                "metadata": {},
                "execution_count": 3,
                "source": ["total = 0\n", "for i in range(4):\n", "    total += i\n", "print(total)"],
                "outputs": [
                    {"output_type": "stream", "name": "stdout", "text": ["6\n"]},
                    {"output_type": "execute_result", "data": {"text/plain": ["6"]}, "metadata": {}, "execution_count": 3},
                ],
            },
            {"cell_type": "code", "metadata": {}, "execution_count": None, "source": "def carre(x):\n    return x**2", "outputs": []},
        ]
    )

    fake_ipynb = tmp_path / "cours.ipynb"
    fake_ipynb.write_text(json.dumps(notebook), encoding="utf-8")

    parser = DocumentParser()
    result = parser.parse_document(str(fake_ipynb))

    assert "# Les boucles Python" in result
    assert "## Cellule 2 (exécution #3)" in result
    assert "```python" in result
    assert "for i in range(4):" in result
    assert "### Résultat" in result
    assert "> 6" in result
    assert "## Cellule 3" in result
    assert "def carre(x):" in result


def test_parse_ipynb_invalid_json(tmp_path):
    """Un notebook non-JSON doit lever une erreur claire."""
    fake_ipynb = tmp_path / "casse.ipynb"
    fake_ipynb.write_text("{pas du json", encoding="utf-8")

    parser = DocumentParser()
    with pytest.raises(ValueError) as exc_info:
        parser.parse_document(str(fake_ipynb))

    assert "JSON invalide" in str(exc_info.value)


def test_parse_ipynb_non_notebook_json(tmp_path):
    """Un JSON valide mais sans liste de cellules n'est pas un notebook."""
    fake_ipynb = tmp_path / "faux.ipynb"
    fake_ipynb.write_text('{"title": "nimporte quoi"}', encoding="utf-8")

    parser = DocumentParser()
    with pytest.raises(ValueError) as exc_info:
        parser.parse_document(str(fake_ipynb))

    assert "notebook Jupyter valide" in str(exc_info.value)


def test_parse_ipynb_skips_images_and_errors(tmp_path):
    """Les sorties non textuelles sont ignorées, les erreurs sont restituées."""
    notebook = _build_notebook(
        [
            {
                "cell_type": "code",
                "metadata": {},
                "execution_count": 1,
                "source": "1/0",
                "outputs": [
                    {"output_type": "display_data", "data": {"image/png": "fake", "text/plain": ["IGNOREE"]}, "metadata": {}},
                    {"output_type": "error", "ename": "ZeroDivisionError", "evalue": "division by zero", "traceback": [], "metadata": {}},
                ],
            }
        ]
    )

    fake_ipynb = tmp_path / "erreur.ipynb"
    fake_ipynb.write_text(json.dumps(notebook), encoding="utf-8")

    parser = DocumentParser()
    result = parser.parse_document(str(fake_ipynb))

    assert "ZeroDivisionError" in result
    assert "division by zero" in result
    assert "IGNOREE" not in result


# ==========================================
# TESTS CODE PYTHON (.py)
# ==========================================


def test_parse_python_success(tmp_path):
    """Un fichier .py structuré est converti en Markdown organisé par AST, code préservé."""
    fake_py = tmp_path / "collections.py"
    fake_py.write_text(
        '"""Outils de statistiques."""\n'
        "\n"
        "def moyenne(valeurs):\n"
        '    """Calcule la moyenne."""\n'
        "    return sum(valeurs) / len(valeurs)\n"
        "\n"
        "class Statistiques:\n"
        '    """Agrégateur statistique."""\n'
        "\n"
        "    def __init__(self, valeurs):\n"
        "        self.valeurs = valeurs\n"
        "\n"
        "    async def etendue(self):\n"
        '        """Retourne l\'étendue."""\n'
        "        return max(self.valeurs) - min(self.valeurs)\n",
        encoding="utf-8",
    )

    parser = DocumentParser()
    result = parser.parse_document(str(fake_py))

    assert "Outils de statistiques." in result
    assert "### def moyenne" in result
    assert "Calcule la moyenne." in result
    assert "return sum(valeurs) / len(valeurs)" in result
    assert "## class Statistiques" in result
    assert "Agrégateur statistique." in result
    assert "### def __init__" in result
    assert "async def etendue" in result
    assert "return max(self.valeurs) - min(self.valeurs)" in result


def test_parse_python_syntax_error_fallback(tmp_path):
    """Un .py invalide est conservé en un seul bloc de code sans crasher."""
    fake_py = tmp_path / "corrompu.py"
    fake_py.write_text("def casse(:\n    pass", encoding="utf-8")

    parser = DocumentParser()
    result = parser.parse_document(str(fake_py))

    assert "```python" in result
    assert "def casse(:" in result


def test_parse_python_plain_module_keeps_code(tmp_path):
    """Un module sans classe ni fonction reste disponible en bloc de code."""
    fake_py = tmp_path / "script.py"
    fake_py.write_text("IMPORT_MATHS = True\n\nprint('hello')\n", encoding="utf-8")

    parser = DocumentParser()
    result = parser.parse_document(str(fake_py))

    assert "```python" in result
    assert "IMPORT_MATHS = True" in result
    assert "print('hello')" in result
