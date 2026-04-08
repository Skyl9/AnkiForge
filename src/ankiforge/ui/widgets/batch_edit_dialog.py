import qtawesome as qta
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QComboBox, QTextEdit, QSpinBox, QMessageBox)

from ankiforge.database.models import LLMConfigModel, AgentModel
from ankiforge.ui.components.components import PrimaryButton, ActionButton


class BatchEditDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("✨ Audit & Modification par l'IA")
        self.setMinimumWidth(500)
        self.setStyleSheet("QDialog { background-color: palette(window); }")

        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # 1. Choix du Moteur IA
        layout.addWidget(QLabel("<b>1. Moteur IA :</b>"))
        self.cb_llm = QComboBox()
        for llm in LLMConfigModel.select().order_by(LLMConfigModel.display_name):
            self.cb_llm.addItem(llm.display_name, userData=llm.id)
        layout.addWidget(self.cb_llm)

        # 2. Choix du mode opératoire (Agent ou Libre)
        layout.addWidget(QLabel("<b>2. Instruction (Agent ou Prompt libre) :</b>"))
        self.cb_agent = QComboBox()
        self.cb_agent.addItem("-- ✍️ Prompt Libre (Saisir ci-dessous) --", userData=None)
        for agent in AgentModel.select().order_by(AgentModel.name):
            self.cb_agent.addItem(f"🤖 Agent : {agent.name}", userData=agent.id)
        self.cb_agent.currentIndexChanged.connect(self._on_agent_changed)
        layout.addWidget(self.cb_agent)

        self.text_prompt = QTextEdit()
        self.text_prompt.setPlaceholderText(
            "Ex: Traduis le champ 'Verso' en anglais et ajoute une astuce mnémotechnique...")
        self.text_prompt.setMinimumHeight(100)
        layout.addWidget(self.text_prompt)

        # 3. Taille du découpage (Le Chunk Size !)
        layout.addWidget(QLabel("<b>3. Taille des lots (Découpage) :</b>"))
        chunk_layout = QHBoxLayout()
        self.spin_chunk = QSpinBox()
        self.spin_chunk.setRange(1, 100)
        self.spin_chunk.setValue(5)  # Par défaut, on traite par 5
        self.spin_chunk.setSuffix(" cartes par requête")

        lbl_chunk_desc = QLabel("<i>Un nombre petit (3-5) réduit les erreurs de formatage de l'IA.</i>")
        lbl_chunk_desc.setStyleSheet("color: palette(placeholder-text);")

        chunk_layout.addWidget(self.spin_chunk)
        chunk_layout.addWidget(lbl_chunk_desc)
        chunk_layout.addStretch()
        layout.addLayout(chunk_layout)

        # 4. Boutons
        btn_layout = QHBoxLayout()
        self.btn_cancel = ActionButton('fa5s.times', "Annuler")
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_start = PrimaryButton(qta.icon('fa5s.magic', color='white'), "Lancer le traitement")
        self.btn_start.clicked.connect(self.accept)

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_start)
        layout.addLayout(btn_layout)

    def _on_agent_changed(self):
        agent_id = self.cb_agent.currentData()
        if agent_id:
            agent = AgentModel.get_by_id(agent_id)
            self.text_prompt.setPlainText(agent.system_prompt)
            self.text_prompt.setReadOnly(True)
            self.text_prompt.setStyleSheet(
                "background-color: palette(alternate-base); color: palette(placeholder-text);")
        else:
            self.text_prompt.clear()
            self.text_prompt.setReadOnly(False)
            self.text_prompt.setStyleSheet("")

    def get_data(self):
        """Retourne les choix de l'utilisateur."""
        return {
            "llm_id": self.cb_llm.currentData(),
            "prompt": self.text_prompt.toPlainText().strip(),
            "chunk_size": self.spin_chunk.value()
        }