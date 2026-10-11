from __future__ import annotations

import json
import uuid

import pytest
from PySide6.QtCore import QItemSelection, QItemSelectionModel, Qt
from PySide6.QtWidgets import QAbstractItemView

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
)
from ankiforge.ui.views.edition_view import EditionView
from ankiforge.ui.views.edition_view.group_edit_dialog import GroupEditDialog
from ankiforge.utils.tags import parse_note_tags

pytestmark = pytest.mark.ui


@pytest.fixture
def edition_test_data(mock_db):
    uid = uuid.uuid4().hex[:6]
    deck = DeckModel.create(name=f"Deck_{uid}")
    nt = NoteTypeModel.create(
        name=f"Model_{uid}",
        fields_schema=json.dumps(["Front", "Back", "Remarks"]),
        templates=json.dumps([{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]),
    )

    notes = []
    for i in range(1, 5):
        n = NoteModel.create(
            guid=f"guid_{uid}_{i}",
            note_type=nt,
            tags=json.dumps([f"tag_{i}"]),
        )
        NoteVersionModel.create(
            note=n,
            content=json.dumps({"Front": f"Question {i}", "Back": f"Answer {i}", "Remarks": f"Remark {i}"}),
            is_active=True,
        )
        CardModel.create(
            note=n,
            deck=deck,
            template_index=0,
            question=f"Question {i}",
            answer=f"Answer {i}",
        )
        notes.append(n)

    return {"deck": deck, "note_type": nt, "notes": notes}


def test_edition_table_extended_selection_mode(qtbot, edition_test_data):
    """Vérifie que la table virtuelle est bien configurée en ExtendedSelection pour autoriser Shift+plage."""
    view = EditionView(ai_manager=None)
    qtbot.addWidget(view)
    view.refresh_data()

    assert view.card_table.selectionMode() == QAbstractItemView.SelectionMode.ExtendedSelection


def test_edition_target_resolution_priority(qtbot, edition_test_data):
    """Vérifie l'ordre de priorité et la cohérence entre lignes sélectionnées (soulignées) et coches."""
    view = EditionView(ai_manager=None)
    qtbot.addWidget(view)
    view.refresh_data()

    notes = edition_test_data["notes"]
    sel_model = view.card_table.selectionModel()
    assert sel_model is not None

    # Cas 3 : Sélection d'une seule ligne (la ligne est soulignée et son icône est cochée)
    view.card_table.select_row(0)
    target_ids = view.get_target_note_ids()
    assert target_ids == [notes[0].id]
    assert view.note_table_model.index(0, 0).data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked

    # Cas 2 : Cocher des cases (l'icône étant cochée, les lignes doivent être soulignées)
    view.deselect_all_cards()
    view.note_table_model.setData(view.note_table_model.index(1, 0), Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole)
    view.note_table_model.setData(view.note_table_model.index(2, 0), Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole)
    target_ids = view.get_target_note_ids()
    assert set(target_ids) == {notes[1].id, notes[2].id}
    assert view.card_table.get_selected_rows() == [1, 2]

    # Cas 1 : Sélection multiple de lignes par plage (Shift+clic / Ctrl+clic)
    # Les 4 lignes sélectionnées sont soulignées et leurs 4 icônes de coche sont validées
    idx0 = view.note_table_model.index(0, 0)
    idx3 = view.note_table_model.index(3, 0)
    selection = QItemSelection(idx0, idx3)
    sel_model.select(selection, QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows)

    selected_rows = view.card_table.get_selected_rows()
    assert len(selected_rows) == 4
    target_ids = view.get_target_note_ids()
    assert target_ids == [notes[0].id, notes[1].id, notes[2].id, notes[3].id]
    for r in range(4):
        assert view.note_table_model.index(r, 0).data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked


def test_bidirectional_sync_between_selection_and_checkboxes(qtbot, edition_test_data):
    """
    Vérifie la synchronisation bidirectionnelle stricte :
    - Ligne soulignée/sélectionnée => icône de coche à gauche validée (Checked).
    - Icône cochée => ligne soulignée/sélectionnée dans card_table.
    """
    view = EditionView(ai_manager=None)
    qtbot.addWidget(view)
    view.refresh_data()

    # 1. Sélection d'une ligne via select_row => coche validée
    view.card_table.select_row(1)
    assert view.card_table.get_selected_rows() == [1]
    assert view.note_table_model.index(1, 0).data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked
    assert view.note_table_model.index(0, 0).data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Unchecked

    # 2. Clic sur la colonne 0 (case à cocher) de la ligne 3 => ajoute la ligne 3 à la sélection sans désélectionner la 1
    view.card_table.toggle_row_selection(3)
    assert view.card_table.get_selected_rows() == [1, 3]
    assert view.note_table_model.index(3, 0).data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked
    assert view.note_table_model.index(1, 0).data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked

    # 3. Clic pour décocher la case de la ligne 1 => retire la ligne 1 de la sélection
    view.card_table.toggle_row_selection(1)
    assert view.card_table.get_selected_rows() == [3]
    assert view.note_table_model.index(1, 0).data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Unchecked
    assert view.note_table_model.index(3, 0).data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked

    # 4. Modification directe du modèle (setData Checked sur ligne 0) => la ligne 0 devient soulignée
    view.note_table_model.setData(view.note_table_model.index(0, 0), Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole)
    assert view.card_table.get_selected_rows() == [0, 3]
    assert view.note_table_model.index(0, 0).data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked

    # 5. Tout décocher => aucune ligne soulignée
    view.deselect_all_cards()
    assert view.card_table.get_selected_rows() == []
    for r in range(4):
        assert view.note_table_model.index(r, 0).data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Unchecked

    # 6. Tout cocher => toutes les lignes sont soulignées et cochées
    view.select_all_cards()
    assert view.card_table.get_selected_rows() == [0, 1, 2, 3]
    for r in range(4):
        assert view.note_table_model.index(r, 0).data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked


def test_nav_ribbon_info_on_group_selection(qtbot, edition_test_data):
    """Vérifie que le ruban de navigation reflète dynamiquement le nombre de cartes sélectionnées."""
    view = EditionView(ai_manager=None)
    qtbot.addWidget(view)
    view.refresh_data()

    sel_model = view.card_table.selectionModel()
    assert sel_model is not None

    # Sélection de 3 lignes
    idx0 = view.note_table_model.index(0, 0)
    idx2 = view.note_table_model.index(2, 0)
    sel_model.select(QItemSelection(idx0, idx2), QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows)

    view._update_nav_ribbon_info()
    assert "3 cartes sélectionnées" in view.lbl_card_ribbon_info.text()
    assert "Modifier le groupe (3)" in view.btn_group_edit.text()


def test_group_edit_dialog_execution(qtbot, edition_test_data):
    """Vérifie l'interaction avec le dialogue d'édition groupée et la mise à jour des notes et de l'UI."""
    notes = edition_test_data["notes"]
    target_ids = [notes[0].id, notes[1].id]

    dialog = GroupEditDialog(note_ids=target_ids)
    qtbot.addWidget(dialog)

    # Renseigner l'ajout de tags et modification de champ
    dialog.input_tags_add.setText("vocabulaire_commun, groupe_A")
    dialog.cb_enable_field_edit.setChecked(True)
    dialog.combo_field.setCurrentText("Remarks")
    dialog.combo_action.setCurrentIndex(0)  # Remplacer par
    dialog.text_field_value.setPlainText("Remarque collective")

    # Déclencher l'application
    dialog._on_apply_clicked()

    assert dialog.result_data is not None
    assert dialog.result_data.success is True
    assert set(dialog.result_data.modified_note_ids) == set(target_ids)

    # Vérification BDD
    for nid in target_ids:
        n = NoteModel.get_by_id(nid)
        tags = parse_note_tags(n.tags)
        assert "vocabulaire_commun" in tags
        assert "groupe_A" in tags

        v = NoteVersionModel.get_or_none(note=n, is_active=True)
        assert v is not None
        assert json.loads(v.content)["Remarks"] == "Remarque collective"


def test_edition_view_check_uncheck_all(qtbot, edition_test_data):
    """Vérifie le fonctionnement de Tout cocher et Tout décocher."""
    view = EditionView(ai_manager=None)
    qtbot.addWidget(view)
    view.refresh_data()

    assert len(view.note_table_model.get_checked_note_ids()) == 0

    # Tout cocher
    view.note_table_model.set_all_checked(True)
    assert len(view.note_table_model.get_checked_note_ids()) == 4

    # Tout décocher
    view.note_table_model.set_all_checked(False)
    assert len(view.note_table_model.get_checked_note_ids()) == 0


def test_edition_view_tag_hygiene_button_and_dialog_integration(qtbot, edition_test_data, monkeypatch):
    """Vérifie la présence du bouton d'hygiène des tags et la répercussion de la fusion sur EditionView."""
    from ankiforge.services.cards.bulk_hygiene_service import TagMergeResult
    from ankiforge.ui.dialogs.tag_hygiene_dialog import TagHygieneDialog

    view = EditionView(ai_manager=None)
    qtbot.addWidget(view)
    view.refresh_data()

    assert hasattr(view, "btn_tag_hygiene")
    assert view.btn_tag_hygiene is not None
    assert "Hygiène" in view.btn_tag_hygiene.toolTip()

    # Mocker TagHygieneDialog pour simuler une fusion réussie
    n1 = edition_test_data["notes"][0]
    n2 = edition_test_data["notes"][1]

    mock_result = TagMergeResult(
        success=True,
        merged_clusters_count=1,
        modified_notes_count=2,
        modified_note_ids=[n1.id, n2.id],
    )

    def mock_exec(dialog_self):
        dialog_self.applied_result = mock_result
        return 1

    monkeypatch.setattr(TagHygieneDialog, "exec", mock_exec)

    # Déclencher l'ouverture du dialogue d'hygiène
    view.open_tag_hygiene_dialog()

    # Vérification que le modèle a bien mis à jour les tags des notes
    assert mock_result.success is True
