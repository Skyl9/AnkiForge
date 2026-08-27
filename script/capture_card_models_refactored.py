import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtWidgets import QApplication
from ankiforge.ui.main_window import MainWindow
from ankiforge.ui.style_engine import get_style_engine
from ankiforge.services.profile_manager import ProfileManager
from ankiforge.database.migration import run_migrations
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

# Select Card Models View
window._on_view_selected("card-models")
view = window._view_widgets.get("card-models")

if view:
    view.left_panel.tabs_bar.set_active_tab(0)
    if view.list_widget.count() > 0:
        view.list_widget.setCurrentRow(0)

for _ in range(8):
    app.processEvents()

# 1. State: Code & Live Preview Side-by-Side (Ouvert côte à côte)
if view:
    view.preview_container.setVisible(True)
    view.editor_horizontal_splitter.setSizes([520, 420])
    view._update_preview()

for _ in range(8):
    app.processEvents()

out_side = Path("temp/screens/card_models_side_by_side_open.png")
out_side.parent.mkdir(parents=True, exist_ok=True)
window.grab().save(str(out_side))
print("✅ Saved Side-by-Side Open to", out_side)

# 2. State: Code Full Width (Preview Closed / replié)
if view:
    view._hide_preview_panel()

for _ in range(8):
    app.processEvents()

out_closed = Path("temp/screens/card_models_side_by_side_closed.png")
window.grab().save(str(out_closed))
print("✅ Saved Side-by-Side Closed to", out_closed)
