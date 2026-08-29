import csv
import json

from ankiforge.database.models import (
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
)
from ankiforge.services.cards.import_manager import ImportManager


def test_compute_field_diffs():
    local = {"Front": "Hello World", "Back": "Bonjour le monde"}
    incoming = {"Front": "Hello Universe", "Back": "Bonjour le monde"}

    diffs = ImportManager.compute_field_diffs(local, incoming)
    assert diffs["Front"]["is_different"] is True
    assert diffs["Back"]["is_different"] is False


def test_txt_import_and_conflict_detection(tmp_path):
    manager = ImportManager()

    # 1. Création d'une première note dans la base locale avec modification manuelle (source='manual')
    nt = NoteTypeModel.create(name="Basic", fields_schema='["Field_1", "Field_2"]', templates="[]", css_style="")
    note = NoteModel.create(guid="g123", note_type=nt, tags='["local"]')
    NoteVersionModel.create(
        note=note,
        version_number=1,
        content=json.dumps({"Field_1": "Question Locale", "Field_2": "Reponse Locale"}),
        source="manual",
        is_active=True,
    )

    # 2. Création d'un fichier texte TSV avec un contenu divergent pour le même GUID
    fake_txt = tmp_path / "import_test.txt"
    with open(fake_txt, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["#separator:tab"])
        writer.writerow(["#guid column:1"])
        writer.writerow(["#deck column:2"])
        writer.writerow(["#notetype column:3"])
        writer.writerow(["#tags column:4"])
        # Format: GUID, Deck, Notetype, Tags, Field_1, Field_2
        writer.writerow(["g123", "Langues::Anglais", "Basic", "entrant", "Question Entrante", "Reponse Entrante"])
        # Format: Nouvelle note
        writer.writerow(["g999", "Sciences", "Basic", "nouveau", "Biologie", "Cellule"])

    # 3. Analyse
    analysis = manager.analyze_archive(fake_txt)

    assert len(analysis.new_notes) == 1
    assert analysis.new_notes[0]["guid"] == "g999"

    # Vérification du conflit strict (Règle 11) car source='manual' et texte différent
    assert len(analysis.conflicts) == 1
    conflict = analysis.conflicts[0]
    assert conflict.guid == "g123"
    assert conflict.local_content["Field_1"] == "Question Locale"
    assert conflict.incoming_content["Field_1"] == "Question Entrante"

    # 4. Commit avec résolution
    resolutions = {
        "g123": {
            "choice": "merged",
            "content": {"Field_1": "Question Fusionnée", "Field_2": "Reponse Locale"},
            "deck": "Langues::Anglais",
            "tags": ["entrant", "local"],
        }
    }

    summary = manager.commit_import(analysis, conflict_resolutions=resolutions)
    assert summary["created"] == 1
    assert summary["merged"] == 1

    # Vérification base de données
    updated_note = NoteModel.get(NoteModel.guid == "g123")
    latest_version = NoteVersionModel.select().where(NoteVersionModel.note == updated_note).order_by(NoteVersionModel.version_number.desc()).first()
    assert latest_version.source == "merge"
    content_data = json.loads(latest_version.content)
    assert content_data["Field_1"] == "Question Fusionnée"


def test_silent_update_when_no_manual_edit(tmp_path):
    """Vérifie que si la note locale n'a jamais été éditée manuellement (source='import'), la mise à jour est silencieuse."""
    manager = ImportManager()

    nt = NoteTypeModel.create(name="Basic", fields_schema='["Field_1", "Field_2"]', templates="[]", css_style="")
    note = NoteModel.create(guid="g_auto", note_type=nt)
    NoteVersionModel.create(
        note=note,
        version_number=1,
        content=json.dumps({"Field_1": "Texte V1", "Field_2": "Reponse V1"}),
        source="import",
        is_active=True,
    )

    fake_txt = tmp_path / "silent_test.txt"
    with open(fake_txt, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["#guid column:1"])
        writer.writerow(["#deck column:2"])
        writer.writerow(["#notetype column:3"])
        writer.writerow(["#tags column:4"])
        writer.writerow(["g_auto", "Nouveau Deck", "Basic", "tag_sync", "Texte V2", "Reponse V2"])

    analysis = manager.analyze_archive(fake_txt)

    # Zéro conflit levé, mise à jour silencieuse
    assert len(analysis.conflicts) == 0
    assert len(analysis.silent_updates) == 1

    manager.commit_import(analysis)

    updated_note = NoteModel.get(NoteModel.guid == "g_auto")
    latest_v = NoteVersionModel.select().where(NoteVersionModel.note == updated_note).order_by(NoteVersionModel.version_number.desc()).first()
    assert latest_v.source == "import"
    assert "Texte V2" in latest_v.content
