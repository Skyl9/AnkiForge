from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QImage, QPixmap, QTransform
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import DocumentModel, DocumentPageModel
from ankiforge.services.ai.vision_category_service import VisionCategoryService
from ankiforge.services.cards.album_service import AlbumService
from ankiforge.services.workers.album_worker import AlbumOCRWorker
from ankiforge.ui.components import (
    Badge,
    IconButton,
    PrimaryButton,
    SecondaryButton,
)
from ankiforge.ui.components.flow_layout import FlowLayout
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon
from ankiforge.utils.paths import get_app_data_dir

logger = logging.getLogger(__name__)


class AlbumPageCard(QFrame):
    """
    Carte de vignette individuelle pour une page d'album dans la planche-contact.
    Affiche la miniature, le numéro de page, le statut OCR et une barre d'actions rapides.
    """

    rotate_requested = Signal(int)  # page_id
    move_requested = Signal(int, int)  # page_id, direction (-1 ou +1)
    delete_requested = Signal(int)  # page_id
    inspect_requested = Signal(int)  # page_id

    def __init__(self, page: DocumentPageModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.page = page
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

        header_layout.addStretch()

        has_ocr = bool(page.ocr_text and page.ocr_text.strip())
        status_text = "✓ OCR" if has_ocr else "Non transcrit"
        status_variant = "success" if has_ocr else "neutral"
        self.ocr_badge = Badge(status_text, variant=status_variant)
        self.ocr_badge.setToolTip(f"{len(page.ocr_text.split())} mots extraits" if has_ocr else "Aucune transcription")
        header_layout.addWidget(self.ocr_badge)

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

        self._load_thumbnail()

        # ── Barre d'actions rapides (Bas de carte) ───────────────────────────
        actions_layout = QHBoxLayout()
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(2)

        self.btn_left = IconButton("ph.caret-left", tooltip="Déplacer vers la gauche (page précédente)", size=22)
        self.btn_left.clicked.connect(lambda: self.move_requested.emit(self.page.id, -1))

        self.btn_right = IconButton("ph.caret-right", tooltip="Déplacer vers la droite (page suivante)", size=22)
        self.btn_right.clicked.connect(lambda: self.move_requested.emit(self.page.id, 1))

        self.btn_rotate = IconButton("ph.arrow-clockwise", tooltip="Tourner de 90°", size=22)
        self.btn_rotate.clicked.connect(lambda: self.rotate_requested.emit(self.page.id))

        self.btn_inspect = IconButton("ph.magnifying-glass-plus", tooltip="Inspecter la page", size=22)
        self.btn_inspect.clicked.connect(lambda: self.inspect_requested.emit(self.page.id))

        self.btn_delete = IconButton("ph.trash", tooltip="Supprimer cette page", size=22)
        self.btn_delete.clicked.connect(lambda: self.delete_requested.emit(self.page.id))

        actions_layout.addWidget(self.btn_left)
        actions_layout.addWidget(self.btn_right)
        actions_layout.addStretch()
        actions_layout.addWidget(self.btn_rotate)
        actions_layout.addWidget(self.btn_inspect)
        actions_layout.addWidget(self.btn_delete)

        layout.addLayout(actions_layout)

    def _load_thumbnail(self) -> None:
        """Charge l'image, applique la rotation actuelle et l'affiche à l'échelle."""
        try:
            filename = self.page.media.filename if self.page.media else ""
            img_path = get_app_data_dir() / "media" / filename
            if not img_path.exists():
                self.img_lbl.setText("Image absente")
                self.img_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
                return

            pixmap = QPixmap(str(img_path))
            if pixmap.isNull():
                self.img_lbl.setText("Erreur image")
                return

            if self.page.rotation % 360 != 0:
                transform = QTransform()
                transform.rotate(self.page.rotation)
                pixmap = pixmap.transformed(transform, Qt.TransformationMode.SmoothTransformation)

            thumb = pixmap.scaled(
                180,
                180,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.img_lbl.setPixmap(thumb)
        except Exception as e:
            logger.warning("Erreur chargement vignette page %d: %s", self.page.id, e)
            self.img_lbl.setText("Aperçu indisponible")

    def update_status(self, ocr_text: str) -> None:
        """Met à jour le badge de statut OCR."""
        self.page.ocr_text = ocr_text
        has_ocr = bool(ocr_text and ocr_text.strip())
        self.ocr_badge.setText("✓ OCR" if has_ocr else "Non transcrit")
        self.ocr_badge.set_variant("success" if has_ocr else "neutral")
        self.ocr_badge.setToolTip(f"{len(ocr_text.split())} mots extraits" if has_ocr else "Aucune transcription")


class PageInspectorWidget(QWidget):
    """
    Vue détaillée et zoomable pour inspecter, ajuster le contraste et retoucher
    le texte OCR d'une page individuelle.
    """

    close_requested = Signal()
    page_saved = Signal(int, str)  # page_id, ocr_text
    navigate_requested = Signal(int)  # delta (-1 pour précédent, +1 pour suivant)
    rotate_requested = Signal(int)  # page_id

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.current_page: DocumentPageModel | None = None
        self._raw_pixmap: QPixmap | None = None
        self._zoom_factor: float = 1.0

        self._setup_ui()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Barre d'outils supérieure de l'inspecteur ─────────────────────────
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

        self.btn_back = SecondaryButton("Planche-contact")
        self.btn_back.setIcon(load_phosphor_icon("ph.squares-four", color=DesignTokens.TEXT_PRIMARY))
        self.btn_back.clicked.connect(self.close_requested.emit)
        top_layout.addWidget(self.btn_back)

        self.lbl_title = QLabel("Inspecteur de page")
        self.lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: bold; font-size: 14px;")
        top_layout.addWidget(self.lbl_title)

        top_layout.addStretch()

        # Navigation entre pages
        self.btn_prev = IconButton("ph.caret-left", tooltip="Page précédente", size=26)
        self.btn_prev.clicked.connect(lambda: self.navigate_requested.emit(-1))
        top_layout.addWidget(self.btn_prev)

        self.btn_next = IconButton("ph.caret-right", tooltip="Page suivante", size=26)
        self.btn_next.clicked.connect(lambda: self.navigate_requested.emit(1))
        top_layout.addWidget(self.btn_next)

        # Rotation
        self.btn_rotate = IconButton("ph.arrow-clockwise", tooltip="Tourner de 90°", size=26)
        self.btn_rotate.clicked.connect(self._on_rotate_clicked)
        top_layout.addWidget(self.btn_rotate)

        # Contrôles de zoom
        self.btn_zoom_out = IconButton("ph.magnifying-glass-minus", tooltip="Zoom arrière", size=26)
        self.btn_zoom_out.clicked.connect(self._on_zoom_out)
        top_layout.addWidget(self.btn_zoom_out)

        self.btn_zoom_reset = IconButton("ph.arrows-out-simple", tooltip="Ajuster à la fenêtre", size=26)
        self.btn_zoom_reset.clicked.connect(self._on_zoom_reset)
        top_layout.addWidget(self.btn_zoom_reset)

        self.btn_zoom_in = IconButton("ph.magnifying-glass-plus", tooltip="Zoom avant", size=26)
        self.btn_zoom_in.clicked.connect(self._on_zoom_in)
        top_layout.addWidget(self.btn_zoom_in)

        # Curseur de contraste
        lbl_contrast = QLabel("Contraste :")
        lbl_contrast.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        top_layout.addWidget(lbl_contrast)

        self.slider_contrast = QSlider(Qt.Orientation.Horizontal)
        self.slider_contrast.setRange(-50, 50)
        self.slider_contrast.setValue(0)
        self.slider_contrast.setFixedWidth(100)
        self.slider_contrast.setToolTip("Ajuster le contraste pour les scans faibles ou manuscrits")
        self.slider_contrast.valueChanged.connect(self._apply_image_transformations)
        top_layout.addWidget(self.slider_contrast)

        main_layout.addWidget(top_bar)

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

        self.image_display = QLabel()
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
        lbl_ocr_title = QLabel("Transcription OCR & Notes")
        lbl_ocr_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: bold; font-size: 13px;")
        ocr_header.addWidget(lbl_ocr_title)
        ocr_header.addStretch()

        self.btn_save_ocr = PrimaryButton("Enregistrer")
        self.btn_save_ocr.setIcon(load_phosphor_icon("ph.floppy-disk", color="white"))
        self.btn_save_ocr.setFixedHeight(28)
        self.btn_save_ocr.setStyleSheet("font-size: 11px; padding: 4px 10px;")
        self.btn_save_ocr.clicked.connect(self._on_save_ocr)
        ocr_header.addWidget(self.btn_save_ocr)
        ocr_layout.addLayout(ocr_header)

        self.ocr_text_edit = QTextEdit()
        self.ocr_text_edit.setPlaceholderText("Aucun texte transcrit pour cette page. Lancez la transcription par Vision IA ou saisissez vos notes ici.")
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
        """Affiche la page spécifiée dans l'inspecteur."""
        self.current_page = page
        self.lbl_title.setText(f"Page {page.page_number} sur {total_pages}")
        self.ocr_text_edit.setPlainText(page.ocr_text or "")
        self.slider_contrast.blockSignals(True)
        self.slider_contrast.setValue(0)
        self.slider_contrast.blockSignals(False)
        self._zoom_factor = 1.0

        filename = page.media.filename if page.media else ""
        img_path = get_app_data_dir() / "media" / filename
        if img_path.exists():
            pix = QPixmap(str(img_path))
            if page.rotation % 360 != 0:
                tr = QTransform()
                tr.rotate(page.rotation)
                pix = pix.transformed(tr, Qt.TransformationMode.SmoothTransformation)
            self._raw_pixmap = pix
        else:
            self._raw_pixmap = None

        self._apply_image_transformations()

    def _apply_image_transformations(self) -> None:
        """Applique le zoom et le contraste sur l'image affichée."""
        if not self._raw_pixmap or self._raw_pixmap.isNull():
            self.image_display.setText("Image non disponible")
            self.image_display.setPixmap(QPixmap())
            return

        pix = self._raw_pixmap
        contrast_val = self.slider_contrast.value()

        if contrast_val != 0:
            img = pix.toImage()
            img = img.convertToFormat(QImage.Format.Format_ARGB32)
            pix = QPixmap.fromImage(img)

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
        self._zoom_factor = min(3.0, self._zoom_factor * 1.2)
        self._apply_image_transformations()

    def _on_zoom_out(self) -> None:
        self._zoom_factor = max(0.3, self._zoom_factor / 1.2)
        self._apply_image_transformations()

    def _on_zoom_reset(self) -> None:
        self._zoom_factor = 1.0
        self._apply_image_transformations()

    def _on_rotate_clicked(self) -> None:
        if self.current_page:
            self.rotate_requested.emit(self.current_page.id)

    def _on_save_ocr(self) -> None:
        if not self.current_page:
            return
        text = self.ocr_text_edit.toPlainText().strip()
        self.current_page.ocr_text = text
        self.current_page.save()
        self.page_saved.emit(self.current_page.id, text)
        show_toast(self, "Transcription enregistrée avec succès.")


class AlbumViewerWidget(QWidget):
    """
    Composant central pour l'affichage, la manipulation et la transcription d'un Album d'images.
    Alterne entre la planche-contact (grille responsive) et l'inspecteur zoomable.
    """

    album_modified = Signal(int)  # document_id
    forge_requested = Signal(int)  # document_id

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._doc: DocumentModel | None = None
        self._pages: list[DocumentPageModel] = []
        self._current_inspect_index: int = 0
        self._ocr_worker: AlbumOCRWorker | None = None
        self._category_service = VisionCategoryService()
        self._album_service = AlbumService()

        self._setup_ui()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── 1. Barre d'actions supérieure de l'Album ──────────────────────────
        self.toolbar_card = QFrame()
        self.toolbar_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
            }}
        """)
        toolbar_vlayout = QVBoxLayout(self.toolbar_card)
        toolbar_vlayout.setContentsMargins(12, 10, 12, 10)
        toolbar_vlayout.setSpacing(8)

        # Ligne 1 : Titre, compteur de pages et boutons d'action
        row1 = QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)
        row1.setSpacing(8)

        album_ico = QLabel()
        album_ico.setPixmap(load_phosphor_icon("ph.images", color=DesignTokens.COLOR_PURPLE).pixmap(20, 20))
        row1.addWidget(album_ico)

        self.lbl_album_title = QLabel("Album d'images")
        self.lbl_album_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 15px; font-weight: bold;")
        row1.addWidget(self.lbl_album_title)

        self.pages_badge = Badge("0 pages", variant="neutral")
        row1.addWidget(self.pages_badge)

        row1.addStretch()

        # Boutons d'action
        self.btn_ocr = SecondaryButton("Transcrire par Vision IA")
        self.btn_ocr.setIcon(load_phosphor_icon("ph.sparkle", color=DesignTokens.COLOR_YELLOW))
        self.btn_ocr.setToolTip("Lancer l'analyse et la transcription de l'album avec le modèle IA sélectionné")
        self.btn_ocr.setFixedHeight(28)
        self.btn_ocr.setStyleSheet(f"font-size: 11px; padding: 3px 10px; border: 1px solid {DesignTokens.BORDER_COLOR};")
        self.btn_ocr.clicked.connect(self._on_start_ocr_flow)
        row1.addWidget(self.btn_ocr)

        self.btn_compile_pdf = SecondaryButton("Compiler en PDF")
        self.btn_compile_pdf.setIcon(load_phosphor_icon("ph.file-pdf", color=DesignTokens.COLOR_RED))
        self.btn_compile_pdf.setToolTip("Assembler toutes les pages en un document PDF de lecture")
        self.btn_compile_pdf.setFixedHeight(28)
        self.btn_compile_pdf.setStyleSheet(f"font-size: 11px; padding: 3px 10px; border: 1px solid {DesignTokens.BORDER_COLOR};")
        self.btn_compile_pdf.clicked.connect(self._on_compile_pdf)
        row1.addWidget(self.btn_compile_pdf)

        self.btn_add_pages = SecondaryButton("Ajouter des images")
        self.btn_add_pages.setIcon(load_phosphor_icon("ph.plus", color=DesignTokens.COLOR_BLUE))
        self.btn_add_pages.setFixedHeight(28)
        self.btn_add_pages.setStyleSheet(f"font-size: 11px; padding: 3px 10px; border: 1px solid {DesignTokens.BORDER_COLOR};")
        self.btn_add_pages.clicked.connect(self._on_add_pages)
        row1.addWidget(self.btn_add_pages)

        self.btn_forge = PrimaryButton("⚡ Forger des cartes")
        self.btn_forge.setIcon(load_phosphor_icon("ph.cards", color="white"))
        self.btn_forge.setFixedHeight(28)
        self.btn_forge.setStyleSheet("font-size: 11px; padding: 3px 12px;")
        self.btn_forge.clicked.connect(self._on_forge_clicked)
        row1.addWidget(self.btn_forge)

        toolbar_vlayout.addLayout(row1)

        # Ligne 2 (Conditionnelle) : Barre de progression OCR
        self.progress_container = QFrame()
        self.progress_container.setVisible(False)
        self.progress_container.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 4px;
            }}
        """)
        prog_layout = QHBoxLayout(self.progress_container)
        prog_layout.setContentsMargins(6, 4, 6, 4)
        prog_layout.setSpacing(8)

        self.lbl_progress_info = QLabel("Transcription IA en cours...")
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

        self.btn_cancel_ocr = IconButton("ph.x", tooltip="Arrêter la transcription", size=20)
        self.btn_cancel_ocr.clicked.connect(self._on_cancel_ocr)
        prog_layout.addWidget(self.btn_cancel_ocr)

        toolbar_vlayout.addWidget(self.progress_container)
        main_layout.addWidget(self.toolbar_card)

        # ── 2. Pile Centrale : Planche-Contact (0) vs Inspecteur (1) ───────────
        self.stack = QStackedWidget()

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
        self.stack.addWidget(self.inspector)

        main_layout.addWidget(self.stack, 1)

    def load_album(self, doc: DocumentModel) -> None:
        """Charge et affiche les pages de l'album spécifié."""
        self._doc = doc
        title = doc.original_media.original_name if doc.original_media else doc.title
        self.lbl_album_title.setText(title)
        self.stack.setCurrentIndex(0)
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
        self.pages_badge.setText(f"{total} page{'s' if total > 1 else ''}")

        for page in self._pages:
            card = AlbumPageCard(page)
            card.rotate_requested.connect(self._on_rotate_page)
            card.move_requested.connect(self._on_move_page)
            card.delete_requested.connect(self._on_delete_page)
            card.inspect_requested.connect(self._on_open_inspector)
            self.grid_layout.addWidget(card)

    @Slot(int)
    def _on_rotate_page(self, page_id: int) -> None:
        """Fait pivoter la page de 90° et rafraîchit l'affichage."""
        try:
            new_rotation = self._album_service.rotate_page(page_id, degrees=90)
            self.refresh_pages()
            if self.stack.currentIndex() == 1 and self.inspector.current_page and self.inspector.current_page.id == page_id:
                self.inspector.load_page(self.inspector.current_page, len(self._pages))
            if self._doc:
                self.album_modified.emit(self._doc.id)
            show_toast(self, f"Page pivotée (actuellement {new_rotation}°).")
        except Exception as e:
            logger.exception("Erreur lors de la rotation de la page %d: %s", page_id, e)
            show_toast(self, "Erreur lors de la rotation de la page.", is_error=True)

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
            show_toast(self, "Erreur lors du réordonnancement.", is_error=True)

    @Slot(int)
    def _on_delete_page(self, page_id: int) -> None:
        """Supprime une page de l'album après confirmation utilisateur."""
        reply = QMessageBox.question(
            self,
            "Supprimer la page",
            "Êtes-vous sûr de vouloir retirer cette page de l'album ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self._album_service.delete_page(page_id)
                self.refresh_pages()
                if self._doc:
                    self.album_modified.emit(self._doc.id)
                show_toast(self, "Page supprimée de l'album.")
            except Exception as e:
                logger.exception("Erreur lors de la suppression de la page %d: %s", page_id, e)
                show_toast(self, "Erreur lors de la suppression.", is_error=True)

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
            show_toast(self, f"{len(file_paths)} image(s) ajoutée(s) à l'album.")
        except Exception as e:
            logger.exception("Erreur lors de l'ajout d'images: %s", e)
            show_toast(self, "Erreur lors de l'ajout des images.", is_error=True)

    @Slot()
    def _on_compile_pdf(self) -> None:
        """Compile l'album complet en un PDF de lecture."""
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

        try:
            pdf_path = self._album_service.compile_album_to_pdf(self._doc.id, output_pdf_path=out_path)
            show_toast(self, f"PDF généré avec succès : {Path(pdf_path).name}")
        except Exception as e:
            logger.exception("Erreur lors de la compilation PDF: %s", e)
            show_toast(self, "Erreur lors de la compilation PDF.", is_error=True)

    @Slot()
    def _on_start_ocr_flow(self) -> None:
        """Déclenche la transcription IA asynchrone des pages de l'album."""
        if not self._doc or not self._pages:
            show_toast(self, "Aucune page à transcrire.", is_error=True)
            return

        categories = self._category_service.get_categories()
        cat_id = categories[0].id if categories else "structured"

        self.btn_ocr.setEnabled(False)
        self.progress_container.setVisible(True)
        self.ocr_progress_bar.setValue(0)
        self.lbl_progress_info.setText("Démarrage de la transcription IA...")

        self._ocr_worker = AlbumOCRWorker(
            document_id=self._doc.id,
            category_id=cat_id,
        )
        self._ocr_worker.progress.connect(self._on_worker_progress)
        self._ocr_worker.page_processed.connect(self._on_worker_page_processed)
        self._ocr_worker.finished_signal.connect(self._on_worker_finished)
        self._ocr_worker.error_signal.connect(self._on_worker_error)
        self._ocr_worker.start()

    @Slot(int, int)
    def _on_worker_progress(self, current: int, total: int) -> None:
        pct = int((current / max(1, total)) * 100)
        self.ocr_progress_bar.setValue(pct)
        self.lbl_progress_info.setText(f"Transcription : {current}/{total} pages ({pct}%)")

    @Slot(int, int, str)
    def _on_worker_page_processed(self, page_id: int, page_number: int, text: str) -> None:
        # Met à jour la vignette en direct
        for i in range(self.grid_layout.count()):
            item = self.grid_layout.itemAt(i)
            if item and isinstance(item.widget(), AlbumPageCard) and item.widget().page.id == page_id:
                item.widget().update_status(text)
                break

    @Slot(int, int)
    def _on_worker_finished(self, success_count: int, error_count: int) -> None:
        self.btn_ocr.setEnabled(True)
        self.progress_container.setVisible(False)
        self._ocr_worker = None

        msg = f"Transcription achevée : {success_count} pages transcrites."
        if error_count > 0:
            msg += f" ({error_count} erreurs)"
        show_toast(self, msg, is_error=(success_count == 0 and error_count > 0))

        if self._doc:
            self.album_modified.emit(self._doc.id)

    @Slot(str)
    def _on_worker_error(self, message: str) -> None:
        self.btn_ocr.setEnabled(True)
        self.progress_container.setVisible(False)
        self._ocr_worker = None
        show_toast(self, f"Erreur transcription : {message}", is_error=True)

    @Slot()
    def _on_cancel_ocr(self) -> None:
        if self._ocr_worker:
            self._ocr_worker.cancel()
            self.lbl_progress_info.setText("Annulation en cours...")

    @Slot()
    def _on_forge_clicked(self) -> None:
        if self._doc:
            self.forge_requested.emit(self._doc.id)
