"""
Vue Pipelines (Éditeur de Chaînes d'Agents) — 100% Conforme à la Maquette concept_ide.
- Sélecteur de Pipeline actif avec gestion (Nouveau / Supprimer).
- Liste d'étapes visuelles réordonnables (PipelineStepModel & AgentModel).
- Ajout dynamique d'agents à la chaîne et sauvegarde atomique en base Peewee.
"""

import logging
from typing import Any, Optional

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import AgentModel, PipelineModel, PipelineStepModel, db
from ankiforge.ui.components import (
    Badge,
    DangerButton,
    IconButton,
    IdePanel,
    PrimaryButton,
    SecondaryButton,
    StyledComboBox,
)
from ankiforge.ui.theme import DesignTokens, apply_shadow
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class PipelineStepRowWidget(QFrame):
    """Widget personnalisé représentant une étape de pipeline avec contrôles."""

    def __init__(self, order: int, agent_name: str, format_str: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: #1a1d24;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 4px 8px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(10)

        # Handle d'entraînement / déplacement
        handle_lbl = QLabel()
        handle_lbl.setPixmap(load_phosphor_icon("ph.dots-six-vertical", color=DesignTokens.TEXT_MUTED).pixmap(16, 16))
        layout.addWidget(handle_lbl)

        # Titre et numéro de l'étape
        self.title_lbl = QLabel(f"<b>{order}.</b> {agent_name}")
        self.title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 13px; border: none;")
        layout.addWidget(self.title_lbl)

        # Badge de format
        badge = Badge(format_str.upper(), variant="outline", color=DesignTokens.COLOR_PURPLE)
        layout.addWidget(badge)

        layout.addStretch()

        # Boutons Monter / Descendre / Supprimer
        self.btn_up = IconButton("ph.caret-up", tooltip="Monter d'un rang", size=18)
        self.btn_down = IconButton("ph.caret-down", tooltip="Descendre d'un rang", size=18)
        self.btn_delete = IconButton("ph.trash", tooltip="Retirer du pipeline", size=18)

        layout.addWidget(self.btn_up)
        layout.addWidget(self.btn_down)
        layout.addWidget(self.btn_delete)


class PipelinesView(QWidget):
    """
    Vue Pipelines de Génération — 100% Conforme à la Maquette concept_ide.
    """

    def __init__(self, ai_manager: Optional[Any] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager
        self._current_pipeline: Optional[PipelineModel] = None
        self.current_steps: list[AgentModel] = []

        self._setup_ui()
        self._connect_signals()
        self.refresh_data()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)

        # Container principal centré (max-width: 820px)
        self.panel_wrapper = QWidget()
        self.panel_wrapper.setMaximumWidth(840)

        wrapper_layout = QVBoxLayout(self.panel_wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)

        self.pipeline_panel = IdePanel(detachable=True)

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setSpacing(16)

        # Top Control Row : Sélecteur de Pipeline + Boutons Nouveau / Supprimer
        pipeline_sel_row = QHBoxLayout()
        pipeline_sel_row.setSpacing(10)

        lbl_pipe = QLabel("PIPELINE ACTIF :")
        lbl_pipe.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold; letter-spacing: 0.5px;")
        pipeline_sel_row.addWidget(lbl_pipe)

        self.pipeline_combo = StyledComboBox()
        self.pipeline_combo.setMinimumWidth(220)
        pipeline_sel_row.addWidget(self.pipeline_combo, 1)

        self.btn_new_pipeline = SecondaryButton("Nouveau Pipeline")
        self.btn_new_pipeline.setIcon(load_phosphor_icon("ph.plus", color=DesignTokens.TEXT_PRIMARY))
        pipeline_sel_row.addWidget(self.btn_new_pipeline)

        self.btn_del_pipeline = DangerButton("Supprimer", ghost=True)
        self.btn_del_pipeline.setIcon(load_phosphor_icon("ph.trash", color=DesignTokens.COLOR_RED))
        pipeline_sel_row.addWidget(self.btn_del_pipeline)

        content_layout.addLayout(pipeline_sel_row)

        # Zone d'affichage des étapes (Step list area)
        lbl_steps = QLabel("ÉTAPES DE LA CHAÎNE D'AGENTS :")
        lbl_steps.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px; margin-top: 6px;")
        content_layout.addWidget(lbl_steps)

        self.steps_list = QListWidget()
        self.steps_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.steps_list.setMinimumHeight(240)
        self.steps_list.setStyleSheet(f"""
            QListWidget {{
                background-color: #111318;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 8px;
            }}
            QListWidget::item {{
                margin-bottom: 6px;
                border: none;
            }}
        """)
        apply_shadow(self.steps_list, blur=12, offset_y=2)
        content_layout.addWidget(self.steps_list, 1)

        # Bottom Toolbar : Ajouter un agent & Sauvegarder le Pipeline
        add_agent_row = QHBoxLayout()
        add_agent_row.setSpacing(10)

        self.agent_combo = StyledComboBox()
        self.agent_combo.setMinimumWidth(240)
        add_agent_row.addWidget(self.agent_combo, 1)

        self.btn_add_agent = SecondaryButton("Ajouter à la chaîne")
        self.btn_add_agent.setIcon(load_phosphor_icon("ph.plus", color=DesignTokens.TEXT_PRIMARY))
        add_agent_row.addWidget(self.btn_add_agent)

        self.btn_save_pipeline = PrimaryButton("Sauvegarder Pipeline")
        self.btn_save_pipeline.setIcon(load_phosphor_icon("ph.floppy-disk", color="white"))
        self.btn_save_pipeline.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #10b981, stop:1 #059669);
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: 600;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #059669, stop:1 #047857);
            }
        """)
        add_agent_row.addWidget(self.btn_save_pipeline)

        content_layout.addLayout(add_agent_row)

        self.pipeline_panel.add_tab("Pipelines de Génération", content_widget, "ph.git-merge", closable=False)
        wrapper_layout.addWidget(self.pipeline_panel)

        main_layout.addWidget(self.panel_wrapper)

    def _connect_signals(self) -> None:
        self.pipeline_combo.currentIndexChanged.connect(self._on_pipeline_changed)
        self.btn_new_pipeline.clicked.connect(self._on_new_pipeline)
        self.btn_del_pipeline.clicked.connect(self._on_delete_pipeline)
        self.btn_add_agent.clicked.connect(self._on_add_agent_to_pipeline)
        self.btn_save_pipeline.clicked.connect(self._on_save_pipeline)

    def refresh_data(self) -> None:
        """Recharge les pipelines et agents depuis Peewee DB."""
        try:
            self.pipeline_combo.blockSignals(True)
            self.pipeline_combo.clear()

            pipelines = list(PipelineModel.select())
            for pipe in pipelines:
                self.pipeline_combo.addItem(pipe.name, userData=pipe)

            self.pipeline_combo.blockSignals(False)

            # Recharger la liste des agents disponibles dans le combo d'ajout
            self.agent_combo.blockSignals(True)
            self.agent_combo.clear()
            self.agent_combo.addItem("Sélectionnez un Agent à ajouter...", userData=None)

            agents = list(AgentModel.select())
            for ag in agents:
                self.agent_combo.addItem(f"🤖 {ag.name}", userData=ag)
            self.agent_combo.blockSignals(False)

            if pipelines:
                self._on_pipeline_changed()

        except Exception as e:
            logger.warning("Erreur refresh_data pipelines_view: %s", e)

    def is_dirty(self) -> bool:
        return False

    @Slot()
    def _on_pipeline_changed(self) -> None:
        selected_pipe: Optional[PipelineModel] = self.pipeline_combo.currentData()
        if not selected_pipe:
            self._current_pipeline = None
            self.current_steps.clear()
            self._render_steps_list()
            return

        self._current_pipeline = selected_pipe
        self.current_steps.clear()

        # Recharger les étapes depuis Peewee (PipelineStepModel)
        steps_models = PipelineStepModel.select().where(PipelineStepModel.pipeline == selected_pipe).order_by(PipelineStepModel.step_order)
        for s in steps_models:
            if s.agent:
                self.current_steps.append(s.agent)

        self._render_steps_list()

    def _render_steps_list(self) -> None:
        self.steps_list.clear()

        if not self.current_steps:
            item = QListWidgetItem("Aucune étape dans ce pipeline. Ajoutez des agents ci-dessous.")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.steps_list.addItem(item)
            return

        for idx, agent in enumerate(self.current_steps, start=1):
            row_widget = PipelineStepRowWidget(
                order=idx,
                agent_name=agent.name,
                format_str=getattr(agent, "output_format", "json"),
            )
            row_widget.btn_up.clicked.connect(lambda _, i=idx - 1: self._move_step(i, -1))
            row_widget.btn_down.clicked.connect(lambda _, i=idx - 1: self._move_step(i, 1))
            row_widget.btn_delete.clicked.connect(lambda _, i=idx - 1: self._remove_step(i))

            item = QListWidgetItem(self.steps_list)
            item.setSizeHint(row_widget.sizeHint())
            self.steps_list.setItemWidget(item, row_widget)

    def _move_step(self, index: int, direction: int) -> None:
        target_idx = index + direction
        if 0 <= target_idx < len(self.current_steps):
            self.current_steps[index], self.current_steps[target_idx] = self.current_steps[target_idx], self.current_steps[index]
            self._render_steps_list()

    def _remove_step(self, index: int) -> None:
        if 0 <= index < len(self.current_steps):
            removed = self.current_steps.pop(index)
            self._render_steps_list()
            show_toast(self, f"Agent '{removed.name}' retiré de la chaîne.")

    @Slot()
    def _on_add_agent_to_pipeline(self) -> None:
        selected_agent: Optional[AgentModel] = self.agent_combo.currentData()
        if not selected_agent:
            show_toast(self, "Veuillez sélectionner un agent à ajouter.", is_error=True)
            return

        self.current_steps.append(selected_agent)
        self._render_steps_list()
        show_toast(self, f"Agent '{selected_agent.name}' ajouté à la chaîne !")

    @Slot()
    def _on_new_pipeline(self) -> None:
        name, ok = QInputDialog.getText(self, "Nouveau Pipeline", "Nom du pipeline :")
        if ok and name.strip():
            try:
                pipe_name = name.strip()
                pipe = PipelineModel.create(name=pipe_name, description="Pipeline personnalisé.")

                # Ajouter un agent par défaut si disponible
                first_agent = AgentModel.select().first()
                if first_agent:
                    PipelineStepModel.create(pipeline=pipe, agent=first_agent, step_order=1)

                self.refresh_data()
                idx = self.pipeline_combo.findText(pipe_name, Qt.MatchFlag.MatchExactly)
                if idx != -1:
                    self.pipeline_combo.setCurrentIndex(idx)

                show_toast(self, f"Pipeline '{pipe_name}' créé avec succès !")
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Impossible de créer le pipeline : {str(e)}")

    @Slot()
    def _on_delete_pipeline(self) -> None:
        if not self._current_pipeline:
            show_toast(self, "Aucun pipeline sélectionné à supprimer.", is_error=True)
            return

        confirm = QMessageBox.question(
            self,
            "Supprimer le pipeline",
            f"Voulez-vous vraiment supprimer le pipeline '{self._current_pipeline.name}' ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            try:
                self._current_pipeline.delete_instance()
                self._current_pipeline = None
                self.refresh_data()
                show_toast(self, "Pipeline supprimé de la base de données.")
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Impossible de supprimer le pipeline : {str(e)}")

    @Slot()
    def _on_save_pipeline(self) -> None:
        if not self._current_pipeline:
            show_toast(self, "Aucun pipeline sélectionné à sauvegarder.", is_error=True)
            return

        try:
            with db.atomic():
                # Vider les anciennes étapes
                PipelineStepModel.delete().where(PipelineStepModel.pipeline == self._current_pipeline).execute()

                # Re-créer les étapes ordonnées
                for idx, agent in enumerate(self.current_steps, start=1):
                    PipelineStepModel.create(
                        pipeline=self._current_pipeline,
                        agent=agent,
                        step_order=idx,
                    )

            show_toast(self, f"Pipeline '{self._current_pipeline.name}' enregistré avec succès !")
        except Exception as e:
            logger.exception("Erreur sauvegarde pipeline: %s", e)
            QMessageBox.critical(self, "Erreur de sauvegarde", f"Échec de l'enregistrement du pipeline : {str(e)}")


PipelinesTab = PipelinesView
