import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtWidgets import QApplication

from ankiforge.database.migration import run_migrations
from ankiforge.services.profile_manager import ProfileManager
from ankiforge.ui.main_window import MainWindow
from ankiforge.ui.style_engine import get_style_engine
from script.capture_view import seed_rich_demo_data

pm = ProfileManager()
pm.switch_profile("default")
run_migrations()
seed_rich_demo_data()

app = QApplication.instance() or QApplication([])
engine = get_style_engine()
engine.apply_theme("ide", app)

window = MainWindow(ai_manager=None, profile_name="default")
window.resize(1280, 800)
window.show()
app.processEvents()

window._on_view_selected("ab-tests")
view = window._view_widgets.get("ab-tests")

for _ in range(8):
    app.processEvents()

out_dir = Path("temp/screens")
out_dir.mkdir(parents=True, exist_ok=True)

# 1. Mode 0 : Moteur vs Moteur (Rendu Cartes)
out_mode0 = out_dir / "ab_tests_overview_mode0.png"
window.grab().save(str(out_mode0))
print("✅ Saved AB Tests Mode 0 to", out_mode0)

if view:
    # 2. Mode 1 : Prompts / Personas
    view.mode_combo.setCurrentIndex(1)
    for _ in range(8):
        app.processEvents()
    out_mode1 = out_dir / "ab_tests_mode1_prompts.png"
    window.grab().save(str(out_mode1))
    print("✅ Saved AB Tests Mode 1 to", out_mode1)

    # 3. Mode 2 : Pipelines DAG
    view.mode_combo.setCurrentIndex(2)
    for _ in range(8):
        app.processEvents()
    out_mode2 = out_dir / "ab_tests_mode2_pipelines.png"
    window.grab().save(str(out_mode2))
    print("✅ Saved AB Tests Mode 2 to", out_mode2)

    # 4. Mode 0 - Subtab 1 (Tableau des Champs)
    view.mode_combo.setCurrentIndex(0)
    view._switch_view_mode(1)
    for _ in range(8):
        app.processEvents()
    out_table = out_dir / "ab_tests_subtab_table.png"
    window.grab().save(str(out_table))
    print("✅ Saved AB Tests Table to", out_table)

    # 5. Subtab 2 (JSON Brut)
    view._switch_view_mode(2)
    for _ in range(8):
        app.processEvents()
    out_json = out_dir / "ab_tests_subtab_json.png"
    window.grab().save(str(out_json))
    print("✅ Saved AB Tests JSON to", out_json)

    # 6. Mode 0 avec Winner State (Résultats simulés)
    view._switch_view_mode(0)
    view.kpi_a.set_results(elapsed=1.12, cards_count=3, tokens=520, cost_usd=0.0012, is_success=True)
    view.kpi_b.set_results(elapsed=2.85, cards_count=3, tokens=610, cost_usd=0.0018, is_success=True)
    view._evaluate_winner()
    for _ in range(8):
        app.processEvents()
    out_winner = out_dir / "ab_tests_winner_state.png"
    window.grab().save(str(out_winner))
    print("✅ Saved AB Tests Winner State to", out_winner)

    # 7. Thème Clair (JetBrains Light)
    engine.apply_theme("jetbrains_light", app)
    for _ in range(8):
        app.processEvents()
    out_light = out_dir / "ab_tests_light.png"
    window.grab().save(str(out_light))
    print("✅ Saved AB Tests Light to", out_light)
