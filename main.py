import os
import sys

os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-logging --log-level=3 --disable-skia-graphite"
os.environ["QT_LOGGING_RULES"] = "qt.webenginecontext.*=false"

from PySide6.QtWidgets import QApplication

from src.database.models import init_db
from src.ui.main_window import MainWindow
from src.services.ai.base import MockProvider
from src.services.ai.flexible_service import OllamaProvider


def main():
    init_db()

    ai_provider = MockProvider()
    try:
        print("Initialisation du service IA...")
        ai_provider = OllamaProvider(model_name="llama2")
    except Exception as e:
        print(f"⚠️ Erreur avec l'IA, passage sur le MockProvider : {e}")

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = MainWindow(ai_provider)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
