from ankiforge.database.models import (
    DeckModel,
    DocumentChunkModel,
    DocumentModel,
    NoteChunkLinkModel,
    NoteModel,
    NoteTypeModel,
    db,
)

if db.is_closed():
    db.connect()

doc = DocumentModel.create(
    title="Introduction à la Physique Quantique",
    content=(
        "# Introduction à la Physique Quantique\n\n"
        "## Définition Fondamentale\n"
        "La physique quantique est la discipline de la physique dont l'objet est l'étude des comportements "
        "de la matière et de la lumière au niveau microscopique ou atomique.\n\n"
        "## Comparaison Classique\n"
        "Contrairement à la mécanique classique, les grandeurs observables ne peuvent prendre que des valeurs discrètes.\n\n"
        "## Concept Avancé\n"
        "De plus, on introduit la notion de dualité onde-corpuscule, selon laquelle une particule peut se comporter comme une onde."
    ),
    file_type="md",
)

chunk1 = DocumentChunkModel.create(
    document=doc,
    chunk_index=0,
    heading_path="Introduction > Définition Fondamentale",
    page_number=1,
    content="La physique quantique est la discipline de la physique dont l'objet est l'étude des comportements de la matière et de la lumière au niveau microscopique ou atomique.",
    content_hash="hash1",
)

chunk2 = DocumentChunkModel.create(
    document=doc,
    chunk_index=1,
    heading_path="Introduction > Comparaison Classique",
    page_number=2,
    content="Contrairement à la mécanique classique, les grandeurs observables ne peuvent prendre que des valeurs discrètes.",
    content_hash="hash2",
)

chunk3 = DocumentChunkModel.create(
    document=doc,
    chunk_index=2,
    heading_path="Introduction > Concept Avancé",
    page_number=3,
    content="De plus, on introduit la notion de dualité onde-corpuscule, selon laquelle une particule peut se comporter comme une onde.",
    content_hash="hash3",
)

deck = DeckModel.create(name="Physique")
nt = NoteTypeModel.select().first() or NoteTypeModel.create(name="Basic", fields_schema='["Front", "Back"]')

note1 = NoteModel.create(deck=deck, note_type=nt, fields_data='{"Front": "Qu\'est-ce que la physique quantique ?", "Back": "Étude microscopique."}')
NoteChunkLinkModel.create(note=note1, chunk=chunk1)

print("Mock document, chunks, and linked notes created successfully.")
