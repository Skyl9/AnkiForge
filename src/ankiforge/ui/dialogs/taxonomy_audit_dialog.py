"""Dialogue d'audit de conformité de taxonomie et réparation assistée des tags.

Détecte les anomalies syntaxiques (espaces, segments vides, divergences de casse)
et permet l'application transactionnelle des réparations (substitution ou scission).
Conforme à l'ADR 0040, GEMINI.md Règles 2, 7, 8, 18, 19 et 20 et DESIGN.md.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ankiforge.services.cards.taxonomy_service import (
    TaxonomyAuditReport,
    TaxonomyRepairAction,
    TaxonomyService,
)
from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.i18n import tr
from ankiforge.utils.icon_loader import load_phosphor_icon
from ankiforge.utils.tags import normalize_tag_input, split_tag_tokens

logger = logging.getLogger(__name__)


class TaxonomyAuditDialog(QDialog):
    """Dialogue modal d'audit et réparation de la taxonomie des tags."""

    def __init__(self, deck_id: int | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.deck_id = deck_id
        self._report: TaxonomyAuditReport | None = None

        self.setWindowTitle(self.tr("Audit de Conformité de la Taxonomie"))
        self.setMinimumSize(680, 480)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {DesignTokens.BG_PANEL};
            }}
        """)

        self._init_ui()
        self._run_audit()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # En-tête
        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)

        ico = QLabel()
        ico.setPixmap(load_phosphor_icon("shield-check", color=DesignTokens.ACCENT_PRIMARY).pixmap(24, 24))
        header_layout.addWidget(ico)

        self.lbl_summary = QLabel(self.tr("Analyse de la collection en cours..."))
        self.lbl_summary.setStyleSheet(f"""
            color: {DesignTokens.TEXT_PRIMARY};
            font-size: 13px;
            font-weight: bold;
            font-family: '{DesignTokens.FONT_MAIN}';
        """)
        header_layout.addWidget(self.lbl_summary, stretch=1)
        layout.addLayout(header_layout)

        # Table des anomalies
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            [
                self.tr("Appliquer"),
                self.tr("Tag actuel (Anomalie)"),
                self.tr("Notes"),
                self.tr("Correction proposée"),
                self.tr("Mode"),
            ]
        )
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-family: '{DesignTokens.FONT_MAIN}';
                gridline-color: {DesignTokens.BORDER_COLOR};
            }}
            QHeaderView::section {{
                background-color: {DesignTokens.BG_SIDEBAR};
                color: {DesignTokens.TEXT_SECONDARY};
                font-size: 11px;
                padding: 4px;
                border: none;
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
            }}
        """)
        layout.addWidget(self.table)

        # Footer
        footer_layout = QHBoxLayout()
        footer_layout.setSpacing(10)

        self.btn_select_all = SecondaryButton(self.tr("Tout cocher"))
        self.btn_select_all.clicked.connect(self._select_all_checkboxes)
        footer_layout.addWidget(self.btn_select_all)

        footer_layout.addStretch()

        btn_cancel = SecondaryButton(self.tr("Fermer"))
        btn_cancel.clicked.connect(self.close)
        footer_layout.addWidget(btn_cancel)

        self.btn_apply = PrimaryButton(self.tr("Appliquer les réparations"))
        self.btn_apply.clicked.connect(self._apply_repairs)
        footer_layout.addWidget(self.btn_apply)

        layout.addLayout(footer_layout)

    def _run_audit(self) -> None:
        """Exécute l'audit et peuple le tableau."""
        self._report = TaxonomyService.audit_taxonomy(self.deck_id)
        self.table.setRowCount(0)

        if not self._report.anomalies:
            self.lbl_summary.setText(self.tr("Aucun problème détecté : l'ensemble des tags respecte la syntaxe Anki."))
            self.btn_apply.setEnabled(False)
            self.btn_select_all.setEnabled(False)
            return

        self.lbl_summary.setText(
            tr(
                "%1 anomalie%2 détectée%3 sur %4 note%5.",
                self._report.total_anomalies_count,
                "s" if self._report.total_anomalies_count > 1 else "",
                "s" if self._report.total_anomalies_count > 1 else "",
                self._report.total_notes_impacted,
                "s" if self._report.total_notes_impacted > 1 else "",
            )
        )
        self.btn_apply.setEnabled(True)
        self.btn_select_all.setEnabled(True)

        self.table.setRowCount(len(self._report.anomalies))

        labels_map = {
            "has_spaces": self.tr("Espaces interdits"),
            "malformed_hierarchy": self.tr("Hiérarchie '::' invalide"),
            "empty": self.tr("Tag vide"),
            "control_chars": self.tr("Caractères non imprimables"),
            "case_variant": self.tr("Variante de casse"),
        }

        for row, item in enumerate(self._report.anomalies):
            # 0. Checkbox
            cb = QCheckBox()
            cb.setChecked(True)
            cb_container = QWidget()
            cb_layout = QHBoxLayout(cb_container)
            cb_layout.setContentsMargins(8, 0, 0, 0)
            cb_layout.addWidget(cb)
            self.table.setCellWidget(row, 0, cb_container)

            # 1. Tag actuel + anomalie
            translated_issues = [labels_map.get(i, i) for i in item.anomalies]
            issues_str = ", ".join(translated_issues)
            desc_item = QTableWidgetItem(f"{item.tag} ({issues_str})")
            desc_item.setData(Qt.ItemDataRole.UserRole, item.tag)
            self.table.setItem(row, 1, desc_item)

            # 2. Nombre de notes
            count_item = QTableWidgetItem(str(item.notes_count))
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 2, count_item)

            # 3. Champ d'édition de la correction
            edit_target = QLineEdit(item.suggested_repair)
            edit_target.setStyleSheet(f"""
                QLineEdit {{
                    background-color: {DesignTokens.BG_INPUT};
                    color: {DesignTokens.TEXT_PRIMARY};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: 4px;
                    padding: 2px 4px;
                }}
            """)
            self.table.setCellWidget(row, 3, edit_target)

            # 4. Mode (Remplacer / Scinder)
            combo_mode = QComboBox()
            combo_mode.addItem(self.tr("Remplacer (_)"), "replace")
            combo_mode.addItem(self.tr("Scinder en plusieurs"), "split")
            if "has_spaces" in item.anomalies:
                combo_mode.setCurrentIndex(0)
            self.table.setCellWidget(row, 4, combo_mode)

    def _select_all_checkboxes(self) -> None:
        for r in range(self.table.rowCount()):
            cb_container = self.table.cellWidget(r, 0)
            if cb_container:
                cb = cb_container.findChild(QCheckBox)
                if cb:
                    cb.setChecked(True)

    def _apply_repairs(self) -> None:
        """Collecte les réparations cochées et les applique."""
        repairs: list[TaxonomyRepairAction] = []

        for r in range(self.table.rowCount()):
            cb_container = self.table.cellWidget(r, 0)
            if not cb_container:
                continue
            cb = cb_container.findChild(QCheckBox)
            if not cb or not cb.isChecked():
                continue

            tag_item = self.table.item(r, 1)
            old_tag = tag_item.data(Qt.ItemDataRole.UserRole) if tag_item else ""
            if not old_tag:
                continue

            edit_target = self.table.cellWidget(r, 3)
            target_text = edit_target.text().strip() if isinstance(edit_target, QLineEdit) else ""

            combo_mode = self.table.cellWidget(r, 4)
            mode = combo_mode.currentData() if isinstance(combo_mode, QComboBox) else "replace"

            if mode == "split":
                repairs.append(
                    TaxonomyRepairAction(
                        old_tag=old_tag,
                        repair_mode="split",
                        split_tags=split_tag_tokens(target_text or old_tag),
                    )
                )
            else:
                repairs.append(
                    TaxonomyRepairAction(
                        old_tag=old_tag,
                        repair_mode="replace",
                        target_tag=normalize_tag_input(target_text or old_tag),
                    )
                )

        if not repairs:
            QMessageBox.information(
                self,
                self.tr("Aucune réparation"),
                self.tr("Veuillez cocher au moins une anomalie à réparer."),
            )
            return

        result = TaxonomyService.apply_taxonomy_repairs(repairs, self.deck_id)
        if result.success:
            self._notify_info(
                self.tr("Réparations appliquées"),
                tr(
                    "%1 tag(s) réparé(s) avec succès sur %2 note(s).",
                    result.repaired_tags_count,
                    result.modified_notes_count,
                ),
            )
            self._run_audit()
        else:
            self._notify_error(
                self.tr("Échec de la réparation"),
                tr("Une erreur est survenue lors de la transaction :\n%1", result.error_message or ""),
            )

    def _notify_info(self, title: str, text: str) -> None:
        QMessageBox.information(self, title, text)

    def _notify_error(self, title: str, text: str) -> None:
        QMessageBox.critical(self, title, text)
