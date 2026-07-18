import logging

import qtawesome as qta
from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QSplitter,
    QMessageBox,
    QListWidgetItem,
    QPushButton,
)

from ankiforge.database.models import AgentModel
from ankiforge.ui.components.components import ActionButton, PrimaryButton, DangerButton, RoundedPanel
from ankiforge.ui.components.inputs import StyledLineEdit, StyledTextEdit, StyledComboBox
from ankiforge.ui.widgets.highlighters import JinjaHighlighter
from ankiforge.ui.widgets.toast import show_toast

logger = logging.getLogger(__name__)


class AgentsTab(QWidget):
    """
    AI Agents Editor tab.
    Allows creating and modifying individual agents.
    """

    def __init__(self) -> None:
        """Initializes the agents tab."""
        super().__init__()
        self.agent_id: int | None = None

        self._setup_ui()
        self._connect_signals()

        self.refresh_ui()

    def _setup_ui(self) -> None:
        """Builds and organizes main layouts and widgets."""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 20, 20, 20)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setHandleWidth(10)

        self._build_agents_list_panel()
        self._build_agent_editor_panel()

        self.main_splitter.setSizes([250, 750])
        self.main_layout.addWidget(self.main_splitter)

    def _build_agents_list_panel(self) -> None:
        list_panel = RoundedPanel()
        list_layout = QVBoxLayout(list_panel)
        list_layout.setContentsMargins(15, 15, 15, 15)

        lbl_agents = QLabel(self.tr("🤖 AGENT LIST"))
        lbl_agents.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px;")
        list_layout.addWidget(lbl_agents)

        self.agents_list = QListWidget()
        self.agents_list.setStyleSheet("QListWidget { border: none; background: transparent; }")
        list_layout.addWidget(self.agents_list)

        self.btn_new_agent = ActionButton("fa5s.plus", self.tr(" New Agent"))
        list_layout.addWidget(self.btn_new_agent)

        self.main_splitter.addWidget(list_panel)

    def _build_agent_editor_panel(self) -> None:
        editor_panel = RoundedPanel()
        editor_layout = QVBoxLayout(editor_panel)
        editor_layout.setContentsMargins(20, 20, 20, 20)

        lbl_edit = QLabel(self.tr("AGENT EDITOR FORM"))
        lbl_edit.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px; margin-bottom: 5px;")
        editor_layout.addWidget(lbl_edit)

        name_layout = QHBoxLayout()
        lbl_name = QLabel(self.tr("Name:"))
        lbl_name.setStyleSheet("font-weight: bold; color: palette(text); font-size: 11px;")
        self.agent_name_input = StyledLineEdit()
        self.agent_name_input.setPlaceholderText(self.tr("ex: Quality Linter"))
        name_layout.addWidget(lbl_name)
        name_layout.addWidget(self.agent_name_input)
        editor_layout.addLayout(name_layout)

        desc_layout = QHBoxLayout()
        lbl_desc = QLabel(self.tr("Description:"))
        lbl_desc.setStyleSheet("font-weight: bold; color: palette(text); font-size: 11px;")
        self.agent_desc_input = StyledLineEdit()
        self.agent_desc_input.setPlaceholderText(self.tr("Role of this agent..."))
        desc_layout.addWidget(lbl_desc)
        desc_layout.addWidget(self.agent_desc_input)
        editor_layout.addLayout(desc_layout)

        lbl_prompt = QLabel(self.tr("System Prompt (Jinja2):"))
        lbl_prompt.setStyleSheet("font-weight: bold; color: palette(text); font-size: 11px; margin-top: 10px;")
        editor_layout.addWidget(lbl_prompt)

        snippets_layout = QHBoxLayout()
        snippets_layout.setSpacing(5)

        snippets = [
            ("{{ fields_str }}", "{{ fields_str }}"),
            ("{{ first_field }}", "{{ first_field }}"),
            ("{{ second_field }}", "{{ second_field }}"),
            ("{% if %}", "{% if condition %}\n    \n{% endif %}"),
            ("{% for %}", "{% for item in liste %}\n    \n{% endfor %}"),
        ]

        for label, text in snippets:
            btn = QPushButton(label)
            btn.setFlat(True)
            btn.setStyleSheet("font-size: 10px; padding: 3px 6px; border: 1px solid palette(alternate-base); border-radius: 4px; color: palette(highlight);")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, t=text: self.insert_snippet(t))
            snippets_layout.addWidget(btn)

        snippets_layout.addStretch()
        editor_layout.addLayout(snippets_layout)

        self.agent_prompt_input = StyledTextEdit()
        self.agent_prompt_input.setPlaceholderText(self.tr("You are an expert in... Your variables are {{Front}} and {{Back}}..."))
        self.agent_prompt_input.setStyleSheet("font-family: monospace; font-size: 12px; background-color: palette(base);")

        self.jinja_highlighter = JinjaHighlighter(self.agent_prompt_input.document())

        editor_layout.addWidget(self.agent_prompt_input, stretch=1)

        format_layout = QHBoxLayout()
        lbl_format = QLabel(self.tr("Output Format:"))
        lbl_format.setStyleSheet("font-weight: bold; color: palette(text); font-size: 11px")
        format_layout.addWidget(lbl_format)

        self.cb_output_format = StyledComboBox()
        self.cb_output_format.addItem(self.tr("Strict JSON (Final agent for Anki)"), userData="json")
        self.cb_output_format.addItem(self.tr("Free Text / Markdown (Intermediate agent)"), userData="text")
        format_layout.addWidget(self.cb_output_format)
        format_layout.addStretch()
        editor_layout.addLayout(format_layout)

        btn_layout_agent = QHBoxLayout()
        self.btn_delete_agent = DangerButton(qta.icon("fa5s.trash", color="white"), self.tr(" Delete"))
        self.btn_save_agent = PrimaryButton(qta.icon("fa5s.save", color="white"), self.tr(" Sauvegarder"))

        btn_layout_agent.addStretch()
        btn_layout_agent.addWidget(self.btn_delete_agent)
        btn_layout_agent.addWidget(self.btn_save_agent)

        editor_layout.addLayout(btn_layout_agent)

        self.main_splitter.addWidget(editor_panel)

    def _connect_signals(self) -> None:
        self.agents_list.itemClicked.connect(self.load_selected_agent)
        self.btn_new_agent.clicked.connect(self.clear_agent_form)
        self.btn_delete_agent.clicked.connect(self.delete_agent)
        self.btn_save_agent.clicked.connect(self.save_agent)

    @Slot()
    def refresh_data(self) -> None:
        self.refresh_ui()

    def insert_snippet(self, text: str) -> None:
        cursor = self.agent_prompt_input.textCursor()
        cursor.insertText(text)
        self.agent_prompt_input.setTextCursor(cursor)
        self.agent_prompt_input.setFocus()

    @Slot()
    def refresh_ui(self) -> None:
        self.agents_list.clear()

        for agent in AgentModel.select().order_by(AgentModel.name):
            self.agents_list.addItem(agent.name)

    @Slot()
    def clear_agent_form(self) -> None:
        self.agent_id = None
        self.agent_name_input.clear()
        self.agent_desc_input.clear()
        self.agent_prompt_input.clear()
        self.cb_output_format.setCurrentIndex(0)
        self.agents_list.clearSelection()

    @Slot(QListWidgetItem)
    def load_selected_agent(self, item: QListWidgetItem) -> None:
        agent = AgentModel.get_or_none(AgentModel.name == item.text())
        if not agent:
            return

        self.agent_id = agent.id
        self.agent_name_input.setText(agent.name)
        self.agent_desc_input.setText(agent.description or "")
        self.agent_prompt_input.setPlainText(agent.system_prompt)
        idx = self.cb_output_format.findData(agent.output_format)
        if idx >= 0:
            self.cb_output_format.setCurrentIndex(idx)

    @Slot()
    def save_agent(self) -> None:
        name = self.agent_name_input.text().strip()
        desc = self.agent_desc_input.text().strip()
        prompt = self.agent_prompt_input.toPlainText().strip()
        output_format = self.cb_output_format.currentData()

        if not name or not prompt:
            QMessageBox.warning(self, "Error", self.tr("Name and prompt are required."))
            return

        try:
            if self.agent_id:
                agent = AgentModel.get_by_id(self.agent_id)
                agent.name = name
                agent.description = desc
                agent.system_prompt = prompt
                agent.output_format = output_format
                agent.save()
            else:
                AgentModel.create(name=name, description=desc, system_prompt=prompt, output_format=output_format)
            logger.info(f"Agent '{name}' saved.")
            show_toast(self, self.tr("Agent saved!"))
            self.refresh_ui()
        except Exception as e:
            logger.exception(f"Error while saving agent '{name}'")
            QMessageBox.critical(self, self.tr("Error"), self.tr("Error during save: {0}").format(str(e)))

    @Slot()
    def delete_agent(self) -> None:
        if not self.agent_id:
            QMessageBox.warning(self, self.tr("Error"), self.tr("Please select an agent before deleting it."))
            return

        name = self.agent_name_input.text().strip()

        reply = QMessageBox.question(
            self,
            self.tr("Confirmation"),
            self.tr('Do you really want to delete the agent "{0}"?').format(name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                agent = AgentModel.get_by_id(self.agent_id)
                agent.delete_instance(recursive=True)

                logger.info(f"Agent '{name}' deleted successfully.")
                show_toast(self, self.tr("Agent successfully destroyed"))

                self.clear_agent_form()
                self.refresh_ui()

            except Exception as e:
                logger.exception(f"Unable to delete agent '{name}'")
                QMessageBox.critical(self, self.tr("Error"), self.tr('Unable to delete agent "{0}":').format(name) + f"\n{e}")
