import json
import logging

import qtawesome as qta
from PySide6.QtCore import Qt, QUrl, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import AgentModel, LLMConfigModel, NoteTypeModel, PipelineModel, PipelineStepModel
from ankiforge.services.ai.flexible_service import AIManager
from ankiforge.services.ai.utils import format_system_prompt, AIReponseParser
from ankiforge.services.workers.ab_worker import AbWorker
from ankiforge.ui.components.components import ActionButton, DangerButton, DBComboBox, HeaderLabel, PrimaryButton, RoundedPanel
from ankiforge.ui.theme import is_dark_mode
from ankiforge.ui.widgets.safe_web_preview import SafeWebEngineView
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.anki_renderer import render_anki_card
from ankiforge.utils.paths import get_app_data_dir

logger = logging.getLogger(__name__)


class ABTestTab(QWidget):
    """
    Laboratoire A/B permettant de comparer deux moteurs IA ou deux invites (prompts/pipelines).
    Affiche les cartes générées avec une navigation par pagination.
    """

    def __init__(self) -> None:
        super().__init__()

        # État interne pour la pagination
        self.worker_thread: AbWorker | None = None
        self.action_list: list[tuple[str, str]] = []
        self.llm_list: list[tuple[str, int]] = []

        self.last_res_a = ""
        self.notes_a: list[dict] = []
        self.idx_a = 0

        self.last_res_b = ""
        self.notes_b: list[dict] = []
        self.idx_b = 0

        self._setup_ui()
        self._connect_signals()

        self.refresh_data()

    def _setup_ui(self) -> None:
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(15)

        self._build_header()
        self._build_mode_panel()
        self._build_source_panel()
        self._build_arena_panel()
        self._build_controls_panel()

    def _build_header(self) -> None:
        header_layout = QHBoxLayout()
        header_layout.addWidget(HeaderLabel("Laboratoire A/B (Prompt Engineering)"))
        self.main_layout.addLayout(header_layout)

    def _build_mode_panel(self) -> None:
        mode_panel = RoundedPanel()
        mode_layout = QHBoxLayout(mode_panel)

        mode_layout.addWidget(QLabel("<b>Mode :</b>"))
        self.cb_mode = QComboBox()
        self.cb_mode.addItems(["Comparer deux Moteurs IA", "Comparer deux Prompts / Pipelines"])
        mode_layout.addWidget(self.cb_mode, stretch=1)

        self.lbl_global_config = QLabel("<b>Global :</b>")
        mode_layout.addSpacing(10)
        mode_layout.addWidget(self.lbl_global_config)
        self.cb_global_config = QComboBox()
        self.cb_global_config.setMinimumWidth(150)
        mode_layout.addWidget(self.cb_global_config, stretch=1)

        mode_layout.addSpacing(10)
        mode_layout.addWidget(QLabel("<b>Modèle :</b>"))
        self.cb_model = DBComboBox(NoteTypeModel)
        self.cb_model.setMinimumWidth(120)
        mode_layout.addWidget(self.cb_model, stretch=1)

        mode_layout.addSpacing(10)
        self.cb_template = QComboBox()
        mode_layout.addWidget(self.cb_template)

        self.cb_side = QComboBox()
        self.cb_side.addItems(["Voir Recto", "Voir Verso"])
        mode_layout.addWidget(self.cb_side)

        self.main_layout.addWidget(mode_panel)

    def _build_source_panel(self) -> None:
        source_layout = QVBoxLayout()
        source_layout.addWidget(QLabel("<b>Texte Source :</b>"))
        self.text_source = QTextEdit()
        self.text_source.setPlaceholderText("Collez ici l'extrait de cours à tester...")
        self.text_source.setMaximumHeight(80)
        source_layout.addWidget(self.text_source)
        self.main_layout.addLayout(source_layout)

    def _create_arena_side(self, title_label: QLabel, cb_config: QComboBox):
        panel = RoundedPanel()
        p_layout = QVBoxLayout(panel)
        p_layout.setContentsMargins(10, 10, 10, 10)

        header = QHBoxLayout()
        header.addWidget(title_label)
        header.addWidget(cb_config, stretch=1)
        p_layout.addLayout(header)

        tabs = QTabWidget()
        tabs.setStyleSheet("QTabBar::tab { padding: 8px 15px; }")

        # --- Onglet Rendu avec Pagination ---
        render_tab = QWidget()
        render_layout = QVBoxLayout(render_tab)
        render_layout.setContentsMargins(0, 5, 0, 0)

        nav_layout = QHBoxLayout()
        btn_prev = ActionButton("fa5s.chevron-left", "")
        btn_prev.setEnabled(False)
        lbl_counter = QLabel("0 / 0")
        lbl_counter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_counter.setStyleSheet("font-weight: bold; color: palette(placeholder-text);")
        btn_next = ActionButton("fa5s.chevron-right", "")
        btn_next.setEnabled(False)

        nav_layout.addWidget(btn_prev)
        nav_layout.addWidget(lbl_counter, stretch=1)
        nav_layout.addWidget(btn_next)

        web_view = SafeWebEngineView()

        render_layout.addLayout(nav_layout)
        render_layout.addWidget(web_view)

        tabs.addTab(render_tab, qta.icon("fa5s.eye"), "Rendu Cartes")

        # --- Onglet JSON Brut ---
        raw_text = QTextEdit()
        raw_text.setReadOnly(True)
        raw_text.setFrameShape(QFrame.Shape.NoFrame)
        raw_text.setStyleSheet("font-family: monospace; background-color: palette(base);")
        tabs.addTab(raw_text, qta.icon("fa5s.code"), "JSON Brut")

        p_layout.addWidget(tabs)
        return panel, web_view, raw_text, btn_prev, btn_next, lbl_counter

    def _build_arena_panel(self) -> None:
        self.arena_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.arena_splitter.setHandleWidth(10)
        self.arena_splitter.setChildrenCollapsible(False)

        self.lbl_a_config = QLabel("<b>A :</b>")
        self.cb_config_a = QComboBox()
        panel_a, self.web_a, self.raw_a, self.btn_prev_a, self.btn_next_a, self.lbl_count_a = self._create_arena_side(self.lbl_a_config, self.cb_config_a)
        self.arena_splitter.addWidget(panel_a)

        self.lbl_b_config = QLabel("<b>B :</b>")
        self.cb_config_b = QComboBox()
        panel_b, self.web_b, self.raw_b, self.btn_prev_b, self.btn_next_b, self.lbl_count_b = self._create_arena_side(self.lbl_b_config, self.cb_config_b)
        self.arena_splitter.addWidget(panel_b)

        self.main_layout.addWidget(self.arena_splitter, stretch=1)

    def _build_controls_panel(self) -> None:
        bottom_layout = QHBoxLayout()

        self.lbl_status = QLabel("Prêt.")
        self.lbl_status.setStyleSheet("color: palette(placeholder-text);")

        self.btn_run = PrimaryButton(qta.icon("fa5s.play", color="white"), " Lancer la Comparaison")
        self.btn_cancel = DangerButton(qta.icon("fa5s.stop", color="white"), " Annuler")
        self.btn_cancel.hide()

        bottom_layout.addWidget(self.lbl_status)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.btn_cancel)
        bottom_layout.addWidget(self.btn_run)

        self.main_layout.addLayout(bottom_layout)

    def _connect_signals(self) -> None:
        self.cb_mode.currentIndexChanged.connect(self._on_mode_changed)
        self.cb_model.currentIndexChanged.connect(self._on_model_changed)
        self.cb_template.currentIndexChanged.connect(self._on_preview_changed)
        self.cb_side.currentIndexChanged.connect(self._on_preview_changed)

        self.btn_run.clicked.connect(self.run_ab_test)
        self.btn_cancel.clicked.connect(self.cancel_test)

        # Pagination
        self.btn_prev_a.clicked.connect(lambda: self._navigate_a(-1))
        self.btn_next_a.clicked.connect(lambda: self._navigate_a(1))
        self.btn_prev_b.clicked.connect(lambda: self._navigate_b(-1))
        self.btn_next_b.clicked.connect(lambda: self._navigate_b(1))

    @Slot()
    def refresh_data(self) -> None:
        self.llm_list = [(llm.display_name, llm.id) for llm in LLMConfigModel.select().order_by(LLMConfigModel.display_name)]
        agents = [("[Agent] " + a.name, f"agent_{a.id}") for a in AgentModel.select().order_by(AgentModel.name)]
        pipes = [("[Pipeline] " + p.name, f"pipe_{p.id}") for p in PipelineModel.select().order_by(PipelineModel.name)]
        self.action_list = agents + pipes

        self.cb_model.refresh_data()
        self._on_model_changed()
        self._on_mode_changed()

    @Slot()
    def _on_mode_changed(self) -> None:
        mode = self.cb_mode.currentIndex()
        self.cb_global_config.blockSignals(True)
        self.cb_config_a.blockSignals(True)
        self.cb_config_b.blockSignals(True)

        self.cb_global_config.clear()
        self.cb_config_a.clear()
        self.cb_config_b.clear()

        if mode == 0:
            self.lbl_global_config.setText("<b>Prompt/Pipe :</b>")
            self.lbl_a_config.setText("<b>Moteur A :</b>")
            self.lbl_b_config.setText("<b>Moteur B :</b>")
            for name, uid_str in self.action_list:
                self.cb_global_config.addItem(name, userData=uid_str)
            for name, uid in self.llm_list:
                self.cb_config_a.addItem(name, userData=uid)
                self.cb_config_b.addItem(name, userData=uid)
        else:
            self.lbl_global_config.setText("<b>Moteur :</b>")
            self.lbl_a_config.setText("<b>A (Prompt/Pipe) :</b>")
            self.lbl_b_config.setText("<b>B (Prompt/Pipe) :</b>")
            for name, uid in self.llm_list:
                self.cb_global_config.addItem(name, userData=uid)
            for name, uid_str in self.action_list:
                self.cb_config_a.addItem(name, userData=uid_str)
                self.cb_config_b.addItem(name, userData=uid_str)

        self.cb_global_config.blockSignals(False)
        self.cb_config_a.blockSignals(False)
        self.cb_config_b.blockSignals(False)

    @Slot()
    def _on_model_changed(self):
        model_id = self.cb_model.currentData()
        self.cb_template.blockSignals(True)
        self.cb_template.clear()

        if model_id:
            note_type = NoteTypeModel.get_by_id(model_id)
            templates = json.loads(note_type.templates) if note_type.templates else []
            for tmpl in templates:
                self.cb_template.addItem(tmpl.get("name", "Carte"))

        self.cb_template.blockSignals(False)
        self._on_preview_changed()

    def _get_prompts_chain(self, item_id_str: str, nt_schema: str) -> list[str]:
        parts = item_id_str.split("_")
        item_type = parts[0]
        uid = int(parts[1])

        if item_type == "agent":
            agent = AgentModel.get_by_id(uid)
            return [format_system_prompt(agent.system_prompt, nt_schema)]
        elif item_type == "pipe":
            pipe = PipelineModel.get_by_id(uid)
            chain = []
            for step in pipe.steps.order_by(PipelineStepModel.step_order):
                chain.append(format_system_prompt(step.agent.system_prompt, nt_schema))
            return chain
        return []

    def _extract_notes_from_json(self, raw_json: str) -> list[dict]:
        """Extrait la liste des notes du JSON de manière sécurisée."""
        try:
            data = AIReponseParser.parse(raw_json)
            notes = data.get("notes", []) if isinstance(data, dict) else data
            if isinstance(notes, list):
                return notes
        except json.JSONDecodeError:
            logger.debug("JSON invalide : %s", raw_json)
        return []

    # --- MÉTHODES DE NAVIGATION ET RENDU ---

    def _navigate_a(self, step: int):
        self.idx_a += step
        self._update_render_a()

    def _navigate_b(self, step: int):
        self.idx_b += step
        self._update_render_b()

    @Slot()
    def _on_preview_changed(self):
        self._update_render_a()
        self._update_render_b()

    def _update_render_a(self):
        self._render_single_note(self.notes_a, self.idx_a, self.web_a, self.btn_prev_a, self.btn_next_a, self.lbl_count_a, self.last_res_a)

    def _update_render_b(self):
        self._render_single_note(self.notes_b, self.idx_b, self.web_b, self.btn_prev_b, self.btn_next_b, self.lbl_count_b, self.last_res_b)

    def _render_single_note(self, notes_list: list[dict], current_idx: int, web_view: SafeWebEngineView, btn_prev: ActionButton, btn_next: ActionButton, lbl_counter: QLabel, raw_json: str):
        """Affiche uniquement la carte sélectionnée avec les contrôles de pagination et corrige les clés JSON."""
        if not notes_list:
            btn_prev.setEnabled(False)
            btn_next.setEnabled(False)
            lbl_counter.setText("0 / 0")

            if raw_json:
                err_html = "<div style='text-align:center; padding:20px; color:#F44336;'>Aucune carte valide trouvée dans le JSON.</div>"
                web_view.setHtmlSafe(err_html)
            else:
                web_view.setHtmlSafe("")
            return

        # Mise à jour des boutons
        btn_prev.setEnabled(current_idx > 0)
        btn_next.setEnabled(current_idx < len(notes_list) - 1)
        lbl_counter.setText(f"Carte {current_idx + 1} / {len(notes_list)}")

        try:
            note_type = NoteTypeModel.get_by_id(self.cb_model.currentData())
            templates = json.loads(note_type.templates) if note_type.templates else []
            if not templates:
                raise ValueError("Ce modèle Anki n'a pas de template HTML.")

            tmpl_idx = self.cb_template.currentIndex()
            if tmpl_idx < 0 or tmpl_idx >= len(templates):
                return

            tmpl = templates[tmpl_idx]
            css = note_type.css_style if note_type.css_style else ""
            is_recto = self.cb_side.currentIndex() == 0
            raw_html = tmpl.get("qfmt", "") if is_recto else tmpl.get("afmt", "")

            # Formater les données de la carte courante
            current_note = dict(notes_list[current_idx])

            # --- PATCH AUTO-MAPPING POUR LES IA RÉCALCITRANTES (Ollama/Mistral) ---
            expected_fields = json.loads(note_type.fields_schema) if note_type.fields_schema else []
            actual_keys = list(current_note.keys())

            # Si les clés générées ne correspondent pas du tout au modèle attendu
            if expected_fields and actual_keys and actual_keys[0] not in expected_fields:
                mapped_note = {}
                for i, expected_name in enumerate(expected_fields):
                    if i < len(actual_keys):
                        # On force le mappage: 1ère clé générée -> 1er champ attendu, etc.
                        mapped_note[expected_name] = current_note[actual_keys[i]]
                    else:
                        mapped_note[expected_name] = ""
                current_note = mapped_note
            # ----------------------------------------------------------------------

            for k, v in current_note.items():
                if isinstance(v, list):
                    current_note[k] = "<br>".join([str(i) for i in v])

            final_html = render_anki_card(
                raw_html=raw_html,
                css=css,
                fields_dict=current_note,
                is_recto=is_recto,
                front_html=tmpl.get("qfmt", ""),
                is_dark_mode=is_dark_mode(),
            )

            media_dir = get_app_data_dir() / "media"
            web_view.setHtmlSafe(final_html, QUrl.fromLocalFile(media_dir))

        except Exception as e:
            logger.exception("Erreur lors du rendu de la note :")
            err_html = f"<div style='text-align:center; padding:20px; color:#F44336;'><h3>Erreur de rendu</h3><p>{str(e)}</p></div>"
            web_view.setHtmlSafe(err_html)

    # --- LANCEMENT ET RECEPTION DES RÉSULTATS ---

    @Slot()
    def run_ab_test(self) -> None:
        source_text = self.text_source.toPlainText().strip()
        model_id = self.cb_model.currentData()

        if not source_text:
            show_toast(self, "Veuillez entrer du texte source.", is_error=True)
            return

        mode = self.cb_mode.currentIndex()

        try:
            nt_schema = NoteTypeModel.get_by_id(model_id).fields_schema

            if mode == 0:
                prompts_a = prompts_b = self._get_prompts_chain(self.cb_global_config.currentData(), nt_schema)
                provider_a = AIManager.create_provider_from_config(LLMConfigModel.get_by_id(self.cb_config_a.currentData()))
                provider_b = AIManager.create_provider_from_config(LLMConfigModel.get_by_id(self.cb_config_b.currentData()))
            else:
                prompts_a = self._get_prompts_chain(self.cb_config_a.currentData(), nt_schema)
                prompts_b = self._get_prompts_chain(self.cb_config_b.currentData(), nt_schema)
                provider_a = provider_b = AIManager.create_provider_from_config(LLMConfigModel.get_by_id(self.cb_global_config.currentData()))

        except Exception as e:
            logger.exception("Configuration incomplète pour le test A/B :")
            show_toast(self, f"Configuration incomplète : {e}", is_error=True)
            return

        self.btn_run.hide()
        self.btn_cancel.show()
        self.btn_cancel.setEnabled(True)

        self.raw_a.clear()
        self.raw_b.clear()

        # Réinitialisation de la navigation
        self.notes_a = []
        self.idx_a = 0
        self._update_render_a()

        self.notes_b = []
        self.idx_b = 0
        self._update_render_b()

        self.worker_thread = AbWorker(provider_a, provider_b, prompts_a, prompts_b, source_text)
        self.worker_thread.progress.connect(self.lbl_status.setText)
        self.worker_thread.result_a.connect(self._on_result_a)
        self.worker_thread.result_b.connect(self._on_result_b)
        self.worker_thread.finished_signal.connect(self._on_test_finished)
        self.worker_thread.error_signal.connect(self._on_test_error)
        self.worker_thread.cancelled.connect(self._on_test_cancelled)

        self.worker_thread.start()

    @Slot(str)
    def _on_result_a(self, text: str):
        self.last_res_a = text
        self.raw_a.setPlainText(text)
        self.notes_a = self._extract_notes_from_json(text)
        self.idx_a = 0
        self._update_render_a()

    @Slot(str)
    def _on_result_b(self, text: str):
        self.last_res_b = text
        self.raw_b.setPlainText(text)
        self.notes_b = self._extract_notes_from_json(text)
        self.idx_b = 0
        self._update_render_b()

    @Slot()
    def cancel_test(self) -> None:
        if self.worker_thread is not None and self.worker_thread.isRunning():
            self.worker_thread.cancel()
            self.btn_cancel.setEnabled(False)
            self.lbl_status.setText("Arrêt en cours...")

    @Slot()
    def _on_test_finished(self) -> None:
        self._reset_ui()
        self.lbl_status.setText("✅ Test terminé. Observez les différences !")

    @Slot(str)
    def _on_test_error(self, err: str) -> None:
        self._reset_ui()
        self.lbl_status.setText("❌ Erreur.")
        show_toast(self, f"Erreur IA : {err}", is_error=True)

    @Slot()
    def _on_test_cancelled(self) -> None:
        self._reset_ui()
        self.lbl_status.setText("🛑 Test annulé.")

    def _reset_ui(self) -> None:
        self.btn_cancel.hide()
        self.btn_run.show()
        self.btn_cancel.setEnabled(True)
