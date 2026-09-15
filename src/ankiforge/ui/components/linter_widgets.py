"""
Widgets UI PySide6 sur mesure pour le Linter Wozniak, Diagnostic des Sources et FSRS-4.5.
"""

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from ankiforge.ui.components.badges import Badge
from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon


class WozniakHubWidget(QWidget):
    """Hub d'accueil pédagogique de l'Audit Wozniak (Progressive Disclosure)."""

    select_deck_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 1. En-tête du Hub
        header_box = QVBoxLayout()
        header_box.setSpacing(6)
        header_box.setAlignment(Qt.AlignmentFlag.AlignCenter)

        ico_badge = QLabel()
        ico_badge.setPixmap(load_phosphor_icon("ph.sparkle", color=DesignTokens.COLOR_BLUE, weight="fill").pixmap(32, 32))
        ico_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ico_badge.setStyleSheet("background: transparent; border: none;")

        lbl_header = QLabel(f"""
            <div style="text-align: center; max-width: 650px;">
                <div style="color: {DesignTokens.TEXT_PRIMARY}; font-weight: bold; font-size: 14px; margin-bottom: 6px;">
                    Audit Ergonomique & Linter Wozniak
                </div>
                <div style="color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; line-height: 140%;">
                    Analyse cognitive automatisée de vos cartes Anki basée sur les 20 règles fondamentales de Piotr Wozniak (SuperMemo).<br>
                    Détectez les formulations ambiguës, scindez les cartes volumineuses et sublimez vos formules mathématiques.
                </div>
            </div>
        """)
        lbl_header.setTextFormat(Qt.TextFormat.RichText)
        lbl_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_header.setStyleSheet("background: transparent; border: none;")

        header_box.addWidget(ico_badge)
        header_box.addWidget(lbl_header)
        layout.addLayout(header_box)

        # 2. Les 3 Piliers Wozniak (Cartes explicatives)
        pillars_layout = QHBoxLayout()
        pillars_layout.setSpacing(12)

        pillars = [
            (
                "ph.cube",
                DesignTokens.COLOR_PURPLE,
                "Principe d'Atomicité (Règle 4)",
                "Évitez les listes et pavés de texte. Chaque carte ne doit tester qu'une seule bribe indivisible de connaissance.",
            ),
            (
                "ph.chat-circle-dots",
                DesignTokens.COLOR_YELLOW,
                "Questions Univoques (Règle 5)",
                "Supprimez les questions vagues ou ouvertes. La formulation doit appeler une réponse précise et immédiate.",
            ),
            (
                "ph.graph",
                DesignTokens.COLOR_BLUE,
                "Désambiguïsation (Règle 9)",
                "Éliminez les interférences entre cartes sœurs grâce à des indices contextuels clairs et distinctifs.",
            ),
        ]

        for icon, color, p_title, p_desc in pillars:
            card = QFrame()
            card.setStyleSheet(f"""
                QFrame {{
                    background-color: {DesignTokens.BG_PANEL};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: {DesignTokens.RADIUS_MD}px;
                    padding: 12px;
                }}
            """)
            c_layout = QVBoxLayout(card)
            c_layout.setSpacing(6)

            c_top = QHBoxLayout()
            c_top.setSpacing(6)
            c_ico = QLabel()
            c_ico.setPixmap(load_phosphor_icon(icon, color=color).pixmap(18, 18))
            c_ico.setStyleSheet("border: none; background: transparent;")

            c_lbl_title = QLabel(p_title)
            c_lbl_title.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
            c_lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")

            c_top.addWidget(c_ico)
            c_top.addWidget(c_lbl_title)
            c_top.addStretch()
            c_layout.addLayout(c_top)

            c_lbl_desc = QLabel(p_desc)
            c_lbl_desc.setFont(QFont(DesignTokens.FONT_MAIN, 10))
            c_lbl_desc.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; border: none; background: transparent;")
            c_lbl_desc.setWordWrap(True)
            c_layout.addWidget(c_lbl_desc)

            pillars_layout.addWidget(card, 1)

        layout.addLayout(pillars_layout)

        # 3. Bouton d'Action Central
        btn_box = QHBoxLayout()
        btn_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.btn_select_deck = PrimaryButton("Sélectionner un Paquet pour Lancer l'Audit")
        self.btn_select_deck.setIcon(load_phosphor_icon("ph.folder-open", color="#ffffff"))
        self.btn_select_deck.clicked.connect(self.select_deck_requested.emit)
        btn_box.addWidget(self.btn_select_deck)
        layout.addLayout(btn_box)


class WozniakKpiCard(QFrame):
    """Carte KPI d'aperçu de catégorie du linter Wozniak avec jauge, état grisé et sélection interactive."""

    clicked = Signal(str)

    def __init__(
        self,
        cat_id: str,
        title: str,
        pct: int = 100,
        subtitle: str = "En attente d'audit",
        color: str = DesignTokens.COLOR_RED,
        icon_name: str = "ph.squares-four",
        is_pending: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.cat_id = cat_id
        self.title = title
        self.color = color
        self.icon_name = icon_name if icon_name.startswith("ph.") else f"ph.{icon_name}"
        self._is_active = False
        self._is_pending = is_pending

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        row1 = QHBoxLayout()
        row1.setSpacing(6)

        self.lbl_icon = QLabel()
        self.lbl_icon.setStyleSheet("border: none; background: transparent;")

        self.lbl_title = QLabel(title)
        self.lbl_title.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))

        self.lbl_pct = QLabel(f"{pct}%" if not is_pending else "--")
        self.lbl_pct.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))

        row1.addWidget(self.lbl_icon)
        row1.addWidget(self.lbl_title)
        row1.addStretch()
        row1.addWidget(self.lbl_pct)
        layout.addLayout(row1)

        self.lbl_sub = QLabel(subtitle)
        self.lbl_sub.setFont(QFont(DesignTokens.FONT_MAIN, 9))
        layout.addWidget(self.lbl_sub)

        # Progress bar
        from PySide6.QtWidgets import QProgressBar

        self.progress = QProgressBar()
        self.progress.setFixedHeight(3)
        self.progress.setTextVisible(False)
        self.progress.setMinimum(0)
        self.progress.setMaximum(100)
        self.progress.setValue(pct if not is_pending else 0)
        layout.addWidget(self.progress)

        self.set_pending(is_pending)
        if not is_pending:
            self.update_pct(pct, subtitle)

    def set_pending(self, pending: bool) -> None:
        """Grisé ou active visuellement la carte selon si l'analyse a été effectuée."""
        self._is_pending = pending
        if pending:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.lbl_icon.setPixmap(load_phosphor_icon(self.icon_name, color=DesignTokens.TEXT_MUTED).pixmap(15, 15))
            self.lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")
            self.lbl_pct.setText("--")
            self.lbl_pct.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")
            self.lbl_sub.setText("En attente d'audit")
            self.lbl_sub.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")
            self.progress.setValue(0)
            self.progress.setStyleSheet(f"""
                QProgressBar {{
                    background-color: {DesignTokens.BG_INPUT};
                    border-radius: 1px;
                    border: none;
                }}
                QProgressBar::chunk {{
                    background-color: {DesignTokens.BORDER_COLOR};
                    border-radius: 1px;
                }}
            """)
            self.setStyleSheet(f"""
                WozniakKpiCard {{
                    background-color: {DesignTokens.BG_MAIN};
                    border: 1px dashed {DesignTokens.BORDER_COLOR};
                    border-radius: {DesignTokens.RADIUS_SM}px;
                }}
            """)
        else:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.lbl_icon.setPixmap(load_phosphor_icon(self.icon_name, color=self.color).pixmap(15, 15))
            self.lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")
            self.lbl_pct.setStyleSheet(f"color: {self.color}; border: none; background: transparent;")
            self.lbl_sub.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")
            self.progress.setStyleSheet(f"""
                QProgressBar {{
                    background-color: {DesignTokens.BG_INPUT};
                    border-radius: 1px;
                    border: none;
                }}
                QProgressBar::chunk {{
                    background-color: {self.color};
                    border-radius: 1px;
                }}
            """)
            self.update_style()

    def update_pct(self, pct: int, subtitle: str = "") -> None:
        """Met à jour le score et dégrise automatiquement la carte."""
        self.set_pending(False)
        self.lbl_pct.setText(f"{pct}%")
        self.progress.setValue(pct)
        if subtitle:
            self.lbl_sub.setText(subtitle)

    def set_active(self, active: bool) -> None:
        self._is_active = active
        if not self._is_pending:
            self.update_style()

    def update_style(self) -> None:
        if self._is_pending:
            return
        border_color = DesignTokens.ACCENT_PRIMARY if self._is_active else DesignTokens.BORDER_COLOR
        bg_color = DesignTokens.BG_ACTIVE if self._is_active else DesignTokens.BG_PANEL
        self.setStyleSheet(f"""
            WozniakKpiCard {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
            WozniakKpiCard:hover {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)

    def mousePressEvent(self, event) -> None:
        if not self._is_pending:
            self.clicked.emit(self.cat_id)
        super().mousePressEvent(event)


class FieldInspectorWidget(QFrame):
    """Inspecteur déroulant 5 champs (NoteType, Recto, Verso, Extra, Tags)."""

    def __init__(self, original_data: dict[str, str], proposal_data: dict[str, str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            FieldInspectorWidget {{
                background-color: {DesignTokens.BG_MAIN};
                border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                border-radius: 6px;
                padding: 8px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        lbl_header = QLabel("Inspecteur MCP · 5 Champs SQLite vs Proposition IA")
        lbl_header.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
        lbl_header.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border-bottom: 1px solid {DesignTokens.BORDER_COLOR}; padding-bottom: 4px;")
        layout.addWidget(lbl_header)

        grid_layout = QHBoxLayout()

        # Original Panel
        # Original Panel
        orig_box = QFrame()
        orig_box.setStyleSheet(f".QFrame {{ background-color: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 4px; padding: 8px; }}")
        orig_layout = QVBoxLayout(orig_box)
        orig_title = QLabel("CARTE ACTUELLE EN BASE (SQLite)")
        orig_title.setFont(QFont(DesignTokens.FONT_MAIN, 10, QFont.Weight.Bold))
        orig_title.setStyleSheet(f"color: {DesignTokens.COLOR_RED};")
        orig_layout.addWidget(orig_title)

        field_keys = ["NoteType", "Recto", "Verso", "Champ Annexe Extra", "Tags"]
        for key in field_keys:
            val = "-"
            if key == "Recto":
                val = original_data.get("Recto") or original_data.get("Front") or original_data.get("Texte") or original_data.get("Text") or "-"
            elif key == "Verso":
                val = original_data.get("Verso") or original_data.get("Back") or "-"
            elif key == "Champ Annexe Extra":
                val = original_data.get("Champ Annexe Extra") or original_data.get("Extra") or original_data.get("Remarques extra") or "-"
            else:
                val = original_data.get(key, "-")

            lbl = QLabel(f"<b>{key} :</b> {val}")
            lbl.setFont(QFont(DesignTokens.FONT_MAIN, 10))
            lbl.setWordWrap(True)
            lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY};")
            orig_layout.addWidget(lbl)

        # Proposal Panel
        prop_box = QFrame()
        prop_box.setStyleSheet(f".QFrame {{ background-color: {DesignTokens.BG_PANEL}; border: 1px solid rgba(16,185,129,0.3); border-radius: 4px; padding: 8px; }}")
        prop_layout = QVBoxLayout(prop_box)
        prop_title = QLabel("PROPOSITION MUTÉE IA MCP")
        prop_title.setFont(QFont(DesignTokens.FONT_MAIN, 10, QFont.Weight.Bold))
        prop_title.setStyleSheet(f"color: {DesignTokens.COLOR_GREEN};")
        prop_layout.addWidget(prop_title)

        for key in field_keys:
            val = "-"
            if key == "Recto":
                val = proposal_data.get("Recto") or proposal_data.get("Front") or proposal_data.get("question") or proposal_data.get("Texte") or "-"
            elif key == "Verso":
                val = proposal_data.get("Verso") or proposal_data.get("Back") or proposal_data.get("reponse") or "-"
            elif key == "Champ Annexe Extra":
                val = proposal_data.get("Champ Annexe Extra") or proposal_data.get("Extra") or proposal_data.get("Remarques extra") or "-"
            else:
                val = proposal_data.get(key, "-")

            lbl = QLabel(f"<b>{key} :</b> {val}")
            lbl.setFont(QFont(DesignTokens.FONT_MAIN, 10))
            lbl.setWordWrap(True)
            lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY};")
            prop_layout.addWidget(lbl)

        grid_layout.addWidget(orig_box)
        grid_layout.addWidget(prop_box)
        layout.addLayout(grid_layout)


class WozniakCardItemWidget(QFrame):
    """Widget de carte problème complet pour le linter Wozniak avec inspecteur déroulant et barre d'action."""

    ignored = Signal()
    applied = Signal(int, dict)

    def __init__(self, item_data: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.item_data = item_data
        self.inspector_visible = False

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            WozniakCardItemWidget {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                padding: 12px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # En-tête de la carte
        h_row = QHBoxLayout()
        h_row.setSpacing(8)

        lbl_title = QLabel(item_data.get("title", "Carte"))
        lbl_title.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
        lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY};")

        badge_text = item_data.get("badge", "Problème")
        badge_variant = "danger" if "atomic" in badge_text.lower() else ("warning" if "interf" in badge_text.lower() else "neutral")
        self.lbl_badge = Badge(badge_text, variant=badge_variant)

        self.btn_inspect = SecondaryButton("Inspecter (5 champs)")
        self.btn_inspect.setIcon(load_phosphor_icon("ph.eye", color=DesignTokens.TEXT_PRIMARY))
        self.btn_inspect.setFixedHeight(24)
        self.btn_inspect.clicked.connect(self.toggle_inspector)

        h_row.addWidget(lbl_title)
        h_row.addWidget(self.lbl_badge)
        h_row.addStretch()
        h_row.addWidget(self.btn_inspect)
        layout.addLayout(h_row)

        # Grille côte à côte (Carte Actuelle vs Proposition MCP)
        side_grid = QHBoxLayout()
        side_grid.setSpacing(10)

        # Gauche (Actuelle)
        orig_panel = QFrame()
        orig_panel.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_MAIN};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 8px;
            }}
        """)
        op_layout = QVBoxLayout(orig_panel)
        op_layout.setSpacing(4)
        op_title = QLabel("CARTE ACTUELLE EN BASE :")
        op_title.setFont(QFont(DesignTokens.FONT_MAIN, 9, QFont.Weight.Bold))
        op_title.setStyleSheet(f"color: {DesignTokens.COLOR_RED}; border: none; background: transparent;")

        orig_dict = item_data.get("original", {})
        orig_val = orig_dict.get("Recto") or orig_dict.get("Front") or orig_dict.get("Texte") or orig_dict.get("Text") or "-"
        op_text = QLabel(orig_val)
        op_text.setFont(QFont(DesignTokens.FONT_MAIN, 10))
        op_text.setWordWrap(True)
        op_text.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")

        op_layout.addWidget(op_title)
        op_layout.addWidget(op_text)

        # Droite (Proposition)
        prop_panel = QFrame()
        prop_panel.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_MAIN};
                border: 1px solid rgba(16,185,129,0.35);
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 8px;
            }}
        """)
        pp_layout = QVBoxLayout(prop_panel)
        pp_layout.setSpacing(4)
        pp_title = QLabel(item_data.get("proposal_summary", "PROPOSITION CORRIGÉE IA :"))
        pp_title.setFont(QFont(DesignTokens.FONT_MAIN, 9, QFont.Weight.Bold))
        pp_title.setStyleSheet(f"color: {DesignTokens.COLOR_GREEN}; border: none; background: transparent;")

        prop_dict = item_data.get("proposal", {})
        prop_val = prop_dict.get("Recto") or prop_dict.get("Front") or prop_dict.get("question") or (list(prop_dict.values())[0] if isinstance(prop_dict, dict) and prop_dict else "-")
        pp_text = QLabel(prop_val)
        pp_text.setFont(QFont(DesignTokens.FONT_MAIN, 10))
        pp_text.setWordWrap(True)
        pp_text.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")

        pp_layout.addWidget(pp_title)
        pp_layout.addWidget(pp_text)

        side_grid.addWidget(orig_panel)
        side_grid.addWidget(prop_panel)
        layout.addLayout(side_grid)

        # Panneau Inspecteur déroulant
        self.inspector_widget = FieldInspectorWidget(
            original_data=item_data.get("original", {}),
            proposal_data=item_data.get("proposal", {}),
        )
        self.inspector_widget.setVisible(False)
        layout.addWidget(self.inspector_widget)

        # Barre d'action inférieure
        act_bar = QFrame()
        act_bar.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_MAIN};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        ab_layout = QHBoxLayout(act_bar)
        ab_layout.setContentsMargins(8, 4, 8, 4)
        ab_layout.setSpacing(8)

        chk_synthese = QCheckBox("Générer la Carte Synthèse Master (#synthese)")
        chk_synthese.setChecked(True)
        chk_synthese.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 10px; border: none; background: transparent;")

        self.btn_ignore = SecondaryButton("Ignorer (Faux Positif)")
        self.btn_ignore.setIcon(load_phosphor_icon("ph.x", color=DesignTokens.TEXT_MUTED))
        self.btn_ignore.setFixedHeight(24)
        self.btn_ignore.clicked.connect(self.on_ignore)

        self.btn_consult_ai = SecondaryButton("Consulter l'IA")
        self.btn_consult_ai.setIcon(load_phosphor_icon("ph.sparkle", color=DesignTokens.COLOR_PURPLE))
        self.btn_consult_ai.setToolTip("Ouvrir cette carte dans le Consultant IA")
        self.btn_consult_ai.setFixedHeight(24)
        self.btn_consult_ai.clicked.connect(self.on_consult_ai)

        self.btn_apply = PrimaryButton("Appliquer la Correction")
        self.btn_apply.setIcon(load_phosphor_icon("ph.check", color="#ffffff"))
        self.btn_apply.setFixedHeight(24)
        self.btn_apply.clicked.connect(self.on_apply)

        ab_layout.addWidget(chk_synthese)
        ab_layout.addStretch()
        ab_layout.addWidget(self.btn_consult_ai)
        ab_layout.addWidget(self.btn_ignore)
        ab_layout.addWidget(self.btn_apply)
        layout.addWidget(act_bar)

    def toggle_inspector(self) -> None:
        self.inspector_visible = not self.inspector_visible
        self.inspector_widget.setVisible(self.inspector_visible)
        self.btn_inspect.setText("Fermer l'inspecteur" if self.inspector_visible else "Inspecter les 5 champs")

    def on_ignore(self) -> None:
        self.setVisible(False)
        self.ignored.emit()

    def on_consult_ai(self) -> None:
        nid = self.item_data.get("note_id")
        rule_name = self.item_data.get("badge", "Règle Wozniak")
        if nid:
            from ankiforge.utils.event_bus import OpenConsultantRequestedEvent, event_bus

            event_bus.publish(
                OpenConsultantRequestedEvent(
                    context_item=f"card_{nid}",
                    initial_prompt=f"La note #{nid} a enfreint la règle '{rule_name}'. Analyse et propose une refactorisation ergonomique.",
                )
            )

    def on_apply(self) -> None:
        nid = self.item_data.get("note_id")
        proposal = self.item_data.get("proposal", {})
        if nid:
            self.applied.emit(nid, proposal)
        self.setVisible(False)


class KatexLivePreviewWidget(QFrame):
    """Panneau interactif Live Preview KaTeX pour tester dynamiquement les formules."""

    def __init__(self, initial_formula: str = r"\int_{-\infty}^{\infty} |f(t)|^2 dt", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            KatexLivePreviewWidget {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                border-radius: 6px;
                padding: 8px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        lbl_title = QLabel("Panneau Live Preview KaTeX (Interactif)")
        lbl_title.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
        lbl_title.setStyleSheet(f"color: {DesignTokens.ACCENT_PRIMARY};")
        layout.addWidget(lbl_title)

        self.input_formula = QLineEdit(initial_formula)
        self.input_formula.setStyleSheet(f"""
            QLineEdit {{
                background-color: {DesignTokens.BG_MAIN};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                color: {DesignTokens.TEXT_PRIMARY};
                font-family: {DesignTokens.FONT_CODE};
                font-size: 11px;
                padding: 4px 8px;
                border-radius: 4px;
            }}
        """)
        self.input_formula.textChanged.connect(self._on_formula_changed)
        layout.addWidget(self.input_formula)

        self.canvas_preview = QLabel()
        self.canvas_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.canvas_preview.setStyleSheet(f"""
            QLabel {{
                background-color: {DesignTokens.BG_MAIN};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                padding: 12px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 14px;
                font-family: {DesignTokens.FONT_CODE};
            }}
        """)
        layout.addWidget(self.canvas_preview)
        self._on_formula_changed(initial_formula)

    def _on_formula_changed(self, text: str) -> None:
        clean = text.strip()
        self.canvas_preview.setText(f"\\[ {clean} \\]")


class RetentionCurveCanvas(QWidget):
    """Visualiseur graphique QPainter pour la courbe de l'oubli FSRS-4.5."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(110)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        left_margin = 35
        right_margin = 25
        top_margin = 15
        bottom_margin = 25
        plot_w = w - left_margin - right_margin
        plot_h = h - top_margin - bottom_margin

        # Background Frame
        painter.fillRect(0, 0, w, h, QColor(DesignTokens.BG_MAIN))

        # Y-Axis Grid lines (100%, 90%, 80%, 70%)
        pen_grid = QPen(QColor(DesignTokens.BORDER_COLOR), 1, Qt.PenStyle.DashLine)
        painter.setPen(pen_grid)
        painter.setFont(QFont(DesignTokens.FONT_MAIN, 8))

        y_100 = top_margin
        y_90 = int(top_margin + plot_h * 0.33)
        y_80 = int(top_margin + plot_h * 0.66)
        y_bottom = top_margin + plot_h

        painter.drawLine(left_margin, y_100, w - right_margin, y_100)
        painter.drawLine(left_margin, y_80, w - right_margin, y_80)
        painter.drawLine(left_margin, y_bottom, w - right_margin, y_bottom)

        # Target 90% Line (Green dashed)
        pen_target = QPen(QColor(16, 185, 129, 180), 1.5, Qt.PenStyle.DashLine)
        painter.setPen(pen_target)
        painter.drawLine(left_margin, y_90, w - right_margin, y_90)

        # Y-Axis Labels
        painter.setPen(QColor(DesignTokens.TEXT_MUTED))
        painter.drawText(5, y_100 + 4, "100%")
        painter.setPen(QColor(DesignTokens.COLOR_GREEN))
        painter.drawText(5, y_90 + 4, " 90%")
        painter.setPen(QColor(DesignTokens.TEXT_MUTED))
        painter.drawText(5, y_80 + 4, " 80%")

        # X-Axis Time Labels
        days = [("J0", 0.0), ("J1", 0.15), ("J7", 0.4), ("J30", 0.7), ("J90", 1.0)]
        for label, pos_factor in days:
            x_pos = int(left_margin + plot_w * pos_factor)
            painter.setPen(QColor(DesignTokens.TEXT_MUTED))
            painter.drawText(x_pos - 10, h - 6, label)

        # Area under curve gradient
        path_fill = QPainterPath()
        path_fill.moveTo(left_margin, y_bottom)
        path_fill.lineTo(left_margin, y_100)
        path_fill.cubicTo(
            left_margin + int(plot_w * 0.3),
            y_100 + int(plot_h * 0.2),
            left_margin + int(plot_w * 0.65),
            y_90 + int(plot_h * 0.2),
            left_margin + plot_w,
            y_80 + 8,
        )
        path_fill.lineTo(left_margin + plot_w, y_bottom)
        path_fill.closeSubpath()

        grad = QLinearGradient(0, y_100, 0, y_bottom)
        grad.setColorAt(0.0, QColor(99, 102, 241, 60))
        grad.setColorAt(1.0, QColor(99, 102, 241, 0))
        painter.fillPath(path_fill, QBrush(grad))

        # Retention Curve Path
        path_curve = QPainterPath()
        path_curve.moveTo(left_margin, y_100)
        path_curve.cubicTo(
            left_margin + int(plot_w * 0.3),
            y_100 + int(plot_h * 0.2),
            left_margin + int(plot_w * 0.65),
            y_90 + int(plot_h * 0.2),
            left_margin + plot_w,
            y_80 + 8,
        )

        pen_curve = QPen(QColor(DesignTokens.ACCENT_PRIMARY), 2.5)
        painter.setPen(pen_curve)
        painter.drawPath(path_curve)

        # Key Points Dots
        points = [
            (left_margin, y_100, DesignTokens.ACCENT_PRIMARY),
            (left_margin + int(plot_w * 0.4), y_90, DesignTokens.COLOR_GREEN),
            (left_margin + plot_w, y_80 + 8, DesignTokens.COLOR_YELLOW),
        ]
        for px, py, p_color in points:
            painter.setPen(QPen(QColor(DesignTokens.BG_PANEL), 2))
            painter.setBrush(QBrush(QColor(p_color)))
            painter.drawEllipse(px - 4, py - 4, 8, 8)


class SourceDiagnosticCardWidget(QFrame):
    """Carte de diagnostic et santé documentaire pour l'onglet Documents du menu d'analyse."""

    inspect_requested = Signal(int)

    def __init__(self, data: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.data = data
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            SourceDiagnosticCardWidget {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 8px;
            }}
            SourceDiagnosticCardWidget:hover {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
                background-color: {DesignTokens.BG_HOVER};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Header: Icon + Title and Score
        h_header = QHBoxLayout()
        ext = str(data.get("extension", "md")).lower()
        title = str(data.get("title", "Document"))
        coverage_pct = float(data.get("coverage_pct", 0.0))
        is_indexed = bool(data.get("is_indexed", False))

        icon_name = "ph.file-text"
        icon_color = DesignTokens.TEXT_MUTED
        if ext == "pdf":
            icon_name = "ph.file-pdf"
            icon_color = DesignTokens.COLOR_RED
        elif ext in ("md", "markdown"):
            icon_name = "ph.file-text"
            icon_color = DesignTokens.COLOR_BLUE
        elif ext == "png":
            icon_name = "ph.image"
            icon_color = DesignTokens.COLOR_YELLOW
        elif ext in ("yt", "youtube"):
            icon_name = "ph.youtube-logo"
            icon_color = DesignTokens.COLOR_RED
        elif ext == "web":
            icon_name = "ph.globe"
            icon_color = DesignTokens.COLOR_BLUE

        lbl_icon = QLabel()
        lbl_icon.setPixmap(load_phosphor_icon(icon_name, color=icon_color).pixmap(18, 18))
        lbl_icon.setStyleSheet("border: none; background: transparent;")

        lbl_title = QLabel(title)
        lbl_title.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
        lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")
        lbl_title.setToolTip(title)

        # Badge Couverture
        lbl_score = QLabel(f"{coverage_pct:.0f}% Couvert" if is_indexed else "Non indexé")
        lbl_score.setFont(QFont(DesignTokens.FONT_MAIN, 9, QFont.Weight.Bold))
        if not is_indexed:
            lbl_score.setStyleSheet(
                f"background-color: {DesignTokens.BG_HOVER}; color: {DesignTokens.TEXT_MUTED}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 4px; padding: 2px 6px;"
            )
        elif coverage_pct >= 90:
            lbl_score.setStyleSheet(f"background-color: rgba(16,185,129,0.15); color: {DesignTokens.COLOR_GREEN}; border: 1px solid rgba(16,185,129,0.3); border-radius: 4px; padding: 2px 6px;")
        elif coverage_pct >= 50:
            lbl_score.setStyleSheet(f"background-color: rgba(245,158,11,0.15); color: {DesignTokens.COLOR_YELLOW}; border: 1px solid rgba(245,158,11,0.3); border-radius: 4px; padding: 2px 6px;")
        else:
            lbl_score.setStyleSheet(f"background-color: rgba(239,68,68,0.15); color: {DesignTokens.COLOR_RED}; border: 1px solid rgba(239,68,68,0.3); border-radius: 4px; padding: 2px 6px;")

        h_header.addWidget(lbl_icon)
        h_header.addWidget(lbl_title, 1)
        h_header.addWidget(lbl_score)
        layout.addLayout(h_header)

        # Micro Progress Bar
        bar_bg = QFrame()
        bar_bg.setFixedHeight(4)
        bar_bg.setStyleSheet(f".QFrame {{ background-color: {DesignTokens.BG_INPUT}; border-radius: 2px; }}")
        b_ly = QHBoxLayout(bar_bg)
        b_ly.setContentsMargins(0, 0, 0, 0)
        b_ly.setSpacing(0)
        if coverage_pct > 0:
            bar_fg = QFrame()
            bar_color = DesignTokens.COLOR_GREEN if coverage_pct >= 90 else (DesignTokens.COLOR_YELLOW if coverage_pct >= 50 else DesignTokens.COLOR_RED)
            bar_fg.setStyleSheet(f".QFrame {{ background-color: {bar_color}; border-radius: 2px; }}")
            b_ly.addWidget(bar_fg, stretch=int(coverage_pct))
            b_ly.addStretch(int(100 - coverage_pct))
        layout.addWidget(bar_bg)

        # Body: Real Stats
        grid_stats = QVBoxLayout()
        grid_stats.setSpacing(5)

        total_chunks = data.get("total_chunks", 0)
        covered_chunks = data.get("covered_chunks", 0)
        orphan_chunks = data.get("orphan_chunks", 0)
        total_cards = data.get("total_cards", 0)
        density = data.get("density", 0.0)
        faiss_status = "Prêt (FAISS)" if is_indexed else "Non indexé"

        stats = [
            ("Sections couvertes :", f"{covered_chunks} / {total_chunks}" if total_chunks > 0 else "0", covered_chunks > 0),
            ("Trous (orphelines) :", f"{orphan_chunks} section(s)" if orphan_chunks > 0 else "Couverture totale", orphan_chunks > 0),
            ("Cartes Anki liées :", f"{total_cards} cartes", True),
            ("Densité :", f"{density:.1f} cartes / sec", False),
            ("Index Vectoriel :", faiss_status, False),
        ]

        for label, val, highlight in stats:
            row = QHBoxLayout()
            lbl_k = QLabel(label)
            lbl_k.setFont(QFont(DesignTokens.FONT_MAIN, 9))
            lbl_k.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")

            lbl_v = QLabel(val)
            lbl_v.setFont(QFont(DesignTokens.FONT_MAIN, 9, QFont.Weight.Bold))
            if label.startswith("Trous") and orphan_chunks > 0:
                lbl_v.setStyleSheet(f"color: {DesignTokens.COLOR_YELLOW}; border: none; background: transparent;")
            elif label.startswith("Cartes"):
                lbl_v.setStyleSheet(f"color: {DesignTokens.COLOR_GREEN}; border: none; background: transparent;")
            elif highlight:
                lbl_v.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")
            else:
                lbl_v.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; border: none; background: transparent;")

            row.addWidget(lbl_k)
            row.addStretch()
            row.addWidget(lbl_v)
            grid_stats.addLayout(row)

        layout.addLayout(grid_stats)

        # Divider
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"background-color: {DesignTokens.BORDER_COLOR}; border: none;")
        layout.addWidget(line)

        # Footer
        h_foot = QHBoxLayout()
        words_cnt = data.get("word_count", 0)
        lbl_foot = QLabel(f".{ext.upper()} · {words_cnt:,} mots")
        lbl_foot.setFont(QFont(DesignTokens.FONT_CODE, 9))
        lbl_foot.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")

        btn_inspect = SecondaryButton("Inspecter l'audit")
        btn_inspect.setIcon(load_phosphor_icon("ph.magnifying-glass", color=DesignTokens.TEXT_PRIMARY))
        btn_inspect.setFixedHeight(26)
        doc_id = data.get("doc_id", -1)
        btn_inspect.clicked.connect(lambda: self.inspect_requested.emit(doc_id))

        h_foot.addWidget(lbl_foot)
        h_foot.addStretch()
        h_foot.addWidget(btn_inspect)
        layout.addLayout(h_foot)
