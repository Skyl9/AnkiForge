"""Tests unitaires pour SystemNotificationService.

Vérifie la détection de fenêtre en arrière-plan, l'émission des notifications de bureau,
le repli sur l'alerte dock/taskbar et l'inhibition sécurisée en environnement de test.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QApplication, QWidget

from ankiforge.services.settings_service import SettingsService
from ankiforge.services.system.notification_service import (
    NotificationMode,
    SystemNotificationService,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def dummy_window(qtbot) -> QWidget:
    w = QWidget()
    qtbot.addWidget(w)
    return w


@pytest.fixture(autouse=True)
def reset_service_and_settings():
    # Réinitialise le singleton et les réglages
    service = SystemNotificationService.get_instance()
    service.reset_state_for_testing()
    SettingsService.set("notifications/system_mode", "system", category="general")
    yield
    service.reset_state_for_testing()


def test_is_window_active_true(dummy_window: QWidget):
    service = SystemNotificationService.get_instance()
    with patch.object(dummy_window, "isActiveWindow", return_value=True), patch.object(QApplication, "activeWindow", return_value=dummy_window):
        assert service.is_window_active(dummy_window) is True


def test_is_window_active_false_when_none():
    service = SystemNotificationService.get_instance()
    assert service.is_window_active(None) is False


def test_is_window_active_false_when_inactive(dummy_window: QWidget):
    service = SystemNotificationService.get_instance()
    with patch.object(dummy_window, "isActiveWindow", return_value=False), patch.object(QApplication, "activeWindow", return_value=dummy_window):
        assert service.is_window_active(dummy_window) is False


def test_is_window_active_false_when_app_inactive(dummy_window: QWidget):
    service = SystemNotificationService.get_instance()
    with patch.object(dummy_window, "isActiveWindow", return_value=True), patch.object(QApplication, "activeWindow", return_value=None):
        assert service.is_window_active(dummy_window) is False


def test_notify_if_background_skips_when_active(dummy_window: QWidget):
    service = SystemNotificationService.get_instance()
    with patch.object(service, "is_window_active", return_value=True):
        handled = service.notify_if_background(dummy_window, "Titre", "Message")
        assert handled is False
        assert service.last_notification is None
        assert service.last_alert_widget is None


def test_notify_if_background_disabled_mode(dummy_window: QWidget):
    service = SystemNotificationService.get_instance()
    SettingsService.set("notifications/system_mode", NotificationMode.DISABLED.value, category="general")
    with patch.object(service, "is_window_active", return_value=False):
        handled = service.notify_if_background(dummy_window, "Titre", "Message")
        assert handled is False
        assert service.last_notification is None
        assert service.last_alert_widget is None


def test_notify_if_background_dock_only_mode(dummy_window: QWidget):
    service = SystemNotificationService.get_instance()
    SettingsService.set("notifications/system_mode", NotificationMode.DOCK_ONLY.value, category="general")
    with patch.object(service, "is_window_active", return_value=False):
        handled = service.notify_if_background(dummy_window, "Titre", "Message")
        assert handled is True
        assert service.last_notification is None
        assert service.last_alert_widget is dummy_window


def test_notify_if_background_system_mode_success(dummy_window: QWidget):
    service = SystemNotificationService.get_instance()
    SettingsService.set("notifications/system_mode", NotificationMode.SYSTEM.value, category="general")
    with patch.object(service, "is_window_active", return_value=False), patch.object(service, "_supports_system_tray_messages", return_value=True):
        handled = service.notify_if_background(dummy_window, "Import terminé", "4 documents ingérés")
        assert handled is True
        assert service.last_notification == ("Import terminé", "4 documents ingérés")
        # Pas d'alerte dock requise si la notification système a réussi
        assert service.last_alert_widget is None


def test_notify_if_background_system_mode_fallback_when_unsupported(dummy_window: QWidget):
    service = SystemNotificationService.get_instance()
    SettingsService.set("notifications/system_mode", NotificationMode.SYSTEM.value, category="general")
    with patch.object(service, "is_window_active", return_value=False), patch.object(service, "_supports_system_tray_messages", return_value=False):
        handled = service.notify_if_background(dummy_window, "Import terminé", "4 documents ingérés")
        assert handled is True
        # Repli gracieux sur l'alerte dock/taskbar
        assert service.last_alert_widget is dummy_window


def test_notify_if_background_system_mode_fallback_on_exception(dummy_window: QWidget):
    service = SystemNotificationService.get_instance()
    SettingsService.set("notifications/system_mode", NotificationMode.SYSTEM.value, category="general")
    with (
        patch.object(service, "is_window_active", return_value=False),
        patch.object(service, "_supports_system_tray_messages", return_value=True),
        patch.object(service, "_emit_system_tray_message", side_effect=RuntimeError("OS Notification Error")),
    ):
        handled = service.notify_if_background(dummy_window, "Import terminé", "4 documents ingérés")
        assert handled is True
        # Doit quand même déclencher le repli
        assert service.last_alert_widget is dummy_window
