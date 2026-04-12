import hashlib
import json
import re
from pathlib import Path

import genanki

from ankiforge.database.models import DeckModel, CardModel, NoteVersionModel, NoteModel, NoteTypeModel, db
from ankiforge.utils.paths import get_app_data_dir

# Suppression des avertissements de genanki notamment pour le mauvais parsing du latex reconnu comme balise html
import warnings

warnings.filterwarnings("ignore", module="genanki")


class ExportManager:
    def __init__(self):
        # On pointe vers notre dossier media local
        self.media_dir = get_app_data_dir() / "media"
        self.media_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def generate_stable_id(text: str) -> int:
        """Génère un entier unique et constant basé sur une chaîne de caractères."""
        return int(hashlib.md5(text.encode("utf-8"), usedforsecurity=False).hexdigest()[:15], 16) % (10**10)

    def export_deck(self, deck_id: int, output_path: str | Path, export_only_new: bool = True) -> None:
        """
        Exporte un paquet, ses sous-paquets, et toutes les images associées vers un .apkg
        """
        deck_model = DeckModel.get_by_id(deck_id)

        # 1. Préparation : On va stocker PLUSIEURS paquets (pour respecter les sous-dossiers)
        genanki_decks = {}
        genanki_models = {}
        processed_notes = set()
        media_files_to_export = set()

        notes_to_update_status = []

        matching_decks = DeckModel.select().where(DeckModel.name.startswith(deck_model.name))

        # 2. Création d'un genanki.Deck pour CHAQUE sous-paquet existant
        for d in matching_decks:
            # On privilégie le vrai anki_id s'il existe, sinon on génère un hash stable
            did = d.anki_id if d.anki_id else self.generate_stable_id(d.name)
            genanki_decks[d.id] = genanki.Deck(deck_id=did, name=d.name)

        condition = CardModel.deck.in_(matching_decks)
        if export_only_new:
            condition = condition & (NoteModel.status == "new")

        # 3. Récupération des cartes (avec Jointure sur le DeckModel pour savoir où les ranger)
        cards = CardModel.select(CardModel, NoteModel, NoteTypeModel, DeckModel).join(NoteModel).join(NoteTypeModel).switch(CardModel).join(DeckModel).where(condition)

        for card in cards:
            note = card.note
            if note.id in processed_notes:
                continue
            processed_notes.add(note.id)

            notes_to_update_status.append(note.id)

            nt = note.note_type

            # 4. Traduction du NoteTypeModel vers genanki.Model
            if nt.id not in genanki_models:
                fields_list = json.loads(nt.fields_schema) if nt.fields_schema else ["Front", "Back"]
                templates_list = json.loads(nt.templates) if nt.templates else []

                g_templates = []
                for i, t in enumerate(templates_list):
                    g_templates.append(
                        {
                            "name": t.get("name", f"Template {i + 1}"),
                            "qfmt": t.get("qfmt", ""),
                            "afmt": t.get("afmt", ""),
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

            # 5. Construction des données de la Note
            active_version = NoteVersionModel.get_or_none(note=note, is_active=True)
            if not active_version:
                continue

            content_dict = json.loads(active_version.content)

            field_values = []
            for field_name in fields_list:
                val = str(content_dict.get(field_name, ""))
                field_values.append(val)

                # RÉCUPÉRATION DES MÉDIAS (Images)
                img_matches = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', val)
                for img_name in img_matches:
                    img_path = self.media_dir / img_name
                    if img_path.exists():
                        media_files_to_export.add(str(img_path))

            tags_list = json.loads(note.tags) if note.tags else []

            g_note = genanki.Note(model=g_model, fields=field_values, guid=note.guid, tags=tags_list)

            genanki_decks[card.deck.id].add_note(g_note)
        if not notes_to_update_status and export_only_new:
            raise ValueError("Aucune NOUVELLE carte à exporter dans ce paquet.")

        # 6. Écriture du fichier final (on passe la liste de tous les paquets/sous-paquets)
        package = genanki.Package(list(genanki_decks.values()))
        package.media_files = list(media_files_to_export)
        package.write_to_file(str(output_path))
        if export_only_new and notes_to_update_status:
            with db.atomic():
                NoteModel.update(status="exported").where(NoteModel.id.in_(notes_to_update_status)).execute()
