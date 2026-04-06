import os
import subprocess
import sys
import tempfile
from pathlib import Path

from ankiforge.services.cards.media_manager import MediaManager

class DocumentParser:
    """Service en charge d'extraire le texte brut de divers formats de documents."""

    def __init__(self, media_manager: MediaManager | None = None):
        self.media_manager = media_manager or MediaManager()

    def parse_document(self, file_path: str|Path,progress_callback=None) -> str:
        """Détecte l'extension et utilise le bon parseur."""
        file_path = Path(file_path)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Le fichier {file_path} est introuvable.")

        ext = file_path.suffix.lower()

        if ext == '.pdf':
            return self._parse_pdf_with_marker(file_path, progress_callback)
        elif ext in ['.txt', '.md']:
            if progress_callback: progress_callback("Lecture du fichier texte immédiate...")
            return self._parse_text(file_path)
        else:
            raise ValueError(f"Format de fichier non supporté : {ext}")

    def _parse_pdf_with_marker(self, file_path: str | Path, progress_callback=None) -> str:
        """Extraction Deep Learning via Marker pour un LaTeX le plus proche de la réalité."""
        # On a retiré le grand "try:" global
        with tempfile.TemporaryDirectory() as temp_dir_str:
            temp_dir = Path(temp_dir_str)
            use_shell = sys.platform.startswith("win")
            cmd = ["marker_single", str(file_path), "--output_dir", str(temp_dir)]

            if progress_callback:
                progress_callback("Lancement du moteur de Deep Learning (Marker)...")
                progress_callback("Le chargement des modèles IA en RAM peut prendre quelques instants.\n")

            # 👇 On limite le try/except EXCLUSIVEMENT au lancement du processus
            try:
                with subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        shell=use_shell,
                        encoding='utf-8',
                        errors='replace'
                ) as process:

                    for line in iter(process.stdout.readline, ''):
                        if line and progress_callback:
                            progress_callback(line.strip())

                    process.wait()

                    if process.returncode != 0:
                        raise RuntimeError(f"Marker a échoué avec le code erreur {process.returncode}.")

            except FileNotFoundError:
                # Cette exception ne s'activera QUE si "marker_single" n'existe pas sur le PC
                raise RuntimeError("Marker n'est pas installé ou introuvable. Lancez 'uv pip install marker-pdf'")

            # 👇 La suite du code n'est plus dans le try/except
            md_files = list(temp_dir.rglob("*.md"))

            if not md_files:
                # Maintenant, cette erreur pourra remonter correctement jusqu'au test !
                raise FileNotFoundError("Marker n'a pas généré de fichier .md. Consultez les logs.")

            if progress_callback:
                progress_callback("\n📄 Extraction texte terminée. Traitement et copie des images...")

            md_file_path = md_files[0]
            marker_output_folder = md_file_path.parent

            raw_markdown = md_file_path.read_text(encoding='utf-8', errors='ignore')

            processed_markdown = self.media_manager.process_extracted_folder(
                source_folder=str(marker_output_folder),
                markdown_content=raw_markdown
            )

            if progress_callback: progress_callback("✅ Terminé !")
            return processed_markdown


    def _parse_text(self, file_path: Path) -> str:
        """Lecture basique de fichiers texte."""
        return file_path.read_text(encoding='utf-8')

    # Les méthodes docx et pptx pourront être ajoutées ici très facilement !
