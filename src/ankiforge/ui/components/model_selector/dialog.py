"""
Dialogue modal d'exploration, de découverte et de comparaison des modèles LLM.
Permet d'inspecter les spécifications détaillées, filtrer par capacités et comparer côte à côte.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import LLMConfigModel
from ankiforge.services.ai.model_catalog import ANKIFORGE_TASKS, ModelCatalog, ModelSpec
from ankiforge.ui.components import (
    GlowLineEdit,
    IconButton,
    PrimaryButton,
    SecondaryButton,
)
from ankiforge.ui.components.model_selector.badges import ModelCapabilityBadgesWidget
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class FilterChipButton(QPushButton):
    """Bouton style 'chip' basculable pour les filtres rapides de capacités et fournisseurs."""

    def __init__(
        self,
        text: str,
        icon_name: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(26)
        if icon_name:
            self.setIcon(load_phosphor_icon(icon_name, color=DesignTokens.TEXT_SECONDARY))


class ModelCardWidget(QFrame):
    """Carte visuelle présentant un modèle avec ses spécifications, atouts et cas d'usage."""

    selected = Signal(object)  # ModelSpec or LLMConfigModel
    comparison_toggled = Signal(object, bool)  # (model, is_checked)

    def __init__(
        self,
        model: ModelSpec | LLMConfigModel,
        is_installed: bool = False,
        is_current: bool = False,
        picker_mode: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.model = model
        self.is_installed = is_installed
        self.is_current = is_current
        self.picker_mode = picker_mode

        self.setObjectName("ModelCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if self.is_current:
            self.setProperty("current", "true")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # ── 1. En-tête : Avatar Fournisseur + Nom + Badges de Statut ──
        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        provider = getattr(model, "provider", "").lower()
        prov_icon = "ph.brain"
        prov_bg_color = DesignTokens.BG_INPUT
        prov_fg_color = DesignTokens.TEXT_PRIMARY
        provider_display = getattr(model, "provider", "").upper()

        if provider == "gemini":
            prov_icon = "ph.sparkle"
            prov_fg_color = DesignTokens.COLOR_BLUE
            prov_bg_color = DesignTokens.COLOR_BLUE_BG
            provider_display = "Google"
        elif provider == "anthropic":
            prov_icon = "ph.sparkle"
            prov_fg_color = DesignTokens.COLOR_YELLOW
            prov_bg_color = DesignTokens.COLOR_YELLOW_BG
            provider_display = "Anthropic"
        elif provider == "groq":
            prov_icon = "ph.lightning"
            prov_fg_color = "#06b6d4"
            prov_bg_color = "rgba(6, 182, 212, 0.15)"
            provider_display = "Groq"
        elif provider == "ollama":
            prov_icon = "ph.cpu"
            prov_fg_color = DesignTokens.COLOR_GREEN
            prov_bg_color = DesignTokens.COLOR_GREEN_BG
            provider_display = "Ollama Local"
        elif provider == "openai":
            prov_icon = "ph.brain"
            prov_fg_color = "#10b981"
            prov_bg_color = "rgba(16, 185, 129, 0.15)"
            provider_display = "OpenAI"
        elif provider == "opencode":
            prov_icon = "ph.code"
            prov_fg_color = "#6366f1"
            prov_bg_color = "rgba(99, 102, 241, 0.15)"
            provider_display = "OpenCode"
        elif provider == "openrouter":
            prov_icon = "ph.arrows-split"
            prov_fg_color = "#ec4899"
            prov_bg_color = "rgba(236, 72, 153, 0.15)"
            provider_display = "OpenRouter"

        # Badge rond / capsule pour l'icône du fournisseur
        icon_container = QLabel()
        icon_container.setFixedSize(28, 28)
        icon_container.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_container.setPixmap(load_phosphor_icon(prov_icon, color=prov_fg_color).pixmap(16, 16))
        icon_container.setStyleSheet(f"""
            QLabel {{
                background-color: {prov_bg_color};
                border: 1px solid {prov_fg_color};
                border-radius: 6px;
            }}
        """)
        header_row.addWidget(icon_container)

        # Titre et sous-titre
        title_col = QVBoxLayout()
        title_col.setSpacing(1)
        display_name = getattr(model, "display_name", "") or getattr(model, "model_id", "")
        self.title_lbl = QLabel(display_name)
        self.title_lbl.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        title_col.addWidget(self.title_lbl)

        lbl_prov = QLabel(provider_display)
        lbl_prov.setStyleSheet(f"font-size: 10px; font-weight: 500; color: {DesignTokens.TEXT_MUTED};")
        title_col.addWidget(lbl_prov)
        header_row.addLayout(title_col, 1)

        # Badges de statut
        if self.is_current:
            badge_curr = QLabel("✓ Actuel")
            badge_curr.setStyleSheet(f"""
                QLabel {{
                    background-color: {DesignTokens.COLOR_GREEN_BG};
                    color: {DesignTokens.COLOR_GREEN};
                    font-size: 10px;
                    font-weight: bold;
                    border: 1px solid {DesignTokens.COLOR_GREEN};
                    border-radius: {DesignTokens.RADIUS_SM}px;
                    padding: 2px 8px;
                }}
            """)
            badge_curr.setToolTip("Ce modèle est actuellement sélectionné dans AnkiForge.")
            header_row.addWidget(badge_curr)
        elif self.is_installed:
            badge_inst = QLabel("Configuré")
            badge_inst.setStyleSheet(f"""
                QLabel {{
                    background-color: {DesignTokens.BG_INPUT};
                    color: {DesignTokens.TEXT_MUTED};
                    font-size: 10px;
                    font-weight: 600;
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: {DesignTokens.RADIUS_SM}px;
                    padding: 2px 7px;
                }}
            """)
            badge_inst.setToolTip("Ce modèle est configuré dans votre base de données locale.")
            header_row.addWidget(badge_inst)
        else:
            badge_cat = QLabel("Catalogue")
            badge_cat.setStyleSheet(f"""
                QLabel {{
                    background-color: {DesignTokens.ACCENT_BG};
                    color: {DesignTokens.ACCENT_PRIMARY};
                    font-size: 10px;
                    font-weight: 600;
                    border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                    border-radius: {DesignTokens.RADIUS_SM}px;
                    padding: 2px 7px;
                }}
            """)
            badge_cat.setToolTip("Modèle suggéré du catalogue officiel AnkiForge. Prêt à être activé.")
            header_row.addWidget(badge_cat)

        layout.addLayout(header_row)

        # ── 2. Rangée de Badges de Capacités ──
        self.badges_widget = ModelCapabilityBadgesWidget(compact=False, parent=self)
        self.badges_widget.set_model(model)
        layout.addWidget(self.badges_widget)

        # ── 3. Cas d'usage recommandé & Atouts ──
        use_case_text = getattr(model, "ankiforge_use_case", "") or getattr(model, "description", "")
        if not use_case_text and hasattr(model, "description"):
            use_case_text = str(model.description)

        if use_case_text:
            uc_frame = QFrame()
            uc_frame.setObjectName("ModelCardUseCase")
            uc_layout = QHBoxLayout(uc_frame)
            uc_layout.setContentsMargins(8, 6, 8, 6)
            uc_layout.setSpacing(6)

            bulb_icon = QLabel()
            bulb_icon.setPixmap(load_phosphor_icon("ph.lightbulb", color=DesignTokens.ACCENT_PRIMARY).pixmap(13, 13))
            bulb_icon.setStyleSheet("background: transparent; border: none;")
            uc_layout.addWidget(bulb_icon, 0, Qt.AlignmentFlag.AlignTop)

            self.lbl_use_case = QLabel(use_case_text)
            self.lbl_use_case.setWordWrap(True)
            self.lbl_use_case.setStyleSheet(f"""
                QLabel {{
                    color: {DesignTokens.TEXT_SECONDARY};
                    font-size: 11px;
                    line-height: 1.35;
                    background: transparent;
                    border: none;
                }}
            """)
            uc_layout.addWidget(self.lbl_use_case, 1)
            layout.addWidget(uc_frame)

        layout.addStretch()

        # ── 4. Pied de carte : Bouton Comparer + Bouton d'Action Principal ──
        footer_row = QHBoxLayout()
        footer_row.setSpacing(8)

        # Chip toggle pour comparer
        self.cb_compare = FilterChipButton("Comparer", icon_name="ph.scales", parent=self)
        self.cb_compare.setToolTip("Cocher pour comparer les spécifications avec d'autres modèles.")
        self.cb_compare.toggled.connect(lambda checked: self.comparison_toggled.emit(self.model, checked))
        footer_row.addWidget(self.cb_compare)

        footer_row.addStretch()

        # Libellé et rôle du bouton d'action
        if self.is_current and self.picker_mode:
            self.btn_select = SecondaryButton("✓ Modèle Actif", parent=self)
            self.btn_select.setFixedHeight(32)
            self.btn_select.clicked.connect(lambda: self.selected.emit(self.model))
        elif self.is_installed:
            self.btn_select = PrimaryButton("Sélectionner" if self.picker_mode else "Configuré", parent=self)
            self.btn_select.setFixedHeight(32)
            if not self.picker_mode:
                self.btn_select.setEnabled(False)
            self.btn_select.clicked.connect(lambda: self.selected.emit(self.model))
        else:
            self.btn_select = PrimaryButton("+ Activer & Choisir" if self.picker_mode else "+ Activer", parent=self)
            self.btn_select.setFixedHeight(32)
            self.btn_select.clicked.connect(lambda: self.selected.emit(self.model))

        footer_row.addWidget(self.btn_select)
        layout.addLayout(footer_row)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Double-cliquer sur la carte sélectionne immédiatement le modèle."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(self.model)
        super().mouseDoubleClickEvent(event)


class ModelDiscoveryDialog(QDialog):
    """
    Modale complète d'exploration, de découverte et de comparaison des modèles IA.
    Prend en charge le filtrage par fournisseur, capacités et cas d'usage AnkiForge.
    """

    model_selected = Signal(object)  # ModelSpec or LLMConfigModel

    def __init__(
        self,
        current_model_id: str | None = None,
        current_provider: str | None = None,
        picker_mode: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.current_model_id = current_model_id
        self.current_provider = current_provider
        self.picker_mode = picker_mode
        self._selected_model: Any | None = None
        self._compared_models: list[Any] = []
        self._active_provider: str = "all"

        title_text = "AnkiForge — Sélectionner un Modèle IA" if picker_mode else "AnkiForge — Catalogue & Comparateur des Moteurs IA"
        self.setWindowTitle(title_text)
        self.resize(1040, 720)

        self._setup_ui()
        self._load_and_filter_models()

    def _setup_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(18, 16, 18, 14)
        root_layout.setSpacing(12)

        # ── 1. En-tête : Titre contextuel & Recherche GlowLineEdit ──
        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        icon_header = QLabel()
        icon_name = "ph.sparkle" if self.picker_mode else "ph.squares-four"
        icon_header.setPixmap(load_phosphor_icon(icon_name, color=DesignTokens.ACCENT_PRIMARY).pixmap(24, 24))
        top_row.addWidget(icon_header)

        col_title = QVBoxLayout()
        col_title.setSpacing(2)

        main_title = "Sélectionner un Modèle IA" if self.picker_mode else "Catalogue & Découverte des Modèles IA"
        lbl_h = QLabel(main_title)
        lbl_h.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")

        sub_title = (
            "Choisissez le modèle adapté à votre tâche parmi vos moteurs configurés et le catalogue officiel."
            if self.picker_mode
            else "Explorez les spécifications réelles (Vision, Thinking, Contexte, Tarifs) adaptées aux pipelines AnkiForge."
        )
        lbl_sub = QLabel(sub_title)
        lbl_sub.setStyleSheet(f"font-size: 11.5px; color: {DesignTokens.TEXT_MUTED};")
        col_title.addWidget(lbl_h)
        col_title.addWidget(lbl_sub)
        top_row.addLayout(col_title, 1)

        # Barre de recherche avec action d'effacement
        self.search_edit = GlowLineEdit()
        self.search_edit.setPlaceholderText("Rechercher modèle, fournisseur, tag...")
        self.search_edit.setFixedWidth(260)
        self.search_edit.textChanged.connect(self._load_and_filter_models)
        self.search_edit.setClearButtonEnabled(True)
        top_row.addWidget(self.search_edit)

        root_layout.addLayout(top_row)

        # ── 2. Cadre des Filtres : Fournisseurs + Capacités + Cas d'usage ──
        filter_card = QFrame()
        filter_card.setObjectName("FilterCard")
        filter_layout = QVBoxLayout(filter_card)
        filter_layout.setContentsMargins(12, 10, 12, 10)
        filter_layout.setSpacing(8)

        # Rangée 1 : Filtre Fournisseurs
        row_prov = QHBoxLayout()
        row_prov.setSpacing(6)
        lbl_p = QLabel("Fournisseur :")
        lbl_p.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        row_prov.addWidget(lbl_p)

        self.prov_buttons: dict[str, FilterChipButton] = {}
        providers_meta = [
            ("all", "Tous", "ph.circles-three"),
            ("gemini", "Google Gemini", "ph.sparkle"),
            ("anthropic", "Anthropic Claude", "ph.sparkle"),
            ("openai", "OpenAI", "ph.brain"),
            ("ollama", "Ollama (100% Local)", "ph.cpu"),
            ("groq", "Groq", "ph.lightning"),
            ("opencode", "OpenCode", "ph.code"),
            ("openrouter", "OpenRouter", "ph.arrows-split"),
        ]

        for p_key, p_label, p_icon in providers_meta:
            btn = FilterChipButton(p_label, icon_name=p_icon, parent=filter_card)
            btn.setChecked(p_key == "all")
            btn.clicked.connect(lambda _, k=p_key: self._select_provider_filter(k))
            self.prov_buttons[p_key] = btn
            row_prov.addWidget(btn)

        row_prov.addStretch()
        filter_layout.addLayout(row_prov)

        # Rangée 2 : Filtres Capacités requises & Cas d'usage
        row_caps_tasks = QHBoxLayout()
        row_caps_tasks.setSpacing(8)

        lbl_c = QLabel("Capacités :")
        lbl_c.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        row_caps_tasks.addWidget(lbl_c)

        self.btn_cap_vision = FilterChipButton("Vision multimodale", icon_name="ph.eye", parent=filter_card)
        self.btn_cap_vision.toggled.connect(self._load_and_filter_models)
        row_caps_tasks.addWidget(self.btn_cap_vision)

        self.btn_cap_thinking = FilterChipButton("Thinking / CoT", icon_name="ph.brain", parent=filter_card)
        self.btn_cap_thinking.toggled.connect(self._load_and_filter_models)
        row_caps_tasks.addWidget(self.btn_cap_thinking)

        self.btn_cap_local = FilterChipButton("100% Local (Ollama)", icon_name="ph.shield-check", parent=filter_card)
        self.btn_cap_local.toggled.connect(self._load_and_filter_models)
        row_caps_tasks.addWidget(self.btn_cap_local)

        self.btn_cap_free = FilterChipButton("Gratuit / Inclus", icon_name="ph.coins", parent=filter_card)
        self.btn_cap_free.toggled.connect(self._load_and_filter_models)
        row_caps_tasks.addWidget(self.btn_cap_free)

        # Séparateur vertical subtil
        sep = QLabel("|")
        sep.setStyleSheet(f"color: {DesignTokens.BORDER_COLOR}; font-weight: bold;")
        row_caps_tasks.addWidget(sep)

        # Menu déroulant compact pour les cas d'usage AnkiForge
        lbl_t = QLabel("Cas d'usage :")
        lbl_t.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        row_caps_tasks.addWidget(lbl_t)

        self.btn_task_all = FilterChipButton("Tous les cas", parent=filter_card)
        self.btn_task_all.setChecked(True)
        self.btn_task_all.clicked.connect(lambda: self._select_task_filter("all"))
        row_caps_tasks.addWidget(self.btn_task_all)

        self.task_buttons: dict[str, FilterChipButton] = {}
        for t_key, t_info in ANKIFORGE_TASKS.items():
            btn_t = FilterChipButton(t_info["label"], icon_name=t_info.get("icon", "ph.sparkle"), parent=filter_card)
            btn_t.clicked.connect(lambda _, k=t_key: self._select_task_filter(k))
            self.task_buttons[t_key] = btn_t
            row_caps_tasks.addWidget(btn_t)

        row_caps_tasks.addStretch()
        filter_layout.addLayout(row_caps_tasks)

        root_layout.addWidget(filter_card)

        # ── 3. Zone Centrale : Grille de Cartes & Volet Comparateur ──
        self.main_splitter = QSplitter(Qt.Orientation.Vertical)
        self.main_splitter.setChildrenCollapsible(False)

        # Zone de défilement des cartes
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setStyleSheet("QScrollArea { background: transparent; border: none; } QScrollArea > QWidget > QWidget { background: transparent; }")

        self.cards_container = QWidget()
        self.cards_grid = QGridLayout(self.cards_container)
        self.cards_grid.setContentsMargins(0, 4, 0, 4)
        self.cards_grid.setSpacing(12)
        self.cards_grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.cards_grid.setColumnStretch(0, 1)
        self.cards_grid.setColumnStretch(1, 1)
        self.scroll_area.setWidget(self.cards_container)

        self.main_splitter.addWidget(self.scroll_area)

        # Volet de comparaison côte à côte (rétractable)
        self.compare_pane = QFrame()
        self.compare_pane.setObjectName("ComparePane")
        self.compare_layout = QVBoxLayout(self.compare_pane)
        self.compare_layout.setContentsMargins(12, 10, 12, 10)
        self.compare_layout.setSpacing(8)

        header_comp = QHBoxLayout()
        icon_comp = QLabel()
        icon_comp.setPixmap(load_phosphor_icon("ph.scales", color=DesignTokens.ACCENT_PRIMARY).pixmap(18, 18))
        header_comp.addWidget(icon_comp)

        self.lbl_comp_title = QLabel("Comparateur de Modèles Côte-à-Côte (2 à 3 modèles)")
        self.lbl_comp_title.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {DesignTokens.ACCENT_PRIMARY};")
        header_comp.addWidget(self.lbl_comp_title)
        header_comp.addStretch()

        btn_clear_comp = SecondaryButton("Vider la sélection")
        btn_clear_comp.setFixedHeight(26)
        btn_clear_comp.setIcon(load_phosphor_icon("ph.trash", color=DesignTokens.TEXT_MUTED))
        btn_clear_comp.clicked.connect(self._clear_comparison)
        header_comp.addWidget(btn_clear_comp)

        btn_close_comp = IconButton("ph.x", "Fermer le comparateur", 24)
        btn_close_comp.clicked.connect(self._clear_comparison)
        header_comp.addWidget(btn_close_comp)

        self.compare_layout.addLayout(header_comp)

        self.compare_table_row = QHBoxLayout()
        self.compare_table_row.setSpacing(10)
        self.compare_layout.addLayout(self.compare_table_row)

        self.compare_pane.hide()
        self.main_splitter.addWidget(self.compare_pane)

        root_layout.addWidget(self.main_splitter, 1)

        # ── 4. Pied de Page : Compteur de résultats & Bouton Fermer ──
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(12)

        self.lbl_status = QLabel("Chargement des modèles...")
        self.lbl_status.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11.5px;")
        bottom_row.addWidget(self.lbl_status)

        bottom_row.addStretch()

        btn_cancel = SecondaryButton("Fermer" if not self.picker_mode else "Annuler")
        btn_cancel.setFixedWidth(100)
        btn_cancel.clicked.connect(self.reject)
        bottom_row.addWidget(btn_cancel)

        root_layout.addLayout(bottom_row)

    def _select_provider_filter(self, selected_key: str) -> None:
        """Gère l'exclusivité visuelle des filtres de fournisseurs."""
        self._active_provider = selected_key
        for k, btn in self.prov_buttons.items():
            btn.setChecked(k == selected_key)
        self._load_and_filter_models()

    def _select_task_filter(self, selected_key: str) -> None:
        """Gère l'exclusivité visuelle des filtres de cas d'usage."""
        self.btn_task_all.setChecked(selected_key == "all")
        for k, btn in self.task_buttons.items():
            btn.setChecked(k == selected_key)
        self._load_and_filter_models()

    def _get_active_task_filter(self) -> str:
        for k, btn in self.task_buttons.items():
            if btn.isChecked():
                return k
        return "all"

    def _reset_all_filters(self) -> None:
        """Réinitialise tous les filtres de recherche."""
        self.search_edit.clear()
        self._select_provider_filter("all")
        self._select_task_filter("all")
        self.btn_cap_vision.setChecked(False)
        self.btn_cap_thinking.setChecked(False)
        self.btn_cap_local.setChecked(False)
        self.btn_cap_free.setChecked(False)
        self._load_and_filter_models()

    def _load_and_filter_models(self) -> None:
        """Filtre les modèles du catalogue et les affiche sous forme de grille responsive."""
        # Nettoyage de la grille
        while self.cards_grid.count():
            item = self.cards_grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()

        # Récupération des modèles installés en base SQLite
        installed_configs = list(LLMConfigModel.select().order_by(LLMConfigModel.sort_order.asc()))
        installed_model_ids = {f"{c.provider.lower()}:{c.model_id.lower()}" for c in installed_configs}

        # Catalogue officiel enrichi
        curated_catalog = ModelCatalog.get_curated_catalog()

        # Fusion : installés d'abord, puis modèles catalogue restants
        all_models: list[tuple[Any, bool]] = []
        for cfg in installed_configs:
            all_models.append((cfg, True))

        for spec in curated_catalog:
            key = f"{spec.provider.lower()}:{spec.model_id.lower()}"
            if key not in installed_model_ids:
                all_models.append((spec, False))

        # Application des critères de filtrage
        query = self.search_edit.text().strip().lower()
        active_task = self._get_active_task_filter()
        req_vision = self.btn_cap_vision.isChecked()
        req_thinking = self.btn_cap_thinking.isChecked()
        req_local = self.btn_cap_local.isChecked()
        req_free = self.btn_cap_free.isChecked()
        active_prov = self._active_provider

        filtered: list[tuple[Any, bool]] = []
        for model, is_inst in all_models:
            display_name = getattr(model, "display_name", "") or getattr(model, "model_id", "")
            provider = getattr(model, "provider", "").lower()
            model_id = getattr(model, "model_id", "")

            # Filtre Fournisseur
            if active_prov != "all" and provider != active_prov:
                continue

            # Filtre texte
            if query and not (query in display_name.lower() or query in provider or query in model_id.lower()):
                continue

            # Filtre cas d'usage
            tasks = getattr(model, "recommended_tasks_list", None) or getattr(model, "recommended_tasks", [])
            if active_task != "all" and active_task not in tasks:
                continue

            # Filtres capacités
            if req_vision and not getattr(model, "supports_vision", False):
                continue
            if req_thinking and not getattr(model, "supports_thinking", False):
                continue
            if req_local and provider != "ollama":
                continue
            if req_free and not (getattr(model, "is_free", False) or provider == "ollama"):
                continue

            filtered.append((model, is_inst))

        # Disposition en 2 colonnes
        curr_str = str(self.current_model_id or "").strip()
        curr_prov = str(self.current_provider or "").strip().lower()

        # Identifier si un modèle installé correspond déjà au modèle actuel demandé
        installed_matched = False
        if curr_str:
            for cfg in installed_configs:
                cfg_mid = str(getattr(cfg, "model_id", ""))
                cfg_prov = str(getattr(cfg, "provider", "")).lower()
                cfg_id = str(getattr(cfg, "id", ""))
                if cfg_id == curr_str or f"{cfg_prov}:{cfg_mid.lower()}" == curr_str.lower() or (cfg_mid.lower() == curr_str.lower() and (not curr_prov or cfg_prov == curr_prov)):
                    installed_matched = True
                    break

        matched_catalog_current = False
        for idx, (model, is_inst) in enumerate(filtered):
            m_id = str(getattr(model, "model_id", ""))
            prov = str(getattr(model, "provider", "")).lower()

            if not curr_str:
                is_curr = False
            elif is_inst:
                is_curr = bool(
                    (hasattr(model, "id") and str(model.id) == curr_str) or f"{prov}:{m_id.lower()}" == curr_str.lower() or (m_id.lower() == curr_str.lower() and (not curr_prov or prov == curr_prov))
                )
            else:
                # Modèle catalogue non installé : ne peut être actuel que si aucun modèle installé ne correspond
                if installed_matched or matched_catalog_current:
                    is_curr = False
                elif f"{prov}:{m_id.lower()}" == curr_str.lower():
                    is_curr = True
                    matched_catalog_current = True
                elif m_id.lower() == curr_str.lower() and (not curr_prov or prov == curr_prov):
                    # Si aucun provider spécifié, éviter qu'un proxy opencode usurpe le modèle originel
                    if (
                        not curr_prov
                        and prov not in m_id.lower()
                        and any(getattr(other_m, "provider", "").lower() in m_id.lower() for other_m, other_inst in filtered if str(getattr(other_m, "model_id", "")).lower() == m_id.lower())
                    ):
                        is_curr = False
                    else:
                        is_curr = True
                        matched_catalog_current = True
                else:
                    is_curr = False

            card = ModelCardWidget(
                model=model,
                is_installed=is_inst,
                is_current=is_curr,
                picker_mode=self.picker_mode,
                parent=self.cards_container,
            )
            card.selected.connect(self._on_model_chosen)
            card.comparison_toggled.connect(self._on_comparison_toggled)

            # Rétablir l'état de comparaison si actif
            if any(getattr(m, "model_id", None) == m_id for m in self._compared_models):
                card.cb_compare.setChecked(True)

            row = idx // 2
            col = idx % 2
            self.cards_grid.addWidget(card, row, col)
            card.show()

        # État vide (Empty State)
        if not filtered:
            empty_container = QFrame()
            empty_layout = QVBoxLayout(empty_container)
            empty_layout.setContentsMargins(24, 40, 24, 40)
            empty_layout.setSpacing(10)
            empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            icon_empty = QLabel()
            icon_empty.setPixmap(load_phosphor_icon("ph.magnifying-glass", color=DesignTokens.TEXT_MUTED).pixmap(36, 36))
            icon_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_layout.addWidget(icon_empty)

            lbl_empty_title = QLabel("Aucun modèle ne correspond à vos critères")
            lbl_empty_title.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
            lbl_empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_layout.addWidget(lbl_empty_title)

            lbl_empty_sub = QLabel("Essayez d'élargir votre recherche ou de réinitialiser les filtres appliqués.")
            lbl_empty_sub.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 12px;")
            lbl_empty_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_layout.addWidget(lbl_empty_sub)

            btn_reset = SecondaryButton("Réinitialiser les filtres")
            btn_reset.setFixedWidth(160)
            btn_reset.clicked.connect(self._reset_all_filters)
            empty_layout.addWidget(btn_reset, 0, Qt.AlignmentFlag.AlignCenter)

            self.cards_grid.addWidget(empty_container, 0, 0, 1, 2)

        # Mise à jour du compteur en bas à gauche
        inst_count = len(installed_configs)
        tot_count = len(all_models)
        filt_count = len(filtered)
        self.lbl_status.setText(f"Affichage de {filt_count} modèle(s) sur {tot_count} au catalogue · {inst_count} configuré(s)")

    def _on_model_chosen(self, model: Any) -> None:
        """Gère la sélection ou l'activation d'un modèle."""
        if not isinstance(model, LLMConfigModel):
            # C'est une ModelSpec provenant du catalogue : on l'enregistre en base SQLite
            spec: ModelSpec = model
            existing = LLMConfigModel.select().where((LLMConfigModel.provider == spec.provider) & (LLMConfigModel.model_id == spec.model_id)).first()
            if not existing:
                import json

                tasks_json = json.dumps(spec.recommended_tasks)
                cfg = LLMConfigModel.create(
                    display_name=spec.display_name,
                    provider=spec.provider,
                    model_id=spec.model_id,
                    context_limit=spec.context_window,
                    max_tokens=spec.max_tokens,
                    prompt_pricing=spec.prompt_pricing,
                    completion_pricing=spec.completion_pricing,
                    is_free=spec.is_free,
                    supports_vision=spec.supports_vision,
                    supports_thinking=spec.supports_thinking,
                    supports_json=spec.supports_json,
                    speed_rating=spec.speed_rating,
                    quality_tier=spec.quality_tier,
                    recommended_tasks=tasks_json,
                    description=spec.ankiforge_use_case or spec.description,
                )
                self._selected_model = cfg
            else:
                self._selected_model = existing
        else:
            self._selected_model = model

        self.model_selected.emit(self._selected_model)
        self.accept()

    def _on_comparison_toggled(self, model: Any, checked: bool) -> None:
        """Ajoute ou retire un modèle de la liste de comparaison."""
        if checked:
            if model not in self._compared_models:
                self._compared_models.append(model)
        else:
            if model in self._compared_models:
                self._compared_models.remove(model)

        self._render_comparison_pane()

    def _clear_comparison(self) -> None:
        """Réinitialise les comparaisons actives."""
        self._compared_models.clear()
        self.compare_pane.hide()
        for i in range(self.cards_grid.count()):
            w = self.cards_grid.itemAt(i).widget()
            if isinstance(w, ModelCardWidget):
                w.cb_compare.setChecked(False)

    def _render_comparison_pane(self) -> None:
        """Affiche le tableau comparatif côte à côte si au moins 2 modèles sont sélectionnés."""
        while self.compare_table_row.count():
            item = self.compare_table_row.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()

        if len(self._compared_models) < 2:
            self.compare_pane.hide()
            return

        self.compare_pane.show()

        # Identifier le modèle avec le plus grand contexte et le plus économique
        max_ctx = max(int(getattr(m, "context_limit", None) or getattr(m, "context_window", 0) or 0) for m in self._compared_models[:3])
        min_price = min(float(getattr(m, "prompt_pricing", 0.0) or 0.0) for m in self._compared_models[:3])

        for model in self._compared_models[:3]:  # Max 3 modèles en simultané
            col_card = QFrame()
            col_card.setObjectName("CompareModelColumn")
            col_layout = QVBoxLayout(col_card)
            col_layout.setContentsMargins(10, 8, 10, 8)
            col_layout.setSpacing(6)

            display_name = getattr(model, "display_name", "") or getattr(model, "model_id", "")
            lbl_name = QLabel(display_name)
            lbl_name.setStyleSheet(f"font-weight: bold; color: {DesignTokens.TEXT_PRIMARY}; font-size: 12.5px;")
            col_layout.addWidget(lbl_name)

            # Métriques comparatives
            ctx = getattr(model, "context_limit", None) or getattr(model, "context_window", 128000)
            ctx_str = f"{ctx // 1000}k" if ctx < 1000000 else f"{ctx / 1000000:.1f}M"

            vis_text = "Oui" if getattr(model, "supports_vision", False) else "Non"
            think_text = "Oui (CoT)" if getattr(model, "supports_thinking", False) else "—"
            speed = getattr(model, "speed_rating", "fast")

            p_price = float(getattr(model, "prompt_pricing", 0.0) or 0.0)
            is_free_val = getattr(model, "is_free", False) or getattr(model, "provider", "") == "ollama"
            cost_str = "100% Gratuit" if is_free_val else f"${p_price:.2f}/1M"

            c_price = float(getattr(model, "completion_pricing", 0.0) or 0.0)
            est_100_cards = (50000 / 1_000_000 * p_price) + (10000 / 1_000_000 * c_price)
            est_str = "0.00 $" if est_100_cards == 0 else f"~{est_100_cards:.4f} $"

            is_max_ctx = ctx == max_ctx and max_ctx > 0
            is_best_price = p_price == min_price or is_free_val

            details = [
                ("Contexte", f"{ctx_str} tokens" + (" ⭐ Atout" if is_max_ctx else "")),
                ("Vision", vis_text),
                ("Thinking CoT", think_text),
                ("Vitesse", speed),
                ("Tarif / 1M", cost_str + (" 🪙 Économique" if is_best_price else "")),
                ("Coût 100 cartes", est_str),
            ]

            for label, val in details:
                row_metric = QHBoxLayout()
                lbl_k = QLabel(f"{label} :")
                lbl_k.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_MUTED};")
                lbl_v = QLabel(val)
                val_color = DesignTokens.COLOR_GREEN if ("⭐" in val or "🪙" in val or "Oui" in val) else DesignTokens.TEXT_PRIMARY
                lbl_v.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {val_color};")
                row_metric.addWidget(lbl_k)
                row_metric.addStretch()
                row_metric.addWidget(lbl_v)
                col_layout.addLayout(row_metric)

            btn_pick = PrimaryButton("Sélectionner ce modèle")
            btn_pick.setFixedHeight(30)
            btn_pick.clicked.connect(lambda _, m=model: self._on_model_chosen(m))
            col_layout.addWidget(btn_pick)

            self.compare_table_row.addWidget(col_card)

    def get_selected_model(self) -> Any | None:
        """Retourne le modèle sélectionné."""
        return self._selected_model


__all__ = ["FilterChipButton", "ModelCardWidget", "ModelDiscoveryDialog"]
