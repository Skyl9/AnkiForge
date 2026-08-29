"""
Modale d'historique et de Machine à Remonter le Temps pour les Personas & Agents IA.
Permet d'explorer les versions passées, de comparer les diffs de prompts et de restaurer un état antérieur.
"""

from __future__ import annotations

import difflib
import json

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import PersonaModel, PersonaVersionModel
from ankiforge.services.ai.persona_version_service import PersonaVersionService
from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon


class PersonaPromptDiffViewer(QTextBrowser):
    """Afficheur HTML coloré comparant le prompt d'une version avec le prompt actuel."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setOpenExternalLinks(False)
        self.setStyleSheet(f"""
            QTextBrowser {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_PRIMARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                font-family: '{DesignTokens.FONT_CODE}';
                font-size: 12px;
                padding: 12px;
                line-height: 1.5;
            }}
        """)

    def set_diff(self, old_prompt: str, current_prompt: str) -> None:
        """Génère le diff HTML syntaxique coloré."""
        old_lines = (old_prompt or "").splitlines()
        cur_lines = (current_prompt or "").splitlines()

        html: list[str] = [
            "<div style='font-family: monospace; line-height: 1.6;'>",
            f"<div style='padding-bottom: 10px; font-weight: bold; color: {DesignTokens.TEXT_MUTED}; font-size: 11px; border-bottom: 1px solid {DesignTokens.BORDER_COLOR}; margin-bottom: 10px;'>",
            "DIFFÉRENTIEL DU PROMPT : <span style='color: #ef4444;'>[ROUGE = SUPPRIMÉ DANS CETTE VERSION]</span> | <span style='color: #10b981;'>[VERT = AJOUTÉ DANS CETTE VERSION]</span>",
            "</div>",
            "<table style='width: 100%; border-collapse: collapse;'>",
        ]

        diff = list(difflib.ndiff(cur_lines, old_lines))
        for line in diff:
            code = line[:2]
            text = line[2:]
            escaped_text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") or "&nbsp;"

            if code == "  ":
                html.append(
                    f"<tr><td style='color: {DesignTokens.TEXT_MUTED}; width: 25px; user-select: none; font-size: 10px;'>&nbsp;</td>"
                    f"<td style='color: {DesignTokens.TEXT_PRIMARY}; padding: 2px 6px;'>{escaped_text}</td></tr>"
                )
            elif code == "- ":
                del_style = "background-color: rgba(239, 68, 68, 0.15); color: #f87171;"
                html.append(f"<tr style='{del_style}'><td style='width: 25px; user-select: none; font-weight: bold; color: #ef4444;'>-</td><td style='padding: 2px 6px;'>{escaped_text}</td></tr>")
            elif code == "+ ":
                add_style = "background-color: rgba(16, 185, 129, 0.15); color: #34d399;"
                html.append(f"<tr style='{add_style}'><td style='width: 25px; user-select: none; font-weight: bold; color: #10b981;'>+</td><td style='padding: 2px 6px;'>{escaped_text}</td></tr>")

        html.append("</table></div>")
        self.setHtml("".join(html))


class PersonaVersionItemWidget(QWidget):
    """Widget de ligne personnalisée représentant une version dans la liste de l'historique."""

    def __init__(self, version: PersonaVersionModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.version = version

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # Ligne du haut : Badge Version + Statut Actif + Date
        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        badge_v = QLabel(f"v{version.version_number}")
        badge_v.setStyleSheet(f"""
            background-color: {DesignTokens.ACCENT_PRIMARY};
            color: white;
            font-weight: bold;
            font-size: 11px;
            padding: 2px 8px;
            border-radius: 10px;
        """)
        top_row.addWidget(badge_v)

        if version.is_active:
            badge_active = QLabel("Actif")
            badge_active.setStyleSheet("""
                background-color: rgba(16, 185, 129, 0.2);
                color: #10b981;
                font-weight: bold;
                font-size: 10px;
                padding: 2px 6px;
                border-radius: 4px;
                border: 1px solid rgba(16, 185, 129, 0.4);
            """)
            top_row.addWidget(badge_active)

        top_row.addStretch()

        created_str = version.created_at.strftime("%d/%m/%Y %H:%M") if hasattr(version.created_at, "strftime") else str(version.created_at)
        lbl_date = QLabel(created_str)
        lbl_date.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        top_row.addWidget(lbl_date)

        layout.addLayout(top_row)

        # Message de commit
        msg = version.commit_message or "Modification"
        lbl_msg = QLabel(msg)
        lbl_msg.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500;")
        lbl_msg.setWordWrap(True)
        layout.addWidget(lbl_msg)


class PersonaHistoryDialog(QDialog):
    """Dialogue modal d'exploration et de restauration des versions d'un Persona."""

    version_restored = Signal(int)

    def __init__(self, persona_id: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.persona_id = persona_id
        self.persona: PersonaModel | None = PersonaModel.get_or_none(PersonaModel.id == persona_id)
        self._selected_version: PersonaVersionModel | None = None

        self.setWindowTitle(f"Historique des Versions — {self.persona.name if self.persona else 'Agent'}")
        self.setMinimumSize(950, 650)
        self.resize(1050, 700)
        self._setup_ui()
        self._load_versions()

    def _setup_ui(self) -> None:
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {DesignTokens.BG_MAIN};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QSplitter::handle {{
                background-color: {DesignTokens.BORDER_COLOR};
                width: 1px;
            }}
            QListWidget {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                outline: none;
            }}
            QListWidget::item {{
                border-bottom: 1px solid {DesignTokens.BORDER_LIGHT};
                padding: 2px;
            }}
            QListWidget::item:selected {{
                background-color: {DesignTokens.BG_HOVER};
                border-left: 3px solid {DesignTokens.ACCENT_PRIMARY};
            }}
            QTabWidget::pane {{
                border: 1px solid {DesignTokens.BORDER_COLOR};
                background: {DesignTokens.BG_MAIN};
                border-radius: 6px;
            }}
            QTabBar::tab {{
                background: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_SECONDARY};
                padding: 8px 16px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
            }}
            QTabBar::tab:selected {{
                background: {DesignTokens.BG_MAIN};
                color: {DesignTokens.ACCENT_PRIMARY};
                font-weight: bold;
                border-bottom: 2px solid {DesignTokens.ACCENT_PRIMARY};
            }}
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 18, 18, 18)
        main_layout.setSpacing(14)

        # ── En-tête ────────────────────────────────────────────────────────────
        header_layout = QHBoxLayout()
        icon_lbl = QLabel()
        icon_lbl.setPixmap(load_phosphor_icon("ph.clock-counter-clockwise", color=DesignTokens.ACCENT_PRIMARY).pixmap(24, 24))
        header_layout.addWidget(icon_lbl)

        title_box = QVBoxLayout()
        self.title_lbl = QLabel(f"Machine à Remonter le Temps : {self.persona.name if self.persona else ''}")
        self.title_lbl.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        self.subtitle_lbl = QLabel("Explorez les révisions de prompts passées et restaurez l'état de l'agent sans perte de travail.")
        self.subtitle_lbl.setStyleSheet(f"font-size: 12px; color: {DesignTokens.TEXT_MUTED};")
        title_box.addWidget(self.title_lbl)
        title_box.addWidget(self.subtitle_lbl)
        header_layout.addLayout(title_box)
        header_layout.addStretch()

        main_layout.addLayout(header_layout)

        # ── Splitter Central ───────────────────────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Panneau Gauche : Liste des versions (340px)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        lbl_list_title = QLabel("RÉVISIONS DISPONIBLES")
        lbl_list_title.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {DesignTokens.TEXT_MUTED}; letter-spacing: 0.5px;")
        left_layout.addWidget(lbl_list_title)

        self.version_list = QListWidget()
        self.version_list.currentItemChanged.connect(self._on_version_selected)
        left_layout.addWidget(self.version_list)

        left_widget.setFixedWidth(340)
        splitter.addWidget(left_widget)

        # Panneau Droit : Détails & Diff
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)

        # Onglets de contenu
        self.tabs = QTabWidget()

        # Onglet 1 : Diff de Prompt
        self.diff_viewer = PersonaPromptDiffViewer()
        self.tabs.addTab(self.diff_viewer, "✨ Diff du System Prompt")

        # Onglet 2 : Métadonnées et Paramètres
        self.meta_browser = QTextBrowser()
        self.meta_browser.setStyleSheet(f"""
            QTextBrowser {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_PRIMARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 14px;
                font-size: 12px;
            }}
        """)
        self.tabs.addTab(self.meta_browser, "⚙️ Paramètres & Configuration")

        right_layout.addWidget(self.tabs)
        splitter.addWidget(right_widget)
        main_layout.addWidget(splitter, 1)

        # ── Barre d'Actions Inférieure ─────────────────────────────────────────
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(10)

        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 12px;")
        bottom_layout.addWidget(self.lbl_status)
        bottom_layout.addStretch()

        self.btn_close = SecondaryButton("Fermer")
        self.btn_close.clicked.connect(self.reject)
        bottom_layout.addWidget(self.btn_close)

        self.btn_restore = PrimaryButton("Restaurer cette Version")
        self.btn_restore.setIcon(load_phosphor_icon("ph.arrow-counter-clockwise", color="white"))
        self.btn_restore.clicked.connect(self._on_restore_clicked)
        self.btn_restore.setEnabled(False)
        bottom_layout.addWidget(self.btn_restore)

        main_layout.addLayout(bottom_layout)

    def _load_versions(self) -> None:
        """Charge toutes les versions disponibles pour ce persona."""
        self.version_list.clear()
        if not self.persona_id:
            return

        versions = PersonaVersionService.get_versions(self.persona_id)
        if not versions and self.persona:
            # Créer la version 1 initiale à la volée si aucune version n'existe encore
            initial_v = PersonaVersionService.create_snapshot(self.persona, commit_message="Version initiale")
            if initial_v:
                versions = [initial_v]

        for v in versions:
            item = QListWidgetItem()
            widget = PersonaVersionItemWidget(v)
            item.setSizeHint(widget.sizeHint())
            item.setData(Qt.ItemDataRole.UserRole, v.id)
            self.version_list.addItem(item)
            self.version_list.setItemWidget(item, widget)

        if self.version_list.count() > 0:
            self.version_list.setCurrentRow(0)

    @Slot(QListWidgetItem, QListWidgetItem)
    def _on_version_selected(self, current: QListWidgetItem | None, previous: QListWidgetItem | None) -> None:
        if not current:
            self._selected_version = None
            self.btn_restore.setEnabled(False)
            return

        version_id = current.data(Qt.ItemDataRole.UserRole)
        version = PersonaVersionService.get_version(version_id)
        self._selected_version = version

        if not version or not self.persona:
            return

        # Mise à jour du bouton de restauration
        self.btn_restore.setEnabled(not version.is_active)
        if version.is_active:
            self.lbl_status.setText("ℹ️ Cette version est actuellement active.")
        else:
            self.lbl_status.setText(f"Prêt à restaurer la version v{version.version_number}.")

        # 1. Diff de Prompt
        current_prompt = self.persona.system_prompt or ""
        self.diff_viewer.set_diff(old_prompt=version.system_prompt or "", current_prompt=current_prompt)

        # 2. Métadonnées HTML
        tools_list: list[str] = []
        try:
            tools_list = json.loads(version.allowed_tools or "[]")
        except Exception:
            tools_list = []

        tools_badges = (
            " ".join([f"<span style='background: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; padding: 2px 6px; border-radius: 4px;'>{t}</span>" for t in tools_list])
            or "<em>Aucun outil assigné</em>"
        )

        engine_name = version.llm_config.display_name if version.llm_config else "Hérité du projet / Global"

        meta_html = f"""
        <div style='line-height: 1.8;'>
            <h3 style='color: {DesignTokens.ACCENT_PRIMARY}; margin-top: 0;'>Configuration Version v{version.version_number}</h3>
            <table style='width: 100%; border-collapse: collapse;'>
                <tr><td style='width: 160px; color: {DesignTokens.TEXT_MUTED}; font-weight: bold;'>Description :</td><td>{version.description or "<em>Non renseignée</em>"}</td></tr>
                <tr><td style='color: {DesignTokens.TEXT_MUTED}; font-weight: bold;'>Format de Sortie :</td><td><b>{version.output_format.upper()}</b></td></tr>
                <tr><td style='color: {DesignTokens.TEXT_MUTED}; font-weight: bold;'>Portée d'Usage :</td><td>{version.persona_type.capitalize()}</td></tr>
                <tr><td style='color: {DesignTokens.TEXT_MUTED}; font-weight: bold;'>Moteur LLM :</td><td>{engine_name}</td></tr>
                <tr><td style='color: {DesignTokens.TEXT_MUTED}; font-weight: bold; vertical-align: top;'>Outils Autorisés :</td><td>{tools_badges}</td></tr>
            </table>
        </div>
        """
        self.meta_browser.setHtml(meta_html)

    @Slot()
    def _on_restore_clicked(self) -> None:
        if not self._selected_version or not self.persona:
            return

        v_num = self._selected_version.version_number
        reply = QMessageBox.question(
            self,
            "Confirmer la restauration",
            f"Êtes-vous sûr de vouloir restaurer le persona '{self.persona.name}' à la version v{v_num} ?\n\nLe prompt et les paramètres actuels seront remplacés.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            PersonaVersionService.restore_version(self._selected_version.id)
            show_toast(self, f"Version v{v_num} restaurée avec succès !")
            self.version_restored.emit(self.persona.id)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Échec de la restauration : {str(e)}")
