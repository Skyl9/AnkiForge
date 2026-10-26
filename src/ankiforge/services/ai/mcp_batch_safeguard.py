"""Garde-fou volumétrique et refus structuré pour les outils de lot MCP (ADR 0048).

Fournit un contrôle partagé et strict pour les outils de mutation par lot
(`create_notes_batch`, `propose_cards_batch_refactor`).
Applique un plafond dur de 100 notes et 32 000 caractères, cumulatif,
avec évaluation ordonnée sans parsing préalable pour la borne textuelle,
et sans écriture d'état partiel.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Seuils canoniques définis par l'ADR 0048
MAX_BATCH_CHARS: int = 32_000
MAX_BATCH_NOTES: int = 100
RECOMMENDED_BATCH_NOTES: str = "5 à 8 notes"
RECOMMENDED_BATCH_CHARS: str = "≈ 8 000 caractères"
BATCH_SUGGESTION_TEXT: str = "Fractionnez en sous-lots de 5 à 8 notes (≈ 8 000 caractères) via des appels successifs sur le même Staged Bundle."


class MCPBatchSafeguard:
    """Garde-fou volumétrique partagé pour les outils de lot MCP."""

    @classmethod
    def validate_batch_payload(
        cls,
        tool_name: str,
        raw_payload: str | list[Any],
    ) -> tuple[list[Any] | None, str | None]:
        """Valide la conformité volumétrique et syntaxique d'un argument de lot MCP.

        Ordre d'évaluation strict :
        1. Volume textuel (`PAYLOAD_TOO_LARGE`) avant tout décodage JSON.
        2. Validité JSON (`INVALID_JSON`) sans tentative de réparation automatique.
        3. Plafond du nombre de notes (`TOO_MANY_NOTES`).

        Instrumentation :
        Journalise uniquement des métadonnées pures (aucun contenu de carte, ni extrait, ni secret).

        Returns:
            Un tuple `(parsed_list, None)` en cas de succès,
            ou `(None, error_json_str)` en cas de refus.
        """
        # 1. Normalisation en chaîne brute pour mesure textuelle et SHA-256
        if isinstance(raw_payload, str):
            raw_str = raw_payload
        elif isinstance(raw_payload, list):
            raw_str = json.dumps(raw_payload, ensure_ascii=False)
        else:
            raw_str = str(raw_payload)

        raw_bytes = raw_str.encode("utf-8")
        received_chars = len(raw_str)
        received_bytes = len(raw_bytes)
        sha256_short = hashlib.sha256(raw_bytes).hexdigest()[:12]

        # -------------------------------------------------------------
        # PALLIER 1 : Contrôle volumétrique brut (AVANT TOUT PARSING)
        # -------------------------------------------------------------
        if received_chars > MAX_BATCH_CHARS:
            error_code = "PAYLOAD_TOO_LARGE"
            logger.warning(
                "Garde-fou lot MCP [%s] : refus error_code=%s chars=%d bytes=%d sha256=%s valid_json=None truncated_suspected=False notes=None error_pos=None",
                tool_name,
                error_code,
                received_chars,
                received_bytes,
                sha256_short,
            )
            err_payload: dict[str, Any] = {
                "status": "error",
                "error_code": error_code,
                "tool": tool_name,
                "received_chars": received_chars,
                "max_chars": MAX_BATCH_CHARS,
                "received_notes": None,
                "max_notes": MAX_BATCH_NOTES,
                "message": (f"Volume de payload dépassé : {received_chars} caractères reçus (limite stricte : {MAX_BATCH_CHARS} caractères)."),
                "suggestion": BATCH_SUGGESTION_TEXT,
                "no_state_written": True,
            }
            return None, json.dumps(err_payload, ensure_ascii=False, indent=2)

        # -------------------------------------------------------------
        # PALLIER 2 : Décodage JSON standard (zéro rafistolage de troncature)
        # -------------------------------------------------------------
        parsed_obj: Any = None
        error_pos: int | None = None
        err_msg = ""
        try:
            parsed_obj = raw_payload if isinstance(raw_payload, list) else json.loads(raw_str)
        except json.JSONDecodeError as exc:
            error_pos = exc.pos
            err_msg = exc.msg
        except Exception as exc:
            error_pos = 0
            err_msg = str(exc)

        # Si le JSON n'est pas une liste ou a levé une erreur
        if error_pos is not None or not isinstance(parsed_obj, list):
            error_code = "INVALID_JSON"
            resolved_error_pos = error_pos if error_pos is not None else 0
            truncated_suspected = "unterminated string" in err_msg.lower() or resolved_error_pos >= max(0, received_chars - 5)

            logger.warning(
                "Garde-fou lot MCP [%s] : refus error_code=%s chars=%d bytes=%d sha256=%s valid_json=False truncated_suspected=%s notes=None error_pos=%d",
                tool_name,
                error_code,
                received_chars,
                received_bytes,
                sha256_short,
                truncated_suspected,
                resolved_error_pos,
            )
            err_payload = {
                "status": "error",
                "error_code": error_code,
                "tool": tool_name,
                "received_chars": received_chars,
                "max_chars": MAX_BATCH_CHARS,
                "received_notes": None,
                "max_notes": MAX_BATCH_NOTES,
                "error_position": resolved_error_pos,
                "message": (f"Format JSON invalide à la position {resolved_error_pos} : {err_msg}" if err_msg else "Le payload doit être une liste JSON valide."),
                "suggestion": BATCH_SUGGESTION_TEXT,
                "no_state_written": True,
            }
            return None, json.dumps(err_payload, ensure_ascii=False, indent=2)

        # -------------------------------------------------------------
        # PALLIER 3 : Contrôle du nombre de notes (plafond dur 100)
        # -------------------------------------------------------------
        received_notes = len(parsed_obj)
        if received_notes > MAX_BATCH_NOTES:
            error_code = "TOO_MANY_NOTES"
            logger.warning(
                "Garde-fou lot MCP [%s] : refus error_code=%s chars=%d bytes=%d sha256=%s valid_json=True truncated_suspected=False notes=%d error_pos=None",
                tool_name,
                error_code,
                received_chars,
                received_bytes,
                sha256_short,
                received_notes,
            )
            err_payload = {
                "status": "error",
                "error_code": error_code,
                "tool": tool_name,
                "received_chars": received_chars,
                "max_chars": MAX_BATCH_CHARS,
                "received_notes": received_notes,
                "max_notes": MAX_BATCH_NOTES,
                "message": (f"Plafond de sécurité dépassé : {received_notes} notes demandées (limite stricte : {MAX_BATCH_NOTES} notes par appel)."),
                "suggestion": BATCH_SUGGESTION_TEXT,
                "no_state_written": True,
            }
            return None, json.dumps(err_payload, ensure_ascii=False, indent=2)

        # -------------------------------------------------------------
        # Cas Nominal : Métadonnées pures journalisées en INFO
        # -------------------------------------------------------------
        logger.info(
            "Garde-fou lot MCP [%s] : accepté chars=%d bytes=%d sha256=%s valid_json=True truncated_suspected=False notes=%d",
            tool_name,
            received_chars,
            received_bytes,
            sha256_short,
            received_notes,
        )

        return parsed_obj, None
