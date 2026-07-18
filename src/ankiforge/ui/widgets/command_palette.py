from typing import Optional, Any, cast

from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QWidget
from PySide6.QtCore import Qt, Signal, QEvent, Slot, QObject
from PySide6.QtGui import QKeyEvent

from ..theme import DesignTokens, apply_shadow
from ..components.inputs import GlowLineEdit


class CommandPalette(QDialog):
    """Palette de commandes ⌘K style VS Code / Raycast."""

    command_selected = Signal(str)  # émet le command_id

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        # Dialog frameless, centré, 600px wide
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Popup)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(600, 400)

        self.commands: list[dict[str, Any]] = []

        self._setup_ui()
        self._setup_shortcuts()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Container principal (glassmorphism)
        self.container = QWidget(self)
        self.container.setObjectName("commandPaletteContainer")
        # Fond: rgba(26, 29, 36, 0.95)
        self.container.setStyleSheet(f"""
            QWidget#commandPaletteContainer {{
                background-color: rgba(26, 29, 36, 0.95);
                border-radius: {DesignTokens.RADIUS_LG}px;
                border: 1px solid {DesignTokens.BORDER_LIGHT};
            }}
        """)
        # QGraphicsDropShadowEffect(blur=32) via theme
        apply_shadow(self.container, blur=32, offset_y=8, color="rgba(0,0,0,0.5)")

        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(12, 12, 12, 12)
        container_layout.setSpacing(8)

        # Input en haut avec icône search + placeholder
        header_layout = QHBoxLayout()
        self.search_input = GlowLineEdit(self.container)
        self.search_input.setPlaceholderText("Rechercher ou lancer une commande...")
        self.search_input.textChanged.connect(self._filter_commands)

        # kbd hint "⌘K" affiché
        shortcut_lbl = QLabel("⌘K")
        shortcut_lbl.setStyleSheet(f"""
            background-color: {DesignTokens.BG_HOVER};
            color: {DesignTokens.TEXT_MUTED};
            border-radius: 4px;
            padding: 4px 8px;
            font-family: {DesignTokens.FONT_CODE};
            font-size: 11px;
            font-weight: bold;
        """)

        header_layout.addWidget(self.search_input)
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
        container_layout.addWidget(self.result_list)

        main_layout.addWidget(self.container)

        # Installation du event filter pour la navigation clavier (↑↓, Enter, Esc)
        self.search_input.installEventFilter(self)

    def _setup_shortcuts(self) -> None:
        """Commandes par défaut à enregistrer."""
        self.register_command("nav.dashboard", "Aller au Dashboard", "🏠", "⌘1", "Navigation")
        self.register_command("nav.studio", "Aller au Studio", "🎨", "⌘2", "Navigation")
        self.register_command("action.create_card", "Créer une carte", "➕", "⌘N", "Actions")
        self.register_command("action.import_doc", "Importer un document", "📄", "⌘O", "Actions")
        self.register_command("system.settings", "Ouvrir les paramètres", "⚙️", "⌘,", "Système")
        self.register_command("system.theme", "Changer le thème", "🌗", "", "Système")

    def register_command(self, command_id: str, title: str, icon_name: str, shortcut: str = "", category: str = "") -> None:
        """Enregistre une commande disponible."""
        self.commands.append({"id": command_id, "title": title, "icon": icon_name, "shortcut": shortcut, "category": category})

    def show_palette(self) -> None:
        """Affiche la palette, focus sur l'input, clear."""
        self.search_input.clear()
        self.refresh_data()

        # Position: center de la fenêtre parente
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
        query = text.lower()

        for cmd in self.commands:
            if query in cmd["title"].lower() or query in cmd["category"].lower():
                item = QListWidgetItem(self.result_list)

                widget = QWidget()
                layout = QHBoxLayout(widget)
                layout.setContentsMargins(12, 8, 12, 8)

                icon_lbl = QLabel(cmd["icon"])
                title_lbl = QLabel(cmd["title"])
                title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: {DesignTokens.FONT_SIZE_BASE}px;")

                layout.addWidget(icon_lbl)
                layout.addWidget(title_lbl)

                if cmd["category"]:
                    cat_lbl = QLabel(f"({cmd['category']})")
                    cat_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: {DesignTokens.FONT_SIZE_SMALL}px;")
                    layout.addWidget(cat_lbl)

                layout.addStretch()

                if cmd["shortcut"]:
                    shortcut_lbl = QLabel(cmd["shortcut"])
                    shortcut_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-family: {DesignTokens.FONT_CODE}; font-size: {DesignTokens.FONT_SIZE_SMALL}px;")
                    layout.addWidget(shortcut_lbl)

                item.setSizeHint(widget.sizeHint())
                item.setData(Qt.ItemDataRole.UserRole, cmd["id"])

                self.result_list.addItem(item)
                self.result_list.setItemWidget(item, widget)

        # Sélectionner le premier élément par défaut
        if self.result_list.count() > 0:
            self.result_list.setCurrentRow(0)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        command_id = item.data(Qt.ItemDataRole.UserRole)
        if command_id:
            self.command_selected.emit(command_id)
            self.close()

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
                self.close()
                return True

        return super().eventFilter(obj, event)
