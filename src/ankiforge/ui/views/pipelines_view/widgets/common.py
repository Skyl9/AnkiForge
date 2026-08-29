from typing import Any

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QWidget,
)

from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.views.pipelines_view.constants import (
    STEP_TYPES_META,
    audit_pipeline_dag,
)
from ankiforge.utils.icon_loader import load_phosphor_icon


class TagPillButton(QPushButton):
    """Pastille cliquable pour l'insertion rapide de variable Jinja2."""

    def __init__(
        self,
        text: str,
        template_code: str,
        tooltip: str = "",
        variant: str = "field",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self.template_code = template_code
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(24)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setToolTip(f"{tooltip}\nInsère : {template_code}")

        if variant == "cloze":
            bg_tint = "rgba(168, 85, 247, 0.12)"
            border_color = "rgba(168, 85, 247, 0.45)"
            text_color = "#c084fc"
        elif variant == "warning":
            bg_tint = "rgba(245, 158, 11, 0.12)"
            border_color = "rgba(245, 158, 11, 0.45)"
            text_color = "#fcd34d"
        elif variant == "success":
            bg_tint = "rgba(16, 185, 129, 0.12)"
            border_color = "rgba(16, 185, 129, 0.45)"
            text_color = "#6ee7b7"
        elif variant == "info":
            bg_tint = "rgba(6, 182, 212, 0.12)"
            border_color = "rgba(6, 182, 212, 0.45)"
            text_color = "#67e8f9"
        else:  # field
            bg_tint = "rgba(99, 102, 241, 0.10)"
            border_color = "rgba(99, 102, 241, 0.40)"
            text_color = "#a5b4fc"

        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg_tint};
                border: 1px solid {border_color};
                border-radius: 12px;
                color: {text_color};
                font-family: '{DesignTokens.FONT_CODE}';
                font-size: 11px;
                font-weight: 600;
                padding: 1px 10px;
            }}
            QPushButton:hover {{
                border: 1.5px solid {DesignTokens.ACCENT_PRIMARY};
                background-color: {DesignTokens.BG_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {DesignTokens.BG_ACTIVE};
            }}
        """)


class SubTabButton(QPushButton):
    """Bouton d'onglet style IDE avec relief et affordance tactile."""

    def __init__(self, text: str, icon_name: str, is_active: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.icon_name = icon_name
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(32)
        self.setIconSize(QSize(15, 15))
        self.set_active(is_active)

    def set_active(self, active: bool) -> None:
        if active:
            self.setIcon(load_phosphor_icon(self.icon_name, color=DesignTokens.ACCENT_PRIMARY))
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {DesignTokens.BG_PANEL};
                    color: {DesignTokens.TEXT_PRIMARY};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-bottom: 2px solid {DesignTokens.ACCENT_PRIMARY};
                    border-radius: {DesignTokens.RADIUS_SM}px;
                    padding: 2px 14px;
                    font-size: 11.5px;
                    font-weight: bold;
                }}
            """)
        else:
            self.setIcon(load_phosphor_icon(self.icon_name, color=DesignTokens.TEXT_MUTED))
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    color: {DesignTokens.TEXT_SECONDARY};
                    border: 1px solid transparent;
                    border-radius: {DesignTokens.RADIUS_SM}px;
                    padding: 2px 14px;
                    font-size: 11.5px;
                    font-weight: normal;
                }}
                QPushButton:hover {{
                    background-color: {DesignTokens.BG_HOVER};
                    color: {DesignTokens.TEXT_PRIMARY};
                }}
            """)


class StatusPillBadge(QFrame):
    """Badge capsule arrondi avec icône Phosphor native et texte (ex: DAG Valide, Alerte)."""

    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(28)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 2, 12, 2)
        layout.setSpacing(6)

        self.lbl_icon = QLabel()
        self.lbl_icon.setFixedSize(16, 16)
        self.lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_text = QLabel("DAG Valide")
        self.lbl_text.setStyleSheet("font-size: 11px; font-weight: bold;")

        layout.addWidget(self.lbl_icon)
        layout.addWidget(self.lbl_text)

        self.set_status(is_valid=True, message="DAG Valide", tooltip="Le graphe DAG est cohérent et valide.")

    def set_status(self, is_valid: bool, message: str, tooltip: str = "") -> None:
        color = DesignTokens.COLOR_GREEN if is_valid else "#f59e0b"
        bg_alpha = "rgba(16, 185, 129, 0.15)" if is_valid else "rgba(245, 158, 11, 0.15)"
        border_alpha = "rgba(16, 185, 129, 0.35)" if is_valid else "rgba(245, 158, 11, 0.35)"
        icon_name = "ph.check-circle" if is_valid else "ph.warning-circle"

        self.lbl_icon.setPixmap(load_phosphor_icon(icon_name, color=color).pixmap(14, 14))
        self.lbl_text.setText(message)
        self.lbl_text.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: bold;")
        self.setStyleSheet(f"""
            StatusPillBadge {{
                background-color: {bg_alpha};
                border: 1px solid {border_alpha};
                border-radius: 9999px;
            }}
            StatusPillBadge:hover {{
                border-color: {color};
            }}
            StatusPillBadge QLabel {{
                background: transparent;
            }}
        """)
        self.setToolTip(tooltip)

    def mousePressEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class DagFlowOverviewWidget(QFrame):
    """Bannière visuelle représentant le flux interactif du graphe DAG avec diagnostic en direct."""

    step_selected = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("DagFlowOverview")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(46)
        self.setStyleSheet(f"""
            QFrame#DagFlowOverview {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
            QFrame#DagFlowOverview QLabel {{
                background: transparent;
            }}
        """)
        self.layout_main = QHBoxLayout(self)
        self.layout_main.setContentsMargins(12, 4, 12, 4)
        self.layout_main.setSpacing(8)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        inner_nodes = QWidget()
        inner_nodes.setStyleSheet("background: transparent;")
        self.nodes_layout = QHBoxLayout(inner_nodes)
        self.nodes_layout.setContentsMargins(0, 0, 0, 0)
        self.nodes_layout.setSpacing(6)
        self.nodes_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        scroll_area.setWidget(inner_nodes)

        self.layout_main.addWidget(scroll_area, 1)

        self.health_badge = StatusPillBadge()
        self.layout_main.addWidget(self.health_badge, alignment=Qt.AlignmentFlag.AlignVCenter)

    def render_flow(self, steps: list[dict[str, Any]], active_index: int = 0) -> None:
        """Re-dessine les badges interactifs du flux d'étapes et évalue la santé du graphe."""
        while self.nodes_layout.count():
            item = self.nodes_layout.takeAt(0)
            if item:
                w = item.widget()
                if w:
                    w.setParent(None)
                    w.deleteLater()

        if not steps:
            lbl_empty = QLabel("Workflow vide. Ajoutez des étapes ci-dessous.")
            lbl_empty.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-style: italic;")
            self.nodes_layout.addWidget(lbl_empty)
            self.health_badge.set_status(is_valid=False, message="Workflow vide", tooltip="Ajoutez au moins une étape pour valider le pipeline.")
            return

        # 1. Diagnostic Linter DAG
        issues = audit_pipeline_dag(steps)
        if issues:
            self.health_badge.set_status(is_valid=False, message=f"{len(issues)} Alerte(s)", tooltip="\n".join(issues))
        else:
            self.health_badge.set_status(is_valid=True, message="DAG Valide", tooltip="Le graphe DAG est cohérent, sans cycle et toutes les variables sont résolues.")

        # 2. Point de départ
        lbl_start = QLabel()
        lbl_start.setFixedSize(18, 18)
        lbl_start.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_start.setPixmap(load_phosphor_icon("ph.play-circle", color=DesignTokens.TEXT_MUTED).pixmap(15, 15))
        lbl_start.setToolTip("Point d'entrée du pipeline")
        self.nodes_layout.addWidget(lbl_start)

        for idx, step_data in enumerate(steps, start=1):
            arrow = QLabel()
            arrow.setFixedSize(14, 14)
            arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
            arrow.setPixmap(load_phosphor_icon("ph.caret-right", color=DesignTokens.TEXT_MUTED).pixmap(12, 12))
            self.nodes_layout.addWidget(arrow)

            step_type = step_data.get("type", "LLM_PROMPT")
            meta = STEP_TYPES_META.get(step_type, STEP_TYPES_META["LLM_PROMPT"])
            persona = step_data.get("persona")
            raw_title = step_data.get("custom_title") or (persona.name if persona else meta["badge"])
            title_escaped = str(raw_title).replace("&", "&&")

            is_active = (idx - 1) == active_index

            btn_node = QPushButton(f"{idx}. {title_escaped}")
            btn_node.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_node.setIcon(load_phosphor_icon(meta["icon"], color=meta["badge_color"]))
            btn_node.setIconSize(QSize(14, 14))
            border_color = meta["badge_color"] if is_active else DesignTokens.BORDER_COLOR
            bg_color = "rgba(99, 102, 241, 0.15)" if is_active else DesignTokens.BG_INPUT

            btn_node.setStyleSheet(f"""
                QPushButton {{
                    background-color: {bg_color};
                    border: 1px solid {border_color};
                    border-radius: 12px;
                    color: {DesignTokens.TEXT_PRIMARY};
                    font-size: 11px;
                    font-weight: {"bold" if is_active else "normal"};
                    padding: 3px 10px;
                }}
                QPushButton:hover {{
                    border-color: {meta["badge_color"]};
                    background-color: {DesignTokens.BG_HOVER};
                }}
            """)
            btn_node.clicked.connect(lambda _, step_idx=idx - 1: self.step_selected.emit(step_idx))
            self.nodes_layout.addWidget(btn_node)

            succ_order = step_data.get("on_success_order")
            if succ_order:
                lbl_jump = QLabel(f"↳ {succ_order}")
                lbl_jump.setStyleSheet(f"color: {DesignTokens.ACCENT_PRIMARY}; font-size: 10px; font-weight: bold;")
                lbl_jump.setToolTip(f"Saute directement vers l'étape {succ_order} en cas de succès")
                self.nodes_layout.addWidget(lbl_jump)

        # Point d'arrivée
        arrow_end = QLabel()
        arrow_end.setFixedSize(14, 14)
        arrow_end.setAlignment(Qt.AlignmentFlag.AlignCenter)
        arrow_end.setPixmap(load_phosphor_icon("ph.caret-right", color=DesignTokens.TEXT_MUTED).pixmap(12, 12))
        self.nodes_layout.addWidget(arrow_end)

        lbl_end = QLabel()
        lbl_end.setFixedSize(18, 18)
        lbl_end.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_end.setPixmap(load_phosphor_icon("ph.check-circle", color=DesignTokens.COLOR_GREEN).pixmap(15, 15))
        lbl_end.setToolTip("Sortie finale : cartes forgées et prêtes")
        self.nodes_layout.addWidget(lbl_end)
