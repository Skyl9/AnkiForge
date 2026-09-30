"""Import de personas, pipelines et contenu (notes, cartes, médias) entre profils AnkiForge."""

from __future__ import annotations

import hashlib
import json
import logging
import mimetypes
import re
import shutil
from contextlib import nullcontext
from pathlib import Path
from typing import Any, NamedTuple

from peewee import SqliteDatabase

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    LLMConfigModel,
    MediaModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionMediaModel,
    NoteVersionModel,
    PersonaFolderModel,
    PersonaModel,
    PersonaVersionModel,
    PipelineModel,
    PipelineStepModel,
)
from ankiforge.services.profile_manager import ProfileManager
from ankiforge.utils.paths import get_media_dir

logger = logging.getLogger(__name__)


class TransferReport(NamedTuple):
    """Rapport synthétique d'un transfert de contenu inter-profils."""

    notes_imported: int
    notes_updated: int
    notes_skipped: int
    media_transferred: int
    decks_created: int
    note_types_created: int
    errors: list[str]


class ProfileContentTransfer:
    """Transfère du contenu entre bases de profils sans changer la base active."""

    _source_models = [
        LLMConfigModel,
        PersonaFolderModel,
        PersonaModel,
        PersonaVersionModel,
        PipelineModel,
        PipelineStepModel,
    ]

    _card_models = [
        DeckModel,
        NoteTypeModel,
        NoteModel,
        NoteVersionModel,
        CardModel,
        MediaModel,
        NoteVersionMediaModel,
    ]

    @staticmethod
    def list_personas(profile_name: str, profiles_dir: Path | None = None) -> list[str]:
        with ProfileContentTransfer._source_database(profile_name, profiles_dir) as source_db, source_db.bind_ctx(ProfileContentTransfer._source_models):
            return [str(p.name) for p in PersonaModel.select().order_by(PersonaModel.name.asc())]

    @staticmethod
    def list_pipelines(profile_name: str, profiles_dir: Path | None = None) -> list[str]:
        with ProfileContentTransfer._source_database(profile_name, profiles_dir) as source_db, source_db.bind_ctx(ProfileContentTransfer._source_models):
            return [str(p.name) for p in PipelineModel.select().order_by(PipelineModel.name.asc())]

    @staticmethod
    def list_decks(profile_name: str, profiles_dir: Path | None = None) -> list[str]:
        """Retourne la liste ordonnée des noms de paquets du profil source."""
        with ProfileContentTransfer._source_database(profile_name, profiles_dir) as source_db, source_db.bind_ctx([DeckModel]):
            return [str(d.name) for d in DeckModel.select(DeckModel.name).order_by(DeckModel.name.asc())]

    @staticmethod
    def list_tags(profile_name: str, profiles_dir: Path | None = None) -> list[str]:
        """Retourne la liste dédoublée et triée de tous les tags du profil source."""
        with ProfileContentTransfer._source_database(profile_name, profiles_dir) as source_db, source_db.bind_ctx([NoteModel]):
            tags_set: set[str] = set()
            for note in NoteModel.select(NoteModel.tags).where(NoteModel.tags.is_null(False)):
                for tag in ProfileContentTransfer._parse_tags(note.tags):
                    tags_set.add(tag)
            return sorted(tags_set)

    @staticmethod
    def get_transfer_preview(
        source_profile: str,
        deck_names: list[str] | None = None,
        tag_names: list[str] | None = None,
        profiles_dir: Path | None = None,
    ) -> dict[str, Any]:
        """Calcule la métrologie préalable au transfert (notes, modèles, cartes, médias et volume)."""
        notes_payload, media_files = ProfileContentTransfer._extract_notes_data(
            source_profile=source_profile,
            deck_names=deck_names,
            tag_names=tag_names,
            profiles_dir=profiles_dir,
        )
        notes_count = len(notes_payload)
        note_types_count = len({n["note_type"]["name"] for n in notes_payload})
        cards_count = sum(len(n["cards"]) for n in notes_payload)
        media_count = len(media_files)
        total_media_size = sum(m["size"] for m in media_files.values())

        return {
            "notes_count": notes_count,
            "note_types_count": note_types_count,
            "cards_count": cards_count,
            "media_count": media_count,
            "total_media_size": total_media_size,
        }

    @staticmethod
    def transfer_content(
        source_profile: str,
        target_profile: str | None = None,
        deck_names: list[str] | None = None,
        tag_names: list[str] | None = None,
        update_existing_notes: bool = False,
        profiles_dir: Path | None = None,
    ) -> TransferReport:
        """
        Transfère notes, cartes, modèles de cartes et médias d'un profil source vers un profil cible.
        Préserve strictement les GUIDs des notes et déduplique les fichiers médias par MD5.
        """
        notes_payload, media_files = ProfileContentTransfer._extract_notes_data(
            source_profile=source_profile,
            deck_names=deck_names,
            tag_names=tag_names,
            profiles_dir=profiles_dir,
        )

        target_media_dir = ProfileContentTransfer._get_target_media_dir(target_profile, profiles_dir)
        target_media_dir.mkdir(parents=True, exist_ok=True)

        notes_imported = 0
        notes_updated = 0
        notes_skipped = 0
        media_transferred = 0
        decks_created = 0
        note_types_created = 0
        errors: list[str] = []

        target_db_context = ProfileContentTransfer._source_database(target_profile, profiles_dir) if target_profile is not None else NoteModel._meta.database

        with (
            target_db_context if target_profile is not None else nullcontext(),
            target_db_context.bind_ctx(ProfileContentTransfer._card_models) if target_profile is not None else nullcontext(),
            target_db_context.atomic(),
        ):
            target_notetypes: dict[str, NoteTypeModel] = {}
            target_decks: dict[str, DeckModel] = {}

            # 1. Réconciliation des types de notes
            for note_data in notes_payload:
                src_nt = note_data["note_type"]
                nt_name = src_nt["name"]
                if nt_name in target_notetypes:
                    continue

                existing_nt = NoteTypeModel.get_or_none(NoteTypeModel.name == nt_name)
                if existing_nt is None:
                    target_nt = NoteTypeModel.create(
                        name=nt_name,
                        description=src_nt["description"],
                        fields_schema=src_nt["fields_schema"],
                        templates=src_nt["templates"],
                        css_style=src_nt["css_style"],
                    )
                    note_types_created += 1
                else:
                    src_fields = ProfileContentTransfer._normalize_fields_schema(src_nt["fields_schema"])
                    existing_fields = ProfileContentTransfer._normalize_fields_schema(existing_nt.fields_schema)
                    if src_fields == existing_fields:
                        target_nt = existing_nt
                    else:
                        cloned_name = ProfileContentTransfer._available_name(
                            f"{nt_name} (Importé {source_profile})",
                            NoteTypeModel,
                        )
                        target_nt = NoteTypeModel.create(
                            name=cloned_name,
                            description=src_nt["description"],
                            fields_schema=src_nt["fields_schema"],
                            templates=src_nt["templates"],
                            css_style=src_nt["css_style"],
                        )
                        note_types_created += 1

                target_notetypes[nt_name] = target_nt

            # 2. Réconciliation de la hiérarchie des paquets (Decks)
            for note_data in notes_payload:
                for card_data in note_data["cards"]:
                    d_name = card_data["deck_name"]
                    if d_name not in target_decks:
                        parts = d_name.split("::")
                        current_name = ""
                        parent = None
                        last_deck = None
                        for part in parts:
                            current_name = f"{current_name}::{part}" if current_name else part
                            deck, created = DeckModel.get_or_create(
                                name=current_name,
                                defaults={"parent_deck": parent},
                            )
                            if created:
                                decks_created += 1
                            parent = deck
                            last_deck = deck
                        if last_deck:
                            target_decks[d_name] = last_deck

            # 3. Réconciliation des Notes et Cartes
            for note_data in notes_payload:
                existing_note = NoteModel.get_or_none(NoteModel.guid == note_data["guid"])
                if existing_note is not None:
                    if not update_existing_notes:
                        notes_skipped += 1
                        continue
                    active_version = next((v for v in note_data["versions"] if v.get("is_active")), note_data["versions"][-1] if note_data["versions"] else None)
                    if active_version:
                        try:
                            content_dict = json.loads(active_version["content"])
                        except Exception:
                            content_dict = {"content": active_version["content"]}
                        existing_note.add_version(content_dict, source="import")
                    if note_data.get("tags"):
                        existing_note.tags = note_data["tags"]
                        existing_note.save()
                    notes_updated += 1
                else:
                    target_nt = target_notetypes[note_data["note_type"]["name"]]
                    new_note = NoteModel.create(
                        guid=note_data["guid"],
                        note_type=target_nt,
                        tags=note_data.get("tags"),
                        status=note_data.get("status", "new"),
                        anki_id=note_data.get("anki_id"),
                        anki_content_hash=note_data.get("anki_content_hash"),
                    )

                    for v_data in note_data["versions"]:
                        NoteVersionModel.create(
                            note=new_note,
                            version_number=v_data.get("version_number", 1),
                            content=v_data.get("content", "{}"),
                            source=v_data.get("source", "import"),
                            is_active=v_data.get("is_active", True),
                        )

                    for card_data in note_data["cards"]:
                        deck = target_decks.get(card_data["deck_name"])
                        if deck:
                            CardModel.create(
                                note=new_note,
                                deck=deck,
                                template_index=card_data.get("template_index", 0),
                                flags=card_data.get("flags", 0),
                                is_suspended=card_data.get("is_suspended", False),
                                ivl=card_data.get("ivl", 0),
                                reps=card_data.get("reps", 0),
                                lapses=card_data.get("lapses", 0),
                                stability=card_data.get("stability", 0.0),
                                difficulty=card_data.get("difficulty", 0.0),
                                retrievability=card_data.get("retrievability", 0.0),
                            )

                    try:
                        from ankiforge.services.search.fts_service import FTSService

                        FTSService.sync_note(new_note.id)
                    except Exception as err:
                        logger.debug("Remarque sync FTS5 dans transfer_content: %s", err)

                    notes_imported += 1

            # 4. Transfert physique des médias et déduplication MD5
            for m_info in media_files.values():
                src_path = m_info["path"]
                file_hash = m_info["checksum"]
                filename = m_info["filename"]
                dst_path = target_media_dir / filename

                existing_media = MediaModel.get_or_none(MediaModel.checksum == file_hash)
                if existing_media is None:
                    if not dst_path.exists() and src_path.exists():
                        shutil.copy2(str(src_path), str(dst_path))
                    mime_type = m_info.get("mime_type") or mimetypes.guess_type(str(dst_path))[0] or "application/octet-stream"
                    MediaModel.create(
                        filename=filename,
                        original_name=m_info.get("original_name") or filename,
                        checksum=file_hash,
                        mime_type=mime_type,
                    )
                    media_transferred += 1
                else:
                    if not dst_path.exists() and src_path.exists():
                        shutil.copy2(str(src_path), str(dst_path))

        return TransferReport(
            notes_imported=notes_imported,
            notes_updated=notes_updated,
            notes_skipped=notes_skipped,
            media_transferred=media_transferred,
            decks_created=decks_created,
            note_types_created=note_types_created,
            errors=errors,
        )

    @staticmethod
    def _extract_notes_data(
        source_profile: str,
        deck_names: list[str] | None = None,
        tag_names: list[str] | None = None,
        profiles_dir: Path | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
        source_media_dir = ProfileContentTransfer._get_profile_media_dir(source_profile, profiles_dir)
        with ProfileContentTransfer._source_database(source_profile, profiles_dir) as source_db, source_db.bind_ctx(ProfileContentTransfer._card_models):
            target_note_ids: set[int] = set()
            selected_deck_names = set(deck_names) if deck_names is not None else None
            selected_tag_names = set(tag_names) if tag_names is not None else None

            if selected_deck_names is None and selected_tag_names is None:
                target_note_ids = {n.id for n in NoteModel.select(NoteModel.id)}
            else:
                deck_note_ids: set[int] = set()
                if selected_deck_names is not None and len(selected_deck_names) > 0:
                    for deck in DeckModel.select():
                        for sel in selected_deck_names:
                            if deck.name == sel or str(deck.name).startswith(sel + "::"):
                                for card in CardModel.select(CardModel.note).where(CardModel.deck == deck):
                                    deck_note_ids.add(card.note_id)
                                break

                tag_note_ids: set[int] = set()
                if selected_tag_names is not None and len(selected_tag_names) > 0:
                    for note in NoteModel.select(NoteModel.id, NoteModel.tags).where(NoteModel.tags.is_null(False)):
                        note_tags = set(ProfileContentTransfer._parse_tags(note.tags))
                        if note_tags & selected_tag_names:
                            tag_note_ids.add(note.id)

                if selected_deck_names is not None and selected_tag_names is not None:
                    target_note_ids = deck_note_ids | tag_note_ids
                elif selected_deck_names is not None:
                    target_note_ids = deck_note_ids
                else:
                    target_note_ids = tag_note_ids

            if not target_note_ids:
                return [], {}

            notes_payload: list[dict[str, Any]] = []
            media_files_to_transfer: dict[str, dict[str, Any]] = {}

            for note in NoteModel.select().where(NoteModel.id.in_(list(target_note_ids))):
                nt = note.note_type
                nt_payload = {
                    "name": str(nt.name),
                    "description": nt.description,
                    "fields_schema": str(nt.fields_schema),
                    "templates": str(nt.templates),
                    "css_style": str(nt.css_style or ""),
                }

                versions = list(NoteVersionModel.select().where(NoteVersionModel.note == note).order_by(NoteVersionModel.version_number.asc()))
                versions_payload = []
                for v in versions:
                    versions_payload.append(
                        {
                            "version_number": int(v.version_number),
                            "content": str(v.content),
                            "source": str(v.source),
                            "is_active": bool(v.is_active),
                            "created_at": v.created_at,
                        }
                    )

                    media_names = ProfileContentTransfer._extract_media_references(str(v.content))
                    for m_name in media_names:
                        if m_name not in media_files_to_transfer:
                            file_path = source_media_dir / m_name
                            if file_path.is_file():
                                chk = ProfileContentTransfer._calculate_md5(str(file_path))
                                media_files_to_transfer[m_name] = {
                                    "path": file_path,
                                    "filename": m_name,
                                    "original_name": m_name,
                                    "checksum": chk,
                                    "mime_type": mimetypes.guess_type(str(file_path))[0] or "application/octet-stream",
                                    "size": file_path.stat().st_size,
                                }

                    for nvm in NoteVersionMediaModel.select().where(NoteVersionMediaModel.note_version == v):
                        m = nvm.media
                        if m and m.filename and m.filename not in media_files_to_transfer:
                            file_path = source_media_dir / m.filename
                            if file_path.is_file():
                                chk = str(m.checksum) if m.checksum else ProfileContentTransfer._calculate_md5(str(file_path))
                                media_files_to_transfer[m.filename] = {
                                    "path": file_path,
                                    "filename": m.filename,
                                    "original_name": str(m.original_name) if m.original_name else m.filename,
                                    "checksum": chk,
                                    "mime_type": str(m.mime_type) if m.mime_type else "application/octet-stream",
                                    "size": file_path.stat().st_size,
                                }

                cards = list(CardModel.select().where(CardModel.note == note))
                cards_payload = []
                for c in cards:
                    cards_payload.append(
                        {
                            "deck_name": str(c.deck.name),
                            "template_index": int(c.template_index),
                            "flags": int(c.flags),
                            "is_suspended": bool(c.is_suspended),
                            "ivl": int(c.ivl),
                            "reps": int(c.reps),
                            "lapses": int(c.lapses),
                            "stability": float(c.stability),
                            "difficulty": float(c.difficulty),
                            "retrievability": float(c.retrievability),
                        }
                    )

                notes_payload.append(
                    {
                        "guid": str(note.guid),
                        "tags": note.tags,
                        "status": str(note.status or "new"),
                        "anki_id": note.anki_id,
                        "anki_content_hash": note.anki_content_hash,
                        "note_type": nt_payload,
                        "versions": versions_payload,
                        "cards": cards_payload,
                    }
                )

            return notes_payload, media_files_to_transfer

    @staticmethod
    def _parse_tags(raw_tags: Any) -> list[str]:
        if not raw_tags:
            return []
        if isinstance(raw_tags, list):
            return [str(t).strip() for t in raw_tags if str(t).strip()]
        if isinstance(raw_tags, str):
            raw_str = raw_tags.strip()
            if raw_str.startswith("["):
                try:
                    parsed = json.loads(raw_str)
                    if isinstance(parsed, list):
                        return [str(t).strip() for t in parsed if str(t).strip()]
                except Exception:
                    pass
            return [t.strip() for t in raw_str.split() if t.strip()]
        return []

    @staticmethod
    def _normalize_fields_schema(raw_schema: Any) -> list[str]:
        if not raw_schema:
            return []
        if isinstance(raw_schema, list):
            return [str(f).strip() for f in raw_schema]
        if isinstance(raw_schema, str):
            try:
                parsed = json.loads(raw_schema)
                if isinstance(parsed, list):
                    return [str(f).strip() for f in parsed]
            except Exception:
                pass
        return []

    @staticmethod
    def _extract_media_references(content: str) -> list[str]:
        if not content:
            return []
        texts: list[str] = []
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                texts.extend(str(v) for v in parsed.values())
            elif isinstance(parsed, list):
                texts.extend(str(v) for v in parsed)
            else:
                texts.append(str(parsed))
        except Exception:
            texts.append(content)

        filenames: list[str] = []
        for text in texts:
            img_matches = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', text, re.IGNORECASE)
            snd_matches = re.findall(r"\[sound:([^\]]+)\]", text, re.IGNORECASE)
            for f in img_matches + snd_matches:
                cleaned = f.strip()
                if cleaned and cleaned not in filenames:
                    filenames.append(cleaned)
        return filenames

    @staticmethod
    def _calculate_md5(file_path: str) -> str:
        hash_md5 = hashlib.md5(usedforsecurity=False)
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    @staticmethod
    def _get_profile_media_dir(profile_name: str, profiles_dir: Path | None) -> Path:
        if profiles_dir is not None:
            return profiles_dir / profile_name / "media"
        manager = ProfileManager()
        return manager.get_media_dir(profile_name)

    @staticmethod
    def _get_target_media_dir(target_profile: str | None, profiles_dir: Path | None) -> Path:
        if target_profile is not None:
            return ProfileContentTransfer._get_profile_media_dir(target_profile, profiles_dir)
        return get_media_dir()

    @staticmethod
    def import_persona(
        profile_name: str,
        persona_name: str,
        profiles_dir: Path | None = None,
    ) -> PersonaModel:
        with ProfileContentTransfer._source_database(profile_name, profiles_dir) as source_db, source_db.bind_ctx(ProfileContentTransfer._source_models):
            source = PersonaModel.get_or_none(PersonaModel.name == persona_name)
            if source is None:
                raise ValueError(f"Agent introuvable dans le profil '{profile_name}' : {persona_name}")
            payload = ProfileContentTransfer._persona_payload(source)

        return ProfileContentTransfer._create_persona(payload, force_copy=True)

    @staticmethod
    def import_pipeline(
        profile_name: str,
        pipeline_name: str,
        profiles_dir: Path | None = None,
    ) -> PipelineModel:
        with ProfileContentTransfer._source_database(profile_name, profiles_dir) as source_db, source_db.bind_ctx(ProfileContentTransfer._source_models):
            source = PipelineModel.get_or_none(PipelineModel.name == pipeline_name)
            if source is None:
                raise ValueError(f"Pipeline introuvable dans le profil '{profile_name}' : {pipeline_name}")
            payload = ProfileContentTransfer._pipeline_payload(source)

        with PipelineModel._meta.database.atomic():
            personas: dict[str, PersonaModel] = {}
            for persona_payload in payload["personas"]:
                persona_name = str(persona_payload["name"])
                existing = PersonaModel.get_or_none(PersonaModel.name == persona_name)
                personas[persona_name] = existing or ProfileContentTransfer._create_persona(persona_payload, force_copy=False)

            name = ProfileContentTransfer._available_name(str(payload["name"]), PipelineModel)
            pipeline = PipelineModel.create(name=name, description=payload["description"])
            created_steps: dict[int, PipelineStepModel] = {}
            for index, step in enumerate(payload["steps"], start=1):
                created_steps[index] = PipelineStepModel.create(
                    pipeline=pipeline,
                    persona=personas.get(step["persona_name"]) if step["persona_name"] else None,
                    step_order=index,
                    step_type=step["step_type"],
                    failure_behavior=step["failure_behavior"],
                    config_data=json.dumps(step["config"]),
                )
            for index, step in enumerate(payload["steps"], start=1):
                updates: dict[str, PipelineStepModel] = {}
                success_order = step["on_success_order"]
                failure_order = step["on_failure_order"]
                if isinstance(success_order, int) and success_order in created_steps:
                    updates["on_success_step"] = created_steps[success_order]
                if isinstance(failure_order, int) and failure_order in created_steps:
                    updates["on_failure_step"] = created_steps[failure_order]
                if updates:
                    PipelineStepModel.update(updates).where(PipelineStepModel.id == created_steps[index].id).execute()
        return pipeline

    @staticmethod
    def _source_database(profile_name: str, profiles_dir: Path | None) -> SqliteDatabase:
        manager = ProfileManager()
        if profiles_dir is not None:
            manager.profiles_dir = profiles_dir
        db_path = manager.get_db_path(profile_name)
        if not db_path.is_file():
            raise FileNotFoundError(f"Base du profil introuvable : {profile_name}")
        return SqliteDatabase(str(db_path), timeout=30, pragmas={"foreign_keys": 1})

    @staticmethod
    def _persona_payload(persona: PersonaModel) -> dict[str, Any]:
        folder_chain: list[dict[str, Any]] = []
        folder = persona.folder
        while folder is not None:
            folder_chain.append({"name": str(folder.name), "parent_index": len(folder_chain) - 1})
            folder = folder.parent
        folder_chain.reverse()

        llm = persona.llm_config
        versions = [
            {
                "version_number": int(version.version_number),
                "system_prompt": str(version.system_prompt),
                "description": version.description,
                "output_format": str(version.output_format),
                "persona_type": str(version.persona_type),
                "allowed_tools": str(version.allowed_tools),
                "commit_message": str(version.commit_message),
                "is_active": bool(version.is_active),
            }
            for version in PersonaVersionModel.select().where(PersonaVersionModel.persona == persona).order_by(PersonaVersionModel.version_number.asc())
        ]
        return {
            "name": str(persona.name),
            "description": persona.description,
            "system_prompt": str(persona.system_prompt),
            "output_format": str(persona.output_format),
            "persona_type": str(persona.persona_type),
            "allowed_tools": str(persona.allowed_tools),
            "folder_chain": folder_chain,
            "llm": (
                {
                    "display_name": str(llm.display_name),
                    "provider": str(llm.provider),
                    "model_id": str(llm.model_id),
                    "context_limit": int(llm.context_limit),
                    "max_tokens": int(getattr(llm, "max_tokens", 16384)),
                    "sort_order": int(getattr(llm, "sort_order", 100)),
                    "temperature": float(llm.temperature),
                    "prompt_pricing": float(llm.prompt_pricing),
                    "completion_pricing": float(llm.completion_pricing),
                    "is_free": bool(llm.is_free),
                }
                if llm is not None
                else None
            ),
            "versions": versions,
        }

    @staticmethod
    def _pipeline_payload(pipeline: PipelineModel) -> dict[str, Any]:
        steps = list(PipelineStepModel.select().where(PipelineStepModel.pipeline == pipeline).order_by(PipelineStepModel.step_order.asc()))
        persona_payloads: dict[str, dict[str, Any]] = {}
        step_payloads: list[dict[str, Any]] = []
        for step in steps:
            persona_name = str(step.persona.name) if step.persona else None
            if step.persona is not None and persona_name is not None and persona_name not in persona_payloads:
                persona_payloads[persona_name] = ProfileContentTransfer._persona_payload(step.persona)
            try:
                config = json.loads(step.config_data or "{}")
            except (TypeError, json.JSONDecodeError):
                config = {}
            step_payloads.append(
                {
                    "persona_name": persona_name,
                    "step_type": str(step.step_type),
                    "failure_behavior": str(step.failure_behavior),
                    "config": config,
                    "on_success_order": int(step.on_success_step.step_order) if step.on_success_step else None,
                    "on_failure_order": int(step.on_failure_step.step_order) if step.on_failure_step else None,
                }
            )
        return {
            "name": str(pipeline.name),
            "description": pipeline.description,
            "steps": step_payloads,
            "personas": list(persona_payloads.values()),
        }

    @staticmethod
    def _create_persona(payload: dict[str, Any], force_copy: bool) -> PersonaModel:
        database = PersonaModel._meta.database
        with database.atomic():
            name = ProfileContentTransfer._available_name(str(payload["name"]), PersonaModel) if force_copy else str(payload["name"])
            folder = None
            for folder_data in payload["folder_chain"]:
                query = PersonaFolderModel.select().where((PersonaFolderModel.name == folder_data["name"]) & (PersonaFolderModel.parent == folder))
                folder = query.get_or_none() or PersonaFolderModel.create(name=folder_data["name"], parent=folder)

            llm = None
            llm_data = payload["llm"]
            if llm_data:
                llm = LLMConfigModel.get_or_none(LLMConfigModel.display_name == llm_data["display_name"])
                if llm is None:
                    llm = LLMConfigModel.create(api_key=None, **llm_data)

            persona = PersonaModel.create(
                name=name,
                description=payload["description"],
                system_prompt=payload["system_prompt"],
                output_format=payload["output_format"],
                persona_type=payload["persona_type"],
                folder=folder,
                allowed_tools=payload["allowed_tools"],
                llm_config=llm,
            )
            versions = payload["versions"] or [
                {
                    "version_number": 1,
                    "system_prompt": payload["system_prompt"],
                    "description": payload["description"],
                    "output_format": payload["output_format"],
                    "persona_type": payload["persona_type"],
                    "allowed_tools": payload["allowed_tools"],
                    "commit_message": "Import depuis un autre profil",
                    "is_active": True,
                }
            ]
            for version in versions:
                PersonaVersionModel.create(persona=persona, **version, llm_config=llm)
        return persona

    @staticmethod
    def _available_name(base_name: str, model: Any) -> str:
        name = base_name
        counter = 1
        while model.get_or_none(model.name == name) is not None:
            name = f"{base_name} (Importé {counter})"
            counter += 1
        return name
