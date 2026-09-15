"""
Composant de sélection de modèle de carte (NoteType).
Reproduit le pattern architectural de `deck_select_window.py` et `tag_select_window.py`.
"""

from __future__ import annotations

import json
import logging

from peewee import fn
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLineEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import NoteModel, NoteTypeModel
from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class ModelSelectWindow(QWidget):
    """
    Fenêtre modale de sélection de modèle de carte (NoteType) avec recherche instantanée
    et prévisualisation des champs et du volume de notes.
    """

    model_selected = Signal(int, str)  # (model_id, model_name)

    def __init__(
        self,
        title: str = "Sélectionner un Modèle de Carte",
        allow_all: bool = True,
        current_model_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.allow_all = allow_all
        self.current_model_id = current_model_id
        self._items_by_id: dict[int, QTreeWidgetItem] = {}
        self._model_cache: dict[int, NoteTypeModel] = {}

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
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Rechercher un modèle de carte (ex: Basique, Cloze, Front)...")
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
        content_layout.addWidget(self.search_input)

        # 2. Arborescence / Liste des modèles
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setExpandsOnDoubleClick(True)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

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

        self.btn_confirm = PrimaryButton("Valider ce modèle")
        self.btn_confirm.clicked.connect(self._on_confirm)
        self.btn_confirm.setEnabled(False)

        footer_layout.addStretch()
        footer_layout.addWidget(btn_cancel)
        footer_layout.addWidget(self.btn_confirm)
        layout.addWidget(footer)

        self.tree.itemSelectionChanged.connect(self._on_selection_changed)
        self.tree.itemDoubleClicked.connect(self._on_confirm)

        self._load_models()

    def _load_models(self) -> None:
        """Charge la liste des modèles de cartes depuis NoteTypeModel."""
        self.tree.clear()
        self._items_by_id.clear()
        self._model_cache.clear()

        # Compter les notes associées à chaque modèle
        note_counts: dict[int, int] = {}
        try:
            note_counts = dict(NoteModel.select(NoteModel.note_type, fn.COUNT(NoteModel.id)).group_by(NoteModel.note_type).tuples())
        except Exception as ex:
            logger.warning("Impossible de charger le décompte des notes par modèle: %s", ex)

        # 0. Item racine "Tous les modèles" si allow_all=True
        if self.allow_all:
            global_item = QTreeWidgetItem(["Tous les modèles"])
            global_item.setData(0, Qt.ItemDataRole.UserRole, -1)
            global_item.setData(0, Qt.ItemDataRole.UserRole + 1, "Tous les modèles")
            global_item.setIcon(0, load_phosphor_icon("cards", color=DesignTokens.COLOR_BLUE))
            self.tree.addTopLevelItem(global_item)
            self._items_by_id[-1] = global_item

            if self.current_model_id is None or self.current_model_id == -1:
                self.tree.setCurrentItem(global_item)

        models = list(NoteTypeModel.select().order_by(NoteTypeModel.name.asc()))

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

            item = QTreeWidgetItem([f"{m.name}  {notes_str}"])
            item.setData(0, Qt.ItemDataRole.UserRole, m.id)
            item.setData(0, Qt.ItemDataRole.UserRole + 1, m.name)
            item.setData(0, Qt.ItemDataRole.UserRole + 2, fields_str)
            item.setData(0, Qt.ItemDataRole.UserRole + 3, m.description or "")

            icon_color = DesignTokens.ACCENT_PRIMARY if "cloze" not in m.name.lower() else DesignTokens.COLOR_PURPLE
            item.setIcon(0, load_phosphor_icon("cards", color=icon_color))

            # Sous-élément présentant les champs
            child = QTreeWidgetItem([f"↳ {fields_str}"])
            child.setData(0, Qt.ItemDataRole.UserRole, m.id)
            child.setData(0, Qt.ItemDataRole.UserRole + 1, m.name)
            child.setForeground(0, QColor(DesignTokens.TEXT_MUTED))
            item.addChild(child)

            tooltip_lines = [f"Modèle: {m.name}", fields_str, notes_str]
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
