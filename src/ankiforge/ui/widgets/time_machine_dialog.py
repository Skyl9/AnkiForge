"""
Machine à Remonter le Temps (Time Machine) Unifiée d'AnkiForge.
Permet d'explorer l'historique complet des versions d'une note (NoteVersionModel),
de visualiser les différences textuelles colorées (rouge/vert) et de restaurer une version en 1 clic.
"""

from __future__ import annotations

import difflib
import json
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, Signal
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

from ankiforge.database.models import NoteModel, NoteVersionModel, db
from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.card_preview_widget import CardPreviewWidget
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon


class DiffViewerWidget(QTextBrowser):
    """Afficheur HTML de Diff syntaxique coloré avec numéros de lignes."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
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
                padding: 10px;
            }}
        """)

    def set_content_diff(self, old_dict: Dict[str, str], current_dict: Dict[str, str]) -> None:
        """Génère le diff HTML comparant la version historique (old) à la version active (current)."""
        html: List[str] = [
            "<div style='font-family: monospace; line-height: 1.5;'>",
            f"<div style='padding-bottom: 8px; font-weight: bold; color: {DesignTokens.TEXT_MUTED}; font-size: 11px;'>",
            "COMPARAISON AVEC LA VERSION ACTUELLE : <span style='color: #ef4444;'>[ROUGE = SUPPRESSION]</span> | <span style='color: #10b981;'>[VERT = AJOUT]</span>",
            "</div>",
        ]

        all_fields = sorted(list(set(list(old_dict.keys()) + list(current_dict.keys()))))

        for field in all_fields:
            old_val = old_dict.get(field, "")
            cur_val = current_dict.get(field, "")

            header_style = (
                f"background-color: {DesignTokens.BG_PANEL}; "
                "padding: 4px 8px; margin-top: 10px; margin-bottom: 4px; "
                f"font-weight: bold; border-radius: 4px; color: {DesignTokens.ACCENT_PRIMARY};"
            )
            html.append(f"<div style='{header_style}'>Champ : {field}</div>")

            old_lines = old_val.splitlines() if old_val else [""]
            cur_lines = cur_val.splitlines() if cur_val else [""]

            diff = list(difflib.ndiff(cur_lines, old_lines))
            html.append("<table style='width: 100%; border-collapse: collapse; margin-bottom: 12px;'>")

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
                    # Présent dans l'actuel mais absent de l'historique (sera supprimé si restauré)
                    del_style = "background-color: rgba(239, 68, 68, 0.15); color: #f87171;"
                    html.append(f"<tr style='{del_style}'><td style='width: 25px; user-select: none; font-weight: bold;'>-</td>" f"<td style='padding: 2px 6px;'>{escaped_text}</td></tr>")
                elif code == "+ ":
                    # Présent dans l'historique mais absent de l'actuel (sera restauré)
                    add_style = "background-color: rgba(16, 185, 129, 0.15); color: #34d399;"
                    html.append(f"<tr style='{add_style}'><td style='width: 25px; user-select: none; font-weight: bold;'>+</td>" f"<td style='padding: 2px 6px;'>{escaped_text}</td></tr>")

            html.append("</table>")

        html.append("</div>")
        self.setHtml("".join(html))


class TimeMachineDialog(QDialog):
    """
    Modale Time Machine consolidée :
    - Timeline chronologique des versions de la note
    - Diff textuel coloré (rouge/vert) comparant à la version active
    - Aperçu du rendu HTML/KaTeX de la version sélectionnée
    - Bouton de restauration en 1 clic
    """

    version_restored = Signal(int, dict)  # note_id, restored_content_dict

    def __init__(
        self,
        note: NoteModel | int | None = None,
        note_id: int | None = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)

        if isinstance(note, int):
            try:
                self.note = NoteModel.get_by_id(note)
            except Exception:
                self.note = NoteModel.select().first() or NoteModel()
        elif note_id is not None:
            try:
                self.note = NoteModel.get_by_id(note_id)
            except Exception:
                self.note = NoteModel.select().first() or NoteModel()
        elif isinstance(note, NoteModel):
            self.note = note
        else:
            self.note = NoteModel.select().first() or NoteModel()

        self.versions: List[NoteVersionModel] = []
        self.active_version: Optional[NoteVersionModel] = None
        self.selected_version: Optional[NoteVersionModel] = None
        self.active_content: Dict[str, str] = {}

        self.setWindowTitle(f"🕒 Machine à Remonter le Temps — Carte #{getattr(self.note, 'id', '?')}")
        self.resize(920, 580)
        self.setStyleSheet(f"background-color: {DesignTokens.BG_MAIN};")

        self._setup_ui()
        self._load_versions()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(10)

        # En-tête
        header_layout = QHBoxLayout()
        header_title = QLabel(f"Historique & Versions de la Note #{getattr(self.note, 'id', '?')}")
        header_title.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        header_layout.addWidget(header_title)

        note_type_name = getattr(getattr(self.note, "note_type", None), "name", "Standard")
        lbl_model = QLabel(f"Modèle : {note_type_name}")
        lbl_model.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_MUTED};")
        header_layout.addWidget(lbl_model)
        header_layout.addStretch()

        main_layout.addLayout(header_layout)

        # Zone centrale (Splitter Timeline <-> Comparaison/Aperçu)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setStyleSheet(f"QSplitter::handle {{ background-color: {DesignTokens.BORDER_COLOR}; width: 4px; }}")

        # --- PANNEAU GAUCHE : Timeline ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        timeline_lbl = QLabel("TIMELINE DES VERSIONS")
        timeline_lbl.setStyleSheet(f"font-size: 10px; font-weight: bold; color: {DesignTokens.TEXT_MUTED}; letter-spacing: 1px;")
        left_layout.addWidget(timeline_lbl)

        self.version_list = QListWidget()
        self.version_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                outline: none;
            }}
            QListWidget::item {{
                padding: 10px;
                color: {DesignTokens.TEXT_PRIMARY};
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
            }}
            QListWidget::item:selected {{
                background-color: rgba(99, 102, 241, 0.15);
                border-left: 3px solid {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        self.version_list.itemSelectionChanged.connect(self._on_version_selected)
        left_layout.addWidget(self.version_list)

        self.splitter.addWidget(left_widget)

        # --- PANNEAU DROIT : Onglets Diff & Aperçu ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {DesignTokens.BORDER_COLOR};
                background: {DesignTokens.BG_MAIN};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
            QTabBar::tab {{
                background: {DesignTokens.BG_PANEL};
                color: {DesignTokens.TEXT_MUTED};
                padding: 6px 14px;
                font-weight: bold;
                font-size: 11px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }}
            QTabBar::tab:selected {{
                background: {DesignTokens.BG_MAIN};
                color: {DesignTokens.ACCENT_PRIMARY};
                border-bottom: 2px solid {DesignTokens.ACCENT_PRIMARY};
            }}
        """)

        # Onglet 1 : Diff Textuel
        self.diff_viewer = DiffViewerWidget()
        self.tabs.addTab(self.diff_viewer, "🔍 Diff Comparatif")

        # Onglet 2 : Rendu Live Preview
        self.preview_widget = CardPreviewWidget(show_header=False)
        self.tabs.addTab(self.preview_widget, "👁️ Aperçu du Rendu")

        right_layout.addWidget(self.tabs)

        self.splitter.addWidget(right_widget)
        self.splitter.setSizes([280, 600])

        main_layout.addWidget(self.splitter)

        # Barre d'actions inférieure
        bottom_layout = QHBoxLayout()
        self.btn_close = SecondaryButton("Fermer")
        self.btn_close.clicked.connect(self.reject)
        bottom_layout.addWidget(self.btn_close)

        bottom_layout.addStretch()

        self.btn_restore = PrimaryButton("Restaurer cette version")
        self.btn_restore.setIcon(load_phosphor_icon("arrow-counter-clockwise", color="white"))
        self.btn_restore.clicked.connect(self._restore_selected_version)
        self.btn_restore.setEnabled(False)
        bottom_layout.addWidget(self.btn_restore)

        main_layout.addLayout(bottom_layout)

    def _load_versions(self) -> None:
        """Charge l'ensemble des versions enregistrées pour cette note."""
        self.version_list.clear()
        if not getattr(self.note, "id", None):
            return

        query = NoteVersionModel.select().where(NoteVersionModel.note == self.note).order_by(NoteVersionModel.version_number.desc())
        self.versions = list(query)

        self.active_version = None
        for v in self.versions:
            if v.is_active:
                self.active_version = v
                try:
                    self.active_content = json.loads(v.content)
                except Exception:
                    self.active_content = {}
                break

        for v in self.versions:
            item = QListWidgetItem()
            src_label = self._format_source_label(str(v.source))
            active_badge = " [Actuelle]" if v.is_active else ""
            date_str = v.created_at.strftime("%d/%m/%Y %H:%M") if hasattr(v, "created_at") and v.created_at else ""

            item.setText(f"v{v.version_number}{active_badge}  —  {src_label}\n📅 {date_str}")
            item.setData(Qt.ItemDataRole.UserRole, v)
            self.version_list.addItem(item)

        if self.version_list.count() > 0:
            self.version_list.setCurrentRow(0)

    def _format_source_label(self, source: str) -> str:
        mapping = {
            "manual": "✏️ Manuel",
            "auto_tag": "🏷️ Auto-Tag",
            "linter": "🩺 Linter IA",
            "batch_edit": "⚡ Édition par Lot",
            "import": "📦 Import",
            "merge": "🤝 Fusion",
            "initial": "🌱 Création",
        }
        return mapping.get(source, f"🔧 {source}")

    def _on_version_selected(self) -> None:
        selected_items = self.version_list.selectedItems()
        if not selected_items:
            self.btn_restore.setEnabled(False)
            return

        version: NoteVersionModel = selected_items[0].data(Qt.ItemDataRole.UserRole)
        self.selected_version = version

        try:
            version_dict = json.loads(version.content)
        except Exception:
            version_dict = {}

        # 1. Mise à jour du Diff Viewer
        self.diff_viewer.set_content_diff(version_dict, self.active_content)

        # 2. Mise à jour de l'Aperçu
        note_type = getattr(self.note, "note_type", None)
        self.preview_widget.update_preview(note_type=note_type, fields_dict=version_dict)

        # Le bouton de restauration n'est actif que si la version choisie n'est pas déjà l'actuelle
        self.btn_restore.setEnabled(not version.is_active)

    def _restore_selected_version(self) -> None:
        if not self.selected_version or not self.note:
            return

        reply = QMessageBox.question(
            self,
            "Confirmer la restauration",
            f"Voulez-vous restaurer la version v{self.selected_version.version_number} ?\nUne nouvelle version sera automatiquement créée.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            content_dict = json.loads(self.selected_version.content)
            with db.atomic():
                new_v = self.note.add_version(content_dict, source=f"restore_v{self.selected_version.version_number}")

            self.version_restored.emit(self.note.id, content_dict)
            show_toast(self, f"Version v{self.selected_version.version_number} restaurée avec succès (v{new_v.version_number}).")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Erreur de restauration", f"Impossible de restaurer la version : {e}")
