from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.views.ab_tests_view.constants import apply_pill_style
from ankiforge.utils.icon_loader import load_phosphor_icon


class BranchKpiWidget(QFrame):
    """Bannière aérée et structurée de KPIs de performance pour une branche A/B."""

    def __init__(self, branch_title: str, color_hex: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.branch_title = branch_title
        self.color_hex = color_hex
        self._running: bool = False
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

        top_row.addStretch()

        self.lbl_status = QLabel("Prêt")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        apply_pill_style(self.lbl_status, DesignTokens.TEXT_MUTED)
        top_row.addWidget(self.lbl_status, alignment=Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(top_row)

        self.metrics_row = QHBoxLayout()
        self.metrics_row.setContentsMargins(0, 0, 0, 0)
        self.metrics_row.setSpacing(16)

        self.lbl_time = QLabel("—")
        self.lbl_time.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; font-weight: bold; background: transparent;")
        ico_time = QLabel()
        ico_time.setFixedSize(14, 14)
        ico_time.setPixmap(load_phosphor_icon("ph.timer", color=DesignTokens.TEXT_MUTED).pixmap(13, 13))
        row_time = QHBoxLayout()
        row_time.setContentsMargins(0, 0, 0, 0)
        row_time.setSpacing(4)
        row_time.addWidget(ico_time)
        row_time.addWidget(self.lbl_time)
        self.metrics_row.addLayout(row_time)

        self.lbl_cards = QLabel("—")
        self.lbl_cards.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; font-weight: bold; background: transparent;")
        ico_cards = QLabel()
        ico_cards.setFixedSize(14, 14)
        ico_cards.setPixmap(load_phosphor_icon("ph.cards", color=DesignTokens.TEXT_MUTED).pixmap(13, 13))
        row_cards = QHBoxLayout()
        row_cards.setContentsMargins(0, 0, 0, 0)
        row_cards.setSpacing(4)
        row_cards.addWidget(ico_cards)
        row_cards.addWidget(self.lbl_cards)
        self.metrics_row.addLayout(row_cards)

        self.lbl_tokens = QLabel("—")
        self.lbl_tokens.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; background: transparent;")
        ico_tokens = QLabel()
        ico_tokens.setFixedSize(14, 14)
        ico_tokens.setPixmap(load_phosphor_icon("ph.coins", color=DesignTokens.TEXT_MUTED).pixmap(13, 13))
        row_tokens = QHBoxLayout()
        row_tokens.setContentsMargins(0, 0, 0, 0)
        row_tokens.setSpacing(4)
        row_tokens.addWidget(ico_tokens)
        row_tokens.addWidget(self.lbl_tokens)
        self.metrics_row.addLayout(row_tokens)

        self.lbl_cost = QLabel("—")
        self.lbl_cost.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; background: transparent;")
        ico_cost = QLabel()
        ico_cost.setFixedSize(14, 14)
        ico_cost.setPixmap(load_phosphor_icon("ph.currency-dollar", color=DesignTokens.TEXT_MUTED).pixmap(13, 13))
        row_cost = QHBoxLayout()
        row_cost.setContentsMargins(0, 0, 0, 0)
        row_cost.setSpacing(4)
        row_cost.addWidget(ico_cost)
        row_cost.addWidget(self.lbl_cost)
        self.metrics_row.addLayout(row_cost)

        self.metrics_row.addStretch()
        layout.addLayout(self.metrics_row)

    def _apply_style(self) -> None:
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)

    def set_idle(self) -> None:
        """État vide : masque les métriques pour éviter d'afficher des zéros trompeurs."""
        self._running = False
        self.lbl_status.setText("Prêt")
        apply_pill_style(self.lbl_status, DesignTokens.TEXT_MUTED)
        self.lbl_time.setText("—")
        self.lbl_cards.setText("—")
        self.lbl_tokens.setText("—")
        self.lbl_cost.setText("—")
        self.metrics_row.setEnabled(False)
        self._set_metrics_dimmed(True)

    def _set_metrics_dimmed(self, dimmed: bool) -> None:
        opacity = 0.4 if dimmed else 1.0
        for lbl in (self.lbl_time, self.lbl_cards):
            lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; font-weight: bold; background: transparent; opacity: {opacity}%;")
        for lbl in (self.lbl_tokens, self.lbl_cost):
            lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; background: transparent; opacity: {opacity}%;")

    def set_running(self) -> None:
        self._running = True
        self.lbl_status.setText("En cours...")
        apply_pill_style(self.lbl_status, DesignTokens.COLOR_BLUE)
        self.metrics_row.setEnabled(True)
        self._set_metrics_dimmed(False)
        self.lbl_time.setText("0.00s")
        self.lbl_cards.setText("—")
        self.lbl_tokens.setText("—")
        self.lbl_cost.setText("—")

    def set_running_elapsed(self, elapsed: float) -> None:
        self.lbl_time.setText(f"{elapsed:.2f}s")

    def set_results(self, elapsed: float, cards_count: int, tokens: int, cost_usd: float, is_success: bool = True, err_msg: str = "") -> None:
        self._running = False
        self._last_elapsed = elapsed
        self._last_cards = cards_count
        self._last_tokens = tokens
        self._last_cost = cost_usd

        self.metrics_row.setEnabled(True)
        self._set_metrics_dimmed(False)
        self.lbl_time.setText(f"{elapsed:.2f}s")
        self.lbl_cards.setText(f"{cards_count} carte{'s' if cards_count > 1 else ''}")
        self.lbl_tokens.setText(f"~{tokens} tok")
        self.lbl_cost.setText(f"${cost_usd:.4f}" if cost_usd > 0 else "0 (Local)")

        if is_success:
            self.lbl_status.setText("Terminé")
            apply_pill_style(self.lbl_status, DesignTokens.COLOR_GREEN)
        else:
            self.lbl_status.setText("Erreur")
            self.lbl_status.setToolTip(err_msg)
            apply_pill_style(self.lbl_status, DesignTokens.COLOR_RED)
