import os
import sys

from ankiforge.database.models import init_db, seed_initial_data
from ankiforge.services.ai.flexible_service import AIManager
from ankiforge.ui.main_window import MainWindow

os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-logging --log-level=3 --disable-skia-graphite"
os.environ["QT_LOGGING_RULES"] = "qt.webenginecontext.*=false"

from PySide6.QtWidgets import QApplication




def main():
    init_db()
    seed_initial_data()
    ai_manager = AIManager()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = MainWindow(ai_manager)
    window.show()

    sys.exit(app.exec())
if __name__ == "__main__":
    main()
