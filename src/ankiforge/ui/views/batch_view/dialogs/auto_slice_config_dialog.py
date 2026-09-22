"""Boîte de dialogue de configuration pour le découpage automatique d'un document."""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import DocumentModel
from ankiforge.services.batch.slicing_service import SlicingMode, SlicingService
from ankiforge.ui.components import PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_on_accent_icon, load_phosphor_icon

logger = logging.getLogger(__name__)


class AutoSliceConfigDialog(QDialog):
    """Dialogue modal permettant de choisir et calibrer la règle de découpage automatique."""

    def __init__(self, doc: DocumentModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.doc = doc
        self.doc_content = getattr(doc, "content", "") or ""
        self.total_words = SlicingService.estimate_words(self.doc_content)
        self.total_tokens = SlicingService.estimate_tokens(self.doc_content)

        self._selected_mode = SlicingMode.HEADINGS
        self._config_params: dict[str, Any] = {}

        self.setWindowTitle("Découpage Automatique du Document")
        self.setFixedWidth(520)
        self._setup_ui()
        self._update_preview()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # En-tête avec métadonnées du document
        header_card = QFrame()
        header_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 10px;
            }}
        """)
        h_layout = QVBoxLayout(header_card)
        h_layout.setContentsMargins(4, 4, 4, 4)
        h_layout.setSpacing(4)

        doc_title_lbl = QLabel(self.doc.title)
        doc_title_lbl.setStyleSheet(f"font-weight: bold; font-size: 13px; color: {DesignTokens.TEXT_PRIMARY};")
        stats_lbl = QLabel(f"Taille totale : ~{self.total_words:,} mots • ~{self.total_tokens:,} tokens".replace(",", " "))
        stats_lbl.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_SECONDARY}; font-family: {DesignTokens.FONT_CODE};")

        h_layout.addWidget(doc_title_lbl)
        h_layout.addWidget(stats_lbl)
        layout.addWidget(header_card)

        # Section Choix de la Stratégie
        strat_lbl = QLabel("CHOISIR LA RÈGLE DE DÉCOUPAGE")
        strat_lbl.setStyleSheet(f"font-size: 10px; font-weight: bold; color: {DesignTokens.TEXT_MUTED}; letter-spacing: 0.5px;")
        layout.addWidget(strat_lbl)

        self.btn_group = QButtonGroup(self)

        self.rb_headings = QRadioButton("Par Chapitres / Titres (Recommandé)")
        self.rb_headings.setChecked(True)
        self.rb_tokens = QRadioButton("Par Blocs de Tokens (Contenu continu)")
        self.rb_pages = QRadioButton("Par Tranches de Pages (PDF / PPTX)")

        self.btn_group.addButton(self.rb_headings, 0)
        self.btn_group.addButton(self.rb_tokens, 1)
        self.btn_group.addButton(self.rb_pages, 2)

        radio_layout = QVBoxLayout()
        radio_layout.setSpacing(8)
        radio_layout.addWidget(self.rb_headings)
        radio_layout.addWidget(self.rb_tokens)
        radio_layout.addWidget(self.rb_pages)
        layout.addLayout(radio_layout)

        # Stack de réglages fins selon la stratégie
        self.settings_stack = QStackedWidget()

        # 0: Réglages Titres
        w_headings = QWidget()
        l_headings = QVBoxLayout(w_headings)
        l_headings.setContentsMargins(0, 4, 0, 4)
        self.lbl_headings_info = QLabel("Découpe le document à chaque grand chapitre (H1 ou H2) et fusionne les sections trop courtes (< 50 mots).")
        self.lbl_headings_info.setWordWrap(True)
        self.lbl_headings_info.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px;")
        l_headings.addWidget(self.lbl_headings_info)
        self.settings_stack.addWidget(w_headings)

        # 1: Réglages Tokens
        w_tokens = QWidget()
        l_tokens = QVBoxLayout(w_tokens)
        l_tokens.setContentsMargins(0, 4, 0, 4)
        l_tokens.setSpacing(6)
        t_header = QHBoxLayout()
        self.lbl_token_target = QLabel("Budget cible par tâche :")
        self.lbl_token_target.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px;")
        self.lbl_token_val = QLabel("2 000 tokens")
        self.lbl_token_val.setStyleSheet(f"color: {DesignTokens.ACCENT_PRIMARY}; font-weight: bold; font-family: {DesignTokens.FONT_CODE}; font-size: 11px;")
        t_header.addWidget(self.lbl_token_target)
        t_header.addStretch()
        t_header.addWidget(self.lbl_token_val)
        l_tokens.addLayout(t_header)

        self.slider_tokens = QSlider(Qt.Orientation.Horizontal)
        self.slider_tokens.setMinimum(800)
        self.slider_tokens.setMaximum(4000)
        self.slider_tokens.setSingleStep(200)
        self.slider_tokens.setValue(2000)
        self.slider_tokens.valueChanged.connect(self._on_token_slider_changed)
        l_tokens.addWidget(self.slider_tokens)
        self.settings_stack.addWidget(w_tokens)

        # 2: Réglages Pages
        w_pages = QWidget()
        l_pages = QHBoxLayout(w_pages)
        l_pages.setContentsMargins(0, 4, 0, 4)
        lbl_pages = QLabel("Nombre de pages par tâche :")
        lbl_pages.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px;")
        self.spin_pages = QSpinBox()
        self.spin_pages.setRange(1, 20)
        self.spin_pages.setValue(5)
        self.spin_pages.valueChanged.connect(lambda _: self._update_preview())
        l_pages.addWidget(lbl_pages)
        l_pages.addStretch()
        l_pages.addWidget(self.spin_pages)
        self.settings_stack.addWidget(w_pages)

        layout.addWidget(self.settings_stack)

        # Encart de prévisualisation du résultat
        self.preview_card = QFrame()
        self.preview_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px dashed {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 10px;
            }}
        """)
        p_layout = QHBoxLayout(self.preview_card)
        p_layout.setContentsMargins(6, 6, 6, 6)
        ico_prev = QLabel()
        ico_prev.setPixmap(load_phosphor_icon("ph.sparkle", color=DesignTokens.COLOR_YELLOW).pixmap(16, 16))
        self.lbl_preview_result = QLabel()
        self.lbl_preview_result.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px;")
        p_layout.addWidget(ico_prev)
        p_layout.addWidget(self.lbl_preview_result, 1)
        layout.addWidget(self.preview_card)

        layout.addStretch()

        # Boutons d'action
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self.btn_cancel = SecondaryButton("Annuler")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_apply = PrimaryButton("Découper & Ajouter à la Queue")
        self.btn_apply.setIcon(load_on_accent_icon("ph.scissors"))
        self.btn_apply.clicked.connect(self._on_apply)

        btn_row.addWidget(self.btn_cancel)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_apply)
        layout.addLayout(btn_row)

        # Signaux
        self.rb_headings.toggled.connect(self._on_mode_changed)
        self.rb_tokens.toggled.connect(self._on_mode_changed)
        self.rb_pages.toggled.connect(self._on_mode_changed)

    def _on_mode_changed(self) -> None:
        if self.rb_headings.isChecked():
            self.settings_stack.setCurrentIndex(0)
            self._selected_mode = SlicingMode.HEADINGS
        elif self.rb_tokens.isChecked():
            self.settings_stack.setCurrentIndex(1)
            self._selected_mode = SlicingMode.TOKENS
        elif self.rb_pages.isChecked():
            self.settings_stack.setCurrentIndex(2)
            self._selected_mode = SlicingMode.PAGES
        self._update_preview()

    def _on_token_slider_changed(self, val: int) -> None:
        self.lbl_token_val.setText(f"{val:,} tokens".replace(",", " "))
        self._update_preview()

    def _update_preview(self) -> None:
        slices = self.get_slices()
        count = len(slices)
        avg_tokens = int(self.total_tokens / max(1, count))
        self.lbl_preview_result.setText(f"Résultat estimé : <b>{count} tâche(s)</b> (~{avg_tokens:,} tokens par tâche)".replace(",", " "))

    def get_slices(self) -> list[Any]:
        """Exécute le découpage virtuel selon la configuration courante."""
        if self._selected_mode == SlicingMode.HEADINGS:
            return SlicingService.slice_by_headings(self.doc_content, max_depth=2, min_words=50)
        if self._selected_mode == SlicingMode.TOKENS:
            target = self.slider_tokens.value()
            return SlicingService.slice_by_tokens(self.doc_content, target_tokens=target, overlap_tokens=150)
        if self._selected_mode == SlicingMode.PAGES:
            pages = self.spin_pages.value()
            return SlicingService.slice_by_pages(self.doc_content, pages_per_slice=pages)
        return []

    def get_result(self) -> dict[str, Any]:
        """Retourne les tranches générées et la configuration utilisée."""
        return {
            "mode": self._selected_mode.value,
            "slices": self.get_slices(),
        }

    def _on_apply(self) -> None:
        self.accept()
