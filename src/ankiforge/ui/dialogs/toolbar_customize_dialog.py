"""
Dialogue modal de personnalisation de la barre d'outils de l'éditeur de notes.
Permet d'activer ou masquer les boutons par catégorie avec mémorisation des préférences.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon

if TYPE_CHECKING:
    from ankiforge.ui.widgets.editor_toolbar_widget import ToolbarAction

CATEGORY_TITLES: dict[str, str] = {
    "text": "Mise en forme du texte",
    "code": "Code préformaté",
    "math": "Formules mathématiques",
    "cloze": "Cartes à trous (Cloze)",
    "media": "Médias & Liens",
    "list": "Listes & Structure",
    "custom": "Extensions & Plugins",
}

CATEGORY_ICONS: dict[str, str] = {
    "text": "text-b",
    "code": "code",
    "math": "function",
    "cloze": "brackets-curly",
    "media": "link",
    "list": "list-bullets",
    "custom": "puzzle-piece",
}


class ToolbarCustomizeDialog(QDialog):
    """Dialogue permettant à l'utilisateur de choisir les boutons visibles dans la toolbar."""

    customization_applied = Signal(set)  # set of hidden action_ids

    def __init__(
        self,
        actions: dict[str, ToolbarAction],
        hidden_action_ids: set[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Personnaliser la barre d'outils")
        self.setFixedWidth(480)
        self.setMinimumHeight(520)
        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        self._actions = actions
        self._initial_hidden_ids = set(hidden_action_ids)
        self._checkboxes: dict[str, QCheckBox] = {}

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {DesignTokens.BG_PANEL};
                color: {DesignTokens.TEXT_PRIMARY};
                font-family: '{DesignTokens.FONT_MAIN}';
            }}
        """)

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        # En-tête
        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(load_phosphor_icon("sliders", color=DesignTokens.ACCENT_PRIMARY).pixmap(24, 24))
        icon_lbl.setStyleSheet("border: none; background: transparent;")
        header_layout.addWidget(icon_lbl)

        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(2)
        title_lbl = QLabel("Personnalisation de la barre d'outils")
        title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 14px; font-weight: bold; border: none;")
        subtitle_lbl = QLabel("Choisissez les outils de formatage visibles dans l'éditeur de cartes.")
        subtitle_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; border: none;")
        title_vbox.addWidget(title_lbl)
        title_vbox.addWidget(subtitle_lbl)
        header_layout.addLayout(title_vbox, 1)

        layout.addLayout(header_layout)

        # Barre d'actions rapides (Tout cocher / Tout décocher / Par défaut)
        quick_bar = QHBoxLayout()
        quick_bar.setSpacing(8)

        btn_select_all = SecondaryButton("Tout cocher")
        btn_select_all.setFixedHeight(26)
        btn_select_all.clicked.connect(self._select_all)

        btn_unselect_all = SecondaryButton("Tout décocher")
        btn_unselect_all.setFixedHeight(26)
        btn_unselect_all.clicked.connect(self._unselect_all)

        btn_default = SecondaryButton("Par défaut")
        btn_default.setFixedHeight(26)
        btn_default.clicked.connect(self._reset_defaults)

        quick_bar.addWidget(btn_select_all)
        quick_bar.addWidget(btn_unselect_all)
        quick_bar.addWidget(btn_default)
        quick_bar.addStretch()

        layout.addLayout(quick_bar)

        # Zone déroulante des catégories
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet(f"""
            QScrollArea {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(12, 12, 12, 12)
        container_layout.setSpacing(14)

        # Regrouper les actions par groupe
        grouped_actions: dict[str, list[ToolbarAction]] = {}
        for act in self._actions.values():
            grp = act.group or "custom"
            grouped_actions.setdefault(grp, []).append(act)

        # Ordre prédéfini des groupes
        group_order = ["text", "code", "math", "cloze", "media", "list", "custom"]
        all_groups = [g for g in group_order if g in grouped_actions] + [g for g in grouped_actions if g not in group_order]

        for grp in all_groups:
            acts = grouped_actions[grp]
            group_card = self._build_group_card(grp, acts)
            container_layout.addWidget(group_card)

        container_layout.addStretch()
        scroll_area.setWidget(container)
        layout.addWidget(scroll_area, 1)

        # Footer
        footer = QHBoxLayout()
        footer.setSpacing(8)

        self.btn_cancel = SecondaryButton("Annuler")
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_apply = PrimaryButton("Appliquer")
        self.btn_apply.clicked.connect(self._on_apply)

        footer.addStretch()
        footer.addWidget(self.btn_cancel)
        footer.addWidget(self.btn_apply)

        layout.addLayout(footer)

    def _build_group_card(self, group_key: str, actions: list[ToolbarAction]) -> QWidget:
        """Construit un bloc de catégorie avec titre et checkboxes d'outils."""
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 6px;
            }}
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(10, 8, 10, 8)
        card_layout.setSpacing(6)

        # En-tête de catégorie
        cat_header = QHBoxLayout()
        cat_header.setSpacing(6)

        icon_name = CATEGORY_ICONS.get(group_key, "tag")
        cat_icon = QLabel()
        cat_icon.setPixmap(load_phosphor_icon(icon_name, color=DesignTokens.ACCENT_PRIMARY).pixmap(14, 14))
        cat_icon.setStyleSheet("border: none; background: transparent;")
        cat_header.addWidget(cat_icon)

        cat_title_text = CATEGORY_TITLES.get(group_key, group_key.capitalize())
        cat_title = QLabel(cat_title_text)
        cat_title.setFont(QFont(DesignTokens.FONT_MAIN, 10, QFont.Weight.Bold))
        cat_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")
        cat_header.addWidget(cat_title, 1)

        card_layout.addLayout(cat_header)

        # Liste des checkboxes d'actions
        for act in actions:
            chk = QCheckBox()
            label_text = f"{act.label}  ({act.shortcut})" if act.shortcut else act.label
            chk.setText(label_text)
            chk.setIcon(load_phosphor_icon(act.icon_name, color=DesignTokens.TEXT_SECONDARY))
            chk.setChecked(act.action_id not in self._initial_hidden_ids)
            chk.setStyleSheet(f"""
                QCheckBox {{
                    color: {DesignTokens.TEXT_SECONDARY};
                    font-size: 11px;
                    spacing: 8px;
                    border: none;
                    background: transparent;
                    padding: 2px 0px;
                }}
                QCheckBox:hover {{
                    color: {DesignTokens.TEXT_PRIMARY};
                }}
                QCheckBox::indicator {{
                    width: 15px;
                    height: 15px;
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: 3px;
                    background-color: {DesignTokens.BG_INPUT};
                }}
                QCheckBox::indicator:checked {{
                    background-color: {DesignTokens.ACCENT_PRIMARY};
                    border-color: {DesignTokens.ACCENT_PRIMARY};
                }}
            """)
            self._checkboxes[act.action_id] = chk
            card_layout.addWidget(chk)

        return card

    def _select_all(self) -> None:
        for chk in self._checkboxes.values():
            chk.setChecked(True)

    def _unselect_all(self) -> None:
        for chk in self._checkboxes.values():
            chk.setChecked(False)

    def _reset_defaults(self) -> None:
        # Par défaut, toutes les actions sont cochées / visibles
        for chk in self._checkboxes.values():
            chk.setChecked(True)

    def _on_apply(self) -> None:
        hidden_ids: set[str] = set()
        for action_id, chk in self._checkboxes.items():
            if not chk.isChecked():
                hidden_ids.add(action_id)

        self.customization_applied.emit(hidden_ids)
        self.accept()
