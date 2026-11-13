"""Sous-onglet adaptatif de pilotage du workspace agentique (drift, synchronisation, amorçage).

Affiche l'état de conformité du workspace mémorisé, propose une matrice de conformité
interactive et un inspecteur contextuel, et déclenche les actions d'audit /
resynchronisation / amorçage via WorkspaceSyncService.
"""

from __future__ import annotations

import difflib
import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ankidraft.services.ai.workspace_sync_service import (
    DriftCategory,
    DriftItem,
    DriftSeverity,
    WorkspaceDriftReport,
    WorkspaceSyncService,
)
from ankidraft.ui.components.badges import StatusBadge
from ankidraft.ui.components.buttons import PrimaryButton, SecondaryButton, apply_compact_style
from ankidraft.ui.theme import DesignTokens
from ankidraft.ui.widgets.toast import show_toast
from ankidraft.utils.environment import get_app_qsettings
from ankidraft.utils.i18n import tr
from ankidraft.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)

_SETTINGS_KEY = "mcp/last_agent_workspace_path"
_DEFAULT_WORKSPACE = Path.home() / "ankiforge_agentique"

_MATRIX_ROWS: list[tuple[str, str, DriftCategory, str | None]] = [
    ("Structure", "ph.table", DriftCategory.STRUCTURE, ""),
    ("Profil actif", "ph.info", DriftCategory.ACTIVE_PROFILE, ".agents/active-profile.md"),
    ("Catalogue FastMCP", "ph.magnifying-glass", DriftCategory.MCP_CATALOG, ".agents/mcp-catalog.md"),
    ("Conventions", "ph.layout", DriftCategory.CORE_SYSTEM, ".agents/rules/ankidraft-conventions.md"),
    ("Compétences", "ph.robot", DriftCategory.SKILLS, None),
    ("Éléments utilisateur protégés", "ph.folder", DriftCategory.USER_CONTEXT, None),
]

_SEVERITY_VARIANT: dict[DriftSeverity, tuple[str, str]] = {
    DriftSeverity.OK: ("success", "Conforme"),
    DriftSeverity.PROTECTED: ("neutral", "Sanctuarisé"),
    DriftSeverity.OUTDATED: ("warning", "Obsolète"),
    DriftSeverity.DESYNC: ("warning", "Désynchronisé"),
    DriftSeverity.CUSTOMIZED: ("warning", "Personnalisé"),
    DriftSeverity.CRITICAL: ("danger", "Critique"),
}

_STATE_SIZES: dict[str, list[int]] = {
    "not_initialized": [650, 350],
    "drift_detected": [500, 500],
    "synchronized": [450, 550],
}

_SEVERITY_RANK: dict[DriftSeverity, int] = {
    DriftSeverity.OK: 0,
    DriftSeverity.PROTECTED: 1,
    DriftSeverity.CUSTOMIZED: 2,
    DriftSeverity.OUTDATED: 3,
    DriftSeverity.DESYNC: 4,
    DriftSeverity.CRITICAL: 5,
}


class MCPWorkspaceGuideWidget(QWidget):
    """Composant sous-onglet adaptatif de pilotage du workspace agentique MCP."""

    def __init__(
        self,
        parent: QWidget | None = None,
        service: WorkspaceSyncService | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("MCPWorkspaceGuideWidget")

        self._service = service or WorkspaceSyncService()
        self._settings = get_app_qsettings()
        self._last_layout_state: str | None = None
        self._current_report: WorkspaceDriftReport | None = None

        self._setup_ui()
        self._restore_workspace_path()
        self._refresh_ui_state(None)
        self.reload_personas()

    @property
    def current_report(self) -> WorkspaceDriftReport | None:
        """Retourne le dernier rapport d'audit du workspace."""
        return self._current_report

    def _setup_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(*DesignTokens.DESIGN_SYSTEM_MARGES["mcp_root"])
        root_layout.setSpacing(DesignTokens.DESIGN_SYSTEM_SPACING["mcp_root"])

        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.splitter.setObjectName("mcp_workspace_splitter")
        self.splitter.setChildrenCollapsible(False)

        # ═══════════════════════════════════════════════════════════════════════
        # PANNEAU GAUCHE : état global, chemin, matrice et actions
        # ═══════════════════════════════════════════════════════════════════════
        self.left_container = QWidget(self.splitter)
        left_layout = QVBoxLayout(self.left_container)
        left_layout.setContentsMargins(0, 0, 8, 0)
        left_layout.setSpacing(DesignTokens.DESIGN_SYSTEM_SPACING["row_controls"])

        self.card_state = QFrame(self.left_container)
        self.card_state.setObjectName("mcp_card_state")
        state_layout = QVBoxLayout(self.card_state)
        state_layout.setContentsMargins(16, 14, 16, 16)
        state_layout.setSpacing(10)

        header_state = QHBoxLayout()
        header_state.setSpacing(8)
        lbl_state_icon = QLabel(self.card_state)
        lbl_state_icon.setPixmap(load_phosphor_icon("ph.layout", color=DesignTokens.ACCENT_PRIMARY).pixmap(20, 20))
        header_state.addWidget(lbl_state_icon)

        lbl_state_title = QLabel(self.tr("Espace de travail agentique"), self.card_state)
        lbl_state_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 14px; font-weight: 700; border: none; background: transparent;")
        header_state.addWidget(lbl_state_title)
        header_state.addStretch()
        state_layout.addLayout(header_state)

        hero_row = QHBoxLayout()
        hero_row.setSpacing(10)
        lbl_hero_tag = QLabel(self.tr("État global :"), self.card_state)
        lbl_hero_tag.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 12px; border: none; background: transparent;")
        hero_row.addWidget(lbl_hero_tag)

        self.hero_badge = StatusBadge(self.tr("Non Initialisé"), "ph.x-circle", variant="danger")
        self.hero_badge.setObjectName("mcp_hero_badge")
        hero_row.addWidget(self.hero_badge)

        self.lbl_drift_count = QLabel(self.tr("—"), self.card_state)
        self.lbl_drift_count.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; border: none; background: transparent;")
        hero_row.addWidget(self.lbl_drift_count)
        hero_row.addStretch()
        state_layout.addLayout(hero_row)

        lbl_path = QLabel(self.tr("Répertoire de travail :"), self.card_state)
        lbl_path.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 600; border: none; background: transparent;")
        state_layout.addWidget(lbl_path)

        path_row = QHBoxLayout()
        path_row.setSpacing(6)

        self.edit_workspace_path = QLineEdit(self.card_state)
        self.edit_workspace_path.setObjectName("mcp_edit_workspace_path")
        self.edit_workspace_path.setPlaceholderText(self.tr("ex: ~/mon-projet ou /chemin/vers/workspace"))
        self.edit_workspace_path.setStyleSheet(
            f"background-color: {DesignTokens.BG_INPUT}; color: {DesignTokens.TEXT_PRIMARY}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 6px; padding: 6px 10px; font-size: 12px;"
        )
        self.edit_workspace_path.editingFinished.connect(self._on_path_edited)
        path_row.addWidget(self.edit_workspace_path, 1)

        self.btn_browse = SecondaryButton(self.tr("Parcourir..."), parent=self.card_state)
        self.btn_browse.setObjectName("mcp_btn_browse_workspace")
        self.btn_browse.setIcon(load_phosphor_icon("ph.folder-open", color=DesignTokens.TEXT_PRIMARY))
        apply_compact_style(self.btn_browse, height=30)
        self.btn_browse.clicked.connect(self._on_browse_workspace)
        path_row.addWidget(self.btn_browse)
        state_layout.addLayout(path_row)

        lbl_matrix = QLabel(self.tr("Matrice de conformité"), self.card_state)
        lbl_matrix.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 600; border: none; background: transparent;")
        state_layout.addWidget(lbl_matrix)

        self.matrix = QTableWidget(self.card_state)
        self.matrix.setObjectName("mcp_matrix")
        self.matrix.setColumnCount(3)
        self.matrix.setHorizontalHeaderLabels([self.tr("Composant"), self.tr("Statut"), self.tr("Détail")])
        self.matrix.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.matrix.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.matrix.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.matrix.verticalHeader().hide()
        self.matrix.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.matrix.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.matrix.setShowGrid(False)
        self.matrix.setStyleSheet(f"QTableWidget#mcp_matrix {{ background-color: {DesignTokens.BG_INPUT}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 6px; }}")
        self.matrix.itemSelectionChanged.connect(self._on_matrix_selection)
        state_layout.addWidget(self.matrix, 1)

        btn_action_row = QHBoxLayout()
        btn_action_row.setSpacing(8)

        self.btn_verify_drift = PrimaryButton(self.tr("Vérifier le drift"), parent=self.card_state)
        self.btn_verify_drift.setObjectName("mcp_btn_verify_drift")
        self.btn_verify_drift.setIcon(load_phosphor_icon("ph.magnifying-glass", color=DesignTokens.TEXT_PRIMARY))
        apply_compact_style(self.btn_verify_drift, height=36)
        self.btn_verify_drift.clicked.connect(self._on_verify_drift)
        btn_action_row.addWidget(self.btn_verify_drift)

        self.btn_sync_workspace = SecondaryButton(self.tr("Resynchroniser"), parent=self.card_state)
        self.btn_sync_workspace.setObjectName("mcp_btn_sync_workspace")
        self.btn_sync_workspace.setIcon(load_phosphor_icon("ph.arrows-clockwise", color=DesignTokens.TEXT_PRIMARY))
        apply_compact_style(self.btn_sync_workspace, height=36)
        self.btn_sync_workspace.clicked.connect(self._on_sync_workspace)
        btn_action_row.addWidget(self.btn_sync_workspace)

        self.btn_init_workspace = SecondaryButton(self.tr("Amorcer le workspace"), parent=self.card_state)
        self.btn_init_workspace.setObjectName("mcp_btn_init_workspace")
        self.btn_init_workspace.setIcon(load_phosphor_icon("ph.sparkle", color=DesignTokens.TEXT_PRIMARY))
        apply_compact_style(self.btn_init_workspace, height=36)
        self.btn_init_workspace.clicked.connect(self._on_init_workspace)
        btn_action_row.addWidget(self.btn_init_workspace)

        btn_action_row.addStretch()
        state_layout.addLayout(btn_action_row)

        left_layout.addWidget(self.card_state, 1)
        self.splitter.addWidget(self.left_container)

        # ═══════════════════════════════════════════════════════════════════════
        # PANNEAU DROIT : inspecteur contextuel (explication / diff / markdown)
        # ═══════════════════════════════════════════════════════════════════════
        self.card_inspector = QFrame(self.splitter)
        self.card_inspector.setObjectName("mcp_card_inspector")
        inspector_layout = QVBoxLayout(self.card_inspector)
        inspector_layout.setContentsMargins(16, 14, 16, 16)
        inspector_layout.setSpacing(10)

        header_inspector = QHBoxLayout()
        header_inspector.setSpacing(8)
        lbl_inspector_icon = QLabel(self.card_inspector)
        lbl_inspector_icon.setPixmap(load_phosphor_icon("ph.info", color=DesignTokens.ACCENT_PRIMARY).pixmap(20, 20))
        header_inspector.addWidget(lbl_inspector_icon)

        lbl_inspector_title = QLabel(self.tr("Inspecteur contextuel"), self.card_inspector)
        lbl_inspector_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 14px; font-weight: 700; border: none; background: transparent;")
        header_inspector.addWidget(lbl_inspector_title)
        header_inspector.addStretch()
        inspector_layout.addLayout(header_inspector)

        self.lbl_inspector_target = QLabel(self.tr("Sélectionnez un composant dans la matrice."), self.card_inspector)
        self.lbl_inspector_target.setWordWrap(True)
        self.lbl_inspector_target.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11.5px; border: none; background: transparent;")
        inspector_layout.addWidget(self.lbl_inspector_target)

        view_row = QHBoxLayout()
        view_row.setSpacing(6)

        self.btn_view_explanation = SecondaryButton(self.tr("Explication"), parent=self.card_inspector)
        self.btn_view_explanation.setObjectName("mcp_btn_view_explanation")
        apply_compact_style(self.btn_view_explanation, height=28)
        self.btn_view_explanation.clicked.connect(lambda: self._set_inspector_page(0))
        view_row.addWidget(self.btn_view_explanation)

        self.btn_view_diff = SecondaryButton(self.tr("Diff"), parent=self.card_inspector)
        self.btn_view_diff.setObjectName("mcp_btn_view_diff")
        apply_compact_style(self.btn_view_diff, height=28)
        self.btn_view_diff.clicked.connect(lambda: self._set_inspector_page(1))
        view_row.addWidget(self.btn_view_diff)

        self.btn_view_markdown = SecondaryButton(self.tr("Aperçu Markdown"), parent=self.card_inspector)
        self.btn_view_markdown.setObjectName("mcp_btn_view_markdown")
        apply_compact_style(self.btn_view_markdown, height=28)
        self.btn_view_markdown.clicked.connect(lambda: self._set_inspector_page(2))
        view_row.addWidget(self.btn_view_markdown)

        view_row.addStretch()
        inspector_layout.addLayout(view_row)

        self.inspector_pages = QStackedWidget(self.card_inspector)
        self.inspector_pages.setObjectName("mcp_inspector_pages")

        self.page_explanation = QTextBrowser(self.card_inspector)
        self.page_explanation.setObjectName("mcp_page_explanation")
        self.page_explanation.setOpenExternalLinks(False)
        self.page_explanation.setStyleSheet(
            f"QTextBrowser#mcp_page_explanation {{ background-color: {DesignTokens.BG_INPUT}; "
            f"color: {DesignTokens.TEXT_PRIMARY}; border: 1px solid {DesignTokens.BORDER_COLOR}; "
            f"border-radius: 6px; padding: 14px; font-size: 12.5px; }}"
        )
        self.inspector_pages.addWidget(self.page_explanation)

        self.page_diff = QTextBrowser(self.card_inspector)
        self.page_diff.setObjectName("mcp_page_diff")
        self.page_diff.setOpenExternalLinks(False)
        self.page_diff.setStyleSheet(
            f"QTextBrowser#mcp_page_diff {{ background-color: {DesignTokens.BG_INPUT}; "
            f"color: {DesignTokens.TEXT_PRIMARY}; border: 1px solid {DesignTokens.BORDER_COLOR}; "
            f"border-radius: 6px; padding: 14px; font-family: {DesignTokens.FONT_CODE}; font-size: 12px; }}"
        )
        self.inspector_pages.addWidget(self.page_diff)

        self.page_markdown = QTextBrowser(self.card_inspector)
        self.page_markdown.setObjectName("mcp_page_markdown")
        self.page_markdown.setOpenExternalLinks(True)
        self.page_markdown.setStyleSheet(
            f"QTextBrowser#mcp_page_markdown {{ background-color: {DesignTokens.BG_INPUT}; "
            f"color: {DesignTokens.TEXT_PRIMARY}; border: 1px solid {DesignTokens.BORDER_COLOR}; "
            f"border-radius: 6px; padding: 14px; font-size: 12.5px; }}"
        )
        self.inspector_pages.addWidget(self.page_markdown)

        inspector_layout.addWidget(self.inspector_pages, 1)

        self.splitter.addWidget(self.card_inspector)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 1)

        root_layout.addWidget(self.splitter, 1)
        self.refresh_theme(None)

    # ── Persistance du chemin de workspace (QSettings) ──────────────────────

    def _on_path_edited(self) -> None:
        path = self._workspace_path()
        if path:
            self._save_workspace_path(path)

    def _workspace_path(self) -> str:
        return self.edit_workspace_path.text().strip()

    def _save_workspace_path(self, path: str) -> None:
        self._settings.setValue(_SETTINGS_KEY, path)

    def _restore_workspace_path(self) -> None:
        value = self._settings.value(_SETTINGS_KEY)
        candidate: Path | None = Path(str(value)) if value is not None and str(value) else None
        if candidate is not None and candidate.exists():
            self.edit_workspace_path.setText(str(candidate))
            return
        if _DEFAULT_WORKSPACE.exists():
            self.edit_workspace_path.setText(str(_DEFAULT_WORKSPACE))
            return
        self.edit_workspace_path.setText(str(Path.home()))

    # ── Actions ─────────────────────────────────────────────────────────────

    def _on_browse_workspace(self) -> None:
        current_text = self._workspace_path()
        start_dir = current_text if current_text and Path(current_text).exists() else str(Path.home())
        selected = QFileDialog.getExistingDirectory(
            self,
            self.tr("Sélectionner le répertoire cible du workspace"),
            start_dir,
        )
        if selected:
            self.edit_workspace_path.setText(selected)
            self._save_workspace_path(selected)

    def _run_service_action(self, action) -> WorkspaceDriftReport | None:
        path = self._workspace_path()
        if not path:
            show_toast(self, self.tr("Renseignez un répertoire de workspace."), level="warning")
            return None
        self._save_workspace_path(path)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        report: WorkspaceDriftReport | None = None
        try:
            try:
                report = action(path)
            except ValueError as exc:
                show_toast(self, str(exc), level="danger")
                return None
        finally:
            QApplication.restoreOverrideCursor()
        if report is None:
            return None
        return report

    def _on_verify_drift(self) -> None:
        report = self._run_service_action(self._service.audit_workspace)
        if report is None:
            return
        self._refresh_ui_state(report)
        show_toast(self, tr("Audit terminé : %1 écart(s)", report.drift_count), level="info")

    def _on_sync_workspace(self) -> None:
        report = self._run_service_action(self._service.sync_workspace)
        if report is None:
            return
        self._refresh_ui_state(report)
        show_toast(self, tr("Resynchronisation terminée : %1 écart(s)", report.drift_count), level="info")

    def _on_init_workspace(self) -> None:
        report = self._run_service_action(self._service.initialize_workspace)
        if report is None:
            return
        self._refresh_ui_state(report)
        show_toast(self, tr("Workspace amorcé : %1 écart(s)", report.drift_count), level="info")

    # ── Rafraîchissement de l'UI à partir d'un rapport ──────────────────────

    def _refresh_ui_state(self, report: WorkspaceDriftReport | None) -> None:
        self._current_report = report
        state = self._state_for_report(report)
        self._update_adaptive_layout(state)

        if report is not None:
            label, icon_name, variant = self._hero_for_status(report.overall_status)
            self.hero_badge.set_status(label, icon_name, variant)
            if report.drift_count > 0:
                self.lbl_drift_count.setText(tr("%1 écart(s)", report.drift_count))
            else:
                self.lbl_drift_count.setText(self.tr("Aucun écart"))
        else:
            self.hero_badge.set_status(self.tr("Non Initialisé"), "ph.x-circle", variant="danger")
            self.lbl_drift_count.setText(self.tr("—"))

        self._refresh_matrix(report)
        self._clear_inspector()

    def _state_for_report(self, report: WorkspaceDriftReport | None) -> str:
        if report is None or not report.is_initialized:
            return "not_initialized"
        if report.drift_count > 0:
            return "drift_detected"
        return "synchronized"

    def _hero_for_status(self, overall_status: DriftSeverity) -> tuple[str, str, str]:
        if overall_status == DriftSeverity.OK:
            return (self.tr("Synchronisé"), "ph.check-circle", "success")
        if overall_status == DriftSeverity.CRITICAL:
            return (self.tr("Non Initialisé"), "ph.x-circle", "danger")
        if overall_status in (DriftSeverity.DESYNC, DriftSeverity.OUTDATED, DriftSeverity.CUSTOMIZED):
            return (self.tr("Dérive Détectée"), "ph.warning-circle", "warning")
        return (self.tr("Erreur"), "ph.info", "neutral")

    def _update_adaptive_layout(self, new_state: str) -> None:
        if new_state == self._last_layout_state:
            return
        self._last_layout_state = new_state
        self.splitter.setSizes(_STATE_SIZES[new_state])

    def _refresh_matrix(self, report: WorkspaceDriftReport | None) -> None:
        self.matrix.setRowCount(0)
        items_by_path = {item.relative_path: item for item in report.items} if report else {}
        for row_index, (label, _icon_name, category, _target) in enumerate(_MATRIX_ROWS):
            self.matrix.insertRow(row_index)
            comp_item = QTableWidgetItem(self.tr(label))
            comp_item.setData(Qt.ItemDataRole.UserRole, row_index)
            self.matrix.setItem(row_index, 0, comp_item)

            status_text, variant, detail = self._resolve_row(report, category, items_by_path)
            badge = StatusBadge(status_text, _icon_name, variant)
            self.matrix.setCellWidget(row_index, 1, badge)

            detail_item = QTableWidgetItem(detail)
            self.matrix.setItem(row_index, 2, detail_item)

    def _resolve_row(
        self,
        report: WorkspaceDriftReport | None,
        category: DriftCategory,
        items_by_path: dict[str, DriftItem],
    ) -> tuple[str, str, str]:
        if report is None or not report.is_initialized:
            return (self.tr("Non initialisé"), "danger", self.tr("Workspace non initialisé"))

        if category == DriftCategory.STRUCTURE:
            return (self.tr("Conforme"), "success", self.tr("Fichiers maîtres présents"))

        if category == DriftCategory.ACTIVE_PROFILE:
            detected = report.detected_profile_name
            active = report.active_profile_name
            if not detected:
                return (self.tr("Non détecté"), "warning", self.tr("active-profile.md absent"))
            if detected == active:
                return (self.tr("Aligné"), "success", detected or "")
            return (self.tr("Dérive"), "warning", tr("%1 ≠ %2", detected, active))

        if category == DriftCategory.MCP_CATALOG:
            item = items_by_path.get(".agents/mcp-catalog.md")
            return self._item_status(item) if item else (self.tr("Absent"), "danger", self.tr(".agents/mcp-catalog.md manquant"))

        if category == DriftCategory.CORE_SYSTEM:
            item = items_by_path.get(".agents/rules/ankidraft-conventions.md")
            return self._item_status(item) if item else (self.tr("Absent"), "danger", self.tr("Conventions manquantes"))

        if category == DriftCategory.SKILLS:
            skill_items = [item for item in report.items if item.category == DriftCategory.SKILLS]
            if not skill_items:
                return (self.tr("Aucune"), "neutral", self.tr("Aucune compétence référencée"))
            worst = max(skill_items, key=lambda item: _SEVERITY_RANK[item.severity])
            return self._item_status(worst)

        if category == DriftCategory.USER_CONTEXT:
            protected = [item for item in report.items if item.is_user_protected]
            if protected:
                return (self.tr("Sanctuarisé"), "neutral", tr("%1 élément(s) protégé(s)", len(protected)))
            return (self.tr("Aucun"), "neutral", self.tr("Aucun dossier utilisateur détecté"))

        return (self.tr("—"), "neutral", "")

    def _item_status(self, item: DriftItem) -> tuple[str, str, str]:
        variant, label = _SEVERITY_VARIANT[item.severity]
        return (self.tr(label), variant, item.message)

    # ── Inspecteur contextuel ───────────────────────────────────────────────

    def _on_matrix_selection(self) -> None:
        selected = self.matrix.selectedItems()
        if not selected or self._current_report is None:
            return
        row = selected[0].data(Qt.ItemDataRole.UserRole)
        if row is None:
            return
        report = self._current_report
        target = _MATRIX_ROWS[row][3]
        items_by_path = {item.relative_path: item for item in report.items}
        item = items_by_path.get(target) if target else None
        self._show_inspector(item, report)

    def _show_inspector(self, item: DriftItem | None, report: WorkspaceDriftReport) -> None:
        root = Path(report.workspace_path)

        if item is None:
            self.lbl_inspector_target.setText(self.tr("Sélectionnez un composant dans la matrice."))
            self.page_explanation.setPlainText(self.tr("Aucun détail disponible."))
            self.page_diff.setPlainText("")
            self.page_markdown.setPlainText("")
            self._set_inspector_page(0)
            return

        self.lbl_inspector_target.setText(item.relative_path or self.tr("Racine du workspace"))

        explanation = self.tr("%1 — %2", item.severity.value, item.message)
        self.page_explanation.setPlainText(explanation)

        if item.relative_path:
            local_path = root / item.relative_path
            local_text = local_path.read_text(encoding="utf-8") if local_path.is_file() else ""
            self.page_markdown.setMarkdown(local_text or self.tr("Fichier absent sur disque."))
            template_rel = self._service._template_for_target(item.relative_path)
            expected_text = self._service._render(template_rel) if template_rel else ""
            self.page_diff.setHtml(self._diff_html(local_text, expected_text))
        else:
            self.page_markdown.setPlainText(self.tr("Aucun fichier associé à ce composant."))
            self.page_diff.setPlainText("")

        self._set_inspector_page(0)

    def _clear_inspector(self) -> None:
        self.lbl_inspector_target.setText(self.tr("Sélectionnez un composant dans la matrice."))
        self.page_explanation.setPlainText("")
        self.page_diff.setPlainText("")
        self.page_markdown.setPlainText("")
        self._set_inspector_page(0)

    def _set_inspector_page(self, index: int) -> None:
        self.inspector_pages.setCurrentIndex(index)

    def _diff_html(self, local_text: str, expected_text: str) -> str:
        lines: list[str] = []
        for line in difflib.ndiff(local_text.splitlines(keepends=True), expected_text.splitlines(keepends=True)):
            clean = line.rstrip("\n")
            if line.startswith("+ "):
                lines.append(f'<span style="color: {DesignTokens.COLOR_GREEN};">+ {clean}</span>')
            elif line.startswith("- "):
                lines.append(f'<span style="color: {DesignTokens.COLOR_RED};">- {clean}</span>')
            elif line.startswith("? "):
                continue
            else:
                lines.append(f'<span style="color: {DesignTokens.TEXT_MUTED};">  {clean}</span>')
        return "<br>".join(lines) if lines else self.tr("Identique.")

    # ── Thème ───────────────────────────────────────────────────────────────

    def refresh_theme(self, profile: Any) -> None:
        """Adapte les styles et les couleurs selon le profil de thème actif."""
        bg_panel = getattr(profile, "bg_panel", DesignTokens.BG_PANEL)
        border_color = getattr(profile, "border_color", DesignTokens.BORDER_COLOR)
        bg_input = getattr(profile, "bg_input", DesignTokens.BG_INPUT)
        text_primary = getattr(profile, "text_primary", DesignTokens.TEXT_PRIMARY)
        text_secondary = getattr(profile, "text_secondary", DesignTokens.TEXT_SECONDARY)

        if hasattr(self, "card_state"):
            self.card_state.setStyleSheet(f"QFrame#mcp_card_state {{ background-color: {bg_panel}; border: 1px solid {border_color}; border-radius: 8px; }}")
        if hasattr(self, "card_inspector"):
            self.card_inspector.setStyleSheet(f"QFrame#mcp_card_inspector {{ background-color: {bg_panel}; border: 1px solid {border_color}; border-radius: 8px; }}")
        if hasattr(self, "edit_workspace_path"):
            self.edit_workspace_path.setStyleSheet(f"background-color: {bg_input}; color: {text_primary}; border: 1px solid {border_color}; border-radius: 6px; padding: 6px 10px; font-size: 12px;")
        if hasattr(self, "matrix"):
            self.matrix.setStyleSheet(f"QTableWidget#mcp_matrix {{ background-color: {bg_input}; border: 1px solid {border_color}; border-radius: 6px; }}")
        if hasattr(self, "hero_badge"):
            self.hero_badge.refresh_theme(profile)
        if hasattr(self, "page_explanation"):
            base = f"QTextBrowser {{ background-color: {bg_input}; color: {text_primary}; border: 1px solid {border_color}; border-radius: 6px; padding: 14px; }}"
            self.page_explanation.setStyleSheet(base)
            self.page_markdown.setStyleSheet(base)
        if hasattr(self, "page_diff"):
            self.page_diff.setStyleSheet(
                f"QTextBrowser {{ background-color: {bg_input}; color: {text_primary}; "
                f"border: 1px solid {border_color}; border-radius: 6px; padding: 14px; font-family: {DesignTokens.FONT_CODE}; font-size: 12px; }}"
            )
        if hasattr(self, "lbl_inspector_target"):
            self.lbl_inspector_target.setStyleSheet(f"color: {text_secondary}; font-size: 11.5px; border: none; background: transparent;")

    def reload_personas(self) -> None:
        """Charge ou rafraîchit la liste des personas MCP depuis la base de données."""
        from ankidraft.database.models import PersonaModel

        try:
            self._personas_cache: list[Any] = list(PersonaModel.select().order_by(PersonaModel.name.asc()))
        except Exception as exc:
            logger.warning("Impossible de charger les personas MCP : %s", exc)
            self._personas_cache = []


__all__ = ["MCPWorkspaceGuideWidget"]
