"""Sous-onglet Garde-Fou & Validation en disposition Maître-Détail pour le serveur MCP.

Présente les propositions d'agents externes dans un volet maître hiérarchique à gauche
(bundles regroupés avec sous-étapes et patchs autonomes), et une zone de détail polymorphe
à droite (diff sémantique, arborescence de paquets, tags et avertissement de suppression)
avec barre d'action séquentielle pas-à-pas et arrêt en cascade.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSizePolicy,
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
    FilterChipButton,
    PrimaryButton,
    SecondaryButton,
)
from ankiforge.ui.components.panels import EmptyStateWidget
from ankiforge.ui.theme import DesignTokens, apply_shadow
from ankiforge.ui.views.consultant_view.widgets.garde_fou_views import (
    DeckOperationWidget,
    DeletionImpactWidget,
    NoteTypePatchWidget,
    TagDiffWidget,
)
from ankiforge.ui.widgets.card_create_view_widget import CardCreateViewWidget
from ankiforge.ui.widgets.card_semantic_diff_widget import CardSemanticDiffWidget
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.environment import get_app_qsettings
from ankiforge.utils.event_bus import MCPBundleStagedEvent, MCPPatchStagedEvent, event_bus
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
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(6)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(load_phosphor_icon("ph.stack", color=DesignTokens.ACCENT_PRIMARY).pixmap(16, 16))
        top_row.addWidget(icon_lbl)

        lbl_title = QLabel(bundle.title or tr("Bloc d'opérations"))
        lbl_title.setWordWrap(True)
        lbl_title.setStyleSheet(f"""
            font-size: 12px;
            font-weight: 600;
            color: {DesignTokens.TEXT_PRIMARY};
            border: none;
            background: transparent;
        """)
        top_row.addWidget(lbl_title, 1)

        if bundle.status == "aborted":
            bundle_badge = Badge(tr("Annulé"), variant="warning")
            bundle_badge.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
            top_row.addWidget(bundle_badge, 0, Qt.AlignmentFlag.AlignTop)
        else:
            badge_text = tr("%1 étapes", bundle.total_steps)
            badge_variant = "accent"
            if bundle.current_step > 1:
                badge_text = tr("Étape %1/%2", bundle.current_step, bundle.total_steps)
                badge_variant = "warning"
            bundle_badge = Badge(badge_text, variant=badge_variant)
            bundle_badge.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
            top_row.addWidget(bundle_badge, 0, Qt.AlignmentFlag.AlignTop)
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
            lbl_desc.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            lbl_desc.setMinimumWidth(0)
            layout.addWidget(lbl_desc)

        # Hauteur minimale adaptée selon présence de description
        min_h = 56 if bundle.explanation else 44
        self.setMinimumHeight(min_h)

    def sizeHint(self) -> QSize:
        """Retourne la taille suggérée respectant la hauteur minimale."""
        hint = super().sizeHint()
        min_hint = self.minimumSizeHint()
        # Respect minimum width and height
        return QSize(max(hint.width(), min_hint.width(), self.minimumWidth()), max(hint.height(), min_hint.height(), self.minimumHeight()))


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
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # Ligne 1 : Titre + Badge de type + Badge d'état si annulé
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(6)

        is_aborted = patch.status == "aborted"
        title_color = DesignTokens.TEXT_MUTED if is_aborted else DesignTokens.TEXT_PRIMARY
        title_weight = "500" if is_aborted else "600"

        lbl_title = QLabel(self.title)
        lbl_title.setStyleSheet(f"""
            font-size: 12px;
            font-weight: {title_weight};
            color: {title_color};
            border: none;
            background: transparent;
        """)
        lbl_title.setWordWrap(True)
        lbl_title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        lbl_title.setMinimumWidth(0)
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
        type_badge.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        top_row.addWidget(type_badge)

        if is_aborted:
            abort_badge = Badge(tr("Annulé"), variant="warning")
            abort_badge.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
            top_row.addWidget(abort_badge)

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
        lbl_meta.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        lbl_meta.setMinimumWidth(0)
        bottom_row.addWidget(lbl_meta, 1)

        created_str = patch.created_at.strftime("%H:%M:%S") if patch.created_at else ""
        if created_str:
            lbl_time = QLabel(created_str)
            lbl_time.setStyleSheet(f"""
                font-size: 10px;
                color: {DesignTokens.TEXT_MUTED};
                border: none;
                background: transparent;
            """)
            lbl_time.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
            bottom_row.addWidget(lbl_time)

        layout.addLayout(bottom_row)

        # Ensure minimum height for the widget (2 rows with margins and spacing)
        self.setMinimumHeight(56)

    def sizeHint(self) -> QSize:
        """Retourne la taille suggérée respectant la hauteur minimale."""
        hint = super().sizeHint()
        min_hint = self.minimumSizeHint()
        # Respect minimum width and height
        return QSize(max(hint.width(), min_hint.width(), self.minimumWidth()), max(hint.height(), min_hint.height(), self.minimumHeight()))


class HierarchicalPatchTreeWidget(QTreeWidget):
    """Arborescence hiérarchique maître supportant les bundles, étapes et patchs autonomes."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.header().setStretchLastSection(True)
        self.setHeaderHidden(True)
        self.setRootIsDecorated(True)
        self.setIndentation(14)
        self.setAnimated(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QTreeWidget {{
                background-color: transparent;
                border: none;
            }}
            QTreeWidget::item {{
                border: 1px solid transparent;
                border-radius: 6px;
                background-color: transparent;
                margin-bottom: 2px;
                padding: 2px;
            }}
            QTreeWidget::item:selected {{
                background-color: {DesignTokens.BG_ACTIVE};
                border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                border-radius: 6px;
            }}
            QTreeWidget::item:hover:!selected {{
                background-color: {DesignTokens.BG_HOVER};
                border-radius: 6px;
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
    """Panneau de supervision et de validation des propositions MCP en disposition Maître-Detail."""

    patch_applied = Signal(str)
    patch_rejected = Signal(str)
    queue_updated = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._patches: list[StagedPatchModel] = []
        self._current_patch: StagedPatchModel | None = None
        self._notified_patch_ids: set[str] = set()
        self._current_status_filter: str = "pending"
        self._skip_confirm_for_test: bool = False

        self._setup_ui()

        # Raccourcis clavier (Power User)
        self._shortcut_apply = QShortcut(QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_Return), self)
        self._shortcut_apply.activated.connect(self._apply_current_patch)
        self._shortcut_apply_enter = QShortcut(QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_Enter), self)
        self._shortcut_apply_enter.activated.connect(self._apply_current_patch)
        self._shortcut_reject = QShortcut(QKeySequence(Qt.Key.Key_Delete), self)
        self._shortcut_reject.activated.connect(self._reject_current_patch)

        # Abonnement direct au bus d'événements pour le rafraîchissement incrémental
        event_bus.subscribe(MCPPatchStagedEvent, self._on_mcp_patch_staged)
        event_bus.subscribe(MCPBundleStagedEvent, self._on_mcp_bundle_staged)

        self.reload_pending_patches()

    @property
    def current_patch_id(self) -> str | None:
        """Identifiant du patch actuellement affiché dans la zone de détail."""
        return self._current_patch.patch_id if self._current_patch else None

    def count(self) -> int:
        """Nombre total de patchs en attente dans la file du garde-fou."""
        return len(self._patches)

    def _save_tree_state(self) -> dict:
        """Capture l'état visuel de l'arbre (expansion, sélection, scroll)."""
        expanded_ids: list[str] = []
        for i in range(self.patch_tree.topLevelItemCount()):
            item = self.patch_tree.topLevelItem(i)
            if item and item.isExpanded():
                data = item.data(0, Qt.ItemDataRole.UserRole)
                if data:
                    expanded_ids.append(data)
                for j in range(item.childCount()):
                    child = item.child(j)
                    if child and child.isExpanded():
                        child_data = child.data(0, Qt.ItemDataRole.UserRole)
                        if child_data:
                            expanded_ids.append(child_data)

        current_item = self.patch_tree.currentItem()
        selected_id = current_item.data(0, Qt.ItemDataRole.UserRole) if current_item else None
        scroll_pos = self.patch_tree.verticalScrollBar().value()

        return {
            "expanded_ids": expanded_ids,
            "selected_id": selected_id,
            "scroll_pos": scroll_pos,
        }

    def _restore_tree_state(self, state: dict) -> None:
        """Restaure l'état visuel de l'arbre."""
        expanded_ids = state.get("expanded_ids", [])
        selected_id = state.get("selected_id")
        scroll_pos = state.get("scroll_pos", 0)

        # Restaurer l'expansion
        for i in range(self.patch_tree.topLevelItemCount()):
            item = self.patch_tree.topLevelItem(i)
            if not item:
                continue
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data in expanded_ids:
                item.setExpanded(True)
            for j in range(item.childCount()):
                child = item.child(j)
                if child:
                    child_data = child.data(0, Qt.ItemDataRole.UserRole)
                    if child_data in expanded_ids:
                        child.setExpanded(True)

        # Restaurer la sélection
        if selected_id:
            for i in range(self.patch_tree.topLevelItemCount()):
                item = self.patch_tree.topLevelItem(i)
                if item and item.data(0, Qt.ItemDataRole.UserRole) == selected_id:
                    self.patch_tree.setCurrentItem(item)
                    break
                for j in range(item.childCount()):
                    child = item.child(j)
                    if child and child.data(0, Qt.ItemDataRole.UserRole) == selected_id:
                        self.patch_tree.setCurrentItem(child)
                        break

        # Restaurer le scroll
        self.patch_tree.verticalScrollBar().setValue(scroll_pos)

    def _on_mcp_bundle_staged(self, event: MCPBundleStagedEvent) -> None:
        """Crée le nœud parent d'un bundle dans l'arborescence maître et charge ses étapes."""
        logger.debug(f"_on_mcp_bundle_staged called: bundle_id={event.bundle_id}")

        if not event.bundle_id:
            return

        # Déduplication : vérifier si le nœud bundle existe déjà
        bundle_key = f"bundle:{event.bundle_id}"
        for i in range(self.patch_tree.topLevelItemCount()):
            item = self.patch_tree.topLevelItem(i)
            if item and item.data(0, Qt.ItemDataRole.UserRole) == bundle_key:
                # Bundle déjà présent, ne rien faire
                logger.debug(f"_on_mcp_bundle_staged: bundle already exists: {bundle_key}")
                return

        # Récupérer le bundle depuis la BDD
        bundle = StagedBundleModel.get_or_none(StagedBundleModel.bundle_id == event.bundle_id)
        if not bundle:
            # Fallback si le bundle n'est pas encore en BDD (peu probable)
            bundle = StagedBundleModel(bundle_id=event.bundle_id, title=event.title, total_steps=event.total_steps)

        bundle_item = QTreeWidgetItem()
        bundle_item.setData(0, Qt.ItemDataRole.UserRole, bundle_key)
        bundle_widget = BundleHeaderItemWidget(bundle, event.total_steps)
        bundle_item.setSizeHint(0, bundle_widget.sizeHint())
        self.patch_tree.addTopLevelItem(bundle_item)
        self.patch_tree.setItemWidget(bundle_item, 0, bundle_widget)
        bundle_item.setExpanded(True)

        # Charger et ajouter les étapes du bundle depuis la BDD
        bundle_patches = list(bundle.patches.where(StagedPatchModel.status == "pending").order_by(StagedPatchModel.step_order.asc()))
        for patch in bundle_patches:
            if patch.patch_id in self._notified_patch_ids:
                continue
            self._notified_patch_ids.add(patch.patch_id)
            self._patches.append(patch)
            step_item = QTreeWidgetItem(bundle_item)
            step_item.setData(0, Qt.ItemDataRole.UserRole, patch.patch_id)
            step_widget = PatchListItemWidget(patch, is_step=True)
            step_item.setSizeHint(0, step_widget.sizeHint())
            self.patch_tree.setItemWidget(step_item, 0, step_widget)
            self.patch_tree.register_selectable_item(step_item)

        # Mise à jour des compteurs et badge
        total_count = len(self._patches)
        self.badge_count.setText(str(total_count))
        self.badge_count.set_variant("danger" if total_count else "neutral")
        self.queue_updated.emit(total_count)

        # Rafraîchir l'affichage de l'arbre pour garantir la mise à jour visuelle immédiate
        # Utiliser singleShot pour s'assurer que la mise à jour se fait après le traitement d'événements courant
        from PySide6.QtCore import QTimer

        def _refresh_tree() -> None:
            self.patch_tree.viewport().repaint()

        QTimer.singleShot(0, _refresh_tree)

        # Si l'arbre était vide, sélectionner automatiquement le premier élément
        if total_count > 0 and self.patch_tree.currentItem() is None:
            self.patch_tree.setCurrentRow(0)

    def _on_mcp_patch_staged(self, event: MCPPatchStagedEvent) -> None:
        """Insère incrémentalement un patch dans l'arborescence (standalone ou enfant d'un bundle)."""
        logger.debug(f"_on_mcp_patch_staged called: patch_id={event.patch_id}, patch_type={event.patch_type}")

        if not event.patch_id or event.patch_id in self._notified_patch_ids:
            logger.debug(f"_on_mcp_patch_staged: skipping (duplicate or no id): {event.patch_id}")
            return
        self._notified_patch_ids.add(event.patch_id)

        # Vérifier si l'arbre était vide avant l'ajout
        was_empty = len(self._patches) == 0

        # Récupérer le patch complet depuis la BDD
        patch = StagedPatchModel.get_or_none(StagedPatchModel.patch_id == event.patch_id)
        if not patch:
            return

        self._patches.append(patch)

        if patch.bundle:
            # Patch appartenant à un bundle : l'ajouter comme enfant du nœud bundle
            bundle_key = f"bundle:{patch.bundle.bundle_id}"
            parent_item = None
            for i in range(self.patch_tree.topLevelItemCount()):
                item = self.patch_tree.topLevelItem(i)
                if item and item.data(0, Qt.ItemDataRole.UserRole) == bundle_key:
                    parent_item = item
                    break
            if parent_item:
                step_item = QTreeWidgetItem(parent_item)
                step_item.setData(0, Qt.ItemDataRole.UserRole, patch.patch_id)
                step_widget = PatchListItemWidget(patch, is_step=True)
                step_item.setSizeHint(0, step_widget.sizeHint())
                self.patch_tree.setItemWidget(step_item, 0, step_widget)
                self.patch_tree.register_selectable_item(step_item)
                # S'assurer que le parent est expandé
                parent_item.setExpanded(True)
            else:
                # Bundle parent pas encore créé (événements hors ordre) -> ajouter en standalone temporaire
                self._add_standalone_patch(patch)
        else:
            # Patch standalone
            self._add_standalone_patch(patch)

        # Mise à jour des compteurs et badge
        total_count = len(self._patches)
        self.badge_count.setText(str(total_count))
        self.badge_count.set_variant("danger" if total_count else "neutral")
        self.queue_updated.emit(total_count)

        # Rafraîchir l'affichage de l'arbre pour garantir la mise à jour visuelle immédiate
        # Utiliser singleShot pour s'assurer que la mise à jour se fait après le traitement d'événements courant
        from PySide6.QtCore import QTimer

        def _refresh_tree() -> None:
            self.patch_tree.viewport().repaint()

        QTimer.singleShot(0, _refresh_tree)

        # Si l'arbre était vide, sélectionner automatiquement le premier élément
        if was_empty and total_count > 0:
            self.patch_tree.setCurrentRow(0)

    def _add_standalone_patch(self, patch: StagedPatchModel) -> None:
        """Ajoute un patch standalone comme élément racine de l'arbre."""
        item = QTreeWidgetItem()
        item.setData(0, Qt.ItemDataRole.UserRole, patch.patch_id)
        item_widget = PatchListItemWidget(patch, is_step=False)
        item.setSizeHint(0, item_widget.sizeHint())
        self.patch_tree.addTopLevelItem(item)
        self.patch_tree.setItemWidget(item, 0, item_widget)
        self.patch_tree.register_selectable_item(item)

    def _setup_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(*DesignTokens.DESIGN_SYSTEM_MARGES["mcp_root"])
        main_layout.setSpacing(DesignTokens.DESIGN_SYSTEM_SPACING["mcp_root"])

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)

        # ── 1. VOLET MAÎTRE HIÉRARCHIQUE (Gauche) ─────────────────────────────
        self.left_panel = QFrame()
        self.left_panel.setObjectName("mcp_gf_master")
        self.left_panel.setMinimumWidth(280)
        self.left_panel.setStyleSheet(f"""
            QFrame#mcp_gf_master {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(12, 12, 12, 12)
        left_layout.setSpacing(8)

        # En-tête de la liste
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        lbl_title = QLabel(tr("PROPOSITIONS EN ATTENTE"))
        lbl_title.setStyleSheet(f"""
            font-size: 11px;
            font-weight: 600;
            letter-spacing: 0.5px;
            text-transform: uppercase;
            color: {DesignTokens.TEXT_MUTED};
        """)
        header_row.addWidget(lbl_title)
        header_row.addStretch()

        self.badge_count = Badge("0", variant="neutral")
        header_row.addWidget(self.badge_count)
        left_layout.addLayout(header_row)

        # Barre de recherche / filtrage
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(tr("Filtrer les propositions..."))
        self.search_input.setFixedHeight(32)
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 11px;
                padding: 0 10px;
            }}
            QLineEdit:focus {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        self.search_input.textChanged.connect(self._filter_list)
        left_layout.addWidget(self.search_input)

        # Filtre de statut des propositions (En attente / Annulés / Tous)
        filter_row = QHBoxLayout()
        filter_row.setContentsMargins(0, 0, 0, 0)
        filter_row.setSpacing(4)

        self.chip_pending = FilterChipButton(tr("Attente"), icon_name="ph.clock")
        self.chip_pending.setChecked(True)
        self.chip_pending.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.chip_pending.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chip_pending.toggled.connect(lambda checked: self._set_status_filter("pending") if checked else None)

        self.chip_aborted = FilterChipButton(tr("Annulés"), icon_name="ph.trash")
        self.chip_aborted.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.chip_aborted.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chip_aborted.toggled.connect(lambda checked: self._set_status_filter("aborted") if checked else None)

        self.chip_all = FilterChipButton(tr("Tous"), icon_name="ph.list")
        self.chip_all.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.chip_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chip_all.toggled.connect(lambda checked: self._set_status_filter("all") if checked else None)

        self._status_chips: list[FilterChipButton] = [self.chip_pending, self.chip_aborted, self.chip_all]

        for chip in self._status_chips:
            filter_row.addWidget(chip)

        left_layout.addLayout(filter_row)

        # Boutons de lot globaux
        batch_row = QHBoxLayout()
        batch_row.setContentsMargins(0, 0, 0, 0)
        batch_row.setSpacing(6)

        self.btn_apply_all = SecondaryButton(tr("Tout valider"))
        self.btn_apply_all.setIcon(load_phosphor_icon("ph.checks", color=DesignTokens.COLOR_GREEN))
        self.btn_apply_all.setFixedHeight(32)
        self.btn_apply_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_apply_all.setStyleSheet("""
            QPushButton {
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 600;
            }
        """)
        self.btn_apply_all.clicked.connect(self._apply_all_patches)
        batch_row.addWidget(self.btn_apply_all)

        self.btn_reject_all = SecondaryButton(tr("Tout rejeter"))
        self.btn_reject_all.setIcon(load_phosphor_icon("ph.x", color=DesignTokens.COLOR_RED))
        self.btn_reject_all.setFixedHeight(32)
        self.btn_reject_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reject_all.setStyleSheet("""
            QPushButton {
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 600;
            }
        """)
        self.btn_reject_all.clicked.connect(self._reject_all_patches)
        batch_row.addWidget(self.btn_reject_all)

        self.lbl_batch_hint = QLabel()
        self.lbl_batch_hint.setStyleSheet(f"""
            font-size: 11px;
            color: {DesignTokens.TEXT_MUTED};
            font-style: italic;
            border: none;
            background: transparent;
        """)
        self.lbl_batch_hint.setVisible(False)
        batch_row.addWidget(self.lbl_batch_hint)
        batch_row.addStretch()

        left_layout.addLayout(batch_row)

        # Arbre hiérarchique maître (avec alias de compatibilité patch_list)
        self.patch_tree = HierarchicalPatchTreeWidget()
        self.patch_list = self.patch_tree
        self.patch_tree.currentItemChanged.connect(self._on_item_selection_changed)
        left_layout.addWidget(self.patch_tree, 1)

        self.splitter.addWidget(self.left_panel)

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

        # Index 0 : Vue Vide (EmptyStateWidget officiel avec guidage d'onboarding)
        self.empty_view = EmptyStateWidget(
            icon_name="ph.shield-check",
            title=tr("Garde-Fou au repos"),
            description=tr("Toutes les propositions d'agents IA ont été traitées.\nVotre collection Anki est parfaitement synchronisée et protégée."),
            parent=self,
        )
        self.detail_stack.addWidget(self.empty_view)

        # Index 1 : Vue Détail Polymorphe
        self.detail_view = QWidget()
        detail_view_layout = QVBoxLayout(self.detail_view)
        detail_view_layout.setContentsMargins(16, 16, 16, 16)
        detail_view_layout.setSpacing(12)

        # Barre supérieure de détail (Titre + Métadonnées + Feedback)
        detail_header = QHBoxLayout()
        detail_header.setContentsMargins(0, 0, 0, 0)
        detail_header.setSpacing(12)

        title_col = QVBoxLayout()
        title_col.setSpacing(4)

        self.lbl_detail_title = QLabel()
        self.lbl_detail_title.setStyleSheet(f"""
            font-size: 15px;
            font-weight: 600;
            color: {DesignTokens.TEXT_PRIMARY};
        """)
        self.lbl_detail_title.setWordWrap(True)
        title_col.addWidget(self.lbl_detail_title)

        self.lbl_detail_meta = QLabel()
        self.lbl_detail_meta.setStyleSheet(f"""
            font-size: 11px;
            color: {DesignTokens.TEXT_MUTED};
            font-family: {DesignTokens.FONT_CODE};
        """)
        self.lbl_detail_meta.setWordWrap(True)
        title_col.addWidget(self.lbl_detail_meta)

        self.lbl_abort_reason = QLabel()
        self.lbl_abort_reason.setStyleSheet(f"""
            font-size: 11px;
            color: {DesignTokens.COLOR_YELLOW};
            font-family: {DesignTokens.FONT_CODE};
            border: none;
            background: transparent;
        """)
        self.lbl_abort_reason.setWordWrap(True)
        self.lbl_abort_reason.hide()
        title_col.addWidget(self.lbl_abort_reason)

        self.badge_abort_status = Badge(tr("Annulé par l'agent"), variant="warning")
        self.badge_abort_status.hide()
        title_col.addWidget(self.badge_abort_status)
        detail_header.addLayout(title_col, 1)

        self.btn_copy_feedback = SecondaryButton(tr("Copier le feedback"))
        self.btn_copy_feedback.setIcon(load_phosphor_icon("ph.copy", color=DesignTokens.TEXT_SECONDARY))
        self.btn_copy_feedback.setFixedHeight(32)
        self.btn_copy_feedback.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.btn_copy_feedback.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy_feedback.setToolTip(tr("Copier le compte-rendu d'arbitrage pour l'assistant IA"))
        self.btn_copy_feedback.clicked.connect(self._copy_feedback)
        detail_header.addWidget(self.btn_copy_feedback, 0, Qt.AlignmentFlag.AlignTop)

        detail_view_layout.addLayout(detail_header)

        # ── Bannière d'annulation claire pour propositions annulées ─────────
        self.abort_banner = QFrame()
        self.abort_banner.setObjectName("mcp_gf_abort_banner")
        self.abort_banner.setStyleSheet(f"""
            QFrame#mcp_gf_abort_banner {{
                background-color: {DesignTokens.COLOR_YELLOW_BG};
                border: 1px solid {DesignTokens.COLOR_YELLOW_BORDER};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 10px 14px;
            }}
        """)
        abort_layout = QHBoxLayout(self.abort_banner)
        abort_layout.setContentsMargins(10, 8, 10, 8)
        abort_layout.setSpacing(12)

        icon_prohibit = QLabel()
        icon_prohibit.setPixmap(load_phosphor_icon("ph.prohibit", color=DesignTokens.COLOR_YELLOW).pixmap(24, 24))
        abort_layout.addWidget(icon_prohibit)

        abort_text_col = QVBoxLayout()
        abort_text_col.setSpacing(2)

        lbl_banner_title = QLabel(tr("PROPOSITION ANNULÉE PAR L'ASSISTANT IA"))
        lbl_banner_title.setStyleSheet(f"font-size: 11px; font-weight: 700; color: {DesignTokens.COLOR_YELLOW_TEXT}; letter-spacing: 0.5px;")
        abort_text_col.addWidget(lbl_banner_title)

        self.lbl_abort_banner_desc = QLabel()
        self.lbl_abort_banner_desc.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_PRIMARY};")
        self.lbl_abort_banner_desc.setWordWrap(True)
        abort_text_col.addWidget(self.lbl_abort_banner_desc)

        abort_layout.addLayout(abort_text_col, 1)
        self.abort_banner.setVisible(False)
        detail_view_layout.addWidget(self.abort_banner)

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

        # Page 4 : Affichage dédié de création de carte (note_create / batch_note_create)
        self.create_view = CardCreateViewWidget()
        self.polymorphic_stack.addWidget(self.create_view)

        # Page 5 : Prévisualisation de note réelle pour les patches de types de notes
        self.note_type_view = NoteTypePatchWidget()
        self.polymorphic_stack.addWidget(self.note_type_view)

        detail_view_layout.addWidget(self.polymorphic_stack, 1)

        # ── Barre d'Action Séquentielle Inférieure ───────────────────────────
        action_bar = QHBoxLayout()
        action_bar.setContentsMargins(0, 8, 0, 0)
        action_bar.setSpacing(12)

        self.btn_reject = SecondaryButton(tr("Rejeter la proposition"))
        self.btn_reject.setIcon(load_phosphor_icon("ph.x", color=DesignTokens.COLOR_RED))
        self.btn_reject.setFixedHeight(36)
        self.btn_reject.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reject.setToolTip(tr("Rejeter la proposition (Suppr)"))
        self.btn_reject.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {DesignTokens.COLOR_RED_TEXT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                font-weight: 600;
                padding: 0 16px;
            }}
            QPushButton:hover {{
                background-color: {DesignTokens.COLOR_RED_BG};
                border-color: {DesignTokens.COLOR_RED};
                color: {DesignTokens.COLOR_RED_TEXT};
            }}
            QPushButton:disabled {{
                opacity: 0.45;
                border-color: {DesignTokens.BORDER_COLOR};
            }}
        """)
        self.btn_reject.clicked.connect(self._reject_current_patch)
        action_bar.addWidget(self.btn_reject)

        action_bar.addStretch()

        self.btn_apply_bundle_all = SecondaryButton(tr("Tout valider le bloc"))
        self.btn_apply_bundle_all.setIcon(load_phosphor_icon("ph.checks", color=DesignTokens.COLOR_GREEN))
        self.btn_apply_bundle_all.setFixedHeight(36)
        self.btn_apply_bundle_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_apply_bundle_all.setToolTip(tr("Valider toutes les étapes du lot en une seule transaction"))
        self.btn_apply_bundle_all.setStyleSheet(f"""
            QPushButton {{
                background-color: {DesignTokens.COLOR_GREEN_BG};
                color: {DesignTokens.COLOR_GREEN_TEXT};
                border: 1px solid {DesignTokens.COLOR_GREEN_BORDER};
                border-radius: 6px;
                font-weight: 600;
                padding: 0 16px;
            }}
            QPushButton:hover {{
                background-color: {DesignTokens.COLOR_GREEN};
                color: white;
            }}
        """)
        self.btn_apply_bundle_all.clicked.connect(self._apply_bundle_all)
        self.btn_apply_bundle_all.setVisible(False)
        action_bar.addWidget(self.btn_apply_bundle_all)

        self.btn_apply = PrimaryButton(tr("Valider la modification"))
        self.btn_apply.setIcon(load_on_accent_icon("ph.check"))
        self.btn_apply.setFixedHeight(36)
        self.btn_apply.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_apply.setToolTip(tr("Valider la modification (Ctrl+Entrée)"))
        apply_shadow(self.btn_apply, blur=12, offset_y=1, color=DesignTokens.ACCENT_GLOW)
        self.btn_apply.clicked.connect(self._apply_current_patch)
        action_bar.addWidget(self.btn_apply)

        self.btn_restore_patch = SecondaryButton(tr("Rétablir en attente"))
        self.btn_restore_patch.setIcon(load_phosphor_icon("ph.arrow-counter-clockwise", color=DesignTokens.COLOR_YELLOW))
        self.btn_restore_patch.setFixedHeight(36)
        self.btn_restore_patch.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_restore_patch.setToolTip(tr("Rétablir cette proposition dans la file d'attente pour révision"))
        self.btn_restore_patch.setStyleSheet(f"""
            QPushButton {{
                background-color: {DesignTokens.COLOR_YELLOW_BG};
                color: {DesignTokens.COLOR_YELLOW_TEXT};
                border: 1px solid {DesignTokens.COLOR_YELLOW_BORDER};
                border-radius: 6px;
                font-weight: 600;
                padding: 0 16px;
            }}
            QPushButton:hover {{
                background-color: {DesignTokens.COLOR_YELLOW};
                color: white;
            }}
        """)
        self.btn_restore_patch.clicked.connect(self._restore_current_patch)
        self.btn_restore_patch.setVisible(False)
        action_bar.addWidget(self.btn_restore_patch)

        detail_view_layout.addLayout(action_bar)
        self.detail_stack.addWidget(self.detail_view)

        right_layout.addWidget(self.detail_stack)
        self.splitter.addWidget(self.right_container)

        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        main_layout.addWidget(self.splitter)

        settings = get_app_qsettings()
        state = settings.value("mcp/garde_fou_splitter_state")
        restored = False
        if state is not None:
            restored = bool(self.splitter.restoreState(state))
        if not restored:
            self.splitter.setSizes([360, max(500, self.width() - 360)])

        self.splitter.splitterMoved.connect(self._on_splitter_moved)

    def _on_splitter_moved(self, pos: int, index: int) -> None:
        """Sauvegarde automatiquement l'état géométrique du séparateur dans QSettings."""
        settings = get_app_qsettings()
        settings.setValue("mcp/garde_fou_splitter_state", self.splitter.saveState())

    def _set_status_filter(self, value: str) -> None:
        """Définit le filtre de statut actif et recharge la file en conséquence."""
        self._current_status_filter = value
        for chip in self._status_chips:
            chip.setChecked(chip is self._chip_for(value))
        self.reload_pending_patches()

    def _chip_for(self, value: str) -> FilterChipButton:
        """Retourne le chip associé à une valeur de filtre."""
        return {"pending": self.chip_pending, "aborted": self.chip_aborted, "all": self.chip_all}[value]

    def reload_pending_patches(self) -> None:
        """Recharge l'arborescence complète des bundles et propositions en attente."""
        # Sauvegarder l'état avant la recharge complète
        tree_state = self._save_tree_state()

        prev_patch_id = self.current_patch_id
        prev_row = self.patch_tree.currentRow()

        self.patch_tree.blockSignals(True)
        self.patch_tree.clear()
        self.patch_tree.reset_selectable_items()

        self._patches.clear()
        self._notified_patch_ids.clear()
        selected_item: QTreeWidgetItem | None = None

        # 1. Chargement des Staged Bundles selon le filtre de statut actif
        if self._current_status_filter == "aborted":
            target_statuses = ["aborted"]
        elif self._current_status_filter == "all":
            target_statuses = ["pending", "partial", "aborted"]
        else:
            target_statuses = ["pending", "partial"]

        bundles = list(StagedBundleModel.select().where(StagedBundleModel.status.in_(target_statuses)).order_by(StagedBundleModel.created_at.asc()))

        for bundle in bundles:
            bundle_patches = list(bundle.patches.where(StagedPatchModel.status.in_(target_statuses)).order_by(StagedPatchModel.step_order.asc()))
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
                self._notified_patch_ids.add(patch.patch_id)
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
            StagedPatchModel.select().where(StagedPatchModel.bundle.is_null(True), StagedPatchModel.status.in_(target_statuses)).order_by(StagedPatchModel.created_at.asc(), StagedPatchModel.id.asc())
        )

        for patch in standalone_patches:
            self._patches.append(patch)
            self._notified_patch_ids.add(patch.patch_id)
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

        # Restaurer l'état de l'arbre
        self._restore_tree_state(tree_state)

        # Mise à jour des compteurs et états
        total_count = len(self._patches)
        self.badge_count.setText(str(total_count))
        self.badge_count.set_variant("accent" if total_count else "neutral")

        self._update_filter_chip_labels()

        # Adapter la barre d'actions globales selon le filtre
        if self._current_status_filter == "aborted":
            self.btn_apply_all.setVisible(False)
            self.btn_reject_all.setVisible(False)
            self.lbl_batch_hint.setVisible(True)
            self.lbl_batch_hint.setText(tr("Historique en lecture seule"))
        else:
            self.btn_apply_all.setVisible(True)
            self.btn_reject_all.setVisible(True)
            self.lbl_batch_hint.setVisible(False)

        if not self._patches:
            self._current_patch = None
            self.detail_stack.setCurrentIndex(0)
            if self._current_status_filter == "aborted":
                self.empty_view.title_lbl.setText(tr("Aucune proposition annulée"))
                self.empty_view.desc_lbl.setText(tr("L'historique des propositions d'assistants IA annulées ou rejetées est vide."))
                self.empty_view.icon_lbl.setPixmap(load_phosphor_icon("ph.prohibit", color=DesignTokens.TEXT_MUTED).pixmap(48, 48))
            elif self._current_status_filter == "all":
                self.empty_view.title_lbl.setText(tr("Aucune proposition"))
                self.empty_view.desc_lbl.setText(tr("Aucune proposition d'assistant IA (en attente ou annulée) n'a encore été enregistrée."))
                self.empty_view.icon_lbl.setPixmap(load_phosphor_icon("ph.tray", color=DesignTokens.TEXT_MUTED).pixmap(48, 48))
            else:
                self.empty_view.title_lbl.setText(tr("Garde-Fou au repos"))
                self.empty_view.desc_lbl.setText(tr("Toutes les propositions d'agents IA ont été traitées.\nVotre collection Anki est parfaitement synchronisée et protégée."))
                self.empty_view.icon_lbl.setPixmap(load_phosphor_icon("ph.shield-check", color=DesignTokens.TEXT_MUTED).pixmap(48, 48))

            self.btn_apply_all.setEnabled(False)
            self.btn_reject_all.setEnabled(False)
            self.btn_apply_all.setToolTip(tr("Aucune proposition en attente à traiter."))
            self.btn_reject_all.setToolTip(tr("Aucune proposition en attente à traiter."))
        else:
            self.btn_apply_all.setEnabled(True)
            self.btn_reject_all.setEnabled(True)
            self.btn_apply_all.setToolTip(tr("Valider l'ensemble des %1 proposition(s) en attente.", total_count))
            self.btn_reject_all.setToolTip(tr("Rejeter l'ensemble des %1 proposition(s) en attente.", total_count))
            if selected_item is not None:
                self.patch_tree.setCurrentItem(selected_item)
            else:
                target_row = max(0, min(prev_row, total_count - 1)) if prev_row >= 0 else 0
                self.patch_tree.setCurrentRow(target_row)

        self.queue_updated.emit(total_count)

    def _update_filter_chip_labels(self) -> None:
        """Met à jour les libellés des puces de filtrage avec les compteurs correspondants."""
        try:
            pending_count = StagedPatchModel.select().where(StagedPatchModel.status.in_(["pending", "partial"])).count()
            aborted_count = StagedPatchModel.select().where(StagedPatchModel.status == "aborted").count()
            total_count = pending_count + aborted_count
            self.chip_pending.setText(tr("Attente (%1)", pending_count))
            self.chip_aborted.setText(tr("Annulés (%1)", aborted_count))
            self.chip_all.setText(tr("Tous (%1)", total_count))
        except Exception as e:
            logger.debug(f"Impossible d'actualiser les compteurs de filtres : {e}")

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
                "Lot : « %1 » • Étape %2 sur %3 • Réf. %4",
                patch.bundle.title or tr("Sans titre"),
                patch.step_order,
                patch.bundle.total_steps,
                patch.patch_id[:8],
            )
            self.btn_apply.setText(tr("Valider cette étape"))
            self.btn_apply.setToolTip(tr("Valider cette étape (Ctrl+Entrée)"))
            self.btn_apply.setIcon(load_on_accent_icon("ph.check"))
            self.btn_apply.setStyleSheet("")
            self.btn_reject.setText(tr("Rejeter la suite du bloc"))
            self.btn_reject.setToolTip(tr("Interrompre et rejeter la suite du bloc (Suppr)"))
            self.btn_apply_bundle_all.setVisible(True)
        else:
            title = str(payload.get("title") or tr("Proposition — %1 #%2", patch.patch_type, patch.target_id))
            meta_str = tr("Réf. %1 • Type : %2", patch.patch_id[:8], patch.patch_type.upper())
            if patch.target_id:
                meta_str += tr(" • Note ciblée #%1", patch.target_id)

            # Adaptation sémantique, visuelle et sécuritaire selon le type d'opération
            if p_type in ("card_delete", "deck_delete", "delete_empty_cards", "empty_cards_delete", "note_delete", "batch_card_deletion", "batch_note_delete"):
                self.btn_apply.setText(tr("Confirmer la suppression"))
                self.btn_apply.setToolTip(tr("Confirmer la destruction définitive (Ctrl+Entrée)"))
                self.btn_apply.setIcon(load_phosphor_icon("ph.trash", color="#ffffff"))
                self.btn_apply.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {DesignTokens.COLOR_RED};
                        color: #ffffff;
                        border: 1px solid {DesignTokens.COLOR_RED};
                        border-radius: 6px;
                        font-weight: 600;
                        padding: 0 16px;
                    }}
                    QPushButton:hover {{
                        background-color: {DesignTokens.COLOR_RED_TEXT};
                    }}
                """)
            elif p_type in ("note_create", "batch_note_create"):
                self.btn_apply.setText(tr("Créer la carte"))
                self.btn_apply.setToolTip(tr("Valider et créer la carte dans la collection (Ctrl+Entrée)"))
                self.btn_apply.setIcon(load_on_accent_icon("ph.plus-circle"))
                self.btn_apply.setStyleSheet("")
            elif p_type in ("deck_create", "create_deck", "deck_rename", "rename_deck"):
                self.btn_apply.setText(tr("Appliquer au paquet"))
                self.btn_apply.setToolTip(tr("Valider l'opération sur le paquet (Ctrl+Entrée)"))
                self.btn_apply.setIcon(load_on_accent_icon("ph.folder-check"))
                self.btn_apply.setStyleSheet("")
            elif p_type in ("set_tags", "set_tags_bulk", "tag_add", "tag_remove", "tags") or (isinstance(payload, dict) and ("tags_added" in payload or "tags_removed" in payload)):
                self.btn_apply.setText(tr("Enregistrer les tags"))
                self.btn_apply.setToolTip(tr("Appliquer les modifications d'étiquettes (Ctrl+Entrée)"))
                self.btn_apply.setIcon(load_on_accent_icon("ph.tag-chevron"))
                self.btn_apply.setStyleSheet("")
            else:
                self.btn_apply.setText(tr("Valider la modification"))
                self.btn_apply.setToolTip(tr("Valider la modification (Ctrl+Entrée)"))
                self.btn_apply.setIcon(load_on_accent_icon("ph.check"))
                self.btn_apply.setStyleSheet("")

            self.btn_reject.setText(tr("Rejeter la proposition"))
            self.btn_reject.setToolTip(tr("Rejeter la proposition (Suppr)"))
            self.btn_apply_bundle_all.setVisible(False)

        is_aborted = patch.status == "aborted"
        if is_aborted:
            self.btn_apply.setEnabled(False)
            self.btn_reject.setEnabled(False)
            self.btn_apply.setVisible(False)
            self.btn_reject.setVisible(False)
            self.btn_apply_bundle_all.setVisible(False)
            self.btn_restore_patch.setVisible(True)

            reason_str = patch.reason or tr("Annulé par l'assistant IA lors de la phase de révision.")
            self.lbl_abort_banner_desc.setText(tr("Motif : %1", reason_str))
            self.abort_banner.setVisible(True)
            self.lbl_abort_reason.setText(tr("Annulé : %1", reason_str))
            self.lbl_abort_reason.show()
            self.badge_abort_status.show()
        else:
            self.btn_apply.setEnabled(True)
            self.btn_reject.setEnabled(True)
            self.btn_apply.setVisible(True)
            self.btn_reject.setVisible(True)
            self.btn_restore_patch.setVisible(False)
            self.abort_banner.setVisible(False)
            self.lbl_abort_reason.hide()
            self.badge_abort_status.hide()

        self.lbl_detail_title.setText(title)
        self.lbl_detail_meta.setText(meta_str)

        # Routage vers la page polymorphe du QStackedWidget
        if p_type in ("note_create", "batch_note_create"):
            self.polymorphic_stack.setCurrentIndex(4)
            self.create_view.set_patch(patch)
        elif p_type in ("note_type_create", "note_type_refactor", "note_type_change", "propose_note_type_refactor"):
            self.polymorphic_stack.setCurrentIndex(5)
            self.note_type_view.set_patch(patch)
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
        idx = self.polymorphic_stack.currentIndex()
        if idx == 0:
            return self.diff_viewer.get_modified_content()
        elif idx == 1:
            return self.deck_view.get_modified_content()
        elif idx == 2:
            return self.tag_view.get_modified_content()
        elif idx == 3:
            return self.deletion_view.get_modified_content()
        elif idx == 4:
            return self.create_view.get_modified_content()
        elif idx == 5:
            return self.note_type_view.get_modified_content()
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

        # 1. Synchronisation de l'édition directe (uniquement pour les modifications, pas les créations ni lots bruts)
        p_type = getattr(self._current_patch, "patch_type", "")
        if p_type not in ("note_create", "batch_note_create", "batch_create"):
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

    def _restore_current_patch(self) -> None:
        """Rétablit une proposition annulée en statut 'pending' pour révision ou application."""
        if not self._current_patch:
            return

        patch_id = self._current_patch.patch_id
        self._current_patch.status = "pending"
        self._current_patch.save()

        if self._current_patch.bundle and self._current_patch.bundle.status == "aborted":
            self._current_patch.bundle.status = "pending"
            self._current_patch.bundle.save()

        show_toast(self, tr("Proposition %1 rétablie en attente !", patch_id[:8]), level="success")
        self.reload_pending_patches()

    def _apply_bundle_all(self) -> None:
        """Applique l'intégralité du bundle en une transaction atomique unique."""
        if not self._current_patch or not self._current_patch.bundle:
            return

        bundle_id = self._current_patch.bundle.bundle_id

        # Synchronisation de l'édition directe de l'étape active avant l'application globale (sauf créations et lots bruts)
        p_type = getattr(self._current_patch, "patch_type", "")
        if p_type not in ("note_create", "batch_note_create", "batch_create"):
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

        if not getattr(self, "_skip_confirm_for_test", False) and self.isVisible():
            reply = QMessageBox.question(
                self,
                tr("Confirmation de rejet groupé"),
                tr(
                    "Voulez-vous vraiment rejeter l'ensemble des %1 proposition(s) en attente ?\nCette action est irréversible.",
                    len(self._patches),
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
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
        """Copie une synthèse d'arbitrage dans le presse-papier pour l'assistant IA."""
        if not self._current_patch:
            return

        p = self._current_patch
        payload = staged_payload_of(p)
        feedback_lines = [
            tr("[AnkiForge] Compte-rendu d'arbitrage utilisateur :"),
            f"- Réf. : {p.patch_id}",
            f"- Cible : Note #{p.target_id} (Type: {p.patch_type})",
            f"- Titre : {payload.get('title', '')}",
            tr("- Statut d'arbitrage : Validé avec retouches / En attente de révision"),
            tr("- Directives complémentaires : Merci d'affiner la concision selon les 20 règles de Wozniak."),
        ]
        text = "\n".join(feedback_lines)
        QGuiApplication.clipboard().setText(text)
        show_toast(self, tr("Compte-rendu copié dans le presse-papier"), level="success")

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
        if hasattr(self, "abort_banner"):
            color_yellow_bg = getattr(profile, "color_yellow_bg", DesignTokens.COLOR_YELLOW_BG)
            color_yellow_border = getattr(profile, "color_yellow_border", DesignTokens.COLOR_YELLOW_BORDER)
            self.abort_banner.setStyleSheet(f"""
                QFrame#mcp_gf_abort_banner {{
                    background-color: {color_yellow_bg};
                    border: 1px solid {color_yellow_border};
                    border-radius: {DesignTokens.RADIUS_SM}px;
                    padding: 10px 14px;
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
        if hasattr(self, "create_view") and hasattr(self.create_view, "refresh_theme"):
            self.create_view.refresh_theme(profile)
        if hasattr(self, "note_type_view") and hasattr(self.note_type_view, "refresh_theme"):
            self.note_type_view.refresh_theme(profile)

    def cleanup(self) -> None:
        """Arrête les chargements Chromium et libère les ressources WebEngine."""
        if hasattr(self, "diff_viewer") and hasattr(self.diff_viewer, "cleanup"):
            self.diff_viewer.cleanup()
        if hasattr(self, "create_view") and hasattr(self.create_view, "cleanup"):
            self.create_view.cleanup()
        if hasattr(self, "deletion_view") and hasattr(self.deletion_view, "cleanup"):
            self.deletion_view.cleanup()
        if hasattr(self, "note_type_view") and hasattr(self.note_type_view, "cleanup"):
            self.note_type_view.cleanup()
