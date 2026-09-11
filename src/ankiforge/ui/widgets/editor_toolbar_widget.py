"""
Barre d'outils d'édition modulaire et extensible pour AnkiForge.
Permet d'appliquer des enrichissements (Gras, Italique, Math KaTeX, Cloze, Liens, Images)
sur le champ actif et de rajouter dynamiquement de nouvelles actions.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QWidget

from ankiforge.ui.components.buttons import IconButton, PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens, StyledMenu
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


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
    consult_ai_requested = Signal()
    toggle_preview_requested = Signal()
    toggle_table_requested = Signal()
    customization_changed = Signal(list)  # list[str] of hidden_action_ids

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._actions: dict[str, ToolbarAction] = {}
        self._action_buttons: dict[str, QWidget] = {}
        self._hidden_action_ids: set[str] = set()

        self._setup_ui()
        self._register_default_actions()
        self.load_customization_preferences()

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

        # Bouton Menu Trois Points (Personnalisation & Overflow)
        self.btn_customize = IconButton("dots-three-vertical", tooltip="Personnaliser la barre d'outils...", size=24, parent=self)
        self.btn_customize.clicked.connect(self._open_customize_menu)
        self.main_layout.addWidget(self.btn_customize)

        self.main_layout.addStretch()

        # Bouton Dé-silotage : Consulter l'IA sur la note courante
        self.btn_consult_ai = SecondaryButton("Consulter l'IA")
        self.btn_consult_ai.setIcon(load_phosphor_icon("sparkle", color=DesignTokens.COLOR_PURPLE))
        self.btn_consult_ai.setToolTip("Ouvrir le Consultant IA pour auditer ou optimiser cette note")
        self.btn_consult_ai.setFixedHeight(26)
        self.btn_consult_ai.setStyleSheet(f"""
            QPushButton {{
                padding: 2px 10px;
                font-size: 11px;
                font-weight: 600;
                border-color: {DesignTokens.COLOR_PURPLE};
            }}
            QPushButton:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
        """)
        self.btn_consult_ai.clicked.connect(self.consult_ai_requested.emit)
        self.main_layout.addWidget(self.btn_consult_ai)

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
        btn.setVisible(action_id not in self._hidden_action_ids)
        self._action_buttons[action_id] = btn
        self.tools_layout.addWidget(btn)
        self._update_separators_visibility()

    def remove_action(self, action_id: str) -> None:
        """Supprime une action enregistrée."""
        if action_id in self._action_buttons:
            btn = self._action_buttons.pop(action_id)
            self.tools_layout.removeWidget(btn)
            btn.deleteLater()
        if action_id in self._actions:
            del self._actions[action_id]
        self._hidden_action_ids.discard(action_id)
        self._update_separators_visibility()

    def set_action_enabled(self, action_id: str, enabled: bool) -> None:
        """Active ou désactive un bouton d'action."""
        if action_id in self._action_buttons:
            self._action_buttons[action_id].setEnabled(enabled)

    def get_registered_actions(self) -> list[ToolbarAction]:
        """Retourne la liste ordonnée des actions enregistrées."""
        return list(self._actions.values())

    def _update_separators_visibility(self) -> None:
        """Cache les séparateurs superflus ou consécutifs dans la barre d'outils."""
        visible_button_seen = False
        last_sep: QFrame | None = None

        for i in range(self.tools_layout.count()):
            item = self.tools_layout.itemAt(i)
            if not item:
                continue
            w = item.widget()
            if not w:
                continue

            if isinstance(w, QFrame) and w.frameShape() == QFrame.Shape.VLine:
                if not visible_button_seen:
                    w.hide()
                else:
                    w.show()
                    last_sep = w
                    visible_button_seen = False
            else:
                if w.isVisible():
                    visible_button_seen = True

        if not visible_button_seen and last_sep is not None:
            last_sep.hide()

    def _apply_visibility(self) -> None:
        """Applique la visibilité sur tous les boutons et met à jour les séparateurs."""
        for aid, btn in self._action_buttons.items():
            btn.setVisible(aid not in self._hidden_action_ids)
        self._update_separators_visibility()
        self.customization_changed.emit(list(self._hidden_action_ids))

    def set_action_visible(self, action_id: str, visible: bool, persist: bool = True) -> None:
        """Affiche ou masque un bouton d'action individuel."""
        if visible:
            self._hidden_action_ids.discard(action_id)
        else:
            self._hidden_action_ids.add(action_id)

        if action_id in self._action_buttons:
            self._action_buttons[action_id].setVisible(visible)

        self._update_separators_visibility()
        self.customization_changed.emit(list(self._hidden_action_ids))

        if persist:
            self.save_customization_preferences()

    def is_action_visible(self, action_id: str) -> bool:
        """Retourne True si l'action est actuellement affichée sur la toolbar."""
        return action_id not in self._hidden_action_ids

    def get_hidden_action_ids(self) -> list[str]:
        """Retourne la liste des identifiants d'actions masquées."""
        return list(self._hidden_action_ids)

    def set_hidden_action_ids(self, hidden_ids: list[str] | set[str], persist: bool = True) -> None:
        """Définit en bloc les actions masquées."""
        self._hidden_action_ids = set(hidden_ids)
        self._apply_visibility()
        if persist:
            self.save_customization_preferences()

    def show_all_actions(self) -> None:
        """Réaffiche l'ensemble des boutons de la barre d'outils."""
        self.set_hidden_action_ids(set(), persist=True)

    def reset_customization(self) -> None:
        """Rétablit la configuration par défaut (toutes les actions visibles)."""
        self.show_all_actions()

    def load_customization_preferences(self) -> None:
        """Charge les préférences de masquage depuis SettingsService."""
        try:
            from ankiforge.services.settings_service import SettingsService

            saved = SettingsService.get("editor/toolbar_hidden_actions", default=[])
            if isinstance(saved, list):
                self._hidden_action_ids = {str(x) for x in saved}
            else:
                self._hidden_action_ids = set()
        except Exception as e:
            logger.debug("Échec chargement préférences toolbar : %s", e)
            self._hidden_action_ids = set()

        self._apply_visibility()

    def save_customization_preferences(self) -> None:
        """Sauvegarde les préférences de masquage dans SettingsService."""
        try:
            from ankiforge.services.settings_service import SettingsService

            SettingsService.set(
                "editor/toolbar_hidden_actions",
                list(self._hidden_action_ids),
                category="ui",
            )
        except Exception as e:
            logger.warning("Échec sauvegarde préférences toolbar : %s", e)

    def _open_customize_menu(self, exec_menu: bool = True) -> StyledMenu:
        """Ouvre le menu contextuel trois points avec accès rapide, sous-menu et réglages."""
        menu = StyledMenu(self)

        # 1. Actions actuellement masquées (accès direct en un clic)
        hidden_actions = [self._actions[aid] for aid in self._hidden_action_ids if aid in self._actions]
        if hidden_actions:
            lbl_hidden = menu.addAction("Actions masquées :")
            lbl_hidden.setEnabled(False)
            for act in hidden_actions:
                shortcut_txt = f"\t{act.shortcut}" if act.shortcut else ""
                item = menu.addAction(
                    load_phosphor_icon(act.icon_name, color=DesignTokens.TEXT_PRIMARY),
                    f"{act.label}{shortcut_txt}",
                )
                item.triggered.connect(act.callback)
            menu.addSeparator()

        # 2. Sous-menu "Boutons visibles"
        submenu_visible = menu.addMenu("Boutons visibles")
        submenu_visible.setIcon(load_phosphor_icon("eye", color=DesignTokens.TEXT_PRIMARY))

        last_grp: str | None = None
        for aid, act in self._actions.items():
            if last_grp is not None and act.group != last_grp:
                submenu_visible.addSeparator()
            last_grp = act.group

            chk_act = submenu_visible.addAction(
                load_phosphor_icon(act.icon_name, color=DesignTokens.TEXT_PRIMARY),
                act.label,
            )
            chk_act.setCheckable(True)
            chk_act.setChecked(aid not in self._hidden_action_ids)
            chk_act.toggled.connect(lambda checked, action_id=aid: self.set_action_visible(action_id, checked))

        menu.addSeparator()

        # 3. Action pour ouvrir ToolbarCustomizeDialog
        action_dialog = menu.addAction(
            load_phosphor_icon("sliders", color=DesignTokens.TEXT_PRIMARY),
            "Personnaliser la barre...",
        )
        action_dialog.triggered.connect(self._open_customize_dialog)

        # 4. Action "Tout afficher"
        action_all = menu.addAction(
            load_phosphor_icon("check-circle", color=DesignTokens.TEXT_PRIMARY),
            "Tout afficher",
        )
        action_all.triggered.connect(self.show_all_actions)

        # 5. Action "Rétablir par défaut"
        action_reset = menu.addAction(
            load_phosphor_icon("arrow-counter-clockwise", color=DesignTokens.TEXT_PRIMARY),
            "Rétablir par défaut",
        )
        action_reset.triggered.connect(self.reset_customization)

        if exec_menu:
            menu.exec(self.btn_customize.mapToGlobal(self.btn_customize.rect().bottomLeft()))

        return menu

    def _open_customize_dialog(self) -> None:
        """Ouvre le dialogue complet de personnalisation ToolbarCustomizeDialog."""
        from ankiforge.ui.dialogs.toolbar_customize_dialog import ToolbarCustomizeDialog

        dlg = ToolbarCustomizeDialog(
            actions=self._actions,
            hidden_action_ids=self._hidden_action_ids,
            parent=self,
        )
        dlg.customization_applied.connect(lambda hids: self.set_hidden_action_ids(hids, persist=True))
        dlg.exec()
