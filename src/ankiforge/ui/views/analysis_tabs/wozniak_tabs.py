from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QScrollArea, QStackedWidget
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QMouseEvent

from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon
from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton
from ankiforge.ui.components.inputs import StyledLineEdit
from ankiforge.ui.widgets.card_preview_widget import CardPreviewWidget  # Ton composant existant !


class WozniakKpiCard(QFrame):
    """Carte KPI cliquable servant d'onglet de navigation."""

    clicked = Signal(str)

    def __init__(self, cat_id: str, title: str, score: str, icon_name: str, color: str, desc: str, parent=None):
        super().__init__(parent)
        self.cat_id = cat_id
        self.base_color = color
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(80)

        self.setStyleSheet(f"""
            WozniakKpiCard {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
            WozniakKpiCard:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        # En-tête : Titre + Score
        header_layout = QHBoxLayout()
        icon_lbl = QLabel()
        icon_lbl.setPixmap(load_phosphor_icon(icon_name, color=self.base_color).pixmap(16, 16))

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(f"font-weight: 600; color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px;")

        score_lbl = QLabel(score)
        score_lbl.setStyleSheet(f"font-weight: bold; color: {self.base_color}; font-size: 12px;")

        header_layout.addWidget(icon_lbl)
        header_layout.addWidget(title_lbl)
        header_layout.addStretch()
        header_layout.addWidget(score_lbl)
        layout.addLayout(header_layout)

        # Barre de progression
        progress_bg = QFrame()
        progress_bg.setFixedHeight(4)
        progress_bg.setStyleSheet(f".QFrame {{ background-color: {DesignTokens.BG_MAIN}; border-radius: 2px; }}")
        prog_layout = QHBoxLayout(progress_bg)
        prog_layout.setContentsMargins(0, 0, 0, 0)

        progress_bar = QFrame()
        # On convertit le score "85%" en un flex stretch (très basique pour l'UI)
        pct = int(score.replace("%", ""))
        progress_bar.setStyleSheet(f".QFrame {{ background-color: {self.base_color}; border-radius: 2px; }}")
        prog_layout.addWidget(progress_bar, stretch=pct)
        prog_layout.addStretch(100 - pct)

        layout.addWidget(progress_bg)

        # Description
        desc_lbl = QLabel(desc)
        desc_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px;")
        layout.addWidget(desc_lbl)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.cat_id)
        super().mousePressEvent(event)

    def set_active(self, is_active: bool):
        if is_active:
            self.setStyleSheet(f"""
                WozniakKpiCard {{
                    background-color: {DesignTokens.BG_ACTIVE};
                    border: 1px solid {self.base_color};
                    border-radius: {DesignTokens.RADIUS_MD}px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                WozniakKpiCard {{
                    background-color: {DesignTokens.BG_PANEL};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: {DesignTokens.RADIUS_MD}px;
                }}
                WozniakKpiCard:hover {{ background-color: {DesignTokens.BG_HOVER}; }}
            """)


class WozniakIssueWidget(QFrame):
    """Le composant Accordéon contenant un problème détecté par le Linter."""

    def __init__(self, title: str, badge_text: str, badge_color: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            WozniakIssueWidget {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(12, 12, 12, 12)
        self.main_layout.setSpacing(10)

        # --- HEADER (Toujours visible) ---
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)

        lbl_title = QLabel(title)
        lbl_title.setStyleSheet(f"font-weight: bold; color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px;")

        lbl_badge = QLabel(badge_text)
        lbl_badge.setStyleSheet(f"background-color: rgba(248, 113, 113, 0.15); color: {badge_color}; font-weight: bold; font-size: 10px; padding: 2px 6px; border-radius: 4px;")

        btn_inspect = SecondaryButton("Inspecter (Live Preview)")
        btn_inspect.setFixedHeight(24)
        btn_inspect.clicked.connect(self.toggle_inspector)

        header_layout.addWidget(lbl_title)
        header_layout.addWidget(lbl_badge)
        header_layout.addStretch()
        header_layout.addWidget(btn_inspect)

        self.main_layout.addWidget(header_widget)

        # Ligne de séparation
        self.sep = QFrame()
        self.sep.setFrameShape(QFrame.Shape.HLine)
        self.sep.setStyleSheet(f"background-color: {DesignTokens.BORDER_COLOR}; border: none; max-height: 1px;")
        self.sep.setVisible(False)
        self.main_layout.addWidget(self.sep)

        # --- INSPECTOR CONTAINER (Caché par défaut) ---
        self.inspector_container = QFrame()
        self.inspector_container.setVisible(False)
        self.inspector_layout = QHBoxLayout(self.inspector_container)
        self.inspector_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.addWidget(self.inspector_container)

        self._build_inspector_content()

    def _build_inspector_content(self):
        """Construit le panneau de Diff et le CardPreviewWidget."""
        # Panneau Gauche : Éditeur de code (Suggestion IA)
        left_panel = QFrame()
        left_layout = QVBoxLayout(left_panel)

        lbl_source = QLabel("CODE SOURCE (MODIFIABLE) :")
        lbl_source.setStyleSheet("font-size: 10px; font-weight: bold; color: #c084fc;")

        # L'éditeur de texte enrichi pour le KaTeX ou la nouvelle question
        from PySide6.QtWidgets import QPlainTextEdit

        self.editor = QPlainTextEdit()
        self.editor.setStyleSheet(
            f"background-color: {DesignTokens.BG_MAIN}; border: 1px solid {DesignTokens.BORDER_COLOR}; font-family: {DesignTokens.FONT_CODE}; color: {DesignTokens.TEXT_PRIMARY};"
        )
        self.editor.setPlainText(r"\[ \int_{-\infty}^{\infty} |f(t)|^2 dt = \frac{1}{2\pi} \int_{-\infty}^{\infty} |\hat{f}(\omega)|^2 d\omega \]")
        self.editor.textChanged.connect(self._on_text_changed)

        left_layout.addWidget(lbl_source)
        left_layout.addWidget(self.editor)
        self.inspector_layout.addWidget(left_panel, stretch=1)

        # Panneau Droit : Le composant WebEngine existant
        right_panel = QFrame()
        right_layout = QVBoxLayout(right_panel)

        lbl_preview = QLabel("RENDU LIVE KATEX :")
        lbl_preview.setStyleSheet("font-size: 10px; font-weight: bold; color: #c084fc;")

        # Utilisation de TON composant CardPreviewWidget
        self.preview_widget = CardPreviewWidget()
        right_layout.addWidget(lbl_preview)
        right_layout.addWidget(self.preview_widget)
        self.inspector_layout.addWidget(right_panel, stretch=1)

        # Boutons d'action
        actions_layout = QHBoxLayout()
        actions_layout.addStretch()
        btn_ignore = SecondaryButton("Ignorer")
        btn_accept = PrimaryButton("Valider et Sauvegarder (Ctrl+Enter)")
        btn_accept.setStyleSheet(btn_accept.styleSheet() + "background-color: #9333ea;")  # Violet KaTeX

        actions_layout.addWidget(btn_ignore)
        actions_layout.addWidget(btn_accept)
        self.main_layout.addLayout(actions_layout)

    @Slot()
    def toggle_inspector(self):
        is_visible = self.inspector_container.isVisible()
        self.inspector_container.setVisible(not is_visible)
        self.sep.setVisible(not is_visible)

        # Trigger un premier rendu si on ouvre l'inspecteur
        if not is_visible:
            self._on_text_changed()

    @Slot()
    def _on_text_changed(self):
        """Met à jour le CardPreviewWidget en temps réel avec le LaTeX."""
        text = self.editor.toPlainText()
        # On crée un faux dictionnaire de champs pour nourrir ton CardPreviewWidget
        fields_dict = {"Front": text, "Back": ""}

        # Il faut un NoteTypeModel mocké ou réel de la base de données.
        from ankiforge.database.models import NoteTypeModel

        nt = NoteTypeModel.get_or_none(NoteTypeModel.name == "Basic")
        if nt:
            self.preview_widget.update_preview(note_type=nt, fields_dict=fields_dict)


class AIWozniakLinterTab(QWidget):
    """Vue principale de l'onglet Linter Wozniak."""

    def __init__(self, ai_manager, parent=None):
        super().__init__(parent)
        self.ai_manager = ai_manager
        self.kpi_cards = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # 1. Header (Titre, Paquet, Score)
        layout.addWidget(self._build_header())

        # 2. KPIs (Navigation)
        layout.addWidget(self._build_kpis())

        # 3. StackedWidget pour les catégories
        self.stacked_widget = QStackedWidget()
        layout.addWidget(self.stacked_widget, stretch=1)

        self._build_categories()

        # Sélection par défaut
        self._switch_category("cat_atomicite")

    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setStyleSheet(f".QFrame {{ background-color: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: {DesignTokens.RADIUS_MD}px; }}")
        header.setFixedHeight(48)

        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(12, 0, 12, 0)

        # Left
        title = QLabel("Audit Ergonomique Wozniak")
        title.setStyleSheet(f"font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        btn_deck = SecondaryButton("L'ensemble des paquets")
        btn_analyze = PrimaryButton("Analyser ce paquet")

        h_layout.addWidget(title)
        h_layout.addWidget(btn_deck)
        h_layout.addWidget(btn_analyze)
        h_layout.addStretch()

        # Right
        search = StyledLineEdit()
        search.setPlaceholderText("Rechercher une carte...")
        btn_settings = SecondaryButton("Sévérités")

        score_badge = QLabel("Score : 88 / 100")
        score_badge.setStyleSheet(
            f"background-color: rgba(245,158,11,0.12); color: {DesignTokens.COLOR_YELLOW}; font-weight: bold; padding: 4px 8px; border-radius: 4px; border: 1px solid rgba(245,158,11,0.3);"
        )

        h_layout.addWidget(search)
        h_layout.addWidget(btn_settings)
        h_layout.addWidget(score_badge)

        return header

    def _build_kpis(self) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # Création des 4 KPIs basés sur ta maquette
        kpi_data = [
            ("cat_atomicite", "Atomicité & Listes", "72%", "squares-four", "#f87171", "4 cartes complexes"),
            ("cat_katex", "Formules & Clarté", "85%", "function", "#c084fc", "3 corrections KaTeX"),
            ("cat_interference", "Non-Interférence", "90%", "intersect", DesignTokens.COLOR_BLUE, "3 désambiguïsations"),
            ("cat_cloze", "Questions Univoques", "84%", "question", DesignTokens.COLOR_YELLOW, "3 conversions Cloze"),
        ]

        for cat_id, title, score, icon, color, desc in kpi_data:
            card = WozniakKpiCard(cat_id, title, score, icon, color, desc)
            card.clicked.connect(self._switch_category)
            self.kpi_cards[cat_id] = card
            layout.addWidget(card)

        return container

    def _build_categories(self):
        """Construit les 4 pages du QStackedWidget avec leur bannière sticky."""

        # Page 1: Atomicité
        page_atom = self._create_category_page(
            title="Catégorie 1 : Découpage & Restructuration Atomicité", color="#f87171", desc="Types de problèmes : Multi-Questions, Énumération Complexe...", count_text="4 Cartes"
        )
        self.stacked_widget.addWidget(page_atom)

        # Page 2: KaTeX
        page_katex = self._create_category_page(
            title="Catégorie 2 : Formules Mathématiques & Rendu KaTeX", color="#c084fc", desc="Types de problèmes : Formule Texte Brut, Syntaxe LaTeX Cassée...", count_text="3 Cartes"
        )
        # Ajout d'un faux problème KaTeX pour la démo
        scroll_area = page_katex.findChild(QScrollArea)
        scroll_content = scroll_area.widget()
        scroll_content.layout().addWidget(WozniakIssueWidget("Carte #1088 · Égalité de Parseval", "Problème 1 : Texte brut non formaté", "#f87171"))
        scroll_content.layout().addStretch()

        self.stacked_widget.addWidget(page_katex)

        # (Idem pour Interférence et Cloze...)
        self.stacked_widget.addWidget(QWidget())  # Placeholder Interférence
        self.stacked_widget.addWidget(QWidget())  # Placeholder Cloze

    def _create_category_page(self, title: str, color: str, desc: str, count_text: str) -> QWidget:
        """Crée une page avec le Sticky Banner en haut, et un ScrollArea en dessous."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # --- STICKY BANNER (Ne scrolle pas !) ---
        banner = QFrame()
        banner.setStyleSheet(f".QFrame {{ background-color: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: {DesignTokens.RADIUS_MD}px; }}")
        b_layout = QVBoxLayout(banner)

        top_h = QHBoxLayout()
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet(f"font-weight: bold; color: {DesignTokens.TEXT_PRIMARY}; font-size: 13px;")

        lbl_count = QLabel(count_text)
        lbl_count.setStyleSheet(f"background-color: rgba(248, 113, 113, 0.15); color: {color}; font-weight: bold; font-size: 10px; padding: 2px 6px; border-radius: 4px;")

        top_h.addWidget(lbl_title)
        top_h.addStretch()
        top_h.addWidget(lbl_count)
        b_layout.addLayout(top_h)

        lbl_desc = QLabel(desc)
        lbl_desc.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px;")
        b_layout.addWidget(lbl_desc)

        layout.addWidget(banner)

        # --- SCROLL AREA (Pour les cartes malades) ---
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background-color: transparent;")

        scroll_content = QWidget()
        scroll_content.setStyleSheet("background-color: transparent;")
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(10)

        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, stretch=1)

        return page

    @Slot(str)
    def _switch_category(self, cat_id: str):
        """Change la page du StackedWidget et met à jour l'UI des KPIs."""
        # Maj UI KPIs
        for key, card in self.kpi_cards.items():
            card.set_active(key == cat_id)

        # Switch StackedWidget
        mapping = {"cat_atomicite": 0, "cat_katex": 1, "cat_interference": 2, "cat_cloze": 3}
        if cat_id in mapping:
            self.stacked_widget.setCurrentIndex(mapping[cat_id])
