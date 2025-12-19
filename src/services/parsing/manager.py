# src/services/parsing/manager.py
import os
from abc import ABC, abstractmethod

class ContentParser(ABC):
    @abstractmethod
    def extract(self, file_path: str) -> str:
        pass

class TextParser(ContentParser):
    """Parser simple pour .txt et .md"""
    def extract(self, file_path: str) -> str:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()

# Placeholder pour le futur PDFParser (nécessite pymupdf)
class PDFParser(ContentParser):
    def extract(self, file_path: str) -> str:
        # TODO: Implémenter fitz/pymupdf ici
        return f"[Simulation] Contenu extrait du PDF : {os.path.basename(file_path)}"

class IngestionManager:
    def __init__(self):
        self.parsers = {
            '.txt': TextParser(),
            '.md': TextParser(),
            '.pdf': PDFParser(),
            # '.pptx': PPTXParser() # À ajouter plus tard
        }

    def process_file(self, file_path: str) -> str:
        _, ext = os.path.splitext(file_path)
        parser = self.parsers.get(ext.lower())
        if parser:
            return parser.extract(file_path)
        raise ValueError(f"Extension non supportée : {ext}")