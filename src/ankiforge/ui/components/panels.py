from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel, QWidget, QHBoxLayout, QStackedWidget
from PySide6.QtCore import Signal, Qt
from ..theme import DesignTokens, apply_shadow
from .buttons import IconButton


class IdePanel(QFrame):
    """Panneau IDE avec tab bar, titre, bouton détacher."""

    detach_requested = Signal()

    def __init__(self, title: str, detachable: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("IdePanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            #IdePanel {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)

        self.layout_main = QVBoxLayout(self)
        self.layout_main.setContentsMargins(0, 0, 0, 0)
        self.layout_main.setSpacing(0)

        self.header = QFrame()
        self.header.setStyleSheet(
            f"background-color: {DesignTokens.BG_INPUT}; border-top-left-radius: {DesignTokens.RADIUS_MD}px; "
            f"border-top-right-radius: {DesignTokens.RADIUS_MD}px; border-bottom: 1px solid {DesignTokens.BORDER_COLOR};"
        )
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(10, 5, 10, 5)

        self.title_lbl = QLabel(title)
        self.title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-weight: bold; font-size: 11px; text-transform: uppercase;")
        header_layout.addWidget(self.title_lbl)
        header_layout.addStretch()

        if detachable:
            self.detach_btn = IconButton("⏏", tooltip="Détacher le panneau", size=24)
            self.detach_btn.clicked.connect(self.detach_requested.emit)
            header_layout.addWidget(self.detach_btn)

        self.layout_main.addWidget(self.header)
        self.stacked_widget = QStackedWidget()
        self.layout_main.addWidget(self.stacked_widget)

    def add_tab(self, title: str, widget: QWidget, icon_name: str = "") -> None:
        self.stacked_widget.addWidget(widget)

    def set_active_tab(self, index: int) -> None:
        self.stacked_widget.setCurrentIndex(index)


class GlassPanel(QFrame):
    """Panneau glassmorphism (semi-transparent + blur effect)."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("GlassPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            #GlassPanel {{
                background-color: rgba(30, 33, 40, 0.6);
                border: 1px solid {DesignTokens.BORDER_LIGHT};
                border-radius: {DesignTokens.RADIUS_LG}px;
            }}
        """)
        apply_shadow(self, blur=32, offset_y=8, color="rgba(0,0,0,0.5)")


class MetricCard(QFrame):
    """Carte métrique avec valeur, label, icône, trend. Usage: Batch CI/CD, Stats."""

    def __init__(self, label: str, value: str, icon_name: str, trend: str = "", trend_positive: bool = True, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("MetricCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            #MetricCard {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        header_layout = QHBoxLayout()
        self.lbl_label = QLabel(label)
        self.lbl_label.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-weight: bold;")
        self.lbl_icon = QLabel(icon_name)
        header_layout.addWidget(self.lbl_label)
        header_layout.addStretch()
        header_layout.addWidget(self.lbl_icon)

        self.lbl_value = QLabel(value)
        self.lbl_value.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 24px; font-weight: bold;")

        layout.addLayout(header_layout)
        layout.addWidget(self.lbl_value)

        if trend:
            color = DesignTokens.COLOR_GREEN if trend_positive else DesignTokens.COLOR_RED
            self.lbl_trend = QLabel(trend)
            self.lbl_trend.setStyleSheet(f"color: {color}; font-size: 11px;")
            layout.addWidget(self.lbl_trend)

    def set_value(self, value: str) -> None:
        self.lbl_value.setText(value)


class StatCard(QFrame):
    """Carte statistique. Usage: Dashboard sidebar, Settings stats."""

    def __init__(self, label: str, value: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("StatCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            #StatCard {{
                background-color: {DesignTokens.BG_INPUT};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        self.lbl_value = QLabel(value)
        self.lbl_value.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 18px; font-weight: bold;")
        self.lbl_label = QLabel(label)
        self.lbl_label.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        layout.addWidget(self.lbl_value)
        layout.addWidget(self.lbl_label)
