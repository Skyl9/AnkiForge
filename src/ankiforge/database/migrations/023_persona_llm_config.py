from peewee_migrate import Migrator


def migrate(migrator: Migrator, database, *, fake: bool = False) -> None:
    """Migration 023 : Ajout du champ llm_config_id dans la table personas."""
    if not fake and database.table_exists("personas"):
        cols = [col.name for col in database.get_columns("personas")]
        if "llm_config_id" not in cols:
            database.execute_sql("ALTER TABLE personas ADD COLUMN llm_config_id INTEGER REFERENCES llm_configs (id);")


def rollback(migrator: Migrator, database, *, fake: bool = False) -> None:
    """Rollback 023 : Suppression du champ llm_config_id de personas."""
    if not fake and database.table_exists("personas"):
        cols = [col.name for col in database.get_columns("personas")]
        if "llm_config_id" in cols:
            migrator.remove_fields("personas", "llm_config_id")
