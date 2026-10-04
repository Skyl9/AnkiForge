import json

import pytest

from ankiforge.database.base import db
from ankiforge.database.models import (
    DocumentModel,
    DocumentPageModel,
    MediaModel,
)

pytestmark = pytest.mark.integration


def test_document_page_crop_box_property():
    """Vérifie la propriété page.crop_box sur DocumentPageModel."""
    doc = DocumentModel.create(title="Doc Crop Model Test")
    media = MediaModel.create(
        filename="test_crop.png",
        original_name="test_crop.png",
        checksum="hash_crop_test",
        mime_type="image/png",
    )
    page = DocumentPageModel.create(
        document=doc,
        media=media,
        page_number=1,
        crop_data=json.dumps([10, 25, 200, 150]),
    )

    assert page.crop_box == (10, 25, 200, 150)

    # Sans recadrage
    page_uncropped = DocumentPageModel.create(
        document=doc,
        media=media,
        page_number=2,
        crop_data=None,
    )
    assert page_uncropped.crop_box is None

    # Donnée corrompue ou invalide
    page_corrupted = DocumentPageModel.create(
        document=doc,
        media=media,
        page_number=3,
        crop_data="not-json",
    )
    assert page_corrupted.crop_box is None


def test_migration_idempotence_and_self_healing_for_crop_and_bounding_box():
    """
    Vérifie l'idempotence des colonnes bounding_box (document_chunks) et crop_data (document_pages).
    La migration post-migration dans migration.py doit auto-guérir ces colonnes sans erreur si elles sont absentes.
    """
    from ankiforge.database.migration import run_migrations

    # run_migrations sur la base de test existante doit s'exécuter sans erreur
    run_migrations()

    # Vérification que les colonnes existent bien
    chunk_cols = [col.name for col in db.get_columns("document_chunks")]
    assert "bounding_box" in chunk_cols

    page_cols = [col.name for col in db.get_columns("document_pages")]
    assert "crop_data" in page_cols
