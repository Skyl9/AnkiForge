"""
Capture d'écran autonome d'AnkiForge pour inspection visuelle et validation UI.
Usage :
    uv run python script/capture_view.py --view creation --output temp/screens/creation.png
    uv run python script/capture_view.py --all --output temp/screens/
    uv run python script/capture_view.py --view analysis --theme catppuccin_mocha --layout macos
"""

import argparse
import os
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    DocumentChunkModel,
    DocumentModel,
    NoteChunkLinkModel,
    NoteModel,
    NoteTypeModel,
)
from ankiforge.ui.style_engine import get_style_engine
from ankiforge.utils.paths import get_project_root


def seed_rich_demo_data() -> None:
    """Peuple la base de données SQLite avec des données réalistes si elle est vide."""
    if NoteModel.select().count() > 0 and DocumentModel.select().count() > 0:
        return

    # Paquet démo
    deck, _ = DeckModel.get_or_create(name="Sciences::Physique Quantique", defaults={"description": "Cours de physique moderne"})
    deck_maths, _ = DeckModel.get_or_create(name="Sciences::Mathématiques", defaults={"description": "Algèbre & Analyse"})

    # Modèles
    nt_basic = NoteTypeModel.select().where(NoteTypeModel.name == "Basique").first()
    if not nt_basic:
        nt_basic = NoteTypeModel.create(name="Basique", fields_schema='["Front", "Back"]', description="Questions simples Q/R")

    # Document & Chunks
    doc, _ = DocumentModel.get_or_create(
        title="Physique Quantique - Chapitre 1 : Dualité Onde-Corpuscule",
        defaults={
            "content": "# Physique Quantique\n\n## 1. Dualité Onde-Corpuscule\n"
            "La relation de de Broglie associe une longueur d'onde lambda à toute particule d'impulsion p : "
            "lambda = h / p.\n\n## 2. Principe d'Incertitude d'Heisenberg\n"
            "Il est impossible de mesurer simultanément la position x et l'impulsion p d'une particule avec "
            "une précision infinie : Delta x * Delta p >= hbar / 2.",
            "file_type": "md",
        },
    )

    chunk1, _ = DocumentChunkModel.get_or_create(
        document=doc,
        chunk_index=0,
        defaults={
            "heading_path": "Chapitre 1 > Dualité Onde-Corpuscule",
            "page_number": 1,
            "content": "La relation de de Broglie associe une longueur d'onde lambda à toute particule d'impulsion p : lambda = h / p.",
            "content_hash": "hash_chunk_1",
        },
    )

    # Notes & Versions
    note1 = NoteModel.create(note_type=nt_basic, tags="quantique physique formule")
    note1.add_version(
        {"Front": "Quelle est la <b>relation de de Broglie</b> pour la longueur d'onde de matière ?", "Back": "La longueur d'onde est donnée par :<br>\\[ \\lambda = \\frac{h}{p} \\]"},
        source="ai_generator",
    )
    CardModel.create(note=note1, deck=deck)
    NoteChunkLinkModel.get_or_create(note=note1, chunk=chunk1)

    note2 = NoteModel.create(note_type=nt_basic, tags="maths algebre")
    note2.add_version(
        {
            "Front": "Énoncer l'<b>inégalité de Cauchy-Schwarz</b> dans un espace préhilbertien réel :",
            "Back": "Pour tous vecteurs \\( x, y \\) :<br>\\[ |\\langle x, y \\rangle| \\le \\|x\\| \\cdot \\|y\\| \\]",
        },
        source="manual",
    )
    CardModel.create(note=note2, deck=deck_maths)


def capture(
    view_name: str | None = None,
    capture_all: bool = False,
    output_path: str | None = None,
    theme_id: str = "ide",
    layout_id: str = "ide",
    profile_name: str = "default",
    width: int = 1440,
    height: int = 900,
    populate_data: bool = True,
) -> None:
    from ankiforge.services.profile_manager import ProfileManager

    pm = ProfileManager()
    pm.switch_profile(profile_name)
    if populate_data:
        seed_rich_demo_data()

    app = QApplication.instance() or QApplication([])

    # Thème
    engine = get_style_engine()
    engine.save_theme_preference("default", theme_id)
    engine.apply_theme(theme_id, app)

    from ankiforge.ui.main_window import MainWindow

    with patch("ankiforge.ui.views.dashboard_view.StatsWorker.start"):
        window = MainWindow(ai_manager=None, profile_name="default")
        window.resize(width, height)
        window.show()
        app.processEvents()

        if layout_id != "ide":
            window.apply_layout(layout_id)
            app.processEvents()

        all_views = list(window.VIEW_REGISTRY.keys())

        if capture_all:
            out_dir = Path(output_path) if output_path else get_project_root() / "temp" / "screens"
            out_dir.mkdir(parents=True, exist_ok=True)

            for vid in all_views:
                try:
                    window._on_view_selected(vid)
                    for _ in range(6):
                        app.processEvents()
                    target_file = out_dir / f"{vid}.png"
                    window.grab().save(str(target_file))
                    print(f"✅ Capture réussie : {vid} -> {target_file}")
                except Exception as e:
                    print(f"❌ Erreur sur {vid} : {e}")
        else:
            target_view = view_name or "dashboard"
            if target_view not in all_views:
                print(f"⚠️ Vue inconnue '{target_view}'. Vues disponibles : {', '.join(all_views)}")
                return

            window._on_view_selected(target_view)
            for _ in range(6):
                app.processEvents()

            if output_path:
                target_file = Path(output_path)
                target_file.parent.mkdir(parents=True, exist_ok=True)
            else:
                target_file = get_project_root() / "temp" / "screens" / f"{target_view}.png"
                target_file.parent.mkdir(parents=True, exist_ok=True)

            window.grab().save(str(target_file))
            print(f"✅ Capture réussie : {target_view} -> {target_file}")


def main():
    parser = argparse.ArgumentParser(description="Capture d'écran autonome des vues AnkiForge")
    parser.add_argument("--view", type=str, default="creation", help="Nom de la vue à capturer")
    parser.add_argument("--all", action="store_true", help="Capturer toutes les vues")
    parser.add_argument("--output", type=str, default=None, help="Chemin de sortie du fichier ou dossier PNG")
    parser.add_argument("--theme", type=str, default="ide", help="Identifiant du thème (ex: ide, dark_modern, catppuccin_mocha, nord)")
    parser.add_argument("--layout", type=str, default="ide", help="Identifiant du layout (ide, macos, dashboard, glassmorphism)")
    parser.add_argument("--profile", type=str, default="default", help="Nom du profil / espace de travail")
    parser.add_argument(
        "--preset", type=str, choices=["macbook13", "macbook14", "macbook16", "fhd", "hd"], default=None, help="Preset de résolution d'écran (macbook13: 1280x800, macbook14: 1512x982, etc.)"
    )
    parser.add_argument("--width", type=int, default=1440, help="Largeur en pixels")
    parser.add_argument("--height", type=int, default=900, help="Hauteur en pixels")
    parser.add_argument("--no-populate", action="store_true", help="Ne pas insérer de données démo")

    args = parser.parse_args()

    # Appliquer les presets de résolution si spécifié
    width = args.width
    height = args.height
    if args.preset == "macbook13":
        width, height = 1280, 800
    elif args.preset == "macbook14":
        width, height = 1512, 982
    elif args.preset == "macbook16":
        width, height = 1728, 1117
    elif args.preset == "fhd":
        width, height = 1920, 1080
    elif args.preset == "hd":
        width, height = 1366, 768

    capture(
        view_name=args.view,
        capture_all=args.all,
        output_path=args.output,
        theme_id=args.theme,
        layout_id=args.layout,
        profile_name=args.profile,
        width=width,
        height=height,
        populate_data=not args.no_populate,
    )


if __name__ == "__main__":
    main()
