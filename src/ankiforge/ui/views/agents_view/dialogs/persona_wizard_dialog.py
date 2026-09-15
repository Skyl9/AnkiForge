"""Assistant et Galerie de Modèles pour la création rapide d'Agents IA (Wizard)."""

from __future__ import annotations

import json
import logging
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import (
    PersonaFolderModel,
    PersonaModel,
    db,
)
from ankiforge.services.ai.persona_templates import PERSONA_TEMPLATES, PersonaTemplate
from ankiforge.services.ai.persona_version_service import PersonaVersionService
from ankiforge.ui.components import (
    Badge,
    GlowLineEdit,
    PrimaryButton,
    SecondaryButton,
    StyledComboBox,
    StyledLineEdit,
)
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.views.agents_view.constants import PERSONA_TYPE_SPECS
from ankiforge.ui.views.agents_view.widgets.sub_tab_button import SubTabButton
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon
from ankiforge.utils.logger import log_and_notify_error

logger = logging.getLogger(__name__)


class TemplateCard(QFrame):
    """Carte individuelle d'un modèle prédéfini dans la galerie."""

    def __init__(self, template: PersonaTemplate, on_select: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.template = template
        self.on_select = on_select
        self._is_selected = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(94)

        self._update_style()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        lbl_icon = QLabel()
        lbl_icon.setFixedSize(22, 22)
        lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_icon.setPixmap(load_phosphor_icon(template.icon, color=template.icon_color).pixmap(18, 18))
        lbl_icon.setStyleSheet("border: none; background: transparent;")
        top_row.addWidget(lbl_icon)

        lbl_name = QLabel(template.name)
        lbl_name.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12.5px; font-weight: bold; border: none; background: transparent;")
        top_row.addWidget(lbl_name, 1)

        badge_cat = Badge(template.category, variant="neutral")
        badge_cat.setFixedHeight(18)
        top_row.addWidget(badge_cat)

        layout.addLayout(top_row)

        lbl_desc = QLabel(template.description)
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; border: none; background: transparent;")
        layout.addWidget(lbl_desc, 1)

        bot_row = QHBoxLayout()
        bot_row.setSpacing(6)
        bot_row.addStretch()

        badge_scope = Badge(template.scope.upper(), variant="primary" if template.scope == "pipeline" else "warning")
        badge_scope.setFixedHeight(16)
        bot_row.addWidget(badge_scope)

        badge_fmt = Badge(template.output_format.upper(), variant="neutral")
        badge_fmt.setFixedHeight(16)
        bot_row.addWidget(badge_fmt)

        layout.addLayout(bot_row)

    def set_selected(self, selected: bool) -> None:
        self._is_selected = selected
        self._update_style()

    def _update_style(self) -> None:
        border_col = DesignTokens.ACCENT_PRIMARY if self._is_selected else DesignTokens.BORDER_COLOR
        bg_col = DesignTokens.BG_ACTIVE if self._is_selected else DesignTokens.BG_INPUT
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_col};
                border: 1px solid {border_col};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
            QFrame:hover {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)

    def mousePressEvent(self, event: Any) -> None:
        super().mousePressEvent(event)
        self.on_select(self.template)


class PersonaCreationWizardDialog(QDialog):
    """
    Assistant de création de Personas et Galerie de Modèles prêts à l'emploi.
    Offre un mode assisté (recommandé) et un mode création vierge personnalisée.
    """

    def __init__(
        self,
        cached_folders: list[PersonaFolderModel] | None = None,
        current_folder: PersonaFolderModel | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.cached_folders = cached_folders or []
        self.current_folder = current_folder
        self.created_persona: PersonaModel | None = None
        self._selected_template: PersonaTemplate = PERSONA_TEMPLATES[0]
        self._template_cards: list[tuple[TemplateCard, PersonaTemplate]] = []
        self._active_category: str = "all"

        self.setWindowTitle("Créer un Nouvel Agent IA — Galerie de Modèles")
        self.resize(920, 620)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {DesignTokens.BG_MAIN};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)

        self._setup_ui()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # En-tête avec onglets de sélection du mode
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        self.btn_mode_gallery = SubTabButton("✨ Modèles Prêts à l'Emploi", "ph.sparkle")
        self.btn_mode_custom = SubTabButton("➕ Agent Vierge Personnalisé", "ph.plus")

        self.btn_mode_gallery.clicked.connect(lambda: self._switch_mode(0))
        self.btn_mode_custom.clicked.connect(lambda: self._switch_mode(1))

        top_bar.addWidget(self.btn_mode_gallery)
        top_bar.addWidget(self.btn_mode_custom)
        top_bar.addStretch()

        main_layout.addLayout(top_bar)

        # Stack maître des modes
        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack, 1)

        # ── MODE 1 : GALERIE DE MODÈLES ──────────────────────────────────────
        self.page_gallery = QWidget()
        gallery_layout = QHBoxLayout(self.page_gallery)
        gallery_layout.setContentsMargins(0, 0, 0, 0)
        gallery_layout.setSpacing(10)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        gallery_layout.addWidget(splitter)

        # Panneau Gauche : Recherche + Filtres + Liste de cartes
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        self.edit_gallery_search = GlowLineEdit(placeholder="Rechercher un modèle (Wozniak, Langues, KaTeX, Médecine)...")
        self.edit_gallery_search.setFixedHeight(30)
        self.edit_gallery_search.textChanged.connect(self._apply_gallery_filters)
        left_layout.addWidget(self.edit_gallery_search)

        # Filtres de catégorie
        cat_row = QHBoxLayout()
        cat_row.setSpacing(4)
        self.cat_buttons: list[tuple[Any, str]] = []

        categories = [
            ("Tous", "all"),
            ("Pédagogie & SRS", "Pédagogie & SRS"),
            ("Langues", "Langues & Traduction"),
            ("Sciences", "Sciences & Médical"),
            ("Cloze", "Format Spécialisé"),
            ("Audit MCP", "Audit & MCP"),
        ]

        for label, cat_key in categories:
            btn = SecondaryButton(label)
            btn.setFixedHeight(24)
            btn.setCheckable(True)
            btn.clicked.connect(lambda _, c=cat_key: self._set_category_filter(c))
            cat_row.addWidget(btn)
            self.cat_buttons.append((btn, cat_key))

        cat_row.addStretch()
        self.cat_buttons[0][0].setChecked(True)
        left_layout.addLayout(cat_row)

        # Scroll des cartes
        cards_scroll = QScrollArea()
        cards_scroll.setWidgetResizable(True)
        cards_scroll.setFrameShape(QFrame.Shape.NoFrame)
        cards_scroll.setStyleSheet("background: transparent;")

        cards_container = QWidget()
        self.cards_vbox = QVBoxLayout(cards_container)
        self.cards_vbox.setContentsMargins(0, 0, 0, 0)
        self.cards_vbox.setSpacing(8)

        for tpl in PERSONA_TEMPLATES:
            card = TemplateCard(tpl, on_select=self._on_template_card_clicked)
            self._template_cards.append((card, tpl))
            self.cards_vbox.addWidget(card)

        self.cards_vbox.addStretch()
        cards_scroll.setWidget(cards_container)
        left_layout.addWidget(cards_scroll, 1)

        splitter.addWidget(left_panel)

        # Panneau Droit : Aperçu du modèle et configuration
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 0, 0, 0)
        right_layout.setSpacing(10)

        # Titre aperçu
        self.lbl_preview_title = QLabel(self._selected_template.name)
        self.lbl_preview_title.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        right_layout.addWidget(self.lbl_preview_title)

        # Champ Nom de l'agent (personnalisable)
        lbl_custom_name = QLabel("NOM DE VOTRE NOUVEL AGENT :")
        lbl_custom_name.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        right_layout.addWidget(lbl_custom_name)

        self.edit_template_agent_name = StyledLineEdit()
        self.edit_template_agent_name.setText(self._selected_template.name)
        right_layout.addWidget(self.edit_template_agent_name)

        # Dossier de destination
        lbl_dest_folder = QLabel("DOSSIER DE DESTINATION :")
        lbl_dest_folder.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        right_layout.addWidget(lbl_dest_folder)

        self.combo_gallery_folder = StyledComboBox()
        self._populate_folder_combo(self.combo_gallery_folder)
        right_layout.addWidget(self.combo_gallery_folder)

        # Aperçu du prompt système
        lbl_prompt_prev = QLabel("APERÇU DU PROMPT SYSTÈME (JINJA2) :")
        lbl_prompt_prev.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        right_layout.addWidget(lbl_prompt_prev)

        self.edit_prompt_preview = QPlainTextEdit()
        self.edit_prompt_preview.setReadOnly(True)
        self.edit_prompt_preview.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {DesignTokens.BG_INPUT};
                color: #a5b4fc;
                font-family: '{DesignTokens.FONT_CODE}';
                font-size: 11px;
                line-height: 1.4;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 8px;
            }}
        """)
        right_layout.addWidget(self.edit_prompt_preview, 1)

        # Bouton Créer depuis ce modèle
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_cancel_1 = SecondaryButton("Annuler")
        btn_cancel_1.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel_1)

        self.btn_create_from_template = PrimaryButton("✨ Créer cet Agent")
        self.btn_create_from_template.setIcon(load_phosphor_icon("ph.check", color="white"))
        self.btn_create_from_template.setFixedHeight(34)
        self.btn_create_from_template.clicked.connect(self._on_create_from_template)
        btn_row.addWidget(self.btn_create_from_template)

        right_layout.addLayout(btn_row)
        splitter.addWidget(right_panel)
        splitter.setSizes([460, 440])

        self.stack.addWidget(self.page_gallery)

        # ── MODE 2 : CRÉATION D'UN AGENT VIERGE ──────────────────────────────
        self.page_custom = QWidget()
        custom_layout = QVBoxLayout(self.page_custom)
        custom_layout.setContentsMargins(16, 16, 16, 16)
        custom_layout.setSpacing(12)

        lbl_custom_header = QLabel("Créer un Agent Personnalisé (Page Blanche)")
        lbl_custom_header.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        custom_layout.addWidget(lbl_custom_header)

        # Nom
        lbl_c_name = QLabel("NOM DE L'AGENT :")
        lbl_c_name.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        custom_layout.addWidget(lbl_c_name)
        self.edit_custom_name = StyledLineEdit()
        self.edit_custom_name.setPlaceholderText("ex: Mon Agent Spécialiste")
        custom_layout.addWidget(self.edit_custom_name)

        # Description
        lbl_c_desc = QLabel("DESCRIPTION & MISSION :")
        lbl_c_desc.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        custom_layout.addWidget(lbl_c_desc)
        self.edit_custom_desc = StyledLineEdit()
        self.edit_custom_desc.setPlaceholderText("ex: Extrait les définitions et cas pratiques du cours.")
        custom_layout.addWidget(self.edit_custom_desc)

        # Ligne Portée + Format + Dossier
        row_c_props = QHBoxLayout()
        row_c_props.setSpacing(10)

        col_scope = QVBoxLayout()
        lbl_s = QLabel("PORTÉE D'USAGE :")
        lbl_s.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold;")
        col_scope.addWidget(lbl_s)
        self.combo_custom_scope = StyledComboBox()
        for s_key, s_spec in PERSONA_TYPE_SPECS.items():
            self.combo_custom_scope.addItem(s_spec["label"], userData=s_key)
        col_scope.addWidget(self.combo_custom_scope)
        row_c_props.addLayout(col_scope, 1)

        col_fmt = QVBoxLayout()
        lbl_f = QLabel("FORMAT DE SORTIE :")
        lbl_f.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold;")
        col_fmt.addWidget(lbl_f)
        self.combo_custom_format = StyledComboBox()
        self.combo_custom_format.addItems(["json", "cloze", "markdown", "text"])
        col_fmt.addWidget(self.combo_custom_format)
        row_c_props.addLayout(col_fmt, 1)

        col_folder = QVBoxLayout()
        lbl_fol = QLabel("DOSSIER :")
        lbl_fol.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold;")
        col_folder.addWidget(lbl_fol)
        self.combo_custom_folder = StyledComboBox()
        self._populate_folder_combo(self.combo_custom_folder)
        col_folder.addWidget(self.combo_custom_folder)
        row_c_props.addLayout(col_folder, 1)

        custom_layout.addLayout(row_c_props)

        # Prompt
        lbl_c_prompt = QLabel("PROMPT SYSTÈME INITIAL :")
        lbl_c_prompt.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold;")
        custom_layout.addWidget(lbl_c_prompt)
        self.edit_custom_prompt = QPlainTextEdit()
        self.edit_custom_prompt.setPlaceholderText("Tu es un assistant expert pour Anki...\nUtilisez {{ text_source }}.")
        self.edit_custom_prompt.setPlainText("Tu es un assistant expert pour Anki.\n\n### Mission :\n{{ text_source }}")
        self.edit_custom_prompt.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_PRIMARY};
                font-family: '{DesignTokens.FONT_CODE}';
                font-size: 11.5px;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 8px;
            }}
        """)
        custom_layout.addWidget(self.edit_custom_prompt, 1)

        # Boutons d'action
        btn_c_row = QHBoxLayout()
        btn_c_row.addStretch()

        btn_cancel_2 = SecondaryButton("Annuler")
        btn_cancel_2.clicked.connect(self.reject)
        btn_c_row.addWidget(btn_cancel_2)

        self.btn_create_custom = PrimaryButton("Créer l'Agent Vierge")
        self.btn_create_custom.setIcon(load_phosphor_icon("ph.check", color="white"))
        self.btn_create_custom.setFixedHeight(34)
        self.btn_create_custom.clicked.connect(self._on_create_custom_persona)
        btn_c_row.addWidget(self.btn_create_custom)

        custom_layout.addLayout(btn_c_row)
        self.stack.addWidget(self.page_custom)

        self._switch_mode(0)
        self._on_template_card_clicked(self._selected_template)

    def _switch_mode(self, idx: int) -> None:
        self.btn_mode_gallery.set_active(idx == 0)
        self.btn_mode_custom.set_active(idx == 1)
        self.stack.setCurrentIndex(idx)

    def _populate_folder_combo(self, combo: StyledComboBox) -> None:
        combo.clear()
        combo.addItem("📁 Racine (Sans dossier)", userData=None)

        def _add_recursive(parent_id: int | None, prefix: str = "") -> None:
            children = [f for f in self.cached_folders if (f.parent.id if f.parent else None) == parent_id]
            for ch in children:
                combo.addItem(f"{prefix}📁 {ch.name}", userData=ch.id)
                _add_recursive(ch.id, prefix + "   ")

        _add_recursive(None)

        if self.current_folder:
            idx = combo.findData(self.current_folder.id)
            if idx != -1:
                combo.setCurrentIndex(idx)

    def _set_category_filter(self, category: str) -> None:
        self._active_category = category
        for btn, cat_key in self.cat_buttons:
            btn.setChecked(cat_key == category)
        self._apply_gallery_filters()

    def _apply_gallery_filters(self) -> None:
        q = self.edit_gallery_search.text().strip().lower()
        active_cat = self._active_category

        for card, tpl in self._template_cards:
            match_cat = active_cat == "all" or tpl.category == active_cat
            match_q = not q or (q in tpl.name.lower() or q in tpl.description.lower() or q in tpl.category.lower())
            card.setVisible(match_cat and match_q)

    def _on_template_card_clicked(self, tpl: PersonaTemplate) -> None:
        self._selected_template = tpl
        for card, card_tpl in self._template_cards:
            card.set_selected(card_tpl.id == tpl.id)

        self.lbl_preview_title.setText(tpl.name)
        self.edit_template_agent_name.setText(tpl.name.split(" ", 1)[-1] if " " in tpl.name else tpl.name)
        self.edit_prompt_preview.setPlainText(tpl.system_prompt)

    def _on_create_from_template(self) -> None:
        tpl = self._selected_template
        agent_name = self.edit_template_agent_name.text().strip()
        if not agent_name:
            show_toast(self, "Veuillez renseigner un nom pour votre agent.", is_error=True)
            return

        folder_id = self.combo_gallery_folder.currentData()
        try:
            with db.atomic():
                new_p = PersonaModel.create(
                    name=agent_name,
                    description=tpl.description,
                    system_prompt=tpl.system_prompt,
                    output_format=tpl.output_format,
                    persona_type=tpl.scope,
                    folder=folder_id,
                    allowed_tools=json.dumps(tpl.recommended_tools),
                )
                PersonaVersionService.create_snapshot(
                    new_p,
                    commit_message=f"Création initiale depuis le modèle '{tpl.name}'",
                )

            self.created_persona = new_p
            show_toast(self, f"Agent '{agent_name}' créé avec succès !")
            self.accept()
        except Exception as e:
            log_and_notify_error(e, context="Création d'agent depuis modèle", parent=self, title="Erreur de création")

    def _on_create_custom_persona(self) -> None:
        name = self.edit_custom_name.text().strip()
        if not name:
            show_toast(self, "Le nom de l'agent ne peut pas être vide.", is_error=True)
            return

        desc = self.edit_custom_desc.text().strip()
        scope = self.combo_custom_scope.currentData() or "pipeline"
        fmt = self.combo_custom_format.currentText().lower()
        folder_id = self.combo_custom_folder.currentData()
        prompt = self.edit_custom_prompt.toPlainText().strip()

        try:
            with db.atomic():
                new_p = PersonaModel.create(
                    name=name,
                    description=desc or "Agent IA personnalisé.",
                    system_prompt=prompt,
                    output_format=fmt,
                    persona_type=scope,
                    folder=folder_id,
                    allowed_tools="[]",
                )
                PersonaVersionService.create_snapshot(
                    new_p,
                    commit_message=f"Création initiale de l'agent personnalisé '{name}'",
                )

            self.created_persona = new_p
            show_toast(self, f"Agent '{name}' créé avec succès !")
            self.accept()
        except Exception as e:
            log_and_notify_error(e, context="Création d'agent vierge", parent=self, title="Erreur de création")
