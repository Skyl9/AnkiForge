"""Bandeau d'activité global d'une passe de réindexation RAG (ADR 0021).

Indicateur d'avancement unique et persistant, hébergé **hors** des dispositions
enfichables (au niveau de :class:`~ankiforge.ui.main_window.MainWindow`), de sorte
qu'une passe reste visible quel que soit l'écran actif.

Il présente deux niveaux, jamais mélangés :

- le **macro** — libellé ``Réindexation X/N : <titre>`` et pourcentage global
  calculé sur les **documents terminés** ;
- le **micro** opportuniste — fragments traités du document courant, affiché à part.

Le bandeau est masqué au repos : il n'existe que pendant une passe.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget

from ankiforge.ui.components import Badge, IconButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.i18n import tr
from ankiforge.utils.icon_loader import load_phosphor_icon


class ReindexActivityBanner(QFrame):
    """Bandeau d'avancement d'une passe de réindexation (masqué au repos)."""

    cancel_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setVisible(False)
        self.setObjectName("reindexActivityBanner")
        self._build_ui()
        self._apply_style()

    def _apply_style(self) -> None:
        """Applique les jetons sémantiques courants (rejouable au changement de thème)."""
        self.setStyleSheet(f"""
            QFrame#reindexActivityBanner {{
                background-color: {DesignTokens.BG_PANEL};
                border: none;
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
            }}
        """)
        self.icon_label.setPixmap(load_phosphor_icon("ph.arrows-clockwise", color=DesignTokens.ACCENT_PRIMARY).pixmap(16, 16))
        self.lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 600;")
        self.lbl_fragments.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {DesignTokens.BG_INPUT};
                border: none;
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
            QProgressBar::chunk {{
                background-color: {DesignTokens.ACCENT_PRIMARY};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)

    def refresh_theme(self, profile: object = None) -> None:
        """Recolore le bandeau lors d'un changement de thème (jetons réassignés à chaud)."""
        self._apply_style()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 8, 14, 8)
        outer.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(8)

        self.icon_label = QLabel()
        header.addWidget(self.icon_label)

        self.lbl_title = QLabel(tr("Réindexation en préparation..."))
        header.addWidget(self.lbl_title, 1)

        self.lbl_fragments = QLabel("")
        self.lbl_fragments.setVisible(False)
        header.addWidget(self.lbl_fragments)

        self.badge_percent = Badge("0 %", variant="filled")
        header.addWidget(self.badge_percent)

        self.btn_cancel = IconButton("ph.x", tooltip=tr("Interrompre la réindexation"), size=18)
        self.btn_cancel.clicked.connect(self.cancel_requested.emit)
        header.addWidget(self.btn_cancel)

        outer.addLayout(header)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(5)
        outer.addWidget(self.progress_bar)

    # ─── Réactions aux signaux du hub ───

    def handle_started(self, total: int) -> None:
        """Affiche le bandeau au démarrage d'une passe de ``total`` documents."""
        self.progress_bar.setRange(0, max(total, 1))
        self.progress_bar.setValue(0)
        self.badge_percent.setText("0 %")
        self.lbl_fragments.setVisible(False)
        self.lbl_title.setText(tr("Réindexation en préparation..."))
        # L'annulation est coopérative *entre documents* : sur une passe mono-document,
        # aucun point d'interruption n'existe, le bouton promettrait donc une action vaine.
        self.btn_cancel.setVisible(total > 1)
        self.setVisible(True)

    def handle_progress(self, number: int, total: int, title: str) -> None:
        """Met à jour le macro : document courant, total et pourcentage de documents terminés."""
        self.progress_bar.setRange(0, max(total, 1))
        completed = max(number - 1, 0)
        self.progress_bar.setValue(completed)
        percent = round(completed / total * 100) if total else 0
        self.badge_percent.setText(f"{percent} %")
        self.lbl_title.setText(tr("Réindexation %1/%2 : %3", number, total, title))

    def handle_fragments(self, processed: int, total: int) -> None:
        """Met à jour la micro-progression (fragments) du document courant, sans toucher au macro."""
        if total <= 0:
            self.lbl_fragments.setVisible(False)
            return
        self.lbl_fragments.setText(tr("Fragments : %1/%2", processed, total))
        self.lbl_fragments.setVisible(True)

    def reset(self) -> None:
        """Masque le bandeau et remet l'affichage à zéro (repos)."""
        self.setVisible(False)
        self.progress_bar.setValue(0)
        self.lbl_fragments.clear()
        self.lbl_fragments.setVisible(False)
        self.lbl_title.setText(tr("Réindexation en préparation..."))
        self.badge_percent.setText("0 %")
