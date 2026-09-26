import sqlite3
from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QMessageBox

from ankiforge.database.backup import BackupInfo
from ankiforge.ui.widgets.settings_modal.tabs.storage_tab import StorageMaintenanceTab

pytestmark = pytest.mark.ui


def test_storage_tab_backups_table_and_restore(qtbot, tmp_path):
    tab = StorageMaintenanceTab()
    qtbot.addWidget(tab)

    fake_backup_dir = tmp_path / "backups"
    fake_backup_dir.mkdir(parents=True)
    fake_db = tmp_path / "ankiforge.db"
    fake_db.write_text("ACTIVE DB DATA")

    # Création d'une sauvegarde saine
    b_healthy = fake_backup_dir / "ankiforge_backup_20260901_100000.db"
    conn = sqlite3.connect(str(b_healthy))
    conn.execute("CREATE TABLE t (id int);")
    conn.commit()
    conn.close()

    with (
        patch("ankiforge.ui.widgets.settings_modal.tabs.storage_tab.list_profile_backups") as mock_list,
        patch("ankiforge.ui.widgets.settings_modal.tabs.storage_tab.get_active_profile", return_value="default"),
    ):
        mock_list.return_value = [
            BackupInfo(
                filename=b_healthy.name,
                filepath=b_healthy,
                created_at=b_healthy.stat().st_mtime,
                size_bytes=b_healthy.stat().st_size,
                is_valid=True,
                is_prerestore=False,
            )
        ]
        tab.refresh_metrics()

        assert tab.table_backups.rowCount() == 1
        # Test restore action
        with (
            patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes),
            patch("ankiforge.ui.widgets.settings_modal.tabs.storage_tab.restore_granular_backup", return_value=True) as mock_restore,
            patch("ankiforge.ui.widgets.settings_modal.tabs.storage_tab.restart_application") as mock_restart,
        ):
            # Click restore button
            btn_restore = tab.table_backups.cellWidget(0, 4)
            assert btn_restore is not None
            btn_restore.click()
            mock_restore.assert_called_once()
            qtbot.waitUntil(lambda: mock_restart.called, timeout=1500)
