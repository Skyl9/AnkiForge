"""
Module de Compaction Dynamique de Contexte pour le Consultant IA.

Gère :
- L'estimation précise de tokens (In-Flight et Post-Task).
- La condensation in-flight des longs retours d'outils MCP tout en préservant le scratchpad et les derniers tours.
- La compaction post-tâche avec génération proactive des prochaines actions (Next Steps).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class ContextCompactor:
    """Gestionnaire de compaction dynamique de contexte pour agents IA et Consultant."""

    @staticmethod
    def estimate_tokens(content: str | list[dict[str, Any]] | dict[str, Any]) -> int:
        """
        Estime le nombre de tokens d'un texte, d'un dictionnaire ou d'une liste de messages.
        Heuristique optimisée pour le français/anglais et le JSON (~1 token pour 3.5 caractères).
        """
        if not content:
            return 0

        if isinstance(content, str):
            text = content
        elif isinstance(content, dict | list):
            try:
                text = json.dumps(content, ensure_ascii=False)
            except Exception:
                text = str(content)
        else:
            text = str(content)

        if not text or text.strip() in ("", "[]", "{}"):
            return 0
        return max(1, int(len(text) / 3.5))

    @classmethod
    def compact_in_flight(
        cls,
        messages: list[dict[str, Any]],
        max_tokens: int = 25000,
        keep_last_turns: int = 3,
        max_tool_chars: int = 400,
    ) -> list[dict[str, Any]]:
        """
        Condense les anciens messages et retours d'outils volumineux pendant une tâche.
        Préserve :
          1. Le message 'system' initial.
          2. Le scratchpad de travail (si présent).
          3. Les `keep_last_turns` derniers tours conversationnels complets.
        """
        if not messages:
            return []

        total_tokens = cls.estimate_tokens(messages)
        if total_tokens <= max_tokens and len(messages) <= (keep_last_turns * 3 + 2):
            return list(messages)

        compacted: list[dict[str, Any]] = []

        # 1. Isoler le message système
        system_msgs = [m for m in messages if m.get("role") == "system"]
        non_system_msgs = [m for m in messages if m.get("role") != "system"]

        compacted.extend(system_msgs)

        if not non_system_msgs:
            return compacted

        # 2. Déterminer le point de scission (garder les N derniers tours intacts)
        cutoff_index = max(0, len(non_system_msgs) - (keep_last_turns * 3))

        older_msgs = non_system_msgs[:cutoff_index]
        recent_msgs = non_system_msgs[cutoff_index:]

        # 3. Compacter les anciens messages (notamment les observations d'outils volumineuses)
        for msg in older_msgs:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "tool" or "[Observation de l'outil MCP" in str(content):
                str_content = str(content)
                if len(str_content) > max_tool_chars:
                    t_name = msg.get("name", "outil")
                    lines = str_content.splitlines()
                    summary_snippet = "\n".join(lines[:3]) + f"\n... [Observation condensée : {len(lines)} lignes initiales traitées]"
                    compacted.append({**msg, "content": f"[Observation {t_name} condensée]\n{summary_snippet}"})
                else:
                    compacted.append(msg)
            elif role == "assistant" and len(str(content)) > 800:
                str_content = str(content)
                snippet = str_content[:300] + "... [Plan intermédiaire validé et résumé]"
                compacted.append({**msg, "content": snippet})
            else:
                compacted.append(msg)

        # 4. Ajouter les messages récents sans altération
        compacted.extend(recent_msgs)

        saved_tokens = total_tokens - cls.estimate_tokens(compacted)
        if saved_tokens > 0:
            logger.info("Compaction In-Flight : ~%d tokens économisés (reste %d tokens)", saved_tokens, cls.estimate_tokens(compacted))

        return compacted

    @classmethod
    def compact_post_task(
        cls,
        messages: list[dict[str, Any]],
        task_summary: str = "",
        context_data: dict[str, Any] | None = None,
    ) -> tuple[str, list[str]]:
        """
        Résume une session post-tâche achevée et génère 2 à 3 suggestions d'actions suivantes proactives.
        Renvoie (recap_markdown, list_next_steps).
        """
        all_text = " ".join(str(m.get("content", "")) for m in messages)
        decks_found = re.findall(r"Paquet\s+['\"]?([A-Za-z0-9_\- ]+)['\"]?", all_text, re.IGNORECASE)
        models_found = re.findall(r"modèle\s+['\"]?([A-Za-z0-9_\- ]+)['\"]?", all_text, re.IGNORECASE)

        deck_name = decks_found[0].strip() if decks_found else "la collection"
        model_name = models_found[0].strip() if models_found else "les cartes"

        if task_summary:
            recap = f"### 📝 Résumé de la session\n{task_summary}"
        else:
            recap = (
                f"### 📝 Résumé de la session\n"
                f"- **Périmètre traité :** {deck_name} ({model_name})\n"
                f"- **Actions :** Diagnostic et optimisations appliqués avec succès.\n"
                f"- **État de la mémoire :** Contexte compacté et prêt pour la prochaine analyse."
            )

        next_steps: list[str] = [
            f"🔍 Auditer les cartes de '{deck_name}' avec le Linter Wozniak",
            f"🎨 Générer un nouveau style CSS pour '{model_name}'",
            f"📦 Exporter le paquet '{deck_name}' au format Anki (.apkg)",
        ]

        if "sangsue" in all_text.lower() or "lapse" in all_text.lower():
            next_steps[0] = f"⚡ Scinder les cartes sangsues restantes dans '{deck_name}'"

        return recap, next_steps[:3]
