"""
Script de test interactif pour le toggle de la sidebar.
"""

import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from unittest.mock import patch

from ankiforge.database.models import init_db
from ankiforge.database.migration import run_migrations
from ankiforge.ui.main_window import MainWindow


def test_sidebar_toggle():
    init_db()
    run_migrations()

    app = QApplication.instance() or QApplication([])

    with patch("ankiforge.services.background_daemon.BackgroundDaemon"), patch("ankiforge.ui.views.dashboard_view.StatsWorker.start"):
        window = MainWindow(ai_manager=None, profile_name="default")
        window.resize(1440, 900)
        window.show()
        app.processEvents()

        sidebar = window.sidebar
        print(f"Sidebar initiale is_collapsed = {sidebar.is_collapsed}, width = {sidebar.width()}")

        # 1. Cliquer sur le bouton toggle_btn
        print("Clicking toggle_btn...")
        sidebar.toggle_btn.click()
        app.processEvents()

        print(f"Après 1er clic toggle_btn: is_collapsed = {sidebar.is_collapsed}, width = {sidebar.width()}")

        # 2. Cliquer sur logo_icon pour ré-étendre
        print("Clicking logo_icon...")
        sidebar.logo_icon.clicked.emit()
        app.processEvents()

        print(f"Après 2e clic logo_icon: is_collapsed = {sidebar.is_collapsed}, width = {sidebar.width()}")


if __name__ == "__main__":
    test_sidebar_toggle()
