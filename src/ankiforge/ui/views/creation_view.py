"""
Studio de Création AnkiForge — 100% Conforme aux Exigences & Raccordement Métier (master).
- Sélection des paquets raccordée à DeckModel.select() + sélecteur et création dynamique (+ Nouveau).
- Détection et auto-seeding automatique des Moteurs IA (LLMConfigModel) avec affichage display_name.
- Détection et auto-seeding automatique des Pipelines Agentiques (PipelineModel).
- Carte visuelle interactive cliquable pour l'Activation de la Vision (PDF / Schémas / Figures) avec retours visuels dorés.
- Sélection de documents (DocumentModel) avec gestion du cas vide -> bouton "Mes Documents" + bouton "Coller le presse-papiers".
- Intégration complète CreationWorker, NoteManager.create_note et CardPreviewWidget.
"""

import json
import logging
import markdown
from typing import Any, Optional, cast

from PySide6.QtCore import Qt, Signal, Slot, QThreadPool, QEvent
from PySide6.QtGui import QCloseEvent, QColor, QKeyEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import (
    DeckModel,
    DocumentChunkModel,
    DocumentModel,
    FolderModel,
    LLMConfigModel,
    NoteChunkLinkModel,
    NoteTypeModel,
    PipelineModel,
)
from ankiforge.services.ai.orchestrator import PipelineOrchestrator
from ankiforge.services.ai.state import PipelineRunState
from ankiforge.services.ai.utils import extract_cards_from_data
from ankiforge.services.cards.note_manager import NoteManager
from ankiforge.ui.dialogs.human_validation_dialog import HumanValidationDialog
from ankiforge.ui.components import (
    Badge,
    StatusBadge,
    DangerButton,
    IconButton,
    IdePanel,
    PrimaryButton,
    SecondaryButton,
    StyledComboBox,
    StyledTableWidget,
    StyledTextEdit,
)
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.card_preview_widget import CardPreviewWidget
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon
from ankiforge.ui.dialogs.selection_dialog import MultiSelectionDialog
from ankiforge.ui.components.deck_select_window import DeckSelectWindow
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem

logger = logging.getLogger(__name__)


class VisionCard(QFrame):
    """Carte interactive cliquable pour l'activation du mode Vision."""

    clicked = Signal()

    def mousePressEvent(self, event: Any) -> None:
        super().mousePressEvent(event)
        self.clicked.emit()


class CardEditDialog(QDialog):
    """Dialogue d'édition rapide d'une carte générée."""

    def __init__(self, front: str, back: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Éditer la carte")
        self.setMinimumWidth(500)
        self.setStyleSheet(f"background-color: {DesignTokens.BG_MAIN};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        lbl_front = QLabel("Recto :")
        lbl_front.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: bold;")
        self.edit_front = StyledTextEdit()
        self.edit_front.setPlainText(front)
        self.edit_front.setFixedHeight(100)

        lbl_back = QLabel("Verso :")
        lbl_back.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: bold;")
        self.edit_back = StyledTextEdit()
        self.edit_back.setPlainText(back)
        self.edit_back.setFixedHeight(120)

        layout.addWidget(lbl_front)
        layout.addWidget(self.edit_front)
        layout.addWidget(lbl_back)
        layout.addWidget(self.edit_back)

        btn_box = QHBoxLayout()
        btn_box.addStretch()

        btn_cancel = SecondaryButton("Annuler")
        btn_cancel.clicked.connect(self.reject)

        btn_save = PrimaryButton("Enregistrer")
        btn_save.clicked.connect(self.accept)

        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_save)

        layout.addLayout(btn_box)

    def get_data(self) -> tuple[str, str]:
        return self.edit_front.toPlainText().strip(), self.edit_back.toPlainText().strip()


class FlashcardPreview(QWidget):
    """Composant d'inspection et de validation des cartes générées."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"background-color: {DesignTokens.BG_PANEL};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Barre supérieure de navigation dans les résultats
        top_toolbar = QHBoxLayout()
        self.btn_prev = IconButton("ph.caret-left", "Carte précédente", 24)
        self.btn_next = IconButton("ph.caret-right", "Carte suivante", 24)
        self.lbl_counter = QLabel("0 / 0")
        self.lbl_counter.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-family: {DesignTokens.FONT_CODE}; font-weight: bold;")

        top_toolbar.addWidget(self.btn_prev)
        top_toolbar.addWidget(self.lbl_counter)
        top_toolbar.addWidget(self.btn_next)
        top_toolbar.addStretch()

        layout.addLayout(top_toolbar)

        # Intégration de CardPreviewWidget (Moteur WebEngine + MathJax + multi-appareils)
        self.card_preview_widget = CardPreviewWidget(show_header=False)
        layout.addWidget(self.card_preview_widget, 1)


class DocumentEditorWidget(QWidget):
    """Conteneur pour l'éditeur de texte source et la barre d'outils de génération associée."""

    generate_requested = Signal(str, str)  # text_source, source_title
    cancel_requested = Signal()

    def __init__(self, content: str = "", source_title: str = "Saisie Libre", doc_model: Optional[Any] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.source_title = source_title
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.doc_model = doc_model
        self.pdf_document = None

        # --- Segmented Control pour vue PDF / Markdown ---
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

        self.btn_view_pdf = QPushButton("PDF")
        self.btn_view_pdf.setCheckable(True)
        self.btn_view_pdf.setChecked(True)

        self.btn_view_md = QPushButton("Markdown Stylisé")
        self.btn_view_md.setCheckable(True)

        toggle_layout.addWidget(self.btn_view_pdf)
        toggle_layout.addWidget(self.btn_view_md)

        self.btn_view_pdf.clicked.connect(lambda: self._on_view_toggled("pdf"))
        self.btn_view_md.clicked.connect(lambda: self._on_view_toggled("md"))

        # Center the toggle horizontally
        toggle_container = QHBoxLayout()
        toggle_container.addStretch()
        toggle_container.addWidget(self.view_toggle_frame)
        toggle_container.addStretch()
        layout.addLayout(toggle_container)

        # Hide by default, show only if it's a PDF
        self.view_toggle_frame.hide()

        self.editor_stack = QStackedWidget()

        # PDF Viewer
        try:
            from PySide6.QtPdf import QPdfDocument
            from PySide6.QtPdfWidgets import QPdfView

            self.pdf_document = QPdfDocument(self)
            self.pdf_view = QPdfView()
            self.pdf_view.setDocument(self.pdf_document)
            self.pdf_view.setPageMode(QPdfView.PageMode.MultiPage)
            self.editor_stack.addWidget(self.pdf_view)
        except ImportError:
            self.pdf_view = QWidget()  # Fallback
            self.editor_stack.addWidget(self.pdf_view)

        self.raw_editor = StyledTextEdit()
        self.raw_editor.setStyleSheet(f"font-family: '{DesignTokens.FONT_CODE}';")
        self.raw_editor.setPlaceholderText("📝 Saisissez ou collez directement votre extrait de cours ici (ex: notes de cours, résumés, chapitres PDF)...")
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

        # Load PDF if applicable
        if self.doc_model and getattr(self.doc_model, "file_type", "") == "pdf" and getattr(self.doc_model, "original_media", None):
            from ankiforge.utils.paths import get_app_data_dir

            pdf_path = get_app_data_dir() / "media" / self.doc_model.original_media.filename
            if pdf_path.exists() and self.pdf_document is not None:
                self.pdf_document.load(str(pdf_path))
                self.view_toggle_frame.show()
                self._on_view_toggled("md")  # Default to Markdown
        layout.addWidget(self.editor_stack, 1)

        bot_widget = QWidget()
        bot_widget.setStyleSheet("background: transparent;")
        bot_layout = QHBoxLayout(bot_widget)
        bot_layout.setContentsMargins(0, 8, 0, 0)

        self.tokens_lbl = QLabel("Aa 0 chars  |  ~0 Tokens")
        self.tokens_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-family: '{DesignTokens.FONT_CODE}'; font-size: 11px;")
        bot_layout.addWidget(self.tokens_lbl)
        bot_layout.addStretch()

        self.btn_paste = SecondaryButton("Coller")
        self.btn_paste.setIcon(load_phosphor_icon("ph.clipboard", color=DesignTokens.TEXT_PRIMARY))
        self.btn_paste.clicked.connect(self.raw_editor.paste)

        self.btn_generate = PrimaryButton("Générer (Ctrl+Enter)")
        self.btn_generate.setIcon(load_phosphor_icon("ph.play", color="white"))
        self.btn_generate.clicked.connect(self._on_generate_clicked)

        self.btn_cancel = DangerButton("Arrêter", ghost=True)
        self.btn_cancel.setIcon(load_phosphor_icon("ph.stop-circle", color=DesignTokens.COLOR_RED))
        self.btn_cancel.hide()
        self.btn_cancel.clicked.connect(self.cancel_requested.emit)

        bot_layout.addWidget(self.btn_paste)
        bot_layout.addWidget(self.btn_generate)
        bot_layout.addWidget(self.btn_cancel)
        layout.addWidget(bot_widget)

        self.set_content(content)

    @Slot(str)
    def _on_view_toggled(self, mode: str) -> None:
        self.btn_view_pdf.setChecked(mode == "pdf")
        self.btn_view_md.setChecked(mode == "md")

        if mode == "pdf":
            self.editor_stack.setCurrentWidget(self.pdf_view)
        else:
            self.editor_stack.setCurrentWidget(self.markdown_viewer)

    def jump_pdf_to_page(self, page_index: int) -> None:
        if hasattr(self, "pdf_view") and hasattr(self.pdf_view, "pageNavigator"):
            from PySide6.QtCore import QPointF

            self.pdf_view.pageNavigator().jump(page_index, QPointF(0, 0), self.pdf_view.zoomFactor())

    def set_content(self, content: str) -> None:
        if self.source_title == "Saisie Libre":
            self.editor_stack.setCurrentWidget(self.raw_editor)
            self.raw_editor.setPlainText(content)
        else:
            if hasattr(self, "btn_view_md") and not self.btn_view_md.isChecked():
                self.btn_view_md.setChecked(True)
                self.btn_view_pdf.setChecked(False)
            self.editor_stack.setCurrentWidget(self.markdown_viewer)
            html = markdown.markdown(content, extensions=["fenced_code", "tables"])
            self.markdown_viewer.setHtml(html)
        self._on_text_changed()

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
        if self.source_title == "Saisie Libre":
            return self.raw_editor.toPlainText().strip()
        else:
            return self.markdown_viewer.toPlainText().strip()

    def set_generation_state(self, is_generating: bool) -> None:
        self.btn_generate.setEnabled(not is_generating)
        if is_generating:
            self.btn_generate.hide()
            self.btn_cancel.show()
        else:
            self.btn_generate.show()
            self.btn_cancel.hide()


class CreationView(QWidget):
    """
    Studio de Création AnkiForge.
    Signal request_navigation(str) pour basculer vers d'autres vues (documents, pipelines, settings).
    """

    request_navigation = Signal(str, object)

    def __init__(self, ai_manager: Any = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager
        self.generated_cards: list[dict[str, Any]] = []
        self.current_preview_index = 0
        self.orchestrator: Optional[PipelineOrchestrator] = None
        self.current_deck: Optional[DeckModel] = None
        self.current_model: Optional[NoteTypeModel] = None
        self.selected_models: list[NoteTypeModel] = []
        self.current_source_title: str = "Saisie Libre"
        self.decks_cache: list[DeckModel] = []
        self._deck_modal: Optional[DeckSelectWindow] = None
        self.models_cache: list[NoteTypeModel] = []
        self.open_editors: dict[str, DocumentEditorWidget] = {}
        self.thread_pool = QThreadPool(self)

        self._setup_ui()
        self._connect_signals()
        self.refresh_data()

    def _navigate(self, view_id: str, data: Optional[dict] = None) -> None:
        self.request_navigation.emit(view_id, data)

    def _setup_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.main_splitter)

        # --- COL 1: Left Tool Window (Explorateur + Config IA) ---
        self.config_panel = IdePanel(detachable=True)
        self.config_panel.setMinimumWidth(260)
        self.config_panel.setStyleSheet(f"border-right: 1px solid {DesignTokens.BORDER_COLOR};")

        # Tab 1: Explorateur
        explorer_content = QWidget()
        explorer_layout = QVBoxLayout(explorer_content)
        explorer_layout.setContentsMargins(10, 10, 10, 10)
        explorer_layout.setSpacing(8)

        self.btn_new_free_input = SecondaryButton("Nouvelle Saisie Libre")
        self.btn_new_free_input.setIcon(load_phosphor_icon("ph.plus", color=DesignTokens.TEXT_PRIMARY))
        explorer_layout.addWidget(self.btn_new_free_input)

        self.file_tree = QTreeWidget()
        self.file_tree.setHeaderHidden(True)
        self.file_tree.setStyleSheet(f"""
            QTreeWidget {{
                background-color: transparent;
                border: none;
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QTreeWidget::item {{
                padding: 4px;
                border-radius: 4px;
            }}
            QTreeWidget::item:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
            QTreeWidget::item:selected {{
                background-color: {DesignTokens.BG_ACTIVE};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)
        explorer_layout.addWidget(self.file_tree)

        # Tab 2: Config IA
        config_content = QWidget()
        config_layout = QVBoxLayout(config_content)
        config_layout.setContentsMargins(12, 12, 12, 12)
        config_layout.setSpacing(16)

        def add_form_group(layout: QVBoxLayout, label_text: str, widget_or_layout: Any) -> None:
            lbl = QLabel(label_text)
            lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-weight: 600; font-size: 11px;")
            layout.addWidget(lbl)
            if isinstance(widget_or_layout, QWidget):
                layout.addWidget(widget_or_layout)
            else:
                layout.addLayout(widget_or_layout)

        # 1. Paquet Cible (Bouton Sélecteur)
        self.btn_select_deck = SecondaryButton("Sélectionner un paquet...")
        self.btn_select_deck.setIcon(load_phosphor_icon("ph.folder-open", color=DesignTokens.TEXT_MUTED))
        self.btn_select_deck.setStyleSheet(
            f"text-align: left; padding: 6px 10px; border-radius: 4px; border: 1px solid {DesignTokens.BORDER_COLOR}; background: {DesignTokens.BG_INPUT}; font-weight: normal;"
        )
        add_form_group(config_layout, "PAQUET CIBLE", self.btn_select_deck)

        # 2. Modèle de Carte (Bouton Sélecteur)
        self.btn_select_model = SecondaryButton("Sélectionner un modèle...")
        self.btn_select_model.setIcon(load_phosphor_icon("ph.file-code", color=DesignTokens.TEXT_MUTED))
        self.btn_select_model.setStyleSheet(
            f"text-align: left; padding: 6px 10px; border-radius: 4px; border: 1px solid {DesignTokens.BORDER_COLOR}; background: {DesignTokens.BG_INPUT}; font-weight: normal;"
        )
        add_form_group(config_layout, "MODÈLE DE CARTE", self.btn_select_model)

        # 3. Moteur IA + Bouton d'aide si vide
        self.engine_combo = StyledComboBox()
        add_form_group(config_layout, "MOTEUR IA :", self.engine_combo)

        self.btn_no_engine_help = SecondaryButton("⚙️ Configurer les Moteurs IA")
        self.btn_no_engine_help.setStyleSheet(f"color: {DesignTokens.COLOR_YELLOW}; border: 1px solid {DesignTokens.COLOR_YELLOW}; font-size: 11px;")
        self.btn_no_engine_help.hide()
        config_layout.addWidget(self.btn_no_engine_help)

        # 4. Pipeline Agentique + Bouton d'aide si vide
        self.pipeline_combo = StyledComboBox()
        add_form_group(config_layout, "PIPELINE AGENTIQUE :", self.pipeline_combo)

        self.btn_no_pipeline_help = SecondaryButton("🔀 Créer un Pipeline d'Agents")
        self.btn_no_pipeline_help.setStyleSheet(f"color: {DesignTokens.ACCENT_PRIMARY}; border: 1px solid {DesignTokens.ACCENT_PRIMARY}; font-size: 11px;")
        self.btn_no_pipeline_help.hide()
        config_layout.addWidget(self.btn_no_pipeline_help)

        # 5. Carte Visuelle Interactive : Activation de la Vision
        self.vision_card = VisionCard()
        self.vision_card.setObjectName("visionCard")
        self.vision_card.setStyleSheet(f"""
            QFrame#visionCard {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
            }}
            QFrame#visionCard:hover {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        self.vision_card.setCursor(Qt.CursorShape.PointingHandCursor)
        vision_layout = QVBoxLayout(self.vision_card)
        vision_layout.setContentsMargins(12, 12, 12, 12)
        vision_layout.setSpacing(6)

        vision_top = QHBoxLayout()
        self.lbl_vision_icon = QLabel()
        self.lbl_vision_icon.setPixmap(load_phosphor_icon("ph.eye-closed", color=DesignTokens.TEXT_MUTED).pixmap(16, 16))
        self.lbl_vision_title = QLabel("Vision (PDF)")
        self.lbl_vision_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: 600; font-size: 12px;")

        self.vision_badge = Badge("OFF", variant="neutral")

        vision_top.addWidget(self.lbl_vision_icon)
        vision_top.addWidget(self.lbl_vision_title)
        vision_top.addStretch()
        vision_top.addWidget(self.vision_badge)
        vision_layout.addLayout(vision_top)

        self.lbl_vision_desc = QLabel("Extraction multimodale des schémas & figures.")
        self.lbl_vision_desc.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        self.lbl_vision_desc.setWordWrap(True)
        vision_layout.addWidget(self.lbl_vision_desc)

        self.vision_cb = QCheckBox()
        self.vision_cb.hide()  # Géré via l'interaction de la carte
        vision_layout.addWidget(self.vision_cb)

        config_layout.addWidget(self.vision_card)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setStyleSheet(f"border: 1px dashed {DesignTokens.BORDER_COLOR}; margin: 8px 0;")
        config_layout.addWidget(separator)

        # Scope Selector (Portée de Génération)
        scope_lbl = QLabel("PORTÉE DE GÉNÉRATION")
        scope_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-weight: 600; font-size: 11px;")
        config_layout.addWidget(scope_lbl)

        self.scope_stack = QStackedWidget()

        # Page 1: Sliders for pages
        self.scope_pages_widget = QWidget()
        scope_pages_layout = QVBoxLayout(self.scope_pages_widget)
        scope_pages_layout.setContentsMargins(0, 0, 0, 0)

        pages_header = QHBoxLayout()
        pages_lbl = QLabel("Plage de pages:")
        pages_header.addWidget(pages_lbl)
        pages_header.addStretch()
        scope_pages_layout.addLayout(pages_header)

        self.pages_input_frame = QFrame()
        self.pages_input_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 2px 6px;
            }}
            QSpinBox {{
                background: transparent;
                border: none;
                color: {DesignTokens.TEXT_PRIMARY};
                font-weight: bold;
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                width: 0px;
            }}
        """)
        pages_input_layout = QHBoxLayout(self.pages_input_frame)
        pages_input_layout.setContentsMargins(4, 2, 4, 2)
        pages_input_layout.setSpacing(4)

        self.spin_page_start = QSpinBox()
        self.spin_page_start.setMinimum(1)
        self.spin_page_start.setMaximum(9999)
        self.spin_page_start.setValue(1)

        lbl_to = QLabel("à")
        lbl_to.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; background: transparent; border: none;")
        lbl_to.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.spin_page_end = QSpinBox()
        self.spin_page_end.setMinimum(1)
        self.spin_page_end.setMaximum(9999)
        self.spin_page_end.setValue(10)

        pages_input_layout.addWidget(self.spin_page_start)
        pages_input_layout.addWidget(lbl_to)
        pages_input_layout.addWidget(self.spin_page_end)

        scope_pages_layout.addWidget(self.pages_input_frame)
        self.scope_stack.addWidget(self.scope_pages_widget)

        self.spin_page_start.valueChanged.connect(self._on_page_scope_changed)
        self.spin_page_end.valueChanged.connect(self._on_page_scope_changed)

        # Page 2: QTreeView for headings
        self.scope_headings_tree = QTreeWidget()
        self.scope_headings_tree.setHeaderHidden(True)
        self.scope_headings_tree.setStyleSheet(f"background-color: transparent; border: 1px solid {DesignTokens.BORDER_COLOR}; color: {DesignTokens.TEXT_PRIMARY};")
        self.scope_stack.addWidget(self.scope_headings_tree)

        config_layout.addWidget(self.scope_stack)

        # The Generate button has been moved to the bottom of the config panel
        # Separator 2
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.Shape.HLine)
        separator2.setFrameShadow(QFrame.Shadow.Sunken)
        separator2.setStyleSheet(f"border: 1px dashed {DesignTokens.BORDER_COLOR}; margin: 8px 0;")
        config_layout.addWidget(separator2)

        # Paramètres Avancés
        self.btn_toggle_advanced = QPushButton()
        self.btn_toggle_advanced.setStyleSheet("background: transparent; border: none; text-align: left; padding: 0;")
        self.btn_toggle_advanced.setCursor(Qt.CursorShape.PointingHandCursor)

        advanced_header = QHBoxLayout(self.btn_toggle_advanced)
        advanced_header.setContentsMargins(0, 0, 0, 0)
        advanced_lbl = QLabel("Paramètres Avancés")
        advanced_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; background: transparent;")

        self.advanced_icon = QLabel()
        self.advanced_icon.setPixmap(load_phosphor_icon("ph.caret-right", color=DesignTokens.TEXT_MUTED).pixmap(14, 14))
        self.advanced_icon.setStyleSheet("background: transparent;")

        advanced_header.addWidget(advanced_lbl)
        advanced_header.addStretch()
        advanced_header.addWidget(self.advanced_icon)

        config_layout.addWidget(self.btn_toggle_advanced)

        self.advanced_container = QFrame()
        self.advanced_container.setObjectName("advancedContainer")
        self.advanced_container.setVisible(False)
        self.advanced_container.setStyleSheet(f"""
            QFrame#advancedContainer {{
                background: rgba(0,0,0,0.1);
                padding: 12px;
                border-radius: 4px;
                border: 1px solid {DesignTokens.BORDER_COLOR};
            }}
        """)
        advanced_layout = QVBoxLayout(self.advanced_container)
        advanced_layout.setContentsMargins(0, 0, 0, 0)
        advanced_layout.setSpacing(12)

        # Style partagé des sliders
        slider_style = f"""
            QSlider::groove:horizontal {{
                border-radius: 2px;
                height: 4px;
                margin: 0px;
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
            }}
            QSlider::sub-page:horizontal {{
                background-color: {DesignTokens.ACCENT_PRIMARY};
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background-color: #ffffff;
                border: 2px solid {DesignTokens.ACCENT_PRIMARY};
                height: 14px;
                width: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }}
            QSlider::handle:horizontal:hover {{
                background-color: {DesignTokens.ACCENT_HOVER};
            }}
        """

        # Température
        temp_layout = QVBoxLayout()
        temp_header = QHBoxLayout()
        temp_lbl = QLabel("Température")
        temp_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px;")
        self.val_temp_lbl = QLabel("0.7")
        self.val_temp_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-family: {DesignTokens.FONT_CODE}; font-size: 11px;")
        temp_header.addWidget(temp_lbl)
        temp_header.addStretch()
        temp_header.addWidget(self.val_temp_lbl)

        self.slider_temp = QSlider(Qt.Orientation.Horizontal)
        self.slider_temp.setMinimum(0)
        self.slider_temp.setMaximum(10)
        self.slider_temp.setValue(7)
        self.slider_temp.setStyleSheet(slider_style)
        self.slider_temp.valueChanged.connect(lambda v: self.val_temp_lbl.setText(f"{v / 10:.1f}"))

        temp_layout.addLayout(temp_header)
        temp_layout.addWidget(self.slider_temp)
        advanced_layout.addLayout(temp_layout)

        # Max Tokens
        tokens_layout = QVBoxLayout()
        tokens_header = QHBoxLayout()
        tokens_lbl = QLabel("Max Tokens")
        tokens_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px;")
        self.val_tokens_lbl = QLabel("4096")
        self.val_tokens_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-family: {DesignTokens.FONT_CODE}; font-size: 11px;")
        tokens_header.addWidget(tokens_lbl)
        tokens_header.addStretch()
        tokens_header.addWidget(self.val_tokens_lbl)

        self.slider_tokens = QSlider(Qt.Orientation.Horizontal)
        self.slider_tokens.setMinimum(1)
        self.slider_tokens.setMaximum(32)
        self.slider_tokens.setValue(16)
        self.slider_tokens.setStyleSheet(slider_style)
        self.slider_tokens.valueChanged.connect(lambda v: self.val_tokens_lbl.setText(f"{v * 256}"))

        tokens_layout.addLayout(tokens_header)
        tokens_layout.addWidget(self.slider_tokens)
        advanced_layout.addLayout(tokens_layout)

        config_layout.addWidget(self.advanced_container)

        # Separator for the bottom
        separator3 = QFrame()
        separator3.setFrameShape(QFrame.Shape.HLine)
        separator3.setFrameShadow(QFrame.Shadow.Sunken)
        separator3.setStyleSheet(f"border: 1px dashed {DesignTokens.BORDER_COLOR}; margin: 8px 0;")
        config_layout.addWidget(separator3)

        # Generate Button (moved from above)
        self.btn_generate_cards = PrimaryButton("Générer les Cartes")
        self.btn_generate_cards.setIcon(load_phosphor_icon("ph.magic-wand", color="white"))
        config_layout.addWidget(self.btn_generate_cards)

        config_layout.addStretch()

        self.config_panel.add_tab("Explorateur", explorer_content, "ph.files", closable=False)
        self.config_panel.add_tab("Config IA", config_content, "ph.cpu", closable=False)

        self.main_splitter.addWidget(self.config_panel)

        # --- COL 2: Source + Results ---
        self.center_splitter = QSplitter(Qt.Orientation.Vertical)
        self.main_splitter.addWidget(self.center_splitter)

        # Panel Document Source
        source_container = QWidget()
        source_layout = QVBoxLayout(source_container)
        source_layout.setContentsMargins(0, 0, 0, 0)

        self.source_panel = IdePanel(detachable=True, tab_variant="document")
        source_layout.addWidget(self.source_panel)

        self.center_splitter.addWidget(source_container)

        # Panel Cartes Générées
        self.results_panel = IdePanel(detachable=True)

        cartes_content = QWidget()
        cartes_layout = QVBoxLayout(cartes_content)
        cartes_layout.setContentsMargins(0, 0, 0, 0)

        self.results_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Gauche : Table des résultats
        table_container = QWidget()
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(12, 12, 12, 12)
        table_layout.setSpacing(8)
        table_container.setStyleSheet(f"border-right: 1px solid {DesignTokens.BORDER_COLOR};")

        self.results_table = StyledTableWidget(["Recto", "Verso", "Statut"])
        self.results_table.setSelectionBehavior(StyledTableWidget.SelectionBehavior.SelectRows)
        # Redimensionnement responsive des colonnes et garantie anti-écrasement
        self.results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.results_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.horizontalHeader().setMinimumSectionSize(125)
        self.results_table.itemSelectionChanged.connect(self._on_table_selection_changed)
        self.results_table.itemChanged.connect(self._on_cell_edited)
        self.results_table.installEventFilter(self)
        table_layout.addWidget(self.results_table, 1)

        self.results_splitter.addWidget(table_container)

        # Droite : Aperçu interactif WebEngine
        self.preview_widget = FlashcardPreview()
        self.results_splitter.addWidget(self.preview_widget)

        cartes_layout.addWidget(self.results_splitter, 1)

        # Barre d'actions globale (Footer du panneau Cartes Générées)
        main_bot_toolbar = QHBoxLayout()
        main_bot_toolbar.setContentsMargins(12, 0, 12, 12)

        self.btn_save_anki = PrimaryButton("Enregistrer dans la Forge (0)")
        self.btn_save_anki.setIcon(load_phosphor_icon("ph.floppy-disk", color="white"))
        self.btn_save_anki.setEnabled(False)
        self.btn_save_anki.setToolTip("Enregistrer les cartes validées dans votre collection AnkiForge (Ctrl+S)")
        main_bot_toolbar.addWidget(self.btn_save_anki)

        main_bot_toolbar.addStretch()

        self.btn_rejeter = DangerButton("Rejeter", ghost=True)
        self.btn_rejeter.setIcon(load_phosphor_icon("ph.trash", color=DesignTokens.COLOR_RED))
        self.btn_rejeter.setToolTip("Rejeter la carte active et passer à la suivante (Raccourci: Suppr ou R)")

        self.btn_editer = SecondaryButton("Éditer")
        self.btn_editer.setIcon(load_phosphor_icon("ph.pencil-simple", color=DesignTokens.TEXT_PRIMARY))
        self.btn_editer.setToolTip("Modifier le texte de la carte (Raccourci: E)")

        self.btn_valider = PrimaryButton("Garder")
        self.btn_valider.setIcon(load_phosphor_icon("ph.check", color="white"))
        self.btn_valider.setToolTip("Garder la carte active et passer à la suivante (Raccourci: Espace ou V)")

        main_bot_toolbar.addWidget(self.btn_rejeter)
        main_bot_toolbar.addWidget(self.btn_editer)
        main_bot_toolbar.addWidget(self.btn_valider)

        cartes_layout.addLayout(main_bot_toolbar)

        erreurs_content = QWidget()
        erreurs_layout = QVBoxLayout(erreurs_content)
        erreurs_layout.setContentsMargins(12, 12, 12, 12)
        self.err_lbl = QLabel("Aucune erreur lors du processus de génération.")
        self.err_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 12px;")
        erreurs_layout.addWidget(self.err_lbl)
        erreurs_layout.addStretch()

        self.results_panel.add_tab("Cartes Générées (0)", cartes_content, "ph.list-numbers", closable=False)
        self.results_panel.add_tab("Journal des Erreurs", erreurs_content, "ph.warning-circle", closable=False)

        self.center_splitter.addWidget(self.results_panel)
        self.center_splitter.setSizes([320, 480])
        self.main_splitter.setSizes([260, 800])

        # Creation du tab initial
        self._open_document_tab("Saisie Libre")
        self._update_vision_ui(False)

    def _connect_signals(self) -> None:
        self.btn_new_free_input.clicked.connect(lambda: self._open_document_tab("Nouvelle Saisie"))
        self.file_tree.itemDoubleClicked.connect(self._on_explorer_item_double_clicked)
        self.btn_generate_cards.clicked.connect(self._on_generate_from_tree)

        self.btn_select_deck.clicked.connect(self._on_click_select_deck)
        self.btn_select_model.clicked.connect(self._on_click_select_model)

        self.vision_card.clicked.connect(self._toggle_vision_card)
        self.vision_cb.toggled.connect(self._update_vision_ui)
        self.btn_toggle_advanced.clicked.connect(self._toggle_advanced_settings)

        self.btn_no_engine_help.clicked.connect(self._open_settings_modal)
        self.btn_no_pipeline_help.clicked.connect(lambda: self._navigate("pipelines"))
        self.btn_save_anki.clicked.connect(self._on_save_anki)
        self.preview_widget.btn_prev.clicked.connect(self._on_prev_card)
        self.preview_widget.btn_next.clicked.connect(self._on_next_card)

        self.btn_valider.clicked.connect(self._on_validate_card)
        self.btn_editer.clicked.connect(self._on_edit_card)
        self.btn_rejeter.clicked.connect(self._on_reject_card)

    def _toggle_vision_card(self) -> None:
        self.vision_cb.setChecked(not self.vision_cb.isChecked())

    def _toggle_advanced_settings(self) -> None:
        is_visible = not self.advanced_container.isVisible()
        self.advanced_container.setVisible(is_visible)
        icon_name = "ph.caret-down" if is_visible else "ph.caret-right"
        self.advanced_icon.setPixmap(load_phosphor_icon(icon_name, color=DesignTokens.TEXT_MUTED).pixmap(14, 14))

    @Slot(bool)
    def _update_vision_ui(self, checked: bool) -> None:
        if checked:
            self.lbl_vision_icon.setPixmap(load_phosphor_icon("ph.eye", color=DesignTokens.COLOR_YELLOW).pixmap(16, 16))
            self.vision_badge.setText("ON")
            self.vision_badge.set_variant("warning")
            self.vision_card.setStyleSheet(f"""
                QFrame#visionCard {{
                    background-color: {DesignTokens.BG_ACTIVE};
                    border: 1px solid {DesignTokens.COLOR_YELLOW};
                    border-radius: {DesignTokens.RADIUS_SM}px;
                }}
            """)
        else:
            self.lbl_vision_icon.setPixmap(load_phosphor_icon("ph.eye-closed", color=DesignTokens.TEXT_MUTED).pixmap(16, 16))
            self.vision_badge.setText("OFF")
            self.vision_badge.set_variant("neutral")
            self.vision_card.setStyleSheet(f"""
                QFrame#visionCard {{
                    background-color: {DesignTokens.BG_INPUT};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: {DesignTokens.RADIUS_SM}px;
                }}
                QFrame#visionCard:hover {{
                    border-color: {DesignTokens.ACCENT_PRIMARY};
                }}
            """)

    def refresh_data(self) -> None:
        """Recharge les données dynamiques depuis Peewee DB (Decks, NoteTypes, Engines, Pipelines, Docs)."""
        try:
            # 1. Decks (Paquets existants + sélecteur)
            decks = list(DeckModel.select())
            if not decks:
                DeckModel.get_or_create(name="Général")
                decks = list(DeckModel.select())
            self.decks_cache = decks
            if self.current_deck is None and self.decks_cache:
                self._set_current_deck(self.decks_cache[0])

            # 2. Note Types
            note_types = list(NoteTypeModel.select())
            if not note_types:
                # Add default models if empty in cache for selection dialog
                class DummyModel:
                    def __init__(self, name: str):
                        self.name = name
                        self.fields_schema = ""

                note_types = [DummyModel("Basique (Recto/Verso)"), DummyModel("Texte à trous (Cloze)")]
            self.models_cache = note_types
            if not self.selected_models and self.models_cache:
                self.selected_models = list(self.models_cache)
            if self.current_model is None and self.models_cache:
                self._set_current_model(self.models_cache[0])
            else:
                self._update_selected_models_display()

            # 3. Engines LLM
            self.engine_combo.blockSignals(True)
            self.engine_combo.clear()
            engines = list(LLMConfigModel.select())
            if not engines:
                LLMConfigModel.create(
                    display_name="GPT-4o (OpenAI)",
                    provider="openai",
                    model_id="gpt-4o",
                    context_limit=128000,
                )
                LLMConfigModel.create(
                    display_name="Claude 3.5 Sonnet (Anthropic)",
                    provider="anthropic",
                    model_id="claude-3-5-sonnet-20240620",
                    context_limit=200000,
                )
                engines = list(LLMConfigModel.select())

            for eg in engines:
                display_name = getattr(eg, "display_name", getattr(eg, "name", str(eg)))
                self.engine_combo.addItem(f"⚡ {display_name}", userData=eg)
            self.btn_no_engine_help.hide()
            self.engine_combo.blockSignals(False)

            # 4. Pipelines
            self.pipeline_combo.blockSignals(True)
            self.pipeline_combo.clear()
            pipelines = list(PipelineModel.select())
            if not pipelines:
                p1 = PipelineModel.create(
                    name="Excellence Math/Info (Archiviste + Linter)",
                    description="Pipeline haute-fidélité pour les cours scientifiques.",
                )
                pipelines = [p1]

            for pipe in pipelines:
                self.pipeline_combo.addItem(f"🔀 {pipe.name}", userData=pipe)
            self.btn_no_pipeline_help.hide()
            self.pipeline_combo.blockSignals(False)

            # 5. Documents in Explorer Tree
            self.file_tree.clear()

            folders = list(FolderModel.select())
            docs = list(DocumentModel.select())

            folder_items: dict[int, QTreeWidgetItem] = {}
            for folder in folders:
                f_item = QTreeWidgetItem(self.file_tree)
                f_item.setText(0, folder.name)
                f_item.setIcon(0, load_phosphor_icon("ph.folder", color=DesignTokens.ACCENT_PRIMARY, weight="fill"))
                f_item.setData(0, Qt.ItemDataRole.UserRole, folder)
                folder_items[folder.id] = f_item
                f_item.setExpanded(True)

            if not docs and not folders:
                item = QTreeWidgetItem(self.file_tree)
                item.setText(0, "Aucun document")
                item.setIcon(0, load_phosphor_icon("ph.warning-circle", color=DesignTokens.TEXT_MUTED))
            else:
                for doc in docs:
                    parent_item: Any = self.file_tree
                    if doc.folder_id and doc.folder_id in folder_items:
                        parent_item = folder_items[doc.folder_id]

                    item = QTreeWidgetItem(parent_item)
                    item.setText(0, doc.title)

                    title_lower = doc.title.lower()
                    is_pdf = getattr(doc, "file_type", "") == "pdf"
                    has_content = bool(doc.content and doc.content.strip())

                    if is_pdf:
                        if has_content:
                            item.setIcon(0, load_phosphor_icon("ph.file-pdf", color=DesignTokens.COLOR_RED, weight="fill"))
                        else:
                            item.setIcon(0, load_phosphor_icon("ph.file-pdf", color=DesignTokens.TEXT_MUTED))
                            item.setText(0, f"{doc.title} (Non extrait)")
                            item.setForeground(0, QColor(DesignTokens.TEXT_MUTED))
                            item.setToolTip(0, "Ce PDF n'a pas encore été analysé par Marker. Allez dans 'Mes Documents' pour l'extraire.")
                    elif getattr(doc, "file_type", "") in ("md", "txt", "json", "csv") or title_lower.endswith((".md", ".txt", ".json", ".csv")):
                        item.setIcon(0, load_phosphor_icon("ph.file-code", color=DesignTokens.COLOR_YELLOW, weight="fill"))
                    else:
                        item.setIcon(0, load_phosphor_icon("ph.file-text", color=DesignTokens.COLOR_GREEN, weight="fill"))

                    item.setData(0, Qt.ItemDataRole.UserRole, doc)

            self._on_model_changed()

        except Exception as e:
            logger.warning("Erreur lors de la mise à jour des combos creation_view: %s", e, exc_info=True)

    # Statuts considérés comme "décision prise" (aucune action utilisateur requise)
    _FINAL_STATUSES = frozenset({"Enregistrée", "Refusée"})

    @Slot()
    def _on_create_new_deck(self) -> None:
        name, ok = QInputDialog.getText(self, "Nouveau Paquet", "Nom du paquet Anki (ex: Science::Physique) :")
        if ok and name.strip():
            try:
                dk_name = name.strip()
                new_deck, _ = DeckModel.get_or_create(name=dk_name, description="Nouveau paquet créé depuis le Studio.")
                self.refresh_data()
                self._set_current_deck(new_deck)
                show_toast(self, f"Paquet '{dk_name}' créé avec succès !")
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Impossible de créer le paquet : {str(e)}")

    @Slot()
    def _open_settings_modal(self) -> None:
        from ankiforge.ui.widgets.settings_modal import SettingsModal

        modal = SettingsModal(ai_manager=self.ai_manager, parent=self)
        modal.exec()

    def _open_document_tab(self, title: str, content: str = "", doc_model: Optional[Any] = None) -> None:
        # Create a unique title if multiple Saisie Libres are opened
        base_title = title
        counter = 1
        while title in self.open_editors:
            title = f"{base_title} {counter}"
            counter += 1

        editor_widget = DocumentEditorWidget(content, source_title=title, doc_model=doc_model, parent=self)
        editor_widget.generate_requested.connect(self._on_generate)
        editor_widget.cancel_requested.connect(self._on_cancel_generation)

        self.open_editors[title] = editor_widget
        icon = "ph.text-t"
        icon_color = DesignTokens.TEXT_SECONDARY

        if doc_model:
            title_lower = title.lower()
            if title_lower.endswith(".pdf"):
                icon = "ph.file-pdf"
                icon_color = DesignTokens.COLOR_RED
            elif title_lower.endswith((".md", ".txt", ".json", ".csv")):
                icon = "ph.file-code"
                icon_color = DesignTokens.COLOR_BLUE
            else:
                icon = "ph.file-text"
                icon_color = DesignTokens.COLOR_BLUE

        self.source_panel.register_tab(title, editor_widget, icon, closable=True, icon_color=icon_color)

    @Slot(QTreeWidgetItem, int)
    def _on_explorer_item_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        doc = item.data(0, Qt.ItemDataRole.UserRole)
        if doc and hasattr(doc, "content"):
            title = doc.title if hasattr(doc, "title") else "Document"
            is_pdf = getattr(doc, "file_type", "") == "pdf"
            has_content = bool(doc.content and doc.content.strip())

            if is_pdf and not has_content:
                show_toast(self, "Ce PDF n'a pas encore été extrait. Vous ne pouvez pas l'ouvrir en texte.", is_error=True)
                return

            # Prevent opening the same document twice, but recreate if the tab was closed
            if title in self.open_editors:
                try:
                    _ = self.open_editors[title].parent()
                    self.source_panel.open_tab(title)
                except RuntimeError:
                    # Widget was deleted (tab closed). Remove it and recreate.
                    self.open_editors.pop(title, None)
                    self._open_document_tab(title, doc.content, doc)
            else:
                self._open_document_tab(title, doc.content, doc)

    def _set_all_generation_states(self, is_generating: bool) -> None:
        for editor in self.open_editors.values():
            editor.set_generation_state(is_generating)

    @Slot()
    def _on_page_scope_changed(self) -> None:
        start = self.spin_page_start.value()
        end = self.spin_page_end.value()

        if start > end:
            self.spin_page_end.blockSignals(True)
            self.spin_page_end.setValue(start)
            self.spin_page_end.blockSignals(False)
            end = start

        selected_items = self.file_tree.selectedItems()
        if not selected_items:
            return

        doc = selected_items[0].data(0, Qt.ItemDataRole.UserRole)
        if not doc or not hasattr(doc, "title"):
            return

        editor = self.open_editors.get(doc.title)
        if not editor:
            return

        has_pages = DocumentChunkModel.select().where((DocumentChunkModel.document == doc) & DocumentChunkModel.page_number.is_null(False)).exists()

        if has_pages:
            chunks = list(
                DocumentChunkModel.select()
                .where((DocumentChunkModel.document == doc) & (DocumentChunkModel.page_number >= start) & (DocumentChunkModel.page_number <= end))
                .order_by(DocumentChunkModel.page_number, DocumentChunkModel.chunk_index)
            )
        else:
            chunks = list(
                DocumentChunkModel.select()
                .where((DocumentChunkModel.document == doc) & (DocumentChunkModel.chunk_index >= start - 1) & (DocumentChunkModel.chunk_index <= end - 1))
                .order_by(DocumentChunkModel.chunk_index)
            )

        if not chunks:
            msg = f"_Aucun contenu trouvé pour les pages {start} à {end}_" if has_pages else f"_Aucun contenu trouvé pour les sections {start} à {end}_"
            editor.set_content(msg)
            return

        content = "\n\n".join([c.content for c in chunks])
        editor.set_content(content)
        editor.jump_pdf_to_page(start - 1)

    @Slot()
    def _on_generate_from_tree(self) -> None:
        selected_items = self.file_tree.selectedItems()
        if not selected_items:
            show_toast(self, "Veuillez sélectionner un document dans l'arborescence.", is_error=True)
            return

        doc = selected_items[0].data(0, Qt.ItemDataRole.UserRole)
        if not doc or not hasattr(doc, "content"):
            show_toast(self, "Veuillez sélectionner un document valide.", is_error=True)
            return

        if not doc.content or not doc.content.strip():
            show_toast(self, "Ce document est vide ou n'a pas encore été extrait.", is_error=True)
            return

        editor = self.open_editors.get(doc.title)
        content_to_use = editor.get_text() if editor else doc.content

        self._on_generate(content_to_use, doc.title)

    @Slot()
    def _on_click_select_deck(self) -> None:
        try:
            if self._deck_modal and self._deck_modal.isVisible():
                self._deck_modal.raise_()
                self._deck_modal.activateWindow()
                return
        except RuntimeError:
            self._deck_modal = None

        self._deck_modal = DeckSelectWindow(title="Sélectionner un paquet cible", parent=self)
        self._deck_modal.deck_selected.connect(self._on_deck_selected_from_modal)
        self._deck_modal.show()

    @Slot(int, str)
    def _on_deck_selected_from_modal(self, deck_id: int, deck_name: str) -> None:
        try:
            deck = DeckModel.get_by_id(deck_id)
            self._set_current_deck(deck)
        except Exception as e:
            logger.error(f"Impossible de trouver le paquet {deck_name}: {e}")

    def _set_current_deck(self, deck: Any) -> None:
        self.current_deck = deck
        name = getattr(deck, "name", str(deck))
        self.btn_select_deck.setText(name)

    @Slot()
    def _on_click_select_model(self) -> None:
        initial = self.selected_models or ([self.current_model] if self.current_model else [])
        dialog = MultiSelectionDialog(
            title="Sélectionner les modèles de cartes autorisés pour l'IA",
            items=self.models_cache,
            display_func=lambda m: m.name,
            initial_selected=initial,
            parent=self,
        )
        if dialog.exec():
            selected = dialog.get_selected_items()
            if selected:
                self.selected_models = selected
                self.current_model = selected[0]
                self._update_selected_models_display()
                self._on_model_changed()

    def _update_selected_models_display(self) -> None:
        if not self.selected_models:
            if self.current_model:
                self.selected_models = [self.current_model]
            elif self.models_cache:
                self.selected_models = [self.models_cache[0]]
                self.current_model = self.models_cache[0]

        if len(self.selected_models) == 1:
            name = getattr(self.selected_models[0], "name", str(self.selected_models[0]))
            self.btn_select_model.setText(name)
        elif len(self.selected_models) > 1:
            first_name = getattr(self.selected_models[0], "name", str(self.selected_models[0]))
            self.btn_select_model.setText(f"{first_name} (+{len(self.selected_models) - 1})")
        else:
            self.btn_select_model.setText("Sélectionner un modèle...")

    def _set_current_model(self, model: Any) -> None:
        self.current_model = model
        if model and model not in self.selected_models:
            self.selected_models = [model]
        self._update_selected_models_display()
        self._on_model_changed()

    @Slot()
    def _on_model_changed(self) -> None:
        headers = ["Modèle", "Recto / Texte", "Verso / Détails", "Statut"]
        self.results_table.blockSignals(True)
        self.results_table.clear()
        self.results_table.setColumnCount(len(headers))
        self.results_table.setHorizontalHeaderLabels(headers)
        self.results_table.setRowCount(0)
        self.results_table.blockSignals(False)

    @Slot(str, str)
    def _on_generate(self, text_source: str = "", source_title: str = "Saisie Libre") -> None:
        self.current_source_title = source_title

        if not text_source:
            show_toast(self, "Veuillez saisir un texte source ou sélectionner un document.", is_error=True)
            return

        selected_nt = self.current_model
        selected_pipeline = self.pipeline_combo.currentData()
        selected_engine = self.engine_combo.currentData()

        if not selected_engine:
            show_toast(self, "Aucun moteur IA configuré. Veuillez configurer les clés API dans les paramètres.", is_error=True)
            return

        nt_id = selected_nt.id if selected_nt and hasattr(selected_nt, "id") else 1
        nt_schema = str(selected_nt.fields_schema) if selected_nt and hasattr(selected_nt, "fields_schema") and selected_nt.fields_schema else '["Front", "Back"]'
        fields = json.loads(nt_schema) if nt_schema else ["Front", "Back"]

        pipe_id = selected_pipeline.id if selected_pipeline and hasattr(selected_pipeline, "id") else None

        provider = None
        if self.ai_manager and hasattr(self.ai_manager, "create_provider_from_config"):
            try:
                provider = self.ai_manager.create_provider_from_config(selected_engine)
            except Exception as e:
                logger.warning("Impossible de créer le provider depuis la config: %s", e)

        # 1. Initialiser le Contexte d'Exécution DAG (PipelineRunState)
        initial_state = PipelineRunState(initial_prompt=text_source[:120])
        initial_state.set_variable("text_source", text_source)
        initial_state.set_variable("fields", fields)
        first_field = fields[0] if len(fields) > 0 else "Front"
        second_field = fields[1] if len(fields) > 1 else "Back"
        fields_str = ", ".join([f'"{f}"' for f in fields])
        initial_state.set_variable("first_field", first_field)
        initial_state.set_variable("second_field", second_field)
        initial_state.set_variable("fields_str", fields_str)
        initial_state.set_variable("note_type_id", nt_id)
        initial_state.set_variable("note_type_fields_schema", nt_schema)
        initial_state.set_variable("selected_models", self.selected_models or ([selected_nt] if selected_nt else []))

        # 2. Configurer et démarrer le PipelineOrchestrator dans QThreadPool
        self._set_all_generation_states(True)

        self.orchestrator = PipelineOrchestrator(
            pipeline_id=pipe_id,
            initial_state=initial_state,
            ai_provider=provider,
        )
        self.orchestrator.setAutoDelete(False)
        self.orchestrator.signals.step_started.connect(self._on_orchestrator_step_started)
        self.orchestrator.signals.step_progress.connect(self._on_orchestrator_step_progress)
        self.orchestrator.signals.step_completed.connect(self._on_orchestrator_step_completed)
        self.orchestrator.signals.human_validation_required.connect(self._on_human_validation)
        self.orchestrator.signals.pipeline_finished.connect(self._on_orchestrator_finished)
        self.orchestrator.signals.error_occurred.connect(self._on_generation_error)
        self.orchestrator.signals.cancelled.connect(self._on_generation_cancelled)

        self.thread_pool.start(self.orchestrator)

    @Slot(int, str)
    def _on_orchestrator_step_started(self, step_order: int, desc: str) -> None:
        logger.info("[Orchestrateur] Démarrage étape %d : %s", step_order, desc)
        active_editor = self.open_editors.get(getattr(self, "current_source_title", ""))
        if active_editor:
            active_editor.raw_editor.setPlaceholderText(f"⏳ Étape {step_order}: {desc}...")

    @Slot(int, int, str)
    def _on_orchestrator_step_progress(self, current: int, total: int, detail: str) -> None:
        logger.info("[Orchestrateur] Progression (%d/%d) : %s", current, total, detail)
        active_editor = self.open_editors.get(getattr(self, "current_source_title", ""))
        if active_editor:
            active_editor.raw_editor.setPlaceholderText(f"⏳ {detail} ({current}/{total})...")

    @Slot(int, object)
    def _on_orchestrator_step_completed(self, step_order: int, state: PipelineRunState) -> None:
        logger.info("[Orchestrateur] Étape %d terminée avec succès.", step_order)

    @Slot(object)
    def _on_human_validation(self, state: PipelineRunState) -> None:
        logger.info("[Orchestrateur] PAUSE INTERACTIVE : Validation Humaine Requise.")
        dialog = HumanValidationDialog(state, self)
        res = dialog.exec()
        if res == QDialog.DialogCode.Accepted:
            show_toast(self, "Plan validé ! Poursuite du pipeline...", is_error=False)
            if self.orchestrator:
                self.orchestrator.resume(state)
        else:
            show_toast(self, "Génération interrompue par l'utilisateur.", is_error=False)
            if self.orchestrator:
                self.orchestrator.cancel()

    @Slot(object)
    def _on_orchestrator_finished(self, state: PipelineRunState) -> None:
        self._set_all_generation_states(False)

        # Récupération des cartes produites par les étapes DAG
        cards_raw = state.get_variable("generated_cards") or state.get_variable("map_reduce_results") or state.get_variable("last_output") or []
        cards = extract_cards_from_data(cards_raw)

        selected_nt = self.current_model
        default_model_name = selected_nt.name if selected_nt else "Basique"

        cleaned_notes: list[dict[str, Any]] = []
        if isinstance(cards, list):
            for item in cards:
                if isinstance(item, dict):
                    card_model_name = item.get("model") or item.get("note_type") or default_model_name
                    target_nt = None
                    if self.models_cache:
                        for m in self.models_cache:
                            if m.name.lower().strip() == str(card_model_name).lower().strip():
                                target_nt = m
                                break
                    if not target_nt:
                        target_nt = selected_nt

                    m_schema = str(target_nt.fields_schema) if target_nt and hasattr(target_nt, "fields_schema") and target_nt.fields_schema else '["Front", "Back"]'
                    try:
                        m_fields = json.loads(m_schema) if m_schema else ["Front", "Back"]
                    except Exception:
                        m_fields = ["Front", "Back"]

                    lower_item = {str(k).lower().strip(): v for k, v in item.items()}
                    raw_values = [v for k, v in item.items() if str(k).lower() not in ("model", "note_type", "status", "chunk_id")]

                    note_dict: dict[str, Any] = {
                        "model": target_nt.name if target_nt else default_model_name,
                        "status": item.get("status", "À valider"),
                    }
                    if "chunk_id" in item:
                        note_dict["chunk_id"] = item["chunk_id"]

                    for i, field_name in enumerate(m_fields):
                        f_lower = field_name.lower().strip()
                        if f_lower in lower_item:
                            val = lower_item[f_lower]
                        elif i < len(raw_values):
                            val = raw_values[i]
                        else:
                            val = ""

                        if isinstance(val, list):
                            val = "<br>".join([str(v) for v in val])
                        else:
                            val = str(val) if val is not None else ""
                        note_dict[field_name] = val

                    # Conserver aussi les clés génériques utiles
                    for k, v in item.items():
                        if k not in note_dict and str(k).lower() not in ("status",):
                            note_dict[k] = v

                    cleaned_notes.append(note_dict)

        if cleaned_notes:
            self._on_generation_finished(cleaned_notes)
        else:
            show_toast(self, "Pipeline terminé (aucune carte générée).", is_error=False)
        logger.info("[Orchestrateur] Fin du Pipeline. %d cartes obtenues.", len(cleaned_notes))

    @Slot(list)
    def _on_generation_finished(self, cards: list[dict[str, Any]]) -> None:
        self._set_all_generation_states(False)
        self.generated_cards = cards
        self.current_preview_index = 0

        self._populate_results_table()
        self._update_card_preview()
        self._refresh_save_button()
        show_toast(self, f"{len(cards)} cartes générées avec succès !")

    @Slot(str)
    def _on_generation_error(self, err_msg: str) -> None:
        self._set_all_generation_states(False)
        self.err_lbl.setText(f"⚠️ Erreur de génération : {err_msg}")
        self.results_panel.set_tab_title(1, "Journal des Erreurs (1)")
        show_toast(self, f"Erreur : {err_msg}", is_error=True)

    @Slot()
    def _on_generation_cancelled(self) -> None:
        self._set_all_generation_states(False)
        show_toast(self, "Génération annulée.", is_error=False)

    def eventFilter(self, obj: Any, event: Any) -> bool:
        if obj == self.results_table and event.type() == QEvent.Type.KeyPress:
            key_event = cast(QKeyEvent, event)
            key = key_event.key()
            if key in (Qt.Key.Key_Space, Qt.Key.Key_V):
                self._on_validate_card()
                return True
            elif key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace, Qt.Key.Key_R):
                self._on_reject_card()
                return True
            elif key == Qt.Key.Key_E:
                self._on_edit_card()
                return True
        return super().eventFilter(obj, event)

    @Slot()
    def _on_cancel_generation(self) -> None:
        if self.orchestrator:
            self.orchestrator.cancel()
            self._set_all_generation_states(False)
            show_toast(self, "Pipeline annulé.", is_error=False)

    def _populate_results_table(self) -> None:
        """Remplit le tableau des cartes générées avec sélecteur de modèle par ligne."""
        saved_index = self.current_preview_index

        self.results_table.blockSignals(True)
        self.results_table.setRowCount(len(self.generated_cards))
        self.results_panel.set_tab_title(0, f"Cartes Générées ({len(self.generated_cards)})")

        headers = ["Modèle", "Recto / Texte Principal", "Verso / Détails", "Statut"]
        self.results_table.setColumnCount(len(headers))
        self.results_table.setHorizontalHeaderLabels(headers)

        _STATUS_META = {
            "Acceptée": ("Validée", "ph.check-circle", "success"),
            "Validée": ("Validée", "ph.check-circle", "success"),
            "Refusée": ("Refusée", "ph.x-circle", "danger"),
            "À valider": ("À valider", "ph.hourglass-simple", "warning"),
            "En attente": ("En attente", "ph.hourglass-simple", "warning"),
            "Enregistrée": ("Enregistrée", "ph.floppy-disk", "info"),
        }

        for row, card in enumerate(self.generated_cards):
            card["status"] = card.get("status", "À valider")
            card_model_name = card.get("model") or (self.current_model.name if self.current_model else "Basique")
            card["model"] = card_model_name

            front_text = card.get("Front") or card.get("Recto") or card.get("Texte") or card.get("Théorème") or ""
            back_text = card.get("Back") or card.get("Verso") or card.get("Remarques extra") or card.get("Démonstration") or ""
            status_text = card["status"]

            # --- Colonne 0 : Modèle (StyledComboBox) ---
            model_combo = StyledComboBox()
            model_combo.setFixedHeight(26)
            for m in self.models_cache:
                model_combo.addItem(m.name, m)
            idx = model_combo.findText(card_model_name)
            if idx >= 0:
                model_combo.setCurrentIndex(idx)

            def make_combo_handler(r=row, combo=model_combo):
                def handler(index: int):
                    new_model_name = combo.currentText()
                    if 0 <= r < len(self.generated_cards):
                        self.generated_cards[r]["model"] = new_model_name
                        if self.current_preview_index == r:
                            self._update_card_preview()

                return handler

            model_combo.currentIndexChanged.connect(make_combo_handler(row, model_combo))
            self.results_table.setCellWidget(row, 0, model_combo)

            # --- Colonne 1 : Recto / Texte Principal ---
            front_item = QTableWidgetItem(str(front_text))
            front_item.setToolTip(str(front_text))
            self.results_table.setItem(row, 1, front_item)

            # --- Colonne 2 : Verso / Détails ---
            back_item = QTableWidgetItem(str(back_text))
            back_item.setToolTip(str(back_text))
            self.results_table.setItem(row, 2, back_item)

            # --- Colonne 3 : Statut (Badge) ---
            label, icon_name, variant = _STATUS_META.get(status_text, (status_text, "ph.hourglass-simple", "warning"))

            badge_container = QWidget()
            badge_layout = QHBoxLayout(badge_container)
            badge_layout.setContentsMargins(6, 2, 6, 2)
            badge_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge = StatusBadge(label, icon_name=icon_name, variant=variant)
            badge_layout.addWidget(badge)

            self.results_table.setItem(row, 3, QTableWidgetItem())
            self.results_table.setCellWidget(row, 3, badge_container)

            self.results_table.setRowHeight(row, 38)

        self.results_table.blockSignals(False)

        # Restaurer la sélection sur la ligne courante
        if self.generated_cards:
            target = max(0, min(saved_index, len(self.generated_cards) - 1))
            self.results_table.selectRow(target)

        # Mettre à jour le bouton de sauvegarde
        self._refresh_save_button()

    def _update_card_preview(self) -> None:
        total = len(self.generated_cards)
        if total == 0:
            self.preview_widget.lbl_counter.setText("0 / 0")
            return

        self.current_preview_index = max(0, min(self.current_preview_index, total - 1))
        self.preview_widget.lbl_counter.setText(f"{self.current_preview_index + 1} / {total}")

        card = self.generated_cards[self.current_preview_index]
        card_model_name = card.get("model") or card.get("note_type")
        selected_nt = None
        if card_model_name and self.models_cache:
            for m in self.models_cache:
                if m.name.lower().strip() == str(card_model_name).lower().strip():
                    selected_nt = m
                    break
        if not selected_nt:
            selected_nt = self.current_model

        self.preview_widget.card_preview_widget.update_preview(
            note_type=selected_nt,
            fields_dict=card,
            override_templates=None,
        )

    @Slot()
    def _on_table_selection_changed(self) -> None:
        selected_rows = self.results_table.selectedItems()
        if selected_rows:
            row = self.results_table.row(selected_rows[0])
            if 0 <= row < len(self.generated_cards):
                self.current_preview_index = row
                self._update_card_preview()

    @Slot(QTableWidgetItem)
    def _on_cell_edited(self, item: QTableWidgetItem) -> None:
        row = item.row()
        col = item.column()
        if 0 <= row < len(self.generated_cards):
            text = item.text()
            card = self.generated_cards[row]
            card_model_name = card.get("model", "")
            if "cloze" in card_model_name.lower():
                if col == 1:
                    card["Texte"] = text
                elif col == 2:
                    card["Remarques extra"] = text
            else:
                if col == 1:
                    card["Front"] = text
                    card["Recto"] = text
                elif col == 2:
                    card["Back"] = text
                    card["Verso"] = text
            self._update_card_preview()

    @Slot()
    def _on_prev_card(self) -> None:
        if self.current_preview_index > 0:
            self.current_preview_index -= 1
            self.results_table.selectRow(self.current_preview_index)
            self._update_card_preview()

    @Slot()
    def _on_next_card(self) -> None:
        if self.current_preview_index < len(self.generated_cards) - 1:
            self.current_preview_index += 1
            self.results_table.selectRow(self.current_preview_index)
            self._update_card_preview()

    def _all_cards_processed(self) -> bool:
        """Retourne True si TOUTES les cartes ont un statut final (Enregistrée ou Refusée).
        Aucune carte ne reste en 'À valider' ou 'Validée'.
        """
        if not self.generated_cards:
            return False
        return all(card.get("status") in self._FINAL_STATUSES for card in self.generated_cards)

    def _count_validated(self) -> int:
        """Retourne le nombre de cartes prêtes à être enregistrées (statut == Validée)."""
        return sum(1 for card in self.generated_cards if card.get("status") == "Validée")

    def _count_by_status(self) -> dict[str, int]:
        """Retourne un résumé des effectifs par statut."""
        counts: dict[str, int] = {}
        for card in self.generated_cards:
            s = card.get("status", "À valider")
            counts[s] = counts.get(s, 0) + 1
        return counts

    def is_dirty(self) -> bool:
        """Indique si la vue contient des cartes générées non encore enregistrées."""
        return any(card.get("status") in ("Validée", "À valider", "En attente") for card in self.generated_cards)

    def _refresh_save_button(self) -> None:
        """Met à jour le label et l'état du bouton Enregistrer selon les cartes."""
        validated_count = self._count_validated()
        total_count = len(self.generated_cards)
        if total_count > 0:
            self.btn_save_anki.setText(f"Enregistrer dans la Forge ({validated_count}/{total_count})")
            self.btn_save_anki.setEnabled(True)
        else:
            self.btn_save_anki.setText("Enregistrer dans la Forge (0)")
            self.btn_save_anki.setEnabled(False)

    @Slot()
    def _on_validate_card(self) -> None:
        """Marque la carte comme Acceptée (statut → Validée) puis passe automatiquement à la suivante."""
        if not self.generated_cards or not (0 <= self.current_preview_index < len(self.generated_cards)):
            return
        next_index = self.current_preview_index + 1
        self.generated_cards[self.current_preview_index]["status"] = "Validée"
        self._populate_results_table()
        show_toast(self, "✅ Carte acceptée !")

        # Navigation automatique fluide vers la carte suivante
        if next_index < len(self.generated_cards):
            self.current_preview_index = next_index
            self.results_table.selectRow(self.current_preview_index)
            self._update_card_preview()
        else:
            self.results_table.selectRow(self.current_preview_index)
            self._update_card_preview()
            show_toast(self, "✅ Toutes les cartes ont été passées en revue !", is_error=False)

    @Slot()
    def _on_edit_card(self) -> None:
        """Ouvre le dialogue d'édition. Le statut de la carte est préservé (non réinitialisé).
        L'édition ne sauvegarde PAS dans la Forge — elle met à jour uniquement l'état mémoire."""
        if not self.generated_cards or not (0 <= self.current_preview_index < len(self.generated_cards)):
            return

        card = self.generated_cards[self.current_preview_index]
        previous_status = card.get("status", "À valider")

        dlg = CardEditDialog(
            front=card.get("Front", card.get("Recto", "")),
            back=card.get("Back", card.get("Verso", "")),
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_front, new_back = dlg.get_data()
            card["Front"] = new_front
            card["Back"] = new_back
            card["status"] = previous_status
            self._populate_results_table()
            self._update_card_preview()
            show_toast(self, "✏️ Carte modifiée en mémoire.")

    @Slot()
    def _on_reject_card(self) -> None:
        """Marque la carte comme Refusée (sans la supprimer) et passe à la suivante."""
        if self.generated_cards and 0 <= self.current_preview_index < len(self.generated_cards):
            next_index = self.current_preview_index + 1
            card = self.generated_cards[self.current_preview_index]
            card["status"] = "Refusée"
            self._populate_results_table()
            show_toast(self, f"❌ Carte '{card.get('Front', '')[:20]}...' marquée Refusée.")

            # Navigation automatique vers la carte suivante
            if next_index < len(self.generated_cards):
                self.current_preview_index = next_index
                self.results_table.selectRow(self.current_preview_index)
                self._update_card_preview()
            else:
                self.results_table.selectRow(self.current_preview_index)
                self._update_card_preview()
                show_toast(self, "Toutes les cartes ont été passées en revue.", is_error=False)

    @Slot()
    def _on_save_anki(self) -> None:
        """Enregistre dans la Forge les cartes avec arbitrage si des cartes restent en attente."""
        if not self.generated_cards:
            show_toast(self, "Aucune carte générée à enregistrer.", is_error=True)
            return

        pending_cards = [c for c in self.generated_cards if c.get("status") in ("À valider", "En attente")]
        validated_cards = [c for c in self.generated_cards if c.get("status") == "Validée"]

        if pending_cards:
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Icon.Question)
            msg_box.setWindowTitle("Enregistrement des Cartes")
            msg_box.setText(f"Il reste <b>{len(pending_cards)} carte(s)</b> en attente de décision.")
            msg_box.setInformativeText("Souhaitez-vous tout valider automatiquement ou enregistrer uniquement les cartes déjà marquées 'Validée' ?")

            btn_accept_all = msg_box.addButton(
                f"Tout Valider et Enregistrer ({len(validated_cards) + len(pending_cards)})",
                QMessageBox.ButtonRole.AcceptRole,
            )
            btn_save_validated = msg_box.addButton(
                f"Enregistrer Validées Uniquement ({len(validated_cards)})",
                QMessageBox.ButtonRole.ActionRole,
            )
            _ = msg_box.addButton("Continuer la Revue", QMessageBox.ButtonRole.RejectRole)

            msg_box.exec()
            clicked_btn = msg_box.clickedButton()

            if clicked_btn == btn_accept_all:
                for c in self.generated_cards:
                    if c.get("status") in ("À valider", "En attente"):
                        c["status"] = "Validée"
                validated_cards = [c for c in self.generated_cards if c.get("status") == "Validée"]
            elif clicked_btn == btn_save_validated:
                if not validated_cards:
                    show_toast(self, "Aucune carte n'a encore été marquée 'Validée'. Utilisez 'Garder' ou validez tout.", is_error=True)
                    return
            else:
                return  # Continuer la revue

        if not validated_cards:
            show_toast(self, "Aucune carte 'Validée' à enregistrer. Utilisez 'Garder' pour valider des cartes.", is_error=True)
            return

        selected_nt = self.current_model
        if not selected_nt:
            show_toast(self, "Aucun modèle de carte sélectionné.", is_error=True)
            return

        deck_data = self.current_deck
        deck_name = deck_data.name if deck_data and hasattr(deck_data, "name") else "Général"

        saved_count = 0
        try:
            for card in validated_cards:
                card_model_name = card.get("model") or card.get("note_type")
                target_nt = None
                if card_model_name and self.models_cache:
                    for m in self.models_cache:
                        if m.name.lower().strip() == str(card_model_name).lower().strip():
                            target_nt = m
                            break
                if not target_nt:
                    target_nt = selected_nt

                try:
                    schema = json.loads(str(target_nt.fields_schema)) if target_nt.fields_schema else ["Front", "Back"]
                except Exception:
                    schema = ["Front", "Back"]

                fields = {}
                for f_name in schema:
                    val = card.get(f_name)
                    if val is None:
                        if f_name.lower() in ("front", "recto"):
                            val = card.get("Front") or card.get("Recto") or card.get("Texte") or ""
                        elif f_name.lower() in ("back", "verso"):
                            val = card.get("Back") or card.get("Verso") or card.get("Remarques extra") or ""
                        elif f_name.lower() in ("texte",):
                            val = card.get("Texte") or card.get("Front") or ""
                        elif f_name.lower() in ("remarques extra", "remarque", "extra"):
                            val = card.get("Remarques extra") or card.get("Back") or ""
                        else:
                            val = ""
                    fields[f_name] = str(val) if val is not None else ""

                tags = ["ankiforge_generated"]
                if getattr(self, "current_source_title", None) and self.current_source_title != "Saisie Libre":
                    clean_title = self.current_source_title.replace(" ", "_").replace("-", "_").lower()
                    if clean_title.endswith((".pdf", ".md", ".txt")):
                        clean_title = clean_title.rsplit(".", 1)[0]
                    tags.append(f"source:{clean_title}")

                deck_obj, _ = DeckModel.get_or_create(name=deck_name)
                note = NoteManager.create_note(
                    note_type=target_nt,
                    deck=deck_obj,
                    content_dict=fields,
                    tags=tags,
                    source="ai",
                )

                if note:
                    target_chunk_id = card.get("chunk_id") or getattr(self, "current_source_chunk_id", None)
                    if target_chunk_id:
                        try:
                            NoteChunkLinkModel.get_or_create(note=note, chunk_id=int(target_chunk_id))
                        except Exception as e:
                            logger.warning("Erreur lors de la création du lien NoteChunkLink: %s", e)

                card["status"] = "Enregistrée"
                saved_count += 1

            self._populate_results_table()
            show_toast(self, f"💾 {saved_count} carte(s) enregistrée(s) dans la Forge !", is_error=False)
            self._check_completion()

        except Exception as e:
            logger.exception("Erreur lors de la sauvegarde dans Anki: %s", e)
            QMessageBox.critical(self, "Erreur de Sauvegarde", f"Échec de l'enregistrement dans Anki : {str(e)}")

    def _check_completion(self) -> None:
        """Vérifie si toutes les cartes ont reçu un statut final.
        Si oui : toast de félicitation et réinitialisation de l'état de travail.
        """
        if not self._all_cards_processed():
            counts = self._count_by_status()
            pending = counts.get("À valider", 0) + counts.get("En attente", 0)
            if pending:
                show_toast(
                    self,
                    f"⏳ {pending} carte(s) restante(s) à traiter (Garder ou Rejeter).",
                    is_error=False,
                )
            return

        counts = self._count_by_status()
        saved = counts.get("Enregistrée", 0)
        refused = counts.get("Refusée", 0)
        show_toast(
            self,
            f"🎉 Session terminée : {saved} carte(s) enregistrée(s), {refused} refusée(s).",
            is_error=False,
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        """Affiche un modal d'avertissement si des cartes générées n'ont pas encore été enregistrées."""
        import os

        # Ne pas bloquer si la vue n'est pas visible ou en environnement de test headless
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen" or not self.isVisible() or getattr(self, "_skip_close_dialog", False):
            event.accept()
            return

        if self.is_dirty():
            unsaved_count = sum(1 for c in self.generated_cards if c.get("status") in ("Validée", "À valider", "En attente"))
            reply = QMessageBox.question(
                self,
                "Quitter le Studio de Création ?",
                f"{unsaved_count} carte(s) générée(s) n'ont pas encore été enregistrées dans la Forge.\n\nVoulez-vous vraiment fermer sans enregistrer ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return
        event.accept()

    def refresh_theme(self, profile: Any) -> None:
        """Rafraîchit à chaud tous les composants du studio de création."""
        if hasattr(self, "preview_widget") and hasattr(self.preview_widget, "card_preview_widget"):
            self.preview_widget.card_preview_widget.refresh_theme(profile)

        if hasattr(self, "config_panel"):
            self.config_panel.setStyleSheet(f"border-right: 1px solid {profile.border_color};")

        if hasattr(self, "btn_select_deck"):
            self.btn_select_deck.setIcon(load_phosphor_icon("ph.folder-open", color=profile.text_muted))
            self.btn_select_deck.setStyleSheet(
                f"text-align: left; padding: 6px 10px; border-radius: 4px; "
                f"border: 1px solid {profile.border_color}; background: {profile.bg_input}; "
                f"color: {profile.text_primary}; font-weight: normal;"
            )

        if hasattr(self, "btn_select_model"):
            self.btn_select_model.setIcon(load_phosphor_icon("ph.file-code", color=profile.text_muted))
            self.btn_select_model.setStyleSheet(
                f"text-align: left; padding: 6px 10px; border-radius: 4px; "
                f"border: 1px solid {profile.border_color}; background: {profile.bg_input}; "
                f"color: {profile.text_primary}; font-weight: normal;"
            )

        if hasattr(self, "vision_card"):
            self.vision_card.setStyleSheet(f"""
                QFrame#visionCard {{
                    background-color: {profile.bg_input};
                    border: 1px solid {profile.border_color};
                    border-radius: 6px;
                }}
                QFrame#visionCard:hover {{
                    border-color: {profile.accent_primary};
                }}
            """)
        if hasattr(self, "lbl_vision_title"):
            self.lbl_vision_title.setStyleSheet(f"color: {profile.text_primary}; font-weight: 600; font-size: 12px;")
        if hasattr(self, "lbl_vision_desc"):
            self.lbl_vision_desc.setStyleSheet(f"color: {profile.text_muted}; font-size: 11px;")
        if hasattr(self, "lbl_vision_icon"):
            self.lbl_vision_icon.setPixmap(load_phosphor_icon("ph.eye-closed", color=profile.text_muted).pixmap(16, 16))

        if hasattr(self, "pages_input_frame"):
            self.pages_input_frame.setStyleSheet(f"""
                QFrame {{
                    background-color: {profile.bg_input};
                    border: 1px solid {profile.border_color};
                    border-radius: {profile.radius_md}px;
                    padding: 2px 6px;
                }}
                QSpinBox {{
                    background: transparent;
                    border: none;
                    color: {profile.text_primary};
                    font-weight: bold;
                }}
                QSpinBox::up-button, QSpinBox::down-button {{
                    width: 0px;
                }}
            """)

        if hasattr(self, "advanced_container"):
            self.advanced_container.setStyleSheet(f"""
                background-color: {profile.bg_input};
                border-radius: {profile.radius_sm}px;
                border: 1px solid {profile.border_color};
            """)

        from ankiforge.ui.components.panels import IdePanel

        for panel in self.findChildren(IdePanel):
            if hasattr(panel, "refresh_theme"):
                panel.refresh_theme(profile)


CreationTab = CreationView
