import sys
from pathlib import Path
import ankiforge.database.models
ankiforge.database.models.DEFAULT_DB_PATH = Path("/Users/tristanrigaud-humbert/.ankiforge/profiles/default/ankiforge.db")

from ankiforge.database.models import db, DeckModel, NoteModel, CardModel, NoteVersionModel
try:
    db.connect(reuse_if_open=True)
    notes = NoteModel.select().order_by(NoteModel.id.desc()).limit(20)
    print("Notes in ~/.ankiforge/profiles/default/ankiforge.db:")
    for note in notes:
        cards = CardModel.select().where(CardModel.note == note)
        deck_names = set(c.deck.name for c in cards)
        active_ver = NoteVersionModel.get_or_none(NoteVersionModel.note == note, NoteVersionModel.is_active == True)
        content = active_ver.content if active_ver else 'None'
        print(f"Note {note.id} in Decks: {deck_names} | Content: {content}")
except Exception as e:
    print(e)
