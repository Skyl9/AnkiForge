"""
Tests unitaires et d'intégration pour le module de logging asynchrone (src/ankiforge/utils/logger.py).
Valide la sanitisation des secrets, l'injection de contexte, le formattage,
le buffer circulaire RingBuffer, le pipeline asynchrone QueueHandler et les gestionnaires de crash.
"""

import logging
import sys
import time
from pathlib import Path

import pytest

from ankiforge.utils.logger import (
    AnkiForgeLogFormatter,
    ContextInjectionFilter,
    RingBufferHandler,
    SecretRedactionFilter,
    install_crash_handlers,
    redact_secrets,
    setup_logging,
    shutdown_logging,
)
from ankiforge.utils.paths import set_active_profile

pytestmark = pytest.mark.unit


def test_redact_secrets():
    """Vérifie le masquage automatique des clés API, tokens et mots de passe."""
    # 1. Clé OpenAI
    raw_openai = "Connecting to OpenAI with key sk-abcdef1234567890abcdef1234567890 in header"
    sanitized_openai = redact_secrets(raw_openai)
    assert "sk-abcdef1234567890" not in sanitized_openai
    assert "[REDACTED_OPENAI_KEY]" in sanitized_openai

    # 2. Clé Anthropic
    raw_anthropic = "Anthropic client initialized: sk-ant-api03-abcdef1234567890abcdef12345"
    sanitized_anthropic = redact_secrets(raw_anthropic)
    assert "sk-ant-api03" not in sanitized_anthropic
    assert "[REDACTED_ANTHROPIC_KEY]" in sanitized_anthropic

    # 3. Clé Google / Gemini
    raw_gemini = "Gemini key: AIzaSyD-1234567890abcdef123456789012345"
    sanitized_gemini = redact_secrets(raw_gemini)
    assert "AIzaSyD-12345" not in sanitized_gemini
    assert "[REDACTED_GEMINI_KEY]" in sanitized_gemini

    # 4. Bearer Token
    raw_bearer = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xyz"
    sanitized_bearer = redact_secrets(raw_bearer)
    assert "eyJhbGciOi" not in sanitized_bearer
    assert "Bearer [REDACTED_TOKEN]" in sanitized_bearer

    # 5. Password / Secret param
    raw_pwd = "User login failed with password='MySuperSecretPassword123!'"
    sanitized_pwd = redact_secrets(raw_pwd)
    assert "MySuperSecretPassword123!" not in sanitized_pwd
    assert "[REDACTED_SECRET]" in sanitized_pwd


def test_secret_redaction_filter():
    """Vérifie que SecretRedactionFilter traite les champs msg, args et exc_text."""
    filter_obj = SecretRedactionFilter()

    # Dans record.msg
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="API call failed with key sk-123456789012345678901234567890",
        args=(),
        exc_info=None,
    )
    filter_obj.filter(record)
    assert "sk-12345" not in record.msg
    assert "[REDACTED_OPENAI_KEY]" in record.msg

    # Dans record.args (tuple)
    record_args = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=12,
        msg="Failed with key %s and user %s",
        args=("sk-ant-12345678901234567890123456", "admin"),
        exc_info=None,
    )
    filter_obj.filter(record_args)
    assert "sk-ant" not in record_args.args[0]
    assert "[REDACTED_ANTHROPIC_KEY]" in record_args.args[0]


def test_context_injection_filter():
    """Vérifie l'injection automatique du profil et du nom court de thread."""
    set_active_profile("Medecine_2026")
    filter_obj = ContextInjectionFilter()

    record = logging.LogRecord(
        name="ankiforge.services",
        level=logging.INFO,
        pathname="test.py",
        lineno=20,
        msg="Traitement terminé",
        args=(),
        exc_info=None,
    )
    filter_obj.filter(record)

    assert getattr(record, "profile_name", None) == "Medecine_2026"
    assert hasattr(record, "thread_short_name")
    assert record.thread_short_name in ("Main", "QTP", record.thread_short_name)


def test_ankiforge_log_formatter():
    """Vérifie le rendu du formatteur de log et la colorisation ANSI."""
    formatter_plain = AnkiForgeLogFormatter(use_colors=False)
    formatter_color = AnkiForgeLogFormatter(use_colors=True)

    record = logging.LogRecord(
        name="ankiforge.ui",
        level=logging.WARNING,
        pathname="test_ui.py",
        lineno=42,
        msg="Avertissement d'incohérence",
        args=(),
        exc_info=None,
    )
    record.profile_name = "default"
    record.thread_short_name = "Main"

    plain_text = formatter_plain.format(record)
    assert "[WARNING]" in plain_text or "[WARNING]" in plain_text
    assert "[default:Main]" in plain_text
    assert "[ankiforge.ui:42]" in plain_text
    assert "Avertissement d'incohérence" in plain_text

    color_text = formatter_color.format(record)
    assert "\033[33m" in color_text  # Code ANSI jaune pour WARNING


def test_ring_buffer_handler():
    """Vérifie le buffer circulaire en mémoire et les callbacks de streaming."""
    buffer = RingBufferHandler(max_records=5)
    formatter = AnkiForgeLogFormatter(use_colors=False)
    buffer.setFormatter(formatter)

    events_captured: list[tuple[str, int]] = []

    def on_log(msg: str, level: int):
        events_captured.append((msg, level))

    buffer.add_callback(on_log)

    for i in range(8):
        rec = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="t.py",
            lineno=i,
            msg=f"Message #{i}",
            args=(),
            exc_info=None,
        )
        buffer.emit(rec)

    # 1. Vérification du plafonnement (max 5 records)
    records = buffer.get_records(limit=10)
    assert len(records) == 5
    assert "Message #3" in records[0]
    assert "Message #7" in records[-1]

    # 2. Vérification des callbacks reçus (tous les 8 messages)
    assert len(events_captured) == 8

    # 3. Filtrage par recherche
    filtered = buffer.get_records(search_query="#6")
    assert len(filtered) == 1
    assert "Message #6" in filtered[0]

    # 4. Nettoyage
    buffer.clear()
    assert len(buffer.get_records()) == 0


def test_setup_logging_and_async_queue(tmp_path: Path):
    """Vérifie l'initialisation du pipeline asynchrone QueueHandler + QueueListener."""
    log_dir = tmp_path / "logs"
    listener = setup_logging(
        level=logging.DEBUG,
        log_to_file=True,
        log_to_console=False,
        max_bytes=1024 * 1024,
        backup_count=2,
        log_dir=log_dir,
    )
    assert listener is not None

    test_logger = logging.getLogger("ankiforge.test_async")
    test_logger.info("Message asynchrone avec clé sk-123456789012345678901234567890")

    # Attendre brièvement le passage dans la queue
    time.sleep(0.1)
    shutdown_logging()

    log_file = log_dir / "ankiforge.log"
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "Message asynchrone" in content
    assert "sk-12345" not in content
    assert "[REDACTED_OPENAI_KEY]" in content


def test_install_crash_handlers(tmp_path: Path):
    """Vérifie la génération du crash.log lors d'une exception fatale non rattrapée."""
    log_dir = tmp_path / "crash_logs"
    install_crash_handlers(log_dir=log_dir)

    try:
        raise ValueError("Erreur critique simulée avec token Bearer abcdef1234567890abcdef")
    except ValueError:
        exc_type, exc_val, exc_tb = sys.exc_info()
        sys.excepthook(exc_type, exc_val, exc_tb)

    crash_file = log_dir / "crash.log"
    assert crash_file.exists()
    content = crash_file.read_text(encoding="utf-8")
    assert "CRASH REPORT" in content
    assert "Erreur critique simulée" in content
    assert "abcdef12345" not in content
    assert "[REDACTED_TOKEN]" in content


def test_log_and_notify_error():
    """Vérifie le fonctionnement du gestionnaire unifié log_and_notify_error."""
    from ankiforge.utils.logger import log_and_notify_error

    err = RuntimeError("Échec de connexion LLM avec clé sk-123456789012345678901234567890")
    # Ne doit pas planter même sans interface graphique
    log_and_notify_error(err, context="Pipeline Execution")
