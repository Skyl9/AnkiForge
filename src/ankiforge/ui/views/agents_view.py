"""
Vue Éditeur d'Agents — 100% Conforme à la Maquette concept_ide.
- Panneau gauche (260px) : Liste des agents IA disponibles depuis AgentModel (Peewee).
- Panneau droit (Flex-1) : Éditeur complet d'agent (Nom, Description, Format de sortie JSON/Cloze/Markdown, Prompt Jinja2).
- Persistance atomique dans la base de données Peewee.
"""

import logging
from typing import Any, Optional

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import AgentModel
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


class AgentsView(QWidget):
    """
    Vue Éditeur d'Agents IA — 100% Conforme à la Maquette concept_ide.
    """

    def __init__(self, ai_manager: Optional[Any] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager
        self._current_agent: Optional[AgentModel] = None

        self._setup_ui()
        self._connect_signals()
        self.refresh_data()

    def _setup_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.main_splitter)

        # --- PANNEAU GAUCHE : Agents IA (260px) ---
        self.list_panel = IdePanel(detachable=True)
        self.list_panel.setMinimumWidth(240)

        list_content = QWidget()
        list_layout = QVBoxLayout(list_content)
        list_layout.setContentsMargins(10, 10, 10, 10)
        list_layout.setSpacing(8)

        lbl_list_title = QLabel("AGENTS DISPONIBLES")
        lbl_list_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        list_layout.addWidget(lbl_list_title)

        self.agent_list = QListWidget()
        self.agent_list.setStyleSheet(f"""
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
        list_layout.addWidget(self.agent_list, 1)

        # Toolbar inférieure (Nouveau & Supprimer)
        list_toolbar = QHBoxLayout()
        list_toolbar.setSpacing(6)

        self.btn_new = SecondaryButton("Nouveau")
        self.btn_new.setIcon(load_phosphor_icon("ph.plus", color=DesignTokens.TEXT_PRIMARY))

        self.btn_del = DangerButton("Supprimer", ghost=True)
        self.btn_del.setIcon(load_phosphor_icon("ph.trash", color=DesignTokens.COLOR_RED))

        list_toolbar.addWidget(self.btn_new, 1)
        list_toolbar.addWidget(self.btn_del, 1)
        list_layout.addLayout(list_toolbar)

        self.list_panel.add_tab("Liste des Agents IA", list_content, "ph.users", closable=False)
        self.main_splitter.addWidget(self.list_panel)

        # --- PANNEAU DROITE : Éditeur d'Agents IA ---
        self.editor_panel = IdePanel(detachable=True)

        self.btn_save = PrimaryButton("Sauvegarder")
        self.btn_save.setIcon(load_phosphor_icon("ph.floppy-disk", color="white"))

        self.editor_panel.add_header_widget(self.btn_save)
        self.editor_panel.add_header_separator()

        editor_content = QWidget()
        editor_layout = QVBoxLayout(editor_content)
        editor_layout.setContentsMargins(16, 16, 16, 16)
        editor_layout.setSpacing(12)

        # Champ Nom
        lbl_name = QLabel("NOM DE L'AGENT :")
        lbl_name.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        editor_layout.addWidget(lbl_name)

        self.name_edit = StyledLineEdit()
        self.name_edit.setPlaceholderText("ex: Linter Qualité")
        editor_layout.addWidget(self.name_edit)

        # Champ Description
        lbl_desc = QLabel("DESCRIPTION (OPTIONNEL) :")
        lbl_desc.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        editor_layout.addWidget(lbl_desc)

        self.desc_edit = StyledLineEdit()
        self.desc_edit.setPlaceholderText("ex: Vérifie la pertinence et les règles de brièveté des cartes.")
        editor_layout.addWidget(self.desc_edit)

        # Champ Format de sortie
        lbl_format = QLabel("FORMAT DE SORTIE :")
        lbl_format.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        editor_layout.addWidget(lbl_format)

        self.format_combo = StyledComboBox()
        self.format_combo.addItems(["json", "cloze", "markdown", "text"])
        editor_layout.addWidget(self.format_combo)

        # Champ Prompt Jinja2
        lbl_prompt = QLabel("PROMPT JINJA2 (INSTRUCTIONS SYSTÈME) :")
        lbl_prompt.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        editor_layout.addWidget(lbl_prompt)

        self.prompt_edit = StyledTextEdit()
        self.prompt_edit.setPlaceholderText("Tu es un expert en création de flashcards Anki...\nUtilisez {{ variable }} pour le templating Jinja2.")
        self.prompt_edit.setStyleSheet("""
            QPlainTextEdit {
                background-color: #090a0f;
                color: #a5b4fc;
                font-family: 'JetBrains Mono', 'Fira Code', monospace;
                font-size: 13px;
                line-height: 1.5;
                border: 1px solid #2d313a;
                border-radius: 6px;
                padding: 10px;
            }
        """)
        editor_layout.addWidget(self.prompt_edit, 1)

        self.editor_panel.add_tab("Éditeur d'Agents IA", editor_content, "ph.robot", closable=False)
        self.main_splitter.addWidget(self.editor_panel)

        self.main_splitter.setSizes([260, 740])

    def _connect_signals(self) -> None:
        self.agent_list.currentItemChanged.connect(self._on_item_selected)
        self.btn_new.clicked.connect(self._on_new_agent)
        self.btn_del.clicked.connect(self._on_delete_agent)
        self.btn_save.clicked.connect(self._on_save_agent)

    def refresh_data(self) -> None:
        """Recharge la liste des agents depuis Peewee DB."""
        try:
            self.agent_list.blockSignals(True)
            self.agent_list.clear()

            agents = list(AgentModel.select())
            for ag in agents:
                item = QListWidgetItem(f"🤖 {ag.name}")
                item.setData(Qt.ItemDataRole.UserRole, ag)
                self.agent_list.addItem(item)

            self.agent_list.blockSignals(False)

            if agents and not self._current_agent:
                self.agent_list.setCurrentRow(0)

        except Exception as e:
            logger.warning("Erreur refresh_data agents_view: %s", e)

    def is_dirty(self) -> bool:
        return False

    @Slot()
    def _on_item_selected(self, current: Optional[QListWidgetItem], previous: Optional[QListWidgetItem]) -> None:
        if not current:
            self._current_agent = None
            return

        ag: Optional[AgentModel] = current.data(Qt.ItemDataRole.UserRole)
        if not ag:
            return

        self._current_agent = ag
        self.name_edit.setText(ag.name)
        self.desc_edit.setText(ag.description or "")
        self.prompt_edit.setPlainText(ag.system_prompt or "")

        fmt = getattr(ag, "output_format", "json").lower()
        idx = self.format_combo.findText(fmt, Qt.MatchFlag.MatchFixedString)
        if idx != -1:
            self.format_combo.setCurrentIndex(idx)
        else:
            self.format_combo.setCurrentText("json")

    @Slot()
    def _on_new_agent(self) -> None:
        name, ok = QInputDialog.getText(self, "Nouvel Agent IA", "Nom de l'agent :")
        if ok and name.strip():
            try:
                ag_name = name.strip()
                default_prompt = "Tu es un agent IA spécialisé dans l'optimisation des cartes de révision Anki."
                AgentModel.create(
                    name=ag_name,
                    description="Nouvel agent IA configuré par l'utilisateur.",
                    system_prompt=default_prompt,
                    output_format="json",
                )
                self.refresh_data()

                # Sélectionner l'agent créé
                for i in range(self.agent_list.count()):
                    item = self.agent_list.item(i)
                    if item.text() == f"🤖 {ag_name}":
                        self.agent_list.setCurrentItem(item)
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

            self._current_agent.name = name
            self._current_agent.description = self.desc_edit.text().strip()
            self._current_agent.system_prompt = self.prompt_edit.toPlainText()
            self._current_agent.output_format = self.format_combo.currentText().lower()
            self._current_agent.save()

            show_toast(self, f"Agent '{name}' enregistré avec succès !")
            self.refresh_data()
        except Exception as e:
            QMessageBox.critical(self, "Erreur de sauvegarde", f"Échec de l'enregistrement de l'agent : {str(e)}")


AgentsTab = AgentsView
