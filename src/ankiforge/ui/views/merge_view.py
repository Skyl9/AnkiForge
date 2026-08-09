from typing import Optional
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QLabel, QTextEdit, QScrollArea
from PySide6.QtCore import Qt, Signal

from ankiforge.ui.components import SecondaryButton, PrimaryButton
from ankiforge.ui.theme import DesignTokens


class MergeView(QWidget):
    """
    Vue pour résoudre les conflits de mise à jour (Levenshtein < 95%).
    Splitter à 3 panneaux: Old Chunk (V1), New Chunk (V2), Anki Cards.
    """

    request_navigation = Signal(str, object)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        # Header
        header_layout = QHBoxLayout()
        title = QLabel("Résolution de Conflits (Smart Merge)")
        title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 18px; font-weight: bold;")

        subtitle = QLabel("Comparaison des versions (Levenshtein < 95%)")
        subtitle.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 12px;")

        header_vbox = QVBoxLayout()
        header_vbox.addWidget(title)
        header_vbox.addWidget(subtitle)
        header_layout.addLayout(header_vbox)
        header_layout.addStretch()

        main_layout.addLayout(header_layout)

        # 3-panel Splitter
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Panel 1: Old Chunk (V1)
        self.old_chunk_panel = self._create_text_panel("Ancien Chunk (V1)", DesignTokens.COLOR_RED)
        self.main_splitter.addWidget(self.old_chunk_panel)

        # Panel 2: New Chunk (V2)
        self.new_chunk_panel = self._create_text_panel("Nouveau Chunk (V2)", DesignTokens.COLOR_GREEN)
        self.main_splitter.addWidget(self.new_chunk_panel)

        # Panel 3: Anki Cards
        self.anki_cards_panel = self._create_anki_cards_panel()
        self.main_splitter.addWidget(self.anki_cards_panel)

        # Configure Splitter sizes (1:1:1 approx)
        self.main_splitter.setSizes([300, 300, 300])
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setStretchFactor(2, 1)

        main_layout.addWidget(self.main_splitter, 1)

        # Footer Action Bar
        footer_layout = QHBoxLayout()
        footer_layout.addStretch()
        self.btn_ignore = SecondaryButton("Ignorer et lier à la V2")
        self.btn_edit_card = PrimaryButton("Éditer la carte")
        footer_layout.addWidget(self.btn_ignore)
        footer_layout.addWidget(self.btn_edit_card)
        main_layout.addLayout(footer_layout)

    def _create_text_panel(self, title_text: str, border_color: str) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel(title_text)
        title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: 600;")
        layout.addWidget(title)

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_PRIMARY};
                border: 2px solid {border_color};
                border-radius: 6px;
                padding: 8px;
            }}
        """)
        layout.addWidget(text_edit)

        # Store a reference dynamically if needed, but not required for scaffolding
        return panel

    def _create_anki_cards_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel("Cartes Anki associées (V1)")
        title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: 600;")
        layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 6px; background-color: transparent;")

        cards_container = QWidget()
        cards_layout = QVBoxLayout(cards_container)
        cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Placeholder for cards
        placeholder = QLabel("Aucune carte associée à afficher.")
        placeholder.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED};")
        cards_layout.addWidget(placeholder)

        scroll.setWidget(cards_container)
        layout.addWidget(scroll)

        return panel
