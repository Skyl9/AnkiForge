from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from ankiforge.services.parsing.document_parser import DocumentParser



def test_parse_document_file_not_found():
    """Test 1: Si le fichier n'existe pas, ça doit crasher tout de suite."""
    parser = DocumentParser()
    with pytest.raises(FileNotFoundError) as exc_info:
        parser.parse_document("fichier_fantome.pdf")

    assert "est introuvable" in str(exc_info.value)



def test_parse_document_unsupported_format(tmp_path):
    """Test 2: Si on passe un .docx alors qu'on ne gère que pdf/txt/md."""
    fake_docx = tmp_path / "document.docx"
    fake_docx.write_text("fake content")

    parser = DocumentParser()
    with pytest.raises(ValueError) as exc_info:
        parser.parse_document(str(fake_docx))

    assert "Format de fichier non supporté : .docx" in str(exc_info.value)



def test_parse_text_file(tmp_path):
    """Test 3: Vérifie que les fichiers texte sont lus instantanément."""
    fake_md = tmp_path / "cours.md"
    fake_md.write_text("# Titre\nCeci est un cours.", encoding="utf-8")

    parser = DocumentParser()
    mock_callback = MagicMock()
    result = parser.parse_document(str(fake_md), progress_callback=mock_callback)

    # On vérifie que le texte ressort bien et que le callback a prévenu l'UI
    assert "Ceci est un cours." in result
    mock_callback.assert_called_with("Lecture du fichier texte immédiate...")


@patch('ankiforge.services.parsing.document_parser.MediaManager')
@patch('subprocess.Popen')
def test_parse_pdf_with_marker_success(mock_popen, MockMediaManager, tmp_path):
    """Test 4: Simule l'extraction d'un PDF avec Marker."""
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

        # On simule la console qui crache du texte
        mock_process.stdout.readline.side_effect = ["Loading AI...\n", "Page 1...\n", ""]
        mock_process.returncode = 0
        return mock_process

    mock_popen.side_effect = side_effect_popen

    parser = DocumentParser()
    mock_callback = MagicMock()
    result = parser.parse_document(str(fake_pdf), progress_callback=mock_callback)

    # On vérifie que tout s'est bien passé
    assert result == "Markdown final traité avec images"
    mock_callback.assert_any_call("Loading AI...")



@patch('subprocess.Popen')
def test_parse_pdf_marker_crash(mock_popen, tmp_path):
    """Test 5: Vérifie ce qui se passe si l'IA plante (ex: RAM pleine)."""
    fake_pdf = tmp_path / "crash.pdf"
    fake_pdf.write_bytes(b"%PDF")

    def side_effect_popen(*args, **kwargs):
        mock_process = MagicMock()
        mock_process.__enter__.return_value = mock_process  # <-- Fix
        mock_process.stdout.readline.side_effect = ["Fatal Error", ""]
        mock_process.returncode = 1  # 👈 C'est ce code d'erreur qui déclenche le RuntimeError
        return mock_process

    mock_popen.side_effect = side_effect_popen

    parser = DocumentParser()
    with pytest.raises(RuntimeError) as exc_info:
        parser.parse_document(str(fake_pdf))

    assert "Marker a échoué avec le code erreur 1" in str(exc_info.value)



@patch('subprocess.Popen')
def test_parse_pdf_no_md_generated(mock_popen, tmp_path):
    """Test 6: L'IA dit qu'elle a fini (Code 0), mais le fichier .md n'est pas là !"""
    fake_pdf = tmp_path / "vide.pdf"
    fake_pdf.write_bytes(b"%PDF")

    def side_effect_popen(*args, **kwargs):
        mock_process = MagicMock()
        mock_process.__enter__.return_value = mock_process  # <-- Fix
        mock_process.stdout.readline.side_effect = [""]
        mock_process.returncode = 0
        return mock_process

    mock_popen.side_effect = side_effect_popen

    parser = DocumentParser()
    with pytest.raises(FileNotFoundError) as exc_info:
        parser.parse_document(str(fake_pdf))


    assert "Marker n'a pas généré de fichier .md" in str(exc_info.value)


@patch('subprocess.Popen')
def test_parse_pdf_marker_not_installed(mock_popen, tmp_path):
    """Test 7: Vérifie que si le PC de l'utilisateur n'a pas Marker, on lui dit gentiment."""
    fake_pdf = tmp_path / "no_marker.pdf"
    fake_pdf.write_bytes(b"%PDF")

    mock_popen.side_effect = FileNotFoundError("No such file or directory: 'marker_single'")

    parser = DocumentParser()
    with pytest.raises(RuntimeError) as exc_info:
        parser.parse_document(str(fake_pdf))

    assert "Marker n'est pas installé ou introuvable" in str(exc_info.value)