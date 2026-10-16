"""Service de diagnostic et de gestion des rapports de crash (Crash Reporter).

Parse les fichiers crash.log, détecte les incidents non encore proposés à l'utilisateur,
applique la sanitisation stricte des secrets (SecretRedactionFilter / redact_secrets),
génère les rapports Markdown et construit les URL de transmission GitHub Issues.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ankiforge.services.feedback_service import FeedbackService, SystemDiagnosticInfo
from ankiforge.utils.environment import get_app_qsettings
from ankiforge.utils.logger import redact_secrets
from ankiforge.utils.paths import get_app_data_dir
from ankiforge.version import get_version_info

logger = logging.getLogger(__name__)

SETTINGS_KEY_PROMPT_ON_CRASH = "feedback/prompt_on_crash"
SETTINGS_KEY_LAST_ACK_CRASH_HASH = "feedback/last_acknowledged_crash_hash"

# Motif de détection d'en-tête de crash report :
# Ex: CRASH REPORT [2026-10-10 14:30:00 UTC] - Darwin-24.1.0-arm64 | Python 3.12.9
# ou l'ancien format : CRASH REPORT - Darwin-24.1.0-arm64 | Python 3.12.9
_RE_CRASH_HEADER = re.compile(
    r"CRASH REPORT(?:\s+\[(?P<timestamp>[^\]]+)\])?\s+-\s+(?P<platform>[^|]+)\|\s+Python\s+(?P<python>[^\n\r]+)",
    re.IGNORECASE,
)
_RE_PROFILE_LINE = re.compile(r"Profil actif\s*:\s*(?P<profile>[^\n\r]+)", re.IGNORECASE)
_RE_EXCEPTION_LINE = re.compile(r"^(?:[a-zA-Z_][a-zA-Z0-9_\.]*\.)?([A-Z][a-zA-Z0-9_]*(?:Error|Exception|Warning|Interrupt|Fault|Exit))\s*:\s*(.*)$", re.MULTILINE)


@dataclass
class CrashReport:
    """Informations structurées extraites d'une entrée de crash.log."""

    timestamp: str = ""
    os_platform: str = ""
    python_version: str = ""
    active_profile: str = "default"
    traceback: str = ""
    raw_block: str = ""
    fingerprint: str = ""
    log_file: Path | None = None


class CrashReporterService:
    """Service centralisé de gestion et d'export des rapports de crash."""

    @staticmethod
    def parse_crash_log_content(content: str, log_file: Path | None = None) -> list[CrashReport]:
        """Parse l'intégralité d'un contenu de crash.log et retourne la liste des CrashReport ordonnés.

        Gère les séparateurs '====' et extrait les métadonnées de chaque incident.
        """
        if not content or not content.strip():
            return []

        # Les blocs sont délimités par des lignes de séparation '==='
        raw_parts = re.split(r"(?:\r?\n)?={40,}(?:\r?\n)?", content)
        reports: list[CrashReport] = []

        i = 0
        while i < len(raw_parts):
            part = raw_parts[i].strip()
            if not part:
                i += 1
                continue

            header_match = _RE_CRASH_HEADER.search(part)
            if header_match:
                ts = header_match.group("timestamp") or ""
                os_plat = header_match.group("platform").strip()
                py_ver = header_match.group("python").strip()

                prof_match = _RE_PROFILE_LINE.search(part)
                prof = prof_match.group("profile").strip() if prof_match else "default"

                # Le traceback se trouve soit dans ce segment après le profil, soit dans le segment suivant
                tb = ""
                raw_block = part
                if i + 1 < len(raw_parts):
                    next_part = raw_parts[i + 1].strip()
                    # Si le segment suivant ressemble à un traceback ou n'est pas un nouvel en-tête
                    if next_part and not _RE_CRASH_HEADER.search(next_part):
                        tb = next_part
                        raw_block = f"{part}\n======================================================================\n{next_part}"
                        i += 1  # Avancer pour consommer le traceback

                if not tb:
                    lines = part.splitlines()
                    tb_lines: list[str] = []
                    found_prof = False
                    for line in lines:
                        if "Profil actif" in line:
                            found_prof = True
                            continue
                        if found_prof and line.strip():
                            tb_lines.append(line)
                    tb = "\n".join(tb_lines).strip()

                sanitized_tb = redact_secrets(tb)
                fingerprint = hashlib.sha256(raw_block.strip().encode("utf-8")).hexdigest()

                reports.append(
                    CrashReport(
                        timestamp=ts,
                        os_platform=os_plat,
                        python_version=py_ver,
                        active_profile=prof,
                        traceback=sanitized_tb,
                        raw_block=raw_block,
                        fingerprint=fingerprint,
                        log_file=log_file,
                    )
                )
            i += 1

        return reports

    @classmethod
    def get_crash_log_path(cls, log_dir: Path | None = None) -> Path:
        """Retourne le chemin canonique vers le fichier crash.log."""
        target_dir = log_dir if log_dir is not None else get_app_data_dir() / "logs"
        return target_dir / "crash.log"

    @classmethod
    def get_latest_crash(cls, log_dir: Path | None = None) -> CrashReport | None:
        """Lit crash.log et retourne le dernier incident enregistré, ou None."""
        crash_file = cls.get_crash_log_path(log_dir)
        if not crash_file.exists():
            return None

        try:
            content = crash_file.read_text(encoding="utf-8", errors="replace")
            reports = cls.parse_crash_log_content(content, log_file=crash_file)
            return reports[-1] if reports else None
        except OSError as err:
            logger.warning("Impossible de lire le fichier crash.log (%s) : %s", crash_file, err)
            return None

    @classmethod
    def is_prompt_enabled(cls) -> bool:
        """Indique si l'utilisateur souhaite être sollicité pour transmettre ses crash reports."""
        settings = get_app_qsettings()
        return bool(settings.value(SETTINGS_KEY_PROMPT_ON_CRASH, True, type=bool))

    @classmethod
    def set_prompt_enabled(cls, enabled: bool) -> None:
        """Enregistre la préférence d'affichage de l'invite de crash report."""
        settings = get_app_qsettings()
        settings.setValue(SETTINGS_KEY_PROMPT_ON_CRASH, bool(enabled))

    @classmethod
    def has_pending_crash(cls, log_dir: Path | None = None) -> bool:
        """Détermine si un crash récent n'a pas encore été proposé/acquitté par l'utilisateur.

        Respecte la préférence utilisateur (retourne False si désactivé).
        """
        if not cls.is_prompt_enabled():
            return False

        latest = cls.get_latest_crash(log_dir)
        if latest is None:
            return False

        settings = get_app_qsettings()
        last_ack_hash = str(settings.value(SETTINGS_KEY_LAST_ACK_CRASH_HASH, ""))
        return latest.fingerprint != last_ack_hash

    @classmethod
    def acknowledge_crash(cls, crash: CrashReport | str) -> None:
        """Marque un crash comme acquitté/traité pour ne plus le reproposer au prochain lancement."""
        fp = crash.fingerprint if isinstance(crash, CrashReport) else str(crash)
        settings = get_app_qsettings()
        settings.setValue(SETTINGS_KEY_LAST_ACK_CRASH_HASH, fp)

    @classmethod
    def build_markdown_report(
        cls,
        crash: CrashReport,
        diagnostic_info: SystemDiagnosticInfo | None = None,
    ) -> str:
        """Génère un rapport Markdown complet et prêt à l'envoi.

        Applique systématiquement la sanitisation des secrets sur l'ensemble du payload.
        """
        now_utc = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        v_info = get_version_info()

        clean_tb = redact_secrets(crash.traceback.strip() or "_Aucune trace disponible_")
        clean_platform = redact_secrets(crash.os_platform or "Inconnu")
        clean_py = redact_secrets(crash.python_version or "Inconnu")
        clean_profile = redact_secrets(crash.active_profile or "default")
        timestamp_str = crash.timestamp or now_utc

        md_parts = [
            "# 💥 [Crash Report] Arrêt Inattendu d'AnkiForge",
            "",
            f"*Rapport d'incident généré le {now_utc} depuis AnkiForge.*",
            "",
            "### 🖥️ Environnement & Versions",
            f"- **AnkiForge :** `{v_info.full_display_version}` ({v_info.build_channel}) commit `{v_info.commit_hash[:8] if v_info.commit_hash else 'local'}`",
            f"- **OS / Plateforme :** `{clean_platform}`",
            f"- **Python :** `{clean_py}`",
            f"- **Profil actif :** `{clean_profile}`",
            f"- **Date de l'incident :** `{timestamp_str}`",
            "",
            "### ⚠️ Traceback d'Erreur Intercepté",
            "```python",
            clean_tb,
            "```",
            "",
        ]

        if diagnostic_info is not None:
            diag_md = diagnostic_info.to_markdown(include_logs=True)
            md_parts.extend(
                [
                    "---",
                    "",
                    diag_md,
                ]
            )

        full_report = "\n".join(md_parts)
        # Défense en profondeur : re-sanitisation complète du rapport généré
        return redact_secrets(full_report)

    @classmethod
    def build_github_issue_url(
        cls,
        crash: CrashReport,
        diagnostic_info: SystemDiagnosticInfo | None = None,
    ) -> str:
        """Construit une URL GitHub Issues pré-remplie avec le titre de l'exception et le rapport d'incident complet."""
        # Extraire le message de la dernière exception levée pour un titre pertinent
        title = "Arrêt inattendu de l'application"
        matches = list(_RE_EXCEPTION_LINE.finditer(crash.traceback))
        if matches:
            last_match = matches[-1]
            exc_type = last_match.group(1)
            exc_msg = last_match.group(2).strip()
            # Limiter la longueur du message d'erreur dans le titre
            short_msg = exc_msg[:60] + "..." if len(exc_msg) > 60 else exc_msg
            title = f"{exc_type}: {short_msg}" if short_msg else exc_type

        full_title = f"[Crash] {title}"
        body = cls.build_markdown_report(crash, diagnostic_info)

        return FeedbackService.build_github_issue_url(title=full_title, body=body, label="crash")

    @classmethod
    def export_crash_report(cls, target_path: Path, content: str) -> None:
        """Exporte le rapport dans un fichier Markdown local de manière sécurisée."""
        FeedbackService.export_report_to_file(target_path, redact_secrets(content))
