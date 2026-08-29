"""
Palette de commandes ⌘K style VS Code / Raycast / JetBrains Search Everywhere.
Permet la recherche globale et la navigation rapide entre toutes les vues d'AnkiForge.
"""

from typing import Any, cast

from PySide6.QtCore import QEvent, QObject, Qt, Signal, Slot
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ankiforge.ui.components.inputs import GlowLineEdit
from ankiforge.ui.theme import DesignTokens, apply_shadow
from ankiforge.utils.icon_loader import load_phosphor_icon


class CommandPalette(QDialog):
    """Palette de commandes ⌘K style VS Code / Raycast."""

    command_selected = Signal(str)  # émet le command_id
    view_requested = Signal(str)  # émet le view_id pour la navigation

    def __init__(self, view_registry: dict[str, Any] | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # Dialog frameless, centré, 620px wide
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(620, 420)

        self.commands: list[dict[str, Any]] = []
        self.view_registry = view_registry or {}

        self._setup_ui()
        self._populate_commands()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # Container principal (glassmorphism)
        self.container = QWidget(self)
        self.container.setObjectName("commandPaletteContainer")
        self.container.setStyleSheet(f"""
            QWidget#commandPaletteContainer {{
                background-color: {DesignTokens.BG_PANEL};
                border-radius: {DesignTokens.RADIUS_LG}px;
                border: 1px solid {DesignTokens.BORDER_COLOR};
            }}
        """)
        apply_shadow(self.container, blur=32, offset_y=8, color="rgba(0,0,0,0.5)")

        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(14, 14, 14, 14)
        container_layout.setSpacing(10)

        # Input en haut avec placeholder
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        self.search_input = GlowLineEdit(placeholder="Rechercher cartes, paquets, vues ou commandes...", parent=self.container)
        self.search_input.textChanged.connect(self._filter_commands)
        header_layout.addWidget(self.search_input, 1)

        # kbd hint "Esc pour fermer"
        shortcut_lbl = QLabel("Échap")
        shortcut_lbl.setStyleSheet(f"""
            background-color: {DesignTokens.BG_HOVER};
            color: {DesignTokens.TEXT_MUTED};
            border-radius: 4px;
            padding: 3px 6px;
            font-family: '{DesignTokens.FONT_CODE}';
            font-size: 11px;
            font-weight: bold;
        """)
        header_layout.addWidget(shortcut_lbl)

        # Liste de résultats filtrable
        self.result_list = QListWidget(self.container)
        self.result_list.setStyleSheet(f"""
            QListWidget {{
                background-color: transparent;
                border: none;
                outline: none;
            }}
            QListWidget::item {{
                border-radius: {DesignTokens.RADIUS_SM}px;
                color: {DesignTokens.TEXT_PRIMARY};
                padding: 2px;
            }}
            QListWidget::item:selected {{
                background-color: {DesignTokens.BG_ACTIVE};
            }}
            QListWidget::item:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
        """)
        self.result_list.itemClicked.connect(self._on_item_clicked)

        container_layout.addLayout(header_layout)
        container_layout.addWidget(self.result_list, 1)

        main_layout.addWidget(self.container)

        # Installation du event filter pour la navigation clavier (↑↓, Enter, Esc)
        self.search_input.installEventFilter(self)

    def _populate_commands(self) -> None:
        """Remplit la liste des commandes à partir du registre de vues et des actions globales."""
        self.commands.clear()

        # 1. Vues de navigation
        if self.view_registry:
            for view_id, info in self.view_registry.items():
                if isinstance(info, (tuple, list)) and len(info) >= 3:
                    cat, icon, title = info[0], info[1], info[2]
                    self.register_command(view_id, f"Aller à {title}", icon, "", cat)
        else:
            self.register_command("dashboard", "Aller au Tableau de bord", "house", "Ctrl+1", "Navigation")
            self.register_command("creation", "Aller au Studio de Création", "magic-wand", "Ctrl+2", "Navigation")
            self.register_command("edition", "Aller à Édition & Navigateur", "cards", "Ctrl+3", "Navigation")
            self.register_command("analysis", "Aller à Analyse & Audit IA", "chart-line-up", "Ctrl+4", "Navigation")
            self.register_command("consultant", "Aller à AI Consultant", "robot", "Ctrl+5", "Navigation")

        # 2. Actions globales
        self.register_command("action.import", "Importer un paquet Anki (.apkg)", "download-simple", "Ctrl+Shift+I", "Actions")
        self.register_command("action.export", "Exporter des cartes Anki (.apkg)", "upload-simple", "Ctrl+Shift+E", "Actions")
        self.register_command("action.settings", "Ouvrir les Paramètres", "gear", "Ctrl+,", "Système")

        self.refresh_data()

    def register_command(self, command_id: str, title: str, icon_name: str, shortcut: str = "", category: str = "") -> None:
        """Enregistre une commande disponible."""
        self.commands.append({"id": command_id, "title": title, "icon": icon_name, "shortcut": shortcut, "category": category})

    def show_palette(self) -> None:
        """Affiche la palette, focus sur l'input, clear."""
        self.search_input.clear()
        self.refresh_data()

        # Position: centre de la fenêtre parente
        parent = self.parentWidget()
        if parent:
            parent_rect = parent.geometry()
            self.move(parent_rect.x() + (parent_rect.width() - self.width()) // 2, parent_rect.y() + (parent_rect.height() - self.height()) // 2)

        self.show()
        self.raise_()
        self.activateWindow()
        self.search_input.setFocus()

    def refresh_data(self) -> None:
        """Rafraîchit la liste des commandes filtrées."""
        self._filter_commands(self.search_input.text())

    @Slot(str)
    def _filter_commands(self, text: str) -> None:
        """Filtrage en temps réel des commandes."""
        self.result_list.clear()
        query = text.lower().strip()

        for cmd in self.commands:
            if not query or query in cmd["title"].lower() or query in cmd["category"].lower() or query in cmd["id"].lower():
                item = QListWidgetItem(self.result_list)

                widget = QWidget()
                layout = QHBoxLayout(widget)
                layout.setContentsMargins(10, 6, 10, 6)
                layout.setSpacing(10)

                icon_lbl = QLabel()
                icon_lbl.setPixmap(load_phosphor_icon(cmd["icon"], color=DesignTokens.ACCENT_PRIMARY).pixmap(16, 16))
                icon_lbl.setStyleSheet("border: none; background: transparent;")

                title_lbl = QLabel(cmd["title"])
                title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12.5px; font-weight: 500; border: none; background: transparent;")

                layout.addWidget(icon_lbl)
                layout.addWidget(title_lbl)

                if cmd["category"]:
                    cat_lbl = QLabel(f"[{cmd['category']}]")
                    cat_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; border: none; background: transparent;")
                    layout.addWidget(cat_lbl)

                layout.addStretch()

                if cmd["shortcut"]:
                    shortcut_lbl = QLabel(cmd["shortcut"])
                    shortcut_lbl.setStyleSheet(f"""
                        color: {DesignTokens.TEXT_SECONDARY};
                        font-family: '{DesignTokens.FONT_CODE}';
                        font-size: 11px;
                        background: {DesignTokens.BG_HOVER};
                        border-radius: 4px;
                        padding: 2px 6px;
                        border: none;
                    """)
                    layout.addWidget(shortcut_lbl)

                item.setSizeHint(widget.sizeHint())
                item.setData(Qt.ItemDataRole.UserRole, cmd["id"])

                self.result_list.addItem(item)
                self.result_list.setItemWidget(item, widget)

        if self.result_list.count() > 0:
            self.result_list.setCurrentRow(0)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        command_id = item.data(Qt.ItemDataRole.UserRole)
        if command_id:
            self.command_selected.emit(command_id)
            if command_id.startswith("action."):
                action_name = command_id.replace("action.", "")
                if action_name == "settings":
                    self.view_requested.emit("settings")
            else:
                self.view_requested.emit(command_id)
            self.accept()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """Navigation clavier (↑↓ pour sélectionner, Enter pour exécuter, Esc pour fermer)."""
        if obj == self.search_input and event.type() == QEvent.Type.KeyPress:
            key_event = cast(QKeyEvent, event)

            if key_event.key() == Qt.Key.Key_Down:
                current = self.result_list.currentRow()
                if current < self.result_list.count() - 1:
                    self.result_list.setCurrentRow(current + 1)
                return True

            elif key_event.key() == Qt.Key.Key_Up:
                current = self.result_list.currentRow()
                if current > 0:
                    self.result_list.setCurrentRow(current - 1)
                return True

            elif key_event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                item = self.result_list.currentItem()
                if item:
                    self._on_item_clicked(item)
                return True

            elif key_event.key() == Qt.Key.Key_Escape:
                self.reject()
                return True

        return super().eventFilter(obj, event)


# Alias pour compatibilité rétroactive
CommandPaletteModal = CommandPalette
