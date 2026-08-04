from ankiforge.database.models import db, PersonaModel
db.connect()
for p in PersonaModel.select():
    print(f"{p.id} - {p.name}")
