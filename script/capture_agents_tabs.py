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

window._on_view_selected("agents")
view = window._view_widgets.get("agents")

if view and hasattr(view, "persona_tree"):
    root = view.persona_tree.invisibleRootItem()
    for i in range(root.childCount()):
        item = root.child(i)
        if item.childCount() > 0:
            view.persona_tree.setCurrentItem(item.child(0))
            break
        else:
            view.persona_tree.setCurrentItem(item)
            break

for _ in range(8):
    app.processEvents()

# Capture Tab 0: Identité & Moteur
if view and hasattr(view, "_switch_subtab"):
    view._switch_subtab(0)
    for _ in range(8):
        app.processEvents()
    out_identity = Path("temp/screens/agents_view_tab_identity.png")
    out_identity.parent.mkdir(parents=True, exist_ok=True)
    window.grab().save(str(out_identity))
    print("✅ Saved Tab Identity to", out_identity)

# Capture Tab 1: Prompt & Instructions
if view and hasattr(view, "_switch_subtab"):
    view._switch_subtab(1)
    for _ in range(8):
        app.processEvents()
    out_prompt = Path("temp/screens/agents_view_tab_prompt.png")
    window.grab().save(str(out_prompt))
    print("✅ Saved Tab Prompt to", out_prompt)

# Capture Tab 2: Permissions d'outils
if view and hasattr(view, "_switch_subtab"):
    view._switch_subtab(2)
    for _ in range(8):
        app.processEvents()
    out_tools = Path("temp/screens/agents_view_tab_tools.png")
    window.grab().save(str(out_tools))
    print("✅ Saved Tab Tools to", out_tools)
