import json
import logging
import os
import re
import shutil
import subprocess  # nosec B404
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import docx
import markdownify
import trafilatura
from bs4 import BeautifulSoup
from pptx import Presentation

from ankiforge.services.cards.media_manager import MediaManager

logger = logging.getLogger(__name__)


class DocumentParser:
    """
    Service d'extraction de texte multi-format.

    Capacité à transformer des fichiers PDF, Word, PowerPoint, Markdown et des pages Web
    en texte brut structuré (Markdown) optimisé pour le traitement par IA.
    """

    def __init__(self, media_manager: MediaManager | None = None):
        """
        Initialise le parseur avec un gestionnaire de médias.

        Args:
            media_manager (MediaManager | None): Pour gérer les images extraites (ex: PDF).
        """
        self.media_manager = media_manager or MediaManager()

    def parse_document(self, source_file_path: str | Path, progress_callback: Any = None, check_cancel: Any = None) -> str:
        """
        Détermine le type de document et invoque le parseur approprié.

        Args:
            source_file_path (str | Path): Chemin local ou URL du document.
            progress_callback (callable | None): Fonction de rappel pour la progression (msg: str).
            check_cancel (callable | None): Fonction pour vérifier si l'utilisateur a annulé.

        Returns:
            str: Le texte extrait au format Markdown.

        Raises:
            FileNotFoundError: Si le fichier local est introuvable.
            ValueError: Si le format n'est pas supporté.
            RuntimeError: En cas d'échec d'un moteur tiers (ex: Marker).
        """
        source_str = str(source_file_path).strip()
        logger.info("Extraction de document démarrée pour : %s", source_str)

        if source_str.startswith("http"):
            if progress_callback:
                progress_callback("Téléchargement et extraction de la page Web...")
            res = self._parse_web(source_str)
            logger.info("Extraction Web terminée pour '%s' (%d caractères)", source_str, len(res))
            return res

        file_path = Path(source_file_path)
        if not os.path.exists(file_path):
            logger.error("Fichier introuvable sur le disque : %s", file_path)
            raise FileNotFoundError(f"Le fichier {file_path} est introuvable.")

        ext = file_path.suffix.lower()

        if ext == ".pdf":
            res = self._parse_pdf_with_marker(file_path, progress_callback, check_cancel) if self.is_marker_available() else self._parse_pdf_with_pypdf(file_path, progress_callback, check_cancel)
        elif ext in [".txt", ".md"]:
            if progress_callback:
                progress_callback("Lecture du fichier texte immédiate...")
            res = self._parse_text(file_path)
        elif ext == ".docx":
            if progress_callback:
                progress_callback("Analyse du document Word en cours...")
            res = self._parse_docx(file_path)
        elif ext == ".pptx":
            if progress_callback:
                progress_callback("Analyse de la présentation PowerPoint en cours...")
            res = self._parse_pptx(file_path, progress_callback, check_cancel)
        elif ext == ".epub":
            if progress_callback:
                progress_callback("Extraction du livre numérique EPUB en cours...")
            res = self._parse_epub(file_path, progress_callback, check_cancel)
        elif ext in (".mp3", ".m4a", ".wav", ".ogg", ".flac", ".aac", ".wma"):
            if progress_callback:
                progress_callback("Transcription de l'enregistrement audio en cours...")
            res = self._parse_audio(file_path, progress_callback, check_cancel)
        else:
            logger.warning("Format de fichier non supporté : %s", ext)
            raise ValueError(f"Format de fichier non supporté : {ext}")

        logger.info("Extraction locale terminée pour '%s' (%d caractères)", file_path.name, len(res))
        return res

    def _parse_web(self, url: str) -> str:
        """
        Télécharge et extrait le contenu principal d'une page Web.
        """
        if "youtube.com/watch" in url or "youtu.be/" in url:
            from ankiforge.services.parsing.youtube_parser import YouTubeParser

            try:
                parser = YouTubeParser()
                # Extraction basique des sous-titres sans l'agent IA (l'IA interviendra lors du batching dans CreationView)
                result = parser.parse(url, ai_manager=None)
                if result:
                    return result
                raise ValueError("Impossible de récupérer les sous-titres YouTube pour cette vidéo.")
            except Exception as e:
                raise ValueError(f"Erreur d'extraction YouTube : {e}") from e

        if trafilatura is None:
            raise RuntimeError("Le module trafilatura n'est pas installé. Lancez 'uv add trafilatura'")
        if "wikipedia.org/wiki/" in url:
            return self._parse_wikipedia(url)
        # Téléchargement
        downloaded = trafilatura.fetch_url(url)
        if downloaded is None:
            raise ValueError("Accès refusé ou URL invalide. Le site est peut-être protégé contre les robots (Cloudflare, connexion requise...).")

        # Extraction intelligente (format markdown activé pour garder la structure h1, h2, listes)
        extracted_text: str = str(trafilatura.extract(downloaded, output_format="markdown", include_links=False, include_images=False) or "")

        if not extracted_text:
            raise ValueError("Aucun contenu textuel principal détecté. Il s'agit peut-être d'une page vide ou générée dynamiquement via JavaScript (SPA).")

        return extracted_text

    @staticmethod
    def _parse_wikipedia(url: str) -> str:
        """
        Extrait le contenu d'un article Wikipédia en préservant les formules LaTeX.

        Args:
            url (str): URL de l'article Wikipédia.

        Returns:
            str: L'article converti en Markdown avec LaTeX protégé par des $$.
        """
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

            req = urllib.request.Request(api_url, headers={"User-Agent": "AnkiForge/1.0"})
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
            logger.exception("Impossible de joindre l'API Wikipédia :")
            raise RuntimeError(f"Impossible de joindre l'API Wikipédia : {e.reason}") from e
        except json.JSONDecodeError as e:
            logger.exception("Réponse Wikipédia corrompue :")
            raise RuntimeError("La réponse de Wikipédia est invalide.") from e
        except Exception as e:
            logger.exception("Erreur lors du traitement Wikipédia :")
            raise RuntimeError(f"Erreur lors du traitement Wikipédia : {str(e)}") from e

    @staticmethod
    def get_marker_executable() -> str | None:
        """Localise l'exécutable marker_single sur le système ou dans les dossiers d'outils AnkiForge."""
        # 1. Recherche dans le PATH système
        exe = shutil.which("marker_single")
        if exe:
            return exe
        # 2. Recherche dans les dossiers d'outils AnkiForge (environnement actif + repli prod)
        from ankiforge.utils.paths import get_tools_search_dirs

        for tools_dir in get_tools_search_dirs():
            candidates = [
                tools_dir / "bin" / "marker_single",
                tools_dir / "Scripts" / "marker_single.exe",
                tools_dir / "marker_single",
                tools_dir / "marker_single.exe",
            ]
            for c in candidates:
                if c.exists() and os.access(c, os.X_OK):
                    return str(c)
        return None

    @classmethod
    def is_marker_available(cls) -> bool:
        """Indique si le moteur OCR Deep Learning Marker est disponible sur la machine."""
        return cls.get_marker_executable() is not None

    def _parse_pdf_with_pypdf(self, file_path: str | Path, progress_callback: Any = None, check_cancel: Any = None) -> str:
        """Extraction rapide native via pypdf (sans dépendances GPU/Torch lourdes)."""
        from pypdf import PdfReader

        if progress_callback:
            progress_callback("Extraction PDF native en cours (pypdf)...")

        reader = PdfReader(str(file_path))
        num_pages = len(reader.pages)
        pages_text: list[str] = []

        for i, page in enumerate(reader.pages):
            if check_cancel and check_cancel():
                raise InterruptedError("Extraction annulée par l'utilisateur.")

            text = (page.extract_text() or "").strip()
            if text:
                pages_text.append(f"## Page {i + 1}\n\n{text}")

            if progress_callback:
                progress_callback(f"Lecture de la page {i + 1} / {num_pages}...")

        if not pages_text:
            raise ValueError("Aucun texte extractible trouvé dans ce fichier PDF (il s'agit peut-être d'un document scanné/image nécessitant Marker OCR).")

        return "\n\n[SPLIT]\n\n".join(pages_text)

    def _parse_pdf_with_marker(self, file_path: str | Path, progress_callback: Any = None, check_cancel: Any = None) -> str:
        """Extraction Deep Learning via Marker pour un LaTeX le plus proche de la réalité."""
        with tempfile.TemporaryDirectory() as temp_dir_str:
            temp_dir = Path(temp_dir_str)

            executable = self.get_marker_executable()
            if not executable:
                raise FileNotFoundError("L'outil Marker n'est pas installé ou introuvable dans le PATH.")

            cmd = [executable, str(file_path), "--output_dir", str(temp_dir), "--paginate_output"]

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
                    shell=False,  # nosec B603
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

    def _parse_pptx(self, file_path: Path, progress_callback: Any = None, check_cancel: Any = None) -> str:
        """Extrait le texte enrichi, les tableaux, les images et les notes d'orateur d'un PowerPoint."""
        if Presentation is None:
            raise RuntimeError("Le module python-pptx n'est pas installé. Lancez 'uv add python-pptx'")

        from ankiforge.services.parsing.pptx_parser import PptxParser

        parser = PptxParser(media_manager=self.media_manager)
        return parser.parse(file_path, progress_callback=progress_callback, check_cancel=check_cancel)

    def _parse_epub(self, file_path: Path, progress_callback: Any = None, check_cancel: Any = None) -> str:
        """Extrait le texte structuré, les formules MathML et les images d'un fichier EPUB."""
        from ankiforge.services.parsing.epub_parser import EpubParser

        parser = EpubParser(media_manager=self.media_manager)
        return parser.parse(file_path, progress_callback=progress_callback, check_cancel=check_cancel)

    def _parse_audio(self, file_path: Path, progress_callback: Any = None, check_cancel: Any = None) -> str:
        """Transcrit et extrait le texte horodaté d'un fichier audio (cours, podcast)."""
        from ankiforge.services.parsing.audio_parser import AudioParser

        parser = AudioParser(media_manager=self.media_manager)
        return parser.parse(file_path, progress_callback=progress_callback, check_cancel=check_cancel)

    @staticmethod
    def _parse_text(file_path: Path) -> str:
        """
        Lit un fichier texte brut ou Markdown.

        Args:
            file_path (Path): Chemin vers le fichier.

        Returns:
            str: Le contenu du fichier.
        """
        return file_path.read_text(encoding="utf-8")
