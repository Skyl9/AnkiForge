"""
Composant de badges et capsules de capacités pour les modèles de langage (LLM).
Affiche de manière compacte et élégante la Vision, le Thinking, le Contexte, la Vitesse et le Coût.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QWidget,
)

from ankiforge.database.models import LLMConfigModel
from ankiforge.services.ai.model_catalog import ModelSpec
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon


class CapabilityPill(QWidget):
    """Pastille individuelle de capacité avec icône Phosphor et texte."""

    def __init__(
        self,
        icon_name: str,
        text: str,
        accent_color: str,
        tooltip: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 2, 6, 2)
        layout.setSpacing(3)

        self.icon_lbl = QLabel()
        self.icon_lbl.setPixmap(load_phosphor_icon(icon_name, color=accent_color).pixmap(11, 11))
        layout.addWidget(self.icon_lbl)

        self.text_lbl = QLabel(text)
        self.text_lbl.setStyleSheet(f"""
            QLabel {{
                color: {accent_color};
                font-size: 10px;
                font-weight: 600;
                background: transparent;
                border: none;
            }}
        """)
        layout.addWidget(self.text_lbl)

        # Style du conteneur
        self.setStyleSheet(f"""
            CapabilityPill {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)

        if tooltip:
            self.setToolTip(tooltip)


class ModelCapabilityBadgesWidget(QWidget):
    """
    Rangée horizontale dynamique affichant les capacités du modèle LLM actif :
    Vision, Thinking (Raisonnement), Vitesse, Taille de contexte, et Gratuité/Coût.
    """

    def __init__(self, compact: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.compact = compact
        self.layout_h = QHBoxLayout(self)
        self.layout_h.setContentsMargins(0, 0, 0, 0)
        self.layout_h.setSpacing(4)
        self.layout_h.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

    def update_for_spec(self, spec: LLMConfigModel | ModelSpec | None) -> None:
        """Alias pour set_model()."""
        self.set_model(spec)

    def set_model(self, model: LLMConfigModel | ModelSpec | None) -> None:
        """Met à jour les badges affichés selon le modèle spécifié."""
        # Nettoyage des badges existants
        while self.layout_h.count():
            item = self.layout_h.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()

        if model is None:
            lbl_none = QLabel("—")
            lbl_none.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px;")
            self.layout_h.addWidget(lbl_none)
            return

        # Extraction unifiée des propriétés
        supports_vision = getattr(model, "supports_vision", False)
        supports_thinking = getattr(model, "supports_thinking", False)
        speed_rating = getattr(model, "speed_rating", "fast")
        provider = str(getattr(model, "provider", "")).lower()
        is_free = getattr(model, "is_free", False) or provider == "ollama"

        # Contexte
        ctx = getattr(model, "context_limit", None) or getattr(model, "context_window", 128000)
        if ctx >= 1_000_000:
            val = ctx / 1_000_000
            ctx_str = f"{val:.1f}M" if val % 1 else f"{int(val)}M"
        elif ctx >= 1_000:
            ctx_str = f"{ctx // 1_000}k"
        else:
            ctx_str = str(ctx)

        # 1. Badge Contexte
        pill_ctx = CapabilityPill(
            "ph.brackets-curly",
            ctx_str,
            DesignTokens.TEXT_PRIMARY,
            tooltip=f"Fenêtre de contexte : {ctx:,} tokens",
            parent=self,
        )
        self.layout_h.addWidget(pill_ctx)

        # 2. Badge Vision (si supporté)
        if supports_vision:
            pill_vis = CapabilityPill(
                "ph.eye",
                "Vision" if not self.compact else "Vis",
                DesignTokens.COLOR_BLUE,
                tooltip="Capacité multimodale : analyse d'images, figures et schémas",
                parent=self,
            )
            self.layout_h.addWidget(pill_vis)

        # 3. Badge Thinking / Raisonnement (si supporté)
        if supports_thinking:
            pill_think = CapabilityPill(
                "ph.brain",
                "Thinking" if not self.compact else "CoT",
                "#a855f7",  # Violet vibrant pour le raisonnement
                tooltip="Mode réflexion approfondie par chaîne de pensée (Chain-of-Thought)",
                parent=self,
            )
            self.layout_h.addWidget(pill_think)

        # 4. Badge Vitesse
        speed_color = DesignTokens.COLOR_GREEN if speed_rating == "ultra-fast" else (DesignTokens.COLOR_YELLOW if speed_rating == "fast" else DesignTokens.TEXT_MUTED)
        speed_text = "Éclair" if speed_rating == "ultra-fast" else ("Rapide" if speed_rating == "fast" else "Posé")
        pill_speed = CapabilityPill(
            "ph.lightning",
            speed_text,
            speed_color,
            tooltip=f"Vitesse d'inférence : {speed_rating}",
            parent=self,
        )
        self.layout_h.addWidget(pill_speed)

        # 5. Badge Localité / Gratuité
        if provider == "ollama":
            pill_local = CapabilityPill(
                "ph.cpu",
                "100% Local" if not self.compact else "Local",
                DesignTokens.COLOR_GREEN,
                tooltip="Exécution 100% locale sur votre machine via Ollama (zéro cloud, zéro coût)",
                parent=self,
            )
            self.layout_h.addWidget(pill_local)
        elif is_free:
            pill_free = CapabilityPill(
                "ph.coins",
                "Gratuit" if not self.compact else "Free",
                DesignTokens.COLOR_GREEN,
                tooltip="Modèle accessible gratuitement (Tier gratuit du fournisseur)",
                parent=self,
            )
            self.layout_h.addWidget(pill_free)
        else:
            p_price = float(getattr(model, "prompt_pricing", 0.0) or 0.0)
            pill_price = CapabilityPill(
                "ph.currency-dollar",
                f"${p_price:.2f}/1M" if not self.compact else f"${p_price:.1f}",
                DesignTokens.TEXT_MUTED,
                tooltip=f"Tarif estimé : ${p_price:.2f} par million de tokens en entrée",
                parent=self,
            )
            self.layout_h.addWidget(pill_price)


__all__ = ["CapabilityPill", "ModelCapabilityBadgesWidget"]
