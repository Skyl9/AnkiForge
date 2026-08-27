import csv

from ankiforge.database.models import DeckModel, NoteModel, NoteTypeModel
from ankiforge.services.cards.import_manager import ImportManager
from ankiforge.services.cards.store_manager import StoreManager


def test_extract_pb_string():
    """Test du mini-décodeur Protobuf dans ImportManager."""
    fake_pb_data = b"\x0a\x05Hello"
    result = ImportManager.extract_pb_string(fake_pb_data, target_field=1)
    assert result == "Hello"


def test_store_manager_handle_txt_delegation(tmp_path):
    """Vérifie la délégation correcte de StoreManager vers ImportManager."""
    store = StoreManager()

    fake_txt = tmp_path / "test_store.txt"
    with open(fake_txt, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["#separator:tab"])
        writer.writerow(["#html:true"])
        writer.writerow(["#tags column:5"])
        writer.writerow(["#notetype column:1"])
        writer.writerow(["#deck column:4"])
        writer.writerow(["Basique", "Chat", "Cat", "Langues::Anglais", "Vocabulaire"])

    store.handle_txt(fake_txt)

    assert DeckModel.select().count() == 2
    assert NoteTypeModel.select().count() == 1
    assert NoteModel.select().count() == 1

    note = NoteModel.get()
    assert note.note_type.name == "Basique"
    assert "Cat" in note.versions.first().content


def test_store_manager_approve_and_delete():
    """Test des opérations de curation de notes."""
    store = StoreManager()

    nt = NoteTypeModel.create(name="Basic", fields_schema='["Field_1"]', templates="[]", css_style="")
    n1 = NoteModel.create(guid="n1", note_type=nt, status="imported")
    n2 = NoteModel.create(guid="n2", note_type=nt, status="imported")

    store.approve_notes([n1.id, n2.id])
    assert NoteModel.get_by_id(n1.id).status == "new"
    assert NoteModel.get_by_id(n2.id).status == "new"

    store.delete_notes([n1.id])
    assert NoteModel.get_or_none(NoteModel.id == n1.id) is None
    assert NoteModel.get_or_none(NoteModel.id == n2.id) is not None
