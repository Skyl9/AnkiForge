"""
Système de Logging Asynchrone, Sécurisé et Haute Performance d'AnkiForge.
Conforme à la Règle 19 de GEMINI.md.

Caractéristiques :
1. Architecture non-bloquante : QueueHandler + QueueListener pour zéro latence sur l'I/O disque et l'UI.
2. Sanitisation automatique (SecretRedactionFilter) : Masquage automatique des clés API (OpenAI, Google, Anthropic, tokens).
3. Contextualisation dynamique (ContextInjectionFilter) : Profil actif, nom court de thread, horodatage milliseconde.
4. Buffer circulaire en mémoire (RingBufferHandler) : Consultation temps réel dans l'interface sans verrou disque.
5. Gestionnaire de crash post-mortem (sys.excepthook & threading.excepthook) : Traçabilité absolue en cas d'erreur fatale.
"""

from __future__ import annotations

from collections import deque
import logging
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler
from pathlib import Path
import platform
import queue
import re
import sys
import threading
from typing import Any, Callable, List, Optional

from ankiforge.utils.paths import get_active_profile, get_app_data_dir

# ── EXPRESSIONS RÉGULIÈRES POUR LE MASQUAGE DES SECRETS (PII / CLÉS API) ──

_RE_ANTHROPIC_KEY = re.compile(r"sk-ant-[a-zA-Z0-9_\-]{15,}")
_RE_OPENAI_KEY = re.compile(r"sk-[a-zA-Z0-9_\-]{20,}")
_RE_GOOGLE_KEY = re.compile(r"AIza[0-9A-Za-z\-_]{35}")
_RE_BEARER_TOKEN = re.compile(r"(Bearer\s+)[a-zA-Z0-9_\-\.]{15,}", re.IGNORECASE)
_RE_PASSWORD_PARAM = re.compile(
    r"(password|api_key|secret|token|auth_token)\s*([:=])\s*['\"]?([^\s'\",]+)['\"]?",
    re.IGNORECASE,
)


def redact_secrets(text: str) -> str:
    """Masque automatiquement les clés API, tokens et mots de passe dans une chaîne."""
    if not text or not isinstance(text, str):
        return str(text)

    # 1. Clés d'API spécifiques (Anthropic en premier car commence aussi par 'sk-')
    sanitized = _RE_ANTHROPIC_KEY.sub("[REDACTED_ANTHROPIC_KEY]", text)
    sanitized = _RE_OPENAI_KEY.sub("[REDACTED_OPENAI_KEY]", sanitized)
    sanitized = _RE_GOOGLE_KEY.sub("[REDACTED_GEMINI_KEY]", sanitized)

    # 2. Tokens d'authentification Bearer
    sanitized = _RE_BEARER_TOKEN.sub(r"\1[REDACTED_TOKEN]", sanitized)

    # 3. Paramètres génériques (password=xxx, api_key=yyy)
    sanitized = _RE_PASSWORD_PARAM.sub(r"\1\2[REDACTED_SECRET]", sanitized)

    return sanitized


class SecretRedactionFilter(logging.Filter):
    """Filtre de logging interceptant et masquant les secrets avant tout traitement."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_secrets(record.msg)

        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: redact_secrets(str(v)) for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(redact_secrets(str(a)) if isinstance(a, str) else a for a in record.args)

        if record.exc_text:
            record.exc_text = redact_secrets(record.exc_text)

        if record.stack_info:
            record.stack_info = redact_secrets(record.stack_info)

        return True


class ContextInjectionFilter(logging.Filter):
    """Enrichit chaque enregistrement de log avec le profil actif et le thread d'exécution."""

    def filter(self, record: logging.LogRecord) -> bool:
        # Profil actif
        try:
            record.profile_name = get_active_profile() or "default"
        except Exception:
            record.profile_name = "default"

        # Nom court du thread
        t_name = threading.current_thread().name
        if t_name == "MainThread":
            short_t = "Main"
        elif "QThreadPool" in t_name or "ThreadPool" in t_name:
            short_t = "QTP"
        elif len(t_name) > 12:
            short_t = t_name[:12]
        else:
            short_t = t_name
        record.thread_short_name = short_t

        return True


class AnkiForgeLogFormatter(logging.Formatter):
    """
    Formatteur de logs standard d'AnkiForge avec horodatage milliseconde et contexte enrichi.
    Exemple : [2026-08-27 19:45:00.123] [INFO   ] [default:Main] [ankiforge.utils.paths:42] Message
    """

    DEFAULT_FORMAT = "[%(asctime)s.%(msecs)03d] [%(levelname)-7s] [%(profile_name)s:%(thread_short_name)s] [%(name)s:%(lineno)d] %(message)s"
    DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

    # Codes couleurs ANSI pour la console
    ANSI_COLORS = {
        logging.DEBUG: "\033[36m",  # Cyan
        logging.INFO: "\033[32m",  # Vert
        logging.WARNING: "\033[33m",  # Jaune
        logging.ERROR: "\033[31m",  # Rouge
        logging.CRITICAL: "\033[1;41m\033[97m",  # Gras Rouge Fond Inversé
    }
    ANSI_RESET = "\033[0m"

    def __init__(self, use_colors: bool = False) -> None:
        super().__init__(fmt=self.DEFAULT_FORMAT, datefmt=self.DATE_FORMAT)
        self.use_colors = use_colors

    def format(self, record: logging.LogRecord) -> str:
        # S'assurer que les attributs injectés existent toujours
        if not hasattr(record, "profile_name"):
            record.profile_name = "default"
        if not hasattr(record, "thread_short_name"):
            record.thread_short_name = "Main"

        formatted = super().format(record)
        # Défense en profondeur : sanitisation du message formaté
        sanitized = redact_secrets(formatted)

        if self.use_colors and record.levelno in self.ANSI_COLORS:
            color = self.ANSI_COLORS[record.levelno]
            return f"{color}{sanitized}{self.ANSI_RESET}"

        return sanitized


class RingBufferHandler(logging.Handler):
    """
    Buffer circulaire en mémoire conservant les derniers enregistrements de log.
    Permet la consultation instantanée dans l'IHM (terminal de log, modale de diagnostic)
    sans aucune opération d'E/S sur disque.
    """

    def __init__(self, max_records: int = 500) -> None:
        super().__init__()
        self.max_records = max_records
        self._buffer: deque[logging.LogRecord] = deque(maxlen=max_records)
        self._lock = threading.Lock()
        self._callbacks: List[Callable[[str, int], None]] = []

    def emit(self, record: logging.LogRecord) -> None:
        with self._lock:
            self._buffer.append(record)
            msg_formatted = self.format(record)
            for cb in self._callbacks:
                try:
                    cb(msg_formatted, record.levelno)
                except Exception:
                    pass

    def add_callback(self, callback: Callable[[str, int], None]) -> None:
        """Enregistre un callback appelé à chaque nouvelle ligne de log émise."""
        with self._lock:
            if callback not in self._callbacks:
                self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[[str, int], None]) -> None:
        with self._lock:
            if callback in self._callbacks:
                self._callbacks.remove(callback)

    def get_records(
        self,
        min_level: int = logging.DEBUG,
        search_query: Optional[str] = None,
        limit: int = 100,
    ) -> List[str]:
        """Retourne les derniers messages formatés correspondant aux filtres."""
        with self._lock:
            records = list(self._buffer)

        matched: List[str] = []
        for r in reversed(records):
            if r.levelno >= min_level:
                formatted = self.format(r)
                if not search_query or search_query.lower() in formatted.lower():
                    matched.append(formatted)
                    if len(matched) >= limit:
                        break

        matched.reverse()
        return matched

    def clear(self) -> None:
        with self._lock:
            self._buffer.clear()


# ── ÉTAT GLOBAL ET GESTION DU LISTENER ASYNCHRONE ──

_log_queue: queue.SimpleQueue[logging.LogRecord] = queue.SimpleQueue()
_global_listener: Optional[QueueListener] = None
_global_ring_buffer: RingBufferHandler = RingBufferHandler(max_records=500)


def get_ring_buffer() -> RingBufferHandler:
    """Retourne l'instance globale du buffer circulaire de logs pour l'UI."""
    return _global_ring_buffer


def setup_logging(
    level: int = logging.INFO,
    log_to_file: bool = True,
    log_to_console: bool = True,
    max_bytes: int = 10 * 1024 * 1024,  # 10 Mo par fichier
    backup_count: int = 5,  # 5 archives (Plafond 50 Mo)
    log_dir: Optional[Path] = None,
) -> Optional[QueueListener]:
    """
    Initialise le pipeline de logging asynchrone global d'AnkiForge.

    - Les producteurs (threads, workers, UI) déposent leurs logs dans une file RAM (zéro latence).
    - Un QueueListener d'arrière-plan distribue les logs aux handlers de sortie.
    """
    global _global_listener, _log_queue, _global_ring_buffer

    # 1. Arrêter un éventuel listener précédent (ex: réinitialisation ou tests)
    shutdown_logging()

    # 2. Préparation du répertoire de log
    target_dir = log_dir if log_dir is not None else get_app_data_dir() / "logs"
    target_dir.mkdir(parents=True, exist_ok=True)
    log_file = target_dir / "ankiforge.log"

    handlers: List[logging.Handler] = []

    # 3. Handler Console (Développement / Terminal)
    if log_to_console:
        console_fmt = AnkiForgeLogFormatter(use_colors=sys.stdout.isatty())
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(console_fmt)
        console_handler.setLevel(level)
        handlers.append(console_handler)

    # 4. Handler Fichier Rotatif (Production / Diagnostic)
    if log_to_file:
        file_fmt = AnkiForgeLogFormatter(use_colors=False)
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(file_fmt)
        file_handler.setLevel(level)
        handlers.append(file_handler)

    # 5. Handler Buffer Circulaire (IHM Live View)
    ring_fmt = AnkiForgeLogFormatter(use_colors=False)
    _global_ring_buffer.setFormatter(ring_fmt)
    _global_ring_buffer.setLevel(level)
    handlers.append(_global_ring_buffer)

    # 6. Configuration du Root Logger avec QueueHandler
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers = []

    # Application des filtres globaux de sécurité et de contexte
    redaction_filter = SecretRedactionFilter()
    context_filter = ContextInjectionFilter()

    root_logger.addFilter(redaction_filter)
    root_logger.addFilter(context_filter)

    # QueueHandler non-bloquant
    _log_queue = queue.SimpleQueue()
    queue_handler = QueueHandler(_log_queue)
    queue_handler.addFilter(redaction_filter)
    queue_handler.addFilter(context_filter)
    root_logger.addHandler(queue_handler)

    # 7. Démarrage du QueueListener en arrière-plan
    _global_listener = QueueListener(_log_queue, *handlers, respect_handler_level=True)
    _global_listener.start()

    logging.info("=== Démarrage d'AnkiForge (Système de Logging Asynchrone Initialisé) ===")
    logging.info("Fichier de log actif : %s", log_file)
    logging.debug("Paramètres de rétention : %d fichiers de max %.1f Mo", backup_count, max_bytes / (1024 * 1024))

    return _global_listener


def shutdown_logging() -> None:
    """Arrête proprement le QueueListener en vidant les logs restants dans la file."""
    global _global_listener
    if _global_listener is not None:
        try:
            _global_listener.stop()
        except Exception:
            pass
        _global_listener = None


# ── GESTIONNAIRE DE CRASH POST-MORTEM (UNHANDLED EXCEPTIONS) ──


def install_crash_handlers(log_dir: Optional[Path] = None) -> None:
    """
    Installe les hooks globaux pour intercepter les exceptions non gérées
    sur le thread principal et les threads secondaires, avec écriture d'un crash.log dédié.
    """
    target_dir = log_dir if log_dir is not None else get_app_data_dir() / "logs"
    target_dir.mkdir(parents=True, exist_ok=True)
    crash_file = target_dir / "crash.log"

    def handle_exception(exc_type: Any, exc_value: Any, exc_traceback: Any) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        import traceback

        tb_lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
        raw_tb = "".join(tb_lines)
        sanitized_tb = redact_secrets(raw_tb)

        logging.critical("FATAL: Exception non gérée interceptée !\n%s", sanitized_tb)

        # Écriture de secours immédiate et synchrone dans crash.log
        try:
            with open(crash_file, "a", encoding="utf-8") as f:
                f.write(f"\n{'=' * 70}\nCRASH REPORT - {platform.platform()} | Python {platform.python_version()}\nProfil actif : {get_active_profile()}\n{'=' * 70}\n{sanitized_tb}\n")
        except Exception as write_err:
            print(f"Échec de l'écriture dans crash.log : {write_err}", file=sys.stderr)

    def handle_thread_exception(args: threading.ExceptHookArgs) -> None:
        handle_exception(args.exc_type, args.exc_value, args.exc_traceback)

    sys.excepthook = handle_exception
    threading.excepthook = handle_thread_exception
