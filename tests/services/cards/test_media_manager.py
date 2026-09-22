import hashlib
from unittest.mock import patch

import pytest

from ankiforge.services.cards.media_manager import MediaManager

pytestmark = pytest.mark.integration


@pytest.fixture
def media_manager(tmp_path):
    """Fixture qui isole le dossier de données et de médias de l'application."""
    media_dir = tmp_path / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    with (
        patch("ankiforge.services.cards.media_manager.get_app_data_dir", return_value=tmp_path),
        patch("ankiforge.services.cards.media_manager.get_media_dir", return_value=media_dir),
    ):
        yield MediaManager(media_dir=media_dir)


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


def test_clean_orphaned_media(media_manager, tmp_path):
    import json

    from ankiforge.database.models import NoteModel, NoteTypeModel, NoteVersionModel

    # 1. Création de fausses images sur le disque
    media_dir = tmp_path / "media"
    media_dir.mkdir(exist_ok=True)

    used_img = media_dir / "used.png"
    orphan_img = media_dir / "orphan.png"
    used_img.write_text("fake image")
    orphan_img.write_text("fake image")

    # 2. Création d'une note en base qui utilise UNIQUEMENT used.png
    nt = NoteTypeModel.create(name="Test", fields_schema='["Front"]', templates="[]", css_style="")
    note = NoteModel.create(guid="123", note_type=nt)
    NoteVersionModel.create(
        note=note,
        version_number=1,
        content=json.dumps({"Front": "Voici une image : <img src='used.png'>"}),
        is_active=True,
    )

    # 3. Exécution du Garbage Collector
    deleted = media_manager.clean_orphaned_media()

    # 4. Vérification
    assert deleted == 1
    assert used_img.exists() is True
    assert orphan_img.exists() is False


def test_clean_orphaned_media_preserves_sound_and_audio_tags(media_manager, tmp_path):
    """Vérifie que [sound:xxx], <audio src="xxx"> et <source src="xxx"> sont préservés."""
    import json

    from ankiforge.database.models import NoteModel, NoteTypeModel, NoteVersionModel

    media_dir = tmp_path / "media"
    media_dir.mkdir(exist_ok=True)

    snd_anki = media_dir / "tts_anki.mp3"
    snd_html = media_dir / "tts_html.wav"
    snd_source = media_dir / "tts_source.ogg"
    snd_orphan = media_dir / "tts_orphan.mp3"

    snd_anki.write_text("audio anki")
    snd_html.write_text("audio html")
    snd_source.write_text("audio source")
    snd_orphan.write_text("audio orphan")

    nt = NoteTypeModel.create(name="AudioDeck", fields_schema='["Front", "Back"]', templates="[]", css_style="")
    note = NoteModel.create(guid="audio_note_1", note_type=nt)
    content = {
        "Front": "Question [sound:tts_anki.mp3]",
        "Back": "Réponse <audio src='tts_html.wav'><source src='tts_source.ogg'></audio>",
    }
    NoteVersionModel.create(
        note=note,
        version_number=1,
        content=json.dumps(content),
        is_active=True,
    )

    deleted = media_manager.clean_orphaned_media()
    assert deleted == 1
    assert snd_anki.exists() is True
    assert snd_html.exists() is True
    assert snd_source.exists() is True
    assert snd_orphan.exists() is False


def test_purge_tts_audio_cache_all_and_orphans(media_manager, tmp_path):
    """Vérifie purge_tts_audio_cache selon only_orphans=True et only_orphans=False."""
    import json

    from ankiforge.database.models import NoteModel, NoteTypeModel, NoteVersionModel

    media_dir = tmp_path / "media"
    media_dir.mkdir(exist_ok=True)

    used_tts = media_dir / "tts_used.mp3"
    orphan_tts = media_dir / "tts_orphan.wav"
    normal_img = media_dir / "normal.png"

    used_tts.write_bytes(b"A" * 500)
    orphan_tts.write_bytes(b"B" * 800)
    normal_img.write_bytes(b"C" * 200)

    nt = NoteTypeModel.create(name="PurgeDeck", fields_schema='["Front"]', templates="[]", css_style="")
    note = NoteModel.create(guid="purge_note", note_type=nt)
    NoteVersionModel.create(
        note=note,
        version_number=1,
        content=json.dumps({"Front": "Phrase [sound:tts_used.mp3]"}),
        is_active=True,
    )

    # 1. Purge orphelins uniquement : tts_used doit être conservé
    del_count, freed = media_manager.purge_tts_audio_cache(only_orphans=True)
    assert del_count == 1
    assert freed == 800
    assert used_tts.exists() is True
    assert orphan_tts.exists() is False
    assert normal_img.exists() is True

    # 2. Purge totale : supprime même le tts_used mais préserve normal_img
    del_count2, freed2 = media_manager.purge_tts_audio_cache(only_orphans=False)
    assert del_count2 == 1
    assert freed2 == 500
    assert used_tts.exists() is False
    assert normal_img.exists() is True
