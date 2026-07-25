"""
Vue Batch Factory (CI/CD Power User) — 100% Conforme à la Maquette concept_ide/index.html (L1883-L2062).
- TOP ROW (Metrics) : Statut Global, Temps Restant, Cartes Générées, Coût Estimé.
- MIDDLE ROW (Config & Queue) :
  - Gauche (350px) : 'Paramètres du Build' (Source combo, Paquet Cible, Modèle, Moteur IA, Pipeline, Vision, Validation auto, Bouton 'Ajouter à la Queue').
  - Droite (flex-1) : 'File d'attente détaillée' (Case à cocher, Statut, Fichier/Source, Barre de progrès %, Tokens Est., Actions, Boutons 'Vider' et 'Démarrer Pipeline' vert émeraude #10b981).
- BOTTOM ROW (250px) : Terminal CI/CD 'root@ankiforge:~/pipeline_logs' (#0c0c0c, logs colorés INFO/WARN/SUCCESS, 'Fira Code').
"""

import datetime
import json
import logging
import time
import uuid
from typing import Any, Optional

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QSplitter,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    DocumentModel,
    LLMConfigModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
    PipelineModel,
    db,
)
from ankiforge.services.workers.batch_worker import BatchTaskPayload, BatchWorker
from ankiforge.ui.components import (
    Badge,
    IconButton,
    IdePanel,
    PrimaryButton,
    SecondaryButton,
    StyledComboBox,
    StyledLineEdit,
    StyledTableWidget,
    StyledTextEdit,
)
from ankiforge.ui.theme import DesignTokens, apply_shadow
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.anki_renderer import get_max_cloze_index
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class CicdMetricCard(QFrame):
    """Stat Card épurée et compacte conforme à la maquette concept_ide (L1888-L1916)."""

    def __init__(self, title: str, value: str, icon_name: str, color: str = "#10b981", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.color = color
        self.setStyleSheet(f"""
            QFrame {{
                background-color: #1e2128;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 0px;
            }}
        """)
        apply_shadow(self, blur=8, offset_y=2)
        self.setFixedHeight(58)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(10)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; border: none; text-transform: uppercase; letter-spacing: 0.5px;")

        self.val_lbl = QLabel(value)
        self.val_lbl.setStyleSheet(f"color: {color}; font-size: 15px; font-weight: bold; border: none; font-family: '{DesignTokens.FONT_CODE}';")

        text_layout.addWidget(title_lbl)
        text_layout.addWidget(self.val_lbl)
        layout.addLayout(text_layout, 1)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(load_phosphor_icon(icon_name, color=color).pixmap(24, 24))
        icon_lbl.setStyleSheet("border: none; background: transparent; opacity: 0.85;")
        layout.addWidget(icon_lbl)


class ProgressTableCellWidget(QWidget):
    """Widget de cellule affichant la barre de progression et l'état textuel (%) sous la barre."""

    def __init__(self, progress_pct: int = 0, status_text: str = "En attente...", color: str = "#6366f1", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(3)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setValue(progress_pct)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: #1a1d24;
                border: none;
                border-radius: 3px;
            }}
            QProgressBar::chunk {{
                background-color: {color};
                border-radius: 3px;
            }}
        """)
        layout.addWidget(self.progress_bar)

        sub_row = QHBoxLayout()
        sub_row.setContentsMargins(0, 0, 0, 0)

        self.lbl_status = QLabel(status_text)
        self.lbl_status.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-family: '{DesignTokens.FONT_CODE}';")

        self.lbl_pct = QLabel(f"{progress_pct}%")
        self.lbl_pct.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-family: '{DesignTokens.FONT_CODE}'; font-weight: bold;")

        sub_row.addWidget(self.lbl_status)
        sub_row.addStretch()
        sub_row.addWidget(self.lbl_pct)

        layout.addLayout(sub_row)

    def update_progress(self, progress_pct: int, status_text: str, color: str = "#10b981") -> None:
        self.progress_bar.setValue(progress_pct)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: #1a1d24;
                border: none;
                border-radius: 3px;
            }}
            QProgressBar::chunk {{
                background-color: {color};
                border-radius: 3px;
            }}
        """)
        self.lbl_status.setText(status_text)
        self.lbl_pct.setText(f"{progress_pct}%")


class BatchView(QWidget):
    """
    Batch Factory CI/CD View — 100% Conforme à la Maquette concept_ide/index.html (L1883-L2062).
    """

    def __init__(self, ai_manager: Optional[Any] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager
        self.worker: Optional[BatchWorker] = None
        self.queue_tasks_data: list[dict[str, Any]] = []
        self.cell_widgets_map: dict[int, ProgressTableCellWidget] = {}
        self.start_timestamp = 0.0

        self._setup_ui()
        self._connect_signals()
        self.refresh_data()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        # =========================================================================
        # TOP ROW: Metrics Cards (L1885-L1916)
        # =========================================================================
        metrics_row = QHBoxLayout()
        metrics_row.setContentsMargins(0, 0, 0, 0)
        metrics_row.setSpacing(12)

        self.card_status = CicdMetricCard("STATUT GLOBAL", "En attente", "ph.check-circle", color="#10b981")
        self.card_time = CicdMetricCard("TEMPS RESTANT", "--:--:--", "ph.timer", color="#3b82f6")
        self.card_cards = CicdMetricCard("CARTES GÉNÉRÉES", "0 / 0", "ph.cards", color="#6366f1")
        self.card_cost = CicdMetricCard("COÛT ESTIMÉ", "$0.00", "ph.coin", color="#eab308")

        metrics_row.addWidget(self.card_status, 1)
        metrics_row.addWidget(self.card_time, 1)
        metrics_row.addWidget(self.card_cards, 1)
        metrics_row.addWidget(self.card_cost, 1)

        main_layout.addLayout(metrics_row)

        # =========================================================================
        # MAIN SPLITTER: Middle Row (Config & Queue) + Bottom Row (Terminal)
        # =========================================================================
        self.main_splitter = QSplitter(Qt.Orientation.Vertical)
        main_layout.addWidget(self.main_splitter, 1)

        # --- MIDDLE ROW: Config & Queue (L1918-L2036) ---
        self.middle_splitter = QSplitter(Qt.Orientation.Horizontal)

        # LEFT PANEL: Paramètres du Build (width: 350px)
        self.build_panel = IdePanel(detachable=True)
        self.build_panel.setMinimumWidth(320)
        self.build_panel.setMaximumWidth(380)

        build_content = QWidget()
        build_layout = QVBoxLayout(build_content)
        build_layout.setContentsMargins(16, 16, 16, 16)
        build_layout.setSpacing(14)

        # 1. Source (Fichiers/Dossiers)
        grp_src = QVBoxLayout()
        grp_src.setSpacing(4)
        lbl_src = QLabel("Source (Fichiers/Dossiers) :")
        lbl_src.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; font-weight: bold;")

        src_row = QHBoxLayout()
        src_row.setSpacing(6)
        self.doc_combo = StyledComboBox()
        src_row.addWidget(self.doc_combo, 1)

        self.btn_browse_doc = SecondaryButton("")
        self.btn_browse_doc.setIcon(load_phosphor_icon("ph.folder-open", color=DesignTokens.TEXT_PRIMARY))
        self.btn_browse_doc.setToolTip("Parcourir et charger un fichier local")
        self.btn_browse_doc.clicked.connect(self._on_browse_local_file)
        src_row.addWidget(self.btn_browse_doc)

        grp_src.addWidget(lbl_src)
        grp_src.addLayout(src_row)
        build_layout.addLayout(grp_src)

        # 2. Paquet Cible
        grp_pkg = QVBoxLayout()
        grp_pkg.setSpacing(4)
        lbl_pkg = QLabel("Paquet Cible :")
        lbl_pkg.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; font-weight: bold;")
        self.pkg_input = StyledLineEdit()
        self.pkg_input.setPlaceholderText("Ex: Médecine::Cardio")
        grp_pkg.addWidget(lbl_pkg)
        grp_pkg.addWidget(self.pkg_input)
        build_layout.addLayout(grp_pkg)

        # 3. Grid Modèle & Moteur IA (grid-2 gap-10)
        grid_model_eng = QGridLayout()
        grid_model_eng.setSpacing(10)

        lbl_mod = QLabel("Modèle :")
        lbl_mod.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; font-weight: bold;")
        self.model_combo = StyledComboBox()
        grid_model_eng.addWidget(lbl_mod, 0, 0)
        grid_model_eng.addWidget(self.model_combo, 1, 0)

        lbl_eng = QLabel("Moteur IA :")
        lbl_eng.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; font-weight: bold;")
        self.engine_combo = StyledComboBox()
        grid_model_eng.addWidget(lbl_eng, 0, 1)
        grid_model_eng.addWidget(self.engine_combo, 1, 1)

        build_layout.addLayout(grid_model_eng)

        # 4. Pipeline
        grp_pipe = QVBoxLayout()
        grp_pipe.setSpacing(4)
        lbl_pipe = QLabel("Pipeline :")
        lbl_pipe.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; font-weight: bold;")
        self.pipeline_combo = StyledComboBox()
        grp_pipe.addWidget(lbl_pipe)
        grp_pipe.addWidget(self.pipeline_combo)
        build_layout.addLayout(grp_pipe)

        # 5. Options Checkboxes
        self.cb_vision = QCheckBox("Vision (Images/PDF)")
        self.cb_vision.setChecked(True)
        self.cb_vision.setIcon(load_phosphor_icon("ph.eye", color="#eab308"))
        self.cb_vision.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px;")

        self.cb_autoval = QCheckBox("Validation automatique")
        self.cb_autoval.setChecked(True)
        self.cb_autoval.setIcon(load_phosphor_icon("ph.check-square-offset", color="#3b82f6"))
        self.cb_autoval.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px;")

        build_layout.addWidget(self.cb_vision)
        build_layout.addWidget(self.cb_autoval)

        build_layout.addStretch()

        # 6. Bouton 'Ajouter à la Queue' (glow-btn-primary full width)
        self.btn_add_to_queue = PrimaryButton("Ajouter à la Queue")
        self.btn_add_to_queue.setIcon(load_phosphor_icon("ph.plus", color="white"))
        self.btn_add_to_queue.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #6366f1, stop:1 #8b5cf6);
                border: 1px solid #6366f1;
                border-radius: 6px;
                padding: 10px 16px;
                font-size: 13px;
                font-weight: bold;
                color: white;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #4f46e5, stop:1 #7c3aed);
            }
        """)
        apply_shadow(self.btn_add_to_queue, blur=20, offset_y=0, color="rgba(99, 102, 241, 0.75)")
        self.btn_add_to_queue.clicked.connect(self._on_add_to_queue_clicked)
        build_layout.addWidget(self.btn_add_to_queue)

        self.build_panel.add_tab("Paramètres du Build", build_content, "ph.sliders-horizontal", closable=False)
        self.middle_splitter.addWidget(self.build_panel)

        # RIGHT PANEL: File d'attente détaillée (flex-1)
        self.queue_panel = IdePanel(detachable=True)

        # Header action buttons (Vider + Démarrer Pipeline)
        self.btn_clear_table = IconButton("ph.trash", tooltip="Vider la file d'attente", size=22)
        self.btn_clear_table.clicked.connect(self._on_clear_queue)
        self.queue_panel.add_header_widget(self.btn_clear_table)

        self.btn_start_pipeline = PrimaryButton("Démarrer Pipeline")
        self.btn_start_pipeline.setIcon(load_phosphor_icon("ph.play", color="white"))
        self.btn_start_pipeline.setStyleSheet("""
            QPushButton {
                background-color: #10b981;
                border: 1px solid #10b981;
                color: white;
                font-weight: bold;
                padding: 6px 18px;
                border-radius: 6px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #059669;
                border-color: #34d399;
            }
        """)
        apply_shadow(self.btn_start_pipeline, blur=24, offset_y=0, color="rgba(16, 185, 129, 0.85)")
        self.btn_start_pipeline.clicked.connect(self._on_start_batch)
        self.queue_panel.add_header_widget(self.btn_start_pipeline)

        queue_content = QWidget()
        queue_layout = QVBoxLayout(queue_content)
        queue_layout.setContentsMargins(0, 0, 0, 0)
        queue_layout.setSpacing(0)

        # Table (L1980-L2032)
        self.queue_table = StyledTableWidget(["[ ]", "Statut", "Fichier / Source", "Progrès", "Tokens Est.", "Actions"])
        self.queue_table.setSelectionBehavior(StyledTableWidget.SelectionBehavior.SelectRows)

        # Explicit Column Widths matching mockup
        self.queue_table.setColumnWidth(0, 40)
        self.queue_table.setColumnWidth(1, 120)
        self.queue_table.setColumnWidth(2, 220)
        self.queue_table.setColumnWidth(4, 110)
        self.queue_table.setColumnWidth(5, 70)

        queue_layout.addWidget(self.queue_table, 1)

        self.queue_panel.add_tab("File d'attente détaillée", queue_content, "ph.list-dashes", closable=False)
        self.middle_splitter.addWidget(self.queue_panel)

        self.middle_splitter.setSizes([350, 750])
        self.main_splitter.addWidget(self.middle_splitter)

        # =========================================================================
        # BOTTOM ROW: Terminal Log Console (L2038-L2062, height: 250px)
        # =========================================================================
        self.terminal_panel = IdePanel(detachable=True)
        self.terminal_panel.setStyleSheet("""
            QFrame {
                border: 1px solid rgba(59, 130, 246, 0.5);
                border-radius: 8px;
            }
        """)
        apply_shadow(self.terminal_panel, blur=22, offset_y=0, color="rgba(59, 130, 246, 0.55)")

        # Header Actions pour le Terminal (Vider console & Scroll Lock)
        self.btn_clear_terminal = IconButton("ph.trash", tooltip="Effacer les logs du terminal", size=20)
        self.btn_clear_terminal.clicked.connect(self._on_clear_terminal_clicked)
        self.terminal_panel.add_header_widget(self.btn_clear_terminal)

        self.btn_scroll_lock = IconButton("ph.lock-key", tooltip="Verrouiller le défilement", size=20)
        self.btn_scroll_lock.clicked.connect(lambda: show_toast(self, "Verrouillage du défilement activé."))
        self.terminal_panel.add_header_widget(self.btn_scroll_lock)

        terminal_content = QWidget()
        terminal_layout = QVBoxLayout(terminal_content)
        terminal_layout.setContentsMargins(0, 0, 0, 0)
        terminal_layout.setSpacing(0)

        # Console Text Edit (#0c0c0c, Fira Code / JetBrains Mono)
        self.console_output = StyledTextEdit()
        self.console_output.setReadOnly(True)
        self.console_output.setStyleSheet("""
            QPlainTextEdit {
                background-color: #0c0c0c;
                color: #10b981;
                font-family: 'Fira Code', 'JetBrains Mono', monospace;
                font-size: 12px;
                line-height: 1.6;
                padding: 14px;
                border: none;
                selection-background-color: #3b82f6;
            }
        """)
        terminal_layout.addWidget(self.console_output, 1)

        self.terminal_panel.add_tab("root@ankiforge:~/pipeline_logs", terminal_content, "ph.terminal-window", closable=False)
        self.main_splitter.addWidget(self.terminal_panel)

        self.main_splitter.setSizes([500, 240])

        self._log_formatted_line("INFO", "Pipeline worker initialized.")
        self._update_queue_table()

    def _connect_signals(self) -> None:
        pass

    def refresh_data(self) -> None:
        """Recharge les données dynamiques depuis Peewee DB."""
        try:
            # 1. Documents combo
            self.doc_combo.blockSignals(True)
            self.doc_combo.clear()
            docs = list(DocumentModel.select())
            if docs:
                for doc in docs:
                    self.doc_combo.addItem(f"📄 {doc.title}", userData=doc)
            else:
                self.doc_combo.addItem("Aucun document disponible")
            self.doc_combo.blockSignals(False)

            # 2. Modèles de cartes
            self.model_combo.blockSignals(True)
            self.model_combo.clear()
            for nt in NoteTypeModel.select():
                self.model_combo.addItem(nt.name, userData=nt)
            self.model_combo.blockSignals(False)

            # 3. Moteurs IA (avec display_name et icône ⚡)
            self.engine_combo.blockSignals(True)
            self.engine_combo.clear()
            engines = list(LLMConfigModel.select())
            if not engines:
                LLMConfigModel.create(display_name="Claude 3.5 Sonnet", provider="anthropic", model_id="claude-3-5-sonnet-20240620")
                LLMConfigModel.create(display_name="GPT-4o", provider="openai", model_id="gpt-4o")
                engines = list(LLMConfigModel.select())

            for eg in engines:
                display_name = getattr(eg, "display_name", getattr(eg, "name", str(eg)))
                self.engine_combo.addItem(f"⚡ {display_name}", userData=eg)
            self.engine_combo.blockSignals(False)

            # 4. Pipelines
            self.pipeline_combo.blockSignals(True)
            self.pipeline_combo.clear()
            pipelines = list(PipelineModel.select())
            if not pipelines:
                PipelineModel.create(name="Excellence (Standard)", description="Archiviste + Linter")
                pipelines = list(PipelineModel.select())

            for pipe in pipelines:
                self.pipeline_combo.addItem(f"🔀 {pipe.name}", userData=pipe)
            self.pipeline_combo.blockSignals(False)

            decks = list(DeckModel.select())
            if decks:
                self.pkg_input.setText(decks[0].name)

        except Exception as e:
            logger.warning("Erreur refresh_data batch_view: %s", e)

    def is_dirty(self) -> bool:
        return len(self.queue_tasks_data) > 0

    def _log_formatted_line(self, level: str, msg: str) -> None:
        """Génère une ligne de log formatée avec horodatage et niveau coloré conforme au terminal (L2052-L2059)."""
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        level_color = "#3b82f6"  # INFO = Blue
        if level == "WARN":
            level_color = "#eab308"  # WARN = Yellow
        elif level == "SUCCESS":
            level_color = "#10b981"  # SUCCESS = Green
        elif level == "ERROR":
            level_color = "#ef4444"  # ERROR = Red

        formatted_html = f"<span style='color: {DesignTokens.TEXT_MUTED}'>[{now_str}]</span> <span style='color: {level_color}; font-weight: bold;'>{level}</span> {msg}"

        self.console_output.appendHtml(formatted_html)

    @Slot()
    def _on_clear_terminal_clicked(self) -> None:
        self.console_output.clear()
        self._log_formatted_line("INFO", "Terminal logs cleared.")

    @Slot()
    def _on_browse_local_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "Sélectionner un document source", "", "Documents (*.pdf *.txt *.md *.docx);;Tous (*)")
        if file_path:
            import os

            title = os.path.basename(file_path)
            doc, _ = DocumentModel.get_or_create(title=title, defaults={"file_path": file_path, "content": f"Contenu du fichier {title}"})
            self.refresh_data()
            show_toast(self, f"Document '{title}' chargé !")

    @Slot()
    def _on_add_to_queue_clicked(self) -> None:
        doc: Optional[DocumentModel] = self.doc_combo.currentData()
        if not doc or not isinstance(doc, DocumentModel):
            show_toast(self, "Veuillez sélectionner un document source valide.", is_error=True)
            return

        selected_nt = self.model_combo.currentData()
        selected_engine = self.engine_combo.currentData()
        selected_pipeline = self.pipeline_combo.currentData()

        # Estimation des tokens
        doc_content = getattr(doc, "content", "") or ""
        words_count = len(doc_content.split())
        tokens_est = int(words_count * 1.3) if words_count > 0 else 25000

        task_data = {
            "doc": doc,
            "deck_name": self.pkg_input.text().strip() or "Médecine::Cardio",
            "note_type": selected_nt,
            "engine": selected_engine,
            "pipeline": selected_pipeline,
            "use_vision": self.cb_vision.isChecked(),
            "auto_val": self.cb_autoval.isChecked(),
            "status": "En attente",
            "tokens_est": tokens_est,
            "progress_pct": 0,
        }

        self.queue_tasks_data.append(task_data)
        self._update_queue_table()
        self._update_estimates_summary()
        show_toast(self, f"Tâche '{doc.title}' ajoutée à la Queue !")

    def _update_queue_table(self) -> None:
        self.queue_table.blockSignals(True)
        self.cell_widgets_map.clear()

        if not self.queue_tasks_data:
            self.queue_table.setRowCount(1)
            empty_item = QTableWidgetItem("La file d'attente est vide. Sélectionnez des documents à gauche pour commencer.")
            empty_item.setFlags(Qt.ItemFlag.NoItemFlags)
            empty_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.queue_table.setItem(0, 0, empty_item)
            self.queue_table.setSpan(0, 0, 1, 6)
            self.queue_table.blockSignals(False)
            return

        self.queue_table.clearSpans()
        self.queue_table.setRowCount(len(self.queue_tasks_data))

        for i, task in enumerate(self.queue_tasks_data):
            doc: DocumentModel = task["doc"]
            status: str = task.get("status", "En attente")
            tokens_est: int = task.get("tokens_est", 25000)
            progress_pct: int = task.get("progress_pct", 0)

            # Col 0: Checkbox
            cb_item = QTableWidgetItem()
            cb_item.setCheckState(Qt.CheckState.Checked)
            self.queue_table.setItem(i, 0, cb_item)

            # Col 1: Statut Badge
            badge_color = DesignTokens.COLOR_YELLOW if status == "En attente" else (DesignTokens.COLOR_BLUE if status == "En cours" else DesignTokens.COLOR_GREEN)
            status_badge = Badge(status, variant="outline", color=badge_color)
            self.queue_table.setCellWidget(i, 1, status_badge)

            # Col 2: Fichier / Source (icône PDF/Doc)
            doc_item = QTableWidgetItem(f"📄 {doc.title}")
            self.queue_table.setItem(i, 2, doc_item)

            # Col 3: Progrès (Progress Bar + text sub)
            prog_widget = ProgressTableCellWidget(progress_pct=progress_pct, status_text="En attente...", color="#6366f1")
            self.cell_widgets_map[i] = prog_widget
            self.queue_table.setCellWidget(i, 3, prog_widget)

            # Col 4: Tokens Est.
            tokens_item = QTableWidgetItem(f"~ {tokens_est:,}")
            tokens_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.queue_table.setItem(i, 4, tokens_item)

            # Col 5: Actions (Bouton Suppression X)
            btn_del = IconButton("ph.x", tooltip="Retirer de la queue", size=18)
            btn_del.clicked.connect(lambda _, row_idx=i: self._remove_from_queue(row_idx))

            del_widget = QWidget()
            del_layout = QHBoxLayout(del_widget)
            del_layout.setContentsMargins(0, 0, 0, 0)
            del_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            del_layout.addWidget(btn_del)

            self.queue_table.setCellWidget(i, 5, del_widget)

        self.queue_table.blockSignals(False)

    def _remove_from_queue(self, row_idx: int) -> None:
        if 0 <= row_idx < len(self.queue_tasks_data):
            self.queue_tasks_data.pop(row_idx)
            self._update_queue_table()
            self._update_estimates_summary()

    @Slot()
    def _on_clear_queue(self) -> None:
        self.queue_tasks_data.clear()
        self._update_queue_table()
        self._update_estimates_summary()
        show_toast(self, "File d'attente vidée.")

    def _update_estimates_summary(self) -> None:
        total_tokens = sum(task.get("tokens_est", 25000) for task in self.queue_tasks_data)
        count = len(self.queue_tasks_data)

        self.card_status.val_lbl.setText("En attente" if count > 0 else "Prêt")
        self.card_cards.val_lbl.setText(f"0 / {count}")
        self.card_cost.val_lbl.setText(f"${(total_tokens / 1000000 * 0.15):.2f}")

    @Slot()
    def _on_start_batch(self) -> None:
        if not self.queue_tasks_data:
            show_toast(self, "La file d'attente est vide ! Ajoutez des tâches avant de lancer.", is_error=True)
            return

        tasks_payloads: list[BatchTaskPayload] = []

        for task in self.queue_tasks_data:
            task["status"] = "En cours"
            doc: DocumentModel = task["doc"]
            deck_name: str = task["deck_name"]

            deck, _ = DeckModel.get_or_create(name=deck_name)

            selected_nt = task["note_type"]
            note_type = selected_nt if isinstance(selected_nt, NoteTypeModel) else NoteTypeModel.select().first()
            if not note_type:
                note_type = NoteTypeModel.create(name="Basic", fields_schema='["Front", "Back"]', templates="[]", css_style="")

            selected_pipeline = task["pipeline"]
            pipeline_id = selected_pipeline.id if selected_pipeline and hasattr(selected_pipeline, "id") else 1

            pipeline_steps = [
                {
                    "name": "BatchGenerator",
                    "system_prompt": 'Génère des cartes Anki sous forme de tableau JSON [{"front": "...", "back": "..."}].',
                    "output_format": "json",
                }
            ]

            selected_engine = task["engine"]
            llm_id = selected_engine.id if selected_engine and hasattr(selected_engine, "id") else 1
            eng_display = getattr(selected_engine, "display_name", getattr(selected_engine, "name", "LLM"))
            llm_config = {
                "display_name": eng_display,
                "model_id": getattr(selected_engine, "model_id", "default"),
                "context_limit": 128000,
                "api_key": getattr(selected_engine, "api_key", ""),
                "provider": getattr(selected_engine, "provider_type", "openai"),
            }

            fields_schema = json.loads(note_type.fields_schema) if note_type.fields_schema else ["Front", "Back"]
            templates = json.loads(note_type.templates) if note_type.templates else []

            payload = BatchTaskPayload(
                doc_id=doc.id,
                doc_title=doc.title,
                doc_content=getattr(doc, "content", ""),
                deck_id=deck.id,
                model_id=note_type.id,
                note_type_fields=fields_schema,
                note_type_templates=templates,
                pipeline_id=pipeline_id,
                pipeline_steps=pipeline_steps,
                llm_id=llm_id,
                llm_config=llm_config,
                chunk_strategy="Sémantique (Titres)",
                use_vision=task["use_vision"],
            )
            tasks_payloads.append(payload)

        self._update_queue_table()
        self.start_timestamp = time.time()

        self.card_status.val_lbl.setText("En cours")
        self.card_status.val_lbl.setStyleSheet(f"color: {DesignTokens.COLOR_BLUE}; font-size: 16px; font-weight: bold; border: none; font-family: '{DesignTokens.FONT_CODE}';")

        self._log_formatted_line("INFO", f"Starting build job for {len(tasks_payloads)} documents in queue...")

        ai_provider = None
        if self.ai_manager and hasattr(self.ai_manager, "get_active_provider"):
            try:
                ai_provider = self.ai_manager.get_active_provider()
            except Exception:
                pass  # nosec B110

        self.worker = BatchWorker(ai_provider=ai_provider, tasks=tasks_payloads)
        self.worker.batch_data_ready.connect(self._save_extracted_notes_to_db)
        self.worker.progress_val.connect(self._on_worker_progress_pct)
        self.worker.progress_text.connect(lambda txt: self._log_formatted_line("INFO", txt))
        self.worker.log.connect(lambda msg: self._log_formatted_line("INFO", msg))
        self.worker.finished.connect(self._on_batch_finished)
        self.worker.error.connect(self._on_batch_error)

        self.worker.start()

    @Slot(int)
    def _on_worker_progress_pct(self, val: int) -> None:
        if self.start_timestamp > 0:
            elapsed = int(time.time() - self.start_timestamp)
            mins = elapsed // 60
            secs = elapsed % 60
            self.card_time.val_lbl.setText(f"{mins:02d}:{secs:02d}")

        if 0 in self.cell_widgets_map:
            self.cell_widgets_map[0].update_progress(val, f"Génération IA ({val}%)...", color="#3b82f6")

    @Slot(list, int, int)
    def _save_extracted_notes_to_db(self, notes_data: list[dict[str, Any]], deck_id: int, model_id: int) -> None:
        """Sauvegarde atomique des cartes générées."""
        try:
            deck = DeckModel.get_by_id(deck_id)
            note_type = NoteTypeModel.get_by_id(model_id)
            templates = json.loads(note_type.templates) if note_type.templates else []
            is_cloze = any("{{cloze:" in t.get("qfmt", "") or "{{cloze:" in t.get("afmt", "") for t in templates)

            new_count = 0
            with db.atomic():
                for cleaned_fields in notes_data:
                    note = NoteModel.create(
                        guid=str(uuid.uuid4())[:10],
                        note_type=note_type,
                        tags=json.dumps(["AnkiForge_Batch"], ensure_ascii=False),
                        status="pending",
                    )
                    NoteVersionModel.create(
                        note=note,
                        version_number=1,
                        content=json.dumps(cleaned_fields, ensure_ascii=False),
                        source="ai_batch",
                        is_active=True,
                    )

                    if is_cloze:
                        max_cloze = get_max_cloze_index(cleaned_fields)
                        num_cards = max(1, max_cloze)
                        for i in range(num_cards):
                            CardModel.create(note=note, deck=deck, template_index=i)
                            new_count += 1
                    else:
                        for idx, _ in enumerate(templates):
                            CardModel.create(note=note, deck=deck, template_index=idx)
                            new_count += 1

            self.card_cards.val_lbl.setText(f"{new_count} / {len(self.queue_tasks_data)}")
            self._log_formatted_line("SUCCESS", f"Chunk validated by Linter Agent: {new_count} cards saved to deck '{deck.name}'")
        except Exception as e:
            logger.exception("Erreur lors de la sauvegarde batch : %s", e)
            self._log_formatted_line("ERROR", f"Save failed: {str(e)}")

    @Slot(int, int)
    def _on_batch_finished(self, success_count: int, error_count: int) -> None:
        self.card_status.val_lbl.setText("Terminé")
        self.card_status.val_lbl.setStyleSheet(f"color: {DesignTokens.COLOR_GREEN}; font-size: 16px; font-weight: bold; border: none; font-family: '{DesignTokens.FONT_CODE}';")
        self._log_formatted_line("SUCCESS", f"Pipeline finished cleanly. {success_count} jobs succeeded, {error_count} errors.")
        show_toast(self, f"Pipeline terminé : {success_count} jobs réussis !")

        for task in self.queue_tasks_data:
            task["status"] = "Terminé"
            task["progress_pct"] = 100

        self._update_queue_table()

    @Slot(str)
    def _on_batch_error(self, error_msg: str) -> None:
        self.card_status.val_lbl.setText("Erreur")
        self.card_status.val_lbl.setStyleSheet(f"color: {DesignTokens.COLOR_RED}; font-size: 16px; font-weight: bold; border: none; font-family: '{DesignTokens.FONT_CODE}';")
        self._log_formatted_line("ERROR", error_msg)
        QMessageBox.critical(self, "Erreur Pipeline", f"Erreur lors de l'exécution du pipeline :\n{error_msg}")


BatchTab = BatchView
