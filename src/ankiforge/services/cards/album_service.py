import datetime
import logging
import re
from collections.abc import Sequence
from pathlib import Path

from PIL import ExifTags, Image

from ankiforge.database.base import db
from ankiforge.database.models import DocumentModel, DocumentPageModel, FolderModel
from ankiforge.services.cards.media_manager import MediaManager

logger = logging.getLogger(__name__)


def natural_sort_key(file_path: str | Path) -> list[int | str]:
    """Clé de tri alphanumérique naturel pour classer logiquement les pages (ex: page_1 < page_2 < page_10)."""
    name = Path(file_path).name
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", name)]


def extract_exif_timestamp(file_path: str | Path) -> datetime.datetime | None:
    """
    Extrait la date et l'heure de capture depuis les métadonnées EXIF (DateTimeOriginal ou DateTime).
    Retourne None si l'image ne contient pas de métadonnées exploitables ou en cas d'erreur.
    """
    try:
        with Image.open(file_path) as img:
            exif_data = img.getexif()
            if not exif_data:
                return None

            # Recherche des tags DateTimeOriginal (36867) ou DateTime (306)
            date_str = exif_data.get(306)  # DateTime standard

            # Vérification dans l'IFD Exif (0x8769) pour DateTimeOriginal (0x9003 = 36867)
            exif_ifd = exif_data.get_ifd(ExifTags.IFD.Exif) if hasattr(exif_data, "get_ifd") else {}
            if exif_ifd and 36867 in exif_ifd:
                date_str = exif_ifd[36867]

            if date_str and isinstance(date_str, str):
                # Format standard EXIF : 'YYYY:MM:DD HH:MM:SS'
                clean_str = date_str.strip().replace("\x00", "")
                return datetime.datetime.strptime(clean_str, "%Y:%m:%d %H:%M:%S")
    except Exception as err:
        logger.debug("Impossible d'extraire les EXIF de %s : %s", file_path, err)
    return None


class AlbumService:
    """Service métier de gestion des Albums d'images et Livres scannés."""

    def __init__(self, media_manager: MediaManager | None = None) -> None:
        self.media_manager = media_manager or MediaManager()

    def sort_images(
        self,
        image_paths: Sequence[str | Path],
        mode: str = "natural",
        method: str | None = None,
    ) -> list[Path]:
        """
        Trie une liste de chemins d'images selon le mode spécifié :
        - 'natural' : tri alphanumérique naturel (page_1, page_2, page_10)
        - 'exif' : tri par date de prise de vue EXIF (avec repli sur mtime puis tri naturel)
        - 'none' : conserve l'ordre fourni
        """
        active_mode = method if method is not None else mode
        paths = [Path(p) for p in image_paths]
        if active_mode == "none":
            return paths

        if active_mode == "exif":

            def _exif_key(p: Path) -> tuple[float, list[int | str]]:
                exif_dt = extract_exif_timestamp(p)
                if exif_dt:
                    ts = exif_dt.timestamp()
                else:
                    try:
                        ts = p.stat().st_mtime
                    except OSError:
                        ts = 0.0
                return (ts, natural_sort_key(p))

            return sorted(paths, key=_exif_key)

        # Mode "natural" par défaut
        return sorted(paths, key=natural_sort_key)

    def create_album_from_images(
        self,
        title: str,
        image_paths: Sequence[str | Path],
        folder: FolderModel | None = None,
        sort_mode: str = "natural",
        folder_id: int | None = None,
        sort_method: str | None = None,
    ) -> DocumentModel:
        """
        Crée un DocumentModel de type 'album' et archive les images dans MediaModel
        en générant les DocumentPageModel ordonnés.
        """
        if not image_paths:
            raise ValueError("Impossible de créer un album sans image.")

        clean_title = title.strip()
        if not clean_title:
            raise ValueError("Le titre de l'album ne peut pas être vide.")

        target_folder = folder
        if target_folder is None and folder_id is not None:
            target_folder = FolderModel.get_or_none(FolderModel.id == folder_id)

        active_sort = sort_method if sort_method is not None else sort_mode
        sorted_paths = self.sort_images(image_paths, mode=active_sort)

        with db.atomic():
            doc = DocumentModel.create(
                title=clean_title,
                file_type="album",
                total_pages=len(sorted_paths),
                folder=target_folder,
            )

            for idx, img_path in enumerate(sorted_paths):
                media = self.media_manager.store_document_source(str(img_path))
                if not media:
                    raise RuntimeError(f"Échec de l'archivage du média : {img_path}")

                DocumentPageModel.create(
                    document=doc,
                    media=media,
                    page_number=idx + 1,
                    rotation=0,
                    status="ready",
                )

            logger.info("Album '%s' créé avec succès (%d pages)", clean_title, len(sorted_paths))
            return doc

    def get_album_pages(self, document_id: int) -> list[DocumentPageModel]:
        """Retourne les pages ordonnées d'un album."""
        return list(DocumentPageModel.select().where(DocumentPageModel.document == document_id).order_by(DocumentPageModel.page_number.asc()))

    def rotate_page(self, page_id: int, degrees: int = 90) -> DocumentPageModel:
        """Fait pivoter une page par incrément de 90° (0°, 90°, 180°, 270°)."""
        with db.atomic():
            page = DocumentPageModel.get_by_id(page_id)
            page.rotation = (page.rotation + degrees) % 360
            page.save()
            logger.info("Page %d (ID %d) pivotée à %d°", page.page_number, page.id, page.rotation)
            return page

    def reorder_pages(self, document_id: int, new_page_ids_order: Sequence[int]) -> list[DocumentPageModel]:
        """
        Réordonne les pages d'un album selon la liste ordonnée des IDs fournie.
        Utilise une mise à jour temporaire négative pour éviter tout conflit sur l'index UNIQUE(document, page_number).
        """
        with db.atomic():
            existing_pages = {p.id: p for p in self.get_album_pages(document_id)}
            if set(new_page_ids_order) != set(existing_pages.keys()):
                raise ValueError("La liste des IDs ne correspond pas aux pages de l'album.")

            # Étape 1 : Passer en négatif temporaire pour libérer les contraintes d'unicité
            for temp_idx, page_id in enumerate(new_page_ids_order):
                DocumentPageModel.update(page_number=-(temp_idx + 1)).where(DocumentPageModel.id == page_id).execute()

            # Étape 2 : Assigner les numéros de page définitifs 1-indexed
            for final_idx, page_id in enumerate(new_page_ids_order):
                DocumentPageModel.update(page_number=final_idx + 1).where(DocumentPageModel.id == page_id).execute()

            logger.info("Album %d réordonné (%d pages)", document_id, len(new_page_ids_order))
            return self.get_album_pages(document_id)

    def delete_page(self, page_id: int) -> None:
        """
        Supprime une page de l'album, renumérote les pages restantes de façon contiguë (1..N),
        et met à jour total_pages du DocumentModel.
        """
        with db.atomic():
            page = DocumentPageModel.get_by_id(page_id)
            document = page.document
            page.delete_instance()

            remaining_pages = self.get_album_pages(document.id)

            # Renumérotation en deux étapes (évite les conflits d'unicité)
            for temp_idx, p in enumerate(remaining_pages):
                DocumentPageModel.update(page_number=-(temp_idx + 1)).where(DocumentPageModel.id == p.id).execute()

            for final_idx, p in enumerate(remaining_pages):
                DocumentPageModel.update(page_number=final_idx + 1).where(DocumentPageModel.id == p.id).execute()

            document.total_pages = len(remaining_pages)
            document.save()
            logger.info(
                "Page ID %d supprimée de l'album %d. Pages restantes : %d",
                page_id,
                document.id,
                len(remaining_pages),
            )

    def add_pages_to_album(
        self,
        document_id: int,
        image_paths: Sequence[str | Path],
        insert_at: int | None = None,
    ) -> list[DocumentPageModel]:
        """
        Ajoute de nouvelles images à un album existant à la position spécifiée (1-indexed).
        Si insert_at est None, les images sont ajoutées à la fin.
        """
        if not image_paths:
            return []

        with db.atomic():
            doc = DocumentModel.get_by_id(document_id)
            existing_pages = self.get_album_pages(document_id)
            total_current = len(existing_pages)

            if insert_at is None or insert_at > total_current + 1:
                target_pos = total_current + 1
            elif insert_at < 1:
                target_pos = 1
            else:
                target_pos = insert_at

            # Décaler les pages existantes à partir de target_pos
            new_count = len(image_paths)
            new_order_pages: list[tuple[int, int]] = []

            for p in existing_pages:
                if p.page_number >= target_pos:
                    new_order_pages.append((p.id, p.page_number + new_count))
                else:
                    new_order_pages.append((p.id, p.page_number))

            # Application du décalage en 2 passes
            for temp_idx, (p_id, _) in enumerate(new_order_pages):
                DocumentPageModel.update(page_number=-(temp_idx + 1000)).where(DocumentPageModel.id == p_id).execute()

            for p_id, final_num in new_order_pages:
                DocumentPageModel.update(page_number=final_num).where(DocumentPageModel.id == p_id).execute()

            # Création des nouvelles pages
            created_pages: list[DocumentPageModel] = []
            for offset, img_path in enumerate(image_paths):
                media = self.media_manager.store_document_source(str(img_path))
                if not media:
                    raise RuntimeError(f"Échec de l'archivage du média : {img_path}")

                new_page = DocumentPageModel.create(
                    document=doc,
                    media=media,
                    page_number=target_pos + offset,
                    rotation=0,
                    status="ready",
                )
                created_pages.append(new_page)

            doc.total_pages = total_current + new_count
            doc.save()

            logger.info(
                "%d nouvelles pages ajoutées à l'album %d à la position %d",
                new_count,
                document_id,
                target_pos,
            )
            return created_pages

    def compile_album_to_pdf(
        self,
        document_id: int,
        output_path: str | Path | None = None,
    ) -> Path:
        """
        Compile toutes les pages de l'album en un fichier PDF de lecture unique,
        en appliquant fidèlement les rotations définies sur chaque page.
        """
        doc = DocumentModel.get_by_id(document_id)
        pages = self.get_album_pages(document_id)
        if not pages:
            raise ValueError(f"L'album {document_id} ne contient aucune page à compiler.")

        final_pdf_path = self.media_manager.media_dir / f"album_{doc.id}.pdf" if output_path is None else Path(output_path)

        final_pdf_path.parent.mkdir(parents=True, exist_ok=True)

        pil_images: list[Image.Image] = []
        try:
            for page in pages:
                media_file = self.media_manager.media_dir / page.media.filename
                if not media_file.exists():
                    raise FileNotFoundError(f"Fichier image manquant sur le disque : {media_file}")

                with Image.open(media_file) as raw_img:
                    # Conversion propre en mode RGB (nécessaire pour la conversion PDF depuis PNG/RGBA/Palette)
                    rgb_img: Image.Image = raw_img.convert("RGB")
                    # Application de la rotation si nécessaire (-angle pour rotation horaire dans Pillow)
                    if page.rotation != 0:
                        rgb_img = rgb_img.rotate(-page.rotation, expand=True)

                    pil_images.append(rgb_img)

            # Sauvegarde PDF
            first_image = pil_images[0]
            rest_images = pil_images[1:]
            first_image.save(
                str(final_pdf_path),
                save_all=True,
                append_images=rest_images,
                format="PDF",
                resolution=150.0,
            )
            logger.info(
                "Album %d compilé en PDF : %s (%d pages)",
                document_id,
                final_pdf_path,
                len(pil_images),
            )
        finally:
            for im in pil_images:
                im.close()

        return final_pdf_path
