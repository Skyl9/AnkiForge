import html
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ankiforge.ui.components import Badge, IconButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.views.pipelines_view.constants import (
    STEP_TYPES_META,
    apply_pill_style,
)
from ankiforge.utils.icon_loader import load_phosphor_icon


class StepItemWidget(QFrame):
    """Ligne représentant une étape dans la liste de gauche (sélectionnable, enrichie, 2 lignes sans scroll horizontal)."""

    clicked = Signal(int)

    def __init__(
        self,
        order: int,
        step_data: dict[str, Any],
        is_selected: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.order = order
        self.step_data = step_data
        self.is_selected = is_selected

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._apply_style()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        step_type = step_data.get("type", "LLM_PROMPT")
        meta = STEP_TYPES_META.get(step_type, STEP_TYPES_META["LLM_PROMPT"])
        persona = step_data.get("persona")
        title = step_data.get("custom_title") or (persona.name if persona else meta["default_title"])

        # ── Ligne 1 : Poignée, Icône, Titre, Badge ───────────────────────────
        row1 = QHBoxLayout()
        row1.setSpacing(6)

        handle_lbl = QLabel()
        handle_lbl.setFixedSize(14, 14)
        handle_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        handle_lbl.setPixmap(load_phosphor_icon("ph.dots-six-vertical", color=DesignTokens.TEXT_MUTED).pixmap(14, 14))
        row1.addWidget(handle_lbl, alignment=Qt.AlignmentFlag.AlignVCenter)

        icon_lbl = QLabel()
        icon_lbl.setFixedSize(18, 18)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setPixmap(load_phosphor_icon(meta["icon"], color=meta["badge_color"]).pixmap(16, 16))
        row1.addWidget(icon_lbl, alignment=Qt.AlignmentFlag.AlignVCenter)

        title_escaped = html.escape(str(title))
        self.title_lbl = QLabel(f"<b>{order}.</b> {title_escaped}")
        self.title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; background: transparent;")
        self.title_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row1.addWidget(self.title_lbl, 1, alignment=Qt.AlignmentFlag.AlignVCenter)

        badge = Badge(meta["badge"], variant="status")
        apply_pill_style(badge, meta["badge_color"])
        badge.setFixedHeight(18)
        row1.addWidget(badge, alignment=Qt.AlignmentFlag.AlignVCenter)

        layout.addLayout(row1)

        # ── Ligne 2 : Variables d'entrée/sortie + Actions (▲, ▼, 🗑) ─────────
        row2 = QHBoxLayout()
        row2.setSpacing(6)

        cfg = step_data.get("config", {})
        var_in = cfg.get("input_variable", meta.get("default_input", "text_source"))
        var_out = cfg.get("output_variable", meta.get("default_output", "generated_cards"))
        lbl_vars = QLabel(f"📥 {var_in} ➔ 📤 {var_out}")
        lbl_vars.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-family: monospace; background: transparent;")
        lbl_vars.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row2.addWidget(lbl_vars, 1, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.btn_up = IconButton("ph.arrow-up", tooltip="Monter d'un rang", size=20)
        self.btn_down = IconButton("ph.arrow-down", tooltip="Descendre d'un rang", size=20)
        self.btn_delete = IconButton("ph.trash", tooltip="Supprimer cette étape", size=20)

        row2.addWidget(self.btn_up, alignment=Qt.AlignmentFlag.AlignVCenter)
        row2.addWidget(self.btn_down, alignment=Qt.AlignmentFlag.AlignVCenter)
        row2.addWidget(self.btn_delete, alignment=Qt.AlignmentFlag.AlignVCenter)

        layout.addLayout(row2)

    def _apply_style(self) -> None:
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        bg = DesignTokens.BG_ACTIVE if self.is_selected else DesignTokens.BG_PANEL
        border = DesignTokens.ACCENT_PRIMARY if self.is_selected else DesignTokens.BORDER_COLOR
        border_left = f"3px solid {DesignTokens.ACCENT_PRIMARY}" if self.is_selected else f"1px solid {border}"
        self.setStyleSheet(f"""
            StepItemWidget {{
                background-color: {bg};
                border: 1px solid {border};
                border-left: {border_left};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
            StepItemWidget:hover {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
            StepItemWidget QLabel {{
                background: transparent;
            }}
        """)

    def mousePressEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.order - 1)
        super().mousePressEvent(event)


class InlineInsertButton(QWidget):
    """Bouton d'insertion contextuelle discret et élégant entre deux étapes du workflow."""

    clicked = Signal(int)

    def __init__(self, insert_index: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.insert_index = insert_index
        self.setFixedHeight(22)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(8)

        line_left = QFrame()
        line_left.setFrameShape(QFrame.Shape.HLine)
        line_left.setStyleSheet(f"border: none; border-top: 1px dashed {DesignTokens.BORDER_COLOR};")
        layout.addWidget(line_left, 1)

        self.btn = QPushButton("+")
        self.btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn.setToolTip(f"Insérer une étape à la position {insert_index + 1}")
        self.btn.setFixedSize(20, 20)
        self.btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 10px;
                color: {DesignTokens.TEXT_MUTED};
                font-size: 12px;
                font-weight: bold;
                padding: 0;
            }}
            QPushButton:hover {{
                background-color: {DesignTokens.ACCENT_PRIMARY};
                border-color: {DesignTokens.ACCENT_PRIMARY};
                color: white;
            }}
        """)
        self.btn.clicked.connect(lambda: self.clicked.emit(self.insert_index))
        layout.addWidget(self.btn)

        line_right = QFrame()
        line_right.setFrameShape(QFrame.Shape.HLine)
        line_right.setStyleSheet(f"border: none; border-top: 1px dashed {DesignTokens.BORDER_COLOR};")
        layout.addWidget(line_right, 1)
