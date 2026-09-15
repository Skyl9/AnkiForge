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

window._on_view_selected("pipelines")
view = window._view_widgets.get("pipelines")

for _ in range(8):
    app.processEvents()

out_dir = Path("temp/screens")
out_dir.mkdir(parents=True, exist_ok=True)

# 1. Capture Overview (Paramètres & Prompt)
out_overview = out_dir / "pipelines_view_overview.png"
window.grab().save(str(out_overview))
print("✅ Saved Pipelines Overview to", out_overview)

if view:
    # 2. Capture de l'onglet Transitions DAG
    if hasattr(view, "inspector") and hasattr(view.inspector, "_switch_subtab"):
        view.inspector._switch_subtab(1)
        for _ in range(8):
            app.processEvents()
        out_dag_tab = out_dir / "pipelines_view_dag_tab.png"
        window.grab().save(str(out_dag_tab))
        print("✅ Saved DAG tab to", out_dag_tab)
        # Revenir au tab 0
        view.inspector._switch_subtab(0)
        for _ in range(8):
            app.processEvents()

    # 3. Capture d'une autre étape si disponible
    if len(view.current_steps) > 1:
        view._on_step_selected(1)
        for _ in range(8):
            app.processEvents()
        out_step1 = out_dir / "pipelines_view_step_1.png"
        window.grab().save(str(out_step1))
        print("✅ Saved Step 1 to", out_step1)

    # 4. Capture du catalogue StepPickerDialog
    from ankiforge.ui.views.pipelines_view import PromptPreviewDialog, StepPickerDialog

    dlg_picker = StepPickerDialog(personas=view._cached_personas)
    dlg_picker.show()
    for _ in range(8):
        app.processEvents()
    out_picker = out_dir / "pipelines_view_step_picker.png"
    dlg_picker.grab().save(str(out_picker))
    dlg_picker.close()
    print("✅ Saved Step Picker to", out_picker)

    # 5. Capture de la modale PromptPreviewDialog
    dlg_preview = PromptPreviewDialog("Extrais les concepts clés depuis :\n{{ state.variables.text_source }}\n\nGénère les cartes pour l'utilisateur :\n{{ state.initial_prompt }}")
    dlg_preview.show()
    for _ in range(8):
        app.processEvents()
    out_preview = out_dir / "pipelines_view_prompt_preview.png"
    dlg_preview.grab().save(str(out_preview))
    dlg_preview.close()
    print("✅ Saved Prompt Preview to", out_preview)
