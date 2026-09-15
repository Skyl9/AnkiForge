"""
Repository for Linter rules, audit records, and ignored duplicates.
"""

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
    """Data access repository for Wozniak linter rules, audit results, and duplicate tracking."""

    def get_all_rules(self) -> list[LinterRuleModel]:
        """Retrieve all linter rules sorted by category and name."""
        return list(LinterRuleModel.select().order_by(LinterRuleModel.category.asc(), LinterRuleModel.name.asc()))

    def get_active_rules(self) -> list[LinterRuleModel]:
        """Retrieve only currently active linter rules."""
        return list(
            LinterRuleModel.select()
            .where(LinterRuleModel.is_active == True)  # noqa: E712
            .order_by(LinterRuleModel.category.asc(), LinterRuleModel.name.asc())
        )

    def get_rule_by_id(self, rule_id: int) -> LinterRuleModel | None:
        """Retrieve a linter rule by its ID."""
        try:
            return LinterRuleModel.get_or_none(LinterRuleModel.id == rule_id)
        except Exception as e:
            logger.error("Failed to get linter rule %s: %s", rule_id, e)
            return None

    def get_rule_by_name(self, name: str) -> LinterRuleModel | None:
        """Retrieve a linter rule by its unique name."""
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
        """Create a new custom linter rule."""
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
        """Update fields of an existing linter rule."""
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
        """Toggle active status of a linter rule."""
        rule = self.get_rule_by_id(rule_id)
        if not rule:
            return False

        with self.atomic():
            rule.is_active = is_active
            rule.save()
            return True

    def delete_rule(self, rule_id: int) -> bool:
        """Delete a linter rule."""
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
        """Query audit records filtered optionally by deck, note, or compliance status."""
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
        """Persist or update an audit record for a note version."""
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
        """Delete audit records optionally scoped to a deck."""
        with self.atomic():
            if deck_id is not None:
                note_ids = [c.note_id for c in CardModel.select(CardModel.note).where(CardModel.deck == deck_id)]
                deleted = AuditRecordModel.delete().where(AuditRecordModel.note.in_(note_ids)).execute()
            else:
                deleted = AuditRecordModel.delete().execute()
            return int(deleted)

    def get_ignored_duplicates(self) -> list[IgnoredDuplicateModel]:
        """Retrieve all recorded ignored duplicate pairs."""
        return list(IgnoredDuplicateModel.select())

    def is_duplicate_ignored(self, note_a_id: int, note_b_id: int) -> bool:
        """Check if a pair of notes was marked as ignored duplicates."""
        min_id = min(note_a_id, note_b_id)
        max_id = max(note_a_id, note_b_id)
        return IgnoredDuplicateModel.select().where((IgnoredDuplicateModel.note_a == min_id) & (IgnoredDuplicateModel.note_b == max_id)).exists()

    def ignore_duplicate(self, note_a_id: int, note_b_id: int) -> IgnoredDuplicateModel:
        """Record a pair of notes as ignored duplicates."""
        min_id = min(note_a_id, note_b_id)
        max_id = max(note_a_id, note_b_id)
        with self.atomic():
            record, _ = IgnoredDuplicateModel.get_or_create(
                note_a=min_id,
                note_b=max_id,
            )
            return record
