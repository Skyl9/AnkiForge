import json
import logging
from typing import Any

import qtawesome as qta
from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtWidgets import QComboBox, QDialog, QHBoxLayout, QHeaderView, QLabel, QProgressBar, QPushButton, QStackedWidget, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget

from ankiforge.database.models import LLMConfigModel, NoteModel, NoteVersionModel, db
from ankiforge.services.ai.base import LLMProvider
from ankiforge.services.ai.flexible_service import AIManager
from ankiforge.services.ai.utils import AIReponseParser
from ankiforge.ui.components.components import PrimaryButton

logger = logging.getLogger(__name__)


class AutoTaggingThread(QThread):
    """Analyse les cartes en lots et génère des tags pertinents."""

    progress = Signal(int, str)
    finished_signal = Signal(list)  # Liste des propositions de tags
    error_signal = Signal(str)
    log_signal = Signal(str)

    def __init__(self, ai_provider: LLMProvider, note_ids: list[int], instruction: str) -> None:
        super().__init__()
        self.ai_provider = ai_provider
        self.note_ids = note_ids
        self.instruction = instruction
        self.chunk_size = 15  # On traite par lots de 15 pour ne pas saturer la sortie JSON de l'IA

    def run(self) -> None:
        try:
            total_notes = len(self.note_ids)
            all_proposals: list[dict[str, Any]] = []

            system_prompt = (
                "Tu es un documentaliste expert chargé de classer des flashcards Anki.\n"
                "Ta mission est d'analyser le contenu de chaque carte et de lui attribuer 1 à 3 tags pertinents (catégorie, matière, concept clé).\n"
                "RÈGLES ABSOLUES :\n"
                "1. Réponds UNIQUEMENT au format JSON strict.\n"
                "2. Le JSON doit être un tableau d'objets avec cette structure exacte :\n"
                '   [{"note_id": 123, "nouveaux_tags": ["Tag1", "Tag2"]}]\n'
                "3. Les tags doivent être courts, sans espaces (utilise des tirets si besoin) et en PascalCase (ex: PathologieCardiaque)."
            )

            for i in range(0, total_notes, self.chunk_size):
                chunk_ids = self.note_ids[i : i + self.chunk_size]
                self.progress.emit(int((i / total_notes) * 100), f"Analyse des cartes {i + 1} à {min(i + self.chunk_size, total_notes)}...")

                # Préparation du payload
                payload = []
                for nid in chunk_ids:
                    note = NoteModel.get_by_id(nid)
                    active_version = NoteVersionModel.get_or_none(note=note, is_active=True)
                    if active_version:
                        payload.append({"note_id": note.id, "contenu": json.loads(active_version.content)})

                if not payload:
                    continue

                user_prompt = f"INSTRUCTION SUPPLÉMENTAIRE :\n{self.instruction}\n\nCARTES À TAGUER :\n{json.dumps(payload, ensure_ascii=False)}"

                # Appel API (On force le format JSON)
                raw_response = self.ai_provider.generate(system_prompt=system_prompt, user_prompt=user_prompt, response_format="json")
                self.log_signal.emit(str(raw_response))

                # Extraction
                try:
                    tagged_results = AIReponseParser.parse(raw_response)
                    if not isinstance(tagged_results, list):
                        raise ValueError("L'IA n'a pas renvoyé une liste JSON.")

                    all_proposals.extend(tagged_results)

                except json.JSONDecodeError as e:
                    logger.warning(f"Erreur de décodage JSON sur le lot {i}: {e}")
                    self.log_signal.emit(f"Erreur JSON : {e}")
                    continue
                except Exception as e:
                    logger.warning(f"Échec du parsing IA sur le lot {i}: {e}")
                    continue  # On continue même si un lot échoue

            self.progress.emit(100, "Terminé !")
            self.finished_signal.emit(all_proposals)

        except Exception as e:
            logger.exception("Erreur fatale lors de l'auto-tagging :")
            self.error_signal.emit(str(e))


class AutoTagDialog(QDialog):
    """Fenêtre de configuration pour lancer l'Archiviste IA."""

    def __init__(self, parent: Any, note_ids: list[int]) -> None:
        super().__init__(parent)
        self.note_ids = note_ids
        self.worker: AutoTaggingThread | None = None

        self.setWindowTitle("🏷️ L'Archiviste IA (Auto-Tagging)")
        self.resize(600, 500)
        self.setModal(True)

        self.main_layout = QVBoxLayout(self)
        self.stacked_widget = QStackedWidget()
        self.main_layout.addWidget(self.stacked_widget)

        self._setup_page_1()
        self._setup_page_2()

        self.stacked_widget.setCurrentIndex(0)

    def _setup_page_1(self) -> None:
        self.page1 = QWidget()
        layout = QVBoxLayout(self.page1)
        layout.setSpacing(15)

        # Info
        lbl_info = QLabel(f"Vous vous apprêtez à catégoriser automatiquement <b>{len(self.note_ids)} carte(s)</b>.")
        layout.addWidget(lbl_info)

        # Moteur IA
        layout.addWidget(QLabel("Moteur IA à utiliser :"))
        self.llm_selector = QComboBox()
        self._populate_llms()
        layout.addWidget(self.llm_selector)

        # Directives
        layout.addWidget(QLabel("Directives spécifiques (Optionnel) :"))
        self.instruction_input = QTextEdit()
        self.instruction_input.setPlaceholderText("Ex: Utilise uniquement des tags liés au droit civil. Ignore les dates.")
        self.instruction_input.setMaximumHeight(80)
        layout.addWidget(self.instruction_input)

        # Progression
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        self.lbl_status = QLabel("")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_status)

        # Boutons
        btn_layout = QHBoxLayout()
        self.btn_start = PrimaryButton(qta.icon("fa5s.tags", color="white"), " Démarrer le Tagging")
        self.btn_start.clicked.connect(self.start_tagging)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_start)

        layout.addLayout(btn_layout)
        self.stacked_widget.addWidget(self.page1)

    def _setup_page_2(self) -> None:
        self.page2 = QWidget()
        layout = QVBoxLayout(self.page2)

        layout.addWidget(QLabel("Validation des tags proposés :"))

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["ID Note", "Tags Proposés", "Valider"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

        layout.addWidget(self.table)

        # Boutons de sélection
        sel_layout = QHBoxLayout()
        btn_check_all = QPushButton("Tout cocher")
        btn_uncheck_all = QPushButton("Tout décocher")
        btn_check_all.clicked.connect(self._check_all)
        btn_uncheck_all.clicked.connect(self._uncheck_all)
        sel_layout.addWidget(btn_check_all)
        sel_layout.addWidget(btn_uncheck_all)
        sel_layout.addStretch()
        layout.addLayout(sel_layout)

        # Action finale
        btn_layout = QHBoxLayout()
        btn_apply = PrimaryButton(qta.icon("fa5s.check", color="white"), " Appliquer la sélection")
        btn_apply.clicked.connect(self.apply_tags)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_apply)

        layout.addLayout(btn_layout)
        self.stacked_widget.addWidget(self.page2)

    def _populate_llms(self) -> None:
        for llm in LLMConfigModel.select().order_by(LLMConfigModel.display_name):
            self.llm_selector.addItem(llm.display_name, userData=llm.id)

    @Slot()
    def start_tagging(self) -> None:
        llm_id = self.llm_selector.currentData()
        llm_config = LLMConfigModel.get_or_none(LLMConfigModel.id == llm_id)
        if not llm_config:
            return

        active_provider = AIManager.create_provider_from_config(llm_config)

        instruction = self.instruction_input.toPlainText().strip()

        # UI Update
        self.btn_start.setEnabled(False)
        self.instruction_input.setEnabled(False)
        self.llm_selector.setEnabled(False)
        self.progress_bar.show()

        # Lancement
        self.worker = AutoTaggingThread(active_provider, self.note_ids, instruction)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished_signal.connect(self.on_generation_finished)
        self.worker.error_signal.connect(self.on_error)
        self.worker.start()

    @Slot(int, str)
    def update_progress(self, val: int, text: str) -> None:
        self.progress_bar.setValue(val)
        self.lbl_status.setText(text)

    @Slot(list)
    def on_generation_finished(self, proposals: list[dict[str, Any]]) -> None:
        self.table.setRowCount(0)
        for row_idx, prop in enumerate(proposals):
            note_id = prop.get("note_id")
            tags = prop.get("nouveaux_tags", [])
            if not note_id or not tags:
                continue

            self.table.insertRow(row_idx)

            id_item = QTableWidgetItem(str(note_id))
            id_item.setFlags(id_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row_idx, 0, id_item)

            tags_str = ", ".join(tags)
            tags_item = QTableWidgetItem(tags_str)
            tags_item.setFlags(tags_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            tags_item.setData(Qt.ItemDataRole.UserRole, tags)
            self.table.setItem(row_idx, 1, tags_item)

            check_item = QTableWidgetItem("")
            check_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            check_item.setCheckState(Qt.CheckState.Checked)
            self.table.setItem(row_idx, 2, check_item)

        self.stacked_widget.setCurrentIndex(1)

    @Slot(str)
    def on_error(self, err: str) -> None:
        self.lbl_status.setText(f"<span style='color:red;'>Erreur : {err}</span>")
        self.btn_start.setEnabled(True)

    def _check_all(self) -> None:
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 2)
            if item:
                item.setCheckState(Qt.CheckState.Checked)

    def _uncheck_all(self) -> None:
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 2)
            if item:
                item.setCheckState(Qt.CheckState.Unchecked)

    @Slot()
    def apply_tags(self) -> None:
        with db.atomic():
            for row in range(self.table.rowCount()):
                check_item = self.table.item(row, 2)
                if check_item and check_item.checkState() == Qt.CheckState.Checked:
                    id_item = self.table.item(row, 0)
                    tags_item = self.table.item(row, 1)
                    if not id_item or not tags_item:
                        continue

                    try:
                        note_id = int(id_item.text())
                        new_tags: list[str] = tags_item.data(Qt.ItemDataRole.UserRole)

                        note = NoteModel.get_by_id(note_id)
                        existing_tags = json.loads(note.tags) if note.tags else []
                        merged_tags = list(set(existing_tags + new_tags))

                        note.tags = json.dumps(merged_tags, ensure_ascii=False)
                        note.save()
                    except Exception as e:
                        logger.error(f"Erreur lors de la sauvegarde de la note {id_item.text()}: {e}")

        self.accept()
