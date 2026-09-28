import logging
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import (
    DocumentChunkModel,
    DocumentModel,
    NoteChunkLinkModel,
)
from ankiforge.repositories.document_repository import DocumentRepository
from ankiforge.services.audit.coverage_alignment_service import CoverageAlignmentService
from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton
from ankiforge.ui.components.inputs import GlowLineEdit
from ankiforge.ui.dispatch import run_on_owner_thread
from ankiforge.ui.theme import DesignTokens, StyledMenu
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.event_bus import CoverageSyncedEvent, event_bus
from ankiforge.utils.icon_loader import load_on_accent_icon, load_phosphor_icon

if TYPE_CHECKING:
    from ankiforge.ui.components.linter_widgets import SourceDiagnosticCardWidget

logger = logging.getLogger(__name__)

# Rôles personnalisés du sommaire de l'inspecteur. Les fragments portent l'essentiel de
# leur identité dans ces rôles plutôt que dans la seule chaîne affichée, afin que les
# actions (exclusion/ré-inclusion) restent possibles sans réinterroger la base.
_SCOPE_HINT = "Clic droit sur une section : exclure / ré-inclure"

_ROLE_CHUNK_ID = int(Qt.ItemDataRole.UserRole)
_ROLE_HEADING = _ROLE_CHUNK_ID + 1
_ROLE_CARDS = _ROLE_CHUNK_ID + 2
_ROLE_TITLE = _ROLE_CHUNK_ID + 3


class ClickableChunkWidget(QFrame):
    """Un paragraphe du document, cliquable, avec un indicateur visuel de couverture."""

    clicked = Signal(int)

    def __init__(self, chunk_id: int, text: str, status: str = "unprofiled", parent=None):
        super().__init__(parent)
        self.chunk_id = chunk_id
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        color_map = {
            "unprofiled": "transparent",
            "gap": DesignTokens.COLOR_YELLOW,
            "covered": DesignTokens.COLOR_GREEN,
        }
        border_color = color_map.get(status, "transparent")

        self.setStyleSheet(f"""
            ClickableChunkWidget {{
                background-color: {DesignTokens.BG_MAIN};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-left: 3px solid {border_color};
                border-radius: 4px;
                margin-bottom: 4px;
            }}
            ClickableChunkWidget:hover {{
                background-color: {DesignTokens.BG_HOVER};
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)

        self.lbl_text = QLabel(text)
        self.lbl_text.setWordWrap(True)
        self.lbl_text.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; line-height: 1.4;")
        layout.addWidget(self.lbl_text)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.chunk_id)
        super().mousePressEvent(event)


class DocumentInspectorPanel(QWidget):
    """Panneau pour inspecter l'audit et la couverture détaillée d'un document."""

    back_requested = Signal()
    request_navigation = Signal(str, object)

    def __init__(self, doc_or_id: int | DocumentModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        if isinstance(doc_or_id, DocumentModel):
            self.doc = doc_or_id
            self.doc_id = doc_or_id.id
        else:
            self.doc_id = doc_or_id
            self.doc = DocumentModel.get_or_none(DocumentModel.id == doc_or_id)

        self._applying_local_coverage_change = False

        if not self.doc:
            return

        self._on_coverage_synced = self._handle_coverage_synced
        event_bus.subscribe(CoverageSyncedEvent, self._on_coverage_synced)
        self.destroyed.connect(lambda: event_bus.unsubscribe(CoverageSyncedEvent, self._on_coverage_synced))

        self.setStyleSheet(f"background-color: {DesignTokens.BG_MAIN};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # 1. Header du Document
        header_frame = QFrame()
        header_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        h_layout = QHBoxLayout(header_frame)
        h_layout.setContentsMargins(12, 8, 12, 8)
        h_layout.setSpacing(10)

        btn_back = SecondaryButton("Retour", tooltip="Retourner à la liste générale des documents")
        btn_back.setIcon(load_phosphor_icon("ph.arrow-left", color=DesignTokens.TEXT_PRIMARY))
        btn_back.clicked.connect(self.back_requested.emit)

        ico_doc = QLabel()
        ico_doc.setPixmap(load_phosphor_icon("ph.file-text", color=DesignTokens.COLOR_BLUE, weight="fill").pixmap(18, 18))
        ico_doc.setStyleSheet("border: none; background: transparent;")

        title_to_display = self.doc.original_media.original_name if self.doc.original_media else self.doc.title
        header_lbl = QLabel(title_to_display)
        header_lbl.setFont(QFont(DesignTokens.FONT_MAIN, 12, QFont.Weight.Bold))
        header_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")
        header_lbl.setToolTip(title_to_display)
        # Le titre du document peut être très long : il cède de la place à la pastille de
        # couverture, dont le libellé change de longueur selon le périmètre retenu.
        header_lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        header_lbl.setMinimumWidth(120)

        self.lbl_doc_summary = QLabel("Couverture : 0%")
        self.lbl_doc_summary.setFont(QFont(DesignTokens.FONT_MAIN, 10, QFont.Weight.Bold))
        self.lbl_doc_summary.setStyleSheet(
            f"background-color: {DesignTokens.COLOR_GREEN_BG}; color: {DesignTokens.COLOR_GREEN}; border: 1px solid {DesignTokens.COLOR_GREEN_BORDER}; border-radius: 9999px; padding: 4px 10px;"
        )

        self.btn_fill_orphans = PrimaryButton("Générer les cartes manquantes", tooltip="Générer automatiquement des flashcards pour les sections non couvertes")
        self.btn_fill_orphans.setIcon(load_on_accent_icon("ph.sparkle"))
        self.btn_fill_orphans.clicked.connect(self._on_fill_all_orphans)

        self.btn_reindex = SecondaryButton("Ré-indexer FAISS", tooltip="Recalculer les embeddings vectoriels et réindexer ce document dans FAISS")
        self.btn_reindex.setIcon(load_phosphor_icon("ph.arrows-clockwise", color=DesignTokens.TEXT_PRIMARY))
        self.btn_reindex.clicked.connect(self._on_reindex_faiss)

        self.btn_align_cards = SecondaryButton("Synchroniser les fiches")
        self.btn_align_cards.setIcon(load_phosphor_icon("ph.link", color=DesignTokens.COLOR_BLUE))
        self.btn_align_cards.setToolTip("Associer les fiches portant les tags de traçabilité (doc:/source:/page:/section:) aux sections de ce cours")
        self.btn_align_cards.clicked.connect(self._on_align_cards)

        self.btn_refine_links = SecondaryButton("Affiner les liens")
        self.btn_refine_links.setIcon(load_phosphor_icon("ph.crosshair", color=DesignTokens.COLOR_BLUE))
        self.btn_refine_links.setToolTip("Rattacher aux sous-sections (H3+) les cartes liées à un titre parent large (H1/H2) — affinement déterministe, local et instantané")
        self.btn_refine_links.clicked.connect(self._on_refine_links)

        h_layout.addWidget(btn_back)
        h_layout.addSpacing(4)
        h_layout.addWidget(ico_doc)
        h_layout.addWidget(header_lbl, 1)
        h_layout.addWidget(self.lbl_doc_summary)
        h_layout.addWidget(self.btn_align_cards)
        h_layout.addWidget(self.btn_refine_links)
        h_layout.addWidget(self.btn_fill_orphans)
        h_layout.addWidget(self.btn_reindex)

        layout.addWidget(header_frame)

        # 2. Splitter 2 Volets
        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        left_panel = QFrame()
        left_panel.setStyleSheet(f".QFrame {{ background-color: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 6px; }}")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(10, 10, 10, 10)
        left_layout.setSpacing(8)

        lbl_toc = QLabel("Sommaire & Sections du Document")
        lbl_toc.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
        lbl_toc.setStyleSheet(
            f"color: {DesignTokens.TEXT_PRIMARY}; border-bottom: 1px solid {DesignTokens.BORDER_COLOR}; "
            f"border-top: none; border-left: none; border-right: none; background: transparent; padding-bottom: 6px;"
        )
        left_layout.addWidget(lbl_toc)

        self.chapters_list = QListWidget()
        self.chapters_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                color: {DesignTokens.TEXT_PRIMARY};
                padding: 4px;
            }}
            QListWidget::item {{
                padding: 8px;
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
            }}
            QListWidget::item:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
            QListWidget::item:selected {{
                background-color: {DesignTokens.BG_HOVER};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)
        self.chapters_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.chapters_list.customContextMenuRequested.connect(self._show_chapter_context_menu)
        self.chapters_list.currentItemChanged.connect(self._on_current_chapter_changed)
        left_layout.addWidget(self.chapters_list, 1)

        scope_row = QHBoxLayout()
        scope_row.setContentsMargins(0, 0, 0, 0)
        scope_row.setSpacing(6)

        self.btn_exclude_section = SecondaryButton("Exclure cette section", tooltip="Retirer la section sélectionnée du périmètre du document")
        self.btn_exclude_section.setIcon(load_phosphor_icon("ph.prohibit", color=DesignTokens.TEXT_PRIMARY))
        # `clicked` émet un `checked` booléen : on court-circuite par un slot sans argument
        # pour que ce booléen ne soit pas pris pour un identifiant de fragment.
        self.btn_exclude_section.clicked.connect(lambda _checked=False: self.toggle_section_exclusion())
        scope_row.addWidget(self.btn_exclude_section)

        lbl_scope_status = QLabel(self._scope_status_text(0, "sections"))
        lbl_scope_status.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; border: none; background: transparent;")
        self.lbl_scope_status = lbl_scope_status
        scope_row.addWidget(lbl_scope_status, 1)
        left_layout.addLayout(scope_row)

        lbl_text_title = QLabel("Extrait de la Section Sélectionnée")
        lbl_text_title.setFont(QFont(DesignTokens.FONT_MAIN, 10, QFont.Weight.Bold))
        lbl_text_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent; padding-top: 4px;")
        left_layout.addWidget(lbl_text_title)

        self.text_preview = QTextBrowser()
        self.text_preview.setStyleSheet(f"""
            QTextBrowser {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_PRIMARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                padding: 10px;
                font-size: 13px;
                line-height: 1.5;
            }}
        """)
        left_layout.addWidget(self.text_preview, 1)

        right_panel = QFrame()
        right_panel.setStyleSheet(f".QFrame {{ background-color: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 6px; }}")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 10, 10, 10)
        right_layout.setSpacing(8)

        lbl_cards_title = QLabel("Cartes Anki Liées & Action de Forge")
        lbl_cards_title.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
        lbl_cards_title.setStyleSheet(
            f"color: {DesignTokens.TEXT_PRIMARY}; border-bottom: 1px solid {DesignTokens.BORDER_COLOR}; "
            f"border-top: none; border-left: none; border-right: none; background: transparent; padding-bottom: 6px;"
        )
        right_layout.addWidget(lbl_cards_title)

        self.cards_scroll = QScrollArea()
        self.cards_scroll.setWidgetResizable(True)
        self.cards_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.cards_scroll.setStyleSheet("background: transparent;")

        self.cards_container = QWidget()
        self.cards_container.setStyleSheet("background: transparent;")
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(4, 4, 4, 4)
        self.cards_layout.setSpacing(10)
        self.cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.cards_scroll.setWidget(self.cards_container)
        right_layout.addWidget(self.cards_scroll, 1)

        self.splitter.addWidget(left_panel)
        self.splitter.addWidget(right_panel)
        self.splitter.setStretchFactor(0, 5)
        self.splitter.setStretchFactor(1, 5)
        layout.addWidget(self.splitter, 1)

        self.load_chunks()

    def _handle_coverage_synced(self, event: CoverageSyncedEvent) -> None:
        if event.doc_id is not None and event.doc_id != self.doc_id:
            return
        if self._applying_local_coverage_change:
            # La modification vient d'être appliquée ligne à ligne : reconstruire la liste
            # ici effacerait la sélection de l'utilisateur pour rien.
            return
        run_on_owner_thread(self, self.load_chunks)

    def load_chunks(self) -> None:
        self.chapters_list.clear()
        chunks = list(DocumentChunkModel.select().where(DocumentChunkModel.document == self.doc).order_by(DocumentChunkModel.chunk_index))

        if not chunks:
            self.lbl_doc_summary.setText("Non indexé (0 section)")
            self.lbl_scope_status.setText(self._scope_status_text(0, "sections"))
            self.text_preview.setHtml(f"<p style='color: {DesignTokens.TEXT_MUTED};'>Ce document n'a pas encore été fragmenté. Cliquez sur 'Ré-indexer FAISS'.</p>")
            self._sync_exclusion_action()
            return

        for chunk in chunks:
            card_count = NoteChunkLinkModel.select().where(NoteChunkLinkModel.chunk == chunk).count()
            title_str = chunk.heading_path or (f"Page {chunk.page_number}" if chunk.page_number else f"Section #{chunk.chunk_index + 1}")

            item = QListWidgetItem()
            item.setData(_ROLE_CHUNK_ID, chunk.id)
            item.setData(_ROLE_HEADING, chunk.heading_path or "")
            item.setData(_ROLE_CARDS, card_count)
            item.setData(_ROLE_TITLE, title_str)
            self._apply_row_state(item, card_count, DocumentRepository.is_section_excluded(self.doc, chunk.heading_path or ""))
            self.chapters_list.addItem(item)

        self._refresh_coverage_summary()

        if self.chapters_list.count() > 0:
            self.chapters_list.setCurrentRow(0)

    @staticmethod
    def _row_cards(item: QListWidgetItem | None) -> int:
        """Nombre de cartes Anki portées par la ligne du sommaire."""
        return int(item.data(_ROLE_CARDS) or 0) if item is not None else 0

    def _apply_row_state(self, item: QListWidgetItem, card_count: int, is_excluded: bool) -> None:
        """Habille une ligne du sommaire selon sa couverture et son appartenance au périmètre."""
        title_str = str(item.data(_ROLE_TITLE) or "")
        if is_excluded:
            item.setText(f"⊘ {title_str}  ·  Exclue de l'analyse")
            item.setForeground(QColor(DesignTokens.TEXT_MUTED))
            item.setToolTip(f"{title_str}\nHors périmètre : cette section ne compte plus dans la couverture du document.")
            return
        if card_count > 0:
            item.setText(f"● {title_str}  ·  {card_count} carte(s)")
            item.setForeground(QColor(DesignTokens.COLOR_GREEN))
        else:
            item.setText(f"○ {title_str}  ·  Trou (0 carte)")
            item.setForeground(QColor(DesignTokens.COLOR_YELLOW))
        item.setToolTip(f"{title_str}\nClic droit pour exclure cette section de l'analyse.")

    def _refresh_row_states(self) -> None:
        """Recalcule les compteurs de cartes et réapplique l'état d'exclusion à chaque ligne, sans reconstruire le sommaire."""
        counts = DocumentRepository().count_cards_by_chunk(self.doc_id)
        for row in range(self.chapters_list.count()):
            item = self.chapters_list.item(row)
            card_count = counts.get(int(item.data(_ROLE_CHUNK_ID) or 0), 0)
            item.setData(_ROLE_CARDS, card_count)
            self._apply_row_state(
                item,
                card_count,
                DocumentRepository.is_section_excluded(self.doc, str(item.data(_ROLE_HEADING) or "")),
            )

    def _covered_row_count(self) -> int:
        """Nombre de lignes du sommaire portant au moins une carte Anki."""
        return sum(1 for row in range(self.chapters_list.count()) if self._row_cards(self.chapters_list.item(row)) > 0)

    def _refresh_coverage_summary(self) -> None:
        """Recalcule la pastille de couverture globale à partir des unités actives du document."""
        stats = DocumentRepository().get_coverage_stats(self.doc_id)
        unit_type = stats.get("unit_type", "sections")
        unit_label = "pages" if unit_type == "pages" else "sections"
        covered_units = stats.get("covered_units", self._covered_row_count())
        total_units = stats.get("total_units", self.chapters_list.count())
        percent = stats.get("coverage_pct", 0.0)
        total_cards = stats.get("total_cards", 0)
        excluded_units = stats.get("excluded_units", 0)
        self.lbl_scope_status.setText(self._scope_status_text(excluded_units, unit_label))
        if total_units == 0 and excluded_units > 0:
            # Périmètre entièrement exclu : afficher « 0 % » en rouge sanctionnerait un choix
            # de l'utilisateur, alors qu'aucune section active ne demande de carte.
            self.lbl_doc_summary.setText("Périmètre vide (0 section active)")
            self.lbl_doc_summary.setStyleSheet(
                f"background-color: {DesignTokens.BG_INPUT}; color: {DesignTokens.TEXT_MUTED}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 9999px; padding: 4px 10px;"
            )
            return
        self.lbl_doc_summary.setText(f"Couverture : {percent:.0f}% ({covered_units}/{total_units} {unit_label} · {total_cards} cartes)")
        if percent >= 90:
            self.lbl_doc_summary.setStyleSheet(
                f"background-color: {DesignTokens.COLOR_GREEN_BG}; color: {DesignTokens.COLOR_GREEN}; border: 1px solid {DesignTokens.COLOR_GREEN_BORDER}; border-radius: 9999px; padding: 4px 10px;"
            )
        elif percent >= 50:
            self.lbl_doc_summary.setStyleSheet(
                f"background-color: {DesignTokens.COLOR_YELLOW_BG}; color: {DesignTokens.COLOR_YELLOW}; border: 1px solid {DesignTokens.COLOR_YELLOW_BORDER}; border-radius: 9999px; padding: 4px 10px;"
            )
        else:
            self.lbl_doc_summary.setStyleSheet(
                f"background-color: {DesignTokens.COLOR_RED_BG}; color: {DesignTokens.COLOR_RED}; border: 1px solid {DesignTokens.COLOR_RED_BORDER}; border-radius: 9999px; padding: 4px 10px;"
            )

    @staticmethod
    def _scope_status_text(excluded_units: int, unit_label: str) -> str:
        """Phrase d'état du périmètre affichée sous le sommaire (accents et pluriel corrects)."""
        if excluded_units <= 0:
            return _SCOPE_HINT
        noun = unit_label if excluded_units > 1 else unit_label.removesuffix("s")
        return f"{excluded_units} {noun} hors périmètre · clic droit pour ré-inclure"

    def _on_current_chapter_changed(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        """La sélection du sommaire pilote l'aperçu et l'action d'exclusion de section."""
        self._sync_exclusion_action()
        if current is None:
            return
        chunk_id = current.data(_ROLE_CHUNK_ID)
        if chunk_id:
            self.inspect_chunk(chunk_id)

    def _exclusion_spec(self, item: QListWidgetItem | None) -> tuple[str, str, bool, bool]:
        """Décide l'état de l'action d'exclusion pour une ligne : (libellé, icône, exclue, appliquable).

        Source unique de vérité partagée par le bouton de la barre d'actions et par le menu
        contextuel : les deux affichent donc toujours la même proposition pour une section.
        """
        heading = str(item.data(_ROLE_HEADING) or "") if item is not None else ""
        if not DocumentRepository.is_excludable_heading(heading):
            return "Exclure cette section", "ph.prohibit", False, False
        if DocumentRepository.is_section_excluded(self.doc, heading):
            return "Ré-inclure la section", "ph.arrow-counter-clockwise", True, True
        return "Exclure cette section", "ph.prohibit", False, True

    def _sync_exclusion_action(self) -> None:
        """Aligne le libellé de l'action d'exclusion sur la section sélectionnée."""
        item = self.chapters_list.currentItem()
        title = str(item.data(_ROLE_TITLE) or "") if item is not None else ""
        label, icon_name, is_excluded, applicable = self._exclusion_spec(item)

        self.btn_exclude_section.setText(label)
        self.btn_exclude_section.setIcon(load_phosphor_icon(icon_name, color=DesignTokens.TEXT_PRIMARY))
        self.btn_exclude_section.setEnabled(applicable)
        if not applicable:
            self.btn_exclude_section.setToolTip("Sélectionnez une section titrée : un fragment au libellé de page n'a pas de titre de section à exclure.")
        elif is_excluded:
            self.btn_exclude_section.setToolTip(f"Réintégrer « {title} » au périmètre du document et à sa couverture.")
        else:
            self.btn_exclude_section.setToolTip(f"Retirer « {title} » du périmètre : la section ne comptera plus comme une lacune de couverture.")

    def toggle_section_exclusion(self) -> None:
        """Exclut ou réintègre la section sélectionnée du périmètre d'analyse du document.

        L'exclusion est persistée sur ``DocumentModel.excluded_headings`` puis répercutée
        immédiatement sur le sommaire et sur la couverture globale, sans reconstruire
        l'inspecteur : la section reste sélectionnée et inspectable.
        """
        item = self.chapters_list.currentItem()
        if item is None:
            return

        heading = str(item.data(_ROLE_HEADING) or "")
        if not DocumentRepository.is_excludable_heading(heading):
            show_toast(self, "Cette section n'a pas de titre exploitable : elle ne peut pas être exclue de l'analyse.")
            return

        was_excluded = DocumentRepository.is_section_excluded(self.doc, heading)
        repo = DocumentRepository()
        if not repo.set_section_excluded(self.doc_id, heading, not was_excluded):
            logger.warning("Exclusion de la section %r refusée pour le document %s", heading, self.doc_id)
            return

        self.doc = repo.get_document_by_id(self.doc_id) or self.doc
        self._refresh_row_states()
        self._refresh_coverage_summary()
        self._sync_exclusion_action()
        show_toast(self, f"Section « {item.data(_ROLE_TITLE) or heading} » {'réintégrée' if was_excluded else 'exclue'} de l'analyse.")

        self._applying_local_coverage_change = True
        try:
            event_bus.publish(CoverageSyncedEvent(doc_id=self.doc_id))
        finally:
            self._applying_local_coverage_change = False

    @staticmethod
    def _refinement_report_text(report: dict[str, Any]) -> str:
        """Phrase de synthèse de l'affinement des liens, pour le toast de synthèse."""
        reassigned = int(report.get("reassigned", 0))
        resolved = int(report.get("false_gaps_resolved", 0))
        kept = int(report.get("kept_on_parent", 0))
        new_gaps = int(report.get("new_gaps", 0))
        if not reassigned and not kept:
            return "Aucune carte de chapitre à rattacher à une sous-section plus fine."

        parts = [f"{reassigned} carte(s) réassignée(s) vers des sous-sections plus fines ({resolved} fausse(s) lacune(s) résolue(s))"]
        if kept:
            parts.append(f"{kept} conservée(s) sur son chapitre faute de sous-section plus spécifique")
        if new_gaps:
            parts.append(f"{new_gaps} conteneur(s) laissé(s) sans carte")
        return " · ".join(parts)

    @Slot()
    def _on_refine_links(self) -> None:
        """Affine les liens rattachés aux titres parents larges vers leurs sous-sections (H3+).

        L'affinement est déterministe, local et instantané : le service réécrit les liens et
        les tags de provenance dans une transaction, puis l'inspecteur rafraîchit ses
        compteurs en place — la section sélectionnée reste sélectionnée et inspectable.
        """
        if not self.doc:
            return

        self._applying_local_coverage_change = True
        try:
            report = CoverageAlignmentService.refine_links_to_subsections(self.doc_id)
        finally:
            self._applying_local_coverage_change = False

        self._refresh_row_states()
        self._refresh_coverage_summary()
        self._refresh_current_chunk_panel()
        show_toast(self, self._refinement_report_text(report))

    def _refresh_current_chunk_panel(self) -> None:
        """Recharge l'aperçu de la section sélectionnée après une modification de ses liens.

        Une carte déplacée hors de la section courante doit disparaître du panneau des
        cartes liées sans attendre que l'utilisateur resélectionne une autre ligne.
        """
        current = self.chapters_list.currentItem()
        chunk_id = current.data(_ROLE_CHUNK_ID) if current is not None else None
        if chunk_id:
            self.inspect_chunk(chunk_id)

    def chapter_context_menu(self, item: QListWidgetItem) -> StyledMenu | None:
        """Menu contextuel d'une ligne du sommaire : exclure ou ré-inclure sa section.

        L'action est proposée pour toute section titrée et désactivée pour un fragment au
        libellé de page, qui n'a pas de titre de section à exclure. Un clic droit ne
        change pas la ligne courante sous Qt : on la sélectionne donc d'abord, ce qui met
        l'aperçu à jour et fait porter l'action à la section visée.
        """
        if item is None:
            return None

        label, icon_name, _is_excluded, applicable = self._exclusion_spec(item)
        menu = StyledMenu(self)
        toggle_action = menu.addAction(load_phosphor_icon(icon_name, color=DesignTokens.TEXT_SECONDARY), label)
        toggle_action.setEnabled(applicable)
        toggle_action.triggered.connect(lambda _checked=False: self._toggle_chapter_from_menu(item))
        return menu

    def _toggle_chapter_from_menu(self, item: QListWidgetItem) -> None:
        """Bascule l'exclusion de la section visée par le menu contextuel, en la sélectionnant."""
        self.chapters_list.setCurrentItem(item)
        self.toggle_section_exclusion()

    def _show_chapter_context_menu(self, pos: QPoint) -> None:
        """Ouvre le menu contextuel du sommaire à l'emplacement du clic droit."""
        menu = self.chapter_context_menu(self.chapters_list.itemAt(pos))
        if menu is None:
            return
        menu.exec(self.chapters_list.viewport().mapToGlobal(pos))

    def inspect_chunk(self, chunk_id: int) -> None:
        chunk = DocumentChunkModel.get_or_none(DocumentChunkModel.id == chunk_id)
        if not chunk:
            return

        header_title = chunk.heading_path or (f"Page {chunk.page_number}" if chunk.page_number else f"Section #{chunk.chunk_index + 1}")
        safe_content = chunk.content.replace("\n", "<br>")
        html_preview = (
            f"<h4 style='color: {DesignTokens.TEXT_PRIMARY}; margin-bottom: 6px;'>{header_title}</h4>"
            f"<hr style='border: 1px solid {DesignTokens.BORDER_COLOR};'/>"
            f"<p style='color: {DesignTokens.TEXT_SECONDARY}; line-height: 1.5;'>{safe_content}</p>"
        )
        self.text_preview.setHtml(html_preview)

        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        links = list(NoteChunkLinkModel.select().where(NoteChunkLinkModel.chunk == chunk))

        if not links:
            box = QFrame()
            box.setStyleSheet(f".QFrame {{ background-color: {DesignTokens.BG_INPUT}; border-radius: 6px; border: 1px dashed {DesignTokens.COLOR_YELLOW}; padding: 16px; }}")
            b_layout = QVBoxLayout(box)
            b_layout.setSpacing(10)

            lbl_warn = QLabel("Trou de cours détecté : Aucune flashcard n'a encore été générée pour cette section.")
            lbl_warn.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
            lbl_warn.setStyleSheet(f"color: {DesignTokens.COLOR_YELLOW}; border: none; background: transparent;")
            lbl_warn.setWordWrap(True)
            b_layout.addWidget(lbl_warn)

            lbl_desc = QLabel("Forgez des cartes ciblées pour combler ce manque et garantir la complétion de votre apprentissage.")
            lbl_desc.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; border: none; background: transparent;")
            lbl_desc.setWordWrap(True)
            b_layout.addWidget(lbl_desc)

            btn_gen = PrimaryButton("Forger cette section maintenant")
            btn_gen.setIcon(load_on_accent_icon("ph.sparkle"))
            btn_gen.clicked.connect(lambda: self._on_forge_chunk(chunk.id))
            b_layout.addWidget(btn_gen)

            self.cards_layout.addWidget(box)
        else:
            lbl_cnt = QLabel(f"{len(links)} carte(s) Anki forgée(s) depuis cette section :")
            lbl_cnt.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
            lbl_cnt.setStyleSheet(f"color: {DesignTokens.COLOR_GREEN}; margin-bottom: 4px; border: none; background: transparent;")
            self.cards_layout.addWidget(lbl_cnt)

            for link in links:
                note = link.note
                card_box = QFrame()
                card_box.setStyleSheet(f".QFrame {{ background-color: {DesignTokens.BG_INPUT}; border-radius: 6px; border: 1px solid {DesignTokens.BORDER_COLOR}; padding: 10px; }}")
                c_layout = QVBoxLayout(card_box)
                c_layout.setContentsMargins(8, 8, 8, 8)
                c_layout.setSpacing(6)

                import json

                from ankiforge.database.models import CardModel, NoteVersionModel

                fields = {}
                if note:
                    active_ver = NoteVersionModel.get_or_none(
                        NoteVersionModel.note == note,
                        NoteVersionModel.is_active == True,  # noqa: E712
                    )
                    if active_ver and active_ver.content:
                        try:
                            fields = json.loads(active_ver.content)
                        except Exception as e:
                            logger.debug("Erreur parsing active_ver content: %s", e)

                    if not fields and hasattr(note, "fields_data") and getattr(note, "fields_data", None):
                        try:
                            fields = json.loads(note.fields_data)
                        except Exception as e:
                            logger.debug("Erreur parsing fields_data: %s", e)

                front = fields.get("Front") or fields.get("Recto") or fields.get("Question") or "Carte Anki"
                back = fields.get("Back") or fields.get("Verso") or fields.get("Answer") or ""

                deck_name = "Général"
                if note:
                    card = CardModel.get_or_none(CardModel.note == note)
                    if card and card.deck:
                        deck_name = card.deck.name
                    elif hasattr(note, "deck") and getattr(note, "deck", None):
                        deck_name = getattr(note.deck, "name", "Général")

                top_row = QHBoxLayout()
                lbl_deck = QLabel(f"Paquet : {deck_name}")
                lbl_deck.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; border: none; background: transparent;")
                top_row.addWidget(lbl_deck)
                top_row.addStretch()
                c_layout.addLayout(top_row)

                lbl_front = QLabel(f"Q : {front}")
                lbl_front.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: 600; font-size: 12px; border: none; background: transparent;")
                lbl_front.setWordWrap(True)
                c_layout.addWidget(lbl_front)

                if back:
                    lbl_back = QLabel(f"R : {back}")
                    lbl_back.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; border: none; background: transparent;")
                    lbl_back.setWordWrap(True)
                    c_layout.addWidget(lbl_back)

                self.cards_layout.addWidget(card_box)

            btn_more = SecondaryButton("+ Générer plus de cartes pour ce chapitre")
            btn_more.setIcon(load_phosphor_icon("ph.plus", color=DesignTokens.TEXT_PRIMARY))
            btn_more.clicked.connect(lambda: self._on_forge_chunk(chunk.id))
            self.cards_layout.addWidget(btn_more)

    def _on_forge_chunk(self, chunk_id: int) -> None:
        chunk = DocumentChunkModel.get_or_none(DocumentChunkModel.id == chunk_id)
        if not chunk:
            return
        doc_title = self.doc.title if self.doc else "Document"
        section_name = chunk.heading_path or (f"Page {chunk.page_number}" if chunk.page_number else f"Section #{chunk.chunk_index + 1}")
        self.request_navigation.emit(
            "creation",
            {
                "text_source": chunk.content,
                "source_title": f"{doc_title} - {section_name}",
                "chunk_id": chunk.id,
            },
        )

    def _on_fill_all_orphans(self) -> None:
        chunks = list(DocumentChunkModel.select().where(DocumentChunkModel.document == self.doc).order_by(DocumentChunkModel.chunk_index))
        linked_chunk_ids = {link.chunk_id for link in NoteChunkLinkModel.select(NoteChunkLinkModel.chunk_id).join(DocumentChunkModel).where(DocumentChunkModel.document == self.doc)}

        orphan = next((c for c in chunks if c.id not in linked_chunk_ids), None)
        if orphan:
            self._on_forge_chunk(orphan.id)
        else:
            show_toast(self, "Toutes les sections de ce cours sont déjà couvertes !")

    def _on_reindex_faiss(self) -> None:
        from ankiforge.services.workers.coverage_worker import CoverageWorker

        show_toast(self, "Indexation FAISS et structuration en cours...")
        self._coverage_worker = CoverageWorker(self.doc.id)
        self._coverage_worker.finished_processing.connect(self._on_coverage_finished)
        self._coverage_worker.start()

    def _on_coverage_finished(self) -> None:
        show_toast(self, "Indexation FAISS terminée avec succès !")
        self.load_chunks()

    @Slot()
    def _on_align_cards(self) -> None:
        if not self.doc:
            return
        from ankiforge.services.audit.coverage_alignment_service import CoverageAlignmentService

        show_toast(self, "Synchronisation des fiches Anki via les tags en cours...")
        res = CoverageAlignmentService.align_document(self.doc.id)
        matched = res.get("matched_notes", 0)
        cov_pct = res.get("coverage_pct", 0.0)
        self.load_chunks()
        show_toast(self, f"✅ {matched} fiches Anki synchronisées via les tags ! Couverture : {cov_pct:.0f}%")


class AISourcesDiagnosticTab(QWidget):
    """Onglet de diagnostic et santé des documents : synthèse globale et inspection détaillée."""

    request_navigation = Signal(str, object)

    MIN_CARD_WIDTH = 320
    MAX_DOCUMENT_COLUMNS = 2

    _doc_cards: "list[SourceDiagnosticCardWidget]"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack)

        # PAGE 0 : Grille des Documents
        self.page_grid = QWidget()
        grid_page_layout = QVBoxLayout(self.page_grid)
        grid_page_layout.setContentsMargins(12, 12, 12, 12)
        grid_page_layout.setSpacing(10)
        self.stack.addWidget(self.page_grid)

        # PAGE 1 : Inspecteur de Document
        self.page_inspector = QWidget()
        inspector_layout = QVBoxLayout(self.page_inspector)
        inspector_layout.setContentsMargins(0, 0, 0, 0)
        self.stack.addWidget(self.page_inspector)

        # 1. Barre de KPIs globaux de la Forge
        kpi_header = QFrame()
        kpi_header.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        kpi_layout = QHBoxLayout(kpi_header)
        kpi_layout.setContentsMargins(12, 8, 12, 8)
        kpi_layout.setSpacing(12)

        def _make_kpi_chip(icon_name: str, icon_color: str, title: str):
            chip = QFrame()
            chip.setStyleSheet(f"""
                QFrame {{
                    background-color: {DesignTokens.BG_MAIN};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: {DesignTokens.RADIUS_SM}px;
                }}
            """)
            c_lay = QHBoxLayout(chip)
            c_lay.setContentsMargins(10, 5, 10, 5)
            c_lay.setSpacing(8)
            ico = QLabel()
            ico.setPixmap(load_phosphor_icon(icon_name, color=icon_color).pixmap(16, 16))
            ico.setStyleSheet("border: none; background: transparent;")
            lbl_t = QLabel(title)
            lbl_t.setFont(QFont(DesignTokens.FONT_MAIN, 10))
            lbl_t.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")
            lbl_v = QLabel("--")
            lbl_v.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
            lbl_v.setStyleSheet(f"color: {icon_color}; border: none; background: transparent;")
            c_lay.addWidget(ico)
            c_lay.addWidget(lbl_t)
            c_lay.addWidget(lbl_v)
            return chip, lbl_v

        chip_docs, self.lbl_kpi_docs_val = _make_kpi_chip("ph.files", DesignTokens.COLOR_BLUE, "Documents")
        chip_cov, self.lbl_kpi_coverage_val = _make_kpi_chip("ph.target", DesignTokens.COLOR_GREEN, "Couverture")
        chip_orphans, self.lbl_kpi_orphans_val = _make_kpi_chip("ph.warning-circle", DesignTokens.COLOR_YELLOW, "Sections orphelines")
        chip_cards, self.lbl_kpi_cards_val = _make_kpi_chip("ph.lightning", DesignTokens.COLOR_PURPLE, "Cartes forgées")

        kpi_layout.addWidget(chip_docs)
        kpi_layout.addWidget(chip_cov)
        kpi_layout.addWidget(chip_orphans)
        kpi_layout.addWidget(chip_cards)
        kpi_layout.addStretch()

        grid_page_layout.addWidget(kpi_header)

        # 2. Barre de Filtres et Recherche
        filter_bar = QFrame()
        filter_bar.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        f_outer = QVBoxLayout(filter_bar)
        f_outer.setContentsMargins(12, 8, 12, 8)
        f_outer.setSpacing(6)

        row1 = QHBoxLayout()
        row1.setSpacing(8)

        self.search_input = GlowLineEdit()
        self.search_input.setPlaceholderText("Rechercher un document ou cours...")
        self.search_input.setMinimumWidth(220)
        self.search_input.textChanged.connect(self.refresh_data)

        self.status_combo = QComboBox()
        self.status_combo.addItems(["Tous les statuts", "Couverts à 100%", "Trous à forger (<100%)", "Non indexés"])
        self.status_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 4px 8px;
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)
        self.status_combo.currentIndexChanged.connect(self.refresh_data)

        self.sort_combo = QComboBox()
        self.sort_combo.addItems(
            [
                "Taux de couverture ↓",
                "Taux de couverture ↑",
                "Nombre de cartes ↓",
                "Sections orphelines ↓",
                "Nom du fichier (A-Z)",
                "Date d'importation ↓",
            ]
        )
        self.sort_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 4px 8px;
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)
        self.sort_combo.currentIndexChanged.connect(self.refresh_data)

        self.btn_refresh = SecondaryButton("Actualiser")
        self.btn_refresh.setIcon(load_phosphor_icon("ph.arrows-clockwise", color=DesignTokens.TEXT_PRIMARY))
        self.btn_refresh.clicked.connect(self.refresh_data)

        row1.addWidget(self.search_input, 1)
        row1.addWidget(self.status_combo)
        row1.addWidget(self.sort_combo)
        row1.addWidget(self.btn_refresh)
        f_outer.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(6)

        lbl_filter = QLabel("Formats :")
        lbl_filter.setFont(QFont(DesignTokens.FONT_MAIN, 10, QFont.Weight.Bold))
        lbl_filter.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")
        row2.addWidget(lbl_filter)

        self.btn_filter_all = SecondaryButton("Tous")
        self.btn_filter_pdf = SecondaryButton("PDF")
        self.btn_filter_md = SecondaryButton("Markdown")
        self.btn_filter_web = SecondaryButton("Web & Vidéo")
        self.current_format_filter = "all"

        self.format_buttons = {
            "all": self.btn_filter_all,
            "pdf": self.btn_filter_pdf,
            "md": self.btn_filter_md,
            "web": self.btn_filter_web,
        }

        for fmt, b in self.format_buttons.items():
            b.setFixedHeight(26)
            b.clicked.connect(lambda _, f=fmt: self._set_format_filter(f))
            row2.addWidget(b)

        row2.addStretch()

        self.btn_align_all = SecondaryButton("Synchroniser toutes les fiches")
        self.btn_align_all.setIcon(load_phosphor_icon("ph.link", color=DesignTokens.COLOR_BLUE))
        self.btn_align_all.setFixedHeight(26)
        self.btn_align_all.setStyleSheet(f"font-size: 11px; padding: 2px 8px; border: 1px solid {DesignTokens.BORDER_COLOR};")
        self.btn_align_all.setToolTip("Associer via les tags de traçabilité les fiches Anki à l'ensemble des cours importés")
        self.btn_align_all.clicked.connect(self._on_align_all_sources)
        row2.addWidget(self.btn_align_all)

        f_outer.addLayout(row2)

        grid_page_layout.addWidget(filter_bar)

        # 3. Grille des Cartes de Documents (colonnes responsive)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("background: transparent;")

        self.grid_content = QWidget()
        self.grid_content.setStyleSheet("background: transparent;")
        self.grid_content.setMinimumWidth(0)
        self.grid_content.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.grid_layout = QGridLayout(self.grid_content)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setSpacing(12)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.scroll_area.setWidget(self.grid_content)
        grid_page_layout.addWidget(self.scroll_area, 1)

        self._doc_cards = []
        self._document_columns = 0
        self.scroll_area.viewport().installEventFilter(self)

        self.refresh_data()

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self.refresh_data)
        self._on_coverage_synced = self._handle_coverage_synced
        event_bus.subscribe(CoverageSyncedEvent, self._on_coverage_synced)
        self.destroyed.connect(lambda: event_bus.unsubscribe(CoverageSyncedEvent, self._on_coverage_synced))

    def _handle_coverage_synced(self, event: CoverageSyncedEvent) -> None:
        def _schedule() -> None:
            self._refresh_timer.start(250)

        run_on_owner_thread(self, _schedule)

    @property
    def document_column_count(self) -> int:
        """Nombre de colonnes actuellement retenues pour la grille des documents."""
        return self._document_columns

    def _columns_for_width(self, available_width: int) -> int:
        """Colonnes tenant dans `available_width` px sans carte trop étroite.

        On descend à une colonne unique dès que deux cartes ne peuvent plus recevoir
        chacune `MIN_CARD_WIDTH` px : sous ce seuil, les lignes de statistiques et le
        pied de carte seraient tronqués.
        """
        if available_width <= 0:
            return 1
        fitting = available_width // (self.MIN_CARD_WIDTH + self.grid_layout.spacing())
        return max(1, min(fitting, self.MAX_DOCUMENT_COLUMNS))

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """Recalcule les colonnes quand la largeur utile du viewport change."""
        if watched is self.scroll_area.viewport() and event.type() == QEvent.Type.Resize:
            self._place_doc_cards()
        return super().eventFilter(watched, event)

    def _place_doc_cards(self) -> None:
        """Repositionne les cartes existantes selon la colonne disponible."""
        columns = self._columns_for_width(self.scroll_area.viewport().width())
        if columns == self._document_columns:
            return
        self._document_columns = columns
        while self.grid_layout.count():
            self.grid_layout.takeAt(0)
        for index, card in enumerate(self._doc_cards):
            self.grid_layout.addWidget(card, index // columns, index % columns)

    def _set_format_filter(self, fmt: str) -> None:
        self.current_format_filter = fmt
        self.refresh_data()

    def refresh_data(self) -> None:
        from ankiforge.ui.components.linter_widgets import SourceDiagnosticCardWidget

        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._doc_cards = []

        docs = list(DocumentModel.select())
        search_text = self.search_input.text().strip().lower()

        docs_data = []
        total_forge_chunks = 0
        total_forge_covered = 0
        total_forge_orphans = 0
        total_forge_cards = 0

        for doc in docs:
            ext = (doc.file_type or "md").lower()
            title = doc.original_media.original_name if doc.original_media else doc.title

            chunks = list(doc.chunks)
            doc_repo = DocumentRepository()
            stats = doc_repo.get_coverage_stats(doc.id)
            total_units = stats.get("total_units", len(chunks))
            covered_units = stats.get("covered_units", 0)
            orphan_units_count = max(0, total_units - covered_units)
            total_cards = stats.get("total_cards", 0)
            coverage_pct = stats.get("coverage_pct", 0.0)
            density = (total_cards / total_units) if total_units > 0 else 0.0
            is_indexed = total_units > 0
            word_count = getattr(doc, "word_count", None) or (len(doc.content.split()) if doc.content else 0)

            total_forge_chunks += total_units
            total_forge_covered += covered_units
            total_forge_orphans += orphan_units_count
            total_forge_cards += total_cards

            total_chunks = total_units
            covered_chunks = covered_units
            orphan_chunks = orphan_units_count

            if self.current_format_filter != "all":
                if self.current_format_filter == "pdf" and ext != "pdf":
                    continue
                if self.current_format_filter == "md" and ext not in ("md", "markdown"):
                    continue
                if self.current_format_filter == "web" and ext not in ("web", "yt", "youtube"):
                    continue

            if search_text and search_text not in title.lower():
                continue

            status_idx = self.status_combo.currentIndex()
            if status_idx == 1 and (not is_indexed or coverage_pct < 100) or status_idx == 2 and (not is_indexed or orphan_chunks == 0) or status_idx == 3 and is_indexed:
                continue

            docs_data.append(
                {
                    "doc_id": doc.id,
                    "extension": ext,
                    "title": title,
                    "coverage_pct": coverage_pct,
                    "is_indexed": is_indexed,
                    "total_chunks": total_chunks,
                    "covered_chunks": covered_chunks,
                    "orphan_chunks": orphan_chunks,
                    "total_cards": total_cards,
                    "density": density,
                    "word_count": word_count,
                    "created_at": getattr(doc, "created_at", None),
                }
            )

        self.lbl_kpi_docs_val.setText(f"{len(docs)}")
        avg_cov = (total_forge_covered / total_forge_chunks * 100) if total_forge_chunks > 0 else 0.0
        self.lbl_kpi_coverage_val.setText(f"{avg_cov:.0f}%")
        self.lbl_kpi_orphans_val.setText(f"{total_forge_orphans}")
        self.lbl_kpi_cards_val.setText(f"{total_forge_cards}")

        sort_idx = self.sort_combo.currentIndex()
        if sort_idx == 0:
            docs_data.sort(key=lambda d: d["coverage_pct"], reverse=True)
        elif sort_idx == 1:
            docs_data.sort(key=lambda d: d["coverage_pct"])
        elif sort_idx == 2:
            docs_data.sort(key=lambda d: d["total_cards"], reverse=True)
        elif sort_idx == 3:
            docs_data.sort(key=lambda d: d["orphan_chunks"], reverse=True)
        elif sort_idx == 4:
            docs_data.sort(key=lambda d: d["title"].lower())
        elif sort_idx == 5:
            docs_data.sort(key=lambda d: str(d["created_at"]), reverse=True)

        self._doc_cards = [SourceDiagnosticCardWidget(data) for data in docs_data]
        for card in self._doc_cards:
            card.inspect_requested.connect(self.show_inspector)
        # Force le recalcul : le nombre de colonnes dépend de la largeur courante.
        self._document_columns = 0
        self._place_doc_cards()

    def _on_card_forge_orphan_requested(self, doc_id: int) -> None:
        doc = DocumentModel.get_or_none(DocumentModel.id == doc_id)
        if not doc:
            return

        chunks = list(DocumentChunkModel.select().where(DocumentChunkModel.document == doc).order_by(DocumentChunkModel.chunk_index))
        linked_chunk_ids = {link.chunk_id for link in NoteChunkLinkModel.select(NoteChunkLinkModel.chunk_id).join(DocumentChunkModel).where(DocumentChunkModel.document == doc)}

        orphan = next((c for c in chunks if c.id not in linked_chunk_ids), None)
        if orphan:
            section_name = orphan.heading_path or (f"Page {orphan.page_number}" if orphan.page_number else f"Section #{orphan.chunk_index + 1}")
            self.request_navigation.emit(
                "creation",
                {
                    "doc_id": doc.id,
                    "text_source": orphan.content,
                    "source_title": f"{doc.title} - {section_name}",
                    "chunk_id": orphan.id,
                    "page_number": orphan.page_number,
                },
            )
        else:
            show_toast(self, "Toutes les sections de ce cours sont déjà couvertes !")

    def _on_card_reindex_requested(self, doc_id: int) -> None:
        from ankiforge.services.workers.coverage_worker import CoverageWorker

        show_toast(self, "Indexation FAISS en cours...")
        self._coverage_worker = CoverageWorker(doc_id)
        self._coverage_worker.finished_processing.connect(self.refresh_data)
        self._coverage_worker.start()

    @Slot()
    def _on_align_all_sources(self) -> None:
        from ankiforge.services.audit.coverage_alignment_service import CoverageAlignmentService

        show_toast(self, "Synchronisation des fiches Anki pour l'ensemble des cours...")
        res = CoverageAlignmentService.align_all_documents()
        total_matched = res.get("total_matched_links", 0)
        self.refresh_data()
        show_toast(self, f"✅ {total_matched} fiches Anki synchronisées via les tags sur l'ensemble des cours !")

    def show_inspector(self, doc_id: int) -> None:
        while self.page_inspector.layout().count():
            item = self.page_inspector.layout().takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        panel = DocumentInspectorPanel(doc_id, self)
        panel.back_requested.connect(lambda: self.stack.setCurrentIndex(0))
        panel.request_navigation.connect(self.request_navigation)
        self.page_inspector.layout().addWidget(panel)
        self.stack.setCurrentIndex(1)
