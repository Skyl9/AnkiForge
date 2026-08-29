from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.views.ab_tests_view.constants import apply_pill_style


class BranchKpiWidget(QFrame):
    """Bannière aérée et structurée de KPIs de performance pour une branche A/B."""

    def __init__(self, branch_title: str, color_hex: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.branch_title = branch_title
        self.color_hex = color_hex
        self._last_elapsed: float = 0.0
        self._last_cards: int = 0
        self._last_tokens: int = 0
        self._last_cost: float = 0.0

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._apply_style()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(4)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(8)

        self.lbl_branch = QLabel(branch_title)
        self.lbl_branch.setAlignment(Qt.AlignmentFlag.AlignCenter)
        apply_pill_style(self.lbl_branch, color_hex)
        top_row.addWidget(self.lbl_branch, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.badge_winner = QLabel("⚡ Plus rapide")
        self.badge_winner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        apply_pill_style(self.badge_winner, DesignTokens.COLOR_GREEN)
        self.badge_winner.hide()
        top_row.addWidget(self.badge_winner, alignment=Qt.AlignmentFlag.AlignVCenter)

        top_row.addStretch()

        self.lbl_status = QLabel("Prêt")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        apply_pill_style(self.lbl_status, DesignTokens.TEXT_MUTED)
        top_row.addWidget(self.lbl_status, alignment=Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(top_row)

        metrics_row = QHBoxLayout()
        metrics_row.setContentsMargins(0, 0, 0, 0)
        metrics_row.setSpacing(12)

        self.lbl_time = QLabel("⏱️ 0.00s")
        self.lbl_time.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; font-weight: bold; background: transparent;")
        metrics_row.addWidget(self.lbl_time, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.lbl_cards = QLabel("🃏 0 cartes")
        self.lbl_cards.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; font-weight: bold; background: transparent;")
        metrics_row.addWidget(self.lbl_cards, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.lbl_tokens = QLabel("🪙 ~0 tok")
        self.lbl_tokens.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; background: transparent;")
        metrics_row.addWidget(self.lbl_tokens, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.lbl_cost = QLabel("💰 $0.000")
        self.lbl_cost.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; background: transparent;")
        metrics_row.addWidget(self.lbl_cost, alignment=Qt.AlignmentFlag.AlignVCenter)

        metrics_row.addStretch()
        layout.addLayout(metrics_row)

    def _apply_style(self) -> None:
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)

    def set_running(self) -> None:
        self.badge_winner.hide()
        self.lbl_status.setText("⏳ En cours...")
        apply_pill_style(self.lbl_status, DesignTokens.COLOR_BLUE)

    def set_results(self, elapsed: float, cards_count: int, tokens: int, cost_usd: float, is_success: bool = True, err_msg: str = "") -> None:
        self._last_elapsed = elapsed
        self._last_cards = cards_count
        self._last_tokens = tokens
        self._last_cost = cost_usd

        self.lbl_time.setText(f"⏱️ {elapsed:.2f}s")
        self.lbl_cards.setText(f"🃏 {cards_count} carte{'s' if cards_count > 1 else ''}")
        self.lbl_tokens.setText(f"🪙 ~{tokens} tok")
        self.lbl_cost.setText(f"💰 ${cost_usd:.4f}" if cost_usd > 0 else "💰 0€ (Local)")

        if is_success:
            self.lbl_status.setText("✅ Terminé")
            apply_pill_style(self.lbl_status, DesignTokens.COLOR_GREEN)
        else:
            self.lbl_status.setText("❌ Erreur")
            self.lbl_status.setToolTip(err_msg)
            apply_pill_style(self.lbl_status, DesignTokens.COLOR_RED)

    def set_winner(self, text: str = "⚡ Plus rapide") -> None:
        self.badge_winner.setText(text)
        self.badge_winner.show()

    def clear_winner(self) -> None:
        self.badge_winner.hide()
