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

# Select Agents View
window._on_view_selected("agents")
view = window._view_widgets.get("agents")

for _ in range(10):
    app.processEvents()

out_overview = Path("temp/screens/agents_view_current_overview.png")
out_overview.parent.mkdir(parents=True, exist_ok=True)
window.grab().save(str(out_overview))
print("✅ Saved Agents View Overview to", out_overview)

# If there's an agent in tree, select it
if view and hasattr(view, "tree_widget"):
    root = view.tree_widget.invisibleRootItem()
    if root.childCount() > 0:
        # Find first leaf persona
        for i in range(root.childCount()):
            item = root.child(i)
            if item.childCount() > 0:
                view.tree_widget.setCurrentItem(item.child(0))
                break
            else:
                view.tree_widget.setCurrentItem(item)
                break

for _ in range(10):
    app.processEvents()

out_selected = Path("temp/screens/agents_view_current_selected.png")
window.grab().save(str(out_selected))
print("✅ Saved Agents View Selected to", out_selected)
