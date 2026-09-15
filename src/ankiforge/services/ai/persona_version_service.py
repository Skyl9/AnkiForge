"""
Service de versioning Git-like et d'historique de configuration pour les Personas / Agents IA.
"""

from __future__ import annotations

import difflib
import logging
from typing import Any

from ankiforge.database.models import PersonaModel, PersonaVersionModel, db

logger = logging.getLogger(__name__)


class PersonaVersionService:
    """Gestionnaire de cycle de vie, snapshots et restauration des versions de prompts et personas."""

    @classmethod
    def create_snapshot(
        cls,
        persona: PersonaModel,
        commit_message: str = "Mise à jour du prompt",
        force: bool = False,
    ) -> PersonaVersionModel | None:
        """
        Crée un nouveau snapshot pour le persona si des modifications significatives ont eu lieu.
        """
        if not persona or not persona.id:
            return None

        # Récupère la dernière version enregistrée
        latest_version = PersonaVersionModel.select().where(PersonaVersionModel.persona == persona).order_by(PersonaVersionModel.version_number.desc()).first()

        # Vérifier s'il y a un réel changement de contenu
        if latest_version and not force:
            prompt_identical = str(latest_version.system_prompt or "").strip() == str(persona.system_prompt or "").strip()
            desc_identical = str(latest_version.description or "").strip() == str(persona.description or "").strip()
            format_identical = str(latest_version.output_format or "") == str(persona.output_format or "")
            type_identical = str(latest_version.persona_type or "") == str(persona.persona_type or "")
            tools_identical = str(latest_version.allowed_tools or "[]") == str(persona.allowed_tools or "[]")
            llm_identical = latest_version.llm_config == persona.llm_config

            if prompt_identical and desc_identical and format_identical and type_identical and tools_identical and llm_identical:
                return latest_version

        next_version_num = (int(latest_version.version_number) + 1) if latest_version else 1

        with db.atomic():
            # Désactiver le statut actif des versions précédentes
            PersonaVersionModel.update(is_active=False).where(PersonaVersionModel.persona == persona).execute()

            # Créer le nouveau snapshot
            new_version = PersonaVersionModel.create(
                persona=persona,
                version_number=next_version_num,
                system_prompt=str(persona.system_prompt or ""),
                description=str(persona.description or ""),
                output_format=str(persona.output_format or "json"),
                persona_type=str(persona.persona_type or "pipeline"),
                allowed_tools=str(persona.allowed_tools or "[]"),
                llm_config=persona.llm_config,
                commit_message=commit_message or f"Version {next_version_num}",
                is_active=True,
            )

        logger.info(
            "Snapshot v%d créé pour le persona '%s' (ID: %s).",
            next_version_num,
            persona.name,
            persona.id,
        )
        return new_version

    @classmethod
    def get_versions(cls, persona_id: int) -> list[PersonaVersionModel]:
        """Retourne la liste chronologique décroissante de toutes les versions d'un persona."""
        return list(PersonaVersionModel.select().where(PersonaVersionModel.persona == persona_id).order_by(PersonaVersionModel.version_number.desc()))

    @classmethod
    def get_version(cls, version_id: int) -> PersonaVersionModel | None:
        """Récupère une version spécifique par son identifiant unique."""
        return PersonaVersionModel.get_or_none(PersonaVersionModel.id == version_id)

    @classmethod
    def get_active_version(cls, persona_id: int) -> PersonaVersionModel | None:
        """Récupère la version actuellement active pour ce persona."""
        return (
            PersonaVersionModel.select()
            .where(
                PersonaVersionModel.persona == persona_id,
                PersonaVersionModel.is_active,
            )
            .first()
        )

    @classmethod
    def restore_version(cls, version_id: int) -> PersonaModel:
        """
        Restaure la configuration d'un persona à l'état de la version spécifiée.
        """
        target_version = cls.get_version(version_id)
        if not target_version:
            raise ValueError(f"Version de persona introuvable (ID: {version_id})")

        persona: PersonaModel = target_version.persona  # type: ignore[assignment]
        if not persona:
            raise ValueError("Persona associé à cette version introuvable.")

        with db.atomic():
            # Mise à jour du Persona principal
            persona.system_prompt = target_version.system_prompt
            persona.description = target_version.description
            persona.output_format = target_version.output_format
            persona.persona_type = target_version.persona_type
            persona.allowed_tools = target_version.allowed_tools
            persona.llm_config = target_version.llm_config
            persona.save()

            # Bascule de l'indicateur is_active
            PersonaVersionModel.update(is_active=False).where(PersonaVersionModel.persona == persona).execute()

            target_version.is_active = True  # type: ignore[assignment]
            target_version.save()

        logger.info(
            "Persona '%s' restauré avec succès à la version v%d.",
            persona.name,
            target_version.version_number,
        )
        return persona

    @classmethod
    def diff_prompt(cls, old_text: str, new_text: str) -> list[dict[str, Any]]:
        """
        Calcule un différentiel ligne par ligne enrichi entre deux textes de prompt.
        Retourne une liste d'objets avec type ('equal', 'insert', 'delete') et contenu textuel.
        """
        old_lines = (old_text or "").splitlines(keepends=True)
        new_lines = (new_text or "").splitlines(keepends=True)

        matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
        diff_chunks: list[dict[str, Any]] = []

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                for line in old_lines[i1:i2]:
                    diff_chunks.append({"type": "equal", "text": line})
            elif tag == "delete":
                for line in old_lines[i1:i2]:
                    diff_chunks.append({"type": "delete", "text": line})
            elif tag == "insert":
                for line in new_lines[j1:j2]:
                    diff_chunks.append({"type": "insert", "text": line})
            elif tag == "replace":
                for line in old_lines[i1:i2]:
                    diff_chunks.append({"type": "delete", "text": line})
                for line in new_lines[j1:j2]:
                    diff_chunks.append({"type": "insert", "text": line})

        return diff_chunks
