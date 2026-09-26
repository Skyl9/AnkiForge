"""
EmbeddedCardPreviewWidget — Cartouche de rendu live KaTeX d'une carte Anki dans le fil de chat.

Affiche une carte Anki telle qu'elle apparaîtra lors des révisions (Recto / Verso) avec :
- Rendu mathématique KaTeX (formules en $..$, $$..$$ et \\[..\\]).
- Application des styles CSS effectifs du modèle de note (NoteTypeModel).
- Basculement Recto/Verso via bouton dédié.
- Mode figé (is_frozen=True) après validation ou rejet — badge immuable, contrôles désactivés.
- Conformité aux 12 thèmes graphiques (refresh_theme via DesignTokens, zéro couleur en dur).

Qt PySide6 equivalent: QFrame > (header QWidget + SafeWebEngineView + footer QWidget)
DESIGN.md: EmbeddedCardPreviewWidget — token bg=BG_PANEL, accent=ACCENT_PRIMARY, border=BORDER_COLOR
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt, QUrl, Signal, Slot
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import NoteTypeModel
from ankiforge.ui.theme import DesignTokens, is_dark_mode
from ankiforge.utils.anki_renderer import get_mathjax_script, render_anki_card
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class EmbeddedCardPreviewWidget(QFrame):
    """
    Cartouche de rendu live KaTeX d'une carte Anki intégré dans une bulle de chat du Consultant IA.

    Affiche le contenu HTML d'une carte avec les styles CSS du modèle et le rendu KaTeX.
    Propose un bouton Recto/Verso et se fige après action via freeze().

    Qt PySide6 equivalent: QFrame héritant de QWidget
    DESIGN.md: EmbeddedCardPreviewWidget — token bg=BG_PANEL, accent=ACCENT_PRIMARY
    """

    open_editor_requested = Signal(int)  # note_id
    """Emis pour ouvrir la note correspondante dans l'Éditeur de notes."""

    def __init__(
        self,
        fields: dict[str, str],
        note_type: NoteTypeModel | None = None,
        note_id: int | None = None,
        title: str = "Aperçu de la carte",
        parent: QWidget | None = None,
    ) -> None:
        """
        Args:
            fields: Dictionnaire des champs de la note (nom_champ -> contenu_html).
            note_type: Modèle de note Peewee optionnel pour récupérer les templates et le CSS.
            note_id: Identifiant de la note en BDD (pour le bouton ↗ ouvrir dans l'Éditeur).
            title: Titre affiché dans l'en-tête.
        """
        super().__init__(parent)
        self.is_frozen: bool = False
        self._fields = fields
        self._note_type = note_type
        self._note_id = note_id
        self._is_recto: bool = True
        self._css: str = ""
        self._templates: list[dict[str, Any]] = []

        self.setObjectName("EmbeddedCardPreviewWidget")

        if note_type:
            try:
                import json

                self._css = note_type.css or ""
                raw_tmpls = note_type.templates
                if isinstance(raw_tmpls, str):
                    self._templates = json.loads(raw_tmpls)
                elif isinstance(raw_tmpls, list):
                    self._templates = raw_tmpls
            except Exception as exc:
                logger.debug("Impossible de charger les templates du modèle de note : %s", exc)

        self._setup_ui(title)
        self._apply_theme()
        self._render()

    # ------------------------------------------------------------------
    # Construction UI
    # ------------------------------------------------------------------

    def _setup_ui(self, title: str) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- En-tête ---
        header_container = QWidget()
        header_container.setObjectName("EmbeddedCardPreviewHeader")
        header_layout = QHBoxLayout(header_container)
        header_layout.setContentsMargins(10, 8, 10, 8)
        header_layout.setSpacing(6)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(load_phosphor_icon("ph.cards", color=DesignTokens.ACCENT_PRIMARY).pixmap(14, 14))
        header_layout.addWidget(icon_lbl)

        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("EmbeddedCardPreviewTitle")
        header_layout.addWidget(self.lbl_title, 1)

        self.lbl_side_badge = QLabel("RECTO")
        self.lbl_side_badge.setObjectName("EmbeddedCardSideBadge")
        header_layout.addWidget(self.lbl_side_badge)

        self.lbl_frozen_badge = QLabel()
        self.lbl_frozen_badge.setObjectName("EmbeddedCardPreviewFrozenBadge")
        self.lbl_frozen_badge.setVisible(False)
        header_layout.addWidget(self.lbl_frozen_badge)

        layout.addWidget(header_container)

        # --- Zone de rendu WebEngine (chargement différé pour économiser la RAM) ---
        # On utilise un QLabel HTML statique en fallback si WebEngine est indisponible (mock test).
        self._web_view: Any = None
        self._fallback_lbl: QLabel | None = None
        try:
            from ankiforge.ui.widgets.safe_web_preview import SafeWebEngineView

            self._web_view = SafeWebEngineView()
            self._web_view.setMinimumHeight(120)
            self._web_view.setMaximumHeight(340)
            self._web_view.setStyleSheet("background: transparent; border: none;")
            layout.addWidget(self._web_view, 1)
        except Exception:
            # Environnement headless sans WebEngine (tests CI) → fallback QLabel
            self._fallback_lbl = QLabel()
            self._fallback_lbl.setTextFormat(Qt.TextFormat.RichText)
            self._fallback_lbl.setWordWrap(True)
            self._fallback_lbl.setAlignment(Qt.AlignmentFlag.AlignTop)
            self._fallback_lbl.setContentsMargins(10, 8, 10, 8)
            layout.addWidget(self._fallback_lbl)

        # --- Barre d'actions inférieure ---
        footer_container = QWidget()
        footer_container.setObjectName("EmbeddedCardPreviewFooter")
        footer_layout = QHBoxLayout(footer_container)
        footer_layout.setContentsMargins(10, 6, 10, 6)
        footer_layout.setSpacing(6)

        self.btn_flip = QPushButton()
        self.btn_flip.setIcon(load_phosphor_icon("ph.arrows-left-right", color=DesignTokens.TEXT_PRIMARY))
        self.btn_flip.setText("Verso")
        self.btn_flip.setFixedHeight(26)
        self.btn_flip.clicked.connect(self._on_flip)
        footer_layout.addWidget(self.btn_flip)

        footer_layout.addStretch(1)

        if self._note_id:
            self.btn_open = QPushButton()
            self.btn_open.setIcon(load_phosphor_icon("ph.arrow-square-out", color=DesignTokens.ACCENT_PRIMARY))
            self.btn_open.setText("Ouvrir dans l'Éditeur")
            self.btn_open.setFixedHeight(26)
            self.btn_open.clicked.connect(lambda: self.open_editor_requested.emit(self._note_id or 0))
            footer_layout.addWidget(self.btn_open)

        layout.addWidget(footer_container)

    # ------------------------------------------------------------------
    # Rendu
    # ------------------------------------------------------------------

    def _render(self) -> None:
        """Génère le HTML final et l'injecte dans le WebEngine ou le fallback QLabel."""
        html = self._build_html()
        if self._web_view is not None:
            self._web_view.setHtml(html, QUrl("about:blank"))
        elif self._fallback_lbl is not None:
            # En mode test headless : on injecte le HTML brut dans le QLabel
            self._fallback_lbl.setText(html)

        side = "RECTO" if self._is_recto else "VERSO"
        self.lbl_side_badge.setText(side)

    def _build_html(self) -> str:
        """Construit le document HTML complet à partir des champs, templates et CSS."""
        if self._templates:
            template = self._templates[0]
            front_template = template.get("qfmt", "{{Front}}")
            back_template = template.get("afmt", "{{FrontSide}}\n{{Back}}")
        else:
            # Fallback générique si aucun template n'est disponible
            fields_html = "".join(f"<div style='margin-bottom: 8px'><b style='font-size: 11px; opacity: 0.6'>{k.upper()}</b><br>{v}</div>" for k, v in self._fields.items())
            front_html_plain = fields_html
            mathjax = get_mathjax_script()
            return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    {mathjax}
    <style>
        body {{
            background: transparent;
            margin: 0;
            padding: 12px;
            font-family: {DesignTokens.FONT_MAIN}, -apple-system, sans-serif;
            font-size: 14px;
            color: {DesignTokens.TEXT_PRIMARY};
            line-height: 1.6;
        }}
    </style>
</head>
<body>{front_html_plain}</body>
</html>"""

        dark = is_dark_mode()

        front_html = render_anki_card(
            raw_html=front_template,
            css=self._css,
            fields_dict=self._fields,
            is_recto=True,
            is_dark_mode=dark,
        )

        if self._is_recto:
            return front_html

        return render_anki_card(
            raw_html=back_template,
            css=self._css,
            fields_dict=self._fields,
            is_recto=False,
            front_html=front_html,
            is_dark_mode=dark,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_fields(self, fields: dict[str, str]) -> None:
        """Met à jour les champs de la note et force un rechargement du rendu."""
        if self.is_frozen:
            logger.debug("EmbeddedCardPreviewWidget.update_fields ignoré : widget figé.")
            return
        self._fields = fields
        self._render()

    def freeze(self, timestamp: str = "") -> None:
        """Fige le widget en mode immuable : désactive les contrôles, affiche un badge de statut."""
        if self.is_frozen:
            return
        self.is_frozen = True
        self.btn_flip.setEnabled(False)
        if hasattr(self, "btn_open"):
            self.btn_open.setEnabled(False)
        badge_text = f"🔒 Figé{f' · {timestamp}' if timestamp else ''}"
        self.lbl_frozen_badge.setText(badge_text)
        self.lbl_frozen_badge.setVisible(True)
        logger.debug("EmbeddedCardPreviewWidget figé.")

    def refresh_theme(self) -> None:
        """Réapplique les tokens DesignTokens après un changement de thème et re-rend la carte."""
        self._apply_theme()
        self._render()

    # ------------------------------------------------------------------
    # Slots internes
    # ------------------------------------------------------------------

    @Slot()
    def _on_flip(self) -> None:
        """Bascule entre le Recto et le Verso."""
        if self.is_frozen:
            return
        self._is_recto = not self._is_recto
        self.btn_flip.setText("Recto" if not self._is_recto else "Verso")
        self._render()

    # ------------------------------------------------------------------
    # Style
    # ------------------------------------------------------------------

    def _apply_theme(self) -> None:
        """Applique les tokens DesignTokens au widget (zéro couleur en dur)."""
        self.setStyleSheet(f"""
            QFrame#EmbeddedCardPreviewWidget {{
                background: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
            QWidget#EmbeddedCardPreviewHeader {{
                background: {DesignTokens.BG_SIDEBAR};
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px {DesignTokens.RADIUS_MD}px 0 0;
            }}
            QWidget#EmbeddedCardPreviewFooter {{
                background: {DesignTokens.BG_SIDEBAR};
                border-top: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 0 0 {DesignTokens.RADIUS_MD}px {DesignTokens.RADIUS_MD}px;
            }}
            QLabel#EmbeddedCardPreviewTitle {{
                font-weight: bold;
                font-size: 11px;
                color: {DesignTokens.TEXT_SECONDARY};
                letter-spacing: 0.3px;
                border: none;
            }}
            QLabel#EmbeddedCardSideBadge {{
                font-size: 10px;
                font-weight: bold;
                color: {DesignTokens.ACCENT_PRIMARY};
                border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                border-radius: 4px;
                padding: 1px 6px;
            }}
            QLabel#EmbeddedCardPreviewFrozenBadge {{
                font-size: 10px;
                color: {DesignTokens.TEXT_MUTED};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                padding: 1px 6px;
            }}
            QPushButton {{
                background: {DesignTokens.BG_MAIN};
                color: {DesignTokens.TEXT_PRIMARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 2px 10px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background: {DesignTokens.BG_HOVER};
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
            QPushButton:disabled {{
                color: {DesignTokens.TEXT_MUTED};
                background: {DesignTokens.BG_SIDEBAR};
            }}
        """)
