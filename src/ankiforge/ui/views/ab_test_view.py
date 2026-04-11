import json
import os
from typing import Any

import qtawesome as qta
from PySide6.QtCore import Qt, QThread, Signal, Slot, QUrl
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTextEdit,
    QComboBox,
    QSplitter,
    QFrame,
    QTabWidget,
)
from jinja2 import Template

from ankiforge.database.models import LLMConfigModel, AgentModel, NoteTypeModel
from ankiforge.services.ai.utils import parse_ai_json_response
from ankiforge.ui.components.components import PrimaryButton, RoundedPanel, DangerButton, HeaderLabel
from ankiforge.ui.theme import is_dark_mode
from ankiforge.ui.widgets.safe_web_preview import SafeWebEngineView
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.anki_renderer import render_anki_card
from ankiforge.utils.paths import get_app_data_dir


class ABTestThread(QThread):
    progress = Signal(str)
    result_a = Signal(str)
    result_b = Signal(str)
    finished_signal = Signal()
    error_signal = Signal(str)
    cancelled = Signal()

    def __init__(self, provider_a: Any, provider_b: Any, prompt_a: str, prompt_b: str, source_text: str):
        super().__init__()
        self.provider_a = provider_a
        self.provider_b = provider_b
        self.prompt_a = prompt_a
        self.prompt_b = prompt_b
        self.source_text = source_text
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            user_input = f"TEXTE SOURCE :\n{self.source_text}"

            if self._is_cancelled:
                self.cancelled.emit()
                return

            self.progress.emit("⏳ Sujet A en cours de génération...")
            res_a = self.provider_a.generate(system_prompt=self.prompt_a, user_prompt=user_input)

            if self._is_cancelled:
                self.cancelled.emit()
                return
            self.result_a.emit(res_a)

            self.progress.emit("⏳ Sujet B en cours de génération...")
            res_b = self.provider_b.generate(system_prompt=self.prompt_b, user_prompt=user_input)

            if self._is_cancelled:
                self.cancelled.emit()
                return
            self.result_b.emit(res_b)

            self.finished_signal.emit()

        except Exception as e:
            self.error_signal.emit(str(e))


class ABTestTab(QWidget):
    def __init__(self) -> None:
        super().__init__()

        # Stockage des derniers résultats pour pouvoir changer de vue (Recto/Verso) sans relancer l'IA
        self.thread: ABTestThread | None = None
        self.agent_list: list[tuple[str, int]] = []
        self.llm_list: list[tuple[str, int]] = []

        self.last_res_a = ""
        self.last_res_b = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        header_layout = QHBoxLayout()
        header_layout.addWidget(HeaderLabel("🧪 Laboratoire A/B (Prompt Engineering)"))
        layout.addLayout(header_layout)

        # --- MODE DE TEST & CIBLE ---
        mode_panel = RoundedPanel()
        mode_layout = QHBoxLayout(mode_panel)

        mode_layout.addWidget(QLabel("<b>Mode :</b>"))
        self.cb_mode = QComboBox()
        self.cb_mode.addItems(["Comparer deux Moteurs IA", "Comparer deux Prompts"])
        self.cb_mode.currentIndexChanged.connect(self._on_mode_changed)
        mode_layout.addWidget(self.cb_mode, stretch=1)

        self.lbl_global_config = QLabel("<b>Global :</b>")
        mode_layout.addSpacing(10)
        mode_layout.addWidget(self.lbl_global_config)
        self.cb_global_config = QComboBox()
        self.cb_global_config.setMinimumWidth(150)
        mode_layout.addWidget(self.cb_global_config, stretch=1)

        # 👇 NOUVEAU : Sélection du modèle de note 👇
        mode_layout.addSpacing(10)
        mode_layout.addWidget(QLabel("<b>Modèle :</b>"))
        self.cb_model = QComboBox()
        self.cb_model.setMinimumWidth(120)
        self.cb_model.currentIndexChanged.connect(self._on_model_changed)
        mode_layout.addWidget(self.cb_model, stretch=1)

        # 👇 NOUVEAU : Contrôles d'aperçu (Recto/Verso) 👇
        mode_layout.addSpacing(10)
        self.cb_template = QComboBox()
        self.cb_template.currentIndexChanged.connect(self._on_preview_changed)
        mode_layout.addWidget(self.cb_template)

        self.cb_side = QComboBox()
        self.cb_side.addItems(["Voir Recto", "Voir Verso"])
        self.cb_side.currentIndexChanged.connect(self._on_preview_changed)
        mode_layout.addWidget(self.cb_side)

        layout.addWidget(mode_panel)

        # --- TEXTE SOURCE ---
        source_layout = QVBoxLayout()
        source_layout.addWidget(QLabel("<b>Texte Source :</b>"))
        self.text_source = QTextEdit()
        self.text_source.setPlaceholderText("Collez ici l'extrait de cours à tester...")
        self.text_source.setMaximumHeight(80)
        source_layout.addWidget(self.text_source)
        layout.addLayout(source_layout)

        # --- L'ARÈNE (SPLITTER A/B) ---
        self.arena_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.arena_splitter.setHandleWidth(10)
        self.arena_splitter.setChildrenCollapsible(False)

        # Helper pour créer un côté de l'arène (A ou B)
        def create_arena_side(title_label, cb_config):
            panel = RoundedPanel()
            p_layout = QVBoxLayout(panel)
            p_layout.setContentsMargins(10, 10, 10, 10)

            header = QHBoxLayout()
            header.addWidget(title_label)
            header.addWidget(cb_config, stretch=1)
            p_layout.addLayout(header)

            tabs = QTabWidget()
            tabs.setStyleSheet("QTabBar::tab { padding: 8px 15px; }")

            # Onglet 1 : Aperçu visuel
            web_view = SafeWebEngineView()
            tabs.addTab(web_view, qta.icon("fa5s.eye"), "Rendu Carte")

            # Onglet 2 : JSON Brut
            raw_text = QTextEdit()
            raw_text.setReadOnly(True)
            raw_text.setFrameShape(QFrame.Shape.NoFrame)
            raw_text.setStyleSheet("font-family: monospace; background-color: palette(base);")
            tabs.addTab(raw_text, qta.icon("fa5s.code"), "JSON Brut")

            p_layout.addWidget(tabs)
            return panel, web_view, raw_text

        self.lbl_a_config = QLabel("<b>A :</b>")
        self.cb_config_a = QComboBox()
        panel_a, self.web_a, self.raw_a = create_arena_side(self.lbl_a_config, self.cb_config_a)
        self.arena_splitter.addWidget(panel_a)

        self.lbl_b_config = QLabel("<b>B :</b>")
        self.cb_config_b = QComboBox()
        panel_b, self.web_b, self.raw_b = create_arena_side(self.lbl_b_config, self.cb_config_b)
        self.arena_splitter.addWidget(panel_b)

        layout.addWidget(self.arena_splitter, stretch=1)

        # --- CONTRÔLES (BARRE DU BAS) ---
        bottom_layout = QHBoxLayout()
        self.lbl_status = QLabel("Prêt.")
        self.lbl_status.setStyleSheet("color: palette(placeholder-text);")

        self.btn_run = PrimaryButton(qta.icon("fa5s.play", color="white"), " Lancer la Comparaison")
        self.btn_run.clicked.connect(self.run_ab_test)

        self.btn_cancel = DangerButton(qta.icon("fa5s.stop", color="white"), " Annuler")
        self.btn_cancel.clicked.connect(self.cancel_test)
        self.btn_cancel.hide()

        bottom_layout.addWidget(self.lbl_status)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.btn_cancel)
        bottom_layout.addWidget(self.btn_run)
        layout.addLayout(bottom_layout)

        self.refresh_data()

    @Slot()
    def refresh_data(self) -> None:
        self.llm_list = [(llm.display_name, llm.id) for llm in LLMConfigModel.select().order_by(LLMConfigModel.display_name)]
        self.agent_list = [(agent.name, agent.id) for agent in AgentModel.select().order_by(AgentModel.name)]

        self.cb_model.blockSignals(True)
        self.cb_model.clear()
        for nt in NoteTypeModel.select().order_by(NoteTypeModel.name):
            self.cb_model.addItem(nt.name, userData=nt.id)
        self.cb_model.blockSignals(False)

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
            self.lbl_global_config.setText("<b>Prompt :</b>")
            self.lbl_a_config.setText("<b>Moteur A :</b>")
            self.lbl_b_config.setText("<b>Moteur B :</b>")
            for name, uid in self.agent_list:
                self.cb_global_config.addItem(name, userData=uid)
            for name, uid in self.llm_list:
                self.cb_config_a.addItem(name, userData=uid)
                self.cb_config_b.addItem(name, userData=uid)
        else:
            self.lbl_global_config.setText("<b>Moteur :</b>")
            self.lbl_a_config.setText("<b>Prompt A :</b>")
            self.lbl_b_config.setText("<b>Prompt B :</b>")
            for name, uid in self.llm_list:
                self.cb_global_config.addItem(name, userData=uid)
            for name, uid in self.agent_list:
                self.cb_config_a.addItem(name, userData=uid)
                self.cb_config_b.addItem(name, userData=uid)

        self.cb_global_config.blockSignals(False)
        self.cb_config_a.blockSignals(False)
        self.cb_config_b.blockSignals(False)

    @Slot()
    def _on_model_changed(self):
        """Met à jour la liste des types de cartes (Carte 1, Carte 2...) quand on change de modèle."""
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

    @Slot()
    def _on_preview_changed(self):
        """Relance le rendu web des deux côtés quand on bascule Recto/Verso ou de Carte."""
        if self.last_res_a:
            self._render_preview(self.last_res_a, self.web_a)
        if self.last_res_b:
            self._render_preview(self.last_res_b, self.web_b)

    @staticmethod
    def _instantiate_provider(llm_id: int) -> Any:
        llm_config = LLMConfigModel.get_by_id(llm_id)
        p_name = llm_config.provider.lower()
        if p_name == "ollama":
            from ankiforge.services.ai.flexible_service import OllamaProvider

            return OllamaProvider(model_name=llm_config.model_id)
        elif p_name == "gemini":
            from ankiforge.services.ai.gemini_service import GeminiService

            return GeminiService(model_name=llm_config.model_id)
        elif p_name == "groq":
            from ankiforge.services.ai.flexible_service import GroqProvider

            return GroqProvider(model_name=llm_config.model_id)
        elif p_name == "openai":
            from ankiforge.services.ai.flexible_service import OpenAICompatibleProvider

            return OpenAICompatibleProvider(
                base_url="https://api.openai.com/v1",
                model_name=llm_config.model_id,
                api_key=os.environ.get("OPENAI_API_KEY", ""),
            )

        from ankiforge.services.ai.base import MockProvider

        return MockProvider()

    @staticmethod
    def _prepare_prompt(agent_id: int, note_type_id: int) -> str:
        """Injecte dynamiquement les champs du modèle de note dans le prompt via Jinja2."""
        agent = AgentModel.get_by_id(agent_id)
        note_type = NoteTypeModel.get_by_id(note_type_id)
        fields = json.loads(note_type.fields_schema) if note_type.fields_schema else ["Front", "Back"]

        jinja_template = Template(agent.system_prompt)
        return jinja_template.render(
            fields_str='", "'.join(fields),
            first_field=fields[0] if len(fields) > 0 else "Field1",
            second_field=fields[1] if len(fields) > 1 else "Field2",
        )

    def _render_preview(self, raw_json: str, web_view: SafeWebEngineView):
        """Tente de parser le JSON et affiche la première carte générée."""
        try:
            data = parse_ai_json_response(raw_json)
            # Gestion si l'IA renvoie {"notes": [...]} ou juste [...]
            notes_list = data.get("notes", []) if isinstance(data, dict) else data

            if not isinstance(notes_list, list) or len(notes_list) == 0:
                raise ValueError("Aucune note trouvée dans le JSON.")

            first_note_data = notes_list[0]
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

            # Formatage des listes potentielles
            for k, v in first_note_data.items():
                if isinstance(v, list):
                    first_note_data[k] = "<br>".join([str(i) for i in v])

            raw_html = tmpl.get("qfmt", "") if is_recto else tmpl.get("afmt", "")

            final_html = render_anki_card(
                raw_html=raw_html,
                css=css,
                fields_dict=first_note_data,
                is_recto=is_recto,
                front_html=tmpl.get("qfmt", ""),
                is_dark_mode=is_dark_mode(),
            )

            media_dir = get_app_data_dir() / "media"
            web_view.setHtmlSafe(final_html, QUrl.fromLocalFile(media_dir))

        except Exception as e:
            err_html = f"""
            <div style='color: palette(text); font-family: sans-serif; padding: 20px; text-align: center;'>
                <h3 style='color: #F44336;'>Erreur de rendu</h3>
                <p>L'IA n'a pas généré un JSON valide ou compatible avec le modèle '{self.cb_model.currentText()}'.</p>
                <p style='font-size: 12px; color: palette(placeholder-text);'>{str(e)}</p>
                <p><i>Vérifiez l'onglet 'JSON Brut'.</i></p>
            </div>
            """
            web_view.setHtmlSafe(err_html)

    @Slot()
    def run_ab_test(self) -> None:
        source_text = self.text_source.toPlainText().strip()
        model_id = self.cb_model.currentData()

        if not source_text:
            show_toast(self, "Veuillez entrer du texte source.", is_error=True)
            return

        mode = self.cb_mode.currentIndex()

        try:
            if mode == 0:  # Moteurs
                prompt_a = prompt_b = self._prepare_prompt(self.cb_global_config.currentData(), model_id)
                provider_a = self._instantiate_provider(self.cb_config_a.currentData())
                provider_b = self._instantiate_provider(self.cb_config_b.currentData())
            else:  # Prompts
                provider_a = provider_b = self._instantiate_provider(self.cb_global_config.currentData())
                prompt_a = self._prepare_prompt(self.cb_config_a.currentData(), model_id)
                prompt_b = self._prepare_prompt(self.cb_config_b.currentData(), model_id)
        except Exception as e:
            show_toast(self, f"Configuration incomplète : {e}", is_error=True)
            return

        self.btn_run.hide()
        self.btn_cancel.show()
        self.btn_cancel.setEnabled(True)

        self.raw_a.clear()
        self.raw_b.clear()
        self.web_a.clear_memory()
        self.web_b.clear_memory()

        self.thread = ABTestThread(provider_a, provider_b, prompt_a, prompt_b, source_text)
        self.thread.progress.connect(self.lbl_status.setText)

        # On intercepte les résultats pour les sauvegarder et lancer le rendu
        self.thread.result_a.connect(self._on_result_a)
        self.thread.result_b.connect(self._on_result_b)

        self.thread.finished_signal.connect(self._on_test_finished)
        self.thread.error_signal.connect(self._on_test_error)
        self.thread.cancelled.connect(self._on_test_cancelled)

        self.thread.start()

    @Slot(str)
    def _on_result_a(self, text: str):
        self.last_res_a = text
        self.raw_a.setPlainText(text)
        self._render_preview(text, self.web_a)

    @Slot(str)
    def _on_result_b(self, text: str):
        self.last_res_b = text
        self.raw_b.setPlainText(text)
        self._render_preview(text, self.web_b)

    @Slot()
    def cancel_test(self) -> None:
        if self.thread is not None and self.thread.isRunning():
            self.thread.cancel()
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
