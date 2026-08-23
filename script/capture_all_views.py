"""
Script automatisé pour capturer les 11 vues de l'application AnkiForge avec un thème forcé.
"""

import sys
import os
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from unittest.mock import patch

from ankiforge.utils.paths import get_project_root
from ankiforge.ui.style_engine import get_style_engine
from ankiforge.database.models import init_db
from ankiforge.database.migration import run_migrations


def capture_views(output_dir: Path, theme_id: str = "ide") -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    init_db()
    run_migrations()

    app = QApplication.instance() or QApplication([])

    engine = get_style_engine()
    engine.save_theme_preference("default", theme_id)
    engine.apply_theme(theme_id, app)

    from ankiforge.ui.main_window import MainWindow

    with patch("ankiforge.ui.views.dashboard_view.StatsWorker.start"):
        window = MainWindow(ai_manager=None, profile_name="default")
        window.resize(1440, 900)
        window.show()
        app.processEvents()

        views = [
            "dashboard",
            "creation",
            "edition",
            "analysis",
            "consultant",
            "batch",
            "documents",
            "card_models",
            "agents",
            "pipelines",
            "ab_tests",
        ]

        for vid in views:
            try:
                window._on_view_selected(vid)
                app.processEvents()
                for _ in range(5):
                    app.processEvents()

                pixmap = window.grab()
                filepath = output_dir / f"{vid}.png"
                pixmap.save(str(filepath))
                print(f"Captured: {vid} -> {filepath}")
            except Exception as e:
                print(f"Error capturing {vid}: {e}")


if __name__ == "__main__":
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else get_project_root() / "temp" / "visual_diffs" / "current"
    theme = sys.argv[2] if len(sys.argv) > 2 else "ide"
    capture_views(out_dir, theme)
