import pytest
from unittest.mock import patch
from PySide6.QtCore import QMimeData, QUrl
from PySide6.QtGui import QImage

# Ajuste l'import selon ton architecture
from ankiforge.ui.widgets.drop_image_text_edit import DropImageTextEdit


@pytest.fixture
def mock_media_dir(tmp_path):
    """
    Détourne la fonction get_app_data_dir() pour qu'elle pointe
    vers un dossier temporaire géré par pytest (tmp_path).
    Cela évite de créer de fausses images dans les vrais dossiers de l'utilisateur !
    """
    with patch('ankiforge.ui.widgets.drop_image_text_edit.get_app_data_dir', return_value=tmp_path):
        yield tmp_path


@pytest.fixture
def editor(qtbot, mock_media_dir):
    """Initialise notre éditeur de texte."""
    widget = DropImageTextEdit()
    qtbot.addWidget(widget)
    return widget


# --- TESTS ---

def test_insert_normal_text(editor):
    """Vérifie que coller du texte normal fonctionne toujours (le Fallback)."""
    # On simule un presse-papier contenant juste du texte
    mime = QMimeData()
    mime.setText("Ceci est un texte normal.")

    # On déclenche l'événement
    editor.insertFromMimeData(mime)

    # On vérifie que le texte a bien été inséré
    assert editor.toPlainText() == "Ceci est un texte normal."


def test_insert_image_file_url(editor, tmp_path, mock_media_dir):
    """Simule le Glisser-Déposer d'un fichier image (ex: depuis le Finder/Explorateur)."""

    # 1. On crée un faux fichier image dans notre dossier temporaire
    source_img_path = tmp_path / "mon_image_source.png"
    source_img_path.write_text("fake_binary_content")  # Contenu factice

    # 2. On prépare l'enveloppe Drag&Drop contenant l'URL locale du fichier
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(source_img_path))])

    # 3. On déclenche le drop
    editor.insertFromMimeData(mime)

    # 4. Vérifications de l'UI
    inserted_text = editor.toPlainText()
    assert inserted_text.startswith('<img src="img_')
    assert inserted_text.endswith('.png">\n')

    # 5. Vérifications du Système de Fichiers (le fichier a-t-il été copié ?)
    # On navigue dans le sous-dossier "media" créé par ta fonction
    media_folder = mock_media_dir / "media"
    assert media_folder.exists()

    # On cherche tous les fichiers commençant par "img_"
    copied_files = list(media_folder.glob("img_*.png"))
    assert len(copied_files) == 1  # Un fichier a bien été copié !


def test_insert_raw_image_data(editor, mock_media_dir):
    """Simule le collage (Ctrl+V) d'une image brute depuis le presse-papier (ex: Capture d'écran)."""

    # 1. On dessine une vraie QImage en mémoire (un carré rouge de 10x10 pixels)
    image = QImage(10, 10, QImage.Format.Format_RGB32)
    image.fill(0xFF0000)

    # 2. On la place dans l'enveloppe du presse-papier
    mime = QMimeData()
    mime.setImageData(image)

    # 3. On déclenche le collage
    editor.insertFromMimeData(mime)

    # 4. Vérifications de l'UI
    inserted_text = editor.toPlainText()
    assert inserted_text.startswith('<img src="img_')
    assert inserted_text.endswith('.png">\n')

    # 5. Vérification du Système de Fichiers
    media_folder = mock_media_dir / "media"
    saved_files = list(media_folder.glob("img_*.png"))
    assert len(saved_files) == 1