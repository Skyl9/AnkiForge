import peewee as pw
from peewee_migrate import Migrator


def migrate(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Migration 028 : Ajout de max_tokens et sort_order à llm_configs + injection de gemini-3.5-flash-lite."""
    if not fake and database.table_exists("llm_configs"):
        cols = [col.name for col in database.get_columns("llm_configs")]
        if "max_tokens" not in cols:
            migrator.add_fields("llm_configs", max_tokens=pw.IntegerField(default=16384))
        if "sort_order" not in cols:
            migrator.add_fields("llm_configs", sort_order=pw.IntegerField(default=100))

        # Mettre à jour les modèles existants et s'assurer de la présence de gemini-3.5-flash-lite en tête
        try:
            database.execute_sql("UPDATE llm_configs SET max_tokens = 64000 WHERE model_id LIKE '%claude-3-7%'")
            database.execute_sql("UPDATE llm_configs SET max_tokens = 8192 WHERE model_id LIKE '%claude-3-5%'")
            database.execute_sql("UPDATE llm_configs SET max_tokens = 16384 WHERE model_id LIKE '%gpt-4o%'")
            database.execute_sql("UPDATE llm_configs SET max_tokens = 65536 WHERE model_id LIKE '%gemini-2.5%' OR model_id LIKE '%gemini-3.5%'")

            cursor = database.execute_sql("SELECT COUNT(*) FROM llm_configs WHERE model_id = 'gemini-3.5-flash-lite'")
            row = cursor.fetchone()
            count = row[0] if row else 0
            if count == 0:
                database.execute_sql(
                    "INSERT INTO llm_configs (display_name, provider, model_id, context_limit, max_tokens, sort_order, temperature, prompt_pricing, completion_pricing, is_free) "
                    "VALUES ('Google Gemini 3.5 Flash Lite', 'gemini', 'gemini-3.5-flash-lite', 1048576, 65536, 0, 0.7, 0.0, 0.0, 1)"
                )
            else:
                database.execute_sql("UPDATE llm_configs SET sort_order = 0, max_tokens = 65536 WHERE model_id = 'gemini-3.5-flash-lite'")
        except Exception:
            pass


def rollback(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Rollback 028 : Suppression des colonnes max_tokens et sort_order."""
    if not fake and database.table_exists("llm_configs"):
        cols = [col.name for col in database.get_columns("llm_configs")]
        fields_to_remove = []
        if "max_tokens" in cols:
            fields_to_remove.append("max_tokens")
        if "sort_order" in cols:
            fields_to_remove.append("sort_order")
        if fields_to_remove:
            migrator.remove_fields("llm_configs", *fields_to_remove)
