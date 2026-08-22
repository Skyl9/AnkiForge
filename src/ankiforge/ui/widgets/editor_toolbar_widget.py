"""
Barre d'outils d'édition modulaire et extensible pour AnkiForge.
Permet d'appliquer des enrichissements (Gras, Italique, Math KaTeX, Cloze, Liens, Images)
sur le champ actif et de rajouter dynamiquement de nouvelles actions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QWidget

from ankiforge.ui.components.buttons import IconButton, PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon


@dataclass
class ToolbarAction:
    action_id: str
    icon_name: str
    label: str
    tooltip: str
    shortcut: str
    callback: Callable[[], None]
    group: str = "format"


class EditorToolbarWidget(QWidget):
    """
    Barre d'outils unifiée et extensible pour l'édition de cartes Anki.
    Fournit un registre public permettant d'ajouter et personnaliser les outils d'édition.
    """

    action_triggered = Signal(str)  # action_id
    save_requested = Signal()
    history_requested = Signal()
    toggle_preview_requested = Signal()
    toggle_table_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._actions: Dict[str, ToolbarAction] = {}
        self._action_buttons: Dict[str, QWidget] = {}

        self._setup_ui()
        self._register_default_actions()

    def _setup_ui(self) -> None:
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(4, 3, 4, 3)
        self.main_layout.setSpacing(4)
        self.setStyleSheet(f"""
            EditorToolbarWidget {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)

        # Bouton Toggle Table (Replier/Déplier la liste)
        self.btn_toggle_table = IconButton("caret-up", tooltip="Replier la liste des cartes (Ctrl+Shift+T)", size=24, parent=self)
        self.btn_toggle_table.clicked.connect(self.toggle_table_requested.emit)
        self.main_layout.addWidget(self.btn_toggle_table)

        self.main_layout.addWidget(self._create_separator())

        # Conteneur des boutons d'outils de formatage
        self.tools_layout = QHBoxLayout()
        self.tools_layout.setContentsMargins(0, 0, 0, 0)
        self.tools_layout.setSpacing(4)
        self.main_layout.addLayout(self.tools_layout)

        self.main_layout.addStretch()

        # Boutons système à droite : Historique + Sauvegarder + Toggle Preview
        self.btn_history = SecondaryButton("Historique")
        self.btn_history.setIcon(load_phosphor_icon("clock-counter-clockwise", color=DesignTokens.TEXT_PRIMARY))
        self.btn_history.setToolTip("Machine à Remonter le Temps (Ctrl+H)")
        self.btn_history.setFixedHeight(26)
        self.btn_history.setStyleSheet("""
            QPushButton {
                padding: 2px 10px;
                font-size: 11px;
                font-weight: 600;
            }
        """)
        self.btn_history.clicked.connect(self.history_requested.emit)
        self.main_layout.addWidget(self.btn_history)

        self.btn_save = PrimaryButton("Sauvegarder")
        self.btn_save.setIcon(load_phosphor_icon("floppy-disk", color="white"))
        self.btn_save.setToolTip("Sauvegarder les modifications (Ctrl+S)")
        self.btn_save.setFixedHeight(26)
        self.btn_save.setStyleSheet("""
            QPushButton {
                padding: 2px 12px;
                font-size: 11px;
                font-weight: 600;
            }
        """)
        self.btn_save.clicked.connect(self.save_requested.emit)
        self.main_layout.addWidget(self.btn_save)

        self.btn_toggle_preview = IconButton("sidebar-simple", tooltip="Afficher / Masquer l'aperçu (Ctrl+P)", size=24, parent=self)
        self.btn_toggle_preview.clicked.connect(self.toggle_preview_requested.emit)
        self.main_layout.addWidget(self.btn_toggle_preview)

    def _create_separator(self) -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Plain)
        sep.setFixedWidth(1)
        sep.setStyleSheet(f"background-color: {DesignTokens.BORDER_COLOR}; border: none; margin: 4px 2px;")
        return sep

    def _register_default_actions(self) -> None:
        # --- Groupe Mise en Forme ---
        self.register_action("bold", "text-b", "Gras", "Gras (Ctrl+B)", "Ctrl+B", lambda: self.action_triggered.emit("bold"), group="text")
        self.register_action("italic", "text-italic", "Italique", "Italique (Ctrl+I)", "Ctrl+I", lambda: self.action_triggered.emit("italic"), group="text")
        self.register_action("underline", "text-underline", "Souligné", "Souligné (Ctrl+U)", "Ctrl+U", lambda: self.action_triggered.emit("underline"), group="text")
        self.register_action("strikethrough", "text-strikethrough", "Barré", "Barré (<s>...</s>)", "Ctrl+Shift+X", lambda: self.action_triggered.emit("strikethrough"), group="text")

        # Séparateur
        self.tools_layout.addWidget(self._create_separator())

        # --- Groupe Code & Math ---
        self.register_action("code_inline", "code", "Code inline", "Code en ligne (<code>...</code>)", "", lambda: self.action_triggered.emit("code_inline"), group="code")
        self.register_action("code_block", "code-block", "Bloc de code", "Bloc préformaté (<pre><code>...</code></pre>)", "", lambda: self.action_triggered.emit("code_block"), group="code")
        self.register_action("math", "function", "Formule KaTeX", "Formule mathématique LaTeX (Ctrl+M)", "Ctrl+M", lambda: self.action_triggered.emit("math"), group="math")

        # Séparateur
        self.tools_layout.addWidget(self._create_separator())

        # --- Groupe Cloze ---
        self.register_action("cloze", "brackets-curly", "Trou Cloze", "Créer un trou Cloze {{cN::...}} (Ctrl+Shift+C)", "Ctrl+Shift+C", lambda: self.action_triggered.emit("cloze"), group="cloze")

        # Séparateur
        self.tools_layout.addWidget(self._create_separator())

        # --- Groupe Médias & Liens ---
        self.register_action("link", "link", "Lien", "Lien hypertexte (Ctrl+K)", "Ctrl+K", lambda: self.action_triggered.emit("link"), group="media")
        self.register_action("image", "image", "Image", "Insérer une image (<img src=...>)", "", lambda: self.action_triggered.emit("image"), group="media")

        # Séparateur
        self.tools_layout.addWidget(self._create_separator())

        # --- Groupe Listes & Structure ---
        self.register_action("bullet_list", "list-bullets", "Liste à puces", "Liste à puces (<ul><li>...</li></ul>)", "", lambda: self.action_triggered.emit("bullet_list"), group="list")
        self.register_action("ordered_list", "list-numbers", "Liste numérotée", "Liste ordonnée (<ol><li>...</li></ol>)", "", lambda: self.action_triggered.emit("ordered_list"), group="list")
        self.register_action("hr", "minus", "Séparateur", "Ligne de séparation (<hr>)", "", lambda: self.action_triggered.emit("hr"), group="list")
        self.register_action("quote", "quotes", "Citation", "Citation en bloc (<blockquote>...</blockquote>)", "", lambda: self.action_triggered.emit("quote"), group="list")

        # --- Actions injectées par les Addons / Plugins ---
        try:
            from ankiforge.services.plugins.plugin_manager import get_plugin_manager

            pm = get_plugin_manager()
            for addon_info in pm.get_all_addons():
                api = pm.get_addon_api(addon_info.id)
                if api:
                    for act in api.ui.get_registered_editor_actions():
                        self.register_action(
                            action_id=act["action_id"],
                            icon_name=act["icon_name"],
                            label=act["label"],
                            tooltip=act["tooltip"],
                            shortcut=act["shortcut"],
                            callback=act["callback"],
                            group=act.get("group", "custom"),
                        )
        except Exception:
            pass  # nosec B110

    def register_action(
        self,
        action_id: str,
        icon_name: str,
        label: str,
        tooltip: str,
        shortcut: str,
        callback: Callable[[], None],
        group: str = "custom",
    ) -> None:
        """Enregistre une nouvelle action et ajoute son bouton dans la barre d'outils."""
        action = ToolbarAction(
            action_id=action_id,
            icon_name=icon_name,
            label=label,
            tooltip=tooltip,
            shortcut=shortcut,
            callback=callback,
            group=group,
        )
        self._actions[action_id] = action

        btn = IconButton(icon_name, tooltip=tooltip, size=24, parent=self)
        btn.clicked.connect(callback)
        self._action_buttons[action_id] = btn
        self.tools_layout.addWidget(btn)

    def remove_action(self, action_id: str) -> None:
        """Supprime une action enregistrée."""
        if action_id in self._action_buttons:
            btn = self._action_buttons.pop(action_id)
            self.tools_layout.removeWidget(btn)
            btn.deleteLater()
        if action_id in self._actions:
            del self._actions[action_id]

    def set_action_enabled(self, action_id: str, enabled: bool) -> None:
        """Active ou désactive un bouton d'action."""
        if action_id in self._action_buttons:
            self._action_buttons[action_id].setEnabled(enabled)

    def get_registered_actions(self) -> List[ToolbarAction]:
        """Retourne la liste ordonnée des actions enregistrées."""
        return list(self._actions.values())
