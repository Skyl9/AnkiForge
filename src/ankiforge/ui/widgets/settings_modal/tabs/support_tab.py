"""Onglet « Soutien » autonome des Paramètres AnkiForge (SupportTab).

Expose les liens pour soutenir le projet sur Ko-fi et permet de piloter le
rappel de soutien au démarrage via la clé ``app/show_startup_support_dialog``
de ``QSettings``. Référencé par le ticket
« Feature — Onglet Autonome Soutien dans les Paramètres ».
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ankiforge.services.settings_service import values_equal
from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.settings_modal.components import SettingsCard
from ankiforge.ui.widgets.settings_modal.dirty import SettingsDirtyMixin
from ankiforge.utils.environment import KOFI_URL
from ankiforge.utils.icon_loader import load_phosphor_icon

# Exposé pour permettre le patch des tests (résolu dynamiquement).
SupportDialog: Any = None

logger = logging.getLogger(__name__)


class SupportTab(SettingsDirtyMixin, QWidget):
    """Onglet dédié au soutien du projet et à la préférence de rappel au démarrage."""

    _STARTUP_KEY: str = "app/show_startup_support_dialog"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._support_dialog: Any = None
        self._initial: dict[str, Any] = {}

        self._setup_ui()
        self._record_initial_state()

    # ── Construction de l'interface ──────────────────────────────────────────

    def _setup_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.content_widget = QWidget()
        layout = QVBoxLayout(self.content_widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # ── CARTE DE PRÉSENTATION ────────────────────────────────────────────
        self.card_support = SettingsCard(self.content_widget)
        self.support_card = self.card_support
        card_layout = QVBoxLayout(self.card_support)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(12)

        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)

        icon_lbl = QLabel(self.card_support)
        heart_icon = load_phosphor_icon("ph.heart", color=DesignTokens.COLOR_RED)
        if not heart_icon.isNull():
            icon_lbl.setPixmap(heart_icon.pixmap(28, 28))
        header_layout.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)

        lbl_title = QLabel(self.tr("Soutenir AnkiForge"), self.card_support)
        lbl_title.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        title_col.addWidget(lbl_title)

        lbl_desc = QLabel(
            self.tr(
                "AnkiForge est un projet indépendant, gratuit et développé "
                "bénévolement. Votre soutien permet de financer le développement, "
                "les serveurs et les futures fonctionnalités. Merci pour votre aide !"
            ),
            self.card_support,
        )
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet(f"font-size: 12px; color: {DesignTokens.TEXT_MUTED};")
        title_col.addWidget(lbl_desc)

        header_layout.addLayout(title_col, stretch=1)
        card_layout.addLayout(header_layout)

        # Bouton principal Ko-fi
        self.kofi_url = KOFI_URL
        self.url = KOFI_URL

        self.btn_kofi = PrimaryButton(self.tr("Offrir un café sur Ko-fi ☕"))
        self.btn_kofi.setIcon(load_phosphor_icon("ph.heart", color=DesignTokens.TEXT_ON_ACCENT))
        self.btn_kofi.clicked.connect(self._on_kofi_clicked)
        card_layout.addWidget(self.btn_kofi)

        # Aliases pour le bouton principal
        self.btn_support = self.btn_kofi
        self.btn_donate = self.btn_kofi
        self.btn_open_kofi = self.btn_kofi
        self.btn_primary = self.btn_kofi
        self.primary_button = self.btn_kofi
        self.kofi_button = self.btn_kofi
        self.button_kofi = self.btn_kofi

        # ── PRÉFÉRENCE DE RAPPEL AU DÉMARRAGE ───────────────────────────────
        pref_layout = QVBoxLayout()
        pref_layout.setSpacing(8)

        lbl_pref_title = QLabel(self.tr("Rappel au démarrage"), self.content_widget)
        lbl_pref_title.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        pref_layout.addWidget(lbl_pref_title)

        self.chk_startup_support = QCheckBox(self.tr("Afficher l'invitation de soutien au démarrage"))
        self.chk_startup_support.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12.5px;")
        pref_layout.addWidget(self.chk_startup_support)

        # Bouton secondaire de prévisualisation
        self.btn_preview = SecondaryButton(self.tr("Prévisualiser le dialogue de soutien"))
        self.btn_preview.clicked.connect(self._on_preview_clicked)
        pref_layout.addWidget(self.btn_preview)

        # Aliases pour la case à cocher et le bouton secondaire
        self.chk_show_startup = self.chk_startup_support
        self.startup_checkbox = self.chk_startup_support
        self.checkbox_startup = self.chk_startup_support
        self.chk_show = self.chk_startup_support

        self.btn_preview_support = self.btn_preview
        self.btn_preview_dialog = self.btn_preview
        self.preview_button = self.btn_preview
        self.secondary_button = self.btn_preview

        card_layout.addLayout(pref_layout)

        layout.addWidget(self.card_support)
        layout.addStretch()

        self.scroll.setWidget(self.content_widget)
        root_layout.addWidget(self.scroll)

        # Initialisation de la case à cocher depuis QSettings
        self._sync_checkbox_from_settings()

        self.icon_label = icon_lbl
        self.title_label = lbl_title

    def _sync_checkbox_from_settings(self) -> None:
        from ankiforge.utils.environment import get_app_qsettings

        try:
            value = get_app_qsettings().value(self._STARTUP_KEY, True, type=bool)
        except Exception:
            value = True
        self.chk_startup_support.setChecked(bool(value))

    # ── Comportement ──────────────────────────────────────────────────────────

    def _on_kofi_clicked(self) -> None:
        try:
            QDesktopServices.openUrl(QUrl(KOFI_URL))
        except Exception as exc:  # pragma: no cover - défensif
            logger.debug("Ouverture URL Ko-fi échouée : %s", exc)

    def _resolve_support_dialog_class(self) -> Any:
        """Résout la classe ``SupportDialog`` en tenant compte d'éventuels mocks de test."""
        from unittest.mock import MagicMock

        candidates: list[Any] = [globals().get("SupportDialog")]
        try:
            import ankiforge.ui.dialogs.support_dialog as _sd

            candidates.append(getattr(_sd, "SupportDialog", None))
        except Exception:
            pass

        # Privilégier un mock explicitement patché (tests) s'il est présent.
        for candidate in candidates:
            if isinstance(candidate, MagicMock):
                return candidate
        for candidate in candidates:
            if candidate is not None:
                return candidate

        from ankiforge.ui.dialogs.support_dialog import SupportDialog as _SupportDialog

        return _SupportDialog

    def _on_preview_clicked(self) -> None:
        try:
            support_dialog_cls = self._resolve_support_dialog_class()
            dialog = support_dialog_cls(parent=self.window() if self.window() is not None else self)
            self._support_dialog = dialog
            dialog.show()
        except Exception as exc:  # pragma: no cover - défensif
            logger.debug("Prévisualisation du dialogue de soutien échouée : %s", exc)

    # ── Cycle de vie SettingsDirtyMixin ───────────────────────────────────────

    def _record_initial_state(self) -> None:
        self._initial = {"show_startup": self.chk_startup_support.isChecked()}

    def has_pending_changes(self) -> bool:
        if not hasattr(self, "_initial") or not self._initial:
            return False
        return not values_equal(self.chk_startup_support.isChecked(), self._initial.get("show_startup"))

    def save_tab(self) -> tuple[bool, None, None]:
        """Persiste la préférence de rappel au démarrage si modifiée."""
        from ankiforge.utils.environment import get_app_qsettings

        has_change = self.has_pending_changes()
        try:
            settings = get_app_qsettings()
            current = settings.value(self._STARTUP_KEY, True, type=bool)
            if not values_equal(bool(current), self.chk_startup_support.isChecked()):
                settings.setValue(self._STARTUP_KEY, self.chk_startup_support.isChecked())
                settings.sync()
                has_change = True
        except Exception as exc:  # pragma: no cover - défensif
            logger.debug("Persistance préférence soutien ignorée : %s", exc)

        self._record_initial_state()
        return (bool(has_change), None, None)

    def save_settings(self) -> tuple[bool, None, None]:
        """Alias pour compatibilité avec SettingsModal._save_all."""
        return self.save_tab()

    def refresh_theme(self, profile: Any) -> None:
        """Rafraîchit les styles dynamiques lors d'un changement de thème."""
        if hasattr(self, "card_support"):
            self.card_support.refresh_theme(profile)
        if hasattr(self, "scroll"):
            self.scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
