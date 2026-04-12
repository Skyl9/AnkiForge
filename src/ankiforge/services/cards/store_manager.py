import csv
import json
import pathlib
import sqlite3
import tempfile
import uuid
import zipfile
from pathlib import Path

import zstandard as zstd
from peewee import DoesNotExist

from ankiforge.database.models import db, DeckModel, NoteTypeModel, NoteModel, CardModel, NoteVersionModel, init_db


class StoreManager:
    def __init__(self):
        pass

    @staticmethod
    def extract_pb_string(data: bytes, target_field: int) -> str:
        """Mini-décodeur Protobuf pour extraire une chaîne précise sans librairie externe."""
        i = 0
        while i < len(data):
            try:
                # 1. Lecture du Tag (Numéro du champ + Type de donnée)
                tag = 0
                shift = 0
                while True:
                    b = data[i]
                    i += 1
                    tag |= (b & 0x7F) << shift
                    if not (b & 0x80):
                        break
                    shift += 7

                field_number = tag >> 3
                wire_type = tag & 0x07

                # 2. On avance dans les octets selon le type de donnée
                if wire_type == 0:  # Type entier (Varint)
                    while data[i] & 0x80:
                        i += 1
                    i += 1
                elif wire_type == 1:
                    i += 8  # Type 64-bit
                elif wire_type == 5:
                    i += 4  # Type 32-bit
                elif wire_type == 2:  # Type Chaîne de caractères (Length-delimited)
                    length = 0
                    shift = 0
                    while True:
                        b = data[i]
                        i += 1
                        length |= (b & 0x7F) << shift
                        if not (b & 0x80):
                            break
                        shift += 7

                    # Si c'est le champ qu'on cherche, on décode la chaîne et on la renvoie !
                    if field_number == target_field:
                        return data[i : i + length].decode("utf-8", errors="ignore")
                    i += length
                else:
                    break
            except IndexError:
                break  # Fin inattendue du fichier binaire
        return ""

    @staticmethod
    def interpret_header(header_ligne: str, header_dict: dict):
        """Remplit le dictionnaire d'entête avec les INDEX (0-based) des colonnes."""
        if header_ligne.startswith("#separator"):
            return

        mapping = {
            "#notetype column": "notetype",
            "#tags column": "tags",
            "#guid column": "guid",
            "#deck column": "deck",
        }

        for key, value in mapping.items():
            if header_ligne.startswith(key):
                # On récupère le chiffre, et on soustrait 1 immédiatement
                col_index = int(header_ligne.split(":")[1].strip()) - 1
                header_dict[value] = col_index

    @staticmethod
    def get_card_content(note_ligne: list[str], header_dict: dict) -> list[str]:
        """Renvoit le contenu de la carte sans les informations des colonnes de métadonnées"""
        meta_indices = header_dict.values()
        # On garde l'élément seulement si son index n'est pas celui d'une métadonnée
        content_only = [val for idx, val in enumerate(note_ligne) if idx not in meta_indices]
        return content_only

    def handle_txt(self, txt_path: str | Path, progress_callback=None):
        """Parse un export Anki au format texte tabulé."""
        cards: list[list[str]] = []
        header_dict: dict[str, int] = {}

        if progress_callback:
            progress_callback(f"Nombre de cartes lues : {len(cards)}")
            progress_callback("Début insertion dans la base de donnée")

        with open(txt_path, "r", encoding="utf-8") as file:
            reader = csv.reader(file, delimiter="\t")
            for row in reader:
                if not row:
                    continue
                if row[0].startswith("#"):
                    self.interpret_header(row[0], header_dict)
                else:
                    cards.append(row)

        print(f"Nombre de cartes lues : {len(cards)}")
        print("Début insertion dans la base de donnée")

        with db.atomic():
            for row in cards:
                try:
                    # 1. Extraction sécurisée des métadonnées (avec valeurs par défaut si absentes)
                    deck_name = row[header_dict["deck"]] if "deck" in header_dict and header_dict["deck"] < len(row) else "Default Deck"
                    notetype_name = row[header_dict["notetype"]] if "notetype" in header_dict and header_dict["notetype"] < len(row) else "Basic"
                    guid = row[header_dict["guid"]] if "guid" in header_dict and header_dict["guid"] < len(row) else str(uuid.uuid4())

                    # 2. Gestion du Deck (avec hiérarchie ::)
                    parent_deck = None
                    if "::" in deck_name:
                        parent_name = deck_name.rsplit("::", 1)[0]
                        parent_deck, _ = DeckModel.get_or_create(name=parent_name)

                    deck_obj, _ = DeckModel.get_or_create(name=deck_name, defaults={"parent_deck": parent_deck})

                    # 3. Gestion du NoteType (Modèle)
                    content_values = self.get_card_content(row, header_dict)
                    field_names = [f"Field_{i + 1}" for i in range(len(content_values))]

                    notetype_obj, _ = NoteTypeModel.get_or_create(
                        name=notetype_name,
                        defaults={"fields_schema": json.dumps(field_names), "templates": "[]", "css_style": ""},
                    )

                    # 4. Création de la Note (Le contenu textuel JSON)
                    content_dict = dict(zip(field_names, content_values, strict=False))

                    note_obj, created = NoteModel.get_or_create(
                        guid=guid,
                        defaults={
                            "note_type": notetype_obj,  # On passe l'objet Peewee !
                            "status": "imported",
                        },
                    )
                    if created:
                        # Nouvelle carte : on crée la v1
                        NoteVersionModel.create(
                            note=note_obj,
                            version_number=1,
                            content=json.dumps(content_dict, ensure_ascii=False),
                            source="import",
                            is_active=True,
                        )
                    else:
                        # La carte existe déjà (le GUID correspond) : on utilise notre méthode pour faire une v2 !
                        note_obj.add_version(content_dict, source="import")
                    # 5. Création de la Carte Physique (Le lien final !)
                    CardModel.get_or_create(note=note_obj, deck=deck_obj)

                except Exception as e:
                    if progress_callback:
                        progress_callback(f"Erreur lors de l'insertion de la ligne {row}: {e}")

    def handle_apkg(self, apkg_path: Path, progress_callback=None):
        """
        Extrait un fichier .apkg ou .colpkg et l'injecte dans la base Peewee.
        """
        if progress_callback:
            progress_callback(f"Extraction de l'archive : {apkg_path.name}...")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            try:
                with zipfile.ZipFile(apkg_path, "r") as zip_ref:
                    zip_ref.extractall(temp_path)
            except zipfile.BadZipFile as e:
                raise ValueError(f"Le fichier {apkg_path.name} n'est pas une archive valide.") from e

            # --- GESTION ZSTANDARD ---
            anki21b_path = temp_path / "collection.anki21b"
            anki2_path = temp_path / "collection.anki2"
            sqlite_db_path = temp_path / "uncompressed_anki.db"

            if anki21b_path.exists():
                if progress_callback:
                    progress_callback("Décompression Zstandard en cours...")
                with open(anki21b_path, "rb") as compressed_file:
                    dctx = zstd.ZstdDecompressor()
                    with open(sqlite_db_path, "wb") as uncompressed_file:
                        dctx.copy_stream(compressed_file, uncompressed_file)
            elif anki2_path.exists():
                if progress_callback:
                    progress_callback("Format SQLite natif détecté.")
                sqlite_db_path = anki2_path
            else:
                raise FileNotFoundError("Aucune base de données Anki trouvée.")

            # --- EXTRACTION SQL -> PEEWEE ---
            if progress_callback:
                progress_callback("Injection des données dans Ankiforge...")
                conn = sqlite3.connect(sqlite_db_path)
            cursor = conn.cursor()
            try:
                # db.atomic() rend l'insertion massive beaucoup plus rapide et sûre
                with db.atomic():
                    # ---------------------------------------------------------
                    # 1. DECKS ET HIÉRARCHIE
                    # ---------------------------------------------------------

                    cursor.execute("SELECT decks FROM col")
                    decks_raw = cursor.fetchone()[0]
                    decks_list = []

                    if decks_raw:
                        # Format classique (Anki < 2.1.50)
                        decks_json = json.loads(decks_raw)
                        decks_list = sorted(decks_json.values(), key=lambda d: d.get("name", ""))
                    else:
                        # Nouveau format (Anki > 2.1.50)
                        cursor.execute("SELECT id, name FROM decks")
                        for row in cursor.fetchall():
                            clean_name = row[1].replace("\x1f", "::")
                            decks_list.append({"id": row[0], "name": clean_name})

                            # On trie alphabétiquement pour la hiérarchie
                        decks_list = sorted(decks_list, key=lambda d: d.get("name", ""))

                    for d_info in decks_list:
                        full_name = d_info.get("name", "Unknown")
                        did = d_info.get("id")
                        parent_deck = None

                        if "::" in full_name:
                            parent_name = full_name.rsplit("::", 1)[0]
                            parent_deck = DeckModel.get_or_none(DeckModel.name == parent_name)

                        deck_obj, created = DeckModel.get_or_create(name=full_name, defaults={"anki_id": did, "parent_deck": parent_deck})

                        if not created and not deck_obj.anki_id:
                            deck_obj.anki_id = did
                            deck_obj.save()

                    # ---------------------------------------------------------
                    # 2. MODÈLES DE NOTES (NoteTypes Blindé)
                    # ---------------------------------------------------------
                    cursor.execute("SELECT models FROM col")
                    models_raw = cursor.fetchone()[0]

                    if models_raw:
                        # Format classique
                        models_json = json.loads(models_raw)
                        for mid_str, m_info in models_json.items():
                            field_names = [f["name"] for f in m_info.get("flds", [])]
                            nt_obj, created = NoteTypeModel.get_or_create(
                                name=m_info.get("name", "Unknown"),
                                defaults={
                                    "anki_id": int(mid_str),
                                    "fields_schema": json.dumps(field_names),
                                    "templates": json.dumps(m_info.get("tmpls", [])),
                                    "css_style": m_info.get("css", ""),
                                },
                            )
                            if not created and not nt_obj.anki_id:
                                nt_obj.anki_id = int(mid_str)
                                nt_obj.save()
                    else:
                        cursor.execute("SELECT id, name, config FROM notetypes")
                        for row in cursor.fetchall():
                            mid, name, config_blob = row

                            # 1. Noms des champs
                            field_names = []
                            try:
                                cursor.execute("SELECT name FROM fields WHERE ntid=? ORDER BY ord", (mid,))
                                field_names = [f[0] for f in cursor.fetchall()]
                            except sqlite3.OperationalError:
                                pass

                            # 2. Extraction PARFAITE du CSS (Le CSS est le champ N°3 du Protobuf Anki)
                            css_style = self.extract_pb_string(config_blob, 3) if config_blob else ""

                            # 3. Extraction PARFAITE des Templates HTML (Recto = Champ N°1, Verso = Champ N°2)
                            tmpls = []
                            try:
                                cursor.execute("SELECT name, config FROM templates WHERE ntid=? ORDER BY ord", (mid,))
                                for t_row in cursor.fetchall():
                                    t_name, t_config = t_row
                                    qfmt = self.extract_pb_string(t_config, 1) if t_config else ""
                                    afmt = self.extract_pb_string(t_config, 2) if t_config else ""
                                    tmpls.append({"name": t_name, "qfmt": qfmt, "afmt": afmt})
                            except sqlite3.OperationalError:
                                pass

                            # Sauvegarde en BDD
                            nt_obj, created = NoteTypeModel.get_or_create(
                                name=name,
                                defaults={
                                    "anki_id": mid,
                                    "fields_schema": json.dumps(field_names),
                                    "templates": json.dumps(tmpls, ensure_ascii=False),
                                    "css_style": css_style,
                                },
                            )
                            if not created and not nt_obj.anki_id:
                                nt_obj.anki_id = mid
                                nt_obj.save()
                    # ---------------------------------------------------------
                    # 3. LE TEXTE DES CARTES (Notes)
                    # ---------------------------------------------------------
                    cursor.execute("SELECT id, guid, mid, tags, flds FROM notes")
                    for row in cursor.fetchall():
                        nid, guid, mid, tags_raw, flds_raw = row

                        note_type = NoteTypeModel.get_or_none(NoteTypeModel.anki_id == mid)
                        if not note_type:
                            continue

                        field_values = flds_raw.split("\x1f")
                        field_names = json.loads(note_type.fields_schema)

                        # --- MAGIE DU FALLBACK ---
                        # Si Anki récent, on a pas les noms ("Front", "Back").
                        # On les nomme dynamiquement "Field_1", "Field_2", etc.
                        if not field_names:
                            field_names = [f"Field_{i + 1}" for i in range(len(field_values))]

                        content_dict = dict(zip(field_names, field_values, strict=False))
                        tags = tags_raw.strip().split(" ") if tags_raw.strip() else []

                        note_obj, created = NoteModel.get_or_create(
                            guid=guid,
                            defaults={
                                "anki_id": nid,
                                "note_type": note_type,
                                "tags": json.dumps(tags),
                                "status": "imported",
                            },
                        )
                        if not created and not note_obj.anki_id:
                            note_obj.anki_id = nid
                            note_obj.save()

                        if created:
                            # Nouvelle note depuis l'apkg
                            NoteVersionModel.create(
                                note=note_obj,
                                version_number=1,
                                content=json.dumps(content_dict, ensure_ascii=False),
                                source="import",
                                is_active=True,
                            )
                        else:
                            # Mise à jour d'une note existante via l'import de l'apkg
                            note_obj.add_version(content_dict, source="import")

                    # ---------------------------------------------------------
                    # 4. LA POSITION DANS LES PAQUETS (Cards)
                    # ---------------------------------------------------------
                    cursor.execute("SELECT id, nid, did, ord FROM cards")
                    for row in cursor.fetchall():
                        cid, nid, did, template_ord = row

                        try:
                            note = NoteModel.get(NoteModel.anki_id == nid)
                            deck = DeckModel.get(DeckModel.anki_id == did)

                            card_obj, created = CardModel.get_or_create(note=note, template_index=template_ord, defaults={"anki_id": cid, "deck": deck})
                            if not created and not card_obj.anki_id:
                                card_obj.anki_id = cid
                                card_obj.save()

                        except DoesNotExist:
                            continue

            except sqlite3.DatabaseError as e:
                raise RuntimeError(f"Erreur SQL lors de l'extraction : {e}") from e
            finally:
                conn.close()

        if progress_callback:
            progress_callback("L'importation totale dans Ankiforge est terminée !")

    def store_collection(self, collection_path: str, progress_callback=None):
        path_obj = pathlib.Path(collection_path)

        if not path_obj.exists():
            raise FileNotFoundError(f"Le fichier {collection_path} est introuvable.")

        extension = path_obj.suffix.lower()

        match extension:
            # On gère apkg et colpkg avec la même fonction !
            case ".apkg" | ".colpkg":
                if progress_callback:
                    progress_callback(f"Lancement de l'extraction pour archive ({extension})")
                self.handle_apkg(apkg_path=path_obj, progress_callback=progress_callback)
            case ".txt":
                if progress_callback:
                    progress_callback("Lancement du parser Texte (.txt)")
                self.handle_txt(txt_path=path_obj, progress_callback=progress_callback)
            case _:
                # Remplacement du return par un raise
                raise ValueError(f"Type de fichier non supporté : {extension}")


if __name__ == "__main__":
    # N'oublie pas d'initialiser la base de données avant de tester !

    init_db()

    store = StoreManager()
    store.store_collection("../../../math_test.txt")
