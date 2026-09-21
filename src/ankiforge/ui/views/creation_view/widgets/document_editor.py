import logging
from pathlib import Path
from typing import Any

import markdown
from PySide6.QtCore import QEvent, Qt, Signal, Slot
from PySide6.QtGui import QCloseEvent, QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ankiforge.ui.components import (
    Badge,
    DangerButton,
    IconButton,
    PrimaryButton,
    SecondaryButton,
    StyledTextEdit,
)
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_on_accent_icon, load_phosphor_icon
from ankiforge.utils.paths import resolve_media_path

logger = logging.getLogger(__name__)


class TextScopeBannerWidget(QFrame):
    """Bandeau d'information et d'actions affiché au-dessus de l'éditeur textuel lorsqu'une portée est active."""

    toggle_display_requested = Signal()
    edit_scope_requested = Signal()
    clear_scope_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("textScopeBanner")
        self.setStyleSheet(f"""
            QFrame#textScopeBanner {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 2px 6px;
            }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        self.icon_lbl = QLabel()
        self.icon_lbl.setPixmap(load_phosphor_icon("ph.funnel", color=DesignTokens.ACCENT_PRIMARY).pixmap(14, 14))
        self.icon_lbl.setStyleSheet("border: none; background: transparent;")

        self.lbl_status = QLabel("Portée active")
        self.lbl_status.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: 600; font-size: 11px; border: none; background: transparent;")

        self.badge_status = Badge("Extrait filtré", variant="success")

        layout.addWidget(self.icon_lbl)
        layout.addWidget(self.lbl_status)
        layout.addWidget(self.badge_status)
        layout.addStretch()

        self.btn_toggle_display = QPushButton("Afficher tout le document")
        self.btn_toggle_display.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_display.setStyleSheet(f"""
            QPushButton {{
                background-color: {DesignTokens.BG_PANEL};
                color: {DesignTokens.TEXT_PRIMARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 3px 8px;
                font-size: 11px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {DesignTokens.BG_ACTIVE};
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        self.btn_toggle_display.clicked.connect(self.toggle_display_requested.emit)
        layout.addWidget(self.btn_toggle_display)

        self.btn_edit_scope = IconButton("ph.sliders", "Modifier la portée documentaire...", 14)
        self.btn_edit_scope.clicked.connect(self.edit_scope_requested.emit)
        layout.addWidget(self.btn_edit_scope)

        self.btn_clear_scope = IconButton("ph.x", "Effacer le filtre de portée", 14)
        self.btn_clear_scope.clicked.connect(self.clear_scope_requested.emit)
        layout.addWidget(self.btn_clear_scope)

    def set_scope_info(self, title: str, chunks_count: int, is_showing_full: bool = False) -> None:
        unit = "fragment" if chunks_count == 1 else "fragments"
        chunks_str = f" ({chunks_count} {unit})" if chunks_count > 0 else ""
        self.lbl_status.setText(f"Portée active : {title}{chunks_str}")
        if is_showing_full:
            self.badge_status.setText("Document entier (filtre en pause)")
            self.badge_status.set_variant("neutral")
            self.btn_toggle_display.setText("Afficher l'extrait filtré")
        else:
            self.badge_status.setText("Extrait filtré")
            self.badge_status.set_variant("success")
            self.btn_toggle_display.setText("Afficher tout le document")


class AlbumPageMiniWidget(QFrame):
    """Mini-carte représentant une planche d'album dans l'éditeur du Studio."""

    clicked = Signal(int)

    def __init__(
        self,
        page_num: int,
        media_path: Path | None,
        snippet: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.page_num = page_num
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("albumMiniCard")
        self.setFixedWidth(180)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        self.lbl_page = QLabel(f"Planche {page_num}")
        self.lbl_page.setStyleSheet(f"font-weight: 700; font-size: 11px; color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")
        self.badge = Badge("Portée", variant="success")
        header.addWidget(self.lbl_page)
        header.addStretch()
        header.addWidget(self.badge)
        layout.addLayout(header)

        self.img_lbl = QLabel()
        self.img_lbl.setFixedSize(168, 112)
        self.img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_lbl.setStyleSheet(f"background-color: {DesignTokens.BG_INPUT}; border-radius: {DesignTokens.RADIUS_SM}px; border: 1px solid {DesignTokens.BORDER_COLOR};")
        if media_path and media_path.exists():
            pix = QPixmap(str(media_path))
            if not pix.isNull():
                self.img_lbl.setPixmap(pix.scaled(168, 112, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            else:
                self.img_lbl.setPixmap(load_phosphor_icon("ph.image", color=DesignTokens.TEXT_MUTED).pixmap(32, 32))
        else:
            self.img_lbl.setPixmap(load_phosphor_icon("ph.image", color=DesignTokens.TEXT_MUTED).pixmap(32, 32))
        layout.addWidget(self.img_lbl)

        clean_snippet = snippet.replace("\n", " ").strip()
        if len(clean_snippet) > 75:
            clean_snippet = clean_snippet[:72] + "..."
        self.lbl_desc = QLabel(clean_snippet or "Aucune transcription")
        self.lbl_desc.setWordWrap(True)
        self.lbl_desc.setStyleSheet(f"font-size: 10px; color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")
        layout.addWidget(self.lbl_desc)

        self.set_in_scope(True)

    def mousePressEvent(self, event: Any) -> None:
        super().mousePressEvent(event)
        self.clicked.emit(self.page_num)

    def set_in_scope(self, in_scope: bool) -> None:
        if in_scope:
            self.setStyleSheet(f"""
                QFrame#albumMiniCard {{
                    background-color: {DesignTokens.BG_PANEL};
                    border: 2px solid {DesignTokens.ACCENT_PRIMARY};
                    border-radius: {DesignTokens.RADIUS_MD}px;
                }}
            """)
            self.badge.setText("Portée")
            self.badge.set_variant("success")
        else:
            self.setStyleSheet(f"""
                QFrame#albumMiniCard {{
                    background-color: {DesignTokens.BG_INPUT};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: {DesignTokens.RADIUS_MD}px;
                }}
            """)
            self.badge.setText("Hors portée")
            self.badge.set_variant("neutral")


class DocumentEditorWidget(QWidget):
    """Conteneur pour l'éditeur de texte source et la barre d'outils de génération associée."""

    generate_requested = Signal(str, str)  # text_source, source_title
    cancel_requested = Signal()
    album_page_selected = Signal(int)
    edit_scope_requested = Signal()
    clear_scope_requested = Signal()

    def __init__(self, content: str = "", source_title: str = "Saisie Libre", doc_model: Any | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.source_title = source_title
        self._raw_content: str = content
        self._original_content: str = content
        self._scoped_content: str = ""
        self._is_scoped: bool = False
        self._is_showing_full_in_scope: bool = False
        self._scope_title: str = ""
        self._scope_chunks_count: int = 0
        self._album_cards: dict[int, AlbumPageMiniWidget] = {}
        self._album_selected_pages: list[int] = []
        self._audio_player: Any | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.text_scope_banner = TextScopeBannerWidget(self)
        self.text_scope_banner.toggle_display_requested.connect(self.toggle_scope_display)
        self.text_scope_banner.edit_scope_requested.connect(self.edit_scope_requested.emit)
        self.text_scope_banner.clear_scope_requested.connect(self.clear_scope_requested.emit)
        self.text_scope_banner.hide()

        self.doc_model = doc_model
        self.pdf_document = None

        file_type = getattr(self.doc_model, "file_type", "").lower() if self.doc_model else ""

        # --- Segmented Control pour vue Document / Markdown ---
        self.view_toggle_frame = QFrame()
        self.view_toggle_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 2px;
            }}
            QPushButton {{
                background: transparent;
                border: none;
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 4px 12px;
                color: {DesignTokens.TEXT_MUTED};
                font-weight: 500;
            }}
            QPushButton:checked {{
                background: {DesignTokens.ACCENT_PRIMARY};
                color: white;
            }}
        """)
        toggle_layout = QHBoxLayout(self.view_toggle_frame)
        toggle_layout.setContentsMargins(2, 2, 2, 2)
        toggle_layout.setSpacing(0)

        # Boutons adaptatifs selon le type de document
        primary_btn_text = "PDF"
        secondary_btn_text = "Markdown Stylisé"
        if file_type == "album":
            primary_btn_text = "Galerie Planches"
            secondary_btn_text = "Texte & Analyse"
        elif file_type == "pdf":
            primary_btn_text = "PDF"
            secondary_btn_text = "Texte Extrait"
        elif self.doc_model is not None:
            primary_btn_text = "Rendu Stylisé"
            secondary_btn_text = "Source Markdown"

        self.btn_view_pdf = QPushButton(primary_btn_text)
        self.btn_view_pdf.setToolTip("Basculer vers la vue PDF / rendu du document")
        self.btn_view_pdf.setCheckable(True)
        self.btn_view_pdf.setChecked(True)

        self.btn_view_md = QPushButton(secondary_btn_text)
        self.btn_view_md.setToolTip("Basculer vers l'éditeur Markdown extrait")
        self.btn_view_md.setCheckable(True)

        toggle_layout.addWidget(self.btn_view_pdf)
        toggle_layout.addWidget(self.btn_view_md)

        self.btn_view_pdf.clicked.connect(lambda: self._on_view_toggled("pdf"))
        self.btn_view_md.clicked.connect(lambda: self._on_view_toggled("md"))

        toggle_container = QHBoxLayout()
        toggle_container.addStretch()
        toggle_container.addWidget(self.view_toggle_frame)
        toggle_container.addStretch()
        layout.addLayout(toggle_container)

        self.view_toggle_frame.hide()

        self.editor_stack = QStackedWidget()

        # PDF Viewer Container avec bandeau de portée asservi
        self.pdf_container = QWidget()
        pdf_layout = QVBoxLayout(self.pdf_container)
        pdf_layout.setContentsMargins(0, 0, 0, 0)
        pdf_layout.setSpacing(6)

        self._pdf_selected_pages: list[int] = []

        # 1. Bandeau de Portée PDF
        self.pdf_scope_banner = QFrame()
        self.pdf_scope_banner.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 2px 6px;
            }}
        """)
        scope_banner_layout = QHBoxLayout(self.pdf_scope_banner)
        scope_banner_layout.setContentsMargins(6, 4, 6, 4)
        scope_banner_layout.setSpacing(8)

        ico_pdf_scope = QLabel()
        ico_pdf_scope.setPixmap(load_phosphor_icon("ph.sliders", color=DesignTokens.COLOR_BLUE).pixmap(14, 14))
        ico_pdf_scope.setStyleSheet("border: none; background: transparent;")

        self.lbl_pdf_scope_status = QLabel("Portée : Pages 1 à 10")
        self.lbl_pdf_scope_status.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-weight: 600; font-size: 11px; border: none; background: transparent;")

        self.badge_pdf_scope = Badge("Dans la portée", variant="success")

        scope_banner_layout.addWidget(ico_pdf_scope)
        scope_banner_layout.addWidget(self.lbl_pdf_scope_status)
        scope_banner_layout.addWidget(self.badge_pdf_scope)
        scope_banner_layout.addStretch()

        self.btn_pdf_scope_prev = IconButton("ph.caret-left", "Page précédente de la sélection", 16)
        self.btn_pdf_scope_prev.clicked.connect(self._on_pdf_scope_prev)

        self.lbl_pdf_scope_cur = QLabel("Page 1 / 10")
        self.lbl_pdf_scope_cur.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px; font-weight: 600; border: none; background: transparent;")

        self.btn_pdf_scope_next = IconButton("ph.caret-right", "Page suivante de la sélection", 16)
        self.btn_pdf_scope_next.clicked.connect(self._on_pdf_scope_next)

        scope_banner_layout.addWidget(self.btn_pdf_scope_prev)
        scope_banner_layout.addWidget(self.lbl_pdf_scope_cur)
        scope_banner_layout.addWidget(self.btn_pdf_scope_next)

        sep = QLabel("|")
        sep.setStyleSheet(f"color: {DesignTokens.BORDER_COLOR}; font-size: 11px; margin: 0 4px; background: transparent; border: none;")
        scope_banner_layout.addWidget(sep)

        self.btn_pdf_zoom_out = IconButton("ph.magnifying-glass-minus", "Dézoomer (Ctrl -)", 16)
        self.btn_pdf_zoom_out.clicked.connect(self._on_pdf_zoom_out)

        self.lbl_pdf_zoom = QLabel("100%")
        self.lbl_pdf_zoom.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: 600; min-width: 32px; background: transparent; border: none;")
        self.lbl_pdf_zoom.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn_pdf_zoom_in = IconButton("ph.magnifying-glass-plus", "Zoomer (Ctrl +)", 16)
        self.btn_pdf_zoom_in.clicked.connect(self._on_pdf_zoom_in)

        self.btn_pdf_fit_width = IconButton("ph.arrows-out-line-horizontal", "Ajuster à la largeur", 16)
        self.btn_pdf_fit_width.clicked.connect(self._on_pdf_fit_width)

        scope_banner_layout.addWidget(self.btn_pdf_zoom_out)
        scope_banner_layout.addWidget(self.lbl_pdf_zoom)
        scope_banner_layout.addWidget(self.btn_pdf_zoom_in)
        scope_banner_layout.addWidget(self.btn_pdf_fit_width)

        pdf_layout.addWidget(self.pdf_scope_banner)

        try:
            from PySide6.QtPdf import QPdfDocument
            from PySide6.QtPdfWidgets import QPdfView

            self.pdf_document = QPdfDocument(self)
            self.pdf_view = QPdfView()
            self.pdf_view.setDocument(self.pdf_document)
            self.pdf_view.setPageMode(QPdfView.PageMode.MultiPage)
            if hasattr(self.pdf_view, "pageNavigator"):
                self.pdf_view.pageNavigator().currentPageChanged.connect(self._on_pdf_page_changed)
            if hasattr(self.pdf_view, "viewport"):
                self.pdf_view.viewport().installEventFilter(self)
            self.pdf_view.installEventFilter(self)
            pdf_layout.addWidget(self.pdf_view, 1)
        except ImportError:
            self.pdf_view = QWidget()
            pdf_layout.addWidget(self.pdf_view, 1)

        self.editor_stack.addWidget(self.pdf_container)

        self.raw_editor = StyledTextEdit()
        self.raw_editor.setStyleSheet(f"font-family: '{DesignTokens.FONT_CODE}';")
        self.raw_editor.setPlaceholderText("Saisissez ou collez directement votre extrait de cours ici (ex: notes de cours, résumés, chapitres PDF)...")
        self.raw_editor.textChanged.connect(self._on_text_changed)

        self.markdown_viewer = QTextBrowser()
        self.markdown_viewer.setOpenExternalLinks(True)
        self.markdown_viewer.setStyleSheet(
            f"background-color: {DesignTokens.BG_INPUT}; "
            f"color: {DesignTokens.TEXT_PRIMARY}; "
            f"border: 1px solid {DesignTokens.BORDER_COLOR}; "
            f"border-radius: {DesignTokens.RADIUS_SM}px; "
            f"padding: 12px; "
            f"font-family: '{DesignTokens.FONT_MAIN}';"
        )

        self.editor_stack.addWidget(self.raw_editor)
        self.editor_stack.addWidget(self.markdown_viewer)

        if self.doc_model:
            if file_type == "pdf" and getattr(self.doc_model, "original_media", None):
                pdf_path = resolve_media_path(self.doc_model.original_media.filename)
                if pdf_path.exists() and self.pdf_document is not None:
                    self.pdf_document.load(str(pdf_path))
                self.view_toggle_frame.show()
                self._on_view_toggled("pdf")
            elif file_type == "album":
                self._init_album_container()
                self.view_toggle_frame.show()
                self._on_view_toggled("pdf")
            elif file_type in ("audio", "mp3", "m4a", "wav", "ogg", "flac", "aac"):
                self._init_audio_bar()
                self.view_toggle_frame.show()
                self._on_view_toggled("pdf")
            else:
                self.view_toggle_frame.show()
                self._on_view_toggled("pdf")

        layout.addWidget(self.text_scope_banner)
        layout.addWidget(self.editor_stack, 1)

        bot_widget = QWidget()
        bot_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        bot_widget.setStyleSheet("background: transparent;")
        bot_layout = QHBoxLayout(bot_widget)
        bot_layout.setContentsMargins(0, 6, 0, 0)

        self.tokens_lbl = QLabel("Aa 0 chars  |  ~0 Tokens")
        self.tokens_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-family: '{DesignTokens.FONT_CODE}'; font-size: 11px;")
        bot_layout.addWidget(self.tokens_lbl)
        bot_layout.addStretch()

        self.btn_paste = SecondaryButton("Coller", tooltip="Coller le contenu du presse-papier (Ctrl+V)")
        self.btn_paste.setIcon(load_phosphor_icon("ph.clipboard", color=DesignTokens.TEXT_PRIMARY))
        self.btn_paste.clicked.connect(self.raw_editor.paste)

        self.btn_generate = PrimaryButton("Générer (Ctrl+Enter)", tooltip="Lancer la forge des flashcards avec le modèle IA sélectionné (Ctrl+Entrée)")
        self.btn_generate.setIcon(load_on_accent_icon("ph.play"))
        self.btn_generate.clicked.connect(self._on_generate_clicked)

        self.btn_cancel = DangerButton("Arrêter", ghost=True, tooltip="Interrompre la génération de cartes en cours")
        self.btn_cancel.setIcon(load_phosphor_icon("ph.stop-circle", color=DesignTokens.COLOR_RED))
        self.btn_cancel.hide()
        self.btn_cancel.clicked.connect(self.cancel_requested.emit)

        bot_layout.addWidget(self.btn_paste)
        bot_layout.addWidget(self.btn_generate)
        bot_layout.addWidget(self.btn_cancel)
        layout.addWidget(bot_widget)

        self.set_content(content)

    def _init_album_container(self) -> None:
        """Initialise la galerie miniature des planches d'album."""
        try:
            from ankiforge.database.models import DocumentChunkModel, DocumentPageModel

            self.album_container = QWidget()
            album_layout = QVBoxLayout(self.album_container)
            album_layout.setContentsMargins(0, 0, 0, 0)
            album_layout.setSpacing(6)

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setStyleSheet("background: transparent; border: none;")

            scroll_content = QWidget()
            scroll_content.setStyleSheet("background: transparent;")
            album_grid = QGridLayout(scroll_content)
            album_grid.setContentsMargins(8, 8, 8, 8)
            album_grid.setSpacing(12)

            pages = list(DocumentPageModel.select().where(DocumentPageModel.document == self.doc_model).order_by(DocumentPageModel.page_number))

            visual_chunks = {
                c.page_number: c.content
                for c in DocumentChunkModel.select().where((DocumentChunkModel.document == self.doc_model) & DocumentChunkModel.page_number.is_null(False))
                if c.page_number is not None
            }

            cols = 3
            for i, page in enumerate(pages):
                media_path = resolve_media_path(page.media.filename) if (page.media and page.media.filename) else None
                desc = page.ocr_text or visual_chunks.get(page.page_number, "")
                card = AlbumPageMiniWidget(page_num=page.page_number, media_path=media_path, snippet=desc)
                card.clicked.connect(self._on_album_mini_card_clicked)
                self._album_cards[page.page_number] = card
                album_grid.addWidget(card, i // cols, i % cols)

            album_grid.setRowStretch((len(pages) + cols - 1) // cols, 1)
            scroll.setWidget(scroll_content)
            album_layout.addWidget(scroll)
            self.editor_stack.addWidget(self.album_container)
        except Exception as e:
            logger.warning("Erreur lors de l'initialisation de l'aperçu d'album : %s", e)

    def _init_audio_bar(self) -> None:
        """Initialise la barre de contrôle audio interactif."""
        try:
            self.audio_bar = QFrame()
            self.audio_bar.setStyleSheet(f"""
                QFrame {{
                    background-color: {DesignTokens.BG_INPUT};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: {DesignTokens.RADIUS_SM}px;
                    padding: 2px 6px;
                }}
            """)
            audio_layout = QHBoxLayout(self.audio_bar)
            audio_layout.setContentsMargins(6, 4, 6, 4)
            audio_layout.setSpacing(8)

            ico = QLabel()
            ico.setPixmap(load_phosphor_icon("ph.waveform", color=DesignTokens.COLOR_GREEN).pixmap(16, 16))
            ico.setStyleSheet("border: none; background: transparent;")

            self.btn_audio_play = IconButton("ph.play", "Lecture / Pause", 16)
            self.lbl_audio_title = QLabel(self.doc_model.title if self.doc_model else "Audio")
            self.lbl_audio_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px; font-weight: 600; border: none; background: transparent;")

            self.lbl_audio_time = QLabel("00:00 / 00:00")
            self.lbl_audio_time.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-family: '{DesignTokens.FONT_CODE}'; border: none; background: transparent;")

            audio_layout.addWidget(ico)
            audio_layout.addWidget(self.btn_audio_play)
            audio_layout.addWidget(self.lbl_audio_title)
            audio_layout.addStretch()
            audio_layout.addWidget(self.lbl_audio_time)

            from PySide6.QtCore import QUrl
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

            self._audio_player = QMediaPlayer(self)
            self._audio_output = QAudioOutput(self)
            self._audio_player.setAudioOutput(self._audio_output)

            media = getattr(self.doc_model, "original_media", None)
            if media and media.filename:
                file_path = resolve_media_path(media.filename)
                if file_path.exists():
                    self._audio_player.setSource(QUrl.fromLocalFile(str(file_path)))

            self.btn_audio_play.clicked.connect(self._toggle_audio_play)
            self._audio_player.positionChanged.connect(self._on_audio_pos_changed)
            self._audio_player.durationChanged.connect(self._on_audio_duration_changed)

            self.layout().insertWidget(1, self.audio_bar)
        except Exception as e:
            logger.debug("Erreur ou absence de QtMultimedia pour barre audio: %s", e)
            self._audio_player = None

    @Slot(int)
    def _on_album_mini_card_clicked(self, page_num: int) -> None:
        self.album_page_selected.emit(page_num)

    def set_album_scope(self, pages: list[int]) -> None:
        """Met à jour la portée active de l'album et asservit les mini-cartes."""
        self._album_selected_pages = sorted(pages)
        for p_num, card in self._album_cards.items():
            card.set_in_scope(p_num in self._album_selected_pages)

    def _toggle_audio_play(self) -> None:
        if self._audio_player is None:
            return
        from PySide6.QtMultimedia import QMediaPlayer

        if self._audio_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._audio_player.pause()
            self.btn_audio_play.setIcon(load_phosphor_icon("ph.play", color=DesignTokens.TEXT_PRIMARY))
        else:
            self._audio_player.play()
            self.btn_audio_play.setIcon(load_phosphor_icon("ph.pause", color=DesignTokens.TEXT_PRIMARY))

    def _on_audio_pos_changed(self, pos_ms: int) -> None:
        if self._audio_player is None:
            return
        dur_ms = self._audio_player.duration()
        pos_s = pos_ms // 1000
        dur_s = dur_ms // 1000
        self.lbl_audio_time.setText(f"{pos_s // 60:02d}:{pos_s % 60:02d} / {dur_s // 60:02d}:{dur_s % 60:02d}")

    def _on_audio_duration_changed(self, dur_ms: int) -> None:
        self._on_audio_pos_changed(self._audio_player.position() if self._audio_player else 0)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._audio_player is not None:
            self._audio_player.stop()
        super().closeEvent(event)

    @Slot(str)
    def _on_view_toggled(self, mode: str) -> None:
        self.btn_view_pdf.setChecked(mode == "pdf")
        self.btn_view_md.setChecked(mode == "md")

        file_type = getattr(self.doc_model, "file_type", "").lower() if self.doc_model else ""

        if mode == "pdf":
            if file_type == "album" and hasattr(self, "album_container"):
                self.editor_stack.setCurrentWidget(self.album_container)
            elif file_type == "pdf":
                self.editor_stack.setCurrentWidget(self.pdf_container)
            else:
                self.editor_stack.setCurrentWidget(self.markdown_viewer)
        else:
            if file_type in ("pdf", "album"):
                self.editor_stack.setCurrentWidget(self.markdown_viewer)
            else:
                self.editor_stack.setCurrentWidget(self.raw_editor)

        if hasattr(self, "text_scope_banner"):
            if mode == "pdf" and file_type == "pdf":
                self.text_scope_banner.hide()
            elif self._is_scoped:
                self.text_scope_banner.show()
            else:
                self.text_scope_banner.hide()

    def set_pdf_scope(self, pages: list[int]) -> None:
        """Met à jour la portée active du PDF et asservit le bandeau de navigation."""
        self._pdf_selected_pages = sorted(pages)
        if not self._pdf_selected_pages:
            self.lbl_pdf_scope_status.setText("Aucune page sélectionnée")
            self.badge_pdf_scope.setText("0 page")
            self.badge_pdf_scope.set_variant("danger")
            return

        count = len(self._pdf_selected_pages)
        first_p = self._pdf_selected_pages[0]

        from ankiforge.ui.views.creation_view.utils import format_page_ranges

        range_str = format_page_ranges(self._pdf_selected_pages)
        if count == 1:
            self.lbl_pdf_scope_status.setText(f"Portée : Page {first_p}")
        else:
            self.lbl_pdf_scope_status.setText(f"Portée : Pages {range_str} ({count} pages)")

        self.jump_pdf_to_page(first_p - 1)
        self._update_scope_indicator(first_p - 1)

    @Slot(int)
    def _on_pdf_page_changed(self, current_page_idx: int) -> None:
        self._update_scope_indicator(current_page_idx)

    def _update_scope_indicator(self, current_page_idx: int) -> None:
        if not self._pdf_selected_pages:
            return

        current_1_based = current_page_idx + 1
        if current_1_based in self._pdf_selected_pages:
            idx_in_scope = self._pdf_selected_pages.index(current_1_based) + 1
            self.badge_pdf_scope.setText("Dans la portée")
            self.badge_pdf_scope.set_variant("success")
            self.lbl_pdf_scope_cur.setText(f"Sélection {idx_in_scope} / {len(self._pdf_selected_pages)} (p. {current_1_based})")
        else:
            self.badge_pdf_scope.setText(f"Hors-portée (p. {current_1_based})")
            self.badge_pdf_scope.set_variant("warning")
            self.lbl_pdf_scope_cur.setText(f"Page {current_1_based}")

    @Slot()
    def _on_pdf_scope_prev(self) -> None:
        if not self._pdf_selected_pages or not hasattr(self, "pdf_view") or not hasattr(self.pdf_view, "pageNavigator"):
            return
        cur_p = self.pdf_view.pageNavigator().currentPage() + 1
        prev_candidates = [p for p in self._pdf_selected_pages if p < cur_p]
        if prev_candidates:
            self.jump_pdf_to_page(prev_candidates[-1] - 1)
        else:
            self.jump_pdf_to_page(self._pdf_selected_pages[0] - 1)

    @Slot()
    def _on_pdf_scope_next(self) -> None:
        if not self._pdf_selected_pages or not hasattr(self, "pdf_view") or not hasattr(self.pdf_view, "pageNavigator"):
            return
        cur_p = self.pdf_view.pageNavigator().currentPage() + 1
        next_candidates = [p for p in self._pdf_selected_pages if p > cur_p]
        if next_candidates:
            self.jump_pdf_to_page(next_candidates[0] - 1)
        else:
            self.jump_pdf_to_page(self._pdf_selected_pages[-1] - 1)

    @Slot()
    def _on_pdf_zoom_in(self) -> None:
        if hasattr(self, "pdf_view") and hasattr(self.pdf_view, "setZoomFactor"):
            from PySide6.QtPdfWidgets import QPdfView

            self.pdf_view.setZoomMode(QPdfView.ZoomMode.Custom)
            new_factor = min(3.0, self.pdf_view.zoomFactor() * 1.2)
            self.pdf_view.setZoomFactor(new_factor)
            self.lbl_pdf_zoom.setText(f"{int(new_factor * 100)}%")

    @Slot()
    def _on_pdf_zoom_out(self) -> None:
        if hasattr(self, "pdf_view") and hasattr(self.pdf_view, "setZoomFactor"):
            from PySide6.QtPdfWidgets import QPdfView

            self.pdf_view.setZoomMode(QPdfView.ZoomMode.Custom)
            new_factor = max(0.4, self.pdf_view.zoomFactor() / 1.2)
            self.pdf_view.setZoomFactor(new_factor)
            self.lbl_pdf_zoom.setText(f"{int(new_factor * 100)}%")

    @Slot()
    def _on_pdf_fit_width(self) -> None:
        if hasattr(self, "pdf_view") and hasattr(self.pdf_view, "setZoomMode"):
            from PySide6.QtPdfWidgets import QPdfView

            self.pdf_view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
            self.lbl_pdf_zoom.setText("Auto")

    def eventFilter(self, obj: Any, event: Any) -> bool:
        if hasattr(self, "pdf_view") and (obj == self.pdf_view or (hasattr(self.pdf_view, "viewport") and obj == self.pdf_view.viewport())) and event.type() == QEvent.Type.Wheel:
            modifiers = event.modifiers()
            if modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier):
                delta = event.angleDelta().y()
                if delta > 0:
                    self._on_pdf_zoom_in()
                elif delta < 0:
                    self._on_pdf_zoom_out()
                return True
        return super().eventFilter(obj, event)

    def jump_pdf_to_page(self, page_index: int) -> None:
        if hasattr(self, "pdf_view") and hasattr(self.pdf_view, "pageNavigator"):
            from PySide6.QtCore import QPointF

            self.pdf_view.pageNavigator().jump(page_index, QPointF(0, 0), self.pdf_view.zoomFactor())

    def set_document(self, doc: Any | None) -> None:
        """Bascule dynamiquement le document affiché (utilisé par le Laboratoire A/B).

        - ``None`` : retour au mode texte libre (toggle masqué, éditeur brut).
        - PDF : charge le PDF (vue PDF + Texte Extrait).
        - Album : galerie planches (vue Galerie + Texte & Analyse).
        - Autre (md/docx/html/...) : Rendu Stylisé + Source Markdown.
        """
        self._pdf_selected_pages = []
        self.doc_model = doc
        file_type = getattr(doc, "file_type", "").lower() if doc else ""

        if doc is None:
            self.view_toggle_frame.hide()
            self._raw_content = ""
            self.raw_editor.setPlainText("")
            self.markdown_viewer.setHtml("")
            self._on_text_changed()
            self.editor_stack.setCurrentWidget(self.raw_editor)
            return

        raw = getattr(doc, "content", "") or getattr(doc, "text_content", "") or ""
        self._original_content = raw
        self._raw_content = raw
        self.clear_scoped_extract()
        self.raw_editor.setPlainText(raw)
        self.markdown_viewer.setHtml(markdown.markdown(raw, extensions=["fenced_code", "tables"]))

        if file_type == "pdf":
            self.btn_view_pdf.setText("PDF")
            self.btn_view_md.setText("Texte Extrait")
            self.view_toggle_frame.show()
            media = getattr(doc, "original_media", None)
            if media and getattr(media, "filename", None) and hasattr(self, "pdf_document") and self.pdf_document is not None:
                pdf_path = resolve_media_path(media.filename)
                if pdf_path.exists():
                    self.pdf_document.load(str(pdf_path))
            self.btn_view_pdf.setChecked(True)
            self._on_view_toggled("pdf")
        elif file_type == "album":
            if not hasattr(self, "album_container"):
                self._init_album_container()
            self.btn_view_pdf.setText("Galerie Planches")
            self.btn_view_md.setText("Texte & Analyse")
            self.view_toggle_frame.show()
            self.btn_view_pdf.setChecked(True)
            self._on_view_toggled("pdf")
        else:
            self.btn_view_pdf.setText("Rendu Stylisé")
            self.btn_view_md.setText("Source Markdown")
            self.view_toggle_frame.show()
            self.btn_view_pdf.setChecked(True)
            self._on_view_toggled("pdf")
        self._on_text_changed()

    def set_content(self, content: str) -> None:
        self._original_content = content
        self._raw_content = content
        self.raw_editor.setPlainText(content)
        html = markdown.markdown(content, extensions=["fenced_code", "tables"])
        self.markdown_viewer.setHtml(html)

        if self.doc_model is None:
            self.editor_stack.setCurrentWidget(self.raw_editor)
        else:
            if hasattr(self, "btn_view_pdf") and self.btn_view_pdf.isChecked():
                self._on_view_toggled("pdf")
            else:
                if hasattr(self, "btn_view_md"):
                    self.btn_view_md.setChecked(True)
                self._on_view_toggled("md")
        self._on_text_changed()

    def set_scoped_extract(self, scoped_text: str, scope_title: str = "", chunks_count: int = 0, is_scoped: bool = True) -> None:
        """Définit l'extrait filtré à afficher dans l'éditeur textuel tout en préservant le texte d'origine."""
        self._scoped_content = scoped_text
        self._scope_title = scope_title
        self._scope_chunks_count = chunks_count
        self._is_scoped = is_scoped
        self._is_showing_full_in_scope = False

        if is_scoped and scoped_text.strip():
            self.text_scope_banner.set_scope_info(scope_title or "Extrait sélectionné", chunks_count, is_showing_full=False)
            file_type = getattr(self.doc_model, "file_type", "").lower() if self.doc_model else ""
            is_in_pdf_mode = hasattr(self, "btn_view_pdf") and self.btn_view_pdf.isChecked() and file_type == "pdf"
            if not is_in_pdf_mode:
                self.text_scope_banner.show()
            self._apply_text_to_editors(scoped_text)
        else:
            self.clear_scoped_extract()

    def clear_scoped_extract(self) -> None:
        """Efface le filtre de portée textuel et restaure le contenu intégral du document."""
        self._is_scoped = False
        self._is_showing_full_in_scope = False
        self._scoped_content = ""
        self._scope_title = ""
        self._scope_chunks_count = 0
        if hasattr(self, "text_scope_banner"):
            self.text_scope_banner.hide()
        if hasattr(self, "_original_content") and self._original_content:
            self._apply_text_to_editors(self._original_content)

    def toggle_scope_display(self) -> None:
        """Alterne entre l'affichage de l'extrait filtré et celui du document complet sans perdre la portée."""
        if not self._is_scoped:
            return
        self._is_showing_full_in_scope = not self._is_showing_full_in_scope
        self.text_scope_banner.set_scope_info(self._scope_title, self._scope_chunks_count, is_showing_full=self._is_showing_full_in_scope)
        if self._is_showing_full_in_scope:
            self._apply_text_to_editors(self._original_content)
        else:
            self._apply_text_to_editors(self._scoped_content)

    def _apply_text_to_editors(self, text: str) -> None:
        self._raw_content = text
        self.raw_editor.blockSignals(True)
        self.raw_editor.setPlainText(text)
        self.raw_editor.blockSignals(False)
        html = markdown.markdown(text, extensions=["fenced_code", "tables"])
        self.markdown_viewer.setHtml(html)
        self._on_text_changed()

    def get_original_content(self) -> str:
        """Retourne le contenu intégral du document d'origine."""
        return getattr(self, "_original_content", "") or self._raw_content

    def highlight_or_scroll_to_text(self, snippet: str, page_number: int | None = None) -> None:
        """Scrolle et met en surbrillance l'extrait spécifié dans l'éditeur textuel, et saute à la page PDF."""
        if page_number is not None:
            self.jump_pdf_to_page(page_number - 1)

        clean_snippet = snippet.strip()
        if not clean_snippet:
            return

        search_str = clean_snippet[:60]
        pos = self.raw_editor.toPlainText().find(search_str)
        if pos != -1:
            cursor = self.raw_editor.textCursor()
            cursor.setPosition(pos)
            cursor.setPosition(pos + len(search_str), QTextCursor.MoveMode.KeepAnchor)
            self.raw_editor.setTextCursor(cursor)
            self.raw_editor.ensureCursorVisible()

        self.markdown_viewer.find(search_str)

    @Slot()
    def _on_text_changed(self) -> None:
        text = self.get_text()
        chars = len(text)
        words = len(text.split())
        estimated_tokens = int(words * 1.3)
        self.tokens_lbl.setText(f"Aa {chars} chars  |  ~{estimated_tokens} Tokens")

    @Slot()
    def _on_generate_clicked(self) -> None:
        self.generate_requested.emit(self.get_text(), getattr(self, "source_title", "Saisie Libre"))

    def get_text(self) -> str:
        text = self.raw_editor.toPlainText().strip()
        if text:
            return text
        if hasattr(self, "_raw_content") and self._raw_content:
            return self._raw_content.strip()
        return self.markdown_viewer.toPlainText().strip()

    def set_generation_state(self, is_generating: bool) -> None:
        self.btn_generate.setEnabled(not is_generating)
        if is_generating:
            self.btn_generate.hide()
            self.btn_cancel.show()
        else:
            self.btn_generate.show()
            self.btn_cancel.hide()
