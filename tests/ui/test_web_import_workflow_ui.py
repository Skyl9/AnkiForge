"""Test du flux d'import web couplé à DocumentsView (bouton « Importer depuis le Web »)."""

import uuid

from PySide6.QtCore import QObject, Signal

from ankiforge.database.models import DocumentModel
from ankiforge.ui.views.documents_view import DocumentsView


def test_web_import_flow_through_documents_view(qtbot, monkeypatch) -> None:
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Article Web {uid}",
        content="# Article\n\nContenu.",
        file_type="web",
        source_url="https://blog.example.com/article-1",
    )

    opened_with_parent = []
    cards_nav: list[tuple[str, dict]] = []

    class StubDialog(QObject):
        import_completed = Signal(list)
        cards_requested = Signal(int)

        def __init__(self, parent=None) -> None:
            super().__init__()
            opened_with_parent.append(parent)

        def exec(self) -> int:
            self.import_completed.emit([doc.id])
            self.cards_requested.emit(doc.id)
            return 1

    monkeypatch.setattr("ankiforge.ui.views.documents_view.view.UrlImportDialog", StubDialog)

    view = DocumentsView(ai_manager=None)
    qtbot.addWidget(view)
    view.request_navigation.connect(lambda target, payload: cards_nav.append((target, payload)))

    view._on_import_url()
    qtbot.wait(100)

    assert opened_with_parent, "Le dialogue d'import web doit être ouvert via DocumentsView"
    assert opened_with_parent[0] is view
    assert cards_nav == [("creation", {"doc_id": doc.id})], "Le clic « Créer des cartes » doit naviguer vers le Studio de Création"
    assert view._current_doc_id == doc.id or view.tree_explorer.currentItem() is not None, "Le document importé doit être sélectionné dans l'arbre"
