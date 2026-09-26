from __future__ import annotations

import time
from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon


class ThoughtStepWidget(QFrame):
    """
    Cartouche repliable avec streaming temps réel affichant la réflexion approfondie (Extended Thinking).
    Inclut chronomètre en direct, compteur de tokens, repli automatique au premier token utile,
    et badge d'audit final.
    """

    def __init__(
        self,
        step: int = 1,
        thought_text: str = "",
        is_running: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.step = step
        self.is_running = is_running
        self._thought_text = thought_text
        self._tokens_count = self._estimate_tokens(thought_text)
        self._start_time: float = time.perf_counter() if is_running else 0.0
        self._duration_seconds: float = 0.0

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            ThoughtStepWidget {{
                background-color: {DesignTokens.BG_ACTIVE};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
            ThoughtStepWidget QLabel {{
                background: transparent;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        header_row = QHBoxLayout()
        header_row.setSpacing(6)

        self.icon_lbl = QLabel()
        self._update_icon()
        header_row.addWidget(self.icon_lbl)

        self.lbl_title = QLabel()
        self.lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-weight: 500; font-size: 11px;")
        header_row.addWidget(self.lbl_title, 1)

        self.btn_toggle = QPushButton("Détails ▾")
        self.btn_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {DesignTokens.TEXT_MUTED};
                font-size: 10px;
                padding: 2px 4px;
            }}
            QPushButton:hover {{
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)
        self.btn_toggle.clicked.connect(self._toggle_content)
        header_row.addWidget(self.btn_toggle)
        layout.addLayout(header_row)

        self.lbl_content = QLabel(thought_text)
        self.lbl_content.setWordWrap(True)
        self.lbl_content.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.lbl_content.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; line-height: 1.4; padding-top: 2px;")
        self.lbl_content.hide()
        layout.addWidget(self.lbl_content)

        # Timer pour mise à jour du chronomètre en direct
        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._on_timer_tick)

        if self.is_running:
            self._timer.start()
            self._update_running_title()
        else:
            self._update_static_title()

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Estime le nombre de tokens pour le texte de réflexion."""
        if not text:
            return 0
        words = text.split()
        return max(1, int(len(words) * 1.3))

    def _format_duration(self, seconds: float) -> str:
        """Formate la durée en secondes ou minutes:secondes."""
        if seconds < 60.0:
            return f"{seconds:.1f}s"
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins:02d}:{secs:02d}"

    def _update_running_title(self) -> None:
        elapsed = time.perf_counter() - self._start_time if self._start_time > 0 else 0.0
        dur_str = self._format_duration(elapsed)
        tok_str = f"{self._tokens_count} tokens" if self._tokens_count > 0 else "0 token"
        self.lbl_title.setText(f"Réflexion en cours... ({dur_str} • {tok_str})")

    def _update_static_title(self) -> None:
        if self._duration_seconds > 0.0:
            dur_str = self._format_duration(self._duration_seconds)
            self.lbl_title.setText(f"🧠 Réflexion terminée en {dur_str} ({self._tokens_count} tokens)")
        elif self._tokens_count > 0:
            self.lbl_title.setText(f"🧠 Réflexion terminée (~{self._tokens_count} tokens)")
        else:
            self.lbl_title.setText("🧠 Réflexion")

    def _on_timer_tick(self) -> None:
        if self.is_running:
            self._update_running_title()

    def _update_icon(self) -> None:
        icon_name = "ph.spinner" if self.is_running else "ph.brain"
        icon_color = DesignTokens.COLOR_YELLOW if self.is_running else DesignTokens.TEXT_MUTED
        self.icon_lbl.setPixmap(load_phosphor_icon(icon_name, color=icon_color).pixmap(13, 13))

    def append_delta(self, delta: str) -> None:
        """Ajoute un fragment de pensée en direct lors du streaming."""
        self._thought_text += delta
        self._tokens_count = self._estimate_tokens(self._thought_text)
        self.lbl_content.setText(self._thought_text)
        if not self.is_running:
            self.is_running = True
            if self._start_time <= 0.0:
                self._start_time = time.perf_counter()
            self._update_icon()
            if not self._timer.isActive():
                self._timer.start()
        self._update_running_title()

    def update_text(self, text: str, is_running: bool = False) -> None:
        """Met à jour l'intégralité du texte de réflexion."""
        self._thought_text = text
        self._tokens_count = self._estimate_tokens(text)
        self.lbl_content.setText(text)
        if is_running:
            if not self.is_running:
                self.is_running = True
                if self._start_time <= 0.0:
                    self._start_time = time.perf_counter()
                self._update_icon()
                if not self._timer.isActive():
                    self._timer.start()
            self._update_running_title()
        else:
            self.finish_thinking()

    def finish_thinking(self, duration_seconds: float | None = None, tokens_count: int | None = None) -> None:
        """
        Finalise la réflexion : stoppe le chronomètre, replie automatiquement le bloc,
        et fige l'en-tête avec les métriques d'audit.
        """
        if self._timer.isActive():
            self._timer.stop()

        if duration_seconds is not None:
            self._duration_seconds = duration_seconds
        elif self._start_time > 0.0:
            self._duration_seconds = max(0.1, time.perf_counter() - self._start_time)

        if tokens_count is not None:
            self._tokens_count = tokens_count
        else:
            self._tokens_count = self._estimate_tokens(self._thought_text)

        self.is_running = False
        self._update_icon()
        self._update_static_title()

        # Repli automatique (fermé par défaut)
        self.lbl_content.hide()
        self.btn_toggle.setText("Détails ▾")

    def _toggle_content(self) -> None:
        if self.lbl_content.isHidden():
            self.lbl_content.show()
            self.btn_toggle.setText("Masquer ▴")
        else:
            self.lbl_content.hide()
            self.btn_toggle.setText("Détails ▾")

    def get_thought_text(self) -> str:
        """Retourne le texte intégral accumulé de la pensée."""
        return self._thought_text

    def refresh_theme(self, profile: Any) -> None:
        self.setStyleSheet(f"""
            ThoughtStepWidget {{
                background-color: {profile.bg_active};
                border: 1px solid {profile.border_color};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
            ThoughtStepWidget QLabel {{
                background: transparent;
            }}
        """)
        icon_color = profile.color_yellow if self.is_running else profile.text_muted
        icon_name = "ph.spinner" if self.is_running else "ph.brain"
        self.icon_lbl.setPixmap(load_phosphor_icon(icon_name, color=icon_color).pixmap(13, 13))
        self.lbl_title.setStyleSheet(f"color: {profile.text_muted}; font-weight: 500; font-size: 11px;")
        self.lbl_content.setStyleSheet(f"color: {profile.text_secondary}; font-size: 11px; line-height: 1.4; padding-top: 2px;")
        self.btn_toggle.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {profile.text_muted};
                font-size: 10px;
                padding: 2px 4px;
            }}
            QPushButton:hover {{
                color: {profile.text_primary};
            }}
        """)
