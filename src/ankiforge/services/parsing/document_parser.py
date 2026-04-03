# src/services/parsing/document_parser.py
import os
import subprocess
import tempfile
from pathlib import Path

from ankiforge.services.cards.media_manager import MediaManager

class DocumentParser:
    """Service en charge d'extraire le texte brut de divers formats de documents."""

    def __init__(self, media_manager: MediaManager | None = None):
        self.media_manager = media_manager or MediaManager()

    def parse_document(self, file_path: str|Path) -> str:
        """Détecte l'extension et utilise le bon parseur."""
        file_path = Path(file_path)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Le fichier {file_path} est introuvable.")

        ext = file_path.suffix.lower()

        if ext == '.pdf':
            return self._parse_pdf_with_marker(file_path)
        elif ext in ['.txt', '.md']:
            return self._parse_text(file_path)
        else:
            raise ValueError(f"Format de fichier non supporté : {ext}")

    def _parse_pdf_with_marker(self, file_path: str|Path) -> str:
        """Extraction Deep Learning via Marker pour un LaTeX le plus proche de la réalité."""
        try:
            with tempfile.TemporaryDirectory() as temp_dir_str:
                temp_dir = Path(temp_dir_str)
                # subprocess.run bloque l'exécution ici jusqu'à la fin de Marker
                process = subprocess.run(
                    ["marker_single", str(file_path), "--output_dir", str(temp_dir)],
                    check=True,
                    capture_output=True,
                    text=True
                )

                md_files = list(temp_dir.rglob("*.md"))

                if not md_files:
                    raise FileNotFoundError(f"Marker n'a pas généré de fichier .md. Logs:\n{process.stderr}")

                md_file_path = md_files[0]  # On prend le fichier trouvé
                marker_output_folder = md_file_path.parent

                raw_markdown = md_file_path.read_text(encoding='utf-8')

                processed_markdown = self.media_manager.process_extracted_folder(
                    source_folder=str(marker_output_folder),
                    markdown_content=raw_markdown
                )

                return processed_markdown

        except FileNotFoundError:
            raise RuntimeError("Marker n'est pas installé ou introuvable. Lancez 'uv pip install marker-pdf'")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Le moteur Marker a rencontré une erreur :\n{e.stderr}")

    def _parse_text(self, file_path: Path) -> str:
        """Lecture basique de fichiers texte."""
        return file_path.read_text(encoding='utf-8')

    # Les méthodes docx et pptx pourront être ajoutées ici très facilement !
