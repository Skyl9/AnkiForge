import sqlite3
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QDialog

from ankiforge.services.cards.import_manager import ImportAnalysisResult, ImportManager
from ankiforge.services.workers.import_cards_worker import ImportCardsWorker
from ankiforge.ui.dialogs.import_dialog import ImportDialog
from ankiforge.ui.views.dashboard_view import DashboardView


def _create_simple_apkg(file_path: Path) -> None:
    db_file = file_path.parent / "temp.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE col (id integer, models text, decks text)")
    conn.execute('INSERT INTO col VALUES (1, \'{"1": {"name": "Basic", "flds": [{"name": "Front"}, {"name": "Back"}]}}\', \'{"1": {"id": 1, "name": "Default"}}\')')
    conn.execute("CREATE TABLE notes (id integer primary key, guid text, mid integer, tags text, flds text)")
    conn.execute("INSERT INTO notes VALUES (1, 'guid_ui_1', 1, '', 'Q_UI\x1fA_UI')")
    conn.execute("CREATE TABLE cards (id integer primary key, nid integer, did integer, ord integer)")
    conn.execute("INSERT INTO cards VALUES (1, 1, 1, 0)")
    conn.commit()
    conn.close()

    with zipfile.ZipFile(file_path, "w") as zf:
        zf.write(db_file, "collection.anki2")
        zf.writestr("media", "{}")


def test_import_dialog_set_initial_file(qtbot) -> None:
    """Vérifie que set_initial_file préremplit l'input sans crash."""
    dialog = ImportDialog()
    qtbot.addWidget(dialog)

    fake_path = "/home/user/deck_test.apkg"
    dialog.set_initial_file(fake_path)

    assert dialog.path_input.text() == fake_path


def test_import_dialog_reject_cleans_temp_dir(qtbot) -> None:
    """Vérifie que reject() nettoie les répertoires temporaires d'analyse."""
    dialog = ImportDialog()
    qtbot.addWidget(dialog)

    temp_d = tempfile.mkdtemp(prefix="test_dialog_cleanup_")
    p = Path(temp_d)
    assert p.exists()

    analysis = ImportAnalysisResult(
        temp_dir=temp_d,
        source_type="apkg",
        sqlite_path=None,
        txt_path=None,
        new_notes=[],
        silent_updates=[],
        identical_count=0,
        conflicts=[],
        media_map={},
    )
    dialog.analysis_result = analysis

    dialog.reject()
    assert not p.exists()


def test_import_cards_worker_signals_success(qtbot, tmp_path: Path) -> None:
    """Vérifie que le worker d'analyse émet analysis_ready avec les bonnes données."""
    apkg_path = tmp_path / "worker_test.apkg"
    _create_simple_apkg(apkg_path)

    worker = ImportCardsWorker(path=apkg_path, mode="analyze")

    with qtbot.waitSignal(worker.analysis_ready, timeout=5000) as blocker:
        worker.start()

    res = blocker.args[0]
    assert isinstance(res, ImportAnalysisResult)
    assert len(res.new_notes) == 1
    assert res.new_notes[0]["guid"] == "guid_ui_1"


def test_import_cards_worker_signals_error_on_bad_file(qtbot, tmp_path: Path) -> None:
    """Vérifie que le worker émet error_signal en cas de fichier non valide."""
    bad_file = tmp_path / "corrupt.apkg"
    bad_file.write_text("invalid content")

    worker = ImportCardsWorker(path=bad_file, mode="analyze")

    with qtbot.waitSignal(worker.error_signal, timeout=5000) as blocker:
        worker.start()

    err_msg = blocker.args[0]
    assert "n'est pas une archive ZIP/APKG valide" in err_msg


def test_dashboard_drop_file_opens_import_dialog_cleanly(qtbot, tmp_path: Path) -> None:
    """Vérifie que le dépôt d'un fichier .apkg sur le Dashboard appelle set_initial_file sans AttributeError."""
    view = DashboardView()
    qtbot.addWidget(view)

    test_file = tmp_path / "drag_test.apkg"
    test_file.touch()

    # Simuler _on_file_selected
    with patch.object(QDialog, "show"), patch.object(QDialog, "raise_"), patch.object(QDialog, "activateWindow"):
        view._on_file_selected(str(test_file))

    assert view._import_dialog is not None
    assert view._import_dialog.path_input.text() == str(test_file)


def test_import_cards_worker_commit_mode(qtbot, tmp_path: Path) -> None:
    """Vérifie que le worker exécute commit_import en arrière-plan et émet commit_finished."""
    apkg_path = tmp_path / "worker_commit_test.apkg"
    _create_simple_apkg(apkg_path)

    mgr = ImportManager()
    analysis = mgr.analyze_archive(apkg_path)

    worker = ImportCardsWorker(mode="commit", import_manager=mgr, analysis=analysis)

    with qtbot.waitSignal(worker.commit_finished, timeout=5000) as blocker:
        worker.start()

    res = blocker.args[0]
    assert res["created"] == 1
    assert res["merged"] == 0


def test_import_dialog_full_async_flow(qtbot, tmp_path: Path) -> None:
    """Vérifie le cycle complet d'importation asynchrone dans ImportDialog sans bloquer l'UI."""
    apkg_path = tmp_path / "dialog_async_test.apkg"
    _create_simple_apkg(apkg_path)

    dialog = ImportDialog()
    qtbot.addWidget(dialog)
    dialog.set_initial_file(str(apkg_path))

    with qtbot.waitSignal(dialog.import_finished, timeout=5000) as blocker:
        dialog._start_import_analysis()

    summary = blocker.args[0]
    assert summary["created"] == 1
    assert dialog.result() == QDialog.DialogCode.Accepted
