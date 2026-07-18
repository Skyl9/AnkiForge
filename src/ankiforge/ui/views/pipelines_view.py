import json
import logging

import qtawesome as qta
from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QAbstractItemView,
    QListWidgetItem,
    QFileDialog,
    QInputDialog,
)

from ankiforge.database.models import PipelineModel, PipelineStepModel, db, AgentModel
from ankiforge.ui.components.components import ActionButton, PrimaryButton, DangerButton, RoundedPanel
from ankiforge.ui.components.inputs import StyledComboBox
from ankiforge.ui.widgets.toast import show_toast

logger = logging.getLogger(__name__)


class PipelinesView(QWidget):
    """
    Pipelines management view.
    Allows assembling specialized agents into execution chains.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 20, 20, 20)

        # Center container with max width 800px
        self.center_container = QWidget()
        self.center_container.setMaximumWidth(800)
        self.center_layout = QVBoxLayout(self.center_container)
        self.center_layout.setContentsMargins(0, 0, 0, 0)

        self.main_layout.addWidget(self.center_container, 0, Qt.AlignmentFlag.AlignHCenter)

        self._build_pipelines_panel()

    def _build_pipelines_panel(self) -> None:
        pipelines_panel = RoundedPanel()
        pipelines_layout = QVBoxLayout(pipelines_panel)
        pipelines_layout.setContentsMargins(15, 15, 15, 15)

        pipe_header_layout = QHBoxLayout()
        lbl_pipelines = QLabel(self.tr("⚙️ PIPELINE ASSEMBLER"))
        lbl_pipelines.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px;")
        pipe_header_layout.addWidget(lbl_pipelines)
        pipe_header_layout.addStretch()

        self.btn_import_pipe = ActionButton("fa5s.folder-open", self.tr(" Import (.json)"))
        self.btn_export_pipe = ActionButton("fa5s.file-export", self.tr(" Export"))

        pipe_header_layout.addWidget(self.btn_import_pipe)
        pipe_header_layout.addWidget(self.btn_export_pipe)
        pipelines_layout.addLayout(pipe_header_layout)

        pipe_select_layout = QHBoxLayout()
        lbl_pipe_sel = QLabel(self.tr("Active Pipeline:"))
        lbl_pipe_sel.setStyleSheet("font-weight: bold; color: palette(text); font-size: 11px;")

        self.pipeline_selector = StyledComboBox()
        self.btn_new_pipeline = ActionButton("fa5s.plus", self.tr(" New"))
        self.btn_rename_pipeline = ActionButton("fa5s.pen", "")
        self.btn_rename_pipeline.setToolTip(self.tr("Rename the Pipeline"))
        self.btn_delete_pipeline = DangerButton(qta.icon("fa5s.trash", color="white"), "")
        self.btn_delete_pipeline.setToolTip(self.tr("Delete the Pipeline"))

        pipe_select_layout.addWidget(lbl_pipe_sel)
        pipe_select_layout.addWidget(self.pipeline_selector, stretch=1)
        pipe_select_layout.addWidget(self.btn_new_pipeline)
        pipe_select_layout.addWidget(self.btn_rename_pipeline)
        pipe_select_layout.addWidget(self.btn_delete_pipeline)
        pipelines_layout.addLayout(pipe_select_layout)

        lbl_chain = QLabel(self.tr("EXECUTION CHAIN (AGENT ORDER):"))
        lbl_chain.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 10px; letter-spacing: 1px; margin-top: 20px; margin-bottom: 5px;")
        pipelines_layout.addWidget(lbl_chain)

        add_step_layout = QHBoxLayout()
        self.available_agents_cb = StyledComboBox()
        self.btn_add_step = ActionButton("fa5s.plus", self.tr(" Ajouter un agent"))

        add_step_layout.addWidget(self.available_agents_cb, stretch=1)
        add_step_layout.addWidget(self.btn_add_step)
        pipelines_layout.addLayout(add_step_layout)

        self.steps_list = QListWidget()
        self.steps_list.setStyleSheet("QListWidget { border: none; background-color: palette(window); border-radius: 6px; }")
        self.steps_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.steps_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.steps_list.model().rowsMoved.connect(self._recalculate_step_numbers)
        pipelines_layout.addWidget(self.steps_list)

        step_ctrl_layout = QHBoxLayout()
        self.btn_step_remove = DangerButton(qta.icon("fa5s.times", color="white"), self.tr(" Remove step"))
        self.btn_save_pipeline = PrimaryButton(qta.icon("fa5s.save", color="white"), self.tr(" Sauvegarder"))

        step_ctrl_layout.addWidget(self.btn_step_remove)
        step_ctrl_layout.addStretch()
        step_ctrl_layout.addWidget(self.btn_save_pipeline)

        pipelines_layout.addLayout(step_ctrl_layout)
        self.center_layout.addWidget(pipelines_panel)

    def _connect_signals(self) -> None:
        self.btn_import_pipe.clicked.connect(self.import_pipeline)
        self.btn_export_pipe.clicked.connect(self.export_pipeline)
        self.pipeline_selector.currentIndexChanged.connect(self.load_selected_pipeline)
        self.btn_new_pipeline.clicked.connect(self.create_new_pipeline)
        self.btn_rename_pipeline.clicked.connect(self.rename_pipeline)
        self.btn_delete_pipeline.clicked.connect(self.delete_pipeline)

        self.btn_add_step.clicked.connect(self.add_agent_to_pipeline)
        self.btn_step_remove.clicked.connect(self.remove_step)
        self.btn_save_pipeline.clicked.connect(self.save_pipeline_steps)

    @Slot()
    def refresh_data(self) -> None:
        self.refresh_ui()

    @Slot()
    def refresh_ui(self) -> None:
        self.available_agents_cb.clear()

        for agent in AgentModel.select().order_by(AgentModel.name):
            self.available_agents_cb.addItem(agent.name, userData=agent.id)

        self.pipeline_selector.blockSignals(True)
        self.pipeline_selector.clear()
        for pipe in PipelineModel.select().order_by(PipelineModel.name):
            self.pipeline_selector.addItem(pipe.name, userData=pipe.id)
        self.pipeline_selector.blockSignals(False)

        if self.pipeline_selector.count() > 0:
            self.load_selected_pipeline()

    @Slot()
    def export_pipeline(self) -> None:
        pipe_id = self.pipeline_selector.currentData()
        if not pipe_id:
            QMessageBox.warning(self, self.tr("Error"), self.tr("No pipeline selected."))
            return

        pipeline = PipelineModel.get_by_id(pipe_id)

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

        path, _ = QFileDialog.getSaveFileName(self, self.tr("Export Pipeline"), self.tr("{0}.json").format(pipeline.name.replace(" ", "_")), self.tr("JSON Files (*.json)"))

        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(export_data, f, ensure_ascii=False, indent=4)
                logger.info(f"Pipeline '{pipeline.name}' exported to {path}")
                show_toast(self, self.tr("The Pipeline has been exported successfully!"))
            except Exception as e:
                logger.exception(f"Unable to export pipeline '{pipeline.name}'")
                QMessageBox.critical(self, self.tr("Error"), self.tr('Unable to export pipeline "{0}":').format(pipeline.name) + f"\n{e}")

    @Slot()
    def import_pipeline(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, self.tr("Import a Pipeline"), "", self.tr("JSON Files (*.json)"))
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            with db.atomic():
                base_name = data.get("name", self.tr("Imported Pipeline"))
                name = base_name
                counter = 1

                while PipelineModel.get_or_none(PipelineModel.name == name):
                    name = f"{base_name} ({counter})"
                    counter += 1

                new_pipe = PipelineModel.create(name=name, description=data.get("description", ""))

                for step_data in data.get("steps", []):
                    agent_name = step_data.get("agent_name", self.tr("Unknown Agent"))
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

            logger.info(f"Pipeline '{name}' imported successfully.")
            show_toast(self, self.tr('Pipeline "{0}" imported!').format(name))

        except Exception as e:
            logger.exception("Error while importing pipeline")
            QMessageBox.critical(self, self.tr("Import Error"), self.tr("The file is invalid or corrupted:\n{0}").format(str(e)))

    @Slot()
    def create_new_pipeline(self) -> None:
        count = PipelineModel.select().count() + 1
        pipe = PipelineModel.create(name=self.tr("New Pipeline {0}").format(count), description=self.tr("To be configured"))
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
            item = QListWidgetItem(f"[≡] {step.step_order}. Agent: {step.agent.name}")
            item.setData(Qt.ItemDataRole.UserRole, step.agent.name)
            self.steps_list.addItem(item)

    @Slot()
    def add_agent_to_pipeline(self) -> None:
        agent_name = self.available_agents_cb.currentText()
        if agent_name:
            next_num = self.steps_list.count() + 1
            item = QListWidgetItem(f"[≡] {next_num}. Agent: {agent_name}")
            item.setData(Qt.ItemDataRole.UserRole, agent_name)
            self.steps_list.addItem(item)

    @Slot()
    def _recalculate_step_numbers(self, *args, **kwargs) -> None:
        """Visually recalculates all numbers after movement."""
        for i in range(self.steps_list.count()):
            item = self.steps_list.item(i)
            agent_name = item.data(Qt.ItemDataRole.UserRole)
            item.setText(f"[≡] {i + 1}. Agent: {agent_name}")

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
            logger.info(f"Pipeline '{pipeline.name}' order updated.")
            show_toast(self, self.tr("Pipeline saved successfully!"))
        except Exception as e:
            logger.exception("Error while saving pipeline")
            QMessageBox.critical(self, self.tr("Error"), self.tr("Error during pipeline save:") + f"\n{e}")

    @Slot()
    def rename_pipeline(self) -> None:
        pipe_id = self.pipeline_selector.currentData()
        if not pipe_id:
            return

        pipeline = PipelineModel.get_by_id(pipe_id)
        new_name, ok = QInputDialog.getText(self, self.tr("Rename Pipeline"), self.tr("New name:"), text=pipeline.name)

        if ok and new_name.strip() and new_name.strip() != pipeline.name:
            try:
                pipeline.name = new_name.strip()
                pipeline.save()

                idx = self.pipeline_selector.currentIndex()
                self.pipeline_selector.setItemText(idx, pipeline.name)
                logger.info(f"Pipeline '{pipeline.name}' renamed.")
                show_toast(self, self.tr("Pipeline renamed successfully!"))
            except Exception as e:
                logger.exception(f"Unable to rename pipeline '{pipeline.name}'")
                QMessageBox.critical(self, self.tr("Error"), self.tr('Unable to rename pipeline "{0}":').format(pipeline.name) + f"\n{e}")

    @Slot()
    def delete_pipeline(self) -> None:
        pipe_id = self.pipeline_selector.currentData()
        if not pipe_id:
            return

        pipeline = PipelineModel.get_by_id(pipe_id)
        reply = QMessageBox.question(
            self,
            self.tr("Delete Pipeline"),
            self.tr('Do you really want to delete the pipeline "{0}"?\nThis will not delete the agents, only the execution order.').format(pipeline.name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                pipeline.delete_instance(recursive=True)

                idx = self.pipeline_selector.currentIndex()
                self.pipeline_selector.removeItem(idx)

                if self.pipeline_selector.count() == 0:
                    self.steps_list.clear()

                logger.info(f"Pipeline '{pipeline.name}' deleted.")
                show_toast(self, self.tr("Pipeline deleted!"))
            except Exception as e:
                logger.exception(f"Unable to delete pipeline '{pipeline.name}'")
                QMessageBox.critical(self, self.tr("Error"), self.tr('Unable to delete pipeline "{0}":').format(pipeline.name) + f"\n{e}")
