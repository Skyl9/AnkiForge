import html
import json
import logging
from typing import Any

from PySide6.QtCore import QSize, Qt, Slot
from PySide6.QtGui import QCursor, QFont
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import (
    LLMConfigModel,
    PersonaModel,
    PipelineModel,
    PipelineStepModel,
    db,
)
from ankiforge.ui.components import (
    Badge,
    IconButton,
    IdePanel,
    PrimaryButton,
    SecondaryButton,
    StyledComboBox,
)
from ankiforge.ui.theme import DesignTokens, StyledMenu, apply_shadow
from ankiforge.ui.views.pipelines_view.constants import (
    PRESET_TEMPLATES,
    STEP_TYPES_META,
    apply_pill_style,
)
from ankiforge.ui.views.pipelines_view.widgets import (
    DagFlowOverviewWidget,
    InlineInsertButton,
    PipelineRunDialog,
    StepInspectorPanel,
    StepItemWidget,
    StepPickerDialog,
    StepTestDialog,
)
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class PipelinesView(QWidget):
    """Vue Pipelines de Génération — Architecture Maître-Détail JetBrains."""

    def __init__(self, ai_manager: Any | None = None, profile_name: str = "default", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager
        self.profile_name = profile_name
        self._current_pipeline: PipelineModel | None = None
        self.current_steps: list[dict[str, Any]] = []
        self._step_widgets: list[StepItemWidget] = []
        self._cached_personas: list[PersonaModel] = []
        self._cached_llms: list[LLMConfigModel] = []
        self._selected_step_index: int = 0

        self._setup_ui()
        self._connect_signals()
        self.refresh_data()

    def _setup_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(0)

        # Panneau IdePanel
        self.pipeline_panel = IdePanel(detachable=True)
        self.pipeline_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        main_layout.addWidget(self.pipeline_panel, 1)

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(16, 16, 16, 16)
        content_layout.setSpacing(12)

        # ── 1. Barre Supérieure Épurée : Gestion & Toolbar ────────────────────
        pipeline_sel_row = QHBoxLayout()
        pipeline_sel_row.setSpacing(10)

        lbl_pipe_icon = QLabel()
        lbl_pipe_icon.setFixedSize(20, 20)
        lbl_pipe_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_pipe_icon.setPixmap(load_phosphor_icon("ph.git-branch", color=DesignTokens.ACCENT_PRIMARY).pixmap(18, 18))
        pipeline_sel_row.addWidget(lbl_pipe_icon, alignment=Qt.AlignmentFlag.AlignVCenter)

        lbl_pipe = QLabel("PIPELINE :")
        lbl_pipe.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold; letter-spacing: 0.5px;")
        pipeline_sel_row.addWidget(lbl_pipe, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.pipeline_combo = StyledComboBox()
        self.pipeline_combo.setMinimumWidth(220)
        self.pipeline_combo.setFixedHeight(30)
        pipeline_sel_row.addWidget(self.pipeline_combo, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.lbl_pipeline_steps_badge = Badge("0 étapes", variant="neutral")
        apply_pill_style(self.lbl_pipeline_steps_badge, "#94a3b8")
        self.lbl_pipeline_steps_badge.setFixedHeight(20)
        pipeline_sel_row.addWidget(self.lbl_pipeline_steps_badge, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.btn_rename_pipeline = IconButton("ph.pencil-simple", tooltip="Renommer le pipeline", size=28)
        pipeline_sel_row.addWidget(self.btn_rename_pipeline, alignment=Qt.AlignmentFlag.AlignVCenter)

        pipeline_sel_row.addStretch()

        # Action Principale : Tester DAG
        self.btn_test_full = SecondaryButton("Tester le DAG")
        self.btn_test_full.setIcon(load_phosphor_icon("ph.play", color=DesignTokens.TEXT_PRIMARY))
        self.btn_test_full.setIconSize(QSize(14, 14))
        self.btn_test_full.setFixedHeight(30)
        self.btn_test_full.clicked.connect(self._on_test_full_pipeline)
        pipeline_sel_row.addWidget(self.btn_test_full, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Action Secondaire : Sauvegarder
        self.btn_save_pipeline = PrimaryButton("Enregistrer")
        self.btn_save_pipeline.setIcon(load_phosphor_icon("ph.floppy-disk", color="white"))
        self.btn_save_pipeline.setIconSize(QSize(14, 14))
        self.btn_save_pipeline.setFixedHeight(30)
        apply_shadow(self.btn_save_pipeline, blur=14, offset_y=0, color="rgba(99, 102, 241, 0.7)")
        pipeline_sel_row.addWidget(self.btn_save_pipeline, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Menu d'Actions Groupées (•••)
        self.btn_more_menu = IconButton("ph.dots-three-vertical", tooltip="Options avancées (Nouveau, Dupliquer, Modèles, Export/Import, Supprimer)", size=28)
        self.btn_more_menu.clicked.connect(self._on_open_more_menu)
        pipeline_sel_row.addWidget(self.btn_more_menu, alignment=Qt.AlignmentFlag.AlignVCenter)

        content_layout.addLayout(pipeline_sel_row)

        # ── 2. Aperçu Visuel du Graphe DAG Interactif ─────────────────────────
        self.flow_overview = DagFlowOverviewWidget()
        self.flow_overview.step_selected.connect(self._on_step_selected)
        content_layout.addWidget(self.flow_overview)

        # ── 3. Splitter Maître-Détail ──────────────────────────────────────────
        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- PANNEAU GAUCHE : LISTE DES ÉTAPES ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        steps_header = QHBoxLayout()
        lbl_steps_title = QLabel("ÉTAPES DU WORKFLOW :")
        lbl_steps_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        steps_header.addWidget(lbl_steps_title)
        steps_header.addStretch()

        self.lbl_step_count = QLabel("0 étape")
        self.lbl_step_count.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        steps_header.addWidget(self.lbl_step_count)
        left_layout.addLayout(steps_header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"QScrollArea {{ background: transparent; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 6px; }}")

        self.steps_inner = QWidget()
        self.steps_layout = QVBoxLayout(self.steps_inner)
        self.steps_layout.setContentsMargins(8, 8, 8, 8)
        self.steps_layout.setSpacing(8)
        self.steps_layout.addStretch()
        scroll.setWidget(self.steps_inner)
        left_layout.addWidget(scroll, 1)

        self.btn_add_step = PrimaryButton("Ajouter une étape au workflow")
        self.btn_add_step.setIcon(load_phosphor_icon("ph.plus", color="white"))
        self.btn_add_step.setIconSize(QSize(14, 14))
        self.btn_add_step.setFixedHeight(32)
        self.btn_add_step.clicked.connect(lambda: self._on_add_step_clicked(insert_at=None))
        left_layout.addWidget(self.btn_add_step)

        self.splitter.addWidget(left_widget)

        # --- PANNEAU DROIT : INSPECTEUR D'ÉTAPE ---
        self.inspector = StepInspectorPanel()
        self.inspector.step_updated.connect(self._on_inspector_step_updated)
        self.inspector.test_step_requested.connect(self._on_test_single_step)
        self.splitter.addWidget(self.inspector)

        self.splitter.setSizes([380, 620])
        content_layout.addWidget(self.splitter, 1)

        self.pipeline_panel.add_tab("Éditeur de Pipelines DAG", content_widget, icon_name="ph.git-branch", closable=False)

    def _connect_signals(self) -> None:
        self.pipeline_combo.currentIndexChanged.connect(self._on_pipeline_changed)
        self.btn_rename_pipeline.clicked.connect(self._on_rename_pipeline)
        self.btn_save_pipeline.clicked.connect(self._on_save_pipeline)

    def _on_open_more_menu(self) -> None:
        """Affiche le menu contextuel élégant regroupant toutes les actions secondaires."""
        menu = StyledMenu(self)

        act_new = menu.addAction(load_phosphor_icon("ph.plus", color=DesignTokens.TEXT_PRIMARY), "Nouveau Pipeline...")
        act_clone = menu.addAction(load_phosphor_icon("ph.copy", color=DesignTokens.TEXT_PRIMARY), "Dupliquer le Pipeline")
        act_templates = menu.addAction(load_phosphor_icon("ph.puzzle-piece", color=DesignTokens.TEXT_PRIMARY), "Modèles Prédéfinis...")

        menu.addSeparator()

        act_export = menu.addAction(load_phosphor_icon("ph.export", color=DesignTokens.TEXT_PRIMARY), "Exporter en JSON...")
        act_import = menu.addAction(load_phosphor_icon("ph.download-simple", color=DesignTokens.TEXT_PRIMARY), "Importer un JSON...")

        menu.addSeparator()

        act_del = menu.addAction(load_phosphor_icon("ph.trash", color=DesignTokens.COLOR_RED), "Supprimer ce Pipeline")

        action = menu.exec(QCursor.pos())
        if action == act_new:
            self._on_new_pipeline()
        elif action == act_clone:
            self._on_clone_pipeline()
        elif action == act_templates:
            self._on_open_templates()
        elif action == act_export:
            self._on_export_json()
        elif action == act_import:
            self._on_import_json()
        elif action == act_del:
            self._on_delete_pipeline()

    def refresh_data(self) -> None:
        """Recharge les Personas, les modèles LLM et les pipelines depuis SQLite."""
        try:
            self._cached_personas = list(PersonaModel.select().order_by(PersonaModel.name.asc()))
            self._cached_llms = list(LLMConfigModel.select().order_by(LLMConfigModel.display_name.asc()))
        except Exception as e:
            logger.warning("Erreur refresh_data personas/llms : %s", e)
            self._cached_personas = []
            self._cached_llms = []

        self.pipeline_combo.blockSignals(True)
        self.pipeline_combo.clear()

        try:
            pipelines = list(PipelineModel.select().order_by(PipelineModel.name.asc()))
            for p in pipelines:
                self.pipeline_combo.addItem(p.name, userData=p)
        except Exception as e:
            logger.warning("Erreur refresh_data pipelines : %s", e)

        self.pipeline_combo.blockSignals(False)

        if self.pipeline_combo.count() > 0:
            self.pipeline_combo.setCurrentIndex(0)
            self._on_pipeline_changed()
        else:
            self._current_pipeline = None
            self.current_steps.clear()
            self._render_steps()

    @Slot()
    def _on_pipeline_changed(self) -> None:
        selected_pipe: PipelineModel | None = self.pipeline_combo.currentData()
        if not selected_pipe:
            self._current_pipeline = None
            self.current_steps.clear()
            self._render_steps()
            return

        self._current_pipeline = selected_pipe
        self.current_steps.clear()

        try:
            steps_models = list(PipelineStepModel.select().where(PipelineStepModel.pipeline == selected_pipe).order_by(PipelineStepModel.step_order.asc()))
        except Exception as e:
            logger.warning("Erreur chargement étapes : %s", e)
            steps_models = []

        for s in steps_models:
            succ_order = s.on_success_step.step_order if s.on_success_step else None
            fail_order = s.on_failure_step.step_order if s.on_failure_step else None
            cfg = {}
            raw_cfg = getattr(s, "config_data", None)
            if raw_cfg:
                try:
                    cfg = json.loads(raw_cfg)
                except Exception:
                    cfg = {}

            self.current_steps.append(
                {
                    "persona": s.persona,
                    "type": s.step_type or "LLM_PROMPT",
                    "on_success_order": succ_order,
                    "on_failure_order": fail_order,
                    "failure_behavior": s.failure_behavior or "stop",
                    "config": cfg,
                }
            )

        self._selected_step_index = 0
        self._render_steps()

    def _render_steps(self) -> None:
        """Re-génère l'affichage de la liste des étapes et met à jour l'inspecteur."""
        while self.steps_layout.count() > 1:
            item = self.steps_layout.takeAt(0)
            if item:
                w = item.widget()
                if w:
                    w.setParent(None)
                    w.deleteLater()

        self._step_widgets.clear()
        total = len(self.current_steps)
        self.lbl_step_count.setText(f"{total} étape{'s' if total > 1 else ''}")
        self.lbl_pipeline_steps_badge.setText(f"{total} étape{'s' if total > 1 else ''}")

        for idx, step_data in enumerate(self.current_steps, start=1):
            is_sel = (idx - 1) == self._selected_step_index
            widget = StepItemWidget(order=idx, step_data=step_data, is_selected=is_sel)
            widget.clicked.connect(self._on_step_selected)
            widget.btn_up.clicked.connect(lambda _, i=idx - 1: self._move_step_up(i))
            widget.btn_down.clicked.connect(lambda _, i=idx - 1: self._move_step_down(i))
            widget.btn_delete.clicked.connect(lambda _, i=idx - 1: self._delete_step(i))

            self._step_widgets.append(widget)
            self.steps_layout.insertWidget(self.steps_layout.count() - 1, widget)

            if idx < total:
                inline_btn = InlineInsertButton(insert_index=idx)
                inline_btn.clicked.connect(lambda insert_at: self._on_add_step_clicked(insert_at=insert_at))
                self.steps_layout.insertWidget(self.steps_layout.count() - 1, inline_btn)

        if total > 0 and 0 <= self._selected_step_index < total:
            self.inspector.inspect_step(
                step_data=self.current_steps[self._selected_step_index],
                step_order=self._selected_step_index + 1,
                total_steps=total,
                personas=self._cached_personas,
                llms=self._cached_llms,
            )
        else:
            self.inspector.inspect_step(
                step_data={},
                step_order=1,
                total_steps=0,
                personas=self._cached_personas,
                llms=self._cached_llms,
            )

        self.flow_overview.render_flow(self.current_steps, active_index=self._selected_step_index)

    def _on_step_selected(self, index: int) -> None:
        if 0 <= index < len(self.current_steps):
            self._selected_step_index = index
            self._render_steps()

    def _on_inspector_step_updated(self) -> None:
        self.flow_overview.render_flow(self.current_steps, active_index=self._selected_step_index)
        if 0 <= self._selected_step_index < len(self._step_widgets):
            cur = self.current_steps[self._selected_step_index]
            persona = cur.get("persona")
            meta = STEP_TYPES_META.get(cur.get("type", "LLM_PROMPT"), STEP_TYPES_META["LLM_PROMPT"])
            title = cur.get("custom_title") or (persona.name if persona else meta["default_title"])
            title_escaped = html.escape(str(title))
            self._step_widgets[self._selected_step_index].title_lbl.setText(f"<b>{self._selected_step_index + 1}.</b> {title_escaped}")

    def _move_step_up(self, index: int) -> None:
        if index > 0:
            self.current_steps[index], self.current_steps[index - 1] = self.current_steps[index - 1], self.current_steps[index]
            self._selected_step_index = index - 1
            self._render_steps()

    def _move_step_down(self, index: int) -> None:
        if index < len(self.current_steps) - 1:
            self.current_steps[index], self.current_steps[index + 1] = self.current_steps[index + 1], self.current_steps[index]
            self._selected_step_index = index + 1
            self._render_steps()

    def _delete_step(self, index: int) -> None:
        if 0 <= index < len(self.current_steps):
            del self.current_steps[index]
            if self._selected_step_index >= len(self.current_steps):
                self._selected_step_index = max(0, len(self.current_steps) - 1)
            self._render_steps()

    def add_step(self, step_payload: dict[str, Any], insert_at: int | None = None) -> None:
        """Ajoute une étape (Agent IA ou Action Système) au workflow courant."""
        stype = step_payload.get("type", "LLM_PROMPT")
        persona = step_payload.get("persona")
        meta = STEP_TYPES_META.get(stype, STEP_TYPES_META["LLM_PROMPT"])

        new_step: dict[str, Any] = {
            "type": stype,
            "persona": persona,
            "custom_title": persona.name if persona else meta["default_title"],
            "on_success_order": None,
            "on_failure_order": None,
            "failure_behavior": "stop",
            "config": {
                "input_variable": meta.get("default_input", "text_source"),
                "output_variable": meta.get("default_output", "generated_cards"),
            },
        }
        if "config" in step_payload:
            new_step["config"].update(step_payload["config"])

        if insert_at is not None and 0 <= insert_at <= len(self.current_steps):
            self.current_steps.insert(insert_at, new_step)
            self._selected_step_index = insert_at
        else:
            self.current_steps.append(new_step)
            self._selected_step_index = len(self.current_steps) - 1

        self._render_steps()
        show_toast(self, f"Étape '{new_step['custom_title']}' ajoutée", is_error=False)

    def _on_add_step_clicked(self, insert_at: int | None = None) -> None:
        """Ouvre la palette/catalogue de composants modernes pour choisir l'étape."""
        dlg = StepPickerDialog(personas=self._cached_personas, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.selected_step_data:
            self.add_step(dlg.selected_step_data, insert_at=insert_at)

    def _on_rename_pipeline(self) -> None:
        if not self._current_pipeline:
            return
        new_name, ok = QInputDialog.getText(self, "Renommer le pipeline", "Nouveau nom :", text=str(self._current_pipeline.name))
        if ok and new_name.strip():
            self._current_pipeline.name = new_name.strip()
            self._current_pipeline.save()
            show_toast(self, "Pipeline renommé avec succès", is_error=False)
            self.refresh_data()

    def _on_new_pipeline(self) -> None:
        name, ok = QInputDialog.getText(self, "Nouveau Pipeline", "Nom du pipeline :")
        if ok and name.strip():
            try:
                p = PipelineModel.create(name=name.strip(), description="Pipeline personnalisé")
                show_toast(self, f"Pipeline '{p.name}' créé !", is_error=False)
                self.refresh_data()
                for i in range(self.pipeline_combo.count()):
                    if self.pipeline_combo.itemText(i) == p.name:
                        self.pipeline_combo.setCurrentIndex(i)
                        break
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Impossible de créer le pipeline : {e}")

    def _on_clone_pipeline(self) -> None:
        if not self._current_pipeline:
            return
        clone_name = f"{self._current_pipeline.name} (Copie)"
        try:
            new_pipe = PipelineModel.create(name=clone_name, description=self._current_pipeline.description)
            created_steps: dict[int, PipelineStepModel] = {}
            for idx, s in enumerate(self.current_steps, start=1):
                ps = PipelineStepModel.create(
                    pipeline=new_pipe,
                    persona=s.get("persona"),
                    step_type=s.get("type", "LLM_PROMPT"),
                    step_order=idx,
                    failure_behavior=s.get("failure_behavior", "stop"),
                    config_data=json.dumps(s.get("config", {})),
                )
                created_steps[idx] = ps

            for idx, s in enumerate(self.current_steps, start=1):
                succ_idx = s.get("on_success_order")
                fail_idx = s.get("on_failure_order")
                need_update = False
                ps = created_steps[idx]
                if succ_idx and succ_idx in created_steps:
                    ps.on_success_step = created_steps[succ_idx]
                    need_update = True
                if fail_idx and fail_idx in created_steps:
                    ps.on_failure_step = created_steps[fail_idx]
                    need_update = True
                if need_update:
                    ps.save()

            show_toast(self, f"Pipeline dupliqué sous le nom '{clone_name}' !", is_error=False)
            self.refresh_data()
            for i in range(self.pipeline_combo.count()):
                if self.pipeline_combo.itemText(i) == clone_name:
                    self.pipeline_combo.setCurrentIndex(i)
                    break
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Échec du clonage : {e}")

    def _on_delete_pipeline(self) -> None:
        if not self._current_pipeline:
            return
        reply = QMessageBox.question(
            self,
            "Supprimer le pipeline",
            f"Voulez-vous vraiment supprimer définitivement le pipeline '{self._current_pipeline.name}' ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self._current_pipeline.delete_instance(recursive=True)
                show_toast(self, "Pipeline supprimé", is_error=False)
                self.refresh_data()
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Échec de suppression : {e}")

    def _on_save_pipeline(self) -> None:
        if not self._current_pipeline:
            return

        try:
            with db.atomic():
                PipelineStepModel.delete().where(PipelineStepModel.pipeline == self._current_pipeline).execute()

                created_steps: dict[int, PipelineStepModel] = {}
                for idx, s in enumerate(self.current_steps, start=1):
                    cfg_json = json.dumps(s.get("config", {}))
                    ps = PipelineStepModel.create(
                        pipeline=self._current_pipeline,
                        persona=s.get("persona"),
                        step_order=idx,
                        step_type=s.get("type", "LLM_PROMPT"),
                        failure_behavior=s.get("failure_behavior", "stop"),
                        config_data=cfg_json,
                    )
                    created_steps[idx] = ps

                for idx, s in enumerate(self.current_steps, start=1):
                    succ_idx = s.get("on_success_order")
                    fail_idx = s.get("on_failure_order")
                    need_update = False
                    ps = created_steps[idx]
                    if succ_idx and succ_idx in created_steps:
                        ps.on_success_step = created_steps[succ_idx]
                        need_update = True
                    if fail_idx and fail_idx in created_steps:
                        ps.on_failure_step = created_steps[fail_idx]
                        need_update = True
                    if need_update:
                        ps.save()

            show_toast(self, f"Pipeline '{self._current_pipeline.name}' sauvegardé avec succès !", is_error=False)
        except Exception as e:
            QMessageBox.critical(self, "Erreur de sauvegarde", f"Échec : {e}")

    def _on_test_single_step(self, step_data: dict) -> None:
        dlg = StepTestDialog(step_data, parent=self)
        dlg.exec()

    def _on_test_full_pipeline(self) -> None:
        if not self._current_pipeline:
            return
        dlg = PipelineRunDialog(self._current_pipeline, self.current_steps, parent=self)
        dlg.exec()

    def _on_open_templates(self) -> None:
        """Affiche la bibliothèque de modèles prédéfinis pour charger un workflow en 1 clic."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Bibliothèque de Modèles Prédéfinis")
        dlg.resize(620, 420)
        dlg.setStyleSheet(f"background-color: {DesignTokens.BG_MAIN}; color: {DesignTokens.TEXT_PRIMARY};")

        dlg_layout = QVBoxLayout(dlg)
        dlg_layout.setContentsMargins(16, 16, 16, 16)
        dlg_layout.setSpacing(12)

        lbl = QLabel("Sélectionnez un modèle de workflow à instancier :")
        lbl.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
        dlg_layout.addWidget(lbl)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll_w = QWidget()
        scroll_l = QVBoxLayout(scroll_w)
        scroll_l.setSpacing(10)

        for tpl in PRESET_TEMPLATES:
            card = QFrame()
            card.setStyleSheet(f"""
                QFrame {{
                    background: {DesignTokens.BG_PANEL};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: 6px;
                    padding: 10px;
                }}
                QFrame:hover {{
                    border-color: {DesignTokens.ACCENT_PRIMARY};
                }}
            """)
            c_l = QVBoxLayout(card)
            c_l.setSpacing(4)
            lbl_t = QLabel(f"<b>{tpl['name']}</b>")
            lbl_t.setStyleSheet(f"font-size: 13px; color: {DesignTokens.TEXT_PRIMARY};")
            lbl_d = QLabel(tpl["description"])
            lbl_d.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_MUTED};")
            lbl_d.setWordWrap(True)

            btn_use = SecondaryButton("Instancier ce Modèle")
            btn_use.setIcon(load_phosphor_icon("ph.plus", color=DesignTokens.TEXT_PRIMARY))

            def _instantiate(t=tpl):
                self._apply_preset_template(t)
                dlg.accept()

            btn_use.clicked.connect(_instantiate)

            c_l.addWidget(lbl_t)
            c_l.addWidget(lbl_d)
            c_l.addWidget(btn_use, alignment=Qt.AlignmentFlag.AlignRight)
            scroll_l.addWidget(card)

        scroll_l.addStretch()
        scroll.setWidget(scroll_w)
        dlg_layout.addWidget(scroll, 1)

        dlg.exec()

    def _apply_preset_template(self, tpl: dict) -> None:
        """Applique un modèle prédéfini sous forme d'un nouveau pipeline."""
        pipe_name = f"{tpl['name']} (Instancié)"
        try:
            new_pipe = PipelineModel.create(name=pipe_name, description=tpl["description"])
            for idx, s in enumerate(tpl["steps"], start=1):
                p_obj = self._cached_personas[0] if self._cached_personas else None
                PipelineStepModel.create(
                    pipeline=new_pipe,
                    persona=p_obj if s["type"] in ("LLM_PROMPT", "MAP_REDUCE") else None,
                    step_type=s["type"],
                    step_order=idx,
                    config_data=json.dumps(s.get("config", {})),
                )
            show_toast(self, f"Modèle '{tpl['name']}' instancié !", is_error=False)
            self.refresh_data()
            for i in range(self.pipeline_combo.count()):
                if self.pipeline_combo.itemText(i) == pipe_name:
                    self.pipeline_combo.setCurrentIndex(i)
                    break
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible d'instancier le modèle : {e}")

    def _on_export_json(self) -> None:
        if not self._current_pipeline:
            return
        data = {
            "name": self._current_pipeline.name,
            "description": self._current_pipeline.description,
            "steps": [
                {
                    "type": s.get("type", "LLM_PROMPT"),
                    "persona_name": s["persona"].name if s.get("persona") else None,
                    "custom_title": s.get("custom_title"),
                    "on_success_order": s.get("on_success_order"),
                    "on_failure_order": s.get("on_failure_order"),
                    "failure_behavior": s.get("failure_behavior", "stop"),
                    "config": s.get("config", {}),
                }
                for s in self.current_steps
            ],
        }
        file_path, _ = QFileDialog.getSaveFileName(self, "Exporter le Pipeline en JSON", f"{self._current_pipeline.name}.json", "Fichiers JSON (*.json)")
        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                show_toast(self, "Pipeline exporté en JSON avec succès !", is_error=False)
            except Exception as e:
                QMessageBox.critical(self, "Erreur d'exportation", str(e))

    def _on_import_json(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "Importer un Pipeline JSON", "", "Fichiers JSON (*.json)")
        if not file_path:
            return
        try:
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)

            name = data.get("name", "Pipeline Importé")
            base_name = name
            cnt = 1
            while PipelineModel.get_or_none(PipelineModel.name == name):
                name = f"{base_name} ({cnt})"
                cnt += 1

            new_pipe = PipelineModel.create(name=name, description=data.get("description", "Importé"))
            for idx, s in enumerate(data.get("steps", []), start=1):
                p_match = None
                p_name = s.get("persona_name")
                if p_name:
                    p_match = PersonaModel.get_or_none(PersonaModel.name == p_name)

                PipelineStepModel.create(
                    pipeline=new_pipe,
                    persona=p_match,
                    step_type=s.get("type", "LLM_PROMPT"),
                    step_order=idx,
                    failure_behavior=s.get("failure_behavior", "stop"),
                    config_data=json.dumps(s.get("config", {})),
                )

            show_toast(self, f"Pipeline '{name}' importé avec succès !", is_error=False)
            self.refresh_data()
            for i in range(self.pipeline_combo.count()):
                if self.pipeline_combo.itemText(i) == name:
                    self.pipeline_combo.setCurrentIndex(i)
                    break
        except Exception as e:
            QMessageBox.critical(self, "Erreur d'importation", f"Fichier JSON invalide : {e}")
