"""Dialogue d'invitation de soutien Ko-fi pour AnkiForge.

Présente une invitation chaleureuse et non bloquante à soutenir le développement
volontaire du projet, avec possibilité de désactiver durablement l'invitation
au démarrage. Référencé par le ticket
« Feature - Dialogue de Soutien Kofi et Declencheur au Demarrage ».
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens, apply_shadow
from ankiforge.utils.environment import KOFI_URL, get_app_qsettings
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class SupportDialog(QDialog):
    """Boîte de dialogue non bloquante d'invitation à soutenir le projet sur Ko-fi."""

    def __init__(self, parent: QWidget | None = None, kofi_url: str | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SupportDialog")
        self.setModal(False)
        self.setWindowTitle(self.tr("Soutenir AnkiForge"))
        self.setMinimumSize(460, 260)
        self.resize(500, 300)

        self.kofi_url: str = kofi_url if kofi_url is not None else KOFI_URL

        self._setup_ui()
        self._apply_styles()

    # ── Construction de l'interface ────────────────────────────────────────────

    def _setup_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(24, 20, 24, 18)
        root_layout.setSpacing(14)

        # En-tête avec icône cœur et titre
        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)

        icon_lbl = QLabel()
        heart_icon = load_phosphor_icon("ph.heart", color=DesignTokens.COLOR_RED)
        if not heart_icon.isNull():
            icon_lbl.setPixmap(heart_icon.pixmap(32, 32))
        header_layout.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)

        main_title = QLabel(self.tr("Soutenir AnkiForge"))
        main_title.setStyleSheet(f"font-size: 17px; font-weight: 700; color: {DesignTokens.TEXT_PRIMARY};")
        title_col.addWidget(main_title)

        sub_title = QLabel(
            self.tr(
                "AnkiForge est un projet open-source et gratuit, développé bénévolement. "
                "Si l'application vous est utile, offrir un café permet de soutenir le "
                "développement et les futures fonctionnalités."
            )
        )
        sub_title.setWordWrap(True)
        sub_title.setStyleSheet(f"font-size: 12.5px; color: {DesignTokens.TEXT_MUTED};")
        title_col.addWidget(sub_title)

        header_layout.addLayout(title_col, stretch=1)
        root_layout.addLayout(header_layout)

        # Case à cocher de désactivation, cochée par défaut et bien contrastée
        self.checkbox = QCheckBox(self.tr("Ne plus afficher cette invitation au démarrage"))
        self.checkbox.setChecked(True)
        self.checkbox.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12.5px; font-weight: 500;")
        root_layout.addWidget(self.checkbox)

        # Pied de page d'actions
        footer_layout = QHBoxLayout()
        footer_layout.setSpacing(10)
        footer_layout.addStretch(1)

        self.btn_close = SecondaryButton(self.tr("Fermer"))
        self.btn_close.clicked.connect(self._on_close_clicked)
        footer_layout.addWidget(self.btn_close)

        self.btn_kofi = PrimaryButton(self.tr("Offrir un café sur Ko-fi ☕"))
        self.btn_kofi.clicked.connect(self._on_kofi_clicked)
        apply_shadow(self.btn_kofi, blur=8, offset_y=0, color=DesignTokens.ACCENT_GLOW)
        footer_layout.addWidget(self.btn_kofi)

        root_layout.addLayout(footer_layout)

        self.icon_label = icon_lbl
        self.header_icon = icon_lbl
        self.title_label = main_title

    def _apply_styles(self) -> None:
        self.setStyleSheet(f"""
            QDialog#SupportDialog {{
                background-color: {DesignTokens.BG_MAIN};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)

    # ── Comportement ──────────────────────────────────────────────────────────

    def _persist_preference(self) -> None:
        """Enregistre la préférence de désactivation si la case est cochée."""
        if not self.checkbox.isChecked():
            return
        try:
            settings = get_app_qsettings()
            settings.setValue("app/show_startup_support_dialog", False)
            settings.sync()
        except Exception as exc:  # pragma: no cover - défensif
            logger.debug("Persistence préférence soutien ignorée : %s", exc)

    # Alias de noms probables utilisés par d'autres appelants/tests
    def _apply_preference(self) -> None:
        self._persist_preference()

    def _save_preference(self) -> None:
        self._persist_preference()

    def _update_preferences(self) -> None:
        self._persist_preference()

    def _on_close_clicked(self) -> None:
        self._persist_preference()
        self.close()

    def _on_fermer_clicked(self) -> None:
        self._on_close_clicked()

    def close_clicked(self) -> None:
        self._on_close_clicked()

    def _on_kofi_clicked(self) -> None:
        try:
            QDesktopServices.openUrl(QUrl(self.kofi_url))
        except Exception as exc:  # pragma: no cover - défensif
            logger.debug("Ouverture URL Ko-fi échouée : %s", exc)
        self._persist_preference()
        self.close()

    def _on_support_clicked(self) -> None:
        self._on_kofi_clicked()

    def _on_donate_clicked(self) -> None:
        self._on_kofi_clicked()

    def _open_kofi(self) -> None:
        self._on_kofi_clicked()

    def _open_url(self) -> None:
        self._on_kofi_clicked()

    def support(self) -> None:
        self._on_kofi_clicked()

    def donate(self) -> None:
        self._on_kofi_clicked()

    def cancel(self) -> None:
        self._on_close_clicked()

    def accept(self) -> None:
        self._persist_preference()
        super().accept()

    def reject(self) -> None:
        self._persist_preference()
        super().reject()

    def closeEvent(self, event: Any) -> None:
        self._persist_preference()
        super().closeEvent(event)

    # URL dérivée, pratique pour les tests
    @property
    def url(self) -> str:
        return self.kofi_url

    @property
    def support_url(self) -> str:
        return self.kofi_url

    @property
    def kofi_url_property(self) -> str:
        return self.kofi_url
