with open("src/ankiforge/ui/views/analysis_view.py", "r") as f:
    content = f.read()

# On rajoute l'import de LinterWorker
if "LinterWorker" not in content:
    content = content.replace("from ankiforge.ui.components.duplicate_widgets", "from ankiforge.services.workers.linter_worker import LinterWorker\nfrom ankiforge.ui.components.duplicate_widgets")

with open("src/ankiforge/ui/views/analysis_view.py", "w") as f:
    f.write(content)
