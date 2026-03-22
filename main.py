# main.py
import sys
import os

os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-logging --log-level=3 --disable-skia-graphite"
os.environ["QT_LOGGING_RULES"] = "qt.webenginecontext.*=false"

from PySide6.QtWidgets import QApplication

from src.database.models import init_db
from src.services.ai.flexible_service import OllamaProvider
from src.ui.main_window import MainWindow
from src.services.ai.base import MockProvider
from src.services.ai.gemini_service import GeminiService  # IMPORT DE GEMINI
from src.services.prompt_manager import PromptManager



def main():
    # 1. Initialisation BDD
    init_db()

    # 3. Initialisation Services (Injection de dépendance)
    ai_provider = MockProvider()
    try:
        print("Initialisation du service IA...")
        # Choisis "openrouter" ou "groq" selon ton choix
        ai_provider = OllamaProvider(model_name="llama2")
    except Exception as e:
        print(f"⚠️ Erreur avec l'IA, passage sur le MockProvider : {e}")

    prompt_manager = PromptManager()

    # 4. Lancement UI
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # On passe le moteur IA à la fenêtre principale
    window = MainWindow(ai_provider, prompt_manager)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
