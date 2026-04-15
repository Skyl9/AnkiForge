import hashlib
import re
import shutil
from pathlib import Path

from ankiforge.utils.paths import get_app_data_dir


class MediaManager:
    """Gère l'importation, le hachage et le formatage HTML des images extraites."""

    def __init__(self):
        # On s'assure que le dossier "data/media" existe
        self.base_dir = get_app_data_dir()
        self.media_dir = self.base_dir / "media"
        self.media_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _calculate_md5(file_path: str) -> str:
        """Calcule l'empreinte MD5 d'un fichier pour garantir un nom unique."""
        hash_md5 = hashlib.md5(usedforsecurity=False)
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def process_extracted_folder(self, source_folder: str, markdown_content: str) -> str:
        """
        1. Trouve toutes les images dans le dossier source (généré par Marker).
        2. Les copie dans data/media/ en les renommant avec leur hash MD5.
        3. Remplace les liens Markdown bruts par des balises HTML <img> compatibles Anki.

        Retourne le Markdown modifié.
        """
        source_path = Path(source_folder)
        if not source_path.exists() or not source_path.is_dir():
            return markdown_content

        # Dictionnaire pour garder la trace des renommages : { "ancien_nom.jpeg" : "hash123.jpeg" }
        image_mapping = {}

        # 1. Traitement des fichiers images
        for file in source_path.iterdir():
            if file.is_file() and file.suffix.lower() in [".jpeg", ".jpg", ".png", ".webp", ".gif"]:
                # Calcul du nouveau nom (Hash + Extension)
                file_hash = self._calculate_md5(str(file))
                new_filename = f"{file_hash}{file.suffix.lower()}"

                # Chemin final dans data/media/
                destination_path = self.media_dir / new_filename

                # Copie du fichier s'il n'existe pas déjà (évite les doublons parfaits)
                if not destination_path.exists():
                    shutil.copy2(str(file), destination_path)

                # On enregistre la correspondance
                image_mapping[file.name] = new_filename

        # 2. Remplacement dans le texte Markdown
        # Marker génère généralement des liens comme ça : ![Description](_page_1_Figure_2.jpeg)
        modified_markdown = markdown_content

        for old_name, new_name in image_mapping.items():
            # Création de la balise HTML Anki-friendly
            html_img_tag = f'<img src="{new_name}">'

            # Recherche du pattern Markdown spécifique à cette image
            # Ex: ![N'importe quelle description](old_name)
            pattern = r"!\[.*?\]\(" + str(re.escape(old_name)) + r"\)"

            # Remplacement dans le texte
            modified_markdown = re.sub(pattern, html_img_tag, modified_markdown)

            # Remplacement de sécurité au cas où l'image serait citée simplement par son nom
            # sans la syntaxe markdown complète
            modified_markdown = modified_markdown.replace(old_name, new_name)

        return modified_markdown

    def clean_orphaned_media(self) -> int:
        """
        Supprime physiquement les fichiers médias qui ne sont plus utilisés.

        Analyse toutes les versions de notes en base de données pour identifier
        les images référencées et nettoie les fichiers orphelins sur le disque.

        Returns:
            int: Le nombre de fichiers supprimés.
        """
        from ankiforge.database.models import NoteVersionModel

        # 1. Lister tous les médias réellement utilisés en base
        used_media = set()

        # On itère sur toutes les versions de notes (actives et inactives)
        for version in NoteVersionModel.select(NoteVersionModel.content):
            # La même regex que tu utilises dans ton ExportManager
            matches = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', version.content)
            used_media.update(matches)

        # 2. Comparer avec les fichiers physiques et supprimer les orphelins
        deleted_count = 0
        if self.media_dir.exists():
            for file_path in self.media_dir.iterdir():
                if file_path.is_file() and file_path.name not in used_media:
                    try:
                        file_path.unlink()  # Supprime le fichier du disque
                        deleted_count += 1
                    except OSError:
                        pass  # Fichier verrouillé par le système, on l'ignorera pour cette fois

        return deleted_count
