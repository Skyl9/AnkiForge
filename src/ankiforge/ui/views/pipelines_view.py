"""
Vue Pipelines (Éditeur de Chaînes DAG et d'Actions Système) — Conforme au Design System et au Moteur DAG.
- Supporte les Agents IA (Personas) et les Actions Système (RAG, Pause Copilote, Map-Reduce, Outil Python).
- QScrollArea + QVBoxLayout natif pour un rendu fluide et sans scintillement.
- Persistance atomique dans la base de données Peewee (PipelineModel & PipelineStepModel).
"""

import logging
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Signal, Slot
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

# Métadonnées des types d'étapes DAG
STEP_TYPES_META: Dict[str, Dict[str, Any]] = {
    "LLM_PROMPT": {
        "label": "Agent IA (LLM)",
        "badge": "LLM",
        "badge_variant": "status",
        "badge_color": "#8b5cf6",
        "icon": "ph.sparkle",
        "default_title": "Exécution d'un Agent IA",
        "requires_persona": True,
    },
    "HUMAN_VALIDATION": {
        "label": "Pause Copilote (Validation)",
        "badge": "PAUSE",
        "badge_variant": "warning",
        "badge_color": "#f59e0b",
        "icon": "ph.hand-palm",
        "default_title": "Pause Copilote (Validation Humaine)",
        "requires_persona": False,
    },
    "RAG_RETRIEVAL": {
        "label": "Recherche RAG Vectorielle",
        "badge": "RAG",
        "badge_variant": "info",
        "badge_color": "#06b6d4",
        "icon": "ph.magnifying-glass",
        "default_title": "Recherche Sémantique Documentaire",
        "requires_persona": False,
    },
    "MAP_REDUCE": {
        "label": "Génération Parallèle (par lots)",
        "badge": "PARALLÈLE",
        "badge_variant": "success",
        "badge_color": "#10b981",
        "icon": "ph.arrows-split",
        "default_title": "Génération Parallèle par Lots",
        "requires_persona": True,
    },
    "PYTHON_TOOL": {
        "label": "Outil Python Déterministe",
        "badge": "OUTIL",
        "badge_variant": "neutral",
        "badge_color": "#f97316",
        "icon": "ph.code",
        "default_title": "Exécution d'un Script / Outil",
        "requires_persona": False,
    },
}


class PipelineStepRowWidget(QFrame):
    """Widget représentant une étape du DAG — fond BG_PANEL sur conteneur BG_SIDEBAR."""

    type_changed = Signal(str)
    persona_changed = Signal(object)

    def __init__(
        self,
        order: int,
        step_data: Dict[str, Any],
        available_personas: List[PersonaModel],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.step_data = step_data
        self.available_personas = available_personas
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

        row_layout = QHBoxLayout(self)
        row_layout.setContentsMargins(14, 10, 14, 10)
        row_layout.setSpacing(12)

        # 1. Poignée de réordonnancement
        handle_lbl = QLabel()
        handle_lbl.setPixmap(load_phosphor_icon("ph.dots-six-vertical", color=DesignTokens.TEXT_MUTED).pixmap(18, 18))
        handle_lbl.setStyleSheet("background: transparent; border: none;")
        row_layout.addWidget(handle_lbl)

        # 2. Icône thématique du type d'étape
        self.icon_lbl = QLabel()
        self.icon_lbl.setStyleSheet("background: transparent; border: none;")
        row_layout.addWidget(self.icon_lbl)

        # 3. Numéro et Titre
        self.title_lbl = QLabel()
        self.title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 13px; background: transparent; border: none;")
        row_layout.addWidget(self.title_lbl)

        # 4. Sélecteur de Persona (si l'étape le supporte / nécessite)
        self.persona_combo = StyledComboBox()
        self.persona_combo.setFixedWidth(190)
        self.persona_combo.addItem("Aucun Agent (Action Pure)", userData=None)
        for p in self.available_personas:
            self.persona_combo.addItem(str(p.name), userData=p)
        self.persona_combo.currentIndexChanged.connect(self._on_persona_combo_changed)
        row_layout.addWidget(self.persona_combo)

        # 5. Combobox du Type d'Étape (DAG)
        self.type_combo = StyledComboBox()
        for key, meta in STEP_TYPES_META.items():
            self.type_combo.addItem(meta["label"], userData=key)
        self.type_combo.setFixedWidth(190)
        self.type_combo.currentIndexChanged.connect(self._on_type_combo_changed)
        row_layout.addWidget(self.type_combo)

        # 6. Badge de Type / Format
        self.role_badge = Badge("LLM", variant="status")
        row_layout.addWidget(self.role_badge)

        row_layout.addStretch()

        # 7. Boutons Monter / Descendre / Supprimer
        self.btn_up = IconButton("ph.caret-up", tooltip="Monter d'un rang", size=18)
        self.btn_down = IconButton("ph.caret-down", tooltip="Descendre d'un rang", size=18)
        self.btn_delete = IconButton("ph.trash", tooltip="Retirer du pipeline", size=18)

        row_layout.addWidget(self.btn_up)
        row_layout.addWidget(self.btn_down)
        row_layout.addWidget(self.btn_delete)

        # Initialisation des valeurs
        self.update_row(order, step_data)

    def update_row(self, order: int, step_data: Dict[str, Any]) -> None:
        """Met à jour l'affichage de la ligne avec les données de l'étape."""
        self.step_data = step_data
        step_type = step_data.get("type", "LLM_PROMPT")
        persona = step_data.get("persona")

        meta = STEP_TYPES_META.get(step_type, STEP_TYPES_META["LLM_PROMPT"])

        # Mise à jour icône
        self.icon_lbl.setPixmap(load_phosphor_icon(meta["icon"], color=meta["badge_color"]).pixmap(18, 18))

        # Titre
        if persona:
            display_title = persona.name
        else:
            display_title = meta["default_title"]
        self.title_lbl.setText(f"<b>{order}.</b> {display_title}")

        # Sélecteur de type
        idx_type = -1
        for i in range(self.type_combo.count()):
            if self.type_combo.itemData(i) == step_type:
                idx_type = i
                break
        if idx_type != -1:
            self.type_combo.blockSignals(True)
            self.type_combo.setCurrentIndex(idx_type)
            self.type_combo.blockSignals(False)

        # Sélecteur de persona
        self.persona_combo.blockSignals(True)
        if persona:
            idx_p = -1
            for i in range(self.persona_combo.count()):
                p_item = self.persona_combo.itemData(i)
                if p_item and getattr(p_item, "id", None) == getattr(persona, "id", None):
                    idx_p = i
                    break
            self.persona_combo.setCurrentIndex(idx_p if idx_p != -1 else 0)
        else:
            self.persona_combo.setCurrentIndex(0)
        self.persona_combo.blockSignals(False)

        # Visibilité du persona_combo selon le type
        if meta["requires_persona"]:
            self.persona_combo.setVisible(True)
        else:
            # Pour validation humaine ou RAG, on peut masquer ou désactiver le combo
            self.persona_combo.setVisible(False)

        # Badge
        self.role_badge.setText(meta["badge"])
        self.role_badge.base_color = meta["badge_color"]
        self.role_badge.set_variant(meta["badge_variant"])

    def _on_type_combo_changed(self) -> None:
        selected_type = self.type_combo.currentData() or "LLM_PROMPT"
        self.step_data["type"] = selected_type
        meta = STEP_TYPES_META.get(selected_type, STEP_TYPES_META["LLM_PROMPT"])

        if not meta["requires_persona"]:
            # On peut détacher le persona si ce n'est pas un prompt LLM
            pass
        self.update_row(int(self.title_lbl.text().split(".")[0].replace("<b>", "")), self.step_data)
        self.type_changed.emit(selected_type)

    def _on_persona_combo_changed(self) -> None:
        selected_persona = self.persona_combo.currentData()
        self.step_data["persona"] = selected_persona
        self.update_row(int(self.title_lbl.text().split(".")[0].replace("<b>", "")), self.step_data)
        self.persona_changed.emit(selected_persona)


class PipelinesView(QWidget):
    """
    Vue Pipelines de Génération — Éditeur de Graphes DAG et de Chaînes d'Exécution.
    100% Conforme au Moteur DAG (Actions Système + Personas IA).
    """

    def __init__(self, ai_manager: Optional[Any] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager
        self._current_pipeline: Optional[PipelineModel] = None
        self.current_steps: List[Dict[str, Any]] = []
        self._step_widgets: List[PipelineStepRowWidget] = []
        self._cached_personas: List[PersonaModel] = []

        self._setup_ui()
        self._connect_signals()
        self.refresh_data()

    def _setup_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(0)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        # Panneau IdePanel centré
        self.pipeline_panel = IdePanel(detachable=True)
        self.pipeline_panel.setMaximumWidth(980)
        self.pipeline_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        main_layout.addWidget(self.pipeline_panel, 1)

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setSpacing(16)

        # ── 1. Barre Supérieure : Gestion des Pipelines ────────────────────────
        pipeline_sel_row = QHBoxLayout()
        pipeline_sel_row.setSpacing(10)

        lbl_pipe = QLabel("PIPELINE ACTIF :")
        lbl_pipe.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold; letter-spacing: 0.5px;")
        pipeline_sel_row.addWidget(lbl_pipe)

        self.pipeline_combo = StyledComboBox()
        self.pipeline_combo.setMinimumWidth(240)
        pipeline_sel_row.addWidget(self.pipeline_combo, 1)

        self.btn_rename_pipeline = SecondaryButton("Renommer")
        self.btn_rename_pipeline.setIcon(load_phosphor_icon("ph.pencil-simple", color=DesignTokens.TEXT_PRIMARY))
        pipeline_sel_row.addWidget(self.btn_rename_pipeline)

        self.btn_new_pipeline = SecondaryButton("Nouveau Pipeline")
        self.btn_new_pipeline.setIcon(load_phosphor_icon("ph.plus", color=DesignTokens.TEXT_PRIMARY))
        pipeline_sel_row.addWidget(self.btn_new_pipeline)

        self.btn_del_pipeline = DangerButton("Supprimer", ghost=True)
        self.btn_del_pipeline.setIcon(load_phosphor_icon("ph.trash", color=DesignTokens.COLOR_RED))
        pipeline_sel_row.addWidget(self.btn_del_pipeline)

        content_layout.addLayout(pipeline_sel_row)

        # ── 2. En-tête de la liste des étapes ──────────────────────────────────
        steps_header_row = QHBoxLayout()
        lbl_steps = QLabel("ÉTAPES DU WORKFLOW DAG (ORCHESTRATION IA & SYSTÈME) :")
        lbl_steps.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        steps_header_row.addWidget(lbl_steps)
        steps_header_row.addStretch()

        self.lbl_step_count = QLabel("0 étape")
        self.lbl_step_count.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        steps_header_row.addWidget(self.lbl_step_count)
        content_layout.addLayout(steps_header_row)

        # ── 3. Zone de défilement des étapes ───────────────────────────────────
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

        # ── 4. Barre Inférieure : Ajouter une Étape & Sauvegarder ───────────────
        add_step_bar = QHBoxLayout()
        add_step_bar.setSpacing(10)

        self.element_to_add_combo = StyledComboBox()
        self.element_to_add_combo.setMinimumWidth(300)
        add_step_bar.addWidget(self.element_to_add_combo, 1)

        self.btn_add_step = SecondaryButton("Ajouter à la chaîne")
        self.btn_add_step.setIcon(load_phosphor_icon("ph.plus", color=DesignTokens.TEXT_PRIMARY))
        add_step_bar.addWidget(self.btn_add_step)

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
        add_step_bar.addWidget(self.btn_save_pipeline)

        content_layout.addLayout(add_step_bar)

        self.pipeline_panel.add_tab("Pipelines de Génération DAG", content_widget, "ph.git-merge", closable=False)

    def _connect_signals(self) -> None:
        self.pipeline_combo.currentIndexChanged.connect(self._on_pipeline_changed)
        self.btn_new_pipeline.clicked.connect(self._on_new_pipeline)
        self.btn_rename_pipeline.clicked.connect(self._on_rename_pipeline)
        self.btn_del_pipeline.clicked.connect(self._on_delete_pipeline)
        self.btn_add_step.clicked.connect(self._on_add_step_clicked)
        self.btn_save_pipeline.clicked.connect(self._on_save_pipeline)

    def refresh_data(self) -> None:
        """Recharge les pipelines et les agents depuis la base Peewee."""
        try:
            self.pipeline_combo.blockSignals(True)
            self.pipeline_combo.clear()

            pipelines = list(PipelineModel.select())
            for pipe in pipelines:
                self.pipeline_combo.addItem(pipe.name, userData=pipe)
            self.pipeline_combo.blockSignals(False)

            self._cached_personas = list(PersonaModel.select())
            self._populate_element_to_add_combo()

            if pipelines:
                self._on_pipeline_changed()
            else:
                self._current_pipeline = None
                self.current_steps.clear()
                self._render_steps()

        except Exception as e:
            logger.warning("Erreur refresh_data pipelines_view: %s", e)

    def _populate_element_to_add_combo(self) -> None:
        """Remplit le sélecteur d'ajout avec les Personas et les Actions Système."""
        self.element_to_add_combo.blockSignals(True)
        self.element_to_add_combo.clear()
        self.element_to_add_combo.addItem("Sélectionnez un élément à insérer...", userData=None)

        # 1. Actions Système prédéfinies
        self.element_to_add_combo.addItem(
            "⚡ [Système] 🤝 Pause Copilote (Validation Humaine)",
            userData={"type": "HUMAN_VALIDATION", "persona": None},
        )
        self.element_to_add_combo.addItem(
            "⚡ [Système] 🔍 Recherche Sémantique RAG",
            userData={"type": "RAG_RETRIEVAL", "persona": None},
        )
        self.element_to_add_combo.addItem(
            "⚡ [Système] 📦 Génération Parallèle (par lots)",
            userData={"type": "MAP_REDUCE", "persona": None},
        )
        self.element_to_add_combo.addItem(
            "⚡ [Système] 🐍 Outil Python Déterministe",
            userData={"type": "PYTHON_TOOL", "persona": None},
        )

        # 2. Agents IA (Personas)
        for ag in self._cached_personas:
            self.element_to_add_combo.addItem(
                f"🤖 [Agent IA] {ag.name}",
                userData={"type": "LLM_PROMPT", "persona": ag},
            )

        self.element_to_add_combo.blockSignals(False)

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
            self.current_steps.append(
                {
                    "persona": s.persona,
                    "type": s.step_type or "LLM_PROMPT",
                }
            )

        self._render_steps()

    def _render_steps(self) -> None:
        """Vide et re-peuple la zone d'étapes."""
        while self.steps_layout.count() > 1:
            item = self.steps_layout.takeAt(0)
            if item:
                w = item.widget()
                if w:
                    w.deleteLater()
        self._step_widgets.clear()

        count = len(self.current_steps)
        self.lbl_step_count.setText(f"{count} étape{'s' if count > 1 else ''}")

        if not self.current_steps:
            empty_lbl = QLabel("Aucune étape dans ce pipeline DAG.\nAjoutez une Action Système ou un Agent IA ci-dessous.")
            empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 13px; background: transparent; border: none; padding: 28px 0;")
            self.steps_layout.insertWidget(0, empty_lbl)
            return

        for idx, step_data in enumerate(self.current_steps, start=1):
            row = PipelineStepRowWidget(
                order=idx,
                step_data=step_data,
                available_personas=self._cached_personas,
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
            name = removed["persona"].name if removed.get("persona") else STEP_TYPES_META.get(removed.get("type", ""), {}).get("label", "Étape")
            show_toast(self, f"Étape '{name}' retirée de la chaîne.")

    @Slot()
    def _on_add_step_clicked(self) -> None:
        data = self.element_to_add_combo.currentData()
        if not data:
            show_toast(self, "Veuillez sélectionner un agent ou une action à ajouter.", is_error=True)
            return

        self.current_steps.append(
            {
                "type": data.get("type", "LLM_PROMPT"),
                "persona": data.get("persona"),
            }
        )
        self._render_steps()
        show_toast(self, "Étape ajoutée avec succès au pipeline !")

    @Slot()
    def _on_new_pipeline(self) -> None:
        name, ok = QInputDialog.getText(self, "Nouveau Pipeline", "Nom du pipeline :")
        if ok and name.strip():
            try:
                pipe_name = name.strip()
                pipe = PipelineModel.create(name=pipe_name, description="Pipeline personnalisé.")

                # Initialiser avec une première étape par défaut si possible
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
    def _on_rename_pipeline(self) -> None:
        if not self._current_pipeline:
            show_toast(self, "Aucun pipeline sélectionné à renommer.", is_error=True)
            return

        old_name = str(self._current_pipeline.name)
        new_name, ok = QInputDialog.getText(self, "Renommer le Pipeline", "Nouveau nom :", text=old_name)
        if ok and new_name.strip() and new_name.strip() != old_name:
            try:
                self._current_pipeline.name = str(new_name.strip())
                self._current_pipeline.save()
                self.refresh_data()
                idx = self.pipeline_combo.findText(new_name.strip(), Qt.MatchFlag.MatchExactly)
                if idx != -1:
                    self.pipeline_combo.setCurrentIndex(idx)
                show_toast(self, f"Pipeline renommé en '{new_name.strip()}' !")
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Impossible de renommer le pipeline : {str(e)}")

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
                        persona=step_data.get("persona"),
                        step_type=step_data.get("type", "LLM_PROMPT"),
                        step_order=idx,
                    )

            show_toast(self, f"Pipeline '{self._current_pipeline.name}' enregistré avec succès !")
        except Exception as e:
            logger.exception("Erreur sauvegarde pipeline: %s", e)
            QMessageBox.critical(self, "Erreur de sauvegarde", f"Échec de l'enregistrement du pipeline : {str(e)}")


PipelinesTab = PipelinesView
