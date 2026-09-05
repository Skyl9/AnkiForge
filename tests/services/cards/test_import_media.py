import hashlib
import json
import sqlite3
import zipfile
from pathlib import Path

import zstandard as zstd

from ankiforge.database.models import MediaModel
from ankiforge.services.cards.import_manager import ImportManager


def _create_minimal_anki2(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE col (id integer, models text, decks text)")
    cursor.execute('INSERT INTO col VALUES (1, \'{"1": {"name": "Basic", "flds": [{"name": "Front"}, {"name": "Back"}]}}\', \'{"1": {"id": 1, "name": "Default"}}\')')
    cursor.execute("CREATE TABLE notes (id integer primary key, guid text, mid integer, tags text, flds text)")
    cursor.execute("INSERT INTO notes VALUES (1, 'guid_media_1', 1, '', 'Card with media\x1f<img src=\"image.png\">')")
    cursor.execute("CREATE TABLE cards (id integer primary key, nid integer, did integer, ord integer)")
    cursor.execute("INSERT INTO cards VALUES (1, 1, 1, 0)")
    conn.commit()
    conn.close()


def test_import_media_json_legacy(tmp_path: Path) -> None:
    """Vérifie l'extraction et la persistance de médias déclarés au format JSON legacy."""
    db_file = tmp_path / "legacy.db"
    _create_minimal_anki2(db_file)

    img_data = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRfake_png_data"
    snd_data = b"ID3\x03\x00\x00\x00fake_mp3_audio_data"

    img_hash = hashlib.sha256(img_data).hexdigest()

    apkg_path = tmp_path / "media_legacy.apkg"
    with zipfile.ZipFile(apkg_path, "w") as zf:
        zf.write(db_file, "collection.anki2")
        zf.writestr("media", json.dumps({"0": "image.png", "1": "sound.mp3"}))
        zf.writestr("0", img_data)
        zf.writestr("1", snd_data)

    manager = ImportManager()
    analysis = manager.analyze_archive(apkg_path)

    assert analysis.media_map == {"0": "image.png", "1": "sound.mp3"}

    summary = manager.commit_import(analysis)
    assert summary["created"] == 1
    assert summary["media"] == 2

    # Vérification MediaModel en BDD
    media_img = MediaModel.get_or_none(MediaModel.filename == "image.png")
    assert media_img is not None
    assert media_img.original_name == "image.png"
    assert media_img.checksum == img_hash
    assert "image" in media_img.mime_type

    # Vérification présence fichier sur disque
    dest_file = manager.media_dir / "image.png"
    assert dest_file.exists()
    assert dest_file.read_bytes() == img_data


def test_import_media_protobuf_modern(tmp_path: Path) -> None:
    """Vérifie le décodage Protobuf d'un fichier media moderne (MediaEntries)."""
    db_file = tmp_path / "legacy.db"
    _create_minimal_anki2(db_file)

    # Construction d'un flux Protobuf MediaEntries
    # MediaEntry 1: name="diagram.png" (index implicite 0)
    name1 = b"diagram.png"
    entry1 = bytes([0x0A, len(name1)]) + name1
    msg = bytes([0x0A, len(entry1)]) + entry1

    # MediaEntry 2: name="alert.wav", legacy_zip_filename=7
    # tag 255 (wire 0) -> 0x07f8 varint -> bytes [0xf8, 0x0f, 7]
    name2 = b"alert.wav"
    entry2 = bytes([0x0A, len(name2)]) + name2 + bytes([0xF8, 0x0F, 7])
    msg += bytes([0x0A, len(entry2)]) + entry2

    apkg_path = tmp_path / "media_pb.apkg"
    with zipfile.ZipFile(apkg_path, "w") as zf:
        zf.write(db_file, "collection.anki2")
        zf.writestr("media", msg)
        zf.writestr("0", b"fake_diagram_png")
        zf.writestr("7", b"fake_alert_wav")

    manager = ImportManager()
    analysis = manager.analyze_archive(apkg_path)

    assert analysis.media_map.get("0") == "diagram.png"
    assert analysis.media_map.get("7") == "alert.wav"

    summary = manager.commit_import(analysis)
    assert summary["media"] == 2

    media_diag = MediaModel.get_or_none(MediaModel.filename == "diagram.png")
    assert media_diag is not None
    assert media_diag.original_name == "diagram.png"


def test_import_media_protobuf_zstd_compressed(tmp_path: Path) -> None:
    """Vérifie la décompression Zstandard et le décodage Protobuf d'un fichier media compressé."""
    db_file = tmp_path / "legacy.db"
    _create_minimal_anki2(db_file)

    name_bytes = b"compressed_image.jpg"
    entry = bytes([0x0A, len(name_bytes)]) + name_bytes
    pb_msg = bytes([0x0A, len(entry)]) + entry

    zstd_media = zstd.compress(pb_msg)

    apkg_path = tmp_path / "media_zstd.apkg"
    with zipfile.ZipFile(apkg_path, "w") as zf:
        zf.write(db_file, "collection.anki2")
        zf.writestr("media", zstd_media)
        zf.writestr("0", b"fake_jpeg_content")

    manager = ImportManager()
    analysis = manager.analyze_archive(apkg_path)

    assert analysis.media_map == {"0": "compressed_image.jpg"}

    summary = manager.commit_import(analysis)
    assert summary["media"] == 1


def test_import_media_direct_filenames(tmp_path: Path) -> None:
    """Vérifie l'auto-détection de fichiers médias stockés sous leur vrai nom sans mapping media."""
    db_file = tmp_path / "legacy.db"
    _create_minimal_anki2(db_file)

    apkg_path = tmp_path / "media_direct.apkg"
    with zipfile.ZipFile(apkg_path, "w") as zf:
        zf.write(db_file, "collection.anki2")
        zf.writestr("photo.jpg", b"photo_bytes")

    manager = ImportManager()
    analysis = manager.analyze_archive(apkg_path)

    assert "photo.jpg" in analysis.media_map.values()

    summary = manager.commit_import(analysis)
    assert summary["media"] == 1
    assert MediaModel.get_or_none(MediaModel.filename == "photo.jpg") is not None


def test_import_media_graceful_on_missing_file_in_zip(tmp_path: Path) -> None:
    """Vérifie qu'un média déclaré mais manquant dans l'archive ne fait pas échouer l'importation."""
    db_file = tmp_path / "legacy.db"
    _create_minimal_anki2(db_file)

    apkg_path = tmp_path / "media_missing.apkg"
    with zipfile.ZipFile(apkg_path, "w") as zf:
        zf.write(db_file, "collection.anki2")
        zf.writestr("media", json.dumps({"0": "absent.png"}))
        # Aucun fichier '0' dans le zip

    manager = ImportManager()
    analysis = manager.analyze_archive(apkg_path)
    summary = manager.commit_import(analysis)

    assert summary["created"] == 1
    assert summary["media"] == 0


def test_import_media_zstd_no_content_size_in_frame(tmp_path: Path) -> None:
    """Vérifie la décompression Zstandard lorsque la taille non compressée est omise dans l'en-tête de frame."""
    db_file = tmp_path / "legacy.db"
    _create_minimal_anki2(db_file)

    name_bytes = b"no_size_image.jpg"
    entry = bytes([0x0A, len(name_bytes)]) + name_bytes
    pb_msg = bytes([0x0A, len(entry)]) + entry

    cctx = zstd.ZstdCompressor(write_content_size=False)
    zstd_media = cctx.compress(pb_msg)

    apkg_path = tmp_path / "media_zstd_no_size.apkg"
    with zipfile.ZipFile(apkg_path, "w") as zf:
        zf.write(db_file, "collection.anki2")
        zf.writestr("media", zstd_media)
        zf.writestr("0", b"fake_jpeg_content_no_size")

    manager = ImportManager()
    analysis = manager.analyze_archive(apkg_path)

    assert analysis.media_map == {"0": "no_size_image.jpg"}

    summary = manager.commit_import(analysis)
    assert summary["media"] == 1
    dest_file = manager.media_dir / "no_size_image.jpg"
    assert dest_file.exists()
    assert dest_file.read_bytes() == b"fake_jpeg_content_no_size"
