import peewee as pw


def migrate(migrator, database, fake=False, **kwargs):
    migrator.add_fields("documentmodel", chroma_collection_name=pw.CharField(null=True, max_length=255))
    migrator.remove_fields("documentmodel", "faiss_index_path")


def rollback(migrator, database, fake=False, **kwargs):
    migrator.add_fields("documentmodel", faiss_index_path=pw.CharField(null=True, max_length=255))
    migrator.remove_fields("documentmodel", "chroma_collection_name")
