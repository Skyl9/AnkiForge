"""Sous-onglet Télémétrie d'Activité en disposition Maître-Détail pour le serveur MCP.

Affiche en temps réel l'ensemble des invocations d'outils MCP effectuées par des agents
externes avec ruban de KPIs, filtrage textuel et par statut, et inspection immédiate
des arguments JSON et des résultats sans boîte de dialogue modale bloquante.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ankiforge.services.ai.mcp_tracker import (
    MCPActivityRecord,
    MCPActivityTracker,
    get_mcp_activity_tracker,
)
from ankiforge.ui.components.badges import StatusBadge
from ankiforge.ui.components.buttons import (
    FilterChipButton,
    PrimaryButton,
    SecondaryButton,
)
from ankiforge.ui.theme import DesignTokens, apply_shadow
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.i18n import tr
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class MCPTelemetryKpiCard(QFrame):
    """Carte individuelle compacte pour un indicateur clé de performance (KPI)."""

    def __init__(
        self,
        title: str,
        initial_value: str,
        icon_name: str,
        color: str = DesignTokens.ACCENT_PRIMARY,
        subtitle: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("mcp_telemetry_kpi_card")
        self.title_text = title
        self.icon_name = icon_name
        self.accent_color = color

        self.setFixedHeight(64)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._setup_ui(initial_value, subtitle)
        self._apply_style()

    def _setup_ui(self, initial_value: str, subtitle: str) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(12)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)

        self.lbl_title = QLabel(self.title_text)
        self.lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: 700; border: none; text-transform: uppercase; letter-spacing: 0.5px;")
        text_layout.addWidget(self.lbl_title)

        val_row = QHBoxLayout()
        val_row.setContentsMargins(0, 0, 0, 0)
        val_row.setSpacing(8)

        self.lbl_val = QLabel(initial_value)
        self.lbl_val.setStyleSheet(f"color: {self.accent_color}; font-size: 17px; font-weight: 700; border: none; font-family: '{DesignTokens.FONT_CODE}';")
        val_row.addWidget(self.lbl_val)

        self.lbl_sub = QLabel(subtitle)
        self.lbl_sub.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; border: none;")
        if not subtitle:
            self.lbl_sub.hide()
        val_row.addWidget(self.lbl_sub)
        val_row.addStretch()

        text_layout.addLayout(val_row)
        layout.addLayout(text_layout, 1)

        self.lbl_icon = QLabel()
        self.lbl_icon.setPixmap(load_phosphor_icon(self.icon_name, color=self.accent_color).pixmap(22, 22))
        self.lbl_icon.setStyleSheet("border: none; background: transparent; opacity: 0.85;")
        layout.addWidget(self.lbl_icon)

        apply_shadow(self, blur=6, offset_y=2)

    def set_value(self, value: str, subtitle: str | None = None) -> None:
        """Met à jour la valeur et le sous-titre de l'indicateur."""
        self.lbl_val.setText(value)
        if subtitle is not None:
            self.lbl_sub.setText(subtitle)
            self.lbl_sub.setVisible(bool(subtitle))

    def _apply_style(self, profile: Any = None) -> None:
        bg_panel = profile.bg_panel if profile else DesignTokens.BG_PANEL
        border_col = profile.border_color if profile else DesignTokens.BORDER_COLOR
        radius_md = profile.radius_md if profile else DesignTokens.RADIUS_MD
        self.setStyleSheet(f"""
            QFrame#mcp_telemetry_kpi_card {{
                background-color: {bg_panel};
                border: 1px solid {border_col};
                border-radius: {radius_md}px;
            }}
        """)

    def refresh_theme(self, profile: Any) -> None:
        """Adapte les styles au profil de thème actif."""
        self._apply_style(profile)
        color = profile.accent_primary if profile else DesignTokens.ACCENT_PRIMARY
        if self.accent_color in (DesignTokens.COLOR_GREEN, DesignTokens.COLOR_RED, DesignTokens.COLOR_BLUE):
            color = self.accent_color
        self.lbl_icon.setPixmap(load_phosphor_icon(self.icon_name, color=color).pixmap(22, 22))


class MCPTelemetryWidget(QWidget):
    """Composant maître-détail de supervision de la télémétrie MCP."""

    count_changed = Signal(int)

    def __init__(
        self,
        tracker: MCPActivityTracker | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("MCPTelemetryWidget")

        self._tracker = tracker if tracker is not None else get_mcp_activity_tracker()
        self._records: dict[str, MCPActivityRecord] = {}
        self._selected_call_id: str | None = None

        self._setup_ui()
        self._connect_signals()
        self._load_initial_history()

    @property
    def lbl_kpi_total_val(self) -> QLabel:
        return self._kpi_total.lbl_val

    @property
    def lbl_kpi_rate_val(self) -> QLabel:
        return self._kpi_rate.lbl_val

    @property
    def lbl_kpi_rate_sub(self) -> QLabel:
        return self._kpi_rate.lbl_sub

    @property
    def lbl_kpi_duration_val(self) -> QLabel:
        return self._kpi_duration.lbl_val

    def _setup_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(*DesignTokens.DESIGN_SYSTEM_MARGES["mcp_root"])
        root_layout.setSpacing(DesignTokens.DESIGN_SYSTEM_SPACING["mcp_root"])

        # ── 1. Ruban supérieur de KPIs ───────────────────────────────────────
        kpi_ribbon = self._setup_kpi_ribbon()
        root_layout.addWidget(kpi_ribbon)

        # ── 2. Splitter horizontal (60% Table / 40% Inspecteur) ──────────────
        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.splitter.setObjectName("mcp_telemetry_splitter")
        self.splitter.setChildrenCollapsible(False)

        # Volet gauche : Table et filtres
        left_pane = self._setup_left_pane()
        self.splitter.addWidget(left_pane)

        # Volet droit : Inspecteur réactif
        right_pane = self._setup_right_pane()
        self.splitter.addWidget(right_pane)

        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setSizes([600, 400])

        root_layout.addWidget(self.splitter, 1)

    def _setup_kpi_ribbon(self) -> QFrame:
        ribbon = QFrame(self)
        ribbon.setObjectName("mcp_telemetry_ribbon_frame")
        ribbon.setStyleSheet("QFrame#mcp_telemetry_ribbon_frame { border: none; background: transparent; }")

        layout = QHBoxLayout(ribbon)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # KPI 1 : Total d'appels
        self._kpi_total = MCPTelemetryKpiCard(
            title=tr("TOTAL DES APPELS"),
            initial_value="0",
            icon_name="ph.terminal-window",
            color=DesignTokens.ACCENT_PRIMARY,
            parent=ribbon,
        )
        layout.addWidget(self._kpi_total, 1)

        # KPI 2 : Taux de succès
        self._kpi_rate = MCPTelemetryKpiCard(
            title=tr("TAUX DE SUCCÈS"),
            initial_value="100%",
            icon_name="ph.check-circle",
            color=DesignTokens.COLOR_GREEN,
            subtitle=self.tr("0 erreur"),
            parent=ribbon,
        )
        layout.addWidget(self._kpi_rate, 1)

        # KPI 3 : Durée moyenne
        self._kpi_duration = MCPTelemetryKpiCard(
            title=tr("DURÉE MOYENNE"),
            initial_value="0 ms",
            icon_name="ph.timer",
            color=DesignTokens.COLOR_BLUE,
            subtitle=self.tr("par appel"),
            parent=ribbon,
        )
        layout.addWidget(self._kpi_duration, 1)

        # Bouton Vider l'historique
        self.btn_clear_history = SecondaryButton(self.tr("Vider l'historique"), parent=ribbon)
        self.btn_clear_history.setIcon(load_phosphor_icon("ph.trash", color=DesignTokens.TEXT_PRIMARY))
        self.btn_clear_history.setFixedHeight(40)
        self.btn_clear_history.clicked.connect(self._on_clear_history_clicked)
        layout.addWidget(self.btn_clear_history, 0, Qt.AlignmentFlag.AlignVCenter)

        return ribbon

    def _setup_left_pane(self) -> QWidget:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(8)

        # Barre de filtres (recherche + chips de statut)
        filter_row = QHBoxLayout()
        filter_row.setContentsMargins(0, 0, 0, 0)
        filter_row.setSpacing(8)

        self.edit_search = QLineEdit(container)
        self.edit_search.setObjectName("mcp_telemetry_search")
        self.edit_search.setPlaceholderText(self.tr("Rechercher un outil ou paramètre..."))
        self.edit_search.setFixedHeight(28)
        self.edit_search.setStyleSheet(f"""
            QLineEdit#mcp_telemetry_search {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_PRIMARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                padding: 0 8px;
                font-size: 12px;
            }}
            QLineEdit#mcp_telemetry_search:focus {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        self.edit_search.textChanged.connect(self._apply_filters)
        filter_row.addWidget(self.edit_search, 1)

        # Puces de statut
        self.chip_all = FilterChipButton(self.tr("Tous"), icon_name="ph.sparkle", parent=container)
        self.chip_success = FilterChipButton(self.tr("Succès"), icon_name="ph.check-circle", parent=container)
        self.chip_error = FilterChipButton(self.tr("Erreurs"), icon_name="ph.warning-circle", parent=container)

        self._status_group = QButtonGroup(container)
        self._status_group.setExclusive(True)
        self._status_group.addButton(self.chip_all)
        self._status_group.addButton(self.chip_success)
        self._status_group.addButton(self.chip_error)
        self.chip_all.setChecked(True)

        self.chip_all.clicked.connect(self._apply_filters)
        self.chip_success.clicked.connect(self._apply_filters)
        self.chip_error.clicked.connect(self._apply_filters)

        filter_row.addWidget(self.chip_all)
        filter_row.addWidget(self.chip_success)
        filter_row.addWidget(self.chip_error)
        layout.addLayout(filter_row)

        # Table des activités
        self.table = QTableWidget(container)
        self.table.setObjectName("mcp_telemetry_table")
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            [
                self.tr("Horodatage"),
                self.tr("Outil"),
                self.tr("Statut"),
                self.tr("Durée"),
                self.tr("Arguments résumés"),
            ]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)

        h_header = self.table.horizontalHeader()
        h_header.setStretchLastSection(True)
        h_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h_header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        h_header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)

        self._apply_table_style()
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.table, 1)

        return container

    def _apply_table_style(self, profile: Any = None) -> None:
        bg_panel = profile.bg_panel if profile else DesignTokens.BG_PANEL
        border_col = profile.border_color if profile else DesignTokens.BORDER_COLOR
        bg_active = profile.bg_active if profile else DesignTokens.BG_ACTIVE
        text_primary = profile.text_primary if profile else DesignTokens.TEXT_PRIMARY
        text_muted = profile.text_muted if profile else DesignTokens.TEXT_MUTED
        radius_md = profile.radius_md if profile else DesignTokens.RADIUS_MD

        self.table.setStyleSheet(f"""
            QTableWidget#mcp_telemetry_table {{
                background-color: {bg_panel};
                border: 1px solid {border_col};
                border-radius: {radius_md}px;
                color: {text_primary};
                gridline-color: transparent;
                selection-background-color: {bg_active};
                selection-color: {text_primary};
                outline: none;
            }}
            QTableWidget#mcp_telemetry_table::item {{
                padding: 6px 8px;
                border-bottom: 1px solid {border_col};
            }}
            QHeaderView::section {{
                background-color: {bg_panel};
                color: {text_muted};
                border: none;
                border-bottom: 1px solid {border_col};
                padding: 6px 8px;
                font-weight: 700;
                font-size: 11px;
                text-transform: uppercase;
                letter-spacing: 0.4px;
            }}
        """)

    def _setup_right_pane(self) -> QWidget:
        container = QFrame(self)
        container.setObjectName("mcp_telemetry_inspector_container")
        container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._apply_inspector_container_style(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.inspector_stack = QStackedWidget(container)

        # Page 0 : État vide
        empty_page = QWidget(self.inspector_stack)
        empty_layout = QVBoxLayout(empty_page)
        empty_layout.setContentsMargins(20, 40, 20, 40)
        empty_layout.setSpacing(12)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        empty_icon = QLabel(empty_page)
        empty_icon.setPixmap(load_phosphor_icon("ph.terminal-window", color=DesignTokens.TEXT_MUTED).pixmap(44, 44))
        empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_icon.setStyleSheet("border: none; background: transparent; opacity: 0.6;")
        empty_layout.addWidget(empty_icon)

        empty_title = QLabel(self.tr("Aucun appel sélectionné"), empty_page)
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 14px; font-weight: 700; border: none;")
        empty_layout.addWidget(empty_title)

        empty_desc = QLabel(
            self.tr("Sélectionnez une ligne dans la table d'activité pour inspecter ses paramètres JSON et son résultat en temps réel sans popup bloquante."),
            empty_page,
        )
        empty_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_desc.setWordWrap(True)
        empty_desc.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11.5px; border: none; max-width: 280px;")
        empty_layout.addWidget(empty_desc)
        empty_layout.addStretch()

        self.inspector_stack.addWidget(empty_page)

        # Page 1 : Vue d'inspection réactive
        detail_page = QWidget(self.inspector_stack)
        detail_layout = QVBoxLayout(detail_page)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(10)

        # En-tête inspecteur
        inspect_header = QHBoxLayout()
        inspect_header.setSpacing(8)

        self.lbl_inspect_tool = QLabel(detail_page)
        self.lbl_inspect_tool.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 14px; font-weight: 700; border: none; font-family: '{DesignTokens.FONT_CODE}';")
        inspect_header.addWidget(self.lbl_inspect_tool, 1)

        self.badge_inspect_status = StatusBadge(self.tr("Succès"), "ph.check-circle", variant="success", parent=detail_page)
        inspect_header.addWidget(self.badge_inspect_status)

        self.btn_copy_json = PrimaryButton(self.tr("Copier le JSON"), parent=detail_page)
        self.btn_copy_json.setIcon(load_phosphor_icon("ph.copy", color=DesignTokens.TEXT_ON_ACCENT))
        self.btn_copy_json.setFixedHeight(30)
        self.btn_copy_json.clicked.connect(self._copy_current_json)
        inspect_header.addWidget(self.btn_copy_json)

        detail_layout.addLayout(inspect_header)

        # Métadonnées
        self.lbl_inspect_meta = QLabel(detail_page)
        self.lbl_inspect_meta.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; border: none;")
        detail_layout.addWidget(self.lbl_inspect_meta)

        # Paramètres d'appel
        lbl_args_title = QLabel(self.tr("Paramètres d'appel (Arguments JSON) :"), detail_page)
        lbl_args_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11.5px; font-weight: 600; border: none;")
        detail_layout.addWidget(lbl_args_title)

        self.edit_inspect_args = QPlainTextEdit(detail_page)
        self.edit_inspect_args.setObjectName("mcp_inspect_edit_args")
        self.edit_inspect_args.setReadOnly(True)
        self.edit_inspect_args.setMaximumHeight(140)
        self.edit_inspect_args.setStyleSheet(self._input_code_style())
        detail_layout.addWidget(self.edit_inspect_args)

        # Observation / Résultat retourné
        self.lbl_inspect_result_title = QLabel(self.tr("Observation / Résultat retourné :"), detail_page)
        self.lbl_inspect_result_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11.5px; font-weight: 600; border: none;")
        detail_layout.addWidget(self.lbl_inspect_result_title)

        self.edit_inspect_result = QPlainTextEdit(detail_page)
        self.edit_inspect_result.setObjectName("mcp_inspect_edit_result")
        self.edit_inspect_result.setReadOnly(True)
        self.edit_inspect_result.setStyleSheet(self._input_code_style())
        detail_layout.addWidget(self.edit_inspect_result, 1)

        self.inspector_stack.addWidget(detail_page)
        layout.addWidget(self.inspector_stack)

        return container

    def _apply_inspector_container_style(self, frame: QFrame, profile: Any = None) -> None:
        bg_panel = profile.bg_panel if profile else DesignTokens.BG_PANEL
        border_col = profile.border_color if profile else DesignTokens.BORDER_COLOR
        radius_md = profile.radius_md if profile else DesignTokens.RADIUS_MD
        frame.setStyleSheet(f"""
            QFrame#mcp_telemetry_inspector_container {{
                background-color: {bg_panel};
                border: 1px solid {border_col};
                border-radius: {radius_md}px;
            }}
        """)

    def _input_code_style(self, is_error: bool = False, profile: Any = None) -> str:
        bg_input = profile.bg_input if profile else DesignTokens.BG_INPUT
        border_col = profile.border_color if profile else DesignTokens.BORDER_COLOR
        fg_col = (profile.color_red if profile else DesignTokens.COLOR_RED) if is_error else (profile.text_primary if profile else DesignTokens.TEXT_PRIMARY)
        return f"""
            QPlainTextEdit {{
                background-color: {bg_input};
                color: {fg_col};
                border: 1px solid {border_col};
                border-radius: 6px;
                font-family: {DesignTokens.FONT_CODE};
                font-size: 11px;
                padding: 8px;
            }}
        """

    def _connect_signals(self) -> None:
        """Connecte les signaux Qt émis par le tracker d'activité."""
        self._tracker.signals.activity_started.connect(self._on_activity_started)
        self._tracker.signals.activity_updated.connect(self._on_activity_updated)
        self._tracker.signals.history_cleared.connect(self._on_history_cleared)

    def _load_initial_history(self) -> None:
        """Peuple la table et les KPIs avec l'historique pré-existant du tracker."""
        history = self._tracker.get_history()
        for record in history:
            self._records[record.call_id] = record
            self._insert_table_row(record, prepend=False)
        self._update_kpis()
        self.count_changed.emit(len(self._records))

    def _find_row_by_call_id(self, call_id: str) -> int | None:
        """Retrouve l'indice de ligne correspondant à un identifiant d'appel."""
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it is not None and it.data(Qt.ItemDataRole.UserRole) == call_id:
                return r
        return None

    def _create_status_cell(self, status: str) -> QWidget:
        """Construit le widget conteneur centré pour le badge de statut de table."""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        if status == "success":
            badge = StatusBadge(self.tr("Succès"), "ph.check-circle", variant="success", parent=container)
        elif status == "error":
            badge = StatusBadge(self.tr("Erreur"), "ph.warning-circle", variant="danger", parent=container)
        else:
            badge = StatusBadge(self.tr("En cours"), "ph.hourglass-simple", variant="warning", parent=container)

        layout.addWidget(badge)
        return container

    def _insert_table_row(self, record: MCPActivityRecord, prepend: bool = True) -> int:
        """Insère une nouvelle ligne dans la table représentant l'appel."""
        row_idx = 0 if prepend else self.table.rowCount()
        self.table.insertRow(row_idx)

        # 0. Horodatage
        time_str = record.started_at.strftime("%H:%M:%S")
        item_time = QTableWidgetItem(time_str)
        item_time.setData(Qt.ItemDataRole.UserRole, record.call_id)
        item_time.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.table.setItem(row_idx, 0, item_time)

        # 1. Outil
        item_tool = QTableWidgetItem(record.tool_name)
        item_tool.setFont(QFont(DesignTokens.FONT_CODE, 11))
        item_tool.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.table.setItem(row_idx, 1, item_tool)

        # 2. Statut
        self.table.setCellWidget(row_idx, 2, self._create_status_cell(record.status))

        # 3. Durée
        if record.status != "running":
            dur = record.duration_ms
            dur_str = tr("%1 ms", dur) if dur < 1000 else tr("%1 s", round(dur / 1000, 2))
        else:
            dur_str = "..."
        item_dur = QTableWidgetItem(dur_str)
        item_dur.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
        self.table.setItem(row_idx, 3, item_dur)

        # 4. Arguments résumés
        item_args = QTableWidgetItem(record.args_summary)
        item_args.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.table.setItem(row_idx, 4, item_args)

        return row_idx

    def _update_table_row(self, row_idx: int, record: MCPActivityRecord) -> None:
        """Met à jour une ligne existante lors de la complétion d'un appel."""
        self.table.setCellWidget(row_idx, 2, self._create_status_cell(record.status))

        dur = record.duration_ms
        dur_str = tr("%1 ms", dur) if dur < 1000 else tr("%1 s", round(dur / 1000, 2))
        item_dur = self.table.item(row_idx, 3)
        if item_dur:
            item_dur.setText(dur_str)

        item_args = self.table.item(row_idx, 4)
        if item_args:
            item_args.setText(record.args_summary)

    def _on_activity_started(self, data: dict[str, Any]) -> None:
        call_id = str(data.get("call_id", ""))
        record = self._tracker.get_record(call_id)
        if not record:
            return

        self._records[call_id] = record
        self._insert_table_row(record, prepend=True)
        self._apply_filters()
        self._update_kpis()
        self.count_changed.emit(len(self._records))

    def _on_activity_updated(self, data: dict[str, Any]) -> None:
        call_id = str(data.get("call_id", ""))
        record = self._tracker.get_record(call_id)
        if not record:
            return

        self._records[call_id] = record
        row_idx = self._find_row_by_call_id(call_id)
        if row_idx is not None:
            self._update_table_row(row_idx, record)

        self._apply_filters()
        self._update_kpis()

        # Si l'appel actuellement examiné dans l'inspecteur a été mis à jour, rafraîchir en temps réel
        if self._selected_call_id == call_id:
            self._display_record_details(record)

    def _on_history_cleared(self) -> None:
        self._records.clear()
        self._selected_call_id = None
        self.table.setRowCount(0)
        self.inspector_stack.setCurrentIndex(0)
        self._update_kpis()
        self.count_changed.emit(0)

    def _on_clear_history_clicked(self) -> None:
        self._tracker.clear_history()
        show_toast(self, self.tr("Historique de télémétrie réinitialisé."))

    def _update_kpis(self) -> None:
        total = len(self._records)
        self._kpi_total.set_value(str(total))

        if total == 0:
            self._kpi_rate.set_value("100%", self.tr("0 erreur"))
            self._kpi_duration.set_value("0 ms", self.tr("par appel"))
            return

        completed = [r for r in self._records.values() if r.status != "running"]
        success_count = sum(1 for r in self._records.values() if r.status == "success")
        error_count = sum(1 for r in self._records.values() if r.status == "error")

        if completed:
            rate = round((success_count / len(completed)) * 100, 1)
            rate_val_str = f"{int(rate)}%" if rate.is_integer() else f"{rate}%"
            avg_dur = round(sum(r.duration_ms for r in completed) / len(completed), 1)
            dur_str = f"{avg_dur} ms" if avg_dur < 1000 else f"{round(avg_dur / 1000, 2)} s"
        else:
            rate_val_str = "100%"
            dur_str = "0 ms"

        err_sub = tr("%1 erreur", error_count) if error_count <= 1 else tr("%1 erreurs", error_count)
        self._kpi_rate.set_value(rate_val_str, err_sub)
        self._kpi_duration.set_value(dur_str, self.tr("par appel"))

    def _on_selection_changed(self) -> None:
        selected_ranges = self.table.selectedRanges()
        if not selected_ranges:
            self._selected_call_id = None
            self.inspector_stack.setCurrentIndex(0)
            return

        row = selected_ranges[0].topRow()
        item_time = self.table.item(row, 0)
        if item_time is None:
            self.inspector_stack.setCurrentIndex(0)
            return

        call_id = str(item_time.data(Qt.ItemDataRole.UserRole))
        record = self._records.get(call_id)
        if record is None:
            record = self._tracker.get_record(call_id)

        if record:
            self._selected_call_id = call_id
            self._display_record_details(record)
            self.inspector_stack.setCurrentIndex(1)
        else:
            self.inspector_stack.setCurrentIndex(0)

    def _display_record_details(self, record: MCPActivityRecord) -> None:
        self.lbl_inspect_tool.setText(record.tool_name)

        if record.status == "success":
            self.badge_inspect_status.set_status(self.tr("Succès"), "ph.check-circle", variant="success")
        elif record.status == "error":
            self.badge_inspect_status.set_status(self.tr("Erreur"), "ph.warning-circle", variant="danger")
        else:
            self.badge_inspect_status.set_status(self.tr("En cours"), "ph.hourglass-simple", variant="warning")

        time_str = record.started_at.strftime("%H:%M:%S")
        dur = record.duration_ms
        dur_str = tr("%1 ms", dur) if dur < 1000 else tr("%1 s", round(dur / 1000, 2))

        if record.status == "running":
            self.lbl_inspect_meta.setText(tr("Déclenché à %1 · En cours d'exécution...", time_str))
        else:
            self.lbl_inspect_meta.setText(tr("Déclenché à %1 · Durée : %2", time_str, dur_str))

        args_json = json.dumps(record.args_full, indent=2, ensure_ascii=False) if record.args_full else "{}"
        self.edit_inspect_args.setPlainText(args_json)

        if record.status == "error":
            self.lbl_inspect_result_title.setText(self.tr("Message d'erreur :"))
            self.edit_inspect_result.setPlainText(record.error_message or record.result_full or self.tr("(aucun message d'erreur)"))
            self.edit_inspect_result.setStyleSheet(self._input_code_style(is_error=True))
        else:
            self.lbl_inspect_result_title.setText(self.tr("Observation / Résultat retourné :"))
            self.edit_inspect_result.setPlainText(record.result_full or self.tr("(aucun contenu retourné)"))
            self.edit_inspect_result.setStyleSheet(self._input_code_style(is_error=False))

    def _copy_current_json(self) -> None:
        if not self._selected_call_id:
            return
        record = self._records.get(self._selected_call_id)
        if not record:
            record = self._tracker.get_record(self._selected_call_id)
        if not record:
            return

        data = record.to_dict()
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(json.dumps(data, indent=2, ensure_ascii=False))
            show_toast(self, self.tr("Détail de l'appel copié dans le presse-papiers."))

    def _apply_filters(self) -> None:
        filter_status = "all"
        if self.chip_success.isChecked():
            filter_status = "success"
        elif self.chip_error.isChecked():
            filter_status = "error"

        search_text = self.edit_search.text().strip().lower()

        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it is None:
                continue
            call_id = str(it.data(Qt.ItemDataRole.UserRole))
            record = self._records.get(call_id)
            if record is None:
                continue

            match_status = (filter_status == "all") or (record.status == filter_status)
            match_search = not search_text or (search_text in record.tool_name.lower()) or (search_text in record.args_summary.lower())
            self.table.setRowHidden(r, not (match_status and match_search))

    def refresh_theme(self, profile: Any) -> None:
        """Adapte les composants internes au profil de thème actif."""
        self._kpi_total.refresh_theme(profile)
        self._kpi_rate.refresh_theme(profile)
        self._kpi_duration.refresh_theme(profile)
        self._apply_table_style(profile)

        # Conteneur inspecteur
        inspector_container = self.findChild(QFrame, "mcp_telemetry_inspector_container")
        if inspector_container:
            self._apply_inspector_container_style(inspector_container, profile)

        # Inspecteur badges et champs
        if hasattr(self, "badge_inspect_status"):
            self.badge_inspect_status.refresh_theme(profile)

        is_err = False
        if self._selected_call_id:
            record = self._records.get(self._selected_call_id)
            if record and record.status == "error":
                is_err = True

        self.edit_inspect_args.setStyleSheet(self._input_code_style(is_error=False, profile=profile))
        self.edit_inspect_result.setStyleSheet(self._input_code_style(is_error=is_err, profile=profile))


__all__ = ["MCPTelemetryWidget", "MCPTelemetryKpiCard"]
