"""Tests unitaires et d'intégration pour la réconciliation des Types de Note (ADR 0037).

Vérifie :
1. La protection anti-corruption du schéma des notes locales existantes.
2. L'isomorphisme structurel pour éviter la prolifération de clones (Importé).
3. L'archivage non destructif des champs supprimés dans _orphaned_fields.
"""

import json

import pytest

from ankiforge.database.models import (
    DeckModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
)
from ankiforge.services.cards.import_manager import ImportAnalysisResult, ImportManager

pytestmark = pytest.mark.integration


def test_import_notetype_reconciliation_protects_existing_notes_schema(mock_db):
    """Vérifie la protection anti-écrasement du schéma local lors d'un import conflictuel.

    Un import .apkg avec un modèle homonyme aux champs divergents N'ÉCRASE PAS
    le fields_schema du modèle local utilisé par des notes existantes.
    """
    manager = ImportManager()
    DeckModel.create(name="Défaut", anki_id=1)

    # 1. Modèle local existant avec notes
    local_nt = NoteTypeModel.create(
        name="Basique",
        fields_schema=json.dumps(["Recto", "Verso"]),
        templates=json.dumps([{"name": "Carte 1", "qfmt": "{{Recto}}", "afmt": "{{Verso}}"}]),
        css_style="",
        anki_id=None,
    )
    note_locale = NoteModel.create(guid="guid_local_1", note_type=local_nt, status="valid")
    NoteVersionModel.create(
        note=note_locale,
        version_number=1,
        content=json.dumps({"Recto": "Capitale France", "Verso": "Paris"}),
        source="manual",
        is_active=True,
    )

    # 2. Archive entrante avec un modèle nommé 'Basique' mais aux champs différents ["Front", "Back", "Extra"]
    analysis = ImportAnalysisResult(
        temp_dir="",
        source_type="apkg",
        sqlite_path=None,
        txt_path=None,
        new_notes=[
            {
                "guid": "guid_entrant_2",
                "deck_name": "Défaut",
                "notetype_name": "Basique",
                "mid": 123456,
                "tags": [],
                "content": {"Front": "Question 2", "Back": "Réponse 2", "Extra": "Indice"},
                "field_names": ["Front", "Back", "Extra"],
                "cards": [{"ord": 0, "did": 1, "ivl": 0, "reps": 0, "lapses": 0}],
            }
        ],
        silent_updates=[],
        identical_count=0,
        conflicts=[],
        media_map={},
        raw_models={
            123456: {
                "name": "Basique",
                "fields": ["Front", "Back", "Extra"],
                "templates": [{"name": "Carte 1", "qfmt": "{{Front}}", "afmt": "{{Back}}<br>{{Extra}}"}],
                "css": "",
            }
        },
        raw_decks=[{"id": 1, "name": "Défaut"}],
    )

    result = manager.commit_import(analysis)
    assert result["created"] == 1

    # 3. Vérification de l'intégrité de la note locale
    local_nt_db = NoteTypeModel.get_by_id(local_nt.id)
    assert json.loads(local_nt_db.fields_schema) == ["Recto", "Verso"], "Le schéma du modèle local ne doit JAMAIS être écrasé par un modèle entrant aux champs différents !"

    note_locale_db = NoteModel.get_by_id(note_locale.id)
    active_v = NoteVersionModel.get_or_none(note=note_locale_db, is_active=True)
    assert active_v is not None
    data_locale = json.loads(active_v.content)
    assert data_locale == {"Recto": "Capitale France", "Verso": "Paris"}

    # 4. La note entrante a été affectée à un modèle propre sans corrompre le modèle local
    note_entrante = NoteModel.get(NoteModel.guid == "guid_entrant_2")
    assert note_entrante.note_type_id != local_nt.id
    assert "Basique (Importé)" in note_entrante.note_type.name


def test_import_notetype_structural_isomorphism_avoids_clones(mock_db):
    """Vérifie la non-prolifération des clones de modèles isomorphes.

    Un modèle entrant avec des champs identiques réutilise le modèle local
    sans créer de clone inutile 'Basique (Importé)'.
    """
    manager = ImportManager()
    DeckModel.create(name="Défaut", anki_id=1)

    local_nt = NoteTypeModel.create(
        name="Basique",
        fields_schema=json.dumps(["Recto", "Verso"]),
        templates=json.dumps([{"name": "Carte 1", "qfmt": "{{Recto}}", "afmt": "{{Verso}}"}]),
        css_style="",
        anki_id=None,
    )
    # Même avec une note déjà présente
    note_locale = NoteModel.create(guid="loc_1", note_type=local_nt)
    NoteVersionModel.create(note=note_locale, version_number=1, content=json.dumps({"Recto": "R1", "Verso": "V1"}), is_active=True)

    # Archive entrante avec modèle homonyme et champs identiques ["Recto", "Verso"], mid=7777
    analysis = ImportAnalysisResult(
        temp_dir="",
        source_type="apkg",
        sqlite_path=None,
        txt_path=None,
        new_notes=[
            {
                "guid": "entrant_1",
                "deck_name": "Défaut",
                "notetype_name": "Basique",
                "mid": 7777,
                "tags": [],
                "content": {"Recto": "R2", "Verso": "V2"},
                "field_names": ["Recto", "Verso"],
                "cards": [{"ord": 0, "did": 1, "ivl": 0, "reps": 0, "lapses": 0}],
            }
        ],
        silent_updates=[],
        identical_count=0,
        conflicts=[],
        media_map={},
        raw_models={
            7777: {
                "name": "Basique",
                "fields": ["Recto", "Verso"],
                "templates": [{"name": "Carte 1", "qfmt": "{{Recto}}", "afmt": "{{Verso}}"}],
                "css": "",
            }
        },
        raw_decks=[{"id": 1, "name": "Défaut"}],
    )

    manager.commit_import(analysis)

    # Vérification : pas de nouveau modèle créé, réutilisation de local_nt
    models = list(NoteTypeModel.select())
    assert len(models) == 1
    assert models[0].id == local_nt.id
    assert models[0].anki_id == 7777

    note_entrante = NoteModel.get(NoteModel.guid == "entrant_1")
    assert note_entrante.note_type_id == local_nt.id


def test_first_import_reuses_local_basic_model_with_notes(mock_db):
    """Un « Basique » local déjà utilisé est adopté, sans clone `(Importé)`.

    Profil non vierge : le modèle « Basique » (Recto/Verso) porte des notes locales
    et n'est pas encore relié à Anki. Un premier import nommé « Basic » (Front/Back)
    structurellement isomorphe réutilise ce modèle, lui attribue l'`anki_id` entrant
    et aligne le contenu des notes sur ses champs, sans dupliquer le modèle.
    """
    manager = ImportManager()
    DeckModel.create(name="Défaut", anki_id=1)

    local_nt = NoteTypeModel.create(
        name="Basique",
        fields_schema=json.dumps(["Recto", "Verso"]),
        templates=json.dumps([{"name": "Carte 1", "qfmt": "{{Recto}}", "afmt": "{{FrontSide}}<hr id=answer>{{Verso}}"}]),
        css_style="",
        anki_id=None,
    )
    note_locale = NoteModel.create(guid="loc_basic_1", note_type=local_nt)
    NoteVersionModel.create(
        note=note_locale,
        version_number=1,
        content=json.dumps({"Recto": "R1", "Verso": "V1"}),
        source="manual",
        is_active=True,
    )

    incoming_mid = 3_141_592
    analysis = ImportAnalysisResult(
        temp_dir="",
        source_type="apkg",
        sqlite_path=None,
        txt_path=None,
        new_notes=[
            {
                "guid": "entrant_basic_1",
                "deck_name": "Défaut",
                "notetype_name": "Basic",
                "mid": incoming_mid,
                "tags": [],
                "content": {"Front": "What is Python?", "Back": "A programming language"},
                "field_names": ["Front", "Back"],
                "cards": [{"ord": 0, "did": 1, "ivl": 0, "reps": 0, "lapses": 0}],
            }
        ],
        silent_updates=[],
        identical_count=0,
        conflicts=[],
        media_map={},
        raw_models={
            incoming_mid: {
                "name": "Basic",
                "fields": ["Front", "Back"],
                "templates": [{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{FrontSide}}<hr id=answer>{{Back}}"}],
                "css": "",
            }
        },
        raw_decks=[{"id": 1, "name": "Défaut"}],
    )

    manager.commit_import(analysis)

    models = list(NoteTypeModel.select())
    assert len(models) == 1, "Aucun clone « (Importé) » ne doit être créé pour un modèle isomorphe"
    assert models[0].id == local_nt.id
    assert models[0].name == "Basique", "Le nom du modèle local déjà utilisé ne doit pas être écrasé"
    assert models[0].anki_id == incoming_mid
    assert json.loads(models[0].fields_schema) == ["Recto", "Verso"]

    note_entrante = NoteModel.get(NoteModel.guid == "entrant_basic_1")
    assert note_entrante.note_type_id == local_nt.id
    active_v = NoteVersionModel.get_or_none(note=note_entrante, is_active=True)
    assert active_v is not None
    assert json.loads(active_v.content) == {"Recto": "What is Python?", "Verso": "A programming language"}


def test_import_notetype_orphaned_fields_archived(mock_db):
    """Vérifie l'archivage non destructif des champs supprimés dans Anki.

    Lorsqu'un modèle Anki (même anki_id) supprime un champ, les données locales
    des notes existantes sont archivées dans _orphaned_fields.
    """
    manager = ImportManager()
    DeckModel.create(name="Défaut", anki_id=1)

    local_nt = NoteTypeModel.create(
        name="Sciences",
        fields_schema=json.dumps(["Question", "Reponse", "Remarque"]),
        templates=json.dumps([{"name": "Carte 1", "qfmt": "{{Question}}", "afmt": "{{Reponse}} <br> {{Remarque}}"}]),
        css_style="",
        anki_id=8888,
    )
    note_locale = NoteModel.create(guid="note_sci_1", note_type=local_nt)
    NoteVersionModel.create(
        note=note_locale,
        version_number=1,
        content=json.dumps({"Question": "Quelle cellule ?", "Reponse": "Eucaryote", "Remarque": "Attention aux mitochondries"}),
        source="manual",
        is_active=True,
    )

    # Archive entrante avec anki_id=8888 mais où 'Remarque' a été supprimé dans Anki
    analysis = ImportAnalysisResult(
        temp_dir="",
        source_type="apkg",
        sqlite_path=None,
        txt_path=None,
        new_notes=[
            {
                "guid": "note_sci_2",
                "deck_name": "Défaut",
                "notetype_name": "Sciences",
                "mid": 8888,
                "tags": [],
                "content": {"Question": "Procaryote ?", "Reponse": "Bactérie"},
                "field_names": ["Question", "Reponse"],
                "cards": [{"ord": 0, "did": 1, "ivl": 0, "reps": 0, "lapses": 0}],
            }
        ],
        silent_updates=[],
        identical_count=0,
        conflicts=[],
        media_map={},
        raw_models={
            8888: {
                "name": "Sciences",
                "fields": ["Question", "Reponse"],
                "templates": [{"name": "Carte 1", "qfmt": "{{Question}}", "afmt": "{{Reponse}}"}],
                "css": "",
            }
        },
        raw_decks=[{"id": 1, "name": "Défaut"}],
    )

    manager.commit_import(analysis)

    # 1. Le modèle a bien son nouveau schéma à 2 champs
    local_nt_db = NoteTypeModel.get_by_id(local_nt.id)
    assert json.loads(local_nt_db.fields_schema) == ["Question", "Reponse"]

    # 2. La note locale existante a conservé sa remarque dans _orphaned_fields !
    note_locale_db = NoteModel.get_by_id(note_locale.id)
    active_v = NoteVersionModel.get_or_none(note=note_locale_db, is_active=True)
    assert active_v is not None
    data_locale = json.loads(active_v.content)
    assert data_locale.get("Question") == "Quelle cellule ?"
    assert data_locale.get("Reponse") == "Eucaryote"
    assert "_orphaned_fields" in data_locale
    assert data_locale["_orphaned_fields"].get("Remarque") == "Attention aux mitochondries"


def test_import_notetype_multilingual_isomorphism_maps_note_content(mock_db):
    """Vérifie le mapping du contenu de note lors d'un isomorphisme multilingue.

    L'isomorphisme multilingue (ex: ['Front', 'Back'] vers ['Recto', 'Verso'])
    réutilise le modèle local et mappe fidèlement le dictionnaire de contenu de la note.
    """
    manager = ImportManager()
    DeckModel.create(name="Défaut", anki_id=1)

    local_nt = NoteTypeModel.create(
        name="Basique",
        fields_schema=json.dumps(["Recto", "Verso"]),
        templates=json.dumps([{"name": "Carte 1", "qfmt": "{{Recto}}", "afmt": "{{Verso}}"}]),
        css_style="",
        anki_id=None,
    )
    # Note locale préexistante utilisant le schéma ['Recto', 'Verso']
    note_pre = NoteModel.create(guid="loc_pre_1", note_type=local_nt)
    NoteVersionModel.create(note=note_pre, version_number=1, content=json.dumps({"Recto": "Bonjour", "Verso": "Hello"}), is_active=True)

    analysis = ImportAnalysisResult(
        temp_dir="",
        source_type="apkg",
        sqlite_path=None,
        txt_path=None,
        new_notes=[
            {
                "guid": "guid_en_1",
                "deck_name": "Défaut",
                "notetype_name": "Basique",
                "mid": 9999,
                "tags": [],
                "content": {"Front": "What is Python?", "Back": "A programming language"},
                "field_names": ["Front", "Back"],
                "cards": [{"ord": 0, "did": 1, "ivl": 0, "reps": 0, "lapses": 0}],
            }
        ],
        silent_updates=[],
        identical_count=0,
        conflicts=[],
        media_map={},
        raw_models={
            9999: {
                "name": "Basique",
                "fields": ["Front", "Back"],
                "templates": [{"name": "Carte 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}],
                "css": "",
            }
        },
        raw_decks=[{"id": 1, "name": "Défaut"}],
    )

    manager.commit_import(analysis)

    # Réutilisation du modèle local
    models = list(NoteTypeModel.select())
    assert len(models) == 1
    assert models[0].id == local_nt.id

    # La note créée a son contenu aligné sur ['Recto', 'Verso']
    created_note = NoteModel.get(NoteModel.guid == "guid_en_1")
    v = NoteVersionModel.get_or_none(note=created_note, is_active=True)
    assert v is not None
    c = json.loads(v.content)
    assert c == {"Recto": "What is Python?", "Verso": "A programming language"}


def test_first_import_adopts_pristine_seed_basic_model(mock_db):
    """Un profil vierge adopte silencieusement l'identité du modèle « Basic » entrant.

    Le seed d'usine ne contient qu'un modèle « Basique » sans anki_id. Au premier
    import d'un paquet contenant « Basic », ce modèle vierge (0 note) adopte
    l'anki_id, le nom, les champs et les gabarits de la collection entrante :
    aucun clone `(Importé)` n'est créé (ADR 0037).
    """
    from ankiforge.database.seeds.initial_seed import seed_initial_data

    seed_initial_data()
    seed_basic = NoteTypeModel.get(NoteTypeModel.name == "Basique")
    assert seed_basic.anki_id is None

    manager = ImportManager()
    incoming_mid = 1_588_742_123_456
    analysis = ImportAnalysisResult(
        temp_dir="",
        source_type="apkg",
        sqlite_path=None,
        txt_path=None,
        new_notes=[
            {
                "guid": "guid_premier_import",
                "deck_name": "Default",
                "notetype_name": "Basic",
                "mid": incoming_mid,
                "tags": [],
                "content": {"Front": "What is the capital of France?", "Back": "Paris"},
                "field_names": ["Front", "Back"],
                "cards": [{"ord": 0, "did": 1, "ivl": 0, "reps": 0, "lapses": 0}],
            }
        ],
        silent_updates=[],
        identical_count=0,
        conflicts=[],
        media_map={},
        raw_models={
            incoming_mid: {
                "name": "Basic",
                "fields": ["Front", "Back"],
                "templates": [{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{FrontSide}}<hr id=answer>{{Back}}"}],
                "css": ".card { font-size: 20px; }",
            }
        },
        raw_decks=[{"id": 1, "name": "Default"}],
    )

    manager.commit_import(analysis)

    models = list(NoteTypeModel.select())
    assert len(models) == 1, "Aucun clone « (Importé) » ne doit apparaître au premier import"
    adopted = models[0]
    assert adopted.id == seed_basic.id
    assert adopted.name == "Basic"
    assert adopted.anki_id == incoming_mid
    assert json.loads(adopted.fields_schema) == ["Front", "Back"]
    assert json.loads(adopted.templates)[0]["qfmt"] == "{{Front}}"
    assert adopted.css_style == ".card { font-size: 20px; }"

    created_note = NoteModel.get(NoteModel.guid == "guid_premier_import")
    assert created_note.note_type_id == adopted.id
    active_v = NoteVersionModel.get_or_none(note=created_note, is_active=True)
    assert active_v is not None
    assert json.loads(active_v.content) == {"Front": "What is the capital of France?", "Back": "Paris"}
