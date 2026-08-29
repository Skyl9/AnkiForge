from typing import Any

from jinja2 import BaseLoader, Environment
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import LLMConfigModel, PersonaModel
from ankiforge.services.tools.tool_service import ToolService
from ankiforge.ui.components import (
    Badge,
    FlowWidget,
    SecondaryButton,
    StyledComboBox,
    StyledLineEdit,
    StyledTextEdit,
)
from ankiforge.ui.dialogs.tool_editor_dialog import ToolEditorDialog
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.views.pipelines_view.constants import (
    STEP_TYPES_META,
    apply_pill_style,
)
from ankiforge.ui.views.pipelines_view.widgets.common import (
    SubTabButton,
    TagPillButton,
)
from ankiforge.ui.views.pipelines_view.widgets.step_picker import PersonaSelectorDialog
from ankiforge.utils.icon_loader import load_phosphor_icon


class PersonaIdentityCard(QFrame):
    """Carte d'identité stylée et enrichie du Persona IA dans l'Inspecteur."""

    change_persona_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            PersonaIdentityCard {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
            PersonaIdentityCard QLabel {{
                background: transparent;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        # Header Row
        h_row = QHBoxLayout()
        h_row.setSpacing(8)
        self.lbl_persona_icon = QLabel()
        self.lbl_persona_icon.setFixedSize(18, 18)
        self.lbl_persona_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_persona_icon.setPixmap(load_phosphor_icon("ph.sparkle", color="#8b5cf6").pixmap(16, 16))
        h_row.addWidget(self.lbl_persona_icon, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.lbl_title = QLabel("<b>Agent : Non défini</b>")
        self.lbl_title.setStyleSheet(f"font-size: 12.5px; color: {DesignTokens.TEXT_PRIMARY};")
        h_row.addWidget(self.lbl_title, 1, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.badge_role = Badge("Agent IA", variant="status")
        apply_pill_style(self.badge_role, "#8b5cf6")
        self.badge_role.setFixedHeight(18)
        h_row.addWidget(self.badge_role, alignment=Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(h_row)

        # Description / System Prompt preview
        self.lbl_desc = QLabel("Prompt système...")
        self.lbl_desc.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_MUTED}; font-style: italic;")
        self.lbl_desc.setWordWrap(True)
        layout.addWidget(self.lbl_desc)

        # Action button
        b_row = QHBoxLayout()
        self.btn_switch = SecondaryButton("Changer d'Agent...")
        self.btn_switch.setIcon(load_phosphor_icon("ph.arrows-clockwise", color=DesignTokens.TEXT_PRIMARY))
        self.btn_switch.setIconSize(QSize(14, 14))
        self.btn_switch.setFixedHeight(28)
        self.btn_switch.clicked.connect(self.change_persona_requested.emit)
        b_row.addWidget(self.btn_switch)
        b_row.addStretch()
        layout.addLayout(b_row)

    def set_persona(self, persona: PersonaModel | None) -> None:
        if persona:
            self.lbl_title.setText(f"<b>Agent : {persona.name}</b>")
            desc = persona.system_prompt.strip().replace("\n", " ") if persona.system_prompt else "Agent IA spécialisé."
            if len(desc) > 95:
                desc = desc[:92] + "..."
            self.lbl_desc.setText(f"« {desc} »")
            self.badge_role.setText("Agent IA")
            apply_pill_style(self.badge_role, "#8b5cf6")
        else:
            self.lbl_title.setText("<b>Aucun Agent IA (Prompt Pur)</b>")
            self.lbl_desc.setText("L'étape s'exécutera avec le prompt personnalisé ci-dessous sans persona de base.")
            self.badge_role.setText("Prompt Pur")
            apply_pill_style(self.badge_role, "#64748b")


class PromptPreviewDialog(QDialog):
    """Affiche la résolution dynamique du template Jinja2 avec des données échantillons réalistes."""

    def __init__(self, template_str: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Aperçu du Prompt Interpolé (Jinja2)")
        self.resize(700, 500)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {DesignTokens.BG_MAIN};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QDialog QLabel {{
                background: transparent;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        row_header = QHBoxLayout()
        row_header.setSpacing(8)
        icon_eye = QLabel()
        icon_eye.setFixedSize(18, 18)
        icon_eye.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_eye.setPixmap(load_phosphor_icon("ph.eye", color=DesignTokens.ACCENT_PRIMARY).pixmap(16, 16))
        row_header.addWidget(icon_eye)

        lbl_header = QLabel("Ce que recevra l'Agent IA (variables résolues) :")
        lbl_header.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        row_header.addWidget(lbl_header)
        row_header.addStretch()
        layout.addLayout(row_header)

        rendered_text = ""
        try:
            env = Environment(loader=BaseLoader(), autoescape=False)  # nosec B701
            tpl = env.from_string(template_str)
            mock_state = {
                "initial_prompt": "Créer 5 flashcards sur la diagonalisation matricielle.",
                "variables": {
                    "text_source": "Soit A une matrice carrée n x n. A est diagonalisable s'il existe une base de vecteurs propres.",
                    "generated_cards": [{"Front": "Définition diagonalisation", "Back": "Existe base de vecteurs propres"}],
                    "last_output": "Cartes générées avec succès.",
                    "plan_cours": "1. Définition\n2. Valeurs propres\n3. Sous-espaces propres",
                },
            }
            rendered_text = tpl.render(state=mock_state)
        except Exception as e:
            rendered_text = f"❌ Erreur de syntaxe Jinja2 dans le template :\n{e}"

        edit_rendered = QPlainTextEdit()
        edit_rendered.setReadOnly(True)
        edit_rendered.setPlainText(rendered_text)
        edit_rendered.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                color: #38bdf8;
                font-family: monospace;
                font-size: 12px;
                line-height: 1.4;
                padding: 10px;
                border-radius: 6px;
            }}
        """)
        layout.addWidget(edit_rendered, 1)

        btn_close = SecondaryButton("Fermer l'aperçu")
        btn_close.setIcon(load_phosphor_icon("ph.check-circle", color=DesignTokens.TEXT_PRIMARY))
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)


class StepInspectorPanel(QFrame):
    """Volet droit d'inspection et de réglages fins de l'étape sélectionnée avec assistance Jinja2."""

    step_updated = Signal()
    test_step_requested = Signal(dict)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.step_data: dict[str, Any] | None = None
        self.step_order: int = 1
        self.total_steps: int = 1
        self.available_personas: list[PersonaModel] = []
        self.available_llms: list[LLMConfigModel] = []

        self.setObjectName("StepInspector")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            QFrame#StepInspector {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
            QFrame#StepInspector QLabel {{
                background: transparent;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        # ── 1. En-tête de l'Inspecteur ──────────────────────────────────────────
        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)

        self.lbl_step_icon = QLabel()
        self.lbl_step_icon.setFixedSize(22, 22)
        self.lbl_step_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(self.lbl_step_icon, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.edit_step_title = StyledLineEdit(placeholder="Nom personnalisé de l'étape...")
        self.edit_step_title.setFixedHeight(30)
        self.edit_step_title.setStyleSheet("font-weight: bold; font-size: 13px;")
        self.edit_step_title.textChanged.connect(self._on_title_changed)
        header_layout.addWidget(self.edit_step_title, 1, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.role_badge = Badge("LLM", variant="status")
        apply_pill_style(self.role_badge, "#8b5cf6")
        self.role_badge.setFixedHeight(20)
        header_layout.addWidget(self.role_badge, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.btn_test_step = SecondaryButton("Tester l'étape")
        self.btn_test_step.setIcon(load_phosphor_icon("ph.flask", color=DesignTokens.TEXT_PRIMARY))
        self.btn_test_step.setIconSize(QSize(14, 14))
        self.btn_test_step.setFixedHeight(30)
        self.btn_test_step.clicked.connect(self._on_test_step_clicked)
        header_layout.addWidget(self.btn_test_step, alignment=Qt.AlignmentFlag.AlignVCenter)

        layout.addLayout(header_layout)

        # ── 2. Barre de Sous-Onglets Style IDE ──────────────────────────────────
        subtabs_bar = QHBoxLayout()
        subtabs_bar.setSpacing(4)
        subtabs_bar.setContentsMargins(0, 0, 0, 0)

        self.btn_subtab_params = SubTabButton("Paramètres && Prompt", "ph.gear", is_active=True)
        self.btn_subtab_params.clicked.connect(lambda: self._switch_subtab(0))
        subtabs_bar.addWidget(self.btn_subtab_params)

        self.btn_subtab_dag = SubTabButton("Transitions DAG && Erreurs", "ph.git-branch", is_active=False)
        self.btn_subtab_dag.clicked.connect(lambda: self._switch_subtab(1))
        subtabs_bar.addWidget(self.btn_subtab_dag)

        subtabs_bar.addStretch()
        layout.addLayout(subtabs_bar)

        # ── 3. Contenu des Sous-Onglets (QStackedWidget) ────────────────────────
        self.tabs = QStackedWidget()

        self.tab_params = QWidget()
        layout_tab_params = QVBoxLayout(self.tab_params)
        layout_tab_params.setContentsMargins(0, 0, 0, 0)
        layout_tab_params.setSpacing(0)

        self.params_scroll = QScrollArea()
        self.params_scroll.setWidgetResizable(True)
        self.params_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.params_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.params_scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{ background: {DesignTokens.BG_INPUT}; width: 6px; border-radius: 3px; }}
            QScrollBar::handle:vertical {{ background: {DesignTokens.BORDER_COLOR}; border-radius: 3px; min-height: 20px; }}
        """)
        layout_tab_params.addWidget(self.params_scroll)
        self.tabs.addWidget(self.tab_params)

        self.tab_dag = QWidget()
        self.layout_dag = QVBoxLayout(self.tab_dag)
        self.layout_dag.setContentsMargins(0, 4, 0, 0)
        self.layout_dag.setSpacing(10)
        self.tabs.addWidget(self.tab_dag)

        self._setup_dag_tab()
        layout.addWidget(self.tabs, 1)

    def _switch_subtab(self, index: int) -> None:
        self.tabs.setCurrentIndex(index)
        self.btn_subtab_params.set_active(index == 0)
        self.btn_subtab_dag.set_active(index == 1)

    def _setup_dag_tab(self) -> None:
        """Construit le contenu de l'onglet Transitions DAG avec des cartes élégantes."""
        while self.layout_dag.count():
            item = self.layout_dag.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        # Carte 1 : Transition de Succès
        card_succ = QFrame()
        card_succ.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        card_succ.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
            QFrame QLabel {{
                background: transparent;
            }}
        """)
        layout_succ = QVBoxLayout(card_succ)
        layout_succ.setContentsMargins(12, 10, 12, 10)
        layout_succ.setSpacing(6)

        lbl_succ_title = QLabel("✅ TRANSITION DE SUCCÈS")
        lbl_succ_title.setStyleSheet(f"color: {DesignTokens.COLOR_GREEN}; font-size: 11px; font-weight: bold;")
        layout_succ.addWidget(lbl_succ_title)

        lbl_succ = QLabel("Étape suivante à exécuter :")
        lbl_succ.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        layout_succ.addWidget(lbl_succ)

        self.combo_succ = StyledComboBox()
        self.combo_succ.currentIndexChanged.connect(self._on_branching_changed)
        layout_succ.addWidget(self.combo_succ)
        self.layout_dag.addWidget(card_succ)

        # Carte 2 : Gestion des Erreurs & Repli
        card_fail = QFrame()
        card_fail.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        card_fail.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
            QFrame QLabel {{
                background: transparent;
            }}
        """)
        layout_fail = QVBoxLayout(card_fail)
        layout_fail.setContentsMargins(12, 10, 12, 10)
        layout_fail.setSpacing(6)

        lbl_fail_title = QLabel("⚠️ EN CAS D'ERREUR OU ÉCHEC")
        lbl_fail_title.setStyleSheet("color: #f59e0b; font-size: 11px; font-weight: bold;")
        layout_fail.addWidget(lbl_fail_title)

        lbl_fail_beh = QLabel("Comportement d'interruption :")
        lbl_fail_beh.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        layout_fail.addWidget(lbl_fail_beh)

        self.combo_fail_beh = StyledComboBox()
        self.combo_fail_beh.addItem("🛑 Arrêter le pipeline (stop)", userData="stop")
        self.combo_fail_beh.addItem("⏭️ Continuer malgré l'erreur (continue)", userData="continue")
        self.combo_fail_beh.addItem("🔀 Sauter vers une étape de secours", userData="goto_failure_step")
        self.combo_fail_beh.currentIndexChanged.connect(self._on_fail_beh_changed)
        layout_fail.addWidget(self.combo_fail_beh)

        self.lbl_fail_target = QLabel("Étape de Secours :")
        self.lbl_fail_target.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; margin-top: 4px;")
        layout_fail.addWidget(self.lbl_fail_target)

        self.combo_fail_target = StyledComboBox()
        self.combo_fail_target.currentIndexChanged.connect(self._on_branching_changed)
        layout_fail.addWidget(self.combo_fail_target)

        self.layout_dag.addWidget(card_fail)
        self.layout_dag.addStretch()

    def inspect_step(
        self,
        step_data: dict[str, Any],
        step_order: int,
        total_steps: int,
        personas: list[PersonaModel],
        llms: list[LLMConfigModel],
    ) -> None:
        """Charge et affiche les données de l'étape sélectionnée."""
        self.step_data = step_data
        self.step_order = step_order
        self.total_steps = total_steps
        self.available_personas = personas
        self.available_llms = llms

        step_type = step_data.get("type", "LLM_PROMPT")
        meta = STEP_TYPES_META.get(step_type, STEP_TYPES_META["LLM_PROMPT"])

        self.lbl_step_icon.setPixmap(load_phosphor_icon(meta["icon"], color=meta["badge_color"]).pixmap(18, 18))
        persona = step_data.get("persona")
        custom_t = step_data.get("custom_title") or (persona.name if persona else meta["default_title"])
        self.edit_step_title.blockSignals(True)
        self.edit_step_title.setText(custom_t)
        self.edit_step_title.blockSignals(False)

        self.role_badge.setText(meta["badge"])
        apply_pill_style(self.role_badge, meta["badge_color"])

        self._build_params_form(step_type)
        self._update_dag_controls()

    def _build_params_form(self, step_type: str) -> None:
        """Génère le formulaire spécifique au type d'étape avec assistance de chips Jinja2 et aperçu."""
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        layout_params = QVBoxLayout(container)
        layout_params.setContentsMargins(4, 4, 4, 4)
        layout_params.setSpacing(12)

        if not self.step_data:
            self.params_scroll.setWidget(container)
            return

        cfg = self.step_data.get("config", {})
        meta = STEP_TYPES_META.get(step_type, STEP_TYPES_META["LLM_PROMPT"])

        if step_type in ("LLM_PROMPT", "MAP_REDUCE"):
            p_card = PersonaIdentityCard()
            cur_persona = self.step_data.get("persona")
            p_card.set_persona(cur_persona)

            def _handle_change_persona() -> None:
                cur_p = self.step_data.get("persona") if self.step_data else None
                dlg = PersonaSelectorDialog(personas=self.available_personas, current_persona=cur_p, parent=self)
                if dlg.exec() == QDialog.DialogCode.Accepted:
                    new_p = dlg.selected_persona
                    self._on_param_changed("persona", new_p)
                    p_card.set_persona(new_p)
                    if new_p and self.step_data and not self.step_data.get("custom_title"):
                        self.edit_step_title.setText(str(new_p.name))

            p_card.change_persona_requested.connect(_handle_change_persona)
            layout_params.addWidget(p_card)

            # Surcharge LLM
            row_llm = QHBoxLayout()
            lbl_m = QLabel("Modèle LLM dédié :")
            lbl_m.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
            combo_llm = StyledComboBox()
            combo_llm.addItem("Modèle par défaut du profil", userData=None)
            sel_llm_idx = 0
            cur_llm_id = cfg.get("llm_config_id")
            for i, m in enumerate(self.available_llms, start=1):
                name = getattr(m, "display_name", None) or getattr(m, "model_id", "Modèle")
                pricing_tag = "Gratuit" if getattr(m, "is_free", False) else f"{getattr(m, 'prompt_pricing', 0):.1f}$/1M"
                combo_llm.addItem(f"{name} ({m.provider} · {pricing_tag})", userData=m.id)
                if cur_llm_id == m.id:
                    sel_llm_idx = i
            combo_llm.setCurrentIndex(sel_llm_idx)
            combo_llm.currentIndexChanged.connect(lambda: self._on_config_changed("llm_config_id", combo_llm.currentData()))
            row_llm.addWidget(lbl_m)
            row_llm.addWidget(combo_llm, 1)
            layout_params.addLayout(row_llm)

            if step_type == "MAP_REDUCE":
                row_mr = QHBoxLayout()
                lbl_batch = QLabel("Taille des lots :")
                lbl_batch.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
                spin_batch = QSpinBox()
                spin_batch.setRange(1, 10)
                spin_batch.setValue(int(cfg.get("batch_size", 3)))
                spin_batch.setFixedHeight(30)
                spin_batch.setStyleSheet(
                    f"background: {DesignTokens.BG_INPUT}; color: {DesignTokens.TEXT_PRIMARY}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 4px; padding: 2px 6px;"
                )
                spin_batch.valueChanged.connect(lambda v: self._on_config_changed("batch_size", v))
                row_mr.addWidget(lbl_batch)
                row_mr.addWidget(spin_batch)

                lbl_mode = QLabel("Découpage :")
                lbl_mode.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold; margin-left: 10px;")
                combo_mode = StyledComboBox()
                combo_mode.addItem("📄 Par Page (PDF)", userData="page")
                combo_mode.addItem("📑 Par Section / Chapitre", userData="chapter")
                combo_mode.addItem("📦 Par Lots de Paragraphes", userData="paragraphs")
                combo_mode.currentIndexChanged.connect(lambda: self._on_config_changed("split_mode", combo_mode.currentData()))
                row_mr.addWidget(lbl_mode)
                row_mr.addWidget(combo_mode, 1)
                layout_params.addLayout(row_mr)

            vars_row = QHBoxLayout()
            vars_row.setSpacing(10)

            col_in = QVBoxLayout()
            col_in.setSpacing(4)
            lbl_in = QLabel("Variable d'entrée :")
            lbl_in.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
            edit_in = StyledLineEdit(placeholder="ex: text_source")
            edit_in.setText(cfg.get("input_variable", meta.get("default_input", "text_source")))
            edit_in.setFixedHeight(30)
            edit_in.setStyleSheet(f"font-family: '{DesignTokens.FONT_CODE}'; font-size: 11px;")
            edit_in.textChanged.connect(lambda t: self._on_config_changed("input_variable", t))
            col_in.addWidget(lbl_in)
            col_in.addWidget(edit_in)
            vars_row.addLayout(col_in, 1)

            col_out = QVBoxLayout()
            col_out.setSpacing(4)
            lbl_out = QLabel("Variable de sortie :")
            lbl_out.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
            edit_out = StyledLineEdit(placeholder="ex: generated_cards")
            edit_out.setText(cfg.get("output_variable", meta.get("default_output", "generated_cards")))
            edit_out.setFixedHeight(30)
            edit_out.setStyleSheet(f"font-family: '{DesignTokens.FONT_CODE}'; font-size: 11px;")
            edit_out.textChanged.connect(lambda t: self._on_config_changed("output_variable", t))
            col_out.addWidget(lbl_out)
            col_out.addWidget(edit_out)
            vars_row.addLayout(col_out, 1)

            col_fmt = QVBoxLayout()
            col_fmt.setSpacing(4)
            lbl_fmt = QLabel("Format de sortie :")
            lbl_fmt.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
            combo_fmt = StyledComboBox()
            combo_fmt.addItem("JSON Strict (Cartes)", userData="json")
            combo_fmt.addItem("Markdown / Texte", userData="text")
            cur_fmt = cfg.get("output_format", "json")
            combo_fmt.setCurrentIndex(0 if cur_fmt == "json" else 1)
            combo_fmt.currentIndexChanged.connect(lambda: self._on_config_changed("output_format", combo_fmt.currentData()))
            col_fmt.addWidget(lbl_fmt)
            col_fmt.addWidget(combo_fmt)
            vars_row.addLayout(col_fmt, 1)

            layout_params.addLayout(vars_row)

            row_prompt_header = QHBoxLayout()
            lbl_prompt = QLabel("Surcharge Prompt Système / Template Jinja2 :")
            lbl_prompt.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
            row_prompt_header.addWidget(lbl_prompt)
            row_prompt_header.addStretch()

            btn_preview_prompt = SecondaryButton("Aperçu Prompt")
            btn_preview_prompt.setIcon(load_phosphor_icon("ph.eye", color=DesignTokens.TEXT_PRIMARY))
            btn_preview_prompt.setIconSize(QSize(14, 14))
            btn_preview_prompt.setFixedHeight(26)
            row_prompt_header.addWidget(btn_preview_prompt)
            layout_params.addLayout(row_prompt_header)

            edit_prompt = StyledTextEdit()
            edit_prompt.setPlaceholderText("Laisser vide pour utiliser le prompt par défaut du Persona...")
            edit_prompt.setPlainText(cfg.get("prompt_override", ""))
            edit_prompt.setMinimumHeight(150)
            edit_prompt.setStyleSheet(f"""
                QPlainTextEdit {{
                    background: {DesignTokens.BG_INPUT};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    color: {DesignTokens.TEXT_PRIMARY};
                    font-family: '{DesignTokens.FONT_CODE}';
                    font-size: 12px;
                    border-radius: 4px;
                    padding: 8px;
                }}
            """)
            edit_prompt.textChanged.connect(lambda: self._on_config_changed("prompt_override", edit_prompt.toPlainText()))

            btn_preview_prompt.clicked.connect(lambda: PromptPreviewDialog(edit_prompt.toPlainText(), parent=self).exec())

            chips_flow = FlowWidget(margin=0, h_spacing=6, v_spacing=6)
            jinja_chips = [
                ("text_source", "{{ state.variables.text_source }}", "Contenu source ou contexte RAG", "field"),
                ("generated_cards", "{{ state.variables.generated_cards }}", "Flashcards générées par les étapes précédentes", "cloze"),
                ("initial_prompt", "{{ state.initial_prompt }}", "Requête initiale soumise par l'utilisateur", "info"),
                ("last_output", "{{ state.variables.last_output }}", "Dernier résultat produit", "warning"),
                ("plan_cours", "{{ state.variables.plan_cours }}", "Plan de cours validé", "success"),
            ]

            for label, tag, tip, var_style in jinja_chips:
                chip_btn = TagPillButton(f"+ {label}", tag, tooltip=tip, variant=var_style)

                def _make_insert(t: str) -> Any:
                    return lambda: (edit_prompt.textCursor().insertText(t), edit_prompt.setFocus())

                chip_btn.clicked.connect(_make_insert(tag))
                chips_flow.addWidget(chip_btn)

            layout_params.addWidget(chips_flow)
            layout_params.addWidget(edit_prompt)

        elif step_type == "RAG_RETRIEVAL":
            row_rag = QHBoxLayout()
            lbl_topk = QLabel("Nombre de fragments (Top-K) :")
            lbl_topk.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
            spin_topk = QSpinBox()
            spin_topk.setRange(1, 20)
            spin_topk.setValue(int(cfg.get("top_k", 5)))
            spin_topk.setFixedHeight(30)
            spin_topk.setStyleSheet(f"background: {DesignTokens.BG_INPUT}; color: {DesignTokens.TEXT_PRIMARY}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 4px; padding: 2px 6px;")
            spin_topk.valueChanged.connect(lambda v: self._on_config_changed("top_k", v))
            row_rag.addWidget(lbl_topk)
            row_rag.addWidget(spin_topk)
            row_rag.addStretch()
            layout_params.addLayout(row_rag)

            lbl_query = QLabel("Template de Requête Sémantique (Jinja2) :")
            lbl_query.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold; margin-top: 4px;")
            layout_params.addWidget(lbl_query)

            edit_query = StyledLineEdit(icon_name="ph.magnifying-glass", placeholder="{{ state.initial_prompt }}")
            edit_query.setText(cfg.get("rag_query_template", "{{ state.initial_prompt }}"))
            edit_query.setFixedHeight(30)
            edit_query.setStyleSheet(f"font-family: '{DesignTokens.FONT_CODE}'; font-size: 11px;")
            edit_query.textChanged.connect(lambda t: self._on_config_changed("rag_query_template", t))
            layout_params.addWidget(edit_query)
            layout_params.addStretch()

        elif step_type == "HUMAN_VALIDATION":
            lbl_ht = QLabel("Titre de l'Interruption Humaine :")
            lbl_ht.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
            layout_params.addWidget(lbl_ht)

            edit_ht = StyledLineEdit(icon_name="ph.hand-palm", placeholder="Validation du Plan de Cours")
            edit_ht.setText(cfg.get("human_title", "Validation du Plan de Cours"))
            edit_ht.setFixedHeight(30)
            edit_ht.textChanged.connect(lambda t: self._on_config_changed("human_title", t))
            layout_params.addWidget(edit_ht)

            lbl_hm = QLabel("Message d'Instructions :")
            lbl_hm.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold; margin-top: 4px;")
            layout_params.addWidget(lbl_hm)

            edit_hm = StyledTextEdit()
            edit_hm.setPlainText(cfg.get("human_message", "Veuillez vérifier et ajuster les sections avant de forger les cartes."))
            edit_hm.setMinimumHeight(140)
            edit_hm.textChanged.connect(lambda: self._on_config_changed("human_message", edit_hm.toPlainText()))
            layout_params.addWidget(edit_hm)

        elif step_type == "PYTHON_TOOL":
            row_sel = QHBoxLayout()
            lbl_tool = QLabel("Outil Python Déterministe :")
            lbl_tool.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
            row_sel.addWidget(lbl_tool)

            btn_new_tool = SecondaryButton("Nouvel Outil")
            btn_new_tool.setIcon(load_phosphor_icon("ph.plus", color=DesignTokens.TEXT_PRIMARY))
            btn_new_tool.setIconSize(QSize(14, 14))
            btn_new_tool.setFixedHeight(28)
            row_sel.addWidget(btn_new_tool)
            row_sel.addStretch()
            layout_params.addLayout(row_sel)

            combo_tool = StyledComboBox()
            tools_list = ToolService.list_tools()
            cur_tool_name = cfg.get("tool_name", "clean_html_latex")
            sel_tool_idx = 0
            for idx, t in enumerate(tools_list):
                tag = " (Natif)" if t.is_builtin else " (Custom)"
                combo_tool.addItem(f"{t.display_name}{tag}", userData=t.name)
                if t.name == cur_tool_name:
                    sel_tool_idx = idx
            combo_tool.setCurrentIndex(sel_tool_idx)
            combo_tool.currentIndexChanged.connect(lambda: self._on_config_changed("tool_name", combo_tool.currentData()))
            layout_params.addWidget(combo_tool)

            row_tool_actions = QHBoxLayout()
            btn_edit_code = SecondaryButton("Voir / Modifier le Script")
            btn_edit_code.setIcon(load_phosphor_icon("ph.pencil-simple", color=DesignTokens.TEXT_PRIMARY))
            btn_edit_code.setIconSize(QSize(14, 14))
            btn_edit_code.setFixedHeight(28)

            def _open_editor() -> None:
                sel_name = combo_tool.currentData()
                tool_obj = ToolService.get_tool(sel_name)
                dlg = ToolEditorDialog(tool_obj, parent=self)
                if dlg.exec() == QDialog.DialogCode.Accepted:
                    self._build_params_form("PYTHON_TOOL")

            def _create_new() -> None:
                dlg = ToolEditorDialog(None, parent=self)
                if dlg.exec() == QDialog.DialogCode.Accepted:
                    self._build_params_form("PYTHON_TOOL")

            btn_new_tool.clicked.connect(_create_new)
            btn_edit_code.clicked.connect(_open_editor)
            row_tool_actions.addWidget(btn_edit_code)
            row_tool_actions.addStretch()
            layout_params.addLayout(row_tool_actions)

            lbl_out = QLabel("Variable de sortie du résultat :")
            lbl_out.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold; margin-top: 4px;")
            layout_params.addWidget(lbl_out)

            edit_out = StyledLineEdit(placeholder="tool_result")
            edit_out.setText(cfg.get("output_variable", "tool_result"))
            edit_out.setFixedHeight(30)
            edit_out.setStyleSheet(f"font-family: '{DesignTokens.FONT_CODE}'; font-size: 11px;")
            edit_out.textChanged.connect(lambda t: self._on_config_changed("output_variable", t))
            layout_params.addWidget(edit_out)
            layout_params.addStretch()

        self.params_scroll.setWidget(container)

    def _update_dag_controls(self) -> None:
        """Met à jour les combos de transitions DAG."""
        if not self.step_data:
            return

        # Succès
        self.combo_succ.blockSignals(True)
        self.combo_succ.clear()
        self.combo_succ.addItem("➡️ Étape suivante par défaut (séquentiel)", userData=None)
        current_succ = self.step_data.get("on_success_order")
        sel_succ_idx = 0
        for num in range(1, self.total_steps + 1):
            if num != self.step_order:
                self.combo_succ.addItem(f"↳ Sauter vers Étape {num}", userData=num)
                if current_succ == num:
                    sel_succ_idx = self.combo_succ.count() - 1
        self.combo_succ.setCurrentIndex(sel_succ_idx)
        self.combo_succ.blockSignals(False)

        # Comportement d'échec
        self.combo_fail_beh.blockSignals(True)
        fail_beh = self.step_data.get("failure_behavior", "stop")
        if fail_beh == "continue":
            self.combo_fail_beh.setCurrentIndex(1)
        elif fail_beh == "goto_failure_step":
            self.combo_fail_beh.setCurrentIndex(2)
        else:
            self.combo_fail_beh.setCurrentIndex(0)
        self.combo_fail_beh.blockSignals(False)

        # Cible d'échec
        self.combo_fail_target.blockSignals(True)
        self.combo_fail_target.clear()
        self.combo_fail_target.addItem("Aucune étape de secours", userData=None)
        current_fail = self.step_data.get("on_failure_order")
        sel_fail_idx = 0
        for num in range(1, self.total_steps + 1):
            if num != self.step_order:
                self.combo_fail_target.addItem(f"↳ Sauter vers Étape {num}", userData=num)
                if current_fail == num:
                    sel_fail_idx = self.combo_fail_target.count() - 1
        self.combo_fail_target.setCurrentIndex(sel_fail_idx)
        self.combo_fail_target.blockSignals(False)

        self._on_fail_beh_changed()

    def _on_fail_beh_changed(self) -> None:
        beh = self.combo_fail_beh.currentData()
        show_target = beh == "goto_failure_step"
        self.lbl_fail_target.setVisible(show_target)
        self.combo_fail_target.setVisible(show_target)
        if self.step_data:
            self.step_data["failure_behavior"] = beh
            self.step_updated.emit()

    def _on_branching_changed(self) -> None:
        if not self.step_data:
            return
        self.step_data["on_success_order"] = self.combo_succ.currentData()
        self.step_data["on_failure_order"] = self.combo_fail_target.currentData()
        self.step_updated.emit()

    def _on_title_changed(self, text: str) -> None:
        if self.step_data:
            self.step_data["custom_title"] = text.strip()
            self.step_updated.emit()

    def _on_param_changed(self, key: str, value: Any) -> None:
        if self.step_data:
            self.step_data[key] = value
            self.step_updated.emit()

    def _on_config_changed(self, key: str, value: Any) -> None:
        if self.step_data:
            if "config" not in self.step_data:
                self.step_data["config"] = {}
            self.step_data["config"][key] = value
            self.step_updated.emit()

    def _on_test_step_clicked(self) -> None:
        if self.step_data:
            self.test_step_requested.emit(self.step_data)
