"""Service de parsage de livres numériques EPUB (EPUB 2 et EPUB 3).

Extrait le texte sémantique structuré au format Markdown, convertit les équations
MathML en LaTeX KaTeX ($...$ / $$...$$), extrait les images intégrées dans le MediaManager,
et découpe le document par chapitre avec des marqueurs de page compatibles ChunkingService.
"""

import logging
import mimetypes
import posixpath
import re
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import defusedxml.ElementTree as ET
import markdownify
from bs4 import BeautifulSoup, Tag

from ankiforge.services.cards.media_manager import MediaManager

logger = logging.getLogger(__name__)

# Table de correspondance des symboles mathématiques usuels vers LaTeX
MATH_UNICODE_TO_LATEX: dict[str, str] = {
    "×": r"\times",
    "÷": r"\div",
    "±": r"\pm",
    "∓": r"\mp",
    "≤": r"\le",
    "≥": r"\ge",
    "≠": r"\ne",
    "≈": r"\approx",
    "≡": r"\equiv",
    "∑": r"\sum",
    "∏": r"\prod",
    "∫": r"\int",
    "∂": r"\partial",
    "∞": r"\infty",
    "√": r"\sqrt",
    "∈": r"\in",
    "∉": r"\notin",
    "⊂": r"\subset",
    "⊆": r"\subseteq",
    "∪": r"\cup",
    "∩": r"\cap",
    "→": r"\to",
    "⇒": r"\implies",
    "↔": r"\leftrightarrow",
    "⇔": r"\iff",
    "α": r"\alpha",
    "β": r"\beta",
    "γ": r"\gamma",
    "δ": r"\delta",
    "ε": r"\varepsilon",
    "θ": r"\theta",
    "λ": r"\lambda",
    "μ": r"\mu",
    "π": r"\pi",
    "σ": r"\sigma",
    "φ": r"\phi",
    "ω": r"\omega",
    "Δ": r"\Delta",
    "Ω": r"\Omega",
    "Σ": r"\Sigma",
    "Π": r"\Pi",
}


def convert_mathml_to_latex(math_tag: Tag) -> str:
    """Convertit récursivement un fragment MathML en syntaxe LaTeX pour KaTeX.

    Prend en charge :
    - Les balises d'annotation LaTeX existantes (application/x-tex).
    - Les attributs alt ou alttext.
    - Les fractions (mfrac), racines (msqrt, mroot), indices et exposants (msup, msub, msubsup).
    - Les opérateurs, délimiteurs (mfenced), vecteurs/accents (mover, munder, munderover), et tableaux (mtable).
    """
    # 1. Vérification d'une annotation LaTeX pré-existante
    ann = math_tag.find("annotation", attrs={"encoding": lambda v: bool(v and "tex" in str(v).lower())})
    if ann and ann.string:
        return ann.string.strip()

    # 2. Vérification des attributs alt / alttext
    if math_tag.get("alt"):
        return str(math_tag["alt"]).strip()
    if math_tag.get("alttext"):
        return str(math_tag["alttext"]).strip()

    def _convert(node: Any) -> str:
        if isinstance(node, str):
            clean = node.strip()
            return MATH_UNICODE_TO_LATEX.get(clean, clean)

        if not hasattr(node, "name") or not node.name:
            return ""

        tag = node.name.lower()
        children = [c for c in node.children if not (isinstance(c, str) and not c.strip())]

        if tag in ("math", "mrow", "mstyle", "semantics", "mpadded", "mphantom"):
            return " ".join(filter(None, (_convert(c) for c in children)))

        if tag == "mi":
            t = node.get_text(strip=True)
            return MATH_UNICODE_TO_LATEX.get(t, t)

        if tag == "mn":
            return node.get_text(strip=True)

        if tag == "mo":
            t = node.get_text(strip=True)
            return MATH_UNICODE_TO_LATEX.get(t, t)

        if tag == "mtext":
            text_val = node.get_text()
            return r"\text{" + text_val + "}"

        if tag == "mspace":
            return r"\quad "

        if tag == "mfrac":
            num = _convert(children[0]) if len(children) > 0 else ""
            den = _convert(children[1]) if len(children) > 1 else ""
            return r"\frac{" + num + "}{" + den + "}"

        if tag == "msqrt":
            inner = " ".join(filter(None, (_convert(c) for c in children)))
            return r"\sqrt{" + inner + "}"

        if tag == "mroot":
            base = _convert(children[0]) if len(children) > 0 else ""
            index = _convert(children[1]) if len(children) > 1 else ""
            return r"\sqrt[" + index + "]{" + base + "}"

        if tag == "msup":
            base = _convert(children[0]) if len(children) > 0 else ""
            sup = _convert(children[1]) if len(children) > 1 else ""
            return "{" + base + "}^{" + sup + "}"

        if tag == "msub":
            base = _convert(children[0]) if len(children) > 0 else ""
            sub = _convert(children[1]) if len(children) > 1 else ""
            return "{" + base + "}_{" + sub + "}"

        if tag == "msubsup":
            base = _convert(children[0]) if len(children) > 0 else ""
            sub = _convert(children[1]) if len(children) > 1 else ""
            sup = _convert(children[2]) if len(children) > 2 else ""
            return "{" + base + "}_{" + sub + "}^{" + sup + "}"

        if tag == "munder":
            base = _convert(children[0]) if len(children) > 0 else ""
            under = _convert(children[1]) if len(children) > 1 else ""
            return r"\underset{" + under + "}{" + base + "}"

        if tag == "mover":
            base = _convert(children[0]) if len(children) > 0 else ""
            over = _convert(children[1]) if len(children) > 1 else ""
            if over in ("→", "->", r"\to"):
                return r"\vec{" + base + "}"
            return r"\overset{" + over + "}{" + base + "}"

        if tag == "munderover":
            base = _convert(children[0]) if len(children) > 0 else ""
            under = _convert(children[1]) if len(children) > 1 else ""
            over = _convert(children[2]) if len(children) > 2 else ""
            return "{" + base + "}_{" + under + "}^{" + over + "}"

        if tag == "mfenced":
            open_delim = str(node.get("open", "("))
            close_delim = str(node.get("close", ")"))
            inner = " ".join(filter(None, (_convert(c) for c in children)))
            return r"\left" + open_delim + " " + inner + r" \right" + close_delim

        if tag == "mtable":
            rows: list[str] = []
            for r in children:
                if hasattr(r, "name") and r.name and r.name.lower() == "mtr":
                    cols = [_convert(d) for d in r.children if not (isinstance(d, str) and not d.strip())]
                    rows.append(" & ".join(cols))
            return r"\begin{matrix} " + r" \\ ".join(rows) + r" \end{matrix}"

        return " ".join(filter(None, (_convert(c) for c in children)))

    converted = _convert(math_tag).strip()
    return converted


class EpubParser:
    """Parseur de livres numériques EPUB (EPUB 2 et EPUB 3).

    Extrait la structure des chapitres, le texte sémantique Markdown,
    les formules MathML converties en LaTeX, et les images intégrées.
    """

    def __init__(self, media_manager: MediaManager | None = None) -> None:
        """Initialise le parseur avec un gestionnaire de médias pour l'archivage d'images."""
        self.media_manager = media_manager or MediaManager()

    def parse(
        self,
        epub_path: str | Path,
        progress_callback: Callable[[str], None] | None = None,
        check_cancel: Callable[[], bool] | None = None,
    ) -> str:
        """Extrait l'ensemble des chapitres d'un fichier EPUB en Markdown paginé.

        Args:
            epub_path: Chemin du fichier .epub sur le disque.
            progress_callback: Callback optionnel pour signaler l'avancement.
            check_cancel: Callback optionnel pour vérifier si l'annulation a été demandée.

        Returns:
            Le contenu complet au format Markdown avec marqueurs de page <!-- PAGE: N -->.
        """
        path_obj = Path(epub_path)
        if not path_obj.exists():
            raise FileNotFoundError(f"Le fichier EPUB '{path_obj}' est introuvable.")

        logger.info("Début du parsage EPUB : %s", path_obj.name)
        with zipfile.ZipFile(str(path_obj), "r") as zf:
            # 1. Localiser le fichier OPF via META-INF/container.xml
            opf_path = self._locate_opf_path(zf)
            opf_dir = posixpath.dirname(opf_path)

            # 2. Parser le fichier OPF (Métadonnées, Manifeste, Spine)
            metadata, manifest, spine_ids = self._parse_opf(zf, opf_path, opf_dir)

            # 3. Parser la table des matières (TOC)
            toc_map = self._parse_toc(zf, manifest, opf_dir)

            # 4. Parcourir les éléments du spine dans l'ordre de lecture
            total_items = len(spine_ids)
            chapter_outputs: list[str] = []
            book_title = metadata.get("title", path_obj.stem)

            for idx, item_id in enumerate(spine_ids, start=1):
                if check_cancel and check_cancel():
                    logger.warning("Extraction EPUB interrompue par l'utilisateur.")
                    break

                item_info = manifest.get(item_id)
                if not item_info:
                    continue

                item_href = item_info["href"]
                # Ne traiter que les fichiers textuels XHTML/HTML
                media_type = item_info.get("media-type", "").lower()
                if "html" not in media_type and not item_href.endswith((".xhtml", ".html", ".htm")):
                    continue

                if progress_callback:
                    progress_callback(f"Analyse du chapitre {idx}/{total_items} : {posixpath.basename(item_href)}...")

                try:
                    raw_bytes = zf.read(item_href)
                except KeyError:
                    logger.warning("Fichier de chapitre introuvable dans l'archive : %s", item_href)
                    continue

                # Décodage XHTML
                try:
                    html_content = raw_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    html_content = raw_bytes.decode("latin-1", errors="replace")

                chapter_dir = posixpath.dirname(item_href)
                chapter_title = toc_map.get(item_href) or toc_map.get(posixpath.basename(item_href))

                chapter_md = self._process_chapter_html(
                    html_content=html_content,
                    chapter_dir=chapter_dir,
                    zip_file=zf,
                    fallback_title=chapter_title,
                )

                if chapter_md.strip():
                    # Formatage sous forme de page / chapitre paginé pour ChunkingService
                    chunk_header = f"<!-- PAGE: {len(chapter_outputs) + 1} -->"
                    chapter_outputs.append(f"{chunk_header}\n\n{chapter_md.strip()}")

            if not chapter_outputs:
                logger.warning("Aucun texte exploitable extrait de l'EPUB : %s", path_obj.name)
                return f"# {book_title}\n\n*Document vide ou non pris en charge.*"

            logger.info(
                "Extraction EPUB achevée avec succès : %d chapitres extraits pour '%s'",
                len(chapter_outputs),
                book_title,
            )
            return "\n\n[SPLIT]\n\n".join(chapter_outputs)

    def _locate_opf_path(self, zf: zipfile.ZipFile) -> str:
        """Localise le chemin relatif du fichier .opf dans l'archive ZIP."""
        container_path = "META-INF/container.xml"
        try:
            container_bytes = zf.read(container_path)
            root = ET.fromstring(container_bytes)
            # Recherche indépendante du namespace
            for elem in root.iter():
                if elem.tag.endswith("rootfile"):
                    full_path = elem.attrib.get("full-path")
                    if full_path:
                        return full_path.strip()
        except Exception as err:
            logger.debug("Échec lecture standard container.xml (%s), recherche directe de .opf", err)

        # Fallback : chercher le premier fichier .opf présent dans l'archive
        for name in zf.namelist():
            if name.lower().endswith(".opf"):
                return name

        raise ValueError("Archive EPUB invalide : impossible de trouver le fichier de manifeste .opf.")

    def _parse_opf(self, zf: zipfile.ZipFile, opf_path: str, opf_dir: str) -> tuple[dict[str, str], dict[str, dict[str, str]], list[str]]:
        """Parse le fichier OPF pour en extraire métadonnées, manifest et spine."""
        opf_bytes = zf.read(opf_path)
        root = ET.fromstring(opf_bytes)

        metadata: dict[str, str] = {}
        manifest: dict[str, dict[str, str]] = {}
        spine_ids: list[str] = []

        for elem in root.iter():
            tag_lower = elem.tag.lower()
            if tag_lower.endswith("title") and elem.text and "title" not in metadata:
                metadata["title"] = elem.text.strip()
            elif tag_lower.endswith("creator") and elem.text and "creator" not in metadata:
                metadata["creator"] = elem.text.strip()
            elif tag_lower.endswith("language") and elem.text and "language" not in metadata:
                metadata["language"] = elem.text.strip()

            elif tag_lower.endswith("item"):
                item_id = elem.attrib.get("id")
                href = elem.attrib.get("href")
                if item_id and href:
                    clean_href = unquote(href)
                    resolved_href = posixpath.normpath(posixpath.join(opf_dir, clean_href)) if opf_dir else clean_href
                    manifest[item_id] = {
                        "href": resolved_href,
                        "raw_href": clean_href,
                        "media-type": elem.attrib.get("media-type", ""),
                        "properties": elem.attrib.get("properties", ""),
                    }

            elif tag_lower.endswith("itemref"):
                idref = elem.attrib.get("idref")
                if idref:
                    spine_ids.append(idref)

        return metadata, manifest, spine_ids

    def _parse_toc(self, zf: zipfile.ZipFile, manifest: dict[str, dict[str, str]], opf_dir: str) -> dict[str, str]:
        """Tente d'extraire la table des matières depuis nav.xhtml (EPUB 3) ou toc.ncx (EPUB 2)."""
        toc_map: dict[str, str] = {}

        # 1. Tenter EPUB 3 Navigation Document (properties="nav")
        nav_item = next(
            (item for item in manifest.values() if "nav" in item.get("properties", "").split()),
            None,
        )
        if nav_item:
            try:
                nav_bytes = zf.read(nav_item["href"])
                soup = BeautifulSoup(nav_bytes, "html.parser")
                nav_tag = soup.find("nav", attrs={"epub:type": "toc"}) or soup.find("nav")
                if nav_tag:
                    for a_tag in nav_tag.find_all("a", href=True):
                        title = a_tag.get_text(strip=True)
                        raw_href = unquote(str(a_tag["href"])).split("#")[0]
                        nav_dir = posixpath.dirname(nav_item["href"])
                        resolved = posixpath.normpath(posixpath.join(nav_dir, raw_href)) if nav_dir else raw_href
                        if title and resolved not in toc_map:
                            toc_map[resolved] = title
                            toc_map[posixpath.basename(resolved)] = title
            except Exception as err:
                logger.debug("Impossible de parser nav.xhtml EPUB 3 : %s", err)

        if toc_map:
            return toc_map

        # 2. Tenter EPUB 2 NCX Document (media-type="application/x-dtbncx+xml")
        ncx_item = next(
            (item for item in manifest.values() if "ncx" in item.get("media-type", "").lower()),
            None,
        )
        if ncx_item:
            try:
                ncx_bytes = zf.read(ncx_item["href"])
                root = ET.fromstring(ncx_bytes)
                ncx_dir = posixpath.dirname(ncx_item["href"])
                for nav_pt in root.iter():
                    if nav_pt.tag.endswith("navPoint"):
                        text_elem = nav_pt.find(".//{*}text")
                        content_elem = nav_pt.find(".//{*}content")
                        if text_elem is not None and text_elem.text and content_elem is not None:
                            title = text_elem.text.strip()
                            raw_src = unquote(content_elem.attrib.get("src", "")).split("#")[0]
                            resolved = posixpath.normpath(posixpath.join(ncx_dir, raw_src)) if ncx_dir else raw_src
                            if title and resolved not in toc_map:
                                toc_map[resolved] = title
                                toc_map[posixpath.basename(resolved)] = title
            except Exception as err:
                logger.debug("Impossible de parser toc.ncx EPUB 2 : %s", err)

        return toc_map

    def _process_chapter_html(
        self,
        html_content: str,
        chapter_dir: str,
        zip_file: zipfile.ZipFile,
        fallback_title: str | None = None,
    ) -> str:
        """Traite le code HTML d'un chapitre : extrait images, convertit MathML et formate en Markdown."""
        soup = BeautifulSoup(html_content, "html.parser")

        # 1. Détection du titre du chapitre si non fourni par la TOC
        effective_title = fallback_title
        if not effective_title:
            h1 = soup.find("h1")
            if h1 and h1.get_text(strip=True):
                effective_title = h1.get_text(strip=True)
            else:
                title_tag = soup.find("title")
                if title_tag and title_tag.get_text(strip=True):
                    effective_title = title_tag.get_text(strip=True)

        # 2. Nettoyage des éléments non désirés (scripts, styles)
        for junk in soup(["script", "style", "noscript"]):
            junk.decompose()

        # 3. Extraction et archivage des images
        for img in soup.find_all(["img", "image"]):
            src = img.get("src") or img.get("xlink:href") or img.get("href")
            if not src or str(src).startswith("data:"):
                continue

            src_clean = unquote(str(src)).split("#")[0]
            img_zip_path = posixpath.normpath(posixpath.join(chapter_dir, src_clean)) if chapter_dir else src_clean

            try:
                img_data = zip_file.read(img_zip_path)
                original_name = posixpath.basename(img_zip_path)
                mime_type, _ = mimetypes.guess_type(original_name)
                media = self.media_manager.store_media_bytes(
                    data=img_data,
                    original_name=original_name,
                    mime_type=mime_type or "image/png",
                )
                if media:
                    img["src"] = media.filename
                    if "xlink:href" in img.attrs:
                        del img["xlink:href"]
            except KeyError:
                logger.debug("Image introuvable dans l'archive EPUB : %s", img_zip_path)

        # 4. Conversion des formules MathML en LaTeX KaTeX
        for math_tag in soup.find_all("math"):
            latex_formula = convert_mathml_to_latex(math_tag)
            is_block = math_tag.get("display") == "block" or (math_tag.parent and "display" in str(math_tag.parent.get("class", "")))
            if latex_formula:
                replacement = f" $${latex_formula}$$ " if is_block else f" ${latex_formula}$ "
                math_tag.replace_with(replacement)
            else:
                math_tag.decompose()

        # 5. Conversion HTML en Markdown avec markdownify
        body = soup.find("body") or soup
        md_text = markdownify.markdownify(
            str(body),
            heading_style="ATX",
            strip=["script", "style"],
        )

        # Nettoyage des lignes vides consécutives
        cleaned_md = re.sub(r"\n{3,}", "\n\n", md_text).strip()

        # 6. S'assurer qu'un titre de niveau 1 (# Titre) commence le chapitre
        if effective_title and not cleaned_md.startswith("# "):
            cleaned_md = f"# {effective_title}\n\n{cleaned_md}"

        return cleaned_md
