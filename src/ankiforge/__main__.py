import os
import sys

from dotenv import load_dotenv

from ankiforge.database.models import init_db, seed_initial_data
from ankiforge.services.ai.flexible_service import AIManager
from ankiforge.ui.main_window import MainWindow
from ankiforge.ui.theme import apply_dark_theme, apply_light_theme, setup_dynamic_theme

os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-logging --log-level=3 --disable-skia-graphite"
os.environ["QT_LOGGING_RULES"] = "qt.webenginecontext.*=false"

from PySide6.QtWidgets import QApplication




def main():
    load_dotenv()
    init_db()
    seed_initial_data()
    ai_manager = AIManager()

    app = QApplication(sys.argv)

    setup_dynamic_theme(app)

    window = MainWindow(ai_manager)
    window.show()

    sys.exit(app.exec())
if __name__ == "__main__":
    main()
