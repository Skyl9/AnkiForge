from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ankiforge.services.batch.slicing_service import GranularityLevel, SliceUnit, SlicingMode, SlicingService
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class AutoSliceWidget(QWidget):
    """Sélecteur et calibrage d'une règle de découpage automatique sur un contenu donné.

    - 4 paliers de granularité : Large (Macro), Équilibré (Standard), Fin (Atomique), Personnalisé.
    - Contrôles précis par mode : Profondeur des titres (H1..H3), seuil de fusion, tokens cibles, pages.
    - Synchronisation bidirectionnelle : ajuster un paramètre bascule automatiquement en Personnalisé.
    - Prévisualisation live immédiate du nombre de tâches et métriques.
    """

    slices_changed = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.doc_content = ""
        self.total_words = 0
        self.total_tokens = 0
        self._selected_mode = SlicingMode.HEADINGS
        self._granularity_level = GranularityLevel.BALANCED
        self._syncing_controls = False

        self._setup_ui()
        self.set_content("")
        self._apply_granularity_to_controls(GranularityLevel.BALANCED)

    def set_content(self, content: str) -> None:
        """Redéfinit le contenu découpable et recalcule la prévisualisation."""
        self.doc_content = content or ""
        self.total_words = SlicingService.estimate_words(self.doc_content)
        self.total_tokens = SlicingService.estimate_tokens(self.doc_content)
        self.stats_lbl.setText(f"Taille découpable : ~{self.total_words:,} mots • ~{self.total_tokens:,} tokens".replace(",", " "))
        self._update_preview()
        self.slices_changed.emit(self.get_slices())

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # 1. En-tête statistiques
        self.stats_lbl = QLabel("Taille découpable : ~0 mots • ~0 tokens")
        self.stats_lbl.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_SECONDARY}; font-family: {DesignTokens.FONT_CODE};")
        layout.addWidget(self.stats_lbl)

        # 2. Règle de découpage (Modes)
        strat_lbl = QLabel("RÈGLE DE DÉCOUPAGE")
        strat_lbl.setStyleSheet(f"font-size: 10px; font-weight: bold; color: {DesignTokens.TEXT_MUTED}; letter-spacing: 0.5px;")
        layout.addWidget(strat_lbl)

        self.btn_group_modes = QButtonGroup(self)
        self.rb_headings = QRadioButton("Par Chapitres / Titres (Structure sémantique)")
        self.rb_headings.setChecked(True)
        self.rb_tokens = QRadioButton("Par Blocs de Tokens (Contenu continu)")
        self.rb_pages = QRadioButton("Par Tranches de Pages (PDF / Présentations)")

        self.btn_group_modes.addButton(self.rb_headings, 0)
        self.btn_group_modes.addButton(self.rb_tokens, 1)
        self.btn_group_modes.addButton(self.rb_pages, 2)

        modes_row = QHBoxLayout()
        modes_row.setSpacing(16)
        modes_row.addWidget(self.rb_headings)
        modes_row.addWidget(self.rb_tokens)
        modes_row.addWidget(self.rb_pages)
        modes_row.addStretch()
        layout.addLayout(modes_row)

        # 3. Paliers de granularité
        gran_lbl = QLabel("NIVEAU DE GRANULARITÉ")
        gran_lbl.setStyleSheet(f"font-size: 10px; font-weight: bold; color: {DesignTokens.TEXT_MUTED}; letter-spacing: 0.5px;")
        layout.addWidget(gran_lbl)

        self.btn_group_granularity = QButtonGroup(self)
        self.rb_gran_coarse = QRadioButton("Large (Macro)")
        self.rb_gran_balanced = QRadioButton("Équilibré (Standard)")
        self.rb_gran_fine = QRadioButton("Fin (Atomique)")
        self.rb_gran_custom = QRadioButton("Personnalisé")

        self.btn_group_granularity.addButton(self.rb_gran_coarse, 0)
        self.btn_group_granularity.addButton(self.rb_gran_balanced, 1)
        self.btn_group_granularity.addButton(self.rb_gran_fine, 2)
        self.btn_group_granularity.addButton(self.rb_gran_custom, 3)
        self.rb_gran_balanced.setChecked(True)

        gran_row = QHBoxLayout()
        gran_row.setSpacing(16)
        gran_row.addWidget(self.rb_gran_coarse)
        gran_row.addWidget(self.rb_gran_balanced)
        gran_row.addWidget(self.rb_gran_fine)
        gran_row.addWidget(self.rb_gran_custom)
        gran_row.addStretch()
        layout.addLayout(gran_row)

        self.lbl_granularity_desc = QLabel()
        self.lbl_granularity_desc.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-style: italic;")
        layout.addWidget(self.lbl_granularity_desc)

        # 4. Paramètres détaillés par mode (Settings Stack)
        self.settings_stack = QStackedWidget()

        # Page 0 : Headings settings
        w_headings = QWidget()
        l_headings = QVBoxLayout(w_headings)
        l_headings.setContentsMargins(0, 4, 0, 4)
        l_headings.setSpacing(8)

        h_controls_row = QHBoxLayout()
        h_controls_row.setSpacing(12)

        lbl_depth = QLabel("Profondeur de découpe :")
        lbl_depth.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px;")
        self.combo_depth = QComboBox()
        self.combo_depth.addItems(
            [
                "H1 uniquement (Grands chapitres)",
                "H1 + H2 (Chapitres et sections majeures)",
                "H1 + H2 + H3 (Sous-sections détaillées)",
                "Tous les niveaux (H1 à H6)",
            ]
        )
        self.combo_depth.setCurrentIndex(1)
        combo_style = (
            f"font-size: 11px; background-color: {DesignTokens.BG_INPUT}; color: {DesignTokens.TEXT_PRIMARY}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 4px; padding: 2px 8px;"
        )
        self.combo_depth.setStyleSheet(combo_style)
        self.combo_depth.currentIndexChanged.connect(self._on_headings_control_changed)

        lbl_fusion = QLabel("Seuil de fusion micro-sections :")
        lbl_fusion.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px;")
        self.spin_min_words = QSpinBox()
        self.spin_min_words.setRange(0, 300)
        self.spin_min_words.setValue(50)
        self.spin_min_words.setSuffix(" mots min.")
        self.spin_min_words.setToolTip("Les sections comportant moins de mots que ce seuil sont fusionnées dans la section adjacente.")
        spin_style = (
            f"font-size: 11px; background-color: {DesignTokens.BG_INPUT}; color: {DesignTokens.TEXT_PRIMARY}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 4px; padding: 2px 6px;"
        )
        self.spin_min_words.setStyleSheet(spin_style)
        self.spin_min_words.valueChanged.connect(self._on_headings_control_changed)

        h_controls_row.addWidget(lbl_depth)
        h_controls_row.addWidget(self.combo_depth)
        h_controls_row.addSpacing(16)
        h_controls_row.addWidget(lbl_fusion)
        h_controls_row.addWidget(self.spin_min_words)
        h_controls_row.addStretch()
        l_headings.addLayout(h_controls_row)

        lbl_headings_info = QLabel("Les sous-sections situées au-delà de la profondeur choisie sont automatiquement incluses dans la tâche parente.")
        lbl_headings_info.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px;")
        l_headings.addWidget(lbl_headings_info)
        self.settings_stack.addWidget(w_headings)

        # Page 1 : Tokens settings
        w_tokens = QWidget()
        l_tokens = QVBoxLayout(w_tokens)
        l_tokens.setContentsMargins(0, 4, 0, 4)
        l_tokens.setSpacing(8)

        t_header = QHBoxLayout()
        lbl_token_target = QLabel("Budget cible par tâche :")
        lbl_token_target.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px;")
        self.lbl_token_val = QLabel("2 000 tokens")
        self.lbl_token_val.setStyleSheet(f"color: {DesignTokens.ACCENT_PRIMARY}; font-weight: bold; font-family: {DesignTokens.FONT_CODE}; font-size: 11px;")
        t_header.addWidget(lbl_token_target)
        t_header.addStretch()
        t_header.addWidget(self.lbl_token_val)
        l_tokens.addLayout(t_header)

        t_slider_row = QHBoxLayout()
        t_slider_row.setSpacing(10)
        self.slider_tokens = QSlider(Qt.Orientation.Horizontal)
        self.slider_tokens.setMinimum(500)
        self.slider_tokens.setMaximum(4000)
        self.slider_tokens.setSingleStep(100)
        self.slider_tokens.setValue(2000)
        self.slider_tokens.valueChanged.connect(self._on_token_slider_changed)
        t_slider_row.addWidget(self.slider_tokens, 1)

        # Boutons presets rapides tokens
        btn_t_1000 = QPushButton("1 000 tks")
        btn_t_2000 = QPushButton("2 000 tks")
        btn_t_3500 = QPushButton("3 500 tks")
        for btn, val in [(btn_t_1000, 1000), (btn_t_2000, 2000), (btn_t_3500, 3500)]:
            btn.setFixedHeight(22)
            btn.setStyleSheet(f"font-size: 10px; padding: 2px 6px; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 4px; background: {DesignTokens.BG_INPUT};")
            btn.clicked.connect(lambda _, v=val: self._set_token_value(v))
            t_slider_row.addWidget(btn)

        l_tokens.addLayout(t_slider_row)
        self.settings_stack.addWidget(w_tokens)

        # Page 2 : Pages settings
        w_pages = QWidget()
        l_pages = QVBoxLayout(w_pages)
        l_pages.setContentsMargins(0, 4, 0, 4)
        l_pages.setSpacing(8)

        p_row = QHBoxLayout()
        p_row.setSpacing(10)
        lbl_pages = QLabel("Nombre de pages par tâche :")
        lbl_pages.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px;")
        self.spin_pages = QSpinBox()
        self.spin_pages.setRange(1, 30)
        self.spin_pages.setValue(5)
        pages_spin_style = (
            f"font-size: 11px; background-color: {DesignTokens.BG_INPUT}; color: {DesignTokens.TEXT_PRIMARY}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 4px; padding: 2px 6px;"
        )
        self.spin_pages.setStyleSheet(pages_spin_style)
        self.spin_pages.valueChanged.connect(self._on_pages_control_changed)
        p_row.addWidget(lbl_pages)
        p_row.addWidget(self.spin_pages)
        p_row.addSpacing(16)

        # Boutons presets rapides pages
        btn_p_1 = QPushButton("1 page")
        btn_p_3 = QPushButton("3 pages")
        btn_p_5 = QPushButton("5 pages")
        btn_p_10 = QPushButton("10 pages")
        for btn, val in [(btn_p_1, 1), (btn_p_3, 3), (btn_p_5, 5), (btn_p_10, 10)]:
            btn.setFixedHeight(22)
            btn.setStyleSheet(f"font-size: 10px; padding: 2px 6px; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 4px; background: {DesignTokens.BG_INPUT};")
            btn.clicked.connect(lambda _, v=val: self._set_page_value(v))
            p_row.addWidget(btn)

        p_row.addStretch()
        l_pages.addLayout(p_row)
        self.settings_stack.addWidget(w_pages)

        layout.addWidget(self.settings_stack)

        # 5. Carte de prévisualisation live garantie sans rognage
        self.preview_card = QFrame()
        self.preview_card.setMinimumHeight(44)
        self.preview_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px dashed {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        p_layout = QHBoxLayout(self.preview_card)
        p_layout.setContentsMargins(12, 8, 12, 8)
        p_layout.setSpacing(10)

        ico_prev = QLabel()
        ico_prev.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ico_prev.setPixmap(load_phosphor_icon("ph.sparkle", color=DesignTokens.COLOR_YELLOW).pixmap(16, 16))

        self.lbl_preview_result = QLabel()
        self.lbl_preview_result.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_preview_result.setWordWrap(True)
        self.lbl_preview_result.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px;")

        p_layout.addWidget(ico_prev, alignment=Qt.AlignmentFlag.AlignVCenter)
        p_layout.addWidget(self.lbl_preview_result, 1, alignment=Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.preview_card)

        # Raccordement des signaux de mode et granularité
        self.rb_headings.toggled.connect(self._on_mode_changed)
        self.rb_tokens.toggled.connect(self._on_mode_changed)
        self.rb_pages.toggled.connect(self._on_mode_changed)

        self.rb_gran_coarse.toggled.connect(self._make_granularity_slot(GranularityLevel.COARSE))
        self.rb_gran_balanced.toggled.connect(self._make_granularity_slot(GranularityLevel.BALANCED))
        self.rb_gran_fine.toggled.connect(self._make_granularity_slot(GranularityLevel.FINE))
        self.rb_gran_custom.toggled.connect(self._make_granularity_slot(GranularityLevel.CUSTOM))

        self._update_granularity_desc()

    def _make_granularity_slot(self, level: GranularityLevel) -> Callable[[bool], None]:
        def _slot(checked: bool) -> None:
            if checked:
                self._on_granularity_toggled(level)

        return _slot

    # ── Gestion des modes et de la granularité ──────────────────────────────────

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

        self._update_granularity_desc()
        self._update_preview()
        self.slices_changed.emit(self.get_slices())

    def _on_granularity_toggled(self, level: GranularityLevel) -> None:
        if self._syncing_controls:
            return
        self._granularity_level = level
        self._update_granularity_desc()
        if level != GranularityLevel.CUSTOM:
            self._apply_granularity_to_controls(level)
        self._update_preview()
        self.slices_changed.emit(self.get_slices())

    def _apply_granularity_to_controls(self, level: GranularityLevel) -> None:
        self._syncing_controls = True
        try:
            # 1. Headings
            depth, min_w = SlicingService.get_headings_preset(level)
            # depth: 1 -> index 0 (H1), 2 -> index 1 (H1+H2), 3 -> index 2 (H1+H2+H3)
            self.combo_depth.setCurrentIndex(min(2, max(0, depth - 1)))
            self.spin_min_words.setValue(min_w)

            # 2. Tokens
            target_tks, _ = SlicingService.get_tokens_preset(level)
            self.slider_tokens.setValue(target_tks)
            self.lbl_token_val.setText(f"{target_tks:,} tokens".replace(",", " "))

            # 3. Pages
            pages = SlicingService.get_pages_preset(level)
            self.spin_pages.setValue(pages)
        finally:
            self._syncing_controls = False

    def _update_granularity_desc(self) -> None:
        mode = self._selected_mode
        level = self._granularity_level

        if level == GranularityLevel.COARSE:
            if mode == SlicingMode.HEADINGS:
                desc = "Large (Macro) : Découpage aux grands chapitres (H1). Toutes les sous-sections sont regroupées dans la tâche parente."
            elif mode == SlicingMode.TOKENS:
                desc = "Large (Macro) : Blocs denses de ~3 500 tokens pour réduire le nombre total de requêtes."
            else:
                desc = "Large (Macro) : Tranches de 10 pages par tâche pour documents volumineux."
        elif level == GranularityLevel.BALANCED:
            if mode == SlicingMode.HEADINGS:
                desc = "Équilibré (Standard) : Découpage aux chapitres et sections (H1-H2). Recommandé pour des cartes ciblées."
            elif mode == SlicingMode.TOKENS:
                desc = "Équilibré (Standard) : Blocs optimaux de ~2 000 tokens avec chevauchement doux."
            else:
                desc = "Équilibré (Standard) : Tranches équilibrées de 5 pages par tâche."
        elif level == GranularityLevel.FINE:
            if mode == SlicingMode.HEADINGS:
                desc = "Fin (Atomique) : Découpage approfondi jusqu'aux sous-sections (H1-H3) avec seuil de fusion réduit."
            elif mode == SlicingMode.TOKENS:
                desc = "Fin (Atomique) : Petits blocs de ~1 000 tokens pour une granularité maximale."
            else:
                desc = "Fin (Atomique) : 1 page par tâche (idéal pour planches d'anatomie, diaporamas et fiches de révision)."
        else:
            desc = "Personnalisé : Les paramètres manuels ci-dessous sont appliqués directement."

        self.lbl_granularity_desc.setText(desc)

    def _mark_as_custom_if_user_edited(self) -> None:
        if self._syncing_controls:
            return
        if self._granularity_level != GranularityLevel.CUSTOM:
            self._syncing_controls = True
            self.rb_gran_custom.setChecked(True)
            self._granularity_level = GranularityLevel.CUSTOM
            self._syncing_controls = False
            self._update_granularity_desc()

    def _on_headings_control_changed(self) -> None:
        self._mark_as_custom_if_user_edited()
        self._update_preview()
        self.slices_changed.emit(self.get_slices())

    def _on_token_slider_changed(self, val: int) -> None:
        self.lbl_token_val.setText(f"{val:,} tokens".replace(",", " "))
        self._mark_as_custom_if_user_edited()
        self._update_preview()
        self.slices_changed.emit(self.get_slices())

    def _set_token_value(self, val: int) -> None:
        self.slider_tokens.setValue(val)

    def _on_pages_control_changed(self) -> None:
        self._mark_as_custom_if_user_edited()
        self._update_preview()
        self.slices_changed.emit(self.get_slices())

    def _set_page_value(self, val: int) -> None:
        self.spin_pages.setValue(val)

    # ── Prévisualisation et calcul des tranches ────────────────────────────────

    def _update_preview(self) -> None:
        slices = self.get_slices()
        count = len(slices)
        avg_tokens = int(self.total_tokens / max(1, count))
        avg_words = int(self.total_words / max(1, count))
        self.lbl_preview_result.setText(f"Résultat estimé : <b>{count} tâche(s)</b> (~{avg_tokens:,} tokens • ~{avg_words:,} mots par tâche)".replace(",", " "))

    def get_max_depth(self) -> int:
        """Retourne la profondeur de titre sélectionnée."""
        idx = self.combo_depth.currentIndex()
        if idx == 0:
            return 1
        if idx == 1:
            return 2
        if idx == 2:
            return 3
        return 6

    def get_slices(self) -> list[SliceUnit]:
        """Exécute le découpage virtuel selon la règle, la granularité et le contenu courants."""
        if self._selected_mode == SlicingMode.HEADINGS:
            depth = self.get_max_depth()
            min_w = self.spin_min_words.value()
            return SlicingService.slice_by_headings(self.doc_content, max_depth=depth, min_words=min_w)
        if self._selected_mode == SlicingMode.TOKENS:
            target = self.slider_tokens.value()
            return SlicingService.slice_by_tokens(self.doc_content, target_tokens=target, overlap_tokens=150)
        if self._selected_mode == SlicingMode.PAGES:
            pages = self.spin_pages.value()
            return SlicingService.slice_by_pages(self.doc_content, pages_per_slice=pages)
        return []

    def get_granularity_level(self) -> GranularityLevel:
        """Retourne le palier de granularité actif."""
        return self._granularity_level

    def set_granularity_level(self, level: GranularityLevel | str) -> None:
        """Définit le palier de granularité actif."""
        lvl = GranularityLevel(str(level).lower())
        if lvl == GranularityLevel.COARSE:
            self.rb_gran_coarse.setChecked(True)
        elif lvl == GranularityLevel.BALANCED:
            self.rb_gran_balanced.setChecked(True)
        elif lvl == GranularityLevel.FINE:
            self.rb_gran_fine.setChecked(True)
        else:
            self.rb_gran_custom.setChecked(True)

    def get_result(self) -> dict[str, Any]:
        """Retourne la configuration complète et les tranches générées."""
        return {
            "mode": self._selected_mode.value,
            "granularity": self._granularity_level.value,
            "max_depth": self.get_max_depth(),
            "min_words": self.spin_min_words.value(),
            "target_tokens": self.slider_tokens.value(),
            "pages_per_slice": self.spin_pages.value(),
            "slices": self.get_slices(),
        }
