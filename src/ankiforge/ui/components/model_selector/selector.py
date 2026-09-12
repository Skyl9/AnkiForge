"""
Composant universel de sélection de modèle LLM pour AnkiForge.
Combine un menu déroulant enrichi, des badges de capacités dynamiques et un bouton d'inspection/découverte.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Signal
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


class ModelSelectorWidget(QWidget):
    """
    Sélecteur universel de modèles LLM avec badges de capacités et accès direct au comparateur.
    """

    model_changed = Signal(object)  # LLMConfigModel | None

    def __init__(
        self,
        allow_inherit: bool = False,
        inherit_label: str = "Hériter du réglage global de l'application",
        show_badges: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.allow_inherit = allow_inherit
        self.inherit_label = inherit_label
        self.show_badges = show_badges
        self._models: list[LLMConfigModel] = []

        self._setup_ui()
        self.refresh_models()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Ligne de contrôle : ComboBox + Bouton d'inspection
        control_row = QHBoxLayout()
        control_row.setContentsMargins(0, 0, 0, 0)
        control_row.setSpacing(6)

        self.combo = StyledComboBox(self)
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
            self.combo.addItem(inherit_icon, self.inherit_label, userData=None)

        try:
            self._models = list(LLMConfigModel.select().order_by(LLMConfigModel.sort_order.asc(), LLMConfigModel.id.asc()))
            for m in self._models:
                display = m.display_name or f"{m.provider} ({m.model_id})"
                pricing_tag = "Gratuit" if (m.is_free or m.provider == "ollama") else f"{m.prompt_pricing:.2f}$/1M"
                prov_icon_name = "ph.brain"
                icon_color = DesignTokens.ACCENT_PRIMARY
                if m.provider == "gemini":
                    prov_icon_name = "ph.sparkle"
                    icon_color = DesignTokens.COLOR_BLUE
                elif m.provider == "anthropic":
                    prov_icon_name = "ph.lightning"
                    icon_color = DesignTokens.COLOR_YELLOW
                elif m.provider == "ollama":
                    prov_icon_name = "ph.cpu"
                    icon_color = DesignTokens.COLOR_GREEN

                icon = load_phosphor_icon(prov_icon_name, color=icon_color)
                label = f"{display}  ·  {pricing_tag}"
                self.combo.addItem(icon, label, userData=m)
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
        dlg = ModelDiscoveryDialog(current_model_id=curr_m_id, picker_mode=True, parent=self)
        if dlg.exec():
            selected = dlg.get_selected_model()
            if selected:
                # Recharger au cas où un nouveau modèle du catalogue a été injecté
                self.refresh_models()
                target_id = getattr(selected, "id", None) or getattr(selected, "model_id", None)
                self.set_current_model_id(target_id)
                self.model_changed.emit(self.get_current_model())


__all__ = ["ModelSelectorWidget"]
