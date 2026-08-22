import os
import sys
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from ankiforge.database.models import init_db
from ankiforge.ui.main_window import MainWindow

def main():
    app = QApplication.instance() or QApplication(sys.argv)
    init_db()

    output_dir = Path("temp/ide_ux_verification")
    output_dir.mkdir(parents=True, exist_ok=True)

    with patch("ankiforge.services.background_daemon.BackgroundDaemon"), patch("ankiforge.ui.views.dashboard_view.StatsWorker.start"):
        win = MainWindow(ai_manager=None)
        win.resize(1400, 880)
        win.show()
        app.processEvents()

        # 1. Dashboard View
        win._on_view_selected("dashboard")
        app.processEvents()
        win.grab().save(str(output_dir / "1_dashboard_breadcrumb.png"))

        # 2. Creation View (Top toolbar + QScrollArea)
        win._on_view_selected("creation")
        app.processEvents()
        win.grab().save(str(output_dir / "2_creation_top_toolbar.png"))

        # 3. Batch Factory (Unfolded terminal)
        win._on_view_selected("batch")
        app.processEvents()
        win.grab().save(str(output_dir / "3_batch_unfolded.png"))

        # 4. Batch Factory (Folded terminal drawer)
        batch_view = win.stacked_widget.currentWidget()
        if hasattr(batch_view, "_toggle_terminal"):
            batch_view._toggle_terminal()
            app.processEvents()
            win.grab().save(str(output_dir / "4_batch_folded_drawer.png"))

        # 5. Edition View (Placeholder state)
        win._on_view_selected("edition")
        app.processEvents()
        win.grab().save(str(output_dir / "5_edition_placeholder.png"))

        # 6. Documents View (Responsive frame)
        win._on_view_selected("documents")
        app.processEvents()
        win.grab().save(str(output_dir / "6_documents_responsive.png"))

    print("Screenshots captured successfully in temp/ide_ux_verification!")

if __name__ == "__main__":
    main()
