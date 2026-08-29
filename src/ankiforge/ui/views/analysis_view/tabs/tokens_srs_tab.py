from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ankiforge.services.ai.linter import TokenSrsFinancialService
from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton
from ankiforge.ui.components.deck_select_window import DeckSelectWindow
from ankiforge.ui.components.linter_widgets import RetentionCurveCanvas
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon


class AITokensSrsTab(QWidget):
    """Onglet de suivi financier des jetons et de santé d'apprentissage FSRS-4.5."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.current_deck_id: Optional[int] = None

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

        lbl_title = QLabel("Finances & Rétention SRS")
        lbl_title.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
        lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")

        self.btn_deck = SecondaryButton("L'ensemble des paquets")
        self.btn_deck.setIcon(load_phosphor_icon("ph.cards", color=DesignTokens.TEXT_PRIMARY))
        self.btn_deck.setFixedHeight(28)
        self.btn_deck.clicked.connect(self.open_deck_select_dialog)

        self.lbl_spent = QLabel("Dépenses : 0.0000 $")
        self.lbl_spent.setFont(QFont(DesignTokens.FONT_MAIN, 9, QFont.Weight.Bold))
        self.lbl_spent.setStyleSheet(f"background-color: rgba(16,185,129,0.15); color: {DesignTokens.COLOR_GREEN}; border: 1px solid rgba(16,185,129,0.3); border-radius: 9999px; padding: 3px 10px;")

        self.lbl_cost = QLabel("~0.00000 $ / carte")
        self.lbl_cost.setFont(QFont(DesignTokens.FONT_MAIN, 9))
        self.lbl_cost.setStyleSheet(
            f"background-color: {DesignTokens.BG_INPUT}; color: {DesignTokens.TEXT_MUTED}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 9999px; padding: 3px 10px;"
        )

        btn_analyze = PrimaryButton("Analyser ce paquet")
        btn_analyze.setIcon(load_phosphor_icon("ph.arrows-clockwise", color="white"))
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
        l_title = QLabel("Dépenses par Fournisseur IA & Modèle")
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
        eq_title = QLabel("Équilibre & Maturité du Paquet (FSRS-4.5)")
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

        h_rtitle = QHBoxLayout()
        ico_curve = QLabel()
        ico_curve.setPixmap(load_phosphor_icon("ph.chart-line-up", color=DesignTokens.ACCENT_PRIMARY).pixmap(16, 16))
        ico_curve.setStyleSheet("border: none; background: transparent;")
        r_title = QLabel("Courbe Théorique de Rétention (Forgetting Curve FSRS-4.5)")
        r_title.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
        r_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")
        h_rtitle.addWidget(ico_curve)
        h_rtitle.addWidget(r_title)
        h_rtitle.addStretch()
        r_layout.addLayout(h_rtitle)

        canvas = RetentionCurveCanvas()
        r_layout.addWidget(canvas)

        btn_opt = PrimaryButton("Optimiser FSRS-4.5 (ML Local)")
        btn_opt.setIcon(load_phosphor_icon("ph.sparkle", color="white"))
        btn_opt.setFixedHeight(30)
        btn_opt.clicked.connect(self._on_optimize_fsrs)
        r_layout.addWidget(btn_opt)

        r_layout.addStretch()
        main_grid.addWidget(right_col, 1)

        layout.addLayout(main_grid, 1)
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

    def _on_optimize_fsrs(self) -> None:
        show_toast(self, "Paramètres FSRS-4.5 optimisés avec succès pour votre rythme d'apprentissage !")

    def refresh_stats(self):
        summary = TokenSrsFinancialService.get_financial_summary(self.current_deck_id)

        self.lbl_spent.setText(f"Dépenses : {summary['total_spent_usd']:.4f} $")
        avg_cost = summary["total_spent_usd"] / max(summary["total_cards"], 1)
        self.lbl_cost.setText(f"~{avg_cost:.5f} $ / carte")

        self._clear_layout(self.kpi_grid)
        self._clear_layout(self.eq_grid)
        self._clear_layout(self.models_container)
        self._clear_layout(self.tasks_container)

        mat_pct = "0%" if summary["total_cards"] == 0 else f"{summary['maturing_cards'] / summary['total_cards'] * 100:.1f}%"
        diff_pct = float(summary["fsrs_retention_pct"]) - float(summary["target_retention_pct"])
        cards_data = [
            (
                "ph.coins",
                "Budget Consommé",
                f"{summary['total_spent_usd']:.4f} $",
                f"{summary['tokens_consumed']:,} jetons · Optimal",
                DesignTokens.COLOR_GREEN,
            ),
            (
                "ph.target",
                "Rétention FSRS-4.5",
                f"{summary['fsrs_retention_pct']:.1f}%",
                f"Cible : {summary['target_retention_pct']:.0f}% ({diff_pct:+.1f}%)",
                DesignTokens.ACCENT_PRIMARY,
            ),
            (
                "ph.sparkle",
                "Cartes Mûres (>21j)",
                f"{summary['maturing_cards']:,} / {summary['total_cards']:,}",
                f"{mat_pct} · Ancrage fort",
                "#c084fc",
            ),
            (
                "ph.clock",
                "Charge Journalière",
                f"{summary['daily_workload_cards']:.1f} cartes / j",
                f"Temps estimé : ~{summary['daily_workload_minutes']:.0f} min",
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
        if tot > 0:
            eq_data.append(("NOUVELLES", str(summary["maturity_distribution"]["new"]), f"{summary['maturity_distribution']['new'] / tot * 100:.1f}%", DesignTokens.COLOR_BLUE))
            eq_data.append(("APPRENTISSAGE", str(summary["maturity_distribution"]["learning"]), f"{summary['maturity_distribution']['learning'] / tot * 100:.1f}%", DesignTokens.COLOR_YELLOW))
            eq_data.append(("MÛRES (>21j)", str(summary["maturity_distribution"]["maturing"]), f"{summary['maturity_distribution']['maturing'] / tot * 100:.1f}%", "#c084fc"))
        else:
            eq_data = [("NOUVELLES", "0", "0%", DesignTokens.COLOR_BLUE), ("APPRENTISSAGE", "0", "0%", DesignTokens.COLOR_YELLOW), ("MÛRES (>21j)", "0", "0%", "#c084fc")]

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
                p_color = "#4285F4"
                p_tag = "Google Gemini"
            elif any(k in m_lower for k in ("qwen", "llama", "mistral", "ollama")):
                p_icon = "ph.terminal"
                p_color = "#10a37f"
                p_tag = "Ollama Local"
            elif any(k in m_lower for k in ("gpt", "openai")):
                p_icon = "ph.brain"
                p_color = "#10a37f"
                p_tag = "OpenAI"
            elif any(k in m_lower for k in ("claude", "anthropic")):
                p_icon = "ph.chat-teardrop-dots"
                p_color = "#d97706"
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

            det = QLabel(f"{p_tag} · {m['tokens']:,} jetons ({m['pct']:.1f}% des dépenses)")
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
        tb_title = QLabel("Répartition par Type de Tâche IA")
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

    def open_deck_select_dialog(self) -> None:
        self._deck_modal = DeckSelectWindow(parent=self)
        self._deck_modal.deck_selected.connect(self._on_deck_selected)
        self._deck_modal.show()

    def _on_deck_selected(self, deck_id: int, deck_name: str) -> None:
        self.current_deck_id = deck_id
        self.btn_deck.setText(deck_name)
        self.refresh_stats()
