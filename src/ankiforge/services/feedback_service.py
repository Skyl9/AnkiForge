"""
Service de feedback et de diagnostic pour AnkiForge.
Gère la collecte des informations système anonymisées, la sanitisation des données sensibles,
le formatage Markdown pour GitHub Issues et l'exportation de rapports.
"""

from __future__ import annotations

import contextlib
import dataclasses
import logging
import platform
import sqlite3
import urllib.parse
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ankiforge.utils.logger import get_ring_buffer, redact_secrets
from ankiforge.utils.paths import get_active_profile, get_app_data_dir
from ankiforge.version import get_version_info

logger = logging.getLogger(__name__)

GITHUB_REPO_URL = "https://github.com/Skyl9/AnkiForge"
GITHUB_NEW_ISSUE_URL = f"{GITHUB_REPO_URL}/issues/new"


@dataclass
class SystemDiagnosticInfo:
    """Informations de diagnostic système anonymisées et sans données sensibles."""

    ankiforge_version: str = ""
    build_channel: str = ""
    commit_hash: str = ""
    os_platform: str = ""
    python_version: str = ""
    pyside_version: str = ""
    qt_version: str = ""
    active_profile: str = "default"
    active_theme: str = ""
    active_layout: str = ""
    screen_resolution: str = ""
    sqlite_version: str = ""
    ai_provider: str = ""
    ai_model: str = ""
    recent_logs: list[str] = field(default_factory=list)
    crash_excerpt: str = ""

    def to_markdown(self, include_logs: bool = True) -> str:
        """Génère un bloc Markdown prêt à intégrer dans une issue GitHub."""
        md = [
            "### 🖥️ Informations Système & Environnement",
            "",
            "| Élément | Valeur |",
            "| :--- | :--- |",
            f"| **AnkiForge** | `{self.ankiforge_version}` ({self.build_channel}) commit `{self.commit_hash}` |",
            f"| **OS / Plateforme** | `{self.os_platform}` |",
            f"| **Python** | `{self.python_version}` |",
            f"| **Qt / PySide6** | PySide6 `{self.pyside_version}` (Qt `{self.qt_version}`) |",
            f"| **Profil actif** | `{self.active_profile}` |",
            f"| **Thème & Layout** | `{self.active_theme}` / `{self.active_layout}` |",
            f"| **Écran** | `{self.screen_resolution}` |",
            f"| **SQLite** | `{self.sqlite_version}` |",
            f"| **IA Configurée** | `{self.ai_provider}` (modèle : `{self.ai_model}`) |",
            "",
        ]

        if include_logs and self.crash_excerpt.strip():
            md.extend(
                [
                    "<details>",
                    "<summary>💥 Dernier Crash Intercepté (crash.log)</summary>",
                    "",
                    "```text",
                    redact_secrets(self.crash_excerpt.strip()),
                    "```",
                    "</details>",
                    "",
                ]
            )

        if include_logs and self.recent_logs:
            logs_content = redact_secrets("\n".join(self.recent_logs))
            md.extend(
                [
                    "<details>",
                    "<summary>📋 Logs Récents de l'Application (anonymisés)</summary>",
                    "",
                    "```text",
                    logs_content,
                    "```",
                    "</details>",
                    "",
                ]
            )

        return "\n".join(md)

    def to_dict(self) -> dict[str, Any]:
        """Convertit l'objet en dictionnaire sérialisable."""
        return dataclasses.asdict(self)


@dataclass
class BugReportData:
    """Données pour le signalement d'un bug."""

    title: str = ""
    severity: str = "Normal"  # Cosmétique, Normal, Élevé / Bloquant, Crash complet
    steps: str = ""
    observed: str = ""
    expected: str = ""
    include_diagnostics: bool = True
    diagnostic_info: SystemDiagnosticInfo | None = None
    custom_traceback: str = ""


@dataclass
class FeatureIdeaData:
    """Données pour la suggestion d'une idée ou d'une nouvelle fonctionnalité."""

    title: str = ""
    category: str = "Autre"  # Studio de Création, RAG & Documents, Édition & Cartes, Modèles de Cartes, Agents & Pipelines IA, Interface & Ergonomie, Autre
    problem: str = ""
    solution: str = ""
    priority: str = "Très utile"  # Optionnel (Nice-to-have), Très utile, Essentiel


class FeedbackService:
    """Service centralisé pour collecter les diagnostics et préparer les retours utilisateur."""

    @staticmethod
    def collect_diagnostics(log_limit: int = 50) -> SystemDiagnosticInfo:
        """
        Collecte les informations système et d'environnement de manière non bloquante et sécurisée.
        Toutes les données sensibles (clés d'API, tokens) sont masquées via redact_secrets.
        """
        v_info = get_version_info()
        diag = SystemDiagnosticInfo()

        diag.ankiforge_version = v_info.full_display_version
        diag.build_channel = v_info.build_channel
        diag.commit_hash = v_info.commit_hash[:8] if v_info.commit_hash else "local"
        diag.os_platform = f"{platform.platform()} ({platform.machine()})"
        diag.python_version = platform.python_version()

        # Qt & PySide6
        with contextlib.suppress(Exception):
            import PySide6
            from PySide6.QtCore import qVersion

            diag.pyside_version = PySide6.__version__
            diag.qt_version = qVersion()

        # Profil actif
        with contextlib.suppress(Exception):
            diag.active_profile = get_active_profile() or "default"

        # Thème & Layout
        with contextlib.suppress(Exception):
            from ankiforge.ui.layouts.layout_manager import LayoutManager
            from ankiforge.ui.style_engine import get_style_engine

            engine = get_style_engine()
            diag.active_theme = engine.get_saved_theme_id(diag.active_profile)
            diag.active_layout = LayoutManager.get_saved_layout_id(diag.active_profile)

        # Résolution d'écran
        with contextlib.suppress(Exception):
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
            if app:
                screen = QApplication.primaryScreen()
                if screen:
                    size = screen.size()
                    diag.screen_resolution = f"{size.width()}x{size.height()} @ {screen.devicePixelRatio():.1f}x"

        # SQLite
        diag.sqlite_version = sqlite3.sqlite_version

        # Moteur IA configuré (sans clés !)
        with contextlib.suppress(Exception):
            import os

            diag.ai_provider = os.getenv("AI_PROVIDER", "non configuré")
            diag.ai_model = os.getenv("AI_MODEL", "par défaut")

        # Logs en mémoire (déjà masqués via RingBufferHandler, re-sanitisés par précaution)
        with contextlib.suppress(Exception):
            ring = get_ring_buffer()
            raw_logs = ring.get_records(limit=log_limit)
            diag.recent_logs = [redact_secrets(line) for line in raw_logs]

        # Crash log récent si existant
        with contextlib.suppress(Exception):
            crash_path = get_app_data_dir() / "logs" / "crash.log"
            if crash_path.exists():
                with open(crash_path, encoding="utf-8", errors="replace") as f:
                    crash_lines = f.readlines()
                    if crash_lines:
                        # Extraire les 35 dernières lignes
                        diag.crash_excerpt = redact_secrets("".join(crash_lines[-35:]))

        return diag

    @classmethod
    def build_bug_report_markdown(cls, data: BugReportData) -> str:
        """Formate le rapport de bug complet au format Markdown pour GitHub ou export."""
        now_utc = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

        clean_title = redact_secrets(data.title.strip() or "Anomalie détectée")
        clean_steps = redact_secrets(data.steps.strip() or "_Aucune étape spécifiée_")
        clean_observed = redact_secrets(data.observed.strip() or "_Non précisé_")
        clean_expected = redact_secrets(data.expected.strip() or "_Non précisé_")

        md_parts = [
            f"# 🐛 [Bug] {clean_title}",
            "",
            f"*Rapport généré le {now_utc} depuis AnkiForge.*",
            "",
            f"**Sévérité :** `{data.severity}`",
            "",
            "### 📌 Description & Étapes de reproduction",
            clean_steps,
            "",
            "### 🔍 Comportement Observé",
            clean_observed,
            "",
            "### ✅ Comportement Attendu",
            clean_expected,
            "",
        ]

        if data.custom_traceback.strip():
            md_parts.extend(
                [
                    "### ⚠️ Traceback d'Erreur Intercepté",
                    "```python",
                    redact_secrets(data.custom_traceback.strip()),
                    "```",
                    "",
                ]
            )

        if data.include_diagnostics and data.diagnostic_info:
            md_parts.append(data.diagnostic_info.to_markdown(include_logs=True))

        return "\n".join(md_parts)

    @classmethod
    def build_feature_request_markdown(cls, data: FeatureIdeaData) -> str:
        """Formate la suggestion de fonctionnalité au format Markdown."""
        now_utc = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

        md_parts = [
            f"# 💡 [Idée] {data.title or 'Nouvelle fonctionnalité'}",
            "",
            f"*Proposition soumise le {now_utc} depuis AnkiForge.*",
            "",
            f"**Catégorie :** `{data.category}` | **Priorité souhaitée :** `{data.priority}`",
            "",
            "### 🎯 Problème résolu ou besoin utilisateur",
            data.problem.strip() or "_Non précisé_",
            "",
            "### 💡 Solution proposée / Description de l'idée",
            data.solution.strip() or "_Non précisé_",
            "",
            "---",
            f"*Proposé via le menu Feedback d'AnkiForge v{get_version_info().short_display_version}*",
        ]

        return "\n".join(md_parts)

    @classmethod
    def build_github_issue_url(cls, title: str, body: str, label: str = "bug") -> str:
        """
        Construit l'URL complète pré-remplie pour créer une issue GitHub.
        Si le corps dépasse 3 500 caractères, tronque poliment les logs pour respecter
        la limite d'URL des navigateurs tout en prévenant l'utilisateur.
        """
        # Sécurité sur la longueur d'URL (les navigateurs limitent souvent à 4000-8000 caractères)
        max_body_len = 3500
        safe_body = body
        if len(safe_body) > max_body_len:
            safe_body = safe_body[:max_body_len] + "\n\n*(Logs tronqués pour respecter la limite d'URL. Le rapport complet peut être copié via le bouton 'Copier le rapport' d'AnkiForge)*"

        params = {
            "title": title,
            "body": safe_body,
            "labels": label,
        }
        encoded_query = urllib.parse.urlencode(params)
        return f"{GITHUB_NEW_ISSUE_URL}?{encoded_query}"

    @classmethod
    def export_report_to_file(cls, target_path: Path, content: str) -> None:
        """Sauvegarde le rapport dans un fichier local (.md ou .json)."""
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info("Rapport de diagnostic exporté avec succès dans : %s", target_path)
