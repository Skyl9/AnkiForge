"""Sous-onglet Garde-Fou & Validation en disposition Maître-Détail pour le serveur MCP.

Présente les propositions d'agents externes dans un volet maître hiérarchique à gauche
(bundles regroupés avec sous-étapes et patchs autonomes), et une zone de détail polymorphe
à droite (diff sémantique, arborescence de paquets, tags et avertissement de suppression)
avec barre d'action séquentielle pas-à-pas et arrêt en cascade.
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
    QSplitter,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import StagedBundleModel, StagedPatchModel
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
from ankiforge.ui.views.consultant_view.widgets.garde_fou_views import (
    DeckOperationWidget,
    DeletionImpactWidget,
    TagDiffWidget,
)
from ankiforge.ui.widgets.card_semantic_diff_widget import CardSemanticDiffWidget
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.i18n import tr
from ankiforge.utils.icon_loader import load_on_accent_icon, load_phosphor_icon

logger = logging.getLogger(__name__)


class BundleHeaderItemWidget(QWidget):
    """En-tête graphique pour un Staged Bundle dans l'arborescence maître."""

    def __init__(self, bundle: StagedBundleModel, pending_count: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.bundle_id = bundle.bundle_id
        self._setup_ui(bundle, pending_count)

    def _setup_ui(self, bundle: StagedBundleModel, pending_count: int) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(6)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(load_phosphor_icon("ph.stack", color=DesignTokens.ACCENT_PRIMARY).pixmap(16, 16))
        top_row.addWidget(icon_lbl)

        lbl_title = QLabel(bundle.title or tr("Bloc d'opérations"))
        lbl_title.setStyleSheet(f"""
            font-size: 11px;
            font-weight: 700;
            color: {DesignTokens.TEXT_PRIMARY};
            border: none;
            background: transparent;
        """)
        top_row.addWidget(lbl_title, 1)

        badge_text = tr("%1 étapes", bundle.total_steps)
        badge_variant = "accent"
        if bundle.current_step > 1:
            badge_text = tr("Étape %1/%2", bundle.current_step, bundle.total_steps)
            badge_variant = "warning"
        top_row.addWidget(Badge(badge_text, variant=badge_variant))
        layout.addLayout(top_row)

        if bundle.explanation:
            lbl_desc = QLabel(bundle.explanation)
            lbl_desc.setStyleSheet(f"""
                font-size: 10px;
                color: {DesignTokens.TEXT_MUTED};
                border: none;
                background: transparent;
            """)
            lbl_desc.setWordWrap(True)
            layout.addWidget(lbl_desc)


class PatchListItemWidget(QWidget):
    """Carte graphique représentant une proposition (autonome ou étape de bundle) dans l'arbre maître."""

    def __init__(self, patch: StagedPatchModel, parent: QWidget | None = None, is_step: bool = False) -> None:
        super().__init__(parent)
        self.patch_id = patch.patch_id
        self.patch_type = patch.patch_type
        self.target_id = patch.target_id
        self.is_step = is_step
        payload = staged_payload_of(patch)

        if is_step:
            self.title = str(payload.get("title") or tr("Étape %1 — %2", patch.step_order, self.patch_type))
        else:
            self.title = str(payload.get("title") or tr("Proposition — %1 #%2", self.patch_type, self.target_id))

        self._setup_ui(patch)

    def _setup_ui(self, patch: StagedPatchModel) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(3)

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

        p_type = self.patch_type.lower()
        if p_type in ("card", "note_update", "note_create"):
            type_variant = "accent"
            type_label = tr("CARTE")
        elif p_type in ("deck_create", "deck_rename", "create_deck"):
            type_variant = "warning"
            type_label = tr("PAQUET")
        elif p_type in ("set_tags", "set_tags_bulk", "tag_add", "tag_remove"):
            type_variant = "success"
            type_label = tr("TAGS")
        elif p_type in ("card_delete", "deck_delete", "delete_empty_cards", "empty_cards_delete", "note_delete", "batch_card_deletion", "batch_note_delete"):
            type_variant = "danger"
            type_label = tr("SUPPR")
        else:
            type_variant = "neutral"
            type_label = self.patch_type.upper()

        type_badge = Badge(type_label, variant=type_variant)
        top_row.addWidget(type_badge)
        layout.addLayout(top_row)

        # Ligne 2 : Identifiant et date
        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(0, 0, 0, 0)
        bottom_row.setSpacing(6)

        id_str = tr("Étape %1 · %2", patch.step_order, self.patch_id[:8]) if self.is_step else (f"#{self.target_id} · {self.patch_id[:8]}" if self.target_id else self.patch_id[:8])

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


class HierarchicalPatchTreeWidget(QTreeWidget):
    """Arborescence hiérarchique maître supportant les bundles, étapes et patchs autonomes."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setRootIsDecorated(True)
        self.setIndentation(14)
        self.setAnimated(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet(f"""
            QTreeWidget {{
                background-color: transparent;
                border: none;
            }}
            QTreeWidget::item {{
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                background-color: {DesignTokens.BG_INPUT};
                margin-bottom: 4px;
                padding: 2px;
            }}
            QTreeWidget::item:selected {{
                background-color: {DesignTokens.BG_ACTIVE};
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
            QTreeWidget::item:hover:!selected {{
                background-color: {DesignTokens.BG_HOVER};
            }}
        """)
        self._selectable_items: list[QTreeWidgetItem] = []

    def register_selectable_item(self, item: QTreeWidgetItem) -> None:
        """Enregistre un item de patch ou d'étape sélectionnable pour l'accès séquentiel."""
        self._selectable_items.append(item)

    def reset_selectable_items(self) -> None:
        self._selectable_items.clear()

    def count(self) -> int:
        """Nombre total d'éléments sélectionnables (parité avec QListWidget)."""
        return len(self._selectable_items)

    def currentRow(self) -> int:
        """Index séquentiel de l'item actuellement sélectionné (0-based)."""
        curr = self.currentItem()
        if not curr:
            return -1
        try:
            return self._selectable_items.index(curr)
        except ValueError:
            return -1

    def setCurrentRow(self, row: int) -> None:
        """Sélectionne le n-ième élément sélectionnable (parité avec QListWidget)."""
        if 0 <= row < len(self._selectable_items):
            self.setCurrentItem(self._selectable_items[row])

    def item(self, index: int) -> QTreeWidgetItem | None:
        """Renvoie le n-ième élément sélectionnable."""
        if 0 <= index < len(self._selectable_items):
            return self._selectable_items[index]
        return None

    def addItem(self, item: QTreeWidgetItem) -> None:
        """Ajoute un item racine (compatibilité QListWidget)."""
        self.addTopLevelItem(item)
        self.register_selectable_item(item)


class MCPGardeFouWidget(QWidget):
    """Panneau de supervision et de validation des propositions MCP en disposition Maître-Détail."""

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

        # ── 1. VOLET MAÎTRE HIÉRARCHIQUE (Gauche) ─────────────────────────────
        self.left_panel = QFrame()
        self.left_panel.setObjectName("mcp_gf_master")
        self.left_panel.setMinimumWidth(280)
        self.left_panel.setMaximumWidth(420)
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

        # Boutons de lot globaux
        batch_row = QHBoxLayout()
        batch_row.setContentsMargins(0, 0, 0, 0)
        batch_row.setSpacing(6)

        self.btn_apply_all = SecondaryButton(tr("Tout appliquer"))
        self.btn_apply_all.setIcon(load_phosphor_icon("ph.checks", color=DesignTokens.COLOR_GREEN))
        self.btn_apply_all.setFixedHeight(30)
        self.btn_apply_all.setStyleSheet("""
            QPushButton {
                padding: 4px 8px;
                font-size: 11px;
                font-weight: 600;
            }
        """)
        self.btn_apply_all.clicked.connect(self._apply_all_patches)
        batch_row.addWidget(self.btn_apply_all)

        self.btn_reject_all = SecondaryButton(tr("Tout rejeter"))
        self.btn_reject_all.setIcon(load_phosphor_icon("ph.x", color=DesignTokens.COLOR_RED))
        self.btn_reject_all.setFixedHeight(30)
        self.btn_reject_all.setStyleSheet("""
            QPushButton {
                padding: 4px 8px;
                font-size: 11px;
                font-weight: 600;
            }
        """)
        self.btn_reject_all.clicked.connect(self._reject_all_patches)
        batch_row.addWidget(self.btn_reject_all)

        left_layout.addLayout(batch_row)

        # Arbre hiérarchique maître (avec alias de compatibilité patch_list)
        self.patch_tree = HierarchicalPatchTreeWidget()
        self.patch_list = self.patch_tree
        self.patch_tree.currentItemChanged.connect(self._on_item_selection_changed)
        left_layout.addWidget(self.patch_tree, 1)

        splitter.addWidget(self.left_panel)

        # ── 2. ZONE DÉTAIL POLYMORPHE (Droite) ───────────────────────────────
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

        # Index 1 : Vue Détail Polymorphe
        self.detail_view = QWidget()
        detail_view_layout = QVBoxLayout(self.detail_view)
        detail_view_layout.setContentsMargins(12, 12, 12, 12)
        detail_view_layout.setSpacing(10)

        # Barre supérieure de détail (Titre + Métadonnées + Feedback)
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

        # ── QStackedWidget Polymorphe (4 pages) ──────────────────────────────
        self.polymorphic_stack = QStackedWidget()

        # Page 0 : Diff sémantique mot à mot pour les cartes
        self.diff_viewer = CardSemanticDiffWidget()
        self.polymorphic_stack.addWidget(self.diff_viewer)

        # Page 1 : Arborescence de paquets (deck_create / deck_rename)
        self.deck_view = DeckOperationWidget()
        self.polymorphic_stack.addWidget(self.deck_view)

        # Page 2 : Tableau comparatif des tags (set_tags / set_tags_bulk)
        self.tag_view = TagDiffWidget()
        self.polymorphic_stack.addWidget(self.tag_view)

        # Page 3 : Bannière rouge vif avec décompte d'impact (suppressions)
        self.deletion_view = DeletionImpactWidget()
        self.polymorphic_stack.addWidget(self.deletion_view)

        detail_view_layout.addWidget(self.polymorphic_stack, 1)

        # ── Barre d'Action Séquentielle Inférieure ───────────────────────────
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

        self.btn_apply_bundle_all = SecondaryButton(tr("Tout valider le bloc"))
        self.btn_apply_bundle_all.setIcon(load_phosphor_icon("ph.checks", color=DesignTokens.COLOR_GREEN))
        self.btn_apply_bundle_all.setFixedHeight(32)
        self.btn_apply_bundle_all.setStyleSheet(f"""
            QPushButton {{
                background-color: {DesignTokens.COLOR_GREEN_BG};
                color: {DesignTokens.COLOR_GREEN};
                border: 1px solid {DesignTokens.COLOR_GREEN};
                border-radius: 4px;
                font-weight: 600;
                padding: 0 14px;
            }}
            QPushButton:hover {{
                background-color: {DesignTokens.COLOR_GREEN};
                color: white;
            }}
        """)
        self.btn_apply_bundle_all.clicked.connect(self._apply_bundle_all)
        self.btn_apply_bundle_all.setVisible(False)
        action_bar.addWidget(self.btn_apply_bundle_all)

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
        """Recharge l'arborescence complète des bundles et propositions en attente."""
        prev_patch_id = self.current_patch_id
        prev_row = self.patch_tree.currentRow()

        self.patch_tree.blockSignals(True)
        self.patch_tree.clear()
        self.patch_tree.reset_selectable_items()

        self._patches.clear()
        selected_item: QTreeWidgetItem | None = None

        # 1. Chargement des Staged Bundles en attente
        bundles = list(StagedBundleModel.select().where(StagedBundleModel.status.in_(["pending", "partial"])).order_by(StagedBundleModel.created_at.asc()))

        for bundle in bundles:
            bundle_patches = list(bundle.patches.where(StagedPatchModel.status == "pending").order_by(StagedPatchModel.step_order.asc()))
            if not bundle_patches:
                continue

            bundle_item = QTreeWidgetItem()
            bundle_item.setData(0, Qt.ItemDataRole.UserRole, f"bundle:{bundle.bundle_id}")
            bundle_widget = BundleHeaderItemWidget(bundle, len(bundle_patches))
            bundle_item.setSizeHint(0, bundle_widget.sizeHint())
            self.patch_tree.addTopLevelItem(bundle_item)
            self.patch_tree.setItemWidget(bundle_item, 0, bundle_widget)
            bundle_item.setExpanded(True)

            for patch in bundle_patches:
                self._patches.append(patch)
                step_item = QTreeWidgetItem(bundle_item)
                step_item.setData(0, Qt.ItemDataRole.UserRole, patch.patch_id)
                step_widget = PatchListItemWidget(patch, is_step=True)
                step_item.setSizeHint(0, step_widget.sizeHint())
                self.patch_tree.setItemWidget(step_item, 0, step_widget)
                self.patch_tree.register_selectable_item(step_item)

                if prev_patch_id and patch.patch_id == prev_patch_id:
                    selected_item = step_item

        # 2. Chargement des patchs autonomes (hors bundle)
        standalone_patches = list(
            StagedPatchModel.select().where(StagedPatchModel.bundle.is_null(True), StagedPatchModel.status == "pending").order_by(StagedPatchModel.created_at.asc(), StagedPatchModel.id.asc())
        )

        for patch in standalone_patches:
            self._patches.append(patch)
            item = QTreeWidgetItem()
            item.setData(0, Qt.ItemDataRole.UserRole, patch.patch_id)
            item_widget = PatchListItemWidget(patch, is_step=False)
            item.setSizeHint(0, item_widget.sizeHint())
            self.patch_tree.addTopLevelItem(item)
            self.patch_tree.setItemWidget(item, 0, item_widget)
            self.patch_tree.register_selectable_item(item)

            if prev_patch_id and patch.patch_id == prev_patch_id:
                selected_item = item

        self.patch_tree.blockSignals(False)

        # Mise à jour des compteurs et états
        total_count = len(self._patches)
        self.badge_count.setText(str(total_count))
        self.badge_count.set_variant("danger" if total_count else "neutral")

        if not self._patches:
            self._current_patch = None
            self.detail_stack.setCurrentIndex(0)
            self.btn_apply_all.setEnabled(False)
            self.btn_reject_all.setEnabled(False)
        else:
            self.btn_apply_all.setEnabled(True)
            self.btn_reject_all.setEnabled(True)
            if selected_item is not None:
                self.patch_tree.setCurrentItem(selected_item)
            else:
                target_row = max(0, min(prev_row, total_count - 1)) if prev_row >= 0 else 0
                self.patch_tree.setCurrentRow(target_row)

        self.queue_updated.emit(total_count)

    def select_patch_by_id(self, patch_id: str) -> bool:
        """Sélectionne un patch spécifique dans l'arborescence par son identifiant unique."""
        clean_id = patch_id.strip()
        for item in self.patch_tree._selectable_items:
            if item.data(0, Qt.ItemDataRole.UserRole) == clean_id:
                self.patch_tree.setCurrentItem(item)
                return True
        return False

    def _on_item_selection_changed(self, current: QTreeWidgetItem | None, _prev: QTreeWidgetItem | None) -> None:
        if not current:
            self._current_patch = None
            self.detail_stack.setCurrentIndex(0)
            return

        raw_id = current.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(raw_id, str) and raw_id.startswith("bundle:"):
            # Si clic sur le conteneur bundle, sélectionner sa 1ère étape
            if current.childCount() > 0:
                first_child = current.child(0)
                if first_child:
                    self.patch_tree.setCurrentItem(first_child)
            return

        match = next((p for p in self._patches if p.patch_id == raw_id), None)
        if not match:
            self.detail_stack.setCurrentIndex(0)
            return

        self._current_patch = match
        self.detail_stack.setCurrentIndex(1)
        self._display_patch(match)

    def _display_patch(self, patch: StagedPatchModel) -> None:
        """Injecte les données du patch dans la zone de détail et route vers la bonne page polymorphe."""
        payload = staged_payload_of(patch)
        p_type = patch.patch_type.lower().strip()

        # En-tête de détail
        if patch.bundle:
            title = str(payload.get("title") or tr("Étape %1 — %2", patch.step_order, patch.patch_type))
            meta_str = tr(
                "Bundle : %1 · Étape %2/%3 · ID: %4",
                patch.bundle.title,
                patch.step_order,
                patch.bundle.total_steps,
                patch.patch_id[:8],
            )
            self.btn_apply.setText(tr("Valider cette étape"))
            self.btn_reject.setText(tr("Rejeter la suite du bloc"))
            self.btn_apply_bundle_all.setVisible(True)
        else:
            title = str(payload.get("title") or tr("Proposition — %1 #%2", patch.patch_type, patch.target_id))
            meta_str = f"ID: {patch.patch_id} · Type: {patch.patch_type.upper()}"
            if patch.target_id:
                meta_str += tr(" · Note ciblée : #%1", patch.target_id)
            self.btn_apply.setText(tr("Appliquer la modification"))
            self.btn_reject.setText(tr("Rejeter la proposition"))
            self.btn_apply_bundle_all.setVisible(False)

        self.lbl_detail_title.setText(title)
        self.lbl_detail_meta.setText(meta_str)

        # Routage vers la page polymorphe du QStackedWidget
        if p_type == "batch_note_create":
            self.polymorphic_stack.setCurrentIndex(0)
            self.diff_viewer.set_patch(patch)
        elif p_type in ("deck_create", "create_deck", "deck_rename", "rename_deck"):
            self.polymorphic_stack.setCurrentIndex(1)
            self.deck_view.set_patch(patch)
        elif p_type in ("set_tags", "set_tags_bulk", "tag_add", "tag_remove", "tags") or (isinstance(payload, dict) and ("tags_added" in payload or "tags_removed" in payload)):
            self.polymorphic_stack.setCurrentIndex(2)
            self.tag_view.set_patch(patch)
        elif p_type in ("card_delete", "deck_delete", "delete_empty_cards", "empty_cards_delete", "note_delete", "batch_card_deletion", "batch_note_delete"):
            self.polymorphic_stack.setCurrentIndex(3)
            self.deletion_view.set_patch(patch)
        else:
            self.polymorphic_stack.setCurrentIndex(0)
            self.diff_viewer.set_patch(patch)

    def _get_current_modified_content(self) -> Any:
        """Extrait le contenu retouché de la vue polymorphe active."""
        if self._current_patch and getattr(self._current_patch, "patch_type", "").lower() == "batch_note_create" and hasattr(self, "diff_viewer"):
            try:
                res = self.diff_viewer.get_modified_content()
                if res is not None:
                    return res
            except Exception:
                pass
        idx = self.polymorphic_stack.currentIndex()
        if idx == 0:
            return self.diff_viewer.get_modified_content()
        elif idx == 1:
            return self.deck_view.get_modified_content()
        elif idx == 2:
            return self.tag_view.get_modified_content()
        elif idx == 3:
            return self.deletion_view.get_modified_content()
        return None

    def _filter_list(self, text: str) -> None:
        """Filtre les éléments de l'arbre par texte."""
        query = text.strip().lower()
        for i in range(self.patch_tree.topLevelItemCount()):
            top_item = self.patch_tree.topLevelItem(i)
            if not top_item:
                continue

            # Si c'est un bundle, on vérifie si lui ou un enfant correspond
            has_matching_child = False
            for j in range(top_item.childCount()):
                child = top_item.child(j)
                if not child:
                    continue
                w = self.patch_tree.itemWidget(child, 0)
                if isinstance(w, PatchListItemWidget):
                    matched = not query or query in w.title.lower() or query in w.patch_id.lower() or query in str(w.target_id)
                    child.setHidden(not matched)
                    if matched:
                        has_matching_child = True

            top_w = self.patch_tree.itemWidget(top_item, 0)
            if isinstance(top_w, BundleHeaderItemWidget):
                top_matched = not query or query in (top_w.bundle_id.lower())
                top_item.setHidden(not (top_matched or has_matching_child))
            elif isinstance(top_w, PatchListItemWidget):
                top_matched = not query or query in top_w.title.lower() or query in top_w.patch_id.lower()
                top_item.setHidden(not top_matched)

    def _apply_current_patch(self) -> None:
        """Applique l'étape courante (avec synchronisation de l'édition directe) et avance d'un cran."""
        if not self._current_patch:
            return

        patch_id = self._current_patch.patch_id
        bundle = self._current_patch.bundle
        step_order = self._current_patch.step_order

        # 1. Synchronisation de l'édition directe (uniquement pour les patchs unitaires ou scissions, pas les lots bruts)
        p_type = getattr(self._current_patch, "patch_type", "")
        if p_type not in ("batch_note_create", "batch_create"):
            edited_content = self._get_current_modified_content()
            if edited_content is not None:
                StagedPatchRegistry.sync_direct_edit(patch_id, edited_content)

        # 2. Application transactionnelle
        res = StagedPatchRegistry.apply_bundle_step(bundle.bundle_id, step_order) if bundle else StagedPatchRegistry.apply_staged_patch(patch_id)

        if res.get("status") == "applied":
            show_toast(self, tr("Étape %1 appliquée avec succès !", patch_id[:8]), level="success")
            self.patch_applied.emit(patch_id)
            self.reload_pending_patches()
        else:
            err_msg = res.get("message") or tr("Échec lors de l'application du patch.")
            show_toast(self, err_msg, level="error")

    def _reject_current_patch(self) -> None:
        """Rejette la proposition courante (avec cascade fail-fast k..N pour un bundle)."""
        if not self._current_patch:
            return

        patch_id = self._current_patch.patch_id
        bundle = self._current_patch.bundle
        step_order = self._current_patch.step_order

        if bundle:
            res = StagedPatchRegistry.reject_bundle_step(
                bundle.bundle_id,
                step_order=step_order,
                reason="Rejet en cascade via IHM Garde-Fou",
            )
            count = res.get("rejected_steps_count", 1)
            show_toast(self, tr("%1 étape(s) rejetée(s) en cascade.", count), level="info")
        else:
            res = StagedPatchRegistry.reject_staged_patch(patch_id, reason="Rejeté via IHM Garde-Fou")
            show_toast(self, tr("Patch %1 rejeté.", patch_id[:8]), level="info")

        if res.get("status") == "rejected":
            self.patch_rejected.emit(patch_id)
            self.reload_pending_patches()

    def _apply_bundle_all(self) -> None:
        """Applique l'intégralité du bundle en une transaction atomique unique."""
        if not self._current_patch or not self._current_patch.bundle:
            return

        bundle_id = self._current_patch.bundle.bundle_id

        # Synchronisation de l'édition directe de l'étape active avant l'application globale (sauf lots)
        p_type = getattr(self._current_patch, "patch_type", "")
        if p_type not in ("batch_note_create", "batch_create"):
            edited_content = self._get_current_modified_content()
            if edited_content is not None:
                StagedPatchRegistry.sync_direct_edit(self._current_patch.patch_id, edited_content)

        res = StagedPatchRegistry.apply_bundle_all(bundle_id)
        if res.get("status") == "applied":
            count = res.get("applied_steps_count", 0)
            show_toast(self, tr("Bundle appliqué avec succès (%1 étapes) !", count), level="success")
            self.patch_applied.emit(bundle_id)
            self.reload_pending_patches()
        else:
            err_msg = res.get("message") or tr("Échec lors de l'application du bundle.")
            show_toast(self, err_msg, level="error")

    def _apply_all_patches(self) -> None:
        """Applique l'ensemble des propositions et bundles en attente."""
        if not self._patches:
            return

        applied_count = 0
        failures: list[str] = []
        handled_bundles: set[str] = set()

        for patch in list(self._patches):
            if patch.bundle:
                b_id = patch.bundle.bundle_id
                if b_id in handled_bundles:
                    continue
                handled_bundles.add(b_id)
                res = StagedPatchRegistry.apply_bundle_all(b_id)
                if res.get("status") == "applied":
                    applied_count += res.get("applied_steps_count", 1)
                    self.patch_applied.emit(b_id)
                else:
                    failures.append(str(res.get("message") or tr("Échec lors de l'application du bundle '%1'.", b_id)))
            else:
                res = StagedPatchRegistry.apply_staged_patch(patch.patch_id)
                if res.get("status") == "applied":
                    applied_count += 1
                    self.patch_applied.emit(patch.patch_id)
                else:
                    failures.append(str(res.get("message") or tr("Échec lors de l'application du patch '%1'.", patch.patch_id[:8])))

        if failures:
            if applied_count:
                message = tr("%1 proposition(s) appliquée(s), %2 échec(s) : %3", applied_count, len(failures), failures[0])
            else:
                message = tr("Échec de l'application des propositions : %1", failures[0])
            show_toast(self, message, level="error")
        else:
            show_toast(self, tr("%1 proposition(s) appliquée(s).", applied_count), level="success")
        self.reload_pending_patches()

    def _reject_all_patches(self) -> None:
        """Rejette l'ensemble des propositions et bundles en attente."""
        if not self._patches:
            return

        count = len(self._patches)
        handled_bundles: set[str] = set()

        for patch in list(self._patches):
            if patch.bundle:
                b_id = patch.bundle.bundle_id
                if b_id in handled_bundles:
                    continue
                handled_bundles.add(b_id)
                StagedPatchRegistry.reject_bundle_step(b_id, step_order=1, reason="Rejet groupé via IHM")
                self.patch_rejected.emit(b_id)
            else:
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
        if hasattr(self, "deck_view") and hasattr(self.deck_view, "refresh_theme"):
            self.deck_view.refresh_theme(profile)
        if hasattr(self, "tag_view") and hasattr(self.tag_view, "refresh_theme"):
            self.tag_view.refresh_theme(profile)
        if hasattr(self, "deletion_view") and hasattr(self.deletion_view, "refresh_theme"):
            self.deletion_view.refresh_theme(profile)

    def cleanup(self) -> None:
        """Arrête les chargements Chromium et libère les ressources WebEngine."""
        if hasattr(self, "diff_viewer") and hasattr(self.diff_viewer, "cleanup"):
            self.diff_viewer.cleanup()
