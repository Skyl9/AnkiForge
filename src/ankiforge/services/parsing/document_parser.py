import json
import os
import re
import subprocess  # nosec B404
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import docx
import markdownify
import trafilatura
from bs4 import BeautifulSoup
from pptx import Presentation

from ankiforge.services.cards.media_manager import MediaManager


class DocumentParser:
    """Service en charge d'extraire le texte brut de divers formats de documents."""

    def __init__(self, media_manager: MediaManager | None = None):
        self.media_manager = media_manager or MediaManager()

    def parse_document(self, source_file_path: str | Path, progress_callback=None, check_cancel=None) -> str:
        """Détecte l'extension et utilise le bon parseur."""
        source_str = str(source_file_path).strip()
        if source_str.startswith("http"):
            if progress_callback:
                progress_callback("Téléchargement et extraction de la page Web...")
            return self._parse_web(source_str)

        file_path = Path(source_file_path)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Le fichier {file_path} est introuvable.")

        ext = file_path.suffix.lower()

        if ext == ".pdf":
            return self._parse_pdf_with_marker(file_path, progress_callback, check_cancel)
        elif ext in [".txt", ".md"]:
            if progress_callback:
                progress_callback("Lecture du fichier texte immédiate...")
            return self._parse_text(file_path)
        elif ext == ".docx":
            if progress_callback:
                progress_callback("Analyse du document Word en cours...")
            return self._parse_docx(file_path)
        elif ext == ".pptx":
            if progress_callback:
                progress_callback("Analyse de la présentation PowerPoint en cours...")
            return self._parse_pptx(file_path)
        else:
            raise ValueError(f"Format de fichier non supporté : {ext}")

    def _parse_web(self, url: str) -> str:
        """Télécharge la page et extrait le contenu sémantique principal (Boilerplate removal)."""
        if trafilatura is None:
            raise RuntimeError("Le module trafilatura n'est pas installé. Lancez 'uv add trafilatura'")
        if "wikipedia.org/wiki/" in url:
            return self._parse_wikipedia(url)
        # Téléchargement
        downloaded = trafilatura.fetch_url(url)
        if downloaded is None:
            raise ValueError("Accès refusé ou URL invalide. Le site est peut-être protégé contre les robots (Cloudflare, connexion requise...).")

        # Extraction intelligente (format markdown activé pour garder la structure h1, h2, listes)
        result = trafilatura.extract(downloaded, output_format="markdown", include_links=False, include_images=False)

        if not result:
            raise ValueError("Aucun contenu textuel principal détecté. Il s'agit peut-être d'une page vide ou générée dynamiquement via JavaScript (SPA).")

        return result

    @staticmethod
    def _parse_wikipedia(url: str) -> str:
        """Utilise l'API de Wikimedia pour récupérer le HTML et extraire le LaTeX proprement."""
        if BeautifulSoup is None or markdownify is None:
            raise RuntimeError("Pour lire les mathématiques de Wikipédia, installez les outils : 'uv add beautifulsoup4 markdownify'")

        try:
            parsed_url = urllib.parse.urlparse(url)
            domain_parts = parsed_url.netloc.split(".")
            lang = domain_parts[0] if len(domain_parts) >= 3 else "en"

            raw_title = parsed_url.path.split("/")[-1]
            title = urllib.parse.unquote(raw_title)

            # CHANGEMENT CRUCIAL : action=parse & prop=text ramène le vrai HTML de la page
            api_url = f"https://{lang}.wikipedia.org/w/api.php?action=parse&format=json&page={urllib.parse.quote(title)}&prop=text"

            req = urllib.request.Request(api_url, headers={"User-Agent": "AnkiForge/0.2"})
            with urllib.request.urlopen(req) as response:  # nosec B310
                data = json.loads(response.read().decode("utf-8"))

            html_content = data.get("parse", {}).get("text", {}).get("*", "")
            if not html_content:
                raise ValueError(f"L'article '{title}' est introuvable ou vide.")

            # 1. Parsing du HTML
            soup = BeautifulSoup(html_content, "html.parser")

            # 2. SAUVETAGE DU LATEX ✨
            # Wikipédia stocke le LaTeX brut dans une balise <annotation> invisible
            for math_span in soup.find_all("span", class_="mwe-math-element"):
                annotation = math_span.find("annotation", encoding="application/x-tex")
                if annotation and annotation.text:
                    latex_code = annotation.text.strip()

                    # Nettoyage de la macro {\displaystyle ...} propre à Wikipedia
                    if latex_code.startswith(r"{\displaystyle") and latex_code.endswith("}"):
                        latex_code = latex_code[14:-1].strip()

                    # On remplace l'image illisible par notre LaTeX entouré de $$
                    math_span.replace_with(f" $${latex_code}$$ ")

            # 3. SUPPRESSION DU BRUIT (Boilerplate removal)
            # On détruit les infoboxes, les menus, et les petites références [1]
            for element in soup.find_all(["table", "div"], class_=["infobox", "navbox", "reflist", "mw-empty-elt"]):
                element.decompose()
            for ref in soup.find_all("sup", class_="reference"):
                ref.decompose()

            # 4. CONVERSION EN MARKDOWN
            markdown_text = markdownify.markdownify(str(soup), heading_style="ATX")

            # Nettoyage final des sauts de ligne multiples générés par la conversion
            markdown_text = re.sub(r"\n{3,}", "\n\n", markdown_text)

            return f"# {title}\n\n{markdown_text.strip()}"

        except urllib.error.URLError as e:
            raise RuntimeError(f"Impossible de joindre l'API Wikipédia : {e.reason}") from e
        except Exception as e:
            raise ValueError(f"Erreur lors du traitement Wikipédia : {e}") from e

    def _parse_pdf_with_marker(self, file_path: str | Path, progress_callback=None, check_cancel=None) -> str:
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
                    shell=use_shell,  # nosec B602
                    encoding="utf-8",
                    errors="replace",
                ) as process:
                    if process.stdout is not None:
                        for line in iter(process.stdout.readline, ""):
                            if check_cancel and check_cancel():
                                process.terminate()
                                try:
                                    process.wait(timeout=2)
                                except subprocess.TimeoutExpired:
                                    process.kill()
                                raise InterruptedError("Extraction annulée par l'utilisateur.")
                            if line and progress_callback:
                                progress_callback(line.strip())

                    process.wait()
                    if check_cancel and check_cancel():
                        raise InterruptedError("Extraction annulée par l'utilisateur.")

                    if process.returncode != 0:
                        raise RuntimeError(f"Marker a échoué avec le code erreur {process.returncode}.")

            except FileNotFoundError as e:
                # Cette exception ne s'activera QUE si "marker_single" n'existe pas sur le PC
                raise RuntimeError("Marker n'est pas installé ou introuvable. Lancez 'uv pip install marker-pdf'") from e

            # 👇 La suite du code n'est plus dans le try/except
            md_files = list(temp_dir.rglob("*.md"))

            if not md_files:
                # Maintenant, cette erreur pourra remonter correctement jusqu'au test !
                raise FileNotFoundError("Marker n'a pas généré de fichier .md. Consultez les logs.")

            if progress_callback:
                progress_callback("\n📄 Extraction texte terminée. Traitement et copie des images...")

            md_file_path = md_files[0]
            marker_output_folder = md_file_path.parent

            raw_markdown = md_file_path.read_text(encoding="utf-8", errors="ignore")

            processed_markdown = self.media_manager.process_extracted_folder(source_folder=str(marker_output_folder), markdown_content=raw_markdown)

            if progress_callback:
                progress_callback("✅ Terminé !")
            return processed_markdown

    @staticmethod
    def _parse_docx(file_path: Path) -> str:
        """Extrait le texte d'un Word en traduisant les styles de titre en Markdown."""
        if docx is None:
            raise RuntimeError("Le module python-docx n'est pas installé. Lancez 'uv add python-docx'")

        doc = docx.Document(str(file_path))
        full_text = []

        for para in doc.paragraphs:
            text = para.text.strip()
            if text:
                style = para.style
                raw_name = getattr(style, "name", "") if style else ""

                # On s'assure d'avoir une chaîne de caractères (même vide)
                style_name = str(raw_name).lower() if raw_name else ""
                # Traduction sémantique pour aider le "Chunking" de l'IA
                if "heading 1" in style_name or "titre 1" in style_name:
                    full_text.append(f"# {text}")
                elif "heading 2" in style_name or "titre 2" in style_name:
                    full_text.append(f"## {text}")
                elif "heading 3" in style_name or "titre 3" in style_name:
                    full_text.append(f"### {text}")
                else:
                    full_text.append(text)

        return "\n\n".join(full_text)

    @staticmethod
    def _parse_pptx(file_path: Path) -> str:
        """Extrait le texte d'un PowerPoint, diapositive par diapositive."""
        if Presentation is None:
            raise RuntimeError("Le module python-pptx n'est pas installé. Lancez 'uv add python-pptx'")

        prs = Presentation(str(file_path))
        full_text = []

        for i, slide in enumerate(prs.slides):
            slide_text = []
            for shape in slide.shapes:
                if hasattr(shape, "has_text_frame") and shape.has_text_frame:
                    for paragraph in shape.text_frame.paragraphs:
                        text = paragraph.text.strip()
                        if text:
                            slide_text.append(text)

            if slide_text:
                slide_content = "\n".join(slide_text)
                # Force un titre Markdown pour chaque slide.
                # Le Chunking "Sémantique" d'AnkiForge découpera donc la prez' slide par slide !
                full_text.append(f"## Diapositive {i + 1}\n{slide_content}")

        # Séparation forte entre les slides
        return "\n\n[SPLIT]\n\n".join(full_text)

    @staticmethod
    def _parse_text(file_path: Path) -> str:
        """Lecture basique de fichiers texte."""
        return file_path.read_text(encoding="utf-8")

    # Les méthodes docx et pptx pourront être ajoutées ici très facilement !
