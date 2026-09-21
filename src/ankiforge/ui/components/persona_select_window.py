"""
Composant de sélection d'agent / persona (prompt) pour les tests A/B.
Reproduit le pattern architectural de `model_select_window.py`.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QLineEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from ankiforge.database.models import PersonaModel
from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon


class PersonaSelectWindow(QWidget):
    """
    Fenêtre modale de sélection d'agent / prompt (PersonaModel) avec recherche instantanée
    et aperçu du system prompt.
    """

    persona_selected = Signal(int, str)  # (persona_id, persona_name)

    def __init__(
        self,
        title: str = "Sélectionner un Agent / Prompt",
        current_persona_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.current_persona_id = current_persona_id
        self._items_by_id: dict[int, QTreeWidgetItem] = {}
        self._persona_cache: dict[int, PersonaModel] = {}

        self.setWindowTitle(title)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setFixedSize(520, 560)

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
        self.search_input.setPlaceholderText("Rechercher un agent (nom, description, prompt)...")
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

        # 2. Arborescence / Liste des personas
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setExpandsOnDoubleClick(True)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tree.setIndentation(18)

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

        self.btn_confirm = PrimaryButton("Valider cet agent")
        self.btn_confirm.clicked.connect(self._on_confirm)
        self.btn_confirm.setEnabled(False)

        footer_layout.addStretch()
        footer_layout.addWidget(btn_cancel)
        footer_layout.addWidget(self.btn_confirm)
        layout.addWidget(footer)

        self.tree.itemSelectionChanged.connect(self._on_selection_changed)
        self.tree.itemDoubleClicked.connect(self._on_confirm)

        self._load_personas()

    def _load_personas(self) -> None:
        """Charge la liste des agents depuis PersonaModel."""
        self.tree.clear()
        self._items_by_id.clear()
        self._persona_cache.clear()

        personas = list(PersonaModel.select().order_by(PersonaModel.name.asc()))

        for p in personas:
            self._persona_cache[p.id] = p
            prompt_preview = (p.system_prompt or "").strip().replace("\n", " ")[:110]
            if len((p.system_prompt or "").strip()) > 110:
                prompt_preview = prompt_preview + "…"

            item = QTreeWidgetItem([p.name])
            item.setData(0, Qt.ItemDataRole.UserRole, p.id)
            item.setData(0, Qt.ItemDataRole.UserRole + 1, p.name)
            item.setData(0, Qt.ItemDataRole.UserRole + 2, p.description or "")
            item.setData(0, Qt.ItemDataRole.UserRole + 3, prompt_preview or "")

            item.setIcon(0, load_phosphor_icon("ph.robot", color=DesignTokens.COLOR_PURPLE))

            # Sous-élément présentant le prompt
            meta = f"{p.output_format or 'json'} • {p.persona_type or 'pipeline'}"
            child = QTreeWidgetItem([f"↳ {meta} — {prompt_preview}"])
            child.setData(0, Qt.ItemDataRole.UserRole, p.id)
            child.setData(0, Qt.ItemDataRole.UserRole + 1, p.name)
            child.setForeground(0, QColor(DesignTokens.TEXT_MUTED))
            item.addChild(child)

            tooltip_lines = [f"Agent : {p.name}", meta]
            if p.description:
                tooltip_lines.append(f"Description : {p.description}")
            if prompt_preview:
                tooltip_lines.append(f"Prompt : {prompt_preview}")
            item.setToolTip(0, "\n".join(tooltip_lines))

            self.tree.addTopLevelItem(item)
            self._items_by_id[p.id] = item

            if self.current_persona_id == p.id:
                self.tree.setCurrentItem(item)

        self.tree.expandAll()

    def _on_search_changed(self, text: str) -> None:
        """Filtre les agents en direct par nom, description et prompt."""
        query = text.lower().strip()

        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if not item:
                continue
            if not query:
                item.setHidden(False)
                self._set_children_visible(item, True)
                continue

            pname = str(item.data(0, Qt.ItemDataRole.UserRole + 1) or item.text(0)).lower()
            desc_str = str(item.data(0, Qt.ItemDataRole.UserRole + 2) or "").lower()
            prompt_str = str(item.data(0, Qt.ItemDataRole.UserRole + 3) or "").lower()

            matches = (query in pname) or (query in desc_str) or (query in prompt_str)
            item.setHidden(not matches)
            self._set_children_visible(item, matches)

    def _set_children_visible(self, item: QTreeWidgetItem, visible: bool) -> None:
        for c_idx in range(item.childCount()):
            child = item.child(c_idx)
            if child:
                child.setHidden(not visible)

    def _on_selection_changed(self) -> None:
        selected = self.tree.selectedItems()
        self.btn_confirm.setEnabled(len(selected) > 0)

    def _on_confirm(self) -> None:
        selected = self.tree.selectedItems()
        if not selected:
            return
        item = selected[0]
        persona_id = item.data(0, Qt.ItemDataRole.UserRole)
        persona_name = item.data(0, Qt.ItemDataRole.UserRole + 1) or item.text(0)
        if persona_id is not None:
            self.persona_selected.emit(int(persona_id), str(persona_name))
            self.close()

    def get_selected_persona(self) -> PersonaModel | None:
        """Retourne l'objet PersonaModel sélectionné ou None."""
        selected = self.tree.selectedItems()
        if not selected:
            return None
        pid = selected[0].data(0, Qt.ItemDataRole.UserRole)
        if pid:
            return self._persona_cache.get(int(pid))
        return None


__all__ = ["PersonaSelectWindow"]
