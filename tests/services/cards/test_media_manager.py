import hashlib
from unittest.mock import patch

import pytest

from ankiforge.services.cards.media_manager import MediaManager


@pytest.fixture
def media_manager(tmp_path):
    """Fixture qui isole le dossier de données de l'application."""
    with patch('ankiforge.services.cards.media_manager.get_app_data_dir') as mock_dir:
        mock_dir.return_value = tmp_path
        yield MediaManager()


def test_calculate_md5(media_manager, tmp_path):
    """Vérifie que la fonction de hachage renvoie bien un MD5 valide."""
    fake_img = tmp_path / "test.jpg"
    fake_img.write_bytes(b"faux contenu image")

    expected_hash = hashlib.md5(b"faux contenu image").hexdigest()
    assert media_manager._calculate_md5(str(fake_img)) == expected_hash


def test_process_extracted_folder_success(media_manager, tmp_path):
    """Vérifie la copie, le renommage de l'image et la modification du Markdown."""
    # 1. On crée un faux dossier source (comme s'il venait de Marker)
    source_dir = tmp_path / "source"
    source_dir.mkdir()

    fake_img = source_dir / "figure1.png"
    fake_img.write_bytes(b"image 1")

    # 2. Le faux Markdown généré par Marker
    raw_markdown = "Regardez cette image : ![Ma figure](figure1.png)"

    # 3. Exécution
    result = media_manager.process_extracted_folder(str(source_dir), raw_markdown)

    # 4. Vérifications
    expected_hash = hashlib.md5(b"image 1").hexdigest()
    expected_filename = f"{expected_hash}.png"

    # Vérifie que l'image a bien été copiée dans data/media
    assert (tmp_path / "media" / expected_filename).exists()

    # Vérifie que le Markdown a bien été converti en HTML Anki-friendly
    assert f'<img src="{expected_filename}">' in result
    assert "![Ma figure]" not in result


def test_process_extracted_folder_missing_dir(media_manager):
    """Vérifie que la fonction gère bien un dossier source inexistant."""
    raw_markdown = "Texte normal."
    result = media_manager.process_extracted_folder("dossier_fantome", raw_markdown)
    assert result == raw_markdown
