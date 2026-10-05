"""
Dialogue modal de configuration pour la transcription d'un album ou de planches sélectionnées.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import DocumentModel, DocumentPageModel
from ankiforge.services.ai.album_transcription_types import (
    AlbumTranscriptionOptions,
    parse_page_ranges,
)
from ankiforge.services.ai.vision_category_service import (
    VisionCategoryService,
    get_closed_image_data_types,
    get_image_data_type,
    is_engine_compatible_with_type,
)
from ankiforge.services.settings_service import SettingsService
from ankiforge.ui.components import Badge, IconButton, PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.i18n import tr
from ankiforge.utils.icon_loader import load_on_accent_icon, load_phosphor_icon

logger = logging.getLogger(__name__)


class AlbumTranscriptionDialog(QDialog):
    """
    Dialogue modal de configuration de transcription d'album.

    Permet de sélectionner un périmètre exclusif (avec décompte dynamique),
    le moteur de vision, les directives de formatage et les consignes contextuelles.
    """

    transcription_requested = Signal(object)  # AlbumTranscriptionOptions

    def __init__(
        self,
        doc: DocumentModel,
        parent: QWidget | None = None,
        category_service: VisionCategoryService | None = None,
    ) -> None:
        super().__init__(parent)
        self._doc = doc
        self._category_service = category_service or VisionCategoryService()
        self._pages: list[DocumentPageModel] = list(DocumentPageModel.select().where(DocumentPageModel.document == self._doc).order_by(DocumentPageModel.page_number.asc()))

        self.setObjectName("albumTranscriptionDialog")
        self.setWindowTitle(self.tr("Transcription de l'album"))
        self.resize(700, 760)
        self.setMinimumSize(600, 620)
        self.setStyleSheet(f"""
            QDialog#albumTranscriptionDialog {{
                background-color: {DesignTokens.BG_MAIN};
            }}
            QLabel {{
                border: none;
                background: transparent;
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QCheckBox, QRadioButton {{
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 12px;
                spacing: 8px;
            }}
            QCheckBox:disabled, QRadioButton:disabled {{
                color: {DesignTokens.TEXT_MUTED};
            }}
            QCheckBox::indicator, QRadioButton::indicator {{
                width: 15px;
                height: 15px;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 3px;
                background-color: {DesignTokens.BG_INPUT};
            }}
            QRadioButton::indicator {{
                border-radius: 7px;
            }}
            QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
            QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
                background-color: {DesignTokens.ACCENT_PRIMARY};
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
            QScrollBar:vertical {{
                border: none;
                background: transparent;
                width: 6px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background-color: {DesignTokens.BORDER_COLOR};
                min-height: 20px;
                border-radius: 3px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {DesignTokens.TEXT_MUTED};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
        """)

        self._setup_ui()
        self._populate_data_types()
        self._populate_categories()
        self._update_scope_counts()
        self._init_default_scope()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.setSpacing(14)

        # ── 1. En-tête ────────────────────────────────────────────────────────
        header_layout = QVBoxLayout()
        header_layout.setSpacing(4)

        title_row = QHBoxLayout()
        title_ico = QLabel()
        title_ico.setPixmap(load_phosphor_icon("ph.sparkle", color=DesignTokens.COLOR_YELLOW).pixmap(22, 22))
        title_row.addWidget(title_ico)

        lbl_title = QLabel(self.tr("Transcription de l'album"))
        lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 17px; font-weight: bold;")
        title_row.addWidget(lbl_title)
        title_row.addStretch()
        header_layout.addLayout(title_row)

        doc_title = self._doc.title if self._doc else "Album"
        lbl_sub = QLabel(tr("Document : « %1 » — %2 planche(s) au total", doc_title, len(self._pages)))
        lbl_sub.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 12px;")
        header_layout.addWidget(lbl_sub)
        main_layout.addLayout(header_layout)

        # ── Zone Scrollable pour les réglages ────────────────────────────────
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setStyleSheet("background: transparent; border: none;")

        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(scroll_content)
        content_layout.setContentsMargins(0, 0, 8, 0)
        content_layout.setSpacing(14)

        # ── 2. Section Périmètre de transcription ─────────────────────────────
        scope_card, scope_layout = self._create_card("Périmètre de transcription (Portée)", "ph.selection", "scopeCard")

        self.scope_button_group = QButtonGroup(self)
        self.scope_button_group.setExclusive(True)

        # Mode Tout l'album
        row_all = QHBoxLayout()
        self.rb_all = QRadioButton(self.tr("Tout l'album"))
        self.lbl_count_all = Badge("(0)", variant="neutral")
        row_all.addWidget(self.rb_all)
        row_all.addWidget(self.lbl_count_all)
        row_all.addStretch()
        self.scope_button_group.addButton(self.rb_all)
        scope_layout.addLayout(row_all)

        # Mode Non transcrites
        row_untrans = QHBoxLayout()
        self.rb_untranscribed = QRadioButton(self.tr("Planches non transcrites uniquement"))
        self.lbl_count_untranscribed = Badge("(0)", variant="neutral")
        row_untrans.addWidget(self.rb_untranscribed)
        row_untrans.addWidget(self.lbl_count_untranscribed)
        row_untrans.addStretch()
        self.scope_button_group.addButton(self.rb_untranscribed)
        scope_layout.addLayout(row_untrans)

        # Mode Périmées (stale)
        row_stale = QHBoxLayout()
        self.rb_stale = QRadioButton(self.tr("Planches périmées (modifiées/pivotées)"))
        self.lbl_count_stale = Badge("(0)", variant="warning")
        row_stale.addWidget(self.rb_stale)
        row_stale.addWidget(self.lbl_count_stale)
        row_stale.addStretch()
        self.scope_button_group.addButton(self.rb_stale)
        scope_layout.addLayout(row_stale)

        # Mode Intervalle personnalisé
        row_custom = QHBoxLayout()
        self.rb_custom = QRadioButton(self.tr("Intervalle personnalisé"))
        self.lbl_count_custom = Badge("(0)", variant="neutral")
        row_custom.addWidget(self.rb_custom)
        row_custom.addWidget(self.lbl_count_custom)
        row_custom.addStretch()
        self.scope_button_group.addButton(self.rb_custom)
        scope_layout.addLayout(row_custom)

        self.le_custom_range = QLineEdit()
        self.le_custom_range.setPlaceholderText(self.tr("ex: 1-5, 8, 12-15"))
        self.le_custom_range.setStyleSheet(f"""
            QLineEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 12px;
                padding: 6px 10px;
                margin-left: 24px;
            }}
            QLineEdit:focus {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
            QLineEdit:disabled {{
                background-color: {DesignTokens.BG_PANEL};
                color: {DesignTokens.TEXT_MUTED};
            }}
        """)
        self.le_custom_range.setEnabled(False)
        self.le_custom_range.textChanged.connect(self._on_custom_range_changed)
        scope_layout.addWidget(self.le_custom_range)

        self.rb_all.toggled.connect(self._on_scope_mode_changed)
        self.rb_untranscribed.toggled.connect(self._on_scope_mode_changed)
        self.rb_stale.toggled.connect(self._on_scope_mode_changed)
        self.rb_custom.toggled.connect(self._on_scope_mode_changed)

        content_layout.addWidget(scope_card)

        # ── 3. Axe 1 : Type de donnée d'image ─────────────────────────────────
        data_type_card, data_type_layout = self._create_card("1. Type de donnée d'image", "ph.shapes", "dataTypeCard")

        dt_row = QHBoxLayout()
        dt_row.setSpacing(8)
        lbl_dt = QLabel(self.tr("Contenu des planches :"))
        lbl_dt.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px;")
        dt_row.addWidget(lbl_dt)

        self.combo_data_type = QComboBox()
        self.combo_data_type.setStyleSheet(f"""
            QComboBox {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 12px;
                padding: 4px 8px;
            }}
        """)
        dt_row.addWidget(self.combo_data_type, 1)
        data_type_layout.addLayout(dt_row)

        self.lbl_data_type_desc = QLabel()
        self.lbl_data_type_desc.setWordWrap(True)
        self.lbl_data_type_desc.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        data_type_layout.addWidget(self.lbl_data_type_desc)

        content_layout.addWidget(data_type_card)

        # ── 4. Axe 2 : Moteur de vision adapté ────────────────────────────────
        engine_card, engine_layout = self._create_card("2. Moteur de vision adapté", "ph.brain", "engineCard")

        combo_row = QHBoxLayout()
        combo_row.setSpacing(8)
        lbl_cat = QLabel(self.tr("Moteur sélectionné :"))
        lbl_cat.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px;")
        combo_row.addWidget(lbl_cat)

        self.combo_category = QComboBox()
        self.combo_category.setStyleSheet(f"""
            QComboBox {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 12px;
                padding: 4px 8px;
            }}
        """)
        self.combo_category.currentIndexChanged.connect(self._on_category_changed)
        combo_row.addWidget(self.combo_category, 1)

        self.btn_browse_catalog = IconButton("ph.sparkle", "Explorer le catalogue des modèles de vision...", 28, self)
        self.btn_browse_catalog.clicked.connect(self._open_catalog)
        combo_row.addWidget(self.btn_browse_catalog)
        engine_layout.addLayout(combo_row)

        self.lbl_cat_description = QLabel()
        self.lbl_cat_description.setWordWrap(True)
        self.lbl_cat_description.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        engine_layout.addWidget(self.lbl_cat_description)

        # Badges de capacités
        badges_row = QHBoxLayout()
        badges_row.setSpacing(6)
        self.badge_vision = Badge(tr("Vision multimodale"), variant="info")
        self.badge_thinking = Badge(tr("CoT Thinking"), variant="primary")
        self.badge_thinking.setVisible(False)
        badges_row.addWidget(self.badge_vision)
        badges_row.addWidget(self.badge_thinking)
        badges_row.addStretch()
        engine_layout.addLayout(badges_row)

        # Bandeau didactique spécifique à Apple Vision
        self.hardware_notice = QFrame()
        self.hardware_notice.setObjectName("hardwareNotice")
        self.hardware_notice.setVisible(False)
        self.hardware_notice.setStyleSheet(f"""
            QFrame#hardwareNotice {{
                background-color: {DesignTokens.BG_INPUT};
                border-left: 3px solid {DesignTokens.COLOR_BLUE};
                border-top: none;
                border-right: none;
                border-bottom: none;
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        hw_layout = QHBoxLayout(self.hardware_notice)
        hw_layout.setContentsMargins(8, 8, 8, 8)
        hw_layout.setSpacing(8)
        hw_ico = QLabel()
        hw_ico.setPixmap(load_phosphor_icon("ph.info", color=DesignTokens.COLOR_BLUE).pixmap(18, 18))
        hw_ico.setStyleSheet("border: none; background: transparent;")
        hw_layout.addWidget(hw_ico)
        hw_lbl = QLabel(
            self.tr(
                "Moteur optique haute vitesse : optimisé pour le texte suivi et la prose en bloc. "
                "Pour les tableaux structurés, schémas et formules mathématiques, privilégiez "
                "un modèle multimodal (VLM, ex: Qwen2.5-VL ou Gemini)."
            )
        )
        hw_lbl.setWordWrap(True)
        hw_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px; border: none; background: transparent;")
        hw_layout.addWidget(hw_lbl, 1)
        engine_layout.addWidget(self.hardware_notice)

        # Tiroir avancé (Surcharges locales de modèle, température, thinking)
        self.advanced_drawer = QFrame()
        self.advanced_drawer.setObjectName("advancedDrawer")
        self.advanced_drawer.setStyleSheet(f"""
            QFrame#advancedDrawer {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        adv_layout = QVBoxLayout(self.advanced_drawer)
        adv_layout.setContentsMargins(10, 8, 10, 8)
        adv_layout.setSpacing(8)

        adv_row1 = QHBoxLayout()
        lbl_model = QLabel(self.tr("Surcharge modèle :"))
        lbl_model.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px;")
        adv_row1.addWidget(lbl_model)
        self.le_model_override = QLineEdit()
        self.le_model_override.setPlaceholderText(self.tr("Laisser vide pour utiliser le modèle par défaut"))
        self.le_model_override.setStyleSheet(f"""
            QLineEdit {{
                background-color: {DesignTokens.BG_MAIN};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 11px;
                padding: 4px 8px;
            }}
        """)
        adv_row1.addWidget(self.le_model_override, 1)
        adv_layout.addLayout(adv_row1)

        adv_row2 = QHBoxLayout()
        lbl_temp = QLabel(self.tr("Température :"))
        lbl_temp.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px;")
        adv_row2.addWidget(lbl_temp)
        self.spin_temp = QDoubleSpinBox()
        self.spin_temp.setRange(0.0, 1.0)
        self.spin_temp.setSingleStep(0.1)
        self.spin_temp.setValue(0.2)
        adv_row2.addWidget(self.spin_temp)

        lbl_think = QLabel(self.tr("Budget de réflexion :"))
        lbl_think.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px;")
        adv_row2.addWidget(lbl_think)
        self.spin_thinking = QSpinBox()
        self.spin_thinking.setRange(0, 32768)
        self.spin_thinking.setSingleStep(1024)
        self.spin_thinking.setValue(0)
        self.spin_thinking.setSpecialValueText("Désactivé")
        adv_row2.addWidget(self.spin_thinking)
        adv_row2.addStretch()
        adv_layout.addLayout(adv_row2)

        engine_layout.addWidget(self.advanced_drawer)
        content_layout.addWidget(engine_card)

        # ── 4. Section Directives de transcription & Formatage ────────────────
        self.directives_group, dir_layout = self._create_card("Directives d'extraction & Formatage", "ph.text-t", "directivesCard")

        self.cb_latex = QCheckBox(self.tr("Formules mathématiques et scientifiques en LaTeX ($...$, $$...$$)"))
        self.cb_latex.setChecked(True)
        dir_layout.addWidget(self.cb_latex)

        self.cb_tables = QCheckBox(self.tr("Tableaux structurés en Markdown ou HTML"))
        self.cb_tables.setChecked(True)
        dir_layout.addWidget(self.cb_tables)

        self.cb_headings = QCheckBox(self.tr("Structure et hiérarchie par titres Markdown (#, ##)"))
        self.cb_headings.setChecked(True)
        dir_layout.addWidget(self.cb_headings)

        self.cb_figures = QCheckBox(self.tr("Descriptions textuelles denses des figures et schémas ([Figure: ...])"))
        self.cb_figures.setChecked(False)
        dir_layout.addWidget(self.cb_figures)

        lbl_inst = QLabel(self.tr("Consignes contextuelles spécifiques :"))
        lbl_inst.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px; font-weight: 500; margin-top: 6px;")
        dir_layout.addWidget(lbl_inst)

        self.txt_custom_instructions = QTextEdit()
        self.txt_custom_instructions.setPlaceholderText(self.tr("ex: Vocabulaire anatomique en latin, ne pas transcrire les en-têtes et bas de page..."))
        self.txt_custom_instructions.setFixedHeight(70)
        self.txt_custom_instructions.setStyleSheet(f"""
            QTextEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 11px;
                padding: 6px;
            }}
        """)
        dir_layout.addWidget(self.txt_custom_instructions)

        content_layout.addWidget(self.directives_group)

        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area, 1)

        # ── 5. Barre d'actions inférieure ─────────────────────────────────────
        action_bar = QHBoxLayout()
        action_bar.setSpacing(10)

        self.lbl_status_feedback = QLabel()
        self.lbl_status_feedback.setStyleSheet(f"color: {DesignTokens.COLOR_RED}; font-size: 11px;")
        action_bar.addWidget(self.lbl_status_feedback)
        action_bar.addStretch()

        self.btn_cancel = SecondaryButton("Annuler")
        self.btn_cancel.clicked.connect(self.reject)
        action_bar.addWidget(self.btn_cancel)

        self.btn_start = PrimaryButton("Démarrer la transcription")
        self.btn_start.setIcon(load_on_accent_icon("ph.sparkle"))
        self.btn_start.clicked.connect(self._on_start_clicked)
        action_bar.addWidget(self.btn_start)

        main_layout.addLayout(action_bar)

    def _create_card(self, title: str, icon_name: str, object_name: str) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName(object_name)
        card.setStyleSheet(f"""
            QFrame#{object_name} {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 14, 14, 14)
        card_layout.setSpacing(10)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        ico = QLabel()
        ico.setPixmap(load_phosphor_icon(icon_name, color=DesignTokens.ACCENT_PRIMARY).pixmap(16, 16))
        ico.setStyleSheet("border: none; background: transparent;")
        header.addWidget(ico)
        lbl = QLabel(title)
        lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 13px; font-weight: bold; border: none; background: transparent;")
        header.addWidget(lbl)
        header.addStretch()
        card_layout.addLayout(header)
        return card, card_layout

    def _populate_data_types(self) -> None:
        """Alimente le sélecteur avec la liste fermée des 6 types de données d'image (CONTEXT.md:56)."""
        types = get_closed_image_data_types()
        self.combo_data_type.blockSignals(True)
        self.combo_data_type.clear()
        for dt in types:
            icon = load_phosphor_icon(dt.icon, color=DesignTokens.ACCENT_PRIMARY)
            self.combo_data_type.addItem(icon, dt.name, dt.id)
        self.combo_data_type.blockSignals(False)

        # Mémorisation et restauration du dernier type sélectionné par profil
        last_type = str(SettingsService.get("ai/last_image_data_type", default="texte_imprime"))
        target_idx = self.combo_data_type.findData(last_type)
        if target_idx >= 0:
            self.combo_data_type.setCurrentIndex(target_idx)
        elif self.combo_data_type.count() > 0:
            self.combo_data_type.setCurrentIndex(0)

        dt_id = self.combo_data_type.currentData()
        dt_obj = get_image_data_type(dt_id)
        if dt_obj:
            self.lbl_data_type_desc.setText(dt_obj.description)

        self.combo_data_type.currentIndexChanged.connect(self._on_data_type_changed)

    def _on_data_type_changed(self) -> None:
        """Réaction au changement de type de donnée : actualise la description et borne les moteurs candidats."""
        dt_id = self.combo_data_type.currentData()
        dt_obj = get_image_data_type(dt_id)
        if dt_obj:
            self.lbl_data_type_desc.setText(dt_obj.description)

        self._populate_categories()

    def _populate_categories(self) -> None:
        """Alimente la liste des moteurs de vision compatibles avec le type de donnée sélectionné."""
        dt_id = self.combo_data_type.currentData() if hasattr(self, "combo_data_type") else "texte_imprime"
        categories = self._category_service.get_categories()

        # Le type de donnée d'image borne l'ensemble des candidats moteur (critère 3)
        compatible_categories = [cat for cat in categories if is_engine_compatible_with_type(cat, dt_id)]

        prev_cat_id = self.combo_category.currentData() if hasattr(self, "combo_category") else None

        self.combo_category.blockSignals(True)
        self.combo_category.clear()
        for cat in compatible_categories:
            self.combo_category.addItem(cat.name, cat.id)
        self.combo_category.blockSignals(False)

        if compatible_categories:
            target_idx = self.combo_category.findData(prev_cat_id)
            if target_idx >= 0:
                self.combo_category.setCurrentIndex(target_idx)
            else:
                self.combo_category.setCurrentIndex(0)
            self._on_category_changed()

    def _on_category_changed(self) -> None:
        """Met à jour les détails, badges et paramètres du moteur de vision sélectionné."""
        cat_id = self.combo_category.currentData()
        category = self._category_service.get_category_by_id(cat_id) if cat_id else None
        if not category:
            return

        self.lbl_cat_description.setText(category.description)
        self.spin_temp.setValue(category.temperature)

        # Le budget de tokens suit strictement le modèle, jamais le type (critère 4)
        self.spin_thinking.setValue(category.thinking_budget)

        is_hardware = category.id == "hardware" or category.provider == "native"
        self.hardware_notice.setVisible(is_hardware)
        self.directives_group.setEnabled(not is_hardware)
        self.advanced_drawer.setEnabled(not is_hardware)

        # Actualisation des badges de capacités
        if is_hardware:
            self.badge_vision.setText(self.tr("OCR optique local"))
            self.badge_vision.set_variant("neutral")
            self.badge_thinking.setVisible(False)
        else:
            self.badge_vision.setText(self.tr("Vision multimodale"))
            self.badge_vision.set_variant("info")
            if category.thinking_budget > 0:
                self.badge_thinking.setText(tr("CoT Thinking (%1t)", category.thinking_budget))
                self.badge_thinking.setVisible(True)
            else:
                self.badge_thinking.setVisible(False)

    def _open_catalog(self) -> None:
        """Ouvre le catalogue de modèles restreint aux capacités de vision (critère 5)."""
        from ankiforge.ui.components.model_selector.dialog import ModelDiscoveryDialog

        curr_id = self.combo_category.currentData()
        dlg = ModelDiscoveryDialog(
            current_model_id=str(curr_id) if curr_id else None,
            picker_mode=True,
            require_vision=True,
            parent=self,
        )
        if dlg.exec():
            selected = dlg.get_selected_model()
            if selected:
                m_id = getattr(selected, "model_id", None) or getattr(selected, "id", None)
                if m_id:
                    self._populate_categories()
                    idx = self.combo_category.findData(str(m_id))
                    if idx >= 0:
                        self.combo_category.setCurrentIndex(idx)
                    else:
                        d_name = getattr(selected, "display_name", str(m_id))
                        self.combo_category.addItem(d_name, str(m_id))
                        self.combo_category.setCurrentIndex(self.combo_category.count() - 1)
                    self._on_category_changed()

    def _update_scope_counts(self) -> None:
        total = len(self._pages)
        untranscribed = sum(1 for p in self._pages if not (p.ocr_text and p.ocr_text.strip()))
        stale = sum(1 for p in self._pages if getattr(p, "status", None) == "stale")

        self.lbl_count_all.setText(tr("(%1)", total))
        self.lbl_count_untranscribed.setText(tr("(%1)", untranscribed))
        self.lbl_count_stale.setText(tr("(%1)", stale))

        self._refresh_custom_count()

    def _init_default_scope(self) -> None:
        stale = sum(1 for p in self._pages if getattr(p, "status", None) == "stale")
        untranscribed = sum(1 for p in self._pages if not (p.ocr_text and p.ocr_text.strip()))

        if stale > 0:
            self.rb_stale.setChecked(True)
        elif untranscribed > 0:
            self.rb_untranscribed.setChecked(True)
        else:
            self.rb_all.setChecked(True)

        self._validate_and_update_button()

    def _on_scope_mode_changed(self) -> None:
        is_custom = self.rb_custom.isChecked()
        self.le_custom_range.setEnabled(is_custom)
        if is_custom:
            self.le_custom_range.setFocus()
        self._validate_and_update_button()

    def _on_custom_range_changed(self) -> None:
        self._refresh_custom_count()
        self._validate_and_update_button()

    def _refresh_custom_count(self) -> None:
        max_page = max((p.page_number for p in self._pages), default=0)
        valid_page_nums = parse_page_ranges(self.le_custom_range.text(), max_page)
        self.lbl_count_custom.setText(tr("(%1)", len(valid_page_nums)))

    def _resolve_target_page_ids(self) -> list[int]:
        if self.rb_stale.isChecked():
            return [p.id for p in self._pages if getattr(p, "status", None) == "stale"]
        if self.rb_untranscribed.isChecked():
            return [p.id for p in self._pages if not (p.ocr_text and p.ocr_text.strip())]
        if self.rb_custom.isChecked():
            max_page = max((p.page_number for p in self._pages), default=0)
            valid_page_nums = parse_page_ranges(self.le_custom_range.text(), max_page)
            return [p.id for p in self._pages if p.page_number in valid_page_nums]
        # rb_all
        return [p.id for p in self._pages]

    def _validate_and_update_button(self) -> None:
        targets = self._resolve_target_page_ids()
        count = len(targets)

        if count == 0:
            self.btn_start.setEnabled(False)
            self.lbl_status_feedback.setText(self.tr("Aucune planche ciblée avec ce filtre."))
        else:
            self.btn_start.setEnabled(True)
            self.lbl_status_feedback.setText("")

    def get_options(self) -> AlbumTranscriptionOptions:
        scope_mode = "all"
        if self.rb_untranscribed.isChecked():
            scope_mode = "untranscribed"
        elif self.rb_stale.isChecked():
            scope_mode = "stale"
        elif self.rb_custom.isChecked():
            scope_mode = "custom"

        model_override = self.le_model_override.text().strip() or None
        temp_val = self.spin_temp.value()
        think_val = self.spin_thinking.value()
        data_type_id = str(self.combo_data_type.currentData() or "texte_imprime")

        return AlbumTranscriptionOptions(
            scope_mode=scope_mode,
            custom_range=self.le_custom_range.text().strip(),
            target_page_ids=self._resolve_target_page_ids(),
            category_id=str(self.combo_category.currentData() or "structured"),
            model_override=model_override,
            temperature_override=temp_val,
            thinking_budget_override=think_val if think_val > 0 else None,
            include_latex=self.cb_latex.isChecked(),
            include_tables=self.cb_tables.isChecked(),
            include_figures=self.cb_figures.isChecked(),
            include_headings=self.cb_headings.isChecked(),
            custom_instructions=self.txt_custom_instructions.toPlainText().strip(),
            data_type=data_type_id,
        )

    def _on_start_clicked(self) -> None:
        opts = self.get_options()
        if not opts.target_page_ids:
            return
        SettingsService.set("ai/last_image_data_type", opts.data_type, category="ai")
        self.transcription_requested.emit(opts)
        self.accept()
