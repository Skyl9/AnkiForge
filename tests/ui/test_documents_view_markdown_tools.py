"""Tests UI pour DocumentOutlineWidget et les outils Markdown de DocumentsView."""

import pytest
from PySide6.QtWidgets import QDialog
from pytestqt.qtbot import QtBot

from ankiforge.database.models import DocumentModel
from ankiforge.services.markdown.models import HeadingRepairItem
from ankiforge.ui.dialogs.repair_headings_dialog import RepairHeadingsDialog
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


def test_documents_view_markdown_actions(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    view = DocumentsView()
    qtbot.addWidget(view)

    # Vérifie la présence des composants
    assert hasattr(view, "btn_format_md")
    assert hasattr(view, "outline_widget")

    # Crée un document de test avec saut anormal H1 -> H3
    doc = DocumentModel.create(
        title="Doc Test Markdown",
        content=("# Titre Valide\n\nCette infor-\nmation est impor-\ntante.\n\n### Sous-titre H3 Direct\n\nFormule : \\[ E = mc^2 \\]"),
        file_type="md",
    )
    view._current_doc_id = doc.id
    view.text_editor.set_content(doc.content)
    view.outline_widget.set_document_content(doc.content)

    # 1. Test réparation des titres avec dialogue accepté
    monkeypatch.setattr(RepairHeadingsDialog, "exec", lambda self: (self.accept(), QDialog.DialogCode.Accepted)[1])
    view._on_repair_document_headings()
    content_after_repair = view.text_editor.get_content()

    # Le H3 direct après H1 doit être devenu H2 et l'ancien H3 n'existe plus
    assert "## Sous-titre H3 Direct" in content_after_repair
    assert "### Sous-titre H3 Direct" not in content_after_repair
    assert view._dirty is True

    # Test de sécurité : Ctrl+Z (Undo) restaure le texte d'origine !
    view.text_editor.editor.undo()
    assert "### Sous-titre H3 Direct" in view.text_editor.get_content()
    # Redo réapplique la correction
    view.text_editor.editor.redo()
    assert "## Sous-titre H3 Direct" in view.text_editor.get_content()

    # 2. Test formatage global
    view._format_current_document()
    content_after_format = view.text_editor.get_content()
    assert "information" in content_after_format
    assert "importante" in content_after_format
    assert "$$\nE = mc^2\n$$" in content_after_format

    # 3. Test insertion de la table des matières in-place
    view._on_insert_document_toc()
    content_after_toc = view.text_editor.get_content()
    assert "<!-- toc -->" in content_after_toc
    assert "<!-- /toc -->" in content_after_toc
    assert "## Table des Matières" in content_after_toc
    assert "- [Sous-titre H3 Direct](#sous-titre-h3-direct)" in content_after_toc

    # Vérification anti-duplication lors d'un second clic
    view._on_insert_document_toc()
    content_second_toc = view.text_editor.get_content()
    assert content_second_toc.count("<!-- toc -->") == 1
    assert content_second_toc.count("## Table des Matières") == 1

    # Test Ctrl+Z sur la table des matières : annule la mise à jour puis l'insertion initiale
    view.text_editor.editor.undo()
    view.text_editor.editor.undo()
    assert "<!-- toc -->" not in view.text_editor.get_content()


def test_repair_headings_dialog_interactive(qtbot: QtBot) -> None:
    repairs = [
        HeadingRepairItem(
            line_number=5,
            raw_line="### Section Orpheline",
            title="Section Orpheline",
            old_level=3,
            new_level=2,
            reason="H1 ➔ H3",
        ),
        HeadingRepairItem(
            line_number=12,
            raw_line="##### Sous-Détail Profond",
            title="Sous-Détail Profond",
            old_level=5,
            new_level=3,
            reason="H2 ➔ H5",
        ),
    ]

    dialog = RepairHeadingsDialog(repairs)
    qtbot.addWidget(dialog)

    assert dialog.table.rowCount() == 2
    assert dialog.table.item(0, 1).text() == "L. 5"
    assert dialog.table.item(0, 2).text() == "Section Orpheline"
    assert dialog.table.item(0, 3).text() == "H3 ➔ H2"

    # Par défaut, toutes les réparations sont cochées
    dialog._on_apply()
    selected = dialog.get_selected_repairs()
    assert len(selected) == 2

    # Test Tout décocher
    dialog.btn_deselect_all.click()
    dialog._on_apply()
    assert len(dialog.get_selected_repairs()) == 0

    # Test Tout cocher
    dialog.btn_select_all.click()
    dialog._on_apply()
    assert len(dialog.get_selected_repairs()) == 2


def test_document_outline_depth_filtering(qtbot: QtBot) -> None:
    widget = DocumentOutlineWidget()
    qtbot.addWidget(widget)

    sample_md = "# H1 Titre\n\nTexte\n\n## H2 Sous-Titre\n\nTexte\n\n### H3 Détail\n\nTexte"
    widget.set_document_content(sample_md)

    root = widget.tree.topLevelItem(0)
    assert root is not None
    h2_item = root.child(0)
    assert h2_item is not None
    h3_item = h2_item.child(0)
    assert h3_item is not None

    # Par défaut (Tous), tout est visible
    assert not root.isHidden()
    assert not h2_item.isHidden()
    assert not h3_item.isHidden()

    # Filtre H1 uniquement
    widget.depth_group.button(1).click()
    assert not root.isHidden()
    assert h2_item.isHidden()
    assert h3_item.isHidden()

    # Filtre H1-H2
    widget.depth_group.button(2).click()
    assert not root.isHidden()
    assert not h2_item.isHidden()
    assert h3_item.isHidden()

    # Retour à Tous
    widget.depth_group.button(6).click()
    assert not root.isHidden()
    assert not h2_item.isHidden()
    assert not h3_item.isHidden()


def test_document_outline_active_line_scroll_spy(qtbot: QtBot) -> None:
    widget = DocumentOutlineWidget()
    qtbot.addWidget(widget)

    sample_md = "# Chapitre 1\n\nLigne 3\nLigne 4\n\n## Section 1.1\n\nLigne 8\nLigne 9\n\n# Chapitre 2\n\nLigne 13"
    widget.set_document_content(sample_md)

    # Curseur à la ligne 8 -> doit cibler Section 1.1
    widget.set_active_line(8)
    assert widget._active_item is not None
    assert "Section 1.1" in widget._active_item.text(0)

    # Curseur à la ligne 13 -> doit cibler Chapitre 2
    widget.set_active_line(13)
    assert widget._active_item is not None
    assert "Chapitre 2" in widget._active_item.text(0)


def test_document_outline_coverage_and_forge_signal(qtbot: QtBot) -> None:
    widget = DocumentOutlineWidget()
    qtbot.addWidget(widget)

    sample_md = "# Anatomie\n\nContenu anatomie.\n\n## Neuro\n\nContenu neuro."
    widget.set_document_content(sample_md)

    # Test transmission des données de couverture
    widget.set_coverage_data({"Anatomie": 5, "Neuro": 0})
    root = widget.tree.topLevelItem(0)
    assert root is not None
    assert "5" in root.toolTip(0) or "Couvert" in root.toolTip(0)

    sub = root.child(0)
    assert sub is not None
    assert "0" in sub.toolTip(0) or "Non couvert" in sub.toolTip(0)

    # Test signal de forge
    received_forge: list[tuple[str, str, int, int]] = []
    widget.forge_section_requested.connect(lambda t, c, s, e: received_forge.append((t, c, s, e)))

    widget._trigger_forge_section(sub)
    assert len(received_forge) == 1
    title, content, start, end = received_forge[0]
    assert title == "Neuro"
    assert "Contenu neuro" in content
    assert start == 5


def test_document_outline_controls_and_stats(qtbot: QtBot) -> None:
    widget = DocumentOutlineWidget()
    qtbot.addWidget(widget)

    sample_md = "# Intro\n\nUn deux trois.\n\n## Details\n\nQuatre cinq six sept."
    widget.set_document_content(sample_md)

    # Vérification des stats
    assert "2 sections" in widget.lbl_stats.text()
    assert "Profondeur max H2" in widget.lbl_stats.text()

    # Test repliage / dépliage
    widget.tree_collapse_all()
    root = widget.tree.topLevelItem(0)
    assert root is not None
    assert not root.isExpanded()

    widget.tree_expand_all()
    assert root.isExpanded()

    # Test effacement de recherche
    widget.search_input.setText("Intro")
    assert widget.search_input.text() == "Intro"
    widget.btn_clear_search.click()
    assert widget.search_input.text() == ""
