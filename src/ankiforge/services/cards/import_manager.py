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
import json
import logging
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


class ImportManager:
    """Gestionnaire central d'ingestion et de fusion des collections Anki."""

    def __init__(self) -> None:
        self.media_dir = get_media_dir()
        self.media_dir.mkdir(parents=True, exist_ok=True)

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

        for row in cards:
            guid = row[header_dict["guid"]] if "guid" in header_dict and header_dict["guid"] < len(row) else str(uuid.uuid4())
            deck_name = row[header_dict["deck"]] if "deck" in header_dict and header_dict["deck"] < len(row) else "Par défaut"
            notetype_name = row[header_dict["notetype"]] if "notetype" in header_dict and header_dict["notetype"] < len(row) else "Basic"
            tags = row[header_dict["tags"]].strip().split() if "tags" in header_dict and header_dict["tags"] < len(row) else []

            meta_indices = header_dict.values()
            content_values = [val for idx, val in enumerate(row) if idx not in meta_indices]
            field_names = [f"Field_{i + 1}" for i in range(len(content_values))]
            content_dict = dict(zip(field_names, content_values, strict=False))

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
                self._evaluate_existing_note(existing_note, content_dict, deck_name, tags, notetype_name, silent_updates, conflicts, identical_count)

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
        )

    def _analyze_apkg(self, apkg_path: Path, progress_callback: Callable[[str], None] | None = None) -> ImportAnalysisResult:
        temp_dir = tempfile.mkdtemp(prefix="ankiforge_import_")
        temp_path = Path(temp_dir)

        try:
            with zipfile.ZipFile(apkg_path, "r") as zf:
                zf.extractall(temp_path)
        except zipfile.BadZipFile as e:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise ValueError(f"Le fichier {apkg_path.name} n'est pas une archive ZIP/APKG valide.") from e

        # Lecture de media map
        media_map: dict[str, str] = {}
        media_json_path = temp_path / "media"
        if media_json_path.exists():
            try:
                with open(media_json_path, encoding="utf-8") as f:
                    media_map = json.load(f)
            except Exception as e:
                logger.warning("Impossible de lire le fichier media du package: %s", e)

        # Détection SQLite / Zstandard
        anki21b_path = temp_path / "collection.anki21b"
        anki2_path = temp_path / "collection.anki2"
        sqlite_db_path = temp_path / "uncompressed_anki.db"

        if anki21b_path.exists():
            if progress_callback:
                progress_callback("Décompression Zstandard...")
            with open(anki21b_path, "rb") as compressed_file:
                dctx = zstd.ZstdDecompressor()
                with open(sqlite_db_path, "wb") as uncompressed_file:
                    dctx.copy_stream(compressed_file, uncompressed_file)
        elif anki2_path.exists():
            sqlite_db_path = anki2_path
        else:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise FileNotFoundError("Aucune base SQLite Anki (collection.anki2 ou anki21b) trouvée dans l'archive.")

        conn = sqlite3.connect(str(sqlite_db_path))
        cursor = conn.cursor()

        # 1. Decks
        raw_decks: list[dict[str, Any]] = []
        try:
            cursor.execute("SELECT decks FROM col")
            decks_raw = cursor.fetchone()[0]
            if decks_raw:
                decks_json = json.loads(decks_raw)
                raw_decks = list(decks_json.values())
            else:
                cursor.execute("SELECT id, name FROM decks")
                for row in cursor.fetchall():
                    raw_decks.append({"id": row[0], "name": row[1].replace("\x1f", "::")})
        except Exception as e:
            logger.warning("Erreur extraction decks: %s", e)

        deck_id_to_name: dict[int, str] = {int(d.get("id", 0)): d.get("name", "Par défaut") for d in raw_decks}

        # 2. Modèles (NoteTypes)
        raw_models: dict[int, dict[str, Any]] = {}
        try:
            cursor.execute("SELECT models FROM col")
            models_raw = cursor.fetchone()[0]
            if models_raw:
                models_json = json.loads(models_raw)
                for mid_str, m_info in models_json.items():
                    raw_models[int(mid_str)] = {
                        "name": m_info.get("name", "Unknown"),
                        "fields": [f["name"] for f in m_info.get("flds", [])],
                        "templates": m_info.get("tmpls", []),
                        "css": m_info.get("css", ""),
                    }
            else:
                cursor.execute("SELECT id, name, config FROM notetypes")
                for row in cursor.fetchall():
                    mid, name, config_blob = row
                    field_names = []
                    try:
                        cursor.execute("SELECT name FROM fields WHERE ntid=? ORDER BY ord", (mid,))
                        field_names = [f[0] for f in cursor.fetchall()]
                    except Exception as f_err:
                        logger.debug("Remarque sur l'extraction des champs pour notetype ID=%s : %s", mid, f_err)
                    css_style = self.extract_pb_string(config_blob, 3) if config_blob else ""
                    tmpls = []
                    try:
                        cursor.execute("SELECT name, config FROM templates WHERE ntid=? ORDER BY ord", (mid,))
                        for t_row in cursor.fetchall():
                            t_name, t_config = t_row
                            qfmt = self.extract_pb_string(t_config, 1) if t_config else ""
                            afmt = self.extract_pb_string(t_config, 2) if t_config else ""
                            tmpls.append({"name": t_name, "qfmt": qfmt, "afmt": afmt})
                    except Exception as t_err:
                        logger.debug("Remarque sur l'extraction des templates pour notetype ID=%s : %s", mid, t_err)
                    raw_models[mid] = {"name": name, "fields": field_names, "templates": tmpls, "css": css_style}
        except Exception as e:
            logger.warning("Erreur extraction models: %s", e)

        # 3. Cards table pour le mapping note_id -> deck_id
        note_to_deck: dict[int, int] = {}
        try:
            cursor.execute("SELECT nid, did FROM cards")
            for nid, did in cursor.fetchall():
                note_to_deck[nid] = did
        except Exception as e:
            logger.warning("Erreur mapping cards/decks: %s", e)

        # 4. Extraction & Classification des notes
        new_notes: list[dict[str, Any]] = []
        silent_updates: list[dict[str, Any]] = []
        conflicts: list[ConflictItem] = []
        identical_count = 0

        try:
            cursor.execute("SELECT id, guid, mid, tags, flds FROM notes")
            for row in cursor.fetchall():
                nid, guid, mid, tags_raw, flds_raw = row
                model_info = raw_models.get(mid, {"name": "Basic", "fields": ["Front", "Back"], "templates": [], "css": ""})
                field_names = model_info.get("fields", [])
                field_values = flds_raw.split("\x1f")

                if not field_names:
                    field_names = [f"Field_{i + 1}" for i in range(len(field_values))]

                content_dict = dict(zip(field_names, field_values, strict=False))
                tags = tags_raw.strip().split(" ") if tags_raw and tags_raw.strip() else []

                did = note_to_deck.get(nid, 1)
                deck_name = deck_id_to_name.get(did, "Par défaut")

                existing_note = NoteModel.get_or_none(NoteModel.guid == guid)
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
                        }
                    )
                else:
                    # Évaluation selon la règle 11
                    local_version = NoteVersionModel.get_or_none(note=existing_note, is_active=True)
                    if not local_version:
                        local_version = NoteVersionModel.select().where(NoteVersionModel.note == existing_note).order_by(NoteVersionModel.version_number.desc()).first()

                    local_content = {}
                    if local_version and local_version.content:
                        try:
                            local_content = json.loads(local_version.content)
                        except Exception as c_err:
                            logger.debug("Remarque sur le décodage du contenu local note ID=%d : %s", existing_note.id, c_err)

                    # Normalisation pour comparaison
                    local_text = " ".join(str(v).strip() for v in local_content.values())
                    incoming_text = " ".join(str(v).strip() for v in content_dict.values())

                    content_differs = local_text != incoming_text

                    # Vérifier si la note a été modifiée manuellement dans AnkiForge
                    has_manual_edits = NoteVersionModel.select().where((NoteVersionModel.note == existing_note) & (NoteVersionModel.source.in_(["manual", "merge", "restore_v"]))).exists()

                    if content_differs and has_manual_edits:
                        # VRAI CONFLIT (Règle 11)
                        sim = get_similarity(local_text, incoming_text)
                        diffs = self.compute_field_diffs(local_content, content_dict)
                        local_deck = "Par défaut"
                        if hasattr(existing_note, "cards") and list(existing_note.cards):
                            c = list(existing_note.cards)[0]
                            if c.deck:
                                local_deck = c.deck.name

                        local_tags = []
                        if existing_note.tags:
                            try:
                                parsed = json.loads(existing_note.tags)
                                if isinstance(parsed, list):
                                    local_tags = parsed
                            except Exception as tag_err:
                                logger.debug("Remarque sur le décodage des tags de la note ID=%d : %s", existing_note.id, tag_err)

                        conflicts.append(
                            ConflictItem(
                                note_id=existing_note.id,
                                guid=guid,
                                note_type_name=existing_note.note_type.name if existing_note.note_type else "Inconnu",
                                local_content=local_content,
                                incoming_content=content_dict,
                                local_deck=local_deck,
                                incoming_deck=deck_name,
                                local_tags=local_tags,
                                incoming_tags=tags,
                                similarity_score=round(sim * 100, 1),
                                field_diffs=diffs,
                            )
                        )
                    elif content_differs and not has_manual_edits:
                        # Pas de modif manuelle locale : mise à jour silencieuse avec nouvelle version
                        silent_updates.append(
                            {
                                "note_id": existing_note.id,
                                "guid": guid,
                                "deck_name": deck_name,
                                "tags": tags,
                                "content": content_dict,
                                "reason": "incoming_newer",
                            }
                        )
                    else:
                        # Contenu identique : mise à jour deck/tags silencieuse si besoin
                        silent_updates.append(
                            {
                                "note_id": existing_note.id,
                                "guid": guid,
                                "deck_name": deck_name,
                                "tags": tags,
                                "content": content_dict,
                                "reason": "identical_content_metadata_sync",
                            }
                        )
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

    def _evaluate_existing_note(
        self,
        existing_note: NoteModel,
        incoming_content: dict[str, str],
        deck_name: str,
        incoming_tags: list[str],
        notetype_name: str,
        silent_updates: list[dict[str, Any]],
        conflicts: list[ConflictItem],
        identical_count: int,
    ) -> None:
        local_version = NoteVersionModel.get_or_none(note=existing_note, is_active=True)
        if not local_version:
            local_version = NoteVersionModel.select().where(NoteVersionModel.note == existing_note).order_by(NoteVersionModel.version_number.desc()).first()

        local_content = {}
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

            local_tags = []
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
        else:
            silent_updates.append(
                {
                    "note_id": existing_note.id,
                    "guid": existing_note.guid,
                    "deck_name": deck_name,
                    "tags": incoming_tags,
                    "content": incoming_content,
                    "reason": "incoming_newer" if content_differs else "identical",
                }
            )

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

        with db.atomic():
            # 1. Enregistrement des Decks & Sous-Decks
            deck_cache: dict[str, DeckModel] = {}
            for d in analysis.raw_decks:
                name = d.get("name", "Par défaut")
                parent = None
                if "::" in name:
                    parent_name = name.rsplit("::", 1)[0]
                    parent, _ = DeckModel.get_or_create(name=parent_name)
                deck_obj, _ = DeckModel.get_or_create(name=name, defaults={"parent_deck": parent, "anki_id": d.get("id")})
                deck_cache[name] = deck_obj

            # 2. Enregistrement des NoteTypes
            model_cache: dict[str, NoteTypeModel] = {}
            for _mid, m_info in analysis.raw_models.items():
                m_name = m_info.get("name", "Basic")
                fields_schema = json.dumps(m_info.get("fields", ["Front", "Back"]))
                templates_json = json.dumps(m_info.get("templates", []), ensure_ascii=False)
                css = m_info.get("css", "")

                nt_obj, _ = NoteTypeModel.get_or_create(
                    name=m_name,
                    defaults={"fields_schema": fields_schema, "templates": templates_json, "css_style": css},
                )
                model_cache[m_name] = nt_obj

            # 3. Insertion des Nouvelles Notes
            for n_info in analysis.new_notes:
                deck_name = n_info["deck_name"]
                if target_deck_override:
                    deck_obj = target_deck_override
                else:
                    deck_obj = deck_cache.get(deck_name)
                    if not deck_obj:
                        parent = None
                        if "::" in deck_name:
                            parent_name = deck_name.rsplit("::", 1)[0]
                            parent, _ = DeckModel.get_or_create(name=parent_name)
                        deck_obj, _ = DeckModel.get_or_create(name=deck_name, defaults={"parent_deck": parent})
                        deck_cache[deck_name] = deck_obj

                nt_name = n_info["notetype_name"]
                nt_obj = model_cache.get(nt_name)
                if not nt_obj:
                    nt_obj, _ = NoteTypeModel.get_or_create(
                        name=nt_name,
                        defaults={
                            "fields_schema": json.dumps(n_info.get("field_names", ["Front", "Back"])),
                            "templates": "[]",
                            "css_style": "",
                        },
                    )
                    model_cache[nt_name] = nt_obj

                note = NoteModel.create(
                    guid=n_info["guid"],
                    anki_id=n_info.get("anki_id"),
                    note_type=nt_obj,
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
                CardModel.get_or_create(note=note, deck=deck_obj)
                created_count += 1

            # 4. Mises à jour silencieuses (Decks/Tags ou contenu non modifié localement)
            for u_info in analysis.silent_updates:
                note = NoteModel.get_or_none(NoteModel.id == u_info["note_id"])
                if not note:
                    continue

                # Mise à jour Deck si changé
                if not target_deck_override and u_info.get("deck_name"):
                    d_name = u_info["deck_name"]
                    d_obj = deck_cache.get(d_name)
                    if not d_obj:
                        parent = None
                        if "::" in d_name:
                            parent_name = d_name.rsplit("::", 1)[0]
                            parent, _ = DeckModel.get_or_create(name=parent_name)
                        d_obj, _ = DeckModel.get_or_create(name=d_name, defaults={"parent_deck": parent})
                        deck_cache[d_name] = d_obj
                    for card in note.cards:
                        if card.deck != d_obj:
                            card.deck = d_obj
                            card.save()

                # Mise à jour version si raison == incoming_newer
                if u_info.get("reason") == "incoming_newer" and u_info.get("content"):
                    note.add_version(u_info["content"], source="import")

                if u_info.get("tags"):
                    note.tags = json.dumps(u_info["tags"])
                    note.save()
                updated_count += 1

            # 5. Application des Résolutions de Conflits
            for conflict in analysis.conflicts:
                guid = conflict.guid
                res = resolutions.get(guid)
                note = NoteModel.get_or_none(NoteModel.id == conflict.note_id)
                if not note:
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
                    note.add_version(resolved_content, source="merge")

                    # Mise à jour deck
                    d_obj = deck_cache.get(resolved_deck_name)
                    if not d_obj:
                        d_obj, _ = DeckModel.get_or_create(name=resolved_deck_name)
                        deck_cache[resolved_deck_name] = d_obj
                    for card in note.cards:
                        card.deck = d_obj
                        card.save()

                    note.tags = json.dumps(resolved_tags)
                    note.save()
                    merged_count += 1
                else:
                    # Défaut : Garder localement intact
                    pass

            # 6. Extraction & Copie des Médias
            if analysis.temp_dir and Path(analysis.temp_dir).exists():
                temp_p = Path(analysis.temp_dir)
                for file_id, filename in analysis.media_map.items():
                    src_file = temp_p / file_id
                    if src_file.exists():
                        dest_file = self.media_dir / filename
                        shutil.copy2(src_file, dest_file)
                        MediaModel.get_or_create(
                            filename=filename,
                            defaults={"file_path": str(dest_file), "file_size": dest_file.stat().st_size},
                        )
                        media_count += 1

        # Nettoyage dossier temporaire
        if analysis.temp_dir and Path(analysis.temp_dir).exists():
            shutil.rmtree(analysis.temp_dir, ignore_errors=True)

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
