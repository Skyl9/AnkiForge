"""Extraction et encodage des images (Markdown et HTML) pour le traitement Vision des documents."""

import base64
import logging
import mimetypes
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Regex pour trouver les images Markdown : ![alt](media/mon_image.jpg)
MD_IMAGE_REGEX = re.compile(r"!\[.*?\]\((.*?)\)")


def strip_image_tags(text: str) -> str:
    """Supprime toutes les balises images (Markdown et HTML) d'un texte.

    Utilisé quand l'utilisateur désactive la fonction Vision pour économiser des tokens.
    """
    # 1. Nettoyage Markdown
    clean_text = re.sub(MD_IMAGE_REGEX, "[IMAGE IGNORÉE]", text)

    # 2. Nettoyage HTML via BeautifulSoup
    if "<img" in clean_text.lower():
        soup = BeautifulSoup(clean_text, "html.parser")
        for img in soup.find_all("img"):
            img.replace_with("[IMAGE IGNORÉE]")
        # On utilise decode_contents() pour ne pas rajouter les tags html/body si BeautifulSoup les a créés
        clean_text = soup.decode_contents()

    return clean_text


def _encode_image_base64(image_path: Path) -> str | None:
    """Lit une image sur le disque et la convertit en chaîne Base64."""
    try:
        if not image_path.exists():
            logger.warning(f"Image introuvable sur le disque : {image_path}")
            return None
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")
    except Exception as e:
        logger.error(f"Erreur lors de la lecture de l'image {image_path}: {e}")
        return None


def prepare_multimodal_payload(
    text: str,
    media_dir: Path,
    extra_images: Sequence[dict[str, Any] | Path | str] | None = None,
) -> list[dict[str, Any]]:
    """Prépare un payload compatible avec les APIs de vision (OpenAI, Gemini).

    Extrait les images citées dans le texte et intègre les images additionnelles
    fournies (ex: planches d'album sélectionnées), les convertit en base64
    et construit une structure de message multimodal.

    Args:
        text: Texte source contenant des balises images.
        media_dir: Dossier racine où sont stockés les fichiers physiques.
        extra_images: Images explicites additionnelles (dict image_url ou chemins).

    Returns:
        Une liste d'objets (texte + images base64) pour le fournisseur IA.
    """
    images_found: list[str] = []

    # 1. Extraction des chemins d'images Markdown
    for match in MD_IMAGE_REGEX.finditer(text):
        images_found.append(match.group(1))

    # 2. Extraction des chemins d'images HTML via BeautifulSoup
    if "<img" in text.lower():
        soup = BeautifulSoup(text, "html.parser")
        for img in soup.find_all("img"):
            src = img.get("src")
            if src:
                images_found.append(str(src))

    # 3. Nettoyage du texte (On remplace les images par des marqueurs pour que l'IA comprenne la structure)
    clean_text = strip_image_tags(text)

    # 4. Construction du Payload standard
    # Le premier élément est toujours le texte
    payload: list[dict[str, Any]] = [{"type": "text", "text": clean_text}]

    # 5. Ajout des images en Base64
    # On utilise un Set pour éviter d'envoyer la même image deux fois si elle est dupliquée dans le texte
    processed_images = set()

    for img_path_str in images_found:
        # Nettoyage du chemin (parfois les parsers rajoutent des ./ ou des %20)
        from urllib.parse import unquote

        clean_path_str = unquote(img_path_str).replace("\\", "/")

        # Si le chemin contient un dossier (ex: 'media/image.jpg'), on ne garde que le nom du fichier
        file_name = clean_path_str.split("/")[-1]

        if file_name in processed_images:
            continue

        full_path = media_dir / file_name
        base64_str = _encode_image_base64(full_path)

        if base64_str:
            mime_type, _ = mimetypes.guess_type(str(full_path))
            if not mime_type:
                mime_type = "image/jpeg"  # Fallback par défaut

            payload.append({"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{base64_str}"}})
            processed_images.add(file_name)

    # 6. Ajout des images transmises explicitement (ex: planches d'album sélectionnées)
    if extra_images:
        for item in extra_images:
            if isinstance(item, dict) and item.get("type") == "image_url":
                payload.append(item)
            elif isinstance(item, (str, Path)):
                p = Path(item)
                target_path = p if p.is_absolute() and p.exists() else (media_dir / p.name)
                b64 = _encode_image_base64(target_path)
                if b64:
                    mtype, _ = mimetypes.guess_type(str(target_path))
                    if not mtype:
                        mtype = "image/png" if target_path.suffix.lower() == ".png" else "image/jpeg"
                    payload.append({"type": "image_url", "image_url": {"url": f"data:{mtype};base64,{b64}"}})

    # Si aucune image n'a été trouvée/chargée, on renvoie simplement une liste avec un bloc texte
    return payload
