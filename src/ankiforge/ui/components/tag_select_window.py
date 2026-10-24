"""Fenêtre de sélection et gestionnaire de taxonomie des tags.

Prend en charge :
- Le mode sélecteur simple (sélection et insertion de tags).
- Le mode gestionnaire complet de taxonomie (renommage hiérarchique avec propagation contrôlée,
  fusion de tags, suppression globale, audit de conformité et garde-fous de provenance).
Conforme à l'ADR 0039, ADR 0040, GEMINI.md Règles 2, 7, 8, 18, 19 et 20 et DESIGN.md.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QAction, QColor, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import NoteModel
from ankiforge.repositories.note_repository import NoteRepository
from ankiforge.services.cards.bulk_hygiene_service import BulkHygieneService, TagMergePlan
from ankiforge.services.cards.taxonomy_service import TaxonomyService
from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens, StyledMenu
from ankiforge.utils.hierarchy import join_hierarchy, split_hierarchy
from ankiforge.utils.i18n import tr
from ankiforge.utils.icon_loader import load_phosphor_icon
from ankiforge.utils.tags import is_provenance_tag, normalize_tag_input, parse_note_tags

logger = logging.getLogger(__name__)


class TagSelectWindow(QWidget):
    """Fenêtre de sélection et gestionnaire de Taxonomie des tags."""

    tag_selected = Signal(str)  # (tag_name)
    taxonomy_mutated = Signal()  # émis lors d'un renommage, fusion ou suppression

    def __init__(
        self,
        title: str | None = None,
        allowed_tags: Sequence[str] | set[str] | None = None,
        show_provenance_toggle: bool = True,
        mode: str = "select",  # "select" ou "manage"
        deck_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        self.raw_allowed_tags = list(allowed_tags) if allowed_tags is not None else None
        self.allowed_tags = set(allowed_tags) if allowed_tags is not None else None
        self.mode = mode
        self.deck_id = deck_id
        super().__init__(parent)

        default_title = self.tr("Gestionnaire de Taxonomie des Tags") if mode == "manage" else self.tr("Sélectionner ou Ajouter un Tag")
        self.setWindowTitle(title or default_title)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        if mode == "manage":
            self.setMinimumSize(540, 600)
            self.resize(560, 620)
        else:
            self.setFixedSize(460, 530)

        self.setStyleSheet(f"""
            QWidget {{
                background-color: {DesignTokens.BG_PANEL};
            }}
        """)

        self.setWindowFlags(Qt.WindowType.Dialog if parent else Qt.WindowType.Window)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Search Bar
        self.search_input = QLineEdit()
        placeholder = self.tr("Filtrer l'arborescence des tags...") if mode == "manage" else self.tr("Rechercher ou saisir un nouveau tag...")
        self.search_input.setPlaceholderText(placeholder)
        search_icon = load_phosphor_icon("magnifying-glass", color=DesignTokens.TEXT_MUTED)
        self.search_input.addAction(search_icon, QLineEdit.ActionPosition.LeadingPosition)
        self.search_input.setFixedHeight(32)

        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                padding: 0 10px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 12px;
                font-family: '{DesignTokens.FONT_MAIN}';
            }}
            QLineEdit:focus {{
                border: 1px solid {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        self.search_input.textChanged.connect(self._on_search_changed)
        layout.addWidget(self.search_input)

        # Options barre : Afficher les tags de traçabilité
        top_opts = QHBoxLayout()
        top_opts.setSpacing(10)

        self.cb_show_provenance = QCheckBox(self.tr("Afficher les tags de traçabilité"))
        self.cb_show_provenance.setChecked(False)
        self.cb_show_provenance.setVisible(show_provenance_toggle)
        self.cb_show_provenance.setStyleSheet(f"""
            QCheckBox {{
                color: {DesignTokens.TEXT_MUTED};
                font-size: 11px;
                font-family: '{DesignTokens.FONT_MAIN}';
                spacing: 6px;
            }}
            QCheckBox:hover {{
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)
        self.cb_show_provenance.toggled.connect(self._load_tags)
        top_opts.addWidget(self.cb_show_provenance)

        top_opts.addStretch()

        if self.mode == "manage":
            lbl_help = QLabel(self.tr("Clic droit sur un tag pour le renommer, fusionner ou supprimer."))
            lbl_help.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-style: italic;")
            top_opts.addWidget(lbl_help)

        layout.addLayout(top_opts)

        # TreeWidget
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setExpandsOnDoubleClick(True)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)

        palette = self.tree.palette()
        palette.setColor(QPalette.ColorRole.Highlight, QColor(0, 0, 0, 0))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(DesignTokens.ACCENT_PRIMARY))
        self.tree.setPalette(palette)

        self.tree.setStyleSheet(f"""
            QTreeWidget {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 13px;
                font-family: '{DesignTokens.FONT_MAIN}';
                show-decoration-selected: 1;
                outline: none;
            }}
            QTreeWidget::item {{
                padding: 6px 4px;
                border: none;
            }}
            QTreeWidget::item:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
            QTreeWidget::item:selected {{
                font-weight: bold;
            }}
        """)
        layout.addWidget(self.tree)

        # Footer
        footer = QWidget()
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.setSpacing(8)

        if self.mode == "manage":
            self.btn_audit = SecondaryButton(self.tr("Auditer la taxonomie..."))
            self.btn_audit.clicked.connect(self._open_audit_dialog)
            footer_layout.addWidget(self.btn_audit)

            footer_layout.addStretch()

            btn_close = PrimaryButton(self.tr("Fermer"))
            btn_close.clicked.connect(self.close)
            footer_layout.addWidget(btn_close)
        else:
            btn_cancel = SecondaryButton(self.tr("Annuler"))
            btn_cancel.clicked.connect(self.close)

            self.btn_confirm = PrimaryButton(self.tr("Valider ce tag"))
            self.btn_confirm.clicked.connect(self._on_confirm)
            self.btn_confirm.setEnabled(False)

            footer_layout.addStretch()
            footer_layout.addWidget(btn_cancel)
            footer_layout.addWidget(self.btn_confirm)

        layout.addWidget(footer)

        self.tree.itemSelectionChanged.connect(self._on_selection_changed)
        if self.mode == "select":
            self.tree.itemDoubleClicked.connect(self._on_confirm)

        self._items_by_path: dict[str, QTreeWidgetItem] = {}
        self._load_tags()

    def _load_tags(self) -> None:
        """Charge l'arborescence des tags depuis la base ou la liste autorisée."""
        self.tree.clear()
        self._items_by_path.clear()

        all_tags: set[str] = set()
        if self.raw_allowed_tags is not None:
            for t in self.raw_allowed_tags:
                all_tags.update(parse_note_tags(t))
        elif self.deck_id is not None:
            all_tags.update(NoteRepository().get_tags_for_scope(deck_id=self.deck_id))
        else:
            for note in NoteModel.select(NoteModel.tags).where(NoteModel.tags.is_null(False)):
                if note.tags:
                    all_tags.update(parse_note_tags(note.tags))

        # Filtrage des tags de traçabilité documentaire si la case n'est pas cochée
        show_prov = self.cb_show_provenance.isChecked() if hasattr(self, "cb_show_provenance") else True
        filtered_tags = {t for t in all_tags if show_prov or not is_provenance_tag(t)}

        sorted_tags = sorted(list(filtered_tags))

        for tag in sorted_tags:
            parts = split_hierarchy(tag)
            parent_item = None

            for i in range(1, len(parts)):
                parent_path = join_hierarchy(parts[:i])
                if parent_path in self._items_by_path:
                    parent_item = self._items_by_path[parent_path]
                else:
                    new_item = QTreeWidgetItem(parent_item, [parts[i - 1]]) if parent_item else QTreeWidgetItem(self.tree, [parts[i - 1]])
                    new_item.setData(0, Qt.ItemDataRole.UserRole, parent_path)
                    new_item.setIcon(0, load_phosphor_icon("tag", color=DesignTokens.ACCENT_PRIMARY))
                    self._items_by_path[parent_path] = new_item
                    parent_item = new_item

            node_name = parts[-1]
            item = QTreeWidgetItem(parent_item, [node_name]) if parent_item else QTreeWidgetItem(self.tree, [node_name])
            item.setData(0, Qt.ItemDataRole.UserRole, tag)
            if is_provenance_tag(tag):
                item.setIcon(0, load_phosphor_icon("file-text", color=DesignTokens.COLOR_PURPLE))
            else:
                item.setIcon(0, load_phosphor_icon("tag", color=DesignTokens.ACCENT_PRIMARY))
            self._items_by_path[tag] = item

        self.tree.expandAll()
        if hasattr(self, "search_input") and self.search_input.text().strip():
            self._on_search_changed(self.search_input.text())

    def _on_search_changed(self, text: str) -> None:
        """Filtre l'arborescence."""
        query = text.lower().strip()

        if hasattr(self, "btn_confirm"):
            if query:
                self.btn_confirm.setEnabled(True)
            else:
                self.btn_confirm.setEnabled(len(self.tree.selectedItems()) > 0)

        if not query:
            for i in range(self.tree.topLevelItemCount()):
                item = self.tree.topLevelItem(i)
                if item:
                    self._set_item_visibility_recursive(item, True)
            return

        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item:
                self._set_item_visibility_recursive(item, False)

        for path, item in self._items_by_path.items():
            if query in path.lower() or query in item.text(0).lower():
                item.setHidden(False)
                parent = item.parent()
                while parent:
                    parent.setHidden(False)
                    parent.setExpanded(True)
                    parent = parent.parent()

    def _set_item_visibility_recursive(self, item: QTreeWidgetItem, visible: bool) -> None:
        item.setHidden(not visible)
        for i in range(item.childCount()):
            child = item.child(i)
            if child:
                self._set_item_visibility_recursive(child, visible)

    def _on_selection_changed(self) -> None:
        selected = self.tree.selectedItems()
        if selected:
            tag = selected[0].data(0, Qt.ItemDataRole.UserRole)
            if self.mode == "select":
                self.search_input.setText(tag)
        if hasattr(self, "btn_confirm"):
            self.btn_confirm.setEnabled(len(self.search_input.text().strip()) > 0)

    def _on_confirm(self) -> None:
        tag = self.search_input.text().strip()
        if tag:
            self.tag_selected.emit(tag)
            self.close()

    def _show_context_menu(self, pos: QPoint) -> None:
        """Affiche le menu contextuel sur un tag de l'arborescence."""
        item = self.tree.itemAt(pos)
        tag = item.data(0, Qt.ItemDataRole.UserRole) if item else None

        menu = StyledMenu(self)

        if tag:
            act_rename = QAction(load_phosphor_icon("pencil-simple", color=DesignTokens.TEXT_PRIMARY), self.tr("Renommer ce tag..."), self)
            act_rename.triggered.connect(lambda: self._execute_rename(tag))
            menu.addAction(act_rename)

            act_merge = QAction(load_phosphor_icon("git-merge", color=DesignTokens.TEXT_PRIMARY), self.tr("Fusionner avec un autre tag..."), self)
            act_merge.triggered.connect(lambda: self._execute_merge(tag))
            menu.addAction(act_merge)

            act_delete = QAction(load_phosphor_icon("trash", color=DesignTokens.COLOR_RED_TEXT), self.tr("Supprimer de la collection..."), self)
            act_delete.triggered.connect(lambda: self._execute_delete(tag))
            menu.addAction(act_delete)

            menu.addSeparator()

        act_audit = QAction(load_phosphor_icon("shield-check", color=DesignTokens.ACCENT_PRIMARY), self.tr("Auditer la conformité de la taxonomie..."), self)
        act_audit.triggered.connect(self._open_audit_dialog)
        menu.addAction(act_audit)

        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _get_rename_inputs(self, old_tag: str) -> tuple[str, bool] | None:
        """Ouvre un dialogue demandant le nouveau nom et l'option de propagation avec décompte."""
        has_subtags = any(p.startswith(f"{old_tag}::") for p in self._items_by_path if p != old_tag)
        counts = NoteRepository().get_tags_with_counts(self.deck_id)
        direct_count = counts.get(old_tag, 0)
        sub_tags = [p for p in self._items_by_path if p.startswith(f"{old_tag}::")]
        total_count = direct_count + sum(counts.get(st, 0) for st in sub_tags)

        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr("Renommer le tag"))
        dialog.setFixedWidth(420)
        d_layout = QVBoxLayout(dialog)
        d_layout.setSpacing(10)

        lbl = QLabel(tr("Nouveau nom pour « %1 » (%2 note%3) :", old_tag, direct_count, "s" if direct_count > 1 else ""))
        d_layout.addWidget(lbl)

        line_edit = QLineEdit(old_tag)
        d_layout.addWidget(line_edit)

        cb_label = tr("Propager à la sous-arborescence (%1 sous-tag%2, %3 note%4)", len(sub_tags), "s" if len(sub_tags) > 1 else "", total_count, "s" if total_count > 1 else "")
        cb_propagate = QCheckBox(cb_label)
        cb_propagate.setChecked(True)
        cb_propagate.setVisible(has_subtags)
        d_layout.addWidget(cb_propagate)

        btns = QHBoxLayout()
        btn_cancel = SecondaryButton(self.tr("Annuler"))
        btn_cancel.clicked.connect(dialog.reject)
        btn_ok = PrimaryButton(self.tr("Renommer"))
        btn_ok.clicked.connect(dialog.accept)
        btns.addStretch()
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_ok)
        d_layout.addLayout(btns)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_name = line_edit.text().strip()
            if new_name and new_name != old_tag:
                return new_name, cb_propagate.isChecked()
        return None

    def _confirm_rename(self, old_tag: str, new_name: str, notes_count: int) -> bool:
        """Demande confirmation avant l'application du renommage."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(self.tr("Confirmer le renommage"))
        box.setText(tr("Renommer « %1 » en « %2 » va modifier %3 note%4. Continuer ?", old_tag, new_name, notes_count, "s" if notes_count > 1 else ""))
        btn_ok = box.addButton(self.tr("Renommer"), QMessageBox.ButtonRole.AcceptRole)
        btn_cancel = box.addButton(self.tr("Annuler"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(btn_cancel)
        box.exec()
        return box.clickedButton() == btn_ok

    def _confirm_provenance_risk(self, tag: str, action_desc: str) -> bool:
        """Avertissement critique niveau 2 pour les tags de provenance."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(self.tr("Garde-Fou de Provenance Documentaire"))
        box.setText(tr("Attention : « %1 » est un tag de traçabilité documentaire (RAG).", tag))
        box.setInformativeText(
            tr(
                "Le %1 de ce tag risque de délier les cartes de leurs sources et de recalculer leur couverture.\n\nVoulez-vous vraiment continuer ?",
                action_desc,
            )
        )
        btn_confirm = box.addButton(self.tr("Confirmer malgré le risque"), QMessageBox.ButtonRole.AcceptRole)
        btn_cancel = box.addButton(self.tr("Annuler"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(btn_cancel)
        box.exec()
        return box.clickedButton() == btn_confirm

    def _execute_rename(self, old_tag: str) -> None:
        """Renomme un tag et ses sous-arborescences avec dialogue et garde-fous."""
        inputs = self._get_rename_inputs(old_tag)
        if not inputs:
            return
        new_name, propagate = inputs

        is_prov = is_provenance_tag(old_tag)
        if is_prov and not self._confirm_provenance_risk(old_tag, "renommage"):
            return

        counts = NoteRepository().get_tags_with_counts(self.deck_id)
        if propagate:
            sub_tags = [p for p in self._items_by_path if p.startswith(f"{old_tag}::")]
            impacted = counts.get(old_tag, 0) + sum(counts.get(st, 0) for st in sub_tags)
        else:
            impacted = counts.get(old_tag, 0)

        if not self._confirm_rename(old_tag, new_name, impacted):
            return

        res = TaxonomyService.rename_tag(
            old_tag=old_tag,
            new_tag=new_name,
            propagate_subtags=propagate,
            deck_id=self.deck_id,
            allow_provenance=is_prov,
        )

        if res.success:
            self._load_tags()
            self.taxonomy_mutated.emit()
        else:
            QMessageBox.critical(
                self,
                self.tr("Échec du renommage"),
                tr("Une erreur est survenue :\n%1", res.error_message or ""),
            )

    def _confirm_delete(self, tag: str, notes_count: int) -> bool:
        """Demande confirmation pour la suppression globale d'un tag."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(self.tr("Supprimer le tag"))
        box.setText(tr("Voulez-vous supprimer le tag « %1 » sur %2 note(s) ?", tag, notes_count))
        btn_del = box.addButton(self.tr("Supprimer"), QMessageBox.ButtonRole.AcceptRole)
        btn_cancel = box.addButton(self.tr("Annuler"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(btn_cancel)
        box.exec()
        return box.clickedButton() == btn_del

    def _execute_delete(self, tag: str) -> None:
        """Supprime un tag sur l'ensemble de la portée."""
        counts = NoteRepository().get_tags_with_counts(self.deck_id)
        notes_count = counts.get(tag, 0)

        is_prov = is_provenance_tag(tag)
        if is_prov and not self._confirm_provenance_risk(tag, "la suppression"):
            return

        if not self._confirm_delete(tag, notes_count):
            return

        has_subtags = any(p.startswith(f"{tag}::") for p in self._items_by_path if p != tag)
        delete_subtags = False
        if has_subtags:
            rep = QMessageBox.question(
                self,
                self.tr("Sous-tags détectés"),
                self.tr("Ce tag possède des sous-tags. Voulez-vous aussi supprimer toute sa sous-arborescence ?"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            delete_subtags = rep == QMessageBox.StandardButton.Yes

        res = TaxonomyService.delete_tag(
            tag=tag,
            delete_subtags=delete_subtags,
            deck_id=self.deck_id,
            allow_provenance=is_prov,
        )

        if res.success:
            self._load_tags()
            self.taxonomy_mutated.emit()
        else:
            QMessageBox.critical(
                self,
                self.tr("Échec de la suppression"),
                tr("Une erreur est survenue :\n%1", res.error_message or ""),
            )

    def _confirm_merge(self, source_tag: str, target_tag: str, count: int) -> bool:
        """Demande confirmation avant l'application d'une fusion."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(self.tr("Confirmer la fusion"))
        box.setText(tr("Voulez-vous fusionner « %1 » vers « %2 » sur %3 note%4 ?", source_tag, target_tag, count, "s" if count > 1 else ""))
        btn_merge = box.addButton(self.tr("Fusionner"), QMessageBox.ButtonRole.AcceptRole)
        btn_cancel = box.addButton(self.tr("Annuler"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(btn_cancel)
        box.exec()
        return box.clickedButton() == btn_merge

    def _execute_merge(self, source_tag: str) -> None:
        """Fusionne le tag sélectionné vers un tag cible avec garde-fous."""
        is_prov = is_provenance_tag(source_tag)
        if is_prov and not self._confirm_provenance_risk(source_tag, "la fusion"):
            return

        all_tags = sorted([t for t in self._items_by_path if t != source_tag])
        target_tag, ok = QInputDialog.getItem(
            self,
            self.tr("Fusionner le tag"),
            tr("Sélectionner le tag cible dans lequel fusionner « %1 » :", source_tag),
            all_tags,
            0,
            True,
        )
        if not ok or not target_tag.strip():
            return

        clean_target = normalize_tag_input(target_tag)
        if clean_target == source_tag:
            return

        counts = NoteRepository().get_tags_with_counts(self.deck_id)
        notes_count = counts.get(source_tag, 0)

        if not self._confirm_merge(source_tag, clean_target, notes_count):
            return

        plan = TagMergePlan(target_tag=clean_target, tags_to_merge=[source_tag])
        res = BulkHygieneService.apply_tag_merges([plan], deck_id=self.deck_id)
        if res.success:
            self._load_tags()
            self.taxonomy_mutated.emit()
        else:
            QMessageBox.critical(
                self,
                self.tr("Échec de la fusion"),
                tr("Une erreur est survenue :\n%1", res.error_message or ""),
            )

    def _open_audit_dialog(self) -> None:
        """Ouvre le dialogue modal d'audit de conformité de taxonomie."""
        from ankiforge.ui.dialogs.taxonomy_audit_dialog import TaxonomyAuditDialog

        dlg = TaxonomyAuditDialog(deck_id=self.deck_id, parent=self)
        dlg.exec()
        self._load_tags()
        self.taxonomy_mutated.emit()
