"""
Widgets UI PySide6 sur mesure pour le Linter Wozniak, Diagnostic des Sources et FSRS-4.5.
"""

from typing import Optional, Dict, Any
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QLineEdit,
    QCheckBox,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QPainter, QPen, QColor, QBrush, QPainterPath

from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton
from ankiforge.utils.icon_loader import load_phosphor_icon


class WozniakKpiCard(QFrame):
    """Carte KPI d'aperçu de catégorie du linter Wozniak avec jauge et sélection interactive."""

    clicked = Signal(str)

    def __init__(self, cat_id: str, title: str, pct: int, subtitle: str, color: str, icon_name: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.cat_id = cat_id
        self.color = color
        self._is_active = False

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.update_style()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        row1 = QHBoxLayout()
        row1.setSpacing(6)

        lbl_icon = QLabel()
        lbl_icon.setPixmap(load_phosphor_icon(icon_name, color=self.color).pixmap(16, 16))

        lbl_title = QLabel(title)
        lbl_title.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
        lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none;")

        self.lbl_pct = QLabel(f"{pct}%")
        self.lbl_pct.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
        self.lbl_pct.setStyleSheet(f"color: {self.color}; border: none;")

        row1.addWidget(lbl_icon)
        row1.addWidget(lbl_title)
        row1.addStretch()
        row1.addWidget(self.lbl_pct)
        layout.addLayout(row1)

        self.lbl_sub = QLabel(subtitle)
        self.lbl_sub.setFont(QFont(DesignTokens.FONT_MAIN, 9))
        self.lbl_sub.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; border: none;")
        layout.addWidget(self.lbl_sub)

        # Progress bar
        from PySide6.QtWidgets import QProgressBar

        self.progress = QProgressBar()
        self.progress.setFixedHeight(4)
        self.progress.setTextVisible(False)
        self.progress.setMinimum(0)
        self.progress.setMaximum(100)
        self.progress.setValue(pct)
        self.progress.setStyleSheet(f"""
            QProgressBar {{
                background-color: {DesignTokens.BG_MAIN};
                border-radius: 2px;
                border: none;
            }}
            QProgressBar::chunk {{
                background-color: {self.color};
                border-radius: 2px;
            }}
        """)
        layout.addWidget(self.progress)

    def update_pct(self, pct: int, subtitle: str = "") -> None:
        self.lbl_pct.setText(f"{pct}%")
        self.progress.setValue(pct)
        if subtitle:
            self.lbl_sub.setText(subtitle)

    def set_active(self, active: bool) -> None:
        self._is_active = active
        self.update_style()

    def update_style(self) -> None:
        border_color = DesignTokens.ACCENT_PRIMARY if self._is_active else DesignTokens.BORDER_COLOR
        bg_color = DesignTokens.BG_ACTIVE if self._is_active else DesignTokens.BG_PANEL
        self.setStyleSheet(f"""
            WozniakKpiCard {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 6px;
            }}
            WozniakKpiCard:hover {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)

    def mousePressEvent(self, event) -> None:
        self.clicked.emit(self.cat_id)
        super().mousePressEvent(event)


class FieldInspectorWidget(QFrame):
    """Inspecteur déroulant 5 champs (NoteType, Recto, Verso, Extra, Tags)."""

    def __init__(self, original_data: Dict[str, str], proposal_data: Dict[str, str], parent: Optional[QWidget] = None) -> None:
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
        orig_box = QFrame()
        orig_box.setStyleSheet(f"background-color: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 4px; padding: 8px;")
        orig_layout = QVBoxLayout(orig_box)
        orig_title = QLabel("CARTE ACTUELLE EN BASE (SQLite)")
        orig_title.setFont(QFont(DesignTokens.FONT_MAIN, 10, QFont.Weight.Bold))
        orig_title.setStyleSheet("color: #f87171;")
        orig_layout.addWidget(orig_title)

        for key in ["NoteType", "Recto", "Verso", "Champ Annexe Extra", "Tags"]:
            val = original_data.get(key, "-")
            lbl = QLabel(f"<b>{key} :</b> {val}")
            lbl.setFont(QFont(DesignTokens.FONT_MAIN, 10))
            lbl.setWordWrap(True)
            lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY};")
            orig_layout.addWidget(lbl)

        # Proposal Panel
        prop_box = QFrame()
        prop_box.setStyleSheet(f"background-color: {DesignTokens.BG_PANEL}; border: 1px solid rgba(16,185,129,0.3); border-radius: 4px; padding: 8px;")
        prop_layout = QVBoxLayout(prop_box)
        prop_title = QLabel("PROPOSITION MUTÉE IA MCP")
        prop_title.setFont(QFont(DesignTokens.FONT_MAIN, 10, QFont.Weight.Bold))
        prop_title.setStyleSheet(f"color: {DesignTokens.COLOR_GREEN};")
        prop_layout.addWidget(prop_title)

        for key in ["NoteType", "Recto", "Verso", "Champ Annexe Extra", "Tags"]:
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

    def __init__(self, item_data: Dict[str, Any], parent: Optional[QWidget] = None) -> None:
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
        lbl_title = QLabel(item_data.get("title", "Carte"))
        lbl_title.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
        lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY};")

        lbl_badge = QLabel(item_data.get("badge", "Problème"))
        lbl_badge.setFont(QFont(DesignTokens.FONT_MAIN, 10, QFont.Weight.Bold))
        badge_color = item_data.get("badge_color", "#f87171")
        lbl_badge.setStyleSheet(f"background-color: rgba(239,68,68,0.15); color: {badge_color}; padding: 2px 6px; border-radius: 4px;")

        self.btn_inspect = SecondaryButton("Inspecter les 5 champs")
        self.btn_inspect.setFixedHeight(24)
        self.btn_inspect.clicked.connect(self.toggle_inspector)

        h_row.addWidget(lbl_title)
        h_row.addWidget(lbl_badge)
        h_row.addStretch()
        h_row.addWidget(self.btn_inspect)
        layout.addLayout(h_row)

        # Grille côte à côte (Carte Actuelle vs Proposition MCP)
        side_grid = QHBoxLayout()
        side_grid.setSpacing(10)

        # Gauche (Actuelle)
        orig_panel = QFrame()
        orig_panel.setStyleSheet(f"background-color: {DesignTokens.BG_MAIN}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 4px; padding: 8px;")
        op_layout = QVBoxLayout(orig_panel)
        op_title = QLabel("CARTE ACTUELLE EN BASE :")
        op_title.setFont(QFont(DesignTokens.FONT_MAIN, 9, QFont.Weight.Bold))
        op_title.setStyleSheet("color: #f87171;")

        orig_dict = item_data.get("original", {})
        op_text = QLabel(orig_dict.get("Recto", orig_dict.get("Text", "-")))
        op_text.setFont(QFont(DesignTokens.FONT_MAIN, 10))
        op_text.setWordWrap(True)
        op_text.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY};")

        op_layout.addWidget(op_title)
        op_layout.addWidget(op_text)

        # Droite (Proposition)
        prop_panel = QFrame()
        prop_panel.setStyleSheet(f"background-color: {DesignTokens.BG_MAIN}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 4px; padding: 8px;")
        pp_layout = QVBoxLayout(prop_panel)
        pp_title = QLabel(item_data.get("proposal_summary", "PROPOSITION MCP :"))
        pp_title.setFont(QFont(DesignTokens.FONT_MAIN, 9, QFont.Weight.Bold))
        pp_title.setStyleSheet(f"color: {DesignTokens.COLOR_GREEN};")

        prop_dict = item_data.get("proposal", {})
        pp_text = QLabel(prop_dict.get("Recto", "-"))
        pp_text.setFont(QFont(DesignTokens.FONT_MAIN, 10))
        pp_text.setWordWrap(True)
        pp_text.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY};")

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
        act_bar.setStyleSheet(f"background-color: {DesignTokens.BG_MAIN}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 4px;")
        ab_layout = QHBoxLayout(act_bar)
        ab_layout.setContentsMargins(8, 4, 8, 4)

        chk_synthese = QCheckBox("Générer la Carte Synthèse Master (#synthese)")
        chk_synthese.setChecked(True)
        chk_synthese.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 10px;")

        btn_ignore = SecondaryButton("Ignorer")
        btn_ignore.setFixedHeight(24)

        btn_apply = PrimaryButton("Valider la génération MCP")
        btn_apply.setFixedHeight(24)

        ab_layout.addWidget(chk_synthese)
        ab_layout.addStretch()
        ab_layout.addWidget(btn_ignore)
        ab_layout.addWidget(btn_apply)
        layout.addWidget(act_bar)

    def toggle_inspector(self) -> None:
        self.inspector_visible = not self.inspector_visible
        self.inspector_widget.setVisible(self.inspector_visible)
        self.btn_inspect.setText("Fermer l'inspecteur" if self.inspector_visible else "Inspecter les 5 champs")


class KatexLivePreviewWidget(QFrame):
    """Panneau interactif Live Preview KaTeX pour tester dynamiquement les formules."""

    def __init__(self, initial_formula: str = r"\int_{-\infty}^{\infty} |f(t)|^2 dt", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            KatexLivePreviewWidget {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid #c084fc;
                border-radius: 6px;
                padding: 8px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        lbl_title = QLabel("Panneau Live Preview KaTeX (Interactif)")
        lbl_title.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
        lbl_title.setStyleSheet("color: #c084fc;")
        layout.addWidget(lbl_title)

        self.input_formula = QLineEdit(initial_formula)
        self.input_formula.setStyleSheet(f"""
            QLineEdit {{
                background-color: {DesignTokens.BG_MAIN};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                color: #c084fc;
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

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(95)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        # Background
        painter.fillRect(0, 0, w, h, QColor(DesignTokens.BG_MAIN))

        # Grid lines
        pen_grid = QPen(QColor(DesignTokens.BORDER_COLOR), 1, Qt.PenStyle.DashLine)
        painter.setPen(pen_grid)
        painter.drawLine(30, 20, w - 20, 20)
        painter.drawLine(30, 50, w - 20, 50)

        pen_axis = QPen(QColor(DesignTokens.BORDER_COLOR), 1)
        painter.setPen(pen_axis)
        painter.drawLine(30, 75, w - 20, 75)

        # Labels
        painter.setPen(QColor(DesignTokens.TEXT_MUTED))
        painter.setFont(QFont(DesignTokens.FONT_MAIN, 8))
        painter.drawText(5, 23, "100%")
        painter.drawText(5, 53, "90%")
        painter.drawText(5, 78, "80%")

        # Target 90% Line
        pen_target = QPen(QColor(16, 185, 129, 150), 1.5, Qt.PenStyle.DashLine)
        painter.setPen(pen_target)
        painter.drawLine(30, 50, w - 20, 50)

        # Retention Path
        path = QPainterPath()
        path.moveTo(30, 20)
        path.cubicTo(100, 32, 200, 48, w - 20, 52)

        pen_curve = QPen(QColor(DesignTokens.ACCENT_PRIMARY), 2.5)
        painter.setPen(pen_curve)
        painter.drawPath(path)

        # Points
        painter.setBrush(QBrush(QColor(DesignTokens.ACCENT_PRIMARY)))
        painter.drawEllipse(30 - 3, 20 - 3, 6, 6)
        painter.drawEllipse(120 - 3, 33 - 3, 6, 6)
        painter.setBrush(QBrush(QColor(DesignTokens.COLOR_GREEN)))
        painter.drawEllipse(w - 20 - 3, 52 - 3, 6, 6)
