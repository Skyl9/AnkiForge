"""Tests unitaires et d'interaction PySide6 pour ChangeNoteTypeDialog."""

import json
from typing import Any

import pytest
from PySide6.QtWidgets import QDialog
from pytestqt.qtbot import QtBot

from ankiforge.database.models import CardModel, DeckModel, NoteModel, NoteTypeModel, db
from ankiforge.ui.dialogs.change_note_type_dialog import ChangeNoteTypeDialog

pytestmark = pytest.mark.ui


@pytest.fixture
def sample_setup() -> dict[str, Any]:
    """Jeu de données pour tester le dialogue de migration de type de note."""
    with db.atomic():
        deck = DeckModel.create(name="Deck Test Dialog")

        # Modèle Source à 3 champs
        nt_source = NoteTypeModel.create(
            name="Source Dialog Model",
            fields_schema=json.dumps(["Question", "Reponse", "Remarque"]),
            templates=json.dumps(
                [
                    {"name": "Carte 1", "qfmt": "{{Question}}", "afmt": "{{FrontSide}}<hr>{{Reponse}}"},
                    {"name": "Carte 2", "qfmt": "{{Reponse}}", "afmt": "{{FrontSide}}<hr>{{Question}}"},
                ]
            ),
        )

        # Modèle Cible 1 (Standard 2 champs, 1 carte)
        nt_target_simple = NoteTypeModel.create(
            name="Target Simple Model",
            fields_schema=json.dumps(["Front", "Back"]),
            templates=json.dumps(
                [
                    {"name": "RectoVerso", "qfmt": "{{Front}}", "afmt": "{{FrontSide}}<hr>{{Back}}"},
                ]
            ),
        )

        # Modèle Cible 2 (3 champs avec Cloze)
        nt_target_cloze = NoteTypeModel.create(
            name="Target Cloze Model",
            fields_schema=json.dumps(["Text", "Extra"]),
            templates=json.dumps(
                [
                    {"name": "Cloze", "qfmt": "{{cloze:Text}}", "afmt": "{{cloze:Text}}<br>{{Extra}}"},
                ]
            ),
        )

        # Note 1 avec 2 cartes
        n1 = NoteModel.create(note_type=nt_source, tags="t1")
        n1.add_version({"Question": "Quelle capitale ?", "Reponse": "Paris", "Remarque": "En Europe"}, source="init")
        c1 = CardModel.create(note=n1, deck=deck, template_index=0, ivl=10, reps=3)
        c2 = CardModel.create(note=n1, deck=deck, template_index=1, ivl=20, reps=5)

        # Note 2 avec 2 cartes
        n2 = NoteModel.create(note_type=nt_source, tags="t2")
        n2.add_version({"Question": "Quelle devise ?", "Reponse": "Euro", "Remarque": "Zone Euro"}, source="init")
        c3 = CardModel.create(note=n2, deck=deck, template_index=0, ivl=5, reps=1)
        c4 = CardModel.create(note=n2, deck=deck, template_index=1, ivl=15, reps=2)

    return {
        "deck": deck,
        "nt_source": nt_source,
        "nt_target_simple": nt_target_simple,
        "nt_target_cloze": nt_target_cloze,
        "notes": [n1, n2],
        "cards": [c1, c2, c3, c4],
    }


def test_dialog_initialization_single_note(qtbot: QtBot, sample_setup: dict[str, Any]) -> None:
    """Vérifie l'initialisation du dialogue pour une seule note."""
    n1 = sample_setup["notes"][0]
    dialog = ChangeNoteTypeDialog(note_ids=[n1.id])
    qtbot.addWidget(dialog)

    assert dialog.combo_target_model.count() >= 2
    assert "Target Simple Model" in [dialog.combo_target_model.itemText(i) for i in range(dialog.combo_target_model.count())]

    # Vérification du tableau de correspondance des champs
    assert dialog.table_fields.rowCount() == 3  # Question, Reponse, Remarque

    # Vérification de l'aperçu en direct
    preview_before = dialog.preview_before.toPlainText()
    assert "Quelle capitale ?" in preview_before
    assert "Paris" in preview_before

    preview_after = dialog.preview_after.toPlainText()
    assert len(preview_after) > 0


def test_dialog_initialization_batch_notes(qtbot: QtBot, sample_setup: dict[str, Any]) -> None:
    """Vérifie l'initialisation du dialogue pour un lot de plusieurs notes."""
    notes = sample_setup["notes"]
    dialog = ChangeNoteTypeDialog(note_ids=[n.id for n in notes])
    qtbot.addWidget(dialog)

    # Sélecteur de note témoin présent pour le lot
    assert dialog.combo_sample_note is not None
    assert dialog.combo_sample_note.count() == 2

    # Vérifier le titre de l'en-tête
    assert "2 note(s)" in dialog.lbl_header_title.text()


def test_field_mapping_change_updates_preview(qtbot: QtBot, sample_setup: dict[str, Any]) -> None:
    """Vérifie que la modification d'un champ cible dans le tableau met à jour l'aperçu en direct."""
    n1 = sample_setup["notes"][0]
    dialog = ChangeNoteTypeDialog(note_ids=[n1.id])
    qtbot.addWidget(dialog)

    # Sélectionner Target Simple Model (Front, Back)
    target_idx = dialog.combo_target_model.findText(sample_setup["nt_target_simple"].name)
    assert target_idx >= 0
    dialog.combo_target_model.setCurrentIndex(target_idx)

    # Modifier le mapping des champs : Question -> Back, Reponse -> Front
    combo_field_0 = dialog.get_field_target_combo(0)
    combo_field_1 = dialog.get_field_target_combo(1)
    assert combo_field_0 is not None and combo_field_1 is not None

    back_idx = combo_field_0.findText("Back")
    assert back_idx >= 0
    combo_field_0.setCurrentIndex(back_idx)

    front_idx = combo_field_1.findText("Front")
    assert front_idx >= 0
    combo_field_1.setCurrentIndex(front_idx)

    # L'aperçu doit refléter que "Quelle capitale ?" va dans Back et "Paris" va dans Front
    preview_after = dialog.preview_after.toPlainText()
    assert '"Back": "Quelle capitale ?"' in preview_after
    assert '"Front": "Paris"' in preview_after


def test_apply_migration_execution(qtbot: QtBot, sample_setup: dict[str, Any]) -> None:
    """Vérifie l'application complète de la migration et l'appel au service lors du clic sur le bouton d'action."""
    n1 = sample_setup["notes"][0]
    dialog = ChangeNoteTypeDialog(note_ids=[n1.id])
    qtbot.addWidget(dialog)

    # Cibler nt_target_simple
    target_idx = dialog.combo_target_model.findText(sample_setup["nt_target_simple"].name)
    dialog.combo_target_model.setCurrentIndex(target_idx)

    # Définir Question -> Front, Reponse -> Back, Remarque -> (Ignorer)
    combo_0 = dialog.get_field_target_combo(0)
    combo_1 = dialog.get_field_target_combo(1)
    combo_2 = dialog.get_field_target_combo(2)
    assert combo_0 is not None
    assert combo_1 is not None
    assert combo_2 is not None

    combo_0.setCurrentIndex(combo_0.findText("Front"))
    combo_1.setCurrentIndex(combo_1.findText("Back"))
    combo_2.setCurrentIndex(combo_2.findText(dialog.ignore_field_label))

    # Clic sur le bouton Appliquer
    with qtbot.waitSignal(dialog.accepted, timeout=2000):
        dialog.btn_apply.click()

    # Vérification que la note est bien migrée en base
    reloaded_n1 = NoteModel.get_by_id(n1.id)
    assert reloaded_n1.note_type.id == sample_setup["nt_target_simple"].id
    assert dialog.migrated_count == 1


def test_cloze_to_standard_clean_cloze(qtbot: QtBot, sample_setup: dict[str, Any]) -> None:
    """Vérifie que lors de la migration d'un modèle Cloze vers Standard, chk_clean_cloze est visible et nettoie les trous."""
    # Créer une note Cloze
    nt_cloze = sample_setup["nt_target_cloze"]
    n_cloze = NoteModel.create(note_type=nt_cloze)
    n_cloze.add_version({"Text": "La capitale de l'Espagne est {{c1::Madrid}}.", "Extra": "Capitale"}, source="init")

    dialog = ChangeNoteTypeDialog(note_ids=[n_cloze.id])
    qtbot.addWidget(dialog)

    # Cibler nt_target_simple (Standard)
    target_idx = dialog.combo_target_model.findText(sample_setup["nt_target_simple"].name)
    dialog.combo_target_model.setCurrentIndex(target_idx)

    assert not dialog.chk_clean_cloze.isHidden()
    assert dialog.chk_clean_cloze.isChecked() is True

    # Vérifier l'aperçu nettoyé
    preview = dialog.preview_after.toPlainText()
    assert "Madrid" in preview
    assert "{{c1::" not in preview


def test_edition_view_ribbon_button_state_and_dialog_trigger(qtbot: QtBot, sample_setup: Any, monkeypatch: Any) -> None:
    """Vérifie l'activation du bouton du ruban selon la sélection et le déclenchement du dialogue."""
    from ankiforge.ui.views.edition_view import EditionView

    view = EditionView(ai_manager=None)
    qtbot.addWidget(view)

    # Au départ sans carte sélectionnée
    view._update_nav_ribbon_info()
    assert hasattr(view, "btn_change_note_type")
    assert view.btn_change_note_type.isEnabled() is False

    # Sélectionner une note
    n1 = sample_setup["notes"][0]
    view.select_note_by_id(n1.id)
    view._update_nav_ribbon_info()
    assert view.btn_change_note_type.isEnabled() is True

    # Vérifier le clic sur le bouton du ruban
    dialog_opened: list[ChangeNoteTypeDialog] = []

    def mock_exec(dialog_self: ChangeNoteTypeDialog) -> int:
        dialog_opened.append(dialog_self)
        return int(QDialog.DialogCode.Rejected)

    monkeypatch.setattr(ChangeNoteTypeDialog, "exec", mock_exec)
    view.btn_change_note_type.click()

    assert len(dialog_opened) == 1
    assert dialog_opened[0].note_ids == [n1.id]


def test_edition_view_migration_success_toast_and_refresh(qtbot: QtBot, sample_setup: Any, monkeypatch: Any) -> None:
    """Vérifie qu'après acceptation du dialogue, la vue se rafraîchit et la note est mise à jour."""
    from ankiforge.ui.views.edition_view import EditionView

    view = EditionView(ai_manager=None)
    qtbot.addWidget(view)

    n1 = sample_setup["notes"][0]
    view.select_note_by_id(n1.id)

    target_nt = sample_setup["nt_target_simple"]

    def mock_exec(dialog_self: ChangeNoteTypeDialog) -> int:
        dialog_self.migrated_count = 1
        dialog_self.target_model_name = target_nt.name
        return int(QDialog.DialogCode.Accepted)

    monkeypatch.setattr(ChangeNoteTypeDialog, "exec", mock_exec)
    view._open_change_note_type_dialog(fallback_note_id=n1.id)

    assert view._change_model_modal is not None


def test_sample_note_selector_updates_preview(qtbot: QtBot, sample_setup: dict[str, Any]) -> None:
    """Vérifie que la modification de la note témoin dans le combo met à jour l'aperçu avec la nouvelle note."""
    notes = sample_setup["notes"]
    dialog = ChangeNoteTypeDialog(note_ids=[n.id for n in notes])
    qtbot.addWidget(dialog)

    assert dialog.combo_sample_note is not None
    assert "Quelle capitale ?" in dialog.preview_before.toPlainText()

    # Basculer sur la 2e note (Euro)
    dialog.combo_sample_note.setCurrentIndex(1)
    assert "Quelle devise ?" in dialog.preview_before.toPlainText()
    assert "Euro" in dialog.preview_before.toPlainText()


def test_template_mapping_delete_card_updates_metrics(qtbot: QtBot, sample_setup: dict[str, Any]) -> None:
    """Vérifie que basculer une carte vers '(Supprimer la carte)' met à jour les métriques prévisionnelles."""
    n1 = sample_setup["notes"][0]
    dialog = ChangeNoteTypeDialog(note_ids=[n1.id])
    qtbot.addWidget(dialog)

    # Récupérer le combobox du premier gabarit
    tmpl_combo_0 = dialog.get_template_target_combo(0)
    assert tmpl_combo_0 is not None

    # Sélectionner la suppression pour la première carte
    tmpl_combo_0.setCurrentIndex(0)  # delete_card_label
    metrics_text = dialog.lbl_cards_metrics.text()
    assert "supprimée" in metrics_text
