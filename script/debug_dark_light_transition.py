"""
Script de reproduction et capture des problèmes lors du passage sombre -> clair.
"""

import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from ankiforge.database.migration import run_migrations
from ankiforge.database.models import init_db
from ankiforge.ui.style_engine import get_style_engine
from ankiforge.utils.paths import get_project_root


def test_transition():
    init_db()
    run_migrations()

    app = QApplication.instance() or QApplication([])

    engine = get_style_engine()
    engine.save_theme_preference("default", "ide")
    engine.apply_theme("ide", app)

    from ankiforge.ui.main_window import MainWindow

    out_dir = get_project_root() / "temp" / "transition_debug"
    out_dir.mkdir(parents=True, exist_ok=True)

    with patch("ankiforge.ui.views.dashboard_view.StatsWorker.start"):
        window = MainWindow(ai_manager=None, profile_name="default")
        window.resize(1440, 900)
        window.show()
        app.processEvents()

        # 1. Capture Dark Initial
        window._on_view_selected("dashboard")
        for _ in range(5):
            app.processEvents()
        window.grab().save(str(out_dir / "1_dark_initial_dashboard.png"))

        # 2. Switch to Light Mode Live
        engine.set_color_mode("light", app)
        for _ in range(5):
            app.processEvents()
        window.grab().save(str(out_dir / "2_switched_to_light_dashboard.png"))

        # 3. Switch to Creation View while in Light Mode
        window._on_view_selected("creation")
        for _ in range(5):
            app.processEvents()
        window.grab().save(str(out_dir / "3_switched_to_light_creation.png"))

        # 4. Switch back to Dark Mode Live
        engine.set_color_mode("dark", app)
        for _ in range(5):
            app.processEvents()
        window.grab().save(str(out_dir / "4_switched_back_to_dark_creation.png"))

        # 5. Switch back to Dashboard in Dark Mode
        window._on_view_selected("dashboard")
        for _ in range(5):
            app.processEvents()
        window.grab().save(str(out_dir / "5_switched_back_to_dark_dashboard.png"))

        print("Captures de transition terminées !")


if __name__ == "__main__":
    test_transition()
