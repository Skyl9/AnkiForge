# src/services/parsing/document_parser.py
import os
import fitz  # PyMuPDF


# import docx  (À décommenter plus tard quand tu feras le pip install python-docx)
# import pptx  (À décommenter plus tard quand tu feras le pip install python-pptx)

class DocumentParser:
    """Service en charge d'extraire le texte brut de divers formats de documents."""

    def parse_document(self, file_path: str) -> str:
        """Détecte l'extension et utilise le bon parseur."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Le fichier {file_path} est introuvable.")

        ext = os.path.splitext(file_path)[1].lower()

        if ext == '.pdf':
            return self._parse_pdf(file_path)
        elif ext in ['.txt', '.md']:
            return self._parse_text(file_path)
        # elif ext == '.docx':
        #     return self._parse_docx(file_path)
        # elif ext == '.pptx':
        #     return self._parse_pptx(file_path)
        else:
            raise ValueError(f"Format de fichier non supporté : {ext}")

    def _parse_pdf(self, file_path: str) -> str:
        """Extraction ultra-rapide du texte d'un PDF via PyMuPDF."""
        text_content = []
        try:
            doc = fitz.open(file_path)
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                text = page.get_text()

                # Petit nettoyage pour éviter les sauts de ligne excessifs
                cleaned_text = "\n".join([line.strip() for line in text.split('\n') if line.strip()])

                text_content.append(f"--- PAGE {page_num + 1} ---\n{cleaned_text}\n")
            return "\n".join(text_content)
        except Exception as e:
            raise RuntimeError(f"Erreur lors de la lecture du PDF : {str(e)}")

    def _parse_text(self, file_path: str) -> str:
        """Lecture basique de fichiers texte."""
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()

    # Les méthodes docx et pptx pourront être ajoutées ici très facilement !