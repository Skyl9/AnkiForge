"""
Vue Pipelines (Éditeur de Chaînes d'Agents) — 100% Conforme à la Maquette concept_ide.
- QScrollArea + QVBoxLayout natif (pas de QListWidget) pour un rendu fidèle des cartes #1e2128 sur fond #16181d.
- Panneau s'étirant sur toute la hauteur de la fenêtre.
"""

import logging
from typing import Any, Optional

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import PersonaModel, PipelineModel, PipelineStepModel, db
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
    """Widget représentant une étape de pipeline — fond BG_PANEL sur conteneur BG_SIDEBAR."""

    def __init__(self, order: int, step_data: dict[str, Any], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("StepRow")
        self.setStyleSheet(f"""
            QFrame#StepRow {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
            QFrame#StepRow:hover {{
                background-color: {DesignTokens.BG_HOVER};
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(12)

        # Handle de réordonnancement
        handle_lbl = QLabel()
        handle_lbl.setPixmap(load_phosphor_icon("ph.dots-six-vertical", color=DesignTokens.TEXT_MUTED).pixmap(18, 18))
        handle_lbl.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(handle_lbl)

        # Titre et numéro de l'étape
        agent_name = step_data["persona"].name if step_data.get("persona") else "Agent Inconnu"
        self.title_lbl = QLabel(f"<b>{order}.</b> {agent_name}")
        self.title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 13px; background: transparent; border: none;")
        layout.addWidget(self.title_lbl)

        # Combobox du Type d'Étape (DAG)
        self.type_combo = StyledComboBox()
        self.type_combo.addItems(["LLM_PROMPT", "RAG_RETRIEVAL", "HUMAN_VALIDATION", "MAP_REDUCE"])
        self.type_combo.setCurrentText(step_data.get("type", "LLM_PROMPT"))
        self.type_combo.currentTextChanged.connect(lambda t: step_data.update({"type": t}))
        self.type_combo.setFixedWidth(160)
        layout.addWidget(self.type_combo)

        # Badge de format
        format_str = getattr(step_data.get("persona"), "output_format", "json")
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
    """Vue Pipelines de Génération — 100% Conforme à la Maquette concept_ide."""

    def __init__(self, ai_manager: Optional[Any] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager
        self._current_pipeline: Optional[PipelineModel] = None
        self.current_steps: list[dict[str, Any]] = []
        self._step_widgets: list[PipelineStepRowWidget] = []

        self._setup_ui()
        self._connect_signals()
        self.refresh_data()

    def _setup_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(0)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        # Panneau IdePanel centré et occupant 100% de la hauteur disponible
        self.pipeline_panel = IdePanel(detachable=True)
        self.pipeline_panel.setMaximumWidth(960)
        self.pipeline_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        main_layout.addWidget(self.pipeline_panel, 1)

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setSpacing(16)

        # ── Sélecteur de Pipeline ──────────────────────────────────────────────
        pipeline_sel_row = QHBoxLayout()
        pipeline_sel_row.setSpacing(10)

        lbl_pipe = QLabel("PIPELINE ACTIF :")
        lbl_pipe.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold; letter-spacing: 0.5px;")
        pipeline_sel_row.addWidget(lbl_pipe)

        self.pipeline_combo = StyledComboBox()
        self.pipeline_combo.setMinimumWidth(240)
        pipeline_sel_row.addWidget(self.pipeline_combo, 1)

        self.btn_new_pipeline = SecondaryButton("Nouveau Pipeline")
        self.btn_new_pipeline.setIcon(load_phosphor_icon("ph.plus", color=DesignTokens.TEXT_PRIMARY))
        pipeline_sel_row.addWidget(self.btn_new_pipeline)

        self.btn_del_pipeline = DangerButton("Supprimer", ghost=True)
        self.btn_del_pipeline.setIcon(load_phosphor_icon("ph.trash", color=DesignTokens.COLOR_RED))
        pipeline_sel_row.addWidget(self.btn_del_pipeline)

        content_layout.addLayout(pipeline_sel_row)

        # ── Label section ──────────────────────────────────────────────────────
        lbl_steps = QLabel("ÉTAPES DE LA CHAÎNE D'AGENTS :")
        lbl_steps.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        content_layout.addWidget(lbl_steps)

        # ── Zone de liste d'étapes (QScrollArea + fond #16181d) ───────────────
        self.steps_container_frame = QFrame()
        self.steps_container_frame.setObjectName("StepsContainer")
        self.steps_container_frame.setStyleSheet(f"""
            QFrame#StepsContainer {{
                background-color: {DesignTokens.BG_SIDEBAR};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        apply_shadow(self.steps_container_frame, blur=12, offset_y=2)

        steps_frame_layout = QVBoxLayout(self.steps_container_frame)
        steps_frame_layout.setContentsMargins(10, 10, 10, 10)
        steps_frame_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{ background: {DesignTokens.BG_INPUT}; width: 6px; border-radius: 3px; }}
            QScrollBar::handle:vertical {{ background: {DesignTokens.BORDER_COLOR}; border-radius: 3px; min-height: 20px; }}
        """)

        # Widget interne du scroll : fond transparent pour laisser voir #16181d
        self.steps_inner = QWidget()
        self.steps_inner.setObjectName("StepsInner")
        self.steps_inner.setStyleSheet("QWidget#StepsInner { background: transparent; }")
        self.steps_layout = QVBoxLayout(self.steps_inner)
        self.steps_layout.setContentsMargins(0, 0, 0, 0)
        self.steps_layout.setSpacing(8)
        self.steps_layout.addStretch(1)

        scroll.setWidget(self.steps_inner)
        steps_frame_layout.addWidget(scroll)

        content_layout.addWidget(self.steps_container_frame, 1)

        # ── Toolbar Ajouter & Sauvegarder ─────────────────────────────────────
        add_agent_row = QHBoxLayout()
        add_agent_row.setSpacing(10)

        self.persona_combo = StyledComboBox()
        self.persona_combo.setMinimumWidth(260)
        add_agent_row.addWidget(self.persona_combo, 1)

        self.btn_add_agent = SecondaryButton("Ajouter à la chaîne")
        self.btn_add_agent.setIcon(load_phosphor_icon("ph.plus", color=DesignTokens.TEXT_PRIMARY))
        add_agent_row.addWidget(self.btn_add_agent)

        self.btn_save_pipeline = PrimaryButton("Sauvegarder Pipeline")
        self.btn_save_pipeline.setIcon(load_phosphor_icon("ph.floppy-disk", color="white"))
        self.btn_save_pipeline.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #6366f1, stop:1 #8b5cf6);
                border: 1px solid #6366f1;
                color: white;
                font-weight: bold;
                padding: 6px 16px;
                border-radius: 6px;
                font-size: 12px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #4f46e5, stop:1 #7c3aed);
            }
        """)
        apply_shadow(self.btn_save_pipeline, blur=14, offset_y=0, color="rgba(99, 102, 241, 0.7)")
        add_agent_row.addWidget(self.btn_save_pipeline)

        content_layout.addLayout(add_agent_row)

        self.pipeline_panel.add_tab("Pipelines de Génération", content_widget, "ph.git-merge", closable=False)

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

            self.persona_combo.blockSignals(True)
            self.persona_combo.clear()
            self.persona_combo.addItem("Sélectionnez un Agent à ajouter...", userData=None)

            agents = list(PersonaModel.select())
            for ag in agents:
                self.persona_combo.addItem(ag.name, userData=ag)
            self.persona_combo.blockSignals(False)

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
            self._render_steps()
            return

        self._current_pipeline = selected_pipe
        self.current_steps.clear()

        steps_models = PipelineStepModel.select().where(PipelineStepModel.pipeline == selected_pipe).order_by(PipelineStepModel.step_order)
        for s in steps_models:
            if s.persona:
                self.current_steps.append({"persona": s.persona, "type": s.step_type or "LLM_PROMPT"})

        self._render_steps()

    def _render_steps(self) -> None:
        """Vide et re-peuple la zone d'étapes via QVBoxLayout natif (pas de QListWidget)."""
        # Supprimer tous les widgets existants (sauf le spacer final)
        while self.steps_layout.count() > 1:
            item = self.steps_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self._step_widgets.clear()

        if not self.current_steps:
            empty_lbl = QLabel("Aucune étape dans ce pipeline.\nAjoutez des agents ci-dessous.")
            empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 13px; background: transparent; border: none; padding: 24px 0;")
            self.steps_layout.insertWidget(0, empty_lbl)
            return

        for idx, step_data in enumerate(self.current_steps, start=1):
            row = PipelineStepRowWidget(
                order=idx,
                step_data=step_data,
            )
            row.btn_up.clicked.connect(lambda _, i=idx - 1: self._move_step(i, -1))
            row.btn_down.clicked.connect(lambda _, i=idx - 1: self._move_step(i, 1))
            row.btn_delete.clicked.connect(lambda _, i=idx - 1: self._remove_step(i))

            self.steps_layout.insertWidget(idx - 1, row)
            self._step_widgets.append(row)

    def _move_step(self, index: int, direction: int) -> None:
        target_idx = index + direction
        if 0 <= target_idx < len(self.current_steps):
            self.current_steps[index], self.current_steps[target_idx] = (
                self.current_steps[target_idx],
                self.current_steps[index],
            )
            self._render_steps()

    def _remove_step(self, index: int) -> None:
        if 0 <= index < len(self.current_steps):
            removed = self.current_steps.pop(index)
            self._render_steps()
            agent_name = removed["persona"].name if removed.get("persona") else "Agent"
            show_toast(self, f"Étape '{agent_name}' retirée de la chaîne.")

    @Slot()
    def _on_add_agent_to_pipeline(self) -> None:
        selected_agent: Optional[PersonaModel] = self.persona_combo.currentData()
        if not selected_agent:
            show_toast(self, "Veuillez sélectionner un agent à ajouter.", is_error=True)
            return

        self.current_steps.append({"persona": selected_agent, "type": "LLM_PROMPT"})
        self._render_steps()
        show_toast(self, f"Agent '{selected_agent.name}' ajouté à la chaîne !")

    @Slot()
    def _on_new_pipeline(self) -> None:
        name, ok = QInputDialog.getText(self, "Nouveau Pipeline", "Nom du pipeline :")
        if ok and name.strip():
            try:
                pipe_name = name.strip()
                pipe = PipelineModel.create(name=pipe_name, description="Pipeline personnalisé.")

                first_agent = PersonaModel.select().first()
                if first_agent:
                    PipelineStepModel.create(pipeline=pipe, persona=first_agent, step_type="LLM_PROMPT", step_order=1)

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
                PipelineStepModel.delete().where(PipelineStepModel.pipeline == self._current_pipeline).execute()

                for idx, step_data in enumerate(self.current_steps, start=1):
                    PipelineStepModel.create(
                        pipeline=self._current_pipeline,
                        persona=step_data["persona"],
                        step_type=step_data.get("type", "LLM_PROMPT"),
                        step_order=idx,
                    )

            show_toast(self, f"Pipeline '{self._current_pipeline.name}' enregistré avec succès !")
        except Exception as e:
            logger.exception("Erreur sauvegarde pipeline: %s", e)
            QMessageBox.critical(self, "Erreur de sauvegarde", f"Échec de l'enregistrement du pipeline : {str(e)}")


PipelinesTab = PipelinesView
