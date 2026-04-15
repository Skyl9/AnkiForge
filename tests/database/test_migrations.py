from ankiforge.database.migration import run_migrations
from ankiforge.database.models import db, SchemaVersionModel


def test_run_migrations_idempotency(mock_db):
    """
    Vérifie que le script de migration crée la table de version,
    incrémente la version correctement, et ne plante pas s'il est lancé plusieurs fois.
    """
    # 1. On supprime la table de version pour simuler un vieil utilisateur
    SchemaVersionModel.drop_table(safe=True)

    # 2. Première exécution (La base possède déjà les colonnes via mock_db,
    # donc cela va tester notre bloc 'except OperationalError' de sécurité)
    run_migrations()

    # Vérifications de l'état
    assert SchemaVersionModel.table_exists(), "La table SchemaVersionModel n'a pas été créée."

    version_record = SchemaVersionModel.get_by_id(1)
    assert version_record.version == 100, "La version du schéma n'a pas été incrémentée à 100 (indicateur peewee-migrate)."

    # On vérifie que peewee-migrate a créé sa table d'historique
    assert db.table_exists("migratehistory"), "La table migratehistory de peewee-migrate est manquante."

    # ✨ NOUVEAU : On vérifie directement dans le moteur SQLite que les colonnes sont bien là
    columns = [col.name for col in db.get_columns("agents")]
    assert "output_format" in columns, "La colonne output_format est manquante dans la table agents."
    assert "created_at" in columns, "La colonne created_at est manquante dans la table agents."

    # 3. Deuxième exécution (Simulation d'un redémarrage de l'application)
    run_migrations()

    # La version doit rester à 100
    version_record = SchemaVersionModel.get_by_id(1)
    assert version_record.version == 100, "La version du schéma a été modifiée anormalement après la seconde passe."
