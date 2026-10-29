import os
import re
import shutil
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from ankiforge.database.backup import (
    backup_before_colpkg_import,
    backup_database,
    check_db_integrity,
    restore_granular_backup,
    restore_latest_valid_backup,
)

pytestmark = pytest.mark.integration


def test_backup_database_skips_if_no_db(tmp_path: Path):
    """Vérifie que la fonction s'arrête silencieusement si la base source n'existe pas."""
    fake_db_path = tmp_path / "non_existent.db"

    with patch("ankiforge.database.backup.ProfileManager.get_db_path") as mock_get_db_path:
        mock_get_db_path.return_value = fake_db_path

        # L'exécution ne doit lever aucune exception
        backup_database()


def test_backup_database_creates_and_rotates(tmp_path: Path):
    """Vérifie que la sauvegarde copie bien le fichier et supprime les sauvegardes les plus anciennes pour respecter la limite imposée."""
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


def test_backup_database_closes_all_sqlite_connections(tmp_path: Path, monkeypatch):
    """Régression Windows : les connexions ouvertes par la sauvegarde doivent être fermées pour ne pas retenir un verrou de fichier sur la base source ou la copie."""
    fake_db = tmp_path / "ankiforge.db"
    seed = sqlite3.connect(str(fake_db))
    seed.execute("CREATE TABLE t (id int);")
    seed.commit()
    seed.close()

    fake_profile_dir = tmp_path / "profile"
    fake_profile_dir.mkdir()

    opened: list[sqlite3.Connection] = []
    real_connect = sqlite3.connect

    def tracking_connect(*args, **kwargs):
        connection = real_connect(*args, **kwargs)
        opened.append(connection)
        return connection

    monkeypatch.setattr("ankiforge.database.backup.sqlite3.connect", tracking_connect)

    with (
        patch("ankiforge.database.backup.ProfileManager.get_db_path", return_value=fake_db),
        patch("ankiforge.database.backup.get_active_profile", return_value="default"),
        patch("ankiforge.database.backup.ProfileManager.PROFILES_DIR", fake_profile_dir),
    ):
        backup_database()

    assert opened, "La sauvegarde doit ouvrir au moins une connexion SQLite"
    for connection in opened:
        with pytest.raises(sqlite3.ProgrammingError):
            connection.execute("SELECT 1;")


def test_check_db_integrity_closes_connection(tmp_path: Path, monkeypatch):
    """Régression Windows : ``check_db_integrity`` ne doit pas laisser sa connexion ouverte."""
    db_path = tmp_path / "healthy.db"
    seed = sqlite3.connect(str(db_path))
    seed.execute("CREATE TABLE t (id int);")
    seed.commit()
    seed.close()

    opened: list[sqlite3.Connection] = []
    real_connect = sqlite3.connect

    def tracking_connect(*args, **kwargs):
        connection = real_connect(*args, **kwargs)
        opened.append(connection)
        return connection

    monkeypatch.setattr("ankiforge.database.backup.sqlite3.connect", tracking_connect)

    assert check_db_integrity(db_path) is True

    assert opened, "Le contrôle d'intégrité doit ouvrir une connexion SQLite"
    for connection in opened:
        with pytest.raises(sqlite3.ProgrammingError):
            connection.execute("SELECT 1;")


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


def _seed_backup_profile(tmp_path: Path) -> tuple[Path, Path]:
    """Crée une base de profil minimale saine et retourne (dossier des profils, base active)."""
    profiles_dir = tmp_path / "profiles"
    profile_dir = profiles_dir / "default"
    (profile_dir / "backups").mkdir(parents=True)

    active_db = profile_dir / "ankiforge.db"
    seed = sqlite3.connect(str(active_db))
    seed.execute("CREATE TABLE notes (id int, front text);")
    seed.execute("INSERT INTO notes VALUES (1, 'Question');")
    seed.commit()
    seed.close()

    return profiles_dir, active_db


def test_backup_before_colpkg_import_creates_valid_snapshot(tmp_path: Path):
    """La sauvegarde pré-importation est nommée, stockée dans `backups/` et intègre."""
    profiles_dir, active_db = _seed_backup_profile(tmp_path)

    with (
        patch("ankiforge.database.backup.ProfileManager.get_db_path", return_value=active_db),
        patch("ankiforge.database.backup.get_active_profile", return_value="default"),
        patch("ankiforge.database.backup.ProfileManager.PROFILES_DIR", profiles_dir),
    ):
        backup_path = backup_before_colpkg_import()

    backup_dir = profiles_dir / "default" / "backups"
    assert backup_path.parent == backup_dir
    assert re.fullmatch(r"ankiforge_backup_precolpkg_\d{8}_\d{6}\.db", backup_path.name)
    assert backup_path.exists()
    assert check_db_integrity(backup_path) is True

    # Le contenu de la base est bien celui du profil actif
    with sqlite3.connect(str(backup_path)) as conn:
        assert conn.execute("SELECT front FROM notes WHERE id=1;").fetchone() == ("Question",)


def test_backup_before_colpkg_import_survives_standard_rotation(tmp_path: Path):
    """La sauvegarde pré-colpkg échappe à la rotation `keep_last` de `backup_database()`."""
    profiles_dir, active_db = _seed_backup_profile(tmp_path)
    backup_dir = profiles_dir / "default" / "backups"
    for day in range(1, 4):
        (backup_dir / f"ankiforge_backup_2020010{day}_000000.db").write_text("ancienne")

    with (
        patch("ankiforge.database.backup.ProfileManager.get_db_path", return_value=active_db),
        patch("ankiforge.database.backup.get_active_profile", return_value="default"),
        patch("ankiforge.database.backup.ProfileManager.PROFILES_DIR", profiles_dir),
    ):
        precolpkg_path = backup_before_colpkg_import()

        # Trois rotations successives avec une limite très stricte
        for _ in range(3):
            backup_database(keep_last=1)

    assert precolpkg_path.exists(), "La sauvegarde pré-colpkg a été emportée par la rotation."
    assert check_db_integrity(precolpkg_path) is True

    standard_backups = [b for b in backup_dir.glob("ankiforge_backup_*.db") if "_precolpkg_" not in b.name]
    assert len(standard_backups) == 1, "La rotation standard n'a pas respecté la limite."


def test_backup_before_colpkg_import_raises_when_no_database(tmp_path: Path):
    """Sans base à sauvegarder, l'import doit être interrompu par une erreur explicite."""
    profiles_dir = tmp_path / "profiles"
    missing_db = profiles_dir / "default" / "ankiforge.db"

    with (
        patch("ankiforge.database.backup.ProfileManager.get_db_path", return_value=missing_db),
        patch("ankiforge.database.backup.get_active_profile", return_value="default"),
        patch("ankiforge.database.backup.ProfileManager.PROFILES_DIR", profiles_dir),
        pytest.raises(RuntimeError),
    ):
        backup_before_colpkg_import()


def test_backup_before_colpkg_import_closes_all_sqlite_connections(tmp_path: Path, monkeypatch):
    """Régression Windows : aucune connexion ne doit rester ouverte après l'instantané."""
    profiles_dir, active_db = _seed_backup_profile(tmp_path)

    opened: list[sqlite3.Connection] = []
    real_connect = sqlite3.connect

    def tracking_connect(*args, **kwargs):
        connection = real_connect(*args, **kwargs)
        opened.append(connection)
        return connection

    monkeypatch.setattr("ankiforge.database.backup.sqlite3.connect", tracking_connect)

    with (
        patch("ankiforge.database.backup.ProfileManager.get_db_path", return_value=active_db),
        patch("ankiforge.database.backup.get_active_profile", return_value="default"),
        patch("ankiforge.database.backup.ProfileManager.PROFILES_DIR", profiles_dir),
    ):
        backup_before_colpkg_import()

    assert opened, "L'instantané doit ouvrir au moins une connexion SQLite"
    for connection in opened:
        with pytest.raises(sqlite3.ProgrammingError):
            connection.execute("SELECT 1;")


def _make_restore_env(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Crée un profil avec backup sain + base active corrompue. Retourne (profiles_dir, backup, active_db)."""
    profile_name = "test_restore_atomic"
    p_dir = tmp_path / "profiles" / profile_name
    backup_dir = p_dir / "backups"
    backup_dir.mkdir(parents=True)

    healthy_db = tmp_path / "healthy.db"
    conn = sqlite3.connect(str(healthy_db))
    conn.execute("CREATE TABLE t (id int);")
    conn.execute("INSERT INTO t VALUES (1);")
    conn.commit()
    conn.close()

    valid_backup = backup_dir / "ankiforge_backup_20260906_120000.db"
    shutil.copy2(healthy_db, valid_backup)

    active_db = p_dir / "ankiforge.db"
    active_db.write_bytes(b"CORRUPT ACTIVE DB")

    return p_dir, valid_backup, active_db


def test_restore_latest_valid_backup_ecriture_atomique(tmp_path: Path, monkeypatch):
    """Restauration de secours : écriture dans un .tmp puis os.replace, jamais de copy2 directe sur la base active."""
    p_dir, valid_backup, active_db = _make_restore_env(tmp_path)

    copy_calls: list[tuple[str, str]] = []
    replace_calls: list[tuple[str, str]] = []
    real_copy2 = shutil.copy2
    real_replace = os.replace

    def spy_copy2(src, dst, *args, **kwargs):
        copy_calls.append((str(src), str(dst)))
        return real_copy2(src, dst, *args, **kwargs)

    def spy_replace(src, dst, *args, **kwargs):
        replace_calls.append((str(src), str(dst)))
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr("ankiforge.database.backup.shutil.copy2", spy_copy2)
    monkeypatch.setattr("ankiforge.database.backup.os.replace", spy_replace)

    with (
        patch("ankiforge.database.backup.ProfileManager.PROFILES_DIR", tmp_path / "profiles"),
        patch("ankiforge.database.backup.ProfileManager.get_db_path", return_value=active_db),
    ):
        assert restore_latest_valid_backup("test_restore_atomic") is True

    assert any(dst.endswith(".db.tmp") for _, dst in copy_calls), f"Pas d'écriture dans .tmp : {copy_calls}"
    assert not any(dst == str(active_db) for _, dst in copy_calls), "copy2 ne doit pas écrire directement sur la base active"
    assert any(src.endswith(".db.tmp") and dst == str(active_db) for src, dst in replace_calls), f"os.replace .tmp -> base active manquant : {replace_calls}"

    assert check_db_integrity(active_db) is True
    with sqlite3.connect(str(active_db)) as conn:
        assert conn.execute("SELECT id FROM t WHERE id=1;").fetchone() == (1,)


def test_restore_granular_backup_ecriture_atomique(tmp_path: Path, monkeypatch):
    """Restauration granulaire : écriture dans un .tmp puis os.replace, jamais de copy2 directe sur la base active."""
    p_dir, valid_backup, active_db = _make_restore_env(tmp_path)

    copy_calls: list[tuple[str, str]] = []
    replace_calls: list[tuple[str, str]] = []
    real_copy2 = shutil.copy2
    real_replace = os.replace

    def spy_copy2(src, dst, *args, **kwargs):
        copy_calls.append((str(src), str(dst)))
        return real_copy2(src, dst, *args, **kwargs)

    def spy_replace(src, dst, *args, **kwargs):
        replace_calls.append((str(src), str(dst)))
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr("ankiforge.database.backup.shutil.copy2", spy_copy2)
    monkeypatch.setattr("ankiforge.database.backup.os.replace", spy_replace)

    with (
        patch("ankiforge.database.backup.ProfileManager.PROFILES_DIR", tmp_path / "profiles"),
        patch("ankiforge.database.backup.ProfileManager.get_db_path", return_value=active_db),
        patch("ankiforge.database.backup.get_active_profile", return_value="test_restore_atomic"),
    ):
        assert restore_granular_backup("test_restore_atomic", valid_backup.name, create_safety_snapshot=False) is True

    assert any(dst.endswith(".db.tmp") for _, dst in copy_calls), f"Pas d'écriture dans .tmp : {copy_calls}"
    assert not any(dst == str(active_db) for _, dst in copy_calls), "copy2 ne doit pas écrire directement sur la base active"
    assert any(dst == str(active_db) for _, dst in replace_calls), f"os.replace vers la base active manquant : {replace_calls}"

    assert check_db_integrity(active_db) is True
