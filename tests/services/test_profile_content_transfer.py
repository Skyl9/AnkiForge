import hashlib
from pathlib import Path

import pytest
from peewee import SqliteDatabase

from ankiforge.database.models import (
    DocumentModel,
    DocumentPageModel,
    FolderModel,
    LLMConfigModel,
    MediaModel,
    NoteTypeModel,
    PersonaFolderModel,
    PersonaModel,
    PersonaVersionModel,
    PipelineModel,
    PipelineStepModel,
)
from ankiforge.services.profile_content_transfer import ProfileContentTransfer

pytestmark = pytest.mark.integration


def _creer_profil_source(
    tmp_path: Path,
    nom: str,
    models: list[type],
    avec_media: bool = True,
) -> Path:
    """Crée un profil source isolé dans tmp_path avec ses tables initialisées."""
    profiles_dir = tmp_path / "profiles"
    source_dir = profiles_dir / nom
    source_dir.mkdir(parents=True)
    if avec_media:
        (source_dir / "media").mkdir()
    db_path = source_dir / "ankiforge.db"
    source_db = SqliteDatabase(str(db_path))
    with source_db.bind_ctx(models, bind_refs=False, bind_backrefs=False):
        source_db.connect()
        source_db.create_tables(models)
        source_db.close()
    return db_path


def test_import_persona_from_another_profile(mock_db, tmp_path: Path) -> None:
    profiles_dir = tmp_path / "profiles"
    source_dir = profiles_dir / "source"
    source_dir.mkdir(parents=True)
    source_db = SqliteDatabase(str(source_dir / "ankiforge.db"))
    models = [LLMConfigModel, PersonaFolderModel, PersonaModel, PersonaVersionModel, PipelineModel, PipelineStepModel]
    with source_db.bind_ctx(models, bind_refs=False, bind_backrefs=False):
        source_db.connect()
        source_db.create_tables(models)
        with source_db.atomic():
            folder = PersonaFolderModel.create(name="Formation")
            llm = LLMConfigModel.create(
                display_name="Source Engine",
                provider="ollama",
                model_id="llama3",
                api_key="must-not-be-copied",
            )
            persona = PersonaModel.create(
                name="Agent Source",
                description="Agent transféré",
                system_prompt="Crée des cartes.",
                output_format="json",
                persona_type="pipeline",
                folder=folder,
                allowed_tools='["query_peewee"]',
                llm_config=llm,
            )
            PersonaVersionModel.create(
                persona=persona,
                system_prompt=persona.system_prompt,
                description=persona.description,
                output_format=persona.output_format,
                persona_type=persona.persona_type,
                allowed_tools=persona.allowed_tools,
                llm_config=llm,
            )
    source_db.close()

    imported = ProfileContentTransfer.import_persona("source", "Agent Source", profiles_dir)

    assert imported.name == "Agent Source"
    assert imported.folder.name == "Formation"
    assert imported.llm_config.display_name == "Source Engine"
    assert imported.llm_config.api_key is None


def test_import_pipeline_imports_missing_personas_and_preserves_links(mock_db, tmp_path: Path) -> None:
    profiles_dir = tmp_path / "profiles"
    source_dir = profiles_dir / "source"
    source_dir.mkdir(parents=True)
    source_db = SqliteDatabase(str(source_dir / "ankiforge.db"))
    models = [LLMConfigModel, PersonaFolderModel, PersonaModel, PersonaVersionModel, PipelineModel, PipelineStepModel]
    with source_db.bind_ctx(models, bind_refs=False, bind_backrefs=False):
        source_db.connect()
        source_db.create_tables(models)
        with source_db.atomic():
            persona = PersonaModel.create(name="Pipeline Agent", system_prompt="Génère.")
            pipeline = PipelineModel.create(name="Pipeline Source", description="DAG transféré")
            first = PipelineStepModel.create(pipeline=pipeline, persona=persona, step_order=1, config_data='{"input_variable":"text_source"}')
            second = PipelineStepModel.create(pipeline=pipeline, step_order=2, step_type="HUMAN_VALIDATION")
            first.on_success_step = second
            first.save()
    source_db.close()

    imported = ProfileContentTransfer.import_pipeline("source", "Pipeline Source", profiles_dir)

    assert imported.name == "Pipeline Source"
    steps = list(PipelineStepModel.select().where(PipelineStepModel.pipeline == imported).order_by(PipelineStepModel.step_order))
    assert [step.persona.name if step.persona else None for step in steps] == ["Pipeline Agent", None]
    assert steps[0].on_success_step.id == steps[1].id


def _ecriture_cible(profiles_dir: Path, nom: str, models: list[type]) -> Path:
    cible_dir = profiles_dir / nom
    cible_dir.mkdir(parents=True)
    (cible_dir / "media").mkdir()
    db_path = cible_dir / "ankiforge.db"
    cible_db = SqliteDatabase(str(db_path))
    with cible_db.bind_ctx(models, bind_refs=False, bind_backrefs=False):
        cible_db.connect()
        cible_db.create_tables(models)
        cible_db.close()
    return db_path


def test_list_note_types_renvoie_modeles_ordonnes(mock_db, tmp_path: Path) -> None:
    profiles_dir = tmp_path / "profiles"
    _creer_profil_source(tmp_path, "source", [NoteTypeModel])
    source_db = SqliteDatabase(str(profiles_dir / "source" / "ankiforge.db"))
    with source_db.bind_ctx([NoteTypeModel], bind_refs=False, bind_backrefs=False):
        source_db.connect()
        NoteTypeModel.create(name="Zebre", description="Dernier", fields_schema='["A"]', templates="[]", css_style="")
        NoteTypeModel.create(name="Alpha", description="Premier", fields_schema='["Q", "R"]', templates="[]", css_style="body{}")
        source_db.close()

    resultats = ProfileContentTransfer.list_note_types("source", profiles_dir=profiles_dir)

    assert [r["name"] for r in resultats] == ["Alpha", "Zebre"]
    alpha = resultats[0]
    assert alpha["id"] is not None
    assert alpha["description"] == "Premier"
    assert alpha["fields_schema"] == '["Q", "R"]'
    assert alpha["templates_count"] == 0
    assert alpha["css_style"] == "body{}"


def test_list_albums_renvoie_albums_avec_compte_planches(mock_db, tmp_path: Path) -> None:
    profiles_dir = tmp_path / "profiles"
    _creer_profil_source(tmp_path, "source", [DocumentModel, DocumentPageModel, MediaModel])
    source_db = SqliteDatabase(str(profiles_dir / "source" / "ankiforge.db"))
    with source_db.bind_ctx([DocumentModel, DocumentPageModel, MediaModel], bind_refs=False, bind_backrefs=False):
        source_db.connect()
        album = DocumentModel.create(title="Anatomie", file_type="album", total_pages=3)
        media = MediaModel.create(filename="p1.png", original_name="p1.png", checksum="abc", mime_type="image/png")
        DocumentPageModel.create(document=album, media=media, page_number=1, rotation=90, crop_data="[0,0,10,10]", ocr_text="page une")
        DocumentPageModel.create(document=album, media=media, page_number=2, rotation=0, crop_data=None, ocr_text="page deux")
        DocumentModel.create(title="Cours md", file_type="md")
        source_db.close()

    resultats = ProfileContentTransfer.list_albums("source", profiles_dir=profiles_dir)

    assert len(resultats) == 1
    assert resultats[0]["id"] == album.id
    assert resultats[0]["title"] == "Anatomie"
    assert resultats[0]["total_pages"] == 2
    assert resultats[0]["created_at"] is not None


def test_import_note_type_cree_nouveau_modele(mock_db, tmp_path: Path) -> None:
    profiles_dir = tmp_path / "profiles"
    _creer_profil_source(tmp_path, "source", [NoteTypeModel])
    _ecriture_cible(profiles_dir, "cible", [NoteTypeModel])
    source_db = SqliteDatabase(str(profiles_dir / "source" / "ankiforge.db"))
    with source_db.bind_ctx([NoteTypeModel], bind_refs=False, bind_backrefs=False):
        source_db.connect()
        NoteTypeModel.create(
            name="Modèle Source",
            description="Rôle IA",
            fields_schema='["Recto", "Verso"]',
            templates='[{"name": "Carte 1", "qfmt": "{{Recto}}", "afmt": "{{Verso}}"}]',
            css_style=".card { color: red; }",
        )
        source_db.close()

    importe = ProfileContentTransfer.import_note_type("source", "Modèle Source", target_profile="cible", profiles_dir=profiles_dir)

    assert importe.name == "Modèle Source"
    assert importe.description == "Rôle IA"
    assert importe.fields_schema == '["Recto", "Verso"]'
    assert importe.css_style == ".card { color: red; }"

    cible_db = SqliteDatabase(str(profiles_dir / "cible" / "ankiforge.db"))
    with cible_db.bind_ctx([NoteTypeModel], bind_refs=False, bind_backrefs=False):
        cible_db.connect()
        assert cible_db.execute_sql("SELECT COUNT(*) FROM notetypemodel WHERE name = 'Modèle Source'").fetchone()[0] == 1
        cible_db.close()


def test_import_note_type_reutilise_existant_si_meme_schema(mock_db, tmp_path: Path) -> None:
    profiles_dir = tmp_path / "profiles"
    _creer_profil_source(tmp_path, "source", [NoteTypeModel])
    _ecriture_cible(profiles_dir, "cible", [NoteTypeModel])
    source_db = SqliteDatabase(str(profiles_dir / "source" / "ankiforge.db"))
    cible_db = SqliteDatabase(str(profiles_dir / "cible" / "ankiforge.db"))
    with source_db.bind_ctx([NoteTypeModel], bind_refs=False, bind_backrefs=False):
        source_db.connect()
        NoteTypeModel.create(name="Commun", description="Src", fields_schema='["A", "B"]', templates="[]", css_style="")
        source_db.close()
    with cible_db.bind_ctx([NoteTypeModel], bind_refs=False, bind_backrefs=False):
        cible_db.connect()
        existant = NoteTypeModel.create(name="Commun", description="Cible", fields_schema='["A", "B"]', templates="[]", css_style="")
        cible_db.close()

    importe = ProfileContentTransfer.import_note_type("source", "Commun", target_profile="cible", profiles_dir=profiles_dir)

    assert importe.id == existant.id
    assert cible_db.execute_sql("SELECT COUNT(*) FROM notetypemodel").fetchone()[0] == 1


def test_import_note_type_renomme_si_schema_differ(mock_db, tmp_path: Path) -> None:
    profiles_dir = tmp_path / "profiles"
    _creer_profil_source(tmp_path, "source", [NoteTypeModel])
    _ecriture_cible(profiles_dir, "cible", [NoteTypeModel])
    source_db = SqliteDatabase(str(profiles_dir / "source" / "ankiforge.db"))
    cible_db = SqliteDatabase(str(profiles_dir / "cible" / "ankiforge.db"))
    with source_db.bind_ctx([NoteTypeModel], bind_refs=False, bind_backrefs=False):
        source_db.connect()
        NoteTypeModel.create(name="Commun", description="Src", fields_schema='["A"]', templates="[]", css_style="")
        source_db.close()
    with cible_db.bind_ctx([NoteTypeModel], bind_refs=False, bind_backrefs=False):
        cible_db.connect()
        NoteTypeModel.create(name="Commun", description="Cible", fields_schema='["A", "B"]', templates="[]", css_style="")
        cible_db.close()

    importe = ProfileContentTransfer.import_note_type("source", "Commun", target_profile="cible", profiles_dir=profiles_dir)

    assert importe.name == "Commun (Importé source)"
    assert importe.fields_schema == '["A"]'


def test_import_note_type_introuvable_leve_erreur(mock_db, tmp_path: Path) -> None:
    profiles_dir = tmp_path / "profiles"
    _creer_profil_source(tmp_path, "source", [NoteTypeModel])
    _ecriture_cible(profiles_dir, "cible", [NoteTypeModel])

    with pytest.raises(ValueError, match="introuvable"):
        ProfileContentTransfer.import_note_type("source", "Inexistant", target_profile="cible", profiles_dir=profiles_dir)


def test_import_album_duplique_document_pages_et_medias(mock_db, tmp_path: Path) -> None:
    profiles_dir = tmp_path / "profiles"
    _creer_profil_source(tmp_path, "source", [DocumentModel, DocumentPageModel, MediaModel])
    _ecriture_cible(profiles_dir, "cible", [DocumentModel, DocumentPageModel, MediaModel, FolderModel])
    source_media_dir = profiles_dir / "source" / "media"
    (source_media_dir / "planche1.png").write_bytes(b"image-donnees-planche-1")

    source_db = SqliteDatabase(str(profiles_dir / "source" / "ankiforge.db"))
    with source_db.bind_ctx([DocumentModel, DocumentPageModel, MediaModel], bind_refs=False, bind_backrefs=False):
        source_db.connect()
        album = DocumentModel.create(title="Album Numérise", file_type="album", total_pages=2)
        media = MediaModel.create(
            filename="planche1.png",
            original_name="Planche 1.png",
            checksum=hashlib.md5(b"image-donnees-planche-1", usedforsecurity=False).hexdigest(),
            mime_type="image/png",
        )
        DocumentPageModel.create(
            document=album,
            media=media,
            page_number=1,
            rotation=90,
            crop_data="[10, 20, 30, 40]",
            ocr_text="Contenu page 1",
        )
        DocumentPageModel.create(
            document=album,
            media=media,
            page_number=2,
            rotation=0,
            crop_data=None,
            ocr_text="Contenu page 2",
        )
        source_db.close()

    importe = ProfileContentTransfer.import_album("source", "Album Numérise", target_profile="cible", profiles_dir=profiles_dir)

    assert importe.file_type == "album"
    assert importe.title == "Album Numérise"

    cible_db = SqliteDatabase(str(profiles_dir / "cible" / "ankiforge.db"))
    with cible_db.bind_ctx([DocumentModel, DocumentPageModel, MediaModel], bind_refs=False, bind_backrefs=False):
        cible_db.connect()
        pages = list(DocumentPageModel.select().where(DocumentPageModel.document == importe).order_by(DocumentPageModel.page_number))
        assert len(pages) == 2
        assert pages[0].page_number == 1
        assert pages[0].rotation == 90
        assert pages[0].crop_data == "[10, 20, 30, 40]"
        assert pages[0].ocr_text == "Contenu page 1"
        assert pages[1].page_number == 2
        assert pages[1].rotation == 0

        cible_media_dir = profiles_dir / "cible" / "media"
        assert (cible_media_dir / "planche1.png").is_file()
        medias = list(MediaModel.select().where(MediaModel.checksum == media.checksum))
        assert len(medias) == 1
        cible_db.close()


def test_import_album_deduplication_par_md5(mock_db, tmp_path: Path) -> None:
    profiles_dir = tmp_path / "profiles"
    _creer_profil_source(tmp_path, "source", [DocumentModel, DocumentPageModel, MediaModel])
    _ecriture_cible(profiles_dir, "cible", [DocumentModel, DocumentPageModel, MediaModel, FolderModel])
    source_media_dir = profiles_dir / "source" / "media"
    contenu = b"image-partagee"
    checksum = hashlib.md5(contenu, usedforsecurity=False).hexdigest()
    (source_media_dir / "shared.png").write_bytes(contenu)

    source_db = SqliteDatabase(str(profiles_dir / "source" / "ankiforge.db"))
    with source_db.bind_ctx([DocumentModel, DocumentPageModel, MediaModel], bind_refs=False, bind_backrefs=False):
        source_db.connect()
        media = MediaModel.create(filename="shared.png", original_name="Shared.png", checksum=checksum, mime_type="image/png")
        album = DocumentModel.create(title="Album A", file_type="album", total_pages=1)
        DocumentPageModel.create(document=album, media=media, page_number=1, rotation=0, crop_data=None, ocr_text="p1")
        source_db.close()

    premier = ProfileContentTransfer.import_album("source", "Album A", target_profile="cible", profiles_dir=profiles_dir)
    deuxieme = ProfileContentTransfer.import_album("source", "Album A", target_profile="cible", profiles_dir=profiles_dir)

    assert premier.title != deuxieme.title
    cible_db = SqliteDatabase(str(profiles_dir / "cible" / "ankiforge.db"))
    with cible_db.bind_ctx([DocumentModel, DocumentPageModel, MediaModel], bind_refs=False, bind_backrefs=False):
        cible_db.connect()
        assert cible_db.execute_sql("SELECT COUNT(*) FROM mediamodel WHERE checksum = ?", (checksum,)).fetchone()[0] == 1
        cible_db.close()


def test_import_album_introuvable_leve_erreur(mock_db, tmp_path: Path) -> None:
    profiles_dir = tmp_path / "profiles"
    _creer_profil_source(tmp_path, "source", [DocumentModel, DocumentPageModel, MediaModel])
    _ecriture_cible(profiles_dir, "cible", [DocumentModel, DocumentPageModel, MediaModel, FolderModel])

    with pytest.raises(ValueError, match="introuvable"):
        ProfileContentTransfer.import_album("source", "Inexistant", target_profile="cible", profiles_dir=profiles_dir)
