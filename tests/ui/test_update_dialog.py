from pathlib import Path

from pytestqt.qtbot import QtBot

from ankiforge.services.update_checker import UpdateInfo
from ankiforge.ui.components.topbar import TopBar
from ankiforge.ui.dialogs.update_dialog import UpdateDialog


def test_update_dialog_creation(qtbot: QtBot) -> None:
    """Vérifie l'initialisation et le contenu de la boîte de dialogue UpdateDialog."""
    info = UpdateInfo(
        version="0.3.0",
        title="AnkiForge 0.3.0",
        release_notes="## Améliorations\n- Vitesse de compilation x2",
        html_url="https://github.com/Skyl9/AnkiForge/releases/tag/v0.3.0",
        published_at="2026-09-01T08:00:00Z",
    )
    dialog = UpdateDialog(info)
    qtbot.addWidget(dialog)

    assert "v0.3.0" in dialog.windowTitle()
    assert "Améliorations" in dialog.notes_browser.toPlainText()


def test_topbar_update_badge_display(qtbot: QtBot) -> None:
    """Vérifie que la TopBar affiche le badge lors de la réception d'une mise à jour."""
    topbar = TopBar()
    qtbot.addWidget(topbar)
    topbar.show()

    assert topbar.update_btn.isHidden() is True

    info = UpdateInfo(
        version="0.3.0",
        title="AnkiForge 0.3.0",
        release_notes="Nouvelle version",
        html_url="https://github.com/Skyl9/AnkiForge/releases/tag/v0.3.0",
        published_at="2026-09-01T08:00:00Z",
    )
    topbar.set_update_available(info)

    assert topbar.update_btn.isVisible() is True
    assert "v0.3.0" in topbar.update_btn.text()


def test_update_dialog_download_ui_transitions(qtbot: QtBot, tmp_path: Path) -> None:
    """Vérifie la transition des états visuels lors de la progression du téléchargement."""
    info = UpdateInfo(
        version="0.3.0",
        title="AnkiForge 0.3.0",
        release_notes="Notes",
        html_url="https://github.com/Skyl9/AnkiForge/releases/tag/v0.3.0",
        published_at="2026-09-01T08:00:00Z",
        assets=[{"name": "AnkiForge-macos-arm64.dmg", "browser_download_url": "https://example.com/dmg"}],
    )
    dialog = UpdateDialog(info)
    qtbot.addWidget(dialog)
    dialog.show()

    assert dialog.progress_container.isVisible() is False

    # Simulation d'un événement de progression
    dialog._on_download_progress(50, 50 * 1024 * 1024, 100 * 1024 * 1024)
    assert dialog.progress_bar.value() == 50
    assert "50.0 Mo" in dialog.progress_status_lbl.text()

    # Simulation de la fin de téléchargement
    dummy_dest = tmp_path / "AnkiForge-macos-arm64.dmg"
    dummy_dest.write_bytes(b"content")
    dialog._on_download_finished(dummy_dest, "abcdef1234567890")
    assert dialog.progress_bar.value() == 100
    assert "Téléchargement vérifié" in dialog.progress_status_lbl.text() or "Téléchargé avec succès" in dialog.progress_status_lbl.text()
