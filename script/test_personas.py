from ankiforge.database.models import PersonaModel, db

db.connect()
for p in PersonaModel.select():
    print(f"{p.id} - {p.name}")
