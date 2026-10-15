from pathlib import Path

import ankiforge.database.models
from ankiforge.database.models import CardModel, NoteModel, NoteVersionModel, db

ankiforge.database.models.DEFAULT_DB_PATH = Path.home() / ".ankiforge" / "profiles" / "default" / "ankiforge.db"

try:
    db.connect(reuse_if_open=True)
    notes = NoteModel.select().order_by(NoteModel.id.desc()).limit(20)
    print(f"Notes in {ankiforge.database.models.DEFAULT_DB_PATH}:")
    for note in notes:
        cards = CardModel.select().where(CardModel.note == note)
        deck_names = set(c.deck.name for c in cards)
        active_ver = NoteVersionModel.get_or_none(NoteVersionModel.note == note, NoteVersionModel.is_active)
        content = active_ver.content if active_ver else "None"
        print(f"Note {note.id} in Decks: {deck_names} | Content: {content}")
except Exception as e:
    print(e)
