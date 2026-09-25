import uuid

import pytest

from ankiforge.database.models import FolderModel
from ankiforge.ui.views.documents_view.dialogs.folder_dialog import FolderCreateDialog

pytestmark = pytest.mark.ui


def test_folder_dialog_preselects_parent_folder(qtbot):
    """Vérifie que la modale pré-sélectionne le dossier parent passé en argument et calcule le chemin complet."""
    uid = uuid.uuid4().hex[:6]
    FolderModel.create(name=f"Fac_{uid}")
    l1 = FolderModel.create(name=f"Fac_{uid}::L1")

    dlg = FolderCreateDialog(parent_folder_id=l1.id)
    qtbot.addWidget(dlg)

    # Le combo doit être positionné sur L1
    assert dlg.combo_parent.currentData() == l1.id

    # Saisir un nom de sous-dossier
    dlg.input_name.setText("Maths")
    assert dlg.get_full_path() == f"Fac_{uid}::L1::Maths"
    assert f"Fac_{uid}::L1::Maths" in dlg.lbl_preview.text()


def test_folder_dialog_root_creation(qtbot):
    """Vérifie la création à la racine avec création automatique de plusieurs sous-niveaux '::'."""
    uid = uuid.uuid4().hex[:6]
    dlg = FolderCreateDialog(parent_folder_id=None)
    qtbot.addWidget(dlg)

    assert dlg.combo_parent.currentData() is None

    dlg.input_name.setText(f"Med_{uid}::PACES::Anatomie")
    assert dlg.get_full_path() == f"Med_{uid}::PACES::Anatomie"

    dlg._on_create()

    # Vérifier que tous les niveaux ont été créés
    assert FolderModel.get_or_none(FolderModel.name == f"Med_{uid}") is not None
    assert FolderModel.get_or_none(FolderModel.name == f"Med_{uid}::PACES") is not None
    leaf = FolderModel.get_or_none(FolderModel.name == f"Med_{uid}::PACES::Anatomie")
    assert leaf is not None
    assert dlg.get_created_folder().id == leaf.id


def test_folder_dialog_create_button_state_and_combo_change(qtbot):
    """Vérifie l'état actif du bouton de création et la mise à jour dynamique du chemin lors d'un changement de parent."""
    uid = uuid.uuid4().hex[:6]
    root_folder = FolderModel.create(name=f"Dossier_{uid}")

    dlg = FolderCreateDialog()
    qtbot.addWidget(dlg)

    # Initialement vide -> bouton désactivé
    assert not dlg.btn_create.isEnabled()

    # Saisie d'espaces -> bouton toujours désactivé
    dlg.input_name.setText("   ")
    assert not dlg.btn_create.isEnabled()

    # Saisie valide -> bouton activé
    dlg.input_name.setText("Sous-dossier")
    assert dlg.btn_create.isEnabled()
    assert dlg.get_full_path() == "Sous-dossier"

    # Changement du dossier parent via le combobox
    idx = dlg.combo_parent.findData(root_folder.id)
    assert idx != -1
    dlg.combo_parent.setCurrentIndex(idx)

    assert dlg.get_full_path() == f"Dossier_{uid}::Sous-dossier"
    assert f"Dossier_{uid}::Sous-dossier" in dlg.lbl_preview.text()
