from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ankiforge.services.ai.linter import TokenSrsFinancialService
from ankiforge.services.audit.fsrs_projection_service import FsrsProjectionService
from ankiforge.services.audit.leech_service import LeechService
from ankiforge.ui.components.badges import Badge
from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton
from ankiforge.ui.components.deck_select_window import ALL_DECKS_NODE_ID, DeckSelectWindow
from ankiforge.ui.dialogs.leech_wozniak_split_dialog import LeechWozniakSplitDialog
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.retention_curve import RetentionCurveWidget
from ankiforge.utils.i18n import tr
from ankiforge.utils.icon_loader import load_on_accent_icon, load_phosphor_icon


class AITokensSrsTab(QWidget):
    """Onglet de suivi financier des jetons et de santé d'apprentissage SRS."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.current_deck_id: int | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # 1. Header
        header = QFrame()
        header.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(12, 8, 12, 8)
        h_layout.setSpacing(10)

        ico_header = QLabel()
        ico_header.setPixmap(load_phosphor_icon("ph.coins", color=DesignTokens.COLOR_YELLOW, weight="fill").pixmap(18, 18))
        ico_header.setStyleSheet("border: none; background: transparent;")

        lbl_title = QLabel(self.tr("Finances & Rétention SRS"))
        lbl_title.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
        lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")

        self.btn_deck = SecondaryButton("L'ensemble des paquets", tooltip=self.tr("Choisir le paquet de cartes à auditer"))
        self.btn_deck.setIcon(load_phosphor_icon("ph.cards", color=DesignTokens.TEXT_PRIMARY))
        self.btn_deck.setFixedHeight(28)
        self.btn_deck.clicked.connect(self.open_deck_select_dialog)

        self.lbl_spent = QLabel(self.tr("Dépenses : 0.0000 $"))
        self.lbl_spent.setFont(QFont(DesignTokens.FONT_MAIN, 9, QFont.Weight.Bold))
        self.lbl_spent.setStyleSheet(
            f"background-color: {DesignTokens.COLOR_GREEN_BG}; color: {DesignTokens.COLOR_GREEN}; border: 1px solid {DesignTokens.COLOR_GREEN_BORDER}; border-radius: 9999px; padding: 3px 10px;"
        )

        self.lbl_cost = QLabel(self.tr("~0.00000 $ / carte"))
        self.lbl_cost.setFont(QFont(DesignTokens.FONT_MAIN, 9))
        self.lbl_cost.setStyleSheet(
            f"background-color: {DesignTokens.BG_INPUT}; color: {DesignTokens.TEXT_MUTED}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 9999px; padding: 3px 10px;"
        )

        btn_analyze = PrimaryButton("Analyser ce paquet", tooltip=self.tr("Rafraîchir les métriques de tokens, dépenses IA et rétention SRS"))
        btn_analyze.setIcon(load_on_accent_icon("ph.arrows-clockwise"))
        btn_analyze.setFixedHeight(28)
        btn_analyze.clicked.connect(self.refresh_stats)

        h_layout.addWidget(ico_header)
        h_layout.addWidget(lbl_title)
        h_layout.addSpacing(6)
        h_layout.addWidget(self.btn_deck)
        h_layout.addStretch()
        h_layout.addWidget(self.lbl_spent)
        h_layout.addWidget(self.lbl_cost)
        h_layout.addWidget(btn_analyze)
        layout.addWidget(header)

        # 2. 4 KPI Summary Cards
        self.kpi_grid = QHBoxLayout()
        self.kpi_grid.setSpacing(10)
        layout.addLayout(self.kpi_grid)

        # 3. Main 2-Column Grid
        main_grid = QHBoxLayout()
        main_grid.setSpacing(10)

        # Left Column
        self.left_col = QFrame()
        self.left_col.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        self.l_layout = QVBoxLayout(self.left_col)
        self.l_layout.setContentsMargins(12, 12, 12, 12)
        self.l_layout.setSpacing(10)

        h_ltitle = QHBoxLayout()
        ico_models = QLabel()
        ico_models.setPixmap(load_phosphor_icon("ph.cpu", color=DesignTokens.COLOR_BLUE).pixmap(16, 16))
        ico_models.setStyleSheet("border: none; background: transparent;")
        l_title = QLabel(self.tr("Dépenses par Fournisseur IA & Modèle"))
        l_title.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
        l_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")
        h_ltitle.addWidget(ico_models)
        h_ltitle.addWidget(l_title)
        h_ltitle.addStretch()

        self.l_layout.addLayout(h_ltitle)

        div_l = QFrame()
        div_l.setFrameShape(QFrame.Shape.HLine)
        div_l.setStyleSheet(f"background-color: {DesignTokens.BORDER_COLOR}; border: none;")
        self.l_layout.addWidget(div_l)

        self.models_container = QVBoxLayout()
        self.models_container.setSpacing(8)
        self.l_layout.addLayout(self.models_container)

        self.tasks_container = QVBoxLayout()
        self.tasks_container.setSpacing(8)
        self.l_layout.addLayout(self.tasks_container)

        self.l_layout.addStretch()
        main_grid.addWidget(self.left_col, 1)

        # Right Column
        right_col = QFrame()
        right_col.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        r_layout = QVBoxLayout(right_col)
        r_layout.setContentsMargins(12, 12, 12, 12)
        r_layout.setSpacing(10)

        eq_box = QFrame()
        eq_box.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_MAIN};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        eq_layout = QVBoxLayout(eq_box)
        eq_layout.setContentsMargins(10, 10, 10, 10)
        eq_layout.setSpacing(8)

        h_eqtitle = QHBoxLayout()
        ico_eq = QLabel()
        ico_eq.setPixmap(load_phosphor_icon("ph.chart-pie", color=DesignTokens.COLOR_PURPLE).pixmap(16, 16))
        ico_eq.setStyleSheet("border: none; background: transparent;")
        eq_title = QLabel(self.tr("Équilibre & Maturité du Paquet"))
        eq_title.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
        eq_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")
        h_eqtitle.addWidget(ico_eq)
        h_eqtitle.addWidget(eq_title)
        h_eqtitle.addStretch()
        eq_layout.addLayout(h_eqtitle)

        self.eq_grid = QHBoxLayout()
        self.eq_grid.setSpacing(8)
        eq_layout.addLayout(self.eq_grid)
        r_layout.addWidget(eq_box)

        self.retention_curve = RetentionCurveWidget()
        r_layout.addWidget(self.retention_curve)

        r_layout.addStretch()
        main_grid.addWidget(right_col, 1)

        layout.addLayout(main_grid, 0)
        self._setup_leech_panel(layout)
        self.refresh_stats()

    def _clear_layout(self, layout):
        if layout is not None:
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
                elif item.layout() is not None:
                    self._clear_layout(item.layout())

    def refresh_stats(self):
        summary = TokenSrsFinancialService.get_financial_summary(self.current_deck_id)
        projection = FsrsProjectionService.project(self.current_deck_id)

        self.lbl_spent.setText(tr("Dépenses : %1 $", f"{summary['total_spent_usd']:.4f}"))
        avg_cost = summary["total_spent_usd"] / max(summary["total_cards"], 1)
        self.lbl_cost.setText(tr("~%1 $ / carte", f"{avg_cost:.5f}"))

        self._clear_layout(self.kpi_grid)
        self._clear_layout(self.eq_grid)
        self._clear_layout(self.models_container)
        self._clear_layout(self.tasks_container)

        self.retention_curve.set_projection(projection)

        mat_pct = "0%" if summary["total_cards"] == 0 else f"{summary['maturing_cards'] / summary['total_cards'] * 100:.1f}%"
        retention_j7 = self._checkpoint_retention(projection, day=7)
        target_pct = float(projection.get("retention_target", 0.90)) * 100
        retention_detail = self.tr("Aucune carte révisée")
        if projection.get("available"):
            retention_detail = tr("Cible : %1%% · J+14 : %2%%", f"{target_pct:.0f}", f"{self._checkpoint_retention(projection, day=14) * 100:.1f}")
        cards_data = [
            (
                "ph.coins",
                self.tr("Budget Consommé"),
                f"{summary['total_spent_usd']:.4f} $",
                tr("%1 jetons · Optimal", f"{summary['tokens_consumed']:,}"),
                DesignTokens.COLOR_GREEN,
            ),
            (
                "ph.target",
                self.tr("Rétention Projetée (J+7)"),
                f"{retention_j7 * 100:.1f}%",
                retention_detail,
                DesignTokens.ACCENT_PRIMARY,
            ),
            (
                "ph.sparkle",
                self.tr("Cartes Mûres (>21j)"),
                f"{summary['maturing_cards']:,} / {summary['total_cards']:,}",
                tr("%1 · Ancrage fort", mat_pct),
                DesignTokens.SYNTAX_KEYWORD,
            ),
            (
                "ph.clock",
                self.tr("Charge à l'Équilibre"),
                tr("%1 / jour", f"{float(projection.get('equilibrium_load_per_day', 0.0)):.1f}"),
                self.tr("Révisions/j · Σ 1/intervalle"),
                DesignTokens.COLOR_BLUE,
            ),
        ]

        for icon_name, title, val, sub_text, color in cards_data:
            box = QFrame()
            box.setStyleSheet(f"""
                QFrame {{
                    background-color: {DesignTokens.BG_PANEL};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: {DesignTokens.RADIUS_MD}px;
                }}
            """)
            b_layout = QVBoxLayout(box)
            b_layout.setContentsMargins(12, 10, 12, 10)
            b_layout.setSpacing(4)

            h_top = QHBoxLayout()
            h_top.setSpacing(6)
            ico = QLabel()
            ico.setPixmap(load_phosphor_icon(icon_name, color=color).pixmap(14, 14))
            ico.setStyleSheet("border: none; background: transparent;")
            t_lbl = QLabel(title)
            t_lbl.setFont(QFont(DesignTokens.FONT_MAIN, 9, QFont.Weight.Bold))
            t_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")
            h_top.addWidget(ico)
            h_top.addWidget(t_lbl)
            h_top.addStretch()

            v_lbl = QLabel(val)
            v_lbl.setFont(QFont(DesignTokens.FONT_MAIN, 14, QFont.Weight.Bold))
            v_lbl.setStyleSheet(f"color: {color}; border: none; background: transparent;")

            s_lbl = QLabel(sub_text)
            s_lbl.setFont(QFont(DesignTokens.FONT_MAIN, 8))
            s_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; border: none; background: transparent;")

            b_layout.addLayout(h_top)
            b_layout.addWidget(v_lbl)
            b_layout.addWidget(s_lbl)
            self.kpi_grid.addWidget(box)

        eq_data = []
        tot = summary["total_cards"]
        dist = summary["maturity_distribution"]
        buckets = (
            (self.tr("NOUVELLES"), dist["new"], DesignTokens.COLOR_BLUE),
            (self.tr("APPRENTISSAGE"), dist["learning"], DesignTokens.COLOR_YELLOW),
            (self.tr("MÛRES (>21j)"), dist["maturing"], DesignTokens.SYNTAX_KEYWORD),
        )
        for label, count, color in buckets:
            pct = f"{count / tot * 100:.1f}%" if tot > 0 else "0%"
            eq_data.append((label, str(count), pct, color))

        for lbl, val, sub, col in eq_data:
            bx = QFrame()
            bx.setStyleSheet(f"""
                QFrame {{
                    background-color: {DesignTokens.BG_PANEL};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: {DesignTokens.RADIUS_SM}px;
                }}
            """)
            b_ly = QVBoxLayout(bx)
            b_ly.setContentsMargins(8, 8, 8, 8)
            b_ly.setSpacing(2)
            b_ly.setAlignment(Qt.AlignmentFlag.AlignCenter)
            t = QLabel(lbl)
            t.setFont(QFont(DesignTokens.FONT_MAIN, 8, QFont.Weight.Bold))
            t.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")
            v = QLabel(val)
            v.setFont(QFont(DesignTokens.FONT_MAIN, 13, QFont.Weight.Bold))
            v.setStyleSheet(f"color: {col}; border: none; background: transparent;")
            s = QLabel(sub)
            s.setFont(QFont(DesignTokens.FONT_MAIN, 8))
            s.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; border: none; background: transparent;")
            b_ly.addWidget(t, 0, Qt.AlignmentFlag.AlignCenter)
            b_ly.addWidget(v, 0, Qt.AlignmentFlag.AlignCenter)
            b_ly.addWidget(s, 0, Qt.AlignmentFlag.AlignCenter)
            self.eq_grid.addWidget(bx)

        for m in summary["models"]:
            m_name = m["name"]
            m_box = QFrame()
            m_box.setStyleSheet(f"""
                QFrame {{
                    background-color: {DesignTokens.BG_MAIN};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: {DesignTokens.RADIUS_SM}px;
                }}
            """)
            mb_layout = QVBoxLayout(m_box)
            mb_layout.setContentsMargins(10, 8, 10, 8)
            mb_layout.setSpacing(4)

            p_icon = "ph.cpu"
            p_color = DesignTokens.COLOR_BLUE
            p_tag = "Modèle IA"
            m_lower = m_name.lower()

            if "gemini" in m_lower:
                p_icon = "ph.sparkle"
                p_color = DesignTokens.COLOR_BLUE
                p_tag = "Google Gemini"
            elif any(k in m_lower for k in ("qwen", "llama", "mistral", "ollama")):
                p_icon = "ph.terminal"
                p_color = DesignTokens.COLOR_GREEN
                p_tag = "Ollama Local"
            elif any(k in m_lower for k in ("gpt", "openai")):
                p_icon = "ph.brain"
                p_color = DesignTokens.COLOR_GREEN
                p_tag = "OpenAI"
            elif any(k in m_lower for k in ("claude", "anthropic")):
                p_icon = "ph.chat-teardrop-dots"
                p_color = DesignTokens.COLOR_YELLOW
                p_tag = "Anthropic"
            elif any(k in m_lower for k in ("local", "marker", "whisper")):
                p_icon = "ph.hard-drives"
                p_color = DesignTokens.COLOR_GREEN
                p_tag = "Moteur Local GPU"

            r1 = QHBoxLayout()
            ico_m = QLabel()
            ico_m.setPixmap(load_phosphor_icon(p_icon, color=p_color).pixmap(14, 14))
            ico_m.setStyleSheet("border: none; background: transparent;")

            name = QLabel(m_name)
            name.setFont(QFont(DesignTokens.FONT_MAIN, 10, QFont.Weight.Bold))
            name.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")

            cost = QLabel(f"{m['cost_usd']:.4f} $")
            cost.setFont(QFont(DesignTokens.FONT_MAIN, 10, QFont.Weight.Bold))
            cost.setStyleSheet(f"color: {DesignTokens.COLOR_GREEN}; border: none; background: transparent;")

            r1.addWidget(ico_m)
            r1.addWidget(name, 1)
            r1.addWidget(cost)
            mb_layout.addLayout(r1)

            det = QLabel(tr("%1 · %2 jetons (%3%% des dépenses)", p_tag, f"{m['tokens']:,}", f"{m['pct']:.1f}"))
            det.setFont(QFont(DesignTokens.FONT_MAIN, 8))
            det.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")
            mb_layout.addWidget(det)

            pct_val = max(0, min(100, int(m["pct"])))
            p_bg = QFrame()
            p_bg.setFixedHeight(3)
            p_bg.setStyleSheet(f"background-color: {DesignTokens.BG_INPUT}; border-radius: 1px;")
            p_ly = QHBoxLayout(p_bg)
            p_ly.setContentsMargins(0, 0, 0, 0)
            p_ly.setSpacing(0)
            if pct_val > 0:
                p_fg = QFrame()
                p_fg.setStyleSheet(f"background-color: {p_color}; border-radius: 1px;")
                p_ly.addWidget(p_fg, stretch=pct_val)
                p_ly.addStretch(100 - pct_val)
            mb_layout.addWidget(p_bg)

            self.models_container.addWidget(m_box)

        task_box = QFrame()
        task_box.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_MAIN};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        tb_layout = QVBoxLayout(task_box)
        tb_layout.setContentsMargins(10, 8, 10, 8)
        tb_layout.setSpacing(8)

        h_tbtitle = QHBoxLayout()
        ico_task = QLabel()
        ico_task.setPixmap(load_phosphor_icon("ph.list-checks", color=DesignTokens.TEXT_MUTED).pixmap(14, 14))
        ico_task.setStyleSheet("border: none; background: transparent;")
        tb_title = QLabel(self.tr("Répartition par Type de Tâche IA"))
        tb_title.setFont(QFont(DesignTokens.FONT_MAIN, 9, QFont.Weight.Bold))
        tb_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")
        h_tbtitle.addWidget(ico_task)
        h_tbtitle.addWidget(tb_title)
        h_tbtitle.addStretch()
        tb_layout.addLayout(h_tbtitle)

        tasks = []
        for t in summary.get("tasks_breakdown", []):
            tasks.append((t["task"], f"{t['cost_usd']:.4f} $ ({t['pct']:.1f}%)", int(t["pct"]), t.get("color", DesignTokens.COLOR_BLUE)))

        for t_name, t_val, t_pct, t_col in tasks:
            t_row = QVBoxLayout()
            t_row.setSpacing(2)

            lbl_row = QHBoxLayout()
            n_lbl = QLabel(t_name)
            n_lbl.setFont(QFont(DesignTokens.FONT_MAIN, 8))
            n_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; border: none; background: transparent;")
            v_lbl = QLabel(t_val)
            v_lbl.setFont(QFont(DesignTokens.FONT_MAIN, 8, QFont.Weight.Bold))
            v_lbl.setStyleSheet(f"color: {DesignTokens.COLOR_GREEN}; border: none; background: transparent;")
            lbl_row.addWidget(n_lbl)
            lbl_row.addStretch()
            lbl_row.addWidget(v_lbl)
            t_row.addLayout(lbl_row)

            p_bg = QFrame()
            p_bg.setFixedHeight(3)
            p_bg.setStyleSheet(f"background-color: {DesignTokens.BG_INPUT}; border-radius: 1px;")
            p_ly = QHBoxLayout(p_bg)
            p_ly.setContentsMargins(0, 0, 0, 0)
            p_ly.setSpacing(0)
            if t_pct > 0:
                p_fg = QFrame()
                p_fg.setStyleSheet(f"background-color: {t_col}; border-radius: 1px;")
                p_ly.addWidget(p_fg, stretch=t_pct)
                p_ly.addStretch(100 - t_pct)

            t_row.addWidget(p_bg)
            tb_layout.addLayout(t_row)

        self.tasks_container.addWidget(task_box)
        self._refresh_leeches()

    def refresh_theme(self, profile: Any) -> None:
        """Réapplique les couleurs du thème actif au widget de courbe de rétention."""
        if hasattr(self, "retention_curve"):
            self.retention_curve.refresh_theme(profile)

    @staticmethod
    def _checkpoint_retention(projection: dict[str, Any], day: int) -> float:
        """Fraction de rétention projetée au repère ``day`` (0.0 si indisponible)."""
        for checkpoint in projection.get("checkpoints", []):
            if int(checkpoint.get("day", -1)) == day:
                return float(checkpoint.get("retention", 0.0))
        return 0.0

    def _setup_leech_panel(self, parent_layout: QVBoxLayout) -> None:
        """Initialise le panneau pleine largeur de diagnostic des cartes sangsues (ADR 0019)."""
        self.leech_panel = QFrame()
        self.leech_panel.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        lp_layout = QVBoxLayout(self.leech_panel)
        lp_layout.setContentsMargins(12, 10, 12, 10)
        lp_layout.setSpacing(8)

        # En-tête du panneau
        h_row = QHBoxLayout()
        h_row.setSpacing(8)

        ico_leech = QLabel()
        ico_leech.setPixmap(load_phosphor_icon("ph.bug", color=DesignTokens.COLOR_RED, weight="fill").pixmap(18, 18))
        ico_leech.setStyleSheet("border: none; background: transparent;")

        self.lbl_leech_title = QLabel(self.tr("Diagnostic des Cartes Sangsues (Leeches)"))
        self.lbl_leech_title.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
        self.lbl_leech_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")

        self.badge_leech_count = Badge(self.tr("0 sangsue"), color=DesignTokens.COLOR_GREEN)

        self.cb_include_high_lapses = QCheckBox(self.tr("Inclure rechutes fréquentes"))
        self.cb_include_high_lapses.setToolTip(self.tr("Inclut les cartes avec un nombre élevé d'échecs même si elles ne sont pas encore tagguées 'leech' par Anki"))
        self.cb_include_high_lapses.setChecked(False)
        self.cb_include_high_lapses.toggled.connect(self._on_leech_filter_changed)

        self.spn_lapse_threshold = QSpinBox()
        self.spn_lapse_threshold.setRange(2, 50)
        self.spn_lapse_threshold.setValue(4)
        self.spn_lapse_threshold.setPrefix("≥ ")
        self.spn_lapse_threshold.setSuffix(self.tr(" oublis"))
        self.spn_lapse_threshold.setEnabled(False)
        self.spn_lapse_threshold.valueChanged.connect(self._on_leech_filter_changed)

        btn_refresh_leeches = SecondaryButton("", tooltip=self.tr("Rafraîchir les cartes sangsues"))
        btn_refresh_leeches.setIcon(load_phosphor_icon("ph.arrows-clockwise", color=DesignTokens.TEXT_PRIMARY))
        btn_refresh_leeches.setFixedHeight(26)
        btn_refresh_leeches.clicked.connect(self._refresh_leeches)

        h_row.addWidget(ico_leech)
        h_row.addWidget(self.lbl_leech_title)
        h_row.addWidget(self.badge_leech_count)
        h_row.addStretch()
        h_row.addWidget(self.cb_include_high_lapses)
        h_row.addWidget(self.spn_lapse_threshold)
        h_row.addWidget(btn_refresh_leeches)
        lp_layout.addLayout(h_row)

        # Tableau des sangsues
        self.table_leeches = QTableWidget()
        self.table_leeches.setColumnCount(9)
        self.table_leeches.setHorizontalHeaderLabels(
            [
                self.tr("ID"),
                self.tr("Paquet"),
                self.tr("Face"),
                self.tr("Oublis"),
                self.tr("Stabilité"),
                self.tr("Difficulté"),
                self.tr("Extrait Recto"),
                self.tr("Extrait Verso"),
                self.tr("Action"),
            ]
        )
        self.table_leeches.verticalHeader().setVisible(False)
        self.table_leeches.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_leeches.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table_leeches.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_leeches.setMinimumHeight(140)
        self.table_leeches.setMaximumHeight(220)
        self.table_leeches.setStyleSheet(f"""
            QTableWidget {{
                background-color: {DesignTokens.BG_MAIN};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                gridline-color: {DesignTokens.BORDER_COLOR};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QHeaderView::section {{
                background-color: {DesignTokens.BG_PANEL};
                color: {DesignTokens.TEXT_SECONDARY};
                font-weight: bold;
                border: none;
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
                padding: 4px 6px;
            }}
        """)

        tbl_header = self.table_leeches.horizontalHeader()
        tbl_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        tbl_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        tbl_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        tbl_header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        tbl_header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        tbl_header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        tbl_header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        tbl_header.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        tbl_header.setSectionResizeMode(8, QHeaderView.ResizeMode.Fixed)
        self.table_leeches.setColumnWidth(8, 95)

        lp_layout.addWidget(self.table_leeches)

        # Message d'état vide
        self.empty_leech_box = QFrame()
        self.empty_leech_box.setStyleSheet("background: transparent; border: none;")
        elb_layout = QHBoxLayout(self.empty_leech_box)
        elb_layout.setContentsMargins(10, 15, 10, 15)
        elb_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        ico_ok = QLabel()
        ico_ok.setPixmap(load_phosphor_icon("ph.check-circle", color=DesignTokens.COLOR_GREEN, weight="fill").pixmap(20, 20))
        ico_ok.setStyleSheet("border: none; background: transparent;")
        lbl_ok = QLabel(self.tr("Aucune carte sangsue détectée. Félicitations pour la santé mnésique de votre collection !"))
        lbl_ok.setFont(QFont(DesignTokens.FONT_MAIN, 9))
        lbl_ok.setStyleSheet(f"color: {DesignTokens.COLOR_GREEN}; border: none; background: transparent;")

        elb_layout.addWidget(ico_ok)
        elb_layout.addWidget(lbl_ok)
        self.empty_leech_box.hide()
        lp_layout.addWidget(self.empty_leech_box)

        parent_layout.addWidget(self.leech_panel)

    def _on_leech_filter_changed(self) -> None:
        self.spn_lapse_threshold.setEnabled(self.cb_include_high_lapses.isChecked())
        self._refresh_leeches()

    def _open_split_dialog(self, leech_data: dict[str, Any]) -> None:
        dialog = LeechWozniakSplitDialog(leech_data=leech_data, parent=self)
        dialog.split_applied.connect(lambda _: self.refresh_stats())
        dialog.exec()

    def _refresh_leeches(self) -> None:
        if not hasattr(self, "table_leeches"):
            return

        include_high = self.cb_include_high_lapses.isChecked()
        threshold = self.spn_lapse_threshold.value()
        leeches = LeechService.get_leech_cards(
            deck_id=self.current_deck_id,
            include_high_lapses=include_high,
            lapse_threshold=threshold,
        )

        count = len(leeches)
        if count == 0:
            self.badge_leech_count.setText(self.tr("0 sangsue"))
            self.badge_leech_count.setStyleSheet(
                f"background-color: {DesignTokens.COLOR_GREEN_BG}; color: {DesignTokens.COLOR_GREEN}; border: 1px solid {DesignTokens.COLOR_GREEN_BORDER}; border-radius: 9999px; padding: 2px 8px;"
            )
            self.table_leeches.setRowCount(0)
            self.table_leeches.hide()
            self.empty_leech_box.show()
            return

        self.badge_leech_count.setText(tr("%1 sangsue(s)", count))
        self.badge_leech_count.setStyleSheet(
            f"background-color: {DesignTokens.COLOR_RED_BG}; color: {DesignTokens.COLOR_RED}; border: 1px solid {DesignTokens.COLOR_RED_BORDER}; border-radius: 9999px; padding: 2px 8px;"
        )
        self.empty_leech_box.hide()
        self.table_leeches.show()
        self.table_leeches.setRowCount(count)

        for row_idx, item in enumerate(leeches):
            card_id_str = f"#{item['card_id']} (N#{item['note_id']})"
            it_id = QTableWidgetItem(card_id_str)
            it_id.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            it_deck = QTableWidgetItem(str(item.get("deck_name", "")))
            it_deck.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            it_face = QTableWidgetItem(str(item.get("face_name", "")))
            it_face.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            it_lapses = QTableWidgetItem(str(item.get("lapses", 0)))
            it_lapses.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            it_stab = QTableWidgetItem(f"{item.get('stability', 0.0):.2f}j")
            it_stab.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            it_diff = QTableWidgetItem(f"{item.get('difficulty', 0.0):.1f}")
            it_diff.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            it_front = QTableWidgetItem(str(item.get("front_snippet", "")))
            it_front.setToolTip(str(item.get("front_snippet", "")))

            it_back = QTableWidgetItem(str(item.get("back_snippet", "")))
            it_back.setToolTip(str(item.get("back_snippet", "")))

            self.table_leeches.setItem(row_idx, 0, it_id)
            self.table_leeches.setItem(row_idx, 1, it_deck)
            self.table_leeches.setItem(row_idx, 2, it_face)
            self.table_leeches.setItem(row_idx, 3, it_lapses)
            self.table_leeches.setItem(row_idx, 4, it_stab)
            self.table_leeches.setItem(row_idx, 5, it_diff)
            self.table_leeches.setItem(row_idx, 6, it_front)
            self.table_leeches.setItem(row_idx, 7, it_back)

            btn_split = PrimaryButton(self.tr("Scinder"))
            btn_split.setIcon(load_on_accent_icon("ph.scissors"))
            btn_split.setFixedHeight(24)
            btn_split.clicked.connect(lambda _, d=item: self._open_split_dialog(d))
            self.table_leeches.setCellWidget(row_idx, 8, btn_split)

    def open_deck_select_dialog(self) -> None:
        self._deck_modal = DeckSelectWindow(parent=self)
        self._deck_modal.deck_selected.connect(self._on_deck_selected)
        self._deck_modal.show()

    def _on_deck_selected(self, deck_id: int, deck_name: str) -> None:
        # Le nœud racine virtuel « Tous les paquets » (-1) n'est pas un paquet réel :
        # il se traduit par l'absence de filtre, jamais par un identifiant inexistant.
        self.current_deck_id = None if deck_id == ALL_DECKS_NODE_ID else deck_id
        self.btn_deck.setText(deck_name)
        self.refresh_stats()
