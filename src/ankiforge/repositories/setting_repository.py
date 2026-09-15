"""
Repository for Application Settings, Token Usage Telemetry, and AI Cache.
"""

from __future__ import annotations

import logging
from typing import Any

from peewee import fn

from ankiforge.database.models import (
    AICacheModel,
    JobModel,
    SettingModel,
    TokenUsageModel,
)
from ankiforge.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class SettingRepository(BaseRepository):
    """Data access repository for application configuration, AI cache, and token telemetry."""

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Retrieve a setting value by its key."""
        return SettingModel.get_value(key, default=default)

    def set_setting(self, key: str, value: Any, category: str = "general") -> SettingModel:
        """Persist or update a setting value."""
        with self.atomic():
            return SettingModel.set_value(key, value, category=category)

    def get_settings_by_category(self, category: str) -> dict[str, Any]:
        """Retrieve all settings in a category as key-value pairs."""
        return SettingModel.get_category(category)

    def get_all_settings(self) -> dict[str, Any]:
        """Retrieve all application settings."""
        settings: dict[str, Any] = {}
        for record in SettingModel.select():
            settings[record.key] = SettingModel.get_value(record.key)
        return settings

    def delete_setting(self, key: str) -> bool:
        """Delete a setting entry."""
        with self.atomic():
            deleted = SettingModel.delete().where(SettingModel.key == key).execute()
            return bool(deleted > 0)

    def get_token_usage_records(self, limit: int = 100) -> list[TokenUsageModel]:
        """Retrieve recent token usage logs."""
        return list(TokenUsageModel.select().order_by(TokenUsageModel.created_at.desc()).limit(limit))

    def record_token_usage(
        self,
        provider: str,
        model_id: str,
        prompt_tokens: int,
        completion_tokens: int,
        estimated_cost_usd: float = 0.0,
        task_type: str = "1. Reformulation & Génération Wozniak",
    ) -> TokenUsageModel:
        """Record token consumption and estimated cost."""
        total = prompt_tokens + completion_tokens
        with self.atomic():
            return TokenUsageModel.create(
                provider=provider,
                model_id=model_id,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total,
                estimated_cost_usd=estimated_cost_usd,
                task_type=task_type,
            )

    def get_total_token_usage_stats(self) -> dict[str, Any]:
        """Calculate aggregate telemetry metrics for tokens and costs."""
        query = (
            TokenUsageModel.select(
                fn.SUM(TokenUsageModel.total_tokens).alias("total_tokens"),
                fn.SUM(TokenUsageModel.prompt_tokens).alias("total_prompt_tokens"),
                fn.SUM(TokenUsageModel.completion_tokens).alias("total_completion_tokens"),
                fn.SUM(TokenUsageModel.estimated_cost_usd).alias("total_cost"),
                fn.COUNT(TokenUsageModel.id).alias("total_calls"),
            )
            .dicts()
            .first()
        )

        if not query or query.get("total_tokens") is None:
            return {
                "total_tokens": 0,
                "total_prompt_tokens": 0,
                "total_completion_tokens": 0,
                "total_cost_usd": 0.0,
                "total_calls": 0,
            }

        return {
            "total_tokens": query.get("total_tokens") or 0,
            "total_prompt_tokens": query.get("total_prompt_tokens") or 0,
            "total_completion_tokens": query.get("total_completion_tokens") or 0,
            "total_cost_usd": float(query.get("total_cost") or 0.0),
            "total_calls": query.get("total_calls") or 0,
        }

    def get_cached_ai_response(
        self,
        prompt_hash: str,
        system_prompt_hash: str = "",
        model_id: str = "",
        temperature: float = 0.7,
    ) -> str | None:
        """Look up response from AI query cache."""
        try:
            record = AICacheModel.get_or_none(
                AICacheModel.prompt_hash == prompt_hash,
                AICacheModel.system_prompt_hash == system_prompt_hash,
                AICacheModel.model_id == model_id,
                AICacheModel.temperature == temperature,
            )
            return record.response_content if record else None
        except Exception as e:
            logger.debug("AI Cache miss or error: %s", e)
            return None

    def cache_ai_response(
        self,
        prompt_hash: str,
        system_prompt_hash: str,
        model_id: str,
        temperature: float,
        response_content: str,
    ) -> AICacheModel:
        """Store an AI response in cache."""
        with self.atomic():
            record, _ = AICacheModel.get_or_create(
                prompt_hash=prompt_hash,
                system_prompt_hash=system_prompt_hash,
                model_id=model_id,
                temperature=temperature,
                defaults={"response_content": response_content},
            )
            if record.response_content != response_content:
                record.response_content = response_content
                record.save()
            return record

    def clear_ai_cache(self) -> int:
        """Clear all entries from the AI cache."""
        with self.atomic():
            return int(AICacheModel.delete().execute())

    def get_pending_jobs(self) -> list[JobModel]:
        """Retrieve pending background jobs."""
        return list(JobModel.select().where(JobModel.status == "pending"))
