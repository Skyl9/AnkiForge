import json
import logging
import time
from typing import Any

from PySide6.QtCore import QThread, Signal

from ankiforge.database.models import NoteModel, NoteVersionModel, db
from ankiforge.services.ai.utils import AIReponseParser

logger = logging.getLogger(__name__)


class BatchEditWorker(QThread):
    """
    Exécute des requêtes de modification IA par lots sur des notes existantes.

    Récupère le contenu actuel des notes et demande à l'IA d'appliquer une transformation
    (ex: simplifier, traduire, formater) sur chaque lot (chunk) de cartes.
    """

    progress = Signal(str)
    finished_signal = Signal(int)
    error_signal = Signal(str)
    cancelled = Signal()

    def __init__(self, ai_provider: Any, note_ids: list[int], user_prompt: str, chunk_size: int):
        """
        Initialise le worker de modification par lots.

        Args:
            ai_provider (Any): Le moteur IA à solliciter.
            note_ids (list[int]): IDs des notes à modifier.
            user_prompt (str): Instructions de modification (ex: 'Traduis en anglais').
            chunk_size (int): Nombre de notes envoyées simultanément à l'IA.
        """
        super().__init__()
        self.ai_provider = ai_provider
        self.note_ids = note_ids
        self.user_prompt = user_prompt
        self.chunk_size = chunk_size
        self._is_cancelled = False

    def cancel(self) -> None:
        """Demande l'arrêt du processus de modification."""
        logger.info("Demande d'annulation reçue pour BatchEditWorker.")
        self._is_cancelled = True

    def run(self) -> None:
        """Parcourt les notes par lots et enregistre les versions modifiées."""
        logger.info("Démarrage du BatchEditWorker (%d notes, taille de lot=%d)", len(self.note_ids), self.chunk_size)
        t0 = time.perf_counter()
        try:
            total_processed = 0

            system_contract = (
                "Tu es un assistant de traitement de base de données.\n"
                "Voici ton instruction principale :\n"
                f"--- {self.user_prompt} ---\n\n"
                "RÈGLE ABSOLUE : Tu vas recevoir un tableau JSON d'objets.\n"
                "Tu dois renvoyer EXACTEMENT la même structure (un tableau JSON).\n"
                "Chaque objet possède une clé 'note_id' que tu DOIS impérativement conserver intacte.\n"
                "Ne rajoute AUCUN texte autour de ta réponse, uniquement du JSON valide."
            )

            total_chunks = (len(self.note_ids) + self.chunk_size - 1) // self.chunk_size
            for i in range(0, len(self.note_ids), self.chunk_size):
                chunk_index = i // self.chunk_size + 1
                if self._is_cancelled:
                    logger.info("Traitement par lots AI annulé par l'utilisateur.")
                    self.cancelled.emit()
                    return

                chunk_ids = self.note_ids[i : i + self.chunk_size]
                self.progress.emit(f"Traitement du lot {chunk_index}/{total_chunks} (Cartes {i + 1} à {min(i + self.chunk_size, len(self.note_ids))})...")

                payload = []
                for nid in chunk_ids:
                    note = NoteModel.get_by_id(nid)
                    active_version = NoteVersionModel.get_or_none(note=note, is_active=True)
                    if active_version:
                        content = json.loads(active_version.content)
                        content["note_id"] = note.id
                        payload.append(content)

                if not payload:
                    continue

                input_json = json.dumps(payload, ensure_ascii=False, indent=2)
                raw_response = self.ai_provider.generate(system_prompt=system_contract, user_prompt=input_json)

                try:
                    modified_notes = AIReponseParser.parse(raw_response)
                    if not isinstance(modified_notes, list):
                        raise ValueError("L'IA n'a pas renvoyé un tableau (list) JSON.")

                    with db.atomic():
                        for modified_note in modified_notes:
                            note_id = modified_note.pop("note_id", None)
                            if not note_id:
                                continue

                            db_note = NoteModel.get_by_id(note_id)
                            active_version = NoteVersionModel.get_or_none(note=db_note, is_active=True)

                            if active_version:
                                old_content = json.loads(active_version.content)
                                if old_content == modified_note:
                                    continue

                            db_note.add_version(modified_note, source="ai_batch")
                            db_note.status = "pending"
                            db_note.save()
                            total_processed += 1

                except (ValueError, TypeError) as e:
                    logger.exception("Erreur de parsing lors du batch edit sur le lot %d : %s", chunk_index, e)
                    self.error_signal.emit(f"Erreur de parsing sur un lot : {e}\nRéponse brute : {raw_response[:100]}...")
                    return

            if not self._is_cancelled:
                elapsed = time.perf_counter() - t0
                logger.info(
                    "BatchEditWorker terminé avec succès : %d notes modifiées en %.2fs",
                    total_processed,
                    elapsed,
                )
                self.finished_signal.emit(total_processed)

        except (ValueError, TypeError, RuntimeError) as e:
            logger.exception("Erreur critique lors du batch edit : %s", e)
            self.error_signal.emit(f"Erreur critique du Batch Edit : {e}")
