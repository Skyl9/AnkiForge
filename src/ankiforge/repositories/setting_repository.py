"""Dépôt des paramètres applicatifs, de la télémétrie d'usage des tokens et du cache IA."""

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
    """Dépôt d'accès aux données de la configuration applicative, du cache IA et de la télémétrie des tokens."""

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Retourne la valeur d'un paramètre par sa clé."""
        return SettingModel.get_value(key, default=default)

    def set_setting(self, key: str, value: Any, category: str = "general") -> SettingModel:
        """Persiste ou met à jour la valeur d'un paramètre."""
        with self.atomic():
            return SettingModel.set_value(key, value, category=category)

    def get_settings_by_category(self, category: str) -> dict[str, Any]:
        """Retourne tous les paramètres d'une catégorie sous forme de paires clé-valeur."""
        return SettingModel.get_category(category)

    def get_all_settings(self) -> dict[str, Any]:
        """Retourne tous les paramètres applicatifs."""
        settings: dict[str, Any] = {}
        for record in SettingModel.select():
            settings[record.key] = SettingModel.get_value(record.key)
        return settings

    def delete_setting(self, key: str) -> bool:
        """Supprime une entrée de paramètre."""
        with self.atomic():
            deleted = SettingModel.delete().where(SettingModel.key == key).execute()
            return bool(deleted > 0)

    def get_token_usage_records(self, limit: int = 100) -> list[TokenUsageModel]:
        """Retourne les journaux récents d'usage des tokens."""
        return list(TokenUsageModel.select().order_by(TokenUsageModel.created_at.desc()).limit(limit))

    def record_token_usage(
        self,
        provider: str,
        model_id: str,
        prompt_tokens: int,
        completion_tokens: int,
        estimated_cost_usd: float = 0.0,
        task_type: str = "1. Reformulation & Génération Wozniak",
        pipeline_id: int | None = None,
        persona_id: int | None = None,
        ab_run_id: str | None = None,
    ) -> TokenUsageModel:
        """Enregistre la consommation de tokens et le coût estimé, liés à leur contexte d'exécution."""
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
                pipeline_id=pipeline_id,
                persona_id=persona_id,
                ab_run_id=ab_run_id,
            )

    def get_usage_for_ab_run(self, ab_run_id: str) -> dict[str, Any]:
        """Agrège la consommation de tokens et le coût mesurés pour une branche d'exécution A/B donnée."""
        query = (
            TokenUsageModel.select(
                fn.SUM(TokenUsageModel.total_tokens).alias("total_tokens"),
                fn.SUM(TokenUsageModel.estimated_cost_usd).alias("total_cost"),
                fn.COUNT(TokenUsageModel.id).alias("total_calls"),
            )
            .where(TokenUsageModel.ab_run_id == ab_run_id)
            .dicts()
            .first()
        )
        if not query or query.get("total_tokens") is None:
            return {"total_tokens": 0, "total_cost_usd": 0.0, "total_calls": 0}
        return {
            "total_tokens": query.get("total_tokens") or 0,
            "total_cost_usd": query.get("total_cost") or 0.0,
            "total_calls": query.get("total_calls") or 0,
        }

    def get_total_token_usage_stats(self) -> dict[str, Any]:
        """Calcule les métriques de télémétrie agrégées des tokens et des coûts."""
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
        """Recherche une réponse dans le cache de requêtes IA."""
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
        """Stocke une réponse IA dans le cache."""
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
        """Vide le cache IA de toutes ses entrées."""
        with self.atomic():
            return int(AICacheModel.delete().execute())

    def get_pending_jobs(self) -> list[JobModel]:
        """Retourne les tâches d'arrière-plan en attente."""
        return list(JobModel.select().where(JobModel.status == "pending"))
