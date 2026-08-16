"""
Vue Éditeur d'Agents — Conforme au Design System et au Moteur DAG / MCP.
- Panneau gauche (260px) : Liste des agents IA disponibles depuis PersonaModel (Peewee).
- Panneau droit (Flex-1) : Éditeur complet d'agent :
  * Nom, Description, Format de sortie (JSON, Cloze, Markdown, Text).
  * Moteur IA Dédié (LLMConfigModel) avec option d'héritage global.
  * Permissions d'Outils MCP (allowed_tools) configurables.
  * Palette de snippets Jinja2 interactifs pour faciliter la rédaction du System Prompt.
- Persistance atomique dans la base de données Peewee.
"""

import json
import logging
from typing import Any, Dict, Optional

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import LLMConfigModel, PersonaModel, db
from ankiforge.ui.components import (
    DangerButton,
    IdePanel,
    PrimaryButton,
    SecondaryButton,
    StyledComboBox,
    StyledLineEdit,
    StyledTextEdit,
)
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)

# Registre des outils disponibles pour les Personas
AVAILABLE_TOOLS_SPEC: Dict[str, Dict[str, str]] = {
    "query_vector_db": {
        "label": "Recherche Vectorielle (RAG)",
        "desc": "Permet d'interroger la base FAISS/ChromaDB des documents importés.",
    },
    "read_anki_stats": {
        "label": "Statistiques Anki & Rétention",
        "desc": "Permet de lire les statistiques SRS (Sangsues, taux d'oubli).",
    },
    "generate_css": {
        "label": "Stylisation CSS d'Atelier",
        "desc": "Permet d'injecter des règles CSS directement dans les modèles de cartes.",
    },
    "execute_python_tool": {
        "label": "Outils Python Déterministes",
        "desc": "Permet d'exécuter des scripts de nettoyage et de formatage.",
    },
}

# Snippets Jinja2 usuels
JINJA2_SNIPPETS = [
    ("{{ text_source }}", "Texte Source"),
    ("{{ last_output }}", "Sortie Étape Précédente"),
    ("{{ fields }}", "Champs NoteType"),
    ("{{ retrieved_chunks }}", "Extraits RAG"),
    ("{{ state.variables.xxx }}", "Variable d'État"),
]


class AgentsView(QWidget):
    """
    Vue Éditeur d'Agents IA — Personas Augmentés d'Outils et Moteur Dédié.
    """

    def __init__(self, ai_manager: Optional[Any] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager
        self._current_agent: Optional[PersonaModel] = None
        self._tool_checkboxes: Dict[str, QCheckBox] = {}

        self._setup_ui()
        self._connect_signals()
        self.refresh_data()

    def _setup_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.main_splitter)

        # ── 1. Panneau Gauche : Liste des Personas (260px) ─────────────────────
        self.list_panel = IdePanel(detachable=True)
        self.list_panel.setMinimumWidth(250)

        list_content = QWidget()
        list_layout = QVBoxLayout(list_content)
        list_layout.setContentsMargins(10, 10, 10, 10)
        list_layout.setSpacing(8)

        lbl_list_title = QLabel("AGENTS & PERSONAS IA")
        lbl_list_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        list_layout.addWidget(lbl_list_title)

        self.persona_list = QListWidget()
        self.persona_list.setStyleSheet(f"""
            QListWidget {{
                background-color: transparent;
                border: none;
                color: {DesignTokens.TEXT_PRIMARY};
                outline: none;
            }}
            QListWidget::item {{
                padding: 10px 12px;
                border-radius: {DesignTokens.RADIUS_SM}px;
                margin-bottom: 3px;
                font-weight: 500;
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QListWidget::item:hover {{
                background-color: {DesignTokens.BG_HOVER};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QListWidget::item:selected {{
                background-color: rgba(99, 102, 241, 0.14);
                color: #a5b4fc;
                font-weight: bold;
                border-left: 3px solid #8b5cf6;
            }}
        """)
        list_layout.addWidget(self.persona_list, 1)

        # Barre inférieure de la liste
        list_toolbar = QHBoxLayout()
        list_toolbar.setSpacing(6)

        self.btn_new = SecondaryButton("Nouvel Agent")
        self.btn_new.setIcon(load_phosphor_icon("ph.plus", color=DesignTokens.TEXT_PRIMARY))

        self.btn_del = DangerButton("Supprimer", ghost=True)
        self.btn_del.setIcon(load_phosphor_icon("ph.trash", color=DesignTokens.COLOR_RED))

        list_toolbar.addWidget(self.btn_new, 1)
        list_toolbar.addWidget(self.btn_del, 1)
        list_layout.addLayout(list_toolbar)

        self.list_panel.add_tab("Liste des Agents", list_content, "ph.users", closable=False)
        self.main_splitter.addWidget(self.list_panel)

        # ── 2. Panneau Droit : Formulaire d'Édition Complète ──────────────────
        self.editor_panel = IdePanel(detachable=True)

        self.btn_save = PrimaryButton("Enregistrer les Modifications")
        self.btn_save.setIcon(load_phosphor_icon("ph.floppy-disk", color="white"))

        self.editor_panel.add_header_widget(self.btn_save)
        self.editor_panel.add_header_separator()

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setStyleSheet("background: transparent; border: none;")

        editor_content = QWidget()
        editor_layout = QVBoxLayout(editor_content)
        editor_layout.setContentsMargins(18, 18, 18, 18)
        editor_layout.setSpacing(14)

        # Nom de l'agent
        lbl_name = QLabel("NOM DU PERSONA :")
        lbl_name.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        editor_layout.addWidget(lbl_name)

        self.name_edit = StyledLineEdit()
        self.name_edit.setPlaceholderText("ex: Architecte de Cours, Rédacteur Médical, Linteur Wozniak...")
        editor_layout.addWidget(self.name_edit)

        # Description
        lbl_desc = QLabel("DESCRIPTION & RÔLE :")
        lbl_desc.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        editor_layout.addWidget(lbl_desc)

        self.desc_edit = StyledLineEdit()
        self.desc_edit.setPlaceholderText("ex: Analyse la structure du texte source et extrait le plan hiérarchique.")
        editor_layout.addWidget(self.desc_edit)

        # Ligne : Format de sortie & Moteur IA Dédié
        cfg_row = QHBoxLayout()
        cfg_row.setSpacing(16)

        # Format de sortie
        fmt_col = QVBoxLayout()
        lbl_format = QLabel("FORMAT DE SORTIE ATTENDU :")
        lbl_format.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        fmt_col.addWidget(lbl_format)
        self.format_combo = StyledComboBox()
        self.format_combo.addItems(["json", "cloze", "markdown", "text"])
        fmt_col.addWidget(self.format_combo)
        cfg_row.addLayout(fmt_col, 1)

        # Moteur IA Dédié
        engine_col = QVBoxLayout()
        lbl_engine = QLabel("MOTEUR IA DÉDIÉ (OPTIONNEL) :")
        lbl_engine.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        engine_col.addWidget(lbl_engine)
        self.engine_combo = StyledComboBox()
        engine_col.addWidget(self.engine_combo)
        cfg_row.addLayout(engine_col, 1)

        editor_layout.addLayout(cfg_row)

        # Permissions d'Outils (allowed_tools)
        lbl_tools = QLabel("PERMISSIONS D'OUTILS MCP & ACTIONS AUTORISÉES :")
        lbl_tools.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        editor_layout.addWidget(lbl_tools)

        tools_container = QFrame()
        tools_container.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_SIDEBAR};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 10px;
            }}
        """)
        tools_grid = QGridLayout(tools_container)
        tools_grid.setContentsMargins(8, 8, 8, 8)
        tools_grid.setSpacing(10)

        col = 0
        row = 0
        for tool_key, tool_info in AVAILABLE_TOOLS_SPEC.items():
            cb = QCheckBox(tool_info["label"])
            cb.setToolTip(tool_info["desc"])
            cb.setStyleSheet(f"""
                QCheckBox {{
                    color: {DesignTokens.TEXT_PRIMARY};
                    font-size: 12px;
                }}
                QCheckBox::indicator {{
                    width: 16px;
                    height: 16px;
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: 4px;
                    background: {DesignTokens.BG_INPUT};
                }}
                QCheckBox::indicator:checked {{
                    background-color: {DesignTokens.ACCENT_PRIMARY};
                    border-color: {DesignTokens.ACCENT_PRIMARY};
                }}
            """)
            self._tool_checkboxes[tool_key] = cb
            tools_grid.addWidget(cb, row, col)
            col += 1
            if col > 1:
                col = 0
                row += 1

        editor_layout.addWidget(tools_container)

        # Snippets Jinja2 Palette
        prompt_header_row = QHBoxLayout()
        lbl_prompt = QLabel("PROMPT JINJA2 (INSTRUCTIONS SYSTÈME) :")
        lbl_prompt.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        prompt_header_row.addWidget(lbl_prompt)
        prompt_header_row.addStretch()

        editor_layout.addLayout(prompt_header_row)

        # Barre de boutons de Snippets
        snippets_bar = QHBoxLayout()
        snippets_bar.setSpacing(6)
        lbl_snip = QLabel("Insérer :")
        lbl_snip.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        snippets_bar.addWidget(lbl_snip)

        for template_code, display_name in JINJA2_SNIPPETS:
            btn_snip = SecondaryButton(display_name)
            btn_snip.setStyleSheet(f"""
                QPushButton {{
                    background: {DesignTokens.BG_SIDEBAR};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    color: {DesignTokens.TEXT_SECONDARY};
                    font-size: 11px;
                    padding: 3px 8px;
                    border-radius: 4px;
                }}
                QPushButton:hover {{
                    border-color: {DesignTokens.ACCENT_PRIMARY};
                    color: #a5b4fc;
                }}
            """)
            btn_snip.clicked.connect(lambda _, code=template_code: self._insert_jinja_snippet(code))
            snippets_bar.addWidget(btn_snip)
        snippets_bar.addStretch()
        editor_layout.addLayout(snippets_bar)

        # Éditeur de Prompt
        self.prompt_edit = StyledTextEdit()
        self.prompt_edit.setPlaceholderText("Tu es un expert en création de flashcards Anki...\nUtilisez {{ variable }} pour le templating Jinja2.")
        self.prompt_edit.setMinimumHeight(240)
        self.prompt_edit.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {DesignTokens.BG_INPUT};
                color: #a5b4fc;
                font-family: 'JetBrains Mono', 'Fira Code', Menlo, monospace;
                font-size: 13px;
                line-height: 1.5;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                padding: 12px;
            }}
            QPlainTextEdit:focus {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        editor_layout.addWidget(self.prompt_edit, 1)

        scroll_area.setWidget(editor_content)
        self.editor_panel.add_tab("Éditeur d'Agents", scroll_area, "ph.sparkle", closable=False)
        self.main_splitter.addWidget(self.editor_panel)

        self.main_splitter.setSizes([260, 740])

    def _connect_signals(self) -> None:
        self.persona_list.currentItemChanged.connect(self._on_item_selected)
        self.btn_new.clicked.connect(self._on_new_agent)
        self.btn_del.clicked.connect(self._on_delete_agent)
        self.btn_save.clicked.connect(self._on_save_agent)

    def refresh_data(self) -> None:
        """Recharge la liste des agents et des moteurs LLM depuis Peewee DB."""
        try:
            # 1. Recharger les moteurs LLM
            self.engine_combo.blockSignals(True)
            self.engine_combo.clear()
            self.engine_combo.addItem("⚙️ Hériter du réglage global de l'application", userData=None)

            llm_configs = list(LLMConfigModel.select())
            for cfg in llm_configs:
                display = cfg.display_name or f"{cfg.provider} ({cfg.model_id})"
                self.engine_combo.addItem(f"🤖 {display}", userData=cfg)
            self.engine_combo.blockSignals(False)

            # 2. Recharger les personas
            self.persona_list.blockSignals(True)
            self.persona_list.clear()

            agents = list(PersonaModel.select())
            for ag in agents:
                item = QListWidgetItem(ag.name)
                item.setData(Qt.ItemDataRole.UserRole, ag)
                self.persona_list.addItem(item)

            self.persona_list.blockSignals(False)

            if agents and not self._current_agent:
                self.persona_list.setCurrentRow(0)

        except Exception as e:
            logger.warning("Erreur refresh_data agents_view: %s", e)

    def is_dirty(self) -> bool:
        return False

    def _insert_jinja_snippet(self, snippet: str) -> None:
        """Insère un snippet Jinja2 à la position courante du curseur."""
        cursor = self.prompt_edit.textCursor()
        cursor.insertText(snippet)
        self.prompt_edit.setTextCursor(cursor)
        self.prompt_edit.setFocus()

    @Slot()
    def _on_item_selected(self, current: Optional[QListWidgetItem], previous: Optional[QListWidgetItem]) -> None:
        if not current:
            self._current_agent = None
            return

        ag: Optional[PersonaModel] = current.data(Qt.ItemDataRole.UserRole)
        if not ag:
            return

        self._current_agent = ag
        self.name_edit.setText(str(ag.name) if ag.name else "")
        self.desc_edit.setText(str(ag.description) if ag.description else "")
        self.prompt_edit.setPlainText(str(ag.system_prompt) if ag.system_prompt else "")

        # Format de sortie
        fmt = getattr(ag, "output_format", "json").lower()
        idx = self.format_combo.findText(fmt, Qt.MatchFlag.MatchFixedString)
        if idx != -1:
            self.format_combo.setCurrentIndex(idx)
        else:
            self.format_combo.setCurrentText("json")

        # Moteur IA dédié
        self.engine_combo.blockSignals(True)
        if getattr(ag, "llm_config", None):
            cfg_id = ag.llm_config.id
            idx_e = -1
            for i in range(self.engine_combo.count()):
                cfg_item = self.engine_combo.itemData(i)
                if cfg_item and getattr(cfg_item, "id", None) == cfg_id:
                    idx_e = i
                    break
            self.engine_combo.setCurrentIndex(idx_e if idx_e != -1 else 0)
        else:
            self.engine_combo.setCurrentIndex(0)
        self.engine_combo.blockSignals(False)

        # Outils autorisés (allowed_tools)
        allowed_list = []
        try:
            raw_tools = getattr(ag, "allowed_tools", "[]") or "[]"
            allowed_list = json.loads(raw_tools)
        except Exception:
            allowed_list = []

        for tool_key, cb in self._tool_checkboxes.items():
            cb.setChecked(tool_key in allowed_list)

    @Slot()
    def _on_new_agent(self) -> None:
        name, ok = QInputDialog.getText(self, "Nouvel Agent IA", "Nom de l'agent :")
        if ok and name.strip():
            try:
                ag_name = name.strip()
                default_prompt = "Tu es un agent IA spécialisé dans l'optimisation des cartes de révision Anki."
                PersonaModel.create(
                    name=ag_name,
                    description="Nouvel agent IA configuré par l'utilisateur.",
                    system_prompt=default_prompt,
                    output_format="json",
                    allowed_tools="[]",
                )
                self.refresh_data()

                # Sélectionner l'agent créé
                for i in range(self.persona_list.count()):
                    item = self.persona_list.item(i)
                    if item.text() == ag_name:
                        self.persona_list.setCurrentItem(item)
                        break

                show_toast(self, f"Agent '{ag_name}' créé avec succès !")
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Impossible de créer l'agent : {str(e)}")

    @Slot()
    def _on_delete_agent(self) -> None:
        if not self._current_agent:
            show_toast(self, "Aucun agent sélectionné.", is_error=True)
            return

        confirm = QMessageBox.question(
            self,
            "Supprimer l'agent",
            f"Voulez-vous vraiment supprimer l'agent '{self._current_agent.name}' ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            try:
                self._current_agent.delete_instance()
                self._current_agent = None
                self.refresh_data()
                show_toast(self, "Agent supprimé de la base de données.")
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Impossible de supprimer l'agent : {str(e)}")

    @Slot()
    def _on_save_agent(self) -> None:
        if not self._current_agent:
            show_toast(self, "Aucun agent sélectionné à sauvegarder.", is_error=True)
            return

        try:
            name = self.name_edit.text().strip()
            if not name:
                show_toast(self, "Le nom de l'agent ne peut pas être vide.", is_error=True)
                return

            # Outils cochés
            selected_tools = [key for key, cb in self._tool_checkboxes.items() if cb.isChecked()]
            selected_engine: Optional[LLMConfigModel] = self.engine_combo.currentData()

            with db.atomic():
                self._current_agent.name = str(name)
                self._current_agent.description = str(self.desc_edit.text().strip())
                self._current_agent.system_prompt = str(self.prompt_edit.toPlainText())
                self._current_agent.output_format = str(self.format_combo.currentText().lower())
                self._current_agent.allowed_tools = str(json.dumps(selected_tools))
                self._current_agent.llm_config_id = selected_engine.id if selected_engine else None
                self._current_agent.save()

            show_toast(self, f"Agent '{name}' enregistré avec succès !")
            self.refresh_data()
        except Exception as e:
            QMessageBox.critical(self, "Erreur de sauvegarde", f"Échec de l'enregistrement de l'agent : {str(e)}")


AgentsTab = AgentsView
