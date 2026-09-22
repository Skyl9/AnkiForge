"""
Batch Activity Log — Journal d'activité moderne remplaçant le terminal QPlainTextEdit vert.

Timeline d'événements horodatés avec icônes Phosphor et badges d'erreur filtrables.
Maintient la rétrocompatibilité avec les tests qui accèdent à :
  - view.terminal_content      → cet objet (QWidget)
  - view._terminal_expanded    → attribut booléen exposé par BatchView

Qt equivalent: QWidget (VBoxLayout with QScrollArea timeline)
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)

# Mapping niveau → (icône Phosphor, couleur DesignToken)
_LEVEL_STYLE: dict[str, tuple[str, str]] = {
    "INFO": ("ph.info", DesignTokens.COLOR_BLUE),
    "SUCCESS": ("ph.check-circle", DesignTokens.COLOR_GREEN),
    "WARN": ("ph.warning", DesignTokens.COLOR_YELLOW),
    "WARNING": ("ph.warning", DesignTokens.COLOR_YELLOW),
    "ERROR": ("ph.x-circle", DesignTokens.COLOR_RED),
    "CRITICAL": ("ph.skull", DesignTokens.COLOR_RED),
    "DEBUG": ("ph.bug", DesignTokens.TEXT_MUTED),
}

_MAX_ENTRIES = 500  # Limite glissante pour éviter la saturation mémoire


class _LogEntry(QFrame):
    """Une ligne horodatée dans la timeline d'activité."""

    def __init__(self, level: str, message: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("batchLogEntry")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        icon_name, color = _LEVEL_STYLE.get(level.upper(), ("ph.circle", DesignTokens.TEXT_MUTED))
        now_str = datetime.datetime.now().strftime("%H:%M:%S")

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 4, 8, 4)
        row.setSpacing(8)

        # Icône
        ico = QLabel()
        ico.setPixmap(load_phosphor_icon(icon_name, color=color).pixmap(14, 14))
        ico.setStyleSheet("border: none; background: transparent;")
        ico.setFixedWidth(18)

        # Timestamp
        ts_lbl = QLabel(now_str)
        ts_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-family: '{DesignTokens.FONT_CODE}'; border: none; background: transparent;")
        ts_lbl.setFixedWidth(54)

        # Badge niveau
        level_lbl = QLabel(level.upper()[:7])
        level_lbl.setStyleSheet(f"color: {color}; font-size: 10px; font-weight: bold; font-family: '{DesignTokens.FONT_CODE}'; border: none; background: transparent;")
        level_lbl.setFixedWidth(54)

        # Message
        msg_lbl = QLabel(message)
        msg_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px; font-family: '{DesignTokens.FONT_CODE}'; border: none; background: transparent;")
        msg_lbl.setWordWrap(True)
        msg_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        row.addWidget(ico)
        row.addWidget(ts_lbl)
        row.addWidget(level_lbl)
        row.addWidget(msg_lbl, 1)

        self.setStyleSheet(f"QFrame#batchLogEntry {{ background: transparent; border: none; border-bottom: 1px solid {DesignTokens.BORDER_COLOR}; }}")


class BatchActivityLog(QWidget):
    """
    Journal d'activité moderne remplaçant la QPlainTextEdit verte.

    Expose :
      - append_log(level, message)   → ajoute une entrée typée
      - clear()                       → vide la timeline
      - appendHtml(html)             → compat legacy (reparse niveau depuis le HTML)

    Qt equivalent: QWidget (VBoxLayout)
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("batchActivityLog")
        self._entries: list[_LogEntry] = []
        self._filter_level: str | None = None  # None = tout afficher

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Barre de filtres ──────────────────────────────────────────────
        filter_bar = QWidget()
        filter_bar.setStyleSheet(f"background: {DesignTokens.BG_PANEL}; border-bottom: 1px solid {DesignTokens.BORDER_COLOR};")
        filter_row = QHBoxLayout(filter_bar)
        filter_row.setContentsMargins(8, 4, 8, 4)
        filter_row.setSpacing(4)

        filter_lbl = QLabel("Filtrer :")
        filter_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; border: none; background: transparent;")
        filter_row.addWidget(filter_lbl)

        for level in ("ALL", "INFO", "SUCCESS", "WARN", "ERROR"):
            _, color = _LEVEL_STYLE.get(level, ("ph.circle", DesignTokens.TEXT_MUTED))
            btn_label = QLabel(level)
            btn_label.setStyleSheet(f"color: {color}; font-size: 10px; font-weight: bold; padding: 2px 6px; border: 1px solid {color}; border-radius: 8px; background: transparent; cursor: pointer;")
            btn_label.setFixedHeight(18)
            btn_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            # NOTE: wrapping labels as clickable filters via mousePressEvent
            _level_capture = level  # capture pour closure

            def _make_handler(lv: str) -> Any:
                def _handler(_event: Any) -> None:
                    self._filter_level = None if lv == "ALL" else lv
                    self._apply_filter()

                return _handler

            btn_label.mousePressEvent = _make_handler(_level_capture)
            filter_row.addWidget(btn_label)

        filter_row.addStretch()
        main_layout.addWidget(filter_bar)

        # ── Zone scrollable ───────────────────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(f"QScrollArea {{ background: {DesignTokens.BG_INPUT}; border: none; }}")

        self._timeline = QWidget()
        self._timeline.setObjectName("batchTimelineContainer")
        self._timeline.setStyleSheet("background: transparent;")
        self._timeline_layout = QVBoxLayout(self._timeline)
        self._timeline_layout.setContentsMargins(0, 0, 0, 0)
        self._timeline_layout.setSpacing(0)
        self._timeline_layout.addStretch()

        self._scroll.setWidget(self._timeline)
        main_layout.addWidget(self._scroll, 1)

    # ── API publique ──────────────────────────────────────────────────────

    def append_log(self, level: str, message: str) -> None:
        """Ajoute une entrée typée dans la timeline."""
        # Respect limite glissante
        while len(self._entries) >= _MAX_ENTRIES:
            oldest = self._entries.pop(0)
            self._timeline_layout.removeWidget(oldest)
            oldest.deleteLater()

        entry = _LogEntry(level, message, self._timeline)
        self._entries.append(entry)
        # Insérer avant le stretch (dernier item)
        insert_idx = self._timeline_layout.count() - 1
        self._timeline_layout.insertWidget(insert_idx, entry)

        if self._filter_level and level.upper() != self._filter_level:
            entry.setVisible(False)

        # Auto-scroll vers le bas
        sb = self._scroll.verticalScrollBar()
        if sb:
            sb.setValue(sb.maximum())

    def clear(self) -> None:
        """Vide la timeline."""
        for entry in self._entries:
            self._timeline_layout.removeWidget(entry)
            entry.deleteLater()
        self._entries.clear()

    def appendHtml(self, html: str) -> None:
        """Compatibilité legacy : parse le niveau dans l'HTML et délègue à append_log."""
        level = "INFO"
        for lvl in ("SUCCESS", "ERROR", "WARN", "WARNING", "DEBUG"):
            if lvl.lower() in html.lower() or f">{lvl}<" in html:
                level = lvl
                break
        # Extraction texte brut minimal
        import re

        text = re.sub(r"<[^>]+>", " ", html).strip()
        text = " ".join(text.split())
        self.append_log(level, text or html[:120])

    # ── Thème ─────────────────────────────────────────────────────────────

    def refresh_theme(self, profile: Any) -> None:
        self._scroll.setStyleSheet(f"QScrollArea {{ background: {profile.bg_input}; border: none; }}")

    # ── Filtrage ─────────────────────────────────────────────────────────

    def _apply_filter(self) -> None:
        for entry in self._entries:
            # _level_text est stocké via objectName trick — on re-lit via le QLabel niveau
            # Simplification : on cache/affiche via la présence du badge dans le style
            entry.setVisible(True)  # reset

        if self._filter_level:
            target = self._filter_level.upper()
            for entry in self._entries:
                # Lire le niveau depuis le 3ème widget (index 2) du layout de l'entrée
                layout = entry.layout()
                if layout and layout.count() >= 3:
                    item = layout.itemAt(2)
                    widget = item.widget() if item else None
                    if isinstance(widget, QLabel) and widget.text().upper() != target:
                        entry.setVisible(False)
