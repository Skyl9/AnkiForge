"""
Service d'Importation, Analyse Déterministe et Gestion des Conflits pour AnkiForge.
Supporte les archives .apkg, .colpkg (Zstandard collection.anki21b, SQLite collection.anki2)
et les fichiers texte tabulés (.txt).
Applique la Règle 11 : Détection stricte des conflits de contenu uniquement si la note locale
a été modifiée manuellement (source == 'manual') et que le texte diffère.
Les déplacements de dossiers et révisions sont fusionnés silencieusement.
"""

from __future__ import annotations

import csv
import difflib
import hashlib
import io
import json
import logging
import mimetypes
import shutil
import sqlite3
import tempfile
import uuid
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import zstandard as zstd

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    MediaModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
    db,
)
from ankiforge.utils.c_bridge import get_similarity
from ankiforge.utils.paths import get_media_dir

logger = logging.getLogger(__name__)


@dataclass
class ConflictItem:
    """Représente un conflit de contenu avéré entre une note locale et une note entrante."""

    note_id: int
    guid: str
    note_type_name: str
    local_content: dict[str, str]
    incoming_content: dict[str, str]
    local_deck: str
    incoming_deck: str
    local_tags: list[str]
    incoming_tags: list[str]
    similarity_score: float
    field_diffs: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class ImportAnalysisResult:
    """Résultat de l'analyse préliminaire d'une archive Anki avant écriture en base."""

    temp_dir: str
    source_type: str  # 'apkg', 'colpkg', 'txt'
    sqlite_path: str | None
    txt_path: str | None
    new_notes: list[dict[str, Any]]
    silent_updates: list[dict[str, Any]]
    identical_count: int
    conflicts: list[ConflictItem]
    media_map: dict[str, str]  # id (numéro de fichier dans le zip) -> filename
    raw_models: dict[int, dict[str, Any]] = field(default_factory=dict)
    raw_decks: list[dict[str, Any]] = field(default_factory=list)

    def cleanup(self) -> None:
        """Supprime le dossier temporaire d'analyse s'il existe."""
        if self.temp_dir and Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            self.temp_dir = ""


class ImportManager:
    """Gestionnaire central d'ingestion et de fusion des collections Anki."""

    def __init__(self) -> None:
        self.media_dir = get_media_dir()
        self.media_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def parse_media_pb(data: bytes) -> dict[str, str]:
        """Décode un flux binaire Protobuf MediaEntries (Anki modern) en dictionnaire file_key -> filename."""
        media_map: dict[str, str] = {}
        i = 0
        entry_idx = 0
        while i < len(data):
            tag = 0
            shift = 0
            while i < len(data):
                b = data[i]
                i += 1
                tag |= (b & 0x7F) << shift
                if not (b & 0x80):
                    break
                shift += 7
            field_num = tag >> 3
            wire_type = tag & 0x07

            if wire_type == 0:
                while i < len(data) and (data[i] & 0x80):
                    i += 1
                i += 1
            elif wire_type == 1:
                i += 8
            elif wire_type == 5:
                i += 4
            elif wire_type == 2:
                length = 0
                shift = 0
                while i < len(data):
                    b = data[i]
                    i += 1
                    length |= (b & 0x7F) << shift
                    if not (b & 0x80):
                        break
                    shift += 7
                sub_data = data[i : i + length]
                i += length

                if field_num == 1:  # repeated MediaEntry
                    entry_name = ""
                    legacy_filename: str | None = None
                    si = 0
                    while si < len(sub_data):
                        stag = 0
                        sshift = 0
                        while si < len(sub_data):
                            sb = sub_data[si]
                            si += 1
                            stag |= (sb & 0x7F) << sshift
                            if not (sb & 0x80):
                                break
                            sshift += 7
                        sfield = stag >> 3
                        swire = stag & 0x07
                        if swire == 0:
                            val = 0
                            vshift = 0
                            while si < len(sub_data):
                                vb = sub_data[si]
                                si += 1
                                val |= (vb & 0x7F) << vshift
                                if not (vb & 0x80):
                                    break
                                vshift += 7
                            if sfield == 255:
                                legacy_filename = str(val)
                        elif swire == 1:
                            si += 8
                        elif swire == 5:
                            si += 4
                        elif swire == 2:
                            slen = 0
                            lshift = 0
                            while si < len(sub_data):
                                lb = sub_data[si]
                                si += 1
                                slen |= (lb & 0x7F) << lshift
                                if not (lb & 0x80):
                                    break
                                lshift += 7
                            content = sub_data[si : si + slen]
                            si += slen
                            if sfield == 1:
                                entry_name = content.decode("utf-8", errors="ignore")
                        else:
                            break
                    if entry_name:
                        file_key = legacy_filename if legacy_filename is not None else str(entry_idx)
                        media_map[file_key] = entry_name
                    entry_idx += 1
            else:
                break
        return media_map

    @staticmethod
    def extract_pb_string(data: bytes, target_field: int) -> str:
        """Décode un champ texte Protobuf sans dépendance externe lourde."""
        i = 0
        while i < len(data):
            try:
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

                if wire_type == 0:
                    while data[i] & 0x80:
                        i += 1
                    i += 1
                elif wire_type == 1:
                    i += 8
                elif wire_type == 5:
                    i += 4
                elif wire_type == 2:
                    length = 0
                    shift = 0
                    while True:
                        b = data[i]
                        i += 1
                        length |= (b & 0x7F) << shift
                        if not (b & 0x80):
                            break
                        shift += 7

                    if field_number == target_field:
                        return data[i : i + length].decode("utf-8", errors="ignore")
                    i += length
                else:
                    break
            except IndexError:
                break
        return ""

    @staticmethod
    def compute_field_diffs(local_content: dict[str, str], incoming_content: dict[str, str]) -> dict[str, dict[str, Any]]:
        """Calcule les différences textuelles champ par champ avec opcodes."""
        all_keys = set(local_content.keys()) | set(incoming_content.keys())
        diffs = {}
        for key in all_keys:
            val1 = local_content.get(key, "")
            val2 = incoming_content.get(key, "")
            matcher = difflib.SequenceMatcher(None, val1, val2)
            ratio = matcher.ratio()
            diffs[key] = {
                "local": val1,
                "incoming": val2,
                "ratio": ratio,
                "is_different": val1.strip() != val2.strip(),
            }
        return diffs

    def analyze_archive(self, file_path: str | Path, progress_callback: Callable[[str], None] | None = None) -> ImportAnalysisResult:
        """
        Analyse une archive (.apkg, .colpkg ou .txt) sans modifier la base de données.
        Identifie les nouvelles notes, les mises à jour silencieuses et les conflits stricts.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Fichier introuvable : {path}")

        if progress_callback:
            progress_callback(f"Analyse de {path.name}...")

        if path.suffix.lower() == ".txt":
            return self._analyze_txt(path, progress_callback)
        return self._analyze_apkg(path, progress_callback)

    def _analyze_txt(self, txt_path: Path, progress_callback: Callable[[str], None] | None = None) -> ImportAnalysisResult:
        cards: list[list[str]] = []
        header_dict: dict[str, int] = {}

        mapping = {
            "#notetype column": "notetype",
            "#tags column": "tags",
            "#guid column": "guid",
            "#deck column": "deck",
        }

        with open(txt_path, encoding="utf-8", errors="ignore") as f:
            reader = csv.reader(f, delimiter="\t")
            for row in reader:
                if not row:
                    continue
                if row[0].startswith("#"):
                    for key, val in mapping.items():
                        if row[0].startswith(key):
                            col_index = int(row[0].split(":")[1].strip()) - 1
                            header_dict[val] = col_index
                else:
                    cards.append(row)

        new_notes: list[dict[str, Any]] = []
        silent_updates: list[dict[str, Any]] = []
        conflicts: list[ConflictItem] = []
        identical_count = 0

        raw_models: dict[int, dict[str, Any]] = {}
        known_models = {nt.name: nt for nt in NoteTypeModel.select()}

        for row in cards:
            guid = row[header_dict["guid"]] if "guid" in header_dict and header_dict["guid"] < len(row) else str(uuid.uuid4())
            deck_name = row[header_dict["deck"]] if "deck" in header_dict and header_dict["deck"] < len(row) else "Par défaut"
            notetype_name = row[header_dict["notetype"]] if "notetype" in header_dict and header_dict["notetype"] < len(row) else "Basic"
            tags = row[header_dict["tags"]].strip().split() if "tags" in header_dict and header_dict["tags"] < len(row) else []

            meta_indices = header_dict.values()
            content_values = [val for idx, val in enumerate(row) if idx not in meta_indices]

            # Détermination intelligente des noms de champs
            field_names: list[str] = []
            if notetype_name in known_models and known_models[notetype_name].fields_schema:
                try:
                    field_names = list(json.loads(known_models[notetype_name].fields_schema))
                except Exception:
                    field_names = []

            if not field_names:
                field_names = [f"Field_{i + 1}" for i in range(len(content_values))]
            elif len(content_values) > len(field_names):
                field_names = list(field_names) + [f"Field_{i + 1}" for i in range(len(field_names), len(content_values))]
            else:
                field_names = field_names[: len(content_values)]

            content_dict = dict(zip(field_names, content_values, strict=False))

            if notetype_name not in [m["name"] for m in raw_models.values()]:
                m_tmpls: list[dict[str, Any]] = []
                m_css = ""
                if notetype_name in known_models:
                    try:
                        m_tmpls = json.loads(known_models[notetype_name].templates) if known_models[notetype_name].templates else []
                    except Exception:
                        m_tmpls = []
                    m_css = getattr(known_models[notetype_name], "css_style", "") or ""
                if not m_tmpls and field_names:
                    back_f = field_names[1] if len(field_names) > 1 else field_names[0]
                    m_tmpls = [{"name": "Carte 1", "qfmt": f"{{{{{field_names[0]}}}}}", "afmt": f"{{{{FrontSide}}}}<hr id=answer>{{{{{back_f}}}}}"}]

                raw_models[len(raw_models) + 1] = {
                    "name": notetype_name,
                    "fields": field_names,
                    "templates": m_tmpls,
                    "css": m_css,
                }

            existing_note = NoteModel.get_or_none(NoteModel.guid == guid)
            if not existing_note:
                new_notes.append(
                    {
                        "guid": guid,
                        "deck_name": deck_name,
                        "notetype_name": notetype_name,
                        "tags": tags,
                        "content": content_dict,
                        "field_names": field_names,
                    }
                )
            else:
                if self._evaluate_existing_note(existing_note, content_dict, deck_name, tags, notetype_name, silent_updates, conflicts):
                    identical_count += 1

        return ImportAnalysisResult(
            temp_dir="",
            source_type="txt",
            sqlite_path=None,
            txt_path=str(txt_path),
            new_notes=new_notes,
            silent_updates=silent_updates,
            identical_count=identical_count,
            conflicts=conflicts,
            media_map={},
            raw_models=raw_models,
        )

    DEFAULT_DECK_NAMES: set[str] = {
        "default",
        "par défaut",
        "predeterminado",
        "standard",
        "predefinito",
        "padrão",
        "по умолчанию",
        "既定",
        "默认",
    }

    def _ensure_deck(self, name: str, deck_cache: dict[str, DeckModel], anki_id: int | None = None) -> DeckModel:
        """Crée ou récupère un deck et toute son arborescence de sous-decks en évitant les collisions d'anki_id."""
        if not name or not name.strip():
            name = "Par défaut"

        if name in deck_cache:
            return deck_cache[name]

        parts = name.split("::")
        current_deck: DeckModel | None = None
        accumulated_name = ""
        for i, part in enumerate(parts):
            accumulated_name = part if i == 0 else f"{accumulated_name}::{part}"
            if accumulated_name in deck_cache:
                current_deck = deck_cache[accumulated_name]
                continue

            is_leaf = i == len(parts) - 1
            leaf_anki_id = anki_id if is_leaf else None

            # 1. Recherche par nom exact
            existing_by_name = DeckModel.get_or_none(DeckModel.name == accumulated_name)
            if existing_by_name:
                current_deck = existing_by_name
                if leaf_anki_id and current_deck.anki_id is None and not DeckModel.select().where(DeckModel.anki_id == leaf_anki_id).exists():
                    current_deck.anki_id = leaf_anki_id
                    current_deck.save()
                deck_cache[accumulated_name] = current_deck
                continue

            # 2. Gestion des alias du paquet racine par défaut (ex: 'Default' vs 'Par défaut', did=1)
            is_default_alias = accumulated_name.lower() in self.DEFAULT_DECK_NAMES or leaf_anki_id == 1
            if is_default_alias:
                existing_default = DeckModel.get_or_none(DeckModel.anki_id == 1)
                if not existing_default:
                    for alias in ("Par défaut", "Default"):
                        existing_default = DeckModel.get_or_none(DeckModel.name == alias)
                        if existing_default:
                            break
                if existing_default:
                    current_deck = existing_default
                    if leaf_anki_id == 1 and current_deck.anki_id is None:
                        current_deck.anki_id = 1
                        current_deck.save()
                    deck_cache[accumulated_name] = current_deck
                    deck_cache[current_deck.name] = current_deck
                    continue

            # 3. Vérification de l'unicité de anki_id pour les nouveaux decks
            target_anki_id = leaf_anki_id
            if target_anki_id is not None:
                existing_by_anki_id = DeckModel.get_or_none(DeckModel.anki_id == target_anki_id)
                if existing_by_anki_id:
                    logger.warning(
                        "Conflit anki_id=%s pour le deck '%s' (déjà attribué au deck '%s'). Création sans anki_id.",
                        target_anki_id,
                        accumulated_name,
                        existing_by_anki_id.name,
                    )
                    target_anki_id = None

            current_deck = DeckModel.create(
                name=accumulated_name,
                parent_deck=current_deck,
                anki_id=target_anki_id,
            )
            deck_cache[accumulated_name] = current_deck

        return current_deck or DeckModel.get_or_create(name="Par défaut")[0]

    def _analyze_apkg(self, apkg_path: Path, progress_callback: Callable[[str], None] | None = None) -> ImportAnalysisResult:
        temp_dir = tempfile.mkdtemp(prefix="ankiforge_import_")
        temp_path = Path(temp_dir)

        try:
            with zipfile.ZipFile(apkg_path, "r") as zf:
                zf.extractall(temp_path)
        except zipfile.BadZipFile as e:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise ValueError(f"Le fichier {apkg_path.name} n'est pas une archive ZIP/APKG valide.") from e

        try:
            # Lecture de media map (support JSON legacy, Protobuf et Zstandard)
            media_map: dict[str, str] = {}
            media_path = temp_path / "media"
            media_zstd_path = temp_path / "media.zstd"

            target_media_file = media_path if media_path.exists() else (media_zstd_path if media_zstd_path.exists() else None)
            if target_media_file and target_media_file.exists():
                try:
                    with open(target_media_file, "rb") as mf:
                        raw_media_bytes = mf.read()

                    # Décompression Zstandard si nécessaire
                    if raw_media_bytes.startswith(b"\x28\xb5\x2f\xfd"):
                        try:
                            dctx = zstd.ZstdDecompressor()
                            with dctx.stream_reader(io.BytesIO(raw_media_bytes)) as reader:
                                raw_media_bytes = reader.read()
                        except Exception as z_err:
                            logger.debug("Remarque décompression zstd media : %s", z_err)

                    # Essai 1 : JSON legacy
                    try:
                        text_cand = raw_media_bytes.decode("utf-8")
                        if text_cand.strip().startswith("{"):
                            media_map = json.loads(text_cand)
                    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                        pass

                    # Essai 2 : Protobuf MediaEntries
                    if not media_map:
                        media_map = self.parse_media_pb(raw_media_bytes)
                except Exception as e:
                    logger.warning("Impossible de lire le fichier media du package: %s", e)

            # Auto-détection complémentaire pour les fichiers médias déjà nommés dans l'archive
            media_extensions = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".mp3", ".wav", ".ogg", ".mp4", ".webp"}
            for f in temp_path.iterdir():
                if f.is_file() and f.suffix.lower() in media_extensions and f.name not in media_map.values() and f.name not in media_map:
                    media_map[f.name] = f.name

            # Détection SQLite / Zstandard (Priorité: anki21b > anki21 > anki2)
            anki21b_path = temp_path / "collection.anki21b"
            anki21_path = temp_path / "collection.anki21"
            anki2_path = temp_path / "collection.anki2"
            sqlite_db_path = temp_path / "uncompressed_anki.db"

            if anki21b_path.exists():
                if progress_callback:
                    progress_callback("Décompression Zstandard...")
                with open(anki21b_path, "rb") as compressed_file:
                    dctx = zstd.ZstdDecompressor()
                    with open(sqlite_db_path, "wb") as uncompressed_file:
                        dctx.copy_stream(compressed_file, uncompressed_file)
            elif anki21_path.exists():
                sqlite_db_path = anki21_path
            elif anki2_path.exists():
                sqlite_db_path = anki2_path
            else:
                shutil.rmtree(temp_dir, ignore_errors=True)
                raise FileNotFoundError("Aucune base SQLite Anki (collection.anki21b, collection.anki21 ou collection.anki2) trouvée dans l'archive.")

            conn = sqlite3.connect(str(sqlite_db_path))
            cursor = conn.cursor()

            try:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = {row[0] for row in cursor.fetchall()}

                col_columns: set[str] = set()
                if "col" in tables:
                    cursor.execute("PRAGMA table_info(col)")
                    col_columns = {row[1] for row in cursor.fetchall()}

                # 1. Decks
                raw_decks: list[dict[str, Any]] = []
                if "decks" in col_columns:
                    try:
                        cursor.execute("SELECT decks FROM col")
                        decks_row = cursor.fetchone()
                        if decks_row and decks_row[0]:
                            decks_json = json.loads(decks_row[0])
                            raw_decks = list(decks_json.values())
                    except Exception as e:
                        logger.warning("Erreur extraction decks col: %s", e)

                if not raw_decks and "decks" in tables:
                    try:
                        cursor.execute("SELECT id, name FROM decks")
                        for row in cursor.fetchall():
                            name_str = row[1].replace("\x1f", "::") if row[1] else "Par défaut"
                            raw_decks.append({"id": row[0], "name": name_str})
                    except Exception as e:
                        logger.warning("Erreur extraction table decks: %s", e)

                if not raw_decks:
                    raw_decks = [{"id": 1, "name": "Par défaut"}]

                deck_id_to_name: dict[int, str] = {int(d.get("id", 0)): d.get("name", "Par défaut") for d in raw_decks}

                # 2. Modèles (NoteTypes)
                raw_models: dict[int, dict[str, Any]] = {}
                if "models" in col_columns:
                    try:
                        cursor.execute("SELECT models FROM col")
                        models_row = cursor.fetchone()
                        if models_row and models_row[0]:
                            models_json = json.loads(models_row[0])
                            for mid_str, m_info in models_json.items():
                                raw_models[int(mid_str)] = {
                                    "name": m_info.get("name", "Unknown"),
                                    "fields": [f["name"] for f in m_info.get("flds", [])],
                                    "templates": m_info.get("tmpls", []),
                                    "css": m_info.get("css", ""),
                                }
                    except Exception as e:
                        logger.warning("Erreur extraction models col: %s", e)

                if not raw_models and "notetypes" in tables:
                    try:
                        cursor.execute("SELECT id, name, config FROM notetypes")
                        for row in cursor.fetchall():
                            mid, name, config_blob = row
                            field_names = []
                            if "fields" in tables:
                                try:
                                    cursor.execute("SELECT name FROM fields WHERE ntid=? ORDER BY ord", (mid,))
                                    field_names = [f[0] for f in cursor.fetchall()]
                                except Exception as f_err:
                                    logger.debug("Remarque extraction champs notetype %s: %s", mid, f_err)

                            css_style = ""
                            if config_blob:
                                try:
                                    c_str = config_blob.decode("utf-8", errors="ignore") if isinstance(config_blob, bytes | bytearray) else str(config_blob)
                                    if c_str.strip().startswith("{"):
                                        c_json = json.loads(c_str)
                                        css_style = c_json.get("css", "")
                                except Exception:
                                    pass
                                if not css_style and isinstance(config_blob, bytes | bytearray):
                                    css_style = self.extract_pb_string(bytes(config_blob), 3)

                            tmpls = []
                            if "templates" in tables:
                                try:
                                    cursor.execute("SELECT name, config FROM templates WHERE ntid=? ORDER BY ord", (mid,))
                                    for t_row in cursor.fetchall():
                                        t_name, t_config = t_row
                                        qfmt = ""
                                        afmt = ""
                                        if t_config:
                                            try:
                                                cfg_str = t_config.decode("utf-8", errors="ignore") if isinstance(t_config, bytes | bytearray) else str(t_config)
                                                if cfg_str.strip().startswith("{"):
                                                    cfg_json = json.loads(cfg_str)
                                                    qfmt = cfg_json.get("qfmt", cfg_json.get("q_format", ""))
                                                    afmt = cfg_json.get("afmt", cfg_json.get("a_format", ""))
                                            except Exception:
                                                pass

                                            if not qfmt and isinstance(t_config, bytes | bytearray):
                                                qfmt = self.extract_pb_string(bytes(t_config), 1)
                                            if not afmt and isinstance(t_config, bytes | bytearray):
                                                afmt = self.extract_pb_string(bytes(t_config), 2)

                                        # Si le gabarit n'a pas pu être extrait, créer un gabarit par défaut basé sur les champs réels
                                        if not qfmt and field_names:
                                            qfmt = f"{{{{{field_names[0]}}}}}"
                                        if not afmt and field_names:
                                            back_f = field_names[1] if len(field_names) > 1 else field_names[0]
                                            afmt = f"{{{{FrontSide}}}}<hr id=answer>{{{{{back_f}}}}}"

                                        tmpls.append({"name": t_name, "qfmt": qfmt, "afmt": afmt})
                                except Exception as t_err:
                                    logger.debug("Remarque extraction templates notetype %s: %s", mid, t_err)
                            raw_models[mid] = {
                                "name": name,
                                "fields": field_names,
                                "templates": tmpls,
                                "css": css_style,
                            }
                    except Exception as e:
                        logger.warning("Erreur extraction table notetypes: %s", e)

                # 3. Cards table pour le mapping multi-cartes et statistiques
                note_cards_map: dict[int, list[dict[str, Any]]] = {}
                if "cards" in tables:
                    try:
                        cursor.execute("SELECT * FROM cards ORDER BY id")
                        col_names = [desc[0] for desc in cursor.description]
                        for crow in cursor.fetchall():
                            cdict = dict(zip(col_names, crow, strict=False))
                            nid = cdict["nid"]
                            card_entry = {
                                "id": cdict["id"],
                                "did": cdict.get("did", 1),
                                "ord": cdict.get("ord", 0),
                                "ivl": cdict.get("ivl", 0),
                                "reps": cdict.get("reps", 0),
                                "lapses": cdict.get("lapses", 0),
                                "flags": int(cdict.get("flags", 0) or 0) & 7,
                            }
                            note_cards_map.setdefault(nid, []).append(card_entry)
                    except Exception as e:
                        logger.warning("Erreur mapping cards/decks: %s", e)

                # 4. Extraction & Classification des notes
                new_notes: list[dict[str, Any]] = []
                silent_updates: list[dict[str, Any]] = []
                conflicts: list[ConflictItem] = []
                identical_count = 0

                cursor.execute("SELECT id, guid, mid, tags, flds FROM notes")
                for row in cursor.fetchall():
                    nid, guid, mid, tags_raw, flds_raw = row
                    try:
                        int_mid = int(mid)
                    except (ValueError, TypeError):
                        int_mid = 0
                    fallback_model: dict[str, Any] = {"name": "Basic", "fields": ["Front", "Back"], "templates": [], "css": ""}
                    model_info = raw_models.get(int_mid, fallback_model)
                    field_names = model_info.get("fields", [])
                    field_values = flds_raw.split("\x1f")

                    if not field_names:
                        field_names = [f"Field_{i + 1}" for i in range(len(field_values))]
                    elif len(field_values) > len(field_names):
                        field_names = list(field_names) + [f"Field_{i + 1}" for i in range(len(field_names), len(field_values))]

                    content_dict = dict(zip(field_names, field_values, strict=False))
                    tags = tags_raw.strip().split(" ") if tags_raw and tags_raw.strip() else []

                    attached_cards = note_cards_map.get(nid, [{"ord": 0, "did": 1, "ivl": 0, "reps": 0, "lapses": 0, "flags": 0}])
                    did = attached_cards[0]["did"] if attached_cards else 1
                    deck_name = deck_id_to_name.get(did, "Par défaut")

                    existing_note = NoteModel.get_or_none(NoteModel.guid == guid)
                    if not existing_note and nid is not None:
                        existing_note = NoteModel.get_or_none(NoteModel.anki_id == nid)

                    if not existing_note:
                        new_notes.append(
                            {
                                "guid": guid,
                                "anki_id": nid,
                                "deck_name": deck_name,
                                "notetype_name": model_info["name"],
                                "model_info": model_info,
                                "tags": tags,
                                "content": content_dict,
                                "field_names": field_names,
                                "cards": attached_cards,
                            }
                        )
                    else:
                        if self._evaluate_existing_note(
                            existing_note=existing_note,
                            incoming_content=content_dict,
                            deck_name=deck_name,
                            incoming_tags=tags,
                            notetype_name=model_info["name"],
                            silent_updates=silent_updates,
                            conflicts=conflicts,
                            attached_cards=attached_cards,
                        ):
                            identical_count += 1
            finally:
                conn.close()

            return ImportAnalysisResult(
                temp_dir=temp_dir,
                source_type="apkg",
                sqlite_path=str(sqlite_db_path),
                txt_path=None,
                new_notes=new_notes,
                silent_updates=silent_updates,
                identical_count=identical_count,
                conflicts=conflicts,
                media_map=media_map,
                raw_models=raw_models,
                raw_decks=raw_decks,
            )
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise

    def _evaluate_existing_note(
        self,
        existing_note: NoteModel,
        incoming_content: dict[str, str],
        deck_name: str,
        incoming_tags: list[str],
        notetype_name: str,
        silent_updates: list[dict[str, Any]],
        conflicts: list[ConflictItem],
        attached_cards: list[dict[str, Any]] | None = None,
    ) -> bool:
        local_version = NoteVersionModel.get_or_none(note=existing_note, is_active=True)
        if not local_version:
            local_version = NoteVersionModel.select().where(NoteVersionModel.note == existing_note).order_by(NoteVersionModel.version_number.desc()).first()

        local_content: dict[str, str] = {}
        if local_version and local_version.content:
            try:
                local_content = json.loads(local_version.content)
            except Exception:
                pass  # nosec B110

        local_text = " ".join(str(v).strip() for v in local_content.values())
        incoming_text = " ".join(str(v).strip() for v in incoming_content.values())
        content_differs = local_text != incoming_text

        has_manual_edits = NoteVersionModel.select().where((NoteVersionModel.note == existing_note) & (NoteVersionModel.source.in_(["manual", "merge", "restore_v"]))).exists()

        if content_differs and has_manual_edits:
            sim = get_similarity(local_text, incoming_text)
            diffs = self.compute_field_diffs(local_content, incoming_content)
            local_deck = "Par défaut"
            if hasattr(existing_note, "cards") and list(existing_note.cards):
                c = list(existing_note.cards)[0]
                if c.deck:
                    local_deck = c.deck.name

            local_tags: list[str] = []
            if existing_note.tags:
                try:
                    parsed = json.loads(str(existing_note.tags))
                    if isinstance(parsed, list):
                        local_tags = parsed
                except Exception:
                    pass  # nosec B110

            conflicts.append(
                ConflictItem(
                    note_id=existing_note.id,
                    guid=str(existing_note.guid),
                    note_type_name=notetype_name,
                    local_content=local_content,
                    incoming_content=incoming_content,
                    local_deck=local_deck,
                    incoming_deck=deck_name,
                    local_tags=local_tags,
                    incoming_tags=incoming_tags,
                    similarity_score=round(sim * 100, 1),
                    field_diffs=diffs,
                )
            )
            return False
        else:
            silent_updates.append(
                {
                    "note_id": existing_note.id,
                    "guid": existing_note.guid,
                    "deck_name": deck_name,
                    "tags": incoming_tags,
                    "content": incoming_content,
                    "cards": attached_cards or [],
                    "reason": "incoming_newer" if content_differs else "identical",
                }
            )
            return not content_differs

    def commit_import(
        self,
        analysis: ImportAnalysisResult,
        conflict_resolutions: dict[str, dict[str, Any]] | None = None,
        target_deck_id: int | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> dict[str, int]:
        """
        Effectue l'écriture finale en base de données de manière atomique.
        Applique les créations, mises à jour silencieuses et résolutions de conflits arbitrées.
        """
        resolutions = conflict_resolutions or {}
        created_count = 0
        updated_count = 0
        merged_count = 0
        media_count = 0

        target_deck_override = DeckModel.get_or_none(DeckModel.id == target_deck_id) if target_deck_id else None
        deck_id_to_name: dict[int, str] = {int(d.get("id", 0)): d.get("name", "Par défaut") for d in analysis.raw_decks}

        with db.atomic():
            # 1. Enregistrement des Decks & Sous-Decks
            deck_cache: dict[str, DeckModel] = {}
            for d in analysis.raw_decks:
                d_name = d.get("name", "Par défaut")
                d_id = d.get("id")
                self._ensure_deck(d_name, deck_cache, anki_id=d_id)

            # 2. Enregistrement des NoteTypes
            model_cache: dict[str, NoteTypeModel] = {}
            for _mid, m_info in analysis.raw_models.items():
                m_name = m_info.get("name", "Basic")
                fields_schema = json.dumps(m_info.get("fields", ["Front", "Back"]))
                templates_json = json.dumps(m_info.get("templates", []), ensure_ascii=False)
                css = m_info.get("css", "")

                existing_nt = NoteTypeModel.get_or_none(NoteTypeModel.name == m_name)
                if existing_nt:
                    # Vérifier si ce modèle local est vierge (0 notes associées en base)
                    notes_count = NoteModel.select().where(NoteModel.note_type == existing_nt).count()
                    if notes_count == 0:
                        # Modèle vierge : on applique directement la structure et les templates du modèle entrant
                        existing_nt.fields_schema = fields_schema
                        existing_nt.templates = templates_json
                        if css:
                            existing_nt.css_style = css
                        existing_nt.save()
                        nt_obj = existing_nt
                    else:
                        # Le modèle local est déjà utilisé par des notes existantes
                        existing_fields = json.loads(existing_nt.fields_schema) if existing_nt.fields_schema else []
                        incoming_fields = m_info.get("fields", [])
                        existing_tmpls = json.loads(existing_nt.templates) if existing_nt.templates else []
                        incoming_tmpls = m_info.get("templates", [])

                        if existing_fields == incoming_fields and len(existing_tmpls) == len(incoming_tmpls):
                            # Schéma compatible, réutilisation sans duplication
                            nt_obj = existing_nt
                        else:
                            # Conflit de structure : créer un modèle avec suffixe unique pour préserver l'intégrité
                            unique_name = f"{m_name} (Importé)"
                            counter = 1
                            while NoteTypeModel.select().where(NoteTypeModel.name == unique_name).exists():
                                counter += 1
                                unique_name = f"{m_name} (Importé {counter})"
                            nt_obj = NoteTypeModel.create(
                                name=unique_name,
                                fields_schema=fields_schema,
                                templates=templates_json,
                                css_style=css,
                            )
                else:
                    nt_obj = NoteTypeModel.create(
                        name=m_name,
                        fields_schema=fields_schema,
                        templates=templates_json,
                        css_style=css,
                    )
                model_cache[m_name] = nt_obj
                model_cache[str(_mid)] = nt_obj

            # 3. Insertion des Nouvelles Notes et de leurs Cartes
            for n_info in analysis.new_notes:
                deck_name = n_info["deck_name"]
                nt_name = n_info["notetype_name"]
                note_type_model: NoteTypeModel | None = model_cache.get(nt_name)
                if not note_type_model:
                    # Essayer via model_info si présent
                    m_info = n_info.get("model_info", {})
                    if m_info and m_info.get("name") in model_cache:
                        note_type_model = model_cache[m_info["name"]]
                    else:
                        existing_nt = NoteTypeModel.get_or_none(NoteTypeModel.name == nt_name)
                        if existing_nt:
                            note_type_model = existing_nt
                        else:
                            fields_list = n_info.get("field_names", ["Front", "Back"])
                            back_f = fields_list[1] if len(fields_list) > 1 else fields_list[0]
                            dyn_tmpl = json.dumps(
                                [{"name": "Carte 1", "qfmt": f"{{{{{fields_list[0]}}}}}", "afmt": f"{{{{FrontSide}}}}<hr id=answer>{{{{{back_f}}}}}"}],
                                ensure_ascii=False,
                            )
                            note_type_model = NoteTypeModel.create(
                                name=nt_name,
                                fields_schema=json.dumps(fields_list),
                                templates=dyn_tmpl,
                                css_style="",
                            )
                            model_cache[nt_name] = note_type_model

                assert note_type_model is not None
                anki_id_val = n_info.get("anki_id")
                if anki_id_val and NoteModel.select().where(NoteModel.anki_id == anki_id_val).exists():
                    anki_id_val = None

                note = NoteModel.create(
                    guid=n_info["guid"],
                    anki_id=anki_id_val,
                    note_type=note_type_model,
                    tags=json.dumps(n_info.get("tags", [])),
                    status="imported",
                )
                NoteVersionModel.create(
                    note=note,
                    version_number=1,
                    content=json.dumps(n_info["content"], ensure_ascii=False),
                    source="import",
                    is_active=True,
                )

                cards_list = n_info.get("cards") or [{"ord": 0, "did": None, "ivl": 0, "reps": 0, "lapses": 0}]
                for cinfo in cards_list:
                    c_ord = cinfo.get("ord", 0)
                    c_did = cinfo.get("did")
                    c_deck = target_deck_override
                    if not c_deck:
                        c_deck_name = deck_id_to_name.get(c_did, deck_name) if c_did else deck_name
                        c_deck = self._ensure_deck(c_deck_name, deck_cache)

                    c_anki_id = cinfo.get("id")
                    if c_anki_id and CardModel.select().where(CardModel.anki_id == c_anki_id).exists():
                        c_anki_id = None

                    CardModel.get_or_create(
                        note=note,
                        template_index=c_ord,
                        defaults={
                            "deck": c_deck,
                            "anki_id": c_anki_id,
                            "ivl": cinfo.get("ivl", 0),
                            "reps": cinfo.get("reps", 0),
                            "lapses": cinfo.get("lapses", 0),
                            "flags": cinfo.get("flags", 0),
                        },
                    )
                created_count += 1

            # 4. Mises à jour silencieuses (Decks/Tags ou contenu non modifié localement)
            for u_info in analysis.silent_updates:
                u_note = NoteModel.get_or_none(NoteModel.id == u_info["note_id"])
                if not u_note:
                    continue

                # Mise à jour Deck si changé
                if not target_deck_override and u_info.get("deck_name"):
                    d_name = u_info["deck_name"]
                    d_obj = self._ensure_deck(d_name, deck_cache)
                    for card in u_note.cards:
                        if card.deck != d_obj:
                            card.deck = d_obj
                            card.save()

                if u_info.get("cards"):
                    for cinfo in u_info["cards"]:
                        c_ord = cinfo.get("ord", 0)
                        card_match = CardModel.get_or_none(CardModel.note == u_note, CardModel.template_index == c_ord)
                        if card_match:
                            if cinfo.get("ivl"):
                                card_match.ivl = cinfo["ivl"]
                            if cinfo.get("reps"):
                                card_match.reps = cinfo["reps"]
                            if cinfo.get("lapses"):
                                card_match.lapses = cinfo["lapses"]
                            if "flags" in cinfo:
                                card_match.flags = cinfo["flags"]
                            card_match.save()

                # Mise à jour version si raison == incoming_newer
                if u_info.get("reason") == "incoming_newer" and u_info.get("content"):
                    u_note.add_version(u_info["content"], source="import")

                if u_info.get("tags"):
                    u_note.tags = json.dumps(u_info["tags"])
                    u_note.save()
                updated_count += 1

            # 5. Application des Résolutions de Conflits
            for conflict in analysis.conflicts:
                guid = conflict.guid
                res = resolutions.get(guid)
                c_note = NoteModel.get_or_none(NoteModel.id == conflict.note_id)
                if not c_note:
                    continue

                if res:
                    choice = res.get("choice", "merged")
                    resolved_content = res.get("content", conflict.local_content)
                    resolved_deck_name = res.get("deck", conflict.local_deck)
                    resolved_tags = res.get("tags", conflict.local_tags)

                    if choice == "incoming":
                        resolved_content = conflict.incoming_content
                        resolved_deck_name = conflict.incoming_deck
                        resolved_tags = conflict.incoming_tags
                    elif choice == "local":
                        resolved_content = conflict.local_content
                        resolved_deck_name = conflict.local_deck
                        resolved_tags = conflict.local_tags

                    # Ajout d'une version avec source='merge'
                    c_note.add_version(resolved_content, source="merge")

                    d_obj = self._ensure_deck(resolved_deck_name, deck_cache)
                    for card in c_note.cards:
                        card.deck = d_obj
                        card.save()

                    c_note.tags = json.dumps(resolved_tags)
                    c_note.save()
                    merged_count += 1

            # 6. Extraction & Copie des Médias
            if analysis.temp_dir and Path(analysis.temp_dir).exists():
                temp_p = Path(analysis.temp_dir)
                for file_id, filename in analysis.media_map.items():
                    src_file = temp_p / file_id
                    if src_file.exists() and src_file.is_file():
                        dest_file = self.media_dir / filename
                        try:
                            with open(src_file, "rb") as sf:
                                header = sf.read(4)
                                sf.seek(0)
                                if header == b"\x28\xb5\x2f\xfd":
                                    dctx = zstd.ZstdDecompressor()
                                    with open(dest_file, "wb") as df:
                                        dctx.copy_stream(sf, df)
                                else:
                                    with open(dest_file, "wb") as df:
                                        shutil.copyfileobj(sf, df)

                            sha256 = hashlib.sha256()
                            with open(dest_file, "rb") as mf:
                                for chunk in iter(lambda: mf.read(65536), b""):
                                    sha256.update(chunk)
                            checksum = sha256.hexdigest()

                            mime_type, _ = mimetypes.guess_type(str(dest_file))
                            mime_type = mime_type or "application/octet-stream"

                            MediaModel.get_or_create(
                                checksum=checksum,
                                defaults={
                                    "filename": filename,
                                    "original_name": filename,
                                    "mime_type": mime_type,
                                },
                            )
                            media_count += 1
                        except Exception as m_err:
                            logger.warning("Erreur copie/enregistrement média '%s' (%s): %s", file_id, filename, m_err)

        # Nettoyage dossier temporaire
        analysis.cleanup()

        logger.info(
            "Validation de l'import achevée : %d créées, %d synchronisées, %d fusionnées, %d médias",
            created_count,
            updated_count,
            merged_count,
            media_count,
        )

        if progress_callback:
            progress_callback(f"Import terminé : {created_count} créées, {updated_count} synchronisées, {merged_count} conflits fusionnés.")

        return {
            "created": created_count,
            "updated": updated_count,
            "merged": merged_count,
            "media": media_count,
        }
