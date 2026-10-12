"""
Gestionnaire de télémétrie en temps réel pour le serveur MCP d'AnkiForge.

Fournit un tampon circulaire en mémoire pour l'historique des invocations d'outils,
assure le masquage systématique des secrets et clés d'API (via SecretRedactionFilter),
et notifie l'interface graphique via des signaux Qt thread-safe.
"""

from __future__ import annotations

import collections
import json
import logging
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from PySide6.QtCore import QObject, Signal

from ankiforge.utils.logger import redact_secrets

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

logger = logging.getLogger(__name__)

# Mots-clés sensibles dont la valeur brute est masquée immédiatement
_SENSITIVE_KEY_NAMES = {
    "api_key",
    "apikey",
    "auth_token",
    "authorization",
    "bearer",
    "password",
    "secret",
    "secret_key",
    "token",
}


def sanitize_value(val: Any) -> Any:
    """Sanitise récursivement une valeur pour masquer les clés et secrets."""
    if isinstance(val, dict):
        sanitized_dict: dict[str, Any] = {}
        for k, v in val.items():
            if str(k).lower() in _SENSITIVE_KEY_NAMES:
                sanitized_dict[k] = "[REDACTED_SECRET]"
            else:
                sanitized_dict[k] = sanitize_value(v)
        return sanitized_dict
    if isinstance(val, list):
        return [sanitize_value(v) for v in val]
    if isinstance(val, tuple):
        return tuple(sanitize_value(v) for v in val)
    if isinstance(val, str):
        return redact_secrets(val)
    return val


def summarize_arguments(args: dict[str, Any], max_length: int = 120) -> str:
    """Produit une représentation condensée et sécurisée des arguments pour l'affichage en table."""
    if not args:
        return ""
    parts: list[str] = []
    for k, v in args.items():
        val_str = str(v)
        if len(val_str) > 35:
            val_str = val_str[:32] + "..."
        parts.append(f"{k}={val_str}")
    summary = ", ".join(parts)
    if len(summary) > max_length:
        summary = summary[: max_length - 3] + "..."
    return redact_secrets(summary)


@dataclass
class MCPActivityRecord:
    """Enregistrement d'une invocation d'outil MCP."""

    call_id: str
    tool_name: str
    started_at: datetime
    ended_at: datetime | None = None
    duration_ms: float = 0.0
    status: Literal["running", "success", "error"] = "running"
    args_summary: str = ""
    args_full: dict[str, Any] = field(default_factory=dict)
    result_summary: str = ""
    result_full: str = ""
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convertit l'enregistrement en dictionnaire sérialisable."""
        res = asdict(self)
        res["started_at"] = self.started_at.isoformat()
        res["ended_at"] = self.ended_at.isoformat() if self.ended_at else None
        return res


class MCPActivitySignals(QObject):
    """Signaux Qt émis par le tracker d'activité MCP pour mettre à jour l'UI."""

    activity_started = Signal(dict)
    activity_updated = Signal(dict)
    history_cleared = Signal()


class MCPActivityTracker:
    """
    Gestionnaire thread-safe de la télémétrie des appels d'outils MCP.

    Conserve un tampon circulaire (deque) des N derniers appels et émet des
    signaux Qt lors du démarrage, du succès, de l'échec ou de la purge.
    """

    def __init__(self, max_history: int = 100) -> None:
        self.max_history = max_history
        self._history: collections.deque[MCPActivityRecord] = collections.deque(maxlen=max_history)
        self._by_id: dict[str, MCPActivityRecord] = {}
        self._lock = threading.Lock()
        self._total_calls = 0
        self.signals = MCPActivitySignals()

    @property
    def total_calls(self) -> int:
        with self._lock:
            return self._total_calls

    def start_tracking(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Enregistre le démarrage de l'invocation d'un outil MCP."""
        call_id = uuid.uuid4().hex[:8]
        now = datetime.now()

        sanitized_args = sanitize_value(arguments)
        if not isinstance(sanitized_args, dict):
            sanitized_args = {"data": sanitized_args}

        summary = summarize_arguments(sanitized_args)

        record = MCPActivityRecord(
            call_id=call_id,
            tool_name=tool_name,
            started_at=now,
            status="running",
            args_summary=summary,
            args_full=sanitized_args,
        )

        with self._lock:
            self._total_calls += 1
            if len(self._history) >= self.max_history:
                # Évincer le plus ancien de _by_id
                oldest = self._history[0]
                self._by_id.pop(oldest.call_id, None)

            self._history.append(record)
            self._by_id[call_id] = record

        try:
            self.signals.activity_started.emit(record.to_dict())
        except Exception as e:
            logger.debug("Exception émission activity_started : %s", e)

        return call_id

    def record_success(
        self,
        call_id: str,
        result: Any,
        duration_ms: float,
    ) -> MCPActivityRecord | None:
        """Enregistre le succès de l'invocation avec son résultat et sa durée."""
        now = datetime.now()

        # Formatage textuel du résultat
        if hasattr(result, "content") and result.content:
            text_parts: list[str] = []
            for item in result.content:
                text_parts.append(str(getattr(item, "text", item)))
            res_full = "\n".join(text_parts)
        elif isinstance(result, (dict, list)):
            try:
                res_full = json.dumps(result, ensure_ascii=False, indent=2)
            except Exception:
                res_full = str(result)
        else:
            res_full = str(result)

        res_full = redact_secrets(res_full)
        res_summary = res_full.strip()
        if len(res_summary) > 120:
            res_summary = res_summary[:117] + "..."

        with self._lock:
            record = self._by_id.get(call_id)
            if not record:
                return None

            record.ended_at = now
            record.duration_ms = round(duration_ms, 2)
            record.status = "success"
            record.result_summary = res_summary
            record.result_full = res_full
            record.error_message = None

        try:
            self.signals.activity_updated.emit(record.to_dict())
        except Exception as e:
            logger.debug("Exception émission activity_updated (success) : %s", e)

        return record

    def record_error(
        self,
        call_id: str,
        error: str | Exception,
        duration_ms: float,
    ) -> MCPActivityRecord | None:
        """Enregistre l'échec de l'invocation avec son message d'erreur et sa durée."""
        now = datetime.now()
        err_str = redact_secrets(str(error))
        err_summary = err_str.strip()
        if len(err_summary) > 120:
            err_summary = err_summary[:117] + "..."

        with self._lock:
            record = self._by_id.get(call_id)
            if not record:
                return None

            record.ended_at = now
            record.duration_ms = round(duration_ms, 2)
            record.status = "error"
            record.error_message = err_str
            record.result_summary = err_summary
            record.result_full = err_str

        try:
            self.signals.activity_updated.emit(record.to_dict())
        except Exception as e:
            logger.debug("Exception émission activity_updated (error) : %s", e)

        return record

    def get_history(self) -> list[MCPActivityRecord]:
        """Retourne un instantané ordonné de l'historique (du plus ancien au plus récent)."""
        with self._lock:
            return list(self._history)

    def get_record(self, call_id: str) -> MCPActivityRecord | None:
        """Récupère un enregistrement par son identifiant unique."""
        with self._lock:
            return self._by_id.get(call_id)

    def clear_history(self) -> None:
        """Réinitialise l'historique complet des appels de la session."""
        with self._lock:
            self._history.clear()
            self._by_id.clear()

        try:
            self.signals.history_cleared.emit()
        except Exception as e:
            logger.debug("Exception émission history_cleared : %s", e)

    def attach_to_server(self, mcp_server: MCPServer) -> None:
        """
        Intercepte automatiquement les appels d'outils du MCPServer sans modifier son code.

        Enveloppe la méthode call_tool() de l'instance pour enregistrer
        systématiquement les temps d'exécution, statuts et arguments.
        """
        if getattr(mcp_server, "_activity_tracking_attached", False):
            return

        orig_call_tool = mcp_server.call_tool

        async def tracked_call_tool(
            name: str,
            arguments: dict[str, Any],
            context: Any = None,
        ) -> Any:
            t0 = time.perf_counter()
            call_id = self.start_tracking(name, arguments)
            try:
                # Appelle la méthode d'origine
                result = await orig_call_tool(name, arguments, context=context)
                duration_ms = (time.perf_counter() - t0) * 1000.0

                is_err = getattr(result, "is_error", False)
                if is_err:
                    content = getattr(result, "content", [])
                    err_text = ""
                    if content:
                        err_text = "\n".join(str(getattr(c, "text", c)) for c in content)
                    self.record_error(call_id, err_text or "CallToolResult error", duration_ms)
                else:
                    self.record_success(call_id, result, duration_ms)
                return result
            except Exception as exc:
                duration_ms = (time.perf_counter() - t0) * 1000.0
                self.record_error(call_id, exc, duration_ms)
                raise

        mcp_server.call_tool = tracked_call_tool  # type: ignore[method-assign]
        mcp_server._activity_tracking_attached = True  # type: ignore[attr-defined]
        logger.debug("Télémétrie d'activité attachée au serveur MCP '%s'.", getattr(mcp_server, "name", "MCP"))


# Singleton global pour l'application
_GLOBAL_TRACKER: MCPActivityTracker | None = None
_TRACKER_LOCK = threading.Lock()


def get_mcp_activity_tracker() -> MCPActivityTracker:
    """Retourne le gestionnaire de télémétrie MCP singleton."""
    global _GLOBAL_TRACKER
    if _GLOBAL_TRACKER is None:
        with _TRACKER_LOCK:
            if _GLOBAL_TRACKER is None:
                _GLOBAL_TRACKER = MCPActivityTracker()
    return _GLOBAL_TRACKER


def reset_mcp_activity_tracker() -> None:
    """Réinitialise l'instance singleton (utilisé principalement pour les tests)."""
    global _GLOBAL_TRACKER
    with _TRACKER_LOCK:
        if _GLOBAL_TRACKER is not None:
            _GLOBAL_TRACKER.clear_history()
        _GLOBAL_TRACKER = None
