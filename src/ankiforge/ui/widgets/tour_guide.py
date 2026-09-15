"""
Tour Guide & Onboarding interactif pour AnkiForge.
Affiche une bulle d'aide flottante guidant l'utilisateur à travers les zones clés de l'application.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QPoint, QSettings, Qt, Signal
from PySide6.QtGui import QColor, QScreen
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ankiforge.ui.components.buttons import ActionButton, PrimaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


@dataclass
class TourStep:
    """Étape individuelle de la visite guidée."""

    title: str
    text: str
    target_widget: QWidget | None = None
    target_widget_getter: Callable[[], QWidget | None] | None = None
    action: Callable[[], None] | None = None


class TourBubble(QWidget):
    """La bulle d'information flottante qui guide l'utilisateur."""

    tour_finished = Signal()

    def __init__(self, main_window: QWidget) -> None:
        super().__init__(main_window)
        self.main_window = main_window

        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumWidth(380)
        self.setMaximumWidth(460)

        self.current_step: int = 0
        self.steps: list[TourStep] = []

        self._setup_ui()
        self.hide()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        self.bg_frame = QWidget()
        self.bg_frame.setObjectName("TourBubbleBg")
        self.bg_frame.setStyleSheet(f"""
            QWidget#TourBubbleBg {{
                background-color: {DesignTokens.BG_PANEL};
                border: 2px solid {DesignTokens.ACCENT_PRIMARY};
                border-radius: {DesignTokens.RADIUS_LG}px;
            }}
        """)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setColor(QColor(0, 0, 0, 160))
        shadow.setOffset(0, 6)
        self.bg_frame.setGraphicsEffect(shadow)

        bg_layout = QVBoxLayout(self.bg_frame)
        bg_layout.setContentsMargins(20, 20, 20, 18)
        bg_layout.setSpacing(12)

        self.lbl_title = QLabel("Titre")
        self.lbl_title.setStyleSheet(f"""
            font-size: 16px;
            font-weight: bold;
            color: {DesignTokens.ACCENT_PRIMARY};
            border: none;
            background: transparent;
        """)
        bg_layout.addWidget(self.lbl_title)

        self.lbl_text = QLabel("Description...")
        self.lbl_text.setStyleSheet(f"""
            font-size: 13px;
            line-height: 1.4;
            color: {DesignTokens.TEXT_PRIMARY};
            border: none;
            background: transparent;
        """)
        self.lbl_text.setWordWrap(True)
        bg_layout.addWidget(self.lbl_text)
        bg_layout.addSpacing(6)

        # --- BARRE DE BOUTONS ---
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.btn_skip = ActionButton("x", " Quitter", parent=self)
        self.btn_skip.clicked.connect(self.end_tour)
        btn_layout.addWidget(self.btn_skip)

        btn_layout.addStretch()

        self.btn_prev = ActionButton("arrow-left", " Précédent", parent=self)
        self.btn_prev.clicked.connect(self.prev_step)
        btn_layout.addWidget(self.btn_prev)

        self.lbl_counter = QLabel("1/x")
        self.lbl_counter.setStyleSheet(f"""
            color: {DesignTokens.TEXT_MUTED};
            font-weight: 600;
            font-size: 12px;
            font-family: '{DesignTokens.FONT_CODE}';
            padding: 0 8px;
            border: none;
            background: transparent;
        """)
        self.lbl_counter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        btn_layout.addWidget(self.lbl_counter)

        self.btn_next = PrimaryButton("Suivant ", parent=self)
        self.btn_next.setIcon(load_phosphor_icon("arrow-right", color="white"))
        self.btn_next.clicked.connect(self.next_step)
        btn_layout.addWidget(self.btn_next)

        bg_layout.addLayout(btn_layout)
        layout.addWidget(self.bg_frame)

    def set_scenario(self, steps: list[TourStep | dict[str, Any]]) -> None:
        """Définit la liste des étapes du tour (supporte objets TourStep ou dicts)."""
        normalized_steps: list[TourStep] = []
        for step in steps:
            if isinstance(step, TourStep):
                normalized_steps.append(step)
            elif isinstance(step, dict):
                normalized_steps.append(
                    TourStep(
                        title=step.get("title", ""),
                        text=step.get("text", ""),
                        target_widget=step.get("target_widget"),
                        target_widget_getter=step.get("target_widget_getter"),
                        action=step.get("action"),
                    )
                )
        self.steps = normalized_steps
        self.current_step = 0

    def start_tour(self) -> None:
        """Démarre le déroulement de la visite guidée."""
        if not self.steps:
            return
        self.current_step = 0
        self.show()
        self.raise_()
        self.play_step()

    def play_step(self) -> None:
        """Exécute et affiche l'étape active."""
        if self.current_step >= len(self.steps):
            self.end_tour()
            return

        step = self.steps[self.current_step]

        if step.action and callable(step.action):
            try:
                step.action()
            except Exception as e:
                logger.warning("Erreur durant l'action de l'étape de tour: %s", e)

        self.lbl_title.setText(step.title)
        self.lbl_text.setText(step.text)
        self.lbl_counter.setText(f"{self.current_step + 1}/{len(self.steps)}")

        # Gestion des boutons
        self.btn_prev.setVisible(self.current_step > 0)

        if self.current_step == len(self.steps) - 1:
            self.btn_next.setText(" Terminer")
            self.btn_next.setIcon(load_phosphor_icon("check", color="white"))
        else:
            self.btn_next.setText(" Suivant")
            self.btn_next.setIcon(load_phosphor_icon("arrow-right", color="white"))

        QApplication.processEvents()

        # Résolution du widget cible
        target = step.target_widget
        if step.target_widget_getter and callable(step.target_widget_getter):
            try:
                target = step.target_widget_getter()
            except Exception:
                target = None

        self._position_bubble(target)

    def _position_bubble(self, target_widget: QWidget | None) -> None:
        """Calcule le positionnement optimal de la bulle à côté du widget cible."""
        self.adjustSize()

        screen: QScreen | None = self.screen()
        screen_rect = screen.availableGeometry() if screen else self.main_window.geometry()

        if target_widget is None or not target_widget.isVisible():
            parent_geom = self.main_window.geometry()
            x = parent_geom.x() + (parent_geom.width() - self.width()) // 2
            y = parent_geom.y() + (parent_geom.height() - self.height()) // 2
            self.move(x, y)
            return

        target_pos = target_widget.mapToGlobal(QPoint(0, 0))

        # Essayer d'abord à droite
        if target_pos.x() + target_widget.width() + 16 + self.width() <= screen_rect.right():
            x = target_pos.x() + target_widget.width() + 16
            y = target_pos.y()
        # Sinon à gauche
        elif target_pos.x() - self.width() - 16 >= screen_rect.left():
            x = target_pos.x() - self.width() - 16
            y = target_pos.y()
        # Sinon en-dessous
        else:
            x = max(screen_rect.left() + 10, target_pos.x())
            y = target_pos.y() + target_widget.height() + 16

        # Clamping vertical
        if y + self.height() > screen_rect.bottom() - 16:
            y = screen_rect.bottom() - self.height() - 16
        if y < screen_rect.top() + 16:
            y = screen_rect.top() + 16

        # Clamping horizontal
        if x + self.width() > screen_rect.right() - 16:
            x = screen_rect.right() - self.width() - 16
        if x < screen_rect.left() + 16:
            x = screen_rect.left() + 16

        self.move(x, y)

    def prev_step(self) -> None:
        """Revient à l'étape précédente."""
        if self.current_step > 0:
            self.current_step -= 1
            self.play_step()

    def next_step(self) -> None:
        """Avance à l'étape suivante ou termine."""
        self.current_step += 1
        self.play_step()

    def end_tour(self) -> None:
        """Termine et enregistre la fin de la visite guidée."""
        self.hide()
        settings = QSettings("AnkiForge", "AnkiForge")
        settings.setValue("app/tour_completed", True)
        if hasattr(self.main_window, "settings") and hasattr(self.main_window.settings, "setValue"):
            try:
                self.main_window.settings.setValue("app/tour_completed", True)
            except (RuntimeError, AttributeError, OSError) as e:
                logger.debug("Échec enregistrement tour_completed : %s", e)
        self.tour_finished.emit()


def create_default_tour_steps(main_window: Any) -> list[TourStep]:
    """Génère le parcours d'onboarding standard pour AnkiForge."""
    return [
        TourStep(
            title="✨ Bienvenue dans AnkiForge",
            text=(
                "AnkiForge est votre atelier professionnel de création, d'ingestion "
                "et d'audit de cartes Anki assisté par IA.\n\n"
                "Ce guide rapide vous présente en 5 étapes les zones clés de l'application."
            ),
            target_widget=None,
        ),
        TourStep(
            title="🧭 Barre de Navigation & Espaces",
            text=(
                "La barre latérale regroupe tous vos ateliers : Tableau de bord, Studio de création, "
                "Éditeur de notes, Audit Wozniak & SRS, Consultant IA, Pipelines et Laboratoire A/B.\n"
                "Vous pouvez la replier à tout moment pour maximiser votre espace de travail."
            ),
            target_widget_getter=lambda: getattr(main_window, "sidebar", None),
        ),
        TourStep(
            title="⚡ Studio de Création & Ingestion",
            text=("Transformez vos cours et documents (PDF, Markdown, pages web, vidéos YouTube) en cartes mémoires atomiques de haute qualité grâce à l'IA et aux pipelines modulaires."),
            target_widget_getter=lambda: main_window.sidebar._items.get("creation") if hasattr(main_window, "sidebar") and hasattr(main_window.sidebar, "_items") else None,
            action=lambda: main_window._on_view_selected("creation") if hasattr(main_window, "_on_view_selected") else None,
        ),
        TourStep(
            title="🎴 Édition & Navigateur de Cartes",
            text=(
                "Visualisez, filtrez et peaufinez vos notes avec aperçu en temps réel (Bureau, Tablette, Mobile). Profitez du support KaTeX, du gestionnaire de cloze et de l'historique Time Machine."
            ),
            target_widget_getter=lambda: main_window.sidebar._items.get("edition") if hasattr(main_window, "sidebar") and hasattr(main_window.sidebar, "_items") else None,
            action=lambda: main_window._on_view_selected("edition") if hasattr(main_window, "_on_view_selected") else None,
        ),
        TourStep(
            title="🔬 Analyse, Audit Wozniak & RAG",
            text=(
                "Vérifiez l'atomicité et l'efficacité mémorielle de vos cartes selon les 20 règles de Piotr Wozniak. Identifiez les lacunes documentaires et optimisez vos rétentions avec FSRS-4.5."
            ),
            target_widget_getter=lambda: main_window.sidebar._items.get("analysis") if hasattr(main_window, "sidebar") and hasattr(main_window.sidebar, "_items") else None,
            action=lambda: main_window._on_view_selected("analysis") if hasattr(main_window, "_on_view_selected") else None,
        ),
        TourStep(
            title="🤖 Consultant IA & Palette de Commandes",
            text=(
                "Votre copilote autonome disponible pour auditer ou enrichir vos paquets. "
                "Astuce : ouvrez la Palette de commandes à tout moment via Ctrl+K / ⌘K "
                "pour rechercher et naviguer instantanément !"
            ),
            target_widget_getter=lambda: main_window.sidebar._items.get("consultant") if hasattr(main_window, "sidebar") and hasattr(main_window.sidebar, "_items") else None,
            action=lambda: main_window._on_view_selected("consultant") if hasattr(main_window, "_on_view_selected") else None,
        ),
    ]
