import json
import logging
from typing import Optional

import qtawesome as qta
from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QListWidget,
    QSplitter,
    QMessageBox,
    QComboBox,
    QAbstractItemView,
    QListWidgetItem,
    QFileDialog,
    QInputDialog,
)

from ankiforge.database.models import PipelineModel, PipelineStepModel, db, AgentModel
from ankiforge.ui.components.components import ActionButton, PrimaryButton, DangerButton, RoundedPanel
from ankiforge.ui.widgets.toast import show_toast

logger = logging.getLogger(__name__)


class AgentsTab(QWidget):
    """
    Onglet de gestion des Agents IA et des Pipelines.
    Permet de créer, modifier et assembler des agents spécialisés en chaînes d'exécution.
    """

    def __init__(self) -> None:
        """Initialise l'onglet des agents et pipelines."""
        super().__init__()
        self.agent_id: Optional[int] = None

        self._setup_ui()
        self._connect_signals()

        self.refresh_ui()

    def _setup_ui(self) -> None:
        """Construit et organise les layouts et widgets principaux."""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(20)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setHandleWidth(10)

        self._build_agents_panel()
        self._build_pipelines_panel()

        self.main_splitter.setSizes([500, 500])
        self.main_layout.addWidget(self.main_splitter)

    def _build_agents_panel(self) -> None:
        """Construit le panneau de création et d'édition des agents individuels."""
        agents_panel = RoundedPanel()
        agents_layout = QVBoxLayout(agents_panel)
        agents_layout.setContentsMargins(15, 15, 15, 15)

        lbl_agents = QLabel("🤖 LABORATOIRE DES AGENTS")
        lbl_agents.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px;")
        agents_layout.addWidget(lbl_agents)

        self.agent_top_splitter = QSplitter(Qt.Orientation.Vertical)
        self.agent_top_splitter.setHandleWidth(10)

        # Liste des agents
        self.agents_list = QListWidget()
        self.agents_list.setStyleSheet("QListWidget { border: none; background: transparent; }")
        self.agent_top_splitter.addWidget(self.agents_list)

        # Formulaire d'édition
        form_widget = QWidget()
        form_layout = QVBoxLayout(form_widget)
        form_layout.setContentsMargins(0, 10, 0, 0)

        lbl_edit = QLabel("ÉDITION DE L'AGENT :")
        lbl_edit.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 10px; letter-spacing: 1px; margin-bottom: 5px;")
        form_layout.addWidget(lbl_edit)

        name_desc_layout = QHBoxLayout()

        name_layout = QVBoxLayout()
        lbl_name = QLabel("Nom :")
        lbl_name.setStyleSheet("font-weight: bold; color: palette(text); font-size: 11px;")
        self.agent_name_input = QLineEdit()
        self.agent_name_input.setPlaceholderText("ex: Linteur Qualité")
        name_layout.addWidget(lbl_name)
        name_layout.addWidget(self.agent_name_input)

        desc_layout = QVBoxLayout()
        lbl_desc = QLabel("Description :")
        lbl_desc.setStyleSheet("font-weight: bold; color: palette(text); font-size: 11px;")
        self.agent_desc_input = QLineEdit()
        self.agent_desc_input.setPlaceholderText("Rôle de cet agent...")
        desc_layout.addWidget(lbl_desc)
        desc_layout.addWidget(self.agent_desc_input)

        name_desc_layout.addLayout(name_layout)
        name_desc_layout.addLayout(desc_layout)
        form_layout.addLayout(name_desc_layout)

        lbl_prompt = QLabel("Prompt Système (Jinja2) :")
        lbl_prompt.setStyleSheet("font-weight: bold; color: palette(text); font-size: 11px; margin-top: 10px;")
        form_layout.addWidget(lbl_prompt)

        self.agent_prompt_input = QTextEdit()
        self.agent_prompt_input.setPlaceholderText("Tu es un expert en... Tes variables sont {{Front}} et {{Back}}...")
        self.agent_prompt_input.setStyleSheet("font-family: monospace;")
        form_layout.addWidget(self.agent_prompt_input)

        lbl_format = QLabel("Format de réponse de l'IA :")
        lbl_format.setStyleSheet("font-weight: bold; color: palette(text); font-size: 11px")
        form_layout.addWidget(lbl_format)

        self.cb_output_format = QComboBox()
        self.cb_output_format.addItem(" JSON Strict (Agent final pour Anki)", userData="json")
        self.cb_output_format.addItem(" Texte Libre / Markdown (Agent intermédiaire)", userData="text")
        form_layout.addWidget(self.cb_output_format)

        btn_layout_agent = QHBoxLayout()
        self.btn_new_agent = ActionButton("fa5s.plus", " Nouvel Agent")
        self.btn_delete_agent = DangerButton(qta.icon("fa5s.trash", color="white"), " Supprimer")
        self.btn_save_agent = PrimaryButton(qta.icon("fa5s.save", color="white"), " Sauvegarder l'Agent")

        btn_layout_agent.addWidget(self.btn_new_agent)
        btn_layout_agent.addStretch()
        btn_layout_agent.addWidget(self.btn_delete_agent)
        btn_layout_agent.addWidget(self.btn_save_agent)

        form_layout.addLayout(btn_layout_agent)
        self.agent_top_splitter.addWidget(form_widget)
        self.agent_top_splitter.setSizes([200, 400])

        agents_layout.addWidget(self.agent_top_splitter)
        self.main_splitter.addWidget(agents_panel)

    def _build_pipelines_panel(self) -> None:
        """Construit le panneau d'assemblage et de configuration des pipelines."""
        pipelines_panel = RoundedPanel()
        pipelines_layout = QVBoxLayout(pipelines_panel)
        pipelines_layout.setContentsMargins(15, 15, 15, 15)

        pipe_header_layout = QHBoxLayout()
        lbl_pipelines = QLabel("⚙️ ASSEMBLEUR DE PIPELINES")
        lbl_pipelines.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px;")
        pipe_header_layout.addWidget(lbl_pipelines)
        pipe_header_layout.addStretch()

        self.btn_import_pipe = ActionButton("fa5s.folder-open", " Importer (.json)")
        self.btn_export_pipe = ActionButton("fa5s.file-export", " Exporter")

        pipe_header_layout.addWidget(self.btn_import_pipe)
        pipe_header_layout.addWidget(self.btn_export_pipe)
        pipelines_layout.addLayout(pipe_header_layout)

        pipe_select_layout = QHBoxLayout()
        lbl_pipe_sel = QLabel("Pipeline Actif :")
        lbl_pipe_sel.setStyleSheet("font-weight: bold; color: palette(text); font-size: 11px;")

        self.pipeline_selector = QComboBox()
        self.btn_new_pipeline = ActionButton("fa5s.plus", " Nouveau")
        self.btn_rename_pipeline = ActionButton("fa5s.pen", "")
        self.btn_rename_pipeline.setToolTip("Renommer le Pipeline")
        self.btn_delete_pipeline = DangerButton(qta.icon("fa5s.trash", color="white"), "")
        self.btn_delete_pipeline.setToolTip("Supprimer le Pipeline")

        pipe_select_layout.addWidget(lbl_pipe_sel)
        pipe_select_layout.addWidget(self.pipeline_selector, stretch=1)
        pipe_select_layout.addWidget(self.btn_new_pipeline)
        pipe_select_layout.addWidget(self.btn_rename_pipeline)
        pipe_select_layout.addWidget(self.btn_delete_pipeline)
        pipelines_layout.addLayout(pipe_select_layout)

        lbl_chain = QLabel("CHAÎNE D'EXÉCUTION (ORDRE DES AGENTS) :")
        lbl_chain.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 10px; letter-spacing: 1px; margin-top: 20px; margin-bottom: 5px;")
        pipelines_layout.addWidget(lbl_chain)

        add_step_layout = QHBoxLayout()
        self.available_agents_cb = QComboBox()
        self.btn_add_step = ActionButton("fa5s.arrow-down", " Ajouter à la chaîne")

        add_step_layout.addWidget(self.available_agents_cb, stretch=1)
        add_step_layout.addWidget(self.btn_add_step)
        pipelines_layout.addLayout(add_step_layout)

        self.steps_list = QListWidget()
        self.steps_list.setStyleSheet("QListWidget { border: none; background-color: palette(window); border-radius: 6px; }")
        self.steps_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        pipelines_layout.addWidget(self.steps_list)

        step_ctrl_layout = QHBoxLayout()
        self.btn_step_up = ActionButton("fa5s.arrow-up", "")
        self.btn_step_down = ActionButton("fa5s.arrow-down", "")
        self.btn_step_remove = DangerButton(qta.icon("fa5s.times", color="white"), " Retirer l'étape")
        self.btn_save_pipeline = PrimaryButton(qta.icon("fa5s.save", color="white"), " Sauvegarder le Pipeline")

        step_ctrl_layout.addWidget(self.btn_step_up)
        step_ctrl_layout.addWidget(self.btn_step_down)
        step_ctrl_layout.addWidget(self.btn_step_remove)
        step_ctrl_layout.addStretch()
        step_ctrl_layout.addWidget(self.btn_save_pipeline)

        pipelines_layout.addLayout(step_ctrl_layout)
        self.main_splitter.addWidget(pipelines_panel)

    def _connect_signals(self) -> None:
        """Centralise la connexion des signaux aux slots de l'interface."""
        # Agents
        self.agents_list.itemClicked.connect(self.load_selected_agent)
        self.btn_new_agent.clicked.connect(self.clear_agent_form)
        self.btn_delete_agent.clicked.connect(self.delete_agent)
        self.btn_save_agent.clicked.connect(self.save_agent)

        # Pipelines
        self.btn_import_pipe.clicked.connect(self.import_pipeline)
        self.btn_export_pipe.clicked.connect(self.export_pipeline)
        self.pipeline_selector.currentIndexChanged.connect(self.load_selected_pipeline)
        self.btn_new_pipeline.clicked.connect(self.create_new_pipeline)
        self.btn_rename_pipeline.clicked.connect(self.rename_pipeline)
        self.btn_delete_pipeline.clicked.connect(self.delete_pipeline)

        # Étapes (Steps)
        self.btn_add_step.clicked.connect(self.add_agent_to_pipeline)
        self.btn_step_up.clicked.connect(self.move_step_up)
        self.btn_step_down.clicked.connect(self.move_step_down)
        self.btn_step_remove.clicked.connect(self.remove_step)
        self.btn_save_pipeline.clicked.connect(self.save_pipeline_steps)

    @Slot()
    def refresh_data(self) -> None:
        """Contrat MainWindow : Rafraîchit les agents et pipelines."""
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
        export_data = {"name": pipeline.name, "description": pipeline.description, "steps": []}

        for step in pipeline.steps.order_by(PipelineStepModel.step_order):
            export_data["steps"].append(
                {
                    "order": step.step_order,
                    "agent_name": step.agent.name,
                    "agent_desc": step.agent.description,
                    "agent_prompt": step.agent.system_prompt,
                }
            )

        # Ouverture de la boîte de dialogue de sauvegarde
        path, _ = QFileDialog.getSaveFileName(self, "Exporter le Pipeline", f"{pipeline.name.replace(' ', '_')}.json", "Fichiers JSON (*.json)")

        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(export_data, f, ensure_ascii=False, indent=4)
                logger.info(f"Pipeline '{pipeline.name}' exporté vers {path}")
                show_toast(self, "Le Pipeline a été exporté avec succès !")
            except Exception as e:
                logger.exception(f"Impossible d'exporter le pipeline '{pipeline.name}' :")
                QMessageBox.critical(self, "Erreur", f"Impossible d'exporter le fichier : {e}")

    @Slot()
    def import_pipeline(self) -> None:
        """Importe un pipeline et ses agents dépendants depuis un fichier JSON."""
        path, _ = QFileDialog.getOpenFileName(self, "Importer un Pipeline", "", "Fichiers JSON (*.json)")
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            with db.atomic():
                base_name = data.get("name", "Pipeline Importé")
                name = base_name
                counter = 1

                # Gestion de la collision des noms de pipeline
                while PipelineModel.get_or_none(PipelineModel.name == name):
                    name = f"{base_name} ({counter})"
                    counter += 1

                new_pipe = PipelineModel.create(name=name, description=data.get("description", ""))

                for step_data in data.get("steps", []):
                    agent_name = step_data.get("agent_name", "Agent Inconnu")
                    agent = AgentModel.get_or_none(AgentModel.name == agent_name)

                    if not agent:
                        agent = AgentModel.create(
                            name=agent_name,
                            description=step_data.get("agent_desc", ""),
                            system_prompt=step_data.get("agent_prompt", ""),
                        )

                    PipelineStepModel.create(pipeline=new_pipe, agent=agent, step_order=step_data.get("order", 1))

            self.refresh_ui()

            idx = self.pipeline_selector.findData(new_pipe.id)
            if idx >= 0:
                self.pipeline_selector.setCurrentIndex(idx)

            logger.info(f"Pipeline '{name}' importé avec succès.")
            show_toast(self, f"Pipeline '{name}' importé !")

        except Exception as e:
            logger.exception("Erreur lors de l'importation du pipeline :")
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
            QMessageBox.warning(self, "Erreur", "Le nom et le prompt sont obligatoires.")
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
            logger.info(f"Agent '{name}' sauvegardé.")
            show_toast(self, "Agent sauvegardé !")
            self.refresh_ui()
        except Exception as e:
            logger.exception(f"Erreur lors de la sauvegarde de l'agent '{name}' :")
            QMessageBox.critical(self, "Erreur", f"Erreur lors de la sauvegarde : {e}")

    @Slot()
    def delete_agent(self) -> None:
        if not self.agent_id:
            QMessageBox.warning(self, "Erreur", "Veuillez sélectionner un agent avant de le supprimer.")
            return

        name = self.agent_name_input.text().strip()

        reply = QMessageBox.question(
            self,
            "Confirmation",
            f"Voulez-vous vraiment supprimer l'agent '{name}' ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                agent = AgentModel.get_by_id(self.agent_id)
                agent.delete_instance(recursive=True)

                logger.info(f"Agent '{name}' supprimé avec succès.")
                show_toast(self, "Agent détruit avec succès")

                self.clear_agent_form()
                self.refresh_ui()

            except Exception as e:
                logger.exception(f"Impossible de supprimer l'agent '{name}' :")
                QMessageBox.critical(self, "Erreur", f"Impossible de supprimer l'agent : {e}")

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
            item = QListWidgetItem(f"{step.step_order}. {step.agent.name}")
            item.setData(Qt.ItemDataRole.UserRole, step.agent.name)
            self.steps_list.addItem(item)

    @Slot()
    def add_agent_to_pipeline(self) -> None:
        agent_name = self.available_agents_cb.currentText()
        if agent_name:
            next_num = self.steps_list.count() + 1
            item = QListWidgetItem(f"{next_num}. {agent_name}")
            item.setData(Qt.ItemDataRole.UserRole, agent_name)
            self.steps_list.addItem(item)

    def _recalculate_step_numbers(self):
        """Recalcule visuellement tous les numéros après un mouvement."""
        for i in range(self.steps_list.count()):
            item = self.steps_list.item(i)
            agent_name = item.data(Qt.ItemDataRole.UserRole)
            item.setText(f"{i + 1}. {agent_name}")

    @Slot()
    def move_step_up(self) -> None:
        row = self.steps_list.currentRow()
        if row > 0:
            item = self.steps_list.takeItem(row)
            self.steps_list.insertItem(row - 1, item)
            self.steps_list.setCurrentRow(row - 1)
            self._recalculate_step_numbers()

    @Slot()
    def move_step_down(self) -> None:
        row = self.steps_list.currentRow()
        if row < self.steps_list.count() - 1 and row != -1:
            item = self.steps_list.takeItem(row)
            self.steps_list.insertItem(row + 1, item)
            self.steps_list.setCurrentRow(row + 1)
            self._recalculate_step_numbers()

    @Slot()
    def remove_step(self) -> None:
        row = self.steps_list.currentRow()
        if row != -1:
            self.steps_list.takeItem(row)
            self._recalculate_step_numbers()

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
                    agent_name = self.steps_list.item(i).data(Qt.ItemDataRole.UserRole)
                    agent = AgentModel.get(AgentModel.name == agent_name)
                    PipelineStepModel.create(pipeline=pipeline, agent=agent, step_order=i + 1)
            logger.info(f"Ordre du pipeline '{pipeline.name}' mis à jour.")
            QMessageBox.information(self, "Succès", "L'ordre du pipeline a été mis à jour !")
        except Exception as e:
            logger.exception("Erreur lors de la sauvegarde du pipeline :")
            QMessageBox.critical(self, "Erreur", f"Erreur lors de la sauvegarde : {e}")

    @Slot()
    def rename_pipeline(self) -> None:
        pipe_id = self.pipeline_selector.currentData()
        if not pipe_id:
            return

        pipeline = PipelineModel.get_by_id(pipe_id)
        new_name, ok = QInputDialog.getText(self, "Renommer Pipeline", "Nouveau nom :", text=pipeline.name)

        if ok and new_name.strip() and new_name.strip() != pipeline.name:
            try:
                pipeline.name = new_name.strip()
                pipeline.save()

                # Mise à jour silencieuse de la combobox
                idx = self.pipeline_selector.currentIndex()
                self.pipeline_selector.setItemText(idx, pipeline.name)
                logger.info(f"Pipeline '{pipeline.name}' renommé.")
                show_toast(self, "Pipeline renommé avec succès !")
            except Exception as e:
                logger.exception(f"Impossible de renommer le pipeline '{pipeline.name}' :")
                QMessageBox.critical(self, "Erreur", f"Impossible de renommer :\n{e}")

    @Slot()
    def delete_pipeline(self) -> None:
        pipe_id = self.pipeline_selector.currentData()
        if not pipe_id:
            return

        pipeline = PipelineModel.get_by_id(pipe_id)
        reply = QMessageBox.question(
            self,
            "Supprimer le Pipeline",
            f"Voulez-vous vraiment supprimer le pipeline '{pipeline.name}' ?\nCela n'effacera pas les agents, juste l'ordre d'exécution.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                # La suppression en cascade effacera les PipelineStepModel associés
                pipeline.delete_instance(recursive=True)

                # Retire de l'interface
                idx = self.pipeline_selector.currentIndex()
                self.pipeline_selector.removeItem(idx)

                if self.pipeline_selector.count() == 0:
                    self.steps_list.clear()

                logger.info(f"Pipeline '{pipeline.name}' supprimé.")
                show_toast(self, "Pipeline supprimé !")
            except Exception as e:
                logger.exception(f"Impossible de supprimer le pipeline '{pipeline.name}' :")
                QMessageBox.critical(self, "Erreur", f"Impossible de supprimer :\n{e}")
