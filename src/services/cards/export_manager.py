# src/services/cards/export_manager.py
import hashlib
import json
import genanki
from src.database.models import DeckModel, CardModel


class ExportManager:
    @staticmethod
    def generate_stable_id(text: str) -> int:
        """Génère un entier unique et constant basé sur une chaîne de caractères."""
        return int(hashlib.md5(text.encode('utf-8')).hexdigest()[:15], 16) % (10 ** 10)

    def export_deck(self, deck_id: int, output_path: str):
        """
        Exporte un paquet (et toutes ses notes) depuis la base Peewee vers un fichier .apkg
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

        # On récupère toutes les cartes associées à ce paquet (et ses sous-paquets si on voulait)
        cards = CardModel.select().where(CardModel.deck == deck_model)

        for card in cards:
            note = card.note
            # On s'assure de ne pas ajouter la même note en double
            if note.id in processed_notes:
                continue
            processed_notes.add(note.id)

            nt = note.note_type

            # 1. Traduction du NoteTypeModel vers genanki.Model
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

            # 2. Construction des données de la Note
            content_dict = json.loads(note.content) if note.content else {}

            # CRITIQUE : L'ordre des valeurs doit correspondre EXACTEMENT à l'ordre des champs du modèle
            field_values = []
            for field_name in fields_list:
                field_values.append(str(content_dict.get(field_name, "")))

            tags_list = json.loads(note.tags) if note.tags else []

            # 3. Création de la genanki.Note
            g_note = genanki.Note(
                model=g_model,
                fields=field_values,
                guid=note.guid,  # On garde ton GUID pour qu'Anki puisse faire des mises à jour sans doublons !
                tags=tags_list
            )

            genanki_deck.add_note(g_note)

        # 4. Écriture du fichier final
        genanki.Package(genanki_deck).write_to_file(output_path)