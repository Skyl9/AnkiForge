# src/services/cards/export_manager.py
import hashlib
import json
import os
import re
import genanki
from src.database.models import DeckModel, CardModel, NoteVersionModel, DATA_DIR


class ExportManager:
    def __init__(self):
        # On pointe vers notre dossier media local
        self.media_dir = os.path.join(DATA_DIR, 'media')
        if not os.path.exists(self.media_dir):
            os.makedirs(self.media_dir)

    @staticmethod
    def generate_stable_id(text: str) -> int:
        """Génère un entier unique et constant basé sur une chaîne de caractères."""
        return int(hashlib.md5(text.encode('utf-8')).hexdigest()[:15], 16) % (10 ** 10)

    def export_deck(self, deck_id: int, output_path: str):
        """
        Exporte un paquet, ses sous-paquets, et toutes les images associées vers un .apkg
        """
        deck_model = DeckModel.get_by_id(deck_id)

        # Genanki exige un ID entier unique. On utilise un hash du nom pour avoir un ID constant.
        genanki_deck_id = self.generate_stable_id(deck_model.name)

        genanki_deck = genanki.Deck(
            deck_id=genanki_deck_id,
            name=deck_model.name
        )

        genanki_models = {}
        processed_notes = set()
        media_files_to_export = set()  # Utilisera un set pour éviter les doublons d'images

        # 1. On récupère le paquet ET tous ses sous-paquets (Ex: "Langues" + "Langues::Anglais")
        matching_decks = DeckModel.select().where(DeckModel.name.startswith(deck_model.name))
        cards = CardModel.select().where(CardModel.deck.in_(matching_decks))

        for card in cards:
            note = card.note
            # On s'assure de ne pas ajouter la même note en double
            if note.id in processed_notes:
                continue
            processed_notes.add(note.id)

            nt = note.note_type

            # 2. Traduction du NoteTypeModel vers genanki.Model
            if nt.id not in genanki_models:
                fields_list = json.loads(nt.fields_schema) if nt.fields_schema else ["Front", "Back"]
                templates_list = json.loads(nt.templates) if nt.templates else []

                # Formatage des templates pour genanki
                g_templates = []
                for i, t in enumerate(templates_list):
                    g_templates.append({
                        'name': t.get("name", f"Template {i + 1}"),
                        'qfmt': t.get("qfmt", ""),
                        'afmt': t.get("afmt", "")
                    })

                g_model = genanki.Model(
                    model_id=abs(hash(nt.name)) % (10 ** 10),
                    name=nt.name,
                    fields=[{'name': f} for f in fields_list],
                    templates=g_templates,
                    css=nt.css_style or ""
                )
                genanki_models[nt.id] = (g_model, fields_list)

            g_model, fields_list = genanki_models[nt.id]

            # 3. Construction des données de la Note (CORRECTION DU BUG ICI 👇)
            active_version = NoteVersionModel.get_or_none(note=note, is_active=True)
            if not active_version:
                continue  # Si la note n'a pas de version active, on l'ignore

            content_dict = json.loads(active_version.content)

            # CRITIQUE : L'ordre des valeurs doit correspondre EXACTEMENT à l'ordre des champs
            field_values = []
            for field_name in fields_list:
                val = str(content_dict.get(field_name, ""))
                field_values.append(val)

                # 4. RÉCUPÉRATION DES MÉDIAS (Images)
                # On cherche les balises <img src="nom_du_fichier.jpg">
                img_matches = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', val)
                for img_name in img_matches:
                    img_path = os.path.join(self.media_dir, img_name)
                    # Si l'image existe physiquement sur le disque, on l'ajoute au zip
                    if os.path.exists(img_path):
                        media_files_to_export.add(img_path)

            tags_list = json.loads(note.tags) if note.tags else []

            # 5. Création de la genanki.Note
            g_note = genanki.Note(
                model=g_model,
                fields=field_values,
                guid=note.guid,  # Vital pour les futures mises à jour Anki
                tags=tags_list
            )

            genanki_deck.add_note(g_note)

        # 6. Écriture du fichier final avec les médias
        package = genanki.Package(genanki_deck)
        package.media_files = list(media_files_to_export)
        package.write_to_file(output_path)