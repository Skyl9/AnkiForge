with open("src/ankidraft/ui/views/analysis_view.py") as f:
    content = f.read()

# On rajoute l'import de LinterWorker
if "LinterWorker" not in content:
    content = content.replace("from ankidraft.ui.components.duplicate_widgets", "from ankidraft.services.workers.linter_worker import LinterWorker\nfrom ankidraft.ui.components.duplicate_widgets")

with open("src/ankidraft/ui/views/analysis_view.py", "w") as f:
    f.write(content)
