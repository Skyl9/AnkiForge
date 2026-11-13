"""Tests UI pytest-qt pour les dialogues de modèles de cartes.

ModelExportDialog, ModelImportDialog et StarterPackDialog.
"""

import json
from pathlib import Path

import pytest
from PySide6.QtWidgets import QFrame, QLabel, QScrollArea, QSplitter
from pytestqt.qtbot import QtBot

from ankidraft.database.models import (
    NoteTypeModel,
)
from ankidraft.ui.dialogs.model_export_dialog import ModelExportDialog
from ankidraft.ui.dialogs.model_import_dialog import ModelImportDialog
from ankidraft.ui.dialogs.starter_pack_dialog import StarterPackDialog
from ankidraft.ui.theme import DesignTokens

pytestmark = pytest.mark.ui


def test_model_export_dialog(qtbot: QtBot, tmp_path: Path):
    model = NoteTypeModel.create(
        name="Law Bar Exam",
        fields_schema=json.dumps(["Article", "Jurisprudence"]),
        templates=json.dumps([{"name": "Droit", "qfmt": "{{Article}}", "afmt": "{{Jurisprudence}}"}]),
        css_style=".law { color: #333; }",
    )

    dlg = ModelExportDialog(model=model)
    qtbot.addWidget(dlg)

    assert dlg.input_author.text() == "AnkiForge User"
    assert dlg.input_version.text() == "1.0.0"
    assert dlg.radio_bundle.isChecked()

    # Définir un chemin temporaire
    target_export = tmp_path / "law_exam.afmodel"
    dlg.dest_input.setText(str(target_export))

    # Déclencher l'export
    dlg._on_confirm_export()
    assert dlg.exported_file_path is not None
    assert dlg.exported_file_path.exists()


def test_model_import_dialog(qtbot: QtBot):
    model_data = {
        "name": "Physics Quantum",
        "fields_schema": ["Equation", "Constant", "Context"],
        "templates": [{"name": "Quantum 1", "qfmt": "{{Equation}}", "afmt": "{{Constant}}"}],
        "css_style": ".quantum { font-family: monospace; }",
        "metadata": {
            "author": "Einstein",
            "version": "1.0.0",
            "description": "Quantum mechanics basics",
            "tags": ["physics", "quantum"],
        },
        "demo_cards": [{"Equation": "E = mc^2", "Constant": "c = 3e8 m/s", "Context": "Special relativity"}],
    }

    dlg = ModelImportDialog(model_data=model_data)
    qtbot.addWidget(dlg)

    assert dlg.name_input.text() == "Physics Quantum"
    assert not dlg.collision_frame.isVisible()

    # Dimensions minimales et taille par défaut confortables
    assert dlg.minimumSize().width() == 980
    assert dlg.minimumSize().height() == 680
    assert dlg.size().width() == 1100
    assert dlg.size().height() == 750

    # Panneau gauche encapsulé dans une QScrollArea fluide
    ancestor = dlg.name_input
    while ancestor is not None and not isinstance(ancestor, QScrollArea):
        ancestor = ancestor.parentWidget()
    assert isinstance(ancestor, QScrollArea)
    assert ancestor.widgetResizable() is True
    assert ancestor.frameShape() == QFrame.Shape.NoFrame

    # Splitter non repliable avec répartition spacieuse (preview plus large que métadonnées)
    splitters = dlg.findChildren(QSplitter)
    assert len(splitters) == 1
    splitter = splitters[0]
    assert splitter.isCollapsible(0) is False
    assert splitter.isCollapsible(1) is False
    dlg.show()
    with qtbot.waitExposed(dlg):
        pass
    sizes = splitter.sizes()
    assert sizes[1] > sizes[0] > 0

    # Doublon de titre d'aperçu supprimé au profit de l'en-tête natif
    preview_titles = [w for w in dlg.findChildren(QLabel) if "APERÇU DU RENDU EN DIRECT" in w.text()]
    assert len(preview_titles) == 0

    # Typographie DesignTokens.FONT_MAIN injectée dans la feuille de style
    assert f'font-family: "{DesignTokens.FONT_MAIN}"' in dlg.styleSheet()

    # Confirmer l'importation
    dlg._on_confirm_import()
    assert dlg.imported_model is not None
    assert dlg.imported_model.name == "Physics Quantum"

    # Vérifier que le modèle est en BDD
    in_db = NoteTypeModel.get_or_none(NoteTypeModel.name == "Physics Quantum")
    assert in_db is not None


def test_starter_pack_dialog(qtbot: QtBot):
    dlg = StarterPackDialog()
    qtbot.addWidget(dlg)

    # Vérifier qu'on peut installer un pack
    pack_data = {
        "id": "medical_qcm",
        "name": "Médical & QCM Interactif Test",
        "category": "Médecine",
        "author": "AnkiForge",
        "version": "1.0.0",
        "fields_schema": ["Question", "Reponse"],
        "templates": [{"name": "QCM", "qfmt": "{{Question}}", "afmt": "{{Reponse}}"}],
        "css_style": "",
    }

    signal_received = []
    dlg.model_installed.connect(lambda model_id: signal_received.append(model_id))

    dlg._on_install_pack(pack_data)
    assert len(signal_received) == 1
    installed_model = NoteTypeModel.get_by_id(signal_received[0])
    assert installed_model.name == "Médical & QCM Interactif Test"


def test_starter_pack_dialog_installed_badge(qtbot: QtBot):
    """Un modèle déjà installé affiche un badge 'Déjà installé' au lieu du bouton Installer."""
    NoteTypeModel.create(
        name="Médical & QCM Interactif",
        fields_schema=json.dumps(["Question", "Reponse"]),
        templates=json.dumps([{"name": "QCM", "qfmt": "{{Question}}", "afmt": "{{Reponse}}"}]),
        css_style="",
    )

    dlg = StarterPackDialog()
    qtbot.addWidget(dlg)

    from ankidraft.ui.dialogs.starter_pack_dialog import StarterModelCardWidget

    cards = dlg.findChildren(StarterModelCardWidget)
    medical_card = next((c for c in cards if c.pack.get("name") == "Médical & QCM Interactif"), None)
    assert medical_card is not None
    assert medical_card.is_installed is True

    state_labels = [w for w in dlg.findChildren(QLabel) if "Déjà installé" in w.text()]
    assert len(state_labels) >= 1


def test_starter_pack_dialog_category_filter(qtbot: QtBot):
    """Le filtre par catégorie masque les cartes hors catégorie sélectionnée."""
    from ankidraft.ui.components.buttons import FilterChipButton
    from ankidraft.ui.dialogs.starter_pack_dialog import StarterModelCardWidget

    dlg = StarterPackDialog()
    qtbot.addWidget(dlg)

    cards = dlg.findChildren(StarterModelCardWidget)
    assert len(cards) == 5

    med_btn = next((b for b in dlg.findChildren(FilterChipButton) if b.text() == "Mémorisation"), None)
    assert med_btn is not None
    med_btn.click()

    visible = [c for c in cards if not c.isHidden()]
    assert len(visible) == 1
    assert visible[0].pack.get("category") == "Mémorisation"

    tous_btn = dlg._btn_tous
    assert not tous_btn.isChecked()
    tous_btn.click()
    assert tous_btn.isChecked()
    visible_all = [c for c in cards if not c.isHidden()]
    assert len(visible_all) == 5
