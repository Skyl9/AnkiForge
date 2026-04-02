# src/services/parsing/document_parser.py
import os
import subprocess
import tempfile

from ankiforge.services.cards.media_manager import MediaManager


# import docx  (À décommenter plus tard quand tu feras le pip install python-docx)
# import pptx  (À décommenter plus tard quand tu feras le pip install python-pptx)

class DocumentParser:
    """Service en charge d'extraire le texte brut de divers formats de documents."""

    def __init__(self):
        self.media_manager = MediaManager()  # <-- INSTANCIATION

    def parse_document(self, file_path: str) -> str:
        """Détecte l'extension et utilise le bon parseur."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Le fichier {file_path} est introuvable.")

        ext = os.path.splitext(file_path)[1].lower()

        if ext == '.pdf':
            return self._parse_pdf_with_marker(file_path)
        elif ext in ['.txt', '.md']:
            return self._parse_text(file_path)
        # elif ext == '.docx':
        #     return self._parse_docx(file_path)
        # elif ext == '.pptx':
        #     return self._parse_pptx(file_path)
        else:
            raise ValueError(f"Format de fichier non supporté : {ext}")

    def _parse_pdf_with_marker(self, file_path: str) -> str:
        """Extraction Deep Learning via Marker pour un LaTeX parfait."""
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                # subprocess.run bloque l'exécution ici jusqu'à la fin de Marker
                process = subprocess.run(
                    ["marker_single", file_path, "--output_dir", temp_dir],
                    check=True,
                    capture_output=True,
                    text=True
                )

                pdf_name = os.path.splitext(os.path.basename(file_path))[0]
                marker_output_folder = os.path.join(temp_dir, pdf_name)
                md_file_path = os.path.join(marker_output_folder, f"{pdf_name}.md")

                if os.path.exists(md_file_path):
                    with open(md_file_path, 'r', encoding='utf-8') as f:
                        raw_markdown = f.read()

                    # 👇 NOUVEAU : Traitement des images avant de renvoyer le texte 👇
                    processed_markdown = self.media_manager.process_extracted_folder(
                        source_folder=marker_output_folder,
                        markdown_content=raw_markdown
                    )
                    return processed_markdown
                else:
                    raise FileNotFoundError(f"Marker n'a pas généré de Markdown. Logs:\n{process.stderr}")

        except FileNotFoundError:
            raise RuntimeError("Marker n'est pas installé. Lancez 'uv pip install marker-pdf'")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Le moteur Marker a planté :\n{e.stderr}")

    def _parse_text(self, file_path: str) -> str:
        """Lecture basique de fichiers texte."""
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()

    # Les méthodes docx et pptx pourront être ajoutées ici très facilement !
