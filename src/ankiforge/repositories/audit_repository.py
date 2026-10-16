"""Dépôt des règles de linter, des enregistrements d'audit et des doublons ignorés."""

from __future__ import annotations

import logging
from typing import Any

from ankiforge.database.models import (
    AuditRecordModel,
    CardModel,
    IgnoredDuplicateModel,
    LinterRuleModel,
    NoteModel,
    NoteVersionModel,
)
from ankiforge.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class AuditRepository(BaseRepository):
    """Dépôt d'accès aux données des règles de linter Wozniak, des résultats d'audit et du suivi des doublons."""

    def get_all_rules(self) -> list[LinterRuleModel]:
        """Retourne toutes les règles de linter triées par catégorie et par nom."""
        return list(LinterRuleModel.select().order_by(LinterRuleModel.category.asc(), LinterRuleModel.name.asc()))

    def get_active_rules(self) -> list[LinterRuleModel]:
        """Retourne uniquement les règles de linter actuellement actives."""
        return list(
            LinterRuleModel.select()
            .where(LinterRuleModel.is_active == True)  # noqa: E712
            .order_by(LinterRuleModel.category.asc(), LinterRuleModel.name.asc())
        )

    def get_rule_by_id(self, rule_id: int) -> LinterRuleModel | None:
        """Retourne une règle de linter par son ID."""
        try:
            return LinterRuleModel.get_or_none(LinterRuleModel.id == rule_id)
        except Exception as e:
            logger.error("Failed to get linter rule %s: %s", rule_id, e)
            return None

    def get_rule_by_name(self, name: str) -> LinterRuleModel | None:
        """Retourne une règle de linter par son nom unique."""
        try:
            return LinterRuleModel.get_or_none(LinterRuleModel.name == name)
        except Exception as e:
            logger.error("Failed to get linter rule by name '%s': %s", name, e)
            return None

    def create_rule(
        self,
        name: str,
        prompt_injection: str,
        category: str = "cat-atomicite",
        category_label: str = "Atomicité & Restructuration",
        description: str | None = None,
        is_active: bool = True,
        color: str = "#f87171",
        icon_name: str = "squares-four",
        example_bad: str | None = None,
        example_good: str | None = None,
    ) -> LinterRuleModel:
        """Crée une nouvelle règle de linter personnalisée."""
        with self.atomic():
            return LinterRuleModel.create(
                name=name,
                prompt_injection=prompt_injection,
                category=category,
                category_label=category_label,
                description=description,
                is_active=is_active,
                color=color,
                icon_name=icon_name,
                example_bad=example_bad,
                example_good=example_good,
            )

    def update_rule(self, rule_id: int, **kwargs: Any) -> LinterRuleModel | None:
        """Met à jour les champs d'une règle de linter existante."""
        rule = self.get_rule_by_id(rule_id)
        if not rule:
            return None

        with self.atomic():
            for key, val in kwargs.items():
                if hasattr(rule, key):
                    setattr(rule, key, val)
            rule.save()
            return rule

    def toggle_rule(self, rule_id: int, is_active: bool) -> bool:
        """Bascule le statut actif d'une règle de linter."""
        rule = self.get_rule_by_id(rule_id)
        if not rule:
            return False

        with self.atomic():
            rule.is_active = is_active
            rule.save()
            return True

    def delete_rule(self, rule_id: int) -> bool:
        """Supprime une règle de linter."""
        rule = self.get_rule_by_id(rule_id)
        if not rule:
            return False

        with self.atomic():
            rule.delete_instance()
            return True

    def get_audit_records(
        self,
        deck_id: int | None = None,
        note_id: int | None = None,
        is_compliant: bool | None = None,
    ) -> list[AuditRecordModel]:
        """Interroge les enregistrements d'audit filtrés éventuellement par paquet, note ou statut de conformité."""
        query = AuditRecordModel.select(AuditRecordModel, NoteModel, NoteVersionModel).join(NoteModel).join(NoteVersionModel)

        if deck_id is not None:
            query = query.join(CardModel, on=(CardModel.note == NoteModel.id)).where(CardModel.deck == deck_id)

        if note_id is not None:
            query = query.where(AuditRecordModel.note == note_id)

        if is_compliant is not None:
            query = query.where(AuditRecordModel.is_compliant == is_compliant)

        return list(query.order_by(AuditRecordModel.analyzed_at.desc()))

    def create_or_update_audit_record(
        self,
        note: NoteModel,
        note_version: NoteVersionModel,
        is_compliant: bool,
        rule_broken: str | None = None,
        reason: str | None = None,
        suggestion: str | None = None,
    ) -> AuditRecordModel:
        """Persiste ou met à jour un enregistrement d'audit pour une version de note."""
        with self.atomic():
            record, _ = AuditRecordModel.get_or_create(
                note=note,
                note_version=note_version,
                defaults={
                    "is_compliant": is_compliant,
                    "rule_broken": rule_broken,
                    "reason": reason,
                    "suggestion": suggestion,
                },
            )
            if record.is_compliant != is_compliant or record.rule_broken != rule_broken:
                record.is_compliant = is_compliant
                record.rule_broken = rule_broken
                record.reason = reason
                record.suggestion = suggestion
                record.save()
            return record

    def clear_audit_records(self, deck_id: int | None = None) -> int:
        """Supprime les enregistrements d'audit, éventuellement limités à un paquet."""
        with self.atomic():
            if deck_id is not None:
                note_ids = [c.note_id for c in CardModel.select(CardModel.note).where(CardModel.deck == deck_id)]
                deleted = AuditRecordModel.delete().where(AuditRecordModel.note.in_(note_ids)).execute()
            else:
                deleted = AuditRecordModel.delete().execute()
            return int(deleted)

    def get_ignored_duplicates(self) -> list[IgnoredDuplicateModel]:
        """Retourne tous les couples de doublons ignorés enregistrés."""
        return list(IgnoredDuplicateModel.select())

    def is_duplicate_ignored(self, note_a_id: int, note_b_id: int) -> bool:
        """Vérifie si un couple de notes a été marqué comme doublons ignorés."""
        min_id = min(note_a_id, note_b_id)
        max_id = max(note_a_id, note_b_id)
        return IgnoredDuplicateModel.select().where((IgnoredDuplicateModel.note_a == min_id) & (IgnoredDuplicateModel.note_b == max_id)).exists()

    def ignore_duplicate(self, note_a_id: int, note_b_id: int) -> IgnoredDuplicateModel:
        """Enregistre un couple de notes comme doublons ignorés."""
        min_id = min(note_a_id, note_b_id)
        max_id = max(note_a_id, note_b_id)
        with self.atomic():
            record, _ = IgnoredDuplicateModel.get_or_create(
                note_a=min_id,
                note_b=max_id,
            )
            return record
