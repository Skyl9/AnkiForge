"""
Worker asynchrone pour l'Audit et le Linter Wozniak AnkiForge.
Orchestre l'analyse par lots des cartes en arrière-plan et gère la persistance de l'audit en base.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, QThread, Signal

from ankiforge.database.models import (
    AuditRecordModel,
    LinterRuleModel,
    NoteModel,
    NoteVersionModel,
    db,
    seed_default_linter_rules,
)
from ankiforge.services.ai.linter import normalize_linter_suggestion
from ankiforge.services.ai.utils import AIReponseParser

logger = logging.getLogger(__name__)


class LinterWorker(QThread):
    """
    Worker d'analyse des cartes du paquet selon les règles d'audit Wozniak et personnalisées.
    """

    finished_processing = Signal(list)  # Renvoie la liste des dicts de résultats
    error_occurred = Signal(str)
    progress_update = Signal(str)

    def __init__(
        self,
        note_ids: List[int],
        llm_config_id: Optional[int] = None,
        force_recheck: bool = False,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.note_ids = note_ids
        self.llm_config_id = llm_config_id
        self.force_recheck = force_recheck

    def _build_dynamic_prompt(self) -> str:
        """Construit le prompt système en récupérant les règles actives depuis la base."""
        seed_default_linter_rules()
        active_rules = list(LinterRuleModel.select().where(LinterRuleModel.is_active == True))  # noqa: E712

        prompt = (
            "Tu es un auditeur de flashcards expert (Linter Wozniak AnkiForge). "
            "Ton but est d'analyser chaque carte fournie et de vérifier si elle respecte STRICTEMENT les règles d'ergonomie et d'apprentissage suivantes :\n\n"
        )

        for idx, rule in enumerate(active_rules, 1):
            prompt += f"### RÈGLE {idx} : {rule.name} [Catégorie : {rule.category}]\n"
            if rule.description:
                prompt += f"Description : {rule.description}\n"
            prompt += f"Instruction : {rule.prompt_injection}\n"
            if rule.example_bad and rule.example_good:
                prompt += f"Exemple mauvaise carte : {rule.example_bad}\n"
                prompt += f"Exemple carte corrigée : {rule.example_good}\n"
            prompt += "-" * 30 + "\n"

        prompt += """
### FORMAT DE RÉPONSE STRICT (TABLEAU JSON) :
Pour chaque carte reçue, retourne un objet JSON :
- "note_id" (int) : Identifiant de la note
- "pass" (bool) : `true` si la carte est exemplaire et conforme, `false` si elle enfreint au moins une règle
- "rule_broken" (str) : Nom exact de la règle enfreinte (ou null si pass=true)
- "category" (str) : Identifiant de la catégorie de la règle (ex: "cat-atomicite", "cat-katex", "cat-cloze", "cat-interference", ou catégorie custom)
- "reason" (str) : Explication concise et pédagogique du problème
- "suggestion" (dict) : Nouveau contenu corrigé de la carte contenant IMPÉRATIVEMENT les clés :
    - "Recto" : La question ou formulation univoque révisée
    - "Verso" : La réponse concise et atomique (avec syntaxe KaTeX $$...$$ si formule)
    - "Champ Annexe Extra" : Le contexte secondaire, mnémotechnique ou notes
    - "Tags" : Tags de la carte (inclure #linter-corrigé)

Exemple de réponse attendue :
[
  {
    "note_id": 123,
    "pass": false,
    "rule_broken": "Principe d'Atomicité Minimale",
    "category": "cat-atomicite",
    "reason": "La carte pose 3 questions à la fois et contient une liste énumérative.",
    "suggestion": {
      "Recto": "Quel est le rôle principal de l'allocateur C++20 ?",
      "Verso": "Gérer l'allocation dynamique de mémoire sur le heap.",
      "Champ Annexe Extra": "Les autres notions sont réparties dans des cartes dédiées.",
      "Tags": "#cpp #memory #linter-corrigé"
    }
  }
]
Retourne UNIQUEMENT le tableau JSON valide, sans texte d'introduction ni de conclusion.
"""
        return prompt

    def run(self) -> None:
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

            notes_to_analyze: List[Dict[str, Any]] = []
            cached_results: List[Dict[str, Any]] = []

            self.progress_update.emit("Vérification du cache d'audit...")
            for nid in self.note_ids:
                note = NoteModel.get_by_id(nid)
                active_version = NoteVersionModel.get_or_none(note=note, is_active=True)

                if not active_version:
                    continue

                content_dict = {}
                try:
                    content_dict = json.loads(active_version.content)
                except Exception:
                    content_dict = {"Recto": str(active_version.content), "Verso": ""}

                if not self.force_recheck:
                    existing_audit = AuditRecordModel.get_or_none(note=note, note_version=active_version)
                    if existing_audit:
                        raw_sug = json.loads(existing_audit.suggestion) if existing_audit.suggestion else None
                        normalized_sug = normalize_linter_suggestion(raw_sug, original_content=content_dict, rule_name=existing_audit.rule_broken or "")
                        cached_results.append(
                            {
                                "note_id": note.id,
                                "pass": existing_audit.is_compliant,
                                "rule_broken": existing_audit.rule_broken,
                                "reason": existing_audit.reason,
                                "suggestion": normalized_sug,
                            }
                        )
                        continue

                notes_to_analyze.append({"note_id": note.id, "content": content_dict})

            final_results = list(cached_results)

            if notes_to_analyze:
                chunk_size = 50
                total_chunks = (len(notes_to_analyze) + chunk_size - 1) // chunk_size

                for i in range(0, len(notes_to_analyze), chunk_size):
                    chunk = notes_to_analyze[i : i + chunk_size]
                    current_chunk_index = (i // chunk_size) + 1

                    self.progress_update.emit(f"Audit IA en cours (Lot {current_chunk_index}/{total_chunks} : {len(chunk)} cartes)...")

                    system_prompt = self._build_dynamic_prompt()
                    user_prompt = f"Voici les cartes à auditer :\n{json.dumps(chunk, ensure_ascii=False, indent=2)}"

                    if not db.is_closed():
                        db.close()

                    raw_response = llm_provider.generate(system_prompt=system_prompt, user_prompt=user_prompt, response_format="json")

                    db.connect(reuse_if_open=True)

                    try:
                        llm_results = AIReponseParser.parse(raw_response)
                        if not isinstance(llm_results, list):
                            raise ValueError(f"L'IA n'a pas renvoyé une liste JSON pour le lot {current_chunk_index}.")

                        self.progress_update.emit(f"Sauvegarde du lot {current_chunk_index}/{total_chunks}...")
                        with db.atomic():
                            for res in llm_results:
                                res_note_id = res.get("note_id")
                                if not res_note_id:
                                    continue
                                res_note = NoteModel.get_by_id(res_note_id)
                                res_version = NoteVersionModel.get(note=res_note, is_active=True)

                                original_c = {}
                                try:
                                    original_c = json.loads(res_version.content)
                                except Exception:
                                    original_c = {"Recto": str(res_version.content)}

                                normalized_sug = normalize_linter_suggestion(res.get("suggestion"), original_content=original_c, rule_name=res.get("rule_broken", ""))
                                res["suggestion"] = normalized_sug

                                AuditRecordModel.delete().where(AuditRecordModel.note == res_note, AuditRecordModel.note_version == res_version).execute()
                                AuditRecordModel.create(
                                    note=res_note,
                                    note_version=res_version,
                                    is_compliant=res.get("pass", res.get("pass_", True)),
                                    rule_broken=res.get("rule_broken"),
                                    reason=res.get("reason"),
                                    suggestion=json.dumps(normalized_sug, ensure_ascii=False),
                                )

                        final_results.extend(llm_results)

                    except Exception as e:
                        logger.error(f"Erreur de parsing ou d'insertion sur le lot {current_chunk_index}: {e}", exc_info=True)
                        raise RuntimeError(f"Le lot {current_chunk_index} a échoué : {e}") from e

            self.progress_update.emit("Audit terminé !")
            self.finished_processing.emit(final_results)

        except Exception as e:
            logger.error(f"Linter error: {e}", exc_info=True)
            if db.is_closed():
                db.connect(reuse_if_open=True)
            self.error_occurred.emit(str(e))
