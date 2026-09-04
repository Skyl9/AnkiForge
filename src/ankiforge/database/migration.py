import logging
import sqlite3
from pathlib import Path

import peewee
from peewee_migrate import Router

from ankiforge.database.models import db
from ankiforge.utils.paths import get_app_data_dir, get_resource_path

logger = logging.getLogger(__name__)


def get_migrations_dir() -> Path:
    """Localise de manière robuste le répertoire contenant les fichiers de migration (.py).

    Compatible Mode Dev, Standalone Nuitka, PyInstaller et Bundle macOS (.app).
    """
    candidates = [
        get_resource_path("src", "ankiforge", "database", "migrations"),
        get_resource_path("migrations"),
        Path(__file__).resolve().parent / "migrations",
    ]
    for c in candidates:
        if c.exists() and any(c.glob("*.py")):
            return c
    for c in candidates:
        if c.exists():
            return c

    # Fallback dans le dossier de données persistant utilisateur (~/.ankiforge/migrations)
    user_mig = get_app_data_dir() / "migrations"
    user_mig.mkdir(parents=True, exist_ok=True)
    return user_mig


def run_migrations() -> None:
    """Évalue la version de la base de données et exécute les migrations nécessaires

    en utilisant peewee-migrate.
    """
    # 1. Localisation sécurisée du répertoire de migrations
    migrations_dir = get_migrations_dir()
    logger.info("Utilisation du répertoire de migrations : %s", migrations_dir)

    router = Router(db, migrate_dir=str(migrations_dir))

    # 2. Gestion de la transition depuis l'ancien système manuel
    # Si la table 'agents' ou 'personas' existe, c'est que l'utilisateur a au moins la v1
    is_legacy = db.table_exists("agents") or db.table_exists("personas")
    done_migrations = router.done

    if is_legacy:
        # Falsifier la migration initiale si elle n'est pas encore tracée
        if "001_initial" not in done_migrations:
            router.model.create(name="001_initial")
            logger.info("Base legacy détectée : enregistrement rétroactif de la migration 001_initial.")

        # Si la colonne prompt_pricing existe, l'utilisateur a déjà la structure de la v2
        if "002_llm_pricing" not in done_migrations and db.table_exists("llm_configs"):
            columns = [col.name for col in db.get_columns("llm_configs")]
            if "prompt_pricing" in columns:
                router.model.create(name="002_llm_pricing")
                logger.info("Base legacy détectée : enregistrement rétroactif de la migration 002_llm_pricing.")

        # Si notemodel n'existe pas ou si la colonne last_synced_at existe déjà
        if "003_orientation_features" not in done_migrations and (not db.table_exists("notemodel") or "last_synced_at" in [col.name for col in db.get_columns("notemodel")]):
            router.model.create(name="003_orientation_features")
            logger.info("Base legacy détectée : enregistrement rétroactif de la migration 003_orientation_features.")

        # Si la table ai_cache existe déjà, l'utilisateur a déjà la structure de la v4
        if "004_ai_cache" not in done_migrations and db.table_exists("ai_cache"):
            router.model.create(name="004_ai_cache")
            logger.info("Base legacy détectée : enregistrement rétroactif de la migration 004_ai_cache.")

        # Si la table personas existe, l'utilisateur a déjà la structure de la v5
        if "005_persona_engine" not in done_migrations and db.table_exists("personas"):
            router.model.create(name="005_persona_engine")
            logger.info("Base legacy détectée : enregistrement rétroactif de la migration 005_persona_engine.")

        # Vérification et ajout dynamique de la colonne llm_config_id sur personas si absente
        if db.table_exists("personas"):
            columns = [col.name for col in db.get_columns("personas")]
            if "llm_config_id" not in columns:
                try:
                    db.execute_sql("ALTER TABLE personas ADD COLUMN llm_config_id INTEGER REFERENCES llm_configs (id);")
                    logger.info("Colonne 'llm_config_id' ajoutée dynamiquement à la table 'personas'.")
                except Exception as e:
                    logger.debug("Remarque sur l'ajout de llm_config_id sur personas : %s", e)

        # Si documentmodel n'existe pas ou si la colonne chroma_collection_name existe
        if "006_chroma_db" not in done_migrations and (not db.table_exists("documentmodel") or "chroma_collection_name" in [col.name for col in db.get_columns("documentmodel")]):
            router.model.create(name="006_chroma_db")
            logger.info("Base legacy détectée : enregistrement rétroactif de la migration 006_chroma_db.")

        # Si la table linter_rules existe déjà ou n'est pas gérée par cette base
        if "007_card_linter" not in done_migrations and (db.table_exists("linter_rules") or not db.table_exists("notemodel")):
            router.model.create(name="007_card_linter")
            logger.info("Base legacy détectée : enregistrement rétroactif de la migration 007_card_linter.")

        # Si la table document_chunks ou cognitive_facets existe, ou si documentmodel n'existe pas
        if "008_document_coverage" not in done_migrations and (db.table_exists("document_chunks") or db.table_exists("cognitive_facets") or not db.table_exists("documentmodel")):
            router.model.create(name="008_document_coverage")
            logger.info("Base legacy détectée : enregistrement rétroactif de la migration 008_document_coverage.")

        # Si cardmodel n'existe pas ou si la colonne stability existe
        if "009_srs_and_task_metrics" not in done_migrations and (not db.table_exists("cardmodel") or "stability" in [col.name for col in db.get_columns("cardmodel")]):
            router.model.create(name="009_srs_and_task_metrics")
            logger.info("Base legacy détectée : enregistrement rétroactif de la migration 009_srs_and_task_metrics.")

        # Si documentmodel n'existe pas ou si original_media existe
        if "010_document_original_media" not in done_migrations:
            doc_cols = [col.name for col in db.get_columns("documentmodel")] if db.table_exists("documentmodel") else []
            if not db.table_exists("documentmodel") or ("original_media" in doc_cols or "original_media_id" in doc_cols):
                router.model.create(name="010_document_original_media")
                logger.info("Base legacy détectée : enregistrement rétroactif de la migration 010_document_original_media.")

        # Si la table facet_profiles existe, l'utilisateur a la v11
        if "011_add_facet_profile" not in done_migrations and db.table_exists("facet_profiles"):
            router.model.create(name="011_add_facet_profile")
            logger.info("Base legacy détectée : enregistrement rétroactif de la migration 011_add_facet_profile.")

        # Si la colonne config_data existe dans pipeline_steps, v12 est là
        if "012_pipeline_step_config" not in done_migrations:
            has_ps = db.table_exists("pipeline_steps") or db.table_exists("pipelinestepmodel")
            if not has_ps or ("config_data" in [col.name for col in db.get_columns("pipeline_steps" if db.table_exists("pipeline_steps") else "pipelinestepmodel")]):
                router.model.create(name="012_pipeline_step_config")
                logger.info("Base legacy détectée : enregistrement rétroactif de la migration 012_pipeline_step_config.")

        # Si la table python_tools existe, v13 est présente
        if "013_python_tools" not in done_migrations and (db.table_exists("python_tools") or db.table_exists("pythontoolmodel")):
            router.model.create(name="013_python_tools")
            logger.info("Base legacy détectée : enregistrement rétroactif de la migration 013_python_tools.")

        # Si la colonne persona_type existe dans personas, v14 est là
        if "014_persona_type" not in done_migrations:
            has_p = db.table_exists("personas") or db.table_exists("personamodel")
            if not has_p or ("persona_type" in [col.name for col in db.get_columns("personas" if db.table_exists("personas") else "personamodel")]):
                router.model.create(name="014_persona_type")
                logger.info("Base legacy détectée : enregistrement rétroactif de la migration 014_persona_type.")

        # Si la table persona_folders existe, v15 est là
        if "015_persona_folders" not in done_migrations and db.table_exists("persona_folders"):
            router.model.create(name="015_persona_folders")
            logger.info("Base legacy détectée : enregistrement rétroactif de la migration 015_persona_folders.")

        # Si la colonne parent_id existe dans persona_folders, v16 est là
        if "016_persona_subfolders" not in done_migrations and db.table_exists("persona_folders") and "parent_id" in [col.name for col in db.get_columns("persona_folders")]:
            router.model.create(name="016_persona_subfolders")
            logger.info("Base legacy détectée : enregistrement rétroactif de la migration 016_persona_subfolders.")

        # Si la colonne category existe dans linter_rules, v17 est là
        if "017_linter_rule_categories" not in done_migrations:
            has_lr = db.table_exists("linter_rules") or db.table_exists("linterrulemodel")
            if not has_lr or ("category" in [col.name for col in db.get_columns("linter_rules" if db.table_exists("linter_rules") else "linterrulemodel")]):
                router.model.create(name="017_linter_rule_categories")
                logger.info("Base legacy détectée : enregistrement rétroactif de la migration 017_linter_rule_categories.")

        # Si la table settings ou app_settings existe, v18 est là
        if "018_app_settings" not in done_migrations and (db.table_exists("settings") or db.table_exists("app_settings") or db.table_exists("settingmodel")):
            router.model.create(name="018_app_settings")
            logger.info("Base legacy détectée : enregistrement rétroactif de la migration 018_app_settings.")

        # Si la table persona_versions existe, l'utilisateur a la v19
        if "019_persona_versions" not in done_migrations and (db.table_exists("persona_versions") or db.table_exists("personaversionmodel")):
            router.model.create(name="019_persona_versions")
            logger.info("Base legacy détectée : enregistrement rétroactif de la migration 019_persona_versions.")

        # Si notetypemodel a déjà la colonne description, l'utilisateur a la v20
        if "020_notetype_description" not in done_migrations:
            has_notetype = db.table_exists("notetypemodel") or db.table_exists("notetype")
            if not has_notetype or ("description" in [col.name for col in db.get_columns("notetypemodel" if db.table_exists("notetypemodel") else "notetype")]):
                router.model.create(name="020_notetype_description")
                logger.info("Base legacy détectée : enregistrement rétroactif de la migration 020_notetype_description.")

        # Si les tables consultant_sessions et consultant_messages existent déjà
        if "022_consultant_sessions" not in done_migrations and db.table_exists("consultant_sessions") and db.table_exists("consultant_messages"):
            router.model.create(name="022_consultant_sessions")
            logger.info("Base legacy détectée : enregistrement rétroactif de la migration 022_consultant_sessions.")

        # Si la table document_pages existe déjà ou si total_pages existe sur documentmodel
        if "024_document_multimedia_and_albums" not in done_migrations:
            has_doc_pages = db.table_exists("document_pages")
            doc_cols = [col.name for col in db.get_columns("documentmodel")] if db.table_exists("documentmodel") else []
            if has_doc_pages or ("total_pages" in doc_cols):
                router.model.create(name="024_document_multimedia_and_albums")
                logger.info("Base legacy détectée : enregistrement rétroactif de la migration 024_document_multimedia_and_albums.")

        # Si les colonnes page_number et heading_path existent déjà sur document_chunks
        if "025_document_chunk_pages_and_headings" not in done_migrations and db.table_exists("document_chunks"):
            chunk_cols = [col.name for col in db.get_columns("document_chunks")]
            if "page_number" in chunk_cols and "heading_path" in chunk_cols:
                router.model.create(name="025_document_chunk_pages_and_headings")
                logger.info("Base legacy détectée : enregistrement rétroactif de la migration 025_document_chunk_pages_and_headings.")

        # Nettoyage et synchronisation de la table note_chunk_links
        if db.table_exists("note_chunk_links"):
            try:
                db.execute_sql("CREATE UNIQUE INDEX IF NOT EXISTS note_chunk_links_note_chunk ON note_chunk_links (note_id, chunk_id);")
            except Exception as e:
                logger.debug("Remarque sur l'index note_chunk_links : %s", e)

    logger.info("Vérification et exécution des migrations BDD...")
    try:
        try:
            db.execute_sql("PRAGMA foreign_keys = OFF;")
        except Exception as fk_err:
            logger.debug("Remarque sur PRAGMA foreign_keys = OFF : %s", fk_err)

        # Exécute toutes les migrations en attente
        router.run()

        # Vérification post-migration : s'assurer que personas possède llm_config_id
        if db.table_exists("personas"):
            cols = [col.name for col in db.get_columns("personas")]
            if "llm_config_id" not in cols:
                try:
                    db.execute_sql("ALTER TABLE personas ADD COLUMN llm_config_id INTEGER REFERENCES llm_configs (id);")
                    logger.info("Colonne 'llm_config_id' ajoutée post-migration à la table 'personas'.")
                except Exception as e:
                    logger.debug("Remarque sur l'ajout post-migration de llm_config_id sur personas : %s", e)

        # Vérification post-migration : auto-guérison de la table document_chunks
        if db.table_exists("document_chunks"):
            chunk_cols = [col.name for col in db.get_columns("document_chunks")]
            if "page_number" not in chunk_cols:
                try:
                    db.execute_sql("ALTER TABLE document_chunks ADD COLUMN page_number INTEGER;")
                    logger.info("Colonne 'page_number' ajoutée post-migration à la table 'document_chunks'.")
                except Exception as e:
                    logger.debug("Remarque sur l'ajout post-migration de page_number sur document_chunks : %s", e)
            if "heading_path" not in chunk_cols:
                try:
                    db.execute_sql("ALTER TABLE document_chunks ADD COLUMN heading_path VARCHAR(255);")
                    logger.info("Colonne 'heading_path' ajoutée post-migration à la table 'document_chunks'.")
                except Exception as e:
                    logger.debug("Remarque sur l'ajout post-migration de heading_path sur document_chunks : %s", e)
            if "start_time" not in chunk_cols:
                try:
                    db.execute_sql("ALTER TABLE document_chunks ADD COLUMN start_time REAL;")
                    logger.info("Colonne 'start_time' ajoutée post-migration à la table 'document_chunks'.")
                except Exception as e:
                    logger.debug("Remarque sur l'ajout post-migration de start_time sur document_chunks : %s", e)
            if "end_time" not in chunk_cols:
                try:
                    db.execute_sql("ALTER TABLE document_chunks ADD COLUMN end_time REAL;")
                    logger.info("Colonne 'end_time' ajoutée post-migration à la table 'document_chunks'.")
                except Exception as e:
                    logger.debug("Remarque sur l'ajout post-migration de end_time sur document_chunks : %s", e)
            if "media_id" not in chunk_cols:
                try:
                    db.execute_sql("ALTER TABLE document_chunks ADD COLUMN media_id INTEGER REFERENCES mediamodel (id) ON DELETE SET NULL;")
                    logger.info("Colonne 'media_id' ajoutée post-migration à la table 'document_chunks'.")
                except Exception as e:
                    logger.debug("Remarque sur l'ajout post-migration de media_id sur document_chunks : %s", e)
            if "bounding_box" not in chunk_cols:
                try:
                    db.execute_sql("ALTER TABLE document_chunks ADD COLUMN bounding_box VARCHAR(255);")
                    logger.info("Colonne 'bounding_box' ajoutée post-migration à la table 'document_chunks'.")
                except Exception as e:
                    logger.debug("Remarque sur l'ajout post-migration de bounding_box sur document_chunks : %s", e)

        # Vérification dynamique de la colonne flags sur cardmodel
        if db.table_exists("cardmodel"):
            card_cols = [col.name for col in db.get_columns("cardmodel")]
            if "flags" not in card_cols:
                try:
                    db.execute_sql("ALTER TABLE cardmodel ADD COLUMN flags INTEGER DEFAULT 0;")
                    logger.info("Colonne 'flags' ajoutée dynamiquement à la table 'cardmodel'.")
                except Exception as e:
                    logger.debug("Remarque sur l'ajout de flags sur cardmodel : %s", e)

        try:
            db.execute_sql("PRAGMA foreign_keys = ON;")
        except Exception as fk_err:
            logger.debug("Remarque sur PRAGMA foreign_keys = ON : %s", fk_err)

        logger.info("Migrations BDD achevées avec succès.")
    except (peewee.DatabaseError, sqlite3.Error) as e:
        try:
            db.execute_sql("PRAGMA foreign_keys = ON;")
        except Exception as fk_err:
            logger.debug("Remarque sur PRAGMA foreign_keys = ON en rollback : %s", fk_err)
        logger.critical("Erreur critique lors de l'exécution des migrations : %s", e, exc_info=True)
        raise
