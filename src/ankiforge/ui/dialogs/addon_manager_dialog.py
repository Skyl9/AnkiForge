"""
Gestionnaire Visuel d'Addons & Extensions AnkiForge.
Conforme au Design System AnkiForge (DesignTokens, PySide6, Nuitka-Safe).
Fournit un éditeur graphique automatique de configuration (config.json),
un visualiseur de documentation (config.md) et un installateur d'archives ZIP.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QScrollArea,
    QSplitter,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ankiforge.services.plugins.manifest_schema import AddonInfo, AddonStatus
from ankiforge.services.plugins.plugin_manager import PluginManager, get_plugin_manager
from ankiforge.ui.components.badges import Badge
from ankiforge.ui.components.buttons import DangerButton, PrimaryButton, SecondaryButton
from ankiforge.ui.components.inputs import StyledLineEdit
from ankiforge.ui.components.tables import StyledTableWidget
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


def _safe_show_toast(widget: QWidget, message: str, is_error: bool = False) -> None:
    """Affiche un toast sécurisé sur la fenêtre parente ou active."""
    try:
        target = widget.window() if widget else None
        if not target:
            from PySide6.QtWidgets import QApplication

            target = QApplication.activeWindow()
        if target:
            show_toast(target, message, is_error=is_error)
        else:
            logger.info(f"[Toast] {message}")
    except Exception:
        logger.info(f"[Toast fallback] {message}")


class AddonConfigForm(QWidget):
    """
    Formulaire dynamique généré à partir du dictionnaire config.json d'un addon.
    """

    config_saved = Signal(dict)

    def __init__(self, addon_info: AddonInfo, plugin_manager: PluginManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.addon_info = addon_info
        self.plugin_manager = plugin_manager
        self._fields: dict[str, QWidget] = {}
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        config_data = self.addon_info.config_schema
        if not config_data:
            lbl_empty = QLabel("Cet addon ne possède aucun paramètre de configuration personnalisable.")
            lbl_empty.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-style: italic; font-size: 12px;")
            layout.addWidget(lbl_empty)
            layout.addStretch()
            return

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        content_widget = QWidget()
        form_layout = QVBoxLayout(content_widget)
        form_layout.setSpacing(10)
        form_layout.setContentsMargins(0, 0, 0, 0)

        for key, val in config_data.items():
            row_frame = QFrame()
            row_frame.setStyleSheet(f"background-color: {DesignTokens.BG_INPUT}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: {DesignTokens.RADIUS_SM}px; padding: 6px;")
            row_layout = QHBoxLayout(row_frame)
            row_layout.setContentsMargins(8, 6, 8, 6)

            lbl = QLabel(f"<b>{key}</b>")
            lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px;")
            row_layout.addWidget(lbl)
            row_layout.addStretch()

            if isinstance(val, bool):
                chk = QCheckBox()
                chk.setChecked(val)
                chk.setCursor(Qt.CursorShape.PointingHandCursor)
                row_layout.addWidget(chk)
                self._fields[key] = chk
            elif isinstance(val, int | float):
                inp = StyledLineEdit()

                inp.setText(str(val))
                inp.setFixedWidth(140)
                row_layout.addWidget(inp)
                self._fields[key] = inp
            elif isinstance(val, str):
                inp = StyledLineEdit()
                inp.setText(val)
                inp.setMinimumWidth(220)
                row_layout.addWidget(inp)
                self._fields[key] = inp
            else:
                inp = StyledLineEdit()
                inp.setText(json.dumps(val, ensure_ascii=False))
                inp.setMinimumWidth(220)
                row_layout.addWidget(inp)
                self._fields[key] = inp

            form_layout.addWidget(row_frame)

        form_layout.addStretch()
        scroll.setWidget(content_widget)
        layout.addWidget(scroll, 1)

        # Bouton de sauvegarde
        btn_save = PrimaryButton("Enregistrer les réglages")
        btn_save.setIcon(load_phosphor_icon("floppy-disk", color="white"))
        btn_save.clicked.connect(self._on_save)
        layout.addWidget(btn_save, alignment=Qt.AlignmentFlag.AlignRight)

    def _on_save(self) -> None:
        new_config: dict[str, Any] = {}
        for key, widget in self._fields.items():
            orig_val = self.addon_info.config_schema.get(key)
            if isinstance(widget, QCheckBox):
                new_config[key] = widget.isChecked()
            elif isinstance(widget, StyledLineEdit):
                text_val = widget.text().strip()
                if isinstance(orig_val, int):
                    try:
                        new_config[key] = int(text_val)
                    except ValueError:
                        new_config[key] = text_val
                elif isinstance(orig_val, float):
                    try:
                        new_config[key] = float(text_val)
                    except ValueError:
                        new_config[key] = text_val
                else:
                    new_config[key] = text_val

        self.addon_info.config_schema = new_config
        api = self.plugin_manager.get_addon_api(self.addon_info.id)
        if api:
            api.config.set_config(new_config)
        else:
            # Sauvegarde directe sur disque si l'addon est inactif
            cfg_file = self.addon_info.folder_path / "config.json"
            try:
                with open(cfg_file, "w", encoding="utf-8") as f:
                    json.dump(new_config, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.error(f"Erreur d'écriture {cfg_file}: {e}")

        _safe_show_toast(self, f"Réglages de '{self.addon_info.name}' enregistrés !", is_error=False)
        self.config_saved.emit(new_config)


class AddonDetailWidget(QWidget):
    """Panneau de détail et gestion d'un addon sélectionné."""

    addon_updated = Signal()

    def __init__(self, plugin_manager: PluginManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.plugin_manager = plugin_manager
        self.current_addon: AddonInfo | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(16, 16, 16, 16)
        self.layout.setSpacing(12)

        # Placeholder stylisé si aucun addon sélectionné
        self.placeholder_widget = QWidget()
        ph_layout = QVBoxLayout(self.placeholder_widget)
        ph_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ph_layout.setSpacing(10)

        self.ph_icon = QLabel()
        self.ph_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ph_icon.setPixmap(load_phosphor_icon("ph.puzzle-piece", color=DesignTokens.TEXT_MUTED).pixmap(36, 36))
        ph_layout.addWidget(self.ph_icon)

        self.lbl_placeholder = QLabel("Sélectionnez une extension dans la liste pour voir ses détails.")
        self.lbl_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_placeholder.setWordWrap(True)
        self.lbl_placeholder.setMaximumWidth(380)
        self.lbl_placeholder.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 13px; font-style: italic;")
        ph_layout.addWidget(self.lbl_placeholder)

        self.layout.addWidget(self.placeholder_widget)

        # Conteneur principal
        self.content_box = QWidget()
        self.content_box.setVisible(False)
        content_layout = QVBoxLayout(self.content_box)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        # Header Info Card
        self.header_card = QFrame()
        self.header_card.setStyleSheet(f"background-color: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: {DesignTokens.RADIUS_MD}px; padding: 12px;")
        h_layout = QVBoxLayout(self.header_card)
        h_layout.setSpacing(6)

        top_row = QHBoxLayout()
        self.lbl_name = QLabel("Nom de l'extension")
        self.lbl_name.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 16px; font-weight: bold;")
        top_row.addWidget(self.lbl_name)

        self.badge_status = Badge("Actif", variant="success")
        top_row.addWidget(self.badge_status)
        top_row.addStretch()

        self.btn_toggle_enable = SecondaryButton("Désactiver")
        self.btn_toggle_enable.clicked.connect(self._toggle_enable)
        top_row.addWidget(self.btn_toggle_enable)

        h_layout.addLayout(top_row)

        self.lbl_meta = QLabel("v1.0.0 • Auteur: Anonyme")
        self.lbl_meta.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        h_layout.addWidget(self.lbl_meta)

        self.lbl_desc = QLabel("Description courte de l'addon...")
        self.lbl_desc.setWordWrap(True)
        self.lbl_desc.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 12px; margin-top: 4px;")
        h_layout.addWidget(self.lbl_desc)

        content_layout.addWidget(self.header_card)

        # Onglets de contenu (Réglages, Documentation, Journal d'erreurs)
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                background-color: {DesignTokens.BG_PANEL};
            }}
            QTabBar::tab {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_SECONDARY};
                padding: 6px 14px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
                font-size: 11px;
                font-weight: 500;
            }}
            QTabBar::tab:selected {{
                background-color: {DesignTokens.BG_PANEL};
                color: {DesignTokens.ACCENT_PRIMARY};
                font-weight: bold;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-bottom: none;
            }}
        """)

        # Tab 1: Formulaire de Réglages
        self.config_container = QWidget()
        self.config_container_layout = QVBoxLayout(self.config_container)
        self.config_container_layout.setContentsMargins(0, 0, 0, 0)
        self.tabs.addTab(self.config_container, "⚙️ Réglages")

        # Tab 2: Documentation Markdown
        self.doc_edit = QTextEdit()
        self.doc_edit.setReadOnly(True)
        self.doc_edit.setStyleSheet(f"background-color: {DesignTokens.BG_PANEL}; color: {DesignTokens.TEXT_PRIMARY}; border: none; padding: 12px;")
        self.tabs.addTab(self.doc_edit, "📖 Documentation")

        # Tab 3: Logs d'Erreur (affiché si statut ERROR)
        self.error_edit = QTextEdit()
        self.error_edit.setReadOnly(True)
        self.error_edit.setStyleSheet(f"background-color: {DesignTokens.BG_INPUT}; color: {DesignTokens.COLOR_RED}; border: none; font-family: monospace; font-size: 11px; padding: 10px;")
        self.tabs.addTab(self.error_edit, "⚠️ Diagnostic Erreur")

        content_layout.addWidget(self.tabs, 1)

        # Barre d'actions en bas
        bottom_row = QHBoxLayout()
        self.btn_open_folder = SecondaryButton("Ouvrir le dossier")
        self.btn_open_folder.setIcon(load_phosphor_icon("folder-open", color=DesignTokens.TEXT_PRIMARY))
        self.btn_open_folder.clicked.connect(self._open_folder)
        bottom_row.addWidget(self.btn_open_folder)

        bottom_row.addStretch()

        self.btn_uninstall = DangerButton("Désinstaller l'extension")
        self.btn_uninstall.setIcon(load_phosphor_icon("trash", color=DesignTokens.COLOR_RED))
        self.btn_uninstall.clicked.connect(self._uninstall)
        bottom_row.addWidget(self.btn_uninstall)

        content_layout.addLayout(bottom_row)
        self.layout.addWidget(self.content_box, 1)

    def set_addon(self, addon_info: AddonInfo | None) -> None:
        self.current_addon = addon_info
        if not addon_info:
            self.placeholder_widget.setVisible(True)
            self.content_box.setVisible(False)
            return

        self.placeholder_widget.setVisible(False)
        self.content_box.setVisible(True)

        self.lbl_name.setText(addon_info.name)
        self.lbl_meta.setText(f"v{addon_info.version} • Auteur: {addon_info.author} • ID: {addon_info.id}")
        self.lbl_desc.setText(addon_info.description or "Aucune description fournie.")

        # Badge & Bouton de toggle
        if addon_info.status == AddonStatus.ACTIVE:
            self.badge_status.setText("Actif")
            self.badge_status.set_variant("success")
            self.btn_toggle_enable.setText("Désactiver")
        elif addon_info.status == AddonStatus.ERROR:
            self.badge_status.setText("Erreur")
            self.badge_status.set_variant("danger")
            self.btn_toggle_enable.setText("Réessayer")
        else:
            self.badge_status.setText("Désactivé")
            self.badge_status.set_variant("neutral")
            self.btn_toggle_enable.setText("Activer")

        # Remplir l'onglet Réglages
        # Nettoyer l'ancien formulaire
        while self.config_container_layout.count():
            item = self.config_container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        form = AddonConfigForm(addon_info, self.plugin_manager)
        self.config_container_layout.addWidget(form)

        # Documentation
        if addon_info.has_documentation and addon_info.doc_markdown:
            self.doc_edit.setMarkdown(addon_info.doc_markdown)
        else:
            self.doc_edit.setHtml(f"<p style='color:{DesignTokens.TEXT_MUTED}; font-style:italic;'>Aucun fichier config.md ou README.md trouvé pour cette extension.</p>")

        # Logs d'erreur
        if addon_info.error_message:
            self.error_edit.setText(addon_info.error_message)
            self.tabs.setTabVisible(2, True)
        else:
            self.error_edit.setText("Aucune anomalie détectée.")
            self.tabs.setTabVisible(2, False)

        self.tabs.setCurrentIndex(0)

    def _toggle_enable(self) -> None:
        if not self.current_addon:
            return
        aid = self.current_addon.id
        if self.current_addon.is_enabled and self.current_addon.status == AddonStatus.ACTIVE:
            self.plugin_manager.disable_addon(aid)
            _safe_show_toast(self, f"Extension '{self.current_addon.name}' désactivée.", is_error=False)
        else:
            self.plugin_manager.enable_addon(aid)
            _safe_show_toast(self, f"Extension '{self.current_addon.name}' activée !", is_error=False)

        self.set_addon(self.plugin_manager.get_addon(aid))
        self.addon_updated.emit()

    def _open_folder(self) -> None:
        if self.current_addon:
            self.plugin_manager.open_addon_folder(self.current_addon.id)

    def _uninstall(self) -> None:
        if not self.current_addon:
            return
        aid = self.current_addon.id
        name = self.current_addon.name
        reply = QMessageBox.question(
            self,
            "Confirmer la suppression",
            f"Êtes-vous sûr de vouloir supprimer définitivement l'extension '{name}' ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.plugin_manager.uninstall_addon(aid)
            _safe_show_toast(self, f"Extension '{name}' désinstallée.", is_error=False)
            self.set_addon(None)
            self.addon_updated.emit()

    def refresh_theme(self, profile: Any) -> None:
        """Met à jour les styles dynamiques selon le profil de thème."""
        if hasattr(self, "ph_icon"):
            self.ph_icon.setPixmap(load_phosphor_icon("ph.puzzle-piece", color=profile.text_muted).pixmap(36, 36))
        if hasattr(self, "header_card"):
            self.header_card.setStyleSheet(f"QFrame {{ background-color: {profile.bg_panel}; border: 1px solid {profile.border_color}; border-radius: {profile.radius_md}px; padding: 12px; }}")
        if hasattr(self, "lbl_name"):
            self.lbl_name.setStyleSheet(f"color: {profile.text_primary}; font-size: 16px; font-weight: bold;")
        if hasattr(self, "lbl_meta"):
            self.lbl_meta.setStyleSheet(f"color: {profile.text_muted}; font-size: 11px;")
        if hasattr(self, "lbl_desc"):
            self.lbl_desc.setStyleSheet(f"color: {profile.text_secondary}; font-size: 12px; margin-top: 4px;")
        if hasattr(self, "doc_edit"):
            self.doc_edit.setStyleSheet(f"background-color: {profile.bg_panel}; color: {profile.text_primary}; border: none; padding: 12px;")
        if hasattr(self, "error_edit"):
            self.error_edit.setStyleSheet(f"background-color: {profile.bg_input}; color: {profile.color_red}; border: none; font-family: monospace; font-size: 11px; padding: 10px;")


class AddonManagerWidget(QWidget):
    """
    Vue principale du gestionnaire d'addons pour intégration dans la modale Paramètres.
    """

    def __init__(self, plugin_manager: PluginManager | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.plugin_manager = plugin_manager or get_plugin_manager()
        self._setup_ui()
        self.refresh_addons_list()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # En-tête & Barre d'outils
        top_bar = QHBoxLayout()
        lbl_title = QLabel("EXTENSIONS & ADDONS")
        lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        top_bar.addWidget(lbl_title)

        if self.plugin_manager.is_safe_mode:
            badge_safe = Badge("🛡️ Mode Sans Échec Actif", variant="warning")
            top_bar.addWidget(badge_safe)

        top_bar.addStretch()

        btn_install_zip = PrimaryButton("Installer (.zip)")
        btn_install_zip.setIcon(load_phosphor_icon("file-arrow-up", color="white"))
        btn_install_zip.clicked.connect(self._install_zip)
        top_bar.addWidget(btn_install_zip)

        btn_open_root = SecondaryButton("Ouvrir le dossier")
        btn_open_root.setIcon(load_phosphor_icon("folder", color=DesignTokens.TEXT_PRIMARY))
        btn_open_root.clicked.connect(self.plugin_manager.open_addons_folder)
        top_bar.addWidget(btn_open_root)

        main_layout.addLayout(top_bar)

        # Splitter gauche (Table) / droite (Détail)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # Panneau gauche : Table des addons
        left_panel = QWidget()
        left_panel.setMinimumWidth(280)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        self.search_input = StyledLineEdit(icon_name="magnifying-glass", placeholder="Filtrer les extensions...")
        self.search_input.textChanged.connect(self._filter_addons)
        left_layout.addWidget(self.search_input)

        self.table = StyledTableWidget(["Nom", "Statut", "Version"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._on_table_selection)
        left_layout.addWidget(self.table, 1)

        self.splitter.addWidget(left_panel)

        # Panneau droit : Détail & Configuration
        self.detail_widget = AddonDetailWidget(self.plugin_manager)
        self.detail_widget.addon_updated.connect(self.refresh_addons_list)
        self.splitter.addWidget(self.detail_widget)

        self.splitter.setSizes([300, 600])
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 7)

        main_layout.addWidget(self.splitter, 1)

    def refresh_addons_list(self) -> None:
        """Recharge la liste des addons."""
        addons = self.plugin_manager.discover_addons()
        filter_text = self.search_input.text().strip().lower()

        self.table.setRowCount(0)
        for addon in addons:
            if filter_text and filter_text not in addon.name.lower() and filter_text not in addon.description.lower() and filter_text not in addon.id:
                continue

            row = self.table.rowCount()
            self.table.insertRow(row)

            item_name = QTableWidgetItem(addon.name)
            item_name.setData(Qt.ItemDataRole.UserRole, addon.id)
            self.table.setItem(row, 0, item_name)

            # Badge Statut
            status_text = "Actif" if addon.status == AddonStatus.ACTIVE else ("Erreur" if addon.status == AddonStatus.ERROR else "Désactivé")
            item_status = QTableWidgetItem(status_text)
            self.table.setItem(row, 1, item_status)

            item_ver = QTableWidgetItem(f"v{addon.version}")
            self.table.setItem(row, 2, item_ver)

    def _filter_addons(self) -> None:
        self.refresh_addons_list()

    def _on_table_selection(self) -> None:
        selected_items = self.table.selectedItems()
        if not selected_items:
            self.detail_widget.set_addon(None)
            return

        row = selected_items[0].row()
        item = self.table.item(row, 0)
        if item:
            addon_id = item.data(Qt.ItemDataRole.UserRole)
            addon_info = self.plugin_manager.get_addon(addon_id)
            self.detail_widget.set_addon(addon_info)

    def _install_zip(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Installer une extension AnkiForge",
            "",
            "Archives Zip (*.zip)",
        )
        if file_path:
            success, msg = self.plugin_manager.install_addon_from_zip(file_path)
            if success:
                _safe_show_toast(self, msg, is_error=False)
                self.refresh_addons_list()
            else:
                QMessageBox.critical(self, "Erreur d'installation", msg)

    def refresh_theme(self, profile: Any) -> None:
        """Met à jour les composants internes selon le thème actif."""
        if hasattr(self, "table") and hasattr(self.table, "refresh_theme"):
            self.table.refresh_theme(profile)
        if hasattr(self, "detail_widget") and hasattr(self.detail_widget, "refresh_theme"):
            self.detail_widget.refresh_theme(profile)


class AddonManagerDialog(QDialog):
    """Boîte de dialogue autonome pour le gestionnaire d'addons."""

    def __init__(self, plugin_manager: PluginManager | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Gestionnaire d'Extensions AnkiForge")
        self.setMinimumSize(820, 520)
        self.resize(920, 580)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.manager_widget = AddonManagerWidget(plugin_manager, self)
        layout.addWidget(self.manager_widget)
