from ankiforge.database.models import db, DocumentModel, DocumentChunkModel, CognitiveFacetModel, ChunkFacetRequirementModel, FacetProfileModel

db.connect()

profile = FacetProfileModel.get_or_none(FacetProfileModel.name == "Profil Étudiant Universel")
if not profile:
    profile = FacetProfileModel.create(name="Profil Étudiant Universel", description="Mock")

doc = DocumentModel.create(
    title="Introduction à la Physique Quantique",
    content="La physique quantique est la discipline de la physique dont l'objet est l'étude des comportements de la matière et de la lumière au niveau microscopique ou atomique. Contrairement à la mécanique classique, les grandeurs observables ne peuvent prendre que des valeurs discrètes. De plus, on introduit la notion de dualité onde-corpuscule, selon laquelle une particule peut se comporter comme une onde.",  # noqa: E501
    file_type="md",
)

chunk1 = DocumentChunkModel.create(
    document=doc,
    chunk_index=0,
    content="La physique quantique est la discipline de la physique dont l'objet est l'étude des comportements de la matière et de la lumière au niveau microscopique ou atomique.",
    content_hash="hash1",
    is_profiled=True,
)

chunk2 = DocumentChunkModel.create(
    document=doc, chunk_index=1, content="Contrairement à la mécanique classique, les grandeurs observables ne peuvent prendre que des valeurs discrètes.", content_hash="hash2", is_profiled=True
)

chunk3 = DocumentChunkModel.create(
    document=doc,
    chunk_index=2,
    content="De plus, on introduit la notion de dualité onde-corpuscule, selon laquelle une particule peut se comporter comme une onde.",  # noqa: E501
    content_hash="hash3",
    is_profiled=True,
)

f1 = CognitiveFacetModel.create(name="Définition Fondamentale", description="Comprendre la base", weight=1.0, profile=profile)
f2 = CognitiveFacetModel.create(name="Comparaison Classique", description="Différences avec la physique classique", weight=1.5, profile=profile)
f3 = CognitiveFacetModel.create(name="Concept Avancé", description="Concepts poussés", weight=2.0, profile=profile)

ChunkFacetRequirementModel.create(chunk=chunk1, facet=f1)
ChunkFacetRequirementModel.create(chunk=chunk2, facet=f2)
ChunkFacetRequirementModel.create(chunk=chunk3, facet=f3)

print("Mock document and chunks created successfully.")
