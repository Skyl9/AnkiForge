import os
import sys

os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-logging --log-level=3 --disable-skia-graphite"
os.environ["QT_LOGGING_RULES"] = "qt.webenginecontext.*=false"

from PySide6.QtWidgets import QApplication

from src.database.models import init_db
from src.ui.main_window import MainWindow
from src.services.ai.base import MockProvider
from src.services.ai.flexible_service import OllamaProvider, AIManager


def main():
    init_db()

    # 🆕 On utilise notre nouveau manager
    ai_manager = AIManager()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = MainWindow(ai_manager)
    window.show()

    sys.exit(app.exec())
if __name__ == "__main__":
    main()
