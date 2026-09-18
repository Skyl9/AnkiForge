"""Boîte de dialogue de prévisualisation et confirmation des réparations de titres."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ankiforge.services.markdown.models import HeadingRepairItem
from ankiforge.ui.components import PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_on_accent_icon, load_phosphor_icon

logger = logging.getLogger(__name__)


class RepairHeadingsDialog(QDialog):
    """Dialogue modal permettant de visualiser les sauts anormaux de titres et de choisir

    quelles corrections appliquer avant modification du document.
    """

    def __init__(self, repairs: list[HeadingRepairItem], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.repairs = list(repairs)
        self._selected_repairs: list[HeadingRepairItem] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setWindowTitle("Harmonisation des Titres Markdown")
        self.setMinimumWidth(640)
        self.setMinimumHeight(420)
        self.resize(700, 480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # En-tête avec icône et descriptif
        header_frame = QFrame()
        header_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 10px;
            }}
        """)
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(8, 8, 8, 8)
        header_layout.setSpacing(12)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(load_phosphor_icon("ph.wrench", color=DesignTokens.COLOR_YELLOW).pixmap(32, 32))
        header_layout.addWidget(icon_lbl)

        desc_layout = QVBoxLayout()
        desc_layout.setSpacing(3)

        title_lbl = QLabel(f"{len(self.repairs)} anomalie(s) de hiérarchie détectée(s)")
        title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 14px; font-weight: bold;")
        desc_layout.addWidget(title_lbl)

        sub_lbl = QLabel("AnkiForge a repéré des sauts de niveau illégaux (ex: H1 suivi directement de H3). Vérifiez ci-dessous les ajustements proposés. Rien ne sera modifié sans votre accord.")
        sub_lbl.setWordWrap(True)
        sub_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px;")
        desc_layout.addWidget(sub_lbl)

        header_layout.addLayout(desc_layout, 1)
        layout.addWidget(header_frame)

        # Tableau des réparations proposées
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Appliquer", "Ligne", "Titre de la Section", "Niveau", "Raison du saut"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)

        self.table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                color: {DesignTokens.TEXT_PRIMARY};
                gridline-color: {DesignTokens.BORDER_COLOR};
            }}
            QHeaderView::section {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_MUTED};
                font-size: 11px;
                font-weight: bold;
                padding: 6px;
                border: none;
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
            }}
        """)

        self.table.setRowCount(len(self.repairs))
        self._checkboxes: list[QCheckBox] = []

        for row, r in enumerate(self.repairs):
            # Checkbox
            cb = QCheckBox()
            cb.setChecked(True)
            cb_container = QWidget()
            cb_layout = QHBoxLayout(cb_container)
            cb_layout.addWidget(cb)
            cb_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cb_layout.setContentsMargins(0, 0, 0, 0)
            self.table.setCellWidget(row, 0, cb_container)
            self._checkboxes.append(cb)

            # Ligne
            item_line = QTableWidgetItem(f"L. {r.line_number}")
            item_line.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_line.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.table.setItem(row, 1, item_line)

            # Titre
            item_title = QTableWidgetItem(r.title)
            item_title.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.table.setItem(row, 2, item_title)

            # Transition de niveau (H3 -> H2)
            item_level = QTableWidgetItem(f"H{r.old_level} ➔ H{r.new_level}")
            item_level.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_level.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.table.setItem(row, 3, item_level)

            # Raison
            item_reason = QTableWidgetItem(r.reason)
            item_reason.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            item_reason.setForeground(QColor(DesignTokens.TEXT_MUTED))
            self.table.setItem(row, 4, item_reason)

        layout.addWidget(self.table, 1)

        # Barre de boutons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.btn_select_all = SecondaryButton("Tout cocher")
        self.btn_select_all.setFixedHeight(28)
        self.btn_select_all.clicked.connect(self._select_all)
        btn_layout.addWidget(self.btn_select_all)

        self.btn_deselect_all = SecondaryButton("Tout décocher")
        self.btn_deselect_all.setFixedHeight(28)
        self.btn_deselect_all.clicked.connect(self._deselect_all)
        btn_layout.addWidget(self.btn_deselect_all)

        btn_layout.addStretch(1)

        self.btn_cancel = SecondaryButton("Annuler")
        self.btn_cancel.setIcon(load_phosphor_icon("ph.x", color=DesignTokens.TEXT_MUTED))
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_apply = PrimaryButton("Appliquer les corrections")
        self.btn_apply.setIcon(load_on_accent_icon("ph.check"))
        self.btn_apply.clicked.connect(self._on_apply)
        btn_layout.addWidget(self.btn_apply)

        layout.addLayout(btn_layout)

    def _select_all(self) -> None:
        for cb in self._checkboxes:
            cb.setChecked(True)

    def _deselect_all(self) -> None:
        for cb in self._checkboxes:
            cb.setChecked(False)

    def accept(self) -> None:
        self._selected_repairs = [self.repairs[idx] for idx, cb in enumerate(self._checkboxes) if cb.isChecked()]
        super().accept()

    def _on_apply(self) -> None:
        self.accept()

    def get_selected_repairs(self) -> list[HeadingRepairItem]:
        """Retourne la liste des réparations cochées par l'utilisateur."""
        if not self._selected_repairs:
            return [self.repairs[idx] for idx, cb in enumerate(self._checkboxes) if cb.isChecked()]
        return self._selected_repairs
