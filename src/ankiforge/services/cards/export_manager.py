"""
Service d'Exportation de Paquets et Collections Anki (.apkg, .colpkg).
Permet l'exportation sélective par paquet racine, sous-paquets, tags et statut,
avec inclusion automatique des médias associés et persistance des identifiants stables.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import warnings
from pathlib import Path
from typing import Callable, List, Optional, Set

import genanki

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
    db,
)
from ankiforge.utils.paths import get_media_dir

# Suppression des avertissements genanki pour le parsing LaTeX / HTML
warnings.filterwarnings("ignore", module="genanki")

logger = logging.getLogger(__name__)


class ExportManager:
    """
    Gestionnaire responsable de l'exportation sélective de paquets et de collections au format .apkg/.colpkg.
    """

    def __init__(self) -> None:
        self.media_dir = get_media_dir()
        self.media_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def generate_stable_id(text: str) -> int:
        """Génère un identifiant numérique stable à 10 chiffres."""
        return int(hashlib.md5(text.encode("utf-8"), usedforsecurity=False).hexdigest()[:15], 16) % (10**10)

    def export_package(
        self,
        output_path: str | Path,
        deck_id: Optional[int] = None,
        tags: Optional[List[str]] = None,
        status_filter: str = "all",  # 'all', 'new', 'modified'
        format_type: str = "apkg",
        include_media: bool = True,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> int:
        """
        Exporte une sélection de cartes vers un fichier .apkg ou .colpkg.

        Args:
            output_path: Chemin du fichier de destination.
            deck_id: ID du paquet racine (optionnel, exporte toute la collection si None).
            tags: Liste de tags à filtrer (optionnel).
            status_filter: Filtre de statut ('all', 'new', 'modified').
            format_type: 'apkg' ou 'colpkg'.
            include_media: Si True, inclut les images et audios référencés.
            progress_callback: Fonction de notification de progression.

        Returns:
            int: Nombre de notes exportées.
        """
        import time

        t0 = time.perf_counter()
        logger.info(
            "Démarrage de l'exportation vers '%s' (deck_id=%s, tags=%s, statut=%s, médias=%s)",
            output_path,
            deck_id,
            tags,
            status_filter,
            include_media,
        )

        if progress_callback:
            progress_callback("Préparation de l'exportation...")

        matching_decks = None
        if deck_id is not None:
            root_deck = DeckModel.get_or_none(DeckModel.id == deck_id)
            if root_deck:
                matching_decks = list(DeckModel.select().where((DeckModel.id == root_deck.id) | (DeckModel.name.startswith(f"{root_deck.name}::"))))
            else:
                matching_decks = []
        else:
            matching_decks = list(DeckModel.select())

        if not matching_decks:
            logger.warning("Aucun paquet trouvé pour l'exportation.")
            raise ValueError("Aucun paquet trouvé pour l'exportation.")

        # Construction de la requête
        condition = CardModel.deck.in_(matching_decks)

        if status_filter == "new":
            condition = condition & (NoteModel.status == "new")

        query = CardModel.select(CardModel, NoteModel, NoteTypeModel, DeckModel).join(NoteModel).join(NoteTypeModel).switch(CardModel).join(DeckModel).where(condition)

        genanki_decks = {}
        for d in matching_decks:
            did = d.anki_id if d.anki_id else self.generate_stable_id(d.name)
            genanki_decks[d.id] = genanki.Deck(deck_id=did, name=d.name)

        genanki_models = {}
        processed_notes: Set[int] = set()
        media_files_to_export: Set[str] = set()
        exported_note_ids: List[int] = []

        cards = list(query)
        total_cards = len(cards)

        for idx, card in enumerate(cards):
            note = card.note
            if note.id in processed_notes:
                continue

            # Filtre par tags si spécifié
            if tags:
                note_tags = []
                if note.tags:
                    try:
                        parsed = json.loads(note.tags)
                        if isinstance(parsed, list):
                            note_tags = parsed
                    except Exception as err:
                        logger.debug("Remarque sur le parsing des tags de la note ID=%d : %s", note.id, err)
                if not any(t in note_tags for t in tags):
                    continue

            processed_notes.add(note.id)
            exported_note_ids.append(note.id)

            nt = note.note_type
            if not nt:
                continue

            # Modèle genanki
            if nt.id not in genanki_models:
                fields_list = json.loads(nt.fields_schema) if nt.fields_schema else ["Front", "Back"]
                templates_list = json.loads(nt.templates) if nt.templates else []

                g_templates = []
                for i, t in enumerate(templates_list):
                    g_templates.append(
                        {
                            "name": t.get("name", f"Template {i + 1}"),
                            "qfmt": t.get("qfmt", "{{Front}}"),
                            "afmt": t.get("afmt", "{{FrontSide}}<hr id=answer>{{Back}}"),
                        }
                    )

                mid = nt.anki_id if nt.anki_id else self.generate_stable_id(nt.name)
                g_model = genanki.Model(
                    model_id=mid,
                    name=nt.name,
                    fields=[{"name": f} for f in fields_list],
                    templates=g_templates,
                    css=nt.css_style or "",
                )
                genanki_models[nt.id] = (g_model, fields_list)

            g_model, fields_list = genanki_models[nt.id]

            # Contenu de la note active
            active_version = NoteVersionModel.get_or_none(note=note, is_active=True)
            if not active_version:
                active_version = NoteVersionModel.select().where(NoteVersionModel.note == note).order_by(NoteVersionModel.version_number.desc()).first()

            content_dict = {}
            if active_version and active_version.content:
                try:
                    content_dict = json.loads(active_version.content)
                except Exception as err:
                    logger.debug("Remarque sur le parsing du contenu de la note ID=%d : %s", note.id, err)

            field_values = []
            for field_name in fields_list:
                val = str(content_dict.get(field_name, ""))
                field_values.append(val)

                # Récupération automatique des médias
                if include_media:
                    # Images
                    img_matches = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', val)
                    for img_name in img_matches:
                        img_path = self.media_dir / img_name
                        if img_path.exists():
                            media_files_to_export.add(str(img_path))

                    # Audio / Sons [sound:xxx.mp3]
                    snd_matches = re.findall(r"\[sound:([^\]]+)\]", val)
                    for snd_name in snd_matches:
                        snd_path = self.media_dir / snd_name
                        if snd_path.exists():
                            media_files_to_export.add(str(snd_path))

            tags_list = []
            if note.tags:
                try:
                    parsed = json.loads(note.tags)
                    if isinstance(parsed, list):
                        tags_list = parsed
                except Exception as err:
                    logger.debug("Remarque sur le parsing des tags de la note ID=%d : %s", note.id, err)

            g_note = genanki.Note(model=g_model, fields=field_values, guid=note.guid, tags=tags_list)

            if card.deck and card.deck.id in genanki_decks:
                genanki_decks[card.deck.id].add_note(g_note)
            else:
                first_deck = list(genanki_decks.values())[0]
                first_deck.add_note(g_note)

            if progress_callback and (idx % 20 == 0 or idx == total_cards - 1):
                progress_callback(f"Exportation : {len(processed_notes)} notes traitées...")

        if not processed_notes:
            logger.warning("Aucune carte ne correspond aux critères d'exportation sélectionnés.")
            raise ValueError("Aucune carte ne correspond aux critères d'exportation sélectionnés.")

        # Emballage final
        if progress_callback:
            progress_callback(f"Génération de l'archive ({len(media_files_to_export)} médias inclus)...")

        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        package = genanki.Package(list(genanki_decks.values()))
        if include_media:
            package.media_files = list(media_files_to_export)

        package.write_to_file(str(out_path))

        # Mise à jour du statut des notes exportées
        with db.atomic():
            NoteModel.update(status="exported").where(NoteModel.id.in_(exported_note_ids)).execute()

        elapsed = time.perf_counter() - t0
        logger.info(
            "Exportation .apkg réussie vers '%s' : %d notes et %d médias exportés en %.2fs",
            out_path.name,
            len(processed_notes),
            len(media_files_to_export),
            elapsed,
        )

        if progress_callback:
            progress_callback(f"Exportation terminée avec succès ({len(processed_notes)} notes exportées) !")

        return len(processed_notes)

    def export_deck(self, deck_id: int, output_path: str | Path, export_only_new: bool = True) -> None:
        """Alias rétrocompatible pour l'export d'un paquet."""
        status = "new" if export_only_new else "all"
        self.export_package(
            output_path=output_path,
            deck_id=deck_id,
            status_filter=status,
            include_media=True,
        )
