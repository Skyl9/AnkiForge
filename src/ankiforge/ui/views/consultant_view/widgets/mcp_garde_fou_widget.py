"""Sous-onglet Garde-Fou & Validation en disposition Maître-Détail pour le serveur MCP.

Présente les propositions d'agents externes dans un volet maître filtrable à gauche,
et le comparateur sémantique de cartes champ par champ dans la zone de détail à droite.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import StagedPatchModel
from ankiforge.services.ai.staged_patch_registry import (
    StagedPatchRegistry,
    staged_payload_of,
)
from ankiforge.ui.components import (
    Badge,
    PrimaryButton,
    SecondaryButton,
)
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.card_semantic_diff_widget import CardSemanticDiffWidget
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.i18n import tr
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class PatchListItemWidget(QWidget):
    """Carte graphique représentant une proposition dans la liste maître du volet gauche."""

    def __init__(self, patch: StagedPatchModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.patch_id = patch.patch_id
        self.patch_type = patch.patch_type
        self.target_id = patch.target_id
        payload = staged_payload_of(patch)
        self.title = str(payload.get("title") or f"Proposition — {self.patch_type} #{self.target_id}")

        self._setup_ui(patch)

    def _setup_ui(self, patch: StagedPatchModel) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # Ligne 1 : Titre + Badge de type
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(6)

        lbl_title = QLabel(self.title)
        lbl_title.setStyleSheet(f"""
            font-size: 11px;
            font-weight: 600;
            color: {DesignTokens.TEXT_PRIMARY};
            border: none;
            background: transparent;
        """)
        top_row.addWidget(lbl_title, 1)

        type_variant = "accent" if self.patch_type in ("card", "note_update") else "warning"
        type_badge = Badge(self.patch_type.upper(), variant=type_variant)
        top_row.addWidget(type_badge)
        layout.addLayout(top_row)

        # Ligne 2 : Identifiant et date
        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(0, 0, 0, 0)
        bottom_row.setSpacing(6)

        id_str = f"#{self.target_id} · {self.patch_id[:12]}" if self.target_id else self.patch_id[:12]
        lbl_meta = QLabel(id_str)
        lbl_meta.setStyleSheet(f"""
            font-size: 10px;
            color: {DesignTokens.TEXT_MUTED};
            font-family: {DesignTokens.FONT_CODE};
            border: none;
            background: transparent;
        """)
        bottom_row.addWidget(lbl_meta)
        bottom_row.addStretch()

        created_str = patch.created_at.strftime("%H:%M:%S") if patch.created_at else ""
        if created_str:
            lbl_time = QLabel(created_str)
            lbl_time.setStyleSheet(f"""
                font-size: 10px;
                color: {DesignTokens.TEXT_MUTED};
                border: none;
                background: transparent;
            """)
            bottom_row.addWidget(lbl_time)

        layout.addLayout(bottom_row)


class MCPGardeFouWidget(QWidget):
    """Panneau de supervision et de validation des propositions de patchs MCP en disposition Maître-Détail."""

    patch_applied = Signal(str)
    patch_rejected = Signal(str)
    queue_updated = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._patches: list[StagedPatchModel] = []
        self._current_patch: StagedPatchModel | None = None

        self._setup_ui()
        self.reload_pending_patches()

    @property
    def current_patch_id(self) -> str | None:
        """Identifiant du patch actuellement affiché dans la zone de détail."""
        return self._current_patch.patch_id if self._current_patch else None

    def count(self) -> int:
        """Nombre total de patchs en attente dans la file du garde-fou."""
        return len(self._patches)

    def _setup_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # ── 1. VOLET MAÎTRE (Gauche : 320px) ─────────────────────────────────
        self.left_panel = QFrame()
        self.left_panel.setObjectName("mcp_gf_master")
        self.left_panel.setMinimumWidth(280)
        self.left_panel.setMaximumWidth(400)
        self.left_panel.setStyleSheet(f"""
            QFrame#mcp_gf_master {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(10, 10, 10, 10)
        left_layout.setSpacing(8)

        # En-tête de la liste
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        lbl_title = QLabel(tr("PROPOSITIONS EN ATTENTE"))
        lbl_title.setStyleSheet(f"""
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 0.5px;
            color: {DesignTokens.TEXT_MUTED};
        """)
        header_row.addWidget(lbl_title)
        header_row.addStretch()

        self.badge_count = Badge("0", variant="danger")
        header_row.addWidget(self.badge_count)
        left_layout.addLayout(header_row)

        # Barre de recherche / filtrage
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(tr("Filtrer les propositions..."))
        self.search_input.setFixedHeight(26)
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 11px;
                padding: 0 8px;
            }}
            QLineEdit:focus {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        self.search_input.textChanged.connect(self._filter_list)
        left_layout.addWidget(self.search_input)

        # Boutons de lot
        batch_row = QHBoxLayout()
        batch_row.setContentsMargins(0, 0, 0, 0)
        batch_row.setSpacing(6)

        self.btn_apply_all = SecondaryButton(tr("Tout appliquer"))
        self.btn_apply_all.setIcon(load_phosphor_icon("ph.checks", color=DesignTokens.TEXT_SECONDARY))
        self.btn_apply_all.setFixedHeight(24)
        self.btn_apply_all.clicked.connect(self._apply_all_patches)
        batch_row.addWidget(self.btn_apply_all)

        self.btn_reject_all = SecondaryButton(tr("Tout rejeter"))
        self.btn_reject_all.setIcon(load_phosphor_icon("ph.x", color=DesignTokens.TEXT_SECONDARY))
        self.btn_reject_all.setFixedHeight(24)
        self.btn_reject_all.clicked.connect(self._reject_all_patches)
        batch_row.addWidget(self.btn_reject_all)

        left_layout.addLayout(batch_row)

        # Liste des propositions
        self.patch_list = QListWidget()
        self.patch_list.setFrameShape(QFrame.Shape.NoFrame)
        self.patch_list.setStyleSheet(f"""
            QListWidget {{
                background-color: transparent;
                border: none;
            }}
            QListWidget::item {{
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                background-color: {DesignTokens.BG_INPUT};
                margin-bottom: 6px;
                padding: 2px;
            }}
            QListWidget::item:selected {{
                background-color: {DesignTokens.BG_ACTIVE};
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
            QListWidget::item:hover:!selected {{
                background-color: {DesignTokens.BG_HOVER};
            }}
        """)
        self.patch_list.currentItemChanged.connect(self._on_item_selection_changed)
        left_layout.addWidget(self.patch_list, 1)

        splitter.addWidget(self.left_panel)

        # ── 2. ZONE DÉTAIL (Droite) ──────────────────────────────────────────
        self.right_container = QFrame()
        self.right_container.setObjectName("mcp_gf_detail")
        self.right_container.setStyleSheet(f"""
            QFrame#mcp_gf_detail {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        right_layout = QVBoxLayout(self.right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.detail_stack = QStackedWidget()

        # Index 0 : Vue Vide
        self.empty_view = QWidget()
        empty_layout = QVBoxLayout(self.empty_view)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.setSpacing(12)

        icon_empty = QLabel()
        icon_empty.setPixmap(load_phosphor_icon("ph.shield-check", color=DesignTokens.TEXT_MUTED).pixmap(56, 56))
        icon_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(icon_empty)

        lbl_empty_title = QLabel(tr("Aucune proposition en attente"))
        lbl_empty_title.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        lbl_empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(lbl_empty_title)

        lbl_empty_sub = QLabel(tr("Toutes les propositions d'agents MCP ont été validées ou rejetées."))
        lbl_empty_sub.setStyleSheet(f"font-size: 12px; color: {DesignTokens.TEXT_MUTED};")
        lbl_empty_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(lbl_empty_sub)

        self.detail_stack.addWidget(self.empty_view)

        # Index 1 : Vue Détail avec CardSemanticDiffWidget
        self.detail_view = QWidget()
        detail_view_layout = QVBoxLayout(self.detail_view)
        detail_view_layout.setContentsMargins(12, 12, 12, 12)
        detail_view_layout.setSpacing(10)

        # Barre supérieure de détail (Titre + Bouton Copier Feedback)
        detail_header = QHBoxLayout()
        detail_header.setContentsMargins(0, 0, 0, 0)
        detail_header.setSpacing(10)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)

        self.lbl_detail_title = QLabel()
        self.lbl_detail_title.setStyleSheet(f"""
            font-size: 14px;
            font-weight: 700;
            color: {DesignTokens.TEXT_PRIMARY};
        """)
        title_col.addWidget(self.lbl_detail_title)

        self.lbl_detail_meta = QLabel()
        self.lbl_detail_meta.setStyleSheet(f"""
            font-size: 11px;
            color: {DesignTokens.TEXT_MUTED};
            font-family: {DesignTokens.FONT_CODE};
        """)
        title_col.addWidget(self.lbl_detail_meta)
        detail_header.addLayout(title_col, 1)

        self.btn_copy_feedback = SecondaryButton(tr("Copier le feedback"))
        self.btn_copy_feedback.setIcon(load_phosphor_icon("ph.copy", color=DesignTokens.TEXT_SECONDARY))
        self.btn_copy_feedback.setFixedHeight(28)
        self.btn_copy_feedback.setToolTip(tr("Copie une synthèse pour le terminal CLI de l'agent externe"))
        self.btn_copy_feedback.clicked.connect(self._copy_feedback)
        detail_header.addWidget(self.btn_copy_feedback)

        detail_view_layout.addLayout(detail_header)

        # Visualiseur Comparatif Sémantique
        self.diff_viewer = CardSemanticDiffWidget()
        detail_view_layout.addWidget(self.diff_viewer, 1)

        # Barre d'actions inférieure
        action_bar = QHBoxLayout()
        action_bar.setContentsMargins(0, 0, 0, 0)
        action_bar.setSpacing(10)

        self.btn_reject = SecondaryButton(tr("Rejeter la proposition"))
        self.btn_reject.setIcon(load_phosphor_icon("ph.x", color=DesignTokens.COLOR_RED))
        self.btn_reject.setFixedHeight(32)
        self.btn_reject.setStyleSheet(f"""
            QPushButton {{
                background-color: {DesignTokens.COLOR_RED_BG};
                color: {DesignTokens.COLOR_RED};
                border: 1px solid {DesignTokens.COLOR_RED};
                border-radius: 4px;
                font-weight: 600;
                padding: 0 14px;
            }}
            QPushButton:hover {{
                background-color: {DesignTokens.COLOR_RED};
                color: white;
            }}
        """)
        self.btn_reject.clicked.connect(self._reject_current_patch)
        action_bar.addWidget(self.btn_reject)

        action_bar.addStretch()

        from ankiforge.utils.icon_loader import load_on_accent_icon

        self.btn_apply = PrimaryButton(tr("Appliquer la modification"))
        self.btn_apply.setIcon(load_on_accent_icon("ph.check"))
        self.btn_apply.setFixedHeight(32)
        self.btn_apply.clicked.connect(self._apply_current_patch)
        action_bar.addWidget(self.btn_apply)

        detail_view_layout.addLayout(action_bar)
        self.detail_stack.addWidget(self.detail_view)

        right_layout.addWidget(self.detail_stack)
        splitter.addWidget(self.right_container)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        main_layout.addWidget(splitter)

    def reload_pending_patches(self) -> None:
        """Recharge l'intégralité des propositions 'pending' depuis la base SQLite."""
        self._patches = list(StagedPatchRegistry.list_pending())
        self.badge_count.setText(str(len(self._patches)))
        self.badge_count.set_variant("danger" if self._patches else "neutral")

        # Sauvegarde de la sélection active si existante
        prev_patch_id = self.current_patch_id

        self.patch_list.blockSignals(True)
        self.patch_list.clear()

        selected_item: QListWidgetItem | None = None
        for patch in self._patches:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, patch.patch_id)
            item_widget = PatchListItemWidget(patch)
            item.setSizeHint(item_widget.sizeHint())

            self.patch_list.addItem(item)
            self.patch_list.setItemWidget(item, item_widget)

            if prev_patch_id and patch.patch_id == prev_patch_id:
                selected_item = item

        self.patch_list.blockSignals(False)

        if not self._patches:
            self._current_patch = None
            self.detail_stack.setCurrentIndex(0)
            self.btn_apply_all.setEnabled(False)
            self.btn_reject_all.setEnabled(False)
        else:
            self.btn_apply_all.setEnabled(True)
            self.btn_reject_all.setEnabled(True)
            if selected_item is not None:
                self.patch_list.setCurrentItem(selected_item)
            else:
                self.patch_list.setCurrentRow(0)

        self.queue_updated.emit(len(self._patches))

    def _on_item_selection_changed(self, current: QListWidgetItem | None, _prev: QListWidgetItem | None) -> None:
        if not current:
            self._current_patch = None
            self.detail_stack.setCurrentIndex(0)
            return

        patch_id = current.data(Qt.ItemDataRole.UserRole)
        match = next((p for p in self._patches if p.patch_id == patch_id), None)
        if not match:
            self.detail_stack.setCurrentIndex(0)
            return

        self._current_patch = match
        self.detail_stack.setCurrentIndex(1)
        self._display_patch(match)

    def _display_patch(self, patch: StagedPatchModel) -> None:
        """Injecte les données d'un patch dans la vue de détail."""
        payload = staged_payload_of(patch)
        title = str(payload.get("title") or f"Proposition — {patch.patch_type} #{patch.target_id}")
        self.lbl_detail_title.setText(title)

        meta_str = f"ID: {patch.patch_id} · Type: {patch.patch_type.upper()}"
        if patch.target_id:
            meta_str += f" · Note ciblée: #{patch.target_id}"
        self.lbl_detail_meta.setText(meta_str)

        self.diff_viewer.set_patch(patch)

    def _filter_list(self, text: str) -> None:
        """Filtre les cartes de la liste maître par texte."""
        query = text.strip().lower()
        for i in range(self.patch_list.count()):
            item = self.patch_list.item(i)
            widget = self.patch_list.itemWidget(item)
            if isinstance(widget, PatchListItemWidget):
                matched = not query or query in widget.title.lower() or query in widget.patch_id.lower() or str(widget.target_id) in query
                item.setHidden(not matched)

    def _apply_current_patch(self) -> None:
        """Applique la proposition courante avec les retouches éventuelles."""
        if not self._current_patch:
            return

        patch_id = self._current_patch.patch_id
        # 1. Synchronisation de l'édition directe
        edited_content = self.diff_viewer.get_modified_content()
        StagedPatchRegistry.sync_direct_edit(patch_id, edited_content)

        # 2. Application transactionnelle
        res = StagedPatchRegistry.apply_staged_patch(patch_id)
        if res.get("status") == "applied":
            show_toast(self, tr("Patch %1 appliqué avec succès !", patch_id), level="success")
            self.patch_applied.emit(patch_id)
            self.reload_pending_patches()
        else:
            err_msg = res.get("message") or tr("Échec lors de l'application du patch.")
            show_toast(self, err_msg, level="error")

    def _reject_current_patch(self) -> None:
        """Rejette la proposition courante."""
        if not self._current_patch:
            return

        patch_id = self._current_patch.patch_id
        res = StagedPatchRegistry.reject_staged_patch(patch_id, reason="Rejeté via IHM Garde-Fou")
        if res.get("status") == "rejected":
            show_toast(self, tr("Patch %1 rejeté.", patch_id), level="info")
            self.patch_rejected.emit(patch_id)
            self.reload_pending_patches()

    def _apply_all_patches(self) -> None:
        """Applique l'ensemble des patchs en attente."""
        if not self._patches:
            return

        applied_count = 0
        for patch in list(self._patches):
            res = StagedPatchRegistry.apply_staged_patch(patch.patch_id)
            if res.get("status") == "applied":
                applied_count += 1
                self.patch_applied.emit(patch.patch_id)

        show_toast(self, tr("%1 proposition(s) appliquée(s).", applied_count), level="success")
        self.reload_pending_patches()

    def _reject_all_patches(self) -> None:
        """Rejette l'ensemble des patchs en attente."""
        if not self._patches:
            return

        count = len(self._patches)
        for patch in list(self._patches):
            StagedPatchRegistry.reject_staged_patch(patch.patch_id, reason="Rejet groupé via IHM")
            self.patch_rejected.emit(patch.patch_id)

        show_toast(self, tr("%1 proposition(s) rejetée(s).", count), level="info")
        self.reload_pending_patches()

    def _copy_feedback(self) -> None:
        """Copie une synthèse d'arbitrage dans le presse-papier pour le terminal de l'agent."""
        if not self._current_patch:
            return

        p = self._current_patch
        payload = staged_payload_of(p)
        feedback_lines = [
            "[Garde-Fou AnkiForge] Feedback pour l'agent MCP :",
            f"- Patch ID : {p.patch_id}",
            f"- Cible : Note #{p.target_id} (Type: {p.patch_type})",
            f"- Titre : {payload.get('title', '')}",
            "- Statut d'arbitrage : Validé avec retouches / En attente de révision",
            "- Directives complémentaires : Merci d'affiner la concision selon les 20 règles de Wozniak.",
        ]
        text = "\n".join(feedback_lines)
        QGuiApplication.clipboard().setText(text)
        show_toast(self, tr("Synthèse de feedback copiée dans le presse-papier"), level="success")

    def refresh_theme(self, profile: Any) -> None:
        """Adapte les styles au profil de thème actif."""
        bg_panel = getattr(profile, "bg_panel", DesignTokens.BG_PANEL)
        border_color = getattr(profile, "border_color", DesignTokens.BORDER_COLOR)

        if hasattr(self, "left_panel"):
            self.left_panel.setStyleSheet(f"""
                QFrame#mcp_gf_master {{
                    background-color: {bg_panel};
                    border: 1px solid {border_color};
                    border-radius: {DesignTokens.RADIUS_SM}px;
                }}
            """)
        if hasattr(self, "right_container"):
            self.right_container.setStyleSheet(f"""
                QFrame#mcp_gf_detail {{
                    background-color: {bg_panel};
                    border: 1px solid {border_color};
                    border-radius: {DesignTokens.RADIUS_SM}px;
                }}
            """)
        if hasattr(self, "diff_viewer") and hasattr(self.diff_viewer, "refresh_theme"):
            self.diff_viewer.refresh_theme(profile)

    def cleanup(self) -> None:
        """Arrête les chargements Chromium et libère les ressources WebEngine."""
        if hasattr(self, "diff_viewer") and hasattr(self.diff_viewer, "cleanup"):
            self.diff_viewer.cleanup()
