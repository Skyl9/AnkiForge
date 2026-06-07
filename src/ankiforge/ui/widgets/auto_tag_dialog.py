import json
import logging
from typing import Any

import qtawesome as qta
from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QTextEdit, QProgressBar

from ankiforge.database.models import NoteModel, LLMConfigModel, NoteVersionModel, db
from ankiforge.services.ai.base import LLMProvider
from ankiforge.services.ai.flexible_service import AIManager
from ankiforge.services.ai.utils import AIReponseParser
from ankiforge.ui.components.components import PrimaryButton

logger = logging.getLogger(__name__)


class AutoTaggingThread(QThread):
    """Analyse les cartes en lots et génère des tags pertinents."""

    progress = Signal(int, str)
    finished_signal = Signal(int)  # Nombre de cartes taguées
    error_signal = Signal(str)

    def __init__(self, ai_provider: LLMProvider, note_ids: list[int], instruction: str):
        super().__init__()
        self.ai_provider = ai_provider
        self.note_ids = note_ids
        self.instruction = instruction
        self.chunk_size = 15  # On traite par lots de 15 pour ne pas saturer la sortie JSON de l'IA

    def run(self):
        try:
            total_tagged = 0
            total_notes = len(self.note_ids)

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
                print(raw_response)
                # Extraction et Sauvegarde
                try:
                    tagged_results = AIReponseParser.parse(raw_response)
                    if not isinstance(tagged_results, list):
                        raise ValueError("L'IA n'a pas renvoyé une liste JSON.")

                    with db.atomic():
                        for result in tagged_results:
                            nid = result.get("note_id")
                            new_tags = result.get("nouveaux_tags", [])

                            if nid and new_tags:
                                note = NoteModel.get_by_id(nid)
                                # On fusionne les anciens tags avec les nouveaux sans faire de doublons
                                existing_tags = json.loads(note.tags) if note.tags else []
                                merged_tags = list(set(existing_tags + new_tags))

                                note.tags = json.dumps(merged_tags, ensure_ascii=False)
                                note.save()
                                total_tagged += 1

                except Exception as e:
                    logger.warning(f"Échec du parsing IA sur le lot {i}: {e}")
                    continue  # On continue même si un lot échoue

            self.progress.emit(100, "Terminé !")
            self.finished_signal.emit(total_tagged)

        except Exception as e:
            logger.exception("Erreur fatale lors de l'auto-tagging :")
            self.error_signal.emit(str(e))


class AutoTagDialog(QDialog):
    """Fenêtre de configuration pour lancer l'Archiviste IA."""

    def __init__(self, parent: Any, note_ids: list[int]):
        super().__init__(parent)
        self.note_ids = note_ids
        self.worker: AutoTaggingThread | None = None

        self.setWindowTitle("🏷️ L'Archiviste IA (Auto-Tagging)")
        self.resize(450, 350)
        self.setModal(True)

        layout = QVBoxLayout(self)
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

    def _populate_llms(self):
        for llm in LLMConfigModel.select().order_by(LLMConfigModel.display_name):
            self.llm_selector.addItem(llm.display_name, userData=llm.id)

    @Slot()
    def start_tagging(self):
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
        self.worker.finished_signal.connect(self.on_success)
        self.worker.error_signal.connect(self.on_error)
        self.worker.start()

    @Slot(int, str)
    def update_progress(self, val: int, text: str):
        self.progress_bar.setValue(val)
        self.lbl_status.setText(text)

    @Slot(int)
    def on_success(self, count: int):
        self.accept()  # Ferme la boîte de dialogue avec un code de succès

    @Slot(str)
    def on_error(self, err: str):
        self.lbl_status.setText(f"<span style='color:red;'>Erreur : {err}</span>")
        self.btn_start.setEnabled(True)
