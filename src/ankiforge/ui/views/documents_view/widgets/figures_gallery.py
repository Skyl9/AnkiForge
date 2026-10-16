"""Onglet « Figures » de l'Inspecteur : la galerie des figures d'un document.

L'onglet lit la **couture visuelle** (`VisualPayloadResolver`) au lieu d'interroger la base
lui-même — une seule règle décide de ce qu'est une figure — et n'écrit **aucune provenance** :
il se contente d'émettre ``occlusion_requested`` pour le fragment choisi. L'appelant (la vue
Documents) possède le contexte documentaire et écrit la provenance
(`CoverageAlignmentService.attach_notes_to_source`, ADR 0023).

Le rendu des vignettes passe par la plaque hors thread GUI (`request_media_thumbnail`, dérivée
de la plaque d'album du ticket S1) : décoder une figure native sur le thread GUI gèlerait
l'interface, exactement comme tourner une planche.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import DocumentChunkModel, DocumentModel
from ankiforge.services.cards.visual_resolver import VisualPayloadResolver
from ankiforge.ui.components import Badge, EmptyStateWidget, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.views.documents_view.widgets.album_thumbnails import (
    request_media_thumbnail,
)
from ankiforge.utils.i18n import tr
from ankiforge.utils.icon_loader import load_phosphor_icon

#: Côté de la vignette d'une figure (plafonné avant transformation par la plaque).
FIGURE_THUMB_PX = 132


class FigureCard(QFrame):
    """Carte d'une figure : vignette, légende et bouton d'action Image Occlusion."""

    occlusion_requested = Signal(int)  # chunk_id

    def __init__(
        self,
        chunk: DocumentChunkModel,
        thumb_px: int = FIGURE_THUMB_PX,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.chunk_id = int(chunk.id)
        self.setObjectName("figureCard")
        self.setStyleSheet(f"""
            QFrame#figureCard {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.thumb = QLabel(self.tr("Chargement…"))
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb.setFixedHeight(thumb_px)
        self.thumb.setStyleSheet(f"background-color: {DesignTokens.BG_MAIN}; border: none; color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        layout.addWidget(self.thumb)

        caption = chunk.heading_path or (f"Page {chunk.page_number}" if chunk.page_number else f"Fragment #{chunk.chunk_index}")
        self.caption_lbl = QLabel(caption)
        self.caption_lbl.setWordWrap(True)
        self.caption_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; border: none;")
        layout.addWidget(self.caption_lbl)

        self.btn_occlude = SecondaryButton(
            "Image Occlusion",
            tooltip=self.tr("Forger des cartes de masquage depuis cette figure"),
        )
        self.btn_occlude.setIcon(load_phosphor_icon("ph.bounding-box", color=DesignTokens.TEXT_PRIMARY))
        self.btn_occlude.clicked.connect(lambda: self.occlusion_requested.emit(self.chunk_id))
        layout.addWidget(self.btn_occlude)

        #: Référence forte : un QPixmap nul se lit comme « vignette absente », sans erreur.
        self._pixmap: QPixmap | None = None

    @Slot(int, int, object)
    def set_thumbnail(self, media_id: int, size_px: int, image: QImage) -> None:
        """Reçoit la vignette prête (livrée sur le thread GUI par la plaque)."""
        if image is None or image.isNull():
            return
        pixmap = QPixmap.fromImage(image)
        self._pixmap = pixmap
        self.thumb.setPixmap(pixmap)

    @Slot(int, str)
    def mark_failed(self, media_id: int, message: str) -> None:
        """Signale une vignette indisponible sans laisser la carte sur « Chargement… »."""
        self.thumb.setText(self.tr("Figure indisponible"))


class FiguresGalleryWidget(QWidget):
    """Galerie des figures d'un document, en colonne (l'Inspecteur fait 250–320 px).

    Émet ``occlusion_requested(chunk_id)`` : la vue décide quoi en faire. La portée est
    « section courante » par défaut, avec bascule « tout le document ».
    """

    occlusion_requested = Signal(int)  # chunk_id

    def __init__(
        self,
        parent: QWidget | None = None,
        resolver: VisualPayloadResolver | None = None,
    ) -> None:
        super().__init__(parent)
        self._resolver = resolver or VisualPayloadResolver()
        self._document: DocumentModel | None = None
        self._heading_path: str | None = None
        self._whole_document = False
        #: Les callbacks de la plaque peuvent être livrés après la construction : on garde
        #: les tasks vivantes le temps du rendu (leur QRunnable est auto-supprimé).
        self._tasks: list[object] = []

        self._build_ui()

    # ── Construction ────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(6)
        self.scope_check = QCheckBox(self.tr("Tout le document"))
        self.scope_check.toggled.connect(self._on_scope_toggled)
        header.addWidget(self.scope_check)
        header.addStretch()
        self.count_badge = Badge(self.tr("0 figure"), variant="neutral")
        header.addWidget(self.count_badge)
        layout.addLayout(header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(8)
        self.cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.cards_container)
        layout.addWidget(self.scroll, 1)

    # ── API ─────────────────────────────────────────────────────────────────────

    def load(
        self,
        document: DocumentModel | None,
        heading_path: str | None,
        whole_document: bool | None = None,
    ) -> None:
        """Change le document et la portée, puis rafraîchit la galerie.

        Args:
            document: Le document courant, ou ``None`` pour vider la galerie.
            heading_path: La section courante (``None`` = aucune section ⇒ tout le document).
            whole_document: Force l'état de la bascule ; ``None`` le laisse inchangé.
        """
        self._document = document
        self._heading_path = heading_path
        if whole_document is not None:
            self._whole_document = whole_document

        self.scope_check.blockSignals(True)
        self.scope_check.setChecked(self._whole_document or heading_path is None)
        self.scope_check.blockSignals(False)
        self.refresh()

    def refresh(self) -> None:
        """Reconstruit la galerie depuis la couture visuelle."""
        self._clear_cards()

        document = self._document
        if document is None:
            self._show_empty(
                "ph.images",
                self.tr("Aucun document sélectionné"),
                self.tr("Sélectionnez un document dans l'explorateur."),
            )
            return

        if (document.file_type or "").lower() == "album":
            self._show_empty(
                "ph.images",
                self.tr("Document album"),
                self.tr("Les planches d'un album s'inspectent depuis la vue Album."),
            )
            return

        scope_heading = None if self._whole_document else self._heading_path
        figures = self._resolver.list_document_figures(document.id, scope_heading)
        if not figures:
            self._show_empty_state(document.id, scope_heading)
            return

        self.count_badge.setText(tr("%1 figure(s)", len(figures)))
        for chunk in figures:
            card = FigureCard(chunk)
            card.occlusion_requested.connect(self.occlusion_requested)
            self.cards_layout.addWidget(card)

            media_id = int(chunk.media_id) if chunk.media_id is not None else -1
            path = self._resolver.figure_media_path(chunk)
            if path is None:
                card.mark_failed(media_id, "fichier absent")
                continue
            task = request_media_thumbnail(
                media_id=media_id,
                file_path=path,
                size_px=FIGURE_THUMB_PX,
                on_ready=card.set_thumbnail,
                on_failed=card.mark_failed,
            )
            self._tasks.append(task)

    # ── Interne ─────────────────────────────────────────────────────────────────

    def _on_scope_toggled(self, checked: bool) -> None:
        self._whole_document = checked
        self.refresh()

    def _clear_cards(self) -> None:
        # Les tasks ne sont plus référencées : leurs signaux, s'ils arrivent, viseront des
        # cartes supprimées (Qt déconnecte automatiquement à la destruction).
        self._tasks.clear()
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _show_empty_state(self, document_id: int, scope_heading: str | None) -> None:
        total = DocumentChunkModel.select().where(DocumentChunkModel.document == document_id).count()
        if total == 0:
            self._show_empty(
                "ph.database",
                self.tr("Document non indexé"),
                self.tr("Structurez ou indexez le document pour révéler ses figures."),
            )
        elif scope_heading:
            self._show_empty(
                "ph.bounding-box",
                self.tr("Aucune figure dans cette section"),
                self.tr("Activez « Tout le document » pour voir les autres sections."),
            )
        else:
            self._show_empty(
                "ph.bounding-box",
                self.tr("Aucune figure"),
                self.tr("Ce document ne contient aucune illustration liée à un fragment."),
            )

    def _show_empty(self, icon_name: str, title: str, description: str) -> None:
        self.count_badge.setText(self.tr("0 figure"))
        self.cards_layout.addWidget(EmptyStateWidget(icon_name=icon_name, title=title, description=description))
