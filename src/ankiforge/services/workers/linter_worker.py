import json
import logging
from PySide6.QtCore import QThread, Signal, QObject
from typing import Optional

from ankiforge.database.models import NoteModel, NoteVersionModel, db

from ankiforge.database.models import LinterRuleModel, AuditRecordModel
from ankiforge.services.ai.utils import AIReponseParser

logger = logging.getLogger(__name__)


class LinterWorker(QThread):
    finished_processing = Signal(list)  # Renverra la liste des dicts de résultats
    error_occurred = Signal(str)
    progress_update = Signal(str)

    def __init__(self, note_ids: list[int], llm_config_id: int | None = None, force_recheck: bool = False, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.note_ids = note_ids
        self.llm_config_id = llm_config_id
        self.force_recheck = force_recheck  # Si True = Mode "Hard", Si False = Mode "Soft"

    def _build_dynamic_prompt(self) -> str:
        """Construit le prompt système en récupérant les règles actives depuis la base."""
        # On force la requête SQL à se terminer immédiatement avec list()
        active_rules = list(LinterRuleModel.select().where(LinterRuleModel.is_active == True))  # noqa: E712

        if not active_rules:
            # Fallback de sécurité si aucune règle n'est configurée
            return "Tu es un auditeur de flashcards..."
        prompt = "Tu es un auditeur de flashcards expert. Ton but est de vérifier si les cartes fournies respectent STRICTEMENT les règles suivantes :\n\n"

        for idx, rule in enumerate(active_rules, 1):
            prompt += f"RÈGLE {idx} : {rule.name}\n"
            if rule.description:
                prompt += f"Description : {rule.description}\n"
            prompt += f"Instruction stricte : {rule.prompt_injection}\n"
            if rule.example_bad and rule.example_good:
                prompt += f"Exemple de mauvaise carte : {rule.example_bad}\n"
                prompt += f"Exemple de carte corrigée : {rule.example_good}\n"
            prompt += "-" * 20 + "\n"

        prompt += (
            "\nPour chaque carte, retourne un objet JSON. Si la carte enfreint UNE de ces règles, "
            "'pass' doit être false, 'rule_broken' doit contenir le nom de la règle, 'reason' l'explication, "
            "et 'suggestion' le nouveau JSON de la carte corrigée.\n"
            "Format attendu : Un tableau JSON d'objets : "
            '[{ "note_id": 123, "pass": false, "rule_broken": "Nom", "reason": "...", "suggestion": {"Front": "...", "Back": "..."} }]'
        )
        return prompt

    def run(self):
        try:
            self.progress_update.emit("Initialisation de l'agent linter...")
            from ankiforge.database.models import LLMConfigModel
            from ankiforge.services.ai.flexible_service import AIManager

            if self.llm_config_id:
                config = LLMConfigModel.get_by_id(self.llm_config_id)
                llm_provider = AIManager.create_provider_from_config(config)
            else:
                self.ai_manager = AIManager()
                llm_provider = self.ai_manager.provider

            notes_to_analyze = []
            cached_results = []

            self.progress_update.emit("Vérification du cache d'audit...")
            for nid in self.note_ids:
                note = NoteModel.get_by_id(nid)
                active_version = NoteVersionModel.get_or_none(note=note, is_active=True)

                if not active_version:
                    continue

                if not self.force_recheck:
                    # On vérifie s'il existe déjà un audit pour CETTE version précise
                    existing_audit = AuditRecordModel.get_or_none(note=note, note_version=active_version)
                    if existing_audit:
                        # On restaure le résultat depuis la BDD au lieu d'appeler l'IA
                        cached_results.append(
                            {
                                "note_id": note.id,
                                "pass": existing_audit.is_compliant,
                                "rule_broken": existing_audit.rule_broken,
                                "reason": existing_audit.reason,
                                "suggestion": json.loads(existing_audit.suggestion) if existing_audit.suggestion else None,
                            }
                        )
                        continue

                # Si on est ici, la carte doit être analysée (nouvelle, modifiée, ou force_recheck)
                notes_to_analyze.append({"note_id": note.id, "content": json.loads(active_version.content)})

            final_results = cached_results

            if notes_to_analyze:
                chunk_size = 50
                total_chunks = (len(notes_to_analyze) + chunk_size - 1) // chunk_size

                for i in range(0, len(notes_to_analyze), chunk_size):
                    chunk = notes_to_analyze[i : i + chunk_size]
                    current_chunk_index = (i // chunk_size) + 1

                    self.progress_update.emit(f"Audit IA en cours (Lot {current_chunk_index}/{total_chunks} : {len(chunk)} cartes)...")

                    system_prompt = self._build_dynamic_prompt()
                    user_prompt = f"Voici les cartes à auditer :\n{json.dumps(chunk, ensure_ascii=False)}"

                    # --- SÉCURITÉ ANTI-DEADLOCK : Libération de SQLite ---
                    if not db.is_closed():
                        db.close()

                    # Appel réseau asynchrone (l'IA traite 50 cartes max)
                    raw_response = llm_provider.generate(system_prompt=system_prompt, user_prompt=user_prompt, response_format="json")

                    # Reconnexion à SQLite pour enregistrer ce lot
                    db.connect(reuse_if_open=True)
                    # -----------------------------------------------------

                    try:
                        llm_results = AIReponseParser.parse(raw_response)
                        if not isinstance(llm_results, list):
                            raise ValueError(f"L'IA n'a pas renvoyé une liste JSON pour le lot {current_chunk_index}.")

                        # 3. SAUVEGARDE DES RÉSULTATS DU LOT EN COURS
                        self.progress_update.emit(f"Sauvegarde du lot {current_chunk_index}/{total_chunks}...")
                        with db.atomic():
                            for res in llm_results:
                                res_note = NoteModel.get_by_id(res["note_id"])
                                res_version = NoteVersionModel.get(note=res_note, is_active=True)

                                # Nettoyage de l'ancien audit pour cette carte
                                AuditRecordModel.delete().where(AuditRecordModel.note == res_note, AuditRecordModel.note_version == res_version).execute()

                                # Insertion du nouveau résultat
                                AuditRecordModel.create(
                                    note=res_note,
                                    note_version=res_version,
                                    is_compliant=res.get("pass", res.get("pass_", True)),  # Sécurité si l'IA écrit "pass_"
                                    rule_broken=res.get("rule_broken"),
                                    reason=res.get("reason"),
                                    suggestion=json.dumps(res.get("suggestion"), ensure_ascii=False) if res.get("suggestion") else None,
                                )

                        # Ajout des résultats de ce lot à la liste finale
                        final_results.extend(llm_results)

                    except Exception as e:
                        logger.error(f"Erreur de parsing ou d'insertion sur le lot {current_chunk_index}: {e}", exc_info=True)
                        raise RuntimeError(f"Le lot {current_chunk_index} a échoué : {e}") from e

                # Envoi du résultat total (Cache + Nouveaux Lots) à l'UI
            self.progress_update.emit("Audit terminé !")
            self.finished_processing.emit(final_results)

        except Exception as e:
            logger.error(f"Linter error: {e}", exc_info=True)
            # S'assurer de rouvrir la BDD en cas d'erreur fatale si elle est restée fermée
            if db.is_closed():
                db.connect(reuse_if_open=True)
            self.error_occurred.emit(str(e))
