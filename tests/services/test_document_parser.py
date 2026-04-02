# tests/test_document_parser.py
import subprocess
import pytest
from unittest.mock import patch
from pathlib import Path

from src import DocumentParser


def test_parse_text_file(tmp_path):
    """Vérifie la lecture d'un simple fichier .txt ou .md sans Marker."""
    # Création d'un vrai faux fichier texte
    fake_md = tmp_path / "cours.md"
    fake_md.write_text("# Titre\nCeci est un cours.", encoding="utf-8")

    parser = DocumentParser()
    result = parser.parse_document(str(fake_md))

    assert "Ceci est un cours." in result


@patch('subprocess.run')  # MAGIE : On intercepte TOUS les appels systèmes dans ce test !
def test_parse_pdf_with_marker_success(mock_subprocess_run, tmp_path):
    """Simule une extraction PDF réussie sans lancer le vrai Deep Learning."""

    # 1. PRÉPARATION DES FAUX FICHIERS
    fake_pdf = tmp_path / "physique_quantique.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 mock pdf content")

    # 2. PROGRAMMATION DE L'INTERCEPTEUR (Le Mock)
    def side_effect_simulate_marker(*args, **kwargs):
        """Cette fonction va s'exécuter À LA PLACE de subprocess.run"""
        # Marker crée un dossier portant le nom du PDF, puis un fichier .md dedans
        output_dir = kwargs.get('cwd') or kwargs.get('env')  # Approximation, on sait que tempdir est utilisé

        # Astuce : On récupère le temp_dir généré par le DocumentParser dans ses arguments
        # args[0] = ["marker_single", "chemin/physique.pdf", "--output_dir", "chemin/temp"]
        cmd_args = args[0]
        temp_dir_idx = cmd_args.index("--output_dir") + 1
        temp_dir = cmd_args[temp_dir_idx]

        # On simule le travail de Marker : Création du dossier et du Markdown
        marker_folder = Path(temp_dir) / "physique_quantique"
        marker_folder.mkdir(parents=True, exist_ok=True)

        mock_md = marker_folder / "physique_quantique.md"
        mock_md.write_text("# Extraction Réussie\nVoici la formule : $\\int x$", encoding="utf-8")

        # On retourne un faux objet de succès pour `subprocess.run`
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="Success", stderr="")

    # On attache notre faux comportement au mock
    mock_subprocess_run.side_effect = side_effect_simulate_marker

    # 3. EXÉCUTION
    parser = DocumentParser()
    result = parser.parse_document(str(fake_pdf))

    # 4. VÉRIFICATIONS
    assert mock_subprocess_run.called, "La commande système n'a pas été appelée."
    assert "Extraction Réussie" in result
    assert "\\int x" in result


@patch('subprocess.run')
def test_parse_pdf_marker_crash(mock_subprocess_run, tmp_path):
    """Vérifie que l'application gère bien un crash violent de Marker (ex: Plus de RAM)."""

    fake_pdf = tmp_path / "gros_document.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 mock")

    # On force l'intercepteur à lever une erreur critique
    mock_subprocess_run.side_effect = subprocess.CalledProcessError(
        returncode=1, cmd="marker_single", stderr="Out of memory (CUDA OOM)"
    )

    parser = DocumentParser()

    # On vérifie que notre DocumentParser attrape l'erreur et lève une RuntimeError propre
    with pytest.raises(RuntimeError) as exc_info:
        parser.parse_document(str(fake_pdf))

    assert "Le moteur Marker a planté" in str(exc_info.value)
    assert "CUDA OOM" in str(exc_info.value)