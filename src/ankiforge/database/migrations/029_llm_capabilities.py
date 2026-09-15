import json

import peewee as pw
from peewee_migrate import Migrator

from ankiforge.services.ai.model_catalog import ModelCatalog


def migrate(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Migration 029 : Ajout des capacités LLM (vision, thinking, json, vitesse, tier, tâches)."""
    if not fake and database.table_exists("llm_configs"):
        cols = [col.name for col in database.get_columns("llm_configs")]

        if "supports_vision" not in cols:
            migrator.add_fields("llm_configs", supports_vision=pw.BooleanField(default=False))
        if "supports_thinking" not in cols:
            migrator.add_fields("llm_configs", supports_thinking=pw.BooleanField(default=False))
        if "supports_json" not in cols:
            migrator.add_fields("llm_configs", supports_json=pw.BooleanField(default=True))
        if "speed_rating" not in cols:
            migrator.add_fields("llm_configs", speed_rating=pw.CharField(default="fast"))
        if "quality_tier" not in cols:
            migrator.add_fields("llm_configs", quality_tier=pw.CharField(default="balanced"))
        if "recommended_tasks" not in cols:
            migrator.add_fields("llm_configs", recommended_tasks=pw.CharField(default="[]"))
        if "description" not in cols:
            migrator.add_fields("llm_configs", description=pw.TextField(default=""))

        # Synchronisation et backfill des modèles existants avec les métadonnées de ModelCatalog
        try:
            cursor = database.execute_sql("SELECT id, provider, model_id FROM llm_configs")
            rows = cursor.fetchall()
            for r_id, prov, m_id in rows:
                spec = ModelCatalog.get_model_spec(prov or "openai", m_id or "")
                tasks_json = json.dumps(spec.recommended_tasks)
                desc = spec.ankiforge_use_case or spec.description
                database.execute_sql(
                    "UPDATE llm_configs SET supports_vision = ?, supports_thinking = ?, supports_json = ?, speed_rating = ?, quality_tier = ?, recommended_tasks = ?, description = ? WHERE id = ?",
                    (
                        int(spec.supports_vision),
                        int(spec.supports_thinking),
                        int(spec.supports_json),
                        spec.speed_rating,
                        spec.quality_tier,
                        tasks_json,
                        desc,
                        r_id,
                    ),
                )
        except Exception:
            pass


def rollback(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Rollback 029 : Suppression des colonnes de capacités."""
    if not fake and database.table_exists("llm_configs"):
        cols = [col.name for col in database.get_columns("llm_configs")]
        fields_to_remove = []
        for f in (
            "supports_vision",
            "supports_thinking",
            "supports_json",
            "speed_rating",
            "quality_tier",
            "recommended_tasks",
            "description",
        ):
            if f in cols:
                fields_to_remove.append(f)
        if fields_to_remove:
            migrator.remove_fields("llm_configs", *fields_to_remove)
