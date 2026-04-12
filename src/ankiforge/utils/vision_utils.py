import base64
import logging
import mimetypes
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Regex pour trouver les images Markdown : ![alt](media/mon_image.jpg)
MD_IMAGE_REGEX = re.compile(r"!\[.*?\]\((.*?)\)")
# Regex pour trouver les images HTML : <img src="media/mon_image.jpg">
HTML_IMAGE_REGEX = re.compile(r'<img[^>]+src=["\'](.*?)["\']', re.IGNORECASE)


def strip_image_tags(text: str) -> str:
    """
    Supprime toutes les balises images (Markdown et HTML) d'un texte.
    Utilisé quand l'utilisateur désactive la fonction Vision pour économiser des tokens.
    """
    clean_text = re.sub(MD_IMAGE_REGEX, "[IMAGE IGNORÉE]", text)
    clean_text = re.sub(HTML_IMAGE_REGEX, "[IMAGE IGNORÉE]", clean_text)
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


def prepare_multimodal_payload(text: str, media_dir: Path) -> list[dict[str, Any]]:
    """
    Scanne le texte, extrait les images, les convertit en Base64,
    et construit le payload JSON standardisé (format OpenAI/Anthropic).
    """
    images_found: list[str] = []

    # 1. Extraction des chemins d'images (Markdown + HTML)
    for match in MD_IMAGE_REGEX.finditer(text):
        images_found.append(match.group(1))
    for match in HTML_IMAGE_REGEX.finditer(text):
        images_found.append(match.group(1))

    # 2. Nettoyage du texte (On remplace les images par des marqueurs pour que l'IA comprenne la structure)
    clean_text = strip_image_tags(text)

    # 3. Construction du Payload standard
    # Le premier élément est toujours le texte
    payload: list[dict[str, Any]] = [{"type": "text", "text": clean_text}]

    # 4. Ajout des images en Base64
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
            # Déduction du type MIME (image/jpeg, image/png...)
            mime_type, _ = mimetypes.guess_type(str(full_path))
            if not mime_type:
                mime_type = "image/jpeg"  # Fallback par défaut

            payload.append({"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{base64_str}"}})
            processed_images.add(file_name)

    # Si aucune image n'a été trouvée/chargée, on renvoie simplement une liste avec un bloc texte
    return payload
