import os
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["ANKIFORGE_ENV"] = "testing"

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPageSize, QPainter, QPdfWriter
from PySide6.QtWidgets import QApplication

from ankiforge.database.models import DocumentModel
from ankiforge.ui.style_engine import get_style_engine
from ankiforge.ui.views.documents_view.dialogs.delimitation_dialog import DocumentDelimitationDialog
from ankiforge.utils.paths import get_project_root


def create_sample_pdf(file_path: Path) -> None:
    """Génère un PDF médical synthétique de 7 pages pour le rendu visuel offscreen."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    writer = QPdfWriter(str(file_path))
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    painter = QPainter(writer)

    pages = [
        (
            "Sommaire & Table des Matières",
            "1. Anatomie Cardiaque ................... Page 3\n"
            "2. Cycle Cardiaque ..................... Page 4\n"
            "3. Électrophysiologie & ECG ............ Page 5\n"
            "4. Régulation Hémodynamique ........... Page 6\n"
            "Annexes ................................ Page 7",
        ),
        (
            "Préface & Remerciements",
            "Ce polycopié a été élaboré pour les étudiants en 2e cycle d'études médicales.\nRemerciements au laboratoire de physiologie cardiovasculaire pour leur relecture.",
        ),
        (
            "Chapitre 1 : Anatomie Cardiaque",
            "Le cœur est un muscle creux constitué de quatre cavités :\n"
            "- Deux oreillettes (atria) réceptrices\n"
            "- Deux ventricules éjecteurs\n\n"
            "Le septum interventriculaire sépare les circulations pulmonaire et générale.",
        ),
        (
            "Chapitre 2 : Cycle Cardiaque",
            "La révolution cardiaque dure environ 0.8 seconde au repos.\n"
            "1. Systole auriculaire (remplissage actif)\n"
            "2. Systole ventriculaire (contraction isovolumétrique puis éjection)\n"
            "3. Diastole générale (relaxation et remplissage passif)",
        ),
        (
            "Chapitre 3 : Électrophysiologie & ECG",
            "L'automatisme cardiaque naît dans le nœud sinusal de Keith et Flack.\n"
            "- Onde P : dépolarisation auriculaire\n"
            "- Complexe QRS : dépolarisation ventriculaire (durée < 0.10s)\n"
            "- Onde T : repolarisation ventriculaire",
        ),
        (
            "Chapitre 4 : Régulation Hémodynamique",
            "Loi fondamentale : Pression Artérielle = Débit Cardiaque x Résistances Vasculaires Périphériques.\nLe débit cardiaque moyen est de 5 L/min chez l'adulte au repos.",
        ),
        (
            "Bibliographie & Annexes Médicales",
            "1. Ganong's Review of Medical Physiology, 26th Ed.\n2. Guyton and Hall Textbook of Medical Physiology, 14th Ed.\n3. Tables de constantes hémodynamiques de référence.",
        ),
    ]

    font_header = QFont("Helvetica", 18, QFont.Weight.Bold)
    font_body = QFont("Helvetica", 12)

    for i, (title, body) in enumerate(pages):
        if i > 0:
            writer.newPage()

        # En-tête page
        painter.setFont(font_header)
        painter.setPen(QColor("#0f172a"))
        painter.drawText(200, 400, title)

        painter.setPen(QColor("#64748b"))
        painter.setFont(font_body)
        painter.drawText(200, 520, f"Faculté de Médecine • Physiologie Humaine • Page {i + 1} sur 7")

        # Ligne séparatrice
        painter.drawLine(200, 560, 4600, 560)

        # Corps de texte
        painter.setFont(font_body)
        painter.setPen(QColor("#1e293b"))
        y = 750
        for line in body.split("\n"):
            painter.drawText(200, y, line)
            y += 200

    painter.end()


def main() -> None:
    from ankiforge.services.profile_manager import ProfileManager

    pm = ProfileManager()
    pm.switch_profile("default")

    app = QApplication.instance() or QApplication([])
    engine = get_style_engine()
    engine.apply_theme("ide")

    pdf_sample_path = get_project_root() / "temp" / "physiologie_cardio.pdf"
    create_sample_pdf(pdf_sample_path)

    doc, _ = DocumentModel.get_or_create(
        title="Physiologie Humaine - Système Cardiovasculaire.pdf",
        defaults={
            "content": (
                "<!-- PAGE: 1 -->\n# Sommaire\nTable des matières générale.\n\n"
                "<!-- PAGE: 2 -->\n# Préface & Remerciements\nCe cours a été rédigé avec l'aide des étudiants.\n\n"
                "<!-- PAGE: 3 -->\n# 1. Anatomie Cardiaque\nLe cœur est constitué de quatre cavités : deux oreillettes et deux ventricules.\n\n"
                "<!-- PAGE: 4 -->\n# 2. Cycle Cardiaque\nLa révolution cardiaque comprend la systole auriculaire, la systole ventriculaire et la diastole générale.\n\n"
                "<!-- PAGE: 5 -->\n# 3. Électrophysiologie & ECG\nL'onde P correspond à la dépolarisation auriculaire. Le complexe QRS traduit la dépolarisation ventriculaire.\n\n"
                "<!-- PAGE: 6 -->\n# 4. Régulation Hémodynamique\nLe débit cardiaque est le produit de la fréquence cardiaque par le volume d'éjection systolique.\n\n"
                "<!-- PAGE: 7 -->\n# Bibliographie & Annexes\nOuvrages de référence et tables de constantes physiologiques.\n"
            ),
            "file_type": "pdf",
            "source_url": str(pdf_sample_path),
            "total_pages": 7,
            "start_page": 3,
            "end_page": 6,
        },
    )
    if not doc.source_url or doc.source_url != str(pdf_sample_path):
        doc.source_url = str(pdf_sample_path)
        doc.save()

    # Chunks et Cartes associées pour l'aperçu réaliste
    import uuid

    from ankiforge.database.models import DocumentChunkModel, NoteChunkLinkModel, NoteModel, NoteTypeModel

    nt = NoteTypeModel.select().first() or NoteTypeModel.create(name="Basic", fields_schema='["Front", "Back"]')
    chunks = list(DocumentChunkModel.select().where(DocumentChunkModel.document == doc))
    if not chunks:
        from ankiforge.services.parsing.chunking_service import ChunkingService

        raw_chunks = ChunkingService.extract_chunks(doc.content, file_type="pdf")
        for idx, rc in enumerate(raw_chunks):
            c = DocumentChunkModel.create(
                document=doc,
                chunk_index=idx,
                heading_path=rc.get("heading_path"),
                page_number=rc.get("page_number"),
                content=rc.get("content"),
                content_hash=rc.get("content_hash"),
            )
            chunks.append(c)

    if chunks and not NoteChunkLinkModel.select().join(DocumentChunkModel).where(DocumentChunkModel.document == doc).exists():
        if len(chunks) > 2:
            for i in range(3):
                n = NoteModel.create(guid=uuid.uuid4().hex, note_type=nt, raw_content=f"Anatomie Q{i + 1}")
                NoteChunkLinkModel.create(note=n, chunk=chunks[2])
        if len(chunks) > 3:
            for i in range(2):
                n = NoteModel.create(guid=uuid.uuid4().hex, note_type=nt, raw_content=f"Cycle Q{i + 1}")
                NoteChunkLinkModel.create(note=n, chunk=chunks[3])

    dlg = DocumentDelimitationDialog(doc)
    dlg.resize(1300, 780)
    dlg.show()
    for _ in range(15):
        app.processEvents()

    out_dir = get_project_root() / "temp" / "screens"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Capture 1: Vue PDF par défaut (Page 1)
    out_pdf = out_dir / "delimitation_modal.png"
    dlg.grab().save(str(out_pdf))
    print(f"Capture vue PDF (Page 1) réussie : {out_pdf}")

    # Test 1 : Désélection individuelle de la section 2 ("1. Anatomie Cardiaque")
    # En cliquant sur la ligne ou sa checkbox
    w_row2 = dlg.sections_list.itemWidget(dlg.sections_list.item(2))
    assert w_row2 is not None
    # On simule un clic sur la checkbox individuelle
    w_row2.checkbox.setChecked(False)
    for _ in range(15):
        app.processEvents()
    assert dlg.sections_list.item(2).checkState() == Qt.CheckState.Unchecked
    out_uncheck = out_dir / "delimitation_modal_individual_uncheck.png"
    dlg.grab().save(str(out_uncheck))
    print(f"Capture désélection individuelle réussie : {out_uncheck}")

    # Re-cocher
    w_row2.checkbox.setChecked(True)
    for _ in range(5):
        app.processEvents()

    # Test 2 : Synchronisation au saut de page (sélection de '2. Cycle Cardiaque' -> Page 4)
    dlg.sections_list.setCurrentRow(3)
    for _ in range(15):
        app.processEvents()
    out_pdf_jump = out_dir / "delimitation_modal_jump_page4.png"
    dlg.grab().save(str(out_pdf_jump))
    print(f"Capture synchronisation saut Page 4 réussie : {out_pdf_jump}")

    dlg.close()

    # Capture 3: Document Markdown natif (SANS notion de page)
    md_doc, _ = DocumentModel.get_or_create(
        title="Guide_Architecture_Moderne.md",
        defaults={
            "content": (
                "# Architecture Système\nVue d'ensemble des microservices et communications gRPC.\n\n"
                "# Modèle de Données\nSchémas relationnels et gestion des migrations de base de données.\n\n"
                "# API & Endpoints\nSpécification OpenAPI et protocoles de streaming événementiel.\n\n"
                "# Monitoring & Métriques\nPrometheus, OpenTelemetry et tableaux de bord Grafana.\n"
            ),
            "file_type": "md",
            "total_pages": 1,
        },
    )
    # Chunks pour le document markdown
    from ankiforge.services.parsing.chunking_service import ChunkingService

    md_chunks = list(DocumentChunkModel.select().where(DocumentChunkModel.document == md_doc))
    if not md_chunks:
        raw_chunks = ChunkingService.extract_chunks(md_doc.content, file_type="md")
        for idx, rc in enumerate(raw_chunks):
            DocumentChunkModel.create(
                document=md_doc,
                chunk_index=idx,
                heading_path=rc.get("heading_path"),
                page_number=None,
                content=rc.get("content"),
                content_hash=rc.get("content_hash"),
            )

    dlg_md = DocumentDelimitationDialog(md_doc)
    dlg_md.resize(1300, 780)
    dlg_md.show()
    for _ in range(15):
        app.processEvents()

    # Vérification que le cadre de pagination est masqué pour un document Markdown
    assert dlg_md.pages_card is not None
    assert dlg_md.pages_card.isHidden()

    # Test de désélection individuelle sur document Markdown
    w_md_row = dlg_md.sections_list.itemWidget(dlg_md.sections_list.item(3))
    assert w_md_row is not None
    w_md_row.checkbox.setChecked(False)
    for _ in range(15):
        app.processEvents()
    assert dlg_md.sections_list.item(3).checkState() == Qt.CheckState.Unchecked

    out_md_doc = out_dir / "delimitation_modal_markdown_document.png"
    dlg_md.grab().save(str(out_md_doc))
    print(f"Capture modal document Markdown (sans page) réussie : {out_md_doc}")
    dlg_md.close()


if __name__ == "__main__":
    main()
