"""
Dialogue de Fusion Smart Merge à 3 Panneaux pour AnkiForge.
Permet d'arbitrer visuellement et interactivement les conflits de contenu entre
la base locale AnkiForge et une archive entrante (.apkg / .colpkg).
- Panneau 1 (Gauche, Rouge) : Version Locale AnkiForge
- Panneau 2 (Centre, Bleu/Éditable) : Résultat Fusionné Interactif avec boutons de transfert par champ
- Panneau 3 (Droite, Vert) : Version Entrante Anki .apkg
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ankiforge.services.cards.import_manager import ConflictItem
from ankiforge.ui.components.badges import Badge
from ankiforge.ui.components.buttons import IconButton, PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens, StyledMenu
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class ConflictFieldRow(QWidget):
    """Ligne de comparaison et d'arbitrage pour un champ spécifique (ex: Front, Back, Notes)."""

    def __init__(
        self,
        field_name: str,
        local_val: str,
        incoming_val: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.field_name = field_name
        self.local_val = local_val
        self.incoming_val = incoming_val

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(4)

        # En-tête du champ
        header_layout = QHBoxLayout()
        lbl_field = QLabel(self.field_name.upper())
        lbl_field.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold;")
        header_layout.addWidget(lbl_field)
        header_layout.addStretch()

        is_diff = self.local_val.strip() != self.incoming_val.strip()
        if is_diff:
            badge_diff = Badge("Différent", variant="warning")
            header_layout.addWidget(badge_diff)
        else:
            badge_same = Badge("Identique", variant="neutral")
            header_layout.addWidget(badge_same)

        layout.addLayout(header_layout)

        # Conteneur 3 colonnes pour ce champ
        row_splitter = QHBoxLayout()
        row_splitter.setContentsMargins(0, 0, 0, 0)
        row_splitter.setSpacing(6)

        # 1. Éditeur Local (Lecture seule)
        self.edit_local = QPlainTextEdit(self.local_val)
        self.edit_local.setReadOnly(True)
        self.edit_local.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: rgba(239, 68, 68, 0.06);
                border: 1px solid rgba(239, 68, 68, 0.3);
                border-radius: {DesignTokens.RADIUS_SM}px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-family: '{DesignTokens.FONT_CODE}';
                font-size: 11px;
                padding: 4px;
            }}
        """)
        self.edit_local.setMaximumHeight(120)
        row_splitter.addWidget(self.edit_local, 1)

        # Bouton transfert Local -> Centre
        btn_use_local = IconButton("caret-right", tooltip="Utiliser le contenu Local", size=22)
        btn_use_local.clicked.connect(self._copy_local_to_center)
        row_splitter.addWidget(btn_use_local)

        # 2. Éditeur Fusionné Central (Éditable)
        self.edit_merged = QPlainTextEdit(self.local_val)  # Par défaut, conserve la valeur locale
        self.edit_merged.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                border-radius: {DesignTokens.RADIUS_SM}px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-family: '{DesignTokens.FONT_CODE}';
                font-size: 11px;
                padding: 4px;
            }}
            QPlainTextEdit:focus {{
                border: 2px solid {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        self.edit_merged.setMaximumHeight(120)
        row_splitter.addWidget(self.edit_merged, 1)

        # Bouton transfert Entrant -> Centre
        btn_use_incoming = IconButton("caret-left", tooltip="Utiliser le contenu Entrant", size=22)
        btn_use_incoming.clicked.connect(self._copy_incoming_to_center)
        row_splitter.addWidget(btn_use_incoming)

        # 3. Éditeur Entrant (Lecture seule)
        self.edit_incoming = QPlainTextEdit(self.incoming_val)
        self.edit_incoming.setReadOnly(True)
        self.edit_incoming.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: rgba(16, 185, 129, 0.06);
                border: 1px solid rgba(16, 185, 129, 0.3);
                border-radius: {DesignTokens.RADIUS_SM}px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-family: '{DesignTokens.FONT_CODE}';
                font-size: 11px;
                padding: 4px;
            }}
        """)
        self.edit_incoming.setMaximumHeight(120)
        row_splitter.addWidget(self.edit_incoming, 1)

        layout.addLayout(row_splitter)

    def _copy_local_to_center(self) -> None:
        self.edit_merged.setPlainText(self.local_val)

    def _copy_incoming_to_center(self) -> None:
        self.edit_merged.setPlainText(self.incoming_val)

    def get_merged_value(self) -> str:
        return self.edit_merged.toPlainText()


class SmartMergeDialog(QDialog):
    """
    Dialogue de Fusion Interactive à 3 Panneaux pour résoudre les conflits d'importation.
    """

    merge_completed = Signal(dict)  # Dict[guid, resolution_dict]

    def __init__(self, conflicts: List[ConflictItem], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.conflicts = conflicts
        self.current_index = 0
        self.resolutions: Dict[str, Dict[str, Any]] = {}  # guid -> {"content": ..., "choice": ...}

        self.setWindowTitle("Smart Merge — Résolution de Conflits")
        self.resize(1100, 700)
        self.setModal(True)

        self.field_rows: Dict[str, ConflictFieldRow] = {}

        self._setup_ui()
        self._load_current_conflict()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)
        self.setStyleSheet(f"background-color: {DesignTokens.BG_MAIN};")

        # --- En-tête de Conflit ---
        header_frame = QFrame()
        header_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 8px 12px;
            }}
        """)
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(8, 6, 8, 6)
        header_layout.setSpacing(12)

        icon_merge = QLabel()
        icon_merge.setPixmap(load_phosphor_icon("git-merge", color=DesignTokens.ACCENT_PRIMARY).pixmap(24, 24))
        icon_merge.setStyleSheet("border: none; background: transparent;")
        header_layout.addWidget(icon_merge)

        info_vbox = QVBoxLayout()
        info_vbox.setSpacing(2)

        self.lbl_conflict_title = QLabel("Conflit 1 sur N")
        self.lbl_conflict_title.setFont(QFont(DesignTokens.FONT_MAIN, 13, QFont.Weight.Bold))
        self.lbl_conflict_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")

        self.lbl_conflict_meta = QLabel("Modèle : Basic | GUID : abc12345")
        self.lbl_conflict_meta.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; border: none; background: transparent;")

        info_vbox.addWidget(self.lbl_conflict_title)
        info_vbox.addWidget(self.lbl_conflict_meta)
        header_layout.addLayout(info_vbox, 1)

        self.badge_similarity = Badge("Similarité : 85%", variant="success")
        header_layout.addWidget(self.badge_similarity)

        main_layout.addWidget(header_frame)

        # --- Titres des 3 Panneaux ---
        titles_layout = QHBoxLayout()
        titles_layout.setContentsMargins(4, 0, 4, 0)
        titles_layout.setSpacing(12)

        lbl_local_title = QLabel("BASE LOCALE ANKIFORGE")
        lbl_local_title.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {DesignTokens.COLOR_RED}; text-transform: uppercase;")
        titles_layout.addWidget(lbl_local_title, 1)

        lbl_merged_title = QLabel("RÉSULTAT FUSIONNÉ (INTERACTIF)")
        lbl_merged_title.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {DesignTokens.ACCENT_PRIMARY}; text-transform: uppercase; text-align: center;")
        titles_layout.addWidget(lbl_merged_title, 1)

        lbl_incoming_title = QLabel("BASE ENTRANTE (.APKG)")
        lbl_incoming_title.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {DesignTokens.COLOR_GREEN}; text-transform: uppercase; text-align: right;")
        titles_layout.addWidget(lbl_incoming_title, 1)

        main_layout.addLayout(titles_layout)

        # --- Zone Centrale de Défilement des Champs ---
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet(f"""
            QScrollArea {{
                background-color: {DesignTokens.BG_SIDEBAR};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)

        self.fields_container = QWidget()
        self.fields_container.setStyleSheet("background: transparent;")
        self.fields_layout = QVBoxLayout(self.fields_container)
        self.fields_layout.setContentsMargins(12, 12, 12, 12)
        self.fields_layout.setSpacing(12)
        self.fields_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.scroll_area.setWidget(self.fields_container)
        main_layout.addWidget(self.scroll_area, 1)

        # --- Barre d'Actions Inférieure ---
        footer_layout = QHBoxLayout()
        footer_layout.setSpacing(8)

        self.btn_keep_local = SecondaryButton("Tout garder Local")
        self.btn_keep_local.setIcon(load_phosphor_icon("caret-double-left", color=DesignTokens.COLOR_RED))
        self.btn_keep_local.clicked.connect(self._on_keep_all_local)
        footer_layout.addWidget(self.btn_keep_local)

        self.btn_keep_incoming = SecondaryButton("Tout remplacer par Entrant")
        self.btn_keep_incoming.setIcon(load_phosphor_icon("caret-double-right", color=DesignTokens.COLOR_GREEN))
        self.btn_keep_incoming.clicked.connect(self._on_keep_all_incoming)
        footer_layout.addWidget(self.btn_keep_incoming)

        footer_layout.addStretch()

        # Pagination
        self.btn_prev = IconButton("caret-left", tooltip="Conflit précédent", size=24)
        self.btn_prev.clicked.connect(self._on_prev_conflict)
        footer_layout.addWidget(self.btn_prev)

        self.lbl_page = QLabel("1 / 1")
        self.lbl_page.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: bold; font-size: 11px;")
        footer_layout.addWidget(self.lbl_page)

        self.btn_next = IconButton("caret-right", tooltip="Conflit suivant", size=24)
        self.btn_next.clicked.connect(self._on_next_conflict)
        footer_layout.addWidget(self.btn_next)

        footer_layout.addStretch()

        self.btn_batch_menu = SecondaryButton("Appliquer à tous ▾")
        self.btn_batch_menu.clicked.connect(self._show_batch_menu)
        footer_layout.addWidget(self.btn_batch_menu)

        self.btn_confirm = PrimaryButton("Valider la Fusion")
        self.btn_confirm.setIcon(load_phosphor_icon("check", color="white"))
        self.btn_confirm.clicked.connect(self._on_confirm_merge)
        footer_layout.addWidget(self.btn_confirm)

        main_layout.addLayout(footer_layout)

    def _load_current_conflict(self) -> None:
        if not self.conflicts:
            return

        conflict = self.conflicts[self.current_index]

        # Mise à jour en-tête
        total = len(self.conflicts)
        self.lbl_conflict_title.setText(f"Conflit {self.current_index + 1} sur {total} (ID #{conflict.note_id})")
        self.lbl_conflict_meta.setText(f"Modèle : {conflict.note_type_name}  |  GUID : {conflict.guid}  |  Dossier : {conflict.local_deck} ➔ {conflict.incoming_deck}")
        self.lbl_page.setText(f"{self.current_index + 1} / {total}")

        sim = conflict.similarity_score
        variant = "success" if sim >= 80 else ("warning" if sim >= 50 else "danger")
        self.badge_similarity.setText(f"Similarité : {sim}%")
        self.badge_similarity.set_variant(variant)

        # Nettoyage des champs précédents
        while self.fields_layout.count():
            item = self.fields_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self.field_rows.clear()

        # Construction des lignes de champs
        all_keys = list(conflict.local_content.keys())
        for k in conflict.incoming_content.keys():
            if k not in all_keys:
                all_keys.append(k)

        for key in all_keys:
            local_val = conflict.local_content.get(key, "")
            incoming_val = conflict.incoming_content.get(key, "")

            row_widget = ConflictFieldRow(key, local_val, incoming_val, parent=self.fields_container)
            self.field_rows[key] = row_widget
            self.fields_layout.addWidget(row_widget)

        self.btn_prev.setEnabled(self.current_index > 0)
        self.btn_next.setEnabled(self.current_index < total - 1)

    def _save_current_resolution(self) -> None:
        if not self.conflicts:
            return
        conflict = self.conflicts[self.current_index]
        merged_dict = {key: row.get_merged_value() for key, row in self.field_rows.items()}

        existing_res = self.resolutions.get(conflict.guid, {})
        choice = existing_res.get("choice", "merged")

        if merged_dict == conflict.local_content and choice == "local":
            resolved_deck = conflict.local_deck
            resolved_tags = conflict.local_tags
        elif merged_dict == conflict.incoming_content and choice == "incoming":
            resolved_deck = conflict.incoming_deck
            resolved_tags = conflict.incoming_tags
        else:
            choice = "merged"
            resolved_deck = conflict.incoming_deck or conflict.local_deck
            resolved_tags = conflict.incoming_tags or conflict.local_tags

        self.resolutions[conflict.guid] = {
            "choice": choice,
            "content": merged_dict,
            "deck": resolved_deck,
            "tags": resolved_tags,
        }

    def _on_keep_all_local(self) -> None:
        if not self.conflicts:
            return
        conflict = self.conflicts[self.current_index]
        for key, row in self.field_rows.items():
            row.edit_merged.setPlainText(conflict.local_content.get(key, ""))
        self.resolutions[conflict.guid] = {
            "choice": "local",
            "content": conflict.local_content,
            "deck": conflict.local_deck,
            "tags": conflict.local_tags,
        }

    def _on_keep_all_incoming(self) -> None:
        if not self.conflicts:
            return
        conflict = self.conflicts[self.current_index]
        for key, row in self.field_rows.items():
            row.edit_merged.setPlainText(conflict.incoming_content.get(key, ""))
        self.resolutions[conflict.guid] = {
            "choice": "incoming",
            "content": conflict.incoming_content,
            "deck": conflict.incoming_deck,
            "tags": conflict.incoming_tags,
        }

    def _on_prev_conflict(self) -> None:
        self._save_current_resolution()
        if self.current_index > 0:
            self.current_index -= 1
            self._load_current_conflict()

    def _on_next_conflict(self) -> None:
        self._save_current_resolution()
        if self.current_index < len(self.conflicts) - 1:
            self.current_index += 1
            self._load_current_conflict()

    def _show_batch_menu(self) -> None:
        menu = StyledMenu(self)
        action_all_local = menu.addAction("Tout conserver en Local (tous les conflits)")
        action_all_local.triggered.connect(self._apply_all_local_batch)

        action_all_incoming = menu.addAction("Tout remplacer par l'Entrant (tous les conflits)")
        action_all_incoming.triggered.connect(self._apply_all_incoming_batch)

        menu.exec(self.btn_batch_menu.mapToGlobal(self.btn_batch_menu.rect().bottomLeft()))

    def _apply_all_local_batch(self) -> None:
        for conflict in self.conflicts:
            self.resolutions[conflict.guid] = {
                "choice": "local",
                "content": conflict.local_content,
                "deck": conflict.local_deck,
                "tags": conflict.local_tags,
            }
        self._load_current_conflict()

    def _apply_all_incoming_batch(self) -> None:
        for conflict in self.conflicts:
            self.resolutions[conflict.guid] = {
                "choice": "incoming",
                "content": conflict.incoming_content,
                "deck": conflict.incoming_deck,
                "tags": conflict.incoming_tags,
            }
        self._load_current_conflict()

    def _on_confirm_merge(self) -> None:
        self._save_current_resolution()

        # Pour tout conflit non encore spécifié, on applique le merged par défaut
        for conflict in self.conflicts:
            if conflict.guid not in self.resolutions:
                self.resolutions[conflict.guid] = {
                    "choice": "merged",
                    "content": conflict.local_content,
                    "deck": conflict.local_deck,
                    "tags": conflict.local_tags,
                }

        self.merge_completed.emit(self.resolutions)
        self.accept()

    def get_resolutions(self) -> Dict[str, Dict[str, Any]]:
        return self.resolutions
