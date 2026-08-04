import json
from pathlib import Path
from ankiforge.database.models import db, NoteVersionModel

db_path = "/Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/.ankiforge/ankiforge.db"
db.init(db_path)
db.connect(reuse_if_open=True)

fixed_count = 0
for nv in NoteVersionModel.select():
    try:
        content = json.loads(nv.content)
        note = nv.note
        nt = note.note_type
        schema_str = nt.fields_schema
        schema = json.loads(schema_str) if schema_str else []
        needs_fix = False
        new_content = content.copy()
        
        # Keep original mapping fallback just in case
        if "Front" in content and "Front" not in schema and len(schema) >= 1:
            new_content[schema[0]] = new_content.pop("Front")
            needs_fix = True
        if "Back" in content and "Back" not in schema and len(schema) >= 2:
            new_content[schema[1]] = new_content.pop("Back")
            needs_fix = True
            
        if needs_fix:
            nv.content = json.dumps(new_content, ensure_ascii=False)
            nv.save()
            fixed_count += 1
    except Exception as e:
        print(f"Error on NV {nv.id}: {e}")

print(f"Fixed {fixed_count}")
