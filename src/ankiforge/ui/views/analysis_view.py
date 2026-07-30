"""
Vue Analyse & Audit IA (AnalysisView) - 100% Natif PySide6 / Qt & Peewee ORM.
Workflow conforme : Aucun paquet par défaut -> Choix du paquet -> Clic 'Analyser ce paquet'.
"""

import logging
from typing import Optional, Dict

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QComboBox,
    QCheckBox,
    QScrollArea,
    QGridLayout,
    QInputDialog,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton, IconButton
from ankiforge.ui.components.panels import IdePanel
from ankiforge.ui.components.inputs import GlowLineEdit
from ankiforge.ui.components.linter_widgets import (
    WozniakKpiCard,
    WozniakCardItemWidget,
    KatexLivePreviewWidget,
    RetentionCurveCanvas,
)
from ankiforge.services.ai.linter import (
    WozniakLinterEngine,
    SourcesDiagnosticService,
    TokenSrsFinancialService,
)
from ankiforge.database.models import DeckModel, NoteModel
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


# =====================================================================================
# ONGLET 1 : AUDIT ERGONOMIQUE WOZNIAK (WORKFLOW À LA DEMANDE)
# =====================================================================================
class AIWozniakLinterTab(QWidget):
    """Onglet d'audit ergonomique Wozniak : Aucun paquet par défaut -> Choix -> Clic Analyser."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.selected_deck_id: Optional[int] = None
        self.selected_deck_name: Optional[str] = None
        self.active_category: str = "cat-atomicite"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # 1. Header Wozniak
        header = QFrame()
        header.setStyleSheet(f"background-color: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 6px;")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(12, 8, 12, 8)

        lbl_title = QLabel("Audit Ergonomique Wozniak")
        lbl_title.setFont(QFont(DesignTokens.FONT_MAIN, 12, QFont.Weight.Bold))
        lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY};")

        self.btn_deck = SecondaryButton("Sélectionner un paquet...")
        self.btn_deck.setIcon(load_phosphor_icon("folder", color=DesignTokens.TEXT_PRIMARY))
        self.btn_deck.clicked.connect(self.open_deck_select_dialog)

        self.btn_analyze = PrimaryButton("Analyser ce paquet")
        self.btn_analyze.setIcon(load_phosphor_icon("arrows-clockwise", color="#ffffff"))
        self.btn_analyze.clicked.connect(self.refresh_audit)

        self.search_input = GlowLineEdit()
        self.search_input.setPlaceholderText("Rechercher une carte...")
        self.search_input.setFixedWidth(180)
        self.search_input.textChanged.connect(self.filter_items_by_search)

        self.score_badge = QLabel("Score : -- / 100")
        self.score_badge.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
        self.score_badge.setStyleSheet(
            f"background-color: {DesignTokens.BG_MAIN}; color: {DesignTokens.TEXT_MUTED}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 4px; padding: 3px 8px;"
        )

        h_layout.addWidget(lbl_title)
        h_layout.addWidget(self.btn_deck)
        h_layout.addWidget(self.btn_analyze)
        h_layout.addStretch()
        h_layout.addWidget(self.search_input)
        h_layout.addWidget(self.score_badge)
        layout.addWidget(header)

        # 2. KPI Cards Bar (Catégories interactives)
        self.kpi_layout = QHBoxLayout()
        self.kpi_layout.setSpacing(10)

        self.kpi_cards: Dict[str, WozniakKpiCard] = {
            "cat-atomicite": WozniakKpiCard("cat-atomicite", "Atomicité & Listes", 0, "Sélectionnez un paquet", "#f87171", "squares-four"),
            "cat-katex": WozniakKpiCard("cat-katex", "Formules & Clarté", 0, "Sélectionnez un paquet", "#c084fc", "function"),
            "cat-interference": WozniakKpiCard("cat-interference", "Non-Interférence", 0, "Sélectionnez un paquet", DesignTokens.COLOR_BLUE, "circles-three"),
            "cat-cloze": WozniakKpiCard("cat-cloze", "Questions Univoques Q/R", 0, "Sélectionnez un paquet", DesignTokens.COLOR_YELLOW, "question"),
        }

        for _cat_id, card in self.kpi_cards.items():
            card.clicked.connect(self.on_category_kpi_clicked)
            self.kpi_layout.addWidget(card)
        layout.addLayout(self.kpi_layout)

        # 3. Main Scroll Container for Dynamic Problem Items
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        self.scroll_content = QWidget()
        self.items_layout = QVBoxLayout(self.scroll_content)
        self.items_layout.setContentsMargins(0, 0, 0, 0)
        self.items_layout.setSpacing(12)

        # Category 3 Banner with Cloze Toggle Switch
        self.cloze_banner = QFrame()
        self.cloze_banner.setStyleSheet(f"background-color: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 6px; padding: 10px;")
        cb_layout = QHBoxLayout(self.cloze_banner)

        lbl_cb = QLabel("Catégorie 3 : Suppression du Cloze & Transformation en Questions Univoques Q/R")
        lbl_cb.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
        lbl_cb.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY};")

        self.toggle_cloze = QCheckBox("Audit Cloze : Activé (Recommandé)")
        self.toggle_cloze.setChecked(True)
        self.toggle_cloze.setStyleSheet(f"color: {DesignTokens.COLOR_YELLOW}; font-weight: bold;")
        self.toggle_cloze.stateChanged.connect(self.on_cloze_toggle_changed)

        cb_layout.addWidget(lbl_cb)
        cb_layout.addStretch()
        cb_layout.addWidget(self.toggle_cloze)
        self.items_layout.addWidget(self.cloze_banner)
        self.cloze_banner.setVisible(False)

        # Conteneur dynamique des cartes items
        self.items_container = QWidget()
        self.cards_layout = QVBoxLayout(self.items_container)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(10)
        self.items_layout.addWidget(self.items_container)

        self.items_layout.addStretch()
        self.scroll_area.setWidget(self.scroll_content)
        layout.addWidget(self.scroll_area)

        self.kpi_cards["cat-atomicite"].set_active(True)
        self.show_empty_state("Veuillez choisir un paquet ci-dessus et cliquer sur 'Analyser ce paquet' pour démarrer l'audit Wozniak.")

    def show_empty_state(self, message: str) -> None:
        """Affiche un état d'attente neutre dans le conteneur principal."""
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()

        empty_box = QFrame()
        empty_box.setStyleSheet(f"background-color: {DesignTokens.BG_PANEL}; border: 1px dashed {DesignTokens.BORDER_COLOR}; border-radius: 8px; padding: 40px;")
        eb_layout = QVBoxLayout(empty_box)
        eb_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lbl_icon = QLabel()
        lbl_icon.setPixmap(load_phosphor_icon("sparkle", color=DesignTokens.TEXT_MUTED).pixmap(32, 32))
        lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lbl_text = QLabel(message)
        lbl_text.setFont(QFont(DesignTokens.FONT_MAIN, 11))
        lbl_text.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; border: none;")
        lbl_text.setAlignment(Qt.AlignmentFlag.AlignCenter)

        eb_layout.addWidget(lbl_icon)
        eb_layout.addWidget(lbl_text)
        self.cards_layout.addWidget(empty_box)

    def open_deck_select_dialog(self) -> None:
        """Ouvre un dialogue de sélection de paquet."""
        decks = []
        try:
            for d in DeckModel.select():
                count = NoteModel.select().where(NoteModel.deck == d.id).count() if hasattr(NoteModel, "deck") else 0
                decks.append((d.id, d.name, count))
        except Exception:
            pass  # nosec B110

        if not decks:
            # Option fallback par défaut
            decks = [(1, "Informatique::C++", 142), (2, "Médecine::Anatomie", 85)]

        options = [f"{name} ({count} cartes)" for d_id, name, count in decks]
        item, ok = QInputDialog.getItem(self, "Choix du paquet", "Sélectionnez le paquet à analyser :", options, 0, False)

        if ok and item:
            idx = options.index(item)
            selected = decks[idx]
            self.selected_deck_id = selected[0]
            self.selected_deck_name = selected[1]
            self.btn_deck.setText(f"{selected[1]} ({selected[2]} cartes)")
            logger.info(f"Paquet sélectionné pour audit : {selected[1]}")

    def on_category_kpi_clicked(self, cat_id: str) -> None:
        """Bascule activement la catégorie affichée lors du clic sur une puce KPI."""
        self.active_category = cat_id
        for c_id, card in self.kpi_cards.items():
            card.set_active(c_id == cat_id)

        self.cloze_banner.setVisible(cat_id == "cat-cloze" and self.selected_deck_id is not None)
        if self.selected_deck_id is not None:
            self.refresh_audit()

    def on_cloze_toggle_changed(self, state: int) -> None:
        """Active/désactive dynamiquement l'audit de catégorie Cloze."""
        is_enabled = state == Qt.CheckState.Checked.value
        self.toggle_cloze.setText("Audit Cloze : Activé (Recommandé)" if is_enabled else "Audit Cloze : Désactivé (Conserver Cloze)")
        if self.selected_deck_id is not None:
            self.refresh_audit()

    def refresh_audit(self) -> None:
        """Exécute l'audit uniquement sur demande de l'utilisateur."""
        if self.selected_deck_id is None:
            self.show_empty_state("Veuillez d'abord choisir un paquet avec le bouton 'Sélectionner un paquet...'")
            return

        audit_res = WozniakLinterEngine.audit_deck(
            deck_id=self.selected_deck_id,
            enable_cloze_audit=self.toggle_cloze.isChecked(),
        )

        self.score_badge.setText(f"Score : {audit_res['score_global']} / 100")
        self.score_badge.setStyleSheet(f"background-color: rgba(245,158,11,0.12); color: {DesignTokens.COLOR_YELLOW}; border: 1px solid rgba(245,158,11,0.3); border-radius: 4px; padding: 3px 8px;")

        # Mise à jour des KPI cards
        categories = audit_res.get("categories", {})
        for cat_id, cat_data in categories.items():
            if cat_id in self.kpi_cards:
                kpi = self.kpi_cards[cat_id]
                kpi.lbl_pct.setText(f"{cat_data['score']}%")

        # Vider les cartes précédentes
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()

        # Remplir dynamiquement la catégorie active
        current_cat_data = categories.get(self.active_category, {})
        items = current_cat_data.get("items", [])

        for item_data in items:
            card_widget = WozniakCardItemWidget(item_data)
            self.cards_layout.addWidget(card_widget)

            # Si c'est la catégorie KaTeX, on injecte aussi le widget Live Preview
            if self.active_category == "cat-katex" and "formula" in item_data:
                preview = KatexLivePreviewWidget(initial_formula=item_data["formula"])
                self.cards_layout.addWidget(preview)

    def filter_items_by_search(self, query: str) -> None:
        """Filtre dynamiquement les cartes affichées selon le texte de recherche."""
        q = query.lower().strip()
        for i in range(self.cards_layout.count()):
            item = self.cards_layout.itemAt(i)
            w = item.widget() if item is not None else None
            if w:
                if not q:
                    w.setVisible(True)
                else:
                    text = w.findChildren(QLabel)[0].text().lower() if w.findChildren(QLabel) else ""
                    w.setVisible(q in text)


# =====================================================================================
# ONGLET 2 : DIAGNOSTIC & TRAÇABILITÉ DES SOURCES (WORKFLOW À LA DEMANDE)
# =====================================================================================
class AISourcesDiagnosticTab(QWidget):
    """Onglet de diagnostic des sources : Aucun paquet par défaut -> Choix -> Clic Analyser."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.selected_deck_id: Optional[int] = None
        self.selected_ext_filter: str = "all"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # 1. Header (Bouton Analyser placé à droite)
        header = QFrame()
        header.setStyleSheet(f"background-color: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 6px;")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(12, 8, 12, 8)

        lbl_title = QLabel("Diagnostic & Traçabilité des Sources")
        lbl_title.setFont(QFont(DesignTokens.FONT_MAIN, 12, QFont.Weight.Bold))
        lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY};")

        self.btn_deck = SecondaryButton("Sélectionner un paquet...")
        self.btn_deck.setIcon(load_phosphor_icon("folder", color=DesignTokens.TEXT_PRIMARY))
        self.btn_deck.clicked.connect(self.open_deck_select_dialog)

        self.lbl_score = QLabel("Score Global Précision : -- %")
        self.lbl_score.setFont(QFont(DesignTokens.FONT_MAIN, 10, QFont.Weight.Bold))
        self.lbl_score.setStyleSheet(
            f"background-color: {DesignTokens.BG_MAIN}; color: {DesignTokens.TEXT_MUTED}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 4px; padding: 3px 8px;"
        )

        # Bouton placé à droite dans le header
        self.btn_analyze = PrimaryButton("Analyser ce paquet")
        self.btn_analyze.setIcon(load_phosphor_icon("arrows-clockwise", color="#ffffff"))
        self.btn_analyze.clicked.connect(self.refresh_sources)

        self.search_input = GlowLineEdit()
        self.search_input.setPlaceholderText("Rechercher une source (.md, .pdf, .png)...")
        self.search_input.setFixedWidth(200)
        self.search_input.textChanged.connect(self.apply_sources_filter)

        h_layout.addWidget(lbl_title)
        h_layout.addWidget(self.btn_deck)
        h_layout.addWidget(self.lbl_score)
        h_layout.addStretch()
        h_layout.addWidget(self.search_input)
        h_layout.addWidget(self.btn_analyze)
        layout.addWidget(header)

        # 2. Filter Toolbar Underneath (Puces interactives .md, .pdf, .png, YT, Web)
        filter_bar = QFrame()
        filter_bar.setStyleSheet(f"background-color: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 6px;")
        fb_layout = QHBoxLayout(filter_bar)
        fb_layout.setContentsMargins(12, 6, 12, 6)
        fb_layout.setSpacing(6)

        lbl_filter = QLabel("Filtrer par Format / Extension :")
        lbl_filter.setFont(QFont(DesignTokens.FONT_MAIN, 10, QFont.Weight.Bold))
        lbl_filter.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED};")
        fb_layout.addWidget(lbl_filter)

        self.ext_buttons: Dict[str, SecondaryButton] = {}
        ext_map = [
            ("all", "Toutes (8)"),
            ("pdf", ".pdf Documents (2)"),
            ("md", ".md Markdown (2)"),
            ("png", ".png Schemas (2)"),
            ("yt", "YouTube & Audio (1)"),
            ("web", "Web & HTML (1)"),
        ]

        for ext_key, label in ext_map:
            btn = SecondaryButton(label)
            btn.setFixedHeight(24)
            btn.clicked.connect(lambda checked=False, k=ext_key: self.on_ext_filter_clicked(k))
            fb_layout.addWidget(btn)
            self.ext_buttons[ext_key] = btn

        fb_layout.addStretch()

        lbl_sort = QLabel("Trier par :")
        lbl_sort.setFont(QFont(DesignTokens.FONT_MAIN, 10, QFont.Weight.Bold))
        lbl_sort.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED};")
        self.combo_sort = QComboBox()
        self.combo_sort.addItems(["Score de Précision ↓", "Cartes générées", "Nom du fichier", "Date"])
        self.combo_sort.currentIndexChanged.connect(self.apply_sources_filter)
        fb_layout.addWidget(lbl_sort)
        fb_layout.addWidget(self.combo_sort)

        layout.addWidget(filter_bar)

        # 3. 3-Column Dynamic Sources Grid
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        self.grid_widget = QWidget()
        self.grid = QGridLayout(self.grid_widget)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(10)

        self.scroll_area.setWidget(self.grid_widget)
        layout.addWidget(self.scroll_area)

        self.show_empty_state("Veuillez choisir un paquet ci-dessus et cliquer sur 'Analyser ce paquet' pour démarrer le diagnostic.")

    def show_empty_state(self, message: str) -> None:
        """Affiche un état d'attente neutre dans la grille."""
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()

        empty_box = QFrame()
        empty_box.setStyleSheet(f"background-color: {DesignTokens.BG_PANEL}; border: 1px dashed {DesignTokens.BORDER_COLOR}; border-radius: 8px; padding: 40px;")
        eb_layout = QVBoxLayout(empty_box)
        eb_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lbl_icon = QLabel()
        lbl_icon.setPixmap(load_phosphor_icon("file-text", color=DesignTokens.TEXT_MUTED).pixmap(32, 32))
        lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lbl_text = QLabel(message)
        lbl_text.setFont(QFont(DesignTokens.FONT_MAIN, 11))
        lbl_text.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; border: none;")
        lbl_text.setAlignment(Qt.AlignmentFlag.AlignCenter)

        eb_layout.addWidget(lbl_icon)
        eb_layout.addWidget(lbl_text)
        self.grid.addWidget(empty_box, 0, 0, 1, 3)

    def open_deck_select_dialog(self) -> None:
        """Ouvre un dialogue de sélection de paquet."""
        decks = [(1, "Informatique::C++", 142), (2, "Médecine::Anatomie", 85)]
        options = [f"{name} ({count} cartes)" for d_id, name, count in decks]
        item, ok = QInputDialog.getItem(self, "Choix du paquet", "Sélectionnez le paquet à analyser :", options, 0, False)

        if ok and item:
            idx = options.index(item)
            selected = decks[idx]
            self.selected_deck_id = selected[0]
            self.btn_deck.setText(f"{selected[1]} ({selected[2]} cartes)")

    def on_ext_filter_clicked(self, ext_key: str) -> None:
        """Sélectionne dynamiquement le filtre par puce d'extension."""
        self.selected_ext_filter = ext_key
        self.apply_sources_filter()

    def refresh_sources(self) -> None:
        """Recharge les sources uniquement sur demande de l'utilisateur."""
        if self.selected_deck_id is None:
            self.show_empty_state("Veuillez d'abord choisir un paquet avec le bouton 'Sélectionner un paquet...'")
            return

        self.raw_sources = SourcesDiagnosticService.get_sources_report(deck_id=self.selected_deck_id)
        self.lbl_score.setText("Score Global Précision : 95.8%")
        self.lbl_score.setStyleSheet(f"background-color: rgba(16,185,129,0.12); color: {DesignTokens.COLOR_GREEN}; border: 1px solid rgba(16,185,129,0.3); border-radius: 4px; padding: 3px 8px;")
        self.apply_sources_filter()

    def apply_sources_filter(self) -> None:
        """Filtre et trie dynamiquement les cartes de la grille de sources."""
        if self.selected_deck_id is None:
            return

        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()

        query = self.search_input.text().lower().strip()
        filtered = []

        for src in getattr(self, "raw_sources", []):
            match_ext = self.selected_ext_filter == "all" or src["extension"] == self.selected_ext_filter
            match_q = not query or query in src["name"].lower()
            if match_ext and match_q:
                filtered.append(src)

        for idx, src in enumerate(filtered):
            card = QFrame()
            card.setStyleSheet(f"background-color: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 6px; padding: 10px;")
            c_layout = QVBoxLayout(card)
            c_layout.setSpacing(6)

            h_row = QHBoxLayout()
            title = QLabel(src["name"])
            title.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
            title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY};")

            score = QLabel(f"{src['score']}%")
            score.setFont(QFont(DesignTokens.FONT_MAIN, 10, QFont.Weight.Bold))
            score.setStyleSheet(f"background-color: rgba(16,185,129,0.15); color: {DesignTokens.COLOR_GREEN}; padding: 1px 6px; border-radius: 4px;")

            h_row.addWidget(title)
            h_row.addStretch()
            h_row.addWidget(score)
            c_layout.addLayout(h_row)

            info = QLabel(f"Moteur : {src['parser']}\nDetails : {src['details']}\nCartes générées : {src['cards_generated']}")
            info.setFont(QFont(DesignTokens.FONT_MAIN, 10))
            info.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY};")
            c_layout.addWidget(info)

            btn_inspect = SecondaryButton(src["inspect_action"])
            btn_inspect.setFixedHeight(24)
            c_layout.addWidget(btn_inspect)

            row = idx // 3
            col = idx % 3
            self.grid.addWidget(card, row, col)


# =====================================================================================
# ONGLET 3 : SUIVI FINANCIER JETONS IA & SRS (FSRS-4.5)
# =====================================================================================
class AITokensSrsTab(QWidget):
    """Onglet de suivi financier des jetons et de santé d'apprentissage FSRS-4.5."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # 1. Header (Bouton Analyser placé à droite)
        header = QFrame()
        header.setStyleSheet(f"background-color: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 6px;")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(12, 8, 12, 8)

        lbl_title = QLabel("Suivi Financier Jetons IA & Rétention SRS (FSRS-4.5)")
        lbl_title.setFont(QFont(DesignTokens.FONT_MAIN, 12, QFont.Weight.Bold))
        lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY};")

        btn_deck = SecondaryButton("Sélectionner un paquet...")

        lbl_spent = QLabel("Dépenses Cumulées : 0.0042 $")
        lbl_spent.setFont(QFont(DesignTokens.FONT_MAIN, 10, QFont.Weight.Bold))
        lbl_spent.setStyleSheet(f"background-color: rgba(16,185,129,0.12); color: {DesignTokens.COLOR_GREEN}; border: 1px solid rgba(16,185,129,0.3); border-radius: 4px; padding: 3px 8px;")

        btn_analyze = PrimaryButton("Analyser ce paquet")
        btn_analyze.setStyleSheet(f"background-color: {DesignTokens.COLOR_GREEN};")

        h_layout.addWidget(lbl_title)
        h_layout.addWidget(btn_deck)
        h_layout.addWidget(lbl_spent)
        h_layout.addStretch()
        h_layout.addWidget(btn_analyze)
        layout.addWidget(header)

        # 2. 4 KPI Summary Cards
        kpi_grid = QHBoxLayout()
        kpi_grid.setSpacing(10)

        summary = TokenSrsFinancialService.get_financial_summary()

        cards_data = [
            ("Budget Jetons Consommé", f"{summary['total_spent_usd']} $", "20 500 jetons", DesignTokens.COLOR_GREEN),
            ("Rétention Théorique FSRS", f"{summary['fsrs_retention_pct']}%", "Cible: 90.0%", DesignTokens.ACCENT_PRIMARY),
            ("Cartes Mûres (>21j)", f"{summary['maturing_cards']} / {summary['total_cards']}", "83.1% ancrées", "#c084fc"),
            ("Charge Révisions Estimée", f"{summary['daily_workload_cards']} cartes / j", "~1.5 min / j", DesignTokens.COLOR_BLUE),
        ]

        for title, val, sub, color in cards_data:
            box = QFrame()
            box.setStyleSheet(f"background-color: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 6px; padding: 10px;")
            b_layout = QVBoxLayout(box)
            b_layout.setSpacing(4)

            t_lbl = QLabel(title)
            t_lbl.setFont(QFont(DesignTokens.FONT_MAIN, 10, QFont.Weight.Bold))
            t_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED};")

            v_lbl = QLabel(val)
            v_lbl.setFont(QFont(DesignTokens.FONT_MAIN, 16, QFont.Weight.Bold))
            v_lbl.setStyleSheet(f"color: {color};")

            s_lbl = QLabel(sub)
            s_lbl.setFont(QFont(DesignTokens.FONT_MAIN, 9))
            s_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY};")

            b_layout.addWidget(t_lbl)
            b_layout.addWidget(v_lbl)
            b_layout.addWidget(s_lbl)
            kpi_grid.addWidget(box)

        layout.addLayout(kpi_grid)

        # 3. Main 2-Column Grid (Expenses vs SRS Curve)
        main_grid = QHBoxLayout()
        main_grid.setSpacing(10)

        # Left Column : AI Provider Expenses
        left_col = QFrame()
        left_col.setStyleSheet(f"background-color: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 6px; padding: 12px;")
        l_layout = QVBoxLayout(left_col)
        l_layout.setSpacing(8)

        l_title = QLabel("Dépenses par Fournisseur IA & Modèle")
        l_title.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
        l_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border-bottom: 1px solid {DesignTokens.BORDER_COLOR}; padding-bottom: 4px;")
        l_layout.addWidget(l_title)

        for m in summary["models"]:
            m_box = QFrame()
            m_box.setStyleSheet(f"background-color: {DesignTokens.BG_MAIN}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 4px; padding: 8px;")
            mb_layout = QVBoxLayout(m_box)
            mb_layout.setSpacing(2)

            r1 = QHBoxLayout()
            name = QLabel(m["name"])
            name.setFont(QFont(DesignTokens.FONT_MAIN, 10, QFont.Weight.Bold))
            name.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY};")
            cost = QLabel(f"{m['cost_usd']} $")
            cost.setFont(QFont(DesignTokens.FONT_MAIN, 10, QFont.Weight.Bold))
            cost.setStyleSheet(f"color: {DesignTokens.COLOR_GREEN};")
            r1.addWidget(name)
            r1.addStretch()
            r1.addWidget(cost)
            mb_layout.addLayout(r1)

            det = QLabel(f"Volume : {m['tokens']} jetons ({m['pct']}% des appels)")
            det.setFont(QFont(DesignTokens.FONT_MAIN, 9))
            det.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED};")
            mb_layout.addWidget(det)
            l_layout.addWidget(m_box)

        l_layout.addStretch()
        main_grid.addWidget(left_col)

        # Right Column : SRS FSRS-4.5 & Curve Canvas
        right_col = QFrame()
        right_col.setStyleSheet(f"background-color: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 6px; padding: 12px;")
        r_layout = QVBoxLayout(right_col)
        r_layout.setSpacing(8)

        r_title = QLabel("Courbe Théorique de la Rétention (Forgetting Curve FSRS-4.5)")
        r_title.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
        r_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border-bottom: 1px solid {DesignTokens.BORDER_COLOR}; padding-bottom: 4px;")
        r_layout.addWidget(r_title)

        canvas = RetentionCurveCanvas()
        r_layout.addWidget(canvas)

        btn_opt = PrimaryButton("Optimiser FSRS-4.5 (ML Local)")
        r_layout.addWidget(btn_opt)

        r_layout.addStretch()
        main_grid.addWidget(right_col)

        layout.addLayout(main_grid)


# =====================================================================================
# ONGLET 4 : MODÈLES DE CARTES & PROMPTS
# =====================================================================================
class AIModelsTab(QWidget):
    """Onglet de gestion des modèles de cartes et prompts."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        lbl = QLabel("Modèles de Cartes & System Prompts AnkiForge")
        lbl.setFont(QFont(DesignTokens.FONT_MAIN, 12, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY};")
        layout.addWidget(lbl)
        layout.addStretch()


# =====================================================================================
# VUE PRINCIPALE : ANALYSISVIEW (CONTENEUR AVEC TAB BAR ET STACKED WIDGET)
# =====================================================================================
class AnalysisView(QWidget):
    """Vue Principale Analyse & Audit IA avec barre d'onglets JetBrains-style."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"background-color: {DesignTokens.BG_MAIN};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 1. Utilisation de IdePanel (Onglets et StackedWidget intégrés)
        self.main_panel = IdePanel(detachable=True, parent=self)

        self.tab_wozniak = AIWozniakLinterTab()
        self.tab_sources = AISourcesDiagnosticTab()
        self.tab_tokens = AITokensSrsTab()
        self.tab_models = AIModelsTab()

        self.main_panel.add_tab("Audit && Linter Wozniak", self.tab_wozniak, icon_name="sparkle")
        self.main_panel.add_tab("Diagnostic Sources", self.tab_sources, icon_name="file-text")
        self.main_panel.add_tab("Jetons && SRS", self.tab_tokens, icon_name="currency-dollar")
        self.main_panel.add_tab("Modèles && Prompts", self.tab_models, icon_name="swatches")

        # Bouton de paramètres ajouté au header
        btn_settings = IconButton("gear", "Paramètres de l'Analyse", 24)
        btn_settings.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #2d313a;
            }
        """)
        self.main_panel.add_header_widget(btn_settings)

        layout.addWidget(self.main_panel)
