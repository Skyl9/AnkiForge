from playhouse.migrate import SqliteMigrator, migrate
from peewee import SqliteDatabase, DateTimeField, SQL
from ankiforge.utils.paths import get_app_data_dir

db = SqliteDatabase(get_app_data_dir() / "ankiforge.db")
migrator = SqliteMigrator(db)

# Ajout de la colonne output_format
output_format_field = DateTimeField(constraints=[SQL("DEFAULT CURRENT_TIMESTAMP")])
migrate(migrator.add_column("agents", "created_at", output_format_field))
print("Migration réussie !")
