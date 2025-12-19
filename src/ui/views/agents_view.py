from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QLineEdit, QTextEdit, QPushButton, QListWidget,
                               QSplitter, QMessageBox, QGroupBox, QComboBox, QAbstractItemView)

from src.database.models import db, AgentModel, PipelineModel, PipelineStepModel


class AgentsTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        # SPLITTER PRINCIPAL (Gauche: Agents / Droite: Pipelines)
        main_splitter = QSplitter(Qt.Horizontal)

        # ==========================================
        # 🧪 PARTIE GAUCHE : LABORATOIRE DES AGENTS
        # ==========================================
        agents_widget = QWidget()
        agents_layout = QVBoxLayout(agents_widget)

        agents_layout.addWidget(QLabel("<h2>🤖 Laboratoire des Agents</h2>"))

        # Liste des agents
        self.agents_list = QListWidget()
        self.agents_list.itemClicked.connect(self.load_selected_agent)
        agents_layout.addWidget(self.agents_list)

        # Formulaire Agent
        self.agent_id = None

        form_group = QGroupBox("Édition de l'Agent")
        form_layout = QVBoxLayout(form_group)

        self.agent_name_input = QLineEdit()
        self.agent_name_input.setPlaceholderText("Nom (ex: Agent Linteur)")
        form_layout.addWidget(QLabel("<b>Nom :</b>"))
        form_layout.addWidget(self.agent_name_input)

        self.agent_desc_input = QLineEdit()
        self.agent_desc_input.setPlaceholderText("Description du rôle...")
        form_layout.addWidget(QLabel("<b>Description :</b>"))
        form_layout.addWidget(self.agent_desc_input)

        self.agent_prompt_input = QTextEdit()
        self.agent_prompt_input.setPlaceholderText("Prompt Système Jinja2...")
        form_layout.addWidget(QLabel("<b>Prompt Système (Jinja2) :</b>"))
        form_layout.addWidget(self.agent_prompt_input)

        # Boutons Agent
        btn_layout_agent = QHBoxLayout()
        self.btn_new_agent = QPushButton("➕ Nouvel Agent")
        self.btn_new_agent.clicked.connect(self.clear_agent_form)
        self.btn_save_agent = QPushButton("💾 Sauvegarder l'Agent")
        self.btn_save_agent.clicked.connect(self.save_agent)
        self.btn_save_agent.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")

        btn_layout_agent.addWidget(self.btn_new_agent)
        btn_layout_agent.addWidget(self.btn_save_agent)
        form_layout.addLayout(btn_layout_agent)

        agents_layout.addWidget(form_group)

        # ==========================================
        # ⚙️ PARTIE DROITE : ASSEMBLEUR DE PIPELINES
        # ==========================================
        pipelines_widget = QWidget()
        pipelines_layout = QVBoxLayout(pipelines_widget)

        pipelines_layout.addWidget(QLabel("<h2>⚙️ Assembleur de Pipelines</h2>"))

        # Sélection du Pipeline
        pipe_header = QHBoxLayout()
        self.pipeline_selector = QComboBox()
        self.pipeline_selector.currentIndexChanged.connect(self.load_selected_pipeline)
        pipe_header.addWidget(QLabel("<b>Pipeline :</b>"))
        pipe_header.addWidget(self.pipeline_selector, stretch=1)

        self.btn_new_pipeline = QPushButton("➕ Nouveau Pipeline")
        self.btn_new_pipeline.clicked.connect(self.create_new_pipeline)
        pipe_header.addWidget(self.btn_new_pipeline)
        pipelines_layout.addLayout(pipe_header)

        # Éditeur de la chaîne
        chain_group = QGroupBox("Chaîne d'exécution (Ordre des Agents)")
        chain_layout = QVBoxLayout(chain_group)

        # Ajout d'un agent à la chaîne
        add_step_layout = QHBoxLayout()
        self.available_agents_cb = QComboBox()
        self.btn_add_step = QPushButton("Ajouter à la chaîne ⬇️")
        self.btn_add_step.clicked.connect(self.add_agent_to_pipeline)
        add_step_layout.addWidget(self.available_agents_cb, stretch=1)
        add_step_layout.addWidget(self.btn_add_step)
        chain_layout.addLayout(add_step_layout)

        # Liste des étapes (Drag & Drop visuel simulé par liste)
        self.steps_list = QListWidget()
        self.steps_list.setSelectionMode(QAbstractItemView.SingleSelection)
        chain_layout.addWidget(self.steps_list)

        # Contrôles des étapes
        step_ctrl_layout = QHBoxLayout()
        self.btn_step_up = QPushButton("⬆️ Monter")
        self.btn_step_up.clicked.connect(self.move_step_up)
        self.btn_step_down = QPushButton("⬇️ Descendre")
        self.btn_step_down.clicked.connect(self.move_step_down)
        self.btn_step_remove = QPushButton("❌ Retirer")
        self.btn_step_remove.clicked.connect(self.remove_step)

        step_ctrl_layout.addWidget(self.btn_step_up)
        step_ctrl_layout.addWidget(self.btn_step_down)
        step_ctrl_layout.addWidget(self.btn_step_remove)
        chain_layout.addLayout(step_ctrl_layout)

        # Sauvegarde du Pipeline
        self.btn_save_pipeline = QPushButton("💾 Sauvegarder le Pipeline")
        self.btn_save_pipeline.setStyleSheet(
            "background-color: #2196F3; color: white; font-weight: bold; padding: 8px;")
        self.btn_save_pipeline.clicked.connect(self.save_pipeline_steps)
        chain_layout.addWidget(self.btn_save_pipeline)

        pipelines_layout.addWidget(chain_group)

        # Assemblage final
        main_splitter.addWidget(agents_widget)
        main_splitter.addWidget(pipelines_widget)
        main_splitter.setSizes([500, 500])

        layout.addWidget(main_splitter)

        self.refresh_ui()

    # --- MÉTHODES AGENTS ---
    def refresh_ui(self):
        """Recharge toutes les données depuis la base."""
        self.agents_list.clear()
        self.available_agents_cb.clear()

        for agent in AgentModel.select().order_by(AgentModel.name):
            self.agents_list.addItem(agent.name)
            self.available_agents_cb.addItem(agent.name, userData=agent.id)

        self.pipeline_selector.blockSignals(True)
        self.pipeline_selector.clear()
        for pipe in PipelineModel.select().order_by(PipelineModel.name):
            self.pipeline_selector.addItem(pipe.name, userData=pipe.id)
        self.pipeline_selector.blockSignals(False)

        if self.pipeline_selector.count() > 0:
            self.load_selected_pipeline()

    def clear_agent_form(self):
        self.agent_id = None
        self.agent_name_input.clear()
        self.agent_desc_input.clear()
        self.agent_prompt_input.clear()
        self.agents_list.clearSelection()

    def load_selected_agent(self, item):
        agent = AgentModel.get(AgentModel.name == item.text())
        self.agent_id = agent.id
        self.agent_name_input.setText(agent.name)
        self.agent_desc_input.setText(agent.description or "")
        self.agent_prompt_input.setPlainText(agent.system_prompt)

    def save_agent(self):
        name = self.agent_name_input.text().strip()
        desc = self.agent_desc_input.text().strip()
        prompt = self.agent_prompt_input.toPlainText().strip()

        if not name or not prompt:
            QMessageBox.warning(self, "Erreur", "Le nom et le prompt sont obligatoires.")
            return

        try:
            if self.agent_id:
                # Mise à jour
                agent = AgentModel.get_by_id(self.agent_id)
                agent.name = name
                agent.description = desc
                agent.system_prompt = prompt
                agent.save()
            else:
                # Création
                AgentModel.create(name=name, description=desc, system_prompt=prompt)

            QMessageBox.information(self, "Succès", "Agent sauvegardé avec succès.")
            self.refresh_ui()
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Erreur lors de la sauvegarde : {e}")

    # --- MÉTHODES PIPELINES ---
    def create_new_pipeline(self):
        # Pour faire simple sans popup complexe, on crée un pipeline générique
        count = PipelineModel.select().count() + 1
        pipe = PipelineModel.create(name=f"Nouveau Pipeline {count}", description="À configurer")
        self.refresh_ui()
        # Sélectionner le nouveau pipeline
        idx = self.pipeline_selector.findData(pipe.id)
        self.pipeline_selector.setCurrentIndex(idx)

    def load_selected_pipeline(self):
        self.steps_list.clear()
        pipe_id = self.pipeline_selector.currentData()
        if not pipe_id: return

        pipeline = PipelineModel.get_by_id(pipe_id)
        # On charge les étapes triées par ordre
        for step in pipeline.steps.order_by(PipelineStepModel.step_order):
            self.steps_list.addItem(f"{step.agent.name}")

    def add_agent_to_pipeline(self):
        agent_name = self.available_agents_cb.currentText()
        if agent_name:
            self.steps_list.addItem(agent_name)

    def move_step_up(self):
        row = self.steps_list.currentRow()
        if row > 0:
            item = self.steps_list.takeItem(row)
            self.steps_list.insertItem(row - 1, item)
            self.steps_list.setCurrentRow(row - 1)

    def move_step_down(self):
        row = self.steps_list.currentRow()
        if row < self.steps_list.count() - 1 and row != -1:
            item = self.steps_list.takeItem(row)
            self.steps_list.insertItem(row + 1, item)
            self.steps_list.setCurrentRow(row + 1)

    def remove_step(self):
        row = self.steps_list.currentRow()
        if row != -1:
            self.steps_list.takeItem(row)

    def save_pipeline_steps(self):
        pipe_id = self.pipeline_selector.currentData()
        if not pipe_id: return

        try:
            with db.atomic():
                pipeline = PipelineModel.get_by_id(pipe_id)

                # 1. On supprime les anciennes étapes
                PipelineStepModel.delete().where(PipelineStepModel.pipeline == pipeline).execute()

                # 2. On recrée les étapes dans l'ordre de la liste UI
                for i in range(self.steps_list.count()):
                    agent_name = self.steps_list.item(i).text()
                    agent = AgentModel.get(AgentModel.name == agent_name)
                    PipelineStepModel.create(
                        pipeline=pipeline,
                        agent=agent,
                        step_order=i + 1
                    )
            QMessageBox.information(self, "Succès", "L'ordre du pipeline a été mis à jour !")
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Erreur lors de la sauvegarde : {e}")