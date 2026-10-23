"""Composant de sélection de modèle de carte (NoteType).

Reproduit le pattern architectural de `deck_select_window.py` et `tag_select_window.py`.
"""

from __future__ import annotations

import json
import logging
from typing import Any, cast

from peewee import fn
from PySide6.QtCore import QEvent, QPoint, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QKeyEvent, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QInputDialog,
    QLineEdit,
    QMenu,
    QMessageBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import NoteModel, NoteTypeModel
from ankiforge.services.settings_service import SettingsService
from ankiforge.ui.components.buttons import IconButton, PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.i18n import tr
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class ModelSelectWindow(QWidget):
    """Fenêtre modale de sélection de modèle de carte (NoteType) avec recherche instantanée et prévisualisation des champs et du volume de notes."""

    model_selected = Signal(int, str)  # (model_id, model_name)

    def __init__(
        self,
        title: str = "Sélectionner un type de note",
        allow_all: bool = True,
        current_model_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.allow_all = allow_all
        self.current_model_id = current_model_id
        self._items_by_id: dict[int, QTreeWidgetItem] = {}
        self._model_cache: dict[int, NoteTypeModel] = {}
        self._sort_order: str = SettingsService.get("card_models/sort_order", "name_asc") or "name_asc"

        self.setWindowTitle(title)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setFixedSize(480, 520)

        self.setStyleSheet(f"""
            QWidget {{
                background-color: {DesignTokens.BG_PANEL};
            }}
        """)

        self.setWindowFlags(Qt.WindowType.Dialog if parent else Qt.WindowType.Window)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(14, 14, 14, 14)
        content_layout.setSpacing(12)

        # 1. Barre de recherche
        search_row = QHBoxLayout()
        search_row.setSpacing(6)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(self.tr("Rechercher un type de note (ex: Basique, Cloze, Front)..."))
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
        search_row.addWidget(self.search_input, 1)

        self.btn_sort_models = IconButton(
            "ph.funnel",
            tooltip=self.tr("Trier les types de note"),
            size=24,
        )
        self.btn_sort_models.setFixedHeight(32)
        self.btn_sort_models.clicked.connect(self._on_show_sort_menu)
        search_row.addWidget(self.btn_sort_models)
        content_layout.addLayout(search_row)

        # 2. Arborescence / Liste des modèles
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setExpandsOnDoubleClick(True)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_tree_context_menu)

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
                color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)

        content_layout.addWidget(self.tree)
        layout.addWidget(content)

        # 3. Footer d'actions
        footer = QWidget()
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.setSpacing(8)

        btn_cancel = SecondaryButton("Annuler")
        btn_cancel.clicked.connect(self.close)

        self.btn_confirm = PrimaryButton(self.tr("Valider ce type de note"))
        self.btn_confirm.clicked.connect(self._on_confirm)
        self.btn_confirm.setEnabled(False)

        footer_layout.addStretch()
        footer_layout.addWidget(btn_cancel)
        footer_layout.addWidget(self.btn_confirm)
        layout.addWidget(footer)

        self.tree.itemSelectionChanged.connect(self._on_selection_changed)
        self.tree.itemDoubleClicked.connect(self._on_confirm)

        # Installation des raccourcis et navigation clavier
        self.search_input.installEventFilter(self)
        self.tree.installEventFilter(self)

        self._load_models()

    def _get_sort_order(self) -> str:
        val = SettingsService.get("card_models/sort_order", "name_asc") or "name_asc"
        return str(val)

    def _set_sort_order(self, sort_order: str) -> None:
        self._sort_order = sort_order
        SettingsService.set("card_models/sort_order", sort_order, category="ui")
        self._load_models()

    def _on_show_sort_menu(self) -> None:
        menu = QMenu(self)
        group = QActionGroup(self)
        group.setExclusive(True)
        options = [
            ("name_asc", self.tr("Nom (A → Z)")),
            ("name_desc", self.tr("Nom (Z → A)")),
            ("created_desc", self.tr("Date de création (Plus récents)")),
            ("created_asc", self.tr("Date de création (Plus anciens)")),
            ("template_count_desc", self.tr("Nombre de gabarits / cartes")),
        ]
        current = self._get_sort_order()
        for key, label in options:
            action = QAction(label, menu)
            action.setCheckable(True)
            if key == current:
                action.setChecked(True)

            def _make_handler(sort_key: str) -> Any:
                def _handler(checked: bool = False) -> None:
                    self._set_sort_order(sort_key)

                return _handler

            action.triggered.connect(_make_handler(key))
            group.addAction(action)
            menu.addAction(action)
        menu.exec(self.btn_sort_models.mapToGlobal(self.btn_sort_models.rect().bottomLeft()))

    def _on_tree_context_menu(self, pos: QPoint) -> None:
        item = self.tree.itemAt(pos)
        if not item:
            return
        mid = item.data(0, Qt.ItemDataRole.UserRole)
        if mid == -1 or mid is None:
            return
        model = self._model_cache.get(int(mid))
        if not model:
            return
        menu = QMenu(self)

        def _rename(m: NoteTypeModel = model) -> None:
            self._on_rename_model(m)

        def _duplicate(m: NoteTypeModel = model) -> None:
            self._on_duplicate_model(m)

        def _set_default(m: NoteTypeModel = model) -> None:
            self._on_set_default_model(m)

        def _export(m: NoteTypeModel = model) -> None:
            self._on_export_json(m)

        def _delete(m: NoteTypeModel = model) -> None:
            self._on_delete_model(m)

        menu.addAction(self.tr("Renommer"), _rename)
        menu.addAction(self.tr("Dupliquer"), _duplicate)
        menu.addAction(self.tr("Définir comme modèle par défaut"), _set_default)
        menu.addAction(self.tr("Exporter (.afmodel / JSON)"), _export)
        menu.addAction(self.tr("Supprimer"), _delete)
        sort_menu = menu.addMenu(self.tr("Trier par..."))
        group = QActionGroup(self)
        group.setExclusive(True)
        options = [
            ("name_asc", self.tr("Nom (A → Z)")),
            ("name_desc", self.tr("Nom (Z → A)")),
            ("created_desc", self.tr("Date de création (Plus récents)")),
            ("created_asc", self.tr("Date de création (Plus anciens)")),
            ("template_count_desc", self.tr("Nombre de gabarits / cartes")),
        ]
        current = self._get_sort_order()
        for key, label in options:
            action = QAction(label, sort_menu)
            action.setCheckable(True)
            if key == current:
                action.setChecked(True)

            def _make_handler(sort_key: str) -> Any:
                def _handler(checked: bool = False) -> None:
                    self._set_sort_order(sort_key)

                return _handler

            action.triggered.connect(_make_handler(key))
            group.addAction(action)
            sort_menu.addAction(action)
        menu.exec(self.tree.mapToGlobal(pos))

    def _on_rename_model(self, model: NoteTypeModel) -> None:
        current_name = model.name or ""
        new_name, ok = QInputDialog.getText(self, self.tr("Renommer le type de note"), self.tr("Nouveau nom :"), text=current_name)
        if not ok:
            return
        new_name = new_name.strip()
        if not new_name or new_name == current_name:
            return
        if NoteTypeModel.get_or_none(NoteTypeModel.name == new_name):
            QMessageBox.warning(self, self.tr("Nom déjà utilisé"), self.tr("Un type de note avec ce nom existe déjà."))
            return
        model.name = new_name
        model.save()
        self._load_models()

    def _on_duplicate_model(self, model: NoteTypeModel) -> None:
        from ankiforge.services.cards.card_model_io import CardModelIO

        try:
            CardModelIO.duplicate(model)
            self._load_models()
        except Exception as e:
            logger.warning("Duplication depuis ModelSelectWindow échouée: %s", e)
            QMessageBox.warning(self, self.tr("Erreur"), str(e))

    def _on_set_default_model(self, model: NoteTypeModel) -> None:
        SettingsService.set("card_models/default_note_type_id", int(model.id), category="ui")
        self._load_models()

    def _on_export_json(self, model: NoteTypeModel) -> None:
        from ankiforge.ui.dialogs.model_export_dialog import ModelExportDialog

        dlg = ModelExportDialog(model, self)
        dlg.exec()

    def _on_delete_model(self, model: NoteTypeModel) -> None:
        res = QMessageBox.question(
            self,
            self.tr("Supprimer le type de note"),
            tr("Voulez-vous vraiment supprimer le type de note '%1' ?", model.name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if res != QMessageBox.StandardButton.Yes:
            return
        try:
            from ankiforge.services.cards.card_model_io import CardModelIO

            CardModelIO.delete_model(model)
            if self.current_model_id == model.id:
                self.current_model_id = None
            self._load_models()
        except Exception as e:
            logger.warning("Suppression depuis ModelSelectWindow échouée: %s", e)
            QMessageBox.warning(self, self.tr("Suppression impossible"), str(e))

    def _load_models(self) -> None:
        """Charge la liste des modèles de cartes depuis NoteTypeModel."""
        from ankiforge.ui.views.card_models_view.utils import sort_note_types

        self.tree.clear()
        self._items_by_id.clear()
        self._model_cache.clear()

        # Compter les notes associées à chaque modèle
        note_counts: dict[int, int] = {}
        try:
            note_counts = dict(NoteModel.select(NoteModel.note_type, fn.COUNT(NoteModel.id)).group_by(NoteModel.note_type).tuples())
        except Exception as ex:
            logger.warning("Impossible de charger le décompte des notes par modèle: %s", ex)

        # 0. Item racine "Tous les types de note" si allow_all=True
        if self.allow_all:
            global_item = QTreeWidgetItem([self.tr("Tous les types de note")])
            global_item.setData(0, Qt.ItemDataRole.UserRole, -1)
            global_item.setData(0, Qt.ItemDataRole.UserRole + 1, "Tous les types de note")
            global_item.setIcon(0, load_phosphor_icon("cards", color=DesignTokens.COLOR_BLUE))
            self.tree.addTopLevelItem(global_item)
            self._items_by_id[-1] = global_item

            if self.current_model_id is None or self.current_model_id == -1:
                self.tree.setCurrentItem(global_item)

        models = list(NoteTypeModel.select())
        sort_order = self._get_sort_order()
        models = sort_note_types(models, sort_order)

        for m in models:
            self._model_cache[m.id] = m

            # Analyse du schéma des champs
            fields: list[str] = []
            if m.fields_schema:
                try:
                    loaded = json.loads(str(m.fields_schema))
                    if isinstance(loaded, list):
                        fields = [str(f) for f in loaded]
                except Exception:
                    fields = ["Front", "Back"]

            notes_num = note_counts.get(m.id, 0)
            notes_str = f"({notes_num} note{'s' if notes_num != 1 else ''})"
            fields_str = f"{len(fields)} champ{'s' if len(fields) > 1 else ''} : {', '.join(fields)}"

            item = QTreeWidgetItem([tr("%1  %2", m.name, notes_str)])
            item.setData(0, Qt.ItemDataRole.UserRole, m.id)
            item.setData(0, Qt.ItemDataRole.UserRole + 1, m.name)
            item.setData(0, Qt.ItemDataRole.UserRole + 2, fields_str)
            item.setData(0, Qt.ItemDataRole.UserRole + 3, m.description or "")

            icon_color = DesignTokens.ACCENT_PRIMARY if "cloze" not in m.name.lower() else DesignTokens.COLOR_PURPLE
            item.setIcon(0, load_phosphor_icon("cards", color=icon_color))

            # Sous-élément présentant les champs
            child = QTreeWidgetItem([tr("↳ %1", fields_str)])
            child.setData(0, Qt.ItemDataRole.UserRole, m.id)
            child.setData(0, Qt.ItemDataRole.UserRole + 1, m.name)
            child.setForeground(0, QColor(DesignTokens.TEXT_MUTED))
            item.addChild(child)

            tooltip_lines = [tr("Type de note : %1", m.name), fields_str, notes_str]
            if m.description:
                tooltip_lines.append(f"Description: {m.description}")
            item.setToolTip(0, "\n".join(tooltip_lines))

            self.tree.addTopLevelItem(item)
            self._items_by_id[m.id] = item

            if self.current_model_id == m.id:
                self.tree.setCurrentItem(item)

        self.tree.expandAll()

    def _on_search_changed(self, text: str) -> None:
        """Filtre les modèles en direct par nom, description et champs."""
        query = text.lower().strip()

        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if not item:
                continue

            if not query:
                item.setHidden(False)
                for c_idx in range(item.childCount()):
                    c_item = item.child(c_idx)
                    if c_item:
                        c_item.setHidden(False)
                continue

            mid = item.data(0, Qt.ItemDataRole.UserRole)
            mname = str(item.data(0, Qt.ItemDataRole.UserRole + 1) or item.text(0)).lower()
            fields_str = str(item.data(0, Qt.ItemDataRole.UserRole + 2) or "").lower()
            desc_str = str(item.data(0, Qt.ItemDataRole.UserRole + 3) or "").lower()

            matches = (query in mname) or (query in fields_str) or (query in desc_str)

            if mid == -1 and (query in "tous" or query in "tous les modèles"):
                matches = True

            item.setHidden(not matches)
            for c_idx in range(item.childCount()):
                c_item = item.child(c_idx)
                if c_item:
                    c_item.setHidden(not matches)

    def _on_selection_changed(self) -> None:
        selected = self.tree.selectedItems()
        self.btn_confirm.setEnabled(len(selected) > 0)

    def _on_confirm(self) -> None:
        selected = self.tree.selectedItems()
        if not selected:
            return

        item = selected[0]
        model_id = item.data(0, Qt.ItemDataRole.UserRole)
        model_name = item.data(0, Qt.ItemDataRole.UserRole + 1) or item.text(0).split("  (")[0].strip()

        if model_id is not None:
            self.model_selected.emit(int(model_id), str(model_name))
            self.close()

    def get_selected_model(self) -> NoteTypeModel | None:
        """Retourne l'objet NoteTypeModel sélectionné ou None."""
        selected = self.tree.selectedItems()
        if not selected:
            return None
        mid = selected[0].data(0, Qt.ItemDataRole.UserRole)
        if mid and mid > 0:
            return self._model_cache.get(mid)
        return None

    def eventFilter(self, obj: object, event: QEvent) -> bool:
        """Navigation clavier et raccourcis dans le sélecteur de modèle."""
        if event.type() == QEvent.Type.KeyPress:
            key_event = cast(QKeyEvent, event)
            key = key_event.key()

            if key == Qt.Key.Key_Escape:
                self.close()
                return True

            if obj is self.search_input:
                if key == Qt.Key.Key_Down:
                    cur = self.tree.currentItem()
                    if cur is None:
                        if self.tree.topLevelItemCount() > 0:
                            self.tree.setCurrentItem(self.tree.topLevelItem(0))
                    else:
                        below = self.tree.itemBelow(cur)
                        if below is not None:
                            self.tree.setCurrentItem(below)
                    return True
                elif key == Qt.Key.Key_Up:
                    cur = self.tree.currentItem()
                    if cur is not None:
                        above = self.tree.itemAbove(cur)
                        if above is not None:
                            self.tree.setCurrentItem(above)
                    return True
                elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    self._on_confirm()
                    return True

            elif obj is self.tree and key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._on_confirm()
                return True

        return super().eventFilter(obj, event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Gère les raccourcis globaux de la fenêtre (Échap, Entrée)."""
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            event.accept()
            return
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._on_confirm()
            event.accept()
            return
        super().keyPressEvent(event)
