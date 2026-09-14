"""Script de capture des DialogDelimitation et DocumentScope en headless pour analyse UI."""

import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QTWEBENGINE_DISABLE_SANDBOX"] = "1"
os.environ["ANKIFORGE_MOCK_WEBENGINE"] = "1"
os.environ["ANKIFORGE_ENV"] = "testing"

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

# Setup in-memory DB (same as conftest.py)
from peewee import SqliteDatabase  # noqa: E402

from ankiforge.database.base import db  # noqa: E402
from ankiforge.database.models import (  # noqa: E402
    AICacheModel,
    AuditRecordModel,
    CardModel,
    ConsultantMessageModel,
    ConsultantSessionModel,
    DeckModel,
    DocumentChunkModel,
    DocumentModel,
    DocumentPageModel,
    EmbeddingCacheModel,
    FolderModel,
    IgnoredDuplicateModel,
    JobModel,
    LinterRuleModel,
    LLMConfigModel,
    MediaModel,
    NoteChunkLinkModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionMediaModel,
    NoteVersionModel,
    PersonaFolderModel,
    PersonaModel,
    PersonaVersionModel,
    PipelineModel,
    PipelineStepModel,
    PromptModel,
    PythonToolModel,
    TokenUsageModel,
)

test_db = SqliteDatabase("file:memdb_capture?mode=memory&cache=shared", uri=True)
db.init("file:memdb_capture?mode=memory&cache=shared", uri=True)

models = [
    DeckModel,
    NoteTypeModel,
    NoteModel,
    CardModel,
    NoteVersionModel,
    PersonaFolderModel,
    PersonaModel,
    PersonaVersionModel,
    ConsultantSessionModel,
    ConsultantMessageModel,
    PipelineModel,
    PipelineStepModel,
    PythonToolModel,
    FolderModel,
    DocumentModel,
    DocumentPageModel,
    IgnoredDuplicateModel,
    LLMConfigModel,
    PromptModel,
    MediaModel,
    NoteVersionMediaModel,
    NoteChunkLinkModel,
    DocumentChunkModel,
    AICacheModel,
    EmbeddingCacheModel,
    JobModel,
    TokenUsageModel,
    LinterRuleModel,
    AuditRecordModel,
]

db.connect(reuse_if_open=True)
db.create_tables(models, safe=True)

import time  # noqa: E402

# Create rich sample data
content = """# Partie 1 : Introduction à la Biologie Cellulaire
Les cellules eucaryotes possèdent un noyau délimité par une membrane nucléaire.

## Définitions clés
Membrane plasmique, cytoplasme, noyau, mitochondries, ribosomes.

## Structure fondamentale
La cellule est l'unité structurale et fonctionnelle du vivant.

# Partie 2 : Organites Cellulaires
Les organites sont des compartiments spécialisés dans des fonctions précises.

## Mitochondries
Les mitochondries produisent de l'ATP via la respiration cellulaire.

## Réticulum endoplasmique
Réseau membranaire intra-cellulaire impliqué dans la synthèse protéique.

# Partie 3 : Communication cellulaire
Les cellules communiquent via des signaux chimiques et électriques.

## Signalisation
Récepteurs membranaires, seconds messagers, cascade de signalisation.
"""

doc = DocumentModel.create(
    title="Biologie Cellulaire — Cours L1",
    file_type="md",
    total_pages=1,
    content=content,
)

DocumentChunkModel.create(
    document=doc,
    chunk_index=0,
    heading_path="Partie 1 : Introduction à la Biologie Cellulaire > Définitions clés",
    content="Membrane plasmique, cytoplasme, noyau, mitochondries, ribosomes.",
    content_hash="hash_0",
)
DocumentChunkModel.create(
    document=doc,
    chunk_index=1,
    heading_path="Partie 2 : Organites Cellulaires > Mitochondries",
    content="Les mitochondries produisent de l'ATP via la respiration cellulaire.",
    content_hash="hash_1",
)
DocumentChunkModel.create(
    document=doc,
    chunk_index=2,
    heading_path="Partie 3 : Communication cellulaire > Signalisation",
    content="Récepteurs membranaires, seconds messagers, cascade de signalisation.",
    content_hash="hash_2",
)

out_dir = sys.argv[1] if len(sys.argv) > 1 else "temp/screens"
os.makedirs(out_dir, exist_ok=True)

# === Capture DelimitationDialog ===
from ankiforge.ui.views.documents_view.dialogs.delimitation_dialog import DocumentDelimitationDialog  # noqa: E402

dlg1 = DocumentDelimitationDialog(doc)
dlg1.show()
app.processEvents()
time.sleep(0.4)
app.processEvents()
dlg1.grab().save(f"{out_dir}/delimitation_dialog.png")
print("✅ delimitation_dialog.png")
dlg1.close()

# === Capture DocumentScopeDialog ===
from ankiforge.ui.dialogs.document_scope_dialog import DocumentScopeDialog  # noqa: E402

dlg2 = DocumentScopeDialog(doc)
dlg2.show()
app.processEvents()
time.sleep(0.4)
app.processEvents()
dlg2.grab().save(f"{out_dir}/scope_dialog.png")
print("✅ scope_dialog.png")
dlg2.close()

print("Captures terminées.")
