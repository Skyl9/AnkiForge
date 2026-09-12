"""Tests UI pour DocumentOutlineWidget et les outils Markdown de DocumentsView."""

from pytestqt.qtbot import QtBot

from ankiforge.database.models import DocumentModel
from ankiforge.ui.views.documents_view.view import DocumentsView
from ankiforge.ui.widgets.document_outline import DocumentOutlineWidget


def test_document_outline_widget_population_and_selection(qtbot: QtBot) -> None:
    widget = DocumentOutlineWidget()
    qtbot.addWidget(widget)

    sample_md = "# Titre 1\n\nContenu 1.\n\n## Sous-Titre 1.1\n\nContenu 1.1.\n\n# Titre 2\n\nContenu 2."
    widget.set_document_content(sample_md)

    assert widget.tree.topLevelItemCount() == 2
    root1 = widget.tree.topLevelItem(0)
    assert root1 is not None
    assert "Titre 1" in root1.text(0)
    assert root1.childCount() == 1
    sub = root1.child(0)
    assert sub is not None
    assert "Sous-Titre 1.1" in sub.text(0)

    # Test signal d'émission au clic
    selected_lines: list[int] = []
    widget.heading_selected.connect(selected_lines.append)

    widget.tree.itemClicked.emit(sub, 0)
    assert len(selected_lines) == 1
    assert selected_lines[0] == 5


def test_document_outline_widget_filtering(qtbot: QtBot) -> None:
    widget = DocumentOutlineWidget()
    qtbot.addWidget(widget)

    sample_md = "# Anatomie Générale\n\n## Système Nerveux\n\n## Système Digestif"
    widget.set_document_content(sample_md)

    # Filtre sur 'nerveux'
    widget.search_input.setText("nerveux")
    root = widget.tree.topLevelItem(0)
    assert root is not None
    assert not root.isHidden()
    assert not root.child(0).isHidden()  # Système Nerveux
    assert root.child(1).isHidden()  # Système Digestif


def test_documents_view_markdown_actions(qtbot: QtBot) -> None:
    view = DocumentsView()
    qtbot.addWidget(view)

    # Vérifie la présence des composants
    assert hasattr(view, "btn_format_md")
    assert hasattr(view, "outline_widget")

    # Crée un document de test
    doc = DocumentModel.create(
        title="Doc Test Markdown",
        content=("#Titre Sans Espace\n\nCette infor-\nmation est impor-\ntante.\n\n### Sous-titre H3 Direct\n\nFormule : \\[ E = mc^2 \\]"),
        file_type="md",
    )
    view._current_doc_id = doc.id
    view.text_editor.set_content(doc.content)
    view.outline_widget.set_document_content(doc.content)

    # 1. Test réparation des titres
    view._on_repair_document_headings()
    content_after_repair = view.text_editor.get_content()
    # Le H3 direct après H1 doit être devenu H2
    assert "## Sous-titre H3 Direct" in content_after_repair
    assert view._dirty is True

    # 2. Test formatage global
    view._format_current_document()
    content_after_format = view.text_editor.get_content()
    assert "# Titre Sans Espace" in content_after_format
    assert "information" in content_after_format
    assert "importante" in content_after_format
    assert "$$\nE = mc^2\n$$" in content_after_format

    # 3. Test insertion de la table des matières
    view._on_insert_document_toc()
    content_after_toc = view.text_editor.get_content()
    assert "## Table des Matières" in content_after_toc
    assert "- [Titre Sans Espace](#titre-sans-espace)" in content_after_toc
