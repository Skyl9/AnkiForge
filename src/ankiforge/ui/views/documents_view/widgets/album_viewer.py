from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from PySide6.QtCore import QPoint, QRect, Qt, Signal, Slot
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QImage,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QPixmap,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import DocumentModel, DocumentPageModel
from ankiforge.services.ai.album_transcription_types import AlbumTranscriptionOptions
from ankiforge.services.ai.vision_category_service import VisionCategoryService
from ankiforge.services.cards.album_service import AlbumService
from ankiforge.services.workers.album_worker import AlbumOCRWorker, AlbumPDFWorker
from ankiforge.ui.components import (
    Badge,
    IconButton,
    PrimaryButton,
    SecondaryButton,
)
from ankiforge.ui.components.flow_layout import FlowLayout
from ankiforge.ui.components.vision_capability import VISION_UNSUPPORTED_LABEL
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.views.documents_view.widgets.album_thumbnails import (
    ThumbnailTask,
    request_thumbnail,
)
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.i18n import tr
from ankiforge.utils.icon_loader import load_on_accent_icon, load_phosphor_icon

logger = logging.getLogger(__name__)


class AlbumPageCard(QFrame):
    """
    Carte de vignette individuelle pour une page d'album dans la planche-contact.
    Affiche la miniature, le numéro de page, le statut OCR et une barre d'actions rapides.

    La vignette est rendue **hors du thread GUI** (ticket S1) : la carte ne fait que
    déclencher une demande et afficher le résultat. Elle ne lit jamais le fichier de la
    planche, et n'applique pas la rotation elle-même — l'orientation vient de la couture.
    """

    rotate_requested = Signal(int)  # page_id
    move_requested = Signal(int, int)  # page_id, direction (-1 ou +1)
    delete_requested = Signal(int)  # page_id
    inspect_requested = Signal(int)  # page_id

    #: Côté utile de la vignette, en pixels logiques. Sert de plafond : la carte ne
    #: demande jamais plus grand que ce qu'elle peut afficher.
    THUMBNAIL_PX = 180

    def __init__(
        self,
        page: DocumentPageModel,
        parent: QWidget | None = None,
        album_service: AlbumService | None = None,
    ) -> None:
        super().__init__(parent)
        self.page = page
        self._album_service = album_service or AlbumService()
        self._thumb_task: ThumbnailTask | None = None
        self.setFixedWidth(200)
        self.setFixedHeight(270)
        self.setObjectName("albumPageCard")

        self.setStyleSheet(f"""
            QFrame#albumPageCard {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
            QFrame#albumPageCard:hover {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # ── En-tête : Badge Numéro de Page & Statut OCR ──────────────────────
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)

        self.page_badge = Badge(f"P. {page.page_number}", variant="neutral")
        header_layout.addWidget(self.page_badge)

        self.crop_badge = Badge(tr("Recadrée"), variant="info")
        self.crop_badge.setVisible(bool(getattr(page, "crop_data", None)))
        header_layout.addWidget(self.crop_badge)

        header_layout.addStretch()

        self.ocr_badge = Badge("", variant="neutral")
        header_layout.addWidget(self.ocr_badge)
        self.update_status(page.ocr_text, page.status)

        layout.addLayout(header_layout)

        # ── Miniature Image ──────────────────────────────────────────────────
        self.img_lbl = QLabel()
        self.img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.img_lbl.setStyleSheet(f"""
            QLabel {{
                background-color: {DesignTokens.BG_INPUT};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        self.img_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        self.img_lbl.mousePressEvent = lambda e: self.inspect_requested.emit(self.page.id)
        layout.addWidget(self.img_lbl, 1)

        self._request_thumbnail()

        # ── Barre d'actions rapides (Bas de carte) ───────────────────────────
        actions_layout = QHBoxLayout()
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(2)

        self.btn_left = IconButton("ph.caret-left", tooltip=self.tr("Déplacer vers la gauche (page précédente)"), size=22)
        self.btn_left.clicked.connect(lambda: self.move_requested.emit(self.page.id, -1))

        self.btn_right = IconButton("ph.caret-right", tooltip=self.tr("Déplacer vers la droite (page suivante)"), size=22)
        self.btn_right.clicked.connect(lambda: self.move_requested.emit(self.page.id, 1))

        self.btn_rotate = IconButton("ph.arrow-clockwise", tooltip=self.tr("Tourner de 90°"), size=22)
        self.btn_rotate.clicked.connect(lambda: self.rotate_requested.emit(self.page.id))

        self.btn_inspect = IconButton("ph.arrow-square-out", tooltip=self.tr("Inspecter la page"), size=22)
        self.btn_inspect.clicked.connect(lambda: self.inspect_requested.emit(self.page.id))

        self.btn_delete = IconButton("ph.trash", tooltip=self.tr("Supprimer cette page"), size=22)
        self.btn_delete.clicked.connect(lambda: self.delete_requested.emit(self.page.id))

        actions_layout.addWidget(self.btn_left)
        actions_layout.addWidget(self.btn_right)
        actions_layout.addStretch()
        actions_layout.addWidget(self.btn_rotate)
        actions_layout.addWidget(self.btn_inspect)
        actions_layout.addWidget(self.btn_delete)

        layout.addLayout(actions_layout)

    def _request_thumbnail(self) -> None:
        """
        Demande la vignette à la plaque de rendu (hors thread GUI).

        Le plafond demandé est la taille utile de la carte, jamais la résolution native :
        un scan A4 à 300 dpi ferait 2500×3500 px, et c'est précisément ce chargement-là
        qui gelait la grille.
        """
        device_ratio = self.devicePixelRatioF() if hasattr(self, "devicePixelRatioF") else 1.0
        wanted = max(1, int(self.THUMBNAIL_PX * (device_ratio or 1.0)))
        self.img_lbl.setText(self.tr("Chargement…"))
        self._thumb_task = request_thumbnail(
            self.page,
            wanted,
            on_ready=self._on_thumbnail_ready,
            on_failed=self._on_thumbnail_failed,
            album_service=self._album_service,
        )

    @Slot(int, int, object)
    def _on_thumbnail_ready(self, page_id: int, _size_px: int, image: object) -> None:
        """Affiche la vignette rendue. La conversion en `QPixmap` se fait ici, sur le thread GUI."""
        if page_id != self.page.id or not isinstance(image, QImage) or image.isNull():
            return
        self.img_lbl.setPixmap(QPixmap.fromImage(image))

    @Slot(int, str)
    def _on_thumbnail_failed(self, page_id: int, message: str) -> None:
        if page_id != self.page.id:
            return
        self.img_lbl.setPixmap(QPixmap())
        self.img_lbl.setText(self.tr("Aperçu indisponible"))
        self.img_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        logger.warning("Vignette indisponible pour la planche %d : %s", page_id, message)

    def update_crop_status(self, crop_data: str | None = None) -> None:
        """Met à jour l'affichage du badge de recadrage."""
        active_crop = crop_data if crop_data is not None else getattr(self.page, "crop_data", None)
        self.crop_badge.setVisible(bool(active_crop))

    def update_status(self, ocr_text: str, status: str | None = None) -> None:
        """
        Met à jour le badge de statut de transcription.

        Un état dérivé **périmé** se dit : la planche a changé, sa transcription
        précédente décrit une orientation qui n'est plus la sienne. Le silence laisserait
        croire à un contenu valide — un état faux sans témoin.
        """
        self.page.ocr_text = ocr_text
        self.update_crop_status()
        active_status = status if status is not None else getattr(self.page, "status", "ready")

        if active_status == "stale":
            self.ocr_badge.setText(self.tr("Périmé"))
            self.ocr_badge.set_variant("warning")
            self.ocr_badge.setToolTip(self.tr("La planche a changé depuis sa transcription : retranscrivez-la pour la mettre à jour."))
            return

        has_ocr = bool(ocr_text and ocr_text.strip())
        self.ocr_badge.setText("✓ OCR" if has_ocr else "Non transcrit")
        self.ocr_badge.set_variant("success" if has_ocr else "neutral")
        self.ocr_badge.setToolTip(f"{len(ocr_text.split())} mots extraits" if has_ocr else "Aucune transcription")


class CropImageLabel(QLabel):
    """
    QLabel interactif pour la sélection rectangulaire de recadrage.
    En mode recadrage, permet de tracer une zone de sélection à la souris avec retour visuel.
    """

    selection_changed = Signal(QRect)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._crop_mode: bool = False
        self._selecting: bool = False
        self._start_pos: QPoint | None = None
        self._selection_rect: QRect = QRect()

    @property
    def is_crop_mode(self) -> bool:
        return self._crop_mode

    def set_crop_mode(self, enabled: bool) -> None:
        self._crop_mode = enabled
        self._selecting = False
        self._selection_rect = QRect()
        if enabled:
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.unsetCursor()
        self.update()

    def set_selection_rect(self, rect: QRect) -> None:
        self._selection_rect = rect
        self.update()

    def reset_selection(self) -> None:
        self._selecting = False
        self._selection_rect = QRect()
        self.update()

    def get_selection_rect(self) -> QRect:
        return self._selection_rect

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._crop_mode and event.button() == Qt.MouseButton.LeftButton:
            self._selecting = True
            self._start_pos = event.pos()
            self._selection_rect = QRect(self._start_pos, self._start_pos)
            self.update()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._crop_mode and self._selecting and self._start_pos is not None:
            self._selection_rect = QRect(self._start_pos, event.pos()).normalized()
            self.selection_changed.emit(self._selection_rect)
            self.update()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._crop_mode and self._selecting and event.button() == Qt.MouseButton.LeftButton and self._start_pos is not None:
            self._selecting = False
            self._selection_rect = QRect(self._start_pos, event.pos()).normalized()
            self.selection_changed.emit(self._selection_rect)
            self.update()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        if self._crop_mode and not self._selection_rect.isNull() and self._selection_rect.isValid():
            painter = QPainter(self)
            # Voile semi-transparent
            painter.fillRect(self.rect(), QColor(0, 0, 0, 90))
            # Découpe transparente de la zone sélectionnée
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(self._selection_rect, Qt.GlobalColor.transparent)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            # Bordure en pointillés accentuée
            pen = QPen(QColor(DesignTokens.ACCENT_PRIMARY), 2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawRect(self._selection_rect)
            painter.end()


class PageInspectorWidget(QWidget):
    """
    Vue détaillée et zoomable pour inspecter une planche et retoucher son texte OCR.

    L'orientation affichée vient de la couture de lecture (ADR 0011), jamais d'une
    transformation locale : deux chemins d'orientation ne peuvent pas diverger.
    """

    close_requested = Signal()
    page_saved = Signal(int, str)  # page_id, ocr_text
    navigate_requested = Signal(int)  # delta (-1 pour précédent, +1 pour suivant)
    rotate_requested = Signal(int)  # page_id
    page_crop_changed = Signal(int)  # page_id

    #: Plafond du rendu d'inspection. Au-delà, on charge la planche native — ce que le
    #: ticket S1 interdit hors d'une demande de zoom explicite.
    INSPECTION_PX = 2048

    def __init__(self, parent: QWidget | None = None, album_service: AlbumService | None = None) -> None:
        super().__init__(parent)
        self.current_page: DocumentPageModel | None = None
        self._total_pages: int = 1
        self._album_service = album_service or AlbumService()
        self._raw_pixmap: QPixmap | None = None
        self._full_pixmap: QPixmap | None = None
        self._zoom_factor: float = 1.0
        #: Vrai quand `_zoom_factor` est calculé par ajustement à la fenêtre plutôt que posé.
        self._zoom_is_fit: bool = False

        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Barre d'outils supérieure de l'inspecteur ─────────────────────────
        top_bar = QFrame()
        top_bar.setObjectName("inspectorTopBar")
        top_bar.setStyleSheet(f"""
            QFrame#inspectorTopBar {{
                background-color: {DesignTokens.BG_PANEL};
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
            }}
        """)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(10, 8, 10, 8)
        top_layout.setSpacing(8)

        self.btn_back = SecondaryButton("Planche-contact")
        self.btn_back.setIcon(load_phosphor_icon("ph.squares-four", color=DesignTokens.TEXT_PRIMARY))
        self.btn_back.clicked.connect(self.close_requested.emit)
        top_layout.addWidget(self.btn_back)

        self.lbl_title = QLabel(self.tr("Inspecteur de page"))
        self.lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: bold; font-size: 14px;")
        top_layout.addWidget(self.lbl_title)

        self.crop_badge = Badge(tr("Recadrée"), variant="info")
        self.crop_badge.setVisible(False)
        top_layout.addWidget(self.crop_badge)

        top_layout.addStretch()

        # Navigation entre pages
        self.btn_prev = IconButton("ph.caret-left", tooltip=self.tr("Page précédente"), size=26)
        self.btn_prev.clicked.connect(lambda: self.navigate_requested.emit(-1))
        top_layout.addWidget(self.btn_prev)

        self.btn_next = IconButton("ph.caret-right", tooltip=self.tr("Page suivante"), size=26)
        self.btn_next.clicked.connect(lambda: self.navigate_requested.emit(1))
        top_layout.addWidget(self.btn_next)

        # Rotation
        self.btn_rotate = IconButton("ph.arrow-clockwise", tooltip=self.tr("Tourner de 90°"), size=26)
        self.btn_rotate.clicked.connect(self._on_rotate_clicked)
        top_layout.addWidget(self.btn_rotate)

        # Recadrage
        self.btn_crop = IconButton("ph.selection", tooltip=self.tr("Recadrer la planche"), size=26)
        self.btn_crop.clicked.connect(self._on_start_crop)
        top_layout.addWidget(self.btn_crop)

        self.btn_remove_crop = IconButton("ph.selection-slash", tooltip=self.tr("Retirer le recadrage (restituer la planche intégrale)"), size=26)
        self.btn_remove_crop.clicked.connect(self._on_remove_crop)
        self.btn_remove_crop.setVisible(False)
        top_layout.addWidget(self.btn_remove_crop)

        # Contrôles de zoom
        self.btn_zoom_out = IconButton("ph.magnifying-glass-minus", tooltip=self.tr("Zoom arrière"), size=26)
        self.btn_zoom_out.clicked.connect(self._on_zoom_out)
        top_layout.addWidget(self.btn_zoom_out)

        self.btn_zoom_reset = IconButton("ph.arrows-out-simple", tooltip=self.tr("Ajuster à la fenêtre"), size=26)
        self.btn_zoom_reset.clicked.connect(self._on_zoom_reset)
        top_layout.addWidget(self.btn_zoom_reset)

        self.btn_zoom_in = IconButton("ph.magnifying-glass-plus", tooltip=self.tr("Zoom avant"), size=26)
        self.btn_zoom_in.clicked.connect(self._on_zoom_in)
        top_layout.addWidget(self.btn_zoom_in)

        # Bouton Image Occlusion IA
        self.btn_occlusion = SecondaryButton("Image Occlusion")
        self.btn_occlusion.setIcon(load_phosphor_icon("ph.bounding-box", color=DesignTokens.ACCENT_PRIMARY))
        self.btn_occlusion.setToolTip(self.tr("Créer des masques d'Image Occlusion sur cette page avec l'IA"))
        self.btn_occlusion.clicked.connect(self._on_open_image_occlusion)
        top_layout.addWidget(self.btn_occlusion)

        main_layout.addWidget(top_bar)

        # ── Bandeau d'actions du mode recadrage (sous la top bar) ────────────
        self.crop_banner = QFrame()
        self.crop_banner.setObjectName("cropBanner")
        self.crop_banner.setStyleSheet(f"""
            QFrame#cropBanner {{
                background-color: {DesignTokens.BG_PANEL};
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
            }}
        """)
        crop_banner_layout = QHBoxLayout(self.crop_banner)
        crop_banner_layout.setContentsMargins(12, 6, 12, 6)
        crop_banner_layout.setSpacing(8)

        lbl_crop_hint = QLabel(self.tr("Mode recadrage : tracez un rectangle sur l'image pour borner la zone à conserver."))
        lbl_crop_hint.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px;")
        crop_banner_layout.addWidget(lbl_crop_hint)

        crop_banner_layout.addStretch()

        self.btn_apply_crop = PrimaryButton("Valider le recadrage")
        self.btn_apply_crop.setIcon(load_on_accent_icon("ph.check"))
        self.btn_apply_crop.setFixedHeight(28)
        self.btn_apply_crop.clicked.connect(self._on_apply_crop)
        crop_banner_layout.addWidget(self.btn_apply_crop)

        self.btn_cancel_crop = SecondaryButton("Annuler")
        self.btn_cancel_crop.setIcon(load_phosphor_icon("ph.x", color=DesignTokens.TEXT_PRIMARY))
        self.btn_cancel_crop.setFixedHeight(28)
        self.btn_cancel_crop.clicked.connect(self._on_cancel_crop)
        crop_banner_layout.addWidget(self.btn_cancel_crop)

        self.crop_banner.setVisible(False)
        main_layout.addWidget(self.crop_banner)

        # ── Corps Principal : Splitter Image / Transcription OCR ─────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background-color: {DesignTokens.BORDER_COLOR};
                width: 1px;
            }}
        """)

        # Volet Gauche : Visualiseur d'image scrollable
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setStyleSheet(f"""
            QScrollArea {{
                background-color: {DesignTokens.BG_MAIN};
                border: none;
            }}
        """)

        self.image_display = CropImageLabel()
        self.image_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setWidget(self.image_display)
        splitter.addWidget(self.scroll_area)

        # Volet Droit : Panneau de Transcription OCR
        ocr_panel = QWidget()
        ocr_panel.setMinimumWidth(300)
        ocr_panel.setMaximumWidth(450)
        ocr_layout = QVBoxLayout(ocr_panel)
        ocr_layout.setContentsMargins(12, 12, 12, 12)
        ocr_layout.setSpacing(8)

        ocr_header = QHBoxLayout()
        lbl_ocr_title = QLabel(self.tr("Transcription OCR & Notes"))
        lbl_ocr_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: bold; font-size: 13px;")
        ocr_header.addWidget(lbl_ocr_title)
        ocr_header.addStretch()

        self.btn_save_ocr = PrimaryButton("Enregistrer")
        self.btn_save_ocr.setIcon(load_on_accent_icon("ph.floppy-disk"))
        self.btn_save_ocr.setFixedHeight(28)
        self.btn_save_ocr.setStyleSheet("font-size: 11px; padding: 4px 10px;")
        self.btn_save_ocr.clicked.connect(self._on_save_ocr)
        ocr_header.addWidget(self.btn_save_ocr)
        ocr_layout.addLayout(ocr_header)

        # L'inspecteur montre aussi l'état périmé : l'utilisateur y passe pour corriger
        # une transcription, et corriger un texte qui décrit une orientation abandonnée
        # revient à recopier une erreur. Le bandeau reste donc visible, pas une infobulle.
        self.stale_notice = QLabel(self.tr("Transcription périmée : la planche a changé depuis. Retranscrivez cette page pour la mettre à jour."))
        self.stale_notice.setWordWrap(True)
        self.stale_notice.setVisible(False)
        self.stale_notice.setStyleSheet(f"""
            QLabel {{
                background-color: {DesignTokens.COLOR_YELLOW_BG};
                color: {DesignTokens.COLOR_YELLOW_TEXT};
                border: 1px solid {DesignTokens.COLOR_YELLOW};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 6px 8px;
                font-size: 11px;
            }}
        """)
        ocr_layout.addWidget(self.stale_notice)

        self.ocr_text_edit = QTextEdit()
        self.ocr_text_edit.setPlaceholderText(self.tr("Aucun texte transcrit pour cette page. Lancez la transcription par Vision IA ou saisissez vos notes ici."))
        self.ocr_text_edit.setStyleSheet(f"""
            QTextEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-family: {DesignTokens.FONT_MAIN};
                font-size: 12px;
                padding: 8px;
            }}
            QTextEdit:focus {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        ocr_layout.addWidget(self.ocr_text_edit, 1)

        splitter.addWidget(ocr_panel)
        splitter.setSizes([650, 350])

        main_layout.addWidget(splitter, 1)

    def load_page(self, page: DocumentPageModel, total_pages: int) -> None:
        """
        Affiche la planche spécifiée dans l'inspecteur.

        L'image vient de la couture : elle porte donc l'orientation de la planche. Le
        rendu est plafonné (`INSPECTION_PX`) — la pleine résolution n'est rechargée que
        lorsqu'un zoom le demande explicitement.
        """
        self._total_pages = total_pages
        self.current_page = page
        self.lbl_title.setText(tr("Page %1 sur %2", page.page_number, total_pages))
        self.ocr_text_edit.setPlainText(page.ocr_text or "")
        self.stale_notice.setVisible(getattr(page, "status", None) == "stale")
        self._full_pixmap = None
        self._zoom_factor = 1.0
        self._zoom_is_fit = True
        self._raw_pixmap = None

        # Sortie du mode recadrage
        self.crop_banner.setVisible(False)
        self.image_display.set_crop_mode(False)

        has_crop = bool(getattr(page, "crop_data", None))
        self.crop_badge.setVisible(has_crop)
        self.btn_remove_crop.setVisible(has_crop)

        try:
            image = self._album_service.render_page_qimage(page, max_size=self._inspection_px())
        except FileNotFoundError as e:
            logger.warning("Planche %d sans image : %s", page.id, e)
        except (UnidentifiedImageError, OSError) as e:
            # Une planche corrompue ou tronquée n'est pas une raison de fermer l'inspecteur :
            # les autres planches de l'album restent consultables. Sans ce filet, l'exception
            # remontait jusqu'au slot Qt et la navigation s'interrompait sur la planche.
            logger.warning("Planche %d illisible : %s", page.id, e)
        else:
            self._raw_pixmap = QPixmap.fromImage(image)

        # Le facteur est calculé ici, pas seulement au redimensionnement : lever le
        # drapeau « ajusté » sans calculer l'échelle laissait la planche à 100 % tant
        # que l'utilisateur n'aurait pas redimensionné la fenêtre — l'ajustement
        # annoncé ne s'exécutait donc pas à l'ouverture.
        self._zoom_factor = self._fit_zoom_factor()
        self._apply_image_transformations()

    def _device_ratio(self) -> float:
        """Densité d'écran du widget, normalisée à 1.0 quand elle est inconnue ou nulle."""
        ratio = self.devicePixelRatioF() if hasattr(self, "devicePixelRatioF") else 1.0
        return ratio if ratio and ratio > 0 else 1.0

    def _viewport_size(self) -> tuple[int, int]:
        """
        Taille du viewport en pixels **logiques**.

        La densité d'écran ne passe pas par ici, et c'est délibéré. Elle sert à *décoder*
        assez de pixels (`_inspection_px`), jamais à *dimensionner* : un `QPixmap` sans
        `devicePixelRatio` est mis en page par Qt en pixels logiques, donc une échelle
        calculée sur des pixels physiques produisait une image deux fois trop large sur
        un écran Retina — l'ajustement à la fenêtre échouait précisément là où il se voit.
        """
        size = self.image_display.size()
        return max(1, size.width()), max(1, size.height())

    def _inspection_px(self) -> int:
        """Plafond de rendu de l'inspecteur, en pixels physiques (donc plus fin sur Retina)."""
        return max(1, int(self.INSPECTION_PX * self._device_ratio()))

    def _fit_zoom_factor(self) -> float:
        """
        Facteur d'ajustement à la fenêtre : la plus grande échelle tenant dans le viewport.

        C'est ce que « ajuster à la fenêtre » promettait. Poser 1.0 — 100 % de la
        résolution native — ne réduit rien : sur une planche de 2500 px dans un widget de
        600 px, le bouton affichait hors champ et paraissait cassé.
        """
        if not self._raw_pixmap or self._raw_pixmap.isNull():
            return 1.0
        view_w, view_h = self._viewport_size()
        return min(view_w / self._raw_pixmap.width(), view_h / self._raw_pixmap.height())

    def _native_max_px(self) -> int:
        """
        Plus grand côté de la planche **native**, sans la recharger.

        Décoder la planche entière pour mesurer ce qu'on sait déjà lire dans ses en-têtes
        PIL annulerait le plafond mis en place : c'est précisément le coût que
        `INSPECTION_PX` sert à éviter. On interroge donc le format, pas les pixels.
        """
        if not self.current_page:
            return 0
        try:
            media_path = self._album_service.page_media_path(self.current_page)
            with Image.open(media_path) as probe:
                return max(int(probe.width), int(probe.height))
        except (FileNotFoundError, UnidentifiedImageError, OSError) as e:
            logger.debug("Dimensions natives de la planche %s illisibles : %s", getattr(self.current_page, "id", "?"), e)
            return 0

    def _display_pixmap(self) -> QPixmap | None:
        """
        Pixmap servant de base à l'affichage, en chargeant la pleine résolution si le
        zoom la demande (au-delà de ce que le rendu plafonné contient).
        """
        if not self.current_page:
            return self._raw_pixmap
        if self._raw_pixmap is None or self._raw_pixmap.isNull():
            return self._raw_pixmap

        # La comparaison se fait sur la résolution **native**, pas sur la largeur du rendu
        # plafonné : comparer le besoin à l'image déjà réduite donnait « il faut plus gros »
        # pour une petite planche (facteur d'ajustement > 1) et déclenchait un décodage
        # pleine résolution sur le thread GUI — le gel que S1 existe pour supprimer.
        native_px = self._native_max_px()
        if native_px <= 0 or self._zoom_factor <= 1.0:
            return self._raw_pixmap
        if self._raw_pixmap.width() * self._zoom_factor >= native_px:
            return self._raw_pixmap

        if self._full_pixmap is None or self._full_pixmap.isNull():
            try:
                self._full_pixmap = self._album_service.render_page_pixmap(self.current_page)
            except FileNotFoundError as e:
                logger.warning("Planche %d sans image pour le zoom : %s", self.current_page.id, e)
                return self._raw_pixmap
        return self._full_pixmap

    def _apply_image_transformations(self) -> None:
        """Applique le zoom courant à l'image affichée."""
        if not self._raw_pixmap or self._raw_pixmap.isNull():
            self.image_display.setText(self.tr("Image non disponible"))
            self.image_display.setPixmap(QPixmap())
            return

        pix = self._display_pixmap()
        if pix is None or pix.isNull():
            self.image_display.setPixmap(QPixmap())
            return

        # Application du zoom
        target_w = int(pix.width() * self._zoom_factor)
        target_h = int(pix.height() * self._zoom_factor)
        scaled_pix = pix.scaled(
            max(50, target_w),
            max(50, target_h),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.image_display.setPixmap(scaled_pix)

    def _on_zoom_in(self) -> None:
        # Partir de l'ajustement courant : zoomer depuis « ajusté » plutôt que depuis 1.0
        # reste prévisible, et 100 % reste atteignable par zoom arrière.
        if self._zoom_is_fit:
            self._zoom_is_fit = False
        self._zoom_factor = min(4.0, self._zoom_factor * 1.2)
        self._apply_image_transformations()

    def _on_zoom_out(self) -> None:
        self._zoom_is_fit = False
        self._zoom_factor = max(0.05, self._zoom_factor / 1.2)
        self._apply_image_transformations()

    def _on_zoom_reset(self) -> None:
        """« Ajuster à la fenêtre » : la plus grande échelle tenant dans le viewport."""
        self._zoom_factor = self._fit_zoom_factor()
        self._zoom_is_fit = True
        self._apply_image_transformations()

    def resizeEvent(self, event: QResizeEvent) -> None:  # Nom imposé par Qt.
        """Recalcule l'ajustement à la fenêtre quand le viewport change de taille."""
        super().resizeEvent(event)
        if self._zoom_is_fit:
            self._zoom_factor = self._fit_zoom_factor()
            self._apply_image_transformations()

    def _on_rotate_clicked(self) -> None:
        if self.current_page:
            self.rotate_requested.emit(self.current_page.id)

    def _on_start_crop(self) -> None:
        """Active le mode de recadrage interactif."""
        if not self.current_page:
            return
        self.crop_banner.setVisible(True)
        # Afficher la planche intégrale non recadrée à la rotation courante
        try:
            image = self._album_service.render_page_qimage(self.current_page, max_size=self._inspection_px(), ignore_crop=True)
            self._raw_pixmap = QPixmap.fromImage(image)
        except Exception as e:
            logger.warning("Impossible de charger la planche intégrale pour recadrage : %s", e)
        self._zoom_factor = self._fit_zoom_factor()
        self._zoom_is_fit = True
        self._apply_image_transformations()
        self.image_display.set_crop_mode(True)

    def _on_cancel_crop(self) -> None:
        """Annule le mode de recadrage et recharge la page."""
        self.crop_banner.setVisible(False)
        self.image_display.set_crop_mode(False)
        if self.current_page:
            self.load_page(self.current_page, self._total_pages)

    def _on_apply_crop(self) -> None:
        """Calcule et enregistre le recadrage sur l'image source via la couture de service."""
        if not self.current_page:
            return
        sel_rect = self.image_display.get_selection_rect()
        pix = self.image_display.pixmap()
        if not pix or pix.isNull() or sel_rect.width() < 5 or sel_rect.height() < 5:
            show_toast(self, self.tr("Veuillez tracer un rectangle sur l'image pour borner la zone à conserver."), is_error=True)
            return

        offset_x = max(0, (self.image_display.width() - pix.width()) // 2)
        offset_y = max(0, (self.image_display.height() - pix.height()) // 2)

        sel_x1 = max(0, sel_rect.left() - offset_x)
        sel_y1 = max(0, sel_rect.top() - offset_y)
        sel_x2 = min(pix.width(), sel_rect.right() - offset_x)
        sel_y2 = min(pix.height(), sel_rect.bottom() - offset_y)

        sel_w = sel_x2 - sel_x1
        sel_h = sel_y2 - sel_y1
        if sel_w < 5 or sel_h < 5:
            show_toast(self, self.tr("Zone de recadrage trop petite."), is_error=True)
            return

        try:
            self._album_service.set_page_crop_from_view(
                self.current_page.id,
                (sel_x1, sel_y1, sel_w, sel_h),
                (pix.width(), pix.height()),
            )
        except Exception as e:
            logger.exception("Erreur lors du recadrage de la page %d : %s", self.current_page.id, e)
            show_toast(self, tr("Erreur lors du recadrage : %1", e), is_error=True)
            return

        self.crop_banner.setVisible(False)
        self.image_display.set_crop_mode(False)
        self.page_crop_changed.emit(self.current_page.id)
        show_toast(self, self.tr("Planche recadrée avec succès."))
        self.load_page(DocumentPageModel.get_by_id(self.current_page.id), self._total_pages)

    def _on_remove_crop(self) -> None:
        """Supprime le recadrage et restitue l'image source intégrale."""
        if not self.current_page:
            return
        self._album_service.remove_page_crop(self.current_page.id)
        self.page_crop_changed.emit(self.current_page.id)
        show_toast(self, self.tr("Recadrage retiré — planche intégrale restituée."))
        self.load_page(DocumentPageModel.get_by_id(self.current_page.id), self._total_pages)

    def _on_save_ocr(self) -> None:
        if not self.current_page:
            return
        text = self.ocr_text_edit.toPlainText().strip()
        self.current_page.ocr_text = text
        self.current_page.save()
        self.page_saved.emit(self.current_page.id, text)
        show_toast(self, self.tr("Transcription enregistrée avec succès."))

    def _on_open_image_occlusion(self) -> None:
        """
        Ouvre le dialogue Image Occlusion sur la planche **dans son orientation**.

        C'est le seul site où une donnée, et non un simple affichage, dépendait de
        l'orientation : les masques SVG sont cuits aux coordonnées relevées sur l'image
        fournie. Passer le fichier brut produisait des masques en rapport avec une image
        que l'utilisateur ne voit pas — une réponse à la mauvaise question, réutilisable
        en l'état dans les cartes.
        """
        if not self.current_page:
            return

        from ankiforge.ui.dialogs.image_occlusion_dialog import ImageOcclusionDialog

        with tempfile.TemporaryDirectory(prefix="ankiforge-occlusion-") as tmp_dir:
            # Le chemin du média vient lui aussi de la couture : ce dialogue consume une
            # donnée, et lire le fichier brut ici réintroduirait exactement le découplage
            # que la couture vient de supprimer (et que le test de garde interdit).
            media_path = self._album_service.page_media_path(self.current_page)
            suffix = media_path.suffix or ".png"
            # Le nom de la source est conservé : l'éditeur d'occlusion l'affiche en en-tête,
            # et « planche.jpg » pour tous les albums ne nommait rien.
            staged = Path(tmp_dir) / f"{media_path.stem}{suffix}"
            try:
                image = self._album_service.render_page_image(self.current_page)
            except (FileNotFoundError, UnidentifiedImageError, OSError) as e:
                logger.warning("Occlusion impossible : %s", e)
                show_toast(self, self.tr("Image de la planche illisible."), is_error=True)
                return
            try:
                from ankiforge.services.ai.ocr_service import save_rendered_page

                save_rendered_page(image, staged, suffix)
            finally:
                image.close()

            dialog = ImageOcclusionDialog(image_path=staged, parent=self.window())
            dialog.exec()


class AlbumViewerWidget(QWidget):
    """
    Composant central pour l'affichage, la manipulation et la transcription d'un Album d'images.
    Alterne entre la planche-contact (grille responsive) et l'inspecteur zoomable.
    """

    album_modified = Signal(int)  # document_id
    forge_requested = Signal(int)  # document_id
    visual_rag_requested = Signal(int)  # document_id
    search_rag_requested = Signal(int)  # document_id

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._doc: DocumentModel | None = None
        self._pages: list[DocumentPageModel] = []
        self._current_inspect_index: int = 0
        self._ocr_worker: AlbumOCRWorker | None = None
        self._pdf_worker: AlbumPDFWorker | None = None
        self._category_service = VisionCategoryService()
        self._album_service = AlbumService()
        self._selected_category_id: str = ""
        self._last_transcription_options: AlbumTranscriptionOptions | None = None
        self._failed_page_ids: list[int] = []

        self._setup_ui()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── 1. Barre d'actions supérieure de l'Album ──────────────────────────
        self.toolbar_card = QFrame()
        self.toolbar_card.setObjectName("albumToolbarCard")
        self.toolbar_card.setStyleSheet(f"""
            QFrame#albumToolbarCard {{
                background-color: {DesignTokens.BG_PANEL};
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
                border-top: none;
                border-left: none;
                border-right: none;
            }}
        """)
        toolbar_vlayout = QVBoxLayout(self.toolbar_card)
        toolbar_vlayout.setContentsMargins(12, 10, 12, 10)
        toolbar_vlayout.setSpacing(8)

        # Ligne 1 : Titre, compteur de pages et bouton principal de forge
        row1 = QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)
        row1.setSpacing(8)

        album_ico = QLabel()
        album_ico.setPixmap(load_phosphor_icon("ph.images", color=DesignTokens.COLOR_PURPLE).pixmap(20, 20))
        row1.addWidget(album_ico)

        self.lbl_album_title = QLabel(self.tr("Album d'images"))
        self.lbl_album_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 15px; font-weight: bold;")
        self.lbl_album_title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.lbl_album_title.setMinimumWidth(50)
        row1.addWidget(self.lbl_album_title, 1)

        self.pages_badge = Badge(tr("0 pages"), variant="neutral")
        row1.addWidget(self.pages_badge)

        self.btn_forge = PrimaryButton("Forger des cartes", tooltip=self.tr("Forger des cartes flash à partir des planches de cet album"))
        self.btn_forge.setIcon(load_on_accent_icon("ph.cards"))
        self.btn_forge.setFixedHeight(28)
        self.btn_forge.setStyleSheet("font-size: 11px; padding: 3px 12px;")
        self.btn_forge.clicked.connect(self._on_forge_clicked)
        row1.addWidget(self.btn_forge)

        toolbar_vlayout.addLayout(row1)

        # Ligne 2 : Barre d'actions responsive (FlowLayout)
        self.toolbar_container = QWidget()
        self.toolbar_flow_layout = FlowLayout(self.toolbar_container, margin=0, h_spacing=6, v_spacing=6)

        # Sélecteur de catégorie conservé pour compatibilité mais masqué de la barre (ADR 0012)
        self.combo_category = QComboBox()
        self.combo_category.setFixedWidth(180)
        self.combo_category.setFixedHeight(26)
        self.combo_category.setStyleSheet("font-size: 11px;")
        self.combo_category.setToolTip(self.tr("Catégorie de transcription : elle détermine le modèle de vision utilisé sur les planches"))
        self.combo_category.currentIndexChanged.connect(lambda _idx: self._on_category_changed())
        self.combo_category.setVisible(False)
        self.toolbar_flow_layout.addWidget(self.combo_category)

        self.btn_ocr = SecondaryButton("Transcrire l'album…")
        self.btn_ocr.setIcon(load_phosphor_icon("ph.sparkle", color=DesignTokens.COLOR_YELLOW))
        self.btn_ocr.setToolTip(self.tr("Configurer et lancer la transcription de l'album"))
        self.btn_ocr.setFixedHeight(26)
        self.btn_ocr.setStyleSheet(f"font-size: 11px; padding: 2px 8px; border: 1px solid {DesignTokens.BORDER_COLOR};")
        self.btn_ocr.clicked.connect(self._on_open_transcription_dialog)
        self.btn_open_transcription = self.btn_ocr
        self.toolbar_flow_layout.addWidget(self.btn_ocr)

        self.btn_rag = SecondaryButton("RAG Visuel")
        self.btn_rag.setIcon(load_phosphor_icon("ph.eye", color=DesignTokens.COLOR_GREEN))
        self.btn_rag.setToolTip(self.tr("Indexer les planches et schémas dans FAISS pour la recherche multimodale"))
        self.btn_rag.setFixedHeight(26)
        self.btn_rag.setStyleSheet(f"font-size: 11px; padding: 2px 8px; border: 1px solid {DesignTokens.BORDER_COLOR};")
        self.btn_rag.clicked.connect(lambda: self.visual_rag_requested.emit(self._doc.id) if self._doc else None)
        self.toolbar_flow_layout.addWidget(self.btn_rag)

        self.btn_search_rag = IconButton("ph.magnifying-glass", tooltip=self.tr("Recherche sémantique visuelle"), size=26)
        self.btn_search_rag.clicked.connect(lambda: self.search_rag_requested.emit(self._doc.id) if self._doc else None)
        self.toolbar_flow_layout.addWidget(self.btn_search_rag)

        self.btn_compile_pdf = SecondaryButton("Compiler en PDF")
        self.btn_compile_pdf.setIcon(load_phosphor_icon("ph.file-pdf", color=DesignTokens.COLOR_RED))
        self.btn_compile_pdf.setToolTip(self.tr("Assembler toutes les pages en un document PDF de lecture"))
        self.btn_compile_pdf.setFixedHeight(26)
        self.btn_compile_pdf.setStyleSheet(f"font-size: 11px; padding: 2px 8px; border: 1px solid {DesignTokens.BORDER_COLOR};")
        self.btn_compile_pdf.clicked.connect(self._on_compile_pdf)
        self.toolbar_flow_layout.addWidget(self.btn_compile_pdf)

        self.btn_add_pages = SecondaryButton("Ajouter des images")
        self.btn_add_pages.setIcon(load_phosphor_icon("ph.plus", color=DesignTokens.COLOR_BLUE))
        self.btn_add_pages.setToolTip(self.tr("Ajouter de nouvelles planches ou images à cet album"))
        self.btn_add_pages.setFixedHeight(26)
        self.btn_add_pages.setStyleSheet(f"font-size: 11px; padding: 2px 8px; border: 1px solid {DesignTokens.BORDER_COLOR};")
        self.btn_add_pages.clicked.connect(self._on_add_pages)
        self.toolbar_flow_layout.addWidget(self.btn_add_pages)

        toolbar_vlayout.addWidget(self.toolbar_container)

        # Ligne 2 (Conditionnelle) : Barre de progression OCR
        self.progress_container = QFrame()
        self.progress_container.setObjectName("ocrProgressContainer")
        self.progress_container.setVisible(False)
        self.progress_container.setStyleSheet(f"""
            QFrame#ocrProgressContainer {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        prog_layout = QHBoxLayout(self.progress_container)
        prog_layout.setContentsMargins(6, 4, 6, 4)
        prog_layout.setSpacing(8)

        self.lbl_progress_info = QLabel(self.tr("Transcription IA en cours..."))
        self.lbl_progress_info.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px; font-weight: 500;")
        prog_layout.addWidget(self.lbl_progress_info)

        self.ocr_progress_bar = QProgressBar()
        self.ocr_progress_bar.setRange(0, 100)
        self.ocr_progress_bar.setValue(0)
        self.ocr_progress_bar.setFixedHeight(8)
        self.ocr_progress_bar.setTextVisible(False)
        self.ocr_progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {DesignTokens.BG_PANEL};
                border-radius: 4px;
                border: none;
            }}
            QProgressBar::chunk {{
                background-color: {DesignTokens.COLOR_YELLOW};
                border-radius: 4px;
            }}
        """)
        prog_layout.addWidget(self.ocr_progress_bar, 1)

        self.btn_retry_failures = SecondaryButton("Relancer les échecs")
        self.btn_retry_failures.setIcon(load_phosphor_icon("ph.arrow-counter-clockwise", color=DesignTokens.COLOR_RED))
        self.btn_retry_failures.setFixedHeight(22)
        self.btn_retry_failures.setStyleSheet(f"font-size: 11px; padding: 2px 8px; border: 1px solid {DesignTokens.COLOR_RED}; color: {DesignTokens.COLOR_RED};")
        self.btn_retry_failures.setVisible(False)
        self.btn_retry_failures.clicked.connect(self._on_retry_failures)
        prog_layout.addWidget(self.btn_retry_failures)

        self.btn_cancel_ocr = IconButton("ph.x", tooltip=self.tr("Arrêter la transcription"), size=20)
        self.btn_cancel_ocr.clicked.connect(self._on_cancel_ocr)
        prog_layout.addWidget(self.btn_cancel_ocr)

        toolbar_vlayout.addWidget(self.progress_container)

        # Ligne 3 (conditionnelle) : Barre de progression de la compilation PDF.
        # Même forme de signal et même expérience que la transcription, dans la même barre
        # d'outils : la compilation s'annonce et s'annule comme elle.
        self.pdf_progress_container = QFrame()
        self.pdf_progress_container.setObjectName("pdfProgressContainer")
        self.pdf_progress_container.setVisible(False)
        self.pdf_progress_container.setStyleSheet(f"""
            QFrame#pdfProgressContainer {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        pdf_prog_layout = QHBoxLayout(self.pdf_progress_container)
        pdf_prog_layout.setContentsMargins(6, 4, 6, 4)
        pdf_prog_layout.setSpacing(8)

        self.lbl_pdf_progress = QLabel(self.tr("Compilation PDF en cours..."))
        self.lbl_pdf_progress.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px; font-weight: 500;")
        pdf_prog_layout.addWidget(self.lbl_pdf_progress)

        self.pdf_progress_bar = QProgressBar()
        self.pdf_progress_bar.setRange(0, 100)
        self.pdf_progress_bar.setValue(0)
        self.pdf_progress_bar.setFixedHeight(8)
        self.pdf_progress_bar.setTextVisible(False)
        self.pdf_progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {DesignTokens.BG_PANEL};
                border-radius: 4px;
                border: none;
            }}
            QProgressBar::chunk {{
                background-color: {DesignTokens.COLOR_RED};
                border-radius: 4px;
            }}
        """)
        pdf_prog_layout.addWidget(self.pdf_progress_bar, 1)

        self.btn_cancel_pdf = IconButton("ph.x", tooltip=self.tr("Arrêter la compilation"), size=20)
        self.btn_cancel_pdf.clicked.connect(self._on_cancel_pdf)
        pdf_prog_layout.addWidget(self.btn_cancel_pdf)

        toolbar_vlayout.addWidget(self.pdf_progress_container)

        main_layout.addWidget(self.toolbar_card)

        # ── 2. Pile Centrale : Planche-Contact (0) vs Inspecteur (1) ───────────
        self.stack = QStackedWidget()
        self.stack.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)

        # Page 0 : Planche-Contact
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet(f"""
            QScrollArea {{
                background-color: {DesignTokens.BG_MAIN};
                border: none;
            }}
        """)

        self.grid_container = QWidget()
        self.grid_container.setStyleSheet("background: transparent;")
        self.grid_layout = FlowLayout(self.grid_container, margin=14, h_spacing=14, v_spacing=14)
        self.scroll_area.setWidget(self.grid_container)
        self.stack.addWidget(self.scroll_area)

        # Page 1 : Inspecteur de page
        self.inspector = PageInspectorWidget()
        self.inspector.close_requested.connect(lambda: self.stack.setCurrentIndex(0))
        self.inspector.page_saved.connect(self._on_page_saved_from_inspector)
        self.inspector.navigate_requested.connect(self._on_inspector_navigate)
        self.inspector.rotate_requested.connect(self._on_rotate_page)
        self.inspector.page_crop_changed.connect(self._on_page_crop_changed)
        self.stack.addWidget(self.inspector)

        main_layout.addWidget(self.stack, 1)

    def load_album(self, doc: DocumentModel) -> None:
        """Charge et affiche les pages de l'album spécifié."""
        self._doc = doc
        title = doc.original_media.original_name if doc.original_media else doc.title
        self.lbl_album_title.setText(title)
        self.stack.setCurrentIndex(0)
        self._populate_category_combo()
        self.refresh_pages()

    def refresh_pages(self) -> None:
        """Recharge les vignettes depuis la base de données."""
        if not self._doc:
            return

        # Vider le layout existant
        while self.grid_layout.count() > 0:
            item = self.grid_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        self._pages = list(DocumentPageModel.select().where(DocumentPageModel.document == self._doc).order_by(DocumentPageModel.page_number))

        total = len(self._pages)
        self.pages_badge.setText(tr("%1 page%2", total, "s" if total > 1 else ""))

        for page in self._pages:
            # Service partagé : une instance par carte ouvrirait N handles de média pour
            # le même album, sans rien gagner puisque la couture est sans état.
            card = AlbumPageCard(page, album_service=self._album_service)
            card.rotate_requested.connect(self._on_rotate_page)
            card.move_requested.connect(self._on_move_page)
            card.delete_requested.connect(self._on_delete_page)
            card.inspect_requested.connect(self._on_open_inspector)
            self.grid_layout.addWidget(card)
            card.show()

    @Slot(int)
    def _on_rotate_page(self, page_id: int) -> None:
        """Fait pivoter la page de 90° et rafraîchit l'affichage."""
        try:
            new_rotation = self._album_service.rotate_page(page_id, degrees=90)
            self.refresh_pages()
            if self.stack.currentIndex() == 1 and self.inspector.current_page and self.inspector.current_page.id == page_id:
                # Rechargée **depuis la base** : `inspector.current_page` est l'instance
                # d'avant la rotation, donc la couture y lirait l'ancienne orientation et
                # son statut « prêt ». L'inspecteur affichait la planche non pivotée, et le
                # bandeau « périmé » restait caché alors qu'il venait d'être déclenché.
                self.inspector.load_page(DocumentPageModel.get_by_id(page_id), len(self._pages))
            if self._doc:
                self.album_modified.emit(self._doc.id)
            show_toast(self, tr("Page pivotée (actuellement %1°).", new_rotation))
        except Exception as e:
            logger.exception("Erreur lors de la rotation de la page %d: %s", page_id, e)
            show_toast(self, self.tr("Erreur lors de la rotation de la page."), is_error=True)

    @Slot(int)
    def _on_page_crop_changed(self, page_id: int) -> None:
        """Rafraîchit les vignettes et notifie de la modification du recadrage d'une page."""
        self.refresh_pages()
        if self._doc:
            self.album_modified.emit(self._doc.id)

    @Slot(int, int)
    def _on_move_page(self, page_id: int, direction: int) -> None:
        """Déplace la page vers la gauche (-1) ou la droite (+1)."""
        if not self._doc:
            return

        page_ids = [p.id for p in self._pages]
        try:
            idx = page_ids.index(page_id)
        except ValueError:
            return

        new_idx = idx + direction
        if not (0 <= new_idx < len(page_ids)):
            return

        # Échange des positions
        page_ids[idx], page_ids[new_idx] = page_ids[new_idx], page_ids[idx]

        try:
            self._album_service.reorder_pages(self._doc.id, page_ids)
            self.refresh_pages()
            self.album_modified.emit(self._doc.id)
        except Exception as e:
            logger.exception("Erreur lors du réordonnancement des pages: %s", e)
            show_toast(self, self.tr("Erreur lors du réordonnancement."), is_error=True)

    @Slot(int)
    def _on_delete_page(self, page_id: int) -> None:
        """Supprime une page de l'album après confirmation utilisateur."""
        reply = QMessageBox.question(
            self,
            self.tr("Supprimer la page"),
            self.tr("Êtes-vous sûr de vouloir retirer cette page de l'album ?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self._album_service.delete_page(page_id)
                self.refresh_pages()
                if self._doc:
                    self.album_modified.emit(self._doc.id)
                show_toast(self, self.tr("Page supprimée de l'album."))
            except Exception as e:
                logger.exception("Erreur lors de la suppression de la page %d: %s", page_id, e)
                show_toast(self, self.tr("Erreur lors de la suppression."), is_error=True)

    @Slot(int)
    def _on_open_inspector(self, page_id: int) -> None:
        """Ouvre l'inspecteur pour la page sélectionnée."""
        for i, page in enumerate(self._pages):
            if page.id == page_id:
                self._current_inspect_index = i
                self.inspector.load_page(page, len(self._pages))
                self.stack.setCurrentIndex(1)
                break

    @Slot(int)
    def _on_inspector_navigate(self, delta: int) -> None:
        """Navigue à la page suivante ou précédente dans l'inspecteur."""
        new_idx = self._current_inspect_index + delta
        if 0 <= new_idx < len(self._pages):
            self._current_inspect_index = new_idx
            self.inspector.load_page(self._pages[new_idx], len(self._pages))

    @Slot(int, str)
    def _on_page_saved_from_inspector(self, page_id: int, ocr_text: str) -> None:
        """Met à jour la vignette correspondante après sauvegarde du texte."""
        for i in range(self.grid_layout.count()):
            item = self.grid_layout.itemAt(i)
            if item and isinstance(item.widget(), AlbumPageCard) and item.widget().page.id == page_id:
                item.widget().update_status(ocr_text)
                break
        if self._doc:
            self.album_modified.emit(self._doc.id)

    @Slot()
    def _on_add_pages(self) -> None:
        """Ouvre une boîte de dialogue pour ajouter de nouvelles images à l'album."""
        if not self._doc:
            return

        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Ajouter des images à l'album",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        if not file_paths:
            return

        try:
            self._album_service.add_pages_to_album(self._doc.id, file_paths)
            self.refresh_pages()
            self.album_modified.emit(self._doc.id)
            show_toast(self, tr("%1 image(s) ajoutée(s) à l'album.", len(file_paths)))
        except Exception as e:
            logger.exception("Erreur lors de l'ajout d'images: %s", e)
            show_toast(self, self.tr("Erreur lors de l'ajout des images."), is_error=True)

    @Slot()
    def _on_compile_pdf(self) -> None:
        """Compile l'album complet en un PDF de lecture, dans un worker."""
        if not self._doc:
            return

        out_path, _ = QFileDialog.getSaveFileName(
            self,
            "Enregistrer l'album au format PDF",
            f"{self._doc.title}.pdf",
            "Fichiers PDF (*.pdf)",
        )
        if not out_path:
            return

        # La compilation ouvre chaque planche en pleine résolution : la faire ici gellerait
        # l'interface sur tout album de taille réelle. Le worker est donc la moitié du
        # correctif — l'autre moitié étant le nom de paramètre, qui levait un TypeError.
        self.btn_compile_pdf.setEnabled(False)
        # Voir `_on_start_ocr_flow` : deux workers écrivant en base ne doivent pas tourner
        # en même temps.
        self.btn_ocr.setEnabled(False)
        self.pdf_progress_container.setVisible(True)
        self.pdf_progress_bar.setValue(0)
        self.lbl_pdf_progress.setText(self.tr("Compilation du PDF..."))

        worker = AlbumPDFWorker(document_id=self._doc.id, output_path=out_path, album_service=self._album_service)
        # La référence est lâchée sur `QThread.finished` (le signal de `QThread`, pas le
        # nôtre) : la libérer dans un slot en file d'attente sur `finished_signal` pouvait
        # détruire le `QThread` encore en cours de `run()`. `closeEvent` l'annule d'abord.
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(lambda: self._release_worker("pdf"))
        self._pdf_worker = worker
        self._pdf_worker.progress.connect(self._on_pdf_progress)
        self._pdf_worker.finished_signal.connect(self._on_pdf_finished)
        self._pdf_worker.cancelled_signal.connect(self._on_pdf_cancelled)
        self._pdf_worker.error_signal.connect(self._on_pdf_error)
        self._pdf_worker.start()

    @Slot(int, int)
    def _on_pdf_progress(self, current: int, total: int) -> None:
        pct = int((current / max(1, total)) * 100)
        self.pdf_progress_bar.setValue(pct)
        self.lbl_pdf_progress.setText(tr("Compilation : %1/%2 planches (%3%%)", current, total, pct))

    @Slot(str)
    def _on_pdf_finished(self, output_path: str) -> None:
        self._restore_pdf_controls()
        show_toast(self, tr("PDF généré avec succès : %1", Path(output_path).name))

    @Slot(int, int)
    def _on_pdf_cancelled(self, done: int, total: int) -> None:
        self._restore_pdf_controls()
        show_toast(self, tr("Compilation annulée (%1/%2 planches).", done, total))

    @Slot(str)
    def _on_pdf_error(self, message: str) -> None:
        self._restore_pdf_controls()
        # Le motif est remonté : « erreur de compilation » sans raison laisse l'utilisateur
        # deviner entre un disque plein, un chemin non inscriptible et un média manquant.
        # Le chemin OCR fait déjà de même ; la compilation ne devait pas être le cas laxiste.
        logger.error("Échec de la compilation PDF de l'album %s : %s", getattr(self._doc, "id", "?"), message)
        show_toast(self, tr("Erreur de compilation PDF : %1", message), is_error=True)

    @Slot()
    def _on_cancel_pdf(self) -> None:
        if self._pdf_worker:
            self._pdf_worker.cancel()
            self.lbl_pdf_progress.setText(self.tr("Annulation en cours..."))

    @Slot()
    def _release_worker(self, kind: str) -> None:
        """
        Lâche la référence Python du worker — sur le **vrai** `QThread.finished` seulement.

        Les signaux métier (`finished_signal`, `cancelled_signal`, `error_signal`) sont émis
        depuis `run()`, donc juste avant que le thread ne rende la main : y remettre
        `self._xxx_worker = None` suffisait à laisser le wrapper Python être ramassé pendant
        que le C++ tournait encore, ce qui produit le crash natif que ce mécanisme cherche
        précisément à éviter.
        """
        if kind == "pdf":
            self._pdf_worker = None
        else:
            self._ocr_worker = None
        self._refresh_pdf_button_state()

    def _restore_pdf_controls(self) -> None:
        self.pdf_progress_container.setVisible(False)
        # L'état des boutons est dérivé de la présence réelle des workers, pas posé en dur :
        # poser « compilation activée » ici réactivait le bouton pendant qu'une transcription
        # était encore en vol.
        self._refresh_category_vision_state()
        self._refresh_pdf_button_state()

    def _populate_category_combo(self) -> None:
        """
        Remplit le sélecteur de catégorie depuis les catégories configurées.

        Aucun concept nouveau : ce sont les mêmes catégories que celles de l'onglet
        Moteurs IA. L'album utilisait `categories[0]` sans jamais proposer le choix —
        le paramètre existait déjà, l'interface ne le remplissait pas.
        """
        categories = self._category_service.get_categories()
        self.combo_category.blockSignals(True)
        self.combo_category.clear()
        for category in categories:
            self.combo_category.addItem(category.name, category.id)
        self.combo_category.blockSignals(False)

        if not categories:
            self._selected_category_id = ""
        else:
            # `findData` renvoie -1 quand la catégorie mémorisée a été supprimée entre-temps.
            # On retombait alors sur un sélecteur **vide** dont l'absence de choix était
            # résolue plus bas par `categories[0]` : l'utilisateur croyait transcrire avec
            # sa catégorie, obtenait le modèle par défaut, et n'en savait rien.
            index = self.combo_category.findData(self._selected_category_id)
            if index < 0:
                index = 0
            self.combo_category.setCurrentIndex(index)
            self._selected_category_id = str(self.combo_category.itemData(index))
        self._refresh_category_vision_state()

    def _current_category_id(self) -> str:
        """
        Catégorie choisie.

        Ne se replie **que** sur ce que le sélecteur affiche effectivement : un repli
        silencieux sur une catégorie par défaut donnerait un modèle que l'utilisateur n'a
        pas choisi, ce que ce ticket existe précisément pour empêcher.
        """
        chosen = self.combo_category.currentData()
        return str(chosen) if chosen else ""

    def _on_category_changed(self) -> None:
        self._selected_category_id = self._current_category_id()
        self._refresh_category_vision_state()

    def _refresh_category_vision_state(self) -> None:
        """
        Refuse la transcription quand la catégorie vise un moteur texte seul.

        « La déclaration fait autorité » : le dépôt l'a déjà tranché pour le Studio de
        Création et la Batch Factory, et l'album serait le seul endroit à l'ignorer —
        l'utilisateur verrait alors la transcription échouer sans raison affichée.
        """
        category_id = self._current_category_id()
        category = self._category_service.get_category_by_id(category_id) if category_id else None
        if category is None:
            self.btn_ocr.setEnabled(True)
            self.btn_ocr.setToolTip(self.tr("Lancer l'analyse et la transcription de l'album avec le modèle IA sélectionné"))
            return

        supports_vision = self._category_service.category_declares_vision(category)
        if supports_vision is False:
            self.btn_ocr.setEnabled(False)
            self.btn_ocr.setToolTip(tr("%1 : « %2 » pointe vers un moteur qui ne sait pas lire les planches.", VISION_UNSUPPORTED_LABEL, category.name))
            return

        self.btn_ocr.setEnabled(True)
        self.btn_ocr.setToolTip(tr("Lancer l'analyse et la transcription de l'album avec « %1 »", category.name))

    @Slot()
    def _on_open_transcription_dialog(self) -> None:
        """Ouvre le dialogue modal dédié à la transcription de l'album."""
        if not self._doc or not self._pages:
            show_toast(self, self.tr("Aucune planche à transcrire dans cet album."), is_error=True)
            return

        from ankiforge.ui.dialogs.album_transcription_dialog import AlbumTranscriptionDialog

        dialog = AlbumTranscriptionDialog(
            doc=self._doc,
            parent=self.window(),
            category_service=self._category_service,
        )
        dialog.transcription_requested.connect(self._on_transcription_options_confirmed)
        dialog.exec()

    @Slot(object)
    def _on_transcription_options_confirmed(self, options: AlbumTranscriptionOptions) -> None:
        """Reçoit les options validées depuis le dialogue et déclenche le worker."""
        self._last_transcription_options = options
        self._on_start_ocr_flow(options=options)

    @Slot()
    def _on_retry_failures(self) -> None:
        """Relance immédiatement la transcription sur les seules planches en échec."""
        if not self._doc or not self._failed_page_ids:
            return

        from dataclasses import replace

        failed_ids = list(self._failed_page_ids)
        self.btn_retry_failures.setVisible(False)

        opts: AlbumTranscriptionOptions | None = None
        if self._last_transcription_options:
            opts = replace(self._last_transcription_options, target_page_ids=failed_ids, scope_mode="custom")

        self._on_start_ocr_flow(options=opts, page_ids_override=failed_ids)

    def _on_start_ocr_flow(
        self,
        options: AlbumTranscriptionOptions | None = None,
        page_ids_override: list[int] | None = None,
    ) -> None:
        """Déclenche la transcription IA asynchrone des pages de l'album."""
        if not self._doc or not self._pages:
            show_toast(self, self.tr("Aucune page à transcrire."), is_error=True)
            return

        category_id = options.category_id if options else self._current_category_id()
        if not category_id:
            show_toast(self, self.tr("Aucune catégorie de transcription configurée."), is_error=True)
            return

        self._selected_category_id = category_id

        self.btn_ocr.setEnabled(False)
        # Les deux workers écrivent en base depuis leur propre thread. Les laisser
        # concurrents les ferait sérialiser sur le verrou d'écriture de SQLite pendant
        # toute la durée du plus lent, sans un mot à l'utilisateur : mieux vaut interdire
        # le cas que l'annoncer.
        self.btn_compile_pdf.setEnabled(False)
        self.progress_container.setVisible(True)
        self.ocr_progress_bar.setValue(0)
        self.btn_retry_failures.setVisible(False)
        self.lbl_progress_info.setText(self.tr("Démarrage de la transcription IA..."))

        worker = (
            AlbumOCRWorker(
                document_id=self._doc.id,
                options=options,
            )
            if options is not None
            else AlbumOCRWorker(
                document_id=self._doc.id,
                category_id=category_id,
                page_ids=page_ids_override,
            )
        )
        # cf. `_on_compile_pdf` : la référence cède la place sur la fin **réelle** du
        # thread, sinon le `QThread` est détruit alors que `run()` s'exécute encore.
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(lambda: self._release_worker("ocr"))
        self._ocr_worker = worker
        self._ocr_worker.progress.connect(self._on_worker_progress)
        self._ocr_worker.page_processed.connect(self._on_worker_page_processed)
        self._ocr_worker.finished_signal.connect(self._on_worker_finished)
        self._ocr_worker.cancelled_signal.connect(self._on_worker_cancelled)
        self._ocr_worker.error_signal.connect(self._on_worker_error)
        self._ocr_worker.start()

    @Slot(int, int)
    def _on_worker_progress(self, current: int, total: int) -> None:
        pct = int((current / max(1, total)) * 100)
        self.ocr_progress_bar.setValue(pct)
        self.lbl_progress_info.setText(tr("Transcription : %1/%2 pages (%3%%)", current, total, pct))

    @Slot(int, int, str)
    def _on_worker_page_processed(self, page_id: int, page_number: int, text: str) -> None:
        # Met à jour la vignette en direct
        for i in range(self.grid_layout.count()):
            item = self.grid_layout.itemAt(i)
            if item and isinstance(item.widget(), AlbumPageCard) and item.widget().page.id == page_id:
                # Le worker ne renvoie que le texte : la page concernée n'est plus périmée
                # puisqu'elle vient d'être retranscrite, on le dit explicitement plutôt que
                # de laisser un « stale » qui n'a plus d'objet.
                item.widget().update_status(text, "ready")
                break

    @Slot(int, int)
    def _on_worker_finished(self, success_count: int, error_count: int) -> None:
        self._restore_ocr_controls()

        if error_count and self._ocr_worker and getattr(self._ocr_worker, "failed_page_ids", None):
            self._failed_page_ids = list(self._ocr_worker.failed_page_ids)
            self.progress_container.setVisible(True)
            self.lbl_progress_info.setText(tr("Échec partiel : %1 réussie(s), %2 en échec", success_count, error_count))
            self.btn_retry_failures.setText(tr("Relancer les échecs (%1)", len(self._failed_page_ids)))
            self.btn_retry_failures.setVisible(True)
        else:
            self._failed_page_ids = []
            self.btn_retry_failures.setVisible(False)

        # Le compte rendu nomme ce qui a échoué au lieu de valider un « terminé » : un album
        # dont toutes les planches ont échoué ne doit pas s'annoncer comme transcrit.
        if error_count and success_count == 0:
            show_toast(self, tr("Transcription en échec : %1 page(s) sans résultat exploitable.", error_count), is_error=True)
        elif error_count:
            show_toast(self, tr("Transcription partielle : %1 page(s) transcrites, %2 en échec.", success_count, error_count), is_error=True)
        else:
            show_toast(self, tr("Transcription achevée : %1 page(s) transcrites.", success_count))

        if self._doc:
            self.album_modified.emit(self._doc.id)

    @Slot(int, int)
    def _on_worker_cancelled(self, done: int, total: int) -> None:
        self._restore_ocr_controls()
        show_toast(self, tr("Transcription interrompue : %1/%2 page(s) traitées.", done, total))

    @Slot(str)
    def _on_worker_error(self, message: str) -> None:
        self._restore_ocr_controls()
        show_toast(self, tr("Erreur transcription : %1", message), is_error=True)

    def _restore_ocr_controls(self) -> None:
        self.progress_container.setVisible(False)
        self.btn_retry_failures.setVisible(False)
        # Réactivé via la politique Vision et non inconditionnellement : si la catégorie
        # visée ne sait pas lire les planches, le bouton doit rester désactivé.
        self._refresh_category_vision_state()
        self._refresh_pdf_button_state()

    def _refresh_pdf_button_state(self) -> None:
        if self._doc is None:
            self.btn_compile_pdf.setEnabled(False)
            return
        self.btn_compile_pdf.setEnabled(self._ocr_worker is None and self._pdf_worker is None)

    @Slot()
    def _on_cancel_ocr(self) -> None:
        if self._ocr_worker:
            self._ocr_worker.cancel()
            self.lbl_progress_info.setText(self.tr("Annulation en cours..."))

    @Slot()
    def _on_forge_clicked(self) -> None:
        if self._doc:
            self.forge_requested.emit(self._doc.id)

    def closeEvent(self, event: QCloseEvent) -> None:  # Nom imposé par Qt.
        """
        Annule les workers en vol avant de laisser la vue disparaître.

        Un `QThread` détruit alors que `run()` s'exécute provoke un crash natif, pas une
        exception Python : fermer la vue en pleine transcription ou en pleine compilation
        devait donc être traité, pas espéré. `wait()` est borné — les workers testent leur
        drapeau d'annuation entre deux planches, donc ils sortent vite.
        """
        still_running = []
        for worker in (self._ocr_worker, self._pdf_worker):
            if worker is None or not worker.isRunning():
                continue
            worker.cancel()
            if not worker.wait(3000):
                still_running.append(worker)

        if still_running:
            # Annoncer une destruction reportée ne la reportait pas : l'événement passait,
            # la vue se détruisait quand même, et le QThread mourait avec elle. La
            # fermeture est donc refusée tant qu'un worker tourne, et l'utilisateur
            # refera la fenêtre une fois l'annulation terminée.
            logger.warning("Worker d'album encore actif après 3 s : fermeture refusée pour éviter un crash natif.")
            show_toast(self, self.tr("Annulation en cours : refermez la fenêtre à nouveau dans un instant."), is_error=True)
            event.ignore()
            return

        super().closeEvent(event)
