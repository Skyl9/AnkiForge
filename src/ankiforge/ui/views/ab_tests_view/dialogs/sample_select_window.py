"""
Fenêtre modale de sélection d'un texte d'exemple (PRESET_SAMPLES).
Miroir de `document_select_window.py` pour le Laboratoire A/B.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.views.ab_tests_view.constants import PRESET_SAMPLES
from ankiforge.utils.icon_loader import load_phosphor_icon


class SampleSelectWindow(QWidget):
    """
    Fenêtre modale de sélection d'un texte d'exemple prédéfini avec recherche et aperçu.
    Émet `sample_picked(str)` avec le texte brut choisi.
    """

    sample_picked = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.setWindowTitle("Choisir un texte d'exemple")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setFixedSize(520, 480)
        self._samples: list[tuple[str, str, str]] = list(PRESET_SAMPLES)

        self.setStyleSheet(f"""
            QWidget {{
                background-color: {DesignTokens.BG_PANEL};
            }}
        """)

        self.setWindowFlags(Qt.WindowType.Dialog if parent else Qt.WindowType.Window)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(14, 14, 14, 14)
        content_layout.setSpacing(12)

        # Barre de recherche
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Rechercher un exemple (ex: Médical, Angles, Droit)...")
        search_icon = load_phosphor_icon("ph.magnifying-glass", color=DesignTokens.TEXT_MUTED)
        self.search_input.addAction(search_icon, QLineEdit.ActionPosition.LeadingPosition)
        self.search_input.setFixedHeight(32)

        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                padding: 0 10px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 12px;
                font-family: '{DesignTokens.FONT_MAIN}';
            }}
            QLineEdit:focus {{
                border: 1px solid {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        self.search_input.textChanged.connect(self._on_search_changed)
        content_layout.addWidget(self.search_input)

        # Liste des exemples
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list.setIconSize(self.list.iconSize())
        self.list.setStyleSheet(f"""
            QListWidget {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 12px;
                font-family: '{DesignTokens.FONT_MAIN}';
                outline: none;
            }}
            QListWidget::item {{
                padding: 8px 6px;
                border: none;
            }}
            QListWidget::item:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
        """)
        palette = self.list.palette()
        palette.setColor(QPalette.ColorRole.Highlight, QColor(0, 0, 0, 0))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(DesignTokens.ACCENT_PRIMARY))
        self.list.setPalette(palette)
        content_layout.addWidget(self.list)

        # Aperçu du texte
        self.preview = QTextBrowser()
        self.preview.setOpenExternalLinks(False)
        self.preview.setStyleSheet(f"""
            QTextBrowser {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 12px;
                font-family: '{DesignTokens.FONT_MAIN}';
                padding: 8px;
            }}
        """)
        self.preview.setPlaceholderText("Sélectionnez un exemple pour l'apercevoir.")
        content_layout.addWidget(self.preview, 1)

        layout.addWidget(content)

        # Footer avec actions
        footer = QWidget()
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.setSpacing(8)

        btn_cancel = SecondaryButton("Annuler")
        btn_cancel.clicked.connect(self.close)

        self.btn_confirm = PrimaryButton("Utiliser cet exemple")
        self.btn_confirm.clicked.connect(self._on_confirm)
        self.btn_confirm.setEnabled(False)

        footer_layout.addStretch()
        footer_layout.addWidget(btn_cancel)
        footer_layout.addWidget(self.btn_confirm)
        layout.addWidget(footer)

        self.list.itemSelectionChanged.connect(self._on_selection_changed)
        self.list.itemDoubleClicked.connect(lambda item: self._on_confirm())
        self._populate()

    def _populate(self) -> None:
        self._all_items: list[tuple[QListWidgetItem, str, str, str]] = []
        for name, text, color_hex in self._samples:
            item = QListWidgetItem(name)
            item.setIcon(load_phosphor_icon("ph.text-t", color=color_hex))
            item.setToolTip(text)
            self._all_items.append((item, name, text, color_hex))
            self.list.addItem(item)

    def _on_search_changed(self, query: str) -> None:
        q = query.lower().strip()
        for item, name, _text, _color in self._all_items:
            item.setHidden(bool(q) and q not in name.lower())

    def _get_selected_sample(self) -> tuple[str, str, str] | None:
        selected = self.list.selectedItems()
        if not selected:
            return None
        item = selected[0]
        for it, name, text, color_hex in self._all_items:
            if it is item:
                return name, text, color_hex
        return None

    def _on_selection_changed(self) -> None:
        sample = self._get_selected_sample()
        if sample is not None:
            _name, text, _color_hex = sample
            self.preview.setHtml(f"<p style='color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px;'>{text}</p>")
            self.btn_confirm.setEnabled(True)
        else:
            self.preview.clear()
            self.btn_confirm.setEnabled(False)

    def _on_confirm(self) -> None:
        sample = self._get_selected_sample()
        if sample is not None:
            _name, text, _color_hex = sample
            self.sample_picked.emit(text)
            self.close()
