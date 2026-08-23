"""
Script de capture de transition sombre vers clair pour Batch Factory.
"""

import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from unittest.mock import patch

from ankiforge.database.models import init_db
from ankiforge.database.migration import run_migrations
from ankiforge.utils.paths import get_project_root
from ankiforge.ui.style_engine import get_style_engine


def test_batch_transition():
    init_db()
    run_migrations()

    app = QApplication.instance() or QApplication([])

    engine = get_style_engine()
    engine.save_theme_preference("default", "ide")
    engine.apply_theme("ide", app)

    from ankiforge.ui.main_window import MainWindow

    out_dir = get_project_root() / "temp" / "transition_batch"
    out_dir.mkdir(parents=True, exist_ok=True)

    with patch("ankiforge.ui.views.dashboard_view.StatsWorker.start"):
        window = MainWindow(ai_manager=None, profile_name="default")
        window.resize(1440, 900)
        window.show()
        app.processEvents()

        # 1. Dark Batch Initial
        window._on_view_selected("batch")
        for _ in range(5):
            app.processEvents()
        window.grab().save(str(out_dir / "1_dark_batch.png"))

        # 2. Switch to Light Mode Live
        engine.set_color_mode("light", app)
        for _ in range(5):
            app.processEvents()
        window.grab().save(str(out_dir / "2_light_batch.png"))

        # 3. Switch back to Dark Mode Live
        engine.set_color_mode("dark", app)
        for _ in range(5):
            app.processEvents()
        window.grab().save(str(out_dir / "3_dark_again_batch.png"))

        print("Captures batch terminées !")


if __name__ == "__main__":
    test_batch_transition()
