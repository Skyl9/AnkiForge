"""
Service de Notifications Système et Alertes d'Arrière-Plan pour AnkiForge.
Permet d'émettre des notifications de bureau natives (via QSystemTrayIcon)
ou d'activer un signal de repli visuel (QApplication.alert dock/taskbar)
lorsqu'une tâche se termine alors qu'AnkiForge n'est pas au premier plan.
"""

from __future__ import annotations

import enum
import logging
import os
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QApplication

from ankiforge.services.settings_service import SettingsService
from ankiforge.utils.environment import AppEnvironment, get_current_environment

if TYPE_CHECKING:
    from PySide6.QtWidgets import QSystemTrayIcon, QWidget

logger = logging.getLogger(__name__)


class NotificationMode(enum.StrEnum):
    """Modes de notification système lorsque la fenêtre est en arrière-plan."""

    SYSTEM = "system"
    DOCK_ONLY = "dock_only"
    DISABLED = "disabled"


class SystemNotificationService:
    """
    Gestionnaire unifié des notifications système et alertes de focus.
    Gère la détection de la fenêtre en arrière-plan, la préférence utilisateur,
    l'émission native et le repli gracieux sur rebond dock / clignotement barre des tâches.
    """

    SETTINGS_KEY: str = "notifications/system_mode"
    _instance: SystemNotificationService | None = None

    def __init__(self) -> None:
        self._tray_icon: QSystemTrayIcon | None = None
        self.last_notification: tuple[str, str] | None = None
        self.last_alert_widget: QWidget | None = None

    @classmethod
    def get_instance(cls) -> SystemNotificationService:
        """Retourne l'instance singleton du service."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def reset_state_for_testing(self) -> None:
        """Réinitialise l'état interne pour les tests automatisés."""
        self.last_notification = None
        self.last_alert_widget = None

    def is_window_active(self, host_window: QWidget | None) -> bool:
        """
        Détermine si la fenêtre spécifiée est active au premier plan de l'OS.
        Retourne False si host_window est None, masquée, minimisée ou si une
        autre application de l'OS détient actuellement le focus clavier.
        """
        if host_window is None:
            return False

        app = QApplication.instance()
        if not isinstance(app, QApplication):
            return False

        active_win = app.activeWindow()
        if active_win is None:
            return False

        try:
            return bool(host_window.isActiveWindow())
        except Exception as err:
            logger.debug("Erreur lors de la vérification isActiveWindow() : %s", err)
            return False

    def _is_testing_environment(self) -> bool:
        """Détecte si le code s'exécute sous banc d'essai ou en environnement headless."""
        return bool(
            get_current_environment() == AppEnvironment.TESTING
            or os.environ.get("ANKIFORGE_ENV") == "testing"
            or os.environ.get("QT_QPA_PLATFORM") == "offscreen"
            or "PYTEST_CURRENT_TEST" in os.environ
        )

    def _supports_system_tray_messages(self) -> bool:
        """Vérifie si le système d'exploitation et Qt supportent les messages de plateau système."""
        from PySide6.QtWidgets import QSystemTrayIcon

        return bool(QSystemTrayIcon.isSystemTrayAvailable() and QSystemTrayIcon.supportsMessages())

    def _emit_system_tray_message(self, title: str, message: str) -> None:
        """Émet une notification de bureau native via QSystemTrayIcon."""
        self.last_notification = (title, message)
        if self._is_testing_environment():
            return

        from PySide6.QtWidgets import QApplication, QSystemTrayIcon

        app = QApplication.instance()
        if not isinstance(app, QApplication):
            return

        if self._tray_icon is None:
            self._tray_icon = QSystemTrayIcon(parent=app)
            icon = app.windowIcon()
            if not icon.isNull():
                self._tray_icon.setIcon(icon)
            self._tray_icon.show()

        self._tray_icon.showMessage(title, message)

    def _emit_dock_or_taskbar_alert(self, host_window: QWidget | None) -> None:
        """Active un signal visuel non-intrusif (rebond Dock macOS ou clignotement barre des tâches)."""
        self.last_alert_widget = host_window
        if self._is_testing_environment():
            return

        if host_window is not None:
            QApplication.alert(host_window, 0)

    def notify_if_background(
        self,
        host_window: QWidget | None,
        title: str,
        message: str,
    ) -> bool:
        """
        Émet une notification système ou une alerte OS si la fenêtre est en arrière-plan.

        Retourne:
            bool: True si une action de notification ou alerte a été traitée, False sinon.
        """
        if self.is_window_active(host_window):
            return False

        raw_mode = SettingsService.get(self.SETTINGS_KEY, NotificationMode.SYSTEM.value)
        try:
            mode = NotificationMode(str(raw_mode).lower().strip())
        except ValueError:
            mode = NotificationMode.SYSTEM

        if mode == NotificationMode.DISABLED:
            return False

        if mode == NotificationMode.DOCK_ONLY:
            self._emit_dock_or_taskbar_alert(host_window)
            return True

        # Mode SYSTEM : tentative de notification de bureau avec repli automatique sur alerte dock
        system_notif_sent = False
        if self._supports_system_tray_messages():
            try:
                self._emit_system_tray_message(title, message)
                system_notif_sent = True
            except Exception as err:
                logger.warning("Échec de l'émission de la notification système bureau : %s", err)
                system_notif_sent = False

        if not system_notif_sent:
            # Repli gracieux : rebond dock ou clignotement barre des tâches
            self._emit_dock_or_taskbar_alert(host_window)

        return True
