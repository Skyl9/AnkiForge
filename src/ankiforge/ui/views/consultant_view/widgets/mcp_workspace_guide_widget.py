"""Sous-onglet d'amorçage de guides méthodologiques et de gestion des workspaces MCP.

Permet à l'utilisateur de générer les adaptateurs d'instructions (CLAUDE.md, GEMINI.md,
.cursorrules, ANKIFORGE_GUIDE.md) dans le répertoire cible de son choix via init_agent_workspace,
d'auditer l'intégrité de la version du guide via check_guide_version, de prévisualiser
le rendu Markdown in-app et de consulter les personas MCP configurées.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import PersonaModel
from ankiforge.services.ai.mcp_server import (
    _GUIDE_AGENT_FILENAMES,
    _normalise_agent_type,
    check_guide_version,
    init_agent_workspace,
)
from ankiforge.ui.components.badges import Badge, StatusBadge
from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton
from ankiforge.ui.components.inputs import StyledComboBox
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.i18n import tr
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class MCPWorkspaceGuideWidget(QWidget):
    """Composant sous-onglet d'amorçage de workspaces et visualisation des guides MCP."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("MCPWorkspaceGuideWidget")

        self._current_guide_content: str = ""
        self._personas_cache: list[PersonaModel] = []

        self._setup_ui()
        self._on_agent_or_options_changed()
        self.reload_personas()

    @property
    def current_guide_content(self) -> str:
        """Retourne le contenu Markdown actuel du guide compilé."""
        return self._current_guide_content

    @property
    def current_target_filename(self) -> str:
        """Retourne le nom du fichier de destination selon l'agent sélectionné."""
        agent_type = str(self.combo_agent_type.currentData() or "generic")
        normalised = _normalise_agent_type(agent_type)
        return _GUIDE_AGENT_FILENAMES.get(normalised, "ANKIFORGE_GUIDE.md")

    def _setup_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(*DesignTokens.DESIGN_SYSTEM_MARGES["mcp_root"])
        root_layout.setSpacing(DesignTokens.DESIGN_SYSTEM_SPACING["mcp_root"])

        # ── Splitter horizontal principal (45% Contrôles / 55% Visualiseur) ──
        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.splitter.setObjectName("mcp_workspace_splitter")
        self.splitter.setChildrenCollapsible(False)

        # ═════════════════════════════════════════════════════════════════════
        # PANNEAU GAUCHE : Formulaire d'amorçage + Personas MCP
        # ═════════════════════════════════════════════════════════════════════
        left_container = QWidget(self.splitter)
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 8, 0)
        left_layout.setSpacing(12)

        # ── Carte 1 : Formulaire d'amorçage de workspace ──
        self.card_init = QFrame(left_container)
        self.card_init.setObjectName("mcp_card_init_workspace")
        init_layout = QVBoxLayout(self.card_init)
        init_layout.setContentsMargins(16, 16, 16, 16)
        init_layout.setSpacing(12)

        header_init = QHBoxLayout()
        header_init.setSpacing(8)
        lbl_init_icon = QLabel(self.card_init)
        lbl_init_icon.setPixmap(load_phosphor_icon("ph.folder-plus", color=DesignTokens.ACCENT_PRIMARY).pixmap(20, 20))
        header_init.addWidget(lbl_init_icon)

        lbl_init_title = QLabel(self.tr("Amorçage de Workspace Agent"), self.card_init)
        lbl_init_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 14px; font-weight: 700; border: none; background: transparent;")
        header_init.addWidget(lbl_init_title)
        header_init.addStretch()
        init_layout.addLayout(header_init)

        lbl_init_subtitle = QLabel(
            self.tr("Générez les adaptateurs d'instructions personnalisés et vérifiez l'intégrité de vos guides."),
            self.card_init,
        )
        lbl_init_subtitle.setWordWrap(True)
        lbl_init_subtitle.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11.5px; border: none; background: transparent;")
        init_layout.addWidget(lbl_init_subtitle)

        # Champ 1 : Sélecteur de type d'agent
        lbl_agent = QLabel(self.tr("Type d'agent & format cible :"), self.card_init)
        lbl_agent.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 600; border: none; background: transparent;")
        init_layout.addWidget(lbl_agent)

        self.combo_agent_type = StyledComboBox(self.card_init)
        self.combo_agent_type.setObjectName("mcp_combo_agent_type")
        self.combo_agent_type.addItem(self.tr("Claude Code / Desktop (CLAUDE.md)"), userData="claude")
        self.combo_agent_type.addItem(self.tr("Google Gemini (GEMINI.md)"), userData="gemini")
        self.combo_agent_type.addItem(self.tr("Cursor / Windsurf (.cursorrules)"), userData="cursor")
        self.combo_agent_type.addItem(self.tr("Antigravity CLI (GEMINI.md)"), userData="agy")
        self.combo_agent_type.addItem(self.tr("Universel / Générique (ANKIFORGE_GUIDE.md)"), userData="generic")
        self.combo_agent_type.currentIndexChanged.connect(self._on_agent_or_options_changed)
        init_layout.addWidget(self.combo_agent_type)

        # Champ 2 : Répertoire cible
        lbl_dir = QLabel(self.tr("Répertoire de travail cible :"), self.card_init)
        lbl_dir.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 600; border: none; background: transparent;")
        init_layout.addWidget(lbl_dir)

        path_row = QHBoxLayout()
        path_row.setSpacing(6)

        self.edit_workspace_path = QLineEdit(self.card_init)
        self.edit_workspace_path.setObjectName("mcp_edit_workspace_path")
        self.edit_workspace_path.setPlaceholderText(self.tr("ex: ~/mon-projet ou /chemin/vers/workspace"))
        self.edit_workspace_path.setStyleSheet(
            f"background-color: {DesignTokens.BG_INPUT}; color: {DesignTokens.TEXT_PRIMARY}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 6px; padding: 6px 10px; font-size: 12px;"
        )
        path_row.addWidget(self.edit_workspace_path, 1)

        self.btn_browse = SecondaryButton(self.tr("Parcourir..."), parent=self.card_init)
        self.btn_browse.setObjectName("mcp_btn_browse_workspace")
        self.btn_browse.setIcon(load_phosphor_icon("ph.folder-open", color=DesignTokens.TEXT_PRIMARY))
        self.btn_browse.clicked.connect(self._on_browse_workspace)
        path_row.addWidget(self.btn_browse)
        init_layout.addLayout(path_row)

        # Option : Inclusion catalogue
        self.chk_include_catalogue = QCheckBox(
            self.tr("Inclure le catalogue exhaustif des 58 outils"),
            self.card_init,
        )
        self.chk_include_catalogue.setObjectName("mcp_chk_include_catalogue")
        self.chk_include_catalogue.setChecked(True)
        self.chk_include_catalogue.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; background: transparent;")
        self.chk_include_catalogue.toggled.connect(self._on_agent_or_options_changed)
        init_layout.addWidget(self.chk_include_catalogue)

        # Boutons d'action
        btn_action_row = QHBoxLayout()
        btn_action_row.setSpacing(8)

        self.btn_init_workspace = PrimaryButton(self.tr("Amorcer le workspace"), parent=self.card_init)
        self.btn_init_workspace.setObjectName("mcp_btn_init_workspace")
        self.btn_init_workspace.setIcon(load_phosphor_icon("ph.sparkle", color=DesignTokens.TEXT_PRIMARY))
        self.btn_init_workspace.clicked.connect(self._on_init_workspace)
        btn_action_row.addWidget(self.btn_init_workspace)

        self.btn_check_version = SecondaryButton(self.tr("Vérifier la version"), parent=self.card_init)
        self.btn_check_version.setObjectName("mcp_btn_check_version")
        self.btn_check_version.setIcon(load_phosphor_icon("ph.shield-check", color=DesignTokens.TEXT_PRIMARY))
        self.btn_check_version.clicked.connect(self._on_check_version)
        btn_action_row.addWidget(self.btn_check_version)

        btn_action_row.addStretch()
        init_layout.addLayout(btn_action_row)

        # Statut d'audit de version
        version_status_row = QHBoxLayout()
        version_status_row.setSpacing(10)

        lbl_status_tag = QLabel(self.tr("État du guide sur disque :"), self.card_init)
        lbl_status_tag.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 12px; border: none; background: transparent;")
        version_status_row.addWidget(lbl_status_tag)

        self.badge_version_status = StatusBadge(self.tr("Non vérifié"), "ph.question", variant="neutral")
        self.badge_version_status.setObjectName("mcp_badge_version_status")
        version_status_row.addWidget(self.badge_version_status)

        self.lbl_version_detail = QLabel("", self.card_init)
        self.lbl_version_detail.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; border: none; background: transparent;")
        version_status_row.addWidget(self.lbl_version_detail, 1)

        init_layout.addLayout(version_status_row)
        left_layout.addWidget(self.card_init)

        # ── Carte 2 : Personas MCP & Agents Dédiés ──
        self.card_personas = QFrame(left_container)
        self.card_personas.setObjectName("mcp_card_personas")
        personas_layout = QVBoxLayout(self.card_personas)
        personas_layout.setContentsMargins(16, 14, 16, 16)
        personas_layout.setSpacing(10)

        header_personas = QHBoxLayout()
        header_personas.setSpacing(8)

        lbl_personas_icon = QLabel(self.card_personas)
        lbl_personas_icon.setPixmap(load_phosphor_icon("ph.users-three", color=DesignTokens.ACCENT_PRIMARY).pixmap(18, 18))
        header_personas.addWidget(lbl_personas_icon)

        lbl_personas_title = QLabel(self.tr("Personas MCP & Agents Dédiés"), self.card_personas)
        lbl_personas_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 13.5px; font-weight: 700; border: none; background: transparent;")
        header_personas.addWidget(lbl_personas_title)

        header_personas.addStretch()

        self.btn_refresh_personas = SecondaryButton(self.tr("Actualiser"), parent=self.card_personas)
        self.btn_refresh_personas.setIcon(load_phosphor_icon("ph.arrows-clockwise", color=DesignTokens.TEXT_PRIMARY))
        self.btn_refresh_personas.clicked.connect(self.reload_personas)
        header_personas.addWidget(self.btn_refresh_personas)

        personas_layout.addLayout(header_personas)

        # Liste des personas
        self.list_personas = QListWidget(self.card_personas)
        self.list_personas.setObjectName("mcp_list_personas")
        self.list_personas.setMaximumHeight(130)
        self.list_personas.setStyleSheet(
            f"QListWidget#mcp_list_personas {{ background-color: {DesignTokens.BG_INPUT}; "
            f"border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 6px; padding: 4px; "
            f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; }} "
            f"QListWidget#mcp_list_personas::item {{ padding: 5px 8px; border-radius: 4px; }} "
            f"QListWidget#mcp_list_personas::item:selected {{ background-color: {DesignTokens.BG_ACTIVE}; color: {DesignTokens.TEXT_PRIMARY}; }}"
        )
        self.list_personas.currentItemChanged.connect(self._on_persona_selected)
        personas_layout.addWidget(self.list_personas)

        # Détail de la persona sélectionnée
        self.lbl_persona_description = QLabel(
            self.tr("Sélectionnez un agent pour inspecter sa consigne."),
            self.card_personas,
        )
        self.lbl_persona_description.setWordWrap(True)
        self.lbl_persona_description.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11.5px; border: none; background: transparent;")
        personas_layout.addWidget(self.lbl_persona_description)

        lbl_prompt_title = QLabel(self.tr("Prompt système (Consigne IA) :"), self.card_personas)
        lbl_prompt_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11.5px; font-weight: 600; border: none; background: transparent;")
        personas_layout.addWidget(lbl_prompt_title)

        self.edit_persona_prompt = QPlainTextEdit(self.card_personas)
        self.edit_persona_prompt.setObjectName("mcp_edit_persona_prompt")
        self.edit_persona_prompt.setReadOnly(True)
        self.edit_persona_prompt.setMaximumHeight(110)
        self.edit_persona_prompt.setStyleSheet(
            f"QPlainTextEdit#mcp_edit_persona_prompt {{ background-color: {DesignTokens.BG_INPUT}; "
            f"color: {DesignTokens.TEXT_PRIMARY}; border: 1px solid {DesignTokens.BORDER_COLOR}; "
            f"border-radius: 6px; font-family: {DesignTokens.FONT_CODE}; font-size: 11px; padding: 6px; }}"
        )
        personas_layout.addWidget(self.edit_persona_prompt)

        left_layout.addWidget(self.card_personas, 1)
        self.splitter.addWidget(left_container)

        # ═════════════════════════════════════════════════════════════════════
        # PANNEAU DROIT : Visualiseur Markdown in-app
        # ═════════════════════════════════════════════════════════════════════
        self.card_preview = QFrame(self.splitter)
        self.card_preview.setObjectName("mcp_card_guide_preview")
        preview_layout = QVBoxLayout(self.card_preview)
        preview_layout.setContentsMargins(16, 14, 16, 16)
        preview_layout.setSpacing(10)

        # Barre d'actions du visualiseur
        preview_header = QHBoxLayout()
        preview_header.setSpacing(8)

        lbl_preview_icon = QLabel(self.card_preview)
        lbl_preview_icon.setPixmap(load_phosphor_icon("ph.book-open", color=DesignTokens.ACCENT_PRIMARY).pixmap(20, 20))
        preview_header.addWidget(lbl_preview_icon)

        lbl_preview_title = QLabel(self.tr("Guide Méthodologique Compilé"), self.card_preview)
        lbl_preview_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 14px; font-weight: 700; border: none; background: transparent;")
        preview_header.addWidget(lbl_preview_title)

        self.badge_target_file = Badge("", variant="neutral")
        self.badge_target_file.setObjectName("mcp_badge_target_file")
        preview_header.addWidget(self.badge_target_file)

        preview_header.addStretch()

        self.btn_copy_guide = SecondaryButton(self.tr("Copier le Markdown"), parent=self.card_preview)
        self.btn_copy_guide.setObjectName("mcp_btn_copy_guide")
        self.btn_copy_guide.setIcon(load_phosphor_icon("ph.copy", color=DesignTokens.TEXT_PRIMARY))
        self.btn_copy_guide.clicked.connect(self._copy_markdown)
        preview_header.addWidget(self.btn_copy_guide)

        self.btn_refresh_preview = SecondaryButton(self.tr("Rafraîchir"), parent=self.card_preview)
        self.btn_refresh_preview.setObjectName("mcp_btn_refresh_preview")
        self.btn_refresh_preview.setIcon(load_phosphor_icon("ph.arrows-clockwise", color=DesignTokens.TEXT_PRIMARY))
        self.btn_refresh_preview.clicked.connect(self._on_agent_or_options_changed)
        preview_header.addWidget(self.btn_refresh_preview)

        preview_layout.addLayout(preview_header)

        # Visualiseur HTML / Markdown stylisé
        self.preview_browser = QTextBrowser(self.card_preview)
        self.preview_browser.setObjectName("mcp_preview_guide_browser")
        self.preview_browser.setOpenExternalLinks(True)
        self.preview_browser.setStyleSheet(
            f"QTextBrowser#mcp_preview_guide_browser {{ background-color: {DesignTokens.BG_INPUT}; "
            f"color: {DesignTokens.TEXT_PRIMARY}; border: 1px solid {DesignTokens.BORDER_COLOR}; "
            f"border-radius: 6px; padding: 14px; font-size: 12.5px; }}"
        )
        preview_layout.addWidget(self.preview_browser, 1)

        self.splitter.addWidget(self.card_preview)
        self.splitter.setStretchFactor(0, 45)
        self.splitter.setStretchFactor(1, 55)

        root_layout.addWidget(self.splitter, 1)

    def _on_agent_or_options_changed(self) -> None:
        """Régénère dynamiquement l'aperçu du guide en fonction de l'agent et des options."""
        agent_type = str(self.combo_agent_type.currentData() or "claude")
        include_catalogue = self.chk_include_catalogue.isChecked()

        try:
            content = init_agent_workspace(
                agent_type=agent_type,
                workspace_path="",
                include_catalogue=include_catalogue,
            )
        except Exception as exc:
            logger.error("Erreur lors de la génération de l'aperçu du guide : %s", exc)
            content = tr("Erreur lors de la génération de l'aperçu : %1", str(exc))

        self._current_guide_content = content
        self.preview_browser.setMarkdown(content)

        # Actualiser le badge du nom de fichier cible
        target_name = self.current_target_filename
        self.badge_target_file.setText(target_name)

    def _on_browse_workspace(self) -> None:
        """Ouvre un dialogue de sélection de dossier natif pour renseigner le workspace cible."""
        current_text = self.edit_workspace_path.text().strip()
        start_dir = current_text if current_text and Path(current_text).exists() else str(Path.home())
        selected = QFileDialog.getExistingDirectory(
            self,
            self.tr("Sélectionner le répertoire cible du workspace"),
            start_dir,
        )
        if selected:
            self.edit_workspace_path.setText(selected)
            self._on_check_version()

    def _on_init_workspace(self) -> None:
        """Amorce le workspace en écrivant le guide méthodologique sur disque."""
        target_path = self.edit_workspace_path.text().strip()
        agent_type = str(self.combo_agent_type.currentData() or "claude")
        include_catalogue = self.chk_include_catalogue.isChecked()

        if not target_path:
            show_toast(
                self,
                self.tr("Veuillez sélectionner un répertoire cible pour amorcer le workspace."),
                level="warning",
            )
            return

        try:
            content = init_agent_workspace(
                agent_type=agent_type,
                workspace_path=target_path,
                include_catalogue=include_catalogue,
            )
            self._current_guide_content = content
            self.preview_browser.setMarkdown(content)

            filename = self.current_target_filename
            show_toast(
                self,
                tr("Guide '%1' généré avec succès dans : %2", filename, target_path),
                level="info",
            )
            self._on_check_version()
        except Exception as exc:
            logger.error("Échec de l'amorçage du workspace : %s", exc)
            show_toast(self, tr("Échec de l'amorçage : %1", str(exc)), level="danger")

    def _on_check_version(self) -> None:
        """Vérifie si le guide présent dans le workspace est synchronisé avec le serveur."""
        target_path = self.edit_workspace_path.text().strip()
        agent_type = str(self.combo_agent_type.currentData() or "claude")

        if not target_path:
            self.badge_version_status.set_status(self.tr("Non défini"), "ph.warning", variant="neutral")
            self.lbl_version_detail.setText(self.tr("Renseignez un dossier cible."))
            return

        try:
            raw_res = check_guide_version(workspace_path=target_path, agent_type=agent_type)
            data = json.loads(raw_res)

            file_path_str = data.get("file_path")
            target_file = Path(file_path_str) if file_path_str else (Path(target_path).expanduser() / self.current_target_filename)

            if not target_file.exists():
                self.badge_version_status.set_status(self.tr("Absent"), "ph.x-circle", variant="danger")
                self.lbl_version_detail.setText(tr("Fichier non trouvé : %1", self.current_target_filename))
            elif data.get("stale"):
                self.badge_version_status.set_status(self.tr("Obsolète"), "ph.warning-circle", variant="warning")
                self.lbl_version_detail.setText(tr("Guide désynchronisé (%1)", self.current_target_filename))
            else:
                self.badge_version_status.set_status(self.tr("À jour"), "ph.check-circle", variant="success")
                self.lbl_version_detail.setText(tr("Intégrité SHA-256 validée (%1)", self.current_target_filename))
        except Exception as exc:
            logger.warning("Erreur audit version guide : %s", exc)
            self.badge_version_status.set_status(self.tr("Erreur"), "ph.warning", variant="danger")
            self.lbl_version_detail.setText(str(exc))

    def _copy_markdown(self) -> None:
        """Copie l'intégralité du Markdown compilé dans le presse-papiers."""
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None and self._current_guide_content:
            clipboard.setText(self._current_guide_content)
            show_toast(self, self.tr("Guide méthodologique copié dans le presse-papiers."))

    def reload_personas(self) -> None:
        """Charge ou rafraîchit la liste des personas MCP depuis la base de données."""
        self.list_personas.clear()
        try:
            self._personas_cache = list(PersonaModel.select().order_by(PersonaModel.name.asc()))
        except Exception as exc:
            logger.warning("Impossible de charger les personas MCP : %s", exc)
            self._personas_cache = []

        if not self._personas_cache:
            item = QListWidgetItem(self.tr("(Aucune persona configurée)"))
            item.setData(Qt.ItemDataRole.UserRole, None)
            self.list_personas.addItem(item)
            self.lbl_persona_description.setText(self.tr("Aucune persona IA configurée dans la collection."))
            self.edit_persona_prompt.setPlainText("")
            return

        for p in self._personas_cache:
            type_label = f"[{p.persona_type.upper()}]" if p.persona_type else "[MCP]"
            item = QListWidgetItem(f"{p.name}  {type_label}")
            item.setIcon(load_phosphor_icon("ph.robot", color=DesignTokens.ACCENT_PRIMARY))
            item.setData(Qt.ItemDataRole.UserRole, p.id)
            self.list_personas.addItem(item)

        # Sélectionner le premier par défaut
        self.list_personas.setCurrentRow(0)

    def _on_persona_selected(self, current: QListWidgetItem | None, previous: QListWidgetItem | None) -> None:
        """Affiche les détails de la persona sélectionnée."""
        if current is None:
            return
        p_id = current.data(Qt.ItemDataRole.UserRole)
        if p_id is None:
            return

        persona = next((p for p in self._personas_cache if p.id == p_id), None)
        if persona is None:
            return

        desc = persona.description or self.tr("(Aucune description)")
        raw_tools = persona.allowed_tools or "[]"
        try:
            tools = json.loads(raw_tools) if isinstance(raw_tools, str) else raw_tools
            tools_count = len(tools) if isinstance(tools, list) else 0
        except Exception:
            tools_count = 0

        tools_str = self.tr("Accès universel à tous les outils") if not raw_tools or "*" in raw_tools else tr("%1 outils autorisés", tools_count)
        self.lbl_persona_description.setText(f"{desc}\n• {tools_str}")
        self.edit_persona_prompt.setPlainText(persona.system_prompt or "")

    def refresh_theme(self, profile: Any) -> None:
        """Adapte les styles et les couleurs selon le profil de thème actif."""
        bg_panel = getattr(profile, "bg_panel", DesignTokens.BG_PANEL)
        border_color = getattr(profile, "border_color", DesignTokens.BORDER_COLOR)
        bg_input = getattr(profile, "bg_input", DesignTokens.BG_INPUT)
        text_primary = getattr(profile, "text_primary", DesignTokens.TEXT_PRIMARY)
        bg_active = getattr(profile, "bg_active", DesignTokens.BG_ACTIVE)

        card_style_tpl = "QFrame#{name} {{ background-color: {bg}; border: 1px solid {border}; border-radius: 8px; }} QFrame#{name} QLabel {{ border: none; background: transparent; }}"

        if hasattr(self, "card_init"):
            self.card_init.setStyleSheet(card_style_tpl.format(name="mcp_card_init_workspace", bg=bg_panel, border=border_color))
        if hasattr(self, "card_personas"):
            self.card_personas.setStyleSheet(card_style_tpl.format(name="mcp_card_personas", bg=bg_panel, border=border_color))
        if hasattr(self, "card_preview"):
            self.card_preview.setStyleSheet(card_style_tpl.format(name="mcp_card_guide_preview", bg=bg_panel, border=border_color))

        if hasattr(self, "edit_workspace_path"):
            self.edit_workspace_path.setStyleSheet(f"background-color: {bg_input}; color: {text_primary}; border: 1px solid {border_color}; border-radius: 6px; padding: 6px 10px; font-size: 12px;")

        if hasattr(self, "list_personas"):
            self.list_personas.setStyleSheet(
                f"QListWidget#mcp_list_personas {{ background-color: {bg_input}; "
                f"border: 1px solid {border_color}; border-radius: 6px; padding: 4px; "
                f"color: {text_primary}; font-size: 12px; }} "
                f"QListWidget#mcp_list_personas::item {{ padding: 5px 8px; border-radius: 4px; }} "
                f"QListWidget#mcp_list_personas::item:selected {{ background-color: {bg_active}; color: {text_primary}; }}"
            )

        if hasattr(self, "edit_persona_prompt"):
            self.edit_persona_prompt.setStyleSheet(
                f"QPlainTextEdit#mcp_edit_persona_prompt {{ background-color: {bg_input}; "
                f"color: {text_primary}; border: 1px solid {border_color}; "
                f"border-radius: 6px; font-family: {DesignTokens.FONT_CODE}; font-size: 11px; padding: 6px; }}"
            )

        if hasattr(self, "preview_browser"):
            self.preview_browser.setStyleSheet(
                f"QTextBrowser#mcp_preview_guide_browser {{ background-color: {bg_input}; "
                f"color: {text_primary}; border: 1px solid {border_color}; "
                f"border-radius: 6px; padding: 14px; font-size: 12.5px; }}"
            )

        if hasattr(self, "badge_version_status"):
            self.badge_version_status.refresh_theme(profile)
        if hasattr(self, "badge_target_file"):
            self.badge_target_file.refresh_theme(profile)


__all__ = ["MCPWorkspaceGuideWidget"]
