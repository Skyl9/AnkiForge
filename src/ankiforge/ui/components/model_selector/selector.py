"""Composant universel de sélection de modèle LLM pour AnkiForge.

Combine un menu déroulant enrichi, des badges de capacités dynamiques et un bouton d'inspection/découverte.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import LLMConfigModel
from ankiforge.ui.components import IconButton, StyledComboBox
from ankiforge.ui.components.model_selector.badges import ModelCapabilityBadgesWidget
from ankiforge.ui.components.model_selector.dialog import ModelDiscoveryDialog
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class LLMModelItem(LLMConfigModel):
    """Encapsulation légère d'un LLMConfigModel supportant l'égalité par identifiant texte."""

    def __str__(self) -> str:
        return str(self.model_id or "")

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            if other in ("hardware", "native") and self.model_id in ("hardware", "native", "apple_vision"):
                return True
            if other == "structured" and (self.model_id in ("structured", "qwen2.5-vl:7b") or "qwen" in self.model_id.lower()):
                return True
            if other == "reasoning" and (self.model_id in ("reasoning", "claude-3-7-sonnet-20250219") or "claude" in self.model_id.lower()):
                return True
            if other == "massive" and (self.model_id in ("massive", "gemini-2.5-flash") or "gemini" in self.model_id.lower()):
                return True
            return bool(self.model_id == other or str(self.id) == other)
        return bool(super().__eq__(other))


class ModelComboBox(StyledComboBox):
    """ComboBox spécialisée pour la sélection de modèle avec résolution par chaîne."""

    def findData(
        self,
        data: Any,
        role: int = Qt.ItemDataRole.UserRole,
        flags: Qt.MatchFlag = Qt.MatchFlag.MatchExactly,
    ) -> int:
        idx = super().findData(data, role, flags)
        if idx >= 0:
            return idx
        target_str = str(data)
        for i in range(self.count()):
            m = self.itemData(i, role)
            if isinstance(m, LLMConfigModel):
                if m.model_id == target_str or str(m.id) == target_str:
                    return i
                if target_str in ("hardware", "native") and m.model_id in ("hardware", "native", "apple_vision"):
                    return i
                if target_str == "structured" and (m.model_id in ("structured", "qwen2.5-vl:7b") or "qwen" in m.model_id.lower()):
                    return i
                if target_str == "reasoning" and (m.model_id in ("reasoning", "claude-3-7-sonnet-20250219") or "claude" in m.model_id.lower()):
                    return i
                if target_str == "massive" and (m.model_id in ("massive", "gemini-2.5-flash") or "gemini" in m.model_id.lower()):
                    return i
        return -1


class ModelSelectorWidget(QWidget):
    """Sélecteur universel de modèles LLM avec badges de capacités et accès direct au comparateur."""

    model_changed = Signal(object)  # LLMConfigModel | None

    def __init__(
        self,
        allow_inherit: bool = False,
        inherit_label: str = "Hériter du réglage global de l'application",
        show_badges: bool = True,
        require_vision: bool = False,
        include_native_vision: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.allow_inherit = allow_inherit
        self.inherit_label = inherit_label
        self.show_badges = show_badges
        self.require_vision = require_vision
        self.include_native_vision = include_native_vision
        self._models: list[LLMConfigModel] = []

        self._setup_ui()
        self.refresh_models()

        from ankiforge.utils.event_bus import LLMModelsChangedEvent, event_bus

        event_bus.subscribe(LLMModelsChangedEvent, self._on_models_changed_event)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Ligne de contrôle : ComboBox + Bouton d'inspection
        control_row = QHBoxLayout()
        control_row.setContentsMargins(0, 0, 0, 0)
        control_row.setSpacing(6)

        self.combo = ModelComboBox(self)
        self.combo.currentIndexChanged.connect(self._on_combo_changed)
        control_row.addWidget(self.combo, 1)

        self.btn_inspect = IconButton(
            "ph.info",
            "Découvrir et comparer les capacités des modèles (Vision, Contexte, Coûts)",
            16,
            self,
        )
        self.btn_inspect.clicked.connect(self._open_discovery_dialog)
        control_row.addWidget(self.btn_inspect)

        layout.addLayout(control_row)

        # Badges de capacités synchronisés
        self.badges_widget = ModelCapabilityBadgesWidget(compact=False, parent=self)
        if not self.show_badges:
            self.badges_widget.hide()
        layout.addWidget(self.badges_widget)

    def set_show_badges(self, show: bool) -> None:
        """Affiche ou masque la rangée de badges de capacités sous le sélecteur."""
        self.show_badges = show
        self.badges_widget.setVisible(show)

    def refresh_models(self) -> None:
        """Recharge les modèles depuis la base SQLite."""
        curr_id = self.get_current_model_id()

        self.combo.blockSignals(True)
        self.combo.clear()

        if self.allow_inherit:
            inherit_icon = load_phosphor_icon("ph.gear", color=DesignTokens.TEXT_MUTED)
            inherit_tip = f"Réglage global de l'application\n{self.inherit_label}"
            self.combo.addItem(inherit_icon, self.inherit_label, userData=None)
            self.combo.setItemData(self.combo.count() - 1, inherit_tip, Qt.ItemDataRole.ToolTipRole)

        try:
            query = LLMConfigModel.select().order_by(LLMConfigModel.sort_order.asc(), LLMConfigModel.id.asc())
            if self.require_vision:
                query = query.where(LLMConfigModel.supports_vision == True)  # noqa: E712
            self._models = list(query)

            if self.require_vision and not self._models:
                # Modèles de vision recommandés si la base n'en contient pas encore
                default_vlms = [
                    LLMModelItem(
                        id=101,
                        display_name="Qwen 2.5 VL 7B (Ollama)",
                        provider="ollama",
                        model_id="qwen2.5-vl:7b",
                        supports_vision=True,
                        supports_thinking=False,
                        description="Modèle de vision structuré local, tableaux et formules.",
                    ),
                    LLMModelItem(
                        id=102,
                        display_name="Claude 3.7 Sonnet (Anthropic)",
                        provider="anthropic",
                        model_id="claude-3-7-sonnet-20250219",
                        supports_vision=True,
                        supports_thinking=True,
                        thinking_budget=2048,
                        description="Raisonnement visuel complexe avec réflexion pas-à-pas.",
                    ),
                    LLMModelItem(
                        id=103,
                        display_name="Google Gemini 2.5 Flash",
                        provider="gemini",
                        model_id="gemini-2.5-flash",
                        supports_vision=True,
                        supports_thinking=False,
                        description="Ingestion massive haute vitesse pour documents scannés.",
                    ),
                ]
                self._models.extend(default_vlms)

            if self.include_native_vision:
                native_model = LLMModelItem(
                    id=-1,
                    display_name="Apple Vision (OCR local)",
                    provider="native",
                    model_id="apple_vision",
                    supports_vision=True,
                    is_free=True,
                    description="Extraction optique locale sans VRAM (Apple Vision sous macOS).",
                )
                self._models.append(native_model)

            for m in self._models:
                m.__class__ = LLMModelItem
                display = m.display_name or f"{m.provider} ({m.model_id})"
                pricing_tag = "Gratuit" if (m.is_free or m.provider in ("ollama", "native")) else f"{m.prompt_pricing:.2f}$/1M"
                prov_icon_name = "ph.brain"
                icon_color = DesignTokens.ACCENT_PRIMARY
                if m.provider == "gemini":
                    prov_icon_name = "ph.sparkle"
                    icon_color = DesignTokens.COLOR_BLUE
                elif m.provider == "anthropic":
                    prov_icon_name = "ph.lightning"
                    icon_color = DesignTokens.COLOR_YELLOW
                elif m.provider == "ollama" or m.provider == "native":
                    prov_icon_name = "ph.cpu"
                    icon_color = DesignTokens.COLOR_GREEN
                elif m.provider == "opencode":
                    prov_icon_name = "ph.code"
                    icon_color = DesignTokens.COLOR_PURPLE
                elif m.provider == "openrouter":
                    prov_icon_name = "ph.arrows-split"
                    icon_color = DesignTokens.FLAG_PINK

                icon = load_phosphor_icon(prov_icon_name, color=icon_color)
                label = f"{display}  ·  {pricing_tag}"
                tooltip_parts = [m.display_name or m.model_id, f"Fournisseur : {m.provider}"]
                if m.formatted_context_window:
                    tooltip_parts.append(f"Fenêtre de contexte : {m.formatted_context_window}")
                self.combo.addItem(icon, label, userData=m)
                self.combo.setItemData(self.combo.count() - 1, "\n".join(tooltip_parts), Qt.ItemDataRole.ToolTipRole)
        except Exception as e:
            logger.warning("Erreur chargement modèles dans ModelSelectorWidget: %s", e)

        self.combo.blockSignals(False)

        # Restaurer la sélection
        if curr_id is not None:
            self.set_current_model_id(curr_id)
        elif self.combo.count() > 0:
            self.combo.setCurrentIndex(0)
            self._update_badges()

    def get_current_model(self) -> LLMConfigModel | None:
        """Retourne l'objet LLMConfigModel actuellement sélectionné, ou None si 'hériter'."""
        data = self.combo.currentData()
        return data if isinstance(data, LLMConfigModel) else None

    def currentData(self) -> LLMConfigModel | None:
        """Alias pour get_current_model() assurant la compatibilité avec StyledComboBox."""
        return self.get_current_model()

    def get_current_model_id(self) -> int | None:
        """Retourne l'ID numérique du modèle sélectionné, ou None."""
        model = self.get_current_model()
        return getattr(model, "id", None) if model else None

    def setCurrentIndex(self, index: int) -> None:
        """Définit l'index actif dans le combobox sous-jacent."""
        self.combo.setCurrentIndex(index)

    def currentIndex(self) -> int:
        """Retourne l'index actif du combobox sous-jacent."""
        return self.combo.currentIndex()

    def count(self) -> int:
        """Retourne le nombre d'éléments dans le combobox."""
        return self.combo.count()

    def findText(self, text: str) -> int:
        """Trouve l'index correspondant au texte affiché."""
        return self.combo.findText(text)

    def findData(self, data: object) -> int:
        """Trouve l'index correspondant à l'objet de données associé."""
        return self.combo.findData(data)

    def _on_models_changed_event(self, event: Any) -> None:
        """Réaction automatique à toute modification du catalogue de modèles LLM."""
        self.refresh_models()

    def set_current_model_id(self, model_id: int | str | None) -> None:
        """Définit le modèle actif par son ID SQLite ou son model_id chaîne."""
        if model_id is None:
            if self.allow_inherit:
                self.combo.setCurrentIndex(0)
            return

        for idx in range(self.combo.count()):
            m = self.combo.itemData(idx)
            if isinstance(m, LLMConfigModel) and (m.id == model_id or m.model_id == str(model_id)):
                self.combo.setCurrentIndex(idx)
                self._update_badges()
                return

        # Si le modèle recherché n'existe plus (supprimé), repli sur le premier élément
        if self.combo.count() > 0:
            self.combo.setCurrentIndex(0)
            self._update_badges()
            self.model_changed.emit(self.get_current_model())

    def _on_combo_changed(self, index: int) -> None:
        self._update_badges()
        self.model_changed.emit(self.get_current_model())

    def _update_badges(self) -> None:
        model = self.get_current_model()
        if self.show_badges:
            self.badges_widget.set_model(model)
            self.badges_widget.setVisible(model is not None)

    def _open_discovery_dialog(self) -> None:
        """Ouvre la modale de découverte et synchronise le choix de l'utilisateur."""
        curr = self.get_current_model()
        curr_m_id = curr.model_id if curr else None
        dlg = ModelDiscoveryDialog(
            current_model_id=curr_m_id,
            picker_mode=True,
            require_vision=self.require_vision,
            parent=self,
        )
        if dlg.exec():
            selected = dlg.get_selected_model()
            if selected:
                # Recharger au cas où un nouveau modèle du catalogue a été injecté
                self.refresh_models()
                target_id = getattr(selected, "id", None) or getattr(selected, "model_id", None)
                self.set_current_model_id(target_id)
                self.model_changed.emit(self.get_current_model())

    def closeEvent(self, event: QCloseEvent) -> None:
        """Désabonne le composant du bus d'événements lors de la destruction du widget."""
        try:
            from ankiforge.utils.event_bus import LLMModelsChangedEvent, event_bus

            event_bus.unsubscribe(LLMModelsChangedEvent, self._on_models_changed_event)
        except Exception:
            pass
        super().closeEvent(event)


__all__ = ["ModelSelectorWidget"]
