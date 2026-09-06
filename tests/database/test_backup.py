import shutil
import sqlite3
from pathlib import Path
from unittest.mock import patch

from ankiforge.database.backup import backup_database, check_db_integrity, restore_latest_valid_backup


def test_backup_database_skips_if_no_db(tmp_path: Path):
    """Vérifie que la fonction s'arrête silencieusement si la base source n'existe pas."""
    fake_db_path = tmp_path / "non_existent.db"

    with patch("ankiforge.database.backup.ProfileManager.get_db_path") as mock_get_db_path:
        mock_get_db_path.return_value = fake_db_path

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

    fake_profile_dir = tmp_path / "profile"
    fake_profile_dir.mkdir()

    # On détourne les variables globales pour pointer vers notre dossier temporaire
    with (
        patch("ankiforge.database.backup.ProfileManager.get_db_path", return_value=fake_db),
        patch("ankiforge.database.backup.get_active_profile", return_value="default"),
        patch("ankiforge.database.backup.ProfileManager.PROFILES_DIR", fake_profile_dir),
    ):
        # Création de 3 fausses anciennes sauvegardes avec des dates antérieures
        backup_dir = fake_profile_dir / "default" / "backups"
        backup_dir.mkdir(parents=True)
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


def test_check_db_integrity_and_restore(tmp_path: Path):
    """Vérifie le diagnostic d'intégrité et la restauration automatique depuis une sauvegarde saine."""
    # 1. Base saine
    healthy_db = tmp_path / "healthy.db"
    conn = sqlite3.connect(str(healthy_db))
    conn.execute("CREATE TABLE test (id int);")
    conn.commit()
    conn.close()
    assert check_db_integrity(healthy_db) is True

    # 2. Fichier corrompu
    corrupt_db = tmp_path / "corrupt.db"
    corrupt_db.write_bytes(b"NOT A SQLITE FILE HEADER GARBAGE DATA")
    assert check_db_integrity(corrupt_db) is False

    # 3. Test restauration
    fake_profile_dir = tmp_path / "profiles"
    profile_name = "test_restore"
    p_dir = fake_profile_dir / profile_name
    backup_dir = p_dir / "backups"
    backup_dir.mkdir(parents=True)

    # Copie de la base saine dans les backups
    valid_backup = backup_dir / "ankiforge_backup_20260906_120000.db"
    shutil.copy2(healthy_db, valid_backup)

    # Base active corrompue
    active_db = p_dir / "ankiforge.db"
    active_db.write_bytes(b"CORRUPT ACTIVE DB")

    with (
        patch("ankiforge.database.backup.ProfileManager.PROFILES_DIR", fake_profile_dir),
        patch("ankiforge.database.backup.ProfileManager.get_db_path", return_value=active_db),
    ):
        restored = restore_latest_valid_backup(profile_name)
        assert restored is True
        assert check_db_integrity(active_db) is True

        # Vérifie qu'un fichier de quarantaine a été créé
        quarantined = list(p_dir.glob("ankiforge_corrupt_*.db"))
        assert len(quarantined) == 1
