"""
Éditeur Visuel Interactif d'Occlusion d'Images (Image Occlusion).
Canevas graphique QGraphicsView & QGraphicsScene permettant d'afficher l'image source,
d'ajouter, déplacer, redimensionner ou supprimer des masques SVG et de générer les cartes Anki.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import QPointF, QRectF, QSizeF, Qt, Signal, Slot
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QFont,
    QImage,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFrame,
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSceneHoverEvent,
    QGraphicsSceneMouseEvent,
    QGraphicsView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import DeckModel
from ankiforge.services.cards.image_occlusion_service import (
    ImageOcclusionService,
    OcclusionBox,
)
from ankiforge.services.workers.image_occlusion_worker import ImageOcclusionDetectionWorker
from ankiforge.ui.components import (
    IconButton,
    PrimaryButton,
    SecondaryButton,
    StyledComboBox,
)
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)

HANDLE_SIZE = 8.0


class OcclusionGraphicsItem(QGraphicsRectItem):
    """
    Rectangle d'occlusion interactif sur le canevas QGraphicsScene.
    Supporte le déplacement, la sélection et le redimensionnement via 4 poignées d'angle.
    """

    def __init__(
        self,
        box: OcclusionBox,
        on_change_cb: Any = None,
        parent: QGraphicsItem | None = None,
    ) -> None:
        super().__init__(QRectF(box.x, box.y, box.width, box.height), parent)
        self.box = box
        self.on_change_cb = on_change_cb

        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)

        self._active_handle: str | None = None
        self._press_rect: QRectF = self.rect()
        self._press_pos: QPointF = QPointF()

    def sync_from_box(self) -> None:
        """Met à jour le rectangle graphique depuis les données de l'OcclusionBox."""
        self.setRect(QRectF(self.box.x, self.box.y, self.box.width, self.box.height))
        self.update()

    def sync_to_box(self) -> None:
        """Met à jour l'OcclusionBox depuis la position et taille réelles."""
        r = self.rect()
        # Coordonnées dans la scène (en pixels d'image)
        pos = self.pos()
        self.box.x = round(pos.x() + r.x(), 1)
        self.box.y = round(pos.y() + r.y(), 1)
        self.box.width = round(r.width(), 1)
        self.box.height = round(r.height(), 1)

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.sync_to_box()
            if self.on_change_cb:
                self.on_change_cb(self.box)
        return super().itemChange(change, value)

    def _get_handles(self) -> dict[str, QRectF]:
        r = self.rect()
        s = HANDLE_SIZE
        hs = s / 2.0
        return {
            "tl": QRectF(r.left() - hs, r.top() - hs, s, s),
            "tr": QRectF(r.right() - hs, r.top() - hs, s, s),
            "bl": QRectF(r.left() - hs, r.bottom() - hs, s, s),
            "br": QRectF(r.right() - hs, r.bottom() - hs, s, s),
        }

    def _handle_at(self, point: QPointF) -> str | None:
        if not self.isSelected():
            return None
        for name, rect in self._get_handles().items():
            if rect.contains(point):
                return name
        return None

    def hoverMoveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        handle = self._handle_at(event.pos())
        if handle in ("tl", "br"):
            self.setCursor(QCursor(Qt.CursorShape.SizeFDiagCursor))
        elif handle in ("tr", "bl"):
            self.setCursor(QCursor(Qt.CursorShape.SizeBDiagCursor))
        else:
            self.setCursor(QCursor(Qt.CursorShape.SizeAllCursor if self.isSelected() else Qt.CursorShape.PointingHandCursor))
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self._handle_at(event.pos())
            if handle:
                self._active_handle = handle
                self._press_rect = self.rect()
                self._press_pos = event.pos()
                event.accept()
                return
        self._active_handle = None
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self._active_handle:
            delta = event.pos() - self._press_pos
            r = QRectF(self._press_rect)

            if self._active_handle == "br":
                r.setRight(max(r.left() + 10.0, r.right() + delta.x()))
                r.setBottom(max(r.top() + 10.0, r.bottom() + delta.y()))
            elif self._active_handle == "bl":
                r.setLeft(min(r.right() - 10.0, r.left() + delta.x()))
                r.setBottom(max(r.top() + 10.0, r.bottom() + delta.y()))
            elif self._active_handle == "tr":
                r.setRight(max(r.left() + 10.0, r.right() + delta.x()))
                r.setTop(min(r.bottom() - 10.0, r.top() + delta.y()))
            elif self._active_handle == "tl":
                r.setLeft(min(r.right() - 10.0, r.left() + delta.x()))
                r.setTop(min(r.bottom() - 10.0, r.top() + delta.y()))

            self.setRect(r.normalized())
            self.sync_to_box()
            if self.on_change_cb:
                self.on_change_cb(self.box)
            self.update()
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        self._active_handle = None
        self.sync_to_box()
        if self.on_change_cb:
            self.on_change_cb(self.box)
        super().mouseReleaseEvent(event)

    def paint(self, painter: QPainter, option: Any, widget: QWidget | None = None) -> None:
        r = self.rect()
        is_sel = self.isSelected()

        # Couleurs stylisées
        fill_color = QColor("#e11d48") if is_sel else QColor("#f59e0b")
        fill_color.setAlpha(180 if is_sel else 160)
        border_color = QColor("#be123c") if is_sel else QColor("#d97706")

        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(QBrush(fill_color))
        painter.setPen(QPen(border_color, 2.0 if is_sel else 1.5))
        painter.drawRoundedRect(r, 4.0, 4.0)

        # Badge numéroté [ID]
        badge_text = f"[{self.box.id}]"
        badge_font = QFont("-apple-system", 9, QFont.Weight.Bold)
        painter.setFont(badge_font)
        painter.setPen(QPen(QColor("#ffffff")))
        painter.drawText(r, Qt.AlignmentFlag.AlignCenter, badge_text)

        # Poignées de redimensionnement si sélectionné
        if is_sel:
            painter.setBrush(QBrush(QColor("#ffffff")))
            painter.setPen(QPen(QColor("#be123c"), 1.5))
            for h_rect in self._get_handles().values():
                painter.drawRect(h_rect)


class OcclusionCanvasView(QGraphicsView):
    """Canevas interactif basé sur QGraphicsView pour la manipulation fluide des masques."""

    box_created = Signal(float, float, float, float)  # (x, y, w, h)
    selection_changed = Signal()

    def __init__(self, scene: QGraphicsScene, parent: QWidget | None = None) -> None:
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(QBrush(QColor(DesignTokens.BG_MAIN)))
        self.setFrameShape(QFrame.Shape.NoFrame)

        self._draw_mode = False
        self._is_drawing = False
        self._start_pos: QPointF = QPointF()
        self._rubber_item: QGraphicsRectItem | None = None

        self.scene().selectionChanged.connect(self.selection_changed.emit)

    def set_draw_mode(self, enabled: bool) -> None:
        self._draw_mode = enabled
        if enabled:
            self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
        else:
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._draw_mode and event.button() == Qt.MouseButton.LeftButton:
            self._is_drawing = True
            self._start_pos = self.mapToScene(event.pos())
            self._rubber_item = QGraphicsRectItem(QRectF(self._start_pos, QSizeF(0, 0)))
            self._rubber_item.setPen(QPen(QColor("#e11d48"), 2.0, Qt.PenStyle.DashLine))
            self._rubber_item.setBrush(QBrush(QColor(225, 29, 72, 60)))
            self.scene().addItem(self._rubber_item)
            event.accept()
            return

        # Clic molette ou Espace pour panoramique
        if event.button() == Qt.MouseButton.MiddleButton or (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._is_drawing and self._rubber_item:
            current_pos = self.mapToScene(event.pos())
            rect = QRectF(self._start_pos, current_pos).normalized()
            self._rubber_item.setRect(rect)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._is_drawing and self._rubber_item:
            self._is_drawing = False
            rect = self._rubber_item.rect()
            self.scene().removeItem(self._rubber_item)
            self._rubber_item = None

            if rect.width() >= 10 and rect.height() >= 10:
                self.box_created.emit(rect.x(), rect.y(), rect.width(), rect.height())

            event.accept()
            return

        if self.dragMode() == QGraphicsView.DragMode.ScrollHandDrag:
            self.setDragMode(QGraphicsView.DragMode.NoDrag if self._draw_mode else QGraphicsView.DragMode.RubberBandDrag)

        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Zoom fluide centré sur le curseur avec la molette."""
        zoom_in_factor = 1.15
        zoom_out_factor = 1.0 / zoom_in_factor

        if event.angleDelta().y() > 0:
            self.scale(zoom_in_factor, zoom_in_factor)
        else:
            self.scale(zoom_out_factor, zoom_out_factor)
        event.accept()


class ImageOcclusionEditor(QWidget):
    """
    Éditeur visuel interactif complet de masquage d'images (Image Occlusion).
    Offre un canevas graphique, une barre d'outils, la détection IA et un panneau de configuration.
    """

    notes_created = Signal(list)  # list[NoteModel]

    def __init__(
        self,
        image_path: str | Path | None = None,
        service: ImageOcclusionService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.service = service or ImageOcclusionService()
        self.image_path: Path | None = Path(image_path) if image_path else None
        self.boxes: list[OcclusionBox] = []

        self._raw_image: QImage | None = None
        self._pixmap_item: QGraphicsPixmapItem | None = None
        self._graphics_items: dict[int, OcclusionGraphicsItem] = {}
        self._worker: ImageOcclusionDetectionWorker | None = None

        self.scene = QGraphicsScene(self)
        self.canvas_view = OcclusionCanvasView(self.scene, self)

        self._setup_ui()
        if self.image_path and self.image_path.exists():
            self.load_image(self.image_path)

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── 1. Barre d'outils supérieure ─────────────────────────────────────
        top_bar = QFrame()
        top_bar.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
            }}
        """)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(10, 8, 10, 8)
        top_layout.setSpacing(8)

        # Mode Pointeur
        self.btn_select = IconButton("ph.cursor", tooltip="Mode Sélection / Déplacement", size=26)
        self.btn_select.clicked.connect(lambda: self._set_tool_mode("select"))
        top_layout.addWidget(self.btn_select)

        # Mode Tracé de masque
        self.btn_draw = IconButton("ph.bounding-box", tooltip="Mode Tracé : cliquer-glisser pour créer un masque", size=26)
        self.btn_draw.clicked.connect(lambda: self._set_tool_mode("draw"))
        top_layout.addWidget(self.btn_draw)

        # Supprimer le masque sélectionné
        self.btn_delete = IconButton("ph.trash", tooltip="Supprimer le masque sélectionné (Suppr)", size=26)
        self.btn_delete.clicked.connect(self._delete_selected_box)
        top_layout.addWidget(self.btn_delete)

        top_layout.addSpacing(12)

        # Bouton Détection IA
        self.btn_ai_detect = SecondaryButton("Détecter avec l'IA")
        self.btn_ai_detect.setIcon(load_phosphor_icon("ph.sparkle", color=DesignTokens.ACCENT_PRIMARY))
        self.btn_ai_detect.setToolTip("Détecte automatiquement toutes les annotations et légendes via Vision IA")
        self.btn_ai_detect.clicked.connect(self._on_ai_detect_clicked)
        top_layout.addWidget(self.btn_ai_detect)

        # Indicateur de chargement IA
        self.ai_spinner = QProgressBar()
        self.ai_spinner.setRange(0, 0)
        self.ai_spinner.setFixedWidth(80)
        self.ai_spinner.setFixedHeight(16)
        self.ai_spinner.setVisible(False)
        top_layout.addWidget(self.ai_spinner)

        top_layout.addStretch()

        # Contrôles de zoom
        self.btn_zoom_out = IconButton("ph.magnifying-glass-minus", tooltip="Zoom arrière", size=26)
        self.btn_zoom_out.clicked.connect(lambda: self.canvas_view.scale(0.85, 0.85))
        top_layout.addWidget(self.btn_zoom_out)

        self.btn_zoom_reset = IconButton("ph.arrows-out-simple", tooltip="Ajuster à l'écran", size=26)
        self.btn_zoom_reset.clicked.connect(self._fit_to_view)
        top_layout.addWidget(self.btn_zoom_reset)

        self.btn_zoom_in = IconButton("ph.magnifying-glass-plus", tooltip="Zoom avant", size=26)
        self.btn_zoom_in.clicked.connect(lambda: self.canvas_view.scale(1.15, 1.15))
        top_layout.addWidget(self.btn_zoom_in)

        main_layout.addWidget(top_bar)

        # ── 2. Corps Principal : Splitter Canevas / Panneau Latéral ──────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background-color: {DesignTokens.BORDER_COLOR};
                width: 1px;
            }}
        """)

        # Canevas Graphique QGraphicsScene & QGraphicsView
        self.canvas_view.box_created.connect(self._on_box_drawn)
        self.canvas_view.selection_changed.connect(self._on_canvas_selection_changed)
        splitter.addWidget(self.canvas_view)

        # Panneau latéral droit
        side_panel = QWidget()
        side_panel.setMinimumWidth(320)
        side_panel.setMaximumWidth(420)
        side_panel.setStyleSheet(f"background-color: {DesignTokens.BG_PANEL};")
        side_layout = QVBoxLayout(side_panel)
        side_layout.setContentsMargins(14, 14, 14, 14)
        side_layout.setSpacing(12)

        # En-tête du panneau
        lbl_panel_title = QLabel("Masques & Légendes")
        lbl_panel_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: bold; font-size: 13px;")
        side_layout.addWidget(lbl_panel_title)

        # Tableau des masques
        self.table_boxes = QTableWidget()
        self.table_boxes.setColumnCount(3)
        self.table_boxes.setHorizontalHeaderLabels(["#", "Texte / Réponse", "Indice"])
        self.table_boxes.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table_boxes.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table_boxes.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.table_boxes.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_boxes.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table_boxes.itemChanged.connect(self._on_table_item_changed)
        self.table_boxes.itemSelectionChanged.connect(self._on_table_selection_changed)
        self.table_boxes.setStyleSheet(f"""
            QTableWidget {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                color: {DesignTokens.TEXT_PRIMARY};
                gridline-color: {DesignTokens.BORDER_COLOR};
            }}
            QHeaderView::section {{
                background-color: {DesignTokens.BG_PANEL};
                color: {DesignTokens.TEXT_MUTED};
                border: none;
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
                padding: 4px 6px;
                font-size: 11px;
                font-weight: bold;
            }}
        """)
        side_layout.addWidget(self.table_boxes)

        # Options pédagogiques d'occlusion
        lbl_mode = QLabel("Mode d'occlusion :")
        lbl_mode.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        side_layout.addWidget(lbl_mode)

        self.combo_mode = StyledComboBox()
        self.combo_mode.addItem("Masquer tout, révéler un (Hide All)", "hide_all")
        self.combo_mode.addItem("Masquer un, révéler un (Hide One)", "hide_one")
        side_layout.addWidget(self.combo_mode)

        self.chk_keep_other_masks = QCheckBox("Garder les autres masques fermés au verso")
        self.chk_keep_other_masks.setChecked(True)
        self.chk_keep_other_masks.setToolTip("Évite les fuites d'indices contextuels : en mode Hide All, les autres étiquettes restent masquées lors de l'affichage de la réponse.")
        self.chk_keep_other_masks.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px;")
        side_layout.addWidget(self.chk_keep_other_masks)

        # Paquet Anki de destination
        lbl_deck = QLabel("Paquet cible :")
        lbl_deck.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        side_layout.addWidget(lbl_deck)

        self.combo_deck = StyledComboBox()
        self._populate_decks()
        side_layout.addWidget(self.combo_deck)

        # En-tête / Titre du schéma
        lbl_header = QLabel("Titre de la carte (En-tête) :")
        lbl_header.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        side_layout.addWidget(lbl_header)

        self.txt_header = QLineEdit()
        self.txt_header.setPlaceholderText("Ex: Anatomie de l'Œil - Coupe sagittale")
        self.txt_header.setStyleSheet(f"""
            QLineEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                color: {DesignTokens.TEXT_PRIMARY};
                padding: 6px 8px;
            }}
        """)
        side_layout.addWidget(self.txt_header)

        # Tags
        lbl_tags = QLabel("Tags (séparés par des virgules) :")
        lbl_tags.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        side_layout.addWidget(lbl_tags)

        self.txt_tags = QLineEdit("image-occlusion")
        self.txt_tags.setStyleSheet(f"""
            QLineEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                color: {DesignTokens.TEXT_PRIMARY};
                padding: 6px 8px;
            }}
        """)
        side_layout.addWidget(self.txt_tags)

        # Bouton principal de génération
        self.btn_generate = PrimaryButton("Créer les cartes d'occlusion")
        self.btn_generate.setIcon(load_phosphor_icon("ph.check-circle", color="#ffffff"))
        self.btn_generate.clicked.connect(self._generate_cards)
        side_layout.addWidget(self.btn_generate)

        splitter.addWidget(side_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        main_layout.addWidget(splitter)

        # Mode initial
        self._set_tool_mode("select")

    def _populate_decks(self) -> None:
        """Charge la liste des paquets Anki en base."""
        self.combo_deck.clear()
        try:
            decks = list(DeckModel.select().order_by(DeckModel.name))
            if not decks:
                default_deck = DeckModel.create(name="Défaut")
                decks = [default_deck]

            for d in decks:
                self.combo_deck.addItem(f"📦 {d.name}", d.id)
        except Exception as err:
            logger.debug("Erreur lors de la lecture des paquets : %s", err)

    def load_image(self, image_path: str | Path) -> None:
        """Charge une image source sur le canevas."""
        self.image_path = Path(image_path)
        if not self.image_path.exists():
            show_toast(self, "Fichier image introuvable", is_error=True)
            return

        self._raw_image = QImage(str(self.image_path))
        if self._raw_image.isNull():
            show_toast(self, "Format d'image non reconnu ou illisible", is_error=True)
            return

        # Nettoyage de la scène
        self.scene.clear()
        self._graphics_items.clear()
        self.boxes.clear()

        # Image de fond
        pixmap = QPixmap.fromImage(self._raw_image)
        self._pixmap_item = self.scene.addPixmap(pixmap)
        self._pixmap_item.setZValue(0)
        self.scene.setSceneRect(0, 0, pixmap.width(), pixmap.height())

        # Définition du titre suggéré
        if not self.txt_header.text().strip():
            self.txt_header.setText(self.image_path.stem.replace("_", " ").title())

        self._refresh_table()
        self._fit_to_view()

    def _fit_to_view(self) -> None:
        """Ajuste le zoom de la vue à l'ensemble de l'image."""
        if self._pixmap_item:
            self.canvas_view.fitInView(self._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

    def _set_tool_mode(self, mode: str) -> None:
        """Bascule entre le mode sélection et le mode tracé de masques."""
        is_draw = mode == "draw"
        self.canvas_view.set_draw_mode(is_draw)
        self.btn_select.setStyleSheet(f"background-color: {DesignTokens.BG_HOVER}; border: 1px solid {DesignTokens.ACCENT_PRIMARY};" if not is_draw else "")
        self.btn_draw.setStyleSheet(f"background-color: {DesignTokens.BG_HOVER}; border: 1px solid {DesignTokens.ACCENT_PRIMARY};" if is_draw else "")

    def _on_box_drawn(self, x: float, y: float, w: float, h: float) -> None:
        """Crée une nouvelle boîte après tracé manuel à la souris."""
        new_id = (max([b.id for b in self.boxes], default=0)) + 1
        box = OcclusionBox(
            id=new_id,
            x=round(x, 1),
            y=round(y, 1),
            width=round(w, 1),
            height=round(h, 1),
            text="",
            hint="",
        )
        self.boxes.append(box)
        self._add_box_item(box)
        self._refresh_table()
        self._select_box_by_id(new_id)

    def _add_box_item(self, box: OcclusionBox) -> None:
        """Ajoute l'élément graphique interactif sur la scène."""
        item = OcclusionGraphicsItem(box, on_change_cb=self._on_box_geometry_changed)
        item.setZValue(10)
        self.scene.addItem(item)
        self._graphics_items[box.id] = item

    def _on_box_geometry_changed(self, box: OcclusionBox) -> None:
        """Met à jour les données lorsqu'un masque est déplacé ou redimensionné."""
        self._update_table_row_for_box(box)

    def _on_canvas_selection_changed(self) -> None:
        """Synchronise la sélection du canevas vers le tableau latéral."""
        selected_items = [it for it in self.scene.selectedItems() if isinstance(it, OcclusionGraphicsItem)]
        if selected_items:
            active_box = selected_items[0].box
            for row in range(self.table_boxes.rowCount()):
                item = self.table_boxes.item(row, 0)
                if item and int(item.text()) == active_box.id:
                    self.table_boxes.blockSignals(True)
                    self.table_boxes.selectRow(row)
                    self.table_boxes.blockSignals(False)
                    break
        else:
            self.table_boxes.blockSignals(True)
            self.table_boxes.clearSelection()
            self.table_boxes.blockSignals(False)

    def _on_table_selection_changed(self) -> None:
        """Synchronise la sélection du tableau vers le canevas graphique."""
        sel_ranges = self.table_boxes.selectedRanges()
        if not sel_ranges:
            return

        row = sel_ranges[0].topRow()
        id_item = self.table_boxes.item(row, 0)
        if not id_item:
            return

        box_id = int(id_item.text())
        self._select_box_by_id(box_id)

    def _select_box_by_id(self, box_id: int) -> None:
        """Sélectionne et centre le rectangle spécifié."""
        self.scene.blockSignals(True)
        for item in self.scene.items():
            if isinstance(item, OcclusionGraphicsItem):
                item.setSelected(item.box.id == box_id)
        self.scene.blockSignals(False)

    def _delete_selected_box(self) -> None:
        """Supprime le ou les masques actuellement sélectionnés."""
        selected_items = [it for it in self.scene.selectedItems() if isinstance(it, OcclusionGraphicsItem)]
        if not selected_items:
            return

        for item in selected_items:
            box_id = item.box.id
            self.scene.removeItem(item)
            self._graphics_items.pop(box_id, None)
            self.boxes = [b for b in self.boxes if b.id != box_id]

        # Ré-indexation propre
        for i, box in enumerate(self.boxes, start=1):
            old_id = box.id
            box.id = i
            if old_id in self._graphics_items:
                g_item = self._graphics_items.pop(old_id)
                g_item.box = box
                self._graphics_items[i] = g_item
                g_item.update()

        self._refresh_table()

    def _refresh_table(self) -> None:
        """Recharge l'intégralité du tableau latéral."""
        self.table_boxes.blockSignals(True)
        self.table_boxes.setRowCount(len(self.boxes))

        for row, box in enumerate(self.boxes):
            # ID
            item_id = QTableWidgetItem(str(box.id))
            item_id.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            item_id.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table_boxes.setItem(row, 0, item_id)

            # Texte
            item_text = QTableWidgetItem(box.text)
            self.table_boxes.setItem(row, 1, item_text)

            # Indice
            item_hint = QTableWidgetItem(box.hint)
            self.table_boxes.setItem(row, 2, item_hint)

        self.table_boxes.blockSignals(False)
        self.btn_generate.setText(f"Créer {len(self.boxes)} cartes d'occlusion")

    def _update_table_row_for_box(self, box: OcclusionBox) -> None:
        """Met à jour une ligne du tableau lors d'une modification géométrique."""
        for row in range(self.table_boxes.rowCount()):
            item = self.table_boxes.item(row, 0)
            if item and int(item.text()) == box.id:
                # Synchronisé
                break

    def _on_table_item_changed(self, item: QTableWidgetItem) -> None:
        """Répercute les modifications de texte/indice du tableau sur l'OcclusionBox."""
        row = item.row()
        id_item = self.table_boxes.item(row, 0)
        if not id_item:
            return

        box_id = int(id_item.text())
        box = next((b for b in self.boxes if b.id == box_id), None)
        if not box:
            return

        col = item.column()
        if col == 1:
            box.text = item.text().strip()
        elif col == 2:
            box.hint = item.text().strip()

    def _on_ai_detect_clicked(self) -> None:
        """Déclenche la détection IA de vision en arrière-plan."""
        if not self.image_path or not self.image_path.exists():
            show_toast(self, "Aucune image chargée pour la détection", is_error=True)
            return

        self.btn_ai_detect.setEnabled(False)
        self.ai_spinner.setVisible(True)
        show_toast(self, "Analyse de vision par l'IA en cours...", is_error=False)

        self._worker = ImageOcclusionDetectionWorker(
            image_path=self.image_path,
            service=self.service,
            parent=self,
        )
        self._worker.finished_signal.connect(self._on_ai_detection_finished)
        self._worker.error_signal.connect(self._on_ai_detection_error)
        self._worker.start()

    @Slot(list)
    def _on_ai_detection_finished(self, boxes: list[OcclusionBox]) -> None:
        """Traite les boîtes détectées par l'IA."""
        self.btn_ai_detect.setEnabled(True)
        self.ai_spinner.setVisible(False)

        if not boxes:
            show_toast(self, "Aucune étiquette détectée par l'IA sur cette image", is_error=False)
            return

        # Remplacement ou ajout
        for item in self._graphics_items.values():
            self.scene.removeItem(item)
        self._graphics_items.clear()

        self.boxes = boxes
        for box in self.boxes:
            self._add_box_item(box)

        self._refresh_table()
        show_toast(self, f"✓ {len(boxes)} légendes détectées par l'IA !", is_error=False)

    @Slot(str)
    def _on_ai_detection_error(self, error_msg: str) -> None:
        """Gère les erreurs de l'analyse visuelle."""
        self.btn_ai_detect.setEnabled(True)
        self.ai_spinner.setVisible(False)
        show_toast(self, f"Erreur Vision : {error_msg}", is_error=True)

    def _generate_cards(self) -> None:
        """Génère les cartes d'occlusion en base de données et dans le paquet cible."""
        if not self.image_path or not self.image_path.exists():
            show_toast(self, "Image source introuvable", is_error=True)
            return

        if not self.boxes:
            show_toast(self, "Ajoutez au moins un masque d'occlusion avant de créer des cartes.", is_error=False)
            return

        deck_id = self.combo_deck.currentData()
        if not deck_id:
            show_toast(self, "Veuillez sélectionner un paquet de destination.", is_error=False)
            return

        mode = self.combo_mode.currentData()
        keep_other = self.chk_keep_other_masks.isChecked()
        header = self.txt_header.text().strip()

        raw_tags = self.txt_tags.text().split(",")
        tags = [t.strip() for t in raw_tags if t.strip()]

        try:
            created_notes = self.service.create_occlusion_notes(
                image_path=self.image_path,
                boxes=self.boxes,
                deck_id=int(deck_id),
                header=header,
                mode=mode,
                keep_other_masks_on_answer=keep_other,
                tags=tags,
            )

            show_toast(self, f"✓ {len(created_notes)} cartes d'occlusion créées avec succès !", is_error=False)
            self.notes_created.emit(created_notes)

        except Exception as err:
            logger.exception("Échec de la génération des cartes d'occlusion : %s", err)
            show_toast(self, f"Erreur de création : {err}", is_error=True)

    def keyPressEvent(self, event: Any) -> None:
        """Raccourci clavier Suppr pour effacer le masque sélectionné."""
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and not isinstance(self.focusWidget(), QLineEdit):
            self._delete_selected_box()
            event.accept()
            return
        super().keyPressEvent(event)
