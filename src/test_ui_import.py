import sys
from PySide6.QtWidgets import QApplication
from ankiforge.database.models import db
from ankiforge.ui.views.documents_view import DocumentsView

db.connect()

app = QApplication(sys.argv)
view = DocumentsView()

# Simuler l'import depuis l'UI
view._on_worker_finished("Mon super titre", "Voici mon contenu")

print("Current doc id:", view._current_doc_id)
print("Stack index:", view.editor_stack.currentIndex())
