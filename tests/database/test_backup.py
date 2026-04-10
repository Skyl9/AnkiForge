from pathlib import Path
from unittest.mock import patch

from ankiforge.database.backup import backup_database


def test_backup_database_skips_if_no_db():
    """Vérifie que la fonction s'arrête silencieusement si la base source n'existe pas."""
    with patch("ankiforge.database.backup.DB_PATH") as mock_db_path:
        mock_db_path.exists.return_value = False

        # L'exécution ne doit lever aucune exception
        backup_database()


def test_backup_database_creates_and_rotates(tmp_path: Path):
    """
    Vérifie que la sauvegarde copie bien le fichier et supprime les
    sauvegardes les plus anciennes pour respecter la limite imposée.
    """
    # 1. Préparation de l'environnement de test (fichiers temporaires)
    fake_db = tmp_path / "ankiforge.db"
    fake_db.write_text("fake sqlite data")

    fake_app_dir = tmp_path / "appdata"
    fake_app_dir.mkdir()

    # On détourne les variables globales pour pointer vers notre dossier temporaire
    with patch("ankiforge.database.backup.DB_PATH", fake_db), \
            patch("ankiforge.database.backup.get_app_data_dir", return_value=fake_app_dir):
        # Création de 3 fausses anciennes sauvegardes avec des dates antérieures
        backup_dir = fake_app_dir / "backups"
        backup_dir.mkdir()
        (backup_dir / "ankiforge_backup_20200101_000000.db").write_text("old1")
        (backup_dir / "ankiforge_backup_20200102_000000.db").write_text("old2")
        (backup_dir / "ankiforge_backup_20200103_000000.db").write_text("old3")

        # 2. Exécution avec une limite stricte de 2 fichiers
        backup_database(keep_last=2)

        # 3. Vérifications
        backups = sorted(list(backup_dir.glob("ankiforge_backup_*.db")))

        # Il doit rester exactement 2 fichiers (la limite configurée)
        assert len(backups) == 2, "La rotation n'a pas respecté la limite de fichiers."

        # Le fichier le plus ancien (20200101) a dû être purgé.
        # Le fichier de 20200103 doit avoir survécu, ainsi que le tout nouveau backup.
        assert "20200101" not in backups[0].name, "L'ancienne sauvegarde n'a pas été supprimée."