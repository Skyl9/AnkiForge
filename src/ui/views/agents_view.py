import json
from typing import Optional

import qtawesome as qta
from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QLineEdit, QTextEdit, QPushButton, QListWidget,
                               QSplitter, QMessageBox, QGroupBox, QComboBox,
                               QAbstractItemView, QListWidgetItem, QFileDialog)

from src.database.models import db, AgentModel, PipelineModel, PipelineStepModel


class AgentsTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)

        # Standard Qt6 : Qt.Orientation.Horizontal
        main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # ==========================================
        # 🧪 PARTIE GAUCHE : LABORATOIRE DES AGENTS
        # ==========================================
        agents_widget = QWidget()
        agents_layout = QVBoxLayout(agents_widget)
        agents_layout.addWidget(QLabel("<h2>🤖 Laboratoire des Agents</h2>"))

        self.agents_list = QListWidget()
        self.agents_list.itemClicked.connect(self.load_selected_agent)
        agents_layout.addWidget(self.agents_list)

        self.agent_id: Optional[int] = None

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

        btn_layout_agent = QHBoxLayout()
        self.btn_new_agent = QPushButton(qta.icon('fa5s.plus'), " Nouvel Agent")
        self.btn_new_agent.clicked.connect(self.clear_agent_form)

        self.btn_save_agent = QPushButton(qta.icon('fa5s.save', color='white'), " Sauvegarder l'Agent")
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

        pipe_header = QHBoxLayout()
        self.pipeline_selector = QComboBox()
        self.pipeline_selector.currentIndexChanged.connect(self.load_selected_pipeline)

        pipe_header.addWidget(QLabel("<b>Pipeline :</b>"))
        pipe_header.addWidget(self.pipeline_selector, stretch=1)

        self.btn_new_pipeline = QPushButton(qta.icon('fa5s.plus'), " Nouveau")
        self.btn_new_pipeline.clicked.connect(self.create_new_pipeline)
        pipe_header.addWidget(self.btn_new_pipeline)
        pipelines_layout.addLayout(pipe_header)

        # BOUTONS IMPORT / EXPORT
        export_import_layout = QHBoxLayout()

        self.btn_import_pipe = QPushButton(qta.icon('fa5s.folder-open'), " Importer (.json)")
        self.btn_import_pipe.clicked.connect(self.import_pipeline)

        self.btn_export_pipe = QPushButton(qta.icon('fa5s.file-export'), " Exporter")
        self.btn_export_pipe.clicked.connect(self.export_pipeline)

        export_import_layout.addWidget(self.btn_import_pipe)
        export_import_layout.addWidget(self.btn_export_pipe)
        pipelines_layout.addLayout(export_import_layout)

        chain_group = QGroupBox("Chaîne d'exécution (Ordre des Agents)")
        chain_layout = QVBoxLayout(chain_group)

        add_step_layout = QHBoxLayout()
        self.available_agents_cb = QComboBox()
        self.btn_add_step = QPushButton(qta.icon('fa5s.arrow-down'), " Ajouter à la chaîne")
        self.btn_add_step.clicked.connect(self.add_agent_to_pipeline)
        add_step_layout.addWidget(self.available_agents_cb, stretch=1)
        add_step_layout.addWidget(self.btn_add_step)
        chain_layout.addLayout(add_step_layout)

        self.steps_list = QListWidget()
        # Standard Qt6 : QAbstractItemView.SelectionMode
        self.steps_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        chain_layout.addWidget(self.steps_list)

        step_ctrl_layout = QHBoxLayout()
        self.btn_step_up = QPushButton(qta.icon('fa5s.arrow-up'), " Monter")
        self.btn_step_up.clicked.connect(self.move_step_up)

        self.btn_step_down = QPushButton(qta.icon('fa5s.arrow-down'), " Descendre")
        self.btn_step_down.clicked.connect(self.move_step_down)

        self.btn_step_remove = QPushButton(qta.icon('fa5s.times', color='#F44336'), " Retirer")
        self.btn_step_remove.clicked.connect(self.remove_step)

        step_ctrl_layout.addWidget(self.btn_step_up)
        step_ctrl_layout.addWidget(self.btn_step_down)
        step_ctrl_layout.addWidget(self.btn_step_remove)
        chain_layout.addLayout(step_ctrl_layout)

        self.btn_save_pipeline = QPushButton(qta.icon('fa5s.save', color='white'), " Sauvegarder le Pipeline")
        self.btn_save_pipeline.setStyleSheet(
            "background-color: #2196F3; color: white; font-weight: bold; padding: 8px;")
        self.btn_save_pipeline.clicked.connect(self.save_pipeline_steps)
        chain_layout.addWidget(self.btn_save_pipeline)

        pipelines_layout.addWidget(chain_group)

        main_splitter.addWidget(agents_widget)
        main_splitter.addWidget(pipelines_widget)
        main_splitter.setSizes([500, 500])

        layout.addWidget(main_splitter)
        self.refresh_ui()
    @Slot()
    def export_pipeline(self) -> None:
        """Exporte le pipeline sélectionné et tous ses agents dans un fichier JSON."""
        pipe_id = self.pipeline_selector.currentData()
        if not pipe_id:
            QMessageBox.warning(self, "Erreur", "Aucun pipeline sélectionné.")
            return

        pipeline = PipelineModel.get_by_id(pipe_id)

        # On construit le dictionnaire de données
        export_data = {
            "name": pipeline.name,
            "description": pipeline.description,
            "steps": []
        }

        for step in pipeline.steps.order_by(PipelineStepModel.step_order):
            export_data["steps"].append({
                "order": step.step_order,
                "agent_name": step.agent.name,
                "agent_desc": step.agent.description,
                "agent_prompt": step.agent.system_prompt
            })

        # Ouverture de la boîte de dialogue de sauvegarde
        path, _ = QFileDialog.getSaveFileName(self, "Exporter le Pipeline", f"{pipeline.name.replace(' ', '_')}.json",
                                              "Fichiers JSON (*.json)")

        if path:
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(export_data, f, ensure_ascii=False, indent=4)
                QMessageBox.information(self, "Succès", "Le Pipeline a été exporté avec succès !")
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Impossible d'exporter le fichier : {e}")

    @Slot()
    def import_pipeline(self) -> None:
        """Importe un pipeline depuis un fichier JSON et le sauvegarde en base de données."""
        path, _ = QFileDialog.getOpenFileName(self, "Importer un Pipeline", "", "Fichiers JSON (*.json)")

        if not path:
            return

        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            with db.atomic():  # Transaction sécurisée
                # 1. Gestion des doublons de nom de pipeline
                base_name = data.get("name", "Pipeline Importé")
                name = base_name
                counter = 1
                while PipelineModel.get_or_none(PipelineModel.name == name):
                    name = f"{base_name} ({counter})"
                    counter += 1

                new_pipe = PipelineModel.create(name=name, description=data.get("description", ""))

                # 2. Création ou récupération des agents
                for step_data in data.get("steps", []):
                    agent_name = step_data.get("agent_name", "Agent Inconnu")

                    # On vérifie si un agent avec le même nom existe déjà
                    agent = AgentModel.get_or_none(AgentModel.name == agent_name)

                    if not agent:
                        # S'il n'existe pas, on le crée !
                        agent = AgentModel.create(
                            name=agent_name,
                            description=step_data.get("agent_desc", ""),
                            system_prompt=step_data.get("agent_prompt", "")
                        )

                    # 3. On lie l'agent au nouveau pipeline
                    PipelineStepModel.create(
                        pipeline=new_pipe,
                        agent=agent,
                        step_order=step_data.get("order", 1)
                    )

            self.refresh_ui()

            # On sélectionne automatiquement le pipeline fraîchement importé
            idx = self.pipeline_selector.findData(new_pipe.id)
            if idx >= 0:
                self.pipeline_selector.setCurrentIndex(idx)

            QMessageBox.information(self, "Succès", f"Le Pipeline '{name}' a été importé avec succès !")

        except Exception as e:
            QMessageBox.critical(self, "Erreur d'import", f"Le fichier est invalide ou corrompu :\n{e}")

    @Slot()
    def refresh_ui(self) -> None:
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
    @Slot()
    def clear_agent_form(self) -> None:
        self.agent_id = None
        self.agent_name_input.clear()
        self.agent_desc_input.clear()
        self.agent_prompt_input.clear()
        self.agents_list.clearSelection()
    @Slot(QListWidgetItem)
    def load_selected_agent(self, item: QListWidgetItem) -> None:
        agent = AgentModel.get(AgentModel.name == item.text())
        self.agent_id = agent.id
        self.agent_name_input.setText(agent.name)
        self.agent_desc_input.setText(agent.description or "")
        self.agent_prompt_input.setPlainText(agent.system_prompt)

    @Slot()
    def save_agent(self) -> None:
        name = self.agent_name_input.text().strip()
        desc = self.agent_desc_input.text().strip()
        prompt = self.agent_prompt_input.toPlainText().strip()

        if not name or not prompt:
            QMessageBox.warning(self, "Erreur", "Le nom et le prompt sont obligatoires.")
            return

        try:
            if self.agent_id:
                agent = AgentModel.get_by_id(self.agent_id)
                agent.name = name
                agent.description = desc
                agent.system_prompt = prompt
                agent.save()
            else:
                AgentModel.create(name=name, description=desc, system_prompt=prompt)

            QMessageBox.information(self, "Succès", "Agent sauvegardé avec succès.")
            self.refresh_ui()
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Erreur lors de la sauvegarde : {e}")
    @Slot()
    def create_new_pipeline(self) -> None:
        count = PipelineModel.select().count() + 1
        pipe = PipelineModel.create(name=f"Nouveau Pipeline {count}", description="À configurer")
        self.refresh_ui()
        idx = self.pipeline_selector.findData(pipe.id)
        self.pipeline_selector.setCurrentIndex(idx)
    @Slot()
    def load_selected_pipeline(self) -> None:
        self.steps_list.clear()
        pipe_id = self.pipeline_selector.currentData()
        if not pipe_id:
            return

        pipeline = PipelineModel.get_by_id(pipe_id)
        for step in pipeline.steps.order_by(PipelineStepModel.step_order):
            self.steps_list.addItem(f"{step.agent.name}")
    @Slot()
    def add_agent_to_pipeline(self) -> None:
        agent_name = self.available_agents_cb.currentText()
        if agent_name:
            self.steps_list.addItem(agent_name)
    @Slot()
    def move_step_up(self) -> None:
        row = self.steps_list.currentRow()
        if row > 0:
            item = self.steps_list.takeItem(row)
            self.steps_list.insertItem(row - 1, item)
            self.steps_list.setCurrentRow(row - 1)
    @Slot()
    def move_step_down(self) -> None:
        row = self.steps_list.currentRow()
        if row < self.steps_list.count() - 1 and row != -1:
            item = self.steps_list.takeItem(row)
            self.steps_list.insertItem(row + 1, item)
            self.steps_list.setCurrentRow(row + 1)
    @Slot()
    def remove_step(self) -> None:
        row = self.steps_list.currentRow()
        if row != -1:
            self.steps_list.takeItem(row)
    @Slot()
    def save_pipeline_steps(self) -> None:
        pipe_id = self.pipeline_selector.currentData()
        if not pipe_id:
            return

        try:
            with db.atomic():
                pipeline = PipelineModel.get_by_id(pipe_id)
                PipelineStepModel.delete().where(PipelineStepModel.pipeline == pipeline).execute()

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
