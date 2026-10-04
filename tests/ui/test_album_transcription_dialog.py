"""
Tests UI pour le dialogue dédié AlbumTranscriptionDialog.
"""

import pytest
from PySide6.QtCore import Qt

from ankiforge.database.models import DocumentModel, DocumentPageModel, MediaModel
from ankiforge.services.ai.album_transcription_types import AlbumTranscriptionOptions
from ankiforge.ui.dialogs.album_transcription_dialog import AlbumTranscriptionDialog

pytestmark = pytest.mark.ui


@pytest.fixture
def album_with_mixed_pages(mock_db, tmp_path):
    """Crée un album avec 4 planches : 1 prête avec OCR, 1 sans OCR, 2 avec status 'stale'."""
    doc = DocumentModel.create(title="Album Test Dialog", original_path=str(tmp_path / "album"))
    media = MediaModel.create(
        filename="test.png",
        original_name="test.png",
        checksum="hash123",
        mime_type="image/png",
        file_size=100,
    )
    pages = []
    # Planche 1 : prête avec OCR
    pages.append(DocumentPageModel.create(document=doc, media=media, page_number=1, ocr_text="Texte existant", status="ready"))
    # Planche 2 : sans OCR
    pages.append(DocumentPageModel.create(document=doc, media=media, page_number=2, ocr_text="", status="ready"))
    # Planche 3 : périmée (stale)
    pages.append(DocumentPageModel.create(document=doc, media=media, page_number=3, ocr_text="Ancien texte", status="stale"))
    # Planche 4 : périmée (stale)
    pages.append(DocumentPageModel.create(document=doc, media=media, page_number=4, ocr_text="", status="stale"))
    return doc, pages


def test_dialog_scope_defaults_to_stale_when_present(qtbot, mock_db, album_with_mixed_pages):
    doc, pages = album_with_mixed_pages
    dialog = AlbumTranscriptionDialog(doc)
    qtbot.addWidget(dialog)

    # 4 planches au total : 1 prête, 1 sans OCR, 2 stale
    assert dialog.lbl_count_all.text() == "(4)"
    assert dialog.lbl_count_untranscribed.text() == "(2)"
    assert dialog.lbl_count_stale.text() == "(2)"

    # Des planches stale existent, le mode stale doit être pré-sélectionné
    assert dialog.rb_stale.isChecked()
    assert dialog.btn_start.isEnabled()

    opts = dialog.get_options()
    assert opts.scope_mode == "stale"
    assert set(opts.target_page_ids) == {pages[2].id, pages[3].id}


def test_dialog_custom_range_updates_and_validates(qtbot, mock_db, album_with_mixed_pages):
    doc, pages = album_with_mixed_pages
    dialog = AlbumTranscriptionDialog(doc)
    qtbot.addWidget(dialog)

    dialog.rb_custom.setChecked(True)
    assert dialog.le_custom_range.isEnabled()

    # Saisie intervalle "1, 3"
    dialog.le_custom_range.setText("1, 3")
    assert dialog.lbl_count_custom.text() == "(2)"
    opts = dialog.get_options()
    assert set(opts.target_page_ids) == {pages[0].id, pages[2].id}

    # Saisie intervalle hors borne (ex: "99") -> 0 planche -> bouton désactivé
    dialog.le_custom_range.setText("99")
    assert dialog.lbl_count_custom.text() == "(0)"
    assert dialog.btn_start.isEnabled() is False


def test_dialog_hardware_category_greys_out_directives(qtbot, mock_db, album_with_mixed_pages):
    doc, pages = album_with_mixed_pages
    dialog = AlbumTranscriptionDialog(doc)
    qtbot.addWidget(dialog)
    dialog.show()

    # Sélection de la catégorie Apple Vision (id="hardware")
    idx = dialog.combo_category.findData("hardware")
    assert idx >= 0
    dialog.combo_category.setCurrentIndex(idx)

    # Le groupe des directives doit être désactivé et le bandeau explicatif visible
    assert dialog.directives_group.isEnabled() is False
    assert dialog.hardware_notice.isVisible() is True

    # Revenir sur "structured" réactive les directives
    idx_struct = dialog.combo_category.findData("structured")
    assert idx_struct >= 0
    dialog.combo_category.setCurrentIndex(idx_struct)
    assert dialog.directives_group.isEnabled() is True
    assert dialog.hardware_notice.isVisible() is False


def test_dialog_accept_emits_transcription_requested(qtbot, mock_db, album_with_mixed_pages):
    doc, pages = album_with_mixed_pages
    dialog = AlbumTranscriptionDialog(doc)
    qtbot.addWidget(dialog)

    received_options = []
    dialog.transcription_requested.connect(received_options.append)

    dialog.rb_all.setChecked(True)
    dialog.cb_figures.setChecked(True)
    dialog.txt_custom_instructions.setText("Langue allemande")

    qtbot.mouseClick(dialog.btn_start, Qt.MouseButton.LeftButton)

    assert len(received_options) == 1
    opts: AlbumTranscriptionOptions = received_options[0]
    assert opts.scope_mode == "all"
    assert len(opts.target_page_ids) == 4
    assert opts.include_figures is True
    assert opts.custom_instructions == "Langue allemande"


def test_dialog_cards_layout_and_scoped_styling(qtbot, mock_db, album_with_mixed_pages):
    """Vérifie que les cartes sont correctement remplies (non vides) et ont des sélecteurs scopés."""
    from PySide6.QtWidgets import QFrame

    doc, pages = album_with_mixed_pages
    dialog = AlbumTranscriptionDialog(doc)
    qtbot.addWidget(dialog)

    # Récupération des cartes par leur objectName scopé
    scope_card = dialog.findChild(QFrame, "scopeCard")
    engine_card = dialog.findChild(QFrame, "engineCard")
    directives_card = dialog.findChild(QFrame, "directivesCard")

    assert scope_card is not None
    assert engine_card is not None
    assert directives_card is not None

    # Chaque carte doit avoir un layout non vide (header + contenu)
    assert scope_card.layout() is not None
    assert scope_card.layout().count() >= 5  # header + row_all + row_untrans + row_stale + row_custom + input

    assert engine_card.layout() is not None
    assert engine_card.layout().count() >= 4  # header + combo_row + desc + hardware_notice + advanced_drawer

    assert directives_card.layout() is not None
    assert directives_card.layout().count() >= 6  # header + 4 checkboxes + custom_instructions label + text

    # Les conteneurs internes ont un objectName pour éviter l'héritage de bordure
    assert dialog.hardware_notice.objectName() == "hardwareNotice"
    assert dialog.advanced_drawer.objectName() == "advancedDrawer"


def test_dialog_two_distinct_axes_and_closed_types(qtbot, mock_db, album_with_mixed_pages):
    """Vérifie l'exposition de deux axes distincts et la liste fermée des 6 types de données."""
    from PySide6.QtWidgets import QFrame

    doc, pages = album_with_mixed_pages
    dialog = AlbumTranscriptionDialog(doc)
    qtbot.addWidget(dialog)

    # 1. Deux cartes distinctes
    data_type_card = dialog.findChild(QFrame, "dataTypeCard")
    engine_card = dialog.findChild(QFrame, "engineCard")
    assert data_type_card is not None
    assert engine_card is not None

    # 2. Liste fermée des 6 types
    assert dialog.combo_data_type.count() == 6
    types_in_combo = [dialog.combo_data_type.itemData(i) for i in range(6)]
    assert types_in_combo == ["table", "pseudocode", "schema", "photo", "logo", "texte_imprime"]


def test_dialog_data_type_bounds_engine_candidates(qtbot, mock_db, album_with_mixed_pages):
    """Vérifie que le type de donnée borne l'ensemble des candidats moteur (critère 3)."""
    doc, pages = album_with_mixed_pages
    dialog = AlbumTranscriptionDialog(doc)
    qtbot.addWidget(dialog)
    dialog.show()

    # Sélectionner "table" : l'OCR matériel ne doit pas figurer parmi les candidats
    idx_table = dialog.combo_data_type.findData("table")
    assert idx_table >= 0
    dialog.combo_data_type.setCurrentIndex(idx_table)

    assert dialog.combo_category.findData("hardware") == -1
    assert dialog.combo_category.findData("structured") >= 0

    # Sélectionner "texte_imprime" : l'OCR matériel réapparaît
    idx_text = dialog.combo_data_type.findData("texte_imprime")
    assert idx_text >= 0
    dialog.combo_data_type.setCurrentIndex(idx_text)

    assert dialog.combo_category.findData("hardware") >= 0


def test_dialog_auto_switch_away_from_incompatible_hardware(qtbot, mock_db, album_with_mixed_pages):
    """Si l'OCR matériel est sélectionné et que l'utilisateur bascule sur un type non-texte, bascule auto."""
    doc, pages = album_with_mixed_pages
    dialog = AlbumTranscriptionDialog(doc)
    qtbot.addWidget(dialog)
    dialog.show()

    # D'abord sur texte imprimé, sélection de hardware
    idx_text = dialog.combo_data_type.findData("texte_imprime")
    dialog.combo_data_type.setCurrentIndex(idx_text)
    idx_hw = dialog.combo_category.findData("hardware")
    assert idx_hw >= 0
    dialog.combo_category.setCurrentIndex(idx_hw)
    assert dialog.combo_category.currentData() == "hardware"

    # Bascule sur schéma : hardware doit être exclu et le moteur remplacé par un VLM compatible
    idx_schema = dialog.combo_data_type.findData("schema")
    dialog.combo_data_type.setCurrentIndex(idx_schema)

    assert dialog.combo_category.currentData() != "hardware"
    assert dialog.combo_category.findData("hardware") == -1


def test_dialog_token_budget_follows_model_never_type(qtbot, mock_db, album_with_mixed_pages):
    """Le budget de réflexion suit le moteur (Claude -> 2048, Gemini -> 0), jamais le type (critère 4)."""
    doc, pages = album_with_mixed_pages
    dialog = AlbumTranscriptionDialog(doc)
    qtbot.addWidget(dialog)
    dialog.show()

    idx_reasoning = dialog.combo_category.findData("reasoning")
    assert idx_reasoning >= 0
    dialog.combo_category.setCurrentIndex(idx_reasoning)
    assert dialog.spin_thinking.value() == 2048

    # Changer de type de donnée ne doit JAMAIS altérer le budget de tokens du modèle
    for type_id in ["table", "pseudocode", "schema", "photo", "logo", "texte_imprime"]:
        idx = dialog.combo_data_type.findData(type_id)
        if idx >= 0:
            dialog.combo_data_type.setCurrentIndex(idx)
            assert dialog.spin_thinking.value() == 2048


def test_dialog_options_contain_both_axes_and_persist(qtbot, mock_db, album_with_mixed_pages):
    """Vérifie que get_options() renvoie les deux axes et que _on_start_clicked persiste la préférence."""
    from ankiforge.services.settings_service import SettingsService

    doc, pages = album_with_mixed_pages
    dialog = AlbumTranscriptionDialog(doc)
    qtbot.addWidget(dialog)

    idx_code = dialog.combo_data_type.findData("pseudocode")
    dialog.combo_data_type.setCurrentIndex(idx_code)

    opts = dialog.get_options()
    assert opts.data_type == "pseudocode"
    assert opts.category_id != ""

    # Démarrage
    dialog._on_start_clicked()
    assert SettingsService.get("ai/last_image_data_type") == "pseudocode"
