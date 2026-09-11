"""
Dialogue modal d'exploration, de découverte et de comparaison des modèles LLM.
Permet d'inspecter les spécifications détaillées, filtrer par capacités et comparer côte à côte.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import LLMConfigModel
from ankiforge.services.ai.model_catalog import ANKIFORGE_TASKS, ModelCatalog, ModelSpec
from ankiforge.ui.components import (
    IconButton,
    PrimaryButton,
    SecondaryButton,
    StyledLineEdit,
)
from ankiforge.ui.components.model_selector.badges import ModelCapabilityBadgesWidget
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class ModelCardWidget(QFrame):
    """Carte visuelle présentant un modèle avec ses spécifications et cas d'usage."""

    selected = Signal(object)  # ModelSpec or LLMConfigModel
    comparison_toggled = Signal(object, bool)  # (model, is_checked)

    def __init__(
        self,
        model: ModelSpec | LLMConfigModel,
        is_installed: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.model = model
        self.is_installed = is_installed

        self.setObjectName("ModelCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            QFrame#ModelCard {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 10px;
            }}
            QFrame#ModelCard:hover {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
                background-color: {DesignTokens.BG_HOVER};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # ── En-tête : Icône Fournisseur + Nom + Badge de Statut ──
        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        provider = getattr(model, "provider", "").lower()
        prov_icon = "ph.brain"
        prov_color = DesignTokens.TEXT_PRIMARY
        if provider == "gemini":
            prov_icon = "ph.sparkle"
            prov_color = DesignTokens.COLOR_BLUE
        elif provider == "anthropic":
            prov_icon = "ph.sparkle"
            prov_color = DesignTokens.COLOR_YELLOW
        elif provider == "groq":
            prov_icon = "ph.lightning"
            prov_color = DesignTokens.COLOR_GREEN
        elif provider == "ollama":
            prov_icon = "ph.cpu"
            prov_color = DesignTokens.COLOR_GREEN

        icon_lbl = QLabel()
        icon_lbl.setPixmap(load_phosphor_icon(prov_icon, color=prov_color).pixmap(18, 18))
        header_row.addWidget(icon_lbl)

        display_name = getattr(model, "display_name", "") or getattr(model, "model_id", "")
        self.title_lbl = QLabel(display_name)
        self.title_lbl.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        header_row.addWidget(self.title_lbl, 1)

        if is_installed:
            badge_inst = QLabel("Configuré")
            badge_inst.setStyleSheet(f"""
                QLabel {{
                    background-color: {DesignTokens.BG_ACTIVE};
                    color: {DesignTokens.COLOR_GREEN};
                    font-size: 10px;
                    font-weight: bold;
                    border: 1px solid {DesignTokens.COLOR_GREEN};
                    border-radius: {DesignTokens.RADIUS_SM}px;
                    padding: 1px 6px;
                }}
            """)
            header_row.addWidget(badge_inst)

        layout.addLayout(header_row)

        # ── Rangée de Badges de Capacités ──
        self.badges_widget = ModelCapabilityBadgesWidget(compact=False, parent=self)
        self.badges_widget.set_model(model)
        layout.addWidget(self.badges_widget)

        # ── Cas d'usage recommandé dans AnkiForge ──
        use_case_text = getattr(model, "ankiforge_use_case", "") or getattr(model, "description", "")
        if not use_case_text and hasattr(model, "description"):
            use_case_text = str(model.description)

        if use_case_text:
            uc_frame = QFrame()
            uc_frame.setStyleSheet(f"""
                QFrame {{
                    background-color: {DesignTokens.BG_INPUT};
                    border: 1px dashed {DesignTokens.BORDER_COLOR};
                    border-radius: {DesignTokens.RADIUS_SM}px;
                }}
            """)
            uc_layout = QHBoxLayout(uc_frame)
            uc_layout.setContentsMargins(6, 6, 6, 6)
            uc_layout.setSpacing(6)

            bulb_icon = QLabel()
            bulb_icon.setPixmap(load_phosphor_icon("ph.lightbulb", color=DesignTokens.TEXT_MUTED).pixmap(14, 14))
            bulb_icon.setStyleSheet("background: transparent; border: none;")
            uc_layout.addWidget(bulb_icon, 0, Qt.AlignmentFlag.AlignTop)

            self.lbl_use_case = QLabel(use_case_text)
            self.lbl_use_case.setWordWrap(True)
            self.lbl_use_case.setStyleSheet(f"""
                QLabel {{
                    color: {DesignTokens.TEXT_SECONDARY};
                    font-size: 11px;
                    line-height: 1.3;
                    background: transparent;
                    border: none;
                }}
            """)
            uc_layout.addWidget(self.lbl_use_case, 1)
            layout.addWidget(uc_frame)

        layout.addStretch()

        # ── Pied de carte : Case Comparer + Bouton Choisir ──
        footer_row = QHBoxLayout()
        footer_row.setSpacing(6)

        self.cb_compare = QCheckBox("Comparer")
        self.cb_compare.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        self.cb_compare.toggled.connect(lambda checked: self.comparison_toggled.emit(self.model, checked))
        footer_row.addWidget(self.cb_compare)

        footer_row.addStretch()

        self.btn_select = PrimaryButton("Choisir ce modèle" if is_installed else "+ Activer")
        self.btn_select.setFixedHeight(26)
        self.btn_select.clicked.connect(lambda: self.selected.emit(self.model))
        footer_row.addWidget(self.btn_select)

        layout.addLayout(footer_row)


class ModelDiscoveryDialog(QDialog):
    """
    Modale complète d'exploration, de découverte et de comparaison des modèles IA.
    """

    model_selected = Signal(object)  # ModelSpec or LLMConfigModel

    def __init__(
        self,
        current_model_id: str | None = None,
        picker_mode: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.current_model_id = current_model_id
        self.picker_mode = picker_mode
        self._selected_model: Any | None = None
        self._compared_models: list[Any] = []

        self.setWindowTitle("AnkiForge — Découverte & Comparateur des Moteurs IA")
        self.resize(980, 680)
        self.setStyleSheet(f"background-color: {DesignTokens.BG_MAIN};")

        self._setup_ui()
        self._load_and_filter_models()

    def _setup_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(18, 16, 18, 16)
        root_layout.setSpacing(12)

        # ── 1. En-tête : Titre & Barre de recherche ──
        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        icon_header = QLabel()
        icon_header.setPixmap(load_phosphor_icon("ph.sparkle", color=DesignTokens.ACCENT_PRIMARY).pixmap(24, 24))
        top_row.addWidget(icon_header)

        col_title = QVBoxLayout()
        col_title.setSpacing(2)
        lbl_h = QLabel("Découverte & Spécifications des Modèles IA")
        lbl_h.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        lbl_sub = QLabel("Explorez les capacités réelles (Vision, Thinking, Contexte, Coût) adaptées à chaque tâche AnkiForge.")
        lbl_sub.setStyleSheet(f"font-size: 11.5px; color: {DesignTokens.TEXT_MUTED};")
        col_title.addWidget(lbl_h)
        col_title.addWidget(lbl_sub)
        top_row.addLayout(col_title, 1)

        self.search_edit = StyledLineEdit()
        self.search_edit.setPlaceholderText("Rechercher un modèle ou fournisseur...")
        self.search_edit.setFixedWidth(240)
        self.search_edit.textChanged.connect(self._load_and_filter_models)
        top_row.addWidget(self.search_edit)

        root_layout.addLayout(top_row)

        # ── 2. Ruban des Filtres par Tâche & Capacités ──
        filter_card = QFrame()
        filter_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 4px;
            }}
        """)
        filter_layout = QVBoxLayout(filter_card)
        filter_layout.setContentsMargins(10, 8, 10, 8)
        filter_layout.setSpacing(6)

        # Ligne Tâches
        row_tasks = QHBoxLayout()
        row_tasks.setSpacing(6)
        lbl_t = QLabel("Cas d'usage :")
        lbl_t.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        row_tasks.addWidget(lbl_t)

        self.btn_task_all = SecondaryButton("Tous")
        self.btn_task_all.setIcon(load_phosphor_icon("ph.squares-four", color=DesignTokens.TEXT_SECONDARY))
        self.btn_task_all.setCheckable(True)
        self.btn_task_all.setChecked(True)
        self.btn_task_all.setFixedHeight(24)
        self.btn_task_all.clicked.connect(lambda: self._select_task_filter("all"))
        row_tasks.addWidget(self.btn_task_all)

        self.task_buttons: dict[str, SecondaryButton] = {}
        for t_key, t_info in ANKIFORGE_TASKS.items():
            btn = SecondaryButton(t_info["label"])
            btn.setIcon(load_phosphor_icon(t_info.get("icon", "ph.sparkle"), color=DesignTokens.TEXT_SECONDARY))
            btn.setCheckable(True)
            btn.setFixedHeight(24)
            btn.clicked.connect(lambda _, k=t_key: self._select_task_filter(k))
            self.task_buttons[t_key] = btn
            row_tasks.addWidget(btn)

        row_tasks.addStretch()
        filter_layout.addLayout(row_tasks)

        # Ligne Filtres Capacités
        row_caps = QHBoxLayout()
        row_caps.setSpacing(10)
        lbl_c = QLabel("Capacités requises :")
        lbl_c.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        row_caps.addWidget(lbl_c)

        self.cb_req_vision = QCheckBox("Vision multimodale")
        self.cb_req_vision.setIcon(load_phosphor_icon("ph.eye", color=DesignTokens.TEXT_SECONDARY))
        self.cb_req_vision.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11.5px;")
        self.cb_req_vision.toggled.connect(self._load_and_filter_models)
        row_caps.addWidget(self.cb_req_vision)

        self.cb_req_thinking = QCheckBox("Thinking / CoT")
        self.cb_req_thinking.setIcon(load_phosphor_icon("ph.brain", color=DesignTokens.TEXT_SECONDARY))
        self.cb_req_thinking.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11.5px;")
        self.cb_req_thinking.toggled.connect(self._load_and_filter_models)
        row_caps.addWidget(self.cb_req_thinking)

        self.cb_req_local = QCheckBox("100% Local (Ollama)")
        self.cb_req_local.setIcon(load_phosphor_icon("ph.shield-check", color=DesignTokens.TEXT_SECONDARY))
        self.cb_req_local.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11.5px;")
        self.cb_req_local.toggled.connect(self._load_and_filter_models)
        row_caps.addWidget(self.cb_req_local)

        self.cb_req_free = QCheckBox("Gratuit / Inclus")
        self.cb_req_free.setIcon(load_phosphor_icon("ph.tag", color=DesignTokens.TEXT_SECONDARY))
        self.cb_req_free.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11.5px;")
        self.cb_req_free.toggled.connect(self._load_and_filter_models)
        row_caps.addWidget(self.cb_req_free)

        row_caps.addStretch()
        filter_layout.addLayout(row_caps)

        root_layout.addWidget(filter_card)

        # ── 3. Zone Centrale : Grille de Cartes & Panneau Comparateur ──
        self.main_splitter = QSplitter(Qt.Orientation.Vertical)

        # Zone de défilement des cartes
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setStyleSheet("background: transparent; border: none;")

        self.cards_container = QWidget()
        self.cards_grid = QGridLayout(self.cards_container)
        self.cards_grid.setContentsMargins(0, 4, 0, 4)
        self.cards_grid.setSpacing(10)
        self.scroll_area.setWidget(self.cards_container)

        self.main_splitter.addWidget(self.scroll_area)

        # Volet de comparaison côte à côte (rétractable)
        self.compare_pane = QFrame()
        self.compare_pane.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border-top: 2px solid {DesignTokens.ACCENT_PRIMARY};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 8px;
            }}
        """)
        self.compare_layout = QVBoxLayout(self.compare_pane)
        self.compare_layout.setContentsMargins(10, 8, 10, 8)
        self.compare_layout.setSpacing(6)

        header_comp = QHBoxLayout()
        icon_comp = QLabel()
        icon_comp.setPixmap(load_phosphor_icon("ph.scales", color=DesignTokens.ACCENT_PRIMARY).pixmap(16, 16))
        header_comp.addWidget(icon_comp)

        lbl_comp_title = QLabel("Comparateur de Modèles Côte-à-Côte")
        lbl_comp_title.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {DesignTokens.ACCENT_PRIMARY};")
        header_comp.addWidget(lbl_comp_title)
        header_comp.addStretch()

        btn_clear_comp = IconButton("ph.x", "Fermer la comparaison", 14)
        btn_clear_comp.clicked.connect(self._clear_comparison)
        header_comp.addWidget(btn_clear_comp)
        self.compare_layout.addLayout(header_comp)

        self.compare_table_row = QHBoxLayout()
        self.compare_table_row.setSpacing(8)
        self.compare_layout.addLayout(self.compare_table_row)

        self.compare_pane.hide()
        self.main_splitter.addWidget(self.compare_pane)

        root_layout.addWidget(self.main_splitter, 1)

        # ── 4. Pied de Page : Fermer ──
        bottom_row = QHBoxLayout()
        bottom_row.addStretch()
        btn_close = SecondaryButton("Fermer")
        btn_close.clicked.connect(self.reject)
        bottom_row.addWidget(btn_close)
        root_layout.addLayout(bottom_row)

    def _select_task_filter(self, selected_key: str) -> None:
        """Gère l'exclusivité visuelle des filtres de tâches."""
        self.btn_task_all.setChecked(selected_key == "all")
        for k, btn in self.task_buttons.items():
            btn.setChecked(k == selected_key)
        self._load_and_filter_models()

    def _get_active_task_filter(self) -> str:
        for k, btn in self.task_buttons.items():
            if btn.isChecked():
                return k
        return "all"

    def _load_and_filter_models(self) -> None:
        """Filtre les modèles du catalogue et les affiche sous forme de grille responsive."""
        # Nettoyage de la grille
        while self.cards_grid.count():
            item = self.cards_grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        # Récupération des modèles installés en base SQLite
        installed_configs = list(LLMConfigModel.select().order_by(LLMConfigModel.sort_order.asc()))
        installed_model_ids = {f"{c.provider.lower()}:{c.model_id.lower()}" for c in installed_configs}

        # Catalogue officiel enrichi
        curated_catalog = ModelCatalog.get_curated_catalog()

        # Fusion des modèles : installed d'abord, puis catalogue
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
        req_vision = self.cb_req_vision.isChecked()
        req_thinking = self.cb_req_thinking.isChecked()
        req_local = self.cb_req_local.isChecked()
        req_free = self.cb_req_free.isChecked()

        filtered: list[tuple[Any, bool]] = []
        for model, is_inst in all_models:
            display_name = getattr(model, "display_name", "") or getattr(model, "model_id", "")
            provider = getattr(model, "provider", "")
            model_id = getattr(model, "model_id", "")

            # Filtre texte
            if query and not (query in display_name.lower() or query in provider.lower() or query in model_id.lower()):
                continue

            # Filtre tâche
            tasks = getattr(model, "recommended_tasks_list", None) or getattr(model, "recommended_tasks", [])
            if active_task != "all" and active_task not in tasks:
                continue

            # Filtres capacités
            if req_vision and not getattr(model, "supports_vision", False):
                continue
            if req_thinking and not getattr(model, "supports_thinking", False):
                continue
            if req_local and provider.lower() != "ollama":
                continue
            if req_free and not (getattr(model, "is_free", False) or provider.lower() == "ollama"):
                continue

            filtered.append((model, is_inst))

        # Disposition en 2 colonnes
        for idx, (model, is_inst) in enumerate(filtered):
            card = ModelCardWidget(model, is_installed=is_inst, parent=self.cards_container)
            card.selected.connect(self._on_model_chosen)
            card.comparison_toggled.connect(self._on_comparison_toggled)

            row = idx // 2
            col = idx % 2
            self.cards_grid.addWidget(card, row, col)

        if not filtered:
            lbl_empty = QLabel("Aucun modèle ne correspond aux filtres sélectionnés.")
            lbl_empty.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 12px; padding: 20px;")
            lbl_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.cards_grid.addWidget(lbl_empty, 0, 0, 1, 2)

    def _on_model_chosen(self, model: Any) -> None:
        """Gère la sélection ou l'installation d'un modèle."""
        if not isinstance(model, LLMConfigModel):
            # C'est une ModelSpec provenant du catalogue : on l'enregistre en BDD
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
        self._compared_models.clear()
        self.compare_pane.hide()
        # Décocher visuellement
        for i in range(self.cards_grid.count()):
            w = self.cards_grid.itemAt(i).widget()
            if isinstance(w, ModelCardWidget):
                w.cb_compare.setChecked(False)

    def _render_comparison_pane(self) -> None:
        """Affiche le tableau comparatif côte à côte si au moins 2 modèles sont sélectionnés."""
        # Nettoyage
        while self.compare_table_row.count():
            item = self.compare_table_row.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        if len(self._compared_models) < 2:
            self.compare_pane.hide()
            return

        self.compare_pane.show()

        for model in self._compared_models[:3]:  # Max 3 modèles en simultané
            col_card = QFrame()
            col_card.setStyleSheet(f"""
                QFrame {{
                    background-color: {DesignTokens.BG_INPUT};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: {DesignTokens.RADIUS_SM}px;
                    padding: 8px;
                }}
            """)
            col_layout = QVBoxLayout(col_card)
            col_layout.setContentsMargins(8, 6, 8, 6)
            col_layout.setSpacing(4)

            display_name = getattr(model, "display_name", "") or getattr(model, "model_id", "")
            lbl_name = QLabel(display_name)
            lbl_name.setStyleSheet(f"font-weight: bold; color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px;")
            col_layout.addWidget(lbl_name)

            # Métriques comparatives
            ctx = getattr(model, "context_limit", None) or getattr(model, "context_window", 128000)
            ctx_str = f"{ctx // 1000}k" if ctx < 1000000 else f"{ctx / 1000000:.1f}M"

            vis_text = "Oui" if getattr(model, "supports_vision", False) else "Non"
            think_text = "Oui (CoT)" if getattr(model, "supports_thinking", False) else "—"
            speed = getattr(model, "speed_rating", "fast")

            p_price = float(getattr(model, "prompt_pricing", 0.0) or 0.0)
            cost_str = "100% Gratuit" if getattr(model, "is_free", False) or getattr(model, "provider", "") == "ollama" else f"${p_price:.2f}/1M"

            # Coût estimé pour 100 cartes (~50k tokens in, 10k out)
            c_price = float(getattr(model, "completion_pricing", 0.0) or 0.0)
            est_100_cards = (50000 / 1_000_000 * p_price) + (10000 / 1_000_000 * c_price)
            est_str = "0.00 $" if est_100_cards == 0 else f"~{est_100_cards:.4f} $"

            details = [
                f"<b>Contexte :</b> {ctx_str} tokens",
                f"<b>Vision :</b> {vis_text}",
                f"<b>Thinking :</b> {think_text}",
                f"<b>Vitesse :</b> {speed}",
                f"<b>Tarif :</b> {cost_str}",
                f"<b>Coût 100 cartes :</b> {est_str}",
            ]
            for d in details:
                lbl_d = QLabel(d)
                lbl_d.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_SECONDARY};")
                col_layout.addWidget(lbl_d)

            btn_pick = PrimaryButton("Sélectionner")
            btn_pick.setFixedHeight(24)
            btn_pick.clicked.connect(lambda _, m=model: self._on_model_chosen(m))
            col_layout.addWidget(btn_pick)

            self.compare_table_row.addWidget(col_card)

    def get_selected_model(self) -> Any | None:
        """Retourne le modèle sélectionné."""
        return self._selected_model


__all__ = ["ModelCardWidget", "ModelDiscoveryDialog"]
