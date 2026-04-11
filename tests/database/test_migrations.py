from ankiforge.database.migration import run_migrations
from ankiforge.database.models import SchemaVersionModel


def test_run_migrations_idempotency(mock_db):
    """
    Vérifie que le script de migration crée la table de version,
    incrémente la version correctement, et ne plante pas s'il est lancé plusieurs fois.
    """
    # La fixture mock_db a déjà créé le schéma complet en mémoire.
    # Nous supprimons manuellement la table de version pour simuler
    # un utilisateur migrant d'une version V1 sans système de suivi.
    SchemaVersionModel.drop_table(safe=True)

    # 1. Première exécution (Simulation d'une mise à jour)
    run_migrations()

    # Vérifications : La table a été créée et la version est actée
    assert SchemaVersionModel.table_exists(), "La table SchemaVersionModel n'a pas été créée."
    version_record = SchemaVersionModel.get_by_id(1)
    assert version_record.version == 2, "La version du schéma n'a pas été incrémentée à 2."

    # 2. Deuxième exécution (Simulation des lancements quotidiens de l'application)
    # L'appel suivant doit s'exécuter silencieusement sans exception (Idempotence)
    run_migrations()

    # La version doit rester bloquée à 2
    version_record = SchemaVersionModel.get_by_id(1)
    assert version_record.version == 2, "La version du schéma a été modifiée anormalement."
